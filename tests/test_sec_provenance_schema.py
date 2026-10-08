"""
ST-EVA 0020 - SEC provenance schema conformance.

Twenty assertions, one per decision the design passes took. Every one of them is
a statement about what the archive does *now*, not about what it should do, and
each is anchored to a finding that was measured rather than argued:

    §1  a key that names the producer rather than the assertion turns a changed
        assertion into a discarded one (`admission_identity`,
        `sqlite_archive.py:283-308`).
    §4  `index.json` and the SGML `<DOCUMENT>` sequence disagree at every
        position, measured 0/17 on one filing and 7/79 on another, so their
        ordinals are not interchangeable.
    §5  `index.json`'s `type` is a MIME type, so it cannot name an exhibit.
    §6  `source_documents.document_type` was verified to be plain TEXT with no
        CHECK, no trigger and no writer validation, so no filing semantic may be
        read out of it.
    §7  a re-extraction that changes its own wording is a contradiction, not a
        new statement and not a no-op.
    §10 `held_filings.report_date` was run-verified holding the XBRL fiscal year
        ('2026') on fact-path rows, and `period_end` NULL on every row, because
        `_ensure_filing_identity` runs first and `INSERT OR IGNORE` means first
        write wins permanently. The projection below must not launder that.

Nothing here fetches anything, reads `%TEMP%`, or touches the network. The
archive is in-memory and every value is a literal.
"""

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from typing import Any, Dict, Optional

from archive import ArchiveError, FilingRef, StoredDocument
from core_registry import CoreRegistry
from data_contract import METRIC_EPS_DILUTED
from evidence_model import source_fact_id
from registry_seed import seed
from sec_ingest import SEC_SOURCE, Ingestor
from sqlite_archive import SQLiteArchive

ASSET = "AAPL"
CIK = "0000320193"
ACCESSION = "0000320193-26-000018"
OUT_OF_WINDOW = "0001193125-13-170623"

MANIFEST_DIRECTORY = "EDGAR_FILING_DIRECTORY_INDEX_JSON"
MANIFEST_SGML = "EDGAR_FULL_SUBMISSION_TEXT"

FILENAME_EX991 = "a8-kex991q3202606272026.htm"
FILENAME_PRIMARY = "aapl-20260730.htm"

QUOTE = (
    'shall not be deemed "filed" for purposes of Section 18 of the '
    "Securities Exchange Act of 1934"
)


# ---------------------------------------------------------------------------
# Identity, in the repository's own convention
# ---------------------------------------------------------------------------


def canonical_json(payload: Dict[str, Any]) -> str:
    """One rendering, so the same assertion hashes the same way on any machine.

    Byte-for-byte what `sqlite_archive._canonical` does
    (`sqlite_archive.py:81-84`), which is what `sfid_` and `adm_` hash.
    """
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def digest_id(prefix: str, payload: Dict[str, Any], width: int = 32) -> str:
    return prefix + hashlib.sha256(
        canonical_json(payload).encode("utf-8")
    ).hexdigest()[:width]


def filing_declaration_id(
    asset_id: str,
    accession: str,
    declaration_source: str,
    form: Optional[str] = None,
    filing_date: Optional[str] = None,
    report_date: Optional[str] = None,
    conformed_period_of_report: Optional[str] = None,
    public_document_count: Optional[int] = None,
    is_xbrl: Optional[int] = None,
    primary_document: Optional[str] = None,
) -> str:
    return digest_id("decl_", {
        "asset_id": asset_id,
        "accession": accession,
        "declaration_source": declaration_source,
        "form": form,
        "filing_date": filing_date,
        "report_date": report_date,
        "conformed_period_of_report": conformed_period_of_report,
        "public_document_count": public_document_count,
        "is_xbrl": is_xbrl,
        "primary_document": primary_document,
    })


def item_declaration_id(
    asset_id: str, accession: str, declaration_source: str, raw_items_text: str
) -> str:
    return digest_id("fid_", {
        "asset_id": asset_id,
        "accession": accession,
        "declaration_source": declaration_source,
        "raw_items_text": raw_items_text,
    })


def item_id(
    declaration_id: str,
    item_ordinal: int,
    item_code: str,
    item_title: Optional[str] = None,
    title_source: Optional[str] = None,
) -> str:
    return digest_id("fit_", {
        "declaration_id": declaration_id,
        "item_ordinal": item_ordinal,
        "item_code": item_code,
        "item_title": item_title,
        "title_source": title_source,
    })


def document_declaration_id(
    asset_id: str,
    accession: str,
    manifest_source: str,
    source_ordinal: int,
    filename: Optional[str],
    sec_document_type: Optional[str] = None,
    mime_type: Optional[str] = None,
    byte_size: Optional[int] = None,
    description: Optional[str] = None,
) -> str:
    return digest_id("fdd_", {
        "asset_id": asset_id,
        "accession": accession,
        "manifest_source": manifest_source,
        "source_ordinal": source_ordinal,
        "filename": filename,
        "sec_document_type": sec_document_type,
        "mime_type": mime_type,
        "byte_size": byte_size,
        "description": description,
    })


def acceptance_id(
    asset_id: str,
    accession: str,
    acceptance_source: str,
    acceptance_datetime: Optional[str],
    acceptance_precision: str,
    raw_value: Optional[str] = None,
) -> str:
    return digest_id("fac_", {
        "asset_id": asset_id,
        "accession": accession,
        "acceptance_source": acceptance_source,
        "acceptance_datetime": acceptance_datetime,
        "acceptance_precision": acceptance_precision,
        "raw_value": raw_value,
    })


def fiscal_calendar_declaration_id(
    asset_id: str,
    fiscal_year_end_mmdd: str,
    declaration_source: str,
    declaring_accession: Optional[str] = None,
) -> str:
    return digest_id("ifc_", {
        "asset_id": asset_id,
        "fiscal_year_end_mmdd": fiscal_year_end_mmdd,
        "declaration_source": declaration_source,
        "declaring_accession": declaring_accession,
    })


def statement_identity(
    asset_id: str,
    accession: str,
    filename: str,
    document_id: str,
    statement_kind: str,
    quote_locator: str,
) -> str:
    return canonical_json({
        "asset_id": asset_id,
        "accession": accession,
        "filename": filename,
        "document_id": document_id,
        "statement_kind": statement_kind,
        "quote_locator": quote_locator,
    })


def statement_id(asset_id: str, accession: str, filename: str,
                 document_id: str, statement_kind: str,
                 quote_locator: str) -> str:
    return "fds_" + hashlib.sha256(
        statement_identity(
            asset_id, accession, filename, document_id,
            statement_kind, quote_locator,
        ).encode("utf-8")
    ).hexdigest()[:32]


# ---------------------------------------------------------------------------
# The approved deterministic projection
# ---------------------------------------------------------------------------


def project_held_filings(store: SQLiteArchive) -> Dict[str, int]:
    """
    Project the four approved columns of `held_filings` into the new relations.

    Deterministic and idempotent: the same ledger rows always produce the same
    identity, so a second run is a no-op.

    It projects `asset_id`, `accession`, `form` and `filed_at` and **nothing
    else**. `period_end`, `report_date`, `primary_document` and `document_id`
    are excluded on purpose: `report_date` was run-verified holding the XBRL
    fiscal year ('2026') rather than a date, `period_end` is NULL on every row,
    `primary_document` is NULL on every fact-path row, and `document_id` is the
    empty string at both writers. Projecting any of them would launder a known
    ledger defect into an authoritative filing fact.

    It lives here rather than in the migration for two reasons. The migration
    engine hashes a file and runs it as SQL, so it cannot compute a content
    digest, and every identity in this schema is one. And wiring this into a
    production writer is a change to `sqlite_archive.py` or `sec_ingest.py`,
    which this task does not authorise. `capture_kind` is FIRST_HAND and
    `captured_at` is the ledger's own `first_seen_at`, never the migration
    timestamp: the value really was captured when the ingest that wrote the
    ledger row saw the filing, and claiming otherwise would make the archive
    assert it could not know the filing's form until upgrade day.
    """
    connection = store.connection
    created = 0
    rows = connection.execute(
        "SELECT asset_id, accession, form, filed_at, first_seen_at"
        " FROM held_filings"
    ).fetchall()
    for row in rows:
        identity = filing_declaration_id(
            row["asset_id"], row["accession"],
            "MIGRATION_PROJECTION_HELD_FILINGS",
            form=row["form"], filing_date=row["filed_at"],
        )
        if connection.execute(
            "SELECT 1 FROM filing_declarations WHERE declaration_id = ?",
            (identity,),
        ).fetchone() is None:
            created += 1
        connection.execute(
            "INSERT OR IGNORE INTO filings (asset_id, accession,"
            " first_archived_at) VALUES (?, ?, ?)",
            (row["asset_id"], row["accession"], row["first_seen_at"]),
        )
        connection.execute(
            "INSERT OR IGNORE INTO filing_declarations (declaration_id,"
            " asset_id, accession, declaration_source, form, filing_date,"
            " report_date, conformed_period_of_report, public_document_count,"
            " is_xbrl, primary_document, declared_at, captured_at,"
            " capture_kind)"
            " VALUES (?, ?, ?, 'MIGRATION_PROJECTION_HELD_FILINGS', ?, ?,"
            " NULL, NULL, NULL, NULL, NULL, NULL, ?, 'FIRST_HAND')",
            (
                identity, row["asset_id"], row["accession"], row["form"],
                row["filed_at"], row["first_seen_at"],
            ),
        )
    connection.commit()
    return {
        "rows_seen": len(rows),
        "created": created,
        "declarations_held": connection.execute(
            "SELECT COUNT(*) FROM filing_declarations"
            " WHERE declaration_source = 'MIGRATION_PROJECTION_HELD_FILINGS'"
        ).fetchone()[0],
    }


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


class ProvenanceArchive(unittest.TestCase):
    """An in-memory archive with one asset and one filing."""

    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.store.record_asset(ASSET, cik=CIK, name="Apple Inc.")
        self.asset_id = self.asset_id_of(ASSET)
        self.add_filing()

    def tearDown(self) -> None:
        self.store.close()

    # -- helpers ---------------------------------------------------------

    @property
    def connection(self):
        return self.store.connection

    def asset_id_of(self, ticker: str) -> str:
        return self.connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ?", (ticker,)
        ).fetchone()["asset_id"]

    def add_filing(self, accession: str = ACCESSION,
                   first_archived_at: str = "2026-07-31T00:30:28Z") -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO filings (asset_id, accession,"
            " first_archived_at) VALUES (?, ?, ?)",
            (self.asset_id, accession, first_archived_at),
        )
        self.connection.commit()

    def add_declaration(self, declaration_source: str, **fields: Any) -> str:
        identity = filing_declaration_id(
            self.asset_id, fields.pop("accession", ACCESSION),
            declaration_source, **fields
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_declarations (declaration_id,"
            " asset_id, accession, declaration_source, form, filing_date,"
            " report_date, conformed_period_of_report, public_document_count,"
            " is_xbrl, primary_document, declared_at, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, 'FIRST_HAND')",
            (
                identity, self.asset_id,
                fields.pop("accession", ACCESSION) if "accession" in fields
                else ACCESSION,
                declaration_source,
                fields.get("form"), fields.get("filing_date"),
                fields.get("report_date"),
                fields.get("conformed_period_of_report"),
                fields.get("public_document_count"), fields.get("is_xbrl"),
                fields.get("primary_document"), "2026-08-01T00:00:00Z",
            ),
        )
        self.connection.commit()
        return identity

    def add_document_declaration(
        self,
        manifest_source: str,
        source_ordinal: int,
        filename: Optional[str],
        sec_document_type: Optional[str] = None,
        mime_type: Optional[str] = None,
        byte_size: Optional[int] = None,
        description: Optional[str] = None,
        accession: str = ACCESSION,
    ) -> str:
        identity = document_declaration_id(
            self.asset_id, accession, manifest_source, source_ordinal,
            filename, sec_document_type, mime_type, byte_size, description,
        )
        self.connection.execute(
            "INSERT INTO filing_document_declarations (declaration_id,"
            " asset_id, accession, manifest_source, source_ordinal, filename,"
            " sec_document_type, mime_type, byte_size, description,"
            " last_modified, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?,"
            " 'FIRST_HAND')",
            (
                identity, self.asset_id, accession, manifest_source,
                source_ordinal, filename, sec_document_type, mime_type,
                byte_size, description, "2026-08-01T00:00:00Z",
            ),
        )
        self.connection.commit()
        return identity

    def add_document(self, filename: str, accession: str = ACCESSION) -> None:
        self.connection.execute(
            "INSERT INTO filing_documents (asset_id, accession, filename,"
            " first_declared_at) VALUES (?, ?, ?, '2026-08-01T00:00:00Z')",
            (self.asset_id, accession, filename),
        )
        self.connection.commit()

    def capture_document(self, payload: bytes, filename: str,
                         accession: str = ACCESSION,
                         capture_kind: str = "FIRST_HAND",
                         captured_at: str = "2026-08-01T00:00:00Z") -> str:
        """Capture bytes into source_documents, then link them as a capture."""
        document_id = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
            uri=(
                "https://www.sec.gov/Archives/edgar/data/320193/"
                f"{accession.replace('-', '')}/{filename}"
            ),
            canonical_uri=None, http_status=200, media_type="text/html",
            byte_size=len(payload), fetched_at=captured_at,
            first_seen_at=captured_at,
            payload=payload,
            provider=SEC_SOURCE, document_type="SEC_FILING_DOCUMENT",
        ))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_captures (asset_id,"
            " accession, filename, document_id, acquisition_class,"
            " captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, 'SEC_FILING_DOCUMENT', ?, ?)",
            (self.asset_id, accession, filename, document_id, captured_at,
             capture_kind),
        )
        self.connection.commit()
        return document_id

    def count(self, table: str, where: str = "", *args: Any) -> int:
        clause = f" WHERE {where}" if where else ""
        return self.connection.execute(
            f"SELECT COUNT(*) AS n FROM {table}{clause}", args
        ).fetchone()["n"]

    def declare_and_capture(self, filename: str, payload: bytes,
                            mime_type: str = "text.gif",
                            ordinal: int = 1) -> str:
        """The ordinary path: a directory declaration, an identity, a capture."""
        self.add_document_declaration(
            MANIFEST_DIRECTORY, ordinal, filename,
            mime_type=mime_type, byte_size=len(payload),
        )
        self.add_document(filename)
        return self.capture_document(payload, filename)


# ---------------------------------------------------------------------------
# 1. Filing identity
# ---------------------------------------------------------------------------


class TestFilingIdentity(ProvenanceArchive):
    def test_one_accession_is_one_filing(self):
        self.add_filing(ACCESSION, "2026-07-31T00:30:28Z")
        self.add_filing(ACCESSION, "2026-08-02T00:00:00Z")
        self.assertEqual(1, self.count("filings", "accession = ?", ACCESSION))

    def test_a_second_writer_cannot_change_the_first_archive_time(self):
        before = self.connection.execute(
            "SELECT first_archived_at FROM filings WHERE accession = ?",
            (ACCESSION,),
        ).fetchone()["first_archived_at"]
        self.add_filing(ACCESSION, "2026-08-02T00:00:00Z")
        after = self.connection.execute(
            "SELECT first_archived_at FROM filings WHERE accession = ?",
            (ACCESSION,),
        ).fetchone()["first_archived_at"]
        self.assertEqual(before, after)

    def test_a_different_accession_is_a_different_filing(self):
        self.add_filing(OUT_OF_WINDOW)
        self.assertEqual(2, self.count("filings"))


# ---------------------------------------------------------------------------
# 2-3. Declaration content identity
# ---------------------------------------------------------------------------


class TestDeclarationIdentity(ProvenanceArchive):
    def test_the_same_assertion_has_the_same_identity(self):
        first = self.add_declaration(
            "SUBMISSIONS_API_FILING_INDEX", form="8-K",
            filing_date="2026-07-30", is_xbrl=1,
        )
        second = self.add_declaration(
            "SUBMISSIONS_API_FILING_INDEX", form="8-K",
            filing_date="2026-07-30", is_xbrl=1,
        )
        self.assertEqual(first, second)
        self.assertEqual(1, self.count("filing_declarations"))

    def test_the_identity_is_a_prefixed_digest_of_the_assertion(self):
        identity = self.add_declaration(
            "SGML_SUBMISSION_HEADER", form="8-K",
            conformed_period_of_report="20260730", public_document_count=14,
        )
        self.assertTrue(identity.startswith("decl_"), identity)
        self.assertEqual(37, len(identity))

    def test_a_changed_assertion_creates_a_second_row_and_keeps_the_first(self):
        first = self.add_declaration(
            "SGML_SUBMISSION_HEADER", form="8-K", public_document_count=14
        )
        second = self.add_declaration(
            "SGML_SUBMISSION_HEADER", form="8-K", public_document_count=16
        )
        self.assertNotEqual(first, second)
        self.assertEqual(2, self.count("filing_declarations"))
        survived = self.connection.execute(
            "SELECT public_document_count FROM filing_declarations"
            " WHERE declaration_id = ?", (first,)
        ).fetchone()["public_document_count"]
        self.assertEqual(14, survived)

    def test_capture_time_is_not_part_of_the_identity(self):
        """Re-confirmation must be a no-op, not a new identity."""
        first = filing_declaration_id(
            self.asset_id, ACCESSION, "SUBMISSIONS_API_FILING_INDEX",
            form="8-K", filing_date="2026-07-30",
        )
        self.add_declaration(
            "SUBMISSIONS_API_FILING_INDEX", form="8-K",
            filing_date="2026-07-30",
        )
        self.assertEqual(
            1, self.count("filing_declarations", "declaration_id = ?", first)
        )

    def test_a_vocabulary_violation_is_refused(self):
        with self.assertRaises(Exception) as caught:
            self.add_declaration("SOMEWHERE_ELSE", form="8-K")
        self.assertIn("closed vocabulary", str(caught.exception))


# ---------------------------------------------------------------------------
# 4. Two item declaration sources coexist
# ---------------------------------------------------------------------------


class TestFilingItemIdentity(ProvenanceArchive):
    def test_one_accession_may_carry_two_declaring_resources(self):
        api = item_declaration_id(
            self.asset_id, ACCESSION, "SUBMISSIONS_API_ITEMS", "2.02,9.01"
        )
        sgml = item_declaration_id(
            self.asset_id, ACCESSION, "SGML_ITEM_INFORMATION",
            "Results of Operations and Financial Condition",
        )
        self.assertNotEqual(api, sgml)
        for identity, source, raw in (
            (api, "SUBMISSIONS_API_ITEMS", "2.02,9.01"),
            (sgml, "SGML_ITEM_INFORMATION",
             "Results of Operations and Financial Condition"),
        ):
            self.connection.execute(
                "INSERT INTO filing_item_declarations (declaration_id,"
                " asset_id, accession, declaration_source, raw_items_text,"
                " declared_item_count, declared_at, captured_at, capture_kind)"
                " VALUES (?, ?, ?, ?, ?, NULL, NULL, '2026-08-01T00:00:00Z',"
                " 'FIRST_HAND')",
                (identity, self.asset_id, ACCESSION, source, raw),
            )
        self.connection.commit()
        self.assertEqual(2, self.count("filing_item_declarations"))

    def test_the_same_ordinal_under_two_sources_is_two_items_not_a_collision(self):
        api = item_declaration_id(
            self.asset_id, ACCESSION, "SUBMISSIONS_API_ITEMS", "2.02,9.01"
        )
        sgml = item_declaration_id(
            self.asset_id, ACCESSION, "SGML_ITEM_INFORMATION", "2.02"
        )
        for declaration, code in ((api, "2.02"), (sgml, "2.02")):
            self.connection.execute(
                "INSERT INTO filing_item_declarations (declaration_id,"
                " asset_id, accession, declaration_source, raw_items_text,"
                " declared_item_count, declared_at, captured_at, capture_kind)"
                " VALUES (?, ?, ?, 'SUBMISSIONS_API_ITEMS', ?, NULL, NULL,"
                " '2026-08-01T00:00:00Z', 'FIRST_HAND')",
                (declaration, self.asset_id, ACCESSION, code),
            )
            self.connection.execute(
                "INSERT INTO filing_items (item_id, declaration_id,"
                " item_ordinal, item_code, item_title, title_source,"
                " captured_at) VALUES (?, ?, 1, ?, NULL, NULL,"
                " '2026-08-01T00:00:00Z')",
                (item_id(declaration, 1, "2.02"), declaration, "2.02"),
            )
        self.connection.commit()
        self.assertEqual(2, self.count("filing_items"))
        self.assertEqual(2, self.count(
            "filing_items", "item_ordinal = 1"))

    def test_a_changed_parse_does_not_discard_the_earlier_item(self):
        declaration = item_declaration_id(
            self.asset_id, ACCESSION, "SUBMISSIONS_API_ITEMS", "2.02,9.01"
        )
        self.connection.execute(
            "INSERT INTO filing_item_declarations (declaration_id, asset_id,"
            " accession, declaration_source, raw_items_text,"
            " declared_item_count, declared_at, captured_at, capture_kind)"
            " VALUES (?, ?, ?, 'SUBMISSIONS_API_ITEMS', '2.02,9.01', NULL,"
            " NULL, '2026-08-01T00:00:00Z', 'FIRST_HAND')",
            (declaration, self.asset_id, ACCESSION),
        )
        for code in ("2.02", "9.01"):
            self.connection.execute(
                "INSERT INTO filing_items (item_id, declaration_id,"
                " item_ordinal, item_code, item_title, title_source,"
                " captured_at) VALUES (?, ?, 1, ?, NULL, NULL,"
                " '2026-08-01T00:00:00Z')",
                (item_id(declaration, 1, code), declaration, code),
            )
        self.connection.commit()
        self.assertEqual(2, self.count("filing_items"))


# ---------------------------------------------------------------------------
# 5-6. Document declaration ordinals, SEC TYPE versus MIME
# ---------------------------------------------------------------------------


class TestDocumentDeclarations(ProvenanceArchive):
    def test_the_two_manifest_ordinals_are_independent(self):
        """Measured: index ordinal 4 and SGML ordinal 1 are different facts."""
        directory = self.add_document_declaration(
            MANIFEST_DIRECTORY, 4, FILENAME_EX991, mime_type="text.gif",
        )
        sgml = self.add_document_declaration(
            MANIFEST_SGML, 1, FILENAME_EX991, sec_document_type="EX-99.1",
        )
        self.assertNotEqual(directory, sgml)
        self.assertEqual(1, self.count(
            "filing_document_declarations",
            "source_ordinal = 1 AND manifest_source = ?", MANIFEST_SGML))
        self.assertEqual(1, self.count(
            "filing_document_declarations",
            "source_ordinal = 4 AND manifest_source = ?", MANIFEST_DIRECTORY))

    def test_sec_document_type_and_mime_type_are_separate_columns(self):
        self.add_document_declaration(
            MANIFEST_SGML, 1, FILENAME_EX991, sec_document_type="EX-99.1",
            mime_type="text.gif",
        )
        row = self.connection.execute(
            "SELECT sec_document_type, mime_type FROM"
            " filing_document_declarations"
        ).fetchone()
        self.assertEqual("EX-99.1", row["sec_document_type"])
        self.assertEqual("text.gif", row["mime_type"])

    def test_two_exhibits_are_told_apart_although_their_mime_is_identical(self):
        """`index.json` cannot do this, which is why MIME is not the identity."""
        self.add_document_declaration(
            MANIFEST_SGML, 1, "d515445dex991.htm", sec_document_type="EX-99.1",
            mime_type="text.gif",
        )
        self.add_document_declaration(
            MANIFEST_SGML, 2, "d515445dex992.htm", sec_document_type="EX-99.2",
            mime_type="text.gif",
        )
        types = [
            r["sec_document_type"] for r in self.connection.execute(
                "SELECT sec_document_type FROM filing_document_declarations"
                " ORDER BY sec_document_type"
            )
        ]
        self.assertEqual(["EX-99.1", "EX-99.2"], types)

    def test_a_directory_declaration_supplies_no_sec_document_type(self):
        self.add_document_declaration(
            MANIFEST_DIRECTORY, 0 + 1, FILENAME_EX991, mime_type="text.gif",
        )
        row = self.connection.execute(
            "SELECT sec_document_type FROM filing_document_declarations"
        ).fetchone()
        self.assertIsNone(row["sec_document_type"])


# ---------------------------------------------------------------------------
# 7-8. FilingDocument identity
# ---------------------------------------------------------------------------


class TestFilingDocumentIdentity(ProvenanceArchive):
    def test_only_a_directory_declaration_mints_an_identity(self):
        self.add_document_declaration(
            MANIFEST_SGML, 1, FILENAME_EX991, sec_document_type="EX-99.1",
        )
        with self.assertRaises(Exception) as caught:
            self.add_document(FILENAME_EX991)
        self.assertIn("minted only by a directory-manifest", str(caught.exception))

    def test_a_duplicate_filename_cannot_mint_an_identity(self):
        """Both declarations survive; no identity row is created or merged."""
        self.add_document_declaration(
            MANIFEST_DIRECTORY, 1, FILENAME_EX991, mime_type="text.gif",
        )
        self.add_document_declaration(
            MANIFEST_DIRECTORY, 2, FILENAME_EX991, mime_type="text.gif",
        )
        with self.assertRaises(Exception) as caught:
            self.add_document(FILENAME_EX991)
        self.assertIn("declared more than once", str(caught.exception))
        self.assertEqual(2, self.count("filing_document_declarations",
                                       "filename = ?", FILENAME_EX991))
        self.assertEqual(0, self.count("filing_documents"))

    def test_an_identity_carries_no_source_asserted_attribute(self):
        self.declare_and_capture(FILENAME_EX991, b"<html>exhibit</html>")
        columns = {
            r["name"] for r in self.connection.execute(
                "PRAGMA table_info(filing_documents)"
            )
        }
        self.assertEqual(
            {"asset_id", "accession", "filename", "first_declared_at"},
            columns,
        )
        for forbidden in ("document_type", "mime_type", "source_ordinal",
                          "document_id", "capture_kind"):
            self.assertNotIn(forbidden, columns)

    def test_a_declared_document_without_capture_is_representable(self):
        self.add_document_declaration(
            MANIFEST_DIRECTORY, 1, FILENAME_EX991, mime_type="text.gif",
        )
        self.add_document(FILENAME_EX991)
        self.assertEqual(1, self.count("filing_documents"))
        self.assertEqual(0, self.count("filing_document_captures"))

    def test_a_document_without_a_filename_gets_no_identity(self):
        self.add_document_declaration(MANIFEST_SGML, 1, None,
                                      sec_document_type="XML")
        self.assertEqual(1, self.count("filing_document_declarations",
                                       "filename IS NULL"))
        self.assertEqual(0, self.count("filing_documents"))


# ---------------------------------------------------------------------------
# 10-11. Capture lifecycle
# ---------------------------------------------------------------------------


class TestCaptureLifecycle(ProvenanceArchive):
    def test_identical_bytes_are_an_idempotent_capture(self):
        payload = b"<html>the exhibit</html>"
        first = self.declare_and_capture(FILENAME_EX991, payload)
        again = self.capture_document(payload, FILENAME_EX991)
        self.assertEqual(first, again)
        self.assertEqual(1, self.count("filing_document_captures"))
        self.assertEqual(1, self.count("source_documents"))

    def test_changed_bytes_are_a_new_capture_and_the_first_survives(self):
        self.declare_and_capture(FILENAME_EX991, b"<html>first</html>")
        second = self.capture_document(b"<html>second</html>", FILENAME_EX991)
        self.assertEqual(2, self.count("filing_document_captures"))
        self.assertEqual(2, self.count("source_documents"))
        document_ids = {
            r["document_id"] for r in self.connection.execute(
                "SELECT document_id FROM filing_document_captures"
                " ORDER BY document_id"
            )
        }
        self.assertEqual(2, len(document_ids))
        self.assertIn(second, document_ids)

    def test_the_same_bytes_referenced_twice_are_one_content_object(self):
        self.declare_and_capture(FILENAME_EX991, b"<html>shared</html>")
        self.add_document_declaration(
            MANIFEST_DIRECTORY, 2, FILENAME_PRIMARY, mime_type="text.gif",
        )
        self.add_document(FILENAME_PRIMARY)
        self.capture_document(b"<html>shared</html>", FILENAME_PRIMARY)
        self.assertEqual(1, self.count("source_documents"))
        self.assertEqual(2, self.count("filing_document_captures"))

    def test_a_capture_requires_an_existing_document_identity(self):
        self.add_document_declaration(
            MANIFEST_DIRECTORY, 1, FILENAME_EX991, mime_type="text.gif",
        )
        with self.assertRaises(Exception):
            self.capture_document(b"<html>orphan</html>", FILENAME_EX991)


# ---------------------------------------------------------------------------
# 12-13. Statements
# ---------------------------------------------------------------------------


class TestFilingDocumentStatements(ProvenanceArchive):
    BODY = (
        "<html><body>The information in this Current Report shall not be deemed"
        ' "filed" for purposes of Section 18 of the Securities Exchange Act of'
        " 1934, as amended.</body></html>"
    )

    def declare_and_capture_primary(self, payload: Optional[bytes] = None
                                    ) -> str:
        payload = payload if payload is not None else self.BODY.encode()
        self.add_document_declaration(
            MANIFEST_DIRECTORY, 1, FILENAME_PRIMARY, mime_type="text.gif",
        )
        self.add_document_declaration(
            MANIFEST_SGML, 1, FILENAME_PRIMARY, sec_document_type="8-K",
        )
        self.add_document(FILENAME_PRIMARY)
        return self.capture_document(payload, FILENAME_PRIMARY)

    def insert_statement(self, document_id: str, quote_text: str,
                         quote_locator: str = "0:64",
                         filename: str = FILENAME_PRIMARY,
                         kind: str = "SECTION_18_NOT_DEEMED_FILED") -> str:
        identity = statement_identity(
            self.asset_id, ACCESSION, filename, document_id, kind,
            quote_locator,
        )
        key = statement_id(
            self.asset_id, ACCESSION, filename, document_id, kind,
            quote_locator,
        )
        self.connection.execute(
            "INSERT INTO filing_document_statements (statement_id,"
            " statement_identity, asset_id, accession, filename, document_id,"
            " statement_kind, quote_locator, quote_text, extraction_method,"
            " extracted_at, capture_kind, applies_to_document_type,"
            " applies_to_filing_item_code)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'DECLARED_VERBATIM_QUOTE',"
            " '2026-08-01T00:00:00Z', 'FIRST_HAND', 'EX-99.1', '2.02')",
            (key, identity, self.asset_id, ACCESSION, filename, document_id,
             kind, quote_locator, quote_text),
        )
        self.connection.commit()
        return key

    def test_a_statement_binds_to_one_capture_and_its_bytes(self):
        document_id = self.declare_and_capture_primary()
        self.insert_statement(document_id, QUOTE)
        row = self.connection.execute(
            "SELECT document_id, filename, applies_to_document_type,"
            " applies_to_filing_item_code FROM filing_document_statements"
        ).fetchone()
        self.assertEqual(document_id, row["document_id"])
        self.assertEqual(FILENAME_PRIMARY, row["filename"])
        self.assertEqual("EX-99.1", row["applies_to_document_type"])
        self.assertEqual("2.02", row["applies_to_filing_item_code"])
        stored = self.store.content_for(
            self.connection.execute(
                "SELECT content_hash FROM source_documents WHERE document_id = ?",
                (document_id,),
            ).fetchone()["content_hash"]
        )
        self.assertIn(QUOTE, stored.decode())

    def test_a_statement_about_an_uncaptured_byte_sequence_is_refused(self):
        document_id = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + "9" * 64, uri="x", canonical_uri=None,
            http_status=200, media_type="text/html", byte_size=1,
            fetched_at="2026-08-01T00:00:00Z",
            first_seen_at="2026-08-01T00:00:00Z", payload=b"x",
            provider=SEC_SOURCE, document_type="SEC_FILING_DOCUMENT",
        ))
        with self.assertRaises(Exception):
            self.insert_statement(document_id, QUOTE)

    def test_the_same_capture_with_different_words_is_refused_loudly(self):
        """The design's named contradiction: never a silent conflict-ignore."""
        document_id = self.declare_and_capture_primary()
        self.insert_statement(document_id, QUOTE)
        with self.assertRaises(Exception) as caught:
            self.insert_statement(document_id, QUOTE.replace("Section 18",
                                                             "Section 13"))
        self.assertIn("not deterministic", str(caught.exception))
        self.assertEqual(1, self.count("filing_document_statements"))

    def test_re_extracting_the_same_words_is_idempotent(self):
        document_id = self.declare_and_capture_primary()
        first = self.insert_statement(document_id, QUOTE)
        identity = statement_identity(
            self.asset_id, ACCESSION, FILENAME_PRIMARY, document_id,
            "SECTION_18_NOT_DEEMED_FILED", "0:64",
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_statements (statement_id,"
            " statement_identity, asset_id, accession, filename, document_id,"
            " statement_kind, quote_locator, quote_text, extraction_method,"
            " extracted_at, capture_kind, applies_to_document_type,"
            " applies_to_filing_item_code)"
            " VALUES (?, ?, ?, ?, ?, ?, 'SECTION_18_NOT_DEEMED_FILED', '0:64',"
            " ?, 'DECLARED_VERBATIM_QUOTE', '2026-08-02T00:00:00Z',"
            " 'FIRST_HAND', 'EX-99.1', '2.02')",
            (first, identity, self.asset_id, ACCESSION, FILENAME_PRIMARY,
             document_id, QUOTE),
        )
        self.connection.commit()
        self.assertEqual(1, self.count("filing_document_statements"))

    def test_a_new_byte_sequence_is_a_new_statement_and_the_first_survives(self):
        first_document = self.declare_and_capture_primary(b"<html>first</html>")
        self.insert_statement(first_document, QUOTE)
        second_document = self.capture_document(b"<html>second</html>",
                                                FILENAME_PRIMARY)
        self.insert_statement(second_document, QUOTE)
        self.assertEqual(2, self.count("filing_document_statements"))
        rows = self.connection.execute(
            "SELECT document_id FROM filing_document_statements"
        ).fetchall()
        self.assertEqual({first_document, second_document},
                         {r["document_id"] for r in rows})


# ---------------------------------------------------------------------------
# 14-15. Filing acceptance
# ---------------------------------------------------------------------------


class TestFilingAcceptance(ProvenanceArchive):
    def insert_acceptance(self, source: str, value: Optional[str],
                          precision: str,
                          raw: Optional[str] = None) -> str:
        identity = acceptance_id(
            self.asset_id, ACCESSION, source, value, precision, raw
        )
        self.connection.execute(
            "INSERT INTO filing_acceptances (declaration_id, asset_id,"
            " accession, acceptance_source, acceptance_datetime,"
            " acceptance_precision, raw_value, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, '2026-08-01T00:00:00Z',"
            " 'FIRST_HAND')",
            (identity, self.asset_id, ACCESSION, source, value, precision, raw),
        )
        self.connection.commit()
        return identity

    def test_both_producers_persist_for_one_filing(self):
        """The same instant, expressed two ways. One filing, two assertions."""
        self.insert_acceptance("SGML_HEADER_ACCEPTANCE_DATETIME",
                               "20260730163028", "INSTANT")
        self.insert_acceptance("SUBMISSIONS_API_ACCEPTANCE_DATETIME",
                               "2026-07-31T00:30:28.000Z", "INSTANT")
        self.assertEqual(2, self.count("filing_acceptances"))
        self.assertEqual(1, self.count("filings", "accession = ?", ACCESSION))

    def test_a_fact_filed_date_is_not_an_acceptance(self):
        with self.assertRaises(Exception) as caught:
            self.insert_acceptance("FACT_FILED_DATE", "2026-07-30", "DATE")
        self.assertIn("closed vocabulary", str(caught.exception))

    def test_precision_none_requires_a_null_datetime(self):
        with self.assertRaises(Exception) as caught:
            self.insert_acceptance("SGML_HEADER_ACCEPTANCE_DATETIME",
                                   "20260730163028", "NONE")
        self.assertIn("must be NULL", str(caught.exception))

    def test_a_declared_precision_requires_a_datetime(self):
        with self.assertRaises(Exception) as caught:
            self.insert_acceptance("SGML_HEADER_ACCEPTANCE_DATETIME",
                                   None, "INSTANT")
        self.assertIn("requires an acceptance_datetime", str(caught.exception))

    def test_consulted_and_declared_nothing_is_representable(self):
        identity = self.insert_acceptance(
            "SUBMISSIONS_API_ACCEPTANCE_DATETIME", None, "NONE", ""
        )
        row = self.connection.execute(
            "SELECT acceptance_datetime, raw_value FROM filing_acceptances"
            " WHERE declaration_id = ?", (identity,)
        ).fetchone()
        self.assertIsNone(row["acceptance_datetime"])
        self.assertEqual("", row["raw_value"])

    def test_there_is_no_precedence_column(self):
        columns = {
            r["name"] for r in self.connection.execute(
                "PRAGMA table_info(filing_acceptances)"
            )
        }
        for forbidden in ("priority", "precedence", "is_current",
                          "superseded", "active", "authoritative"):
            self.assertNotIn(forbidden, columns)


# ---------------------------------------------------------------------------
# 16. Observation is untouched
# ---------------------------------------------------------------------------


class TestObservationIsUntouched(ProvenanceArchive):
    def setUp(self) -> None:
        super().setUp()
        self.registry = CoreRegistry(self.connection)
        seed(self.registry)
        self.ingestor = Ingestor(self.store, object(), self.registry)
        self.entry = {
            "start": "2026-01-01", "end": "2026-03-28", "val": 1.65,
            "accn": ACCESSION, "fy": 2026, "fp": "Q2", "frame": "CY2026Q1",
            "form": "10-Q", "filed": "2026-05-01",
        }
        payload = {
            "cik": CIK, "taxonomy": "us-gaap", "tag": "EarningsPerShareDiluted",
            "label": "EPS", "description": "Diluted EPS",
        }
        mapping = next(
            m for m in self.registry.mappings_for_metric(METRIC_EPS_DILUTED)
            if m.concept_id == "us-gaap:EarningsPerShareDiluted"
        )
        availability = self.ingestor._availability_for(self.entry, {})
        observation = self.ingestor._observation(
            METRIC_EPS_DILUTED, "us-gaap", "EarningsPerShareDiluted",
            mapping, payload, self.entry, "USD/shares",
            self.entry["start"], self.entry["end"], *availability, ACCESSION,
        )
        fact_id = source_fact_id(
            source_id=SEC_SOURCE, document_ref=ACCESSION,
            taxonomy="us-gaap", concept="EarningsPerShareDiluted",
            period_start=self.entry["start"], period_end=self.entry["end"],
            context=ACCESSION,
        )
        self.observation_id = self.store.record_observation(
            asset=ASSET, observation=observation,
            availability_class="SOURCE_DECLARED",
            filing=self.ingestor._filing(
                fact_id, "us-gaap", "EarningsPerShareDiluted", ACCESSION,
                self.entry, self.entry["start"],
            ),
        )

    def snapshot(self) -> Dict[str, Any]:
        row = self.connection.execute(
            "SELECT * FROM observations WHERE observation_id = ?",
            (self.observation_id,),
        ).fetchone()
        return {key: row[key] for key in row.keys()}

    def test_an_observation_is_byte_identical_after_provenance_is_written(self):
        before = self.snapshot()
        self.declare_and_capture(FILENAME_EX991, b"<html>exhibit</html>")
        self.add_declaration(
            "SUBMISSIONS_API_FILING_INDEX", form="10-Q",
            filing_date="2026-05-01", report_date="2026-03-28",
        )
        self.add_filing(ACCESSION, "2026-05-01T20:01:00Z")
        self.connection.execute(
            "INSERT INTO observation_filing_documents (observation_id,"
            " asset_id, accession, filename, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, '2026-08-01T00:00:00Z', 'LATER_ACQUISITION')",
            (self.observation_id, self.asset_id, ACCESSION, FILENAME_EX991),
        )
        self.connection.commit()
        self.assertEqual(before, self.snapshot())

    def test_no_classification_reaches_the_observation_row(self):
        self.declare_and_capture(FILENAME_EX991, b"<html>exhibit</html>")
        for forbidden in ("evidence_class", "audit_status", "sec_item",
                          "legal_status_note"):
            columns = {
                r["name"] for r in self.connection.execute(
                    "PRAGMA table_info(observations)"
                )
            }
            self.assertNotIn(forbidden, columns)
        self.connection.execute(
            "INSERT INTO observation_filing_documents (observation_id,"
            " asset_id, accession, filename, captured_at, capture_kind)"
            " VALUES (?, ?, ?, ?, '2026-08-01T00:00:00Z', 'FIRST_HAND')",
            (self.observation_id, self.asset_id, ACCESSION, FILENAME_EX991),
        )
        self.connection.commit()
        self.assertEqual(before := self.snapshot(), self.snapshot())
        self.assertNotIn("evidence_class", str(before))

    def test_the_link_is_not_inferred_from_the_accession_alone(self):
        before = self.count("observation_filing_documents")
        self.declare_and_capture(FILENAME_EX991, b"<html>exhibit</html>")
        self.assertEqual(
            before, self.count("observation_filing_documents")
        )


# ---------------------------------------------------------------------------
# 17-18. Projection and capture provenance
# ---------------------------------------------------------------------------


class TestHeldFilingsProjection(ProvenanceArchive):
    def seed_ledger(self) -> None:
        """A ledger row in exactly the shape the run-verified probe produced."""
        self.connection.execute(
            "INSERT OR IGNORE INTO held_filings (asset_id, accession, form,"
            " filed_at, period_end, report_date, primary_document, document_id,"
            " first_seen_at) VALUES (?, ?, '10-Q', '2026-05-01', NULL, '2026',"
            " NULL, '', '2026-05-01T16:01:00Z')",
            (self.asset_id, ACCESSION),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO held_filings (asset_id, accession, form,"
            " filed_at, period_end, report_date, primary_document, document_id,"
            " first_seen_at) VALUES (?, ?, '8-K', '2009-10-27', NULL, '2009',"
            " NULL, '', '2009-10-27T00:00:00Z')",
            (self.asset_id, OUT_OF_WINDOW),
        )
        self.connection.commit()

    def test_the_defective_ledger_columns_are_not_projected(self):
        """`report_date` held '2026', the XBRL fiscal year. It must not move."""
        self.seed_ledger()
        report = project_held_filings(self.store)
        self.assertEqual(2, report["rows_seen"])
        self.assertEqual(2, report["created"])
        projected = self.connection.execute(
            "SELECT form, filing_date, report_date,"
            " conformed_period_of_report, public_document_count, is_xbrl,"
            " primary_document FROM filing_declarations"
            " WHERE declaration_source = 'MIGRATION_PROJECTION_HELD_FILINGS'"
            " ORDER BY accession"
        ).fetchall()
        self.assertEqual(2, len(projected))
        for row in projected:
            self.assertIsNone(row["report_date"])
            self.assertIsNone(row["conformed_period_of_report"])
            self.assertIsNone(row["public_document_count"])
            self.assertIsNone(row["is_xbrl"])
            self.assertIsNone(row["primary_document"])
            self.assertIsNotNone(row["form"])
            self.assertIsNotNone(row["filing_date"])
        self.assertEqual(
            ["10-Q", "8-K"], [r["form"] for r in projected]
        )

    def test_capture_time_is_the_original_capture_not_the_projection(self):
        self.seed_ledger()
        project_held_filings(self.store)
        captured = {
            r["accession"]: r["captured_at"]
            for r in self.connection.execute(
                "SELECT accession, captured_at FROM filing_declarations"
                " WHERE declaration_source = 'MIGRATION_PROJECTION_HELD_FILINGS'"
            )
        }
        ledger = {
            r["accession"]: r["first_seen_at"]
            for r in self.connection.execute(
                "SELECT accession, first_seen_at FROM held_filings"
            )
        }
        self.assertEqual(ledger, captured)

    def test_the_projection_is_idempotent(self):
        self.seed_ledger()
        project_held_filings(self.store)
        before = self.count("filing_declarations")
        again = project_held_filings(self.store)
        self.assertEqual(2, again["rows_seen"])
        self.assertEqual(0, again["created"])
        self.assertEqual(before, self.count("filing_declarations"))
        self.assertEqual(2, self.count("filings"))

    def test_later_acquisition_stays_distinguishable(self):
        self.declare_and_capture(FILENAME_EX991, b"<html>exhibit</html>")
        second = self.capture_document(
            b"<html>exhibit, re-fetched later</html>", FILENAME_EX991,
            capture_kind="LATER_ACQUISITION",
            captured_at="2027-01-01T00:00:00Z",
        )
        rows = {
            r["capture_kind"]: r["captured_at"]
            for r in self.connection.execute(
                "SELECT capture_kind, captured_at FROM filing_document_captures"
            )
        }
        self.assertEqual(2, len(rows))
        self.assertEqual("2026-08-01T00:00:00Z", rows["FIRST_HAND"])
        self.assertEqual("2027-01-01T00:00:00Z", rows["LATER_ACQUISITION"])
        self.assertEqual(
            second,
            self.connection.execute(
                "SELECT document_id FROM filing_document_captures"
                " WHERE capture_kind = 'LATER_ACQUISITION'"
            ).fetchone()["document_id"],
        )


# ---------------------------------------------------------------------------
# 19-20. Discipline
# ---------------------------------------------------------------------------


NEW_RELATIONS = (
    "filings", "filing_declarations", "filing_item_declarations",
    "filing_items", "filing_document_declarations", "filing_documents",
    "filing_document_captures", "filing_document_statements",
    "filing_acceptances", "issuer_fiscal_calendar_declarations",
    "observation_filing_documents",
)


class TestDiscipline(ProvenanceArchive):
    def test_all_eleven_relations_exist(self):
        for relation in NEW_RELATIONS:
            self.assertEqual(
                1,
                self.connection.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                    " AND name = ?", (relation,)
                ).fetchone()[0],
                relation,
            )

    def test_no_evidence_table_was_created(self):
        for forbidden in ("evidence", "quarter_eps_evidence", "historical_pe",
                          "historical_p_e"):
            found = self.connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                " AND name = ?", (forbidden,)
            ).fetchone()[0]
            self.assertEqual(0, found, forbidden)

    def test_every_relation_is_append_only(self):
        """
        Two assertions per relation, because they fail for different reasons.

        A `BEFORE DELETE` trigger fires *per row*, so on an empty relation it
        never fires and would silently pass. The trigger's existence is therefore
        asserted structurally for all eleven, and its behaviour is exercised on
        the relations this fixture can populate.
        """
        for relation in NEW_RELATIONS:
            for operation in ("no_update", "no_delete"):
                self.assertIsNotNone(
                    self.connection.execute(
                        "SELECT sql FROM sqlite_master WHERE type='trigger'"
                        " AND name = ?", (f"{relation}_{operation}",)
                    ).fetchone(),
                    f"{relation} has no {operation} trigger",
                )

    def test_update_and_delete_are_refused_on_a_populated_relation(self):
        self.declare_and_capture(FILENAME_EX991, b"<html>exhibit</html>")
        self.add_declaration("SUBMISSIONS_API_FILING_INDEX", form="8-K")
        for relation in ("filings", "filing_declarations", "filing_documents",
                         "filing_document_declarations",
                         "filing_document_captures"):
            with self.assertRaises(Exception, msg=f"UPDATE {relation}"):
                self.connection.execute(f"UPDATE {relation} SET 1 = 1")
            with self.assertRaises(Exception, msg=f"DELETE {relation}"):
                self.connection.execute(f"DELETE FROM {relation}")
            self.connection.rollback()
        self.assertEqual(1, self.count("filings", "accession = ?", ACCESSION))
        self.assertEqual(1, self.count("filing_documents"))

    def test_no_existing_relation_gained_a_provenance_column(self):
        existing = {
            "observations": {"evidence_class", "audit_status", "sec_item",
                             "legal_status_note", "filing_document_id"},
            "held_filings": {"items", "acceptance_source",
                             "acceptance_precision"},
            "source_documents": {"accession", "is_primary"},
            "observation_sources": {"document_type"},
        }
        for relation, forbidden in existing.items():
            columns = {
                r["name"] for r in self.connection.execute(
                    f"PRAGMA table_info({relation})"
                )
            }
            for column in forbidden:
                self.assertNotIn(column, columns, f"{relation}.{column}")

    def test_the_migration_checksum_discipline_still_aborts(self):
        import sqlite_archive

        version, name = 20, "sec_provenance"
        recorded = self.connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            (version,),
        ).fetchone()["checksum"]
        path = sqlite_archive.MIGRATIONS_DIR / f"{version:04d}_{name}.sql"
        self.assertEqual(
            recorded, hashlib.sha256(path.read_text(encoding="utf-8")
                                     .encode("utf-8")).hexdigest()
        )
        self.connection.execute(
            "UPDATE schema_migrations SET checksum = 'tampered'"
            " WHERE version = ?", (version,)
        )
        self.connection.commit()
        with self.assertRaises(ArchiveError):
            self.store._ensure_schema()


if __name__ == "__main__":
    unittest.main()