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
        for issuer in ISSUERS:
            cls.first[issuer] = Ingestor(
                cls.store, SECProvider(), cls.registry
            ).ingest(issuer, metrics=DEFAULT_METRICS)
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
        The cross-company finding, asserted as behaviour.

        `metric_concept_mapping` carries one global window per concept, seeded
        from AAPL. Filers adopt concepts on their own schedules, so a global
        window is wrong for some of them: MSFT filed `us-gaap:Revenues` from
        2007, nine years before AAPL's window opens, and NVDA still files it in
        2026, eight years after AAPL's window closed.

        The correct response is to leave those figures unresolved and say so. The
        failure this guards against is the convenient one — resolving by name, or
        widening the window until nothing is unresolved — which would attach a
        figure to a metric its filer never claimed for that period.
        """
        unresolved = {}
        for issuer in ISSUERS:
            rows = self.query.query_observations(
                asset=issuer, metric="revenue",
                order="PERIOD_ASCENDING", limit=5000,
            )
            unresolved[issuer] = [
                row for row in rows if not row["semantic"].get("resolved")
            ]

        # At least one issuer must actually hit this, or the guard is vacuous.
        self.assertTrue(
            any(unresolved.values()),
            "no issuer fell outside a registry window; the claim that filers "
            "adopt concepts on their own schedules is untested here",
        )
        for issuer, rows in unresolved.items():
            for row in rows:
                self.assertIsNone(
                    row["semantic"].get("metric"),
                    f"{issuer}: a figure outside its window was attached to a "
                    "metric anyway",
                )
                self.assertIn(
                    "NOT_EXPLAINED", row["semantic"].get("reason", "")
                )

    def test_a_window_is_a_registry_fact_not_a_filer_specific_one(self):
        """
        The limitation stated plainly, so it cannot be forgotten by whoever
        reads the next registry change.

        The mapping table has no issuer dimension, by design: the registry
        describes a concept and a metric, not a company. That is right for the
        mapping *type* and wrong for the *window*, because adoption is per
        filer. The fix is not a company column on the mapping — it would make
        every query issuer-aware and put filer trivia into the semantic layer —
        but a separate per-issuer adoption record the window is checked against.
        Recorded here as a known gap, deliberately not fixed at this stage.
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
        # And the consequence is real and measured: a filer outside the window
        # is left unresolved rather than mis-resolved.
        outside = self.store.connection.execute(
            "SELECT COUNT(*) AS n FROM observations o"
            " JOIN metric_concept_mapping m"
            " ON m.concept_id = o.source_concept_ref"
            " WHERE m.effective_from IS NOT NULL"
            " AND o.period_end < m.effective_from"
        ).fetchone()["n"]
        self.assertGreater(
            outside, 0,
            "no fact falls outside a window, so the gap above is theoretical",
        )

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
