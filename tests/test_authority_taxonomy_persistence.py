"""Phase 3C-C2B — Minimal persistence writer tests (offline, no B2, no DB creation)."""
from __future__ import annotations
import sqlite3, tempfile, os, sys, importlib.util, hashlib, shutil
import pytest
# Load writer (uses importlib for parser, same convention)
sys.path.insert(0, ".")
# Pre-load parser module so writer import finds it
spec = importlib.util.spec_from_file_location("parse_edgar_taxonomies_catalog", "archive/parse_edgar_taxonomies_catalog.py")
mod = importlib.util.module_from_spec(spec)
sys.modules["parse_edgar_taxonomies_catalog"] = mod
spec.loader.exec_module(mod)

spec2 = importlib.util.spec_from_file_location("record_authority_taxonomy_assertion", "archive/record_authority_taxonomy_assertion.py")
writer_mod = importlib.util.module_from_spec(spec2)
sys.modules["record_authority_taxonomy_assertion"] = writer_mod
spec2.loader.exec_module(writer_mod)

from sqlite_archive import SQLiteArchive

class TestAuthorityTaxonomyPersistence:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp(prefix="steva-c2b-")
        self.db = os.path.join(self.tmp, "test.db")
        self.archive = SQLiteArchive(self.db)
        # Seed source_documents with a dummy authority document
        self.archive.connection.execute(
            "INSERT INTO source_documents (document_id, content_hash, fetched_at, first_seen_at, document_type, provider, uri) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("doc_auth_c2b_1", "hash_c2b_1", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "SEC_TAXONOMY_CATALOG", "SecEdgar", "https://www.sec.gov/info/edgar/edgartaxonomies.xml"),
        )
        self.archive.connection.execute(
            "INSERT INTO source_documents (document_id, content_hash, fetched_at, first_seen_at, document_type, provider, uri) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("doc_auth_c2b_2", "hash_c2b_2", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", "SEC_TAXONOMY_CATALOG", "SecEdgar", "https://www.sec.gov/info/edgar/edgartaxonomies.xml"),
        )
        self.archive.connection.commit()

    def teardown_method(self):
        self.archive.connection.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_assertion(self, family, version, namespace, prefix=None, file_type="Schema", href="https://example.xsd"):
        return mod.ParsedAuthorityAssertion(
            taxonomy_family=family,
            taxonomy_version=version,
            namespace_uri=namespace,
            standard_prefix=prefix,
            file_type_name=file_type,
            schema_href=href,
        )

    # A. first insert success
    def test_a_first_insert(self):
        a = self._make_assertion("US GAAP", "2026", "http://fasb.org/us-gaap/2026", prefix="us-gaap")
        atn_id = writer_mod.record_authority_taxonomy_assertion(self.archive, a, "doc_auth_c2b_1")
        assert atn_id.startswith("atn_")
        row = self.archive.connection.execute("SELECT * FROM authority_taxonomy_namespaces WHERE authority_taxonomy_id = ?", (atn_id,)).fetchone()
        assert row is not None
        assert row["taxonomy_family"] == "US GAAP"

    # B. idempotent same assertion (same document + identity)
    def test_b_idempotent_same_assertion(self):
        a = self._make_assertion("US GAAP", "2026", "http://fasb.org/us-gaap/2026")
        id1 = writer_mod.record_authority_taxonomy_assertion(self.archive, a, "doc_auth_c2b_1")
        id2 = writer_mod.record_authority_taxonomy_assertion(self.archive, a, "doc_auth_c2b_1")
        assert id1 == id2
        cnt = self.archive.connection.execute("SELECT COUNT(*) FROM authority_taxonomy_namespaces WHERE authority_taxonomy_identity = ?",
            (writer_mod._authority_taxonomy_identity(writer_mod._canonical_preimage("doc_auth_c2b_1","http://fasb.org/us-gaap/2026","SecEdgar","US GAAP","2026")),)).fetchone()[0]
        assert cnt == 1

    # C. same namespace / different family -> coexist
    def test_c_shared_namespace_different_family(self):
        a1 = self._make_assertion("US GAAP", "2026", "http://www.xbrl.org/2009/role/negated")
        a2 = self._make_assertion("BASE", "2026", "http://www.xbrl.org/2009/role/negated")
        id1 = writer_mod.record_authority_taxonomy_assertion(self.archive, a1, "doc_auth_c2b_1")
        id2 = writer_mod.record_authority_taxonomy_assertion(self.archive, a2, "doc_auth_c2b_1")
        assert id1 != id2
        # Both present
        cnt = self.archive.connection.execute("SELECT COUNT(*) FROM authority_taxonomy_namespaces WHERE namespace_uri = ?", ("http://www.xbrl.org/2009/role/negated",)).fetchone()[0]
        assert cnt == 2

    # D. same namespace / different version -> coexist
    def test_d_same_namespace_different_version(self):
        a1 = self._make_assertion("US GAAP", "2026", "http://fasb.org/us-gaap/2026")
        a2 = self._make_assertion("US GAAP", "2025", "http://fasb.org/us-gaap/2025")
        id1 = writer_mod.record_authority_taxonomy_assertion(self.archive, a1, "doc_auth_c2b_1")
        id2 = writer_mod.record_authority_taxonomy_assertion(self.archive, a2, "doc_auth_c2b_1")
        assert id1 != id2

    # E. different document_id / same family/version/namespace -> different identity
    def test_e_different_doc_same_assertion(self):
        a = self._make_assertion("IFRS", "2026", "http://ifrs.org/2026")
        id1 = writer_mod.record_authority_taxonomy_assertion(self.archive, a, "doc_auth_c2b_1")
        id2 = writer_mod.record_authority_taxonomy_assertion(self.archive, a, "doc_auth_c2b_2")
        assert id1 != id2
        # Both retained; no first-writer-wins
        assert self.archive.connection.execute("SELECT COUNT(*) FROM authority_taxonomy_namespaces WHERE namespace_uri = ?", ("http://ifrs.org/2026",)).fetchone()[0] == 2

    # F. identity deterministic
    def test_f_identity_deterministic(self):
        a = self._make_assertion("US GAAP", "2026", "http://fasb.org/us-gaap/2026")
        id1 = writer_mod.record_authority_taxonomy_assertion(self.archive, a, "doc_auth_c2b_1", captured_at="2026-01-01T00:00:00Z")
        # Same inputs -> same identity (even with different captured_at, identity does not include captured_at)
        # But since identity includes document_id and identity fields only, identical inputs yield same id
        # Reset DB (new archive) for pure determinism check
        import shutil
        self.archive.connection.close()
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.tmp = tempfile.mkdtemp(prefix="steva-c2b-determ-")
        self.db = os.path.join(self.tmp, "test.db")
        self.archive = SQLiteArchive(self.db)
        self.archive.connection.execute("INSERT INTO source_documents (document_id, content_hash, fetched_at, first_seen_at, document_type, provider, uri) VALUES (?, ?, ?, ?, ?, ?, ?)", ("doc_auth_c2b_1","h","2026-01-01T00:00:00Z","2026-01-01T00:00:00Z","SEC_TAXONOMY_CATALOG","SecEdgar","https://www.sec.gov/info/edgar/edgartaxonomies.xml"))
        self.archive.connection.commit()
        id3 = writer_mod.record_authority_taxonomy_assertion(self.archive, a, "doc_auth_c2b_1", captured_at="2026-06-01T00:00:00Z")
        # Same identity because captured_at excluded; document_id and fields same
        assert id1 == id3

    # G. non-existent document_id -> FK violation propagated (no bypass)
    def test_g_missing_document_id_fk(self):
        a = self._make_assertion("US GAAP", "2026", "http://fasb.org/us-gaap/2026")
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            writer_mod.record_authority_taxonomy_assertion(self.archive, a, "doc_nonexistent")
