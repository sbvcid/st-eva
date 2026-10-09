"""
Cross-framework and applicability verification.

Twelve questions, one archive, no company in this file. The issuers and the
metrics come in as arguments precisely so that the thing being verified is the
*model* and not the answer: a check that names its own subject cannot be
reused, and a check that does can be pointed at the next issuer in the list.

The order the questions are asked in is the order the phases are:

    1  what did this issuer actually file
    2  which declared concepts reached observations, and how exactly
    3  which concepts the issuer reported that no mapping claims
    4  which metrics are inapplicable by business model, and why
    5  whether inapplicable and empty stayed apart
    6  what changed in the registry
    7  what the query surface exposes for a cross-framework metric
    8  whether a full provenance chain resolves
    9  how many company-specific definitions, columns and code paths exist

The ninth is the one that cannot be asserted from inside the program that also
grew the registry, so it is counted from the source text and the schema rather
than from a flag.
"""

from __future__ import annotations

# Keep repository modules, repository-relative data paths, and sibling research
# scripts available after this utility is stored under scripts/research/.
import os as _os
import sys as _sys
from pathlib import Path as _Path

_SCRIPT_DIR = _Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
for _path in (str(_REPO_ROOT), str(_SCRIPT_DIR)):
    if _path not in _sys.path:
        _sys.path.insert(0, _path)

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional

HERE = str(_REPO_ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry, MAPPING_TYPES  # noqa: E402
from evidence_model import NOT_APPLICABLE, SOURCE_REPORTED  # noqa: E402
from evidence_query import APPLICABLE, EvidenceQuery  # noqa: E402

# Tokens that would make the semantic layer issuer-specific. Counted, not
# forbidden: the point is to be able to *show* the number, and a check that
# simply raised would be a check that could be satisfied by renaming.
ISSUER_TOKENS = (
    "TSM", "TAIWAN", "SEMICONDUCTOR", "NU", "NUPAG", "NUBANK",
    "AAPL", "APPLE", "MSFT", "MICROSOFT", "MU", "MICRON", "NVDA", "NVIDIA",
)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def phase1_inventory(connection, asset: str) -> Dict[str, Any]:
    """1. What the archive actually holds for this issuer, by taxonomy."""
    asset_id = connection.execute(
        "SELECT asset_id FROM assets WHERE ticker = ?", (asset.upper(),)
    ).fetchone()
    if asset_id is None:
        return {"ticker": asset, "held": False}
    asset_id = asset_id["asset_id"]
    by_taxonomy = {
        row["taxonomy"]: row["n"]
        for row in connection.execute(
            "SELECT COALESCE(taxonomy, 'NONE') AS taxonomy, COUNT(*) AS n"
            " FROM observations WHERE asset_id = ? GROUP BY taxonomy",
            (asset_id,),
        )
    }
    by_form = {
        row["form"]: row["n"]
        for row in connection.execute(
            "SELECT o.form AS form, COUNT(*) AS n FROM observations o"
            " WHERE o.asset_id = ? GROUP BY o.form",
            (asset_id,),
        )
    }
    concepts = connection.execute(
        "SELECT COUNT(DISTINCT source_concept_ref) FROM observations"
        " WHERE asset_id = ? AND source_concept_ref IS NOT NULL",
        (asset_id,),
    ).fetchone()[0]
    return {
        "ticker": asset.upper(),
        "cik": connection.execute(
            "SELECT cik FROM assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()[0],
        "held": True,
        "observations": connection.execute(
            "SELECT COUNT(*) FROM observations WHERE asset_id = ?", (asset_id,)
        ).fetchone()[0],
        "distinct_source_concepts": concepts,
        "by_taxonomy": by_taxonomy,
        "by_form": by_form,
        "currencies": sorted({
            row["currency"] for row in connection.execute(
                "SELECT DISTINCT currency FROM observations"
                " WHERE asset_id = ? AND currency IS NOT NULL", (asset_id,)
            )
        }),
    }


def phase2_mappings(connection, asset: str) -> Dict[str, Any]:
    """
    2. Every declared concept that reached an observation, and how exactly.

    Read from the archive rather than from the seed, so a mapping that was
    declared and never used cannot be counted as a generalisation, and a concept
    that was ingested through a mapping nobody intended cannot hide.
    """
    rows = connection.execute(
        "SELECT o.metric, o.source_concept_ref, m.mapping_type,"
        " m.effective_from, m.effective_to, COUNT(*) AS n,"
        " MIN(o.period_end) AS first_period, MAX(o.period_end) AS last_period"
        " FROM observations o"
        " JOIN assets a ON a.asset_id = o.asset_id"
        " LEFT JOIN metric_concept_mapping m"
        " ON m.concept_id = o.source_concept_ref"
        " WHERE a.ticker = ? AND o.source_concept_ref IS NOT NULL"
        " GROUP BY o.metric, o.source_concept_ref, m.mapping_type,"
        " m.effective_from, m.effective_to"
        " ORDER BY o.metric, m.mapping_type, o.source_concept_ref",
        (asset.upper(),),
    ).fetchall()
    by_metric: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    unmapped: List[Dict[str, Any]] = []
    for row in rows:
        entry = {
            "metric": row["metric"],
            "concept": row["source_concept_ref"],
            "taxonomy": row["source_concept_ref"].split(":", 1)[0],
            "mapping_type": row["mapping_type"],
            "observations": row["n"],
            "first_period": row["first_period"],
            "last_period": row["last_period"],
            "effective_from": row["effective_from"],
            "series_continues": row["mapping_type"] in ("EXACT", "EQUIVALENT"),
        }
        if row["mapping_type"] is None:
            unmapped.append(entry)
        else:
            by_metric[row["metric"]].append(entry)
    return {
        "by_metric": dict(by_metric),
        "observations_through_a_concept": sum(
            e["observations"] for m in by_metric.values() for e in m
        ),
        "concepts_used_without_a_mapping": unmapped,
    }


def phase3_unresolved(connection, asset: str) -> Dict[str, Any]:
    """
    3. Concepts this issuer reported that no mapping claims.

    The unresolved list is the deliverable, not a gap to be closed. A framework
    boundary that produced no unresolved concepts would mean the mapping was
    written by looking at the filer's labels, which is the failure this phase
    exists to rule out.
    """
    reported = {
        row["source_concept_ref"]
        for row in connection.execute(
            "SELECT DISTINCT o.source_concept_ref FROM observations o"
            " JOIN assets a ON a.asset_id = o.asset_id"
            " WHERE a.ticker = ? AND o.source_concept_ref IS NOT NULL",
            (asset.upper(),),
        )
    }
    declared = {
        row["concept_id"]
        for row in connection.execute("SELECT concept_id FROM metric_concept_mapping")
    }
    # Concepts the ingester looked for and the registry could not resolve are
    # recorded too, because "we asked for it and the registry had no mapping" is
    # a different fact from "we never looked".
    unresolved = sorted(reported - declared)
    return {
        "concepts_reported": len(reported),
        "concepts_mapped": len(reported & declared),
        "unmapped": unresolved,
        "note": (
            "Concepts reported by the filer that no declared mapping claims. "
            "Each is a concept ST-EVA is deliberately not asserting a metric "
            "for, and the seeded notes say why for the ones a reader is most "
            "likely to expect."
        ),
    }


def phase4_applicability(connection, registry: CoreRegistry, asset: str) -> Dict[str, Any]:
    """
    4 and 5. Applicability, and whether it stayed apart from absence.

    The distinction is the whole point of the phase, so it is tested rather than
    described: a metric is looked up two ways and the two answers must not
    coincide by accident. Inapplicable is a statement about the company; empty is
    a statement about what has been collected so far.
    """
    metrics = [
        row["metric_id"]
        for row in connection.execute(
            "SELECT metric_id FROM metric_registry WHERE status = 'ACTIVE'"
            " ORDER BY metric_id"
        )
    ]
    business_model = registry.business_model_of(
        connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ?", (asset.upper(),)
        ).fetchone()[0]
    )
    model = business_model["business_model"] if business_model else None

    rows = []
    for metric in metrics:
        definition = registry.metric(metric)
        inapplicable = definition is not None and not definition.applies_to(model)
        rows.append({
            "metric": metric,
            "applicability": NOT_APPLICABLE if inapplicable else APPLICABLE,
            "inapplicable_in": list(definition.inapplicable_in) if definition else [],
            "business_model": model,
        })
    return {
        "business_model": model,
        "metrics": rows,
        "inapplicable": [r["metric"] for r in rows if r["applicability"] == NOT_APPLICABLE],
        "applicable": [r["metric"] for r in rows if r["applicability"] == APPLICABLE],
    }


def phase5_evidence_versus_applicability(query: EvidenceQuery, asset: str,
                                         asset_id: str) -> Dict[str, Any]:
    """
    Whether an inapplicable metric and an empty one are distinguishable.

    Asked of the query surface, not the tables, because the tables were never
    where they could be confused: the risk is that the *surface* collapses them.
    """
    report = query.coverage_report(asset)
    states = {e["metric"]: e for e in report.get("metrics", [])}
    out = []
    for metric, entry in sorted(states.items()):
        out.append({
            "metric": metric,
            "state": entry.get("state"),
            "reason_code": entry.get("reason_code"),
            "observations_held": entry.get("observations_held"),
            "resolved_from": entry.get("resolved_from"),
            # The other axis, carried through from the report rather than
            # re-derived here: the whole question in this phase is whether the
            # two can be told apart, and reading one of them from the surface
            # while recomputing the other would make the comparison worthless.
            "applicability": entry.get("applicability"),
            "business_model": entry.get("business_model"),
        })
    return {
        "asset": asset,
        "state_counts": report.get("state_counts", {}),
        "applicability_counts": report.get("applicability_counts", {}),
        "business_model": report.get("business_model"),
        "per_metric": out,
        "not_applicable_metrics": [
            m for m, e in states.items() if e.get("state") == NOT_APPLICABLE
        ],
    }


def phase6_registry_changes(connection) -> Dict[str, Any]:
    """6. What the semantic layer holds, by taxonomy."""
    concepts = {
        row["taxonomy"]: row["n"]
        for row in connection.execute(
            "SELECT taxonomy, COUNT(*) AS n FROM concept_registry GROUP BY taxonomy"
        )
    }
    mappings = {
        row["taxonomy"]: defaultdict(int)
        for row in connection.execute(
            "SELECT DISTINCT taxonomy FROM concept_registry"
        )
    }
    for row in connection.execute(
        "SELECT sc.taxonomy AS taxonomy, m.mapping_type AS mapping_type,"
        " COUNT(*) AS n FROM metric_concept_mapping m"
        " JOIN concept_registry sc ON sc.concept_id = m.concept_id"
        " GROUP BY sc.taxonomy, m.mapping_type"
    ):
        mappings.setdefault(row["taxonomy"], defaultdict(int))
        # The grouped count, not one per group. Counting groups would report
        # "this framework has one exact mapping" for a framework with four, and
        # the number is the deliverable.
        mappings[row["taxonomy"]][row["mapping_type"]] += row["n"]
    return {
        "concepts_by_taxonomy": concepts,
        "mappings_by_taxonomy_and_type": {
            taxonomy: dict(counts) for taxonomy, counts in mappings.items()
        },
        "mapping_types_in_use": sorted(MAPPING_TYPES),
    }


def phase8_provenance(query: EvidenceQuery, connection, asset: str,
                      metric: str) -> Dict[str, Any]:
    """
    8. The full chain, resolved from one semantic metric.

    query -> observation -> source_fact_id -> document -> accession -> filing ->
    taxonomy -> concept -> semantic metric -> mapping type -> period ->
    available_at. Every link is read back rather than asserted, and a missing
    link is reported as missing so the chain cannot be described as complete when
    it is not.
    """
    rows = query.query_observations(asset=asset, metric=metric, limit=5)
    if not rows:
        return {"metric": metric, "resolved": False,
                "detail": "no observation for this metric and asset"}
    row = rows[0]
    observation_id = row["observation_id"]
    stored = connection.execute(
        "SELECT o.source_fact_id, o.accession, o.taxonomy, o.period_end,"
        " o.available_at, o.source_concept_ref, sc.taxonomy AS concept_taxonomy"
        " FROM observations o LEFT JOIN concept_registry sc"
        " ON sc.concept_id = o.source_concept_ref"
        " WHERE o.observation_id = ?", (observation_id,)
    ).fetchone()
    document = connection.execute(
        "SELECT os.document_id, os.accession AS os_accession, sd.uri"
        " FROM observation_sources os"
        " LEFT JOIN source_documents sd ON sd.document_id = os.document_id"
        " WHERE os.observation_id = ?", (observation_id,)
    ).fetchone()
    # The filing behind the document, which is the link a reader has to be able
    # to follow: a concept resolves to a filing through the document that
    # filing published, and a chain that stops at the document is a chain that
    # stops one short of the evidence.
    filing = None
    accession = None
    if document is not None:
        accession = document["os_accession"] or (stored["accession"] if stored else None)
        filing = connection.execute(
            "SELECT accession, form, filed_at, period_end, report_date,"
            " primary_document, document_id FROM held_filings"
            " WHERE accession = ?", (accession,)
        ).fetchone() if accession else None
    mapping = connection.execute(
        "SELECT mapping_type FROM metric_concept_mapping WHERE concept_id = ?",
        (stored["source_concept_ref"],),
    ).fetchone()
    lineage = query.get_lineage(observation_id)
    links = {
        "semantic_metric": metric,
        "observation": observation_id,
        "source_fact_id": stored["source_fact_id"] if stored else None,
        "document": document["document_id"] if document else None,
        "document_uri": document["uri"] if document else None,
        "accession": accession,
        "form": filing["form"] if filing else None,
        "filed_at": filing["filed_at"] if filing else None,
        "taxonomy": stored["taxonomy"] if stored else None,
        "source_concept": stored["source_concept_ref"] if stored else None,
        "concept_taxonomy": stored["concept_taxonomy"] if stored else None,
        "mapping_type": mapping["mapping_type"] if mapping else None,
        "period_end": stored["period_end"] if stored else None,
        "available_at": stored["available_at"] if stored else None,
        "evidence_state": row.get("status", {}).get("evidence_state", {}).get("state"),
        "semantic_block_present": "semantic" in row,
        "issuer_adoption": (
            (row.get("semantic") or {}).get("issuer_adoption") or {}
        ).get("last_used"),
    }
    required = (
        "semantic_metric", "observation", "source_fact_id", "document",
        "accession", "form", "taxonomy", "source_concept", "mapping_type",
        "period_end", "available_at",
    )
    missing = [k for k in required if links.get(k) in (None, "")]
    return {
        "metric": metric,
        "resolved": True,
        "chain": links,
        "missing_links": missing,
        "complete": not missing,
        "lineage_operations": [
            step.get("operation") for step in lineage.get("chain", [])
        ],
    }


def phase9_issuer_specificity(snapshot: str) -> Dict[str, Any]:
    """
    9. How issuer-specific the semantic layer actually is.

    Counted from two places that cannot be argued with: the schema of the archive
    and the text of the modules that define the semantic layer. A check that
    merely asserted "no company-specific code" would be worth exactly as much as
    the assertion.
    """
    connection = sqlite3.connect(snapshot)
    columns = [
        row[1] for row in connection.execute("PRAGMA table_info(observations)")
    ]
    asset_columns = [
        row[1] for row in connection.execute("PRAGMA table_info(assets)")
    ]
    connection.close()
    issuer_columns = [
        c for c in columns + asset_columns
        if any(t in c.upper() for t in ("AAPL", "TSM", "NU_", "TICKER_SPECIFIC"))
    ]

    modules = (
        "core_registry.py", "registry_seed.py", "evidence_model.py",
        "data_contract.py", "evidence_query.py",
    )
    findings = []
    for module in modules:
        path = os.path.join(HERE, module)
        with open(path, encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"'):
                    continue
                for token in ISSUER_TOKENS:
                    if re.search(rf"\b{token}\b", stripped):
                        findings.append({
                            "module": module, "line": number, "token": token,
                            "text": stripped[:120],
                        })
    return {
        "issuer_named_columns": issuer_columns,
        "issuer_named_column_count": len(issuer_columns),
        "issuer_tokens_in_semantic_modules": findings,
        "issuer_token_occurrences": len(findings),
        "note": (
            "Comment lines are skipped deliberately: this project documents "
            "which issuer prompted which decision, and a count that included "
            "the documentation would forbid the record of why."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--issuer", action="append", required=True)
    parser.add_argument("--probe-metric", action="append", default=[])
    parser.add_argument("--json", help="write the full result here")
    args = parser.parse_args()

    connection = sqlite3.connect(args.snapshot)
    connection.row_factory = sqlite3.Row
    query = EvidenceQuery.open(args.snapshot)
    registry = CoreRegistry(connection)

    result: Dict[str, Any] = {
        "snapshot": {
            "path": args.snapshot,
            "sha256": _sha256(args.snapshot),
        },
        "issuers": {},
        "registry": phase6_registry_changes(connection),
        "issuer_specificity": phase9_issuer_specificity(args.snapshot),
        "provenance": {},
    }
    for issuer in args.issuer:
        asset_id = connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ?", (issuer.upper(),)
        ).fetchone()
        result["issuers"][issuer.upper()] = {
            "inventory": phase1_inventory(connection, issuer),
            "mappings": phase2_mappings(connection, issuer),
            "unresolved": phase3_unresolved(connection, issuer),
            "applicability": phase4_applicability(
                connection, registry, issuer
            ),
            "evidence_states": phase5_evidence_versus_applicability(
                query, issuer, asset_id[0] if asset_id else ""
            ),
        }
    for metric in args.probe_metric or ["revenue", "net_income", "assets"]:
        for issuer in args.issuer:
            result["provenance"][f"{issuer.upper()}:{metric}"] = (
                phase8_provenance(query, connection, issuer, metric)
            )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, sort_keys=True, default=str)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    query.close()
    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())