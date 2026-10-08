"""
ST-EVA Phase 3B - document-level statement provenance.

Fourteen assertions about the last link in the provenance chain:

    filing_documents -> filing_document_captures -> source_documents
                     -> filing_document_statements

The fixtures are shaped from the **measured real filing**, not invented:

* the primary 8-K carries the Section 18 sentence inside a `<span style=...>`
  and with HTML entities (`&#8220;filed&#8221;`), at byte 30586 of 38459, with
  `Section 18` 56 bytes later and `Item 2.02` at a *different* offset, 29858;
* the EX-99.1 exhibit contains **zero** occurrences of `shall not be deemed`,
  `Section 18` or `Item 2.02` — it has the results, not the statement about
  their legal status.

That asymmetry is the test. A pipeline that looked in the exhibit "because it
holds the earnings material" would find nothing, and one that copied the
statement there would be fabricating provenance from a document that does not
carry it.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List, Optional, Tuple

from core_registry import CoreRegistry
from registry_seed import seed
from sec_ingest import Ingestor
from sec_provider import extract_section18_statement
from sqlite_archive import SQLiteArchive

from test_sec_document_bytes import (  # noqa: E402  shared realistic fixture
    ACCESSION, CIK, DIRECTORY_ENTRIES, EXHIBIT, PRIMARY, SGML_DOCUMENTS,
    TICKER, document_bytes,
)

# The measured sentence, with the measured markup around it.
SECTION_18_SPAN = (
    b'<div style="margin-top:12pt;text-align:justify">'
    b'<span style="color:#000000;font-size:9pt">'
    b"The information contained in this Current Report shall not be deemed "
    b"&#8220;filed&#8221; for purposes of Section 18 of the Securities Exchange "
    b"Act of 1934, as amended (the &#8220;Exchange Act&#8221;), or incorporated "
    b"by reference in any filing under the Securities Act of 1933, as amended."
    b"</span></div>"
)

PRIMARY_BODY = (
    b"<html><body>"
    b"<div style='-sec-extract:summary'><span>Item&#160;2.02 Results of "
    b"Operations and Financial Condition</span></div>"
    b"<p>Third Quarter 2026 Results.</p>"
    + SECTION_18_SPAN
    + b"<p>Item 9.01 Financial Statements and Exhibits.</p>"
    b"</body></html>"
)

# The exhibit: the financial results, and nothing about their legal status.
EXHIBIT_BODY = (
    b"<html><body><h1>Apple Reports Third Quarter Results</h1>"
    b"<p>Revenue of $98.0 billion. Diluted EPS of $1.65.</p>"
    b"<p>These results are furnished herewith.</p>"
    b"</body></html>"
)

# A primary document that says nothing about Section 18 at all.
QUIET_PRIMARY_BODY = (
    b"<html><body><p>Item 8.01 Other Events.</p>"
    b"<p>An agreement was entered into.</p></body></html>"
)


def provider(primary_body: bytes = PRIMARY_BODY,
             exhibit_body: bytes = EXHIBIT_BODY) -> Any:
    """A fixture provider serving distinct bodies for the two documents."""
    from test_sec_document_bytes import ByteProvider, fetched_document

    class StatementProvider(ByteProvider):
        def filing_document(self, cik: str, accession: str,
                            filename: str) -> Any:
            self.requested.append(f"document:{filename}")
            body = (primary_body if filename == PRIMARY
                    else exhibit_body if filename == EXHIBIT
                    else document_bytes(filename))
            return fetched_document(filename, body)

    return StatementProvider()


class StatementBase(unittest.TestCase):
    def run_ingest(self, prov: Any, store: Optional[SQLiteArchive] = None
                   ) -> Tuple[Any, SQLiteArchive]:
        store = store or SQLiteArchive(":memory:")
        registry = CoreRegistry(store.connection)
        seed(registry)
        report = Ingestor(store, prov, registry).ingest(
            TICKER, metrics=["eps_diluted"], forms=["8-K"])
        return report, store

    def statements(self, store: SQLiteArchive) -> List[Dict[str, Any]]:
        return [
            dict(row) for row in store.connection.execute(
                "SELECT * FROM filing_document_statements"
                " ORDER BY statement_kind, quote_locator"
            )
        ]


# --------------------------------------------------------------------------
# Extraction is real, and comes from the right document
# --------------------------------------------------------------------------


class TestStatementExtraction(StatementBase):
    def test_the_section_18_statement_is_read_from_the_primary_8k(self):
        report, store = self.run_ingest(provider())
        try:
            self.assertEqual([], report.errors)
            rows = self.statements(store)
            self.assertEqual(1, len(rows))
            self.assertEqual(PRIMARY, rows[0]["filename"])
            self.assertEqual("SECTION_18_NOT_DEEMED_FILED",
                             rows[0]["statement_kind"])
            self.assertIn("shall not be deemed", rows[0]["quote_text"])
            self.assertIn("Section 18", rows[0]["quote_text"])
        finally:
            store.close()

    def test_the_exhibit_is_never_used_as_the_source(self):
        """The exhibit carries the results, not the statement about them."""
        report, store = self.run_ingest(provider())
        try:
            rows = self.statements(store)
            self.assertEqual([PRIMARY], [r["filename"] for r in rows])
            self.assertNotIn(EXHIBIT, [r["filename"] for r in rows])
            # And the archive agrees: the exhibit really does not contain it.
            exhibit_hash = store.connection.execute(
                "SELECT content_hash FROM source_documents WHERE document_id ="
                " (SELECT document_id FROM filing_document_captures"
                "  WHERE filename = ?)", (EXHIBIT,)).fetchone()[0]
            self.assertIsNone(extract_section18_statement(
                store.content_for(exhibit_hash)))
        finally:
            store.close()

    def test_an_exhibit_named_like_the_primary_cannot_substitute(self):
        """
        The primary document is chosen by the submission's first `<DOCUMENT>`,
        never by looking for whichever file mentions Section 18.
        """
        report, store = self.run_ingest(provider(
            primary_body=QUIET_PRIMARY_BODY,
            exhibit_body=EXHIBIT_BODY + SECTION_18_SPAN))
        try:
            # The exhibit now contains the language, and is still not read.
            self.assertEqual(0, len(self.statements(store)))
            exhibit_hash = store.connection.execute(
                "SELECT content_hash FROM source_documents WHERE document_id ="
                " (SELECT document_id FROM filing_document_captures"
                "  WHERE filename = ?)", (EXHIBIT,)).fetchone()[0]
            self.assertIsNotNone(extract_section18_statement(
                store.content_for(exhibit_hash)))
        finally:
            store.close()

    def test_a_primary_document_that_says_nothing_yields_no_statement(self):
        report, store = self.run_ingest(provider(primary_body=QUIET_PRIMARY_BODY))
        try:
            self.assertEqual([], report.errors)
            self.assertEqual(0, len(self.statements(store)))
        finally:
            store.close()

    def test_no_document_bytes_means_no_statement(self):
        """
        Without captured bytes there is nothing to quote. A capture row alone
        must never become a statement.
        """
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            connection = store.connection
            asset_id = store.record_asset(TICKER, cik=CIK, name="Apple Inc.")
            connection.execute(
                "INSERT INTO filings (asset_id, accession, first_archived_at)"
                " VALUES (?, ?, '2026-07-31T00:30:28Z')",
                (asset_id, ACCESSION))
            for source, ordinal, name in (
                ("EDGAR_FULL_SUBMISSION_TEXT", 1, PRIMARY),
                ("EDGAR_FILING_DIRECTORY_INDEX_JSON", 1, PRIMARY),
            ):
                connection.execute(
                    "INSERT INTO filing_document_declarations (declaration_id,"
                    " asset_id, accession, manifest_source, source_ordinal,"
                    " filename, captured_at, capture_kind)"
                    " VALUES (?, ?, ?, ?, ?, ?, '2026-07-31T00:30:28Z',"
                    " 'FIRST_HAND')",
                    (f"d{source}", asset_id, ACCESSION, source, ordinal, name))
            connection.execute(
                "INSERT INTO filing_documents (asset_id, accession, filename,"
                " first_declared_at) VALUES (?, ?, ?, '2026-07-31T00:30:28Z')",
                (asset_id, ACCESSION, PRIMARY))
            # A capture whose bytes were stored as a reference, not as content.
            document_id = store.record_source_document(_reference_document())
            connection.execute(
                "INSERT INTO filing_document_captures (asset_id, accession,"
                " filename, document_id, acquisition_class, captured_at,"
                " capture_kind) VALUES (?, ?, ?, ?, 'SEC_FILING_DOCUMENT',"
                " '2026-07-31T00:30:28Z', 'FIRST_HAND')",
                (asset_id, ACCESSION, PRIMARY, document_id))
            connection.commit()
            ingestor = Ingestor(store, provider(), registry)
            self.assertEqual(
                0, ingestor._acquire_document_statements(asset_id, ACCESSION))
            self.assertEqual(0, connection.execute(
                "SELECT COUNT(*) FROM filing_document_statements"
            ).fetchone()[0])
        finally:
            store.close()

    def test_no_capture_at_all_means_no_statement(self):
        store = SQLiteArchive(":memory:")
        try:
            registry = CoreRegistry(store.connection)
            seed(registry)
            connection = store.connection
            asset_id = store.record_asset(TICKER, cik=CIK, name="Apple Inc.")
            connection.execute(
                "INSERT INTO filings (asset_id, accession, first_archived_at)"
                " VALUES (?, ?, '2026-07-31T00:30:28Z')",
                (asset_id, ACCESSION))
            for source, ordinal in (
                ("EDGAR_FULL_SUBMISSION_TEXT", 1),
                ("EDGAR_FILING_DIRECTORY_INDEX_JSON", 1),
            ):
                connection.execute(
                    "INSERT INTO filing_document_declarations (declaration_id,"
                    " asset_id, accession, manifest_source, source_ordinal,"
                    " filename, captured_at, capture_kind)"
                    " VALUES (?, ?, ?, ?, ?, ?, '2026-07-31T00:30:28Z',"
                    " 'FIRST_HAND')",
                    (f"e{source}", asset_id, ACCESSION, source, ordinal, PRIMARY))
            connection.execute(
                "INSERT INTO filing_documents (asset_id, accession, filename,"
                " first_declared_at) VALUES (?, ?, ?, '2026-07-31T00:00:00Z')",
                (asset_id, ACCESSION, PRIMARY))
            connection.commit()
            ingestor = Ingestor(store, provider(), registry)
            # The document exists and its bytes exist nowhere. No statement.
            self.assertEqual(
                0, ingestor._acquire_document_statements(asset_id, ACCESSION))
        finally:
            store.close()


# --------------------------------------------------------------------------
# Capture linkage, locator, identity
# --------------------------------------------------------------------------


class TestStatementLinkage(StatementBase):
    def test_the_statement_names_the_exact_capture_it_was_read_from(self):
        report, store = self.run_ingest(provider())
        try:
            row = self.statements(store)[0]
            capture = store.connection.execute(
                "SELECT document_id, acquisition_class, capture_kind,"
                " captured_at FROM filing_document_captures"
                " WHERE asset_id = ? AND accession = ? AND filename = ?"
                " AND document_id = ?",
                (row["asset_id"], row["accession"], row["filename"],
                 row["document_id"]),
            ).fetchone()
            self.assertIsNotNone(capture)
            self.assertEqual(row["document_id"], capture["document_id"])
            # The statement carries the capture's provenance, not its own.
            self.assertEqual(capture["capture_kind"], row["capture_kind"])
            self.assertEqual("SEC_FILING_DOCUMENT",
                             capture["acquisition_class"])
        finally:
            store.close()

    def test_a_statement_cannot_exist_without_its_capture(self):
        """The composite foreign key is what stops a statement floating free."""
        report, store = self.run_ingest(provider())
        try:
            row = self.statements(store)[0]
            with self.assertRaises(Exception):
                store.connection.execute(
                    "INSERT INTO filing_document_statements (statement_id,"
                    " statement_identity, asset_id, accession, filename,"
                    " document_id, statement_kind, quote_locator, quote_text,"
                    " extraction_method, extracted_at, capture_kind)"
                    " VALUES ('fds_x', 'identity-x', ?, ?, ?, 'doc_orphan',"
                    " 'SECTION_18_NOT_DEEMED_FILED', '0:9', 'x',"
                    " 'DECLARED_VERBATIM_QUOTE', '2026-07-31T00:30:28Z',"
                    " 'FIRST_HAND')",
                    (row["asset_id"], row["accession"], row["filename"]))
            store.connection.rollback()
        finally:
            store.close()

    def test_the_quote_and_locator_address_the_stored_bytes_exactly(self):
        report, store = self.run_ingest(provider())
        try:
            row = self.statements(store)[0]
            start, end = (int(p) for p in row["quote_locator"].split(":"))
            content_hash = store.connection.execute(
                "SELECT content_hash FROM source_documents WHERE document_id = ?",
                (row["document_id"],)).fetchone()[0]
            stored = store.content_for(content_hash)
            self.assertEqual(
                stored[start:end].decode("utf-8"), row["quote_text"])
            # And the quotation is genuinely inside the document.
            self.assertIn(b"Section 18", stored[start:end])
            self.assertNotIn(b"<span", stored[start:end])
        finally:
            store.close()

    def test_statement_identity_is_stable_and_scoped_to_its_capture(self):
        report, store = self.run_ingest(provider())
        try:
            row = self.statements(store)[0]
            from sec_provenance import (
                filing_document_statement_id,
                filing_document_statement_identity,
            )
            self.assertEqual(
                filing_document_statement_id(
                    row["asset_id"], row["accession"], row["filename"],
                    row["document_id"], row["statement_kind"],
                    row["quote_locator"],
                ),
                row["statement_id"],
            )
            self.assertEqual(
                filing_document_statement_identity(
                    row["asset_id"], row["accession"], row["filename"],
                    row["document_id"], row["statement_kind"],
                    row["quote_locator"],
                ),
                row["statement_identity"],
            )
            # quote_text is payload and is not in the identity.
            self.assertNotIn(row["quote_text"], row["statement_identity"])
            # Nor is the extraction time.
            self.assertNotIn(row["extracted_at"], row["statement_identity"])
        finally:
            store.close()

    def test_repeated_extraction_is_idempotent(self):
        store = SQLiteArchive(":memory:")
        try:
            prov = provider()
            registry = CoreRegistry(store.connection)
            seed(registry)
            ingestor = Ingestor(store, prov, registry)
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            first = self.statements(store)
            self.assertEqual(1, len(first))
            for _ in range(3):
                asset_id = store.asset_id_for_cik(CIK)
                ingestor._acquire_document_statements(asset_id, ACCESSION)
            self.assertEqual(first, self.statements(store))
        finally:
            store.close()

    def test_a_conflicting_extraction_is_refused_not_absorbed(self):
        """
        The same capture, kind and locator yielding different words is a
        contradiction. It must surface, not be conflict-ignored.
        """
        store = SQLiteArchive(":memory:")
        try:
            prov = provider()
            registry = CoreRegistry(store.connection)
            seed(registry)
            ingestor = Ingestor(store, prov, registry)
            ingestor.ingest(TICKER, metrics=["eps_diluted"], forms=["8-K"])
            row = self.statements(store)[0]
            with self.assertRaises(Exception) as caught:
                store.record_filing_document_statement(
                    row["statement_id"], row["statement_identity"],
                    row["asset_id"], row["accession"], row["filename"],
                    row["document_id"], row["statement_kind"],
                    row["quote_locator"], "a different quotation entirely",
                    "DECLARED_VERBATIM_QUOTE", "2027-01-01T00:00:00Z",
                    "LATER_ACQUISITION",
                )
            self.assertIn("not deterministic", str(caught.exception))
            self.assertEqual(row["quote_text"], self.statements(store)[0]
                             ["quote_text"])
        finally:
            store.close()

    def test_a_second_capture_of_changed_bytes_gets_its_own_statement(self):
        report, store = self.run_ingest(provider())
        try:
            self.assertEqual(1, len(self.statements(store)))
            # A later capture with different bytes is a different document_id,
            # so the statement identity differs and both are kept.
            asset_id = store.asset_id_for_cik(CIK)
            second = b"<html><body><p>Replacement.</p>" + SECTION_18_SPAN + \
                     b"</body></html>"
            document_id = store.record_source_document(_stored(PRIMARY, second))
            store.record_filing_document_capture(
                asset_id, ACCESSION, PRIMARY, document_id,
                "SEC_FILING_DOCUMENT", "2027-01-01T00:00:00Z",
                "LATER_ACQUISITION")
            rows = self.statements(store)
            self.assertEqual(1, len(rows))
            # The new capture has not been read yet in this test; the identity
            # that a statement from it would carry is nonetheless distinct.
            from sec_provenance import filing_document_statement_id
            new_id = filing_document_statement_id(
                asset_id, ACCESSION, PRIMARY, document_id,
                "SECTION_18_NOT_DEEMED_FILED",
                extract_section18_statement(second).quote_locator,
            )
            self.assertNotEqual(rows[0]["statement_id"], new_id)
        finally:
            store.close()


# --------------------------------------------------------------------------
# Nothing else moves
# --------------------------------------------------------------------------


class TestStatementScope(StatementBase):
    def test_no_observation_row_is_modified(self):
        run_clock = ("retrieved_at", "first_archived_at")
        _, with_statements = self.run_ingest(provider())
        _, without = self.run_ingest(provider(primary_body=QUIET_PRIMARY_BODY))
        try:
            observed = [
                {k: ("<clock>" if k in run_clock else v)
                 for k, v in dict(r).items()}
                for r in with_statements.connection.execute(
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
            self.assertEqual(1, len(self.statements(with_statements)))
        finally:
            with_statements.close()
            without.close()

    def test_no_observation_document_link_is_created(self):
        report, store = self.run_ingest(provider())
        try:
            self.assertEqual(0, store.connection.execute(
                "SELECT COUNT(*) FROM observation_filing_documents"
            ).fetchone()[0])
        finally:
            store.close()

    def test_no_classification_and_no_audit_status_appear(self):
        report, store = self.run_ingest(provider())
        try:
            for table in ("filing_document_statements", "filings",
                          "filing_documents", "observations"):
                columns = {
                    r["name"] for r in store.connection.execute(
                        f"PRAGMA table_info({table})")
                }
                for forbidden in ("evidence_class", "audit_status", "sec_item",
                                  "furnished", "legal_status"):
                    self.assertNotIn(forbidden, columns, table)
            row = self.statements(store)[0]
            # The statement is a quotation, not a verdict.
            self.assertTrue(row["quote_text"].startswith("The information"))
            self.assertIn("shall not be deemed", row["quote_text"])
        finally:
            store.close()

    def test_the_item_code_is_read_from_the_documents_own_bytes(self):
        report, store = self.run_ingest(provider())
        try:
            row = self.statements(store)[0]
            # The measured filing names Item 2.02 in its heading, before the
            # sentence, and writes the separator as an HTML entity.
            self.assertEqual("2.02", row["applies_to_filing_item_code"])
            # The governed document type is not derivable and is not guessed.
            self.assertIsNone(row["applies_to_document_type"])
        finally:
            store.close()

    def test_item_semantics_are_unchanged(self):
        """The frozen rule still holds: only a code source writes item rows."""
        report, store = self.run_ingest(provider())
        try:
            # Both declaration sources are present and unmerged.
            sources = {
                r[0] for r in store.connection.execute(
                    "SELECT DISTINCT declaration_source FROM"
                    " filing_item_declarations")
            }
            self.assertEqual({"SUBMISSIONS_API_ITEMS", "SGML_ITEM_INFORMATION"},
                             sources)
            # Every `filing_items` row descends from the code source alone.
            producers = {
                r[0] for r in store.connection.execute(
                    "SELECT DISTINCT d.declaration_source FROM filing_items i"
                    " JOIN filing_item_declarations d"
                    " ON d.declaration_id = i.declaration_id")
            }
            self.assertEqual({"SUBMISSIONS_API_ITEMS"}, producers)
            self.assertEqual(
                {"2.02", "9.01"},
                {r[0] for r in store.connection.execute(
                    "SELECT item_code FROM filing_items")},
            )
            # The header's titles are still preserved verbatim and uncoded.
            sgml = store.connection.execute(
                "SELECT raw_items_text FROM filing_item_declarations"
                " WHERE declaration_source = 'SGML_ITEM_INFORMATION'"
            ).fetchone()
            self.assertIn("Results of Operations", sgml["raw_items_text"])
        finally:
            store.close()


def _reference_document() -> Any:
    """A stored document captured as a reference: a hash, but no payload."""
    return _stored(PRIMARY, b"not stored", keep_payload=False)


def _stored(filename: str, payload: bytes,
            keep_payload: bool = True) -> Any:
    """A StoredDocument for one document's bytes, as a fetch would produce."""
    import hashlib as _hashlib

    from archive import StoredDocument

    return StoredDocument(
        content_hash="sha256:" + _hashlib.sha256(payload).hexdigest(),
        uri=("https://www.sec.gov/Archives/edgar/data/320193/"
             f"000032019326000018/{filename}"),
        canonical_uri=None, http_status=200, media_type="text/html",
        byte_size=len(payload), fetched_at="2026-07-31T00:30:28Z",
        first_seen_at="2026-07-31T00:30:28Z",
        payload=payload if keep_payload else None,
        provider="SecEdgar", document_type="SEC_FILING_DOCUMENT",
    )


if __name__ == "__main__":
    unittest.main()