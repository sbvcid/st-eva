# The AAPL research lane

Apple Inc., CIK `0000320193`, is the second issuer the research lane carries.
Its configuration is in `data/research_issuers.json`, its capture is in
`data/research_multiples/AAPL`, its results are in
`data/research_lanes/AAPL`, and the engine that computes them is the same
engine KO's lanes use.

This document records what AAPL's data actually looks like, what the lanes
made of it, and what could not be established.

## The issuer

The identity is not taken from the ticker. The SEC's own submissions API
states the entity as **Apple Inc.**, CIK `0000320193`, SIC 3571 (electronic
computers), with a fiscal year end of 09-26 -- the last Saturday of September,
not a calendar quarter end. The capture's manifest records the CIK, the entity
name and the fiscal year end it was built from.

## The capture

The capture was built by the general builder from the configuration's element
table, with no issuer-specific code:

```
python tools/build_research_capture.py --ticker AAPL
```

| | |
|---|---|
| Periodic filings | 67 (10-K and 10-Q) from 2010-01-25 to 2026-07-31 |
| Earliest filed date | 2010-01-01 |
| Price series | 4,204 daily closes from 2010-01-04, with both split events |
| Facts | the filer's own XBRL, from `data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` |
| Dimensions | none: the SEC facts payloads publish only facts with no dimensional qualifiers |
| Units | amounts in USD, the cover-page share count in shares |

Every role's element was served by the filer's own facts. No companyconcept
substitution and no instance-document fallback was needed: the facts API
carried all eleven elements the configuration names, with their contexts
pinned by `(accession, element, period, unit)`.

### The acceptance times

The SEC states a filing's acceptance time in two places, and for AAPL they do
not agree. The SGML header states the Eastern local time the filing was
accepted; EDGAR's own filing index page shows the same value. The submissions
API states an instant four hours later in summer and five hours later in
winter, because it serialises the Eastern wall clock with the offset applied
twice.

The lane uses the header's time, and the capture records both, with the
difference in hours on every row. 55 of AAPL's 67 filings were accepted at or
after 16:00 Eastern, so they became knowable on the next trading day.

The general builder had a defect that would have hidden this: the filing
index the SEC generates carries the field as `ACCEPTANCE-DATETIME&gt;...`,
while the full submission's own SGML header carries it as
`<ACCEPTANCE-DATETIME>...`, and the builder's pattern matched only the first
shape. A filing whose index header does not exist therefore fell through to
the submissions API and took the late time. The builder now reads both
shapes.

### What the roles read

| Role | Elements the lane may read | What the filer actually did |
|---|---|---|
| `revenue` | `us-gaap:Revenues`, `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `us-gaap:SalesRevenueNet` in every periodic filing from the FY2009 10-Q to the FY2018 third-quarter 10-Q; `us-gaap:Revenues` in the FY2018 10-K alone; `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` from the FY2019 first-quarter 10-Q |
| `operating_income` | `us-gaap:OperatingIncomeLoss` | unchanged throughout |
| `depreciation` | `us-gaap:DepreciationAndAmortization`, `us-gaap:DepreciationDepletionAndAmortization` | `us-gaap:DepreciationAndAmortization` for FY2008 to FY2016, annually; `us-gaap:DepreciationDepletionAndAmortization` from FY2015; `us-gaap:DepreciationAmortizationAndAccretionNet` for the quarterly cash-flow line until the FY2018 third-quarter 10-Q |
| `shares_outstanding` | `dei:EntityCommonStockSharesOutstanding` | the cover page, every filing |
| `cash` | `us-gaap:CashAndCashEquivalentsAtCarryingValue` | every balance sheet from FY2006 |
| `marketable_securities_current` | `us-gaap:MarketableSecuritiesCurrent` | from the FY2018 10-K onwards |
| `commercial_paper` | `us-gaap:CommercialPaper` | every quarterly balance sheet from FY2013, except the FY2020 second and third quarters |
| `long_term_debt_current` | `us-gaap:LongTermDebtCurrent` | from FY2014 |
| `long_term_debt_noncurrent` | `us-gaap:LongTermDebtNoncurrent` | from FY2014 |

Two elements the filer used are **not** read, and the reasons are recorded on
every observation:

* `us-gaap:SalesRevenueNet` is not accepted by the registry for the
  `revenue` metric, and it is a different presentation from the successor.
* `us-gaap:DepreciationAmortizationAndAccretionNet` is not accepted for
  `depreciation_and_amortization`, and it is net of accretion, which is not
  the quantity the successor element measures.

`us-gaap:Depreciation` is pure depreciation and is not read at all.

The consequence is stated rather than worked around: because the elements the
role reads become quarterly only in FY2018, the earliest four-quarter window
the lane can build is FY2018's, and the dates before it are refused for a
missing window rather than filled from an element the role does not name.

### The commercial paper gap

In the FY2020 second and third quarters, Apple filed the balance-sheet line
"Commercial paper and repurchase agreement" on
`us-gaap:OtherShortTermBorrowings` and did not file `us-gaap:CommercialPaper`
at all. The bridge therefore holds the 2019-12-28 commercial-paper instant
against a 2020-03-28 or 2020-06-27 balance sheet at the two evaluation dates
of those quarters, and the lane refuses both for a mixed balance sheet rather
than mix two dates or complete the bridge by omission. The production AAPL
dataset refuses the same two dates for the same reason.

## The three lanes

All three are candidates and all three are computed by the same engine. The
first and the third are the two the case was opened for; the second shares the
third's denominator and differs only in its numerator, which is what makes
the attribution between market capitalisation and enterprise value readable.

| Lane | Research metric | Valid | Evaluations | Median | Period | Status |
|---|---|---|---|---|---|---|
| `aapl_reported_revenue_multiple` | `RESEARCH_AAPL_REPORTED_REVENUE_MULTIPLE` | 32 | 67 | 6.996311 | 2018-11-05 to 2026-07-31 | `RESEARCH_DISTRIBUTION` |
| `aapl_reported_operating_profit_plus_reported_d_and_a_multiple` | `RESEARCH_AAPL_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE` | 29 | 67 | 22.054083 | 2019-08-01 to 2026-07-31 | `RESEARCH_DISTRIBUTION` |
| `aapl_filed_ev_bridge_multiple_production_shape` | `RESEARCH_AAPL_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE` | 27 | 67 | 22.326 | 2019-08-01 to 2026-07-31 | `RESEARCH_DISTRIBUTION` |

Refusals:

| Lane | Reason | Count |
|---|---|---|
| revenue | `RESEARCH_REASON_NO_DENOMINATOR_WINDOW` | 35 |
| operating profit plus D&A | `RESEARCH_REASON_NO_DENOMINATOR_WINDOW` | 38 |
| EV bridge | `RESEARCH_REASON_NO_DENOMINATOR_WINDOW` | 38 |
| EV bridge | `RESEARCH_REASON_MIXED_BALANCE_SHEET_PERIODS` | 2 |

The revenue lane starts at the FY2018 10-K's usable date, 2018-11-05, because
that filing carries FY2018's four quarters. The two earnings lanes start at
2019-08-01: FY2019's third-quarter 10-Q is the first filing that carries the
FY2018 year-to-date spans, and FY2018's fourth quarter can only be derived by
subtracting them from the FY2018 annual figure. The lane did not guess a
quarter it could not derive.

## What was verified

### The fiscal calendar

Every published window holds four consecutive fiscal quarters, in order and
without overlap, and every fiscal year ends on a Saturday in September.
Consecutive quarters are thirteen or fourteen weeks apart, which no calendar
quarter is: the FY2018 fourth quarter ends 2018-09-29, the FY2019 first ends
2018-12-29, and so on. The lane never assumes a quarter end is a calendar
quarter end, and it never fills a gap in a window with a quarter it does not
have.

### The two splits

The provider's close series is adjusted for later splits, so the lane restores
the as-traded close from the split events in the payload before it pairs a
price with a share count.

| | Before the 7:1 (2014-06-09) | After | Before the 4:1 (2020-08-31) | After |
|---|---|---|---|---|
| Evaluation date | 2014-04-25 | 2014-07-24 | 2020-07-31 | 2020-10-30 |
| As-traded close | 571.94 | 97.03 | 425.04 | 108.86 |
| Cover-page shares | 861,381,000 | 5,987,867,000 | 4,275,634,000 | 17,001,802,000 |
| Market capitalisation | 492,658,249,140 | 581,002,735,010 | 1,817,315,475,360 | 1,850,816,165,720 |

The close on the last date before each split is the price the market printed
(571.94 is seven times the split-adjusted 81.71; 425.04 is four times the
split-adjusted 106.26), and the share count is the count the cover page
stated, in the scale of the day. The market capitalisation is continuous
across both splits: a double adjustment would have shown as a sevenfold or
fourfold step.

### The depreciation element's chronology

| | `DepreciationAndAmortization` | `DepreciationDepletionAndAmortization` |
|---|---|---|
| First period | FY2008 | FY2015 |
| Last period | FY2016 | still filed |
| Annual only? | yes, throughout | until FY2018 |
| Registry standing | `QUALIFIED` | `QUALIFIED` |
| Element change | re-tag | re-tag |

The two overlap on FY2015 and FY2016, and both are annual before FY2018, so
the overlap is recorded rather than hidden. The FY2018 10-K restates FY2016 on
the successor at 10,105 million against the 8,300 million first filed; the
lane records that as a prior-period value revision, with the old value, the
new value, the accessions and the observations it reaches. No quarter before
FY2018 is derived from either element, and no pure depreciation is read in
place of a full D&A.

### The point-in-time rule

The 16:00 Eastern rule and the `America/New_York` timezone are the engine's,
unchanged. 55 of AAPL's 67 filings were accepted at or after 16:00 Eastern
and become knowable on the next trading day; the twelve accepted earlier
become knowable the same day. The lane's usable dates are the rule's dates,
computed from the header's own acceptance time.

## The comparison with the production AAPL dataset

The production AAPL historical P/S and EV/EBITDA datasets are an independent
reference, not an input. On the 35 evaluation dates the two share:

* the **EV/EBITDA** lane and the production EV/EBITDA agree on **every** one:
  the same price, the same cover-page share count, the same market
  capitalisation, the same enterprise value and the same multiple to six
  decimal places, and the same refusal on the same dates with the same
  condition behind it.
* the **revenue** lane and the production P/S agree on all 28 dates on which
  both publish.

The dates on which they differ are named, and the reason is the source facts:

| Date | Research | Production | Why |
|---|---|---|---|
| 2018-11-05 | publishes | `REASON_SOURCE_CONCEPT_COVERAGE_GAP` | the production capture holds only the successor element; the research capture also holds `us-gaap:Revenues`, which the FY2018 10-K states FY2018's quarters on |
| 2019-01-31 | publishes | `REASON_MISSING_REVENUE_WINDOW` | FY2019's first quarter was not derivable from the successor element alone |
| 2019-05-02 | publishes | `REASON_MISSING_REVENUE_WINDOW` | as above |
| 2019-08-01 | publishes | `REASON_MISSING_REVENUE_WINDOW` | as above |
| 2018-02-02, 2018-05-03, 2018-08-02 | refuses, no window | refuses, coverage gap | neither can build a window before FY2018's quarters are filed |

The medians differ because the samples differ: 6.996311 over 32 observations
against 7.257709 over 28. The research median is recomputed from the
research observations; the production median is never read into it.

The evaluation dates differ at the left edge for a separate reason: the
production AAPL price series begins on 2018-01-02, so every earlier filing
collapses onto that first trading day, while the research capture's price
series begins on 2010-01-04 and the lane evaluates 67 dates from
2010-01-26.

## The identities

| Lane | `input_set_id` | `content_hash` |
|---|---|---|
| revenue | `7a10ab27891e6fa2ebe518905cddd3ac1a496a953cc1779f1ce3631040585b58` | `1a23c95d3fcc6f1f79204e82c6aab3e5760bf2cf3ab32f02c104cb2eb10acb32` |
| operating profit plus D&A | `e59f5e4e0665bad1572fbebc2ae2c4a7ccfddc705dda0a39aaa5ee218714127c` | `c48713e2cdadaf26cfc435da1d40f2b28b7b89c00f32ec729e8a4f11feee5cc0` |
| EV bridge | `4f0067be31d437c4607b55faa29f19603619b4f0519e9d7b1a36d170afec9081` | `c5fbaa23b68459578262556070d77d4bab2ba4ed142d4e2feba950344238b373` |

What each identity covers is set out in `docs/RESEARCH-LANE.md`. In short: the
`input_set_id` holds the lane's identity and the digests of the eleven capture
files it read; the capture manifest describes the capture and is not itself
part of the identity; the unit policy and the registry's standing on every
element read are the policy identity, carried on the distribution and on every
observation; and the calculation hash is the hash of the input set id and the
observation hashes.

## The isolation

* Every AAPL distribution carries `production_eligible=False`, fixed by the
  type.
* No AAPL research figure produces a `refc:*` production reference, and the
  research tree is the only place it is written.
* The production payload digests for AAPL, AEP and MSFT are unchanged.
* KO's four research lanes publish the same values, the same refusal reasons,
  the same `input_set_id`s, the same observation hashes and the same
  comparison hashes as before.
* AAPL is not qualified for production by any of this, and is not closer to
  being qualified. The registry's standing on the elements the lanes read is
  recorded on every observation, and it says that one of the two revenue
  elements and one of the two depreciation elements the lanes read are
  accepted and one is not.

## What could not be established

* **The pre-FY2018 quarterly window.** AAPL tagged its quarterly net sales on
  `us-gaap:SalesRevenueNet` and its quarterly cash-flow depreciation on
  `us-gaap:DepreciationAmortizationAndAccretionNet`. Neither is accepted by
  the registry for the metric it would be read for, and the second is net of
  accretion, so the role does not read either. The consequence is a stated
  refusal, not a silent substitution: the lane's sample begins with FY2018.
  A research lane that chose to read them would publish a longer sample built
  on elements the registry does not accept, and would have to say so on every
  observation.
* **The FY2020 second and third quarters' bridge.** The commercial paper is
  not filed on the element the bridge reads in those two quarters, so the two
  evaluation dates are refused. A separate bridge role reading
  `us-gaap:OtherShortTermBorrowings` would cover them, and would be a
  different bridge from the one the production definition names.
* **A byte-for-byte rebuild.** The capture cannot be rebuilt byte for byte,
  because the price payload carries the provider's live metadata and the
  acceptance index records the digest of a header page the SEC regenerates.
  The committed capture is the one the identity is pinned to.
