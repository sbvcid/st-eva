# ST-EVA 2.2.3 Specification

## 1. Objective

ST-EVA is a market-implied assumptions engine.

Primary question:

Given the observed market price, what earnings or valuation assumptions are required for that price to be consistent with an explicit valuation reference?

The engine is descriptive and conditional. It is not a price-target or trading-signal engine.

## 2. Analytical hierarchy

### Observed

Examples:

- current market price;
- current, forward, or consensus EPS supplied by a source;
- historical P/E, P/FCF, P/S, and EV/EBITDA bands;
- current FCF, EBITDA, revenue, enterprise value, and market cap when sourced;
- price and volume history;
- event date supplied by a source.

### Derived

Examples:

- current P/E;
- forward P/E;
- consensus forward P/E;
- implied forward EPS;
- EPS gap;
- required EPS CAGR;
- historical P/E position;
- price at consensus EPS times historical median P/E.

### Conditional inference

Every reverse-engineered figure is conditional on an explicit valuation reference.

Example:

P0 = 425.50
Reference P/E = 30x
Implied forward EPS = 425.50 / 30 = 14.18

Correct interpretation:

14.18 forward EPS is implied conditional on a 30x reference multiple.

Incorrect interpretation:

The market expects EPS of 14.18.

## 3. Forbidden behavior

The core engine must never:

- invent EPS;
- invent consensus;
- infer probabilities without explicit source data;
- create Bull/Base/Bear prices from arbitrary percentage multipliers;
- convert unavailable fundamentals into synthetic values;
- output a buy/sell recommendation;
- silently select a valuation reference without reporting it.

## 4. Reference multiple

Priority:

1. User-supplied reference_multiple.
2. Historical P/E median supplied by the data source.
3. No reference.

If no reference is available, observed valuation can still be reported, but reverse-engineered EPS and growth remain null.

### 4.1 Historical band quality gate

A historical valuation band may act as a reference only when it reports at least
`MIN_BAND_OBSERVATIONS_FOR_REFERENCE` (20) observations.

A band below the threshold must not silently become the reference multiple and
must not produce a percentile reading. The engine reports it as
`DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS` in `reference.historical_band_status`
and leaves the dependent reverse-valuation outputs null.

Precision is not evidence. A percentile distribution computed from too few
observations is not a defensible reference, regardless of how many decimal places
the median carries.

A band that declares no `observations` field is treated as usable. This preserves
static regression fixtures and explicitly supplied reference bands.

## 5. Formulas

Current P/E:
P0 / current_eps

Forward P/E:
P0 / forward_eps

Consensus forward P/E:
P0 / consensus_forward_eps

Implied forward EPS:
P0 / reference_multiple

EPS gap versus consensus:
implied_forward_eps / consensus_forward_eps - 1

Required EPS CAGR:
(implied_forward_eps / current_eps) ^ (1 / horizon_years) - 1

Consensus price at historical median:
consensus_forward_eps * historical_pe_median

Price gap versus that reference:
consensus_median_price / P0 - 1

## 6. Multi-method valuation

The deterministic engine consumes fundamentals through a provider abstraction. The Yahoo implementation may supply trailing EPS, forward EPS, forward-year consensus EPS, and an observed historical trailing P/E distribution. Each field is source-derived and timestamped where Yahoo exposes the information.

Consensus EPS must come from an explicit estimate source. Forward EPS must never be reused as consensus merely to fill a missing field. Historical P/E statistics must be calculated only from retrieved observations.

Provider failures or unavailable fields do not trigger fallback estimates. They remain unavailable.

## 7. Missing-data policy

Missing inputs are represented as UNAVAILABLE at the raw-data layer and null in numeric derived output.

No fallback guess is allowed.

A provider failure must degrade to UNAVAILABLE, never to an exception that aborts
acquisition. Partially acquired data remains usable; the failure is recorded.

## 8. Evidence policy

Every material source input receives an Evidence ID.

Invalid evidence references are validation errors.

Evidence unit must describe the value actually carried. Valuation bands are
multiples (`unit = "multiple"`), not currency amounts.

## 9. Data quality reporting

Every run reports a `data_quality` block containing `discrepancy_status`,
`acquisition_errors`, and `consensus_forward_eps_period`.

`discrepancy_status` is an evidence state, not an investment rating. A live
acquisition from a single provider is `UNVERIFIABLE`: one source cannot
cross-validate itself, and the engine must not present its output as verified.

Provider errors must be propagated to the caller. Collecting errors internally and
discarding them is a defect.

## 10. Snapshot policy

Analysis snapshots are append-only at the application level.

Outcome records are separate files and never modify the original analysis snapshot.

Artifacts produced by the pre-2.2 framework are retained under `history/legacy-v6/`
and must not be presented as current engine output.

## 11. Future extensions

Possible later modules:

- multi-provider consensus acquisition;
- event-window outcome calibration;
- optional LLM interpretation layer.

These must remain separate from the deterministic calculation core.
