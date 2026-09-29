# MSFT — context-only analysis

Source: `input/MSFT.context.json` (sha256 `0BD7BA9EAB0DEBB3`, `context_schema_version 2.3-C.1`, as_of 2026-09-28)
No external data used. Every claim below carries its `ref`.

## A. What the Context clearly knows

| # | Claim | Provenance | ref |
|---|---|---|---|
| 1 | Price 509.22 USD | `FACT` OBSERVED | `obs:ev-price-001` |
| 2 | Market capitalisation 3,717,153,817,339 USD | `FACT` OBSERVED | `obs:ev-market-cap-001` |
| 3 | Enterprise value 3,697,328,817,339 USD | `FACT` OBSERVED | `obs:ev-enterprise-value-001` |
| 4 | Trailing revenue 331,839,000,000 USD | `FACT` OBSERVED | `obs:ev-revenue-001` |
| 5 | Trailing diluted EPS 17.96 USD/share | `FACT` OBSERVED | `obs:ev-current-eps-001` |
| 6 | Consensus forward EPS 23.67588 USD/share | `FACT` OBSERVED | `obs:ev-consensus-eps-001` |
| 7 | Free cash flow 66,987,000,000 USD | `FACT` OBSERVED | `obs:ev-fcf-001` |
| 8 | EBITDA 207,519,000,000 USD | `FACT` OBSERVED | `obs:ev-ebitda-001` |
| 9 | Filing-side trailing revenue to 2026-06-30: 331,839,000,000 USD | `FACT` OBSERVED | `obs:cmp-revenue-sec-ttm-to-2026-06-30-000119312526323660` |
| 10 | Filing-side trailing diluted EPS to 2026-03-31: 16.79 USD/share | `FACT` OBSERVED | `obs:cmp-eps_diluted-sec-ttm-to-2026-03-31-000119312526191507` |

Evidence coverage is 13 of 14 available; `evidence_coverage.unavailable` = 1.

## B. What the Context clearly does not know

- **P/FCF band** — `NOT_REPORTED_BY_SOURCE`. Requested and not provided by
  `YahooFinanceFundamentals`. `blocks: []`.
- **Valuation reference multiple** — `NO_REFERENCE_AVAILABLE`. The P/E band
  carries 7 observations against a required 20. Blocks `implied_forward_eps`,
  `consensus_price_at_median`, `pe_percentile`.
- **Secondary reference multiples** — pfcf, EV/EBITDA, P/S, each
  `NO_REFERENCE_AVAILABLE`, each blocking one derived value.
- **Percentiles** `pe_percentile`, `ps_percentile`, `ev_ebitda_percentile` —
  `INSUFFICIENT_OBSERVATIONS`.
- **The entire implied block** — `implied_forward_eps`, `required_eps_cagr`,
  `consensus_price_at_median`, `implied_fcf`, `implied_ebitda`,
  `implied_revenue` are `UNAVAILABLE / MISSING_INPUT` with no `value` key.

`UNVERIFIED` — vendor cash and debt carry `currency: null` and
`basis.reporting_currency: UNDECLARED`.

## C. Validation

| Metric | Status | Independence | Filing period |
|---|---|---|---|
| `revenue` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | 2025-07-01 .. 2026-06-30 |
| `net_income` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | 2025-07-01 .. 2026-06-30 |
| `eps_diluted` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | **2025-04-01 .. 2026-03-31** |
| `cash` | `METHODOLOGY_MISMATCH` | `UNVERIFIED_INDEPENDENCE` | .. 2026-06-30 |
| `debt` | `METHODOLOGY_MISMATCH` | `UNVERIFIED_INDEPENDENCE` | .. 2026-06-30 |
| `shares_outstanding` | `PERIOD_MISMATCH` | `NOT_INDEPENDENT` | .. 2026-07-23 |
| `assets` | `UNAVAILABLE` | `NOT_INDEPENDENT` | no vendor observation |

`VALIDATION` **The `eps_diluted` filing period differs from `revenue` and
`net_income` by one quarter.** `eps_diluted` covers 2025-04-01 .. 2026-03-31;
`revenue` and `net_income` cover 2025-07-01 .. 2026-06-30. The vendor stamps
differ accordingly: `obs:cmp-eps_diluted-yahoo-2026-03-31` as_of 2026-03-31,
against `obs:cmp-revenue-yahoo-2026-06-30` as_of 2026-06-30.

These observations have different filing periods. This report does not conclude
that any of them is wrong, and the Context does not either: each is validated
against the other source for its own window, and each pair is internally
consistent for that window.

| Derived | Value | State | Operands |
|---|---|---|---|
| `der:current_pe` | 28.3530 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-current-eps-001` |
| `der:forward_pe` | 21.5080 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-forward-eps-001` |
| `der:consensus_forward_pe` | 21.5080 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-consensus-eps-001` |
| `der:current_ps` | 11.2017 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-revenue-001` |
| `der:current_pfcf` | 55.4907 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-fcf-001` |
| `der:current_ev_ebitda` | 17.8168 | `UNVALIDATED` | `obs:ev-enterprise-value-001`, `obs:ev-ebitda-001` |
| `der:implied_shares` | 7,299,701,146 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-price-001` |

`VALIDATION` All sixteen derived entries are `UNVALIDATED`, for the reason given
in the AAPL report: validations judged `cmp-` observations while the derivations
consume `ev-` observations.

## D. Derived values

`DERIVED` — `current_pe` 28.3530 = 509.22 / 17.96; `forward_pe` 21.5080 =
509.22 / 23.67588; `consensus_forward_pe` 21.5080 = 509.22 / 23.67588;
`current_ps` 11.2017 = 3,717,153,817,339 / 331,839,000,000;
`current_pfcf` 55.4907 = 3,717,153,817,339 / 66,987,000,000;
`current_ev_ebitda` 17.8168 = 3,697,328,817,339 / 207,519,000,000;
`implied_shares` 7,299,701,146 = 3,717,153,817,339 / 509.22.

`UNAVAILABLE` — nine entries, blockers named in `unavailable[].blocks` exactly as
for AAPL.

No figure here is described as cheap, expensive or mispriced.

## E. Data quality

- **Methodology mismatch** — `cash`, `debt`: vendor `UNDECLARED` currency
  against the filing's `USD`.
- **Period mismatch** — `shares_outstanding`: vendor `as_of: null`.
- **Stale / no-recent-value** — **none.** `freshness.stale_metrics` is empty.
  Stated rather than replaced with another category.
- **Unavailable** — `pfcf_band` and the implied block.
- **Insufficient observations** — the three percentiles and the valuation
  reference (7 observations against 20).

## F. Period coherence

Covered in §C. `eps_diluted` is validated over 2025-04-01 .. 2026-03-31 while
`revenue` and `net_income` are validated over 2025-07-01 .. 2026-06-30. **These
observations have different filing periods.** No further inference is drawn.

`INFERENCE` A reader might be tempted to treat the `eps_diluted` window as
stale, or to prefer the longer window. The Context supports neither: the
`period_offset` between vendor and filing is 0 days for all three validations,
so each is aligned for its own period, and the recency state
(`freshness.by_metric`) reports no metric as stale for MSFT.

## G. Unit, currency, basis

No currency mismatch asserted: every stated currency is `USD`; the two
undeclared figures are `null`. No unit mismatch. No share-basis mismatch
recorded; `identity_conflicts` is empty because `implied_shares`
7,299,701,146 sits within 5% of the reported count.

## H. Market-implied requirements

**Context is insufficient to determine the market-implied requirement.**

`valuation_reference.multiple` is `null`, `basis: NONE`,
`eligible_as_reference: false`, `eligibility_reason: "7 observations is below
the required count"` against `min_observations_for_reference = 20`. The implied
block is `UNAVAILABLE / MISSING_INPUT`.

No median is selected, no consensus multiple substituted, no target price built.

## I. Inference separation

`FACT` — §A, each with a `ref`.
`DERIVED` — §D, each traced to operand refs.
`VALIDATION` — §C, including the one-quarter period difference between
`eps_diluted` and `revenue`/`net_income`.
`UNAVAILABLE` — §B and the `MISSING_INPUT` chain in §D.
`INFERENCE` — one, flagged: the observation that a reader might want to treat
the shorter `eps_diluted` window as stale is not supported by the Context. No
`INFERENCE` supports any number in this report.

## Note for the audit

`data_quality.series` for this company reports 16 entries in
`discontinuities` across `revenue`, `net_income` and `eps_diluted`, several with
`from_period` equal to `to_period`, and relative changes of 0.5–3.0. The
Context marks every one `explanation: NOT_EXPLAINED_BY_ST_EVA`. This report does
**not** treat any of them as a real economic discontinuity, because
`data_quality.series.bases` shows the `REPORTED_PERIOD` group for `revenue`
contains both ~90-day quarters and 364-day periods, and differencing across
those spans is not a trend. This is raised in `self_audit.md` as a Context
defect, not used as a finding here.
