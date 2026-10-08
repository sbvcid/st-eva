"""
ST-EVA Phase 2A - filing metadata acquisition in production ingestion.

Fifteen assertions about the first point at which SEC provenance becomes visible
in a real ingest run. Every provider here is a fixture; nothing opens a socket.

The reason this phase needed its own careful tests is that it is the first change
to touch the module the observation pipeline lives in. `record_observation` is
required to behave exactly as it did before, so the load-bearing assertions are
the negative ones:

    * the same ingest, once with provenance and once without it, writes
      **byte-identical** `observations` -- every column, every row, both compared
      by value rather than by count;
    * nothing calls `index.json`, the full submission, or any document URI;
    * no SGML parser is imported, let alone reached;
    * none of the six document-side relations gains a row.

And the positive ones, which are where the interesting decisions live:

    * an item string the Submissions API publishes becomes one declaration plus
      its parsed items, with the raw string kept unsplit;
    * a `PRECISION_DATE` acceptance value is **not** recorded as an EDGAR
      acceptance, because on the bootstrap path that value is a fact's own filed
      date -- the exact fabrication the frozen design forbids;
    * a `fiscalYearEnd` that is not four digits produces no declaration at all
      rather than a malformed one;
    * a second identical ingest writes nothing, and a source that changed its
      mind writes a second row while the first is untouched.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional, Tuple

from core_registry import CoreRegistry
from data_contract import PRECISION_DATE, PRECISION_INSTANT
from registry_seed import seed
from sec_ingest import Ingestor
from sec_provider import SECDocument, content_hash_of
from sqlite_archive import SQLiteArchive

TICKER = "AAPL"
CIK = "0000320193"
ACCESSION = "0000320193-26-000018"
OLD_ACCESSION = "0001193125-13-170623"
EXHIBIT = "a8-kex991q3202606272026.htm"

DOCUMENT_RELATIONS = (
    "filing_document_declarations", "filing_documents",
    "filing_document_captures", "filing_document_statements",
    "observation_filing_documents",
)


def submissions_payload(items: str = "2.02,9.01",
                        fiscal_year_end: str = "0926") -> Dict[str, Any]:
    return {
        "cik": CIK,
        "sic": "3571",
        "sicDescription": "Electronic Computers",
        "fiscalYearEnd": fiscal_year_end,
        "exchanges": ["Nasdaq"],
        "tickers": ["AAPL"],
        "filings": {"recent": {
            "accessionNumber": [ACCESSION],
            "form": ["8-K"],
            "filingDate": ["2026-07-30"],
            "reportDate": ["2026-07-30"],
            "acceptanceDateTime": ["2026-07-31T00:30:28.000Z"],
            "primaryDocument": ["aapl-20260730.htm"],
            "isXBRL": [1],
            "items": [items],
        }},
    }


def index_entry(**overrides: Any) -> Dict[str, Any]:
    entry = {
        "accession": ACCESSION,
        "form": "8-K",
        "filing_date": "2026-07-30",
        "report_date": "2026-07-30",
        "acceptance_datetime": "2026-07-31T00:30:28.000Z",
        "acceptance_precision": PRECISION_INSTANT,
        "primary_document": "aapl-20260730.htm",
        "is_xbrl": 1,
    }
    entry.update(overrides)
    return entry


def concept_payload(accession: str = ACCESSION, form: str = "10-Q",
                    filed: str = "2026-05-01",
                    fiscal_year: int = 2026) -> Dict[str, Any]:
    return {"cik": CIK, "taxonomy": "us-gaap",
            "tag": "EarningsPerShareDiluted", "label": "EPS",
            "description": "Diluted EPS",
            "units": {"USD/shares": [{
                "start": "2026-01-01", "end": "2026-03-28", "val": 1.65,
                "accn": accession, "fy": fiscal_year, "fp": "Q2",
                "frame": "CY2026Q1", "form": form, "filed": filed,
            }]}}


class RecordingProvider:
    """A fixture provider that records what was asked and refuses the documents."""

    def __init__(self, entries: Optional[List[Dict[str, Any]]] = None,
                 submissions: Optional[Dict[str, Any]] = None,
                 payload: Optional[Dict[str, Any]] = None) -> None:
        self.entries = [index_entry()] if entries is None else entries
        self._submissions = submissions_payload() if submissions is None \
            else submissions
        self._payload = concept_payload() if payload is None else payload
        self.submissions_calls = 0
        self.index_calls = 0
        self.document_endpoints_called: List[str] = []

    # -- resources this phase must never reach -------------------------
    #
    # Phase 2B authorises the two manifests, so they are served -- as `None`,
    # meaning "this provider has nothing for that accession", which is what a
    # bootstrap archive or a provider without Archives access looks like. What is
    # never authorised at any phase so far is an individual document.

    def filing_directory(self, cik: str, accession: str) -> None:
        self.document_endpoints_called.append("filing_directory")
        return None

    def full_submission(self, cik: str, accession: str) -> None:
        self.document_endpoints_called.append("full_submission")
        return None

    def filing_document(self, *args: Any, **kwargs: Any) -> None:
        self.document_endpoints_called.append("filing_document")
        raise AssertionError("no phase so far may fetch a filing document")

    # -- the endpoints Phase 2A does use -------------------------------

    def submissions(self, cik: str) -> Dict[str, Any]:
        self.submissions_calls += 1
        return self._submissions

    def filing_index(self, cik: str) -> List[Dict[str, Any]]:
        self.index_calls += 1
        return [dict(entry) for entry in self.entries]

    def resolve_company(self, ticker: str) -> Any:
        class Company:
            pass

        company = Company()
        company.cik = CIK
        company.name = "Apple Inc."
        company.ticker = TICKER
        return company

    def concept_history(self, cik: str, taxonomy: str,
                        concept: str) -> Optional[Dict[str, Any]]:
        return self._payload

    def documents_for(self, taxonomy: str, concept: str) -> Tuple[Any, ...]:
        body = b'{"units": {}}'
        return (SECDocument(
            content_hash=content_hash_of(body),
            uri="https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193"
                "/us-gaap/EarningsPerShareDiluted.json",
            payload=body, media_type="application/json", byte_size=len(body),
            http_status=200, fetched_at="2026-08-01T00:00:00Z",
            provider="SecEdgar", document_type="SEC_COMPANY_CONCEPT",
        ),)

    def transport_stats(self) -> Dict[str, Any]:
        return {"requests_made": 1, "bytes_downloaded": 0,
                "documents_retained": 1, "unique_document_bytes": 1}

    @property
    def network_fetches(self) -> int:
        return self.submissions_calls + self.index_calls

    @property
    def concept_fetches(self) -> int:
        return 1


class AcquisitionBase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.provider = RecordingProvider()
        self.ingestor = Ingestor(self.store, self.provider, self.registry)
        # Resolved after the asset exists, so a test can build its own
        # declaration against the same asset the ingest will use.
        self.store.record_asset(TICKER, cik=CIK, name="Apple Inc.")
        self.asset_id = self.store.asset_id_for_cik(CIK)

    def tearDown(self) -> None:
        self.store.close()

    def count(self, table: str, where: str = "", *args: Any) -> int:
        clause = f" WHERE {where}" if where else ""
        return self.connection.execute(
            f"SELECT COUNT(*) FROM {table}{clause}", args
        ).fetchone()[0]

    @property
    def connection(self):
        return self.store.connection

    def rows(self, table: str, order: str = "rowid") -> List[Tuple[Any, ...]]:
        return [
            tuple(row) for row in self.connection.execute(
                f"SELECT * FROM {table} ORDER BY {order}"
            )
        ]

    def document_table_snapshot(self) -> Dict[str, int]:
        return {
            table: self.count(table) for table in DOCUMENT_RELATIONS
        }


# --------------------------------------------------------------------------
# 1-3. Filing identity and declarations
# --------------------------------------------------------------------------


class TestFilingAcquisition(AcquisitionBase):
    def test_a_normal_ingest_records_the_index_declaration(self):
        report = self.ingestor.ingest(TICKER, metrics=["eps_diluted"],
                                      forms=["8-K"])
        self.assertEqual([], report.errors)
        self.assertEqual(1, self.count("filings", "accession = ?", ACCESSION))
        row = self.connection.execute(
            "SELECT declaration_source, form, filing_date, report_date,"
            " primary_document, is_xbrl, capture_kind FROM"
            " filing_declarations WHERE accession = ?", (ACCESSION,)
        ).fetchone()
        self.assertEqual("SUBMISSIONS_API_FILING_INDEX",
                         row["declaration_source"])
        self.assertEqual("8-K", row["form"])
        self.assertEqual("2026-07-30", row["filing_date"])
        self.assertEqual("2026-07-30", row["report_date"])
        self.assertEqual("aapl-20260730.htm", row["primary_document"])
        self.assertEqual(1, row["is_xbrl"])
        self.assertEqual("FIRST_HAND", row["capture_kind"])

    def test_a_filing_row_carries_no_metadata(self):
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        columns = {
            r["name"] for r in self.connection.execute(
                "PRAGMA table_info(filings)"
            )
        }
        self.assertEqual({"asset_id", "accession", "first_archived_at"},
                         columns)

    def test_filing_identity_is_idempotent_across_runs(self):
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        first_archived = self.connection.execute(
            "SELECT first_archived_at FROM filings WHERE accession = ?",
            (ACCESSION,),
        ).fetchone()[0]
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.assertEqual(1, self.count("filings", "accession = ?", ACCESSION))
        self.assertEqual(
            first_archived,
            self.connection.execute(
                "SELECT first_archived_at FROM filings WHERE accession = ?",
                (ACCESSION,),
            ).fetchone()[0],
        )

    def test_a_changed_assertion_adds_a_row_and_keeps_the_first(self):
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        # The same source now reports a different report date, which is a
        # different assertion rather than a correction of the old one.
        self.provider.entries = [index_entry(report_date="2026-07-31")]
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        dates = sorted(
            r[0] for r in self.connection.execute(
                "SELECT report_date FROM filing_declarations"
                " WHERE declaration_source = 'SUBMISSIONS_API_FILING_INDEX'"
            )
        )
        self.assertEqual(["2026-07-30", "2026-07-31"], dates)
        # The earlier declaration is untouched rather than amended.
        self.assertEqual(2, self.count(
            "filing_declarations",
            "declaration_source = 'SUBMISSIONS_API_FILING_INDEX'"
        ))

    def test_a_fact_outside_the_index_still_gets_filing_identity(self):
        # The index lists one filing; the fact belongs to a different, older
        # accession the bounded index will never mention.
        provider = RecordingProvider(payload=concept_payload(
            accession=OLD_ACCESSION, form="10-K", filed="2013-04-24",
            fiscal_year=2013))
        ingestor = Ingestor(self.store, provider, self.registry)
        ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.assertEqual(
            1, self.count("filings", "accession = ?", OLD_ACCESSION)
        )
        self.assertEqual(
            0, self.count("filing_declarations",
                          "accession = ? AND declaration_source = ?",
                          OLD_ACCESSION, "SUBMISSIONS_API_FILING_INDEX"),
        )
        row = self.connection.execute(
            "SELECT declaration_source, form, filing_date, report_date FROM"
            " filing_declarations WHERE accession = ?", (OLD_ACCESSION,)
        ).fetchone()
        self.assertEqual("FACT_RECORD", row["declaration_source"])
        self.assertEqual("10-K", row["form"])
        self.assertEqual("2013-04-24", row["filing_date"])
        # The fact's `end` is the period it covers, not a filing attribute.
        self.assertIsNone(row["report_date"])

    def test_no_sgml_declaration_is_invented(self):
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.assertEqual(
            0,
            self.count("filing_declarations",
                       "declaration_source = 'SGML_SUBMISSION_HEADER'"),
        )


# --------------------------------------------------------------------------
# 4-5. Items
# --------------------------------------------------------------------------


class TestItemAcquisition(AcquisitionBase):
    def test_the_api_item_string_becomes_one_declaration_and_its_items(self):
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        declaration = self.connection.execute(
            "SELECT declaration_id, declaration_source, raw_items_text,"
            " declared_item_count FROM filing_item_declarations"
        ).fetchone()
        self.assertEqual("SUBMISSIONS_API_ITEMS",
                         declaration["declaration_source"])
        self.assertEqual("2.02,9.01", declaration["raw_items_text"])
        self.assertEqual(2, declaration["declared_item_count"])
        items = [
            (r["item_ordinal"], r["item_code"])
            for r in self.connection.execute(
                "SELECT item_ordinal, item_code FROM filing_items"
                " ORDER BY item_ordinal"
            )
        ]
        self.assertEqual([(1, "2.02"), (2, "9.01")], items)

    def test_the_item_parse_is_deterministic(self):
        from sec_provenance import parse_items

        self.assertEqual(((1, "2.02"), (2, "9.01")),
                         parse_items("2.02,9.01"))
        self.assertEqual(parse_items("2.02,9.01"), parse_items(" 2.02 , 9.01 "))
        self.assertEqual(parse_items("2.02"), parse_items("2.02,"))
        self.assertEqual((), parse_items(""))
        self.assertEqual((), parse_items("  ,  "))

    def test_an_absent_or_empty_item_string_yields_no_declaration(self):
        for value in ("", "   "):
            provider = RecordingProvider(
                submissions=submissions_payload(items=value))
            ingestor = Ingestor(self.store, provider, self.registry)
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            self.assertEqual(
                0, self.count("filing_item_declarations"),
                f"items={value!r} produced a declaration",
            )

    def test_the_index_carries_no_items_and_none_are_invented(self):
        self.assertNotIn("items", self.provider.entries[0])
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        sources = {
            r[0] for r in self.connection.execute(
                "SELECT DISTINCT declaration_source FROM"
                " filing_item_declarations"
            )
        }
        self.assertEqual({"SUBMISSIONS_API_ITEMS"}, sources)


# --------------------------------------------------------------------------
# 6-7. Acceptance
# --------------------------------------------------------------------------


class TestAcceptanceAcquisition(AcquisitionBase):
    def test_an_instant_acceptance_becomes_a_declaration(self):
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        row = self.connection.execute(
            "SELECT acceptance_source, acceptance_datetime,"
            " acceptance_precision, raw_value FROM filing_acceptances"
        ).fetchone()
        self.assertEqual("SUBMISSIONS_API_ACCEPTANCE_DATETIME",
                         row["acceptance_source"])
        self.assertEqual("2026-07-31T00:30:28.000Z", row["acceptance_datetime"])
        self.assertEqual(PRECISION_INSTANT, row["acceptance_precision"])

    def test_a_consulted_source_that_declared_nothing_is_none_with_null(self):
        provider = RecordingProvider(
            entries=[index_entry(acceptance_datetime="",
                                 acceptance_precision=PRECISION_INSTANT)])
        ingestor = Ingestor(self.store, provider, self.registry)
        ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        row = self.connection.execute(
            "SELECT acceptance_datetime, acceptance_precision, raw_value"
            " FROM filing_acceptances"
        ).fetchone()
        self.assertIsNone(row["acceptance_datetime"])
        self.assertEqual("NONE", row["acceptance_precision"])
        self.assertEqual("", row["raw_value"])

    def test_a_date_precision_value_is_never_recorded_as_acceptance(self):
        """
        On the bootstrap path a `PRECISION_DATE` value is a fact's own `filed`
        date. Recording it here would turn a filed-date availability fallback
        into filing-level provenance.
        """
        provider = RecordingProvider(entries=[index_entry(
            accession=OLD_ACCESSION,
            acceptance_datetime="2013-04-24",
            acceptance_precision=PRECISION_DATE,
        )])
        ingestor = Ingestor(self.store, provider, self.registry)
        ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.assertEqual(0, self.count("filing_acceptances"))

    def test_no_precedence_column_and_both_producers_can_coexist(self):
        from sec_provenance import filing_acceptance_id

        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.store.record_filing_acceptance(
            filing_acceptance_id(
                self.asset_id, ACCESSION,
                "SGML_HEADER_ACCEPTANCE_DATETIME", "20260730163028",
                PRECISION_INSTANT, "20260730163028",
            ),
            self.asset_id, ACCESSION, "SGML_HEADER_ACCEPTANCE_DATETIME",
            PRECISION_INSTANT, "2026-08-01T00:00:00Z", "FIRST_HAND",
            acceptance_datetime="20260730163028",
            raw_value="20260730163028",
        )
        self.assertEqual(2, self.count("filing_acceptances"))
        columns = {
            r["name"] for r in self.connection.execute(
                "PRAGMA table_info(filing_acceptances)"
            )
        }
        for forbidden in ("priority", "precedence", "is_current",
                          "superseded", "authoritative"):
            self.assertNotIn(forbidden, columns)

    def test_a_fact_filed_date_reaches_no_filing_acceptance(self):
        # The fact belongs to an accession the index does not list, and it is the
        # only thing that has spoken about that filing.
        provider = RecordingProvider(payload=concept_payload(
            accession=OLD_ACCESSION, form="10-K", filed="2013-04-24",
            fiscal_year=2013))
        ingestor = Ingestor(self.store, provider, self.registry)
        ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.assertEqual(
            0, self.count("filing_acceptances", "accession = ?",
                          OLD_ACCESSION)
        )
        # Every observation the fact produced is anchored on the filed date, and
        # none of them claims an acceptance instant.
        self.assertGreater(
            self.count("observations", "available_at_basis = 'FILED_AS_OF_DATE'"),
            0,
        )
        self.assertEqual(
            self.count("observations"),
            self.count("observations",
                       "available_at_basis = 'FILED_AS_OF_DATE'"),
        )
        self.assertEqual(
            0, self.count("observations",
                          "available_at_basis = 'ACCEPTANCE_DATETIME'"),
        )


# --------------------------------------------------------------------------
# 8. Fiscal calendar
# --------------------------------------------------------------------------


class TestFiscalCalendarAcquisition(AcquisitionBase):
    def test_the_declared_year_end_is_recorded_in_its_raw_form(self):
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        row = self.connection.execute(
            "SELECT fiscal_year_end_mmdd, declaration_source,"
            " declaring_accession FROM issuer_fiscal_calendar_declarations"
        ).fetchone()
        self.assertEqual("0926", row["fiscal_year_end_mmdd"])
        self.assertEqual("SUBMISSIONS_API_FISCAL_YEAR_END",
                         row["declaration_source"])
        self.assertIsNone(row["declaring_accession"])

    def test_drift_is_two_declarations_and_needs_no_fiscal_year(self):
        ingestor = Ingestor(self.store, RecordingProvider(), self.registry)
        ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.store.record_fiscal_calendar_declaration(
            "ifc_" + "0" * 32, self.asset_id, "0929",
            "SGML_HEADER_FISCAL_YEAR_END", "2026-08-01T00:00:00Z",
            "FIRST_HAND", declaring_accession=ACCESSION,
        )
        months = sorted(
            r[0] for r in self.connection.execute(
                "SELECT fiscal_year_end_mmdd FROM"
                " issuer_fiscal_calendar_declarations"
            )
        )
        self.assertEqual(["0926", "0929"], months)
        columns = {
            r["name"] for r in self.connection.execute(
                "PRAGMA table_info(issuer_fiscal_calendar_declarations)"
            )
        }
        self.assertNotIn("fiscal_year", columns)

    def test_a_value_that_is_not_four_digits_produces_nothing(self):
        for value in ("", "9", "09269", "Sept", "09-26"):
            store = SQLiteArchive(":memory:")
            try:
                registry = CoreRegistry(store.connection)
                seed(registry)
                ingestor = Ingestor(
                    store,
                    RecordingProvider(
                        submissions=submissions_payload(fiscal_year_end=value)),
                    registry,
                )
                ingestor.ingest(TICKER, metrics=["eps_diluted"],
                                forms=["8-K"])
                self.assertEqual(
                    0,
                    store.connection.execute(
                        "SELECT COUNT(*) FROM"
                        " issuer_fiscal_calendar_declarations"
                    ).fetchone()[0],
                    f"fiscalYearEnd={value!r}",
                )
            finally:
                store.close()


# --------------------------------------------------------------------------
# 9-10. The held-filings projection, run by production
# --------------------------------------------------------------------------


class TestProjectionDuringIngestion(AcquisitionBase):
    def seed_ledger(self, report_date: str = "2026") -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO held_filings (asset_id, accession, form,"
            " filed_at, period_end, report_date, primary_document, document_id,"
            " first_seen_at) VALUES (?, ?, '10-Q', '2026-05-01', NULL, ?,"
            " NULL, '', '2026-05-01T16:01:00Z')",
            (self.asset_id, OLD_ACCESSION, report_date),
        )
        self.connection.commit()

    def test_ingestion_projects_the_ledger_itself(self):
        self.seed_ledger()
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.assertEqual(1, self.count("filings", "accession = ?",
                                       OLD_ACCESSION))
        row = self.connection.execute(
            "SELECT form, filing_date, report_date FROM"
            " filing_declarations WHERE accession = ?"
            " AND declaration_source = 'MIGRATION_PROJECTION_HELD_FILINGS'",
            (OLD_ACCESSION,),
        ).fetchone()
        self.assertEqual("10-Q", row["form"])
        self.assertEqual("2026-05-01", row["filing_date"])

    def test_the_defective_ledger_columns_are_not_projected(self):
        self.seed_ledger(report_date="2026")
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        row = self.connection.execute(
            "SELECT report_date, conformed_period_of_report,"
            " public_document_count, is_xbrl, primary_document FROM"
            " filing_declarations WHERE accession = ?"
            " AND declaration_source = 'MIGRATION_PROJECTION_HELD_FILINGS'",
            (OLD_ACCESSION,),
        ).fetchone()
        self.assertIsNone(row["report_date"])
        self.assertIsNone(row["conformed_period_of_report"])
        self.assertIsNone(row["public_document_count"])
        self.assertIsNone(row["is_xbrl"])
        self.assertIsNone(row["primary_document"])

    def test_the_projection_keeps_the_original_capture_time(self):
        self.seed_ledger()
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        captured = self.connection.execute(
            "SELECT captured_at FROM filing_declarations WHERE accession = ?"
            " AND declaration_source = 'MIGRATION_PROJECTION_HELD_FILINGS'",
            (OLD_ACCESSION,),
        ).fetchone()[0]
        self.assertEqual("2026-05-01T16:01:00Z", captured)

    def test_an_already_projected_ledger_gains_nothing(self):
        self.seed_ledger()
        # The ledger seeded above is projected by the first run; the row that run
        # itself writes is projected by the second. Steady state is the third.
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        before = {
            table: self.count(table)
            for table in ("filings", "filing_declarations")
        }
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.assertEqual(before, {
            table: self.count(table)
            for table in ("filings", "filing_declarations")
        })


# --------------------------------------------------------------------------
# 11-15. Compatibility
# --------------------------------------------------------------------------


class TestIngestionCompatibility(AcquisitionBase):
    def ingest_into(self, store: SQLiteArchive, with_provenance: bool
                    ) -> Tuple[List[Tuple[Any, ...]], List[Any]]:
        registry = CoreRegistry(store.connection)
        seed(registry)
        provider = RecordingProvider()
        ingestor = Ingestor(store, provider, registry)
        if not with_provenance:
            ingestor._acquire_filing_provenance = lambda *a, **k: None
            ingestor._acquire_fiscal_calendar = lambda *a, **k: None
            ingestor._record_fact_filing_provenance = lambda *a, **k: None
        report = ingestor.ingest(TICKER, metrics=["eps_diluted"],
                                 forms=["8-K"])
        return [
            tuple(row) for row in store.connection.execute(
                "SELECT * FROM observations ORDER BY observation_id"
            )
        ], list(report.errors)

    def ingest_report(self, store: SQLiteArchive, with_provenance: bool
                   ) -> Any:
        """A first, clean run into a fresh archive; returns its report."""
        registry = CoreRegistry(store.connection)
        seed(registry)
        ingestor = Ingestor(store, RecordingProvider(), registry)
        if not with_provenance:
            ingestor._acquire_filing_provenance = lambda *a, **k: None
            ingestor._acquire_fiscal_calendar = lambda *a, **k: None
            ingestor._record_fact_filing_provenance = lambda *a, **k: None
        return ingestor.ingest(TICKER, metrics=["eps_diluted"],
                               forms=["8-K"])

    # Columns whose value is this run's wall clock rather than a fact about a
    # filing. Two runs a few milliseconds apart differ here and nowhere else, so
    # they are masked -- and the mask is checked against the schema so that it
    # cannot quietly widen to hide a column provenance introduced.
    RUN_CLOCK_COLUMNS = ("retrieved_at", "first_archived_at")

    def normalised_observations(self, store: SQLiteArchive) -> List[Dict[str, Any]]:
        columns = {
            r["name"] for r in store.connection.execute(
                "PRAGMA table_info(observations)"
            )
        }
        for name in self.RUN_CLOCK_COLUMNS:
            self.assertIn(name, columns, f"{name} is masked but does not exist")
        return [
            {
                key: ("<run clock>" if key in self.RUN_CLOCK_COLUMNS else value)
                for key, value in dict(row).items()
            }
            for row in store.connection.execute(
                "SELECT * FROM observations ORDER BY observation_id"
            )
        ]

    def test_observations_are_byte_identical_with_and_without_provenance(self):
        """
        The compatibility assertion this phase turns on.

        Two fresh archives, the same fixture provider, the same metric. The only
        difference is whether provenance acquisition runs. Every column of every
        observation row must be identical, value for value -- not merely the same
        count, and not merely the same hash, because a count would pass while an
        observation silently gained or lost a classification.
        """
        with_provenance = SQLiteArchive(":memory:")
        without_provenance = SQLiteArchive(":memory:")
        try:
            _, errors = self.ingest_into(with_provenance, True)
            self.ingest_into(without_provenance, False)
            self.assertEqual([], errors)
            acquired = self.normalised_observations(with_provenance)
            plain = self.normalised_observations(without_provenance)
            self.assertTrue(acquired, "no observation was written at all")
            self.assertEqual(plain, acquired)
            self.assertGreater(
                with_provenance.connection.execute(
                    "SELECT COUNT(*) FROM filings"
                ).fetchone()[0], 0,
                "the run with provenance recorded nothing, so the comparison"
                " proved nothing",
            )
        finally:
            with_provenance.close()
            without_provenance.close()

    def test_record_observation_gains_no_backfill_behaviour(self):
        """A provenance-enriched archive does not fill an observation's ledger."""
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        row = self.connection.execute(
            "SELECT * FROM observations"
        ).fetchone()
        for column in ("evidence_class", "audit_status", "sec_item",
                       "legal_status_note", "filing_document_id"):
            self.assertNotIn(column, row.keys())

    def test_a_repeated_ingest_writes_no_new_assertion(self):
        """
        Steady state, reached on the third run rather than the second.

        The second run legitimately differs from the first: the first run's own
        ledger rows are written at the very end of that run, so the projection
        has nothing to read until the second one starts. Projecting them then is
        correct rather than drift -- the form and filing date genuinely were
        first-hand captured by the run that wrote the ledger row, and the
        declaration carries that run's `first_seen_at`, not the projection's.
        """
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        before = {
            table: self.count(table) for table in (
                "filings", "filing_declarations", "filing_item_declarations",
                "filing_items", "filing_acceptances",
                "issuer_fiscal_calendar_declarations",
            )
        }
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.assertEqual(before, {
            table: self.count(table) for table in before
        })
        sources = {
            r[0] for r in self.connection.execute(
                "SELECT DISTINCT declaration_source FROM filing_declarations"
            )
        }
        self.assertEqual(
            {"SUBMISSIONS_API_FILING_INDEX", "FACT_RECORD",
             "MIGRATION_PROJECTION_HELD_FILINGS"},
            sources,
        )

    def test_no_individual_document_is_requested(self):
        """Phase 2A and Phase 2B may read manifests; neither may read a document."""
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.assertNotIn("filing_document", self.provider.document_endpoints_called)

    def test_no_bytes_no_statements_and_no_observation_linkage(self):
        """Everything Phase 3 would do, none of which exists yet."""
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        for table in ("filing_document_captures", "filing_document_statements",
                      "observation_filing_documents"):
            self.assertEqual(0, self.count(table), table)

    def test_no_sgml_producer_is_reached_without_a_submission(self):
        """Phase 2A reads no SGML. The manifests serve `None`, so none is reached."""
        import sec_ingest

        for name in ("FullSubmission", "SubmissionHeader"):
            self.assertFalse(hasattr(sec_ingest, name), name)
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        for source, table in (
            ("SGML_SUBMISSION_HEADER", "filing_declarations"),
            ("SGML_ITEM_INFORMATION", "filing_item_declarations"),
            ("SGML_HEADER_FISCAL_YEAR_END",
             "issuer_fiscal_calendar_declarations"),
            ("SGML_HEADER_ACCEPTANCE_DATETIME", "filing_acceptances"),
        ):
            self.assertEqual(
                0, self.count(table, "declaration_source = ?", source)
                if table != "filing_acceptances" else
                self.count(table, "acceptance_source = ?", source),
                f"{table} asserted a {source} declaration",
            )

    def test_no_document_relation_is_written(self):
        before = self.document_table_snapshot()
        self.ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        self.assertEqual(before, self.document_table_snapshot())
        for table, count in self.document_table_snapshot().items():
            self.assertEqual(0, count, table)

    def test_a_provenance_failure_is_reported_and_does_not_lose_the_run(self):
        """
        The same fixture, ingested twice into fresh archives: once with
        provenance working, once with provenance broken from the start.

        Comparing two runs against one archive would prove nothing, because the
        second run of an archive finds nothing new to ingest and stores nothing
        regardless of whether provenance works.
        """
        def explode(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("the provenance store is unavailable")

        healthy, broken = SQLiteArchive(":memory:"), SQLiteArchive(":memory:")
        try:
            healthy_report = self.ingest_report(healthy, True)
            self.assertEqual([], healthy_report.errors)
            self.assertGreater(healthy_report.observations_stored, 0)

            registry = CoreRegistry(broken.connection)
            seed(registry)
            broken_ingestor = Ingestor(broken, RecordingProvider(), registry)
            broken_ingestor._acquire_filing_provenance = explode
            broken_report = broken_ingestor.ingest(
                TICKER, metrics=["eps_diluted"], forms=["8-K"])

            self.assertGreater(healthy_report.observations_stored, 0)
            self.assertEqual(
                healthy_report.observations_stored,
                broken_report.observations_stored,
                "a provenance failure changed what the run stored",
            )
            self.assertEqual(
                self.normalised_observations(healthy),
                self.normalised_observations(broken),
            )
            self.assertEqual(1, len(broken_report.errors))
            self.assertIn("provenance", broken_report.errors[0])
            self.assertIn("the provenance store is unavailable",
                          broken_report.errors[0])
            # The index-level acquisition is the one that was broken. The
            # fact-level one is a separate path with its own guard, so it still
            # wrote -- which is the granularity doing its job rather than a leak.
            self.assertEqual(
                0, broken.connection.execute(
                    "SELECT COUNT(*) FROM filing_declarations"
                    " WHERE declaration_source = 'SUBMISSIONS_API_FILING_INDEX'"
                ).fetchone()[0],
            )
            self.assertEqual(
                1, broken.connection.execute(
                    "SELECT COUNT(*) FROM filing_declarations"
                    " WHERE declaration_source = 'FACT_RECORD'"
                ).fetchone()[0],
            )
        finally:
            healthy.close()
            broken.close()

    def test_an_empty_submissions_payload_records_nothing_and_still_ingests(self):
        """A payload with no `filings` and no `fiscalYearEnd` is an absence."""
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            report = Ingestor(
                store, RecordingProvider(submissions={"cik": CIK}), registry
            ).ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            self.assertGreater(report.observations_stored, 0)
            for table in ("filing_item_declarations",
                          "issuer_fiscal_calendar_declarations"):
                self.assertEqual(
                    0, store.connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0], table,
                )
            # The index declaration survives: it came from `filing_index`, which
            # is a different resource from the submissions payload.
            self.assertEqual(
                1,
                store.connection.execute(
                    "SELECT COUNT(*) FROM filing_declarations"
                    " WHERE declaration_source = 'SUBMISSIONS_API_FILING_INDEX'"
                ).fetchone()[0],
            )
        finally:
            store.close()

    def test_a_submissions_call_that_raises_is_recorded_not_propagated(self):
        """The guard itself, tested where a full ingest cannot reach it.

        A provider whose `submissions` raises fails earlier than provenance, in
        the business-model lookup this phase does not touch, so the raise path is
        exercised on `_submission_recent` directly rather than through `ingest`.
        """
        class Exploding(RecordingProvider):
            def submissions(self, cik: str) -> Dict[str, Any]:
                raise RuntimeError("the submissions endpoint is unavailable")

        ingestor = Ingestor(self.store, Exploding(), self.registry)
        self.assertEqual(
            {"recent": {}, "fiscalYearEnd": None},
            ingestor._submission_recent(CIK),
        )
        self.assertEqual(1, len(ingestor._provenance_errors))
        self.assertIn("submissions", ingestor._provenance_errors[0])


if __name__ == "__main__":
    unittest.main()