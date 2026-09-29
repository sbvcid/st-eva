# Experiment 001 — Context-only agent analysis

## What this experiment is

Does a general-capability LLM, given **only** an ST-EVA `InvestmentContext`,
read it correctly? Specifically: can it tell what ST-EVA knows from what ST-EVA
does not know, without filling gaps from its own training or from the web?

This is not a test of investment judgment. No buy, no sell, no target price, no
ranking, no probability. Those are all out of scope by construction, and the
Context contains no fields that would support them.

## Inputs

Six `InvestmentContext` documents, pinned in `input/`. These are the exact files
this experiment consumed; nothing else was read.

| Ticker | sha256 (first 16) | context_id | as_of |
|---|---|---|---|
| AAPL | `6C8EECB83A0EDD35` | see `input/AAPL.context.json` | 2026-09-28 |
| MSFT | `0BD7BA9EAB0DEBB3` | see `input/MSFT.context.json` | 2026-09-28 |
| NVDA | `73BE254B85EC7842` | see `input/NVDA.context.json` | 2026-09-28 |
| MU | `BC64D39E6CF9E097` | see `input/MU.context.json` | 2026-09-28 |
| TSM | `5EF8ED02E9E0931E` | see `input/TSM.context.json` | 2026-09-28 |
| NU | `A50C863A2B451DB7` | see `input/NU.context.json` | 2026-09-28 |

All six are `context_schema_version 2.3-C.1`, built from ST-EVA commit `46e05d3`
(2.4.2). No earlier context, and no research report, was used as input.

## Information boundary

The agent must not, and did not:

- search the web, or call any financial data API
- consult Yahoo Finance, the SEC, or any news source
- use prior knowledge of these companies to fill a gap
- estimate a missing value
- pick a winner among conflicting observations
- present its own assumption as a market assumption

Every factual claim must resolve to a `ref` in the Context. Where the Context
has nothing, the correct output is `UNAVAILABLE` or `NOT PROVIDED BY CONTEXT`.

`UNAVAILABLE`, `NO_RECENT_VALUE`, `METHODOLOGY_MISMATCH` and
`NO_WINNER_SELECTED` are **valid results**. The experiment is not asking for a
complete-looking report; it is asking for an accurate one.

## What each report must contain

**A. What the Context clearly knows** — 5–10 material facts, each with claim,
provenance type, and `ref`. Inference must not be written as an observed fact.

**B. What the Context clearly does not know** — the important `UNAVAILABLE`,
`NO_RECENT_VALUE`, `MISSING_INPUT`, `INSUFFICIENT_OBSERVATIONS`,
`NOT_REPORTED_BY_SOURCE` and `UNVERIFIED` items, each with what is missing, the
reason and `reason_kind`, and whether it blocks a derived value.

**C. Validation** — which metrics have validation evidence, at what status, for
what period, and whether a ref linkage can be built from a validation
observation to the derived input actually used. Check `der:current_pe`,
`der:forward_pe`, `der:consensus_forward_pe`, `der:current_ps`,
`der:current_pfcf`, `der:current_ev_ebitda`, `der:implied_shares`. Do not
assume that a metric name matching a validated metric means the derived figure is
validated.

**D. Derived values** — for each material one: find the derivation record, the
expression, the operand refs, whether the operands exist, whether any operand is
unavailable, and whether a validation linkage exists. Do not redefine the
calculation. A derived value may be described arithmetically. It must not be
restated as cheap, expensive, undervalued, overvalued, attractive or
unattractive, because the Context does not say that.

**E. Data quality** — at least one methodology mismatch, one period mismatch,
one stale or no-recent-value, one unavailable, one insufficient-observation.
Where a category does not apply, say so rather than manufacturing a case.

**F. Period coherence** — check the filing periods of different validated
metrics, MSFT revenue/net_income against MSFT eps_diluted in particular. If the
periods differ, state only that they differ. Do not conclude one is wrong.

**G. Unit, currency, basis** — currency mismatch, unit mismatch, share-basis
mismatch, ADS/ordinary share distinction. TSM in particular. Confirm that a USD
market cap divided by a TWD revenue is not a valid P/S.

**H. Market-implied requirements** — is the Context sufficient to derive the
market-implied EPS/revenue/FCF/EBITDA requirement? If `valuation_reference` is
`UNAVAILABLE` or the derived values are `MISSING_INPUT`, the answer must be that
the Context is insufficient. Do not set a historical multiple, do not use a
consensus multiple, do not select a median, do not build a target price.

**I. Inference separation** — tag output as `FACT`, `DERIVED`, `VALIDATION`,
`UNAVAILABLE` or `INFERENCE`. Anything unsupported by the Context is not
written as fact.

## Cross-company comparison

Permitted, and only for figures the Context supplies: reported price, market
cap, revenue, EPS, derived PE, derived forward PE, volatility, return,
validation status, freshness status, unavailable status.

Not permitted: best/worst, ranking, score, attractiveness, buy/sell, valuation
judgement, target price, expected return, probability.

"MU has the highest reported annualized realized volatility among the six
contexts" is a Context observation. "MU is the riskiest investment" is an
investment interpretation and is out of scope.

## Deliverables

```
input/        the six contexts actually used, pinned
prompt.md     this file
outputs/      AAPL.md MSFT.md NVDA.md MU.md TSM.md NU.md
self_audit.md F1–F8
experiment_summary.md
```

## Constraint on the outcome

If the Context is ambiguous, incomplete, or self-contradictory, that is a
finding to report — **not** something to repair by editing ST-EVA. The
experiment measures the Context as it is.
