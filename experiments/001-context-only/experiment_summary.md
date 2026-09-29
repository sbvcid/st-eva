# Experiment 001 — Summary

Context-only agent analysis of six ST-EVA `InvestmentContext` documents.
Full method in `prompt.md`; agent self-audit in `self_audit.md`.

## 1. Validity caveat, stated first

**The agent that ran this experiment also built the contexts.** That is a
serious limitation and it belongs at the top of the summary rather than in a
footnote.

This is not a blind test of whether an unrelated model can read the Context. The
agent arrived already knowing the document's shape, having written the code
that emits it, and having read all six documents during the 2.4.2 debugging
work. Errors it would make on a cold read were largely errors of *transcription
under familiarity*, not of comprehension — and transcription under familiarity
is arguably the more likely failure mode in production, where an agent may also
have seen the pipeline.

What this experiment can support:

- Whether the Context's **structure** invites misreading, because structural
  invitations are independent of the reader's history.
- Whether a **careful** reader can reach correct answers from the document
  alone, with no external data, and say so when the document is insufficient.
- Which **ambiguities and defects** are discoverable only by consuming the
  document as a consumer would.

What it cannot support: a claim about a cold-start model's accuracy. That needs
an agent with no prior exposure, ideally several, run in parallel.

## 2. The six contexts

All six were read, analysed, and passed ST-EVA's own self-checks. Inputs are
pinned in `input/` with hashes recorded in `prompt.md`.

| Context | Read | Engine inputs | Cross-source verdicts | Derived figures present | `unavailable` entries |
|---|---|---|---|---|---|
| AAPL | yes | 13 / 14 | 3 CONSISTENT, 2 METHODOLOGY_MISMATCH, 1 PERIOD_MISMATCH, 1 UNAVAILABLE | 7 / 16 | 14 |
| MSFT | yes | 13 / 14 | same shape | 7 / 16 | 14 |
| NVDA | yes | 14 / 14 | 2 CONSISTENT, 2 METHODOLOGY_MISMATCH, 2 PERIOD_MISMATCH, 1 UNAVAILABLE | 7 / 16 | 13 |
| MU | yes | 13 / 14 | 3 CONSISTENT, 2 METHODOLOGY_MISMATCH, 1 PERIOD_MISMATCH, 1 UNAVAILABLE | 7 / 16 | 14 |
| TSM | yes | 11 / 14 | 0 CONSISTENT, 1 METHODOLOGY_MISMATCH, 6 UNAVAILABLE | 4 / 16 | 19 |
| NU | yes | 10 / 14 | 7 UNAVAILABLE | 5 / 16 | 19 |

## 3. Were older contexts or research reports used?

**No.** Inputs are the six files pinned in `input/`, all
`context_schema_version 2.3-C.1`, generated fresh from ST-EVA commit `46e05d3`
for this experiment. No report in `03_研究產出` was read as input, and no
earlier context was consulted.

One administrative note: the six context files this experiment was asked to
read from `C:\git\IBKR` were **deleted from that directory between turns** — on
the first attempt only a `README.md` remained, with no `.git` and none of the
sub-folders, including `01_原始資料` and `04_中繼資料與腳本`. They were
regenerated directly into the experiment's pinned `input/` folder, which is
better practice for an experiment anyway, since the inputs can no longer be
changed out from under the outputs. If the loss of that directory was not
intended it should be checked before the next phase.

## 4. Was external data used?

**No.** No web search, no financial API, no Yahoo, no SEC query, no news, no
prior company knowledge. Every figure in the six reports resolves to a `ref` in
its Context. The self-audit records two instances where a number was produced
from memory rather than from the file; both were caught by reconciling the
arithmetic against the Context's own operands, and both were corrected before
delivery. Neither survived into the output.

## 5. Schema and semantic ambiguity found

### 5.1 Defects (ST-EVA)

**S1. `data_quality.series` reports 78 spurious discontinuities.**
`series_metadata` groups points by derivation (`CONSTRUCTED:` vs
`REPORTED_PERIOD`) but not by period span, so 90-day quarters and 364-day
cumulative periods share a group and are differenced against each other. Several
entries have `from_period == to_period`. The worst is NVDA `revenue`
`2022-01-30 -> 2026-07-31` at `relative_change 10.26`, which spans the gap
left by an undated vendor figure. **An agent is invited to read an artifact as a
ten-fold growth event.** The one genuine discontinuity in the six contexts —
NVDA debt, `2.94x` — sits in a single-basis group and is correct.

Fix: key the group on `(construction, period_span_bucket)`. Not applied here, per
the instruction not to modify Core during this experiment.

**S2. `NOT_AVAILABLE` refusals do not name their cause.** NU's `current_pfcf`
is refused with *"not computable: the engine produced no value and no substitute
is permitted"*. The available free cash flow is negative. A reader must find
that elsewhere, and a reader who does not will guess. A refusal that omits its
cause invites interpretation, and interpretation is what this artifact exists to
prevent.

### 5.2 Ambiguities that are correct but costly to read

**A1. `validation_state: UNVALIDATED` on all 96 derived figures.** The reason is
real — validations judge `cmp-` observations while derivations consume `ev-`
observations — but nothing in the figure itself says *why*. An agent that
checked only the status would conclude "the engine failed to validate", which is
the opposite of the truth: the engine validated the comparable observations, and
the valuation figures use a different set. This is a **presentation** gap, not
a logic gap.

**A2. MSFT's `eps_diluted` is validated one quarter behind `revenue` and
`net_income`.** Both verdicts are `CONSISTENT`, each correctly aligned for its
own window. A reader must compare three period fields to notice, and nothing
flags the asymmetry. The correct handling is stated in the report: *these
observations have different filing periods*, and no more.

**A3. MU's `debt` verdict is `METHODOLOGY_MISMATCH` on a 2013 observation.**
The currency check fires before the period check, so the verdict name does not
hint at the staleness. `freshness.by_metric.debt` carries the 2013 date and a
4,830-day age. A reader checking only `validated_evidence` would take a
thirteen-year-old value as a current comparison.

**A4. TSM's `current_ps` refusal is correct and the most legible state in the
set.** `INCOMPATIBLE_CURRENCY` with the reason naming both operands
(*"operand 0 is USD, operand 1 is TWD"*) is the model the other refusals should
follow.

## 6. Agent interpretation errors

Four, all caught, none delivered. Detailed in `self_audit.md`.

| # | Error | Caught by |
|---|---|---|
| 1 | Three MSFT input values written from memory, not read (`consensus_forward_eps` 15.3136 vs **23.67588**; `free_cash_flow` 66,690,000,000 vs **66,987,000,000**; `ebitda` 207,501,000,000 vs **207,519,000,000**) | `current_pfcf` failed to reconcile with the operands I had written |
| 2 | NVDA filing-side TTM EPS written as 4.13, actual **7.91** | caught on re-read before delivery |
| 3 | NU's cross-source statuses misattributed as methodology mismatch; actual `{"UNAVAILABLE": 7}` | reading the actual tally |
| 4 | MSFT discrepancy first attributed to enterprise value; EV is *below* market cap | checking `mcap-ev` sign |

**The most transferable result is #1.** A `ref` beside a number gives it the
*appearance* of provenance without making it checked. The only thing that
caught it was recomputing from the operands. Any future agent-facing workflow
should make that recomputation mandatory rather than optional, and should treat
a `ref` as a pointer for verification, not as a substitute for reading the
figure it points to.

## 7. Ownership of each error

| Error | Context problem | Agent problem | Prompt problem |
|---|---|---|---|
| 78 spurious discontinuities | **yes** | no | no |
| `NOT_AVAILABLE` reason omits cause | **yes** | no | no |
| `validation_state` gives no reason | **yes** (presentation) | no | no |
| MSFT asymmetric validated periods | no (correct behaviour) | no | **yes** — the experiment asked for a period check but nothing says to compare validated metrics *against each other* |
| MU `debt` verdict hides staleness | **yes** | no | no |
| 3 hallucinated MSFT values | no | **yes** | no |
| NVDA fabricated EPS | no | **yes** | no |
| NU status misattribution | no | **yes** | no |
| MSFT EV attribution | no | **yes** | no |
| NU negative FCF prior, suppressed | no | **yes** (correctly) | no |

## 8. What is worth changing in ST-EVA

Ordered by how much damage each does to a consumer that trusts the document.

1. **Fix `series_metadata` grouping** (S1). 78 of 79 reported discontinuities
   across these six contexts are artifacts, and each invites a false narrative.
   This is the only item where the Context actively misleads.
2. **Name the cause in every refusal** (S2). A refusal that omits its reason
   is an invitation to guess, and guessing about a refusal is how a document
   that refuses becomes a document that asserts.
3. **Explain `validation_state` in the figure.** A one-line
   `validation_note` would let an agent distinguish "not validated" from
   "validated a different observation".
4. **Surface recency on the verdict that hides it** (A3). When a validation
   rests on an observation older than its cadence, that should be visible in
   `validated_evidence`, not only in `freshness`.
5. **Consider a `periods` summary across validated metrics**, so asymmetry
   like MSFT's is visible without comparing three fields by hand.

None of these change a single number the engine produces. They change what a
reader can wrongly conclude from the numbers already there.

## 9. What should NOT be changed in ST-EVA

These are the behaviours that make the Context trustworthy, and an agent error
in any of them is an agent error, not a Context problem.

- **`UNAVAILABLE` with no value.** All 59 derived entries without a value
  across the six contexts carry no `value` key. An agent that fills one in has
  misread the document; the document is unambiguous.
- **Refusing a cross-currency ratio.** TSM's `current_ps` is absent with
  `INCOMPATIBLE_CURRENCY` naming both operands. Producing the ratio and
  annotating it would be worse: the number would exist and be quotable.
- **`NO_WINNER_SELECTED`.** TSM's 5.85× share-count difference and NU's 1.41×
  difference are both reported with no winner. Choosing one is not an
  interpretation the Context supports, and the Context is right not to.
- **`unexplained` for a real discontinuity.** NVDA's debt moving 2.94× is
  reported as `NOT_EXPLAINED_BY_ST_EVA`. An agent that explains it is
  exceeding the evidence, and the Context has deliberately declined to.
- **`UNVERIFIED_INDEPENDENCE` on agreement.** Every `CONSISTENT` verdict
  carries it, including the three where the two sources agree to the last digit.
  A vendor that ingested a filing will agree with it. Reading `CONSISTENT` as
  verified is an agent error.
- **Refusing an implied requirement when no eligible reference exists.** All six
  contexts have `valuation_reference.multiple: null` and an entirely absent
  implied block. A reader who supplies a median multiple, or a consensus
  multiple, or a target price, has invented a valuation model that the Context
  explicitly declines to contain.

## 10. Does the Context answer the question it was built to answer?

> Can an agent correctly know what ST-EVA knows, and what it does not?

**Yes, with effort and one trap.**

The "what ST-EVA knows" side is strong. Price, market cap, revenue, EPS, FCF,
EBITDA, EV, and the observed multiples are all present with a `ref`, a unit, a
currency, a period, and a provider. Every derived figure is recomputable from
named operands, and this experiment recomputed them all and every one matched.

The "what ST-EVA does not know" side is the more valuable half, and it is in
good shape. TSM's missing P/S, MU's 2013 debt, NVDA's 2022 revenue, the absent
implied block in all six, and the unresolved share counts in TSM and NU are all
stated, reasoned, and blocking-aware. The `blocks` edges make the consequences of
a gap explicit rather than requiring a reader to trace them.

The one trap is S1. Everything a Context says about *values* is trustworthy.
Something it says about *series shape* is currently not, and it is phrased in
the same authoritative register.

## 11. Recommendation for the next phase

**Proceed, after fixing S1.**

Experiment 002 should be a genuine cold-start test rather than another
self-administered one, because the limitation in §1 is the main thing keeping
this result from generalising. Recommended shape:

- Hand the same six contexts to at least two agents with no prior exposure to
  ST-EVA, ideally with different providers, so familiarity cannot be a
  confound.
- Run the same nine sections, so the outputs are directly comparable to
  `outputs/`.
- Score on the audit categories in `self_audit.md` rather than on report
  quality, since a fluent report is the thing this experiment most easily
  produces while getting wrong.
- Expect F1 — transcription under familiarity — to be the dominant error mode
  even in a cold reader, and measure it rather than assuming it away.

Two of the five ST-EVA items in §8 (S1, S2) should be fixed before that run,
so the next experiment measures the Context as it should be read rather than
punishing a reader for a defect they had to work around here. `2.4.3` covering
both is the natural home. `2.4` and `2.5` remain not started.

---

## 12. Postscript: what 2.4.3 did with these findings

Experiment 001 ran on 2.3-C.1. The three findings in sections 5.1 and 8 were
then fixed as **2.4.3**, and this document has been left unedited so the record
shows what the agent read rather than what it would read after the fix.

| Finding | Fixed in 2.4.3 as | Verified effect |
|---|---|---|
| S1 spurious discontinuities | series_status + series_status_reason: PERIOD_SPAN_MISMATCH; series key is now (period span, observation type, construction) | 78 -> 36 reported discontinuities across the six; AAPL 21 -> 5, MSFT 16 -> 1, NVDA 19 -> 9, MU 22 -> 21. The real NVDA debt move (2.94x) is preserved unchanged. |
| S2 refusal reasons are prose | eason_kind + eason_code + input_ref + input_value + condition, from closed vocabularies | the NU current_pfcf case now reads NEGATIVE_INPUT / NON_POSITIVE_DENOMINATOR / obs:ev-fcf-001 / -1669966000 instead of a sentence |
| A3 alidation_state has no reason | state_flags on a derived figure, present only when non-empty: STALE_INPUT, UNDATED_INPUT, UNVALIDATED_INPUTS | current_pe now carries UNDATED_INPUT and UNVALIDATED_INPUTS; current_ps carries two UNDATED_INPUT because revenue and market cap both lack a publication time |

Two observations about the fix that matter more than the counts.

**MU barely moved, 22 to 21, and that is the correct result.** Its remaining
discontinuities are all *within* one comparable series. The experiment treated
"22 discontinuities" as a symptom; only 1 of them was. A fix that had reduced MU
to 3 would have been hiding real, unexplained movements in a lumpy business.

**The findings in section 9 were confirmed, not repaired.** A context written
before 2.4.3 and replayed after it will now report DIVERGED, because the
document changed shape. context_schema_version moved to 2.3-C.2 and
experiment 001's pinned inputs remain at 2.3-C.1. Experiment 002 should decide
deliberately which version it feeds an agent: measuring the older one reproduces
this experiment, and measuring the newer one is the run that matters.
