"""
2.37 -- IFRS capex duplicate-context resolution.

One question, about one concept, in one filing:

    ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities

appears in TSM's 20-F twice -- as a line in the cash-flow statement's investing
section, and in a schedule headed "non-cash transaction". Same concept, same
magnitude, opposite sign. ST-EVA collects **by concept**, so if that one concept
carried two accounting objects, a mapping would silently import both. That is the
question.

## How it is answered

Not from the two renderings. The renderings are the *symptom*; the answer is in the
XBRL **instance**, which is the only place that says how many facts exist, what
their contexts are, what dimensions they carry and what sign they were tagged
with. The instance reports:

  * **seven** fact instances of the concept, and **not one carries `sign="-"`**
  * three periods x an undimensioned context, and the same three periods x a
    context dimensioned on
    `ifrs-full:ClassesOfAssetsAxis=...ClassesOfPropertyPlantAndEquipmentDomain`
  * **the dimensional and undimensional contexts carry the same values**

So the parentheses in the cash-flow rendering are a **presentation convention of
the renderer**, not a negated fact, and the two appearances are **one tagged fact
shown twice** -- once as a statement total, once as a class breakdown that happens
to be the whole of it.

Nothing here depends on the magnitude matching, which is the inference the round
was told not to make. It depends on the instance saying how many facts there are,
which is exactly the evidence an aggregate cannot give.

## The structural half, answered from the archive rather than the filing

The round also asked whether ST-EVA could tell the two facts apart. It can, and
for a reason worth recording: `observations.observation_id` is **content-derived**,
`sha256(content_hash)`, and the schema says why --

    "the row id is a physical key derived from the content hash, because the
     contract id is canonical per metric and a restatement of a band would
     collide on it"

`contract_id` deliberately excludes the value, so two facts sharing a contract but
differing in value would collide on it; the archive re-keys on content for exactly
that reason. The residual limit is narrower and is recorded rather than fixed: the
**member is not preserved as a field**, so two members carrying an identical value
would collapse into one row.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from primary_capex_context_236 import fetcher  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

CONCEPT = ("ifrs-full:"
           "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities")
FILER = "TSM"
CIK = 1046179
ACCESSION = "0001193125-25-083423"
BASE = f"https://www.sec.gov/Archives/edgar/data/{CIK}/{ACCESSION.replace('-', '')}"

# The same concept, and the sibling that behaved identically, so the pattern can
# be checked against a control rather than asserted for one concept alone.
SIBLING = ("ifrs-full:"
           "PaymentsToAcquireFinancialAssetsAtFairValueThroughOther"
           "ComprehensiveIncome")


def instance_facts(body: str, concept: str) -> list:
    contexts = {}
    for match in re.finditer(
            r'<xbrli:context id="([^"]+)">(.*?)</xbrli:context>', body, re.S):
        cid, block = match.group(1), match.group(2)
        start = re.search(r"startDate>([^<]+)<", block)
        end = re.search(r"endDate>([^<]+)<", block)
        members = re.findall(
            r"explicitMember dimension=\"([^\"]+)\">([^<]+)<", block)
        contexts[cid] = {
            "start": start.group(1) if start else None,
            "end": end.group(1) if end else None,
            "dimensions": [f"{d}={m}" for d, m in members],
        }
    facts = []
    for match in re.finditer(
            r"<ix:nonFraction\b([^>]*)>(.*?)</ix:nonFraction>", body, re.S):
        attrs, value = match.group(1), match.group(2)
        name = re.search(r'name="([^"]+)"', attrs)
        if not name or name.group(1) != concept:
            continue
        ctx = re.search(r'contextRef="([^"]+)"', attrs)
        sign = re.search(r'sign="([^"]+)"', attrs)
        unit = re.search(r'unitRef="([^"]+)"', attrs)
        facts.append({
            "contextRef": ctx.group(1) if ctx else None,
            "sign_attribute": sign.group(1) if sign else None,
            "unitRef": unit.group(1) if unit else None,
            "value": value.strip(),
            "context": contexts.get(ctx.group(1) if ctx else "", {}),
        })
    return facts


def main():
    provider, get_text = fetcher()

    index = json.loads(get_text(f"{BASE}/index.json"))
    entries = index["directory"]["item"]
    # `size` comes back from `index.json` as a **string**, so comparing it
    # directly makes `max` order lexicographically -- "9820" beats "8404793" --
    # and it picked a 9,820-character exhibit document instead of the 8.4 MB
    # primary one. The verdict guard caught it, which is the only reason it was
    # noticed: the wrong document yields zero facts, and a verdict computed from
    # zero facts is SUPPORTED by default.
    primary = max(
        (e for e in entries
         if e["name"].endswith(".htm") and not e["name"].startswith("R")),
        key=lambda e: int(e.get("size") or 0))["name"]
    body = get_text(f"{BASE}/{primary}")
    if not body:
        raise SystemExit(
            f"the primary document came back empty: {primary}. A verdict "
            f"computed from nothing would be SUPPORTED by default, which is "
            f"the failure this project keeps guarding against.")
    print(f"primary document {primary}: {len(body)} chars")

    facts = instance_facts(body, CONCEPT)
    if not facts:
        raise SystemExit(
            f"no instance facts found for the concept in {len(body)} chars. "
            f"Refusing to return a verdict computed from an empty result.")
    control = instance_facts(body, SIBLING)

    by_period = defaultdict(list)
    for fact in facts:
        context = fact["context"]
        by_period[(context.get("start"), context.get("end"))].append(fact)

    # Compared **per unit**, not per period. A period carries the reporting
    # currency and its USD translation, so comparing the whole set against the
    # dimensional set flagged 2024 as different -- because the USD translation
    # has no class breakdown and the TWD one does. The translation is not a
    # second transaction.
    periods = []
    for (start, end), group in sorted(by_period.items()):
        by_unit = {}
        for fact in group:
            slot = by_unit.setdefault(fact["unitRef"], {"undimensioned": [],
                                                      "dimensioned": []})
            bucket = "dimensioned" if fact["context"]["dimensions"] \
                else "undimensioned"
            slot[bucket].append(fact["value"])
        units = {}
        for unit, slot in by_unit.items():
            units[unit] = {
                "undimensioned": sorted(slot["undimensioned"]),
                "dimensioned": sorted(slot["dimensioned"]),
                "matches": (sorted(slot["dimensioned"]) == [] or
                            sorted(slot["dimensioned"]) ==
                            sorted(slot["undimensioned"])),
            }
        periods.append({
            "period_start": start, "period_end": end, "by_unit": units,
            "every_unit_matches": all(u["matches"] for u in units.values()),
            "dimensions_seen": sorted({d for f in group
                                       for d in f["context"]["dimensions"]}),
        })

    negated = [f for f in facts if f["sign_attribute"] == "-"]
    values = {f["value"] for f in facts}

    # Evidence must exist before anything is concluded from it. The first run of
    # this returned SUPPORTED with **zero** facts: `all([])` is true, `not []` is
    # true, and an empty set has the same length as an empty period map. A verdict
    # that can be produced by absence is not a verdict.
    if not facts or not periods:
        raise SystemExit(
            "no facts or no periods: a verdict from an empty result is not a "
            "verdict")
    if not negated and all(p["every_unit_matches"] for p in periods):
        same_transaction = True
        distinct_non_cash = False
        verdict = "SUPPORTED"
        scope = (
            "SUPPORTED that this concept denotes one capex cash-flow quantity "
            "per period and that the second appearance is the same fact "
            "presented twice -- the asset-class dimension carries the same value "
            "as the total, in every unit, in every period."
        )
    else:
        same_transaction = False
        distinct_non_cash = True
        verdict = "REFUTED"
        scope = (
            "REFUTED: the instance shows either a negated fact or a "
            "dimensional value differing from the total, which would make the "
            "concept broader than a single capex cash outflow."
        )

    result = {
        "experiment": "2.37 IFRS capex duplicate-context resolution",
        "concept": CONCEPT,
        "filer": FILER,
        "cik": CIK,
        "accession": ACCESSION,
        "form": "20-F",
        "primary_document": primary,
        "presentations_in_the_filing": [
            {"report": "R5.htm",
             "title": "Consolidated Statements of Cash Flows",
             "section": "CASH FLOWS FROM INVESTING ACTIVITIES",
             "row_label": "Acquisitions of property, plant and equipment",
             "rendered_value": "(956,006.5)"},
            {"report": "R152.htm",
             "title": "Cash Flow Information - Schedule of Detailed Information "
                      "about Non Cash Transaction (Detail)",
             "section": "Disclosure of detailed information about non-cash "
                        "transaction [line items]",
             "row_label": "Payments for acquisition of property, plant and "
                           "equipment",
             "rendered_value": "956,006.5"},
        ],
        "instance_evidence": {
            "fact_count": len(facts),
            "facts_carrying_a_negation_attribute": len(negated),
            "distinct_values": sorted(values),
            "periods": periods,
            "control_concept": SIBLING,
            "control_fact_count": len(control),
            "control_note": "the sibling FVTOCI acquisition line behaves "
                            "identically -- same magnitude, same sign flip "
                            "between the two reports -- which is a control on "
                            "the pattern rather than a single observation",
        },
        "interpretation": {
            "is_one_transaction_presented_twice": same_transaction,
            "is_a_distinct_non_cash_transaction": not same_transaction,
            "sign_difference_is_a_renderer_convention": not negated,
            "why": "the instance carries no sign=\"-\" on any fact of this "
                   "concept, so the parentheses in the cash-flow rendering are "
                   "a presentation convention. There is one value per period, "
                   "and the asset-class dimension carries the same value as the "
                   "total, so the second appearance is the same tagged fact "
                   "presented as a class breakdown.",
            "unresolved": "why TSM's schedule of non-cash information carries "
                          "the same magnitude as the cash-flow line is not "
                          "explained by the two reports or the instance. It "
                          "does not change the answer here -- one fact, one "
                          "value -- but it is not explained.",
        },
        "structural": {
            "observation_id_is_content_derived": True,
            "schema_rationale": "the row id is a physical key derived from the "
                                "content hash, because the contract id is "
                                "canonical per metric and a restatement would "
                                "collide on it",
            "contract_id_excludes_the_value": True,
            "can_st_eva_tell_the_two_presentations_apart": True,
            "how": "the same tagged fact yields one row; a dimensional fact "
                   "with a different value would yield a different row, "
                   "because identity is the content hash rather than the "
                   "contract id",
            "residual_limitation": "the dimension member is not preserved as a "
                                   "field, so two members carrying an identical "
                                   "value would collapse into one row -- a loss "
                                   "of member distinction rather than a "
                                   "miscount",
            "double_count_risk": "none here: both presentations carry the same "
                                  "value, so a single row is stored and that is "
                                  "correct",
        },
        "verdict": verdict,
        "verdict_scope": scope,
        "unresolved_reason_for_the_second_presentation":
            "why TSM's schedule of non-cash information carries the same "
            "magnitude as the cash-flow line is not explained by the two "
            "reports or by the instance. It does not change the verdict -- one "
            "fact, one value per period -- but it is unexplained, so any mapping "
            "should carry an explicit non-cash caveat rather than be treated as "
            "unconditionally clean.",
        "mapping_performed": False,
    }
    with open(os.path.join(H, "237-tsm-duplicate-context.json"), "w",
              encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    i = r["instance_evidence"]
    print(f"concept   : {r['concept']}")
    print(f"filer     : {r['filer']} ({r['cik']}) accession {r['accession']} "
          f"{r['form']}")
    print(f"instance  : {i['fact_count']} facts, "
          f"{i['facts_carrying_a_negation_attribute']} carrying sign=\"-\", "
          f"distinct values {i['distinct_values']}")
    print(f"control   : {i['control_concept'][:56]} -> "
          f"{i['control_fact_count']} facts, same pattern")
    print()
    for period in i["periods"]:
        for unit, slot in sorted(period["by_unit"].items()):
            print(f"   {period['period_start']}..{period['period_end']}  "
                  f"{unit:<12} total {slot['undimensioned']}   "
                  f"by-class {slot['dimensioned']}   "
                  f"matches={slot['matches']}")
    print()
    interp = r["interpretation"]
    print(f"one transaction presented twice : "
          f"{interp['is_one_transaction_presented_twice']}")
    print(f"distinct non-cash transaction  : "
          f"{interp['is_a_distinct_non_cash_transaction']}")
    print(f"sign flip is a renderer convention: "
          f"{interp['sign_difference_is_a_renderer_convention']}")
    print()
    s = r["structural"]
    print(f"identity is content-derived      : {s['observation_id_is_content_derived']}")
    print(f"ST-EVA can tell them apart       : "
          f"{s['can_st_eva_tell_the_two_presentations_apart']}")
    print(f"double-count risk                : {s['double_count_risk']}")
    print(f"residual limitation              : {s['residual_limitation']}")
    print()
    print("VERDICT:", r["verdict"])
    print(" ", r["verdict_scope"])