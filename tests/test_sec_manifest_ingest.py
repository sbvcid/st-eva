"""
ST-EVA Phase 2B - filing manifest and SGML acquisition.

Eighteen assertions about the two manifests in production ingest. The SEC
payloads are the frozen strings from `test_sec_filing_parsers`, reused rather
than copied: one place that knows what a real `index.json` and a real full
submission look like, and a fixture cannot drift away from the parser that was
written against it.

Every provider here is a fixture and nothing opens a socket. A call for an
individual document raises, because that resource is Phase 3.

The claims being pinned:

    * the two manifests are independent -- a directory that arrives without a
      submission, and a submission without a directory, both produce a legal and
      useful archive, and neither discards what the other wrote;
    * **identity is minted from the directory listing alone**, and only for a
      filename the listing declared exactly once;
    * a directory ordinal and a submission ordinal are different numbers for the
      same document, and nothing in the code can make them one;
    * the SGML header reaches `filing_acceptances` through `ACCEPTANCE-DATETIME`
      only, so `FILED AS OF DATE` has nowhere to be mistaken for one;
    * the two item sources coexist rather than merging, even when a filing has
      both, and the API's codes are never replaced by the header's titles.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional, Tuple

from core_registry import CoreRegistry
from registry_seed import seed
from sec_ingest import Ingestor
from sec_provider import parse_filing_directory, parse_full_submission
from sqlite_archive import SQLiteArchive

from test_sec_filing_parsers import (  # noqa: E402  frozen fixtures, reused
    ACCESSION_2013,
    ACCESSION_2026,
    CIK,
    INDEX_JSON_2026,
    SUBMISSION_2013,
    SUBMISSION_2026,
)

TICKER = "AAPL"
FILENAME_PRIMARY = "aapl-20260730.htm"
FILENAME_EX991 = "a8-kex991q3202606272026.htm"

# The assertions this phase turns on. No document bytes, no statements, no
# observation linkage, no classification.
FORBIDDEN_RELATIONS = (
    "filing_document_captures", "filing_document_statements",
    "observation_filing_documents",
)


def index_entry(accession: str = ACCESSION_2026) -> Dict[str, Any]:
    return {
        "accession": accession, "form": "8-K", "filing_date": "2026-07-30",
        "report_date": "2026-07-30",
        "acceptance_datetime": "2026-07-31T00:30:28.000Z",
        "acceptance_precision": "INSTANT",
        "primary_document": FILENAME_PRIMARY, "is_xbrl": 1,
    }


class ManifestProvider:
    """A fixture provider serving the two manifests and refusing documents."""

    def __init__(self, directory_payload: Optional[bytes] = INDEX_JSON_2026,
                 submission_payload: Optional[bytes] = SUBMISSION_2026,
                 accession: str = ACCESSION_2026,
                 entries: Optional[List[Dict[str, Any]]] = None) -> None:
        # The frozen fixtures are strings; the provider serves bytes, because
        # that is what the transport hands a parser.
        self._directory = (
            None if directory_payload is None
            else directory_payload.encode()
            if isinstance(directory_payload, str) else directory_payload
        )
        self._submission = (
            None if submission_payload is None
            else submission_payload.encode()
            if isinstance(submission_payload, str) else submission_payload
        )
        self.accession = accession
        self.entries = [index_entry(accession)] if entries is None else entries
        self.requested: List[str] = []
        self.submissions_calls = 0

    # -- the two authorised Archives resources ------------------------

    def filing_directory(self, cik: str, accession: str) -> Any:
        self.requested.append(f"index.json:{accession}")
        if self._directory is None:
            return None
        return parse_filing_directory(self._directory, "index.json")

    def full_submission(self, cik: str, accession: str) -> Any:
        self.requested.append(f".txt:{accession}")
        if self._submission is None:
            return None
        return parse_full_submission(self._submission, "submission.txt")

    # -- never authorised at any phase so far ------------------------

    def filing_document(self, *args: Any, **kwargs: Any) -> None:
        self.requested.append("individual-document")
        raise AssertionError("no phase so far may fetch a filing document")

    # -- the endpoints the rest of ingest uses ------------------------

    def submissions(self, cik: str) -> Dict[str, Any]:
        self.submissions_calls += 1
        return {
            "cik": CIK, "sic": "3571",
            "sicDescription": "Electronic Computers",
            "fiscalYearEnd": "0926", "exchanges": ["Nasdaq"],
            "filings": {"recent": {
                "accessionNumber": [self.accession],
                "form": ["8-K"], "filingDate": ["2026-07-30"],
                "reportDate": ["2026-07-30"],
                "acceptanceDateTime": ["2026-07-31T00:30:28.000Z"],
                "primaryDocument": [FILENAME_PRIMARY], "isXBRL": [1],
                "items": ["2.02,9.01"],
            }},
        }

    def filing_index(self, cik: str) -> List[Dict[str, Any]]:
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
        return {"cik": CIK, "taxonomy": "us-gaap",
                "tag": "EarningsPerShareDiluted", "label": "EPS",
                "description": "Diluted EPS",
                "units": {"USD/shares": [{
                    "start": "2026-01-01", "end": "2026-03-28", "val": 1.65,
                    "accn": self.accession, "fy": 2026, "fp": "Q2",
                    "frame": "CY2026Q1", "form": "8-K",
                    "filed": "2026-07-30",
                }]}}

    def documents_for(self, taxonomy: str, concept: str) -> Tuple[Any, ...]:
        return ()

    def transport_stats(self) -> Dict[str, Any]:
        return {"requests_made": 1, "bytes_downloaded": 0,
                "documents_retained": 0, "unique_document_bytes": 0}

    @property
    def network_fetches(self) -> int:
        return len(self.requested) + self.submissions_calls

    @property
    def concept_fetches(self) -> int:
        return 0


class NoItemCodesProvider(ManifestProvider):
    """
    A Submissions payload whose `items` column is empty.

    This is the case the freeze turns on. `SUBMISSIONS_API_ITEMS` does not come
    from either Archives manifest -- it comes from `filings.recent.items` on the
    Submissions API, which is a third resource -- so a filing can name its items
    in the SGML header while no code is available anywhere.
    """

    def submissions(self, cik: str) -> Dict[str, Any]:
        payload = super().submissions(cik)
        payload["filings"]["recent"]["items"] = [""]
        return payload


class ManifestBase(unittest.TestCase):
    provider_kwargs: Dict[str, Any] = {}

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.provider = ManifestProvider(**self.provider_kwargs)
        self.ingestor = Ingestor(self.store, self.provider, self.registry)
        # Not named `run`: unittest.TestCase.run is the framework's hook.
        self.ingest_once()

    def ingest_once(self) -> Any:
        return self.ingestor.ingest(TICKER, metrics=["eps_diluted"],
                                    forms=["8-K"])

    def tearDown(self) -> None:
        self.store.close()

    @property
    def connection(self):
        return self.store.connection

    def count(self, table: str, where: str = "", *args: Any) -> int:
        clause = f" WHERE {where}" if where else ""
        return self.connection.execute(
            f"SELECT COUNT(*) FROM {table}{clause}", args
        ).fetchone()[0]

    def ingest_into(self, provider: "ManifestProvider") -> Tuple[Any, SQLiteArchive]:
        """
        Ingest into a *fresh* archive.

        These tests change what a manifest says, and the relations are
        append-only, so reusing `setUp`'s archive would leave the first answer
        sitting next to the second and the assertion would be measuring both.
        """
        store = SQLiteArchive(":memory:")
        registry = CoreRegistry(store.connection)
        seed(registry)
        report = Ingestor(store, provider, registry).ingest(
            TICKER, metrics=["eps_diluted"], forms=["8-K"])
        return report, store


# --------------------------------------------------------------------------
# 3, 5, 6, 7, 8. The directory listing
# --------------------------------------------------------------------------


class TestDirectoryAcquisition(ManifestBase):
    def test_every_entry_becomes_a_declaration_in_edgars_order(self):
        rows = self.connection.execute(
            "SELECT source_ordinal, filename, mime_type, byte_size,"
            " last_modified, sec_document_type FROM"
            " filing_document_declarations"
            " WHERE manifest_source = 'EDGAR_FILING_DIRECTORY_INDEX_JSON'"
            " ORDER BY source_ordinal"
        ).fetchall()
        self.assertEqual(17, len(rows))
        self.assertEqual(list(range(1, 18)),
                         [r["source_ordinal"] for r in rows])
        self.assertEqual(
            "0000320193-26-000018-index-headers.html", rows[0]["filename"]
        )
        self.assertEqual(FILENAME_EX991, rows[4]["filename"])
        self.assertEqual("text.gif", rows[4]["mime_type"])
        self.assertEqual(173484, rows[4]["byte_size"])
        # index.json publishes no SEC <TYPE>, and nothing fills it in.
        self.assertEqual([None] * 17, [r["sec_document_type"] for r in rows])

    def test_the_generated_index_artefacts_are_kept_as_declarations(self):
        artefacts = {
            r[0] for r in self.connection.execute(
                "SELECT filename FROM filing_document_declarations"
                " WHERE manifest_source = 'EDGAR_FILING_DIRECTORY_INDEX_JSON'"
                " AND (filename LIKE '%-index.html'"
                " OR filename LIKE '%-index-headers.html'"
                " OR filename = ?)",
                (ACCESSION_2026 + ".txt",),
            )
        }
        self.assertEqual(3, len(artefacts))

    def test_filing_identity_is_minted_for_every_unique_filename(self):
        # Every directory entry is a file in the filing's directory, including
        # the three EDGAR generated ones: whether an entry is a filed document or
        # an artefact is answered by comparing against the submission, not by
        # guessing from a name.
        self.assertEqual(
            17, self.count("filing_documents")
        )
        self.assertEqual(
            1, self.count("filing_documents", "filename = ?",
                          FILENAME_PRIMARY)
        )

    def test_an_empty_size_stays_absent_rather_than_becoming_zero(self):
        row = self.connection.execute(
            "SELECT byte_size FROM filing_document_declarations"
            " WHERE manifest_source = 'EDGAR_FILING_DIRECTORY_INDEX_JSON'"
            " AND filename = ?", ("Show.js",)
        ).fetchone()
        self.assertEqual(1085, row["byte_size"])
        artefact = self.connection.execute(
            "SELECT byte_size FROM filing_document_declarations"
            " WHERE manifest_source = 'EDGAR_FILING_DIRECTORY_INDEX_JSON'"
            " AND filename = ?",
            ("0000320193-26-000018-index.html",)
        ).fetchone()
        self.assertIsNone(artefact["byte_size"])

    def test_the_two_ordinals_for_one_document_are_different_numbers(self):
        rows = {
            r["manifest_source"]: r["source_ordinal"]
            for r in self.connection.execute(
                "SELECT manifest_source, source_ordinal FROM"
                " filing_document_declarations WHERE filename = ?",
                (FILENAME_PRIMARY,)
            )
        }
        self.assertIn("EDGAR_FILING_DIRECTORY_INDEX_JSON", rows)
        self.assertIn("EDGAR_FULL_SUBMISSION_TEXT", rows)
        # Measured on the real filing: index position 6, submission position 1.
        self.assertNotEqual(
            rows["EDGAR_FILING_DIRECTORY_INDEX_JSON"],
            rows["EDGAR_FULL_SUBMISSION_TEXT"],
        )

    def test_the_two_manifests_are_joined_by_filename_only(self):
        """The one document both manifests name agrees on nothing but its name."""
        rows = self.connection.execute(
            "SELECT filename, sec_document_type, mime_type FROM"
            " filing_document_declarations WHERE filename = ?",
            (FILENAME_PRIMARY,)
        ).fetchall()
        self.assertEqual(2, len(rows))
        by_source = {
            r["sec_document_type"] is not None: r for r in rows
        }
        self.assertIn(True, by_source)
        self.assertIn(False, by_source)
        sgml = [r for r in rows if r["sec_document_type"] is not None][0]
        directory = [r for r in rows if r["sec_document_type"] is None][0]
        self.assertEqual("8-K", sgml["sec_document_type"])
        self.assertEqual("text.gif", directory["mime_type"])

    def test_a_duplicate_filename_refuses_identity_and_is_reported(self):
        import json

        duplicated = json.dumps({"directory": {"item": [
            {"name": "a.htm", "type": "text.gif", "size": "1"},
            {"name": "a.htm", "type": "text.gif", "size": "2"},
            {"name": "b.htm", "type": "text.gif", "size": "1"},
        ]}})
        report, store = self.ingest_into(
            ManifestProvider(directory_payload=duplicated))
        try:
            # Both declarations survive; one identity row is refused.
            self.assertEqual(2, store.connection.execute(
                "SELECT COUNT(*) FROM filing_document_declarations"
                " WHERE manifest_source ="
                " 'EDGAR_FILING_DIRECTORY_INDEX_JSON'"
                " AND filename = 'a.htm'").fetchone()[0])
            self.assertEqual(0, store.connection.execute(
                "SELECT COUNT(*) FROM filing_documents"
                " WHERE filename = 'a.htm'").fetchone()[0])
            # The unambiguous one is still recorded.
            self.assertEqual(1, store.connection.execute(
                "SELECT COUNT(*) FROM filing_documents"
                " WHERE filename = 'b.htm'").fetchone()[0])
            self.assertTrue(
                any("duplicate_filename" in e for e in report.errors),
                report.errors,
            )
        finally:
            store.close()

    def test_a_filename_that_is_absent_produces_no_identity(self):
        import json

        nameless = json.dumps({"directory": {"item": [
            {"type": "text.gif", "size": "1"},
        ]}})
        report, store = self.ingest_into(
            ManifestProvider(directory_payload=nameless))
        try:
            self.assertEqual([], report.errors)
            self.assertEqual(0, store.connection.execute(
                "SELECT COUNT(*) FROM filing_documents").fetchone()[0])
            self.assertEqual(1, store.connection.execute(
                "SELECT COUNT(*) FROM filing_document_declarations"
                " WHERE manifest_source ="
                " 'EDGAR_FILING_DIRECTORY_INDEX_JSON'"
                " AND filename IS NULL").fetchone()[0])
        finally:
            store.close()


# --------------------------------------------------------------------------
# 6, 7. The submission
# --------------------------------------------------------------------------


class TestSubmissionAcquisition(ManifestBase):
    def test_every_document_block_becomes_a_declaration(self):
        rows = self.connection.execute(
            "SELECT source_ordinal, sec_document_type, filename, mime_type"
            " FROM filing_document_declarations"
            " WHERE manifest_source = 'EDGAR_FULL_SUBMISSION_TEXT'"
            " ORDER BY source_ordinal"
        ).fetchall()
        self.assertEqual(5, len(rows))
        self.assertEqual(list(range(1, 6)),
                         [r["source_ordinal"] for r in rows])
        self.assertEqual("8-K", rows[0]["sec_document_type"])
        self.assertEqual(FILENAME_PRIMARY, rows[0]["filename"])
        self.assertEqual("EX-99.1", rows[1]["sec_document_type"])
        # The submission names no MIME type; that is the other manifest's field.
        self.assertEqual([None] * 5, [r["mime_type"] for r in rows])

    def test_the_submission_never_mints_a_document_identity(self):
        submission_only = {
            r[0] for r in self.connection.execute(
                "SELECT DISTINCT filename FROM filing_document_declarations"
                " WHERE manifest_source = 'EDGAR_FULL_SUBMISSION_TEXT'"
            )
        }
        directory = {
            r[0] for r in self.connection.execute(
                "SELECT DISTINCT filename FROM filing_document_declarations"
                " WHERE manifest_source = 'EDGAR_FILING_DIRECTORY_INDEX_JSON'"
            )
        }
        self.assertTrue(submission_only)
        self.assertEqual(directory, {
            r[0] for r in self.connection.execute(
                "SELECT DISTINCT filename FROM filing_documents"
            )
        })
        self.assertEqual(17, len(directory))

    def test_a_repeated_document_type_is_fine(self):
        report, store = self.ingest_into(ManifestProvider(
            submission_payload=SUBMISSION_2013, accession=ACCESSION_2013))
        try:
            self.assertEqual([], report.errors)
            self.assertEqual(3, store.connection.execute(
                "SELECT COUNT(*) FROM filing_document_declarations"
                " WHERE manifest_source = 'EDGAR_FULL_SUBMISSION_TEXT'"
                " AND sec_document_type = 'XML'").fetchone()[0])
        finally:
            store.close()

    def test_a_block_without_a_filename_is_recorded_rather_than_skipped(self):
        report, store = self.ingest_into(ManifestProvider(
            submission_payload=SUBMISSION_2013, accession=ACCESSION_2013))
        try:
            self.assertEqual([], report.errors)
            row = store.connection.execute(
                "SELECT sec_document_type, source_ordinal FROM"
                " filing_document_declarations"
                " WHERE manifest_source = 'EDGAR_FULL_SUBMISSION_TEXT'"
                " AND filename IS NULL"
            ).fetchone()
            self.assertEqual("EX-101.LAB", row["sec_document_type"])
            self.assertEqual(8, row["source_ordinal"])
        finally:
            store.close()

    def test_no_classification_is_produced_by_either_manifest(self):
        columns = {
            r["name"] for r in self.connection.execute(
                "PRAGMA table_info(filing_document_declarations)"
            )
        }
        for forbidden in ("evidence_class", "audit_status", "legal_status",
                          "is_furnished"):
            self.assertNotIn(forbidden, columns)


# --------------------------------------------------------------------------
# 8, 9. The header
# --------------------------------------------------------------------------


class TestHeaderAcquisition(ManifestBase):
    def header_row(self, table: str, column: str) -> Optional[Any]:
        row = self.connection.execute(
            f"SELECT {column} FROM {table}"
            " WHERE declaration_source = 'SGML_SUBMISSION_HEADER'"
        ).fetchone()
        return None if row is None else row[0]

    def test_the_header_declares_filing_metadata_under_its_own_producer(self):
        row = self.connection.execute(
            "SELECT form, filing_date, report_date,"
            " conformed_period_of_report, public_document_count FROM"
            " filing_declarations"
            " WHERE declaration_source = 'SGML_SUBMISSION_HEADER'"
        ).fetchone()
        self.assertEqual("8-K", row["form"])
        self.assertEqual("20260730", row["filing_date"])
        self.assertEqual("20260730", row["report_date"])
        self.assertEqual("20260730", row["conformed_period_of_report"])
        self.assertEqual(14, row["public_document_count"])

    def test_the_header_does_not_amend_the_index_declaration(self):
        producers = {
            r[0] for r in self.connection.execute(
                "SELECT DISTINCT declaration_source FROM filing_declarations"
            )
        }
        self.assertEqual(
            {"SUBMISSIONS_API_FILING_INDEX", "SGML_SUBMISSION_HEADER",
             "FACT_RECORD"},
            producers,
        )

    def test_the_acceptance_element_is_recorded_and_filed_date_is_not(self):
        row = self.connection.execute(
            "SELECT acceptance_datetime, acceptance_precision, raw_value"
            " FROM filing_acceptances"
            " WHERE acceptance_source = 'SGML_HEADER_ACCEPTANCE_DATETIME'"
        ).fetchone()
        self.assertEqual("20260730163028", row["acceptance_datetime"])
        self.assertEqual("INSTANT", row["acceptance_precision"])
        self.assertEqual("20260730163028", row["raw_value"])
        # `FILED AS OF DATE` reached the filing declaration as a date, and
        # reached no acceptance row at all.
        self.assertEqual(
            2, self.count("filing_acceptances"),
        )
        self.assertEqual(
            {("SGML_HEADER_ACCEPTANCE_DATETIME",),
             ("SUBMISSIONS_API_ACCEPTANCE_DATETIME",)},
            {(r[0],) for r in self.connection.execute(
                "SELECT acceptance_source FROM filing_acceptances")},
        )

    def test_the_fiscal_year_end_is_stored_as_raw_mmdd(self):
        row = self.connection.execute(
            "SELECT fiscal_year_end_mmdd, declaration_source,"
            " declaring_accession FROM issuer_fiscal_calendar_declarations"
            " WHERE declaration_source = 'SGML_HEADER_FISCAL_YEAR_END'"
        ).fetchone()
        self.assertEqual("0926", row["fiscal_year_end_mmdd"])
        self.assertEqual(ACCESSION_2026, row["declaring_accession"])

    def test_drift_is_two_declarations_from_two_sources(self):
        provider = ManifestProvider(submission_payload=SUBMISSION_2013.encode(),
                                    directory_payload=None,
                                    accession=ACCESSION_2013)
        ingestor = Ingestor(self.store, provider, self.registry)
        ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
        declared = {
            r[0] for r in self.connection.execute(
                "SELECT fiscal_year_end_mmdd FROM"
                " issuer_fiscal_calendar_declarations"
            )
        }
        self.assertEqual({"0926", "0929"}, declared)

    def test_both_item_sources_coexist_and_never_merge(self):
        sources = {
            r[0] for r in self.connection.execute(
                "SELECT DISTINCT declaration_source FROM"
                " filing_item_declarations"
            )
        }
        self.assertEqual({"SUBMISSIONS_API_ITEMS", "SGML_ITEM_INFORMATION"},
                         sources)
        api = self.connection.execute(
            "SELECT raw_items_text, declared_item_count FROM"
            " filing_item_declarations"
            " WHERE declaration_source = 'SUBMISSIONS_API_ITEMS'"
        ).fetchone()
        sgml = self.connection.execute(
            "SELECT raw_items_text, declared_item_count FROM"
            " filing_item_declarations"
            " WHERE declaration_source = 'SGML_ITEM_INFORMATION'"
        ).fetchone()
        # Codes and titles, kept apart rather than paired by list order.
        self.assertEqual("2.02,9.01", api["raw_items_text"])
        self.assertEqual(2, api["declared_item_count"])
        self.assertEqual(
            "Results of Operations and Financial Condition\n"
            "Financial Statements and Exhibits",
            sgml["raw_items_text"],
        )
        # The header names items rather than coding them, so no per-item row is
        # written; `filing_items.item_code` is NOT NULL and there is no
        # source-faithful code to put there.
        self.assertEqual(2, self.count("filing_items"))

    def test_the_header_names_items_and_no_item_row_claims_a_title_as_a_code(
        self,
    ):
        codes = {
            r[0] for r in self.connection.execute(
                "SELECT item_code FROM filing_items"
            )
        }
        self.assertEqual({"2.02", "9.01"}, codes)
        self.assertEqual(
            0, self.count("filing_items",
                          "item_code LIKE '%Financial Condition%'"),
        )


    def test_titles_without_codes_yield_a_declaration_and_no_items(self):
        """
        The freeze case, pinned.

        The header names two items and no code exists anywhere in the archive.
        The declaration must survive verbatim -- it is source evidence -- while
        `filing_items` stays empty, because that relation is a normalised
        item-code relation and a title is not a code. And with no code to join,
        nothing downstream may be resolved: the filing's items are unknown rather
        than approximated.
        """
        report, store = self.ingest_into(NoItemCodesProvider(
            directory_payload=INDEX_JSON_2026,
            submission_payload=SUBMISSION_2026))
        try:
            self.assertEqual([], report.errors)
            rows = store.connection.execute(
                "SELECT declaration_source, declared_item_count,"
                " raw_items_text FROM filing_item_declarations"
                " ORDER BY declaration_source"
            ).fetchall()
            # Exactly one declaration, and it is the titles, kept verbatim.
            self.assertEqual(1, len(rows))
            self.assertEqual("SGML_ITEM_INFORMATION",
                             rows[0]["declaration_source"])
            self.assertEqual(2, rows[0]["declared_item_count"])
            self.assertEqual(
                "Results of Operations and Financial Condition\n"
                "Financial Statements and Exhibits",
                rows[0]["raw_items_text"],
            )
            # No codes, so no item rows. A title is never promoted into one.
            self.assertEqual(0, store.connection.execute(
                "SELECT COUNT(*) FROM filing_items").fetchone()[0])
            # And nothing is resolved in its place.
            for table in ("filing_items", "filing_item_declarations",
                          "filing_document_declarations", "filings"):
                columns = {
                    r["name"] for r in store.connection.execute(
                        f"PRAGMA table_info({table})"
                    )
                }
                for forbidden in ("evidence_class", "audit_status", "sec_item",
                                  "legal_status", "classification"):
                    self.assertNotIn(forbidden, columns, table)
        finally:
            store.close()

    def test_filing_items_are_written_only_by_the_code_source(self):
        """Rule D, as an assertion about producers rather than about a value."""
        report, store = self.ingest_into(ManifestProvider(
            directory_payload=INDEX_JSON_2026,
            submission_payload=SUBMISSION_2026))
        try:
            self.assertEqual([], report.errors)
            producers = {
                r[0] for r in store.connection.execute(
                    "SELECT DISTINCT d.declaration_source"
                    " FROM filing_items i"
                    " JOIN filing_item_declarations d"
                    " ON d.declaration_id = i.declaration_id"
                )
            }
            self.assertEqual({"SUBMISSIONS_API_ITEMS"}, producers)
            # Titles reached no item row from either manifest.
            self.assertEqual(
                {"2.02", "9.01"},
                {r[0] for r in store.connection.execute(
                    "SELECT item_code FROM filing_items")},
            )
        finally:
            store.close()


# --------------------------------------------------------------------------
# 10, 11, 16, 17. Independence and retry
# --------------------------------------------------------------------------


class TestManifestIndependence(unittest.TestCase):
    def ingest(self, provider: ManifestProvider,
               store: SQLiteArchive) -> Any:
        registry = CoreRegistry(store.connection)
        seed(registry)
        return Ingestor(store, provider, registry).ingest(
            TICKER, metrics=["eps_diluted"], forms=["8-K"])

    def test_a_submission_without_a_directory_is_a_legal_archive(self):
        store = SQLiteArchive(":memory:")
        try:
            report = self.ingest(
                ManifestProvider(directory_payload=None), store)
            self.assertEqual([], report.errors)
            self.assertEqual(
                5, store.connection.execute(
                    "SELECT COUNT(*) FROM filing_document_declarations"
                    " WHERE manifest_source = 'EDGAR_FULL_SUBMISSION_TEXT'"
                ).fetchone()[0])
            self.assertEqual(
                0, store.connection.execute(
                    "SELECT COUNT(*) FROM filing_documents").fetchone()[0])
            self.assertEqual(
                1, store.connection.execute(
                    "SELECT COUNT(*) FROM filing_acceptances"
                    " WHERE acceptance_source = 'SGML_HEADER_ACCEPTANCE_DATETIME'"
                ).fetchone()[0])
        finally:
            store.close()

    def test_a_directory_without_a_submission_is_a_legal_archive(self):
        store = SQLiteArchive(":memory:")
        try:
            report = self.ingest(
                ManifestProvider(submission_payload=None), store)
            self.assertEqual([], report.errors)
            self.assertEqual(
                17, store.connection.execute(
                    "SELECT COUNT(*) FROM filing_documents").fetchone()[0])
            self.assertEqual(
                0, store.connection.execute(
                    "SELECT COUNT(*) FROM filing_document_declarations"
                    " WHERE manifest_source = 'EDGAR_FULL_SUBMISSION_TEXT'"
                ).fetchone()[0])
            # Phase 2A metadata is untouched by either manifest being absent.
            self.assertEqual(
                1, store.connection.execute(
                    "SELECT COUNT(*) FROM filing_declarations"
                    " WHERE declaration_source ="
                    " 'SUBMISSIONS_API_FILING_INDEX'"
                ).fetchone()[0])
        finally:
            store.close()

    def test_one_unit_failing_leaves_the_other_untouched(self):
        class ExplodingDirectory(ManifestProvider):
            def filing_directory(self, cik: str, accession: str) -> Any:
                self.requested.append(f"index.json:{accession}")
                raise urllib_error("404 Not Found")

        def urllib_error(message: str) -> Exception:
            import urllib.error

            return urllib.error.HTTPError(
                "u", 404, message, {}, None
            )

        store = SQLiteArchive(":memory:")
        try:
            report = self.ingest(ExplodingDirectory(), store)
            self.assertEqual(1, len(report.errors))
            self.assertIn("directory", report.errors[0])
            self.assertEqual(
                5, store.connection.execute(
                    "SELECT COUNT(*) FROM filing_document_declarations"
                    " WHERE manifest_source = 'EDGAR_FULL_SUBMISSION_TEXT'"
                ).fetchone()[0])
            self.assertEqual(
                0, store.connection.execute(
                    "SELECT COUNT(*) FROM filing_documents").fetchone()[0])
            self.assertEqual(
                2, store.connection.execute(
                    "SELECT COUNT(*) FROM filing_acceptances").fetchone()[0])
            self.assertEqual(
                1, store.connection.execute(
                    "SELECT COUNT(*) FROM filing_acceptances"
                    " WHERE acceptance_source ="
                    " 'SGML_HEADER_ACCEPTANCE_DATETIME'").fetchone()[0])
        finally:
            store.close()

    def test_a_repeated_run_writes_nothing_new(self):
        """
        Steady state is the third run, for the same reason as in Phase 2A: a
        run's own ledger rows are written at the end of that run, so the
        projection cannot see them until the next one.
        """
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            provider = ManifestProvider()
            ingestor = Ingestor(store, provider, registry)
            tables = ("filings", "filing_declarations",
                      "filing_item_declarations", "filing_items",
                      "filing_acceptances",
                      "issuer_fiscal_calendar_declarations",
                      "filing_document_declarations", "filing_documents")

            def counts() -> Dict[str, int]:
                return {
                    table: store.connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0] for table in tables
                }

            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            before = counts()
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            self.assertEqual(before, counts())
            # Both manifests really were read on every run.
            self.assertEqual(
                3, provider.requested.count(
                    f"index.json:{ACCESSION_2026}"),
            )
        finally:
            store.close()

    def test_a_changed_manifest_entry_adds_a_declaration_and_keeps_the_first(
        self,
    ):
        import json

        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            provider = ManifestProvider()
            ingestor = Ingestor(store, provider, registry)
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            provider._directory = json.dumps({"directory": {"item": [
                {"name": FILENAME_PRIMARY, "type": "text.gif", "size": "99999"},
            ]}}).encode()
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            sizes = sorted(
                r[0] for r in store.connection.execute(
                    "SELECT byte_size FROM filing_document_declarations"
                    " WHERE manifest_source ="
                    " 'EDGAR_FILING_DIRECTORY_INDEX_JSON'"
                    " AND filename = ?", (FILENAME_PRIMARY,)
                )
            )
            self.assertEqual([38350, 99999], sizes)
            # One identity row, whatever the manifests now say.
            self.assertEqual(17, store.connection.execute(
                "SELECT COUNT(*) FROM filing_documents").fetchone()[0])
        finally:
            store.close()

    def test_no_individual_document_is_requested(self):
        store = SQLiteArchive(":memory:")
        try:
            provider = ManifestProvider()
            self.ingest(provider, store)
            self.assertNotIn("individual-document", provider.requested)
            self.assertEqual(
                {"index.json:" + ACCESSION_2026, ".txt:" + ACCESSION_2026},
                set(provider.requested),
            )
        finally:
            store.close()

    def test_nothing_phase_three_exists_yet(self):
        store = SQLiteArchive(":memory:")
        try:
            self.ingest(ManifestProvider(), store)
            for table in FORBIDDEN_RELATIONS:
                self.assertEqual(
                    0, store.connection.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0], table,
                )
        finally:
            store.close()


# --------------------------------------------------------------------------
# 19. Observations are unchanged by either manifest
# --------------------------------------------------------------------------


RUN_CLOCK_COLUMNS = ("retrieved_at", "first_archived_at")


class TestObservationUnchanged(unittest.TestCase):
    def observations(self, store: SQLiteArchive) -> List[Dict[str, Any]]:
        return [
            {
                key: ("<run clock>" if key in RUN_CLOCK_COLUMNS else value)
                for key, value in dict(row).items()
            }
            for row in store.connection.execute(
                "SELECT * FROM observations ORDER BY observation_id"
            )
        ]

    def run_with(self, provider: ManifestProvider) -> Tuple[Any, SQLiteArchive]:
        store = SQLiteArchive(":memory:")
        registry = CoreRegistry(store.connection)
        seed(registry)
        return Ingestor(store, provider, registry).ingest(
            TICKER, metrics=["eps_diluted"], forms=["8-K"]), store

    def test_observations_are_identical_with_and_without_the_manifests(self):
        with_manifests, enriched = self.run_with(ManifestProvider())
        without_manifests, plain = self.run_with(
            ManifestProvider(directory_payload=None, submission_payload=None)
        )
        try:
            self.assertEqual([], with_manifests.errors)
            self.assertEqual([], without_manifests.errors)
            observed = self.observations(enriched)
            self.assertTrue(observed)
            self.assertEqual(self.observations(plain), observed)
            # The same rows, ids and hashes -- not merely the same count.
            self.assertEqual(
                [row["observation_id"] for row in self.observations(plain)],
                [row["observation_id"] for row in observed],
            )
            self.assertEqual(
                [row["content_hash"] for row in self.observations(plain)],
                [row["content_hash"] for row in observed],
            )
            # And the manifests really did write something, so this compared.
            self.assertEqual(
                17, enriched.connection.execute(
                    "SELECT COUNT(*) FROM filing_documents").fetchone()[0])
            self.assertEqual(
                0, plain.connection.execute(
                    "SELECT COUNT(*) FROM filing_documents").fetchone()[0])
        finally:
            enriched.close()
            plain.close()


if __name__ == "__main__":
    unittest.main()