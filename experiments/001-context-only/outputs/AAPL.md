# AAPL — context-only analysis

Source: `input/AAPL.context.json` (sha256 `6C8EECB83A0EDD35`, `context_schema_version 2.3-C.1`, as_of 2026-09-28)
No external data used. Every claim below carries its `ref`.

## A. What the Context clearly knows

| # | Claim | Provenance | ref |
|---|---|---|---|
| 1 | Price 338.40 USD | `FACT` OBSERVED | `obs:ev-price-001` |
| 2 | Market capitalisation 4,918,530,543,600 USD | `FACT` OBSERVED | `obs:ev-market-cap-001` |
| 3 | Enterprise value 4,940,475,543,600 USD | `FACT` OBSERVED | `obs:ev-enterprise-value-001` |
| 4 | Trailing revenue 466,823,000,000 USD | `FACT` OBSERVED | `obs:ev-revenue-001` |
| 5 | Trailing diluted EPS 8.66 USD/share | `FACT` OBSERVED | `obs:ev-current-eps-001` |
| 6 | Consensus forward EPS 9.57829 USD/share | `FACT` OBSERVED | `obs:ev-consensus-eps-001` |
| 7 | Free cash flow 136,683,000,000 USD | `FACT` OBSERVED | `obs:ev-fcf-001` |
| 8 | EBITDA 167,959,000,000 USD | `FACT` OBSERVED | `obs:ev-ebitda-001` |
| 9 | Filing-side trailing revenue to 2026-06-27: 466,823,000,000 USD | `FACT` OBSERVED | `obs:cmp-revenue-sec-ttm-to-2026-06-27-000032019326000020` |
| 10 | Filing-side total assets at 2026-06-27: 383,266,000,000 USD | `FACT` OBSERVED | `obs:cmp-assets-sec-2026-06-27-000032019326000020` |

Evidence coverage is 13 of 14 available; `evidence_coverage.unavailable` = 1.

## B. What the Context clearly does not know

- **P/FCF band** — `UNAVAILABLE`, `reason_kind: NOT_REPORTED_BY_SOURCE`.
  `pfcf_band` was requested and not provided by `YahooFinanceFundamentals`.
  Blocks no derived value, because no percentile is computed from it. It is
  listed in `unavailable` with `blocks: []`.
- **Valuation reference multiple** — `NO_REFERENCE_AVAILABLE`. The P/E band
  carries 8 observations against `min_observations_for_reference = 20`.
  Blocks `der:implied_forward_eps`, `der:consensus_price_at_median`,
  `der:pe_percentile`.
- **Secondary reference multiples** (pfcf, EV/EBITDA, P/S) — all four
  `NO_REFERENCE_AVAILABLE`, each blocking exactly one derived value
  (`der:implied_fcf`, `der:implied_ebitda`, `der:implied_revenue`).
- **Percentile positions** `pe_percentile`, `ps_percentile`,
  `ev_ebitda_percentile` — `INSUFFICIENT_OBSERVATIONS`. The bands exist but
  each declares 8 observations, below the 20 required.
- **The entire implied block** — `implied_forward_eps`, `required_eps_cagr`,
  `consensus_price_at_median`, `implied_fcf`, `implied_ebitda`,
  `implied_revenue` all carry `provenance_kind: UNAVAILABLE` with
  `reason_kind: MISSING_INPUT` and no `value` key at all.

`UNVERIFIED`: the vendor figures for cash and debt carry
`currency: null` and `basis.reporting_currency: UNDECLARED`. The Context does
not assert a currency for them and must not be read as asserting one.

## C. Validation

Seven metrics carry a verdict. Six have a filing-side observation; `assets` has
a filing observation and no vendor one.

| Metric | Status | Independence | Filing period |
|---|---|---|---|
| `revenue` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | 2025-06-29 .. 2026-06-27 |
| `net_income` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | 2025-06-29 .. 2026-06-27 |
| `eps_diluted` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | 2025-06-29 .. 2026-06-27 |
| `cash` | `METHODOLOGY_MISMATCH` | `UNVERIFIED_INDEPENDENCE` | .. 2026-06-27 |
| `debt` | `METHODOLOGY_MISMATCH` | `UNVERIFIED_INDEPENDENCE` | .. 2026-06-27 |
| `shares_outstanding` | `PERIOD_MISMATCH` | `NOT_INDEPENDENT` | .. 2026-07-17 |
| `assets` | `UNAVAILABLE` | `NOT_INDEPENDENT` | no vendor observation |

**The linkage the experiment asks about does not hold, and the Context says so.**
Every one of the sixteen `der:` entries carries `validation_state:
UNVALIDATED`, including:

| Derived | Value | State | Operands |
|---|---|---|---|
| `der:current_pe` | 39.0762 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-current-eps-001` |
| `der:forward_pe` | 35.3039 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-forward-eps-001` |
| `der:consensus_forward_pe` | 35.3299 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-consensus-eps-001` |
| `der:current_ps` | 10.5362 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-revenue-001` |
| `der:current_pfcf` | 35.9849 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-fcf-001` |
| `der:current_ev_ebitda` | 29.4148 | `UNVALIDATED` | `obs:ev-enterprise-value-001`, `obs:ev-ebitda-001` |
| `der:implied_shares` | 14,534,664,727 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-price-001` |

`VALIDATION` The reason is visible in the operands. Every validation judged a
`cmp-` observation — for example `revenue` was validated on
`obs:cmp-revenue-yahoo-2026-06-30` against
`obs:cmp-revenue-sec-ttm-to-2026-06-27-…`. Every derived figure is computed
from an `ev-` observation — `obs:ev-revenue-001`. These are different
observations of the same metric. Sharing a metric name is not the same
observation, and the Context's `validation_state` correctly reports that no
valuation figure rests on a cross-validated input.

## D. Derived values

All sixteen were checked against `provenance.derivations`.

`DERIVED` — arithmetically: `current_pe` 39.0762 = 338.40 / 8.66;
`forward_pe` 35.3039 = 338.40 / 9.58535; `consensus_forward_pe` 35.3299 =
338.40 / 9.57829; `current_ps` 10.5362 = 4,918,530,543,600 / 466,823,000,000;
`current_pfcf` 35.9849 = 4,918,530,543,600 / 136,683,000,000;
`current_ev_ebitda` 29.4148 = 4,940,475,543,600 / 167,959,000,000;
`implied_shares` 14,534,664,727 = 4,918,530,543,600 / 338.40
(`shares_from_market_cap`).

`UNAVAILABLE` — nine entries carry no `value` key. Each names its blocker in
`unavailable[].blocks`: `implied_forward_eps` → `refc:valuation_reference`;
`required_eps_cagr` → `der:implied_forward_eps`; `implied_fcf` →
`refc:pfcf_reference`; `implied_ebitda` → `refc:ev_ebitda_reference`;
`implied_revenue` → `refc:ps_reference`; the three percentiles → the relevant
band.

None of these figures is described here as cheap, expensive, or mispriced. The
Context does not make that claim and neither does this report.

## E. Data quality

- **Methodology mismatch** — `cash`, `debt`. The vendor observation
  `obs:cmp-cash-yahoo-undated` declares no currency
  (`basis.reporting_currency: UNDECLARED`) against the filing's `USD`, so the
  two are not comparable and no difference is computed.
- **Period mismatch** — `shares_outstanding`. The vendor observation
  `obs:cmp-shares_outstanding-yahoo-undated` has `as_of: null`, so the two
  cannot be attributed to the same moment.
- **Stale / no-recent-value** — none. `freshness.stale_metrics` is empty and
  every metric is `CURRENT` or `UNDATED_AVAILABILITY`. This company has no
  stale series; that is stated rather than filled in with another case.
- **Unavailable** — `pfcf_band`, and the entire implied block (§B).
- **Insufficient observations** — all three percentiles, and the valuation
  reference itself (8 observations against a required 20).
- **Identity conflicts** — none. `price_times_count_equals_market_cap` does not
  fire: `implied_shares` 14,534,664,727 is within 5% of the reported count.

## F. Period coherence

The three `CONSISTENT` metrics — `revenue`, `net_income`, `eps_diluted` — all
cover the filing period 2025-06-29 .. 2026-06-27. The vendor side is stamped
`as_of 2026-06-30` for all three, a 3-day offset.

`VALIDATION` The three validated windows are mutually consistent here. This is
a statement about the periods only; it is not a judgement that the underlying
figures are correct.

## G. Unit, currency, basis

No currency mismatch is asserted anywhere in this context: every `currency`
that is stated is `USD`, and the two figures with an unstated currency are
`null` rather than mislabelled. No unit mismatch: `per_share`, `currency` and
`multiple` are used consistently. No share-basis mismatch is recorded —
`identity_conflicts` is empty and no basis key is declared as differing for
`shares_outstanding`.

`basis` is `UNDECLARED` for the vendor share count
(`obs:cmp-shares-outstanding-yahoo-undated`), meaning the Context does not claim
to know what the vendor is counting. `INFERENCE` It would be a mistake to infer
that it is the same security as the filing's cover-page count, and this report
does not.

## H. Market-implied requirements

**Context is insufficient to determine the market-implied requirement.**

`valuation_reference.multiple` is `null`, `basis: NONE`,
`eligible_as_reference: false`, with
`eligibility_reason: "8 observations is below the required count"` against
`min_observations_for_reference: 20`.

Consequently `implied_forward_eps`, `required_eps_cagr`, `consensus_price_at_median`,
`implied_fcf`, `implied_ebitda` and `implied_revenue` are all
`UNAVAILABLE / MISSING_INPUT`.

This report does not select a median, substitute a consensus multiple, or build
a target price. The Context states the condition itself: *"Implied fundamentals
are conditional on the selected valuation multiple. Price alone does not
identify a unique fundamental path."*

## I. Inference separation

`FACT` — every row in §A, each with a `ref`.
`DERIVED` — the seven arithmetic results in §D, each traced to its operand refs.
`VALIDATION` — the seven verdicts in §C and the `UNVALIDATED` linkage finding.
`UNAVAILABLE` — §B and the `MISSING_INPUT` chain in §D.
`INFERENCE` — only two, both flagged: that `UNDECLARED` basis on the vendor
share count must not be read as the filing's basis, and that the mutual period
agreement in §F is an observation about periods rather than a correctness claim.
No `INFERENCE` is used to support any number in this report.
