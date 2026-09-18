# ST-EVA 2.2 Specification

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

## 8. Missing-data policy

Missing inputs are represented as UNAVAILABLE at the raw-data layer and null in numeric derived output.

No fallback guess is allowed.

## 9. Evidence policy

Every material source input receives an Evidence ID.

Invalid evidence references are validation errors.

## 10. Snapshot policy

Analysis snapshots are append-only at the application level.

Outcome records are separate files and never modify the original analysis snapshot.

## 11. Future extensions

Possible later modules:

- multi-provider consensus acquisition;
- event-window outcome calibration;
- optional LLM interpretation layer.

These must remain separate from the deterministic calculation core.
