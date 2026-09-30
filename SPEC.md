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
