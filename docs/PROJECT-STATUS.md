# ST-EVA — Current Project Status

**Status checked:** 2026-10-11  
**Repository:** `sbvcid/st-eva`, branch `master`  
**Current implementation baseline:** `cb5ab8c`  
**Latest verified GitHub Actions:** [run 38140076063](https://github.com/sbvcid/st-eva/actions/runs/38140076063), triggered by `cb5ab8c`; backend and browser jobs passed.

This is the live, changeable implementation/status record. The root [README](../README.md) contains the enduring product definition and rules. This file records what is implemented, wired, not wired, failing, or not yet verified. Historical files under `docs/archive/` are not current status or instructions.

## Continuation checkpoint — read this before planning or running work

This section is the hand-off checkpoint for future conversations and coding agents. Use the current status below; do not restart prior audits just because a new conversation begins.

**Completed and should not be repeated without a concrete reason**

- **P0 CI contract repair is complete** at commit `cb5ab8c`. The three failures previously seen in runs `38137995221` / `38138343712` were fixed. Local results: 1,897 passed, 168 skipped, 140 subtests passed; archive-isolation 6 passed; web API 15 passed; frontend build passed. GitHub Actions run `38140076063` passed both backend and browser jobs.
- Persistent local SQLite files were SHA-256 checked before and after the test runs; the reported hashes were unchanged. Do not rerun this audit unless a subsequent task touches database persistence or tests.
- The archive was inventoried and semantically reviewed through `C:\st-eva-audit\inventory\phase2\integration-decision.md`. The decision was **zero archive content integrated**. Do not repeat the broad inventory or phase-2 review unless a specific product gap points to a particular archive item.
- The existing reverse-requirements engine is not a blank slate: `reverse_requirements.py` has formula version `1.1`; the reported AAPL artifact `data/historical_pe/AAPL/reverse_requirements_output.json` contains 27 scenarios. This proves an output artifact exists, not that the browser path is complete. Do not regenerate the artifact or repeat a broad formula audit just to re-establish that the matrix exists.
- The reported local Git state after P0 had only `data/historical_pe/AAPL/reverse_requirements_output.json` untracked. Re-check current local Git status before changing or committing that file; do not add it automatically.

**Outstanding but intentionally not complete**

- The full scenario matrix is not yet wired as a first-class typed web response and displayed in the browser.
- Browser inputs do not yet represent all assumptions/axes required by the matrix, and the fixed regression-mode path must not be mistaken for live data.
- The browser does not yet offer complete row-level provenance and recomputation details.
- The archive has **not** been deleted or cleaned. The integration decision lists about 1.3–1.5 GB as `NO_LONGER_NEEDED` and about 0.8–1.0 GB as `REVIEW_REQUIRED`; these are planning classifications, not proof that files were deleted. Cleanup is a separate bounded task and must not block product development.

**Next task — one task only**

Implement the first-class reverse-requirements matrix contract through the existing web API and browser, using the existing calculation engine. Start by tracing the current DTO/request path and produce the smallest implementation diff. Do not redo P0, repeat the archive audit, create a new valuation engine, or revalidate every formula without a specific failure or code change that warrants it.

**Execution rule**

Before running tests, compare the working tree and task diff with this checkpoint. Run targeted tests first; run the full suite when the code change warrants it and record the actual result. Mark an item complete only when its acceptance evidence exists. Update this file rather than creating another status/roadmap document.

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

Confirmed gaps:

1. **No full reverse-requirements matrix in the UI.** The browser doesn't render the `reverse_requirements_matrix` from the core report.
2. **No complete scenario controls.** The browser submission sends ticker and mode only. It doesn't pass `reference_multiple` / `horizon_years`, and the schema itself currently doesn't model all of the full matrix's multiple horizons, required-return choices, exit-multiple choices, or dividend assumptions.
3. **A misleading regression-mode branch.** The browser selects `regression` for `MSFT` and `0700.HK`, and `auto` for other symbols. That can make fixture results look like ordinary current results unless their mode/data provenance is plainly exposed.
4. **No scenario-level provenance view.** The current UI does not provide a path from each reverse-matrix row to its full set of actual source observations, periods, units/currencies, starting EPS anchor, formula version and computability reason.
5. **Summary labels conceal different computations.** `required_eps_cagr` is mapped from the summary engine; it is not the same as every row's `required_eps_cagr` in the full matrix.
6. **The response contract is summary-oriented.** `ValuationSummary` contains headline fields and `AnalysisResultDTO` provides an optional `raw_analysis` object, but there is no strongly typed first-class scenario matrix that the frontend renders and validates.
7. **Progress/status wording leads with process infrastructure.** Acquisition, admission and replay can help explain data states, but the main user result must be the conditional financial requirements implied by the price.

The web path is not yet the complete reverse-valuation product even though the backend performs related calculations.

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

However, current integration does not complete the reverse-matrix trace:

- `run_st_eva()` places the full matrix in `result["reverse_requirements"]`.
- The reviewed `_build_context_if_requested()` call passes the analysis/evidence/metrics path into the Context builder without passing the full reverse-requirements matrix and all of its row-specific assumptions as the matrix's own trace surface.
- The ordinary `SnapshotManager.save()` payload includes analysis/metrics/evidence/contract and optional context, but does not save the full reverse-requirements matrix as a dedicated snapshot field.
- The web adapter uses `save_snapshot=False` and instead requests a temporary Context JSON plus its per-ticker SQLite archive. The resulting web response maps the headline summary and does not render a row-by-row matrix.

Therefore a reproducible generic Context is not yet the same thing as an end-to-end, inspectable reverse-scenario record. The matrix must become a first-class output with its exact inputs/refs/formula version and must be preserved consistently across JSON display/export and any saved snapshot that claims to represent that reverse valuation.

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

Current implementation baseline: `cb5ab8c`.

- **GitHub Actions:** [run 38140076063](https://github.com/sbvcid/st-eva/actions/runs/38140076063) — backend and browser jobs passed.
- **Local backend suite:** 1,897 passed, 168 skipped, 140 subtests passed.
- **Archive-isolation tests:** 6 passed.
- **Web API tests:** 15 passed.
- **Frontend production build:** passed (`tsc -b && vite build`).
- **Persistent SQLite protection:** local report records SHA-256 hashes for `data/st-eva.sqlite`, the AAPL/MSFT/TSM per-ticker databases and the relevant WAL/SHM files before and after tests; all reported hashes were unchanged.

The three earlier CI failures were resolved in `cb5ab8c`:

1. `test_a_derived_figure_carries_state_flags_only_when_something_is_wrong`: unavailable consensus price derivations are retained in Context instead of omitted.
2. `test_engine_and_context_agree_on_what_is_missing`: `pe_percentile` unavailable state and historical-band sample-count rules align between Engine and Context.
3. `test_the_reference_states_its_basis_and_source`: a user-supplied reference multiple such as `30.0` is passed through with `USER_SUPPLIED` basis.

A regression test was added for unavailable consensus price derivations. These defects are closed; do not spend another task reproducing them unless a later code change reopens them.

## 13. Roadmap and acceptance checklist

Work is sequenced by the user-visible reverse-valuation path. A capability is not complete merely because a module or JSON output exists.

### R0 — CI baseline and data protection — COMPLETE

- [x] Fix the three backend contract failures.
- [x] Add a regression test for unavailable consensus price derivations.
- [x] Run local backend suite, archive-isolation tests, web API tests and frontend build.
- [x] Verify GitHub Actions backend and browser jobs pass on `cb5ab8c`.
- [x] Verify persistent SQLite hashes unchanged before/after reported tests.

Do not redo R0 without a new failure or a code change affecting the protected paths.

### R1 — First-class reverse-requirements matrix in web/API — NEXT

Use the existing `reverse_requirements.py` engine and its `reverse-requirements/1.1` formula contract. Do not create a second engine or start with a broad formula re-audit.

- [ ] Trace the current runner output through `AnalysisServiceAdapter`, API schema/DTO, and frontend result rendering.
- [ ] Make the complete matrix a typed first-class API result, preserving the existing engine's scenario rows and formula version.
- [ ] Provide the necessary user controls for reference multiple, holding period, required-return assumptions, exit multiple, EPS anchor/coverage and return/dividend basis, limited to axes actually supported by the engine.
- [ ] Remove or visibly label the hard-coded browser regression path so fixture outputs cannot appear to be current live prices.
- [ ] Render every scenario's assumptions and calculated outputs, including an explicit unavailable/not-computable state and reason.
- [ ] Add integration tests proving API inputs reach the engine and the returned matrix is not silently reduced to summary metrics.
- [ ] Verify representative rows against the existing engine output or an independent recomputation. Do not repeat all prior formula tests unless implementation changes reveal a defect.

**R1 acceptance:** Enter AAPL in the real browser path; the browser sends explicit assumptions to the normal API path; the response and UI show the actual matrix from the existing engine, with formula version and correct statuses. Regression fixtures are never represented as live market data.

### R2 — Row-level traceability and reproducible output — AFTER R1

- [ ] For each row, expose the exact values and references used: observed price/as-of, EPS value and period, valuation/exit multiple and its basis, holding period, required return, return basis, units/currency and formula version.
- [ ] Make unavailable, conflicting, stale and incompatible inputs visible with reasons; never substitute zero or silently switch sources.
- [ ] Provide a way to inspect or export the selected row's inputs and calculation contract so its numbers can be independently recomputed.
- [ ] If persistence/snapshots claim to preserve reverse-valuation results, preserve the matrix and row assumptions explicitly rather than only a summary.

**R2 acceptance:** A reviewer can select a displayed row, retrieve its exact inputs and formula version, and independently reproduce its numeric outputs or confirm why it is not computable.

### R3 — AAPL live end-to-end acceptance — AFTER R1/R2

- [ ] Run AAPL through the ordinary web/API flow with its mode and source times visible.
- [ ] Check the current price/as-of and source; EPS value, currency and coverage period; and reference-multiple basis and eligibility.
- [ ] Verify the displayed matrix reflects those actual inputs rather than an unrelated fixture or stale artifact.
- [ ] Independently recompute representative rows and follow their source references.
- [ ] Confirm UI and export/persistence preserve the same assumptions, formula version and status.

The existing `data/historical_pe/AAPL/reverse_requirements_output.json` was reported to contain 27 scenarios under formula version `1.1`, sourced via Yahoo v8 with an as-of date of 2026-10-06. Treat this as an existing local artifact to inspect if needed, not proof of live browser completion or current market freshness. Its reported untracked status must be checked locally before deciding whether to keep it, ignore it, or add it to version control.

### R4 — Additional tickers and methods — DEFERRED

Only after AAPL passes the browser acceptance path should the same interface be extended to MSFT/MU/TSM or additional multiple/DCF/dividend methods. Do not expand the product surface ahead of the primary workflow.

## 14. Archive decision and cleanup state

The local Phase 1/2 audit has been completed. Its detailed CSV reports are disposable working artifacts, not product dependencies; the durable decision and follow-up rules are recorded in this status file. Do not regenerate the audit reports merely because their local directory is removed.

- **Integration decision:** no archive content was copied, merged or imported into the current project.
- The 10 MSFT historical-P/E validation Python files were content-hash matches for files already present in the current research experiment path.
- The archive experiment group, 116 unmatched Python files and large snapshots were not shown to fill a current product gap; they were not integrated.
- The reported cleanup classification was approximately 1.3–1.5 GB `NO_LONGER_NEEDED` and 0.8–1.0 GB `REVIEW_REQUIRED`. These were audit estimates, not deletion results.
- At the time of the integration decision, no archive contents had been deleted. The user has since clarified the retention rule: archive material should be kept only if it fills a demonstrated current-product gap; historical uniqueness alone is not a reason to keep it.
- The remaining archive contains old DB versions, MU data and experimental snapshots that were not integrated. Deleting them means accepting the loss of their historical/research contents, not removing anything required by the current product according to the audit completed so far.

Do not rerun the full archive inventory or repeat Phase 2. If the user proceeds with deletion, execute only after closing programs using the archive, verify the exact target paths, and keep `C:\git\st-eva` untouched. Preserve current project runtime databases under `C:\git\st-eva\data`; never delete them as part of archive cleanup. Archive cleanup is separate from R1–R3 and must not delay product implementation.

## 15. Explicitly not yet accepted as complete

- [ ] Full configurable reverse-requirements matrix wired from browser inputs through the API to the existing engine and back to the UI.
- [ ] Row-level lineage showing actual inputs, source references, period, units/currency, formula version and computability reason.
- [ ] Reproducible selected-row inspection/export and any corresponding persisted matrix snapshot.
- [ ] Live AAPL web end-to-end acceptance; the existence of a 27-row JSON artifact alone does not meet this criterion.
- [ ] Removal or clear labelling of regression fixtures in the ordinary browser path.
- [ ] One consistent production eligibility rule for historical valuation bands across selectors and matrix construction.
- [ ] Default web use of the dedicated daily point-in-time historical P/E reconstruction.
- [ ] Confirmation that the current local canonical valuation-input boundary contains only qualified/admitted inputs, distinct from an audit archive that may store refused observations.
- [ ] Execution of the separately planned archive cleanup; no removal should be claimed until the exact paths are deleted and the resulting state verified.

Not prerequisites: live LLM integration, keeping every historical experiment, or copying archive-only files into the current repository without a demonstrated product gap.

## 16. Documentation and evidence sources

- [Root README](../README.md): stable product goal, core data/calculation rules and non-goals only.
- [This document](PROJECT-STATUS.md): authoritative current code state, completed evidence, open acceptance checks and next task. Update this file when state changes; do not add another parallel roadmap/status file.
- [CLI usage](USAGE.md): commands/options and current command-line behavior.
- [Frontend usage](../web/frontend/README.md): start/build instructions and current frontend boundary.
- `docs/archive/`: historical plans, status snapshots and architecture notes. They are not the current project-state source and must not override current code or the user's present direction.
