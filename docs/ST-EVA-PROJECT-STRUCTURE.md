# ST-EVA Project Structure — Historical Record

> **歷史資料／非現行指令。** 本文件只記錄撰寫時的設計、狀態、計畫或決策，不具有授權、禁止、限制或要求未來工作的效力。文中任何「binding」「frozen」「approved」「not authorized」「must」等措辭均為歷史內容，不得凌駕使用者目前的要求。當前狀態以現行程式碼、測試及實際 Git 狀態為準。
>
> **HISTORICAL ARCHIVE — NOT CURRENT INSTRUCTIONS.** This document records prior design, status, plans, or decisions. It does not grant, deny, restrict, or require work. Any “binding,” “frozen,” “approved,” “not authorized,” or “must” wording below is historical and does not override the user's current request. Determine current state from current source code, tests, and Git state.

**Historical status:** Originally described as a structure contract; retired as an operative document. It has no current authority.
**Adopted:** 2026-10-07
**Original scope:** directory conventions proposed for the repository as observed on 2026-10-07; not a restriction on future contributions.
**Historical reference:** earlier directory conventions in `WORKSPACE-INVENTORY.md` §I; no current rule is superseded.

At the time, this document proposed an answer to one organizational question. It is not permanent and may be changed freely.

> When ST-EVA adds research, agent intermediate output, raw evidence, formal
> documents, SQLite data, reports or tests — where does each of them go?

It defines structure only. It performs no migration, moves no file, and decides
nothing about methodology.

---

## 1. The eleven directories

| # | Directory | Role class |
|---:|---|---|
| 1 | repo root `*.py` | production |
| 2 | `web/` | production |
| 3 | `tests/` | production |
| 4 | `docs/` | formal documentation |
| 5 | `docs/methodology/` | **canonical methodology** |
| 6 | `data/` | runtime / canonical application data |
| 7 | `archive/` | production subsystem |
| 8 | `reports/` | formal reports |
| 9 | `history/` | runtime-derived records |
| 10 | `research/` | **research — permanent home** |
| 11 | `experiments/` | **legacy — frozen** |

---

## 2. Fixed semantics

### 2.1 Repo root `*.py`

| | |
|---|---|
| **Put here** | Importable production modules. `st_eva_runner.py`, `data_contract.py`, `evidence_valuation_boundary.py`, `sec_provider.py`, `sqlite_archive.py`, `registry_seed.py`, and their peers. |
| **Never here** | Research scripts. Experiment runners. Validation harnesses. Anything that exists to produce a finding. A module that imports nothing from ST-EVA and writes to a directory rather than returning a value is a research script and belongs in `research/`. |
| **Git** | Tracked |
| **New additions** | Allowed |
| **Class** | production, canonical |

### 2.2 `web/`

| | |
|---|---|
| **Put here** | FastAPI application, job manager, schemas, service adapter, and the Vite/React frontend source. |
| **Never here** | Build output (`dist/`, `node_modules/` are gitignored and must never be committed), research fixtures, or backend logic that does not belong to the product surface. |
| **Git** | Tracked (`node_modules/`, `dist/` ignored) |
| **New additions** | Allowed |
| **Class** | production |

Where the ignore rules actually live: the frontend is at `web/frontend/`, and
`web/frontend/.gitignore` has ignored `node_modules` and `dist` throughout. The
root `.gitignore` additionally carries `web/node_modules/` and `web/dist/` so the
`web/`-level layout named above is covered too. Verified: `git ls-files --others
--exclude-standard web/` returns 0 untracked files.

### 2.3 `tests/`

| | |
|---|---|
| **Put here** | Executable tests that assert ST-EVA behaviour. Unit, integration, replay, conformance. |
| **Never here** | Research outputs, generated reports, or any file that records a *finding* rather than asserting a *behaviour*. A validation result is not a test; a test is a claim that is checked. |
| **Git** | Tracked (`__pycache__/` ignored) |
| **New additions** | Allowed |
| **Class** | production, canonical |

### 2.4 `docs/`

| | |
|---|---|
| **Put here** | Formal documentation: specs, status checkpoints, audits, architecture records, usage guides. |
| **Never here** | Methodology that governs a build (that is `docs/methodology/`), research output, or anything that would change meaning if edited casually. |
| **Git** | Tracked |
| **New additions** | Allowed |
| **Class** | formal documentation |

### 2.5 `docs/methodology/`

| | |
|---|---|
| **Put here** | Documents that constrain what an implementation may do. Currently one file: `CONTRACT-HISTORICAL-PE.md`. |
| **Never here** | Status notes, audits, or design exploration. Methodology is not where thinking is recorded; it is where a decision is published. |
| **Git** | Tracked |
| **New additions** | Allowed, but see §5 — a methodology document is a governed artifact and may not be relocated casually once published. |
| **Class** | **canonical, governed** |

`docs/ADR-HISTORICAL-PE-METHODOLOGY.md` also lives under `docs/` rather than here.
That is deliberate: it is the methodology, this directory is its current home,
and moving it is a separate decision, not a consequence of this contract.

### 2.6 `data/`

| | |
|---|---|
| **Put here** | ST-EVA runtime and canonical application data. SQLite archives (`data/st-eva.sqlite`, `data/archives/<TICKER>.sqlite`), runtime indexes, runtime caches the product reads. |
| **Never here** | Raw research artifacts. Frozen SEC filings. Verification outputs. Manifests of a study. **A research artifact in `data/` is misplaced even if it is large and even if it is "data".** |
| **Git** | `data/` is tracked but its runtime contents are not committed. The directory is tracked as a placeholder. |
| **New additions** | Allowed, runtime only |
| **Class** | runtime |

The distinction that matters: `data/` holds what ST-EVA **reads at run time**;
`research/` holds what a study **produced**.

### 2.7 `archive/`

| | |
|---|---|
| **Put here** | The archive subsystem: `migrations/*.sql`, schema infrastructure, migration-runner support. |
| **Never here** | A private or relocated research archive. A personal or ad-hoc copy of prior work does not belong to the archive subsystem, and mixing them makes the migration lineage unreadable. |
| **Git** | Tracked |
| **New additions** | Allowed, migrations only — forward-only, checksum-verified |
| **Class** | production |

### 2.8 `reports/`

| | |
|---|---|
| **Put here** | Formal stage reports that are part of the product record: `2_7_` … `2_38_` and their successors. |
| **Never here** | Ad-hoc investigation output. A report promoted into `reports/` has been accepted as part of the ST-EVA record; one that has not been should live in `research/`. |
| **Git** | Tracked |
| **New additions** | Allowed, by promotion |
| **Class** | formal record |

### 2.9 `history/`

| | |
|---|---|
| **Put here** | Runtime-derived records the product itself emits, e.g. `*_market_implied_assumptions.json`. |
| **Never here** | Research inputs, research outputs, or anything hand-authored. |
| **Git** | Tracked |
| **New additions** | Allowed, runtime output only |
| **Class** | runtime-derived |

### 2.10 `research/` — the permanent home

This is the most important section of this document.

| | |
|---|---|
| **Put here** | **All** ST-EVA research data, permanently and without relocation: POCs, raw source material, SEC documents, SGML headers, verification artifacts, manifests, deterministic outputs, negative-path artifacts, agent research artifacts, intermediate results, historical study data. |
| **Never here** | Production code, methodology, runtime data, or the archive subsystem. |
| **Git** | Not tracked. Treated as ignored working material (see §6). |
| **New additions** | Allowed, and this is where new research goes by default |
| **Class** | **research — preserved** |

**`research/` is the final destination.** When a study finishes, its artifacts
stay exactly where they are. A completed study is not moved "somewhere more
permanent", because `research/` is already permanent.

**Research value does not determine directory.** Nothing is relocated because a
study looks unimportant, small, superseded, or low-value. Value is judged, if at
all, at the moment a result is *promoted* into a governed document — never by
moving a directory.

**This includes agent intermediate output.** Anything an agent generates while
investigating belongs in `research/`, not in a scratch location outside the
repository and not in `experiments/`.

### 2.11 `experiments/` — legacy, frozen

| | |
|---|---|
| **Put here** | Nothing new. Ever. |
| **Never here** | Any research started from this contract onward. |
| **Git** | 46 tracked legacy files remain tracked and are never untracked, moved, or deleted. |
| **New additions (historical proposal)** | None proposed at the time; not a current restriction |
| **Class** | legacy |

Rules:

1. **46 tracked legacy artifacts stay exactly where they are.** All of
   `001-context-only` (15 files) and 31 files of `002-cold-start`. They are part
   of ST-EVA history — committed deliberately at `95373eb` and `7d86a39` — and
   relocating them would break the trail.
2. **No new research enters `experiments/`.** New research starts in `research/`.
3. **Existing content is not deleted because of this contract.** The remaining
   untracked historical research under `experiments/aapl-historical-pe-poc/` is
   historical data; §9 governs its relocation, and until that happens it stays.
4. The original proposal requested a stated reason in commit messages for modifying legacy experiments. This is not a current authorization gate; handle changes according to the user's current request and actual technical impact.

---

## 3. Git policy

### 3.1 Tracked

- production code (root modules, `web/`, `tests/`)
- methodology and contracts (`docs/ADR-HISTORICAL-PE-METHODOLOGY.md`,
  `docs/methodology/`)
- formal specs and documentation (`docs/`)
- selected formal regression fixtures
- formal reports (`reports/`)
- runtime records (`history/`) and archive schema (`archive/`)
- project status, architecture and structure documents
- existing legacy tracked research (the 46 files in `experiments/`)

### 3.2 Not tracked

`research/`. It is preserved research material of the same kind that already
lives outside version control, and it is large enough that tracking it would
dominate the repository.

**Implementation status: ACTIVE.** `/research/` **is** in `.gitignore`, added at
commit `499bd6c` together with the relocation it protects. `research/` therefore
does not appear as untracked in `git status`. Two files inside it are
deliberate exceptions and *are* tracked, because the archive is only verifiable
if its manifest survives with the repository: `research/README.md` and
`research/RESEARCH-ARCHIVE-MANIFEST.json`. Everything else under `research/` is
ignored working material.

### 3.3 Never

- `git add .` in this repository. Even with `/research/` ignored, a careless
  `git add .` stages unrelated content; use an explicit path list.
- `git clean`, `git reset`, or `git restore` as a cleanup mechanism. Removal is
  always done from an explicit, verified file list.

---

## 4. Preservation policy

> **Research artifacts are preserved by default. Low value does not imply
> deletion.**

The following was a proposed preservation policy at the time. It is historical guidance only, not a current limit on deletion or cleanup:

- cache (`__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`)
- temporary and scratch files
- build output (`web/frontend/dist`)
- confirmed duplicate garbage
- invalid empty temporary downloads

Everything else is preserved until an explicit decision says otherwise.

**"Regenerable" is not a deletion reason.** A file may be reproducible in
principle and still be the only surviving record of something — an upstream
vendor may have changed, a fetch may no longer return the same bytes, a
generator script may have been superseded without the output being regenerated.
Regenerability must be *demonstrated and verified*, not assumed, and it is never
sufficient on its own. Deleting a research artifact requires a positive reason
of its own.

Corollaries:

- A frozen raw evidence set is preserved even when a study is superseded.
- A verification artifact is preserved even when the code that produced it is
  gone.
- A manifest is preserved because it is what makes the artifacts beside it
  verifiable.
- Removing a study does not remove its evidence.

---

## 5. Naming and organisation

No taxonomy. No required template. Research is organised by topic and keeps
whatever internal structure makes it legible:

```
research/<topic>/
research/<topic>/<issuer>/
research/<topic>/verification/
```

Optional, at the author's discretion. What is required:

- A study's own internal directory structure is preserved as designed. Studies
  are not required to share an identical internal layout, and normalising them
  would be a form of data loss.
- Filenames are not rewritten on relocation.
- Contents are not reformatted, recompressed, or "cleaned up" in place.

Where a study needs its frozen inputs, its scripts, and its results kept
distinct, the existing `raw/` · scripts · `out/` convention that the AAPL and
MSFT studies already use is a good default to copy.

---

## 6. Migration policy

**This contract performed no migration and moved nothing.**

The relocation this section anticipated has since been carried out, once, as a
move of preserved material. State as it now stands:

| Location | State |
|---|---|
| `experiments/001-context-only/` | 15 tracked legacy files — stays |
| `experiments/002-cold-start/` | 31 tracked + 13 gitignored — stays |
| `experiments/aapl-historical-pe-poc/` | **no longer present** — 829 untracked historical research relocated, not deleted |
| `research/experiments/aapl-historical-pe-poc/` | 829 artifacts, relocated with relative paths preserved |
| `research/experiments/` (total) | 829 artifacts, 1,147,661,516 bytes |

**Relocation: COMPLETE.** The 829 files were moved in a single one-time
operation at commit `499bd6c`, preserving their relative paths and verifying every
file by SHA-256 on both sides **before any source file was removed**.
`research/RESEARCH-ARCHIVE-MANIFEST.json` is the authority: it records each
file's relative path, byte size, and SHA-256 at source and destination, with
`verification.result = PASS` (`file_count_source` = `file_count_destination` =
829, `byte_total_source` = `byte_total_destination` = 1147661516, `missing` = 0,
`extra` = 0, `mismatch` = 0). §4 governed that operation: it was a move of
preserved material, not a cleanup, and no research artifact was deleted.

`experiments/` now holds 46 tracked legacy files and nothing else that is not
either tracked legacy material or a gitignored `.pyc`.

---

## 7. Retired agent guidance (historical only)

The numbered instructions that originally occupied this section have been retired. They described a proposed workflow from 2026-10-07 and do not bind or restrict current or future agents. In particular, they do not require reading this file first, do not prohibit creating or changing directories, and do not impose a retention or Git policy. Follow the user's current request and verify current repository state directly.

## 8. What this contract does not decide

It records no methodology decision, changes no ADR, changes no Contract, and
designs no schema. In particular it does not touch, and must not be read as
touching: the ten OPEN items in the ADR and `docs/methodology/CONTRACT-HISTORICAL-PE.md`;
the reason-code enumeration; the data-layer gaps recorded in
`docs/ST-EVA-DATA-LAYER-AUDIT.md`; or the status of any individual research
artifact.

---

## 9. Quick reference

| I have… | It goes in |
|---|---|
| A production module | repo root `*.py` |
| A web route or component | `web/` |
| A test asserting behaviour | `tests/` |
| A spec, status note, audit | `docs/` |
| An implementation-governing contract | `docs/methodology/` |
| A SQLite archive the product reads | `data/` |
| A migration or archive subsystem file | `archive/` |
| A formal stage report | `reports/` |
| A runtime-emitted record | `history/` |
| **A POC, raw filing, verification, manifest, agent output, intermediate result** | **`research/<topic>/`** |
| A modified legacy experiment | `experiments/` — only with an explicit stated reason |
| Cache, build output, temp files | delete freely (§4) |

---

*Adopted 2026-10-07. No file was moved, deleted, staged or committed in adopting
this contract. No `.gitignore` rule was changed. No ADR, Contract, Core, Web,
test or research artifact was modified.*