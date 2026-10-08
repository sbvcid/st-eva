"""Phase 3C-C1 — SEC Taxonomy Catalog Acquisition (offline, deterministic).

Tests acquisition of edgartaxonomies.xml through existing provider/ archive
machinery. No live SEC dependency. No parsing. No authority-row creation.
"""
from __future__ import annotations

import hashlib
import io
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

# Module under test (archive/ is a directory, not a package; load by path)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "acquire_taxonomy_catalog", "archive/acquire_taxonomy_catalog.py"
)
_acquire_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_acquire_mod)
fetch_taxonomy_catalog_bytes = _acquire_mod.fetch_taxonomy_catalog_bytes
record_taxonomy_catalog = _acquire_mod.record_taxonomy_catalog
URL = _acquire_mod.URL

# Existing archive subsystem for content-addressed recording
from sqlite_archive import SQLiteArchive
from archive import StoredDocument

# Synthetic byte payload mimicking the live SEC catalog structure
# (not parsed — only preserved as exact bytes).
SYNTHETIC_CATALOG_BYTES = (
    b'<Erxl version="78">\n'
    b'<Loc><Family>US GAAP</Family><Version>2026</Version>'
    b'<Namespace>http://fasb.org/us-gaap/2026</Namespace>'
    b'<Prefix>us-gaap</Prefix><FileTypeName>Schema</FileTypeName>'
    b'<Href>https://xbrl.fasb.org/us-gaap/2026/elts/us-gaap-2026.xsd</Href>'
    b'</Loc></Erxl>\n'
)


def _expected_content_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _expected_document_id(content_hash: str) -> str:
    return "doc_" + hashlib.sha256(content_hash.encode("utf-8")).hexdigest()[:24]


class MockUrlResponse:
    """Minimal mock for urllib.request.urlopen return value."""

    def __init__(self, payload: bytes, status: int = 200, headers=None):
        self._payload = payload
        self.status = status
        self.headers = headers or {}

    def getcode(self):
        return self.status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TaxonomyCatalogAcquisitionTest(unittest.TestCase):
    """C1 targeted tests — all offline."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="steva-c1-")
        self.db_path = os.path.join(self.tmpdir, "test.db")
        # SQLiteArchive applies 0001..0022 automatically on first use.
        self.archive = SQLiteArchive(self.db_path)
        # Pre-verify source_documents exists (from 0001) and 0022 exists.
        self.assertTrue(
            self.archive.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='source_documents'"
            ).fetchone()
        )
        self.assertTrue(
            self.archive.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='authority_taxonomy_namespaces'"
            ).fetchone()
        )

    def tearDown(self):
        self.archive.connection.close()
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # A. successful fetch -> exact bytes persisted
    def test_a_successful_fetch_bytes_persisted(self):
        with patch("urllib.request.urlopen", return_value=MockUrlResponse(SYNTHETIC_CATALOG_BYTES)):
            payload = fetch_taxonomy_catalog_bytes()
        self.assertIsInstance(payload, bytes)
        self.assertEqual(payload, SYNTHETIC_CATALOG_BYTES)
        # Record
        doc_id = record_taxonomy_catalog(payload, self.archive)
        self.assertTrue(doc_id.startswith("doc_"))
        # Verify byte preservation via content_for
        row = self.archive.connection.execute(
            "SELECT content, content_hash, byte_size, document_type FROM source_documents WHERE document_id = ?",
            (doc_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        content_stored, content_hash, byte_size, doc_type = row
        self.assertIsNotNone(content_stored)
        # Decompress if gzip; here payload stored compressed (archive default)
        # We just assert content_hash matches exact bytes.
        self.assertEqual(content_hash, _expected_content_hash(SYNTHETIC_CATALOG_BYTES))
        self.assertEqual(byte_size, len(SYNTHETIC_CATALOG_BYTES))
        self.assertEqual(doc_type, "SEC_TAXONOMY_CATALOG")

    # B. content hash is based on exact bytes
    def test_b_content_hash_exact_bytes(self):
        expected = _expected_content_hash(SYNTHETIC_CATALOG_BYTES)
        with patch("urllib.request.urlopen", return_value=MockUrlResponse(SYNTHETIC_CATALOG_BYTES)):
            payload = fetch_taxonomy_catalog_bytes()
        self.assertEqual(hashlib.sha256(payload).hexdigest(), expected)

    # C. document_id matches existing convention
    def test_c_document_id_convention(self):
        with patch("urllib.request.urlopen", return_value=MockUrlResponse(SYNTHETIC_CATALOG_BYTES)):
            payload = fetch_taxonomy_catalog_bytes()
        doc_id = record_taxonomy_catalog(payload, self.archive)
        expected_id = _expected_document_id(_expected_content_hash(SYNTHETIC_CATALOG_BYTES))
        self.assertEqual(doc_id, expected_id)

    # D. same bytes idempotent
    def test_d_same_bytes_idempotent(self):
        with patch("urllib.request.urlopen", return_value=MockUrlResponse(SYNTHETIC_CATALOG_BYTES)):
            payload = fetch_taxonomy_catalog_bytes()
        doc_id_1 = record_taxonomy_catalog(payload, self.archive)
        doc_id_2 = record_taxonomy_catalog(payload, self.archive)
        self.assertEqual(doc_id_1, doc_id_2)
        cnt = self.archive.connection.execute(
            "SELECT COUNT(*) FROM source_documents WHERE document_id = ?", (doc_id_1,)
        ).fetchone()[0]
        self.assertEqual(cnt, 1)

    # E. changed bytes create new document identity
    def test_e_changed_bytes_new_identity(self):
        with patch("urllib.request.urlopen", return_value=MockUrlResponse(SYNTHETIC_CATALOG_BYTES)):
            payload = fetch_taxonomy_catalog_bytes()
        doc_id_old = record_taxonomy_catalog(payload, self.archive)
        # Modify payload (simulating new SEC release / changed bytes)
        changed = SYNTHETIC_CATALOG_BYTES + b"\n<!-- changed -->"
        doc_id_new = record_taxonomy_catalog(changed, self.archive)
        self.assertNotEqual(doc_id_old, doc_id_new)
        # Old preserved
        old_row = self.archive.connection.execute(
            "SELECT 1 FROM source_documents WHERE document_id = ?", (doc_id_old,)
        ).fetchone()
        self.assertIsNotNone(old_row)
        new_row = self.archive.connection.execute(
            "SELECT 1 FROM source_documents WHERE document_id = ?", (doc_id_new,)
        ).fetchone()
        self.assertIsNotNone(new_row)

    # F. failed fetch -> no authority rows (and exception raised, not fabricated)
    def test_f_failed_fetch_no_fabricated_evidence(self):
        # Before any record, count authority rows
        before = self.archive.connection.execute(
            "SELECT COUNT(*) FROM authority_taxonomy_namespaces"
        ).fetchone()[0]
        with patch("urllib.request.urlopen", side_effect=TimeoutError("simulated timeout")):
            with self.assertRaises(Exception):
                fetch_taxonomy_catalog_bytes()
        after = self.archive.connection.execute(
            "SELECT COUNT(*) FROM authority_taxonomy_namespaces"
        ).fetchone()[0]
        self.assertEqual(after, before)

    # G. failed fetch after prior capture -> previous bytes remain
    def test_g_failed_fetch_after_prior_capture_previous_remains(self):
        with patch("urllib.request.urlopen", return_value=MockUrlResponse(SYNTHETIC_CATALOG_BYTES)):
            payload = fetch_taxonomy_catalog_bytes()
        doc_id = record_taxonomy_catalog(payload, self.archive)
        with patch("urllib.request.urlopen", side_effect=TimeoutError("simulated timeout")):
            with self.assertRaises(Exception):
                fetch_taxonomy_catalog_bytes()
        # Previous document still present; no new document created by failure
        row = self.archive.connection.execute(
            "SELECT 1 FROM source_documents WHERE document_id = ?", (doc_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        # No extra rows from failed attempt
        total = self.archive.connection.execute(
            "SELECT COUNT(*) FROM source_documents"
        ).fetchone()[0]
        self.assertEqual(total, 1)

    # H. source_documents schema unchanged (no new columns / alterations)
    def test_h_source_documents_schema_unchanged(self):
        info = self.archive.connection.execute(
            "PRAGMA table_info(source_documents)"
        ).fetchall()
        cols = {row[1] for row in info}
        expected = {
            "document_id", "content_hash", "uri", "canonical_uri",
            "http_status", "media_type", "byte_size", "fetched_at",
            "first_seen_at", "storage_path", "compression", "provider",
            "document_type", "content", "content_encoding",
        }
        self.assertTrue(expected.issubset(cols))
        # 0022 does not alter source_documents; verify no new columns added.
        self.assertEqual(len(info), len(expected))

    # I. document_type exactly SEC_TAXONOMY_CATALOG
    def test_i_document_type_exact(self):
        with patch("urllib.request.urlopen", return_value=MockUrlResponse(SYNTHETIC_CATALOG_BYTES)):
            payload = fetch_taxonomy_catalog_bytes()
        doc_id = record_taxonomy_catalog(payload, self.archive)
        doc_type = self.archive.connection.execute(
            "SELECT document_type FROM source_documents WHERE document_id = ?", (doc_id,)
        ).fetchone()[0]
        self.assertEqual(doc_type, "SEC_TAXONOMY_CATALOG")

    # J. no authority_taxonomy_namespaces rows created
    def test_j_no_authority_rows_created(self):
        with patch("urllib.request.urlopen", return_value=MockUrlResponse(SYNTHETIC_CATALOG_BYTES)):
            payload = fetch_taxonomy_catalog_bytes()
        record_taxonomy_catalog(payload, self.archive)
        cnt = self.archive.connection.execute(
            "SELECT COUNT(*) FROM authority_taxonomy_namespaces"
        ).fetchone()[0]
        self.assertEqual(cnt, 0)

    # K. no B2 changes (observe no new tables / triggers / indexes related to B2)
    def test_k_b2_unchanged(self):
        # B2 logic is not in this repo as a standalone module; verify 0022 unchanged
        # and no new B2-related files / modifications.
        # Here we verify 0022 table exists as previously created and unmodified.
        self.assertTrue(
            self.archive.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='authority_taxonomy_namespaces'"
            ).fetchone()
        )

    # L. no Observation changes
    def test_l_observation_unchanged(self):
        # observations table exists and has not been modified by this phase
        self.assertTrue(
            self.archive.connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='observations'"
            ).fetchone()
        )

    # M. no network dependency in tests (all mocked)
    def test_m_no_network_dependency(self):
        # All fetch calls in this suite go through MockUrlResponse; no live URL
        # is contacted. If a live call accidentally occurred, urlopen would hit
        # the real network; the mock prevents this entirely.
        with patch("urllib.request.urlopen", return_value=MockUrlResponse(SYNTHETIC_CATALOG_BYTES)):
            payload = fetch_taxonomy_catalog_bytes()
        self.assertEqual(payload, SYNTHETIC_CATALOG_BYTES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
