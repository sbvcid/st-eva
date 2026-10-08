"""ST-EVA Phase 3C-C4G — B2 Taxonomy Authority Bridge Integration Tests.

Validates the corrected Phase 3C-C4G implementation under the frozen
Amendment 7 / C4I Evidence Sufficiency Matrix contract:
- Claim C3: Company Concept API taxonomy token == catalog Prefix -> NOT PROVEN
- Claim C7: Observation <-> filing occurrence taxonomy equivalence -> NOT PROVEN
- Claim C9: Historical authority validity -> UNAVAILABLE / UNPROVEN
- Claim C10: Exact source document assertion -> UNAVAILABLE for production C4G
- Lexical equality != vocabulary equivalence != semantic taxonomy equivalence
- Direct taxonomy equality bypass (occurrence.taxonomy == observation.taxonomy) is prohibited
- TAXONOMY_REFUSAL_MUST_NOT_SHRINK_EXACT_SOURCE_CANDIDATES
- Diagnostic precedence: ordinary mismatch yields NO_OBSERVATION, not masked by taxonomy
- Isolated test proof: strictly separated into test-only pure decision harness;
  production Ingestor / linker does NOT accept synthetic proofs or authority_context.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import os
import sqlite3
import sys
import unittest
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
    OccurrenceMatch,
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


# ---------------------------------------------------------------------------
# Pure decision harness (test-only, strictly isolated from production Ingestor)
# ---------------------------------------------------------------------------

def evaluate_taxonomy_equivalence_with_explicit_proof(
    occurrence_taxonomy: Optional[str],
    observation_taxonomy: Optional[str],
    provider: Optional[str],
    proof: Dict[str, Any],
) -> Tuple[bool, str]:
    """Test-only pure decision harness for evaluating explicit hypothetical taxonomy proof.

    STRICTLY TEST-ONLY: Never imported by production Ingestor or sec_ingest.
    """
    if not occurrence_taxonomy or not observation_taxonomy or not provider:
        return False, TAXONOMY_UNPROVEN
    if proof.get("provider") and proof.get("provider") != provider:
        return False, TAXONOMY_UNPROVEN

    candidates = proof.get("logical_candidates", [])
    if candidates:
        matching = [
            c for c in candidates
            if c.get("provider") == provider
            and c.get("standard_prefix") == observation_taxonomy
            and c.get("namespace_uri") == occurrence_taxonomy
        ]
        if len(matching) == 1:
            return True, MATCHED
        if len(matching) > 1:
            return False, TAXONOMY_AMBIGUOUS
        return False, TAXONOMY_UNPROVEN

    if proof.get("standard_prefix") == observation_taxonomy and proof.get("namespace_uri") == occurrence_taxonomy:
        return True, MATCHED

    return False, TAXONOMY_UNPROVEN


def pure_decision_match_occurrence(
    occurrence: Dict[str, Any],
    observations: Sequence[Dict[str, Any]],
    proof: Dict[str, Any],
) -> OccurrenceMatch:
    """Test-only pure decision matching helper using explicit hypothetical proof."""
    ordinary_candidates = [
        obs for obs in observations
        if occurrence_matches_observation_ordinary(occurrence, obs)
    ]
    if not ordinary_candidates:
        return OccurrenceMatch(occurrence["document_fact_id"], None, NO_OBSERVATION)
    distinct_obs_ids = {obs["observation_id"] for obs in ordinary_candidates}
    if len(distinct_obs_ids) != 1:
        return OccurrenceMatch(occurrence["document_fact_id"], None, AMBIGUOUS_OBSERVATION)
    matched_obs = ordinary_candidates[0]
    tax_ok, tax_reason = evaluate_taxonomy_equivalence_with_explicit_proof(
        occurrence.get("taxonomy"),
        matched_obs.get("taxonomy"),
        matched_obs.get("provider"),
        proof=proof,
    )
    if tax_ok:
        return OccurrenceMatch(occurrence["document_fact_id"], matched_obs["observation_id"], MATCHED)
    return OccurrenceMatch(occurrence["document_fact_id"], None, tax_reason)


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

        fact_id = overrides.get("source_fact_id") or source_fact_id(
            source_id=SEC_SOURCE, document_ref=ACCESSION, taxonomy="us-gaap",
            concept=values["concept"], period_start=values["period_start"],
            period_end=values["period_end"], context=ACCESSION + ":" + str(values["observation_id"]),
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

    def link(self) -> int:
        self.ingestor._acquire_document_fact_occurrences(self.asset_id, ACCESSION)
        return self.ingestor._acquire_observation_fact_links(self.asset_id, ACCESSION)

    def links(self) -> List[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM observation_filing_document_facts ORDER BY document_fact_id"
        ).fetchall()


class TestC4GAuthorityBridge(C4GBase):
    def test_uri_uri_equality_does_not_prove_taxonomy(self):
        """1. URI/URI string equality does not prove C7 semantic equivalence."""
        tax_uri = "http://fasb.org/us-gaap/2026"
        tax_ok, reason = evaluate_taxonomy_equivalence(
            occurrence_taxonomy=tax_uri,
            observation_taxonomy=tax_uri,
            provider=SEC_SOURCE,
        )
        self.assertFalse(tax_ok)
        self.assertEqual(TAXONOMY_UNPROVEN, reason)

        # Prefix equality also fails
        tax_ok_pfx, reason_pfx = evaluate_taxonomy_equivalence("us-gaap", "us-gaap", SEC_SOURCE)
        self.assertFalse(tax_ok_pfx)
        self.assertEqual(TAXONOMY_UNPROVEN, reason_pfx)

        # Cross prefix/URI equality also fails
        tax_ok_cross, reason_cross = evaluate_taxonomy_equivalence("us-gaap", tax_uri, SEC_SOURCE)
        self.assertFalse(tax_ok_cross)
        self.assertEqual(TAXONOMY_UNPROVEN, reason_cross)

    def test_no_production_isolated_test_proof_parameter(self):
        """2. Production control flow and signatures cannot accept synthetic proof / authority_context."""
        # 1. evaluate_taxonomy_equivalence signature
        sig_eval = inspect.signature(evaluate_taxonomy_equivalence)
        params_eval = list(sig_eval.parameters.keys())
        self.assertEqual(["occurrence_taxonomy", "observation_taxonomy", "provider"], params_eval)
        with self.assertRaises(TypeError):
            evaluate_taxonomy_equivalence("a", "b", "c", authority_context={})  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            evaluate_taxonomy_equivalence("a", "b", "c", isolated_test_proof=True)  # type: ignore[call-arg]

        # 2. match_occurrence signature
        sig_match = inspect.signature(match_occurrence)
        params_match = list(sig_match.parameters.keys())
        self.assertEqual(["occurrence", "observations"], params_match)
        with self.assertRaises(TypeError):
            match_occurrence({}, [], authority_context={})  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            match_occurrence({}, [], isolated_test_proof=True)  # type: ignore[call-arg]

        # 3. Ingestor._acquire_observation_fact_links signature
        sig_link = inspect.signature(Ingestor._acquire_observation_fact_links)
        params_link = list(sig_link.parameters.keys())
        self.assertEqual(["self", "asset_id", "accession"], params_link)
        with self.assertRaises(TypeError):
            self.ingestor._acquire_observation_fact_links(self.asset_id, ACCESSION, authority_context={})  # type: ignore[call-arg]
        with self.assertRaises(TypeError):
            self.ingestor._acquire_observation_fact_links(self.asset_id, ACCESSION, isolated_test_proof=True)  # type: ignore[call-arg]

    def test_candidate_docs_are_fixed_before_taxonomy_adjudication(self):
        """3. Candidate Discovery occurs and fixes candidate_docs before taxonomy evaluation."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.declare_and_capture(FILENAME_EXTRACTED_XML, EXTRACTED_XML, ordinal=7)

        obs_id = self.store_observation(
            observation_id="obs-c4g-fixed-cand",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )

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

        # Pre-taxonomy candidate discovery solely by ordinary predicates
        pre_tax_docs = {
            (occ["asset_id"], occ["accession"], occ["filename"])
            for occ in occurrences
            if occurrence_matches_observation_ordinary(occ, obs_row)
        }
        self.assertEqual(2, len(pre_tax_docs))
        expected_docs = {
            (self.asset_id, ACCESSION, FILENAME_PRIMARY),
            (self.asset_id, ACCESSION, FILENAME_EXTRACTED_XML),
        }
        self.assertEqual(expected_docs, pre_tax_docs)

    def test_taxonomy_refusal_preserves_two_candidates(self):
        """4. Taxonomy refusal must not shrink pre-taxonomy candidate documents (Case A & Case B)."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.declare_and_capture(FILENAME_EXTRACTED_XML, EXTRACTED_XML, ordinal=7)

        self.store_observation(
            observation_id="obs-c4g-two-cand",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )

        # In production, both occurrences suffer taxonomy refusal
        stored = self.link()
        self.assertEqual(0, stored)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))

        # Candidate documents must not shrink to 0 or 1. Exact source reports DOCUMENTS_AMBIGUOUS!
        self.assertTrue(any(DOCUMENTS_AMBIGUOUS in err for err in self.provenance_errors))

    def test_ambiguous_observation_preserves_candidate_provenance(self):
        """5. AMBIGUOUS_OBSERVATION preserves candidate document provenance across all matching observations."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)

        self.store_observation(
            observation_id="obs-c4g-amb-1",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        self.store_observation(
            observation_id="obs-c4g-amb-2",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )

        stored = self.link()
        # No links written for ambiguous observations
        self.assertEqual(0, stored)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))

        # AMBIGUOUS_OBSERVATION provenance error must be recorded
        self.assertTrue(any(AMBIGUOUS_OBSERVATION in err for err in self.provenance_errors))

    def test_ambiguous_observation_cannot_enable_exact_source(self):
        """6. Ambiguous observation cannot enable exact-source assertion or single-source upgrade."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)

        self.store_observation(
            observation_id="obs-c4g-no-up-1",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        self.store_observation(
            observation_id="obs-c4g-no-up-2",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )

        self.link()
        self.assertEqual(0, self.count("observation_filing_documents"))
        exact_errs = [e for e in self.provenance_errors if "exact_source:" in e]
        self.assertTrue(any(AMBIGUOUS_OBSERVATION in e for e in exact_errs))

    def test_taxonomy_refusal_preserves_competing_context(self):
        """7. Taxonomy refusal must not eliminate competing context (Case F)."""
        # LEGACY_INSTANCE contains two contexts: D2012Q3 and D2012Q3_segment
        self.declare_and_capture(FILENAME_EX101, LEGACY_INSTANCE)
        self.store_observation(taxonomy="us-gaap")

        stored = self.link()
        self.assertEqual(0, stored)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))

        # Context ambiguity must be preserved and reported, not masked by taxonomy
        self.assertTrue(any(CONTEXT_AMBIGUOUS in err for err in self.provenance_errors))

    def test_ordinary_mismatch_precedes_taxonomy_diagnosis(self):
        """8. Ordinary mismatch precedes taxonomy adjudication (Stage B before Stage C)."""
        # Period mismatch
        occ_period = _occurrence_row(period_start="2026-03-29", period_end="2026-06-27")
        obs_period = _observation_row(period_start="2026-06-28", period_end="2026-09-26")
        out_p = match_occurrence(occ_period, [obs_period])
        self.assertEqual(NO_OBSERVATION, out_p.reason)

        # Value mismatch
        occ_val = _occurrence_row(resolved_value=100.0)
        obs_val = _observation_row(value_json=json.dumps(200.0))
        out_v = match_occurrence(occ_val, [obs_val])
        self.assertEqual(NO_OBSERVATION, out_v.reason)

        # Unit mismatch
        occ_u = _occurrence_row()
        obs_u = _observation_row(unit=CURRENCY)
        out_u = match_occurrence(occ_u, [obs_u])
        self.assertEqual(NO_OBSERVATION, out_u.reason)

        # Tag mismatch
        occ_tag = _occurrence_row(tag="Revenues")
        obs_tag = _observation_row(concept="us-gaap:NetIncomeLoss")
        out_t = match_occurrence(occ_tag, [obs_tag])
        self.assertEqual(NO_OBSERVATION, out_t.reason)

    def test_provider_mismatch_is_ordinary_mismatch(self):
        """9. Provider mismatch is an ordinary predicate mismatch yielding NO_OBSERVATION."""
        occ = _occurrence_row(provider=SEC_SOURCE)
        obs = _observation_row(provider="OtherProvider")
        outcome = match_occurrence(occ, [obs])
        self.assertEqual(NO_OBSERVATION, outcome.reason)

    def test_accession_mismatch_is_ordinary_mismatch(self):
        """10. Accession mismatch is an ordinary predicate mismatch yielding NO_OBSERVATION."""
        occ = _occurrence_row(accession=ACCESSION)
        obs = _observation_row(accession="0000320193-26-999999")
        outcome = match_occurrence(occ, [obs])
        self.assertEqual(NO_OBSERVATION, outcome.reason)

    def test_current_catalog_does_not_prove_historical_validity(self):
        """11. Current 2026 catalog does not prove 2012 historical validity (C9 UNAVAILABLE)."""
        self.declare_and_capture(FILENAME_EX101, LEGACY_SINGLE)
        self.record_authority(
            standard_prefix="us-gaap",
            taxonomy_family="US GAAP",
            namespace_uri=USGAAP_2026,
            taxonomy_version="2026",
        )
        self.store_observation(taxonomy="us-gaap")
        stored = self.link()
        self.assertEqual(0, stored)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertEqual(0, self.count("observation_filing_documents"))
        self.assertTrue(any(TAXONOMY_UNPROVEN in err for err in self.provenance_errors))

    def test_c7_unproven_blocks_production_fact_link(self):
        """12. C7 UNPROVEN blocks writing observation_filing_document_facts in production."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.store_observation(
            observation_id="obs-c4g-c7-link",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        stored = self.link()
        self.assertEqual(0, stored)
        self.assertEqual(0, self.count("observation_filing_document_facts"))
        self.assertTrue(any(TAXONOMY_UNPROVEN in err for err in self.provenance_errors))

    def test_c7_unproven_blocks_production_exact_source(self):
        """13. C7 UNPROVEN blocks writing observation_filing_documents in production."""
        self.declare_and_capture(FILENAME_PRIMARY, INLINE_PRIMARY, ordinal=1)
        self.store_observation(
            observation_id="obs-c4g-c7-source",
            concept="us-gaap:Revenues", metric="revenue",
            value=39536000000.0, unit=Unit.CURRENCY.value,
            period_start="2026-03-29", period_end="2026-06-27",
            taxonomy="us-gaap",
        )
        stored = self.link()
        self.assertEqual(0, self.count("observation_filing_documents"))
        exact_errs = [e for e in self.provenance_errors if "exact_source:" in e]
        self.assertTrue(any(TAXONOMY_UNPROVEN in e for e in exact_errs))

    def test_repo_wide_architecture_regression_no_production_bypass(self):
        """14. Architecture regression: no production caller or method accepts synthetic proof."""
        forbidden_terms = {"isolated_test_proof", "authority_context"}
        prod_files = [
            os.path.join(_PROJECT_ROOT, "sec_xbrl_facts.py"),
            os.path.join(_PROJECT_ROOT, "sec_ingest.py"),
            os.path.join(_PROJECT_ROOT, "sqlite_archive.py"),
        ]

        for filepath in prod_files:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content, filename=filepath)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    arg_names = {a.arg for a in node.args.args + node.args.kwonlyargs}
                    found = arg_names.intersection(forbidden_terms)
                    self.assertFalse(
                        found,
                        f"Forbidden parameter {found} in {filepath} at {node.name}()",
                    )

    def test_pure_decision_harness_with_explicit_proof(self):
        """15. Future proof testing: pure decision harness tests explicit proof without production bypass."""
        # 1. Single candidate with explicit proof -> link succeeds, exact source succeeds
        occ_1 = _occurrence_row(
            document_fact_id="dfid_1",
            filename=FILENAME_PRIMARY,
            taxonomy=USGAAP_2026,
            context_ref="ctx_single",
        )
        obs = _observation_row(
            observation_id="obs_iso",
            taxonomy="us-gaap",
        )
        proof = {
            "provider": SEC_SOURCE,
            "standard_prefix": "us-gaap",
            "namespace_uri": USGAAP_2026,
        }

        match_1 = pure_decision_match_occurrence(occ_1, [obs], proof=proof)
        self.assertEqual(MATCHED, match_1.reason)
        self.assertEqual("obs_iso", match_1.observation_id)

        doc, reason = exact_source_document(
            linked=[occ_1],
            candidate_docs=[(occ_1["asset_id"], occ_1["accession"], occ_1["filename"])],
            candidate_occurrences=[occ_1],
        )
        self.assertEqual((occ_1["asset_id"], occ_1["accession"], FILENAME_PRIMARY), doc)
        self.assertIsNone(reason)

        # 2. Two candidates with explicit proof -> link succeeds for both, exact source BLOCKED
        occ_2 = _occurrence_row(
            document_fact_id="dfid_2",
            filename=FILENAME_EXTRACTED_XML,
            taxonomy=USGAAP_2026,
            context_ref="ctx_single",
        )
        cand_docs = [
            (occ_1["asset_id"], occ_1["accession"], occ_1["filename"]),
            (occ_2["asset_id"], occ_2["accession"], occ_2["filename"]),
        ]
        doc_2, reason_2 = exact_source_document(
            linked=[occ_1, occ_2],
            candidate_docs=cand_docs,
            candidate_occurrences=[occ_1, occ_2],
        )
        self.assertIsNone(doc_2)
        self.assertEqual(DOCUMENTS_AMBIGUOUS, reason_2)

    def test_provider_isolation_in_pure_decision_harness(self):
        """16. Pure decision harness enforces provider isolation."""
        proof = {
            "provider": "OtherProvider",
            "standard_prefix": "us-gaap",
            "namespace_uri": USGAAP_2026,
        }
        tax_ok, reason = evaluate_taxonomy_equivalence_with_explicit_proof(
            occurrence_taxonomy=USGAAP_2026,
            observation_taxonomy="us-gaap",
            provider=SEC_SOURCE,
            proof=proof,
        )
        self.assertFalse(tax_ok)
        self.assertEqual(TAXONOMY_UNPROVEN, reason)

    def test_multiple_authority_documents_and_versions_preserve_c4f_semantics(self):
        """17. Multiple authority documents corroborate; different families yield TAXONOMY_AMBIGUOUS in decision harness."""
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

        # Multiple families sharing prefix and namespace yield TAXONOMY_AMBIGUOUS in pure decision harness
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
        tax_ok, reason = evaluate_taxonomy_equivalence_with_explicit_proof(
            occurrence_taxonomy=shared_ns,
            observation_taxonomy="amb-pfx",
            provider=SEC_SOURCE,
            proof=res_amb,
        )
        self.assertFalse(tax_ok)
        self.assertEqual(TAXONOMY_AMBIGUOUS, reason)


if __name__ == "__main__":
    unittest.main()
