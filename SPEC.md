# ST-EVA 2.0 Specification

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
- historical P/E band;
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

## 6. Missing-data policy

Missing inputs are represented as UNAVAILABLE at the raw-data layer and null in numeric derived output.

No fallback guess is allowed.

## 7. Evidence policy

Every material source input receives an Evidence ID.

Invalid evidence references are validation errors.

## 8. Snapshot policy

Analysis snapshots are append-only at the application level.

Outcome records are separate files and never modify the original analysis snapshot.

## 9. Future extensions

Possible later modules:

- EV/EBITDA reverse engineering;
- FCF yield reverse engineering;
- revenue × margin reverse engineering;
- multi-provider consensus acquisition;
- event-window outcome calibration;
- optional LLM interpretation layer.

These must remain separate from the deterministic calculation core.
