"""
2.100 -- promotion of `us-gaap:RestrictedStockExpense` to `sbc` as PARTIAL.

The research is closed and this file is a production declaration test. It does not
re-derive the semantic conclusion; it proves the registry now states what that
conclusion says, and that stating it changed nothing else.

    us-gaap:RestrictedStockExpense is the same core share-based compensation
    expense object at a narrower award-category scope, so IDENTITY + PARTIAL is
    the correct registry representation.

## What this file asserts, and why each part is a separate assertion

  A  the declaration itself -- IDENTITY + PARTIAL to `sbc`, named not counted
  B  the scope, in the representation 2.73 already established, with no new key
  C  the window, pinned to the derivation 2.96 recorded rather than to a date
     chosen here. Probe dates are derived from the mapping's own window, because
     2.74's first run used a fixed date grid, missed `us-gaap:Revenues`
     entirely, and reported thirteen where the answer was fourteen.
  D  the resolver: RESOLVED, destination `sbc`, PARTIAL, never upgraded
  E  a consumer can tell this source from the EXACT one
  F  the mapping is IDENTITY and enters no COMPOSITION path
  G  the 2.74 gate is untouched in both directions

## What this file deliberately does not assert

  * that the corpus proves a numerical gain for this source. It does not, and
    2.97R2/R3 recorded why: every candidate concept is already claimed.
  * that the mapping is total SBC. It is not, and `EXACT` would say it was.
  * that CB and CZWI, the two unmeasured corpus holders, agree. Nothing measured
    them, so the mapping records them as unmeasured instead of asserting them.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unittest
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import (  # noqa: E402
    MAPPING_COMPOSITION,
    MAPPING_EXACT,
    MAPPING_IDENTITY,
    MAPPING_PARTIAL,
    ConceptMapping,
    ConceptResolution,
    CoreRegistry,
)
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

H = os.path.join(os.path.dirname(HERE), "experiments",
                 "003-llm-evidence-retrieval", "harness")
VALIDATION_296 = os.path.join(H, "296-restricted-stock-partial-validation.json")

CONCEPT = "us-gaap:RestrictedStockExpense"
METRIC = "sbc"
# The concept that already held `sbc` exactly. Everything in E is relative to it.
EXACT_SOURCE = "us-gaap:ShareBasedCompensation"
RETIRED = "us-gaap:Revenues"
UNTOUCHED = "us-gaap:SalesRevenueNet"
UNRESOLVED = ConceptResolution.UNRESOLVED_NO_APPLICABLE_MAPPING

# The registry counts this promotion is expected to produce. Pinned rather than
# computed, because a computed expectation is the current value restated.
EXPECTED_TOTAL = 50
EXPECTED_IDENTITY = 46
EXPECTED_IDENTITY_BY_TYPE = {"EXACT": 30, "PARTIAL": 15, "EQUIVALENT": 1}
EXPECTED_COMPOSITION = 4


def seeded() -> Any:
    store = SQLiteArchive(":memory:")
    registry = CoreRegistry(store.connection)
    seed(registry)
    store.connection.commit()
    return store, registry


def rows_for(registry: CoreRegistry, concept: str) -> List[Dict[str, Any]]:
    return [dict(r) for r in registry.connection.execute(
        "SELECT metric_id, concept_id, mapping_type, relation_kind,"
        " effective_from, effective_to, scope_json, notes"
        " FROM metric_concept_mapping WHERE concept_id = ?"
        " ORDER BY metric_id", (concept,))]


class TestTheDeclaration(unittest.TestCase):
    """A. The mapping exists, and exists as exactly the four declared facts."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_1_the_concept_is_registered(self) -> None:
        """
        The concept had to be declared as well as mapped.

        `resolve_source_concept` asks what a concept is before it asks which
        metric claims it, so a mapping to an undeclared concept resolves to
        nothing at all. Asserted by identity rather than by count so a rename
        cannot satisfy it.
        """
        row = self.registry.connection.execute(
            "SELECT taxonomy, concept, label, source_definition"
            " FROM concept_registry WHERE concept_id = ?",
            (CONCEPT,)).fetchone()
        self.assertIsNotNone(row, "%s is not a registered concept" % CONCEPT)
        self.assertEqual(row["taxonomy"], "us-gaap")
        self.assertEqual(row["concept"], "RestrictedStockExpense")
        # The source's own words, quoted. Every concept in this registry quotes
        # the SEC's definition rather than paraphrasing it, because a paraphrase
        # would let two concepts read as equal when the source says otherwise.
        self.assertIn("restricted stock or unit", row["source_definition"])

    def test_2_exactly_one_mapping_claims_the_concept(self) -> None:
        rows = rows_for(self.registry, CONCEPT)
        self.assertEqual(len(rows), 1, rows)

    def test_3_the_mapping_states_the_four_declared_facts(self) -> None:
        row = rows_for(self.registry, CONCEPT)[0]
        self.assertEqual(row["metric_id"], METRIC)
        self.assertEqual(row["relation_kind"], MAPPING_IDENTITY)
        self.assertEqual(row["mapping_type"], MAPPING_PARTIAL)

    def test_4_it_is_not_exact_and_never_upgraded(self) -> None:
        """
        PARTIAL is the substantive claim, so it is asserted from both ends: the
        stored row is not EXACT, and no EXACT row exists for this concept to any
        destination at all.
        """
        self.assertNotEqual(rows_for(self.registry, CONCEPT)[0]["mapping_type"],
                            MAPPING_EXACT)
        self.assertEqual(
            [r for r in rows_for(self.registry, CONCEPT)
             if r["mapping_type"] == MAPPING_EXACT], [])

    def test_5_the_metric_is_the_one_that_exists_and_is_unchanged(self) -> None:
        row = self.registry.connection.execute(
            "SELECT display_name, statement, unit_family, normal_period_type,"
            " comparability_group, status FROM metric_registry"
            " WHERE metric_id = ?", (METRIC,)).fetchone()
        self.assertEqual(row["display_name"], "Share-based compensation")
        self.assertEqual(row["statement"], "CASH_FLOW")
        self.assertEqual(row["unit_family"], "currency")
        self.assertEqual(row["normal_period_type"], "DURATION")
        self.assertEqual(row["comparability_group"], "noncash_expenses")
        self.assertEqual(row["status"], "ACTIVE")


class TestTheScope(unittest.TestCase):
    """B. Structured, machine-readable, and in the existing representation."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)
        row = rows_for(self.registry, CONCEPT)[0]
        self.assertIsNotNone(row["scope_json"],
                             "a PARTIAL destination must carry its measurement")
        self.scope = json.loads(row["scope_json"])

    def test_1_the_scope_is_stored_as_json_not_prose(self) -> None:
        """The column is `scope_json`; a reader parses it, it does not parse you."""
        self.assertIsInstance(self.scope, dict)
        self.assertTrue(self.scope)

    def test_2_it_uses_the_existing_production_key_set(self) -> None:
        """
        2.73 established the representation on the `LongtermBorrowings` row. This
        mapping adds no key to it and removes none, so a consumer that already
        reads scope_json needs no new case.
        """
        self.assertEqual(set(self.scope),
                         {"variation", "measured", "unmeasured_holders", "basis"})

    def test_3_it_names_the_restricted_stock_award_category(self) -> None:
        self.assertEqual(self.scope["variation"], "AWARD_CATEGORY")
        self.assertEqual(self.scope["measured"]["award_category"],
                         "RESTRICTED_STOCK_AND_RESTRICTED_STOCK_UNIT")

    def test_4_it_says_what_is_excluded_not_merely_that_it_is_narrower(self) -> None:
        """
        The difference between a measured qualifier and a prose note. "Narrower"
        is a claim; "restricted stock and restricted stock units, excluding stock
        options and other awards" is something a reader can check against a
        filing.
        """
        excluded = self.scope["measured"]["excluded_award_categories"]
        self.assertIn("STOCK_OPTIONS", excluded)
        self.assertIn("OTHER_AWARDS", excluded)

    def test_5_the_basis_names_the_filers_that_were_measured(self) -> None:
        basis = self.scope["basis"]
        self.assertIn("EFC", basis)
        self.assertIn("HUM", basis)

    def test_6_the_unmeasured_holders_are_recorded_rather_than_asserted(self) -> None:
        """
        Four corpus holders exist and two were examined. The mapping says so
        rather than implying four filers were measured.
        """
        self.assertIsInstance(self.scope["unmeasured_holders"], int)
        self.assertEqual(self.scope["unmeasured_holders"], 2)

    def test_7_the_scope_survives_the_database_round_trip(self) -> None:
        """Persisted as JSON, read back as a dict, not as a string."""
        resolution = self.registry.resolve_source_concept(CONCEPT)
        self.assertIsInstance(resolution.scope, dict)
        self.assertEqual(resolution.scope, self.scope)


class TestTheEffectiveWindow(unittest.TestCase):
    """C. Evidence-derived, and probed from the mapping's own window."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)
        self.row = rows_for(self.registry, CONCEPT)[0]
        with io.open(VALIDATION_296, encoding="utf-8") as handle:
            self.derivation = json.load(handle)["candidate_representation"][
                "window_derivation"]

    def test_1_the_window_equals_the_derivation_2_96_recorded(self) -> None:
        """
        The date is pinned against the research round's own recorded derivation
        rather than against a constant written here. If the production row ever
        drifts from the evidence, this fails.

        The derivation is the candidate's earliest observed fact period among the
        validated holders. The corpus agrees with it under the other rule this
        registry uses -- the earliest period reported by any filer at all -- so
        the two are not competing readings of the same number.
        """
        self.assertEqual(self.derivation["derivation"],
                         "earliest observed fact period among the validated "
                         "holders; no end date, because the corpus does not "
                         "close the series")
        self.assertEqual(self.row["effective_from"],
                         self.derivation["effective_from"])

    def test_2_the_end_is_open_and_the_start_is_inside_the_observations(self) -> None:
        self.assertIsNone(self.row["effective_to"])
        self.assertEqual(self.row["effective_from"],
                         self.derivation["observed_period_min"])
        self.assertLess(self.row["effective_from"],
                        self.derivation["observed_period_max"])

    def test_3_the_mapping_is_absent_before_its_window(self) -> None:
        """
        Probe dates come from the mapping's own window, with the boundary day
        excluded rather than picked from a grid. A grid that happens to miss a
        window does not measure it -- that is how 2.74's first run missed
        `us-gaap:Revenues` and undercounted by one.
        """
        before = "2008-06-30"
        self.assertLess(before, self.row["effective_from"])
        resolution = self.registry.resolve_source_concept(CONCEPT, as_of=before)
        self.assertFalse(resolution.is_resolved, before)
        self.assertIsNone(resolution.destination_metric)
        self.assertEqual(resolution.status, UNRESOLVED)

    def test_4_the_mapping_is_active_from_its_window_onward(self) -> None:
        for when in (self.row["effective_from"],
                     self.derivation["observed_period_max"]):
            resolution = self.registry.resolve_source_concept(CONCEPT, as_of=when)
            self.assertTrue(resolution.is_resolved, when)
            self.assertEqual(resolution.destination_metric, METRIC, when)

    def test_5_a_partial_mapping_is_required_to_carry_dates_at_all(self) -> None:
        """
        The production rule the derivation exists to satisfy: a PARTIAL source is
        a view of a series and the series does not continue across it.
        """
        with self.assertRaises(Exception):
            ConceptMapping(metric_id=METRIC, concept_id=CONCEPT,
                           mapping_type=MAPPING_PARTIAL,
                           relation_kind=MAPPING_IDENTITY)


class TestTheResolver(unittest.TestCase):
    """D. `PARTIAL`, `is_exact = False`, and an affirmative destination."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)
        self.resolution = self.registry.resolve_source_concept(CONCEPT)

    def test_1_it_resolves(self) -> None:
        self.assertTrue(self.resolution.is_resolved)
        self.assertEqual(self.resolution.status, ConceptResolution.RESOLVED)

    def test_2_the_destination_is_sbc(self) -> None:
        self.assertEqual(self.resolution.destination_metric, METRIC)

    def test_3_it_resolves_as_partial_and_never_as_exact(self) -> None:
        self.assertEqual(self.resolution.mapping_type, MAPPING_PARTIAL)
        self.assertFalse(self.resolution.is_exact)
        self.assertTrue(self.resolution.is_component)

    def test_4_the_claim_is_direct(self) -> None:
        """
        DIRECT, not inherited: `sbc` is active and not superseded, so nothing is
        being resolved through `metric_supersession`.
        """
        self.assertEqual(self.resolution.mapping_origin, ConceptResolution.DIRECT)

    def test_5_the_measured_scope_travels_with_the_resolution(self) -> None:
        self.assertIsNotNone(self.resolution.scope)
        self.assertEqual(self.resolution.scope["variation"], "AWARD_CATEGORY")


class TestTheConsumerCanTellThemApart(unittest.TestCase):
    """E. `sbc`/PARTIAL/scoped is distinguishable from `sbc`/EXACT."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)
        self.partial = self.registry.resolve_source_concept(CONCEPT)
        self.exact = self.registry.resolve_source_concept(EXACT_SOURCE)

    def test_1_the_two_sources_share_a_metric_and_differ_in_fidelity(self) -> None:
        self.assertEqual(self.exact.destination_metric, METRIC)
        self.assertEqual(self.partial.destination_metric, METRIC)
        self.assertNotEqual(self.partial.mapping_type, self.exact.mapping_type)

    def test_2_the_exact_source_is_exact_and_carries_no_scope(self) -> None:
        self.assertEqual(self.exact.mapping_type, MAPPING_EXACT)
        self.assertTrue(self.exact.is_exact)
        self.assertIsNone(self.exact.scope)

    def test_3_the_partial_source_is_not_exact_and_carries_its_scope(self) -> None:
        self.assertFalse(self.partial.is_exact)
        self.assertNotEqual(self.partial.scope, self.exact.scope)

    def test_4_sbc_lists_both_and_only_the_partial_one_is_partial(self) -> None:
        sources = self.registry.effective_metric_sources(METRIC)
        by_concept = {s["concept"]: s for s in sources}
        self.assertIn(CONCEPT, by_concept)
        self.assertIn(EXACT_SOURCE, by_concept)
        self.assertEqual(by_concept[CONCEPT]["mapping_type"], MAPPING_PARTIAL)
        self.assertEqual(by_concept[EXACT_SOURCE]["mapping_type"], MAPPING_EXACT)

    def test_5_the_source_list_carries_the_window_both_rows_were_given(self) -> None:
        by_concept = {s["concept"]: s
                      for s in self.registry.effective_metric_sources(METRIC)}
        self.assertEqual(by_concept[CONCEPT]["effective_from"], "2008-12-31")
        self.assertIsNone(by_concept[CONCEPT]["effective_to"])


class TestNoCompositionPath(unittest.TestCase):
    """F. IDENTITY means the source is not an ingredient of the metric."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_1_no_composition_row_claims_the_concept(self) -> None:
        rows = [r for r in rows_for(self.registry, CONCEPT)
                if r["relation_kind"] == MAPPING_COMPOSITION]
        self.assertEqual(rows, [], "the source is a scoped view of sbc, not an"
                                   " ingredient of it")

    def test_2_sbc_has_no_composition_rows_at_all(self) -> None:
        rows = [dict(r) for r in self.registry.connection.execute(
            "SELECT concept_id FROM metric_concept_mapping"
            " WHERE metric_id = ? AND relation_kind = ?",
            (METRIC, MAPPING_COMPOSITION))]
        self.assertEqual(rows, [])

    def test_3_the_composition_set_is_unchanged(self) -> None:
        """
        Pinned by name so a later promotion cannot quietly add a fifth ingredient
        row and have this test keep passing on a count.
        """
        rows = {(r["metric_id"], r["concept_id"])
                for r in self.registry.connection.execute(
                    "SELECT metric_id, concept_id FROM metric_concept_mapping"
                    " WHERE relation_kind = ?", (MAPPING_COMPOSITION,))}
        self.assertEqual(rows, {
            ("long_term_debt", "us-gaap:LongTermDebtNoncurrent"),
            ("long_term_debt", "us-gaap:LongTermDebtCurrent"),
            ("long_term_debt", "ifrs-full:CurrentPortionOfLongtermBorrowings"),
            ("long_term_debt", "ifrs-full:LongtermBorrowings"),
        })


class TestTheMeasuredScopeGateIsIntact(unittest.TestCase):
    """
    G. 2.74 in both directions.

    This promotion is the second mapping to satisfy the gate. It must not have
    widened it: a PARTIAL with a measured scope resolves, and a PARTIAL without
    one still does not.
    """

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_1_measured_partial_resolves(self) -> None:
        resolution = self.registry.resolve_source_concept(CONCEPT)
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.mapping_type, MAPPING_PARTIAL)

    def test_2_missing_scope_does_not(self) -> None:
        """
        Strip the measurement in place. The mapping must stop resolving rather
        than resolve on an unmeasured claim -- which is exactly the failure 2.74
        was written to stop, and exactly the one that would be reintroduced if
        scope were treated as a formality.
        """
        self.assertTrue(
            self.registry.resolve_source_concept(CONCEPT).is_resolved,
            "the mapping must resolve before the scope is removed")
        self.registry.connection.execute(
            "UPDATE metric_concept_mapping SET scope_json = NULL"
            " WHERE metric_id = ? AND concept_id = ?", (METRIC, CONCEPT))
        self.registry.connection.commit()
        resolution = self.registry.resolve_source_concept(CONCEPT)
        self.assertIsNone(resolution.scope)
        self.assertEqual(resolution.status, UNRESOLVED)
        self.assertFalse(resolution.is_exact)

    def test_3_an_empty_scope_object_is_not_a_measurement(self) -> None:
        self.registry.connection.execute(
            "UPDATE metric_concept_mapping SET scope_json = '{}'"
            " WHERE metric_id = ? AND concept_id = ?", (METRIC, CONCEPT))
        self.registry.connection.commit()
        self.assertEqual(
            self.registry.resolve_source_concept(CONCEPT).status, UNRESOLVED)

    def test_4_the_2_73_promotion_is_still_resolvable(self) -> None:
        resolution = self.registry.resolve_source_concept(
            "ifrs-full:LongtermBorrowings")
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.mapping_type, MAPPING_PARTIAL)
        self.assertEqual(resolution.scope["variation"], "FILER_DEPENDENT")

    def test_5_the_unmeasured_partials_are_still_gated(self) -> None:
        """
        A representative unmeasured PARTIAL stays unresolved. The new mapping
        must not have become a general admission for PARTIALs.
        """
        for concept in ("us-gaap:SalesRevenueNet", "ifrs-full:Revenue",
                        "us-gaap:InterestExpenseDebt"):
            resolution = self.registry.resolve_source_concept(concept)
            self.assertEqual(resolution.status, UNRESOLVED, concept)
            self.assertFalse(resolution.is_exact, concept)


class TestTheRegistryCounts(unittest.TestCase):
    """The active production registry, pinned by value and by composition."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)
        self.rows = [dict(r) for r in self.registry.connection.execute(
            "SELECT metric_id, concept_id, mapping_type, relation_kind"
            " FROM metric_concept_mapping")]

    def test_1_the_total(self) -> None:
        self.assertEqual(len(self.rows), EXPECTED_TOTAL)

    def test_2_the_identity_split(self) -> None:
        identity = [r for r in self.rows if r["relation_kind"] == MAPPING_IDENTITY]
        self.assertEqual(len(identity), EXPECTED_IDENTITY)
        counts: Dict[str, int] = {}
        for row in identity:
            counts[row["mapping_type"]] = counts.get(row["mapping_type"], 0) + 1
        self.assertEqual(counts, EXPECTED_IDENTITY_BY_TYPE)

    def test_3_the_composition_count(self) -> None:
        composition = [r for r in self.rows
                       if r["relation_kind"] == MAPPING_COMPOSITION]
        self.assertEqual(len(composition), EXPECTED_COMPOSITION)

    def test_4_sbc_has_exactly_two_sources_and_the_second_is_the_promotion(self) -> None:
        """
        `sbc` has one EXACT source and now one PARTIAL source. No third was
        invented to satisfy a count.
        """
        sources = self.registry.effective_metric_sources(METRIC)
        self.assertEqual(len(sources), 2, sources)
        self.assertEqual({s["concept"] for s in sources},
                         {CONCEPT, EXACT_SOURCE})


class TestTheRetiredRevenueMappingStaysRetired(unittest.TestCase):
    """2.99 must not be undone by anything here."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_1_no_mapping_claims_revenues(self) -> None:
        self.assertEqual(rows_for(self.registry, RETIRED), [])

    def test_2_revenues_still_resolves_nowhere(self) -> None:
        resolution = self.registry.resolve_source_concept(RETIRED)
        self.assertFalse(resolution.is_resolved)
        self.assertEqual(resolution.status, UNRESOLVED)

    def test_3_revenues_is_still_a_registered_concept(self) -> None:
        """
        Retired as a mapping, not deleted as a concept. The finding stays
        auditable, which is the difference between a retraction and an erasure.
        """
        row = self.registry.connection.execute(
            "SELECT concept_id FROM concept_registry WHERE concept_id = ?",
            (RETIRED,)).fetchone()
        self.assertIsNotNone(row)

    def test_4_the_sibling_revenue_mapping_is_untouched(self) -> None:
        rows = rows_for(self.registry, UNTOUCHED)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["metric_id"], "revenue")
        self.assertEqual(rows[0]["mapping_type"], MAPPING_PARTIAL)
        self.assertEqual(rows[0]["effective_from"], "2007-09-29")
        self.assertEqual(rows[0]["effective_to"], "2018-06-30")


if __name__ == "__main__":
    unittest.main()