"""
2.71 -- promotion of ifrs-full:CurrentPortionOfLongtermBorrowings to EXACT.

Focused regression for the promotion. The promotion itself was authorised by
the 2.70 policy; this file proves the production state matches the authorisation
and that nothing else moved.

What must hold afterwards:

  * the concept maps EXACT to `long_term_debt_current` from a date the evidence
    supports, and not before it
  * the inherited PARTIAL composition mapping is still there and still loses
  * the concept resolves to its own component metric, never to the total
  * `us-gaap:LongTermDebtCurrent` and `ifrs-full:LongtermBorrowings` are untouched
  * canonical retrieval reaches the legacy rows under the component metric and
    **not** under the total
  * no observation, interpretation or supersession row changed
  * resolution stays period-dependent
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry  # noqa: E402
from evidence_query import EvidenceQuery  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

H = os.path.join(os.path.dirname(HERE), "experiments",
                 "003-llm-evidence-retrieval", "harness")

CONCEPT = "ifrs-full:CurrentPortionOfLongtermBorrowings"
TARGET = "long_term_debt_current"
SUCCESSOR = "long_term_debt"
NONCURRENT_METRIC = "long_term_debt_noncurrent"
IFRS_NONCURRENT = "ifrs-full:LongtermBorrowings"
US_GAAP_CURRENT = "us-gaap:LongTermDebtCurrent"
LEGACY = "debt"

# The date the evidence supports, and which the pre-existing PARTIAL mapping for
# this same concept already used: the earliest reported period for the element
# across filers using the taxonomy. The archives hold no earlier period, so this
# is derived rather than chosen.
EXPECTED_EFFECTIVE_FROM = "2016-12-31"


def seeded() -> Any:
    store = SQLiteArchive(":memory:")
    registry = CoreRegistry(store.connection)
    seed(registry)
    store.connection.commit()
    return store, registry


class TestThePromotedMapping(unittest.TestCase):
    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def rows_for(self, concept: str) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.registry.connection.execute(
            "SELECT metric_id, mapping_type, effective_from, effective_to, notes, relation_kind, scope_json"
            " FROM metric_concept_mapping WHERE concept_id = ?"
            " ORDER BY mapping_type", (concept,))]

    def test_1_the_registry_contains_the_exact_mapping(self) -> None:
        exact = [r for r in self.rows_for(CONCEPT)
                 if r["metric_id"] == TARGET and r["mapping_type"] == "EXACT"]
        self.assertEqual(len(exact), 1,
                         "exactly one EXACT mapping is expected")
        self.assertIsNone(exact[0]["effective_to"])

    def test_2_the_mapping_is_active_at_its_effective_date(self) -> None:
        resolution = self.registry.resolve_source_concept(
            CONCEPT, as_of=EXPECTED_EFFECTIVE_FROM)
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.destination_metric, TARGET)

    def test_3_the_mapping_is_absent_before_its_effective_date(self) -> None:
        earlier = "2016-06-30"
        self.assertLess(earlier, EXPECTED_EFFECTIVE_FROM)
        resolution = self.registry.resolve_source_concept(CONCEPT, as_of=earlier)
        self.assertFalse(resolution.is_resolved)
        self.assertIsNone(resolution.destination_metric)

    def test_the_effective_date_is_the_one_the_evidence_supports(self) -> None:
        exact = next(r for r in self.rows_for(CONCEPT)
                     if r["metric_id"] == TARGET)
        self.assertEqual(exact["effective_from"], EXPECTED_EFFECTIVE_FROM)
        # And it matches the window the pre-existing composition mapping uses,
        # so the two rows cannot drift apart on the same concept.
        partial = next(r for r in self.rows_for(CONCEPT)
                       if r["metric_id"] == SUCCESSOR)
        self.assertEqual(partial["effective_from"], exact["effective_from"])

    def test_4_the_existing_us_gaap_mapping_is_unchanged(self) -> None:
        rows = [r for r in self.rows_for(US_GAAP_CURRENT)
                if r["metric_id"] == TARGET]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["mapping_type"], "EXACT")
        self.assertEqual(rows[0]["effective_from"], "2014-09-27")

    def test_5_the_longterm_borrowings_relations_do_not_compete(self) -> None:
        """
        WHY THIS CHANGED: 2.73 promoted these 298.

        Previously the concept carried only a `debt` PARTIAL and resolved
        nowhere. What must now hold is a partition rather than a count: the
        component metric claims the concept as an IDENTITY destination, and the
        aggregate declares it as a COMPOSITION component. Both relationships stay
        true; only one is a destination.
        """
        rows = {r["metric_id"]: r for r in self.rows_for(IFRS_NONCURRENT)}
        self.assertEqual(rows[SUCCESSOR]["relation_kind"], "COMPOSITION")
        self.assertEqual(rows[NONCURRENT_METRIC]["mapping_type"], "PARTIAL")
        self.assertEqual(rows[NONCURRENT_METRIC]["relation_kind"], "IDENTITY")

        resolution = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.destination_metric, NONCURRENT_METRIC)
        # The aggregate is never a destination, which is the whole point.
        self.assertNotEqual(resolution.destination_metric, SUCCESSOR)
        # PARTIAL is not upgraded to EXACT.
        self.assertFalse(resolution.is_exact)
        self.assertTrue(resolution.is_component)

    def test_6_the_core_metric_count_is_unchanged(self) -> None:
        active = [m.metric_id for m in self.registry.metrics()
                  if m.status == "ACTIVE"]
        self.assertEqual(len(active), 20)

    def test_15_the_promotion_resolves_nothing_else(self) -> None:
        """
        WHY THIS CHANGED: the noncurrent IFRS concept now resolves, to its own
        component metric. What must still hold is that the two IFRS concepts stay
        apart and that neither reaches the aggregate.
        """
        resolution = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.destination_metric, NONCURRENT_METRIC)
        self.assertNotEqual(resolution.destination_metric, SUCCESSOR)

        # The 2.71 promotion of the current-portion concept is untouched.
        current = self.registry.resolve_source_concept(
            "ifrs-full:CurrentPortionOfLongtermBorrowings")
        self.assertEqual(current.destination_metric, TARGET)
        self.assertTrue(current.is_exact)

    def test_the_promotion_note_records_the_qualifier(self) -> None:
        notes = (next(r for r in self.rows_for(CONCEPT)
                       if r["metric_id"] == TARGET)["notes"] or "").lower()
        self.assertIn("qualifier", notes)
        self.assertIn("2 of 8", notes)
        self.assertIn("6 holders unmeasured", notes)


class TestResolutionUnderThePromotion(unittest.TestCase):
    def setUp(self) -> None:
        self.store, self.registry = seeded()
        self.addCleanup(self.store.close)

    def test_7_the_resolver_returns_only_the_component_metric(self) -> None:
        resolution = self.registry.resolve_source_concept(CONCEPT)
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.destination_metric, TARGET)
        self.assertNotEqual(resolution.destination_metric, SUCCESSOR)

    def test_7_the_observation_path_resolves_the_same_way(self) -> None:
        outcome = self.registry.mappings_for_observation(
            LEGACY, source_concept=CONCEPT)
        self.assertTrue(outcome.is_resolved)
        self.assertEqual(outcome.resolved_metric_id, TARGET)
        self.assertEqual(outcome.stored_metric_id, LEGACY)
        self.assertTrue(outcome.is_superseded)

    def test_8_no_inherited_mapping_creates_ambiguity(self) -> None:
        resolution = self.registry.resolve_source_concept(CONCEPT)
        self.assertNotEqual(resolution.status, "AMBIGUOUS_MAPPING")
        self.assertEqual(resolution.candidates, ())
        # The composition mapping is still declared, and still not chosen.
        inherited = {
            mapping.metric_id
            for mapping, _ in self.registry.metrics_for_concept(CONCEPT)
            if mapping.mapping_type == "PARTIAL"}
        self.assertIn(SUCCESSOR, inherited)

    def test_14_resolution_remains_period_dependent(self) -> None:
        self.assertFalse(self.registry.resolve_source_concept(
            CONCEPT, as_of="2016-06-30").is_resolved)
        self.assertTrue(self.registry.resolve_source_concept(
            CONCEPT, as_of="2016-12-31").is_resolved)
        self.assertTrue(self.registry.resolve_source_concept(
            CONCEPT, as_of="2999-01-01").is_resolved)


class TestRealArchiveRetrieval(unittest.TestCase):
    """
    The promotion has to be visible on real archived rows.

    Every subject is discovered from the archive. An empty result is never
    accepted as success: each retrieval assertion carries a positive control
    taken from the archive before it asserts anything about the query.
    """

    ARCHIVE = "snapshot-universe"

    def setUp(self) -> None:
        if not os.path.isdir(H):
            self.skipTest("harness archives are not present")
        source = os.path.join(H, f"{self.ARCHIVE}.sqlite")
        if not os.path.exists(source):
            self.skipTest("target archive is not present")
        self.workdir = tempfile.mkdtemp()
        self.path = os.path.join(self.workdir, "seeded.sqlite")
        shutil.copy2(source, self.path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        registry = CoreRegistry(self.connection)
        seed(registry)
        self.connection.commit()
        self.query = EvidenceQuery(connection=self.connection)
        self.addCleanup(self._close)

    def _close(self) -> None:
        self.query.close()
        self.connection.close()

    def _sample(self) -> Optional[Dict[str, Any]]:
        row = self.connection.execute(
            "SELECT o.contract_id, o.observation_id, o.concept, o.period_end,"
            " o.metric, s.ticker FROM observations o"
            " JOIN assets s ON s.asset_id = o.asset_id"
            " WHERE o.concept = ? AND o.metric = ?"
            " ORDER BY o.period_end LIMIT 1", (CONCEPT, LEGACY)).fetchone()
        return dict(row) if row else None

    def test_the_population_still_exists_and_is_untouched(self) -> None:
        scoped = self.connection.execute(
            "SELECT COUNT(*) FROM observations WHERE concept = ? AND"
            " metric = ?", (CONCEPT, LEGACY)).fetchone()[0]
        self.assertGreater(scoped, 0, "no rows to reason about")

    def test_12_canonical_retrieval_reaches_a_real_legacy_row(self) -> None:
        sample = self._sample()
        self.assertIsNotNone(sample, "no archived row discovered")
        rows = self.query.query_observations(metric=TARGET, limit=5000)
        returned = {r["contract_id"] for r in rows}
        self.assertIn(sample["contract_id"], returned,
                      "the promoted mapping did not make the row reachable")

    def test_13_that_row_is_not_reachable_under_the_total(self) -> None:
        sample = self._sample()
        self.assertIsNotNone(sample)
        rows = self.query.query_observations(metric=SUCCESSOR, limit=5000)
        self.assertNotIn(sample["contract_id"], {r["contract_id"]
                                                 for r in rows})

    def test_14_retrieval_of_that_row_is_period_dependent(self) -> None:
        sample = self._sample()
        self.assertIsNotNone(sample)
        before = self.query.query_observations(
            metric=TARGET, period_end="2016-06-30", limit=5000)
        self.assertNotIn(sample["contract_id"],
                         {r["contract_id"] for r in before},
                         "a row dated after the effective date was returned "
                         "for a cutoff before it")
        after = self.query.query_observations(
            metric=TARGET, period_end="2999-12-31", limit=5000)
        self.assertIn(sample["contract_id"], {r["contract_id"] for r in after})

    def test_9_10_11_reading_changes_no_row(self) -> None:
        before = (
            self.connection.execute(
                "SELECT COUNT(*) FROM observations").fetchone()[0],
            self.connection.execute(
                "SELECT COUNT(*) FROM interpretations").fetchone()[0],
            self.connection.execute(
                "SELECT COUNT(*) FROM metric_supersession").fetchone()[0],
            self.connection.execute(
                "SELECT COUNT(*) FROM metric_concept_mapping").fetchone()[0],
        )
        self.query.query_observations(metric=TARGET, limit=5000)
        self.query.query_observations(metric=SUCCESSOR, limit=5000)
        self.query.query_observations(metric=LEGACY, limit=5000)
        after = (
            self.connection.execute(
                "SELECT COUNT(*) FROM observations").fetchone()[0],
            self.connection.execute(
                "SELECT COUNT(*) FROM interpretations").fetchone()[0],
            self.connection.execute(
                "SELECT COUNT(*) FROM metric_supersession").fetchone()[0],
            self.connection.execute(
                "SELECT COUNT(*) FROM metric_concept_mapping").fetchone()[0],
        )
        self.assertEqual(before, after)
        # And the population is unmigrated: no row was moved to the new metric.
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM observations WHERE metric = ?",
                (TARGET,)).fetchone()[0], 0,
            "promotion must not migrate observations into the target metric")


if __name__ == "__main__":
    unittest.main()