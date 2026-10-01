# 2.31 — Debt Composition Characterisation

No registry change, no mapping, no metric definition change, no applicability
rule, nothing fetched. Suite 714 run / 640 passed / 74 skipped. Not committed.

---

## A. The proposition states four shapes and the data picked one

Pre-registered, and deliberately not written with the answer inside it — not
"current debt = ShortTermBorrowings + LongTermDebtCurrent", which would have
assumed what it is meant to test:

> **For filers supplying the relevant current-debt concepts, is there sufficient
> evidence to characterise the composition of current debt?**

| | shape | found? |
| --- | --- | --- |
| A | total = current_a + current_b | **yes, for long-term debt** |
| B | total = three current components | no |
| C | a current concept is a slice of a wider base, so a naive sum mixes bases | **yes — CMI and THRMV** |
| D | no entity-level total reported; composition not establishable | yes for the 11 silent filers |

### SUPPORTED — and narrower than it sounds

> **`LongTermDebtCurrent + LongTermDebtNoncurrent == LongTermDebt`**
> holds across **MSFT, STMEF, THRMV**.

The registry's own declared composition is source-proven, as an arithmetic
identity. That is the first time this project has established a decomposition by
value rather than by assertion.

But it is a split of **long-term** debt, which by its own description *excludes*
capital lease obligations and short-term borrowings. So:

- **No current-debt total is derived anywhere.** The totals that appear as results
  are non-current-inclusive: `LongTermDebt`, `DebtAndCapitalLeaseObligations`.
- **`ShortTermBorrowings` appears in 0 of the 25 reproducible identities.**

That last line converts Proposition C's negative from an absence into a positive
finding: the candidate does not participate in any debt arithmetic the source
reports, so it is neither the current side nor a component of one.

### Case C, visible only through arithmetic

```
LongTermDebtAndCapitalLeaseObligations  +  LongTermDebtCurrent
                                       == DebtAndCapitalLeaseObligations      CMI, THRMV
```

Here the **non-current side includes capital leases and the current side does
not**. The two components of `debt`'s composition are drawn from different bases
in the filers that report both, so a naive current + non-current sum mixes bases
rather than reconstructing a quantity. No name-based test would have surfaced it:
both concepts contain "LongTermDebt".

---

## B. How the relationships were found — and why that matters

**By arithmetic on values.** For every balance-sheet instant of a monetary unit,
every pair of concepts is summed and the sum looked up among the same period's
concepts. A relationship surviving across ≥ 6 periods and ≥ 2 filers is an
accounting identity the filers actually report, whether or not anyone named it.

The search found, unprompted:

```
Liabilities + StockholdersEquity == Assets                                    5 filers
Liabilities + StockholdersEquity == LiabilitiesAndStockholdersEquity          5 filers
MinorityInterest + StockholdersEquity == StockholdersEquityIncluding…NCI      5 filers
PropertyPlantAndEquipmentNet + AccumulatedDepreciation == PPE Gross            5 filers
DeferredTaxAssetsNet + DeferredTaxAssetsValuationAllowance == …Gross           5 filers
OperatingLeaseLiability + Lessee…ExcessAmount == LeasePaymentsDue             5 filers
```

25 reproducible identities, 4 of them type A, **3 touching debt concepts**. The
balance-sheet equation and the depreciation roll-forward coming out of a pair sum
is the method validating itself: these are identities a reader would recognise,
found without being asked.

This is the direct answer to 2.29's lesson. There, four keyword passes each
admitted a different non-debt category. Here **nothing is filtered by name at
all** — the search finds whatever arithmetic holds, and the debt roles are
attached afterwards for labelling.

---

## C. The calibration sample, and the question it cannot answer

```
CB      INSURANCE     debt=COLLECTED    instants= 90   identities>=6 periods=80
CMI     MANUFACTURING  debt=COLLECTED    instants= 90   identities>=6 periods=54
LTRX    MANUFACTURING  debt=COLLECTED    instants= 67   identities>=6 periods=56
MSFT    SERVICES      debt=COLLECTED    instants= 94   identities>=6 periods=47
SSYS    MANUFACTURING  debt=COLLECTED    instants= 65   identities>=6 periods=19
STMEF   MANUFACTURING  debt=COLLECTED    instants= 38   identities>=6 periods=24
THRMV   MANUFACTURING  debt=COLLECTED    instants= 78   identities>=6 periods=40
```

Selected on the presence of co-reported concepts, which is a **selection
criterion and not evidence**.

**All seven have `debt = COLLECTED`.** They can answer *when a source supplies
these concepts together, what relationships hold*. They cannot answer *therefore
the eleven silent filers' `debt` should be reconstructed this way* — the eleven
report no current-side concept of any kind, so there is nothing to characterise
there. That is Case D and it is established, not assumed.

---

## D. Answers

**A. Observable component structure.** Partially, and not the one the
decomposition implies. Long-term debt's presentation split is source-proven across
three filers. And a second identity shows the two sides drawn from **different
bases** in CMI and THRMV, so the components cannot simply be added.

**B. Is a source-proven current-debt total reported?** **No.** Every total that
appears as the result of a reproducible identity is non-current-inclusive. No
identity derives a *current* total.

**C. Can `ShortTermBorrowings + LongTermDebtCurrent` be shown to be some
current-debt quantity?** **No, and now positively** — the candidate appears in 0
of the 25 reproducible identities.

**D. Resolvable only by future source evidence.**
- Whether any of the eleven silent filers reports a current-side concept or an
  entity-level total the registry does not reach. The calibration sample cannot
  say, because all seven of its filers already report `debt`.
- Whether current debt is reconstructible at all for a filer reporting neither
  component: Case D cannot be distinguished from Case A without a reported total.
- Whether the two sides are drawn from the same base in filers reporting both —
  CMI and THRMV demonstrably do not, and two filers is not a pattern.

---

## E. The qualification before a mapping is even arguable

> **ST-EVA's `debt` is declared as a *presentation* composition — current plus
> non-current. The totals the source reports are *entity-level total debt*. Those
> are different quantities.**

The identity that holds is a split of long-term debt that excludes capital leases
and short-term borrowings, and it says nothing about total debt. A **definition
match** has to be established before a mapping is arguable at all, and on this
evidence it is not.

So even a clean SUPPORTED on composition would not have been a licence to map
`ShortTermBorrowings`. It would have been a licence to ask a further question
about which quantity `debt` is meant to denote.

---

## F. Where the three research layers stand

| layer | status |
| --- | --- |
| 1. Semantic characterisation | done — `ShortTermBorrowings` is an outstanding carrying amount; it participates in no debt identity |
| 2. Composition characterisation | done — the declared split holds; no current total exists; bases differ across filers |
| 3. Coverage implication | **not reached.** Layer 2 does not establish that composition is reconstructible for a filer reporting no current-side concept |

Layer 3 is the only one that could justify touching `debt`'s vocabulary, and it
requires evidence this corpus does not contain. The seven calibration filers are
all filers that already work.

## G. State

| | |
| --- | --- |
| full suite | **714 run, 640 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| fetched | **nothing** |
| registry / mappings / coverage / applicability | **unchanged** |
| commits | 2.27 at `7cb5e27`; 2.28–2.31 not committed |

`debt_composition_231.py` is read-only and writes `harness/231-debt-composition.json`,
carrying every reproducible identity with its filers and period counts so the
verdict can be inspected rather than taken on trust.