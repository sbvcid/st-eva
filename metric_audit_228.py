"""
2.28 Core Metric Empirical Audit -- metric-centric, offline, repository only.

2.27 answered what filers of different business models report. This asks the
other question: for each of the twenty Core metrics, **what does that metric
actually represent in the Evidence world?**

Per metric, from the 63 full-scope filers:

    collected rate, and SOURCE_SILENT pattern by business model
    which concepts actually produce the facts, and their mapping types
    dimension ambiguity, at the metric x concept grain
    declared-date share -- PIT precision that varies by filer for one metric
    declared decompositions, and whether a component is held anywhere
    what the corpus already established about it

and then a **research classification** into five descriptive categories. The
categories are a partition, not a rating: there is no ordering and no
best-to-worst, and nothing here changes the registry, a mapping, a decline or an
applicability policy.

    A  broad and consistently observable
    B  broad, but how the source represents it varies
    C  collection exists and the mapping or decomposition is suspect
    D  genuinely model-specific in what gets reported
    E  insufficient evidence in this corpus to say

Read-only against archives that already exist. Nothing is written to any archive.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry  # noqa: E402
from coverage_semantics import scoped_ledger  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

# The five full-scope archives, in the order 2.27 combined them.
ARCHIVES = [
    ("cohort A1 (2.27)", os.path.join(H, "snapshot-227-a1.sqlite")),
    ("cohort B (2.27)", os.path.join(H, "snapshot-227-b.sqlite")),
    ("BANK (2.17-2.24)", os.path.join(H, "snapshot-banks2.sqlite")),
    ("FINANCE_SERVICES (2.25)", os.path.join(H, "snapshot-fs.sqlite")),
    ("MINING+INSURANCE (2.23)", os.path.join(H, "snapshot-ins-min.sqlite")),
]
SEED_ARCHIVE = os.path.join(H, "snapshot-227-b.sqlite")

CATEGORIES = {
    "A": "broad and consistently observable",
    "B": "broad, but how the source represents it varies",
    "C": "collection exists and the mapping or decomposition is suspect",
    "D": "genuinely model-specific in what gets reported",
    "E": "insufficient evidence in this corpus to say",
}


def seed_registry():
    """A seeded in-memory registry, for the mapping and decline declarations."""
    from registry_seed import seed
    from sqlite_archive import SQLiteArchive

    probe = SQLiteArchive(":memory:")
    registry = CoreRegistry(probe.connection)
    seed(registry)
    return probe, registry


def declared():
    """What the registry says about each metric, independent of any archive."""
    probe, registry = seed_registry()
    out = {}
    for metric in registry.metrics():
        mappings = [
            {"concept_id": m.concept_id, "mapping_type": m.mapping_type}
            for m in registry.mappings_for_metric(metric.metric_id)
        ]
        declines = [
            {"concept_id": d["concept_id"],
             "considered_for_metric": d["considered_for_metric"],
             "reason_code": d["reason_code"],
             "framework_basis": d["framework_basis"]}
            for d in registry.declines_for_metric(metric.metric_id)
        ]
        out[metric.metric_id] = {
            "normal_period_type": metric.normal_period_type,
            "comparability_group": metric.comparability_group,
            "unit_family": metric.unit_family,
            "mappings": mappings,
            "declines": declines,
            "inapplicable_in": list(metric.inapplicable_in),
            "exclusions": [
                {"business_model": m, "state": s}
                for m, s, _ in getattr(metric, "exclusions", ())
            ],
        }
    probe.close()
    return out


def observed():
    """What the 63 full-scope filers actually hold."""
    per_metric = defaultdict(lambda: {
        "status": Counter(),
        "silent_by_model": Counter(),
        "collected_by_model": Counter(),
        "issuers_by_model": Counter(),
        "concepts": Counter(),
        "observations": 0,
        "periods": set(),
        "declared_dates": 0,
        "collisions": 0,
        "collision_max_values": 0,
        "issuers_with_evidence": set(),
        "instances": 0,
    })
    models = {}

    for label, path in ARCHIVES:
        if not os.path.exists(path):
            continue
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        registry = CoreRegistry(c)
        for row in c.execute("SELECT asset_id, ticker FROM assets"):
            asset_id, ticker = str(row["asset_id"]), str(row["ticker"]).upper()
            led = scoped_ledger(c, registry, asset_id, ticker)
            model = led["business_model"] or "UNCLASSIFIED"
            models[ticker] = model
            for cell in led["rows"]:
                metric = cell["metric"]
                slot = per_metric[metric]
                slot["status"][cell["status"]] += 1
                slot["instances"] += 1
                slot["issuers_by_model"][model] += 1
                if cell["status"] == "SOURCE_SILENT":
                    slot["silent_by_model"][model] += 1
                else:
                    slot["collected_by_model"][model] += 1
                if cell["observations_held"]:
                    slot["issuers_with_evidence"].add(ticker)
                coll = c.execute(
                    "SELECT COUNT(*) n, COALESCE(MAX(distinct_values),0) mx"
                    " FROM ingestion_dimension_collisions"
                    " WHERE asset_id=? AND metric_id=?",
                    (asset_id, metric),
                ).fetchone()
                slot["collisions"] += int(coll["n"])
                slot["collision_max_values"] = max(
                    slot["collision_max_values"], int(coll["mx"]))
        # Observations, concepts and PIT share, read once per archive.
        for row in c.execute(
            "SELECT o.metric AS metric, o.concept AS concept,"
            " o.available_at_basis AS basis, o.period_end AS pe,"
            " a.ticker AS ticker FROM observations o"
            " JOIN assets a ON a.asset_id = o.asset_id"
        ):
            slot = per_metric[row["metric"]]
            slot["observations"] += 1
            slot["concepts"][str(row["concept"])] += 1
            if row["pe"]:
                slot["periods"].add(f"{row['ticker']}|{row['pe']}")
            if row["basis"] == "FILED_AS_OF_DATE":
                slot["declared_dates"] += 1
        c.close()
    return per_metric, models


def probe_evidence():
    """
    Whether a metric's silence is a mapping gap or a reporting fact.

    `debt` is the known case: 2.23 measured that no bank tags any of the four
    concepts the registry maps to it, while banks plainly report debt. Asking the
    raw `companyfacts` documents -- not the archive -- is what separates "the
    registry cannot see it" from "the filer did not report it", and the two need
    different categories because only one of them is a mapping question.

    Read from a probe run offline against the stored payloads. If it is absent
    the classification falls back on the archive evidence alone and says so.
    """
    path = os.path.join(H, "228-unmapped-probe.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def classify(metric, decl, obs, probe):
    """
    Place one metric, and say which observations decided it.

    A category is a claim about the evidence, so each one names the numbers that
    produced it. Where the evidence does not reach, the metric is E rather than
    being given the benefit of a guess.

    The one distinction that matters most: **D is a claim about filers and C is a
    claim about the registry.** A metric where most silent filers carry adjacent
    unmapped concepts is a registry question however model-structured its silence
    looks, because the silence may be an artefact of what the registry can see.
    """
    filers = obs["instances"]
    silent = obs["status"].get("SOURCE_SILENT", 0)
    declined = obs["status"].get("DELIBERATELY_DECLINED", 0)
    unmapped = obs["status"].get("MAPPED_NO_CURRENT_OBSERVATION", 0)
    collected = obs["status"].get("COLLECTED", 0)
    rate = round(collected / filers, 4) if filers else None

    silent_by_model = dict(obs["silent_by_model"])
    all_collected = collected == filers
    all_silent = silent == filers
    nothing = collected == 0

    # A component whose parent holds its facts shows up as
    # MAPPED_NO_CURRENT_OBSERVATION rather than as absence, so the counts below
    # are what distinguishes "the registry cannot see it" from "the filer did not
    # report it".
    model_silence = {}
    for model in obs["issuers_by_model"]:
        n = obs["issuers_by_model"][model]
        model_silence[model] = round(silent_by_model.get(model, 0) / n, 3)
    spread = (max(model_silence.values()) - min(model_silence.values())
              if model_silence else 0)
    mapping_suspect = False

    reasons = []
    if nothing:
        reasons.append("no filer in 63 holds an observation")
    if unmapped:
        reasons.append(
            f"{unmapped} filers report MAPPED_NO_CURRENT_OBSERVATION, which "
            f"for a declared composition means the facts are held under the "
            f"parent metric rather than absent")
    if obs["collisions"]:
        reasons.append(
            f"{obs['collisions']} dimension-collision rows across the corpus, "
            f"up to {obs['collision_max_values']} distinct values on one key")
    if len(obs["concepts"]) > 1:
        reasons.append(
            f"{len(obs['concepts'])} distinct concepts produce this metric "
            f"({', '.join(f'{k} x{v}' for k, v in obs['concepts'].most_common(3))})")
    if spread >= 0.6:
        reasons.append(
            f"SOURCE_SILENT rate varies {spread:.2f} across business models "
            f"({model_silence})")
    if obs["declared_dates"]:
        reasons.append(
            f"{round(100.0 * obs['declared_dates'] / obs['observations'], 1)}% "
            f"of its observations carry a filed date rather than an acceptance "
            f"instant")
    probe_for_metric = (probe or {}).get(metric)
    if probe_for_metric:
        silent_n = probe_for_metric["silent_or_declined_filers"]
        adjacent_n = probe_for_metric["filers_with_adjacent_unmapped_concepts"]
        if silent_n and adjacent_n:
            share = round(adjacent_n / silent_n, 3)
            reasons.append(
                f"{adjacent_n} of {silent_n} filers that report nothing for this "
                f"metric carry adjacent concepts the registry does not map, "
                f"checked against the raw companyfacts rather than the archive")
            if share >= 0.5:
                reasons.append(
                    "adjacency is a question, not a conclusion: many of these are "
                    "cash-flow movements rather than stocks, so whether a "
                    "mapping is warranted is a proposition to formulate")
                mapping_suspect = True

    # ---- the partition -------------------------------------------------
    if nothing:
        category = "C" if (unmapped or declined) else "E"
    elif unmapped and collected < filers * 0.7:
        # A declared composition whose components are not separately held.
        category = "C"
    elif mapping_suspect:
        # Silence that may be the registry's blind spot rather than the filer's.
        category = "C"
    elif all_collected and obs["collisions"] == 0 and not obs["declared_dates"]:
        category = "A"
    elif all_collected and (obs["collisions"] or obs["declared_dates"]):
        category = "B"
    elif spread >= 0.6:
        category = "D"
    elif obs["collisions"] or len(obs["concepts"]) > 2:
        category = "B"
    else:
        category = "A"
    return category, {
        "collected_rate": rate,
        "status_counts": dict(sorted(obs["status"].items())),
        "source_silent_rate_by_model": model_silence,
        "concepts": dict(obs["concepts"].most_common()),
        "declaration": decl,
        "observations": obs["observations"],
        "filers_with_evidence": len(obs["issuers_with_evidence"]),
        "declared_date_share_pct": (
            round(100.0 * obs["declared_dates"] / obs["observations"], 1)
            if obs["observations"] else None),
        "dimension_collision_rows": obs["collisions"],
        "max_distinct_values_one_key": obs["collision_max_values"],
        "unmapped_probe": ({
            "silent_or_declined_filers":
                probe_for_metric["silent_or_declined_filers"],
            "with_adjacent_unmapped_concepts":
                probe_for_metric["filers_with_adjacent_unmapped_concepts"],
        } if probe_for_metric else None),
        "reasons": reasons,
    }


def main():
    decl = declared()
    probe = probe_evidence()
    per_metric, models = observed()
    audit = {}
    for metric in sorted(decl):
        if metric not in per_metric:
            per_metric[metric] = {
                "status": Counter(), "silent_by_model": Counter(),
                "collected_by_model": Counter(), "issuers_by_model": Counter(),
                "concepts": Counter(), "observations": 0, "periods": set(),
                "declared_dates": 0, "collisions": 0,
                "collision_max_values": 0, "issuers_with_evidence": set(),
                "instances": 0,
            }
        category, detail = classify(metric, decl[metric],
                                    per_metric[metric], probe)
        audit[metric] = {"category": category,
                         "category_meaning": CATEGORIES[category], **detail}

    result = {
        "audit": "2.28 Core Metric Empirical Audit",
        "corpus": {
            "filers": len(models),
            "sources": [label for label, _ in ARCHIVES],
            "denominator": "20 Core metrics x every full-scope filer",
        },
        "categories": CATEGORIES,
        "category_note": "a descriptive partition, not a rating; no ordering "
                         "and no best-to-worst",
        "by_category": {
            code: sorted(m for m, v in audit.items() if v["category"] == code)
            for code in sorted(CATEGORIES)
        },
        "metrics": audit,
    }
    with open(os.path.join(H, "228-metric-audit.json"), "w",
              encoding="utf-8") as h:
        json.dump(result, h, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    print(f"corpus: {r['corpus']['filers']} full-scope filers\n")
    for code, meaning in r["categories"].items():
        print(f"  {code}  {meaning}")
        for m in r["by_category"][code]:
            v = r["metrics"][m]
            print(f"      {m:<32} collected {v['collected_rate']}"
                  f"  collisions {v['dimension_collision_rows']:>5}"
                  f"  declared {v['declared_date_share_pct']}%"
                  f"  concepts {len(v['concepts'])}")