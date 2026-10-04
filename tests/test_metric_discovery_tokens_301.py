"""
3.01 production contract -- `metric_discovery_tokens.effective_metric_tokens`.

Candidate discovery fallback is evaluated **per mapped concept**. Adding a mapped
concept with a discriminating token cannot suppress fallback required by another
mapped concept.

## Why this file needs no corpus

`effective_metric_tokens` is a pure function of a metric's mapped concepts and a
caller-supplied informative-token set. Nothing here reads the archive, the
payload corpus or a harness artefact, so every case below is decided in
microseconds and the suite runs in a clean checkout.

That separation is the point of the extraction. The rule had no committed owner
and lived inside an untracked research round, which is how a defect that removed
223 candidates from `sbc` and 598 and 409 from two debt metrics survived a
production commit with no test failing. The corpus-backed blast radius is
measured separately and stays in the research record; this file owns the rule.

## What is deliberately not asserted

No historical candidate count. `17`, `53`, `224` and `240` are telemetry about
particular registry states and particular corpora, and a test pinning any of them
would fail on a legitimate recall change while passing through a recall collapse.
The assertions are on the rule, on set containment, and on the absence of
duplication.

The `r_and_d` mandatory control is unchanged and is not restated here; it belongs
to the research record that already established it, and restating it would give a
corpus-dependent test a permanent home it does not need.
"""

from __future__ import annotations

import itertools
import os
import sys
import unittest
from typing import Dict, Set, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from metric_discovery_tokens import (  # noqa: E402
    STOP,
    effective_metric_tokens,
    tokens,
)

# Invented on purpose. The rule under test is token arithmetic over whatever set
# the caller supplies, so binding these tests to real concept names would let a
# future registry change move them for a reason that has nothing to do with the
# rule. One real shape is used in the regression case below because the defect
# was reported in those terms and the name is what makes it recognisable.
NO_USEFUL_TOKEN = "us-gaap:AlphaBeta"
ALSO_NO_USEFUL_TOKEN = "us-gaap:EpsilonZeta"
WITH_RESTRICTED = "us-gaap:RestrictedStockExpense"


def select(mapped, informative: Set[str]
           ) -> Tuple[Set[str], Dict[str, dict]]:
    effective, report = effective_metric_tokens(mapped, informative)
    return set(effective), {row["concept_id"]: row for row in report}


class TestTokenisation(unittest.TestCase):
    """The one behaviour the rule depends on, pinned so it cannot drift."""

    def test_camel_case_is_split_into_lowercase_tokens(self) -> None:
        self.assertEqual(tokens("ShareBasedCompensation"),
                         {"share", "based", "compensation"})

    def test_tokens_is_not_prefix_aware_and_the_rule_is(self) -> None:
        """
        The prefix strip lives in the caller, so this pins where it actually is.

        `tokens()` is a plain tokeniser and will happily return `ifrs` and `full`
        from a qualified id. `effective_metric_tokens` is what partitions on the
        taxonomy prefix first, so the rule never sees it. Getting that wrong once
        pulled oil and gas depletion into a research and development pool on the
        strength of "full cost method".
        """
        qualified = "ifrs-full:ResearchAndDevelopmentExpense"
        self.assertIn("full", tokens(qualified))
        self.assertIn("ifrs", tokens(qualified))

        effective, report = select([qualified], set())
        self.assertEqual(effective, {"research", "development", "expense"})
        self.assertNotIn("full", effective)
        self.assertNotIn("ifrs", effective)
        self.assertNotIn("full", report[qualified]["tokens"])

    def test_stop_words_and_short_tokens_are_dropped(self) -> None:
        self.assertEqual(tokens("GainLossOnSaleOfAssetsAndLiabilitiesOfAnEntity"),
                         {"gain", "loss", "sale", "assets", "liabilities",
                          "entity"})
        for stop_word in STOP:
            self.assertNotIn(stop_word, tokens("Some" + stop_word.capitalize()
                                               + "Thing"))

    def test_several_names_can_be_tokenised_at_once(self) -> None:
        self.assertEqual(tokens("ShareBasedCompensation", "RestrictedUnitExpense"),
                         {"share", "based", "compensation", "restricted", "unit",
                          "expense"})


class TestCase1SingleConceptWithNoDiscriminatingToken(unittest.TestCase):
    """Fallback must fire when the filter empties a concept."""

    def test_the_fallback_tokens_are_retained(self) -> None:
        effective, report = select([NO_USEFUL_TOKEN], set())
        self.assertEqual(effective, {"alpha", "beta"})
        self.assertTrue(report[NO_USEFUL_TOKEN]["token_fallback_used"])

    def test_the_report_says_what_the_filter_discarded(self) -> None:
        _effective, report = select([NO_USEFUL_TOKEN], set())
        row = report[NO_USEFUL_TOKEN]
        self.assertEqual(row["discriminating"], [])
        self.assertEqual(row["filtered_out"], ["alpha", "beta"])
        self.assertEqual(row["effective"], ["alpha", "beta"])


class TestCase2SingleConceptWithADiscriminatingToken(unittest.TestCase):
    """Behaviour that was already right, and must stay right."""

    def test_only_the_discriminating_token_is_retained(self) -> None:
        effective, report = select([NO_USEFUL_TOKEN], {"alpha"})
        self.assertEqual(effective, {"alpha"})
        self.assertFalse(report[NO_USEFUL_TOKEN]["token_fallback_used"])

    def test_the_filter_is_not_loosened_for_a_partly_filterable_concept(self) -> None:
        """
        Fallback rescues a concept the filter would have silenced, not one the
        filter only partly silenced. `beta` stays out.
        """
        _effective, report = select([NO_USEFUL_TOKEN], {"alpha"})
        self.assertEqual(report[NO_USEFUL_TOKEN]["filtered_out"], ["beta"])
        self.assertNotIn("beta", report[NO_USEFUL_TOKEN]["effective"])


class TestCase3TheRegressionShape(unittest.TestCase):
    """
    Two mapped concepts: one needs the fallback, one has a discriminating token.

    This is the exact defect. Under the pre-3.01 rule the fallback was tested on
    the union, so `restricted` alone made the union non-empty, the fallback
    switched off for *both* concepts, and every candidate arriving on `alpha` or
    `beta` was dropped with no documented filter behind it.

    Measured on the real corpus, that was 223 lost candidates for `sbc`, 598 for
    `long_term_debt_current` and 409 for `long_term_debt_noncurrent`.
    """

    def test_the_concept_that_needs_the_fallback_still_contributes_it(self) -> None:
        effective, _report = select([WITH_RESTRICTED, NO_USEFUL_TOKEN], {"restricted"})
        self.assertIn("restricted", effective)
        self.assertIn("alpha", effective)
        self.assertIn("beta", effective)

    def test_each_concept_reports_its_own_decision(self) -> None:
        _effective, report = select([WITH_RESTRICTED, NO_USEFUL_TOKEN],
                                    {"restricted"})
        self.assertFalse(report[WITH_RESTRICTED]["token_fallback_used"])
        self.assertTrue(report[NO_USEFUL_TOKEN]["token_fallback_used"])

    def test_the_pre_3_01_rule_would_have_dropped_those_tokens(self) -> None:
        """
        The control, so case 3 cannot pass by accident.

        Stated as the arithmetic the old code performed rather than asserted
        against code that no longer exists: the pre-3.01 effective set was the
        union intersected with `informative`, which here is a strict subset of the
        per-concept set.
        """
        informative = {"restricted"}
        union = tokens(WITH_RESTRICTED) | tokens(NO_USEFUL_TOKEN)
        pre_3_01 = (union & informative) or union
        effective, _report = select([WITH_RESTRICTED, NO_USEFUL_TOKEN], informative)
        self.assertEqual(pre_3_01, {"restricted"})
        self.assertLess(pre_3_01, effective)
        self.assertEqual(effective - pre_3_01, {"alpha", "beta"})


class TestCase4Monotonicity(unittest.TestCase):
    """
    D(R1) is a subset of D(R2) where R2 adds one mapped concept.

    Exhaustively, because three concepts have six orderings and the property is
    free to check exhaustively. A counterexample is found here rather than in a
    corpus-sized run.
    """

    CONCEPTS = (NO_USEFUL_TOKEN, WITH_RESTRICTED, ALSO_NO_USEFUL_TOKEN)

    def test_adding_a_concept_never_shrinks_the_effective_set(self) -> None:
        for informative in (set(), {"restricted"}, {"restricted", "epsilon"}):
            for order in itertools.permutations(self.CONCEPTS):
                previous: Set[str] = set()
                for size in range(1, len(order) + 1):
                    current, _ = select(list(order[:size]), informative)
                    self.assertLessEqual(
                        previous, current,
                        "informative=%s adding %s shrank the effective set"
                        % (sorted(informative), order[size - 1]))
                    previous = current

    def test_a_useful_concept_never_removes_a_useless_one_contribution(self) -> None:
        """
        The predicate stated directly, in the shape the defect took: before and
        after differ only by the addition of a concept with a discriminating
        token, and nothing before may be missing afterwards.
        """
        before, _ = select([NO_USEFUL_TOKEN], set())
        after, _ = select([NO_USEFUL_TOKEN, WITH_RESTRICTED], {"restricted"})
        self.assertLessEqual(before, after)
        self.assertEqual(after - before, {"restricted"})


class TestNoDuplication(unittest.TestCase):
    """A repair that widens recall by unioning token sets must not double-count."""

    def test_the_effective_set_has_no_duplicates(self) -> None:
        effective, report = select(
            [NO_USEFUL_TOKEN, WITH_RESTRICTED, ALSO_NO_USEFUL_TOKEN],
            {"restricted"})
        self.assertEqual(len(effective), len(set(effective)))
        # Reported per concept, so a shared token is reported twice rather than
        # merged away -- the report is a per-concept account, not a tally.
        self.assertEqual(len(report), 3)

    def test_a_shared_token_is_contributed_by_each_concept_that_has_it(self) -> None:
        """
        Two concepts whose names share a token must both show it, and the union
        must still contain it exactly once.
        """
        effective, report = select([NO_USEFUL_TOKEN, ALSO_NO_USEFUL_TOKEN], set())
        self.assertIn("alpha", report[NO_USEFUL_TOKEN]["effective"])
        self.assertIn("epsilon", report[ALSO_NO_USEFUL_TOKEN]["effective"])
        self.assertEqual(len(effective), len(set(effective)))

    def test_the_result_is_independent_of_the_order_concepts_arrive_in(self) -> None:
        """
        A union does not accumulate, so ordering cannot change what is searched
        for. Asserted because a future implementation that accumulated into a
        counter, or deduplicated destructively, would still pass the containment
        tests above.
        """
        forward, forward_report = select(
            [NO_USEFUL_TOKEN, WITH_RESTRICTED], {"restricted"})
        backward, backward_report = select(
            [WITH_RESTRICTED, NO_USEFUL_TOKEN], {"restricted"})
        self.assertEqual(forward, backward)
        self.assertEqual({k: v["effective"] for k, v in forward_report.items()},
                         {k: v["effective"] for k, v in backward_report.items()})


class TestTheDegenerateState(unittest.TestCase):
    """A metric with no mapped concepts is real and must not raise."""

    def test_an_empty_mapped_set_yields_an_empty_result(self) -> None:
        effective, report = select([], set())
        self.assertEqual(effective, set())
        self.assertEqual(report, {})


if __name__ == "__main__":
    unittest.main()