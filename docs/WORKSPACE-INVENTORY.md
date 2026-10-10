# WORKSPACE-INVENTORY

**Status:** inventory map. Superseded figures corrected 2026-10-07 at `5df7f34`+.
**Scope:** `C:\git\st-eva` @ branch `master`
**Original survey:** 2026-10-07 @ `b124123`
**Corrected:** 2026-10-07 (tracked/untracked accounting; Contract promoted to `docs/methodology/`)
**Date:** 2026-10-07

Purpose of this file: a permanent map so that future sessions do not have to
re-derive the workspace layout. It is a description, not an instruction to act.
Every disposition below is a *recommendation only*.

> **Correction note.** The first version of this file reported
> `experiments/` as "entire tree untracked". That was wrong, and the error was
> produced by deriving the untracked count by subtraction from an on-disk total
> instead of reading `git ls-files experiments/` directly. Measured now:
> **46 files under `experiments/` are tracked** (legacy research from ST-EVA
> 2.4.3 / 2.6.1b), and they are not part of any private-archive cleanup. The
> three accounting figures that disagreed are reconciled in §A.1.

---

## A. Git state summary

Figures below are as measured at `5df7f34`, before the Contract promotion. The
promotion itself changes only which path the Contract lives at; see §A.1 for the
post-promotion figures.

| Category | Count | Command used |
| --- | --- | --- |
| **staged** | 0 | `git status --porcelain=v1 -uall` (no leading non-`?` column) |
| **modified tracked** | 0 | same (no ` M` / `M ` entries) |
| **deleted** | 0 | same (no ` D` / `D ` entries) |
| **untracked (files)** | **0** | `git status --porcelain=v1 -uall` |
| **tracked files** | **308** | `git ls-files` |
| **branch** | `master`, in sync with `origin/master` | `git status` |

Untracked breakdown: **none.** As of 2026-10-07 (Stage 2C) the last 829 untracked
research files were relocated to `research/experiments/` and `/research/` was
added to `.gitignore`, so the working tree carries no untracked material.

The `research/` tree holds 830 files on disk — 829 relocated research artifacts
plus `RESEARCH-ARCHIVE-MANIFEST.json`. It is **not** tracked and **not** counted
here; its integrity record is
`research/RESEARCH-ARCHIVE-MANIFEST.json`.

### A.1 Reconciling the three experiments/ figures

> **Historical.** These figures describe the workspace *before* Stage 2C. The
> 829 untracked files they describe no longer exist under `experiments/`; they
> were relocated to `research/experiments/` with per-file SHA-256 verification.
> The current figures are in §A.0.

At the time of the survey, `experiments/` held **888 files on disk**. That splits
three ways, and the split is the thing the first version of this file got wrong:

| Classification | Files | Source of the number |
| --- | ---: | --- |
| Tracked in git | **47** | `git ls-files experiments/` |
| Untracked | **829** | `git status --porcelain=v1 -uall -- experiments` |
| Gitignored | **13** | `experiments/002-cold-start/__pycache__/*.pyc` |
| Total on disk | **888** | `Get-ChildItem experiments -Recurse -File` (889 before the Contract moved out) |

47 + 829 = 876; the remaining 13 are `__pycache__` `.pyc` files, gitignored and
therefore counted in neither Git figure. Reading only the on-disk total and the
untracked count, and inferring that the difference was tracked research,
produced the "entirely untracked" claim. It was an inference where a direct query
was available.

The 47 tracked files break down as:

| Tracked subtree | Files | Introduced by |
| --- | ---: | --- |
| `experiments/001-context-only/` (+ `input/`, `outputs/`) | 15 | `95373eb` — *2.4.3 Fix what the consumption experiment found* |
| `experiments/002-cold-start/` (+ `contexts/`) | 31 | `7d86a39` — *2.6.1b: make an unknown metric and an absent figure different answers* |
| `experiments/aapl-historical-pe-poc/contract/CONTRACT-HISTORICAL-PE.md` | 1 | `5e655a7` — this programme; since promoted to `docs/methodology/` |

After the Contract promotion the tracked count under `experiments/` is **46**.
These 46 are **legacy tracked research** and are deliberately retained: they were
committed deliberately in the ST-EVA 2.x era, they are part of that history, and
they are **excluded from private-archive cleanup**. Copying already-tracked files
to private archive would produce an untracked duplicate of tracked content.

Ignored but present on disk (not counted in the 831; regenerable or tooling state):

| Path | Files | Size | Ignored by |
| --- | --- | --- | --- |
| `web/frontend/node_modules` | 9306 | 165.2 MB | `web/frontend/.gitignore:10` |
| `web/frontend/dist` | 11 | 0.3 MB | `web/frontend/.gitignore:11` |
| `.pytest_cache` | 5 | 0.2 MB | `.gitignore:7` |
| `__pycache__` (root) | 82 | 2.4 MB | `.gitignore:1` |
| `tests/__pycache__` | 127 | 4.1 MB | `.gitignore:1` |
| `web/__pycache__` | — | — | `.gitignore:1` |
| `experiments/002-cold-start/__pycache__` | 13 | ~0.1 MB | `.gitignore:1` |
| `.kilo/worktrees` | — | 110.6 MB | `.git/info/exclude:9` |

`.kilo/worktrees` contains two managed worktrees (`eastern-anglerfish`,
`pepper-chess`). It is excluded via `.git/info/exclude`, **not** via
`.gitignore` — so it is invisible to a repo-level ignore policy and is the most
likely source of future "why is my repo 110 MB of nothing" confusion.

---

## B. Directory summary

| Directory | Files | Size | Tracked | Category | Notes |
| --- | ---: | ---: | ---: | --- | --- |
| `.git/` | 270 | 10.6 MB | — | version control | |
| `.kilo/` | 917 | 110.6 MB | 0 | tooling / agent worktrees | excluded via `.git/info/exclude` |
| `web/` | 9373 | 165.8 MB | 49 | production + build artifact | `frontend/node_modules` = 165.2 MB |
| `research/` | 830 | **1094.8 MB** | 0 | **research — permanent, gitignored** | 829 relocated research artifacts + `RESEARCH-ARCHIVE-MANIFEST.json`; verified by per-file SHA-256 |
| `experiments/` | 59 | 4.6 MB | 46 | **legacy research — frozen** | 46 tracked legacy files + 13 gitignored `.pyc`; **0 untracked** since Stage 2C |
| `tests/` | 174 | 5.2 MB | 47 | tests | 127 of 174 files are `__pycache__` |
| `history/` | 35 | 2.6 MB | 35 | generated evidence records | `_market_implied_assumptions.json` per issuer |
| `__pycache__/` (root) | 82 | 2.4 MB | 0 | cache | ignored |
| `reports/` | 35 | 0.33 MB | 35 | final reports | numbered `2_7_` … `2_38_` |
| `docs/` | 14 | 0.27 MB | 13 | docs / ADR | 1 of 14 untracked (the ADR) |
| `archive/` | 19 | 0.08 MB | 19 | archive | `legacy-v6/`, `migrations/` |
| `data/` | 0 | 0 | 0 | empty | tracked, no content |

Repo root additionally holds ~55 tracked `*.py` production modules
(`st_eva_runner.py`, `data_contract.py`, `evidence_valuation_boundary.py`,
`sec_provider.py`, `sqlite_archive.py`, `registry_seed.py`, `investment_context.py`,
`llm_interpreter.py`, …) plus 6 tracked `*.context.json` fixture files at root
(`AAPL`, `MSFT`, `MU`, `NU`, `NVDA`, `TSM`, ~1.9 MB total) and
`README.md`, `SPEC.md`, `LICENSE`.

`data/` is empty and tracked. That is intentional-looking (empty dir placeholder)
and is **not** a leftover to clean.

---

## C. Research groups

All research lives under `experiments/`. Three independent studies exist:
two unrelated ones (`001`, `002`, small, **legacy tracked**) and one large
Historical P/E programme (`aapl-historical-pe-poc`, 1094.5 MB, five
sub-studies, **wholly untracked** except for the Contract, which has been
promoted to `docs/methodology/`).

Note the sizes: `001` + `002` together are 6.4 MB, of which 4.8 MB is
`002-cold-start`. The 1101 MB attributed to `experiments/` is almost entirely
the untracked `aapl-historical-pe-poc` tree. Cleanup scope is the untracked
portion only.

### C.1 `experiments/001-context-only`

| Field | Value |
| --- | --- |
| Files / size | 15 files, 1.9 MB — **all 15 tracked in git** |
| Purpose | Context-only experiment: feed 6 issuer context JSONs, produce per-issuer markdown. Validates whether context alone yields usable output. |
| Final artifact | Yes — `experiment_summary.md`, `self_audit.md`, `outputs/*.md` (6) |
| Regenerable | Partially. `outputs/*.md` come from `input/*.json` but no script is retained in this folder. |
| Raw evidence | Yes — `input/*.context.json` (6 files) |
| Verification | No |
| Long-term value | Medium. Documents an experiment whose conclusion is superseded by `002-cold-start`. |
| **Disposition** | **LEGACY_TRACKED / KEEP_IN_REPO.** All 15 files are tracked (`95373eb`, ST-EVA 2.4.3). An earlier version of this file said `PRIVATE_ARCHIVE`; that was derived from the wrong tracked/untracked accounting and has been corrected. Already in git history — archiving would duplicate tracked content. **Not in cleanup scope.** |

### C.2 `experiments/002-cold-start`

| Field | Value |
| --- | --- |
| Files / size | 44 files, 4.8 MB — **31 tracked**, 13 gitignored `__pycache__` |
| Purpose | Cold-start experiment: cross-source / provenance / derived-metric examination over 6 issuer contexts. Produced the lineage and evidence-model thinking that later became production modules. |
| Final artifact | Yes — `RESEARCH_REPORT_AND_SELF_AUDIT.md`, `analysis_summary.json`, `summary.txt`, `key_values.txt`, `crosssource*.txt`, `derived_detail.txt`, `val_dq.txt`, `provenance_refs.txt`, `full_structure.txt` |
| Regenerable | **Yes**, largely. 12 `.py` scripts are retained and read `contexts/*.json`, which are also retained. The `*.txt` outputs are regenerable by rerunning. |
| Raw evidence | Yes — `contexts/*.json` (6 files) |
| Verification | No formal verification artifact. `RESEARCH_REPORT_AND_SELF_AUDIT.md` is the self-audit. |
| Long-term value | High for provenance reasoning. Its conclusions are cited in production docs. |
| **Disposition** | **LEGACY_TRACKED / KEEP_IN_REPO** for the 31 tracked files (`7d86a39`, ST-EVA 2.6.1b). Corrected from `PRIVATE_ARCHIVE`. The 13 `.pyc` files are gitignored cache and are **DISPOSABLE**. **Not in cleanup scope.** |

### C.3 `experiments/aapl-historical-pe-poc` — sub-study breakdown

Total: **829 untracked files, 1094.5 MB** (the figure rose to 830 tracked-or-not
when the Contract was committed at `5e655a7`; that one file has since been
promoted to `docs/methodology/`). Five sub-studies, in the order they were
executed. **This group is the entire cleanup scope.**

#### C.3.1 Core AAPL Historical P/E POC

| Field | Value |
| --- | --- |
| Path | `experiments/aapl-historical-pe-poc/` (root scripts) + `raw/` + `out/` |
| Files / size | 7 scripts + 48 raw + 5 out = 60 files, **1.44 MB** |
| Purpose | First proof that a deterministic, replayable TTM GAAP diluted P/E can be built from raw SEC filings + prices under point-in-time rules. Produced the 31 observation dates and the negative path. |
| Final artifact | **Yes — `out/historical_pe_points.json` (186 KB), `out/historical_pe_points.csv`, `out/report.txt`, `out/verification.txt`, `out/determinism.txt`** |
| Regenerable | Yes, from `raw/` — but only if the fetch scripts still hit equivalent SEC data. The frozen `raw/` + `manifest.json` is what makes it reproducible; `raw/` itself is not reliably refetchable byte-for-byte. |
| Raw evidence | Yes — `raw/` 48 files / 1.24 MB: `manifest.json`, `daily_prices.json`, `eps_diluted_concept.json`, `filing_acceptance_evidence.json`, `submissions.json`, `headers/` (43 SGML headers with `ACCEPTANCE-DATETIME`) |
| Verification | **Yes — `out/verification.txt`, `out/determinism.txt`** (two-run hash equality) |
| Long-term value | **Very high.** This is the evidence base the ADR Amendment 1 and the whole Contract rest on. |
| **Disposition** | **PRIVATE_ARCHIVE** — do not commit; do not delete. Contains the 31/31 TTM worked example cited by the ADR and the Contract. |

#### C.3.2 AAPL Q4 Study

| Field | Value |
| --- | --- |
| Path | `experiments/aapl-historical-pe-poc/q4_study/` |
| Files / size | 167 files, **78.0 MB** (155 raw / 77.9 MB, 6 out / 0.06 MB, 6 scripts) |
| Purpose | The empirical basis for ADR Amendment 1. Spotted that AAPL stopped tagging quarter-length `EarningsPerShareDiluted` XBRL facts from FY2021, then proved the same figure still exists as document text in Form 8-K Item 2.02 EX-99.1. 5/5 Q4 quarters recovered. |
| Final artifact | **Yes — `out/q4_evidence_table.txt`, `out/q4_evidence_table.csv`, `out/q4_evidence_records.json`, `out/ttm_unblocking.json`, `out/verification.txt`, `out/additivity_check.txt`** |
| Regenerable | Partially. `raw/docs/` is the frozen SEC byte set; the extraction scripts are retained. Re-fetch would not reproduce byte-identical exhibits. |
| Raw evidence | **Yes — the highest-value raw set in the repo.** `raw/docs/` (155 files / 77.9 MB): 10 accessions' complete EDGAR document trees, including `_htm.xml` inline-XBRL, `_lab.xml`, `_pre.xml`, `.xsd`, and embedded `.jpg` images. `raw/headers/` (10 SGML headers). `raw/ir/apple_earnings_release_index.htm`. `raw/source_manifest.json`. |
| Verification | **Yes — `out/verification.txt`**, plus `additivity_check.txt` (explicitly demonstrating that FY − YTD differencing does **not** reconcile, supporting ADR Decision 4) |
| Long-term value | **Highest.** `raw/` here is the primary-source evidence that ADR §6.1 tabulates accession-by-accession. Losing it would make the ADR unverifiable. |
| **Disposition** | **PRIVATE_ARCHIVE** — must never be deleted; move to cold storage rather than repo. |

#### C.3.3 Amendment 1 Verification

| Field | Value |
| --- | --- |
| Path | `experiments/aapl-historical-pe-poc/amendment1_verify/` |
| Files / size | 9 files, **0.33 MB** |
| Purpose | Re-ran the POC with the furnished evidence class admitted, then diffed against the prior result. This is what produced 31/31 TTM and the "0 mislabelled components" claim. |
| Final artifact | **Yes — `out/amendment1_pe_points.json`, `out/negative_path_no_furnished.json`, `out/prior_vs_current.txt`, `out/prior_vs_current.csv`, `out/verification.txt`** |
| Regenerable | **Yes** — runs entirely off `../raw/` and `../q4_study/out/`, both of which are retained. No separate raw set. |
| Raw evidence | No — inherits from C.3.1 and C.3.2 |
| Verification | **Yes — `out/verification.txt`.** The negative path here is the artifact that proves furnished admission is what changed the result, not a data accident. |
| Long-term value | **Very high.** `negative_path_no_furnished.json` is what Contract §I.3 item 3 and §L.2 cite as the byte-for-byte reproduction of the prior 12/31 state. |
| **Disposition** | **PRIVATE_ARCHIVE** — the negative-path file is a deterministic conformance artifact. Keep both the JSON and the verification text. |

#### C.3.4 Historical P/E Contract

| Field | Value |
| --- | --- |
| Path | **`docs/methodology/CONTRACT-HISTORICAL-PE.md`** (promoted 2026-10-07; was `experiments/aapl-historical-pe-poc/contract/`) |
| Files / size | **1 file, 51.6 KB** |
| Purpose | The engine interface contract: `QuarterEpsEvidence` / `HistoricalPriceEvidence` / `HistoricalPeObservation`, resolver sequence E.0–E.8, invariants F-1…F-15, replay requirements I.1–I.4, OPEN decisions K.1–K.9, consistency review L.1–L.9. |
| Final artifact | **Yes — it is the artifact.** |
| Regenerable | **No.** This is a decision document. It is not derivable from any other file in the workspace. |
| Raw evidence | n/a |
| Verification | §L is an in-document consistency review against the ADR and both POCs. |
| Long-term value | **Highest of all.** It is the normative document an implementation is written against. §B.2.1 (Genericization Note, added 2026-10-07 from MSFT Finding C.1) is the only place the AAPL-layout parser hazard is stated. |
| **Disposition** | **KEEP_IN_REPO** — and now, since the promotion, it sits beside the ADR at `docs/methodology/`. The one substantive edit made during promotion was line 7's self-referential `**File:**` header, corrected from the old path. No methodology content was altered. |

Note: 12 **untracked** MSFT research files still name the old Contract path
(`compute_msft_pe.py`, `build_msft_evidence.py`, `phase1_fiscal_identity/`
scripts and report, and five `out/` artifacts). These are frozen validation
outputs whose bytes are hash-recorded in the private-archive manifest. They are
deliberately **not** rewritten. See §G.6.

#### C.3.5 MSFT Contract Validation

| Field | Value |
| --- | --- |
| Path | `experiments/aapl-historical-pe-poc/contract/msft_validation/` (+ `phase1_fiscal_identity/`) |
| Files / size | 593 files, **1014.7 MB** — 99.6% of it is `raw/docs/` |
| Purpose | Second-issuer contract validation. Applied the contract's resolver sequence to MSFT (CIK 0000789019, FYE June) without modifying the contract. Result: 24/27 TTM available, 0/24 with furnished disabled, all F-1…F-15 pass, 6/6 failure paths pass. Produced Finding C.1 (AAPL exhibit layout is not universal), J.1 (10-K-list bug shifts a full fiscal year on MSFT), J.2 (MSFT has no before-cutoff acceptance), J.3 (evidence class keys on Item 2.02 code, not form). |
| Final artifact | **Yes — `out/report.txt`, `out/verification.txt`, `out/failure_paths.txt` / `.json`, `README.md`, `out/observations.csv`, `out/msft_pe_points.json`, `out/msft_negative_path.json`, `out/msft_evidence.json`; plus `phase1_fiscal_identity/report.md` and `verification.txt`.** |
| Regenerable | Partially. 7 scripts + 8 phase-1 scripts are retained. `raw/` can be re-fetched from EDGAR but **will not** reproduce byte-identical documents, and the prices are explicitly labelled "validation-only scratch data; contract B.3 chooses no provider". |
| Raw evidence | **Yes — the largest raw set. 570 files / 1013.8 MB.** `raw/docs/` 469 files / 1011.7 MB (48 accessions' complete EDGAR trees, incl. `_htm.xml` inline-XBRL and many embedded `.jpg` page images from the FY2026 Q1 8-K), `raw/headers/` 48 SGML headers, `raw/index/` 47 filing index pages, `raw/submissions.json`, `raw/eps_diluted.json`, `raw/eps_basic.json`, `raw/net_income.json`, `raw/prices.json`, `raw/source_manifest.json` (sha256 manifest). |
| Verification | **Yes — `out/verification.txt` (independent second computation path, PIT checks, F-1…F-15 matrix, two-run hash equality, frozen-input hash re-verification), `out/failure_paths.txt` (7 refusal scenarios), `phase1_fiscal_identity/verification.txt`.** |
| Long-term value | **High for the findings, low for the bulk bytes.** The 12 documentation files + 8 `out/` files carry the entire result. The 1011 MB of `raw/docs/` is bulky primary source whose only unique contribution is byte-level re-verifiability, which is served by `raw/source_manifest.json`. |
| **Disposition** | **NEEDS_REVIEW** — this is the one group where the "regenerable vs. keep" judgement is genuinely contested, and it is also where 92% of the workspace's bytes sit. See §G. |

---

## D. File count / size

| Group | Files | Size | % of workspace |
| --- | ---: | ---: | ---: |
| C.3.5 MSFT validation `raw/docs/` | 469 | 1011.7 MB | 76.4% |
| C.3.2 Q4 study `raw/docs/` | 155 | 77.9 MB | 5.9% |
| `web/frontend/node_modules` | 9306 | 165.2 MB | 12.5% |
| `.kilo/worktrees` | 917 | 110.6 MB | 8.4% |
| C.3.5 MSFT validation (all other) | 124 | 3.0 MB | 0.2% |
| C.3.2 Q4 study (all other) | 12 | 0.1 MB | <0.1% |
| C.2 `002-cold-start` | 44 | 4.8 MB | 0.4% |
| C.1 `001-context-only` | 15 | 1.9 MB | 0.1% |
| C.3.1 AAPL POC | 60 | 1.4 MB | 0.1% |
| C.3.3 Amendment 1 verify | 9 | 0.3 MB | <0.1% |
| C.3.4 Contract | 1 | 0.05 MB | <0.1% |
| `docs/` | 14 | 0.27 MB | <0.1% |
| `history/` + `reports/` + `archive/` | 89 | 3.0 MB | 0.2% |
| **Total workspace** | **~13,000** | **~1324 MB** | |

Compression note: `raw/docs/` is overwhelmingly inline-XBRL `.htm`, `_htm.xml`,
`cal.xml`, `def.xml`, `lab.xml`, `pre.xml`, `.xsd` and `.jpg` — highly
compressible text and images. The 1090 MB of raw SEC evidence would likely
archive to a small fraction of that. This is an estimate to verify before
acting, not a measured figure.

---

## E. Recommended disposition

One disposition per group. **Recommendations only — nothing was executed.**

| # | Group | Disposition | Rationale |
| --- | --- | --- | --- |
| 1 | `docs/ADR-HISTORICAL-PE-METHODOLOGY.md` | **KEEP_IN_REPO** | Frozen, approved methodology. Amended once (Amendment 1). Tracked since `5e655a7`. |
| 2 | `docs/methodology/CONTRACT-HISTORICAL-PE.md` | **KEEP_IN_REPO** | The normative engine contract. Not regenerable. Promoted out of `experiments/` on 2026-10-07 so it sits beside the ADR. |
| 3 | Repo root production `*.py`, `web/`, `tests/` (non-cache), `docs/` (other 13), `reports/`, `history/`, `archive/` | **KEEP_IN_REPO** | Already tracked. No action. |
| 4 | `web/frontend/node_modules`, `web/frontend/dist`, all `__pycache__`, `.pytest_cache` | **REGENERABLE** | Build/tooling output. Already gitignored. Zero information content. Deleting costs only a reinstall/build. |
| 5 | `.kilo/worktrees` | **NEEDS_REVIEW** | 110 MB, 0 tracked, excluded via `.git/info/exclude` rather than `.gitignore`. Contains live managed sessions (`eastern-anglerfish`, `pepper-chess`). Deleting it would destroy in-flight work. Determine first whether either session is still active. |
| 6 | `experiments/aapl-historical-pe-poc/q4_study/` (untracked) | **PRIVATE_ARCHIVE** | Primary-source evidence underpinning ADR Amendment 1. Never delete. Move to cold storage. |
| 7 | `experiments/aapl-historical-pe-poc/raw/`, `out/` (untracked) | **PRIVATE_ARCHIVE** | The 31/31 worked example the ADR and Contract cite. Never delete. |
| 8 | `experiments/aapl-historical-pe-poc/amendment1_verify/` (untracked) | **PRIVATE_ARCHIVE** | Contains `negative_path_no_furnished.json`, the deterministic conformance artifact cited by Contract §I.3/§L.2. Never delete. |
| 9 | `experiments/001-context-only/` — **46-file legacy tracked set, corrected from `PRIVATE_ARCHIVE`** | **LEGACY_TRACKED / KEEP_IN_REPO** | All 15 files tracked since `95373eb` (ST-EVA 2.4.3). Already in git history. **Excluded from cleanup** — archiving would duplicate tracked content. |
| 10 | `experiments/002-cold-start/` — **31 tracked + 13 gitignored, corrected from `PRIVATE_ARCHIVE`** | **LEGACY_TRACKED / KEEP_IN_REPO**; `.pyc` **DISPOSABLE** | 31 files tracked since `7d86a39` (ST-EVA 2.6.1b). **Excluded from cleanup.** Only the 13 gitignored `.pyc` are disposable. |
| 11 | `experiments/.../contract/msft_validation/` (untracked) | **NEEDS_REVIEW** | See §G.1. The 12 documentation files + 8 `out/` files are the finding and should be preserved; the 1011 MB raw set is a separate decision. |
| 12 | `experiments/002-cold-start/__pycache__/` (13 `.pyc`) | **DISPOSABLE** | Pure cache. Already gitignored. |
| 13 | `data/` (empty, tracked) | **KEEP_IN_REPO** | Empty tracked directory. Looks intentional. Not a leftover. |
| — | **Anything not classified above** | **NEEDS_REVIEW** | — |

---

## F. Important artifacts — must not be deleted by accident

Ordered by consequence of loss.

### F.1 Governing documents

| Artifact | Why |
| --- | --- |
| `docs/ADR-HISTORICAL-PE-METHODOLOGY.md` | Frozen methodology. Decisions 1–14. Every other artifact cites it. §6.1's Q4 evidence table is derived from `q4_study`. Tracked since `5e655a7`. |
| `docs/methodology/CONTRACT-HISTORICAL-PE.md` | The engine contract. §B.2.1 is the only statement of the exhibit-layout genericization hazard. Tracked since `5e655a7`, promoted out of `experiments/` on 2026-10-07. |

Both were untracked single copies until `5e655a7`. That was the single largest
risk in this workspace and it is now closed: both are in git history, and the
Contract sits beside the ADR under `docs/` rather than inside the untracked
research tree, so a `git clean` or a worktree reset can no longer take it.

### F.2 Manifests and hashes

| Artifact | Why |
| --- | --- |
| `aapl-historical-pe-poc/raw/manifest.json` | sha256 manifest of the frozen core POC input set |
| `q4_study/raw/source_manifest.json` | sha256 manifest of the frozen Q4 study input set |
| `msft_validation/raw/source_manifest.json` | sha256 manifest of the frozen MSFT input set |
| `msft_validation/out/verification.txt` — final check | "every frozen raw input still matches its recorded hash / drift=[]" |

These are what make the other files verifiable rather than merely present. A raw
document set without its manifest is not evidence; it is a folder.

### F.3 Deterministic verification artifacts

| Artifact | Why |
| --- | --- |
| `aapl-historical-pe-poc/out/determinism.txt` | Two-run hash equality for the core POC |
| `aapl-historical-pe-poc/out/verification.txt` | Core POC invariant + PIT verification |
| `q4_study/out/verification.txt` | Q4 evidence verification |
| `q4_study/out/additivity_check.txt` | Empirical demonstration that FY − YTD differencing does not reconcile — the evidence behind ADR Decision 4 |
| `amendment1_verify/out/negative_path_no_furnished.json` | Furnished class disabled → reproduces the prior POC's 12/31 state. Cited by Contract §I.3 item 3 and §L.2 |
| `amendment1_verify/out/verification.txt` | Amendment 1 verification |
| `msft_validation/out/verification.txt` | Independent second computation path, PIT checks, F-1…F-15 matrix, two-run hash equality |
| `msft_validation/out/failure_paths.txt` / `.json` | 7 refusal scenarios |
| `msft_validation/phase1_fiscal_identity/verification.txt` | Fiscal-identity resolution without a 10-K list |
| `msft_validation/phase1_fiscal_identity/report.md` | The FY2022-Q1-has-no-10-K boundary scenario |

### F.4 Final reports

| Artifact | Why |
| --- | --- |
| `msft_validation/README.md` | Findings C.1, J.1, J.2, J.3 in narrative form, with the explicit "non-GAAP case is honestly weak" caveat and the vacuous-invariant qualifications (F-6, F-10) |
| `msft_validation/out/report.txt` | 23 furnished extractions, FY2021 worked example, 27-date observation table, invariant matrix |
| `aapl-historical-pe-poc/out/report.txt` | Core POC report |
| `q4_study/README.md` | Q4 study method and source-priority table |
| `experiments/002-cold-start/RESEARCH_REPORT_AND_SELF_AUDIT.md` | The self-audit for the cold-start study |
| `reports/2_7_` … `2_38_` (35 files, tracked) | Production-stage reports, already in git |

### F.5 Raw primary-source evidence

| Set | Size | Note |
| --- | ---: | --- |
| `msft_validation/raw/docs/` | 1011.7 MB | 48 MSFT accessions, complete EDGAR trees incl. inline XBRL and page images |
| `q4_study/raw/docs/` | 77.9 MB | 10 AAPL accessions, incl. the 5 × EX-99.1 exhibits that Amendment 1 depends on |
| `msft_validation/raw/headers/` + `index/` | 1.2 MB | 48 SGML headers (the authoritative `ACCEPTANCE-DATETIME` per ADR Decision 12) |
| `q4_study/raw/headers/` | — | 10 SGML headers |
| `aapl-historical-pe-poc/raw/headers/` | 0.78 MB | 43 SGML headers |
| `aapl-historical-pe-poc/raw/*.json` | ~0.5 MB | submissions, EPS concept, prices, acceptance evidence |

Note on a trap: `msft_validation/raw/headers/` and
`msft_validation/raw/index/` look like derived caches but are the authoritative
PIT anchors. ADR Decision 12 makes the **SGML header** the normative acceptance
source; the submissions-API JSON is explicitly non-conformant. Those `.txt`
files are load-bearing, not scratch.

---

## G. Items requiring manual review

### G.1 `msft_validation/raw/docs/` — 1011.7 MB, 92% of the workspace

This is the one decision I am not going to make for you. Both readings are
defensible:

**Argument for keeping it:** the Contract §H.3 requires that
`content_sha256` be re-verifiable by refetch, and the MSFT verification's final
check is "every frozen raw input still matches its recorded hash". That check is
only meaningful while the bytes are present. `raw/source_manifest.json` alone
verifies nothing.

**Argument for discarding it:** EDGAR does not delete filings, so the documents
are refetchable in principle. The price input is explicitly labelled scratch
data with no chosen provider (Contract §B.3), so the manifest is already
honest about a partial gap. And the 12 documentation files plus 8 `out/` files
carry the actual finding.

What would settle it: check whether any future work intends to re-run the MSFT
validation end to end. If yes, keep. If the result is being accepted as final
and only the findings matter, the compressed archive plus the manifest is
sufficient.

Before deleting anything: confirm `raw/source_manifest.json` covers all 469 files
under `raw/docs/`, not only the 48 top-level ones.

### G.2 The governing documents — **RESOLVED**

This item was written when the ADR and the Contract were untracked, unbacked
single copies, with the Contract sitting inside the untracked 1.1 GB research
tree — a naive "delete the experiments folder" would have taken it. Both are now
tracked and pushed (`5e655a7`), and the Contract was promoted to
`docs/methodology/CONTRACT-HISTORICAL-PE.md` on 2026-10-07 so that no governed
document lives under `experiments/` at all. **Nothing here is outstanding.**

### G.3 `.kilo/worktrees` — 110.6 MB

Two live managed sessions. Excluded via `.git/info/exclude`, so no repo-level
policy covers it. Determine whether either session is still active before any
action. This is out of scope for the archive question but it is 8% of the
workspace and it is invisible to `.gitignore`.

### G.4 `experiments/002-cold-start` — superseded status

Its conclusions were carried forward into production. 31 of its 44 files are
tracked (ST-EVA 2.6.1b), so its status as a reference is already settled by
history; whether the remaining disposition should change is not open. **Not in
cleanup scope.**

### G.5 Unclassified files — **RESOLVED**

Previously `git status -uall` reported 829 untracked files under `experiments/`.
All 829 were relocated to `research/experiments/` in Stage 2C and verified by
per-file SHA-256; the working tree now reports **0 untracked**. No orphans.

### G.6 Known archived-artifact staleness — accepted, do not "fix"

Twelve MSFT research files name the Contract's former path
`experiments/aapl-historical-pe-poc/contract/CONTRACT-HISTORICAL-PE.md`. They are
now at `research/experiments/aapl-historical-pe-poc/contract/msft_validation/`
and remain byte-identical to what was archived:

| File | Kind |
| --- | --- |
| `msft_validation/compute_msft_pe.py` | research script |
| `msft_validation/build_msft_evidence.py` | research script |
| `msft_validation/README.md` | research report |
| `msft_validation/out/report.txt` | generated output |
| `msft_validation/out/msft_pe_points.json` | generated output |
| `msft_validation/out/msft_negative_path.json` | generated output |
| `msft_validation/out/msft_evidence.json` | generated output |
| `phase1_fiscal_identity/build_phase1.py` | research script |
| `phase1_fiscal_identity/fiscal_identity.json` | generated output |
| `phase1_fiscal_identity/report.md` | research report |

These are **frozen research artifacts**. Their bytes are SHA-256 recorded in
`C:\st-eva-private-archive\historical-pe\msft-validation-ARCHIVE-MANIFEST.json`,
so rewriting the path inside them would break the very verification that makes
them trustworthy. They are left as-is deliberately. The stale path is a record of
when the validation ran, which is exactly what a research artifact should be.

**No tracked file contains the old Contract path.**

---

## H. Recommended one-time cleanup sequence

**This is a proposal. Nothing below was executed.**

The ordering matters: it front-loads the safety steps and pushes every
irreversible action to the end.

| Step | Action | Reversible? | Precondition |
| --- | --- | --- | --- |
| 0 | ~~**Get the two governing documents under version control**~~ | Yes | **done** — `5e655a7` |
| 0b | ~~**Promote the Contract to `docs/methodology/`**~~ | Yes | **done** — `694ec96` |
| 0c | ~~**Correct the tracked/untracked accounting**~~ | Yes | **done** — see §A.1 |
| 0d | ~~**Define the permanent directory structure**~~ | Yes | **done** — `docs/ST-EVA-PROJECT-STRUCTURE.md`, `7464422` |
| 0e | ~~**Relocate the 829 untracked research files to `research/experiments/`**~~ | Yes, by relocation | **done** — per-file SHA-256 PASS, `missing=0 extra=0 mismatch=0` |
| 0f | ~~**Add `/research/` to `.gitignore`**~~ | Yes | **done** — working tree now reports 0 untracked |
| 1 | ~~Verify the relocation manifest~~ | — | **done** — `research/RESEARCH-ARCHIVE-MANIFEST.json` |
| 2 | Confirm whether `.kilo/worktrees` sessions are live; leave alone if either is active | — | **still outstanding** |
| 3 | Resolve §G.1 (MSFT raw bulk retention) | — | **still outstanding** |
| 4 | Delete `__pycache__`, `.pytest_cache`, `web/frontend/dist`. Leave `node_modules` unless disk pressure demands otherwise. | Yes (`npm ci`) | none |

**Outcome.** The relocation is complete and verified. `experiments/` now contains
**only** the 46 tracked legacy files plus 13 gitignored `.pyc` — the directory
exists solely as the frozen legacy record required by
`docs/ST-EVA-PROJECT-STRUCTURE.md` §2.11. All 829 research artifacts now live
permanently under `research/experiments/`, with their relative paths, bytes and
SHA-256 hashes recorded in the archive manifest. **Nothing was deleted**: every
one of the 829 files exists at its new location, hash-identical.

Two things this sequence deliberately never did: it never ran `git add .`,
`git clean`, or `git reset`; and it never removed a source file before its hash
matched at the destination. The per-file SHA-256 comparison is what made step 0e
reversible — had any file mismatched, the source would still be intact.

---

## I. Directory rule — "organize once, never again"

Adopt this as the standing convention. The point is that the decision is made
once per new artifact at creation time, so no future session has to re-derive it.

### The rule

```
A file's directory determines its fate. Decide at creation, never later.

  production / ADR / contract / test / spec  ->  Git, tracked
  research / POC / experiment                 ->  private archive
  raw primary-source evidence                 ->  private archive, cold
  generated output                            ->  regenerable; safe to delete
  cache / temp / build output                 ->  delete
```

### How each rule manifests in this repo

| Rule | Path | Git? |
| --- | --- | --- |
| production | `*.py` at root, `web/` (minus ignored), `tests/` (minus cache) | tracked |
| ADR / spec | `docs/` | tracked |
| **contract** | **`docs/methodology/CONTRACT-*.md`** — **promoted out of `experiments/` 2026-10-07** | tracked |
| tests | `tests/` | tracked |
| report | `reports/` | tracked |
| archive | `archive/` | tracked |
| **research** | **`research/**`** — permanent home, all new research | **not** tracked (`/research/` gitignored) |
| research (legacy) | `experiments/001-context-only/`, `experiments/002-cold-start/` | **tracked** — frozen, see §A.1 |
| research (historical) | `research/experiments/aapl-historical-pe-poc/**` — relocated from `experiments/` | **not** tracked |
| raw evidence | `research/**/raw/**` | **not** tracked |
| generated output | `research/**/out/**` | **not** tracked |
| cache | `__pycache__`, `.pytest_cache`, `web/frontend/dist` | ignored |

> **Superseded.** This section restates rules that are now canonically defined in
> `docs/ST-EVA-PROJECT-STRUCTURE.md` (`7464422`). Where the two differ, that
> document governs. In particular `research/` is now the permanent home for all
> research — a completed study is **not** relocated out of it.

### The exception that must be written down

**A contract is governed, not experimental.** It used to live under `experiments/`
by historical accident. It no longer does: as of 2026-10-07 the Contract is at
`docs/methodology/CONTRACT-HISTORICAL-PE.md`, beside the ADR, so the rule no
longer depends on an exception being remembered:

> A contract lives in `docs/methodology/`, never under `experiments/`.

The governing principle remains, because it still applies to final reports and
to anything else a tracked document cites:

> If a file is an ADR, a contract, or a final report that another artifact
> cites, it is tracked **regardless of which directory it is in**, and it is
> never deleted as part of an experiment cleanup.

The inverse also holds, and it is the rule that would have prevented the earlier
situation:

> A cleanup that targets a directory never removes a file from that directory
> if that file is cited by a tracked document — unless the citation is updated
> first.

And a third, added after the §A.1 correction:

> Cleanup scope is defined by git tracking status, not by directory. A directory
> can contain both tracked and untracked files, and "clean up this directory"
> means the untracked ones only.

### Operating procedure

- Commit ADR and contract changes **separately** from research output, with the
  research evidence cited by path in the commit message. The evidence stays in
  private archive; the pointer lives in git.
- Give every experiment a `README.md` stating: what it tested, what it concluded,
  which raw evidence it depends on, and which governing document cites it. Both
  `001-context-only` and `002-cold-start` already do this.
- Every experiment carries a `raw/source_manifest.json`. A raw set without a
  manifest is not evidence.
- Every experiment carries an `out/verification.txt` stating what was verified
  and what was only vacuously true. The MSFT validation's honesty about its weak
  non-GAAP case and its vacuous F-6/F-10 is the model.
- Prefer regenerating `out/` over preserving it. But when an `out/` file is
  cited by a governing document — `negative_path_no_furnished.json` is — it
  becomes a governed artifact and is preserved.
- Never `git add .` in this repo. Explicit paths only. The `.gitignore` does not
  exclude `experiments/`, so `git add .` would attempt to stage 1.1 GB of SEC
  filings.

### Files that would still need attention under this rule

Applied so far: the ADR and the Contract are tracked (`5e655a7`); the Contract
has been promoted to `docs/methodology/`; the tracked/untracked accounting in
§A, §B, §C, §D, §E, §F, §G and §H has been corrected against direct git
queries. Outstanding: resolve §G.1 for the 1011 MB MSFT raw set, and resolve
§G.3 for `.kilo/worktrees`. Steps 4 and 5 of §H, scoped to untracked research
only.

---

*Inventory first generated read-only on 2026-10-07 at `b124123`. Corrected the
same day: the original reported `experiments/` as entirely untracked, which was
an inference error – 46 legacy tracked research files exist there. No production
code, ADR or methodology content was altered. The Contract was promoted to
`docs/methodology/` with exactly one edit: line 7's self-referential `**File:**`
header.*

---

## Addendum, 2026-10-10 — one stale claim in §B corrected

The row in §B and the note in §A reading `` `data/` is empty and tracked `` are
no longer accurate. Measured directly on 2026-10-10:

| Path | Size | Notes |
|---|---:|---|
| `data/st-eva.sqlite` (+ `-wal`, `-shm`) | 659 KB | CLI `--archive` default target |
| `data/archives/AAPL.sqlite` (+ `-wal`, `-shm`) | 1.71 MB | per-ticker archive from the web adapter |
| `data/archives/MSFT.sqlite` (+ `-wal`, `-shm`) | 1.67 MB | per-ticker archive |
| `data/archives/TSM.sqlite` (+ `-wal`, `-shm`) | 1.18 MB | per-ticker archive |

These are runtime state, not source. They are excluded by `.gitignore` (added in
`90fbd41`) and remain untracked, which is correct. They were **read only** for
this verification; nothing was written, deleted or reset. The `-wal` files being
zero length and `-shm` present means a connection was opened and not cleanly
closed at some point, which is normal for these archives and not a defect.

The AAPL archive holds real acquired evidence: 71 `REGULATORY_FILING` rows from
SEC EDGAR, 20 vendor API rows, price and volume history, the four valuation
bands, and one persisted Investment Context. This is the practical starting
point for a single-company acceptance run.

Everything else in this inventory was re-measured on 2026-10-07 and is left as
recorded; only the `data/` claim was found to be wrong.
