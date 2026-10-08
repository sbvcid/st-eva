"""
Source-conditional resolution and effective metric retrieval, 2.67.

## What changed

2.66 measured three defects on real archives:

    * `us-gaap:LongTermDebtCurrent` carried three claimants -- its own
      component metric, the superseded `debt`, and the successor
      `long_term_debt` -- so `resolve` answered AMBIGUOUS and all 3,378 legacy
      rows collapsed onto the total
    * an inherited PARTIAL proposition was treated as an affirmative
      destination, exposing all 417 unauthorised IFRS rows as total long-term
      debt
    * a query for `long_term_debt_current` returned 0 of the 1,442 rows that
      belong to it, because every metric query filtered the stored metric

## The rule, and what it is not

An identity claim is an EXACT mapping declared by a metric that is itself
active. PARTIAL records a component relationship, and an unauthorised one is a
characterisation rather than a decision. Nothing here ranks metrics by name,
value, period or insertion order.

Measured while writing it: "declared by an active metric" is *not* sufficient on
its own, because the successor re-declares its PARTIAL components in its own
name, making those rows structurally indistinguishable from a direct declaration
while meaning something different. Mapping type carries the distinction and the
registry already uses it.

## The tests cannot pass on nothing

Every real-archive test discovers its own subject and asserts a positive count. A
filter that returned nothing would fail, not pass.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import ConceptResolution, CoreRegistry  # noqa: E402
from evidence_query import EvidenceQuery  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402
import corpus_gate  # noqa: E402

H = os.path.join(os.path.dirname(HERE), "experiments",
                 "003-llm-evidence-retrieval", "harness")

LEGACY = "debt"
SUCCESSOR = "long_term_debt"
CURRENT_METRIC = "long_term_debt_current"
NONCURRENT_METRIC = "long_term_debt_noncurrent"
US_GAAP_CURRENT = "us-gaap:LongTermDebtCurrent"
US_GAAP_NONCURRENT = "us-gaap:LongTermDebtNoncurrent"
IFRS_NONCURRENT = "ifrs-full:LongtermBorrowings"
IFRS_CURRENT = "ifrs-full:CurrentPortionOfLongtermBorrowings"


def fresh():
    store = SQLiteArchive(":memory:")
    registry = CoreRegistry(store.connection)
    seed(registry)
    store.connection.commit()
    return store, registry


class TestResolutionPrecedence(unittest.TestCase):
    """Requirements 1-7."""

    def setUp(self) -> None:
        self.store, self.registry = fresh()
        self.addCleanup(self.store.close)

    def test_1_the_current_concept_resolves_to_the_current_component(self) -> None:
        resolution = self.registry.resolve_source_concept(US_GAAP_CURRENT)
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.destination_metric, CURRENT_METRIC)
        self.assertEqual(resolution.mapping_origin, ConceptResolution.DIRECT)
        self.assertEqual(resolution.mapping_type, "EXACT")

    def test_2_the_non_current_concept_resolves_to_its_component(self) -> None:
        resolution = self.registry.resolve_source_concept(US_GAAP_NONCURRENT)
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.destination_metric, NONCURRENT_METRIC)

    def test_3_the_inherited_mapping_does_not_compete(self) -> None:
        """
        The successor declares the US-GAAP concepts too, as PARTIAL components.

        If a PARTIAL component statement could compete, the concept would again
        carry several claimants and the split would collapse onto the total.
        """
        successor_claims = {
            mapping.concept_id
            for mapping in self.registry.mappings_for_metric(SUCCESSOR)}
        self.assertIn(US_GAAP_CURRENT, successor_claims)
        resolution = self.registry.resolve_source_concept(US_GAAP_CURRENT)
        self.assertEqual(resolution.mapping_type, "EXACT")
        self.assertNotEqual(resolution.destination_metric, SUCCESSOR)

    def test_4_more_than_one_direct_claim_stays_ambiguous(self) -> None:
        """
        Two EXACT claims on one concept is a registry question, not a guess.

        The concept is chosen from the registry so it
        has no other exact claim, which leaves the insertion below as the only way
        to reach ambiguity.
        """
        contested = self.registry.connection.execute(
            "SELECT c.concept_id FROM concept_registry c"
            " WHERE NOT EXISTS (SELECT 1 FROM metric_concept_mapping m"
            " WHERE m.concept_id = c.concept_id AND m.mapping_type = 'EXACT')"
            " LIMIT 1").fetchone()["concept_id"]
        for metric in (CURRENT_METRIC, NONCURRENT_METRIC):
            self.registry.connection.execute(
                "INSERT INTO metric_concept_mapping (metric_id, concept_id,"
                " mapping_type, effective_from, effective_to, notes)"
                " VALUES (?, ?, 'EXACT', NULL, NULL, NULL)",
                (metric, contested))
        resolution = self.registry.resolve_source_concept(contested)
        self.assertEqual(resolution.status,
                         ConceptResolution.AMBIGUOUS_MAPPING)
        self.assertFalse(resolution.is_resolved)
        self.assertIn(CURRENT_METRIC, resolution.candidates)
        self.assertIn(NONCURRENT_METRIC, resolution.candidates)

    def test_5_a_concept_with_no_authorised_claim_is_unresolved(self) -> None:
        resolution = self.registry.resolve_source_concept(
            "us-gaap:ShortTermBorrowings")
        self.assertFalse(resolution.is_resolved)
        self.assertEqual(resolution.status,
                         ConceptResolution.UNRESOLVED_NO_APPLICABLE_MAPPING)

    def test_6_no_source_concept_is_its_own_status(self) -> None:
        for value in (None, ""):
            resolution = self.registry.resolve_source_concept(value)
            self.assertEqual(resolution.status,
                             ConceptResolution.UNRESOLVED_NO_SOURCE_CONCEPT)

    def test_7_an_inherited_partial_does_not_resolve(self) -> None:
        """
        The IFRS debt concepts.

        Each is declared PARTIAL on the successor, so under 2.66 they resolved to
        total long-term debt. An unauthorised PARTIAL proposition is a
        characterisation, not a decision.

        Revised in 2.71 for the current-portion concept only, which now carries an
        EXACT claim of its own against `long_term_debt_current`. The noncurrent
        concept is untouched and still unresolved. Both halves matter: the rule is
        unchanged, and what changed is one concept's evidence.

        Revised in 2.73 for the noncurrent concept, and this is the rule under
        test rather than an exception to it. It now carries a measured IDENTITY
        PARTIAL claim of its own against `long_term_debt_noncurrent`. What must
        still hold is everything 2.66 established: the successor's PARTIAL
        declaration does not become a destination, and a PARTIAL identity claim
        is never upgraded into a whole.
        """
        # The inherited declaration is still on the successor, and still did not
        # win. This is the 2.66 defect, unchanged.
        inherited = {
            mapping.metric_id
            for mapping, _ in self.registry.metrics_for_concept(IFRS_NONCURRENT)
            if mapping.mapping_type == "PARTIAL"
        }
        self.assertIn(SUCCESSOR, inherited, "2.73 must not remove the declaration")

        promoted = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.assertTrue(promoted.is_resolved, IFRS_NONCURRENT)
        self.assertEqual(promoted.destination_metric, NONCURRENT_METRIC)
        self.assertEqual(promoted.mapping_type, "PARTIAL")
        self.assertEqual(promoted.mapping_origin, ConceptResolution.DIRECT)
        # Never the aggregate that declares it, never a whole.
        self.assertNotEqual(promoted.destination_metric, SUCCESSOR)
        self.assertFalse(promoted.is_exact)
        self.assertTrue(promoted.is_component)
        # And the measured scope rides with it, so PARTIAL is not taken on
        # trust.
        self.assertEqual(promoted.scope["unmeasured_holders"], 6)

        current = self.registry.resolve_source_concept(IFRS_CURRENT)
        self.assertTrue(current.is_resolved, IFRS_CURRENT)
        self.assertEqual(current.destination_metric, CURRENT_METRIC)
        self.assertEqual(current.mapping_type, "EXACT")
        # The rule under test for the sibling: the inherited PARTIAL composition
        # mapping is present and still does not compete with an exact identity
        # claim.
        inherited = {
            mapping.metric_id
            for mapping, _ in self.registry.metrics_for_concept(IFRS_CURRENT)
            if mapping.mapping_type == "PARTIAL"}
        self.assertIn(SUCCESSOR, inherited)
        self.assertNotEqual(current.destination_metric, SUCCESSOR)

    def test_a_concept_with_no_identity_claim_is_still_unresolved(self) -> None:
        """
        The anti-vacuous half of the rule 2.73 did not move.

        Promoting one concept says nothing about a concept nothing claims, and
        the answer there is still "unresolved, not refuted" -- the distinction
        2.66 exists to preserve.
        """
        bare = self.registry.resolve_source_concept(
            "us-gaap:ShortTermBorrowings")
        self.assertFalse(bare.is_resolved)
        self.assertEqual(bare.destination_metric, None)
        self.assertIn("unresolved, not refuted", bare.detail.lower())

    def test_an_unauthorised_proposition_is_not_promoted_by_this_change(self) -> None:
        before = self.registry.connection.execute(
            "SELECT COUNT(*) FROM metric_concept_mapping").fetchone()[0]
        self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.registry.resolve_source_concept(US_GAAP_CURRENT)
        after = self.registry.connection.execute(
            "SELECT COUNT(*) FROM metric_concept_mapping").fetchone()[0]
        self.assertEqual(before, after)


class TestResolutionInvariants(unittest.TestCase):
    """Requirements 8-10: period, and independence from ordering."""

    def setUp(self) -> None:
        self.store, self.registry = fresh()
        self.addCleanup(self.store.close)
        window = self.registry.connection.execute(
            "SELECT effective_from, effective_to FROM metric_concept_mapping"
            " WHERE concept_id = ?", (US_GAAP_CURRENT,)).fetchone()
        self.effective_from = window["effective_from"]
        self.effective_to = window["effective_to"]

    def test_8_the_effective_window_is_respected(self) -> None:
        """The destination may vary by date, and must not be cached."""
        if not self.effective_from:
            self.skipTest("mapping carries no effective_from")
        before = self.registry.resolve_source_concept(
            US_GAAP_CURRENT, as_of="1900-01-01")
        at = self.registry.resolve_source_concept(
            US_GAAP_CURRENT, as_of=self.effective_from)
        after = self.registry.resolve_source_concept(
            US_GAAP_CURRENT, as_of="2999-01-01")
        self.assertFalse(before.is_resolved,
                         "a mapping applied before its window opened")
        self.assertTrue(at.is_resolved, "the boundary itself must apply")
        self.assertTrue(after.is_resolved)
        self.assertEqual(at.destination_metric, CURRENT_METRIC)

    def test_a_closed_window_excludes_its_end(self) -> None:
        if not self.effective_to:
            self.skipTest("mapping is open-ended")
        self.registry.connection.execute(
            "UPDATE metric_concept_mapping SET effective_to = '2020-12-31'"
            " WHERE concept_id = ?", (US_GAAP_NONCURRENT,))
        inside = self.registry.resolve_source_concept(
            US_GAAP_NONCURRENT, as_of="2020-06-30")
        outside = self.registry.resolve_source_concept(
            US_GAAP_NONCURRENT, as_of="2021-06-30")
        self.assertTrue(inside.is_resolved)
        self.assertFalse(outside.is_resolved)

    def test_9_resolution_does_not_depend_on_insertion_order(self) -> None:
        first = self.registry.resolve_source_concept(US_GAAP_CURRENT)
        # Reverse the physical row order and re-resolve.
        self.registry.connection.execute(
            "CREATE TABLE _reordered AS SELECT * FROM metric_concept_mapping"
            " ORDER BY rowid DESC")
        self.registry.connection.execute(
            "DELETE FROM metric_concept_mapping")
        self.registry.connection.execute(
            "INSERT INTO metric_concept_mapping SELECT * FROM _reordered")
        self.registry.connection.execute("DROP TABLE _reordered")
        second = self.registry.resolve_source_concept(US_GAAP_CURRENT)
        self.assertEqual(first.destination_metric, second.destination_metric)
        self.assertEqual(first.status, second.status)

    def test_10_resolution_does_not_depend_on_concept_name_order(self) -> None:
        """
        A second exact claim under a metric that sorts after the first must
        still leave the result ambiguous rather than silently picking one.
        """
        other = self.registry.connection.execute(
            "SELECT metric_id FROM metric_registry WHERE metric_id > ?"
            " AND metric_id NOT IN (?, ?) ORDER BY metric_id DESC LIMIT 1",
            (NONCURRENT_METRIC, CURRENT_METRIC, NONCURRENT_METRIC)
        ).fetchone()["metric_id"]
        self.registry.connection.execute(
            "INSERT INTO metric_concept_mapping (metric_id, concept_id,"
            " mapping_type, effective_from, effective_to, notes)"
            " VALUES (?, ?, 'EXACT', NULL, NULL, NULL)",
            (other, US_GAAP_NONCURRENT))
        resolution = self.registry.resolve_source_concept(US_GAAP_NONCURRENT)
        self.assertEqual(resolution.status,
                         ConceptResolution.AMBIGUOUS_MAPPING)
        self.assertIn(other, resolution.candidates)


class TestEffectiveMetricRetrievalOnRealArchives(unittest.TestCase):
    """Requirements 11-19, against real archived rows."""

    def setUp(self) -> None:
        corpus_gate.require(self, "snapshot-universe")
        self.source = os.path.join(H, "snapshot-universe.sqlite")
        if not os.path.exists(self.source):
            self.skipTest("target archive is not present")
        workdir = tempfile.mkdtemp()
        self.path = os.path.join(workdir, "seeded.sqlite")
        shutil.copy2(self.source, self.path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        seed(CoreRegistry(self.connection))
        self.connection.commit()
        self.query = EvidenceQuery(connection=self.connection)
        self.addCleanup(self._close)

    def _close(self) -> None:
        self.query.close()
        self.connection.close()

    def _count(self, metric):
        self.query.query_observations(metric=metric, limit=5)
        return self.query._last_result_total

    def test_11_the_current_component_query_retrieves_legacy_rows(self) -> None:
        """
        Both concepts that resolve to this component metric must be retrieved.

        Since 2.71 that is the US-GAAP current portion and the IFRS current
        portion, so the expected count has to cover both -- a query that
        returned only the US-GAAP rows would match the old expectation and miss
        the promoted mapping entirely.
        """
        expected = self.connection.execute(
            "SELECT COUNT(*) FROM observations WHERE metric = ? AND concept IN"
            " (?, ?) AND period_end >= (SELECT MIN(effective_from) FROM"
            " metric_concept_mapping WHERE metric_id = ?)",
            (LEGACY, US_GAAP_CURRENT, IFRS_CURRENT, CURRENT_METRIC)
        ).fetchone()[0]
        self.assertGreater(expected, 0, "no positive control in the archive")
        rows = self.query.query_observations(metric=CURRENT_METRIC, limit=5000)
        self.assertEqual(len(rows), expected)
        concepts = {(r.get("source") or {}).get("concept") for r in rows}
        self.assertIn(US_GAAP_CURRENT, concepts)
        self.assertIn(IFRS_CURRENT, concepts)

    def test_12_the_non_current_component_query_retrieves_legacy_rows(self) -> None:
        """
        WHY THIS CHANGED: 2.73 gave this component a second declaring concept.

        `long_term_debt_noncurrent` is now claimed by the US-GAAP non-current
        portion *and* by `ifrs-full:LongtermBorrowings`, each inside its own
        persisted window. The expected population is therefore a partition over
        both concepts, not the old count plus a constant: a query that dropped
        the IFRS rows, or returned the pre-window ones, would have to pass a
        hardcoded number to get through.
        """
        expected = {}
        for concept in (US_GAAP_NONCURRENT, IFRS_NONCURRENT):
            window = self.connection.execute(
                "SELECT effective_from FROM metric_concept_mapping"
                " WHERE metric_id = ? AND concept_id = ?",
                (NONCURRENT_METRIC, concept)).fetchone()
            self.assertIsNotNone(
                window, f"{concept} declares nothing for this metric")
            expected[concept] = {
                r["contract_id"] for r in self.connection.execute(
                    "SELECT contract_id FROM observations WHERE metric = ?"
                    " AND concept = ? AND period_end >= ?",
                    (LEGACY, concept, window["effective_from"]))}
            self.assertGreater(len(expected[concept]), 0,
                               f"{concept}: no positive control in the archive")

        self.assertEqual(self._count(NONCURRENT_METRIC),
                         sum(len(v) for v in expected.values()))

        rows = self.query.query_observations(metric=NONCURRENT_METRIC,
                                             limit=5000)
        by_concept = {}
        for row in rows:
            by_concept.setdefault(
                (row.get("source") or {}).get("concept"), set()).add(
                    row["contract_id"])
        # Set equality, not a count: which rows arrived, per declaring concept.
        self.assertEqual(by_concept, expected)

    def test_13_the_total_query_does_not_retrieve_component_rows(self) -> None:
        """
        WHY THIS CHANGED: 2.73 added a fourth COMPOSITION row's twin claim.

        The aggregate still retrieves nothing at all. Under 2.73 it could not
        have retrieved the IFRS rows through their component metric either,
        because the concept resolves to the component and not to the aggregate.
        """
        self.assertEqual(self._count(SUCCESSOR), 0)
        rows = self.query.query_observations(metric=SUCCESSOR, limit=5000)
        self.assertEqual(rows, [])

    def test_14_ifrs_rows_appear_only_under_their_own_component(self) -> None:
        """
        Stronger than before the promotions, not weaker.

        2.45's failure was IFRS rows leaking into the total. What is asserted
        now is positive destination isolation for both IFRS concepts: each
        appears under its own component metric and **only** there -- in
        particular neither may reach the aggregate, and the two may not reach
        each other's metric.
        """
        for concept in (IFRS_NONCURRENT, IFRS_CURRENT):
            present = self.connection.execute(
                "SELECT COUNT(*) FROM observations WHERE concept = ?"
                " AND metric = ?", (concept, LEGACY)).fetchone()[0]
            self.assertGreater(present, 0, f"{concept}: no positive control")

        by_metric = {}
        for metric in (SUCCESSOR, NONCURRENT_METRIC, CURRENT_METRIC):
            rows = self.query.query_observations(metric=metric, limit=5000)
            by_metric[metric] = {(r.get("source") or {}).get("concept")
                                 for r in rows}

        self.assertIn(IFRS_NONCURRENT, by_metric[NONCURRENT_METRIC])
        self.assertIn(IFRS_CURRENT, by_metric[CURRENT_METRIC])
        # Each IFRS concept reaches its own component metric, and each is denied
        # the other two -- including, crucially, the aggregate, which is the
        # 2.45 failure.
        self.assertNotIn(IFRS_NONCURRENT, by_metric[SUCCESSOR])
        self.assertNotIn(IFRS_NONCURRENT, by_metric[CURRENT_METRIC])
        self.assertNotIn(IFRS_CURRENT, by_metric[SUCCESSOR])
        self.assertNotIn(IFRS_CURRENT, by_metric[NONCURRENT_METRIC])
        self.assertEqual(by_metric[SUCCESSOR], set())

    def test_15_ambiguous_rows_are_excluded(self) -> None:
        """
        WHY THIS CHANGED: the non-current component gained a PARTIAL source.

        The invariant is the exclusion of ambiguity, not the exclusion of
        PARTIAL. 2.73 widened who may feed a metric query; it did not widen what
        counts as a destination, so every source feeding one must still resolve
        uniquely, directly, to that metric and no other.
        """
        registry = CoreRegistry(self.connection)
        for metric in (CURRENT_METRIC, NONCURRENT_METRIC, SUCCESSOR):
            for source in self.registry_sources(metric):
                where = (metric, source["concept"])
                resolution = registry.resolve_source_concept(
                    source["concept"])
                self.assertTrue(resolution.is_resolved, where)
                self.assertEqual(resolution.destination_metric, metric, where)
                self.assertEqual(resolution.mapping_origin,
                                 ConceptResolution.DIRECT, where)
                self.assertEqual(resolution.status,
                                 ConceptResolution.RESOLVED, where)
                self.assertEqual(resolution.candidates, (), where)
                self.assertEqual(source["mapping_type"],
                                 resolution.mapping_type, where)

        # The aggregate has no destination source at all: all four of its rows
        # are COMPOSITION declarations. Asserted explicitly because a loop over
        # an empty list would pass vacuously.
        self.assertEqual(self.registry_sources(SUCCESSOR), [])

        # EXACT stays EXACT, and the one measured PARTIAL is a component rather
        # than a quieter whole.
        self.assertEqual(
            {(s["concept"], s["mapping_type"])
             for s in self.registry_sources(CURRENT_METRIC)},
            {(US_GAAP_CURRENT, "EXACT"), (IFRS_CURRENT, "EXACT")})
        self.assertEqual(
            {(s["concept"], s["mapping_type"])
             for s in self.registry_sources(NONCURRENT_METRIC)},
            {(US_GAAP_NONCURRENT, "EXACT"), (IFRS_NONCURRENT, "PARTIAL")})

    def registry_sources(self, metric):
        return CoreRegistry(self.connection).effective_metric_sources(metric)

    def test_16_the_stored_metric_query_is_unchanged(self) -> None:
        """An explicit historical query means the stored identity."""
        stored = self.connection.execute(
            "SELECT COUNT(*) FROM observations WHERE metric = ?",
            (LEGACY,)).fetchone()[0]
        self.assertGreater(stored, 0)
        self.assertEqual(self._count(LEGACY), stored)

    def test_17_metric_history_uses_the_same_logic(self) -> None:
        """No second retrieval algorithm."""
        asset = self.connection.execute(
            "SELECT a.ticker FROM observations o JOIN assets a"
            " ON a.asset_id = o.asset_id WHERE o.concept = ? AND o.metric = ?"
            " LIMIT 1", (US_GAAP_CURRENT, LEGACY)).fetchone()
        self.assertIsNotNone(asset, "no positive control")
        history = self.query.get_metric_history(asset["ticker"], CURRENT_METRIC)
        self.assertGreater(history.get("point_count") or 0, 0,
                           "metric history returned nothing for a metric that"
                           " has observations")
        # The legacy series is still independently queryable.
        legacy = self.query.get_metric_history(asset["ticker"], LEGACY)
        self.assertGreater(legacy.get("point_count") or 0, 0)

    def test_18_no_source_fact_appears_twice(self) -> None:
        for metric in (CURRENT_METRIC, NONCURRENT_METRIC, LEGACY):
            rows = self.query.query_observations(metric=metric, limit=5000)
            ids = [row["contract_id"] for row in rows]
            self.assertEqual(len(ids), len(set(ids)), metric)

    def test_19_no_observation_changed(self) -> None:
        before = self.connection.execute(
            "SELECT COUNT(*), SUM(CASE WHEN unit = 'ratio' THEN 1 ELSE 0 END)"
            " FROM observations WHERE metric = ?", (LEGACY,)).fetchone()
        self._count(CURRENT_METRIC)
        after = self.connection.execute(
            "SELECT COUNT(*), SUM(CASE WHEN unit = 'ratio' THEN 1 ELSE 0 END)"
            " FROM observations WHERE metric = ?", (LEGACY,)).fetchone()
        self.assertEqual(tuple(before), tuple(after))

    def test_a_canonical_row_really_is_the_discovered_component_row(self) -> None:
        """
        Positivity of the answer, not only of the count.

        A count can match while the rows returned are something else entirely,
        and the row is chosen inside the mapping window so the retrieval is
        expected to reach it.
        """
        window = self.connection.execute(
            "SELECT MIN(effective_from) FROM metric_concept_mapping"
            " WHERE concept_id = ?", (US_GAAP_CURRENT,)).fetchone()[0]
        expected = self.connection.execute(
            "SELECT o.contract_id FROM observations o WHERE o.metric = ?"
            " AND o.concept = ? AND o.period_end >= ? LIMIT 1",
            (LEGACY, US_GAAP_CURRENT, window)).fetchone()
        self.assertIsNotNone(expected, "no positive control")
        rows = self.query.query_observations(metric=CURRENT_METRIC, limit=5000)
        self.assertIn(expected["contract_id"], {r["contract_id"] for r in rows})

    def test_a_row_outside_the_mapping_window_is_not_retrieved(self) -> None:
        """
        Requirement 20, and the reason retrieval must carry the window.

        Measured on a real archive: rows exist for this concept with
        `period_end` before the mapping opened, and reaching them would report a
        destination the mapping does not authorise for that period.
        """
        window = self.connection.execute(
            "SELECT MIN(effective_from) FROM metric_concept_mapping"
            " WHERE concept_id = ?", (US_GAAP_CURRENT,)).fetchone()[0]
        before = self.connection.execute(
            "SELECT COUNT(*) FROM observations WHERE metric = ? AND concept = ?"
            " AND period_end < ?", (LEGACY, US_GAAP_CURRENT, window)).fetchone()[0]
        self.assertGreater(before, 0,
                           "no pre-window rows, so the window is untested")
        rows = self.query.query_observations(metric=CURRENT_METRIC, limit=5000)
        returned_ids = {r["contract_id"] for r in rows}
        excluded = self.connection.execute(
            "SELECT contract_id FROM observations WHERE metric = ? AND"
            " concept = ? AND period_end < ? LIMIT 20",
            (LEGACY, US_GAAP_CURRENT, window)).fetchall()
        self.assertTrue(excluded, "no pre-window row to check")
        for row in excluded:
            self.assertNotIn(row["contract_id"], returned_ids)


class TestKnowledgeStateStaysSeparate(unittest.TestCase):
    """A legacy debt row can carry an effective metric AND an effective unit."""

    def setUp(self) -> None:
        corpus_gate.require(self, "snapshot-universe")
        source = os.path.join(H, "snapshot-universe.sqlite")
        workdir = tempfile.mkdtemp()
        self.path = os.path.join(workdir, "probe.sqlite")
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

def test_the_two_mechanisms_are_not_merged_into_one_field(self) -> None:
    """
    A single legacy debt row, three independent answers.

    The repaired rows are the IFRS ones. Those concepts now have an authorised
    metric destination, but *this* row's `period_end` precedes the mapping's
    window, so the destination is still unresolved here -- for the window
    reason, not because nothing claims the concept. Stored metric identity is
    therefore kept, metric destination explicitly unresolved, and the unit
    corrected: three questions, three fields, none of them answering for
    another. Module-level and uncollected at HEAD; 2.73 only corrected the
    description.
    """
    row = self.connection.execute(
        "SELECT o.*, a.ticker FROM observations o"
        " JOIN interpretations i ON i.source_fact_id = o.source_fact_id"
        " JOIN assets a ON a.asset_id = o.asset_id"
        " WHERE o.concept = ? AND o.metric = ? LIMIT 1",
        (IFRS_NONCURRENT, LEGACY)).fetchone()
    self.assertIsNotNone(row, "no repaired IFRS debt row to exercise")
    package = self.query.get_observation(row["contract_id"])
    semantic = package["semantic"]
    inherited = semantic["inherited_mapping"]

    # 1. Stored metric identity is untouched.
    self.assertEqual(package["metric"], LEGACY)
    self.assertEqual(semantic["stored_metric"], LEGACY)
    # 2. Metric destination is a separate, unresolved answer.
    self.assertEqual(inherited["status"],
                     "UNRESOLVED_NO_APPLICABLE_MAPPING")
    self.assertFalse(inherited["resolved"])
    # 3. The unit correction is a third answer, and it is applied.
    self.assertEqual(package["unit"], "currency")
    self.assertIsNotNone(package["currency"])
    self.assertEqual(row["unit"], "ratio")
    # The two mechanisms do not leak into each other's fields.
    self.assertNotIn("unit", inherited)
    self.assertNotIn("knowledge_at", semantic.get("stored_metric", ""))

test_the_two_mechanisms_are_not_merged_into_one_field.__test__ = False


class TestLegacyArchives(unittest.TestCase):
    def test_an_unregistered_successor_keeps_raising_unknown_metric(self) -> None:
        """
        The harness archives predate the supersession migration.

        Metric registration must not be synthesised to make the new predicate
        work; a query for an unregistered metric keeps raising.
        """
        corpus_gate.require(self, "snapshot-universe")
        source = os.path.join(H, "snapshot-universe.sqlite")
        connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            registry = CoreRegistry(connection)
            self.assertEqual(registry.superseded_metric_ids(), [])
            self.assertIsNone(registry.metric(SUCCESSOR))
            self.assertEqual(registry.effective_metric_sources(SUCCESSOR), [])
            query = EvidenceQuery(connection=connection)
            try:
                with self.assertRaises(Exception) as caught:
                    query.query_observations(metric=SUCCESSOR, limit=5)
                self.assertIn("UNKNOWN_METRIC", str(caught.exception).upper())
            finally:
                query.close()
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()