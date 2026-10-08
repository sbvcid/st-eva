"""Phase 3C-C4 — B2 Taxonomy Equivalence Gate (deterministic gate tests).

Read-only. No migration, no 0022 change, no B2 activation, no Observation
identity change. Confirms only the four frozen conditions activate equivalence;
otherwise TAXONOMY_UNPROVEN.
"""
from __future__ import annotations
import sqlite3, tempfile, os, sys, importlib.util

spec_g = importlib.util.spec_from_file_location(
    "authority_evidence_gate", "archive/authority_evidence_gate.py"
)
mod_g = importlib.util.module_from_spec(spec_g)
sys.modules["authority_evidence_gate"] = mod_g
spec_g.loader.exec_module(mod_g)
evaluate_gate = mod_g.evaluate_taxonomy_equivalence_gate


class DummyArchive:
    def __init__(self, db_path: str):
        self.connection = sqlite3.connect(db_path)


def _archive():
    tmp = tempfile.mkdtemp(prefix="c4c-")
    db = os.path.join(tmp, "t.db")
    store = DummyArchive(db)
    store.connection.execute(
        "CREATE TABLE IF NOT EXISTS source_documents ("
        "document_id TEXT PRIMARY KEY, content_hash TEXT, fetched_at TEXT)"
    )
    store.connection.execute(
        "CREATE TABLE IF NOT EXISTS filing_document_captures ("
        "asset_id TEXT, accession TEXT, filename TEXT, document_id TEXT)"
    )
    store.connection.execute(
        "CREATE TABLE IF NOT EXISTS filing_document_fact_occurrences ("
        "document_fact_id TEXT PRIMARY KEY, document_id TEXT, provider TEXT,"
        "asset_id TEXT, accession TEXT, filename TEXT, taxonomy TEXT)"
    )
    store.connection.execute(
        "CREATE TABLE IF NOT EXISTS authority_taxonomy_namespaces ("
        "authority_taxonomy_id TEXT PRIMARY KEY, authority_taxonomy_identity TEXT,"
        "document_id TEXT NOT NULL, provider TEXT NOT NULL, taxonomy_family TEXT NOT NULL,"
        "taxonomy_version TEXT NOT NULL, namespace_uri TEXT NOT NULL,"
        "standard_prefix TEXT, file_type_name TEXT, schema_href TEXT,"
        "authority_source TEXT, authority_source_class TEXT,"
        "authority_source_version TEXT, captured_at TEXT)"
    )
    store.connection.execute(
        "CREATE INDEX IF NOT EXISTS authority_taxonomy_lookup ON"
        " authority_taxonomy_namespaces(provider, namespace_uri, taxonomy_family)"
    )
    store.connection.commit()
    return store, tmp


def _seed_authority(store, doc_id="auth_doc", family="US GAAP", version="2026", ns="http://fasb.org/us-gaap/2026"):
    store.connection.execute(
        "INSERT OR IGNORE INTO source_documents VALUES (?, ?, ?)",
        (doc_id, "h", "2026-01-01"),
    )
    store.connection.execute(
        "INSERT OR IGNORE INTO authority_taxonomy_namespaces VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("atn_" + doc_id, "id_" + doc_id, doc_id, "SecEdgar", family, version, ns,
         "us-gaap", None, None, "SOURCE", "MACHINE_READABLE_CATALOG", None, "2026-01-01"),
    )
    store.connection.commit()


def _seed_filing_use(store, doc_id="fil_doc", ns="http://fasb.org/us-gaap/2026"):
    store.connection.execute(
        "INSERT OR IGNORE INTO filing_document_fact_occurrences VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("dfid_" + doc_id, doc_id, "SecEdgar", "asset_1", "acc_1", "file.htm", ns),
    )
    store.connection.commit()


def _seed_capture(store, doc_id="fil_doc", asset="asset_1", accession="acc_1", filename="file.htm"):
    store.connection.execute(
        "INSERT OR IGNORE INTO filing_document_captures VALUES (?, ?, ?, ?)",
        (asset, accession, filename, doc_id),
    )
    store.connection.commit()


class TestC4CTaxonomyEquivalenceGate:
    # 1. authority absent -> TAXONOMY_UNPROVEN
    def test_authority_absent(self):
        store, tmp = _archive()
        try:
            res = evaluate_gate(store, "SecEdgar", "US GAAP", "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc", existing_b2_exact_match=True,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is False
            assert res["authority_evidence_found"] is False
            assert res["note"] is not None and "TAXONOMY_UNPROVEN" in res["note"]
        finally:
            store.connection.close()

    # 2. family mismatch -> TAXONOMY_UNPROVEN
    def test_family_mismatch(self):
        store, tmp = _archive()
        try:
            _seed_authority(store, family="IFRS")
            res = evaluate_gate(store, "SecEdgar", "US GAAP", "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc", existing_b2_exact_match=True,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is False
            assert res["authority_evidence_found"] is False
        finally:
            store.connection.close()

    # 3. namespace mismatch -> TAXONOMY_UNPROVEN
    def test_namespace_mismatch(self):
        store, tmp = _archive()
        try:
            _seed_authority(store, ns="http://bad/ns")
            res = evaluate_gate(store, "SecEdgar", "US GAAP", "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc", existing_b2_exact_match=True,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is False
            assert res["authority_evidence_found"] is False
        finally:
            store.connection.close()

    # 4. all four true -> possible, note None, no historical claim
    def test_all_four_true(self):
        store, tmp = _archive()
        try:
            _seed_authority(store)
            _seed_filing_use(store)
            _seed_capture(store)
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc",
                                existing_b2_exact_match=True,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is True
            assert res["note"] is None
            assert res["authority_evidence_found"] is True
            assert res["filing_use_evidence_found"] is True
            assert res["existing_b2_exact_match"] is True
            assert res["filing_cardinality_1"] is True
            assert res["matching_document_ids"] == ["auth_doc"]
        finally:
            store.connection.close()

    # 5. cardinality 0 (no captures, query-based)
    def test_cardinality_0(self):
        store, tmp = _archive()
        try:
            _seed_authority(store)
            _seed_filing_use(store)
            # no capture row for fil_doc
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc",
                                existing_b2_exact_match=True,
                                filing_cardinality_ok=None)
            assert res["taxonomy_equivalence_possible"] is False
            assert res["filing_cardinality_1"] is False
            assert res["note"] is not None and "filing_cardinality_1" in res["note"]
        finally:
            store.connection.close()

    # 6. cardinality 2 (two distinct captures) -> fails
    def test_cardinality_2(self):
        store, tmp = _archive()
        try:
            _seed_authority(store)
            _seed_filing_use(store)
            _seed_capture(store, asset="asset_a", accession="acc_a", filename="a.htm")
            _seed_capture(store, asset="asset_b", accession="acc_b", filename="b.htm")
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc",
                                existing_b2_exact_match=True,
                                filing_cardinality_ok=None)
            assert res["taxonomy_equivalence_possible"] is False
            assert res["filing_cardinality_1"] is False
        finally:
            store.connection.close()

    # 7. B2 exact mismatch -> TAXONOMY_UNPROVEN
    def test_b2_exact_mismatch(self):
        store, tmp = _archive()
        try:
            _seed_authority(store)
            _seed_filing_use(store)
            _seed_capture(store)
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc",
                                existing_b2_exact_match=False,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is False
            assert res["existing_b2_exact_match"] is False
            assert res["note"] is not None and "existing_b2_exact_match" in res["note"]
        finally:
            store.connection.close()

    # 8. multiple authority docs (same mapping, different document_id)
    def test_multiple_authority_docs(self):
        store, tmp = _archive()
        try:
            _seed_authority(store, doc_id="auth_1")
            _seed_authority(store, doc_id="auth_2")
            _seed_filing_use(store, doc_id="fil_doc")
            _seed_capture(store, doc_id="fil_doc")
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc",
                                existing_b2_exact_match=True,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is True
            assert len(res["matching_document_ids"]) == 2
            assert sorted(res["matching_document_ids"]) == ["auth_1", "auth_2"]
        finally:
            store.connection.close()

    # 9. multiple taxonomy versions preserved; no preference
    def test_multiple_taxonomy_versions(self):
        store, tmp = _archive()
        try:
            _seed_authority(store, doc_id="auth_2025", version="2025")
            _seed_authority(store, doc_id="auth_2026", version="2026")
            _seed_filing_use(store)
            _seed_capture(store)
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc",
                                existing_b2_exact_match=True,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is True
            assert "2025" in res["version_variants"]
            assert "2026" in res["version_variants"]
            assert len(res["version_variants"]) == 2
        finally:
            store.connection.close()

    # 10. authority document_id != filing document_id -> permitted; no equality enforced
    def test_authority_doc_neq_filing_doc(self):
        store, tmp = _archive()
        try:
            _seed_authority(store, doc_id="auth_source")
            _seed_filing_use(store, doc_id="fil_filing")
            _seed_capture(store, doc_id="fil_filing")
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_filing",
                                existing_b2_exact_match=True,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is True
            assert res["matching_document_ids"] == ["auth_source"]
        finally:
            store.connection.close()

    # 11. current catalog must not be interpreted as historical proof
    def test_current_catalog_not_historical(self):
        store, tmp = _archive()
        try:
            _seed_authority(store, version="2026")
            _seed_filing_use(store)
            _seed_capture(store)
            # Without B2 exact match provided, equivalence stays unproven
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc",
                                existing_b2_exact_match=None,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is False
            assert res["existing_b2_exact_match"] is None
            assert res["note"] is not None and "existing_b2_exact_match" in res["note"]
            # Only current versions reported; no historical inference
            assert "2026" in res["version_variants"]
        finally:
            store.connection.close()

    # 12. existing B2 negative cases unchanged (family / namespace / authority absent)
    def test_existing_negative_cases_unchanged(self):
        store, tmp = _archive()
        try:
            # family mismatch with all else correct -> still False
            _seed_authority(store, family="IFRS")
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                existing_b2_exact_match=True,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is False

            # namespace mismatch -> still False
            _seed_authority(store, doc_id="auth_bad_ns", family="US GAAP",
                            ns="http://bad/ns")
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc",
                                existing_b2_exact_match=True,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is False

            # authority absent entirely -> still False
            res = evaluate_gate(store, "SecEdgar", "US GAAP",
                                "http://fasb.org/us-gaap/2026",
                                filing_document_id="fil_doc",
                                existing_b2_exact_match=True,
                                filing_cardinality_ok=True)
            assert res["taxonomy_equivalence_possible"] is False
        finally:
            store.connection.close()
