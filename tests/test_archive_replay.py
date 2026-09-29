"""
ST-EVA 2.4 tests.

The phase's whole claim is that a replay answers a question about T using only
what existed at T. So the tests are mostly about what replay *refuses* to do.

The four replay classes come straight from the specification:

    A  Determinism          the rebuild reproduces the stored document
    B  Exclusion            later information is not used
    C  Honest insufficiency a missing history is reported, not filled in
    D  Restatement survival both sides of an amendment remain visible

Class C is the one that matters most. A replay that substitutes a value is
worse than a replay that fails, because it produces a plausible document that
answers a different question.
"""

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from archive import (
    ARCHIVE_FIRST_SEEN,
    FIDELITY_OBSERVATIONAL,
    FIDELITY_SOURCE_DECLARED,
    REPLAY_INSUFFICIENT,
    REPLAY_MATCH,
    REPLAY_NO_SNAPSHOT,
    SOURCE_DECLARED,
    UNDECLARED,
    ArchiveError,
    ArchiveStore,
    NullArchive,
    StoredDocument,
    availability_class_for,
    replay,
)
from data_contract import (
    AvailabilityBasis,
    METRIC_PRICE,
    Observation,
    ObservationSet,
    SourceType,
    Unit,
    ValidationStatus,
)
from sqlite_archive import SQLiteArchive  # noqa: F401  (observation_content_hash covered by round-trip tests)
from st_eva_runner import (
    CompanyResolver,
    DeterministicMetricsEngine,
    _document_hashes_of,
    build_context_from_observations,
    build_evidence,
    market_data_from_observations,
    material_observations,
    metrics_observation,
    run_st_eva,
)

REPO = Path(__file__).resolve().parent.parent
ARCHIVED_AT = "2026-09-28T12:00:00+00:00"


def make_observation(
    observation_id: str,
    metric: str,
    value,
    *,
    unit: str = Unit.CURRENCY.value,
    currency: str = "USD",
    period_start: str = "2025-06-29",
    period_end: str = "2026-06-27",
    as_of: str = "2026-06-27",
    available_at: str = "2026-07-31T10:01:02.000Z",
    available_at_basis: str = AvailabilityBasis.ACCEPTANCE_DATETIME.value,
    retrieved_at: str = "2026-09-28T12:00:00+00:00",
    provider: str = "SecEdgar",
    accession: str = "0000320193-26-000020",
    concept: str = "us-gaap:NetIncomeLoss",
    source_type: str = SourceType.REGULATORY_FILING.value,
) -> Observation:
    taxonomy, _, tag = concept.rpartition(":")
    return Observation(
        observation_id=observation_id,
        metric=metric,
        value=value,
        unit=unit,
        currency=currency,
        currency_basis="REPORTED" if currency else "NOT_APPLICABLE",
        period_start=period_start,
        period_end=period_end,
        as_of=as_of,
        available_at=available_at,
        available_at_basis=available_at_basis,
        provider=provider,
        source_type=source_type,
        source_url=f"https://data.sec.gov/x/{concept.replace(':', '/')}.json",
        definition=f"{metric} definition",
        methodology="stub methodology",
        retrieved_at=retrieved_at,
        raw={
            "sec_fact": {
                "taxonomy": taxonomy or "vendor",
                "tag": tag or concept,
                "accession": accession,
            }
        },
        status=ValidationStatus.UNVERIFIABLE,
        status_reasons=(
            "a single official source cannot cross-validate itself",
        ),
    )


def price_observation(
    price: float = 425.50,
    *,
    as_of: str = "2026-09-18",
    available_at: str = "2026-09-18T20:00:00.000Z",
    retrieved_at: str = "2026-09-28T12:00:00+00:00",
) -> Observation:
    return Observation(
        observation_id="ev-price-001",
        metric=METRIC_PRICE,
        value=price,
        unit=Unit.CURRENCY.value,
        currency="USD",
        currency_basis="REPORTED",
        period_start=None,
        period_end=as_of,
        as_of=as_of,
        available_at=available_at,
        available_at_basis=AvailabilityBasis.OBSERVATION_INSTANT.value,
        provider="RegressionFixture",
        source_type=SourceType.REGRESSION_FIXTURE.value,
        source_url=None,
        definition="Observed current or latest market price.",
        methodology="static regression fixture",
        retrieved_at=retrieved_at,
        raw={"regular_market_price": price, "closes": [price]},
        status=ValidationStatus.SINGLE_SOURCE,
    )


def archive_fixture_run(store: SQLiteArchive, ticker: str = "MSFT") -> dict:
    """Archive exactly what a real regression run produces."""
    data = CompanyResolver.resolve(ticker, mode="regression")
    metrics = DeterministicMetricsEngine.compute(
        data.price_history, data.volume_history
    )
    store.record_asset(
        ticker,
        name=data.company_name,
        exchange=data.exchange,
        currency=data.currency,
    )
    for observation in material_observations(data).values():
        store.record_observation(ticker, observation)
    store.record_observation(ticker, metrics_observation(data, metrics))
    for identifier in (
        "obs-price-history-001",
        "obs-volume-history-001",
    ):
        store.record_observation(ticker, data.observations.get(identifier))
    for identifier in data.observations.ids():
        observation = data.observations.get(identifier)
        if observation is not None and observation.observation_id.startswith(
            "cmp-"
        ):
            store.record_observation(ticker, observation)
    store.connection.commit()

    evidence = build_evidence(data, metrics)
    from st_eva_runner import MarketImpliedAssumptionsEngine

    analysis = MarketImpliedAssumptionsEngine.analyze(data)
    from investment_context import build_investment_context

    document = build_investment_context(
        data=data,
        analysis=analysis,
        evidence=evidence,
        metrics=metrics,
        material_observations=list(material_observations(data).values())
        + [metrics_observation(data, metrics)],
        generated_at=ARCHIVED_AT,
    )
    store.record_context(
        ticker, document, replay_fidelity=FIDELITY_SOURCE_DECLARED
    )
    return document


def archival_watermark(store: SQLiteArchive, asset: str = "MSFT") -> str:
    """
    The latest instant at which anything became replay-eligible for an asset.

    A replay before this watermark is asking a question about a time the
    archive had not yet learned the answer to, which is a different question
    from the one a determinism check is asking.
    """
    row = store.connection.execute(
        "SELECT MAX(o.replay_eligible_from) AS watermark FROM observations o"
        " JOIN assets a ON a.asset_id = o.asset_id WHERE a.ticker = ?",
        (asset.upper(),),
    ).fetchone()
    return row["watermark"]


def replay_document(
    observation_set: ObservationSet,
    as_of: str,
    generated_at: str,
    asset_metadata=None,
):
    return build_context_from_observations(
        [
            observation_set.get(identifier)
            for identifier in observation_set.ids()
        ],
        ticker=observation_set.ticker,
        as_of=as_of,
        generated_at=generated_at,
        asset_metadata=asset_metadata,
    )


class TestArchiveSchema(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_the_specified_tables_exist(self):
        for table in (
            "assets",
            "sources",
            "source_documents",
            "observations",
            "observation_lineage",
            "observation_sources",
            "validation_records",
            "derived_values",
            "context_snapshots",
        ):
            self.assertIn(table, self.store.table_names(), f"{table} missing")

    def test_the_schema_version_is_recorded(self):
        version = self.store.connection.execute("PRAGMA user_version").fetchone()[0]
        self.assertGreaterEqual(version, 1)

    def test_migrations_are_recorded_with_a_checksum(self):
        rows = self.store.connection.execute(
            "SELECT version, name, checksum FROM schema_migrations"
        ).fetchall()
        self.assertTrue(rows)
        for row in rows:
            self.assertTrue(row["checksum"])

    def test_reopening_does_not_reapply_a_migration(self):
        path = str(Path(tempfile.mkdtemp()) / "archive.sqlite")
        expected = len(list((REPO / "archive" / "migrations").glob("*.sql")))

        first = SQLiteArchive(path)
        applied = first.connection.execute(
            "SELECT COUNT(*) AS n FROM schema_migrations"
        ).fetchone()["n"]
        self.assertEqual(applied, expected)
        first.record_observation("AAPL", price_observation())
        first.close()

        second = SQLiteArchive(path)
        after = second.connection.execute(
            "SELECT COUNT(*) AS n FROM schema_migrations"
        ).fetchone()["n"]
        self.assertEqual(after, expected, "a migration was re-applied")
        second.close()

    def test_every_migration_is_recorded_with_a_checksum(self):
        rows = self.store.connection.execute(
            "SELECT version, name, checksum FROM schema_migrations"
            " ORDER BY version"
        ).fetchall()
        self.assertGreaterEqual(len(rows), 1)
        versions = [row["version"] for row in rows]
        self.assertEqual(versions, sorted(versions), "migrations must be ordered")
        for row in rows:
            self.assertTrue(row["checksum"])

    def test_a_modified_migration_aborts(self):
        """
        Forward-only means forward-only. A migration edited after it was
        applied means the archive's shape is no longer the one that ran.
        """
        import sqlite_archive

        original = sqlite_archive.MIGRATIONS_DIR / "0001_initial.sql"
        directory = Path(tempfile.mkdtemp())
        copied = directory / original.name
        copied.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
        sql = copied.read_text(encoding="utf-8") + "\n-- tampered\n"
        copied.write_text(sql, encoding="utf-8")

        path = str(directory / "a.sqlite")
        first = SQLiteArchive(path)
        first.close()

        saved = sqlite_archive.MIGRATIONS_DIR
        sqlite_archive.MIGRATIONS_DIR = directory
        try:
            with self.assertRaises(ArchiveError):
                SQLiteArchive(path)
        finally:
            sqlite_archive.MIGRATIONS_DIR = saved


class TestAppendOnlyEnforcement(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.store.record_observation("AAPL", price_observation())

    def tearDown(self) -> None:
        self.store.close()

    def test_an_observation_cannot_be_updated(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "UPDATE observations SET value_json = '0'"
            )

    def test_an_observation_cannot_be_deleted(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute("DELETE FROM observations")

    def test_a_context_snapshot_cannot_be_changed(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        metrics = DeterministicMetricsEngine.compute(
            data.price_history, data.volume_history
        )
        document = archive_fixture_run(self.store, "MSFT")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "UPDATE context_snapshots SET as_of = '1999-01-01'"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "DELETE FROM context_snapshots WHERE context_id = ?",
                (document["context_id"],),
            )

    def test_a_historical_observation_is_never_overwritten(self):
        before = self.store.all_observations("AAPL")
        # The same fact archived again must not mutate the first row.
        self.store.record_observation("AAPL", price_observation())
        after = self.store.all_observations("AAPL")
        self.assertEqual(
            [(o.observation_id, o.value) for o in before],
            [(o.observation_id, o.value) for o in after],
        )


class TestAvailabilityClassSemantics(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_a_source_declared_observation_is_classed_from_its_basis(self):
        observation = make_observation(
            "obs-filing", "net_income", 1.0
        )
        self.assertEqual(availability_class_for(observation), SOURCE_DECLARED)
        self.store.record_observation("AAPL", observation)
        classes = self.store.availability_classes("AAPL")
        self.assertEqual(list(classes.values()), [SOURCE_DECLARED])

    def test_an_undated_observation_is_never_replay_eligible(self):
        """
        Requirement 9. A value the source never dated cannot become knowable
        merely because it was fetched.
        """
        observation = make_observation(
            "obs-undated",
            "trailing_eps",
            8.72,
            unit=Unit.PER_SHARE.value,
            available_at=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
        )
        self.store = SQLiteArchive(":memory:", archive_unknown_availability=False)
        self.store.record_observation("AAPL", observation)
        classes = self.store.availability_classes("AAPL")
        self.assertEqual(list(classes.values()), [UNDECLARED])
        self.assertEqual(
            self.store.observations_for("AAPL", "2030-01-01"), [],
            "an undeclared observation must be ineligible at every instant",
        )
        self.store.close()

    def test_an_archive_first_seen_observation_is_observational(self):
        observation = make_observation(
            "obs-undated",
            "trailing_eps",
            8.72,
            unit=Unit.PER_SHARE.value,
            available_at=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
        )
        self.store.record_observation("AAPL", observation)
        classes = self.store.availability_classes("AAPL")
        self.assertEqual(list(classes.values()), [ARCHIVE_FIRST_SEEN])
        eligibility = self.store.eligibility_for("AAPL")
        self.assertTrue(
            eligibility,
            "an archive-dated observation is eligible from first archival",
        )

    def test_retrieved_at_never_becomes_available_at(self):
        """
        Requirement 6, and the single easiest way to produce a worthless
        backtest. A retrieval time is when this process asked, not when the
        data became public.
        """
        observation = make_observation(
            "obs-undated",
            "trailing_eps",
            8.72,
            unit=Unit.PER_SHARE.value,
            available_at=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            retrieved_at="2026-09-28T12:00:00+00:00",
        )
        self.store.record_observation("AAPL", observation)
        row = self.store.connection.execute(
            "SELECT available_at, retrieved_at, availability_class,"
            " replay_eligible_from, first_archived_at FROM observations"
        ).fetchone()
        self.assertIsNone(row["available_at"], "available_at was back-filled")
        self.assertIsNotNone(row["retrieved_at"])
        self.assertNotEqual(
            row["replay_eligible_from"], row["available_at"]
        )
        self.assertEqual(row["replay_eligible_from"], row["first_archived_at"])

    def test_the_database_refuses_an_inconsistent_class(self):
        """The rule is enforced by the database, not by a docstring."""
        self.store.record_observation("AAPL", price_observation())
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO observations (observation_id, contract_id,"
                " asset_id, lineage_id, metric, provider, source_type, concept,"
                " value_json, availability_class, retrieved_at,"
                " first_archived_at, replay_eligible_from, content_hash)"
                " VALUES ('x', 'x',"
                " (SELECT asset_id FROM assets LIMIT 1),"
                " (SELECT lineage_id FROM observation_lineage LIMIT 1),"
                " 'm', 'p', 'API_LIVE', 'us-gaap:X', '1',"
                " 'UNDECLARED', '2026-01-01', '2026-01-02', '2026-01-02',"
                " 'h2')"
            )

    def test_an_undeclared_observation_cannot_claim_eligibility(self):
        self.store.record_observation("AAPL", price_observation())
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO observations (observation_id, contract_id,"
                " asset_id, lineage_id, metric, provider, source_type, concept,"
                " value_json, availability_class, retrieved_at,"
                " first_archived_at, replay_eligible_from, content_hash)"
                " VALUES ('y', 'y',"
                " (SELECT asset_id FROM assets LIMIT 1),"
                " (SELECT lineage_id FROM observation_lineage LIMIT 1),"
                " 'm', 'p', 'API_LIVE', 'us-gaap:X', '1',"
                " 'UNDECLARED', '2026-01-01', '2026-01-02', '2026-01-02',"
                " 'h3')"
            )


class TestSourceDocumentCapture(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def _document(self, content: str) -> StoredDocument:
        import hashlib

        return StoredDocument(
            content_hash="sha256:" + hashlib.sha256(
                content.encode("utf-8")
            ).hexdigest(),
            uri="https://data.sec.gov/x.json",
            http_status=200,
            media_type="application/json",
            byte_size=len(content),
            fetched_at="2026-09-28T12:00:00+00:00",
            first_seen_at="2026-09-28T12:00:00+00:00",
        )

    def test_identical_content_is_stored_once(self):
        """Requirement 12. The same bytes are one document however often seen."""
        document = self._document("same bytes")
        first = self.store.record_source_document(document)
        second = self.store.record_source_document(document)
        self.assertEqual(first, second)
        self.assertEqual(self.store.document_count(), 1)

    def test_different_content_is_a_different_document(self):
        first = self.store.record_source_document(self._document("a"))
        second = self.store.record_source_document(self._document("b"))
        self.assertNotEqual(first, second)
        self.assertEqual(self.store.document_count(), 2)

    def test_an_observation_links_to_the_document_it_came_from(self):
        self.store.record_source_document(self._document("payload"))
        captured = self.store.record_source_document(self._document("second"))
        self.store.record_observation(
            "AAPL",
            price_observation(),
            document_hashes=[self._document("payload").content_hash],
        )
        self.store.connection.commit()
        self.assertEqual(
            self.store.dangling_document_references(), [],
            "a dangling reference looks like evidence and is not",
        )
        self.assertTrue(captured)

    def test_a_document_reference_resolves_by_id_or_by_hash(self):
        document = self._document("either way")
        document_id = self.store.record_source_document(document)
        self.assertEqual(
            self.store.document_id_for(document.content_hash), document_id
        )
        self.assertEqual(
            self.store.document_id_for(document_id), document_id
        )

    def test_a_dangling_reference_is_refused(self):
        """Requirement 13. Capture failure is recorded, not hidden."""
        with self.assertRaises(ArchiveError):
            self.store.record_observation(
                "AAPL",
                price_observation(),
                document_hashes=["sha256:never-captured"],
            )

    def test_the_same_fact_seen_in_two_filings_keeps_both_sightings(self):
        """
        One value, two filings. The value is not duplicated and neither is the
        filing that saw it.
        """
        first = self.store.record_source_document(self._document("10-Q"))
        second = self.store.record_source_document(self._document("10-K"))
        observation = price_observation()
        self.store.record_observation(
            "AAPL", observation, document_hashes=[first]
        )
        self.store.record_observation(
            "AAPL", observation, document_hashes=[first, second]
        )
        self.store.connection.commit()
        self.assertEqual(self.store.observation_count(), 1)
        row = self.store.connection.execute(
            "SELECT observation_id FROM observations"
        ).fetchone()
        self.assertEqual(len(self.store.documents_for(row["observation_id"])), 2)


class TestLineageAndRestatement(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_a_restatement_appends_and_never_overwrites(self):
        """Invariant I3, measured: a 26.6% restatement stays visible."""
        original = make_observation(
            "cmp-net-income-sec-fy2007",
            "net_income",
            4_834_000_000.0,
            period_start="2006-09-30",
            period_end="2007-09-29",
            as_of="2007-09-29",
            available_at="2007-11-01T16:30:00.000Z",
            accession="0001193125-07-000032",
        )
        restated = make_observation(
            "cmp-net-income-sec-fy2007-amd",
            "net_income",
            6_119_000_000.0,
            period_start="2006-09-30",
            period_end="2007-09-29",
            as_of="2007-09-29",
            available_at="2008-01-25T16:30:00.000Z",
            accession="0001193125-08-000204",
        )
        self.store.record_observation("AAPL", original)
        self.store.record_observation("AAPL", restated)
        self.store.connection.commit()

        lineages = self.store.lineage_for("AAPL", "net_income")
        self.assertEqual(len(lineages), 1, "one period, one lineage")
        self.assertEqual(lineages[0]["versions"], 2)
        self.assertEqual(self.store.observation_count(), 2)

    def test_two_providers_do_not_share_a_lineage(self):
        """
        Section 6.3. Collapsing Yahoo and SEC at archive time would destroy
        the evidence cross-validation needs.
        """
        filing = make_observation("sec-revenue", "revenue", 100.0)
        vendor = make_observation(
            "cmp-revenue-yahoo-1",
            "revenue",
            100.0,
            available_at="2026-09-28T12:00:00+00:00",
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            provider="YahooFinance",
            concept="trailingTotalRevenue",
            source_type=SourceType.API_LIVE.value,
        )
        self.store.record_observation("AAPL", filing)
        self.store.record_observation("AAPL", vendor)
        self.store.connection.commit()
        lineages = self.store.lineage_for("AAPL", "revenue")
        self.assertEqual(
            len(lineages), 2, "a vendor and a filing are not the same lineage"
        )
        self.assertEqual(
            {row["concept"] for row in lineages},
            {"us-gaap:NetIncomeLoss", "vendor:trailingTotalRevenue"},
            "a vendor field and a filing concept are not one lineage",
        )


class TestReplayDeterminism(unittest.TestCase):
    """Class A: the same historical inputs reproduce the same context."""

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.document = archive_fixture_run(self.store, "MSFT")
        # Everything the run learned became eligible at its archival moment, so
        # a determinism check has to replay at or after that. Replaying earlier
        # is a different question and is tested separately.
        self.cutoff = archival_watermark(self.store, "MSFT")

    def tearDown(self) -> None:
        self.store.close()

    def test_replay_reproduces_the_stored_context(self):
        result = replay(self.store, "MSFT", self.cutoff, replay_document)
        self.assertEqual(result.outcome, REPLAY_MATCH, result.reason)
        self.assertTrue(result.matched)
        self.assertEqual(
            result.document["context_id"], self.document["context_id"]
        )

    def test_replay_is_stable_across_repetitions(self):
        first = replay(self.store, "MSFT", self.cutoff, replay_document)
        second = replay(self.store, "MSFT", self.cutoff, replay_document)
        self.assertEqual(
            first.document["context_id"], second.document["context_id"]
        )

    def test_a_replay_of_undated_vendor_data_is_observational(self):
        """
        The MSFT fixture's fundamentals carry no source-declared availability,
        so the archive dates them at first archival and a replay over them is
        OBSERVATIONAL. It is never promoted to source-declared knowledge.
        """
        result = replay(self.store, "MSFT", self.cutoff, replay_document)
        # The price and the series are genuinely source-dated; the
        # fundamentals are not. One archive-dated input is enough to downgrade
        # the whole replay, because the document cannot be more trustworthy
        # than its weakest input.
        self.assertEqual(result.replay_fidelity, FIDELITY_OBSERVATIONAL)
        self.assertIn(
            ARCHIVE_FIRST_SEEN,
            [klass for _, klass in result.availability_classes],
            "the fixture's undated fundamentals must be classed as "
            "archive-dated, never as source-declared",
        )
        self.assertIn(
            SOURCE_DECLARED,
            [klass for _, klass in result.availability_classes],
            "the price really is source-dated, and saying otherwise would "
            "understate what the archive knows",
        )

    def test_a_fully_dated_archive_reports_source_declared_fidelity(self):
        """SEC filings all carry acceptance timestamps, so they replay clean."""
        store = SQLiteArchive(":memory:")
        for observation in (
            price_observation(),
            make_observation("obs-ni", "net_income", 101_464_000_000.0),
            make_observation("obs-assets", "assets", 3.0, available_at="2026-07-31T10:01:02.000Z"),
        ):
            store.record_observation("AAPL", observation)
        store.connection.commit()
        result = replay(store, "AAPL", "2026-12-31", replay_document)
        self.assertEqual(result.replay_fidelity, FIDELITY_SOURCE_DECLARED)
        store.close()

    def test_replaying_before_archival_yields_less_evidence_and_that_is_correct(self):
        """
        The reconstructive-versus-archival distinction, made concrete.

        The MSFT fixture was archived today, so a replay at its own price date
        of 2026-09-18 cannot know fundamentals the archive learned on
        2026-09-28. It builds, and it is emptier. Filling that gap would mean
        using today's knowledge to answer a question about an earlier day.
        """
        early = replay(
            self.store, "MSFT", self.document["as_of"], replay_document
        )
        self.assertIsNotNone(early.document)
        self.assertNotEqual(
            early.document["context_id"], self.document["context_id"]
        )
        self.assertLess(
            early.document["data_quality"]["evidence_coverage"]["available"],
            self.document["data_quality"]["evidence_coverage"]["available"],
            "an earlier replay must not know more than it did",
        )
        # The later replay does reproduce it exactly.
        later = replay(self.store, "MSFT", self.cutoff, replay_document)
        self.assertEqual(later.outcome, REPLAY_MATCH)


class TestReplayExclusion(unittest.TestCase):
    """Class B: later information is not used."""

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_a_later_filing_is_excluded_at_an_earlier_cutoff(self):
        self.store.record_observation(
            "AAPL", make_observation("obs-q1", "net_income", 100.0)
        )
        self.store.record_observation(
            "AAPL",
            make_observation(
                "obs-q2",
                "net_income",
                200.0,
                available_at="2026-10-01T10:00:00.000Z",
                accession="0000320193-26-000099",
            ),
        )
        self.store.connection.commit()

        before = self.store.observations_for("AAPL", "2026-09-30")
        self.assertEqual(
            [o.observation_id for o in before], ["obs-q1"],
            "a filing accepted after the cutoff must not be present",
        )
        after = self.store.observations_for("AAPL", "2026-10-02")
        self.assertEqual(len(after), 2)

    def test_an_excluded_observation_is_still_in_the_archive(self):
        """Replay filters. It does not delete."""
        observation = make_observation(
            "obs-later",
            "net_income",
            200.0,
            available_at="2026-10-01T10:00:00.000Z",
        )
        self.store.record_observation("AAPL", observation)
        self.store.connection.commit()
        self.store.observations_for("AAPL", "2026-09-30")
        self.assertEqual(self.store.observation_count(), 1)

    def test_replay_uses_the_contract_time_selector(self):
        """
        Requirement 15: one time-selection implementation, the contract's. The
        archive filters on its own column and then defers to
        `latest_knowable` for which restatement applies.
        """
        from data_contract import ObservationSet as ContractSet

        self.store.record_observation(
            "AAPL", make_observation("obs-q1", "net_income", 100.0)
        )
        self.store.record_observation(
            "AAPL",
            make_observation(
                "obs-q2",
                "net_income",
                200.0,
                available_at="2026-10-01T10:00:00.000Z",
                accession="0000320193-26-000099",
            ),
        )
        self.store.connection.commit()

        rows = self.store.observations_for("AAPL", "2026-09-30")
        self.assertEqual([o.observation_id for o in rows], ["obs-q1"])

        contract_set = ContractSet(ticker="AAPL", observations=rows)
        selected = contract_set.latest_knowable("2026-09-30", "net_income")
        self.assertIsNotNone(selected)
        self.assertEqual(selected.value, 100.0)


class TestHonestInsufficiency(unittest.TestCase):
    """Class C: a missing history is reported, never filled in."""

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_no_price_means_no_context_rather_than_a_substituted_one(self):
        """
        The highest-severity defect this phase could ship. A plausible,
        fully-populated document built from today's price is worse than no
        document at all.
        """
        self.store.record_observation(
            "AAPL", make_observation("obs-ni", "net_income", 100.0)
        )
        self.store.record_observation(
            "AAPL", make_observation("obs-assets", "assets", 1.0)
        )
        self.store.connection.commit()

        result = replay(self.store, "AAPL", "2026-09-30", replay_document)
        self.assertEqual(result.outcome, REPLAY_INSUFFICIENT)
        self.assertIsNone(result.document, "no document may be produced")
        self.assertIn("price", result.reason.lower())
        self.assertIn("substitute", result.reason.lower())

    def test_an_empty_archive_is_insufficient_and_says_so(self):
        result = replay(self.store, "AAPL", "2026-09-30", replay_document)
        self.assertEqual(result.outcome, REPLAY_INSUFFICIENT)
        self.assertIsNone(result.document)
        self.assertIn("nothing was substituted", result.reason.lower())

    def test_a_cutoff_before_the_archive_began_is_insufficient(self):
        """
        Nothing archived in 2026 makes 2024 replayable. The answer is an
        honest insufficiency, not an approximation.
        """
        self.store.record_observation("AAPL", price_observation())
        self.store.connection.commit()
        result = replay(self.store, "AAPL", "2020-01-01", replay_document)
        self.assertEqual(result.outcome, REPLAY_INSUFFICIENT)
        self.assertIsNone(result.document)

    def test_no_snapshot_is_reported_as_a_distinct_outcome(self):
        self.store.record_observation("AAPL", price_observation())
        self.store.record_observation(
            "AAPL",
            make_observation("obs-ni", "net_income", 101_464_000_000.0),
        )
        self.store.connection.commit()
        result = replay(self.store, "AAPL", "2026-09-30", replay_document)
        self.assertEqual(result.outcome, REPLAY_NO_SNAPSHOT)
        self.assertIsNotNone(
            result.document,
            "a reconstruction is still shown, just not as a match",
        )

    def test_market_data_from_observations_refuses_without_a_price(self):
        self.assertIsNone(
            market_data_from_observations(
                [make_observation("obs-ni", "net_income", 1.0)],
                ticker="AAPL",
            )
        )


class TestRestatementSurvival(unittest.TestCase):
    """Class D: both sides of an amendment remain historically distinguishable."""

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.store.record_observation(
            "AAPL",
            make_observation(
                "cmp-revenue-fy2007",
                "revenue",
                4_834_000_000.0,
                available_at="2007-11-01T16:30:00.000Z",
                accession="0001193125-07-000032",
            ),
        )
        self.store.record_observation(
            "AAPL",
            make_observation(
                "cmp-revenue-fy2007-amd",
                "revenue",
                6_119_000_000.0,
                available_at="2008-01-25T16:30:00.000Z",
                accession="0001193125-08-000204",
            ),
        )
        self.store.connection.commit()

    def test_replay_before_the_restatement_sees_the_original(self):
        rows = self.store.observations_for("AAPL", "2007-12-01")
        self.assertEqual([o.value for o in rows], [4_834_000_000.0])

    def test_replay_after_the_restatement_sees_the_restated_value(self):
        """
        Both restatements remain available; the contract's selector is what
        resolves which one applies at a given instant. The archive filters by
        eligibility and does not itself choose a value.
        """
        rows = self.store.observations_for("AAPL", "2008-02-01")
        self.assertEqual(
            sorted(o.value for o in rows),
            [4_834_000_000.0, 6_119_000_000.0],
        )
        observation_set = ObservationSet(ticker="AAPL", observations=rows)
        self.assertEqual(
            observation_set.latest_knowable("2008-02-01", "revenue").value,
            6_119_000_000.0,
        )

    def test_both_remain_in_the_archive(self):
        self.assertEqual(self.store.observation_count(), 2)
        lineages = self.store.lineage_for("AAPL", "revenue")
        self.assertEqual(lineages[0]["versions"], 2)

    def test_the_contract_selector_picks_the_restatement_when_appropriate(self):
        observation_set = ObservationSet(
            ticker="AAPL",
            observations=self.store.all_observations("AAPL"),
        )
        self.assertEqual(
            observation_set.latest_knowable("2007-12-01", "revenue").value,
            4_834_000_000.0,
        )
        self.assertEqual(
            observation_set.latest_knowable("2008-02-01", "revenue").value,
            6_119_000_000.0,
        )

    def test_a_restated_band_does_not_silently_win_at_an_earlier_cutoff(self):
        """
        A later run re-observes a band under the same canonical id. The
        earlier cutoff must still get the earlier value.
        """
        self.store.record_observation(
            "AAPL",
            make_observation(
                "ev-pe-band-001",
                "pe_band",
                {"10th": 20.0, "25th": 25.0, "median": 30.0,
                 "75th": 35.0, "90th": 40.0, "observations": 120},
                available_at="2026-07-31T10:01:02.000Z",
                accession="0000320193-26-000020",
            ),
        )
        self.store.record_observation(
            "AAPL",
            make_observation(
                "ev-pe-band-001",
                "pe_band",
                {"10th": 18.0, "25th": 23.0, "median": 28.0,
                 "75th": 33.0, "90th": 38.0, "observations": 121},
                available_at="2026-10-30T10:01:02.000Z",
                accession="0000320193-26-000099",
            ),
        )
        self.store.connection.commit()

        early = self.store.observations_for("AAPL", "2026-09-01")
        bands = [o for o in early if o.metric == "pe_band"]
        self.assertEqual([o.value["median"] for o in bands], [30.0])
        late = self.store.observations_for("AAPL", "2026-11-01")
        bands = [o for o in late if o.metric == "pe_band"]
        self.assertEqual([o.value["median"] for o in bands], [28.0])


class TestArchiveIndependence(unittest.TestCase):
    def test_the_archive_does_not_import_the_engine_or_a_storage_engine(self):
        """Invariant I9: the archive is a consumer, never a source."""
        import ast
        import inspect

        import archive
        import sqlite_archive

        for module in (archive, sqlite_archive):
            tree = ast.parse(inspect.getsource(module))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(
                        alias.name.split(".")[0] for alias in node.names
                    )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertNotIn("st_eva_runner", imported)
            self.assertNotIn("investment_context", imported)
            self.assertNotIn("cross_validation", imported)
            self.assertNotIn("sec_provider", imported)

    def test_sqlite_is_only_an_implementation_of_the_interface(self):
        self.assertTrue(issubclass(SQLiteArchive, ArchiveStore))
        self.assertTrue(issubclass(NullArchive, ArchiveStore))

    def test_the_null_archive_makes_the_layer_optional(self):
        """Invariant I10: deleting the archive deletes nothing the CLI needs."""
        null = NullArchive()
        self.assertEqual(null.observations_for("AAPL", "2030-01-01"), [])
        self.assertIsNone(null.context_at("AAPL", "2026-09-18"))
        null.record_observation("AAPL", price_observation())
        null.close()

    def test_a_replay_never_writes_to_the_archive(self):
        store = SQLiteArchive(":memory:")
        archive_fixture_run(store, "MSFT")
        before = store.observation_count()
        documents = store.document_count()
        replay(store, "MSFT", "2026-09-18", replay_document)
        self.assertEqual(store.observation_count(), before)
        self.assertEqual(store.document_count(), documents)
        store.close()


class TestRoundTripFidelity(unittest.TestCase):
    """
    A stored observation must come back as the same observation.

    Any lossy step shows up later as a replayed context that differs from the
    archived one for a reason that has nothing to do with the data, and the
    cheapest place to catch it is here.
    """

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_every_contract_field_survives_the_round_trip(self):
        original = make_observation("obs-filed", "net_income", 101_464_000_000.0)
        self.store.record_observation("AAPL", original)
        self.store.connection.commit()
        restored = self.store.all_observations("AAPL")[0]
        self.assertEqual(restored, original)

    def test_status_reasons_survive(self):
        original = make_observation("obs-filed", "net_income", 1.0)
        self.assertTrue(original.status_reasons)
        self.store.record_observation("AAPL", original)
        self.store.connection.commit()
        self.assertEqual(
            self.store.all_observations("AAPL")[0].status_reasons,
            original.status_reasons,
        )

    def test_a_fixture_observation_survives_a_full_pipeline_round_trip(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        for observation in material_observations(data).values():
            self.store.record_observation("MSFT", observation)
        self.store.connection.commit()
        restored = {
            observation.observation_id: observation
            for observation in self.store.all_observations("MSFT")
        }
        for original in material_observations(data).values():
            self.assertEqual(
                restored[original.observation_id],
                original,
                f"{original.observation_id} did not survive archival",
            )


class TestSecondSourceCannotReplaceTheEngineInput(unittest.TestCase):
    """
    The engine's view is material.

    A second source reports the same metric names. If a filing-sourced
    observation won the provenance selection, the engine would silently read
    the filing's figure instead of the market data source's, and the 2.3-B
    guarantee that the engine never depends on a second source would be false.
    """

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def test_the_view_keeps_the_market_data_figure(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        filing = make_observation(
            "cmp-revenue-sec-old",
            "revenue",
            1.0,
            period_start="2023-12-31",
            period_end="2024-03-30",
            as_of="2024-03-30",
            available_at="2024-05-02T22:04:25.000Z",
        )
        self.store.record_observation("MSFT", filing)
        for observation in material_observations(data).values():
            self.store.record_observation("MSFT", observation)
        self.store.connection.commit()

        rows = self.store.observations_for(
            "MSFT", archival_watermark(self.store, "MSFT")
        )
        rebuilt = market_data_from_observations(
            rows, ticker="MSFT", company_name=data.company_name
        )
        self.assertIsNotNone(rebuilt)
        self.assertEqual(
            rebuilt.current_revenue, data.current_revenue,
            "a filing-sourced figure replaced the engine's revenue",
        )
        observation = self.store.connection.execute(
            "SELECT provider FROM observations WHERE contract_id ="
            " 'ev-revenue-001'"
        ).fetchone()
        self.assertIn(observation["provider"], ("Yahoo", "RegressionFixture"))

    def test_a_comparable_observation_is_only_a_cross_source_input(self):
        data = CompanyResolver.resolve("MSFT", mode="regression")
        vendor = make_observation(
            "cmp-revenue-yahoo-undated",
            "revenue",
            9.99,
            available_at=None,
            available_at_basis=AvailabilityBasis.UNDECLARED.value,
            provider="YahooFinance",
            concept="trailingTotalRevenue",
            source_type=SourceType.API_LIVE.value,
        )
        rows = list(material_observations(data).values()) + [vendor]
        rebuilt = market_data_from_observations(rows, ticker="MSFT")
        self.assertIsNotNone(rebuilt)
        self.assertNotEqual(rebuilt.current_revenue, 9.99)


class TestSourceCapture(unittest.TestCase):
    """
    2.4.1: an observation must be traceable to the specific version of a
    document that produced it.

    A URL is not that. SEC data is updated as filings are disseminated and a
    filing can be corrected after acceptance, so the same URI can serve
    different bytes on different days. Only the captured version can say what
    a number was read from.
    """

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")

    def tearDown(self) -> None:
        self.store.close()

    def _document(self, content: str, document_type: str = "SEC_COMPANY_CONCEPT"):
        payload = content.encode("utf-8")
        return StoredDocument(
            content_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
            uri="https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/X.json",
            canonical_uri="https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/X.json",
            http_status=200,
            media_type="application/json",
            byte_size=len(payload),
            fetched_at="2026-09-28T12:00:00+00:00",
            first_seen_at="2026-09-28T12:00:00+00:00",
            payload=payload,
            provider="SecEdgar",
            document_type=document_type,
        )

    def test_captured_content_round_trips_byte_identically(self):
        document = self._document('{"units": {"USD": []}}')
        self.store.record_source_document(document)
        restored = self.store.content_for(document.content_hash)
        self.assertIsNotNone(restored)
        self.assertEqual(restored, document.payload)

    def test_the_content_hash_covers_the_uncompressed_bytes(self):
        """
        The hash must mean the same thing whether or not the payload is kept,
        otherwise a reference-only archive and a content archive would disagree
        about which documents they contain.
        """
        document = self._document('{"a": 1}')
        self.store.record_source_document(document)
        row = self.store.documents_summary()[0]
        self.assertEqual(row["content_hash"], document.content_hash)
        self.assertEqual(row["content_encoding"], "gzip")
        self.assertEqual(row["byte_size"], len(document.payload))

    def test_identical_content_is_stored_once_across_runs(self):
        """Content addressing: a stable endpoint costs one row forever."""
        first = self.store.record_source_document(self._document("same"))
        second = self.store.record_source_document(self._document("same"))
        self.assertEqual(first, second)
        self.assertEqual(self.store.document_count(), 1)

    def test_a_second_run_adds_no_bytes_when_nothing_changed(self):
        self.store.record_source_document(self._document("stable"))
        before = self.store.captured_bytes()
        self.store.record_source_document(self._document("stable"))
        self.assertEqual(self.store.captured_bytes(), before)

    def test_different_content_is_a_different_document(self):
        self.store.record_source_document(self._document("before"))
        self.store.record_source_document(self._document("after"))
        self.assertEqual(self.store.document_count(), 2)

    def test_the_document_type_and_provider_are_recorded(self):
        document = self._document("x", "SEC_SUBMISSIONS")
        self.store.record_source_document(document)
        row = self.store.documents_summary()[0]
        self.assertEqual(row["document_type"], "SEC_SUBMISSIONS")
        self.assertEqual(row["provider"], "SecEdgar")
        self.assertEqual(row["canonical_uri"], document.canonical_uri)

    def test_an_observation_links_to_the_documents_it_was_read_from(self):
        document = self._document("fact source")
        self.store.record_source_document(document)
        observation = make_observation(
            "obs-filed",
            "net_income",
            101_464_000_000.0,
        )
        self.store.record_observation(
            "AAPL", observation, document_hashes=[document.content_hash]
        )
        self.store.connection.commit()
        row = self.store.connection.execute(
            "SELECT observation_id FROM observations WHERE contract_id = ?",
            ("obs-filed",),
        ).fetchone()
        self.assertEqual(
            self.store.documents_for(row["observation_id"]),
            [self.store.document_id_for(document.content_hash)],
        )
        self.assertEqual(self.store.dangling_document_references(), [])

    def test_a_captured_document_is_never_deleted(self):
        """A referenced document is evidence, and this table offers no delete."""
        self.store.record_source_document(self._document("evidence"))
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute("DELETE FROM source_documents")

    def test_a_stored_document_must_be_complete(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO source_documents (document_id, content_hash,"
                " fetched_at, first_seen_at, content) VALUES"
                " ('d', 'h', '2026-01-01', '2026-01-01', X'00')"
            )

    def test_reference_only_capture_keeps_the_hash_but_no_payload(self):
        """
        Some sources are too large or too restricted to keep. The archive
        records the hash and the URI, and says so, rather than pretending an
        absent payload is an empty document.
        """
        reference_only = SQLiteArchive(":memory:", capture_content=False)
        try:
            document = self._document("not kept")
            reference_only.record_source_document(document)
            self.assertIsNone(
                reference_only.content_for(document.content_hash)
            )
            self.assertEqual(reference_only.documents_with_content(), 0)
            self.assertEqual(reference_only.document_count(), 1)
            row = reference_only.documents_summary()[0]
            self.assertIsNone(row["content_encoding"])
            self.assertEqual(row["content_hash"], document.content_hash)
            self.assertEqual(row["byte_size"], document.byte_size)
        finally:
            reference_only.close()

    def test_an_observation_records_its_document_hashes_in_raw(self):
        """The adapter knows which document it read; it must say so."""
        from data_contract import (
            AvailabilityBasis,
            SourceType,
            Unit,
            ValidationStatus,
        )

        observation = Observation(
            observation_id="cmp-net-income-sec-x",
            metric="net_income",
            value=1.0,
            unit=Unit.CURRENCY.value,
            currency="USD",
            currency_basis="REPORTED",
            period_start="2025-06-29",
            period_end="2026-06-27",
            as_of="2026-06-27",
            available_at="2026-07-31T10:01:02.000Z",
            available_at_basis=AvailabilityBasis.ACCEPTANCE_DATETIME.value,
            provider="SecEdgar",
            source_type=SourceType.REGULATORY_FILING.value,
            source_url="https://data.sec.gov/x",
            definition="d",
            methodology="m",
            retrieved_at="2026-09-28T12:00:00+00:00",
            raw={
                "sec_fact": {"accession": "0000320193-26-000020"},
                "source_document_hashes": ["sha256:abc", "sha256:def"],
            },
            status=ValidationStatus.UNVERIFIABLE,
        )
        self.assertEqual(
            _document_hashes_of(observation), ["sha256:abc", "sha256:def"]
        )
        self.assertEqual(
            _document_hashes_of(make_observation("x", "net_income", 1.0)),
            [],
            "an observation with no recorded document must yield no link",
        )


class TestLegacyCompatibility(unittest.TestCase):
    def test_the_cli_output_is_unchanged_by_the_archive_flag(self):
        for ticker in ("MSFT", "TENCENT", "NU"):
            with self.subTest(ticker=ticker):
                before = subprocess.run(
                    [sys.executable, "st_eva_runner.py", ticker, "--mode",
                     "regression", "--no-snapshot", "--json"],
                    cwd=str(REPO), capture_output=True, text=True,
                    encoding="utf-8",
                )
                self.assertEqual(before.returncode, 0, before.stderr[-400:])
                with tempfile.TemporaryDirectory() as directory:
                    archive = str(Path(directory) / "a.sqlite")
                    after = subprocess.run(
                        [sys.executable, "st_eva_runner.py", ticker, "--mode",
                         "regression", "--no-snapshot", "--json",
                         "--context", str(Path(directory) / "c.json"),
                         "--context-sources", "yahoo", "--archive", archive],
                        cwd=str(REPO), capture_output=True, text=True,
                        encoding="utf-8",
                    )
                    self.assertEqual(after.returncode, 0, after.stderr[-400:])
                    self.assertTrue(Path(archive).exists())
                self.assertEqual(
                    json.loads(before.stdout), json.loads(after.stdout)
                )


@unittest.skipUnless(
    os.environ.get("ST_EVA_LIVE") == "1",
    "live archive tests need ST_EVA_LIVE=1",
)
class TestLiveArchive(unittest.TestCase):
    def test_a_live_run_archives_and_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = str(Path(directory) / "live.sqlite")
            store = SQLiteArchive(archive)
            try:
                result = run_st_eva(
                    "AAPL",
                    mode="live",
                    save_snapshot=False,
                    context_path=str(Path(directory) / "ctx.json"),
                    context_sources=("yahoo", "sec"),
                    archive=store,
                )
                self.assertIsNotNone(result)
                document = json.loads(
                    (Path(directory) / "ctx.json").read_text(encoding="utf-8")
                )
                self.assertGreater(store.observation_count(), 0)
            finally:
                # Windows holds a lock on the file while the connection is
                # open, which would fail the temporary directory cleanup.
                store.close()

            store = SQLiteArchive(archive)
            try:
                replayed = replay(
                    store, "AAPL", archival_watermark(store, "AAPL"),
                    replay_document,
                )
                self.assertEqual(replayed.outcome, REPLAY_MATCH, replayed.reason)
                # A live vendor figure is archive-dated, so the replay is
                # honest about being observational even though it reproduces
                # the archived document exactly.
                self.assertEqual(
                    replayed.replay_fidelity, FIDELITY_OBSERVATIONAL
                )
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
