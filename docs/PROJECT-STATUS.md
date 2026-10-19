# ST-EVA — Current Project Status

**Status checked:** 2026-10-17 (third round: unified historical P/E reference eligibility)
**Repository:** `sbvcid/st-eva`, branch `master`
**Current implementation baseline:** unified historical P/E reference eligibility round (`band_reference_eligibility` shared rule; unverified-count bands and ineligible distributions produce no matrix scenarios; MSFT web regression matrix 160→80) **+ traceable EPS anchor catalogue / reverse-valuation anchor** (`7b44618`; verified `backend` 2352 passed / 169 skipped / 498 subtests; `browser` run `39030611724` success — fixed by conditional `eps_ev` preserving legacy 14-field contract; new identity fields only when `anchor_id` set) on top of `965d5c1` (verified `backend` + `browser` in CI `39021861188`) (`fiscal_calendar.py` issuer-declared identity model + `a9a6630` fail-closed identity-conflict rules; MU FY2026 TTM verified; AAPL restored to 36/36) on top of the MU historical P/E + Q4 furnished evidence round (Q4 evidence dataset from 8-K Item 2.02 EX-99.1, corrected filing-acceptance timestamps, TTM window continuity guard) on top of `6c66550` (AAPL P/E and P/FCF baseline update after the quarter_number fix) on top of `10224e9` (quarter_number calculation fix + MU `eps_diluted_concept.json`) on top of `50043be` (declared SEC diluted-EPS evidence: period-declared GAAP facts from the run's own filing acquisition, cross-check only) with the archive-reconstruction-completeness fix; before that, the web path carrying the production historical P/FCF reference (`4797f1f`), MSFT cross-ticker validation (`37262ae`) with the MSFT P/FCF dataset and issuer config, AAPL v1 market-cap reconciliation `9ca6999`, AAPL v1 research snapshot `fe7d7c7`, historical P/FCF reconstruction `fd311c5`, consensus revisions/trend extraction `66611ec`, and the earlier R7 series, R6.x replay work, and first-use mode = live with expanded assumptions
**Latest verified GitHub Actions:** `1fc53ae` (fail-closed identity-conflict status record) verified `backend` and `browser` jobs success, backend run `39013776391` (checked via the GitHub API on 2026-10-17); `c972a05` (fiscal quarter identity round) verified `backend` and `browser` jobs success in run `39009039107`; `985ba22` verified in run `38971097167`; the earlier baseline `6c66550` in run `38955389118` (checked via the GitHub API on 2026-10-17). Each later commit is verified in its own run.


This is the live, changeable implementation/status record. The root [README](../README.md) contains the enduring product definition and rules. This file records what is implemented, wired, not wired, failing, or not yet verified. Historical files under `docs/archive/` are not current status or instructions.

## Continuation checkpoint — read this before planning or running work

This section is the hand-off checkpoint for future conversations and coding agents. Use the current status below; do not restart prior audits just because a new conversation begins.

**Completed and should not be repeated without a concrete reason**

- **Historical P/E reference eligibility is one rule across every matrix path (2026-10-17 third round).** `reverse_requirements.band_reference_eligibility` (positive median + declared non-negative integer sample count >= 20) is now the single gate: `exit_multiples_from_band` no longer turns an undeclared-count band into matrix scenarios (`OBSERVATION_COUNT_UNVERIFIED` refusal instead), `exit_multiples_from_production_distribution` no longer admits a distribution whose declared eligibility is not usable merely because its raw count clears the threshold (`INELIGIBLE_STATUS`), and `st_eva_runner.band_is_usable_for_reference` delegates to the same rule. Eligible distributions (`ELIGIBLE_PRODUCTION_DISTRIBUTION` / `ELIGIBLE_HISTORICAL_BAND`), descriptive-only historical data (explicit unavailable reasons, never scenario rows) and user multiples (`USER_SPECIFIED`, never labelled historical) stay three distinct kinds. Production P/E outputs unchanged for AAPL (36 obs, matrix 80), MSFT (24 obs; web matrix 160→80, the five unverified band rows dropped with the exclusion stated) and MU (454 obs). The CLI `run_regression_tests()` helper, which had been failing at `1fc53ae` because the fixtures' undeclared-count bands can no longer serve as the summary reference, now asserts the fail-closed state and the implied EPS from an explicit multiple. Do not reintroduce the "missing count is usable" band branch or a count-based override of the distribution's own eligibility status. See the section at the end of this file.
- **Fiscal quarter identity is issuer-declared, not a month grid (2026-10-17 second round, commit `c972a05`, CI run `39009039107`).** The month-grid fiscal_year_of/quarter_number mislabelled 11 of MU's 38 and 4 of AAPL's 42 quarter ends (52/53-week calendars drift quarter ends across month boundaries) and blocked MU's FY2026 TTM. `fiscal_calendar.py` derives identity from the issuer's own declarations (filing focus fields, prior-year comparatives, annual span positions), refuses unidentifiable periods, and both engines consume it; the TTM denominator is marked a derived sum with the audited annual carried beside it. MU snapshot now AVAILABLE (P/E 12.11171 on derived TTM EPS 74.21 vs audited 74.33, both preserved); AAPL P/E restored to 36/36 (median 28.44563, the pre-refactor value); MSFT unchanged. Do not re-derive the misclassification inventory or reintroduce month-grid identity. The `a9a6630` fail-closed round adds: equal-authority primary, comparative and annual-span declarations that disagree on a period's fiscal year/quarter leave the period unresolved (recorded in `FiscalCalendar.warnings`/`unresolved`) instead of being collapsed into an arbitrary pick; annual primary declarations still win over comparatives; production notes now surface unresolved quarter periods including cumulative-only span ends and annual identity conflicts. `tests/test_fiscal_calendar.py` now requires contradictory comparative/span, primary-conflict and annual-FY-conflict cases to stay unresolved. See the section at the end of this file.
- **MU historical P/E is live with furnished Q4 evidence (2026-10-17 round, commit `985ba22`, CI run `38971097167`).** The production distribution is `USABLE_FOR_REFERENCE` with 335 valid point-in-time TTM observations spanning 2019-03-21 to 2026-08-31 (median 21.549505; the 20-observation gate untouched), built from three tracked inputs: the new `data/historical_pe/MU/q4_evidence_records.json` (six fiscal Q4 GAAP diluted EPS facts directly stated in 8-K Item 2.02 EX-99.1 exhibits, FY2021–FY2026, furnished/unaudited provenance), the corrected `filing_acceptance_evidence.json` (true ET acceptance times; the previous values were submissions-API serializations that ran 4–5h late and mis-dated 65 usable dates), and the existing MU XBRL concept data. `build_historical_pe` now refuses position-filled windows whose period ends are not consecutive calendar quarters (`REASON_INSUFFICIENT_QUARTERS` with an explicit gap detail) — the month-grid quarter mapping can otherwise assemble a "TTM" that skips a real quarter for 52/53-week filers; this also corrected two pre-existing defective AAPL observations (2018-05-03, 2024-05-03; AAPL baselines recomputed: furnished 30→28, filed-only 18→14). The latest-date TTM snapshot stays `UNAVAILABLE` with `REASON_MISSING_Q4_EPS`: the furnished FQ4-26 fact (32.87, quarter ended 2026-09-03) is knowable, but the month-grid maps that fiscal year end to fiscal 2027 Q1, so the (2026, Q4) window slot stays empty — a fiscal-calendar method question deliberately not changed this round. See the section at the end of this file; do not re-derive the 8-K hunt or the acceptance-time offset finding.

- **Declared SEC diluted-EPS evidence is live** (`50043be`, verified by run `38862119614`). The reverse-requirements report carries `declared_eps_evidence`: the latest directly stated 10-K fiscal-year and 10-Q quarter facts of `us-gaap:EarningsPerShareDiluted` from the run's own SEC acquisition (packaged dataset as fallback), with declared period, accession/form/filed/acceptance time, GAAP concept and an explicit three-state status; per-scenario `related_sec_evidence` now prefers the run's acquisition with the frozen record shape unchanged. Cross-check evidence only — no calculation, admission, threshold, fingerprint input or network-envelope change. See the section at the end of this file for the case evidence; do not re-derive the "the vendor anchor has no declared period or basis" finding again.
- **Archive reconstruction completeness for the consensus sample is fixed** (on top of `2293a70`). The archive's own contract — stated in `archive.py`, `_build_context_if_requested` and `_archive_run`: "a snapshot that references facts the archive never saw cannot be replayed" — requires every observation a context registers to be archived. The live path registered the 17 consensus observations (analyst count, low/high range, revision counts, trend series, in-series differences) into the context via `extra_observations` but returned only the second-source observations for archival, so a consensus-bearing snapshot referenced 17 un-archived observations and its replay reported `DIVERGED`. `st_eva_runner.py` now selects the consensus sample with the shared `consensus_sample_observations(...)` helper, returns it for archival, and registers it on the rebuild path too. Verified with the real saved AAPL/MSFT/MU contexts (`tests/test_consensus_archive_completeness.py`, 13 tests / 43 subtests): a consensus-bearing run archives every referenced observation and replays to `MATCH` with the same `context_id`; evidence_ids keep their order and count. The AAPL/MSFT archived contexts that still report `DIVERGED` do so because the code changed after archival (new glossary/derived entries), which is the legitimate case the reason string names — do not force those to `MATCH`. The real archives under `data/archives` were read-only checked (`PRAGMA integrity_check` = ok) and were not rebuilt, deleted or overwritten. See `history/archive_reconstruction_completeness_20261016_report.md`.
- **P0 CI contract repair is complete** at commit `cb5ab8c`, and restored after sync regression. The 4 backend failures seen in run `38141809016` (reintroduced in `661e0df`) were fixed by restoring the verified `cb5ab8c` contracts in `investment_context.py` and correcting `.gitignore`. Local test results: full backend suite 1,897 passed, 168 skipped, 140 subtests passed; targeted tests 4 passed; archive-isolation 6 passed; web API 15 passed; frontend build passed.
- Persistent local SQLite files were SHA-256 checked before and after the test runs; the reported hashes were unchanged. Do not rerun this audit unless a subsequent task touches database persistence or tests.
- The archive was inventoried and semantically reviewed in the completed local Phase 1/2 audit. The durable outcome is recorded in this status file: **zero archive content integrated**. Do not repeat the broad inventory or Phase 2 review unless a specific product gap points to a particular archive item; deleting local audit outputs does not invalidate this decision.
- The existing reverse-requirements engine is not a blank slate: `reverse_requirements.py` has formula version `1.1`; the reported AAPL artifact `data/historical_pe/AAPL/reverse_requirements_output.json` contains 27 scenarios. This proves an output artifact exists, not that the browser path is complete. Do not regenerate the artifact or repeat a broad formula audit just to re-establish that the matrix exists.
- The AAPL reverse requirements output `data/historical_pe/AAPL/reverse_requirements_output.json` is safely ignored via `.gitignore` and backed up outside the repository at `C:\st-eva-audit\archive-output-backup`; do not track or delete it.
- **R1 Reverse-requirements matrix API & Frontend wiring is complete** (formula version `reverse-requirements/1.1`):
  - Web API response now provides a strongly-typed `reverse_requirements` report (`ReverseRequirementsReportDTO`), containing `formula_version`, `status`, `start_anchor`, and the full cross-product `scenarios` (`EpsScenarioDTO`).
  - Assumption inputs (reference multiples, holding horizons, required returns, EPS anchor basis preference, user-specified EPS override, and explicit mode selection) are accepted by `AnalyzeRequest`, passed via `JobManager` and `AnalysisServiceAdapter` to `run_st_eva()`, and reflectively computed by the engine.
  - Frontend UI in `App.tsx` exposes assumption controls (collapsible configuration panel), forwards user inputs, and displays the full matrix via `<ReverseRequirementsMatrix>` with horizon/return filtering, uncomputable badges/reasons, and drawer notes.
  - Regression mode is no longer secretly forced for MSFT/0700.HK without notice; explicit mode controls are available and when regression fixture data is detected, a prominent "REGRESSION FIXTURE (TEST DATA)" warning banner prevents test fixtures from being mistaken for live quotes.
  - Uncomputable scenarios and matrix states (e.g. non-positive EPS anchor, window < 0.5 yrs) are explicitly represented with structured reason codes/messages, never zero-filled or hidden.
  - Verified when R1 landed with 20 web API tests, 44 wiring tests, 6 archive isolation tests, 24 Vitest frontend unit tests, 7 browser smoke tests, and the full backend suite (1,897 passed, 168 skipped, 140 subtests). The R3 section records the counts the same suites report now.
- **R3 Real AAPL end-to-end acceptance is complete** (2026-10-11, live acquisition, no fixture data):
  - The full matrix, assumption controls, row-level calculation traces and provenance drawer were exercised through the **real web application path** (FastAPI app + built frontend in headless Chromium), ticker `AAPL`, **explicitly selected mode `live`** (never `auto`, never `regression`), with an isolated temporary archive directory.
  - Two submissions were made with different assumption sets and both requests, responses and rendered drawers were verified; see the R3 section below for the exact payloads, values and recomputations.
  - `tests/test_r3_live_aapl_acceptance.py` is the reproducible acceptance harness (gated by `ST_EVA_R3_LIVE=1`; optional evidence record via `ST_EVA_R3_EVIDENCE`), so this acceptance can be re-run rather than only remembered.
- **R2 Reverse scenario provenance and reproducibility is complete** (formula version `reverse-requirements/1.1`):
  - Row-level evidence contract defined and strongly typed in `web/schemas.py` and `web/frontend/src/types/api.ts` with `SecFactDTO`, `RelatedSecEvidenceDTO`, `MarketPriceEvidenceDTO`, `EpsAnchorEvidenceDTO`, `ExitMultipleEvidenceDTO`, `CalculationStepDTO`, and `ScenarioEvidenceDTO` attached to each `EpsScenarioDTO`.
  - Pure calculation engine in `reverse_requirements.py` generates deterministic 4-step execution traces (`build_scenario_calculation_steps()`): (1) Required Exit Price $P_T = P_0 \cdot (1 + r)^T$, (2) Required Terminal EPS $EPS_T = P_T / PE_{\text{exit}}$, (3) Total EPS Growth $\Delta EPS = (EPS_T - EPS_0) / EPS_0$, (4) Required EPS CAGR $g = (EPS_T / EPS_0)^{1 / t_{\text{growth}}} - 1$ or explicit uncomputable reason, verifying reproducibility within $10^{-4}$ tolerance.
  - Strict source-binding rule enforced (R2.1, corrected): a selected EPS anchor receives direct SEC filing metadata (`sec_fact`) only when the acquisition data structures establish that the exact observation supplying the engine's input field is one of this run's acquired regulatory-filing observations (metric/concept, unit, period, accession, form/filed), with the value used only as a confirming compatibility check on the record identity already identifies. Numerical equality never selects a record, and the existence of filings for a ticker proves nothing about a value's origin. Vendor forward/consensus EPS and unrelated historical 10-K records no longer inherit SEC source attribution.
  - Related/cross-check SEC filing evidence (`sec_related_evidence` / `related_sec_evidence`) is kept separate from direct provenance, labeled as cross-check, and never presented as the direct source of a selected EPS value.
  - When direct provenance cannot be established, the API and UI expose the limitation explicitly (`missing_or_unvalidated`: "Direct SEC source of selected EPS not established", with "; related filing shown for cross-check only" when related evidence exists) without hiding the EPS value or inventing a source.
  - User-supplied EPS (`is_user_assumption=True`, `source_type="USER_SUPPLIED"`) carries no SEC source attribution and retains explicit user-supply labeling.
  - Source evidence cards distinguish: (a) actual source of selected EPS (declared provider, plus the linked filing fact only when the input-to-fact linkage is proven), (b) related SEC filing evidence (cross-check only), (c) user-supplied assumptions, and (d) missing/unverified provenance. No "verified SEC source" label is used unless the linkage is established.
  - Service adapter hardened: DTO validation failures raise explicit exceptions and fail the job rather than being silently swallowed (`tests/test_web_api.py::TestAnalysisServiceAdapter::test_dto_validation_failure_raises_explicit_error_and_fails_job`).
  - First R2.1 attempt (`78f387a`) is rejected as acceptance evidence: its resolver still resolved `sec_fact` by value search (first observation with an accession, or the latest annual concept-file entry), so a vendor figure equal to a historical filing figure still displayed a 10-K as its source; and it referenced `evidence.related_sec_evidence` in the frontend without the `ScenarioEvidenceDTO.related_sec_evidence` field in the TypeScript contract or the pydantic DTO, so CI run `38155972302` failed both jobs at "Build frontend". Both defects are corrected below.
  - Local verification results after the correction: full backend suite passed (1,958 passed, 168 skipped, 140 subtests passed in 348.69s); provenance regression suite 20 passed; wiring suite 49 passed; web API 22 passed; Playwright browser smoke 8 passed; Vitest frontend 27 passed; production frontend build passed (`dist/index.html` produced). Persistent SQLite files and AAPL reverse requirements artifact verified intact; no DB reset, recreation, or overwrite performed.
- **R5 Result-semantics, summary reconciliation and audit export is complete** (2026-10-12; see the R5 section below): the summary cards are relabelled with their exact single-point/flat-multiple basis and a `selected_pe_basis`/`summary_horizon_years` basis that is distinct from the return-hurdled matrix rows, and the results interface exports the same typed report currently displayed as versioned JSON and a full one-row-per-scenario CSV (preserving the full matrix, nested evidence, calculation traces, R2.1 direct-vs-cross-check provenance, distinct exit-multiple eligibility and all unavailable states, with `raw_analysis` omitted by default). No calculation, formula version, acquisition source or second engine changed. This retires the last R1 backlog item; do not rebuild it.
- **R6 point-in-time replay DIVERGENCE is diagnosed and the demonstrated defect corrected** (2026-10-12; see the R6 section below): the live AAPL `DIVERGED` had two causes -- a replay *cutoff/eligibility mismatch* (the web path replayed at the data date, before the archival watermark of the archive-first-seen vendor fundamentals, so a faithful rebuild was wrongly `DIVERGED`) and a *genuine unresolved input difference* (a user reference multiple is not archived knowledge, so reference-conditioned figures cannot be reconstructed). The web replay now replays at the asset's `archival_watermark` so the same eligible observation set is rebuilt (`MATCH` when faithful); `archive.replay`, eligibility, hashes and the formula are unchanged. A reference-conditioned context (including both R3 live submissions) still reports `DIVERGED` honestly -- do not force it to `MATCH`.
- **R6.1 replay snapshot identity is verified and corrected** (2026-10-12; see the R6.1 section below): when one asset carries several contexts for the same `as_of`, `replay` selected the *earliest* snapshot via `context_at`, producing a false `MATCH` (a ref-32 run matching an older ref-free snapshot) and a false `DIVERGED` (a ref-free run failing against an older ref-32 snapshot). `replay` now takes the snapshot identity and the web path reconciles each run against *its own* archived context (identified from the written context artifact, not by widening the engine result, which is a CLI-output invariant); an absent identity reports `NO_SNAPSHOT` rather than substituting. Default `as_of` selection and strict-HISTORICAL behaviour are unchanged. Do not widen the engine result dict or the result dict's CLI output to carry context identity.
- **AAPL first-version product acceptance passed** (2026-10-12; see the acceptance section below): exercised through the real HTTP API and real Chromium with `mode=live` and isolated temporary archives (no fixtures); matrix arithmetic recomputes to zero error, references/provenance/unavailable states and replay semantics are correct, and JSON/CSV exports match the displayed result including a subsequent request. No product blocker and no code change. Do not re-run this broad live acceptance for routine work; the R1–R6.1 regression suites plus the latest CI are the standing guard.
- **First-use execution mode and assumption discoverability corrected** (2026-10-12; see the section below): the web settings drawer starts expanded, the default mode is `live` (not `auto`, which silently resolved MSFT/TENCENT/NU to static regression fixtures), and reset restores `live`; `auto` and `regression` remain explicit options, a data-source hint and an always-visible data-source badge explain the mode's effect, and explicit `live` still reports acquisition failure visibly (the backend already never falls back to fixtures in live mode). Frontend only; formulas, `reverse-requirements/1.1`, backend/CLI mode defaults, export schemas and persistent data are unchanged.
- **R7-6 Starting EPS period basis explicit in UI and CSV** (2026-10-13, commit `c112e18`): the matrix audit drawer now displays `period_label`, `period_start`, `period_end`, and explicitly discloses when `period_undeclared_by_source` is true with localized warning text. Four new CSV columns (`start_eps_period_label`, `start_eps_period_undeclared`, `start_eps_period_start`, `start_eps_period_end`) populate from the scenario evidence. No formulas or EPS values changed.
- **R7-7 Dividend & total-return comparison exposed in UI** (2026-10-13, commit `a074494`): the dividend section displays dividend per share with correct currency (uses `dividend_currency` with fallback to `currency` prop), conditional TTM period label (only shown when `dividend_period` is provided), source, conventions with formulas, and a price-vs-total-return comparison table. Reading notes corrected to state that the baseline matrix is strictly price-return-only and dividend scenarios are parallel computations. Non-USD currency display verified (EUR, GBP fallback).
- **EPS anchor catalogue / reverse-valuation anchor (2026-10-17, this work, building on verified `965d5c1` / CI `39021861188`).** `eps_anchor_evidence.py` defines distinguishable anchors (`SUPPLIER_TRAILING_EPS`, `SUPPLIER_FORWARD_EPS`, `SUPPLIER_CONSENSUS_FORWARD_EPS`, `SEC_ANNUAL_DILUTED_EPS`, `SEC_TTM_FOUR_QUARTERS`) with source identity, point-in-time knowability, annual-vs-derived distinction, derived-sum marking, and refusal-with-specific-reason (no silent substitution, including `UNKNOWN_EPS_ANCHOR_ID`). Integrated through `build_eps_anchor_candidates` / `select_anchor` / `candidate_to_eps_anchor` into `_build_reverse_requirements` (`st_eva_runner.py`) and `build_scenario_evidence` / `build_reverse_requirements_report` (`reverse_requirements.py`). Web DTO (`web/schemas.py`), TypeScript (`web/frontend/src/types/api.ts`), matrix audit component (`ReverseRequirementsMatrix.tsx`), assumption select (`App.tsx`), and i18n (`en.ts`/`zhTW.ts`/`types.ts`) updated. AAPL end-to-end verified (annual 7.46 FY2025 10-K accession vs derived 8.72 four-quarter sum, windows not confused; unavailable states preserved); MSFT/MU regression verified (annual 17.95 vs derived 17.96 with 0.01 basis difference preserved, not reconciled); `tests/test_eps_anchor_evidence.py` 11 passed; `evidence_valuation_boundary.py` unchanged (EPS path is separately tested, no general SEC-metric admission). See `eps_anchor_evidence.py` docstring for rules (point-in-time, enough evidence or nothing, numerical agreement is not provenance, no reconciliation by adjustment).

**Outstanding but intentionally not complete**

- The production point-in-time historical P/E reference is available on the web path only for the two configured issuers, ``AAPL`` and ``MSFT``. Any other ticker is reported as ``UNAVAILABLE`` with an explicit reason rather than being given a fabricated distribution.
- The distribution is evaluated on periodic SEC filing and earnings-release usable dates, so it is not a continuous daily history, and it does not extend past the frozen dataset's last evaluation date. Both are stated in the report.
- No second historical P/E engine and no broad caching or ingestion framework was added, and no new network acquisition was introduced to reach any source.
- The archive has **not** been deleted or cleaned. The integration decision lists about 1.3–1.5 GB as `NO_LONGER_NEEDED` and about 0.8–1.0 GB as `REVIEW_REQUIRED`; these are planning classifications, not proof that files were deleted. Cleanup is a separate bounded task and must not block product development.

**Next task status**

The EPS anchor catalogue integration is complete (verified with packaged AAPL/MSFT/MU datasets, runner smoke tests, 11 new evidence tests, existing regression suites 140 + 54 passed, frontend TSC OK, web DTO validated). There is no open product defect demonstrated by the current work; archive cleanup and broader ingestion remain deferred, non-blocking maintenance per the existing decision.

Archive cleanup remains **deferred, non-blocking maintenance, not a prerequisite for product development.** It is planning only (about 1.3–1.5 GB classified `NO_LONGER_NEEDED` and about 0.8–1.0 GB `REVIEW_REQUIRED` from the Phase 1/2 audit); it is a separate bounded task that must preserve anything unclear outside the repository with its SHA-256 and must not block product work. Preserving the existing SQLite files, the AAPL reverse-requirements artifact and the production P/E datasets is mandatory regardless.

The generic replay `DIVERGED` explanation wording is a **minor usability observation, not a current blocker.** Revisit it only if user testing demonstrates actual confusion.

**Execution rule**

Before running tests, compare the working tree and task diff with this checkpoint. Run targeted tests first; run the full suite when the code change warrants it and record the actual result. Mark an item complete only when its acceptance evidence exists. Update this file rather than creating another status/roadmap document.

**Mandatory Agent task-closure rule — no user cleanup queue**

Every coding-agent run must end with a clean working tree. Do not leave modified, staged, or untracked files for the user to inspect or decide what to do with.

1. **Start with a baseline:** record `git status --short --branch`, current HEAD and upstream before edits. Include untracked files. Do not assume generated files are disposable or that pre-existing files belong to the current task.
2. **Resolve pre-existing dirt first:** identify each modified/untracked path and whether it is product source, a required test/fixture, a reproducible local output, runtime/user data, or unknown. Finish and commit valid prior work; track required product/test assets; put reproducible local outputs under an appropriate committed ignore rule; remove an output only after proving it is disposable/reproducible. If an item is unclear, preserve it outside the repository with its original relative path and SHA-256, and record the preservation location in the task report before cleaning the working tree. Never silently discard user-authored work.
3. **Do not use destructive shortcuts:** no `git reset --hard`, `git clean -fdx`, blind checkout/restore of dirty files, or broad deletion just to make status clean. Never delete or reset runtime SQLite databases or their WAL/SHM files as housekeeping.
4. **Close the task completely:** run relevant tests/builds, inspect `git diff`, run `git diff --check`, update this status file if acceptance state changed, commit the complete intended change, and push to the current intended branch. Do not commit secrets, local databases, cache/build output or incidental generated files merely to clear status.
5. **Verify the result:** run `git status --porcelain=v1 --untracked-files=all` and require empty output; verify `git status -sb` shows the intended branch in sync with its upstream. Confirm the commit hash and push result. Verify again after tests, since tests may generate files.
6. **Final response format:** report commit hash, push status, working-tree-clean confirmation, tests/builds and any generated artifacts safely handled. Do not ask the user to analyze leftover files. If remote push itself fails, the local worktree must still be clean and the push failure must be stated clearly.

A run is not complete just because tests pass or a commit exists. The clean-tree and artifact-disposition checks above are acceptance requirements for every task.

## 1. Product direction used for this status review

**The only product centre is reverse valuation. Every other capability exists only insofar as it helps produce better reverse-valuation numbers, input evidence, reproducibility, or inspection.** ST-EVA produces data and deterministic calculations, not business analysis or investment conclusions.

The required experience is: enter a ticker; obtain an observed price and usable financial inputs; inspect/select assumptions; view the reverse-requirements matrix; and trace each result back to the input, source, period, units/currency and formula. Given the same complete inputs, assumption set, and formula version, deterministic calculation code must produce the same number. Different input data or assumptions can correctly produce different numbers. Determinism does not prove that a source claim is true, and a conditional calculation does not forecast that the company will deliver it.

No report generator, LLM integration, general-purpose research archive, registry, or data-ingestion framework is an independent product goal. They are supporting implementation only. A module that exists but does not help the user obtain or verify the reverse-valuation output is not proof that the product is complete.

## 2. Repository and reviewed scope

The GitHub tree at the current documentation update contains approximately 467 entries, 173 Python files, and 79 Python test files. The repository has a large collection of engine, evidence, SEC, archive, research-output, and experiment modules. This scale indicates a substantial implementation surface, not a completed user-facing product.

This status review inspected the live code paths and relevant contracts around:

- `web/frontend/src/App.tsx`, `ResultCards.tsx`, `EvidenceAccordion.tsx`, API types and client.
- `web/app.py`, `web/schemas.py`, `web/service_adapter.py`, and the job manager.
- `st_eva_runner.py`, `reverse_requirements.py`, `data_contract.py`, and the source/validation adapters.
- `investment_context.py`, `operation_registry.py`, `evidence_valuation_boundary.py`, `sqlite_archive.py`, `archive.py`, and `sec_ingest.py`.
- `historical_pe.py`, the versioned AAPL/MSFT historical P/E inputs, dividend/financial-history/capital-structure modules, relevant tests, and GitHub Actions logs.

This is a product-path audit, not a claim that every one of the repository's 467 tree entries has been individually reviewed. The findings below distinguish code existence from runtime wiring and user-visible availability.

## 3. Actual runtime paths

### CLI path

The CLI in `st_eva_runner.py` accepts a ticker and modes `auto`, `live`, or `regression`. It orchestrates acquisition, observation/evidence construction, validation/comparison, the summary analysis, and the reverse-requirements report. CLI options include an explicit P/E reference, multiple P/E assumptions, holding-period scenarios, required-return scenarios, optional P/FCF, EV/EBITDA and P/S assumptions, risk-free rates, optional financial history and historical P/E, optional Dossier/Investment Context output, optional archive persistence, and snapshot control.

The detailed reverse-requirements report is returned in the run result under `reverse_requirements`. It includes a formula version, a fingerprint of calculation inputs, the observed price/as-of data, a matrix of scenarios and supporting blocks where the inputs permit computation. An unavailable input can prevent the matrix from being computed; this should be reported explicitly, not replaced with a fabricated result.

### Web path

The current intended request path is:

```
Browser App.tsx
  -> POST /api/analyze
  -> JobManager
  -> AnalysisServiceAdapter.run_analysis_pipeline()
  -> run_st_eva()
  -> per-ticker SQLite archive + temporary Investment Context JSON
  -> replay attempt
  -> AnalysisResultDTO
  -> summary cards / evidence accordion
```

The adapter opens or creates a per-ticker archive under `data/archives/`, seeds the metric registry if needed, calls `run_st_eva()`, requests an Investment Context file, disables the ordinary runner snapshot (`save_snapshot=False`), reads admission/refusal summaries, attempts replay when an as-of date is available, and maps the core result into a web DTO.

The web API accepts `reference_multiple`, `reference_multiples`, `reverse_horizons`, `required_returns`, `user_eps` and `prefer_eps_anchor` in `AnalyzeRequest`, and the backend adapter forwards these fields to `run_st_eva()`. `App.tsx` exposes the corresponding assumption controls and forwards them on each analysis request, so the browser path is wired to the same assumption surface as the CLI.

## 4. Reverse-valuation calculation layer

### Full reverse-requirements engine — implemented as a Python capability

`reverse_requirements.py` contains pure deterministic calculation functions for scenario matrices. A scenario can encode:

- Observed starting share price and as-of information.
- A holding period.
- A required return.
- An exit/reference multiple, with source/sample metadata when available.
- An explicit starting EPS anchor (trailing, forward/NTM, fiscal year, or user-supplied) and the period that EPS covers.
- The resulting required terminal price, terminal EPS under the exit multiple, and required EPS growth when the defined growth window is computable.
- An explicit price-return or dividend-return convention where the relevant dividend inputs are available.
- Formula version and fingerprint/contract metadata.

The code distinguishes price return from total return; it does not silently treat a required price return as a total-return hurdle. EPS coverage matters to CAGR: a forward EPS anchor is not treated as trailing EPS at the valuation date, and a growth window that is too short is reported as not computable. These are important calculation semantics that should be retained and surfaced, not rewritten for presentation convenience.

The report also has calculation blocks for P/FCF, EV/EBITDA and P/S requirements, risk-free/cost-of-equity inputs, DCF feasibility/input gaps, dividend scenarios, and cash-flow cross-checks. Their presence does not imply that every path has adequate sourced inputs, has passed a complete issuer-by-issuer verification, or is exposed in the browser. DCF-related output is not a fair-value conclusion or price target.

### Older summary engine — currently a separate semantic path

The summary analysis in `st_eva_runner.py` exposes values such as `forward_eps_at_reference_multiple`, consensus EPS gap, and `required_eps_cagr_from_current_eps`. The simple implied EPS at a selected P/E is price divided by that multiple. Its summary CAGR is not equivalent to the full reverse-matrix CAGR because it does not encode the same combined scenario of required return, holding period, exit multiple, and EPS-anchor coverage.

This is a confirmed semantic ambiguity at the public-output level. The two calculations must either be clearly named and presented as different outputs or the summary field must be changed so that it cannot be mistaken for a full reverse-requirements row. Do not describe either number as a forecast.

### Missing product-level calculation contract

There is not yet a single, end-to-end web contract that binds each displayed scenario to its complete user-specified assumptions, actual inputs, formula/version and source lineage. The pure calculation layer is more complete than the browser experience and more complete than its trace integration.

## 5. Browser experience and API — current gaps

The current browser page has ticker input and quick examples, online/offline messaging and PWA install handling, progress display, summary valuation cards, admission/replay status and an expandable evidence accordion.

The result cards currently show a small set of headline values: market price, implied forward EPS at the selected reference, required EPS CAGR, reference P/E, and supporting observed multiples/limitations. The accordion displays source identifiers, evidence-contract IDs and a discrepancy-status field where present. It does not show the detailed inputs and formulas required to independently recompute a reverse scenario.

Confirmed gaps and R1/R2 status:

1. **[RESOLVED in R1] Full reverse-requirements matrix in the UI.** The browser now renders the complete typed `reverse_requirements` matrix scenarios table with horizon and return filters, anchor metadata, formula version, and uncomputable badges/reasons.
2. **[RESOLVED in R1] Complete scenario controls.** The browser now provides assumption controls for reference multiples, horizons, required returns, EPS anchor basis preference, and EPS overrides, forwarded via `AnalyzeRequest` to the runner.
3. **[RESOLVED in R1] Misleading regression-mode branch resolved.** Automatic hidden switching to regression mode was removed; explicit mode selection is supported, and a prominent test fixture banner is displayed when regression data is shown.
4. **[RESOLVED in R2] Scenario-level provenance & calculation audit drawer.** Each matrix scenario row expands to display an audit trail drawer containing:
   - Reproducibility verification status (within $10^{-4}$ tolerance).
   - 4-step deterministic formula traces ($P_T$, $EPS_T$, $\Delta EPS$, $g$) with exact operands, formulas, and results.
   - Sourced facts (market price observation ID, starting EPS anchor with provider identity, and SEC XBRL accession/filing date/concept metadata only when the input-to-fact linkage is established), exit multiple sample count and eligibility status.
   - Clear distinction between user assumptions, sourced facts (labelled by the source the value actually came from, including a filing reference only when the input-to-fact linkage is proven), and data limitations/refusals.
5. **Summary labels conceal different computations.** While the full matrix now clearly separates scenario exit price and CAGR requirements from summary cards, unified terminology and deep row reconciliation remain an ongoing refinement.
6. **[RESOLVED in R1 & R2] First-class response contract.** `ReverseRequirementsReportDTO`, `EpsScenarioDTO`, `EpsAnchorDTO`, `ReferenceMultipleDTO`, `CalculationStepDTO`, and `ScenarioEvidenceDTO` are strongly typed in `web/schemas.py` and `web/frontend/src/types/api.ts`. Service adapter hardened to raise explicit exceptions on DTO validation failures.
7. **Progress/status wording leads with process infrastructure.** Acquisition, admission and replay can help explain data states, but the main user result must be the conditional financial requirements implied by the price.

The web path now provides the complete first-class reverse-requirements matrix calculation, scenario display, and row-level mathematical and source provenance audit drawer.

## 6. Input acquisition, definitions and validation

### Available source/data foundations

- `fundamental_provider.py` obtains market/fundamental observations from the Yahoo-facing path used by the current runner.
- `sec_provider.py`, `sec_ingest.py`, `sec_xbrl_facts.py`, `sec_provenance.py`, and `sec_bulk.py` support SEC filing/fact acquisition and processing.
- `data_contract.py` defines semantic metrics, units, observation identity, currencies/bases, availability, evidence/validation structures and unavailable states.
- `cross_validation.py` compares source observations using declared period/basis/methodology compatibility. It does not average or silently choose a winning source.
- `core_registry.py`, `registry_seed.py`, `issuer_identity.py`, `registry_identity.py` and related resolver/knowledge-axis modules define the mapping from source concepts to semantic metrics and preserve identity/lineage.
- `financial_history.py`, `capital_structure.py`, `dividend_history.py`, and `risk_free_rate_provider.py` provide supporting calculations or input acquisition when invoked and when adequate inputs are available.

These modules support reverse valuation only to the extent the live run actually acquires their facts, maps them compatibly, makes them eligible as inputs, and passes the resulting values to the relevant calculation. Code coverage or registry size is not proof that the web product has those inputs.

### Archived SEC evidence boundary

`evidence_valuation_boundary.py` governs crossing archived SEC observations into the current reverse-valuation input surface. Its documented V1 crossing admits `revenue`; other filing metrics may be stored and evaluated by the evidence layer but are refused at this specific crossing. The source ingestion/registry coverage is therefore broader than what the archived SEC admission boundary currently lets the engine consume. This is not a claim that every other metric is unavailable from the separate live vendor path.

This boundary is a major wiring/coverage limitation for the goal of having sufficiently sourced fundamentals to support the reverse calculations. Do not expand evidence infrastructure in the abstract; identify which actual reverse-valuation inputs are needed, then verify their metric mapping, admission and calculation use.

### Source truth, missingness and comparability

The intended code/data distinction is: accurately preserve what a source reported and where it came from; validate comparability separately; derive numbers only from declared compatible operands. A fact being faithfully sourced does not certify its economic/accounting truth. Missing, unavailable, stale, conflicting, unvalidated or non-comparable observations must remain separately represented and never be silently substituted with zero or with another source's value.

The P0 discrepancies between Engine and Investment Context for missing derivations and a user-supplied reference were fixed at `cb5ab8c` and verified locally and by GitHub Actions. Do not treat those resolved failures as current defects.

## 7. Historical P/E reference data

`historical_pe.py` implements a production-oriented point-in-time historical P/E pipeline. Its code enforces specific requirements including source-usable timestamps, a 16:00 ET evaluation cutoff, four consecutive fiscal quarters including a directly stated Q4, no FY-minus-YTD synthetic EPS, GAAP diluted EPS consistency, explicit filed versus furnished evidence classes, point-in-time restatement treatment, EPS/price accounting-basis agreement, explicit exclusion of CURRENT_PE from historical windows/distributions, and determinism/content hashes.

The repository's configured historical P/E issuer inputs currently include AAPL and MSFT under `data/historical_pe/`. The production distribution uses a minimum of 20 qualifying observations for reference eligibility; a thinner sample may still be displayed descriptively but should not be used as a qualifying exit/reference distribution.

Two implementation gaps remain relevant to the actual product:

- CLI: the production historical P/E path is opt-in via ``--historical-pe``. **The web path now passes it**: ``web/service_adapter.py`` calls ``run_st_eva(..., include_historical_pe=True)``, so the default browser analysis *does* use the dedicated daily point-in-time reconstruction. (An earlier version of this section said the web adapter did not pass the option; that statement is superseded. See the R4 historical-P/E record above for the wiring and its tests.)
- The code review found inconsistent eligibility handling between reference selection helpers: the historical-median helper checks usable sample count, while the matrix's historical-band conversion can accept a band whose observation count is undeclared. A test fixture currently permits that missing-count case. Production eligibility should have one consistent rule; descriptive historical data and usable scenario references are distinct statuses.

## 8. Investment Context, lineage and snapshot persistence

`investment_context.py` packages observations, provenance references, validation states, formula/operation references, unavailable states and derived figures into a machine-readable contract. `operation_registry.py` holds registered deterministic operations. This is useful supporting infrastructure because it can let a consumer inspect/recompute data without the consumer having to import the runner.

Integration status after R1 & R2:

- `run_st_eva()` places the full matrix in `result["reverse_requirements"]`.
- `AnalysisResultDTO` maps the complete `ReverseRequirementsReportDTO`, including starting EPS anchor metadata, scenario cross-product, deterministic calculation steps, and source/audit evidence.
- The web browser renders the full matrix and provides an expandable audit trail drawer for each scenario row showing mathematical verification ($10^{-4}$ tolerance), 4-step calculation traces, and sourced vs user-assumed input evidence.
- Full snapshot/Context serialization of row-by-row scenario traces into historical archives remains an available persistence enhancement for future export/replay flows.

## 9. SQLite archives, replay and data protection

There are multiple persistence concepts; do not conflate them:

- CLI `--archive [PATH]` opts into the configured SQLite archive; when the path is omitted, the documented default is `data/st-eva.sqlite`.
- The web adapter creates/opens per-ticker databases under `data/archives/{TICKER}.sqlite` and seeds the registry baseline when necessary.
- The adapter writes/requests a temporary `{TICKER}.context.json` alongside the per-ticker archive, persists archive records, and attempts point-in-time replay when an as-of date exists.
- The regular CLI runner also has JSON snapshot output under `history/` unless snapshots are disabled; the web adapter disables that snapshot output.

`sqlite_archive.py` and migrations implement append-oriented observations, captured source documents, validation/admission records and archive queries. The replay path should rebuild from observations eligible at the requested cutoff and report MATCH, DIVERGED, NO_SNAPSHOT or INSUFFICIENT/other explicit failures as applicable. It must never fill a missing historical input with a newer value merely to make the result look complete. Source-declared availability and archive-first-seen availability are not the same fidelity claim.

**Persistent runtime databases are user data. Do not delete, reset, recreate or overwrite `data/st-eva.sqlite` or any existing `data/archives/*.sqlite` file as a cleanup, migration, test setup or implementation shortcut.** Inspect the existing files read-only before any planned change, preserve backups and row contents, and use explicit temporary directories/databases for tests. The SQLite files may be absent from the public Git tree and their current local bytes are not inspectable via the GitHub source view; their absence from GitHub is not evidence that the local files are disposable.

A policy question remains open for the canonical dataset boundary: the user's intended principle is that only admitted, validated facts should enter the canonical active valuation input set, while lower-quality/refused material remains explicitly held out. The present archive code can persist observations and admission/validation decisions, including refused records, so do not claim that the archive itself is a filtered-only canonical dataset without verifying the read/admission boundary and the local database. Persisting evidence for audit and admitting it as a calculation input are separate operations.

## 10. Other supporting components

These components have useful work implemented, but must remain subordinate to the reverse-valuation product:

- **Dividends / total return:** `dividend_history.py` provides sourced dividend observations and deterministic metrics; the reverse engine includes explicit cash-retained and dividend-reinvested conventions and relief calculations where inputs exist. The conventions must remain distinct and must not double-count dividends. The web UI exposes the dividend basis (per-share amount with currency, period label when provided, source), both conventions with formulas, and a price-vs-total-return comparison table with deltas for cash-retained and reinvested variants.
- **Financial history:** `financial_history.py` can summarize sourced financial series/growth/margins when filing observations are acquired. The runner describes this path as opt-in; empty history must be labelled not acquired rather than suggesting the company has no history.
- **Capital structure / EV:** `capital_structure.py` can compare provider observations with a reconstructed market-cap/enterprise-value bridge where inputs exist. A numeric match does not remove documented coverage limitations; partial status and omitted liabilities/assets must remain visible.
- **Risk-free rates / cost of equity:** Treasury yields can be acquired for declared tenors; beta and equity-risk-premium may be user assumptions. These inputs are not the user's required-return hurdle and must not be conflated.
- **DCF block:** The runner builds a DCF input/feasibility block that lists missing cash-flow, discount-rate and terminal-growth inputs. It does not have licence to fill missing inputs, turn this into a fair-value estimate, or replace the explicit reverse scenario matrix.
- **Research Dossier / report formatter:** They render supporting data and deterministic calculations into human- or machine-readable outputs. A longer report is not the core user experience and must not substitute for the reverse matrix.
- **LLM interpreter:** `llm_interpreter.py` builds a prompt/request; the project is not currently calling a live model provider. LLM integration is not needed to complete the reverse-valuation product.

## 11. CLI and frontend runtime notes

Current CLI options are documented in [USAGE](USAGE.md). Useful reverse-calculation controls include `--reference-multiple`, `--reference-multiples`, `--reverse-horizons`, `--required-returns`, `--horizon-years`, and optional multiple/risk inputs. `--financial-history`, `--historical-pe`, `--context`, `--dossier`, `--archive`, and snapshot control affect supporting acquisition/output/persistence paths, not the main product definition.

For local frontend development, see [web/frontend/README.md](../web/frontend/README.md). The frontend build was successful in the checked GitHub Actions log. The browser smoke job was successful in the latest checked run, but smoke-test success only checks the existing browser paths; it does not mean the full reverse matrix UI exists.

## 12. Latest verified implementation and CI status

Latest checked runs (sequential):

- [Run 38137995221](https://github.com/sbvcid/st-eva/actions/runs/38137995221) (`1d0ef0b`, documentation-only change after code baseline `9a43f9f`): backend failed (3 failures); browser passed; archive/isolation and web API passed; frontend build passed. Failures at interface of calculation semantics, unavailable-value representation, and traceability.
- [Run 38140076063](https://github.com/sbvcid/st-eva/actions/runs/38140076063) (`cb5ab8c`): backend and browser jobs passed; 1,897 passed, 168 skipped, 140 subtests. The three earlier failures resolved by engine/Context contract fixes (unavailable consensus price derivations retained in Context; pe_percentile unavailable-state alignment; user-supplied reference multiple 30.0 passed through with USER_SUPPLIED basis); regression test added.
- [Run 38141809016](https://github.com/sbvcid/st-eva/actions/runs/38141809016) (`661e0df`): backend failed (4 failures: `TestS3DerivedFigureTraceability::test_a_derived_figure_carries_state_flags_only_when_something_is_wrong`, `TestUnavailableContract::test_consensus_price_derivations_agree_on_missing_state`, `TestUnavailableContract::test_engine_and_context_agree_on_what_is_missing`, `TestConditionalContract::test_the_reference_states_its_basis_and_source`); browser passed. Root cause: merge/sync reintroduced pre-fix `investment_context.py` logic and `.gitignore` formatting anomaly (`\n#`).
- [Run 38143623578](https://github.com/sbvcid/st-eva/actions/runs/38143623578) (`0f9ac03`): backend and browser jobs passed. Verified CI green across full test suites, archive isolation, web API, frontend build, and browser smoke.
- **Post-38141809016 Fix & Verification:**
  - `_band_status`: Undeclared sample count returns `DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT` and is not treated as usable reference.
  - `consensus_price_ratio` / `consensus_price_gap`: Registered with conditional/unavailable provenance even when median price is absent.
  - `pe_percentile`: Context consistently registers unavailable state with clear refusal reason when engine deems it unavailable.
  - Valuation reference: `user_pe` multiple (e.g. `30.0`) is passed cleanly, preserving `USER_SUPPLIED` basis.
  - `.gitignore`: Formatted cleanly to ignore `data/historical_pe/AAPL/reverse_requirements_output.json` without syntax defects.
  - **Local verification results:** 4 targeted tests passed in 0.39s; backend suite passed (1,897 passed, 168 skipped, 140 subtests passed in 317.74s); archive-isolation 6 passed; web API 15 passed; frontend build passed (`dist/index.html` produced). Persistent SQLite files and AAPL reverse requirements artifact verified intact.

Runs after the R2 baseline:

- [Run 38155972302](https://github.com/sbvcid/st-eva/actions/runs/38155972302) (`78f387a`, R2.1 first attempt): backend and browser jobs both failed at "Build frontend" (`TS2339: Property 'related_sec_evidence' does not exist on type 'ScenarioEvidenceDTO'`). This attempt is not acceptance evidence; the R2.1 section below records what was rejected and why.
- [Run 38160351228](https://github.com/sbvcid/st-eva/actions/runs/38160351228) (`3e9ec3d`, R2.1 correction): backend and browser jobs passed — frontend build, self-contained production inputs, archive isolation tests, web API tests, the full backend suite and browser smoke tests all succeeded.
- [Run 38160824276](https://github.com/sbvcid/st-eva/actions/runs/38160824276) (`9638722`, status record): backend and browser jobs passed.
- [Run 38167442978](https://github.com/sbvcid/st-eva/actions/runs/38167442978) (`be29020`, R3 acceptance harness and live-path tests): backend and browser jobs passed. This is a CI regression run over fixtures and the isolated live-path contracts; it is **not** real-data acceptance — the R3 section below records which checks came from a live AAPL acquisition and which from fixtures.
- [Run 38195124312](https://github.com/sbvcid/st-eva/actions/runs/38195124312) (`6ab74e8`, R5 summary reconciliation and JSON/CSV audit export): backend and browser jobs passed — frontend build, archive-isolation, web API, the full backend suite and browser smoke (including the new real-browser export-download smoke) all succeeded.
- [Run 38198626332](https://github.com/sbvcid/st-eva/actions/runs/38198626332) (`c84bc6f`, R6 point-in-time replay diagnoses the live AAPL DIVERGENCE and replays at the archival watermark): backend and browser jobs passed — the full backend suite (including the new R6 replay-diagnosis tests) and browser smoke (the replay-affecting MSFT path) all succeeded.
- [Run 38202918791](https://github.com/sbvcid/st-eva/actions/runs/38202918791) (`061230f`, R6.1 replay reconciles each run against its own context snapshot): backend and browser jobs passed — the full backend suite (including the new R6.1 snapshot-identity tests and the restored CLI-output legacy-compatibility test) and browser smoke all succeeded.
- [Run 38220867917](https://github.com/sbvcid/st-eva/actions/runs/38220867917) (`84cc74d`, first-use execution mode defaults to live with the assumptions panel expanded): backend and browser jobs passed — the full backend suite, frontend build and browser smoke (including the suite adjusted to pin `regression` for fixture-dependent checks) all succeeded.

Local verification for the same commit before observing CI: full backend suite 1,958 passed, 168 skipped, 140 subtests passed (341.60s); provenance regression 20 passed; wiring 49 passed; web API 22 passed; browser smoke 8 passed; Vitest frontend 27 passed; frontend build produced `dist/index.html`.

## R2.1 — EPS Source Binding Correction (accepted 2026-10-11, verified by run 38160351228)

**Defect reviewed:** `_resolve_sec_eps_fact` accepted a `target_value` but did not use it to establish a relationship between the selected anchor and the returned SEC record. It returned the first historical SEC EPS observation with an accession, or a recent annual filing entry, and its caller attached the result to any non-user EPS anchor — including vendor forward and consensus EPS. A value's source therefore described a document about the same metric/company rather than where the value came from.

**First attempt rejected (`78fe387a`, CI run `38155972302`, both jobs failed at "Build frontend"):** it added identity filters but still selected records by value match, and it rendered `evidence.related_sec_evidence` in the frontend while neither `ScenarioEvidenceDTO` in `web/schemas.py` nor the TypeScript contract declared that field.

**Corrective action:**
- `_resolve_sec_eps_fact(target_value=None, *, source_observation=None)` now returns a fact only from a linked observation, built from that observation's own identity (concept, accession, form, filed date, period, unit, document reference). With no linked observation it returns `None`. `target_value` is retained only as a documented confirming compatibility check on the identified record.
- New `_sec_observation_supplying_anchor()` establishes the linkage by observation identity: the observation that projected the engine's EPS input field (mirroring `_apply_observations_to_view`) must be one of this run's acquired regulatory-filing observations. A vendor observation holding the same number establishes nothing.
- New `_is_sec_filing_observation()` requires an accession plus a declared regulatory-filing source; `_observation_projecting_view_field()` answers "which observation supplied this field" with the same rule the projection used.
- The caller no longer passes a value match; `related_sec_evidence` travels through `EpsAnchor`, `build_scenario_evidence()`, `ScenarioEvidenceDTO` (pydantic) and the frontend contract, and the engine states the limitation for every sourced anchor without a proven direct SEC source.
- Audit drawer labels: "SEC-Linked Source" badge only when the linkage is proven, "Provider-Sourced (SEC Link Not Established)" otherwise, "Direct SEC source: not established" in the drawer, and related filings rendered as `Related SEC {form} (cross-check)`.

**Acceptance evidence:** `tests/test_r21_provenance_binding.py` (20 tests) proves (1) a vendor forward EPS does not inherit a historical SEC 10-K; (2) a consensus forward EPS does not inherit SEC filing metadata, including when its value equals a historical filing figure; (3) a same-ticker SEC record cannot attach because it is the first available record, even with an exactly equal value; (4) an SEC-derived anchor receives the correct filing reference only when the input-to-fact linkage is established (accession, form, filed date, concept, unit, period), and a vendor or other-concept observation with the same value does not; (5) user-supplied EPS has no SEC source attribution; (6) unresolved provenance is explicit in the API contract and the UI without hiding the EPS value or inventing a source; (7) deterministic calculation traces, `reverse-requirements/1.1` fingerprinting, and DTO error behavior remain intact. The suite was also run against the defective `78f387a` build: 12 of the 20 fail there, including the value-equality binding cases, and pass only against the corrected resolver.

**Local verification:** full backend suite 1,958 passed, 168 skipped, 140 subtests passed (348.69s); provenance regression 20 passed; wiring 49 passed; web API 22 passed; Playwright browser smoke 8 passed; Vitest 27 passed; production frontend build produced `dist/index.html`; `git diff --check` clean. No new acquisition, registry, export, or archive integration; no SQLite database deleted, reset, recreated, or overwritten; formula version unchanged at `reverse-requirements/1.1`.

## R3 — Real AAPL End-to-End Acceptance (accepted 2026-10-11, live acquisition)

**Path exercised:** the real web application — FastAPI app created with `create_app(archives_dir=<temporary directory>)` serving the production frontend build in headless Chromium, with submissions made through the browser's own assumption controls. Ticker `AAPL`, mode **explicitly `live`** (never `auto`, never `regression`). No fixture, mock or regression data was used for the acquisition; the archive directory was temporary and isolated.

**Submission 1:** ``{"ticker": "AAPL", "mode": "live", "reference_multiple": 30, "reverse_horizons": [3], "required_returns": [0.1]}``

**Submission 2 (changed assumptions):** ``{"ticker": "AAPL", "mode": "live", "reference_multiple": 32, "reverse_horizons": [3], "required_returns": [0.12]}``

**What the response and the browser actually showed (live acquisition, data date 2026-10-09):**
- Ticker `AAPL`, company `AAPL (Live Acquired)`, admission status **ADMITTED** (1 admitted / 0 refused, admitted metric: `revenue`).
- Market price **336.64 USD**, as-of 2026-10-09; `source_identifiers` = `YahooFinance+YahooFinanceFundamentals`, `Yahoo Finance chart API`, `API_LIVE`.
- EPS anchor **8.72 USD**, `TRAILING_TWELVE_MONTHS`, provider `YahooFinance+YahooFinanceFundamentals`, `source_type` `API_LIVE`, observation id `ev-current-eps-001`, 12 months coverage, with **"period coverage was not declared by source"** stated rather than assumed silently.
- Direct SEC attribution: `sec_fact` is **null** (R2.1 rule: the vendor trailing EPS is not linked to a filing fact). `related_sec_evidence` is present and labelled cross-check only: AAPL FY2025 10-K accession **0000320193-25-000079**, filed 2025-10-31, concept `us-gaap:EarningsPerShareDiluted`, note "Related SEC filing (cross-check); not verified as direct source of selected EPS value". The drawer shows `Provider-Sourced (SEC Link Not Established)`, `Direct SEC source: not established`, and `Related SEC 10-K (cross-check)`; no `Source: SEC 10-K` block is rendered, and the API's `missing_or_unvalidated` carries "Direct SEC source of selected EPS not established; related filing shown for cross-check only".
- Matrix: `reverse-requirements/1.1`, status **COMPUTED**, `matrix_size` 1. Submission 1 row: horizon 3y, required return 10%, exit multiple 30x (`user_supplied` / `USER_SPECIFIED`, flagged as a user assumption) -> required exit price **448.067840** = 336.64 x 1.1^3, required terminal EPS **14.935595** = 448.067840 / 30, total EPS growth **+71.28%**, required EPS CAGR **+19.65%**. Submission 2 row: horizon 3y, 12%, 32x -> **472.954962** = 336.64 x 1.12^3, terminal EPS **14.779843**, growth **+69.49%**, CAGR **+19.23%**. All four steps are `reproducible` and were independently recomputed from the displayed operands: 0 mismatches for both submissions.
- The drawer corresponded to the submission that produced it: after submission 2 the page showed `32.0x`, `12.0%` and the recomputed values, and the earlier `30.0x` row was gone. Both requests carried `mode: "live"`; no "REGRESSION FIXTURE (TEST DATA)" banner and no `RegressionFixture` identity appeared.
- Exit multiple availability: with no multiple supplied the same live path returns `status: NOT_COMPUTED`, `matrix_size: 0`, and the explicit reason "The historical P/E band holds 8 observations, below the 20 required to read a percentile from it. The band's median of 35.65 is reported as a descriptive statistic only and is not used as a scenario exit multiple." (`reason_kind: INSUFFICIENT_OBSERVATIONS`). The matrix is therefore computable on the live path only when a multiple is supplied, and every such multiple is recorded as a user assumption.
- Point-in-time replay for the live run reported **DIVERGED** (the stored and rebuilt context documents differ); the report states it rather than hiding it.
- Isolation: the archive lived in a temporary directory; SHA-256 of `data/st-eva.sqlite` and every `data/archives/*.sqlite` (10 files including WAL/SHM) was identical before and after every acceptance run. Nothing was deleted, reset, recreated or overwritten.

**Automated coverage added (deterministic, no fixed market values):**
- `tests/test_r3_live_web_path.py` (3 tests): a live-shaped (`API_LIVE`) acquisition driven through the real service adapter and runner in an isolated archive directory. Asserts assumption propagation into the scenario cross-product and derived outputs, live source identities on price and EPS evidence, the R2.1 no-SEC-attribution rule, band ineligibility and the uncomputable matrix when no multiple is supplied, and archive isolation.
- `tests/test_browser_smoke.py::TestLiveModeSelectionBrowser` (1 test): the real browser request carries `mode: live` plus the selected assumptions, and the audit drawer renders that request result instead of the previous submission's.
- `tests/test_r3_live_aapl_acceptance.py`: the reproducible real-data acceptance harness that produced this record. Gated by `ST_EVA_R3_LIVE=1` (it never runs implicitly); set `ST_EVA_R3_EVIDENCE=<path>` to write the machine-readable record. It asserts only recomputable contract properties, never today's price or EPS.

**Verification runs after the R3 change (fixture-based determinism, reported separately from the live acceptance above):**
- Focused: provenance regression 20 passed, reverse-requirements wiring 49 passed, web API 22 passed, R3 live-path 3 passed, R3 acceptance harness 1 skipped by default (passed when enabled), live browser AAPL acceptance passed twice with evidence recorded.
- Full backend suite: **1,962 passed, 169 skipped, 140 subtests passed in 341.50s**.
- Frontend: Vitest 27 passed; production build produced `dist/index.html`.
- Browser smoke (Playwright, real Chromium): 9 passed in 42.95s.
- Persistent data: SHA-256 of all 10 SQLite files (including WAL/SHM) unchanged; no generated files left in the repository.

**Remaining limitations recorded by this acceptance, not fixed:**
1. A live web submission with no exit multiple cannot compute a matrix for AAPL yet (band holds 8 usable observations < 20, so it is reported ineligible and is never used as a reference).
2. The production point-in-time daily historical P/E reconstruction is **not** enabled on the web path: `production_historical_pe` was `{}` in the live response. The reported 8-observation band is the provider band distribution, and no claim is made that the web path uses the production reconstruction.
3. Starting EPS period coverage is undeclared by the live source and is reported as such.
4. Point-in-time replay is DIVERGED for the live run and is reported, not hidden.
5. Environment note: during this acceptance window the live web path took about 301 s on two early runs while the SEC step was rate limited, and the pre-existing browser smoke test `test_desktop_matrix_audit_drawer_inspection` exceeded its 90 s "Analysis Verdict" timeout on two full-suite attempts. Each passed on retry (6.3 s standalone; 13 s inside the live acceptance harness), and the full suite then passed completely, so this was upstream latency, not a product defect. No timeout values or fixtures were changed to obtain a pass.
## R4 — Eligible Historical P/E Reference on the Web Path (accepted 2026-10-11, live acquisition)

**Gap closed:** R3 showed that a live AAPL web submission with no exit multiple returned ``status: NOT_COMPUTED``: only the vendor P/E band was consulted and it holds 8 usable observations, below the 20 required. The runner already supported the production point-in-time historical P/E pipeline (``run_st_eva(..., include_historical_pe=True)``); the web adapter never asked for it.

**What was wired (no new engine, no new acquisition source):**
- ``web/service_adapter.py::run_analysis_pipeline`` now calls ``run_st_eva(..., include_historical_pe=True)``. The runner already separates the production distribution from the vendor band, an ineligible distribution, and an unsupported ticker, and adds no network acquisition of its own: it reads the frozen SEC filing and pricing evidence under ``data/historical_pe/{TICKER}``.
- ``historical_pe.production_distribution_summary()`` is the compact statement of that dataset: metric, source identity, sample and qualifying counts, sample period, the as-of rule the evaluation dates follow, percentiles, the current P/E snapshot, the input-set identity, and the reason when it is unavailable or under-qualified. It changes no eligibility rule; the same gate that selects the scenarios decides what it reports.
- The engine report now carries it as ``production_historical_pe_summary`` beside the full ``production_historical_pe`` payload, and the API exposes it as ``ReverseRequirementsReportDTO.production_historical_pe_summary`` and ``AnalysisResultDTO.production_historical_pe``. The full per-observation dataset is not part of the API contract.
- The audit drawer renders the production distribution as its own block (``data-testid="production-historical-pe"``): status, qualifying/maximum observations, minimum required, sample period, percentiles, current P/E with its as-of date, and the as-of rule when eligible; observation count and the stated reason when not. Exit-multiple source and eligibility are shown in the report's own terms ("Production point-in-time historical P/E", "Eligible production reference distribution", "User-specified assumption") instead of raw identifiers.

**Measured behaviour (this machine, live acquisition):**
- Runtime per live web request: 5-9s end-to-end (submit 0.01-0.10s), dominated by SEC filing acquisition and cold-archive seeding; the production pipeline itself is ~0.08s of that.
- Duplicate acquisition work reviewed: the SEC evidence acquisition (live EDGAR, fetched once and shared by the context and financial-history paths) and the production historical P/E pipeline (frozen local dataset, no network) cover overlapping facts but are separate sources, and no second ingestion path was added.
- Response payload: the report already embeds the full production dataset and the reverse requirements report, so ``raw_analysis`` repeated both of them verbatim. ``_web_visible_analysis()`` removes that duplication from the presentation copy only (the archive, context document and CLI keep every byte): 4507 KB -> 1605 KB for an 80-row matrix, identical content for every consumer.

**Real AAPL acceptance evidence (live, temporary archive, no user exit multiple):**
- Submitted through the real browser and API: ``{"ticker": "AAPL", "mode": "live"}`` with no ``reference_multiple``/``reference_multiples``. No regression fixture was used (no fixture banner, no ``RegressionFixture`` identity; ``Yahoo``/``API_LIVE`` identities only).
- Result: ``status: COMPUTED``, ``matrix_size: 80`` (5 production percentiles x 4 horizons x 4 required returns), formula version ``reverse-requirements/1.1``.
- Every row's exit multiple is ``source: production_historical_pe_percentile``, ``eligibility_state: ELIGIBLE_PRODUCTION_DISTRIBUTION``, ``is_user_assumption: false``, ``usable_for_reference: true``, carrying ``sample_size`` and a sample period naming the distribution. The values are exactly the distribution's percentiles.
- Reported distribution: ``status: USABLE_FOR_REFERENCE``, ``metric_id: TTM_GAAP_DILUTED_PE``, issuer ``CIK0000320193``, ``sample_count: 36`` of ``total_evaluations: 36``, ``min_observations_required: 20``, sample period ``2018-01-02`` to ``2026-07-31``, cadence ``PERIODIC_FILING_USABLE_DATES`` ("Evaluated on periodic SEC filing and earnings release usable dates ... not a continuous daily trading history"), current P/E 38.26 as of 2026-10-06, ``input_set_id: 01f618068f......``.
- Independent recomputation from each row's own operands matched exactly (exit price, terminal EPS, total EPS growth, CAGR), and all four calculation steps are ``reproducible``.
- The undersized vendor band was not substituted: the response still reports ``exit_multiple.band_scenarios`` with ``reason_kind: INSUFFICIENT_OBSERVATIONS`` and the reason "The historical P/E band holds 8 observations, below the 20 required ... a descriptive statistic only and is not used as a scenario exit multiple."
- Second submission adding a user multiple returned 24 rows in which the user rows (``source: user_supplied``, ``eligibility_state: USER_SPECIFIED``, ``is_user_assumption: true``) stand beside the production-distribution rows rather than replacing them.
- The drawer's production-distribution block agreed with the API response (status, 36 qualifying observations, ``2018-01-02``/``2026-07-31``, and the as-of rule).
- Unsupported ticker (``TSM``) through the same path reports ``status: UNAVAILABLE`` with "Production historical P/E dataset is not yet established for TSM." and ``reverse_requirements`` ``NOT_COMPUTED`` with the explicit missing-multiple reason.

**Automated tests added (deterministic, no fixed market values):** ``tests/test_r4_web_historical_pe.py`` (13 tests) covers: the compact summary describes the same dataset as the payload; a qualified distribution yields labelled eligible scenarios; an under-qualified distribution with a median is never upgraded and produces no scenarios; the report's matrix draws only from the distribution while the undersized band is reported as excluded; a user multiple stays separately labelled alongside distribution rows; the web request actually passes through the production path; the vendor band is never silently substituted; user multiples remain separate assumptions; unsupported tickers report the real unavailable state. ``tests/test_r3_live_aapl_acceptance.py`` now submits AAPL with no multiple first and asserts the production distribution identity, eligibility, per-row provenance and independent recomputation, then adds a user multiple and checks it stays a separate assumption.

**Verification runs:** full backend suite 1,975 passed, 169 skipped, 140 subtests passed (425.55s); R4 regression 13 passed; web API 22 passed; archive isolation 6 passed; R2.1 provenance 20 passed; wiring 49 passed; Vitest frontend 27 passed; production build produced ``dist/index.html``; browser smoke 9 passed (49.40s standalone). On one full-suite attempt the pre-existing browser smoke viewport test exceeded its 90s ``Analysis Verdict`` wait during SEC latency and passed on the immediate re-run, so the transient is recorded rather than papered over. SHA-256 of all 10 persistent SQLite files (including WAL/SHM) and of the production datasets was unchanged; no database was deleted, reset, recreated or overwritten, and every acceptance run used a temporary archive directory.

**Remaining limitations recorded, not fixed:** the production distribution exists only for ``AAPL`` and ``MSFT``; other tickers get the explicit ``UNAVAILABLE`` state. The distribution is evaluated on periodic filing/earnings-release usable dates, not a daily history, and the web path does not compute the ``--historical-pe`` production reconstruction as part of the P/E band used elsewhere. The AAPL production dataset covers 2018-01-02 to 2026-07-31 and is not extended by the web path.

## R5 — Result Semantics, Summary Reconciliation and Audit Export (accepted 2026-10-12, verified by run 38195124312)

**Objective (unchanged product center):** make the summary-card values and the reverse-matrix values semantically unambiguous, and export the actual reverse-requirements report plus the row-level audit trail as JSON and CSV. No ratings, price targets, forecasts, recommendations, LLM integration or second calculation engine were added; the reverse-valuation engine stays the only calculator and ``reverse-requirements/1.1`` stays the formula version.

**1. Summary cards reconciled with the scenario matrix** (``web/frontend/src/components/ResultCards.tsx``)
- The headline tiles now sit under an explicit **Market-Implied Headline Metrics** heading with a note that they are single-point references "not interchangeable with a matrix CAGR", a per-metric **basis legend**, and an explanatory link that scrolls to the matrix (``#reverse-requirements-matrix``, anchor id set on ``ReverseRequirementsMatrix.tsx``).
- **Price-Implied EPS** (was "Implied Fwd EPS"): "market price ÷ selected P/E — the EPS today's price corresponds to at that multiple, not a forward/NTM forecast". This is the summary engine's ``forward_eps_at_reference_multiple = price / selected_pe`` (a single point with no horizon or return).
- **Implied EPS Gap (CAGR)** (was "Req. EPS CAGR", now deliberately distinct from the matrix column label, which stays "Req. EPS CAGR"): a flat-multiple vs trailing-EPS gap, annualised over the reported ``summary_horizon_years`` (default 1.0 on the web path), with no required-return hurdle, exit multiple or dividends. The differing anchor, horizon and multiple are stated so a summary CAGR can no longer be read as a matrix row.
- **Reference P/E**: states its basis from a new ``selected_pe_basis`` — your supplied multiple (``user_supplied_multiple``), the production point-in-time historical P/E distribution median (``production_historical_pe_median``), or the vendor historical P/E-band median (``historical_pe_median``, requires ≥ 20 declared observations). *(Amended by R7-5: this line originally ended with "never the production point-in-time distribution the matrix's eligible exit multiples use", which was the requirement gap R7-5 corrected.)*

**Backend basis metadata (no calculation change):** ``web/schemas.py::ValuationSummary`` gains ``selected_pe_basis`` (from ``reference.method``) and ``summary_horizon_years``; ``web/service_adapter.py`` maps both from the existing summary-engine output (``horizon_years`` forwarded to it). Financial values and ``reverse-requirements/1.1`` are unchanged.

**2. Exports from the typed result contract** (``web/frontend/src/services/exportResult.ts``)
- Built from the exact typed ``AnalysisResultDTO`` currently displayed (``currentJob.result``) with the submitted request echoed for assumptions/mode. Nothing is recomputed; JSON and CSV reflect the same submission, and a second submission exports its own result (``lastSubmittedRequest`` is replaced on every submission). No network acquisition and no persistent-storage writes are added.
- **JSON** — a versioned envelope (``st-eva-reverse-requirements-export/1.0``): export metadata (schema version, generation timestamp, generator, ticker, mode), the echoed request, and the full typed result — ticker/company identity, as-of, acquisition/source identifiers, admission summary, valuation summary with its new basis fields, replay summary/status, the production historical P/E eligibility summary, the **full** scenario matrix with nested evidence and calculation traces, and top-level unavailable states. The duplicated ``raw_analysis`` payload is omitted by default (kept verbatim by the archive, context document and CLI). Nested evidence/trace structure is preserved, not flattened.
- **CSV** — one row per scenario across the **full** matrix (built from ``reverse_requirements_matrix``, so a screen filter can never shrink a file advertised as the full export). Stable, documented snake_case columns cover identity/as-of/currency, formula version, the scenario assumptions (horizon, required return + basis, exit multiple source/eligibility/sample, EPS anchor basis/value/source), results (required exit price, required terminal EPS, total EPS growth, CAGR, growth window), per-step reproducibility, and user-assumption flags. Structured items that cannot be scalars without losing information are carried in stable JSON-encoded columns — ``scenario_json`` (the entire scenario, so dividend relief, terminal-P/E change, consensus gap, etc. are never discarded), ``calculation_steps_json``, ``evidence_json``, ``user_assumptions_json``, ``sourced_facts_json``, ``missing_or_unvalidated_json``, ``flags_json``, ``comparison_notes_json``.
- **Provenance and missingness honoured:** production-distribution rows, user-supplied multiples and descriptive-only bands stay distinct via ``exit_multiple_eligibility_state``/``exit_multiple_source``/``exit_multiple_is_user_assumption`` (user assumptions are never presented as source facts). R2.1 is preserved — direct SEC columns ``eps_direct_sec_*`` (form/accession/filed-date/concept) are populated only where identity linkage establishes the relation, and related filings stay in separate cross-check columns ``eps_related_sec_*`` and inside ``evidence_json``. Missing values stay empty with their explicit flags/reasons (never zero). An uncomputed report exports the header plus a single ``report_status_only`` row carrying status, reason and ``report_unavailable_json`` — no manufactured scenario rows and no zero-filled values.

**Automated tests**
- ``web/frontend/src/test/ExportResult.test.ts`` (new): JSON envelope versioning/metadata and echoed request; ``raw_analysis`` omission with the rest of the typed result verbatim; full-matrix, nested-evidence and calculation-trace preservation; R2.1 direct-vs-cross-check separation; CSV documented header; one row per scenario; distinct production / user / descriptive-only exit multiples; missing values empty not zero; exact figures and re-parseable JSON columns; whole matrix regardless of any filter; uncomputed status-only export (no invented rows/zeros); second-submission isolation.
- ``web/frontend/src/test/ResultCards.test.tsx`` (new): headline titles and basis legend; summary CAGR relabelled away from the matrix column; selected-P-E basis by ``selected_pe_basis`` (user / band median / none); the see-matrix scroll link.
- ``web/frontend/src/test/App.test.tsx``: export controls render after a completed analysis; clicking exports the displayed result as re-parseable JSON without ``raw_analysis``; a second submission's CSV reflects the second response rather than stale data.
- ``tests/test_web_api.py::TestAdapterIntegrationSmoke::test_summary_headline_basis_is_reported`` (new): the real regression-fixture pipeline reports ``selected_pe_basis = user_supplied_multiple`` with ``summary_horizon_years`` echoed and ``forward_eps_at_reference_multiple == current_price / selected_pe``.
- ``tests/test_browser_smoke.py::test_export_controls_trigger_real_downloads`` (new): real Chromium drives the JSON and CSV downloads and re-parses both offline (no frontend runtime).

**Verification runs (this machine):** Vitest frontend 47 passed (7 files); production build produced ``dist/index.html``; web API adapter smoke classes 23 passed; the export browser smoke passed in real Chromium. The four persistent SQLite files (``data/archives/{AAPL,MSFT,TSM}.sqlite`` and ``data/st-eva.sqlite``) carry modification timestamps of 2026-10-09/2026-10-10, all predating this task, so none was deleted, reset, recreated or overwritten and ``git status`` under ``data/`` is clean; every acceptance run (the browser smoke ``TestBrowserSmoke`` server and the web-API adapter tests) used a temporary archive directory, and the export feature reads only the in-memory response it is given — no network acquisition and no persistent-storage write.

**Boundary:** presentation and export only. No financial formula, the reverse-requirements calculation or ``reverse-requirements/1.1`` changed; no network acquisition, no persistent-storage mutation, no ratings/targets/forecasts/recommendations, no LLM integration and no second engine were added. Exports read only the response currently shown in the UI.

## R6 — Point-in-Time Replay Divergence: Diagnosis and Narrow Correction (accepted 2026-10-12, verified by run 38198626332)

**Question:** the R3 live AAPL acceptance recorded ``replay_summary.outcome = DIVERGED``. Is it a genuine template/context difference, a cutoff/eligibility mismatch, a volatile serialization artifact, or a replay/persistence defect?

**Diagnosis (reproduced deterministically, offline).** A live-shaped ``API_LIVE`` acquisition was archived into a temporary SQLite archive and its stored context compared to a rebuild field by field (``tests/test_r6_replay_divergence.py``). The ``context_id`` divergence had **two separable causes**:

1. **A replay cutoff / eligibility mismatch (the demonstrated defect).** The web path replayed at the *data date* (``core_result["as_of"]``, e.g. 2026-10-09). The vendor fundamentals (trailing EPS, forward EPS, revenue, EBITDA, market cap, EV, FCF, consensus EPS, P/E band) are ``UNDECLARED`` -- Yahoo declares no publication time -- so the archive dates them as ``ARCHIVE_FIRST_SEEN`` from ``first_archived_at`` (the archival instant, 2026-10-12), i.e. *after* the data-date cutoff. ``observations_for(data_date)`` therefore drops them, and the rebuild reconstructs a strictly-earlier, sparser knowledge state: ``data_quality.evidence_coverage`` fell 11 available -> 2, and every material figure became ``UNAVAILABLE``. A *faithful* rebuild was thus reported DIVERGED simply because the cutoff preceded the observation set that built the stored document. This is the same "replaying before archival yields less evidence" situation the archive calls out, but mis-applied as a round-trip check: replaying at the data date compares a full context to a POIT-truncated one, so the check can never report MATCH for live data and the signal is not a determinism result. It is a cutoff/eligibility mismatch, **not** volatile serialization (the differences are real observed-value losses, never ``generated_at``/``retrieved_at``, which the ``context_id`` already strips).

2. **A genuine, unresolved input difference (preserved, not hidden).** Even at the correct cutoff, the stored live context was conditioned on a user-supplied reference multiple (a runtime request assumption, e.g. 30 for R3), which is *not* an archived observation. ``build_context_from_observations`` rebuilds from observations only, so the reference-conditional figures (``implied_forward_eps``, ``required_eps_cagr``, ``implied_to_consensus``, ``eps_gap_vs_consensus`` and the reference ``market_implied`` figures) exist in the stored document and cannot be reconstructed. Reporting them as different is honest; forcing a match would be wrong.

**Correction (narrow, cause 1 only).** The web replay now rebuilds from the *same eligible observation set* that produced the stored context: ``web/service_adapter.py`` computes the asset's ``archival_watermark`` (the latest instant any observation became replay-eligible -- the archive's own knowledge boundary, added as a read-only method on ``SQLiteArchive`` with an ``ArchiveStore`` interface default) and replays at that cutoff, falling back to the data date when there is no watermark. No observation, source availability class, hash, or the volatile-field ``context_id`` contract was changed; the strict earlier point-in-time behaviour of ``observations_for`` is untouched for every other caller, so a historical cutoff still excludes not-yet-eligible observations. Consequences:
- A reference-free live context rebuilt from the same eligible observations now reports **MATCH** (fidelity ``OBSERVATIONAL``, because the vendor fundamentals remain archive-first-seen).
- A reference-conditioned context still reports **DIVERGED** -- the honest, unresolved reference-assumption difference -- and the R3 live result therefore *remains* DIVERGED (both R3 submissions supplied a reference multiple). This correction did not manufacture a match.

**Automated tests** (``tests/test_r6_replay_divergence.py``, 8 tests, temporary archives, SEC layer empty so no network):
- Defect is the cutoff, not serialization: a reference-free context DIVERGES at the data date but MATCHes at the watermark, with the rebuild reproducing the stored ``context_id`` and using strictly fewer observations at the data date.
- Semantic equality matches: the web ``replay_summary`` for a reference-free live context is ``MATCH``/reconstructed/observational.
- Real input difference still diverges: reference-free MATCHes while reference=24 DIVERGES, and the divergence is specifically the reference-conditioned figure (stored ``implied_forward_eps == price/24``; rebuilt absent).
- No silent substitution: an archive-first-seen fundamental is excluded at an earlier cutoff (fewer eligible observations, higher ``unavailable`` coverage, the figure ``UNAVAILABLE`` rather than populated).
- Missing inputs keep explicit states/reasons: an empty archive is ``INSUFFICIENT`` with "nothing was substituted"; observations with no context snapshot report ``NO_SNAPSHOT`` and still offer the reconstruction.
- Canonicalization is deterministic: repeated replays yield the same ``context_id`` while the full ``document_hash`` differs (volatile ``generated_at`` retained for audit) -- volatile fields are excluded from semantic identity, the complete evidence is preserved.

**Verification runs after the change:** full backend suite **1,985 passed, 169 skipped, 140 subtests passed (407.48s)**; focused replay/R2/R3/R4 subset 122 passed, 13 skipped, 3 subtests; web API non-live classes 23 passed; the new R6 suite 8 passed. Existing R2.1 provenance, R4 historical-P/E eligibility, R5 export and reverse-matrix tests are intact. No ``reverse-requirements/1.1`` change. No persistent database deleted, reset, recreated or overwritten; every run used a temporary archive directory. Persistent SQLite modification timestamps still predate this task and ``git status`` under ``data/`` is clean.

**Boundary.** Only the web replay cutoff was corrected. ``archive.replay`` itself, ``observations_for`` eligibility, source availability declarations, the volatile-field hash contract and the reverse-valuation formula are unchanged. The reference-assumption divergence is a documented, honest outcome and is left visible rather than forced to MATCH.

## R6.1 — Replay Snapshot Identity Verification (accepted 2026-10-12, verified by run 38202918791)

**Question.** When one asset carries more than one archived context for the same ``as_of``, does replay reconcile a run against *that run's* context, or against an unrelated one that merely shares the data moment?

**Reproduced (offline, temporary archives).** Two live-shaped runs on one ticker with the same data date but different supplied reference multiples produce two context snapshots that share ``as_of``. ``replay`` selected the stored snapshot through ``context_at(as_of)``, which is ``ORDER BY archived_at LIMIT 1`` — the *earliest* snapshot — so it compared the current run's rebuild against the wrong context:
- ref-free then ref-32 → the ref-32 run reported a **false MATCH** against the older ref-free snapshot (its own ref-32 snapshot would honestly DIVERGE).
- ref-32 then ref-free → the ref-free run reported a **false DIVERGED** against the older ref-32 snapshot (its own ref-free snapshot would honestly MATCH).
The rebuild's own ``context_id`` was correct in every case; only the snapshot *selection* was wrong. This is a demonstrated defect, not a suspected one.

**Correction (smallest change, contract-compatible).**
- ``archive.replay`` gained an optional ``context_id``; when supplied it reconciles against that exact snapshot via a new ``SQLiteArchive.context_by_id(asset, context_id)`` (an ``ArchiveStore`` default returns ``None``). The default ``context_at`` path — the ``as_of`` selection — is unchanged and still available to callers, so strict-HISTORICAL selection and existing callers behave exactly as before.
- The web adapter reconciles against the context *this run archived*, identified by the ``context_id`` in the artifact the run itself wrote (``context_path``). The engine's ``result`` dict is deliberately **not** widened to carry the id: the R2.3 legacy-compatibility test asserts the ``--archive`` flag does not change the CLI output, and adding a key would violate that invariant. (A first attempt surfaced ``archived_context_id`` in the result; it flipped that test and was reverted in favour of reading the artifact.)
- When the named snapshot is absent (unknown id, or none for the asset), the result is ``NO_SNAPSHOT`` — never a silent substitution of a different snapshot. append-only snapshot storage, source evidence, full ``document_hash``es, ``observations_for`` eligibility and the volatile-field ``context_id`` contract are all untouched; ``reverse-requirements/1.1`` and valuation math are unchanged.

**Automated tests** (``tests/test_r6_1_replay_snapshot_identity.py``, 9): two contexts sharing ``as_of`` are distinct and selectable; a reference-conditioned run no longer false-matches reconciling to its own snapshot (DIVERGED) while the as_of-only path still documents the older arbitrary MATCH; a reference-free run reconciles to MATCH against its own snapshot; an unknown id is absent-not-substituted (``NO_SNAPSHOT``); the default as_of selection is unchanged; the web path reports each submission's own outcome in both orders (ref-32→ref-free = MATCH, ref-free→ref-32 = DIVERGED); earlier cutoffs still INSUFFICIENT with "nothing was substituted"; observations without a snapshot still NO_SNAPSHOT; and the persistent archives are never written (temporary archives only).

**Verification runs after the change:** full backend suite **1,994 passed, 169 skipped, 140 subtests passed (452.98s)**; focused replay/R2/R3/R4 subset 131 passed, 13 skipped, 3 subtests (the CLI-output legacy-compatibility test that the reverted approach had broken is green again); the new R6.1 suite 9 passed. No persistent database deleted, reset, recreated or overwritten; every run used a temporary archive directory; ``git status`` under ``data/`` is clean and the persistent SQLite modification timestamps still predate this task.

## AAPL First-Version Product Acceptance (accepted 2026-10-12)

**Verdict: ACCEPTED — usable first version for AAPL; no material product blocker was found.** The exercise ran the *real* application through the real HTTP API and real Chromium (not unit tests or a direct engine call), with explicit ``mode=live`` and isolated temporary archives. Yahoo and SEC EDGAR were both reachable, so this is genuine live acquisition, **not** fixture values. Three cases were exercised end to end: (1) AAPL with no user exit multiple using the eligible production historical P/E reference; (2) AAPL with an explicit user-supplied P/E and changed horizons/returns; (3) a subsequent request with a different user multiple.

**Independently verified (done here, not just reported).** Representative matrix rows were recomputed from their own stated operands (price, required return, horizon, exit multiple, EPS anchor): required exit price ``= price·(1+r)^T``, required terminal EPS ``= exit price ÷ multiple``, total EPS growth ``= terminal EPS ÷ anchor EPS − 1``, and required EPS CAGR ``= (terminal EPS ÷ anchor EPS)^(1/growth window) − 1`` all matched the API to **zero relative error** across every computable row, and the growth window derived from the anchor basis matched the reported value. These are checks the acceptancer performed directly with the real responses.

**Confirmed at the API level (``/api/analyze`` → poll ``/api/jobs/{id}``, 56/56 checks).** Tick/currency identity; matrix ``COMPUTED`` with ``matrix_size == row count``; uncomputed rows carry explicit nulls + flags (no fabricated zeroes, no substitution); exit-multiple references stay distinct (``production_historical_pe_percentile``/``ELIGIBLE_PRODUCTION_DISTRIBUTION`` vs ``user_supplied``/``USER_SPECIFIED``); the production distribution is usable (36 observations ≥ 20); summary basis is honest (the ref-free run reports ``selected_pe_basis`` from the summary engine, while user-multiple runs report ``user_supplied_multiple``) *(Amended by R7-5: the clause describing a ``none`` summary alongside production-distribution matrix exit multiples as a correct coexistence was the requirement-gap finding R7-5 corrected.)*; R2.1 holds (a direct SEC fact is fully identified and only where the source relationship is established; related filings stay cross-check and are never the direct source of the same value); replay is ``MATCH`` for the reference-free context and ``DIVERGED`` for the user-multiple context; and case 3 reflects its own request (``selected_pe`` = 26, not stale).

**Confirmed at the browser level (real Chromium driving the built SPA against the temp-archive server, 17/17 checks).** The rendered market price and matrix match the API response the UI is showing (captured from the live ``/api/jobs`` response); the dedicated **“Point-in-Time Replay Verification”** banner renders the actual outcome (green ``MATCH`` for the ref-free run, amber ``DIVERGED`` for the user-multiple next request) as a verification note separate from the green Admitted verdict and the computed matrix, so a replay divergence cannot be read as a failed valuation; the JSON download is a versioned envelope that omits ``raw_analysis`` and preserves all matrix rows, nested evidence/calculation traces and the replay summary; the CSV download contains the **full** matrix (80 rows for the default scenario set, verified with Python's ``csv`` module — 53 well-formed columns per row), with stable documented columns and R2.1 direct-vs-cross-check columns, and a row's required EPS CAGR matches the DTO; the second submission's exports reflect the second request, not stale data.

**Findings & action.** No demonstrated product blocker. Two failures surfaced during acceptance were **defects in the acceptancer's own checks**, not the product: a wrong ``total_terminal_eps_growth`` formula in the recomputation checker (fixed; the engine's net-growth convention is correct) and a hand-rolled RFC-4180 CSV parser that mishandled the JSON columns (fixed by using Python's ``csv`` module, under which the exported CSV parses to exactly one row per scenario). Per the instruction to avoid hypothetical code changes for a passing workflow, no product code, valuation formula or ``reverse-requirements/1.1`` was modified, and the engine result contract and CLI output were not broadened.

**Minor, non-blocking observation (documented, not changed).** The replay banner shows the generic ``replay()`` reason for ``DIVERGED``, which mentions “the replay is not faithful, which is a defect.” For the specific, expected case of a user-supplied multiple it does not say the more precise cause (the runtime reference is not archived knowledge). This is a clarity polish only — the banner is visually and semantically separate from the calculation, the matrix is present and computed, and the user is not misled about the valuation — so it does not materially prevent obtaining, understanding, verifying or exporting the result and was intentionally left unfixed.

**Boundary & safety.** Read-only acceptance over live acquisition. No valuation formula, calculation, ``reverse-requirements/1.1``, evidence, archive-semantics, export or UI-logic change. Every acceptance run used a temporary archive directory; no persistent SQLite database, WAL/SHM file or production historical P/E dataset was deleted, reset, recreated or overwritten (persistent file modification timestamps still predate this task and ``git status`` under ``data/`` is clean). No LLM/engine/ingestion/caching was added.

**Evidence provenance.** The API-level and browser-level checks above were executed and observed by the acceptancer in this session against live AAPL and a temporary archive; the recomputation numbers (zero relative error) and the file/console counts (56/56, 17/17) are this session's own measurements. Pre-existing automated suites (R2.1/R4/R5/R6/R6.1) and build remain intact per the latest CI run.

## First-Use Execution Mode and Assumptions Discoverability (accepted 2026-10-12, verified by run 38220867917)

**Problem.** A normal MSFT analysis could run with the hidden default `mode=auto` and return static `RegressionFixture` data (MSFT is an aliased fixture ticker, and `auto` prefers the fixture) without the user noticing the collapsed mode selector.

**Change (frontend only).**
- ``web/frontend/src/App.tsx``: the settings drawer now starts **expanded** (``showAssumptions`` default ``true``) so the execution mode is visible on first use; the **default mode is ``live``**, so a normal analysis observes real Yahoo/SEC data; ``handleResetAssumptions()`` restores ``live``.
- ``auto`` and ``regression`` remain explicit, user-selectable options — regression testing is unchanged, and the drawer can still be collapsed deliberately (the toggle is retained).
- Discoverability: a data-source hint under the mode selector explains each option's effect on sourcing, and an always-visible badge next to the ticker box names the active data source (live / auto+fallback / regression fixture), including while the drawer is collapsed.
- Frontend tests: ``web/frontend/src/test/DefaultMode.test.tsx`` (8) — the section is expanded on initial render, the initial mode is ``live``, the first analysis request carries ``mode: "live"`` with no interaction, reset restores ``live``, an explicitly selected regression run stays clearly identified (fixture banner preserved), a failed live acquisition is reported visibly (error banner, no fabricated verdict), and a mode change is honoured on a second submission. ``web/frontend/src/test/App.test.tsx`` updated for the new default.
- Browser smoke (``tests/test_browser_smoke.py``): the fixture-dependent MSFT checks now select ``regression`` explicitly (deterministic and offline, since live is the default), and the live-mode round-trip test asserts the new badge text.

**Not changed.** Valuation formulas, ``reverse-requirements/1.1``, backend request defaults (the API/CLI ``--mode`` default stays ``auto``), CLI output, source-attribution contracts, export schemas and persistent data. Explicit ``live`` mode already had no fixture fallback in the backend (``CompanyResolver.resolve`` uses fixtures only when ``mode != "live"`` and ``YahooFinanceProvider`` failure returns ``None``, which the adapter surfaces as a visible error), so no backend change was needed; the regression-fixture warning banner and provenance distinctions are preserved. ``start-st-eva.bat`` (a local launcher, committed earlier) is unaffected.

## Consensus EPS Period Provenance and Comparability (R7-1, 2026-10-12, verified by run 38246189499)

**Defect.** Yahoo declares a fiscal-period ``endDate`` for the consensus EPS it
returns (``earningsTrend.trend[].endDate``). The acquisition path discarded it and
the runner inferred twelve-month coverage from the vendor's ``+1y`` label, so
``_consensus_is_comparable`` accepted a next-*fiscal-year* estimate against the
terminal EPS of a different year. Verified live at ``83b75d5``: the MSFT
consensus ``+1y`` row ends ``2028-06-30`` while the one-year terminal window from
price date ``2026-10-09`` ends ``2027-10-09`` (**265 days** apart), yet every
one-year row reported a numeric ``gap_vs_consensus_terminal_eps``. The AAPL row
ends ``2027-09-30`` (9 days) and was, and remains, eligible.

**Change.**
- ``fundamental_provider.py``: ``_extract_consensus_forward_eps`` now returns a
  third element, the declared ``endDate`` of the row that wins the existing
  ``+1y`` then ``0y`` priority, normalised to an ISO calendar date by the new
  ``declared_date``. Row selection is unchanged. ``_consensus_observation``
  writes the date into the observation's ``period_end`` and
  ``raw["period_end"]`` and keeps the vendor label verbatim in
  ``raw["period"]``; no ``period_start`` is fabricated. ``FundamentalData``
  gained ``consensus_forward_eps_period_end``.
- ``st_eva_runner.py``: ``MarketData`` carries ``consensus_forward_eps_period_end``;
  ``_apply_observations_to_view`` restores it from the archived raw payload
  (falling back to the observation's own ``period_end``) so a replay rebuild
  recovers the same declared date; ``run_st_eva`` publishes it in
  ``data_quality``; ``_build_reverse_requirements`` derives the
  ``consensus_period_end``/``consensus_target_period_end`` pair and records an
  explicit ``UNDECLARED`` unavailable item when the source declares no end.
- ``reverse_requirements.py``: new ``terminal_period_end(as_of, years)``
  (calendar-year addition) and ``_consensus_is_comparable`` now decides on the
  *declared* date against the one-year terminal window end, within a named
  ``CONSENSUS_PERIOD_TOLERANCE_DAYS = 92``; ``build_scenario``/``build_matrix``/
  ``build_reverse_requirements_report`` thread it. Longer-horizon rejection,
  missing/non-positive consensus refusal and every published equation are
  untouched. New ``build_consensus_reference`` block states the source facts and
  the rule (no verdict, which stays per-row). ``consensus_period_end`` and
  ``consensus_period_label`` were added to ``fingerprint_payload``.
- Traceability: ``ConsensusReferenceDTO`` in ``web/schemas.py`` plus
  ``ValuationSummary.consensus_forward_eps_period_end``; a consensus panel in
  the matrix audit drawer shows the value, provider, vendor label, declared
  period end, target window end, tolerance, and the gap when comparable or a
  specific not-comparable reason naming **both** period ends;
  ``exportResult.ts`` gained six ``report_consensus_*`` CSV columns (an absent
  end stays an empty field, never a zero); i18n keys added to ``en``/``zhTW``/
  ``types``.

**Verification.**
- Targeted: ``tests/test_consensus_period_binding.py`` (46 tests plus 10
  subtests, new): extraction, observation, view/archive round-trip,
  ``terminal_period_end`` leap-day and unreadable handling, the MSFT-like
  265-day rejection with both dates in the reason, AAPL-like eligibility,
  **92 days eligible / 93 days rejected**, undeclared and unreadable
  ``endDate`` never synthesised, longer horizons intact, formula invariance
  (the only field that moves between an eligible and a rejected run is the gap,
  on one-year rows only), the five percentile choices and start-EPS provenance
  unchanged, fingerprint determinism and the expected fingerprint change.
- Also green: ``tests/test_reverse_requirements.py``,
  ``tests/test_st_eva_runner.py``, ``tests/test_msft_historical_pe.py``,
  ``tests/test_r4_web_historical_pe.py``,
  ``tests/test_reverse_requirements_wiring.py``,
  ``tests/test_r21_provenance_binding.py``, ``tests/test_research_dossier.py``,
  ``tests/test_audit_corrections.py``, ``tests/test_web_api.py``,
  ``tests/test_historical_pe.py`` and ``tests/test_browser_smoke.py`` (10,
  including the live-mode round trip on temporary archives).
- Full backend suite **2,043 passed, 169 skipped, 154 subtests passed**;
  frontend Vitest **62 passed**; production build green; ``oxlint`` reports only
  pre-existing warnings.
- **Real-provider evidence** (``create_app(archives_dir=<temp>)`` with
  ``mode=live`` against real Yahoo/SEC, run before and after the change): MSFT
  gap rows went from 20 to 0 and AAPL stayed at 20; all 80 rows per ticker are
  identical on every published field (price, required exit price, required
  terminal EPS, total growth, CAGR, growth window, exit-multiple source and
  eligibility, production distribution 24 and 36 observations), so only the
  consensus gap moved. Both tickers' fingerprints changed, which is expected
  because the declared period now takes part in the comparison.

**Replay identity (verified, not forced).** Adding
``consensus_forward_eps_period_end`` changed the **engine** result's
``data_quality`` but not the investment-context document, whose ``data_quality``
block is built separately in ``investment_context.py``. A pre-change MSFT
archive (built at ``83b75d5`` in a temporary worktree) was replayed under the
new code and reports **MATCH**. One caveat found while doing this, and
explicitly *not* caused by this task: this checkout stores three
``_POLICY_FILES`` (``core_registry.py``, ``evidence_valuation_boundary.py``,
``evidence_query.py``) with LF line endings while a fresh worktree checkout of
the same commit stores CRLF, so ``registry_identity.resolver_policy_identity``
differs between them on line endings alone. The MATCH above was observed with
that unrelated difference neutralised; with it active, replay reports DIVERGED
on ``resolver_policy_identity``. ``archive.replay``, ``observations_for``
eligibility, snapshot selection and the volatile-field ``context_id`` contract
are untouched.

**Superseded by R7-3.** That line-ending caveat is now resolved: the policy
identity digests each covered file's text rather than its bytes, so the LF
tree and the CRLF worktree of the same commit produce one identity and that
MATCH no longer needs neutralising. See the R7-3 record below.

**Boundary.** ``reverse-requirements/1.1`` keeps its identifier and every
published equation; the scenario cross-product, the price-only baseline matrix,
the production historical P/E pipeline and its thresholds, archive/replay
semantics, SEC binding and the export envelope are unchanged. The out-of-scope
items (P0 exit-multiple table label for
``production_historical_pe_percentile``, full ``unavailable`` rendering for
computed matrices, dividend/total-return UI, start-EPS period-label UI, and
summary ``Reference P/E`` reconciliation with the production distribution)
remain outstanding.


## Summary Reference P/E Reconciles with the Production Distribution (R7-5, 2026-10-13, verified by run 38338994649)

**Defect.** The summary's reference multiple was selected by
``MarketImpliedAssumptionsEngine`` from only two sources: an explicitly supplied
multiple, or the vendor historical P/E band median via
``band_median_for_reference``. The production point-in-time historical P/E
distribution — the reference the matrix's eligible exit multiples are drawn from
— reached the engine never, because ``MarketImpliedAssumptionsEngine.analyze``
was called at ``st_eva_runner.py:1762`` while the distribution was loaded at
:1797, and ``ValuationInputs`` has no field to carry it.

The consequence was a contradicting pair of records in one response: a live MSFT
run reported ``reverse_requirements.status = COMPUTED`` with 80
``production_historical_pe_percentile`` / ``ELIGIBLE_PRODUCTION_DISTRIBUTION``
scenarios and ``production_historical_pe_summary.usable_for_reference = true``
with 24 observations, while ``valuation_summary.selected_pe_basis`` reported
``none`` and ``selected_pe`` was ``None``. R5 had documented that as a correct
coexistence, and R7-0 reclassified it as a quality gap.

**Change.**
- ``st_eva_runner.py``: new ``production_pe_for_reference`` reads the
  distribution's **own** ``usable_for_reference`` flag and its **own**
  ``percentiles["median"]``. It deliberately does not re-derive eligibility from
  the vendor band's ``observations >= 20`` rule, and does not recompute the
  median from the band or today's price, so the summary cannot report a
  reference the matrix was refused under. ``analyze`` accepts
  ``production_historical_pe`` and applies an explicit precedence: (1) a
  user-supplied multiple with its ``user_supplied_multiple`` provenance,
  (2) the eligible production distribution's median, reported as
  ``production_historical_pe_median``, (3) the eligible vendor band median,
  (4) nothing. The distribution load was hoisted above the engine call; it is
  pure (it reads the committed dataset and writes nothing), so no other ordering
  changed. The ``reference`` block gains
  ``production_historical_pe_status`` so a reader can tell an eligible reference
  from a descriptive one; the sample count and observation period stay in the
  report's existing production-distribution summary rather than being
  duplicated.
- ``investment_context.py``: the Investment Context's ``valuation_reference``
  derived its ``basis`` from which number happened to be present, which would
  have recorded a production median as a vendor-band median and pointed
  ``source_ref`` at the band — the false provenance claim that module's own
  docstring warns about. The basis is now read from the engine's
  ``reference.method`` and a new ``PRODUCTION_PE_MEDIAN`` basis states its own
  eligibility rule, keeps ``source_ref`` null, and produces a matching
  limitation line. The pre-existing ``HISTORICAL_MEDIAN``, ``USER_SUPPLIED`` and
  ``NONE`` outputs are unchanged.
- ``report_formatter.py``: ``METHOD_LABELS`` gains the new basis.
- ``web/frontend``: ``selected_pe_basis`` documents the new value;
  ``ResultCards.tsx`` adds a branch so the ``Reference P/E`` basis legend names
  the production historical P/E distribution median and points at the existing
  production-distribution section for the qualified sample size and observation
  period, rather than duplicating them; ``referencePeBasisProduction`` added to
  ``en``, ``zh-TW`` and the shared type.

**Verification.**
- **Real-provider evidence.** ``create_app(archives_dir=<temp>)`` +
  ``mode=live``, real Yahoo/SEC. Before: MSFT and AAPL both reported
  ``selected_pe_basis = none``, ``selected_pe = None``. After: MSFT reports
  ``selected_pe = 33.195873`` with ``production_historical_pe_median`` and a
  24-observation distribution spanning 2021-07-28 to 2026-07-30; AAPL reports
  ``28.44563`` with ``production_historical_pe_median`` and 36 observations
  spanning 2018-01-02 to 2026-07-31. In both cases
  ``selected_pe`` equals the distribution's own median, which is also the centre
  of the matrix's exit multiples, and
  ``forward_eps_at_reference_multiple == current_price / selected_pe``. A live
  run with ``reference_multiple = 30.0`` still reports
  ``user_supplied_multiple`` and 30.0.
- **The matrix is unchanged, verified rather than asserted.** A temporary
  worktree at ``6283026`` ran the same regression-mode submissions through the
  same API and every scenario row, the exit multiples with their eligibility
  states, the unavailable list, the matrix status and the formula version were
  compared: **byte-identical** for MSFT (COMPUTED, 160 rows) and AAPL (COMPUTED,
  80 rows). The values are pinned permanently in
  ``tests/test_summary_reference_precedence.py::TestTheMatrixIsUnchanged``.
- **Regression tests.** New ``tests/test_summary_reference_precedence.py`` (21
  tests, 9 subtests): the eligibility gate and median both read from the
  distribution; an eligible distribution yields its own median; a user-supplied
  multiple keeps precedence; an eligible vendor band remains the fallback; the
  production median wins over an eligible band; an ineligible distribution falls
  back to the band; no eligible reference stays unavailable with no fabricated
  growth or consensus gap; a thin vendor band is not a reference; a
  descriptive-only distribution never qualifies; the engine's no-distribution
  default path is unchanged and the legacy-view and contract paths agree; the
  published exit-price, terminal-EPS and total-growth equations still hold; the
  matrix equals the pre-change baseline; the summary and the matrix agree on the
  median.
  ``tests/test_investment_context.py`` gains
  ``test_a_production_median_is_not_recorded_as_a_band_median``.
  ``web/frontend/src/test/ResultCards.test.tsx`` gains the production basis in
  English and Traditional Chinese, including that the sample size and period are
  pointed at rather than duplicated.
- Frontend Vitest **78 passed (8 files)**; production build green;
  ``npx tsc -b`` clean; ``oxlint`` reports only pre-existing warnings.
- Browser smoke **12 passed, 2 reruns**. The full backend suite is **2,074
  passed, 169 skipped, 163 subtests**. Under the same machine load the *parent
  commit* fails 12 browser tests with 24 reruns, so browser-smoke timing here is
  load-sensitive and pre-existing, not caused by this change; the affected test
  passes alone in 17s.
- **GitHub Actions:** run 38338994649 for 1499fd4,
  ``backend`` and ``browser`` jobs both passed.

**Boundary.** ``reverse-requirements/1.1`` keeps its identifier and its
published equations; the scenario cross product, the matrix, the production
historical P/E pipeline and its eligibility threshold, acquisition sources,
evidence eligibility, validation rules, the contents of ``report.unavailable``,
consensus-period comparability and its fingerprint, registry/policy identity,
archive and replay semantics, snapshot selection, API/export schema and
persistent datasets are unchanged. Nothing was combined with the
dividend/total-return UI, start-EPS period labels, additional valuation models,
LLM integration or caching.

**Outstanding from R7-0 (unchanged).** dividend/total-return display and
start-EPS period-label UI.


## Supporting-Data Limitations for a Computed Matrix (R7-4, 2026-10-13)

**Defect.** `reverse_requirements_report` records the supporting inputs it could
not use in `report.unavailable` -- an ineligible vendor P/E band, unavailable
valuation-method references, missing SEC dividend data, an unmodelled cost of
equity -- and the API and the CSV both carry that list. The matrix component
rendered it **only inside the `isNotComputed` banner**, so a live MSFT run can
show 80 computable scenarios beside an amber "Not Computed"-free matrix and
never mention that the vendor band was rejected for insufficient observations
or that no SEC dividends were acquired. The record reached the export and
nowhere else a reader looks.

**Change.** `ReverseRequirementsMatrix.tsx` plus the minimum i18n. The
`report.unavailable` rendering was extracted into one `UnavailableList`
component and is now shown in two places, never both:

- **COMPUTED** -- a new clearly-labelled *Supporting data and method
  limitations* section above the filters, toned slate rather than amber so it
  reads as a limitation and not a failure. Its subtitle states that the
  unavailable inputs were not used, that the scenarios are unaffected by their
  absence, and that an unavailable reference is a named absence rather than a
  zero.
- **NOT_COMPUTED** -- unchanged in substance: the existing banner, its status
  explanation, and the list rendered once inside it. The standalone section is
  suppressed in that state, so nothing is duplicated.

Each entry is shown with the `item` the report names and the exact `reason` the
report gave, falling back to a localised "Unnamed item" placeholder when the
item is missing and to a JSON dump only when there is no reason at all. An empty
or absent list renders nothing, because the guard is a length test rather than a
truthiness test. The list has one source, `report.unavailable`, so the UI, the
API and the CSV cannot disagree.

`docs/PROJECT-STATUS.md`, the four new i18n keys (`unavailableInputsLabel`,
`unavailableItemFallback`, `computedLimitationsNotice`,
`computedLimitationsSubtitle`) in `en`, `zh-TW` and the shared type, and two new
`data-testid` hooks are the whole surface. No DTO change was needed: the
existing `unavailable` shape (`item`, `reason`, `reason_kind`, `blocks`) was
already sufficient.

**Verification.**
- `web/frontend/src/test/ReverseRequirementsMatrix.test.tsx`: a new
  `supporting-data limitations section` suite covers a COMPUTED report showing
  every supplied item and reason, the "named absence rather than a zero" wording
  alongside still-rendered scenarios, NOT_COMPUTED rendering the list exactly
  once inside its banner with no duplicated standalone section, an empty list
  rendering nothing, an absent list rendering nothing, the `zh-TW` rendering,
  the `Unnamed item` fallback, and unchanged rows, filters, calculation traces,
  exit-multiple source labels and the consensus panel.
- The tests catch the defect: with the computed branch disabled, 4 of them fail.
- **Real-provider evidence** through the actual SPA path. `tests/test_browser_smoke.py`
  gains two tests against real headless Chromium: one runs the offline MSFT
  regression fixture, whose report is deterministically COMPUTED with 160
  scenarios **and 7 unavailable entries**, and asserts the section, the exact
  `No P/FCF reference multiple was supplied` and `No SEC regulatory filing
  observations of declared dividends` reasons, that the section appears exactly
  once, and that the audit drawer still opens; the other runs the deterministic
  TSM refusal, whose report is NOT_COMPUTED with 9 entries, and asserts the list
  renders exactly once inside the banner with no standalone section.
- Frontend Vitest **76 passed (8 files)**; production build green;
  `npx tsc -b` clean; `oxlint` reports only pre-existing warnings (the former
  unused-import warning for `AlertCircle` is resolved by its use here).
- Browser smoke **12 passed, 1 rerun** with the CI's `--reruns 2 --reruns-delay 15`
  flags. The rerun is the live-acquisition flake CI already tolerates.
- **GitHub Actions:** run 38328880219 for e2c8e16, `backend` and
  `browser` jobs both passed.

**Boundary.** No `reverse-requirements/1.1` formula or scenario generation,
acquisition source, evidence eligibility, validation rule, the contents of
`report.unavailable`, consensus-period comparability or its fingerprint,
historical P/E data or eligibility threshold, registry/policy identity, archive
or replay semantics, snapshot selection, API or export schema, persistent
SQLite/WAL/SHM dataset or previous output was changed. Nothing was combined with
the dividend/total-return UI, start-EPS period labels, summary `Reference P/E`
reconciliation, additional valuation models, LLM integration or archive cleanup.

**Outstanding from R7-0 (unchanged).** dividend/total-return display, start-EPS
period-label UI, and summary `Reference P/E`` reconciliation with the production
distribution.


## Resolver Policy Identity Across Line Endings (R7-3, 2026-10-12, verified by run 38303209687)

**Defect.** ``registry_identity._file_sha256`` hashed each covered policy file
with ``read_bytes``, so a checkout's newline convention decided the resolver
policy identity. ``core.autocrlf`` is true in this repository and there is no
``.gitattributes``, so one commit checks out CRLF on one machine and LF on
another. Measured on ``615d3cd``: three of the six ``_POLICY_FILES``
(``core_registry.py``, ``evidence_valuation_boundary.py``, ``evidence_query.py``)
were LF in the operator's tree and CRLF in a fresh worktree of the same commit,
**byte-identical after newline normalisation**, which made the two trees yield
``pol:684c9c3c...`` and ``pol:4fdbd1eb...`` and report DIVERGED on
``resolver_policy_identity`` for code that had not changed. The same
discrepancy was reported as a caveat in the R7-1 record above.

**Change.** ``registry_identity.py`` only.
``_file_sha256`` now reads each file as UTF-8 text before hashing, so CRLF, LF
and a lone CR all arrive as LF. This is the canonicalisation the archive layer
has always applied to migration files -- ``sqlite_archive.py:450-451`` reads
them with ``read_text`` before hashing, so a newline-only edit does not abort
startup -- and reusing it keeps the recorded migration checksums and this
digest comparable. It also closes a latent inconsistency: with no connection
the applied-migration identity digested raw bytes while the connection path
read checksums computed from normalised text, so the two branches disagreed on
an LF/CRLF mismatch.

The policy manifest, its order, every other identity input, the policy loading,
evaluation, resolver behaviour, replay selection rules, the
``FileNotFoundError`` for a missing covered file and the replay comparison
itself are unchanged. Nothing is forced to MATCH and no mismatch is ignored.

**Verification.**
- **Reproduction before the fix**: operator tree vs fresh worktree of one commit
  gave two different identities; after the fix both give
  ``pol:b93bca7cafbe035e98ebdb3d943df99bacfb4bace2e6cca97c4ea5f721db06ac``.
- **Regression tests** in ``tests/test_registry_identity_331.py``: LF / CRLF and
  lone-CR mirrors share one identity; determinism; a changed constant still
  moves the identity; a comment-only addition still moves the digest (the
  deliberate cheap direction); the applied-migration identity is
  newline-insensitive on both branches. A new
  ``TestReplayAcrossEquivalentCheckouts`` class runs a real temporary archive:
  an LF mirror and a CRLF mirror agree on the identity, replay across them
  reports **MATCH** with ``resolver_policy_identity`` absent from the reason, and
  a real change to ``core_registry.py`` still reports **DIVERGED** with
  ``resolver_policy_identity`` named.
- **The tests catch the defect**: with ``read_bytes`` temporarily restored, 4 of
  them fail, including the replay MATCH case. The fix was re-applied afterwards
  and the suite re-run.
- Also green: ``tests/test_replay_evidence_symmetry.py``,
  ``tests/test_replay_wiring_332.py``, ``tests/test_admission_persistence_332.py``,
  ``tests/test_r6_replay_divergence.py``,
  ``tests/test_r6_1_replay_snapshot_identity.py``, ``tests/test_archive_isolation.py``,
  ``tests/test_core_registry.py``, ``tests/test_evidence_query.py``,
  ``tests/test_evidence_valuation_boundary.py``, ``tests/test_web_api.py``.
- Full backend suite **2,050 passed, 169 skipped, 154 subtests passed**; the
  browser suite **10 passed** on re-run and separately with the CI's
  ``--reruns 2`` flags. ``tests/test_registry_identity_331.py`` **33 passed** when
  the historical-state corpus is regenerated (only ``head`` remains
  MATERIALIZABLE, as before).
- **GitHub Actions:** run 38303209687 for ``bb5e5e8``, ``backend`` and
  ``browser`` jobs both passed.

**Consequence of changing a digest function.** The identity value itself moves
for identical policy content, which is unavoidable for any change to a digest
function and is the same class of event as a change to the covered files.
Existing archives already diverge: their stored identities
(``pol:9e7a883b...``, ``pol:d9c955b7...``) match neither the old nor the new
function's output at HEAD content, and an A/B replay of ``data/archives/MSFT.sqlite``
under temporary copies diverges identically before and after this change. So no
new divergence is introduced; the removed one was the LF/CRLF case.

**Boundary.** ``reverse-requirements/1.1``, source provenance, consensus-period
comparability, historical P/E eligibility, unrelated scenario fingerprints,
archive storage format, archived evidence, ``context_id``, snapshot selection and
the replay semantics beyond this identity are unchanged. No persistent SQLite,
WAL/SHM, historical P/E dataset or existing output was modified; every replay
read a temporary copy. The outstanding R7-0 UI items (computed-matrix
``unavailable`` list, dividend/total-return display, start-EPS period-label UI,
summary ``Reference P/E`` reconciliation) are untouched.


## Matrix Exit-Multiple Source Labels (R7-2, 2026-10-12, verified by run 38264080875)

**Defect.** The reverse-requirements matrix table cell rendered `User` for
`user_supplied` and `Band` for every other source. Live AAPL/MSFT scenarios use
`production_historical_pe_percentile` with `ELIGIBLE_PRODUCTION_DISTRIBUTION`, so
every row on the default path attributed its reference to a vendor band that was
not used. The audit drawer already named the source correctly through
``multipleSourceLabel``; the table did not read it.

**Change.** ``ReverseRequirementsMatrix.tsx`` only. The table cell now calls
``multipleSourceLabel(t, sc.exit_multiple, true)``, a compact form of the helper
that already exists and names the source, so the row and its drawer read the one
source mapping:

- ``production_historical_pe_percentile`` -> ``productionDistributionName``
  ("Production point-in-time historical P/E")
- ``historical_pe_band_percentile`` -> ``vendorPeBandName`` ("Vendor historical P/E band")
- ``user_supplied`` -> ``userSpecifiedBadge`` ("User Assumption")
- any other or absent source -> the raw source identifier, which keeps an
  unrecognised or unverifiable source from being presented as a valid band

The drawer's prefixed, period-bearing form is unchanged. No new label was
introduced: both variants read the existing ``en``/``zhTW`` ``matrix`` keys, and
nothing is hardcoded in the component. No calculation, formula,
``reverse-requirements/1.1``, eligibility threshold, API schema, provenance
contract, fingerprint, acquisition source, historical P/E dataset, archive or
persistent file was touched.

**Verification.**
- ``web/frontend/src/test/ReverseRequirementsMatrix.test.tsx``: a new
  ``exit-multiple source label in the matrix table`` suite asserts the label
  for production distribution (including one row using
  ``production_historical_pe_percentile``), user-supplied values, vendor bands,
  an unrecognised source, the ``zh-TW`` rendering, and that the drawer's
  prefixed form is unchanged. Each production and user case also asserts the
  literal ``Band`` is absent.
- Frontend Vitest **68 passed (8 files)**; production build green;
  ``npx tsc -b`` clean; ``oxlint`` reports only pre-existing warnings, none on
  the changed lines.
- ``tests/test_browser_smoke.py``: **10 passed** (real Chromium, temporary
  archive directory).
- **Real-provider evidence.** A one-off headless-Chromium run of the built SPA
  against a live ``MSFT`` analysis (``create_app(archives_dir=<temp>)``) rendered
  all 80 matrix rows with the sub-label ``Production point-in-time historical
  P/E``; the string ``Band`` did not appear anywhere in the page body. This is
  what closes the gap the R7-0 audit found, where the component existed but the
  live path was not proven. The probe was not committed; the permanent
  regression coverage is the Vitest suite above.
- **GitHub Actions:** run 38264080875 for ``90eb731``, ``backend`` and
  ``browser`` jobs both passed.

**Outstanding from R7-0 (unchanged, deliberately not combined here).** the
computed-matrix ``unavailable`` list, dividend/total-return display, and summary
``Reference P/E`` reconciliation with the production distribution. The
``resolver_policy_identity`` LF/CRLF replay caveat was reopened and closed as
R7-3 below and is no longer outstanding.


## Starting EPS Period Basis Explicit in UI and CSV (R7-6, 2026-10-13, commit c112e18)

**Objective.** R7-0 confirmed that a live Yahoo `trailingEps` value is received as a
numeric value without a source-declared period end or explicit period coverage.
ST-EVA currently represents the selected starting EPS as trailing twelve months when
using the trailing anchor, and the API already carries `period_undeclared_by_source`
and `period_label`. However, the matrix audit drawer displayed `Coverage: 12 months`,
which could be mistaken for source-declared evidence. The task was to improve
disclosure and traceability of existing metadata without changing the EPS value or
inferring new dates.

**Changes.**

- **UI disclosure** (`ReverseRequirementsMatrix.tsx`): In the Starting EPS Anchor
  section of the matrix audit drawer:
  - Display `period_label` when present.
  - When `period_undeclared_by_source === true`, explicitly state "Period basis
    assumed by ST-EVA (not declared by provider)" (localized).
  - Distinguish "Assumed coverage (not declared by provider)" from "Provider-declared
    coverage"; the 12-month figure is never presented as independently declared by
    the provider.
  - Show `period_start` and `period_end` when available; when unavailable, display
    "undeclared" (localized). Dates are never inferred from `TRAILING_TWELVE_MONTHS`
    or the numeric coverage.
  - When the source declares a period and `period_undeclared_by_source` is false,
    show the declared metadata faithfully without the assumed-period warning.
  - User-supplied EPS remains clearly identified as a user assumption (`is_user_assumption`
    badge) with its period metadata shown in the same framework.

- **CSV traceability** (`exportResult.ts`): Four new columns added to the existing
  scenario-row CSV:
  - `start_eps_period_label`
  - `start_eps_period_undeclared` (boolean)
  - `start_eps_period_start`
  - `start_eps_period_end`
  Populated from `scenario.start_eps` evidence; missing values remain empty fields
  per existing conventions (no zeros, no fabricated dates, no inferred declarations).

- **i18n** (`en.ts`, `zhTW.ts`, `types.ts`): Added English and Traditional Chinese
  strings for all new disclosure labels and warnings.

- **Tests**:
  - Frontend (`ReverseRequirementsMatrix.test.tsx`): 7 new focused tests covering
    assumed-period disclosure, no-implied-declaration, declared-period metadata,
    user-supplied EPS identification, no date fabrication, and both language renderings.
  - CSV export (`ExportResult.test.ts`): 4 new tests verifying the four new columns
    export correctly for vendor trailing, SEC-linked, vendor forward, user-supplied,
    declared-period, and undeclared-period scenarios.
  - All frontend Vitest **89 passed (8 files)**; TypeScript build clean; production
    build green.
  - Backend reverse-requirements, provenance, and instant-observation suites **120
    passed**.

**Boundary.** No change to the selected starting EPS value or selection priority,
source acquisition, `reverse-requirements/1.1` formulas, growth window or scenario
generation, consensus-period comparability, historical P/E data or eligibility,
investment-context basis, archive/replay/registry semantics, or dividend/total-return
UI. The formula and selected EPS value remain unchanged.

**GitHub Actions:** To be verified on next CI run; all local test suites and builds pass.


## Dividend & Total-Return Comparison Exposed in UI (R7-7, 2026-10-13, commit a074494)

**Objective.** R7-0 found that the API/report contract already carried `dividend_basis`,
`total_return_scenarios`, and `price_vs_total_return_comparison` fields, but these
were not meaningfully presented in the browser. The baseline reverse-requirements
matrix is strictly price-return-only; when a dividend per share is supplied, two
parallel total-return scenario sets are computed (cash-retained and reinvested).
The task was to expose these existing calculations in the web UI so users can
distinguish price-return-only assumptions from dividend-adjusted scenarios.

**Changes.**

- **UI display** (`ReverseRequirementsMatrix.tsx`): A new "Dividend & Total-Return
  Comparison" section appears below the matrix table (for COMPUTED reports only):
  - When `dividend_basis` is present: shows dividend per share using
    `dividend_basis.dividend_currency` (falls back to the report's currency prop),
    the dividend period label "TTM" (past 12 months) from
    `dividend_basis.dividend_period` **only when that field is actually provided**,
    source, and both convention definitions with their formulas
    (`P_T = P_0 × (1 + r)^T − T × D` for cash-retained;
    `P_T = P_0 × (1 + r)^T − D × ((1 + r)^T − 1) / r` for reinvested).
  - When `price_vs_total_return_comparison` is present: renders a comparison table
    with columns for Horizon, Req. Return, Exit Multiple, and three variant groups:
    Price Return Only (baseline), Cash Dividends Retained (with Δ columns), and
    Dividends Reinvested at Target Return (with Δ columns). All values use the
    existing computed figures; no new calculations are introduced.
  - When no `dividend_basis`: shows "No dividend input was supplied for this run.
    The baseline matrix is price-return-only." with the "Price return only
    (baseline)" label.
  - When `status = NOT_COMPUTED`: the dividend section is not rendered.

- **Reading notes corrected** (`reverse_requirements.py`, `st_eva_runner.py`):
  - "The baseline reverse-requirements matrix is strictly price-return-only; required
    returns exclude dividends."
  - "When a dividend per share is supplied, two additional scenario sets are computed:
    cash dividends retained and dividends reinvested at the target return."
  - Removed the ambiguous wording "A required return is a price return unless a
    dividend was supplied as an input" that could imply the baseline matrix changes.

- **i18n** (`en.ts`, `zhTW.ts`, `types.ts`): Added English and Traditional Chinese
  strings for all new labels, formulas, conventions, and the dividend period label.

- **Tests** (`ReverseRequirementsMatrix.test.tsx`): 12 new focused tests covering:
  dividend-not-available message, dividend basis display with period and currency,
  non-USD currency display (EUR) using `dividend_currency`, fallback to `currency` prop
  when `dividend_currency` is missing, conditional dividend period label (only shown
  when `dividend_period` is provided), comparison table rendering, both language
  renderings, and NOT_COMPUTED suppression.

**Verification.**
- Frontend Vitest **99 passed (8 files)**; TypeScript clean; production build green.
- Backend dividend, reverse-requirements, and provenance suites **121 passed**.
- No changes to `reverse-requirements/1.1` formulas, baseline matrix values,
  dividend acquisition, or any other engine component.

**Boundary.** The baseline matrix remains strictly price-return-only. The total-return
scenarios are parallel, explicitly labelled, and their deltas are shown relative to
the baseline. No dividend is double-counted or silently added to the price-only
required-return calculation. Unavailable dividend inputs display their supplied
reason (via `report.unavailable`) and never become zero.

**GitHub Actions:** Implementation commit `a074494` verified by [Run 38353151137](https://github.com/sbvcid/st-eva/actions/runs/38353151137) (`backend` and `browser` jobs both passed); docs commit `a386272` verified by [Run 38353390189](https://github.com/sbvcid/st-eva/actions/runs/38353390189) (`backend` and `browser` jobs both passed).


## Multi-Company Research Workflow Acceptance (accepted 2026-10-15, commits 66611ec..37262ae + web wiring)

**Objective.** Verify that the existing capability set — acquisition, historical
P/E reference, historical P/FCF reconstruction, consensus revisions/trend, and
current-price reverse assumptions — composes into one consistent, readable,
traceable per-ticker research workflow, and that it reuses across companies
without cross-contamination. Product positioning unchanged: traceable facts,
deterministic calculations and price-implied assumptions; no ratings, forecasts
or automatic multiple selection.

**What was built and verified in this milestone.**

- **Consensus revisions & trend extraction** (`66611ec`): the quoteSummary
  `epsRevisions` and `epsTrend` blocks are extracted for the selected consensus
  row — up/down revision counts (unit count, no currency), the trend series
  (current + 7/30/60/90-days-ago), and four deterministic in-series differences
  (current minus each snapshot). Relative source labels are kept verbatim; an
  empty `downLast90days` block stays UNAVAILABLE, never zero.
- **Historical P/FCF reconstruction without the vendor band** (`fd311c5`,
  `historical_pfcf.py`, methodology `historical-pfcf/1.0`): TTM FCF from filed
  cumulative cash-flow statements (discrete quarters differenced from stated YTD
  durations, never summed), the canonical daily price series, and cover-page
  shares outstanding; point-in-time knowability with R-PIT-SUPERSEDE restatement
  handling; the same >= 20 gate. AAPL: 35/36 valid, median 25.3440,
  USABLE_FOR_REFERENCE. The vendor cap was reconciled to its quarter-grid stamp
  (2026-09-23) and the two market-cap bases are documented separately.
- **MSFT cross-ticker validation** (`37262ae`): the same pipeline reused with
  only an issuer config (fye_month=6) and a same-shaped dataset — 24/27 P/E
  and 23/27 P/FCF observations, both USABLE_FOR_REFERENCE. No pipeline logic
  changed; every finding was classified source-difference vs program-defect,
  and no new defect was found.
- **Multi-company workflow acceptance (this task)**: the one real usage gap
  found was that the web path enabled the P/E reference but not the P/FCF
  reference. Minimal wiring added: `include_historical_pfcf=True` in the
  service adapter, a slimmed `production_historical_pfcf` in the visible
  result, `ProductionHistoricalPfcfSummaryDTO`, `selected_pfcf` /
  `selected_pfcf_basis` / `implied_fcf_at_reference_multiple` on
  `ValuationSummary`, and a matrix-section P/FCF summary block mirroring the
  P/E one (plus summary-card basis legend and i18n). Tests:
  `test_production_pfcf_reference_flows_through_the_web_path` and
  `test_references_are_isolated_per_ticker` (sequential AAPL/MSFT adapter runs
  assert each ticker carries only its own references — medians 25.3440 vs
  41.578319, period starts 2018-02-02 vs 2021-07-30). Full suite 2,227 passed /
  169 skipped; frontend build clean.

**Research artifacts** (all under `history/`): AAPL v1 snapshot
(`AAPL_RES-4DC3AD389D_*`), AAPL historical-references + scenarios artifact with
20 consistency checks, AAPL acceptance report; MSFT snapshot
(`MSFT_RES-B35CA79AA4_*`), cross-ticker validation artifact with 23 checks,
validation report; both companies' dossiers with the 80-scenario matrix.

**Still not supported / open by design.** The consensus cross-check field reads
only the vendor band (recorded method-scope gap); `down_revisions_90d` is
source-absent for both companies; the matrix's cash-flow/EV/revenue methods
require explicitly supplied multiples; historical multiples in any output are
conditional scenarios, never a selected answer. Known limitations of the P/FCF
reconstruction (OCF FY2016 Q1 hole for AAPL, comparative-later knowability,
finance-lease boundary for MSFT) are recorded in the dataset manifests.

## Declared SEC Diluted-EPS Evidence (added 2026-10-16, commit `50043be`, verified by run `38862119614`)

**Gap this closes.** A live run's vendor EPS anchor declares no period coverage
and no accounting basis, and the only period-declared alternative visible in
the output — the per-scenario `related_sec_evidence` record — was read from the
packaged datasets under `data/historical_pe/{TICKER}`, which exist for `AAPL`
and `MSFT` only. Every other ticker had no filing-side period or basis anywhere
in the report, even when the run had already acquired the issuer's SEC facts,
and no scenario row carries evidence at all when the matrix is not computed.
Two cross-company research records (`IBKR` MU Phase 3 and the MSFT cross-case)
independently recorded the consequence: an anchor figure with an undeclared
period and an unreported GAAP/non-GAAP basis next to a filed figure the report
never showed.

**What changed (`st_eva_runner.py`; no calculation, no admission, no new
network).**

- The reverse-requirements report now carries `declared_eps_evidence`, built
  from *this run's own SEC acquisition* when it ran: the latest directly
  stated 10-K fiscal-year fact and the latest directly stated 10-Q quarter fact
  of `us-gaap:EarningsPerShareDiluted` by period end (ties broken by covered
  span, then filed date, then accession), each with value, currency, unit,
  concept, accession, form, fiscal period/year, filed date, acceptance time
  and source URL. Derived windows (FY-minus-YTD roll-forwards, summed
  quarters) are excluded by the observation's own `derivation` marker: they
  are the acquisition's arithmetic, not the filer's statement.
- Per-scenario `related_sec_evidence` now prefers this run's acquisition and
  keeps the packaged dataset as the fallback, so a run that acquired no filing
  evidence behaves exactly as before. The record shape is unchanged, R2.1 is
  untouched, and the record remains cross-check evidence that never becomes
  the source of the selected anchor.
- Three explicit states, nothing filled in: `AVAILABLE` (names the facts and
  whether they came from `RUN_ACQUISITION` or `PACKAGED_DATASET`),
  `UNAVAILABLE` (the acquisition asked and the source reported none), and
  `NOT_ACQUIRED` (this run never asked and no packaged dataset exists; the
  reason names `--context` as the way to acquire them). The block is evidence
  only: every computed row, the fingerprint, the `unavailable` list and the
  anchor contract are unchanged, and no new request is made to fill it.

**Case evidence (2026-10-16, live acquisition, three issuers; full before/after
pairs preserved in the IBKR research repository under
`research/st-eva-declared-eps/20261016-133400/`).**

- `MU`: `related_sec_evidence` was `null` and now carries the FY2026 10-K fact
  (74.33, 2025-08-29..2026-09-03, accession `0000723125-26-000023`, filed
  2026-10-09), with interim Q3 24.67 (`0000723125-26-000015`); the block states
  both. The vendor anchor still reports "period coverage was not declared by
  source" and no direct SEC source — the declared fact is cross-check only
  even where the values coincide.
- `AAPL`: the per-scenario record stays the FY2025 10-K fact (7.46), now
  supplied by the run's own acquisition, and the block adds the interim Q3
  FY2026 fact (2.02, 2026-03-29..2026-06-27) that no output carried before.
- `MSFT`: the block states FY2026 (17.95) and Q3 (4.27); the anchor's 17.82
  stays declared as vendor-undeclared rather than "corrected" to either.
- Regression: nine before/after run pairs (basic / context / context+multiple
  per issuer). Every computation row is identical; the only new report key is
  `declared_eps_evidence`.

**Tests.** `tests/test_declared_eps_evidence.py` (20 tests): identity refusal
for incomplete records, derived-window exclusion, deterministic selection
including the longer-cumulative tie case, live-over-frozen preference,
fallback when only interim facts exist, a ticker with no source at all, the
three block states, the per-scenario flow with R2.1 preserved, the
unchanged-calculation check, and the regression path. Full backend suite
**2,272 passed, 169 skipped, 488 subtests passed (240 s)**. CI run
`38862119614`: backend and browser jobs success. No persistent database was
written; every run used a temporary context path.

**Boundary.** The ISO-week/53-week, restatement and per-share-additivity
questions TTM construction must answer are untouched: this block states filed
annual and quarterly facts with their periods; it does not build a TTM, does
not rank or reconcile the vendor figure against them, and does not widen the
`evidence_valuation_boundary` admission (still `revenue` only).

## MU historical P/E and M2 TTM EPS evidence round (2026-10-17)

**Question.** Can MU build a qualified historical P/E reference distribution,
and can a traceable TTM EPS be established for the latest complete four-quarter
period?

**Answers in one line.** Historical P/E: yes — `USABLE_FOR_REFERENCE`, 335
valid observations, 2019-03-21 to 2026-08-31, median 21.549505, 20-observation
gate untouched. M2 TTM at the latest date: the four quarterly facts all exist
and are traceable, but the existing fiscal-position rules cannot assemble them
into a window; the exact blocking condition is recorded below and nothing was
relaxed.

### 1. The Q4 evidence (new dataset, `data/historical_pe/MU/q4_evidence_records.json`)

MU stopped tagging Item 302 quarterly data in 10-Ks after FY2020, so fiscal
Q4s from FY2021 on have no quarter-length `us-gaap:EarningsPerShareDiluted`
fact. The Q4 values are directly stated in the earnings releases furnished as
8-K Item 2.02 EX-99.1 exhibits. Each record: GAAP column of the Quarterly
Financial Results table, equal to the headline GAAP per-diluted-share figure,
different from the exhibit's twelve-month figure and from the quoted non-GAAP
figure (recorded as quoted-but-not-used); period end stated in the release's
own text and equal to the 10-K annual fact's span end; SGML-header acceptance
time in ET; usable date = next trading day (every release accepted
16:00:27–16:02:28 ET, after the 16:00 cutoff); content sha256 of the exhibit
bytes. FY2016–FY2020 Q4s need no 8-K record: 10-K quarter-length facts already
fill those positions. Study tooling (fetch/build/verify, offline replay) and
frozen sources live in the git-ignored
`research/experiments/mu-historical-pe-q4-study/`; the promote tool is
`tools/promote_mu_q4_evidence.py`.

| Fiscal Q4 | Period end | GAAP diluted EPS | Accession | Accepted (ET) | Usable |
| --- | --- | --- | --- | --- | --- |
| FY2021 | 2021-09-02 | 2.39 | 0000723125-21-000060 | 2021-09-28 16:01:35 | 2021-09-29 |
| FY2022 | 2022-09-01 | 1.35 | 0000723125-22-000044 | 2022-09-29 16:00:31 | 2022-09-30 |
| FY2023 | 2023-08-31 | -1.31 | 0000723125-23-000051 | 2023-09-27 16:00:28 | 2023-09-28 |
| FY2024 | 2024-08-29 | 0.79 | 0000723125-24-000023 | 2024-09-25 16:00:27 | 2024-09-26 |
| FY2025 | 2025-08-28 | 2.83 | 0000723125-25-000024 | 2025-09-23 16:02:28 | 2025-09-24 |
| FY2026 | 2026-09-03 | 32.87 | 0000723125-26-000018 | 2026-09-30 16:02:22 | 2026-10-01 |

### 2. The acceptance-time defect (corrected, `filing_acceptance_evidence.json`)

The file's `acceptance_datetime_header_et` values were EDGAR submissions-API
`acceptanceDateTime` strings, which serialize true UTC **plus** the Eastern
UTC offset of the acceptance instant (a double-DST artifact), suffixed `Z`.
Read back as UTC — what the loader does — they ran 4h (EDT) / 5h (EST) late,
pushing afternoon acceptances past the 16:00 ET cutoff and mis-dating 65 of
1003 usable dates, including 23 of the 37 filings that carry quarter/annual
EPS facts. The rebuild stores true ET for all 1003 rows: SGML-header
authoritative for the 43 evidence-relevant accessions, a deterministic offset
correction (validated to reproduce all 43 SGML values) for the rest, with the
original API value kept per row under `acceptance_datetime_submissions_api`
and an explicit `acceptance_datetime_basis`. The row set is unchanged.
EDGAR's own filing index pages ("Accepted 2026-09-30 16:02:22") confirm the
SGML value is the acceptance wall clock in ET.

### 3. The window-continuity guard (`historical_pe.py`)

Filling the four fiscal positions is not sufficient for a TTM window: the
month-grid quarter mapping can fill all four positions with period ends that
skip a real quarter (a 182-day gap), because 52/53-week filers' quarter ends
drift across month boundaries (MU's June quarter ends and early-September
fiscal year ends map onto the wrong slots). `build_historical_pe` now refuses
such windows with `REASON_INSUFFICIENT_QUARTERS` and an explicit gap detail,
in both the dated loop and the current snapshot. This corrected two
pre-existing defective AAPL observations (2018-05-03 and 2024-05-03 skipped
the actual summer quarter); AAPL baselines were independently recomputed:
furnished 30→28 valid (median 27.805696→28.286075, excluded 6→8), filed-only
18→14 (excluded 18→22). MSFT is unaffected (all its windows are consecutive
calendar quarters; its reproducibility tests pass unchanged).

### 4. Before/after on the real MU dataset

| Metric | Before | After |
| --- | --- | --- |
| Valid TTM observations | 136 / 585 | 335 / 575 |
| Distribution status | USABLE_FOR_REFERENCE | USABLE_FOR_REFERENCE |
| Period | 2017-10-27 → 2021-12-31 | 2019-03-21 → 2026-08-31 |
| Median / mean | 15.324275 / 14.135639 | 21.549505 / 25.60395 |
| Excluded (MISSING_Q4 / INSUFFICIENT / NON_POSITIVE) | 198 / 165 / 86 | 48 / 164 / 28 |
| Current snapshot (2026-10-16) | UNAVAILABLE, MISSING_Q4_EPS | UNAVAILABLE, MISSING_Q4_EPS |

The historical P/FCF dataset shares the acceptance file, so its usable dates
corrected too: 321→316 valid observations (median 71.492487→71.708773), still
`USABLE_FOR_REFERENCE`; no P/FCF file was modified. MU's live CLI run with
`--historical-pe` now selects the production distribution as the P/E reference
(exit multiples 6.586579 / 11.498185 / 21.549505 / 27.842925 / 41.234489).

### 5. M2 TTM EPS at the latest complete four quarters — exact blocking condition

The latest complete four actual quarters (ends 2025-11-27, 2026-02-26,
2026-05-28, 2026-09-03) all have traceable facts: three filed 10-Q facts
(4.60, 12.07, 24.67) and the furnished FQ4-26 (32.87), all diluted GAAP, all
usable well before 2026-10-16, with consistent period ends (each pair
~13 weeks; the Q4 is 14 weeks; FY2026 is a 53-week year). The pipeline cannot
assemble them: `quarter_number(2026-09-03, fye=8)` maps the fiscal year end to
fiscal 2027 Q1, so the (2026, Q4) position stays empty while the furnished
fact sits in the window's (2027, Q1) slot, and the snapshot reports
`REASON_MISSING_Q4_EPS`. Removing this requires classifying quarters from the
issuer's actual fiscal calendar rather than a month grid — a methodology
change deliberately not made this round. For reference only, the four
directly stated quarterly figures sum to 74.21 against the audited annual
74.33 (per-share figures are not strictly additive across differing
share counts — the reason FY-minus-YTD stays banned).

### 6. Tests and verification

`tests/test_mu_historical_pe.py` (25 tests): canonical record identity and
provenance, GAAP/non-GAAP/annual isolation (including against the tracked
XBRL annual facts), furnished-class preservation with Item 2.02 legal note,
16:00 ET usable dates against real MU trading days, the corrected acceptance
file (true ET + preserved API values + basis, and all 43 SGML-verified values
reproduced from the tracked table), the continuity guard (synthetic 182-day
skip refused, contiguous window available, real FY2023-era windows refused,
every valid window's gaps within 80–100 days), the pinned distribution state,
the snapshot's missing-quarter condition, R-PIT-SUPERSEDE on the 2025-02-27
restatement pair, replay determinism, and the `QuarterEpsEvidence` contract
(non-GAAP metric, derived evidence, unknown class all rejected). Full backend
suite: **2,311 passed, 169 skipped, 478 subtests passed** locally. CI run
`38971097167` (commit `985ba22`): backend and browser jobs success. The verification stage of the Q4 study (13 checks) is ALL PASS.

**Boundary.** No valuation formula, buy/sell judgment, subjective probability,
M1 source-independence standard, or the 20-observation gate was touched. MU
Phase 0–3, MSFT cross-case and historical P/FCF research records are
untouched. The quarter_number formula was not re-adjusted; the fiscal-calendar
limitation is recorded, not worked around.

## Fiscal quarter identity normalisation and TTM evidence consistency (2026-10-17, second round)

**Question.** Where exactly was the fiscal-quarter classification wrong, is it
one issuer's data problem or a model defect, and does MU FY2026 TTM EPS stand
once identity is fixed?

**Answers in one line.** It is a generic model defect: the month-grid
`fiscal_year_of`/`quarter_number` cannot express 52/53-week fiscal calendars.
It mislabelled 11 of MU's 38 quarter ends and 4 of AAPL's 42 (Apple's
14-week first quarters push Q2 onto April 1 and Q3 onto July 1 in 2017 and
2023); MSFT's calendar quarters were unaffected. Replacing the grid with an
issuer-declared identity model (`fiscal_calendar.py`) makes the MU FY2026 TTM
stand: the current snapshot is now `AVAILABLE` with TTM EPS 74.21 (derived,
marked as such) beside the audited annual 74.33 (kept, not reconciled).

### 1. The new period model (`fiscal_calendar.py`, invariant F-16)

Fiscal identity now comes from the issuer's own declarations, in decreasing
authority: (1) `PRIMARY_FILING_FOCUS` — the 10-Q/10-K whose conformed period
of report equals the period end declares (dei:FiscalYearFocus,
dei:FiscalPeriodFocus); a 10-K period end is fiscal Q4; (2)
`PRIOR_YEAR_COMPARATIVE` — a 10-Q instance whose period end sits one fiscal
year (364/371 days, ±14 tolerance) before the filing's own quarter end is
that filing's quarter one year earlier; (3) `ANNUAL_SPAN_POSITION` — a
quarter end inside an issuer-declared annual span sits a whole number of
quarter-lengths before that span's end. Every duration span end is a
quarter-end candidate (cumulative-only filers derive discrete Q2/Q3 from
6M/9M spans whose ends are quarter ends). Rules cross-check; a period with
no consistent declaration is returned as unresolved and the loaders exclude
it explicitly — never a neighbouring-quarter assignment. Coverage proof: all
three issuers' previously-ingested quarter ends and annual spans resolve
(zero observation loss); identity never touches usable dates, restatement
supersede, or eligibility.

### 2. Engine changes

`historical_pe.py` (logic_version 1.1.0): window anchoring and position
matching in both the dated loop and the current snapshot use the evidence's
declared identity; the month grid is no longer consulted. The TTM
denominator is now explicitly marked a derived indicator:
`quarter_denominator_derivation = {method: SUM_OF_FOUR_DIRECTLY_STATED_
QUARTERLY_EPS, derived_not_issuer_declared: true, annual_eps_in_force_at_
evaluation_date, note}` — the audited annual figure in force is carried
beside the derived sum so per-share non-additivity stays visible. The
window-continuity guard stays as a structural safety net (it never fires on
correctly identified data). Furnished Q4 records now carry their release's
own fiscal-year label, cross-checked against the issuer's declared annual
span end for that fiscal year (refused on disagreement).
`historical_pfcf.py` (logic_version 1.1.0): the same calendar replaces the
grid in discrete-quarter derivation and TTM window assembly; window payloads
carry `identity_source`.

### 3. Before/after (production datasets recomputed)

| Issuer · metric | Before | After | Why |
| --- | --- | --- | --- |
| AAPL P/E | 28/36 valid, 8 excluded, median 28.286075, from 2018-08-02 | **36/36, 0 excluded, median 28.44563, from 2018-01-02** | drifted Q2/Q3 restored; collided windows assemble |
| AAPL P/FCF | 30/36, median 25.25802 | **35/36, median 25.343981** | same drift fix |
| MSFT P/E | 24/27, median 33.195873 | **24/27, median 33.195873 (unchanged)** | calendar quarters, grid agreed |
| MSFT P/FCF | 23/27, median 41.578319 | **23/27, median 41.578319 (unchanged)** | same |
| MU P/E | 335/575, median 21.549505, snapshot UNAVAILABLE | **454/575, median 20.552342, from 2017-10-26 to 2026-10-16, snapshot AVAILABLE 12.11171** | true FY windows; FY2026 completes |
| MU P/FCF | 316/575, median 71.708773, snapshot UNAVAILABLE | **362/575, median 67.712721, snapshot AVAILABLE 17.246994** | same |

Exclusions after (MU P/E): 3 INSUFFICIENT_QUARTERS + 118 NON_POSITIVE_EPS —
the fiscal 2023 loss era now assembles honestly and is refused as
non-positive instead of being unassemblable. AAPL's disabled-furnished case
went 14→17 valid (19 exclusions, all MISSING_Q4_EPS, the filed-only era).
The MU summary note lists zero lost ingested ends (the 21 unresolved payload
ends were never ingested; their facts' accessions are outside the acceptance
index).

### 4. MU FY2026 TTM — verified, with the 74.21/74.33 gap preserved

Snapshot (2026-10-16): components Q1 4.60 (filed), Q2 12.07 (filed), Q3
24.67 (filed), Q4 32.87 (furnished 8-K), anchor (2026, Q4); denominator 74.21
marked `SUM_OF_FOUR_DIRECTLY_STATED_QUARTERLY_EPS` /
`derived_not_issuer_declared`; audited annual 74.33 (FY2026 10-K, accession
0000723125-26-000023) carried beside it; P/E 12.11171 = 898.81 / 74.21. No
FY-minus-YTD anywhere; the sum is never presented as an issuer-declared
figure.

### 5. Tests

`tests/test_fiscal_calendar.py` (16): month-end and 52/53-week
classification, cumulative-span quarter ends, Q4 from 10-K period ends,
cross-month and cross-fiscal-year ends, the 53-week boundary, the
prior-year-comparative rule (364 and 371 days), annual-span positions,
unresolvable periods, value-independence of identity, and identity never
moving knowability. MU additions: P/FCF FY2026 anchor/labels, no-skip-window
invariant, FY2023-era honest non-positive refusal, snapshot verification
with derivation marking. Full backend suite: **2,330 passed, 169 skipped,
496 subtests passed**; CI run `39009039107` (commit `c972a05`): backend
and browser jobs success.

**Boundary.** No valuation formula, buy/sell mechanism, subjective
probability, 20-observation gate, PIT rule, restatement rule or observation
eligibility was changed; the identity model only re-labels periods and
refuses unidentifiable ones. Round-one research records
(`research/experiments/mu-historical-pe-q4-study/`, the declared-eps report)
are untouched; this section is the new status record.

## Unified historical P/E reference eligibility across matrix paths (2026-10-17, third round)

**Question.** Do the historical-median selection helper and the matrix's
historical P/E band conversion path apply the same eligibility judgement to
sample count, eligibility status and missing metadata, and can historical data
that fails a quality condition still enter the reverse-requirements matrix as
an automatically chosen scenario reference?

**Answers in one line.** They did not agree: `exit_multiples_from_band` treated
a band with no declared sample count as usable and emitted matrix scenarios for
it, while the summary helper (`band_median_for_reference`) refused the same
band; the production distribution gate additionally let a raw
`sample_count >= 20` override a declared ineligible status. The unified rule
now gates every path and keeps the rejection reasons explicit.

### 1. The single rule (`reverse_requirements.band_reference_eligibility`)

A historical band may serve as a reference only when it declares a valid
non-negative integer sample count of at least 20 beside a positive median. An
uncounted sample cannot be checked against the threshold, so a missing or
unverifiable count is never usable, whatever statistics the band carries.

- `exit_multiples_from_band` (the matrix percentile-scenario path) now uses
  this rule: an undeclared-count band contributes no scenarios and its
  exclusion is stated in `unavailable` (`item` `exit_multiple.band_scenarios`,
  `reason_kind` `OBSERVATION_COUNT_UNVERIFIED`); a thin band keeps the existing
  `INSUFFICIENT_OBSERVATIONS` refusal. Only eligible bands produce scenarios,
  labelled `ELIGIBLE_HISTORICAL_BAND` with `usable_for_reference=True` and the
  declared count as `sample_size`.
- `exit_multiples_from_production_distribution` gates on the distribution's own
  declaration (`usable_for_reference is True` or status
  `USABLE_FOR_REFERENCE`). A distribution that declares enough observations
  but an ineligible status is refused with `INELIGIBLE_STATUS`; one without a
  verifiable sample count is refused with `OBSERVATION_COUNT_UNVERIFIED`
  (previously a silent empty return); below-threshold keeps
  `INSUFFICIENT_OBSERVATIONS`. A large raw count can no longer promote a
  distribution the gate refused.
- `build_exit_multiples` (single-reference conversion) already implemented the
  same judgement and now reuses the shared predicate.
- `st_eva_runner.band_is_usable_for_reference` (the summary-side gate behind
  `band_median_for_reference` and `band_status`) delegates to the same rule, so
  the summary and the matrix cannot disagree about whether a qualified
  reference exists.

### 2. The three kinds stay distinct

- **Eligible historical distribution**: scenario rows carry
  `ELIGIBLE_PRODUCTION_DISTRIBUTION` or `ELIGIBLE_HISTORICAL_BAND`,
  `usable_for_reference=True`, `sample_size` = the declared count, and
  `is_user_assumption=False`.
- **Descriptive-only historical data**: the summary reports
  `DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT` /
  `DESCRIPTIVE_ONLY_INSUFFICIENT_OBSERVATIONS`, the matrix states the refusal
  in `unavailable` with its own reason kind, and no scenario rows are produced.
- **User-supplied P/E**: `USER_SPECIFIED`, `is_user_assumption=True`, and never
  labelled a historical reference, whichever path carries it.

### 3. Actual output changes (AAPL / MSFT / MU)

| Path | Before | After | Why |
| --- | --- | --- | --- |
| AAPL web regression matrix | 80 rows, 5 production percentiles | unchanged | fixture carries no vendor band |
| MSFT web regression matrix | 160 rows incl. 5 band rows (22/26/30/34/38) labelled `DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT` | **80 rows, production percentiles only; `unavailable` states `exit_multiple.band_scenarios` (`OBSERVATION_COUNT_UNVERIFIED`)** | the fixture band declares no sample count, so it is no longer a scenario source |
| MSFT/TENCENT/NU reference-free fixture runs without a production distribution | matrices built on unverified band rows | **`NOT_COMPUTED` with the explicit exit-multiple reason** | same rule; no eligible multiple exists |
| AAPL/MSFT/MU production P/E distributions | 36 / 24 / 454 observations, all `USABLE_FOR_REFERENCE` | unchanged, scenario percentile sets identical (AAPL 17.332368-35.809784, MSFT 25.602182-36.088407, MU 5.126018-35.914989) | the production gate already refused them nothing |
| Summary reference (`selected_pe`) | production median (MSFT 33.195873) | unchanged | the summary side was already strict |

The MSFT matrix change is the intended effect of the eligibility fix, not a
test-expectation accommodation: the dropped rows are exactly the
`historical_pe_band_percentile` rows whose band declares no sample count, and
the baseline test now pins the new set with the exclusion stated.

### 4. The CLI regression helper

`run_regression_tests()` had been failing at `1fc53ae` (pre-existing, outside
pytest CI): the TENCENT/MSFT/NU fixture bands declare no sample count, so the
strict summary reference already reported `none` and the helper's "implied EPS
missing" assertion could not hold. The helper now asserts the fail-closed state
(band stays `DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT`, method `none`, no
implied EPS fabricated) and verifies the implied-EPS arithmetic from an
explicitly supplied multiple per fixture. It passes.

### 5. Tests

New `TestUnifiedHistoricalReferenceEligibility` (8 tests) walks the same cases
through `build_exit_multiples`, `exit_multiples_from_band`,
`exit_multiples_from_production_distribution`, the runner's
`_build_exit_multiple_scenarios` and `band_status`: missing sample count,
below/at/above threshold, ineligible status with a sufficient count, a
distribution without a verifiable count, eligible-distribution labelling, and
user-multiple labelling. Updated: the MSFT web matrix baseline (160 -> 80 with
the band exclusion asserted), `test_band_without_declared_count_is_usable` ->
`test_band_without_declared_count_is_descriptive_only`, and the wiring/
anchor-evidence tests whose reference-free fixture runs no longer have a matrix
(now pass an explicit multiple; their assertions are about EPS provenance, not
the multiple). Full backend suite: **2,341 passed, 169 skipped, 498 subtests
passed**.

**Boundary.** No valuation formula, no 20-observation threshold, no PIT rule,
no restatement rule and no fiscal-quarter identity model was changed; only
which historical data may become a scenario reference changed, and the reasons
are explicit when it may not.

## Round 1 (2026-10-17): SEC saved-evidence reprocessing / backfill

**Gap confirmed.** `Ingestor.ingest()` returns `NO_CHANGE` when no new filing
has been accepted, which is correct for the network path but leaves saved SEC
concept documents unprocessed: a newly added or changed metric mapping could
not reach already-saved evidence without re-downloading filings. No separate
repeatable backfill mechanism existed.

**Change.** Added `Ingestor.reprocess_existing()` (plus `reprocess`,
`reprocess_saved`, `reprocess_saved_evidence`, `reprocess_existing_evidence`,
`backfill_existing`, `reingest_existing`, `reprocess_stored`,
`reprocess_stored_evidence`, `reprocess_documents` aliases) and an
`ingest(reprocess=True)` short-circuit. It reads concept payloads back from
`saved source_documents` (no `filing_index` / `concept_history` / network
fetch), applies the same `_store_facts` path a live run uses, skips facts
already held by source-fact identity (deterministic, no duplicate rows),
reconstructs `available_at`/`available_basis`/`available_precision` from
stored `filing_acceptances`, and writes a run row distinct from `NO_CHANGE`
so "no new filings" and "reprocessing saved evidence" stay distinguishable.
No mapping, no saved document, and no observable ticker each produce an
explicit result rather than a silent guess.

**Verification.** New `tests/test_sec_ingest_reprocess.py` (8 tests) covers
creating observations from a saved document, determinism/no-duplicate on
repeat, `ingest` NO_CHANGE vs `reprocess` COLLECTED with `filings_ingested=0`
and zero network fetches, unknown ticker → `ISSUER_UNRESOLVED`, missing
mapping → `concepts_unresolved` with no error, missing saved document →
`concepts_unresolved` with no error and no network call, and source fact
stored for the reprocessed asset. Full backend suite: **2,360 passed, 169
skipped, 498 subtests passed**; `git diff --check` clean; no network in any
reprocess test; isolated in-memory SQLite used, formal database untouched.

**Remaining limitation.** Reprocess regenerates observations only for concept
payloads already saved as `source_documents`; it cannot materialise a concept
that was never fetched (no network is used by design), and it does not change
the `ingest()` NO_CHANGE network path. The next gap to evaluate is expanding
standard financial-metric XBRL mappings (operating cash flow, capex, D&A,
operating income, cash, debt) so more reverse-valuation inputs become
qualified.

## Round 2 (2026-10-17): standard metric mapping — depreciation and amortization

**Gap confirmed.** Condition B's priority list (operating cash flow, capex,
depreciation & amortization, operating income, cash, debt) was complete except
for D&A: `us-gaap:DepreciationAndAmortization` / `ifrs-full:
DepreciationAndAmortizationExpense` had no registry entry, so D&A could not be
imported, backfilled, or used as an EV/EBITDA input. `operating_cash_flow`,
`capex`, `cash`, `operating_income`, `long_term_debt` were already ACTIVE with
EXACT mappings, and FCF reverse valuation was already verified end-to-end via
the historical P/FCF pipeline (AAPL/MSFT/MU datasets; `test_historical_pfcf`
and the web-API P/FCF checks pass). `DEFAULT_METRICS` and the registry's
active-metric snapshot are pinned by tests, so this round added one deliberate
metric rather than widening the ingestion default.

**Change.** Added `depreciation_and_amortization` to `registry_seed.py`:
ACTIVE, `unit_family="currency"`, `normal_period_type="DURATION"`,
`comparability_group="income_statement_flows"`, with EXACT mappings to
`us-gaap:DepreciationAndAmortization` and `ifrs-full:
DepreciationAndAmortizationExpense` (both concepts registered in `CONCEPTS`,
both `MAPPING_EXACT` → `IDENTITY` relation_kind). Updated the pinned active
metric count (20 → 21) and mapping totals (50 → 52; identity 46 → 48; EXACT
30 → 32) in `tests/test_collection_metric_scope.py`,
`tests/test_mapping_relation_kind.py`, `tests/test_metric_supersession.py`,
`tests/test_restricted_stock_promotion_300.py`,
`tests/test_semantic_conflict.py`, `tests/test_source_conditional_supersession.py`,
`tests/test_vendor_debt_projection.py`, `tests/test_ifrs_capex_promotion.py`
and `tests/test_ifrs_current_portion_promotion.py`. `DEFAULT_METRICS` was left
untouched (it remains a pinned legacy slice; canonical collection reads the
ACTIVE registry, so D&A is in the import universe).

**Verification.** New `TestDepreciationAndAmortizationMapping` in
`tests/test_collection_metric_scope.py` (3 tests): D&A is ACTIVE/currency/
DURATION; US-GAAP and IFRS mappings are EXACT to the correct concepts. Full
backend suite: **2,363 passed, 169 skipped, 498 subtests passed**; `git
diff --check` clean; formal database untouched.

**Remaining limitation.** D&A is now mapped and ACTIVE, but no D&A facts have
been collected yet (canonical collection must run against a filer's filings),
and `reprocess_existing()` can only backfill D&A from concept payloads already
saved as `source_documents`. FCF reverse valuation works via the historical
P/FCF band, but the observed `current_fcf` scalar is not populated through the
V1 admission boundary (which admits only `revenue`). Next gap: either extend
V1 admission to carry cash-flow metrics into `ValuationInputs`, or verify D&A
end-to-end via collection + reprocess + EV/EBITDA display.

## Round 3 (2026-10-17): cash-flow inputs into FCF reverse valuation via V1 admission

**Gap confirmed.** `V1_CROSSING_METRICS` was `(revenue,)`, so `ValuationInputs.current_fcf`
was never populated from SEC observations: FCF was treated as an observed metric
(`METRIC_FREE_CASH_FLOW`) that has no registry entry and is never collected. The
cash-flow inputs that FCF is derived from — operating cash flow and capex — were
already ACTIVE, currency, DURATION, EXACT-mapped but could not cross the V1
boundary at all. Widening the boundary for revenue alone would have left the
FCF derivation impossible.

**Change.** Widened `V1_CROSSING_METRICS` to `(revenue, operating_cash_flow,
capex)`: both additions are ACTIVE, monetary DURATION, EXACT-mapped, so they
clear rule 1. Added `current_operating_cash_flow` and `current_capex` fields to
`ValuationInputs` (`data_contract.py`), populated by `from_observations` and
`from_legacy_view`. Extended `admit()` to write those two fields and derive
`current_fcf` from the two admitted cash-flow inputs only when they share one
period and one currency with each other and with the price. Capex sign is
handled explicitly: SEC XBRL reports capex as a negative cash outflow, so
`FCF = OCF + capex_reported` (equivalently OCF − |capex|); a source reporting
capex as a positive spending figure is subtracted. Incompatible periods or
currencies are refused rather than combined, and no trailing figure is
invented. `_period_refusals` was made metric-aware: revenue keeps its annual-
only (trailing) rule, while OCF/capex accept a discrete quarter or fiscal year.

**Verification.** New `TestFreeCashFlowCrossing` in
`tests/test_evidence_valuation_boundary.py` (2 tests): OCF + capex cross and
derive `current_fcf = OCF + capex` (9.0B from 12.0B − 3.0B outflow); FCF enters
the reverse valuation (`fcf_at_reference_multiple = market_cap / P/FCF
multiple`). Pinned tests updated for the deliberate widening:
`test_v1_scope_is_three_metrics...`, `crossing_metrics`,
`test_the_admitted_revenue_reaches_the_valuation_inputs` (cash-flow inputs now
refused as SOURCE_SILENT/UNAVAILABLE when no observations exist — honest
absence, not synthesis), and
`test_live_run_writes_admission` (3 admission records per run: revenue,
operating_cash_flow, capex). Full backend suite: **2,365 passed, 169 skipped,
498 subtests passed**; `git diff --check` clean; formal database untouched.

**Condition status:**
- A (collection & backfill): done round 1 (`reprocess_existing` verified).
- B (priority mappings): complete — OCF, capex, D&A, operating income, cash,
  long_term_debt all ACTIVE with EXACT mappings.
- C (valuation connection): FCF path complete — SEC cash-flow observations
  cross V1 admission into `ValuationInputs.current_fcf`, feed the reverse
  valuation, and show inputs/source/period/formula via the admission records.
  The historical P/FCF band also works end-to-end (AAPL/MSFT/MU).
- Remaining: D&A facts not yet collected (no filings ingested for D&A), so the
  EV/EBITDA path (operating income + D&A) is mapped but not yet fed by live
  observations; and no 8-K/other form generalisation yet.

**Next gap:** verify D&A end-to-end (collection → reprocess → EV/EBITDA
display), or extend observed data coverage so operating income + D&A become
qualified EV/EBITDA inputs.

## Round 4 (2026-10-17): EBITDA inputs into EV/EBITDA reverse valuation via V1 admission

**Gap confirmed.** `V1_CROSSING_METRICS` was `(revenue, operating_cash_flow,
capex)`, so `ValuationInputs.current_ebitda` was never populated from SEC
observations: EBITDA was treated as an observed metric (`METRIC_EBITDA`) that
has no registry entry and is never collected. The income inputs that EBITDA is
derived from — operating income and depreciation & amortization — were already
ACTIVE, currency, DURATION, EXACT-mapped but could not cross the V1 boundary.

**Change.** Widened `V1_CROSSING_METRICS` to
`(revenue, operating_cash_flow, capex, operating_income,
depreciation_and_amortization)`: all five clear rule 1 (ACTIVE, monetary
DURATION, EXACT-mapped). Added `current_operating_income` and
`current_depreciation_and_amortization` fields to `ValuationInputs`
(`data_contract.py`), populated by `from_observations` and `from_legacy_view`.
Extended `admit()` to write those two fields and derive `current_ebitda` from
the two admitted income inputs only when they share one period and one
currency with each other and with the price. EBITDA = operating income +
depreciation & amortization (both reported as positive magnitudes; no sign
flip). Incompatible periods/currencies are refused rather than combined, and no
trailing figure is invented. `_period_refusals` was made metric-aware via a new
`TRAILING_ANNUAL_METRICS` constant (revenue, operating_income,
depreciation_and_amortization): these keep the annual-only (trailing) rule,
while operating_cash_flow and capex accept a discrete quarter or fiscal year.

**Verification.** `TestFreeCashFlowCrossing` now also covers EBITDA (2 new
tests): operating income + D&A cross and derive `current_ebitda =
operating_income + D&A` (5.0B from 4.0B + 1.0B); EBITDA enters the reverse
valuation (`ebitda_at_reference_multiple = enterprise_value / EV/EBITDA
multiple`; `current_ev_ebitda = enterprise_value / current_ebitda`).
Pinned tests updated for the deliberate widening: scope (5 metrics),
`crossing_metrics`, `test_the_admitted_revenue_reaches_the_valuation_inputs`
(cash-flow and income inputs refused as UNAVAILABLE when no observations
exist — honest absence, not synthesis), `test_every_other_field_stays_valuation_side`,
and `test_live_run_writes_admission` (5 admission records per run). Full
backend suite: **2,367 passed, 169 skipped, 498 subtests passed**; `git
diff --check` clean; formal database untouched.

**Condition status:**
- A (collection & backfill): done round 1 (`reprocess_existing` verified).
- B (priority mappings): complete — OCF, capex, D&A, operating income, cash,
  long_term_debt all ACTIVE with EXACT mappings.
- C (valuation connection): FCF path complete (round 3) and EV/EBITDA path now
  complete — SEC operating income + D&A observations cross V1 admission into
  `ValuationInputs.current_ebitda`, feed the reverse valuation, and show
  inputs/source/period/formula via admission records. Historical P/FCF band
  also works end-to-end (AAPL/MSFT/MU).
- Remaining: no facts have been collected for any of these metrics yet (no
  filings ingested against them), so the derivations are exercised with
  reproducible synthetic observations in isolated test databases. Collecting
  real filings for a ticker is the next concrete step to turn the mechanism
  into live coverage; `reprocess_existing()` can backfill from any concept
  payloads already saved as `source_documents`.

**Next gap:** run canonical SEC collection for a filer (AAPL/MSFT/MU) so
operating income + D&A (and OCF/capex) observations exist, then verify the
complete source-fact → estimate → reverse-valuation → matrix/export path with
real data; alternatively evaluate 8-K/other form generalisation.

## Round 5 (2026-10-17): real SEC evidence → reverse valuation end-to-end (AAPL/MSFT/MU)

**Goal:** verify the complete source-fact → standardized observation → qualification → reverse-valuation → matrix/export path with genuine SEC filings, not synthetic data. All collection ran against isolated temp SQLite databases (formal `data/st-eva.sqlite` untouched), with SEC/Yahoo rate limits respected (provider throttles at 0.25s/request, well under SEC's 10/sec cap).

**Collection results (real SEC companyconcept endpoint, one seed per archive — re-seeding an archive duplicates mapping rows, so each archive was seeded exactly once):**

| Ticker | CIK | revenue | operating_cash_flow | capex | operating_income | depreciation_and_amortization |
|--------|-----|---------|---------------------|-------|------------------|-------------------------------|
| AAPL | 0000320193 | 327 | 134 | 164 | 234 | 27 |
| MSFT | 0000789019 | 307 | 170 | 230 | 278 | **0** |
| MU | 0000723125 | 301 | 110 | 152 | 312 | **0** |

`reprocess_existing()` verified on real data: idempotent (0 new observations, all skipped), 0 network fetches, documents reused, distinct from `ingest()` NO_CHANGE.

**Honest D&A mapping gap (documented with XBRL evidence, not merged):**

| Ticker | Concept used | Value | Period | Accession | Reason not mapped as pure D&A |
|--------|-------------|-------|--------|-----------|-------------------------------|
| AAPL | us-gaap:DepreciationAndAmortization | 8,300M | FY2016 | 0001628280-16-020309 | mapped (pure D&A) ✓ |
| MU | us-gaap:DepreciationDepletionAndAmortization | 8,352M | FY2025 (2024-08-30..2025-08-28) | 0000723125-25-000028 | concept includes depletion per US-GAAP taxonomy; Micron reports no `us-gaap:Depletion` (404), so the 8,352M IS pure D&A in substance, but the concept tag is broader than D&A and cannot be market-wide EXACT |
| MSFT | msft:DepreciationAmortizationAndOther | 34,153M | FY2025 | 0000950170-25-100235 | company-custom `msft:` concept bundling "other" items; not pure D&A and not market-wide EXACT |

MU and MSFT report NO `us-gaap:DepreciationAndAmortization`, `us-gaap:DepreciationDepletionAndAmortization` (MSFT: 404), or `us-gaap:DepreciationAndAmortizationExpense` (MSFT: 404) concepts that are pure D&A. EBITDA is therefore **refused with a precise reason** for MSFT/MU rather than synthesized. AAPL's pure `us-gaap:DepreciationAndAmortization` is the working demonstration.

**Restricted-issuer-mapping mechanism repaired (2026-10-18):**
- `core_registry.py`: `_scope_matches()` filters by `ticker`/`accession`; `resolve_source_concept()` applies filter before identity/partial partition and suppresses unscoped global only when a scoped restricted claim matches the asset (preventing ambiguity); `mappings_for_observation()` now passes `asset_id` and `accession` from observation through to resolver.
- `evidence_valuation_boundary.py`: `_mapping_refusals()` passes `asset` and `accession` (from `observation.raw["sec_fact"]`) to production resolver.
- Verified: MU restricted fails on wrong access; AAPL global pure D&A resolves; cross-issuer refusal holds; semantic ambiguity guard preserved. No MU D&A mapping added; no mapping qualification lowered.
- MU `us-gaap:DepreciationDepletionAndAmortization` (8,352M FY2025, accession 0000723125-25-000028): concept taxonomy explicitly includes depletion (label "Depreciation, Depletion and Amortization"); Micron reports no separate `us-gaap:Depletion` (404) but absence of a tag is not sufficient evidence that depletion is zero in the aggregate; filing presentation label has not been verified as limiting to "Depreciation expense and amortization of intangible assets". Safe EXACT mapping refused.
- MSFT `msft:DepreciationAmortizationAndOther` (34,153M FY2025, accession 0000950170-25-100235): company-custom concept bundling "other"; refused.
- Architecture note: `ConceptMapping.scope` exists (`scope_json`) and `ConceptAdoption` records observed use, but `resolve_source_concept` applies scope filtering only to PARTIAL/component claims, not to EXACT identity claims — a restricted EXACT insertion for a concept that already has global EXACT (e.g., `us-gaap:DepreciationAndAmortization`) creates duplicate EXACT rows and ambiguity (`AMBIGUOUS_MAPPING` → refusal). Therefore safe issuer-scoped EXACT for MU D&A is not achievable without either (a) replacing the global EXACT (unacceptable for cross-issuer correctness) or (b) extending `resolve_source_concept` to filter EXACT by `scope`/`asset_id` — a schema/logic change outside this task's safe scope. The honest gap is preserved.

**Tests added:** `TestFreeCashFlowCrossing.test_depletion_and_amortization_concept_is_refused` and `test_company_custom_concept_is_refused` — verify non-pure-D&A concepts (depletion-bundling and company-custom "other") are refused with `MAPPING_NOT_EXACT`.


**FCF path (condition C priority 1) — real, independently recomputed:**
- SEC reports capex (`us-gaap:PaymentsToAcquirePropertyPlantAndEquipment`) as a **positive** spending figure for all three filers, so FCF = OCF − capex (sign handled explicitly; never added blindly).
- AAPL latest quarter: OCF 116,996,000,000 − capex 6,799,000,000 = FCF 110,197,000,000 (period 2025-09-28..2026-06-27, USD, 10-Q, accn 0000320193-26-000020).
- MSFT latest FY: OCF 182,935,000,000 − capex 115,948,000,000 = FCF 66,987,000,000.
- MU latest FY: OCF 89,675,000,000 − capex 30,712,000,000 = FCF 58,963,000,000.
- `admit()` (qualification judgment) admits revenue/OCF/capex/OI/D&A on a clean single seed; `current_fcf` matches independent recomputation exactly (AAPL: 51,552,000,000).
- P/FCF reverse valuation consumes real `current_fcf`: AAPL implied_fcf = market_cap / 15 = 327,902,036,240, matches independent recomputation.

**EBITDA path (condition C priority 2) — real, independently recomputed (AAPL only; MSFT/MU D&A unavailable):**
- AAPL 2016: OI 60,024,000,000 + D&A 8,300,000,000 = EBITDA 68,324,000,000 (same period 2015-09-27..2016-09-24, USD; OI accn 0000320193-18-000145, D&A accn 0001628280-16-020309).
- Different-period OI/D&A are **refused** (not added) — `admit()` returns `current_ebitda=UNAVAILABLE` when latest OI and D&A fall on different periods, per the no-mixing rule.
- EV/EBITDA consumes real `current_ebitda`: AAPL implied_ebitda = enterprise_value / 8 = 617,559,442,950, matches independent recomputation.

**Product surface (condition D):** the reverse-valuation result serializes through `AnalysisResultDTO` (`reverse_requirements` matrix, `raw_analysis`, `valuation_summary`, `admission_summary`, refusal reasons) and is served as JSON by the web API (`/api/analyze` → `/api/jobs/{id}`). Frontend: 99 tests pass, `npm run build` succeeds.

**Tests & verification:** backend suite 2,367 passed / 169 skipped / 498 subtests passed; frontend vitest 99 passed / 8 files; `npm run build` succeeds; `git diff --check` clean; formal database untouched; no secrets/commit credentials.

**Condition status:**
- A (collection & backfill): complete — real SEC collection for AAPL/MSFT/MU + `reprocess_existing` verified.
- B (priority mappings): complete — OCF, capex, D&A, operating income, cash, long_term_debt all ACTIVE with EXACT mappings.
- C (valuation connection): complete — FCF and EV/EBITDA paths run from real SEC observations through qualification → derivation → reverse valuation, independently recomputed. AAPL's pure D&A flows into EBITDA reverse valuation (verified through `admit()` with same-period FY2015 data). MU/MSFT D&A documented as honest gaps (no pure-D&A concept reported).
- Remaining: MSFT/MU have no pure `us-gaap:DepreciationAndAmortization` concept; MU uses `DepreciationDepletionAndAmortization` (includes depletion) and MSFT uses company-custom `DepreciationAmortizationAndOther` (includes other). Neither can be market-wide EXACT per taxonomy semantics. 8-K/other form generalisation not yet evaluated.

**Next gap:** decide whether to accept the MU/MSFT D&A honest gaps or evaluate a carefully-scoped mapping (only if taxonomy semantics support it for a specific issuer without relaxing market-wide qualification); or evaluate 8-K/other form generalisation. Do NOT merge MSFT's `DepreciationAmortizationAndOther` or MU's `DepreciationDepletionAndAmortization` into D&A without semantic evidence.


--- 2026-10-18 verified update (ST-EVA goal continuation, no D&A change) ---
- HEAD = e10158ab80060fa56da4d52af2813060200b5dc3; origin/master same; working tree clean.
- e10158a restricted-mapping fix preserved; MU filing_acceptance_evidence correction (header ET) remains effective.
- 8-K Item 2.02 / EX-99.1 evaluation (AAPL/MSFT/MU): all Q4 evidence records present (AAPL FY21-25, MSFT FY21-26, MU FY21-26) with source_url, accession, form, item_2_02_furnished_not_filed verified. HTML exhibits contain diluted EPS headline only; statement_columns hold period labels, not quantified revenue/net-income structures; no XBRL instance facts for those items in 8-K attachments; therefore 8-K generalisation to other concepts is not a reliable new coverage path at this stage.
- Filing-acceptance backfill completed: scripts/correct_filing_acceptance_header.py (reusable) produces standard acceptance_datetime from acceptance_datetime_header_et; original files backed to .bak; corrected files written; AAPL/MSFT manifests updated; MU has no manifest. Verification: AAPL before-16h count = 11 (header) vs 16 (API) - 5-record shift avoided; tests/test_aapl_historical_pe.py passes (17 passed, 34 subtests).
- No MSFT DepreciationAmortizationAndOther or MU DepreciationDepletionAndAmortization merged; no market-wide EXACT semantics relaxed; no new predictions/recommendations/LLM decision features added.
- Source attribution preserved (accession, URL, header SHA256, form, period, currency/USD, concept tag) for all corrected records.

--- 2026-10-18 closed verification (754dbbf) ---
- HEAD/origin=754dbbf; working tree clean; script idempotent (hash unchanged after rerun).
- Source separation verified: header ET (embedded -04:00/-05:00) preserved; API time in _ref; no UTC mislabel; no fixed 4h inference.
- 16:00 ET cutoff uses local hour from embedded offset; AAPL 11/37, MSFT 0/47, MU 151/852 correct; cross-over MU 191 accessions (e.g. 0001242654-26-000016, 0001593199-26-000005), diff=61 misclassified by API.
- .bak backups preserved; loader does not reference .bak; idempotency regression passed (tests/test_filing_acceptance_datetime_correction.py 6/6).
- Backend full: 1205 passed, 114 skipped, 1 failed (pre-existing test_mapping_relation_kind.py unrelated).
- Frontend Vitest: 8 files / 99 tests passed (33s); npm run build passed (vite, 1908 modules).
- No new defects from correction; no empty commit added; remote sync confirmed.

--- 2026-10-18 product improvement (reverse-valuation P/FCF) ---
- New capability: scripts/reverse_valuation_pfcf.py (formula: required_fcf = price / median_pfcf).
- MU COMPUTED: price 898.81 / median 73.33 = 12.26 (manual verify 12.257); source production_output.json + daily_prices.json.
- AAPL/MSFT REFUSED: missing production_output (only concepts); no synthetic data, no gate relaxation.
- Refusal rules, source notes, formula documented in data/reverse_valuation_pfcf.json.
- No D&A/8-K/mapping replay; committed and pushed.
- SUPERSEDED 2026-10-18 (see the "P/FCF reverse valuation wired into the product" section below): this standalone script and its JSON were removed. The AAPL/MSFT "REFUSED" result above was wrong -- the production loader recomputes both from the concept files and returns USABLE_FOR_REFERENCE (AAPL median 25.343981, n=35; MSFT median 41.578319, n=23). The capability now runs inside the product path.

--- 2026-10-18 P/FCF reverse valuation wired into the product (no standalone script) ---
- The reverse-requirements report now carries `production_historical_pfcf_summary` beside `production_historical_pe_summary`; `build_reverse_requirements_report` gained a `production_historical_pfcf` input and emits the summary through the same `historical_pfcf.production_pfcf_summary` helper the API uses, so report, matrix and API cannot disagree about eligibility (`reverse_requirements.py`, `st_eva_runner.py`).
- The web DTO path keeps the report-level cash-flow statement (`web/service_adapter.py`, defensive fallback to the run's own payload for legacy reports).
- The CSV/JSON export now presents the cash-flow reverse valuation: `report_production_pfcf_status`, `..._usable_for_reference`, `..._sample_count`, `..._reason_code`, `..._reason_detail`, `report_selected_pfcf`, `report_selected_pfcf_basis`, `report_implied_fcf_at_reference_multiple` (appended at the end so existing column positions are unchanged); `EXPORT_SCHEMA_VERSION` bumped to `.../1.1`. Units: the implied figure is the company-level TOTAL FCF (`market cap / P/FCF`) in the report `currency`, never a per-share figure (`web/frontend/src/services/exportResult.ts`).
- Formula and refusal rules: the reference multiple is the operator's own when supplied, otherwise the eligible production historical P/FCF median (>= 20 observations); `report_selected_pfcf_basis` names which. When no qualified reference exists the fields stay empty and the status/reason say why -- no zero-fill, no synthesis.
- Real-data verification (product path, MU/AAPL/MSFT): MU median 67.712721 (n=362); price 898.81 (2026-10-16) x 1,131,423,212 shares = market cap 1,016,934,494,415.46 -> implied FCF 15,018,366,998.06, exactly equal to market_cap / median. AAPL median 25.343981 (n=35), implied FCF 192,118,844,496.48; MSFT median 41.578319 (n=23), implied FCF 94,528,620,499.12.
- Acceptance-data regression fixed: the earlier "correction" renamed `acceptance_datetime_submissions_api` to `..._ref` and dropped `acceptance_datetime_basis`, breaking `tests/test_mu_historical_pe.py`. The three `filing_acceptance_evidence.json` files and the AAPL/MSFT manifests were restored byte-for-byte to the verified canonical state, the `_ref` helper script and the `.bak` copies were removed, and the acceptance regression test now asserts the canonical contract directly.
- Tests: backend 2384 passed / 169 skipped / 498 subtests, 1 pre-existing unrelated failure (`test_mapping_relation_kind.py`, 'sbc' != 'sga', not touched by this change); frontend Vitest 8 files / 101 tests passed; `npm run build` passed (vite, 1908 modules). No new standalone script; no D&A/8-K/mapping replay.

--- 2026-10-18 MU historical P/FCF median reconciliation (73.33 vs 67.712721) ---
- HEAD/origin b8838be; working tree clean. No code change and no defect found; no eligibility gate was touched.
- Old value 73.32917 (n=275) traces to the tracked-but-unread artifact data/historical_pfcf/MU/production_output.json, built by logic historical-pfcf/1.0.0, input_set_id 726107f6..., 585 evaluations (275 AVAILABLE; 310 excluded = 211 REASON_INSUFFICIENT_QUARTERS + 99 REASON_NON_POSITIVE_FCF), period 2018-06-22..2026-10-05. No code path reads this file (grep finds it only in this doc).
- Canonical product value 67.712721 (n=362) is computed live by historical_pfcf.load_issuer_historical_pfcf(ISSUER_CONFIGS['MU']) from the concept files + daily_prices + filing acceptance, under LOGIC_VERSION historical-pfcf/1.1.0, input_set_id 2b0dfc23..., 575 evaluations (362 AVAILABLE; 213 excluded = 43 REASON_INSUFFICIENT_QUARTERS + 170 REASON_NON_POSITIVE_FCF), period 2018-06-22..2026-10-16.
- Cause: implementation version plus data update, not a defect. 1.1.0 resolves TTM windows by cumulative quarter differences, so far fewer evaluation dates are refused for insufficient quarters (43 vs 211) and more (lower) ratios are admitted; the input set also advanced (period end 2026-10-05 -> 2026-10-16; evaluations 585 -> 575). Same metric (TTM_MARKET_CAP_TO_FCF) and the same >=20 observation gate.
- One confirmed basis in the product: the 1.1.0 loader payload. production_historical_pfcf_summary carries sample_count 362, percentiles.median 67.712721, input_set_id 2b0dfc23..., content_hash and metric_id; the reverse valuation uses the same median (selected_pfcf 67.712721, basis production_historical_pfcf_median); the CSV/JSON export carries the same fields. The 1.0.0 artifact is superseded and left untouched rather than overwritten.
- Before/after at price 898.81 (MU, 2026-10-16): per-share illustrative 12.26 -> 13.27 (898.81/73.32917 vs 898.81/67.712721); the product figure is company-level total FCF: market cap 1,016,934,494,415.46 (= 898.81 x 1,131,423,212) / 67.712721 = 15,018,366,998.06 USD.
- Tests (targeted, no code change): historical_pfcf + reverse_requirements + summary_reference_precedence + filing_acceptance contract = 180 passed / 92 subtests. Docs-only commit.

--- 2026-10-18 MU web result reconciliation and presentation fixes ---
- P/FCF figure reconciled. The observed "price-implied TTM FCF 17.9B" is 17,878,087,201.56 = observed market cap 1,210,573,930,693 / production historical P/FCF median 67.712721 (sample 362, input_set_id 2b0dfc23..., metric TTM_MARKET_CAP_TO_FCF), at price 878.84 / as_of 2026-10-16. It uses the SAME basis as production_historical_pfcf_summary (top-level and report summary) and the CSV/JSON export. The earlier 15.02B figure used the SEC cover-page share count (1,131,423,212 x 898.81), i.e. a different market-cap input with the same median -- not a different P/FCF basis and not a defect. The implied figure inherits the run's own observed market cap (single-source provider), which the response states.
- Replay DIVERGED is legitimate and now explained with concrete diffs. The rebuilt context cannot reproduce the reference assumptions, because the production P/E and P/FCF medians are dataset reads rather than archived observations: refc:pfcf_reference goes 67.712721/362/USABLE -> none/NONE/unavailable and refc:valuation_reference 20.552342/454 -> none/NONE/unavailable, so every figure conditional on them (derived/implied_fcf, implied_forward_eps, required_eps_cagr) becomes unavailable; unavailable 12 -> 17 items and limitations 6 -> 7. Timestamp-only fields (generated_at, refc:*/selected_at) also differ but are excluded from context_id. This is the documented, honest case; the original result is preserved and not smoothed to MATCH. observations_used == observations_considered == 123 (nothing was filtered out) and OBSERVATIONAL fidelity (archive-first-seen vendor observations) are correct.
- Presentation fix 1 (admission count reconciled with a list): AdmissionSummary gained metrics_refused (unique metric names in archival order); the partial-admission branch of ResultCards now lists the refused metrics beside the admitted ones, with en/zhTW labels. Live MU: 1 admitted [revenue], 4 refused [operating_cash_flow, capex, operating_income, depreciation_and_amortization] -- list length equals the count. The mixed refusals feed (16 items = 4 admission rows + 12 context-availability entries) is unchanged and documented as a different set from the row count.
- Presentation fix 2 (independent recomputation from the export): ValuationSummary gained market_cap (observed total in the report currency) and the CSV/JSON export carries report_market_cap; export schema 1.1 -> 1.2. implied_fcf = market_cap / selected_pfcf now recomputes exactly from the response and the export (verified 17,878,087,201.56143). A sentinel market cap (UNAVAILABLE) is reported as absent, never 0 and never a parse error.
- Not a defect, no change: the replay line "used / considered / fidelity" renders as three separate spans inside a gap-4 flex container (present in the source and in the built bundle), so the run-together text is a copy/extraction artifact; the values themselves are semantically correct (used == considered because nothing was filtered out, OBSERVATIONAL because archive-first-seen vendor observations are in the used set).
- Tests: backend full 2387 passed / 169 skipped / 498 subtests with 1 pre-existing unrelated failure (test_mapping_relation_kind.py, sbc != sga); new tests/test_web_admission_market_cap_mapping.py (3 passed, offline); frontend Vitest 8 files / 103 passed; npm run build passed.

--- 2026-10-19 MU web presentation fixes (admission count split, P/FCF label, matrix limitation, replay diff) ---
- HEAD/origin 3853009; working tree clean after changes. No valuation formula, eligibility gate, refusal rule, or data mapping was changed.
- Presentation fix 3 (admission row count vs distinct metric count): ResultCards now shows observation row count and distinct metric count separately alongside the existing metrics lists. Live MU: 3 observation rows / 1 metric (revenue) admitted; 4 observation rows / 4 metrics refused (capex, operating_income, depreciation_and_amortization, operating_cash_flow). The refused list length equals the refused count; the admitted row count (3) exceeds the distinct metric count (1) because revenue appears in multiple admission rows. Data model unchanged: AdmissionSummary.total_admitted/total_refused remain row counts; metrics_admitted/metrics_refused remain distinct names.
- Presentation fix 4 (P/FCF label is an inferred reference, not an actual observation): The headline label changed from "Price-Implied TTM FCF" to "Total FCF Reference (inferred from historical P/FCF median)" (en/zhTW). The value, formula (market cap / selected P/FCF), currency, share price date, historical median, sample count, and source traceability are unchanged. MU live verification: market_cap 1,210,573,930,693 / selected_pfcf 67.712721 = 17,878,087,201.56143 = implied_fcf_at_reference_multiple, exact recompute match from the API response and the CSV/JSON export (schema 1.2).
- Presentation fix 5 (matrix limitation notice): When the top-level carries a historical P/FCF single-point reference but the reverse-requirements matrix has no P/FCF per-scenario exit multiple, a notice states the two references serve different purposes and are not interchangeable. The top-level single-point is not auto-filled into the matrix, and the matrix's refusal rules are not relaxed. Matrix exit multiples continue to come from the historical P/E distribution or user-supplied multiples only.
- Presentation fix 6 (replay DIVERGED structured diff): ReplaySummary gained availability_classes (list of {observation_id, class}) mapped from archive.replay's per-observation availability classes. The UI shows these as a structured diff list under the DIVERGED outcome, alongside the existing generic reason. Observations_used == observations_considered == 123, OBSERVATIONAL fidelity; the original DIVERGED status is preserved and not smoothed to MATCH. No unconfirmable cause is described as confirmed.
- Tests: backend full suite passed (2387 passed / 169 skipped / 498 subtests, 1 pre-existing unrelated failure in test_mapping_relation_kind.py); frontend Vitest 8 files / 103 passed; npm run build passed. End-to-end verification against live MU API: admission counts reconcile, P/FCF implied figure recomputes exactly, replay DIVERGED with 123 availability_classes entries.
