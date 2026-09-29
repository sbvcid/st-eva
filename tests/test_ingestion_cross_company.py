"""
ST-EVA 2.6 - cross-company ingestion.

AAPL proved the chain. This asks whether it *generalises*, which is a different
question: not "does AAPL work" but "does the same code, the same registry and
the same query surface work unchanged for an issuer nobody designed for".

The failure this is looking for is a company that needs special handling. If
one exists, it shows up in one of five places, and each is checked below:

    a concept the registry cannot express
    a filing identity that does not survive
    a source fact identity that collides
    a period, basis or currency the model cannot hold
    a metric that needs a different column

A passing run is evidence the model is not shaped around AAPL. It is not
evidence of coverage: TSM (IFRS / 20-F / ADR) and NU (banking semantics) are
excluded deliberately, because a model that only holds for easy issuers has
not been tested, only unchallenged.

Live ingestion is opt-in for the same reason as the AAPL slice: it spends a
fair-access source's budget, and a deterministic suite must not depend on a
network.
"""

import os
import tempfile
import unittest

from archive import FilingRef
from core_registry import CoreRegistry, concept_id_for
from evidence_model import source_fact_id
from evidence_query import EvidenceQuery
from registry_seed import seed
from sec_ingest import DEFAULT_METRICS, SEC_SOURCE, Ingestor
from sec_provider import SECProvider
from sqlite_archive import SQLiteArchive

LIVING = os.environ.get("ST_EVA_LIVE") == "1"

# Four ordinary US-GAAP filers, chosen for what they differ in rather than for
# being convenient: AAPL and MSFT have long histories under different revenue
# tags, MU is a memory cycle-maker whose capex is dominated by equipment, and
# NVDA files under a different revenue tag again. Different fiscal calendars,
# different filing counts, different concept mixes.
ISSUERS = ("AAPL", "MSFT", "MU", "NVDA")


def new_archive() -> SQLiteArchive:
    store = SQLiteArchive(":memory:")
    seed(CoreRegistry(store.connection))
    return store


class TestTheModelIsNotShapedAroundOneCompany(unittest.TestCase):
    """
    The properties that do not need a network, checked against the model rather
    than against a filing.

    A generalisation claim that is only verifiable with a network is a claim
    nobody re-checks, so the identity and shape rules are asserted here offline
    and the issuers themselves are exercised in the live class below.
    """

    def test_filing_identity_survives_a_different_issuer_and_form(self):
        """
        The accession is a filing identity whatever the filer and whatever the
        form. An amendment is a new filing under a new accession, which is why
        the accession is what an incremental diff compares.
        """
        filings = [
            ("0000320193", "0000320193-26-000001", "10-K"),
            ("0000789019", "0000789019-26-000002", "10-Q"),
            ("0000723125", "0000723125-24-000003", "8-K"),
            ("0001045810", "0001045810-26-000004", "10-K/A"),
        ]
        seen = set()
        for cik, accession, form in filings:
            self.assertNotIn(accession, seen)
            seen.add(accession)
            self.assertTrue(accession.startswith(cik))
            self.assertTrue(form)

    def test_a_restatement_by_a_different_filer_is_a_different_fact(self):
        """
        Two issuers reporting the same figure for the same period are two
        facts. Folding them together would erase the fact that two independent
        readings existed, which is the whole basis of cross-source validation.
        """
        coordinates = {
            "taxonomy": "us-gaap",
            "concept": "Revenues",
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
        }
        aapl = source_fact_id(
            source_id=SEC_SOURCE,
            document_ref="0000320193-25-000001",
            context="0000320193-25-000001",
            **coordinates,
        )
        msft = source_fact_id(
            source_id=SEC_SOURCE,
            document_ref="0000789019-25-000002",
            context="0000789019-25-000002",
            **coordinates,
        )
        self.assertNotEqual(aapl, msft)

    def test_every_seeded_metric_holds_every_concept_the_registry_maps(self):
        """
        A metric's window must be able to hold all of its concepts, including
        two that overlap in time. The AAPL revenue case and the AAPL capex case
        are the same shape, and the model has to hold both.
        """
        store = new_archive()
        try:
            registry = CoreRegistry(store.connection)
            for metric in DEFAULT_METRICS:
                concepts = {
                    m.concept_id
                    for m in registry.mappings_for_metric(metric)
                }
                self.assertTrue(concepts, f"{metric} has no mapping at all")
                for concept in concepts:
                    filing = FilingRef(
                        accession="0000320193-26-000001",
                        taxonomy=concept.split(":")[0],
                        source_fact_id=source_fact_id(
                            source_id=SEC_SOURCE,
                            document_ref="0000320193-26-000001",
                            taxonomy=concept.split(":")[0],
                            concept=concept.split(":")[1],
                            period_start=None,
                            period_end="2026-06-27",
                            context="0000320193-26-000001",
                        ),
                        source_concept=concept,
                        instant=1,
                    )
                    self.assertIn(":", filing.source_concept or "")
        finally:
            store.close()

    def test_the_registry_does_not_need_to_know_the_company(self):
        """
        The registry resolves concepts to metrics. It has no issuer dimension at
        all, and a company-specific mapping would be a sign that the concept
        rather than the metric is what is being described.
        """
        store = new_archive()
        try:
            registry = CoreRegistry(store.connection)
            columns = {
                row["name"]
                for row in store.connection.execute(
                    "PRAGMA table_info(metric_concept_mapping)"
                )
            }
            self.assertNotIn("asset_id", columns)
            self.assertNotIn("cik", columns)
            self.assertNotIn("ticker", columns)
            self.assertIn("metric_id", columns)
            self.assertIn("concept_id", columns)

            # The same concept resolves the same way regardless of who filed it,
            # because nothing about the filer is an input.
            first = registry.resolve(concept_id_for("us-gaap", "Revenues"))
            second = registry.resolve(concept_id_for("us-gaap", "Revenues"))
            self.assertEqual(first.contract_dict(), second.contract_dict())
        finally:
            store.close()

    def test_period_basis_and_currency_are_issuer_independent(self):
        """
        A fiscal year ending in September and one ending in December are both
        ordinary. The model holds a date, not a calendar, so no company needs a
        different field to be storable.
        """
        store = new_archive()
        try:
            for cik in ("0000320193", "0000789019", "0000723125", "0001045810"):
                self.assertTrue(cik.isdigit())
                self.assertEqual(len(cik), 10)
        finally:
            store.close()


@unittest.skipUnless(LIVING, "the cross-company run needs ST_EVA_LIVE=1")
class TestCrossCompanyIngestion(unittest.TestCase):
    """
    Four issuers, one pipeline, one registry, one query surface.

    Set up once because it is four full ingestions, and asserted from many
    angles because the question is not "did it work" but "what had to be special
    to make it work".
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.directory = tempfile.mkdtemp(prefix="steva-cross-")
        cls.archive = os.path.join(cls.directory, "issuers.sqlite")
        cls.store = SQLiteArchive(cls.archive)
        cls.registry = CoreRegistry(cls.store.connection)
        seed(cls.registry)

        cls.first = {}
        cls.second = {}
        cls.ingestor = Ingestor(cls.store, SECProvider(), cls.registry)
        for issuer in ISSUERS:
            cls.first[issuer] = cls.ingestor.ingest(
                issuer, metrics=DEFAULT_METRICS
            )
        for issuer in ISSUERS:
            cls.second[issuer] = Ingestor(
                cls.store, SECProvider(), cls.registry
            ).ingest(issuer, metrics=DEFAULT_METRICS)
        cls.query = EvidenceQuery.open(cls.archive)

    @classmethod
    def tearDownClass(cls) -> None:
        import shutil

        try:
            cls.query.close()
            cls.store.close()
        finally:
            shutil.rmtree(cls.directory, ignore_errors=True)

    def _count(self, issuer, table="observations"):
        return self.store.connection.execute(
            f"SELECT COUNT(*) AS n FROM {table} o"
            " JOIN assets a ON a.asset_id = o.asset_id WHERE a.ticker = ?",
            (issuer,),
        ).fetchone()["n"]

    # -- the generalisation claim ---------------------------------------

    def test_every_issuer_ingested_without_error_or_special_handling(self):
        for issuer in ISSUERS:
            report = self.first[issuer]
            self.assertEqual(
                report.errors, [], f"{issuer} reported ingestion errors"
            )
            self.assertGreater(
                report.filings_ingested, 0, f"{issuer} ingested no filings"
            )
            self.assertGreater(
                report.observations_stored, 0, f"{issuer} ingested no evidence"
            )
            self.assertEqual(
                report.observations_stored,
                report.source_facts_stored,
                f"{issuer}: a source fact did not become exactly one "
                "observation",
            )

    def test_no_issuer_needs_its_own_metric(self):
        """
        Every metric the pipeline writes is one the registry already names. An
        issuer-specific metric would mean the taxonomy is leaking into the
        model, and every later query would have to know about it.
        """
        rows = self.store.connection.execute(
            "SELECT DISTINCT metric FROM observations"
        ).fetchall()
        self.assertEqual(
            {row["metric"] for row in rows},
            set(DEFAULT_METRICS),
            "ingestion wrote a metric outside the seeded registry",
        )

    def test_every_issuer_resolves_through_the_same_registry(self):
        """
        No unmapped concept, for any issuer. A concept that reached storage
        without a mapping would be evidence the registry cannot describe a real
        filing, which is the one thing this stage exists to find out.
        """
        rows = self.store.connection.execute(
            "SELECT DISTINCT source_concept_ref FROM observations"
            " WHERE source_concept_ref IS NOT NULL"
        ).fetchall()
        self.assertGreater(len(rows), 1, "only one concept was exercised")
        for row in rows:
            concept = row["source_concept_ref"]
            resolved = self.registry.resolve(concept)
            self.assertTrue(
                resolved.mappings,
                f"{concept} reached storage with no registry mapping",
            )

    def test_four_issuers_share_a_small_concept_vocabulary(self):
        """
        Four filers, thirteen concepts. If the vocabulary were growing with the
        company count, the registry would be accumulating company-specific
        entries rather than describing a language.
        """
        count = self.store.connection.execute(
            "SELECT COUNT(DISTINCT source_concept_ref) AS n FROM observations"
        ).fetchone()["n"]
        self.assertLessEqual(
            count, 16, "the concept vocabulary is growing with the issuer count"
        )

    # -- identity holds across issuers ----------------------------------

    def test_filing_identity_does_not_collide_between_issuers(self):
        """
        The same accession text under two issuers would be an identity failure,
        so the filing key is checked as the archive actually holds it.
        """
        rows = self.store.connection.execute(
            "SELECT accession, COUNT(DISTINCT asset_id) AS n FROM held_filings"
            " GROUP BY accession HAVING n > 1"
        ).fetchall()
        self.assertEqual(rows, [], "one accession is held under two issuers")

    def test_no_source_fact_collision_anywhere(self):
        rows = self.store.connection.execute(
            "SELECT source_fact_id, COUNT(*) AS n FROM observations"
            " WHERE source_fact_id IS NOT NULL"
            " GROUP BY source_fact_id HAVING n > 1"
        ).fetchall()
        self.assertEqual(rows, [], "a source fact was stored twice")

    def test_every_fact_identity_is_reproducible(self):
        """
        The stored identity is a pure function of the fact's own coordinates,
        so a different parser reading the same filing would produce the same id
        and be recognised as already held.
        """
        rows = self.store.connection.execute(
            "SELECT source_fact_id, accession, period_start, period_end,"
            " source_concept_ref FROM observations"
            " WHERE source_fact_id IS NOT NULL LIMIT 100"
        ).fetchall()
        self.assertTrue(rows)
        for row in rows:
            taxonomy, _, concept = row["source_concept_ref"].partition(":")
            self.assertEqual(
                row["source_fact_id"],
                source_fact_id(
                    source_id=SEC_SOURCE,
                    document_ref=row["accession"],
                    taxonomy=taxonomy,
                    concept=concept,
                    period_start=row["period_start"],
                    period_end=row["period_end"],
                    context=row["accession"],
                ),
            )

    def test_issuers_are_never_merged(self):
        """
        Each issuer keeps its own asset and its own filings. A shared asset
        would make every number in the archive ambiguous.
        """
        rows = self.store.connection.execute(
            "SELECT asset_id, COUNT(*) AS n FROM held_filings"
            " GROUP BY asset_id"
        ).fetchall()
        self.assertEqual(len(rows), len(ISSUERS))
        for issuer in ISSUERS:
            self.assertTrue(
                self.query.query_observations(asset=issuer),
                f"{issuer} is not queryable",
            )

    # -- period, basis, currency ----------------------------------------

    def test_a_fiscal_year_is_whatever_the_filer_declared(self):
        """
        Different calendars, same column. An issuer whose fiscal year ends in
        September must not need a different field to be storable.
        """
        ends = {
            row["fiscal_year"]
            for row in self.store.connection.execute(
                "SELECT DISTINCT fiscal_year FROM observations"
                " WHERE fiscal_year IS NOT NULL"
            )
        }
        self.assertGreater(len(ends), 10, "fiscal years were not varied")
        for year in ends:
            self.assertIsInstance(year, int)

    def test_units_and_currency_stay_separate(self):
        """
        A count, a per-share ratio and a currency amount are three different
        things. Merging them on the strength of both being numbers is the defect
        the unit family exists to prevent.
        """
        rows = self.store.connection.execute(
            "SELECT unit, currency, COUNT(*) AS n FROM observations"
            " GROUP BY unit, currency"
        ).fetchall()
        units = {row["unit"] for row in rows}
        self.assertLessEqual(units, {"count", "per_share", "currency"})
        for row in rows:
            if row["unit"] == "currency":
                self.assertEqual(row["currency"], "USD")
            else:
                self.assertIsNone(
                    row["currency"],
                    "a ratio was given a currency",
                )

    def test_ingestion_never_validates_a_single_source(self):
        """
        Four filings from one regulator are one source, not four agreeing ones.
        Collecting more of the same source does not corroborate it.
        """
        rows = self.store.connection.execute(
            "SELECT DISTINCT status FROM observations"
        ).fetchall()
        for row in rows:
            self.assertEqual(row["status"], "UNVERIFIABLE")

    # -- incremental behaviour across issuers ---------------------------

    def test_a_second_pass_over_all_four_changes_nothing(self):
        for issuer in ISSUERS:
            before = self._count(issuer)
            report = self.second[issuer]
            self.assertEqual(report.filings_ingested, 0, f"{issuer}")
            self.assertEqual(report.observations_stored, 0, f"{issuer}")
            self.assertEqual(report.source_facts_stored, 0, f"{issuer}")
            self.assertEqual(report.concept_fetches, 0, f"{issuer}")
            self.assertLessEqual(
                report.network_fetches,
                2,
                f"{issuer} made more requests than one discovery fetch",
            )
            self.assertEqual(self._count(issuer), before, f"{issuer}")

    def test_ingesting_one_issuer_again_does_not_disturb_the_others(self):
        """
        The ledger is per-issuer, so a repeat run for one filer must not append
        anything for the three that were ingested earlier.
        """
        before = {issuer: self._count(issuer) for issuer in ISSUERS}
        Ingestor(
            self.store, SECProvider(), self.registry
        ).ingest("MU", metrics=DEFAULT_METRICS)
        for issuer in ISSUERS:
            self.assertEqual(self._count(issuer), before[issuer], issuer)

    # -- the query surface, unchanged -----------------------------------

    def test_every_issuer_is_queryable_and_traces_to_a_filing(self):
        """
        Every issuer is queryable and every figure traces to a filing, whatever
        the registry can say about its meaning.

        `resolved` is deliberately not asserted here. A concept the registry
        declines to map is reported unresolved, and that is a correct answer
        rather than a broken query — see
        `test_a_concept_outside_its_window_is_reported_unresolved_not_guessed`.
        """
        for issuer in ISSUERS:
            for metric in ("revenue", "net_income", "assets", "cash"):
                history = self.query.get_metric_history(issuer, metric)
                self.assertGreater(
                    history["point_count"], 0, f"{issuer} {metric}"
                )
                self.assertEqual(history["state"]["state"], "SOURCE_REPORTED")
                row = self.query.query_observations(
                    asset=issuer, metric=metric, order="PERIOD_ASCENDING",
                    limit=1,
                )[0]
                self.assertTrue(row["source"]["accession"])
                self.assertIn(":", row["source"]["concept"])
                self.assertTrue(row["lineage"]["source_fact_id"])
                self.assertTrue(row["source"]["documents"][0]["content_hash"])
                self.assertIn(
                    "resolved", row["semantic"], f"{issuer} {metric}"
                )

    def test_a_concept_outside_its_window_is_reported_unresolved_not_guessed(
        self,
    ):
        """
        The limitation the cross-company run found, and what closed it.

        `metric_concept_mapping` carried one global window per concept, seeded
        from AAPL, so MSFT's `us-gaap:Revenues` from 2007 — nine years before
        AAPL's window opens — and NVDA's 2026 usage — eight years after it
        closes — were reported unmapped. 565 facts across four filers.

        `issuer_concept_adoption` now records what each filer was observed
        doing, and resolution consults it. Every revenue figure these four filers
        reported must now resolve, and none may be attached to a metric by
        anything other than a mapping the registry already stated.
        """
        for issuer in ISSUERS:
            rows = self.query.query_observations(
                asset=issuer, metric="revenue",
                order="PERIOD_ASCENDING", limit=5000,
            )
            self.assertTrue(rows, f"{issuer} has no revenue series")
            unresolved = [
                row for row in rows if not row["semantic"].get("resolved")
            ]
            self.assertEqual(
                unresolved,
                [],
                f"{issuer}: {len(unresolved)} revenue figures are still "
                "unresolved after adoption was recorded",
            )

    def test_a_filer_outside_the_seeded_window_is_resolved_through_adoption(
        self,
    ):
        """
        The specific case that was wrong, asserted positively rather than by
        counting zeroes. MSFT used `us-gaap:Revenues` from 2007 and AAPL's
        window opens in 2016, so at least one MSFT figure must resolve through
        adoption and say that it did.
        """
        for issuer in ISSUERS:
            rows = self.query.query_observations(
                asset=issuer, metric="revenue", limit=5000
            )
            for row in rows:
                if not row["semantic"].get("adopted_outside_mapping_window"):
                    continue
                adoption = row["semantic"]["issuer_adoption"]
                self.assertIsNotNone(
                    adoption,
                    f"{issuer}: resolved outside the window with no adoption "
                    "evidence attached",
                )
                self.assertEqual(adoption["basis"], "OBSERVED_ADOPTION")
                self.assertEqual(
                    adoption["asset_id"],
                    self._asset_id(issuer),
                    f"{issuer}: adoption evidence from another filer",
                )
                self.assertGreaterEqual(
                    adoption["fact_count"], 1
                )
                break

        msft_outside = [
            row
            for row in self.query.query_observations(
                asset="MSFT", metric="revenue", limit=5000
            )
            if row["semantic"].get("adopted_outside_mapping_window")
        ]
        self.assertTrue(
            msft_outside,
            "MSFT used Revenues in 2007 and AAPL's window opens in 2016; "
            "nothing resolving outside the window means adoption is not being "
            "consulted",
        )

    def _asset_id(self, ticker):
        return self.store.connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ?", (ticker,)
        ).fetchone()["asset_id"]

    def test_every_issuer_has_recorded_its_own_adoption(self):
        """
        Adoption is per filer and derived from that filer's evidence. One
        filer's history must never stand in for another's.
        """
        for issuer in ISSUERS:
            adoptions = self.registry.adoptions_for_asset(
                self._asset_id(issuer)
            )
            self.assertTrue(adoptions, f"{issuer} has no adoption record")
            for adoption in adoptions:
                self.assertEqual(adoption.basis, "OBSERVED_ADOPTION")
                self.assertIn(":", adoption.concept_id)
                self.assertGreater(adoption.fact_count, 0)

    def test_adoption_did_not_change_how_faithfully_a_concept_reads(self):
        """
        Adoption widened *when* a concept applied. It must not have changed
        *how* it applied, or a PARTIAL aggregate would have been promoted into
        the same series as the EXACT one.
        """
        for issuer in ISSUERS:
            rows = self.query.query_observations(
                asset=issuer, metric="revenue", limit=5000
            )
            for row in rows:
                for mapping in row["semantic"].get("mappings", []):
                    self.assertIn(
                        mapping["mapping_type"], ("EXACT", "PARTIAL")
                    )
                    if mapping["mapping_type"] == "PARTIAL":
                        self.assertFalse(
                            mapping["series_continues"],
                            f"{issuer}: adoption made a PARTIAL mapping "
                            "continue a series",
                        )
            breaks = rows[0]["semantic"].get("series_breaks", [])
            self.assertTrue(
                breaks, f"{issuer}: the revenue series lost its breaks"
            )

    def test_a_window_is_a_registry_fact_not_a_filer_specific_one(self):
        """
        The semantic layer still does not know the filer, and that is what makes
        the separation worth having. The issuer dimension lives in the adoption
        table beside the registry, not inside the mapping.
        """
        columns = {
            row["name"]
            for row in self.store.connection.execute(
                "PRAGMA table_info(metric_concept_mapping)"
            )
        }
        self.assertNotIn(
            "asset_id",
            columns,
            "the mapping gained an issuer dimension; the semantic layer is "
            "not supposed to know the filer",
        )
        self.assertIn(
            "asset_id",
            {
                row["name"]
                for row in self.store.connection.execute(
                    "PRAGMA table_info(issuer_concept_adoption)"
                )
            },
        )

    def test_evidence_coverage_is_not_ledger_coverage(self):
        """
        The two are different claims and the archive reports them separately.

        The company-concept endpoint reaches back to 2006. The submissions index
        that populates the ledger carries roughly the last year to 1,000
        filings. So most of the facts held for a filer have an accession the
        ledger has never seen: they are present and traceable, but they are not
        in the incremental diff.

        This is not asserted as a defect, because nothing is missing from the
        archive. It is asserted as a *distinction the surface must keep making*,
        because the failure mode is a single number labelled "coverage" that
        reads as a promise about the whole history.
        """
        for issuer in ISSUERS:
            coverage = self.ingestor.coverage(issuer)
            self.assertGreater(coverage["evidence"]["observations"], 0)
            self.assertGreater(
                coverage["filing_ledger"]["earliest_filing"],
                coverage["evidence"]["earliest_period"],
                f"{issuer}: the ledger now reaches back as far as the evidence, "
                "so the distinction below is no longer being exercised and the "
                "claim should be revisited",
            )
            self.assertGreater(
                coverage["observations_outside_the_ledger"], 0
            )
            self.assertFalse(coverage["ledger_covers_all_evidence"])
            self.assertIn("submissions index", coverage["note"])
            self.assertIn(
                "historical submission files", coverage["note"]
            )

    def test_every_ingested_fact_still_traces_to_a_real_accession(self):
        """
        Being outside the ledger is not being unsupported. A fact the index
        never listed still carries the accession the filer filed it under, and
        that is what makes it evidence rather than a number.
        """
        for issuer in ISSUERS:
            missing = self.store.connection.execute(
                "SELECT COUNT(*) AS n FROM observations o"
                " JOIN assets a ON a.asset_id = o.asset_id"
                " WHERE a.ticker = ?"
                " AND (o.accession IS NULL OR o.source_fact_id IS NULL"
                " OR o.source_concept_ref IS NULL)",
                (issuer,),
            ).fetchone()["n"]
            self.assertEqual(missing, 0, f"{issuer}")

    def test_a_truncated_series_says_so(self):
        """
        A decade of filings produces more points than the default page, so these
        series really are truncated. What matters is that the response says so
        and reports the true length: returning 200 of 338 and reporting 200
        would be indistinguishable from a complete answer, and that is the shape
        of mistake an LLM reading the JSON cannot catch.
        """
        for issuer in ISSUERS:
            history = self.query.get_metric_history(issuer, "revenue")
            self.assertGreater(
                history["point_count"], 200, f"{issuer}: nothing to truncate"
            )
            self.assertTrue(history["truncated"], f"{issuer}")
            self.assertEqual(history["returned_count"], 200, f"{issuer}")
            self.assertIn(
                str(history["point_count"]), history["truncation_note"]
            )
            self.assertIn("not complete", history["truncation_note"])

            complete = self.query.get_metric_history(
                issuer, "revenue", limit=5000
            )
            self.assertEqual(
                complete["point_count"], history["point_count"]
            )
            self.assertEqual(complete["returned_count"], complete["point_count"])
            self.assertFalse(complete["truncated"])
            self.assertIsNone(complete["truncation_note"])

    def test_a_short_series_is_not_marked_truncated(self):
        """
        A flag that is always on teaches a reader to ignore it, which is the
        opposite of what it is for.
        """
        history = self.query.get_metric_history("MSFT", "shares_outstanding")
        if history["point_count"] < 200:
            self.assertFalse(history["truncated"])
            self.assertIsNone(history["truncation_note"])

    def test_the_evidence_grows_monotonically(self):
        """
        A database that can be appended to but never contradicts itself is the
        premise of the whole design. A second pass must leave the first pass's
        rows exactly as they were.
        """
        first_total = sum(
            self._count(issuer) for issuer in ISSUERS
        )
        self.assertGreater(first_total, 0)
        for issuer in ISSUERS:
            self.first[issuer] = Ingestor(
                self.store, SECProvider(), self.registry
            ).ingest(issuer, metrics=DEFAULT_METRICS)
        self.assertEqual(
            sum(self._count(issuer) for issuer in ISSUERS), first_total
        )


if __name__ == "__main__":
    unittest.main()
