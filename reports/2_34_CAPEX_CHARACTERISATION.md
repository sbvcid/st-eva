# 2.34 — CAPEX vocabulary characterisation

Read-only. No registry entry, no mapping, no metric definition, no applicability
rule, no fetch. `debt` is closed at 2.33 and untouched here.

**Proposition**

> Does `us-gaap:PaymentsForCapitalImprovements` denote the same accounting
> quantity that Core `capex` is declared to preserve?

**Verdict: UNDECIDED** — and the reason is nameable rather than vague.

---

## A. `PaymentsForCapitalImprovements`, in its own words

```
us-gaap:PaymentsForCapitalImprovements   "Payments for Capital Improvements"

  "The cash outflow for acquisition of or capital improvements to properties
   held for investment (operating, managed, leased) or for use."

  declared for capex : no
  filers              : 7
  periods             : 124        accessions: 106
  instants / durations: 0 / 124    unit: USD throughout
  forms               : 10-K, 10-Q, 20-F
  dimension ambiguity : 6 of 21 periods (RBC), 6 of 21 (CIK0001324948)
```

It is unambiguously a **cash outflow**, and every fact is a duration — a flow over
a period, which is what a cash outflow is. Conditions 1 and 3 pass outright.

Its scope clause is the problem. **"Properties held for investment"** is a
*purpose* restriction: investment property is not an asset *used in the normal
conduct of business to produce goods and services*, which is the metric's own
declared scope. Investment property is a distinct balance-sheet object under both
ASC 360 and IAS 40, not a subset of productive assets.

Values can be negative — EFC reports −168,000 for 2026-06-30 — which a gross
capital-expenditure line does not usually do.

---

## B. Its relationship to Core `capex`

**The arithmetic says "same quantity". The definition says "different object".
They cannot both be right, and nothing here settles it.**

For the three filers that report **both** `PaymentsForCapitalImprovements` and the
declared EXACT concept:

```
CIK0001324948   equal 3,  near_equal 1
RBC             equal 3,  near_equal 1
MLCO            different 1
                              9 comparable periods: 6 equal, 2 near_equal, 1 different
```

So 8 of 9 periods carry the same value. That is strong evidence of sameness — and
it comes from filers that **already have `capex` collected**, so none of them is
part of the population that needs this mapping.

**For the three filers where `capex` is `SOURCE_SILENT` — CCXIU, EFC, HPP — there
is no comparator at all.** Each reports the candidate alone. The evidence for
sameness was measured somewhere the mapping is not needed.

That asymmetry is why the verdict is UNDECIDED rather than either way.

---

## C. The three candidates side by side

| | `PaymentsToAcquirePropertyPlantAndEquipment` | `PaymentsToAcquireProductiveAssets` | `PaymentsForCapitalImprovements` |
| --- | --- | --- | --- |
| declared | **EXACT** | **PARTIAL** | *unmapped* |
| SEC scope | long-lived **physical** assets used in production, plus self-construction | that **plus software and intangibles** | **property held for investment** (operating, managed, leased) |
| filers / periods | 47 / 2,364 | 14 / 347 | 7 / 124 |
| units | USD | USD | USD |
| shape | durations | durations | durations |

**A finding about the registry's own typing, which came out of the comparison.**
Where filers report both declared concepts, the values are **identical in 23 of 23
comparable periods** — so the declared scope widening (`EXACT` → `PARTIAL`, physical
→ physical plus intangibles) is **real in the definitions and invisible in the
numbers** on this corpus.

That is worth knowing before using value arithmetic to settle the next question.
Two concepts with different declared scopes producing identical values everywhere
they co-report is exactly the situation where arithmetic can confirm a relationship
it cannot distinguish from a third thing.

**No filer reports both** `PaymentsToAcquireProductiveAssets` and
`PaymentsForCapitalImprovements`, so no nesting or additivity test against the
broader declared scope is available at all.

---

## D. The silence is mostly *not* this concept

2.28 found `PaymentsForCapitalImprovements` in three silent filers. Across the 20
`capex = SOURCE_SILENT` filers that have a document on disk:

```
report PaymentsForCapitalImprovements                      3   CCXIU EFC HPP
report an unmapped IFRS capex concept                      5   BHP PAAS RIO TECK TSM
neither                                                    12   AFL BBAR CB CONC FMCCH
                                                              GNW NU ORXCF PFG PRU TRV WPM
```

**The larger gap is the IFRS vocabulary.** Five IFRS filers report

```
ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities
ifrs-full:AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment
```

neither of which is declared — and they are the IFRS presentations of the very
quantity the US-GAAP concept captures. So `capex`'s vocabulary gap is **not
primarily a US-GAAP gap**, and a round spent on the US-GAAP candidate would have
addressed 3 filers of 20.

The remaining 12 report only what 2.29 warned about, and none of it is capital
expenditure: securities purchases, business combinations, *balances* rather than
flows (`PropertyPlantAndEquipmentNet` / `Gross`), depreciation, deferred tax, and
useful-life metadata. Three near-misses worth naming for a later round:
`PaymentsToAcquireRealEstateHeldForInvestment` and
`PaymentsToAcquireOtherRealEstate` (TRV, HPP, PFG),
`PaymentsToAcquireEquipmentOnLease` (ORXCF), and
`PaymentsToAcquireOtherProductiveAssets` / `...OtherPropertyPlantAndEquipment`
(ORXCF).

WPM deserves its own line: an IFRS filer whose document carries
`ifrs-full:PropertyPlantAndEquipment` — a **balance** — and no capex flow concept
at all. Its capital expenditure is not in the aggregated document, which is a
source-availability fact and not a vocabulary gap.

---

## E. The verdict, condition by condition

| condition | |
| --- | --- |
| 1 definition describes a cash outflow | **PASS** — "The cash outflow for…" |
| 2 quantity is capex or a provably equivalent quantity | **NOT ESTABLISHED** — the purpose clause narrows it to investment property |
| 3 period / unit / basis compatible | **PASS** — USD, 0 instants / 124 durations |
| 4 clear correspondence of asset scope | **NOT ESTABLISHED** — "held for investment" against "used in production" |
| 5 reproducible across filers and periods | **PARTIAL** — 8 of 9, and none of it in the population that needs it |
| 6 differences are scope, not a different accounting object | **CONTESTED** — the blocker |
| 7 no name-substring reliance | **PASS** |
| 8 no intuition | **PASS** |

Three conditions fail, and two of them fail *against each other*: the values say
one quantity, the source's own definition says another.

---

## F. Which evidence produced it, and what would move it

**UNDECIDED** because the two strongest anchors disagree:

- **Value arithmetic** — 8 of 9 comparable periods equal or near-equal against the
  declared EXACT concept, which is what a `PARTIAL` or `EXACT` mapping would want.
- **The SEC's own definition** — "properties held for investment", a distinct
  balance-sheet object, not a subset of assets used in production.

**The named blocker is statement context.** `companyfacts` carries concepts and
values but not the presentation link, so nothing in what is held can say whether
`PaymentsForCapitalImprovements` sits on the cash-flow statement's capital
expenditure line or on an investment-property line. That is the one piece of
evidence that would break the tie, it is not obtainable from these documents, and
answering it means reading a filing rather than an aggregated one.

Two further things that would change the verdict, and are worth recording because
they are cheaper than a filing read:

1. **A filer reporting all three concepts in one period** would let
   `PaymentsToAcquireProductiveAssets` and `PaymentsForCapitalImprovements` be
   compared, which no filer currently permits. That is the missing third anchor.
2. **A `PaymentsForCapitalImprovements` filer that also reports the declared
   concepts** would put the comparator inside the population that needs it. All
   three co-reporters are filers whose `capex` is already collected.

**What was deliberately not done.** No mapping was added or promoted; a `PARTIAL`
was not upgraded; no metric definition was edited; no applicability rule was
created; nothing was fetched. `debt` was not touched.

---

## State

| | |
| --- | --- |
| full suite | **744 run, 670 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| commits | `1a37225` (2.33) · 2.34 uncommitted |

`capex_characterisation_234.py` reads only the archives and the raw documents
already on disk, and writes `harness/234-capex-characterisation.json` with every
concept's SEC label and definition, per-filer counts, period shapes, units,
dimension ambiguity, representative raw facts, and the measured relationships.