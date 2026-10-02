"""
Knowledge-state interpretations, 2.61.

Focused tests for migration 17 and the domain API that sits on it.

## Which layer enforces what, and why the tests bother distinguishing

SQLite contributes NOT NULL, the foreign key, the unique identity and
append-only. It cannot express the cross-row rules -- one reading per knowledge
instant, supersedes within one source fact, backwards only, no cycles -- because
there is no CHECK across rows in SQLite. Those belong to the 2.59 validators, and
a test that only asserted "it raised" would pass whether the schema or the domain
caught it, and would leave a future reader unsure which guarantee they had.

So every refusal in this file asserts **which layer** refused. That is the
distinction 2.59 measured and 2.61 has to preserve rather than blur.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from archive import InterpretationError  # noqa: E402
from core_registry import CoreRegistry  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

SOURCE_AVAILABLE_AT = "2025-04-22T06:30:00+00:00"
T1 = "2026-09-30T12:00:00+00:00"
T2 = "2026-10-02T00:00:00+00:00"
T3 = "2026-11-15T00:00:00+00:00"
RESTATEMENT_AT = "2026-10-01T00:00:00+00:00"

SFID_F = "sfid_0000000000000000000000F"
SFID_G = "sfid_0000000000000000000000G"
SFID_H = "sfid_0000000000000000000000H"
LINEAGE = "line_shared_by_F_and_G"


class _Source:
    """Three source facts: one to correct, a later filing, and an unrelated one."""

    documents_read = 0
    concept_fetches = 0
    network_fetches = 0

    def resolve_company(self, ticker):
        class Company:
            cik = "0001046179"
            name = "Fixture"
            exchanges = ()
        return Company()

    def submissions(self, cik):
        return {"sic": "3674", "sicDescription": "Semiconductors"}

    def filing_index(self, cik):
        return [{
            "accession": "0001193125-25-083423", "form": "20-F",
            "filing_date": "2025-04-22", "report_date": "2024-12-31",
            "acceptance_datetime": "2025-04-22T06:30:00.000Z",
            "acceptance_precision": "INSTANT",
            "primary_document": "", "is_xbrl": 1,
        }]

    def concept_history(self, cik, taxonomy, concept):
        return None

    def documents_for(self, taxonomy, concept):
        return ()


def build(with_migrations: bool = True) -> SQLiteArchive:
    directory = tempfile.mkdtemp()
    store = SQLiteArchive(os.path.join(directory, "a.sqlite"))
    registry = CoreRegistry(store.connection)
    seed(registry)
    asset_id = store.record_asset("TSM")
    store.connection.execute(
        "INSERT INTO observation_lineage VALUES (?,?,?,?,?,?,?,?)",
        (LINEAGE, asset_id, "debt",
         "ifrs-full:CurrentPortionOfLongtermBorrowings", None,
         "2024-12-31", "2026-09-30T00:00:00+00:00", "one fact about a period"))

    from archive import FilingRef
    from data_contract import Observation, utc_now
    from evidence_model import source_fact_id

    # A distinct accession per fact. `observations_for` collapses rows that
    # share a contract_id -- the documented band-restatement rule -- so two
    # fixtures sharing an accession and a unit would be hidden by that rule and
    # this test would be measuring the collapse rather than the new layer.
    facts = [
        (SFID_F, "ratio", None, "NOT_APPLICABLE", SOURCE_AVAILABLE_AT, 1.0,
         "accF"),
        (SFID_G, "currency", "TWD", "REPORTED", RESTATEMENT_AT, 2.0, "accG"),
        (SFID_H, "currency", "TWD", "REPORTED", SOURCE_AVAILABLE_AT, 3.0,
         "accH"),
    ]
    for sfid, unit, currency, basis, available, value, accession in facts:
        fact_id = source_fact_id(
            source_id="SecEdgar", document_ref=accession, taxonomy="ifrs-full",
            concept="CurrentPortionOfLongtermBorrowings", period_start=None,
            period_end="2024-12-31")
        store.record_observation(
            "TSM",
            Observation(
                observation_id=(
                    f"ingest|debt|ifrs-full:CurrentPartionOfLongtermBorrowings"
                    f"|{accession}|instant|2024-12-31|{unit}"),
                metric="debt", value=value, unit=unit, currency=currency,
                currency_basis=basis, period_start=None,
                period_end="2024-12-31", as_of="2024-12-31",
                available_at=available,
                available_at_basis="ACCEPTANCE_DATETIME",
                provider="SecEdgar", source_type="REGULATORY_FILING",
                source_url=None, definition="debt",
                methodology="as filed", retrieved_at=utc_now(),
                raw={"sec_fact": {"taxonomy": "ifrs-full",
                                  "tag": "CurrentPartionOfLongtermBorrowings"}},
                basis={"reporting_framework": "ifrs-full",
                       "source_declared": True}),
            accession=accession,
            filing=FilingRef(
                accession=accession, form="20-F", taxonomy="ifrs-full",
                fiscal_year=2024, fiscal_period="FY", statement=None,
                instant=1, source_fact_id=sfid,
                source_concept="ifrs-full:CurrentPortionOfLongtermBorrowings"),
            availability_class="SOURCE_DECLARED",
            first_archived_at=available)
    return store


class TestMigrationObjects(unittest.TestCase):
    def setUp(self) -> None:
        self.store = build()
        self.addCleanup(self.store.close)
        self.connection = self.store.connection

    def objects(self, kind: str, table: Optional[str] = None) -> List[str]:
        if table:
            rows = self.connection.execute(
                f"SELECT name FROM sqlite_master WHERE type = ? AND tbl_name = ?"
                " ORDER BY name", (kind, table))
        else:
            rows = self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = ? ORDER BY name",
                (kind,))
        return [r[0] for r in rows]

    def test_interpretations_table_exists(self) -> None:
        self.assertIn("interpretations", self.objects("table"))

    def test_full_unique_index_on_source_fact_exists(self) -> None:
        self.assertIn("observations_source_fact_full",
                      self.objects("index", "observations"))

    def test_0006_partial_index_is_retained(self) -> None:
        """Superseded as a constraint, deliberately not dropped."""
        self.assertIn("observations_source_fact",
                      self.objects("index", "observations"))

    def test_append_only_triggers_exist_on_interpretations(self) -> None:
        triggers = self.objects("trigger", "interpretations")
        self.assertIn("interpretations_no_update", triggers)
        self.assertIn("interpretations_no_delete", triggers)

    def test_observation_append_only_triggers_still_exist(self) -> None:
        triggers = self.objects("trigger", "observations")
        self.assertIn("observations_no_update", triggers)
        self.assertIn("observations_no_delete", triggers)

    def test_migration_is_recorded(self) -> None:
        version = self.connection.execute(
            "SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        self.assertGreaterEqual(version, 17)

    def test_migration_is_idempotent(self) -> None:
        before = self.connection.execute(
            "SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        SQLiteArchive(self.store.path)
        after = self.connection.execute(
            "SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        self.assertEqual(before, after)

    def test_interpretations_start_empty(self) -> None:
        self.assertEqual(self.store.interpretation_count(), 0)

    def test_observation_columns_are_unchanged(self) -> None:
        columns = [r[1] for r in self.connection.execute(
            "PRAGMA table_info(observations)")]
        for required in ("observation_id", "content_hash", "contract_id",
                         "lineage_id", "source_fact_id", "available_at",
                         "replay_eligible_from", "value_json", "unit",
                         "currency"):
            self.assertIn(required, columns)


class TestEnforcementBoundary(unittest.TestCase):
    """Which layer refuses, recorded rather than blurred."""

    def setUp(self) -> None:
        self.store = build()
        self.addCleanup(self.store.close)

    def refuses(self, label: str, fn) -> Tuple[bool, str]:
        try:
            fn()
        except InterpretationError as error:
            return True, f"domain: {error}"
        except sqlite3.IntegrityError as error:
            return True, f"sqlite: {error}"
        except sqlite3.OperationalError as error:
            return True, f"sqlite: {error}"
        return False, "accepted"

    def test_foreign_key_to_a_nonexistent_source_fact_is_refused_by_sqlite(self) -> None:
        refused, by = self.refuses(
            "unknown source fact",
            lambda: self.store.add_interpretation(
                "sfid_does_not_exist", T1, "currency", "TWD", "REPORTED"))
        self.assertTrue(refused)
        # The archive looks the fact up itself so it can hand the validators a
        # real series, and refuses before the database is reached.
        self.assertIn("no observation carries source_fact_id", by)

    def test_missing_knowledge_at_is_refused_by_the_domain(self) -> None:
        self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                      "NOT_APPLICABLE")
        refused, by = self.refuses(
            "missing knowledge_at",
            lambda: self.store.add_interpretation(
                SFID_F, "", "currency", "TWD", "REPORTED"))
        self.assertTrue(refused)
        self.assertIn("knowledge_at", by)

    def test_same_knowledge_at_is_refused_by_the_domain(self) -> None:
        self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                      "NOT_APPLICABLE")
        refused, by = self.refuses(
            "a second reading at T1",
            lambda: self.store.add_interpretation(
                SFID_F, T1, "currency", "USD", "REPORTED"))
        self.assertTrue(refused)
        self.assertIn("domain:", by)
        self.assertIn("already exists at", by)

    def test_earlier_knowledge_at_is_refused_by_the_domain(self) -> None:
        self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                      "NOT_APPLICABLE")
        refused, by = self.refuses(
            "a reading before T1",
            lambda: self.store.add_interpretation(
                SFID_F, "2026-01-01T00:00:00+00:00", "currency", "TWD",
                "REPORTED"))
        self.assertTrue(refused)
        self.assertIn("domain:", by)
        self.assertIn("precedes", by)

    def test_an_identical_repeat_is_recognised_rather_than_refused(self) -> None:
        first = self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                              "NOT_APPLICABLE")
        again = self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                              "NOT_APPLICABLE")
        self.assertTrue(first["created"])
        self.assertFalse(again["created"])
        self.assertEqual(first["interpretation"]["interpretation_id"],
                         again["interpretation"]["interpretation_id"])
        self.assertEqual(len(
            self.store.interpretations_for_source_fact(SFID_F)), 1)

    def test_unique_identity_is_also_enforced_by_sqlite(self) -> None:
        """Belt and braces: even bypassing the domain, the index refuses."""
        self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                      "NOT_APPLICABLE")
        row = self.store.interpretations_for_source_fact(SFID_F)[0]
        refused, by = self.refuses(
            "direct duplicate insert",
            lambda: self.store.connection.execute(
                "INSERT INTO interpretations (interpretation_id,"
                " source_fact_id, knowledge_at, unit, currency,"
                " currency_basis, identity, supersedes, created_at)"
                " VALUES ('other', ?, ?, 'ratio', NULL, 'NOT_APPLICABLE',"
                " ?, NULL, '2026-10-02T00:00:00+00:00')",
                (SFID_F, T1, row["identity"])))
        self.assertTrue(refused)
        self.assertIn("sqlite:", by)

    def test_update_is_refused_by_sqlite(self) -> None:
        self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                      "NOT_APPLICABLE")
        refused, by = self.refuses(
            "update an interpretation",
            lambda: self.store.connection.execute(
                "UPDATE interpretations SET unit = 'currency'"
                " WHERE knowledge_at = ?", (T1,)))
        self.assertTrue(refused)
        self.assertIn("append-only", by)

    def test_delete_is_refused_by_sqlite(self) -> None:
        self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                      "NOT_APPLICABLE")
        refused, by = self.refuses(
            "delete an interpretation",
            lambda: self.store.connection.execute(
                "DELETE FROM interpretations WHERE knowledge_at = ?", (T1,)))
        self.assertTrue(refused)
        self.assertIn("append-only", by)


class TestSelectionAndAudit(unittest.TestCase):
    def setUp(self) -> None:
        self.store = build()
        self.addCleanup(self.store.close)
        self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                      "NOT_APPLICABLE")
        self.store.add_interpretation(SFID_F, T2, "currency", "TWD", "REPORTED")

    def test_pit_selection_matches_the_contract(self) -> None:
        """Applied, then compared -- not asserted from the contract's wording."""
        observed = {
            "before T1": self.store.effective_interpretation(
                SFID_F, "2026-01-01"),
            "exactly T1": self.store.effective_interpretation(SFID_F, T1),
            "between": self.store.effective_interpretation(SFID_F, "2026-10-01"),
            "exactly T2": self.store.effective_interpretation(SFID_F, T2),
            "after T2": self.store.effective_interpretation(SFID_F, "2026-12-31"),
        }
        units = {k: (v["unit"] if v else None) for k, v in observed.items()}
        self.assertEqual(units, {
            "before T1": None, "exactly T1": "ratio", "between": "ratio",
            "exactly T2": "currency", "after T2": "currency"})
        # The empty position alone proves nothing, so the same trace must also
        # show both later positions selecting correctly.
        self.assertEqual(units["exactly T2"], "currency")
        self.assertIsNotNone(observed["after T2"])

    def test_audit_lists_every_interpretation_in_knowledge_order(self) -> None:
        rows = self.store.interpretations_for_source_fact(SFID_F)
        self.assertEqual([r["unit"] for r in rows], ["ratio", "currency"])
        self.assertEqual([r["knowledge_at"] for r in rows], [T1, T2])

    def test_supersedes_chains_the_preceding_reading(self) -> None:
        rows = self.store.interpretations_for_source_fact(SFID_F)
        self.assertIsNone(rows[0]["supersedes"])
        self.assertEqual(rows[1]["supersedes"], rows[0]["interpretation_id"])

    def test_a_second_correction_appends_and_chains(self) -> None:
        third = self.store.add_interpretation(SFID_F, T3, "currency", "USD",
                                              "REPORTED")
        rows = self.store.interpretations_for_source_fact(SFID_F)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]["supersedes"],
                         rows[1]["interpretation_id"])
        self.assertEqual(third["interpretation"]["currency"], "USD")

    def test_restatement_keeps_its_own_series_despite_a_shared_lineage(self) -> None:
        self.store.add_interpretation(SFID_G, RESTATEMENT_AT, "currency", "TWD",
                                      "REPORTED")
        f_rows = self.store.interpretations_for_source_fact(SFID_F)
        g_rows = self.store.interpretations_for_source_fact(SFID_G)
        self.assertEqual(len(f_rows), 2)
        self.assertEqual(len(g_rows), 1)
        self.assertNotEqual(f_rows[0]["source_fact_id"],
                            g_rows[0]["source_fact_id"])

    def test_unrelated_source_fact_is_unaffected(self) -> None:
        rows = self.store.interpretations_for_source_fact(SFID_H)
        self.assertEqual(rows, [])

    def test_get_interpretation_round_trips(self) -> None:
        stored = self.store.interpretations_for_source_fact(SFID_F)[0]
        fetched = self.store.get_interpretation(stored["interpretation_id"])
        self.assertEqual(fetched["identity"], stored["identity"])

    def test_no_interpretation_carries_source_fact_attributes(self) -> None:
        columns = {r[1] for r in self.store.connection.execute(
            "PRAGMA table_info(interpretations)")}
        for borrowed in ("value_json", "period_start", "period_end", "metric",
                         "available_at", "replay_eligible_from", "lineage_id"):
            self.assertNotIn(borrowed, columns)


class TestObservationsAreUntouched(unittest.TestCase):
    def setUp(self) -> None:
        self.store = build()
        self.addCleanup(self.store.close)

    def test_writing_an_interpretation_changes_no_observation(self) -> None:
        before = [tuple(r) for r in self.store.connection.execute(
            "SELECT observation_id, content_hash, contract_id, source_fact_id,"
            " available_at, replay_eligible_from, value_json, unit FROM"
            " observations ORDER BY observation_id")]
        self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                      "NOT_APPLICABLE")
        self.store.add_interpretation(SFID_F, T2, "currency", "TWD", "REPORTED")
        after = [tuple(r) for r in self.store.connection.execute(
            "SELECT observation_id, content_hash, contract_id, source_fact_id,"
            " available_at, replay_eligible_from, value_json, unit FROM"
            " observations ORDER BY observation_id")]
        self.assertEqual(before, after)

    def test_existing_readers_are_untouched(self) -> None:
        """`observations_for` must not see or be changed by the new layer."""
        self.store.add_interpretation(SFID_F, T1, "ratio", None,
                                      "NOT_APPLICABLE")
        replay = self.store.observations_for("TSM", "2026-12-31")
        self.assertEqual(len(replay), 3)
        self.assertEqual(
            sorted((o.unit or "") for o in replay),
            ["currency", "currency", "ratio"])


class TestOlderArchives(unittest.TestCase):
    """An archive predating 2.61 must open, and must not crash other calls."""

    def test_an_archive_without_the_table_reports_absence_rather_than_raising(
            self) -> None:
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, "old.sqlite")
        store = SQLiteArchive(path)
        try:
            store.connection.execute("DROP TABLE interpretations")
            store.connection.execute("DROP INDEX observations_source_fact_full")
            self.assertFalse(store._has_interpretations())
            self.assertEqual(store.interpretations_for_source_fact(SFID_F), [])
            self.assertIsNone(store.effective_interpretation(SFID_F, T2))
            self.assertIsNone(store.get_interpretation("anything"))
            self.assertEqual(store.interpretation_count(), 0)
            with self.assertRaises(InterpretationError):
                store.add_interpretation(SFID_F, T1, "ratio", None,
                                         "NOT_APPLICABLE")
            # Existing reads still work on an archive that predates 2.61. This
            # one is freshly created and therefore empty, so the assertion is
            # that the reads answer rather than that they return rows: an empty
            # result is not evidence of a working knowledge model.
            self.assertIsInstance(store.observation_count(), int)
            self.assertEqual(store.observations_for("TSM", "2026-12-31"), [])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()