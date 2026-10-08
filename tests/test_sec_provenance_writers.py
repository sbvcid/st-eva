"""
ST-EVA Phase 1A - provenance identity and archive writers.

Twenty-one assertions about the two production modules this phase added:
`sec_provenance.py` (identity) and the eleven `record_*` writers added to
`sqlite_archive.py` (persistence).

The claims being pinned are the ones the design took, and every one of them is a
statement about behaviour rather than about structure:

    * identity is a digest of the *assertion*, so a repeated assertion is a no-op
      and a changed one is a second row rather than an amendment;
    * capture time is not in any preimage, so re-confirmation cannot manufacture
      an identity;
    * NULL is spelled `null` and never omitted, so "said nothing about it" and
      "did not say" stay distinguishable;
    * a statement is bound to a captured byte sequence, not merely to a document;
    * a re-extraction that changes its own wording is refused loudly;
    * `FACT_FILED_DATE` cannot be stored as filing acceptance;
    * none of these writers can reach an Observation, proven by tracing the SQL
      they actually issue rather than by reading the source and hoping.

Nothing here performs a network fetch, parses an SEC payload, or classifies a
document. Those are Phase 1B and 2, and this suite is what makes them safe to
add later without changing any of the identities below.
"""

from __future__ import annotations

import hashlib
import re
import unittest
from typing import Any, List, Tuple

from archive import StoredDocument
from core_registry import CoreRegistry
from data_contract import METRIC_EPS_DILUTED
from evidence_model import source_fact_id
from registry_seed import seed
from sec_ingest import SEC_SOURCE, Ingestor
from sec_provenance import (
    ACCEPTANCE_SOURCES,
    fiscal_calendar_declaration_id,
    filing_acceptance_id,
    filing_declaration_id,
    filing_document_declaration_id,
    filing_document_statement_id,
    filing_document_statement_identity,
    filing_item_declaration_id,
    filing_item_id,
)
from sqlite_archive import SQLiteArchive

ASSET = "AAPL"
CIK = "0000320193"
ACCESSION = "0000320193-26-000018"
SECOND_ACCESSION = "0001193125-13-170623"
FILENAME = "aapl-20260730.htm"
FILENAME_EX991 = "a8-kex991q3202606272026.htm"
QUOTE = 'shall not be deemed "filed" for purposes of Section 18'
FIRST_HAND_AT = "2026-07-31T00:30:28Z"
LATER_AT = "2027-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# 1-4. Identity semantics
# ---------------------------------------------------------------------------


class TestIdentitySemantics(unittest.TestCase):
    def test_the_same_assertion_yields_the_same_identity(self):
        first = filing_declaration_id(
            self_asset := "asset-1", ACCESSION, "SUBMISSIONS_API_FILING_INDEX",
            form="8-K", filing_date="2026-07-30", is_xbrl=1,
        )
        second = filing_declaration_id(
            self_asset, ACCESSION, "SUBMISSIONS_API_FILING_INDEX",
            form="8-K", filing_date="2026-07-30", is_xbrl=1,
        )
        self.assertEqual(first, second)

    def test_a_changed_assertion_yields_a_different_identity(self):
        base = dict(
            asset_id="asset-1", accession=ACCESSION,
            declaration_source="SGML_SUBMISSION_HEADER",
        )
        self.assertNotEqual(
            filing_declaration_id(**base, public_document_count=14),
            filing_declaration_id(**base, public_document_count=16),
        )
        self.assertNotEqual(
            filing_declaration_id(**base, form="8-K"),
            filing_declaration_id(**base, form="8-K/A"),
        )
        self.assertNotEqual(
            filing_declaration_id(**base, report_date=None),
            filing_declaration_id(**base, report_date="2026-07-30"),
        )

    def test_capture_time_is_not_part_of_any_identity(self):
        """Re-confirmation has to be a no-op, and capture time is the temptation."""
        base = dict(
            asset_id="asset-1", accession=ACCESSION,
            declaration_source="SUBMISSIONS_API_FILING_INDEX", form="8-K",
        )
        self.assertEqual(
            filing_declaration_id(**base),
            filing_declaration_id(**base),
        )
        # The stronger form of the same guarantee: no identity function accepts a
        # capture time, a capture kind or a migration timestamp at all, so there
        # is no argument a caller could pass that would change an identity.
        for forbidden in ("captured_at", "capture_kind", "declared_at"):
            with self.assertRaises(TypeError, msg=forbidden):
                filing_declaration_id(**base, **{forbidden: FIRST_HAND_AT})

    def test_null_and_non_null_are_distinguishable(self):
        base = dict(
            asset_id="asset-1", accession=ACCESSION,
            declaration_source="SGML_SUBMISSION_HEADER",
        )
        self.assertNotEqual(
            filing_declaration_id(**base, is_xbrl=None),
            filing_declaration_id(**base, is_xbrl=0),
        )
        self.assertNotEqual(
            filing_document_declaration_id(
                "asset-1", ACCESSION, "EDGAR_FULL_SUBMISSION_TEXT", 1, FILENAME,
                sec_document_type=None, mime_type="text.gif",
            ),
            filing_document_declaration_id(
                "asset-1", ACCESSION, "EDGAR_FULL_SUBMISSION_TEXT", 1, FILENAME,
                sec_document_type="8-K", mime_type="text.gif",
            ),
        )
        self.assertNotEqual(
            filing_acceptance_id(
                "asset-1", ACCESSION, "SGML_HEADER_ACCEPTANCE_DATETIME",
                None, "NONE",
            ),
            filing_acceptance_id(
                "asset-1", ACCESSION, "SGML_HEADER_ACCEPTANCE_DATETIME",
                "20260730163028", "INSTANT",
            ),
        )

    def test_every_prefix_is_fixed_and_hashed_the_repository_way(self):
        cases = [
            (filing_declaration_id("a", "b", "FACT_RECORD"), "decl_", 37),
            (filing_item_declaration_id("a", "b", "SGML_ITEM_INFORMATION", "2.02"),
             "fid_", 36),
            (filing_item_id("fid_x", 1, "2.02"), "fit_", 36),
            (filing_document_declaration_id(
                "a", "b", "EDGAR_FILING_DIRECTORY_INDEX_JSON", 1, FILENAME),
             "fdd_", 36),
            (filing_acceptance_id(
                "a", "b", "SGML_HEADER_ACCEPTANCE_DATETIME", None, "NONE"),
             "fac_", 36),
            (fiscal_calendar_declaration_id(
                "a", "0926", "SUBMISSIONS_API_FISCAL_YEAR_END"), "ifc_", 36),
            (filing_document_statement_id(
                "a", "b", FILENAME, "doc_x", "SECTION_18_NOT_DEEMED_FILED", "0:9"),
             "fds_", 36),
        ]
        for identity, prefix, length in cases:
            self.assertTrue(identity.startswith(prefix), identity)
            self.assertEqual(length, len(identity))
            self.assertRegex(identity, rf"^{prefix}[0-9a-f]+$")

    def test_identity_uses_the_repository_canonical_hash_and_not_another(self):
        """A second hash framework would make two archive layers disagree."""
        import json

        from evidence_model import canonical_json

        payload = {
            "asset_id": "asset-1", "accession": ACCESSION,
            "declaration_source": "FACT_RECORD", "form": None,
            "filing_date": None, "report_date": None,
            "conformed_period_of_report": None, "public_document_count": None,
            "is_xbrl": None, "primary_document": None,
        }
        expected = "decl_" + hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()[:32]
        self.assertEqual(
            expected,
            filing_declaration_id("asset-1", ACCESSION, "FACT_RECORD"),
        )
        self.assertEqual(
            json.dumps(payload, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")),
            canonical_json(payload),
        )

    def test_two_item_sources_at_the_same_ordinal_do_not_collide(self):
        api = filing_item_declaration_id(
            "asset-1", ACCESSION, "SUBMISSIONS_API_ITEMS", "2.02,9.01"
        )
        sgml = filing_item_declaration_id(
            "asset-1", ACCESSION, "SGML_ITEM_INFORMATION",
            "Results of Operations and Financial Condition",
        )
        self.assertNotEqual(api, sgml)
        self.assertNotEqual(
            filing_item_id(api, 1, "2.02"),
            filing_item_id(sgml, 1, "2.02"),
        )

    def test_a_statement_is_bound_to_a_byte_sequence_not_a_document(self):
        first = filing_document_statement_id(
            "asset-1", ACCESSION, FILENAME, "doc_a",
            "SECTION_18_NOT_DEEMED_FILED", "0:64",
        )
        second = filing_document_statement_id(
            "asset-1", ACCESSION, FILENAME, "doc_b",
            "SECTION_18_NOT_DEEMED_FILED", "0:64",
        )
        self.assertNotEqual(first, second)

    def test_a_statement_locator_changes_the_identity_but_its_text_does_not(self):
        base = ("asset-1", ACCESSION, FILENAME, "doc_a",
                "SECTION_18_NOT_DEEMED_FILED")
        self.assertNotEqual(
            filing_document_statement_id(*base, "0:64"),
            filing_document_statement_id(*base, "0:99"),
        )

    def test_the_statement_preimage_is_recomputable_from_the_persisted_row(self):
        identity = filing_document_statement_identity(
            "asset-1", ACCESSION, FILENAME, "doc_a",
            "SECTION_18_NOT_DEEMED_FILED", "0:64",
        )
        self.assertEqual(
            "fds_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32],
            filing_document_statement_id(
                "asset-1", ACCESSION, FILENAME, "doc_a",
                "SECTION_18_NOT_DEEMED_FILED", "0:64",
            ),
        )
        self.assertIn('"quote_locator":"0:64"', identity)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


class WriterArchive(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.store.record_asset(ASSET, cik=CIK, name="Apple Inc.")
        self.asset_id = self.connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ?", (ASSET,)
        ).fetchone()["asset_id"]
        self.traced: List[str] = []
        self.connection.set_trace_callback(self.traced.append)
        self.store.record_filing(self.asset_id, ACCESSION, FIRST_HAND_AT)

    def tearDown(self) -> None:
        self.connection.set_trace_callback(None)
        self.store.close()

    @property
    def connection(self):
        return self.store.connection

    def count(self, table: str) -> int:
        return self.connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

    def declare_directory_document(self, filename: str = FILENAME,
                                   ordinal: int = 1, mint: bool = True) -> str:
        """Declare a document in the directory manifest, and mint its identity.

        The mint is not optional in the ordinary path: a capture cannot exist
        without a `filing_documents` row, and the row is minted only by a
        directory-manifest declaration.
        """
        identity = filing_document_declaration_id(
            self.asset_id, ACCESSION, "EDGAR_FILING_DIRECTORY_INDEX_JSON",
            ordinal, filename, mime_type="text.gif", byte_size=38350,
        )
        self.store.record_filing_document_declaration(
            identity, self.asset_id, ACCESSION,
            "EDGAR_FILING_DIRECTORY_INDEX_JSON", ordinal, FIRST_HAND_AT,
            "FIRST_HAND", filename=filename, mime_type="text.gif",
            byte_size=38350, last_modified="2026-07-30 16:30:28",
        )
        if mint:
            self.store.record_filing_document(
                self.asset_id, ACCESSION, filename, FIRST_HAND_AT
            )
        return identity

    def capture(self, payload: bytes, filename: str = FILENAME) -> str:
        document_id = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
            uri="https://www.sec.gov/Archives/edgar/data/320193/"
                f"{ACCESSION.replace('-', '')}/{filename}",
            canonical_uri=None, http_status=200, media_type="text/html",
            byte_size=len(payload), fetched_at=FIRST_HAND_AT,
            first_seen_at=FIRST_HAND_AT, payload=payload,
            provider=SEC_SOURCE, document_type="SEC_FILING_DOCUMENT",
        ))
        self.store.record_filing_document_capture(
            self.asset_id, ACCESSION, filename, document_id,
            "SEC_FILING_DOCUMENT", FIRST_HAND_AT, "FIRST_HAND",
        )
        return document_id


# ---------------------------------------------------------------------------
# 5-6. Writer idempotency
# ---------------------------------------------------------------------------


class TestWriterIdempotency(WriterArchive):
    def test_record_filing_is_idempotent_and_keeps_the_first_clock(self):
        self.assertFalse(
            self.store.record_filing(self.asset_id, ACCESSION, LATER_AT)
        )
        held = self.connection.execute(
            "SELECT first_archived_at FROM filings WHERE accession = ?",
            (ACCESSION,),
        ).fetchone()[0]
        self.assertEqual(FIRST_HAND_AT, held)

    def test_every_declaration_writer_is_idempotent(self):
        declaration = filing_declaration_id(
            self.asset_id, ACCESSION, "SUBMISSIONS_API_FILING_INDEX",
            form="8-K", filing_date="2026-07-30",
        )
        for _ in range(3):
            self.store.record_filing_declaration(
                declaration, self.asset_id, ACCESSION,
                "SUBMISSIONS_API_FILING_INDEX", LATER_AT, "LATER_ACQUISITION",
                form="8-K", filing_date="2026-07-30",
            )
        self.assertEqual(1, self.count("filing_declarations"))

        items = filing_item_declaration_id(
            self.asset_id, ACCESSION, "SUBMISSIONS_API_ITEMS", "2.02,9.01"
        )
        for _ in range(3):
            self.store.record_filing_item_declaration(
                items, self.asset_id, ACCESSION, "SUBMISSIONS_API_ITEMS",
                "2.02,9.01", LATER_AT, "LATER_ACQUISITION",
            )
        self.assertEqual(1, self.count("filing_item_declarations"))

        for _ in range(3):
            self.store.record_filing_item(
                filing_item_id(items, 1, "2.02"), items, 1, "2.02", LATER_AT,
            )
        self.assertEqual(1, self.count("filing_items"))

        manifest = filing_document_declaration_id(
            self.asset_id, ACCESSION, "EDGAR_FULL_SUBMISSION_TEXT", 1, FILENAME,
            sec_document_type="8-K",
        )
        for _ in range(3):
            self.store.record_filing_document_declaration(
                manifest, self.asset_id, ACCESSION,
                "EDGAR_FULL_SUBMISSION_TEXT", 1, LATER_AT,
                "LATER_ACQUISITION", filename=FILENAME,
                sec_document_type="8-K",
            )
        self.assertEqual(1, self.count("filing_document_declarations"))

        acceptance = filing_acceptance_id(
            self.asset_id, ACCESSION, "SGML_HEADER_ACCEPTANCE_DATETIME",
            "20260730163028", "INSTANT",
        )
        for _ in range(3):
            self.store.record_filing_acceptance(
                acceptance, self.asset_id, ACCESSION,
                "SGML_HEADER_ACCEPTANCE_DATETIME", "INSTANT", LATER_AT,
                "LATER_ACQUISITION", acceptance_datetime="20260730163028",
            )
        self.assertEqual(1, self.count("filing_acceptances"))

        calendar = fiscal_calendar_declaration_id(
            self.asset_id, "0926", "SGML_HEADER_FISCAL_YEAR_END", ACCESSION,
        )
        for _ in range(3):
            self.store.record_fiscal_calendar_declaration(
                calendar, self.asset_id, "0926",
                "SGML_HEADER_FISCAL_YEAR_END", LATER_AT, "LATER_ACQUISITION",
                declaring_accession=ACCESSION,
            )
        self.assertEqual(1, self.count("issuer_fiscal_calendar_declarations"))

    def test_the_document_and_capture_writers_are_idempotent(self):
        self.declare_directory_document(mint=False)
        self.assertTrue(
            self.store.record_filing_document(
                self.asset_id, ACCESSION, FILENAME, FIRST_HAND_AT
            )
        )
        self.assertFalse(
            self.store.record_filing_document(
                self.asset_id, ACCESSION, FILENAME, LATER_AT
            )
        )
        self.assertEqual(1, self.count("filing_documents"))
        payload = b"<html>8-K body</html>"
        first = self.capture(payload)
        self.assertFalse(
            self.store.record_filing_document_capture(
                self.asset_id, ACCESSION, FILENAME, first,
                "SEC_FILING_DOCUMENT", LATER_AT, "LATER_ACQUISITION",
            )
        )
        self.assertEqual(1, self.count("filing_document_captures"))
        self.assertEqual(1, self.count("source_documents"))

    def test_a_changed_declaration_is_a_second_row_not_an_amendment(self):
        before = filing_declaration_id(
            self.asset_id, ACCESSION, "SGML_SUBMISSION_HEADER",
            public_document_count=14,
        )
        after = filing_declaration_id(
            self.asset_id, ACCESSION, "SGML_SUBMISSION_HEADER",
            public_document_count=16,
        )
        for identity, count in ((before, 14), (after, 16)):
            self.store.record_filing_declaration(
                identity, self.asset_id, ACCESSION, "SGML_SUBMISSION_HEADER",
                FIRST_HAND_AT, "FIRST_HAND", public_document_count=count,
            )
        self.assertEqual(2, self.count("filing_declarations"))
        self.assertEqual(
            14,
            self.connection.execute(
                "SELECT public_document_count FROM filing_declarations"
                " WHERE declaration_id = ?", (before,)
            ).fetchone()[0],
        )

    def test_no_writer_ever_updates_a_provenance_row(self):
        self.declare_directory_document()
        self.capture(b"<html>body</html>")
        writes = [sql for sql in self.traced
                  if re.match(r"\s*(UPDATE|DELETE|INSERT OR REPLACE)\b", sql,
                              re.IGNORECASE)]
        self.assertEqual([], writes)


# ---------------------------------------------------------------------------
# 7-8. Statements
# ---------------------------------------------------------------------------


class TestStatementWriters(WriterArchive):
    def prepare(self) -> str:
        self.declare_directory_document()
        return self.capture(b"<html>" + QUOTE.encode() + b"</html>")

    def insert(self, document_id: str, quote_text: str,
               quote_locator: str = "0:64") -> str:
        identity = filing_document_statement_identity(
            self.asset_id, ACCESSION, FILENAME, document_id,
            "SECTION_18_NOT_DEEMED_FILED", quote_locator,
        )
        key = filing_document_statement_id(
            self.asset_id, ACCESSION, FILENAME, document_id,
            "SECTION_18_NOT_DEEMED_FILED", quote_locator,
        )
        self.store.record_filing_document_statement(
            key, identity, self.asset_id, ACCESSION, FILENAME, document_id,
            "SECTION_18_NOT_DEEMED_FILED", quote_locator, quote_text,
            "DECLARED_VERBATIM_QUOTE", FIRST_HAND_AT, "FIRST_HAND",
            applies_to_document_type="EX-99.1",
            applies_to_filing_item_code="2.02",
        )
        return key

    def test_a_statement_requires_a_capture(self):
        orphan = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + "7" * 64, uri="x", canonical_uri=None,
            http_status=200, media_type="text/html", byte_size=1,
            fetched_at=FIRST_HAND_AT, first_seen_at=FIRST_HAND_AT,
            payload=b"x", provider=SEC_SOURCE,
            document_type="SEC_FILING_DOCUMENT",
        ))
        with self.assertRaises(Exception):
            self.insert(orphan, QUOTE)
        self.assertEqual(0, self.count("filing_document_statements"))

    def test_a_statement_is_bound_to_its_capture_and_survives_a_refetch(self):
        first = self.prepare()
        self.insert(first, QUOTE)
        second = self.capture(b"<html>re-fetched body</html>")
        self.insert(second, QUOTE)
        self.assertEqual(2, self.count("filing_document_statements"))
        documents = {
            r[0] for r in self.connection.execute(
                "SELECT document_id FROM filing_document_statements"
            )
        }
        self.assertEqual({first, second}, documents)

    def test_an_identical_reextraction_is_a_no_op(self):
        document_id = self.prepare()
        key = self.insert(document_id, QUOTE)
        self.assertEqual(key, self.insert(document_id, QUOTE))
        self.assertEqual(1, self.count("filing_document_statements"))

    def test_a_conflicting_reextraction_is_refused_not_absorbed(self):
        document_id = self.prepare()
        self.insert(document_id, QUOTE)
        with self.assertRaises(Exception) as caught:
            self.insert(document_id, QUOTE.replace("Section 18", "Section 13"))
        self.assertIn("not deterministic", str(caught.exception))
        self.assertEqual(1, self.count("filing_document_statements"))
        self.assertEqual(
            QUOTE,
            self.connection.execute(
                "SELECT quote_text FROM filing_document_statements"
            ).fetchone()[0],
        )

    def test_the_persisted_preimage_matches_the_identity(self):
        document_id = self.prepare()
        self.insert(document_id, QUOTE)
        row = self.connection.execute(
            "SELECT statement_id, statement_identity FROM"
            " filing_document_statements"
        ).fetchone()
        self.assertEqual(
            filing_document_statement_id(
                self.asset_id, ACCESSION, FILENAME, document_id,
                "SECTION_18_NOT_DEEMED_FILED", "0:64",
            ),
            row["statement_id"],
        )
        self.assertEqual(
            filing_document_statement_identity(
                self.asset_id, ACCESSION, FILENAME, document_id,
                "SECTION_18_NOT_DEEMED_FILED", "0:64",
            ),
            row["statement_identity"],
        )

    def test_the_scope_of_a_primary_document_quote_is_stated_not_inferred(self):
        document_id = self.prepare()
        self.insert(document_id, QUOTE)
        row = self.connection.execute(
            "SELECT filename, applies_to_document_type,"
            " applies_to_filing_item_code FROM filing_document_statements"
        ).fetchone()
        self.assertEqual(FILENAME, row["filename"])
        self.assertEqual("EX-99.1", row["applies_to_document_type"])
        self.assertEqual("2.02", row["applies_to_filing_item_code"])


# ---------------------------------------------------------------------------
# 9-11. Vocabulary refusals
# ---------------------------------------------------------------------------


class TestWriterRefusals(WriterArchive):
    def test_an_invalid_acquisition_class_is_refused(self):
        self.declare_directory_document()
        document_id = self.capture(b"<html>body</html>")
        with self.assertRaises(ValueError) as caught:
            self.store.record_filing_document_capture(
                self.asset_id, ACCESSION, FILENAME, document_id,
                "SEC_COMPANY_CONCEPT", FIRST_HAND_AT, "FIRST_HAND",
            )
        self.assertIn("acquisition_class", str(caught.exception))

    def test_an_invalid_acceptance_source_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            filing_acceptance_id(
                self.asset_id, ACCESSION, "SOMEWHERE_ELSE", None, "NONE",
            )
        self.assertIn("acceptance_source", str(caught.exception))

    def test_a_fact_filed_date_can_never_be_filing_acceptance(self):
        with self.assertRaises(ValueError):
            filing_acceptance_id(
                self.asset_id, ACCESSION, "FACT_FILED_DATE", "2026-07-30", "DATE",
            )
        with self.assertRaises(ValueError):
            self.store.record_filing_acceptance(
                "fac_" + "0" * 32, self.asset_id, ACCESSION, "FACT_FILED_DATE",
                "DATE", FIRST_HAND_AT, "FIRST_HAND",
                acceptance_datetime="2026-07-30",
            )
        self.assertEqual(0, self.count("filing_acceptances"))

    def test_the_acceptance_vocabulary_is_exactly_two_producers(self):
        self.assertEqual(
            ("SGML_HEADER_ACCEPTANCE_DATETIME",
             "SUBMISSIONS_API_ACCEPTANCE_DATETIME"),
            tuple(ACCEPTANCE_SOURCES),
        )

    def test_both_producers_coexist_for_one_filing(self):
        for source, value in (
            ("SGML_HEADER_ACCEPTANCE_DATETIME", "20260730163028"),
            ("SUBMISSIONS_API_ACCEPTANCE_DATETIME",
             "2026-07-31T00:30:28.000Z"),
        ):
            self.store.record_filing_acceptance(
                filing_acceptance_id(
                    self.asset_id, ACCESSION, source, value, "INSTANT"
                ),
                self.asset_id, ACCESSION, source, "INSTANT", FIRST_HAND_AT,
                "FIRST_HAND", acceptance_datetime=value, raw_value=value,
            )
        self.assertEqual(2, self.count("filing_acceptances"))
        self.assertEqual(1, self.count("filings"))

    def test_precision_none_keeps_its_null_coupling(self):
        self.store.record_filing_acceptance(
            filing_acceptance_id(
                self.asset_id, ACCESSION, "SUBMISSIONS_API_ACCEPTANCE_DATETIME",
                None, "NONE", "",
            ),
            self.asset_id, ACCESSION, "SUBMISSIONS_API_ACCEPTANCE_DATETIME",
            "NONE", FIRST_HAND_AT, "FIRST_HAND", raw_value="",
        )
        row = self.connection.execute(
            "SELECT acceptance_datetime, raw_value FROM filing_acceptances"
        ).fetchone()
        self.assertIsNone(row["acceptance_datetime"])
        self.assertEqual("", row["raw_value"])

    def test_an_unknown_capture_kind_is_refused(self):
        with self.assertRaises(ValueError):
            self.store.record_filing_declaration(
                filing_declaration_id(self.asset_id, ACCESSION, "FACT_RECORD"),
                self.asset_id, ACCESSION, "FACT_RECORD", FIRST_HAND_AT,
                "WHENEVER",
            )

    def test_the_manifest_vocabulary_cannot_be_widened(self):
        with self.assertRaises(ValueError):
            filing_document_declaration_id(
                self.asset_id, ACCESSION, "EDGAR_SOMETHING_ELSE", 1, FILENAME,
            )


# ---------------------------------------------------------------------------
# 12. Provenance never reaches an Observation
# ---------------------------------------------------------------------------


class TestProvenanceNeverWritesObservations(WriterArchive):
    def setUp(self) -> None:
        super().setUp()
        self.registry = CoreRegistry(self.connection)
        seed(self.registry)
        ingestor = Ingestor(self.store, object(), self.registry)
        entry = {
            "start": "2026-01-01", "end": "2026-03-28", "val": 1.65,
            "accn": ACCESSION, "fy": 2026, "fp": "Q2", "frame": "CY2026Q1",
            "form": "10-Q", "filed": "2026-05-01",
        }
        payload = {"cik": CIK, "taxonomy": "us-gaap",
                   "tag": "EarningsPerShareDiluted", "label": "EPS",
                   "description": "Diluted EPS"}
        mapping = next(
            m for m in self.registry.mappings_for_metric(METRIC_EPS_DILUTED)
            if m.concept_id == "us-gaap:EarningsPerShareDiluted"
        )
        observation = ingestor._observation(
            METRIC_EPS_DILUTED, "us-gaap", "EarningsPerShareDiluted", mapping,
            payload, entry, "USD/shares", entry["start"], entry["end"],
            *ingestor._availability_for(entry, {}), ACCESSION,
        )
        self.observation_id = self.store.record_observation(
            asset=ASSET, observation=observation,
            availability_class="SOURCE_DECLARED",
        )

    def snapshot(self) -> List[Tuple[Any, ...]]:
        return [
            tuple(row)
            for row in self.connection.execute(
                "SELECT * FROM observations ORDER BY observation_id"
            )
        ]

    def exercise_every_provenance_writer(self) -> None:
        self.declare_directory_document()
        self.store.record_filing_document(self.asset_id, ACCESSION, FILENAME)
        document_id = self.capture(b"<html>body</html>")
        self.store.record_filing_declaration(
            filing_declaration_id(
                self.asset_id, ACCESSION, "SUBMISSIONS_API_FILING_INDEX",
                form="10-Q", filing_date="2026-05-01",
            ),
            self.asset_id, ACCESSION, "SUBMISSIONS_API_FILING_INDEX",
            FIRST_HAND_AT, "FIRST_HAND", form="10-Q", filing_date="2026-05-01",
        )
        items = filing_item_declaration_id(
            self.asset_id, ACCESSION, "SUBMISSIONS_API_ITEMS", "2.02,9.01"
        )
        self.store.record_filing_item_declaration(
            items, self.asset_id, ACCESSION, "SUBMISSIONS_API_ITEMS",
            "2.02,9.01", FIRST_HAND_AT, "FIRST_HAND", declared_item_count=2,
        )
        self.store.record_filing_item(
            filing_item_id(items, 1, "2.02"), items, 1, "2.02", FIRST_HAND_AT,
        )
        self.store.record_filing_document_declaration(
            filing_document_declaration_id(
                self.asset_id, ACCESSION, "EDGAR_FULL_SUBMISSION_TEXT", 1,
                FILENAME, sec_document_type="8-K",
            ),
            self.asset_id, ACCESSION, "EDGAR_FULL_SUBMISSION_TEXT", 1,
            FIRST_HAND_AT, "FIRST_HAND", filename=FILENAME,
            sec_document_type="8-K",
        )
        identity = filing_document_statement_identity(
            self.asset_id, ACCESSION, FILENAME, document_id,
            "SECTION_18_NOT_DEEMED_FILED", "0:64",
        )
        self.store.record_filing_document_statement(
            filing_document_statement_id(
                self.asset_id, ACCESSION, FILENAME, document_id,
                "SECTION_18_NOT_DEEMED_FILED", "0:64",
            ),
            identity, self.asset_id, ACCESSION, FILENAME, document_id,
            "SECTION_18_NOT_DEEMED_FILED", "0:64", "Section 18",
            "DECLARED_VERBATIM_QUOTE", FIRST_HAND_AT, "FIRST_HAND",
        )
        self.store.record_filing_acceptance(
            filing_acceptance_id(
                self.asset_id, ACCESSION, "SGML_HEADER_ACCEPTANCE_DATETIME",
                "20260730163028", "INSTANT",
            ),
            self.asset_id, ACCESSION, "SGML_HEADER_ACCEPTANCE_DATETIME",
            "INSTANT", FIRST_HAND_AT, "FIRST_HAND",
            acceptance_datetime="20260730163028",
        )
        self.store.record_fiscal_calendar_declaration(
            fiscal_calendar_declaration_id(
                self.asset_id, "0926", "SGML_HEADER_FISCAL_YEAR_END", ACCESSION,
            ),
            self.asset_id, "0926", "SGML_HEADER_FISCAL_YEAR_END", FIRST_HAND_AT,
            "FIRST_HAND", declaring_accession=ACCESSION,
        )
        self.store.record_observation_filing_document(
            self.observation_id, self.asset_id, ACCESSION, FILENAME,
            FIRST_HAND_AT, "FIRST_HAND",
        )

    def test_no_provenance_writer_issues_a_write_against_observations(self):
        before = len(self.traced)
        self.exercise_every_provenance_writer()
        issued = self.traced[before:]
        offenders = [
            sql for sql in issued
            if re.search(
                r"\b(INSERT\s+OR\s+REPLACE|UPDATE|DELETE)\b[\s\S]{0,120}"
                r"\bobservations\b", sql, re.IGNORECASE,
            )
        ]
        self.assertEqual([], offenders)
        self.assertTrue(issued, "the trace callback captured nothing to check")

    def test_the_observation_is_byte_identical_after_enrichment(self):
        before = self.snapshot()
        self.exercise_every_provenance_writer()
        self.assertEqual(before, self.snapshot())

    def test_the_link_is_explicit_and_never_derived_from_the_accession(self):
        """An 8-K accession must not become an EX-99.1 by itself."""
        self.store.record_filing(self.asset_id, SECOND_ACCESSION, FIRST_HAND_AT)
        declaration = filing_document_declaration_id(
            self.asset_id, SECOND_ACCESSION,
            "EDGAR_FILING_DIRECTORY_INDEX_JSON", 4, FILENAME_EX991,
            mime_type="text.gif",
        )
        self.store.record_filing_document_declaration(
            declaration, self.asset_id, SECOND_ACCESSION,
            "EDGAR_FILING_DIRECTORY_INDEX_JSON", 4, FIRST_HAND_AT,
            "FIRST_HAND", filename=FILENAME_EX991, mime_type="text.gif",
        )
        # The document exists and the observation knows the accession. Nothing
        # links them, because linking is a caller's assertion and not a
        # consequence of the accession.
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertEqual(
            SECOND_ACCESSION,
            self.connection.execute(
                "SELECT accession FROM filings WHERE accession = ?",
                (SECOND_ACCESSION,),
            ).fetchone()[0],
        )


if __name__ == "__main__":
    unittest.main()