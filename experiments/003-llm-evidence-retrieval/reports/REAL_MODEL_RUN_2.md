# ST-EVA 2.6.1 — Second Real-Model Run

Model: `qwen3:14b`, local Ollama. Same dataset, same snapshot, same auditor,
same temperature. Changed since run 1: the evaluator's two false passes
(2.6.1a), `UNKNOWN_METRIC` and `validation_status` (2.6.1b), the ambiguity
marker and the rewritten T1 (2.6.1c). **Only those.**

Run 1 is 0/15, not the 2/15 it published — both of its passes were the
evaluator's fault.

## Read this first: the same model scored 1/15 and 3/15

Run 2 was executed twice, with nothing changed between them — same model tag,
temperature 0, seed 7, snapshot, dataset, tools, evaluator, prompt:

| | run 2a | run 2b |
|---|---|---|
| passed | **3/15** | **1/15** |
| tests with no evidence retrieved | 7 | 7 |
| failed tool calls | 3 | 3 |
| format-repair turns | 11 | 7 |
| tool calls | 15 | 12 |

**A 3x spread in the headline number on identical inputs.** The aggregate
retrieval outcome was stable at 7, but the score moved because different tests
happened to come out right.

This is the most important methodological result in the sequence, and it
invalidates the comparison I was about to write. A single run cannot separate
"the query surface got better" from "this time it got lucky", and the 0/15 →
3/15 improvement I could have reported from run 2a is not safe to report as an
effect. **Before any cross-model comparison, this harness needs repeated runs
and a dispersion measure — or a model whose output is actually deterministic
at temperature 0.**

What survives the variance is the *direction* of the retrieval change, because
run 1's 7 no-evidence tests were 7 different tests from run 2's:

| | run 1 | run 2 (both) |
|---|---|---|
| tool calls | 25 | 15 / 12 |
| failed calls | 8 | 3 / 3 |
| T3, T4, T10, T11, T12, T12, T1, T13 retrieval | 0–200 | improved |

The failed-call drop from 8 to 3 is reproduced in both runs and has a known
cause (below). The score does not reproduce and is not trustworthy at n=1.

## The failed-call drop was a harness bug, not a model fix

Run 1 recorded 8 failed tool calls, most of them `limit: "1"` — a JSON string
where the schema said integer. `from __future__ import annotations` makes every
annotation in the harness a string, so `harness/schemas.py` read
`Optional[int]` as a string type and **told the model to send a number as a
string**. It did so four times, correctly following the schema it was shown.

The attribution in the first run's report — recorded as model weakness — was
wrong. Annotations are now resolved rather than read, and `order` carries its
enumeration. Failed calls: 8 → 3, reproduced in both runs.

## The dominant remaining failure: fabricated citation ids

**Five of the eight tests that cite any evidence cite identifiers the archive
does not hold.**

| test | what it cited |
|---|---|
| T1 | `observation_12345`, `observation_67890` |
| T2 | `observation_123`, `observation_456` |
| T11 | `observation_123` |
| T12 | `observation_id_12345` |
| T13 | a source-fact string, not an observation id |

T1 is the case that matters:

> "Two observations report conflicting values for Apple's (AAPL) revenue during
> 2006-10-01 to 2007-09-29: 24,578,000,000.0 … and 24,006,000,000.0."

It **read the ambiguity marker correctly**, found both values, and understood
the archive holds two. Then it cited `observation_12345`. The reasoning is
right and the provenance is invented.

In a system whose product is traceability this is worse than a wrong number,
because a wrong number can be checked against evidence and a fabricated id
*looks* checkable. The audit catches it mechanically.

## Four tests never ask

T3, T7, T8 and T9 made **zero tool calls** and answered anyway. T8 again:

> "The existence of a disagreement for AAPL is noted, but … cannot be determined
> from the available tools."

The archive records the conflict. The model answered about it without looking.

T9 is the interesting one, because the surface is now working:

> "The metric 'operating margin bank' is not recognized by ST-EVA. The available
> metrics for AAPL include operating margin, net income, and revenue, among
> others."

The refusal is **correct** — the metric is `operating_margin_bank` and the model
wrote a space. The error message told it so, it listed the real names it had
just been given, and it did not retry. A1 fixed the ambiguity; it did not teach
recovery from it. That is now a model limitation, not a surface defect.

## A-category findings: both closed, none new

A1 and A2 are fixed and pinned by tests that fail if either is reintroduced.
**No new A-category defect appeared**, and all 14 remaining failures classify as
B. The database, registry and archive were correct in every case examined.

## Two harness defects this run found in the harness

Both were caught by requiring a stored run to reproduce its own score, which is
a stronger property than "the report looks right":

- **The trace was not sufficient to re-audit.** A trace kept only
  `result_shape`, and the pagination check reads how many points came back, so
  a re-audit counted zero and disagreed with the published verdict. Traces now
  carry `returned_count`.
- **A check read a value the trace does not keep.** T4's point-in-time check
  tested `call.result`, so it passed live and failed on re-audit. Checks now
  use `Call.succeeded`, derived from fields that survive into a trace.

A trace that cannot reproduce the audit is not a trace. Both are fixed and the
invariant is now a test.

## Where each category stands

| | run 1 | run 2 | attribution |
|---|---|---|---|
| retrieval | 7 no-evidence | 7 no-evidence | **unchanged** |
| tool failures | 8 | 3 | harness schema bug, fixed |
| fabricated citations | not reached | 5 of 8 citing | the model's |
| semantic | ~2 | ~2 | never the weak point |
| score | 0/15 | 1–3/15 | **not distinguishable from noise** |

Retrieval did **not** improve, once the run-to-run variance is taken into
account. The first two runs of 2.6.1 both landed at 7 no-evidence tests, the
same as run 1. The apparent retrieval improvement in run 2a was noise.

This reverses the conclusion I drew from run 2a. What *is* real: the tool
schema fix (8 → 3 failed calls, reproduced), and the A1/A2 surface fixes, which
are demonstrably correct even though this run did not show a score benefit.

## Next

1. **Variance before comparison.** Run each model 3–5 times and report a
   dispersion, or pin determinism. Without this, a model comparison measures
   luck. This is now the blocking methodological issue.
2. **Then `gemma4:12b`**, already available locally, on the identical baseline.
3. **Do not change ST-EVA again on this evidence.** Every remaining failure is
   B. The fabricated-citation finding is a model property and belongs in a
   report, not in the query surface.

## Reproducing

```bash
cd experiments/003-llm-evidence-retrieval
PYTHONPATH=C:/git/st-eva python -m harness --build --live
PYTHONPATH=C:/git/st-eva python run_real_model.py
```

Run 1's artefacts are in git at `176c4af`. `reaudit_recorded_run.py` re-grades
stored answers with the current evaluator; `tests/test_eval_harness.py`
asserts that a recorded run re-audits to its published score.
