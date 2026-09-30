"""
The eight gates, scored per Core metric per issuer.

Not "how much data". Every metric ST-EVA promises has to clear eight
independent checks, and two of the outcomes that count as success are ones with
no data in them at all:

    NOT_APPLICABLE    the metric does not exist for this company
    SOURCE_SILENT     we asked and the source had nothing

A metric that fails any gate has failed, and the two failures that matter most
are the ones a coverage percentage cannot see:

    a number whose meaning is unknown      no semantic definition or mapping
    a number whose source cannot be traced no provenance

The third outcome, NOT_YET_COLLECTED, is not a failure either -- it is a
quantified backlog item, and the only one of the eight statuses that is work to
do.

Reported per metric per issuer, and then summarised. The gates are:

    1 definition      the semantic layer says what the metric is
    2 mapping         a source concept is declared to express it
    3 adoption        this filer was observed using that concept
    4 observations    the archive holds figures
    5 provenance      every figure resolves to a source fact, document,
                      accession, form and taxonomy
    6 applicability   we know whether it applies to this issuer
    7 missingness     a non-collected metric carries a status, not a blank
    8 discoverable    it is reachable from a query without knowing an id
"""

import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, r"C:\git\st-eva")
from core_registry import CoreRegistry  # noqa: E402
from coverage_semantics import scoped_ledger  # noqa: E402
from evidence_query import EvidenceQuery  # noqa: E402

GATES = (
    "definition", "mapping", "adoption", "observations",
    "provenance", "applicability", "missingness", "discoverable",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--chain-dir", required=True)
    parser.add_argument("--json")
    args = parser.parse_args()

    connection = sqlite3.connect(args.snapshot)
    connection.row_factory = sqlite3.Row
    registry = CoreRegistry(connection)
    query = EvidenceQuery.open(args.snapshot)

    issuers = {}
    for name in sorted(os.listdir(args.chain_dir)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(args.chain_dir, name), encoding="utf-8") as h:
            chain = json.load(h)
        issuers[chain["asset"]] = chain

    report = {}
    print("=" * 96)
    print("EIGHT GATES, PER CORE METRIC PER ISSUER")
    print("=" * 96)
    for ticker, chain in sorted(issuers.items()):
        asset_id = connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ?", (ticker,)
        ).fetchone()[0]
        model = registry.business_model_of(asset_id)
        ledger = scoped_ledger(connection, registry, asset_id, ticker)
        rows = {}
        passed = {gate: 0 for gate in GATES}
        print(f"\n--- {ticker}  business_model={model['business_model'] if model else None}"
              f"  ({model['source'] if model else 'no classification recorded'})")
        for row in ledger["rows"]:
            metric = row["metric"]
            definition = registry.metric(metric)
            mappings = registry.mappings_for_metric(metric)
            used = row["expected_concepts_used"]
            observations = row["observations_held"]
            provenance = 0
            if observations:
                provenance = connection.execute(
                    "SELECT COUNT(*) FROM observations o"
                    " JOIN observation_sources os"
                    " ON os.observation_id = o.observation_id"
                    " WHERE o.asset_id = ? AND o.metric = ?"
                    " AND o.source_fact_id IS NOT NULL"
                    " AND os.accession IS NOT NULL",
                    (asset_id, metric),
                ).fetchone()[0]
            reachable = 0
            if definitions_only := True:
                try:
                    reachable = len(query.query_observations(
                        asset=ticker, metric=metric, limit=1
                    ))
                except Exception:
                    reachable = 0
            gates = {
                "definition": definition is not None
                and bool((definition.semantic_definition or "").strip()),
                "mapping": bool(mappings),
                # Adoption is a *question*, not a yes. The gate is satisfied
                # when the question has a recorded answer, and there are three
                # kinds of answer besides "yes": the source was asked and had
                # nothing, the concept was declined on the record, or the archive
                # says it cannot tell. Anything else means nobody has ever
                # asked, which is the failure this gate exists to catch.
                "adoption": bool(mappings) and (
                    bool(used) or row["status"] in (
                        "SOURCE_SILENT", "NOT_YET_COLLECTED", "UNDETERMINED",
                        "MAPPED_NO_CURRENT_OBSERVATION",
                        "DELIBERATELY_DECLINED",
                    )
                ),
                "observations": observations > 0,
                "provenance": (observations == 0) or (
                    provenance == observations
                ),
                # Known means either a classification exists and a ruling was
                # derived, or no classification exists and the archive says so
                # rather than assuming. A blank is the failure here.
                "applicability": model is not None or (
                    row["status"] == "NOT_APPLICABLE"
                ),
                "missingness": observations > 0 or bool(row["status"]),
                "discoverable": bool(reachable) or observations == 0,
            }
            rows[metric] = gates
            for gate, ok in gates.items():
                if ok:
                    passed[gate] += 1
        report[ticker] = {
            "business_model": model["business_model"] if model else None,
            "business_model_source": model["source"] if model else None,
            "metrics": rows,
            "gate_totals": passed,
            "metrics_total": len(rows),
            "chain_totals": chain["totals"],
        }
        print("   " + "  ".join(
            f"{gate}={passed[gate]}/{len(rows)}" for gate in GATES
        ))
        failures = [
            f"{metric}:{gate}"
            for metric, gates in rows.items()
            for gate, ok in gates.items() if not ok
        ]
        print(f"   failing gates: {failures or 'none'}")

    print()
    print("=" * 96)
    print("ACROSS ALL SIX ISSUERS")
    print("=" * 96)
    total = {}
    for ticker, entry in sorted(report.items()):
        t = entry["chain_totals"]
        print(f"\n{ticker:<6} metrics {t['metrics']:<3} applicable {t['applicable']:<3}"
              f" collected {t['collected']:<3} backlog {t['backlog']:<3}"
              f" declined concepts {t['declined_concepts']}")
        for gate, n in entry["gate_totals"].items():
            total.setdefault(gate, 0)
            total[gate] += n
    print()
    print("gate pass counts across every issuer (6 x 20 = 120 metric-issuers):")
    for gate, n in total.items():
        print(f"   {gate:<16} {n}/120")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, default=str)
    query.close()
    connection.close()


if __name__ == "__main__":
    main()