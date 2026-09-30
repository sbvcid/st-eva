# 2.6.4 — Semantic Consumer Screening

Two consumer classes, a structured way to ask what evidence *means*, and one
model's series completed.

**The round's finding is the shape of the architecture, and it took a new
measurement to see it.** 2.6.3 found that a model could be perfect at finding
evidence and unable to read it. That is two facts, and the harness reported them
as one number. So:

```
Evidence Consumer  = find the evidence, cite it truthfully
Semantic Consumer  = say what the evidence means
```

Both gates are decided mechanically from a run series. Neither is a judgement
call, and no score combines them.

---

## 1. What was added

### 1.1 Semantic probes — five questions with a structured answer

The sealed fifteen ask a question and look for a right answer in prose. That
measures grounding well and understanding badly, for a reason that belongs to
the harness: the grader has to infer the claim from the wording, and *"this seems
to be saying it is not reported"* is a guess with a false-pass direction. A model
that understood a negative state perfectly and phrased it unconventionally scores
the same as one that did not understand it.

A probe states the claim as a **field**:

```json
{"claim_type": "...", "semantic_state": "...", "reason_code": "...",
 "operation_ref": "...", "stated_value": ...}
```

and the auditor compares values. No English is interpreted anywhere. `stated_value`
is coerced to a number and a code is case-folded, because a code is an identifier
and an identifier is not respelled in prose. A field that arrives as the wrong
type is **dropped, not stringified** — a model that answered `["PARTIAL","EXACT"]`
has not made a claim, and turning that into a string would produce a confident
mismatch that reads as "the model was wrong" rather than "the model did not
answer".

**Probes are experiment protocol. No production change.** A test asserts that
`claim_type`, `semantic_state`, `operation_ref` and `stated_value` appear nowhere
in `evidence_query.py` or `sqlite_archive.py`, and that the probe field set does
not appear as a group. `reason_code` is deliberately exempt and the exemption is
the point: it is the archive's own field, emitted by `coverage_report` and in
every observation's status block, so a probe asking for it is the model quoting
the archive. A name collision with a fact the archive genuinely holds is not a
leak, and a test that cannot tell the two apart gets it wrong in both directions.

**Every probe is unguessable in at least one field**, and this was the first
correction. Built naively, P5 was a two-way choice between `COMPARABLE` and
`NOT_COMPARABLE` and a coin would have beaten it. Each probe now also requires
something obtainable only by reading the archive — an operation id from the
operation registry, a reason code from the coverage report, a figure from the
lineage, or the specific observation ids of a group. A `test_unguessable_fields`
assertion fails the build if a probe has none.

| probe | correct | unguessable by |
| --- | --- | --- |
| P1 reported or derived | `DERIVED`, op `divide`, 31.42, the operand id | operation id + figure + citation |
| P2 negative state cause | the recorded state + its reason code | a 7-value external code |
| P3 what the disagreement is | `MULTIPLE_SOURCE_CONCEPTS` | 3 specific observation ids |
| P4 what PARTIAL means | `PARTIAL` + `NOT_COMPARABLE` | the concept's observation id |
| P5 two concepts, one series | `NOT_COMPARABLE` | one observation from each concept |

Every answer key is read from the archive at build time. P4 and P5 take their
comparability answer from the core registry's own `series_breaks`, because whether
a series is comparable is the registry's rule and a probe that restated it would
eventually disagree with it. A probe whose subject has disappeared is not run
rather than run with a stale key. P3's ambiguity vocabulary is **copied rather
than imported** from production, on purpose: if a probe imported the constant, a
production edit would silently rewrite the answer key and the probe would stop
measuring the model and start measuring the edit.

### 1.2 The two gates

`harness/consumer.py`. Each class has named criteria, each criterion is decided
from a run series, and a criterion the run set never exercised is reported `n/a`
and carries no weight.

Two decisions inside it, both of which were wrong first:

**A criterion is a conjunction over its tests, not a sum.** `reads_a_derived_figure`
has two ways of testing the same reading — the sealed prose test and the
structured probe — and a sum lets the easy one carry the hard one. A model that
reads a derived figure in prose 3/3 and picks the right field 1/3 would have
passed the summed version. Now every test in a criterion must independently reach
a majority of runs, the majority being derived from `run_count` rather than tuned
per criterion.

**Absence of a test is not a failed test.** A screening run carries five sealed
tests, not fifteen, and the first version of the gate reported that Space Bunny
failed point-in-time because point-in-time was never asked.

**A gate is a gate:** the evidence gate is evaluated first and the semantic
verdict is `NOT_REACHED` when it fails, because a model that invents citations may
read semantics beautifully and calling it a Semantic Consumer would say its
accuracy transfers to claims that do not exist.

### 1.3 One silent data loss, found and fixed

The probe `test_id`s contained a colon: `probe:P1_reported_or_derived`. A test id
is also a path — the runner writes `audit/<test_id>.json` and the re-audit and
variance phases find tests by globbing that directory.

On Windows a colon in a filename does not fail. `open("audit/probe:P1_x.json","w")`
raises nothing, `os.listdir` shows a zero-byte file called `probe`, and the
content goes into an NTFS alternate data stream that glob cannot see, git will not
commit, and a reviewer will never find. **Five probes' worth of audit records
vanished from runs that reported them as passing.**

Fixed three ways: the prefix is now `probe-`; `test_id_must_be_a_filename` refuses
an id containing a reserved character, at mint time rather than write time,
because by the time the write has gone wrong the run is over and nothing says so;
and all 30 lost records were read back out of the streams and re-filed under the
correct ids, with a `recovered_from` note on each. Nothing was re-run and no
model's answer was touched.

### 1.4 Two transport faults, both found by being wrong

**A gateway reports an upstream failure with whatever status it likes.** An
OpenRouter endpoint whose backing provider was degraded answered `400` with
`{"error": {"message": "Provider returned error", "provider_name": ...}}`, and a
classifier reading only the status called that a network failure — wrong twice
over, since the retry advice differs and the recorded reason becomes a claim about
the network that the response contradicts. Both entry points now consult the
body, through one function, so they cannot drift.

**A read that stalls mid-response is not a `URLError`.** `urlopen` wraps what it
can and lets the rest through; a read that stalls during `getresponse()` arrives
as a bare `TimeoutError` and ended the process, taking the run with it. A slow
provider now looks like a provider that did not answer rather than a crash, which
is one level worse than a misclassification because there is nothing left to
correct. `TimeoutError` and `OSError` are caught and classified.

A third fault is now its own signal: a 4xx naming our own request is
`request_rejected` and **not retried**, because sending it again gets the same
refusal and the cause is here rather than out there.

---

## 2. Space Bunny Alpha — `stealth/space-bunny-alpha`, 3 runs

Snapshot `ce603a5588cef067`, evaluator and prompt unchanged since 2.6.2, 8
exchanges, temperature 0. Ten tests per run: the five sealed screening tests and
the five probes.

| test | r1 | r2 | r3 | | |
| --- | :-: | :-: | :-: | --- | --- |
| T1 exact value | E | PASS | FAIL | unstable | retrieval |
| T3 pagination | FAIL | FAIL | PASS | unstable | pagination |
| T6 reported vs derived | FAIL | FAIL | FAIL | **stable fail** | |
| T8 conflict | FAIL | PASS | FAIL | unstable | |
| T13 provenance chain | FAIL | FAIL | PASS | unstable | |
| probe P1 reported/derived | FAIL | FAIL | FAIL | **stable fail** | |
| probe P2 negative state | FAIL | FAIL | FAIL | **stable fail** | |
| probe P3 disagreement meaning | PASS | FAIL | PASS | unstable | |
| probe P4 partial mapping | FAIL | FAIL | FAIL | **stable fail** | |
| probe P5 two concepts | FAIL | FAIL | FAIL | **stable fail** | |

**`stealth/space-bunny-alpha`: EVIDENCE CONSUMER REJECTED · SEMANTIC CONSUMER NOT REACHED · not a consumer**

| criterion | observed | |
| --- | --- | --- |
| uses the tool surface | 30/30 test-runs | ok |
| **no fabricated identifiers** | **136 cited, 0 the archive does not hold** | **ok** |
| citation slots hold identifiers | 4/136 not an identifier (97.1%) | ok |
| **retrieval and pagination** | T1 1/3, T3 1/3 | **FAIL** |
| **citations retrieved, in namespace** | 15/136 (89.0% clean) | **FAIL** |
| no off-surface calls | none in any run | ok |
| temporal discipline | not exercised | n/a |

The rejection is **not** fabrication. It fabricates nothing: 136 citations, every
one either a real identifier or a real line of tool output. It is rejected on
instability — it passed T1 in one run of three and T3 in one of three — and on
citation hygiene at 89%.

**And it fails every semantic probe it was asked, 0/4 stable.** Including P3,
which it passed twice: reading that two figures are two different *measures*
rather than two readings of one is a thing a model can do. It just cannot do it
reliably.

### 2.1 A false accusation, caught before it was written down

The first version of this section said Space Bunny fabricated an identifier. It
did not. Chasing the finding down:

- the auditor emits **one** check — `every cited observation exists` — for *any*
  citation that is not an observation id;
- three different faults land on it: an invented `obs_ff00…`, a real `sfid_…`
  filed in the wrong column, and a line of tool output copied into the array;
- Space Bunny did the second and the third, and none of the first.

The gate now classifies each citation against the archive and against the shapes
the archive issues, giving `fabricated` / `misfiled` / `not_an_identifier`, and
scores them as three criteria. All three verdicts are pinned by tests, and
`test_a_real_identifier_in_the_wrong_field_is_not_fabrication` exists specifically
so the mistake cannot be made a second time.

The third fault is worth naming because it is a *new* observation, not a
restatement: this model filled `evidence_refs` with
`coverage_report:AAPL -> metric 'operating_margin_bank': state NOT_APPLICABLE` —
real transcript lines, not identifiers. That is a broken citation field rather
than a false statement about the archive, and a downstream system trusting that
field cannot tell the two apart. It is the one criterion where Nemotron scored
100% and Space Bunny 97.1%.

---

## 3. Nemotron — its 2.6.3 series, through the new gate

**`nvidia/nemotron-3-ultra-550b-a55b:free` could not be run this round.** Four
attempts across roughly an hour, each stopped by the request budget after 3–4
requests with `provider_error`: `Upstream error from Nvidia: Service temporarily
overloaded` / `DEGRADED function cannot be invoked`. Attempt 1's error was
misclassified as `network` by the pre-fix classifier, which is how the fix was
found. All four are preserved under `screen2/run1-attempt*-aborted-by-provider/`,
each with its `budget.json` recording the reason and 147 of 150 requests unspent.
No provider was switched and no model was substituted, per the standing rule.

So the table below is the **2.6.3 full series** — same snapshot, same evaluator,
same tools, same prompt, three runs — put through the new gate. It is a real
series and it is the substantive Nemotron result:

| criterion | observed | |
| --- | --- | --- |
| uses the tool surface | 42/45 test-runs | ok |
| **no fabricated identifiers** | **79 cited, 0 the archive does not hold** | **ok** |
| citation slots hold identifiers | 0/79 (100%) | ok |
| citations retrieved, in namespace | 2/79 (97.5% clean) | ok |
| **retrieval and pagination** | T1, T2, T3, T14 all majority | **ok** |
| **temporal discipline** | T4 majority | **ok** |
| no off-surface calls | none in any run | ok |
| reads a derived figure | T6 0/3 | FAIL |
| reads a negative state | T9 0/3 | FAIL |
| reads a disagreement | T8 1/3 | FAIL |
| reads concept semantics | T10 1/3 | FAIL |

**`nvidia/nemotron-3-ultra-550b-a55b:free`: EVIDENCE CONSUMER ACCEPTED · SEMANTIC CONSUMER NOT_YET · bounded / supervised consumer**

**What the probes did not measure for Nemotron.** None of the five ran, so
`reads_a_disagreement`, `reads_concept_semantics` and `reads_a_negative_state`
rest on the sealed prose tests alone. P3 is the probe that matters most for the
2.6.3 surface fix — it asks whether a consumer can *read*
`MULTIPLE_SOURCE_CONCEPTS` — and for Nemotron that is **unmeasured**. The
prose answers suggest it cannot (it repeated the old false explanation in 3 of its
2.6.2 runs, and 0 of 38 after the fix), but that is inference from prose and the
probe exists precisely because prose inference is not good enough. Recorded as
unmeasured rather than as a failure.

---

## 4. Both models, one gate, no ranking

| | Space Bunny Alpha | Nemotron 3 Ultra |
| --- | --- | --- |
| runs | 3 (screen2) | 3 (full, 2.6.3) |
| tests per run | 10 | 15 |
| **fabricated identifiers** | **0 of 136** | **0 of 79** |
| citation slots clean | 97.1% | **100%** |
| citations in namespace, retrieved | 89.0% | **97.5%** |
| off-surface calls | 0 | 0 |
| retrieval / pagination | **unstable (1/3, 1/3)** | **stable, every test majority** |
| temporal discipline | not exercised | **stable** |
| semantic probes | **0 of 4 stable** | not measured |
| sealed semantic tests | 0/3 on T6, unstable T8 | 0/3 on T6, 1/3 on T8 |
| **Evidence Consumer** | **REJECTED** | **ACCEPTED** |
| **Semantic Consumer** | NOT REACHED | **NOT YET** |

**No ranking is given, and this table is not one.** The two series differ in
which tests they contain, so the pass counts are not comparable, and one model
was not re-run at all. What the table does support is a per-model statement, and
both are the same statement about different subjects: **neither model is a
Semantic Consumer, and the difference between them is entirely in the evidence
layer.** Space Bunny grounds as honestly as Nemotron — zero fabrications in 136
citations — and cannot be relied on to do it twice the same way. Nemotron can.

That is the product's own result, stated by the harness rather than by a
judgement: ST-EVA's evidence layer carries machine-verifiable provenance, and a
strong model will actually use it. **The binding constraint is the semantic
consumption layer, and it is a model property, not a surface property.**

### 4.1 Experiment philosophy, as the results now say it

```
strong model + stable grounding + semantic correctness
  -> candidate autonomous consumer

strong model + stable grounding + weak semantics
  -> bounded / supervised consumer          <- Nemotron

strong model + unstable grounding
  -> not a consumer                          <- Space Bunny

weak model
  -> rejected before the full run
```

ST-EVA defines the evidence interface; the gate decides who may read it. Nothing
in this round added a hint to the query surface to move a semantic test, and
**no new A defect was found in production** — the surface was probed five more
times, through five more questions, and answered every one of them from data the
archive already held.

---

## 5. Failure taxonomy

| | count | what |
| --- | --- | --- |
| **A** | **0 new** | the 2.6.3 ambiguity defect stays fixed; the surface answered all five probes from evidence it already held |
| **B** | 14 probes, 10 sealed | model errors: derived-vs-reported, negative states, concept fidelity, series comparability, and one citation fault the gate now names |
| **C** | 0 new | |
| **D** | 0 new | |
| **E** | 4 Nemotron attempts, 1 Space Bunny test | upstream `provider_overloaded` / `DEGRADED`; 1 Space Bunny run-1 T1 transport error |
| **harness** | 3 | colon-in-filename data loss, 400-misclassified-as-network, uncaught `TimeoutError` |

The three harness faults are the most useful output, because all three were found
by this round running rather than by reading: two by a provider misbehaving, and
one by a filename being legal on the machine that wrote it and invisible
everywhere else.

---

## 6. Reproducing

```
python openrouter_screening.py screen2  --model <m> --run-label run1 --request-budget 150
python openrouter_screening.py variance  --model <m> --reaudit-phase screen2
python openrouter_screening.py reaudit  --model <m> --reaudit-phase screen2
```

`variance` prints the per-test matrix, the per-capability rollup, the grounding
counts and both consumer verdicts with every criterion's observation next to its
threshold. It sends nothing. `reaudit` re-grades stored answers with the current
evaluator and sends nothing.

520 offline tests pass, up from 496. `verify_harness` is unchanged: the reference
target still passes all fifteen and each deliberately broken target still fails
exactly the one test it was built to fail.

**Requests this round:** 112 for Space Bunny's three runs, 13 across Nemotron's
four aborted attempts. No credential is in any artifact; a repository-wide scan
returns zero matches.
