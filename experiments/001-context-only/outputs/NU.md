# NU — context-only analysis

Source: `input/NU.context.json` (sha256 `A50C863A2B451DB7`, `context_schema_version 2.3-C.1`, as_of 2026-09-28)
No external data used. Every claim below carries its `ref`.

This is the sparsest context of the six: 10 of 14 engine inputs available, and
all seven cross-source verdicts `UNAVAILABLE`. It is reported at that length.

## A. What the Context clearly knows

| # | Claim | Provenance | ref |
|---|---|---|---|
| 1 | Price 12.23 USD | `FACT` OBSERVED | `obs:ev-price-001` |
| 2 | Market capitalisation 65,793,979,534 USD | `FACT` OBSERVED | `obs:ev-market-cap-001` |
| 3 | Trailing revenue 13,174,203,000 USD | `FACT` OBSERVED | `obs:ev-revenue-001` |
| 4 | Trailing diluted EPS 0.66 USD/share | `FACT` OBSERVED | `obs:ev-current-eps-001` |
| 5 | Forward EPS 1.12985 USD/share | `FACT` OBSERVED | `obs:ev-forward-eps-001` |
| 6 | Consensus forward EPS 1.10138 USD/share | `FACT` OBSERVED | `obs:ev-consensus-eps-001` |
| 7 | Free cash flow **−1,669,966,000 USD** (negative) | `FACT` OBSERVED | `obs:ev-fcf-001` |
| 8 | Realized annualized volatility 0.4439; return_1d −0.1001 | `FACT` OBSERVED | `obs:ev-metrics-001` |

Evidence coverage is 10 of 14 available; 4 unavailable.

Row 7 is negative and is reported as observed. The Context does not restate it
as a magnitude, and neither does this report.

## B. What the Context clearly does not know

- **`ebitda` — `NOT_REPORTED_BY_SOURCE`,** blocking `der:current_ev_ebitda`.
- **`enterprise_value` — `NOT_REPORTED_BY_SOURCE,**` blocking
  `der:current_ev_ebitda` and `der:implied_ebitda`. The observation exists with
  `value: null` and `currency: null`.
- **`ev_ebitda_band` — `NOT_REPORTED_BY_SOURCE,**` blocking
  `der:ev_ebitda_percentile`.
- **`pfcf_band` — `NOT_REPORTED_BY_SOURCE.**
- **`current_pfcf` — `NOT_AVAILABLE`,** reason: *"not computable: the engine
  produced no value and no substitute is permitted."* The available free cash
  flow at `obs:ev-fcf-001` is negative.
- **Valuation reference multiple** — `NO_REFERENCE_AVAILABLE`. P/E band carries
  5 observations against 20. Blocks `implied_forward_eps`,
  `consensus_price_at_median`, `pe_percentile`.
- **Secondary reference multiples** — pfcf, EV/EBITDA, P/S, all
  `NO_REFERENCE_AVAILABLE`.
- **Percentiles** `pe_percentile`, `ps_percentile` (`INSUFFICIENT_OBSERVATIONS`),
  `ev_ebitda_percentile` (`INSUFFICIENT_OBSERVATIONS`).
- **The entire implied block** — `UNAVAILABLE / MISSING_INPUT`.
- **All seven cross-source metrics** — `filing_ref: null` for every one.

`UNVERIFIED` — no metric in this context carries any cross-source validation, so
nothing about any figure here has been confirmed against a second source. The
`independence` field is present on all seven verdicts and is paired with
`UNAVAILABLE`.

## C. Validation

`data_quality.cross_source` is `{"UNAVAILABLE": 7}`. Every metric has
`filing_ref: null`.

| Metric | Status | Independence | Filing side |
|---|---|---|---|
| `revenue` | `UNAVAILABLE` | `UNVERIFIED_INDEPENDENCE` | none |
| `net_income` | `UNAVAILABLE` | `UNVERIFIED_INDEPENDENCE` | none |
| `eps_diluted` | `UNAVAILABLE` | `UNVERIFIED_INDEPENDENCE` | none |
| `cash` | `UNAVAILABLE` | `UNVERIFIED_INDEPENDENCE` | none |
| `debt` | `UNAVAILABLE` | `UNVERIFIED_INDEPENDENCE` | none |
| `assets` | `UNAVAILABLE` | `NOT_INDEPENDENT` | none |
| `shares_outstanding` | `UNAVAILABLE` | `NOT_INDEPENDENT` | none |

| Derived | Value | State | Operands |
|---|---|---|---|
| `der:current_pe` | 18.5303 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-current-eps-001` |
| `der:forward_pe` | 10.8244 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-forward-eps-001` |
| `der:consensus_forward_pe` | 11.1043 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-consensus-eps-001` |
| `der:current_ps` | 4.9942 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-revenue-001` |
| `der:current_pfcf` | `UNAVAILABLE` | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-fcf-001` |
| `der:current_ev_ebitda` | `UNAVAILABLE` | `UNVALIDATED` | `obs:ev-enterprise-value-001`, `obs:ev-ebitda-001` |
| `der:implied_shares` | 5,379,720,322 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-price-001` |

`VALIDATION` All sixteen derived entries are `UNVALIDATED`, and for this company
there is nothing to link to in the first place.

## D. Derived values

`DERIVED` — `current_pe` 18.5303 = 12.23 / 0.66; `forward_pe` 10.8244 =
12.23 / 1.12985; `consensus_forward_pe` 11.1043 = 12.23 / 1.10138;
`current_ps` 4.9942 = 65,793,979,534 / 13,174,203,000;
`implied_shares` 5,379,720,322 = 65,793,979,534 / 12.23.

`UNAVAILABLE` — `current_pfcf`, `current_ev_ebitda`, and the nine
reference-dependent entries.

**No P/FCF is reported.** The available free cash flow is negative and
`current_pfcf` carries no value. This report does not substitute the absolute
value of free cash flow, and does not describe the absence as meaningful.

No figure is described as cheap, expensive or mispriced.

## E. Data quality

- **Methodology mismatch** — **none.** All seven verdicts are `UNAVAILABLE`,
  because no filing-side observation exists for any metric. Stated rather than
  manufactured from a different category.
- **Period mismatch** — **none**, for the same reason: a period comparison
  requires two observations to align.
- **Stale / no-recent-value** — **none.** `freshness.stale_metrics` is empty;
  the metrics that are not `CURRENT` are `UNDATED_AVAILABILITY`, which is
  reported in `freshness.by_metric` but is not the same state. This company
  has no stale series and none is asserted.
- **Unavailable** — `ebitda`, `enterprise_value`, `ev_ebitda_band`,
  `pfcf_band`, all seven cross-source metrics, and the implied block.
- **Insufficient observations** — the three percentiles and the valuation
  reference (5 observations against 20).
- **Identity conflict** — one. `price_times_count_equals_market_cap`: derived
  `implied_shares` **5,379,720,322** against reported **3,808,087,961**,
  `relative_difference 29.2%`, `resolution: NO_WINNER_SELECTED`. Both values
  are retained. This report selects neither.

## F. Period coherence

**Not performable for this company.** No metric has a filing-side observation
with a period, so there are no two filing periods to compare. The experiment's
usual check is reported as inapplicable rather than replaced.

## G. Unit, currency, basis

- **Currency** — `asset.currency` is `USD` and every available figure is
  `USD`. No currency mismatch is present. The two figures with `currency: null`
  are `ebitda` and `enterprise_value`, and both are unavailable, so the absence
  cannot produce a false combination.
- **Unit** — no unit mismatch. `per_share`, `currency` and `multiple` are used
  consistently, and the one refused ratio is refused for unavailability rather
  than a unit conflict.
- **Share basis** — **a conflict, not a mismatch.**
  `data_quality.identity_conflicts` records
  `price_times_count_equals_market_cap` with a 29.2% difference and
  `NO_WINNER_SELECTED`. No basis is declared on either side
  (`basis.security_type: UNDECLARED` for the vendor count; the reported count's
  basis is not declared either), so the Context reports the size of the
  disagreement and explicitly declines to say which count is right. **This
  report does not choose, average, or reconcile the two.**

## H. Market-implied requirements

**Context is insufficient to determine the market-implied requirement.**

`valuation_reference.multiple` is `null`, `basis: NONE`,
`eligible_as_reference: false`, `eligibility_reason: "5 observations is below
the required count"` against `min_observations_for_reference = 20`. The implied
block is `UNAVAILABLE / MISSING_INPUT`.

This context has the least cross-source evidence of the six — none — so no
implied figure here rests on a second source. No median is selected, no
consensus multiple substituted, no target price built.

## I. Inference separation

`FACT` — §A, each with a `ref`, including the negative free cash flow and the
vendor share count that conflicts with the derived one.
`DERIVED` — §D, five results, each traced to operand refs.
`VALIDATION` — §C, including the null `filing_ref` on all seven metrics.
`UNAVAILABLE` — §B, including `current_pfcf` refused with a negative free cash
flow.
`INFERENCE` — one, flagged: that the absence of a period comparison and of a
methodology mismatch here is a consequence of having no filing side at all,
rather than a clean result. No `INFERENCE` supports any number in this report,
and no share count is selected between the two the Context reports.
