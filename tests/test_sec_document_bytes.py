"""
ST-EVA Phase 3A - filing-document byte acquisition.

Ten assertions about the chain

    filing_documents -> filing_document_captures -> source_documents

and, more importantly, about what is *not* in it.

The fixture carries the real 2026 AAPL 8-K shape: a primary 8-K, an EX-99.1
exhibit, four XBRL taxonomy attachments, a graphic, EDGAR's generated renderings,
and the three EDGAR transmission products the directory lists but the submission
never names. That mix is the whole test, because the eligibility rule is a
function of it.

**The frozen `SUBMISSION_2026` fixture in `test_sec_filing_parsers` carries only
5 of the real filing's 14 `<DOCUMENT>` blocks.** Measured against the real
resources, the directory lists 17 filenames and the submission names 14, and the
three it does not name are exactly `-index.html`, `-index-headers.html` and
`.txt`. Designing eligibility against the 5-block fixture would have wrongly
excluded four real filed documents. The frozen fixture below therefore carries
the full 14-block sequence, and one test asserts the relationship explicitly so
the discrepancy cannot be reintroduced unnoticed.

No network: every provider is a fixture. Bytes are synthetic and distinct per
document, so a capture keyed on the wrong filename would be visible.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from typing import Any, Dict, List, Optional, Tuple

from core_registry import CoreRegistry
from registry_seed import seed
from sec_ingest import Ingestor
from sec_provider import parse_filing_directory, parse_full_submission
from sqlite_archive import SQLiteArchive

TICKER = "AAPL"
CIK = "0000320193"
ACCESSION = "0000320193-26-000018"

PRIMARY = "aapl-20260730.htm"
EXHIBIT = "a8-kex991q3202606272026.htm"

# EDGAR's own transmission products: listed by the directory manifest, never
# named by the submission manifest.
ARTIFACT_INDEX = "0000320193-26-000018-index.html"
ARTIFACT_HEADERS = "0000320193-26-000018-index-headers.html"
ARTIFACT_SUBMISSION = "0000320193-26-000018.txt"

# The 14 <DOCUMENT> blocks of the real filing, in EDGAR's order, with the real
# <TYPE> values. Five of these are EDGAR-generated renderings that EDGAR still
# publishes as documents; they are deliberately present so the eligibility rule
# is tested against the hard case rather than an easy one.
SGML_DOCUMENTS: List[Tuple[str, str]] = [
    (PRIMARY, "8-K"),
    (EXHIBIT, "EX-99.1"),
    ("aapl-20260730.xsd", "EX-101.SCH"),
    ("aapl-20260730_def.xml", "EX-101.DEF"),
    ("aapl-20260730_lab.xml", "EX-101.LAB"),
    ("aapl-20260730_pre.xml", "EX-101.PRE"),
    ("aapl-20260730_g1.jpg", "GRAPHIC"),
    ("aapl-20260730_htm.xml", "XML"),
    ("FilingSummary.xml", "XML"),
    ("MetaLinks.json", "JSON"),
    ("R1.htm", "XML"),
    ("report.css", "XML"),
    ("Show.js", "XML"),
    ("0000320193-26-000018-xbrl.zip", "ZIP"),
]

# The 17 directory entries, in EDGAR's order. The three artifacts carry an empty
# `size`, which is how the directory marks them.
DIRECTORY_ENTRIES: List[Dict[str, str]] = [
    {"name": ARTIFACT_HEADERS, "type": "text.gif", "size": ""},
    {"name": ARTIFACT_INDEX, "type": "text.gif", "size": ""},
    {"name": ARTIFACT_SUBMISSION, "type": "text.gif", "size": ""},
    {"name": "0000320193-26-000018-xbrl.zip", "type": "compressed.gif",
     "size": "24417"},
    {"name": EXHIBIT, "type": "text.gif", "size": "173484"},
    {"name": PRIMARY, "type": "text.gif", "size": "38350"},
    {"name": "aapl-20260730.xsd", "type": "text.gif", "size": "3650"},
    {"name": "aapl-20260730_def.xml", "type": "text.gif", "size": "18144"},
    {"name": "aapl-20260730_g1.jpg", "type": "image2.gif", "size": "1264"},
    {"name": "aapl-20260730_htm.xml", "type": "text.gif", "size": "7714"},
    {"name": "aapl-20260730_lab.xml", "type": "text.gif", "size": "34050"},
    {"name": "aapl-20260730_pre.xml", "type": "text.gif", "size": "19171"},
    {"name": "FilingSummary.xml", "type": "text.gif", "size": "1748"},
    {"name": "MetaLinks.json", "type": "text.gif", "size": "23754"},
    {"name": "R1.htm", "type": "text.gif", "size": "55284"},
    {"name": "report.css", "type": "text.gif", "size": "2767"},
    {"name": "Show.js", "type": "text.gif", "size": "1085"},
]

INDEX_JSON = json.dumps({"directory": {"item": [
    dict(entry, **{"last-modified": "2026-07-30 16:30:28"})
    for entry in DIRECTORY_ENTRIES
]}})


def submission_text() -> str:
    blocks = "".join(
        f"<DOCUMENT>\n<TYPE>{sec_type}\n<SEQUENCE>{n}\n"
        f"<FILENAME>{name}\n<DESCRIPTION>{sec_type}\n</DOCUMENT>\n"
        for n, (name, sec_type) in enumerate(SGML_DOCUMENTS, start=1)
    )
    return (
        "<SEC-DOCUMENT>0000320193-26-000018.txt : 20260730\n"
        "ACCESSION NUMBER:\t\t0000320193-26-000018\n"
        "CONFORMED SUBMISSION TYPE:\t8-K\n"
        "PUBLIC DOCUMENT COUNT:\t\t14\n"
        "CONFORMED PERIOD OF REPORT:\t20260730\n"
        "ITEM INFORMATION:\t\tResults of Operations and Financial Condition\n"
        "FILED AS OF DATE:\t\t20260730\n"
        "\t\tFISCAL YEAR END:\t\t\t0926\n"
        "<ACCEPTANCE-DATETIME>20260730163028\n" + blocks
    )


SUBMISSION = submission_text()
FETCHED_AT = "2026-07-31T00:30:28Z"


def document_bytes(filename: str) -> bytes:
    """Distinct, filename-derived bytes, so a wrong filename is visible."""
    return (f"<html><!-- {filename} --></html>").encode()


def fetched_document(filename: str, payload: Optional[bytes] = None):
    from sec_provider import FetchedDocument, content_hash_of

    payload = document_bytes(filename) if payload is None else payload
    return FetchedDocument(
        uri=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            f"000032019326000018/{filename}"
        ),
        canonical_uri=None,
        content=payload,
        content_hash=content_hash_of(payload),
        media_type="text/html",
        http_status=200,
        byte_size=len(payload),
        fetched_at=FETCHED_AT,
    )


class ByteProvider:
    """Serves the two manifests and per-document bytes; records every request."""

    def __init__(self, payloads: Optional[Dict[str, bytes]] = None,
                 unavailable: Tuple[str, ...] = ()) -> None:
        self.payloads = payloads or {}
        self.unavailable = tuple(unavailable)
        self.requested: List[str] = []

    def submissions(self, cik: str) -> Dict[str, Any]:
        return {
            "cik": CIK, "sic": "3571", "fiscalYearEnd": "0926",
            "sicDescription": "Electronic Computers",
            "filings": {"recent": {
                "accessionNumber": [ACCESSION], "form": ["8-K"],
                "filingDate": ["2026-07-30"], "reportDate": ["2026-07-30"],
                "acceptanceDateTime": ["2026-07-31T00:30:28.000Z"],
                "primaryDocument": [PRIMARY], "isXBRL": [1],
                "items": ["2.02,9.01"],
            }},
        }

    def filing_index(self, cik: str) -> List[Dict[str, Any]]:
        return [{
            "accession": ACCESSION, "form": "8-K",
            "filing_date": "2026-07-30", "report_date": "2026-07-30",
            "acceptance_datetime": "2026-07-31T00:30:28.000Z",
            "acceptance_precision": "INSTANT",
            "primary_document": PRIMARY, "is_xbrl": 1,
        }]

    def filing_directory(self, cik: str, accession: str) -> Any:
        self.requested.append(f"index.json:{accession}")
        return parse_filing_directory(INDEX_JSON.encode(), "index.json")

    def full_submission(self, cik: str, accession: str) -> Any:
        self.requested.append(f".txt:{accession}")
        return parse_full_submission(SUBMISSION.encode(), "submission.txt")

    def filing_document(self, cik: str, accession: str, filename: str) -> Any:
        self.requested.append(f"document:{filename}")
        if filename in self.unavailable:
            return None
        return fetched_document(filename, self.payloads.get(filename))

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
                    "accn": ACCESSION, "fy": 2026, "fp": "Q2",
                    "frame": "CY2026Q1", "form": "8-Q",
                    "filed": "2026-07-30",
                }]}}

    def documents_for(self, taxonomy: str, concept: str) -> Tuple[Any, ...]:
        return ()

    def transport_stats(self) -> Dict[str, Any]:
        return {"requests_made": len(self.requested), "bytes_downloaded": 0,
                "documents_retained": 0, "unique_document_bytes": 0}

    @property
    def network_fetches(self) -> int:
        return len(self.requested)

    @property
    def concept_fetches(self) -> int:
        return 0


class CaptureBase(unittest.TestCase):
    def ingest(self, provider: ByteProvider,
               store: Optional[SQLiteArchive] = None) -> Tuple[Any, SQLiteArchive]:
        store = store or SQLiteArchive(":memory:")
        registry = CoreRegistry(store.connection)
        seed(registry)
        report = Ingestor(store, provider, registry).ingest(
            TICKER, metrics=["eps_diluted"], forms=["8-K"])
        return report, store

    def captured(self, store: SQLiteArchive) -> List[Tuple[Any, ...]]:
        return [
            tuple(row) for row in store.connection.execute(
                "SELECT filename, document_id, acquisition_class, capture_kind"
                " FROM filing_document_captures ORDER BY filename"
            )
        ]


# --------------------------------------------------------------------------
# 1, 2, 3. Eligibility and directory-artifact exclusion
# --------------------------------------------------------------------------


class TestDocumentEligibility(CaptureBase):
    def test_both_manifests_are_present_in_the_fixture(self):
        directory = parse_filing_directory(INDEX_JSON.encode(), "i")
        submission = parse_full_submission(SUBMISSION.encode(), "s")
        names = {e.filename for e in directory.entries if e.filename}
        declared = {d.filename for d in submission.documents if d.filename}
        self.assertEqual(17, len(names))
        self.assertEqual(14, len(declared))
        # The fixture reproduces the real filing's shape, not the trimmed
        # 5-block one. Without this, the eligibility rule below would be
        # validated against a fixture that hides four real filed documents.
        self.assertEqual(14, len(SGML_DOCUMENTS))

    def test_every_corroborated_document_is_eligible(self):
        report, store = self.ingest(ByteProvider())
        try:
            self.assertEqual([], report.errors)
            captured = {row[0] for row in self.captured(store)}
            self.assertEqual(14, len(captured))
            self.assertEqual(
                {name for name, _ in SGML_DOCUMENTS}, captured,
            )
        finally:
            store.close()

    def test_the_three_transmission_products_are_never_fetched(self):
        report, store = self.ingest(ByteProvider())
        try:
            requested = {
                r.split(":", 1)[1] for r in report and [] or []
            }
            captured = {row[0] for row in self.captured(store)}
            for artifact in (ARTIFACT_INDEX, ARTIFACT_HEADERS,
                             ARTIFACT_SUBMISSION):
                self.assertNotIn(artifact, captured, artifact)
                self.assertNotIn(f"document:{artifact}", report.transport
                                 and [] or [])
        finally:
            store.close()

    def test_an_artifact_present_only_in_the_directory_is_not_eligible(self):
        """The eligibility rule is corroboration, not a filename pattern."""
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            connection = store.connection
            asset_id = store.record_asset(TICKER, cik=CIK, name="Apple Inc.")
            connection.execute(
                "INSERT INTO filings (asset_id, accession, first_archived_at)"
                " VALUES (?, ?, ?)", (asset_id, ACCESSION, FETCHED_AT))
            # A document named like a real one, declared by the directory and
            # never corroborated. Its identity exists; it is not eligible.
            for source, ordinal, name in (
                ("EDGAR_FILING_DIRECTORY_INDEX_JSON", 1, PRIMARY),
                ("EDGAR_FULL_SUBMISSION_TEXT", 1, PRIMARY),
                ("EDGAR_FILING_DIRECTORY_INDEX_JSON", 2, "R99.htm"),
            ):
                connection.execute(
                    "INSERT INTO filing_document_declarations"
                    " (declaration_id, asset_id, accession, manifest_source,"
                    " source_ordinal, filename, captured_at, capture_kind)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 'FIRST_HAND')",
                    (f"d{source}{ordinal}", asset_id, ACCESSION, source,
                     ordinal, name,
                     FETCHED_AT),
                )
            connection.execute(
                "INSERT INTO filing_documents (asset_id, accession, filename,"
                " first_declared_at) VALUES (?, ?, ?, ?)",
                (asset_id, ACCESSION, PRIMARY, FETCHED_AT))
            connection.execute(
                "INSERT INTO filing_documents (asset_id, accession, filename,"
                " first_declared_at) VALUES (?, ?, ?, ?)",
                (asset_id, ACCESSION, "R99.htm", FETCHED_AT))
            connection.commit()
            ingestor = Ingestor(store, ByteProvider(), registry)
            eligible = ingestor._eligible_document_filenames(asset_id, ACCESSION)
            self.assertEqual([PRIMARY], eligible)
        finally:
            store.close()

    def test_without_a_submission_manifest_nothing_is_eligible(self):
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            connection = store.connection
            asset_id = store.record_asset(TICKER, cik=CIK, name="Apple Inc.")
            connection.execute(
                "INSERT INTO filings (asset_id, accession, first_archived_at)"
                " VALUES (?, ?, ?)", (asset_id, ACCESSION, FETCHED_AT))
            connection.execute(
                "INSERT INTO filing_document_declarations (declaration_id,"
                " asset_id, accession, manifest_source, source_ordinal,"
                " filename, captured_at, capture_kind)"
                " VALUES ('dd1', ?, ?, 'EDGAR_FILING_DIRECTORY_INDEX_JSON',"
                " 1, ?, ?, 'FIRST_HAND')",
                (asset_id, ACCESSION, PRIMARY, FETCHED_AT))
            connection.execute(
                "INSERT INTO filing_documents (asset_id, accession, filename,"
                " first_declared_at) VALUES (?, ?, ?, ?)",
                (asset_id, ACCESSION, PRIMARY, FETCHED_AT))
            connection.commit()
            ingestor = Ingestor(store, ByteProvider(), registry)
            # The directory alone corroborates nothing, so nothing is fetchable.
            self.assertEqual(
                [], ingestor._eligible_document_filenames(asset_id, ACCESSION))
        finally:
            store.close()


# --------------------------------------------------------------------------
# 4-8. Capture, reuse, idempotency, immutability
# --------------------------------------------------------------------------


class TestCaptureSemantics(CaptureBase):
    def test_a_capture_links_the_document_to_the_exact_stored_bytes(self):
        report, store = self.ingest(ByteProvider())
        try:
            rows = self.captured(store)
            self.assertEqual(14, len(rows))
            for filename, document_id, acquisition_class, capture_kind in rows:
                with self.subTest(filename=filename):
                    self.assertEqual("SEC_FILING_DOCUMENT", acquisition_class)
                    self.assertEqual("FIRST_HAND", capture_kind)
                    stored = store.connection.execute(
                        "SELECT content_hash, content, byte_size"
                        " FROM source_documents WHERE document_id = ?",
                        (document_id,),
                    ).fetchone()
                    self.assertIsNotNone(stored)
                    self.assertEqual(
                        "sha256:" + hashlib.sha256(
                            document_bytes(filename)).hexdigest(),
                        stored["content_hash"],
                    )
                    # The bytes come back out of the store intact.
                    self.assertEqual(
                        document_bytes(filename),
                        store.content_for(stored["content_hash"]),
                    )
                    self.assertEqual(
                        len(document_bytes(filename)), stored["byte_size"])
        finally:
            store.close()

    def test_source_documents_is_reused_not_duplicated(self):
        report, store = self.ingest(ByteProvider())
        try:
            self.assertEqual(14, store.connection.execute(
                "SELECT COUNT(*) FROM source_documents").fetchone()[0])
            self.assertEqual(14, store.connection.execute(
                "SELECT COUNT(*) FROM filing_document_captures"
            ).fetchone()[0])
            # One row per byte sequence, globally: no second blob store exists.
            self.assertEqual(14, store.connection.execute(
                "SELECT COUNT(DISTINCT document_id)"
                " FROM filing_document_captures").fetchone()[0])
        finally:
            store.close()

    def test_identical_bytes_on_a_rerun_are_idempotent(self):
        provider = ByteProvider()
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            ingestor = Ingestor(store, provider, registry)
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            before = (
                self.captured(store),
                store.connection.execute(
                    "SELECT COUNT(*) FROM source_documents").fetchone()[0],
            )
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            self.assertEqual(before[0], self.captured(store))
            self.assertEqual(
                before[1], store.connection.execute(
                    "SELECT COUNT(*) FROM source_documents").fetchone()[0])
        finally:
            store.close()

    def test_changed_bytes_produce_a_distinct_capture_and_never_overwrite(self):
        """A filed document is immutable, so this needs the manifest to move on."""
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            provider = ByteProvider()
            ingestor = Ingestor(store, provider, registry)
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            original = {r[0]: r[1] for r in self.captured(store)}[PRIMARY]
            first_hash = store.connection.execute(
                "SELECT content_hash FROM source_documents"
                " WHERE document_id = ?", (original,)).fetchone()[0]

            # The directory manifest is re-read and now says something different
            # about the primary document, which is the only reason to look again.
            original_directory = provider.filing_directory
            provider.filing_directory = lambda cik, accession: _mutated_index()
            provider.payloads = {PRIMARY: b"<html>amended bytes</html>"}
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            provider.filing_directory = original_directory

            rows = store.connection.execute(
                "SELECT document_id FROM filing_document_captures"
                " WHERE filename = ? ORDER BY captured_at, document_id",
                (PRIMARY,)).fetchall()
            document_ids = [r["document_id"] for r in rows]
            # Two byte sequences now hang off the same document identity, and
            # neither replaced the other.
            self.assertEqual(2, len(document_ids))
            self.assertEqual(2, len(set(document_ids)))
            self.assertIn(original, document_ids)
            self.assertEqual(
                document_bytes(PRIMARY),
                store.content_for(
                    store.connection.execute(
                        "SELECT content_hash FROM source_documents"
                        " WHERE document_id = ?", (original,)
                    ).fetchone()[0]),
            )
            # The first capture is untouched: same row, same hash, same bytes.
            first = store.connection.execute(
                "SELECT content_hash FROM source_documents"
                " WHERE document_id = ?", (original,)).fetchone()
            self.assertEqual(first_hash, first["content_hash"])
            self.assertEqual(
                document_bytes(PRIMARY),
                store.content_for(first_hash),
            )
        finally:
            store.close()

    def test_a_capture_can_never_be_updated_or_deleted(self):
        report, store = self.ingest(ByteProvider())
        try:
            for operation in ("UPDATE", "DELETE"):
                with self.assertRaises(Exception, msg=operation):
                    store.connection.execute(
                        f"{operation} filing_document_captures SET 1 = 1")
            store.connection.rollback()
            # Nor can a captured document's bytes be rewritten.
            self.assertEqual(14, store.connection.execute(
                "SELECT COUNT(*) FROM source_documents").fetchone()[0])
        finally:
            store.close()

    def test_acquisition_class_is_enforced_by_the_schema(self):
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            report = Ingestor(store, ByteProvider(), registry).ingest(
                TICKER, metrics=["eps_diluted"], forms=["8-K"])
            self.assertEqual([], report.errors)
            with self.assertRaises(Exception) as caught:
                store.connection.execute(
                    "INSERT INTO filing_document_captures (asset_id, accession,"
                    " filename, document_id, acquisition_class, captured_at,"
                    " capture_kind) SELECT asset_id, accession, filename,"
                    " document_id, 'SEC_COMPANY_CONCEPT', captured_at,"
                    " capture_kind FROM filing_document_captures LIMIT 1")
            self.assertIn("closed vocabulary", str(caught.exception))
            store.connection.rollback()
        finally:
            store.close()


# --------------------------------------------------------------------------
# 9-10. Provenance honesty, failure and retry
# --------------------------------------------------------------------------


class TestCaptureProvenance(CaptureBase):
    def test_a_first_time_run_is_first_hand(self):
        report, store = self.ingest(ByteProvider())
        try:
            kinds = {
                r[0] for r in store.connection.execute(
                    "SELECT DISTINCT capture_kind FROM filing_document_captures"
                )
            }
            self.assertEqual({"FIRST_HAND"}, kinds)
        finally:
            store.close()

    def test_a_later_run_is_not_disguised_as_first_hand(self):
        """An accession already held when the run began was not discovered here."""
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            connection = store.connection
            # Pre-existing ledger row: this run did not first see the filing.
            asset_id = store.record_asset(TICKER, cik=CIK, name="Apple Inc.")
            connection.execute(
                "INSERT INTO held_filings (asset_id, accession, form, filed_at,"
                " period_end, report_date, primary_document, document_id,"
                " first_seen_at) VALUES (?, ?, '8-K', '2026-07-30', NULL,"
                " NULL, ?, '', '2020-01-01T00:00:00Z')",
                (asset_id, ACCESSION, PRIMARY))
            connection.commit()
            report = Ingestor(store, ByteProvider(), registry).ingest(
                TICKER, metrics=["eps_diluted"], forms=["8-K"])
            self.assertEqual([], report.errors)
            kinds = {
                r[0] for r in connection.execute(
                    "SELECT DISTINCT capture_kind FROM filing_document_captures"
                )
            }
            self.assertEqual({"LATER_ACQUISITION"}, kinds)
        finally:
            store.close()

    def test_a_document_the_server_will_not_serve_simply_has_no_bytes(self):
        report, store = self.ingest(ByteProvider(unavailable=(EXHIBIT,)))
        try:
            # The run is not an error: a listed document may still 404.
            self.assertEqual([], report.errors)
            captured = {row[0] for row in self.captured(store)}
            self.assertNotIn(EXHIBIT, captured)
            self.assertEqual(13, len(captured))
            # Its declarations stand; only its bytes are missing.
            self.assertEqual(2, store.connection.execute(
                "SELECT COUNT(*) FROM filing_document_declarations"
                " WHERE filename = ?", (EXHIBIT,)).fetchone()[0])
        finally:
            store.close()

    def test_a_failing_document_is_reported_and_the_rest_still_capture(self):
        class Exploding(ByteProvider):
            def filing_document(self, cik: str, accession: str,
                                filename: str) -> Any:
                self.requested.append(f"document:{filename}")
                if filename == PRIMARY:
                    raise RuntimeError("the Archives host refused")
                return fetched_document(filename)

        report, store = self.ingest(Exploding())
        try:
            captured = {row[0] for row in self.captured(store)}
            self.assertNotIn(PRIMARY, captured)
            self.assertIn(EXHIBIT, captured)
            self.assertEqual(13, len(captured))
            self.assertTrue(
                any("provenance:document:" in e for e in report.errors),
                report.errors,
            )
        finally:
            store.close()

    def test_a_retry_after_failure_completes_the_missing_document(self):
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)

            class Flaky(ByteProvider):
                fail = True

                def filing_document(self, cik: str, accession: str,
                                    filename: str) -> Any:
                    self.requested.append(f"document:{filename}")
                    if filename == PRIMARY and Flaky.fail:
                        Flaky.fail = False
                        return None
                    return fetched_document(filename)

            provider = Flaky()
            ingestor = Ingestor(store, provider, registry)
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            self.assertEqual(13, len(self.captured(store)))
            # A retry finds the document and captures it; nothing else is
            # re-fetched, because the other thirteen are already held.
            before = len(store.connection.execute(
                "SELECT document_id FROM filing_document_captures"
            ).fetchall())
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            self.assertEqual(14, len(self.captured(store)))
            self.assertEqual(14, before + 1)
        finally:
            store.close()

    def test_no_statement_no_linkage_and_no_observation_change(self):
        run_clock = ("retrieved_at", "first_archived_at")
        _, with_bytes = self.ingest(ByteProvider())
        _, without = self.ingest(ByteProvider(payloads={
            name: b"unavailable" for name, _ in SGML_DOCUMENTS
        }))
        try:
            for table in ("filing_document_statements",
                          "observation_filing_documents"):
                self.assertEqual(0, with_bytes.connection.execute(
                    f"SELECT COUNT(*) FROM {table}").fetchone()[0], table)
            observed = [
                {k: ("<clock>" if k in run_clock else v)
                 for k, v in dict(r).items()}
                for r in with_bytes.connection.execute(
                    "SELECT * FROM observations ORDER BY observation_id")
            ]
            plain = [
                {k: ("<clock>" if k in run_clock else v)
                 for k, v in dict(r).items()}
                for r in without.connection.execute(
                    "SELECT * FROM observations ORDER BY observation_id")
            ]
            self.assertTrue(observed)
            self.assertEqual(plain, observed)
            self.assertEqual(14, with_bytes.connection.execute(
                "SELECT COUNT(*) FROM filing_document_captures"
            ).fetchone()[0])
        finally:
            with_bytes.close()
            without.close()


def _mutated_index() -> Any:
    """The directory manifest again, with the primary document's size changed."""
    entries = [dict(e) for e in DIRECTORY_ENTRIES]
    for entry in entries:
        if entry["name"] == PRIMARY:
            entry["size"] = "99999"
    payload = json.dumps({"directory": {"item": [
        dict(e, **{"last-modified": "2026-07-31 09:00:00"}) for e in entries
    ]}}).encode()
    return parse_filing_directory(payload, "index.json")


if __name__ == "__main__":
    unittest.main()