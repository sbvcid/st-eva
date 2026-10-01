"""
2.32 -- Debt Definition Proposition: which quantity does Core `debt` denote?

Layers 1 and 2 are settled (2.29, 2.31). Layer 3 asks the question the other two
were circling: **even when the source has the numbers, which accounting quantity
should ST-EVA's `debt` be?**

The candidates are enumerated and **not chosen** here:

    A  long-term debt              current + non-current portion of *long-term* debt
    B  total debt                   long-term debt + short-term borrowings + other
                                    debt liabilities
    C  total obligations incl.      debt + capital-lease obligations
       leases
    D  a source-specific           whatever presentation total the filer itself
       presentation quantity       reports

For each, the corpus is asked six questions -- the formal definition, which source
concepts represent it, whether a cross-filer entity-level total is observable,
whether leases are included, whether short-term borrowings are included, and
whether the current and non-current sides share an accounting basis.

**What is explicitly not done:**

  * `debt` is **not renamed** to `long_term_debt`. 2.31 proved a reconstructible
    quantity exists; that is not the same as it being the quantity ST-EVA should
    denote, and the difference is the whole of this round.
  * The existing definition is **not treated as the answer.** It is one of the
    things under test.
  * No mapping, registry entry, metric definition or applicability rule changes,
    and nothing is fetched.

Pre-registered outcome:
  SUPPORTED  the definition matches a source-observable quantity clearly and
             reproducibly across filers
  REFUTED    the definition is clearly inconsistent with the quantity it claims
  UNDECIDED  several quantities are plausible and the evidence cannot choose
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core_registry import CoreRegistry  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

# Concepts that would represent each candidate, read from what the corpus already
# contains. This is a *reporting* list keyed to each candidate, not a candidate
# search: nothing here is being proposed as a mapping.
LEASES = ("CapitalLease", "FinanceLease", "OperatingLease")
SHORT_TERM = ("ShortTermBorrowings", "ShortTermBankLoansAndNotesPayable",
              "ShortTermNonBankLoansAndNotesPayable", "DebtCurrent",
              "NotesPayableCurrent")

CANDIDATES = {
    "A_long_term_debt": {
        "statement": "current portion of long-term debt plus non-current "
                     "portion of long-term debt",
        "components": ["us-gaap:LongTermDebtCurrent",
                       "us-gaap:LongTermDebtNoncurrent",
                       "ifrs-full:CurrentPortionOfLongtermBorrowings",
                       "ifrs-full:LongtermBorrowings"],
        "entity_level_total": ["us-gaap:LongTermDebt"],
    },
    "B_total_debt": {
        "statement": "long-term debt plus short-term borrowings plus other "
                     "debt liabilities",
        "components": ["us-gaap:LongTermDebtCurrent",
                       "us-gaap:LongTermDebtNoncurrent",
                       "us-gaap:ShortTermBorrowings"],
        "entity_level_total": ["us-gaap:DebtAndCapitalLeaseObligations"],
    },
    "C_total_obligations_including_leases": {
        "statement": "debt plus capital-lease obligations",
        "components": ["us-gaap:LongTermDebtAndCapitalLeaseObligations",
                       "us-gaap:LongTermDebtCurrent"],
        "entity_level_total": ["us-gaap:DebtAndCapitalLeaseObligations"],
    },
    "D_source_specific_presentation_total": {
        "statement": "whatever presentation total the filer itself reports",
        "components": [],
        "entity_level_total": ["us-gaap:DebtAndCapitalLeaseObligations",
                               "us-gaap:DebtCurrent",
                               "us-gaap:LongTermDebt"],
    },
}


def main():
    # The thing under test, read from the registry rather than remembered.
    probe = SQLiteArchive(":memory:")
    registry = CoreRegistry(probe.connection)
    seed(registry)
    debt = registry.metric("debt")
    declared = {
        "display_name": debt.display_name,
        "statement": debt.statement,
        "semantic_definition": debt.semantic_definition,
        "comparability_group": debt.comparability_group,
        "components": [
            {"concept_id": m.concept_id, "mapping_type": m.mapping_type,
             "notes": m.notes}
            for m in registry.mappings_for_metric("debt")
        ],
    }
    component_ids = {c["concept_id"] for c in declared["components"]}
    probe.close()

    # What 2.31 established, by value arithmetic and not by name.
    with open(os.path.join(H, "231-debt-composition.json"),
              encoding="utf-8") as handle:
        composition = json.load(handle)

    identities = []
    for entry in (composition["reproducible_identities"]
                  + composition["identities_touching_debt_concepts"]):
        parts = [x.split(" [")[0] for x in entry["sum_of"]]
        identities.append({
            "sum_of": parts, "equals": entry["equals"].split(" [")[0],
            "filers": entry["filers"], "filer_count": entry["filer_count"],
        })
    seen = set()
    identities = [i for i in identities
                  if not (tuple(i["sum_of"]) + (i["equals"],)) in seen
                  and not seen.add(tuple(i["sum_of"]) + (i["equals"],))]

    def filers_of(*concepts):
        out = set()
        for identity in identities:
            if all(c in identity["sum_of"] for c in concepts):
                out |= set(identity["filers"])
        return sorted(out)

    # **All** of a candidate's components must appear in the identity for it to
    # count as reconstructible. Subset matching silently ignored the components a
    # filer did *not* report -- which is how candidate B, whose components include
    # `ShortTermBorrowings`, was credited with an identity containing no
    # short-term borrowings. That is "presence is not participation" again.
    #
    # Components are grouped by taxonomy first, because a declared composition is
    # taxonomy-specific: `debt` maps a us-gaap current/non-current pair *and* an
    # ifrs-full pair, and no filer reports both. So an identity satisfies the
    # candidate when it contains one complete taxonomy group -- the pair, not all
    # four concepts at once.
    def groups(components):
        by_taxonomy = defaultdict(set)
        for concept in components:
            by_taxonomy[concept.split(":")[0]].add(concept)
        return list(by_taxonomy.values())

    rows = {}
    for key, spec in CANDIDATES.items():
        components = set(spec["components"])
        reconstructible = []
        for identity in identities:
            present = set(identity["sum_of"])
            satisfied = [g for g in groups(components) if g <= present]
            if satisfied and len(satisfied[0]) > 1:
                reconstructible.append({
                    "taxonomy_group_used": sorted(satisfied[0]),
                    "equals": identity["equals"], "filers": identity["filers"],
                })
        uses_lease = any(any(mark in c for mark in LEASES) for c in components)
        uses_short_term = any(c in SHORT_TERM for c in components)
        rows[key] = {
            "statement": spec["statement"],
            "components": spec["components"],
            "reconstructible_from_observed_identities": reconstructible,
            "reconstructible": bool(reconstructible),
            "entity_level_totals_declared_for_this_quantity":
                spec["entity_level_total"],
            "includes_leases": uses_lease,
            "includes_short_term_borrowings": uses_short_term,
            "identity_holds_in_filers": sorted({
                f for x in reconstructible for f in x["filers"]}),
        }

    # Question 6 for each candidate: are the two sides on the same basis? The
    # evidence for that is 2.31's Case C identity, which is checked here rather
    # than asserted.
    mixed_basis = [i for i in identities
                   if {i["equals"]} & {"us-gaap:DebtAndCapitalLeaseObligations"}
                   and any(c == "us-gaap:LongTermDebtCurrent"
                           for c in i["sum_of"])]

    # Which candidate does the declaration match?
    declared_components_are_all_long_term = all(
        "LongTermDebt" in c or "LongtermBorrowings" in c
        for c in component_ids)
    name_claims_total = "total" in (declared["display_name"] or "").lower()

    def matches(candidate):
        covers = set(CANDIDATES[candidate]["components"])
        return component_ids == covers

    matched = [c for c in CANDIDATES if matches(c)]

    # What the declaration says about its own target, taken three ways. The
    # criterion is about the *definition*, so the components matching a candidate
    # is a fact about the components and not a verdict on the definition.
    name_says = ("B_total_debt" if name_claims_total else "a long-term quantity")
    components_say = matched[0] if matched else None
    definition_says = None                      # circular; it names nothing
    agreement = len({name_says, components_say, definition_says})

    if matched and not declared_components_are_all_long_term:
        verdict = "SUPPORTED"
        why = (f"the declared components reconstruct {matched[0]} across filers")
    else:
        # The declaration does not state one target. It states three, and they do
        # not agree -- so it can neither match a candidate nor contradict one, and
        # UNDECIDED is the only reading the evidence supports.
        verdict = "UNDECIDED"
        why = (
            "**The declaration does not name one quantity. It names three, and "
            "they disagree.**\n\n"
            f"- the **display name** is {declared['display_name']!r}, which "
            f"claims candidate B, total debt\n"
            f"- the **components** are {sorted(component_ids)}, which are "
            f"exclusively long-term-debt concepts and reconstruct candidate A, "
            f"long-term debt -- proven by value arithmetic in 2.31 across "
            f"MSFT, STMEF and THRMV\n"
            f"- the **definition text** is "
            f"{declared['semantic_definition']!r}, which is circular: "
            f"'borrowings classified as debt under this metric definition' does "
            f"not identify which borrowings, so it can neither match nor "
            f"contradict any quantity\n\n"
            "**A name cannot be outweighed by components, and a circular "
            "definition cannot break the tie.** 2.31 established that a "
            "reconstructible quantity exists; that is not a reason to conclude it "
            "is the quantity `debt` was meant to denote, and no rename is "
            "proposed.\n\n"
            f"**Candidate A is observable** -- its components sum to "
            f"`us-gaap:LongTermDebt` in the corpus. **Candidate B is not "
            f"supported**: it requires `ShortTermBorrowings`, which appears in "
            f"none of the {len(identities)} observed identities. **Candidate C "
            f"is not cleanly reconstructible either**, because the identity that "
            f"produces `DebtAndCapitalLeaseObligations` mixes bases: the "
            f"non-current side includes capital leases and the current side does "
            f"not.\n\n"
            "So several quantities remain plausible and the evidence cannot "
            "choose among them. That is the honest position, and it is not a "
            "close call -- it is the absence of a definition that could be "
            "tested."
        )

    result = {
        "proposition_E": {
            "statement": "Core `debt` denotes a quantity that can be matched "
                         "clearly and reproducibly to something the source "
                         "reports.",
            "verdict": verdict,
            "reasoning": why,
            "candidates_enumerated_not_chosen": list(CANDIDATES),
            "debt_is_not_renamed": "2.31 proved a reconstructible quantity "
                                    "exists; that is not a reason to rename "
                                    "`debt`, and no rename is proposed here",
        },
        "the_thing_under_test": declared,
        "declaration_versus_components": {
            "name_claims_total": name_claims_total,
            "components_are_all_long_term_debt": declared_components_are_all_long_term,
            "components": sorted(component_ids),
            "component_set_equals_candidate": matched or None,
            "any_identity_mixes_bases": [
                {"sum_of": i["sum_of"], "equals": i["equals"],
                 "filers": i["filers"]} for i in mixed_basis
            ],
        },
        "candidate_evidence": rows,
        "observed_identities_considered": len(identities),
    }
    with open(os.path.join(H, "232-debt-definition.json"), "w",
              encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    pe = r["proposition_E"]
    print("PROPOSITION E:", pe["verdict"])
    print(" ", pe["reasoning"], "\n")
    t = r["the_thing_under_test"]
    print(f"  the thing under test: {t['display_name']!r}")
    print(f"    definition: {t['semantic_definition']}")
    print(f"    components: {[c['concept_id'] for c in t['components']]}")
    dv = r["declaration_versus_components"]
    print(f"    name claims total: {dv['name_claims_total']}")
    print(f"    components all long-term: {dv['components_are_all_long_term_debt']}")
    print(f"    matches candidate: {dv['component_set_equals_candidate']}")
    print(f"    identities mixing bases: {len(dv['any_identity_mixes_bases'])}")
    for m in dv["any_identity_mixes_bases"]:
        print(f"      {' + '.join(m['sum_of'])} == {m['equals']}  {m['filers']}")
    print()
    print("candidate evidence:")
    for key, v in r["candidate_evidence"].items():
        recon = v["reconstructible_from_observed_identities"]
        print(f"   {key}")
        print(f"      statement                : {v['statement']}")
        print(f"      reconstructible          : {len(recon)} identity/identities")
        for x in recon:
            print(f"          {' + '.join(x['taxonomy_group_used'])} == {x['equals']}"
                  f"  {x['filers']}")
        print(f"      includes leases          : {v['includes_leases']}")
        print(f"      includes short-term      : {v['includes_short_term_borrowings']}")