"""
2.30 -- `us-gaap:ShortTermBorrowings` against the current side of `debt`.

One candidate. No search, no shortlist.

2.29 established Proposition A -- the four concepts mapped to `debt` appear in
none of the 29 filers that report nothing for it -- and left Proposition B
UNDECIDED: whether some unmapped concept is a corresponding representation of
Core `debt`. This tests exactly one candidate against Proposition B.

    Proposition C
    `us-gaap:ShortTermBorrowings` has sufficient evidence to be treated as a
    *current-side candidate* for the `debt` composition.

**It is not "does it equal `LongTermDebtCurrent`".** Those are two different
quantities and the difference is the point:

    ShortTermBorrowings    all borrowings with initial terms under one year --
                           commercial paper, notes payable, the current portion
                           of long-term debt, and whatever else is short-dated
    LongTermDebtCurrent    the portion of *long-term* debt falling due within a
                           year -- one slice of long-term debt, not of all debt

Both are current liabilities. They are not the same quantity, and a
greater-than relationship is the *expected* result rather than a refutation. So
the pre-registered support condition is about **accounting identity**, not
equality:

  1. the candidate's own SEC definition denotes an outstanding carrying amount
  2. period shape, unit and basis are compatible with a debt balance
  3. where a declared current-side concept coexists, the relationship to it is
     the one their definitions imply, and it is reproducible across filers and
     periods
  4. **no competing interpretation explains the same observations better** --
     including the reading that the candidate belongs to the parent `debt` rather
     than to its current side

Condition 4 is the one that can move the answer, so it is measured rather than
asserted: the candidate is also compared against the *whole* composition
(current + noncurrent), which is what "it is the parent, not the current side"
would look like.

Read-only. No mapping, registry entry, coverage status or applicability rule is
changed, and nothing is fetched.
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
from coverage_semantics import scoped_ledger  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402
# Issuer identity comes from the payload's own `cik`; see
# issuer_identity.py for why the filename is a diagnostic only.
import issuer_identity  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

CANDIDATE = "us-gaap:ShortTermBorrowings"
ARCHIVES = ["snapshot-227-a1", "snapshot-227-b", "snapshot-banks2",
            "snapshot-fs", "snapshot-ins-min"]
PAYLOAD_DIRS = ["bulkfacts-227a-orig", "bulkfacts-227b", "bulkfacts-ins-min",
                "bulkfacts-fs", "bulkfacts-banks-2", "inventory", "bulkfacts",
                "bulkfacts-banks"]

# Concepts that describe a *current* liability, for the alignment test. The
# declared current side comes first and is the one that carries the proposition;
# the rest are context and are labelled as such.
DECLARED_CURRENT_SIDE = ["us-gaap:LongTermDebtCurrent",
                         "ifrs-full:CurrentPortionOfLongtermBorrowings"]
DECLARED_NONCURRENT_SIDE = ["us-gaap:LongTermDebtNoncurrent",
                             "ifrs-full:LongtermBorrowings"]
# Other current-liability concepts, used only to see whether the candidate
# coexists with something current-side at all.
OTHER_CURRENT = ["us-gaap:DebtCurrent", "us-gaap:NotesPayableCurrent",
                 "us-gaap:ShortTermBankLoansAndNotesPayable",
                 "us-gaap:LongTermDebtAndCapitalLeaseObligationsCurrent",
                 "us-gaap:ShortTermNonBankLoansAndNotesPayable"]


def documents():
    out = {}
    for d in PAYLOAD_DIRS:
        p = os.path.join(H, d)
        if not os.path.isdir(p):
            continue
        out.update(issuer_identity.load_companyfacts_payloads(p, harness_dir=H)[0])
    return out


def filed_under(path):
    """The forms a document's facts actually come from."""
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    forms = Counter()
    for concepts in (doc.get("facts") or {}).values():
        for body in concepts.values():
            for rows in (body.get("units") or {}).values():
                for r in rows:
                    if r.get("form"):
                        forms[r["form"]] += 1
    return forms


def facts_of(path, concept):
    """Every fact for one concept, as {period_end: (value, unit, accessions)}."""
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    out = {}
    for taxonomy, concepts in (doc.get("facts") or {}).items():
        body = concepts.get(concept.split(":")[-1]) if concept.startswith(
            taxonomy + ":") else None
        if not body:
            continue
        label, desc = body.get("label"), body.get("description")
        for unit, rows in (body.get("units") or {}).items():
            for r in rows:
                if not r.get("end"):
                    continue
                key = str(r["end"])
                prev = out.get(key)
                val = r.get("val")
                # Multiple values for one period is dimension flattening, and it
                # makes the period unusable for an identity comparison.
                if prev and prev[0] != val:
                    out[key] = (None, unit, prev[2] | {r.get("accn")}, "AMBIGUOUS")
                elif prev:
                    out[key] = (prev[0], unit, prev[2] | {r.get("accn")}, prev[3])
                else:
                    out[key] = (val, unit, {r.get("accn")}, None)
        return out, label, desc
    return out, None, None


def main():
    docs = documents()

    # Which of the 63 full-scope filers report the candidate at all.
    holders, silent_for_debt = {}, {}
    for name in ARCHIVES:
        path = os.path.join(H, f"{name}.sqlite")
        if not os.path.exists(path):
            continue
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        registry = CoreRegistry(c)
        for row in c.execute("SELECT asset_id, ticker FROM assets"):
            asset_id, ticker = str(row["asset_id"]), str(row["ticker"]).upper()
            led = scoped_ledger(c, registry, asset_id, ticker)
            debt = next(r for r in led["rows"] if r["metric"] == "debt")
            if ticker in holders:
                continue
            doc = docs.get(ticker)
            if not doc:
                continue
            cand, _, _ = facts_of(doc, CANDIDATE)
            if cand:
                holders[ticker] = {
                    "business_model": led["business_model"] or "UNCLASSIFIED",
                    "debt_status": debt["status"],
                    "debt_observations": debt["observations_held"],
                    "periods": len(cand),
                }
            if debt["status"] in ("SOURCE_SILENT", "DELIBERATELY_DECLINED"):
                silent_for_debt[ticker] = holders.get(ticker)
        c.close()

    # Conditions 1 and 2: what the payload says the concept is. Read the
    # comparator's own definition from a document that actually carries it --
    # sampling it from a document that lacks the concept yields nothing, which is
    # how the first run reported a null comparator.
    sample_doc = next((docs[t] for t in sorted(holders)), None)
    cand_all, label, description = (facts_of(sample_doc, CANDIDATE)
                                    if sample_doc else ({}, None, None))
    comparator_doc = next(
        (docs[t] for t in sorted(holders)
         if facts_of(docs[t], DECLARED_CURRENT_SIDE[0])[0]), None)
    _, cur_label, cur_desc = (
        facts_of(comparator_doc, DECLARED_CURRENT_SIDE[0])
        if comparator_doc else ({}, None, None))

    supporting_language = ("carrying amount", "carrying value", "outstanding",
                           "debt having initial terms")
    disqualifying = ("capacity", "available to be borrowed", "unused",
                     "payment", "repayment", "proceeds", "ratio",
                     "fair value", "face amount")

    def verdict_language(text):
        if not text:
            return "no_description"
        low = text.lower()
        hits = [p for p in supporting_language if p in low]
        bad = [p for p in disqualifying if p in low]
        if bad:
            return f"disqualifying language: {bad}"
        if hits:
            return f"supporting language: {hits}"
        return "no supporting or disqualifying language"

    # Condition 3 and 4: the value relationship, per filer and per period.
    relationships = Counter()
    per_filer = {}
    for ticker in sorted(holders):
        doc = docs[ticker]
        cand, _, _ = facts_of(doc, CANDIDATE)
        current, _, _ = facts_of(doc, DECLARED_CURRENT_SIDE[0])
        other_current, _, _ = facts_of(doc, OTHER_CURRENT[0])
        whole = {}
        for concept in DECLARED_CURRENT_SIDE + DECLARED_NONCURRENT_SIDE:
            got, _, _ = facts_of(doc, concept)
            for period, (val, unit, accs, amb) in got.items():
                if val is None:
                    whole[period] = None
                    continue
                whole[period] = (None if whole.get(period) is None
                                 else whole[period] + val)
        rows = []
        for period in sorted(set(cand) & set(current)):
            cv, cu, _, camb = cand[period]
            xv, xu, _, xamb = current[period]
            if cv is None or xv is None or camb or xamb:
                rows.append({"period_end": period, "usable": False,
                             "why": "dimension-ambiguous on one side"})
                continue
            if cu != xu:
                rows.append({"period_end": period, "usable": False,
                             "why": f"unit differs: {cu} vs {xu}"})
                continue
            if cv == xv:
                rel = "equal"
            elif cv > xv:
                rel = "candidate_greater"
            else:
                rel = "candidate_less"
            relationships[rel] += 1
            rows.append({"period_end": period, "usable": True,
                         "candidate": cv, "declared_current_side": xv,
                         "ratio": round(cv / xv, 4) if xv else None,
                         "relationship": rel,
                         "candidate_vs_whole_composition":
                             (round(cv / whole[period], 4)
                              if whole.get(period) else None)})
        per_filer[ticker] = {
            "business_model": holders[ticker]["business_model"],
            "debt_status": holders[ticker]["debt_status"],
            "candidate_periods": len(cand),
            "co_reported_with_declared_current_side": len(set(cand) & set(current)),
            "co_reported_with_any_other_current_concept":
                len(set(cand) & set(other_current)),
            "usable_comparable_periods": sum(1 for x in rows if x["usable"]),
            "relationships": rows,
        }

    usable = sum(relationships.values())
    equal = relationships.get("equal", 0)
    greater = relationships.get("candidate_greater", 0)
    less = relationships.get("candidate_less", 0)
    # "Reproducible" has to mean *directional*, not merely present. A candidate
    # that is sometimes equal to, sometimes above and sometimes below the
    # comparator has no stable accounting identity with it, and counting its
    # presence as reproducibility would turn the absence of a finding into one.
    dominant = max(equal, greater, less)
    dominant_share = dominant / usable if usable else 0.0
    filers_compared = len([
        t for t, v in per_filer.items() if v["usable_comparable_periods"]])

    conditions = {}
    conditions["1_definition_denotes_outstanding_carrying_amount"] = (
        "supporting" in verdict_language(description))
    conditions["2_period_unit_and_basis_compatible"] = bool(usable)
    conditions["3_relationship_reproducible"] = bool(
        usable and dominant_share >= 0.9 and filers_compared >= 2)
    # Condition 4: the competing reading is that the candidate is the parent
    # rather than the current side. If the candidate sits at or above the
    # comparator everywhere, "all short-term borrowings" is a coherent reading --
    # and it is a *different* one from the proposition, so it wins.
    competing = bool(
        usable and greater + equal == usable and greater > 0)
    conditions["4_no_competing_interpretation_explains_it_better"] = not competing

    failed = [k for k, ok in conditions.items() if not ok]
    if not failed:
        verdict = "SUPPORTED"
    elif conditions["1_definition_denotes_outstanding_carrying_amount"] is False:
        verdict = "REFUTED"
    else:
        verdict = "UNDECIDED"

    result = {
        "proposition_C": {
            "statement": "us-gaap:ShortTermBorrowings has sufficient evidence "
                         "to be treated as a current-side candidate for the "
                         "`debt` composition.",
            "not_asked": "whether it equals us-gaap:LongTermDebtCurrent. They "
                         "are different quantities and a greater-than "
                         "relationship is the expected result, not a refutation.",
            "verdict": verdict,
            "conditions": conditions,
            "conditions_failed": failed,
        },
        "candidate": {
            "concept": CANDIDATE, "taxonomy": "us-gaap",
            "label": label, "definition": description,
            "definition_verdict": verdict_language(description),
            "declared_current_side_comparator": {
                "concept": DECLARED_CURRENT_SIDE[0],
                "label": cur_label, "definition": cur_desc,
            },
        },
        "population": {
            "full_scope_filers_with_a_payload": len(docs),
            "filers_reporting_the_candidate": len(holders),
            "filers_reporting_it_that_are_silent_for_debt": len([
                t for t, v in holders.items()
                if v["debt_status"] in ("SOURCE_SILENT",
                                        "DELIBERATELY_DECLINED")]),
        },
        "comparison": {
            "relationships": dict(relationships),
            "comparable_periods_total": sum(relationships.values()),
            "filers_with_comparable_periods": len([
                t for t, v in per_filer.items() if v["usable_comparable_periods"]]),
            "dominant_relationship": (
                max((("equal", equal), ("candidate_greater", greater),
                     ("candidate_less", less)), key=lambda kv: kv[1])[0]
                if usable else None),
            "dominant_share": round(dominant_share, 4) if usable else None,
            "competing_interpretation_holds": competing,
            "note": "a candidate that exceeds the declared current side in "
                    "every comparable period is consistent with 'all "
                    "short-term borrowings', which is a broader quantity than "
                    "the current portion of long-term debt",
        },
        "per_filer": per_filer,
    }
    with open(os.path.join(H, "230-short-term-borrowings.json"), "w",
              encoding="utf-8") as h:
        json.dump(result, h, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    pc = r["proposition_C"]
    print("PROPOSITION C:", pc["verdict"])
    print(" ", pc["statement"])
    print("  failed conditions:", pc["conditions_failed"])
    print()
    for k, ok in pc["conditions"].items():
        print(f"   {'PASS' if ok else 'FAIL'}  {k}")
    print()
    c = r["candidate"]
    print(f"  {c['concept']}: {c['label']}")
    print(f"    {c['definition']}")
    print(f"    -> {c['definition_verdict']}")
    comp = c["declared_current_side_comparator"]
    print(f"  comparator {comp['concept']}: {comp['label']}")
    print(f"    {comp['definition']}")
    print()
    p = r["population"]
    print(f"  filers with a payload {p['full_scope_filers_with_a_payload']}, "
          f"reporting the candidate {p['filers_reporting_the_candidate']}, "
          f"of which silent for debt "
          f"{p['filers_reporting_it_that_are_silent_for_debt']}")
    cm = r["comparison"]
    print(f"  comparable periods {cm['comparable_periods_total']} across "
          f"{cm['filers_with_comparable_periods']} filers: {cm['relationships']}")
    print(f"  competing reading (candidate is the parent, not the current side) "
          f"holds: {cm['competing_interpretation_holds']}")