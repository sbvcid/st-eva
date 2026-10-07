# ST-EVA Project Status Checkpoint

**Purpose:** a factual checkpoint of the repository as it stands, so that a later
session can establish where things are without re-deriving it.
**Basis:** direct inspection of `C:\git\st-eva` only. Nothing here is researched,
inferred, or decided.
**Date:** 2026-10-07

This document records state. It introduces no new architectural decision, and it
changes no decision already recorded in the ADR, the Contract, or the Core.

---

## 1. Git baseline

Measured at `0becbdc`, the commit that added
`docs/ST-EVA-DATA-ADMISSION-RECONCILIATION.md`. This section is the **housekeeping
checkpoint**; §4 and later retain the pre-relocation measurements, superseded
in place where they were.

| Item | Value |
|---|---|
| Commit | `0becbdc` |
| Short | `0becbdc docs: reconcile ST-EVA data admission rules` |
| Branch | `master` |
| Remote | `origin` → `https://github.com/sbvcid/st-eva.git` |
| Sync | `## master...origin/master` — **in sync, no ahead/behind** |
| Preceding commits | `499bd6c` finalize research workspace archive · `7464422` define project structure · `5df7f34` workspace/architecture status · `5e655a7` formalize ADR + Contract · `b124123` remove experiment 003 |

Housekeeping status at this checkpoint:

| Item | Status |
|---|---|
| Workspace Stabilization Stage 2C | **COMPLETE** |
| Research relocation | **COMPLETE** — 829 artifacts, SHA-256 verified |
| `/research/` gitignore rule | **ACTIVE** |
| `experiments/` freeze at 46 tracked | **COMPLETE** — 46 tracked, 0 untracked |
| Housekeeping | **COMPLETE** |
| Reconciliation document | **committed** — `0becbdc` |
| Product development | **NOT STARTED** — see §3, unchanged by this checkpoint |

| Count | Value |
|---|---:|
| Tracked files | **311** |
| Untracked files (`-uall`) | **0** |
| Staged | **0** |
| Modified (tracked) | **0** |
| Deleted | **0** |

Untracked breakdown: **none.** Stage 2C completed the workspace move: the last 829
untracked research files were relocated to `research/experiments/` with
per-file SHA-256 verification, and `/research/` was added to `.gitignore`.

| Location | Files | Tracked | Git state |
|---|---:|---:|---|
| `research/experiments/` | 829 | 0 | ignored (`/research/`) |
| `research/RESEARCH-ARCHIVE-MANIFEST.json` | 1 | 1 | tracked |
| `research/README.md` | 1 | 1 | tracked |
| `experiments/` | 59 | 46 | 46 tracked + 13 gitignored `.pyc`, **0 untracked** |

Tracked composition: 48 root production `*.py` modules · `docs/` 19 ·
`tests/` 47 · `reports/` 35 · `history/` 35 · `archive/` 19 ·
`web/` 49 · repo root docs 3 · **`experiments/` 46 legacy** · `research/` 2.

### 1.0 `docs/ST-EVA-DATA-LAYER-AUDIT.md` and the reconciliation that followed

The audit found that the archive could not represent a conforming Historical P/E
observation, because `evidence_class`, `legal_status_note`, `audit_status`,
`accounting_basis` and `fiscal_year_end_month` had no home. Those five fields are
now judged individually in `docs/ST-EVA-DATA-ADMISSION-RECONCILIATION.md`
(`0becbdc`): one already represented, one derivable in an existing container,
three genuinely missing. That document is analysis only — it changes no schema,
no code, and no frozen decision.

### 1.1 `experiments/` accounting — corrected, then superseded

> **Superseded by Stage 2C (2026-10-07).** The table below describes the state
> before the relocation. `experiments/` now holds 46 tracked + 13 gitignored =
> 59 files, with **0 untracked**. The 829 untracked research files described here
> are at `research/experiments/`, verified hash-identical.

An earlier version of this checkpoint reported the experiments tree as entirely
untracked. That was wrong. Measured by direct query at the time:

| Classification | Files | Command |
|---|---:|---|
| Tracked in git | **47** | `git ls-files experiments/` |
| Untracked | **829** | `git status --porcelain=v1 -uall -- experiments` |
| Gitignored | **13** | `experiments/002-cold-start/__pycache__/*.pyc` |
| **Total on disk** | **888** | `Get-ChildItem experiments -Recurse -File` (889 before the Contract moved out) |

47 + 829 = 876; the 13-file remainder is gitignored cache. The original error was
deriving the tracked count by subtraction instead of running `git ls-files`.

The 47 tracked files are **legacy research from the ST-EVA 2.x era**, not from
this Historical P/E programme:

| Tracked subtree | Files | Introduced by |
|---|---:|---|
| `experiments/001-context-only/` (+ `input/`, `outputs/`) | 15 | `95373eb` — *2.4.3 Fix what the consumption experiment found* |
| `experiments/002-cold-start/` (+ `contexts/`) | 31 | `7d86a39` — *2.6.1b: make an unknown metric and an absent figure different answers* |
| `experiments/aapl-historical-pe-poc/contract/CONTRACT-HISTORICAL-PE.md` | 1 | `5e655a7` — since promoted to `docs/methodology/` |

**Decision (2026-10-07):** these legacy files stay tracked. They are not
untracked, not moved, not archived, and not in cleanup scope. Workspace cleanup
covers untracked research only — in practice, `experiments/aapl-historical-pe-poc/`
minus the already-promoted Contract.

---

## 2. Completed

### Core — complete and tracked

- ~48 production modules at repo root, including `st_eva_runner.py`,
  `data_contract.py`, `evidence_model.py`, `evidence_query.py`,
  `evidence_valuation_boundary.py`, `sec_provider.py`, `sec_ingest.py`,
  `core_registry.py`, `registry_seed.py`, `operation_registry.py`,
  `sqlite_archive.py`, `archive.py`, `investment_context.py`,
  `issuer_identity.py`, `knowledge_axis.py`, `llm_interpreter.py`, `web/`
- 19 migrations under `archive/migrations/` (2.4 → 3.32), forward-only,
  checksum-verified
- 47 tracked test files under `tests/`
- 35 stage reports under `reports/` (`2_7_` … `2_38_`), all tracked
- 35 evidence records under `history/`, all tracked
- Specification set under `docs/`: 2.3-A Data Contract, 2.3-B SEC Validation,
  2.3-C Investment Context, 2.3 Plan, 2.4 Point-in-Time Archive/Replay,
  2.4.3 Completion, 2.5 Core Evidence Spec, 2.5 Core Registry, 2.5 Database
  Design, 2.5 Ingestion, 2.5.1 Hardening, 2.6 Cross-Company, `USAGE.md`

### Web / PWA — built, tracked, build artifacts present but untracked

- `web/` — `app.py`, `job_manager.py`, `schemas.py`, `service_adapter.py`,
  `api/`, `frontend/` (Vite + React + TypeScript, i18n, oxlint, vitest)
- 49 tracked files. `frontend/node_modules` (9306 files, 165.17 MB) and
  `frontend/dist` (11 files, 0.3 MB) are gitignored build output.
- Per commit `828deb1`: i18n, registry baseline seed, replay evidence symmetry

### Historical P/E ADR — APPROVED / FROZEN, tracked

`docs/ADR-HISTORICAL-PE-METHODOLOGY.md`, 323 lines. Status APPROVED / FROZEN
(Methodology Specification). 14 frozen decisions. §4 carries four OPEN items
that the ADR explicitly declines to settle.

### Amendment 1 — ratified into the ADR, tracked

Same file. Introduces Decisions 10–14: `filed` / `furnished` evidence-class
separation; unaudited not a refusal reason; `acceptance_datetime` extended to
furnished sources with the Eastern-Time implementation lesson; the mandatory
distinction between `XBRL fact unavailable` and `primary evidence unavailable`;
and TTM component source mixing. §6.1 records the empirical basis. §5.6 and §5.7
place engine implementation and parser implementation out of scope.

### AAPL Historical P/E POC — complete, in `experiments/` (untracked)

`experiments/aapl-historical-pe-poc/` root, `raw/`, `out/` — 7 scripts, 48 raw
files (1.24 MB), 5 output files (0.2 MB). Result: 31/31 TTM available with
furnished evidence admitted; 12/31 on the prior XBRL-only path; negative path
reproduces the prior result. `out/determinism.txt` records two-run hash equality.

### Q4 evidence study — complete, in `experiments/` (untracked)

`experiments/aapl-historical-pe-poc/q4_study/` — 167 files, 77.97 MB (155 raw /
77.85 MB, 6 output / 0.06 MB, 6 scripts). Established that AAPL stopped tagging
quarter-length `EarningsPerShareDiluted` XBRL facts from FY2021 while the same
figure remained directly stated in Form 8-K Item 2.02 EX-99.1 exhibits:
**5/5 quarters recovered**, all accepted 16:30 ET, all landing on the next
trading day. Source priority measured across four categories. This study is the
stated empirical basis for Amendment 1 §6.1.

### Historical P/E Contract — complete, tracked, **promoted**

**`docs/methodology/CONTRACT-HISTORICAL-PE.md`**, 1178 lines / 51.6 KB. Input
schema (§B), output schema (§C), state definitions (§D), normative resolver
sequence E.0–E.8, invariants **F-1 … F-15**, failure semantics (§G), provenance
requirements (§H), replay requirements (§I.1–§I.4), genericization limits (§J),
**nine OPEN decisions §K.1–§K.9**, consistency review §L.1–§L.9.

Tracked at `5e655a7` while still under `experiments/`; promoted out of the
research tree to `docs/methodology/` on 2026-10-07 via `git mv`, so it now sits
beside the ADR and no governed document lives under `experiments/`. Exactly one
line of content changed: line 7's self-referential `**File:**` header, corrected
to the new path. **No methodology content was altered.**

### MSFT contract validation — complete, in `experiments/` (untracked)

`experiments/aapl-historical-pe-poc/contract/msft_validation/` (+ `phase1_fiscal_identity/`)
— 593 files, 1014.69 MB, of which 1011.67 MB is frozen SEC primary-source
evidence. Result: contract expresses MSFT without modification.
27 evaluation dates · **24/27 TTM AVAILABLE** with furnished evidence, **0/24**
with it disabled · all of F-1…F-15 PASS · 7/7 failure paths PASS · independent
second computation path with zero mismatch · two-run replay determinism.
Four findings recorded:

- **C.1** — AAPL's exhibit layout is not a universal template
- **J.1** — the 10-K-list fiscal-identity bug misassigns 3 of 21 MSFT quarters,
  a systematic full-year shift, worse than AAPL's 455-day window
- **J.2** — MSFT has no before-cutoff acceptance; that branch is N/A, not PASS
- **J.3** — evidence class is determined by the Item 2.02 item code, not by form

The validation states its own weak points rather than burying them: F-6 held
vacuously (no split in the window), F-10 not exercised (no `CURRENT_PE` emitted),
and the non-GAAP failure path is weak because MSFT presents no non-GAAP EPS line.

### C.1 genericization note — complete, tracked

`CONTRACT-HISTORICAL-PE.md` **§B.2.1 "Genericization Note: Furnished Evidence
Column Semantics"** (lines 178–221), added 2026-10-07 from Finding C.1. States
that `period_start` / `duration_days` may be null for `STATEMENT_COLUMN_LABEL`
evidence; prohibits requiring a fixed column count, a cumulative column, a
narrative corroboration sentence, or any issuer-specific layout; establishes
column-header semantics as the eligibility signal; and records that AAPL's five
exhibits and MSFT's twenty-three are **examples, not parser contract**. Adds no
reason code and changes no schema semantics.

---

## 3. Not started

| Item | State | Basis |
|---|---|---|
| Historical P/E production Engine | **Not started** | ADR §5.6 places engine implementation out of scope of the ADR; the Contract specifies interfaces, semantics, ordering, invariants and conformance tests but no algorithm beyond the two load-bearing derivations in §E.1 and §E.3. No production `*.py` module references any P/E metric id. |
| Integration (Engine ↔ Core / archive) | **Not started** | Contract §L.8–L.9 state the boundary with Core is respected and that no file in `st_eva_runner.py`, `data_contract.py`, `evidence_valuation_boundary.py`, the SEC provider, the web app, the ADR or the POC outputs is modified. `docs/ST-EVA-DATA-LAYER-AUDIT.md` §C–D records the data-layer gaps that would block a conforming observation. |
| Production regression suite for P/E | **Not started** | Contract §I.3 specifies a seven-item conformance suite (replay, independent recomputation, negative path, lookahead, window integrity, provenance completeness, class integrity) as an acceptance criterion. No such suite exists in `tests/`. |
| Web surface for P/E | **Not started** | `web/` has no P/E route, metric or display. |

What exists instead, entirely inside `experiments/`, is validation-only
throwaway code: 7 root POC scripts, 6 q4_study scripts, 4 amendment1_verify
scripts, 7 msft_validation scripts, 8 phase1_fiscal_identity scripts. None is
production; none is importable from Core.

---

## 4. OPEN decisions

Recorded as OPEN by the documents themselves. None is decided here, and none may
be decided without the decision record the ADR or Contract specifies.

### From the ADR §4

| # | Item | Blocks |
|---|---|---|
| ADR-4.1 | **Reference Sufficiency** — whether count ≥ 20 suffices, or time span and fiscal-quarter coverage must also be met, and at what values. No threshold pre-set. | Whether a 31-observation AAPL set forms a usable reference set |
| ADR-4.2 | **Corporate Action Evidence Schema** — source authority, ex-date timestamp precision, storage structure | Decision 8 (point-in-time split adjustment); Contract F-6 |
| ADR-4.3 | **Sampling Frequency** — daily / weekly / monthly / event-driven, and effect on percentile stability | Historical band construction |
| ADR-4.4 | **Annual P/E fallback policy for FPIs** — may a semi-annual/annual-only filer be declared annual-driven, and how does it interact with the TTM/Annual separation | FPI support |

### From the Contract §K

| # | Item |
|---|---|
| K.1 | Reference Sufficiency threshold — restates ADR-4.1; `REASON_INSUFFICIENT_OBSERVATIONS` and `REASON_INSUFFICIENT_TIME_SPAN` exist in the closed enumeration but their triggers are undetermined |
| K.2 | The 20 / 24 observation requirement — unchanged and untouched; whether it governs a TTM-based set, an annual-based one, or both |
| K.3 | Sampling Frequency — restates ADR-4.3; §E.4 requires the strategy be named, versioned and monotone but does not choose one |
| K.4 | Corporate Action evidence schema — restates ADR-4.2; also absorbs per-fiscal-year `fiscal_year_end_month` resolution |
| K.5 | FPI fallback policy — restates ADR-4.4 |
| K.6 | Weighting of furnished evidence in **other** valuation contexts — whether it may appear in a standalone `trailing_eps` observation, in a band, or in any non-historical-P/E crossing |
| K.7 | `XBRL_FACT_UNAVAILABLE` observability — observation attribute or reason code? Reason-code enumeration stays closed; today it is diagnostic only |
| K.8 | Ties among competing admissible instances — §D.3 refuses rather than tie-breaks; whether a documented precedence rule is warranted |
| K.9 | Non-USD currency handling — whether cross-currency EPS and price may ever be paired, and under what declaration |

### From Amendment 1 §6.1

- Machine-observable status of `XBRL fact unavailable` (same subject as K.7)
- Weighting of furnished evidence in reverse-valuation reference calculation, and
  its interaction with `ANNUAL_GAAP_DILUTED_PE` (overlaps K.6)
- Unit handling when the EPS reporting currency is not USD (overlaps K.9)

**Ten distinct OPEN items** across the three documents, with four duplicated
between ADR and Contract by design.

**Unchanged by Amendment 1:** the reason-code enumeration is closed and was not
extended; the 20 / 24 observation requirement is unmodified.

---

## 5. Current workspace state

### Stage 2C complete — research relocated in-repo

| Step | Status |
|---|---|
| Governing documents tracked | **Done** — `5e655a7` |
| `WORKSPACE-INVENTORY.md` tracked | **Done** — `5df7f34` |
| Contract promoted to `docs/methodology/` | **Done** — `694ec96` |
| Tracked/untracked accounting corrected | **Done** — see §1.1 |
| Project structure contract defined | **Done** — `docs/ST-EVA-PROJECT-STRUCTURE.md`, `7464422` |
| **829 research artifacts relocated** | **Done** — to `research/experiments/`, relative paths preserved |
| **Archive verification** | **PASS** — 829/829 files, 1,147,661,516 bytes both sides, per-file SHA-256: missing 0, extra 0, mismatch 0 |
| **Source research removed from `experiments/`** | **Done** — relocated, not deleted; every file exists at its new location hash-identical |
| 46 legacy tracked experiments retained | **Done** — unmoved, un-untracked, undeleted |
| `/research/` added to `.gitignore` | **Done** — working tree reports 0 untracked |
| `.kilo/worktrees` | **Untouched** |
| Cache / build cleanup | **Not done** — out of scope |

**No research artifact was deleted.** The relocation is a move with hash
verification, and the manifest
`research/RESEARCH-ARCHIVE-MANIFEST.json` records every file's SHA-256 at both
locations.

### `research/` — the permanent research home (830 files, 1094.8 MB)

Defined by `docs/ST-EVA-PROJECT-STRUCTURE.md`. Gitignored. Contains:

| Path | Files | Size |
|---|---:|---:|
| `research/experiments/aapl-historical-pe-poc/contract/msft_validation/` | 593 | 1014.69 MB |
| `research/experiments/aapl-historical-pe-poc/q4_study/` | 167 | 77.97 MB |
| `research/experiments/aapl-historical-pe-poc/raw/` | 48 | 1.24 MB |
| `research/experiments/aapl-historical-pe-poc/out/` | 5 | 0.20 MB |
| `research/experiments/aapl-historical-pe-poc/amendment1_verify/` | 9 | 0.33 MB |
| `research/experiments/aapl-historical-pe-poc/*.py` (root scripts) | 7 | — |
| `research/RESEARCH-ARCHIVE-MANIFEST.json` | 1 | 354 KB |
| `research/README.md` | 1 | — |
| **Total** | **830** | **1094.8 MB** |

A study that finishes **stays here**. It is not moved "somewhere more permanent",
and it is not moved on the basis of perceived research value.

### `experiments/` — frozen legacy (59 files, 4.6 MB)

| Directory | Files | Tracked |
|---|---:|---:|
| `experiments/001-context-only/` | 15 | **15** |
| `experiments/002-cold-start/` | 44 | **31** (+13 gitignored `.pyc`) |
| **Total on disk** | **59** | **46** |

No new research enters this directory. The Contract no longer sits inside it — it
is at `docs/methodology/CONTRACT-HISTORICAL-PE.md`, tracked.

### Prior private archive — `C:\st-eva-private-archive` (historical)

Superseded by `research/` as the working destination. Retained unchanged; not
the primary archive.

| Item | Value |
|---|---|
| Total | 2290 files, 2406.63 MB |
| `st-eva-research-archive/` | prior archive (includes the removed experiment 003) |
| `historical-pe/msft-validation/` | **new this session** — 593 files, 1014.69 MB, verified |
| `historical-pe/msft-validation-ARCHIVE-MANIFEST.json` | new — records verification result, layout, confirmed artifacts, the four findings, and the validation's disclosed weaknesses |

The archive copy is a preservation copy. **The workspace copy remains
authoritative and was not deleted.**

### Worktrees — outstanding

`.kilo/worktrees/` holds two managed worktrees: **`eastern-anglerfish`** and
**`pepper-chess`**, 917 files / 110.61 MB, 0 tracked. Excluded via
`.git/info/exclude`, **not** `.gitignore`, which makes it invisible to repo-level
ignore policy. `pepper-chess` has its own `archive/` and the removed experiment
003 harness. Activity status of both is **unverified** — this must be resolved
before any worktree action.

### Unresolved from the inventory

`docs/ST-EVA-DATA-LAYER-AUDIT.md` §G.1 flags the one genuinely contested
judgement: whether `msft_validation/raw/docs/` (1011.67 MB) should be retained in
full. Both readings are defensible — EDGAR filings are refetchable in principle,
but the manifest's re-verification check is only meaningful while the bytes are
present, and `raw/prices.json` is explicitly scratch data with no chosen
provider. Currently **resolved in favour of keeping**: the full copy is in
private archive and the workspace copy is intact.

---

## 6. Next milestone

### Workspace Stabilization — nearly complete

| Step | Action | Reversible |
|---:|---|---|
| 0 | ~~Governing documents under version control~~ | **done** — `5e655a7` |
| 0b | ~~Promote the Contract to `docs/methodology/`~~ | **done** — `694ec96` |
| 0c | ~~Correct the tracked/untracked accounting~~ | **done** — §1.1 |
| 0d | ~~Define the permanent directory structure~~ | **done** — `7464422` |
| 0e | ~~Relocate 829 research files to `research/experiments/`, hash-verified~~ | **done** — PASS |
| 0f | ~~Add `/research/` to `.gitignore`~~ | **done** — 0 untracked |
| 1 | ~~Confirm untracked baseline was 829 before touching anything~~ | **done** |
| 2 | Determine whether `eastern-anglerfish` / `pepper-chess` worktrees are live | **outstanding** |
| 3 | Decide whether to retain the 1011.67 MB MSFT raw bulk in `research/` | **outstanding** |
| 6 | Delete `__pycache__`, `.pytest_cache`, `web/frontend/dist` | yes |

The relocation was the destructive step and it was completed safely: per-file
SHA-256 was compared across all 829 files *before* any source was removed, and
recorded in `research/RESEARCH-ARCHIVE-MANIFEST.json`. Had any file mismatched,
every source would still have been intact.

**Standing directory rule.** `docs/ST-EVA-PROJECT-STRUCTURE.md` (`7464422`) is
now canonical and supersedes the conventions in `WORKSPACE-INVENTORY.md` §I.
In summary: production / methodology / contracts / tests → Git, tracked;
contract → `docs/methodology/`; **all research → `research/`, permanently, not
relocated when a study completes**; runtime data → `data/`; migrations →
`archive/`; cache and build output → deletable. Two rules persist above all
others: research artifacts are preserved by default and low value does not imply
deletion, and cleanup scope is defined by git tracking status rather than by
directory.

---

## 7. Recommended sequence after stabilization

Recorded as a recommendation. No step below is authorized by this document, and
none begins a new architectural decision.

| # | Stage | Status | Notes |
|---:|---|---|---|
| 1 | **ST-EVA data-layer audit** | **Done — Phase 1 complete** | `docs/ST-EVA-DATA-LAYER-AUDIT.md`, tracked. Read-only. Recorded: 26-table schema, no populated instance; 7 gaps; Historical P/E cannot currently store a conforming observation. |
| 2 | **Historical P/E implementation design** | Not started | Depends on the audit's Class-1 gaps. Its smallest recommended step is an ADR amendment in the form of Amendment 1, answering four questions: where `evidence_class` lives, where `legal_status_note` lives, the three `audit_status` values and their derivation rule, and what `accounting_basis` becomes. Decision work, no migration. |
| 3 | **Historical P/E Engine implementation** | Not started | Blocked on #2. Contract §L.9 forbids specifying an algorithm beyond the two derivations in §E.1 / §E.3, so the implementation must follow the design, not precede it. |
| 4 | **Regression** | Not started | Contract §I.3's seven-item conformance suite. AAPL and MSFT already produce the exact rows that would serve as the test corpus. |
| 5 | **Web integration** | Not started | Last. `web/` currently has no P/E surface. |

Ordering rationale, recorded so it is not re-litigated: the data-layer audit
precedes implementation design because four Class-1 gaps make a conforming
observation **unrepresentable** today — that is a correctness blocker, not a
scale blocker, and it is the same class of problem Amendment 1 fixed for evidence
retrieval. Design precedes implementation because the Contract deliberately
specifies no parser. Implementation precedes regression because the conformance
suite is defined against the Contract's own sequence. Web integration is last
because a P/E surface over an unrepresentable observation would display a number
the archive cannot justify.

Deliberately **not** in this sequence: corporate-action schema design (ADR-4.2 /
K.4). One split on AAPL and zero splits on MSFT is insufficient evidence to
decide, and the Contract already leaves it OPEN.

---

*Checkpoint first recorded from direct workspace inspection at `5e655a7`;
updated at `5df7f34`; Contract promoted at `694ec96`; structure contract at
`7464422`; research relocation completed (Stage 2C), 2026-10-07; housekeeping
closed and baseline re-measured at `0becbdc`, 2026-10-07.*

*Revision history of this file: (a) the tracked/untracked accounting of
`experiments/` was corrected — 46 legacy tracked research files exist and are
excluded from cleanup scope (§1.1); (b) the Contract was promoted to
`docs/methodology/` with one self-referential header line changed; (c) Stage 2C
relocated 829 research artifacts to `research/experiments/` with per-file
SHA-256 verification (PASS), removed their source copies, and added `/research/`
to `.gitignore`; (d) the §1 baseline was re-measured at `0becbdc` (tracked files
308 → **311**), the relocation status in `docs/ST-EVA-PROJECT-STRUCTURE.md` §6 was
corrected from pending to complete, and the `.gitignore` was given the two
`web/`-level rules `docs/ST-EVA-PROJECT-STRUCTURE.md` §2.2 names.*

*No research was performed. No production code, Core, Web, ADR, Contract,
methodology content, database schema or test was modified. The 46 legacy tracked
research files remain tracked and untouched in `experiments/`. **No research
artifact was deleted** — the 829 files were relocated, and every one exists at
its new location with a matching hash recorded in
`research/RESEARCH-ARCHIVE-MANIFEST.json`.*