# ST-EVA 2.5 — Core Evidence Scope

Status: SPEC. Design only. No production code is changed by this document.
Baseline: `667d05d`, `context_schema_version 2.3-C.2`
Predecessors: [2.3-A contract](ST-EVA-2.3-A-DATA-CONTRACT.md),
[2.3-B validation](ST-EVA-2.3-B-SEC-VALIDATION.md),
[2.3-C context](ST-EVA-2.3-C-INVESTMENT-CONTEXT.md),
[2.4 archive](ST-EVA-2.4-POINT-IN-TIME-ARCHIVE-REPLAY.md),
[2.4.3 completion](ST-EVA-2.4.3-COMPLETION.md)

## 0. What 2.5 is

> Turn ST-EVA from a system that produces one Context per run into a
> database that accumulates traceable financial Evidence over time.

The target pipeline:

```
Source -> Source Document -> Observation -> Validation -> Derived
       -> Evidence Database -> Query -> Context -> LLM
```

ST-EVA's job is the left half through the database: accumulate Evidence with a
stated provider, a located document, a publication time, a covered period, a
definition, and a basis. The LLM does the right half: interpretation,
comparison, scenario, valuation. ST-EVA does not decide the research method.

### 0.1 The governing principle

ST-EVA does not claim truth. It claims to be able to say, for any number it
holds:

> who provided this, from which document, published when, covering which
> period, under which definition and basis, and whether other evidence agrees,
> disagrees, or is silent.

Everything below follows from that. A number with no answer to those questions
is not Core Evidence, however useful it would be.

### 0.2 Position, restated

ST-EVA is not an investment analysis agent and is not a buy/sell, ranking,
fair-value, or forecasting system. It does not produce ratings, scores,
probabilities, or recommendations, and no Core Evidence item may be defined in
terms of one.

## 1. The definition of Core Evidence

An item is **Core Evidence** if and only if all four gates pass.

| # | Gate | Question | Fails when |
|---|---|---|---|
| G1 | **Public source** | Is it obtainable from a source anyone may lawfully read? | the only source is licensed, scraped against terms, or inferred |
| G2 | **Defined semantics** | Does the concept have a name a source states, not one we choose? | the definition would have to be invented, or two sources mean different things by the same word |
| G3 | **Preservable provenance** | Can provider, document, concept, period and publication time all be recorded and re-fetched? | the figure floats free of any document |
| G4 | **Reproducible** | Would a second person, given the record, get the same figure? | the value depends on our processing in a way we cannot state |

A fifth constraint applies to everything:

> **G5 — no derived judgement.** A Core item is what a source reported, not a
> ratio we computed about it, and not a conclusion we drew. Margins, growth
> rates, EBITDA, and multiples are Derived (§3.3), never Evidence.

**G2 is the gate that does the most work.** "Cost of Revenue" passes only
because a filer tags a cost-of-revenue concept. "Profitability" fails, because
no source states profitability as a fact about a company.

### 1.1 The legal states of a Core item

For any company and any Core item, exactly one of these is true. All are
normal results and none is an error.

| State | Meaning | Distinct from |
|---|---|---|
| `SOURCE_REPORTED` | a source stated it; the value exists | — |
| `SOURCE_DID_NOT_REPORT` | the source was consulted and does not state it | `UNAVAILABLE`: we failed to ask, not the source |
| `NOT_APPLICABLE` | the concept does not exist for this business | a missing value: the correct answer is that there is nothing to report |
| `UNAVAILABLE` | the source could not be reached, or the value was not extractable | `SOURCE_DID_NOT_REPORT`: the answer is unknown, not negative |
| `CONFLICTING` | two or more sources state materially different values, and no winner is selected | `DISCREPANT`: a discrepancy assumes comparability, a conflict does not |
| `STALE` | the newest observation for the item predates the source's cadence | the value is retained and recomputable; only its currency is absent |

**Why each distinction earns its place.** A single "missing" cannot tell a
consumer whether the company lacks the item, the source omits it, or our
retrieval failed, and those imply different next actions:

```
NU   EBITDA   NOT_APPLICABLE       BUSINESS_MODEL_NOT_MEANINGFUL
MU   debt      STALE                NO_RECENT_VALUE, newest filing 2013-05-30
NU   revenue   SOURCE_DID_NOT_REPORT the filing exists and omits the tag
AAPL whatever  UNAVAILABLE           the request failed
```

The first says *ask a different question*. The second says *go back to the
filings*. The third says *ask the filer*. The fourth says *retry us*.

`NOT_APPLICABLE` is the one state the current model cannot express, and it is
the most important addition. A bank has no operating-income tag and a mining
company has no inventory; recorded as a null, both are indistinguishable from
retrieval failure, and a database full of indistinguishable nulls is not
queryable.

## 2. What ST-EVA must retain

### 2.1 The eight questions every evidence record answers

Adapted from the "like a paper citation" standard.

| Question | Field | Source of truth |
|---|---|---|
| **What?** | `value`, `unit` | the source |
| **Who?** | `provider`, `filer` | the source |
| **Where?** | `document_ref`, `accession`, `section`, `concept`, `taxonomy` | the filing |
| **When?** | `available_at`, `filed_at`, `accepted_at` | EDGAR |
| **For what period?** | `period_start`, `period_end`, `instant` | the filing |
| **How defined?** | `definition`, `methodology` | the source, quoted not paraphrased |
| **What basis?** | `currency`, `basis` | the source, declared not inferred |
| **Corroborated?** | `validation`, `independence` | 2.3-B |
| **Reproducible?** | `provenance`, `raw`, `content_hash` | 2.4.1 capture |

### 2.2 Retained vs referenced

A distinction the current archive does not make, and which §12 makes
necessary.

**Retained** — derived, indexable, redistributable where the licence allows:
provider, concept, taxonomy, value, unit, currency, basis, period, filing
identity, publication time, validation outcome.

**Referenced** — a pointer, never a copy: the source document bytes when the
licence or size argues against retention, or when the provider's own terms
restrict redistribution (§12).

Both are first-class. A record that references without retaining is complete
Evidence if it names provider, locator, retrieval time, and identifier. That is
already how 2.4.2 treats the vendor's undated balance-sheet figures.

## 3. Initial Core Evidence scope

### 3.1 The admission table

Every candidate the brief listed, ruled against the four gates. This is the
deliverable; the list exists to be judged, not adopted.

| Candidate | Verdict | Gate that decided it | Note |
|---|---|---|---|
| Revenue | **CORE** | — | concept already in the model |
| Cost of Revenue | **CORE** | G2 | `CostOfRevenue` / `CostOfGoodsAndServicesSold` |
| Gross Profit | **CORE** | G2 | stated by filers as its own tag |
| Operating Income | **CORE** | G2 | `OperatingIncomeLoss` |
| R&D expense | **CORE** | G2 | `ResearchAndDevelopmentExpense` |
| SG&A / operating expenses | **CORE** | G2 | two distinct tags; never silently merged |
| Interest income/expense | **CORE, with a fork** | G2 | gross and net interest are different facts and must not be one metric |
| Income tax | **CORE** | G2 | `IncomeTaxExpenseBenefit` |
| Net Income | **CORE** | — | already in the model |
| Diluted EPS | **CORE** | — | already in the model |
| Weighted-average diluted shares | **CORE** | G2 | distinct from shares outstanding (§3.2) |
| Cash and equivalents | **CORE** | — | already in the model |
| Receivables | **CORE, with a fork** | G2 | `ReceivablesNetCurrent` excludes contract assets; `ReceivablesNet` does not |
| Inventory | **CORE** | G2 | genuinely absent for a bank; `NOT_APPLICABLE` |
| Total current assets | **CORE** | G2 | |
| Total current liabilities | **CORE** | G2 | |
| Debt | **CORE, as a composition** | G2 | no single total-debt tag exists; composition must be declared per filer |
| Equity | **CORE, with a fork** | G2 | total vs parent-only equity |
| Total Assets | **CORE** | — | already in the model |
| Operating Cash Flow | **CORE** | G2 | |
| CapEx | **CORE** | G2 | filer-tagged, not derived as FCF minus OCF |
| Stock-based compensation | **CORE** | G2 | |
| Dividends paid | **CORE** | G2 | cash-flow-statement tag |
| Dividends declared per share | **CORE** | G2 | a different fact from dividends paid |
| Buybacks | **CORE** | G2 | `PaymentsForRepurchaseOfCommonStock` |
| Price | **CORE** | — | already in the model |
| Volume | **CORE** | G2 | |
| Shares outstanding | **CORE** | — | already in the model |
| Corporate actions — *declared* | **CORE** | G2 | only what a filing declares: split ratio, dividend rate, merger terms |
| Corporate actions — *adjusted series* | **NOT CORE** | G5 | a restated-for-comparability series is our transformation |
| EBITDA, EBIT | **NOT Core Evidence** | G5 | Derived, and `NOT_APPLICABLE` for a bank |
| Margins, growth rates, returns | **NOT Core Evidence** | G5 | Derived |
| P/E, EV/EBITDA, P/S, P/FCF | **NOT Core Evidence** | G5 | Derived and conditional on a reference choice |
| Net debt, enterprise value | **NOT Core Evidence** | G5 | Derived composition |

"with a fork" means: two related but unequal concepts. The specification must
register both as separate metrics, because a filer that switches tags has not
changed the fact, only the name. Merging them would produce a series with a
silent discontinuity — the defect 2.4.3 exists to prevent.

### 3.2 A metric is not a concept, and the two are related by a mapping

**This is a normative decision and it replaces the earlier "fork" phrasing.**

A **metric** is a semantic meaning, named by ST-EVA, stable over time. A
**source concept** is what a source calls it: an XBRL tag, a vendor field, a
line-item label. The two are related by an explicit mapping, and the mapping
carries a fidelity:

| Mapping fidelity | Meaning |
|---|---|
| `EXACT` | the source states this concept and it means exactly the metric |
| `EQUIVALENT` | a different name, an equal meaning; the series continues |
| `PARTIAL` | the source states a component or a wider aggregate; the series is not comparable across the switch |
| `NON_COMPARABLE` | related but not the same quantity; a new metric |

The registry therefore has three tables, not one wide table:

```
metric_registry           metric_id, statement, semantic_definition,
                          applicability, comparable_group, is_core

source_concept_registry   taxonomy, concept, label, source_definition

metric_source_mapping     metric_id, taxonomy, concept, fidelity, valid_from,
                          valid_to, source_id
```

**The rule that replaces "fork everything":**

> A concept may change. A metric keeps one series only while its definition
> stays equivalent.

So `operating_expense_sga` mapped to
`us-gaap:SellingGeneralAndAdministrativeExpense` by one source and to a
differently-named tag by another, both `EQUIVALENT`, is **one metric with two
source concepts**, not two metrics. The series continues unbroken, and the
cross-source comparison is between concepts, not between metrics.

`total_debt`, `long_term_debt` and `current_debt` are **three metrics**, because
no concept of one is `EQUIVALENT` to any other. A filer that moves from
`LongTermDebtNoncurrent` to a composed total has changed the quantity, not its
name.

`receivables` is the instructive middle case. `ReceivablesNetCurrent` excludes
contract assets and `ReceivablesNet` does not. Those are `PARTIAL`, not
`EQUIVALENT`, so a filer switching between them produces a discontinuity at that
date rather than a silent splice. Same for total versus parent-only equity.

This is the 2.4.3 rule applied upward: names may be similar and the quantities
may not be, and 2.4.3 already removed the cross-span differencing that would
otherwise hide the switch. The mapping table is where a name change is recorded
explicitly rather than inferred from a matching label.

### 3.3 Three count families that must never be conflated
The 2.4.2 audit found a 5.85x difference for TSM and a 1.41x difference for
NU between share counts. The Core scope must make the conflation impossible:

- **Shares outstanding** — an instant count, from a cover page.
- **Weighted-average diluted shares** — a period average, from an income
  statement.
- **ADS-equivalent / listed-unit count** — a conversion, which only the filer
  can state.

Each is its own metric. A period average is not an instant count, and an
ADS-equivalent count is neither.

### 3.4 What becomes Derived rather than Evidence

EBITDA, net debt, enterprise value, margins, growth, and multiples are all
Derived. They are legitimate ST-EVA outputs and all of them already exist in
2.3-C. They are simply not *facts someone reported*, and the 2.4.3
declaration that every derived figure must be recomputable from named
operands already constrains how they enter 2.5. The distinction matters
because Derived is where a method choice can be questioned, and Evidence is
where it cannot.

## 4. Optional extensions

Present only if a source states them and they are not already Core:

- segment or product-level breakdowns, from filer-tagged dimensions
- quarterly versus annual granularity, from the filing's own periods
- auditor name, filing form, and fiscal-year-end, from the submissions index
- XBRL concept metadata: label, description, taxonomy version
- treasury-share and buyback-authorisation detail, where separately tagged
- dividends per share by declaration date, where separately tagged

Optional means: absence is `NOT_APPLICABLE` or `SOURCE_DID_NOT_REPORT` and
never blocks a query. Optional is not "nice to have later", it is "a filer
sometimes states it and sometimes does not".

## 5. What the LLM or an analyst must find for itself

Out of scope because no public source states them as facts, or because
producing them is analysis:

- industry and sector classification beyond what a filer itself states
- peer comparison, competitive position, market share
- analyst estimates, estimate dispersion, consensus revisions
- implied volatility, short interest, borrow cost
- news, transcripts, management commentary
- competitive advantage, moat, brand, management quality
- any DCF, fair value, bull/base/bear, or target price
- any ranking, score, or recommendation

If an LLM needs one of these it fetches it and cites it, and that citation is
its own, not ST-EVA's. The reason is not squeamishness about finance: these
have no single observable truth to record, and a database that stores
inferences without labelling them as inferences is worse than one that does not
store them.

## 6. What has no objective truth and must not become an ST-EVA fact

Three classes, and the distinction is what keeps the database honest.

1. **Aggregations over sources** — "the market's estimate of next year's
   revenue". Real, useful, and not a fact. If a vendor publishes it, it is
   `SOURCE_REPORTED` **as that vendor's estimate**, carrying
   `estimate = TRUE` and the vendor identity. It is never promoted to fact and
   never used to fill a missing actual.
2. **Transformations we apply** — a restated-for-comparability revenue series, a
   constant-currency comparison, a fiscal-year normalisation. These are Derived,
   declared, and recomputable. They are not Evidence, and storing them as
   Evidence would make a transformation indistinguishable from a filing.
3. **Judgements** — every item in §5. Not stored at all.

The practical test for all three: *can a second person, given only the record,
reproduce the number from a source?* If the answer is "no", it is not Evidence.

## 7. Source, Source Document, Observation, Validation

```
Source                     a provider, identified once and reused forever
   |                          data.sec.gov | vendor | exchange
   v
Source Document           the exact bytes served, or a reference to them
   |                          content_hash, uri, fetched_at, byte_size,
   |                          document_type, provider
   v
Observation               one stated value about one concept and one period
   |                          the 23 contract fields, unchanged
   |
   +--> Validation          does other evidence agree?
   |                          status, independence, basis, tolerance
   v
Derived                   computed from named observations
                              operation + operands, recomputable
```

Relationships, stated as rules:

- One Source has many Source Documents. A document belongs to one provider.
- One Source Document yields many Observations, and may yield none.
- One Observation references one or more Source Documents, and exactly one
  concept and one period.
- **The observation does not own the document.** The document owns the bytes;
  the observation owns the claim. Several observations may cite one document,
  which is the normal case for a financial statement.
- A Validation compares two or more Observations. It never edits them, and it
  never selects a winner.
- A Derived figure names its input Observations. It is not Evidence and is
  recomputable from them.

## 8. Minimum provenance for a record to be stored

A record is storable when all are present. A record missing any of them is
refused, because a partially-sourced fact is indistinguishable from a
fabricated one once it is in a database.

```
provider            non-empty
document_ref        a resolvable document id or an explicit reference-only marker
locator             accession, or an equivalent identifier
period              period_start and period_end, or an explicit instant
as_of               the date the value is stated as of
available_at        with its basis
unit                a contract unit
basis               declared or explicitly UNDECLARED
retrieved_at        when we asked
```

A value with no period is an instant, and an instant is a period with a
boundary. There is no third option.

## 9. Temporal semantics

Three dates, never merged, already enforced by the 2.3-C contract and the
2.4.2 fixes.

| Date | Question | Owner |
|---|---|---|
| `period_start` / `period_end` | what window does it cover? | the filer |
| `as_of` | what date is it stated as of? | the filer |
| `available_at` | when did it become public? | EDGAR, for a filing |
| `filed_at` / `accepted_at` | when was it submitted and accepted? | EDGAR |
| `retrieved_at` | when did we ask? | us |
| `first_archived_at` | when did the archive learn it? | us |

Two rules the archive already enforces and 2.5 must not weaken:

- **`available_at` is never `retrieved_at`.** An undated source is recorded
  with `availability_class = UNDECLARED` or `ARCHIVE_FIRST_SEEN`, never
  back-filled with a fetch time.
- **An observation's period and its publication time are different axes.** A
  filing accepted in July can report a period ending in June. Collapsing them
  misdates history by up to a quarter.

Cadence governs freshness: a daily market source and a quarterly filing have
different staleness windows, and 2.4.3 established that a single global window
misreports one of them.

## 10. Unit, currency, basis

Three independent axes, from 2.4.2. Core Evidence must populate all three
explicitly, and an unstated currency is `UNDECLARED`, never the instrument's
quote currency.

- **Unit** — `currency`, `per_share`, `count`, `multiple`, `ratio`. Multiple
  and ratio are Derived-only and never appear on an Evidence record.
- **Currency** — a monetary value with no currency is not Core. Where a filer
  reports in a currency other than the listing currency, both are retained.
  The 2.4.2 TSM finding, a USD market capitalisation over a TWD revenue, is
  exactly what the currency gate now refuses.
- **Basis** — the 2.4.3 `basis` block. For Core Evidence this is where
  ordinary-versus-ADS, parent-only, attributable-to-noncontrolling-interests,
  continuing-versus-total-operations, and gross-versus-net live.
- **Accounting framework** — `us-gaap` or `ifrs-full`, read from the
  taxonomy, never assumed. NU and TSM report under `ifrs-full`; 2.3-B
  established that querying only `us-gaap` returns nothing for them, and that
  is a taxonomy boundary rather than a defect.

## 11. Restatement and revision

Already implemented in 2.4 and it is sufficient. Recorded here as a 2.5
requirement rather than new work.

- A restated period **appends** a new observation in the same
  `observation_lineage` row. The original is never overwritten.
- Two versions of one period are reported as a `same_period_pairs` entry with
  `relationship = RESTATEMENT_OR_REVISION` and
  `selection = NO_WINNER_SELECTED`. 2.4.3 made this explicit because a
  same-period pair is not a step on a time series.
- Which version applies at an instant is a point-in-time question, answered by
  `latest_knowable(cutoff)`. The archive never picks a "current" value.
- A concept *change* — a filer moving from one tag to another — starts a new
  lineage. The two are related and not comparable, and 2.3-B already classifies
  that as a methodology mismatch.

## 12. Public redistribution boundary

Stated now rather than discovered later, because it decides what the archive
keeps and what it only points at.

**Tier A — retain and publish.** Structured values plus their citation:
provider, concept, taxonomy, value, unit, currency, basis, period, filing
identity, publication time, and the derived validation outcome. For SEC data
these are the filer's own reported figures with a locator, and a citation
chain is the form in which they are meant to circulate.

**Tier B — reference only, never republish.** The document bytes. A filing's
exhibits, a vendor's response body, anything a provider's terms restrict.
Recorded as provider, locator, `retrieved_at`, `content_hash`, and a
`reference_only` marker. The archive keeps the bytes locally; publication
exports the pointer.

**Tier C — never collect.** Data whose licence forbids it, and anything whose
collection would require circumventing access control.

Consequences already in force: 2.4.1 captures SEC document bytes and stores
them locally with content-addressed deduplication; 2.4.2 stopped asserting a
vendor currency the vendor never stated, because a derived figure from an
unstated basis is not a fact that can be published. The 2.5 ingestion work
must classify each new source A, B, or C **before** the first fetch, and the
classification is stored on the Source row.

## 13. Incremental ingestion

### 13.1 Identity, and why there are two kinds

**This is a normative decision, and it is the one that could most damage the
2.3-B validation model if implemented carelessly.**

The tempting fix for "two adapters name the same filed fact differently" is to
derive one identity from the fact's content and deduplicate on it. That must not
be done, because it destroys the structure 2.3-B exists to provide:

```
SEC filing  -> Observation A (100)
Vendor      -> Observation B (100)
                      dedupe on value
           -> Observation   (100)      WRONG
```

Collapsing A and B because the numbers agree deletes the only evidence that two
independent readings existed, and with it the `independence` field, the
`CONSISTENT` verdict, and any future `DISCREPANT` or `CONFLICTING` finding. The
whole cross-source layer is a record of *disagreement between named sources*, and
a database that keeps one row cannot represent disagreement.

**There are therefore two identities, and they are not interchangeable:**

| Identity | Scope | Answers |
|---|---|---|
| `source_fact_id` | one fact, **within one source document** | "have I already parsed *this* fact out of *this* filing?" |
| `observation_id` | one source's claim, in ST-EVA's model | "which source said this, for which period, and under what basis?" |

```
source_fact_id   = sha256(source | document | taxonomy | concept
                                     | fact_period | fact_context)
observation_id   = distinct per source, never merged across sources
```

Deduplication happens **only** where the two refer to the same raw fact in the
same document:

- the same filing fetched twice by one ingestion run
- the same filing parsed by two different adapters

Both yield the same `source_fact_id`, and the second is recognised as already
held. That is a genuine duplicate and collapsing it loses nothing.

Two sources reporting the same value are **not** duplicates. They remain two
observations, linked by a `ValidationRecord`. This is already what 2.3-B does
and what the 2.4.2 audit relied on: TSM's 5.85x share discrepancy and NU's
1.41x discrepancy were only findable because both sides were kept.

`0008` carries this rule because it is the one migration that could silently
undo a sealed semantic. The invariant to assert is simple and worth stating as
an acceptance criterion of its own: **after any 2.5 ingestion, two sources
reporting the same number still produce two observations and one validation
record.**

### 13.2 The loop

The pipeline becomes a loop rather than a one-shot fetch.

```
first ingestion
    resolve company -> fetch filings -> parse -> store documents
    -> store observations -> validate -> store

every later run
    fetch the submissions index -> diff against what the archive holds
    -> fetch only unseen accessions -> store only new documents
    -> append only new observations -> validate new against held
```

The archive is already largely built for this, which is the main reason 2.4
pays off here:

- documents dedupe on `content_hash`; a stable endpoint costs one row ever
- observations dedupe on a content hash over fact, concept, period and
  accession, so re-running an unchanged filing adds nothing
- contexts dedupe on `context_id`
- everything is append-only, enforced by triggers, so a re-run cannot corrupt
- a document is fetched at most once per provider instance

**What is missing** and is genuinely 2.5 work:

- an explicit *"which accessions does the archive already hold?"* query, so
  ingestion can diff rather than refetch. Today the content hash prevents
  duplicate *storage*, not duplicate *fetching*.
- a declared fetch window, so a run cannot silently re-download a decade of
  filings.
- a per-source rate and budget policy, carried from the SEC's fair-access rule
  into the archive rather than living only in the provider.

## 14. Database and Context

**The database is the record. The Context is a query view over it.**

Today: a run fetches live and builds one large Context. Tomorrow: a query
selects the rows a question needs, and the Context is built from those rows.

```
question: "AAPL revenue and R&D over five years"
  -> query: AAPL, metrics {revenue, research_and_development}, periods 2021..2026
  -> context: 12 observations, their sources, their validations
```

Consequences to accept deliberately:

- **A Context is no longer the unit of persistence.** The database is. A
  Context is derived, disposable, and rebuildable, and its `context_id` becomes
  a function of the *query* as well as the data.
- **A Context gets smaller.** That is the point. A large Context is evidence
  that the database is not being queried well.
- **The 2.3-C Context schema does not have to be the agent interface.** The
  brief's point that the database need not be pinned to one Context format is
  correct. `2.3-C.2` is the current *view* format and may be superseded without
  re-collecting anything.
- **Replay semantics carry over.** A Context built at cutoff T must contain
  nothing that became knowable after T, and that is checkable because
  `available_at` is per-observation. This is already true and is a property the
  database inherits for free.

One thing 2.5 must not do: make the Context the *only* way to read the
database, so that answering a question still requires assembling a document
first. The database is queryable on its own.

## 15. What a future Evidence API needs

Conceptually, and deliberately as capabilities rather than routes, because the
storage should not dictate the interface:

| Capability | Answers |
|---|---|
| `describe_company` | identity, filings held, metrics held, period coverage |
| `list_metrics` | the Core set, with per-company state |
| `get_observations` | by company, metric, period, source; with the states of §1.1 |
| `get_series` | a metric over time, per basis, with discontinuities marked |
| `get_source` | provider, locator, retrieval time, content hash, tier of §12 |
| `get_provenance` | the full chain for one figure, citation to document |
| `get_validation` | what other evidence says, and its independence |
| `get_conflicts` | unresolved disagreements, no winner |
| `compare_periods` | same metric, two periods, same basis only |
| `coverage_report` | what is held, what is missing, and why |

Requirements on the API, which follow from the brief:

- **It hides SQLite.** A consumer must not need to know the table shape. This
  is what makes a future storage change cheap.
- **It returns states, not just values.** A metric with no rows must come back
  as `SOURCE_DID_NOT_REPORT`, `NOT_APPLICABLE`, or `UNAVAILABLE` — never as an
  empty success, and never as zero.
- **It is the reproducible unit.** Every response carries the same
  provenance blocks a Context figure carries today, because a figure without
  them is not evidence.
- **It never computes an interpretation.** No ranking, no score, no
  recommendation, and no composite that a consumer could mistake for a source
  figure.

## 16. What the existing architecture already supports

Assessed against the code at `667d05d`, not from memory.

### 16.1 Already sufficient

| Need | Present at baseline | Note |
|---|---|---|
| per-figure provenance | yes | the 23 contract fields, unchanged since 2.3-A |
| security / share basis | yes | the 2.4.3 `basis` block, which carried the TSM 5.85x finding |
| source document capture | yes | 2.4.1, content-addressed |
| observation -> document link | yes | `observation_sources`, many-to-many |
| append-only | yes | enforced by triggers, not by convention |
| restatement lineage | yes | `observation_lineage`, 2.4 |
| point-in-time selection | yes | `knowable_at`, `latest_knowable`, `replay_eligible_from` |
| availability classes | yes | 2.4.2 |
| per-cadence freshness | yes | 2.4.2 |
| cross-source validation | yes | 2.3-B, with `independence` |
| conflict without a winner | yes | 2.4.2, `NO_WINNER_SELECTED` |
| machine-readable refusals | yes | 2.4.3, closed vocabularies |
| derived recomputability | yes | 2.3-C operation registry, verified by parity |
| idempotent storage | yes | dedupe on `content_hash` and `context_id` |
| source provider registry | yes | the `sources` table |
| context is a rebuildable view | yes | by construction; `verify_document` re-checks it |

That is most of the foundation. The 2.4.x line was, in retrospect, the right
preparation for 2.5.

### 16.2 Genuinely missing, and required

| # | Gap | Why it blocks 2.5 | Size |
|---|---|---|---|
| 1 | **No `NOT_APPLICABLE` state** | a bank's operating income and a miner's inventory have no tag. Without this state they are indistinguishable from retrieval failures, and the brief names it as a required outcome | small — one enum member, one classifier, one test |
| 2 | **No statement taxonomy** | 22 metrics are a flat list. Income, balance sheet, cash flow and capital return cannot be queried as groups, and a filer-tagged statement line has nowhere to sit | small — a `statement` field on the metric registry |
| 3 | **`taxonomy` and `concept` are not first-class** | they live in `raw.sec_fact`, so a database cannot be *queried* by concept. The brief's "where?" question is unanswerable at the index level | small — two indexed columns |
| 4 | **Filing identity is not first-class** | accession, form, fiscal year, fiscal period and section live in `raw`. A filing-level query is impossible | small — five columns, all already parsed |
| 5 | **`observation_id` is adapter-assigned** | generated by the adapter, not derived from asset + concept + period + accession. Two adapters describing the same fact produce two identities, so dedupe cannot be content-based and the same fact from two sources looks like two facts | moderate — a derived identity function, with the old ids preserved for replay |
| 6 | **No concept registry** | the metric-to-concept mapping is a 7-entry Python dict in `sec_provider`. Growing Core Evidence to ~30 items without a registry puts a data model in a provider file, where it will drift | moderate — one table, concept priority as rows |
| 7 | **No ingestion diff** | the archive prevents duplicate *storage* but not duplicate *fetching*. A multi-year SEC pull would re-fetch everything on every run | small — a "which accessions are held" query |
| 8 | **No redistribution tier on a source** | §12 needs it before the first fetch, and nothing records it | small — one column on `sources` |
| 9 | **Cross-source set is hard-coded to 7** | `COMPARABLE_METRICS` is a fixed tuple. Core Evidence needs a metric to be Core *and* declared comparable-or-not, per company | small — a registry field |
| 10 | **No query surface** | there is no read path other than full replay. 2.5 §14 needs `get_observations` and `get_series` | moderate — read-only query functions over the existing tables |

Items 1, 2, 3, 4, 6, 8 and 9 are one migration plus a registry table. Item 5
is the one that needs real care, because it touches the identity of everything
already archived. Item 10 is additive. None of them changes an arithmetic rule
or a documented semantic, and none of them should change
`context_schema_version` behaviour beyond a further MINOR bump.

### 16.3 What must not be done to get there

- Do not re-architect. The Observation, Evidence, Validation and Archive
  semantics from 2.3-A through 2.4.3 are correct and tested; 2.5 adds storage
  and query, not semantics.
- Do not renumber or re-key existing archive rows to chase a tidier identity.
  2.4 archives must keep replaying. If item 5 is done, it is done
  additively with the legacy id retained.
- Do not widen the contract to make a query easy. If a query needs a field
  that is not there, the field belongs in the metric registry, not in
  `Observation`.
- Do not let a Core Evidence list become a ranking, a completeness score, or a
  coverage percentage. Coverage is reported as states per §1.1 and nothing else.
- Do not feed analyst research gaps into the Core list. §5 is the filter, and
  a metric enters Core by passing G1–G5, not by being asked for.

## 17. Scope of the first implementation experiment

One company, one full chain, end to end. Not six companies, and not the whole
Core list. The chain is proven with the seven most basic metrics first —
revenue, net income, diluted EPS, cash, debt, total assets, shares outstanding
— because once identity, registry, filing provenance, incremental ingestion and
query all work for seven metrics, adding R&D, CapEx, SBC or segment revenue is
adding evidence *mappings* rather than redesigning the database.

```
AAPL
  multi-year SEC filings
    -> SourceDocument  (content-addressed, stored)
    -> Observation    (with concept, taxonomy, accession, statement, period,
                       available_at, source_fact_id)
    -> Validation     (where a second source agrees or does not)
    -> database       (incremental; a second run adds nothing)
    -> exported Context
    -> the chain traceable from a figure back to the filing
```

Chosen because AAPL is `us-gaap`, files 10-K and 10-Q on a conventional fiscal
calendar, and has cross-source vendor figures to validate against. It is the
*unproblematic* case, which is what a first experiment needs: if the chain fails
here, the failure is worth having found.

**TSM and NU are explicitly out of scope for the first experiment.** Both are
`ifrs-full` filers, and 2.3-B established that the `us-gaap` concept set
returns nothing for either. The brief is right that they should not distort the
Core schema to make six companies uniform. They are the natural second
experiment, and their taxonomy is a reason to extend the registry, never a
reason to bend the model.

### 17.1 The first experiment's acceptance criteria

The chain, not a page count. All five must hold.

| # | Criterion | Proves |
|---|---|---|
| 1 | A second ingestion of the same filing adds **0** new observations | the identity and dedupe rules work |
| 2 | The same filing parsed twice, by two paths, produces **no** duplicate source fact | `source_fact_id` deduplicates within a source document |
| 3 | Two sources reporting the same number keep **two** observations and one validation record | cross-source evidence survives, per §13.1 |
| 4 | A concept rename with an `EQUIVALENT` definition keeps **one** continuous metric series | the mapping fidelity rules work, per §3.2 |
| 5 | Two similarly-named concepts with different definitions produce a **discontinuity or non-comparable**, never a silent splice | 2.4.3's rule holds upward |

Criteria 4 and 5 are what make the "fork" question answerable rather than
debatable, and they are the reason they are acceptance criteria rather than a
design note.

## 18. Explicit non-goals for 2.5

Recorded so the boundary is checkable rather than remembered.

- No new provider beyond extending the SEC ingestion already in 2.3-B.
- No new valuation model. EBITDA stays Derived; `NOT_APPLICABLE` for a bank.
- No ranking, score, completeness metric, or recommendation.
- No LLM anywhere in the ingestion, storage, or query path. The LLM consumes
  the database; it does not shape it.
- No analyst research item enters Core by request.
- No change to the 2.2.3 CLI output, and no new default behaviour.
- No retroactive filling of a gap from a later filing, a vendor estimate, or a
  computed value.
