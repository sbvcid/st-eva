"""
Availability precision: a date is not an instant, and nothing may make it one.

2.14 reconciled a bulk-built archive against an API-built one and found that
17,043 of 17,043 rows differed in exactly one field. Not the value, not the
period, not the concept -- the availability value, and only because the two
routes disagreed about its *precision*:

    SEC API path   filed date -> "2015-10-28T00:00:00+00:00", basis
                   ACCEPTANCE_DATETIME. The time of day was invented and the
                   basis over-claimed an instant EDGAR does not publish.
    bulk path      filed date -> "2015-10-28", basis UNDECLARED. A date the
                   source *had* published lost its declared-ness entirely.

And because `replay_eligible_from` is the point-in-time boundary, the first of
those made 6,508 of 17,043 facts replayable from a moment before the filer
published them.

The contract the repository already had was right. `AvailabilityBasis` has
carried `FILED_AS_OF_DATE` -- "a provable date whose time of day is not
published" -- since the vocabulary was written, `sec_provider._availability`
already emitted it, and `tests/test_ingestion_aapl.py::test_15` already asserts
that ingestion produces `ACCEPTANCE_DATETIME` or `FILED_AS_OF_DATE`. That test is
gated on `ST_EVA_LIVE=1`, so it does not run, and the only statement of this
contract in the suite was one nobody executes. These tests are the offline
version of it.

The rule under test, in one sentence: **ST-EVA does not raise date-precision
information to an exact timestamp**, and a fact known only by its declared date
becomes replayable when that date is provably elapsed, not at its midnight.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from typing import Any, Dict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from archive import ARCHIVE_FIRST_SEEN, SOURCE_DECLARED  # noqa: E402
from data_contract import (  # noqa: E402
    AvailabilityBasis,
    Observation,
    ObservationSet,
    PRECISION_DATE,
    PRECISION_INSTANT,
    PRECISION_NONE,
    DECLARED_DATE_LAG_DAYS,
    eligibility_for_declared_date,
    end_of_declared_day,
    point_in_time_cutoff,
    start_of_day_after,
)
from sec_bulk import BulkFactsSource  # noqa: E402
from sec_ingest import (  # noqa: E402
    DEFAULT_ACCEPTANCE_PRECISION,
    Ingestor,
)
from sqlite_archive import SQLiteArchive  # noqa: E402


ACCEPTED = AvailabilityBasis.ACCEPTANCE_DATETIME.value
FILED = AvailabilityBasis.FILED_AS_OF_DATE.value
UNDECLARED = AvailabilityBasis.UNDECLARED.value


def observation(**overrides) -> Observation:
    """One filing fact, with a declared availability unless overridden."""
    fields = {
        "observation_id": "ingest|revenue|Revenue|0000000000-26-000001"
                          "|2025-01-01|2025-12-31|USD",
        "metric": "revenue",
        "value": 100.0,
        "unit": "currency",
        "currency": "USD",
        "currency_basis": "REPORTED",
        "period_start": "2025-01-01",
        "period_end": "2025-12-31",
        "as_of": "2025-12-31",
        "available_at": "2026-03-04T17:22:31.000Z",
        "available_at_basis": ACCEPTED,
        "provider": "SecEdgar",
        "source_type": "REGULATORY_FILING",
        "source_url": None,
        "definition": "revenue",
        "methodology": "test",
        "retrieved_at": "2026-09-30T12:00:00+00:00",
    }
    fields.update(overrides)
    return Observation(**fields)


class TestTheVocabularyAlreadyExisted(unittest.TestCase):
    """The basis for a declared date was here before this round."""

    def test_filed_as_of_date_is_a_declared_basis(self):
        self.assertEqual(FILED, "FILED_AS_OF_DATE")
        self.assertIn(FILED, [basis.value for basis in AvailabilityBasis])

    def test_it_is_not_the_same_as_undisclosed(self):
        # The defect was not that a date was stored as undisclosed. It was that
        # the two words meant the same thing to the writer and different things
        # to the reader.
        self.assertNotEqual(FILED, UNDECLARED)


class TestADateIsNotPromotedToAnInstant(unittest.TestCase):
    """`eligibility_for_declared_date` is the whole of the rule."""

    def test_a_declared_date_becomes_eligible_after_the_day(self):
        self.assertEqual(
            "2026-03-06T00:00:00+00:00",
            eligibility_for_declared_date("2026-03-04"),
        )

    def test_the_allowance_for_a_trailing_declared_date_is_named(self):
        # 2.14 found 65 facts whose EDGAR filed-as-of date was one day *earlier*
        # than the acceptance instant -- MU, filed 2020-06-29, accepted
        # 2020-06-30T16:12:44Z. Without the allowance those facts were replayable
        # before EDGAR published them.
        self.assertEqual(1, DECLARED_DATE_LAG_DAYS)
        self.assertEqual(
            "2020-07-01T00:00:00+00:00",
            eligibility_for_declared_date("2020-06-29"),
        )

    def test_a_declared_date_is_not_read_as_its_own_midnight(self):
        # The exact failure: this used to be the eligibility boundary, and it
        # is earlier than any instant the filer could have published at.
        self.assertLess(
            "2026-03-04T00:00:00+00:00",
            eligibility_for_declared_date("2026-03-04"),
        )
        self.assertLess(
            "2026-03-04T20:31:09.000Z",
            eligibility_for_declared_date("2026-03-04"),
        )

    def test_it_clears_a_trailing_declared_date(self):
        # The measured 65 rows, exactly as reconciliation saw them: filed
        # 2020-06-29, accepted 2020-06-30T16:12:44Z. The boundary has to land
        # after the acceptance, or the fact is replayable too early.
        self.assertGreater(
            eligibility_for_declared_date("2020-06-29"),
            "2020-06-30T16:12:44.000Z",
        )
        # And without the allowance it does not, which is why the allowance
        # exists rather than being belt-and-braces.
        self.assertLess(
            start_of_day_after("2020-06-29"),
            "2020-06-30T16:12:44.000Z",
        )

    def test_a_declared_date_time_value_is_also_handled(self):
        # An index that hands over a midnight-stamped value but declares a date
        # is still a date, and the rule must not depend on the string.
        self.assertEqual(
            eligibility_for_declared_date("2026-03-04"),
            eligibility_for_declared_date("2026-03-04T00:00:00+00:00"),
        )

    def test_unparseable_yields_nothing_rather_than_a_guess(self):
        for bad in (None, "", "not-a-date", "2026-13-40"):
            self.assertIsNone(eligibility_for_declared_date(bad), bad)
            self.assertIsNone(start_of_day_after(bad), bad)

    def test_it_does_not_pretend_to_be_precise_to_the_microsecond(self):
        # A day has no last instant at second resolution, so the boundary is
        # the next day's start rather than an invented 23:59:59.999999.
        self.assertNotIn(".", eligibility_for_declared_date("2026-03-04"))


class TestArchiveEligibilityFollowsPrecision(unittest.TestCase):
    """`replay_eligible_from` is derived from the declared basis."""

    def setUp(self) -> None:
        self.directory = tempfile.mkdtemp()
        self.store = SQLiteArchive(os.path.join(self.directory, "a.sqlite"))

    def tearDown(self) -> None:
        self.store.close()

    def _eligible(self, obs: Observation):
        return self.store._eligibility_for(
            obs, SOURCE_DECLARED, "2026-09-30T12:00:00+00:00"
        )

    def test_an_acceptance_instant_is_eligible_from_that_instant(self):
        self.assertEqual(
            "2026-03-04T17:22:31.000Z",
            self._eligible(observation()),
        )

    def test_a_declared_date_is_eligible_from_after_the_day(self):
        self.assertEqual(
            "2026-03-06T00:00:00+00:00",
            self._eligible(observation(
                available_at="2026-03-04",
                available_at_basis=FILED,
            )),
        )

    def test_a_declared_date_is_eligible_from_after_the_day_even_when_the_value_carries_a_midnight(self):
        # The exact shape 2.14 measured: a value that *looks* like an instant
        # but was declared as a date. Eligibility follows the declaration.
        self.assertEqual(
            "2026-03-06T00:00:00+00:00",
            self._eligible(observation(
                available_at="2026-03-04T00:00:00+00:00",
                available_at_basis=FILED,
            )),
        )

    def test_archive_first_seen_is_still_the_archives_own_clock(self):
        self.assertEqual(
            "2026-09-30T12:00:00+00:00",
            self.store._eligibility_for(
                observation(available_at=None, available_at_basis=UNDECLARED),
                ARCHIVE_FIRST_SEEN,
                "2026-09-30T12:00:00+00:00",
            ),
        )

    def test_a_declared_date_stays_source_declared(self):
        # Precision must not demote the class: the source did declare something,
        # and demoting it would turn a real date into an observational one.
        self.assertEqual(
            SOURCE_DECLARED,
            self.store._class_for(
                observation(
                    available_at="2026-03-04", available_at_basis=FILED
                ),
                "2026-09-30T12:00:00+00:00",
            ),
        )

    def test_stored_row_records_the_derived_boundary(self):
        self.store.record_observation(
            asset="TESTCO",
            observation=observation(
                available_at="2026-03-04", available_at_basis=FILED
            ),
        )
        row = self.store.connection.execute(
            "SELECT available_at, available_at_basis, availability_class,"
            " replay_eligible_from FROM observations WHERE metric = 'revenue'"
        ).fetchone()
        self.assertEqual("2026-03-04", row["available_at"])
        self.assertEqual(FILED, row["available_at_basis"])
        self.assertEqual(SOURCE_DECLARED, row["availability_class"])
        self.assertEqual(
            "2026-03-06T00:00:00+00:00", row["replay_eligible_from"]
        )
        # And the value is not promoted anywhere in the row.
        self.assertNotIn("T", row["available_at"])

    def test_retrieval_time_is_never_the_boundary(self):
        self.store.record_observation(
            asset="TESTCO",
            observation=observation(
                available_at="2026-03-04",
                available_at_basis=FILED,
                retrieved_at="2026-09-30T12:00:00+00:00",
            ),
        )
        row = self.store.connection.execute(
            "SELECT replay_eligible_from, retrieved_at FROM observations"
            " WHERE metric = 'revenue'"
        ).fetchone()
        self.assertNotEqual(
            row["retrieved_at"], row["replay_eligible_from"]
        )


class TestBothPointInTimePathsAgree(unittest.TestCase):
    """
    The repository has two point-in-time implementations.

    One compares `replay_eligible_from` in SQL, the other compares dates in
    memory. Before this round they answered "when was this knowable" differently
    for date-precision facts, which would have given a corpus two answers
    depending on which code path asked.
    """

    def setUp(self) -> None:
        self.directory = tempfile.mkdtemp()
        self.store = SQLiteArchive(os.path.join(self.directory, "a.sqlite"))
        self.store.record_observation(
            asset="TESTCO",
            observation=observation(
                available_at="2026-03-04", available_at_basis=FILED
            ),
        )
        self.store.connection.commit()

    def tearDown(self) -> None:
        self.store.close()

    def _sql_count(self, cutoff: str) -> int:
        at = point_in_time_cutoff(cutoff)
        if at is None:
            return 0
        connection = sqlite3.connect(self.store.path)
        try:
            return connection.execute(
                "SELECT COUNT(*) FROM observations o"
                " JOIN assets a ON a.asset_id = o.asset_id"
                " WHERE a.ticker = 'TESTCO'"
                " AND o.replay_eligible_from IS NOT NULL"
                " AND o.replay_eligible_from <= ?",
                (at,),
            ).fetchone()[0]
        finally:
            connection.close()

    def _memory_count(self, cutoff: str) -> int:
        observations = ObservationSet("TESTCO")
        observations.add(observation(
            available_at="2026-03-04", available_at_basis=FILED
        ))
        return len(observations.knowable_at(cutoff))

    def test_not_knowable_on_the_declared_day(self):
        for cutoff in ("2026-03-04", "2026-03-04T00:00:00+00:00",
                       "2026-03-04T23:59:59+00:00", "2026-03-05",
                       "2026-03-05T23:59:59+00:00"):
            self.assertEqual(0, self._sql_count(cutoff), cutoff)
            self.assertEqual(0, self._memory_count(cutoff), cutoff)

    def test_knowable_once_the_declared_day_has_elapsed(self):
        for cutoff in ("2026-03-06", "2026-03-06T00:00:00+00:00",
                       "2026-04-01T00:00:00+00:00"):
            self.assertEqual(1, self._sql_count(cutoff), cutoff)
            self.assertEqual(1, self._memory_count(cutoff), cutoff)

    def test_the_two_paths_answer_identically(self):
        for cutoff in ("2026-03-04", "2026-03-04T12:00:00+00:00",
                       "2026-03-05", "2026-03-05T12:00:00+00:00",
                       "2026-03-06", "2026-06-01"):
            self.assertEqual(
                self._sql_count(cutoff), self._memory_count(cutoff), cutoff
            )

    def test_an_acceptance_instant_is_unchanged_by_all_of_this(self):
        # The rule must not move facts that were already exact.
        observations = ObservationSet("TESTCO")
        observations.add(observation())
        self.assertEqual(1, len(observations.knowable_at("2026-03-04")))
        self.assertEqual(
            0, len(observations.knowable_at("2026-03-03"))
        )


class TestIngestorReadsTheDeclarationsRatherThanTheStrings(unittest.TestCase):
    """`_availability_for` is the ingestion-layer half of the contract."""

    def setUp(self) -> None:
        self.directory = tempfile.mkdtemp()
        self.store = SQLiteArchive(os.path.join(self.directory, "a.sqlite"))
        self.ingestor = Ingestor(self.store, object(), object())

    def tearDown(self) -> None:
        self.store.close()

    def test_a_declared_acceptance_instant(self):
        self.assertEqual(
            ("2026-03-04T17:22:31.000Z", ACCEPTED, PRECISION_INSTANT),
            self.ingestor._availability_for(
                {"accn": "A", "filed": "2026-03-04"},
                {"A": ("2026-03-04T17:22:31.000Z", PRECISION_INSTANT)},
            ),
        )

    def test_a_declared_date_stays_a_date(self):
        self.assertEqual(
            ("2026-03-04", FILED, PRECISION_DATE),
            self.ingestor._availability_for(
                {"accn": "A", "filed": "2026-03-04"},
                {"A": ("2026-03-04", PRECISION_DATE)},
            ),
        )

    def test_a_filed_date_fallback_is_a_date_and_never_a_midnight(self):
        # The exact 2.14 defect: `f"{filed}T00:00:00+00:00"` labelled
        # ACCEPTANCE_DATETIME, on 8,825 of 17,043 rows.
        value, basis, precision = self.ingestor._availability_for(
            {"accn": "A", "filed": "2015-10-28"}, {"A": None}
        )
        self.assertEqual("2015-10-28", value)
        self.assertNotIn("T", value)
        self.assertEqual(FILED, basis)
        self.assertEqual(PRECISION_DATE, precision)

    def test_an_accession_with_no_acceptance_and_no_filed_date_is_undeclared(self):
        self.assertEqual(
            (None, UNDECLARED, PRECISION_NONE),
            self.ingestor._availability_for({"accn": "A"}, {"A": None}),
        )

    def test_the_retrieval_time_is_never_consulted(self):
        value, basis, precision = self.ingestor._availability_for(
            {"accn": "A"}, {"A": None}
        )
        self.assertIsNone(value)
        self.assertEqual(UNDECLARED, basis)
        self.assertEqual(PRECISION_NONE, precision)


class TestACutoffIsReadAsTheQuestionItAsks(unittest.TestCase):
    """
    "As of 2026-03-05" means the whole of that day.

    The SQL selector compared stored strings, where a bare date sorts before
    every instant of that day, so it read a date cutoff as midnight and excluded
    a fact whose eligibility was that day. The in-memory selector compares dates
    and included it. 2.14 introduced eligibility values that land exactly on
    midnight, which is what turned a latent disagreement into a live one.
    """

    def test_a_bare_date_cutoff_covers_the_whole_day(self):
        self.assertEqual(
            "2026-03-05T23:59:59.999999+00:00",
            point_in_time_cutoff("2026-03-05"),
        )

    def test_an_instant_cutoff_is_left_alone(self):
        for cutoff in (
            "2026-03-05T00:00:00+00:00",
            "2026-03-05T12:30:00Z",
            "2026-03-05 12:30:00",
        ):
            self.assertEqual(cutoff, point_in_time_cutoff(cutoff))

    def test_an_unreadable_cutoff_yields_nothing_rather_than_everything(self):
        for bad in (None, "", "   ", "not-a-cutoff"):
            self.assertIsNone(point_in_time_cutoff(bad), bad)

    def test_end_of_day_is_not_used_on_a_declared_value(self):
        # This normaliser is for a *question*, never for what a source said. A
        # declared date keeps its own precision.
        self.assertEqual(
            "2026-03-05T23:59:59.999999+00:00", end_of_declared_day("2026-03-05")
        )
        self.assertIsNone(end_of_declared_day("nonsense"))


class TestBothSourcesDeclareTheirPrecision(unittest.TestCase):
    """
    The two producers say what they have.

    If either relied on a default, the contract would hold only as long as
    nobody wrote a third adapter.
    """

    def setUp(self) -> None:
        self.directory = tempfile.mkdtemp()

    def test_the_bulk_source_declares_a_date(self):
        # `companyfacts` carries each fact's `filed` date and no time of day.
        document = {
            "cik": "0000000001",
            "entityName": "Test Co",
            "facts": {
                "us-gaap": {
                    "Revenues": {
                        "label": "Revenues",
                        "units": {
                            "USD": [
                                {
                                    "start": "2025-01-01",
                                    "end": "2025-12-31",
                                    "val": 100,
                                    "accn": "0000000001-26-000001",
                                    "fy": 2026,
                                    "fp": "FY",
                                    "form": "10-K",
                                    "filed": "2026-03-04",
                                }
                            ]
                        },
                    }
                }
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            import json

            with open(
                os.path.join(directory, "0000000001.json"), "w", encoding="utf-8"
            ) as handle:
                json.dump(document, handle)
            source = BulkFactsSource(directory)
            entry = source.filing_index("0000000001")[0]
        self.assertEqual(PRECISION_DATE, entry["acceptance_precision"])
        self.assertEqual("2026-03-04", entry["acceptance_datetime"])
        self.assertNotIn("T", entry["acceptance_datetime"])

    def test_the_derived_index_holds_one_entry_per_accession(self):
        """
        One entry per accession that carries a fact -- and no fewer.

        Added because this round broke that loop by one indentation level, which
        silently collapsed a 72-entry index to 50. Nothing failed: the
        observations were identical, because a fact's own `filed` date supplies
        the same answer when the index is missing. Only the filing ledger and the
        reported filing count moved, and only a test that looks at the index
        shape would have said so.
        """
        accessions = [f"0000000001-26-{n:06d}" for n in range(1, 8)]

        def body(shift: int) -> Dict[str, Any]:
            return {
                "units": {
                    "USD": [
                        {
                            "start": "2025-01-01",
                            "end": "2025-12-31",
                            "val": 100.0 + shift,
                            "accn": accessions[index],
                            "form": "10-K",
                            "filed": "2026-03-04",
                        }
                        for index in range(7)
                    ]
                }
            }

        facts = {f"Concept{shift}": body(shift) for shift in range(4)}
        document = {
            "cik": "0000000001",
            "entityName": "Test Co",
            "facts": {"us-gaap": facts},
        }
        with tempfile.TemporaryDirectory() as directory:
            import json

            with open(
                os.path.join(directory, "0000000001.json"), "w", encoding="utf-8"
            ) as handle:
                json.dump(document, handle)
            source = BulkFactsSource(directory)
            index = source.filing_index("0000000001")
        self.assertEqual(len(accessions), len(index))
        self.assertEqual(
            sorted(accessions), sorted(entry["accession"] for entry in index)
        )
        # And every entry carries the declared precision, not just the last one
        # written -- the same loop collapsed both.
        for entry in index:
            self.assertEqual(PRECISION_DATE, entry["acceptance_precision"])
            self.assertEqual("2026-03-04", entry["acceptance_datetime"])

    def test_the_default_is_an_instant_and_is_declared_as_one(self):
        # A source that puts a time in the field is asserting a time; the
        # default is only reached by a source that has not spoken yet.
        self.assertEqual(PRECISION_INSTANT, DEFAULT_ACCEPTANCE_PRECISION)

    def test_an_index_declaring_an_unknown_precision_is_refused(self):
        # A closed vocabulary, and the ingestor raises rather than defaulting.
        # Silently reading an undeclared precision as an instant is how a date
        # becomes a fabricated timestamp in the first place.
        class Provider:
            def resolve_company(self, ticker):
                class Company:
                    cik = "0000000001"
                    name = "Test Co"
                    exchanges = ()
                return Company()

            def submissions(self, cik):
                return {}

            def filing_index(self, cik):
                return [{
                    "accession": "0000000001-26-000001",
                    "form": "10-K",
                    "filing_date": "2026-03-04",
                    "report_date": "2025-12-31",
                    "acceptance_datetime": "2026-03-04",
                    "acceptance_precision": "SOMETIME",
                    "primary_document": "",
                    "is_xbrl": 1,
                }]

            def concept_history(self, cik, taxonomy, concept):
                return None

            def documents_for(self, taxonomy, concept):
                return ()

        store = SQLiteArchive(os.path.join(self.directory, "bad.sqlite"))
        try:
            ingestor = Ingestor(store, Provider(), object())
            with self.assertRaises(ValueError) as caught:
                ingestor.ingest("TESTCO", metrics=("revenue",))
            self.assertIn("SOMETIME", str(caught.exception))
        finally:
            store.close()

    def test_the_precision_vocabulary_is_closed(self):
        from data_contract import PRECISIONS

        self.assertEqual(
            (PRECISION_INSTANT, PRECISION_DATE, PRECISION_NONE), PRECISIONS
        )


if __name__ == "__main__":
    unittest.main()
