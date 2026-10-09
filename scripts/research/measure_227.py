"""
2.27 measurement. Reads the two cohort archives and reports them apart.

The two cohorts answer different questions and are never combined into one
number:

    Cohort A   18 filers, companyfacts already held, submissions newly fetched
               -> does context enrichment change Evidence?
    Cohort B   22 new filers, both streams, full Core scope
               -> what does coverage look like across business models?

The population-level matrix is built from the **full-scope** archives only, and
the 75-issuer population archive is reported beside it rather than merged. That
archive holds eight of the twenty metrics, so its cells are scope gaps, not
source silence, and merging it would put `NOT_YET_COLLECTED` and `SOURCE_SILENT`
in the same column. The denominator was registered in advance as
20 metrics x full-scope filers and is not adjusted afterwards.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(os.path.dirname(SCRIPT_DIR))
for _path in (HERE, SCRIPT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from core_registry import CoreRegistry  # noqa: E402
from coverage_semantics import scoped_ledger  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

COHORT_A = os.path.join(H, "snapshot-227-a1.sqlite")
COHORT_B = os.path.join(H, "snapshot-227-b.sqlite")
# Full-scope archives that predate 2.27 and are not superseded by a cohort.
PRIOR_FULL = {
    "BANK (2.17-2.24)": os.path.join(H, "snapshot-banks2.sqlite"),
    "FINANCE_SERVICES (2.25)": os.path.join(H, "snapshot-fs.sqlite"),
    "MINING + INSURANCE (2.23)": os.path.join(H, "snapshot-ins-min.sqlite"),
}
POPULATION_8_METRIC = os.path.join(H, "snapshot-universe.sqlite")
METRICS = 20


def connect(path):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    return c


def panel(path):
    c = connect(path)
    one = lambda q: (c.execute(q).fetchone() or [0])[0]  # noqa: E731
    out = {
        "archive": os.path.basename(path),
        "issuers": one("SELECT COUNT(*) FROM assets"),
        "filings_held": one("SELECT COUNT(*) FROM held_filings"),
        "distinct_accessions_in_observations":
            one("SELECT COUNT(DISTINCT accession) FROM observations"),
        "documents_stored": one("SELECT COUNT(*) FROM source_documents"),
        "observations": one("SELECT COUNT(*) FROM observations"),
        "distinct_source_fact_id":
            one("SELECT COUNT(DISTINCT source_fact_id) FROM observations"),
        "duplicate_identities": one(
            "SELECT COUNT(*) FROM (SELECT 1 FROM observations"
            " GROUP BY source_fact_id HAVING COUNT(*) > 1)"),
        "missing_accession": one(
            "SELECT COUNT(*) FROM observations"
            " WHERE accession IS NULL OR accession = ''"),
        "missing_document": one(
            "SELECT COUNT(*) FROM observations o WHERE NOT EXISTS"
            " (SELECT 1 FROM observation_sources s"
            "  WHERE s.observation_id = o.observation_id)"),
        "dimension_collision_rows":
            one("SELECT COUNT(*) FROM ingestion_dimension_collisions")
            if _has(c, "ingestion_dimension_collisions") else 0,
    }
    c.close()
    return out


def _has(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def issuer_rows(path):
    """One record per issuer: model, forms, PIT share, collisions, ledger."""
    c = connect(path)
    registry = CoreRegistry(c)
    out = []
    for r in c.execute("SELECT asset_id, ticker FROM assets ORDER BY ticker"):
        asset_id, ticker = str(r["asset_id"]), str(r["ticker"]).upper()
        led = scoped_ledger(c, registry, asset_id, ticker)
        obs = c.execute("SELECT COUNT(*) n FROM observations WHERE asset_id=?",
                        (asset_id,)).fetchone()["n"]
        dated = c.execute(
            "SELECT COUNT(*) n FROM observations WHERE asset_id=?"
            " AND available_at_basis='FILED_AS_OF_DATE'", (asset_id,)).fetchone()["n"]
        forms = sorted({x[0] for x in c.execute(
            "SELECT DISTINCT form FROM held_filings WHERE asset_id=?"
            " AND form IS NOT NULL", (asset_id,))})
        coll = c.execute(
            "SELECT COUNT(*) n, COALESCE(MAX(distinct_values),0) mx"
            " FROM ingestion_dimension_collisions WHERE asset_id=?",
            (asset_id,)).fetchone()
        coll_by_metric = Counter()
        if _has(c, "ingestion_dimension_collisions"):
            for row in c.execute(
                "SELECT metric_id, COUNT(*) n FROM"
                " ingestion_dimension_collisions WHERE asset_id=? GROUP BY 1",
                (asset_id,)
            ):
                coll_by_metric[str(row["metric_id"])] = int(row["n"])
        span = c.execute(
            "SELECT MIN(filed_at), MAX(filed_at) FROM held_filings"
            " WHERE asset_id=?", (asset_id,)).fetchone()
        out.append({
            "ticker": ticker,
            "business_model": led["business_model"] or "UNCLASSIFIED",
            "forms": forms,
            "observations": obs,
            "metrics_with_evidence": sum(
                1 for row in led["rows"] if row["observations_held"] > 0),
            "declared_date_pct": round(100.0 * dated / obs, 1) if obs else None,
            "earliest_filing": span[0], "latest_filing": span[1],
            "dimension_collision_rows": int(coll["n"]),
            "max_distinct_values_one_key": int(coll["mx"]),
            "dimension_collisions_by_metric": dict(sorted(coll_by_metric.items())),
            "status_counts": led["status_counts"],
            "semantic_conflicts": led["semantic_conflicts"],
            "by_metric": {
                row["metric"]: {
                    "status": row["status"],
                    "observations": row["observations_held"],
                    "conflicts": 1 if row.get("semantic_conflict") else 0,
                }
                for row in led["rows"]
            },
        })
    c.close()
    return out


def combined_matrix(groups):
    """business_model x metric x status, over the full-scope archives only."""
    cells = defaultdict(Counter)
    three_way = defaultdict(lambda: defaultdict(Counter))
    conflicts = defaultdict(lambda: defaultdict(int))
    ambiguity = defaultdict(lambda: defaultdict(int))
    issuers_by_model = defaultdict(set)
    pit_by_model = defaultdict(list)
    for label, path in groups:
        if not os.path.exists(path):
            continue
        for rec in issuer_rows(path):
            model = rec["business_model"]
            issuers_by_model[model].add(rec["ticker"])
            if rec["declared_date_pct"] is not None:
                pit_by_model[model].append(
                    (rec["ticker"], rec["declared_date_pct"], rec["observations"]))
            for metric, cell in rec["by_metric"].items():
                cells[metric][cell["status"]] += 1
                three_way[metric][model][cell["status"]] += 1
                if cell["conflicts"]:
                    conflicts[metric][model] += cell["conflicts"]
                ambiguity[metric][model] += rec.get(
                    "dimension_collisions_by_metric", {}).get(metric, 0)
    return {
        "denominator": {
            "definition": "20 Core metrics x every full-scope filer, fixed "
                          "before the fetch by reports/2_27_POPULATION_DESIGN.md",
            "applicable_is_not_a_denominator_term": True,
        },
        "issuers_by_business_model": {k: sorted(v) for k, v in
                                      sorted(issuers_by_model.items())},
        "issuer_counts_by_business_model": {k: len(v) for k, v in
                                           sorted(issuers_by_model.items())},
        "metric_x_status": {m: dict(sorted(c.items())) for m, c in
                            sorted(cells.items())},
        "business_model_x_metric_x_status": {
            m: {mod: dict(sorted(c.items())) for mod, c in sorted(v.items())}
            for m, v in sorted(three_way.items())
        },
        "declared_date_pct_by_business_model": {
            mod: {"issuers": sorted(t for t, _, _ in v),
                  "values": sorted(pct for _, pct, _ in v),
                  "median": sorted(pct for _, pct, _ in v)[len(v) // 2]}
            for mod, v in sorted(pit_by_model.items())
        },
        "metric_x_business_model_conflicts": {
            m: dict(sorted(v.items())) for m, v in sorted(conflicts.items())},
        "metric_x_business_model_dimension_ambiguity": {
            m: dict(sorted(v.items())) for m, v in sorted(ambiguity.items())},
    }


def main():
    result = {
        "experiment": "2.27 cross-business-model evidence corpus",
        "population_manifest": "reports/2_27_POPULATION_DESIGN.md",
        "requests": {
            "cohort_a_submissions": 18,
            "cohort_a_companyfacts_refetched_unintentionally": 18,
            "cohort_b_submissions": 22,
            "cohort_b_companyfacts": 22,
            "total": 80,
        },
        "cohort_a_context_enrichment": {
            "what_it_is": "18 filers whose companyfacts were already held; "
                          "submissions fetched for the first time",
            "panel": panel(COHORT_A),
            "issuers": issuer_rows(COHORT_A),
        },
        "cohort_b_new_issuers": {
            "what_it_is": "22 new filers, companyfacts + submissions, "
                          "20 Core metrics, forms from the issuer's own "
                          "submissions document",
            "panel": panel(COHORT_B),
            "issuers": issuer_rows(COHORT_B),
        },
    }
    result["population_full_scope"] = combined_matrix([
        ("cohort A1", COHORT_A),
        ("cohort B", COHORT_B),
    ] + list(PRIOR_FULL.items()))
    result["prior_full_scope_archives"] = {
        label: panel(path) for label, path in PRIOR_FULL.items()
    }
    result["population_8_metric_archive"] = {
        "note": "the 75-issuer population archive holds 8 of the 20 metrics, so "
                "its cells are scope gaps rather than source silence and it is "
                "reported beside the matrix, not inside it",
        "panel": panel(POPULATION_8_METRIC),
    }
    with open(os.path.join(H, "227-results.json"), "w", encoding="utf-8") as h:
        json.dump(result, h, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    print("cohort A:", json.dumps(r["cohort_a_context_enrichment"]["panel"]))
    print("cohort B:", json.dumps(r["cohort_b_new_issuers"]["panel"]))
    print()
    print("full-scope issuers by business model:")
    for m, n in r["population_full_scope"]["issuer_counts_by_business_model"].items():
        print(f"   {m:<20} {n}")
    print()
    print("metric x status:")
    for m, c in r["population_full_scope"]["metric_x_status"].items():
        tot = sum(c.values())
        print(f"   {m:<32} {c}")
    print()
    print("metric x business_model with semantic conflicts:")
    for m, v in r["population_full_scope"]["metric_x_business_model_conflicts"].items():
        print(f"   {m:<20} {v}")
    print()
    print("metric x business_model dimension ambiguity (collision rows):")
    for m, v in list(r["population_full_scope"][
            "metric_x_business_model_dimension_ambiguity"].items())[:10]:
        print(f"   {m:<20} {v}")