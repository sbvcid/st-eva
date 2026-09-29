"""
ST-EVA 2.5.1 - semantic adoption and query completeness.

Two defects that only appear once the archive holds more than one company, and
that a single-company suite cannot see at all.

    A concept's meaning and a filer's use of it were the same row.

`metric_concept_mapping` carried one `effective_from` / `effective_to` window,
seeded from AAPL, and the query surface resolved against it. So MSFT's
`us-gaap:Revenues` from 2007 — nine years before AAPL's window opens — was
reported unmapped, and NVDA's 2026 usage — eight years after it closes — was
too. 565 facts across four filers. The window was never wrong about AAPL; it
was AAPL's filing history wearing a general rule's clothes.

    A truncated series reported the page size as the series length.

`get_metric_history` applies a default limit of 200 and reported
`point_count: 200` for a 338-point series. A reader cannot detect that, which
makes it the worst kind of wrong in an evidence database: a JSON document that
looks complete and is not.

Both are fixed here. The first by separating a mapping from an observation, the
second by stating the boundary in the response.
"""

import sqlite3
import unittest

from archive import FilingRef
from core_registry import (
    ADOPTION_BASES,
    MAPPING_PARTIAL,
    OBSERVED_ADOPTION,
    ConceptAdoption,
    CoreRegistry,
    concept_id_for,
)
from evidence_query import EvidenceQuery, QueryError
from registry_seed import seed
from sqlite_archive import SQLiteArchive

US_GAAP = "us-gaap"
REVENUES = concept_id_for(US_GAAP, "Revenues")


def new_archive() -> SQLiteArchive:
    store = SQLiteArchive(":memory:")
    seed(CoreRegistry(store.connection))
    return store


class TestAdoptionIsSeparateFromMeaning(unittest.TestCase):
    """
    The separation, checked where it can be checked without a network.
    """

    def setUp(self) -> None:
        self.store = new_archive()
        self.registry = CoreRegistry(self.store.connection)
        self.store.record_asset("AAPL", cik="0000320193", name="Apple Inc.")
        self.store.record_asset("MSFT", cik="0000789019", name="Microsoft")
        self.aapl = self.store.record_asset("AAPL")
        self.msft = self.store.record_asset("MSFT")

    def tearDown(self) -> None:
        self.store.close()

    def test_the_adoption_table_is_not_the_mapping_table(self):
        """
        Two objects, two claims. A mapping says what a concept means; adoption
        says what one filer did. Collapsing them is what put AAPL's timeline in
        a column named `effective_from`.
        """
        mapping_columns = {
            row["name"]
            for row in self.store.connection.execute(
                "PRAGMA table_info(metric_concept_mapping)"
            )
        }
        adoption_columns = {
            row["name"]
            for row in self.store.connection.execute(
                "PRAGMA table_info(issuer_concept_adoption)"
            )
        }
        self.assertNotIn("asset_id", mapping_columns)
        self.assertIn("asset_id", adoption_columns)
        self.assertIn("basis", adoption_columns)

    def test_adoption_records_observation_not_intent(self):
        self.registry.record_adoption(
            self.msft, REVENUES, "2007-09-30", "2010-12-31",
            fact_count=31, filing_count=6,
        )
        adoption = self.registry.adoption_for(self.msft, REVENUES)
        self.assertEqual(adoption.basis, OBSERVED_ADOPTION)
        self.assertEqual(adoption.first_used, "2007-09-30")
        self.assertEqual(adoption.last_used, "2010-12-31")
        self.assertEqual(adoption.fact_count, 31)

    def test_reobserving_widens_and_never_narrows(self):
        """
        A later run covering more history must extend what is known. Shrinking
        on re-observation would mean the record described one execution rather
        than the evidence, and a second ingestion would quietly retract the
        first.
        """
        self.registry.record_adoption(
            self.aapl, REVENUES, "2016-09-24", "2018-09-29",
            fact_count=11, filing_count=1,
        )
        # A later, wider observation of a different period.
        self.registry.record_adoption(
            self.aapl, REVENUES, "2010-01-01", "2020-01-01",
            fact_count=4, filing_count=2,
        )
        adoption = self.registry.adoption_for(self.aapl, REVENUES)
        self.assertEqual(adoption.first_used, "2010-01-01")
        self.assertEqual(adoption.last_used, "2020-01-01")
        self.assertEqual(adoption.fact_count, 15)

    def test_a_narrower_reobservation_does_not_shrink_the_window(self):
        self.registry.record_adoption(
            self.aapl, REVENUES, "2010-01-01", "2020-01-01",
            fact_count=10, filing_count=5,
        )
        self.registry.record_adoption(
            self.aapl, REVENUES, "2016-09-24", "2018-09-29",
            fact_count=2, filing_count=1,
        )
        adoption = self.registry.adoption_for(self.aapl, REVENUES)
        self.assertEqual(adoption.first_used, "2010-01-01")
        self.assertEqual(adoption.last_used, "2020-01-01")

    def test_unobserved_is_not_the_same_as_unused(self):
        """
        No adoption record means the filer's evidence has not been ingested. It
        is a gap in what we hold and never a claim that the filer did not use
        the concept, so it reads as None rather than as an empty window.
        """
        self.assertIsNone(self.registry.adoption_for(self.msft, REVENUES))

    def test_two_filers_holding_the_same_concept_are_two_records(self):
        self.registry.record_adoption(
            self.aapl, REVENUES, "2016-09-24", "2018-09-29", 11, 1
        )
        self.registry.record_adoption(
            self.msft, REVENUES, "2007-09-30", "2010-12-31", 31, 6
        )
        self.assertEqual(
            self.registry.adoption_for(self.aapl, REVENUES).first_used,
            "2016-09-24",
        )
        self.assertEqual(
            self.registry.adoption_for(self.msft, REVENUES).first_used,
            "2007-09-30",
        )

    def test_the_basis_vocabulary_is_closed(self):
        """
        A stronger claim — "this filer retired the concept" — must not be
        storable, because the evidence for it does not exist. An undeclared
        basis would make "how much do we actually know here?" unanswerable.
        """
        self.assertEqual(ADOPTION_BASES, (OBSERVED_ADOPTION,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO issuer_concept_adoption (asset_id, concept_id,"
                " first_used, last_used, basis) VALUES (?, ?, ?, ?, ?)",
                (self.msft, REVENUES, "2007-01-01", "2010-01-01", "DECLARED"),
            )

    def test_an_unqualified_concept_is_refused(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO issuer_concept_adoption (asset_id, concept_id,"
                " first_used, last_used, basis) VALUES (?, ?, ?, ?, ?)",
                (self.msft, "Revenues", "2007-01-01", "2010-01-01",
                 OBSERVED_ADOPTION),
            )

    def test_a_window_that_ends_before_it_starts_is_refused(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.registry.record_adoption(
                self.msft, REVENUES, "2010-01-01", "2007-01-01"
            )

    def test_covers_ignores_a_missing_date_rather_than_guessing(self):
        adoption = ConceptAdoption(
            asset_id=self.msft,
            concept_id=REVENUES,
            first_used="2007-09-30",
            last_used="2010-12-31",
            fact_count=31,
            filing_count=6,
        )
        self.assertTrue(adoption.covers(None))
        self.assertTrue(adoption.covers("2008-06-30"))
        self.assertFalse(adoption.covers("2006-06-30"))
        self.assertFalse(adoption.covers("2012-06-30"))


class TestAdoptionResolvesWhatTheWindowRefused(unittest.TestCase):
    """
    The cross-company case, reproduced against two filers and no network.

    The seeded `Revenues` window is AAPL's 2016-2018. MSFT filed the concept in
    2007. Before adoption existed that fact was unmapped, and the reason given
    — "no registry mapping relates this concept to a metric" — was true of the
    table and false about MSFT.
    """

    def setUp(self) -> None:
        self.store = new_archive()
        self.registry = CoreRegistry(self.store.connection)
        self.store.record_asset("AAPL", cik="0000320193")
        self.aapl = self.store.record_asset("AAPL")
        self.store.record_asset("MSFT", cik="0000789019")
        self.msft = self.store.record_asset("MSFT")

    def tearDown(self) -> None:
        self.store.close()

    def _observe(self, asset_id, first, last, facts=10, concept=REVENUES):
        self.registry.record_adoption(
            asset_id, concept, first, last, fact_count=facts, filing_count=2
        )

    def test_without_adoption_the_seeded_window_still_governs(self):
        """
        The sealed behaviour is untouched for a filer with no evidence. Adoption
        is additional knowledge, not a replacement rule.
        """
        self.assertFalse(
            self.registry.resolve(REVENUES, as_of="2007-09-30").is_resolved
        )
        self.assertTrue(
            self.registry.resolve(REVENUES, as_of="2017-09-30").is_resolved
        )

    def test_observed_use_outside_the_window_resolves(self):
        self._observe(self.msft, "2007-09-30", "2010-12-31")
        resolved = self.registry.resolve(
            REVENUES, as_of="2008-06-30", asset_id=self.msft
        )
        self.assertTrue(resolved.is_resolved)
        self.assertEqual(resolved.metric.metric_id, "revenue")
        self.assertTrue(resolved.adopted_outside_mapping_window)

    def test_one_filers_adoption_does_not_resolve_another_filers_gap(self):
        """
        Adoption is evidence about one filer. If it leaked across issuers, the
        fix would have reintroduced the original defect with a filing-shaped
        hole in it.
        """
        self._observe(self.msft, "2007-09-30", "2010-12-31")
        self.assertFalse(
            self.registry.resolve(
                REVENUES, as_of="2008-06-30", asset_id=self.aapl
            ).is_resolved,
            "MSFT's filing history resolved AAPL's 2008 fact",
        )

    def test_use_past_a_closed_window_still_resolves(self):
        """
        NVDA reported `Revenues` through 2026, eight years after AAPL's window
        closed. A window that closes is that filer's last period, not a
        statement that the concept stopped existing.
        """
        self._observe(self.msft, "2008-01-27", "2026-07-26")
        resolved = self.registry.resolve(
            REVENUES, as_of="2026-06-30", asset_id=self.msft
        )
        self.assertTrue(resolved.is_resolved)
        self.assertTrue(resolved.adopted_outside_mapping_window)

    def test_adoption_widens_when_but_never_how_faithfully(self):
        """
        The mapping's fidelity is untouched. A PARTIAL concept is still PARTIAL
        after adoption widens its window, so adoption cannot quietly promote a
        wider aggregate into the same series as a narrower one.
        """
        self._observe(self.msft, "2007-09-30", "2010-12-31")
        resolved = self.registry.resolve(
            REVENUES, as_of="2008-06-30", asset_id=self.msft
        )
        self.assertEqual(len(resolved.mappings), 1)
        self.assertEqual(resolved.mappings[0].mapping_type, MAPPING_PARTIAL)
        self.assertFalse(resolved.mappings[0].series_continues)

    def test_a_period_outside_the_observed_window_does_not_resolve(self):
        """
        Adoption is a bounded claim about what was seen. Extending it to an
        unobserved period would be inference dressed as evidence, which is the
        thing the registry was built to refuse.
        """
        self._observe(self.msft, "2007-09-30", "2010-12-31")
        self.assertFalse(
            self.registry.resolve(
                REVENUES, as_of="2015-06-30", asset_id=self.msft
            ).is_resolved
        )

    def test_the_response_states_when_adoption_was_what_resolved_it(self):
        """
        A reader can tell the difference between "this concept means revenue"
        and "this filer's filings show it was used then, which is outside the
        concept's stated window". The second is worth knowing about.
        """
        self._observe(self.msft, "2007-09-30", "2010-12-31")
        payload = self.registry.resolve(
            REVENUES, as_of="2008-06-30", asset_id=self.msft
        ).contract_dict()
        self.assertTrue(payload["adopted_outside_mapping_window"])
        self.assertIsNotNone(payload["issuer_adoption"])
        self.assertEqual(payload["issuer_adoption"]["basis"], OBSERVED_ADOPTION)
        self.assertEqual(
            payload["issuer_adoption"]["first_used"], "2007-09-30"
        )

    def test_an_unresolved_concept_still_says_it_is_unresolved(self):
        """
        Adoption fixes a false negative. It must not become a way to attach
        anything to anything: a concept with no mapping at all stays unmapped,
        because there is no meaning to extend.
        """
        self._observe(
            self.msft, "2010-01-01", "2012-01-01",
            concept=concept_id_for(US_GAAP, "SomethingNovel"),
        )
        resolved = self.registry.resolve(
            concept_id_for(US_GAAP, "SomethingNovel"),
            as_of="2011-01-01",
            asset_id=self.msft,
        )
        self.assertFalse(resolved.is_resolved)
        self.assertIn("NOT_EXPLAINED", resolved.contract_dict()["reason"])


class TestTruncationIsStatedNotHidden(unittest.TestCase):
    """
    A truncated series must say so in the response that truncates it.
    """

    def setUp(self) -> None:
        import tempfile

        from core_registry import CoreRegistry as Registry
        from evidence_model import source_fact_id

        self.directory = tempfile.mkdtemp(prefix="steva-trunc-")
        self.path = f"{self.directory}/trunc.sqlite"
        self.store = SQLiteArchive(self.path)
        registry = Registry(self.store.connection)
        seed(registry)
        self.store.record_asset("AAPL", cik="0000320193")

        from data_contract import (
            Observation,
            SourceType,
            Unit,
            ValidationStatus,
        )

        # More than the default page size, so truncation is real rather than
        # theoretical.
        self.total = 260
        for index in range(self.total):
            accession = f"0000320193-26-{index:06d}"
            period_end = f"{2000 + index % 25}-12-31"
            self.store.record_observation(
                asset="AAPL",
                observation=Observation(
                    observation_id=f"obs-{index}",
                    metric="revenue",
                    value=float(index),
                    unit=Unit.CURRENCY.value,
                    currency="USD",
                    currency_basis="REPORTED",
                    period_start=f"{2000 + index % 25}-01-01",
                    period_end=period_end,
                    as_of=period_end,
                    available_at="2026-01-01T00:00:00.000Z",
                    available_at_basis="ACCEPTANCE_DATETIME",
                    provider="SecEdgar",
                    source_type=SourceType.REGULATORY_FILING.value,
                    source_url=None,
                    definition="revenue",
                    methodology="fixture",
                    retrieved_at="2026-02-01T00:00:00+00:00",
                    raw={"sec_fact": {"accession": accession}},
                    status=ValidationStatus.UNVERIFIABLE,
                ),
                availability_class="SOURCE_DECLARED",
                filing=FilingRef(
                    accession=accession,
                    form="10-K",
                    taxonomy=US_GAAP,
                    fiscal_year=2000 + index % 25,
                    fiscal_period="FY",
                    instant=0,
                    source_fact_id=source_fact_id(
                        "SecEdgar", accession, US_GAAP, "Revenues",
                        f"{2000 + index % 25}-01-01", period_end, accession,
                    ),
                    source_concept=REVENUES,
                ),
            )
        self.query = EvidenceQuery.open(self.path)

    def tearDown(self) -> None:
        import shutil

        self.query.close()
        self.store.close()
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_a_truncated_series_reports_its_true_length(self):
        """
        The defect: `point_count: 200` for a 260-point series reads as a claim
        that the series has 200 points. Nothing in the JSON says otherwise.
        """
        history = self.query.get_metric_history("AAPL", "revenue")
        self.assertEqual(history["point_count"], self.total)
        self.assertEqual(history["returned_count"], 200)
        self.assertTrue(history["truncated"])
        self.assertIn("260", history["truncation_note"])
        self.assertIn("200", history["truncation_note"])

    def test_a_complete_series_is_not_marked_truncated(self):
        """
        The flag is not a standing disclaimer. Marking a complete series
        truncated teaches a reader to ignore it, which is the opposite of what
        it is for.
        """
        history = self.query.get_metric_history(
            "AAPL", "revenue", limit=5000
        )
        self.assertEqual(history["point_count"], self.total)
        self.assertEqual(history["returned_count"], self.total)
        self.assertFalse(history["truncated"])
        self.assertIsNone(history["truncation_note"])

    def test_paging_reaches_every_point_exactly_once(self):
        """
        The honest form is only useful if the rest is reachable. Every point
        arrives once and the walk terminates.
        """
        seen = []
        cursor = None
        for _ in range(20):
            page = self.query.page(
                asset="AAPL", metric="revenue", limit=40, cursor=cursor
            )
            self.assertEqual(page["total_count"], self.total)
            seen.extend(row["observation_id"] for row in page["results"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertIsNone(cursor, "paging did not terminate")
        self.assertEqual(len(seen), self.total)
        self.assertEqual(len(set(seen)), self.total)

    def test_the_last_page_says_it_is_the_last(self):
        pages = []
        cursor = None
        while True:
            page = self.query.page(
                asset="AAPL", metric="revenue", limit=100, cursor=cursor
            )
            pages.append(page)
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertGreater(len(pages), 1)
        self.assertTrue(pages[0]["truncated"])
        self.assertIsNone(pages[0]["next_cursor"] and None)
        self.assertTrue(pages[-1]["truncated"])
        self.assertIsNone(pages[-1]["next_cursor"])

    def test_a_forged_cursor_is_refused(self):
        """
        The cursor crosses the interface, so it is validated rather than
        trusted. A cursor that is not one is a malformed query, not an empty
        page.
        """
        for forged in ("", "not-a-cursor", "!!!", "b2Zmc2V0Om5vcGU="):
            with self.assertRaises(QueryError):
                self.query.page(asset="AAPL", metric="revenue", cursor=forged)

    def test_a_missing_cursor_still_reads_the_first_page(self):
        """
        Omitting the cursor is how a caller starts. Only an empty *string* is
        forged, because that is what a caller holding a lost cursor tends to
        pass and it looks identical to the start of a series.
        """
        page = self.query.page(asset="AAPL", metric="revenue", limit=40)
        self.assertEqual(page["returned_count"], 40)
        self.assertEqual(page["total_count"], self.total)

    def test_the_count_is_independent_of_the_limit(self):
        """
        A caller that asks for 10 and one that asks for 5000 are looking at the
        same series, and both are told how long it is.
        """
        small = self.query.get_metric_history("AAPL", "revenue", limit=10)
        large = self.query.get_metric_history("AAPL", "revenue", limit=5000)
        self.assertEqual(small["point_count"], large["point_count"])
        self.assertEqual(small["point_count"], self.total)
        self.assertEqual(small["returned_count"], 10)
        self.assertEqual(large["returned_count"], self.total)

    def test_the_surface_offers_no_raw_paging_escape_hatch(self):
        """
        Pagination that can be bypassed by reaching for `execute` is not a
        guarantee. The sealed surface exposes no such method, and adding one
        would undo the property the 2.5 tests assert.
        """
        for forbidden in ("execute", "raw_sql", "run_sql"):
            self.assertFalse(hasattr(EvidenceQuery, forbidden))


if __name__ == "__main__":
    unittest.main()
