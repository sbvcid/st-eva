"""
2.32 -- Debt Semantic Decision: what does Core `debt` denote?

Not an experiment. A decision document.

2.31 settled what the corpus can answer: which quantities exist, which arithmetic
relationships hold, and that `LongTermDebtCurrent + LongTermDebtNoncurrent ==
LongTermDebt` across three filers. What it cannot answer is **which quantity
ST-EVA intends to preserve.** That is a design decision about the schema's
meaning, and pretending the data can make it is the mistake 2.31 was about to
make.

So this round does three things and stops:

  1. inventories **every declaration of what `debt` means**, in both contracts
     that contain it, and shows they do not reconcile with what the components
     deliver
  2. sets out the four candidate quantities with the evidence already in hand,
     and answers for each the four questions a semantic target has to answer
  3. leaves the target as an **explicit human decision**, with what each option
     implies for the chain it would move

Nothing is changed. No mapping, no registry entry, no metric definition, no
applicability rule. No corpus is asked to choose.
"""

from __future__ import annotations

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(os.path.dirname(SCRIPT_DIR))
for _path in (HERE, SCRIPT_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import data_contract  # noqa: E402
from core_registry import CoreRegistry  # noqa: E402
from registry_seed import seed  # noqa: E402
from sqlite_archive import SQLiteArchive  # noqa: E402

H = os.path.join(HERE, "experiments", "003-llm-evidence-retrieval", "harness")

# The four questions a semantic target must answer. The first is a design
# question, not an empirical one, and is marked as such.
QUESTIONS = [
    "is this the quantity ST-EVA intends to preserve?",
    "can its definition be written without circularity?",
    "which source concepts could map to it EXACT or PARTIAL?",
    "can the same semantic target hold across us-gaap and ifrs-full?",
]

CANDIDATES = {
    "A_long_term_debt": {
        "statement": "Long-term debt: the current portion of long-term debt plus "
                     "the non-current portion of long-term debt.",
        "non_circular_definition":
            "The balance-sheet amount of long-term debt at a stated date, "
            "excluding short-term borrowings, commercial paper and capital-lease "
            "obligations, split by the filer into the portion due within a year "
            "and the portion falling after that year.",
        "concepts": ["us-gaap:LongTermDebtCurrent",
                     "us-gaap:LongTermDebtNoncurrent",
                     "ifrs-full:CurrentPortionOfLongtermBorrowings",
                     "ifrs-full:LongtermBorrowings"],
        "evidence_from_2_31":
            "`LongTermDebtCurrent + LongTermDebtNoncurrent == "
            "us-gaap:LongTermDebt` across MSFT, STMEF and THRMV -- found by "
            "value arithmetic, not by name.",
    },
    "B_total_debt": {
        "statement": "Total debt: long-term debt plus short-term borrowings plus "
                     "other debt-bearing liabilities.",
        "non_circular_definition":
            "The total interest-bearing obligation of the entity at a stated "
            "date, comprising every current and non-current borrowing, however "
            "the filer chooses to present them.",
        "concepts": ["us-gaap:LongTermDebtCurrent",
                     "us-gaap:LongTermDebtNoncurrent",
                     "us-gaap:ShortTermBorrowings"],
        "evidence_from_2_31":
            "no supporting identity. `ShortTermBorrowings` appears in none of "
            "the 27 observed identities, and no filer in the corpus reports a "
            "quantity that its current and non-current components sum to.",
    },
    "C_obligations_including_leases": {
        "statement": "Total debt obligations including capital-lease "
                     "obligations.",
        "non_circular_definition":
            "Debt plus capital-lease obligations at a stated date, on the "
            "filer's own basis.",
        "concepts": ["us-gaap:LongTermDebtAndCapitalLeaseObligations",
                     "us-gaap:LongTermDebtCurrent"],
        "evidence_from_2_31":
            "`LongTermDebtAndCapitalLeaseObligations + LongTermDebtCurrent == "
            "us-gaap:DebtAndCapitalLeaseObligations` in CMI and THRMV -- but "
            "the two components come from different bases: the non-current side "
            "includes capital leases and the current side does not, so the sum "
            "does not reconstruct a single reporting basis.",
    },
    "D_source_specific_presentation": {
        "statement": "A source-specific presentation quantity: whatever total "
                     "the filer itself reports.",
        "non_circular_definition":
            "Not writable as one definition. The filer's own presentation total "
            "is what is preserved, and it differs between filers.",
        "concepts": ["us-gaap:LongTermDebt",
                     "us-gaap:DebtAndCapitalLeaseObligations",
                     "us-gaap:DebtCurrent"],
        "evidence_from_2_31":
            "entity-level totals do exist and are reproducible "
            "(`LongTermDebt`, `DebtAndCapitalLeaseObligations`), but they are "
            "not equivalent to one another across filers, so they are one "
            "concept per filer rather than one metric.",
    },
}


def main():
    # ---- 1. every declaration of what `debt` means -------------------------
    probe = SQLiteArchive(":memory:")
    registry = CoreRegistry(probe.connection)
    seed(registry)
    metric = registry.metric("debt")
    components = [
        {"concept_id": m.concept_id, "mapping_type": m.mapping_type,
         "notes": m.notes}
        for m in registry.mappings_for_metric("debt")
    ]
    probe.close()

    # The cross-source container is named, not guessed. `METRIC_UNITS` also maps
    # `debt` -- to "currency" -- so discovering "the first dict whose value is a
    # string" picked the unit table and reported the cross-source definition as
    # `currency`. A discovery step that can silently return the wrong field is
    # the same failure shape as the four keyword passes in 2.29: it finds
    # something plausible and calls it the thing asked for.
    cross_source = None
    for name in dir(data_contract):
        value = getattr(data_contract, name)
        if not isinstance(value, dict):
            continue
        text = value.get(data_contract.METRIC_DEBT)
        # A definition is prose; a unit is a token. The test is that.
        if isinstance(text, str) and len(text.split()) > 4:
            cross_source = {"container": name, "definition": text}

    in_core_registry = True
    in_cross_source_contract = data_contract.METRIC_DEBT in \
        data_contract.CONTRACT_METRICS
    shared = sorted(set(data_contract.CONTRACT_METRICS)
                    & set(m.metric_id for m in
                          CoreRegistry(SQLiteArchive(":memory:").connection).metrics())
    ) if False else None

    declarations = [
        {
            "where": "registry_seed.py -> metric_registry",
            "contract": "Core evidence registry (2.5+)",
            "field": "display_name",
            "text": metric.display_name,
            "claims": "total debt",
        },
        {
            "where": "registry_seed.py -> metric_registry",
            "contract": "Core evidence registry (2.5+)",
            "field": "semantic_definition",
            "text": metric.semantic_definition,
            "claims": "nothing -- circular",
        },
        {
            "where": "registry_seed.py -> metric_concept_mapping.notes",
            "contract": "Core evidence registry (2.5+)",
            "field": "mapping notes",
            "text": " | ".join(c["notes"] or "" for c in components),
            "claims": "components are 'a component of total debt'",
        },
    ]
    if cross_source:
        declarations.append({
            "where": f"data_contract.py -> {cross_source['container']}",
            "contract": "cross-source contract (2.3-B, `cmp-` ids)",
            "field": "metric definition",
            "text": cross_source["definition"],
            "claims": "total debt, composed from current and non-current",
        })

    # ---- 2. the candidates ------------------------------------------------
    candidate_rows = {}
    for key, spec in CANDIDATES.items():
        candidate_rows[key] = {
            "statement": spec["statement"],
            "definition_can_be_written_non_circularly": bool(
                spec["non_circular_definition"])
            and "Not writable" not in spec["non_circular_definition"],
            "non_circular_definition": spec["non_circular_definition"],
            "concepts_that_could_map": spec["concepts"],
            "already_mapped_in_the_registry": sorted(
                {c["concept_id"] for c in components}
                & set(spec["concepts"])),
            "evidence_from_2_31": spec["evidence_from_2_31"],
            "holds_across_taxonomies": (
                "yes, structurally: both a us-gaap and an ifrs-full "
                "current/non-current pair are declared"
                if len({"us-gaap", "ifrs-full"}
                       & {c.split(":")[0] for c in spec["concepts"]}) == 2
                else "not established"),
            "same_target_observed_in_both_taxonomies_in_corpus": None,
        }

    # ---- 3. the decision, left open ---------------------------------------
    decision = {
        "what_is_decided_now": "nothing. This document sets out the decision; it "
                               "does not make it.",
        "the_question": "Which accounting quantity does Core `debt` denote?",
        "why_the_corpus_cannot_answer_it": (
            "The corpus establishes which quantities exist and which arithmetic "
            "relationships hold. It cannot establish which of them this schema "
            "intends to preserve, because that is a statement about intent. "
            "Candidate A is the only source-supported option and the only one "
            "whose components are already declared -- which is a fact about the "
            "registry's present state, not an argument for it."),
        "options": [
            {
                "option": "target A: long-term debt",
                "effect": "the components already reconstruct it and the "
                          "identity is proven; the display name and both "
                          "definitions must change, and `total debt` stops being "
                          "what `debt` is called",
                "risk": "if the research use genuinely needs a broader "
                        "obligation, this silently narrows what has been "
                        "reported as total debt since 2.7",
            },
            {
                "option": "target B: total debt",
                "effect": "the name and one definition are already right and "
                          "both are wrong; the components must change, and the "
                          "mapping problem 2.29--2.31 characterised becomes a "
                          "live design question again",
                "risk": "no filer in the corpus reports a quantity its current "
                        "and non-current components sum to, so the target would "
                        "be unverifiable against everything held so far",
            },
            {
                "option": "split into `long_term_debt` and `total_debt`",
                "effect": "removes the ambiguity rather than choosing; changes "
                          "the Core metric set, so every downstream count, "
                          "coverage denominator and valuation input moves",
                "risk": "two metrics where the corpus supports one is its own "
                        "kind of over-collection, and `total_debt` would be "
                        "unverifiable here for the same reason as B",
            },
            {
                "option": "target D: source-specific presentation",
                "effect": "never conflicts with a filer; needs a per-concept "
                          "definition and no comparability claim",
                "risk": "the Core metric set exists to be comparable across "
                        "filers; this gives that up for debt specifically",
            },
        ],
        "what_the_choice_moves": [
            "the Core metric set and its size",
            "cross-source definitions in data_contract.py",
            "registry mappings and their EXACT/PARTIAL typing",
            "coverage denominators, since the metric universe changes",
            "any future valuation input that reads a balance-sheet obligation",
        ],
        "prerequisites_regardless_of_choice": [
            "the two contracts containing `debt` need one definition between "
            "them, or an explicit statement that they are different metrics",
            "the circular phrasing in both must go whichever target is chosen; a "
            "circular definition cannot be tested against anything",
        ],
    }

    result = {
        "proposition_F": {
            "statement": "Core `debt` denotes a quantity that can be written "
                         "down non-circularly and matched to something the "
                         "source reports.",
            "status": "requires a human design decision",
            "not_decided_here": True,
        },
        "the_two_contracts": {
            "core_evidence_registry": "registry_seed.py, metric_registry; "
                                      "`debt` is one of the 20 Core metrics",
            "cross_source": f"data_contract.py, {cross_source['container']}; "
                            f"`debt` is in CONTRACT_METRICS and is emitted "
                            f"with a `cmp-` id",
            "metric_id_in_both": in_cross_source_contract and in_core_registry,
            "the_two_definitions_reconcile": False,
            "why_not": (
                "Both say 'total debt'. Both define it as current plus "
                "non-current. 2.31 established by value arithmetic that current "
                "plus non-current reconstructs `us-gaap:LongTermDebt` -- a "
                "long-term-debt quantity that excludes short-term borrowings "
                "and capital leases by its own SEC description. So the two "
                "contracts and the registry's own components name three "
                "different quantities and agree on none of them."),
        },
        "declarations_inventory": declarations,
        "candidate_targets": candidate_rows,
        "questions_each_candidate_must_answer": QUESTIONS,
        "decision": decision,
    }
    with open(os.path.join(H, "232-debt-semantic-decision.json"), "w",
              encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, default=str)
    return result


if __name__ == "__main__":
    r = main()
    t = r["the_two_contracts"]
    print("THE TWO CONTRACTS THAT CONTAIN `debt`")
    print(f"  core evidence registry : {t['core_evidence_registry']}")
    print(f"  cross-source           : {t['cross_source']}")
    print(f"  metric id in both      : {t['metric_id_in_both']}")
    print(f"  the two reconcile      : {t['the_two_definitions_reconcile']}")
    print(f"  why not                : {t['why_not']}\n")
    print("EVERY DECLARATION OF WHAT `debt` MEANS")
    for d in r["declarations_inventory"]:
        print(f"  [{d['contract']}] {d['where']} / {d['field']}")
        print(f"      claims: {d['claims']}")
        print(f"      text  : {str(d['text'])[:150]}")
    print()
    print("CANDIDATE TARGETS")
    for key, v in r["candidate_targets"].items():
        print(f"  {key}")
        print(f"      non-circular definition writable : "
              f"{v['definition_can_be_written_non_circularly']}")
        print(f"      already mapped in the registry   : "
              f"{v['already_mapped_in_the_registry']}")
        print(f"      holds across taxonomies          : "
              f"{v['holds_across_taxonomies']}")
        print(f"      2.31 evidence                    : "
              f"{v['evidence_from_2_31'][:110]}")
    print()
    d = r["decision"]
    print("THE DECISION")
    print(f"  {d['what_is_decided_now']}")
    for o in d["options"]:
        print(f"  option: {o['option']}")
        print(f"     effect: {o['effect'][:120]}")
        print(f"     risk  : {o['risk'][:120]}")
    print(f"  moves regardless: {d['what_the_choice_moves']}")