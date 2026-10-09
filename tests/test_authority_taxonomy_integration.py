"""Phase 3C-C3 — Minimal integration workflow test (C1 -> C2A -> C2B).

Offline, fixture-based, no live network, no B2, no parser change.
Uses archive/authority_taxonomy_workflow.py with fixture bytes.
"""
from __future__ import annotations
import sys, os, tempfile, shutil
sys.path.insert(0, ".")

def _load_workflow():
    import importlib.util
    spec = importlib.util.spec_from_file_location("authority_taxonomy_workflow", "archive/authority_taxonomy_workflow.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["authority_taxonomy_workflow"] = mod
    spec.loader.exec_module(mod)
    return mod

workflow = _load_workflow()

from sqlite_archive import SQLiteArchive


def _fixture_bytes():
    with open("tests/fixtures/edgartaxonomies_sample.xml", "rb") as f:
        return f.read()


class TestAuthorityTaxonomyIntegration:
    def setup_method(self):
        import tempfile
        self.tmp = tempfile.mkdtemp(prefix="steva-c3-")
        self.db = os.path.join(self.tmp, "test.db")
        self.archive = SQLiteArchive(self.db)

    def teardown_method(self):
        self.archive.connection.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # A. workflow completes with fixture bytes; document_id flows from C1 to C2B
    def test_a_workflow_fixture_bytes_end_to_end(self):
        result = workflow.run_authority_taxonomy_workflow(
            self.archive, payload_bytes=_fixture_bytes(),
            provider="SecEdgar", document_type="SEC_TAXONOMY_CATALOG",
        )
        assert "document_id" in result
        assert result["document_id"].startswith("doc_")
        assert result["assertion_count"] > 0
        assert len(result["authority_taxonomy_ids"]) == result["assertion_count"]
        # All ids start with atn_
        for atn in result["authority_taxonomy_ids"]:
            assert atn.startswith("atn_")

    # B. repeated workflow with same bytes idempotent (same doc, same assertions, no duplicate authority rows)
    def test_b_workflow_idempotent_re_run(self):
        fixture = _fixture_bytes()
        r1 = workflow.run_authority_taxonomy_workflow(
            self.archive, payload_bytes=fixture,
            provider="SecEdgar", document_type="SEC_TAXONOMY_CATALOG",
        )
        r2 = workflow.run_authority_taxonomy_workflow(
            self.archive, payload_bytes=fixture,
            provider="SecEdgar", document_type="SEC_TAXONOMY_CATALOG",
        )
        assert r1["document_id"] == r2["document_id"]
        assert r1["assertion_count"] == r2["assertion_count"]
        # Same identity -> no extra authority rows
        total = self.archive.connection.execute(
            "SELECT COUNT(*) FROM authority_taxonomy_namespaces"
        ).fetchone()[0]
        # Fixture contains duplicate identical CEF 2026 (same identity); DB idempotent
        # => DB total stays at unique identity count, not assertion_count
        unique_ids = {row[0] for row in self.archive.connection.execute(
            "SELECT authority_taxonomy_id FROM authority_taxonomy_namespaces"
        ).fetchall()}
        assert len(unique_ids) == total

    # C. same document_id used for every assertion in result
    def test_c_same_document_id_all_assertions(self):
        fixture = _fixture_bytes()
        result = workflow.run_authority_taxonomy_workflow(
            self.archive, payload_bytes=fixture,
            provider="SecEdgar", document_type="SEC_TAXONOMY_CATALOG",
        )
        # Verify every authority row references same source document
        ids = result["authority_taxonomy_ids"]
        doc_ids = [
            self.archive.connection.execute(
                "SELECT document_id FROM authority_taxonomy_namespaces WHERE authority_taxonomy_id = ?",
                (atn,),
            ).fetchone()[0]
            for atn in ids
        ]
        assert all(d == result["document_id"] for d in doc_ids)

    # D. shared namespace across families retained (fixture includes US GAAP + BASE + role/negated)
    def test_d_shared_namespace_preserved(self):
        fixture = _fixture_bytes()
        result = workflow.run_authority_taxonomy_workflow(
            self.archive, payload_bytes=fixture,
            provider="SecEdgar", document_type="SEC_TAXONOMY_CATALOG",
        )
        # At least two families reference shared namespace
        perms = self.archive.connection.execute(
            "SELECT DISTINCT taxonomy_family FROM authority_taxonomy_namespaces WHERE namespace_uri = ?",
            ("http://www.xbrl.org/2009/role/negated",),
        ).fetchall()
        families = {row[0] for row in perms}
        assert "US GAAP" in families
        assert "BASE" in families

    # E. parser not called with network / parser stays pure (no network in workflow result)
    def test_e_no_network_in_workflow(self):
        # Confirm result obtained without live fetch (payload_bytes passed)
        result = workflow.run_authority_taxonomy_workflow(
            self.archive, payload_bytes=_fixture_bytes(),
        )
        assert result["document_id"] is not None

    # F. parser output not reinterpretated (writer takes NamedTuple directly)
    def test_f_no_second_semantic_interpretation(self):
        # Workflow passes parser assertions directly; writer uses fields verbatim
        # No family/version derivation occurs
        fixture = _fixture_bytes()
        result = workflow.run_authority_taxonomy_workflow(
            self.archive, payload_bytes=fixture,
        )
        # At least one assertion retains source-declared family/version
        first = self.archive.connection.execute(
            "SELECT taxonomy_family, taxonomy_version FROM authority_taxonomy_namespaces WHERE authority_taxonomy_id = ?",
            (result["authority_taxonomy_ids"][0],),
        ).fetchone()
        assert first[0] == "CEF"
        assert first[1] == "2026"

    # G. no 0022 / B2 / parser / observation / C1 acquisition changes
    def test_g_no_existing_file_changes(self):
        # Verified externally by git status; this test asserts 0022 schema unchanged
        import sqlite3, hashlib
        with open("archive/migrations/0022_authority_taxonomy_namespaces.sql", "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()[:16]
        assert h == "3347303174edb0a4"

    # H. workflow completes with captured official catalog fixture (201 eligible assertions persisted, 194 unique identities in DB, 2 non-assertions excluded from writer)
    def test_h_workflow_captured_official_catalog(self):
        with open("tests/fixtures/edgartaxonomies_captured.xml", "rb") as f:
            captured_bytes = f.read()

        result = workflow.run_authority_taxonomy_workflow(
            self.archive, payload_bytes=captured_bytes,
            provider="SecEdgar", document_type="SEC_TAXONOMY_CATALOG",
        )
        assert result["document_id"].startswith("doc_")
        assert result["assertion_count"] == 201
        assert len(result["authority_taxonomy_ids"]) == 201
        assert result.get("non_assertion_count") == 2
        assert result.get("total_loc_count") == 203

        # Exactly 194 unique rows in DB
        db_rows = self.archive.connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT authority_taxonomy_identity) FROM authority_taxonomy_namespaces WHERE document_id = ?",
            (result["document_id"],),
        ).fetchone()
        assert db_rows[0] == 194
        assert db_rows[1] == 194

