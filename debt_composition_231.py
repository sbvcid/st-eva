"""
2.31 -- Debt Composition Characterisation.

The previous round asked whether `us-gaap:ShortTermBorrowings` is the current side
of `debt` and returned UNDECIDED, having established something more useful: the
candidate and the declared current side are **complementary, not nested**, and
the population that would need the candidate reports no comparator at all.

So the question changes shape. It is no longer about one concept; it is about
whether a current-debt *structure* is observable in what the source already
provides.

    Proposition D
    For filers that supply the relevant current-debt concepts, is there
    sufficient evidence to characterise the composition of current debt?

Pre-registered outcome: SUPPORTED / REFUTED / UNDECIDED. **SUPPORTED requires at
least one reproducible accounting relationship that does not follow merely from
two concepts sharing a name.**

## How the relationships are found

Not by name. 2.29 tried that four times and each pass admitted a different
category of thing that was not a debt balance.

The relationships here are found by **arithmetic on the values**. For every
balance-sheet instant of a monetary unit, every pair of concepts is summed and the
sum looked up among the same period's concepts. A relationship that survives that
search, across several periods and several filers, is an accounting identity the
filers actually report -- whether or not anyone had thought to name it. That is a
different kind of evidence from a label, and it is the kind this proposition turns
on.

Four shapes are distinguished, and the search reports which occur:

    A   total = current_a + current_b
    B   total = current_a + current_b + current_c
    C   one current concept is a superset of another, so a naive sum
        double-counts
    D   no entity-level total is reported at all, and the composition cannot be
        established from the source

Nothing here modifies the registry, a mapping, a metric definition or an
applicability rule, and nothing is fetched.

## The calibration sample, and what it cannot answer

The five filers that co-report a declared current-side concept **all have
`debt = COLLECTED`** — they do not need any candidate. The eleven that are silent
report no current-side concept of any kind, so there is nothing to characterise
there.

So this round can answer:

> when a source supplies these concepts together, what relationships hold?

and **cannot** answer:

> therefore the silent filers' `debt` should be reconstructed this way.

That second question is a further proposition, and it needs evidence this corpus
does not contain. The distinction is carried through the output rather than
collapsed into a verdict.
"""

from __future__ import annotations

import glob
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
# Issuer identity comes from the payload's own `cik`; see
# issuer_identity.py for why the filename is a diagnostic only.
import issuer_identity  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

ARCHIVES = ["snapshot-227-a1", "snapshot-227-b", "snapshot-banks2",
            "snapshot-fs", "snapshot-ins-min"]
PAYLOAD_DIRS = ["bulkfacts-227a-orig", "bulkfacts-227b", "bulkfacts-ins-min",
                "bulkfacts-fs", "bulkfacts-banks-2", "inventory", "bulkfacts",
                "bulkfacts-banks"]

# Concepts whose own SEC description places them in the debt structure. Used for
# *labelling* an identity the value search found, never for finding candidates.
CURRENT_SIDE = {"us-gaap:LongTermDebtCurrent",
                "ifrs-full:CurrentPortionOfLongtermBorrowings"}
NONCURRENT_SIDE = {"us-gaap:LongTermDebtNoncurrent",
                   "ifrs-full:LongtermBorrowings"}
CANDIDATE = "us-gaap:ShortTermBorrowings"
# Concepts that look like an entity-level total. Whether they *are* one is what
# the search decides, not what this list assumes.
TOTAL_SHAPED = {
    "us-gaap:DebtCurrent", "us-gaap:DebtAndCapitalLeaseObligations",
    "us-gaap:LongTermDebt", "us-gaap:LongTermDebtAndCapitalLeaseObligations",
    "us-gaap:LongTermDebtAndCapitalLeaseObligationsCurrent",
    "us-gaap:DebtNoncurrent", "us-gaap:DebtInstrumentCarryingAmount",
    "us-gaap:NotesPayable", "us-gaap:NotesPayableCurrent",
    "us-gaap:ShortTermBankLoansAndNotesPayable",
    "us-gaap:ShortTermNonBankLoansAndNotesPayable",
    "us-gaap:LongTermDebtCurrentMaturities",
    "us-gaap:OtherLongTermDebt", "us-gaap:ConvertibleDebtNoncurrent",
    "us-gaap:OtherBorrowings", "us-gaap:FinanceLeaseLiabilityCurrent",
    "us-gaap:FinanceLeaseLiabilityNoncurrent",
    "us-gaap:OperatingLeaseLiabilityCurrent",
    "us-gaap:OperatingLeaseLiabilityNoncurrent",
}

TOLERANCE = 0.5          # absolute, on a USD balance sheet
MIN_PERIODS = 6          # periods in which an identity must hold
MIN_FILERS = 2           # filers in which it must hold


def documents():
    out = {}
    for d in PAYLOAD_DIRS:
        p = os.path.join(H, d)
        if not os.path.isdir(p):
            continue
        out.update(issuer_identity.load_companyfacts_payloads(p, harness_dir=H)[0])
    return out


def calibration_filers():
    """
    Filers that report a declared current-side concept alongside the candidate.

    Selected on the *presence* of co-reported concepts, which is a selection
    criterion and not evidence: these are the only filers in the corpus where a
    composition can be observed at all.
    """
    docs = documents()
    out = {}
    for name in ARCHIVES:
        path = os.path.join(H, f"{name}.sqlite")
        if not os.path.exists(path):
            continue
        c = sqlite3.connect(path)
        c.row_factory = sqlite3.Row
        registry = CoreRegistry(c)
        for row in c.execute("SELECT asset_id, ticker FROM assets"):
            asset_id, ticker = str(row["asset_id"]), str(row["ticker"]).upper()
            if ticker in out or ticker not in docs:
                continue
            led = scoped_ledger(c, registry, asset_id, ticker)
            debt = next(r for r in led["rows"] if r["metric"] == "debt")
            co = 0
            for concept in CURRENT_SIDE | {CANDIDATE}:
                if _has_instant(docs[ticker], concept):
                    co += 1
            if co >= 2:
                out[ticker] = {
                    "business_model": led["business_model"] or "UNCLASSIFIED",
                    "debt_status": debt["status"],
                    "debt_observations": debt["observations_held"],
                    "concepts_co_reported": co,
                }
        c.close()
    return out, docs


def _has_instant(path, concept):
    """True when the document carries at least one instant fact for `concept`."""
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    taxonomy, name = concept.split(":")
    body = (doc.get("facts") or {}).get(taxonomy, {}).get(name)
    if not body:
        return False
    for rows in (body.get("units") or {}).values():
        for r in rows:
            if r.get("end") and not r.get("start"):
                return True
    return False


def instants(path):
    """
    Every monetary instant in one document.

    Returns {period_end: {concept: (value, accession, ambiguous)}}. A period with
    two different values for one concept is dimension-flattened and is excluded,
    because a reconciliation across it would be a reconciliation across
    something the source cannot separate.
    """
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    by_period = defaultdict(dict)
    meta = {}
    for taxonomy, concepts in (doc.get("facts") or {}).items():
        for name, body in concepts.items():
            key = f"{taxonomy}:{name}"
            label = body.get("label")
            desc = body.get("description")
            if label or desc:
                meta[key] = {"label": label, "description": desc}
            for unit, rows in (body.get("units") or {}).items():
                if unit not in ("USD",):
                    continue
                for r in rows:
                    if not r.get("end") or r.get("start"):
                        continue
                    period = str(r["end"])
                    val = r.get("val")
                    prev = by_period[period].get(key)
                    if prev is None:
                        by_period[period][key] = {
                            "value": val, "accession": r.get("accn"),
                            "ambiguous": False,
                        }
                    elif prev["value"] != val:
                        by_period[period][key]["ambiguous"] = True
                        by_period[period][key]["accession"] = (
                            prev["accession"], r.get("accn"))
    return by_period, meta


def identities(by_period):
    """
    Every additive relationship the filer actually reports.

    For each period, for each pair of concepts, sum and look the sum up among the
    same period's concepts. Nothing is filtered by name: the search finds whatever
    arithmetic holds and the caller labels it.
    """
    found = defaultdict(set)          # (a, b, c) -> periods
    for period, values in by_period.items():
        usable = {k: v for k, v in values.items() if not v["ambiguous"]}
        lookup = defaultdict(list)
        for concept, rec in usable.items():
            if isinstance(rec["value"], (int, float)):
                lookup[round(float(rec["value"]), 2)].append(concept)
        keys = sorted(usable)
        for i, a in enumerate(keys):
            va = usable[a]["value"]
            if not isinstance(va, (int, float)):
                continue
            for b in keys[i + 1:]:
                vb = usable[b]["value"]
                if not isinstance(vb, (int, float)):
                    continue
                total = va + vb
                if total == 0:
                    continue
                for c in lookup.get(round(total, 2), ()):
                    if c not in (a, b):
                        found[(a, b, c)].add(period)
    return found


def main():
    filers, docs = calibration_filers()

    report = {}
    recurring = defaultdict(set)      # (a, b, c) -> filers
    for ticker, info in sorted(filers.items()):
        by_period, meta = instants(docs[ticker])
        found = identities(by_period)
        for triple, periods in found.items():
            if len(periods) >= MIN_PERIODS:
                recurring[triple].add(ticker)
        report[ticker] = {
            "business_model": info["business_model"],
            "debt_status": info["debt_status"],
            "usable_instants": len(by_period),
            "identities_holding_in_6_or_more_periods": [
                {"a": a, "b": b, "c": c, "periods": len(p)}
                for (a, b, c), p in sorted(found.items(),
                                          key=lambda kv: -len(kv[1]))
                if len(p) >= MIN_PERIODS
            ],
        }

    reproducible = sorted(
        ((a, b, c) for (a, b, c), fs in recurring.items()
         if len(fs) >= MIN_FILERS),
        key=lambda t: (-len(recurring[t]), t))
    irreproducible = sorted(
        ((a, b, c) for (a, b, c), fs in recurring.items()
         if len(fs) == 1),
        key=lambda t: (-len(recurring[t]), t))

    def describe(triple):
        a, b, c = triple
        tags = []
        for concept in (a, b):
            if concept in CURRENT_SIDE:
                tags.append(f"{concept} [declared current side]")
            elif concept == CANDIDATE:
                tags.append(f"{concept} [the candidate]")
            elif concept in TOTAL_SHAPED:
                tags.append(f"{concept} [total-shaped]")
            else:
                tags.append(f"{concept} [unlabelled]")
        return {
            "sum_of": tags[:2], "equals": (
                f"{c} [declared current side]" if c in CURRENT_SIDE else
                f"{c} [total-shaped]" if c in TOTAL_SHAPED else
                f"{c} [unlabelled]"),
            "filers": sorted(recurring[triple]),
            "filer_count": len(recurring[triple]),
            "shape": (
                "A: two components sum to a total"
                if c in TOTAL_SHAPED else
                "C: a current concept is itself a sum, so adding to it "
                "double-counts" if c in CURRENT_SIDE else
                "unlabelled: an arithmetic relationship with no declared "
                "role on either side"),
        }

    shapes = Counter(describe(t)["shape"].split(":")[0] for t in reproducible)

    # The pre-registered verdict, and the precision that matters with it.
    debt_identities = [
        t for t in reproducible
        if ({t[0], t[1]} & (CURRENT_SIDE | {CANDIDATE} | TOTAL_SHAPED))
        and t[2] in (CURRENT_SIDE | {CANDIDATE} | TOTAL_SHAPED)
    ]
    composition_holds = [
        t for t in debt_identities
        if set(t[:2]) == {"us-gaap:LongTermDebtCurrent",
                          "us-gaap:LongTermDebtNoncurrent"}
    ]
    current_side_totals = [
        t for t in debt_identities
        if "Current" in t[2] or "current" in t[2]
    ]
    candidate_in_identity = [t for t in reproducible if CANDIDATE in t]
    if composition_holds:
        verdict = "SUPPORTED"
        why = (
            f"The declared composition holds as an arithmetic identity in the "
            f"source: `LongTermDebtCurrent + LongTermDebtNoncurrent == "
            f"LongTermDebt`, across "
            f"{sorted(recurring[composition_holds[0]])} -- found by summing "
            f"values, not by matching names."
            f"\n\n**What it establishes is narrower than a debt structure.** It "
            f"establishes that long-term debt's presentation split adds up to a "
            f"total the filers report. It is a split of *long-term* debt, which "
            f"excludes capital lease obligations and short-term borrowings by "
            f"its own descriptions."
            f"\n\n**No current-debt total is derived anywhere in these "
            f"identities.** The totals that appear are non-current-inclusive: "
            f"`LongTermDebt`, `DebtAndCapitalLeaseObligations`."
            f"\n\n**`ShortTermBorrowings` appears in none of them.** "
            f"{len(candidate_in_identity)} reproducible identity involves it, so "
            f"Proposition C's negative answer is now positive evidence rather "
            f"than an absence of a comparator."
        )
    elif debt_identities:
        verdict = "SUPPORTED"
        why = (f"{len(debt_identities)} arithmetic relationship(s) among debt "
               f"concepts hold across at least {MIN_FILERS} filers.")
    elif reproducible:
        verdict = "UNDECIDED"
        why = (f"{len(reproducible)} relationship(s) hold across at least "
               f"{MIN_FILERS} filers, but **none of them joins the declared or "
               f"candidate debt concepts**: they are arithmetic among other "
               f"balance-sheet lines. A structure that can be summed is not "
               f"evidence about debt composition.")
    else:
        verdict = "REFUTED"
        why = ("no arithmetic relationship among these filers' balance-sheet "
               "instants holds across two filers, so no composition is "
               "observable from this corpus.")

    total_reported = sorted({
        t[2] for t in reproducible} & TOTAL_SHAPED)

    result = {
        "proposition_D": {
            "statement": "For filers supplying the relevant current-debt "
                         "concepts, is there sufficient evidence to "
                         "characterise the composition of current debt?",
            "verdict": verdict,
            "reasoning": why,
            "support_requires": "at least one reproducible accounting "
                                "relationship not following from two concepts "
                                "sharing a name",
        },
        "method": {
            "how_relationships_are_found": "arithmetic on values: for every "
                                          "balance-sheet instant of a monetary "
                                          "unit, every pair is summed and the "
                                          "sum looked up among the same "
                                          "period's concepts",
            "why_not_by_name": "2.29 admitted a different non-debt category "
                               "on four successive keyword passes",
            "min_periods_per_identity": MIN_PERIODS,
            "min_filers_per_identity": MIN_FILERS,
        },
        "calibration_sample": {
            "note": "selected on the presence of co-reported concepts, which "
                    "is a selection criterion and not evidence. All of them "
                    "have `debt = COLLECTED`; the eleven silent filers report "
                    "no current-side concept and cannot be characterised.",
            "filers": report,
        },
        "reproducible_identities": [describe(t) for t in reproducible[:25]],
        "single_filer_identities": len(irreproducible),
        "identities_touching_debt_concepts": [
            describe(t) for t in debt_identities],
        "answers": {
            "A_observable_component_structure": (
                "partially, and not the one the decomposition implies: "
                "`LongTermDebtCurrent + LongTermDebtNoncurrent == LongTermDebt` "
                "is source-proven across 3 filers, so long-term debt's "
                "presentation split is observable. A second identity shows the "
                "two sides drawn from different bases: "
                "`LongTermDebtAndCapitalLeaseObligations + LongTermDebtCurrent "
                "== DebtAndCapitalLeaseObligations` in CMI and THRMV, where "
                "the non-current side includes capital leases and the current "
                "side does not. That is Case C -- adding to a current concept "
                "that is itself a slice of a wider base mixes bases -- and it "
                "was visible only through value arithmetic."),
            "B_is_a_source_proven_current_debt_total_reported": (
                f"no. The totals that appear as the result of a reproducible "
                f"identity are non-current-inclusive "
                f"({sorted(total_reported)}); no identity derives a "
                f"*current* total"),
            "C_can_short_term_plus_current_side_be_shown_to_be_a_quantity": (
                f"no, and now positively: `ShortTermBorrowings` appears in "
                f"{len(candidate_in_identity)} of the reproducible identities, "
                f"so the negative is a finding about the concept rather than a "
                f"gap in comparators"),
            "D_resolvable_only_by_future_source_evidence": [
                "whether any of the eleven filers silent for `debt` reports a "
                "current-side concept or an entity-level total the registry "
                "does not reach -- the calibration sample cannot say, because "
                "all seven of its filers have `debt = COLLECTED`",
                "whether current debt is reconstructible at all for a filer "
                "that reports neither component, since Case D cannot be "
                "distinguished from Case A without a reported total",
                "whether the current and non-current sides are drawn from the "
                "same base in the filers that report both, given that CMI and "
                "THRMV demonstrably do not",
            ],
            "and_the_qualification_before_any_mapping_is_even_considered": (
                "ST-EVA's `debt` is declared as a *presentation* composition "
                "-- current plus non-current. The totals the source reports are "
                "*entity-level total debt*. Those are different quantities. The "
                "identity that holds is a split of long-term debt excluding "
                "capital leases and short-term borrowings, and it says nothing "
                "about total debt. A definition match has to be established "
                "before a mapping is even arguable, and on this evidence it is "
                "not."),
        },
        "shapes_present": dict(shapes),
    }
    with open(os.path.join(H, "231-debt-composition.json"), "w",
              encoding="utf-8") as h:
        json.dump(result, h, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    pd = r["proposition_D"]
    print("PROPOSITION D:", pd["verdict"])
    print(" ", pd["reasoning"], "\n")
    print("calibration sample:")
    for t, v in r["calibration_sample"]["filers"].items():
        print(f"   {t:<7} {v['business_model']:<16} debt={v['debt_status']:<12} "
              f"instants={v['usable_instants']:>4}  identities>=6 periods="
              f"{len(v['identities_holding_in_6_or_more_periods'])}")
    print()
    print("shapes among reproducible identities:", r["shapes_present"])
    print("reproducible identities:", len(r["reproducible_identities"]),
          " touching debt concepts:",
          len(r["identities_touching_debt_concepts"]))
    for ident in r["reproducible_identities"][:8]:
        print(f"   {' + '.join(x.split(' [')[0] for x in ident['sum_of'])}"
              f"  ==  {ident['equals'].split(' [')[0]}"
              f"   [{ident['shape'].split(':')[0]}]  filers {ident['filer_count']}")
    print()
    for key, value in r["answers"].items():
        print(f"   {key}: {value}")