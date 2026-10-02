# 2.35 — IFRS CAPEX characterisation

Read-only. No registry entry, no mapping, no metric definition, no applicability
rule, no fetch. `debt` closed at 2.33; the US-GAAP `capex` candidate is UNDECIDED at
2.34. This round is the two IFRS concepts 2.34 found behind five capex-silent
filers, validated **independently**.

| | verdict |
| --- | --- |
| **A** `ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities` | **UNDECIDED** |
| **B** `ifrs-full:AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment` | **UNDECIDED** |

The two share a root cause, and it is not the argument between them.

---

## A. Neither candidate has a source semantic anchor

```
  SEC label      : None
  SEC definition : None
```

**Both concepts return no label and no description.** The entire `ifrs-full` side of
this registry supplies neither in `companyfacts` — which 2.29 noted in passing when
it classified the `ifrs-full` debt candidates as "held as unresolved" and is here
measured properly.

So for A and B the only semantic signal available is **the concept name** — and the
critical rule for this round excludes exactly that. There is no statement
anywhere in the held evidence of what either concept measures.

This is a property of the source, not a gap in the analysis, and it is why both
verdicts are UNDECIDED rather than one being SUPPORTED on a technicality. It also
generalises what 2.30 said about vendor `totalDebt`: **a concept ST-EVA cannot
describe is not a concept ST-EVA can map.**

---

## B. What is measurable

| | A | B |
| --- | --- | --- |
| filers | 4 — BHP PAAS TECK TSM | 4 — BHP PAAS RIO TECK |
| periods | 47 | 39 |
| durations / instants | **47 / 0** | **39 / 0** |
| units | CAD, TWD, USD | CAD, USD |
| values positive / negative / zero | 62 / 0 / 0 | 41 / 0 / 0 |
| dimension-ambiguous periods | **15 of 47** | 2 of 39 |
| declared for `capex` | no | no |
| comparators in the same documents | `ifrs-full:PropertyPlantAndEquipment` only | `ifrs-full:PropertyPlantAndEquipment` only |

Three observations, each carefully bounded:

**Every fact is a duration.** A flow over a period, which is what a capital
outflow or an addition would be. It is consistent with the right shape and it
proves nothing about content — a non-cash addition is also a duration.

**No value is negative, in either candidate.** For A, whose name asserts a purchase,
that is consistent with a gross outflow. For B it does not discriminate at all: a
revaluation or a transfer would also be positive.

**Units are per-filer, not uniform.** TECK reports CAD, TSM reports both TWD and
USD, the rest USD. So even the unit is a property of the filer's presentation
rather than of the concept.

**And a quarter of A's periods are unusable for comparison.** 15 of 47 carry more
than one value for a period, which is dimension flattening — 9 of TSM's 12 periods
alone. Those periods cannot enter a value comparison at all.

### A against B, measured

Three filers report both — BHP, PAAS, TECK — giving **23 comparable periods,
every one `near_equal`, with B between 67% and 81% of A.**

```
BHP   2017-06-30  0.696
BHP   2018-06-30  0.749
BHP   2019-06-30  0.805
BHP   2022-06-30  0.667
BHP   2023-06-30  0.797
BHP   2024-06-30  0.807
```

A stable, consistent relationship — and an IFRS-internal one. **It compares two
unmapped IFRS concepts to each other, not to `capex`.** Per the critical rule it
is supporting evidence and nothing more: it cannot establish that either is capital
expenditure, and it cannot distinguish "A contains cash purchases B does not" from
"B contains non-cash additions A does not".

---

## C. Condition by condition

| condition | A | B |
| --- | --- | --- |
| 1 definition / accounting object | **NOT ESTABLISHED** — no label, no description | **NOT ESTABLISHED** — same |
| 2 cash-flow vs balance/movement | **PASS** — 47/0 durations | **PASS** — 39/0 durations |
| 3 asset scope | **NOT ESTABLISHED** — knowable only from the name | **NOT ESTABLISHED** — same |
| 4 acquisitions outside PPE | NOT ESTABLISHED | NOT ESTABLISHED — the name asserts an exclusion, and asserting it is not evidence |
| 5 non-cash additions possible | NOT ESTABLISHED | **NOT ESTABLISHED — and this is B's specific burden** |
| 6 unit / sign / period semantics | recorded: CAD/TWD/USD, all positive | recorded: CAD/USD, all positive |
| 7 a recognised capex comparator in the same document | **FAIL** — none | **FAIL** — none |
| 8 survives cross-filer comparison | **PARTIAL** — 23 periods against B, not against `capex` | **PARTIAL** — same |

Condition 7 fails for **both**, and it is the harder failure. Not one filer of
either candidate reports any declared `capex` concept. The only concept co-occurring
in their documents is `ifrs-full:PropertyPlantAndEquipment` — a **balance**, which
cannot serve as a flow comparator.

---

## D. The silence, classified

27 `capex = SOURCE_SILENT` filers. **20 have a document on disk; 7 do not**, and
that is reportable in its own right — a silent filer with nothing to read cannot be
characterised at all.

```
both A and B                                   3   BHP PAAS TECK
A only                                          1   TSM
B only                                          1   RIO
neither, but other capex-shaped concepts        6   BBAR CCXIU EFC HPP NU WPM
neither                                         9   AFL CB CONC FMCCH GNW ORXCF PFG PRU TRV
no document on disk                             7   AILLP BNH BPYPN BRCNF CELZ CIG-C IPB
```

So the two IFRS candidates reach **5 of the 20 characterisable silent filers** —
the same five 2.34 identified. Consistent, and it confirms the IFRS gap is the
larger one rather than a restatement of the previous finding.

The six in "neither, but other" include CCXIU, EFC and HPP, which report the
2.34 candidate `PaymentsForCapitalImprovements` — itself UNDECIDED. **Four
filers are blocked on a semantic anchor the held evidence does not contain**:
three on a US-GAAP concept whose definition exists but conflicts with its
arithmetic, three on IFRS concepts that have no definition at all.

---

## E. Verdict, and what would change it

**Both UNDECIDED**, on three blockers, identical for both plus one that only
applies to B:

1. **No label, no description.** The accounting object cannot be stated.
2. **No recognised comparator in any filer.** No cross-framework comparison is
   possible at all.
3. **B only: the non-cash question.** An *addition* to PPE excluding business
   combinations can be non-cash — a revaluation, a transfer, an exchange — so B has
   to show its additions carry no material non-cash source before its numbers can
   be read as capital expenditure. That is exactly what a definition would answer,
   and there is none.

**What would move either verdict:**

- **A statement of what the concept measures.** The filing's own taxonomy
  reference, or a statement of presentation context. This is the blocker that
  matters, and it is not obtainable from an aggregated document.
- **A filer reporting the candidate together with a declared `capex` concept in the
  same period.** None of the four filers of either candidate does, so there is
  currently no measurement that could substitute for the definition — and that is
  worth stating plainly, because it means more fetching would not fix this.
- **For B specifically:** evidence that additions in these periods have no
  non-cash component. The A-vs-B relationship — B at 67–81% of A across 23 periods
  — is consistent with one and equally consistent with the other, and cannot
  distinguish them.

**Deliberately not done.** No mapping added. No `PARTIAL` promoted. No definition
edited. No applicability rule created. Nothing fetched. `debt` untouched.

---

## State

| | |
| --- | --- |
| full suite | **744 run, 670 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| commits | `1a37225` (2.33) · 2.34 and 2.35 uncommitted |

`ifrs_capex_characterisation_235.py` reads only the archives and the documents
already on disk, and writes `harness/235-ifrs-capex.json` with both concepts'
per-filer counts, shapes, units, signs, dimension ambiguity, the measured A-against-B
relationship, the comparator check, the silent-filer classification and the
condition table per candidate.