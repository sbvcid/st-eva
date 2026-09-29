# MU — context-only analysis

Source: `input/MU.context.json` (sha256 `BC64D39E6CF9E097`, `context_schema_version 2.3-C.1`, as_of 2026-09-28)
No external data used. Every claim below carries its `ref`.

## A. What the Context clearly knows

| # | Claim | Provenance | ref |
|---|---|---|---|
| 1 | Price 1,053.98 USD | `FACT` OBSERVED | `obs:ev-price-001` |
| 2 | Market capitalisation 1,210,573,930,693 USD | `FACT` OBSERVED | `obs:ev-market-cap-001` |
| 3 | Enterprise value 1,190,927,930,693 USD | `FACT` OBSERVED | `obs:ev-enterprise-value-001` |
| 4 | Trailing revenue 90,274,000,000 USD | `FACT` OBSERVED | `obs:ev-revenue-001` |
| 5 | Trailing diluted EPS 43.11 USD/share | `FACT` OBSERVED | `obs:ev-current-eps-001` |
| 6 | Forward EPS 161.09428 USD/share | `FACT` OBSERVED | `obs:ev-forward-eps-001` |
| 7 | Consensus forward EPS 161.09428 USD/share | `FACT` OBSERVED | `obs:ev-consensus-eps-001` |
| 8 | Free cash flow 26,172,000,000 USD | `FACT` OBSERVED | `obs:ev-fcf-001` |
| 9 | EBITDA 68,305,000,000 USD | `FACT` OBSERVED | `obs:ev-ebitda-001` |
| 10 | Filing-side trailing revenue to 2026-05-28: 90,274,000,000 USD | `FACT` OBSERVED | `obs:cmp-revenue-sec-ttm-to-2026-05-28-000072312526000015` |

Evidence coverage is 13 of 14 available; `evidence_coverage.unavailable` = 1.

## B. What the Context clearly does not know

- **P/FCF band** — `NOT_REPORTED_BY_SOURCE`. Requested and not provided by
  `YahooFinanceFundamentals`. `blocks: []`.
- **`debt` has no current value** — `NO_RECENT_VALUE`.
  `freshness.by_metric.debt` reports `recency: NO_RECENT_VALUE`,
  `latest_as_of: 2013-05-30`, age 4,830 days. The newest filing-side debt
  observation is from 2013-05-30
  (`obs:cmp-debt-sec-2013-05-30-000072312513000108`, value 3,624,000,000 USD).
  The vendor's `obs:cmp-debt-yahoo-undated` (84,343,996,416) carries no
  `available_at` and cannot supply a current value either.
- **Valuation reference multiple** — `NO_REFERENCE_AVAILABLE`. P/E band carries
  **3** observations against a required 20, the thinnest of the six. Blocks
  `implied_forward_eps`, `consensus_price_at_median`, `pe_percentile`.
- **Secondary reference multiples** — pfcf, EV/EBITDA, P/S, all
  `NO_REFERENCE_AVAILABLE`.
- **Percentiles** `pe_percentile`, `ps_percentile`, `ev_ebitda_percentile` —
  `INSUFFICIENT_OBSERVATIONS`.
- **The entire implied block** — `UNAVAILABLE / MISSING_INPUT`, no `value` key.

`UNVERIFIED` — vendor cash and debt carry `currency: null` and
`basis.reporting_currency: UNDECLARED`.

## C. Validation

| Metric | Status | Independence | Filing period |
|---|---|---|---|
| `revenue` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | 2025-05-30 .. 2026-05-28 |
| `net_income` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | 2025-05-30 .. 2026-05-28 |
| `eps_diluted` | `CONSISTENT` | `UNVERIFIED_INDEPENDENCE` | 2025-05-30 .. 2026-05-28 |
| `cash` | `METHODOLOGY_MISMATCH` | `UNVERIFIED_INDEPENDENCE` | .. 2026-05-28 |
| `debt` | `METHODOLOGY_MISMATCH` | `UNVERIFIED_INDEPENDENCE` | **.. 2013-05-30** |
| `shares_outstanding` | `PERIOD_MISMATCH` | `NOT_INDEPENDENT` | .. 2026-06-17 |
| `assets` | `UNAVAILABLE` | `NOT_INDEPENDENT` | no vendor observation |

`VALIDATION` **The `debt` verdict compares against a 2013 observation.** The
filing side is `obs:cmp-debt-sec-2013-05-30-…` and the vendor side is
`obs:cmp-debt-yahoo-undated`. The status is `METHODOLOGY_MISMATCH` rather than
`PERIOD_MISMATCH` because the vendor declares no currency at all, so the
currency check fires before the period check. Both facts are present: the
Context reports the 2013 filing period *and* the `NO_RECENT_VALUE` recency
state. A reader checking only the verdict would miss the staleness; the
recency section is where it lives.

| Derived | Value | State | Operands |
|---|---|---|---|
| `der:current_pe` | 24.4486 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-current-eps-001` |
| `der:forward_pe` | 6.5426 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-forward-eps-001` |
| `der:consensus_forward_pe` | 6.5426 | `UNVALIDATED` | `obs:ev-price-001`, `obs:ev-consensus-eps-001` |
| `der:current_ps` | 13.4100 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-revenue-001` |
| `der:current_pfcf` | 46.2545 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-fcf-001` |
| `der:current_ev_ebitda` | 17.4354 | `UNVALIDATED` | `obs:ev-enterprise-value-001`, `obs:ev-ebitda-001` |
| `der:implied_shares` | 1,148,573,911 | `UNVALIDATED` | `obs:ev-market-cap-001`, `obs:ev-price-001` |

`VALIDATION` All sixteen derived entries are `UNVALIDATED`: validations judged
`cmp-` observations, derivations consume `ev-` observations.

## D. Derived values

`DERIVED` — `current_pe` 24.4486 = 1,053.98 / 43.11; `forward_pe` 6.5426 =
1,053.98 / 161.09428; `consensus_forward_pe` 6.5426 = 1,053.98 / 161.09428;
`current_ps` 13.4100 = 1,210,573,930,693 / 90,274,000,000;
`current_pfcf` 46.2545 = 1,210,573,930,693 / 26,172,000,000;
`current_ev_ebitda` 17.4354 = 1,190,927,930,693 / 68,305,000,000;
`implied_shares` 1,148,573,911 = 1,210,573,930,693 / 1,053.98.

`UNAVAILABLE` — nine entries, blockers named in `unavailable[].blocks`.

`current_pe` 24.4486 and `forward_pe` 6.5426 are both present and both
`UNVALIDATED`. This report does not characterise that gap. The Context contains
no field that would support a judgement about it, and the pe_band carries 3
observations, which is far too thin to place anything in a distribution.

## E. Data quality

- **Methodology mismatch** — `cash`, `debt`: vendor `UNDECLARED` currency
  against the filing's `USD`. For `debt` the filing side is a 2013 observation.
- **Period mismatch** — `shares_outstanding`: vendor `as_of: null` against a
  filing date of 2026-06-17.
- **Stale / no-recent-value** — **`debt`**, `NO_RECENT_VALUE`, latest_as_of
  2013-05-30, age 4,830 days. The 2013 observation is retained in
  `provenance.refs` and in `observed.debt` with its value intact; the
  `freshness.by_metric` entry is what marks it as not current.
- **Unavailable** — `pfcf_band` and the implied block.
- **Insufficient observations** — the three percentiles and the valuation
  reference, at 3 observations against a required 20.
- **Identity conflicts** — none. `implied_shares` 1,148,573,911 is within 5% of
  the reported count.
- **Series discontinuity** — `debt` shows
  `2026-04-26 -> 2026-07-26`, `relative_change 2.94`,
  `explanation: NOT_EXPLAINED_BY_ST_EVA`. This is stated as recorded. The
  Context explicitly declines to say what caused it, and this report does not
  guess.

## F. Period coherence

`revenue`, `net_income` and `eps_diluted` are all validated over
2025-05-30 .. 2026-05-28, with the vendor side stamped 2026-05-31. `debt` is
the outlier, validated against a 2013 window. **These observations have
different filing periods.** No inference is drawn about which is correct; the
Context marks `debt` stale independently through `freshness`.

## G. Unit, currency, basis

No currency mismatch asserted: every stated currency is `USD`; undeclared
figures are `null`. No unit mismatch. No share-basis conflict recorded;
`identity_conflicts` is empty. The `debt` figures in this context span two
incompatible vintages — a 2013 filing observation and an undated vendor figure
— which is a freshness and availability problem rather than a currency or basis
problem, and the Context reports it as such.

## H. Market-implied requirements

**Context is insufficient to determine the market-implied requirement.**

`valuation_reference.multiple` is `null`, `basis: NONE`,
`eligible_as_reference: false`, `eligibility_reason: "3 observations is below
the required count"` against `min_observations_for_reference = 20`. The implied
block is `UNAVAILABLE / MISSING_INPUT`.

No median is selected, no consensus multiple substituted, no target price built.
In particular this report does not use `forward_pe` 6.5426, or the
`CONSISTENT` EPS verdict, to construct an implied requirement. A verified
forward EPS is not a reference multiple, and the Context does not treat it as
one.

## I. Inference separation

`FACT` — §A, each with a `ref`.
`DERIVED` — §D, traced to operand refs.
`VALIDATION` — §C, including that the `debt` verdict sits on a 2013 observation.
`UNAVAILABLE` — §B, including the retained-but-stale 2013 debt value.
`INFERENCE` — one, flagged: that a reader checking only the `debt` verdict
would miss its staleness, which is why both sections are reported. No
`INFERENCE` supports any number in this report.
