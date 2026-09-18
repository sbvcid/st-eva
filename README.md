# Short-Term Event-Driven Valuation Framework (ST-EVA v6.1)

ST-EVA v6.1 is an independent **Short-Term Event-Driven Investment Research Engine** designed for 1–8 week horizons. It is structured to serve as a rigorous research tool that can be invoked programmatically by future Investment Agents.

---

## What ST-EVA Solves
- **Expectation Gaps**: Quantifies what the market is pricing in versus consensus and fundamentals over short event windows (e.g., earnings, product launches, macroeconomic catalysts).
- **Deterministic Valuation**: Eliminates LLM math hallucination by enforcing Python-driven calculation of Expected Value (EV), Scenario Target Prices, Upside/Downside, and Payoff Ratios.
- **Evidence Traceability**: Enforces strict provenance through a Unified Evidence Store where every claim and metric maps to verifiable Evidence IDs.
- **Anti-Hallucination & Stress Validation**: Validates all model hypotheses, scenario probability limits, data discrepancies across multi-source providers, and evidence-to-claim consistency.

## What ST-EVA Does Not Solve
- Long-term DCF, DDM, or LBO modeling.
- Portfolio optimization or automated trade execution.
- Multi-agent debate or subjective asset allocation.

---

## Architecture Pipeline

```text
Market Data Providers (Yahoo Finance, Alpha Vantage, FMP)
                   ↓
         Multi-Source Aggregator
                   ↓
         Unified Evidence Store
                   ↓
       Deterministic Metrics Engine
                   ↓
            ResearchInput
                   ↓
      Single LLM Research Engine (Structured JSON)
                   ↓
       Dynamic Scenario Engine
                   ↓
        Python Valuation Arithmetic
                   ↓
              Validator 3.0
                   ↓
    ┌──────────────┴──────────────┐
    ↓                             ↓
Structured JSON           Human-Readable Markdown
(Machine-Readable API)    (Analyst Report)
    ↓
Immutable Research Snapshot (`history/`)
```

---

## Core Principles
1. **Separation of Concerns**: LLM is strictly responsible for *interpretation, hypotheses, and qualitative reasoning*. Python is responsible for *math, deterministic calculations, and schema validation*.
2. **Evidence as Hard Constraint**: All claims must reference valid Evidence IDs. Non-existent IDs trigger immediate rejection.
3. **Multi-Source Data Provenance**: Data is acquired across providers with deterministic discrepancy checks (e.g., >1% price variance flagged as `DATA_DISCREPANCY`).
4. **Immutable Historical Snapshots**: Every run generates a version-controlled canonical JSON record in `history/` containing outcome tracking stubs for future calibration and backtesting.

---

## Public Tool Interface (`run_st_eva`)

```python
from st_eva_runner import run_st_eva

result = run_st_eva(
    ticker="AAPL",
    horizon="1-8 weeks",
    event="Q3 2026 Earnings"
)
```

### Output JSON Schema
```json
{
  "ticker": "AAPL",
  "company_name": "AAPL (Live Acquired)",
  "research_id": "RES-455776B8",
  "as_of": "2026-09-18",
  "horizon": "1-8 weeks",
  "price": 337.0,
  "currency": "USD",
  "event": {
    "date": "UNAVAILABLE",
    "status": "Unconfirmed"
  },
  "market_expectation": { ... },
  "scenarios": { ... },
  "expected_value": 346.60,
  "expected_return_pct": 2.85,
  "upside": 50.55,
  "downside": 33.70,
  "payoff": 1.50,
  "risks": [ ... ],
  "triggers": [ ... ],
  "kill_switches": [ ... ],
  "evidence": [ ... ],
  "validation": { "status": "PASSED", "validator_version": "v3-adversarial" },
  "version_metadata": { ... }
}
```

---

## Test Commands

Run the full ST-EVA test suite:
```powershell
python st_eva_runner.py
```
