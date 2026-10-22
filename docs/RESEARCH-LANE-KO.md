# The KO research case

The Coca-Cola Company (CIK 0000021344) is the first case for the research
calculation lane. The lane is described in
[RESEARCH-LANE.md](RESEARCH-LANE.md); this document records the case: what
was captured, what the lanes computed, what the registry said, and what the
evidence turned out to say.

KO has no production P/S and no production EV/EBITDA. The registry holds no
mapping for the element KO files for revenue, and the depreciation element is
scoped to other filers. Every figure below is a research figure, computed
from the same filed facts the production pipeline reads, published under its
own name, and eligible for nothing.

## The capture

`data/research_multiples/KO/`, built by the general builder,
`tools/build_research_capture.py --ticker KO`, from the element table in
`data/research_issuers.json`.

| | |
|---|---|
| Issuer | The Coca-Cola Company, CIK 0000021344, fiscal year end 12-31 |
| Acceptance index | 67 periodic filings (10-K and 10-Q), usable dates 2010-02-26 to 2026-07-29 |
| Price series | 4,204 daily bars, 2010-01-04 to 2026-09-21, with the 2012-08-13 2:1 split event |
| Concept elements | ten filed elements and one cover-page element, 1,410 facts in all |
| Source | the SEC's company facts payload for the issuer, SHA-256 recorded in the manifest |

The acceptance datetime comes from each filing's SGML header for 49 filings.
For 18 filings from 2010 to 2013 the SEC generated no filing index for the
capture to read, and the submissions API's acceptance datetime, converted to
America/New_York, is used instead. The basis is recorded per filing, and the
capture says which is which.

The general builder now reads the header out of the full submission itself
when the filing index does not carry it, so a capture built today would hold
the header's own time for all 67 filings. KO's committed capture is not
rebuilt, so it still holds the API's time for those 18; for KO the two clocks
agree to the second, so the instants it records are the same either way, and
the identity the phase 9.9 run pinned is untouched. The divergence is real
for other filers -- AAPL's API runs four to five hours late -- and it is
recorded per filing in the capture as the difference in hours.

The acceptance times carry the Eastern offset of their own date, so a
standard-time filing is written at five hours from UTC and a daylight-time
filing at four. Every record now holds the instant the SEC's own submissions
API states, and the capture's usable dates follow the 16:00 ET rule without
exception. Three annual filings -- the FY2018, FY2019 and FY2022 10-Ks -- were
accepted between 16:00 and 17:00 Eastern, so each of them becomes knowable
on the next trading day rather than on the day it was accepted. That is the
rule the production resolver applies; the capture had been recording those
instants an hour early, which made the three filings look knowable a day
before they were.

The SEC's company concept endpoint serves `us-gaap:Revenues` with empty
units for this filer, so the rows come from the issuer's fact set in the
company facts payload. The capture records the substitution for that element
and for no other.

## What the registry said

Read from the core registry through `semantic_qualification.qualify_element`,
and recorded on every observation.

| Role | Element | Decision | Reason |
|---|---|---|---|
| revenue | `us-gaap:Revenues` | NOT_QUALIFIED | `NO_MAPPING_FOR_METRIC` — retired as a source of the `revenue` metric in decision 2.99 |
| revenue | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | QUALIFIED | the accepted element, but KO files no fact on it |
| operating_income | `us-gaap:OperatingIncomeLoss` | QUALIFIED | `QUALIFIED_EXACT_IDENTITY_MAPPING` |
| depreciation_and_amortization | `us-gaap:DepreciationDepletionAndAmortization` | NOT_QUALIFIED | `SCOPE_NOT_APPLICABLE` — the registry maps this element for Apple and Nike alone |
| cash | `us-gaap:CashAndCashEquivalentsAtCarryingValue` | QUALIFIED | exact identity |
| long_term_debt_noncurrent | `us-gaap:LongTermDebtNoncurrent` | QUALIFIED | exact identity |
| long_term_debt_current | `us-gaap:LongTermDebtCurrent` | QUALIFIED | exact identity |
| marketable_securities_current | any | NOT_APPLICABLE | `NO_SUCH_REGISTRY_METRIC` |
| commercial_paper | `us-gaap:CommercialPaper` | NOT_APPLICABLE | `NO_SUCH_REGISTRY_METRIC` |
| notes_and_loans_payable | `us-gaap:NotesAndLoansPayable` | NOT_APPLICABLE | `NO_SUCH_REGISTRY_METRIC` |

The last three are not refusals. The registry declares no metric for them,
so it has no opinion on the element, and the filed-bridge specification
governs them.

## What production says about the same capture

The production pipeline, run over the same filed facts, refuses both of KO's
production figures:

| Production metric | Status | Reason |
|---|---|---|
| `P_S_RATIO_REFERENCE` | UNAVAILABLE, 0 observations | `REASON_NO_QUALIFIED_REVENUE_ELEMENT` on all 67 dates |
| `EV_EBITDA_RATIO_REFERENCE` | UNAVAILABLE, 0 observations | `REASON_NO_QUALIFIED_DA_ELEMENT` on all 67 dates |

This is the case the research lane exists for, and it is also the case the
research lane does not change: KO is not qualified for production, and
nothing in the research tree makes it so.

The two pipelines compute the same figures on the same evidence. Over this
capture the production pipeline and the research lane produce the same price,
the same cover-page share count and the same market capitalisation on all 67
dates, and the same enterprise value on all 11 dates at which the production
bridge is complete. The production bridge is complete on 11 of the 67 dates
because commercial paper's annual-only reporting leaves it spanning two
balance sheets at the quarterly dates, and the research lane's own bridge
carries the same condition. What differs is the gate and the name, not the
arithmetic.

## The lanes

Four candidate research metrics and one diagnostic. Every figure below is
recomputed from the capture by the lane; the committed summary under
`data/research_lanes/KO/` carries one line per evaluation date, so each
statistic can be recomputed from it.

| Lane | Metric id | Valid | Refused | Sample period | Median | Mean | Std dev |
|---|---|---:|---:|---|---:|---:|---:|
| A | `RESEARCH_KO_REPORTED_REVENUE_MULTIPLE` | 29 | 38 | 2019-07-26 … 2026-07-29 | **6.403373** | 6.460903 | 0.562180 |
| B | `RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE` | 64 | 3 | 2010-10-29 … 2026-07-29 | **19.774421** | 19.092492 | 3.835147 |
| C1 | `RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE` | 27 | 40 | 2011-02-28 … 2026-07-29 | **23.654283** | 23.133471 | 4.294477 |
| C2 | `RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS` | 29 | 38 | 2018-10-30 … 2026-07-29 | **24.675484** | 24.753179 | 2.331508 |
| C3 | `RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_DOUBLE_COUNTED_DIAGNOSTIC` | 16 | 51 | 2019-02-21 … 2026-07-29 | 25.556776 | 25.731022 | 2.574429 |

Every lane evaluates all 67 usable dates. Percentiles are on the same
convention the production distributions use.

### A — KO's reported revenue

`(as-traded close x cover-page shares outstanding) / TTM of us-gaap:Revenues`

The denominator is KO's reported net operating revenues, on the element KO
files. It is not a price-to-sales reference and it does not claim to be.

Thirty-eight dates are refused with `RESEARCH_REASON_NO_DENOMINATOR_WINDOW`,
and the reason is a window discontinuity rather than a shortage of filings:
KO tagged its net operating revenues on `us-gaap:SalesRevenueGoodsNet` until
the FY2018 10-K, and the `us-gaap:Revenues` element carries no knowable
version of the earlier years before 2019-02-21. A four-quarter window on that
element therefore exists only from 2019-07-26.

### B — KO's reported operating profit plus its reported D&A

`(as-traded close x cover-page shares outstanding) / TTM of (us-gaap:OperatingIncomeLoss + us-gaap:DepreciationDepletionAndAmortization)`

The two roles are paired quarter by quarter. A quarter that carries only one
of them is absent, not half a quarter, and a window is refused rather than
assembled from mismatched quarters. Three dates are refused for want of four
discrete quarters: 2010-02-26, 2010-04-29 and 2010-08-02, before KO's FY2009
fourth quarter could be derived.

This figure is not EBITDA and does not claim to be. The registry does not
accept KO's depreciation element for the depreciation-and-amortization
metric, and the lane records that refusal on every observation. KO's separate
`us-gaap:Depreciation` element, from the property note, is disclosed only
annually and cannot carry a quarterly trailing window at all.

### C1 — the filed bridge in the production shape

`EV = market cap + (long-term debt non-current + long-term debt current + commercial paper) - (cash and cash equivalents + current marketable securities)`

One observation is refused for an incomplete bridge and thirty-six for a
bridge whose components describe more than one balance-sheet date. The cause
is commercial paper: KO does not carry a commercial paper line on the face
of its balance sheet, and discloses commercial paper as a component of loans
and notes payable in its debt note, so KO files the element annually only
until 2023. At a quarterly evaluation date the commercial paper in force is
the previous 10-K's 31 December figure while every other component is the
quarter's own, and the bridge spans two balance sheets. The stale component
is not carried forward.

### C2 — loans and notes payable in place of commercial paper

The same bridge, with `us-gaap:NotesAndLoansPayable` replacing
`us-gaap:CommercialPaper`.

KO's balance sheet carries **Loans and notes payable** as the total of its
short-term borrowings. The FY2025 10-K shows no commercial paper line on the
face of the balance sheet, and the debt note states that loans and notes
payable consist primarily of commercial paper. The filed values satisfy

```
us-gaap:NotesAndLoansPayable = us-gaap:CommercialPaper + us-gaap:OtherShortTermBorrowings
```

at every date at which both are reported: 1,495 + 56 = 1,551 at 2025-12-31,
1,139 + 360 = 1,499 at 2024-12-31, and so on back to 2019-12-31.

Three consequences follow, and the lanes are built on all three.

1. The substitution is **scope-correct**: the role stands for KO's total
   short-term borrowings, which is what a short-term-debt component of an
   enterprise-value bridge is for.
2. A bridge holding **both** commercial paper and loans and notes payable
   counts commercial paper twice. That is what the diagnostic lane measures.
3. The substitution changes the bridge's **coverage**. The element exists
   from 2017-12-31, as `us-gaap:NotesAndLoansPayableCurrent` until 2019-12-31
   and as `us-gaap:NotesAndLoansPayable` after it. Thirty-two dates are
   refused for an incomplete bridge because the element is not yet filed, and
   three more for a bridge spanning two balance sheets.

**The two medians are not a measure of debt.** C1's 23.654283 and C2's
24.675484 differ by 1.036049, but the two lanes sample different dates
against different balance-sheet compositions, and C1's sample is the one
constrained by commercial paper's annual reporting. The difference is a
difference of scope and of sample. It is not a finding about KO's leverage,
and the lanes do not offer it as one.

### C3 — the double-count diagnostic

Not a candidate metric. It is not among the selectable research metrics, its
`candidate_metric` flag is false, and its formula is written so that it
cannot be mistaken for an acceptable enterprise-value definition. It exists
to measure what a bridge holding both components would overstate.

On the sixteen dates where the diagnostic and C2 both publish, the
double-counted bridge is **+0.0161 to +1.3349** higher than the correct one,
which is **+0.06% to +5.79%** depending on how much commercial paper was
outstanding.

## The element changes

Three changes in the evidence are recorded as basis breaks rather than
absorbed.

**Marketable securities: a re-tagging.** KO's "Marketable securities" line
is carried on `us-gaap:MarketableSecuritiesCurrent` through 2020-12-31 and on
`us-gaap:MarketableSecurities` afterwards. Where both are reported they
carry the same filed value, so the change is a re-tagging of the same
quantity, and the lane says so.

**Long-term debt: a scope change.** `us-gaap:LongTermDebtNoncurrent` and
`us-gaap:LongTermDebtCurrent` are filed through 2024-03-29. From 2023-12-31
KO carries the same lines on `us-gaap:LongTermDebtAndCapitalLeaseObligations`
and its current counterpart, whose definitions include the lease obligation
where the earlier elements excluded it. The element change is therefore also
a scope change, and the lane declares it as one.

**The consolidation of Coca-Cola Beverages Africa: value revisions.** KO
re-presented its income statement for the consolidation of Coca-Cola
Beverages Africa, and the lane's R-9 rule detects the change as a
prior-period value revision:

| Period | Old value | New value | Difference | Detected |
|---|---:|---:|---:|---|
| FY2017 | 35,410,000,000 | 36,212,000,000 | +802,000,000 (+2.26%) | 2020-02-24 |
| FY2018 | 31,856,000,000 | 34,300,000,000 | +2,444,000,000 (+7.67%) | 2020-02-24 |
| 9M 2018 | 24,798,000,000 | 26,494,000,000 | +1,696,000,000 (+6.84%) | 2019-10-24 |
| Q3 2018 | 8,245,000,000 | 8,775,000,000 | +530,000,000 (+6.43%) | 2019-10-24 |
| Q1 2019 | 8,020,000,000 | 8,694,000,000 | +674,000,000 (+8.40%) | 2020-04-24 |

Operating income was re-presented as well, in twenty revisions across the
sample. The lane classifies them `PRIOR_PERIOD_VALUE_REVISION`: the evidence
shows that a value it already knew was replaced by a different value. It does
not show that the issuer formally restated, and it does not say so.

Three observations in each lane carry a mixed-basis note. At 2019-10-24 the
quarter ending 2018-12-31 is derived from the FY2018 annual figure, which
was not yet re-presented, and the nine-month figure, which was. The same
condition arises at 2012-10-25 and 2018-10-30. The quarter is made of a
pre-revision figure and a post-revision figure and is on neither basis, and
the lane records that on the observation rather than absorbing it.

## The limits of this case

- **The capture's acceptance index covers periodic filings only.** A fact
  first published in another form becomes knowable in the lane at the next
  periodic filing that carries it. The lane never uses a value before it was
  public, and it may use a value later than it first became public. For KO
  this means the consolidation of Coca-Cola Beverages Africa, published in a
  form 8-K on 2019-09-20, is first knowable in the lane at the FY2019 10-K's
  usable date of 2020-02-24.
- **The enterprise-value bridge is a partial statement of enterprise value.**
  It omits operating leases under ASC 842, non-current investments and
  off-balance-sheet commitments, and it is never presented as the whole of
  enterprise value.
- **The bridge's liquid funds are cash and the current marketable securities
  line.** KO carries a separate "Short-term investments" line, which this
  bridge does not net out.
- **A sample is a sample.** The lane reports its sample size and its sample
  period. It does not assert that the sample describes anything beyond the
  period it covers, and it does not offer the distribution for production
  use at any size.

## The reconciliation with the phase 9.2 audit

The phase 9.2 design round recorded four cross-check figures. They are
reproduced here from the committed capture, and they are a cross-check rather
than an input: every figure in this document is recomputed by the lane.

| Lane | Phase 9.2 | Recomputed | Match |
|---|---:|---:|---|
| A | 29 valid, median 6.403373 | 29 valid, median 6.403373 | yes |
| B | 64 valid, median 19.775345 | 64 valid, median 19.774421 | the median moved |
| C1 | 27 valid, median 23.639435 | 27 valid, median 23.654283 | the median moved |
| C2 | 29 valid, median 24.675484 | 29 valid, median 24.675484 | yes |

The two medians that moved belong to the two lanes that publish an
observation on each of the three annual filings whose acceptance times were
corrected. The valid counts are unchanged, and the change is confined to
three evaluation dates. The figures that moved moved because the evidence
behind them became knowable a day later than the capture had said, not
because the arithmetic changed: the phase 9.5 audit's independent
recomputation, run against the corrected capture, agrees with the lane on
every one of the 67 dates.

The phase 9.2 report's acceptance criteria listed the exclusion counts as
`38 + 3 + 37 + 35 + 19`. The counts taken from the observation records are
`38 + 3 + 40 + 38 + 51`. The two bridge lanes' counts in that list omitted
the three window refusals each of them carries, and the diagnostic lane's
count of nineteen was neither its valid count nor its refusal count. The
counts in this document are the ones the records carry.

One number from the phase 9.1 audit could not be reproduced from the filed
inputs under any of the bridge, denominator, element or sample variants that
were tested, and it is not carried forward as an expectation anywhere. It is
recorded as an unattributed historical figure. The test suite asserts that
it appears in no research output, no source file and no document.

## What this case does not do

It does not qualify KO for production. It does not change a registry
decision, extend a registry scope, or add a registry metric. It does not
change the production bridge, the production window, the production
point-in-time rule or the production sample gate. It does not add a
production issuer, and it does not touch any production dataset, valuation
result or Archive.

What it does add is a traceable, reproducible capacity to state a figure
about filed evidence that the production regime does not admit, and to say
exactly what that figure is and exactly what it is not.
