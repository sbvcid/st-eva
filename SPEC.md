# ST-EVA 2.2.3 Specification

## 0. Data contract (2.3-A) and cross-source validation (2.3-B)

The data layer is defined by
[docs/ST-EVA-2.3-A-DATA-CONTRACT.md](docs/ST-EVA-2.3-A-DATA-CONTRACT.md).

    Provider -> Observation -> Evidence -> Validation -> Derived

`Observation` is a frozen, provider-agnostic record of one sourced value. It
carries metric, unit, currency, period_start, period_end, as_of, available_at,
provider, source_type, source_url, definition, methodology, and the raw
provider payload. `Evidence` binds an observation to an engine-facing ID.
`Validation` attaches a `ValidationStatus` to a value and can never write to
it. `Derived` values record the observations they consumed and can be
recomputed from them.

2.3-B adds the SEC as a second source for seven metrics, specified in
[docs/ST-EVA-2.3-B-SEC-VALIDATION.md](docs/ST-EVA-2.3-B-SEC-VALIDATION.md). Its
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
[docs/ST-EVA-2.3-C-INVESTMENT-CONTEXT.md](docs/ST-EVA-2.3-C-INVESTMENT-CONTEXT.md).
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
[docs/ST-EVA-2.4-POINT-IN-TIME-ARCHIVE-REPLAY.md](docs/ST-EVA-2.4-POINT-IN-TIME-ARCHIVE-REPLAY.md).
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
