# ST-EVA — Reverse Valuation

ST-EVA is a reverse-valuation tool. Given an observed market price and explicit valuation assumptions, it calculates the financial performance implied by those assumptions. **Reverse valuation is the product itself**, not a side feature of a general research platform.

Its central question is:

> At this price, what would a company have to deliver under a stated holding period, required return, and exit valuation multiple?

ST-EVA provides conditional numerical results for a person or an external tool to analyse. It does not decide whether the assumptions are reasonable.

## Product contract

A user supplies a company ticker and inspects the available market price, valuation reference, and financial inputs. The user can specify or inspect scenario assumptions and examine the resulting reverse-requirements matrix. Each scenario states the required terminal price and the fundamental level implied by its exit multiple; it calculates the growth required from a clearly identified starting figure when that growth is computable.

Every material figure must be checkable:

- Source-reported observations, validation results, deterministic derivations, and conditional calculations remain distinct.
- Inputs and outputs retain relevant source, as-of time, covered period, unit, currency, and basis information.
- Each conditional result identifies its assumptions and formula version so the calculation can be independently recomputed.
- EPS figures covering trailing twelve months, next twelve months, and a fiscal year are not silently treated as interchangeable.
- A return requirement without an explicit dividend treatment is a price-return condition, not a total-return claim.
- Missing, unavailable, conflicting, stale, or incompatible inputs remain explicit. They are not replaced with invented values or silently treated as zero.
- Descriptive historical multiples are not automatically eligible as scenario references; reference use follows an explicit quality rule.

## Boundaries

ST-EVA does not forecast actual business results, determine fair value, generate price targets, decide whether a price is cheap or expensive, assign probabilities, rank investments, or make buy/sell recommendations. A reverse calculation is conditional arithmetic, not a prediction that the company will achieve the calculated result.

ST-EVA does not need to call or embed an LLM. Any later interpretation by a person or external LLM is separate from ST-EVA's observed facts and deterministic calculations; it must not be recorded as a source fact.

## Project documentation

- [Current project status](docs/PROJECT-STATUS.md) — changeable implementation findings, unresolved defects, verification status, and next steps.
- [CLI usage](docs/USAGE.md) — commands, options, and current command-line behavior.

The root README records the enduring product purpose and calculation/data rules. Current implementation status belongs in the project-status document; historical notes under `docs/archive/` are not current status or instructions.
