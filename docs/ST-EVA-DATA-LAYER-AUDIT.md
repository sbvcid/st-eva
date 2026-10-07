# ST-EVA Data Layer Audit — Phase 1: Existing Data Inventory

**Status:** READ-ONLY AUDIT. Nothing was designed, implemented, migrated or modified.
**Scope:** the data layer that already exists in `C:\git\st-eva` at commit `5e655a7`.
**Question asked:** can this data layer serve as the canonical data layer for
ST-EVA's future large-scale multi-company research?
**Date:** 2026-10-07

This phase inventories what exists and states gaps. It does not propose a schema,
and it creates no table.

---

## A. Existing DB inventory

### A.1 The headline finding

**There is no live database in this repository.** Zero `.sqlite`, `.db`,
`.sqlite3` or `.duckdb` files exist anywhere in the working tree (verified by
recursive extension search excluding `node_modules`, `.git/` and `.kilo/worktrees/`).

What exists is a **schema definition without a populated instance**:

| Artifact | Path | Size | Table count | Purpose | Classification |
|---|---|---|---:|---|---|
| Migration set | `archive/migrations/*.sql` | 19 files, ~72 KB | 26 tables, ~30 indexes, ~35 triggers | Forward-only schema lineage, 2.4 → 3.32 | **production** |
| Archive writer | `sqlite_archive.py` (93.9 KB) | — | — | `SQLiteArchive`: migration runner, record/insert/read API | **production** |
| Default archive path | `data/st-eva.sqlite` (runner `--archive` const, `web/service_adapter.py`) | — | — | CLI default `data/st-eva.sqlite`; web default `data/archives/<TICKER>.sqlite` | **production** |
| `data/archives/` | directory | exists, **empty** | — | web per-ticker archive target | **production** (empty) |
| `data/st-eva.sqlite` | — | **does not exist** | — | CLI archive default | absent |
| Research snapshots | `experiments/003-llm-evidence-retrieval/harness/*.sqlite` | **does not exist** | — | ~15 named snapshot DBs referenced by `measure_227.py`, `fullscope_bulk.py`, `metric_audit_228.py`, tests | **removed** (commit `b124123` "archive: remove experiment 003 from current tree") |
| Worktree copy | `.kilo/worktrees/pepper-chess/` | — | — | a second checkout with its own `archive/` and the 003 harness | tooling |

Two consequences follow immediately, and they shape the rest of this audit:

1. **The 26-table schema is the deliverable; the data is not.** Whether the
   schema actually holds 291,134 observations, 120 issuers or 8 bank filers
   cannot be verified here, because the archives that held those rows were
   removed with experiment 003 and were not committed. The counts quoted in the
   migration comments and in `docs/ST-EVA-2.5-DATABASE-DESIGN.md` are
   *design-time measurements from a prior corpus*, not state observable in this
   tree.
2. **The schema is exercised by 47 tracked test files** (`tests/`, 5.2 MB) that
   create their own temporary archives. So the schema is not untested — it is
   structurally exercised — but it is not populated.

### A.2 Migration lineage

| Version | File | Adds |
|---|---|---|
| 0001 | `initial.sql` | `schema_migrations`, `assets`, `sources`, `source_documents`, `observation_lineage`, `observations`, `observation_sources`, `validation_records`, `context_snapshots`, `derived_values` |
| 0002 | `source_capture.sql` | gzip `content BLOB` + `provider`/`document_type`/`canonical_uri` on `source_documents` |
| 0003 | `observation_basis.sql` | `observations.basis_json` (security / share / price basis) |
| 0004 | `source_policy.sql` | `redistribution_tier`, `fair_access_policy`, `contact_identity` on `sources` |
| 0005 | `evidence_state.sql` | `evidence_state` |
| 0006 | `source_fact_identity.sql` | `taxonomy`, `accession`, `form`, `fiscal_year`, `fiscal_period`, `statement`, `instant`, `source_fact_id` on `observations`; partial UNIQUE on `source_fact_id` |
| 0007 | `core_registry.sql` | `metric_registry`, `concept_registry`, `metric_concept_mapping` |
| 0008 | `ingestion_ledger.sql` | `held_filings`, `ingestion_runs`, `observations.source_concept_ref` |
| 0009 | `issuer_concept_adoption.sql` | `issuer_concept_adoption` |
| 0010 | `issuer_business_model.sql` | `issuer_business_model` |
| 0011 | `no_observations_state.sql` | widens `evidence_state.state` with `NO_OBSERVATIONS` |
| 0012 | `coverage_semantics.sql` | `ingestion_scope`, `declined_concept_mappings` |
| 0013 | `services_and_unmodelled_taxonomies.sql` | `unmodelled_taxonomies`; adds `SERVICES` to the business-model vocabulary |
| 0014 | `dimension_collisions.sql` | `ingestion_dimension_collisions`; `sources.retains_dimensions`, `aggregation_note` |
| 0015 | `exclusion_lifecycle.sql` | `metric_exclusion`; formalises `metric_inapplicable_in` as the refusal surface |
| 0016 | `metric_supersession.sql` | `metric_supersession` |
| 0017 | `knowledge_state_interpretations.sql` | `interpretations`; full UNIQUE index enabling the FK |
| 0018 | `mapping_relation_kind.sql` | `relation_kind`, `scope_json` on `metric_concept_mapping` (schema only; classification lives in `registry_seed.py`) |
| 0019 | `admissions.sql` | `admissions` |

### A.3 Domain-level schema summary

Six domains, not 26 tables.

**Identity** — `assets` (`asset_id`, unique `ticker`, unique partial `cik`,
`exchange`, `currency`, plus both `name` and `sec_entity_name` because the
filer's own name and the market data name differ and a replay must carry both).
Note this is *issuer* identity; there is no separate security/instrument table.

**Source & document** — `sources` (provider, type, URI, redistribution tier A/B/C,
`retains_dimensions` AGGREGATE/NONE). `source_documents` (`content_hash` UNIQUE,
gzip `content`, byte size, storage path, compression). This pair is the archive's
content-addressed store: "which document, which bytes, which hash".

**Fact** — `observation_lineage` (asset + metric + concept + optional period; a
lineage always exists even for a point-in-time or never-reported fact) and
`observations` (the wide row: `contract_id`, value JSON, unit, currency +
`currency_basis`, period, `available_at` + `available_at_basis` +
`availability_class`, `retrieved_at`, `replay_eligible_from`, `definition`,
`methodology`, `status` + reasons, `raw_json`, `content_hash` UNIQUE, and from
0003/0006/0008 `basis_json`, `taxonomy`/`accession`/`form`/`fiscal_year`/
`fiscal_period`/`statement`/`instant`/`source_fact_id`/`source_concept_ref`).

**Semantic registry** — `metric_registry` (statement ∈ INCOME/BALANCE_SHEET/
CASH_FLOW/CAPITAL_RETURN/MARKET, `unit_family` ∈ currency/per_share/count/ratio/
multiple, period type, applicability, comparability group), `concept_registry`
(taxonomy + concept, `source_definition` quoted verbatim), `metric_concept_mapping`
(`EXACT`/`EQUIVALENT`/`PARTIAL`/`NON_COMPARABLE` + effective window + optional
`relation_kind`), `metric_supersession` (append-only chain, `debt` →
`long_term_debt`), `metric_exclusion` (PROPOSED/TESTABLE/SUPPORTED/REFUTED/
UNDECIDED) and the separate refusal surface `metric_inapplicable_in`.

**Coverage & state** — `evidence_state` (per asset+metric, 7-state closed
vocabulary), `held_filings` (accession-keyed ingestion ledger),
`ingestion_runs` (counters), `ingestion_scope` (per run+metric: attempted,
mapping_count, status INGESTED/SOURCE_SILENT/NO_MAPPING/NOT_ATTEMPTED/ERROR),
`declined_concept_mappings`, `unmodelled_taxonomies`,
`issuer_concept_adoption`, `issuer_business_model`,
`ingestion_dimension_collisions`.

**Interpretation, replay & derived** — `interpretations` (a later reading of an
existing source fact, on a `knowledge_at` axis deliberately distinct from
`available_at`), `admissions` (which observation the engine took at one asset /
instant / metric under named `registry_state_identity` and
`resolver_policy_identity`), `context_snapshots` (immutable, hashed document),
`derived_values`, `observation_sources`, `validation_records`.

### A.4 Invariants enforced *by the database*, not by convention

This is the most important structural property and the main reason to keep this
schema. Triggers abort the write, they do not merely document it:

| Invariant | Mechanism |
|---|---|
| `observations`, `context_snapshots`, `interpretations`, `admissions`, `metric_supersession`, `source_documents` are append-only | `BEFORE UPDATE` / `BEFORE DELETE` triggers raising `RAISE(ABORT)` |
| A `SOURCE_DECLARED` observation must carry `available_at` | insert trigger |
| An `UNDECLARED` observation is never replay-eligible | insert trigger |
| A stored document with content must have hash + encoding + byte size | insert trigger |
| `PARTIAL`/`NON_COMPARABLE` mappings must record an effective window | insert trigger |
| Closed vocabularies on `statement`, `unit_family`, `applicability`, `evidence_state.state`, `business_model`, `business_model.basis`, `decline reason_code`, `unmodelled_taxonomies.kind`, `ingestion_scope.status`, `redistribution_tier`, `source_concept_ref` shape | insert triggers |
| Negative states must not carry a locator (no second unchecked copy of a value) | insert trigger |
| A `DECLARED_BY_ISSUER` or derived business model must name its source | insert trigger |
| A decline must state why, not only which category | insert trigger |
| Two sources reporting the same number stay two observations | deliberate *absence* of a uniqueness constraint on (concept, value, period) |
| One raw fact in one document is stored once | partial UNIQUE on `source_fact_id` |

---

## B. Existing canonical concepts

Requested mapping: Concept | Existing location | Canonical? | Notes.

| Concept | Existing location | Canonical? | Notes |
|---|---|---|---|
| **Company / Issuer** | `assets` (`asset_id`, unique `ticker`, unique partial `cik`, `sec_entity_name`, `exchange`, `currency`); `issuer_business_model`; `issuer_concept_adoption` | **Yes** | Strongest asset in the schema. CIK uniqueness, dual naming, business model with mandatory declared source. Scales to any issuer count with no structural change. |
| **Security** | *No dedicated relation.* `assets.currency`, `assets.exchange`, and `observations.basis_json` (added by 0003 for "a price quoted per ADS and a filing count of ordinary shares") | **No — absorbed** | `basis_json` exists precisely because there is no instrument table. One `assets` row = one issuer. ADRIs, dual listings, per-ADS vs per-ordinary-share, and non-USD securities have no first-class identity. This is a real gap for a multi-company study, not a cosmetic one. |
| **Filing** | `held_filings` (PK `(asset_id, accession)`), plus denormalised `observations.accession` / `.form` / `.fiscal_year` / `.fiscal_period` / `.report_date`-adjacent fields, and `ingestion_dimension_collisions.accession` | **Yes** | Accession-keyed by design; 0008's comment explains why an amendment arrives under a new accession. Filing identity is duplicated on `observations` deliberately, for index-level queryability (0006's stated motivation). |
| **Source Document** | `source_documents` (`content_hash` UNIQUE, gzip `content`, `storage_path`, `compression`), `sources` (redistribution tier, `retains_dimensions`) | **Yes** | Content-addressed with byte retention and a tier system. Already supports "keep bytes locally, publish the pointer". |
| **Observation** | `observations` + `observation_lineage`, `observation_sources` | **Yes** | Widest and most mature relation. Replay filter (`replay_eligible_from`), availability class, basis, filing identity, lineage for restatement. |
| **Evidence** | `evidence_query.py` (production, 85 KB) builds `Evidence` in-memory from the archive; `evidence_state` records *why* something is absent; `evidence_valuation_boundary.py` (48.8 KB) is the admission/refusal layer | **Partly** | `evidence_state` is canonical. `Evidence` itself is **not persisted** — it is a query product assembled at read time. A Historical P/E observation is an Evidence-shaped thing, so this distinction matters. |
| **Admission** | `admissions` (0019) — decision identity `(asset_id, decided_at, metric)`, `supersedes` chain, `registry_state_identity` + `resolver_policy_identity`, price recorded by identity not value | **Yes** | Deliberately separate from `observations`: "WHAT the source said" vs "WHICH of it the engine took". Its header records that `Observation.role` was measured and rejected (291,134 rows would have to be re-keyed). |
| **Valuation** | `metric_registry` admits `statement = 'MARKET'` and `unit_family = 'multiple'`; `data_contract.py` declares `METRIC_PE_BAND`, `METRIC_EV_EBITDA_BAND`, `METRIC_TRAILING_EPS`, `METRIC_PRICE`, `METRIC_MARKET_CAP`, `METRIC_ENTERPRISE_VALUE`, and a `ValuationInputs` dataclass | **Registry only** | The *vocabulary* for valuation is canonical and closed. There is **no persisted valuation observation, no valuation band table, no reverse-valuation record**. `ValuationInputs` is not in the schema. |
| **Registry** | `metric_registry`, `concept_registry`, `metric_concept_mapping`, `metric_supersession`, `metric_exclusion`, `metric_inapplicable_in`; seeded by `registry_seed.py` (94 KB) | **Yes** | The registry's own discipline is the archive's strongest quality signal: concept ≠ metric; adoption is per-issuer evidence not a concept window (0009); applicability and availability are kept apart (0011); a `TESTABLE` rule holds no production authority (0015). |
| **Archive** | `archive/migrations/`, `sqlite_archive.py`, `data/st-eva.sqlite`, `data/archives/<TICKER>.sqlite` | **Yes (schema), unpopulated** | Forward-only, checksum-verified, transaction-wrapped (0017 documents why: `executescript` autocommits otherwise). |
| **Provenance** | `observation_sources`, `observations.source_url` / `source_concept_ref` / `taxonomy` / `accession` / `form`, `source_documents.uri`, `validation_records.references_json`, `admissions.superseded_accessions` | **Yes** | Multi-hop and answerable without leaving the record. |
| **Content hash** | `source_documents.content_hash` (of *uncompressed* bytes) and `observations.content_hash` (UNIQUE, canonical form) | **Yes** | Two distinct hash domains, correctly separated. `observation_content_hash()` in `sqlite_archive.py` is the canonical function. |
| **Replay** | `observations.replay_eligible_from` + `availability_class` + `available_at`; `context_snapshots` (immutable, `document_hash`); `interpretations.knowledge_at`; `admissions.decided_at`; `historical_state_reconstruction_331.py`; `tests/test_archive_replay.py` | **Yes — three distinct time axes** | The archive deliberately separates *source availability*, *ST-EVA's knowledge*, and *the engine's decision*. 0017's header is explicit that folding a parser correction into `available_at` "is how a point-in-time contract is quietly destroyed". |
| **Research Run** | `ingestion_runs` (counters, per asset, `status`, `error`) | **Partial** | An *ingestion* run. There is no record of a research run, its question, its inputs, or its conclusion. 0012's `ingestion_scope` is per-run-per-metric but its scope is what was *retrieved*, not what was *investigated*. |
| **Research Artifact** | **Nowhere.** `tests/` holds 35 tracked `reports/2_*.md` in the repo, and `experiments/**` holds ad-hoc outputs, but none is a schema relation | **No** | Reports are version-controlled Markdown. They are not addressable, not hash-tracked, and not linked from the archive. The MSFT validation's `negative_path_no_furnished.json` — a deterministic conformance artifact — has no canonical home. |

---

## C. Multi-company scalability

**Question:** if AAPL, MSFT, MU, NVDA, TSM, NU and 100 further companies are added
tomorrow, which parts of the existing DB support them directly?

### C.1 Supported directly, no gap

| Area | Evidence |
|---|---|
| Issuer registration | `assets` keyed by CIK with partial unique index; 0010's `issuer_business_model` requires a named source for any declared model. Adding 106 issuers is 106 INSERTs. |
| Per-issuer fiscal and calendar differences | `observations.fiscal_year` / `fiscal_period` / `period_start` / `period_end` / `instant`. The Historical P/E contract's `fiscal_year_end_month` derivation has no column, but it is a function of `period_end` plus an issuer-declared constant, so it does not need one. |
| Per-issuer concept adoption | `issuer_concept_adoption` with `fact_count` / `filing_count` and a closed `OBSERVED_ADOPTION` basis. 0009 exists precisely because one AAPL-seeded window was masquerading as a general rule across MSFT and NVDA. |
| Per-issuer applicability | `issuer_business_model` + `metric_exclusion` → `metric_inapplicable_in`. |
| Filing-scale growth | `held_filings` + `source_documents` content-addressing. 0008 exists because re-downloading a decade of filings per run was "indefensible". |
| Coverage honesty at scale | `ingestion_scope` separates "never asked" from "asked and the filer was silent". This is the single most important table for scaling to 100 companies, because at that size most metrics will be absent for most issuers and a naive count would be meaningless. |
| Endpoint ambiguity at scale | `ingestion_dimension_collisions` per (run, asset, metric, concept, period, unit). Measured at 404 collisions across 8 bank filers; at 100 issuers this would be thousands. |
| Point-in-time replay at scale | Three separated time axes, append-only, with `replay_eligible_from` indexed by `(asset_id, replay_eligible_from)`. |

### C.2 Actual gaps — only these, no padding

1. **No security / instrument identity.** `assets` is an issuer. For 106 issuers
   this is fine; for ADRIs, dual-listed names, per-ADS securities, or any issuer
   with two traded securities, price and EPS cannot be bound to an instrument
   identity. `observations.basis_json` is the mitigation and it is a JSON blob,
   not a relation. The Historical P/E contract's `HistoricalPriceEvidence` carries
   `instrument_id` — there is nowhere canonical to put it.

2. **No corporate-action / split-adjustment evidence.** `sources` has
   `retains_dimensions`; `source_documents` has bytes. Nothing represents an
   ex-date or a split ratio. ADR Decision 8 and Contract Invariant F-6 require
   price and EPS accounting bases to be reconcilable, and §B.3 `accounting_basis`
   has no column. The AAPL POC handled its 4:1 split by choosing `as_traded`
   pricing; the MSFT window had no split, so the invariant held *vacuously*. At
   100 issuers, splits are certain and the schema cannot express the difference.
   (Contract §K.4 leaves the schema OPEN by decision — this is not an oversight in
   the archive, it is an open decision the archive has not absorbed.)

3. **No `fiscal_year_end_month` per issuer.** The contract's §E.1 derivation
   depends on the issuer's *declared* fiscal year end month. `assets` does not
   carry it. It currently lives only in SEC SGML headers captured as
   `source_documents` bytes and in experiment scripts. The contract itself flags
   this: "`fiscal_year_end_month` is a property of a fiscal year, not of the
   issuer… This contract does not define that resolution and it is OPEN (§K.4)."
   The data layer has the same hole.

4. **No evidence-class distinction (`filed` vs `furnished`).** This is the
   largest semantic gap. `observations` has `form` and `accession` but nothing
   recording that a Form 8-K Item 2.02 EX-99.1 exhibit is *furnished* and
   expressly not deemed filed for Section 18. ADR Amendment 1 Decision 10 makes
   that distinction load-bearing; Decision 11 forbids laundering it into
   `audited`. The archive's `source_type` and the `sources.redistribution_tier`
   are about redistribution, not legal status. Nothing in the schema can express
   the difference between a filed statement and a furnished exhibit.

5. **No three-valued `audit_status`.** `data_contract.py` has no such enum, and
   the schema has no column. ADR Decision 11 requires `audited` /
   `unaudited_reviewed` / `unaudited` as distinct attributes that must not imply
   one another. Currently derivable only from `form`, which the MSFT validation
   showed is wrong — MSFT tagged quarter-length diluted EPS in 8-K filings from
   2011–2015, so form alone would have misclassified 16 facts as `filed`.

6. **No research-run or research-artifact relation.** Ingestion runs are
   recorded; investigations are not. For a programme whose main output is
   *findings*, this is the gap that will bite hardest as the number of studies
   grows.

7. **Multi-tenancy shape is per-ticker files, not one corpus.** The web adapter
   uses `data/archives/<TICKER>.sqlite`; the CLI uses a single
   `data/st-eva.sqlite`; the research scripts used ~15 named snapshot files.
   Three different conventions. A canonical layer needs one, and cross-company
   queries (peer comparison, cohort censuses, population design — most of
   `reports/`) are only possible in the single-file shape. Note that ADR §5.2
   currently excludes peer comparison from scope, so this is not urgent, but the
   inconsistency is real.

8. **Price is not a first-class observation.** `data_contract.py` declares
   `METRIC_PRICE` / `METRIC_PRICE_HISTORY`, and `admissions` references
   `price_contract_id` by identity — so price observations clearly exist in the
   model. But price as a *time series* has no storage-design story in the
   migrations; `observations` carries a single `as_of` per row. A daily close
   series for 106 issuers is a different storage question from a filing-fact
   series, and it is unaddressed.

---

## D. Historical P/E integration gap

Integration gap analysis only. No design proposed.

### D.1 AAPL POC — what already has a home

| POC artifact | Canonical counterpart | Assessment |
|---|---|---|
| Price series (`raw/daily_prices.json`) | `observations` with `metric = price` | **Partial.** Shape fits; volume at daily × 106 issuers is unresolved (C.8). `accounting_basis` has no column (C.2). |
| Quarter EPS from 10-Q XBRL (`raw/eps_diluted_concept.json`) | `observations` with `source_concept_ref = us-gaap:EarningsPerShareDiluted`, `taxonomy`, `accession`, `form`, `fiscal_year`, `fiscal_period` | **Good fit.** 0006 added exactly these columns for exactly this purpose. |
| SGML `ACCEPTANCE-DATETIME` (`raw/headers/*.txt`, 43 files) | `source_documents` bytes + `observations.available_at` / `available_at_basis` | **Good fit in principle.** ADR Decision 12 makes the SGML header the *authoritative* acceptance source and the submissions-API field non-conformant; `available_at_basis` is exactly the column that would carry which one was used. Strong match. |
| Content hashes of exhibits | `source_documents.content_hash` | **Direct.** |
| TTM denominator (4 quarters summed) | `derived_values` with `depends_on_json` + `deterministic` | **Direct.** This is the intended home for a derived figure with a recomputable operation. |
| `historical_pe_points.json` observations | `observations` with `metric = TTM_GAAP_DILUTED_PE`, `unit_family = 'multiple'`, `statement = 'MARKET'` | **Shape fits, three fields missing.** Needs `evidence_class` (C.4), `audit_status` (C.5), `accounting_basis` (C.2). |
| Negative-path state (`UNAVAILABLE` / `REASON_MISSING_Q4_EPS`) | `observations.status` + `status_reasons_json`; or `evidence_state` | **Direct**, and the reason-code enumeration is already closed elsewhere. `evidence_state`'s 7-state vocabulary is orthogonal to the ADR's `AVAILABLE`/`UNAVAILABLE`/`REFUSED` — a genuine vocabulary collision to be aware of, not a defect. |
| 31 evaluation dates (sampling) | `observations.as_of`; `admissions.decided_at` | **Direct.** Contract §E.4 requires the selection strategy be named, versioned and monotone — that belongs on the run, which does not exist (C.6). |
| `input_set_id` / `logic_version` / `content_hash` replay identity | `observations.content_hash` + `derived_values.depends_on_json` | **Partial.** `content_hash` is canonical; `input_set_id` and `logic_version` have no column. |

### D.2 MSFT validation — what already has a home

| Validation artifact | Canonical counterpart | Assessment |
|---|---|---|
| 23 Item 2.02 furnished extractions | `observations` + `source_documents` | **Blocked by C.4.** The extraction worked and the values are sound, but the schema cannot record that these are *furnished*. They would land indistinguishable from filed statements — exactly what ADR Decision 10 and Invariant F-5 forbid. |
| `evidence_class` keyed on Item 2.02 code, not form (Finding J.3) | *nowhere* | **Gap.** The validation's own finding is that form is the wrong discriminator. The schema offers only `form`. |
| `legal_status_note` (Section 18 language) | *nowhere*; `sources.notes` is about redistribution | **Gap.** Contract §B.2 makes it mandatory for furnished evidence. |
| `candidate_evidence_classes_enumerated` (audit precondition for `REASON_MISSING_Q4_EPS`) | `status_reasons_json` | **Fits.** Structured JSON is already the convention. |
| Fiscal identity without a 10-K list (Finding J.1 / F-3) | `observations.fiscal_year` / `.fiscal_period` / `.period_end` | **Fits for storage.** The *derivation* needs `fiscal_year_end_month` per issuer (C.3). |
| `msft_negative_path.json` — deterministic conformance artifact | *nowhere* | **Gap.** Contract §I.3 item 3 and §L.2 cite it as the byte-for-byte reproduction of the prior 12/31 state. It is a research artifact (B, C.6). |
| 7 failure-path scenarios | `admissions` + `refusals_json` | **Good fit.** `admissions` exists precisely to record refusals as rows rather than absences. |
| `raw/source_manifest.json` (sha256 of frozen inputs) | *nowhere* | **Gap.** No input-set manifest relation. `observations.content_hash` hashes the observation, not the input set. |
| `raw/prices.json` — "validation-only scratch data, no provider chosen" | — | Correctly uncanonical. The contract chose no provider (§B.3); the archive should not either. |

### D.3 What is *only* experiments

Nothing in `experiments/aapl-historical-pe-poc/` is canonical, and nothing needs
to become canonical as a *file*. Specifically:

- All frozen raw SEC byte sets — primary-source evidence, but evidence for a
  validation, not operational data. The schema already stores exactly this shape
  in `source_documents`, which is the point: the same bytes belong in the archive
  when an observation derives from them.
- All `out/*.json`, `out/*.txt`, `out/*.csv` — reports of one validation run.
- `phase1_fiscal_identity/` — a sub-study whose finding (fiscal identity without
  a 10-K list) *is* canonical and is already encoded in Contract Invariant F-3,
  but whose data is not.
- The 7 + 8 pipeline scripts — the methods that produced C.1, J.1, J.2, J.3.
- `q4_study/out/additivity_check.txt` — empirical support for ADR Decision 4.
  The decision is canonical; the check is evidence for it.

### D.4 What plausibly *should* become canonical data

Stated as candidates for a decision, not as a design. Each names why the
current home is inadequate.

| Candidate | Why it would need to be canonical | Precedent in the archive |
|---|---|---|
| Evidence class (`filed`/`furnished`) + `legal_status_note` | ADR Amendment 1 Decision 10 makes it load-bearing for every TTM denominator; F-5 forbids laundering | The registry already separates concept from metric, adoption from meaning, applicability from availability. This is the same class of separation. |
| Three-valued `audit_status` | Decision 11 requires the three values be distinct and non-implying; `form` is provably the wrong discriminator (MSFT 2011–2015) | Same precedent. |
| Issuer fiscal calendar (`fiscal_year_end_month`, drift flag) | Contract §E.1 derivation and F-3 both depend on it; it currently lives only in captured SGML bytes | `issuer_business_model` is already declared issuer metadata with a mandatory source |
| Security / instrument identity | `HistoricalPriceEvidence.instrument_id`; ADRIs and dual listings among a 106-issuer universe | `assets` is the only identity relation |
| Price time series storage design | P/E is price ÷ EPS; `observations` carries one `as_of` per row | `admissions.price_contract_id` shows price is already an observation by identity |
| Input-set manifest / `input_set_id` / `logic_version` | Contract §I.1 replay guarantee is stated over a frozen input set | `schema_migrations.checksum` is the same idea for migrations |
| Research run + research artifact | The programme's output is findings; 35 reports and 5 sub-studies are currently unaddressable | `ingestion_runs` is the ingestion analogue |

---

## E. Experiments vs canonical boundary

Applying the standing rule from `WORKSPACE-INVENTORY.md` — *a contract is governed,
not experimental; research is not* — to the data layer:

**Canonical (goes in the archive):**

- Facts a source stated, with accession, concept, period, availability, content
  hash → `observations` + `source_documents`.
- Decisions about facts: admissions, interpretations, metric supersession,
  exclusion state → their existing relations.
- Negative states, declines, coverage scope → `evidence_state`,
  `declined_concept_mappings`, `ingestion_scope`.
- Anything a future query must be able to answer.

**Not canonical (stays a report):**

- Any finding stated in prose. `report.txt`, `verification.txt`,
  `failure_paths.txt`, `prior_vs_current.txt` are *evidence about* a computation,
  not the computation's data.
- Frozen raw byte sets kept only so a past validation can be re-checked. These
  are held in private archive; they become canonical only when an observation
  cites them.
- Scripts, harnesses, snapshots.
- The negative-path artifact — **with one caveat.** It is not canonical data,
  but it is a *deterministic conformance artifact* that a governing document
  (Contract §I.3, §L.2) cites. Under the inventory's rule, "when an `out/` file is
  cited by a governing document, it becomes a governed artifact and is
  preserved." It is governed, not canonical, and it currently has no home that
  expresses either.

**The boundary is currently unstated.** Nothing in the repo records which side of
this line any artifact is on. That is a documentation gap, not a schema gap, and
it is the cheapest of the seven gaps to close.

---

## F. Whether the existing DB is sufficient

**No — but the shortfall is narrow and well-localised.**

The schema is stronger than typical for this kind of system, and its strength is
in discipline rather than breadth. Six separations that most schemas of this size
have collapsed are here kept distinct by trigger: observation vs admission;
source fact vs interpretation; source availability vs ST-EVA's knowledge vs the
engine's decision; concept vs metric; adoption vs meaning; applicability vs
availability. Each was written because a measurement showed collapsing it
produced a wrong answer. That is the part worth preserving intact.

The gaps fall into two classes, and the distinction matters for sequencing.

**Class 1 — blockers for the Historical P/E method specifically (4 items)**

1. `evidence_class` + `legal_status_note` (C.4)
2. `audit_status` three-valued (C.5)
3. `accounting_basis` / corporate-action provenance (C.2)
4. `fiscal_year_end_month` per issuer (C.3)

Without these, a TTM GAAP diluted P/E observation cannot be stored without
either losing a load-bearing distinction or storing a false one. This is not a
scale problem; it is a correctness problem, and it is the same problem ADR
Amendment 1 was written to fix. Note the contract already forbids laundering
evidence class (F-5) and requires `audit_status` as a distinct field — so the
schema is currently *incapable of representing a conforming observation*.

**Class 2 — blockers for 100-company scale, not for Historical P/E (4 items)**

5. Security / instrument identity (C.1)
6. Research run / research artifact (C.6)
7. Multi-tenancy shape convergence (C.7)
8. Price time-series storage design (C.8)

Also worth stating plainly: **the archive is unpopulated.** Whatever is built next
starts from an empty database, so the first real corpus will be its first
migration test at scale — which is an argument for a small pilot before a large
one, not a reason to defer.

And one item that is **not** a gap, to prevent it being re-raised: multi-company
scale itself. Issuer registration, per-issuer fiscal periods, per-issuer concept
adoption, per-issuer applicability, coverage honesty, endpoint ambiguity and
point-in-time replay are all already first-class and scale without change. 106
issuers is not the hard part.

---

## G. Smallest next engineering step

Not a design. The smallest step that would convert the two Class-1 blockers from
*known* to *decided*, without writing a migration.

**Step: put the evidence-class and audit-status question in front of an ADR, as a
narrow amendment in the form of Amendment 1.**

Concretely: a decision document that answers four questions and nothing else —

1. Does `evidence_class` (`filed` / `furnished`) become a first-class attribute
   of `observations`, or of `sources`, or of neither?
2. Where does `legal_status_note` live, and what is mandatory when?
3. What are the three `audit_status` values' names and their derivation rule —
   given that `form` is provably the wrong discriminator?
4. Does `accounting_basis` become a column, a structured `basis_json` extension,
   or remain an observation-level obligation?

Why this and not a migration:

- It is pure decision work; it changes no schema, no code, no archive.
- It is the step whose *absence* is why Class 1 cannot be scheduled. A migration
  written before this is decided would encode an unstated choice as structure,
  which is precisely the failure ADR Amendment 1's Decision 4 documents (a
  derived quantity recorded as if it were a reported one).
- It is bounded. Four questions, one document, no code — comparable in size to
  what Amendment 1 already does.
- Its absence is also blocking the second-issuer question. The MSFT validation
  proved the contract is issuer-agnostic, and §B.2.1 now states the parser
  contract. What is *not* stated anywhere is where an issuer-agnostic evidence
  class and audit status are persisted. The contract says what they mean; the
  data layer says nothing.

Once that decision exists, the smallest *schema* step follows directly and is
small: one migration adding the decided fields, then re-running the AAPL and MSFT
validations against a real archive to confirm a conforming TTM observation
round-trips. Both validations already produce the exact rows that would be the
test — that is a useful property of the current position and worth preserving.

Deliberately excluded from this recommendation: corporate-action schema
(Contract §K.4 is OPEN and the AAPL/MSFT evidence is one split and zero splits
respectively — insufficient to decide), and any migration.

---

*Phase 1 complete: read-only inspection. No file was modified, created, moved or
deleted except this document. `experiments/` untouched. No `git add`, `commit`,
`reset` or `clean`. No DB was opened for writing; no schema was altered; no
migration was applied or authored.*