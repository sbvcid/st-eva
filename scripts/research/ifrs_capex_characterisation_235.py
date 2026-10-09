"""
2.35 -- IFRS CAPEX characterisation, two candidates validated independently.

Read-only. No registry entry, no mapping, no metric definition, no applicability
rule, no fetch. `debt` is closed at 2.33; `capex`'s US-GAAP candidate is UNDECIDED
at 2.34. This round is about the two IFRS concepts 2.34 found behind five
capex-silent filers.

    A  ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities
    B  ifrs-full:AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment

They are separated deliberately. A reads as a cash purchase of PPE; B reads as an
*addition* to PPE excluding business combinations, which need not be a cash
outflow at all -- a revaluation, a transfer or an exchange would satisfy B and not
A. So B carries a burden A does not: it has to show that additions here have no
important non-cash source before its numbers can be read as capital expenditure.

## What counts as evidence here

Not a name. Not identical values. Not the same period coverage, the same sign, or
simultaneous reporting. A numerical match is supporting evidence and nothing
more. 2.34 established why this is not pedantry: where the two *declared* capex
concepts co-report they are **identical in 23 of 23 periods** despite different
declared scopes, so value arithmetic can confirm a relationship it cannot
distinguish from a third thing.

The anchor is the source's own definition. Which produces the finding of this
round, in `main` and in the artefact:

    both candidates return label=None and definition=None

The entire `ifrs-full` side of this registry supplies **neither a label nor a
description** in `companyfacts`. So for these two there is no source semantic
anchor to reason from, and the only semantic signal available is the name -- which
the critical rule forbids using. That is not a gap in the analysis; it is a
property of the source, and it is why both verdicts are UNDECIDED rather than
one being SUPPORTED on a technicality.
"""

from __future__ import annotations

import glob
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
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402
# Issuer identity comes from the payload's own `cik`; see
# issuer_identity.py for why the filename is a diagnostic only.
import issuer_identity  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")
PAYLOAD_DIRS = [
    "bulkfacts-227a-orig", "bulkfacts-227b", "bulkfacts-ins-min",
    "bulkfacts-fs", "bulkfacts-banks-2", "inventory", "bulkfacts",
    "bulkfacts-banks",
]
ARCHIVES = ["snapshot-227-a1", "snapshot-227-b", "snapshot-banks2",
            "snapshot-fs", "snapshot-ins-min", "snapshot-universe",
            "snapshot-population"]

CANDIDATE_A = (
    "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities")
CANDIDATE_B = (
    "ifrs-full:AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment")
DECLARED_CAPEX = [
    "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
    "us-gaap:PaymentsToAcquireProductiveAssets",
]
OTHER = [
    "ifrs-full:PropertyPlantAndEquipment",
    "us-gaap:PaymentsForCapitalImprovements",
]


def documents():
    # Issuer identity comes from each payload's own `cik`, joined to the
    # archive assets table; the filename is a diagnostic. The per-directory
    # loader is not used here because it cannot know the harness root, and
    # without the join it degrades silently to CIK: keys.
    return issuer_identity.load_harness_payloads(H, list(PAYLOAD_DIRS))[0]


def body_of(doc: dict, concept: str):
    taxonomy, name = concept.split(":")
    return (doc.get("facts") or {}).get(taxonomy, {}).get(name)


def facts_of(body: dict) -> dict:
    """period_end -> {"values": set, "starts": set, "accessions": set}."""
    by_period = defaultdict(
        lambda: {"values": set(), "starts": set(), "accessions": set()})
    for unit, rows in (body.get("units") or {}).items():
        for r in rows:
            if not r.get("end"):
                continue
            slot = by_period[str(r["end"])]
            slot["values"].add(r.get("val"))
            if r.get("start"):
                slot["starts"].add(str(r["start"]))
            if r.get("accn"):
                slot["accessions"].add(r["accn"])
    return dict(by_period)


def describe(concept: str, docs: dict, declared: set) -> dict:
    filers = {}
    label = description = None
    for ticker, path in docs.items():
        doc = json.load(open(path, encoding="utf-8"))
        body = body_of(doc, concept)
        if not body:
            continue
        label = label or body.get("label")
        description = description or body.get("description")
        periods = facts_of(body)
        instants = sum(1 for p in periods.values() if not p["starts"])
        durations = len(periods) - instants
        signs = Counter()
        for slot in periods.values():
            for v in slot["values"]:
                try:
                    signs["negative" if float(v) < 0
                          else "positive" if float(v) > 0 else "zero"] += 1
                except (TypeError, ValueError):
                    signs["non_numeric"] += 1
        units = sorted({u for u in (body.get("units") or {})})
        filers[ticker] = {
            "periods": len(periods), "instants": instants,
            "durations": durations,
            "accessions": len({a for s in periods.values()
                               for a in s["accessions"]}),
            "units": units,
            "signs": dict(signs),
            "ambiguous_periods": sum(
                1 for s in periods.values() if len(s["values"]) > 1),
            "earliest_period": min(periods) if periods else None,
            "latest_period": max(periods) if periods else None,
            "facts": {k: {"values": sorted(v["values"], key=str),
                          "accessions": sorted(v["accessions"]),
                          "starts": sorted(v["starts"])}
                      for k, v in periods.items()},
        }
    comparators = {}
    for other in DECLARED_CAPEX + OTHER:
        taxonomy, name = other.split(":")
        both = sorted(
            t for t in filers
            if body_of(json.load(open(docs[t], encoding="utf-8")), other))
        if both:
            comparators[other] = both
    return {
        "concept": concept,
        "declared_for_capex": concept in declared,
        "sec_label": label,
        "sec_definition": description,
        "source_semantic_anchor_available": bool((label or "").strip()
                                                 or (description or "").strip()),
        "filer_count": len(filers), "filers": sorted(filers),
        "total_periods": sum(f["periods"] for f in filers.values()),
        "total_instants": sum(f["instants"] for f in filers.values()),
        "total_durations": sum(f["durations"] for f in filers.values()),
        "total_accessions": sum(f["accessions"] for f in filers.values()),
        "ambiguous_periods": sum(f["ambiguous_periods"] for f in filers.values()),
        "units_across_filers": sorted({
            u for f in filers.values() for u in f["units"]}),
        "signs": dict(Counter(
            k for f in filers.values() for k, v in f["signs"].items()
            for _ in range(v))),
        "comparators_in_the_same_documents": comparators,
        "per_filer": filers,
    }


def compare(left: dict, right: dict, shared_filers) -> dict:
    kinds = Counter()
    rows = []
    for ticker in shared_filers:
        lf, rf = left["per_filer"][ticker]["facts"], right["per_filer"][ticker]["facts"]
        for period in sorted(set(lf) & set(rf)):
            lv, rv = lf[period]["values"], rf[period]["values"]
            if len(lv) != 1 or len(rv) != 1:
                rows.append({"ticker": ticker, "period_end": period,
                             "usable": False,
                             "why": "more than one value for a period on one "
                                    "side; dimension members are not separable"})
                continue
            a, b = float(next(iter(lv))), float(next(iter(rv)))
            if abs(a - b) < 0.5:
                kind = "equal"
            elif abs(a - b) < 0.5 * max(abs(a), abs(b)):
                kind = "near_equal"
            else:
                kind = "different"
            kinds[kind] += 1
            rows.append({"ticker": ticker, "period_end": period, "usable": True,
                         "relationship": kind, "left": a, "right": b,
                         "ratio_left_to_right": round(a / b, 4) if b else None})
    return {"comparable_periods": sum(kinds.values()),
            "relationship_kinds": dict(kinds), "per_period": rows}


def capex_silent(docs: dict) -> list:
    out = []
    for name in ARCHIVES:
        path = os.path.join(H, f"{name}.sqlite")
        if not os.path.exists(path):
            continue
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        registry = CoreRegistry(c)
        from coverage_semantics import scoped_ledger
        for row in c.execute("SELECT asset_id, ticker FROM assets"):
            t = str(row["ticker"]).upper()
            if t in out:
                continue
            led = scoped_ledger(c, registry, str(row["asset_id"]), t)
            cell = next(r for r in led["rows"] if r["metric"] == "capex")
            if cell["status"] == "SOURCE_SILENT":
                out.append(t)
        c.close()
    return sorted(set(out))


def main():
    probe = SQLiteArchive(":memory:")
    registry = CoreRegistry(probe.connection)
    seed(registry)
    capex = registry.metric("capex")
    declared = {m.concept_id for m in registry.mappings_for_metric("capex")}
    mapped_anywhere = {m.concept_id for metric in registry.metrics()
                      for m in registry.mappings_for_metric(metric.metric_id)}
    probe.close()

    docs = documents()
    a = describe(CANDIDATE_A, docs, declared)
    b = describe(CANDIDATE_B, docs, declared)

    shared = sorted(set(a["filers"]) & set(b["filers"]))
    a_vs_b = compare(a, b, shared)

    silent = capex_silent(docs)
    classification = {}
    for ticker in silent:
        if ticker not in docs:
            classification[ticker] = {
                "bucket": "no document on disk to characterise",
                "A_present": None, "B_present": None,
                "other_concepts_present": None,
            }
            continue
        doc = json.load(open(docs[ticker], encoding="utf-8"))
        present_a = bool(body_of(doc, CANDIDATE_A))
        present_b = bool(body_of(doc, CANDIDATE_B))
        other = sorted(
            concept for concept in OTHER + DECLARED_CAPEX
            if body_of(doc, concept)
            and concept not in (CANDIDATE_A, CANDIDATE_B))
        if present_a and present_b:
            bucket = "both A and B"
        elif present_a:
            bucket = "A only"
        elif present_b:
            bucket = "B only"
        elif other:
            bucket = "neither, but other capex-shaped concepts present"
        else:
            bucket = "neither"
        classification[ticker] = {
            "bucket": bucket, "A_present": present_a, "B_present": present_b,
            "other_concepts_present": other,
        }

    # A recognised capex comparator in the same document is condition 7, and it
    # is checked explicitly rather than assumed.
    comparator_check = {}
    for name, row in (("A", a), ("B", b)):
        recognised = {k: v for k, v in
                      row["comparators_in_the_same_documents"].items()
                      if k in DECLARED_CAPEX}
        balances = {k: v for k, v in
                    row["comparators_in_the_same_documents"].items()
                    if k == "ifrs-full:PropertyPlantAndEquipment"}
        comparator_check[name] = {
            "declared_capex_comparator_in_same_document":
                recognised or None,
            "balance_sheet_concept_in_same_document": balances or None,
            "any_recognised_comparator": bool(recognised),
        }

    def verdict(name, row, burden):
        anchor = row["source_semantic_anchor_available"]
        comparator = comparator_check[name]["any_recognised_comparator"]
        conditions = {
            "1_definition_and_accounting_object_available":
                ("PASS" if anchor else
                 "NOT ESTABLISHED -- the payload supplies no label and no "
                 "description for this concept, so there is no source statement "
                 "of what it measures"),
            "2_cash_flow_or_balance_nature": (
                "PASS -- every fact is a duration, a flow over a period"
                if row["total_instants"] == 0 else
                "PARTIAL -- instants and durations both present"),
            "3_asset_scope": (
                "NOT ESTABLISHED -- scope is knowable only from the name, which "
                "the critical rule excludes as evidence"),
            "4_acquisitions_outside_ppe":
                "NOT ESTABLISHED -- requires the definition; the name of B "
                "asserts an exclusion and asserting it is not evidence"
                if name == "B" else
                "NOT ESTABLISHED -- requires the definition",
            "5_non_cash_additions_possible": (
                "NOT ESTABLISHED -- this is precisely the question a definition "
                "would answer, and there is none"
                if name == "B" else
                "NOT ESTABLISHED -- requires the definition"),
            "6_unit_sign_period_semantics": (
                f"RECORDED -- durations {row['total_durations']}, instants "
                f"{row['total_instants']}, units {row['units_across_filers']}, "
                f"signs {row['signs']}"),
            "7_a_recognised_capex_comparator_in_the_same_document": (
                "FAIL -- no filer of this concept reports any declared capex "
                "concept" if not comparator else "PASS"),
            "8_survives_cross_filer_comparison": (
                f"PARTIAL -- {len(shared)} filer(s) report both IFRS concepts, "
                f"{a_vs_b['comparable_periods']} comparable periods: "
                f"{a_vs_b['relationship_kinds']}"),
        }
        if anchor and comparator:
            state = "NEEDS_REVIEW"
        else:
            state = "UNDECIDED"
        return {
            "verdict": state,
            "conditions": conditions,
            "blocking_evidence_gaps": [
                g for g in (
                    None if anchor else
                    "the source supplies no label or description for this "
                    "concept, so the accounting object cannot be stated",
                    None if comparator else
                    "no filer reporting this concept also reports a declared "
                    "capex concept, so no cross-framework comparison is "
                    "possible",
                    burden,
                ) if g
            ],
            "what_would_change_the_verdict": [
                "a statement of what the concept measures, from the filing's "
                "own taxonomy reference or a statement of presentation context",
                "a filer reporting this concept together with a declared capex "
                "concept in the same period",
            ],
        }

    results = {
        "A": verdict("A", a,
                     "A's burden is light: a name asserting a cash purchase of "
                     "PPE is consistent with capital expenditure, and the "
                     "absence of a label means even that is unconfirmed"),
        "B": verdict("B", b,
                     "B carries the extra burden set out in the goal: an "
                     "*addition* to PPE excluding business combinations can be "
                     "non-cash, so the concept has to show its additions have "
                     "no material non-cash source before its numbers can be read "
                     "as capital expenditure. Without a definition that is "
                     "unavailable"),
    }

    result = {
        "experiment": "2.35 IFRS CAPEX characterisation",
        "capex_declaration": {
            "display_name": capex.display_name,
            "semantic_definition": capex.semantic_definition,
            "declared_concepts": sorted(declared),
        },
        "candidates": {"A": a, "B": b},
        "comparator_check": comparator_check,
        "A_vs_B_measured": a_vs_b,
        "capex_silent_filers": silent,
        "silent_filer_classification": classification,
        "candidate_verdicts": results,
        "mapping_performed": False,
    }
    with open(os.path.join(H, "235-ifrs-capex.json"), "w", encoding="utf-8") as h:
        json.dump(result, h, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    d = r["capex_declaration"]
    print("Core capex, as declared")
    print(f"  definition : {d['semantic_definition']}")
    print(f"  declared   : {d['declared_concepts']}\n")
    for name in ("A", "B"):
        row = r["candidates"][name]
        v = r["candidate_verdicts"][name]
        print(f"Candidate {name}: {v['verdict']}   {row['concept']}")
        print(f"  SEC label      : {row['sec_label']}")
        print(f"  SEC definition : {row['sec_definition']}")
        print(f"  anchor available: {row['source_semantic_anchor_available']}")
        print(f"  filers         : {row['filer_count']} {row['filers']}")
        print(f"  durations/instants: {row['total_durations']}/{row['total_instants']}"
              f"  units {row['units_across_filers']}  signs {row['signs']}")
        print(f"  ambiguous periods : {row['ambiguous_periods']}")
        print(f"  comparators       : "
              f"{list(row['comparators_in_the_same_documents']) or 'none'}")
        for gap in v["blocking_evidence_gaps"]:
            print(f"    BLOCKER: {gap}")
        print()
    m = r["A_vs_B_measured"]
    print(f"A vs B, measured: {m['comparable_periods']} comparable periods "
          f"{m['relationship_kinds']}")
    for row in m["per_period"][:8]:
        print(f"    {row.get('ticker')} {row.get('period_end')} "
              f"{row.get('relationship')} {row.get('ratio_left_to_right')}")
    print()
    buckets = defaultdict(list)
    for t, row in r["silent_filer_classification"].items():
        buckets[row["bucket"]].append(t)
    print(f"capex = SOURCE_SILENT filers with a document: {len(r['capex_silent_filers'])}")
    for bucket, tickers in sorted(buckets.items()):
        print(f"  {bucket:<48} {len(tickers):>2} {sorted(tickers)}")