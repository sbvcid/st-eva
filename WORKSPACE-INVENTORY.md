# WORKSPACE-INVENTORY

**Status:** read-only inventory. Nothing was moved, deleted, staged or committed.
**Scope:** `C:\git\st-eva` @ branch `master` @ `b124123`
**Date:** 2026-10-07

Purpose of this file: a permanent map so that future sessions do not have to
re-derive the workspace layout. It is a description, not an instruction to act.
Every disposition below is a *recommendation only*.

---

## A. Git state summary

| Category | Count | Command used |
| --- | --- | --- |
| **staged** | 0 | `git status --porcelain=v1 -uall` (no leading non-`?` column) |
| **modified tracked** | 0 | same (no ` M` / `M ` entries) |
| **deleted** | 0 | same (no ` D` / `D ` entries) |
| **untracked (files)** | **831** | `git status --porcelain=v1 -uall` (831 lines) |
| **tracked files** | 302 | `git ls-files` |
| **branch** | `master`, in sync with `origin/master` | `git status` |

Untracked breakdown (`-uall`, per file, not per collapsed directory):

| Untracked path | Files |
| --- | --- |
| `docs/ADR-HISTORICAL-PE-METHODOLOGY.md` | 1 |
| `experiments/aapl-historical-pe-poc/**` | 830 |

Note: plain `git status` collapses the experiments tree into a single line. The
831 figure comes from `-uall`. Do not trust the collapsed form for sizing work.

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
| `experiments/` | 889 | **1101.0 MB** | 0 | research | entire tree untracked |
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
two unrelated ones (`001`, `002`, untracked, small) and one large Historical P/E
programme (`aapl-historical-pe-poc`, 1101 MB, itself five sub-studies).

### C.1 `experiments/001-context-only`

| Field | Value |
| --- | --- |
| Files / size | 15 files, 1.9 MB |
| Purpose | Context-only experiment: feed 6 issuer context JSONs, produce per-issuer markdown. Validates whether context alone yields usable output. |
| Final artifact | Yes — `experiment_summary.md`, `self_audit.md`, `outputs/*.md` (6) |
| Regenerable | Partially. `outputs/*.md` come from `input/*.json` but no script is retained in this folder. |
| Raw evidence | Yes — `input/*.context.json` (6 files) |
| Verification | No |
| Long-term value | Medium. Documents an experiment whose conclusion is superseded by `002-cold-start`. |
| **Disposition** | **PRIVATE_ARCHIVE** — historical research record; keep out of the repo. Do not delete; the summary documents why context-only was insufficient. |

### C.2 `experiments/002-cold-start`

| Field | Value |
| --- | --- |
| Files / size | 44 files, 4.8 MB (13 of them `__pycache__`) |
| Purpose | Cold-start experiment: cross-source / provenance / derived-metric examination over 6 issuer contexts. Produced the lineage and evidence-model thinking that later became production modules. |
| Final artifact | Yes — `RESEARCH_REPORT_AND_SELF_AUDIT.md`, `analysis_summary.json`, `summary.txt`, `key_values.txt`, `crosssource*.txt`, `derived_detail.txt`, `val_dq.txt`, `provenance_refs.txt`, `full_structure.txt` |
| Regenerable | **Yes**, largely. 12 `.py` scripts are retained and read `contexts/*.json`, which are also retained. The `*.txt` outputs are regenerable by rerunning. |
| Raw evidence | Yes — `contexts/*.json` (6 files) |
| Verification | No formal verification artifact. `RESEARCH_REPORT_AND_SELF_AUDIT.md` is the self-audit. |
| Long-term value | High for provenance reasoning. Its conclusions are cited in production docs. |
| **Disposition** | **PRIVATE_ARCHIVE** — the scripts + contexts + final report are the record. The 13 `.pyc` files are pure disposable cache. |

### C.3 `experiments/aapl-historical-pe-poc` — sub-study breakdown

Total: **830 files, 1101.0 MB**, all untracked. Five sub-studies, in the order
they were executed.

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
| Path | `experiments/aapl-historical-pe-poc/contract/` (excluding `msft_validation/`) |
| Files / size | **1 file, 50.4 KB** |
| Purpose | The engine interface contract: `QuarterEpsEvidence` / `HistoricalPriceEvidence` / `HistoricalPeObservation`, resolver sequence E.0–E.8, invariants F-1…F-15, replay requirements I.1–I.4, OPEN decisions K.1–K.9, consistency review L.1–L.9. |
| Final artifact | **Yes — it is the artifact.** |
| Regenerable | **No.** This is a decision document. It is not derivable from any other file in the workspace. |
| Raw evidence | n/a |
| Verification | §L is an in-document consistency review against the ADR and both POCs. |
| Long-term value | **Highest of all.** It is the normative document an implementation is written against. §B.2.1 (Genericization Note, added 2026-10-07 from MSFT Finding C.1) is the only place the AAPL-layout parser hazard is stated. |
| **Disposition** | **KEEP_IN_REPO.** Exception to the rule that research goes to private archive: a contract is a governed artifact, not a POC result. It is the one thing here that a future implementer must be able to read. |

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
| 1 | `docs/ADR-HISTORICAL-PE-METHODOLOGY.md` | **KEEP_IN_REPO** | Frozen, approved methodology. Amended once (Amendment 1). A governed decision record. Currently the only untracked file in `docs/`. |
| 2 | `experiments/aapl-historical-pe-poc/contract/CONTRACT-HISTORICAL-PE.md` | **KEEP_IN_REPO** | The normative engine contract. Not regenerable. A future implementer must be able to read it from the repo. |
| 3 | Repo root production `*.py`, `web/`, `tests/` (non-cache), `docs/` (other 13), `reports/`, `history/`, `archive/` | **KEEP_IN_REPO** | Already tracked. No action. |
| 4 | `web/frontend/node_modules`, `web/frontend/dist`, all `__pycache__`, `.pytest_cache` | **REGENERABLE** | Build/tooling output. Already gitignored. Zero information content. Deleting costs only a reinstall/build. |
| 5 | `.kilo/worktrees` | **NEEDS_REVIEW** | 110 MB, 0 tracked, excluded via `.git/info/exclude` rather than `.gitignore`. Contains live managed sessions (`eastern-anglerfish`, `pepper-chess`). Deleting it would destroy in-flight work. Determine first whether either session is still active. |
| 6 | `experiments/aapl-historical-pe-poc/q4_study/` | **PRIVATE_ARCHIVE** | Primary-source evidence underpinning ADR Amendment 1. Never delete. Move to cold storage. |
| 7 | `experiments/aapl-historical-pe-poc/raw/`, `out/` (core POC) | **PRIVATE_ARCHIVE** | The 31/31 worked example the ADR and Contract cite. Never delete. |
| 8 | `experiments/aapl-historical-pe-poc/amendment1_verify/` | **PRIVATE_ARCHIVE** | Contains `negative_path_no_furnished.json`, the deterministic conformance artifact cited by Contract §I.3/§L.2. Never delete. |
| 9 | `experiments/001-context-only/` | **PRIVATE_ARCHIVE** | Superseded by 002 but documents why context-only failed. Keep. |
| 10 | `experiments/002-cold-start/` | **PRIVATE_ARCHIVE** | Provenance reasoning cited in production docs. Keep everything except `__pycache__`. |
| 11 | `experiments/.../contract/msft_validation/` | **NEEDS_REVIEW** | See §G.1. The 12 documentation files + 8 `out/` files are the finding and should be preserved; the 1011 MB raw set is a separate decision. |
| 12 | `experiments/002-cold-start/__pycache__/` (13 `.pyc`) | **DISPOSABLE** | Pure cache. Already gitignored. |
| 13 | `data/` (empty, tracked) | **KEEP_IN_REPO** | Empty tracked directory. Looks intentional. Not a leftover. |
| — | **Anything not classified above** | **NEEDS_REVIEW** | — |

---

## F. Important artifacts — must not be deleted by accident

Ordered by consequence of loss.

### F.1 Governing documents

| Artifact | Why |
| --- | --- |
| `docs/ADR-HISTORICAL-PE-METHODOLOGY.md` | Frozen methodology. Decisions 1–14. Every other artifact cites it. §6.1's Q4 evidence table is derived from `q4_study`. **Untracked — single copy, no git history.** |
| `experiments/aapl-historical-pe-poc/contract/CONTRACT-HISTORICAL-PE.md` | The engine contract. §B.2.1 is the only statement of the exhibit-layout genericization hazard. **Untracked — single copy, no git history.** |

Both of these are untracked. That is the single largest risk in this workspace:
they exist in exactly one place, are not in git history, and a `git clean` or a
worktree reset would destroy them without a trace.

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

### G.2 The two untracked single-copy documents

`docs/ADR-HISTORICAL-PE-METHODOLOGY.md` and
`experiments/aapl-historical-pe-poc/contract/CONTRACT-HISTORICAL-PE.md` are
untracked, unbacked, and are the two documents everything else defers to. This
is the highest-severity item in the inventory regardless of how any cleanup
proceeds. The Contract is also unbacked *and* sitting inside the untracked
1.1 GB tree, which means a naive "delete the experiments folder" would take it
with it.

### G.3 `.kilo/worktrees` — 110.6 MB

Two live managed sessions. Excluded via `.git/info/exclude`, so no repo-level
policy covers it. Determine whether either session is still active before any
action. This is out of scope for the archive question but it is 8% of the
workspace and it is invisible to `.gitignore`.

### G.4 `experiments/002-cold-start` — superseded status

Its conclusions were carried forward into production. Whether it is a reference
or a historical artifact is a judgement call, not a technical one. Flagged, not
decided.

### G.5 Unclassified files

`git status -uall` reports 831 untracked files; §C accounts for all 830 under
`experiments/` plus the 1 ADR. No orphans were found. But this inventory is a
snapshot of directory *structure* — individual file contents were not audited,
so a file that is structurally accounted for but semantically dead would not
show up here.

---

## H. Recommended one-time cleanup sequence

**This is a proposal. Nothing below was executed.**

The ordering matters: it front-loads the safety steps and pushes every
irreversible action to the end.

| Step | Action | Reversible? | Precondition |
| --- | --- | --- | --- |
| 0 | **Get the two governing documents under version control** (`git add` the ADR and the Contract explicitly, by path — never `git add .`) | Yes | none. Do this first. |
| 1 | Verify `git status -uall` count still reads 831 before touching anything | — | baseline |
| 2 | Confirm whether `.kilo/worktrees` sessions are live; leave alone if either is active | — | must resolve first |
| 3 | Resolve §G.1 (MSFT raw bulk). Compress-then-verify rather than delete-then-hope. | — | manifest coverage confirmed |
| 4 | Copy `experiments/**` to private archive storage, preserving paths. Verify file count and byte total before declaring success. | Yes, if verified | step 3 resolved |
| 5 | Only after step 4 verifies, remove the `experiments/` tree from the working copy. | **No** | step 4 verified |
| 6 | Delete `__pycache__`, `.pytest_cache`, `web/frontend/dist`. Leave `node_modules` unless disk pressure demands otherwise. | Yes (`npm ci`) | none |
| 7 | Final `git status -uall`; expected untracked count drops to 0 or near it. | — | — |

Two things this sequence deliberately does **not** do: it never runs `git add .`,
`git clean`, or `git reset`; and it never deletes from `experiments/` before a
verified copy exists elsewhere. Step 4's verification (file count + byte total
against §D) is what makes step 5 safe — skipping it turns step 5 into the
single most destructive action available in this workspace.

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
| contract | `experiments/*/contract/CONTRACT-*.md` — **exception, see below** | tracked |
| tests | `tests/` | tracked |
| report | `reports/` | tracked |
| archive | `archive/` | tracked |
| research | `experiments/**` (everything else) | **not** tracked |
| raw evidence | `experiments/**/raw/**` | **not** tracked |
| generated output | `experiments/**/out/**` | **not** tracked |
| cache | `__pycache__`, `.pytest_cache`, `web/frontend/dist` | ignored |

### The exception that must be written down

**A contract is governed, not experimental.** It lives under `experiments/` by
historical accident, but it is the document an implementation is written
against. Governing documents take precedence over the directory they happen to
sit in:

> If a file is an ADR, a contract, or a final report that another artifact
> cites, it is tracked **regardless of which directory it is in**, and it is
> never deleted as part of an experiment cleanup.

The inverse also holds, and it is the rule that would have prevented today's
situation:

> A cleanup that targets a directory never removes a file from that directory
> if that file is cited by a tracked document — unless the citation is updated
> first.

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

The rule is proposed, not applied. Applying it means: track the ADR and the
Contract, move everything else under `experiments/` to private archive, and
resolve §G.1 for the 1011 MB MSFT raw set. Steps 0 and 4 of §H.

---

*Inventory generated read-only. No file was moved, deleted, staged, committed,
reset or cleaned. No `.gitignore` was modified. No production code, ADR or
contract content was altered.*