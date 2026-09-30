# 2.6.5 — Semantic Consumer evaluation

Seven semantic probes, five runs, one model. The point of this round was to find
out **what a capable model fails at when it understands the evidence**, and the
answer turned out to be that most of what it failed at, it failed at because of
me.

---

## 1. What the model did

`nvidia/nemotron-3-ultra-550b-a55b:free`, five runs, same snapshot
`ce603a5588cef067`, same tool schema, same prompt, same evaluator, temperature 0.

| probe | runs | |
| --- | --- | --- |
| P1 reported or derived | **5/5** | `DERIVED`, op `divide`, 31.42, the operand — in one `get_lineage` call |
| P2 negative state cause | **5/5** | the recorded state and its reason code |
| P3 what the disagreement is | **5/5** | `MULTIPLE_SOURCE_CONCEPTS` |
| P4 what PARTIAL means | **1/5** | fidelity right, comparability unreliable |
| P5 two concepts, one series | **5/5** | `NOT_COMPARABLE`, one figure of each concept |
| P6 point-in-time | **0/5** | right figure, right observation, wrong code |
| P7 source consistency vs truth | **0/5** | no answer at all, five runs |

**`nvidia/nemotron-3-ultra-550b-a55b:free`: EVIDENCE CONSUMER ACCEPTED · SEMANTIC CONSUMER NOT_YET**

| criterion | observed | |
| --- | --- | --- |
| no fabricated identifiers | 45 cited, 0 the archive does not hold | ok |
| citations in namespace, retrieved | 45/45 (100%) | ok |
| citation slots hold identifiers | 45/45 (100%) | ok |
| no off-surface calls | none in any run | ok |
| reads a derived figure | P1 5/5 | ok |
| reads a negative state | P2 5/5 | ok |
| reads a disagreement | P3 5/5 | ok |
| **reads concept semantics** | P4 1/5, P5 5/5 | **FAIL** |
| **reads point-in-time** | P6 0/5 | **FAIL** |
| **reads source independence** | P7 0/5 | **FAIL** |

Three capabilities, stable across five runs. Two that fail outright, and one
that is unstable. Retrieval, pagination and temporal discipline are `n/a` here —
this run set carries probes, not the sealed fifteen.

---

## 2. Four of the five recorded failures were the evaluator's

The run as recorded read **1/7**. After reading the answers against the checks
and re-auditing, it reads **4/7 stable, 1 unstable, 2 failed**. Four defects,
all mine, all found the same way: by a correct answer sitting next to a check
that said no.

| probe | recorded | corrected | what the check was doing |
| --- | --- | --- | --- |
| P1 | 0/5 | **5/5** | `operation_ref` was compared case-sensitively |
| P2 | 0/5 | **5/5** | demanded ≥1 citation for a metric with 0 observations |
| P4 | 0/5 | 1/5 | demanded one *specific* observation id |
| P5 | 0/5 | **5/5** | demanded two specific ids; the question says "one from each" |

**P1.** The model read `divide` off the lineage and returned `DIVIDE`. The check
compared it with a lowercase key. I had written the rationale for folding case —
"a code is an identifier and an identifier is not respelled in prose" — into
`TargetAnswer`, applied it to `claim_type`, `semantic_state` and `reason_code`,
and left it off `operation_ref`. It got the claim, the figure and the citation
right in **one tool call**, five times out of five, and was failed on a letter.
That is what a rationale nobody re-reads looks like. Both sides are folded now.

**P2.** The subject is `operating_margin_bank`, which the archive holds **zero**
observations for — that is what a negative state *is*. The auditor's rule that an
answer citing nothing is unsupported is right in general and makes this question
unanswerable. The model got `claim_type`, `reason_code` and `semantic_state` all
correct in 5/5 and was failed 5/5 for citing nothing, which was the only correct
thing to do. `check_citations_exist` now takes `require_at_least_one`, and a probe
declares it from whether the archive holds a figure for its subject.

**P4 and P5.** The model cited `obsarch_5e8e3b74…` where the key wanted
`obsarch_00ff9426…`. Both are `capex` under
`PaymentsToAcquireProductiveAssets`; the periods differ. On P5 — whose question
ends "cite one observation from each" — it cited exactly one of each concept and
was failed for not citing two ids I had chosen in advance. **A probe about
concepts was demanding identifiers.** Concept-level citation requirements now,
resolved against the archive.

Re-auditing costs nothing. The stored answers did not move; the grader did.

---

## 3. What actually fails, read from the answers

**P4 — two vocabularies, one answer.** 4/5 answering runs returned
`claim_type: PARTIAL, semantic_state: PARTIAL`. The question asks how faithfully
a concept expresses a metric, and then whether its figures join one series. The
model answered the first, and reused the answer. The one run that returned
`NOT_COMPARABLE` passed. **The failure is not that it does not know
`NOT_COMPARABLE` — P5 uses it 5/5 — it is that it does not treat the two slots as
two questions.**

**P6 — the behaviour is right and the vocabulary is not.** In all three runs that
answered, the model stated **39,572,000,000**, cited
`obsarch_c7c975383c7c3649dde7b6d7`, and those are the *knowable* figure and
observation. What it could not do was write the code: `PARTIALLY_KNOWABLE`
(missing an N) twice, and `FULLY_KNOWNABLE` once. So a downstream system reading
its `claim_type` would have mis-read a correct answer three times out of three.

That is a distinct failure mode from not understanding, and it deserves its own
name in the taxonomy: **semantics correct, code emission unreliable.** It is
also precisely the failure my own case-folding defect would have hidden — P1 was
the same thing and I called it my fault. The difference is that a typo is
recoverable and a wrong concept is not, and a consumer needs to know which it is
looking at.

**P7 — no answer, five runs out of five.** The model spent all 8 exchanges and
returned nothing. The traces show `get_validation` called four or five times
against ids it had guessed, and `query_observations` paging for the conflict.

This probe is **confounded and I should say so.** 2.6.3 established that the
archive's single `DISCREPANT` record is not discoverable by search: the
`validation_status` filter returns empty for every status, `coverage_report`
reports `CONFLICTING: 0`, and the record is reachable only through
`get_validation(observation_id)` for an id the caller must already have. So P7
asks a model to read a distinction that the surface will not let it find. It
measures findability at least as much as reading, and its 0/5 cannot be read as
a semantic verdict.

That is an **A-class finding carried forward, not a new one**, and it is the one
place where a fix belongs in ST-EVA rather than in the model or the grader.

---

## 4. A new surface finding: `as_of` is not what it is called

Found while checking that P6's answer key agreed with the surface, which it did
— after I had used the wrong parameter in the test.

`query_observations` exposes **fifteen** parameters and the tool schema
**describes four**. `as_of` and `knowable_at` are both bare names.

```
as_of="2009-07-23"        -> []            # exact match on the row's reporting instant
knowable_at="2009-07-23"  -> [1 row]       # the point-in-time filter
```

`as_of` reads as a point-in-time filter and is an exact equality test on a
per-row field. A model asking what was knowable in 2009 uses it, gets `[]`, and
cannot distinguish that from *no evidence existed* — which is the single most
expensive confusion in this interface, and the one 2.6.1 fixed when `status` was
renamed `validation_status`.

**I did not fix it before measuring.** Changing the tool surface mid-experiment
would have broken comparability with every earlier run, and it is exactly the
"teach the model the answer" move worth avoiding. P6 therefore measures the
interface **as sealed** — and the trace shows the model never used `as_of` or
`knowable_at` at all, reaching the right observation another way. So the naming
gap is real, recorded, and did not cause this round's failures. Two tests pin it,
including one that asserts the *current wrong* behaviour so that changing it has
to be deliberate.

---

## 5. Where each model stands

Not a ranking. Three models, two verdicts each, and the verdicts are not
comparable to one another because the run sets are not the same.

| | `nemotron-3-ultra-550b-a55b:free` | `space-bunny-alpha` | `qwen3:14b` (local) |
| --- | --- | --- | --- |
| runs | 5 probes + 3 full (2.6.3) | 3 screening (2.6.4) | 2, before the surface fix |
| **Evidence Consumer** | **ACCEPTED** | **REJECTED** | **REJECTED / weak** |
| **Semantic Consumer** | **NOT_YET** | **NOT REACHED** | not measured |
| fabricated identifiers | **0 of 124** | 0 of 136 | the original defect |
| semantic probes passed | 3 of 7 stable | 0 of 4 | — |
| off-surface calls | 0 | 0 | 0 |

Space Bunny's 2.6.4 result predates two of this round's probe corrections, so
**its Semantic Consumer is UNMEASURED, not zero** — and re-screening it is the
first thing the next round should do. qwen3:14b ran against a surface that has
since been corrected twice; its numbers are not a statement about the model.

**The one fact that holds across all of it: no model has ever fabricated an
observation identifier against the 2.5+ surface.** 260 citations, zero
inventions. The local model's defining failure — a correct answer next to an
invented `observation_id` — has not recurred in any cloud run.

---

## 6. The principle, written down

> **ST-EVA defines the Evidence contract. Model capability determines whether a
> consumer can satisfy it.**

The three rounds of this project are the evidence. One surface, one tool schema,
one prompt, one evaluator:

- a model can be **rejected** for reasons that have nothing to do with the data
  (unstable grounding);
- a model can be **accepted as a bounded consumer** whose failures are all in
  interpretation, and the remedy is supervision rather than a different archive;
- and a model can be **failed by the evaluator** — which happened four times here
  and once in 2.6.2 and twice in 2.6.3.

Not one of those outcomes required changing what Revenue means, what Conflict
means, or what Source means. Every fix went into the grader or the harness, and
the archive's semantics were untouched in all three rounds except for the one
genuine defect found in 2.6.3.

The corollary is the one worth stating: **do not adapt the surface until a weak
model passes.** The 2.6.3 fix made the surface *correct* and it improved every
model's behaviour immediately — 5 of 10 answers asserting a false cause became 0
of 38. Making it *teachable* would improve the numbers and destroy the thing the
numbers are for.

---

## 7. Taxonomy

| | count | |
| --- | --- | --- |
| **A** | 1 carried forward | the `DISCREPANT` record is not discoverable by search, so P7 is confounded; plus the `as_of` naming gap, newly recorded |
| **B** | 7 checks | model errors: one code reused in two slots, a misspelled code, a wrong code, a wrong claim_type, and P7's non-answers |
| **C** | **4, all corrected** | case-sensitive operation id, unsatisfiable citation rule, identifier-granularity citations in P4 and P5 |
| **D** | 0 | |
| **E** | 3 | 2 upstream `provider_overloaded` in P6, and 3 `DEGRADED` refusals in the smoke phase that preceded the runs |
| **harness** | 2 | the variance table read the *recorded* audit rather than the re-audit, so it contradicted the artifacts beside it; and a half-run criterion was marked `n/a`, discarding a probe that passed 5/5 |

**Fourteen of the twenty-one recorded failures in this round were the
evaluator's.** The model's own failures are three: it reused one code where two
were asked for, it emitted a code that was not in the vocabulary, and it could
not answer a question the surface will not let it find.

---

## 8. Reproducing

```
python openrouter_screening.py probes   --model nvidia-nemotron-3-ultra --run-label run1 --request-budget 60
python openrouter_screening.py reaudit  --model nvidia-nemotron-3-ultra --reaudit-phase probes
python openrouter_screening.py variance --model nvidia-nemotron-3-ultra --reaudit-phase probes
```

`variance` now reads the **re-audit** where one exists and records which it used,
so the table and the artifacts beside it cannot disagree. `reaudit` walks a run
series and rebuilds each answer through the full contract — its first version
copied only the four sealed keys, silently dropped every probe field, and graded
seven passing probes as failures.

525 offline tests pass. `verify_harness` unchanged: reference 0/15, each broken
target still failing only its own test. No production file touched. No
credential in any artifact.

**Requests:** 2 for the smoke, 133 across five probe runs, 3 for the refused
smoke. 45 identifiers cited, 0 fabricated, 100% in namespace and retrieved.
