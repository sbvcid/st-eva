# ST-EVA — Current Project Status

**Status checked:** 2026-10-11
**Repository:** `sbvcid/st-eva`, branch `master`
**Current implementation baseline:** `1271f94` (R1 reverse requirements matrix API and browser UI complete)
**Latest verified GitHub Actions:** [Run 38148637724](https://github.com/sbvcid/st-eva/actions/runs/38148637724), triggered by `1271f94`; backend and browser jobs passed.

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
  - Verified with 20 web API tests, 44 wiring tests, 6 archive isolation tests, 24 Vitest frontend unit tests, 7 browser smoke tests, and the full backend suite (1,897 passed, 168 skipped, 140 subtests).
- **R2 Reverse scenario provenance and reproducibility is complete** (formula version `reverse-requirements/1.1`):
  - Row-level evidence contract defined and strongly typed in `web/schemas.py` and `web/frontend/src/types/api.ts` with `SecFactDTO`, `MarketPriceEvidenceDTO`, `EpsAnchorEvidenceDTO`, `ExitMultipleEvidenceDTO`, `CalculationStepDTO`, and `ScenarioEvidenceDTO` attached to each `EpsScenarioDTO`.
  - Pure calculation engine in `reverse_requirements.py` generates deterministic 4-step execution traces (`build_scenario_calculation_steps()`): (1) Required Exit Price $P_T = P_0 \cdot (1 + r)^T$, (2) Required Terminal EPS $EPS_T = P_T / PE_{\text{exit}}$, (3) Total EPS Growth $\Delta EPS = (EPS_T - EPS_0) / EPS_0$, (4) Required EPS CAGR $g = (EPS_T / EPS_0)^{1 / t_{\text{growth}}} - 1$ or explicit uncomputable reason, verifying reproducibility within $10^{-4}$ tolerance.
  - Strict segregation between sourced facts and user assumptions:
    - User assumptions (`--user-eps`, user-specified exit multiples) are tagged `is_user_assumption=True`, `source_type="USER_SUPPLIED"` / `eligibility_state="USER_SPECIFIED"`, with no fabricated SEC provenance.
    - Sourced facts include market price evidence (`ev-price-001`), starting EPS anchor evidence (`ev-current-eps-001` or `ev-forward-eps-001`) with verified SEC diluted EPS XBRL fact metadata (accession, form 10-K/10-Q, filed date, concept `us-gaap:EarningsPerShareDiluted`, unit `USD/shares`), and exit multiple historical sample count / eligibility state.
    - Historical multiple sample count limitations (<20 qualifying observations) are explicitly marked `DESCRIPTIVE_ONLY_UNVERIFIED_SAMPLE_COUNT` and `usable_for_reference=False`.
  - Service adapter hardened in `web/service_adapter.py`: DTO validation failures raise explicit exceptions rather than silently swallowing the error and omitting the matrix while reporting success.
  - Frontend UI in `<ReverseRequirementsMatrix>` provides an expandable audit trail drawer with:
    - "Mathematically Verified" reproducibility badge
    - 4-step deterministic calculation trace cards with formulas, operands, and results
    - Source evidence cards with observation IDs, provider, and SEC filing metadata
    - Distinct tags distinguishing User Assumptions from Verified Sourced Facts and Limitations.
  - Local verification results: full backend suite passed (1,938 passed, 168 skipped in 398.59s); wiring suite 49 passed; web API 22 passed; Playwright browser smoke 8 passed; Vitest frontend unit tests 25 passed; production frontend build passed (`dist/index.html` produced). Persistent SQLite files and AAPL reverse requirements artifact verified intact.

**Outstanding but intentionally not complete**

- Full interactive point-in-time daily historical P/E distribution recomputation graph inside the browser drawer (currently provides verified sample count, observation range, and eligibility status).
- The archive has **not** been deleted or cleaned. The integration decision lists about 1.3–1.5 GB as `NO_LONGER_NEEDED` and about 0.8–1.0 GB as `REVIEW_REQUIRED`; these are planning classifications, not proof that files were deleted. Cleanup is a separate bounded task and must not block product development.

**Next task — one task only**

Reconcile summary cards with reverse-requirements matrix metrics, unify displayed terminology, and extend export capabilities (e.g. JSON/CSV export of audit trail and scenario matrix).

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

The web API accepts `reference_multiple` and `horizon_years` in `AnalyzeRequest`, and the backend adapter forwards these fields to `run_st_eva()`. However, the actual browser in `App.tsx` currently sends only `ticker` and `mode`; it does not provide these assumptions and has no complete controls for the matrix axes. The API/adapter's existence must not be mistaken for a wired end-to-end user feature.

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
   - Sourced facts (market price observation ID, starting EPS anchor with verified SEC XBRL accession/filing date/concept metadata, exit multiple sample count and eligibility status).
   - Clear distinction between user assumptions, verified sourced facts, and data limitations/refusals.
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

- The production historical P/E path is opt-in in the CLI (`--historical-pe`); the web adapter does not pass this option to the runner. The default browser path therefore must not be assumed to be using the dedicated daily point-in-time reconstruction.
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
