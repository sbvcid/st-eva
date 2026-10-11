# ST-EVA Development History and Accumulated Technical Notes

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

## 0. Data contract (2.3-A) and cross-source validation (2.3-B)

The data layer is defined by
[docs/ST-EVA-2.3-A-DATA-CONTRACT.md](ST-EVA-2.3-A-DATA-CONTRACT.md).

    Provider -> Observation -> Evidence -> Validation -> Derived

`Observation` is a frozen, provider-agnostic record of one sourced value. It
carries metric, unit, currency, period_start, period_end, as_of, available_at,
provider, source_type, source_url, definition, methodology, and the raw
provider payload. `Evidence` binds an observation to an engine-facing ID.
`Validation` attaches a `ValidationStatus` to a value and can never write to
it. `Derived` values record the observations they consumed and can be
recomputed from them.

2.3-B adds the SEC as a second source for seven metrics, specified in
[docs/ST-EVA-2.3-B-SEC-VALIDATION.md](ST-EVA-2.3-B-SEC-VALIDATION.md). Its
governing rule:

> Validation is a third thing. It is not a modification of an Observation.

Neither source is authoritative. A comparison produces a `ValidationRecord`
carrying a status, the basis of the comparison, the tolerance applied, an
explanation, and references to both observations. Nothing merges, averages, or
selects a winner, and the engine does not consume the SEC value at all.

An observation enters one of three availability classes, and the archive never
moves one up: `SOURCE_DECLARED` (the source published when it became public),
`UNDECLARED` (archived, queryable, and replay-ineligible at every instant), and
`ARCHIVE_FIRST_SEEN` (eligible from the moment the archive first held it, and
labelled observational forever). The contract can only guarantee history it has
itself archived; earlier data is reconstructive only where the source retains
enough original metadata, which is why SEC filings replay and vendor
fundamentals do not.

## 0.2 Investment Context (2.3-C)

Specified in
[docs/ST-EVA-2.3-C-INVESTMENT-CONTEXT.md](ST-EVA-2.3-C-INVESTMENT-CONTEXT.md).
An opt-in `--context` flag emits the verifiable research material ST-EVA holds
about one asset at one point in time.

Every derived figure declares an operation from a versioned registry
(`operation_registry.py`) with declared arity, accepted units, output unit,
formula, parameters, and missing-value rule. An unregistered operation is a hard
error, not a skipped check, because a derivation whose formula cannot be
evaluated is a derivation whose provenance cannot be verified. A missing
operand propagates: the result is unavailable, never a substitute.

The engine's value is the authority and the registry is the check. Each derived
figure is recomputed at build time and a disagreement raises `ParityError`
rather than producing a document, so a number can never reach the document that
the engine did not produce.

The 2.2.3 CLI, JSON, and report behaviour is unchanged. The sections below
describe the analytical rules, which none of 2.3-A, 2.3-B or 2.3-C modifies.

### Roadmap

| Phase | Scope | State |
|---|---|---|
| 2.3-A | Data contract: `Observation` / `Evidence` / `Validation` / `Derived` | done |
| 2.3-B | Multi-source validation: SEC as a second source | done |
| 2.3-C | Investment Context: one agent-consumable, fully traceable document | done |
| 2.4 | Point-in-time archive and replay | done |
| 2.4.1 | Source-document capture | done |
| 2.4.2 | Input compatibility and freshness, from a six-company context audit | done |
| 2.4.3 | Series comparability, machine-readable refusals, figure traceability | done |
| 2.5 | Agent consumption experiment | experiment 001 done; cold-start 002 not started |

2.4 depends on contexts being replay-safe, which 2.3-C establishes; 2.5 tests
the claim that a formalised context leaves the remaining intelligence free to
delegate, which is only meaningful once 2.4 can replay the same question across
time.

## 0.3 Point-in-time archive (2.4)

Specified in
[docs/ST-EVA-2.4-POINT-IN-TIME-ARCHIVE-REPLAY.md](ST-EVA-2.4-POINT-IN-TIME-ARCHIVE-REPLAY.md).
An opt-in `--archive` flag persists a run's observations and context, and
`archive.replay` answers what was knowable at an earlier instant.

The archive is a **consumer** of the Data Contract behind an interface, with a
`NullArchive` for the CLI's normal path. `sqlite_archive.py` is one
implementation; the Core imports neither it nor any storage engine.

Three rules the phase enforces structurally:

    Raw observations are append-only, enforced by SQLite triggers rather than
    by convention. A restatement appends a new row in the same lineage, so a
    replay before it still shows the original.

    `retrieved_at` never substitutes for `available_at`. Retrieval is always
    populated and would make everything replayable, which is exactly why
    copying it is a fabrication.

    Replay must not fill in a missing historical world. An insufficient result
    is a successful replay; a substituted value is not.

A captured observation resolves to a specific version of a source document, not
to a URL that may serve different bytes tomorrow. `content_hash` always covers
the uncompressed payload, so an archive that keeps content and one that keeps
only references agree about which documents they contain.

## 0.4 Input compatibility, and the states that are not numbers (2.4.2)

The six-company context audit found seven material defects, all of one kind:
ST-EVA published a number, or a verdict, that its own inputs did not support.
Three rules now hold, and each is enforced where it cannot be bypassed rather
than where it can be forgotten.

**A derived value requires compatible inputs.** `unit` and `currency` are two
different axes. Two figures can both be `currency` and still be incomparable,
and a US dollar market capitalisation divided by a New Taiwan dollar revenue
yields a plausible-looking ratio that no arithmetic produces and no reader
should trust. `operation_registry.evaluate` now takes the currency axis and
refuses a binary combination whose operands declare different currencies.

**A source is not asked for what it does not say.** The vendor's balance-sheet
module states no currency; stamping the instrument's quote currency on those
figures turned an unknown into a false fact, and a false currency is worse than
a missing one because it combines silently with everything else in that
currency. Those observations now carry `currency: None` and are refused at any
derivation needing a stated currency. Observations gained a `basis` block, so a
price quoted per ADS, a filing count of ordinary shares, and accounts in a local
currency are three declared bases rather than three interchangeable numbers.

**A disagreement is a state, not a number.** Three states were added, and none
of them selects a side:

| State | When |
|---|---|
| `CONFLICTING` | both sources declare *different* bases for the same metric |
| `METHODOLOGY_MISMATCH` | one source declares its basis and the other does not, and the values differ materially. The magnitude is reported; the cause is explicitly not inferred. |
| `NO_RECENT_VALUE` | a metric's newest observation is older than its source cadence's freshness window. Retained and flagged; nothing is substituted. |

Freshness is per cadence rather than one global window. A daily quote is stale
in a week; a quarterly filing is inherently up to a quarter and a filing lag
old, and holding it to a daily window would mark every periodic source
permanently stale, which is the same as flagging nothing.

A derived figure also carries `validation_state`, so a consumer can see whether
the numbers it was computed from are the numbers a cross-source check judged.
A clean verdict on one trailing window says nothing about a figure computed from
another, and previously the document gave no way to tell the difference.

Two accounting identities are cross-checked generically — price times share
count against a reported market capitalisation — and a breach is reported under
`data_quality.identity_conflicts` with both values, the expression, the periods,
and `NO_WINNER_SELECTED`. These are properties of how a quoted price relates to
a count, not statements about any issuer, and no ticker is named in any rule.

## 0.5 What a consumption experiment found, and what it changed (2.4.3)

An experiment that asked a general-capability model to read six Investment
Contexts produced no new analysis and three defects in how the Context presents
itself. All three were about *explanation*, not about numbers: no figure the
engine produces changed.

**A derived series may only be differenced within one series key.** Two points
are comparable only when their period span, their observation type, and their
construction all match. A quarterly observation and an annual one are not two
points on a line, and differencing them measures the filing calendar rather than
the business. Where a metric's points fall into more than one key, the Context
reports `series_status: NOT_COMPARABLE` with
`series_status_reason: PERIOD_SPAN_MISMATCH` and the groups it holds, instead
of producing a change. Two versions of one period are reported separately as a
restatement pair rather than as a step.

Measured on the six experiment contexts, reported discontinuities fell from 78
to 36, and the reduction is entirely spurious ones: AAPL 21 to 5, MSFT 16 to
1, NVDA 19 to 9, MU 22 to 21. MU's remaining 21 are all *within* a single
group and are genuine reported moves, correctly left unexplained. The one real
finding in the set — a 2.94x move in one issuer's debt — survives untouched,
because it is a real discontinuity inside one comparable series.

**A refusal must carry a reason code, not only prose.** Every absent figure now
carries `reason_kind` and `reason_code` from closed vocabularies, the
`input_ref` and `input_value` responsible, and a `condition` where one applies,
with the human-readable explanation retained alongside and never alone. A
refusal that omits its cause is a guess waiting to happen, and the earlier
wording — *the engine produced no value* — did not say that the divisor was
negative, which is why a reader had to go and find it.

**A figure must be able to reach its own state.** A derived figure now carries
`state_flags` when, and only when, something about its inputs needs saying: a
stale input, an input whose source declared no publication time, or inputs no
cross-source check judged. The flags are pointers to the affected ref and to the
section holding the detail, rather than a second copy of the freshness and
validation blocks, because a duplicated fact is a fact that can disagree with
itself.

The experiment's most transferable result was not a defect. It was that **a ref
is not a verification**: a model wrote a number next to a perfectly valid ref
and the number was wrong, and only recomputing the figure from its operands
caught it. Requiring a ref prevents an unsourced claim; it does not prevent a
miscount, and any later consumer-facing workflow needs mechanical comparison
of a claim against the value its ref points to.

`context_schema_version` moves to `2.3-C.2`, a MINOR bump, because the document
shape changed. An archive written by `2.3-C.1` and replayed by this version will
report `DIVERGED`, which is the correct outcome for a changed document and not a
defect.


2.4 and 2.5 are deliberately not begun. 2.4 depends on contexts being
replay-safe, which 2.3-C establishes; 2.5 tests the claim that a formalised
context leaves the remaining intelligence free to delegate, which is only
meaningful once 2.4 can replay the same question across time.

## 0.6 What a cloud-model experiment found, and what it changed (2.6.3)

The 2.4.3 section above came from asking a model to read investment contexts.
This one came from asking a cloud model to consume evidence through the query
surface, against the sealed AAPL snapshot, with a mechanical auditor deciding
every verdict. It found one production defect, and the defect is the same *kind*
of thing 2.4.3 found: not a wrong number, a wrong **explanation offered as
evidence**.

**An ambiguity must name its cause, and the cause must come from the rows.**
`EvidenceQuery` reports, on any figure that is one of several it will not choose
between, the competing observation ids, the competing values, and
`resolution: NO_WINNER_SELECTED`. Until 2.6.3 it also returned a single sentence
for all of them: that the rows "share this metric, period and source concept" and
that "the source endpoint aggregates dimension members without returning the
member". That sentence was false for **107 of 107** ambiguity groups in the
snapshot, including the one its own docstring offered as the worked example.
Sixty-eight groups are two different US-GAAP concepts mapped to one metric
(`cash` as `CashAndCashEquivalentsAtCarryingValue` and
`CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`; `debt` as
`LongTermDebtCurrent` and `LongTermDebtNoncurrent`); thirty-eight are one concept
reported by two filings; one is a filing against a vendor quote. **Zero** are a
dimension collision, which is the only shape that sentence fits.

The cost was measurable rather than theoretical. Before the fix, five of ten
model answers asserted the dimension-aggregation mechanism as the archive's
finding. After it, none of thirty-eight did, and eight quoted the correct
classification. The models were not making the mistake; they were reporting what
the surface told them.

So the block now carries a `reason` drawn from a closed vocabulary, decided by a
pure function of the evidence gathered — `CROSS_PROVIDER_DISCREPANCY`,
`MULTIPLE_SOURCE_CONCEPTS`, `DIMENSION_COLLISION`, `MULTIPLE_FILINGS`,
`MULTIPLE_OBSERVATIONS` — together with the `basis` it was decided from, and
`same_measure_established`, which is **false** wherever the competing rows are
known to measure different things. That last field is the one that matters
downstream: two figures that measure different things are not a disagreement, and
a consumer who is not told so will pick one and report it as a fact about the
metric. Where the archive holds a recorded cross-check behind a cross-provider
pair, the record is quoted and `determination` becomes
`FROM_RECORDED_EVIDENCE` rather than a re-derivation.

`NO_WINNER_SELECTED` is unchanged, and deliberately so. The experiment showed
that softening it is how a consumer ends up asserting a winner, and the fix
changed what the archive *knows* about a disagreement, never whether it chooses.

**A derived figure must be readable from the reference that names it.**
`get_lineage("der:current_ps")` returned 31.42 only inside `chain[0]`, one level
down in a payload whose whole purpose is to answer what the figure is and how it
was made. Value, unit and expression are now at the top level beside the
operands, and `recomputation` states `recomputed_by_query: false` with
`value_source: STORED_DERIVED_VALUE` in the same payload. The value is read back
from the archive. The query layer is still not a second calculation engine, and
both halves of that are asserted.

The experiment's own result is a limit worth recording. The same model that
failed to distinguish a derived value from a reported one — three runs, three
failures — never called `get_lineage` at all, so the fix did not change its
behaviour. A missing capability in the surface and a missing capability in the
consumer look identical from the outside and need different fixes, and only the
trace tells them apart.

**A refusal is never a finding about the model, and a harness should not need a
human to know that.** `harness/budget.py` counts every request on the way out —
a refused request spends the allowance — classifies refusals by kind
(`rate_limited`, `provider_error`, `model_unavailable`, `malformed_response`,
`network`), and stops the phase rather than letting a loop decide. `provider_error`
and `rate_limited` may be retried; `model_unavailable` may not, because a
withdrawn model is not a transient condition. Three refusals of one kind with no
answer in between end the run, and the untested remainder is recorded as *not
run*, which is a different fact from *failed*. It mattered within an hour: a
three-request `503 provider_overloaded` storm cut one of three runs off at 0/15,
and without the guard that number would have been averaged into the variance
series as a model result.

## 0.7 What that experiment measured about the model (2.6.3)

Three runs of one fixed model on one fixed snapshot, dataset, tool schema, prompt
and evaluator. Recorded here because the shape is the transferable part, and
because one run is not a measurement.

| capability | three runs |
|---|---|
| evidence retrieval, pagination, temporal discipline | 15/15, stable |
| concept semantics | 6/8, one unstable |
| provenance | split — attribution stable, full chain unstable |
| conflict handling | 1/3, flips between runs |
| reported vs derived | 0/3 decided |
| negative states | 0/3 |

**Zero fabricated identifiers in 79 citations across 45 test-attempts**, and zero
off-surface tool calls. The dividing line is layer, not difficulty: everything
requiring the model to *find and cite* evidence was stable at 100%, and everything
requiring it to *classify* what the evidence means was where it failed. The
product is grounding, so the capability gate is written that way — a model with a
high pass count and a habit of inventing observation ids is worse than useless as
a consumer, because an invented citation looks checkable to whoever reads the
answer.

Seven of fifteen tests were stable across three runs, four were stable failures,
and three flip between PASS and FAIL on an identical configuration. That last
number is the argument for run series: a single run of this model is a number
with no error bar, and 9/15 and 10/15 out of the same configuration are both
consistent with the same model.

## 0.8 Two consumer classes, and what binds them (2.6.4)

2.6.3 ended with a result that one number could not express. A model retrieved
evidence, cited it, and read a series to the end — every run, no exceptions — and
the same model scored zero on telling a derived figure from a reported one and on
naming why a figure is absent. Both halves were real, stable across three runs,
and unrelated. Averaging them into `9/15` said neither.

So the consumer is assessed twice, and the two verdicts are never combined:

**Evidence Consumer** — can it find the evidence and cite it truthfully? The
question is grounding: identifiers that exist, citations that were actually
retrieved, nothing claimed that no tool returned, and a series read to the end
rather than to the first page. A model that fails here is not a consumer, and the
reason is not politeness. An invented observation id is a false statement about
the archive, and it looks checkable to whoever reads the answer, which is what
makes it worse than no citation at all.

**Semantic Consumer** — can it say what the evidence means? The question is
reading the distinctions the archive already makes: a derived figure from a
reported one, `SOURCE_DID_NOT_REPORT` from `UNAVAILABLE` from `STALE`, two
different measures from two readings of one measure, a `PARTIAL` mapping from an
`EXACT` one. Failing here is a capability ceiling, not a safety problem, and it
is addressable by supervision rather than by refusing the model.

The split decides what to do next, which is the point of it. A model that cannot
ground is rejected. A model that can ground but cannot read semantics is usable
with a second reader on the semantics — and adapting the surface until a weak
model passes is how an evidence database starts lying by omission.

Three results, all from the same measurement:

**Zero fabricated identifiers, in 215 citations, across two models and six
runs.** Seventy-nine from one, 136 from the other. That is the product's own
claim, verified by the archive rather than asserted: ST-EVA can supply
machine-verifiable provenance, and a capable model will actually use it.

**Neither model is a Semantic Consumer.** One passed a derived-figure reading in
prose three times out of three and picked the right field once out of three; the
other failed every semantic probe it was asked, four out of four, stably. **The
binding constraint is the semantic consumption layer, and it is a property of the
model, not of the surface.**

**The surface was probed five more times and answered every question from data it
already held. No new defect.** The fix in 2.6.3 and the probes are the two halves
of one check: a surface that is right is not the same as a surface a consumer can
read, and 2.6.3 could only measure the first, because the answer arrived as prose
and the grader had to infer the claim from the wording.

The measurement itself carried three findings, all of them about the harness and
all of them found by running rather than by reading:

A test id is also a path, and on Windows a colon in a filename does not fail — it
redirects the write to an NTFS alternate data stream, which glob cannot see, git
will not commit and a reviewer will never find. Five probes' worth of audit
records vanished from runs that had reported them as passing. Ids are now
filesystem-safe and a reserved character is refused at mint time, because by the
time the write has gone wrong the run is over and nothing says so.

A gateway reports an upstream failure with whatever status it likes. An endpoint
whose backing provider was degraded answered `400` with `Provider returned error`,
and a classifier reading only the status recorded a network fault — wrong twice
over, since the retry advice differs and the recorded reason becomes a claim about
the network that the response contradicts.

A read that stalls mid-response arrives as a bare `TimeoutError`, which `urlopen`
does not wrap, and it ended the process. A slow provider should look like a
provider that did not answer. It now does.

The last of these is the shape of the whole project. The failure mode is never the
number being wrong. It is the experiment reporting a fact about the model that
belongs to the harness.

## 0.9 What a semantic evaluation found, and the principle it settled (2.6.5)

The 2.6.4 round produced the finding and this one measured it. Seven semantic
probes — reported against derived, a negative state and its reason, what kind
of disagreement this is, what a `PARTIAL` mapping means, whether two concepts
are one series, what was knowable at an instant rather than what exists now, and
whether two sources corroborate independently — run five times against one
accepted model.

**Fourteen of the twenty-one recorded failures were the evaluator's.** Four
distinct defects, all found the same way: a correct answer sitting next to a
check that said no, and no time pressure to believe the check.

An operation id was compared case-sensitively, after the rationale for folding
case had been written and applied to three other fields. A probe about a metric
the archive holds no observation for required a citation, which made the correct
answer — cite nothing — unsatisfiable. Two concept probes demanded one specific
observation id each, and failed a model that cited the right concept at a
different period; on one of them the question said "cite one observation from
each" and it did exactly that.

After correction: **three capabilities stable across five runs** — telling a
derived figure from a reported one, naming a negative state and its reason, and
saying that two figures are two different measures rather than two readings of
one. That last one is the direct test of the 2.6.3 fix, and it passes 5/5.

**A new failure mode, and it needs its own name: semantics correct, code
emission unreliable.** Asked what was knowable at an instant, the model stated
the right figure, cited the right observation, three runs out of three — and
wrote `PARTIALLY_KNOWABLE` twice and `FULLY_KNOWNABLE` once. A consumer reading
its `claim_type` would mis-read a correct answer every time. That is a different
problem from not understanding, it is partly recoverable, and a gate that
reports only pass or fail cannot tell a consumer which one it is looking at.

**The seventh probe is confounded and is recorded as confounded.** The archive's
one cross-source `DISCREPANT` record is not discoverable by search — the
`validation_status` filter returns empty for every status, `coverage_report`
reports `CONFLICTING: 0`, and the record is reachable only through
`get_validation(observation_id)` for an identifier the caller must already
hold. Asking a model to read that distinction asks it to find something the
surface will not let it find, so its 0/5 measures findability at least as much
as reading. That is a query-surface gap, carried forward from 2.6.3 and not
counted against the model.

Alongside it, a new surface finding: `query_observations` exposes fifteen
parameters and the tool schema describes four, and **`as_of` is not a
point-in-time filter** — it is an exact match on a row's own reporting instant,
beside `knowable_at`, which is the point-in-time filter and has no description.
A caller asking what was knowable in 2009 uses `as_of`, gets an empty list, and
cannot tell that from *no evidence existed*. This is the same class as the
`status` to `validation_status` rename in 2.6.1: a name that has to be
disambiguated by prose is not self-describing. It was **deliberately not fixed
before measuring**, because changing the tool surface mid-experiment breaks
comparability and is the "teach the model the answer" move worth avoiding. The
trace shows the model never used either filter, so it caused none of this
round's failures — and two tests now pin the current behaviour, one of them
asserting the defect so that fixing it has to be deliberate.

### The principle this settles

> **ST-EVA defines the Evidence contract. Model capability determines whether a
> consumer can satisfy it.**

Three rounds, one surface, one tool schema, one prompt, one evaluator. A model
was rejected for reasons that had nothing to do with the data. A model was
accepted as a *bounded* consumer whose failures were all interpretive, where the
remedy is supervision rather than a different archive. A model was failed four
times by the evaluator, twice in 2.6.2, twice in 2.6.3, four times here. **Not
one outcome required changing what Revenue means, what Conflict means, or what
Source means.** Every correction went into the grader or the harness, and the
archive's semantics were untouched in all three rounds except for the one real
defect 2.6.3 found.

Across every run of the 2.5+ surface, **260 citations and zero fabricated
observation identifiers.** The local model's defining failure — a correct answer
next to an invented identifier — has not recurred in any cloud run, and the
grounding surface does its job.

The corollary is the part worth keeping: **do not adapt the surface until a weak
model passes.** The 2.6.3 fix made the surface *correct*, and every model
improved at once — five of ten answers asserting a false cause became none of
thirty-eight. Making the surface *teachable* would improve the numbers and
destroy the thing the numbers measure.

## 0.10 Three consumer classes, and three axes of coverage (2.6.6)

2.6.5 ended with a finding that a two-class gate could not hold. Asked what was
knowable at an instant, the model retrieved the correct figure, cited the correct
observation, and then wrote a code that was not in the vocabulary — three runs
out of three. It **understood and could not encode what it understood**, and
recording that as "Semantic Consumer: NOT_YET" asserts two things that are both
wrong: that the model cannot judge evidence, and that more archive or more
supervision over its judgements is the remedy.

So there are three, each answering a different question:

**Evidence Consumer** — can it find the evidence and cite it truthfully? The
question is grounding. A model that fails here is not a consumer, because an
invented identifier looks checkable to whoever reads the answer.

**Semantic Consumer** — does its *judgement* match the archive's? Credit is given
for getting the underlying fact right: the figure, the concept, the state, the
observation.

**Structured Consumer** — can it *encode* that judgement in the schema it was
given? Measured only over runs where the judgement was right, because a model
that reaches the wrong figure and also writes the wrong code has demonstrated
nothing about encoding, and counting it would dilute the class with faults it
does not have.

The split is mechanical, from the check names. Grading still compares values and
never infers a claim from English; the split classifies a run that has already
failed. The result: **27 runs where the model understood the evidence, 21 where
it also encoded it — 77.8%, with all six mis-encodings on two probes.** Six runs
in which the model retrieved the right thing and then failed to say so in the
vocabulary it was handed, and all six invisible inside a single "NOT_YET".

### Coverage is three numbers, not one

> **evidence_coverage** — the archive holds it
> **query_discoverability** — a consumer can reach it without already knowing
> its identifier
> **semantic_interpretability** — a model that found it reads it correctly

They disagree, and each disagreement has a different remedy. Missing evidence is
an ingestion problem. **Undiscoverable evidence is a surface problem and the
worst of the three**: the data is there, so every count of held rows says the
archive is complete, and no consumer can find it anyway. Unreadable evidence is
a model problem that no amount of ingestion touches.

Measured on the AAPL snapshot, the axes say:

| | |
| --- | --- |
| evidence held | 1,925 observations, 2 unmapped, `us-gaap` 1,852 / `dei` 71 |
| **discoverable by search** | **112 of 114 facts (98.2%)** |
| — negative states | 4 / 4, via `coverage_report` |
| — ambiguity groups | 107 / 107, via `query_observations` |
| — **cross-source validation records** | **0 / 1, nothing reaches it** |
| — **the conflicting observations** | **1 / 2, only with an id the consumer lacks** |
| read correctly | 27 / 32 (84.4%) |
| read *and* encoded | 21 / 32 (65.6%) |

The 2% that is not discoverable is the entire cross-source story, and it is the
measurement behind 2.6.5's P7 being recorded as confounded rather than as a model
failure. `registered_metrics_without_observations` is deliberately **not** counted
as a gap: a metric the registry declares inapplicable to an issuer's business
model is supposed to have none, and that distinction is the point of the
applicability surface.

### What this settles, and what it hands to the next phase

The evidence question is closed. Nemotron retrieves stably, cites only
identifiers that exist, reads every series to the end, and has never left the
eight typed operations — **0 fabricated identifiers in 124 citations**. It has
demonstrated it can be an ST-EVA consumer, and that question should not be
reopened. It has not demonstrated it can be an *unsupervised* consumer, and the
three failures behind that now have three different owners: two are the model's
capability, and one is the surface's.

Semantic probes are also closed. 2.6.5's correction rate was four evaluator
defects in twenty-one recorded failures, and at that ratio another probe round
measures the grader more than the model.

The next phase is cross-framework — TSM for IFRS, NU for banking applicability —
and its question is not "can it run". AAPL, MSFT, MU and NVDA answered that. It
is whether the semantic model generalises past US-GAAP and past ordinary
industrials. **These axes are the instrument for that question**, because they
turn `0 IFRS mappings` on TSM from a silent zero into one of three statements:
evidence thin, discoverability thin, or interpretability thin. Only the first is
an ingestion problem, and building the wrong one because the number was silent is
how a project spends a quarter.

The success condition for NU is that ST-EVA **refuses**: `EBITDA` for a bank is
`NOT_APPLICABLE` with `BUSINESS_MODEL_NOT_MEANINGFUL`, the way
`operating_margin_bank` already is in the AAPL archive. The measure of a banking
model is not that it computes, and a derived figure computed for a bank to fill
a gap in the schema would be precisely the failure this architecture exists to
prevent.

## 0.11 Cross-framework and applicability generalization (2.7)

The 2.6 series answered whether a language model can consume ST-EVA evidence.
It can — retrieval, pagination, temporal discipline and citation grounding are
stable, with zero fabricated identifiers in every run. It also left open the
question that matters for the archive itself rather than for a consumer: **does
the semantic model generalise past one accounting framework and one kind of
company?**

Two issuers, neither chosen for convenience. TSM files Form 20-F under Taiwan
IFRSs and reports **zero** `us-gaap` concepts. NU is classified by the SEC under
SIC 6199, Finance Services — and turned out to be an IFRS foreign private issuer
too, which means it cannot isolate the applicability question from the framework
question on its own. That is recorded rather than worked around.

### The principle this establishes

> **Framework-specific source concepts may differ; semantic metrics must remain
> framework-neutral where their definitions are genuinely equivalent.**

And, less comfortably:

> **A similar label does not establish the same metric.**

`ifrs-full:Revenue` and `us-gaap:Revenues` read alike and are not the same claim.
The IFRS element is an aggregate of ordinary-activity income that may carry
interest, dividend, royalty and grant income; the concept the metric calls
*exact* is contracts-with-customers only, which is a component of it. TSM reports
both at 2,894,307,700,000 and reports the interest, grant and dividend income as
separate concepts, so the two figures coincide in its filings. **That is a fact
about TSM and not a definition**, and a mapping that said EXACT would be
asserting a generalisation from one filer's presentation. It is PARTIAL, the
series break is recorded, and a test asserts the weaker type so a later edit
cannot promote it on the strength of the spelling.

Four IFRS concepts map EXACT, on definitions that hold in both frameworks. Five
map PARTIAL, each for a stated reason: a wider aggregate, non-controlling
interests in the total, *issued* rather than *outstanding* shares, and a `debt`
metric that no single standard concept declares in either framework — handled, in
both, by a declared composition of two components, which is structurally the same
generalisation the US-GAAP pair already used.

Concepts left unresolved are the other half of the deliverable, and one of them is
sharp: **TSM reports the same 2,894,307,700,000 under both `Revenue` and
`RevenueFromContractsWithCustomers`.** Same number, same period, one is a
component of the other. Mapping both would have raised the count and lowered the
meaning. Also unmapped: the IFRS revenue components, the continuing-operations
EPS variant, `NumberOfSharesAuthorised`, and `IssuedCapital` — which is a
currency amount, not a share count.

### Applicability was declared, and unreachable

`metric_inapplicable_in` is keyed by business model, and its own column comment
already said the right thing: *"recorded only when a business model is actually
excluded; an empty list stays empty, and never stands in for a retrieval that
found nothing."* That rule was enforceable and completely unreachable, because
**nothing in the archive said which business model an issuer was in.** The table
had a column no row could fill.

So a metric correctly declared inapplicable to a financial institution fell
through to its evidence fallback and answered

```
UNAVAILABLE / RETRIEVAL_FAILED
```

which says *our last attempt failed* about a line of business that does not have
one. This is not a missing feature. It is the collapse between applicability and
availability that the whole phase was written to prevent, arriving through a
missing wire rather than a wrong rule.

Migration 0010 adds the link — `issuer_business_model`, with a closed basis
vocabulary, so that "the filer publishes this classification" and "somebody
decided this informally" can never read the same in a row. A filer's SIC code is
part of its own submission, so the classification is the issuer's and a reader
with the same filing can check it. Migration 0011 then adds the state the
collapse was hiding behind: `NO_OBSERVATIONS`, reason `NOT_YET_COLLECTED`, for a
metric that applies and has not been collected — a fact about the archive, which
is not the same as a fact about a retrieval, and not the same as a fact about the
company.

The result for NU, derived rather than asserted:

```
gross_profit      NOT_APPLICABLE    BUSINESS_MODEL_NOT_MEANINGFUL   held 0
operating_income  NOT_APPLICABLE    BUSINESS_MODEL_NOT_MEANINGFUL   held 0
capex             NO_OBSERVATIONS   NOT_YET_COLLECTED               held 0
r_and_d           NO_OBSERVATIONS   NOT_YET_COLLECTED               held 0
revenue           SOURCE_REPORTED   SOURCE_STATED_VALUE          held 12
```

**Zero `UNAVAILABLE`, and the three states never collapse.** NU's own taxonomy
settled the question before any policy was written: it reports
`operating_income` in **zero concepts**, because a bank's income statement has
interest income and interest expense and no cost of sales, so both gross profit
and operating income are undefined for it. ST-EVA refuses, on its own definition
and a filed classification.

`EBITDA`, `enterprise_value` and `PFCF` are **not Core metrics and were not
added.** Under the rule that a metric is not created because a test asked for it,
the honest answer is that the registry does not define them and the question is
out of scope by construction. `gross_profit` and `operating_income` were the two
registered metrics that genuinely do not apply.

### A provenance gap that was not new

Phase 5 asked for the chain to resolve from a semantic metric to a filing, and
it stopped one link short for **29 of 86 accessions**. `held_filings` is written
from the submissions index, which is bounded; company facts reach much further
back, so facts were stored for accessions the index never mentioned and no
filing row was written for them. The sealed 2.6 archive has the same gap for 30
of its 74 accessions, so this was latent rather than new, and nothing about it
was specific to a framework or an issuer — it was an identity sitting in the fact
the whole time, never written down. Now zero.

### What generalised, and what did not

**Issuer-named columns: 0. Issuer tokens in the semantic modules: 0** — counted
from the schema and the module text, not from a flag, and skipping comments on
purpose, because this project records which issuer prompted which decision and a
count that included the documentation would forbid the record of why. One
registry serves two taxonomies and two business models; the sealed archive is
byte-identical; `verify_harness` is unchanged; 554 tests pass.

And the number that is the honest headline:

> **Coverage is 10 of 334 concepts for TSM — 3.0% — and 6 of 151 for NU — 4.0%.**

The framework generalised *reachability* for the concepts someone declared, and
it did not come close to generalising *collection*. "TSM revenue works" and "TSM
is covered" are different claims, and the coverage axes from 2.6.6 are what made
the difference visible instead of letting the first stand in for the second.

Which leaves the thing this phase hands to the next. The set of concepts ST-EVA
considered and **declined** currently lives in seed-file notes rather than in the
archive, so the archive can report what it holds and not what it ruled out. With
3.0% as the coverage figure, a reader has no way to tell how much of the
remainder is deliberate. The difference between "not collected" and "considered
and declined" is exactly what a coverage claim has to be honest about, and only
the first of those is currently recorded in a machine-readable place.

## 0.12 Coverage semantics: where is coverage low, and why (2.8)

2.7 ended with a number that was true and almost useless. **3.0% of TSM's
concepts** — measured against a denominator that is not a target, and
indecomposable, so it read as *ST-EVA only manages 3%* when the truth was that
nine concepts had been deliberately declined with reasons, ten were declared,
and the rest had never been asked for. Three completely different situations,
one number, no way to tell them apart.

### The universe, and the refusal to change it

Coverage is measured against **ST-EVA's own Core Metric Universe** — every active
semantic metric, and the source concepts declared to express it — and not against
a filer's full concept count.

That is a refusal rather than an oversight, and this project has now walked into
the opposite mistake twice. A figure against the source's concept count invites
someone to raise it, and **the cheapest way to raise it is to collect concepts
nobody asked for** — the exact opposite of providing necessary, trustworthy
data. The source figure is still reported, because losing it would lose a real
number; it is just not the denominator, and every ledger says so in its payload
rather than in a comment.

The filer's full concept list is also **not derivable from the archive**, since
ingestion only fetches concepts the registry maps. It is an input, and where it
is absent the ledger says so rather than concluding the filer reports nothing.

### What 3.0% means

```
TSM, against what ST-EVA promised:
     18 applicable Core metrics
      7 collected
     11 never asked for        <- a backlog, and it is knowable

TSM, against what TSM reports:
    336 concepts
     10 declared
      9 declined, with reasons
    317 not considered
```

The first is the product question and it has an answer. The second is a size,
not a score, and it is reported so that nobody has to guess at it.

Every issuer has the same **35 declared-or-declined concepts**. The semantic
layer is issuer-independent, and the differences between three companies in three
different taxonomies are entirely in what has been collected and what applies to
them.

### Two records that had to exist

`ingestion_runs` recorded what a run *did* and nothing about what it was *for*,
so "this metric has no observations" was a sentence with three meanings that all
read the same: never asked, asked and silent, asked and the rows are not here.
`ingestion_scope` is one row per metric per run. A run that returned early
because nothing was new has asked nothing and records `NOT_ATTEMPTED` — written
on every run including those that ask nothing, because an unattempted metric is
the most useful thing a coverage figure can report.

`declined_concept_mappings` turns 2.7's nine prose decisions into records with a
closed reason vocabulary: `COMPONENT_OF`, `WIDER_AGGREGATE`,
`NARROWER_AGGREGATE`, `DIFFERENT_QUANTITY`, `IDENTITY_MISMATCH`, `NOT_A_METRIC`.
The codes are the point — a component of a metric, a wider aggregate of it, a
measure of something else, a count of a different population, and a figure that
is not a measurement at all all read as "not mapped" in a flat list, and they
call for completely different responses.

Keyed on **(concept, metric considered)** because the interesting declines are
near misses, and deliberately **not per issuer**: "this element measures
continuing operations" is a fact about the element and does not become true or
false per company.

### The order of the derivation is the argument

`COLLECTED`, then `NOT_APPLICABLE`, then a decline, then what was asked, then what
was not. **The decisions are evaluated above the fetches**, which is what stops a
deliberate refusal from being reported as a gap to be filled. `NOT_YET_COLLECTED`
is the only status flagged as a backlog item.

Two statuses that are real and not hypothetical:

```
shares_outstanding  NU   DELIBERATELY_DECLINED
    both IFRS candidates rejected -- authorised shares count a different
    population, and IssuedCapital is a currency amount -- and NU reports no
    share count. A decided thing, not a gap.

debt                NU   SOURCE_SILENT
    asked, and the source had nothing under the declared borrowings elements.
    A fact about the filer, and completely different work from the eleven
    NOT_YET_COLLECTED metrics beside it.
```

### Three errors of my own, and what each showed

A decline was made to **compete** with a collection, so a metric collected
through one concept hid every decline against another. A decline is a fact about
a *concept*: AAPL's revenue is collected through US-GAAP concepts while four
IFRS revenue elements are declined, and those are framework judgements rather
than per-issuer ones. Declines are a row attribute that coexists with any
status, and become the status only when nothing is held.

`decline_concept_mapping` **skipped its own validation** — `DeclinedConcept`
checked the reason and the qualification, the writer did not. Two validation
paths is how a blank reason reaches a table whose trigger refuses one. There is
now one path.

And an archive predating the ledger would have reported every uncollected metric
as `NOT_YET_COLLECTED` — *nobody has ever looked* — about metrics it plainly
holds. It answers `UNDETERMINED`, which is the only honest thing an archive
without a scope record can say.

### What is still missing

The ledger does **not** do concept-level `UNMAPPED` matching. NU reports
`ifrs-full:Borrowings`, no mapping claims it, and the ledger does not say so.
Doing it properly means matching an inventory concept to a metric without a
mapping — which is the "similar label" problem 2.7 spent a phase refusing to
solve by name, and an `UNMAPPED` built on a name match would be worse than none.

And collection is still the bottleneck, but it is now **measurable**: the eleven
TSM backlog items and the nine for AAPL are the same list of Core metrics, so
widening collection is one decision rather than three per-issuer negotiations.

## 0.13 Core evidence collection, and the gates that are the real KPI (2.9)

The first round that fills the database rather than exploring the architecture.
2.8 said the Core promise was eighteen applicable metrics, seven collected and
eleven backlog — and two of those numbers were wrong for the same reason: **seven
of the eleven held nothing because the registry declared no concept to ask the
source about.** Ingestion cannot close a registry gap however hard it runs,
because there is nothing to ask for. So this was a registry round wearing a
collection round's clothes, and the collection followed.

The concepts were found by inventorying what the six filers **actually report**,
not by matching a name. Two Core metrics did not exist, seven had no concept, and
one had an obvious candidate that was wrong.

### The finding worth the round

**IFRS has no standard element for the diluted weighted-average share count.**

Both IFRS filers report `ifrs-full:WeightedAverageShares` and it is almost the
metric's name. It is the **basic** count. IFRS presents the basic figure as a
standard element and discloses the diluted one in the earnings-per-share note, so
there is nothing to map.

Mapping it would have given every IFRS issuer a diluted share count that is not
diluted, and a question about dilution would have been answered with the basic
number **and no error anywhere to notice it** — the values are plausible, the
label is nearly right, and the difference is one or two percent. It is declined
as `IDENTITY_MISMATCH`, and the asymmetry is now visible in the ledger:

```
weighted_average_diluted_shares
    AAPL MSFT MU  NVDA    COLLECTED
    NU   TSM             DELIBERATELY_DECLINED -- no standard element exists
```

Nine other declines exist because a name was not enough, and three of them are
the kind of error nothing downstream would catch:

- **`LiabilitiesAndStockholdersEquity` → equity is total assets.** The label
  contains "equity" because assets equal liabilities plus equity, and mapping it
  would have reported a balance sheet's largest number as shareholders' equity.
- **`EquityMethodInvestments` → equity** is an investment carrying amount, which
  a filer whose business is largely joint ventures reports as a large share of
  its balance sheet.
- **`WeightedAverageNumberDilutedSharesOutstandingAdjustment` → diluted shares**
  is the *increment* from basic to diluted, which is neither population.

### The gates, not the count

Eight per metric per issuer, 120 metric-issuers, computed from the archive by
`score_collection_gates.py`:

```
 1 definition     120/120      5 provenance     120/120
 2 mapping        120/120      6 applicability  100/120
 3 adoption       119/120      7 missingness    120/120
 4 observations    97/120      8 discoverable   120/120
```

Two of those are the ones a coverage percentage cannot see, and both are clean:
**provenance complete for every figure**, and **no metric is blankly empty**.

Gate 4's twenty-three failures are every one a metric the archive is *right* not
to have — a bank reports no capital expenditure element, an IFRS filer has no
diluted share count, and the two debt components hold nothing because the
filers demonstrably reported 90, 116 and 142 facts which the archive stores
under the composed `debt` metric. **Every backlog is now empty** across six
issuers, two taxonomies and five business models: AAPL/MSFT/MU/NVDA 7 → 18
collected, TSM 7 → 14, NU 5 → 10.

Two of those are counter-intuitive and correct. **NU reports
`ifrs-full:GrossProfit` and ST-EVA still rules the metric inapplicable to it** —
a filer tagging an element called GrossProfit does not make "revenue less cost
of revenue" meaningful for a bank, because applicability is a statement about the
metric's meaning and the element is a statement about the filer's presentation.
And **the debt components are empty because the data was collected**, under the
composition the mapping declares them a part of.

### Gate 6 found a real gap, and the gate was right to

**MSFT has no recorded business model**, so all twenty of its applicability
gates fail — not because any ruling is wrong, but because there are none. Its SIC
is 7372, major group 73, and the classification rule covers manufacturing, finance
and mining only. The safe default is what happened: an unrecognised
classification makes no ruling, every declared metric stays applicable, and the
issuer is asked about all of them.

The rule was not widened to improve the number. A services company is
classifiable and the rule should eventually say so, but **the finding is that the
rule has a hole**, and a hole a number hides is what these gates exist to surface.

### The standing order held

```
semantic correctness -> provenance -> applicability -> collection -> coverage
```

The registry was touched *before* ingesting, which is the right order, and only
because every mapping was decided against the filings and the near misses were
declined. Nine of the nineteen declines exist because a name was not enough. Had
this round raised coverage by mapping the first plausible candidate for each
unmapped metric, the number would be higher, the archive worse, and **nothing in
the eight gates would have shown it.**

### What remains

The next work is not collection. It is the two gaps the gates found: the SIC rule
has no services category, and the ledger still does no concept-level `UNMAPPED`
matching, which is why the extension taxonomies MU and NVDA report appear
nowhere. Those are filer-specific concepts, and the right answer for them is a
recorded "not a standard concept" — a decline reason the vocabulary does not
have yet.

## 0.14 Completing the coverage surface (2.10)

The two gaps 2.9's own gates reported, closed. **No collection work, and nothing
in this round changes what is collectible** — which was the constraint on it, and
which is measured below rather than asserted.

### A services business model, and the check it had to pass

Gate 6 failed for one issuer on all twenty of its metrics. Not a wrong ruling:
**no ruling**, because the filer's SIC falls outside the recognised groups and an
unrecognised classification deliberately makes none.

Adding `SERVICES` for SIC major group 70–89 is a one-line change that makes
twenty gates pass. It was made deliberately, under a stated constraint:

> **adding `SERVICES` must not make any metric more collectible.**

A business model earns a place in the vocabulary by carrying a ruling — some
metric whose meaning changes for that kind of company. Services carries none, so
nothing is excluded for it and every metric stays applicable.

And the constraint held. On the same archive rebuilt from the same filings:
applicability 100/120 → **120/120**, observations **97/120 → 97/120**, and every
collected count identical. **Twenty gates fixed and not one row of data moved.**
If the collection numbers had moved, that would have been the first thing to
check rather than a result.

### What a filer reports that the semantic layer does not model

2.8 could not answer this and 2.9 showed the answer was worth having. Across
six issuers reporting 2,836 concepts between them, the unmodelled part is
**20 concepts in four taxonomies**:

```
ffd     filing-fee disclosure -- fee amounts, offering amounts, offsets
ecd     executive compensation, pay-versus-performance
srt     supplementary narrative tagging
invest  an industry taxonomy
```

**None of them is a financial-statement metric.** No consumer asking about
revenue, assets or equity wanted any of them. So the record is a declaration
that these taxonomies are outside the layer, with the reason — not a decline per
concept, and not a coverage gap. A table rather than a name-based rule, because a
name rule has to match a concept to a metric, which is the "similar label"
problem 2.7 spent a phase refusing to solve by name; and because a taxonomy is
the unit at which the answer exists.

A filer's XBRL now splits three ways, and the third column is the only work:

| | modelled | declared-unmodelled | **unrepresented** |
| --- | --- | --- | --- |
| six issuers, 2,836 concepts | 2,816 | 20 | **0** |

That is a better answer than the question assumed. It is not a coverage hole; it
is twenty concepts about offering mechanics, executive pay and narrative
tagging, and the right response to every one is nothing.

### Two of eight gates were the whole story

Seven are now complete, and the eighth — observations, 97/120 — fails only on
metrics the archive is *right* not to have: a bank reports no capital expenditure
element, an IFRS filer has no diluted share count, and the debt components hold
nothing because their 90, 116 and 142 facts are stored under the composed
`debt` metric.

The coverage surface is complete for the Core universe. What remains is **scale**,
and the instruments for it already exist: the per-run collection chain, the
per-issuer ledger, the gate scorer across a population, and the source inventory
for the one number the archive cannot know. At ten thousand companies those four
answer *which Core metrics are thin, for which kinds of company, and why* — a
sort order for work rather than a percentage. There is no ambiguity left about
what a number means, and the remaining risk is doing a thousand companies badly
rather than getting one right. Which is the better problem, and is where this
stops.

## 0.15 Scale, and the number the whole phase turns on (2.11)

The question stopped being what ST-EVA should be. It became whether it can
accumulate twenty years of traceable evidence for a thousand companies cheaply and
incrementally **without changing what evidence means**. Seventy-five issuers, twelve
SIC strata, two accounting frameworks, every filing form the population uses.

### What a company costs, and the cost is flat

| per issuer | |
| --- | --- |
| requests | 23.4 |
| seconds | 10.8 |
| observations | 728 |
| archive size | 2.33 MB |

**6,160 filings, 54,602 observations, 174 MB, in 13.5 minutes.** The flatness is
the structural result: requests are a function of *how many filings were
accepted*, and a filing costs 0.13 seconds. A company is expensive because it has
a long history, not because it is large.

### The number the phase turns on

```
first pass    1755 requests   2,743,506 bytes   807 seconds   54,602 observations
second pass      0 requests           0 bytes     0.3 seconds         0 observations
```

**Zero, not "few."** A second pass issued no request at all, because the index is
re-read to discover new filings, nothing was accepted since, and the run therefore
asked about no concept. That is what separates "ST-EVA can ingest EDGAR" from
"ST-EVA can be *maintained* against EDGAR", and it is the ingestion ledger, held
filings and source-fact identity from 2.5 that make it zero.

Extrapolated to ten thousand: **234,000 requests once, and zero on every pass
after.** 16 hours at our self-limit, 6.5 at the SEC's ceiling, 23.3 GB, 7.3
million observations.

### The caveat that decides how much weight that carries

**23.4 requests and 2.33 MB per company is a floor, not a central estimate.** The
sample is the deepest readable history in a strided sample of 700 candidates, and
it contains no mega-cap — because ranking by raw form count *selects against*
them, a mega-cap's recent window being mostly Form 4 and Form 8-K. The
twenty-year archives live in files the submissions payload only names. The linear
*shape* extrapolates; the *constant* is what a mega-cap-weighted sample would
revise.

### Every failure classified, which was the acceptance criterion

70 of 75 issuers `COLLECTED`, 3 `SOURCE_SILENT`, 2 `NOT_ATTEMPTED`, **0
unclassified**. Of 1,500 metric slots, 109 classified failures — every one
`SOURCE_SILENT` or `NOT_ATTEMPTED`, which are facts about the filer — and zero
unclassified. `PARSER_FAILURE` and `FILING_UNSUPPORTED` are both zero, and that
is a result: those two exist because a form the pipeline cannot handle and a
document that will not parse look identical in a count and call for opposite
responses.

One behaviour changed because it was wrong at population scale: **an unresolvable
ticker used to raise, and a raise ends a run.** One bad name on issuer three
leaves ninety-seven unclassified. It now returns `ISSUER_UNRESOLVED` and
continues; the sealed test's actual claim, that such a ticker ingests nothing, is
unchanged and still asserted.

### A ticker is not an issuer

Found at issuer thirty: a preferred share and its common mapped to one CIK and
`record_asset` refused the second. The UNIQUE constraint is right, so the fix went
into the caller and a lookup — the sample deduplicates by CIK, and
`asset_id_for_cik()` resolves an issuer held under a different ticker. It matters
for the cost model: EDGAR lists **10,431 tickers** for far fewer companies, so
per-company cost is understated by however many share classes a company trades.

### Two methods, one removed

The population is **strided, not prefixed**: the first version took the first 700
alphabetically and produced 73 issuers all beginning with A, mostly warrants, not
one anybody would name. And forms are **derived from each issuer's own
submission history**, because assuming 10-K/10-Q reports every foreign private
issuer as `SOURCE_SILENT` — a fact about our request dressed as a fact about the
filer.

A reported number was also **removed rather than corrected**:
`deduplication_ratio: 0.157` divided gzipped wire bytes by decompressed
retained bytes — two different units, producing a confident category error. What
is reported instead is **requests per unique document: 2.48**, which is
meaningful and says deduplication is already doing most of its work.

### What is not settled

**The archive path is documented, not exercised.** At 234,000 requests the SEC's
own guidance is that bulk archives are the right mechanism, and ST-EVA's 2.5
identity model is what would let a bulk bootstrap reconcile with an incremental
one — but **the reconciliation itself is untested**, and it is the single thing
between this sample and a ten-thousand-issuer corpus. That is the next piece of
work, ahead of a mega-cap-weighted resample and well ahead of 1,000.

The risk at scale is no longer semantic. There is no ambiguity left about what a
number means.

## 0.16 Bulk bootstrap, reconciled (2.12)

2.11 measured the incremental path at 23.4 requests per company with a second
pass at zero, said that at 234,000 requests the SEC's own guidance is that bulk
archives are the right mechanism, and said the reconciliation between the two was
**documented but never exercised**. This is that exercise, and the result is
better than a match.

**7,956 observations, 7,956 matched, zero divergent values, zero one-sided.**

### The abstraction held, and that is the finding

A bulk source needs **no second ingestion path**, and that was verified before any
code was written: a `companyconcept` payload is *exactly* a `companyfacts` slice
plus four envelope fields, with **byte-identical fact rows** (117 = 117). So the
bulk source is thin by construction, and the six-member provider interface
`Ingestor` uses is satisfied by both. Had the bulk path needed its own ingestor,
the two archives would have been different things sharing a name and
reconciling them would have proved nothing.

### What differs, and why it is not a disagreement

**All 7,956 observations differ in `document_id` and in nothing else.** The API
path reads a fact from that issuer's `companyconcept` document; the bulk path
reads the same fact from the `companyfacts` document. Both are honest, and they
are not the same bytes.

Which is exactly why provenance is classified separately. **An archive rebuilt
from a different source would otherwise look like it disagreed with itself**, and
a diff reporting 7,956 differences would train a reader to ignore diffs.

### The economics, now measured rather than asserted

**23.4 requests per company becomes one document per company.** Twelve issuers in
19.2 seconds with **zero network requests**. The 234,000-request bootstrap of
2.11 becomes 10,000 documents.

### Two things `companyfacts` does not carry

**No SIC**, so an issuer classified from bulk alone is unclassified and every
declared metric stays applicable — the safe default, and the same position 2.10
measured for a filer whose SIC major group the rule does not recognise. The source
reports `submissions_available: false` so a caller can tell *why* no ruling was
made rather than inferring it from an empty metric.

**No submissions index**, so the filing index is derived from the facts: every
accession that contributed a fact becomes an accepted filing. Narrower than the
API path's, and better for bootstrap, because every entry is a filing that
actually carries evidence.

### A bug this round refused to commit

The first bulk source resolved a ticker by matching the company name. That is
**exactly the guess the API provider explicitly refuses to make** — it resolved 2
of 12 issuers, both accidentally, and would have attached filings to the wrong
company. A bulk archive is keyed by CIK and says nothing about tickers, so the
mapping comes from a `tickers.json` written beside the documents, and an unmapped
ticker returns `None` — the already-classified `ISSUER_UNRESOLVED` rather than a
guess.

Had the reconciliation passed with that in place, it would have compared two wrong
things consistently.

### What is now settled, and what is not

A ten-thousand-issuer corpus has **two working routes** that agree: bootstrap by
bulk archive at one document per issuer and zero requests, and incremental at
zero requests when nothing is new — the 2.11 second pass was exactly that.

Still not settled: the per-company **constant** remains a floor, for the reason
2.11 gave and this round did not change. And the bulk archive itself has not been
downloaded — this exercises the *interface* one is read through, per-issuer
documents fetched individually, because a delivery format is not where the
semantic risk was. What is untested is reconciling a bulk bootstrap into an
archive an incremental run has already touched, where the incremental run may hold
observations the bulk payload predates. That is a question about append-only
evidence, and it is now a small question rather than an unknown one.

## 0.17 Mixed-source bootstrap, and the rule it produced (2.13)

2.12 proved the two delivery paths agree when one is the only source, which is
the easy direction: there was nothing to overwrite. 2.13 ran the hard one — a bulk
bootstrap into an archive an incremental run had already built — with two
asymmetries created from real data: the incremental archive was built at a
narrower Core metric scope, and the bulk payload had each issuer's most recent
accessions **removed from it**, which is what a nightly archive built before those
filings landed looks like. Two issuers were in the bulk set and not the
incremental set, so bulk-only evidence was genuine.

### Every irreversibility claim, measured

bulk-only evidence added · already-shared evidence duplicated **0** · incremental-
new evidence preserved · any existing observation **changed 0, removed 0** ·
**4,002 of 4,002 survived three steps with identity stable, 0 lost** · `UPDATE`
**refused: observations are append-only** · `DELETE` **refused: observations are
append-only**.

The append-only guarantee was **attempted, not assumed** — a real `UPDATE` and a
real `DELETE` against a real row, recorded as refused. And duplication is measured
on *identity* rather than on row count, because a second row for the same
evidence would look like a successful addition to any fingerprint.

### The finding: neither route can widen scope once filings are held

```
fresh archive, full Core scope, one filer      18 metrics
narrow scope first, then bulk at full scope     8 metrics
then incremental at full scope                  8 metrics
```

Ten Core metrics exist for that filer, the registry has concepts for them, and
**neither later route fetched them.** `ingest()` returns as soon as every filing
in the index is already held — *before* the metric loop. A source asked about an
issuer with nothing new to learn is asked about nothing at all.

That guard is the property 2.11 measured as its best result. It is also the thing
that blocks a legitimate request, and the two are the same code.

So the architecture is sharper than "bulk is cheaper":

> **bulk must bootstrap a fresh archive at the full Core scope. Incremental is
> for new filings only. A change to the Core metric set is a re-bootstrap, not an
> incremental run** — and a coverage report must distinguish the two, or it reads
> "18 metrics" and "8 metrics" as the same kind of absence.

### A bug this round nearly reported as a finding

Step 2 added nothing and finished in 0.2 seconds, which looks like "the merge is a
no-op, and therefore safe". It was not a merge: the trimmed payload directory
carried an **empty** `tickers.json`, so the bulk source resolved no issuer and
ingested no issuer. **An empty map and an empty archive look identical from
outside**, and the "no errors" output said nothing.

It was visible only because a merge that adds nothing immediately after one that
added 5,998 is arithmetically impossible, and the steps were printed side by side.
The generalisation is the one worth keeping: **a merge test that cannot fail is
not a test**, and here what made it un-failable was an input that resolved to
nothing.

### What is now settled

There is no untested step left between this and a corpus of thousands. The
interface, the path reconciliation, the merge, the irreversibility of
incremental → bulk → incremental, the append-only guarantee, and the scope rule
have all been measured on real filings. What remains is arithmetic and an
operations decision: how many companies, which Core metrics, how often to run,
and where the boundary of free public data sits.

## 0.18 Full Core scope, bulk, and the availability contract (2.14)

2.13 produced a rule rather than a bug — bulk must bootstrap a fresh archive at
the full Core scope, and a change to the Core metric set is a re-bootstrap. That
rule had never been *used*, because the full Core scope has only ever been run
over **six** issuers through the API path, while the one population-scale
archive holds 54,602 observations over 75 issuers and **eight** of the twenty
seeded metrics. The 8-metric path had been shown to scale; the 20-metric path
had been shown to work on six filers; the two had never met.

This is that meeting, offline by construction: the six `companyfacts` documents
2.10 already fetched, a fresh archive, the twenty Core metrics, zero network,
and a point-in-time safety check against the API route's real acceptance
instants.

```
scope confirmed    20 Core metrics, the 8-metric slice is a strict subset, and
                   the registry seed declares exactly the same 20
bootstrap          6 issuers  17,043 obs  0 requests  52.6s  57.5 MB
reconciliation     17,043 shared source_fact_id, 0 one-sided, 0 duplicates
                   0 divergence in value, unit, period, taxonomy, concept,
                     accession, form, contract id, definition, methodology
pit safety         0 declared values promoted to an instant
                   0 of 8,218 facts eligible before EDGAR published them
gates              7 of 8 identical; applicability 0/120 against 120/120
```

### The scope is asserted, not passed

There are three metric-set definitions in the repository and they do not agree:
`sec_ingest.DEFAULT_METRICS` is 8, `build_crossframework_snapshot.ALL_METRICS`
is 20, `merge_sources.FULL_CORE_METRICS` is 20 in a different order. The script
imports all three, checks the two twenty-metric sets are one set, checks the
seed declares exactly that, and refuses to run otherwise — because a run that
quietly used eight looks identical to a twenty-metric run that collected
nothing, which is the shape of the empty-`tickers.json` failure 2.13 caught.
The guard fired on first contact, against a registry that had not been seeded.

### Every yield is identical

Eighteen of the twenty metrics yield; the two debt components yield nothing
because they are the declared composition of `debt`, and the filers reported 90,
116 and 142 facts held under it. **Every per-metric and per-issuer total matches
the API-built reference exactly.** The 8-metric slice and the 20-metric set are
not two amounts of collection — they are the same eight plus twelve.

| per issuer | 8-metric slice | **20-metric, bulk** |
| --- | --- | --- |
| requests | 23.4 | **0** |
| seconds | 10.8 | **8.76** |
| observations | 728 | **2,840** |
| archive | 2.33 MB | **9.58 MB** |

Ten thousand issuers: zero requests, 24.3 hours, 28.4 M observations, 95.8 GB —
of which 5% is document payload and 95% is rows and indexes. The no-mega-cap
caveat from 2.11 still stands, so the constant is still a floor.

### `observation_id` is not a cross-archive key

Found rather than assumed. `record_observation` re-keys whatever contract id it
is handed, so both archives store an archive-assigned `obsarch_<hash>` and
disagree on all 17,043 values of it. `source_fact_id` is the route-independent
identity and `contract_id` the route-independent string, and both match
everywhere.

**`observation_id` is assigned by the archive holding it and is not a global
identity.** A consumer that stores one cannot use it against a rebuilt corpus.

### The availability contract, which already existed

`AvailabilityBasis.FILED_AS_OF_DATE` has been in the vocabulary since the
vocabulary was written — "a provable date whose time of day is not published" —
`sec_provider._availability` already emitted it, `archive.DECLARED_BASES`
already listed it, and `tests/test_ingestion_aapl.py::test_15` already asserts
that ingestion produces `ACCEPTANCE_DATETIME` or `FILED_AS_OF_DATE`. **That test
is gated on `ST_EVA_LIVE=1`, so it does not run.** The only statement of the
availability contract in the suite was one nobody executes.

The ingestor decided the basis by asking whether the string contained a `T`, and
the two delivery routes therefore disagreed on 17,043 of 17,043 rows while each
was right about which basis it meant:

```
SEC API path   filed date -> "2015-10-28T00:00:00+00:00"  ACCEPTANCE_DATETIME
bulk path      filed date -> "2015-10-28"                UNDECLARED
```

Because `replay_eligible_from` is the point-in-time boundary, the first of those
made **6,508 of 17,043 facts replayable from a moment before the filer published
them**: 6,443 same-day rows treated as midnight against a real 20:31 acceptance,
and 65 where EDGAR's filed date trails its acceptance instant by a day.

### The rule

One sentence, uniform across both routes, and never "API exact / bulk
approximate":

> **ST-EVA does not raise date-precision information to an exact timestamp.**

```
source declares precision
        ↓
availability representation, at that precision
        ↓
point-in-time eligibility, from the declared basis
```

| what the source published | value stored | basis | replayable from |
| --- | --- | --- | --- |
| an instant | the instant | `ACCEPTANCE_DATETIME` | that instant |
| a date | **the date, no time** | `FILED_AS_OF_DATE` | after the declared day, plus a one-day allowance |
| nothing | none | `UNDECLARED` | never |

A filing index declares its precision per entry. An index that carries a value
without declaring its precision is read as an instant, because a source that
puts a time in the field is asserting a time; an index that declares an unknown
precision is refused. The declaration is preserved in the observation's `raw`
block, so a consumer reads the precision rather than re-deriving it from a
string — which is the mistake this corrects.

`DECLARED_DATE_LAG_DAYS = 1` is the allowance for a declared date that trails
the acceptance instant, measured on the 65 rows where EDGAR's own two dates
disagree by a day (MU, filed-as-of 2020-06-29, accepted 2020-06-30T16:12:44Z). A
fact known only by a declared date 2020-06-29 is eligible from 2020-07-01. It is
a measured property of the source, not a precision the source states, and it is
the one place that has to move if the SEC ever disagrees by more.

### Two things the fix exposed

**The bulk path was producing contract-invalid observations.** The contract
validator escalates `MISSING_METADATA` when `available_at` is set while the
basis is `UNDECLARED` — which the bulk route did on 100% of rows. The validator
already knew; the ingestion path never called it.

**The two point-in-time implementations gave different answers.** The SQL
selector compared stored strings, where a bare date cutoff sorts before every
instant of that day, so "as of 2026-03-05" was read as midnight, while the
in-memory selector compares dates and read it as the whole day. A cutoff is now
read through `point_in_time_cutoff`, and an unreadable one returns nothing
rather than everything.

### The residual divergence is not one thing

"17,043 divergent" against the pre-fix reference is not an actionable number.
Split by cause: **8,825** is the reference holding the old code's midnight
fabrication, and **8,218** is the API route holding a real EDGAR acceptance
instant that `companyfacts` cannot supply. Neither is a semantic fork.

### The missing `submissions` payload costs a refusal, not collection

Six of eight gates were identical, including the identical nine failing
observation gates. `applicability` reads 0/120 because `companyfacts` carries no
SIC, so no business model is recorded and the rule deliberately makes no ruling.
But the archive holds the same facts:

```
                        bulk (no rulings)      api (SIC from submissions)
NU gross_profit         COLLECTED, 12 facts    NOT_APPLICABLE, 12 facts held
NU operating_income     DELIBERATELY_DECLINED  NOT_APPLICABLE, 0 facts
```

The API-built archive **already holds twelve `ifrs-full:GrossProfit` facts for a
bank and declines to count them.** So a bulk-only corpus does not fill with
`SOURCE_SILENT` noise, because ingestion never filtered on applicability. The
risk runs the other way: a bank reports a collected gross profit.

`adoption` now reads 120/120 on both sides. The API archive's 119/120 was a
scoring defect: `score_collection_gates.py` omitted `NOT_APPLICABLE` from the
statuses that satisfy the gate, so a correct applicability ruling failed the gate
for having been recorded.

### Fixed, and what is left

Fixed: the bulk index's declared precision; the ingestor's basis and its
promotion of a date to a timestamp; the adoption gate. Added: 34 offline tests
in `tests/test_availability_precision.py`, which is the version of
`test_15` that actually runs.

Recorded, not fixed, and non-blocking: `sec_ingest._store_document` hardcodes
the document URI to `data.sec.gov/api/xbrl/companyconcept/`, so a bulk-built
archive names a URL whose bytes are not the bytes stored, overwriting the honest
`bulk://companyfacts/...` the bulk source set. `provider` is recorded correctly,
so the row is not wholly false, and it does not change when anything was
knowable.

Also introduced and caught in this round: one lost indentation level in the
bulk index collapsed 72 entries to 50, and **nothing failed** — the
observations were byte-identical, because a fact's own `filed` date supplies the
same answer when the index entry is missing. Only `filings_ingested` moved, 69 to
48. It is now guarded by a test asserting one index entry per accession, which
is the shape that collapsed.

### Unresolved, and not a code question

Whether a bulk bootstrap ships with `submissions`, which decides whether a public
corpus has any inapplicability ruling at all; whether `ACCEPTANCE_DATETIME` may
ever be claimed for a filed-date fallback, since every archive built before this
round labels 8,825 rows that way and none is rewritten; whether the one-day
allowance belongs in the contract or should be measured per source; and the
corpus-shape decision now that 95.8 GB is measured rather than extrapolated.

### The next experiment

Full-scope bulk bootstrap over the twelve `harness/bulkfacts/` issuers,
reconciled against the 75-issuer archive, with the point-in-time safety check
running on the result. Twelve is a strided SIC sample rather than six
hand-picked filers, all twelve are already held in the 75-issuer archive, and it
is still zero network. It answers the question 2.10 actually left open and
nothing since has widened: which Core metrics get thin, for which kinds of
company, and why. It does not revise the cost constant and does not test the
zip; those stay where 2.12 left them.
## 0.19 Full Core scope across twelve issuers, and the shape of coverage (2.15)

2.14 closed "can the bulk path reproduce twenty Core metrics from evidence the
API path already collected" — yes, exactly, on 17,043 of 17,043 facts. This asks
the question 2.10 left open and nothing since has widened: when the full
twenty-metric scope moves from six hand-picked filers to a different population,
which metrics get thin, and is that the metric's fault or the filer's.

Twelve issuers from `harness/bulkfacts/`, the same bulk path, the same twenty
metrics, zero network, point-in-time safety check running on the result.

```
bootstrap          12 issuers  22,482 obs  0 requests  71.8s  76.3 MB
completeness       481 filings  233 documents  22,482 observations, all distinct,
                   0 duplicates, 0 without an accession, 0 without a document
reconciliation     9,390 shared identity, divergent on availability only
                   13,092 only-in-bulk      -> outside the reference's metric scope
                   45,212 only-in-reference -> issuers this run did not cover
                   0 unexplained rows
pit safety         0 promoted to an instant, 0 of 8,603 eligible too early
gates              7 of 8 at 240/240; applicability 0/240 (no SIC, as expected)
```

### The unit of report is a cell, and the first ratio was wrong

Averaging over metrics and issuers together is the operation that hides both
effects, so the unit is a cell: 20 x 12 = 240, each carrying the ledger's status,
the observation count, and a ratio.

Scoring each metric against every instant the archive knows made twelve of twenty
metrics look thin. It was an artefact of the denominator. RBC holds 152 distinct
instants, but `Assets` spans 68, `Cash` 77 and `Equity` 73, and **their union is
86** — the remaining ~66 come from a `dei` cover-page concept and two alternate
cash/equity tags, each with its own history. A metric scored 0.45 against a union
no single concept spans.

The obvious explanation was also wrong. Reporting cadence — concepts appearing
only at annual or only at quarterly dates — is falsified in the opposite
direction: annual-only instants are the ones *most* likely to be missing.

The denominator that answers the operational question does not depend on which
concepts happen to be in the archive:

```
filing_ratio = periods of this metric that hold it
             / filings in which this filer reported anything we hold
```

Both denominators are reported, because a ratio without its denominator is not a
measurement.

### The twenty-metric scope is not thin

Seventeen of the eighteen metrics that hold anything sit at a median filing ratio
of 1.0 or above — every filing a filer made, the metric is in it, often more than
once, because a 10-K reports the prior year-end as a comparative, which is a real
fact at a real date.

Two are genuinely thin, and both are **decomposition questions rather than
collection failures**: `debt` at 0.34 (7 of 12 collected, 5 `SOURCE_SILENT`,
because no single concept declares total debt so the registry maps
`LongTermDebtCurrent` / `LongTermDebtNoncurrent` as `PARTIAL` components), and
`interest_expense` at 0.66 (9 collected, 3 declined, because filers tag
`InterestIncomeExpenseNet` or `InterestAndDebtExpense`).

### The finding the matrix was built to find

**The two debt components hold nothing, and the ledger says the source is silent
when the source answered 423 times.**

`us-gaap:LongTermDebtCurrent` carries two mappings: `debt` as `PARTIAL` ("a
component of total debt, never the total on its own") and
`long_term_debt_current` as `EXACT`. Ingestion stores the fact under `debt` — 423
observations across 222 filings, and 310 of the non-current tag across 171. The
component metrics hold zero by construction.

So the ledger reports `MAPPED_NO_CURRENT_OBSERVATION` on seven issuers and
`SOURCE_SILENT` on five. `SOURCE_SILENT` is **affirmatively wrong**: it says the
filer was asked and had nothing, and the filer answered with tagged facts. The
two statuses also disagree with each other about the same fact, which is a
granularity defect independent of the misreading.

A decision, not a patch. If the composition is the point, the vocabulary is
missing a member meaning *held under a parent composition* and `SOURCE_SILENT`
should be reserved for a filer that reported nothing. If the components should be
addressable, a fact is stored under every mapping that accepts it — which is a
duplication decision, because 2.5's boundary is *derived != reported* and a stored
observation is a reported fact. Neither is decided here; what is decided is that
the current status is a misreading rather than an absence.

### The two axes cannot be separated

**All twelve issuers are `MANUFACTURING`** — SIC 3510, 3530, 3562, 3564, 3569
x2, 3576, 3577, 3663, 3672, 3674, 3679, all from the 35xx/36xx industrial
range. So "is the thinness the metric's fault or the company type's" is **not
answerable from this sample**, and the instrument reports the degeneracy rather
than hiding it.

What the sample does contain is a filer-type mix 2.10 did not test: three foreign
private issuers filing 20-F and never 10-K. The form policy is read from each
issuer's own recorded forms rather than hand-written, so a coverage difference
could not be a form-policy artefact — a 10-K/10-Q policy would have reported those
three as `SOURCE_SILENT` when the real answer is that nobody asked.

### Two gaps in the operational machinery

**The 75-issuer population archive has never been gated.** `ingest_universe.py`
writes no collection chains, so the largest population archive has never been
through the instrument that found the SIC hole and the unmodelled taxonomies.

**The gate tool crashes instead of skipping.** `score_collection_gates.py:76`
does `.fetchone()[0]` with no guard, so a chain naming a ticker the archive does
not hold raises `TypeError` and the run dies. Same failure shape as 2.13's empty
map: a broken input and an empty input look alike. Recorded, not fixed.

### The next step, and the constraint that arrives with it

**The experiment sequence has run out of offline payload.** The repository holds
18 `companyfacts` documents: 6 cross-framework and 12 population. Widening the
population along the axis this sample is degenerate on needs documents that are
not on disk.

So the next input is a **fetch**, with the population selected **by business
model** rather than by convenience — the 75-issuer archive already records the
SIC-derived classification for all 75, and the twelve on disk were all one type.
The sample must contain at least one filer from each model the registry can
classify differently, or the metric-versus-type question stays unanswerable.

Before that fetch, two cheap repairs, neither semantic: write collection chains
for a population archive, and make the gate tool skip an unknown ticker with a
reason.
## 0.20 The 75-issuer archive, gated for the first time (2.16)

2.15 left two instrumentation gaps, both blocking the next question: the
75-issuer population archive had never been gated, because `ingest_universe.py`
writes no collection chains; and `score_collection_gates.py:76` did
`.fetchone()[0]` with no guard, so a chain naming a ticker the archive does not
hold raised `TypeError` and killed the run.

Both fixed, and the gates have now run over **1,500 metric-issuers**.

```
75 issuers  1,500 metric-issuers  0 skipped
   definition / mapping / adoption / provenance / missingness / discoverable
                                          1500/1500
   applicability                          1280/1500
   observations                            491/1500
```

### Chains are recoverable; run logs are not

`derive_collection_chains.py` derives one chain per issuer from an archive that
has none, because `coverage_semantics.collection_chain` is a pure function of the
archive and the registry. What it does **not** reconstruct is transport
accounting -- request counts, concept fetches, whether a run returned early --
because those are properties of a run rather than of stored evidence, and the
output says so instead of reporting zeros that look measured.

The archive is opened **read-only** (`file:...?mode=ro`). `Ingestor.collection_chain`
calls `record_asset` on its way to the ledger and would create an asset row for an
unknown ticker, so a measurement that can alter its subject is prevented rather
than promised against.

### A broken input and an empty input now look different

A chain naming an unknown ticker is a skip with a reason, in stdout and in the
JSON. The universe line is counted rather than typed in -- it read
`6 x 20 = 120 metric-issuers` with both numbers hardcoded, which described one run
rather than measuring whatever ran. The JSON shape changed with it, to
`{issuers, measured, skipped}`, because a run's universe and its skips are part of
its result; `fullscope_bulk.py` reads both shapes.

### `observations` 491/1500 is a scope measure wearing a quality name

The gate asserts `observations > 0`. That is the right assertion and an unreadable
one, and over an 8-metric archive scored against a 20-metric universe it produces
a 33% pass rate that is almost entirely scope and decisions. The tool now splits
it by the ledger's own status, reading a signal that already exists rather than
adding one:

```
COLLECTED                       491    491 with observations,    0 without
DELIBERATELY_DECLINED           384      0 with observations,  384 without
NOT_YET_COLLECTED               488      0 with observations,  488 without
MAPPED_NO_CURRENT_OBSERVATION    55      0 with observations,   55 without
NOT_APPLICABLE                   48      0 with observations,   48 without
SOURCE_SILENT                    34      0 with observations,   34 without
```

**Of 1,009 cells holding no observations, 34 are `SOURCE_SILENT` -- a filer that
was asked and reported nothing, which is what the gate exists to catch.** The
other 975 are scope and decisions: 488 never asked (2.13's scope rule working as
designed), 384 a concept declined on the record, 55 a declared composition held
under the parent, 48 an inapplicability ruling. **The gate is not changed** --
whether `observations` should be satisfied by a recorded answer, the way
`adoption` is, is a semantic decision and is recorded rather than taken.

This is 2.13 §3's point one round later: a coverage report must distinguish "never
requested" from "not reported". The *ledger* does; the *gate* did not read it.

### `applicability` 1280/1500 is 11 issuers

220 failures, and 11 x 20 = 220 exactly: AILLP, CDZI, CIG-C, EONGY, FAST, FIP,
GRWG, NMPWP, TAC, TSCO, UEPEO. Eleven of seventy-five have no recorded business
model, so no ruling was derived and the gate correctly reports a blank. That is
15% of the population where nothing is known about whether any metric applies --
and it is the first number this project has produced about the 75-issuer
archive's classification coverage, because nothing had ever run over it.

### The type axis exists in the population; only the payload was degenerate

2.15 reported all twelve issuers on disk as `MANUFACTURING`, which was true of the
twelve. The population archive is not degenerate:

```
MANUFACTURING 37   FINANCE_SERVICES 24   SERVICES 3   unclassified 11
```

Three of nine vocabulary members have filers, so **the next selection is fully
determined by data already in the repository** -- only `companyfacts` documents
are missing.

**MINING is reachable and has no filer.** SIC 10-14 maps to MINING and the
strided sample contained no such filer, so including it is a matter of selection.
**But five of the nine vocabulary members cannot be reached by SIC at all** --
`BANK`, `INSURANCE`, `OPERATING`, `REIT`, `TECHNOLOGY`. `BUSINESS_MODEL_BASES`
declares them reachable through `DECLARED_BY_ISSUER`,
`DERIVED_FROM_REPORTED_CONCEPTS` or `MANUAL_CLASSIFICATION`, and the SEC ingestion
path performs none of those. SIC 60-67 is one `FINANCE_SERVICES` bucket, so a bank
and an insurer are the same class to this pipeline.

So the type axis cannot be fully exercised by widening the population alone. It
needs either a finer mapping -- 60/61/62/63/64 are banks, insurers, finance
companies and holding companies -- or an explicit decision to keep one financial
bucket. Cheaper to decide before the fetch than after.

### State

Full suite **612 passed**, 74 skipped, 686 run. No production file changed. The
75-issuer archive was not modified: the chain derivation opens it read-only.

### The next step, and the one decision that precedes it

```
select across business model from the 64 classified issuers
    FINANCE_SERVICES 24 · MANUFACTURING 37 · SERVICES 3
    MINING 0 available -> needs a SIC 10-14 filer in the candidate pool
fetch companyfacts, full 20-metric bulk bootstrap, reconcile, gate, matrix
```

The decision that should be made first, because it changes what the fetch targets:
**whether to split SIC 60-67 into bank / insurance / finance, or accept one
financial bucket.** Widening exercises four of nine vocabulary members; splitting
the financial group exercises two more and makes the applicability rules testable
against the cases 2.7 introduced them for -- a bank that reports no capex and an
insurer that reports no inventory are the two rulings the rules exist to make.
## 0.21 Splitting SIC 60-67, only as far as the rules need (2.16.1)

2.16 left one decision: split SIC 60-67 into bank / insurance / finance, or
accept one financial bucket. Taken, and taken narrowly. The question is whether
the classification has enough **resolution to explain missing evidence**, not
whether the vocabulary has coverage.

```
SIC major group -> business model
   10-14   MINING
   20-39   MANUFACTURING
   70-89   SERVICES
   60-60   BANK               new
   61-62   FINANCE_SERVICES   unchanged
   63-64   INSURANCE          new
```

`REIT` (SIC 65) is deliberately **not** mapped, and no rule was added for
`OPERATING` / `TECHNOLOGY`. `BUSINESS_MODEL_BASES` already declares those reachable
only through `DECLARED_BY_ISSUER`, `DERIVED_FROM_REPORTED_CONCEPTS` or
`MANUAL_CLASSIFICATION`, and the SEC ingestion path performs none of those. They
stay unreachable rather than being given a SIC code they do not own: a rule added
to raise taxonomy coverage cannot answer a question about missing evidence.

### What it does to the population, measured read-only

```
recorded under the old map:  MANUFACTURING 37  FINANCE_SERVICES 24  SERVICES 3
under the new map:           MANUFACTURING 37  BANK 8  FINANCE_SERVICES 8
                             SERVICES 3        unclassified 8
```

16 issuers change: 8 gain a more specific label, and **8 lose a classification**.

```
SIC 60 -> BANK             FHB CCFN BBAR PFBX NRIM CZWI AUBN FCNCP
SIC 61 -> FINANCE_SERVICES unchanged, 8 issuers
SIC 65 -> unclassified     AWCA EFC MYCB BPYPN CRESY HPP VAC BNH
                           (6500 real estate, 6512 REITs, 6531 real estate)
```

The eight that lose one are REITs. They were `FINANCE_SERVICES`, which was wrong
for them, and are now `None`, which is the safe direction: an unclassified filer
is asked about a metric that turns out not to exist and told so by the evidence
layer, rather than silently having a metric removed from its coverage. The cost is
that they can no longer express that gross profit does not apply to them, and
mapping SIC 65 to `REIT` would cost the same as `INSURANCE` -- a label and no
ruling, since no seeded rule names `REIT` either. **Left undecided rather than
taken quietly.** SIC 67 also left the range, so a finance company now makes no
ruling where it made a financial one.

### BANK is populated; INSURANCE and MINING are not

```
SIC 63-64 (INSURANCE) filers in the 75-issuer population: none
SIC 10-14 (MINING)   filers in the 75-issuer population: none
```

**`BANK` is reachable and populated**, 8 filers, and it is the one label whose
classification changes an applicability ruling: `gross_profit` and
`operating_income` are refused for `BANK`, and `BANK` was unreachable from any SIC
code before this split, so **those two rules had never fired for the reason they
were written.** They now can.

**`INSURANCE` is reachable in principle and empty in practice.** The split adds a
label and no ruling, because no seeded rule names it:

```
refused for BANK:        gross_profit, operating_income
refused for INSURANCE:   (nothing)
refused for MINING:      r_and_d
```

Claiming the split "tests insurance applicability" would be a null result dressed
as a success. Writing those rules is a semantic decision, not a mapping fix.
`r_and_d`'s MINING rule still has never fired and still cannot from this
population.

The 8 BANK filers are named above, so the next selection needs no new
classification work. Insurance and mining filers are **not in the archive** and
must be sourced deliberately -- a fact about the candidate pool, not the pipeline.

### The obvious validation is inconclusive

The 8 newly-BANK filers hold zero `gross_profit` and zero `operating_income`,
which is what the ruling claims. **That is not a validation.** The 75-issuer
archive holds eight metrics -- cash, net_income, eps_diluted, revenue, assets,
capex, debt, shares_outstanding -- and `gross_profit`, `operating_income` and
`r_and_d` are not in it. Their absence is scope, not evidence of inapplicability,
and the check cannot distinguish "correctly refused" from "never asked".

This is 2.13 §3 and 2.16's `observations` split arriving a third time in a new
place: **an absent metric is not a negative result.** The ruling-vs-evidence check
only becomes real once the full scope has been collected at population scale.

So the status is: implemented, measured against the population, confirmed to
contradict nothing in the archive -- with the archive unable to confirm it yet.

### A schema observation

The numeric SIC is **not stored**. `issuer_business_model` holds `(asset_id,
business_model, basis, source, recorded_at)` and the code appears only inside the
provenance string, `"SIC 6199 Finance Services"`. Re-classifying an existing
archive therefore means parsing a human-readable provenance string -- which is
what made the measurement above possible offline instead of requiring a re-fetch
of submissions for 75 issuers. A filer's SIC is a property of the filer and not of
any metric, so it belongs in its own column. Recorded, not changed: a migration on
a gitignored archive is not this round's work.

### State

Full suite **620 passed**, 74 skipped, 694 run (+8). One production change,
`sec_ingest.SIC_GROUPS`. Eight tests added, including a **gap marker**:
`test_insurance_is_reachable_and_has_no_rule` asserts that no rule refuses
`INSURANCE`, and is written to **fail** if someone adds one -- which they should,
and should then update this test and this section with it. That is the mechanism
that stops a later round discovering the gap as a surprise.
## 0.22 Eight bank filers, and what the source says about the rules (2.17)

2.16.1 left `BANK` reachable, populated with eight filers, with two applicability
rules already written against it. This runs the full Core scope over them and asks
what 2.16.1 could not: does the ruling materialise, and does the source agree
with it?

2.16.1's obstacle was that absence is ambiguous -- the 75-issuer archive holds
eight metrics and the ruling speaks about two that are not among them. Solvable
without guessing: read the **raw `companyfacts` documents** for the concepts the
registry maps to the refused metrics, independently of the semantic layer. If a
bank tags a concept ST-EVA refuses, the refusal is contradicted by the source and
no archive is needed to see it.

Eight SIC 60 filers fetched, one request each, `fullscope_bulk.py` unchanged.

```
8 issuers  11,174 observations  0 requests  34.3s  37.6 MB
completeness  389 filings, 105 documents, all 11,174 identities distinct,
              0 duplicates, 0 without an accession, 0 without a document
pit safety  0 promoted to an instant, 0 of 5,447 eligible too early
gates  7 of 8 at 160/160; applicability 0/160
```

### The ruling cannot materialise on the bulk path

**`applicability` reads 0/160, structurally.** `companyfacts` carries no SIC, so no
business model is recorded, so no applicability rule fires. The rule is not wrong
here, it is **unreachable**. That is why `gross_profit` reads `COLLECTED` for two
of the eight rather than `NOT_APPLICABLE` -- the refusal exists on the
submissions/API path and is absent on the only path that scales.

2.15 established that a missing `submissions` payload removes a refusal rather
than adding data. This is the same fact against a rule that exists, is populated,
and would otherwise fire: **applicability is currently untestable at scale**, and
no amount of collecting banks changes that.

### What the source says, read before the archive

```
operating_income   0 of 8 banks tag us-gaap:OperatingIncomeLoss
                   -> the refusal is SUPPORTED
gross_profit       2 of 8 banks tag a mapped concept  -> CONTRADICTED
```

Both are real reported lines, not artefacts. **NRIM** files
`us-gaap:GrossProfit` as a clean quarterly and annual series in USD beside its 10-K
and 10-Q. **BBAR** files `ifrs-full:GrossProfit` in ARS units on a 20-F, with the
same period carrying different values across filing years -- a restatement or a
flattened dimension member, and worth knowing which.

So `gross_profit -> NOT_APPLICABLE for BANK` asserts a bank never reports a gross
profit subtotal, and **two of eight do**. The rule is too broad. Narrowing it,
keeping it, or making applicability a prior rather than a refusal is a **semantic
decision**, not taken here.

### Two rules the evidence would justify, and one registry gap

```
r_and_d    SOURCE_SILENT 8 of 8   no bank reports R&D   -> rule warranted by evidence
sga        SOURCE_SILENT 7 of 8   banks report no SG&A   -> rule warranted by evidence
revenue    COLLECTED 3 of 8, DELIBERATELY_DECLINED 5   -> a decline to revisit first
debt       SOURCE_SILENT 8 of 8   and it is not the filers
```

`debt` is the finding. The registry maps four concepts -- `us-gaap:
LongTermDebtCurrent`, `us-gaap:LongTermDebtNoncurrent` and two ifrs equivalents --
and **0 of 8 banks tag any of them**. They tag `us-gaap:LongTermDebt` (6 of 8),
`ShortTermBorrowings` (4), `OtherBorrowings` (3), `SubordinatedDebt` (2). `debt` is
declared a composition of current and non-current, and the registry already records
why: no single standard concept declares total debt. **A bank reporting one
unsplit `LongTermDebt` is reporting a total, not the composition**, so mapping it
would be a different claim rather than a missing one.

That also explains 2.15's `debt` at a median filing ratio of 0.34: manufacturers
tagging one side of the split get partial coverage, filers reporting a combined
total get none. One cause, two populations.

### The positive control

The pipeline is not refusing everything financial. `interest_expense` is `COLLECTED`
for **8 of 8** at a median filing ratio of 0.93, and `assets`, `equity`, `cash`,
`income_tax`, `operating_cash_flow` and `eps_diluted` are 8 of 8 as well. A bank
archive built to suit banks would read `SOURCE_SILENT` across the board; this one
collected 11,174 observations.

### Three measured states of an applicability rule

```
gross_profit   rule exists, evidence AGAINST it      (2 of 8 report it)
operating_income  rule exists, evidence FOR it       (0 of 8 report it)
r_and_d (MINING)  rule exists, NO FILER to test it   (no SIC 10-14 filer anywhere)
```

`r_and_d` and `sga` are the mirror image of `INSURANCE`: there the label is
reachable and the evidence is absent, here the evidence is unanimous and the rule
is absent.

### State

Full suite **620 passed**, 74 skipped, 694 run, unchanged. No production file
changed. Eight companyfacts documents fetched, one request each. Nothing here was a
defect, so nothing was changed: four of the five findings are semantic decisions
about what a bank is, and the fifth is the missing `submissions` payload recorded
in 2.15 and still the largest structural gap in the project.

**The cheapest next measurement is not more rules.** It is the one that would make
applicability testable at all: **does `submissions` ship with the bulk bootstrap?**
Eight submissions documents would answer it, and every applicability rule in the
registry depends on the answer.
## 0.23 companyfacts + submissions: what the second stream is worth (2.18)

2.17 concluded that business-model applicability is not a coverage problem but a
**reachability** one: `companyfacts` carries no SIC, so no business model is
recorded, so no applicability rule fires, and `applicability` reads 0/160 on eight
filers already classified in another archive.

So the question is not "must bulk ingestion have submissions" but the sharper one:
**which semantic capabilities become unreachable without it?**

```
companyfacts   what a filer ever tagged        -> facts, and only facts
submissions    the filer's own filing history,
               and the filer's own SIC          -> issuer and filing context
```

```
                       companyfacts only      + submissions
observations                    11,174             11,174    unchanged
distinct identities             11,174             11,174    unchanged
duplicate identities                 0                  0      unchanged
metrics yielding                      15                 15      unchanged
facts without an accession            0                  0      unchanged
observations without a document       0                  0      unchanged
filings held                        389                858      2.2x
availability basis     FILED_AS_OF_DATE 1174    ACCEPTANCE_DATETIME 11022
                                              FILED_AS_OF_DATE   152
applicability gate                 0/160            160/160    restored
reconciliation vs API path      0 matched/5535    5447 matched/5535
```

**Facts did not move. Context did.** Every number in the first block is identical,
and that is the finding: the second stream changes nothing about the evidence and
everything about what can be said about it.

### The capability split, measured rather than asserted

| capability | companyfacts only | + submissions |
| --- | --- | --- |
| fact identity | 11,174 distinct, 0 duplicates | **unchanged** |
| metric mapping | 15 metrics yield | **unchanged** |
| provenance chain | complete, 389 filings | complete, **858 filings** |
| point-in-time | 100% declared date, one-day-late bound | **98.6% acceptance instants**, 0 eligible too early |
| reconciliation vs the API path | 0 matched of 5,535 | **5,447 matched**, 88 divergent |
| applicability / business model | **0/160** | **160/160** |

Only the classification-dependent capabilities are affected. Identity, mapping,
provenance and every value are untouched, because none of them reads a SIC.

Three things are genuinely restored, worth separating:

**Applicability.** All eight banks classified from their own SIC -- 6022, 6029,
6035: five state commercial banks, one commercial bank NEC, two federally
chartered savings institutions -- and every ruling derives. `gross_profit` and
`operating_income` read `NOT_APPLICABLE` for all eight. **The first time an
applicability rule has fired in a bulk-built archive at all.**

**Point-in-time precision.** 11,022 of 11,174 facts carry EDGAR's acceptance
instant rather than a filed date. The 152 that fall back to a declared date have
accessions outside the submissions window, which is the correct answer rather than
a gap. `promoted: 0`, `eligible too early: 0` -- the invariant holds on the sharper
data, which is the point of checking it.

**Equivalence with the API path.** 5,447 of 5,535 shared facts now match on every
semantic field including `available_at`. The bulk path stopped being a different
kind of source and became the same kind, read from a file. The 88 that still differ
are all one thing -- **the reference archive holding the pre-fix midnight
fabrication** -- so zero unexplained rows, for the third time.

### The filing ledger widened without the evidence moving

`filings_held` 389 -> 858 while `distinct_accessions_in_observations` stayed at 389.
That is the distinction `Ingestor.coverage` was written to state and that 2.15 found
the gates could not read: **evidence coverage** (389 filings actually contributed
tagged facts) against **filing-ledger coverage** (858 the filer declared). The
derived index can only prove the first; the submitted index carries the second,
which is what lets incremental ingestion answer "what is new since the last run"
for filings that tagged nothing we ask for.

The gap is uneven and instructive: BBAR held **8** filings against 253 observations
and 11 metrics, where NRIM held 128. BBAR's facts were fine; its ledger was sixteen
times narrower than the filer's own account of itself.

### What the restored ruling exposes, now materialised

```
                ledger status        observations in the archive
gross_profit    NOT_APPLICABLE       40   (BBAR 18, NRIM 22)
operating_income NOT_APPLICABLE        0
```

**The archive holds 40 observations for a metric it reports as inapplicable.**
NRIM tagged `us-gaap:GrossProfit` in twenty-two rows, BBAR tagged
`ifrs-full:GrossProfit` in eighteen, both were stored, and the ledger says the
metric does not apply to a bank.

Not a data-integrity problem -- the semantic contradiction 2.17 inferred from the
raw source, now visible inside one archive, which is the state in which the
decision is worth making. Three options, none taken: narrow the rule; keep it and
accept that two filers' reported gross profit is collected then not counted; or
**refuse to store** observations for a metric the ledger calls inapplicable, so
archive and ledger agree. The third is a distinct decision -- it is about whether
evidence and a coverage ruling may disagree inside one archive -- and this round
makes it unavoidable by making the ruling reachable at all.

### Two engineering defects, both mine, both caught

**Recursion between `filing_index` and `submissions`.** Teaching `filing_index` to
prefer the submitted index made it call `submissions`, whose companyfacts-only
fallback payload calls `filing_index` to report a count. Every companyfacts-only
mode recursed until the stack ran out, and the offline suite caught it on the first
run in `test_the_bulk_source_declares_a_date` -- the derived-index test, which is
the exact case every prior measurement depends on. Fixed by splitting
`_submissions_document` out of `submissions`.

**`is_xbrl` became a string in the submitted index** where the derived index stored
an integer. `Ingestor` tests `str(...) == "1"` so both work, but the two shapes now
differ in type where they used to agree. Recorded, not changed.

### State

Full suite **620 passed**, 74 skipped, 694 run. One production change:
`sec_bulk.filing_index` prefers the submitted index, with the derived index kept as
the fallback. **Both companyfacts-only modes re-run and reproduce exactly** -- the
fallback is untouched, and that was verified by re-running two prior measurements
rather than by reasoning that it should.

The two-stream shape is settled: it costs one extra request per issuer, the SEC
bulk distribution already ships both, and nothing has to be synthesised.

**Opened, in priority order:** `gross_profit` for BANK; whether ingestion should
store evidence for a metric the ledger calls inapplicable; `r_and_d` and `sga` for
banks, `SOURCE_SILENT` at 8/8 and 7/8 with unanimous evidence, which is the
strongest applicability candidate this project has; and `debt`, a registry gap
rather than a filer one -- 0 of 8 tag the four mapped concepts while 6 of 8 tag
`us-gaap:LongTermDebt`.
## 0.24 Evidence, applicability and coverage are three facts (2.19)

2.18 produced a contradiction and left it sitting in an archive: eight banks, all
classified `BANK` from their own SIC, `gross_profit` ruled out for banks -- and
forty reported gross profit facts held and addressable. This settles what that
means and makes the archive say so in words rather than leaving a reader to notice
two columns disagreeing.

### The decision

**A coverage interpretation is not a deletion filter on evidence.**

The tempting alternative was to refuse to store observations for a metric the
ledger calls inapplicable, so archive and coverage layer would agree. That would
have been a mistake, and this round is the evidence for why:

> Those forty observations are the **entire** finding. They are how
> `BANK -> gross_profit NOT_APPLICABLE` was caught as too broad. Had ingestion
> refused them on the grounds that the metric was ruled inapplicable, the ledger
> would have read zero, the rule would have looked **confirmed**, and the error
> would have been locked in by the very mechanism meant to catch it.

A rule that cannot be contradicted by evidence is not a rule. It is an assumption
with a column.

### Three facts, three places

```
Evidence existence   did the source report this metric?
Applicability        should it mean anything for this filer?
Coverage             have we handled it?
```

In the bank archive these three disagree for the first time: Evidence = yes (40
observations, two concepts, one filer each), Applicability = no (ruled out for
BANK), Coverage = handled.

The tempting encoding is a `SEMANTIC_CONFLICT` *status*. Rejected, for a reason
that is mechanical rather than philosophical: **a status is a partition of the
Core universe.** `scoped_ledger` guarantees the status counts sum to
`metrics_total` -- 20 for every filer -- and every reader reconciling a tally
against the registry depends on that. Moving a conflicted cell into a status of
its own breaks the sum, silently.

So the conflict is a **derived marker beside the status**, not a fourth value of
it. Reported on every ledger row, counted in `ledger["semantic_conflicts"]`,
carried through `collection_chain`, printed by the gate tool. Over the eight banks
exactly two cells fire:

```
BBAR    gross_profit    18 obs    ifrs-full:GrossProfit
NRIM    gross_profit    22 obs    us-gaap:GrossProfit
```

and the statuses still sum to 20 on every filer.

### Three things deliberately not done

**Not a backlog item.** `NOT_YET_COLLECTED` means work to do: the metric has not
been handled. This metric *has* been handled -- collected, ruled on, and
contradicted -- which is a different state, flagged separately rather than folded
into the one that means "get to this".

**Not scored.** The gate tool reports the conflict and says plainly that it is not
scoring it, because whether a conflict should fail a gate is an open decision and
the tool does not take it quietly. It currently passes `observations` (22 > 0)
*and* counts under `NOT_APPLICABLE` at the same time, which is the honest reading
of three independent facts.

**A decline is not a conflict.** Declining a concept is a recorded decision about
that concept, and a metric the registry has already routed around is not evidence
contradicting a ruling.

### The regression guard

`tests/test_semantic_conflict.py`, 11 cases, on the hardest version of the
situation: a filer that classifies as `BANK`, reports `us-gaap:GrossProfit`, and is
asked for a metric the registry refuses it. Nothing about the run is exceptional --
the conflict arises from the registry, not from the pipeline.

```
the observation is stored                              1 row, addressable
the ledger still reports NOT_APPLICABLE
both facts are in the same row                          no join required
the conflict is named, with its concept
the conflict is counted at the ledger level
the status counts still partition the Core universe    sum == metrics_total
a conflicted cell is not a backlog item
a silent inapplicable metric raises no conflict
a quiet cell stays quiet                                only one fires
```

The last group matters as much as the first: a marker that fires constantly
teaches a reader to ignore it, so it stays silent wherever the three facts agree
-- 158 such cells here against 2 that fire.

Writing it caught a fixture bug: the fake source answered for *both* declared
`gross_profit` concepts, so two observations appeared where there should have been
one. A test for "the evidence survives the rule" has to be about one real fact, or
it measures the fixture.

### The three dimensions, measured and now enforced

```
                        NRIM in this archive
filing universe         128 filings held, from the filer's own submissions
evidence universe       2,695 observations across 14 metrics
coverage state          13 collected, 5 silent, 2 not-applicable, 0 backlog
```

**All three are different numbers and none substitutes for another.** A reader who
takes `filings held` as evidence coverage is wrong by two orders of magnitude.
2.18 measured it from the other end -- `filings_held` 389 -> 858 while
`distinct_accessions_in_observations` stayed at 389 -- and BBAR's ledger was
sixteen times narrower than the filer's own account of itself while its facts were
untouched. These three, plus the applicability ruling, are now four separately
reported things and are no longer allowed to be read as one.

### State

Full suite **631 passed**, 74 skipped, 705 run (+11). Two production files:
`coverage_semantics` (the conflict marker) and `score_collection_gates` (reports
it, does not score it). The 5,447 / 88 / 0 is recorded as **5,447
semantic-equivalent, 88 known-stale-reference differences, 0 unexplained** -- not
as a clean sweep, because the 88 are real. The six-issuer, twelve-issuer and
eight-bank runs all reproduce exactly, including 2.14's row-level reconciliation.

### What is next

**The semantic contract is settled; what remains is closing, then widening.**

**A corrected API reference.** Not because there is serious doubt -- the 88 are
fully explained as the pre-fix fabrication in the older archive -- but because
"5,447 equivalent, 88 known-stale, 0 unexplained" is an argument and "5,535 /
5,535" is a measurement.

**`BANK -> gross_profit`.** The conflict is now named, so the decision has a
stable input to reason from: narrow the rule, keep it, or accept that two filers'
reported gross profit is collected and not counted.

**A real cross-business-model population.** The bank sample is homogeneous by
construction -- eight SIC 60 filers. INSURANCE and MINING still have no filer
anywhere, and the type axis cannot be exercised until they do.

No further bulk machinery. `companyfacts + submissions` covers the context the
current layer needs, and the remaining work is semantic.
## 0.25 The bulk/API equivalence chain, closed (2.20)

2.18 left an argument rather than a measurement: **5,447 semantic-equivalent, 88
known-stale-reference differences, 0 unexplained.** The 88 were fully explained --
accessions outside the submissions window, where the older API-built archive still
recorded the filed date as a fabricated midnight labelled `ACCEPTANCE_DATETIME`,
the defect 2.14 fixed -- but "fully explained" is not "measured".

Rebuilding the reference under the corrected contract and reconciling again:

```
11,174 shared source_fact_id
11,174 matched
     0 divergent
     0 only-in-bulk
     0 only-in-reference
     0 unexplained

all eight gates identical on both routes
sealed snapshot ce603a5588cef067, unchanged
```

**The chain is closed.** The bulk route reads the same SEC source through two
files per filer instead of 49 requests and lands on an archive identical on every
one of 26 semantic fields for every row.

### What closed, and how

| | bulk (2 files per filer) | API (per-concept requests) |
| --- | --- | --- |
| network requests | **0** | **392** (49 per filer) |
| elapsed | 34.9 s | -- |
| observations | 11,174 | 11,174 |
| distinct identities | 11,174 | 11,174 |
| filings held | 858 | 858 |

Eight `companyfacts` + `submissions` documents read from disk against eight SEC
API walks, same twenty metrics, same forms policy read from one archive so the
comparison could not be a form-policy artefact.

**Cross-checked without the project's code**, because a test satisfiable only by
the code under test is not a second opinion:

```
INDEPENDENT SQL CROSS-CHECK
  bulk rows                       11,174
  api rows                        11,174
  shared source_fact_id           11,174
  differing on any of 26 fields        0
  only in bulk / only in api            0 / 0
```

Same answer from two unrelated implementations of the same comparison.

### Gates identical, both routes

```
                     bulk     API
definition        160/160  160/160
mapping           160/160  160/160
applicability     160/160  160/160
adoption          160/160  160/160
observations       95/160   95/160
provenance        160/160  160/160
missingness       160/160  160/160
discoverable      160/160  160/160
```

Including the same nine failing `observations` cells -- `debt` at 8 of 8, the two
debt components, `r_and_d`, `sga`, `capex`, `shares_outstanding`,
`weighted_average_diluted_shares`. Those are real findings about banks, not route
differences.

### The conflict survives both routes

```
                bulk                 API
gross_profit    BBAR:18 NRIM:22      BBAR:18 NRIM:22
business models recorded    8/8            8/8
```

Both archives hold the forty observations, both refuse to count them, both name
the conflict. That is the 0.24 contract working identically on both delivery
paths, which is the point of having measured equivalence: a contract that only
behaved on one route would not be a contract.

### What the equivalence licenses

**It licenses** treating the bulk route as a *substitute* rather than a variant.
Reading from files rather than endpoints produces the same evidence, identity,
point-in-time boundary and coverage surface. The 2.13 premise -- that a bootstrap
and an incremental run can be reconciled because they produce the same thing -- is
now demonstrated at the full Core scope rather than asserted, and the archive can
be rebuilt from a nightly bulk download with no semantic consequence.

**It does not license** assuming the next filer behaves the same way. Eight SIC 60
banks, 47 concept fetches each, no mega-cap, no filer outside one industry group.
The cost constant is still a floor.

**It makes the operational number concrete at full scope:** 392 requests for eight
filers, or 49 per filer, against **zero** for the same eight from files. At ten
thousand filers the API route extrapolates to roughly half a million requests; the
bulk route's does not move.

### State

Full suite **631 passed**, 74 skipped, 705 run. No production file changed.
`build_crossframework_snapshot.py` gained `--issuer` / `--reference`, with the
issuer set and form policy read from an archive rather than hand-written -- 2.13's
empty-map incident was a run that reported no errors and collected nothing. 392
network requests, one API walk per filer. Neither archive modified in place.

### What remains

**`BANK -> gross_profit`.** The conflict is named identically on both routes with
the concept attached, and the decision is semantic rather than operational:

```
BBAR    ifrs-full:GrossProfit   18 rows   20-F, ARS units, same period carrying
                                            different values across filing years
NRIM    us-gaap:GrossProfit     22 rows   10-K and 10-Q, clean quarterly series
```

Narrow the rule, keep it, or accept that two filers' reported gross profit is
collected and then not counted. Deleting the evidence is **not** available as an
option, for the reason 0.24 recorded.

**`r_and_d` and `sga` for banks** -- `SOURCE_SILENT` at 8 of 8 and 7 of 8 with
unanimous evidence. The strongest applicability candidate in the project, and the
mirror image of `INSURANCE`, where there is no filer to say anything.

**A cross-business-model population** -- the bank sample is homogeneous by
construction. `INSURANCE` (SIC 63-64) and `MINING` (SIC 10-14) still have no
filer anywhere, so the type axis cannot be exercised and `r_and_d`'s MINING
exclusion has never fired.

**Whether a semantic conflict should score as a gate failure** -- open, reported
rather than decided, and now measurable on any archive that holds one.
## 0.26 What the forty observations actually are (2.21)

2.20 closed the equivalence chain and left the semantic question standing:
`BANK -> gross_profit NOT_APPLICABLE`, against 2 of 8 banks reporting a mapped
gross profit concept. The standing order was not to overturn the rule on 2 of 8
but to turn it into an explicit, testable proposition -- which means
characterising the evidence first. That produced the finding, and it **narrows the
counterexample count from two to one.**

### Two banks reported it. One of them is not a counterexample.

```
NRIM   22 obs  us-gaap:GrossProfit   unit currency  10-K x6, 10-Q x16
       17 distinct periods, 5 with more than one value:
         4 are IDENTICAL values  -> a restated comparative filed twice
         1 differs: 2025 Q1  46,906,000 -> 45,746,000
       range 34.1M .. 208.9M

BBAR   18 obs  ifrs-full:GrossProfit  unit RATIO     20-F x18
       8 distinct periods, 6 with more than one value, diverging:
         2019   88.8B / 120.9B / 182.5B
         2022   368.3B / 1,146.8B / 2,497.3B
```

**BBAR is not evidence for or against anything.** A restatement moves a number; it
does not move it sevenfold. Six of BBAR's eight periods carry two or three
distinct values spread by factors of three to seven, all tagged
`ifrs-full:GrossProfit` in a `ratio` unit on a 20-F. That is the signature of the
aggregated endpoint hiding dimension members -- several different facts arriving
looking like one. **BBAR's 18 observations are not 18 comparable gross-profit
values.**

And the archive already knew. `dimension_collisions` across the eight:

```
AUBN 11   BBAR 133   CCFN 2   CZWI 65   FCNCP 86   NRIM 48   PFBX 59    404 total
```

133 for BBAR, the filer whose gross profit is flattened.

**NRIM is a clean counterexample.** A US savings institution filing
`us-gaap:GrossProfit` as a quarterly line beside its 10-Q, with ordinary
restatement behaviour. So the honest count is not "2 of 8 banks report gross
profit":

| filer | reports a mapped concept | usable as evidence |
| --- | --- | --- |
| NRIM | yes, 22 rows, quarterly, currency | **yes** -- a real entity-level subtotal |
| BBAR | yes, 18 rows, annual, ratio units | **no** -- dimension members flattened |
| other 6 | no | -- |

**One genuine counterexample, one artefact.** The difference is only visible
because the collisions were counted.

### The proposition, stated

> Does `BANK` imply that `gross_profit` is `NOT_APPLICABLE`?

**In general: refuted.** One filer of eight reports an entity-level gross profit
subtotal under a mapped concept, quarterly, in its own 10-Q, and it is a real
reported line rather than a dimensional artefact.

**For these filers: undecided.** Six report nothing, one refutes, and one is
untestable from the evidence held.

**And the vocabulary cannot say it.** `applies_to` is binary -- there is no
conditional -- so "a bank *may* report gross profit and this filer *does*" is not
expressible, which is exactly the situation the evidence describes.

Three options, none taken. **Narrow** the rule: six banks get `SOURCE_SILENT`
forever -- honest but noisy, where the rule served them. **Keep** it: one filer's
reported gross profit is collected and never counted, and the conflict marker
becomes permanent furniture. **Make it conditional**: `BANK` stops being a
statement about the company and becomes a statement about the filer's reporting,
which is what `SOURCE_SILENT` is already for -- and which would make the 0.24
conflict inexpressible for this pair, since the two mechanisms would be solving the
same problem.

### The gap that blocks deciding on a bigger sample

`dimension_collisions` is counted per run and per issuer and printed in the
ingestion report. It is **not persisted per metric**, so it cannot be joined to
the conflict. BBAR's conflict looks exactly like NRIM's:

```
BBAR   gross_profit  NOT_APPLICABLE  18 obs  ['ifrs-full:GrossProfit']
NRIM   gross_profit  NOT_APPLICABLE  22 obs  ['us-gaap:GrossProfit']
```

One is a refutation and one is an artefact of reading from a single aggregated
document, and a consumer of the coverage surface cannot tell them apart. **The
measurement exists; it is filed at the wrong grain.** Before a larger bank sample
is used to decide anything, the collision count has to travel with the metric --
`ingestion_scope` is already keyed by `(run_id, asset_id, metric_id)` and the
counter is already computed inside `_store_facts` where the metric is in hand.
Not done this round, because the instruction was to state a proposition rather than
build instrumentation, and a half-done version would make the conflict marker look
more authoritative than it is.

**Until then, any count of "how many banks report gross profit" taken from this
archive is wrong, and the error is toward over-counting.**

### The opposite case: r_and_d and sga

Both `SOURCE_SILENT` at 8 of 8 and 7 of 8, and both **not** contradicted by
anything -- no bank tags the concepts, so there is no conflict, only silence. They
need more filers, not better characterisation, and `INSURANCE` and `MINING` have
no filer anywhere, which is the only remaining sufficient reason to fetch.

Worth carrying forward: **a rule that fires and is contradicted is more
informative than a rule that fires and is silent.** `gross_profit` has already
taught more about banks than eight `SOURCE_SILENT` results could.

### State

Full suite **633 passed**, 74 skipped, 707 run (+2). No production file changed;
archives read only. Two tests added to `tests/test_semantic_conflict.py` pinning
the pair that makes the argument hold: the rule under dispute is a **live seeded
rule** (`gross_profit.inapplicable_in` contains `BANK`, `applies_to("BANK")` is
False), and the vocabulary **cannot express conditionality**. The second is a gap
marker written to fail if anyone adds `CONDITIONAL` -- because they will have to
decide whether a conditional ruling satisfies or overrides the conflict marker,
and that is not obvious.

### Next, in order

**Per-metric dimension collisions**, so a conflict marker can tell a refutation
from an artefact. **`INSURANCE` and `MINING` filers** -- the only remaining
sufficient reason to fetch. **Decide `BANK -> gross_profit`** with evidence that
can be trusted at that size. **`r_and_d` and `sga`**, which need population rather
than characterisation.
## 0.27 Dimension collisions at the grain the decision needs (2.22)

2.21 refused to decide `BANK -> gross_profit` because the deciding evidence could
not be trusted: the collision count was filed per issuer, so a question about a
metric had no number to answer it with. This persists the collision at the grain it
is asked at, re-runs the eight banks, and re-characterises. It also caught the
implementation making a claim the data cannot support.

### Two corrections to 0.26, one of them a logic error

**The general rule is refuted, not undecided.** 0.26 said "for these filers
undecided", which conflated a refutation with an open decision. One valid
counterexample refutes a universal rule; NRIM is valid, so:

```
BANK -> gross_profit NOT_APPLICABLE     REFUTED
BANK -> ?  (the replacement)            UNDECIDED
```

Stated separately on purpose. The failure this prevents is specific: "the sample
is too small, so we keep `NOT_APPLICABLE`" keeps a rule alive that has already
been contradicted. The six filers reporting nothing are evidence about the
*replacement*, not about the rule.

**BBAR is a third state, not a subtraction from a count:**

```
NRIM    valid positive evidence against a BANK-wide NOT_APPLICABLE rule
BBAR    source concept present -> dimension ambiguity -> meaning unresolved
others  no mapped evidence -> SOURCE_SILENT
```

which is the project's existing ambiguity contract arrived at by another route.

### The table

Migration `0014_dimension_collisions.sql`, one row per collision with the metric,
the concept, the filing and the period attached, keyed on the collision rather than
the run so a rerun replaces and a wider rerun adds. Written in the same
transaction as the run, for the same reason the scope rows are: a collision is a
statement about a metric, and filing it per issuer put the number where nobody
asking the question would look. That was the defect -- 404 collisions across eight
banks and no way to say whether any belonged to gross profit.

```
metric                              filers  keys  extra values per key
operating_cash_flow                     6     67    74
cash                                    5     37    51
eps_diluted                              5     29    34
equity                                   4     57    73
net_income                               4     56    62
income_tax                               4     43    48
interest_expense                         4     28    33
assets                                   4     17    18
capex                                    3     20    20
weighted_average_diluted_shares          2     13    13
gross_profit                             2     11    15
sga                                      1     12    17
```

Which is itself a finding: **the collisions are not concentrated in the disputed
metric.** `gross_profit` has 11 affected keys; `operating_cash_flow` has 67, and
`equity` has more extra values per key. A reader who assumed the ambiguity was
specific to the metric under argument would be looking in the wrong place -- it is
a property of aggregated sources generally, not of this rule.

### The claim the data would not support

The first implementation classified a collision as `RESTATED_SAME_PERIOD` when
earlier and later filings disagreed and no single filing reported two values for
one period. On these eight banks it reported **392 of 392** as restatements,
including BBAR's GrossProfit, where 2019 moves 88.8bn -> 120.9bn -> 182.5bn across
three 20-F filings. **A restatement does not move a number by 36% and then 51%.**

And it could not be rescued: the member axis was dropped by the aggregated endpoint
*before ingestion saw anything*, so "this filer revised the number" and "these are
two members reported in two filings" are the same observation. No test on this data
can separate them. So the vocabulary says what was seen:

```
SAME_PERIOD_DIFFERENT_VALUE   one filing reported two values for one period. A
                              member was hidden. Provable from this source.
LATER_FILING_DIFFERS          an earlier and a later filing reported different
                              values for one period, each reporting one value.
                              Whether it is a revision or a hidden member is NOT
                              determinable here.
```

`RESTATED_SAME_PERIOD` was removed rather than left available, and `UNIT_MISMATCH`
went with it: the collision key includes the unit, so a unit mismatch never
collides and nothing could produce it. **A closed vocabulary that names a state no
code can emit is worse than a short one -- it advertises a distinction the archive
cannot make.** `SAME_PERIOD_DIFFERENT_VALUE` did not occur on these eight banks;
that is a real zero, covered by a test.

The consequence: BBAR is now correctly **undeterminable** rather than *artefact*.

```
NRIM   1 key, 2025 Q1, 46,906,000 -> 45,746,000    a 2% revision
BBAR   9 keys, values moving 36% then 51%             not a revision; not provable either
```

NRIM stands as the valid counterexample and the general rule stays refuted. BBAR
contributes no evidence in either direction -- which is the finding, and what a
consumer needs to be told rather than left to guess.

`LATER_FILING_DIFFERS` also does not make the series unusable. A restated series
is a series with a history of revisions, which is ordinary, and the conflict marker
still fires correctly for both filers. What it prevents is treating either as 18
comparable points.

### Two bugs the grain caught, both mine

**`distinct_values` off by one** -- reported before the new value was added.

**The restatement test compared the wrong container** -- it tested whether a set of
accessions was a subset of a dict keyed by *values*, never true, so
`RESTATED_SAME_PERIOD` could not execute even in principle. All 392 came out as the
other kind and nothing complained, because there was only one kind in play.

The second is the instructive one: **a label that cannot fire looks exactly like a
label that correctly never fires.** The difference became visible only when a
second kind existed and neither appeared. A vocabulary member with no test is not a
closed vocabulary -- it is an untested branch in a comment.

### State

Full suite **639 passed**, 74 skipped, 713 run (+6). Production change:
`sec_ingest` and migration `0014`. Equivalence **11,174 / 11,174 matched, 0
divergent, 0 one-sided** -- unchanged. Sealed snapshot untouched. Six tests cover
both kinds, the metric-and-concept naming, the running count for a third value,
and the two removed members being rejected by the database rather than merely
absent. The two vocabulary tests build real parent rows first, because with fakes
the foreign key can fire instead of the CHECK and the test passes for the wrong
reason.

### What is decidable now, and what is not

`BANK -> gross_profit NOT_APPLICABLE` is **REFUTED**. The replacement is undecided,
and 2.22's measurement suggests it may not need a `CONDITIONAL` state at all:
`SOURCE_SILENT` already says "this filer, in this source evidence, does not report
this metric", while `APPLICABLE` / `NOT_APPLICABLE` answers a different question --
do we have sufficient semantic reason to refuse asking. If there is no such reason,
the move is not to invent a conditional but **not to write the rule**, which keeps
the three layers clean and leaves `semantic_conflict` firing only where layer 1 and
layer 2 genuinely disagree.

And a note cutting the other way: six banks reporting no gross profit would become
permanent `SOURCE_SILENT` if the rule is removed. Honest, and also a retrieval
backlog growing every night for six filers -- exactly the noise the rule was
suppressing. The decision is a genuine trade, and the evidence now narrows it to a
choice rather than a guess.

**Next, and larger than any one applicability rule:** the `LATER_FILING_DIFFERS`
rate is now measurable per metric, so the question worth asking is whether **392
collisions across eight banks is normal for an aggregated source or a filer
effect.** If it is normal, then no metric built on `companyfacts` should be read as
a flat series without that caveat attached.
## 0.28 MINING and INSURANCE: the first rules with filers of their own (2.23)

2.22 left the semantic question standing and refused to widen the bank sample. This
went and got the population that has been missing since 2.16.1: `INSURANCE`
(SIC 63-64) and `MINING` (SIC 10-14) had **no filer in any archive in this
repository**, so `r_and_d`'s MINING exclusion had never fired and no INSURANCE rule
could even be evaluated.

Eight filers, four of each, full Core scope, zero network:

```
8 issuers  16,351 observations  0 requests  52.1s  54.9 MB
completeness  996 filings, 132 documents, all 16,351 identities distinct,
              0 duplicates, 0 without an accession, 0 without a document
pit safety  0 promoted to an instant
              basis: ACCEPTANCE_DATETIME 8,279 / FILED_AS_OF_DATE 8,072
gates  7 of 8 at 160/160, applicability 160/160, observations 110/160
```

**`r_and_d -> NOT_APPLICABLE for MINING` fired for the first time in this
project's history, and it is contradicted.**

```
ticker   model      r_and_d status      obs   conflict
BHP      MINING     NOT_APPLICABLE        0
KNF      MINING     NOT_APPLICABLE        0
NEM      MINING     NOT_APPLICABLE      236    EVIDENCE_HELD_FOR_INAPPLICABLE_METRIC
PAAS     MINING     NOT_APPLICABLE        0
HUM/PFG/PRU/SIGI  INSURANCE  SOURCE_SILENT  0
```

**NEM (Newmont, SIC 1040 Gold and Silver Ores) tags
`us-gaap:ResearchAndDevelopmentExpense` in 236 observations.** A gold miner
reporting research and development is not a contradiction of the word "mining" -- it
is what the word has meant since gold and silver exploration became capitalised.
The rule is right for three of four miners and wrong for the fourth.

The conflict marker fired on its own, naming the concept. Nothing needed a special
case: the rule fired, the source contradicted it, both facts in one ledger row.

### Two for two

Every applicability rule testable against real filers in its own target class has
been contradicted by at least one of them:

| rule | class | filers | contradicted by |
| --- | --- | --- | --- |
| `gross_profit` NOT_APPLICABLE | BANK | 8 | NRIM, 22 obs, `us-gaap:GrossProfit` |
| `r_and_d` NOT_APPLICABLE | MINING | 4 | NEM, 236 obs, `us-gaap:ResearchAndDevelopmentExpense` |

Two rules, two independent model classes, two contradictions. A small sample that
does not prove a general law -- but enough to say that **a rule authored from a
category intuition and never checked against a filer in the class should be assumed
wrong until the filers say otherwise.** `r_and_d`'s exclusion was written in 2.7
and survived untouched through every round since, because no miner had ever been
in an archive to contradict it.

### The INSURANCE baseline, which did not exist before

```
              BHP   KNF   NEM   PAAS  |  HUM   PFG   PRU   SIGI    (observations held)
revenue        33    48   141    18  |  391   309   329   255
eps_diluted    33    45   331    18  |  321   309   273   303
operating_cash_flow
               33    31   164    18  |  160    77   155    92
interest_expense
               39    15    54    31  |  207     0    43   215
gross_profit    0    45    98    18  |    0     0     0     0   <-- 0 of 4
r_and_d         0     0   236     0  |    0     0     0     0   <-- 0 of 4
operating_income
                0    45     0     0  |  233     0     0     0
sga             0    45   236    18  |  233     0   155     0
capex           0    31   208     0  |  165     0     0    73
debt            0    72   276    26  |  144     0   138     0
```

Four filers is thin and this does not write a rule. What it gives:

**`gross_profit` is 0 of 4 insurers** -- the same silence as 0 of 6 banks, for a
different reason: an insurer's income statement is built from premiums and
benefits, with no cost-of-goods subtotal to take a margin from. Two independent
industries reaching the same silence for different reasons is a better argument
than either alone.

**`r_and_d` is 0 of 4 insurers**, which is *evidence* for an INSURANCE exclusion
rather than the absence of evidence that `INSURANCE` currently is.

**`operating_income` is reported by HUM and no other insurer.** A hospital and
medical service plan has an operating income line; a life insurer does not. The
clearest example yet of why an industry bucket is too coarse -- HUM and PRU are
both `INSURANCE` and they differ on this metric.

**PFG reports almost nothing**: revenue, EPS and operating cash flow only, zero on
interest expense, operating income, SG&A, capex and debt. One filer saying less
than its peers is a finding about the registry, not about the filer.

### A point-in-time finding only longer histories show

```
bank corpus  (8 filers)   ACCEPTANCE_DATETIME 11,022  FILED_AS_OF_DATE  152   1.4%
this corpus  (8 filers)   ACCEPTANCE_DATETIME  8,279  FILED_AS_OF_DATE 8,072  49.4%
```

**Half of this corpus falls back to a declared date.** BHP and KNF are decades-old
and their early filings sit outside the ~1,000-filing submissions window, so
`DECLARED_DATE_LAG_DAYS = 1` is not an edge case governing a rounding error -- **on
older filers it governs half the evidence**, and on a corpus reaching back further
it would govern more. Also means the two corpora are not directly comparable on
time coverage, and a coverage figure drawn across them without saying so would be
misleading.

### Two corrections this round made

**My own error, corrected in 0.27.** That said removing the `gross_profit` rule
would leave six banks with "a retrieval backlog growing every night". Wrong, and
wrong in the direction the system exists to prevent: they would read

```
not ruled inapplicable + source asked + nothing returned  =  SOURCE_SILENT
```

which is **handled, source silent** -- a coverage state, not undone work.
`NOT_YET_COLLECTED` is the only status meaning work to do. There is real recurring
cost, but it belongs to ingestion scheduling, not coverage.

**The ticker map could not come from the reference archive.** These eight filers
exist in no archive here, and `fullscope_bulk.py` correctly refused rather than
guess a CIK. The map now comes from the payload's own `tickers.json`, written by
`fetch_source_inventory.py` from the SEC company ticker map through the same
provider ingestion resolves through. Also added, because eight filers in no archive
needed it: **`--forms submissions`**, reading each filer's form set from the
submissions document the run already holds, so no form-policy assumption enters a
result whose value is that nothing was assumed.

Discovery note worth keeping: the candidate pool was chosen for *industry*
coverage and SIC was read from the SEC's own submissions, which is the only reason
it is trustworthy. Four guesses that looked like miners were not -- `GOLD` is
wholesale jewellery (50), `AA` primary aluminium (33), `NUE` steel (33), `CIG`
electric services (49).

### The reframing that made this possible

0.27's collisions are a **source representation property**, not a metric
exception, and this made it structural. `sources` had **no row at all** in any
evidence archive, so a question about the shape of a source's facts had nowhere to
be answered except as a per-metric exception. Now declared once:

```
sources.retains_dimensions = 'AGGREGATE'
sources.aggregation_note   = 'Facts are aggregated across dimension members...'

source fact
    ↓
does the endpoint retain the dimensional axis?   AGGREGATE -- it does not
    ↓
ambiguity may attach, and is recorded per event
```

That makes `ingestion_dimension_collisions` readable as **evidence** for a
declared property rather than a list of odd metrics -- which matters here, because
`operating_cash_flow` has six times more affected keys than the `gross_profit` the
argument was about.

### State

Full suite **639 passed**, 74 skipped, 713 run. Production change: `sec_ingest`
(source registration), `sqlite_archive` (declaration columns), migration `0014`.
Bank archive rebuilt and equivalence re-verified **11,174 / 11,174**. Sealed
snapshot untouched; all five pre-existing archives open under the edited migration.

### Where this leaves the semantic work

```
BANK -> gross_profit NOT_APPLICABLE      REFUTED  (NRIM)
MINING -> r_and_d NOT_APPLICABLE         REFUTED  (NEM, 236 observations)
INSURANCE -> ?                           no rule; baseline now exists
```

It is no longer open whether a semantic rule can survive real source evidence. The
answer is that neither of the two tested could.

**And the direction of the fix is now empirically supported rather than argued.**
0.26 offered three options for `gross_profit` and leaned toward "no universal
rule, possibly conditional". The evidence says something stronger:
**conditionality is probably unnecessary, because the correct response to a refuted
rule is to have no rule.** `SOURCE_SILENT` already says what a filer did not
report, and it is not work to do. A filer that genuinely reports gross profit gets
it collected; one that does not is asked again when the source has something new.
That is existing behaviour and needs no new state.

**Next, and it is a decision rather than a measurement:** apply that to both
refuted rules. Removing them is the smallest change that makes the archive agree
with the evidence, and it is now supported by two independent counterexamples
rather than one. The counter-argument -- six banks and three insurers asked again
each cycle -- is a scheduling cost, not a coverage debt.

What should **not** happen is a third rule written from the same intuition and
waiting for a filer to contradict it. If a narrower rule is wanted, it needs
evidence for the narrower claim.
## 0.29 The two refuted rules are removed, and a rule lifecycle (2.24)

`2/2 rules refuted` supported removing those two rules. It did not support
"applicability rules are useless", and the difference is not pedantic: a rule that
has not been tested is not a rule that has been upheld, and the failure mode this
section exists to prevent is a third rule being written from the same intuition and
waiting for a filer to contradict it.

### The lifecycle

```
PROPOSED
    ↓  a filer of that class exists and has been through a full Core-scope
       collection
TESTABLE
    ↓
    ├── SUPPORTED    no counterexample found
    ├── REFUTED      a filer of that class contradicts it
    └── UNDECIDED    the replacement proposition has not been established
```

Two of those definitions carry the weight, and both are about what a state
**forbids**:

**`REFUTED` means the rule must not serve as a refusal rule.** Removal is required,
not optional, and re-adding it requires editing the test that records which filer
contradicted it and why. `tests/test_semantic_conflict.py::TestRefutedRulesAreAbsent`
is that test, and it names the filer:

```
BANK   -> gross_profit    NRIM,  22 obs, us-gaap:GrossProfit
MINING -> r_and_d         NEM,  236 obs, us-gaap:ResearchAndDevelopmentExpense
```

**`UNDECIDED` means the replacement has not been established. It does not mean
the old rule may continue to exist.** Those are different sentences and conflating
them is how a refuted rule comes back: "the sample was only four filers" is an
argument about a *replacement*, and never an argument that the refuted rule was
right.

**`SUPPORTED` requires an affirmative evidentiary basis, and "no counterexample
found" is not one.** This is the distinction that keeps a hypothesis layer from
hardening into a fact layer, stated here rather than left implied because the
pressure toward the wrong reading is constant: silence looks like evidence because
it produces a number.

A metric with no observations is a different fact from a metric with no meaning;
that distinction is what `SOURCE_SILENT` against `NOT_APPLICABLE` is for. So *"0 of
8 banks report this"* is consistent with a rule about banks and does not support
it. To reach `SUPPORTED` a rule needs evidence of the thing it asserts -- here,
that the line does not exist on the filer's statement -- rather than evidence that
the archive has not yet seen it.
`tests/test_semantic_conflict.py::TestRefutedDoesNotMeanUseless` pins that a rule
with only consistency behind it stays `TESTABLE`.

### The current states of every seeded exclusion

| rule | class | state | why |
| --- | --- | --- | --- |
| `gross_profit` NOT_APPLICABLE | BANK | **REFUTED** | NRIM, 22 obs, `us-gaap:GrossProfit`, quarterly beside its 10-Q |
| `r_and_d` NOT_APPLICABLE | MINING | **REFUTED** | NEM, 236 obs, `us-gaap:ResearchAndDevelopmentExpense` |
| `gross_profit` NOT_APPLICABLE | FINANCE_SERVICES | **PROPOSED** | never tested: SIC 61-62 was split out in 2.16.1 and the eight filers it produced were all SIC 60, so no filer of this class has been through a full Core-scope collection anywhere |
| `operating_income` NOT_APPLICABLE | BANK, FINANCE_SERVICES | **TESTABLE** | 8 banks, 0 tag `us-gaap:OperatingIncomeLoss`; consistent with the rule, does not establish it |

Three of four states, and none of them is "supported". That is the honest position:
one rule is contradicted twice over, one has never been tested, and one is
untouched by any counterexample and untouched by any evidence for it.

### What removal produced, verified rather than asserted

No special case anywhere. The statuses the removal should yield, and what it did
yield, on both corpora:

```
snapshot-banks2      gross_profit
   NRIM               COLLECTED      22 obs
   BBAR               COLLECTED      18 obs
   AUBN CCFN CZWI FCNCP FHB PFBX      SOURCE_SILENT

snapshot-ins-min     r_and_d
   NEM                COLLECTED     236 obs
   BHP KNF PAAS                      SOURCE_SILENT
   HUM PFG PRU SIGI (INSURANCE)       SOURCE_SILENT
```

**258 observations that were previously collected-then-refused are now simply
collected.** Nothing was fetched that was not already fetched, nothing was
discarded, and the three filers that report these metrics keep their evidence.

**And the conflict markers are gone** -- 0 on both metrics. That is correct and
worth stating plainly rather than treating as a regression: a `semantic_conflict`
is a statement about a *rule*, and with no rule there is nothing to contradict. The
machinery is still live and still tested, against the rule that survived
(`operating_income` x a `FINANCE_SERVICES` filer), because a contract that only
ever applied to rules that have since been deleted would not be evidence of
anything.

### What removal does not fix

`operating_income` still refuses for financial institutions on no evidence beyond
consistency, and `gross_profit` still refuses for `FINANCE_SERVICES` on no evidence
at all. Removing two refuted rules did not make the remaining ones supported; it
made their lack of support visible.

Both are now in a state where the remedy is named: a filer of the class, collected
at full Core scope. `FINANCE_SERVICES` needs eight more of the SIC 61-62 filers the
75-issuer archive already names, and `operating_income` needs either a bank that
reports it or an explicit decision that the silence is enough -- which would be a
change of evidentiary standard, not a change of rule.

### The philosophy this adds up to

> **`NOT_APPLICABLE` is not a default. It is a refusal proposition that requires
> Evidence to support it. Without sufficient evidence to refuse, the question goes
> to the source and the answer is whatever the source says.**

Which reduces to four cases, and needs no conditional state:

```
a rule exists and rules the metric out   -> NOT_APPLICABLE
no rule                                  -> no refusal; the metric is asked
the source reports it                     -> COLLECTED
the source has nothing                    -> SOURCE_SILENT
```

`CONDITIONAL` was considered and rejected on evidence rather than taste. It was
never needed: the two propositions it would have described were "a bank may report
gross profit" and "a miner may report research and development" -- and for both, the
correct resolution turned out to be that there is no rule at all, because
`SOURCE_SILENT` already expresses what a filer did not report, and it is not work
to do. `applies_to` remains binary and `tests/test_semantic_conflict.py` carries a
gap marker that fails if anyone adds conditionality, because the first thing they
would have to decide is whether a conditional ruling satisfies or overrides the
conflict marker.

### Two points from 2.23 preserved, because they are not about rules

**The availability semantics stay genuinely distinct.** `FILED_AS_OF_DATE` is 1.4%
of the bank corpus and **49.4%** of the MINING/INSURANCE one, because BHP and KNF
are decades-old and their early filings sit outside the ~1,000-filing submissions
window. "The source has only a filed date" is not a tail on the corpus -- it is a
substantial part of any historical one, and on older filers it grows. So a filed
date must not become a timestamp for convenience later, and the further back in
history a consumer looks, the more its PIT precision should be visible to it.

**`INSURANCE` is too coarse to carry a universal rule.** Four filers, four SIC
subgroups, and `operating_income` reported by one of them: a hospital and medical
service plan has that line, a life insurer does not. `gross_profit` 0 of 4 and
`r_and_d` 0 of 4 are four source-silent observations each, which is not evidence
for an exclusion. Before any insurance rule is written the question is *which kind
of insurance* -- which is the same lesson as `BANK` and `gross_profit`: a coarse
business-model label makes a false universal rule easy to write.

### State

Full suite **643 passed**, 74 skipped, 717 run (+4). One production file:
`registry_seed.py`. Both corpora re-run; bulk/API equivalence still **11,174 /
11,174** with 0 divergent and 0 one-sided, and the point-in-time invariant holds on
both. Sealed snapshot untouched.
## 0.30 Both remaining exclusions refuted, and the registry is nearly empty (2.25)

2.24 left three seeded exclusions and labelled them honestly: two REFUTED and
removed, one PROPOSED-but-never-tested, one TESTABLE-but-unestablished. This
collected the population for the untested one.

The test set was already in an archive. The 75-issuer population's own
classification table names every SIC 61-62 filer, and 2.16.1's split of SIC 60-67
is what put them there. Seven were fetched; the eighth, **IPB, has no
`companyfacts` document at all** -- EDGAR returns 404, which is a different fact
from reporting nothing and is recorded as the absence of the document rather than
as silence about a concept.

```
7 filers  12,489 observations  0 requests  34.9s  42.9 MB
completeness  983 filings, 129 documents, all identities distinct, 0 duplicates
pit safety  0 promoted, 0 of 4,826 eligible too early
```

### Both rules refuted

Proposition, stated before the run: *refuted if any filer of the class tags a
mapped concept; silence would be testable-with-no-counterexample, not supported.*

```
ticker   gross_profit                        operating_income
AIXC     COLLECTED       4 obs  us-gaap      COLLECTED  134 obs
FMCCH    SOURCE_SILENT   0 obs               DELIBERATELY_DECLINED  0 obs
OMCC     SOURCE_SILENT   0 obs               COLLECTED   18 obs
ORXCF    SOURCE_SILENT   0 obs               COLLECTED  107 obs
PRAA     SOURCE_SILENT   0 obs               COLLECTED  216 obs
SLNHP    COLLECTED      20 obs  us-gaap      COLLECTED  152 obs
SUIG     COLLECTED      15 obs  us-gaap      COLLECTED   39 obs
```

**`gross_profit x FINANCE_SERVICES`: refuted by three of seven.** A savings and
loan holding company reporting a gross profit subtotal is the ordinary case, not
an exception -- the same finding as NRIM, from the same SIC major group one
division over.

**`operating_income x FINANCIAL`: refuted for `FINANCE_SERVICES` by six of seven,
666 observations.** And this one says the most: `operating_income` for `BANK`
remains **0 of 8**, while for `FINANCE_SERVICES` it is 666. **The same metric,
the same mapped concept -- silence in one class and a complete series in the
other.** The original reasoning said a financial institution's operating result "is
not an operating-income concept"; a credit union, a mortgage banker and a savings
and loan holding company all report it. The sentence was about banks and was
written as a statement about finance.

By the 0.29 lifecycle, `REFUTED` forbids use as a refusal rule -- so removing them
is executing that rule, not making a new decision. Both `FINANCE_SERVICES`
exclusions are gone and `operating_income` was **narrowed to `BANK`** rather than
deleted, because `BANK` was not refuted and narrowing is what the evidence
supports.

**What is left in the entire registry: one exclusion.**

```
operating_income   NOT_APPLICABLE   for   BANK
```

Eight banks, none tagging `us-gaap:OperatingIncomeLoss`. Consistent with the rule,
does not support it, so it stays `TESTABLE`.

### The prediction, verified

```
FINANCE_SERVICES  gross_profit      AIXC/SLNHP/SUIG COLLECTED, four SOURCE_SILENT
                  operating_income  six COLLECTED, FMCCH DELIBERATELY_DECLINED
BANK              operating_income  eight NOT_APPLICABLE, 0 obs
semantic conflicts across both corpora: 0
```

**705 observations that were collected-then-refused are now simply collected.**
Nothing newly fetched, nothing discarded, and the refusal surface went from three
exclusions to one **without a single line of ingestion code changing** -- which is
0.29's invariant: **changing a semantic interpretation must not change Evidence.**

Conflicts are zero for the same reason as in 0.29: a conflict is a statement about
a rule, and there is no longer a rule to contradict.

### What this sequence established

| rule | class | filers | outcome |
| --- | --- | --- | --- |
| `gross_profit` NOT_APPLICABLE | BANK | 8 | **REFUTED** -- NRIM, 22 obs |
| `r_and_d` NOT_APPLICABLE | MINING | 4 | **REFUTED** -- NEM, 236 obs |
| `gross_profit` NOT_APPLICABLE | FINANCE_SERVICES | 7 | **REFUTED** -- 3 of 7, 39 obs |
| `operating_income` NOT_APPLICABLE | FINANCIAL | 15 | **REFUTED for FINANCE_SERVICES** -- 6 of 7, 666 obs |

**Four refutations, zero supports, one rule left standing on consistency alone.**
Not one of these was argued; every one was contradicted by a filer within the class
it was written about.

And the mature practice is the opposite of what a rule-based screener does:

> Not "no counterexample found, therefore add the rule." But: **propose a
> falsifiable rule first, then decide in advance what evidence would support or
> refute it.**

`CONDITIONAL` remains unnecessary. `SOURCE_SILENT` already expresses what a filer
did not report, and it is not work to do.

### Two points preserved

**IPB has no `companyfacts` document at all.** EDGAR returns 404. That is not a
filer reporting no gross profit; it is a filer with no aggregated fact document, and
it is recorded as the absence of the document rather than as silence about a
concept. Six of seven is the honest sample.

**Availability precision stays a first-class distinction.** `FILED_AS_OF_DATE` is
1.4% of the bank corpus, 49.4% of MINING/INSURANCE, and 9.9% here. The spread is
the argument: "the source has only a filed date" is a minority on young filers and
a plurality on old ones, so it must not be converted to a timestamp for
convenience, and the further back in history a consumer looks the more its PIT
precision should be visible to it.

The 540 divergent against the 75-issuer reference decompose to a single cause --
`reference holds the pre-fix midnight fabrication` -- the third time.

### State

Full suite **643 passed**, 74 skipped, 717 run. Production change:
`registry_seed.py` only. Registry exclusions remaining: **1**. All three corpora
re-run and statuses verified against the prediction; PIT invariant holds on all
three; equivalence still 11,174 / 11,174. Eight tests failed after the edit, all
asserting the two removed exclusions -- the correct failure direction, since the
rewritten tests now say `gross_profit` is applicable to every financial class and
`operating_income` is refused for `BANK` alone.

`operating_income x BANK` has been asserted false by no filer in seven rounds, so
the one rule left standing is also the one whose justification is weakest. Its
remedy is named and is not a code change: **a bank that reports operating income**
refutes it, and eight that do not, do not support it.
## 0.31 Only SUPPORTED may refuse, and nothing does (2.26)

2.24 left open whether a `TESTABLE` rule could keep refusing collection. It
could -- which meant an unsupported hypothesis held **production authority over
Evidence**, the same defect as a screening heuristic wearing a rule's clothes,
except that this one also edited the archive's coverage surface.

```
PROPOSED / TESTABLE / UNDECIDED   ->  may not refuse
SUPPORTED                          ->  may refuse
REFUTED                            ->  must not refuse
```

### The change

`metric_inapplicable_in` and `metric_exclusion` were one table doing two jobs:

```
metric_exclusion        a proposition, its state, its falsifiable claim, and who
                        refuted it. Recorded whatever the state.
metric_inapplicable_in  the refusal surface. Only SUPPORTED reaches it.
```

Migration `0015` carries any existing row over as `TESTABLE` -- a rule written in
2.7 with no evidence claim recorded is exactly what "testable, never tested"
means -- and then empties the refusal surface. Nothing is deleted; the hypotheses
stay queryable. A refusal can now only come into existence by an explicit act,
`registry.support_exclusion(metric, model)`, which is deliberately not a data
edit: refusing Evidence collection is a decision, so it is made like one.

What survives:

```
metric_exclusion        {"operating_income": {"BANK": "TESTABLE"}}
metric_inapplicable_in  0 rows
```

### The four checks, on all three archives

```
corpus                          NOT_APPLICABLE   observations   held+visible
BANK x8                                    0          11,174        11,174
FINANCE_SERVICES x7                        0          12,489        12,489
MINING + INSURANCE x8                      0          16,351        16,351
```

**Evidence unchanged** -- every observation count identical to before, and every
observation held *and* visible, meaning no metric lost its collected count to a
refusal. **Coverage re-reflected** -- `NOT_APPLICABLE` is now **zero cells in
every archive**. **The collected-then-refused observations all survive**: 705 from
2.25, 258 from 2.24, 39 from 2.25 -- nothing was ever discarded, and every
round of refuting a rule turned collected-then-hidden into simply collected.

### What this makes of NOT_APPLICABLE

A much harder thing to be, without changing the vocabulary:

```
no rule                        -> the metric is asked
the source reports it           -> COLLECTED
the source has nothing          -> SOURCE_SILENT
the source has nothing and the
  line provably does not exist  -> NOT_APPLICABLE
a filer contradicts a refusal    -> CONFLICT
```

It no longer means *"an analyst would not expect this company to have this
number."* It means **ST-EVA has affirmative evidence that this metric is not part
of the issuer's core evidence.**

`TESTABLE` does not appear in the runtime coverage vocabulary at all. It is a
**rule lifecycle state**, not an Evidence state, and keeping it out of the ledger
is what stops an open question from reading as a settled answer.

### The first generation of rules

**ST-EVA has no applicability rule with sufficient evidence to refuse anything.**
Four were written in 2.7 from category intuition; three were refuted by filers of
their own class; the fourth is unsupported and now refuses nothing. That is not a
failure of the rules -- it is the first honest result they could have produced,
and the alternative (promoting the survivor on eight silent banks) is the exact
move the `SUPPORTED` bar forbids.

### Cost, stated rather than assumed

Three classes now answer `SOURCE_SILENT` each time their filing universe moves,
where a refusal would have stopped asking. Real recurring work, and **not** a
coverage debt: `NOT_YET_COLLECTED` is the only status that means work to do, and
these cells are handled -- the source was asked and had nothing. The saving that
matters is quieter: the coverage surface stopped asserting things it could not
support, and an answer nobody can defend is worse than a question that is
recorded and visible.

### State

Full suite **637 passed**, 74 skipped, 711 run. Production changes:
`core_registry` (hypothesis layer, `support_exclusion`, `exclusion_states`),
`registry_seed`, migration `0015`. Refusal surface **0 rows** across every
archive. Open propositions: 1. `NOT_APPLICABLE` cells **0** in all three corpora,
from 8 before. Evidence unchanged in all three. Equivalence 11,174 / 11,174.
PIT invariant holds on all three.

Thirteen tests failed when this landed, all exercising a refusal the seed no
longer provides -- the correct failure direction. Every one now creates its
refusal explicitly through `support_exclusion`, so the semantics of
`NOT_APPLICABLE` are tested against a refusal somebody made rather than one nobody
remembers making.

One migration bug worth recording: the first version of `0015` read and deleted
`metric_inapplicable_in` before creating it, because that table was created
lazily by the registry rather than by a migration. It broke 286 tests, which is a
good ratio. Making the refusal surface part of the versioned schema rather than an
artefact of a write is the right fix regardless.


## 1. Objective

ST-EVA is a market-implied assumptions engine.

Primary question:

Given the observed market price, what earnings or valuation assumptions are required for that price to be consistent with an explicit valuation reference?

The engine is descriptive and conditional. It is not a price-target or trading-signal engine.

## 2. Analytical hierarchy

### Observed

Examples:

- current market price;
- current, forward, or consensus EPS supplied by a source;
- historical P/E, P/FCF, P/S, and EV/EBITDA bands;
- current FCF, EBITDA, revenue, enterprise value, and market cap when sourced;
- price and volume history;
- event date supplied by a source.

### Derived

Examples:

- current P/E;
- forward P/E;
- consensus forward P/E;
- implied forward EPS;
- EPS gap;
- required EPS CAGR;
- historical P/E position;
- price at consensus EPS times historical median P/E.

### Conditional inference

Every reverse-engineered figure is conditional on an explicit valuation reference.

Example:

P0 = 425.50
Reference P/E = 30x
Implied forward EPS = 425.50 / 30 = 14.18

Correct interpretation:

14.18 forward EPS is implied conditional on a 30x reference multiple.

Incorrect interpretation:

The market expects EPS of 14.18.

## 3. Forbidden behavior

The core engine must never:

- invent EPS;
- invent consensus;
- infer probabilities without explicit source data;
- create Bull/Base/Bear prices from arbitrary percentage multipliers;
- convert unavailable fundamentals into synthetic values;
- output a buy/sell recommendation;
- silently select a valuation reference without reporting it.

## 4. Reference multiple

Priority:

1. User-supplied reference_multiple.
2. Historical P/E median supplied by the data source.
3. No reference.

If no reference is available, observed valuation can still be reported, but reverse-engineered EPS and growth remain null.

### 4.1 Historical band quality gate

A historical valuation band may act as a reference only when it reports at least
`MIN_BAND_OBSERVATIONS_FOR_REFERENCE` (20) observations.

A band below the threshold must not silently become the reference multiple and
must not produce a percentile reading. The engine reports it as
`DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS` in `reference.historical_band_status`
and leaves the dependent reverse-valuation outputs null.

Precision is not evidence. A percentile distribution computed from too few
observations is not a defensible reference, regardless of how many decimal places
the median carries.

A band that declares no `observations` field is treated as usable. This preserves
static regression fixtures and explicitly supplied reference bands.

## 5. Formulas

Current P/E:
P0 / current_eps

Forward P/E:
P0 / forward_eps

Consensus forward P/E:
P0 / consensus_forward_eps

Implied forward EPS:
P0 / reference_multiple

EPS gap versus consensus:
implied_forward_eps / consensus_forward_eps - 1

Required EPS CAGR:
(implied_forward_eps / current_eps) ^ (1 / horizon_years) - 1

Consensus price at historical median:
consensus_forward_eps * historical_pe_median

Price gap versus that reference:
consensus_median_price / P0 - 1

## 6. Multi-method valuation

The deterministic engine consumes fundamentals through a provider abstraction.
The Yahoo implementation may supply trailing EPS, forward EPS, forward-year
consensus EPS, and an observed historical trailing P/E distribution. Each field
is source-derived and timestamped where Yahoo exposes the information.

The engine's input surface is `ValuationInputs`, a provider-agnostic projection
of the observations. It names metrics and values; it contains no provider field
names, endpoints, or wire structures, so the calculation core does not depend
on any single provider's shape. A Yahoo field name survives only as the
`methodology` of an observation.

Consensus EPS must come from an explicit estimate source. Forward EPS must
never be reused as consensus merely to fill a missing field. Historical P/E
statistics must be calculated only from retrieved observations, and the
samples behind a band are preserved so the statistics can be recomputed.

Provider failures or unavailable fields do not trigger fallback estimates. They
remain unavailable.

## 7. Missing-data policy

Missing inputs are represented as UNAVAILABLE at the raw-data layer and null in numeric derived output.

No fallback guess is allowed.

A provider failure must degrade to UNAVAILABLE, never to an exception that aborts
acquisition. Partially acquired data remains usable; the failure is recorded.

## 8. Evidence policy

Every material source input receives an Evidence ID.

Invalid evidence references are validation errors.

Evidence unit must describe the value actually carried. Valuation bands are
multiples (`unit = "multiple"`), not currency amounts.

An evidence row references its observation rather than copying a value, so the
raw observation survives by construction. A duplicate evidence ID is refused; a
duplicate metric reported by two providers is preserved, not collapsed.

## 8.1 Cross-source evidence states

A cross-source verdict is one of `CONSISTENT`, `DISCREPANT`,
`METHODOLOGY_MISMATCH`, `PERIOD_MISMATCH`, or `UNAVAILABLE`.

Two values that are not comparable must not receive a numeric verdict. A
difference between two figures that answer different questions is arithmetic
noise, and reporting it as a discrepancy would train a reader to ignore the
real ones. `PERIOD_MISMATCH` and `METHODOLOGY_MISMATCH` are both "these cannot
be compared" states, and neither asserts that a figure is wrong.

Agreement between a vendor and a filing is not automatically corroboration. A
vendor that ingests the filing will agree with it by construction, so the
independence of a comparison is declared alongside the verdict, and
`VERIFIED` remains uncomputed until a third independent source exists.

## 9. Data quality reporting

Every run reports a `data_quality` block containing `discrepancy_status`,
`acquisition_errors`, and `consensus_forward_eps_period`.

`discrepancy_status` is an evidence state, not an investment rating. A live
acquisition from a single provider is `UNVERIFIABLE`: one source cannot
cross-validate itself, and the engine must not present its output as verified.

Provider errors must be propagated to the caller. Collecting errors internally and
discarding them is a defect.

Per-observation validation states are recorded in the snapshot
`data_contract` block. The `VERIFIED`, `CONSISTENT`, `DISCREPANT`, and
`METHODOLOGY_MISMATCH` states are declared in the vocabulary but are not
computed in 2.3-A, because assigning them requires a second source.

## 10. Snapshot policy

Analysis snapshots are append-only at the application level.

Outcome records are separate files and never modify the original analysis snapshot.

Artifacts produced by the pre-2.2 framework are retained under `history/legacy-v6/`
and must not be presented as current engine output.

## 11. Future extensions

Possible later modules:

- multi-provider consensus acquisition;
- event-window outcome calibration;
- optional LLM interpretation layer.

These must remain separate from the deterministic calculation core.
