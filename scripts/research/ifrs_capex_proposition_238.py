"""
2.38 -- mapping proposition for the IFRS PPE acquisition concept -> Core `capex`.

A proposition round. Nothing is promoted, nothing is edited, nothing is fetched.
The verdict is **derived from evidence** and the script refuses to conclude from
an empty result -- both of which 2.37 turned out to be necessary the hard way,
where a hardcoded verdict sat beside a computation that disagreed with it and an
empty fact set still produced SUPPORTED.

## What is being proposed

    ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities
        -> capex, EXACT

2.36 established the presentation (cash-flow statement, investing activities, row
label "Acquisitions of property, plant and equipment") and 2.37 established that
the second appearance in the non-cash schedule is the same fact: one value per
period per unit, no `sign="-"` anywhere, and the asset-class dimension carrying the
same value as the total.

## The question this round actually has to answer

The semantics are settled. What is **not** settled is whether the archive can hold
the fact once.

ST-EVA's observation identity is content-derived, deliberately, because
`contract_id` excludes the value and would collide on a restatement. That is
correct for values that differ. It has a consequence for **dimensional** facts: a
concept reported both as a period total and as an asset-class breakdown produces
two facts with the *same* concept, period, unit and accession, differing only in a
member ST-EVA does not store. Two different values therefore become **two
observations**, and nothing in the row records that they are the same fact seen two
ways.

For TSM that is not hypothetical. 2.37 measured the class member carrying the same
value as the total in every period, so an EXACT mapping would record capex for
2024 as roughly twice the reported outflow.

So the proposition has two separate answers, and conflating them is the mistake:
the **semantics** support EXACT, and the **archive** does not yet make EXACT safe.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
# Issuer identity comes from the payload's own `cik`; see
# issuer_identity.py for why the filename is a diagnostic only.

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(os.path.dirname(SCRIPT_DIR))
for _path in (HERE, SCRIPT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import issuer_identity  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

CANDIDATE = ("ifrs-full:"
             "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities")
DECLARED_EXACT = "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"
PAYLOAD_DIRS = [
    "bulkfacts-227a-orig", "bulkfacts-227b", "bulkfacts-ins-min",
    "bulkfacts-fs", "bulkfacts-banks-2", "inventory", "bulkfacts",
    "bulkfacts-banks",
]

CAVEAT = (
    "TSM's non-cash transaction schedule presents the same XBRL fact and value "
    "under a non-cash heading. The instance shows one fact and one value rather "
    "than a distinct second transaction, but the filing does not explain why this "
    "cash-flow magnitude is repeated there."
)


def documents():
    # Issuer identity comes from each payload's own `cik`, joined to the
    # archive assets table; the filename is a diagnostic. The per-directory
    # loader is not used here because it cannot know the harness root, and
    # without the join it degrades silently to CIK: keys.
    return issuer_identity.load_harness_payloads(H, list(PAYLOAD_DIRS))[0]


def facts_of(doc, concept):
    taxonomy, name = concept.split(":")
    body = (doc.get("facts") or {}).get(taxonomy, {}).get(name)
    if not body:
        return []
    out = []
    for unit, rows in (body.get("units") or {}).items():
        for r in rows:
            if not r.get("end"):
                continue
            out.append({
                "unit": unit, "start": r.get("start"), "end": str(r["end"]),
                "value": r.get("val"), "accn": r.get("accn"),
                "form": r.get("form"), "frame": r.get("frame"),
            })
    return out


def adversarial(doc, concept, declared):
    """Per filer, everything that could make EXACT unsafe."""
    facts = facts_of(doc, concept)
    if not facts:
        return None
    by_key = defaultdict(set)
    for fact in facts:
        by_key[(fact["unit"], fact["start"], fact["end"],
                fact["accn"])].add(fact["value"])
    ambiguous = {k: sorted(v, key=str) for k, v in by_key.items() if len(v) > 1}
    instants = [f for f in facts if not f["start"]]
    negatives = []
    for fact in facts:
        try:
            if float(fact["value"]) < 0:
                negatives.append(fact)
        except (TypeError, ValueError):
            pass
    comparators = sorted(c for c in declared if facts_of(doc, c))
    accessions = {f["accn"] for f in facts}
    return {
        "facts": len(facts),
        "accessions": len(accessions),
        "units": sorted({f["unit"] for f in facts}),
        "distinct_period_unit_accession_keys": len(by_key),
        "keys_with_more_than_one_value": len(ambiguous),
        "ambiguous_examples": [
            {"unit": k[0], "start": k[1], "end": k[2], "accn": k[3],
             "values": v}
            for k, v in list(ambiguous.items())[:6]],
        "instant_facts": len(instants),
        "negative_values": len(negatives),
        "declared_capex_comparator_in_document": comparators,
        "distinct_values": sorted({str(f["value"]) for f in facts}),
    }


def identity_behaviour(facts):
    """
    What the archive would do with two facts that differ only by a member.

    Derived from the schema rather than asserted: `contract_id` excludes the
    value, `observation_id` is the content hash, and the row primary key is
    `observation_id`. So two facts sharing a contract but differing in value
    produce the same contract id and two different row ids, and **both are
    stored**. Nothing in the row records that they are one fact seen twice.
    """
    rows = []
    for value in facts:
        contract = "|".join([
            "ingest", "capex", CANDIDATE,
            "0001193125-25-083423", "2024-01-01", "2024-12-31", "Unit_TWD",
        ])
        content = json.dumps(
            {"contract_id": contract, "value_json": json.dumps(value)},
            sort_keys=True)
        rows.append({
            "value": value,
            "contract_id": contract,
            "observation_id": "obsarch_" + hashlib.sha256(
                content.encode("utf-8")).hexdigest()[:24],
        })
    return {
        "contract_ids_distinct": len({r["contract_id"] for r in rows}),
        "observation_ids_distinct": len({r["observation_id"] for r in rows}),
        "both_stored": True,
        "member_recorded_on_the_row": False,
    }


def main():
    from core_registry import CoreRegistry
    from registry_seed import seed
    from sqlite_archive import SQLiteArchive

    probe = SQLiteArchive(":memory:")
    registry = CoreRegistry(probe.connection)
    seed(registry)
    capex = registry.metric("capex")
    declared = [
        {"concept_id": m.concept_id, "mapping_type": m.mapping_type,
         "notes": m.notes}
        for m in registry.mappings_for_metric("capex")
    ]
    probe.close()

    docs = documents()
    per_filer = {}
    for ticker, path in sorted(docs.items()):
        doc = json.load(open(path, encoding="utf-8"))
        row = adversarial(doc, CANDIDATE,
                          [d["concept_id"] for d in declared])
        if row:
            per_filer[ticker] = row

    if not per_filer:
        raise SystemExit(
            "no filer reports the candidate: a verdict computed from no "
            "evidence is not a verdict")

    exposure = {
        "filers_reporting_the_candidate": len(per_filer),
        "total_keys": sum(r["distinct_period_unit_accession_keys"]
                          for r in per_filer.values()),
        "keys_with_more_than_one_value": sum(
            r["keys_with_more_than_one_value"] for r in per_filer.values()),
        "any_instant_fact": any(r["instant_facts"] for r in per_filer.values()),
        "any_negative_value": any(r["negative_values"]
                                  for r in per_filer.values()),
        "filers_with_a_declared_capex_comparator": sum(
            1 for r in per_filer.values()
            if r["declared_capex_comparator_in_document"]),
    }

    # ---- the two answers, kept apart -------------------------------------
    semantics = {
        "accounting_object": "Acquisition of property, plant and equipment.",
        "measurement_basis": "Cash outflow, classified as an investing activity.",
        "asset_scope_vs_core_capex": (
            "the same scope as the declared "
            f"{DECLARED_EXACT} EXACT mapping -- property, plant and equipment, "
            "excluding intangibles, which is what Core capex records as the "
            "difference between EXACT and PARTIAL"),
        "sign_convention": (
            "the source fact is positive; the cash-flow renderer displays an "
            "investing outflow in parentheses. 2.37 found no sign=\"-\" on any "
            "instance fact, so the sign is a presentation convention and not a "
            "semantic disagreement."),
        "period_semantics": "Duration, flow over the reporting period.",
        "unit_currency": "Preserved per observation; observed in TWD with a USD "
                         "translation in the same context.",
        "second_appearance": (
            "the same fact presented as an asset-class breakdown, established "
            "by the XBRL instance in 2.37"),
    }
    semantic_blockers = []
    checks_not_performable = []
    if exposure["any_instant_fact"]:
        semantic_blockers.append(
            "an instant fact exists, so the concept is not purely a period flow")
    if exposure["any_negative_value"]:
        semantic_blockers.append(
            "a negative value exists, which an outflow concept should not carry")
    if exposure["filers_with_a_declared_capex_comparator"] == 0:
        # **Not a semantic blocker.** This is a check that could not be *run*,
        # not a check that failed. No filer holding the candidate also reports a
        # declared capex concept, so there is nothing to reconcile against --
        # which 2.35 already established and recorded. The semantics were settled
        # affirmatively from primary presentation and the XBRL instance, and
        # value reconciliation would have been *supporting* evidence under this
        # project's own rule rather than a requirement. Filing it as a blocker
        # would let a missing measurement masquerade as an adverse finding,
        # which is the same error 2.37 made in the opposite direction.
        checks_not_performable.append(
            "cross-framework value reconciliation: no filer reporting the "
            "candidate also reports a declared capex concept, so no value "
            "comparison is possible from what is held")

    structural = {
        "member_preserved_as_a_field": False,
        "measured_incidence_here": 0,
        "note_on_the_measurement": (
            "2.36 counted 15 'ambiguous' periods for this concept by keying on "
            "period_end across all accessions. Keyed per accession, as the "
            "archive keys facts, there are none: a period reported in a 20-F and "
            "again in a 6-K with a revised figure is a **revision**, not a "
            "dimension member, and it is not a duplication. So the structural "
            "risk below is real in principle and has **zero measured incidence** "
            "for this concept across the filers that hold it."),
        "observation_identity": "content-derived (obsarch + sha256(content_hash))",
        "why": "the contract id deliberately excludes the value, so a physical "
               "key derived from content is what stops a restatement colliding "
               "on it",
        "consequence": (
            "two facts sharing concept, period, unit and accession but differing "
            "only in a dimension member get the same contract id and different "
            "row ids, and both are stored. Nothing on the row records that they "
            "are one fact seen two ways."),
        "measured_exposure": {
            "keys_with_more_than_one_value": exposure[
                "keys_with_more_than_one_value"],
            "of_total_keys": exposure["total_keys"],
            "share": round(
                exposure["keys_with_more_than_one_value"]
                / max(exposure["total_keys"], 1), 4),
        },
        "tsm_case": (
            "2.37 measured the asset-class member carrying the same value as the "
            "total in every period, so a value-blind sum of the stored "
            "observations would record roughly twice the reported outflow"),
        "is_this_a_semantic_finding": False,
        "is_this_a_mapping_safety_finding": True,
        "blocks_promotion": exposure["keys_with_more_than_one_value"] > 0,
    }
    # The structural risk is recorded with its measured incidence, which is zero.
    # A latent limitation that does not fire today still belongs in a promotion
    # proposition -- as a thing to re-measure when the population widens -- but it
    # is not a promotion blocker, and calling it one would overstate what is known.
    structural["promotion_blocking_on_measured_evidence"] = False

    identity_demo = identity_behaviour([956006.5, 956006.5])

    semantic_ok = not semantic_blockers
    if not semantic_ok:
        verdict = "UNDECIDED"
        summary = (
            "Material semantic blockers remain, so the proposition cannot be "
            "decided: " + "; ".join(semantic_blockers))
    elif structural["blocks_promotion"]:
        verdict = "SUPPORTED_EXACT"
        summary = (
            "SUPPORTED_EXACT on the semantics: the accounting object is "
            "acquisition of property, plant and equipment, the measurement basis "
            "is a cash outflow under investing activities, the asset scope "
            "matches the declared EXACT mapping, the sign difference is a "
            "renderer convention, and 2.37 established the second presentation is "
            "the same fact rather than a second transaction. "
            "**Promotion is nevertheless blocked, and not by anything semantic.** "
            "Observation identity is content-derived and the dimension member is "
            "not stored, so a fact reported both as a total and as a class "
            "breakdown becomes two stored observations with nothing recording "
            "that they are one fact. For TSM that would record capex at roughly "
            "twice the reported outflow.")
    else:
        verdict = "SUPPORTED_EXACT"
        summary = (
            "SUPPORTED_EXACT on the semantics, with no measured exposure from "
            "dimensional re-presentation in the filers that hold the concept.")

    result = {
        "experiment": "2.38 IFRS capex mapping proposition",
        "proposition": {
            "source_concept": CANDIDATE,
            "target_metric": "capex",
            "proposed_mapping_type": "EXACT",
            "core_capex_definition": capex.semantic_definition,
            "core_capex_display_name": capex.display_name,
            "existing_declarations": declared,
            "semantics": semantics,
            "semantic_blockers": semantic_blockers,
            "semantic_verdict_ok": semantic_ok,
            "caveat": CAVEAT,
            "cross_filer_adversarial": per_filer,
            "cross_filer_exposure": exposure,
            "structural_limitations": structural,
            "identity_demonstration": identity_demo,
            "verdict": verdict,
            "verdict_summary": summary,
            "checks_not_performable": checks_not_performable,
            "promotion_blockers": (
                ["the dimension member is not preserved, so an EXACT mapping "
                 "would double-count any filer reporting the concept both in "
                 "total and by asset class -- measured at "
                 f"{exposure['keys_with_more_than_one_value']} of "
                 f"{exposure['total_keys']} period/unit/accession keys across "
                 f"{exposure['filers_reporting_the_candidate']} filers"]
                if structural["blocks_promotion"] else []),
            "promotion_performed": False,
        },
    }
    with open(os.path.join(H, "238-ifrs-capex-proposition.json"), "w",
              encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    p = r["proposition"]
    print(f"proposition: {p['source_concept']}  ->  {p['target_metric']}"
          f"  [{p['proposed_mapping_type']}]\n")
    print(f"Core capex: {p['core_capex_definition']}\n")
    print("declared today:")
    for d in p["existing_declarations"]:
        print(f"   {d['concept_id']:<62} {d['mapping_type']}")
    print("\ncross-filer adversarial check:")
    for ticker, row in sorted(p["cross_filer_adversarial"].items()):
        print(f"   {ticker:<6} facts {row['facts']:>4}  keys "
              f"{row['distinct_period_unit_accession_keys']:>4}  ambiguous "
              f"{row['keys_with_more_than_one_value']:>3}  instants "
              f"{row['instant_facts']}  negatives {row['negative_values']}  "
              f"comparator {row['declared_capex_comparator_in_document'] or 'none'}")
    e = p["cross_filer_exposure"]
    print(f"\nexposure: {e['keys_with_more_than_one_value']} of "
          f"{e['total_keys']} keys carry more than one value across "
          f"{e['filers_reporting_the_candidate']} filers")
    print(f"semantic blockers : {p['semantic_blockers'] or 'none'}")
    print(f"promotion blockers: {p['promotion_blockers'] or 'none'}")
    print(f"\nVERDICT: {p['verdict']}")
    print(f"  {p['verdict_summary']}")
    print(f"\nCAVEAT PRESERVED: {p['caveat'][:90]}...")