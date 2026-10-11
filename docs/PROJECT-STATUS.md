# ST-EVA — Current Project Status

**Status checked:** 2026-10-11  
**Repository:** `sbvcid/st-eva`, branch `master`  
**Implementation baseline:** `9a43f9f`  
**Documentation-only commits after that baseline:** through `b057b94` at the time of this review.  
**Latest checked CI for the same implementation baseline:** [run 38137995221](https://github.com/sbvcid/st-eva/actions/runs/38137995221), triggered at `1d0ef0b`; backend failed, browser job passed.

This is the live, changeable implementation/status record. The root [README](../README.md) contains the enduring product definition and rules. This file records what is implemented, wired, not wired, failing, or not yet verified. Historical files under `docs/archive/` are not current status or instructions.

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

Current latest tests expose some disagreement between engine output and Investment Context for missing values and a supplied reference. See CI defects below.

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

## 12. Latest verified CI status

Latest checked run for the same implementation code: [GitHub Actions run 38137995221](https://github.com/sbvcid/st-eva/actions/runs/38137995221), commit `1d0ef0b` (documentation-only change after code baseline `9a43f9f`).

- **Backend:** failed — 3 failed, 1,893 passed, 168 skipped, 140 subtests passed.
- **Browser job:** passed.
- **Frontend production build:** passed.
- Archive-isolation tests: 6 passed in the logged run.
- Web API tests: 15 passed in the logged run.

The backend failures reported by the CI log are:

1. `tests/test_2_4_3_traceability.py::TestS3DerivedFigureTraceability::test_a_derived_figure_carries_state_flags_only_when_something_is_wrong` — `KeyError: 'consensus_price_gap'`. The same assertion also reports a contract mismatch: an unavailable/nullable `approx_historical_pe_percentile` field is absent from the Context where the test expects the field to be represented.
2. `tests/test_investment_context.py::TestUnavailableContract::test_engine_and_context_agree_on_what_is_missing` — the engine represents `pe_percentile` as unavailable/null, while the Context omits it.
3. `tests/test_investment_context.py::TestConditionalContract::test_the_reference_states_its_basis_and_source` — the test supplies a user reference multiple of `30.0`, but the Context's recorded multiple is `None`; the source/basis and selected multiple are not joined consistently.

These fail at the intersection of calculation semantics, unavailable-value representation, and traceability. They should be resolved by fixing the underlying engine/Context contracts and their inputs, not by simply weakening the tests.

The current code baseline has not been validated as CI-green. Documentation-only commits do not resolve these failures.

## 13. Verified gaps and priority

### P0 — Preserve data and make the current contract honest

- Protect the existing `data/st-eva.sqlite` and per-ticker archives; audit file/deletion/reset and migration paths read-only first.
- Fix the three currently failing backend tests by aligning engine, context and derived-figure contracts for missing fields and user-supplied reference multiple.
- Keep regression fixtures clearly separate from live acquired data.

### P1 — Establish one unambiguous reverse-calculation contract

- Explicitly separate (a) price/reference-multiple implied fundamental, such as `price / P/E`, from (b) terminal EPS and growth required by a chosen horizon, return hurdle and exit multiple.
- Verify each named output's formula, starting EPS basis, coverage period, currency/unit constraints, return basis, computability status and formula version.
- Apply one eligibility policy to historical distributions: descriptive stats may exist below threshold or with missing sample count, but such a band cannot become an eligible reference without meeting the production gate.

### P2 — Finish end-to-end matrix and trace flow

- Extend the request/UI contracts to the actual scenario axes needed by the product.
- Make the full matrix a first-class typed result, not a hidden field only available in the core run result.
- Carry row-specific assumptions and input/source references through Context/export/persistence; record formula version and fingerprint.
- Show unavailable/conflicting/mismatched inputs and why an individual scenario is not computable.
- Remove or make explicit the hard-coded regression path in the browser; never let fixtures appear to be live prices.

### P3 — Verify the first real issuer path, not just isolated modules

Use AAPL as the first end-to-end acceptance case:

- Run through the actual web UI and normal API path with live mode clearly declared.
- Verify the displayed price date, price source, EPS source and covered period, reference-multiple source/sample eligibility, all scenario inputs and output numbers.
- Independently recompute selected matrix rows from the recorded operands and formula version.
- Follow a row back to source observations/documents and verify unavailable/conflicting states.
- Confirm the same saved output can be read/exported without loss of assumptions or trace information.
- Keep regression mode in tests and labelled examples only; do not treat its outputs as current market values.

Only after this works should the same product path be expanded to MSFT/MU or further metrics.

## 14. Not yet verified / do not claim completed

- The complete, configurable reverse-requirements matrix in the browser.
- End-to-end row-by-row traceability from the browser output to exact observations, source documents, EPS anchors, formula version and computation inputs.
- A dedicated reverse-matrix snapshot/archive/export contract.
- A single consistent production eligibility rule for historical valuation bands across reference selectors and matrix construction.
- Default web usage of the dedicated daily production historical P/E reconstruction.
- Full archived SEC metric admission into the valuation-input surface; the reviewed V1 boundary only admits `revenue`.
- A canonical database containing only qualified admitted inputs, as distinct from an audit archive that also records refused/held-out facts.
- Passing backend CI.
- Any need for a live LLM integration; this is not a prerequisite for product completion.

## 15. Documentation and evidence sources

- [Root README](../README.md): stable product goal, core data/calculation rules and non-goals only.
- [This document](PROJECT-STATUS.md): current code state, defects, tests and work sequence.
- [CLI usage](USAGE.md): commands/options and current command-line behavior.
- [Frontend usage](../web/frontend/README.md): start/build instructions and current frontend boundary.
- `docs/archive/`: historical plans, status snapshots and architecture notes. They are not the current project-state source and must not override current code or the user's present direction.
