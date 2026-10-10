# ST-EVA 2.3-B — SEC Cross-Validation

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

Status: SPEC (to be reviewed before implementation)
Target: 2.3-B
Baseline: 2.3-A
Repository: sbvcid/st-eva
Implements: the second-source half of
[docs/ST-EVA-2.3-PLAN.md](ST-EVA-2.3-PLAN.md) phase 2,
against the contract in
[docs/ST-EVA-2.3-A-DATA-CONTRACT.md](ST-EVA-2.3-A-DATA-CONTRACT.md)

## 0. Goal, stated narrowly

Add the SEC as a second data source, for one purpose only:

> Prove that the 2.3-A `Observation → Evidence → Validation` architecture
> actually works across two independent sources.

2.3-B is not a second valuation source. Nothing the SEC reports changes what the
engine calculates, and the CLI output is unchanged. The SEC is used to
*cross-check* Yahoo, not to replace it.

### 0.1 Non-goals

- No EBITDA, FCF, P/E, P/S, EV/EBITDA. Seven metrics, listed in §2.
- No MOPS.
- No A/B comparison UI, no ranking, no score, no probability, no buy/sell.
- No new valuation model, no change to any existing formula.
- No change to the 2.2.3 CLI, JSON, or report output.
- No point-in-time backtest engine. 2.3-B records point-in-time facts; it does
  not yet replay history.
- No LLM in the comparison path.

## 1. The principle this phase exists to protect

> **Validation is a third thing. It is not a modification of an Observation.**

Explicitly forbidden, and guarded by tests:

```
Yahoo = 6.20
SEC  = 6.18
   -> EPS = 6.19          FORBIDDEN  (never merge or average)

   -> SEC is authoritative, keep 6.18
                          FORBIDDEN  (never pick a winner)

   -> Yahoo = 6.20, SEC = 6.18
      ValidationRecord(
        status             = CONSISTENT | DISCREPANT | METHODOLOGY_MISMATCH
                              | PERIOD_MISMATCH | UNAVAILABLE,
        comparison_basis   = <how the comparison was constructed>,
        tolerance          = <the rule that was applied>,
        explanation        = <why this status>,
        references         = [<both observation ids>, <filing accessions>],
      )
                          REQUIRED
```

Both source observations survive the comparison, unmodified, with their own
provenance. A consumer may read either one, or both, and reach its own
conclusion. The comparison is an annotation on the pair, never a replacement of
one of them.

This is the 2.3-A rule "validation labels a value, it never edits one", applied
across two values instead of one.

## 2. Which metrics, and what the sources actually offer

Seven metrics. Each is a *concept*; period and basis are separate attributes.

| Contract metric | SEC concepts, in priority order | Period type |
|---|---|---|
| `revenue` | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`, `us-gaap:Revenues`, `us-gaap:SalesRevenueNet` | duration |
| `net_income` | `us-gaap:NetIncomeLoss`, `us-gaap:ProfitLoss` | duration |
| `eps_diluted` | `us-gaap:EarningsPerShareDiluted` | duration, per share |
| `assets` | `us-gaap:Assets` | instant |
| `cash` | `us-gaap:CashAndCashEquivalentsAtCarryingValue`, `us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents` | instant |
| `debt` | `us-gaap:LongTermDebtNoncurrent` + `us-gaap:LongTermDebtCurrent`, else `us-gaap:LongTermDebtNoncurrent` | instant, composed |
| `shares_outstanding` | `dei:EntityCommonStockSharesOutstanding` | instant, cover page |

Concepts are tried in order and the first that returns data wins. The concept
actually used is recorded in `methodology`. Concept drift is real and is
therefore expected, not exceptional: Apple reported revenue under
`us-gaap:Revenues` until FY2018 and under
`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` from FY2019
(ASC 606 adoption), verified against `companyconcept`.

A concept that returns HTTP 404 is `UNAVAILABLE`. It is not an error, and it
does not abort the run.

### 2.1 What Yahoo actually provides, measured

Probed against the live `fundamentals-timeseries` and `quoteSummary` endpoints:

| Concept | Yahoo field | Value shape | Usable for comparison? |
|---|---|---|---|
| `revenue` | `trailingTotalRevenue` | TTM, `asOfDate` only | yes, with `as_of` alignment |
| `net_income` | `trailingNetIncomeCommonStockholders` | TTM, `asOfDate` only | yes, with `as_of` alignment |
| `eps_diluted` | `trailingDilutedEPS` | TTM, `asOfDate` only | yes, with the §4.4 caveat |
| `assets` | — | `trailingTotalAssets` returns HTTP 404 | **no — permanently UNAVAILABLE on the Yahoo side** |
| `cash` | `financialData.totalCash` | instant, **no date, no currency** | comparison only, see §4.4 |
| `debt` | `financialData.totalDebt` | instant, **no date, no currency** | comparison only, see §4.4 |
| `shares_outstanding` | `defaultKeyStatistics.sharesOutstanding` | instant, **no date** | comparison only, see §4.4 |

Three findings that shape the design:

1. **Yahoo does not publish a TTM window.** `trailingTotalRevenue` has an
   `asOfDate` and nothing else. The engine knows the value is trailing twelve
   months; it does not know which twelve months. `period_start` and
   `period_end` must therefore be `None` with basis `UNDECLARED`, and any
   comparison is anchored on `as_of`.
2. **Yahoo's `financialData` block carries no date and no currency.**
   `totalCash`, `totalDebt` and `totalRevenue` are undated and the module's
   `currency` field is `null`. These are not silently upgraded to "as of today
   in USD".
3. **Yahoo's share count is not independent of the SEC.** Yahoo's
   `sharesOutstanding` for AAPL is 14,594,180,000, which is exactly the SEC
   `dei:EntityCommonStockSharesOutstanding` for the same cover date. Yahoo
   sources it from the filing. Agreement there is therefore *not*
   corroboration, and the comparison must say so.

Point 3 is a general warning, not a quirk: a vendor that ingests a filing will
agree with that filing by construction. 2.3-B reports the agreement and labels
its independence; it does not suppress the finding, and it does not promote it.

## 3. SEC provider: what it produces

`sec_provider.py` emits `Observation` objects and nothing else. It never
computes a valuation ratio, never selects a reference, and never returns a
merged value.

### 3.1 Company resolution

- `https://www.sec.gov/files/company_tickers.json` maps ticker → `{cik_str,
  ticker, title}`. Observed shape: an object keyed by a running index, each
  value `{cik_str, ticker, title}`.
- CIK is normalised to the 10-digit zero-padded form used by the APIs.
- A ticker absent from the mapping is `UNAVAILABLE` with a recorded reason. It
  is not guessed from the company name.

### 3.2 Access rules

Non-negotiable, from the SEC fair-access policy:

- A declared, contactable `User-Agent` is required. An undeclared agent is
  throttled or blocked.
- Maximum 10 requests per second, counted per IP. The provider rate-limits
  itself to a documented budget below that ceiling rather than relying on
  politeness.
- No authentication and no API key.
- Only the non-custom taxonomies are usable: `us-gaap`, `dei`, `ifrs-full`,
  `srt`. The company-concept API aggregates only facts that use a standard
  taxonomy and that apply to the entire filing entity, which is what makes them
  comparable between companies and between filings.

### 3.3 Endpoints

- `https://data.sec.gov/submissions/CIK##########.json` — filing history.
- `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/{taxonomy}/{tag}.json`
  — one concept, one company.

`submissions.filings.recent` is a columnar array. Fields used, as observed:
`accessionNumber`, `filingDate`, `reportDate`, `acceptanceDateTime`, `form`,
`isXBRL`, `primaryDocument`, `core_type`.

`companyconcept` returns `cik`, `taxonomy`, `tag`, `label`, `description`,
`entityName`, `units`. Each unit array entry has `start` (duration concepts
only), `end`, `val`, `accn`, `fy`, `fp`, `form`, `filed`, and `frame` on
discrete periods only.

## 4. The eleven questions

### Q1. Which Observations does the SEC provider supply?

For each of the seven concepts, one `Observation` per *discrete reported
period*, not one per ticker:

- A **duration** fact yields an observation with `period_start`, `period_end`
  and `as_of` all populated from the fact's own `start` and `end`.
- An **instant** fact yields an observation with `period_start = None`,
  `period_end = as_of = end`. Instant facts carry no `start` in the API, and
  inventing one would be fabrication.
- `unit` is the XBRL unit: `USD`, `USD/shares`, or `shares`.
- `currency` is `USD` only when the XBRL unit is `USD` or `USD/shares`.
  `shares` carries `currency = None` with basis `NOT_APPLICABLE`.
- `source_type` is a new contract value, `REGULATORY_FILING`.
- `source_url` is the company-concept endpoint, and the filing document URL is
  recorded in `raw`.
- `raw` preserves the fact verbatim, including `accn`, `form`, `fy`, `fp`,
  `frame`, `filed`, and the concept's `label` and `description`.

#### The YTD trap, and why it decides the design

A 10-Q reports a fact **twice** for the same end date: year-to-date and the
discrete quarter. Observed for AAPL `NetIncomeLoss`, end `2026-06-27`:

```
start 2025-09-28  end 2026-06-27  val 101,464,000,000   <- 9-month YTD
start 2026-03-29  end 2026-06-27  val  29,789,000,000   <- discrete quarter
```

Only the discrete entry carries a `frame` (`CY2026Q2`). The YTD entry has no
frame.

A naive "take the latest value for the latest end date" takes the **nine-month
figure and compares it to a trailing-twelve-month figure**. That is not a small
error; it is a category error, and it would be reported as a discrepancy.

The provider therefore accepts only facts that are discrete: a duration fact
must have a `frame`, or its length must be consistent with a quarter
(60 to 130 days) or a year (330 to 400 days). YTD entries are rejected and the
rejection is counted, not silently dropped.

Because Yahoo reports a **TTM** value and the SEC reports discrete periods, the
SEC adapter also emits derived trailing views for the three duration metrics.
The vendor publishes no window, so the comparison needs a filing-side window
that covers the same period, and it must be able to offer more than one.

#### Three constructions, most direct first

| Construction | When it applies |
|---|---|
| `ANNUAL_FACT_AS_TRAILING_WINDOW` | a filed annual period **is** twelve months, and when a fiscal year has just closed it is fresher than any quarter sum |
| `SUM_OF_DISCRETE_QUARTERS` | four contiguous discrete quarters |
| `ANNUAL_ROLL_FORWARD` | `prior fiscal year − prior-year cumulative + current cumulative`, for a filer whose quarters have a hole |

The quarter sum is not always available. A retail filer with a 4-4-5 week
calendar often reports its fiscal Q3 only inside the annual context, never as a
discrete quarter. Apple's four most recent discrete quarters therefore have a
hole, and summing them would silently omit a quarter of revenue. The provider
detects the gap, refuses the sum, and falls back to the roll-forward.

For AAPL: 416,161,000,000 − 313,695,000,000 + 364,357,000,000 =
466,823,000,000, over the window 2025-06-29 to 2026-06-27.

The cumulative facts this consumes are year-to-date, so they are *not* emitted
as comparable observations — a cumulative figure is not comparable with a
trailing one. They are retained in the derived observation's `raw`, and the
construction is named in `methodology`. This is the only use a cumulative fact
is put to.

#### The anchor is the window's end, not a bound

A comparison is an alignment, not a contest to find the newest number on each
side. A vendor may be quoting a trailing figure that predates the filer's most
recent annual report. Observed: Microsoft's trailing EPS is stamped
2026-03-31 while its fiscal year closed 2026-06-30, and Apple's trailing
figures are stamped three days after its fiscal quarter end.

So the provider emits a trailing view for **each** period end it can anchor to,
and the comparison picks the filing-side window closest to the vendor's `as_of`.
The anchor is the window's required end date, within a 10-day tolerance. A
window ending a quarter before the anchor is refused rather than returned as a
near match, because returning it would manufacture a period mismatch.

Whichever construction is used, the derived observation records it:

- `raw.derivation` names the construction.
- `raw.constituents` holds the exact facts, so the arithmetic is recomputable
  under the 2.3-A rule rather than trusted.
- `period_start` and `period_end` span the window — information the vendor does
  not provide at all.
- `available_at` is the availability of the latest constituent, the first
  moment the whole window could be assembled.
- The observation ID carries the anchor end, so two windows from one filing
  coexist instead of colliding.

#### Restatements produce multiple observations, by design

The same `(concept, period)` can be reported by several filings with
**different values**. Verified for AAPL `NetIncomeLoss`:

```
2007-09-30 | 2008-09-27   10-K   @2009-10-27  ->  4,834,000,000
                             10-K/A @2010-01-25  ->  6,119,000,000   (+26.6%)
2008-09-28 | 2009-06-27   10-Q   @2009-07-22  ->  4,039,000,000
                             10-Q   @2010-07-21  ->  5,703,000,000   (+41.2%)
```

And the reverse also occurs: a quarter is reported identically by the 10-Q that
first disclosed it and again as a comparative inside the following 10-K.

So the provider does **not** collapse a period to one value. It emits one
observation per `(concept, period, filing)`, each with its own `available_at`,
and the observation ID carries the accession:

```
cmp-revenue-sec-2026q3-0000320193-26-000020
cmp-revenue-sec-fy2007-0001193125-10-000032
cmp-revenue-sec-fy2007-amd-0001193125-10-000204
```

"Which value is correct" is not a question the provider answers. It is not its
job, and answering it would require a restatement policy that does not exist
yet. A point-in-time selector, `latest_knowable(cutoff)`, chooses the newest
filing accepted at or before a cutoff, and it is a pure function with no
network access. 2.3-B supplies the selector and the raw facts; it does not yet
replay them.

To keep the observation count bounded, only the most recent filings per concept
are considered, and the cap is a declared parameter.

### Q2. Which Yahoo metrics can be compared with which SEC metrics?

A concept pair is comparable when **all** of the following hold. Failing any of
them is not a discrepancy; it is a reason not to compare.

| # | Condition | Rationale |
|---|---|---|
| C1 | Both sides available | Otherwise `UNAVAILABLE`. |
| C2 | Units equal, or both are per-share | Otherwise `METHODOLOGY_MISMATCH`. |
| C3 | Currencies equal, or both dimensionless | Otherwise `METHODOLOGY_MISMATCH`. |
| C4 | Period types equal: duration with duration, instant with instant | A flow against a stock is not a disagreement, it is a category error. Otherwise `METHODOLOGY_MISMATCH`. |
| C5 | `as_of` anchors within the period-alignment window (§4.4) | Otherwise `PERIOD_MISMATCH`. |
| C6 | Measurement basis equal: TTM against TTM, instant against instant | Otherwise `METHODOLOGY_MISMATCH`. |
| C7 | Construction declared on both sides | A composed metric such as `debt` is comparable only if the composition is stated. |

Applying C1–C7 to the measured availability in §2.1, the result for v1, as
observed against the live APIs for AAPL:

| Metric | Observed verdict | Why |
|---|---|---|
| `revenue` | `CONSISTENT` | trailing against a declared trailing window, anchors 3 days apart (AAPL) or 0 (MSFT) |
| `net_income` | `CONSISTENT` | as above |
| `eps_diluted` | `CONSISTENT` | as above; for MSFT the window is aligned to the vendor's older `as_of` rather than to the newest filing |
| `assets` | `UNAVAILABLE` | the vendor publishes no total-assets counterpart |
| `cash` | `METHODOLOGY_MISMATCH` | vendor total cash includes short-term investments; the filing-side concept does not |
| `debt` | `METHODOLOGY_MISMATCH` | no single total-debt concept exists; the value is composed, and the composition is recorded even though the verdict is a mismatch |
| `shares_outstanding` | `PERIOD_MISMATCH` | both sides read the same cover page and the values are identical, but the vendor states no date, so contemporaneity cannot be confirmed |

Three of seven reach a numeric verdict. **That is the correct outcome, not a
shortfall.** The point of 2.3-B is to classify all seven correctly, including
the four that cannot be compared. A phase that only compared the four that
happen to work would prove less than one that explains why the rest cannot be
compared.

### 2.2 A finding about agreement itself

The SEC roll-forward for AAPL reproduces the vendor's trailing figures
**exactly**: revenue 466,823,000,000 against 466,823,000,000, and diluted EPS
agreeing to floating-point noise. Independently reconstructing a vendor figure
to the last digit is not what two independent pipelines do. It is what happens
when one of them read the other's source.

The verdict is still `CONSISTENT`, because the two values are comparable and do
agree. But `comparison_basis.independence` is `UNVERIFIED_INDEPENDENCE`, and the
record says so. The rule is deliberate: report the agreement, label its
strength, and never promote an unverified agreement into corroboration. A
pipeline that silently treated a shared upstream as two witnesses would be
manufacturing the appearance of a check.

For `shares_outstanding` this is not a suspicion but a certainty: the vendor's
share count is the SEC cover-page figure, which is why the verdict is
`PERIOD_MISMATCH` (undated) rather than a corroborated `CONSISTENT`.

### Q3. What does "comparable" mean?

> Comparable means the two observations are the *same measurement of the same
> quantity over the same period*, so that their difference is informative.

Comparable is **not**:

- "both numbers are in dollars";
- "the values are close";
- "one source is more reputable";
- "the periods are the same length".

The test is constructive. Name the quantity and the window. If both sides
answer that question, they are comparable. Yahoo's `revenue` answers "trailing
twelve months ending on or about 2026-06-30"; the SEC's 10-Q YTD entry answers
"the nine months to 2026-06-27". Both are revenue, both are USD, and they are
**not comparable**, because the windows differ. The difference between them is
a difference of *questions*, not of *arithmetic*, and reporting it as a
discrepancy would be a false alarm that trains a reader to ignore the real ones.

Comparability is therefore declared, per metric, before any value is read. The
declaration is data, not a comment: it lives in `comparison_basis` and is
serialized.

### Q4. How are `period_start`, `period_end` and `as_of` aligned?

They are three different things and are never merged.

- `period_start` / `period_end` bound **what the value measures**.
- `as_of` is **the date the value is stated as of**, which for an instant fact
  is the balance-sheet date, and for a duration fact is the period end.
- `available_at` is **when the value became knowable**. §5.

Alignment rule, applied in order:

1. If both sides declare a period, require `period_end` within the alignment
   window on the SEC side. The SEC side is authoritative for the window,
   because it is the side that states one.
2. If the Yahoo side declares no period, fall back to `as_of` proximity, and
   record `period_basis = "AS_OF_ONLY"` in `comparison_basis`. The reader is
   told the match rests on a date, not on a period.
3. If the anchors differ by more than the window, `PERIOD_MISMATCH`. The
   values are not compared and no difference is computed.

**The window must exist, and it must be generous.** Company fiscal calendars do
not align with calendar quarters. Apple's fiscal Q3 2026 ended `2026-06-27`
while Yahoo stamps its trailing value `2026-06-30`. A 3-day gap is ordinary
noise, not a discrepancy. The window is 7 days, matching the existing freshness
constant, and is a declared parameter.

The SEC's own documentation warns that facts in a frame carry differing
reporting start and end dates, and defines quarterly frames as 91 days ±30 and
annual frames as 365 days ±30. The discrete-fact test in Q1 follows that
tolerance directly.

`as_of` is never set to `available_at` and `period_end` is never set to
`available_at`. A filing accepted on 2026-07-31 whose balance sheet is dated
2026-06-27 has `period_end = 2026-06-27`, `as_of = 2026-06-27`,
`available_at = 2026-07-31T10:01:02Z`. Collapsing the third into the first
would silently make a July fact look like a June fact, which is precisely the
error that corrupts a backtest.

### Q5. How is `available_at` derived from SEC filing metadata?

The SEC defines three distinct dates, and the provider maps them one-to-one.

| SEC field | Meaning | Contract field |
|---|---|---|
| `ACCEPTANCE-DATETIME` (`acceptanceDateTime`) | when EDGAR accepted the submission | **`available_at`** |
| `FILED AS OF DATE` (`filingDate`, `filed`) | official submission date | fallback for `available_at`, and recorded in `raw` |
| `CONFORMED PERIOD OF REPORT` (`reportDate`) | the period the filing reports on | **`period_end`**, not `available_at` |

Derivation:

1. A fact carries its `accn`. Look that accession up in `submissions` to obtain
   `acceptanceDateTime`.
2. `available_at` is that instant, with
   `available_at_basis = ACCEPTANCE_DATETIME`.
3. If the accession is absent from `filings.recent` (the API exposes roughly the
   most recent 1,000 filings, with older ones in separate archive files), fall
   back to `filed` with
   `available_at_basis = FILED_AS_OF_DATE`, and record
   `time_of_day_known = False`. The date is provable; the instant is not, and
   the basis says which one was used.
4. If neither is available, `available_at = None` with basis `UNDECLARED`. It
   is never filled with the retrieval time.

`available_at` is acceptance, not filing, because acceptance is the moment the
data became knowable to the public. EDGAR's APIs are updated in real time as
filings are disseminated, and the fact is not public before then.

The three dates are carried separately in `raw` on every SEC observation, so a
reader can reconstruct the bitemporal position without re-fetching anything.

### Q6. How are `currency` and `unit` checked?

1. Read the XBRL unit from the fact. It is part of the fact's identity: the
   same concept can be reported in `USD` and in another currency, and
   `companyconcept` returns one array per unit.
2. Map it to a contract unit: `USD` → `currency`, `shares` → `count`,
   `USD/shares` → `per_share`. Any other unit is `UNAVAILABLE` with a recorded
   reason; it is not coerced.
3. `currency` is set only for units that are monetary. `shares` is
   dimensionless: `currency = None`, basis `NOT_APPLICABLE`.
4. A value is only comparable to a value with an equal unit and an equal
   currency, per C2 and C3 in §Q2.
5. If the Yahoo side does not state a currency, the comparison does not proceed
   to a numeric verdict. It is `UNAVAILABLE` on the currency check, with the
   reason "the counterparty does not state a currency".

Two real traps this catches:

- **XBRL unit spelling.** The SEC documentation describes numerator/denominator
  units as `USD-per-shares`, but the live API returned `USD/shares` for
  `EarningsPerShareDiluted`. Both spellings are accepted; the observed one is
  recorded in `raw`.
- **Yahoo mislabels a share count as currency.** `trailingDilutedAverageShares`
  returns `currencyCode: "USD"` for a quantity of 14,778,629,000 shares. If
  that field were trusted, the unit check would accept a share count as a
  monetary amount. The provider maps the field name to the unit, and the
  reported `currencyCode` is recorded in `raw` as a disagreement to be aware
  of, not as a unit declaration.

### Q7. What `ValidationRecord` is produced when the two sources agree?

`status = CONSISTENT`, and **both observations remain unmodified**.

```
ValidationRecord(
  status           = CONSISTENT,
  comparison_basis = {
      basis              = "cross_source",
      metric             = "revenue",
      independence       = "UNVERIFIED_INDEPENDENCE",
      period_basis       = "AS_OF_ONLY",
      period_window_days = 7,
      period_offset_days = 3,
      vendor_observation = "cmp-revenue-yahoo-2026-06-30",
      filing_observation = "cmp-revenue-sec-ttm-to-2026-06-27-000032019326000020",
      vendor_value       = 466823000000.0,
      filing_value       = 466823000000.0,
      difference         = 0.0,
      relative_difference = 0.0,
  },
  tolerance        = {"kind": "RELATIVE_AND_ABSOLUTE_BOUND",
                      "relative": 0.005, "absolute": 50000000.0,
                      "rule": "difference must satisfy both bounds"},
  explanation      = "revenue agrees across the two sources. ...",
  references       = ["cmp-revenue-yahoo-2026-06-30",
                      "cmp-revenue-sec-ttm-to-2026-06-27-000032019326000020",
                      "0000320193-26-000020"],
  value_snapshot   = (466823000000.0, 466823000000.0),
)
```

`CONSISTENT` is a statement about agreement between two sources. It is not a
claim that either is true, and it is not `VERIFIED`. `VERIFIED` is reserved
for agreement across three or more sources and remains undeclared-by-computation
in 2.3-B for the same reason it was in 2.3-A.

`value_snapshot` is a copy of both values as they stood when validated. It is
the audit trail for the no-overwrite rule: if an observation's value ever
differs from the snapshot, the mutation is detectable after the fact. It is a
copy for auditing, never a replacement.

#### The tolerance must satisfy both bounds

A difference passes only when it is small *relatively* **and** small
*absolutely*. Either bound alone is wrong in a way that matters here:

- **Relative alone** would accept a 0.5% gap on a 466 billion revenue figure.
  That is 2.3 billion dollars, which no reader would call agreement.
- **Absolute alone** would accept any difference between two per-share figures,
  because every diluted EPS is under 100 and the only thing separating most of
  them is rounding.

So the effective width is the tighter of the two, and each metric declares the
pair that suits its magnitude: a revenue tolerance of 50 million absolute, an
EPS tolerance of one cent. Both halves are asserted by tests, so neither can be
quietly dropped.

### Q8. What happens when they disagree?

`status = DISCREPANT`, and **neither value is touched**.

The record carries the full arithmetic so a human can adjudicate: both values,
both units, both currencies, both period anchors, both `available_at` values,
the absolute difference, the relative difference, and the tolerance that was
applied. The explanation names the most likely cause, and says when it does not
know.

Three findings that are *not* discrepancies, and are recorded as such:

- A difference explained by a **restatement**: the two filings have different
  `accn` and the later one supersedes the earlier.
- A difference explained by a **YTD-versus-discrete** error on either side. The
  discrete-fact test should prevent it; if it appears, it is a defect in the
  provider and is reported as one.
- A difference explained by a **fiscal calendar** that does not match. The
  alignment window absorbs ordinary offsets; an offset beyond the window is
  `PERIOD_MISMATCH`, not `DISCREPANT`.

A `DISCREPANT` verdict is deliberately conservative: it is issued only when the
two sides are comparable by §Q3 and still differ beyond tolerance. Reporting a
discrepancy for two figures that do not answer the same question would make the
signal useless.

### Q9. What happens when the definitions differ?

`status = METHODOLOGY_MISMATCH`. No numeric verdict is issued, because the
difference between the two values cannot be attributed to either source being
wrong. The two observations may agree numerically, and it still does not matter:
they are measuring different things.

Expected cases, all confirmed against the live sources:

- **`cash`.** Yahoo's `financialData.totalCash` is cash *and short-term
  investments*. The SEC's `CashAndCashEquivalentsAtCarryingValue` is cash only.
  A gap here is arithmetic, not disagreement.
- **`debt`.** Yahoo publishes one `totalDebt`. The SEC has no single
  equivalent; `debt` is composed from `LongTermDebtNoncurrent` plus
  `LongTermDebtCurrent`, and companies compose it differently. Composition
  differs per filer, so the composition is recorded in `methodology` and
  compared under C7.
- **`revenue` across an accounting-standard change.** `us-gaap:Revenues` and
  `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` are not the
  same concept, and which one applies depends on the filer's adoption of ASC
  606. Comparing across the transition is a methodology mismatch even when the
  fiscal periods align.
- **`eps_diluted`.** Per-share amounts are not strictly additive: four
  quarterly diluted EPS figures sum to trailing EPS only while the share
  denominator is constant. The sum is therefore declared as an approximation,
  and the record says so.

The record names both definitions, both concept identifiers, and the specific
reason the comparison cannot proceed numerically.

### Q10. Neither source is the truth. How are both preserved?

Both are stored, in full, as independent `Observation` objects, and the
comparison is a third object that references both.

```
Observation A  cmp-revenue-yahoo-001   value 466,822,987,776  provider YahooFinance
                raw {...}  unit currency  period_start None  as_of 2026-06-30
                available_at None (UNDECLARED)

Observation B  cmp-revenue-sec-ttm-... value 466,300,000,000  provider SecEdgar
                raw {quarters: [4 facts], accn, label, description}
                unit currency  period_start 2025-07-01  period_end 2026-06-27
                available_at 2026-07-31T10:01:02Z (ACCEPTANCE_DATETIME)

Observation C  cmp-revenue-sec-2026q3-... value 103,000,000,000
Observation D  ... one per discrete quarter, all retained

ValidationRecord  status, comparison_basis, tolerance, explanation, references
                  -> references A and B, never replaces either
```

Concretely:

- `ObservationSet` already permits several observations per metric, and 2.3-A
  has a test asserting that two providers reporting the same metric are both
  kept. 2.3-B is that rule exercised for real.
- Observation IDs are **source-qualified**: `cmp-<metric>-<source>-<period>`.
  The 2.2.3 material-evidence IDs (`ev-*`) are untouched, so `evidence_ids`
  and the CLI JSON do not change. 2.3-A's mapping of one canonical ID per
  metric assumed a single source; 2.3-B widens it to one ID per
  (metric, source, period).
- No aggregation, averaging, blending, or winner-selection helper exists in the
  codebase, and a test asserts the absence of one.
- The engine is not given the SEC value. Nothing in §Q1–Q9 feeds
  `ValuationInputs`. The engine still reads Yahoo exactly as in 2.2.3.

### Q11. Minimum acceptance criteria for 2.3-B

The eight conditions, each objectively checkable:

1. **`SECProvider` resolves a specified company.** Given a ticker, it yields a
   CIK and an entity name. An unknown ticker is `UNAVAILABLE` with a reason, not
   an exception and not a guess.
2. **SEC data becomes `Observation`.** Every fact emits a contract observation
   carrying all twelve required fields plus `raw`.
3. **Filing provenance is retained.** `accn`, `form`, `fy`, `fp`, `frame`,
   `filed`, concept `label`, and `description` survive into `raw`, and
   `source_url` points at a real SEC endpoint.
4. **`available_at` is a provable SEC time.** It is the acceptance datetime
   when obtainable, the filed date with `time_of_day_known = False` when not,
   and `None` when neither is available. It is never the retrieval time, and it
   is never equal to `period_end` by construction.
5. **Yahoo and SEC can be compatibility-checked.** All seven metrics are
   classified; C1–C7 in §Q2 are applied and each rejection reason is recorded.
6. **Agreement produces a `ValidationRecord`** carrying status, basis,
   tolerance, explanation and references.
7. **Conflict produces `DISCREPANT` and overwrites nothing.** Both
   observations are still present and unmodified after the comparison, and no
   merge, average, or winner-selection helper exists.
8. **Every 2.2.3 and 2.3-A test still passes**, and the CLI JSON and report are
   byte-identical to the 2.2.3 baseline.

Two further conditions are treated as part of criterion 8 rather than as
separate features: the provider respects the SEC rate limit and User-Agent
requirement, and it performs no network access during unit tests.

## 5. Changes to the 2.3-A contract

Additive only. No existing field changes meaning; no existing test changes.

| Change | Kind |
|---|---|
| `ValidationStatus.PERIOD_MISMATCH` | new member |
| `SourceType.REGULATORY_FILING` | new member |
| `AvailabilityBasis.ACCEPTANCE_DATETIME` | new member |
| `AvailabilityBasis.FILED_AS_OF_DATE` | new member |
| `Unit` per-share and count mapping for XBRL units | existing members, new inputs |
| `ValidationRecord.comparison_basis / .tolerance / .explanation / .references` | new optional fields, defaulted |
| `ValidationRecord.value_snapshot` | new optional field, defaulted |
| `COMPARABLE_METRICS`, `comparable_observation_id(metric, source)`, `is_comparable_observation` | new |
| `ObservationSet.knowable_at / .latest_knowable` | new |
| `CrossValidationResult` | new type |
| Six cross-source metrics in `CONTRACT_METRICS` / `METRIC_UNITS` / `METRIC_DEFINITIONS` | new (`revenue` already existed) |

`ValidationRecord` gains the five fields the principle in §1 requires. They are
optional and default to `None` / `()`, so a 2.3-A single-source record is
unchanged, its serialized form is unchanged, and the existing validation tests
continue to hold.

`PERIOD_MISMATCH` is placed at the same severity as `METHODOLOGY_MISMATCH`:
both are "these cannot be compared" verdicts, distinct from a claim that two
comparable figures disagree.

`VERIFIED` remains declared and uncomputed. Two sources agreeing is
`CONSISTENT`; promoting that to `VERIFIED` would need a third, and §2.2 gives a
concrete reason not to count a vendor that ingested the filing as one.

## 6. Module layout

| Module | Responsibility |
|---|---|
| `data_contract.py` | types, new enum members, `ValidationRecord` fields, comparable-metric vocabulary, point-in-time selector |
| `sec_provider.py` | SEC adapter: ticker→CIK, submissions, company-concept, facts→observations, discrete-fact filter, trailing-window construction, rate limiting |
| `cross_validation.py` | comparability policy C1–C7, period alignment, tolerance, `ValidationRecord` construction. Pure functions, no I/O. |
| `fundamental_provider.py` | gains the seven comparable metrics as *additional* `cmp-` observations. No existing observation changes. |
| `st_eva_runner.py` | **unchanged**. The engine and the output path are untouched. |

The trailing-window constructions are pure module-level functions
(`_annual_view`, `_quarter_view`, `_roll_forward_view`) so they can be tested
without constructing a provider, and so the three alternatives sit side by side
for comparison rather than being spread across methods.

The comparison is not wired into `run_st_eva`. It is a library capability, used
by tests and by 2.3-C, so that adding a second source cannot perturb the 2.2.3
output. A test asserts that `st_eva_runner` does not reference either new
module, so "adding a source cannot move a number" is checked rather than
promised.

### 6.1 Rate limiting

The SEC caps automated access at 10 requests/second per IP. The provider
self-limits to 4 requests/second (`SAFE_REQUEST_INTERVAL_SECONDS`), which is
comfortably under the ceiling, and declares a contactable `User-Agent`. A
single AAPL run issues 8 requests and takes about 8 seconds. Nothing polls:
each concept is fetched once and cached for the run.

## 7. Stop condition

2.3-B is complete when the eight criteria in §Q11 hold.

Work stops there. MOPS, 2.3-C (`Validated Evidence Set → Investment Context`),
further metrics, and the point-in-time replay engine are all out of scope.

2.3-C is the next phase, and it is where this work eventually pays off: a
standard output any agent can consume directly, built from `Observation`,
`Evidence`, `Validation`, `Derived`, and `Implied`.
