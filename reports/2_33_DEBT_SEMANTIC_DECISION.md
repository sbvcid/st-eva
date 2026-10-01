# 2.32 — Debt Semantic Decision

**Not an experiment. A decision document, and the decision is not made here.**

No mapping, registry entry, metric definition or applicability rule was changed.
No corpus was asked to choose. Nothing fetched. Suite 714 run / 640 passed /
74 skipped. Not committed.

---

## A. `debt` lives in two contracts, and neither is testable

```
Core evidence registry (2.5+)
    registry_seed.py -> metric_registry
    display_name          "Total debt"
    semantic_definition   "Borrowings classified as debt under this metric
                           definition. No single standard concept states it..."
    mapping notes         "a component of total debt, never the total on its own"

cross-source contract (2.3-B, `cmp-` ids)
    data_contract.py -> METRIC_DEFINITIONS
    "Total debt at a balance sheet date, composed from the filer's current and
     non-current debt concepts. Never synthesized."
```

**Both say "total debt". Both define it as current plus non-current. And 2.31
established by value arithmetic that current plus non-current reconstructs
`us-gaap:LongTermDebt`** — a long-term-debt quantity that excludes short-term
borrowings and capital leases by its own SEC description.

So there are **three declarations of what `debt` means and they name three
different quantities:**

| declaration | says it is |
| --- | --- |
| `display_name`, both contracts' prose | **total debt** |
| the components actually mapped | **long-term debt** — proven, across three filers |
| `semantic_definition` | nothing; it is circular |

A circular definition cannot be tested against anything, and it is the one that
would adjudicate between the other two.

This is a **Core metric definition bug**, not a mapping bug. Nothing about the
mapping is wrong: the four concepts are correctly mapped as components, and they
sum correctly. What is wrong is that the whole thing is called "Total debt".

---

## B. Four candidate targets, and what is already known about each

| | non-circular definition writable | already mapped | across taxonomies | 2.31 evidence |
| --- | --- | --- | --- | --- |
| **A** long-term debt | **yes** | **all four** | yes, structurally — a us-gaap and an ifrs-full pair are declared | `LTDCurrent + LTDNoncurrent == LongTermDebt`, MSFT / STMEF / THRMV |
| **B** total debt | yes | 2 of 3 | not established | **none** — `ShortTermBorrowings` appears in 0 of 27 identities |
| **C** obligations incl. leases | yes | 1 of 2 | not established | reconstructible but **base-mixing**: non-current side includes leases, current side does not |
| **D** source-specific presentation | **no** | none | not established | totals exist (`LongTermDebt`, `DebtAndCapitalLeaseObligations`) but are not equivalent across filers, so they are one concept per filer rather than one metric |

The four questions each candidate must answer:

1. is this the quantity ST-EVA intends to preserve? — **a design question**
2. can its definition be written without circularity?
3. which source concepts could map to it EXACT or PARTIAL?
4. can the same semantic target hold across us-gaap and ifrs-full?

Only **A** has a non-circular definition, all four concepts already mapped, a
proven arithmetic identity, and a declared pair in both taxonomies. **That is a
fact about the registry's present state, not an argument for A** — the components
having been declared first is exactly why A looks attractive.

---

## C. The decision, stated and not taken

**Why the corpus cannot make it.** The corpus establishes which quantities exist
and which arithmetic relationships hold. It cannot establish which of them this
schema intends to preserve, because that is a statement about intent. Asking the
data to choose is the move 2.31 was one step away from making, and the name
`Total debt` — which sounds like an answer — is not evidence for B any more than
the components are evidence for A.

| option | effect | risk |
| --- | --- | --- |
| **target A** — long-term debt | components already reconstruct it and the identity is proven; display name and both definitions must change | if the research use genuinely needs a broader obligation, this silently narrows what has been reported as total debt since 2.7 |
| **target B** — total debt | name and one definition are already right and both are wrong; components must change, and the 2.29–2.31 problem becomes a live design question again | **no filer in the corpus reports a quantity its current and non-current components sum to** — the target would be unverifiable against everything held |
| **split** — `long_term_debt` + `total_debt` | removes the ambiguity instead of choosing | two metrics where the corpus supports one is its own over-collection, and `total_debt` would be unverifiable for the same reason as B |
| **target D** — source presentation | never conflicts with a filer | the Core metric set exists to be comparable across filers; this gives that up for debt alone |

**What any choice moves:** the Core metric set and its size · cross-source
definitions in `data_contract.py` · registry mappings and their EXACT/PARTIAL
typing · coverage denominators, since the metric universe changes · any future
valuation input that reads a balance-sheet obligation.

**Required regardless of which is chosen:**

1. **The two contracts need one definition between them**, or an explicit
   statement that `debt` and `cmp-` `debt` are different metrics. They currently
   share an id and disagree on meaning, and nothing in the suite notices.
2. **The circular phrasing in both must go.** "Borrowings classified as debt under
   this metric definition" and "composed from the filer's current and non-current
   debt concepts" both define `debt` by reference to `debt`. A definition that
   cannot be tested cannot be maintained either.

---

## D. Two things found along the way

**A discovery step that silently returned the wrong field.** The first run of the
contract audit asked "which dict maps `debt` to a string" and found `METRIC_UNITS`,
which maps it to `"currency"` — so the cross-source definition was reported as
`currency`. Corrected by testing for prose rather than for a string. It is the
same failure shape as the four keyword passes in 2.29: find something plausible,
call it the thing that was asked for.

**`debt` is in both contracts and nothing reconciles them.** `debt` is one of the
20 Core metrics in `metric_registry` and also in `CONTRACT_METRICS` with a `cmp-`
prefix. Two meanings, one id, no test asserting they agree.

---

## E. State

| | |
| --- | --- |
| full suite | **714 run, 640 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| fetched | **nothing** |
| registry / mappings / metric definitions / applicability | **unchanged** |
| commits | 2.27 at `7cb5e27`; 2.28–2.32 not committed |

`debt_semantic_decision_232.py` is read-only and writes
`harness/232-debt-semantic-decision.json` with every declaration, all four
candidates, and the options with their consequences.

## F. What 2.33 would be

Redesigning the debt mapping against the chosen target — and only then touching the
registry. The order matters: choosing a mapping first and a target second is how a
metric ends up named "Total debt" while holding long-term components, which is
where 2.32 found it.