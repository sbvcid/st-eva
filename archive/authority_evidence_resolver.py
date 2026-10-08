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


def find_authority_assertions_by_prefix(
    archive,
    provider: str,
    standard_prefix: str,
) -> dict:
    """Query 0022 authority_taxonomy_namespaces for all source-backed assertions
    matching provider + standard_prefix via exact string equality.

    Returns complete supporting assertion rows and logical candidate grouping
    (provider, standard_prefix, taxonomy_family, namespace_uri).
    Zero inference: does not infer family from prefix or namespace, does not
    infer version from URI, does not select a latest-version winner, does not
    collapse distinct logical candidates, and does not hardcode any prefix mapping.
    """
    if not isinstance(provider, str) or not isinstance(standard_prefix, str) or standard_prefix is None:
        return {
            "evidence_found": False,
            "provider": provider,
            "standard_prefix": standard_prefix,
            "assertion_count": 0,
            "assertions": [],
            "logical_candidates": [],
            "candidate_count": 0,
            "distinct_families": [],
            "distinct_namespaces": [],
        }

    cursor = archive.connection.execute(
        "SELECT authority_taxonomy_id, authority_taxonomy_identity, document_id, "
        "provider, standard_prefix, taxonomy_family, taxonomy_version, namespace_uri "
        "FROM authority_taxonomy_namespaces "
        "WHERE provider = ? AND standard_prefix = ? "
        "ORDER BY taxonomy_family, namespace_uri, taxonomy_version, document_id, authority_taxonomy_id",
        (provider, standard_prefix),
    )

    cols = [col[0] for col in cursor.description] if cursor.description else []
    raw_rows = cursor.fetchall()

    assertions: List[dict] = []
    for r in raw_rows:
        if hasattr(r, "keys"):
            row_dict = dict(r)
        else:
            row_dict = {cols[i]: r[i] for i in range(len(cols))}
        assertions.append({
            "authority_taxonomy_id": row_dict["authority_taxonomy_id"],
            "authority_taxonomy_identity": row_dict["authority_taxonomy_identity"],
            "document_id": row_dict["document_id"],
            "provider": row_dict["provider"],
            "standard_prefix": row_dict["standard_prefix"],
            "taxonomy_family": row_dict["taxonomy_family"],
            "taxonomy_version": row_dict["taxonomy_version"],
            "namespace_uri": row_dict["namespace_uri"],
        })

    # Group into logical candidates: (provider, standard_prefix, taxonomy_family, namespace_uri)
    # taxonomy_version is supporting evidence attribute; distinct documents corroborate candidates.
    groups: dict = {}
    for assertion in assertions:
        group_key = (
            assertion["provider"],
            assertion["standard_prefix"],
            assertion["taxonomy_family"],
            assertion["namespace_uri"],
        )
        if group_key not in groups:
            groups[group_key] = {
                "provider": assertion["provider"],
                "standard_prefix": assertion["standard_prefix"],
                "taxonomy_family": assertion["taxonomy_family"],
                "namespace_uri": assertion["namespace_uri"],
                "taxonomy_versions": set(),
                "supporting_document_ids": set(),
                "supporting_authority_taxonomy_ids": [],
                "supporting_assertions": [],
            }
        g = groups[group_key]
        if assertion["taxonomy_version"]:
            g["taxonomy_versions"].add(assertion["taxonomy_version"])
        if assertion["document_id"]:
            g["supporting_document_ids"].add(assertion["document_id"])
        g["supporting_authority_taxonomy_ids"].append(assertion["authority_taxonomy_id"])
        g["supporting_assertions"].append(assertion)

    logical_candidates: List[dict] = []
    for group_key in sorted(groups.keys()):
        g = groups[group_key]
        logical_candidates.append({
            "provider": g["provider"],
            "standard_prefix": g["standard_prefix"],
            "taxonomy_family": g["taxonomy_family"],
            "namespace_uri": g["namespace_uri"],
            "taxonomy_versions": sorted(g["taxonomy_versions"]),
            "supporting_document_ids": sorted(g["supporting_document_ids"]),
            "supporting_authority_taxonomy_ids": g["supporting_authority_taxonomy_ids"],
            "assertion_count": len(g["supporting_assertions"]),
        })

    distinct_families = sorted({c["taxonomy_family"] for c in logical_candidates})
    distinct_namespaces = sorted({c["namespace_uri"] for c in logical_candidates})

    return {
        "evidence_found": len(assertions) > 0,
        "provider": provider,
        "standard_prefix": standard_prefix,
        "assertion_count": len(assertions),
        "assertions": assertions,
        "logical_candidates": logical_candidates,
        "candidate_count": len(logical_candidates),
        "distinct_families": distinct_families,
        "distinct_namespaces": distinct_namespaces,
    }
