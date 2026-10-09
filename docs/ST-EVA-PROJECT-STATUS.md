# ST-EVA Project Status Checkpoint

**Purpose:** A factual, verifiable checkpoint of the repository state as it stands, so that any subsequent session or contributor can establish current progress, frozen boundaries, open decisions, and next steps without re-deriving or guessing.
**Basis:** Direct, reproducible inspection of `C:\git\st-eva` at commit `10d298f` only. Nothing here is speculative, inferred, or prematurely claimed.
**Date:** 2026-10-09
**Status:** FACTUAL CHECKPOINT — VERIFIED AGAINST DISK & GIT

This document records state. It introduces no new architectural decisions, modifies no formal ADRs, alters no methodology contracts, changes no database schemas or migrations, and confers no implementation authorizations.

---

## 1. Git Baseline & Working Tree Metrics

Measured directly at `10d298ffbc315c20070b27472b407ac3ed2337aa` on 2026-10-09. This section records the repository baseline state as of commit `10d298f`. This checkpoint documents the repository baseline at `10d298f`. The status-file update was subsequently committed as a documentation-only change; that later commit does not alter the measured baseline described here.

### 1.1 Git Metadata

| Item | Value |
|---|---|
| Commit SHA | `10d298ffbc315c20070b27472b407ac3ed2337aa` |
| Short SHA | `10d298f` |
| Commit Subject | `docs: add Amendment 10 v10 draft` |
| Branch | `master` |
| Remote URL | `origin` -> `https://github.com/sbvcid/st-eva.git` |
| Remote Sync | `## master...origin/master` — **in sync, 0 ahead, 0 behind** |
| Prior Checkpoint Commit | `0becbdc` (`docs: reconcile ST-EVA data admission rules`, 2026-10-07) |
| Baseline Working Tree State | At measured baseline `10d298f`: clean tracked tree (0 staged, 0 modified, 0 deleted); only untracked `?? data/` present. This describes the baseline commit, not the later documentation-only commit that records it. |

### 1.2 Progression Lineage (0becbdc -> 10d298f)

Forty-three commits advance the repository between the 2026-10-07 checkpoint (`0becbdc`) and this checkpoint (`10d298f`), spanning eight major development clusters:

| Commit Range / Milestones | Cluster Description | Governing Files Added / Modified |
|---|---|---|
| `d138e10` | Workspace housekeeping closeout | `.gitignore`, housekeeping logs |
| `8fdbe2b` -> `31eb227` | Canonical Architecture Constitution established | [`docs/ST-EVA-ARCHITECTURE.md`](ST-EVA-ARCHITECTURE.md) (1084 lines) |
| `271d948` | Observation identity conformance tests formalized | [`tests/test_observation_identity_conformance.py`](../tests/test_observation_identity_conformance.py) |
| `e6f7165` -> `8a0a487` | SEC source document provenance infrastructure (Phase 3A/3B) | Migration [`archive/migrations/0020_sec_provenance.sql`](../archive/migrations/0020_sec_provenance.sql), [`sec_provenance.py`](../sec_provenance.py), tests |
| `3f913a9` -> `5e6287b` | XBRL document-fact provenance & observation linking | [`docs/ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md`](ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md), Migration [`archive/migrations/0021_sec_document_fact_occurrences.sql`](../archive/migrations/0021_sec_document_fact_occurrences.sql), [`sec_xbrl_facts.py`](../sec_xbrl_facts.py), tests |
| `b38b1e0` -> `d067444` | SEC taxonomy authority catalog & resolution (Phase 3C-C1..C4) | Migration [`archive/migrations/0022_authority_taxonomy_namespaces.sql`](../archive/migrations/0022_authority_taxonomy_namespaces.sql), [`archive/acquire_taxonomy_catalog.py`](../archive/acquire_taxonomy_catalog.py), [`archive/parse_edgar_taxonomies_catalog.py`](../archive/parse_edgar_taxonomies_catalog.py), [`archive/record_authority_taxonomy_assertion.py`](../archive/record_authority_taxonomy_assertion.py), [`archive/authority_taxonomy_workflow.py`](../archive/authority_taxonomy_workflow.py), [`archive/authority_evidence_resolver.py`](../archive/authority_evidence_resolver.py), tests |
| `b1e920d` -> `4680839` | C3/C7 bridge research & Shared Authority Archive Target (Amendment 9) | [`docs/ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md`](ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md) (Amendments 7–9 ratified; C4G archived; baseline commit `4680839`) |
| `e9e3843` -> `e2d427f` | Project development roadmap formalized | [`docs/roadmap/README.md`](roadmap/README.md), [`docs/roadmap/ROADMAP.md`](roadmap/ROADMAP.md) |
| `10d298f` | Standalone Amendment 10 v10 draft merged to `master` | [`docs/drafts/AMENDMENT-10-C2A-v10-DRAFT.md`](drafts/AMENDMENT-10-C2A-v10-DRAFT.md) (1533 lines, `DRAFT — NOT IN FORCE`) |

### 1.3 Tracked Files Inventory (348 files total)

Measured directly via `git ls-files`:

| Top-Level Directory / Area | Tracked Count | Description & Key Components |
|---|---:|---|
| Repo Root (`.`) | **61** | 50 production/core `*.py` modules + 11 root configuration/context files (`.gitignore`, `LICENSE`, `README.md`, `SPEC.md`, `WORKSPACE-INVENTORY.md`, 6 `*.context.json`) |
| [`archive/`](../archive/) | **28** | 6 authority acquisition/parser/workflow Python modules + 22 forward-only schema migrations ([`0001`](../archive/migrations/0001_initial.sql) through [`0022`](../archive/migrations/0022_authority_taxonomy_namespaces.sql)) |
| [`docs/`](.) | **24** | Architecture constitution, formal ADRs, roadmap, specifications, audit/reconciliation reports, and [`docs/drafts/AMENDMENT-10-C2A-v10-DRAFT.md`](drafts/AMENDMENT-10-C2A-v10-DRAFT.md) |
| [`experiments/`](../experiments/) | **46** | Frozen legacy experiments from ST-EVA 2.x (`001-context-only/` 15, `002-cold-start/` 31; 0 untracked) |
| [`history/`](../history/) | **35** | Frozen historical evaluation reports and context snapshot fixtures |
| [`reports/`](../reports/) | **35** | Frozen stage design/decision reports referenced by [`registry_seed.py`](../registry_seed.py) |
| [`research/`](../research/) | **2** | [`research/README.md`](../research/README.md) and [`research/RESEARCH-ARCHIVE-MANIFEST.json`](../research/RESEARCH-ARCHIVE-MANIFEST.json) (controls for gitignored `research/experiments/`) |
| [`tests/`](../tests/) | **68** | Automated test suite (expanded from 47 with 21 new provenance/authority tests and 1 fixture) |
| [`web/`](../web/) | **49** | Web application: FastAPI backend (`app.py`, `job_manager.py`, `service_adapter.py`) and React PWA frontend |
| **Total Tracked** | **348** | |

### 1.4 Untracked Files and Working Directory Status

Measured via `git status --short`:
```text
?? data/
```

Detailed inspection of `data/`:
* `data/archives/` (directory): exists, currently **empty**. Designated for per-ticker runtime archives (`data/archives/<TICKER>.sqlite`).
* `data/st-eva.sqlite`: exists on disk (659,456 bytes). Designated by Amendment 9 as the central shared authority archive target.
* `data/st-eva.sqlite-shm`: exists on disk (32,768 bytes).
* `data/st-eva.sqlite-wal`: exists on disk (0 bytes).

> [!IMPORTANT]
> The database files in `data/` are untracked runtime artifacts. Under the read-only audit and safety constraints, their internal contents remain **UNVERIFIED** (no application code or SQLite queries executed). They must never be deleted, overwritten, or reset.

### 1.5 Historical Relocation Accounting (Preserved from Stage 2C)

The Stage 2C research relocation completed on 2026-10-07 remains fully intact:
* **829 research artifacts** relocated from `experiments/` to `research/experiments/` with byte-identical SHA-256 verification (1,147,661,516 bytes both sides).
* `/research/` rule in `.gitignore` remains active.
* [`research/RESEARCH-ARCHIVE-MANIFEST.json`](../research/RESEARCH-ARCHIVE-MANIFEST.json) tracks all 829 relative paths and SHA-256 digests.
* The 46 tracked legacy files in `experiments/` remain frozen and tracked.

---

## 2. Capability Classification & Verification Matrix

To avoid conflating specifications or research prototypes with production software, every subsystem and capability in ST-EVA is classified strictly across the following five mutually exclusive status tiers:

1. **`SPECIFIED`**: Formally documented in an approved ADR, contract, or architecture document; zero production implementation code exists.
2. **`RESEARCH-VALIDATED`**: Empirically proven and verified in standalone research scripts/POCs within `research/experiments/`; code is non-production, throwaway, and not integrated into Core.
3. **`IMPLEMENTED`**: Code and/or schema migrations exist in tracked production modules (`*.py` or `archive/migrations/`).
4. **`TESTED`**: Exercised and verified by automated regression tests in `tests/`.
5. **`PRODUCTION-INTEGRATED`**: Fully wired into runtime entry points, CLI runner ([`st_eva_runner.py`](../st_eva_runner.py)), archive subsystem, or Web/API routes.

Where evidence cannot be verified from disk without executing code, the state is recorded as **`UNVERIFIED`** or **`NEEDS REVALIDATION`**.

### 2.1 Subsystem Status Matrix

| Subsystem / Capability | Primary Source Files / References | Status Tier | Verifiable Evidence & Boundaries |
|---|---|---|---|
| **Reverse Valuation Engine Core** | [`st_eva_runner.py`](../st_eva_runner.py), [`data_contract.py`](../data_contract.py) | **PRODUCTION-INTEGRATED** | Deterministic arithmetic, implied forward EPS, EPS CAGR, consensus gap calculation. Consumes provider-fed `historical_pe_band` if present. |
| **Core Observation & Evidence Model** | [`data_contract.py`](../data_contract.py), [`evidence_model.py`](../evidence_model.py) | **PRODUCTION-INTEGRATED** | Frozen `Observation` dataclass, immutable hashing, `EVIDENCE_STATES`, `ObservationIdentity`. Tested in `test_observation_identity_conformance.py`. |
| **Core Concept Registry & Seed** | [`core_registry.py`](../core_registry.py), [`registry_seed.py`](../registry_seed.py), [`registry_identity.py`](../registry_identity.py) | **PRODUCTION-INTEGRATED** | 35 design reports mapped; pure hash registry identities; concept adoption & mapping rules. |
| **Valuation Admission Boundary** | [`evidence_valuation_boundary.py`](../evidence_valuation_boundary.py) | **PRODUCTION-INTEGRATED** | Admission Rules 1–10. **Critical constraint:** evaluator crossing scope is strictly `V1_CROSSING_METRICS = (METRIC_REVENUE,)`. Metric admission evaluates only `revenue`. Price bypasses admission. P/E metrics are not admitted in V1. |
| **Archive & Replay Subsystem** | [`sqlite_archive.py`](../sqlite_archive.py), [`archive.py`](../archive.py), [`archive/migrations/`](../archive/migrations/) | **PRODUCTION-INTEGRATED** | 22 forward-only migrations. Append-only triggers enforced. Replay dynamically re-evaluates admissions without reading stored rows. |
| **Web Service & React PWA** | [`web/app.py`](../web/app.py), [`web/job_manager.py`](../web/job_manager.py), [`web/frontend/`](../web/frontend/) | **PRODUCTION-INTEGRATED** | FastAPI REST endpoints, background task jobs, React PWA dashboard. Operates over reverse-valuation outputs; zero Historical P/E surface. |
| **SEC Filing Document Provenance (Phase 3A/3B)** | Migration [`archive/migrations/0020_sec_provenance.sql`](../archive/migrations/0020_sec_provenance.sql), [`sec_provenance.py`](../sec_provenance.py) | **TESTED** | Tracks filing documents, SGML ordinals, document raw bytes, and filing metadata. Exercised by `tests/test_sec_*`. |
| **XBRL Document-Fact Provenance** | Migration [`archive/migrations/0021_sec_document_fact_occurrences.sql`](../archive/migrations/0021_sec_document_fact_occurrences.sql), [`sec_xbrl_facts.py`](../sec_xbrl_facts.py) | **TESTED** | Resolves document-level fact occurrences, inline XBRL vs XML instances, and observation-to-fact linking. |
| **SEC Taxonomy Authority Acquisition & Parsers (Phase 3C-C1..C4)** | Migration [`archive/migrations/0022_authority_taxonomy_namespaces.sql`](../archive/migrations/0022_authority_taxonomy_namespaces.sql), [`archive/authority_taxonomy_workflow.py`](../archive/authority_taxonomy_workflow.py), [`archive/parse_edgar_taxonomies_catalog.py`](../archive/parse_edgar_taxonomies_catalog.py) | **TESTED** (with known trigger failure) | C1 acquisition, C2A parsing, C2B persistence, C3 workflow, C4 evidence gates. **Known defect:** baseline C2A parser aborts on official catalog `doc_eb3d9eb2...` at record #127. Gated by Amendment 9; claims C3/C7/C9 unproven; C4G archived. |
| **Historical P/E Methodology & Architecture** | [`docs/ADR-HISTORICAL-PE-METHODOLOGY.md`](ADR-HISTORICAL-PE-METHODOLOGY.md) | **SPECIFIED** | APPROVED / FROZEN (with Amendment 1 Decisions 10–14). 4 open items in §4. |
| **Historical P/E Contract Specification** | [`docs/methodology/CONTRACT-HISTORICAL-PE.md`](methodology/CONTRACT-HISTORICAL-PE.md) | **SPECIFIED** | Explicitly marked `Status: DESIGN ARTIFACT — not implementation, not production`. Invariants F-1..F-15, sequence E.0..E.8, 9 open decisions §K. |
| **Historical P/E Empirical Validation** | `research/experiments/aapl-historical-pe-poc/` | **RESEARCH-VALIDATED** | AAPL POC (31/31 TTM), Q4 evidence study (5/5 quarters recovered from 8-K EX-99.1), MSFT validation (24/27 TTM). All code is throwaway research. |
| **Historical P/E Production Engine** | None | **NOT STARTED** | Zero production Python modules exist for Contract-defined Historical P/E calculation; no `HistoricalPeObservation` type. |
| **Historical P/E Archive Integration** | None | **NOT STARTED** | Evaluator boundary crossing scope does not include P/E metrics (`V1_CROSSING_METRICS`). Data-layer has 4 Class-1 gaps. |
| **Historical P/E Conformance Test Suite** | None | **NOT STARTED** | Contract §I.3 specified 7-item conformance suite (replay, independent recomputation, negative path, lookahead, window integrity, provenance completeness, class integrity) does not exist in `tests/`. |
| **Historical P/E Web / CLI Surface** | None | **NOT STARTED** | Zero routes, endpoints, or UI components exist in `web/` or CLI for Historical P/E. |
| **ST-EVA Development Roadmap** | [`docs/roadmap/ROADMAP.md`](roadmap/ROADMAP.md) | **SPECIFIED** | Workstreams RM-0, GOV-1, HPE-1..5, PLAT-1 defined. Explicitly states it confers no implementation authorization. |

---

## 3. Dedicated Amendment 10 Governance Checkpoint

Amendment 10 governs C2A catalog parsing, record classification, identity collapse, and evidence preservation for the SEC taxonomy authority layer. To prevent premature execution or governance confusion, its five distinct operational and legal statuses are recorded separately:

```text
+---------------------------------------------------------------------------------------------------------+
|                                    AMENDMENT 10 FIVEFOLD STATUS REGISTER                                |
+------------------------------------+--------------------------------------------------------------------+
| 1. Branch Merge Status             | MERGED into master (commit 10d298f, docs/drafts/...)              |
| 2. Semantic Review Status          | ALL CLEAR — READY FOR RATIFICATION CONSIDERATION (0 defects)      |
| 3. Formal Ratification Status      | DRAFT — NOT IN FORCE (pending human ratification decision)        |
| 4. Formal ADR Update Status        | ADR-XBRL-PROVENANCE UNCHANGED (2597 lines, hash 684d985...)       |
| 5. Implementation Authorization    | ZERO AUTHORIZATION (code, tests, migrations, and DB frozen)       |
+------------------------------------+--------------------------------------------------------------------+
```

### 3.1 Fivefold Status Details

1. **Branch Merge Status: MERGED into `master`**
   Merged into `master` at commit `10d298ffbc315c20070b27472b407ac3ed2337aa` as a standalone draft file:
   [`docs/drafts/AMENDMENT-10-C2A-v10-DRAFT.md`](drafts/AMENDMENT-10-C2A-v10-DRAFT.md) (1533 lines, blob SHA `b841fb487b26eba14888e901c157ac2a0cfac42b`).
   The file is located in `docs/drafts/`, isolated from formal ADRs.
2. **Semantic Review Status: ALL CLEAR — READY FOR RATIFICATION CONSIDERATION**
   Independent full-document semantic review across §0–§14 confirmed:
   - Exactly 84 decision clauses (44 bare headings + 40 sub-clauses across 10 compound decisions) and 25 output table rows.
   - Internal numbering, cross-references, reason-code mappings, and disposition semantics are completely consistent.
   - Targeted counterexample verification on Decision 10.30(d) passed across all four boundary conditions (A, B, C, D).
   - Zero blocking semantic defects or internal contradictions remain.
3. **Formal Ratification Status: DRAFT — NOT IN FORCE**
   The draft states in §0 that it is `DRAFT — NOT IN FORCE`. Merging the draft to `master` does not constitute ratification. Formal adoption requires an explicit human governance decision (Roadmap Gate `GOV-1b`).
4. **Formal ADR Update Status: FORMAL ADR UNCHANGED**
   The governing ADR [`docs/ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md`](ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md) remains exactly 2,597 lines (blob SHA `684d985078237a5ac9359127a3a42c5f5542022b`), byte-identical to commit `4680839`. It ends at Amendment 9. Amendment 10 has **not** been appended to the formal ADR.
5. **Implementation Authorization Status: ZERO AUTHORIZATION CONFERRED**
   The draft confers no authority to modify [`archive/parse_edgar_taxonomies_catalog.py`](../archive/parse_edgar_taxonomies_catalog.py), [`archive/record_authority_taxonomy_assertion.py`](../archive/record_authority_taxonomy_assertion.py), tests, database schemas, or migrations, nor does it authorize executing the C1–C2B workflow against `data/st-eva.sqlite`. All code and database work remains strictly gated behind Gate `GOV-1d`.

### 3.2 Stable Taxonomy of Disclosed Limitations

The final semantic review confirmed that the draft's disclosed normative limitations are honest boundaries of the official SEC catalog, not defects. They remain classified under their original stable identifiers:
* **Class A (Upstream Format Constraints):** Unversioned namespace collisions (Decision 10.21), absence of historical effective dates (Decision 10.23), and multi-prefixed authority namespaces (Decision 10.25).
* **Class B (Execution & Collision Defenses):** Catalog-internal collision defenses CC-1 / CC-2, distinct from archive pre-existing assertions G1 / G2 (Decision 10.29).
* **Class C (Operational Scope):** Scope restricted to C2A authority parsing; no cross-archive reading, no B2 candidate linking, and no C4G reactivation permitted.

---

## 4. Historical P/E Productization Status & Data-Layer Gaps

### 4.1 Methodology vs. Software Reality

While ST-EVA possesses extensive research evidence and frozen methodology specifications for Historical P/E, **no production Historical P/E pipeline currently exists in the codebase**:

```text
               SPECIFICATION                 RESEARCH & PROOF                  PRODUCTION CODE
        ┌─────────────────────────┐     ┌─────────────────────────┐     ┌─────────────────────────┐
        │ ADR Methodology         │     │ AAPL POC (31/31 TTM)    │     │ Production Engine:      │
        │ APPROVED / FROZEN       │ --> │ Q4 Study (8-K EX-99.1)  │ --> │ NOT STARTED             │
        │                         │     │ MSFT Validation (24/27) │     │                         │
        │ Contract §A-§L          │     │                         │     │ Core Integration:       │
        │ DESIGN ARTIFACT         │     │ All in /research/       │     │ NOT STARTED             │
        └─────────────────────────┘     └─────────────────────────┘     └─────────────────────────┘
```

### 4.2 Legacy `historical_pe_band` vs. Contract-Defined Pipeline

The codebase contains a legacy mechanism that must never be confused with the Contract-defined Historical P/E pipeline:
* **Legacy Provider-Fed Band ([`data_contract.py:1805`](../data_contract.py#L1805), [`st_eva_runner.py:1378`](../st_eva_runner.py#L1378)):**
  `ValuationInputs.historical_pe_band` is an optional dictionary supplied directly by an external provider (such as Yahoo Finance) containing pre-aggregated percentiles (e.g. median). `STEVAEEngine.analyze()` reads this band if present. It performs zero quarter-level reconstruction, enforces no point-in-time usable dates, and has no provenance.
* **Contract-Defined Historical P/E Pipeline ([`docs/methodology/CONTRACT-HISTORICAL-PE.md`](methodology/CONTRACT-HISTORICAL-PE.md)):**
  A deterministic, point-in-time engine that reconstructs quarter-level Diluted EPS from SEC filed statements and Form 8-K Item 2.02 furnished exhibits, pairs them with historical market closing prices under the 16:00 ET cutoff convention, enforces Invariants F-1..F-15, and emits conforming observations with complete lineage. **This pipeline is completely unwritten.**

### 4.3 Data-Layer Audit Findings & Genuine Schema Gaps

Per [`docs/ST-EVA-DATA-LAYER-AUDIT.md`](ST-EVA-DATA-LAYER-AUDIT.md) and [`docs/ST-EVA-DATA-ADMISSION-RECONCILIATION.md`](ST-EVA-DATA-ADMISSION-RECONCILIATION.md), the current 22-migration schema cannot store a conforming Historical P/E observation due to **four Class-1 genuine schema gaps**:

1. **Evidence Class:** No machine-observable column or attribute distinguishes `filed` (Section 13(a)) from `furnished` (Form 8-K Item 2.02 EX-99.1) evidence.
2. **Audit Status & Legal-Status Note:** No 3-valued `audit_status` field (`AUDITED`, `UNAUDITED`, `NOT_APPLICABLE`) and no required accompanying `legal_status_note` exist in `observations` or `source_facts`. Inferring audit status from form type alone is prohibited by ADR Decision 11.
3. **Fiscal Calendar Axis:** The data layer lacks an issuer fiscal calendar table or resolved `fiscal_year_end_month` mapping on the observation time axis.
4. **Acceptance-Instant Source Provenance:** The archive cannot distinguish whether an acceptance timestamp originated from official EDGAR SGML header bytes or an untrusted external vendor feed.

These gaps represent correctness blockers. Until they are designed and resolved via approved governance, no conforming Historical P/E observation can be persisted.

---

## 5. Open Decisions & Unresolved Issues Register

The following decisions are formally registered as **OPEN** by their governing documents. None has been decided, and none may be decided without following the required governance process.

### 5.1 Historical P/E Open Decisions

| Source | Identifier | Subject | Description & Status |
|---|---|---|---|
| ADR §4 | **ADR-4.1** | Reference Sufficiency | Minimum observation count threshold (whether >= 20 suffices, or time span and fiscal quarter coverage are also required). OPEN. |
| ADR §4 | **ADR-4.2** | Corporate Action Schema | Source authority, ex-date timestamp precision, and split-adjustment evidence schema. OPEN. |
| ADR §4 | **ADR-4.3** | Sampling Frequency | Frequency strategy (daily, weekly, monthly, event-driven) and impact on percentile stability. OPEN. |
| ADR §4 | **ADR-4.4** | FPI Fallback Policy | Annual P/E fallback rules for Foreign Private Issuers reporting semi-annually. OPEN. |
| Contract §K | **K.1** | Reference Sufficiency Threshold | Triggers for `REASON_INSUFFICIENT_OBSERVATIONS` and `REASON_INSUFFICIENT_TIME_SPAN`. OPEN. |
| Contract §K | **K.2** | 20 / 24 Observation Scope | Whether the 20/24 threshold governs TTM sets, annual sets, or both. OPEN. |
| Contract §K | **K.3** | Sampling Strategy | Monotone, versioned sampling strategy naming and selection. OPEN. |
| Contract §K | **K.4** | Corporate Action Evidence | Storage structure absorbing per-fiscal-year calendar resolution. OPEN. |
| Contract §K | **K.5** | FPI Fallback Policy | Restates ADR-4.4. OPEN. |
| Contract §K | **K.6** | Furnished Evidence Scope | Weighting and eligibility of furnished evidence in non-historical-P/E valuation contexts. OPEN. |
| Contract §K | **K.7** | Fact-Unavailable Observability | Machine-observable representation of `XBRL_FACT_UNAVAILABLE` (attribute vs reason code). OPEN. |
| Contract §K | **K.8** | Precedence in Instance Ties | Documented precedence rules among competing admissible instances. OPEN. |
| Contract §K | **K.9** | Cross-Currency Handling | Pairing cross-currency EPS and market price when reporting currency is non-USD. OPEN. |

### 5.2 SEC Taxonomy Authority Unproven Claims

From [`docs/ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md`](ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md) (Amendments 7–9):
* **Claim C3:** `NOT PROVEN` — No cross-source contract connecting API token to catalog `<Prefix>`.
* **Claim C7:** `NOT PROVEN` — Equivalence between observation and occurrence representations unproven.
* **Claim C9:** `UNAVAILABLE / UNPROVEN` — Historical filing-date validity cannot be proven by current catalog snapshot.
* **Claim C10:** `UNAVAILABLE` — Production refuses unproven taxonomy equivalence.

### 5.3 Workspace & Inventory Unresolved Items

1. **Managed Worktrees Activity Status (`.kilo/worktrees/`):**
   Contains two managed worktrees: `eastern-anglerfish` and `pepper-chess` (917 files, 110.61 MB, excluded via `.git/info/exclude`). Activity status remains **UNVERIFIED / NEEDS REVALIDATION**. No deletion or modification permitted.
2. **MSFT Raw Bulk Retention Policy:**
   `research/experiments/aapl-historical-pe-poc/contract/msft_validation/raw/docs/` holds 1011.67 MB of frozen SEC primary filings. Whether to retain this in full permanently or treat EDGAR as re-fetchable remains an unresolved design trade-off. Currently resolved in favor of **retention**.
3. **Runtime Database Files in `data/`:**
   `data/st-eva.sqlite` (659 KB) exists untracked. Its internal tables and contents remain **UNVERIFIED** under the read-only constraint.

---

## 6. Development Roadmap Alignment & Milestone Status

Aligned with the authoritative project roadmap [`docs/roadmap/ROADMAP.md`](roadmap/ROADMAP.md) (established at `e2d427f`):

| Workstream ID | Workstream Title | Current Status | Next Action / Gate |
|---|---|---|---|
| **RM-0** | Baseline & Status Reconciliation | **CHECKPOINT RECORDED; residual items remain UNVERIFIED** | Status snapshot reconciled against baseline `10d298f`; explicitly listed worktree and research-retention uncertainties remain open and must not be treated as resolved. |
| **GOV-1** | Amendment 10 Governance Track | **IN PROGRESS — RATIFICATION NOT DECIDED** | Whole-draft review report recommends readiness for consideration. Before GOV-1b, reconcile the report's disclosed-gap labels against their canonical source and clarify Decision 10.54's authorization wording against the planned separate implementation gate. GOV-1c and GOV-1d remain unexecuted. |
| **HPE-1** | Historical P/E Scope & Design Prerequisites | **NOT STARTED** | Define bounded first-release scope; map blocking vs deferred open decisions; obtain required ADR governance approvals. |
| **HPE-2** | Historical P/E Data-Model Design | **NOT STARTED** | Blocked on HPE-1. Design conforming representation resolving the 4 Class-1 data-layer gaps without altering existing boundaries. |
| **HPE-3** | Historical P/E Production Pipeline | **NOT STARTED** | Blocked on HPE-1 and HPE-2. Implement Contract-defined pipeline in tracked modules; integrate with core archive and admission. |
| **HPE-4** | Historical P/E Conformance & Regression | **NOT STARTED** | Blocked on HPE-3. Implement Contract §I.3 7-item conformance regression suite in `tests/`. |
| **HPE-5** | CLI and Web/PWA Integration | **NOT STARTED** | Blocked on HPE-3 and HPE-4. Expose validated outputs to CLI and React frontend with clear provenance. |
| **PLAT-1** | Long-Term Platform Improvements | **DEFERRED / CASE-DEPENDENT** | Undertake only when justified by a concrete correctness blocker or named consumer. |

---

## 7. Immediate Next Concrete Actions

Following the roadmap sequencing protocol, the next concrete steps are:

1. **Checkpoint Verification & Freezing (RM-0):**
   Review this updated [`docs/ST-EVA-PROJECT-STATUS.md`](ST-EVA-PROJECT-STATUS.md) against git status and git diff to ensure complete fidelity, zero untracked file destruction, and clean working tree.
2. **Amendment 10 Ratification Consideration (GOV-1b):**
   Submit the review findings to project leadership for formal ratification consideration. Do NOT append to the formal ADR or begin implementation until explicit human approval is granted.
3. **Historical P/E First-Release Scoping (HPE-1):**
   Before any schema design or code drafting, establish a bounded first-release scope (e.g. US-GAAP filers with standard calendar and filed+furnished evidence, deferring FPI annual fallback and corporate actions) and register resolutions for the blocking decisions via the required governance path.

---

## 8. Checkpoint History & Revision Register

* **2026-10-07 (`5e655a7`):** First recorded status checkpoint from direct workspace inspection.
* **2026-10-07 (`5df7f34`):** Updated with workspace inventory and architecture boundaries.
* **2026-10-07 (`694ec96`):** Promoted Historical P/E Contract to [`docs/methodology/CONTRACT-HISTORICAL-PE.md`](methodology/CONTRACT-HISTORICAL-PE.md).
* **2026-10-07 (`7464422`):** Project structure contract formalized ([`docs/ST-EVA-PROJECT-STRUCTURE.md`](ST-EVA-PROJECT-STRUCTURE.md)).
* **2026-10-07 (`499bd6c`):** Stage 2C research relocation completed (829 files relocated to `research/experiments/`, hash verified PASS).
* **2026-10-07 (`0becbdc`):** Data admission reconciliation recorded; baseline measured at 311 tracked files.
* **2026-10-09 (`10d298f`):** Updated to reflect baseline `10d298f`:
  - Measured 348 tracked files (expanded by architecture constitution, SEC provenance, XBRL fact linking, taxonomy authority C1–C4, and roadmap).
  - Formalized 5-tier capability matrix (`SPECIFIED`, `RESEARCH-VALIDATED`, `IMPLEMENTED`, `TESTED`, `PRODUCTION-INTEGRATED`).
  - Recorded Amendment 10's fivefold status: merged to `master` as draft, reviewed all-clear, `DRAFT — NOT IN FORCE`, formal ADR unchanged, implementation unauthorized.
  - Reconciled Historical P/E status: methodology specified, research validated, production unstarted, data-layer gapped (4 Class-1 gaps), legacy band separated.
  - Aligned status with [`docs/roadmap/ROADMAP.md`](roadmap/ROADMAP.md) workstreams RM-0, GOV-1, HPE-1..5, PLAT-1.
  - Zero modifications to code, tests, schemas, migrations, or database files.
