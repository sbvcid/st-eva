# ST-EVA 2.3 — Multi-Source Evidence & Cross-Validation Plan

Status: PLANNED
Target: 2.3
Baseline: 2.2.2
Repository: sbvcid/st-eva

## 1. Purpose

ST-EVA remains a deterministic Market-Implied Assumptions Engine.

Version 2.3 does not change the core philosophy into a forecasting, target-price, or buy/sell system.

The primary goal of 2.3 is to make the evidence behind valuation references auditable and robust across multiple data sources.

Core principle:

Observed data -> Source provenance -> Cross-source validation -> Deterministic calculation -> Conditional inference -> LLM interpretation

The system must never treat a numerically precise valuation reference as trustworthy merely because a provider returned it.

## 2. Problem Identified in 2.2.2

A live NU run produced a historical P/E median of 45.4x while the regression fixture used 20.0x.

The reverse calculation itself was mathematically correct:

Implied EPS = Price / Reference P/E

13.73 / 45.4 ~= 0.30

The problem is that the economic meaning of the result depends directly on the validity and definition of the reference multiple.

The 2.3 objective is therefore not to replace 45.4x with 20x arbitrarily.

Instead, the system must determine:

- where the reference came from;
- what metric definition was used;
- what historical period was used;
- when the source was updated;
- how many observations were used;
- whether another source agrees;
- whether sources are actually measuring the same thing.

## 3. Scope

### 3.1 Multi-source acquisition

Add support for multiple independent data sources where practical.

The architecture should permit:

- primary provider;
- secondary provider;
- optional tertiary provider;
- static regression fixtures.

Providers must remain separate adapters. Provider-specific acquisition logic must not leak into the deterministic valuation engine.

### 3.2 Provenance

Every material financial or valuation observation should carry provenance sufficient to reproduce or audit the result.

Minimum provenance fields should include, where available:

- provider;
- source type;
- source URL;
- metric name;
- metric definition;
- currency;
- as_of;
- period_start;
- period_end;
- observation count;
- retrieval timestamp;
- methodology or calculation basis.

Do not silently normalize incompatible definitions.

### 3.3 Cross-source comparison

For the same metric, compare observations only when their definitions and temporal scopes are sufficiently compatible.

Example:

Source A:
- trailing P/E
- TTM diluted EPS
- 2024-09 through 2026-09

Source B:
- trailing P/E
- different EPS definition
- full-history period

These must not be treated as directly equivalent observations.

### 3.4 Discrepancy detection

Introduce deterministic discrepancy detection.

Suggested statuses:

- VERIFIED — multiple compatible sources agree within configured tolerance.
- CONSISTENT — sources differ modestly but remain within tolerance.
- DISCREPANT — materially different values require investigation.
- UNVERIFIABLE — only one usable source is available.
- STALE — source data is older than the configured freshness window.
- METHODOLOGY_MISMATCH — definitions or periods are not directly comparable.
- UNAVAILABLE — required evidence is missing.

These are evidence states, not investment ratings.

### 3.5 Historical valuation windows

Make historical valuation periods explicit.

Do not expose only:

historical_pe_median = 45.4

Prefer a structure containing:

- median;
- min;
- max;
- period_start;
- period_end;
- metric_definition;
- observation_count;
- provider;
- methodology;
- source evidence.

The system should be able to distinguish all-history statistics from a recent rolling window.

### 3.6 Reference selection

Do not automatically choose a source because it is numerically closest to another source.

Reference selection must be explicit and auditable.

Priority should remain:

1. User-supplied reference.
2. Validated historical reference.
3. No reference.

A historical median may only become a validated reference when the underlying evidence passes the applicable data-quality checks.

If multiple sources materially disagree, ST-EVA should preserve the disagreement rather than manufacture a consensus.

## 4. Output Model

The 2.3 output should clearly separate five layers.

### OBSERVED

What the provider actually reports.

Example:

Price = 13.73
Consensus Forward EPS = 1.11

### REFERENCE

The valuation reference selected for reverse calculation.

Example:

Historical trailing P/E median = 20.1x
Period = 2024-09 to 2026-09
Provider = Source A

### IMPLIED

The deterministic reverse calculation.

Example:

Implied EPS = 13.73 / 20.1 = 0.68

### COMPARISON

Deterministic comparisons against observed or consensus values.

Example:

Implied EPS vs consensus EPS
Implied EPS vs current EPS

### INTERPRETATION

Optional LLM-generated explanation of the validated JSON.

The LLM must not perform valuation arithmetic or silently change the selected reference.

## 5. Important Semantic Rules

Avoid ambiguous labels.

Do not call an implied EPS value an "EPS growth requirement" unless the calculation explicitly represents a growth requirement.

Do not call a one-period percentage change a CAGR unless the time horizon and CAGR calculation are explicitly defined.

Prefer labels such as:

- Implied EPS
- EPS gap vs consensus
- EPS change vs current
- Required EPS CAGR over N years

Do not convert a low historical percentile directly into "undervalued."

Use descriptive language such as:

"Current P/S is at the 10th historical percentile."

Any further interpretation must remain conditional.

Do not state:

"The market expects EPS to be 0.30."

Instead state:

"At the selected 45.4x reference multiple, the observed price implies EPS of approximately 0.30."

## 6. Data Quality Rules

2.3 must preserve the existing zero-synthetic principle.

Never:

- fabricate missing EPS;
- synthesize consensus estimates;
- fill missing FCF;
- invent historical valuation observations;
- silently substitute one metric definition for another;
- silently use stale fixture values as live data;
- select a more convenient reference merely because it produces a more plausible result.

When evidence is insufficient, return UNAVAILABLE or an appropriate evidence-status state.

## 7. Regression Fixtures

Regression fixtures must be clearly separated from live data.

Each fixture should include:

- fixture_as_of;
- source/provider;
- metric definitions;
- historical window;
- expected values;
- purpose of the fixture.

Fixtures should not be described as current market data.

Where a live result materially diverges from a fixture, the test/reporting layer should make the divergence visible rather than assuming the live provider is wrong.

## 8. Provider Architecture

Target architecture:

Provider A
    |
Provider B
    |
Provider C
    |
Fixture
    |
    v
Evidence Normalization
    |
    v
Cross-Source Validation
    |
    v
Validated Evidence Set
    |
    v
Deterministic Metrics
    |
    v
Reverse Valuation
    |
    v
Machine-readable JSON
    |
    v
Optional LLM Interpretation

The deterministic engine must remain provider-agnostic.

## 9. Testing Requirements

Add tests for:

1. Two compatible sources agreeing.
2. Two compatible sources disagreeing.
3. Different historical windows.
4. Different metric definitions.
5. Stale source detection.
6. Missing secondary source.
7. Currency mismatch.
8. Period mismatch.
9. Fixture/live divergence.
10. Reference selection with explicit user reference.
11. Reference selection when historical references disagree.
12. No reference available.
13. Correct semantic labeling of implied EPS, EPS gap, and CAGR.
14. Preservation of provenance through the final JSON.
15. LLM adapter receiving validated data without performing arithmetic.

All existing 2.2.2 tests must continue to pass.

## 10. Acceptance Criteria

ST-EVA 2.3 is complete when:

- at least two compatible data sources can be represented for a material metric;
- source provenance survives into the final machine-readable output;
- historical valuation windows are explicit;
- incompatible sources are not silently merged;
- material discrepancies are surfaced deterministically;
- reference selection is auditable;
- stale fixtures cannot masquerade as current data;
- zero-synthetic behavior remains intact;
- currency and temporal consistency checks remain intact;
- deterministic arithmetic remains outside the LLM;
- all regression tests pass;
- a live validation run demonstrates the cross-source behavior on several tickers.

## 11. Non-Goals

2.3 will not:

- create price targets;
- generate buy/sell recommendations;
- predict stock prices;
- assign Bull/Base/Bear probabilities;
- choose a "best" stock;
- infer investor sentiment from price alone;
- replace fundamental research;
- make the LLM responsible for valuation arithmetic;
- hide disagreement between data providers.

## 12. Suggested Implementation Order

Phase 1:
Define the normalized evidence/provenance schema.

Phase 2:
Refactor the existing Yahoo provider to populate the expanded provenance fields.

Phase 3:
Add a second provider adapter.

Phase 4:
Implement deterministic cross-source comparison and evidence-status classification.

Phase 5:
Make historical valuation windows explicit and configurable.

Phase 6:
Update reverse-valuation output to use OBSERVED / REFERENCE / IMPLIED / COMPARISON / INTERPRETATION separation.

Phase 7:
Update fixtures and tests.

Phase 8:
Run live validation on a representative set of tickers and document discrepancies.

## 13. Design Decision

ST-EVA 2.2.2 is considered the frozen baseline.

The NU discrepancy is treated as the motivating case for 2.3, not as a reason to patch the 2.2.2 release with an arbitrary replacement multiple.

The 2.3 objective is evidence quality and auditability first.

Additional valuation formulas are secondary.

The project should remain a deterministic analytical primitive that an Agent can call as a tool:

User:
"查 NU"

Agent:
1. Acquire current evidence.
2. Run ST-EVA.
3. Validate reference evidence.
4. Return structured market-implied assumptions.
5. Explain the result.
6. Escalate discrepancies for deeper research.

## 14. One-Line Definition

ST-EVA is a deterministic engine that converts observed market prices into auditable, conditional market-implied fundamental and valuation assumptions, with explicit evidence provenance and no investment decision output.
