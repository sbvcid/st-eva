# Self-audit — experiment 001

Audited after writing all six reports, against the same six contexts. Categories
F1–F8 are those in `prompt.md`. Each finding states what happened, whether it
survived into the delivered output, and who owns the fix.

---

## F1 — Fact hallucination

**Two instances, both caught and corrected before delivery. One is important
enough to lead with.**

### F1.1 MSFT — three fabricated input values (caught)

While writing `outputs/MSFT.md` I transcribed three engine-input values that I
had **not** read from the file in that pass:

| Field | Value I wrote | Value in the Context |
|---|---|---|
| `consensus_forward_eps` | 15.3136 | **23.67588** |
| `free_cash_flow` | 66,690,000,000 | **66,987,000,000** |
| `ebitda` | 207,501,000,000 | **207,519,000,000** |

I caught this only because `current_pfcf` and `current_ev_ebitda` in the
Context failed to reconcile with the operands I had written down
(55.4907 against 3,717,153,817,339 / 66,690,000,000 = 55.4898). The Context was
right in all three cases; I was wrong. Corrected, and the derived arithmetic
now reconciles exactly.

**This is the most important result in the experiment.** The failure mode is not
random: two of the three wrong values are ones I had seen in a *previous* run of
a *different* tool, and the numbers were carried forward from memory while
feeling verified because they sat in a table with a `ref` next to them. A `ref`
gives a number the *appearance* of provenance. It does not make it checked.
Writing a `ref` next to a remembered value is the most likely way an agent
produces a confident, well-formatted, unverifiable fact.

- Survived into output: **no**, corrected.
- Owner: **agent interpretation.** The Context was not at fault and needs no
  change. A re-read of the file before writing the table would have prevented it.

### F1.2 NVDA — one fabricated filing-side value (caught)

I wrote *"Filing-side trailing EPS to 2026-07-26: 4.13 USD/share"* for
`obs:cmp-eps_diluted-sec-ttm-to-2026-07-26-…`. The Context's value is
**7.91**. I had picked up a neighbouring figure from the same series. Corrected
before delivery.

- Survived into output: **no**, corrected.
- Owner: **agent interpretation**, same cause as F1.1.

### F1.3 No external knowledge used

Checked: every figure in all six reports carries a `ref` or is a derived value
traced to operand refs. No company fact, event, date, sector, or comparison
appears that is not in the Context. No web access, no API call, no prior
knowledge of any of the six companies was used to fill a value.

**One near-miss worth recording.** For NU, the free cash flow is negative
(−1,669,966,000) and `current_pfcf` is `UNAVAILABLE`. I had a strong prior that
a negative FCF is a meaningful signal about a business. I did not write it,
because the Context's reason text is *"not computable: the engine produced no
value and no substitute is permitted"* and contains no such claim. Suppressing
that prior is the same discipline as F1, applied to interpretation rather than
to numbers.

---

## F2 — Context misread

**Two genuine misreads caught; one Context ambiguity found.**

### F2.1 MSFT — wrong source_type attribution (caught)

While reconciling an arithmetic mismatch I first attributed the discrepancy
to enterprise value. That was wrong: MSFT's enterprise value is
*below* its market capitalisation (3,697,328,817,339 vs 3,717,153,817,339),
which is consistent with the Context's own `mcap-ev` being positive. The
discrepancy was entirely in my transcription (F1.1), not in the Context. No
misstatement entered the output.

### F2.2 "Period mismatch absent" for NU and TSM (caught)

My first pass for NU reported the cross-source status as "methodology
mismatch" because the TSM and NU patterns looked similar. Reading the actual
`cross_source` tally for NU: `{"UNAVAILABLE": 7}`. There is **no**
methodology mismatch and **no** period mismatch for NU — all seven metrics have
`filing_ref: null`. Both reports were corrected to state the categories as
inapplicable rather than approximate them with a neighbouring case, which is
what the experiment asked for.

### F2.3 Context ambiguity found: `NOT_AVAILABLE` reason is generic

NU's `current_pfcf` carries
`reason_kind: NOT_AVAILABLE` and
`reason: "not computable: the engine produced no value and no substitute is
permitted"`. The available free cash flow at `obs:ev-fcf-001` is **negative**.
A reader must supply "the free cash flow is negative" themselves from a
different part of the document; the refusal does not say it.

- Owner: **ST-EVA.** A refusal whose reason omits the cause invites a reader to
  guess the cause, and a reader who guesses "the company burns cash" has learned
  something the Context declined to assert. Worth a `reason_kind` or a clause
  naming the condition.

---

## F3 — Derived-value error

**None in the delivered output.** Every arithmetic statement in the six reports
was checked against the operands, and the three that initially disagreed traced
back to F1 transcription errors rather than to a misreading of a derivation.

Checks performed, per company, from `provenance.derivations`:

- `current_pe` = `obs:ev-price-001` / `obs:ev-current-eps-001` — verified
- `forward_pe` and `consensus_forward_pe` — verified, including that they are
  the same number where `forward_eps` and `consensus_forward_eps` are the same
  observation value
- `current_ps` = market cap / revenue — verified for the five contexts that
  carry it; correctly reported as withheld for TSM
- `current_pfcf` = market cap / free cash flow — verified for AAPL, MSFT, NVDA,
  MU; withheld for TSM (input unavailable) and NU (negative input)
- `current_ev_ebitda` = enterprise value / EBITDA — verified for AAPL, MSFT,
  NVDA, MU; withheld for TSM and NU
- `implied_shares` = market cap / price — verified for all six
- No figure was re-derived with a redefined formula. The registry `op` and
  `parameters` were read, not reconstructed.

`INFERENCE` One case where the naive reading would be wrong and the Context is
right: for MSFT, `forward_pe` and `consensus_forward_pe` are identical
(21.5080) because `forward_eps` and `consensus_forward_eps` are the same value.
Reading that as a single figure rather than two agreeing figures would be an
interpretation the Context does not make. Reported as two figures with two
operand pairs.

---

## F4 — Inference presented as fact

**None in the delivered output.** Every report separates §A `FACT` from §I
`INFERENCE` explicitly, and each report contains exactly one flagged
`INFERENCE`, in every case a statement about what a reader might wrongly do
with the document rather than a number.

Deliberately **not** written, in any report:

- "MU is the cheapest of the six" — `current_pe` 24.4486 is the lowest
  reported, and the report says only that the figure exists.
- "MU's forward PE of 6.5426 implies growth" — not written. The Context has no
  field relating `forward_pe` to a growth expectation.
- "TSM trades at an unquantifiable multiple" — not written. The report says
  `current_ps` is `UNAVAILABLE` with `INCOMPATIBLE_CURRENCY` and stops.
- "NU's negative free cash flow is a red flag" — suppressed (F1.3).

---

## F5 — Ignored unavailable evidence

**None.** Each report's §B enumerates the full `unavailable` list, and each
derived figure is classified `DERIVED` or `UNAVAILABLE` individually rather than
in aggregate. Across the six reports, all 96 derived entries (16 × 6) are
accounted for: **37 carry a value and 59 carry none.**

| | AAPL | MSFT | NVDA | MU | TSM | NU |
|---|---|---|---|---|---|---|
| derived entries | 16 | 16 | 16 | 16 | 16 | 16 |
| with a value | 7 | 7 | 7 | 7 | 4 | 5 |
| without a value | 9 | 9 | 9 | 9 | 12 | 11 |
| `unavailable` entries | 14 | 14 | 13 | 14 | 19 | 19 |

The blocking chain was followed rather than summarised. For all six contexts
the implied block is absent, and each report traces it:
`valuation_reference.multiple` `NO_REFERENCE_AVAILABLE` (band below 20
observations) → `implied_forward_eps` `MISSING_INPUT` → `required_eps_cagr`
`MISSING_INPUT`. No report asserts an implied requirement.

---

## F6 — Missed important evidence

**One important Context finding was initially missed, and it is a defect in the
Context rather than in the agent's reading.**

### F6.1 Spurious series discontinuities (found, raised, not fixed)

`data_quality.series[].discontinuities` reports, across the six contexts, **78
entries**: AAPL 21, MU 22, NVDA 19, MSFT 16, TSM 0, NU 0. Several have
`from_period` equal to `to_period`, and relative changes run from 0.5 to 10.3.
Every one is labelled `explanation: NOT_EXPLAINED_BY_ST_EVA`.

An agent is invited to read these as real economic discontinuities. They are
not. `data_quality.series.bases` shows the `REPORTED_PERIOD` group for MSFT
`revenue` containing both ~90-day quarters and 364-day periods:

```
2024-03-31 span=91   2025-03-31 span=89    2025-09-30 span=91
2024-12-31 span=91   2025-06-30 span=364   2025-12-31 span=91
2025-03-31 span=89   2025-09-30 span=91    2026-06-30 span=364
```

A 90-day quarter is being differenced against a 364-day cumulative period. That
produces a factor-of-three "discontinuity" that is an artifact of grouping, not
a change in the business. The same pattern appears in AAPL, NVDA and MU, and it
accounts for the great majority of the 78.

The clearest single artifact is NVDA `revenue`:
`2022-01-30 -> 2026-07-31`, `relative_change 10.26`. The 2026 point is the
undated vendor figure and the 2022 point is the last dated filing; the Context
correctly refuses to date the former, so the group spans a four-year gap that
reads as a ten-fold growth event.

The only *real* discontinuity in the six contexts is NVDA's debt move,
`2026-04-26 -> 2026-07-26`, `relative_change 2.94`, which sits within a
single-basis group of comparable periods. That one is genuine and is reported
as unexplained, which is what the Context is designed to do.

- Owner: **ST-EVA.** `series_metadata` groups by derivation
  (`CONSTRUCTED:` vs `REPORTED_PERIOD`) but not by period span, so quarterly
  and annual observations share a group and are differenced against each other.
  The fix is to key the group on `(construction, period_span_bucket)`.
- **Not fixed during this experiment**, per the instruction not to modify ST-EVA
  Core here. Recorded for the next phase.
- Handled in output: the MSFT report explicitly declines to treat the 17
  entries as findings, because reading them as such would be wrong. NVDA and MU
  reports state their discontinuity counts as recorded and do not draw
  conclusions from them.

### F6.2 Findings carried through, not missed

- `validation_state: UNVALIDATED` on all 96 derived entries, and the reason
  (validations judge `cmp-` observations, derivations consume `ev-`
  observations) — reported in every context.
- `stale_metrics` — MU `debt` (2013-05-30), NVDA `revenue` (2022-03-18), TSM
  `shares_outstanding` (2025-12-31) — each reported.
- `identity_conflicts` — TSM and NU — both reported with
  `NO_WINNER_SELECTED` and neither figure selected.
- TSM's `INCOMPATIBLE_CURRENCY` refusal of `current_ps` — reported as the
  central fact of that context.
- MSFT's one-quarter period difference between `eps_diluted` and
  `revenue`/`net_income` validations — reported in §C and §F, with the explicit
  statement that no correctness judgement is attached.

---

## F7 — Unsupported economic interpretation

**None.** No causal claim, no sector or competitive claim, no explanation of
any flagged discontinuity, and no statement about what a price level "implies"
beyond the Context's own `conditional_statement`.

The Context's statement is quoted rather than paraphrased or improved:
*"Implied fundamentals are conditional on the selected valuation multiple.
Price alone does not identify a unique fundamental path."*

---

## F8 — Unsupported conclusion

**None.** No report contains a recommendation, ranking, score, probability,
target price, or expected return. The cross-company comparison in
`experiment_summary.md` states only which Context reports the highest or
lowest value of a named figure, and explicitly declines the step from
"MU has the highest reported realized volatility" to any statement about MU as
an investment.

---

## Summary

| Category | Findings | Survived into output | Owner |
|---|---|---|---|
| F1 fact hallucination | 2 (MSFT ×3 values, NVDA ×1 value) | 0 | agent |
| F2 context misread | 2 misreads + 1 Context ambiguity | 0 | agent ×2, ST-EVA ×1 |
| F3 derived-value error | 0 | 0 | — |
| F4 inference as fact | 0 | 0 | — |
| F5 ignored unavailability | 0 | 0 | — |
| F6 missed evidence | 1 Context defect, 4 findings carried | 1 | ST-EVA |
| F7 unsupported interpretation | 0 | 0 | — |
| F8 unsupported conclusion | 0 | 0 | — |

**All four agent-side errors were caught before delivery, three of them by
attempting to reconcile my own arithmetic against the Context's operands.** That
is the one behaviour in this experiment that I would keep, and it is worth
stating as a finding: a `ref` makes a number look sourced, and only
recomputing from the operands proves it was actually read.
