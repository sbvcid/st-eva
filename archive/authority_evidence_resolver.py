"""Phase 3C-C4 — Authority Evidence Resolver (read-only query layer).

Determines whether captured 0022 authority_taxonomy_namespaces contains
matching evidence for a given (provider, taxonomy_family, namespace_uri).
No DB writes. No parser invocation. No B2 equivalence evaluation.
No historical claim beyond what captured source_documents prove.
"""
from __future__ import annotations
from typing import Optional, List


def find_authority_evidence(
    archive,
    provider: str,
    taxonomy_family: str,
    namespace_uri: str,
    document_id: Optional[str] = None,
) -> dict:
    """Query 0022 authority_taxonomy_namespaces for evidence matching
    provider + family + namespace URI. Returns explicit evidence status
    without inferring family from prefix, version from URI, or selecting
    a canonical current-state winner.

    If document_id is given, query is restricted to that source document.
    Multiple matching source-backed assertions (same or different
    document_ids) all count as evidence present.
    """
    if document_id is not None:
        rows = archive.connection.execute(
            "SELECT authority_taxonomy_id, document_id, taxonomy_version, standard_prefix "
            "FROM authority_taxonomy_namespaces "
            "WHERE provider = ? AND taxonomy_family = ? AND namespace_uri = ? AND document_id = ?",
            (provider, taxonomy_family, namespace_uri, document_id),
        ).fetchall()
    else:
        rows = archive.connection.execute(
            "SELECT authority_taxonomy_id, document_id, taxonomy_version, standard_prefix "
            "FROM authority_taxonomy_namespaces "
            "WHERE provider = ? AND taxonomy_family = ? AND namespace_uri = ?",
            (provider, taxonomy_family, namespace_uri),
        ).fetchall()

    matching_document_ids = sorted({row["document_id"] for row in rows})
    version_variants = sorted({row["taxonomy_version"] for row in rows if row["taxonomy_version"]})
    # Neutral note if shared namespace appears under multiple families globally
    # (observable from query, not a verdict)
    shared_family_note = None
    if document_id is None:
        family_counts = archive.connection.execute(
            "SELECT taxonomy_family, COUNT(*) as c FROM authority_taxonomy_namespaces "
            "WHERE provider = ? AND namespace_uri = ? GROUP BY taxonomy_family",
            (provider, namespace_uri),
        ).fetchall()
        if len(family_counts) > 1:
            shared_family_note = (
                f"shared namespace across {len(family_counts)} families; "
                f"queried family is '{taxonomy_family}'"
            )

    return {
        "evidence_found": len(rows) > 0,
        "matching_row_count": len(rows),
        "matching_authority_taxonomy_ids": [row["authority_taxonomy_id"] for row in rows],
        "matching_document_ids": matching_document_ids,
        "version_variants": version_variants,
        "shared_namespace_families_observed": len(family_counts) if document_id is None else None,
        "shared_namespace_note": shared_family_note,
        "provider": provider,
        "taxonomy_family": taxonomy_family,
        "namespace_uri": namespace_uri,
    }
