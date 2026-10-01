# 2.14 — Full Core scope, bulk, and the availability contract

2.13 produced a rule rather than a bug: bulk must bootstrap a fresh archive at
the full Core scope, and a change to the Core metric set is a re-bootstrap. That
rule had never been *used*, because the full Core scope has only ever been run
over **six** issuers, through the API path.

This runs it. Six `companyfacts` documents already on disk, a fresh archive, the
twenty seeded Core metrics, zero network — and then a per-fact reconciliation
against the archive the API path built, the eight gates over the result, and a
point-in-time safety check against the API route's real acceptance instants.

```
scope confirmed    20 Core metrics, the 8-metric slice is a strict subset,
                   and the registry seed declares exactly the same 20
bootstrap          6 issuers  17,043 obs  0 requests  52.6s  57.5 MB
reconciliation     17,043 shared source_fact_id
                     0 one-sided      0 duplicate identities
                     0 divergence in value, unit, period, taxonomy, concept,
                       accession, form, contract id, definition, methodology
                   17,043 differ in available_at and available_at_basis
pit safety         0 declared values promoted to an instant
                   0 of 8,218 facts eligible before EDGAR published them
gates              7 of 8 identical. applicability 0/120 against 120/120
```

**The chain holds. It found one field that made a third of a corpus knowable
before it was published, and that field is now fixed, measured and tested.**

---

## A. Did the experiment succeed

Yes, and it was offline by construction.

| | |
| --- | --- |
| network requests | **0** |
| documents read | 6 (one per issuer) |
| concept fetches | 132 |
| issuers | AAPL MSFT MU NVDA TSM NU |
| forms | 10-K, 10-Q / 20-F, per filer, as the reference build used |
| elapsed | 52.6 s |
| archive | 57.5 MB |

The scope was **asserted, not passed**. There are three metric-set definitions
in this repository and they do not agree:

```
sec_ingest.DEFAULT_METRICS                  8    the vertical slice
build_crossframework_snapshot.ALL_METRICS  20    the Core set
merge_sources.FULL_CORE_METRICS            20    the Core set, other order
```

`fullscope_bulk.py` imports all three, checks that the two twenty-metric sets
are the same set, checks the registry seed declares exactly that set, and
refuses to run otherwise. A run that quietly used the eight would have looked
exactly like a twenty-metric run that collected nothing — the same shape as the
empty-`tickers.json` failure 2.13 caught. The guard fired on its first
invocation, against a registry that had not been seeded, which is the second
time in two rounds that an assumption about the archive was wrong on contact.

The ticker map was passed in, read from the reference archive's own `assets`
table, because `BulkFactsSource` refuses to infer a ticker from a company name
and 2.12 recorded why. Nothing was guessed and nothing was downloaded.

---

## B. What twenty metrics actually collected

| issuer | observations | metrics | filings held |
| --- | --- | --- | --- |
| AAPL | 4,230 | 18 | 72 |
| MSFT | 4,344 | 18 | 71 |
| MU | 4,009 | 18 | 66 |
| NVDA | 3,895 | 18 | 70 |
| TSM | 420 | 14 | 10 |
| NU | 145 | 11 | 4 |

```
20 metrics requested   20 applicable per issuer (no rulings were made)
collected              18 / 18 / 18 / 18 / 14 / 11
backlog                0
declined concepts      19 each
duplicate identities   0
```

Eighteen of the twenty yield. The two that yield nothing,
`long_term_debt_current` and `long_term_debt_noncurrent`, are the declared
composition of `debt` — the filers reported 90, 116 and 142 facts, they are
held under `debt`, and a component of a declared composition is not separately
stored. The ledger says `MAPPED_NO_CURRENT_OBSERVATION` rather than leaving two
metrics silently empty, exactly as 2.9 recorded.

**Every one of these twenty totals is identical in the API-built reference.** Not
approximately — the per-metric and per-issuer yields match exactly. The 8-metric
slice and the 20-metric set are not two different amounts of collection. They
are the same eight plus twelve.

### Cost, now measured at full scope rather than extrapolated from eight

| per issuer | 8-metric slice (2.11/2.12) | **20-metric, bulk** |
| --- | --- | --- |
| requests | 23.4 | **0** |
| seconds | 10.8 | **8.76** |
| observations | 728 | **2,840** |
| archive | 2.33 MB | **9.58 MB** |

Extrapolated to ten thousand: **zero requests, 24.3 hours, 28.4 million
observations, 95.8 GB.** The same caveat 2.11 gave applies and has not gone
away — this sample has no mega-cap, so the constant is still a floor.

One thing the file size shows that the per-company number hides: of 57.5 MB,
**2.8 MB is document payload**. The other 95% is rows and indexes. A corpus
built this way is not 96 GB of evidence; it is 5 GB of evidence and 91 GB of
SQLite.

---

## C. Bulk against API

Joined on **`source_fact_id`**, which is the 2.5 identity and the only join key
that is route-independent by construction.

```
bulk total 17,043      api total 17,043
shared identity        17,043
only in bulk                0
only in api                 0
duplicate identities        0
```

**Every semantic field matches on all 17,043 facts** — value, unit, currency,
period, as-of, taxonomy, concept, accession, form, fiscal period, contract id,
source concept ref, basis block, definition, methodology, status, instant.

`observation_id` is *not* a cross-archive key, and this run found that out
rather than assuming it. Both archives store an archive-assigned
`obsarch_<hash>`, because `record_observation` re-keys whatever contract id it
is handed, so the two disagree on **every** value of that column. The
route-independent string is `contract_id`, and it matches everywhere.

Provenance differs on all 17,043, in `document_id`, `content_hash`,
`retrieved_at` and `first_archived_at` — the API path read a
`companyconcept` document, the bulk path read the `companyfacts` slice. Both
honest, not the same bytes, classified rather than counted as disagreement.

The filing ledger differs slightly, as 2.12 predicted: NU 4 against 5, TSM 10
against 11, the other four identical. The bulk index is derived from the facts,
so a filing that contributed no fact we can see is absent from it.

### The one field, and the residual divergence is not one thing

```
bulk   available_at  a bare date           available_at_basis  FILED_AS_OF_DATE
api    available_at  a timestamp           available_at_basis  ACCEPTANCE_DATETIME
```

"17,043 divergent" is not an actionable number, and this is why: the reference
archive was built by the **2.13-era code**, so it carries that code's two
behaviours, while the bulk archive is the only side written under the corrected
contract. Split by cause:

| cause | rows | what it is |
| --- | --- | --- |
| reference holds the pre-fix midnight fabrication | 8,825 | a stale artefact. The corrected contract produces this value on neither route |
| same day, the API route holds a real acceptance instant | 6,443 | a genuine precision difference: EDGAR has a time, `companyfacts` does not |
| API accepted before the filed date the bulk route has | 1,710 | same, and the safe direction |
| the two routes have different source precision | 65 | the filed date trails the acceptance instant by a day — see section E |

So the honest reading of the residual divergence is: **8,825 rows of it is the old
code, and 8,218 rows is the API route knowing more than the bulk route can
know.** Neither is a semantic fork in the ingestion model.

### Point-in-time safety

The check that actually matters, run per fact rather than in aggregate against
the 8,218 rows where the API route holds a genuine EDGAR acceptance instant:

```
declared value promoted to an instant        0
eligible before the source said it was public 0
invariant holds                             True
```

Before the fix, the same check read **6,508 of 17,043 eligible too early**. The
number that matters is not zero-versus-not; it is that the check exists, it runs
on every corpus build, and it reads instants rather than strings.

---

## D. The eight gates

Run as a subprocess against the committed tool, not reimplemented: a gate
rewritten for a report is a gate that can disagree with the one the project
measures with.

| gate | bulk | api | |
| --- | --- | --- | --- |
| definition | 120/120 | 120/120 | |
| mapping | 120/120 | 120/120 | |
| **applicability** | **0/120** | **120/120** | no SIC in `companyfacts` |
| adoption | 120/120 | 120/120 | fixed, see E |
| observations | 97/120 | 97/120 | identical |
| provenance | 120/120 | 120/120 | |
| missingness | 120/120 | 120/120 | |
| discoverable | 120/120 | 120/120 | |

Seven of eight are identical, including the identical nine failing observation
gates. One differs, and it is informative.

### Applicability 0/120, and what it really costs

`companyfacts` carries no SIC, so `submissions_available` is false, no business
model is recorded, and the rule deliberately makes no ruling. All 120 gates fail
— not because a ruling is wrong, but because there is none.

But the archive holds the *same* facts, so the loss is not collection. It is
the refusal:

```
                        bulk (no rulings)      api (SIC from submissions)
NU gross_profit         COLLECTED, 12 facts    NOT_APPLICABLE, 12 facts held
NU operating_income     DELIBERATELY_DECLINED  NOT_APPLICABLE, 0 facts
```

**The API-built archive already holds twelve `ifrs-full:GrossProfit` facts for a
bank, and declines to count them.** Without the submissions payload the ledger
counts the same twelve. So the missing `submissions` file does not add data — it
removes a refusal. The prediction made before this run was the opposite: that a
bulk-only corpus would be full of `SOURCE_SILENT` noise from inapplicable
metrics. It is not, because ingestion never filtered on applicability. The
direction of the risk is that a bank reports a "collected gross profit".

---

## E. The availability contract, which already existed

The finding that changed the round.

**`AvailabilityBasis.FILED_AS_OF_DATE` has been in the vocabulary since the
vocabulary was written** — "a provable date whose time of day is not published" —
`sec_provider._availability` already emitted it, `archive.DECLARED_BASES`
already listed it, and `tests/test_ingestion_aapl.py::test_15` already asserts
that ingestion produces `ACCEPTANCE_DATETIME` or `FILED_AS_OF_DATE`.

**That test is gated on `ST_EVA_LIVE=1`, so it does not run.** The only
statement of the availability contract in the suite was one nobody executes. The
vocabulary was right, the provider was right, and the ingestor was wrong — it
decided the basis by asking whether the string contained a `T`.

### The rule

One sentence, and it is now enforced in six places:

> **ST-EVA does not raise date-precision information to an exact timestamp.**

A source that has only a date must be able to say so without a consumer
guessing from the shape of a string.

```
source declares precision
        ↓
availability representation, at that precision
        ↓
point-in-time eligibility, from the declared basis
```

Three cases, uniform across both delivery routes, and never "API exact / bulk
approximate":

| what the source published | value stored | basis | replayable from |
| --- | --- | --- | --- |
| an instant | the instant | `ACCEPTANCE_DATETIME` | that instant |
| a date | **the date, no time** | `FILED_AS_OF_DATE` | after the declared day, plus a one-day allowance |
| nothing | none | `UNDECLARED` | never |

### What changed, in the code

- `data_contract` — `PRECISION_INSTANT` / `PRECISION_DATE` / `PRECISION_NONE`,
  a closed vocabulary; `eligibility_for_declared_date`; `end_of_declared_day`
  and `point_in_time_cutoff` for reading a cutoff.
- `sec_ingest` — `_availability_for` resolves value, basis and precision from
  the source's declaration. The `T00:00:00+00:00` fabrication is gone.
  `_observation` takes the basis as an argument and refuses an undeclared one.
  The declaration is preserved in the observation's `raw` block, so a consumer
  can read the precision without re-deriving it.
- `sec_bulk` and `sec_provider` — each filing index declares its own precision.
  A filing index that carries a value without declaring its precision is read as
  an instant, and an index that declares an unknown precision is refused.
- `sqlite_archive` — `replay_eligible_from` is derived from the declared basis.
- `data_contract.ObservationSet.knowable_at` — the in-memory selector applies
  the same rule, so the two point-in-time implementations cannot drift.
- `evidence_query` — the package reports `precision` beside the value, because
  a `FILED_AS_OF_DATE` value is a date and this is a consumer-facing surface.

### Two things the fix exposed that were not visible before

**1. The bulk path was producing contract-invalid observations.** The contract
validator escalates `MISSING_METADATA` when `available_at` is set while the basis
is `UNDECLARED` — and the bulk route was doing exactly that on 100% of rows. The
validator already knew. The ingestion path simply never called it.

**2. The two point-in-time implementations gave different answers.** The SQL
selector compared stored strings, where a bare date cutoff sorts *before* every
instant of that day, so "as of 2026-03-05" was read as midnight. The in-memory
selector compares dates and read it as the whole day. Same question, two
answers — and it only became reachable once an eligibility value could land
exactly on midnight. A cutoff is now read through `point_in_time_cutoff`, and an
unreadable one returns nothing rather than everything.

### The 65 rows, and the one-day allowance

The first attempt at the boundary was "the moment the declared day is over", and
it still failed the safety check on 65 rows: MU, filed-as-of **2020-06-29**,
accepted **2020-06-30T16:12:44Z**. EDGAR's `filed` date and its
`acceptanceDateTime` do not always agree on the day.

So the boundary carries a named allowance, `DECLARED_DATE_LAG_DAYS = 1`, and it
is a measured property of this source rather than a precision the source states.
It is the single place that has to move if the SEC ever disagrees by more, and
the per-fact safety check reports it rather than hiding it. A fact known only by
a declared date 2020-06-29 is eligible from 2020-07-01, not 2020-06-30.

This is a two-day lag and it is deliberate. A date is a claim about a day; the
archive will not make it a claim about a moment, and will not discard the
evidence either.

### Engineering defect I introduced and caught

Adding the precision declaration to `sec_bulk.filing_index` lost one indentation
level, which collapsed the derived index from 72 entries to 50. Nothing failed:
the observations were byte-identical, because a fact's own `filed` date supplies
the same answer when the index entry is missing. Only `filings_ingested` and the
filing ledger moved — 69 to 48 for AAPL — and nothing else noticed.

It was caught by measuring rather than by assuming, and it is now guarded by a
test that asserts one index entry per accession across four concepts, which is
the shape that collapsed. The general lesson is the one 2.13 already paid for:
**a number that changes is a finding until you know why.**

---

## F. Engineering defects, fixed and outstanding

Fixed in this round:

1. ~~`sec_bulk.py` puts a date where a timestamp belongs~~ — the derived index
   now declares `PRECISION_DATE`.
2. ~~`sec_ingest.py:1100` the filed-date fallback is labelled
   `ACCEPTANCE_DATETIME`~~ — the basis arrives as a declaration.
3. ~~`score_collection_gates.py` omits `NOT_APPLICABLE` from the adoption gate~~.
   Both archives now read 120/120, and the API archive's 119/120 was never a
   semantic difference: a filer whose applicability ruling was recorded and
   correct failed the gate for having recorded it.

Recorded, not fixed, and non-blocking:

4. **`sec_ingest.py:867` — a bulk-built archive names a document it never
   fetched.** The document URI is hardcoded to
   `https://data.sec.gov/api/xbrl/companyconcept/...` regardless of provider,
   overwriting the honest `bulk://companyfacts/...` the bulk source set.
   `provider` is recorded correctly, so the row is not wholly false — but
   `uri` and `canonical_uri` name a URL whose bytes are not the bytes stored,
   which is what 2.4.1 said an observation must not resolve to. It is a
   provenance-representation defect, not an availability one, and it does not
   change when anything was knowable.

Documented rather than changed:

5. **`observation_id` is archive-local.** `record_observation` re-keys whatever
   contract id it is handed, so two archives built from identical evidence
   disagree on every value. `source_fact_id` and `contract_id` are the
   route-independent keys and both match. Nothing in the repository said which
   was intended; the specification now says `observation_id` is assigned by the
   archive holding it and is not a global identity.

---

## G. Unresolved semantic decisions

**1. Does a bulk bootstrap ship with `submissions`?** The NU case is the argument
for yes: a corpus built only from `companyfacts` has *no* inapplicability
rulings, so a bank's gross profit reads as collected. The argument against is
that `submissions` is the second, larger half of SEC's bulk distribution. What
is decided is whether "no ruling" is acceptable for a public corpus.

**2. What is the honest availability basis for a fact known only by its filed
date, and may `ACCEPTANCE_DATETIME` ever be claimed for a fallback?** The first
question is now answered — `FILED_AS_OF_DATE`, with a date and no invented time.
The second is not: the reference archive still labels 8,825 rows
`ACCEPTANCE_DATETIME` when the value was a filed-date fallback, and every archive
built before this round does too. Existing archives are not rewritten; the
contract is corrected going forward.

**3. Corpus shape, now arithmetic rather than extrapolation.** 95.8 GB at ten
thousand issuers, of which 5% is document payload. A decision about
partitioning, retention and backup, and grounded in a measurement rather than
scaled up from eight metrics.

**4. The one-day allowance.** `DECLARED_DATE_LAG_DAYS = 1` is measured on 65
rows from one source. Whether it belongs in the contract or should be measured
per source, and what the archive should do if a source ever needs two, is
undecided. The safety check will report it; nothing yet escalates it.

---

## H. The next experiment

**Full-scope bulk bootstrap over the twelve `harness/bulkfacts/` issuers,
reconciled against the 75-issuer archive.**

The availability contract is now correct, so the corpus is worth building:

- **twelve issuers instead of six.** The full Core scope has now touched six
  filers, all from `build_crossframework_snapshot.DEFAULT_ISSUERS`. The twelve in
  `harness/bulkfacts/` are a strided SIC sample, so full scope would meet a real
  population for the first time.
- **twelve against a different archive.** All twelve are already held in the
  75-issuer archive, so this is a second independent reconciliation — different
  asset set, different form policy, different build.
- **it answers the question 2.10 actually left open.** Which Core metrics get
  thin, for which kinds of company, and why. 2.10 measured that across six
  filers and could not answer it; nothing since has widened it.
- **still zero network**, and the PIT safety check runs on the result.

What stays after it, unchanged: the mega-cap-weighted resample, the real
`companyfacts.zip`, and the corpus-shape decision. In that order, and none of
them is semantic any more except the third.

---

## I. State

| | |
| --- | --- |
| full suite | **612 passed**, 74 skipped, 686 run |
| new tests | `tests/test_availability_precision.py`, 34 cases |
| `verify_harness` | **unchanged** — reference target 15/15, every broken target caught by its probe |
| sealed snapshot | untouched |
| production files changed | `data_contract`, `sec_ingest`, `sec_bulk`, `sec_provider`, `sqlite_archive`, `evidence_query`, `score_collection_gates` |
| committed artefact | `harness/fullscope-214.json` |
| archives | `snapshot-fullscope.sqlite` (57.5 MB, untracked, one command to rebuild) |

No metric definition names an issuer, no code path knows a company, and the
archive holds one semantic layer for three taxonomies and two delivery paths —
now with one answer to "when was this knowable", arrived at from what each
source declared rather than from the shape of a string.
