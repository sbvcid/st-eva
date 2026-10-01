"""
2.7: cross-framework and applicability generalisation.

The tests a second framework and a second business model have to pass before
either is called generalised. Written against a fixture rather than against the
cross-framework archive on purpose -- the archive is a build artefact and is not
committed, so a test that needs it would be a test that cannot run, and this is
the layer where the invariants belong anyway.

What is here, in the order the phase asked the questions:

    a filer's own classification, read from its submission
    a metric inapplicable to a kind of company, derived rather than asserted
    applicable-and-empty, which is not the same as inapplicable
    an inapplicability ruling that needs a recorded business model
    a concept mapped into an existing metric across a framework boundary
    a similar label that does not earn an EXACT mapping
    a filing identity for every accession a fact came from
"""

import contextlib
import json
import os
import sqlite3
import sys
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from archive import FilingRef, StoredDocument  # noqa: E402
from core_registry import CoreRegistry, RegistryError, concept_id_for  # noqa: E402
from data_contract import utc_now  # noqa: E402
from evidence_model import (  # noqa: E402
    NO_OBSERVATIONS,
    NOT_APPLICABLE,
    SOURCE_REPORTED,
    UNAVAILABLE,
)
from evidence_query import APPLICABLE, EvidenceQuery  # noqa: E402
from registry_seed import METRICS as SEED_METRICS  # noqa: E402
from registry_seed import seed  # noqa: E402
from sec_ingest import (  # noqa: E402
    Ingestor,
    business_model_from_filer_classification,
)
from sqlite_archive import SQLiteArchive  # noqa: E402

IFRS_FULL = "ifrs-full"
AAPL = "AAPL"


def _now():
    return datetime.now(timezone.utc).isoformat()


class TestAFilersOwnClassification(unittest.TestCase):
    """
    The classification is the filer's, read from its submission.

    Not inferred from which concepts it happens to report, and not looked up in
    a table of companies. Both of those would let the answer depend on what the
    archive already holds, which is the failure the 2.5.1 adoption split was
    written to remove in a different place.
    """

    def test_a_finance_filer_resolves_from_its_sic(self):
        model, source = business_model_from_filer_classification({
            "sic": "6199", "sicDescription": "Finance Services",
        })
        self.assertEqual(model, "FINANCE_SERVICES")
        self.assertIn("6199", source)

    def test_a_manufacturer_resolves_from_its_sic(self):
        model, _ = business_model_from_filer_classification({
            "sic": "3674", "sicDescription": "Semiconductors & Related Devices",
        })
        self.assertEqual(model, "MANUFACTURING")

    def test_a_classification_outside_the_vocabulary_rules_nothing_out(self):
        """
        An unrecognised classification makes no ruling, and that is the answer.

        The dangerous direction to get wrong is the one where an issuer we cannot
        classify has a metric silently removed from its coverage. Returning
        `None` means every declared metric stays applicable and the issuer is
        asked about all of them, which is a recoverable mistake; returning
        something invented would not be.
        """
        model, source = business_model_from_filer_classification({
            "sic": "5141", "sicDescription": "Warehousing and Storage",
        })
        self.assertIsNone(model)
        self.assertIn("5141", source)

    def test_a_submitted_classification_with_no_sic_makes_no_ruling(self):
        model, source = business_model_from_filer_classification({})
        self.assertIsNone(model)
        self.assertIsNone(source)


class ArchiveFixture(unittest.TestCase):
    """One store, seeded, with an issuer that can be classified."""

    def setUp(self):
        self.store = SQLiteArchive(":memory:")
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.connection = self.store.connection
        self.asset_id = self.store.record_asset(AAPL, cik="0000320193", name="X")
        self.query = EvidenceQuery(connection=self.store.connection)

    def tearDown(self):
        self.store.close()

    def classify(self, model="BANK", source="SIC 6022 State Commercial Banks"):
        """
        Default to `BANK`, and make the one refusal these tests need.

        It was `FINANCE_SERVICES` when this file was written. 2.23 refuted
        `gross_profit` for `BANK`; 2.25 refuted the remaining exclusions; and
        2.25's contract change left a refusal reachable only at state
        `SUPPORTED`, of which there is none. So the behaviour 2.7 was written to
        protect -- an inapplicable metric is not a failed retrieval -- is now
        exercised against a refusal somebody makes, which is the only way one can
        come into existence.
        """
        with self.writable():
            self.registry.support_exclusion("operating_income", "BANK")
        with self.writable():
            self.registry.set_issuer_business_model(
                self.asset_id, model, basis="DECLARED_BY_ISSUER", source=source
            )
        with self.writable():
            self.registry.set_issuer_business_model(
                self.asset_id, model, basis="DECLARED_BY_ISSUER", source=source
            )

    @contextlib.contextmanager
    def writable(self):
        """
        Lift `query_only` for a write, and put it straight back.

        `EvidenceQuery` marks the shared connection read-only, which is the right
        guarantee for the read surface and the wrong one for a fixture that is
        building the archive it will read. Restored rather than left off, so the
        guarantee the production surface provides is the one these tests run
        under.
        """
        self.connection.execute("PRAGMA query_only = OFF")
        try:
            yield
        finally:
            self.connection.execute("PRAGMA query_only = ON")

    def add_observation(self, metric, value="100.0", currency="USD"):
        observation_id = "obs_" + uuid.uuid4().hex
        fact_id = "sfid_" + uuid.uuid4().hex
        with self.writable():
            # The observation's lineage is a foreign key, so the row has to
            # exist before the observation that points at it.
            self.connection.execute(
                "INSERT OR IGNORE INTO observation_lineage (lineage_id,"
                " asset_id, metric, concept, period_start, period_end,"
                " created_at, note) VALUES ('l1', ?, ?, 'us-gaap:Revenues',"
                " '2023-01-01', '2023-12-31', ?, 'test')",
                (self.asset_id, metric, _now()),
            )
            self.connection.execute(
                "INSERT INTO observations (observation_id, contract_id,"
                " asset_id, lineage_id, metric, provider, source_type,"
                " source_url, concept, value_json, unit, currency,"
                " currency_basis, period_start, period_end, as_of, available_at,"
                " available_at_basis, availability_class, retrieved_at,"
                " first_archived_at, replay_eligible_from, definition,"
                " methodology, status, status_reasons_json, inputs_json,"
                " observation_count, raw_json, content_hash, basis_json, taxonomy,"
                " accession, form, fiscal_year, fiscal_period, statement,"
                " instant, source_fact_id, source_concept_ref)"
                " VALUES (?, 'c1', ?, 'l1', ?, 'SecEdgar', 'REGULATORY_FILING',"
                " NULL, 'us-gaap:Revenues', ?, 'currency', ?, 'REPORTED',"
                " '2023-01-01', '2023-12-31', '2023-12-31', '2024-02-01',"
                " 'ACCEPTANCE_DATETIME', 'FILING_ACCEPTED', '2024-02-01',"
                " '2024-02-02', '2024-02-01', 'd', 'm', 'UNVERIFIABLE', '[]',"
                " '[]', NULL, '{}', 'h2', '{}', 'us-gaap',"
                " '0000320193-24-000001', '10-K', 2023, 'FY', 'INCOME', 0,"
                " ?, NULL)",
                (observation_id, self.asset_id, metric, value, currency, fact_id),
            )
            self.connection.commit()
        return observation_id


class TestInapplicabilityIsDerived(ArchiveFixture):
    """
    A metric that does not exist for this kind of company, from two facts.

    The registry declares the exclusion and the issuer is classified; together
    they determine the answer, and neither is asserted per issuer. Before 2.7 the
    archive had nowhere to put the second fact, so the declaration was
    unreachable and the surface fell through to `UNAVAILABLE` -- reporting a
    failed retrieval for a line of business that does not have one.
    """

    def test_an_inapplicable_metric_is_not_a_failed_retrieval(self):
        self.classify()
        report = self.query.coverage_report(AAPL)
        by_metric = {e["metric"]: e for e in report["metrics"]}
        self.assertEqual(by_metric["operating_income"]["state"], NOT_APPLICABLE)
        self.assertEqual(
            by_metric["operating_income"]["reason_code"],
            "BUSINESS_MODEL_NOT_MEANINGFUL",
        )
        self.assertEqual(
            by_metric["operating_income"]["applicability"], NOT_APPLICABLE
        )
        # And it is not the retrieval failure it used to be reported as.
        self.assertNotEqual(by_metric["operating_income"]["state"], UNAVAILABLE)

    def test_gross_profit_is_no_longer_inapplicable_to_any_financial_class(self):
        """
        2.23 refuted this for `BANK` and 2.25 for `FINANCE_SERVICES`.

        The exclusion is gone entirely, and this test is the one that will fail if
        anyone puts it back. The behaviour 2.7 protects -- an inapplicable metric
        is not a failed retrieval -- is unchanged and still exercised by
        `operating_income`, which is the only standing proposition.
        """
        report = self.query.coverage_report(AAPL)
        by_metric = {e["metric"]: e for e in report["metrics"]}
        self.assertEqual(by_metric["gross_profit"]["applicability"], APPLICABLE)
        self.assertNotEqual(by_metric["gross_profit"]["state"], NOT_APPLICABLE)

    def test_an_unclassified_issuer_gets_no_ruling(self):
        """
        An unknown kind of business is not evidence that a metric is meaningless.
        """
        report = self.query.coverage_report(AAPL)
        by_metric = {e["metric"]: e for e in report["metrics"]}
        self.assertNotEqual(by_metric["operating_income"]["state"], NOT_APPLICABLE)
        self.assertEqual(
            by_metric["operating_income"]["applicability"], APPLICABLE
        )

    def test_applicable_and_never_collected_is_its_own_state(self):
        """
        The three facts, and the two that used to be one.

            NOT_APPLICABLE   the metric does not exist for this company
            NO_OBSERVATIONS  it applies and nothing has been collected
            UNAVAILABLE      an attempt was made and produced nothing
        """
        self.classify()
        report = self.query.coverage_report(AAPL)
        by_metric = {e["metric"]: e for e in report["metrics"]}
        # Not classified as a financial institution, so applicable and empty.
        self.assertEqual(
            by_metric["capex"]["state"], NO_OBSERVATIONS
        )
        self.assertEqual(by_metric["capex"]["applicability"], APPLICABLE)
        self.assertEqual(by_metric["capex"]["reason_code"], "NOT_YET_COLLECTED")
        # Inapplicable, and *not* "not yet collected".
        self.assertEqual(by_metric["operating_income"]["state"], NOT_APPLICABLE)
        self.assertNotEqual(
            by_metric["operating_income"]["reason_code"], "NOT_YET_COLLECTED"
        )

    def test_an_observation_with_a_value_is_never_not_yet_collected(self):
        """
        A regression guard for a real mistake, not a hypothetical one.

        The first cut overloaded `has_value=None` to mean "no rows", which is
        also what the per-observation package passes when it is not asking the
        question at all. Every observation therefore reported its own state as
        NOT_YET_COLLECTED -- an observation with a value in it, described as
        never collected. The named flag exists so that cannot recur.
        """
        self.add_observation("revenue", "100.0")
        rows = self.query.query_observations(asset=AAPL, metric="revenue")
        self.assertEqual(
            rows[0]["status"]["evidence_state"]["state"], SOURCE_REPORTED
        )

    def test_the_business_model_basis_is_kept(self):
        self.classify()
        report = self.query.coverage_report(AAPL)
        self.assertEqual(
            report["business_model"]["basis"], "DECLARED_BY_ISSUER"
        )
        self.assertIn("6022", report["business_model"]["source"])

    def test_a_declared_classification_must_name_its_source(self):
        with self.assertRaises(RegistryError):
            self.registry.set_issuer_business_model(
                self.asset_id, "FINANCE_SERVICES",
                basis="DECLARED_BY_ISSUER", source=None,
            )

    def test_the_database_refuses_an_unknown_business_model(self):
        with self.writable(), self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute(
                "INSERT INTO issuer_business_model (asset_id, business_model,"
                " basis, source, recorded_at) VALUES (?, 'CRYPTO', ?, ?, ?)",
                (self.asset_id, "MANUAL_CLASSIFICATION", "guess", _now()),
            )

    def test_an_older_archive_still_answers(self):
        """
        The read path must not require a migration it cannot demand.

        Every 2.1 to 2.6 result was read out of an archive built before 0010, and
        applying the migration to it would change the ground truth those results
        were graded against. An archive with no such table therefore answers
        "no classifications recorded", which is exactly what it knew before.
        """
        store = SQLiteArchive(":memory:")
        store.connection.execute("DROP TABLE issuer_business_model")
        store.connection.execute(
            "DELETE FROM schema_migrations WHERE version = 10"
        )
        registry = CoreRegistry(store.connection)
        seed(registry)
        asset_id = store.record_asset(AAPL, cik="1", name="X")
        self.assertIsNone(registry.business_model_of(asset_id))
        query = EvidenceQuery(connection=store.connection)
        report = query.coverage_report(AAPL)
        self.assertNotIn(
            NOT_APPLICABLE,
            {e["state"] for e in report["metrics"]},
        )
        store.close()


class TestTheFilingIdentityIsWritten(ArchiveFixture):
    """
    Every accession a fact came from has a filing row behind it.

    `held_filings` is written from the submissions index, and that index is
    bounded. Company facts reach much further back, so facts were being stored
    for accessions the index never mentioned, and the provenance chain stopped
    one link short for each of them. Pre-existing: the sealed 2.6 archive has the
    same gap for 30 of its 74 accessions.
    """

    class Index:
        """A provider that knows the index and nothing else."""

        def __init__(self, entries):
            self.entries = entries

        def submissions(self, cik):
            return {"sic": "3571", "sicDescription": "Electronic Computers",
                    "filings": {"recent": {}}}

        def filing_index(self, cik):
            return self.entries

        def companyconcept(self, cik, taxonomy, concept):
            return None

        def documents_for(self, taxonomy, concept):
            return []

    def test_a_fact_from_outside_the_index_still_gets_a_filing(self):
        old = {
            "accessionNumber": ["0001193125-09-214859"],
            "filingDate": ["2009-10-27"],
            "reportDate": ["2009-10-27"],
            "form": ["10-K"],
            "primaryDocument": ["a.htm"],
        }
        provider = self.Index([old])
        ingestor = Ingestor(self.store, provider, self.registry)
        with self.writable():
            ingestor._ensure_filing_identity(
                self.asset_id, "0001193125-09-214859",
                {"form": "10-K", "filed": "2009-10-27"},
            )
        row = self.connection.execute(
            "SELECT form, filed_at FROM held_filings WHERE accession = ?",
            ("0001193125-09-214859",),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["form"], "10-K")
        self.assertEqual(row["filed_at"], "2009-10-27")

    def test_an_existing_filing_row_is_not_overwritten(self):
        """
        The index is the better source for a filing the index actually lists.
        """
        self.classify()
        ingestor = Ingestor(self.store, self.Index([]), self.registry)
        with self.writable():
            ingestor._record_filing(
                self.asset_id,
                {"accession": "0001-1", "form": "10-K",
                 "filing_date": "2024-01-02"},
                "doc_1",
            )
            ingestor._ensure_filing_identity(
                self.asset_id, "0001-1", {"form": "8-K", "filed": "1999-01-01"}
            )
        row = self.connection.execute(
            "SELECT form, document_id FROM held_filings WHERE accession = ?",
            ("0001-1",),
        ).fetchone()
        self.assertEqual(row["form"], "10-K")
        self.assertEqual(row["document_id"], "doc_1")

    def test_an_empty_accession_is_not_a_filing(self):
        ingestor = Ingestor(self.store, self.Index([]), self.registry)
        with self.writable():
            ingestor._ensure_filing_identity(
                self.asset_id, "", {"form": "10-K"}
            )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM held_filings"
            ).fetchone()[0],
            0,
        )


class TestTheFrameworkIsNotAShortcut(ArchiveFixture):
    """
    A second accounting framework, reached through the same registry.

    The whole claim of 2.7 is that a semantic metric is reached through
    whichever source concept the filer used, with no issuer, no framework branch
    and no new column. These are the tests that would fail if that stopped being
    true.
    """

    def test_one_metric_is_reachable_from_both_taxonomies(self):
        revenue = {
            m.concept_id.split(":", 1)[0]
            for m in self.registry.mappings_for_metric("revenue")
        }
        self.assertIn("us-gaap", revenue)
        self.assertIn(IFRS_FULL, revenue)

    def test_a_similar_label_does_not_earn_an_exact_mapping(self):
        """
        The single most important assertion in the phase.

        `ifrs-full:Revenue` reads like `us-gaap:Revenues` and does not mean the
        same thing: the IFRS element is an aggregate of ordinary-activity income
        that may carry interest, dividend and royalty income, while the concept
        the metric calls exact is contracts-with-customers only, which is a
        component of it. A promotion to EXACT on the strength of the spelling
        fails here.
        """
        mapping = next(
            m for m in self.registry.mappings_for_metric("revenue")
            if m.concept_id == concept_id_for(IFRS_FULL, "Revenue")
        )
        self.assertEqual(mapping.mapping_type, "PARTIAL")
        self.assertFalse(mapping.series_continues)

    def test_an_exact_mapping_never_comes_from_the_second_framework(self):
        for entry in self.registry.mappings_for_metric("revenue"):
            if entry.mapping_type == "EXACT":
                self.assertTrue(entry.concept_id.startswith("us-gaap:"))

    def test_a_partial_mapping_across_frameworks_records_a_window(self):
        """
        The 2.5.1 rule, and the reason it is a rule.

        A series does not continue across a partial boundary, so the boundary
        has to be visible. The window has to be evidence-derived too: dating the
        mapping from the day it was written would hide the concept for every
        historical period, which is the same silent loss as an undiscoverable
        fact.
        """
        for metric in ("revenue", "net_income", "shares_outstanding", "debt"):
            for entry in self.registry.mappings_for_metric(metric):
                if entry.mapping_type == "PARTIAL" and entry.concept_id.startswith(
                    IFRS_FULL + ":"
                ):
                    self.assertTrue(
                        entry.effective_from,
                        f"{entry.concept_id} is partial with no window",
                    )
                    self.assertIsNone(entry.effective_to)

    def test_no_metric_definition_names_an_issuer(self):
        for metric in SEED_METRICS:
            self.assertNotIn("AAPL", metric.semantic_definition)
            self.assertNotIn("TSM", metric.semantic_definition)
            self.assertNotIn("NU", metric.semantic_definition)

    def test_the_registry_reaches_an_ifrs_concept_by_asking(self):
        contract = self.registry.resolve(
            concept_id_for(IFRS_FULL, "Assets"), as_of="2024-01-01"
        ).contract_dict()
        self.assertTrue(contract["resolved"])
        self.assertEqual(contract["concept"], "ifrs-full:Assets")
        self.assertEqual(contract["metric"], "assets")
        self.assertEqual(contract["mappings"][0]["mapping_type"], "EXACT")


if __name__ == "__main__":
    unittest.main()