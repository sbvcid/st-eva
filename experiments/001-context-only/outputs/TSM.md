# TSM — context-only analysis

Source: `input/TSM.context.json` (sha256 `5EF8ED02E9E0931E`, `context_schema_version 2.3-C.1`, as_of 2026-09-28)
No external data used. Every claim below carries its `ref`.

This is the context the experiment most needs to be read carefully: the Context
refuses three of the figures it would otherwise publish, and each refusal is
carried with a reason.

## A. What the Context clearly knows

| # | Claim | Provenance | ref |
|---|---|---|---|
| 1 | Price 452.88 USD | `FACT` OBSERVED | `obs:ev-price-001` |
| 2 | Market capitalisation 2,008,084,460,181 **USD** | `FACT` OBSERVED | `obs:ev-market-cap-001` |
| 3 | Enterprise value 1,928,367,260,763 **USD** | `FACT` OBSERVED | `obs:ev-enterprise-value-001` |
| 4 | Trailing revenue 4,440,492,457,000 **TWD** | `FACT` OBSERVED | `obs:ev-revenue-001` |
| 5 | Trailing diluted EPS 13.50 **USD**/share | `FACT` OBSERVED | `obs:ev-current-eps-001` |
| 6 | Forward EPS 21.9251 **USD**/share | `FACT` OBSERVED | `obs:ev-forward-eps-001` |
| 7 | Consensus forward EPS 21.9251 **USD**/share | `FACT` OBSERVED | `obs:ev-consensus-eps-001` |
| 8 | EBITDA — unavailable, currency declared TWD | `UNAVAILABLE` OBSERVED | `obs:ev-ebitda-001` |
| 9 | Free cash flow — unavailable, currency declared TWD | `UNAVAILABLE` OBSERVED | `obs:ev-fcf-001` |
| 10 | Filing-side share count at 2025-12-31: 25,932,733,242 | `FACT` OBSERVED | `obs:cmp-shares_outstanding-sec-2025-12-31-000162828026025362` |

Evidence coverage is 11 of 14 available; 3 unavailable.

The mixed currencies in rows 2–7 are the point of this company, not an error.
`obs:ev-revenue-001` declares `currency: TWD`; `obs:ev-market-cap-001`,
`obs:ev-enterprise-value-001`, `obs:ev-current-eps-001`,
`obs:ev-forward-eps-001` and `obs:ev-consensus-eps-001` all declare `USD`.

## B. What the Context clearly does not know

- **`current_ps` — `INCOMPATIBLE_CURRENCY`.** The reason text reads:
  *"divide v1 combines amounts in different currencies (operand 0 is USD,
  operand 1 is TWD). The result would be a number with no economic meaning, so
  it is refused."* The figure carries `provenance_kind: UNAVAILABLE` and **no
  `value` key**. There is no P/S number in this context.
- **`current_pfcf` — `MISSING_INPUT`,** blocked by `obs:ev-fcf-001`.
  `free_cash_flow` is `NOT_REPORTED_BY_SOURCE`.
- **`current_ev_ebitda` — `MISSING_INPUT`,** blocked by both
  `obs:ev-ebitda-001` and `obs:ev-enterprise-value-001` is *available*; the
  blocking input is `obs:ev-ebitda-001`, which is
  `NOT_REPORTED_BY_SOURCE`.
- **Percentiles** `pe_percentile` (blocked by `refc:valuation_reference`),
  `ps_percentile` (blocked by `der:current_ps`), `ev_ebitda_percentile`
  (blocked by `der:current_ev_ebitda`) — `INSUFFICIENT_OBSERVATIONS`.
- **Valuation reference multiple** — `NO_REFERENCE_AVAILABLE`. P/E band carries
  8 observations against 20. Blocks `implied_forward_eps`,
  `consensus_price_at_median`, `pe_percentile`.
- **Secondary reference multiples** — pfcf, EV/EBITDA, P/S, all
  `NO_REFERENCE_AVAILABLE`.
- **The entire implied block** — `UNAVAILABLE / MISSING_INPUT`.
- **`shares_outstanding` is `NO_RECENT_VALUE`** —
  `freshness.by_metric.shares_outstanding` reports
  `latest_as_of: 2025-12-31`, age 165 days, `recency: NO_RECENT_VALUE`.

## C. Validation

Six of the seven metrics are `UNAVAILABLE`: `assets`, `cash`, `debt`,
`eps_diluted`, `net_income`, `revenue` all have `filing_ref: null`.

| Metric | Status | Independence | Vendor side | Filing side |
|---|---|---|---|---|
| `revenue` | `UNAVAILABLE` | `UNVERIFIED_INDEPENDENCE` | `obs:cmp-revenue-yahoo-2026-06-30` | **none** |
| `net_income` | `UNAVAILABLE` | `UNVERIFIED_INDEPENDENCE` | `obs:cmp-net_income-yahoo-2026-06-30` | **none** |
| `eps_diluted` | `UNAVAILABLE` | `UNVERIFIED_INDEPENDENCE` | `obs:cmp-eps_diluted-yahoo-2026-06-30` | **none** |
| `cash` | `UNAVAILABLE` | `UNVERIFIED_INDEPENDENCE` | `obs:cmp-cash-yahoo-undated` | **none** |
| `debt` | `UNAVAILABLE` | `UNVERIFIED_INDEPENDENCE` | `obs:cmp-debt-yahoo-undated` | **none** |
| `assets` | `UNAVAILABLE` | `NOT_INDEPENDENT` | none | none |
| `shares_outstanding` | `METHODOLOGY_MISMATCH` | `NOT_INDEPENDENT` | `obs:cmp-shares_outstanding-yahoo-undated` | `obs:cmp-shares_outstanding-sec-2025-12-31-…` |

`VALIDATION` **No revenue, net income or EPS figure in this context is
cross-source validated.** Every `filing_ref` is `null` and
`data_quality.cross_source` tallies `{UNAVAILABLE: 6, METHODOLOGY_MISMATCH: 1}`.
The `assets`, `cash` and `debt` filings refs are `None` with reason
`NOT_REPORTED_BY_SOURCE` / undeclared currency respectively.

`shares_outstanding` is the one metric with both sides, and it does not agree.
`comparison_basis.value_ratio` records **5.0000**, and
`ratio_interpretation` reads: *"NOT_EXPLAINED. The counts differ by a factor of
5.0000, which is far more than a rounding difference. One source declares the
security or share basis it counts and the other does not, so the two cannot be
shown to be counting the same thing. ST-EVA does not infer what the factor
represents."* `basis_differences` is `null`, because only one side declared a
basis at all.

| Derived | Value | State | Operands |
|---|---|---|---|
| `der:current_pe` | 33.5467 | `UNVALIDATED` | `obs:ev-price-001` (USD), `obs:ev-current-eps-001` (USD) |
| `der:forward_pe` | 20.6558 | `UNVALIDATED` | `obs:ev-price-001` (USD), `obs:ev-forward-eps-001` (USD) |
| `der:consensus_forward_pe` | 20.6558 | `UNVALIDATED` | `obs:ev-price-001` (USD), `obs:ev-consensus-eps-001` (USD) |
| `der:current_ps` | **`UNAVAILABLE`** | `UNVALIDATED` | `obs:ev-market-cap-001` (USD), `obs:ev-revenue-001` (**TWD**) |
| `der:current_pfcf` | `UNAVAILABLE` | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-fcf-001` (unavailable) |
| `der:current_ev_ebitda` | `UNAVAILABLE` | `UNVALIDATED` | `obs:ev-enterprise-value-001`, `obs:ev-ebitda-001` (unavailable) |
| `der:implied_shares` | 4,434,032,106 | `UNVALIDATED` | `obs:ev-market-cap-001` (USD), `obs:ev-price-001` (USD) |

`VALIDATION` `current_pe`, `forward_pe` and `consensus_forward_pe` survive
because **both** their operands are USD-denominated. The Context does not
refuse a P/E merely because the company reports in another currency; it refuses
only where the two operands of a single operation are in different currencies.

## D. Derived values

`DERIVED` — `current_pe` 33.5467 = 452.88 / 13.50; `forward_pe` 20.6558 =
452.88 / 21.9251; `consensus_forward_pe` 20.6558 = 452.88 / 21.9251;
`implied_shares` 4,434,032,106 = 2,008,084,460,181 / 452.88.

`UNAVAILABLE` — twelve entries, including every figure that would require mixing
currencies or a reference multiple. `current_ps`, `current_pfcf` and
`current_ev_ebitda` are the three *observed* multiples for this company, and
none of them is available.

No figure is described as cheap, expensive or mispriced. `INFERENCE` A reader
could compute a P/S by converting the TWD revenue at some rate, but the Context
supplies no rate and no converted figure, so this report does not.

## E. Data quality

- **Methodology mismatch** — `shares_outstanding`. The two sides differ by a
  large factor, one source declares its basis and the other declares
  `security_type: UNDECLARED`, so the Context cannot show they are counting the
  same thing. Status `METHODOLOGY_MISMATCH`, not `CONFLICTING`, because a
  *declared* basis difference would be a conflict and this is a declared-versus-
  silent difference.
- **Period mismatch** — **none in `validated_evidence`.** This company has no
  `PERIOD_MISMATCH` verdict, because six of seven metrics have no filing side
  at all and the seventh is refused earlier on basis. Stated rather than
  manufactured.
- **Stale / no-recent-value** — `shares_outstanding`, `latest_as_of
  2025-12-31`, age 165 days.
- **Unavailable** — `free_cash_flow`, `ebitda` (`NOT_REPORTED_BY_SOURCE`), and
  all six cross-source metrics with a null `filing_ref`.
- **Insufficient observations** — three percentiles and the valuation reference
  (8 observations against 20).
- **Identity conflict** — one. `price_times_count_equals_market_cap`:
  derived `implied_shares` **4,434,032,106** against reported
  **25,932,733,242**, `relative_difference 82.9%`,
  `resolution: NO_WINNER_SELECTED`. Both values are retained. This report
  selects neither and does not name the factor.

## F. Period coherence

Only one metric has a filing-side observation with a period:
`shares_outstanding`, `.. 2025-12-31`. Every other filing ref is `null`.

**There is no pair of filing periods to compare for this company.** The
experiment's usual period-coherence check cannot be performed here, and this
report does not substitute a different check to fill the gap.

## G. Unit, currency, basis

This is the case the experiment asks about, and the Context handles it.

- **Currency mismatch — detected and refused.** `obs:ev-market-cap-001` is
  `USD`; `obs:ev-revenue-001` is `TWD`. `current_ps` is `UNAVAILABLE` with
  `INCOMPATIBLE_CURRENCY`. **A USD market capitalisation divided by a TWD
  revenue is not a valid P/S calculation, and this context contains no such
  number.** The engine's own arithmetic is unchanged; the gate is in the
  derivation layer, so the figure is withheld rather than published and then
  annotated.
- **Which figures survive.** `current_pe` is computed because price (USD) and
  EPS (USD) share a currency. `current_ps` is not, because they do not. The
  distinction is currency identity, not unit type — both are `currency` / `per_share`
  and both are `currency` / `currency` respectively.
- **Share basis — declared, unmerged.** The filing-side cover-page count
  carries `basis.shares_basis: FILING_COVER_PAGE_REGISTERED_SECURITY` and
  `excludes_listing_adjustment: true`. The vendor count carries
  `basis.shares_basis: UNDECLARED` and `source_declared: false`. The Context
  reports the factor and refuses to interpret it. **This report does not state an
  ADS ratio**, because the Context does not contain one, and inferring a listing
  ratio from two counts would be exactly the assumption the basis block exists
  to prevent.
- **Identity conflict.** `implied_shares` 4,434,032,106 against a reported
  25,932,733,242 is a 5.85× difference and the Context's own
  `explanation` for it is `NO_WINNER_SELECTED`.

## H. Market-implied requirements

**Context is insufficient to determine the market-implied requirement.**

`valuation_reference.multiple` is `null`, `basis: NONE`,
`eligible_as_reference: false`, `eligibility_reason: "8 observations is below
the required count"`. The implied block is `UNAVAILABLE / MISSING_INPUT`.

This company additionally has no cross-source validation for revenue, net
income or EPS, so even the inputs that are present here carry a single source.
No median is selected, no consensus multiple substituted, no target price
built.

## I. Inference separation

`FACT` — §A, each with a `ref`, including the declared currency on every row.
`DERIVED` — §D, four results, each traced to operand refs and their currencies.
`VALIDATION` — §C, including the null `filing_ref` on six of seven metrics.
`UNAVAILABLE` — §B, including the `INCOMPATIBLE_CURRENCY` refusal and the
`NO_WINNER_SELECTED` identity conflict.
`INFERENCE` — one, flagged: that a reader could construct a P/S by applying a
currency conversion, and that the Context deliberately provides no rate for it.
No `INFERENCE` supports any number in this report, and no ADS ratio, listing
relationship, or currency conversion is asserted anywhere in it.
