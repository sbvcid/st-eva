# NVDA — context-only analysis

Source: `input/NVDA.context.json` (sha256 `73BE254B85EC7842`, `context_schema_version 2.3-C.1`, as_of 2026-09-28)
No external data used. Every claim below carries its `ref`.

## A. What the Context clearly knows

| # | Claim | Provenance | ref |
|---|---|---|---|
| 1 | Price 228.86 USD | `FACT` OBSERVED | `obs:ev-price-001` |
| 2 | Market capitalisation 5,445,389,970,000 USD | `FACT` OBSERVED | `obs:ev-market-cap-001` |
| 3 | Enterprise value 5,421,271,970,000 USD | `FACT` OBSERVED | `obs:ev-enterprise-value-001` |
| 4 | Trailing revenue 302,970,000,000 USD | `FACT` OBSERVED | `obs:ev-revenue-001` |
| 5 | Trailing diluted EPS 8.03 USD/share | `FACT` OBSERVED | `obs:ev-current-eps-001` |
| 6 | Forward EPS 15.68263 USD/share | `FACT` OBSERVED | `obs:ev-forward-eps-001` |
| 7 | Consensus forward EPS 15.68263 USD/share | `FACT` OBSERVED | `obs:ev-consensus-eps-001` |
| 8 | Free cash flow 127,006,000,000 USD | `FACT` OBSERVED | `obs:ev-fcf-001` |
| 9 | EBITDA 233,894,000,000 USD | `FACT` OBSERVED | `obs:ev-ebitda-001` |
| 10 | Filing-side trailing EPS to 2026-07-26: 7.91 USD/share | `FACT` OBSERVED | `obs:cmp-eps_diluted-sec-ttm-to-2026-07-26-000104581026000075` |

Evidence coverage is 14 of 14 available; `evidence_coverage.unavailable` = 0.
This is the only company of the six with complete engine-input coverage.

## B. What the Context clearly does not know

- **Valuation reference multiple** — `NO_REFERENCE_AVAILABLE`. P/E band carries
  10 observations against a required 20. Blocks `implied_forward_eps`,
  `consensus_price_at_median`, `pe_percentile`.
- **Secondary reference multiples** — pfcf, EV/EBITDA, P/S, all four
  `NO_REFERENCE_AVAILABLE`, each blocking one derived value. Unlike the other
  four US contexts, this company *has* a P/FCF band
  (`obs:ev-pfcf-band-001`, 10th 38.28); it is still ineligible at 10
  observations.
- **Percentiles** `pe_percentile`, `ps_percentile`, `ev_ebitda_percentile` —
  `INSUFFICIENT_OBSERVATIONS`.
- **The entire implied block** — `implied_forward_eps`, `required_eps_cagr`,
  `consensus_price_at_median`, `implied_fcf`, `implied_ebitda`,
  `implied_revenue` are `UNAVAILABLE / MISSING_INPUT`, no `value` key.
- **`revenue` is `NO_RECENT_VALUE`.** `freshness.by_metric.revenue` reports
  `recency: NO_RECENT_VALUE`, `latest_as_of: 2026-07-31`, age 1,655 days. The
  newest revenue observation with a *dated* publication is from 2022-03-18;
  the 2026-07-31 vendor figure exists but carries no `available_at`, so it
  cannot establish recency.

`UNVERIFIED` — vendor cash and debt carry `currency: null` and
`basis.reporting_currency: UNDECLARED`.

## C. Validation

| Metric | Status | Independence | Filing period |
|---|---|---|---|
| `eps_diluted` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | 2025-07-28 .. 2026-07-26 |
| `net_income` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | 2025-07-28 .. 2026-07-26 |
| `revenue` | **`PERIOD_MISMATCH`** | `UNVERIFIED_INDEPENDENCE` | **2021-02-01 .. 2022-01-30** |
| `cash` | `METHODOLOGY_MISMATCH` | `UNVERIFIED_INDEPENDENCE` | .. 2026-07-26 |
| `debt` | `METHODOLOGY_MISMATCH` | `UNVERIFIED_INDEPENDENCE` | .. 2026-07-26 |
| `shares_outstanding` | `PERIOD_MISMATCH` | `NOT_INDEPENDENT` | .. 2026-08-21 |
| `assets` | `UNAVAILABLE` | `NOT_INDEPENDENT` | no vendor observation |

`VALIDATION` **`revenue` could not be validated against the vendor's current
figure.** The verdict compares
`obs:cmp-revenue-yahoo-2026-07-31` (as_of 2026-07-31) against
`obs:cmp-revenue-sec-ttm-to-2022-01-30-…`, a window ending
**2022-01-30** — roughly four and a half years before the vendor's stamp. The
anchors fall outside the alignment window, so the Context refuses rather than
comparing. This is consistent with `revenue` being the one metric marked
`NO_RECENT_VALUE`.

`eps_diluted` and `net_income` are validated over 2025-07-28 .. 2026-07-26,
matching the vendor stamp of 2026-07-31 within 5 days.

| Derived | Value | State | Operands |
|---|---|---|---|
| `der:current_pe` | 28.5006 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-current-eps-001` |
| `der:forward_pe` | 14.5932 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-forward-eps-001` |
| `der:consensus_forward_pe` | 14.5932 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-consensus-eps-001` |
| `der:current_ps` | 17.9734 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-revenue-001` |
| `der:current_pfcf` | 42.8751 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-fcf-001` |
| `der:current_ev_ebitda` | 23.1783 | `UNVALIDATED` | `obs:ev-enterprise-value-001`, `obs:ev-ebitda-001` |
| `der:implied_shares` | 23,793,541,772 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-price-001` |

`VALIDATION` All sixteen derived entries are `UNVALIDATED`. Validations judged
`cmp-` observations; derivations consume `ev-` observations.

## D. Derived values

`DERIVED` — `current_pe` 28.5006 = 228.86 / 8.03; `forward_pe` 14.5932 =
228.86 / 15.68263; `consensus_forward_pe` 14.5932 = 228.86 / 15.68263;
`current_ps` 17.9734 = 5,445,389,970,000 / 302,970,000,000;
`current_pfcf` 42.8751 = 5,445,389,970,000 / 127,006,000,000;
`current_ev_ebitda` 23.1783 = 5,421,271,970,000 / 233,894,000,000;
`implied_shares` 23,793,541,772 = 5,445,389,970,000 / 228.86.

`UNAVAILABLE` — nine entries, blockers named in `unavailable[].blocks`.

No figure is described as cheap, expensive or mispriced. `INFERENCE` The gap
between `current_pe` 28.5006 and `forward_pe` 14.5932 is arithmetically
visible; whether that gap is a judgement about the business is not in the
Context, and this report does not make it.

## E. Data quality

- **Methodology mismatch** — `cash`, `debt`: vendor `UNDECLARED` currency
  against the filing's `USD`.
- **Period mismatch** — `revenue` (2022 window against a 2026 vendor stamp)
  and `shares_outstanding` (vendor `as_of: null`).
- **Stale / no-recent-value** — **`revenue`**, `NO_RECENT_VALUE`, latest dated
  availability 2022-03-18, age 1,655 days. This is the only company of the six
  with a stale revenue series.
- **Unavailable** — `assets` (no vendor observation) and the implied block.
- **Insufficient observations** — the three percentiles and the valuation
  reference (10 observations against 20).
- **Identity conflicts** — none. `implied_shares` 23,793,541,772 is within 5% of
  the reported count.

## F. Period coherence

`eps_diluted` and `net_income` are validated over 2025-07-28 .. 2026-07-26.
`revenue` is validated against a filing window ending 2022-01-30, which is why
its verdict is `PERIOD_MISMATCH` rather than a comparison.

**These observations have different filing periods.** No inference is drawn
about which is correct. The Context records the mismatch and the recency state
separately.

## G. Unit, currency, basis

No currency mismatch asserted: every stated currency is `USD`; undeclared
figures are `null`. No unit mismatch. No share-basis conflict recorded;
`identity_conflicts` is empty. This is the only context of the six with a
complete `currency` declaration on every stated figure and no identity
conflict.

## H. Market-implied requirements

**Context is insufficient to determine the market-implied requirement.**

`valuation_reference.multiple` is `null`, `basis: NONE`,
`eligible_as_reference: false`, `eligibility_reason: "10 observations is below
the required count"`. The implied block is `UNAVAILABLE / MISSING_INPUT`.

Note the specific contrast with the other US contexts: this company has all 14
engine inputs available and the strongest evidence coverage of the six, yet the
implied block is exactly as absent as for the contexts missing inputs. Full
input coverage does not produce a market-implied figure; an eligible reference
multiple does, and this band is too thin.

## I. Inference separation

`FACT` — §A, each with a `ref`.
`DERIVED` — §D, traced to operand refs.
`VALIDATION` — §C, including the `revenue` period mismatch and its link to the
`NO_RECENT_VALUE` recency state.
`UNAVAILABLE` — §B and the `MISSING_INPUT` chain in §D.
`INFERENCE` — one, flagged: that the `current_pe` / `forward_pe` gap is
arithmetically visible but its interpretation is not in the Context. No
`INFERENCE` supports any number in this report.
