# ST-EVA — Current Project Status

**Status checked:** 2026-10-12
**Repository:** `sbvcid/st-eva`, branch `master`
**Current implementation baseline:** `363afd9` (R7-1: source-declared consensus period end preserved and comparability decided on it; R5: summary-card semantics reconciled + JSON/CSV audit export; R6: replay at the archival watermark; R6.1: replay reconciled to a run's own context snapshot; first-use mode = live with expanded assumptions)
**Latest verified GitHub Actions:** [Run 38246189499](https://github.com/sbvcid/st-eva/actions/runs/38246189499), triggered by `363afd9`; `backend` and `browser` jobs both passed.

This is the live, changeable implementation/status record. The root [README](../README.md) contains the enduring product definition and rules. This file records what is implemented, wired, not wired, failing, or not yet verified. Historical files under `docs/archive/` are not current status or instructions.

## Continuation checkpoint — read this before planning or running work

This section is the hand-off checkpoint for future conversations and coding agents. Use the current status below; do not restart prior audits just because a new conversation begins.

**Completed and should not be repeated without a concrete reason**

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

**Outstanding but intentionally not complete**

- The production point-in-time historical P/E reference is available on the web path only for the two configured issuers, ``AAPL`` and ``MSFT``. Any other ticker is reported as ``UNAVAILABLE`` with an explicit reason rather than being given a fabricated distribution.
- The distribution is evaluated on periodic SEC filing and earnings-release usable dates, so it is not a continuous daily history, and it does not extend past the frozen dataset's last evaluation date. Both are stated in the report.
- No second historical P/E engine and no broad caching or ingestion framework was added, and no new network acquisition was introduced to reach any source.
- The archive has **not** been deleted or cleaned. The integration decision lists about 1.3–1.5 GB as `NO_LONGER_NEEDED` and about 0.8–1.0 GB as `REVIEW_REQUIRED`; these are planning classifications, not proof that files were deleted. Cleanup is a separate bounded task and must not block product development.

**Next task status**

The AAPL first-version product acceptance is complete (accepted 2026-10-12; see the acceptance section below), and **there is currently no scheduled product implementation task.** Do not start speculative framework, ingestion, caching, LLM or engine work, and do not initiate another replay/archive engineering round without a demonstrated product defect — the R1–R6.1 items are complete and the standing CI is the guard.

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

- **Dividends / total return:** `dividend_history.py` provides sourced dividend observations and deterministic metrics; the reverse engine includes explicit cash-retained and dividend-reinvested conventions and relief calculations where inputs exist. The conventions must remain distinct and must not double-count dividends. The web UI does not expose the full scenario results.
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
- **Reference P/E**: states its basis from a new ``selected_pe_basis`` — your supplied multiple (``user_supplied_multiple``) or the vendor historical P/E-band median (``historical_pe_median``, requires ≥ 20 declared observations) — never the production point-in-time distribution the matrix's eligible exit multiples use.

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

**Confirmed at the API level (``/api/analyze`` → poll ``/api/jobs/{id}``, 56/56 checks).** Tick/currency identity; matrix ``COMPUTED`` with ``matrix_size == row count``; uncomputed rows carry explicit nulls + flags (no fabricated zeroes, no substitution); exit-multiple references stay distinct (``production_historical_pe_percentile``/``ELIGIBLE_PRODUCTION_DISTRIBUTION`` vs ``user_supplied``/``USER_SPECIFIED``); the production distribution is usable (36 observations ≥ 20); summary basis is honest (ref-free run reports ``selected_pe_basis`` from the summary engine — ``none`` when no user multiple and no eligible vendor-band median, which coexists correctly with the production-distribution matrix exit multiples — while user-multiple runs report ``user_supplied_multiple``); R2.1 holds (a direct SEC fact is fully identified and only where the source relationship is established; related filings stay cross-check and are never the direct source of the same value); replay is ``MATCH`` for the reference-free context and ``DIVERGED`` for the user-multiple context; and case 3 reflects its own request (``selected_pe`` = 26, not stale).

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

**Boundary.** ``reverse-requirements/1.1`` keeps its identifier and every
published equation; the scenario cross-product, the price-only baseline matrix,
the production historical P/E pipeline and its thresholds, archive/replay
semantics, SEC binding and the export envelope are unchanged. The out-of-scope
items (P0 exit-multiple table label for
``production_historical_pe_percentile``, full ``unavailable`` rendering for
computed matrices, dividend/total-return UI, start-EPS period-label UI, and
summary ``Reference P/E`` reconciliation with the production distribution)
remain outstanding.
