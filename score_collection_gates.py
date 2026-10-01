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
from collections import defaultdict
from typing import Any, Dict, List

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

    # metric-issuers by ledger status, accumulated across issuers, so the
    # `observations` gate can be read rather than only counted.
    outcome_by_status: Dict[str, Dict[str, int]] = defaultdict(dict)
    report = {}
    skipped: list = []
    print("=" * 96)
    print("EIGHT GATES, PER CORE METRIC PER ISSUER")
    print("=" * 96)
    for ticker, chain in sorted(issuers.items()):
        row = connection.execute(
            "SELECT asset_id FROM assets WHERE ticker = ?", (ticker,)
        ).fetchone()
        if row is None:
            # Named, not fatal, and not silent. This used to raise
            # `TypeError: 'NoneType' object is not subscriptable` and kill the whole
            # run, which is the same failure shape as 2.13's empty
            # `tickers.json`: a chain naming an issuer the archive does not hold
            # and a genuine gap are indistinguishable if the only difference is
            # that one of them stops the tool. So a skip is recorded with a reason
            # and reported at the end.
            skipped.append({
                "ticker": ticker,
                "reason": "the archive holds no asset with this ticker",
            })
            print(f"\n--- {ticker}  SKIPPED: the archive holds no asset "
                  f"with this ticker")
            continue
        asset_id = row[0]
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
                # when the question has a recorded answer, and there are several
                # kinds of answer besides "yes": the source was asked and had
                # nothing, the concept was declined on the record, the archive
                # says it cannot tell, or -- the case 2.14 found -- the metric
                # was ruled inapplicable to this filer. `NOT_APPLICABLE` was
                # missing from this list, so an issuer whose applicability ruling
                # was recorded and correct failed the gate for having recorded
                # it: the API-built archive read 119/120 against the bulk-built
                # archive's 120/120 for no semantic reason at all.
                "adoption": bool(mappings) and (
                    bool(used) or row["status"] in (
                        "SOURCE_SILENT", "NOT_YET_COLLECTED", "UNDETERMINED",
                        "MAPPED_NO_CURRENT_OBSERVATION",
                        "DELIBERATELY_DECLINED",
                        "NOT_APPLICABLE",
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
            # Why a cell holds no observations, next to the fact that it holds
            # none.
            #
            # `observations` is `observations > 0`, which is the right assertion
            # and an unreadable one. Run over the 75-issuer archive -- 8 metrics
            # asked, 20 in the Core universe -- it read 491/1500, and 1,009 of
            # those "failures" were: 488 never asked (scope), 384 a concept
            # declined on the record, 48 a filer the metric was ruled inapplicable
            # to, 55 a declared composition whose facts are held under the parent,
            # and 34 -- 3.4% -- a filer that was asked and reported nothing.
            #
            # So the pass rate is not a quality measure; it is a scope measure
            # wearing a quality measure's name. The gate is not changed here,
            # because deciding which statuses satisfy it is a semantic decision.
            # What is added is the split, so the number can be read instead of
            # being waved at.
            # Keyed by issuer as well as metric, or 75 issuers collapse into one
            # and the summary reports 37 cells instead of 1,500.
            outcome_by_status[row["status"]][(ticker, metric)] = observations
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
    print(f"ACROSS ALL {len(report)} ISSUERS MEASURED")
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

    # The universe is counted, not asserted. This line used to read
    # "6 x 20 = 120 metric-issuers" with both numbers typed in, which is a
    # description of one run rather than a measurement of whatever ran.
    issuers_measured = len(report)
    metrics_total = sum(
        entry["metrics_total"] for entry in report.values()
    )
    universe = metrics_total
    print()
    print(
        f"gate pass counts across every issuer measured "
        f"({issuers_measured} x "
        f"{metrics_total // issuers_measured if issuers_measured else 0} "
        f"= {universe} metric-issuers, "
        f"{len(skipped)} skipped):"
    )
    for gate, n in total.items():
        print(f"   {gate:<16} {n}/{universe}")

    if skipped:
        print()
        print("SKIPPED ISSUERS, BY REASON")
        for entry in skipped:
            print(f"   {entry['ticker']}: {entry['reason']}")

    print()
    print("=" * 96)
    print("WHY A CELL HOLDS NO OBSERVATIONS, BY LEDGER STATUS")
    print("=" * 96)
    print(
        "  The `observations` gate asserts observations > 0. That is the right "
        "assertion\n  and an unreadable one, so the failures are split here "
        "rather than only counted."
    )
    status_summary = {}
    for status, cells in sorted(outcome_by_status.items()):
        cells_total = len(cells)
        empty = sum(1 for n in cells.values() if n == 0)
        status_summary[status] = {
            "metric_issuers": cells_total,
            "with_observations": cells_total - empty,
            "without_observations": empty,
        }
        print(
            f"   {status:<32} {cells_total:>5} metric-issuers, "
            f"{cells_total - empty:>5} with observations, {empty:>5} without"
        )
    without = sum(
        entry["without_observations"] for entry in status_summary.values()
    )
    asked_and_empty = sum(
        entry["without_observations"]
        for status, entry in status_summary.items()
        if status == "SOURCE_SILENT"
    )
    print()
    print(
        f"   of {without} cells holding no observations, {asked_and_empty} are "
        f"SOURCE_SILENT -- a filer\n   that was asked and reported nothing, "
        f"which is what this gate exists to catch."
    )

    print()
    print("=" * 96)
    print("SEMANTIC CONFLICTS: EVIDENCE HELD FOR A METRIC RULED INAPPLICABLE")
    print("=" * 96)
    conflicts: List[Dict[str, Any]] = []
    for ticker, chain in sorted(issuers.items()):
        for entry in chain.get("semantic_conflicts") or []:
            conflicts.append({"ticker": ticker, **entry})
    if conflicts:
        print(
            f"  {len(conflicts)} metric-issuer(s) where the source reported a "
            f"metric the registry\n  rules out for this filer. The evidence is "
            f"kept and the conflict is reported."
        )
        for entry in conflicts:
            print(
                f"   {entry['ticker']:<7} {entry['metric']:<20} "
                f"{entry['observations_held']:>4} obs   "
                f"{entry['concepts_reported']}"
            )
        print()
        print(
            "  ** Not scored. ** These cells pass `observations` and are "
            "counted under\n  `NOT_APPLICABLE` at the same time, because "
            "evidence existence, applicability\n  and coverage are three "
            "separate facts. Whether a conflict should\n  count as a gate "
            "failure is an open decision, and this tool does not\n  take it "
            "quietly."
        )
    else:
        print("  none: no metric holds evidence the registry rules out.")

    if args.json:
        payload = {"issuers": report}
        if skipped:
            payload["skipped"] = skipped
        payload["measured"] = {
            "issuers": issuers_measured,
            "metric_issuers": universe,
            "gate_pass_counts": dict(sorted(total.items())),
            "observations_by_ledger_status": status_summary,
        }
        # Reported, not scored. A conflict is a disagreement between the source
        # and the registry, and whether it should fail a gate is a decision this
        # tool does not take on the reader's behalf.
        payload["semantic_conflicts"] = conflicts
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, default=str)
    query.close()
    connection.close()


if __name__ == "__main__":
    main()