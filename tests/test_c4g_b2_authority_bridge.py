"""ST-EVA Phase 3C-C4G — B2 Taxonomy Authority Bridge Integration Tests.

Validates the corrected Phase 3C-C4G candidate implementation under the frozen
Amendment 7 / C4I Evidence Sufficiency Matrix contract:
- Claim C3: Company Concept API taxonomy token == catalog Prefix -> NOT PROVEN
- Claim C7: Observation <-> filing occurrence taxonomy equivalence -> NOT PROVEN
- Claim C9: Historical authority validity -> UNAVAILABLE / UNPROVEN
- Claim C10: Exact source document assertion -> UNAVAILABLE for production C4G
- Lexical equality != vocabulary equivalence != semantic taxonomy equivalence
- Direct taxonomy equality shortcut (occurrence.taxonomy == observation.taxonomy) is prohibited
- TAXONOMY_REFUSAL_MUST_NOT_SHRINK_EXACT_SOURCE_CANDIDATES
- Diagnostic precedence: ordinary mismatch yields NO_OBSERVATION, not masked by taxonomy
- Isolated test hook: explicit injected proof can be tested in an isolated harness,
  strictly isolated from production.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import unittest
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from archive import StoredDocument
from core_registry import CoreRegistry
from data_contract import Unit
from registry_seed import seed
from sec_ingest import SEC_SOURCE, Ingestor
from sec_xbrl_facts import (
    AMBIGUOUS_OBSERVATION,
    CONTEXT_AMBIGUOUS,
    DOCUMENTS_AMBIGUOUS,
    MATCHED,
    NO_OBSERVATION,
    TAXONOMY_AMBIGUOUS,
    TAXONOMY_UNPROVEN,
    contract_unit_of,
    evaluate_taxonomy_equivalence,
    exact_source_document,
    match_occurrence,
    occurrence_matches_observation,
    occurrence_matches_observation_ordinary,
)
from sqlite_archive import SQLiteArchive
from test_sec_xbrl_fact_extraction import (
    ACCESSION,
    CAPTURED_AT,
    CIK,
    EXTRACTED_XML,
    FILENAME_EX101,
    FILENAME_EXTRACTED_XML,
    FILENAME_PRIMARY,
    INLINE_PRIMARY,
    LEGACY_INSTANCE,
    MANIFEST_DIRECTORY,
)

# Load C4F modules
_parse_spec = importlib.util.spec_from_file_location(
    "parse_edgar_taxonomies_catalog",
    os.path.join(_PROJECT_ROOT, "archive", "parse_edgar_taxonomies_catalog.py"),
)
_parse_mod = importlib.util.module_from_spec(_parse_spec)
sys.modules["parse_edgar_taxonomies_catalog"] = _parse_mod
_parse_spec.loader.exec_module(_parse_mod)
ParsedAuthorityAssertion = _parse_mod.ParsedAuthorityAssertion
parse_edgar_taxonomies_catalog = _parse_mod.parse_edgar_taxonomies_catalog

_writer_spec = importlib.util.spec_from_file_location(
    "record_authority_taxonomy_assertion",
    os.path.join(_PROJECT_ROOT, "archive", "record_authority_taxonomy_assertion.py"),
)
_writer_mod = importlib.util.module_from_spec(_writer_spec)
sys.modules["record_authority_taxonomy_assertion"] = _writer_mod
_writer_spec.loader.exec_module(_writer_mod)
record_authority_taxonomy_assertion = _writer_mod.record_authority_taxonomy_assertion

_resolver_spec = importlib.util.spec_from_file_location(
    "authority_evidence_resolver",
    os.path.join(_PROJECT_ROOT, "archive", "authority_evidence_resolver.py"),
)
_resolver_mod = importlib.util.module_from_spec(_resolver_spec)
sys.modules["authority_evidence_resolver"] = _resolver_mod
_resolver_spec.loader.exec_module(_resolver_mod)
find_authority_assertions_by_prefix = _resolver_mod.find_authority_assertions_by_prefix

ASSET = "AAPL"
USGAAP_2013 = "http://fasb.org/us-gaap/2013"
USGAAP_2025 = "http://fasb.org/us-gaap/2025"
USGAAP_2026 = "http://fasb.org/us-gaap/2026"
PER_SHARE = "per_share"
CURRENCY = "currency"

LEGACY_PERIOD = ("2012-06-24", "2012-09-29")
LEGACY_UNITS = '{"measures":["USD","xbrli:shares"],"divide":1}'

LEGACY_SINGLE = LEGACY_INSTANCE.replace(
    b'  <us-gaap:EarningsPerShareDiluted contextRef="D2012Q3_segment"'
    b' unitRef="u-usd-per-share" decimals="2">1.36'
    b"</us-gaap:EarningsPerShareDiluted>\n", b"")


class _NoFetchProvider:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(
            f"3C-C4G must read the archive only, but {name} was requested")


def _observation_row(**overrides: Any) -> Dict[str, Any]:
    row = {
        "observation_id": "obsarch_c4g_test",
        "asset_id": "asset_test",
        "provider": SEC_SOURCE,
        "accession": ACCESSION,
        "taxonomy": "us-gaap",
        "concept": "us-gaap:EarningsPerShareDiluted",
        "period_start": LEGACY_PERIOD[0],
        "period_end": LEGACY_PERIOD[1],
        "unit": PER_SHARE,
        "value_json": json.dumps(1.36),
        "source_fact_id": "sfid_test",
    }
    row.update(overrides)
    return row


def _occurrence_row(**overrides: Any) -> Dict[str, Any]:
    row = {
        "document_fact_id": "dfid_c4g_test",
        "provider": SEC_SOURCE,
        "taxonomy": USGAAP_2026,
        "tag": "EarningsPerShareDiluted",
        "context_ref": "D2012Q3",
        "unit_ref": "u-usd-per-share",
        "period_kind": "DURATION",
        "period_start": LEGACY_PERIOD[0],
        "period_end": LEGACY_PERIOD[1],
        "resolved_value": 1.36,
        "filename": FILENAME_EX101,
        "asset_id": "asset_test",
        "accession": ACCESSION,
    }
    row.update(overrides)
    if "contract_unit" not in overrides:
        row["contract_unit"] = contract_unit_of(LEGACY_UNITS)
    return row


class C4GBase(unittest.TestCase):
    def setUp(self) -> None:
        self.store = SQLiteArchive(":memory:")
        self.store.record_asset(ASSET, cik=CIK, name="Apple Inc.")
        self.asset_id = self.store.asset_id_for_cik(CIK)
        self.registry = CoreRegistry(self.store.connection)
        seed(self.registry)
        self.ingestor = Ingestor(self.store, _NoFetchProvider(), self.registry)
        self.connection = self.store.connection
        self.connection.execute(
            "INSERT INTO filings (asset_id, accession, first_archived_at)"
            " VALUES (?, ?, '2026-07-31T00:30:28Z')",
            (self.asset_id, ACCESSION))
        self.connection.commit()

    def tearDown(self) -> None:
        self.store.close()

    @property
    def provenance_errors(self) -> List[str]:
        return list(self.ingestor._provenance_errors)

    def count(self, table: str, where: str = "", *args: Any) -> int:
        clause = f" WHERE {where}" if where else ""
        return self.connection.execute(
            f"SELECT COUNT(*) AS n FROM {table}{clause}", args
        ).fetchone()["n"]

    def declare_and_capture(self, filename: str, payload: bytes, ordinal: int = 1) -> str:
        import hashlib
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_declarations"
            " (declaration_id, asset_id, accession, manifest_source,"
            " source_ordinal, filename, mime_type, byte_size, captured_at,"
            " capture_kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " 'FIRST_HAND')",
            (f"fdd-c4g-{ordinal}-{filename}", self.asset_id, ACCESSION,
             MANIFEST_DIRECTORY, ordinal, filename, "text/html",
             len(payload), CAPTURED_AT))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_documents (asset_id, accession,"
            " filename, first_declared_at) VALUES (?, ?, ?, ?)",
            (self.asset_id, ACCESSION, filename, CAPTURED_AT))
        document_id = self.store.record_source_document(StoredDocument(
            content_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
            uri=("https://www.sec.gov/Archives/edgar/data/320193/"
                 f"{ACCESSION.replace('-', '')}/{filename}"),
            canonical_uri=None, http_status=200, media_type="text/html",
            byte_size=len(payload), fetched_at=CAPTURED_AT,
            first_seen_at=CAPTURED_AT, payload=payload,
            provider=SEC_SOURCE, document_type="SEC_FILING_DOCUMENT",
        ))
        self.connection.execute(
            "INSERT OR IGNORE INTO filing_document_captures (asset_id,"
            " accession, filename, document_id, acquisition_class,"
            " captured_at, capture_kind) VALUES (?, ?, ?, ?,"
            " 'SEC_FILING_DOCUMENT', ?, 'FIRST_HAND')",
            (self.asset_id, ACCESSION, filename, document_id, CAPTURED_AT))
        self.connection.commit()
        return document_id

    def seed_authority_document(self, document_id: str = "doc_auth_cat_1") -> str:
        import hashlib
        payload = f"<catalog id='{document_id}'/>".encode("utf-8")
        self.connection.execute(
            "INSERT OR IGNORE INTO source_documents (document_id, content_hash,"
            " fetched_at, first_seen_at, document_type, provider, uri, media_type, byte_size)"
            " VALUES (?, ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z',"
            " 'SEC_TAXONOMY_CATALOG', ?, 'https://www.sec.gov/info/edgar/edgartaxonomies.xml',"
            " 'text/xml', ?)",
            (document_id, "sha256:" + hashlib.sha256(payload).hexdigest(),
             SEC_SOURCE, len(payload)),
        )
        self.connection.commit()
        return document_id

    def record_authority(
        self,
        standard_prefix: str = "us-gaap",
        taxonomy_family: str = "US GAAP",
        namespace_uri: str = USGAAP_2026,
        taxonomy_version: str = "2026",
        document_id: str = "doc_auth_cat_1",
        provider: str = SEC_SOURCE,
    ) -> str:
        self.seed_authority_document(document_id)
        a = ParsedAuthorityAssertion(
            taxonomy_family=taxonomy_family,
            taxonomy_version=taxonomy_version,
            namespace_uri=namespace_uri,
            standard_prefix=standard_prefix,
            provider=provider,
        )
        return record_authority_taxonomy_assertion(self.store, a, document_id)

    def store_observation(self, taxonomy: str = "us-gaap", **overrides: Any) -> str:
        from archive import FilingRef
        from data_contract import Observation, ValidationStatus
        from evidence_model import source_fact_id

        values = {
            "observation_id": "obs-c4g-eps",
            "value": 1.36,
            "unit": Unit.PER_SHARE.value,
            "concept": "us-gaap:EarningsPerShareDiluted",
            "period_start": LEGACY_PERIOD[0],
            "period_end": LEGACY_PERIOD[1],
            "metric": "eps_diluted",
        }
        values.update(overrides)

        fact_id = source_fact_id(
            source_id=SEC_SOURCE, document_ref=ACCESSION, taxonomy="us-gaap",
            concept=values["concept"], period_start=values["period_start"],
            period_end=values["period_end"], context=ACCESSION,
        )
        filing = FilingRef(
            source_fact_id=fact_id, accession=ACCESSION,
            taxonomy=taxonomy, form="10-K",
            fiscal_year=2012, fiscal_period="Q4",
            statement="FY", instant=0,
            source_concept=values["concept"],
        )
        return self.store.record_observation(
            asset=ASSET,
            observation=Observation(
                observation_id=values["observation_id"],
                metric=values["metric"],
                value=values["value"],
                unit=values["unit"],
                currency="USD",
                currency_basis="REPORTED",
                period_start=values["period_start"],
                period_end=values["period_end"],
                as_of=values["period_end"],
                available_at="2026-07-30T20:30:28Z",
                available_at_basis="ACCEPTANCE_DATETIME",
                provider=SEC_SOURCE,
                source_type="REGULATORY_FILING",
                source_url=None,
                retrieved_at=CAPTURED_AT,
                definition=values["metric"],
                methodology="fixture",
                status=ValidationStatus.UNVERIFIABLE,
                status_reasons=("single official source cannot cross-validate itself",),
                raw={"sec_fact": {"taxonomy": "us-gaap",
                                  "tag": values["concept"].split(":")[-1]}},
            ),
            availability_class="SOURCE_DECLARED",
            accession=ACCESSION,
            filing=filing,
        )

    def link(self, authority_context: Optional[Any] = None) -> int:
        self.ingestor._acquire_document_fact_occurrences(self.asset_id, ACCESSION)
        return self.ingestor._acquire_observation_fact_links(
            self.asset_id, ACCESSION, authority_context=authority_context
        )

    def links(self) -> List[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM observation_filing_document_facts ORDER BY document_fact_id"
        ).fetchall()


class TestC4GAuthorityBridge(C4GBase):
    def test_01_direct_taxonomy_equality_returns_unproven(self):
        """1. Direct taxonomy equality (prefix == prefix) yields TAXONOMY_UNPROVEN."""
        # Evaluating 'us-gaap' == 'us-gaap' without representation proof must not return MATCHED
        tax_ok, reason = evaluate_taxonomy_equivalence(
            occurrence_taxonomy="us-gaap",
            observation_taxonomy="us-gaap",
            provider=SEC_SOURCE,
        )
        self.assertFalse(tax_ok)
        self.assertEqual(TAXONOMY_UNPROVEN, reason)

        # Ingestion with occurrence having prefix string 'us-gaap' must not bypass gate
        payload = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance">
  <xbrli:context id="c"><xbrli:entity><xbrli:identifier scheme="s">1</xbrli:identifier></xbrli:entity>
  <xbrli:period><xbrli:startDate>2026-03-29</xbrli:startDate><xbrli:endDate>2026-06-27</xbrli:endDate></xbrli:period></xbrli:context>
  <xbrli:unit id="u"><xbrli:measure>USD</xbrli:measure></xbrli:unit>
</xbrli:xbrl>"""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.store_observation(
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        # Without injected proof, link must fail with TAXONOMY_UNPROVEN
        stored = self.link()
        self.assertEqual(0, stored)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(TAXONOMY_UNPROVEN in err for err in self.provenance_errors))

    def test_02_two_ordinary_candidates_one_taxonomy_refusal_cardinality_remains_two(self):
        """2. Two ordinary candidates + one taxonomy refusal -> candidate cardinality remains 2."""
        # Primary document asserts diluted EPS with USGAAP_2026
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        # Second document asserts diluted EPS with an unproven/unmapped URI
        unmapped_payload = EXTRACTED_XML.replace(
            b'xmlns:us-gaap="http://fasb.org/us-gaap/2026"',
            b'xmlns:us-gaap="http://example.com/unmapped-gaap"',
        )
        self.declare_and_capture(FILENAME_EXTRACTED_XML, unmapped_payload, ordinal=7)

        obs_id = self.store_observation(
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )

        # Isolated test harness with injected proof for USGAAP_2026 only
        injected_context = {
            "isolated_test_proof": True,
            "provider": SEC_SOURCE,
            "standard_prefix": "us-gaap",
            "namespace_uri": USGAAP_2026,
        }

        stored = self.link(authority_context=injected_context)
        # Primary document linked successfully
        self.assertEqual(1, stored)
        self.assertEqual(1, self.count("observation_filing_document_facts"))
        # TAXONOMY_REFUSAL_MUST_NOT_SHRINK_EXACT_SOURCE_CANDIDATES:
        # Pre-taxonomy candidate docs = {FILENAME_PRIMARY, FILENAME_EXTRACTED_XML} (cardinality 2).
        # Even though Extracted XML suffered TAXONOMY_UNPROVEN, exact source MUST NOT be asserted!
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(DOCUMENTS_AMBIGUOUS in err for err in self.provenance_errors))

    def test_03_two_ordinary_candidates_both_taxonomy_refusal_cardinality_remains_two(self):
        """3. Two ordinary candidate documents + both taxonomy refusal -> cardinality remains 2."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.declare_and_capture(FILENAME_EXTRACTED_XML, EXTRACTED_XML, ordinal=7)
        self.store_observation(
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        # Production case without injected proof: both fail taxonomy
        stored = self.link()
        self.assertEqual(0, stored)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(DOCUMENTS_AMBIGUOUS in err for err in self.provenance_errors))

    def test_04_one_ordinary_candidate_taxonomy_refusal_no_link_no_exact_source(self):
        """4. One ordinary candidate + taxonomy refusal -> no link, no exact-source."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.store_observation(
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        stored = self.link()
        self.assertEqual(0, stored)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(TAXONOMY_UNPROVEN in err for err in self.provenance_errors))

    def test_05_ordinary_mismatch_with_taxonomy_refusal_yields_no_observation(self):
        """5. Ordinary period/value/unit mismatch + taxonomy refusal yields NO_OBSERVATION."""
        # Case A: Period mismatch (Q2 vs Q3)
        occ_period_mismatch = _occurrence_row(period_start="2026-03-29", period_end="2026-06-27")
        obs_period = _observation_row(period_start="2026-06-28", period_end="2026-09-26")
        outcome_a = match_occurrence(occ_period_mismatch, [obs_period])
        self.assertEqual(NO_OBSERVATION, outcome_a.reason)
        self.assertNotEqual(TAXONOMY_UNPROVEN, outcome_a.reason)

        # Case B: Value mismatch (100 vs 200)
        occ_val = _occurrence_row(resolved_value=100.0)
        obs_val = _observation_row(value_json=json.dumps(200.0))
        outcome_b = match_occurrence(occ_val, [obs_val])
        self.assertEqual(NO_OBSERVATION, outcome_b.reason)
        self.assertNotEqual(TAXONOMY_UNPROVEN, outcome_b.reason)

        # Case C: Unit mismatch (per_share vs currency)
        occ_unit = _occurrence_row()
        obs_unit = _observation_row(unit=CURRENCY)
        outcome_c = match_occurrence(occ_unit, [obs_unit])
        self.assertEqual(NO_OBSERVATION, outcome_c.reason)
        self.assertNotEqual(TAXONOMY_UNPROVEN, outcome_c.reason)

        # Case D: Concept local tag mismatch
        occ_tag = _occurrence_row(tag="Revenues")
        obs_tag = _observation_row(concept="us-gaap:NetIncomeLoss")
        outcome_d = match_occurrence(occ_tag, [obs_tag])
        self.assertEqual(NO_OBSERVATION, outcome_d.reason)

    def test_06_provider_isolation(self):
        """6. Provider isolation strictly prevents cross-provider candidate matching."""
        self.record_authority(
            standard_prefix="us-gaap",
            taxonomy_family="US GAAP",
            namespace_uri=USGAAP_2026,
            provider="OtherProvider",
        )
        tax_ok, reason = evaluate_taxonomy_equivalence(
            occurrence_taxonomy=USGAAP_2026,
            observation_taxonomy="us-gaap",
            provider=SEC_SOURCE,
            authority_context=find_authority_assertions_by_prefix(
                self.store, "OtherProvider", "us-gaap"
            ),
        )
        self.assertFalse(tax_ok)
        self.assertEqual(TAXONOMY_UNPROVEN, reason)

    def test_07_multiple_authority_documents_and_versions_preserve_c4f_semantics(self):
        """7. Multiple authority documents and versions corroborate; different families yield TAXONOMY_AMBIGUOUS."""
        self.record_authority(
            standard_prefix="us-gaap", taxonomy_family="US GAAP",
            namespace_uri=USGAAP_2026, taxonomy_version="2025",
            document_id="doc_auth_1",
        )
        self.record_authority(
            standard_prefix="us-gaap", taxonomy_family="US GAAP",
            namespace_uri=USGAAP_2026, taxonomy_version="2026",
            document_id="doc_auth_2",
        )
        res = find_authority_assertions_by_prefix(self.store, SEC_SOURCE, "us-gaap")
        self.assertEqual(2, res["assertion_count"])
        self.assertEqual(1, res["candidate_count"])
        cand = res["logical_candidates"][0]
        self.assertEqual(2, len(cand["supporting_document_ids"]))
        self.assertEqual(["2025", "2026"], cand["taxonomy_versions"])

        # Multiple families sharing prefix and namespace yield TAXONOMY_AMBIGUOUS in isolated harness
        shared_ns = "http://example.com/shared-ns"
        self.record_authority(
            standard_prefix="amb-pfx", taxonomy_family="FAMILY_A",
            namespace_uri=shared_ns, taxonomy_version="2026",
            document_id="doc_auth_a",
        )
        self.record_authority(
            standard_prefix="amb-pfx", taxonomy_family="FAMILY_B",
            namespace_uri=shared_ns, taxonomy_version="2026",
            document_id="doc_auth_b",
        )
        res_amb = find_authority_assertions_by_prefix(self.store, SEC_SOURCE, "amb-pfx")
        self.assertEqual(2, res_amb["candidate_count"])
        res_amb["isolated_test_proof"] = True
        tax_ok, reason = evaluate_taxonomy_equivalence(
            occurrence_taxonomy=shared_ns,
            observation_taxonomy="amb-pfx",
            provider=SEC_SOURCE,
            authority_context=res_amb,
        )
        self.assertFalse(tax_ok)
        self.assertEqual(TAXONOMY_AMBIGUOUS, reason)

    def test_08_historical_filing_vs_current_catalog_unproven(self):
        """8. Historical 2012 filing vs 2026 authority catalog -> historical validity remains unproven."""
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.record_authority(
            standard_prefix="us-gaap",
            taxonomy_family="US GAAP",
            namespace_uri=USGAAP_2026,
            taxonomy_version="2026",
        )
        # 2012 filing cannot be back-validated by 2026 catalog
        self.store_observation(taxonomy="us-gaap")
        stored = self.link()
        self.assertEqual(0, stored)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))

    def test_09_isolated_harness_injected_proof_one_candidate_succeeds(self):
        """9. Isolated harness with explicit injected taxonomy proof + one candidate -> link + exact-source succeed."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        obs_id = self.store_observation(
            observation_id="obs-c4g-iso-1",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        injected_context = {
            "isolated_test_proof": True,
            "provider": SEC_SOURCE,
            "standard_prefix": "us-gaap",
            "namespace_uri": USGAAP_2026,
        }
        stored = self.link(authority_context=injected_context)
        self.assertEqual(1, stored)
        self.assertEqual(1, self.count("observation_filing_document_facts"))
        self.assertEqual(1, self.count("observation_filing_documents"))
        doc_row = self.connection.execute(
            "SELECT filename, accession FROM observation_filing_documents WHERE observation_id = ?",
            (obs_id,),
        ).fetchone()
        self.assertEqual(FILENAME_PRIMARY, doc_row["filename"])
        self.assertEqual(ACCESSION, doc_row["accession"])

    def test_10_isolated_harness_injected_proof_two_candidates_exact_source_blocked(self):
        """10. Isolated harness with explicit injected proof + two candidates -> exact-source remains blocked."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.declare_and_capture(FILENAME_EXTRACTED_XML, EXTRACTED_XML, ordinal=7)
        obs_id = self.store_observation(
            observation_id="obs-c4g-iso-2",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        injected_context = {
            "isolated_test_proof": True,
            "provider": SEC_SOURCE,
            "standard_prefix": "us-gaap",
            "namespace_uri": USGAAP_2026,
        }
        stored = self.link(authority_context=injected_context)
        # Both documents linked
        self.assertEqual(2, stored)
        self.assertEqual(2, self.count("observation_filing_document_facts"))
        # Exact source document remains BLOCKED due to cardinality 2
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(DOCUMENTS_AMBIGUOUS in err for err in self.provenance_errors))

    def test_11_taxonomy_refusal_must_not_shrink_candidate_docs(self):
        """11. Regression: TAXONOMY_REFUSAL_MUST_NOT_SHRINK_EXACT_SOURCE_CANDIDATES.

        Directly verifies that before-taxonomy candidate document cardinality is 2,
        and after-taxonomy refusal of candidate 2, candidate document cardinality
        remains 2 (exact source is blocked).
        """
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        unmapped_payload = EXTRACTED_XML.replace(
            b'xmlns:us-gaap="http://fasb.org/us-gaap/2026"',
            b'xmlns:us-gaap="http://example.com/unmapped-diff"',
        )
        self.declare_and_capture(FILENAME_EXTRACTED_XML, unmapped_payload, ordinal=7)

        obs_id = self.store_observation(
            observation_id="obs-c4g-card-shrink",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )

        # 1. Inspect occurrences directly from database:
        # Both occurrences match all ordinary predicates
        self.ingestor._acquire_document_fact_occurrences(self.asset_id, ACCESSION)
        occurrences = [
            dict(r) for r in self.connection.execute(
                "SELECT * FROM filing_document_fact_occurrences WHERE asset_id = ? AND accession = ?",
                (self.asset_id, ACCESSION),
            ).fetchall()
        ]
        obs_row = dict(self.connection.execute(
            "SELECT * FROM observations WHERE observation_id = ?", (obs_id,)
        ).fetchone())

        for occ in occurrences:
            occ["contract_unit"] = contract_unit_of(occ["unit_measures_json"])

        pre_tax_docs = {
            (occ["asset_id"], occ["accession"], occ["filename"])
            for occ in occurrences
            if occurrence_matches_observation_ordinary(occ, obs_row)
        }
        # Verify: before taxonomy evaluation, exactly 2 candidate documents exist
        self.assertEqual(2, len(pre_tax_docs))

        # 2. Run linking with injected proof for Primary document only:
        injected_context = {
            "isolated_test_proof": True,
            "provider": SEC_SOURCE,
            "standard_prefix": "us-gaap",
            "namespace_uri": USGAAP_2026,
        }
        self.ingestor._acquire_observation_fact_links(
            self.asset_id, ACCESSION, authority_context=injected_context
        )

        # 3. Verify: candidate document cardinality remained 2 and was not shrunk to 1!
        self.assertEqual(1, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(DOCUMENTS_AMBIGUOUS in err for err in self.provenance_errors))

    def test_12_production_invariant_c7_not_proven_blocks_links_and_exact_source(self):
        """12. Production invariant: under normal SEC concept route, C7 NOT PROVEN blocks links and exact source."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.store_observation(
            observation_id="obs-c4g-prod-inv",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        # Production execution (no authority_context passed)
        stored = self.link()
        self.assertEqual(0, stored)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(TAXONOMY_UNPROVEN in err for err in self.provenance_errors))


if __name__ == "__main__":
    unittest.main()
