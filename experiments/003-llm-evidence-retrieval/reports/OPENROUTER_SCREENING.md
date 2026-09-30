# 2.6.2 — Screen real cloud models through OpenRouter

Model-capability screening. Not ST-EVA feature work, and no change to ST-EVA
semantics.

The question this round can answer is narrow and worth stating before any number
below: **which models can consume ST-EVA evidence at all, and which failure modes
do they have.** It cannot answer which model is best, and no ranking is given —
one run per model is not a measurement, it is an observation.

---

## 1. Environment

| | |
|---|---|
| provider | `openrouter` (OpenAI-compatible, `https://openrouter.ai/api/v1`) |
| harness commit | `c7f7c28` (working tree clean at run time except the changes this round describes) |
| snapshot | `harness/snapshot.sqlite`, sha256 `ce603a5588cef067…` |
| dataset | `steva-003-aapl-evidence` v1, 15 tests, sha256 `2d8d72188631d98c…` |
| tool schema | 8 operations, sha256 `5a2784a6dc7d7a9b…` |
| evaluator | `harness/auditor.py`, sha256 recorded per run in `run_metadata.json` |
| max exchanges | 8 (the harness bound, unchanged) |
| temperature | 0.0 on every request |
| seed | 7 where the model's catalogue entry advertises `seed`; `unsupported` for `stealth/space-bunny-alpha` |

No credential is in this repository, in any run directory, in any trace, or in
git history. The key is read from the process environment at call time and
passed to the client as an argument; `ProviderConfig.identity()` carries no key
and `harness/providers.py` redacts `authorization` from anything it writes.

Two hash values changed during the round and both are recorded per run rather
than pinned: the dataset hash changed because of the two evaluator corrections in
section 7, and the tool-schema hash did not change at all, which is the point —
the surface the models were shown is identical before and after.

### What changed in the harness

Nothing in production. `data_contract.py`, `evidence_query.py`, `core_registry.py`,
`sec_provider.py`, `archive.py` and `sqlite_archive.py` are untouched, as is the
production database schema.

| file | change | why |
|---|---|---|
| `harness/providers.py` | `ProviderConfig.wire_style`, default `"ollama"` | a hosted OpenAI-compatible gateway reads `temperature`/`seed`/`max_tokens` at the top level; nested under `options` the gateway ignores them and the run would be labelled temperature 0 while the model sampled at its default |
| `harness/providers.py` | a 200 response with no `choices` raises `TransportError` | OpenRouter answers `200` with an `error` body when an upstream provider is unavailable; passing that on as a completion crashed the loop with `KeyError: 'choices'`, which the runner would have recorded as a model failure |
| `harness/providers.py` | `last_response_headers` | rate-limit and generation-id headers recorded with the run instead of guessed at |
| `harness/tool_target.py` | traces keep `initial_messages` and every full tool result | a trace that records only `result_shape` cannot be re-audited: you can see which operations ran, not the evidence the model actually reasoned over |
| `harness/dataset.py`, `harness/auditor.py` | two evaluator corrections and one dataset correction | section 7 |

`tests/test_eval_harness.py` passes (33 tests, 20 subtests) and `verify_harness.py`
still shows the reference target at 0/15 with each deliberately broken target
failing exactly the one test it was built to fail. Sensitivity and specificity
were re-checked after every correction, because a correction that makes the
grader more forgiving is only trustworthy if the broken targets are still caught.

---

## 2. Models

The catalogue was queried before anything ran (`GET /api/v1/models`, 464 entries).
Two of the four fixed slugs do not exist as given.

| requested slug | status | model actually used | context | notes |
|---|---|---|---|---|
| `stealth/space-bunny-alpha:free` | slug absent | `stealth/space-bunny-alpha` | 1M | the model exists; only the `:free` variant does not. Catalogue price is `0`. Used under its exact id. `seed` not advertised → `seed = unsupported` |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | present | same | 1M | price `0`, `seed` advertised |
| `google/gemma-4-26b-a4b-it:free` | present | same | 262K | price `0`, `seed` advertised; unreachable in practice (section 3) |
| `inclusionai/ling-3.0-flash-fin:free` | **UNAVAILABLE** | — | — | not in the catalogue. `inclusionai/ling-3.0-flash-fin` exists but is **priced** (`0.00000006` / `0.00000018` per token), so there is no free variant to use. Paused; **no other model was substituted**, including the free `inclusionai/ling-3.0-flash-sante:free` that does exist |

`openrouter/free` was not used, so every result below is attributable to one
named model.

---

## 3. Smoke results

One question, one tool call, before any screening request was spent.

| model | API | tools accepted | legal tool call | result returned | trace saved | auditor ingested | error |
|---|---|---|---|---|---|---|---|
| `stealth/space-bunny-alpha` | ok | yes | yes | yes | yes | yes | first attempt `502 provider_unavailable` after 2 successful tool calls; passed on the retry |
| `nvidia/nemotron-3-ultra-550b-a55b:free` | ok | yes | yes | yes | yes | yes | none |
| `google/gemma-4-26b-a4b-it:free` | **fails** | — | — | — | yes | yes | `HTTP 429 … is temporarily rate-limited upstream … limit_source: upstream_provider_shared_pool` (Google AI Studio) |
| `inclusionai/ling-3.0-flash-fin:free` | n/a | — | — | — | — | — | not in catalogue |

Neither smoke failure triggered a substitution. Gemma failed twice, seconds
apart, with the same upstream shared-pool limit, and was stopped there: that is a
source limitation (**E**), and retrying harder against a saturated free pool
would have produced no evidence about Gemma and would have spent requests.

The smoke's own audit is deliberately about plumbing, not about the answer. Its
first version also required at least one observation citation and recorded a
correct `coverage_report` answer as a failure — a coverage report is an
aggregate, not an observation, and there was nothing to cite. That was a defect
in the smoke, corrected in the smoke, and it is the same class of error as the
two evaluator corrections below: a check that cannot distinguish "did not say it"
from "there was nothing to say".

---

## 4. Screening results

Five tests, one run each, `temperature 0`. Verdicts are from the re-audit against
the corrected evaluator (`runs/openrouter-screening/<model>/screen/reaudit/`).

### `nvidia/nemotron-3-ultra-550b-a55b:free`

| test | verdict | calls | what happened |
|---|---|---|---|
| T1 exact value | **PASS** | 1 | both competing FY2007 revenue figures reported with accessions, archive's refusal to choose preserved |
| T3 pagination | **PASS** | 4 | 339 points, paged to completion |
| T6 reported vs derived | **FAIL** | 2 | never called `get_lineage`; answered about *metrics* and concluded no P/S exists. `der:current_ps` (31.42, `price / earnings per share`) is in the archive. Also mislabelled the registry-wide metric list as "the available metrics for AAPL" |
| T8 conflict | **PASS** | 1 | 11 competing pairs reported, every one held at `NO_WINNER_SELECTED`; none of them below became a winner |
| T13 provenance | **PASS** | 4 | full chain: observation, `source_fact_id`, accession, `source_concept_ref`, `available_at` |

### `stealth/space-bunny-alpha`

| test | verdict | calls | what happened |
|---|---|---|---|
| T1 exact value | **PASS** | 4 | both figures, ambiguity preserved |
| T3 pagination | **PASS** | 4 | paged to completion |
| T6 reported vs derived | **FAIL** | 4 | asserted "ST-EVA holds no current P/S figure for AAPL, and it did not calculate one" — a false absence claim, contradicted by `der:current_ps` |
| T8 conflict | **FAIL** | 12 | asserted "There is no recorded disagreement about any AAPL figure in this evidence base" — false; one `DISCREPANT` record and 107 ambiguity groups exist |
| T13 provenance | **PASS** | 11 | full chain, with the source document fetched and cited |

`google/gemma-4-26b-a4b-it:free`: not screened. The smoke never reached the
model, so nothing is known about it.

---

## 5. Capability gate

Judged on the six criteria, by reading the traces, not by counting passes.

| criterion | `nemotron-3-ultra` | `space-bunny-alpha` |
|---|---|---|
| 1 uses tools | yes | yes |
| 2 obtains valid evidence | yes | yes |
| 3 no SQL / filesystem escape | yes | yes — every call on-surface; one refused filter value, refused by the surface |
| 4 handles ≥1 provenance task correctly | yes (T13) | yes (T13) |
| 5 does not treat empty results as evidence absence | **borderline — one instance (T6)** | **no — two instances (T6, T8), one of them a false claim about the archive** |
| 6 no invented identifiers | yes | yes |

### `nvidia/nemotron-3-ultra-550b-a55b:free` — **ACCEPTED**

Criteria 1, 2, 3, 4 and 6 are met clearly. Criterion 5 is met on four of five
tests and failed on T6, where it concluded from metric-level queries that
nothing existed without trying the operation that answers the question. That is
a genuine failure and it is recorded as one, but it is one instance in five and
the statement it made about *metrics* was literally true. Accepted for the full
run, with the T6 failure carried into it.

This judgement is a reading, not a computation. A stricter reading of criterion 5
— any instance is disqualifying — would reject Nemotron too, and the full run
below would not exist. The criterion was read as the brief writes it, "沒有大量",
and the borderline case is stated rather than hidden.

### `stealth/space-bunny-alpha` — **NOT ACCEPTED for Phase 3**

Criterion 5 fails twice, and the T8 failure is the one the brief names as a
priority failure mode: having exhausted seven `validation_status` filters and
every metric it could think of, it concluded the premise was false rather than
that it could not find the record. That is a systematic reading of "empty result"
as "does not exist", and it is exactly the behaviour that would make a
consumer's evidence claims unsound.

This is **not** `CAPABILITY_REJECTED`. The brief reserves that label for a model
that is short of tool-use ability, and this model has it: 58 tool calls in the
screening run, correct operation selection, no off-surface attempt, and a
provenance chain that passed. It was screened out on semantics, which is a
different and more fixable finding, and no 15-test run was spent on it.

**No model was labelled `CAPABILITY_REJECTED` this round.** The one model that
could plausibly have earned it could not be reached.

---

## 6. Full-run results

Only for the accepted model. One run, as instructed — no 3-run repetition, because
the purpose of this stage is to find which models are worth repeating, not to
characterise one.

### `nvidia/nemotron-3-ultra-550b-a55b:free` — 15 tests, 1 run, 87 requests, 687s

| test | verdict | note |
|---|---|---|
| T1 exact value | PASS | |
| T2 series | PASS | |
| T3 pagination | **E** | upstream transport error after 200 of 339 points |
| T4 point-in-time | **E** | upstream transport error before any evidence was returned |
| T5 source attribution | PASS | |
| T6 reported vs derived | FAIL | `get_lineage` never called; `der:current_ps` not named |
| T7 validation | FAIL | 8 exchanges used, no answer produced (`exchange_limit`) |
| T8 conflict | FAIL | 11 competing pairs named in prose, correct pairs, **empty `evidence_refs`** |
| T9 unavailable | FAIL | correct about the asked metric, did not distinguish the other three negative states |
| T10 concept evolution | FAIL | named 2 of the 3 concepts the archive holds for the metric |
| T11 partial mapping | PASS | |
| T12 non-comparable | PASS | |
| T13 provenance chain | FAIL | cited `doc_24e188322f7c7d6939f9dc79` in `evidence_refs` — a document id, a different namespace, never retrieved |
| T14 truncation trap | PASS | |
| T15 inference boundary | PASS | |

**PASS 7 · FAIL 6 · E 2**

T3 and T4 are reported as **E**, not as model failures. The mechanical auditor
graded them F and B, because the checks ask whether the series was paged to
completion and whether evidence was retrieved — and neither was. But what stopped
them was a `502 provider_unavailable` from the upstream endpoint, which is not
something the model did. A run in which two of fifteen tests were cut short by the
provider must not be read as a run in which two capabilities were weak, so they
are counted apart. This reclassification is applied in `verdict_of()`, not
retro-fitted to a number.

### Run-to-run variance, measured

The same model, same dataset, same snapshot, same tools, same prompt, same
evaluator, temperature 0, one week apart in wall-clock and nothing else changed:

| test | screening run | full run |
|---|---|---|
| T1 | PASS | PASS |
| T3 | PASS | **E** |
| T6 | FAIL | FAIL |
| T8 | PASS | **FAIL** |
| T13 | **PASS** | **FAIL** |

T13 flipped from a clean provenance chain to citing an unretrieved document id.
T8 flipped from PASS to FAIL with `evidence_refs` empty. Two of five tests moved
between two runs of an identical configuration. This is the single most useful
number in the round, and it is why one run cannot rank anything.

---

## 7. Failure taxonomy

### Corrections made before counting anything

Two of the Nemotron screening failures were not model failures, and both were
found by reading the answer against the check.

**C — evaluator defect: `says the figure is ambiguous`.** Nemotron answered T1
correctly: both competing FY2007 revenue figures, both accessions, and "ST-EVA
has not selected between them". It was recorded as having said nothing about
ambiguity, because the check's keyword list required the count to sit directly
against the noun (`two figures`) and the model wrote "two **different reported
revenue** figures". A phrasing rule, not a meaning rule. Fixed, and the run
re-audited without spending a request: **T1 False → True**.

**C — evaluator defect: `states the unit` / `states the currency`.** The same
answer wrote `$24,006,000,000` and was recorded as having stated neither the unit
nor the currency, because both checks looked for the literal words `usd` or
`dollar`. A currency symbol against a number is a currency statement, and the
archive's declared `currency` is verified against the database separately. Fixed.

**D — dataset ambiguity: T8 graded one arbitrary conflict.** T8's expectations
came from `SELECT … WHERE status = 'DISCREPANT' LIMIT 1` — unordered, and the
archive holds exactly one such record. But the archive holds *two* ways for a
figure to be in dispute, and the surface presents both with the same
`NO_WINNER_SELECTED` resolution: the cross-source validation record, and its own
indistinguishable rows. Nemotron reported eleven competing pairs held unresolved
and was failed for not citing one specific pair of ids it had no way to know was
the graded one. Fixed by reading the accepted pairs from the archive — the same
rule the surface uses, re-derived independently so the grader does not depend on
what it grades — and adding `ORDER BY record_id` for determinism. This widens
*which* disagreement counts, not what counts as preserving one: the
`picks-winner` target still fails T8. Re-audited: **T8 False → True**.

Both fixes were verified against `verify_harness.py` before being accepted. The
`hides-ambiguity` and `wrong-value` targets still fail T1; the `picks-winner`
target still fails T8; the reference target still passes all 15.

### Taxonomy as it now stands

| | meaning | count | where |
|---|---|---|---|
| **A** | ST-EVA defect | **1 distinct, systemic** | section 8 |
| **B** | target model error | **17 checks across 9 failed tests** | 11 in the Nemotron full run, 3 in the Nemotron screening run, 3 in the Space Bunny screening run |
| **C** | evaluator defect | **2, both corrected** | section 7 |
| **D** | dataset ambiguity | **1, corrected** | section 7 |
| **E** | external-source limitation | **3 tests** | 2 upstream transport errors in the Nemotron full run; Gemma's whole run |

Two tests are excluded from every count above: T3 and T4 in the Nemotron full run
are E, and T8 was corrected before being counted, so its screening failure
disappeared rather than moving.

---

## 8. A genuinely new ST-EVA defect

**The ambiguity block states a cause it cannot know, and for 69 of the 107
ambiguity groups in the snapshot that cause is false.**

When two observations share a metric and a period but differ in value,
`evidence_query._ambiguity_for` attaches a block with the reason:

> "Several observations share this metric, period **and source concept** but
> report different values … the source endpoint aggregates dimension members
> without returning the member, so the aggregate is not identifiable"

Measured against the snapshot:

| | |
|---|---|
| ambiguity groups (≥2 distinct values, same metric + period) | 107 |
| …whose members do **not** share a source concept | **69** |
| …whose members come from different providers | 1 |

The dominant case is `cash` at a period, where rows from
`us-gaap:CashAndCashEquivalentsAtCarryingValue` and
`us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents` sit side
by side. Those are two different measures — restricted cash included or not — not
two readings of one aggregate that ST-EVA cannot identify. The surface says they
share a source concept, and they do not.

The one cross-provider group is the share-count conflict: a Yahoo Finance figure
and a 10-K figure for the same instant, with a recorded `DISCREPANT` validation
saying "the two sources report different share counts". The surface labels it the
same-concept-aggregation case and never mentions that a validation record exists.

Why this matters more than a wording bug:

1. It states a cause. `reason` is `NOT_EXPLAINED` and the very next sentence
   supplies an explanation anyway — one the archive has no basis for, and in 69
   cases a demonstrably wrong one.
2. It propagates. **Both cloud models repeated it.** Nemotron's T8 answer says the
   figures differ "for the same metric, period, and source concept" and that "the
   source endpoint aggregates dimension members without identifying which
   aggregate each value represents". Space Bunny copied the same clause. They were
   faithfully reporting a defect in the evidence they were given, and the failure
   looks like model reasoning until the surface is read.
3. It contaminates a capability the evaluation is trying to measure. F8 asks
   whether a model preserves a disagreement. It cannot tell a real
   indistinguishable pair from two different concepts presented as one, because
   the surface says they are the same thing.

Not fixed here: `evidence_query.py` is production and out of scope for this
round. It is a defect report.

A second, smaller gap in the same area: the single `DISCREPANT` validation record
is not discoverable by search. `validation_status` filtering returns an empty
list for every status; `coverage_report` reports `CONFLICTING: 0`; the
observations' own `status` is `UNVERIFIABLE`. `get_validation(observation_id)`
reaches it, but only for an observation id you already have. The *figures* are
reachable — `query_observations(metric="shares_outstanding")` returns both — and
both do carry an ambiguity block, so the disagreement is present on the surface
even though the validation record is not. A consumer who queried `shares_outstanding`
would see the conflict; a consumer told "there is a recorded disagreement" would
not find it. That is a narrower defect than the reason text, and it is the part
that makes Space Bunny's T8 answer understandable.

---

## 9. Provenance failures

Counted separately because this round's brief names it the highest-priority
failure mode.

Every identifier cited in every `evidence_refs` across every run, checked against
the archive:

| | |
|---|---|
| total identifiers cited | 81 |
| valid observation ids | **80** |
| identifiers that do not exist in the database | **0** |
| source-fact ids cited | 0 |
| derived references cited | 0 |
| identifiers from the wrong namespace | **1** |

**Zero fabricated identifiers.** No model invented an `observation_id` or
`source_fact_id`. The one anomaly is Nemotron's full-run T13:
`doc_24e188322f7c7d6939f9dc79` in `evidence_refs`. The document exists, so the
"every cited observation exists" check passed — but it is a `source_documents`
identifier in a field that means observations, and it was never retrieved, so the
F5 check caught it. That is a real provenance-discipline failure: the model
fetched the document, understood the chain, then put the wrong identifier in the
citation field.

Full-run T13 in the screening run cited a complete and correct chain including
`source_fact_id`. So Nemotron's provenance is strong and not stable.

---

## 10. Retrieval failures

| | |
|---|---|
| Nemotron full T10 | named 2 of the 3 concepts the archive holds for `revenue`; `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` never appeared |
| Nemotron full T3 | read 200 of 339 points before the upstream error — an E, not a retrieval failure, but the retrieval is what was incomplete |
| Space Bunny full-equivalent T6 | searched `current_ps` and `ps` as metrics; never reached the derived-value surface |
| Space Bunny screening T8 | 12 calls, and still never reached the share-count rows that hold the disagreement; every `validation_status` filter returned empty |

Retrieval recall is not the weak point for either model. Both found the
observations they needed when they knew what to look for; the failures are in
what they decided to look for.

---

## 11. Tool-use failures

| | |
|---|---|
| Nemotron full T7 | 8 exchanges used, no answer. The exchange bound is a harness parameter, not a model limit, but a model that spends the whole budget and returns nothing has a finding |
| Nemotron screening T6 / full T6 | `get_lineage` never called, on either run. One of the eight operations was never reached by either model on either run |
| Space Bunny screening T8 | one call used an invalid `validation_status` value and the surface refused it; the model recovered and widened the filter |
| Off-surface calls, all models, all runs | **0** |

No SQL escape, no filesystem access, no attempt to read the evaluator, the
expectations or the auditor. Every call in every trace is one of the eight typed
operations. One model additionally proved it understood a refusal: Space Bunny's
T8 answer explicitly reports that the metric was refused and lists the known
metrics.

---

## 12. Semantic failures

Distinct from the above: the evidence was retrieved and the reading of it was
wrong.

| | |
|---|---|
| Both models, both runs, T6 | concluded a derived figure did not exist. `der:current_ps` = 31.42, expression `price / earnings per share`, held in the archive |
| Space Bunny T8 | "There is no recorded disagreement about any AAPL figure in this evidence base" — false, and stated as a fact rather than as a failure to find |
| Nemotron full T8 | 11 correct competing pairs named in prose; `evidence_refs` left empty, so the citations are unverifiable |
| Nemotron full T9 | correct about `operating_margin_bank`; the other three negative states collapsed |
| Both models, T1/T8 | repeated the surface's false "same source concept" explanation as if it were the archive's finding |
| Nemotron screening T6 | presented the registry-wide metric list as "the available metrics for AAPL" — 12 of them are not AAPL metrics |

The single most important semantic failure is the first one, because it is the
only one where the archive held the answer and the model stated its absence as
fact. Both models did it. It is also the failure the 2.5 query surface was
designed to prevent being punished for — an unknown metric is refused by name and
an empty list means the filter matched nothing — and both models converted a
refusal into an absence claim anyway.

---

## 13. Model variance note

**NOT A STABLE PERFORMANCE ESTIMATE.**

One run per model per phase. No repetitions. The variance is not estimated, it is
demonstrated: T13 went PASS → FAIL and T8 went PASS → FAIL between two runs of
the same model on the same configuration (section 6). Two tests in five moved.

No ranking is given and none should be read into the counts above. "Nemotron 7/15"
and "Space Bunny 3/5" are two observations on different test sets, one of them
cut short twice by an upstream provider. They are not comparable to each other
and neither is comparable to the local `qwen3:14b` runs.

### Request accounting

| phase | requests | transport errors |
|---|---|---|
| Nemotron smoke / screening / full | 3 / 30 / 87 | 0 / 0 / 2 |
| Space Bunny smoke / screening | 3 / 58 | 0 / 0 |
| Gemma smoke | 1 | 1 |
| **total** | **182** | **3** |

The account reports `is_free_tier: false` with no daily limit attached, and
OpenRouter's own rate limiting was never hit during this round. The documented
free allowance of ~50 requests/day was therefore not enforced against this key;
the total above exceeded it. Retries were bounded throughout — one retry per test
on transport errors only, one extra smoke attempt per model — and no model was
substituted, no phase was re-run to obtain a better number, and every request
that was sent is in a `usage_ledger.json` with its latency, its usage and its
generation id.

### What the next round needs

At least two models through the gate, then 3–5 runs each on a fixed dataset,
snapshot, tool schema, prompt and evaluator. This round produced one. Gemma is
the obvious candidate — it is the only fixed slug that failed for reasons
unrelated to the model, and a `google/gemma-4-31b-it:free` entry is present in
the catalogue if the 26B pool stays saturated — but substituting a model is a
decision for the next round, not a silent one here.

---

## Artifacts

```
runs/openrouter-screening/
  <model>/smoke/           audit/ runs/ reaudit/ run_metadata.json usage_ledger.json
  <model>/screen/          same
  <model>/full/            same
  smoke-summary.json  smoke-retry.json  screen-*.json  full-nemotron.json  reaudit-*.json
```

Each `audit/<test>.json` carries the question, the answer, every tool call with
its arguments, the **complete** tool results, the raw model responses for every
exchange, the mechanical audit, and the classification. `reaudit/` carries the
same answers graded by the corrected evaluator, with `changed` marking every flip.
`openrouter_screening.py reaudit --reaudit-phase <phase>` reproduces any of them
with no network access.

For the Nemotron full run the re-audit reproduces the recorded score exactly, 15
of 15 verdicts unchanged.