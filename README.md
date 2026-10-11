# ST-EVA — Reverse Valuation

ST-EVA is a reverse-valuation tool. Given a company's observed market price and explicit valuation assumptions, it calculates the financial performance implied by those assumptions. **Reverse valuation is the product itself**, not a side feature of a general research platform.

The central question is:

> At this price, what would the company have to deliver under a stated holding period, required return, and exit valuation multiple?

ST-EVA produces conditional numbers that a person or an external tool may analyse. It does not decide whether the assumptions are reasonable.

## Intended user workflow

1. Enter a company ticker in the web interface.
2. Retrieve the available market price and financial inputs, with their dates, periods, units, currencies, sources, and availability limits.
3. Inspect the observed valuation and set or inspect the reference/exit multiples, holding periods, and required-return assumptions used in the calculation.
4. View a reverse-requirements matrix. Each scenario should show the required terminal price, the fundamental level implied by its exit multiple, and the growth required from an explicitly identified starting figure when that growth is computable.
5. Open a scenario's inputs, formulas, source records, and calculation details so the result can be independently checked and recomputed.

The matrix is conditional arithmetic, not a forecast. A different horizon, required return, EPS anchor, or exit multiple can produce a different result. The interface must make those assumptions visible rather than hide them in defaults.

## Data and calculation rules

- **Observed facts, source claims, derived values, and conditional results are distinct.** Recording a source accurately does not guarantee that the source itself is true.
- Every material input and output must retain its relevant source or derivation, as-of date, fiscal/coverage period, unit, currency, and other basis information supplied or required by the calculation.
- A calculation must use compatible periods, units, currencies, and EPS anchors. Trailing, next-twelve-month, and fiscal-year EPS must not be silently treated as interchangeable.
- Each reverse scenario must identify its assumptions and formula version. A return without an explicit dividend treatment is a price-return condition, not a total-return claim.
- Missing, unavailable, conflicting, stale, or incompatible inputs must be labelled as such. They must not be silently replaced with invented values or treated as zero.
- A historical multiple distribution may be shown descriptively without automatically being eligible as a scenario reference. Reference eligibility must follow an explicit quality rule.

## What ST-EVA does not do

ST-EVA does not forecast business results, determine fair value, generate price targets, judge whether a price is cheap or expensive, assign probabilities, assess business quality, or make investment recommendations. It does not need to call or embed an LLM. Any later interpretation by a person or external LLM is outside the calculation engine and must not be written back as an observed fact.

## Current implementation status

The CLI already contains deterministic reverse-requirement calculations and options for evaluating multiple assumptions. **The browser experience is not yet the complete product described above.** The current interface presents a reduced summary, observed multiples, evidence identifiers, and replay/admission information; it does not yet expose the full configurable reverse-requirements matrix or per-scenario formula/source trace. The web request currently does not send the reference-multiple or horizon fields, and the frontend hard-codes regression mode for `MSFT` and `0700.HK`. These are implementation gaps, not completed features.

A complete first release must pass an end-to-end AAPL case in the real web path before broader issuer coverage is treated as evidence of completion. Regression fixtures must always be visibly distinguished from live observations.

## First-release acceptance

- A user can enter a ticker and see the observed price/as-of date, the valuation reference used, and the actual assumptions applied.
- The web UI lets the user inspect or set the scenario dimensions and displays the complete reverse-requirements matrix for the available inputs.
- Every matrix row can be traced to its inputs, source/period metadata, formula and version; an independent recomputation from the same inputs produces the same result.
- EPS basis and growth window, currency/unit compatibility, price-return versus total-return basis, and reference eligibility are explicit.
- Missing or conflicting data remain visible with reasons; no regression fixture is presented as live data.
- The AAPL web path is verified first, including calculations, traceability, missing-data behaviour, and regression coverage. Additional issuers and calculation methods follow only after this path passes.

## Run the current CLI

Install the Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

Run live analysis with an explicit P/E reference, without writing a result snapshot:

```powershell
python st_eva_runner.py AAPL --mode live --reference-multiple 30 --no-snapshot
```

Print machine-readable JSON:

```powershell
python st_eva_runner.py AAPL --mode live --reference-multiple 30 --json --no-snapshot
```

The CLI supports `auto`, `live`, and `regression` modes. Live data requires network access and may be unavailable for some fields. Regression mode uses fixtures and is not live market data.

For CLI options and output semantics, see [docs/USAGE.md](docs/USAGE.md). The root README defines the product and its acceptance conditions; implementation notes and historical records do not override that definition.
