# ST-EVA CLI Usage

This guide documents the current command-line interface. ST-EVA's product goal and first-release acceptance conditions are defined in the root [README](../README.md). The browser UI is not yet equivalent to the CLI's reverse-requirements capabilities; see [Current Project Status](PROJECT-STATUS.md).

## Setup

Python 3.9 or newer is required.

```powershell
python -m pip install -r requirements.txt
```

Live acquisition requires network access. An individual field may remain unavailable even when a run succeeds.

## Basic runs

Live data, no persistent result snapshot:

```powershell
python st_eva_runner.py AAPL --mode live --no-snapshot
```

Supply a P/E reference and calculate the corresponding reverse requirements:

```powershell
python st_eva_runner.py AAPL --mode live --reference-multiple 30 --no-snapshot
```

Emit JSON:

```powershell
python st_eva_runner.py AAPL --mode live --reference-multiple 30 --json --no-snapshot
```

Run a deterministic fixture for regression checks:

```powershell
python st_eva_runner.py MSFT --mode regression --no-snapshot
```

Modes are `auto`, `live`, and `regression`. A regression run uses static fixture data and must never be interpreted as a live quote or current financial observation. In `auto` mode, a supported fixture may be selected; otherwise the ticker falls through to live acquisition. Prefer `--mode live` when checking the actual acquisition path.

## Reverse-valuation assumptions

Common options:

| Option | Purpose |
|---|---|
| `--reference-multiple N` | Supply one explicit P/E reference |
| `--reference-multiples N...` | Evaluate multiple P/E reference/exit-multiple assumptions |
| `--pfcf-multiple N` | Supply a P/FCF reference |
| `--ev-ebitda-multiple N` | Supply an EV/EBITDA reference |
| `--ps-multiple N` | Supply a P/S reference |
| `--reverse-horizons N...` | Set holding periods for the reverse-requirements matrix |
| `--required-returns N...` | Set required-return assumptions as decimals, such as `0.08 0.10` |
| `--horizon-years N` | Set the horizon used by the summary engine's EPS-CAGR calculation |
| `--risk-free-rates` | Acquire observed US Treasury yields |
| `--beta N`, `--equity-risk-premium N` | Supply inputs to the CAPM/cost-of-equity calculation |
| `--no-dcf` | Skip the DCF feasibility calculation |

The summary engine's `required_eps_cagr` and a row in the full reverse-requirements matrix are not interchangeable merely because both contain a CAGR. When comparing outputs, inspect the selected EPS anchor, horizon, required-return basis, exit multiple, and formula metadata for the specific calculation.

All user-supplied multiples, horizons, and rates are assumptions, not observed facts. A reference multiple is a conditional input, not proof that the market expects the resulting earnings figure. A return hurdle without an explicit dividend treatment is a price-return condition, not a total-return condition.

A historical valuation band may be shown as descriptive evidence even when it fails the minimum-observation gate for use as a scenario reference. Descriptive availability and reference eligibility are separate questions.

## Optional output and history tools

These are supporting interfaces for inspection or reproducibility; they do not replace the reverse-valuation result.

Create a Research Dossier:

```powershell
python st_eva_runner.py AAPL --mode live --dossier dossier.json --no-snapshot
```

Create a machine-readable Investment Context:

```powershell
python st_eva_runner.py AAPL --mode live --context context.json --no-snapshot
```

The context can include figure references, source observations, validation states, and registered operations. Use `--context -` to write it to standard output. By default it requests Yahoo and SEC evidence; `--context-sources yahoo` or `--context-sources sec` selects a source.

Issuer-specific historical data paths:

```powershell
python st_eva_runner.py AAPL --mode live --financial-history --no-snapshot
python st_eva_runner.py MSFT --mode live --historical-pe --no-snapshot
```

These paths require their configured and qualifying evidence. Their existence does not imply that all metrics or issuers are covered by the same source path.

## Archive and replay

Archive persistence is opt-in and requires an Investment Context:

```powershell
python st_eva_runner.py AAPL --mode live --context context.json --archive data/st-eva.sqlite
```

The archive can preserve captured source documents, observations, contexts, and supported admission/validation records. Replay distinguishes a matching reconstruction from divergence, a missing snapshot, or insufficient historical evidence. It must not silently substitute current inputs for unavailable historical facts.

**Treat existing SQLite files as persistent data. Do not delete or reset `data/st-eva.sqlite`, files under `data/archives/`, or another configured runtime archive as a cleanup step.** Use an isolated temporary path for tests and experiments that must not affect existing records.

Some sources do not declare when a value became publicly available. Those observations are labelled accordingly; replay based on archive-first-seen time must not be described as source-declared point-in-time fidelity.

## Interpreting output

- **Observed:** a source-reported value, with source and timing metadata where available.
- **Derived:** deterministic arithmetic from identified inputs.
- **Conditional result:** a value implied only under named assumptions.
- **Unavailable or refused:** an input or derivation that could not be established under the applicable rules.

A missing value is not automatically a failed run. Inspect the reason, period, unit, currency, and provenance. Cross-source validation reports comparability and discrepancies; it does not average competing observations, silently select a winner, or overwrite either source's value.

## Known implementation boundaries

- Archived SEC evidence entering the reverse-valuation input surface is currently admitted only for `revenue`. This boundary does not mean other metrics are absent from every separate live or historical-data path.
- `llm_interpreter.py` builds a prompt/request but does not call a live LLM provider. An LLM is not required for ST-EVA's deterministic calculations.

## Tests

```powershell
python -m pip install -r requirements-test.txt
python -m pytest tests/ -q
```

`python st_eva_runner.py --test` runs the small built-in checks; it is not a replacement for the repository test suite.
