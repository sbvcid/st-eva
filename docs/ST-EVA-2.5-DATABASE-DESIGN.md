# ST-EVA 2.5 — Database Design

Status: SPEC. Design only. No migration is applied by this document.
Companion to [2.5 Core Evidence Scope](ST-EVA-2.5-CORE-EVIDENCE-SPEC.md).
Baseline: `667d05d`, `context_schema_version 2.3-C.2`

## 1. What the archive already is

Ten tables exist at `667d05d`:

```
assets                issuer identity: ticker, cik, name, exchange, currency
sources               provider registry: provider, source_type, base_url
source_documents      content-addressed bytes: content_hash, uri, media_type,
                      byte_size, fetched_at, provider, document_type, content
observation_lineage   one fact about one period: asset, metric, concept, period
observations          the fact itself, 26 columns, append-only
observation_sources   observation to document, many-to-many
validation_records    what other evidence said, and its independence
derived_values        a computed figure, with its operation and operands
context_snapshots     a stored InvestmentContext, deduped on context_id
schema_migrations     applied migrations, with checksums
```

**This is a sound base and most of 2.5 is query and registry work, not schema
work.** The properties 2.5 depends on are already enforced:

| Property | Enforced by | Verified at |
|---|---|---|
| append-only observations | SQLite triggers | 2.4, 64 archive tests |
| document dedupe | `content_hash` UNIQUE | 2.4.1 |
| observation dedupe | `content_hash` UNIQUE over fact + concept + period + accession | 2.4.2 |
| restatement lineage | `observation_lineage`, never overwritten | 2.4 |
| point-in-time eligibility | `replay_eligible_from`, per-cadence window | 2.4.2 |
| derived recomputability | operation registry, parity check at build | 2.3-C, 2.4 replay |

## 2. The four things 2.5 adds

### 2.1 `metric_registry` — moves the data model out of a provider file

Today the metric-to-concept mapping is `sec_provider.SEC_CONCEPTS`, a
seven-entry dict. Growing Core Evidence to roughly thirty items would put a
data model in a provider module, where it will drift and where no query can
reach it.

```sql
CREATE TABLE metric_registry (
    metric            TEXT NOT NULL,
    provider          TEXT NOT NULL,
    taxonomy          TEXT NOT NULL,
    concept           TEXT NOT NULL,
    statement         TEXT,             -- INCOME | BALANCE_SHEET | CASH_FLOW
                                            -- CAPITAL_RETURN | MARKET
    concept_priority  INTEGER NOT NULL,  -- tried in order
    unit_expected     TEXT NOT NULL,
    currency_expected TEXT,
    definition        TEXT NOT NULL,
    is_core           INTEGER NOT NULL,
    cross_comparable  INTEGER NOT NULL,
    valid_from        TEXT,             -- a filer switching tag starts a
    valid_to          TEXT,             -- new lineage, not a new metric
    PRIMARY KEY (metric, provider, taxonomy, concept)
);
```

Three decisions carried directly from the Core Evidence scope:

- **`statement`** gives the flat 22-metric list the grouping the brief asks for,
  and it is what makes "AAPL's income statement for FY2026" a query rather than
  thirty predicates.
- **`concept_priority`** replaces the Python dict. `revenue` becomes three rows,
  not three `if` branches, and the order in which concepts are tried becomes
  data a consumer can read.
- **`cross_comparable`** replaces the hard-coded `COMPARABLE_METRICS` tuple. A
  metric is Core and independently not cross-comparable, and that is a normal
  fact about the metric rather than a constant in a module.

`is_core`, `definition` and `unit_expected` make the Core scope executable
rather than prose. A metric absent from the registry is not Core, which is the
correct default: adding a research item becomes a registry insert that a
reviewer can see, not a code change.

### 2.2 First-class filing identity on `observations`

Today accession, form, fiscal year, fiscal period, taxonomy and concept live
inside `raw.sec_fact`. That is correct for a document dump and wrong for a
database, because a query cannot reach into `raw`.

```sql
ALTER TABLE observations ADD COLUMN taxonomy        TEXT;
ALTER TABLE observations ADD COLUMN concept         TEXT;
ALTER TABLE observations ADD COLUMN accession       TEXT;
ALTER TABLE observations ADD COLUMN form            TEXT;
ALTER TABLE observations ADD COLUMN fiscal_year     INTEGER;
ALTER TABLE observations ADD COLUMN fiscal_period   TEXT;
ALTER TABLE observations ADD COLUMN statement       TEXT;
ALTER TABLE observations ADD COLUMN instant         INTEGER;  -- 1 for a point-in-time
CREATE INDEX observations_concept ON observations(asset_id, concept, period_end);
CREATE INDEX observations_filing  ON observations(accession);
```

No existing value changes. The columns are populated from the fields already
parsed into `raw`, and `raw` is retained, because a filing's raw frame
metadata is worth keeping even once the indexed columns exist.

`instant` is explicit rather than inferred from `period_start IS NULL`, because
"this is a balance-sheet date" is a statement about the filer and not a
side-effect of how a period was serialised.

### 2.3 `evidence_state` — the state of every Core item, per company

The Core scope's six states must be first class, because a query has to be
able to say "not reported" rather than "no rows".

```sql
CREATE TABLE evidence_state (
    asset_id    TEXT NOT NULL,
    metric      TEXT NOT NULL,
    state       TEXT NOT NULL,   -- SOURCE_REPORTED | SOURCE_DID_NOT_REPORT
                                  -- NOT_APPLICABLE | UNAVAILABLE
                                  -- CONFLICTING | STALE
    reason_kind TEXT,
    reason_code TEXT,
    as_of       TEXT,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (asset_id, metric)
);
```

`NOT_APPLICABLE` does not exist at `667d05d` and is the single most important
addition. A bank has no operating-income tag and a miner has no inventory, and
without this state both are recorded as retrieval failures. `reason_code` reuses
the 2.4.3 closed vocabulary, extended only with the codes these two states
need, so a refusal never becomes prose-only.

`CONFLICTING` and `STALE` are *derived* from the evidence and are written here
as a query index rather than as new truth. The conflict itself stays in
`identity_conflicts` and the staleness in `freshness`, both of which already
exist.

### 2.4 Redistribution tier on `sources`

The Core scope requires the tier to be decided before the first fetch.

```sql
ALTER TABLE sources ADD COLUMN redistribution_tier TEXT NOT NULL DEFAULT 'B';
ALTER TABLE sources ADD COLUMN rate_limit_per_second REAL;
ALTER TABLE sources ADD COLUMN fair_access_policy TEXT;
```

`A` retain and publish, `B` reference only, `C` never collect. Defaulting to
`B` is the safe direction: a source that is never classified keeps its bytes
local. The SEC fair-access policy travels with the source row instead of living
in a provider's constructor, so a second source cannot accidentally ignore it.

## 3. The one change that needs real care

### 3.1 Observation identity

At `667d05d` the adapter assigns `observation_id` — `ev-pe-band-001` for the
material set, `cmp-revenue-sec-<period>-<accession>` for the cross-source set.
It is a name, not a derivation.

That is tolerable for one run and wrong for a database. Two adapters describing
the same filed fact produce two ids, so:

- the same fact from two sources is stored as two facts and a content comparison
  cannot find them
- a query by concept and period has to try every naming convention
- a re-ingestion that changes nothing still depends on an adapter generating ids
  identically forever, and nothing enforces that

The fix is a derived identity:

```
observation_id = sha256(asset | provider | taxonomy | concept
                           | period_start | period_end | accession)
```

**Done additively.** A legacy `observation_id` column is retained, existing rows
are left untouched, and the derived id becomes an additional indexed column.
New ingests populate both. Replay keeps working against the legacy column, and
a future migration can backfill the derived id and prove equivalence per row
before any column is retired.

This is the only 2.5 change that touches the identity of data already
archived, and it is the reason the first experiment is one company: a bad
identity function is far cheaper to discover against one filer's history than
against six.

### 3.2 What deliberately does not change

- No re-keying of existing rows.
- No change to the 23 contract fields, the append-only triggers, the lineage
  model, the point-in-time selector, or the validation model.
- No change to the operation registry or to derived recomputability.
- No change to the 2.2.3 CLI output.

## 4. Migration plan

Forward-only, one file per step, each verifiable on its own. The 2.4 schema
already demonstrated the shape: `0001_initial`, `0002_source_capture`,
`0003_observation_basis`, each a checksum recorded in `schema_migrations` and
each verified at startup.

| Migration | Adds | Reversible? |
|---|---|---|
| `0004_metric_registry` | `metric_registry`, and backfill from `sec_provider.SEC_CONCEPTS` | yes, drop the table |
| `0005_filing_identity` | the seven first-class columns, populated from `raw` | yes, drop the columns |
| `0006_evidence_state` | `evidence_state`, `NOT_APPLICABLE` on the enum | yes, drop the table |
| `0007_source_tier` | redistribution tier and rate limits | yes, drop the columns |
| `0008_derived_identity` | derived `observation_id`, backfilled and verified | **no**, after verification |

`0008` is separated because it is the only one that is not trivially
reversible. It is gated on a check that, for every existing row, the derived id
is unique and that a re-ingest of an unchanged filing produces no new row.

## 5. Query surface

Read-only, over the existing tables plus the two new ones. No ORM, no query
DSL, no abstraction that would later need the storage engine's shape leaked
into it.

```python
class EvidenceQuery(Protocol):
    def describe_company(self, asset) -> CompanyCoverage: ...
    def list_metrics(self, asset) -> List[MetricDescriptor]: ...
    def get_observations(self, asset, metrics, period=None,
                         statement=None) -> List[Observation]: ...
    def get_series(self, asset, metric, basis=None) -> Series: ...
    def get_source(self, document_ref) -> SourceDocument: ...
    def get_provenance(self, observation_id) -> Provenance: ...
    def get_validation(self, observation_id) -> List[ValidationRecord]: ...
    def get_conflicts(self, asset) -> List[Conflict]: ...
    def coverage_report(self, asset) -> Dict[str, EvidenceState]: ...
```

Four properties the Core Evidence scope requires of it:

1. **It hides the schema.** A consumer learns ST-EVA's concept, not SQLite's.
2. **It returns states.** A metric with no rows comes back as
   `SOURCE_DID_NOT_REPORT`, `NOT_APPLICABLE` or `UNAVAILABLE`, never as an
   empty success and never as zero.
3. **Every figure carries its provenance blocks**, exactly as a 2.3-C figure
   does today, because a figure without them is not Evidence.
4. **It computes no interpretation.** No ratio, no ranking, no composite a
   consumer could mistake for a source figure.

`get_series` must return the 2.4.3 series semantics unchanged:
`series_status`, `series_status_reason`, per-group `bases`, and discontinuities
that only ever appear within one group. A query surface that forgot this would
quietly reintroduce the defect 2.4.3 removed.

## 6. Ingestion loop

The shape the brief describes, and the parts already present:

```
resolve company
  -> fetch submissions index
  -> diff against accessions already held          [NEW in 2.5]
  -> fetch only unseen accessions                  [NEW in 2.5]
  -> store documents by content_hash               [exists, 2.4.1]
  -> parse to observations
  -> store observations by derived identity        [NEW in 2.5]
  -> validate against held evidence               [exists, 2.3-B]
  -> update evidence_state                        [NEW in 2.5]
```

**The diff is the point.** The archive already prevents duplicate *storage*;
without the diff it does not prevent duplicate *fetching*, and a multi-year SEC
pull would re-download a decade of filings on every run, against a fair-access
policy that asks callers to be considerate.

The rate and budget policy moves from the provider's constructor to the
`sources` row, so it is a property of the source rather than of whichever
module happened to fetch it.

## 7. The first experiment, concretely

One company, one chain, end to end.

```
AAPL, multi-year 10-K and 10-Q
  SourceDocument   content-addressed, stored, tier recorded
  Observation      Income Statement subset of the Core list, with concept,
                   taxonomy, accession, statement, period, available_at
  Validation       vendor figures where they exist, with independence
  database         re-run adds zero rows
  Context          exported, 2.3-C.2, built from the database rather than
                   from a live fetch
```

**Acceptance, in order:**

1. A figure in the exported Context traces mechanically to accession,
   concept, period and `available_at`.
2. Re-running ingestion adds zero rows, at the document, observation and
   context level.
3. A metric the filer does not report comes back as `SOURCE_DID_NOT_REPORT`,
   not as an empty result.
4. A metric that does not exist for the business comes back as
   `NOT_APPLICABLE`. AAPL is a poor test of this, so it is asserted against a
   synthetic bank record rather than faked.
5. The prior archive still replays. Nothing already stored changes.

**Out of scope for the first experiment:** TSM and NU, which are `ifrs-full`
filers that the `us-gaap` concept set does not reach. They are the second
experiment, and the reason to extend the registry, not a reason to bend the
model.

## 8. What 2.5 does not build

- No new provider. The SEC ingestion of 2.3-B is extended, not replaced.
- No new valuation model. EBITDA stays Derived and `NOT_APPLICABLE` for a bank.
- No ranking, score, coverage percentage, or recommendation. Coverage is
  reported as states per company and per metric, and nothing more.
- No LLM in the ingestion, storage or query path.
- No new default CLI behaviour, and no change to the 2.2.3 output.
- No retroactive filling of a gap from a later filing, a vendor estimate, or a
  computed value.
