# ST-EVA 2.4 — Point-in-Time Archive & Replay

Status: SPEC (to be reviewed before implementation)
Target: 2.4
Baseline: 2.3-C
Repository: sbvcid/st-eva
Builds on:
[docs/ST-EVA-2.3-A-DATA-CONTRACT.md](ST-EVA-2.3-A-DATA-CONTRACT.md),
[docs/ST-EVA-2.3-B-SEC-VALIDATION.md](ST-EVA-2.3-B-SEC-VALIDATION.md),
[docs/ST-EVA-2.3-C-INVESTMENT-CONTEXT.md](ST-EVA-2.3-C-INVESTMENT-CONTEXT.md)

## 0. Purpose

2.3-C produced a document that answers *"what did ST-EVA know about this
asset, as of the moment it was built?"* 2.4 makes ST-EVA able to answer a
strictly harder question:

> **What could the market actually have known at time T?**

```
Provider -> Observation -> Evidence -> Validation -> Derived
         -> InvestmentContext
                    |
               Persistent Archive
                    |
         Point-in-Time Replay
```

The difference between those two questions is the whole phase. "What ST-EVA
knows now" is easy and is what 2.3-C does. "What was knowable then" requires
that the archive record *when each fact became public*, never mutate a fact,
and be able to reconstruct an entire prior state from first principles.

### 0.1 The measured asymmetry that shapes this phase

Before designing anything, the availability of real data was measured against
the live sources:

| Source | observations | with source-declared `available_at` |
|---|---|---|
| SEC EDGAR | 71 | **71 (100%)**, all `ACCEPTANCE_DATETIME` |
| Yahoo fundamentals (2.2.3 material set) | 12 | **0**, all `UNDECLARED` |
| Yahoo price and derived metrics | 2 | 2, `OBSERVATION_INSTANT` |

This is not an implementation detail. It means:

- **SEC history is fully replayable**, because the SEC publishes the exact
  instant EDGAR accepted each filing.
- **Yahoo fundamentals are not replayable at all under a strict rule**, because
  Yahoo does not say when a figure became public, and back-dating a retrieval
  time to a publication time would be a fabrication.

A phase that pretended otherwise would produce confident, wrong answers about
the past, which is worse than producing none. 2.4 therefore separates two
questions that are easy to conflate:

> **Point-in-time truth** — was this knowable at T, on the source's own
> authority? Only answerable where the source declares availability.

> **Observational replay** — did ST-EVA have this on file at T? Answerable from
> the archive's first day forward, and explicitly *not* the same thing.

Both are supported. They are never mixed, and every observation carries which
one it is (§5).

### 0.2 What the archive can and cannot guarantee

> **ST-EVA can only guarantee the history it has itself archived. For data
> predating the archive, reconstructive replay is possible only where the
> source itself retains sufficient original provenance and availability
> metadata.**

Two different guarantees, and conflating them would be the central error of
this phase:

| | Guarantee | Holds for |
|---|---|---|
| **Archival history** | ST-EVA can attest that it held the fact on file at T | every archived observation, from the archive's first day forward |
| **Reconstructive history** | the source retains the fact *and* when it became public, so T can be answered even though ST-EVA was not running | SEC EDGAR, which serves historical filings with their original acceptance timestamps |

The SEC is the second kind, which is why SEC history is replayable to dates
before the archive existed. Yahoo fundamentals are the first kind only, and
nothing archived in 2026 makes their 2024 values replayable: nobody recorded
when they were published.

The consequence is a hard rule rather than a caveat:

> **Replay must not fill in a missing historical world for the sake of
> completeness.**

An `INSUFFICIENT` result is a successful replay. A fully-populated document built
from substituted or reconstructed data is a failure, however plausible it looks.
This is the single most important invariant in the phase, and it is test C's
entire subject.

### 0.3 Non-goals
- No backfill of history from elsewhere. An archive that ingests reconstructed
  history is not a point-in-time archive.
- No live trading, order routing, or portfolio state.
- No new valuation model, no new metric, no new provider.
- No time-series database, no distributed store, no compaction daemon.
- No change to the 2.2.3 CLI output.
- No agent work. That is 2.5.

## 1. Purpose

Restated as testable commitments. If a change to 2.4 makes one of these
untrue, the change is wrong regardless of what else it achieves.

1. A replay at T answers a question about T, using only information that
   existed at T.
2. A replay that cannot be answered says so, and says why, instead of
   approximating.
3. Two replays of the same T produce byte-identical documents.
4. A fact already archived never changes. A correction is a new fact.
5. A future version of ST-EVA can read a 2026 archive without rewriting it.

## 2. Archive invariants

These are the rules the archive must hold to be worth trusting. Each is
enforceable and therefore testable; none is a design intention.

```
I1  Raw observations are append-only.
I2  Historical observations are never overwritten.
I3  A revision creates a new observation in the same lineage, never an edit.
I4  available_at determines replay eligibility.
I5  retrieved_at never substitutes for available_at.
I6  Replay never uses information unavailable at the requested time.
I7  The same historical inputs reproduce the same context.
I8  A context snapshot is immutable; a later context supersedes it by link.
I9  The archive is a consumer of the Data Contract, never a source of it.
I10 Deleting the archive deletes no knowledge the CLI still needs.
```

**I1 and I2 are enforced by the database, not by convention.** The
`observations` table gets no `UPDATE` or `DELETE` path in the code at all, and
SQLite triggers reject them (§10.4). A rule that lives only in a docstring is a
rule that gets broken by the first bugfix under time pressure.

**I3 is the one that costs the most and buys the most.** Observed in 2.3-B:
Apple's FY2007 net income was filed as 4,834,000,000 and restated to
6,119,000,000 (+26.6%) four months later. An archive that kept only the latest
value would have made the restatement invisible, and any 2009 replay would have
been quietly rewritten by a 2010 filing.

**I4 and I5 together are the phase's core.** See §5.

**I9 is the architectural boundary.** The dependency runs
`Data Contract ← Archive`, never the reverse:

```
        st_eva_runner / adapters          (the Core)
                    |
             InvestmentContext            (the document)
                    |
        +-----------+-----------+
        |                       |
   archive.py              (nothing)
   (an adapter)
        |
   sqlite_archive.py
        |
   data/st-eva.sqlite
```

Swapping SQLite for PostgreSQL, DuckDB, Parquet, or a columnar lake means
writing one new module that satisfies the same interface. The contract, the
engine, and the document must not change. There is no ORM and no schema object
model: the archive serialises the Data Contract's own types, so the database
shape can be replaced without the contract learning anything about storage.

**I10 is what makes the archive safe to delete.** Nothing in the CLI reads the
archive to produce output. The archive is for questions the CLI cannot answer,
not for questions it already can.

## 3. Observation versioning

### 3.1 One row per (fact, filing)

An observation row is identified by the *content* of the fact, not by the time
it was seen:

```
content_hash = sha256(
    asset_id, metric, provider, taxonomy+concept, value,
    unit, currency, period_start, period_end, as_of,
    available_at, accession
)
```

Two runs that observe the same filing produce the same `content_hash` and
therefore the same row. A second filing reporting the same period with a
different value produces a different row and a new lineage link (§7).

### 3.2 The observation is a faithful copy, not a rendering

The archive stores the 2.3-A `Observation` fields *and* its `raw` payload
verbatim. It does not normalise, re-project, or re-derive anything. A stored
observation must round-trip to a byte-identical `Observation`, because
replay reconstructs contexts from these rows and any lossy step would show up
as a context mismatch with no way to tell a data change from a storage bug.

### 3.3 `first_archived_at` is a fourth date

The Data Contract has `as_of`, `available_at`, and `retrieved_at`. The archive
adds one:

| Field | Question |
|---|---|
| `as_of` | what moment does the value describe? |
| `period_start` / `period_end` | what window does it cover? |
| `available_at` | when did the source say it was public? |
| `retrieved_at` | when did *ST-EVA* ask? |
| `first_archived_at` | when did this archive *learn* of it? |

`first_archived_at` is what makes observational replay possible for a source
that declares nothing, and it is stored in the archive rather than the
contract because it is a property of the archive, not of the fact.

## 4. Source-document capture

> We can either record a number, or record the document the number came from.
> Only the second is worth keeping for years.

**Implemented in 2.4.1.** The SEC adapter returns the exact bytes it parsed,
each fact records the documents it was read from, and the archive stores them
content-addressed. An observation now resolves to a specific version of a
document, not to a URL that may serve different bytes tomorrow.

### 4.1 What is captured

| Field | Purpose |
|---|---|
| `content_hash` | sha256 of the response bytes; the document's identity |
| `uri` | the exact request URL, including query parameters |
| `canonical_uri` | the stable form of that URL, for reference |
| `http_status` | whether the response was actually the document |
| `fetched_at` | when the bytes were obtained |
| `byte_size`, `media_type` | for retention policy and integrity |
| `provider`, `document_type` | which source, and which kind of document |
| `content`, `content_encoding` | the captured payload, gzip-compressed |
| `first_seen_at` | first archival of this exact content |
| `storage_path` | an external location, when the payload is not stored here |

Documents are **content-addressed**: the same bytes are stored once, however
many observations reference them. A new version of the same endpoint is a new
row, linked by the same URI with a different `content_hash`.

`content_hash` always covers the **uncompressed** bytes, so it means the same
thing whether or not the payload was kept. A database that stores content and
one that stores only references therefore agree about which documents they
contain.

### 4.2 What this is for

Years later, "why does this observation say 4,834,000,000?" is answerable: the
`source_document_id` resolves to the exact XBRL document as EDGAR served it,
and every fact in it can be re-extracted. Without capture, only the extraction
survives, and a change in the adapter's parsing logic becomes permanently
unfalsifiable.

### 4.3 Sizing, measured

Real response sizes for one AAPL run:

| Document | Bytes |
|---|---|
| `company_tickers.json` | **798,244** |
| `submissions/CIK0000320193.json` | 163,991 |
| `EarningsPerShareDiluted.json` | 48,741 |
| `NetIncomeLoss.json` | 50,767 |
| `CashAndCashEquivalentsAtCarryingValue.json` | 30,428 |
| `Assets.json` | 19,972 |
| `RevenueFromContractWithCustomerExcludingAssessedTax.json` | 18,356 |
| `LongTermDebtNoncurrent.json` | 12,621 |
| `LongTermDebtCurrent.json` | 12,430 |
| `dei/EntityCommonStockSharesOutstanding.json` | 10,629 |
| **total, one run** | **1,166,179** |

`company_tickers.json` is **68% of the payload and is global**: identical for
every ticker and every run. It is captured once and content-addressed, so it
costs one row forever. Excluding it, a run is ~368 KB of issuer-specific
documents.

The remaining documents are *stable between filings*: the same
`companyconcept` returns byte-identical content until a new filing lands.
Content addressing therefore collapses the per-run cost to roughly the size of
whatever changed. The exact compression ratio is an empirical question 2.4
should measure and report rather than assume.

Naive worst case without deduplication is 1.17 MB × 250 runs × 50 tickers ×
10 years ≈ **146 GB**.

**Measured after 2.4.1.** A live AAPL run captured 10 documents totalling
1,166,179 bytes, and a *second* live run against the same archive added **zero
documents and zero bytes**, because SEC concept responses are byte-stable until
a new filing lands. The prediction in this section that content addressing
would collapse the per-run cost to whatever changed is therefore confirmed: the
realistic long-run cost is the cumulative set of distinct filings, not the
cumulative set of runs. `company_tickers.json` alone is 68% of one run and
costs one row forever.

`capture_content=False` records the hash and the URI without the payload, for a
source that is too large or too restricted to keep. The distinction is
visible: `content_encoding` is `NULL` for a reference and `gzip` for a
capture, and `content_for()` returns `None` for the former, so a missing
payload is never mistaken for an empty document.

### 4.4 Capture policy and retention

- **Capture by default** for the SEC concept and submissions endpoints: small,
  stable, official, and the actual evidence.
- **Capture by policy flag** for vendor endpoints, which are larger, less
  stable, and carry redistribution questions.
- **Compression** is a storage concern, not a correctness one: a gzip'd BLOB
  plus the hash of the *uncompressed* bytes, so `content_hash` always means the
  same thing.
- **Retention is never automatic deletion of evidence.** If a retention policy
  is added it must be explicit, logged, and must never remove a document that a
  stored observation still references. A dangling `source_document_id` is
  worse than no capture at all.

### 4.5 Unavailability of capture is recorded, not hidden

If a document could not be captured, the observation is still archived, with
`source_document_id = NULL` and a recorded reason. A run that silently lost its
evidence would be indistinguishable from a run that never fetched it.

## 5. `available_at` / `retrieved_at` semantics

The most important section in the document, because I4 and I5 live or die here.

### 5.1 The three dates, never merged

| Date | Meaning | Written by |
|---|---|---|
| `available_at` | when the value became public | the **source**, or a declared derivation |
| `retrieved_at` | when ST-EVA asked | ST-EVA |
| `first_archived_at` | when the archive learned of it | the archive |

`retrieved_at` is **never** copied into `available_at`. Ever. It is tempting,
because it is always populated and it would make every observation replayable,
and it is a fabrication: a figure published on 2026-07-31 and fetched on
2026-09-28 was not knowable on 2026-07-30. Substituting the two is the exact
error that produces a backtest that looks brilliant and is worthless.

### 5.2 Availability classes

Every archived observation carries one of:

| Class | Meaning | Replay eligibility |
|---|---|---|
| `SOURCE_DECLARED` | the source published when it became public (`ACCEPTANCE_DATETIME`, `FILED_AS_OF_DATE`, `OBSERVATION_INSTANT`) | from `available_at` |
| `UNDECLARED` | the source did not say, and the archive does not guess | **none**, under a strict replay |
| `ARCHIVE_FIRST_SEEN` | the source was silent; the archive dates it at first archival | from `first_archived_at`, **flagged as observational** |

`replay_eligible_from` is a stored, non-null column:

```
replay_eligible_from = available_at        when availability_class = SOURCE_DECLARED
                     = first_archived_at    when availability_class = ARCHIVE_FIRST_SEEN
                     = NULL                 when availability_class = UNDECLARED
```

A `NULL` `replay_eligible_from` means the observation is archived, queryable,
and **excluded from every replay**. That is the honest state for Yahoo
fundamentals seen for the first time today.

### 5.3 `ARCHIVE_FIRST_SEEN` is opt-in per source, and labelled forever

Archiving a silently-dated value is useful, so 2.4 supports it. It is never
presented as point-in-time truth:

- the class is stored, and appears in every replayed context's
  `knowledge_cutoff` accounting;
- a replay using an `ARCHIVE_FIRST_SEEN` observation reports
  `replay_fidelity: OBSERVATIONAL` instead of `SOURCE_DECLARED`;
- the distinction survives into every derived figure, because every figure's
  `inputs` name the observations it consumed and their classes are readable.

A single scalar `replay_fidelity` on the context, derived from the worst class
among the inputs, would be cleaner to consume. It is still a scalar grade over
provenance, so the per-observation class is the source of truth and the scalar
is a convenience that must be reconstructible from it.

### 5.4 What "the same time" means at second resolution

SEC acceptance timestamps have second resolution; a daily price has
date resolution. Replay at `T` uses `replay_eligible_from <= T` with `T`
parsed to a full ISO-8601 instant. A caller asking for `2026-06-30` gets
midnight UTC, so a filing accepted at `2026-06-30T21:00:00Z` is **excluded**,
which is correct: at the start of 2026-06-30 that filing did not exist. The CLI
must therefore make the instant explicit and never accept a bare date without
documenting the interpretation.

## 6. Deduplication

Three different kinds of near-duplicate, with three different correct answers.

### 6.1 Same fact, seen twice

The same `(metric, period, value)` reported by the 10-Q that first disclosed it
and again as a comparative inside the following 10-K. Observed constantly.

**Answer: one row, many sources.** The second sighting is stored as a
`source_document_id` link in `observation_sources`, with its own accession
preserved. The value is not duplicated and neither is the filing that saw it.

### 6.2 Same period, different value

A restatement. FY2007 net income: 4,834,000,000 then 6,119,000,000.

**Answer: two rows in one lineage.** Never merged, never overwritten. The
later row is simply the one a later replay sees, because its
`replay_eligible_from` is later. The earlier row remains queryable and a
replay before the restatement still shows the original figure. This is the
behaviour 2.3-B already implements, and the archive must not flatten it.

### 6.3 Same fact, from two providers

Yahoo and SEC both report revenue.

**Answer: two rows, two lineages, one concept.** Never deduplicated across
providers. Agreement between them is a 2.3-B `ValidationRecord`, and collapsing
them at archive time would destroy exactly the evidence cross-validation needs.

### 6.4 Deduplication is content-addressed, not heuristic

The key is `content_hash` (§3.1). Two rows collide only when every semantic
field matches, including the accession. There is no fuzzy matching and no
timestamp window, because both would eventually merge two facts that a human
would want kept apart.

## 7. Amendment / restatement lineage

`observation_lineage` groups every fact about the same `(asset, metric,
concept, period)` regardless of how many times it was restated:

```
lineage: aapl/revenue/us-gaap:RevenueFromContract.../fy2007
    |
    +-- observation 4,834,000,000   available 2009-10-27T16:30:00Z  accn 0001193125-09-000032
    +-- observation 6,119,000,000   available 2010-01-25T16:30:00Z  accn 0001193125-10-000204
                                         (an amendment, not an edit)
```

Rules:

1. **Lineage is created on first observation and never reparented.** A restated
   period stays in the lineage it was born in.
2. **The archive never chooses a winner.** Which restatement to believe is a
   policy question that belongs to 2.5 or to the consumer, exactly as in 2.3-B.
   A "latest value" column would be a silent policy decision, and 2.4 must not
   make one.
3. **`latest_knowable(cutoff)` is the selection rule**, and it already exists in
   2.3-A's `ObservationSet`. The archive reuses it rather than reimplementing
   it, which is the clearest evidence that the 2.3-A design anticipated this
   phase.
4. **Amendments are first-class.** A `10-K/A` or `20-F/A` produces a new
   observation with a later acceptance datetime, and the amendment relationship
   is recorded in `raw`, not inferred.
5. **Concept changes are lineage breaks.** A filer that moved from
   `us-gaap:Revenues` to `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`
   at ASC 606 adoption has a *different concept*, so a new lineage starts. The
   two are related but not comparable, and 2.3-B already classifies that as a
   methodology mismatch. Merging them at archive time would erase the reason.

## 8. Context snapshot

### 8.1 What is stored

The complete 2.3-C document, verbatim, plus a few archive-managed columns:

| Column | Purpose |
|---|---|
| `context_id` | the 2.3-C content hash; the identity of the knowledge |
| `document_json` | the exact document as emitted |
| `document_hash` | hash of the stored bytes, for tamper detection |
| `as_of` | the moment the context is about |
| `knowledge_cutoff` | the latest `available_at` the context used |
| `replay_fidelity` | `SOURCE_DECLARED` or `OBSERVATIONAL`, derived from inputs |
| `supersedes` | the `context_id` this one replaces, if any |
| `archived_at` | when the archive received it |

`context_id` is already a content hash over everything except the
when-we-asked fields, so the same context built twice is the same identity. That
is what makes `supersedes` meaningful rather than decorative: it chains by
*knowledge*, not by time.

### 8.2 Snapshots are immutable and deduplicated

Archiving a context whose `context_id` already exists is a no-op. A context is
a statement about knowledge; re-archiving the same statement adds nothing.

### 8.3 What a snapshot is *not*

A snapshot is not a prediction and not a result. It is a document describing
what was knowable. Its `limitations` block is stored with it, and
`SnapshotManager.update_outcome` from 2.2.3 continues to work on the separate
`history/` files. 2.4 does not move, rename, or reinterpret that directory.

## 9. Point-in-Time Replay

### 9.1 The algorithm

```
replay(asset, as_of=T):
    1. rows   = archive.observations_for(asset, replay_eligible_from <= T)
    2. set    = ObservationSet(rows)                  # 2.3-A type, unchanged
    3. pick   = set.latest_knowable(T, metric)        # 2.3-A, unchanged
    4. price  = pick("price")                         # must exist, see 9.3
    5. run    = the ordinary pipeline on `set`        # same code as a live run
    6. doc    = build_investment_context(run)
    7. stored = archive.context_at(asset, T)
    8. return compare(doc, stored)
```

Step 5 is the important one: **replay uses the ordinary pipeline.** There is no
second, simpler code path that could drift from the real one. The archive
supplies inputs; the engine and the document builder do the rest.

### 9.2 The comparison is the product

| Outcome | Meaning |
|---|---|
| `MATCH` | `document_hash` equal — the archive reproduces what was known |
| `DIVERGED` | same inputs, different document — a builder or engine change |
| `NO_SNAPSHOT` | no context was ever archived for T |
| `INSUFFICIENT` | not enough archived data existed at T to build a context |

`DIVERGED` is the most valuable outcome and must never be smoothed over. It
means either the code changed since archival (legitimate, and the diff is
useful) or the replay is not faithful (a defect). The archive must be able to
distinguish those, which is why `built_from` and the operation registry are
stored inside the document: a consumer can see that the archived context was
built by `2.3-C.1` and replayed by `2.3-D.3`, and judge the diff accordingly.

### 9.3 The failure that must never happen

> **Replaying T must never fall back to the most recent price.**

If no price was archived with `replay_eligible_from <= T`, the replay returns
`INSUFFICIENT` with the reason "no archived price knowable at T". It does not
use today's price, does not use the nearest earlier price silently, and does
not report a context with a substituted `as_of`.

This is the highest-severity defect this phase could ship, because it produces
a plausible, fully-populated, completely fictional document. It gets a
dedicated invariant, a dedicated error type, and a dedicated test.

### 9.4 Replay is a read operation

Replay never writes to the archive. If it did, a replay bug could corrupt the
thing being replayed, and the archive would stop being trustworthy because it
was used. Replays are logged to an ordinary log file, not to the database.

### 9.5 Replay is not the same as 2.3-C's point-in-time claim

2.3-C's `knowledge_cutoff` is *self-reported* by the context: it states the
boundary of one document's knowledge. 2.4's replay is *enforced* against a
persistent store. A context can only claim a cutoff if the archive confirms
that nothing later was used. A 2.4 replay therefore carries an extra fact —
`replay_verified: true` — that a 2.3-C document does not. That flag is earned
by the archive, not claimed by the document.

## 10. SQLite schema and migration rules

SQLite is the **first archive implementation**, not the data model. One file:

```
data/st-eva.sqlite
```

### 10.1 Interface first, SQLite second

`archive.py` defines the interface; `sqlite_archive.py` implements it. The
Core depends on `archive.py` only, and can be constructed with a
`NullArchive` that discards everything. The contract never learns what a
database is.

```python
class ArchiveStore(Protocol):
    def record_source_document(...) -> str: ...
    def record_observation(...) -> str: ...
    def record_context(...) -> str: ...
    def observations_for(asset, cutoff) -> List[Observation]: ...
    def context_at(asset, as_of) -> Optional[Dict]: ...
```

`observations_for` returns `Observation` objects, not rows. **The archive's job
ends at the contract boundary**; everything downstream of that is unchanged
code from 2.3-A/2.3-C.

**The store is read/write only; `replay` lives in `archive.py`, not in the
Protocol.** The store cannot know how to rebuild a context, because that
requires the engine and the document builder, and importing those would invert
the dependency. `archive.replay(store, asset, as_of, build_document)` therefore
takes the pipeline as an injected callable:

```python
def replay(store, asset, as_of, build_document) -> ReplayResult: ...
```

The Core injects the ordinary pipeline, so replay runs exactly the same code as
a live run (§9.1 step 5) while `archive.py` still imports nothing but
`data_contract`. This is the one place the Protocol in §10.1 is narrowed, and
it is narrowed in the direction the dependency rule already requires.

### 10.2 Tables

Ten tables. Not fifty.

```
assets(asset_id PK, ticker, cik, name, exchange, currency, first_seen_at)

sources(source_id PK, provider, source_type, base_url, user_agent,
        declared, notes)

source_documents(document_id PK, content_hash UNIQUE, uri, http_status,
                 media_type, byte_size, fetched_at, first_seen_at,
                 storage_path, compression)

observations(observation_id PK, asset_id FK, lineage_id FK, metric,
             provider, concept, value_json, unit, currency, currency_basis,
             period_start, period_end, as_of,
             available_at, available_at_basis, availability_class,
             retrieved_at, first_archived_at, replay_eligible_from,
             definition, methodology, status, raw_json, content_hash UNIQUE)

observation_lineage(lineage_id PK, asset_id FK, metric, concept,
                    period_start, period_end, created_at, note)

observation_sources(observation_id FK, document_id FK, accession,
                    PRIMARY KEY(observation_id, document_id))

validation_records(record_id PK, observation_id FK, kind, status,
                   reasons_json, comparison_basis_json, tolerance_json,
                   explanation, references_json, value_snapshot_json,
                   checked_at)

derived_values(context_id FK, ref, operation_json, expression, value_json,
               unit, deterministic, depends_on_json,
               PRIMARY KEY(context_id, ref))

context_snapshots(context_id PK, asset_id FK, as_of, knowledge_cutoff,
                  replay_fidelity, built_from_json, document_json,
                  document_hash, supersedes, archived_at)
```

Indexes that matter: `observations(asset_id, replay_eligible_from)` for replay,
`observations(content_hash)` for dedup, `observation_lineage(asset_id, metric,
period_end)` for restatement queries, `context_snapshots(asset_id, as_of)` for
`context_at`.

### 10.3 Column conventions

- **Identifiers are opaque strings** (`ctx_…`, `obs_…`, `line_…`). No
  auto-increment integers: an archive is copied, merged, and re-imported between
  machines, and integer primary keys do not survive that.
- **Times are ISO-8601 UTC text**, as the Data Contract already uses. SQLite's
  date functions are not a reason to diverge from the contract's format, and
  the format is what a consumer will read.
- **`*_json` columns hold canonical JSON** with sorted keys, so a byte
  comparison is a semantic comparison.
- **`replay_eligible_from` is NOT NULL in practice** except for
  `UNDECLARED` observations, where it is NULL by design. A CHECK constraint
  ties the three together so a row cannot claim an eligibility its class does
  not support.
- **No foreign keys to a "schema" or "type" table.** The contract owns that
  vocabulary; the archive references it by string.

### 10.4 Append-only enforcement

```sql
CREATE TRIGGER observations_no_update BEFORE UPDATE ON observations
BEGIN SELECT RAISE(ABORT, 'observations are append-only'); END;

CREATE TRIGGER observations_no_delete BEFORE DELETE ON observations
BEGIN SELECT RAISE(ABORT, 'observations are append-only'); END;
```

I1 and I2 enforced by the database. A bug, a mistaken migration, or a
well-meaning developer running `DELETE FROM observations` gets an error rather
than a quietly destroyed archive.

`context_snapshots` gets the same treatment. The only mutable table is
`source_documents.storage_path`, because a document may move without changing
its content, and even that is better handled by writing a new path.

### 10.5 Migrations

- `PRAGMA user_version` holds the applied version; it only increases.
- Migrations live in `archive/migrations/NNNN_name.sql`, applied in numeric
  order, each recording `version, name, checksum, applied_at` in
  `schema_migrations`.
- **Forward only.** A migration that destroys data is not a migration; it is a
  documented archival step followed by a migration.
- **Never edit an applied migration.** The recorded checksum is verified at
  startup and a mismatch aborts, because a rewritten migration means the
  archive's shape no longer matches what actually ran.
- **Idempotent.** Re-running is a no-op, so a partially applied migration can
  be re-run after a crash.
- `0001_initial` creates the ten tables, the append-only triggers, the
  constraints, and the indexes.
- `0002_source_capture` adds the captured content, the provider, and the
  document type. It is a **new** migration rather than an edit to `0001`, so
  the forward-only rule is exercised for real and an archive created by an
  earlier build migrates cleanly. `0001` has not been edited since it shipped,
  and its recorded checksum is verified on every startup.

### 10.6 Operational settings

`journal_mode=WAL` for concurrent read while writing, `foreign_keys=ON`,
`synchronous=FULL` for the archive (a lost write is a lost fact, and this is
not a throughput-bound workload). The archive is opened lazily so the CLI never
pays for it when it is not used.

### 10.7 What is captured by default

| Source | Payload | Reason |
|---|---|---|
| SEC company-concept | captured | small, stable, official, and the actual evidence |
| SEC submissions | captured | carries the acceptance timestamps replay depends on |
| SEC ticker map | captured, once ever | global and identical for every run |
| Market data vendor | referenced, not captured | larger, less stable, and redistribution questions |

A vendor document is recorded as a hash and a URI, so a fact from it is still
traceable to *something* identified, and the archive never has to answer for
holding a copy it should not hold.

## 11. The replay test that decides whether 2.4 is correct

This is the phase's acceptance criterion, and it is deliberately three tests
rather than one, because "rebuild and compare" can pass for the wrong reason.

### 11.1 Test A — round-trip determinism (the core)

```
archive a run at T
replay at T
assert document_hash is identical
```

This is achievable today and is the real test of I7. It fails if the builder is
not a pure function of the archived observations.

### 11.2 Test B — exclusion (the point-in-time test)

```
archive a run whose data includes a filing accepted AFTER T
replay at T
assert no observation with replay_eligible_from > T is present
assert the newer filing is absent by id
```

A replay that quietly includes later information is worse than no replay. This
test must also assert that the *excluded* observation is still in the archive —
replay filters, it does not delete.

### 11.3 Test C — honest insufficiency (the test that prevents fiction)

```
replay at a date before any price was archived
assert the result is INSUFFICIENT
assert no price was substituted
assert the reason names the missing archived price
```

A test that only checks "the context looks right" would pass against an
implementation that silently used today's price. This one cannot.

### 11.4 Test D — restatement survival

```
archive a period that was later restated
replay before the restatement  -> the original value
replay after the restatement   -> the restated value
assert both observations still exist in the archive
```

This is the test for I3, and the one that would catch an implementation that
kept only the latest value.

### 11.5 The user's stated test, and its honest scope

The stated test is *"replay AAPL at 2026-06-30, reject anything with
`available_at` after it, rebuild, and match the stored snapshot."*

Given the measured availability in §0.1, a 2026-06-30 replay can use every SEC
filing accepted on or before that date — so the TTM window, the fundamental
inputs, and most of the cross-source verdicts rebuild correctly. It **cannot**
use Yahoo's fundamentals, which were never dated, and it **cannot** use a Yahoo
price unless one was archived on or before that date.

So the test as stated is right in shape and must be run, but its expected
outcome for 2.4's first release is: *SEC history reconstructs; vendor history is
absent and is reported as absent.* Writing the test to demand a full match
would force the implementation to fabricate, which is the one outcome the phase
exists to prevent.

## 12. Stop condition

2.4 is complete when the archive persists a run, replay at that instant
reproduces the stored context byte for byte, replay strictly before an
observation's availability excludes it, replay with insufficient data reports
insufficiency rather than substituting, and a restatement is visible from both
sides of its date.

Work stops there. No 2.5, no agent experiments, no new provider, no new
valuation model, no time-series engine.

At that point the Core finally describes not just the present but the past:

> The same Data Contract that answers "what does this cost imply today" also
> answers "what could anyone have known on that date, and from which document".

That is the precondition 2.5 needs. Handing the same historical context to
different models only tests something if the context is verifiably the context
that existed at the time, and 2.4 is what makes that claim checkable rather
than asserted.
