# ST-EVA 2.1 — Market-Implied Assumptions Engine

ST-EVA answers one question:

「目前價格反映了什麼假設？」

It starts from the observed market price and reverse-engineers the earnings assumptions required to justify that price under an explicitly selected valuation reference.

## Core calculation

For current price P0 and reference P/E multiple M:

Implied Forward EPS = P0 / M

If current EPS is available:

Required EPS CAGR = (Implied Forward EPS / Current EPS) ^ (1 / T) - 1

If consensus forward EPS is available:

EPS Gap = Implied Forward EPS / Consensus Forward EPS - 1

The word "implied" is conditional. Price alone cannot identify one unique future EPS or growth path.

## What the engine reports

- Current price and provenance.
- Current P/E when current EPS is available.
- Forward P/E when forward EPS is available.
- Consensus forward P/E when consensus EPS is available.
- Historical P/E band.
- Approximate position inside the historical P/E band.
- Forward EPS implied by the selected valuation multiple.
- EPS gap between implied EPS and consensus EPS.
- EPS CAGR required from current EPS.
- Price implied by consensus EPS at the historical median P/E.
- Price and volume statistics.
- Missing data.
- Evidence IDs.
- An immutable-at-application-level research snapshot.

## What it does not do

ST-EVA does not:

- invent EPS;
- invent consensus estimates;
- invent probability weights;
- invent Bull/Base/Bear target prices;
- use arbitrary price multipliers when fundamentals are unavailable;
- output a buy/sell stance;
- claim that one P/E multiple is objectively what the market assumes;
- ask an LLM to perform valuation arithmetic.

An LLM can later interpret the structured result, but the calculation core is deterministic Python.

## Data categories

OBSERVED:
Data supplied by a market-data provider or explicit test fixture.

DERIVED:
Deterministic calculations from observed inputs.

CONDITIONAL_INFERENCE:
Reverse-engineered assumptions that depend on an explicit valuation reference.

UNAVAILABLE:
A required input that has not been sourced. It is never guessed.

## Valuation reference

Priority:

1. User-supplied reference multiple.
2. Historical P/E median.
3. No reference.

Example:

python st_eva_runner.py AAPL --mode live --reference-multiple 30

If neither a supplied reference multiple nor a historical median is available, ST-EVA still reports observed valuation data but does not fabricate implied EPS.

## Usage

Run regression tests:

python st_eva_runner.py --test

Run static fixtures:

python st_eva_runner.py MSFT --mode regression
python st_eva_runner.py TENCENT --mode regression
python st_eva_runner.py NU --mode regression

Run live Yahoo Finance acquisition:

python st_eva_runner.py AAPL --mode live --no-snapshot

Save a research snapshot:

python st_eva_runner.py AAPL --mode live --reference-multiple 30

Snapshots are written to history/.

## Fundamental data provider

Live mode now uses a separate `YahooFundamentalProvider` for source financial data. It attempts to acquire trailing EPS, forward EPS, forward-year consensus EPS from Yahoo earnings estimates, and an observed historical trailing P/E distribution from Yahoo fundamentals time series. Missing fields remain unavailable.

The provider does not synthesize consensus from forward EPS and does not invent historical valuation ranges. Historical P/E 10th/median/90th values are descriptive statistics calculated only from retrieved observations.

## Architecture

Observed Market Data
        |
        +--> Yahoo Fundamental Provider
        |         |
        |         +--> EPS / consensus / P-E observations
        |
        v
Evidence Store
        |
        v
Deterministic Metrics
        |
        v
Reverse Valuation Engine
        |
        +--> Historical P/E reference
        |
        +--> Consensus EPS cross-check
        |
        +--> Required EPS / CAGR
        |
        v
Validator
        |
        v
Machine-readable JSON
        |
        v
Immutable-at-application-level Snapshot

## Testing

The regression fixtures are static test data. They are not live prices.

The test suite checks:

- reverse-valuation arithmetic;
- evidence integrity;
- zero synthetic financial data;
- missing-data behavior;
- unknown-ticker handling.

Future extensions can add EV/EBITDA, FCF yield, revenue/margin reverse engineering, more providers, and an optional LLM interpretation layer without changing the deterministic core.

## Scope

ST-EVA is an analytical component. It describes assumptions embedded in a price; it does not make the investment decision.
