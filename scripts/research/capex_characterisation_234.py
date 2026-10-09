"""
2.34 -- CAPEX vocabulary characterisation.

`debt` is closed at 2.33 and is not touched here. This round asks one question
about `capex`, as a proposition and not as a mapping request:

> Does `us-gaap:PaymentsForCapitalImprovements` denote the same accounting
> quantity that Core `capex` is declared to preserve?

Nothing is changed. No registry entry, no mapping, no metric definition, no
applicability rule, no fetch. Only the archives and the raw `companyfacts` already
on disk are read.

## The three candidates

`capex` currently declares two concepts, and 2.28 found a third in the documents
of three filers whose `capex` reads `SOURCE_SILENT`:

    us-gaap:PaymentsToAcquirePropertyPlantAndEquipment   EXACT   (declared)
    us-gaap:PaymentsToAcquireProductiveAssets            PARTIAL (declared)
    us-gaap:PaymentsForCapitalImprovements               --      (unmapped)

## What is evidence here, and what is not

**The source's own definition is the anchor.** 2.29 established, four times over,
that a name is not a definition: a needle for "debt" admitted debt *securities*,
a borrowing *capacity*, a *ratio* of indebtedness, accrued *interest* and a debt
*extinguishment payment*. So every semantic statement below is grounded in the
SEC's own concept description, quoted, and never in a name.

**Value arithmetic is the second anchor, where it is available.** 2.31 established
for `debt` that two concepts either sum, or nest, or are disjoint, and only
arithmetic says which. So for every filer reporting more than one candidate, the
relationships are measured rather than inferred.

**What is explicitly not evidence:**

  * that a concept has observations
  * that every fact is an instant -- a movement is also an instant-shaped fact and
    period shape is a property of the shape, not the meaning
  * that several filers report it -- usage is not equivalence
  * that the words resemble each other
  * that a `PARTIAL` mapping could be promoted because it would raise coverage
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
# Issuer identity comes from the payload's own cik; see
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

CANDIDATES = [
    "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
    "us-gaap:PaymentsToAcquireProductiveAssets",
    "us-gaap:PaymentsForCapitalImprovements",
]

# Wording that would make a concept a different accounting object from capital
# expenditure as the registry declares it. Used only to *disqualify*, never to
# admit -- an admission has to rest on the source's own description.
DIFFERENT_OBJECT = (
    "debt", "borrow", "lease", "interest", "income tax", "dividend",
    "proceeds from", "repayment", "goodwill", "intangible asset",
    "revenue", "expense other than", "noncash", "non-cash",
    "net of", "acquisition of a business",
)

# Substrings used only to *collect* capital-expenditure-like concepts for the
# silence check. A candidate admitted by this list is not thereby a candidate;
# every one is reported with its own description for a reader to judge.
CAPEX_SHAPED = (
    "PaymentsToAcquire", "PaymentsForCapital", "CapitalExpenditure",
    "PropertyPlantAndEquipment", "ProductiveAssets",
)


def documents():
    """ticker -> companyfacts path, from whatever payload holds it."""
    # Issuer identity comes from each payload's own `cik`, joined to the
    # archive assets table; the filename is a diagnostic. The per-directory
    # loader is not used here because it cannot know the harness root, and
    # without the join it degrades silently to CIK: keys.
    return issuer_identity.load_harness_payloads(H, list(PAYLOAD_DIRS))[0]


def capex_status() -> dict:
    """`capex` status and business model, per filer, across the archives."""
    out = {}
    for name in ARCHIVES:
        path = os.path.join(H, f"{name}.sqlite")
        if not os.path.exists(path):
            continue
        c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        registry = CoreRegistry(c)
        for row in c.execute("SELECT asset_id, ticker FROM assets"):
            t = str(row["ticker"]).upper()
            if t in out:
                continue
            led = scoped = registry
            from coverage_semantics import scoped_ledger
            led = scoped_ledger(c, registry, str(row["asset_id"]), t)
            cell = next(r for r in led["rows"] if r["metric"] == "capex")
            out[t] = {
                "business_model": led["business_model"] or "UNCLASSIFIED",
                "capex_status": cell["status"],
                "capex_observations": cell["observations_held"],
                "archive": name,
            }
        c.close()
    return out


def concept_facts(doc: dict, concept: str) -> dict:
    """Every fact for one concept: values, periods, units, accessions."""
    taxonomy, name = concept.split(":")
    body = (doc.get("facts") or {}).get(taxonomy, {}).get(name)
    if not body:
        return {}
    by_period = defaultdict(lambda: {"values": set(), "accessions": set(),
                                     "forms": set(), "starts": set()})
    units = set()
    for unit, rows in (body.get("units") or {}).items():
        units.add(unit)
        for r in rows:
            if not r.get("end"):
                continue
            slot = by_period[str(r["end"])]
            slot["values"].add(r.get("val"))
            if r.get("accn"):
                slot["accessions"].add(r["accn"])
            if r.get("form"):
                slot["forms"].add(r["form"])
            slot["starts"].add(r.get("start"))
    return {
        "label": body.get("label"),
        "description": body.get("description"),
        "units": sorted(units),
        "periods": {p: {"values": sorted(v["values"], key=str),
                        "accessions": sorted(v["accessions"]),
                        "forms": sorted(v["forms"]),
                        "starts": sorted(x for x in v["starts"] if x),
                        "duration": any(v["starts"])}
                    for p, v in by_period.items()},
    }


def relationships(a: dict, b: dict) -> list:
    """Measured relationships between two concepts, per shared period."""
    out = []
    shared = set(a["periods"]) & set(b["periods"])
    for period in sorted(shared):
        left = a["periods"][period]["values"]
        right = b["periods"][period]["values"]
        if len(left) != 1 or len(right) != 1:
            out.append({"period_end": period, "usable": False,
                        "why": "more than one value for a period on one side; "
                               "dimension members are not separable here"})
            continue
        lv, rv = next(iter(left)), next(iter(right))
        try:
            lv, rv = float(lv), float(rv)
        except (TypeError, ValueError):
            out.append({"period_end": period, "usable": False,
                        "why": "non-numeric value"})
            continue
        if abs(lv - rv) < 0.5:
            kind = "equal"
        elif abs(lv - rv) < 0.5 * max(abs(lv), abs(rv)):
            kind = "near_equal"
        else:
            kind = "different"
        out.append({
            "period_end": period, "usable": True, "relationship": kind,
            "left": lv, "right": rv,
            "ratio_left_to_right": round(lv / rv, 4) if rv else None,
            "right_is_sum_with_others": None,
        })
    return out


def main():
    registry_store = SQLiteArchive(":memory:")
    registry = CoreRegistry(registry_store.connection)
    seed(registry)
    capex_metric = registry.metric("capex")
    declared = {m.concept_id: m.mapping_type
                for m in registry.mappings_for_metric("capex")}
    registry_store.close()

    docs = documents()
    status = capex_status()

    candidate_rows = {}
    concepts = {}
    for concept in CANDIDATES:
        per_filer = {}
        meta = {"label": None, "description": None, "units": set()}
        for ticker, path in docs.items():
            doc = json.load(open(path, encoding="utf-8"))
            facts = concept_facts(doc, concept)
            if not facts:
                continue
            meta["label"] = meta["label"] or facts["label"]
            meta["description"] = meta["description"] or facts["description"]
            meta["units"] |= set(facts["units"])
            periods = facts["periods"]
            accessions = {a for p in periods.values() for a in p["accessions"]}
            ambiguous = sum(1 for p in periods.values() if len(p["values"]) > 1)
            durations = sum(1 for p in periods.values() if p["duration"])
            per_filer[ticker] = {
                "capex_status": status.get(ticker, {}).get("capex_status"),
                "business_model": status.get(ticker, {}).get(
                    "business_model"),
                "periods": len(periods),
                "accessions": len(accessions),
                "forms": sorted({f for p in periods.values()
                                 for f in p["forms"]}),
                "duration_periods": durations,
                "instant_periods": len(periods) - durations,
                "units": facts["units"],
                "ambiguous_periods": ambiguous,
                "earliest_period": min(periods) if periods else None,
                "latest_period": max(periods) if periods else None,
                "representative_facts": [
                    {"period_end": p,
                     "values": periods[p]["values"],
                     "accessions": periods[p]["accessions"][:3],
                     "forms": periods[p]["forms"]}
                    for p in sorted(periods)[-3:]
                ],
                "facts": periods,
            }
        description = (meta["description"] or "").strip()
        # Prompt, not verdict. `PaymentsToAcquireProductiveAssets` mentions
        # intangibles, and it is *deliberately* declared PARTIAL for exactly that
        # reason -- so a keyword that fires on it is reporting a scope difference
        # the registry already knows about and has typed.
        deserves_attention = [t for t in DIFFERENT_OBJECT
                              if t in description.lower()]
        concepts[concept] = per_filer
        candidate_rows[concept] = {
            "sec_label": meta["label"],
            "sec_definition": description or None,
            "declared_for_capex": declared.get(concept),
            "filers_reporting_it": sorted(per_filer),
            "filer_count": len(per_filer),
            "total_accessions": sum(f["accessions"] for f in per_filer.values()),
            "total_periods": sum(f["periods"] for f in per_filer.values()),
            "units": sorted(meta["units"]),
            "wording_deserving_attention": deserves_attention,
            "per_filer": per_filer,
        }

    # Measured relationships between the candidates, for filers reporting both.
    pair_rows = {}
    for i, left in enumerate(CANDIDATES):
        for right in CANDIDATES[i + 1:]:
            shared_filers = sorted(set(concepts[left]) & set(concepts[right]))
            rows = []
            for ticker in shared_filers:
                lf = concepts[left][ticker]["facts"]
                rf = concepts[right][ticker]["facts"]
                found = relationships({"periods": lf}, {"periods": rf})
                usable = [r for r in found if r["usable"]]
                if usable:
                    tally = Counter(r["relationship"] for r in usable)
                    rows.append({"ticker": ticker,
                                 "comparable_periods": len(usable),
                                 "relationships": dict(tally)})
            kinds = Counter()
            for r in rows:
                kinds.update(r["relationships"])
            pair_rows[f"{left}  vs  {right}"] = {
                "filers_reporting_both": shared_filers,
                "per_filer": rows,
                "relationship_kinds": dict(kinds),
                "comparable_periods_total": sum(kinds.values()),
            }

    # The silence check: what else do the silent filers report that is
    # capex-shaped, and unmapped.
    probe = SQLiteArchive(":memory:")
    preg = CoreRegistry(probe.connection)
    seed(preg)
    mapped = {m.concept_id for m in preg.metrics()
              for m in preg.mappings_for_metric(m.metric_id)}
    declined = {d["concept_id"] for m in preg.metrics()
                for d in preg.declines_for_metric(m.metric_id)}
    probe.close()

    silent = sorted(t for t, v in status.items()
                    if v["capex_status"] == "SOURCE_SILENT")
    silence_rows = {}
    for ticker in silent:
        path = docs.get(ticker)
        if not path:
            continue
        doc = json.load(open(path, encoding="utf-8"))
        found = []
        for taxonomy, concepts_map in (doc.get("facts") or {}).items():
            for name, body in concepts_map.items():
                key = f"{taxonomy}:{name}"
                if not any(s in key for s in CAPEX_SHAPED):
                    continue
                units = (body.get("units") or {})
                rows = sum(len(r) for r in units.values())
                found.append({
                    "concept": key,
                    "declared_for_capex": key in declared,
                    "mapped_to_anything": key in mapped,
                    "declined": key in declined,
                    "label": body.get("label"),
                    "description": (body.get("description") or "")[:400],
                    "rows": rows,
                    "units": sorted(units),
                })
        silence_rows[ticker] = {
            "business_model": status[ticker]["business_model"],
            "capex_shaped_concepts": sorted(
                found, key=lambda x: -x["rows"]),
            "unmapped_capex_shaped": sorted(
                x["concept"] for x in found
                if not x["mapped_to_anything"] and not x["declared_for_capex"]),
        }

    result = {
        "proposition": {
            "statement": "us-gaap:PaymentsForCapitalImprovements denotes the "
                         "same accounting quantity as Core capex.",
            "verdict": None,
        },
        "capex_declaration": {
            "display_name": capex_metric.display_name,
            "semantic_definition": capex_metric.semantic_definition,
            "unit_family": capex_metric.unit_family,
            "period_type": capex_metric.normal_period_type,
            "declared_concepts": declared,
        },
        "candidates": candidate_rows,
        "measured_relationships": pair_rows,
        "capex_silent_filers": silent,
        "silence_check": silence_rows,
    }
    with open(os.path.join(H, "234-capex-characterisation.json"), "w",
              encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    d = r["capex_declaration"]
    print("Core capex, as declared")
    print(f"  display_name : {d['display_name']}")
    print(f"  definition   : {d['semantic_definition']}")
    print(f"  declared     : {d['declared_concepts']}\n")
    for concept, row in r["candidates"].items():
        print(f"{concept}")
        print(f"  SEC label : {row['sec_label']}")
        print(f"  declared  : {row['declared_for_capex']}")
        print(f"  filers    : {row['filer_count']}  periods {row['total_periods']}"
              f"  accessions {row['total_accessions']}  units {row['units']}")
        if row["wording_deserving_attention"]:
            print(f"  ~ wording worth reading: "
                  f"{row['wording_deserving_attention']}")
        print(f"  definition: {(row['sec_definition'] or '(none)')[:300]}")
        silent_reports = [t for t, f in row["per_filer"].items()
                          if f["capex_status"] == "SOURCE_SILENT"]
        if silent_reports:
            print(f"  filers whose capex is SOURCE_SILENT and report it: "
                  f"{sorted(silent_reports)}")
        print()
    print("measured relationships between candidates")
    for pair, row in r["measured_relationships"].items():
        if not row["per_filer"]:
            print(f"  {pair}\n      no filer reports both")
            continue
        print(f"  {pair}\n      filers with both: "
              f"{row['filers_reporting_both']}\n"
              f"      comparable periods {row['comparable_periods_total']}: "
              f"{row['relationship_kinds']}")
        # `r` is the result dict; the loop variable must not shadow it, which it
        # did -- and the failure appeared as a KeyError three hundred lines away
        # from the assignment that caused it.
        for filer in row["per_filer"]:
            print(f"        {filer['ticker']:<14} {filer['relationships']}")
    print()
    silent_filers = sorted(r["silence_check"])
    print(f"capex = SOURCE_SILENT filers with a document on disk: "
          f"{len(silent_filers)}")
    interesting = {
        t: row["unmapped_capex_shaped"] for t, row in r["silence_check"].items()
        if row["unmapped_capex_shaped"]
    }
    print(f"  of those, reporting an unmapped capex-shaped concept: "
          f"{len(interesting)}")
    for ticker, concepts in sorted(interesting.items()):
        model = r["silence_check"][ticker]["business_model"]
        print(f"    {ticker:<7} {model:<18} {concepts}")
    for ticker, row in r["silence_check"].items():
        print(f"  {ticker:<7} {row['business_model']:<18} unmapped "
              f"capex-shaped: {row['unmapped_capex_shaped'] or 'none'}")
    with open(os.path.join(H, "234-capex-characterisation.json"),
              encoding="utf-8") as handle:
        result = json.load(handle)