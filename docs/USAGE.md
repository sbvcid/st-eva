# ST-EVA Usage Guide

ST-EVA answers one question: 「目前價格反映了什麼假設？」

It reverse-engineers the earnings assumptions required to justify an observed
price under an explicitly selected valuation reference. It does not forecast,
does not produce target prices, and does not issue buy/sell signals.

## Requirements

Python 3.9 or newer. No third-party packages. No API keys.

## The central idea

Most tools ask "what will this stock be worth". ST-EVA asks the inverse:

> Given this price, what must be true for the price to make sense?

The whole engine is one division:

$$\text{Implied forward EPS} = \frac{P_0}{M}$$

where $P_0$ is the observed price and $M$ is the valuation multiple you have
explicitly chosen.

Everything else — EPS gap, required CAGR, implied FCF/EBITDA/revenue, implied
net margin — is built on top of that single reference.

## Modes

| Mode | Command | Behaviour |
|---|---|---|
| `live` | `python st_eva_runner.py AAPL --mode live` | Acquire from Yahoo Finance |
| `regression` | `python st_eva_runner.py MSFT --mode regression` | Use a static fixture, no network |
| `auto` (default) | `python st_eva_runner.py AAPL` | Fixture when one exists, otherwise live |

`regression` only recognises these keys: `TENCENT`, `0700.HK`, `騰訊`, `MSFT`,
`MICROSOFT`, `NU`, `NU HOLDINGS`. Anything else falls through to live.

## Workflow

### Step 1 — check whether a historical reference is usable

```powershell
python st_eva_runner.py 0700.HK --mode live --no-snapshot
```

Read `reference.historical_band_status.pe`:

- `USABLE_FOR_REFERENCE` — enough observations, the historical median will be
  adopted automatically.
- `DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS` — the band exists but is too
  thin. Implied figures will be `null`.
- `UNAVAILABLE` — no band at all.

A real live run for AAPL currently reports only 8 P/E observations, so the
historical median is refused. This is deliberate: eight points cannot support a
10/25/50/75/90 percentile reading, and a median that looks precise is not the
same as evidence.

### Step 2 — supply your own reference multiple

```powershell
python st_eva_runner.py 0700.HK --mode live --reference-multiple 20 --no-snapshot
```

An explicit multiple always wins over a historical band, thin or not.

### Step 3 — verify, then save

Only write a snapshot once the numbers look defensible:

```powershell
python st_eva_runner.py 0700.HK --mode live --reference-multiple 20
```

## Reading the output

Example using the TENCENT regression fixture:

```powershell
python st_eva_runner.py TENCENT --mode regression --no-snapshot
```

```
price       432.2 HKD | 0700.HK
forward PE  13.72
PE band     {10th: 12.0, 25th: 15.0, median: 18.5, 75th: 23.0, 90th: 28.0}
PE pctile   50.0

ref method  historical_pe_median | multiple 18.5
implied EPS 23.36
eps gap     -0.2583
```

Interpretation:

1. The stock trades at 13.72x forward earnings.
2. The historical median is 18.5x, so the current multiple sits at the 50th
   percentile — neither expensive nor cheap.
3. At 18.5x, the price implies forward EPS of 23.36.
4. Consensus forward EPS is 31.50, so the price-implied figure sits 25.8% below
   consensus.

The conditional statement that matters: **23.36 is what the price requires if
the market is paying 18.5x.** It is not a forecast, and it is not "the market
expects 23.36".

## Key output fields

```jsonc
{
  "market_snapshot":        { "price": 341.07, "currency": "USD", ... },
  "data_quality":           { "discrepancy_status": "UNVERIFIABLE", ... },
  "observed_valuation":     { "current_pe": 39.07, "historical_pe_band": {...}, ... },
  "market_implied_assumptions": {
    "forward_eps_at_reference_multiple": 11.37,
    "eps_gap_vs_consensus": 0.187,
    "required_eps_cagr_from_current_eps": null,
    "reference_multiples": { "pe": 30.0, "pfcf": 25.0, ... }
  },
  "consensus_cross_check":  { "consensus_forward_eps": 30.15, ... },
  "reference":              { "method": "user_supplied_multiple", "multiple": 30.0, ... },
  "missing_data":           [ "current_fcf" ],
  "evidence_ids":           [ "ev-price-001", ... ]
}
```

`missing_data` is a first-class output. A long list there means the run is thin,
not that the engine failed.

## Multi-method reverse valuation

```powershell
python st_eva_runner.py AAPL --mode live `
  --reference-multiple 30 `
  --pfcf-multiple 25 `
  --ev-ebitda-multiple 20 `
  --ps-multiple 8
```

```
  P/E        current=39.07    implied=11.37
  P/FCF      current=35.98    implied=196741221744.0
  EV/EBITDA  current=29.41    implied=247023777180.0
  P/S        current=10.54    implied=614816317950.0
  eps gap    0.187
  implied margin 0.2667
```

Each method expresses the same price in a different unit. Comparing them is how
you detect a price that is only defensible under one lens.

The implied net margin is worth attention: it combines the P/S-implied revenue
with the P/E-implied EPS to answer "what profitability must this company earn
for the current price to hold?" For AAPL at 30x, that is 26.7%.

P/FCF, EV/EBITDA and P/S implied figures are absolute currency amounts and will
be large. Compare them across methods or against history; do not read the
absolute magnitude.

## Other options

```powershell
# Years over which required EPS growth is compounded
python st_eva_runner.py AAPL --reference-multiple 30 --horizon-years 3

# Record an event date (metadata only, does not affect calculation)
python st_eva_runner.py AAPL --event "Q3 earnings"

# Suppress snapshot writing
python st_eva_runner.py AAPL --no-snapshot
```

## Snapshots and outcome tracking

Without `--no-snapshot`, a run writes:

```
history/<TICKER>_RES-<ID>_market_implied_assumptions.json
```

The snapshot is append-only. Outcomes are recorded in separate files and never
modify the original analysis.

```python
from st_eva_runner import SnapshotManager

SnapshotManager('history').update_outcome(
    'RES-5F74EBF112',
    {'t_plus_1_return': 0.0079, 'event_result': None},
)
```

This creates `history/AAPL_RES-5F74EBF112_outcome_<timestamp>.json` alongside
the untouched snapshot.

## Using it as a library

`run_st_eva()` is the same entry point the CLI uses:

```python
from st_eva_runner import run_st_eva

result = run_st_eva(
    'AAPL',
    mode='live',
    reference_multiple=30.0,
    save_snapshot=False,
)

print(result['market_implied_assumptions']['forward_eps_at_reference_multiple'])
```

## LLM interpretation

The adapter in `llm_interpreter.py` converts a validated snapshot into a strict
interpretation prompt. Its system prompt forbids the model from calculating,
modifying, or inventing any financial figure, and from issuing a verdict.

```python
from llm_interpreter import (
    build_interpretation_prompt,
    build_interpretation_request,
)

prompt = build_interpretation_prompt(result)
request = build_interpretation_request(result)
```

Send `prompt` to whichever model client you already use. The calculation core
stays deterministic Python; only the prose is delegated.

## Tests

```powershell
python st_eva_runner.py --test              # 6 built-in regression checks
python -m unittest discover -s tests        # 19 unit tests
```

## Windows console encoding

Console output containing Chinese may be mangled on a default Windows terminal.
Set the encoding first:

```powershell
$env:PYTHONIOENCODING="utf-8"
python -X utf8 st_eva_runner.py TENCENT --mode regression
```

This is a terminal issue, not an engine issue.

## What this tool will not do

- invent EPS, consensus estimates, or probabilities;
- produce Bull/Base/Bear target prices;
- issue a buy/sell recommendation;
- pick a valuation reference without reporting which one it used;
- fabricate fundamentals when data is missing;
- ask an LLM to perform valuation arithmetic.

If a required input is missing, the answer is `UNAVAILABLE` or `null`. It stays
that way rather than becoming a guess.
