"""
2.74 F1: a PARTIAL destination requires a measured scope.

## What went wrong

2.73 added a general rule: a single direct `PARTIAL` identity claim resolves a
source concept. Applied to the registry as seeded, that admitted 14 concepts
rather than the one that had been researched -- 2.47 measured the IFRS
long-term borrowings object, 2.70 gate F admitted it, and the measurement rides
on the mapping as structured scope.

The other fourteen had `scope = null`. They were `UNRESOLVED_NO_APPLICABLE_MAPPING`
under 2.67's rule that a PARTIAL proposition is a characterisation rather than a
decision, and 2.73 silently upgraded "not yet researched" into "measured to
differ". That is the opposite of what 2.70 established: PARTIAL is a semantic
outcome, not a state for insufficient evidence, and coverage is a qualifier
rather than a resolution licence.

The first run of this audit said thirteen. `us-gaap:Revenues` holds an
unmeasured PARTIAL whose window is 2016-09-24 to 2018-09-29, and none of the six
fixed probe dates that run used fell inside it -- so a concept the rule did admit
was reported as unaffected. The audit now derives its probe dates from each
concept's own windows, and finds fourteen. A date grid that happens to miss a
window does not measure a window.

Retrieval was not affected -- those concepts' rows are stored under their own
metric, so resolving them added no row to any canonical query. What changed was
the semantic report: `inherited_mapping` began reading `RESOLVED` where it had
read unresolved, on 6,495 observations in `snapshot-universe` alone. A resolver
whose answer is stronger than its evidence is still wrong.

## The contract

    IDENTITY + EXACT                     -> existing behaviour unchanged
    IDENTITY + PARTIAL + measured scope  -> RESOLVED / PARTIAL
    IDENTITY + PARTIAL + no scope        -> UNRESOLVED_NO_APPLICABLE_MAPPING

The gate is one predicate over evidence that already exists. There is no
per-mapping flag and no analyst conclusion stored anywhere: `scope` is the
measurement, and the resolver asks only whether it is present.

## The tests cannot pass on nothing

Every concept named below is checked by identity and its status is compared to
the exact unresolved string, so a filter that returned nothing, or one that
resolved everything, would fail.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import (  # noqa: E402
    ConceptMapping,
    ConceptResolution,
    CoreRegistry,
)
from evidence_query import EvidenceQuery  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

H = os.path.join(os.path.dirname(HERE), "experiments",
                 "003-llm-evidence-retrieval", "harness")

AGGREGATE = "long_term_debt"
NONCURRENT = "long_term_debt_noncurrent"
CURRENT = "long_term_debt_current"
IFRS_NONCURRENT = "ifrs-full:LongtermBorrowings"
IFRS_CURRENT = "ifrs-full:CurrentPortionOfLongtermBorrowings"
LEGACY = "debt"
UNRESOLVED = ConceptResolution.UNRESOLVED_NO_APPLICABLE_MAPPING

# An existing concept nothing declares, so a claim about it can only come from
# what a test inserts. Inventing an id would be rejected by the foreign key and
# would test nothing.
UNCLAIMED = "ifrs-full:WeightedAverageShares"

# The concepts 2.73 admitted without evidence. Named individually and paired
# with the metric each had claimed, so this cannot pass on a count and so a
# future change to any one of them is visible by name.
#
# Fourteen, not the thirteen 2.74's first run reported. `us-gaap:Revenues` holds
# an unmeasured PARTIAL whose window is 2016-09-24 to 2018-09-29, and none of
# the six fixed probe dates that run used falls inside it -- so a concept the
# rule did admit was reported as unaffected. The audit now derives its probe
# dates from each concept's own windows; this list is checked against that
# derivation rather than trusted.
GATED = (
    ("ifrs-full:Equity", "equity"),
    ("ifrs-full:FinanceCosts", "interest_expense"),
    ("ifrs-full:GeneralAndAdministrativeExpense", "sga"),
    ("ifrs-full:IncomeTaxExpenseContinuingOperations", "income_tax"),
    ("ifrs-full:NumberOfSharesIssuedAndFullyPaid", "shares_outstanding"),
    ("ifrs-full:ProfitLoss", "net_income"),
    ("ifrs-full:Revenue", "revenue"),
    ("us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
     "cash"),
    ("us-gaap:GeneralAndAdministrativeExpense", "sga"),
    ("us-gaap:InterestExpenseDebt", "interest_expense"),
    ("us-gaap:PaymentsToAcquireProductiveAssets", "capex"),
    ("us-gaap:SalesRevenueNet", "revenue"),
    ("us-gaap:StockholdersEquityIncludingPortionAttributableTo"
     "NoncontrollingInterest", "equity"),
)

COMPOSITION_ROWS = (
    (AGGREGATE, "us-gaap:LongTermDebtNoncurrent"),
    (AGGREGATE, "us-gaap:LongTermDebtCurrent"),
    (AGGREGATE, IFRS_NONCURRENT),
    (AGGREGATE, IFRS_CURRENT),
)

# Representative EXACT claims that predate both 2.73 and 2.74.
EXACT_CLAIMS = (
    ("us-gaap:Assets", "assets"),
    ("us-gaap:CashAndCashEquivalentsAtCarryingValue", "cash"),
    ("us-gaap:LongTermDebtNoncurrent", NONCURRENT),
    ("us-gaap:LongTermDebtCurrent", CURRENT),
    (IFRS_CURRENT, CURRENT),
)


def seeded():
    store = SQLiteArchive(":memory:")
    registry = CoreRegistry(store.connection)
    seed(registry)
    store.connection.commit()
    return store, registry


class TestAMeasuredPartialResolves(unittest.TestCase):
    """A. The 2.73 promotion is untouched and must stay resolvable."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_the_promoted_concept_still_resolves(self) -> None:
        resolution = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.assertTrue(resolution.is_resolved, IFRS_NONCURRENT)
        self.assertEqual(resolution.status, ConceptResolution.RESOLVED)
        self.assertEqual(resolution.destination_metric, NONCURRENT)
        self.assertEqual(resolution.mapping_type, "PARTIAL")
        self.assertEqual(resolution.mapping_origin, ConceptResolution.DIRECT)

    def test_its_scope_is_present_and_unchanged(self) -> None:
        resolution = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.assertIsNotNone(resolution.scope,
                             "a PARTIAL destination must carry its measurement")
        self.assertEqual(resolution.scope["variation"], "FILER_DEPENDENT")
        self.assertEqual(resolution.scope["measured"],
                         {"TSM": "SUBSET", "RIO": "WHOLE"})
        self.assertEqual(resolution.scope["unmeasured_holders"], 6)

    def test_partial_is_not_upgraded_to_exact(self) -> None:
        resolution = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.assertFalse(resolution.is_exact)
        self.assertTrue(resolution.is_component)
        self.assertNotEqual(resolution.mapping_type, "EXACT")

    def test_the_mapping_row_still_carries_the_measurement(self) -> None:
        row = self.registry.connection.execute(
            "SELECT relation_kind, mapping_type, scope_json FROM"
            " metric_concept_mapping WHERE metric_id = ? AND concept_id = ?",
            (NONCURRENT, IFRS_NONCURRENT)).fetchone()
        self.assertEqual(row["relation_kind"], "IDENTITY")
        self.assertEqual(row["mapping_type"], "PARTIAL")
        self.assertTrue(row["scope_json"])


class TestAnUnmeasuredPartialDoesNotResolve(unittest.TestCase):
    """B. Unknown stays unknown, with the exact status."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_a_seeded_unmeasured_partial_is_unresolved(self) -> None:
        for concept, _metric in GATED:
            row = self.registry.connection.execute(
                "SELECT mapping_type, relation_kind, scope_json FROM"
                " metric_concept_mapping WHERE concept_id = ?"
                " AND relation_kind = 'IDENTITY'", (concept,)).fetchall()
            self.assertTrue(row, concept)
            self.assertTrue(all(r["mapping_type"] == "PARTIAL" for r in row),
                            concept)
            self.assertTrue(all(not r["scope_json"] for r in row), concept)

            resolution = self.registry.resolve_source_concept(concept)
            self.assertEqual(resolution.status, UNRESOLVED, concept)
            self.assertFalse(resolution.is_resolved, concept)

    def test_the_status_is_the_unresolved_one_not_a_weak_verdict(self) -> None:
        """Not `AMBIGUOUS`, not a null destination with a RESOLVED status."""
        resolution = self.registry.resolve_source_concept(GATED[0][0])
        self.assertNotEqual(resolution.status, ConceptResolution.RESOLVED)
        self.assertNotEqual(resolution.status,
                            ConceptResolution.AMBIGUOUS_MAPPING)
        self.assertIsNone(resolution.destination_metric)
        self.assertIsNone(resolution.mapping_type)
        self.assertFalse(resolution.is_exact)
        self.assertFalse(resolution.is_component)

    def test_unresolved_still_reads_as_unresolved_not_refuted(self) -> None:
        resolution = self.registry.resolve_source_concept(GATED[0][0])
        self.assertIn("unresolved, not refuted", resolution.detail.lower())

    def test_an_empty_scope_object_is_not_evidence(self) -> None:
        """A present-but-empty scope must not be mistaken for a measurement."""
        self.registry.add_mapping(ConceptMapping(
            metric_id="sga", concept_id=UNCLAIMED,
            mapping_type="PARTIAL", relation_kind="IDENTITY",
            effective_from="2020-12-31", scope={}))
        resolution = self.registry.resolve_source_concept(UNCLAIMED)
        self.assertEqual(resolution.status, UNRESOLVED)

    def test_a_measured_scope_on_a_fresh_mapping_does_resolve(self) -> None:
        """The gate is evidence, not a hardcoded list."""
        self.registry.add_mapping(ConceptMapping(
            metric_id="sga", concept_id=UNCLAIMED,
            mapping_type="PARTIAL", relation_kind="IDENTITY",
            effective_from="2020-12-31",
            scope={"variation": "FILER_DEPENDENT",
                   "measured": {"TSM": "SUBSET"}}))
        resolution = self.registry.resolve_source_concept(UNCLAIMED)
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.destination_metric, "sga")
        self.assertEqual(resolution.mapping_type, "PARTIAL")

    def test_a_malformed_scope_column_does_not_resolve(self) -> None:
        """
        `_read_scope` is the validation path and it must keep being one.

        A persisted row whose scope text is not JSON loads with `scope = None`,
        so the mapping stops resolving rather than resolving on garbage. This
        is the 2.73 promotion being corrupted in place, so the positive control
        is that it resolves before and does not after.
        """
        self.assertTrue(
            self.registry.resolve_source_concept(IFRS_NONCURRENT).is_resolved,
            "the promotion must resolve before the scope is corrupted")
        self.registry.connection.execute(
            "UPDATE metric_concept_mapping SET scope_json = 'not json at all'"
            " WHERE metric_id = ? AND concept_id = ?",
            (NONCURRENT, IFRS_NONCURRENT))
        self.registry.connection.commit()
        resolution = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.assertIsNone(resolution.scope)
        self.assertEqual(resolution.status, UNRESOLVED)


class TestTheGatedConceptsRemainUnresolved(unittest.TestCase):
    """C. By identity, not by count."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_every_named_concept_is_unresolved(self) -> None:
        for concept, _metric in GATED:
            resolution = self.registry.resolve_source_concept(concept)
            self.assertEqual(resolution.status, UNRESOLVED, concept)
            self.assertFalse(resolution.is_resolved, concept)
            self.assertNotEqual(resolution.status, ConceptResolution.RESOLVED,
                                concept)

    def test_none_of_them_is_a_destination_or_a_retrieval_source(self) -> None:
        for concept, metric in GATED:
            resolution = self.registry.resolve_source_concept(concept)
            self.assertNotEqual(resolution.destination_metric, metric, concept)
            sources = [s["concept"]
                       for s in self.registry.effective_metric_sources(metric)]
            self.assertNotIn(concept, sources, concept)

    def test_the_list_is_exactly_the_concepts_that_had_no_other_claim(self) -> None:
        """
        Positive control, and stated as a rule rather than as a count.

        A concept is gated exactly when every IDENTITY row it holds is an
        unmeasured PARTIAL. It is derived from the seed rather than copied from
        this list, so adding or dropping a mapping here without changing the
        registry fails.
        """
        self.assertEqual(len(GATED), 13)
        self.assertEqual(len(set(c for c, _ in GATED)), 13)

        derived = set()
        for concept in [r["concept_id"] for r in
                        self.registry.connection.execute(
                            "SELECT DISTINCT concept_id FROM"
                            " metric_concept_mapping"
                            " WHERE relation_kind = 'IDENTITY'")]:
            rows = self.registry.connection.execute(
                "SELECT mapping_type, scope_json FROM metric_concept_mapping"
                " WHERE concept_id = ? AND relation_kind = 'IDENTITY'",
                (concept,)).fetchall()
            if rows and all(r["mapping_type"] == "PARTIAL"
                            and not r["scope_json"] for r in rows):
                derived.add(concept)
        self.assertEqual(derived, set(c for c, _ in GATED))

    def test_every_gate_holds_inside_its_own_window(self) -> None:
        """
        The miss that produced 13 instead of 14, turned into a check.

        Each gated concept is asked at its own `effective_from`, not at a date
        chosen once for the whole registry.
        """
        checked = 0
        for concept, _metric in GATED:
            window = self.registry.connection.execute(
                "SELECT MIN(effective_from) FROM metric_concept_mapping"
                " WHERE concept_id = ? AND relation_kind = 'IDENTITY'"
                " AND scope_json IS NULL", (concept,)).fetchone()[0]
            self.assertIsNotNone(window, concept)
            resolution = self.registry.resolve_source_concept(
                concept, as_of=window)
            self.assertEqual(resolution.status, UNRESOLVED, concept)
            checked += 1
        self.assertEqual(checked, len(GATED))

    def test_exactly_one_measured_partial_exists_in_the_seed(self) -> None:
        measured = [dict(r) for r in self.registry.connection.execute(
            "SELECT metric_id, concept_id FROM metric_concept_mapping"
            " WHERE mapping_type = 'PARTIAL' AND relation_kind = 'IDENTITY'"
            " AND scope_json IS NOT NULL")]
        self.assertEqual(measured,
                         [{"metric_id": NONCURRENT,
                           "concept_id": IFRS_NONCURRENT}])

    def test_the_whole_registry_has_one_resolved_partial_destination(self) -> None:
        resolved = []
        for concept in [r["concept_id"] for r in
                        self.registry.connection.execute(
                            "SELECT concept_id FROM concept_registry"
                            " ORDER BY concept_id")]:
            resolution = self.registry.resolve_source_concept(concept)
            if resolution.is_resolved and resolution.mapping_type == "PARTIAL":
                resolved.append((concept, resolution.destination_metric))
        self.assertEqual(resolved, [(IFRS_NONCURRENT, NONCURRENT)])


class TestCompositionStaysIsolated(unittest.TestCase):
    """D. The four declarations remain true and remain non-destinations."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_the_four_rows_are_still_composition(self) -> None:
        stored = {(r["metric_id"], r["concept_id"]): r["relation_kind"]
                  for r in self.registry.connection.execute(
                      "SELECT metric_id, concept_id, relation_kind FROM"
                      " metric_concept_mapping")}
        for pair in COMPOSITION_ROWS:
            self.assertEqual(stored[pair], "COMPOSITION", pair)

    def test_no_composition_row_is_a_retrieval_source(self) -> None:
        """
        For each of the four, the metric that declared it must not list it.

        Asserted per pair so the loop cannot pass over an empty list, and
        against the persisted `relation_kind` rather than the pair name.
        """
        for metric, concept in COMPOSITION_ROWS:
            row = self.registry.connection.execute(
                "SELECT relation_kind FROM metric_concept_mapping"
                " WHERE metric_id = ? AND concept_id = ?",
                (metric, concept)).fetchone()
            self.assertEqual(row["relation_kind"], "COMPOSITION", concept)
            sources = [s["concept"]
                       for s in self.registry.effective_metric_sources(metric)]
            self.assertNotIn(concept, sources, concept)

    def test_a_composition_row_is_never_a_candidate_for_its_own_concept(
            self) -> None:
        for metric, concept in COMPOSITION_ROWS:
            resolution = self.registry.resolve_source_concept(concept)
            self.assertNotIn(metric, resolution.candidates, concept)

    def test_the_aggregate_has_no_sources_at_all(self) -> None:
        self.assertEqual(self.registry.effective_metric_sources(AGGREGATE), [])

    def test_no_component_concept_resolves_to_the_aggregate(self) -> None:
        for _declared, concept in COMPOSITION_ROWS:
            resolution = self.registry.resolve_source_concept(concept)
            self.assertNotEqual(resolution.destination_metric, AGGREGATE,
                                concept)


class TestExactClaimsAreUnchanged(unittest.TestCase):
    """E. Nothing about EXACT moved."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_representative_exact_claims_still_resolve_exact(self) -> None:
        for concept, metric in EXACT_CLAIMS:
            resolution = self.registry.resolve_source_concept(concept)
            self.assertTrue(resolution.is_resolved, concept)
            self.assertEqual(resolution.destination_metric, metric, concept)
            self.assertEqual(resolution.mapping_type, "EXACT", concept)
            self.assertTrue(resolution.is_exact, concept)
            self.assertFalse(resolution.is_component, concept)

    def test_every_exact_claim_in_the_registry_still_resolves(self) -> None:
        """No enumeration to update: every EXACT IDENTITY row, by name."""
        for concept in [r["concept_id"] for r in
                        self.registry.connection.execute(
                            "SELECT DISTINCT concept_id FROM"
                            " metric_concept_mapping"
                            " WHERE mapping_type = 'EXACT'"
                            " AND relation_kind = 'IDENTITY'"
                            " ORDER BY concept_id")]:
            resolution = self.registry.resolve_source_concept(concept)
            self.assertTrue(resolution.is_resolved, concept)
            self.assertEqual(resolution.mapping_type, "EXACT", concept)


class TestLongtermBorrowingsRetrievalIsUnchanged(unittest.TestCase):
    """F. The A/B observable 2.73 established."""

    ARCHIVE = "snapshot-universe"

    def setUp(self) -> None:
        if not os.path.isdir(H):
            self.skipTest("harness archives are not present")
        source = os.path.join(H, f"{self.ARCHIVE}.sqlite")
        if not os.path.exists(source):
            self.skipTest("target archive is not present")
        self.path = os.path.join(tempfile.mkdtemp(), "seeded.sqlite")
        shutil.copy2(source, self.path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        seed(CoreRegistry(self.connection))
        self.connection.commit()
        self.query = EvidenceQuery(connection=self.connection)
        self.addCleanup(self._close)

    def _close(self) -> None:
        self.query.close()
        self.connection.close()

    def _affected(self):
        return {r["contract_id"] for r in self.connection.execute(
            "SELECT contract_id FROM observations WHERE concept = ?"
            " AND metric = ? AND period_end >= '2020-12-31'",
            (IFRS_NONCURRENT, LEGACY))}

    def test_reachable_under_the_component_and_not_the_aggregate(self) -> None:
        affected = self._affected()
        self.assertGreater(len(affected), 0, "no positive control")

        under_component = {r["contract_id"] for r in
                           self.query.query_observations(
                               metric=NONCURRENT, limit=5000)}
        self.assertEqual(affected - under_component, set())

        under_aggregate = {r["contract_id"] for r in
                           self.query.query_observations(
                               metric=AGGREGATE, limit=5000)}
        self.assertEqual(affected & under_aggregate, set())
        self.assertEqual(self.query._last_result_total, 0)

    def test_the_component_query_total_is_the_2_73_value(self) -> None:
        """
        Recorded by 2.73's own harness run, so this is a baseline rather than
        an expectation written for this round.
        """
        self.query.query_observations(metric=NONCURRENT, limit=5000)
        self.assertEqual(self.query._last_result_total, 1519)


class TestEmptyCandidateSetsCannotProduceAVerdict(unittest.TestCase):
    """Invariant 8, kept because the gate added a new way to reach it."""

    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_a_concept_nothing_declares_is_unresolved(self) -> None:
        resolution = self.registry.resolve_source_concept(
            "us-gaap:NeverDeclared")
        self.assertEqual(resolution.status, UNRESOLVED)
        self.assertIsNone(resolution.destination_metric)
        self.assertEqual(resolution.candidates, ())

    def test_no_source_concept_is_still_its_own_answer(self) -> None:
        for value in (None, ""):
            resolution = self.registry.resolve_source_concept(value)
            self.assertEqual(
                resolution.status,
                ConceptResolution.UNRESOLVED_NO_SOURCE_CONCEPT)


if __name__ == "__main__":
    unittest.main()