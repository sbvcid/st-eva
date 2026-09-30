# 2.6.6 — Three consumer classes, and three axes of coverage

Two instruments, built from data already recorded. No requests were sent, no
production file was touched, and the point of both is the phase after this one.

---

## 1. The third class

2.6.5 produced a result that made a two-class gate unusable. On the point-in-time
probe the model stated the correct figure, cited the correct observation, and
then wrote `PARTIALLY_KNOWABLE` when the code was `PARTIALLY_KNOWNABLE` — three
runs out of three. It understood, and it could not encode what it understood.

Folding that into "Semantic Consumer: NOT_YET" says two things that are both
wrong: that the model cannot judge evidence, and that more archive or more
supervision over its judgements is the remedy. Neither follows. What it has is a
narrow, mechanical fault.

```
Evidence Consumer      find the data, cite it truthfully
        ↓
Semantic Consumer      does its judgement match the archive's?
        ↓
Structured Consumer    can it encode that judgement in the schema given?
```

**The split is mechanical, not read from prose.** `split_probe_outcome` decides
from the check names alone: if every meaning check passed and a code field
failed, the run was *structured*; if a meaning check failed, it was *semantic*;
if there was no answer, *tool_use*. Grading still compares values and never
infers a claim from English — the same discipline as everywhere else, and the
reason this is a classification of an already-failed test rather than a new way
of scoring one.

### What the split produces

| | |
| --- | --- |
| runs where the model **understood** the evidence | **27** |
| runs where it **also encoded it** | **21** |
| **encoding rate** | **77.8%** |
| joint rate (what a consumer experiences) | 65.6% |
| right reading, wrong code — P4 | 3× |
| right reading, wrong code — P6 | 3× |

`{read_and_encoded: 21, structured: 6, semantic: 5, no_answer: 3}`

**Six of twenty-seven correct readings were mis-encoded, and P4 and P6 account
for every one.** That is the finding the class exists to make visible: six runs
in which the model retrieved the right thing and then failed to say so in the
vocabulary it was handed. All six would have been invisible inside a single
"Semantic Consumer: NOT_YET".

`Structured Consumer: NOT_YET` at 95%, and the 95% bar is recorded as chosen
rather than derived — a code misspelled once in fifty is a reliability figure,
not a capability boundary, and a gate demanding perfection reports noise as a
finding.

---

## 2. Three axes, because "we have the data" is three different claims

```
evidence_coverage         the archive holds it
query_discoverability     a consumer can reach it without already knowing its id
semantic_interpretability a model that found it reads it correctly
```

Measured against the sealed AAPL snapshot from three sources that already exist:
what the archive holds, what the eight operations return without an identifier,
and the 2.6.5 probe runs. No requests.

### Axis 1 — evidence held

| | |
| --- | --- |
| observations | **1,925** |
| unmapped to any source concept | **2** |
| by framework | `us-gaap` 1,852 · `dei` 71 · none 2 |

Two things worth naming. **`dei` is 71 observations** — a third framework, and it
is the XBRL element taxonomy, not a second accounting framework. And
`registered_metrics_without_observations` is **not** a gap: it is the
applicability surface, and a metric the registry declares inapplicable to an
issuer's business model is *supposed* to have none. This axis exists to make
sure that distinction is measured rather than assumed.

### Axis 2 — discoverable by search

| fact class | held | discoverable | |
| --- | --- | --- | --- |
| negative states | 4 | 4 | `coverage_report` names state and reason per metric |
| ambiguity groups | 107 | 107 | `query_observations(metric)` attaches the class and its basis |
| **cross-source validation records** | **1** | **0** | nothing reaches it |
| **the conflicting observations** | **2** | **1** | only with an id the consumer does not have |

**112 of 114 facts discoverable, 98.2% — and the 2 that are not are the entire
cross-source story.** The archive holds a recorded disagreement between a filing
and a vendor figure, and no operation returns it without an observation
identifier. 2.6.5's P7 failed five runs out of five and was recorded as
confounded; this is the measurement behind that, and it is a **query-surface
gap**, not a model failure and not an evidence gap.

It is the worst of the three kinds of missing thing, and that is why it needs its
own axis: every count of *held* rows says the archive is complete, and no
consumer can find the fact anyway.

`the_conflicting_observations` reads 1 of 2 because `get_observation(id)` does
return the record's own subject. That is counted as undiscoverable on purpose —
a consumer holding that identifier has already done the work a search was for.

### Axis 3 — semantic interpretability

| | |
| --- | --- |
| probe runs | 35 |
| decided | 32 |
| **read correctly** | **27 (84.4%)** |
| encoded correctly | 21 (65.6%) |

`read_rate` above `joint_rate` is what this axis exists to make visible: two
numbers a consumer experiences identically, produced by a model whose readings
are mostly right and whose encodings are not.

---

## 3. The boundary, stated

```
Evidence Consumer       ACCEPTED     0 fabricated in 124 citations
                                    retrieval, pagination, PIT stable
                                    100% citations in namespace and retrieved
                                    0 off-surface calls

Semantic Consumer       NOT_YET      concept semantics, point-in-time,
                                    source independence
                                    3 capabilities stable at 5/5

Structured Consumer     NOT_YET      77.8% of correct readings encoded correctly
                                    6 mis-encodings, all on two probes
```

**Nemotron has demonstrated it can be an ST-EVA consumer.** Retrieval is stable,
citations are grounded, no identifier has been invented, and nothing has escaped
the surface. That question is answered and should not be reopened.

**It has not demonstrated it can be an unsupervised consumer**, and the three
failures behind that are now separated into three different problems with three
different remedies: two are its own capability, and one — P7 — is ours.

---

## 4. What this means for 2.7

The next phase is cross-framework: TSM for IFRS, NU for banking applicability.
Its question is not "can it run" — AAPL, MSFT, MU and NVDA answered that — but
whether the semantic model generalises past US-GAAP and past ordinary industrials.

**This round builds the instrument that question is measured with, and the
instrument is not the model.** The three axes are what turn `0 IFRS mappings` on
TSM from a silent zero into one of three statements:

```
ifrs-full -> 0 mappings
    is it that  evidence_coverage  is thin?       (we did not fetch IFRS revenue)
    or that     discoverability  is thin?        (we fetched it and no query returns it)
    or that     interpretability is thin?        (we serve it and nobody reads it)
```

Only the first is an ingestion problem. The second is a surface problem and the
third is a model problem, and building the wrong one because the number was
silent is how a project spends a quarter.

### The two tests, and what each should produce

**TSM / IFRS.** Build `ifrs-full` concept → same semantic metric? → mapping, and
map `EXACT` **only** where the definition is genuinely equivalent. Everything
else is `PARTIAL` or `UNRESOLVED`. The machinery already exists — the registry
carries `mapping_type` and `comparability_group`, the 2.6.3 ambiguity classifier
already reads `source_concept_ref`, and `EXACT` vs `PARTIAL` is already the
distinction P4 exists to test. What does not exist is a single IFRS concept in
the archive, and that is the finding to expect: a framework the registry has
never seen should produce *unresolved mappings and an honest zero on axis 1*,
not a special case invented to make the count look better.

**NU / banking.** The desired result is **not** a computed EBITDA:

```
EBITDA for a bank  ->  NOT_APPLICABLE
                       BUSINESS_MODEL_NOT_MEANINGFUL
```

The machinery is already there and already proven: `metric_inapplicable_in`,
`MetricDefinition.inapplicable_in`, and `operating_margin_bank` →
`NOT_APPLICABLE` in the AAPL archive right now. NU is the test of whether that
generalises to a whole business model rather than one metric, and the measure of
success is that ST-EVA **refuses** rather than that it computes.

### Not being done this round

TSM and NU ingestion is the following round's work, and this report does not
pretend to have done it. The eval snapshot holds AAPL only. Producing a real
cross-framework result needs live SEC ingestion of two issuers, an IFRS concept
path, and a banking applicability set — and the axes above are what will say
whether the result means anything once it exists.

**Semantic probes are closed.** The evaluator's correction rate in 2.6.5 was
four defects in twenty-one recorded failures, and at that ratio another probe
round measures the grader more than the model. The gate and the axes are the
instruments now; more probes are not.

---

## 5. Reproducing

```
python openrouter_screening.py variance --model nvidia-nemotron-3-ultra --reaudit-phase probes
```

Prints the per-test matrix, the per-capability rollup, the three consumer
verdicts with every criterion's observation beside its threshold, and the three
coverage axes. Sends nothing.

530 offline tests pass. `verify_harness` unchanged: reference 0/15, each broken
target still failing only its own test. No production file touched. No credential
in any artifact.
