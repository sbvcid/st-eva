# The research calculation lane

A research lane computes a named figure from filed evidence that the
production qualification regime does not admit. It does so without touching
that regime. This document states what a lane is, what it may and may not do,
and how it is kept separate from production.

The lane is implemented in `research_lane.py`. The first case, KO, is in
`research_lane_ko.py` and is described in
[RESEARCH-LANE-KO.md](RESEARCH-LANE-KO.md).

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
| R-6 | An element change is a basis break, not a continuity. Where a filer changes the element it uses for a line, the lane reads the successor element and records the break on the observation. |
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
| `ResearchDistribution` | The sample size, the sample period, the statistics, the per-observation exclusion reasons, the research-use limits, and `production_eligible` fixed to `False`. |
| `ResearchLaneResult` | The input set id, the content hash, the formula version and the whole package. |

## The refusals

The lane has its own closed set of refusal codes. A production code is never
renamed into it: the conditions are different, and a lane must be able to say
that a figure was refused for a reason the production vocabulary has no word
for. An unknown code is an error, not a refusal.

| Code | Meaning |
|---|---|
| `RESEARCH_REASON_MISSING_PRICE` | No price is observed for the trading day. |
| `RESEARCH_REASON_MISSING_SHARES` | No cover-page share count is knowable at the evaluation date. |
| `RESEARCH_REASON_NO_DENOMINATOR_WINDOW` | The denominator's four-quarter window is not knowable at the evaluation date. |
| `RESEARCH_REASON_FISCAL_POSITION_UNRESOLVED` | The denominator's roles do not share a fiscal anchor, so no single trailing figure is built from them. |
| `RESEARCH_REASON_NON_POSITIVE_DENOMINATOR` | The trailing denominator is non-positive; no multiple is produced from it. |
| `RESEARCH_REASON_INCOMPLETE_EV_BRIDGE` | A filed bridge component is not knowable at the evaluation date. The bridge is never completed by omission or zero-fill. |
| `RESEARCH_REASON_MIXED_BALANCE_SHEET_PERIODS` | The bridge's components describe more than one balance-sheet date. The stale component is not carried forward. |

Every refusal carries a readable reason that names what was missing.

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

- `input_set_id` is the canonical hash of the lane's configuration, the
  SHA-256 of every capture file it read, and the evidence of the isolation
  check.
- Each observation carries a `content_hash` over its own content.
- The result's `content_hash` is the canonical hash of the input set id and
  the observation hashes.

The same capture and the same logic version produce the same identity.

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

## Running a lane

```python
from research_lane_ko import build_ko_research_lanes

for result in build_ko_research_lanes():
    print(result.metric_id, result.distribution.sample_count,
          result.distribution.percentiles.get("median"))
```

To write the research tree:

```python
from pathlib import Path
from research_lane_ko import write_ko_research_outputs

write_ko_research_outputs(Path("data/research_lanes/KO"))
```

To rebuild the capture from its sources:

```
python tools/build_ko_research_capture.py --as-of YYYY-MM-DD
```

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

The four candidate research metrics are the selectable ones. The diagnostic
lane is not a metric and cannot be selected: asking for it by name is a
refusal, not an empty result.

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
