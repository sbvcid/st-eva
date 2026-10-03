"""
2.73 focused suite: identity versus composition.

Everything here is about one thing -- the registry can now express that
`ifrs-full:LongtermBorrowings` is both a COMPOSITION component of
`long_term_debt` and the IDENTITY source of `long_term_debt_noncurrent`, without
those two statements competing for the same question.

2.72 measured what happens without that: promoting the component mapping left
the concept AMBIGUOUS between the aggregate that names it and the component it
belongs to. The four COMPOSITION rows are untouched and still true; they are
simply no longer candidates.
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

from core_registry import CoreRegistry  # noqa: E402
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
US_GAAP_NONCURRENT = "us-gaap:LongTermDebtNoncurrent"

# An existing concept with no mapping at all, so a claim about it can only come
# from what this test inserts. Inventing a concept id would be rejected by the
# foreign key and would test nothing.
UNDECLARED = "ifrs-full:WeightedAverageShares"

EXPECTED_COMPOSITION = {
    (AGGREGATE, "us-gaap:LongTermDebtNoncurrent"),
    (AGGREGATE, "us-gaap:LongTermDebtCurrent"),
    (AGGREGATE, IFRS_NONCURRENT),
    (AGGREGATE, IFRS_CURRENT),
}


class TestRegistryClassification(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.addCleanup(self.store.close)
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.store.connection.commit()

    def rows(self):
        return [dict(r) for r in self.registry.connection.execute(
            "SELECT metric_id, concept_id, mapping_type, relation_kind,"
            " scope_json, effective_from, effective_to FROM"
            " metric_concept_mapping")]

    def test_every_mapping_has_a_relation_kind(self) -> None:
        for row in self.rows():
            self.assertIn(row["relation_kind"], ("IDENTITY", "COMPOSITION"),
                          row)
        self.assertEqual(len(self.rows()), 50)

    def test_exactly_four_mappings_are_composition(self) -> None:
        composition = {(r["metric_id"], r["concept_id"]) for r in self.rows()
                      if r["relation_kind"] == "COMPOSITION"}
        self.assertEqual(composition, EXPECTED_COMPOSITION)

    def test_every_other_mapping_is_identity(self) -> None:
        identity = [r for r in self.rows() if r["relation_kind"] == "IDENTITY"]
        self.assertEqual(len(identity), 46)

    def test_the_composition_rows_were_stored_not_defaulted(self) -> None:
        """
        The seed is authoritative, so a dataclass default would silently make
        every row IDENTITY. This reads the persisted column.
        """
        stored = {(r["metric_id"], r["concept_id"]): r["relation_kind"]
                  for r in self.rows()}
        for pair in EXPECTED_COMPOSITION:
            self.assertEqual(stored[pair], "COMPOSITION", pair)

    def test_the_composition_relationships_are_not_dated_out(self) -> None:
        for row in self.rows():
            if (row["metric_id"], row["concept_id"]) in EXPECTED_COMPOSITION:
                self.assertIsNone(row["effective_to"],
                                  "2.73 must not weaken a composition "
                                  "relationship by closing its window")
                self.assertEqual(row["mapping_type"], "PARTIAL", row)

    def test_the_promoted_mapping_is_identity_and_partial(self) -> None:
        row = next(r for r in self.rows()
                   if r["concept_id"] == IFRS_NONCURRENT
                   and r["metric_id"] == NONCURRENT)
        self.assertEqual(row["relation_kind"], "IDENTITY")
        self.assertEqual(row["mapping_type"], "PARTIAL")
        self.assertEqual(row["effective_from"], "2020-12-31")

    def test_the_271_current_mapping_is_untouched(self) -> None:
        row = next(r for r in self.rows()
                   if r["concept_id"] == IFRS_CURRENT
                   and r["metric_id"] == CURRENT)
        self.assertEqual(row["relation_kind"], "IDENTITY")
        self.assertEqual(row["mapping_type"], "EXACT")
        self.assertEqual(row["effective_from"], "2016-12-31")

    def test_the_active_core_metric_count_is_unchanged(self) -> None:
        active = [m.metric_id for m in self.registry.metrics()
                  if m.status == "ACTIVE"]
        self.assertEqual(len(active), 20)


class TestResolverIsolation(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.addCleanup(self.store.close)
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.store.connection.commit()

    def test_longterm_borrowings_resolves_to_its_component(self) -> None:
        resolution = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.destination_metric, NONCURRENT)
        self.assertEqual(resolution.mapping_type, "PARTIAL")
        self.assertEqual(resolution.mapping_origin, "DIRECT")
        self.assertFalse(resolution.is_exact)
        self.assertTrue(resolution.is_component)

    def test_the_aggregate_is_never_a_destination(self) -> None:
        resolution = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.assertNotEqual(resolution.destination_metric, AGGREGATE)
        # And it never appears as a candidate at all.
        declared = {
            mapping.metric_id: mapping.relation_kind
            for mapping, _ in self.registry.metrics_for_concept(IFRS_NONCURRENT)}
        self.assertEqual(declared.get(AGGREGATE), "COMPOSITION")

    def test_the_current_portion_still_resolves_exact(self) -> None:
        resolution = self.registry.resolve_source_concept(IFRS_CURRENT)
        self.assertTrue(resolution.is_resolved)
        self.assertEqual(resolution.destination_metric, CURRENT)
        self.assertTrue(resolution.is_exact)

    def test_an_exact_claim_beats_a_partial_one(self) -> None:
        """
        What 2.73 must not introduce: strength ordering inside PARTIAL.

        An EXACT identity claim is still the answer when another active metric
        calls the same concept one of its components.
        """
        self.registry.add_mapping(_ConceptMapping(
            metric_id="sga", concept_id=UNDECLARED,
            mapping_type="EXACT", relation_kind="IDENTITY"))
        self.registry.add_mapping(_ConceptMapping(
            metric_id="sbc", concept_id=UNDECLARED,
            mapping_type="PARTIAL", relation_kind="IDENTITY",
            effective_from="2020-12-31"))
        resolution = self.registry.resolve_source_concept(UNDECLARED)
        self.assertEqual(resolution.destination_metric, "sga")
        self.assertEqual(resolution.mapping_type, "EXACT")
        self.assertNotIn("sbc", resolution.candidates)

    def test_genuine_competing_exact_claims_stay_ambiguous(self) -> None:
        self.registry.add_mapping(_ConceptMapping(
            metric_id="sga", concept_id=UNDECLARED,
            mapping_type="EXACT", relation_kind="IDENTITY"))
        self.registry.add_mapping(_ConceptMapping(
            metric_id="sbc", concept_id=UNDECLARED,
            mapping_type="EXACT", relation_kind="IDENTITY"))
        resolution = self.registry.resolve_source_concept(UNDECLARED)
        self.assertEqual(resolution.status, "AMBIGUOUS_MAPPING")
        self.assertFalse(resolution.is_resolved)
        # An ambiguity is a question, so it names both claimants rather than
        # picking one. Guarding this is what keeps the promoted concept's single
        # PARTIAL claim meaningful.
        self.assertEqual(set(resolution.candidates), {"sga", "sbc"})

    def test_two_direct_partial_claims_are_ambiguous_not_ordered(self) -> None:
        """
        The new component branch cannot silently choose between two metrics.

        One measured PARTIAL is a destination. Two is the same registry question
        as two EXACT claims, and 2.73 answers it the same way.
        """
        self.registry.add_mapping(_ConceptMapping(
            metric_id="sga", concept_id=UNDECLARED,
            mapping_type="PARTIAL", relation_kind="IDENTITY",
            effective_from="2020-12-31"))
        self.registry.add_mapping(_ConceptMapping(
            metric_id="sbc", concept_id=UNDECLARED,
            mapping_type="PARTIAL", relation_kind="IDENTITY",
            effective_from="2020-12-31"))
        resolution = self.registry.resolve_source_concept(UNDECLARED)
        self.assertEqual(resolution.status, "AMBIGUOUS_MAPPING")
        self.assertFalse(resolution.is_resolved)
        self.assertEqual(set(resolution.candidates), {"sga", "sbc"})

    def test_an_empty_candidate_set_stays_unresolved(self) -> None:
        resolution = self.registry.resolve_source_concept(
            "us-gaap:NeverDeclared")
        self.assertFalse(resolution.is_resolved)
        self.assertEqual(resolution.status,
                         "UNRESOLVED_NO_APPLICABLE_MAPPING")

    def test_resolution_does_not_depend_on_mapping_order(self) -> None:
        first = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        rows = [dict(r) for r in self.registry.connection.execute(
            "SELECT * FROM metric_concept_mapping")]
        for row in reversed(rows):
            self.registry.add_mapping(_ConceptMapping(
                metric_id=row["metric_id"], concept_id=row["concept_id"],
                mapping_type=row["mapping_type"],
                relation_kind=row["relation_kind"],
                effective_from=row["effective_from"],
                effective_to=row["effective_to"], scope=_scope(row)))
        second = self.registry.resolve_source_concept(IFRS_NONCURRENT)
        self.assertEqual(first.destination_metric, second.destination_metric)
        self.assertEqual(first.mapping_type, second.mapping_type)


def _scope(row):
    import json as _json
    raw = row.get("scope_json")
    if not raw:
        return None
    try:
        return _json.loads(raw)
    except ValueError:
        return None


def _ConceptMapping(**kwargs):
    from core_registry import ConceptMapping
    return ConceptMapping(**kwargs)


class TestScopeMetadata(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.addCleanup(self.store.close)
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.store.connection.commit()

    def test_scope_round_trips(self) -> None:
        mapping = next(
            m for m, _ in self.registry.metrics_for_concept(IFRS_NONCURRENT)
            if m.metric_id == NONCURRENT)
        self.assertIsNotNone(mapping.scope)

    def test_the_measured_breadth_is_persisted(self) -> None:
        mapping = next(
            m for m, _ in self.registry.metrics_for_concept(IFRS_NONCURRENT)
            if m.metric_id == NONCURRENT)
        scope = mapping.scope
        self.assertEqual(scope["variation"], "FILER_DEPENDENT")
        self.assertEqual(scope["measured"], {"TSM": "SUBSET", "RIO": "WHOLE"})
        self.assertEqual(scope["unmeasured_holders"], 6)

    def test_a_composition_row_needs_no_scope(self) -> None:
        for mapping, _ in self.registry.metrics_for_concept(IFRS_CURRENT):
            if mapping.metric_id == AGGREGATE:
                self.assertIsNone(mapping.scope)


class TestPre273ArchiveCompatibility(unittest.TestCase):
    """
    An archive without the new columns must still answer.

    This builds the pre-2.73 table shape for real rather than projecting around
    the columns, because a projection cannot fail the way an archive can: the
    loader reads whatever columns the row carries, and `SELECT *` on a table that
    never had them is the only thing that exercises the tolerance.
    """

    PRE_273_SCHEMA = (
        "CREATE TABLE metric_concept_mapping ("
        "metric_id TEXT, concept_id TEXT, mapping_type TEXT,"
        " effective_from TEXT, effective_to TEXT, notes TEXT)")

    def test_a_table_without_the_new_columns_still_loads(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(self.PRE_273_SCHEMA)
            connection.execute(
                "INSERT INTO metric_concept_mapping VALUES"
                " (?, ?, 'EXACT', '2014-09-27', NULL, 'pre-2.73 row')",
                ("long_term_debt_current", "us-gaap:LongTermDebtCurrent"))
            registry = CoreRegistry(connection)
            mapping = registry._mapping(
                connection.execute("SELECT * FROM metric_concept_mapping")
                .fetchone())
            self.assertIsNotNone(mapping)
            self.assertEqual(mapping.metric_id, "long_term_debt_current")
            self.assertEqual(mapping.mapping_type, "EXACT")
            # Absent columns mean absent metadata, not a default claim of
            # anything, and never an exception.
            self.assertEqual(mapping.relation_kind, "IDENTITY")
            self.assertIsNone(mapping.scope)
        finally:
            connection.close()

    def test_a_row_with_the_columns_still_reads_them(self) -> None:
        """The other direction, so the tolerance is not the only path."""
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(self.PRE_273_SCHEMA)
            connection.execute("ALTER TABLE metric_concept_mapping"
                               " ADD COLUMN relation_kind TEXT")
            connection.execute("ALTER TABLE metric_concept_mapping"
                               " ADD COLUMN scope_json TEXT")
            connection.execute(
                "INSERT INTO metric_concept_mapping VALUES"
                " (?, ?, 'PARTIAL', '2020-12-31', NULL, NULL, 'COMPOSITION',"
                " '{\"variation\": \"FILER_DEPENDENT\"}')",
                ("long_term_debt", "ifrs-full:LongtermBorrowings"))
            registry = CoreRegistry(connection)
            mapping = registry._mapping(
                connection.execute("SELECT * FROM metric_concept_mapping")
                .fetchone())
            self.assertEqual(mapping.relation_kind, "COMPOSITION")
            self.assertEqual(mapping.scope, {"variation": "FILER_DEPENDENT"})
        finally:
            connection.close()

    def test_malformed_scope_json_degrades_to_absent(self) -> None:
        """Scope is a qualification; losing it must not lose the mapping."""
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            connection.execute(self.PRE_273_SCHEMA)
            connection.execute("ALTER TABLE metric_concept_mapping"
                               " ADD COLUMN relation_kind TEXT")
            connection.execute("ALTER TABLE metric_concept_mapping"
                               " ADD COLUMN scope_json TEXT")
            connection.execute(
                "INSERT INTO metric_concept_mapping VALUES"
                " (?, ?, 'EXACT', NULL, NULL, NULL, 'IDENTITY', 'not json')",
                ("sga", "us-gaap:SellingCosts"))
            mapping = CoreRegistry(connection)._mapping(
                connection.execute("SELECT * FROM metric_concept_mapping")
                .fetchone())
            self.assertEqual(mapping.metric_id, "sga")
            self.assertIsNone(mapping.scope)
        finally:
            connection.close()


class TestHistoricalPartition(unittest.TestCase):
    """
    The primary 2.73 observable, executed against real archived rows.

    Not an expected count copied from a test: the partition is measured by
    querying the archive, and both sides are asserted so a query that returned
    everything, or nothing, would fail.

    The partition under test is over one source concept:

        ifrs-full:LongtermBorrowings
          -> long_term_debt_noncurrent   reachable
          -> long_term_debt              not reachable
    """

    ARCHIVE = "snapshot-universe"
    LEGACY = "debt"

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

    def _window(self, metric):
        """The persisted window of the promoted mapping, or None if absent."""
        row = self.connection.execute(
            "SELECT effective_from, effective_to FROM metric_concept_mapping"
            " WHERE metric_id = ? AND concept_id = ?",
            (metric, IFRS_NONCURRENT)).fetchone()
        return (row["effective_from"], row["effective_to"]) if row else None

    def _discovered(self, since=None, until=None):
        """Real rows carrying the concept, discovered from the archive."""
        sql = ("SELECT contract_id FROM observations WHERE concept = ?"
               " AND metric = ?")
        params = [IFRS_NONCURRENT, self.LEGACY]
        if since:
            sql += " AND period_end >= ?"
            params.append(since)
        if until:
            sql += " AND period_end < ?"
            params.append(until)
        return {r["contract_id"] for r in self.connection.execute(sql, params)}

    def _reachable(self, metric):
        rows = self.query.query_observations(metric=metric, limit=5000)
        return {r["contract_id"] for r in rows}

    def test_the_promoted_mapping_is_persisted_in_the_archive(self) -> None:
        window = self._window(NONCURRENT)
        self.assertIsNotNone(
            window,
            "the 2.73 promotion is absent from the seeded archive, so every "
            "retrieval assertion below would pass vacuously")

    def test_the_affected_rows_reach_the_component_and_not_the_aggregate(
            self) -> None:
        since, until = self._window(NONCURRENT)
        affected = self._discovered(since)
        self.assertGreater(len(affected), 0,
                           "no affected rows discovered, so nothing tested")

        under_component = self._reachable(NONCURRENT)
        self.assertEqual(
            affected - under_component, set(),
            "affected rows must be reachable under their canonical destination")

        under_aggregate = self._reachable(AGGREGATE)
        self.assertEqual(affected & under_aggregate, set())
        # The aggregate has no destination source at all, so it retrieves
        # nothing -- not the affected rows, and not anything else.
        self.assertEqual(self.query._last_result_total, 0)
        self.assertEqual(len(under_aggregate), 0)

    def test_the_component_query_returns_both_declarers_and_nothing_else(
            self) -> None:
        """
        Partition is exact in both directions.

        Both directions matter: returning everything would satisfy the first
        test, and returning only the IFRS rows would satisfy it too while
        dropping 1,404 US-GAAP rows.
        """
        since, until = self._window(NONCURRENT)
        rows = self.query.query_observations(metric=NONCURRENT, limit=5000)
        returned = {r["contract_id"] for r in rows}
        concepts = {(r.get("source") or {}).get("concept") for r in rows}
        self.assertEqual(concepts, {IFRS_NONCURRENT, US_GAAP_NONCURRENT})

        ifrs = {c for c in returned
                if self.connection.execute(
                    "SELECT concept FROM observations WHERE contract_id = ?",
                    (c,)).fetchone()["concept"] == IFRS_NONCURRENT}
        self.assertEqual(ifrs, self._discovered(since))
        self.assertLess(len(ifrs), len(returned),
                        "the US-GAAP rows disappeared, so the partition is "
                        "one-sided")

    def test_rows_outside_the_promoted_window_are_still_excluded(self) -> None:
        """
        Reachability is the window's, not the concept's.

        The archive holds IFRS rows from before the mapping opened. Reaching
        them would report a destination for a period the mapping does not
        cover, and a query that returned every row of the concept would pass
        every other test here.
        """
        since, _until = self._window(NONCURRENT)
        outside = self._discovered(None, since)
        self.assertGreater(len(outside), 0,
                           "no pre-window rows, so the window is untested")
        self.assertEqual(outside & self._reachable(NONCURRENT), set())

    def test_the_canonical_stored_query_is_unchanged(self) -> None:
        """The stored identity is untouched: promotion adds a destination."""
        legacy = self.query.query_observations(metric=self.LEGACY, limit=5000)
        self.assertGreater(len(legacy), 0)
        stored = self.connection.execute(
            "SELECT COUNT(*) FROM observations WHERE metric = ?",
            (self.LEGACY,)).fetchone()[0]
        self.assertEqual(self.query._last_result_total, stored)


if __name__ == "__main__":
    unittest.main()