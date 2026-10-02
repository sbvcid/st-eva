# 2.36 — Primary-source capex context resolution

The semantic blockers 2.34 and 2.35 left are resolved by going to the filing
rather than to the aggregate. Read-only: no registry entry, no mapping, no
promotion, no definition change, no applicability rule, no historical observation
touched.

**24 requests, 0.1 MB.** The first version of this fetched every R-file in every
filing — 1,535 requests for a question three documents answer. Only cash-flow and
PPE-note reports can answer a capex question, so only those are now fetched.

Labels used below, so the verdict is unambiguous:

| | concept |
| --- | --- |
| **A** | `us-gaap:PaymentsForCapitalImprovements` |
| **B** | `ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities` |
| **C** | `ifrs-full:AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment` |

| | verdict |
| --- | --- |
| **A** | **UNDECIDED, narrowed** — cash-flow semantics settled and supported; accounting object still filer-dependent |
| **B** | **SUPPORTED for the accounting object and cash-flow semantics**, with a filing-evidenced condition that must be handled before mapping |
| **C** | **REFUTED** — presented as a property, plant and equipment note line, not a cash outflow |

---

## A. `PaymentsForCapitalImprovements` — EFC

**Filing:** CIK 1411342, accession 0001628280-26-055148, 10-Q · **Report:** R7.htm,
*"Consolidated Statement of Cash Flows"*, MenuCategory **Statements**

```
section : Cash Flows from Investing Activities:
row     : Payments for Capital Improvements
values  : (168)   0
```

**The presentation resolves the tension 2.34 could not.** The SEC description said
"properties held for investment (operating, managed, leased)"; the arithmetic said
"the same value as `PaymentsToAcquirePropertyPlantAndEquipment`". Both are right,
and they are not in conflict — the description names the *asset class* the filer
improved, while the presentation fixes the *measurement basis*. The concept sits on
the consolidated statement of cash flows, under investing activities, as a cash
outflow. It is not a note movement wearing a cash-flow name.

The rendered value −168 (thousands) is exactly the −168,000 that `companyfacts`
carries, so the two layers are confirmed end to end.

**What is settled:** cash-flow semantics. It is a cash outflow classified as an
investing activity, on the face of the statement.

**What is not:** whether the accounting object equals Core `capex`. Core `capex` is
"cash outflow to acquire long-lived assets **used in the normal conduct of
business**". EFC is a mortgage real estate investment trust, so for EFC the property
it improves *is* its operating business — which supports the match. **That is a
statement about EFC, and only EFC was retrieved.** The three US-GAAP filers in
priority (EFC, HPP, CCXIU) were not all resolved; the run resolved the first and
stopped.

So A is **UNDECIDED and narrower than it was**, not resolved.

---

## B. `PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities` — TSM

**Filing:** CIK 1046179, accession 0001193125-25-083423, 20-F

**R5.htm — "Consolidated Statements of Cash Flows"** (Statements)

```
section : CASH FLOWS FROM INVESTING ACTIVITIES
row     : Acquisitions of property, plant and equipment
values  : (956,006.5)  (29,155.4)  (949,816.8)  (1,082,672.1)
```

The accounting object is acquisitions of property, plant and equipment, presented as
a negative figure under investing activities. That is a cash outflow for PPE —
matching Core `capex`'s accounting object and cash-flow semantics exactly.

**But the same concept appears a second time, and this is the condition.**

**R152.htm — "Cash Flow Information - Schedule of Detailed Information"** (Details)

```
section : Disclosure of detailed information about non-cash transaction [line items]
row     : Payments for acquisition of property, plant and equipment
values  : 956,006.5   $ 29,155.4   949,816.8   $ 1,082,672.1
```

**Identical magnitudes, opposite sign, in a schedule headed non-cash transaction
line items.** Two different facts sharing one concept: the cash outflow in the
statement, and something disclosed in the non-cash schedule. Whether TSM discloses
a genuinely non-cash acquisition under this concept, or re-presents the same
acquisition under the schedule's heading, **cannot be settled from these two
documents** — and it has to be settled, because ST-EVA collects by concept and not
by statement context, so a mapping would import both.

**Verdict: SUPPORTED** for the accounting object and the cash-flow semantics, as
the pre-registered bar requires. **Not yet map-ready**, and the blocker is not
semantic ambiguity — it is that the concept's use is broader than the cash outflow
its row suggests, which only the filing revealed.

This is the finding that justifies the round having gone to primary source. The
name asserts *investing activities*, `companyfacts` says nothing, and the cash-flow
statement alone would have said SUPPORTED with no caveat at all. Only reading the
*second* report in the same filing surfaced it.

---

## C. `AdditionsOtherThanThroughBusinessCombinationsPropertyPlantAndEquipment` — BHP

**Filing:** CIK 811809, accession 0001193125-25-185641, 20-F

**R108.htm — "Property, Plant and Equipment - Summary of Property, Plant and
Equipment (Details)"** · MenuCategory **Details** — a **note**, not a statement.

```
section : Disclosure of detailed information about property, plant and equipment
row     : Additions
values  : 11,500 / 10,926    28 / 27    1,653 / 1,206    1,066 / 795
```

Four separate `Additions` rows, consistent with additions broken down by asset
class, inside a **property, plant and equipment roll-forward**. It appears in **no
cash-flow statement** — the scan covered every cash-flow and PPE report in the
filing.

**The special rule applies directly:** the filing does not establish that these
additions exclude material non-cash additions, and the presentation is evidence
they do not. A roll-forward's additions are an asset movement — the line exists to
reconcile opening balance to closing balance, which is a different measurement
object from a cash outflow even in a period where every addition happened to be
cash. Core `capex` is defined as a *cash outflow*, and this concept is not
presented as one.

**REFUTED**, on affirmative evidence of a materially different measurement basis.
This closes 2.34's and 2.35's open item without further research.

---

## D. What changed across the three rounds

```
2.34  PaymentsForCapitalImprovements  UNDECIDED   definition said "investment
                                                 property", arithmetic said "same
                                                 as PPE capex", and neither could
                                                 say which
2.35  PurchaseOfPPE...                 UNDECIDED   no label, no description, no
                                                 comparator in any filer
      Additions...                     UNDECIDED   same

2.36  A  UNDECIDED, narrowed           the cash-flow basis is now established
                                          from the statement face; only the
                                          accounting object remains, and it is
                                          filer-dependent
      B  SUPPORTED, conditioned        cash-flow investing line for PPE
                                          acquisitions -- and the same concept
                                          also appears in a non-cash schedule,
                                          which only the filing revealed
      C  REFUTED                       a PPE note roll-forward line labelled
                                          "Additions", never a cash-flow line
```

**The two UNDECIDED pair in 2.35 turned out not to be equally blocked.** B was
waiting for exactly the evidence this round gathered. C was waiting for evidence
that, once seen, points the other way — and had more been fetched from
`companyfacts` it would never have appeared, because the aggregate simply does not
say where a concept is presented.

---

## E. Scope limits, recorded rather than glossed

- **One filer per candidate.** EFC for A, TSM for B, BHP for C — the first of
  each priority list, and the run stopped there. The instructions asked for at
  least one representative filing and no substitution was needed, because these
  were the target filers. But every finding is a **single-filer** finding, and
  A's accounting-object question is explicitly filer-dependent.
- **B's non-cash schedule appearance is unresolved.** It is either a genuinely
  non-cash acquisition disclosed under the same concept, or the same acquisition
  re-presented. Resolving it needs the cash-flow statement's own non-cash
  reconciliation, which was not fetched.
- **The scan is report-name filtered.** Only reports whose `ShortName` mentions
  cash flows or property, plant and fixed assets were fetched. A concept presented
  elsewhere would not have been seen. For these three that is very likely
  complete — each was located in the report its subject belongs to — but it is a
  filter, not an exhaustive search.
- **Dimension-flattened values were not re-examined** at the presentation layer;
  2.34 and 2.35 recorded that 15 of A-equivalent periods and 2 of B-equivalent
  periods carry multiple values, and those periods remain unusable for
  comparison.

---

## F. State

| | |
| --- | --- |
| full suite | **744 run, 670 passed, 74 skipped**, unchanged |
| production files changed | **none** |
| registry / mappings / definitions / applicability | untouched |
| historical observations | untouched |
| requests | **24**, 0.1 MB |

`primary_capex_context_236.py` reads the filing presentation layer through the
repository's own SEC transport — the provider's User-Agent, cookies, throttle and
fetch log, so the request count above covers everything this round asked of EDGAR —
and writes `harness/236-primary-capex-context.json` with the report, section, row
label and values for every hit.

**Next.** B is the only candidate that could become a mapping proposition, and
its condition is concrete: establish what TSM's non-cash schedule row represents.
A is decided per filer and needs the other two. C needs nothing.

No mapping proposed, nothing committed.