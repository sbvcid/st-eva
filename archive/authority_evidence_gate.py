"""Phase 3C-C4 — B2 Taxonomy Equivalence Gate (read-only query).

Determines whether sufficient authority + filing-use + existing B2 exact-match
+ filing document cardinality == 1 conditions exist to support taxonomy
equivalence assertion. Does not activate B2; does not modify existing identity,
observations, or 0022. Returns explicit status with missing conditions noted.
"""
from __future__ import annotations
from typing import Optional


def evaluate_taxonomy_equivalence_gate(
    archive,
    provider: str,
    taxonomy_family: str,
    namespace_uri: str,
    filing_document_id: Optional[str] = None,
    existing_b2_exact_match: Optional[bool] = None,
    filing_cardinality_ok: Optional[bool] = None,
    filing_asset_id: Optional[str] = None,
    filing_accession: Optional[str] = None,
    filing_filename: Optional[str] = None,
) -> dict:
    """Evaluate whether taxonomy equivalence can be proven under frozen B2 rules.

    Conditions (all must be true for possible):
      1. authority_evidence_found (0022 row with provider/family/namespace)
      2. filing_use_evidence_found (0021 filing_document_fact_occurrences.taxonomy == namespace_uri for filing_document)
      3. existing_b2_exact_match is True (external B2 evaluation — not fabricated)
      4. filing_cardinality_ok is True (cardinality == 1 per filing_document_captures / filing_document identity)

    No inference: family/version/namespace come from evidence, not derived.
    No version selection: all version variants preserved, none preferred.
    No historical inference: current catalog evidence only.
    """
    # 1. Authority evidence (strict identity fields; no inference, no document equality with filing)
    # Authority document_id (source document) is not required to match filing_document_id.
    auth_rows = archive.connection.execute(
        "SELECT authority_taxonomy_id, document_id, taxonomy_version FROM authority_taxonomy_namespaces "
        "WHERE provider = ? AND taxonomy_family = ? AND namespace_uri = ?",
        (provider, taxonomy_family, namespace_uri),
    ).fetchall()

    authority_evidence_found = len(auth_rows) > 0
    matching_atn_ids = [row[0] for row in auth_rows]
    matching_doc_ids = sorted({row[1] for row in auth_rows if row[1]})
    version_variants = sorted({row[2] for row in auth_rows if row[2]})

    # 2. Filing-use evidence (exact namespace URI from filing fact occurrence)
    filing_use_evidence_found = False
    if filing_document_id is not None:
        filing_use_rows = archive.connection.execute(
            "SELECT 1 FROM filing_document_fact_occurrences WHERE document_id = ? AND taxonomy = ? LIMIT 1",
            (filing_document_id, namespace_uri),
        ).fetchall()
        filing_use_evidence_found = len(filing_use_rows) > 0

    # 3. Cardinality == 1 (existing B2 invariant; minimal check from filing_document_captures)
    cardinality_ok = filing_cardinality_ok
    if cardinality_ok is None and filing_document_id is not None:
        try:
            # Candidate identity = (asset_id, accession, filename) for the filing document
            # We check that exactly one capture/filing identity links to this document.
            # If filing_document_captures table exists, count distinct candidate identity.
            caps = archive.connection.execute(
                "SELECT DISTINCT asset_id, accession, filename FROM filing_document_captures WHERE document_id = ?",
                (filing_document_id,),
            ).fetchall()
            cardinality_ok = len(caps) == 1
        except Exception:
            # If table missing or query fails, leave unknown (do not fabricate True)
            cardinality_ok = None

    # 4. Combine — do not invent B2 logic; report missing conditions explicitly
    conditions_met = {
        "authority_evidence_found": authority_evidence_found,
        "filing_use_evidence_found": filing_use_evidence_found,
        "existing_b2_exact_match": existing_b2_exact_match,
        "filing_cardinality_1": cardinality_ok,
    }
    # Only when all four explicitly true; if any is None/False -> not possible
    taxonomy_equivalence_possible = (
        authority_evidence_found
        and filing_use_evidence_found
        and existing_b2_exact_match is True
        and cardinality_ok is True
    )

    return {
        "taxonomy_equivalence_possible": taxonomy_equivalence_possible,
        "authority_evidence_found": authority_evidence_found,
        "filing_use_evidence_found": filing_use_evidence_found,
        "existing_b2_exact_match": existing_b2_exact_match,
        "filing_cardinality_1": cardinality_ok,
        "conditions_met": conditions_met,
        "matching_authority_taxonomy_ids": matching_atn_ids,
        "matching_document_ids": matching_doc_ids,
        "version_variants": version_variants,
        "note": (
            None if taxonomy_equivalence_possible else
            ("TAXONOMY_UNPROVEN: missing " + ", ".join(
                k for k, v in conditions_met.items() if v is not True
            ))
        ),
    }
