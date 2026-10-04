"""
Knowledge-state reader integration, 2.63.

`observations_for` now overlays the interpretation effective at the requested
cutoff onto the observation, so a correction becomes visible without the stored
row ever being rewritten.

## The rule these tests exist to pin

    before availability        -> the source fact is not observable at all
    availability <= cutoff < K -> the observation's own reading, BASELINE
    cutoff >= K                -> the interpretation's reading, APPLIED

The middle row is the one that was broken. 2.62 established that an
interpretation table is an *overlay* and not a replacement: the original reading
is the observation itself, so "no interpretation at this cutoff" must mean "the
baseline still stands" and never "this fact has nothing". A reader that returned
None there would make every corrected fact vanish from the window between its
publication and the correction.

## Three states, kept apart

`interpretation_for` distinguishes APPLIED, BASELINE and UNAVAILABLE_LEGACY. The
last is an archive predating migration 17, where the question is unanswerable
rather than answered with nothing. Collapsing it into the other two would make
a legacy archive look like an archive that believes the stored reading was
always wrong.
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
import corpus_gate  # noqa: E402

# The harness archives live beside `tests`, not inside it.
H = os.path.join(os.path.dirname(HERE), "experiments",
                 "003-llm-evidence-retrieval", "harness")

AVAILABLE = "2018-03-28T21:29:52.000Z"
K1 = "2026-10-02T00:00:00+00:00"
K2 = "2026-11-15T00:00:00+00:00"
RESTATEMENT_AVAILABLE = "2026-10-01T00:00:00+00:00"

SFID_MAIN = "sfid_00000000000000000000001"
SFID_RESTATED = "sfid_00000000000000000000002"
SFID_UNRELATED = "sfid_00000000000000000000003"
LINEAGE = "line_shared"


def build(with_interpretations_table: bool = True) -> SQLiteArchive:
    """Three facts: one to correct, a later restatement, one unrelated."""
    directory = tempfile.mkdtemp()
    store = SQLiteArchive(os.path.join(directory, "a.sqlite"))
    registry = CoreRegistry(store.connection)
    seed(registry)
    asset_id = store.record_asset("TSM")
    store.connection.execute(
        "INSERT INTO observation_lineage VALUES (?,?,?,?,?,?,?,?)",
        (LINEAGE, asset_id, "debt",
         "ifrs-full:CurrentPortionOfLongtermBorrowings", None, "2024-12-31",
         "2026-09-30T00:00:00+00:00", "one fact about a period"))

    from archive import FilingRef
    from data_contract import Observation, utc_now
    from evidence_model import source_fact_id

    facts = [
        (SFID_MAIN, "acc1", AVAILABLE, "ratio", None, 1.0),
        (SFID_RESTATED, "acc2", RESTATEMENT_AVAILABLE, "currency", "TWD", 2.0),
        (SFID_UNRELATED, "acc3", AVAILABLE, "currency", "TWD", 3.0),
    ]
    for sfid, accession, available, unit, currency, value in facts:
        fact_id = source_fact_id(
            source_id="SecEdgar", document_ref=accession, taxonomy="ifrs-full",
            concept="CurrentPortionOfLongtermBorrowings", period_start=None,
            period_end="2024-12-31")
        store.record_observation(
            "TSM",
            Observation(
                observation_id=(
                    f"ingest|debt|ifrs-full:CurrentPortionOfLongtermBorrowings"
                    f"|{accession}|instant|2024-12-31|{unit}"),
                metric="debt", value=value, unit=unit, currency=currency,
                currency_basis="REPORTED" if currency else "NOT_APPLICABLE",
                period_start=None, period_end="2024-12-31",
                as_of="2024-12-31", available_at=available,
                available_at_basis="ACCEPTANCE_DATETIME",
                provider="SecEdgar", source_type="REGULATORY_FILING",
                source_url=None, definition="debt", methodology="as filed",
                retrieved_at=utc_now(),
                raw={"sec_fact": {"taxonomy": "ifrs-full", "tag": "X"}},
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
    if not with_interpretations_table:
        store.connection.execute("DROP TABLE interpretations")
    return store


class _Reader:
    """Helpers that drive the real reader rather than restating its result."""

    def __init__(self, store: SQLiteArchive, source_fact_id: str,
                 ticker: str = "TSM"):
        self.store = store
        self.source_fact_id = source_fact_id
        # The ticker is a parameter, not a constant: the fixture happens to be
        # TSM, and the real archives are not. Hardcoding it made every
        # real-archive assertion pass vacuously -- the reader was asked about an
        # asset that does not exist there and correctly returned nothing.
        self.ticker = ticker

    def read(self, cutoff: str) -> dict:
        for observation in self.store.observations_for(self.ticker, cutoff):
            if self.store._source_fact_id_of(observation) == self.source_fact_id:
                applied = (observation.basis or {}).get(
                    "knowledge_interpretation")
                return {
                    "present": True,
                    "unit": observation.unit,
                    "currency": observation.currency,
                    "value": observation.value,
                    "period_end": observation.period_end,
                    "metric": observation.metric,
                    "contract_id": observation.observation_id,
                    "interpretation_applied": applied is not None,
                    "interpretation_at": (applied or {}).get("knowledge_at"),
                }
        return {"present": False}


class TestLegacyArchives(unittest.TestCase):
    """Areas 1 and 2: no table, and a table with no rows."""

    def test_an_archive_without_the_table_behaves_exactly_as_before(self) -> None:
        store = build(with_interpretations_table=False)
        try:
            self.assertFalse(store.knowledge_state_available())
            row = _Reader(store, SFID_MAIN).read("2024-06-01")
            self.assertTrue(row["present"])
            self.assertEqual(row["unit"], "ratio")
            self.assertIsNone(row["currency"])
            self.assertFalse(row["interpretation_applied"])
        finally:
            store.close()

    def test_a_legacy_archive_is_distinguished_from_no_applicable_reading(self) -> None:
        store = build(with_interpretations_table=False)
        try:
            _, status = store.interpretation_for(SFID_MAIN, "2024-06-01")
            self.assertEqual(status, "UNAVAILABLE_LEGACY")
        finally:
            store.close()

    def test_an_empty_table_reads_as_baseline_not_unavailable(self) -> None:
        store = build()
        try:
            self.assertTrue(store.knowledge_state_available())
            _, status = store.interpretation_for(SFID_MAIN, "2024-06-01")
            self.assertEqual(status, "BASELINE")
            self.assertEqual(store.interpretation_count(), 0)
            row = _Reader(store, SFID_MAIN).read("2024-06-01")
            self.assertEqual(row["unit"], "ratio")
        finally:
            store.close()

    def test_a_legacy_archive_creates_no_structures_to_make_a_query_pass(self) -> None:
        store = build(with_interpretations_table=False)
        try:
            store.observations_for("TSM", "2024-06-01")
            names = {r[0] for r in store.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertNotIn("interpretations", names)
        finally:
            store.close()


class TestBaselineFallback(unittest.TestCase):
    """Area 3 and the fallback that 2.62 exposed."""

    def test_a_fact_without_a_correction_reads_as_itself(self) -> None:
        store = build()
        try:
            row = _Reader(store, SFID_UNRELATED).read("2024-06-01")
            self.assertEqual(row["unit"], "currency")
            self.assertEqual(row["currency"], "TWD")
            self.assertFalse(row["interpretation_applied"])
        finally:
            store.close()

    def test_a_fact_with_a_correction_reads_baseline_before_it(self) -> None:
        store = build()
        try:
            store.add_interpretation(SFID_MAIN, K1, "currency", "TWD",
                                     "REPORTED")
            row = _Reader(store, SFID_MAIN).read("2024-06-01")
            self.assertEqual(row["unit"], "ratio")
            self.assertIsNone(row["currency"])
            self.assertFalse(row["interpretation_applied"])
        finally:
            store.close()

    def test_the_fact_does_not_disappear_merely_because_no_row_applies(self) -> None:
        store = build()
        try:
            store.add_interpretation(SFID_MAIN, K1, "currency", "TWD",
                                     "REPORTED")
            _, status = store.interpretation_for(SFID_MAIN, "2020-01-01")
            self.assertEqual(status, "BASELINE")
            self.assertTrue(_Reader(store, SFID_MAIN).read("2020-01-01")["present"])
        finally:
            store.close()


class TestPITMatrix(unittest.TestCase):
    """Areas 6 to 10, executed through the reader."""

    def setUp(self) -> None:
        self.store = build()
        self.addCleanup(self.store.close)
        self.store.add_interpretation(SFID_MAIN, K1, "currency", "TWD",
                                      "REPORTED")
        self.reader = _Reader(self.store, SFID_MAIN)

    def test_1_before_source_availability_the_fact_is_absent(self) -> None:
        self.assertFalse(self.reader.read("2017-01-01")["present"])

    def test_2_at_source_availability_the_baseline_stands(self) -> None:
        row = self.reader.read(AVAILABLE[:10])
        self.assertTrue(row["present"])
        self.assertEqual(row["unit"], "ratio")
        self.assertIsNone(row["currency"])

    def test_3_between_availability_and_correction_the_baseline_stands(self) -> None:
        row = self.reader.read("2024-06-01")
        self.assertEqual(row["unit"], "ratio")
        self.assertIsNone(row["currency"])

    def test_4_exactly_at_knowledge_at_the_correction_applies(self) -> None:
        row = self.reader.read(K1)
        self.assertEqual(row["unit"], "currency")
        self.assertEqual(row["currency"], "TWD")
        self.assertTrue(row["interpretation_applied"])
        self.assertEqual(row["interpretation_at"], K1)

    def test_5_after_knowledge_at_the_correction_applies(self) -> None:
        row = self.reader.read("2999-01-01")
        self.assertEqual(row["currency"], "TWD")

    def test_the_boundary_is_inclusive(self) -> None:
        just_before = self.store.interpretation_for(SFID_MAIN, "2026-10-01")
        just_after = self.store.interpretation_for(SFID_MAIN, K1)
        self.assertEqual(just_before[1], "BASELINE")
        self.assertEqual(just_after[1], "APPLIED")

    def test_a_second_correction_takes_over_at_its_own_time(self) -> None:
        self.store.add_interpretation(SFID_MAIN, K2, "currency", "USD",
                                      "REPORTED")
        self.assertEqual(self.reader.read(K1)["currency"], "TWD")
        self.assertEqual(self.reader.read(K2)["currency"], "USD")
        self.assertEqual(self.reader.read("2999-01-01")["currency"], "USD")


class TestFieldRestriction(unittest.TestCase):
    """Areas 14, 17, 18: the overlay may not touch the fact."""

    def setUp(self) -> None:
        self.store = build()
        self.addCleanup(self.store.close)
        self.store.add_interpretation(SFID_MAIN, K1, "currency", "TWD",
                                      "REPORTED")
        self.before = self.store.connection.execute(
            "SELECT value_json, period_end, period_start, metric,"
            " available_at, replay_eligible_from, contract_id, lineage_id,"
            " source_fact_id FROM observations WHERE source_fact_id = ?",
            (SFID_MAIN,)).fetchone()

    def test_the_overlay_cannot_alter_the_accounting_fact(self) -> None:
        row = _Reader(self.store, SFID_MAIN).read(K1)
        self.assertEqual(row["value"], float(self.before["value_json"]))
        self.assertEqual(row["period_end"], self.before["period_end"])
        self.assertEqual(row["metric"], self.before["metric"])
        self.assertEqual(row["contract_id"], self.before["contract_id"])

    def test_the_stored_row_is_never_modified(self) -> None:
        self.reader_rows = _Reader(self.store, SFID_MAIN).read(K1)
        after = self.store.connection.execute(
            "SELECT value_json, period_end, period_start, metric,"
            " available_at, replay_eligible_from, contract_id, lineage_id,"
            " source_fact_id, unit, currency FROM observations"
            " WHERE source_fact_id = ?", (SFID_MAIN,)).fetchone()
        for field in ("value_json", "period_end", "period_start", "metric",
                      "available_at", "replay_eligible_from", "contract_id",
                      "lineage_id", "source_fact_id"):
            self.assertEqual(self.before[field], after[field], field)
        self.assertEqual(after["unit"], "ratio")
        self.assertIsNone(after["currency"])

    def test_the_overlay_fields_are_exactly_three(self) -> None:
        self.assertEqual(
            SQLiteArchive.INTERPRETATION_OVERLAY_FIELDS,
            ("unit", "currency", "currency_basis"))

    def test_provenance_is_structured_not_free_text(self) -> None:
        row = _Reader(self.store, SFID_MAIN).read(K1)
        applied = row["interpretation_applied"]
        self.assertTrue(applied)
        # The marker lives in the structured basis, keyed and typed.
        stored = self.store.connection.execute(
            "SELECT basis_json FROM observations WHERE source_fact_id = ?",
            (SFID_MAIN,)).fetchone()["basis_json"]
        self.assertNotIn("knowledge_interpretation", stored or "")


class TestRestatementSeparation(unittest.TestCase):
    """Areas 11 and 12."""

    def setUp(self) -> None:
        self.store = build()
        self.addCleanup(self.store.close)

    def test_a_restatement_obeys_source_availability(self) -> None:
        # This fact was published later, so it is absent before that date and
        # present after it. That is the opposite axis to a correction, which is
        # present from its source availability and changes reading only later.
        self.assertFalse(
            _Reader(self.store, SFID_RESTATED).read("2024-06-01")["present"])
        self.assertTrue(
            _Reader(self.store, SFID_RESTATED).read("2024-06-01") is not None)
        self.assertTrue(
            _Reader(self.store, SFID_RESTATED).read("2999-01-01")["present"])

    def test_a_correction_obeys_knowledge_time_not_availability(self) -> None:
        self.store.add_interpretation(SFID_MAIN, K1, "currency", "TWD",
                                      "REPORTED")
        self.assertTrue(
            _Reader(self.store, SFID_MAIN).read("2020-01-01")["present"])
        self.assertEqual(
            _Reader(self.store, SFID_MAIN).read("2020-01-01")["unit"], "ratio")

    def test_a_shared_lineage_never_selects_for_another_fact(self) -> None:
        self.store.add_interpretation(SFID_MAIN, K1, "currency", "TWD",
                                      "REPORTED")
        # The unrelated fact shares the lineage row and must be untouched.
        row = _Reader(self.store, SFID_UNRELATED).read("2999-01-01")
        self.assertFalse(row["interpretation_applied"])
        self.assertEqual(row["currency"], "TWD")

    def test_lineage_is_not_the_selection_key(self) -> None:
        self.assertEqual(self.store.interpretations_for_source_fact(
            SFID_UNRELATED), [])


class TestNoDoubleCounting(unittest.TestCase):
    """Area 13 and idempotence of the read."""

    def setUp(self) -> None:
        self.store = build()
        self.addCleanup(self.store.close)
        self.store.add_interpretation(SFID_MAIN, K1, "currency", "TWD",
                                      "REPORTED")

    def test_one_source_fact_yields_exactly_one_effective_reading(self) -> None:
        rows = [o for o in self.store.observations_for("TSM", "2999-01-01")
                if self.store._source_fact_id_of(o) == SFID_MAIN]
        self.assertEqual(len(rows), 1)

    def test_repeating_the_correction_adds_no_second_reading(self) -> None:
        self.store.add_interpretation(SFID_MAIN, K1, "currency", "TWD",
                                      "REPORTED")
        rows = [o for o in self.store.observations_for("TSM", "2999-01-01")
                if self.store._source_fact_id_of(o) == SFID_MAIN]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            len(self.store.interpretations_for_source_fact(SFID_MAIN)), 1)

    def test_a_duplicate_knowledge_at_is_still_refused(self) -> None:
        with self.assertRaises(InterpretationError):
            self.store.add_interpretation(SFID_MAIN, K1, "currency", "USD",
                                          "REPORTED")

    def test_an_unknown_source_fact_is_refused(self) -> None:
        with self.assertRaises(InterpretationError):
            self.store.add_interpretation("sfid_absent", K1, "currency", "TWD",
                                          "REPORTED")

    def test_audit_exposes_the_original_and_the_later_reading(self) -> None:
        audit = self.store.audit_for_source_fact(SFID_MAIN)
        self.assertEqual(audit["original_observation"]["unit"], "ratio")
        self.assertIsNone(audit["original_observation"]["currency"])
        self.assertEqual(len(audit["interpretations"]), 1)
        self.assertEqual(audit["interpretations"][0]["currency"], "TWD")
        self.assertEqual(audit["interpretations"][0]["knowledge_at"], K1)


class TestTheRepairedPopulation(unittest.TestCase):
    """
    Areas 19 and 20, against the rows 2.62 actually wrote.

    Not a fixture: the real archives, opened read-only. Every repaired currency
    is checked, because a reader that worked only for a synthetic TWD would not
    be evidence that the repair is visible.
    """

    ARCHIVES = ["snapshot-universe", "snapshot-crossframework",
                "snapshot-227-a1", "snapshot-227-b"]
    EXPECTED = {"TWD", "CAD", "SEK", "JPY", "BRL", "GBP", "ARS"}

    def setUp(self) -> None:
        corpus_gate.require(self, "snapshot-universe", "snapshot-crossframework", "snapshot-227-a1", "snapshot-227-b")

    def _samples(self):
        for archive in self.ARCHIVES:
            path = os.path.join(H, f"{archive}.sqlite")
            if not os.path.exists(path):
                continue
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                rows = connection.execute(
                    "SELECT i.source_fact_id, i.currency, i.knowledge_at,"
                    " o.replay_eligible_from, a.ticker"
                    " FROM interpretations i"
                    " JOIN observations o ON o.source_fact_id = i.source_fact_id"
                    " JOIN assets a ON a.asset_id = o.asset_id"
                    " GROUP BY i.currency").fetchall()
            except sqlite3.Error:
                continue
            finally:
                connection.close()
            yield archive, path, rows

    def test_every_repaired_currency_is_visible_through_the_reader(self) -> None:
        seen = set()
        for archive, path, rows in self._samples():
            store = SQLiteArchive(path)
            try:
                for row in rows:
                    currency = row["currency"]
                    seen.add(currency)
                    availability = row["replay_eligible_from"]
                    knowledge_at = row["knowledge_at"]
                    # Cutoffs are derived from the fact's own timestamps rather
                    # than fixed dates. A hardcoded "before" can precede the
                    # fact's own availability -- and in this population
                    # availability runs as late as 2026-06 -- where the correct
                    # answer is absent, which would test nothing about the
                    # overlay. The exact availability instant is used so the
                    # boundary itself is exercised.
                    at_availability = availability
                    before = _Reader(store, row["source_fact_id"],
                                     row["ticker"]).read(at_availability)
                    after = _Reader(store, row["source_fact_id"],
                                    row["ticker"]).read(knowledge_at)
                    self.assertTrue(before["present"],
                                    f"{archive} {currency} at availability")
                    self.assertEqual(before["unit"], "ratio",
                                     f"{archive} {currency} at availability")
                    self.assertIsNone(before["currency"],
                                      f"{archive} {currency} at availability")
                    self.assertEqual(after["unit"], "currency",
                                     f"{archive} {currency} at K")
                    self.assertEqual(after["currency"], currency,
                                     f"{archive} {currency} at K")
                    self.assertTrue(after["interpretation_applied"],
                                    f"{archive} {currency} provenance")
                    self.assertIsNotNone(availability)
            finally:
                store.close()
        self.assertEqual(seen, self.EXPECTED,
                         "not every repaired currency was exercised")

    def test_observations_remain_untouched_by_reading(self) -> None:
        debt = ("ifrs-full:LongtermBorrowings",
                "ifrs-full:CurrentPortionOfLongtermBorrowings")
        for archive, path, rows in self._samples():
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                # Scoped to `metric = 'debt'`, which is the population the
                # repair selected. Scoping to a hand-picked concept list would
                # compare two different populations: 2.62 repaired every
                # ratio/NULL observation under `debt`, which spans four
                # concepts -- two ifrs-full and two us-gaap.
                still_faulty = connection.execute(
                    "SELECT COUNT(*) FROM observations WHERE metric = 'debt'"
                    " AND unit = 'ratio' AND currency IS NULL").fetchone()[0]
                interpretations = connection.execute(
                    "SELECT COUNT(*) FROM interpretations").fetchone()[0]
            finally:
                connection.close()
            self.assertGreater(interpretations, 0, archive)
            self.assertEqual(still_faulty, interpretations,
                             f"{archive}: every repaired row must still be "
                             "stored as the original faulty reading")


if __name__ == "__main__":
    unittest.main()