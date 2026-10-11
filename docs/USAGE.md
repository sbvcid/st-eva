# ST-EVA Usage

ST-EVA starts with a market price and an explicit valuation reference, then reports the financial assumptions implied under that condition. Observed data, deterministic calculations, and conditional inferences are kept distinct.

## Setup

Python 3.9 or newer is required.

```powershell
python -m pip install -r requirements.txt
```

Live acquisition requires network access. Missing values and source availability gaps are reported rather than filled with guesses.

## Basic commands

Run live acquisition:

```powershell
python st_eva_runner.py AAPL --mode live --no-snapshot
```

Use an explicit P/E reference to produce the corresponding reverse requirements:

```powershell
python st_eva_runner.py AAPL --mode live --reference-multiple 30 --no-snapshot
```

Use a fixture for a deterministic regression run:

```powershell
python st_eva_runner.py MSFT --mode regression --no-snapshot
```

Output JSON instead of the readable report:

```powershell
python st_eva_runner.py AAPL --mode live --reference-multiple 30 --json --no-snapshot
```

Modes are `auto`, `live`, and `regression`. In `auto` mode, a supported fixture is used when available; otherwise the ticker falls through to live acquisition.

## Valuation inputs

The default P/E reference selection is a user-supplied multiple, then a usable historical P/E median, then no reference. A historical band must meet the minimum-observation quality gate before it can be used as a reference; a thinner band may still be shown as descriptive evidence.

Common options:

| Option | Purpose |
|---|---|
| `--reference-multiple N` | Set one explicit P/E reference |
| `--reference-multiples N...` | Evaluate multiple P/E assumptions |
| `--pfcf-multiple N` | Set a P/FCF reference |
| `--ev-ebitda-multiple N` | Set an EV/EBITDA reference |
| `--ps-multiple N` | Set a P/S reference |
| `--horizon-years N` | Set the span for the required EPS CAGR calculation |
| `--reverse-horizons N...` | Set holding periods for the reverse-requirements matrix |
| `--required-returns N...` | Set required-return assumptions as decimals |
| `--risk-free-rates` | Acquire observed US Treasury yields |
| `--beta N`, `--equity-risk-premium N` | Supply assumptions for the CAPM feasibility calculation |
| `--no-dcf` | Skip the DCF feasibility check |

All user-supplied multiples, horizons, and rates are assumptions, not observed facts. The output records the reference used for each conditional calculation.

## Research outputs

### Research Dossier

Create a structured research report from the same analysis result:

```powershell
python st_eva_runner.py AAPL --mode live --dossier dossier.json --no-snapshot
```

Use `--dossier` without a path to write the dossier to standard output, or `--dossier-report` to render a readable version alongside the regular report.

### Investment Context

Create a traceable, machine-readable document:

```powershell
python st_eva_runner.py AAPL --mode live --context context.json --no-snapshot
```

The context records figure references, source observations, validation states, and registered operations so a consumer can inspect how the values were derived. Use `--context -` to write it to standard output.

By default, the context requests both Yahoo and SEC evidence. Use `--context-sources yahoo` or `--context-sources sec` to select sources.

### Financial history and historical P/E

```powershell
python st_eva_runner.py AAPL --mode live --financial-history --no-snapshot
python st_eva_runner.py MSFT --mode live --historical-pe --no-snapshot
```

Financial-history and historical-P/E paths may access external sources. Historical P/E is available only for issuers with configured and qualifying evidence.

### Archive and point-in-time replay

Archive persistence is opt-in and requires an Investment Context:

```powershell
python st_eva_runner.py AAPL --mode live --context context.json --archive data/st-eva.sqlite
```

The archive records source documents where captured, observations, the context, and supported admission/validation records. Replay distinguishes a matching reconstruction from a divergence, a missing snapshot, or insufficient historical evidence. An insufficient replay is reported as such; it must not silently replace historical inputs with current values.

Some sources do not declare when a value became publicly available. Those observations are labelled accordingly, and a replay using archive-first-seen observations cannot claim source-declared point-in-time fidelity.

## Reading the result

The report distinguishes:

- **Observed:** values obtained from a source, with provenance where available.
- **Derived:** deterministic calculations from identified inputs.
- **Conditional inference:** quantities implied only under an explicitly stated reference or assumption.
- **Unavailable:** a required input that could not be established.

A missing value is not automatically a failed run. Read the associated status, reason, time period, units and provenance before using it.

Cross-source validation produces a separate comparison result. It does not average source values, silently choose a winner, or overwrite either observation. A period mismatch or methodology mismatch means the figures cannot be treated as directly comparable, even if the numeric values happen to match.

## Snapshots

Unless `--no-snapshot` is supplied, a regular run writes a result snapshot under `history/`. Use `--no-snapshot` for exploratory runs that should not create a persistent result file.

## Development checks

Install the test dependencies and run the current test suite with:

```powershell
python -m pip install -r requirements-test.txt
python -m pytest tests/ -q
```

`python st_eva_runner.py --test` runs the small built-in regression checks; it is not a replacement for the repository test suite.

## Current implementation boundary

Archived SEC evidence entering the reverse-valuation input surface is currently admitted only for `revenue`. Other archived metrics can be recorded and evaluated by the evidence layer, but are refused at this specific crossing. This does not mean that all other metrics are absent from the separate live valuation path or from Historical P/E processing.

`llm_interpreter.py` builds a prompt/request for external interpretation; it does not call a live LLM provider. The deterministic calculation remains in ST-EVA, and model interpretation is not a source of financial facts.