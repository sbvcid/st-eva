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

| Item | Value |
|---|---|
| Commit | `5e655a7ffcd8877dbaf4ed61dbf8843ac9f9747a` |
| Short | `5e655a7 docs: formalize historical PE methodology and contract` |
| Branch | `master` |
| Remote | `origin` → `https://github.com/sbvcid/st-eva.git` |
| Sync | `## master...origin/master` — **in sync, no ahead/behind** |
| Previous commit | `b124123 archive: remove experiment 003 from current tree` |

| Count | Value |
|---|---:|
| Tracked files | **304** |
| Untracked files (`-uall`) | **831** |
| Staged | **0** |
| Modified (tracked) | **0** |
| Deleted | **0** |

Untracked breakdown: `experiments/` 829 · `docs/` 1 (`ST-EVA-DATA-LAYER-AUDIT.md`)
· repo root 1 (`WORKSPACE-INVENTORY.md`) · plus this file once written.

Tracked composition: 48 root production `*.py` modules · `docs/` 14 · `tests/` 47
· `reports/` 35 · `history/` 35 · `archive/` 19 (migrations) · `web/` 49.

Note the arithmetic: `5e655a7` moved the ADR and the Contract under version
control, which is why the `experiments/` untracked count fell from 830 to 829
while tracked rose from 302 to 304.

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

### Historical P/E Contract — complete, tracked

`experiments/aapl-historical-pe-poc/contract/CONTRACT-HISTORICAL-PE.md`,
1178 lines / 50.4 KB. Input schema (§B), output schema (§C), state definitions
(§D), normative resolver sequence E.0–E.8, invariants **F-1 … F-15**,
failure semantics (§G), provenance requirements (§H), replay requirements
(§I.1–§I.4), genericization limits (§J), **nine OPEN decisions §K.1–§K.9**,
consistency review §L.1–§L.9.

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

## 5. Current workspace cleanup state

### Stage 1 complete

| Step | Status |
|---|---|
| Governing documents tracked | **Done** — ADR and Contract committed at `5e655a7` and pushed |
| `WORKSPACE-INVENTORY.md` | **Done** — repo root, untracked |
| MSFT private archival copy | **Done** — 593 files / 1,063,982,608 bytes copied and SHA-256 verified, 0 mismatches, 0 missing, 0 extra |
| Removal of research files from workspace | **Not done, by design** — nothing was deleted |
| Cache / build cleanup | **Not done** — out of Stage 1 scope |

### experiments — 889 files, 1100.95 MB

| Directory | Files | Size |
|---|---:|---:|
| `experiments/aapl-historical-pe-poc/` | 830 | 1094.54 MB |
| ├ `contract/msft_validation/` | 593 | 1014.69 MB |
| ├ `q4_study/` | 167 | 77.97 MB |
| ├ root scripts | 7 | — |
| ├ `raw/` | 48 | 1.24 MB |
| ├ `out/` | 5 | 0.20 MB |
| └ `amendment1_verify/` | 9 | 0.33 MB |
| `experiments/002-cold-start/` | 44 | 4.56 MB |
| `experiments/001-context-only/` | 15 | 1.85 MB |

`contract/CONTRACT-HISTORICAL-PE.md` sits inside this tree but is **tracked** —
the standing rule that a contract is governed regardless of directory.

### Private archive — `C:\st-eva-private-archive`

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

### Workspace Stabilization

Finish the disposition decisions that Stage 1 deliberately deferred, then execute
the verified-copy-then-remove sequence. Per `WORKSPACE-INVENTORY.md` §H:

| Step | Action | Reversible |
|---:|---|---|
| 0 | ~~Governing documents under version control~~ | **done** |
| 1 | Verify untracked baseline count (831) | — |
| 2 | Determine whether `eastern-anglerfish` / `pepper-chess` are live; leave alone if active | — |
| 3 | Decide the 1011.67 MB MSFT raw bulk | — |
| 4 | Copy `experiments/**` to private archive, preserving paths; verify file count and byte total | yes, if verified |
| 5 | Only after step 4 verifies, remove `experiments/` from the working copy | **no** |
| 6 | Delete `__pycache__`, `.pytest_cache`, `web/frontend/dist` | yes |
| 7 | Confirm untracked count approaches 0 | — |

Step 4's verification against §D of the inventory is what makes step 5 safe.
Skipping it turns step 5 into the most destructive available action.

Standing directory rule (`WORKSPACE-INVENTORY.md` §I), summarised: production /
ADR / contract / test / spec → Git, tracked. Research / POC / raw evidence →
private archive. Generated output → regenerable. Cache / build → delete. The
exception that must persist: **a contract is governed, not experimental — tracked
regardless of which directory it sits in**, and a cleanup targeting a directory
never removes a file a tracked document cites.

---

## 7. Recommended sequence after stabilization

Recorded as a recommendation. No step below is authorized by this document, and
none begins a new architectural decision.

| # | Stage | Status | Notes |
|---:|---|---|---|
| 1 | **ST-EVA data-layer audit** | **Done — Phase 1 complete** | `docs/ST-EVA-DATA-LAYER-AUDIT.md`, untracked. Read-only. Recorded: 26-table schema, no populated instance; 7 gaps; Historical P/E cannot currently store a conforming observation. |
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

*Checkpoint recorded from direct workspace inspection at `5e655a7`. No research
was performed. No production code, ADR, Contract, or Core was modified. Nothing
under `experiments/` was moved or deleted. Not committed.*