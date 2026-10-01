# 2.32 — Debt Definition Proposition: UNDECIDED

Layers 1 and 2 are settled. Layer 3 asks the question they were circling: **even
when the source has the numbers, which accounting quantity should ST-EVA's `debt`
be?**

No mapping, registry entry, metric definition or applicability rule was changed.
Nothing was fetched. Suite 714 run / 640 passed / 74 skipped. Not committed.

---

## A. The candidates, enumerated and not chosen

```
A  long-term debt                      current + non-current portion of long-term debt
B  total debt                           long-term debt + short-term borrowings + other
                                        debt liabilities
C  total obligations incl. leases       debt + capital-lease obligations
D  source-specific presentation total   whatever total the filer itself reports
```

Six questions per candidate, asked of the corpus: the formal definition, which
source concepts represent it, whether a cross-filer entity-level total is
observable, whether leases are included, whether short-term borrowings are
included, and whether the two sides share an accounting basis.

---

## B. UNDECIDED — and the reason is not ambiguity in the evidence

> **The declaration does not name one quantity. It names three, and they
> disagree.**

```
display name    "Total debt"                      -> candidate B
components      LongTermDebtCurrent              -> candidate A, proven by arithmetic
                LongTermDebtNoncurrent
                CurrentPortionOfLongtermBorrowings
                LongtermBorrowings
definition      "Borrowings classified as debt
                under this metric definition"     -> names nothing
```

The **components** are exclusively long-term-debt concepts, and 2.31 proved by
value arithmetic that the us-gaap pair sums to `us-gaap:LongTermDebt` across MSFT,
STMEF and THRMV.

The **definition text is circular.** "Borrowings classified as debt under this
metric definition" does not identify which borrowings, so it can neither match a
candidate nor contradict one. A name cannot be outweighed by components, and a
circular definition cannot break the tie.

That is the whole verdict, and it is not a close call: it is **the absence of a
definition that could be tested.**

---

## C. What the corpus supports, candidate by candidate

| | reconstructible | leases | short-term | filers |
| --- | --- | --- | --- | --- |
| **A** long-term debt | **yes** — `LTDCurrent + LTDNoncurrent == LongTermDebt` | no | no | MSFT, STMEF, THRMV |
| **B** total debt | **no** — needs `ShortTermBorrowings`, absent from every identity | no | yes | — |
| **C** obligations incl. leases | partially — but base-mixing, below | yes | no | CMI, THRMV |
| **D** source presentation total | no identity derives one | — | — | — |

**Candidate B has no support at all**, and the reason is precise: it requires
`ShortTermBorrowings`, which appears in **none** of the 27 observed identities.
That is the same finding as 2.31's, now attached to a specific candidate rather
than to a concept.

**Candidate C is reconstructible and base-mixing at once:**

```
LongTermDebtAndCapitalLeaseObligations  +  LongTermDebtCurrent
                                       == DebtAndCapitalLeaseObligations   CMI, THRMV
```

The non-current side includes capital leases; the current side does not. So C's
components do not share an accounting basis, and answering question 6 for C is
"no" — which is why it cannot be adopted on the strength of one identity.

---

## D. Two errors of my own, both the same error

**Subset matching credited candidate B with an identity containing no short-term
borrowings.** Matching an identity against *any subset* of a candidate's
components silently ignores the components the filer did not report — the third
time in this sequence that presence has been mistaken for participation. All of a
candidate's components must appear.

**The first verdict was SUPPORTED, on a comparison that could not decide it.** I
matched the *components* to candidate A and declared the proposition supported,
but the proposition is about the *definition*, and the definition is circular.
Deciding a question about a definition with evidence about its parts is the same
category of mistake.

Both are recorded because the pattern is the round's real content: **in three
consecutive rounds the instrument produced a confident verdict that a plausible
list satisfied, and each time the list was the problem.**

---

## E. What this round deliberately did not do

**`debt` was not renamed to `long_term_debt`.** 2.31 proved a reconstructible
quantity exists. That is not a reason to conclude it is the quantity `debt` was
meant to denote — it is the difference between "the source contains a
reconstructible quantity" and "this is what we want to preserve". The name still
says "Total debt", the components say long-term debt, and neither has been
overwritten on the strength of an arithmetic identity.

**No candidate was selected.** Four were enumerated and each was tested against
six questions. Three are unsupported or base-mixed; one is observable and is what
the components already say. That is a finding about the declaration, not a choice.

---

## F. Where the three layers now stand

| layer | proposition | verdict | established by |
| --- | --- | --- | --- |
| 1 | vocabulary coverage | **SUPPORTED** | zero coverage of four declared concepts across 29 silent filers (2.29) |
| 2 | composition | **SUPPORTED** | `LTDCurrent + LTDNoncurrent == LongTermDebt`, value arithmetic, 3 filers (2.31) |
| 3 | semantic target | **UNDECIDED** | the declaration names three quantities and they disagree (2.32) |

Layer 3 is the one that decides every future mapping, and it is blocked on a
definition rather than on evidence. No amount of further collection resolves it,
because the thing that has to be decided is what ST-EVA intends `debt` to mean —
and that is not a question the corpus can answer.

## G. State

| | |
| --- | --- |
| full suite | **714 run, 640 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| fetched | **nothing** |
| registry / mappings / metric definitions / applicability | **unchanged** |
| commits | 2.27 at `7cb5e27`; 2.28–2.32 not committed |

`debt_definition_232.py` is read-only and writes `harness/232-debt-definition.json`
with the declared metric, all four candidates, and per-candidate evidence.