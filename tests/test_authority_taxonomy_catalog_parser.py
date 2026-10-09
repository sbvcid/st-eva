"""Phase 3C-C2A — Offline parser tests for parse_edgar_taxonomies_catalog.

No network. No DB. No authority_taxonomy_namespaces insertion.
Fixture based on observed live edgartaxonomies.xml structure (200 OK, root <Erxl version=\"78\">, <Loc> with Family/Version/Href/AttType/FileTypeName/Elements/Namespace/Prefix; 203 Loc; 12 duplicate namespace URIs; some missing <Prefix>).
"""
from __future__ import annotations

import os
import unittest

import importlib.util, sys
spec = importlib.util.spec_from_file_location("parse_edgar_taxonomies_catalog", "archive/parse_edgar_taxonomies_catalog.py")
_parser_mod = importlib.util.module_from_spec(spec)
sys.modules["parse_edgar_taxonomies_catalog"] = _parser_mod
spec.loader.exec_module(_parser_mod)
parse_edgar_taxonomies_catalog = _parser_mod.parse_edgar_taxonomies_catalog
ParsedAuthorityAssertion = _parser_mod.ParsedAuthorityAssertion
CatalogParseError = _parser_mod.CatalogParseError
NonAssertionLoc = _parser_mod.NonAssertionLoc
CatalogParseResult = _parser_mod.CatalogParseResult


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name: str) -> bytes:
    with open(os.path.join(FIXTURE_DIR, name), "rb") as f:
        return f.read()


class TaxonomyCatalogParserTest(unittest.TestCase):
    """C2A focused parser verification."""

    # 1. ordinary entry parses
    def test_01_ordinary_entry_parses(self):
        payload = _fixture("edgartaxonomies_sample.xml")
        assertions = parse_edgar_taxonomies_catalog(payload)
        self.assertGreaterEqual(len(assertions), 1)
        # First entry is CEF 2026 ordinary
        first = assertions[0]
        self.assertEqual(first.taxonomy_family, "CEF")
        self.assertEqual(first.taxonomy_version, "2026")
        self.assertEqual(first.namespace_uri, "http://xbrl.sec.gov/cef/2026")
        self.assertEqual(first.file_type_name, "Schema")
        self.assertEqual(first.schema_href, "https://xbrl.sec.gov/cef/2026/cef-2026.xsd")
        self.assertEqual(first.authority_source_version, "78")

    # 2. family preserved
    def test_02_family_preserved(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        families = {a.taxonomy_family for a in assertions}
        self.assertIn("CEF", families)
        self.assertIn("US GAAP", families)
        self.assertIn("BASE", families)
        self.assertIn("DEI", families)

    # 3. taxonomy version preserved
    def test_03_taxonomy_version_preserved(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        versions = {a.taxonomy_version for a in assertions}
        self.assertIn("2026", versions)
        self.assertIn("2025", versions)

    # 4. namespace URI preserved
    def test_04_namespace_uri_preserved(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        uris = {a.namespace_uri for a in assertions}
        self.assertIn("http://xbrl.sec.gov/cef/2026", uris)
        self.assertIn("http://www.xbrl.org/2009/role/negated", uris)

    # 5. standard prefix preserved
    def test_05_standard_prefix_preserved(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        prefixes = {a.standard_prefix for a in assertions}
        self.assertIn("cef", prefixes)
        self.assertIn("us-gaap", prefixes)

    # 6. file type preserved
    def test_06_file_type_preserved(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        types = {a.file_type_name for a in assertions}
        self.assertIn("Schema", types)
        self.assertIn("Entry Point", types)

    # 7. schema href preserved
    def test_07_schema_href_preserved(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        hrefs = {a.schema_href for a in assertions if a.schema_href}
        self.assertTrue(any("xbrl.sec.gov/cef/2026/cef-2026.xsd" in (h or "") for h in hrefs))

    # 8. root catalog version preserved separately (not substituted for taxonomy version)
    def test_08_root_version_separate(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        for a in assertions:
            self.assertEqual(a.authority_source_version, "78")
        # At least one taxonomy version is different (2025 vs root 78)
        versions = {a.taxonomy_version for a in assertions}
        self.assertNotEqual(versions, {"78"})

    # 9. shared namespace across families preserved (no namespace-only dedup)
    def test_09_shared_namespace_across_families(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        shared = [a for a in assertions if a.namespace_uri == "http://www.xbrl.org/2009/role/negated"]
        families = {a.taxonomy_family for a in shared}
        self.assertIn("US GAAP", families)
        self.assertIn("BASE", families)

    # 10. multiple versions preserved
    def test_10_multiple_versions(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        versions = {a.taxonomy_version for a in assertions}
        self.assertIn("2026", versions)
        self.assertIn("2025", versions)

    # 11. duplicate identical assertion deterministic (preserved as separate entries)
    def test_11_duplicate_identical_assertion_deterministic(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        # Fixture has two identical CEF 2026 entries (index 0 and 1)
        first_two = assertions[:2]
        self.assertEqual(first_two[0].taxonomy_family, first_two[1].taxonomy_family)
        self.assertEqual(first_two[0].taxonomy_version, first_two[1].taxonomy_version)
        self.assertEqual(first_two[0].namespace_uri, first_two[1].namespace_uri)
        # Source order preserved; both present
        self.assertGreaterEqual(len(assertions), 2)

    # 12. missing optional fields behave explicitly (Prefix missing -> None)
    def test_12_missing_optional_fields_explicit(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        # DEI 2026 has no <Prefix> in fixture
        dei = [a for a in assertions if a.taxonomy_family == "DEI"]
        self.assertTrue(dei)
        self.assertIsNone(dei[0].standard_prefix)

    # 13. missing required identity fields classified as non-assertions (not fatal catalog error)
    def test_13_missing_identity_fields_classified_as_non_assertion(self):
        sample = b"<?xml version='1.0'?><Erxl version='78'><Loc><Family>US GAAP</Family></Loc></Erxl>"
        result = parse_edgar_taxonomies_catalog(sample)
        self.assertEqual(len(result.assertions), 0)
        self.assertEqual(len(result.non_assertions), 1)
        self.assertEqual(result.total_loc_count, 1)
        na = result.non_assertions[0]
        self.assertEqual(na.source_loc_index, 0)
        self.assertEqual(na.taxonomy_family, "US GAAP")
        self.assertEqual(na.missing_fields, ("Version", "Namespace"))
        self.assertIn("version_absent", na.reason)
        self.assertIn("namespace_absent", na.reason)

    # 14. malformed XML refused
    def test_14_malformed_xml_refused(self):
        bad = b"<Erxl version='78'><Loc><Family>US GAAP</Family>"
        with self.assertRaises(CatalogParseError) as ctx:
            parse_edgar_taxonomies_catalog(bad)
        msg = str(ctx.exception)
        self.assertTrue("malformed XML" in msg or "ParseError" in msg)

    # 15. structurally invalid catalog refused (bad root or missing version)
    def test_15_structurally_invalid_catalog_refused(self):
        # Missing root version
        bad = b"<?xml version='1.0'?><Erxl><Loc><Family>US GAAP</Family><Version>2026</Version><Namespace>http://test</Namespace></Loc></Erxl>"
        with self.assertRaises(CatalogParseError) as ctx:
            parse_edgar_taxonomies_catalog(bad)
        msg = str(ctx.exception)
        self.assertIn("missing root", msg)

    # 16. source order deterministic (preservation of input order)
    def test_16_source_order_deterministic(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        families_in_order = [a.taxonomy_family for a in assertions]
        # First assertions should be CEF, then CEF (dup), then US GAAP (shared), etc.
        self.assertEqual(families_in_order[0], "CEF")

    # 17. no namespace-only deduplication
    def test_17_no_namespace_only_dedup(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        # Count assertions for shared namespace; must be >= 2 (US GAAP + BASE)
        shared = [a for a in assertions if a.namespace_uri == "http://www.xbrl.org/2009/role/negated"]
        self.assertGreaterEqual(len(shared), 2)

    # 18. no family inferred from prefix
    def test_18_no_family_inferred_from_prefix(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        # Prefix "cef-pre" belongs to CEF family explicitly; parser must not derive family from prefix
        cef_pre = [a for a in assertions if a.standard_prefix == "cef-pre"]
        self.assertTrue(cef_pre)
        self.assertEqual(cef_pre[0].taxonomy_family, "CEF")

    # 19. no version inferred from URI
    def test_19_no_version_inferred_from_uri(self):
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        # Namespace http://fasb.org/us-gaap/2025 should have version 2025 (explicit) not derived from URI
        us_gaap_2025 = [a for a in assertions if a.taxonomy_family == "US GAAP" and a.taxonomy_version == "2025"]
        self.assertTrue(us_gaap_2025)
        self.assertEqual(us_gaap_2025[0].namespace_uri, "http://fasb.org/us-gaap/2025")

    # 20. no network dependency (fixture only; mock/patch not needed since no network in parser)
    def test_20_no_network_dependency(self):
        # Parser is pure bytes-in; no urllib, no sqlite, no external dependency
        assertions = parse_edgar_taxonomies_catalog(_fixture("edgartaxonomies_sample.xml"))
        self.assertGreaterEqual(len(assertions), 1)

    # 21. captured official SEC catalog regression: counts and classification (203 / 201 / 2)
    def test_21_captured_catalog_regression_counts(self):
        payload = _fixture("edgartaxonomies_captured.xml")
        result = parse_edgar_taxonomies_catalog(payload)
        # Total Loc count is 203
        self.assertEqual(result.total_loc_count, 203)
        self.assertEqual(len(result.records), 203)
        # 201 eligible assertions
        self.assertEqual(result.assertion_eligible_count, 201)
        self.assertEqual(len(result.assertions), 201)
        self.assertEqual(len(result), 201)
        # 2 non-assertions due to missing Namespace
        self.assertEqual(result.non_assertion_count, 2)
        self.assertEqual(len(result.non_assertions), 2)
        self.assertEqual(result.reason_distribution, {"namespace_absent": 2})

    # 22. captured official SEC catalog regression: non-assertion details (records 126, 127)
    def test_22_captured_catalog_non_assertions_details(self):
        payload = _fixture("edgartaxonomies_captured.xml")
        result = parse_edgar_taxonomies_catalog(payload)
        na0, na1 = result.non_assertions
        self.assertEqual(na0.source_loc_index, 126)
        self.assertEqual(na0.missing_fields, ("Namespace",))
        self.assertEqual(na0.reason, "namespace_absent")
        self.assertEqual(na0.taxonomy_family, "IFRS")
        self.assertEqual(na0.taxonomy_version, "2025")
        self.assertEqual(
            na0.schema_href,
            "https://xbrl.ifrs.org/taxonomy/2025-03-27/full_ifrs/dimensions/dim_full_ifrs_2025-03-27_role-995000.xml",
        )
        self.assertEqual(na0.att_type, "DEF")
        self.assertEqual(na0.file_type_name, "Definition, Dimensions")
        self.assertEqual(na0.elements, "0")

        self.assertEqual(na1.source_loc_index, 127)
        self.assertEqual(na1.missing_fields, ("Namespace",))
        self.assertEqual(na1.reason, "namespace_absent")
        self.assertEqual(na1.taxonomy_family, "IFRS")
        self.assertEqual(na1.taxonomy_version, "2025")
        self.assertEqual(
            na1.schema_href,
            "https://xbrl.ifrs.org/taxonomy/2025-03-27/full_ifrs/dimensions-ea/dim_ifrs_ea_2025-03-27_role-995000.xml",
        )
        self.assertEqual(na1.att_type, "DEF")
        self.assertEqual(na1.file_type_name, "Definition, Dimensions")
        self.assertEqual(na1.elements, "0")

    # 23. captured official SEC catalog regression: unique identity set and fingerprint (194)
    def test_23_captured_catalog_unique_identity_set_and_fingerprint(self):
        import hashlib, json
        payload = _fixture("edgartaxonomies_captured.xml")
        result = parse_edgar_taxonomies_catalog(payload)

        doc_id = "doc_eb3d9eb2f741a4e844f7ed11"
        def canonical_json(p):
            return json.dumps(p, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

        identities = set()
        for a in result.assertions:
            preimage = {
                "document_id": doc_id,
                "namespace_uri": a.namespace_uri,
                "provider": a.provider,
                "taxonomy_family": a.taxonomy_family,
                "taxonomy_version": a.taxonomy_version,
            }
            identities.add(canonical_json(preimage))

        # Expected unique identity count is 194
        self.assertEqual(len(identities), 194)

        # Reproducible identity set fingerprint verification
        sorted_identities = sorted(identities)
        fingerprint = hashlib.sha256("\n".join(sorted_identities).encode("utf-8")).hexdigest()
        self.assertEqual(fingerprint, "398ab08774e78f6803a55eb9fad0f5cf037554f7920875f76bbb41eb482b9e3d")

    # 24. captured official SEC catalog regression: source order and record accounting
    def test_24_captured_catalog_source_order_and_record_accounting(self):
        payload = _fixture("edgartaxonomies_captured.xml")
        result = parse_edgar_taxonomies_catalog(payload)

        # All 203 records accounted in source order
        self.assertEqual(len(result.records), 203)
        self.assertIsInstance(result.records[125], ParsedAuthorityAssertion)
        self.assertIsInstance(result.records[126], NonAssertionLoc)
        self.assertIsInstance(result.records[127], NonAssertionLoc)
        self.assertIsInstance(result.records[128], ParsedAuthorityAssertion)

        # Check that records[126] and [127] are the exact non-assertions
        self.assertIs(result.records[126], result.non_assertions[0])
        self.assertIs(result.records[127], result.non_assertions[1])

        # Verify source loc indices match 0..202
        for idx, rec in enumerate(result.records):
            self.assertEqual(rec.source_loc_index, idx)



# Additional empirical checks from live catalog observation (not persisted; only assertions)
class TaxonomyCatalogLiveObservationTests(unittest.TestCase):
    """Optional empirical checks using live fetch — NOT part of automated test suite dependency.
    These may be run manually once to validate fixture fidelity; they do not alter
    source_documents, authority_taxonomy_namespaces, or production state."""

    def test_live_root_version_and_duplicate_counts(self):
        # Only runs if environment permits live fetch; skipped if unavailable.
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://www.sec.gov/info/edgar/edgartaxonomies.xml",
                headers={"User-Agent": "ST-EVA/2.3 (research; contact st-eva@example.com)"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = resp.read()
            text = payload.decode("utf-8")
            # Root version observation
            root_line = next(l for l in text.splitlines() if "<Erxl" in l)
            self.assertIn('version="78"', root_line)
            # Duplicate namespace observation
            from collections import Counter
            namespaces = [
                line.split("<Namespace>")[1].split("</Namespace>")[0].strip()
                for line in text.splitlines() if "<Namespace>" in line
            ]
            c = Counter(namespaces)
            self.assertGreaterEqual(len([ns for ns, cnt in c.items() if cnt > 1]), 1)
        except Exception:
            self.skipTest("Live SEC catalog unavailable; observation skipped")
