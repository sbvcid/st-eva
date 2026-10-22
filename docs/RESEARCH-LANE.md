# The research calculation lane

A research lane computes a named figure from filed evidence that the
production qualification regime does not admit. It does so without touching
that regime. This document states what a lane is, what it may and may not do,
and how it is kept separate from production.

The lane is implemented in `research_lane.py`, and the issuers it carries are
described in `data/research_issuers.json`. The first case, KO, is documented in
[RESEARCH-LANE-KO.md](RESEARCH-LANE-KO.md); the second, AAPL, in
[RESEARCH-LANE-AAPL.md](RESEARCH-LANE-AAPL.md).

## Why a lane exists

The production regime refuses a figure for two different reasons, and it
treats them alike: the figure cannot be published.

- The **evidence** does not support it. The window is not continuous, the
  fact was not knowable at the evaluation date, the balance-sheet components
  do not describe one balance sheet, or the sample is too thin. These
  refusals are correct and the research lane repeats them.
- The **registry** does not accept the element. The filed fact is sound; what
  fails is the registry's naming of it, for this metric, for this filer. The
  filed values stay held as evidence, and no figure is built from them.

The second kind of refusal is sometimes a naming problem that a research
metric can solve honestly, because a research metric is allowed to say what
it actually reads. KO's revenue is the worked example: the registry retired
`us-gaap:Revenues` as a source of the `revenue` metric in decision 2.99,
because the element's own definition is broader than the metric, and the
registry's accepted revenue element is not filed by KO at all. The filed
figures are sound. What is missing is a name that is true of them.

A lane supplies that name, and nothing else. It does not relax the point in
time rule, the fiscal window rule, the filed enterprise-value bridge rule,
or the sample-size rule. It does not relax the registry, and it does not
extend it.

## The separation

Four mechanisms keep a research lane out of production. Each is checked.

**The names.** A research metric id begins with `RESEARCH_` and is not a
production metric id; a research basis is not a production basis.
`assert_research_isolation()` reads `archive.PRODUCTION_REFERENCE_BASES` and
`investment_context.REFERENCE_SOURCES` and refuses to run when a research id
collides with a production name. The check is against the production
vocabularies as they are in the repository, at run time, not against a
restatement of them.

**The gate.** A lane reads the registry's standing on every element it uses
and records it on every observation, but the standing never decides the
arithmetic. A registry refusal is a fact about the element, carried on the
observation so a reader can see exactly why a research figure is not a
production figure.

**The flag.** `ResearchDistribution.production_eligible` is fixed to `False`
by the type: it is declared with `init=False` on a frozen dataclass, so it
cannot be set at construction and cannot be changed afterwards. No code path
can turn a research distribution into a production reference by forgetting a
check.

**The destination.** A lane reads a capture and returns a result. The caller
decides where the result goes, and the only destination the repository
supports is the research tree under `data/research_lanes/`. A lane never
writes an Archive, never produces a `refc:*` row, never reaches an Investment
Context, and is never read by the production runner.

## The methodology

`research-multiples/1.0`. Nine rules.

| Rule | Statement |
|---|---|
| R-1 | The point-in-time rule is the production rule. A fact is knowable only from its filing's usable date under the 16:00 ET cutoff, the value in force at an evaluation date is the latest knowable version, and a price is the as-traded close of the evaluation date. |
| R-2 | The window is the production window: four consecutive fiscal quarters containing a Q4, anchored on the greatest fiscal position with knowable evidence, refused rather than backfilled. |
| R-3 | The registry's standing on every element is read and recorded on every observation, and it never decides the figure. |
| R-4 | A research metric names its own quantity. A research figure is never a production metric under another name: the metric id says what the denominator is, and the formula is carried on every observation. |
| R-5 | The filed balance-sheet bridge keeps the production rules: every component must be knowable at the evaluation date, every component must describe one balance-sheet date, and the bridge is never completed by omission, substitution or zero-fill. |
| R-6 | An element change is a basis break, not a continuity. Where a filer changes the element it uses for a line, the lane reads whichever element is in force at the evaluation date and records the break on the observation: on the observation whose window reads from more than one element, on the observation whose quarter is derived from spans of two elements, and on the observation where the element the line is carried by changes. The break states, from the capture, whether the two elements file the same amount for the periods they share, so a reader can see whether the filer re-tagged the same figure or moved the figure as well. |
| R-7 | Every observation carries the accessions, elements, spans, periods, units, usable dates and the operands the figure was computed from, so the figure can be recomputed from the evidence rather than trusted. |
| R-8 | The result is descriptive. A lane states its sample size and its sample period, and it never asserts production eligibility. |
| R-9 | A revision of a value already known for a prior period is detected and recorded rather than absorbed. |

The arithmetic the lane borrows is the arithmetic that must not be
re-invented: the discrete-quarter derivation, the trailing-window walk, the
usable-date rule and the as-traded close restoration. They are imported from
`historical_pfcf.py`, `historical_pe.py` and `fiscal_calendar.py`, not copied.
A research figure and a production figure built from the same filed facts
agree on the window and disagree only where the production gate says they
must. `tests/test_research_lane.py` pins that: over the same capture, the
two produce the same price, the same share count, the same market
capitalisation, and the same enterprise value on every date at which both
bridges are complete.

## The data model

Five objects.

| Object | What it carries |
|---|---|
| `ResearchRole` | A quantity, the elements it may be read from in the filer's own chronology, the formula role, the registry metric it would be read for, the kind of element change, and its sign in the bridge. |
| `ResearchLaneConfig` | The lane's identity, the issuer, the research metric id and label, the capture, the formula and its version, the numerator and denominator, and the research purpose. |
| `ResearchObservation` | One evaluation date: the value or the refusal, the price, the share count, the market capitalisation, the enterprise value, every denominator quarter with its accessions and its input spans, every bridge component with its element, value, period end, accession, filed date, usable date, unit and source file hash, the registry standing of every role, the basis breaks, the prior-period revisions, the formula with every operand, the run identity and the content hash. |
| `ResearchDistribution` | The sample size, the sample period, the statistics, the per-observation exclusion reasons, the basis the figure rests on, the homogeneous sub-samples the lane's published observations fall into, the research-use limits, and `production_eligible` fixed to `False`. |
| `ResearchLaneResult` | The input set id, the content hash, the formula version and the whole package. |

## The distribution's basis

A role names a quantity and the filer's own chronology of the elements it
filed that quantity on, so two of a lane's published observations may rest on
different elements. A median over both would be a statistic over a sample
that is not one kind of figure.

The lane therefore groups its published observations by their **basis**: the
elements each denominator role's window was read from, read from the
observation's own evidence and not from the issuer's configuration. Each group
states its own valid count, its own refusals, its own statistics and its own
status, and a group is one of two kinds:

| Kind | What it is | What may be published over it |
|---|---|---|
| `SAMPLE` | Every window in the group read a single element for every role. | A median, a mean, a period, and a status: a distribution at the lane's threshold, or a thin sample below it. |
| `DIAGNOSTIC` | Some window in the group read more than one element, so the figure is on neither element alone. | Nothing. The observations are kept with their evidence and their basis breaks, and no statistic is published over them. |

The distribution's own figure is the largest `SAMPLE` group, and it says which
group that is: the `basis` field names the elements the median rests on, and
`basis_groups` lists every group with its own count and status. The published
observations that are not in the figure are not pooled into it: they are
counted in `published_observation_count` and described in their own groups. A
group below the lane's threshold says so; the threshold is not relaxed, and
the lane does not fall back to a statistic over the mixed observations.

The status of a distribution is one of `RESEARCH_DISTRIBUTION` (the sample is
at the lane's threshold), `RESEARCH_THIN_SAMPLE` (it is below it),
`RESEARCH_UNAVAILABLE` (there is no figure to describe) or
`RESEARCH_DIAGNOSTIC` (the group is a diagnostic). The lane's own versions
are `research-multiples/1.0.0` for an observation and
`research-multiples/1.1.0` for a distribution's construction: an observation
is the figure and the evidence it was computed from, and neither changes when
the way a distribution is assembled changes.


## The refusals

The lane has its own closed set of refusal codes. A production code is never
renamed into it: the conditions are different, and a lane must be able to say
that a figure was refused for a reason the production vocabulary has no word
for. An unknown code is an error, not a refusal.

### The lane's observation refusals

| Code | Meaning |
|---|---|
| `RESEARCH_REASON_MISSING_PRICE` | No price is observed for the trading day. |
| `RESEARCH_REASON_MISSING_SHARES` | No cover-page share count is knowable at the evaluation date. |
| `RESEARCH_REASON_NO_DENOMINATOR_WINDOW` | The denominator's four-quarter window is not knowable at the evaluation date. |
| `RESEARCH_REASON_FISCAL_POSITION_UNRESOLVED` | The denominator's roles do not share a fiscal anchor, so no single trailing figure is built from them. |
| `RESEARCH_REASON_NON_POSITIVE_DENOMINATOR` | The trailing denominator is non-positive; no multiple is produced from it. |
| `RESEARCH_REASON_INCOMPLETE_EV_BRIDGE` | A filed bridge component is not knowable at the evaluation date. The bridge is never completed by omission or zero-fill. |
| `RESEARCH_REASON_MIXED_BALANCE_SHEET_PERIODS` | The bridge's components describe more than one balance-sheet date. The stale component is not carried forward. |
| `RESEARCH_REASON_ELEMENT_UNAVAILABLE` | The capture holds no element for a role the lane reads, or holds only some of the elements the role names. The lane refuses rather than read the subset the capture happens to carry, because a figure computed from a smaller set of elements is a different figure from the one the role names. |
| `RESEARCH_REASON_NO_HOMOGENEOUS_SAMPLE` | The lane's published observations do not rest on one element, so there is no sample to describe and no median to publish. The observations are kept as traceable research observations, and they are not pooled into a single figure. |

Every refusal carries a readable reason that names what was missing.

Two refusals are raised before the lane computes anything, because they are
properties of the capture and the configuration rather than of an evaluation
date: a role that names an element the capture does not hold, and a capture
whose declared normalisation disagrees with the unit policy. Both are results
with their reason, not exceptions.

### The calculation's refusals

The calculation service has its own closed set, separate from the lane's
observation refusals, because the conditions are different: the lane refuses
an observation, the service refuses a calculation.

| Code | Meaning |
|---|---|
| `RESEARCH_CALCULATION_REFUSED_METRIC_UNAVAILABLE` | No research metric carries that id. |
| `RESEARCH_CALCULATION_REFUSED_METRIC_NOT_SELECTABLE` | The metric is a research diagnostic, not a research metric. |
| `RESEARCH_CALCULATION_REFUSED_MULTIPLE_UNAVAILABLE` | The multiple does not exist: the metric has no median, or the observation has no value, or the user supplied none. |
| `RESEARCH_CALCULATION_REFUSED_MULTIPLE_NOT_POSITIVE` | The multiple is not greater than zero. |
| `RESEARCH_CALCULATION_REFUSED_MULTIPLE_NOT_FINITE` | The multiple is not a finite number. |
| `RESEARCH_CALCULATION_REFUSED_NUMERATOR_UNAVAILABLE` | The market value does not exist. |
| `RESEARCH_CALCULATION_REFUSED_NUMERATOR_NOT_POSITIVE` | The market value is not greater than zero. |
| `RESEARCH_CALCULATION_REFUSED_NUMERATOR_NOT_FINITE` | The market value is not a finite number. |
| `RESEARCH_CALCULATION_REFUSED_RESULT_NOT_FINITE` | Finite operands produced a quotient that is not finite. |
| `RESEARCH_CALCULATION_REFUSED_OBSERVATION_REJECTED` | The observation the user named was refused by the lane. |
| `RESEARCH_CALCULATION_REFUSED_OBSERVATION_UNKNOWN` | The metric has no evaluation on that date. |
| `RESEARCH_CALCULATION_REFUSED_DATA_IDENTITY_MISMATCH` | The capture does not match its own manifest. |
| `RESEARCH_CALCULATION_REFUSED_DENOMINATOR_UNAVAILABLE` | The denominator cannot be built. |

A non-finite operand is refused on **every** path into the service. The
request model refuses a NaN or an infinity at validation, and the service
refuses one itself, so a caller that reaches the service directly -- with no
HTTP model in between -- is refused as well. A finite pair whose quotient
overflows is refused too, and a non-finite result is never published as an
available figure: it is not turned into `null`, into `0.0`, or into any other
value that would look like a result.

## R-9: prior-period value revisions

The lane compares the version in force for the same role and the same fiscal
period across adjacent evaluation dates.

- A period that appears for the first time is a **first appearance**, not a
  revision.
- A version replaced by the same value is not a value revision.
- A version replaced by a **different value** is a prior-period value
  revision. The lane records the old value, accession and first-knowable
  date; the new value, accession and first-knowable date; the difference and
  its ratio; the observations whose trailing window the revision reaches; and
  whether the element changed.

The classification is neutral: `PRIOR_PERIOD_VALUE_REVISION`. The lane's
evidence shows that a value it already knew was replaced by a different
value. It does not show that the issuer formally restated, and it does not
say so.

A derived quarter is made by subtracting one cumulative span from another.
When one of those spans has been revised and the other has not, the quarter
is made of a pre-revision figure and a post-revision figure, and the quarter
is on neither basis. The lane records that condition on the observation
rather than absorbing it.

## The run identity

Four things are identified separately, and it is worth being exact about what
each one covers.

| Identity | Covers |
|---|---|
| `input_set_id` | The lane's identity -- its lane id, the issuer id, the research metric id, the formula version, the denominator roles and the numerator kind -- the SHA-256 of every capture file it read, and the evidence of the isolation check. |
| The capture manifest identity | The manifest describes the capture: the issuer, the capture date, the source of each file, its unit, its normalisation and its digest. The manifest is **not** part of `input_set_id`, so a change to a description alone is not a change to the calculation. |
| The policy identity | The unit policy the lane was configured with -- the unit the filings are stated in, the currency, the price's currency, the share unit, the scaling factor and its basis, and the currency conversion rule -- and the registry's standing on every element each role reads. The unit policy is recorded on the distribution; the registry's standing is on every observation. |
| The calculation hash | Each observation's `content_hash` is the canonical hash of that observation's own content, and the result's `content_hash` is the canonical hash of the input set id and the observation hashes. |

The consequence is that a policy change is always visible, in one of two
places, and never silent:

* A change to the capture's **bytes** -- a different unit, a different
  normalisation, a different element -- moves the file digests and therefore
  the `input_set_id`.
* A change to the **configuration** that the capture does not carry -- a
  different unit policy, a different element in a role -- moves the policy
  record and the observation's registry standing, and therefore the
  observation's `content_hash`. A role element the capture does not hold is
  refused outright rather than read around.
* A change to the capture's **description** alone moves neither, because the
  manifest is not part of the input identity.

The same capture and the same logic version produce the same identity.

### The capture and the policy must agree

A capture states, per role, the unit it holds its amounts in and the factor it
applied to the filed amounts. The configuration states the unit the issuer's
figures are in and the factor the capture is to apply. When the two disagree,
the figures the lane would compute are not the figures the policy describes,
and the lane refuses with `RESEARCH_REASON_UNIT_CONFLICT` before it computes
anything. That is what keeps "the policy changed but the identity did not" from
being possible: a policy that disagrees with the capture produces a refusal,
and a refusal has its own identity.

The capture states its normalisation in two places: the concept file's own
`normalisation` block, which is inside the file and so covered by the file's
digest, and the manifest's copy of it, which describes the file. The lane reads
the file's own block, checks it against the policy, checks the manifest's copy
against the policy, and checks the two against each other. A capture whose
description and whose files disagree is refused rather than one of the two
being adopted silently, and re-describing a capture cannot paper over a
mismatch the files themselves carry.

A share count is a count, not an amount. The unit policy's scaling factor
applies to the issuer's amounts and never to the cover-page share count: a
capture that scaled the count would hold a thousand shares for every share
filed, and would cancel the scale out of a market-capitalisation multiple
instead of stating it.

## Replay: two contracts, not one

"Reproducible" means two different things here, and the repository keeps them
apart.

**A replay over fixed inputs.** The committed capture files and the committed
configuration are the inputs; the lane recomputes the canonical observations,
the lane outputs, the `input_set_id`, the `content_hash` and every
observation's hash from them, without reaching the network. The same inputs
give the same figures and the same hashes, and the replay leaves the capture
untouched. `tests/test_research_lane_boundaries.py` runs the replay with the
network refused and compares the result against the committed tree.

**A re-download of the sources.** The SEC and the price provider answer again,
and their answers are not the same bytes: the price payload carries the
provider's live metadata, and the acceptance index records the digest of a
header page the SEC regenerates. A re-download is therefore a **new snapshot**,
not a replay, and it is not required to match the old one byte for byte. What
it does produce is evidence: the element rows of a rebuilt capture are
identical to the committed capture's when the sources have not moved, and the
files whose bytes have moved are named by their digests.

The manifest is a function of the files it describes: a manifest written from
the same files is the same manifest, so the manifest can be re-derived offline
and the capture's identity does not depend on when it was described. What the
manifest cannot do is stand in for the files. The lane verifies every file
against its recorded digest before it reads anything, and a capture whose
bytes have changed since it was built is refused rather than read.

## The capture

A capture is a versioned, hashed directory holding only what the lanes read:
the daily price series, the filing acceptance index, the cover-page share
counts, and the filed concept elements each role may be read from. It lives
under `data/research_*`, never under a production `data/historical_*` path,
and every file records where it came from, how it was retrieved, and the
SHA-256 of the bytes it was built from.

The capture's acceptance index covers the issuer's periodic filings. A fact
first published in another form therefore becomes knowable in the lane at the
next periodic filing that carries it: the lane never uses a value before it
was public, and it may use a value later than it first became public. That
is a capture-scope decision, and it is stated in the capture manifest and in
every lane's data limitations.

The SEC facts APIs publish facts without dimensional qualifiers and do not
publish a filing's context reference. Each row's context is therefore pinned
by `(accession, element, period, unit)` with no dimensions, which identifies
exactly one fact in that filing, and the capture states that in every file's
provenance.

### The acceptance times, and their time zone

The capture records when each filing was accepted, and that time is what
decides when the filing's facts become knowable. The SEC states the time in
Eastern local time and carries no offset, and Eastern local time is not a
fixed offset: a standard-time filing is five hours from UTC and a
daylight-time filing is four. The capture therefore takes the offset from the
region, not from a constant, so that the recorded instant is the instant the
SEC states. A capture that writes a fixed offset records an instant an hour
early for every winter filing, and a filing accepted between 16:00 and 17:00
Eastern then appears to be knowable a trading day before it was.

The capture's own manifest records, for every filing, the acceptance
datetime the SEC's submissions API states, and the usable date the rule
gives. `tests/test_research_capture.py` pins the conversion in both seasons
and pins the usable dates the capture produces, so a change to the
representation cannot quietly move a filing's knowability.

### The two clocks, and which one the lane uses

The SEC states a filing's acceptance time twice: in the filing's own SGML
header, and in the submissions API. **They do not always agree.** For AAPL the
submissions API serialises the same instant with the eastern offset applied
twice, so it runs four hours late in summer and five hours late in winter;
KO's filings do not show the difference. The header agrees with what EDGAR
itself displays on the filing's index page, and it agrees with the fact that
the SEC accepts filings between 06:00 and 22:00 Eastern -- an API-derived
time of 01:29 in the morning would be outside the window in which a filing can
be accepted at all.

The lane therefore uses the header's own `ACCEPTANCE-DATETIME`, and the
capture records both: the header's time, the API's time, and the difference
between them in hours, so the divergence is visible in the capture rather than
buried in it. The capture builder reads the header from the filing's
`-index-headers.html` when the SEC generates one, and from the full
submission's own SGML header when it does not; both shapes are parsed, so a
filing whose index header is not retrievable still yields its own acceptance
time.

A capture built before that fix may hold the API's time for the filings whose
index header does not exist. KO's committed capture does, and for KO the two
clocks agree to the second, so its instants are the same either way; AAPL's
capture was built after the fix and holds the header's time for every filing.

## Running a lane

```python
from research_issuers import build_lane_results

for lane_id, result in build_lane_results().items():
    print(lane_id, result.distribution.sample_count,
          result.distribution.percentiles.get("median"))
```

To write the research tree:

```python
from pathlib import Path
from research_issuers import write_research_outputs

write_research_outputs(Path("data/research_lanes/KO"), issuer_ids=["KO"])
write_research_outputs(Path("data/research_lanes/AAPL"), issuer_ids=["AAPL"])
```

To rebuild an issuer's capture from its sources:

```
python tools/build_research_capture.py --ticker KO
python tools/build_research_capture.py --ticker AAPL
```

The builder takes the element table, the sources, the earliest filed date and
the unit policy from `data/research_issuers.json`; there is no issuer-specific
builder and none is needed. The builder is not deterministic in its bytes: the
price payload carries the provider's live metadata and the acceptance index
records the digest of a header page the SEC regenerates. A rebuilt capture is
therefore evidence that the evidence behind the committed one is unchanged, not
a replacement for it.

## The issuer configuration

`data/research_issuers.json` is the only place an issuer's elements, roles,
formulas and units are written down. The capture builder and the research
lanes both read it, so an issuer is described once rather than twice.

It records, for each issuer:

* the identity -- the CIK, the ticker, the entity name and the fiscal year
  end;
* the capture -- its directory, the earliest filed date, the periodic forms,
  the price series, the order the element sources are tried in, and the
  element table, which is the single truth about which elements a capture
  role holds;
* the roles -- the capture role each one reads, the formula role, the
  registry metric the element would be read for, the kind of element change,
  the bridge sign and the bridge group, and the note that says what the
  element means for this filer;
* the unit policy -- the unit the filings are stated in, the currency, the
  price's currency, the unit the share count is in, the factor the capture
  scaled by and the basis for the scaling, and the conversion rule when the
  price and the denominator are in different currencies;
* the lanes -- the lane id, the research metric id, the name, the research
  purpose, the formula, the denominator and bridge roles, the numerator
  kind, the descriptive threshold and whether the lane is a candidate.

`research_issuers.py` loads it and checks it. A configuration that names a
role twice, a lane twice, a metric twice, a role the capture does not hold,
a lane that names a role the issuer does not declare, an unknown formula
role, an unknown bridge group, a metric that takes a production name, or a
missing file is refused with the field that is wrong. Nothing falls back to a
built-in issuer.

A lane whose capture has not been built is not offered as a metric. The
configuration may describe it, and the registry says so, but there is nothing
to compute from and the metric is not listed.

### The unit policy

A multiple is a market value over a financial denominator, so the two must be
in the same currency and the denominator must be stated in the unit the
policy names. A capture whose facts are stated in thousands is not the same
capture as one stated in units, and the difference is a factor of a thousand
rather than a rounding detail.

Before a lane computes, it checks that every role's unit is the unit the
policy names, that the share count is in the unit the policy names, that the
price series names the currency the policy names, and that the denominator's
currency and the price's currency agree or that the policy declares a
conversion rule between them. A lane that cannot state the units it reads
refuses to compute, and the refusal is a result with its reason rather than
an exception: `RESEARCH_REASON_UNIT_UNKNOWN`,
`RESEARCH_REASON_UNIT_CONFLICT` or
`RESEARCH_REASON_CURRENCY_MISMATCH`.

Every scaling is recorded: the unit the filer used, the factor, the unit the
capture holds, and the basis. The capture's manifest records it per role, and
the distribution records the policy and the units the facts were read in.

### The bridge groups

A bridge component says what it is -- `LONG_TERM`, `SHORT_TERM` or
`LIQUID` -- rather than what it is called. The comparison service reads the
group, so an issuer that names its short-term borrowings differently is still
compared correctly, and the attribution to a single component still requires
the other components and the denominator window to agree.

## The comparison and sensitivity service

`research_comparison.py` is the service a user works with when the question
is not "what is this metric" but "why do these two numbers differ, and what
may that difference rest on".

A comparison is an argument about two numbers, and the service answers three
questions before it shows anything.

### Are the two metrics the same kind of thing?

Every research metric publishes its comparability attributes: the kind of
numerator it divides by, the definition and elements of its denominator, the
currency and unit, its formula version, its bridge components, the registry's
standing on it, and the basis breaks it carries. Two metrics may be shown side
by side whatever they are, but a difference between them is only a statement
about something when their definitions agree.

| Pair | What it supports |
|---|---|
| The two enterprise-value lanes | A paired bridge comparison. They share their numerator kind, their denominator, their currency and their formula version, and differ only in the short-term component of the bridge. |
| Two metrics with different denominators | A side-by-side view, labelled as a difference between two different formulas. No single attribution is offered. |
| Two metrics with different numerators | The same, with the numerator difference named. |

The comparability record names every attribute that agrees and every one
that does not, so that a reader is never left to assume the two are the same
kind of thing.

### Are the two observations of the same thing?

A comparison across two evaluation dates of one lane requires both dates to
have published a figure. A date the lane refused is a refusal, with its
reason, not a gap to be filled in. The dates in between that were refused
are returned with their reasons, so that two figures are never read as a
continuous series. The comparison also reports what changed in the evidence
itself between the two dates: the elements each bridge read, the balance
sheet each bridge described, and whether the denominator window moved.

### Is the difference attributable?

For the two enterprise-value lanes, only the dates where both published are
paired. For each paired date the service checks that every component of both
bridges describes one balance-sheet date and was knowable at that date, that
the denominator window is the same version in both lanes, and that the
components other than the short-term one agree. Where they do, the
difference is the difference of the two short-term components, and the
service says so. Where they do not, the pair is marked as affected by other
factors, and the factors are named.

The paired sample count, the attributable count, the unpaired dates and the
reason each was refused are all computed from the observation records. The
number of paired dates is never assumed.

A difference between the two lanes' *medians* is not a measurement of
anything, because the two lanes publish on different dates. The paired
comparison, not the median difference, is what the service offers.

### The sensitivity analysis

A sensitivity asks how one published figure changes when one named input
changes. The assumptions are a closed, named set, and each one records its
name, its value, its unit and its own hash.

| Assumption | What it changes |
|---|---|
| `NUMERATOR_MULTIPLIER` | The market value, or the enterprise value, is multiplied by a factor. |
| `MULTIPLE_OVERRIDE` | The research multiple is replaced with a supplied one. |

A sensitivity may only be computed on a date the lane itself published, so
it cannot be used to get around a point-in-time refusal, a fiscal window
that does not exist, or an enterprise-value bridge that is not complete. The
observation is never modified: the sensitivity is a separate record that
names the assumption it makes, and it is not a forecast, a target price or
a fair value.

### The comparison routes

| Route | What it serves |
|---|---|
| `GET /api/research/definitions` | The comparability attributes of every selectable metric, and the named sensitivity assumptions. |
| `POST /api/research/compare/compatibility` | Whether two metrics may be compared, and on what basis. |
| `POST /api/research/compare/history` | One metric at two evaluation dates. |
| `POST /api/research/compare/bridges` | Two metrics on the dates where both published. |
| `POST /api/research/sensitivity` | One named assumption applied to one published figure. |

The comparison surface has its own state and its own metric selectors. No
metric and no date is chosen for the user, and a comparison that cannot be
made says why.

## What a lane may not do

- It may not publish under a production name, and it may not feed
  `PRODUCTION_PS_MEDIAN`, `PRODUCTION_EV_EBITDA_MEDIAN`, an Investment
  Context, the production Summary, or the production runner's valuation
  inputs.
- It may not treat an unreported value as zero, may not carry a stale
  balance-sheet component forward, may not use a value the evaluation date
  could not know, may not build a trailing figure from a wrong fiscal period,
  and may not obtain production standing from a small sample.
- It may not be offered as a way around the qualification rules. A research
  metric is a different quantity with its own name and formula, and the
  difference between the two lanes' medians is a difference of scope and
  sample, not a measure of anything the production regime declined to say.

## The research calculation

`research_calculator.py` is the service a user works with. It puts a user
in front of a lane: the user chooses a research metric, states a multiple
and a market value, and reads the figure that pair implies together with the
evidence behind it.

### Choosing a metric

The candidate research metrics are the selectable ones. A diagnostic lane is
not a metric and cannot be selected: asking for it by name is a refusal, not
an empty result.

Every metric carries its own name and formula, its valid and refused
observation counts, its sample period, its statistics, the registry's
standing on each element it reads, the reasons it does not have production
standing, its element chronology, its basis breaks and its known
limitations. None of them is presented as a price-to-sales or an EV/EBITDA
reference, because none of them is one.

### The reverse calculation

The service computes what a research multiple and a market value imply about
the financial denominator underneath them.

| Input | Where it comes from |
|---|---|
| The research metric | The user. There is no default, and a research result is never used as a valuation reference. |
| The multiple | The metric's own median, one of the metric's own observations, or a number the user supplies. |
| The market value | The lane's own market capitalisation or its own enterprise value on a named evaluation date, or a number the user supplies. |

The numerator is the lane's own. Lanes A and B divide a market
capitalisation; lanes C1 and C2 divide an enterprise value built from that
lane's own filed balance-sheet bridge. A calculation never mixes one lane's
numerator with another lane's denominator or sample.

A user-supplied multiple or market value is labelled
`user_supplied_research_assumption` and is kept apart from the observed
facts. The service does not offer a live market value: a live price cannot
be paired with the capture's historical share count or with a historical
bridge without splicing two different dates, so the traceable market value
is the lane's own, with its date and its data identity, or the user's own.

A calculation that cannot be made is refused with its own reason code, and
never falls back to a test figure or a stale one: a multiple that does not
exist, an observation the lane refused, a market value the lane does not
have, a non-positive operand, and a capture that does not match its own
manifest are each their own refusal.

### The evidence

Every result can be followed back to the filing it came from. The service
returns the operands, the formula and its version, the lane's input-set
identity and content hash, the calculation's own content hash, the accessions,
elements, periods, units, knowability and source-file digests behind the
numerator, the four denominator quarters with the accessions each was built
from, the balance-sheet components with their digests, the registry's
standing, the basis breaks and the value revisions, and the statement that
the result is not a production reference.

The same inputs and the same formula version give the same result. A change
of input or of data version changes the calculation's content hash, so the
difference is visible.

### The distribution's state, and the threshold it is read against

A distribution is in one of three states, and the surface tells them apart:

| State | What it means |
|---|---|
| `RESEARCH_DISTRIBUTION` | The metric holds enough valid observations to be described as a distribution. It is still a research figure, not a valuation reference. |
| `RESEARCH_THIN_SAMPLE` | The sample holds fewer valid observations than the lane's own descriptive threshold. The figures describe a small sample. The threshold is the lane's research setting, carried in the payload so a reader is told it rather than left to assume one; it says how much evidence a description rests on, and it says nothing about production eligibility, which is a separate field and stays `False`. |
| `RESEARCH_UNAVAILABLE` | The metric holds no valid observation, so no distribution is shown. The reason travels with the metric. |

The threshold is never hard-coded in the interface: it comes from the lane's
own setting, through the payload.

### The source of every input

Every input says where it came from, in what unit, and over what period, so
that a reader does not have to read a payload to find a source link.

| Input | What it carries |
|---|---|
| The price | The capture file, its digest, the provider URL, the currency, the accounting basis and the date the price applies to. |
| The cover-page share count | The capture file, its digest, the element's endpoint, the unit (`shares`), the cover date, the accession and the usable date. |
| Each denominator quarter and its input spans | The unit and currency, the period, the accessions, the file, its digest, the element's endpoint, and when each span became knowable. |
| Each balance-sheet component | The currency, the balance-sheet date, the accession, the filed date, the usable date, the file, its digest and the element's endpoint. |

A source the capture does not record is shown as not provided. Nothing is
guessed.

### The interface

`web/research_api.py` serves the research path at `/api/research`, mounted
before the single-page-application catch-all so its routes are matched on
their own terms. It starts no analysis job, writes no Archive, produces no
production reference and reaches no Investment Context.

| Route | What it serves |
|---|---|
| `GET /api/research/metrics` | The selectable research metrics and the notice that governs them. |
| `GET /api/research/metrics/{metric_id}` | A metric and every evaluation date behind it, published and refused. |
| `GET /api/research/metrics/{metric_id}/observations/{evaluation_date}` | The full evidence of one evaluation date. |
| `POST /api/research/calculate` | One research reverse calculation, with its evidence. |

The interface offers the metric selection, the metric's own figures, the
calculation, the result, and the evidence explorer: the table of every
evaluation date the lane made, with the refused dates and their reasons,
and the source chain behind any one of them. The research-only notice is on
the surface from the first moment, and it is not a warning line that can be
dismissed: the figure is structurally ineligible, and the surface says what
makes it so.

## The two cases

The engine is the same for both; only the configuration differs. Each case has
its own capture, its own tree and its own document.

| | KO | AAPL |
|---|---|---|
| Issuer | The Coca-Cola Company, CIK 0000021344 | Apple Inc., CIK 0000320193 |
| Fiscal year end | 31 December | The last Saturday of September: a 52/53-week year |
| Split in the price series's range | none | 7:1 on 2014-06-09 and 4:1 on 2020-08-31 |
| Capture | `data/research_multiples/KO` | `data/research_multiples/AAPL` |
| Results | `data/research_lanes/KO` | `data/research_lanes/AAPL` |
| Document | `docs/RESEARCH-LANE-KO.md` | `docs/RESEARCH-LANE-AAPL.md` |

AAPL is the case that tests the engine rather than the configuration: its
fiscal quarters are not calendar quarters, its share count changes scale twice
inside the sample, its revenue and depreciation elements both change tag, and
its commercial paper is filed on a different element in two quarters.
