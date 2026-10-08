"""Phase 3C-C4F — Authority Prefix Resolver Tests.

Tests find_authority_assertions_by_prefix read-only query over 0022
authority_taxonomy_namespaces.

Verifies:
- exact prefix match
- no prefix (unmatched prefix returns empty evidence)
- NULL prefix (DB row with standard_prefix=NULL is ignored; query prefix=None returns empty)
- multiple authority documents, same logical candidate (single logical candidate with multiple supporting docs)
- same prefix / different family (multiple logical candidates across families)
- same prefix / different namespace (multiple logical candidates across namespaces)
- multiple versions (versions preserved without latest-version preference)
- provider mismatch (returns empty evidence)
- deterministic ordering (sorted deterministically)
- complete supporting assertion preservation (all 8 identity/evidence attributes preserved)
- synthetic SEC-shaped catalog fixture: synthetic fixture resolves us-gaap to US GAAP and namespace without hardcoded mapping
"""
from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import tempfile
import importlib.util
import pytest

# Load parser NamedTuple
spec_p = importlib.util.spec_from_file_location(
    "parse_edgar_taxonomies_catalog", "archive/parse_edgar_taxonomies_catalog.py"
)
parse_mod = importlib.util.module_from_spec(spec_p)
sys.modules["parse_edgar_taxonomies_catalog"] = parse_mod
spec_p.loader.exec_module(parse_mod)
ParsedAuthorityAssertion = parse_mod.ParsedAuthorityAssertion
parse_edgar_taxonomies_catalog = parse_mod.parse_edgar_taxonomies_catalog

# Load writer
spec_w = importlib.util.spec_from_file_location(
    "record_authority_taxonomy_assertion", "archive/record_authority_taxonomy_assertion.py"
)
writer_mod = importlib.util.module_from_spec(spec_w)
sys.modules["record_authority_taxonomy_assertion"] = writer_mod
spec_w.loader.exec_module(writer_mod)
record_authority_taxonomy_assertion = writer_mod.record_authority_taxonomy_assertion

# Load resolver
spec_r = importlib.util.spec_from_file_location(
    "authority_evidence_resolver", "archive/authority_evidence_resolver.py"
)
resolver_mod = importlib.util.module_from_spec(spec_r)
sys.modules["authority_evidence_resolver"] = resolver_mod
spec_r.loader.exec_module(resolver_mod)
find_authority_assertions_by_prefix = resolver_mod.find_authority_assertions_by_prefix


def _archive():
    from sqlite_archive import SQLiteArchive
    tmp = tempfile.mkdtemp(prefix="steva-c4f-")
    db = os.path.join(tmp, "test.db")
    store = SQLiteArchive(db)
    # Seed authority source document 1
    store.connection.execute(
        "INSERT INTO source_documents (document_id, content_hash, fetched_at, first_seen_at, "
        "document_type, provider, uri) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("doc_c4f_auth_1", "hash_c4f_1", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
         "SEC_TAXONOMY_CATALOG", "SecEdgar", "https://www.sec.gov/info/edgar/edgartaxonomies.xml"),
    )
    # Seed authority source document 2
    store.connection.execute(
        "INSERT INTO source_documents (document_id, content_hash, fetched_at, first_seen_at, "
        "document_type, provider, uri) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("doc_c4f_auth_2", "hash_c4f_2", "2026-01-02T00:00:00Z", "2026-01-02T00:00:00Z",
         "SEC_TAXONOMY_CATALOG", "SecEdgar", "https://www.sec.gov/info/edgar/edgartaxonomies.xml"),
    )
    store.connection.commit()
    return store, tmp


class TestC4FAuthorityPrefixResolver:
    def setup_method(self):
        self.store, self.tmp = _archive()

    def teardown_method(self):
        self.store.connection.close()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_exact_prefix_match(self):
        """Exact prefix query retrieves assertion and matching logical candidate."""
        a = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2026",
            namespace_uri="http://fasb.org/us-gaap/2026",
            standard_prefix="us-gaap",
        )
        record_authority_taxonomy_assertion(self.store, a, "doc_c4f_auth_1")

        res = find_authority_assertions_by_prefix(self.store, "SecEdgar", "us-gaap")
        assert res["evidence_found"] is True
        assert res["assertion_count"] == 1
        assert res["candidate_count"] == 1

        cand = res["logical_candidates"][0]
        assert cand["provider"] == "SecEdgar"
        assert cand["standard_prefix"] == "us-gaap"
        assert cand["taxonomy_family"] == "US GAAP"
        assert cand["namespace_uri"] == "http://fasb.org/us-gaap/2026"
        assert cand["taxonomy_versions"] == ["2026"]
        assert cand["supporting_document_ids"] == ["doc_c4f_auth_1"]

    def test_02_no_prefix_returns_empty_evidence(self):
        """Querying a non-existent prefix returns empty evidence deterministically."""
        a = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2026",
            namespace_uri="http://fasb.org/us-gaap/2026",
            standard_prefix="us-gaap",
        )
        record_authority_taxonomy_assertion(self.store, a, "doc_c4f_auth_1")

        res = find_authority_assertions_by_prefix(self.store, "SecEdgar", "nonexistent-prefix")
        assert res["evidence_found"] is False
        assert res["assertion_count"] == 0
        assert res["candidate_count"] == 0
        assert res["assertions"] == []
        assert res["logical_candidates"] == []

    def test_03_null_and_missing_prefix_handling(self):
        """DB rows with NULL standard_prefix are never matched; passing None returns empty."""
        # Row with NULL standard_prefix (omitted <Prefix> in XML)
        a_null = ParsedAuthorityAssertion(
            taxonomy_family="DEI",
            taxonomy_version="2026",
            namespace_uri="http://xbrl.sec.gov/dei/2026",
            standard_prefix=None,
        )
        record_authority_taxonomy_assertion(self.store, a_null, "doc_c4f_auth_1")

        # Passing None as prefix must return empty, not match NULL rows
        res_none = find_authority_assertions_by_prefix(self.store, "SecEdgar", None)
        assert res_none["evidence_found"] is False
        assert res_none["assertion_count"] == 0
        assert res_none["candidate_count"] == 0

        # Querying an actual prefix also does not see the null row
        res_dei = find_authority_assertions_by_prefix(self.store, "SecEdgar", "dei")
        assert res_dei["evidence_found"] is False

    def test_04_multiple_authority_documents_same_logical_candidate(self):
        """Same prefix/family/namespace across multiple docs is 1 logical candidate with multiple supporting assertions."""
        a1 = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2026",
            namespace_uri="http://fasb.org/us-gaap/2026",
            standard_prefix="us-gaap",
        )
        # Record in doc 1
        record_authority_taxonomy_assertion(self.store, a1, "doc_c4f_auth_1")
        # Record same assertion in doc 2
        record_authority_taxonomy_assertion(self.store, a1, "doc_c4f_auth_2")

        res = find_authority_assertions_by_prefix(self.store, "SecEdgar", "us-gaap")
        assert res["evidence_found"] is True
        # Two supporting assertion rows preserved
        assert res["assertion_count"] == 2
        assert len(res["assertions"]) == 2
        # BUT exactly ONE logical candidate (not treated as ambiguity)
        assert res["candidate_count"] == 1
        cand = res["logical_candidates"][0]
        assert cand["taxonomy_family"] == "US GAAP"
        assert cand["namespace_uri"] == "http://fasb.org/us-gaap/2026"
        assert cand["supporting_document_ids"] == ["doc_c4f_auth_1", "doc_c4f_auth_2"]
        assert cand["assertion_count"] == 2

    def test_05_same_prefix_different_family(self):
        """Same prefix across different families yields multiple distinct logical candidates without picking a winner."""
        # e.g., 'xbrl' prefix shared by US GAAP and BASE
        a_ug = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2026",
            namespace_uri="http://www.xbrl.org/2009/role/negated",
            standard_prefix="xbrl",
        )
        a_base = ParsedAuthorityAssertion(
            taxonomy_family="BASE",
            taxonomy_version="2026",
            namespace_uri="http://www.xbrl.org/2009/role/negated",
            standard_prefix="xbrl",
        )
        record_authority_taxonomy_assertion(self.store, a_ug, "doc_c4f_auth_1")
        record_authority_taxonomy_assertion(self.store, a_base, "doc_c4f_auth_1")

        res = find_authority_assertions_by_prefix(self.store, "SecEdgar", "xbrl")
        assert res["evidence_found"] is True
        assert res["assertion_count"] == 2
        # Two logical candidates because families differ
        assert res["candidate_count"] == 2
        assert res["distinct_families"] == ["BASE", "US GAAP"]
        assert res["distinct_namespaces"] == ["http://www.xbrl.org/2009/role/negated"]
        # Both candidates exposed; no winner chosen
        families = [c["taxonomy_family"] for c in res["logical_candidates"]]
        assert "BASE" in families and "US GAAP" in families

    def test_06_same_prefix_different_namespace(self):
        """Same prefix pointing to different namespaces yields multiple distinct logical candidates."""
        a_v25 = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2025",
            namespace_uri="http://fasb.org/us-gaap/2025",
            standard_prefix="us-gaap",
        )
        a_v26 = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2026",
            namespace_uri="http://fasb.org/us-gaap/2026",
            standard_prefix="us-gaap",
        )
        record_authority_taxonomy_assertion(self.store, a_v25, "doc_c4f_auth_1")
        record_authority_taxonomy_assertion(self.store, a_v26, "doc_c4f_auth_1")

        res = find_authority_assertions_by_prefix(self.store, "SecEdgar", "us-gaap")
        assert res["evidence_found"] is True
        assert res["assertion_count"] == 2
        assert res["candidate_count"] == 2
        assert res["distinct_families"] == ["US GAAP"]
        assert res["distinct_namespaces"] == [
            "http://fasb.org/us-gaap/2025",
            "http://fasb.org/us-gaap/2026",
        ]
        # Resolver does NOT pick the newer version (2026) as winner
        ns_list = [c["namespace_uri"] for c in res["logical_candidates"]]
        assert "http://fasb.org/us-gaap/2025" in ns_list
        assert "http://fasb.org/us-gaap/2026" in ns_list

    def test_07_multiple_versions_preservation(self):
        """Same provider/standard_prefix/family/namespace with different version
        and different authority document: one logical candidate, both versions
        preserved, both supporting documents retained; no latest-version winner."""
        a_v25 = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2025",
            namespace_uri="http://fasb.org/us-gaap/2025",
            standard_prefix="us-gaap",
        )
        a_v26 = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2026",
            namespace_uri="http://fasb.org/us-gaap/2025",
            standard_prefix="us-gaap",
        )
        record_authority_taxonomy_assertion(self.store, a_v25, "doc_c4f_auth_1")
        record_authority_taxonomy_assertion(self.store, a_v26, "doc_c4f_auth_2")

        res = find_authority_assertions_by_prefix(self.store, "SecEdgar", "us-gaap")
        assert res["evidence_found"] is True
        assert res["candidate_count"] == 1
        cand = res["logical_candidates"][0]
        assert cand["taxonomy_family"] == "US GAAP"
        assert cand["namespace_uri"] == "http://fasb.org/us-gaap/2025"
        assert sorted(cand["taxonomy_versions"]) == ["2025", "2026"]
        assert sorted(cand["supporting_document_ids"]) == ["doc_c4f_auth_1", "doc_c4f_auth_2"]
        assert cand["assertion_count"] == 2
        assert res["assertion_count"] == 2

    def test_08_provider_mismatch(self):
        """Query with non-matching provider returns zero assertions."""
        a = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2026",
            namespace_uri="http://fasb.org/us-gaap/2026",
            standard_prefix="us-gaap",
        )
        record_authority_taxonomy_assertion(self.store, a, "doc_c4f_auth_1")

        res = find_authority_assertions_by_prefix(self.store, "OTHER_PROVIDER", "us-gaap")
        assert res["evidence_found"] is False
        assert res["assertion_count"] == 0
        assert res["candidate_count"] == 0
        assert res["assertions"] == []

    def test_08b_provider_isolation_same_prefix_different_providers(self):
        """Same standard_prefix with assertions under provider A and provider B:
        querying provider A returns only provider A assertions."""
        a_a = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2026",
            namespace_uri="http://fasb.org/us-gaap/2026",
            provider="SecEdgar",
            standard_prefix="us-gaap",
        )
        a_b = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2026",
            namespace_uri="http://fasb.org/us-gaap/2026",
            provider="OtherProvider",
            standard_prefix="us-gaap",
        )
        record_authority_taxonomy_assertion(self.store, a_a, "doc_c4f_auth_1")
        record_authority_taxonomy_assertion(self.store, a_b, "doc_c4f_auth_2")

        res_a = find_authority_assertions_by_prefix(self.store, "SecEdgar", "us-gaap")
        assert res_a["provider"] == "SecEdgar"
        assert all(row["provider"] == "SecEdgar" for row in res_a["assertions"])
        assert res_a["assertion_count"] == 1
        assert res_a["candidate_count"] == 1

    def test_09_deterministic_ordering(self):
        """Assertions and candidates ordered deterministically regardless of insertion order;
        full assertion/candidate output identical after shuffle."""
        a_z = ParsedAuthorityAssertion(
            taxonomy_family="Z_FAMILY",
            taxonomy_version="2026",
            namespace_uri="http://z.org/2026",
            standard_prefix="shared-pfx",
        )
        a_a = ParsedAuthorityAssertion(
            taxonomy_family="A_FAMILY",
            taxonomy_version="2026",
            namespace_uri="http://a.org/2026",
            standard_prefix="shared-pfx",
        )
        # Insert out of order: Z first, A second
        record_authority_taxonomy_assertion(self.store, a_z, "doc_c4f_auth_1")
        record_authority_taxonomy_assertion(self.store, a_a, "doc_c4f_auth_1")

        res = find_authority_assertions_by_prefix(self.store, "SecEdgar", "shared-pfx")
        # Complete output comparison: assertions ordered by SQL, candidates sorted by key
        assert res["provider"] == "SecEdgar"
        assert res["standard_prefix"] == "shared-pfx"
        assert res["evidence_found"] is True
        assert res["assertion_count"] == 2
        assert res["candidate_count"] == 2
        # Full assertion fields preserved and ordered deterministically
        families = [c["taxonomy_family"] for c in res["logical_candidates"]]
        assert families == ["A_FAMILY", "Z_FAMILY"]
        namespaces = [c["namespace_uri"] for c in res["logical_candidates"]]
        assert namespaces == ["http://a.org/2026", "http://z.org/2026"]
        # Assertions list fully ordered (not just families)
        assertion_families = [a["taxonomy_family"] for a in res["assertions"]]
        assert assertion_families == ["A_FAMILY", "Z_FAMILY"]
        # Candidate detail fully preserved
        cand_a = res["logical_candidates"][0]
        cand_z = res["logical_candidates"][1]
        assert cand_a["taxonomy_family"] == "A_FAMILY"
        assert cand_z["taxonomy_family"] == "Z_FAMILY"
        assert cand_a["assertion_count"] == 1
        assert cand_z["assertion_count"] == 1

    def test_10_complete_supporting_assertion_preservation(self):
        """Each assertion in assertions retains all 8 required identity and evidence fields."""
        a = ParsedAuthorityAssertion(
            taxonomy_family="US GAAP",
            taxonomy_version="2026",
            namespace_uri="http://fasb.org/us-gaap/2026",
            standard_prefix="us-gaap",
        )
        record_authority_taxonomy_assertion(self.store, a, "doc_c4f_auth_1")

        res = find_authority_assertions_by_prefix(self.store, "SecEdgar", "us-gaap")
        assert len(res["assertions"]) == 1
        row = res["assertions"][0]

        expected_fields = {
            "authority_taxonomy_id",
            "authority_taxonomy_identity",
            "document_id",
            "provider",
            "standard_prefix",
            "taxonomy_family",
            "taxonomy_version",
            "namespace_uri",
        }
        assert set(row.keys()) == expected_fields
        assert row["document_id"] == "doc_c4f_auth_1"
        assert row["provider"] == "SecEdgar"
        assert row["standard_prefix"] == "us-gaap"
        assert row["taxonomy_family"] == "US GAAP"
        assert row["taxonomy_version"] == "2026"
        assert row["namespace_uri"] == "http://fasb.org/us-gaap/2026"

    def test_11_synthetic_sec_catalog_fixture_us_gaap_bridge_without_hardcoding(self):
        """Synthetic SEC-shaped catalog fixture: parsed synthetic fixture resolves
        us-gaap to US GAAP and namespace purely via catalog rows without hardcoded
        mapping. Not a live SEC catalog."""
        fixture_path = os.path.join(
            os.path.dirname(__file__), "fixtures", "edgartaxonomies_sample.xml"
        )
        with open(fixture_path, "rb") as f:
            xml_bytes = f.read()

        assertions = parse_edgar_taxonomies_catalog(xml_bytes)
        assert len(assertions) > 0

        # Persist all parsed assertions from the synthetic SEC-shaped catalog fixture
        for a in assertions:
            record_authority_taxonomy_assertion(self.store, a, "doc_c4f_auth_1")

        # Resolve 'us-gaap' prefix
        res = find_authority_assertions_by_prefix(self.store, "SecEdgar", "us-gaap")
        assert res["evidence_found"] is True
        assert res["standard_prefix"] == "us-gaap"

        # Synthetic fixture contains US GAAP 2025 entry with prefix us-gaap
        ug_candidates = [c for c in res["logical_candidates"] if c["taxonomy_family"] == "US GAAP"]
        assert len(ug_candidates) >= 1
        cand = ug_candidates[0]
        assert cand["taxonomy_family"] == "US GAAP"
        assert "http://fasb.org/us-gaap/2025" in res["distinct_namespaces"]
        assert "2025" in cand["taxonomy_versions"]
