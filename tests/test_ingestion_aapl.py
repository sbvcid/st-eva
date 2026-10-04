"""
ST-EVA 2.5.1 - incremental ingestion, AAPL vertical slice.

The acceptance property is that a second identical run changes nothing and
downloads nothing. Everything else here is what that property depends on.

Live ingestion is opt-in, because it spends a fair-access source's budget and
a deterministic suite should not depend on a network. The identity and registry
logic is tested offline against the same rules, so a regression is caught
without a request.
"""

import os
import sqlite3
import unittest
from pathlib import Path

from archive import FilingRef
from core_registry import (
    ConceptMapping,
    MAPPING_PARTIAL,
    CoreRegistry,
    concept_id_for,
)
from evidence_model import source_fact_id
from evidence_query import EvidenceQuery
from registry_seed import seed
from sec_ingest import DEFAULT_METRICS, SEC_SOURCE, Ingestor
from sqlite_archive import SQLiteArchive

US_GAAP = "us-gaap"
AAPL = "AAPL"
LIVING = os.environ.get("ST_EVA_LIVE") == "1"


def new_archive() -> SQLiteArchive:
    store = SQLiteArchive(":memory:")
    seed(CoreRegistry(store.connection))
    return store


class TestSourceFactIdentity(unittest.TestCase):
    """
    A fact's identity is its position in a filing, not its value.

    Two filings reporting the same number, or the same fact reported by two
    adapters, must resolve the way the rules say and not by coincidence.
    """

    def test_the_same_fact_gets_the_same_id(self):
        first = source_fact_id(
            "SecEdgar", "sha256:doc", US_GAAP, "Assets",
            None, "2026-06-27", "0000320193-26-000001",
        )
        second = source_fact_id(
            "SecEdgar", "sha256:doc", US_GAAP, "Assets",
            None, "2026-06-27", "0000320193-26-000001",
        )
        self.assertEqual(first, second)

    def test_identity_ignores_the_value(self):
        """A restatement is a different fact, not the same fact re-valued."""
        before = source_fact_id(
            "SecEdgar", "sha256:a", US_GAAP, "NetIncomeLoss",
            "2025-01-01", "2025-12-31", "acc-1",
        )
        after = source_fact_id(
            "SecEdgar", "sha256:b", US_GAAP, "NetIncomeLoss",
            "2025-01-01", "2025-12-31", "acc-2",
        )
        self.assertNotEqual(before, after)

    def test_different_sources_never_share_a_fact(self):
        filing = source_fact_id(
            "SecEdgar", "sha256:doc", US_GAAP, "Assets",
            None, "2026-06-27", "acc-1",
        )
        vendor = source_fact_id(
            "YahooFinance", "sha256:doc", US_GAAP, "Assets",
            None, "2026-06-27", "acc-1",
        )
        self.assertNotEqual(filing, vendor)

    def test_different_concepts_never_share_a_fact(self):
        one = source_fact_id(
            "SecEdgar", "sha256:doc", US_GAAP, "LongTermDebtNoncurrent",
            None, "2026-06-27", "acc-1",
        )
        two = source_fact_id(
            "SecEdgar", "sha256:doc", US_GAAP, "LongTermDebtCurrent",
            None, "2026-06-27", "acc-1",
        )
        self.assertNotEqual(one, two)

    def test_different_dimensions_never_share_a_fact(self):
        """
        The same concept, period and unit under two different contexts is two
        facts. An aggregated endpoint hides the dimension, so the context has to
        be in the identity.
        """
        consolidated = source_fact_id(
            "SecEdgar", "sha256:doc", US_GAAP, "Revenue",
            "2026-01-01", "2026-03-31", "acc-1",
        )
        segment = source_fact_id(
            "SecEdgar", "sha256:doc", US_GAAP, "Revenue",
            "2026-01-01", "2026-03-31", "acc-1-ctx2",
        )
        self.assertNotEqual(consolidated, segment)

    def test_identity_is_stable_across_processes(self):
        """A pure function of its inputs, so a re-run reproduces it exactly."""
        self.assertTrue(
            source_fact_id("s", "d", US_GAAP, "Assets", None, "x", "y").startswith(
                "sfid_"
            )
        )


class TestSourceConceptIsNotSemanticMetric(unittest.TestCase):
    def test_the_two_are_separate_columns(self):
        store = new_archive()
        try:
            columns = {
                row["name"]
                for row in store.connection.execute(
                    "PRAGMA table_info(observations)"
                )
            }
            self.assertIn("source_concept_ref", columns)
            self.assertIn("metric", columns)
        finally:
            store.close()

    @staticmethod
    def _archive_one(store, observation_id, filing=None):
        """
        Store one observation the way the rest of the system does.

        Built through `record_observation` rather than raw SQL, so the asset,
        lineage and content-hash rows the foreign keys require exist and the test
        is about the concept column rather than about hand-written inserts.
        """
        from data_contract import (
            Observation,
            SourceType,
            Unit,
            ValidationStatus,
        )

        store.record_asset(AAPL, cik="0000320193", name="Apple Inc.")
        store.record_observation(
            asset=AAPL,
            observation=Observation(
                observation_id=observation_id,
                metric="revenue",
                value=1.0,
                unit=Unit.CURRENCY.value,
                currency="USD",
                currency_basis="REPORTED",
                period_start="2025-01-01",
                period_end="2025-12-31",
                as_of="2025-12-31",
                available_at="2026-01-01T00:00:00.000Z",
                available_at_basis="ACCEPTANCE_DATETIME",
                provider="SecEdgar",
                source_type=SourceType.REGULATORY_FILING.value,
                source_url=None,
                definition="revenue",
                methodology="fixture",
                retrieved_at="2026-02-01T00:00:00+00:00",
                raw={},
                status=ValidationStatus.UNVERIFIABLE,
            ),
            availability_class="SOURCE_DECLARED",
            filing=filing,
        )

    def test_a_bare_word_is_refused_as_a_source_concept(self):
        """
        A bare word is a metric name. Accepting one here is how a semantic
        metric ends up recorded as a filing concept, so the database refuses it
        rather than leaving it to be noticed downstream.
        """
        store = new_archive()
        try:
            with self.assertRaises(sqlite3.IntegrityError) as caught:
                self._archive_one(
                    store, "obs-bare", FilingRef(source_concept="revenue")
                )
            self.assertIn("taxonomy:concept", str(caught.exception))
        finally:
            store.close()

    def test_a_qualified_concept_is_accepted(self):
        store = new_archive()
        try:
            self._archive_one(
                store,
                "obs-qualified",
                FilingRef(source_concept="us-gaap:Revenues", taxonomy="us-gaap"),
            )
            row = store.connection.execute(
                "SELECT metric, source_concept_ref FROM observations"
            ).fetchone()
            self.assertEqual(row["metric"], "revenue")
            self.assertEqual(row["source_concept_ref"], "us-gaap:Revenues")
        finally:
            store.close()

    def test_a_null_concept_means_no_filing_concept(self):
        """
        Not "unknown". A vendor aggregate has no filing concept, and a null says
        that rather than leaving the two indistinguishable.
        """
        store = new_archive()
        try:
            self._archive_one(
                store, "obs-null-concept", FilingRef(accession="0000320193-26-1")
            )
            row = store.connection.execute(
                "SELECT source_concept_ref, accession FROM observations"
            ).fetchone()
            self.assertIsNone(row["source_concept_ref"])
            self.assertEqual(row["accession"], "0000320193-26-1")
        finally:
            store.close()


class TestCrossSourceIsNeverMerged(unittest.TestCase):
    def test_the_same_value_from_two_sources_stays_two_observations(self):
        from data_contract import (
            Observation,
            SourceType,
            Unit,
            ValidationStatus,
        )

        store = new_archive()
        try:
            store.record_asset(AAPL, cik="0000320193")
            for provider in ("SecEdgar", "YahooFinance"):
                store.record_observation(
                    asset=AAPL,
                    observation=Observation(
                        observation_id=f"obs-{provider}",
                        metric="revenue",
                        value=466_823_000_000.0,
                        unit=Unit.CURRENCY.value,
                        currency="USD",
                        currency_basis="REPORTED",
                        period_start="2025-06-29",
                        period_end="2026-06-27",
                        as_of="2026-06-27",
                        available_at="2026-07-31T10:01:02.000Z",
                        available_at_basis="ACCEPTANCE_DATETIME",
                        provider=provider,
                        source_type=SourceType.API_LIVE.value,
                        source_url=None,
                        definition="revenue",
                        methodology="m",
                        retrieved_at="2026-08-01T00:00:00+00:00",
                        raw={},
                        status=ValidationStatus.UNVERIFIABLE,
                    ),
                )
            store.connection.commit()
            rows = store.connection.execute(
                "SELECT observation_id, provider, value_json FROM observations"
            ).fetchall()
            self.assertEqual(len(rows), 2, "two sources collapsed into one")
            self.assertEqual(
                {row["provider"] for row in rows},
                {"SecEdgar", "YahooFinance"},
            )
            self.assertEqual(
                {row["value_json"] for row in rows}, {"466823000000.0"}
            )
        finally:
            store.close()


class TestConceptEvolutionIsNotSpliced(unittest.TestCase):
    """
    The registry's job, checked through the mapping rules rather than a
    network call. A name match would splice these into one series.
    """

    def setUp(self) -> None:
        self.store = new_archive()
        self.registry = CoreRegistry(self.store.connection)

    def tearDown(self) -> None:
        self.store.close()

    def test_revenue_breaks_where_a_mapped_concept_ends(self):
        """
        The two legacy revenue presentations that remain declared each break the
        series, and the contract-revenue line does not.

        `us-gaap:Revenues` is deliberately absent: 2.99 retired it, because
        2.98R proved it a broader earning-process measure than `revenue` and so
        never a valid PARTIAL source. It is no longer a source, so it is no
        longer a break, and this test now asserts that rather than pretending the
        retirement did not happen.
        """
        breaks = {
            item["concept_id"] for item in self.registry.series_breaks("revenue")
        }
        self.assertNotIn(concept_id_for(US_GAAP, "Revenues"), breaks)
        self.assertIn(
            concept_id_for(US_GAAP, "SalesRevenueNet"), breaks
        )
        self.assertNotIn(
            concept_id_for(
                US_GAAP, "RevenueFromContractWithCustomerExcludingAssessedTax"
            ),
            breaks,
        )

    def test_the_revenue_concept_overlap_is_covered_by_both_windows(self):
        """
        `Revenues` and the contract concept overlapped for two quarters of
        FY2018. A series crossing that overlap would splice a broader measure
        into a narrower one.

        That overlap is a historical window condition, and the mapping carrying it
        was retired by 2.99 because the *semantic* relation was invalid -- being
        BROADER_THAN_TARGET relative to `revenue`. So the window is reproduced
        here as a test-local mapping: the property under test is temporal overlap,
        not the correctness of the retired relation, and no scope is invented so
        2.74 still refuses to resolve it.
        """
        self.store.connection.execute(
            "INSERT OR IGNORE INTO concept_registry"
            " (concept_id, taxonomy, concept, label, source_definition)"
            " VALUES (?, ?, ?, ?, NULL)",
            (concept_id_for(US_GAAP, "Revenues"), US_GAAP, "Revenues",
             "Revenues"),
        )
        self.store.connection.commit()
        self.registry.add_mapping(ConceptMapping(
            concept_id=concept_id_for(US_GAAP, "Revenues"),
            metric_id="revenue",
            mapping_type="PARTIAL",
            relation_kind="IDENTITY",
            effective_from="2016-09-24",
            effective_to="2018-09-29",
        ))
        by_concept = {}
        for mapping in self.registry.mappings_for_metric("revenue"):
            by_concept.setdefault(mapping.concept_id, []).append(mapping)
        revenues = by_concept[concept_id_for(US_GAAP, "Revenues")][0]
        contract = by_concept[
            concept_id_for(
                US_GAAP, "RevenueFromContractWithCustomerExcludingAssessedTax"
            )
        ][0]
        self.assertTrue(revenues.effective_to >= "2018-06-30")
        self.assertLessEqual(revenues.effective_to, "2018-09-29")
        self.assertGreaterEqual(contract.effective_from, "2017-09-30")
        self.assertFalse(revenues.series_continues)
        self.assertTrue(contract.series_continues)

    def test_a_concept_only_maps_in_its_own_window(self):
        for when, expected in (
            ("2010-01-01", "us-gaap:SalesRevenueNet"),
            ("2020-01-01",
             "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"),
        ):
            resolved = self.registry.resolve(expected, as_of=when)
            self.assertTrue(
                resolved.is_resolved, f"{expected} did not resolve at {when}"
            )
            # Filing concepts only: `vendor:trailingTotalRevenue` is a real
            # mapping with no window, and asking for filings is what makes the
            # "only one concept speaks in this period" claim true rather than
            # an accident of a second mapping being absent.
            older = [
                m.concept_id
                for m in self.registry.mappings_for_metric("revenue", as_of=when)
                if m.concept_id.startswith("us-gaap:")
            ]
            self.assertEqual(older, [expected])

    def test_capex_definitions_still_differ(self):
        exact = self.registry.concept(
            concept_id_for(US_GAAP, "PaymentsToAcquirePropertyPlantAndEquipment")
        )
        partial = self.registry.concept(
            concept_id_for(US_GAAP, "PaymentsToAcquireProductiveAssets")
        )
        self.assertNotIn("intangible", (exact.source_definition or "").lower())
        self.assertIn("intangible", (partial.source_definition or "").lower())
        breaks = self.registry.series_breaks("capex")
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0]["mapping_type"], MAPPING_PARTIAL)

    def test_an_unknown_concept_is_not_assigned_to_the_nearest_metric(self):
        for concept in (
            "us-gaap:Revenueish", "us-gaap:NetRevenueish", "revenue",
            "vendor:revenueish",
        ):
            self.assertIsNone(
                self.registry.resolve(concept).metric,
                f"{concept} was assigned a metric by name",
            )


class TestIngestorNeedsAFilingIndex(unittest.TestCase):
    def test_an_unresolvable_ticker_ingests_nothing(self):
        """
        An unresolvable ticker is a *classified* outcome, not an exception.

        The claim this test has always made is that an unresolvable ticker
        ingests nothing, and that is still asserted. What changed in 2.11 is the
        shape of the report, and for a reason that only appears at population
        scale: **a raise ends the run.** A hundred-issuer pass that hits one bad
        name on issuer three leaves ninety-seven unclassified, and the report
        says only which ticker stopped it — which is the opposite of the
        acceptance criterion for the round, that every failure carries a kind.

        So the run reports `ISSUER_UNRESOLVED` and carries on, and the test
        pins the classification as well as the absence of data. Nothing is
        loosened: an exception would have been *easier* to assert, and would
        have been the wrong contract.
        """
        from sec_ingest import OUTCOME_ISSUER_UNRESOLVED

        store = new_archive()

        class NoIndex:
            def resolve_company(self, ticker):
                return None

        try:
            report = Ingestor(
                store, NoIndex(), CoreRegistry(store.connection)
            ).ingest("NOT_A_TICKER")
            self.assertEqual(report.outcome, OUTCOME_ISSUER_UNRESOLVED)
            self.assertEqual(report.observations_stored, 0)
            self.assertEqual(
                [f["subject"] for f in report.failures], ["NOT_A_TICKER"]
            )
            self.assertEqual(
                store.connection.execute(
                    "SELECT COUNT(*) AS n FROM held_filings"
                ).fetchone()["n"],
                0,
            )
            # And no asset was created either, because an issuer we cannot
            # resolve is not an issuer we know anything about.
            self.assertEqual(
                store.connection.execute(
                    "SELECT COUNT(*) AS n FROM assets"
                ).fetchone()["n"],
                0,
            )
        finally:
            store.close()

    def test_a_second_run_makes_no_concept_fetches_when_nothing_is_new(self):
        """
        With a stale index and nothing new accepted, the run must not download
        a single document.

        This is the property that makes repeated ingestion defensible against a
        source that asks callers to be considerate, and it is asserted without a
        network by handing the ingestor an index it has already seen.
        """
        store = new_archive()
        registry = CoreRegistry(store.connection)

        class Index:
            def __init__(self):
                self.entry = {
                    "accession": "0000320193-26-000001",
                    "form": "10-Q",
                    "filing_date": "2026-05-01",
                    "report_date": "2026-03-28",
                    "acceptance_datetime": "2026-05-01T16:01:00Z",
                    "primary_document": "aapl-20260328.htm",
                    "is_xbrl": 1,
                }
                self.fetches = 0

            def filing_index(self, cik):
                self.fetches += 1
                return [dict(self.entry)]

            def resolve_company(self, ticker):
                class C:
                    cik = "0000320193"
                    name = "Apple Inc."
                    ticker = "AAPL"
                return C()

            @property
            def network_fetches(self):
                return self.fetches

            @property
            def concept_fetches(self):
                return 0

            def concept_history(self, *args):
                raise AssertionError(
                    "a document was fetched when no new filing was accepted"
                )

        index = Index()
        first = Ingestor(store, index, registry).ingest(AAPL)
        self.assertEqual(first.filings_ingested, 1)
        self.assertEqual(first.concept_fetches, 0, "no documents existed yet")

        second = Ingestor(store, index, registry).ingest(AAPL)
        self.assertEqual(second.filings_ingested, 0)
        self.assertEqual(second.filings_already_held, 1)
        self.assertEqual(second.concept_fetches, 0)
        self.assertFalse(second.changed_anything)
        store.close()


@unittest.skipUnless(LIVING, "the AAPL ingestion needs ST_EVA_LIVE=1")
class TestAapplIngestion(unittest.TestCase):
    """The real thing, once, and everything checked against it."""

    @classmethod
    def setUpClass(cls) -> None:
        import shutil
        import tempfile

        cls.directory = tempfile.mkdtemp(prefix="steva-ingest-")
        cls.archive = os.path.join(cls.directory, "aapl.sqlite")
        cls.store = SQLiteArchive(cls.archive)
        cls.registry = CoreRegistry(cls.store.connection)
        seed(cls.registry)

        from sec_provider import SECProvider

        cls.first = Ingestor(
            cls.store, SECProvider(), cls.registry
        ).ingest(AAPL, metrics=DEFAULT_METRICS)
        cls.second = Ingestor(
            cls.store, SECProvider(), cls.registry
        ).ingest(AAPL, metrics=DEFAULT_METRICS)
        cls.query = EvidenceQuery.open(cls.archive)

    @classmethod
    def tearDownClass(cls) -> None:
        import shutil

        try:
            cls.query.close()
            cls.store.close()
        finally:
            shutil.rmtree(cls.directory, ignore_errors=True)

    # -- 1: first run ----------------------------------------------------

    def test_1_first_ingestion_stores_evidence_with_provenance(self):
        self.assertEqual(self.first.errors, [])
        self.assertGreater(self.first.filings_ingested, 0)
        self.assertGreater(self.first.documents_stored, 0)
        self.assertGreater(self.first.observations_stored, 0)
        self.assertEqual(
            self.first.observations_stored,
            self.first.source_facts_stored,
            "every source fact became exactly one observation",
        )

    def test_1_every_seeded_metric_ingested(self):
        for metric in DEFAULT_METRICS:
            count = self.store.connection.execute(
                "SELECT COUNT(*) AS n FROM observations WHERE metric = ?",
                (metric,),
            ).fetchone()["n"]
            self.assertGreater(count, 0, f"{metric} ingested nothing")

    def test_1_every_ingested_observation_has_a_filing(self):
        """
        Every row is traceable to a filing. A fiscal year is *not* required: an
        8-K reports figures without declaring one, and inventing a value from the
        calendar year would be a fact the filing never made.
        """
        rows = self.store.connection.execute(
            "SELECT accession, form FROM observations"
            " WHERE accession IS NULL OR form IS NULL"
        ).fetchall()
        self.assertEqual(rows, [], "an observation has no filing identity")
        self.assertEqual(
            self.store.connection.execute(
                "SELECT COUNT(*) AS n FROM observations"
                " WHERE source_fact_id IS NULL OR source_concept_ref IS NULL"
            ).fetchone()["n"],
            0,
            "an observation has no source fact or no filing concept",
        )

    def test_1_no_observation_lands_under_an_asset_named_after_an_id(self):
        """
        The evidence has to be findable by ticker. Registering an asset under
        its own asset_id is silent — the rows are all there — and a query by
        ticker then returns nothing, which reads as "we ingested nothing".
        """
        rows = self.store.connection.execute(
            "SELECT ticker, COUNT(*) AS n FROM observations"
            " JOIN assets ON assets.asset_id = observations.asset_id"
            " GROUP BY ticker"
        ).fetchall()
        tickers = {row["ticker"] for row in rows}
        self.assertEqual(tickers, {AAPL})
        self.assertTrue(
            self.query.query_observations(asset=AAPL),
            "the ingested evidence is unreachable by ticker",
        )

    # -- 2: second run ---------------------------------------------------

    def test_2_second_run_is_idempotent(self):
        self.assertEqual(self.second.filings_ingested, 0)
        self.assertEqual(self.second.documents_stored, 0)
        self.assertEqual(self.second.source_facts_stored, 0)
        self.assertEqual(self.second.observations_stored, 0)
        self.assertEqual(self.second.filings_already_held, self.first.filings_seen)
        self.assertFalse(self.second.changed_anything)

    def test_2_second_run_makes_no_unnecessary_fetches(self):
        """
        The criterion is one bounded discovery request and nothing else.

        Zero requests is not achievable and was the wrong target. The submissions
        API *is* the live filing history, so the only way to learn that nothing
        was newly accepted is to ask; skipping that would mean assuming nothing
        changed, which is how an incremental pipeline silently stops ingesting.
        What must hold is that the answer costs one request and re-downloads
        nothing.
        """
        self.assertEqual(
            self.second.concept_fetches,
            0,
            f"re-downloaded documents: {self.second.concept_fetches}",
        )
        self.assertLessEqual(
            self.second.network_fetches,
            2,
            "more requests than the index and the CIK lookup need",
        )

    def test_2_no_new_rows_anywhere(self):
        for table in (
            "observations", "source_documents", "observation_sources",
            "held_filings",
        ):
            before = self.store.connection.execute(
                f"SELECT COUNT(*) AS n FROM {table}"
            ).fetchone()["n"]
            self.assertGreater(before, 0, f"{table} is empty")
        after_counts = {
            table: self.store.connection.execute(
                f"SELECT COUNT(*) AS n FROM {table}"
            ).fetchone()["n"]
            for table in (
                "observations", "source_documents", "observation_sources",
                "held_filings",
            )
        }
        self.assertEqual(
            after_counts["observations"],
            self.first.observations_stored,
        )
        self.assertEqual(after_counts["held_filings"], self.first.filings_seen)

    # -- 4: source fact identity ----------------------------------------

    def test_4_reingesting_the_same_filing_reuses_the_same_fact_id(self):
        rows = self.store.connection.execute(
            "SELECT source_fact_id, COUNT(*) AS n FROM observations"
            " WHERE source_fact_id IS NOT NULL"
            " GROUP BY source_fact_id HAVING n > 1"
        ).fetchall()
        self.assertEqual(rows, [], "a source fact was stored twice")

    def test_4_a_fact_keeps_its_identity_when_its_document_changes(self):
        """
        The defect this guards is silent and total.

        A fact's document is the filing that contains it, whose identity is the
        accession. The companyconcept endpoint is a rolling view over every
        filing that ever reported the concept, so its content hash changes the
        moment the filer reports anything new. Anchoring the identity to that
        hash would give all 1,900 historical facts new ids on the next filing and
        re-append the entire history, which is the exact failure incremental
        ingestion exists to prevent.
        """
        coordinates = {
            "source_id": SEC_SOURCE,
            "taxonomy": US_GAAP,
            "concept": "Assets",
            "period_start": None,
            "period_end": "2026-06-27",
            "context": "0000320193-26-000001",
        }
        by_filing = source_fact_id(
            document_ref="0000320193-26-000001", **coordinates
        )
        self.assertEqual(
            by_filing,
            source_fact_id(document_ref="0000320193-26-000001", **coordinates),
        )
        self.assertNotEqual(
            source_fact_id(document_ref="sha256:before", **coordinates),
            source_fact_id(document_ref="sha256:after", **coordinates),
            "a document hash would be a usable filing identity, and it is not",
        )

    def test_4_no_fact_identity_is_a_bare_value(self):
        row = self.store.connection.execute(
            "SELECT source_fact_id FROM observations"
            " WHERE source_fact_id IS NOT NULL LIMIT 1"
        ).fetchone()
        self.assertTrue(row["source_fact_id"].startswith("sfid_"))

    def test_5_a_second_parser_of_the_same_filing_produces_the_same_facts(self):
        """
        Two adapters reading the same filing are the deduplication case that
        `source_fact_id` exists for, and it is the one the SEC slice cannot
        exercise on its own — there is only one parser here.

        So it is asserted against the identity function rather than against a
        second adapter: given the same document, concept, period and context, the
        identity is a pure function of them, and a run that produced a different
        id for the same fact would be a different bug the uniqueness index would
        hide as an IntegrityError rather than as a wrong number.
        """
        rows = self.store.connection.execute(
            "SELECT source_fact_id, taxonomy, accession, period_start,"
            " period_end, source_concept_ref FROM observations"
            " WHERE source_fact_id IS NOT NULL LIMIT 50"
        ).fetchall()
        self.assertTrue(rows)
        for row in rows:
            taxonomy, _, concept = row["source_concept_ref"].partition(":")
            self.assertEqual(taxonomy, row["taxonomy"])
            self.assertEqual(
                row["source_fact_id"],
                source_fact_id(
                    SEC_SOURCE,
                    row["accession"],
                    taxonomy,
                    concept,
                    row["period_start"],
                    row["period_end"],
                    row["accession"],
                ),
                "the stored identity is not reproducible from the fact's own "
                "coordinates, so a second parser would not match it",
            )

    def test_5_b_re_parsing_the_same_filing_stores_nothing_new(self):
        """
        A whole second pass over the same issuer, in one run rather than two,
        must add nothing. This is the property a later adapter depends on.
        """
        store = new_archive()
        registry = CoreRegistry(store.connection)
        try:
            from sec_provider import SECProvider

            Ingestor(store, SECProvider(), registry).ingest(
                AAPL, metrics=DEFAULT_METRICS
            )
            first = store.connection.execute(
                "SELECT COUNT(*) AS n FROM observations"
            ).fetchone()["n"]
            second = Ingestor(store, SECProvider(), registry).ingest(
                AAPL, metrics=DEFAULT_METRICS
            )
            self.assertEqual(second.observations_stored, 0)
            self.assertEqual(second.source_facts_stored, 0)
            self.assertEqual(second.concept_fetches, 0)
            self.assertEqual(
                store.connection.execute(
                    "SELECT COUNT(*) AS n FROM observations"
                ).fetchone()["n"],
                first,
            )
        finally:
            store.close()

    def test_6_ingestion_never_marks_a_single_source_as_validated(self):
        """
        Ingestion adds a source; it cannot corroborate one. A filing cannot
        cross-validate itself, so every row must stay unverified rather than
        being promoted by the act of having been collected.
        """
        rows = self.store.connection.execute(
            "SELECT DISTINCT status FROM observations"
        ).fetchall()
        self.assertTrue(rows)
        for row in rows:
            self.assertEqual(
                row["status"],
                "UNVERIFIABLE",
                "an ingested observation was promoted past a single source",
            )
        row = self.store.connection.execute(
            "SELECT status_reasons_json FROM observations LIMIT 1"
        ).fetchone()
        self.assertIn("single official source", row["status_reasons_json"])

    # -- 7, 8, 9: registry -----------------------------------------------

    def test_7_every_ingested_concept_resolves_through_the_registry(self):
        """
        Every concept that reached storage was resolved by the registry, not by
        name. "Resolved" includes *declining to resolve*: a concept that maps to
        more than one metric is reported as ambiguous and stays unmapped, which
        is the correct answer rather than a failure to look up.
        """
        rows = self.store.connection.execute(
            "SELECT DISTINCT source_concept_ref FROM observations"
            " WHERE source_concept_ref IS NOT NULL"
        ).fetchall()
        self.assertTrue(rows)
        for row in rows:
            concept = row["source_concept_ref"]
            resolved = self.registry.resolve(concept)
            self.assertTrue(
                resolved.mappings,
                f"{concept} reached storage without any registry mapping",
            )
            candidates = {m.metric_id for m in resolved.mappings}
            if len(candidates) > 1:
                self.assertIsNone(
                    resolved.metric,
                    f"{concept} maps to several metrics and was forced to one",
                )
                self.assertIn("NOT_EXPLAINED", resolved.contract_dict()["reason"])
            else:
                self.assertIsNotNone(resolved.metric, f"{concept} did not resolve")
                self.assertEqual(
                    resolved.metric.metric_id,
                    next(iter(candidates)),
                    f"{concept} resolved to a metric it is not mapped to",
                )

    def test_8_an_unmapped_concept_is_left_unresolved(self):
        self.registry.add_concept(
            type(self.registry.concept("us-gaap:Assets"))(
                concept_id="us-gaap:BrandValueImpairment",
                taxonomy="us-gaap",
                concept="BrandValueImpairment",
                label="Brand value impairment",
                source_definition="Write-down of an indefinite-lived brand.",
            )
        )
        resolved = self.registry.resolve("us-gaap:BrandValueImpairment")
        self.assertIsNone(resolved.metric)
        self.assertIn("NOT_EXPLAINED", resolved.contract_dict()["reason"])

    def test_9_the_source_concept_differs_from_the_semantic_metric(self):
        row = self.store.connection.execute(
            "SELECT metric, source_concept_ref FROM observations"
            " WHERE source_concept_ref IS NOT NULL LIMIT 1"
        ).fetchone()
        self.assertNotEqual(
            row["metric"],
            row["source_concept_ref"],
            "the metric and the concept are the same string",
        )
        self.assertIn(":", row["source_concept_ref"])

    # -- 10, 11, 12: concept evolution -----------------------------------

    def test_10_a_concept_change_does_not_splice_a_series(self):
        self.assertTrue(self.registry.series_breaks("revenue"))
        self.assertTrue(self.registry.series_breaks("capex"))

    def _concept_spans(self, metric):
        """What each concept of a metric actually covers, as stored."""
        return {
            row["source_concept_ref"]: (row["first_end"], row["last_end"])
            for row in self.store.connection.execute(
                "SELECT source_concept_ref, MIN(period_end) AS first_end,"
                " MAX(period_end) AS last_end FROM observations"
                " WHERE metric = ? AND source_concept_ref IS NOT NULL"
                " GROUP BY source_concept_ref",
                (metric,),
            )
        }

    def test_11_the_revenue_overlap_is_real_in_the_stored_data(self):
        """
        All three revenue concepts are present, and the two that overlap in time
        really do overlap in the rows rather than merely in the registry's
        windows. Each carries its own fidelity, so nothing has been joined.
        """
        spans = self._concept_spans("revenue")
        contract = concept_id_for(
            US_GAAP, "RevenueFromContractWithCustomerExcludingAssessedTax"
        )
        revenues = concept_id_for(US_GAAP, "Revenues")
        sales_net = concept_id_for(US_GAAP, "SalesRevenueNet")
        self.assertEqual(
            set(spans), {contract, revenues, sales_net},
            "a revenue concept the registry maps was not ingested",
        )

        # `Revenues` is the broader tag; the contract concept is narrower. If
        # they had been spliced into one series, neither would still be present
        # for the quarters where both were filed.
        self.assertLessEqual(spans[revenues][0], spans[contract][1])
        self.assertLessEqual(spans[sales_net][0], spans[contract][1])

        mappings = {
            m.concept_id: m.mapping_type
            for m in self.registry.mappings_for_metric("revenue")
        }
        self.assertEqual(mappings[contract], "EXACT")
        self.assertEqual(mappings[revenues], "PARTIAL")
        self.assertEqual(mappings[sales_net], "PARTIAL")

    def test_11_b_the_older_concepts_are_not_the_current_series(self):
        """
        The narrowest concept is the one that continues. The two that stop are
        marked as not continuing, and that is what stops a query from reading
        `Revenues` as a continuation of the current revenue line.
        """
        by_concept = {
            m.concept_id: m
            for m in self.registry.mappings_for_metric("revenue")
        }
        self.assertTrue(
            by_concept[
                concept_id_for(
                    US_GAAP, "RevenueFromContractWithCustomerExcludingAssessedTax"
                )
            ].series_continues
        )
        for older in ("Revenues", "SalesRevenueNet"):
            self.assertFalse(
                by_concept[concept_id_for(US_GAAP, older)].series_continues,
                f"{older} was allowed to continue the current revenue series",
            )

    def test_12_the_capex_distinction_survives_ingestion(self):
        """
        Both capex concepts are stored and each keeps its own fidelity, which
        matters more than it first appears: AAPL filed both tags for a year, so
        the concepts genuinely overlap in the data. An implementation that kept
        only the first concept that answered would have dropped a year of
        filings, and one that merged them would have called the wider
        `ProductiveAssets` total the same measure as the narrower
        `PropertyPlantAndEquipment` one.
        """
        spans = self._concept_spans("capex")
        exact = concept_id_for(
            US_GAAP, "PaymentsToAcquirePropertyPlantAndEquipment"
        )
        partial = concept_id_for(US_GAAP, "PaymentsToAcquireProductiveAssets")
        self.assertEqual(set(spans), {exact, partial})
        self.assertLessEqual(
            spans[exact][0],
            spans[partial][1],
            "AAPL stopped filing the wider capex tag before it filed the "
            "narrower one, which would contradict the registry's windows",
        )

        mappings = {
            m.concept_id: m.mapping_type
            for m in self.registry.mappings_for_metric("capex")
        }
        self.assertEqual(mappings[exact], "EXACT")
        self.assertEqual(mappings[partial], "PARTIAL")

        breaks = self.registry.series_breaks("capex")
        self.assertEqual(len(breaks), 1)
        self.assertEqual(breaks[0]["concept_id"], partial)
        self.assertEqual(breaks[0]["mapping_type"], MAPPING_PARTIAL)

    # -- 13, 14, 15: identity and provenance ----------------------------

    def test_13_filing_identity_is_the_accession(self):
        rows = self.store.connection.execute(
            "SELECT accession, COUNT(*) AS n FROM held_filings"
            " GROUP BY accession HAVING n > 1"
        ).fetchall()
        self.assertEqual(rows, [], "a filing was held under two accessions")
        self.assertGreater(
            self.first.filings_ingested,
            0,
            "no filing was recorded by identity",
        )

    def test_14_source_document_provenance_survives(self):
        row = self.store.connection.execute(
            "SELECT o.observation_id, d.content_hash FROM observations o"
            " JOIN observation_sources os ON os.observation_id ="
            " o.observation_id JOIN source_documents d"
            " ON d.document_id = os.document_id LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(row, "no observation reaches a source document")
        self.assertTrue(row["content_hash"].startswith("sha256:"))

    def test_15_available_at_is_source_declared(self):
        rows = self.store.connection.execute(
            "SELECT available_at, available_at_basis, retrieved_at"
            " FROM observations WHERE metric = 'revenue' LIMIT 5"
        ).fetchall()
        self.assertTrue(rows)
        for row in rows:
            self.assertIsNotNone(row["available_at"])
            self.assertNotEqual(
                row["available_at"],
                row["retrieved_at"],
                "retrieval time was used as availability",
            )
            self.assertIn(
                row["available_at_basis"],
                ("ACCEPTANCE_DATETIME", "FILED_AS_OF_DATE"),
            )

    # -- 16: query traceability -----------------------------------------

    def test_16_a_figure_traces_to_its_accession_and_concept(self):
        row = self.query.query_observations(
            asset=AAPL, metric="revenue", order="PERIOD_ASCENDING", limit=1
        )[0]
        self.assertTrue(row["source"]["accession"])
        self.assertIn(":", row["source"]["concept"])
        self.assertTrue(row["source"]["documents"][0]["content_hash"])
        self.assertTrue(row["lineage"]["source_fact_id"])
        self.assertEqual(row["semantic"]["metric"], "revenue")
        self.assertTrue(row["semantic"]["resolved"])

    def test_16_a_series_is_queryable_after_ingestion(self):
        history = self.query.get_metric_history(AAPL, "revenue")
        self.assertGreater(history["point_count"], 0)
        self.assertTrue(history["state"]["state"].endswith("REPORTED"))

    def test_16_lineage_reaches_the_document(self):
        row = self.query.query_observations(
            asset=AAPL, metric="revenue", order="PERIOD_ASCENDING", limit=1
        )[0]
        lineage = self.query.get_lineage(row["observation_id"])
        steps = [item["step"] for item in lineage["chain"]]
        self.assertIn("SOURCE_DOCUMENT", steps)
        self.assertIn("SOURCE_FACT", steps)
        self.assertIn("OBSERVATION", steps)

    # -- an honest limitation -------------------------------------------

    def test_dimension_collisions_are_counted_not_hidden(self):
        """
        The aggregated concept endpoint does not expose dimension members, so
        two facts that differ only by segment arrive looking identical. The run
        counts them rather than pretending the series is clean.
        """
        self.assertGreater(
            self.first.dimension_collisions,
            0,
            "AAPL revenue is reported by segment; the endpoint hides that",
        )


if __name__ == "__main__":
    unittest.main()
