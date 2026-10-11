# ST-EVA

ST-EVA is a financial research engine built around traceable, time-indexed evidence and deterministic calculations.

Its central question is: **Given an observed market price and an explicitly stated valuation reference, what financial performance does that price require?**

ST-EVA describes conditional assumptions implied by a price. It does not predict fair value, generate price targets, assign probabilities, or make buy/sell recommendations.

## Research workflow

```
Research inputs and as-of date
        ↓
Market data and financial-source acquisition
        ↓
Observation / Evidence / Validation with provenance and time semantics
        ↓
Source comparison and evidence admission
        ↓
Deterministic valuation and reverse requirements
        ↓
Research Dossier and/or Investment Context
        ↓
Optional archive persistence and point-in-time replay
```

Each step must preserve the distinction between observed facts, deterministic derivations, and conditional inferences. Missing or unverified inputs remain explicit; retrieval time is not treated as publication time.

## Main capabilities

- Observed market and financial metrics with source, period, currency, and availability metadata where the source provides them.
- Cross-source comparison that reports consistency, discrepancies, and methodological or period mismatches without silently merging competing values.
- Reverse valuation using explicit P/E, P/FCF, EV/EBITDA, and P/S references, with required growth and other conditional financial requirements where inputs permit.
- Historical valuation distributions that are not used as a reference unless the observation-count quality gate is met.
- Research Dossier for people and Investment Context for machine-readable, provenance-carrying analysis.
- Optional SQLite archive for source capture, observations, contexts, evidence-admission records, and point-in-time replay.
- Historical P/E reconstruction from qualifying time-indexed evidence for supported issuers.

## Important boundaries

- A price and a multiple do not uniquely determine a future outcome. Every reverse calculation is conditional on its stated reference and inputs.
- No EPS, consensus estimate, publication timestamp, or other financial input is invented to fill a gap.
- Cross-source comparison does not itself select a winning source or overwrite either observation.
- Archive replay reports when available evidence is insufficient; it does not substitute current data and present the result as historical truth.
- Archived SEC evidence admitted directly into the reverse-valuation input surface is currently limited to the `revenue` metric. This is an implementation boundary, not a statement that other metrics are unavailable to every separate research path.
- `llm_interpreter.py` currently builds an interpretation prompt/request; it does not call a live model provider. LLM interpretation remains separate from sourced facts and deterministic arithmetic.

## Quick start

Core runtime dependency setup:

```powershell
python -m pip install -r requirements.txt
```

Run live research with an explicit P/E reference, without writing a snapshot:

```powershell
python st_eva_runner.py AAPL --mode live --reference-multiple 30 --no-snapshot
```

Print machine-readable JSON:

```powershell
python st_eva_runner.py AAPL --mode live --reference-multiple 30 --json --no-snapshot
```

Create a Research Dossier:

```powershell
python st_eva_runner.py AAPL --mode live --dossier dossier.json
```

Create an Investment Context and persist the run for replay:

```powershell
python st_eva_runner.py AAPL --mode live --context context.json --archive data/st-eva.sqlite
```

The CLI accepts `auto`, `live`, and `regression` modes. Live acquisition requires network access; a source may leave values unavailable.

## Project components

| Component | Responsibility |
|---|---|
| `st_eva_runner.py` | Acquisition orchestration, deterministic analysis, validation, snapshots, and optional output integration |
| `data_contract.py` and evidence modules | Observation, evidence identity, provenance, availability, and validation semantics |
| `fundamental_provider.py`, `sec_provider.py` | Market/fundamental and SEC source acquisition |
| `cross_validation.py` | Cross-source comparability and result classification |
| `evidence_valuation_boundary.py` | Admission decisions for archived evidence entering valuation inputs |
| `historical_pe.py`, `reverse_requirements.py` | Historical P/E reconstruction and conditional reverse calculations |
| `research_dossier.py`, `investment_context.py` | Human-readable and machine-readable research packages |
| `archive.py`, `sqlite_archive.py`, `archive/migrations/` | Persistence, source capture, and point-in-time replay |
| `web/` | Existing browser interface and HTTP API |

For command options and output semantics, see [docs/USAGE.md](docs/USAGE.md).