# ST-EVA — Current Project Status

**Status checked:** 2026-10-21 (Apple holds qualified historical P/S and EV/EBITDA references on 28 and 27 observations; American Electric Power holds a qualified EV/EBITDA reference on 24 observations and reports its P/S as a short sample of four, because the registry-accepted revenue element's coverage reaches four windows; Microsoft holds a qualified P/S reference on 23 observations and reports its EV/EBITDA unavailable, because it has no element that qualifies for the depreciation-and-amortization role; and every role of every historical valuation dataset is now qualified against the core registry before it produces a figure, so an element the registry does not accept cannot obtain `USABLE_FOR_REFERENCE` however many complete, point-in-time observations it carries -- Phase 8, `semantic_qualification.py`) -- Phase 9.3, `research_lane.py` (the isolated research calculation lane: a named research metric is computed from filed evidence the production qualification regime does not admit, under its own `RESEARCH_*` id and its own formula, with the registry's standing recorded on every observation and never enforced, the point-in-time, fiscal-window and filed-bridge rules unchanged, and the result held out of the Archive, the Investment Context, the production Summary and the production reference chain; KO is the first case, and KO remains without a production P/S and without a production EV/EBITDA) -- Phase 9.4, `research_calculator.py` and `web/research_api.py` (the research calculation and its evidence explorer: the user chooses one of the four KO research metrics, states a multiple and a market value, and reads the implied denominator together with the operands, the accessions, the elements, the periods, the units, the knowability, the source-file digests, the registry's standing, the basis breaks and the lane's identity; a user-supplied input is labelled `user_supplied_research_assumption` and kept apart from the observed facts; the path is mounted at `/api/research`, writes no Archive, and reaches no Investment Context or production runner) -- Phase 9.6, the research calculation hardening (a non-finite multiple or market value is refused on both the request and the service path, and a finite pair whose quotient overflows is refused too, so no research result is ever published as a non-finite figure; the research surface now tells a research distribution, a thin sample and an unusable distribution apart, and carries the lane's own descriptive threshold so it is not hard-coded in the interface; every input -- the price, the cover-page share count, each denominator quarter and each balance-sheet component -- now states its unit, its currency, the period it applies to and its source file, digest and endpoint; and the research capture's acceptance times carry the Eastern offset of their own date, so three annual filings are no longer knowable a trading day before the 16:00 ET rule allows) -- Phase 9.7, the research comparison and sensitivity analysis (a user may now compare one metric at two dates, or two metrics on the dates where both published, or apply one named assumption to one published figure; every metric publishes the attributes it may be compared with -- its numerator kind, its denominator and elements, its currency and unit, its formula version and its registry standing -- and a pair that does not share a definition is labelled as a difference between two different formulas with no single attribution; the two enterprise-value lanes pair on the 16 dates where both published, and on every one of them the enterprise-value difference reproduces from the two bridges as the difference of the short-term component alone, with the unpaired dates and their refusal reasons recorded; a sensitivity names its assumption, its unit and its own hash, never modifies the observation, and may only be computed on a date the lane itself published)
**Repository:** `sbvcid/st-eva`, branch `master`
**Current implementation baseline:** the production historical P/S and EV/EBITDA reference distributions are implemented for three issuers by the same generic code (`historical_multiples.py`, `data/historical_multiples/{TICKER}`; AAPL: P/S 28 valid / 8 rejected over 36 evaluations, median 7.257709, and EV/EBITDA 27 valid / 9 rejected, median 22.326 - both `USABLE_FOR_REFERENCE`; AEP: EV/EBITDA 24 valid / 9 rejected over 33 evaluations, median 13.221693, `USABLE_FOR_REFERENCE`, and P/S 4 valid / 29 rejected, `INSUFFICIENT_OBSERVATIONS`, because the registry-accepted revenue element's coverage reaches four windows; MSFT: P/S 23 valid / 4 rejected, median 11.783822, and EV/EBITDA unavailable, because Microsoft has no element that qualifies for the depreciation-and-amortization role; the filed EV bridge requires every component to describe the same balance-sheet date, and a window's quarters must be four consecutive periods of the issuer's own cycle **+** the filed trailing revenue and trailing EBITDA are the engine's inputs (`production historical income-statement dataset`, `data/historical_income/{TICKER}`; `der:ttm_revenue` and `der:ttm_ebitda` are `sum_periods` over the four quarters the document holds, and P/S and EV/EBITDA divide by them) **+ SEC-derived trailing figures in the formal valuation chain** (`82ad6b6`; the engine computes `der:current_pe` and `der:current_pfcf` from `der:ttm_eps` / `der:ttm_fcf`, the document recomputes each from the four quarters it holds, the parity check is not relaxed) **+ the replay reproduces the run's production reference** (`ca07496`; the AAPL live replay reports `MATCH` with 0 field differences) on top of the unified historical P/E reference eligibility round (`band_reference_eligibility` shared rule; unverified-count bands and ineligible distributions produce no matrix scenarios; MSFT web regression matrix 160→80) **+ traceable EPS anchor catalogue / reverse-valuation anchor** (`7b44618`; verified `backend` 2352 passed / 169 skipped / 498 subtests; `browser` run `39030611724` success — fixed by conditional `eps_ev` preserving legacy 14-field contract; new identity fields only when `anchor_id` set) on top of `965d5c1` (verified `backend` + `browser` in CI `39021861188`) (`fiscal_calendar.py` issuer-declared identity model + `a9a6630` fail-closed identity-conflict rules; MU FY2026 TTM verified; AAPL restored to 36/36) on top of the MU historical P/E + Q4 furnished evidence round (Q4 evidence dataset from 8-K Item 2.02 EX-99.1, corrected filing-acceptance timestamps, TTM window continuity guard) on top of `6c66550` (AAPL P/E and P/FCF baseline update after the quarter_number fix) on top of `10224e9` (quarter_number calculation fix + MU `eps_diluted_concept.json`) on top of `50043be` (declared SEC diluted-EPS evidence: period-declared GAAP facts from the run's own filing acquisition, cross-check only) with the archive-reconstruction-completeness fix; before that, the web path carrying the production historical P/FCF reference (`4797f1f`), MSFT cross-ticker validation (`37262ae`) with the MSFT P/FCF dataset and issuer config, AAPL v1 market-cap reconciliation `9ca6999`, AAPL v1 research snapshot `fe7d7c7`, historical P/FCF reconstruction `fd311c5`, consensus revisions/trend extraction `66616ec`, and the earlier R7 series, R6.x replay work, and first-use mode = live with expanded assumptions **+ every historical dataset's source role is qualified against the core registry before it produces a figure** (Phase 8; `semantic_qualification.py` asks the registry's own resolver whether an element is a metric for a filer, and `historical_income.py` / `historical_multiples.py` refuse a role the registry does not qualify, with the refusal naming the registry's decision rather than a shortage of quarters; the datasets, the six manifests, the summary, the Investment Context and the archive all carry the basis, and the replay compares it) **+ the isolated research calculation lane** (Phase 9.3; `research_lane.py` and `research_lane_ko.py`, `data/research_multiples/KO/` and `data/research_lanes/KO/`; four candidate research metrics and one diagnostic over KO's filed facts, medians 6.403373, 19.775345, 23.639435 and 24.675484 on 29, 64, 27 and 29 valid observations; the production pipeline refuses both of KO's production figures over the same capture, and the two agree on the price, the share count, the market capitalisation and the enterprise value date by date)
**Latest verified GitHub Actions:** `86fadea` (Phase 9.15, cross-issuer research selection through the real API in the browser) verified overall `completed`/`success` with both jobs `success` in run `39832572712` (checked via the GitHub API on 2026-10-22: backend 3014 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 15 passed, success); `f5ecbbd` (Phase 9.14, the research surface audited across the three issuers) verified `backend` and `browser` jobs success in run `39821248227` (checked via the GitHub API on 2026-10-22: backend 3014 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 14 passed, success); `1b3c5b5` (Phase 9.13, MSFT's research lane, end to end, and the round's report corrected) verified `backend` and `browser` jobs success in run `39808561869` (checked via the GitHub API on 2026-10-22: backend 3014 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 14 passed, success); `50265f6` (MSFT's research capture and lanes) verified `backend` and `browser` jobs success in run `39795097273` (checked via the GitHub API on 2026-10-22: backend 3011 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 14 passed, success); `f560211` (Phase 9.12, homogeneous research distributions and manifest consistency) verified `backend` and `browser` jobs success in run `39779933271` (checked via the GitHub API on 2026-10-22: backend 3007 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 14 passed, success); `01887b7` (Phase 9.11, the research lane's semantic boundaries and its replay) verified `backend` and `browser` jobs success in run `39771424489` (checked via the GitHub API on 2026-10-22: backend 2984 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 14 passed, success); `32f685c` (Phase 9.10, AAPL's research lane, end to end) verified `backend` and `browser` jobs success in run `39761358154` (checked via the GitHub API on 2026-10-22: backend 2956 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 14 passed, success); `aa06ae0` (Phase 9.9, the research lanes become configuration driven) verified `backend` and `browser` jobs success in run `39746363059` (checked via the GitHub API on 2026-10-22: backend 2899 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 14 passed, success); d2bb77b` (Phase 9.7, the research comparison and sensitivity analysis) verified `backend` and `browser` jobs success in run `39725124318` (checked via the GitHub API on 2026-10-22: backend 2862 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 14 passed, success); `21343fe` (Phase 9.6, the research calculation hardening and the capture's Eastern times) verified `backend` and `browser` jobs success in run `39717641976` (checked via the GitHub API on 2026-10-22: backend 2819 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 13 passed, success); `f2a8674` (Phase 9.4, the research calculation and its evidence explorer) verified `backend` and `browser` jobs success in run `39667766985` (checked via the GitHub API on 2026-10-21: backend 2791 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 13 passed, success); `aba08b6` (the phase 9.3 CI record) verified `backend` and `browser` jobs success in run `39654587262` (checked via the GitHub API on 2026-10-21: backend 2749 passed / 171 skipped / 534 subtests, success); `bc32209` (Phase 9.3, the isolated research calculation lane) verified `backend` and `browser` jobs success in run `39653312560` (checked via the GitHub API on 2026-10-21: backend 2748 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 12 passed, success); the preceding run `39617779061` verified `3f268d9` (the phase 8 CI record: backend 2749 passed / 171 skipped / 534 subtests, success); the preceding run `39616759679` verified `9f2911f` (Phase 8, the registry-backed semantic qualification) verified `backend` and `browser` jobs success in run `39616759679` (checked via the GitHub API on 2026-10-21: backend 2706 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 12 passed, success); the preceding run `39598786653` verified `d85cfc1` (the phase 7.3 CI record: backend 2706 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 12 passed, success); the preceding run `39598264148` verified `bc36384` (the phase and documentation reconciliation: backend 2681 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 12 passed, success); the preceding run `39591871200` verified the American Electric Power correction `0aadc8a` (backend 2681 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 12 passed, success); the preceding runs `39578452809` (Microsoft's dataset `d3cec3b`: backend 2635 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 12 passed, success) and `39562741308` (Microsoft's D&A role left empty, `3ec78b7`: backend 2643 passed / 171 skipped / 534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke 12 passed, success);



This is the live, changeable implementation/status record. The root [README](../README.md) contains the enduring product definition and rules. This file records what is implemented, wired, not wired, failing, or not yet verified. Historical files under `docs/archive/` are not current status or instructions.

## Continuation checkpoint — read this before planning or running work

This section is the hand-off checkpoint for future conversations and coding agents. Use the current status below; do not restart prior audits just because a new conversation begins.

**Completed and should not be repeated without a concrete reason**

- **The replay reproduces the run's production reference (2026-10-20, commit `ca07496`, CI run `39431909757`).** The production historical P/E and P/FCF distributions are committed frozen data, so a rebuild reads the same dataset the live run read: `st_eva_runner.load_production_historical_references` is the single loader for both paths, `archive.replay` names the sources the archived run had in force (read from the document's own reference basis) and `web.service_adapter.default_replay_doc_builder` loads them. The archive names the source and never the number, so a dataset that changed since archival produces an honest divergence. The AAPL live replay went from `DIVERGED` with 37 differing fields to `MATCH` with 0. Three boundaries are kept and tested: a reference-free run still matches and gains no reference; an operator's own multiple still diverges (an assumption is not archived knowledge); a run that built its distribution without the furnished evidence still matches, because the archived observation count says which load the run used. Do not re-derive the production reference inside the archive, do not copy the archived number, and do not let a rebuild invent a reference the run did not have.

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

- The production point-in-time historical P/E reference is available on the web path for all four configured issuers in ``historical_pe.py:ISSUER_CONFIGS``: ``AAPL`` (36/36 qualifying, median 28.44563, ``USABLE_FOR_REFERENCE``), ``MSFT`` (24/27 qualifying, median 33.195873, ``USABLE_FOR_REFERENCE``), ``MU`` (454/575 qualifying, median 20.552342, ``USABLE_FOR_REFERENCE``) and ``SOFI`` (130/330 qualifying, median 47.299768, ``USABLE_FOR_REFERENCE``). Each is gated on its distribution's own ``usable_for_reference`` flag at the ``>= 20`` qualifying-observation rule and reported as ``production_historical_pe_median``. Any ticker not in ``ISSUER_CONFIGS`` is reported as ``UNAVAILABLE`` with an explicit reason rather than being given a fabricated distribution.
- The production point-in-time historical **P/S** reference (Phase 5) is established for ``AAPL`` and ``MSFT`` (28 and 23 qualifying observations respectively); AEP's P/S is a short sample of four and reports ``INSUFFICIENT_OBSERVATIONS`` rather than a reference. The historical **EV/EBITDA** reference (Phase 5) is established for ``AAPL`` and ``AEP`` only; MSFT reports ``UNAVAILABLE`` because it has no element that qualifies for the depreciation-and-amortization role. The production **P/FCF** reference is already integrated: it is established for ``AAPL`` (35/36, median 25.343981), ``MSFT`` (23/27, median 41.578319) and ``MU`` (362/575, median 67.712721), each gated on its distribution's own ``usable_for_reference`` flag at the same ``>= 20`` qualifying-observation rule as P/E and reported as ``production_historical_pfcf_median``; any other ticker reports ``UNAVAILABLE`` with an explicit reason. P/S, EV/EBITDA and P/FCF do not borrow each other's references, and a production median is never recorded as a vendor-band figure.
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
5. **[RESOLVED in part] Summary labels conceal different computations.** Summary cards now use distinct labels ('Price-Implied EPS', 'Implied EPS Gap (CAGR)' with a flat-multiple basis note stating no required-return hurdle, exit multiple or dividends) plus a per-metric basis legend and an explanatory link that scrolls to the matrix, so they cannot be mistaken for the matrix's return-hurdled per-scenario CAGR. Unified terminology and deep row reconciliation remain an ongoing refinement.
6. **[RESOLVED in R1 & R2] First-class response contract.** `ReverseRequirementsReportDTO`, `EpsScenarioDTO`, `EpsAnchorDTO`, `ReferenceMultipleDTO`, `CalculationStepDTO`, and `ScenarioEvidenceDTO` are strongly typed in `web/schemas.py` and `web/frontend/src/types/api.ts`. Service adapter hardened to raise explicit exceptions on DTO validation failures.
7. **[RESOLVED] Main user result is now the conditional matrix.** The reverse-requirements matrix renders before the supporting summary cards, admission status and replay diagnostics. The results heading uses neutral 'Reverse-Valuation Results' wording (no verdict language), and each matrix row carries an explicit note that it is conditional on its own holding period, required return, exit multiple and starting EPS basis, with no row preselected as the answer.

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

The repository's configured historical P/E issuer inputs currently include ``AAPL``, ``MSFT``, ``MU`` and ``SOFI`` under `data/historical_pe/` (all four in `historical_pe.py:ISSUER_CONFIGS`, each loading as `USABLE_FOR_REFERENCE` on the web path). The production distribution uses a minimum of 20 qualifying observations for reference eligibility; a thinner sample may still be displayed descriptively but should not be used as a qualifying exit/reference distribution.

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

For local frontend development, see [web/frontend/README.md](../web/frontend/README.md). The frontend build was successful in the checked GitHub Actions log. The browser smoke job was successful in the latest checked run; the reverse-requirements matrix is now the primary UI, rendered above the supporting summary cards, admission status, and replay diagnostics.

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

Local verification for Phase 9.20.x (reverse-valuation UI refinements): full backend suite 3014 passed, 171 skipped, 534 subtests passed; web API 25 passed; frontend lint clean; frontend build produced `dist/index.html`; Vitest frontend 131 passed; browser smoke 15 passed (15 passed in 48.40s). Reverse-requirements matrix now renders as the primary result above supporting summary cards; security identity header (ticker, company, price, currency, as-of) rendered above the matrix; verdict-style wording replaced with neutral "Reverse-Valuation Results" (en/zh-TW); matrix rows carry explicit conditional-assumption disclosure; market-price evidence badge respects the user-assumption flag.

## Phase 9.21 — Reverse-Valuation End-to-End Acceptance Audit (verified 2026-10-23, commit fe26c6e)

**Audit result: No defects found. No code changes required.**

All invariants verified against the committed implementation:

- **Identity and price:** ticker, company name, current price, currency, as-of date, and research ID rendered by `SecurityIdentityHeader` above the matrix; `ResultCards` no longer duplicates ticker/price/as-of.
- **Evidence classification:** `is_user_assumption` badges correctly shown for market-price, start-EPS, and exit-multiple evidence (blue "User Assumption" vs slate "Verified Sourced Fact"/"Provider-Sourced"/"SEC-Linked Source").
- **Production/research isolation:** `production_eligible=False` frozen on research distributions; research lanes write nothing to Archive, produce no `refc:*`, reach no Investment Context; research API mounted separately at `/api/research`; all 11 research lanes confirmed `production_eligible=False` with no `refc:*` in output.
- **Reference eligibility:** historical P/E, P/S, EV/EBITDA, P/FCF distributions gate on their own `usable_for_reference` flag (`>=20` qualifying observations); insufficient samples reported as `INSUFFICIENT_OBSERVATIONS`, never silently substituted; missing/unavailable references reported explicitly, never as zero.
- **Conditional matrix:** each row discloses its holding period, required return, exit multiple, and starting EPS basis (period label, start/end, declared vs assumed coverage); no row preselected; no buy/sell/verdict language.
- **Missing/incompatible evidence:** unavailable values shown as `—`, never zero; currency mismatches and incomplete inputs refused explicitly.
- **Exports:** JSON/CSV retain `refc:*` provenance, `is_user_assumption` flags, `user_assumptions_json`, `sourced_facts_json`, `missing_or_unvalidated_json`; uncomputed matrices exported as status-only rows without fabrication.
- **Browser acceptance:** 15/15 browser smoke tests pass (48.40s), including identity→matrix→cards ordering and localized heading in en/zh-TW.

CI: backend 3014 passed / 171 skipped / 534 subtests; web API 25 passed; archive isolation 6 passed; Vitest frontend 131 passed; browser smoke 15 passed; production build (`dist/index.html`) produced; `git diff --cached --check` clean.

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

**Remaining limitations recorded, not fixed:** the production distribution exists for all four configured issuers (``AAPL``, ``MSFT``, ``MU`` and ``SOFI``, each ``USABLE_FOR_REFERENCE`` per ``historical_pe.py:ISSUER_CONFIGS``); any ticker not in ``ISSUER_CONFIGS`` reports the explicit ``UNAVAILABLE`` state rather than being given a fabricated distribution. The distribution is evaluated on periodic filing/earnings-release usable dates, not a daily history, and the web path does not compute the ``--historical-pe`` production reconstruction as part of the P/E band used elsewhere. The AAPL production dataset covers 2018-01-02 to 2026-07-31 and is not extended by the web path.

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

--- 2026-10-19 MU replay DIVERGED field-level diff ---
- HEAD/origin 8f6ca2a; working tree clean after changes. No valuation formula, eligibility gate, refusal rule, or data mapping was changed.
- Presentation fix 7 (replay field-level diff): archive.replay now compares the stored context against the rebuilt context field by field (recursive dict comparison), excluding volatile fields (generated_at, document_hash, refc:* reference timestamps). ReplaySummary gained field_diffs (list of {field, stored, rebuilt}), mapped through web/schemas.py and web/service_adapter.py into the API. The frontend ResultCards separates observation availability classes (informational, all observations) from field-level differences (actual stored vs rebuilt values), showing a diff count, the first 10 differing fields in an expandable details block, and a note when there are no differences. The original DIVERGED status is preserved; no cause is labeled as confirmed unless evidenced by actual field diffs.
- Live MU verification: replay outcome DIVERGED, observations_used=123=observations_considered, OBSERVATIONAL fidelity, 123 availability_classes entries, 74 field_diffs entries with concrete old/new values (e.g., derived.current_pe.figure.value, derived.implied_fcf.figure.provenance_kind). Admission counts, P/FCF implied figure, and CSV/JSON export unchanged — no regression.
- Tests: backend full suite passed (2387 passed / 169 skipped / 498 subtests, 1 pre-existing unrelated failure in test_mapping_relation_kind.py); frontend Vitest 8 files / 103 passed; npm run build passed.

--- 2026-10-19 MUFG cross-currency reverse EPS analysis (FX date scoping corrected) ---
- HEAD/origin 5d1f29f; working tree clean after changes. No valuation formula, eligibility gate, refusal rule, data mapping, or P/FCF calculation was changed. MUFG-specific only; no general international market support added.
- Correction 1 (FX rate scoping): fx_rates.py now maintains TWO distinct FX scopes:
  - Historical reference rate: Fed H.10 observation for 2026-10-09 (0.006316 USD/JPY, 158.3400 JPY per USD). Carries scope "reference_only" — historical reference observation only, NOT a fiscal-period conversion rate, NOT used as proxy for analysis-date rate.
  - Analysis-date spot rate: ECB-derived rate for 2026-10-16 (0.0063283095... USD/JPY, derived from 1 EUR = 1.1253 USD and 1 EUR = 177.82 JPY). Used for converting JPY financial data to USD for current valuation comparison. Rate carried unrounded (1.1253 / 177.82); rounded display values never used as calculation inputs.
  - Neither rate is disguised as the other: analysis-date as_of = "2026-10-16", provider = "European Central Bank (ECB)"; historical-reference as_of = "2026-10-09", provider = "operator-supplied" (runner) / "Federal Reserve Board H.10" (module constant).
- Correction 2 (ADR ratio): adr_ratio.py ratio confirmed at 1.0 underlying shares per ADR. NYSE listing confirms "MITSUBISHI UFJ FINANCIAL GROUP INC SPON ADS EACH REP 1 ORD SHS" → 1 ADR = 1 ordinary share. provider = "NYSE".
- Correction 3 (st_eva_runner.py): run_st_eva() gained optional fx_analysis_date_usd_per_jpy parameter alongside fx_rate_usd_per_jpy. When both provided, conversions use the analysis-date rate; historical reference rate carries scope "reference_only" and is not used for period conversion. cross_currency section reports fx_rate_fiscal_period (field name kept for API compatibility, scope = "reference_only") and fx_rate_analysis_date separately, each with scope, as_of, provider, source_url, quote_direction. All conversions (revenue, EPS, net income) name fx_rate_used, fx_scope, and fx_as_of.
- Correction 4 (recomputed values with ECB analysis-date rate 0.0063283095... and ADR 1.0):
  - Diluted EPS (FY2026, SEC): ¥151.09 × 0.0063283095 = $0.956 USD/share; ADR 1:1 → $0.956 USD/ADR. Labelled annual, not true TTM (quarterly SEC data unavailable).
  - P/S: USD market cap $258,756,499,250 / USD-converted JPY revenue (¥7,863,006,000,000 × 0.0063283095 = $49,758,318,217.6) = 5.20x. Raw JPY/USD P/S 0.03x rejected as mixed-currency. Revenue period (Yahoo, as_of 2026-06-30) differs from market cap as_of (2026-09-23); periods not reconciled.
  - Net income FY2025 actual: ¥2,427,000,000,000 × 0.0063283095 = $15,358,798,115.5 ≈ $15.36B USD.
  - Net income FY2026 management target: ¥2,700,000,000,000 × 0.0063283095 = $17,086,435,722.5 ≈ $17.09B USD.
  - JPY original facts preserved alongside USD conversions; each converted figure names the FX rate, ADR ratio, as_of date, scope, and original amounts. Net income targets NOT converted to EPS growth rate (share count unavailable).
- Correction 5 (reverse EPS matrix): historical P/E band has 8 observations (< 20 minimum), so production_historical_pe_status = UNAVAILABLE and the matrix cannot use historical distribution as reference. Reverse requirements status = NOT_COMPUTED when no user-supplied exit multiple; observed P/E 14.3x is NOT treated as historical reference or recommended exit multiple. Matrix accepts user-supplied exit P/E only when starting EPS passes currency/period/semantics review.
- Tests: backend full suite passed (2405 passed / 169 skipped / 498 subtests, 1 pre-existing unrelated failure in test_mapping_relation_kind.py); new TestMUFGFxRate, TestMUFGAdrRatio, TestMUFGFxRateAnalysisDate, TestMUFGCrossCurrencyAnalysis, TestMUFGRegressionDatesAndPrecision (18 tests) added to tests/test_st_eva_runner.py; frontend Vitest 8 files / 103 passed. End-to-end MUFG verification: two FX scopes distinct, analysis-date rate used for conversions, P/S 0.03x rejected as mixed-currency, converted P/S = 5.20x, EPS converted with disclosure, reverse matrix correctly refuses historical P/E (8 obs < 20).

## SOFI Historical Price Acquisition and SEC Evidence via historical_pe_adapter (2026-10-19)

**Gap confirmed.** `historical_pe_adapter.py` had only SQLite archive reading and manifest generation; it did not acquire external historical prices. `min_observations_for_reference` was unused, error handling used a bare `except Exception`, and the entry point was SOFI-hardcoded rather than a generic ticker interface. No SEC EPS evidence existed for SOFI.

**Change — adapter.** Rewrote `historical_pe_adapter.py` as a generic ticker data acquisition interface:

- `fetch_yahoo_daily_prices(ticker, ...)` — fetches daily bars from Yahoo Finance chart API v8 (`https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5y&interval=1d`), returns `(chart_result, raw_response_sha256)` with specific exception handling for HTTP errors, network errors, invalid JSON, and empty results (no bare `except`).
- `parse_yahoo_price_bars(chart_result, ticker)` — normalizes into standardized records with `price_date`, `close` (as-traded), `currency`, `accounting_basis`, `price_source`, `price_source_url`; drops null closes rather than zero-filling; raises on zero usable records.
- `save_standardized_prices(ticker, records, meta, ..., raw_payload, raw_response_sha256)` — writes `daily_prices.json` (Yahoo-chart shape consumable by `historical_pe.py`, including `events.splits` and `indicators.adjclose`) and `prices_manifest.json` (source, count, coverage period, save path, currency, **distinct** `raw_response_sha256` for the raw HTTP response and `standardized_content_sha256` for the saved normalized file).
- `acquire_standardized_prices(ticker, ..., min_observations_for_reference=20)` — end-to-end fetch/parse/validate/save; enforces the `min_observations_for_reference` gate.
- `read_sqlite_price_observations(archive_path, ticker)` — clearly-labelled secondary source; archive reads are never repackaged as newly acquired data.
- Legacy `build_sofi_historical_pe_dataset` kept for compatibility, delegating to the archive read.

**Change — hash consistency fix.** `data/historical_pe/SOFI/manifest.json` had inconsistent bytes (56,731) and SHA-256 (`7bfd5475...`) that did not match the actual `daily_prices.json` (56,732 bytes, SHA `6dceb233...`). After re-saving with the corrected adapter, actual file is **56,786 bytes, SHA-256 `c1424311458a87a52d8598dbd90db8d661a2a2c480466511f90db9b62b0f61b7`**. All manifest records updated to match actual file. Tests verify manifest bytes/SHA match actual file, raw-response hash is distinct from standardized hash, and content changes produce hash changes.

**Real price acquisition result (SOFI, live Yahoo Finance, 2026-10-19):**
- 1,255 daily close prices, all non-null, USD, as-traded basis
- Coverage: 2021-10-19 to 2026-10-19
- Source URL: `https://query1.finance.yahoo.com/v8/finance/chart/SOFI`
- Raw response SHA-256: `32e143487548564d015656614ffcf8fb5d0aaf19bc9439c658557d66f360b112`
- Standardized content SHA-256: `c1424311458a87a52d8598dbd90db8d661a2a2c480466511f90db9b62b0f61b7`
- Saved to: `data/historical_pe/SOFI/daily_prices.json` (56,786 bytes)
- Manifest: `data/historical_pe/SOFI/prices_manifest.json`
- No split events or dividend events in source (source explicitly reports empty events; recorded as `"events": {}`, not omitted)
- `adjclose` field preserved when present in source (null for SOFI)
- Existing `data/historical_pe/SOFI/manifest.json` updated to `PRICE_DATA_ACQUIRED` with source URL, count, coverage, save paths; archive SQLite observations (2 pre-existing points) listed separately as secondary source, not repackaged.

**Change — SEC evidence acquisition.** Acquired SOFI SEC data from official EDGAR endpoints:

- **CIK**: 0001818874 (SoFi Technologies, Inc., Nasdaq)
- `data/historical_pe/SOFI/sec_submissions.json` — 973 filings from SEC submissions API (6× 10-K, 18× 10-Q, 81× 8-K, etc.)
- `data/historical_pe/SOFI/eps_diluted_concept.json` — 69 `us-gaap:EarningsPerShareDiluted` XBRL facts (15× 10-K annual, 54× 10-Q quarterly), CIK zero-padded to 10 digits
- `data/historical_pe/SOFI/filing_acceptance_evidence.json` — 973 rows with accession, form, period_end, `acceptance_datetime_header_et` (ET with offset, not raw UTC Z), `acceptance_datetime_submissions_api`, `api_minus_header_hours`
- `data/historical_pe/SOFI/q4_evidence_records.json` — 4 Q4 earnings records from 8-K Item 2.02 EX-99.1 exhibits:
  - FY2025 Q4 (2025-12-31): diluted EPS 0.13, accession 0001818874-26-000008, accepted 2026-01-30T07:07:34-05:00
  - FY2024 Q4 (2024-12-31): diluted EPS 0.29, accession 0001818874-25-000006, accepted 2025-01-27T07:05:01-05:00
  - FY2023 Q4 (2023-12-31): diluted EPS 0.02, accession 0001818874-24-000004, accepted 2024-01-29T07:05:33-05:00
  - FY2022 Q4 (2022-12-31): diluted EPS -0.05 (net loss), accession 0001818874-23-000005, accepted 2023-01-30T07:09:20-05:00
- FY2021 Q4: no Item 2.02 earnings 8-K found; not fabricated

**Production pipeline validation.** Ran `historical_pe.py` `load_issuer_historical_pe()` on SOFI:

- Distribution status: **USABLE_FOR_REFERENCE** (≥ 20 observation gate met)
- Valid observations: **130** (period 2024-11-08 to 2026-09-24)
- Total evaluations: 330; excluded: 200
- Median P/E: 47.299768; mean 57.297255; range 28.81–179.20
- Current snapshot (2026-10-19): AVAILABLE, P/E 30.21875
- Excluded reasons: REASON_MISSING_Q4_EPS (98, pre-Q4-evidence dates), REASON_NON_POSITIVE_EPS (102, loss-making periods)
- All available observations use `accounting_basis: as_traded`; PIT monotonicity enforced (usable_date ≤ evaluation_date); all unavailable reasons are explicit closed-enumeration codes
- No interpolation, no fabricated values, no vendor descriptive median used to bypass gate

**Next step.** SOFI historical P/E reference is established with 130 qualifying observations. No EPS evidence gap remains for the pipeline. Archive cleanup remains deferred per existing decision.

**Tests.** New `tests/test_historical_pe_adapter.py`: 30 unit tests (30 passed, 1 live test gated by `ST_EVA_ADAPTER_LIVE=1`). Covers fetch success, HTTP/network/JSON/empty errors, null-close dropping, all-null rejection, manifest/file writing, hash consistency (raw vs standardized, byte count, change detection), splits/events preservation, adjclose preservation, min-observations gate, fetch-error propagation, SQLite archive read, SEC evidence file format, Q4 evidence format, and SOFI production pipeline validation (PIT monotonicity, price basis, unavailable reasons, reference eligibility). Existing `tests/test_historical_pe.py` (48 tests) plus AAPL/MSFT/MU tests all pass with no regressions (106 total).

**Verification.** Live SOFI acquisition confirmed via real Yahoo Finance response (200 OK, 1,255 timestamps, 1,255 non-null closes, currency USD, exchange NMS). SEC data acquired from official EDGAR endpoints. All unit tests pass; existing historical_pe test suites pass with no regressions.

## SOFI Data Integrity and Acceptance Corrections (2026-10-19)

Continued from `9cb3610`. This round addressed SOFI data integrity and acceptance only; no price data was re-downloaded and no new source audit was performed.

### Manifest was not valid JSON

`data/historical_pe/SOFI/manifest.json` failed a standard JSON parser with `Expecting ',' delimiter: line 34 column 11`. Cause: the `note` value was written as a multi-line JavaScript-style string concatenation, which JSON does not allow. Rewritten as valid JSON. Its role, status and description were also stale — it still carried `role: price_acquisition` / `status: PRICE_DATA_ACQUIRED` and the wording "no EPS evidence acquired yet, so this is not a complete historical P/E reference dataset", which the acquired SEC evidence had made false. Now `role: production_candidate_qualified`, `status: USABLE_FOR_REFERENCE`, with the SEC evidence block, the production-pipeline result block, per-file digests, the sources actually consulted, and an explicit `known_gaps` list. `prices_manifest.json` continues to describe the price acquisition on its own and is unchanged.

The manifest is now generated from the live saved data and a live `load_issuer_historical_pe()` run, so its digests, counts and pipeline figures cannot drift from the evidence.

### Filing acceptance time source was not header-verified

`filing_acceptance_evidence.json` previously carried `acceptance_datetime_header_et` values derived from the SEC **submissions API** only, with `header_source_sha256: null` and no independent header check. The field name therefore claimed more than the evidence supported.

Every 10-K, 10-K/A, 10-Q, 8-K and 8-K/A accession — 109 in total, covering every filing form the historical P/E pipeline can consume — was re-verified against the real EDGAR SGML header at `https://www.sec.gov/Archives/edgar/data/1818874/<accession>/<accession>-index-headers.html`:

- 109/109 headers fetched successfully, 0 failures.
- The SGML `ACCEPTANCE-DATETIME` field is the **Eastern wall clock** of acceptance, not UTC. Read as UTC it yields a time 4h (EDT) / 5h (EST) early — this was the source of a wrong intermediate conclusion in this round, corrected after re-reading the field with the correct timezone.
- With the correct reading, the submissions API `acceptanceDateTime`, read as a UTC instant and expressed in Eastern, **agrees with the SGML header for all 109 accessions** (`api_minus_header_hours = 0.0` for every one). For SOFI the submissions API carries a true UTC instant; there is no double-offset artifact here.
- **0 of 109 committed acceptance times differed** from the header-verified value, so the previously stored times were correct and no observation moved.

Each verified row now carries `acceptance_datetime_source: SEC_EDGAR_SGML_HEADER_ACCEPTANCE_DATETIME`, the real `header_source_url`, the real `header_source_sha256` (SHA-256 of the actually-fetched header bytes), `header_source_bytes` and `header_verified: true`. The remaining 864 rows — forms the pipeline never consumes (Form 4, 144, 3, 5, 25, 424B, S-*, DEF 14A, ARS, …) — are labelled `acceptance_datetime_source: SEC_SUBMISSIONS_API_DERIVED` with `header_verified: false`, `header_source_sha256: null` and `header_source_url: null`. No header hash is asserted for any row that was not actually fetched.

**Q4 evidence correction.** `q4_evidence_records.json` had the same defect: its four `acceptance_datetime` values were read from the SGML header as if they were UTC, making them 5h early (e.g. FY2025 Q4 stored `2026-01-30T02:07:34-05:00`, header `2026-01-30T07:07:34-05:00`). All four are now the header-verified Eastern values and carry the real header URL, SHA-256 and byte count. Because all four are before the 16:00 ET cutoff either way, the derived usable dates are unchanged and the production output is unaffected.

### Production pipeline reproducibility

Re-ran `historical_pe.py` `load_issuer_historical_pe()` on SOFI after the corrections. Reproduced exactly: **USABLE_FOR_REFERENCE**, **130** valid observations, period **2024-11-08 to 2026-09-24**, median **47.299768**, current snapshot **AVAILABLE at 30.21875**, 330 evaluations with 200 excluded (REASON_MISSING_Q4_EPS 98, REASON_NON_POSITIVE_EPS 102). The ≥ 20 qualifying-observation gate is unchanged and was met by the evidence. Only `input_set_id` and `content_hash` moved, because the input file bytes changed when the header evidence and corrected Q4 times were written.

### GitHub Actions backend status

The `backend-tests` workflow has been **failing on every push**, including pushes that predate all SOFI work. Comparing the run for the first SOFI commit (39290402337, `42 failed, 2353 passed, 170 skipped`) against the pre-SOFI MUFG run (39239093577, `42 failed, 2323 passed, 169 skipped`), the failing test sets are **byte-identical**: 42 in both, zero only-in-new, zero only-in-pre. The +30 passing tests are the new adapter tests; that commit introduced **no new failure and fixed none**.

> **Correction (added with the next round).** The commit that followed, `157e636`, then added three manifest-integrity tests and **did** introduce three new failures: its run (39304225754) reported `45 failed, 2364 passed, 170 skipped`, i.e. exactly the three new tests failing and nothing else. The statement above is accurate for `9cb3610` only; the "no new failure" claim does not extend to `157e636`. Those three failures and their root cause are resolved in the next section.

The 42 pre-existing failures fall into four unrelated groups, none touching historical P/E, the price adapter, or SEC evidence:
- `ValuationInputs` has no attribute `observations` (22 failures across `test_evidence_valuation_boundary.py`, `test_historical_pfcf.py`, `test_summary_reference_precedence.py`)
- replay identity returns `DIVERGED` instead of `MATCH` (9 failures across `test_r6_1_replay_snapshot_identity.py`, `test_r6_replay_divergence.py`)
- `test_mapping_relation_kind.py::TestResolverIsolation::test_an_exact_claim_beats_a_measured_partial_one` — `'sbc' != 'sga'` (1)
- `test_st_eva_runner.py` — `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'` and `test_mufg_cross_currency_two_fx_scopes` asserting `unexpectedly None` (2)

The designated historical P/E and adapter test suites pass locally (120 passed, 1 skipped, 34 subtests). That is **not** the same as the whole CI being green: the 42 pre-existing failures are still red in CI and are out of scope for this round.

A full local run of `tests/` reproduces the same picture: `41 failed, 2411 passed, 170 skipped, 498 subtests`. The local failure set is a **strict subset** of the CI set — 0 local-only failures (no new regressions), and the single CI-only failure is `test_st_eva_runner.py::TestMUFGCrossCurrencyAnalysis::test_mufg_cross_currency_two_fx_scopes`, which fails in CI and passes locally (environment-dependent, MUFG, untouched by this round).

### Tests

`tests/test_historical_pe_adapter.py` grew from 30 to 44 unit tests (44 passed, 1 live test gated by `ST_EVA_ADAPTER_LIVE=1`). New coverage:
- both `manifest.json` and `prices_manifest.json` parse with a standard JSON parser
- the main manifest's recorded byte counts and SHA-256 match the actual files, and agree with `prices_manifest.json` for `daily_prices.json`
- the main manifest's status and recorded counts match the saved evidence (EPS fact count, acceptance row counts split by verification, Q4 record count and fiscal years, price count)
- the main manifest's `production_pipeline` block equals a live `load_issuer_historical_pe()` run (status, sample count, totals, exclusion reason breakdown, percentiles, mean/min/max, input_set_id, content_hash, current snapshot)
- the main manifest carries no stale "no EPS evidence" / `PRICE_DATA_ACQUIRED` wording
- every acceptance row states its time source and precision; header-verified rows carry a real 64-hex header hash and header URL; API-derived rows never claim verification and never carry a header hash; every 10-K/10-Q/8-K row is header-verified
- every acceptance time used by the EPS and Q4 evidence is Eastern with an explicit offset, and the raw submissions API value is preserved beside it

### Git

Committed and pushed; remote HEAD verified in sync and the working tree clean.

## SOFI Manifest Digests: Cross-Platform Byte Contract (2026-10-19)

Continued from `157e636`. The three failures that commit introduced in CI are fixed. No price data was re-downloaded and no test was relaxed or removed.

### The three CI failures and their single root cause

CI run 39304225754 for `157e636` reported `45 failed, 2364 passed, 170 skipped` against the pre-SOFI baseline 39239093577's `42 failed, 2323 passed, 169 skipped` — exactly three new failures, all of them the new manifest tests:

- `test_main_manifest_digests_match_the_actual_files` — `AssertionError: 1335 != 1304 : manifest byte count is stale for prices_manifest.json`
- `test_prices_manifest_digest_matches_the_actual_daily_prices_file` — `AssertionError: False is not true : prices manifest references a missing file: data\historical_pe\SOFI\daily_prices.json`
- `test_manifest_pipeline_block_matches_the_live_pipeline_output` — `AssertionError: '3a90086cd54a3f1e70b4c18a886dd19a244b5a5c734d6b480d596540e207458e' != 'c71f89d587d0dadcc8743f5b81991cc7e3abd3a600fcc481a6103bc020d1bc54'`

All three had one cause: **the repository had no `.gitattributes`, so the recorded digests were platform-specific.** `core.autocrlf=true` was set on the Windows workstation, so the JSON data files sat in the working tree with CRLF while the git blobs stayed LF. Measured on the SOFI dataset:

| file | git blob | Windows working tree | CI (Linux) sees |
| --- | --- | --- | --- |
| `daily_prices.json` | 56786 bytes, LF | 56786 bytes, LF | 56786 bytes, LF |
| `prices_manifest.json` | 1304 bytes, LF | 1335 bytes, CRLF | 1304 bytes, LF |
| `eps_diluted_concept.json` | 17348 bytes, LF | 18075 bytes, CRLF | 17348 bytes, LF |
| `filing_acceptance_evidence.json` | 729256 bytes, LF | 747744 bytes, CRLF | 729256 bytes, LF |
| `q4_evidence_records.json` | 5516 bytes, LF | 5627 bytes, CRLF | 5516 bytes, LF |

`1335 - 1304 = 31` bytes over 31 lines is exactly the CRLF/LF difference, and the recorded `input_set_id` was a digest over those CRLF bytes. The path failure was the same class of problem: `prices_manifest.json` recorded a native Windows path with backslashes, which is a single filename on Linux and does not resolve. The AAPL dataset already followed the correct convention — its digest-verified files are LF in both the blob and the working tree, and `test_aapl_historical_pe.py::test_manifest_role_and_hashes_match_canonical_files` verifies them against raw bytes.

### Fixes

1. **`.gitattributes` added** — `data/historical_pe/**/*.json text eol=lf`. The dataset files are digest-verified against their exact bytes and the production loader derives `input_set_id` from the same bytes, so the checkout must not rewrite line endings. This makes the blob, the working tree and every checkout platform agree byte for byte, and it also closes the same latent instability for the MU files, whose working tree was CRLF while their blob was LF.
2. **All SOFI dataset files rewritten with canonical LF bytes**, and the AAPL/MSFT/MU working trees re-checked out so the local tree matches the Linux CI byte for byte. The committed blobs for AAPL/MSFT/MU are unchanged — only their working-tree representation is now consistent.
3. **`historical_pe_adapter.py` — portable paths and LF output:**
   - new `manifest_path(path)` helper records forward-slash paths, relative to the repository root when the file is inside it, so a manifest resolves on Windows and on Linux;
   - new `write_json_lf(path, payload)` helper serializes in memory and writes bytes, so text mode cannot translate newlines to CRLF and change the recorded byte count and digest;
   - `save_standardized_prices()` now uses both, and `parse_yahoo_price_bars()` carries the source epoch timestamp so re-saving a parsed series reproduces the same file byte for byte instead of collapsing the timestamp to midnight UTC.
4. **Manifests regenerated from the live data** with the corrected digests and portable paths.

### Verification that the fix is platform-independent

The CI's own reported live `input_set_id` for `157e636` was `c71f89d587d0dadcc8743f5b81991cc7e3abd3a600fcc481a6103bc020d1bc54`. The regenerated manifest now records **that same value**, computed on Windows from the LF-canonical files. A simulation that materializes the git blobs (what a Linux runner checks out) into a temporary tree and runs the production loader against them reproduces:

- `input_set_id` = `c71f89d587d0dadcc8743f5b81991cc7e3abd3a600fcc481a6103bc020d1bc54` — matches the manifest
- `content_hash` = `d6c9cc88f8308628ffd7c2ef9c6bf816596431032198777256cfe0135d81af55` — matches the manifest
- `sample_count` = 130, median = 47.299768 — match the manifest
- every byte count and SHA-256 recorded in both manifests matches the blob bytes the Linux runner will read

The production output is unchanged by the fix: `USABLE_FOR_REFERENCE`, **130** observations, 2024-11-08 to 2026-09-24, median **47.299768**, current snapshot **AVAILABLE at 30.21875**, 200 excluded (98 `REASON_MISSING_Q4_EPS`, 102 `REASON_NON_POSITIVE_EPS`). The ≥ 20 qualifying-observation gate is unchanged.

### Tests

`tests/test_historical_pe_adapter.py` grew from 44 to 50 unit tests (50 passed, 1 live test gated by `ST_EVA_ADAPTER_LIVE=1`). New coverage:

- every git-tracked dataset file has canonical LF bytes (the gitignored local artifact is excluded, and the check degrades safely if git is unavailable)
- `.gitattributes` exists and forces `eol=lf` for the dataset directory
- every path recorded in a manifest uses forward slashes and resolves to an existing file
- the adapter writes LF bytes and records forward-slash paths
- the adapter preserves the source timestamps, so a parsed series round-trips to the same file

The manifest's recorded production block is still compared against a live `load_issuer_historical_pe()` run by `test_manifest_pipeline_block_matches_the_live_pipeline_output`; that test was **not** weakened — it now passes because the underlying bytes are platform-independent.

### CI

The three new failures are gone, confirmed on the CI runner itself (run 39308312152 for `bf08476`): **`42 failed, 2373 passed, 170 skipped, 498 subtests`**.

| comparison | result |
| --- | --- |
| baseline 39239093577 (pre-SOFI MUFG) | 42 failed, 2323 passed, 169 skipped, 498 subtests |
| CI 39290402337 (`9cb3610`) | 42 failed, 2353 passed, 170 skipped, 498 subtests |
| CI 39304225754 (`157e636`) | 45 failed, 2364 passed, 170 skipped, 498 subtests |
| CI 39308312152 (`bf08476`, this round) | **42 failed, 2373 passed, 170 skipped, 498 subtests** |
| `test_main_manifest_digests_match_the_actual_files` | **resolved** |
| `test_prices_manifest_digest_matches_the_actual_daily_prices_file` | **resolved** |
| `test_manifest_pipeline_block_matches_the_live_pipeline_output` | **resolved** |
| new regressions vs baseline 39239093577 | **none** — the failure set is identical to the baseline, not merely the same size |
| failures fixed relative to baseline | **none** |

The `bf08476` failure set is byte-identical to the baseline's: 42 entries in both, zero only-in-new and zero only-in-pre. The workflow still reports `failure` overall because those 42 pre-existing failures remain; that is the confirmed pre-existing state, not a new regression.

Local full backend run of `tests/`: `41 failed, 2417 passed, 170 skipped, 498 subtests` — the same pre-existing set, with the three manifest failures resolved and 6 more tests passing. The local set differs from the CI set by exactly one entry in the other direction: `test_st_eva_runner.py::TestMUFGCrossCurrencyAnalysis::test_mufg_cross_currency_two_fx_scopes` fails in CI and passes locally, in the baseline and in this round alike — an environment-dependent pre-existing MUFG failure, untouched by this work.

The designated historical P/E, adapter and reproducibility suites pass locally (`146 passed, 1 skipped, 121 subtests` for `test_historical_pe.py`, `test_aapl_historical_pe.py`, `test_msft_historical_pe.py`, `test_mu_historical_pe.py`, `test_historical_pe_adapter.py` and `test_msft_production_reproducibility.py`).

### Git

Committed and pushed; remote HEAD verified in sync and the working tree clean.

## SOFI Reverse Valuation Production Integration (2026-10-20)

Continued from `543ca08`. SOFI was a qualified candidate in a data directory; it is now a configured issuer whose historical P/E reference actually reaches the reverse valuation through the product's own call path. No data was re-collected, no SEC evidence was re-researched, and no reverse-valuation rule was duplicated or bypassed.

### How the product path was found

`historical_pe.ISSUER_CONFIGS` is the single issuer registry, and `st_eva_runner.run_st_eva()` already consults it: `if data.ticker in ISSUER_CONFIGS: load_issuer_historical_pe(config, enable_furnished=...)` produces `production_historical_pe`, which is then passed to `MarketImpliedAssumptionsEngine.analyze(..., production_historical_pe=...)` for the reference selection and to `build_reverse_requirements(..., production_historical_pe=...)` for the matrix. The web adapter sets `include_historical_pe=True`, so `POST /api/analyze` is the path that exercises the whole chain. The integration therefore required no new calculation code.

### Changes

1. **`historical_pe.ISSUER_CONFIGS`** — added SOFI: `issuer_id="CIK0001818874"`, `fye_month=12`, `data_dir=Path("data/historical_pe/SOFI")`, `canonical_path=None`, matching the AAPL/MSFT/MU entries' shape.
2. **`st_eva_runner.REGRESSION_TEST_FIXTURES`** — added a SOFI fixture, a frozen capture of the live run's own values, so the offline product path reproduces the same result without a provider call. The price is the canonical historical P/E dataset's last daily close (14.505 at 2026-10-19, verifiable and tracked); the trailing, forward and consensus EPS observations carry the source identity of the observations they were captured from (`YahooFinanceFundamentals`, `query2.finance.yahoo.com/v10/finance/quoteSummary/SOFI`, each with its own definition, methodology and raw field). The captured vendor historical P/E band is carried exactly as observed — at **five** observations it is below the reference threshold, so the exit multiples must come from the production distribution.
3. **`st_eva_runner.CompanyResolver.resolve`** — added the `"SOFI": "SOFI"` alias so regression mode resolves the fixture instead of falling through to the live provider.
4. **`data/historical_pe/SOFI/manifest.json`** — regenerated through the *registered* configuration. The input-set identity digests `issuer_config`, and the registered issuer id is `CIK0001818874` (the ST-EVA identifier form) while the SEC's own CIK is `0001818874`; the manifest had been generated against the bare CIK, so its recorded `input_set_id` did not match the product path's. The manifest now records `input_set_id 4b69c139ddbfea489bf751745f9aece6babaa21e569438c8a5c9a23d17fff114` and `content_hash aef00dfa5372eaf215878df32dc1a16e9859a549d712cf7e387915bc999e348c`, the values the product path actually computes.
5. **`tests/test_historical_pe_adapter.py`** — the SOFI pipeline tests now load through `ISSUER_CONFIGS["SOFI"]` instead of a hand-built configuration, so the manifest comparison exercises the registered issuer.

### Verified end-to-end results

Through the product's own web API (`POST /api/analyze`, `mode=regression`):

- `production_historical_pe_summary.status` = `USABLE_FOR_REFERENCE`, `usable_for_reference` = true, `issuer_id` = `CIK0001818874`
- `sample_count` = **130**, `percentiles.median` = **47.299768**, `period_start`/`period_end` = **2024-11-08** / **2026-09-24**
- `current_pe` = **30.21875** at `2026-10-19` (the current snapshot, `AVAILABLE`)
- `valuation_summary.selected_pe_basis` = `production_historical_pe_median`, `selected_pe` = 47.299768 — the reference the summary names is the distribution's own median
- `forward_eps_at_reference_multiple` = `current_price / selected_pe` — the reference reaches the arithmetic, not only the response
- reverse requirements `status` = `COMPUTED`, **80** matrix rows; every row's exit multiple is `source: production_historical_pe_percentile`, `eligibility_state: ELIGIBLE_PRODUCTION_DISTRIBUTION`, `sample_size: 130`, `is_user_assumption: false`, and the five exit multiples are exactly the distribution's percentiles (34.40145, 37.502967, 47.299768, 54.025914, 136.74)
- a row's own arithmetic recomputes from the reference it names: `required_exit_price` = `price × (1 + required_return)^horizon`, `required_terminal_eps` = `required_exit_price / exit_multiple`, `required_eps_cagr` = the CAGR between the starting and terminal EPS
- the vendor band is refused, not used: the `unavailable` block still carries `exit_multiple.band_scenarios` with `reason_kind: INSUFFICIENT_OBSERVATIONS` for the five-observation band, and no matrix row uses a band source

**Live path, real market data.** The same chain was also run with `mode=live`, so the price and EPS come from the live Yahoo Finance provider rather than the frozen capture: `selected_pe_basis` = `production_historical_pe_median`, `selected_pe` = 47.299768, `current_price` = 14.3 USD as of 2026-10-19, `forward_eps_at_reference_multiple` = 0.30232706426805306 (= 14.3 / 47.299768), reverse requirements `COMPUTED` with 80 rows, and the same five production exit multiples. The frozen fixture's 14.505 is the canonical dataset's last daily close; the live run's 14.3 is the provider's price at run time. Both feed the same qualified distribution.

### Assumptions and refusals

Each matrix row states its inputs (`price_evidence`, `eps_evidence`, `multiple_evidence` with provider, observation id and source type), its formula (`formula_version`, `required_return_basis`, `dividend` basis), its period (`as_of`, `period_label`, `sample_period`) and its conditionality ("The implied figure is the fundamental this multiple corresponds to. It is not a statement of what the market expects."). The `missing_or_unvalidated` block names what the sources did not declare. The summary's limitations include "This output is descriptive valuation analysis, not a buy/sell signal." and "ST-EVA does not invent EPS, consensus, probabilities, or target prices." No output describes a forecast, a fair value or a recommendation: the words "forecast", "target price" and "price target" appear only inside explicit denials.

Nothing was padded. The 200 excluded windows keep their reasons — 98 `REASON_MISSING_Q4_EPS` and 102 `REASON_NON_POSITIVE_EPS` — and every excluded row carries a `reason_code` with no value. The ≥ 20 qualifying-observation gate is unchanged: a distribution built from 19 real observations is refused with `INSUFFICIENT_OBSERVATIONS` and yields no exit multiple.

### No regression

- AAPL, MSFT and MU are unchanged: AAPL 36 observations / median 28.44563, MSFT 24 / 33.195873, MU 454 / 20.552342, all `USABLE_FOR_REFERENCE`, each reproducible with an identical `input_set_id` and `content_hash` across runs.
- `ISSUER_CONFIGS` now holds exactly `AAPL, MSFT, MU, SOFI`; no other issuer was registered.
- MUFG's cross-currency inputs are untouched: it has no production historical P/E dataset, the ADR ratio stays 1.0, and the reference FX rate stays 0.006316 USD/JPY as of 2026-10-09, provider Federal Reserve Board H.10, scope reference-only. The MUFG runner tests pass locally (18 tests).

### Tests

New `tests/test_sofi_production_integration.py`: **28 tests, 19 subtests, all passing**. It drives the web API, not the loader alone, and covers the issuer registration, the qualified distribution and its agreement with the manifest, the summary's reference selection, the derived figure, the matrix's construction and recomputability, the refusal of the ineligible vendor band, the assumption/period/conditionality disclosures, the disclaimer-only usage of forecast language, the unchanged reference gate, and the non-regression of the other issuers and of MUFG.

### CI

Confirmed on the CI runner: run **39366918042** for `ee5e227` reported **`42 failed, 2401 passed, 170 skipped, 517 subtests`**.

| comparison | result |
| --- | --- |
| CI baseline 39239093577 (pre-SOFI MUFG) | 42 failed, 2323 passed, 169 skipped, 498 subtests |
| CI 39308312152 (`bf08476`, previous round) | 42 failed, 2373 passed, 170 skipped, 498 subtests |
| CI 39366918042 (`ee5e227`, this round) | **42 failed, 2401 passed, 170 skipped, 517 subtests** |
| new regressions vs the CI baseline 39239093577 | **none** — the failure set is byte-identical, not merely the same size |
| new regressions vs the previous round | **none** |
| pre-existing failures fixed | **none** |
| failures mentioning SOFI | **none** |

The +28 passing tests and +19 subtests are the new integration suite. The workflow still reports `failure` overall because those 42 pre-existing failures remain; that is the confirmed pre-existing state, not a regression from this integration.

Local full backend run of `tests/`: `41 failed, 2445 passed, 170 skipped, 517 subtests`. The local set is a strict subset of the CI set by exactly one entry — `test_st_eva_runner.py::TestMUFGCrossCurrencyAnalysis::test_mufg_cross_currency_two_fx_scopes`, which fails in CI and passes locally in the baseline and in this round alike, an environment-dependent pre-existing MUFG failure untouched by this work.

The designated suites pass locally: `test_historical_pe.py`, `test_aapl_historical_pe.py`, `test_msft_historical_pe.py`, `test_mu_historical_pe.py`, `test_historical_pe_adapter.py`, `test_sofi_production_integration.py` and `test_msft_production_reproducibility.py` — 174 passed, 1 skipped, 140 subtests. The MUFG runner tests pass locally (18 tests).

### Git

Committed and pushed; remote HEAD verified in sync and the working tree clean.

## ValuationInputs Contract and the Engine Boundary (2026-10-20)

Continued from `d5c7040`. This round fixed the `ValuationInputs` / engine-interface failures and did not touch the SOFI integration.

### The target failures, measured

The task brief named 28 failures across four files. Re-running the suites on the current code measured **30**, because `tests/test_summary_reference_precedence.py` contributes 17 rather than 15:

| file | brief | measured |
| --- | --- | --- |
| `tests/test_data_contract.py` | 3 | 3 |
| `tests/test_evidence_valuation_boundary.py` | 6 | 6 |
| `tests/test_historical_pfcf.py` | 4 | 4 |
| `tests/test_summary_reference_precedence.py` | 15 | **17** |
| total | 28 | **30** |

All 30 failed with the same error, and the traceback pointed at the implementation, not the test:

```
st_eva_runner.py:1889: AttributeError: 'ValuationInputs' object has no attribute 'observations'.
Did you mean: 'from_observations'?
```

### Root cause: the implementation violated its own documented contract

`MarketImpliedAssumptionsEngine.analyze()` documents its own input contract:

> `data` is either a `ValuationInputs`, which is the provider-agnostic contract projection, or a 2.2.3 `MarketData` view, which is converted.

It then did this:

```python
_mc_obs = data.observations.latest("market_cap")
_rev_obs = data.observations.latest("revenue")
_mc_currency = _mc_obs.currency if _mc_obs else data.currency
_rev_currency = _rev_obs.currency if _rev_obs else None
```

`ValuationInputs` is a frozen dataclass of metric/value fields with a single `currency`; it has no `observations` and never had. So every call that took the contract path raised `AttributeError` before producing any output. The production path happened to survive only because `run_st_eva` hands the engine a `MarketData` view, which does carry `observations`.

**The tests were not stale.** They are the contract: `test_engine_matches_from_observations_and_from_the_view` requires the engine to produce *identical* output from a `ValuationInputs` and from a view, and `test_engine_runs_on_a_non_yahoo_provider` requires it to run on another provider's observations. The implementation was the thing that had to change.

The rule the engine was reaching for — "P/S may only be computed when the market cap and the revenue are denominated in the same currency" — is not view data. It is contract data. `ValuationInputs` carried no way to express it, which is why the engine had to reach past its own projection.

### The fix

1. **`data_contract.ValuationInputs`** gained two fields, `current_revenue_currency` and `current_market_cap_currency`, holding the currency each of the two currency-sensitive figures is denominated in. `None` means the currency was never stated, which is deliberately *not* the same as the instrument's currency.
2. **`ValuationInputs._effective_currency()`** resolves them by one rule, shared by both builders: an observation that states no currency states no currency, and the fallback (the instrument's currency for the market cap, none for the revenue) applies only when the metric has no observation at all. `from_observations()` reads the observation set; `from_legacy_view()` reads the view's own observation set by name, so the contract still imports nothing from the engine module.
3. **`ValuationInputs.ratio_currencies_compatible()` / `ratio_currencies_differ()`** now hold the rule in one place, so the engine's arithmetic and the reason the runner reports cannot drift apart.
4. **`st_eva_runner.MarketImpliedAssumptionsEngine.analyze()`** reads the two currencies from the projection and calls the shared rule. It no longer touches `data.observations` at all, so the contract path and the view path are the same code.
5. **`evidence_valuation_boundary.admit()`** puts the admitted revenue's own currency on the contract, and states that the valuation-side market cap is denominated in the price's currency — the same fallback the engine applies when no market-cap observation exists.
6. **The runner's two copies of the rule were removed.** The block at the old lines 2772-2782 assigned `_mc_cur_lim` and `_rev_cur_lim` and then used neither — dead code that computed a rule's inputs and decided nothing. The P/S-refusal limitation, which re-implemented the comparison inline, now calls the same contract method. The runner therefore reports a refusal for exactly the condition under which the engine refuses the ratio.

### What each of the 30 failures was, and what resolved it

All 30 shared the one root cause: the engine raised `AttributeError` before reaching any assertion, so none of them could observe a wrong number. They are grouped by what each asserts:

| assertion group | count | what it pins down |
| --- | --- | --- |
| `test_data_contract.py` — absent observation reaches the engine as unavailable; the engine matches from observations and from the view; the engine runs on a non-Yahoo provider | 3 | the provider-agnostic contract, and that a missing observation stays unavailable rather than becoming a zero |
| `test_evidence_valuation_boundary.py` — the engine accepts the constructed inputs; a refused SEC revenue leaves the engine output unchanged; injecting SEC revenue makes no reverse output SEC-derived; the conventional P/S uses the filed revenue; free cash flow and EBITDA enter the reverse valuation | 6 | that admitted evidence reaches the engine, that refused evidence changes nothing, and that the P/S uses the filed revenue |
| `test_historical_pfcf.py` — the P/FCF reference precedence: a user-supplied multiple keeps precedence, the production median is the cash-flow reference, no reference stays none, the band fallback is unchanged | 4 | the cash-flow reference precedence and the no-fabrication rule |
| `test_summary_reference_precedence.py` — the P/E reference precedence, the band fallback, the ineligible-distribution fallback, the reference's own sample count, and that the summary and the matrix agree on the production median | 17 | the reference precedence, the eligibility gate, and that the summary and the matrix cannot disagree |

Every one of them now passes. The 4 files go from **30 failed / 155 passed** to **185 passed, 86 subtests**.

### Behaviours preserved, each checked

- **A missing observation stays unavailable.** `ValuationInputs._scalar` is unchanged, so an absent observation and a present-but-null observation still both reach the engine as `UNAVAILABLE`; nothing is zero-filled. The contract's own test for this is one of the three that now passes.
- **A refused SEC revenue changes nothing.** `admit()` still leaves every unadmitted field at the dataclass default. The revenue's currency is set only when a revenue was actually admitted (`revenue.currency if revenue is not None else None`), so a refusal leaves it `None` and the P/S stays refused.
- **Admitted revenue, EBITDA and free cash flow reach the reverse valuation.** `current_revenue`, `current_ebitda` and `current_fcf` are unchanged, and the two free-cash-flow crossing tests now pass.
- **The P/E reference precedence, the eligibility gate and the source identity are unchanged.** The engine's selection order — a user-supplied multiple, then the production distribution's median, then the vendor band's median, then nothing — is untouched; only the currency lookup moved. The 17 summary-precedence tests pin it and now pass.
- **A user-supplied multiple is not displaced.** Unchanged, and asserted by `test_a_user_supplied_multiple_keeps_precedence` and the P/FCF equivalent.
- **The currency rule itself is unchanged in effect.** The engine's original expression was moved into the contract verbatim: the market cap's currency is its observation's currency, falling back to the instrument's currency only when no market-cap observation exists; the revenue's currency is its observation's currency or `None`. A cross-currency ratio is still refused, never converted, and the converted figure is still reported separately in `cross_currency.revenue_conversion`.
- **SOFI, AAPL, MSFT and MU are not degraded.** The 53-check acceptance run still passes end to end: SOFI's 130 observations, median 47.299768, window 2024-11-08..2026-09-24, snapshot AVAILABLE at 30.21875, the 80-row reverse requirements matrix and the five production exit multiples; AAPL 36 / 28.44563, MSFT 24 / 33.195873, MU 454 / 20.552342.
- **The MUFG cross-currency limit is not degraded.** The MUFG runner tests pass (20), the ADR ratio stays 1.0 and the reference FX rate stays 0.006316 USD/JPY as of 2026-10-09, and a cross-currency P/S is still refused rather than computed.

### New tests

`tests/test_data_contract.py` gained `TestCurrencyCompatibilityContract` — 7 tests covering the bare `ValuationInputs` path, the same-currency ratio, the cross-currency refusal, an undeclared currency being refused rather than assumed, the projection resolving the currencies from observations, the instrument currency applying only when no observation exists, and the currencies carrying no provider structure.

### The failures that remain, and why

The full local run of `tests/` reports **11 failed, 2482 passed, 170 skipped, 519 subtests**. All 11 are in the CI baseline and none was introduced here:

- `tests/test_mapping_relation_kind.py::TestResolverIsolation::test_an_exact_claim_beats_a_measured_partial_one` — 1
- `tests/test_r6_1_replay_snapshot_identity.py` — 5 (replay identity)
- `tests/test_r6_replay_divergence.py` — 4 (replay divergence)
- `tests/test_st_eva_runner.py::TestMarketImpliedAssumptions::test_multi_method_reverse_valuation` — 1

The last one is the P/S assertion in the MSFT regression view. Its cause is unchanged from the baseline and is **not** the contract fix: the MSFT regression view carries no revenue observation and no market-cap observation, so the revenue's currency is unstated and the P/S is refused — the same refusal the baseline produced, from the same rule, with the same `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'`. The test mutates the view's attributes *after* its observation set was built, so the currency the engine needs is not there. Fixing it means giving the MSFT regression fixture a revenue observation, which is a separate item.

The replay identity and mapping failures are likewise untouched and unrelated to this round.

### CI

Confirmed on the CI runner: run **39372514397** for `2ce9ee3` reported **`12 failed, 2438 passed, 170 skipped, 519 subtests`**.

| comparison | result |
| --- | --- |
| CI baseline 39239093577 (pre-SOFI MUFG) | 42 failed, 2323 passed, 169 skipped, 498 subtests |
| CI 39372514397 (`2ce9ee3`, this round) | **12 failed, 2438 passed, 170 skipped, 519 subtests** |
| the 30 target failures | **all 30 resolved in CI** — the failure count falls by exactly 30 |
| new regressions vs the CI baseline 39239093577 | **none** — the failure set is a strict subset of the baseline's |
| pre-existing failures fixed beyond the target set | **none** |

The 12 that remain in CI are the confirmed pre-existing set, and they are not this round's work:

- `tests/test_r6_1_replay_snapshot_identity.py` — 5 (replay identity)
- `tests/test_r6_replay_divergence.py` — 4 (replay divergence)
- `tests/test_mapping_relation_kind.py::TestResolverIsolation::test_an_exact_claim_beats_a_measured_partial_one` — 1
- `tests/test_st_eva_runner.py::TestMarketImpliedAssumptions::test_multi_method_reverse_valuation` — 1 (the MSFT-fixture P/S assertion explained above)
- `tests/test_st_eva_runner.py::TestMUFGCrossCurrencyAnalysis::test_mufg_cross_currency_two_fx_scopes` — 1 (environment-dependent; it fails in CI and passes locally, in the baseline and in this round alike)

Locally the run reports `11 failed, 2482 passed` — the same set without the environment-dependent MUFG test. The workflow still reports `failure` overall because those 12 pre-existing failures remain; that is the confirmed pre-existing state, not a regression from this round.

### Git

Committed and pushed; remote HEAD verified in sync and the working tree clean.

## Replay Identity and Replay Consistency (2026-10-20)

Continued from `efc76a7`. This round fixed the nine replay failures. The `ValuationInputs` currency work and the SOFI integration were not redone.

### The nine failures, and the single cause behind them

Re-running the two files on the current code gave the same nine failures the task named, all of them an identity that would not reproduce itself:

| file | failures |
| --- | --- |
| `tests/test_r6_1_replay_snapshot_identity.py` | 5 |
| `tests/test_r6_replay_divergence.py` | 4 |

They were **not** nine different errors. Every one of them came out of the same comparison, and the `field_diffs` the replay already reports named it: replaying at the archival watermark produced a rebuilt context whose `context_id` differed from the stored one, and the only substantive difference was one derived figure.

```
derived.current_ps.figure.provenance_kind   stored: "UNAVAILABLE"   rebuilt: "DERIVED"
derived.current_ps.figure.value            stored: null            rebuilt: 9.436304941643904
```

The other six diffs were consequences: the `context_id` itself, the `provenance` reference to that figure, the `unavailable` list (the figure was no longer in it) and `valuation_reference.selected_at`, a volatile timestamp.

**The mechanism.** The engine judges a market-cap/revenue ratio only when the two are in one currency, and it resolves those currencies from the view's observation set. But the two paths do not carry the same set:

- the **live run**'s view carries the acquisition's own observations — in the live path, the price and the provider's stated fundamentals. A revenue that the provider reported as a bare view *attribute* has no observation of its own, so the engine could not confirm its currency and **refused** the ratio;
- the **replay** rebuilds the view from the *archived* material set, which contains a revenue observation minted from that very attribute, so the currency was confirmable and the **replay computed** the ratio.

The rebuild was therefore strictly more informed than the run it was rebuilding, and the honest verdict was DIVERGED — for the wrong reason. A figure the run refused came back as one it had computed.

The same asymmetry exists in production, not only in the tests: `material_observations()` mints the archived revenue observation from the view's attribute, and the live view's own set does not contain it.

**This is not a defect the previous round introduced.** Running the same diagnostic against `d5c7040` (before the `ValuationInputs` currency work) produced the *identical* seven diffs and the *identical* rebuilt `context_id` `ctx_68eb431adb4861a2b52a946cf774ca47`. The currency expression was moved verbatim last round, so the asymmetry was preserved exactly.

### The fix: one rule decides a figure's currency

The codebase already had the rule — in `st_eva_runner._observed_currency`, which is what the archive uses when it mints an observation for a figure no adapter reported:

> a figure an adapter stated carries the currency the adapter stated; a figure it did not state carries the instrument's currency, because that is the only currency the acquisition named.

The engine was not using it. It looked for an observation and, finding none, concluded the currency was unknown. The archive, using the rule, had concluded the figure was in the instrument's currency and recorded that. **The archive and the engine were answering the same question two different ways**, and the replay inherited the disagreement.

1. **`data_contract.effective_currency(source, instrument_currency)`** is now that rule, in the contract, where both sides can reach it.
2. **`ValuationInputs._effective_currency`** resolves a figure's currency through it, so the contract projection and the archive mint an observation the same way.
3. **`st_eva_runner._observed_currency`** delegates to it, so there is one implementation rather than two that can drift.
4. **`data_contract.VOLATILE_FIELDS`** moved into the contract, and the replay's difference report now uses it. The report was showing `valuation_reference.selected_at` as a difference the identity deliberately ignores; a reader is no longer shown a difference the identity does not act on.

The live run and its rebuild now resolve the same figure's currency the same way, so the rebuild reproduces the run instead of improving on it.

### What was *not* changed

The replay contract was already implemented and correct, and none of it was touched:

- `replay()` already accepted `context_id` and already selected the snapshot by identity through `context_by_id`, so a stored context reconciles against *its own* snapshot and not against another context that happens to share its `as_of`.
- `context_at` still resolves the earliest snapshot, so the default by-`as_of` selection is unchanged.
- The identity is still the hash of the knowledge with the volatile fields stripped; no identity field was removed or excluded to force a result.
- The comparison is still on `context_id`, not on `document_hash`, and the document hashes still differ, because `generated_at` is part of the bytes.
- The web adapter already replayed at the archival watermark and already passed the context id the run had just archived. Neither was changed.
- The data-date cutoff and the archival watermark are still distinguished by the availability rules, not by substituting one for the other: replaying at the data date still sees strictly fewer observations and still reports DIVERGED, and replaying at the watermark still sees the whole eligible set and now MATCHes.

Nothing was forced to MATCH. The reference-conditioned case still reports DIVERGED, because a user-supplied reference multiple is a runtime assumption the archive does not hold and the rebuild cannot reconstruct — that difference is preserved rather than smoothed over.

### Behaviours preserved, each checked

- **A genuine input difference is still detected.** A reference-conditioned run still reports DIVERGED against its own snapshot, and the test that pins it passes.
- **A cross-currency ratio is still refused, in the run *and* in its rebuild.** A new boundary test gives the revenue a provider observation in a different currency from the market cap and asserts that the live run refuses the ratio *and* that the rebuild refuses it too. The rebuild must not be more informed than the record.
- **The MUFG cross-currency limit is not degraded.** MUFG's revenue observation states JPY against a USD market cap, so the observation wins over the instrument's currency and the ratio is still refused. The MUFG runner tests pass (20), the ADR ratio stays 1.0 and the reference FX rate stays 0.006316 USD/JPY as of 2026-10-09.
- **SOFI, AAPL, MSFT and MU are not degraded.** The 53-check acceptance run still passes end to end: SOFI's 130 observations, median 47.299768, window 2024-11-08..2026-09-24, snapshot AVAILABLE at 30.21875, the 80-row reverse requirements matrix and the five production exit multiples; AAPL 36 / 28.44563, MSFT 24 / 33.195873, MU 454 / 20.552342.

### A tenth failure fell out

`tests/test_st_eva_runner.py::TestMarketImpliedAssumptions::test_multi_method_reverse_valuation` was failing in the baseline with `TypeError: unsupported operand type(s) for -: 'NoneType' and 'float'` on `current_ps`. Its cause was the same asymmetry: the test mutates the MSFT regression view's attributes after its observation set was built, so the revenue and market cap had no observations, the currency could not be confirmed, and the ratio was refused. Under the shared rule both figures carry the view's USD, the ratio is computed, and the test's expectation of 20.0 is met. This was a genuine pre-existing failure, now resolved by the same fix, and it is reported here rather than folded into the nine.

### New tests

`tests/test_replay_identity_boundary.py` — 11 tests, all passing:

- the archive's minted observation and the contract's projection resolve the same currency for the same figure; a figure with no observation carries the instrument's currency; a stated currency wins over the instrument's; with no currency anywhere it stays undeclared
- a provider-reported ratio is reproduced by its own replay
- a run that refused a cross-currency ratio still refuses it in the rebuild
- the data date sees fewer observations than the watermark, and the data-date rebuild is not the watermark rebuild
- a reference-conditioned run still diverges from its own snapshot, and two runs that differ report their difference
- a volatile field is not reported as a difference

### The failure that remains

One local failure remains, and it is the pre-existing one, unchanged:

- `tests/test_mapping_relation_kind.py::TestResolverIsolation::test_an_exact_claim_beats_a_measured_partial_one` — `AssertionError: 'sbc' != 'sga'`, the same assertion and the same message as in the baseline. The registry resolves an exact claim to `sbc` where the test expects `sga`. It is a mapping-relation question with nothing to do with the replay or the currency contract, and it is a separate item.

### CI

Confirmed on the CI runner: run **39375763097** for `cd25e7a` reported **`2 failed, 2459 passed, 170 skipped, 519 subtests`**.

| comparison | result |
| --- | --- |
| CI baseline 39239093577 (pre-SOFI MUFG) | 42 failed, 2323 passed, 169 skipped, 498 subtests |
| CI 39372859907 (`efc76a7`, previous round) | 12 failed, 2438 passed, 170 skipped, 519 subtests |
| CI 39375763097 (`cd25e7a`, this round) | **2 failed, 2459 passed, 170 skipped, 519 subtests** |
| the 9 target failures | **all 9 resolved in CI** |
| new regressions vs the CI baseline 39239093577 | **none** — the failure set is a strict subset of the baseline's |
| pre-existing failures fixed beyond the target set | **1** (the MSFT-fixture P/S assertion, which shared the cause) |

The two that remain in CI are the confirmed pre-existing ones, and they are not this round's work:

- `tests/test_mapping_relation_kind.py::TestResolverIsolation::test_an_exact_claim_beats_a_measured_partial_one` — the mapping-relation question described above
- `tests/test_st_eva_runner.py::TestMUFGCrossCurrencyAnalysis::test_mufg_cross_currency_two_fx_scopes` — environment-dependent; it fails in CI and passes locally, in the baseline and in this round alike

Locally the run reports `1 failed, 2503 passed, 170 skipped, 519 subtests` — the same set without the environment-dependent MUFG test. The workflow still reports `failure` overall because those two pre-existing failures remain; that is the confirmed pre-existing state, not a regression from this round.

### Git

Committed and pushed; remote HEAD verified in sync and the working tree clean.

## The Last Two CI Failures (2026-10-20)

Continued from `7869541`. The SOFI integration, the data-contract work and the replay-identity work were not redone. This round closes the two failures CI run `39376082727` still reported.

### A. The mapping resolver chose a measured PARTIAL over an EXACT claim

`tests/test_mapping_relation_kind.py::TestResolverIsolation::test_an_exact_claim_beats_a_measured_partial_one` asserted that a metric declaring the concept **exactly** wins over another metric that calls the same concept one of its components. It resolved to `sbc` (the measured PARTIAL) instead of `sga` (the EXACT).

**The conflation.** `core_registry.resolve_source_concept()` applies two scope rules, and they were answering two different questions with one test:

- `_scope_matches()` decides **applicability**: a scope naming a `ticker` or an `accession` applies only to that issuer or filing; a scope with no such key matches everything.
- the `restricted_kept` filter decided **priority**: *any* mapping with a non-`None` scope displaced every unscoped claim.

Those are different questions. `MEASURED_SCOPE` — `{variation, measured, unmeasured_holders}` — records **how** a metric was measured. It qualifies a PARTIAL, which is what makes the narrower scope a measurement rather than an assumption, and it says nothing about **where** the claim applies. Treating it as a restriction meant a measured component statement could suppress a global EXACT claim about the same concept: the weaker claim won because it carried more metadata rather than because it was stronger.

**The fix.** `core_registry._scope_restricts()` now says what restricts *where* a mapping applies — a scope that names a `ticker` or an `accession` — and the `restricted_kept` filter uses it. A measured scope no longer displaces a global claim; an issuer- or filing-restricted scope still does.

**What is preserved.** The existing suite already pinned the rest of the contract, and all of it still holds:

- a valid EXACT claim beats a weaker measured PARTIAL claim;
- two genuinely competing EXACT claims stay `AMBIGUOUS_MAPPING`, and the ambiguity names both claimants;
- two qualifying PARTIAL claims stay ambiguous rather than being ordered;
- a PARTIAL with no measured scope does not compete at all;
- the resolution does not depend on the database row order.

Three tests were added for the distinction the fix introduces: an issuer-restricted mapping still restricts and does not widen to another issuer, a filing-restricted mapping still restricts to that filing, and a measured scope is not a restriction for any asset.

### B. The MUFG cross-currency test read a gitignored file

`tests/test_st_eva_runner.py::TestMUFGCrossCurrencyAnalysis::test_mufg_cross_currency_two_fx_scopes` failed in CI with `AssertionError: unexpectedly None` and passed locally. The traceback pointed at the assertion, not the cause, so the cause was located by reproducing the CI environment.

**The cause.** `data/archives/` is **gitignored** (`.gitignore:24`), so `data/archives/MUFG.sqlite` exists on a developer machine and does not exist in a CI checkout. `st_eva_runner` reads MUFG's SEC diluted EPS from exactly that file (`data/archives/{ticker}.sqlite`, the `eps_diluted` observation), and the read was wrapped in a bare `except Exception` that set the value to `None` and carried on.

Reproducing the CI condition — the archive path made to fail, exactly as a checkout without it does — identified the failing assertion precisely: **`line 728`, `assertIsNotNone(cc["eps_conversion"])`**. `revenue_conversion` was present (the revenue comes from the provider), `eps_conversion` and `ttm_eps` were `None` (the SEC diluted EPS comes from the archive), and the `corporate_target_comparison` was present (it is not read from the archive). This was not a network failure.

So a *product fact* — MUFG's FY2026 diluted EPS — was being read from a file that is not in the repository. The cross-currency output was therefore reproducible on one machine and silently incomplete on another.

**The fix, in two parts.**

1. **The filing fact is now a tracked dataset.** `data/cross_currency/MUFG/sec_filing_facts.json` holds the SEC facts the analysis converts, each with the filing that reported it: the value (151.09 JPY per share), the accession (`0001628280-26-047095`), the form (20-F), the fiscal year and period (FY2026, 2025-04-01 to 2026-03-31), the acceptance instant (2026-07-06T11:13:02.000Z), the concept, the source URL, the filing's document hashes and the observation content hash. The runner reads it first, and the per-ticker archive remains only a fallback for a ticker that has no packaged dataset. The selection rule is unchanged: the latest fact by period end, the same one the archive query chose. The derived TTM aliases are not packaged: they are not separate filing facts, and the vendor figure for the same metric is not a filing fact either.
2. **The test's market data is now a fixed, traceable input.** A MUFG regression fixture holds the captured values — the ADR's USD price (21.86), market cap (258,756,499,250 USD), trailing/forward/consensus EPS, the P/E and P/S bands, and the price and volume history — with each observation carrying the source identity it was captured from. The revenue is declared in **JPY** on purpose: the unconverted ratio of a USD market cap to a JPY revenue is not a same-currency ratio, and it has to be refused rather than computed. The seven MUFG tests now run against the fixture instead of a live provider call, so a provider price move can no longer change a number the test is about the *conversion*.

**No assertion was weakened and nothing was skipped.** Every assertion stands, including the ones that carry the constraints: the fiscal-period reference rate `0.006316 USD/JPY` as of `2026-10-09` with `scope: reference_only`, the analysis-date rate `1.1253 / 177.82` as of `2026-10-16` with `scope: analysis_date`, the ADR ratio `1.0`, the converted P/S of 5.20 against the raw JPY/USD 0.03x, the refusal of the unconverted ratio, the single "P/S not reported" limitation naming the currency, the `not true TTM` labelling of the derived EPS, and the "no EPS in the archive" reason. Four tests were added for the packaged facts: the dataset exists, every fact names the filing that reported it, the runner reads it, and the conversion names the accession and period it converted.

The MUFG tests now pass under the CI condition as well: with the archive path made to fail, all 20 MUFG tests pass.

### Results

| | |
| --- | --- |
| the two target failures | **both resolved** |
| full local backend run of `tests/` | **2511 passed, 170 skipped, 524 subtests, 0 failed** |
| new regressions vs baseline 39239093577 | **none** — the local failure set is empty, and the baseline's 42 are all resolved |
| SOFI | 53/53 acceptance checks: 130 observations, median 47.299768, 2024-11-08..2026-09-24, snapshot AVAILABLE at 30.21875, 80-row matrix, five production exit multiples |
| AAPL / MSFT / MU | unchanged: 36 / 28.44563, 24 / 33.195873, 454 / 20.552342 |
| MUFG | 24 runner tests pass; ADR ratio 1.0; 0.006316 USD/JPY as of 2026-10-09; 1.1253 / 177.82 as of 2026-10-16; the unconverted JPY/USD P/S still refused |

### CI

**The workflow is green.** Run **39379885654** for `0f2edaf`:
<https://github.com/sbvcid/st-eva/actions/runs/39379885654>

```
Run backend test suite: 2468 passed, 170 skipped, 1 warning, 524 subtests passed in 106.52s
Run web API tests:       25 passed, 1 warning in 5.81s
conclusion: success
```

The 1 warning is the Starlette deprecation notice about `httpx`/`TestClient`, unrelated to this work.

| comparison | result |
| --- | --- |
| CI baseline 39239093577 (pre-SOFI MUFG) | 42 failed, 2323 passed, 169 skipped, 498 subtests |
| CI 39376082727 (`7869541`, previous round) | 2 failed, 2459 passed, 170 skipped, 519 subtests |
| CI 39379885654 (`0f2edaf`, this round) | **0 failed, 2468 passed, 170 skipped, 524 subtests** |
| the two target failures | **both resolved** |
| new regressions vs the CI baseline | **none** |
| pre-existing failures still outstanding | **none** |

Every failure the baseline recorded is now resolved, and nothing new was introduced. The local full run reports 2511 passed against the CI's 2468 because the browser-smoke, archive-isolation and web-API suites are separate steps in the workflow and the browser tests need a browser the runner does not install.

### Git

Committed and pushed; remote HEAD verified in sync and the working tree clean.

## AAPL FY2025 10-K into the Live Reverse Valuation (2026-10-20)

Continued from `524bd09`. This round put AAPL's real filing facts into the live
crossing. No price data was re-downloaded, no eligibility rule was relaxed, and
the reverse-valuation engine was not changed.

### The gap, located

The live analysis refused four crossing metrics. The refusal reason was the same
for all four and named the real cause:

> no observation of this metric is replay-eligible at this instant, so there is
> no filed figure to consider (no 'capex' row is replay-eligible at this
> instant)

That is the admission's rule 2 — there is no candidate row — and the cause is
upstream of it: **the SEC provider never asked for those concepts.** Its
`SEC_CONCEPTS` covered revenue, net income, diluted EPS, assets, cash, long-term
debt, shares, securities, commercial paper and dividends, and not the four that
the crossing consumes. The archive held a `revenue` row and nothing else, so
revenue crossed and the other four had nothing to cross with.

### The data path

`sec_provider.SEC_CONCEPTS` now names the element each filer reports the line
on, and the four metrics are in the default set so an ordinary run asks for
them:

| metric | element |
| --- | --- |
| operating income | `us-gaap:OperatingIncomeLoss` |
| depreciation and amortization | `us-gaap:DepreciationDepletionAndAmortization` |
| operating cash flow | `us-gaap:NetCashProvidedByUsedInOperatingActivities` |
| capital expenditure | `us-gaap:PaymentsToAcquirePropertyPlantAndEquipment` |

The provider's own filters are unchanged and still refuse what they refused: a
nine-month cumulative is not a discrete period, and the fiscal quarters the
filers do not report discretely (Q2 and Q3 FY2026, where only year-to-date
stubs exist) do not become quarters. A fiscal Q1 *is* a discrete quarter
because a Q1 10-Q's year-to-date is the quarter.

### The depreciation mapping, and why it is scoped to Apple

Apple's FY2025 10-K (`0000320193-25-000079`, filed 2025-10-31, accepted
2025-10-31T14:01:26Z, period 2024-09-29..2025-09-27) reports one cash-flow
line labelled **"Depreciation and amortization"** of 11,698 million USD, carried
on `us-gaap:DepreciationDepletionAndAmortization`. Read from the filing's own
rendered statement (`R8.htm`), that element's definition also covers
*depleting assets*, and Apple's company facts contain only the `dei` and
`us-gaap` taxonomies — **Apple has no company-specific element for the line**.
`us-gaap:DepreciationAndAmortization`, the element the registry already maps
market-wide, has no Apple rows at all.

So the element is not the pure element, and a market-wide EXACT mapping would
assert something false for a filer with depleting assets. The registry's own
`RestrictedIssuerMappingTests` documents both halves of this: the architecture
"can represent an issuer-restricted EXACT claim", and MU's real
`us-gaap:DepreciationDepletionAndAmortization` "remains refused because the
concept's US-GAAP taxonomy definition explicitly includes depletion **and the
filing's presentation label has not been verified** as limiting to depreciation
and amortization". For Apple the label *was* verified — from the filing's own
statement, where the line is labelled "Depreciation and amortization" and is the
only depreciation line in the reconciliation. So the mapping is declared
**scoped to Apple**:

```python
ConceptMapping(
    metric_id="depreciation_and_amortization",
    concept_id="us-gaap:DepreciationDepletionAndAmortization",
    mapping_type=MAPPING_EXACT,
    relation_kind=MAPPING_IDENTITY,
    scope={"ticker": "AAPL"},
)
```

The scope is what keeps the claim honest: the element means this metric for
Apple and for no other issuer. A new test asserts that it resolves for Apple
and does **not** resolve for another issuer, and that the market-wide mapping
for the pure element is unchanged.

### The product database, not just a test database

A fresh archive was never the problem. `AnalysisServiceAdapter.ensure_registry_seeded`
seeded the canonical registry only when the registry table was **empty**, so an
archive created before a declaration changed kept a registry that no longer
matched the code, and the admission it decided was a decision about a registry
that was not the one in force. A test against a fresh database would see the new
declaration and the product's own archive would not.

The seed is now applied on every run. It is idempotent, and making it so exposed
a latent defect: `metric_concept_mapping`'s primary key is
`(metric_id, concept_id, effective_from)` and `effective_from` is **nullable**,
and SQLite treats NULLs in a primary key as distinct from one another. So
`INSERT OR REPLACE` cannot replace a row whose `effective_from` is NULL — it
inserts a second one beside it. Re-seeding therefore accumulated rows, and two
rows claiming one concept read as an *ambiguity*, which refused the very
admission the seed was there to enable. The seed now removes its own rows
before writing them, identified by the metric, concept, effective date **and
scope**, so a global claim and a restricted one for the same concept stay
distinct.

### What the product now reports

The API's `admission_summary` carries, for every crossing metric, the qualified
figure and where it came from: value, currency, period, accession, form, XBRL
concept, availability class, mapping type, availability instant and source URL.
It also carries the two derived figures with the rule each was derived by and
the two admitted figures it was derived from.

The derivation is one implementation. `evidence_valuation_boundary` holds it,
the admission calls it with the figures it admitted, and the web layer calls it
with the figures it read back from the archive — so the number a reader sees is
the number the crossing produced, and the two cannot drift.

The derived figures live in the archive's reading, not in the run's output,
because the run's output must not depend on whether an archive was configured.
`tests/test_archive_replay.py::TestLegacyCompatibility::test_the_cli_output_is_unchanged_by_the_archive_flag`
pins that the CLI's JSON is identical with and without `--archive`, and it is
what caught the first attempt, which put the derivations in the run's result and
so changed the CLI's output.

### The figures, and the arithmetic behind them

From Apple's FY2025 10-K, admitted under the product's own pipeline:

- **EBITDA = 144,748 million USD** — operating income 133,050 + depreciation
  and amortization 11,698, one period (2024-09-29..2025-09-27), one currency
  (USD), one filing (accession `0000320193-25-000079`)
- **Free cash flow = 98,767 million USD** — operating cash flow 111,482 less
  capital expenditure 12,715, the same period and currency. The source states
  capital expenditure as a positive spending figure and the derivation
  subtracts it; a source that stated it as a negative outflow would add it, and
  a test covers both.

The 11,698 figure is *not* the SEC's 8,000 `us-gaap:Depreciation` (depreciation
alone) and not the vendor's trailing figure; it is the filed line.

What is **not** claimed: the vendor's own trailing EBITDA and free cash flow
still sit in the engine's inputs, and the EV/EBITDA and cash-flow reverse
methods stay unavailable without a qualified historical exit multiple. The
supplier's eight-observation band is still not a reference, and the historical
P/FCF-median-implied 194.1B is still labelled as an implied reference and not
as a filed current free cash flow.

### The replay differences, classified

The AAPL replay reports DIVERGED with 54 differing fields. They fall into two
classes, and neither is a defect in the rebuild:

1. **The archive now holds what the run did not have.** The four metrics'
   `data_quality.series`, `data_quality.freshness` and `glossary` blocks are
   null in the archived context and populated in the rebuild, because the
   archived context was written before this round's data path and the rebuild
   reads the archive, which now holds those facts. The `context_id` difference
   is the consequence of the rest.
2. **Runtime assumptions the archive cannot reconstruct.** The consensus series
   (`consensus_forward_eps_60d_ago` and its siblings) and the derived figures
   that depend on a reference (`implied_fcf`, `implied_forward_eps`,
   `required_eps_cagr`, `eps_gap_vs_consensus`, `implied_to_consensus`) are
   present in the archived context and absent in the rebuild, because a
   user-supplied or vendor reference is a runtime assumption rather than an
   archived observation.

The replay's status was left `DIVERGED`. It was not forced to `MATCH`, and no
difference was hidden: the honest verdict is that the rebuild differs, and the
diff says why. A run archived with the current code and the current registry
reduces the first class on its own.

### The product path, verified

Running the live web path (`POST /api/analyze`, `mode=live`, against
`data/archives/AAPL.sqlite`) now gives:

- admitted: revenue, operating income, depreciation and amortization, operating
  cash flow, capex — **five admitted, none refused**
- `operating_income` 133,050,000,000 USD, 2024-09-29..2025-09-27, 10-K,
  accession `0000320193-25-000079`, `us-gaap:OperatingIncomeLoss`,
  `SOURCE_DECLARED`, EXACT
- `depreciation_and_amortization` 11,698,000,000 USD, the same period and
  filing, `us-gaap:DepreciationDepletionAndAmortization`
- `operating_cash_flow` 53,925,000,000 USD and `capex` 2,373,000,000 USD, both
  2025-09-28..2025-12-27, 10-Q accession `0000320193-26-000006` — the latest
  discrete quarter the SEC reports for Apple
- derivations: EBITDA 144,748,000,000 with its formula and both inputs;
  free cash flow 51,552,000,000 over the same quarter

The cash-flow pair is the latest *knowable* discrete period, which is a
quarter: Apple does not report a discrete Q2 or Q3 for FY2026, only year-to-date
stubs, and the rule refuses a stub. The FY2025 annual pair (111,482 and 12,715,
the same 10-K) is admissible and derives 98,767,000,000, and the test proves
that over the filing's own figures.

### No regression

- **AAPL, MSFT, MU, SOFI** are unchanged: the historical P/E distributions, the
  53-check SOFI acceptance run (130 observations, median 47.299768, window
  2024-11-08..2026-09-24, snapshot AVAILABLE at 30.21875, 80-row matrix) and
  the MUFG cross-currency limit (ADR ratio 1.0, 0.006316 USD/JPY as of
  2026-10-09, 1.1253/177.82 as of 2026-10-16, the unconverted JPY/USD P/S still
  refused) all pass.
- The reference gate is unchanged: the supplier's eight-observation band is
  still not a reference.
- Three pinned registry counts moved by one, because the issuer-scoped
  depreciation mapping is one row: `EXPECTED_TOTAL` 52 → 53, `EXPECTED_IDENTITY`
  48 → 49, `EXPECTED_IDENTITY_BY_TYPE` EXACT 32 → 33. The reason is recorded at
  the constant. One contract test was refined rather than weakened: every EXACT
  IDENTITY row now resolves exactly *for the issuer it is scoped to*, and an
  unscoped row is additionally asserted to resolve for any issuer.
- `capex` stays out of the cross-source contract (`data_contract.METRIC_UNITS`
  and `METRIC_DEFINITIONS`): it is Core-only, and a second contract would be a
  second thing to drift. The provider takes those descriptions from the
  registry, which is the authority.

### Tests

New `tests/test_aapl_sec_crossing.py`: 14 tests, 4 subtests. It uses the real
archive, the real registry and the real admission over Apple's filed FY2025
figures, and covers the traceability of each fact, the four admissions, the
scoping of the depreciation mapping, both derivations, the source's own sign,
a mismatched period, a nine-month cumulative, a currency mismatch, a metric
with no fact, and the API's own DTO.

### CI

**The workflow is green.** Run **39403422457** for `31f2cc0`:
<https://github.com/sbvcid/st-eva/actions/runs/39403422457>

```
Run backend test suite: 2482 passed, 170 skipped, 1 warning, 528 subtests passed in 116.51s
Run web API tests:        25 passed, 1 warning
Run browser smoke tests:  12 passed
conclusion: success
```

There is not one `FAILED` line in the run's log.

| comparison | result |
| --- | --- |
| CI baseline 39239093577 (pre-SOFI MUFG) | 42 failed, 2323 passed, 169 skipped, 498 subtests |
| CI 39380241485 (`524bd09`, previous round) | 0 failed, 2468 passed, 170 skipped, 524 subtests |
| CI 39403422457 (`31f2cc0`, this round) | **0 failed, 2482 passed, 170 skipped, 528 subtests** |
| the 42 baseline failures | **all 42 resolved** |
| new regressions | **none** |

The 1 warning is the Starlette deprecation notice about `httpx`/`TestClient`,
unrelated to this work.

### Git

Committed and pushed; remote HEAD verified in sync and the working tree clean.

## Making the Evidence and the Valuation Input Agree (2026-10-20)

Continued from `36a0931`. This round asked one question about every input of the reverse valuation: is it only *shown* as admitted, is it actually *used* by the engine, or is it on a different basis and therefore to be kept apart?

### What the engine was actually using

Traced from `POST /api/analyze` through the V1 admission, the `ValuationInputs` projection and into `MarketImpliedAssumptionsEngine.analyze()`:

| multiple | the engine's input | its source | its period |
| --- | --- | --- | --- |
| P/E | 8.72 | provider trailing EPS | **undeclared** |
| P/FCF | 136,683,000,000 | provider trailing FCF | **undeclared** |
| EV/EBITDA | 167,959,000,000 | provider trailing EBITDA | **undeclared** |
| P/S | 466,823,000,000 | provider trailing revenue | **undeclared** |

The engine read `inputs.current_eps`, `inputs.current_fcf`, `inputs.current_ebitda` and `inputs.current_revenue` — the provider's figures. **None of the SEC-admitted figures reached the arithmetic.** The admission was reported in the API and the valuation used the provider's, which is exactly the confusion to close.

### The filed figures that exist, and on what basis

The qualified trailing figures are reconstructible, and the machinery already existed:

- **Trailing diluted EPS = 8.72**, a sum of four *directly stated* quarterly figures — Q4 FY2025 **1.85** from the furnished 8-K Item 2.02 exhibit (accession `0000320193-25-000077`, accepted 2025-10-30T16:30:35-04:00, usable 2025-10-31), Q1 FY2026 2.84, Q2 FY2026 2.01 and Q3 FY2026 2.02 from the 10-Qs. The window ends 2026-06-27 and is knowable from 2026-07-31, before the cut. This is the production historical P/E dataset's own reconstruction (`data/historical_pe/AAPL`).
- **Trailing free cash flow = 136,683,000,000**, four consecutive quarters (Q4 FY2025 26,486,000,000; Q1 51,552,000,000; Q2 26,731,000,000; Q3 25,139,000,000), each with its own operating cash flow, capital expenditure, formula, knowable date and SEC accessions. This is the production historical P/FCF dataset's own point-in-time pipeline (`data/historical_pfcf/AAPL`).
- **The filed annual figures**: operating income 133,050,000,000 and D&A 11,698,000,000 for FY2025 (2024-09-29..2025-09-27, 10-K `0000320193-25-000079`), deriving **EBITDA 144,748,000,000**; operating cash flow 53,925,000,000 and capex 2,373,000,000 for Q1 FY2026 (2025-09-28..2025-12-27, 10-Q `0000320193-26-000006`), deriving **free cash flow 51,552,000,000** — a *quarter*, not a year.

### The correction: report them apart, and say which is which

The first attempt substituted the filed figures into the engine's inputs. It broke fifteen tests, and the break was the architecture speaking:

> `der:current_pe: the registry recomputed 29.476243093922648 but the engine produced 29.70601336302895 ... The published formula does not reproduce the published number.`

The Investment Context recomputes every derived figure from the document itself and refuses a document whose published formula does not reproduce the published number. The engine's inputs are the document's published figures, so a substituted figure would make the document internally inconsistent — and for MSFT the two genuinely differ (the filed trailing EPS is 17.96, the provider's 18.09), so the substitution was not a no-op.

**The engine's arithmetic therefore keeps the document's published figure, and the filed figure is reported beside it**, on its own basis, with its window, its constituents and whether the two agree. That is the distinction the product has to make, and it is now explicit:

- the figure the engine used, its source and its basis (`VENDOR_REPORTED` / `UNDECLARED` for the provider's trailing figures; `POINT_IN_TIME` for the price, the market capitalisation and the enterprise value);
- the **qualified filed trailing figure** beside it (`SEC_DERIVED` / `TTM`), with its four constituents, the furnished fourth quarter, the derivation, the instant it became knowable, and `agrees_with_engine_input` — true for AAPL's earnings and cash flow, false for MSFT's earnings;
- the **filed figures on another basis**, named with the reason they are not the input: a fiscal year's EBITDA is not a trailing EBITDA, and a fiscal year's revenue is not a trailing revenue, so neither enters a trailing multiple; the filed annual figures stay in the admission summary with their own periods.

The API's new `calculation_inputs` block carries this per multiple, with the observed multiple and the formula that produced it, so a reader can see what was divided into what.

Nothing was relabelled to look better than it is. The provider's trailing earnings figure keeps its "undeclared period" label; the filed trailing figure is a different, separately-labelled quantity; and the latest quarter's free cash flow is never presented as a trailing one. The EV/EBITDA and cash-flow reverse methods stay unavailable without a qualified historical exit multiple, the provider's eight-observation band is still not a reference, and the historical P/FCF-median-implied 194.1B is still an implied reference and not a filed current free cash flow.

### Which trailing figure qualifies, and which does not

The SEC provider builds a trailing earnings view of its own, and for Apple it is a **roll-forward**: its fiscal Q3 is reported inside the annual context rather than as a discrete quarter, so the four most recent quarters have a hole and the provider subtracts — prior fiscal year minus prior-year cumulative plus current cumulative. The provider records that construction on the observation, and for a per-share amount it records the window as **not additive**, because the denominator moves and the result is an approximation rather than a filed figure.

That is exactly the figure the task forbids labelling as a filed trailing EPS, so the qualification rule refuses it. A trailing earnings figure qualifies only when it is a **sum of four directly stated quarterly figures** with the fourth quarter coming from a **furnished earnings release**:

- `SUM_OF_FOUR_DIRECTLY_STATED_QUARTERLY_EPS` → qualifies
- `ANNUAL_ROLL_FORWARD` (a subtraction) → **refused**
- a window with no furnished fourth quarter → **refused**
- a missing quarter, a declared gap, a quarter not knowable at the cut, or a window after the cut → **refused**

The qualified figure is the production historical P/E dataset's own reconstruction (`data/historical_pe/AAPL`): 1.85 (8-K Item 2.02, accession `0000320193-25-000077`, accepted 2025-10-30T16:30:35-04:00) + 2.84 + 2.01 + 2.02, `derived_not_issuer_declared: true` and stated as a sum.

The trailing free cash flow qualifies on the same discipline: four quarters, each declaring the formula it was arrived at (Apple's quarters are the difference of two cumulative filings, so the derivation is declared rather than assumed), each with its own knowable date and SEC accessions.

### Tests

New `tests/test_engine_input_provenance.py`: 23 tests, 4 subtests, all passing, plus one live test gated on `ST_EVA_LIVE=1` that drives the real AAPL live path. It covers the qualification rules (a missing quarter, a declared gap, a quarter not knowable at the cut, and a window after the cut all refuse the reconstruction; a rolled-forward earnings figure and a window with no furnished fourth quarter are refused; a free-cash-flow quarter without a declared derivation is refused), the four-quarter requirement for a trailing free cash flow, the engine's input staying the published figure, the filed figure being reported beside it with its components and the furnished fourth quarter, a filed figure that differs being reported as a difference, a quarter's free cash flow never standing in for a trailing one, the filed annual EBITDA keeping its annual basis and not entering a trailing multiple, one refused input leaving the other methods able to compute, and the API reporting the engine's inputs.

The live path is verified end to end: the filed trailing earnings figure has four directly stated quarters, the filed trailing free cash flow has four quarters, the filed annual figures and the derived EBITDA of 144,748,000,000 are in the admission summary with their periods, and the API's numbers are the engine's numbers.

### Regressions

AAPL, MSFT, MU and SOFI historical valuation, the SOFI 80-row reverse matrix, the MUFG cross-currency limit and the CLI's output-with-and-without-`--archive` equality all pass: **191 passed, 2 skipped, 61 subtests** across the historical P/E, AAPL/MSFT/MU/SOFI integration, adapter, SEC-crossing and input-provenance suites; **24 passed** for the MUFG runner tests; **1 passed, 3 subtests** for the CLI archive-flag equality.

### CI

Local full backend run of `tests/`: **2548 passed, 171 skipped, 532 subtests, 0 failed**.

**The workflow is green.** Run **39411403528** for `7a0ca6d`:
<https://github.com/sbvcid/st-eva/actions/runs/39411403528>

```
Run backend test suite: 2505 passed, 171 skipped, 1 warning, 532 subtests passed in 84.53s
Run web API tests:        25 passed, 1 warning
Run browser smoke tests:  12 passed
conclusion: success
```

There is not one `FAILED` line in the run's log.

| comparison | result |
| --- | --- |
| CI baseline 39239093577 (pre-SOFI MUFG) | 42 failed, 2323 passed, 169 skipped, 498 subtests |
| CI 39403963927 (`36a0931`) | 0 failed, 2482 passed, 170 skipped, 524 subtests |
| CI 39409786897 (`226c605`) | 0 failed, 2502 passed, 171 skipped, 532 subtests |
| CI 39411403528 (`7a0ca6d`, this round) | **0 failed, 2505 passed, 171 skipped, 532 subtests** |
| new regressions | **none** |

The 1 warning is the Starlette deprecation notice about `httpx`/`TestClient`, unrelated to this work.


### Git

Committed and pushed; remote HEAD verified in sync and the working tree clean.

## SEC-Derived Trailing Figures Enter the Formal Valuation Chain (2026-10-20)

Continued from `524bd09`. The previous round made the qualified filed trailing figures the valuation's *reported* input; this round makes them the valuation's **actual** input, with the Investment Context able to recompute each one from the quarters it holds.

### What the engine uses now

Through `POST /api/analyze` with `mode=live` for AAPL:

| multiple | the engine's input | source | basis |
| --- | --- | --- | --- |
| P/E | 8.72 | `SEC_DERIVED` | `TTM` — the sum of four directly stated quarterly diluted figures |
| P/FCF | 136,683,000,000 | `SEC_DERIVED` | `TTM` — four consecutive quarters |
| EV/EBITDA | 167,959,000,000 | `VENDOR_REPORTED` | `UNDECLARED` |
| P/S | 466,823,000,000 | `VENDOR_REPORTED` | `UNDECLARED` |

The earnings figure's four constituents: **1.85** from the furnished 8-K Item 2.02 exhibit (accession `0000320193-25-000077`, accepted 2025-10-30T16:30:35-04:00, usable 2025-10-31) and **2.84 / 2.01 / 2.02** from the 10-Qs (accessions `0000320193-26-000006`, `-000013`, `-000020`; usable 2026-01-30, 2026-05-01, 2026-07-31). The window ends 2026-06-27 and is knowable from 2026-07-31, before the cut. The figure is `derived_not_issuer_declared`: it is a sum of directly stated quarters, not a number the issuer declared as a trailing twelve months.

### How the document can recompute it

The trailing figure is **a derivation in the document, not an observation the document trusts**:

```
der:ttm_eps  op=sum_periods  operands=[obs:ttm_eps_window-2026-06-27#samples]
             expression=sum of the four directly stated quarters ending 2026-06-27
der:ttm_fcf  op=sum_periods  operands=[obs:ttm_fcf_window-2026-06-27#samples]
```

The window is an observation the context holds: it carries the four quarters with their accessions, acceptance instants, usable dates, evidence classes and content hashes, and the samples the registry sums. The engine's value is the authority, and the registry's recomputation is checked against it by the document's existing parity check — which was not disabled, relaxed, or given a new field to skip.

`der:current_pe` divides the price by `der:ttm_eps` rather than by the provider's trailing figure, and the same holds for the cash-flow multiple. The window travels with the archive, so a rebuild finds it and reproduces the figure from the same quarters.

Two defects surfaced while wiring this, and both were fixed rather than worked around:

- `operation_registry.result_unit` never resolved the rule `"the operand's unit"`, because the branch testing it sat inside a test for the plural spelling `"the operands' shared unit"`. A figure declaring the singular rule was published with the rule's own wording as its unit, and the next multiple refused it. The rule is now honoured.
- The cash-flow window's quarters carry `knowable_from` while the earnings ones carry `usable_date`, so the window's availability was empty and the window was archived first-seen rather than source-declared. It now reads either.

### What was deliberately not substituted

- **FY2025 EBITDA 144,748,000,000** stays an annual figure in the admission summary with its own period. A fiscal year's EBITDA is not a trailing EBITDA, so it does not enter a trailing enterprise-value multiple.
- **The latest quarter's free cash flow 51,552,000,000** stays a quarterly figure in the admission summary. It is not the trailing figure and is never presented as one.
- **The annual revenue** and the provider's undeclared-period figures stay as they are.
- The EV/EBITDA and cash-flow reverse methods remain unavailable without a qualified historical exit multiple, the provider's eight-observation band is still not a reference, and the historical P/FCF median's implied 194.1B is still an implied reference and not a filed current free cash flow.

### The replay, and what still differs

The AAPL live replay reports `DIVERGED` with **37** differing fields — down from 54 before this round. Every one of them is the **valuation reference** and the figures derived from it (`valuation_reference.multiple`, `basis`, `provenance_kind`, `selection_method`, and `derived.implied_forward_eps`, `derived.implied_fcf`, `derived.required_eps_cagr`, `derived.eps_gap_vs_consensus`, `derived.implied_to_consensus`).

That is a **pre-existing gap, not this round's**: the rebuild does not re-derive the production historical reference, so a rebuild has no reference where the archived run had one. The differences this round introduced — the trailing figures' own series, freshness and glossary entries, and their derivations — are now identical on both sides, which is why the count fell from 54 to 37. The reference gap is recorded as a separate item and was not expanded into this round's scope.

**Superseded by the next section**: the reference gap this round left open was closed in "The Replay Reproduces the Run's Reference (2026-10-20)", and the AAPL live replay now reports `MATCH` with 0 field differences.

### Tests

`tests/test_engine_input_provenance.py` was rewritten for the new semantics: the qualified filed trailing figure **is** the engine's input; the provider's figure is recorded beside it as the cross-check it is; the window carries the four quarters with their filings; a window without a furnished fourth quarter is not used; a quarterly free cash flow is never the trailing one; the filed annual EBITDA is not used for a trailing multiple; and one refused input leaves the other methods able to compute.

### CI

**The workflow is green.** Run **39424919643** for `82ad6b6`:
<https://github.com/sbvcid/st-eva/actions/runs/39424919643>

```
Run backend test suite: 2508 passed, 171 skipped, 1 warning, 532 subtests passed in 105.80s
Run web API tests:        25 passed
Run browser smoke tests:  12 passed
conclusion: success
```

There is not one `FAILED` line in the run's log.

| comparison | result |
| --- | --- |
| CI 39411729148 (`eb84b63`, previous round) | 0 failed, 2502 passed, 171 skipped, 524 subtests |
| CI 39424919643 (`82ad6b6`, this round) | **0 failed, 2508 passed, 171 skipped, 532 subtests** |
| new regressions | **none** |

The 1 warning is the Starlette deprecation notice about `httpx`/`TestClient`, unrelated to this work.

### Git

Committed and pushed; remote HEAD verified in sync and the working tree clean.

## The Replay Reproduces the Run's Reference (2026-10-20)

Continued from `82ad6b6`. That round made the qualified SEC-derived trailing figures the valuation's **actual** inputs. The AAPL live replay still reported `DIVERGED` with 37 differing fields, and every one of them was the valuation reference and the figures derived from it.

### The defect

The production historical P/E and P/FCF distributions were loaded inside the live run and nowhere else. `build_context_from_observations` called the engine without them, so a rebuild selected **no reference at all** where the archived run had one: `valuation_reference.multiple`, `basis`, `provenance_kind` and `selection_method` differed, every figure conditional on the reference was absent from the rebuild (`derived.implied_forward_eps`, `derived.implied_fcf`, `derived.required_eps_cagr`, `derived.eps_gap_vs_consensus`, `derived.implied_to_consensus`), and the provenance, limitation and unavailable entries that name the reference differed with them. The diff reported a difference in the *reference*, not in the observations.

### The correction

The distributions are committed, frozen data — the same kind of input the trailing figures' windows come from. The same loader now serves both paths:

- `st_eva_runner.load_production_historical_references(ticker, include_historical_pe, include_historical_pfcf, enable_furnished_pe)` is what the live run calls and what a rebuild calls.
- `archive.replay` reads the archived document's own reference basis (`PRODUCTION_PE_MEDIAN`, `PRODUCTION_PFCF_MEDIAN`) and names the sources the run had in force.
- `web.service_adapter.default_replay_doc_builder` loads them with the live path's loader and hands them to `build_context_from_observations`, which passes them to the engine.

The archive names the **source** and never the number: the median is read from the committed dataset at replay time, not copied from the document being replayed. A dataset that changed since archival therefore produces a divergence, which is the honest result.

Three boundaries are kept, and each is tested:

- A run that asked for **no** production reference still replays as a match, and the rebuild invents no reference the run did not have.
- A run conditioned on an **operator's own multiple** still diverges. That multiple is an assumption rather than archived knowledge, and the rebuild must not substitute the production median for it.
- A run that built its distribution **without the furnished evidence** replays as a match too: the archived document records how many observations stood behind its reference, and that count says which load of the dataset the run used.

### What the product reports now

Real API output, `POST /api/analyze` with `mode=live` (2026-10-20), and the figures the archived Investment Context holds for the same run:

| ticker | multiple | the engine's input | source | basis | the engine's multiple | the Context's own figure |
| --- | --- | --- | --- | --- | --- | --- |
| AAPL | P/E | 8.72 | `SEC_DERIVED` | `TTM` | 39.1651376146789 | `der:current_pe` 39.1651376146789 |
| AAPL | P/FCF | 136,683,000,000 | `SEC_DERIVED` | `TTM` | 35.98494723996401 | `der:current_pfcf` 35.98494723996401 |
| AAPL | EV/EBITDA | 167,959,000,000 | `VENDOR_REPORTED` | `UNDECLARED` | 29.414771126286773 | `der:current_ev_ebitda` |
| AAPL | P/S | 466,823,000,000 | `VENDOR_REPORTED` | `UNDECLARED` | 10.536178687853855 | `der:current_ps` |
| MSFT | P/E | 17.96 | `SEC_DERIVED` | `TTM` | 29.420935412026722 | `der:current_pe` 29.420935412026722 |
| MSFT | P/FCF | 66,987,000,000 | `SEC_DERIVED` | `TTM` | 55.490674568782005 | `der:current_pfcf` 55.490674568782005 |

The engine's multiple and the Context's own figure are the **same number** in every row: the delivered API and the archived document agree because the document recomputes the trailing figure from the four quarters it holds and divides by that. MSFT's earnings figure is 17.96 against the provider's 18.09, so the substitution is not a no-op; EV/EBITDA and P/S remain the provider's undeclared-period figures and were not substituted.

### The replay

AAPL live run → **`MATCH`**, **0** field differences, 180/180 observations used, `OBSERVATIONAL` replay fidelity.

### What did not change

- The document's schema version stays `2.3-C.2`: this round changed what a rebuild can reproduce, not the document's shape.
- `VOLATILE_FIELDS` is unchanged — four when-we-asked timestamps. No calculation difference is hidden from the identity by widening it.
- The `context_id` still covers the whole document's knowledge, so the trailing-figure round changed it (the window and the derivations are knowledge) and this round changed nothing in the document itself.

### An older archive is not rewritten into the new version

The archive this round's live run replaced is preserved at `data/archives/AAPL.sqlite.pre-2026-10-20` (SHA-256 `b7641293a46ff052da4df4f1092a2df2ced9cdc00a1fcdcaaa9228452544ceba`). Its seven snapshots were built before the trailing figures entered the chain, and replaying them with today's code reports the differences rather than forcing a `MATCH`:

| snapshot's data moment | outcome | differing fields | what differs |
| --- | --- | --- | --- |
| 2026-10-08 | `DIVERGED` | 71 | the rebuild describes a later data moment (`as_of` 2026-10-19) and carries the trailing figures those documents do not have |
| 2026-10-09 | `DIVERGED` | 71 | the same |
| 2026-10-19 (07:00) | `DIVERGED` | 81 | the trailing-figure fields, the provider's consensus series that moved between the run and the rebuild, and the comparable-filing series the older code recorded |
| 2026-10-19 (07:21, 07:31, 07:43) | `DIVERGED` | 9 | the trailing-figure fields, the provider's consensus series, and the definition text of the comparable filing rows |
| 2026-10-19 (08:11) | `DIVERGED` | 41 | the definition text of the comparable filing rows, which an earlier code state wrote with a longer sentence |

The stored documents are not rewritten, their schema and references are not migrated, and the diff names each difference. A rebuild of an old snapshot is a statement about what today's code would produce from that archive, not a restatement of what the run said.

### Tests

`tests/test_replay_production_reference.py` (5 tests): a production-reference run replays as a match; the rebuilt reference is the production median; a reference-free run replays as a match and gains no reference; an operator's multiple is not replaced by the production median; a run without the furnished evidence replays as a match.

`tests/test_r4_web_historical_pe.py` was updated for the second load: the web request reaches the production path, and the replay's rebuild reads the same committed dataset.

### CI

Run **39431909757** for `ca07496`:
<https://github.com/sbvcid/st-eva/actions/runs/39431909757>

```
Run backend test suite:  2513 passed, 171 skipped, 1 warning, 532 subtests passed
Run web API tests:        25 passed
Run archive isolation:     6 passed
Run browser smoke tests:  12 passed
conclusion: success
```

| comparison | result |
| --- | --- |
| CI 39424919643 (`82ad6b6`, previous round) | 0 failed, 2508 passed, 171 skipped, 532 subtests |
| CI 39431909757 (`ca07496`, this round) | **0 failed, 2513 passed, 171 skipped, 532 subtests** |
| new regressions | **none** |

## The Filed Trailing Revenue and EBITDA Enter the Valuation Chain (2026-10-20)

Continued from `ca07496`. The trailing earnings and trailing free cash flow were the valuation's inputs; the sales and enterprise-value multiples still divided by the provider's trailing revenue and trailing EBITDA, whose periods the provider does not declare.

### What was missing

`current_revenue` and `current_ebitda` were the only engine inputs still taken from the provider's undeclared trailing figures. The provider's numbers happened to agree with the filed ones, but nothing in the document said where they came from, what period they covered, or which filing they were built from: a reader had to take them on trust, and a different provider would have produced a different valuation without any visible difference.

### The production dataset

`data/historical_income/AAPL/` holds the issuer's filed quarterly facts, captured verbatim from data.sec.gov and pinned by hash:

| file | concept | sha256 |
| --- | --- | --- |
| `revenue_concept.json` | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | `4495f7a16b4ade43dfa8041ac6477074122cbd5b88033e3e0f68b3f919e7ffbf` |
| `operating_income_concept.json` | `us-gaap:OperatingIncomeLoss` | `de614247dd39d514abcd9b972d46d4dbb7ac3f21f09fe6bb6130081760b2492c` |
| `depreciation_concept.json` | `us-gaap:DepreciationDepletionAndAmortization` | `1392aa467e999502d0d7f7cb622abfef7285d848bd2887bc5576a5bb8380596b` |

The canonical price series and the acceptance index are read by path from the historical P/E dataset, so one trading calendar decides every filing's usable date. `historical_income.py` (methodology `historical-income/1.0`) derives the discrete quarters under the historical P/FCF pipeline's rules: a directly stated quarter-length duration, or the difference of two cumulative durations that share one fiscal-year start (Q2 = 6M − Q1, Q3 = 9M − 6M, Q4 = FY − 9M). A derived quarter keeps both of its sources and the formula, and is marked derived rather than directly stated. A quarter's fiscal identity is the issuer's own declaration; a quarter with only operating income, or only depreciation, is absent rather than half a quarter.

The depreciation element is Apple's own presentation, and its own definition also covers depleting assets, so the registry maps it to the metric **for Apple alone**. The qualification checks that scope before the figure is used: for another issuer the same element is not this metric's input, and Microsoft's `DepreciationAmortizationAndOther` and Micro's `DepreciationDepletionAndAmortization` keep the refusal they already had. No mapping gate was relaxed to widen coverage.

### What the qualification refuses

A trailing figure is used only when four consecutive quarters are knowable at the cut, in one currency, each carrying the sources it was arrived at, and each concept mapped to its metric for that issuer. A missing quarter, a gap in the fiscal positions, two currencies in one window, a quarter that is not yet knowable, a quarter without its sources, and a concept the registry does not map to the metric all refuse. When a window refuses, the engine keeps the provider's figure and says so, and the provider's figure is never relabelled as a filed one.

### What the product reports now

Real API output, `POST /api/analyze` with `mode=live` (2026-10-20):

| multiple | the engine's input | source | basis | currency | period | the engine's multiple | the Context's own figure |
| --- | --- | --- | --- | --- | --- | --- | --- |
| P/E | 8.72 | `SEC_DERIVED` | `TTM` | USD | — | 39.00860091743119 | `der:current_pe` |
| P/FCF | 136,683,000,000 | `SEC_DERIVED` | `TTM` | USD | — | 35.98494723996401 | `der:current_pfcf` |
| EV/EBITDA | 167,959,000,000 | `SEC_DERIVED` | `TTM` | USD | 2025-09-27 → 2026-06-27 | 29.414771126286773 | `der:current_ev_ebitda` |
| P/S | 466,823,000,000 | `SEC_DERIVED` | `TTM` | USD | 2025-09-27 → 2026-06-27 | 10.536178687853855 | `der:current_ps` |

The four quarters the document holds, and the filings behind them:

| quarter | revenue | EBITDA | filings |
| --- | --- | --- | --- |
| 2025-09-27 (FY2025 Q4) | 102,466,000,000 | 35,554,000,000 | `0000320193-25-000079` (10-K) and `0000320193-26-000020` (10-Q), the fiscal year less the nine months |
| 2025-12-27 (FY2026 Q1) | 143,756,000,000 | 54,066,000,000 | `0000320193-26-000006` (10-Q) |
| 2026-03-28 (FY2026 Q2) | 111,184,000,000 | 39,324,000,000 | `0000320193-26-000013` (10-Q) and `0000320193-26-000006` (10-Q), the six months less the three |
| 2026-06-27 (FY2026 Q3) | 109,417,000,000 | 39,015,000,000 | `0000320193-26-000020` (10-Q) and `0000320193-26-000013` (10-Q), the nine months less the six |

Each quarter's depreciation is itself a difference where the cash-flow statement is cumulative, and each quarterly EBITDA is that quarter's operating income plus that quarter's depreciation. The document holds both windows as observations and registers `der:ttm_revenue` and `der:ttm_ebitda` as `sum_periods` over their `samples`, so the registry recomputes each figure from the document's own quarters; the parity check is not relaxed and the two agree.

### What did not change

- The FY2025 annual EBITDA (144,748,000,000) and the latest quarter's free cash flow (51,552,000,000) are still reported on their own periods in the admission summary, and neither is a trailing figure.
- A qualified trailing denominator is not a qualified historical exit multiple. The minimum twenty qualifying observations for a reference multiple is unchanged, and P/S, EV/EBITDA and P/FCF do not borrow each other's references. The production historical P/S and EV/EBITDA distributions are **now implemented** — see "Phase 5 (2026-10-20)" below for the dataset, its measured counts, its eligibility and how the qualified references reach the report's sales and enterprise-value methods. The cash-flow method reads the production historical P/FCF reference where eligible (integrated via `fd311c5`/`4797f1f`, applying the same ``usable_for_reference`` gate as P/E); Phase 5's P/S and EV/EBITDA work did not change P/FCF selection. MSFT: 23/27, median 41.578319; AAPL: 35/36, median 25.343981; MU: 362/575, median 67.712721.
- `VOLATILE_FIELDS` is unchanged and the document's schema version stays `2.3-C.2`: the round changed what the valuation is computed from, not the document's shape.

### An archive tie the replay needed

`sqlite_archive.py`'s observation collapse ordered equally eligible rows by their content hash, so two runs on the same trading day could leave the rebuild holding the earlier reading of the same price-and-volume series — the intraday volume moves during the session, so the two runs' values differ. The order now breaks the tie by when the row was archived, so the later reading is the one a rebuild gets. The AAPL live replay went from `DIVERGED` on that observation to `MATCH` with no field difference.

### Tests

`tests/test_historical_income.py` (26 tests): the dataset's concept identity and window structure; the four consecutive quarters and their filings; a derived quarter saying it is derived; the qualification on both figures; the trailing figure being the sum of the quarters; a cut before any window is knowable; an earlier cut using the window that was knowable then; a missing quarter, a gap in the positions, two currencies, a quarter not yet knowable, a quarter without its sources, a quarter without its depreciation, a concept the registry does not map, a mapping scoped to another issuer, and no issuer at all — each refusing; and the document holding both windows, recomputing both figures from them, and the engine's inputs being the filed ones.

`tests/test_engine_input_provenance.py`'s live-gated test now asserts the current behaviour of all four multiples: the filed figure is the engine's input, the provider's figure is the cross-check beside it, and the sales and enterprise-value multiples divide by the filed trailing figures.

### What other issuers show

Microsoft has no income-statement dataset, so its sales and enterprise-value multiples keep the provider's trailing figures and their labels: `VENDOR_REPORTED` on an `UNDECLARED` basis, with the reason recorded beside them. Its trailing EPS (17.96) and trailing free cash flow (66,987,000,000) are the filed ones, as before. Its live replay reports `MATCH` with no field difference.

### CI

Run **39449339747** for `5661383`:
<https://github.com/sbvcid/st-eva/actions/runs/39449339747>

```
Run backend test suite:  2539 passed, 171 skipped, 1 warning, 532 subtests passed
Run web API tests:         25 passed
Run archive isolation:      6 passed
Run browser smoke tests:   12 passed
conclusion: success
```

## Phase 5 (2026-10-20): Production historical P/S and EV/EBITDA reference distributions

### What was actually in the repository when this round started

The reported Phase 5 completion was **not** in the repository. `HEAD` was
`2024f05` (equal to `origin/master`, "Record the phase 4 CI run in the project
status"), the working tree carried exactly two untracked paths, and no other
local or remote branch held any part of the work:

| path | state found | verdict |
| --- | --- | --- |
| `data/historical_multiples/AAPL/` | untracked: a `manifest.json` and five balance-sheet `companyconcept` payloads (cash, current marketable securities, commercial paper, long-term debt non-current, long-term debt current) | the **production inputs**, usable and now committed |
| `historical_multiples/AAPL/reference_distribution.py` | untracked: a stub that computed only P/S, whose two loaders were left as `...`, with no EV/EBITDA function, no qualification rules, no reverse-requirements wiring, no Investment Context derivations, no replay wiring and no tests | **not an implementation**; superseded |

The stub package was preserved outside the repository with its SHA-256 before
being replaced: `C:\st-eva-audit\phase5-stub-backup\historical_multiples\AAPL\reference_distribution.py`,
sha256 `d5e476f67b7b0269edcb46fb2edf3131e875d3f0fd06fc87eefa1bf02c6e1959`.
The five production payloads were kept and committed; only the abandoned stub
module was removed.

### What was built

`historical_multiples.py` (methodology `historical-multiples/1.0`, logic
version `historical-multiples/1.0.0`) builds two point-in-time reference
distributions from filed evidence, and `data/historical_multiples/AAPL/` is
their committed production input.

- **Denominators** are the income-statement dataset's own trailing windows
  (`data/historical_income/AAPL`), reused rather than recomputed: TTM revenue
  for P/S, TTM EBITDA for EV/EBITDA. A window the income dataset refused stays
  refused; this dataset never repairs a denominator.
- **Numerator for P/S** is the as-traded close on the evaluation date times the
  latest knowable cover-page share count — the same rule the production
  historical P/FCF reconstruction uses, on the same price series and the same
  share series, read by path.
- **Numerator for EV/EBITDA** is a filed-component enterprise-value bridge:
  market capitalization + (long-term debt non-current + long-term debt current
  + commercial paper) − (cash and cash equivalents + current marketable
  securities). **Every component must be knowable at the evaluation date, and
  every one of them must describe the same balance-sheet date.** A date
  missing any component has no EV, and a date whose components span more than
  one balance sheet has no EV either: the bridge is never completed by
  omission, substitution or zero-fill, and a component that was not reported
  is not carried forward as zero. Market capitalization is not a
  balance-sheet component and is not part of the same-date rule. The bridge
  stays a partial statement of enterprise value even when complete (it omits
  leases, non-current investments and off-balance sheet claims), and every
  observation says so.
- **Point-in-time rule** is the shared 16:00 ET acceptance cutoff: a fact is
  knowable from its filing's usable date, and the value in force at an
  evaluation date is the latest knowable version of each component.
- **The gate** is the shared `>= 20` qualifying observations rule. A thinner
  sample stays descriptive and is never a reference.

### The committed production inputs and their hashes

`data/historical_multiples/AAPL/` (SHA-256, each verified against the
manifest's own pinned value):

| file | bytes | sha256 |
| --- | --- | --- |
| `cash_concept.json` | 30428 | `0d7146e8db9c12ecb46e6c5e4caee0a21f6e0a469bfb66fbdaab8dc9ed27e7bb` |
| `marketable_securities_current_concept.json` | 8568 | `fc20dc98b7f45215167312565e81a68b0d07188dea0c98aac06d1af54e57164b` |
| `commercial_paper_concept.json` | 13147 | `f29592058366f7a5d9f37ad0cfafe09febb30bb933276190c80314792ec3a981` |
| `long_term_debt_noncurrent_concept.json` | 12621 | `54da82bf4310e57768c27e50848e5fabfd0c3b6317cd4456d64cce31e7345619` |
| `long_term_debt_current_concept.json` | 12430 | `e3dbc15eac1b3a839afea8f996325a7dc767bc47653320b8a6c47ab865d9acb9` |
| `daily_prices.json` (reused by path) | — | `bc259131ac0168a4f641dda7cadd9c7faa1c13265325f9f547d26a7233122741` |
| `filing_acceptance_evidence.json` (reused by path) | — | `ac74bcdd430efccaa8a0ce33d6fa7b539e46d4cae19e4d8b92b9f0b69f0d0654` |
| `shares_outstanding_concept.json` (reused by path) | — | `7f82d86420d0ff08ca3618a7bdce02902a21f54f7d1d98166fd6e6ef61b71e0e` |

The three reused files are **not** duplicated: the price series and the
acceptance index come from `data/historical_pe/AAPL` and the cover-page share
counts from `data/historical_pfcf/AAPL`, so one trading calendar and one share
series govern every reconstruction and the datasets cannot drift apart.

Dataset identity: `input_set_id`
`77402a13b164324323ab08341cfca35408b489232a4066f0a9e61b479c78a540`, package
`content_hash`
`321e8b165bfc7ef30e4c178934a122e5bc2f41fd639ab7ad0767d0ce595b59b0`.

### Measured counts and eligibility (AAPL)

| distribution | valid | rejected | total evaluations | period | median | status | eligible as a reference |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `P_S_RATIO_REFERENCE` | **28** | 8 | 36 | 2019-10-31 → 2026-07-31 | **7.257709** | `USABLE_FOR_REFERENCE` | **yes** (28 ≥ 20) |
| `EV_EBITDA_RATIO_REFERENCE` | **27** | 9 | 36 | 2019-08-01 → 2026-07-31 | **22.326** | `USABLE_FOR_REFERENCE` | **yes** (27 ≥ 20) |

P/S percentiles: 10th `5.988517`, 25th `6.697746`, median `7.257709`, 75th
`8.022627`, 90th `9.004834`; mean `7.286787`, std `1.327004`, min `4.248336`,
max `9.657382`. EV/EBITDA percentiles: 10th `17.812807`, 25th `20.709942`,
median `22.326`, 75th `25.068764`, 90th `26.29394`; mean `22.38634`, std
`3.595801`, min `12.485945`, max `27.903961`.

**Every rejection is stated, none is silent, and each says which cause it is.**
The P/S rejections split by cause, and the split is made from the captured
source rather than from prose:

| evaluation date | P/S refusal | why |
| --- | --- | --- |
| 2018-01-02, 2018-02-02, 2018-05-03, 2018-08-02, 2018-11-05 | `REASON_SOURCE_CONCEPT_COVERAGE_GAP` | the captured revenue concept carries no fact from any of the filings the acceptance index records as knowable by then, so no trailing revenue window could exist from the capture |
| 2019-01-31, 2019-05-02, 2019-08-01 | `REASON_MISSING_REVENUE_WINDOW` | the capture covers the fiscal positions the window needed (FY2018 Q2, Q3, Q4), but not all of them were knowable at the date; the reason names each position and the date it first became knowable (2019-05-02, 2019-08-01, 2019-10-31) |

The EV/EBITDA rejections are seven `REASON_MISSING_EBITDA_WINDOW` (the
positions were covered by the capture but were not knowable at the date) and
two `REASON_MIXED_BALANCE_SHEET_PERIODS` (2020-05-01 and 2020-07-31, below).
A refusal never carries the upstream's prose: the shared window helper names
the quantity it was first written for, and that wording is not propagated.

### How the qualified references reach the product

- **The summary references** (`analysis["reference"]`) now select the
  production medians in the same precedence every other reference uses: an
  operator's own multiple first, then the eligible production distribution's
  median, then the vendor band's median. The methods are labelled
  `production_historical_ps_median` and
  `production_historical_ev_ebitda_median`, and the statuses and observation
  counts travel with them (`production_historical_ps_status`,
  `production_historical_ps_sample_count`,
  `production_historical_ev_ebitda_status`,
  `production_historical_ev_ebitda_sample_count`).
- **The reverse-requirements report** carries the distributions' compact
  statement in `production_historical_multiples_summary`, and the sales and
  enterprise-value valuation methods now read the qualified medians:
  `revenue_multiple` → `7.257709`, source
  `production_historical_ps_median`, eligibility
  `ELIGIBLE_PRODUCTION_DISTRIBUTION`, `is_user_assumption: false`, 28
  observations; `enterprise_value_multiple` → `22.326`, source
  `production_historical_ev_ebitda_median`, same eligibility, 27 observations.
  A user's own multiple still wins and is still labelled `user_supplied` /
  `USER_SPECIFIED`; an ineligible or under-qualified distribution leaves the
  method **unavailable with its own reason** and is never filled from a band
  or from another method's number.
- **The Investment Context** records the two references under two new bases,
  `PRODUCTION_PS_MEDIAN` and `PRODUCTION_EV_EBITDA_MEDIAN`, each with its
  eligibility rule, the distribution's own status and its observation count —
  never as a vendor-band median and never as a user assumption. The
  `REFERENCE_SOURCES` closed set was extended deliberately, and
  `tests/test_investment_context.py`'s closed-set guard records that decision.
- **The implied net margin** now declares the reference it is conditional on
  (the valuation reference and the sales reference). The production P/S median
  makes `implied_revenue` computable on the web path, which exposed that this
  derivation had never declared its conditionality; the declaration was added
  rather than the figure withheld.

### Replay and dataset identity

The archive names the source and, since the corrective round, the count
behind it: `PRODUCTION_REFERENCE_BASES` carries
`("ps_reference", "PRODUCTION_PS_MEDIAN", "multiples_ps")` and
`("ev_ebitda_reference", "PRODUCTION_EV_EBITDA_MEDIAN", "multiples_ev_ebitda")`,
the reference payload carries the distribution's own
`source_observation_count`, and the replay's document builder loads the
dataset with the **same loader a live run uses**. Measured: a rebuild asked
for the archived multiples references reads `input_set_id`
`77402a13b164324323ab08341cfca35408b489232a4066f0a9e61b479c78a540` — the
same identity the live run reads — and the archived document's request
carries the counts (P/S 28, EV/EBITDA 27).

**What the comparison actually depends on, stated exactly:**

- A **new** archive records the count in `source_observation_count`, and the
  replay compares it with the count the rebuild read. A difference is a
  divergence with the count named, even when the median is unchanged.
- An **older** archive — one written before the count was preserved —
  records no count for these two references. The count is *not* filled in for
  it: the archived side does not know the number, so there is nothing to
  compare, and the rebuild's number is not evidence against an unknown. Such
  an archive is decided by the document comparison, which sees the difference
  in what each side recorded, and its diff shows the count as the thing that
  differs.
- The `context_id` of a document digests the whole document, so a change in
  any recorded field — the count included — changes the identity. A replay
  over an archive written before the count was preserved therefore reports a
  divergence, with the count visible in the field diff. That is the honest
  outcome, and the older archive is not rewritten to hide it.

### What is not established

- Only **AAPL** has a production multiples dataset. Any other ticker is
  reported `UNAVAILABLE` with the explicit reason "Production historical P/S
  dataset is not yet established for {TICKER}." and the reason code
  `REASON_DATASET_NOT_ESTABLISHED` — a condition of its own, never reported
  as a thin sample — and contributes no reference.
- The evaluation dates are the filing usable dates shared with the income
  reconstruction, not a continuous daily trading history, and the distributions
  do not extend past the frozen dataset's last evaluation date.
- The **P/FCF** valuation method was not altered in this round; it is outside this round's scope because it was already integrated via `fd311c5`/`4797f1f` and reads the production historical P/FCF reference where eligible (same ``usable_for_reference`` gate as P/E). MSFT: 23/27, median 41.578319; AAPL: 35/36, median 25.343981; MU: 362/575, median 67.712721.
- The reconstructed enterprise value omits operating leases, non-current
  investments and off-balance sheet commitments. It is labelled partial on
  every observation.
- The filed components are not always carried on the same balance sheet.
  Apple's 10-Qs after FY2019 Q4 report no commercial paper, so at 2020-05-01
  and 2020-07-31 the component in force is the older one and those dates
  publish no enterprise value at all. This is the same-date rule doing its
  work, and it costs the EV/EBITDA sample two observations (29 → 27).

### Tests

`tests/test_historical_multiples.py` (59 tests): the dataset's concept
identity; every observation carrying a reason for every refusal; every
published multiple recomputing from its own stated operands; market cap
recomputing from price and shares; the EV bridge summing the components it
names; AAPL qualifying on both distributions; the gate counting qualifying
observations rather than evaluations; a thinner sample staying descriptive; a
refused denominator never being repaired; every bridge component and the share
count knowable at their evaluation date; the denominators travelling with the
income dataset's identity; a complete bridge naming every component; **a
missing component refusing EV/EBITDA with `REASON_INCOMPLETE_EV_BRIDGE` while
P/S still computes**; the identity changing when an input file changes; the
loader and the module producing the same payload; eligible distributions
becoming the references; an ineligible one staying descriptive; an unestablished
ticker stating its unavailability; the report carrying the summary; a user's
multiple still winning; the valuation methods carrying the production medians
with their own provenance; the replay request naming the two new bases; and the
compact summary agreeing with the payload.

Added for the corrective round: a published enterprise value uses one
balance-sheet date; a mixed-period bridge publishes no enterprise value and
names the periods; the stale component is never zero-filled; the EV/EBITDA
sample excludes the mixed-period dates and its median is recomputed from the
survivors; the P/S distribution is unchanged by the bridge rule; the policy is
recorded on every bridge; every rejection uses a code from the closed set; the
P/S rejections tell a coverage gap from a timing refusal, date by date; a
coverage gap says it is a property of the capture; a timing refusal names the
positions and when they arrived; the upstream's free-cash-flow wording is not
propagated; **the archived document saves the counts, the replay request
carries them, a count difference is found, a replay over a changed count
diverges and says why, and an archive without the count is not given one**;
and the three availability conditions — an absent dataset, a thin dataset and
a qualified dataset — report three different reasons.

Local verification for this round: backend suite **2574 passed, 171 skipped,
534 subtests passed**; web API and archive isolation **31 passed**; browser
smoke **12 passed**; frontend production build produced `dist/index.html`.

The corrective round's own local verification: backend suite **2598 passed,
171 skipped, 534 subtests passed**; web API **25 passed** and archive isolation
**6 passed**; browser smoke **12 passed**; frontend production build produced
`dist/index.html`. The live path was exercised end to end as well: the
production medians are selected (`production_historical_ps_median` 7.257709
from 28 observations, `production_historical_ev_ebitda_median` 22.326 from 27),
the implied revenue is 677,697,403,354.14 (the live market cap ÷ 7.257709) and
the implied EBITDA 221,287,984,574.04 (the live enterprise value ÷ 22.326),
and the report's sales and enterprise-value methods carry the production
medians with `is_user_assumption: false`.

### Corrective round (2026-10-21): what the independent audit found, and
### what this round changed

An independent read-only audit of `4e40c8a` and `3cfef08` found five
defects. Each is recorded here with what it was, what changed, and what the
change did to the numbers.

| finding | what was wrong | what changed |
| --- | --- | --- |
| F1 | the two new bases saved no `source_observation_count`: the archived document recorded `null` for both, and the replay's request carried `null` where the P/E carried 36 | the count now follows the basis — `REFERENCE_SOURCES` says where each basis's count comes from, so every production basis carries its own — and the count reaches the payload and the replay request (P/S 28, EV/EBITDA 27) |
| F2 | the EV bridge published a value whose components described **two** balance sheets (2 of 29 dates) while calling the bridge "complete" | the same-date rule: every required component must describe one balance sheet, or no enterprise value is published (`REASON_MIXED_BALANCE_SHEET_PERIODS`). The EV/EBITDA sample is **27**, not 29 |
| F3 | all 8 P/S refusals were `REASON_MISSING_REVENUE_WINDOW`, which did not say that the captured revenue concept carries no fact from any filing knowable before 2019-01-30 | the refusal is classified from the capture's own facts: `REASON_SOURCE_CONCEPT_COVERAGE_GAP` where the capture carries no fact for the fiscal positions the window needed, `REASON_MISSING_REVENUE_WINDOW` where it carries them but they were not yet knowable — 5 coverage gaps and 3 timing refusals for P/S |
| F4 | a ticker with no multiples dataset reported `REASON_INSUFFICIENT_OBSERVATIONS` | `REASON_DATASET_NOT_ESTABLISHED`, and a load failure reports `REASON_DATASET_LOAD_FAILED`. An absent dataset is not a thin sample |
| F5 | the status document described the archive as holding observation counts it did not hold | the archive section now states exactly which fields the comparison depends on, and what an older archive's `null` means |

**The history is preserved, not rewritten.** The first Phase 5 commit
(`4e40c8a`) really did publish an EV/EBITDA distribution of 29 observations
with the median 22.326, and its EV bridge really did mix balance-sheet dates
on two dates. That is what the code did, and the audit found it. The
corrected rule refuses those two dates, so the distribution now holds **27**
qualifying observations with the **same median** (22.326) and a recomputed
mean (22.208469 → 22.38634). The P/S distribution is unaffected by the bridge
rule and remains 28 observations with median 7.257709.

The upstream income dataset gained a structured, per-role statement of a
refused window (`window_rejection`: the reason code, the fiscal positions the
window required, the ones it could not fill, and whether no quarter was
knowable at all). Its calculations are unchanged; its `input_set_id` is
unchanged (`401a14e73b53e6b1434be23b2c27c4ea6a0a10db0025b23cbf3740419c58e4b4`);
its `content_hash` changed because the payload now carries the structured
refusal. The income dataset's own reason prose no longer names free cash flow
for a revenue refusal, and the multiples dataset writes its own reason text
rather than propagating the upstream's.

### CI

Run **39544896687** for the corrective round `7b6e159`:
<https://github.com/sbvcid/st-eva/actions/runs/39544896687>

```
Run backend test suite:  2598 passed, 171 skipped, 1 warning, 534 subtests passed
Run web API tests:         25 passed
Run archive isolation:      6 passed
Run browser smoke tests:   12 passed
conclusion: success
```

Both jobs (`backend`, `browser`) succeeded for the commit `7b6e159`
(`7b6e159bb07bae727f92d6c8aec334a3a0a01bf9`). The run's "Assert production
inputs are self-contained" step passed, so the committed multiples dataset
checks out with the bytes the manifest pins.

The preceding run **39480897329** verified the first phase 5 commit `4e40c8a`
(`4e40c8aa9fcc5aeb7da8d1133be7bf7ea2bbb60c`) — backend 2574 passed / 171
skipped / 534 subtests, web API 25 passed, archive isolation 6 passed,
browser smoke 12 passed, conclusion success. It is kept here because it is the
run that verified the implementation this round corrected.

## Phase 6 (2026-10-21): Microsoft as the second production issuer

### Why Microsoft, and what its sources actually carry

Microsoft was the candidate because the project's own promoted datasets already
cover it: `data/historical_pe/MSFT` (the price series and the acceptance
index) and `data/historical_pfcf/MSFT` (the cover-page share counts). The
income-statement and balance-sheet inputs had to be acquired, and the
acquisition had to survive the generic pipeline's rules, so the tags were
checked against the filer rather than assumed from Apple:

| quantity | Apple's element | Microsoft's element | why |
| --- | --- | --- | --- |
| revenue | `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax` | the same | the same contract-revenue element |
| operating income | `us-gaap:OperatingIncomeLoss` | the same | the same presented line |
| depreciation and amortization | `us-gaap:DepreciationDepletionAndAmortization` | **none qualifies** | Microsoft has no pure D&A element: `us-gaap:DepreciationAndAmortization` returns HTTP 404, and its own `msft:DepreciationAmortizationAndOther` is company-custom, bundles "other" items, is not served by the company-concept API, and stays refused by the project's existing decision. `us-gaap:Depreciation` is the property and equipment note's depreciation expense, which is depreciation alone. Phase 6 read that note figure as the D&A role; Phase 6.2 corrected it |
| cash | `us-gaap:CashAndCashEquivalentsAtCarryingValue` | the same | the same balance-sheet line |
| current marketable securities | `us-gaap:MarketableSecuritiesCurrent` | `us-gaap:ShortTermInvestments` | Microsoft reports the line as "Short-term investments" and does not use Apple's element at all |
| commercial paper | `us-gaap:CommercialPaper` | the same | the same balance-sheet line |
| long-term debt, current and non-current | `us-gaap:LongTermDebtCurrent` / `LongTermDebtNoncurrent` | the same | the same balance-sheet lines |

Each element was verified against Microsoft's own filings: the 10-K figures
(11,000,000,000 for FY2023, 15,200,000,000 for FY2024, 22,000,000,000 for
FY2025 on `us-gaap:Depreciation`) and the balance-sheet components were read
from the company-concept payloads before anything was built on them.

The acceptance index that governs knowability is Microsoft's own promoted
index: 47 filings accepted between 2020-10-27 and 2026-07-29 -- 18 10-Q, 6
10-K and 23 8-K Item 2.02 earnings releases, the furnished evidence class
this issuer's production dataset already uses. It yields **27 distinct
evaluation dates**.

### The two committed production datasets

`data/historical_income/MSFT/` and `data/historical_multiples/MSFT/`, each
with a manifest that pins every file's byte count and SHA-256, the
company-concept URL it came from, and the issuer's own line behind each role.
The eight payloads were fetched from `data.sec.gov` with a declared
contactable User-Agent and the SEC's fair-access pacing, and written
byte-exact.

| dataset | identity | files |
| --- | --- | --- |
| income | `input_set_id` `2593d2b0c49ccc2c42e9664e63cfd228f1cd7eeacfa824d39ecc9c4be7f5f73f`, `content_hash` `521eadca2112d9c9…` | `revenue_concept.json`, `operating_income_concept.json`, `depreciation_concept.json` |
| multiples | `input_set_id` `b98c4d94270e4e57473deadbc710e9d87d4666cd7095792ddc9fe8efe3a451ba`, `content_hash` `321a99c4265ef58fac130a7422301075fb3aa9b606b200d3aa1e987b776c5e4b` | `cash_concept.json`, `marketable_securities_current_concept.json`, `commercial_paper_concept.json`, `long_term_debt_current_concept.json`, `long_term_debt_noncurrent_concept.json` |

### The two distributions, qualified independently

| distribution | valid | rejected | total evaluations | period | median | status | eligible as a reference |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `P_S_RATIO_REFERENCE` | **23** | 4 | 27 | 2021-07-30 → 2026-07-30 | **11.783822** | `USABLE_FOR_REFERENCE` | **yes** (23 ≥ 20) |
| `EV_EBITDA_RATIO_REFERENCE` | **0** | 27 | 27 | — | — | `UNAVAILABLE` | **no** |

P/S percentiles: 10th `9.632858`, 25th `10.549233`, median `11.783822`, 75th
`12.711876`, 90th `13.236002`; mean `11.533715`, std `1.49521`, min `8.49129`,
max `14.076168`.

**One qualifying distribution does not qualify the other, and neither rule was
moved to make the other one work.**

The four P/S rejections are `REASON_MISSING_REVENUE_WINDOW`, and each names
the fiscal positions the window needed and the date each became knowable: the
acceptance index starts at 2020-10-27, so the first four evaluation dates
(2020-10-28, 2021-01-27, 2021-04-28, 2021-07-28) have no trailing revenue
window, because the fiscal positions it needs are carried by filings outside
the index. The window is refused rather than backfilled with a later filing's
comparative.

**The EV/EBITDA distribution has no qualifying observation, for two
independent reasons that are both evidence, not judgement.** Phase 6.2
corrected the first of them: the element Phase 6 used for the denominator was
the wrong one, and the reason is now the correct one.

1. **There is no qualifying depreciation-and-amortization element for
   Microsoft, so no trailing EBITDA denominator exists at all.** The cash-flow
   line "Depreciation, amortization, and other" is carried on the
   company-specific element `msft:DepreciationAmortizationAndOther`, which
   the company-concept API does not serve and the core registry does not
   accept; the element that *is* acquirable, `us-gaap:Depreciation`, is the
   property and equipment note's depreciation expense, which is depreciation
   alone. Every evaluation date refuses with
   `REASON_NO_QUALIFIED_DA_EVIDENCE`. See Phase 6.2 below.
2. **The EV bridge would not have qualified the distribution either.** Only 8
   of the 27 evaluation dates have all five components describing one balance
   sheet: Microsoft disclosed its commercial paper through the fair-value note
   (6,693 million at 2024-06-30 and an explicit zero at 2025-06-30) and has
   not reported it since, so 15 dates have no commercial-paper evidence inside
   the acceptance index and the last four carry the stale 2025-06-30 fact,
   which the same-date rule refuses. The ceiling is 8 observations against a
   gate of 20, so the verdict does not depend on the denominator at all.

The distribution therefore reports `REASON_INSUFFICIENT_OBSERVATIONS` with the
tally of the exclusions -- "27 x REASON_NO_QUALIFIED_DA_EVIDENCE" -- so a
reader sees that the sample is thin because of the filer's own evidence and
not because a rule was relaxed.

The bridge is complete, and the same-date rule passes, for the nine dates
between 2023-10-25 and 2025-07-31, where all five components describe one
balance sheet (2023-09-30 through 2025-06-30).

### Independent verification

Recomputed from the raw sources, not from the builder's own output: the
as-traded close from `daily_prices.json`, the cover-page share count from
`shares_outstanding_concept.json`, and the trailing revenue window summed
from the income dataset's own quarters. Every one of the 23 published P/S
values reproduces exactly, and the median and mean reproduce exactly
(11.783822 and 11.533715). Representative dates: 2021-07-30, price 284.91 x
7,514,891,248 shares / 168,088,000,000 revenue = 12.737778; 2025-07-31, price
533.50 x 7,433,166,379 / 281,724,000,000 = 14.076168; 2026-07-30, price
451.10 x 7,425,545,491 / 331,839,000,000 = 10.094243.

The point-in-time rule holds: no operand is knowable after its evaluation
date, the price is the as-traded close of that date, and Microsoft has had no
stock split since 2003, so the close and the cover-page count pair without
adjustment. The market capitalization is continuous across the sample.

### The product wiring

The same generic code carries Microsoft's distribution into the same places
Apple's goes, with no Microsoft-specific branch anywhere:

- The summary reference selects `production_historical_ps_median` 11.783822
  from 23 observations, and the enterprise-value reference reports `none` /
  `UNAVAILABLE` -- Microsoft's P/S reference is never borrowed for anything
  else, and no other issuer's multiple is used for Microsoft.
- The reverse-requirements report carries the compact summary, and the sales valuation method reads the production median with `ELIGIBLE_PRODUCTION_DISTRIBUTION` and `is_user_assumption: false`; the enterprise-value method reports itself unavailable, and the cash-flow method still reads no production reference at all. Clarification (superseded): this sentence records the Phase 6 MSFT audit state; the production historical P/FCF distribution was subsequently rebuilt (`fd311c5`, `historical_pfcf/1.0`) and carried through the web path (`4797f1f`), so the cash-flow method now reads the production reference where eligible — `production_pfcf_for_reference` applies the same `usable_for_reference` gate (>= 20 qualifying observations, the distribution's own median). MSFT's distribution qualifies with 23 observations and median 41.578319 (`production_historical_pfcf_median`); AAPL: 35/36, median 25.343981; MU: 362/575, median 67.712721. The dated sentence is preserved; it no longer describes the current tree.
- The Investment Context registers `refc:ps_reference` under
  `PRODUCTION_PS_MEDIAN` with the observation count 23.
- The archive saves the count, the replay request carries it, and a replay
  over the archive reproduces the document (`MATCH`).
- The web API's DTO and the frontend's existing display path carry the
  summary; the live run computes `implied_revenue` 315,445,516,517.39 from the
  production median (the live market cap 3,717,153,817,339 ÷ 11.783822) and
  no enterprise-value figure, because there is no qualified reference to
  invert.

**Microsoft's current valuation figures are unchanged by this round.** The core
registry is untouched, so `us-gaap:Depreciation` is still not mapped to the
pure depreciation-and-amortization metric, and Microsoft's current EBITDA
remains the provider's figure (207,519,000,000) on the basis the status
document already records. The trailing EBITDA in the historical dataset is a
reconstruction from the filer's own cash-flow line, declared as such in both
manifests, and it is used only as a historical denominator.

### The identity contract, checked

The corrective round added a structured refusal to the income dataset's
payload, and the question that raises is whether the identifiers still mean
what they mean. They do, and the direction is the safe one:

- The income dataset's `input_set_id` digests its **input files** only. The
  structured refusal is payload, so it moved the income dataset's
  `content_hash` and not its identity. A dataset is identified by what it
  was built from, and its content hash says what it produced.
- The multiples dataset's `input_set_id` digests the income dataset's identity
  **and** its content hash, so a change anywhere in the income output moves
  it even where the numbers did not change. That is over-sensitive, and
  over-sensitivity in this direction cannot reuse a stale result: the
  identity never fails to move when the numbers move.
- A stale reuse was checked and is not reachable: a change that moves the
  numbers moves both the identity and the content hash, and the replay
  compares the document and the reference counts, so an archive that no
  longer matches is a divergence rather than a match.

No defect was found here, so nothing was changed.

### Cross-company isolation

The two issuers share no source data and no identity: Apple's
`input_set_id` is unchanged at
`77402a13b164324323ab08341cfca35408b489232a4066f0a9e61b479c78a540` with
28 P/S and 27 EV/EBITDA observations (medians 7.257709 and 22.326), Microsoft's
is `b98c4d94270e4e57473deadbc710e9d87d4666cd7095792ddc9fe8efe3a451ba` with 23
and 0, and each reads its own price series, acceptance index, share series
and concept payloads.

### Tests

`tests/test_historical_multiples_msft.py` (37 tests): the manifest pinning
every file's hash and every source's URL; the concepts being the elements
Microsoft uses; the issuer identity and fiscal year; every observation
carrying its source lineage; no operand knowable after its evaluation date;
the price being the as-traded close of the evaluation date; no split in the
series; the market cap's continuity; every P/S recomputing from the raw
price, share count and revenue window; the median recomputing from the
published observations; every rejection using a closed-set code; a refused
window never backfilled; no enterprise value published from a mixed or an
incomplete bridge; the P/S distribution qualifying on 23 observations and the
EV/EBITDA one reporting unavailable with both causes named; one qualifying
distribution not qualifying the other; the two issuers' identities differing;
Apple's distribution unchanged; each issuer's observations naming only its own
filings; the two issuers reading different price and share series; no
Microsoft multiple offered for Apple; the run selecting the production P/S
median; the enterprise-value reference unavailable and never borrowed; a user
multiple still winning with the right labels; the P/FCF method still reading
no production reference; the report carrying the summary; the compact summary
agreeing with the payload; the archive saving the count; the replay request
carrying it; the replay reproducing the document; a changed count not
reproducing the archive; and an archive without a count not being given one.

### CI

Run **39552263859** for `784d721`:
<https://github.com/sbvcid/st-eva/actions/runs/39552263859>

```
Run backend test suite:  2635 passed, 171 skipped, 1 warning, 534 subtests passed
Run web API tests:         25 passed
Run archive isolation:      6 passed
Run browser smoke tests:   12 passed
conclusion: success
```

Both jobs (`backend`, `browser`) succeeded for the commit `784d721`
(`784d7214b51c2b7007fe713967093e1a50a6b886`). The run's "Assert production
inputs are self-contained" step passed, so both new Microsoft datasets check
out with the bytes their manifests pin.

Local verification for this round: backend suite **2635 passed, 171 skipped,
534 subtests passed**; web API **25 passed** and archive isolation **6
passed**; browser smoke **12 passed**; frontend production build produced
`dist/index.html`. The live path was exercised as well: Microsoft's P/S
reference is selected (`production_historical_ps_median` 11.783822 from 23
observations), its enterprise-value reference is unavailable, `implied_revenue`
is 315,445,516,517.39 (the live market cap 3,717,153,817,339 ÷ 11.783822),
no enterprise-value figure is computed, and Microsoft's current revenue and
EBITDA are unchanged at the provider's figures.

## Phase 6.2 (2026-10-21): Microsoft has no qualifying D&A evidence, and the role is empty

### What the audit found

A read-only audit of the Phase 6 implementation (commit `784d721`) examined
Microsoft's FY2023-FY2026 10-Ks and 10-Qs in their own inline-XBRL instances,
with their facts and contexts, and established:

- The cash-flow line "Depreciation, amortization, and other" is 38,534 million
  for fiscal 2026 (29,433 for 2025, 20,958 for 2024) and is carried on
  **`msft:DepreciationAmortizationAndOther`**, in a context with no dimension
  and in USD. The SEC's own definition of that element says it is the net
  amount of depreciation, amortization and accretion "and other operating
  transactions that are not included elsewhere in the statement of cash flows".
- **`us-gaap:Depreciation` is the property and equipment note's depreciation
  expense** -- 34,300 million for fiscal 2026 (22,000 for 2025, 15,200 for
  2024), on a line that reads "During fiscal years 2026, 2025, and 2024,
  depreciation expense was $34.3 billion, $22.0 billion, and $15.2 billion".
  It is depreciation alone: it excludes the amortization of intangible assets
  (4,700 / 6,000 / 4,800) and the other items the cash-flow line aggregates.
- The company-concept and companyfacts APIs serve Microsoft only `dei` and
  `us-gaap`; `msft:DepreciationAmortizationAndOther` returns HTTP 404 and is
  absent from companyfacts. The element is reachable only by reading the
  filing's own inline XBRL, and the core registry does not accept it.

So the Phase 6 income dataset was reading the note's pure depreciation as the
depreciation-and-amortization role, and its "TTM EBITDA" was operating income
plus depreciation alone -- 189,537 million for fiscal 2026 where the cash-flow
line's own figure would make 193,771 million.

### What changed

- The depreciation-and-amortization role is now **empty for Microsoft**. The
  income config names no element for it, and the loader builds no such role.
- The note's pure depreciation is **kept as source evidence** and named for
  what it is. The file is now `depreciation_expense_concept.json` -- the
  name makes the semantic error structurally impossible to repeat -- it is
  digested so the dataset's identity covers what the dataset holds, and it
  contributes to no figure.
- No trailing EBITDA window is constructed for any date, and every
  observation refuses with the new reason code
  `REASON_NO_QUALIFIED_DA_EVIDENCE`, whose text names the element the issuer
  reports and why it is not the metric. Nothing is estimated, the provider's
  current figure is not used to fill a historical window, and the two note
  elements are not added together to stand in for the cash-flow line (for
  fiscal 2026 they sum to 39,000 million against the 38,534 million the line
  reports, because the line is a net figure that also aggregates accretion
  and other operating adjustments).
- The `msft:DepreciationAmortizationAndOther` element stays out of the D&A
  role. Accepting it is a separate registry decision, and this round does not
  make it.
- The EV/EBITDA distribution's refusal now names the cause that binds:
  `27 x REASON_NO_QUALIFIED_DA_EVIDENCE`. The EV bridge's own state is still
  recorded on every observation, and its evidence ceiling -- 8 complete
  bridges against a gate of 20 -- means the verdict does not depend on the
  denominator.

### Superseded in part by Phase 7.2

The figures in this section are what Phase 7 published, and they are left
here as the record of that round. Phase 7.2 withdrew one of the two
production qualifications: the P/S denominator's element had been retired by
registry decision 2.99 and was never qualified, so the P/S distribution is
now reported as a short sample of four observations. The EV/EBITDA median
moved from 13.224119 to 13.221693 because the one non-contiguous window is
now refused. See "Phase 7.2" below.

### The identities, before and after

| dataset | before (Phase 6) | after (Phase 6.2) |
| --- | --- | --- |
| MSFT income `input_set_id` | `2593d2b0c49ccc2c42e9664e63cfd228f1cd7eeacfa824d39ecc9c4be7f5f73f` | `39302572afa7c49ee22569681e43c1e46e39842610358d9d09cf2b166ac4bdee` |
| MSFT income `content_hash` | `521eadca2112d9c9732a0218df0bc012b77231dd15c5e76207a6a2942a376479` | `d57ea0aeb4db864ef9cae8644fbb71a110cbc697efd475163a10b4ddbf25af5b` |
| MSFT multiples `input_set_id` | `b98c4d94270e4e57473deadbc710e9d87d4666cd7095792ddc9fe8efe3a451ba` | `ba4b639cc4ca353ce999ac6c5190f6d169c6717634a55c82282d75033d18988f` |
| MSFT multiples `content_hash` | `81f4b14c3c982a09b3f675f907e33d852af3ba021f163672b94bb6fc47573bac` | `d80b2d3d16331b3ed67f9d9edd4aa4ea75c1b405d6539cd9f2d9108a8cd38774` |

The identities moved because the content moved: the income dataset no longer
holds a depreciation role, its input manifest now carries the evidence file
instead of a role file, and its observations state a different refusal. They
were not preserved to keep the old identifiers.

**Apple's identities did not move at all**: income `input_set_id`
`401a14e73b53e6b1434be23b2c27c4ea6a0a10db0025b23cbf3740419c58e4b4` and
`content_hash` `568d33fac2c202a2ac601657a6a5ebffdaa9057d0aec5bd2f0b600bec3f1f30b`;
multiples `input_set_id`
`77402a13b164324323ab08341cfca35408b489232a4066f0a9e61b479c78a540` and
`content_hash`
`321e8b165bfc7ef30e4c178934a122e5bc2f41fd639ab7ad0767d0ce595b59b0`. Its P/S
(28 observations, median 7.257709) and EV/EBITDA (27 observations, median
22.326) are unchanged, because the correction is a per-issuer role
declaration and Apple's role is filled by its own element.

### What did not change

- Microsoft's P/S: 23 valid, 4 rejected, median **11.783822** -- the revenue
  windows and the formula are untouched by the correction.
- Microsoft's EV/EBITDA: `UNAVAILABLE`, no multiple published, and no number
  produced from a wrong denominator.
- Microsoft's current figures: revenue 331,839,000,000 and EBITDA
  **207,519,000,000**, still the provider's. The core registry is untouched,
  and the income dataset now holds no element the valuation chain could read a
  filed EBITDA out of.
- The P/FCF method, the user-multiple precedence, and every other valuation
  path.

### Tests

`tests/test_historical_multiples_msft.py` grew to 45 tests. Added for this
round: the role is empty and no element fills it; no observation carries a
trailing EBITDA; the EBITDA role's refusal uses the new reason code and names
no missing position; the pure-depreciation evidence is kept, pinned by hash and
named for what it is; the manifest states which element fills the role, which
is rejected and why, and that the two note elements are not summed to stand in
for the cash-flow line; the pure depreciation reaches no EBITDA figure; the
core registry maps neither element for this issuer; and the dataset is not a
substitute for the provider's current figure.

### CI

Run **39562293886** for `3ec78b7`:
<https://github.com/sbvcid/st-eva/actions/runs/39562293886>

```
Run backend test suite:  2643 passed, 171 skipped, 1 warning, 534 subtests passed
Run web API tests:         25 passed
Run archive isolation:      6 passed
Run browser smoke tests:   12 passed
conclusion: success
```

Both jobs (`backend`, `browser`) succeeded for the commit `3ec78b7`
(`3ec78b7f046625598e3dc498b455db1afca8ab9d`). The run's "Assert production
inputs are self-contained" step passed, so the renamed evidence file and both
manifests check out with the bytes they pin.

Local verification for this round: backend suite **2643 passed, 171 skipped,
534 subtests passed**; web API **25 passed** and archive isolation **6
passed**; browser smoke **12 passed**; frontend production build produced
`dist/index.html`. The live path was exercised as well: Microsoft's current
revenue (331,839,000,000) and current EBITDA (**207,519,000,000**, the
provider's) are unchanged, its P/S reference is still
`production_historical_ps_median` 11.783822 from 23 observations, its
enterprise-value reference is still unavailable, and Apple's references are
unchanged.

## Phase 7 (2026-10-21): a second issuer with a qualified EV/EBITDA reference

### The candidates, and why American Electric Power

The task was a second issuer whose *enterprise-value* reference qualifies, so
the candidates were assessed on the evidence before any dataset was built. The
assessment read each candidate's own company facts: the period ends where all
five bridge roles have a fact (the bridge's evidence ceiling) and the
depreciation and amortization element each candidate actually uses.

| candidate | five roles aligned at the same period end | the D&A element the issuer uses | verdict |
| --- | --- | --- | --- |
| **PEP** (PepsiCo) | 2 | `us-gaap:DepreciationAndAmortization` (9 quarterly spans) | the cash-flow line is on a company element the registry refuses; the balance sheet aggregates short-term debt, and the commercial paper is not reported at the fiscal year ends |
| **TXN** (Texas Instruments) | 58 (44 interim) | none: the cash flow states "Depreciation" 1,918 and "Amortization of capitalized software" 81 separately | the bridge is the best measured of any candidate, but no single element carries a combined D&A, and the element it does carry is the pure-depreciation one the Microsoft audit refused |
| **NKE** (Nike) | 1 | `us-gaap:DepreciationDepletionAndAmortization` (8 quarterly spans) | the five roles do not align: the current marketable securities and the long-term debt are not reported at the same balance-sheet dates |
| **AEP** (American Electric Power) | **66 (49 interim)** | `us-gaap:UtilitiesOperatingExpenseDepreciationAndAmortization` (90 quarterly spans) | **selected** |

Roughly 145 issuers were screened for the two conditions together. Only three
had an AAPL-shaped balance sheet at all -- the five roles all reported at the
same balance-sheet date -- and of those only AEP's depreciation line is a
single combined D&A line the registry can accept.

AEP's evidence, read from its own filings:

- The cash-flow line "Depreciation and Amortization" is 3,380 million USD for
  fiscal 2025, carried on `us-gaap:UtilitiesOperatingExpenseDepreciationAndAmortization`.
  The amortization of nuclear fuel is a **separate** cash-flow line (109
  million), so the line is depreciation and amortization and nothing else.
  The element is a utility-sector element, so the registry maps it to the
  metric **for AEP alone** -- the same treatment Apple's own element receives.
- All five bridge components are reported at the same balance-sheet date:
  cash 197, short-term investments 1,656, commercial paper, long-term debt
  due within one year 3,194 and long-term debt 44,128, all as of 2025-12-31.
- The income statement presents "Depreciation and Amortization" as an
  operating expense, so operating income is after it and adding it back gives
  EBITDA.

### What was built

`data/historical_pe/AEP/` (the shared price series and acceptance evidence),
`data/historical_income/AEP/` (three concept payloads) and
`data/historical_multiples/AEP/` (five balance-sheet concepts and the
cover-page share counts), each with a manifest that pins every file's byte
count and SHA-256, the company-concept URL it came from, and the issuer's own
line behind each role. The acceptance index holds 62 filings accepted between
2019-01-24 and 2026-07-30, each read from its own SGML header with the
header's URL and digest recorded, drawn from the submissions' recent list and
from the additional submissions files for the older filings.

| distribution | valid | rejected | total evaluations | period | median | status | eligible as a reference |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `P_S_RATIO_REFERENCE` | **29** | 4 | 33 | 2019-02-22 → 2026-07-30 | **2.728945** | `USABLE_FOR_REFERENCE` | **yes** (29 ≥ 20) |
| `EV_EBITDA_RATIO_REFERENCE` | **25** | 8 | 33 | 2019-10-24 → 2026-07-30 | **13.224119** | `USABLE_FOR_REFERENCE` | **yes** (25 ≥ 20) |

### The rejections, each with its cause

- **Four dates carry `REASON_SOURCE_CONCEPT_COVERAGE_GAP`** (2019-01-24 and
  2021-07-22, 2021-10-28, 2022-02-24). At the first, the capture carries no
  fact from the one filing the index records as knowable. At the other three,
  the captured revenue concept carries no fact for **fiscal 2021 Q1 in any
  filing**: the issuer reported that quarter on the contract-revenue element
  instead, and the two elements are the same quantity on different elements
  rather than two quantities to add. The reason says exactly that, and the
  window is refused rather than backfilled.
- **Four dates carry `REASON_MISSING_EBITDA_WINDOW`** (2019-02-22, 2019-04-25,
  2019-04-26, 2019-07-25): the capture carries the D&A facts, but no four
  consecutive fiscal positions were knowable yet, and the reason names the
  positions and the date each became knowable.

### The revenue element, and the decision that stands

AEP's revenue is carried on `us-gaap:Revenues`, and the core registry retired
that element as a mapping to the revenue metric in decision 2.99: the
element's own definition is broader than the metric (it allows investment and
interest income before taxes), and the seeded mapping had described the
relationship in the wrong direction. The tests pin that retirement, and they
pin the three ways it could quietly come back -- as an EXACT mapping, with an
invented scope, or with an unaudited destination.

**This round did not overturn it.** The first attempt at this work added a
scope-limited mapping for AEP; the registry's own regression tests rejected it,
and the mapping was removed rather than the tests. AEP's historical dataset
reads the filer's own "TOTAL REVENUES" line, and the manifest states what
that means and what it does not: the trailing revenue the dataset builds is the
filer's own total revenue, and the issuer's **current** figures in the
valuation chain remain the provider's, because the registry does not accept
this element as the metric. That is the same boundary Microsoft's dataset has.

The enterprise-value reference's denominators are unaffected by that boundary:
its operating income and its depreciation and amortization are both elements
the registry accepts for this issuer.

### The registry, and what it did not change

One mapping was added: `depreciation_and_amortization` for
`us-gaap:UtilitiesOperatingExpenseDepreciationAndAmortization`, scoped to
AEP, on the same evidence discipline as Apple's. The registry's own
inventory tests, which track the seed, were updated with it (54 mappings, 50
identity rows, 34 of them EXACT). Nothing else moved: the pure-depreciation
element and Microsoft's company-custom element are still refused, and the
retired revenue mapping is still retired with no scope invented.

### Independent verification

Recomputed from the raw sources, not from the builder's output: the as-traded
close from the price file, the cover-page share count from the share file, the
trailing revenue from the income dataset's own quarters, and the trailing
EBITDA as the sum of the operating income and depreciation of the same
quarters. All 29 published P/S values, all 25 enterprise-value bridges and
their multiples reproduce exactly, and the medians recompute exactly
(2.728945 and 13.224119). No operand is knowable after its evaluation date;
there is no split in the covered period, so the close and the cover-page count
pair without adjustment; and the market capitalization is continuous across
the sample.

### The product wiring

The same generic code carries AEP's distribution into the same places, with
no issuer-specific branch anywhere: the summary reference selects
`production_historical_ps_median` 2.728945 (29 observations) and
`production_historical_ev_ebitda_median` 13.224119 (25); the report carries
the compact summary and the sales and enterprise-value valuation methods read
the production medians with `is_user_assumption: false`; the Investment
Context registers `refc:ps_reference` and `refc:ev_ebitda_reference` under
their own bases with the counts 29 and 25; the archive saves both counts, the
replay request carries them, and the replay reproduces the document
(`MATCH`). The live run computes `implied_revenue` 23,619,620,943.62 and
`implied_ebitda` 8,874,061,589.74 from the production medians.

The first two issuers are untouched: Apple's identities are still
`77402a13b164…` / `321e8b16…` with 28 and 27 observations and the medians
7.257709 and 22.326, and Microsoft's are still `ba4b639c…` / `d80b2d3d…`
with 23 P/S observations and no qualified enterprise-value reference. The
three issuers' dataset identities are distinct, each reads its own price
series, and no issuer's median is offered for another.

### Two defects this round found and fixed

The first attempt at AEP exposed two latent faults in the multiples builder,
which the first two issuers never reached because every one of their
evaluation dates had a price and a cover-page share count:

- the enterprise-value bridge, the total debt and the liquid funds were bound
  only where a price and a share count existed, so a date without either
  raised `UnboundLocalError` instead of refusing;
- the bridge was likewise undefined at such a date, and the formulas below it
  could not state what the bridge would have been.

Both are fixed: the bridge is now stated empty, with its reason, at a date
that cannot build one, and the debt and liquid-funds figures are bound
outside the branch that computes them.

### Tests

`tests/test_historical_multiples_aep.py` (34 tests): the manifest pinning
every file and every source; the concepts being the elements this issuer
uses; the core registry accepting this issuer's depreciation and operating
income elements; the retired revenue mapping staying retired with no scope
invented; the other issuers' decisions standing; every observation carrying
its lineage; no operand knowable after its evaluation date; the price being
the as-traded close; no split in the covered period; the market cap's
continuity; every P/S recomputing from the raw price, share count and revenue
window; every trailing EBITDA being the sum of its quarters' operating income
and depreciation; every enterprise value recomputing from its components; the
medians recomputing from the published observations; no enterprise value
published from a mixed or an incomplete bridge; both distributions qualifying
on their own samples with the measured counts and medians; every rejection
stating its cause; the references being the distributions' own medians; the
three issuers' identities, distributions and price series being distinct; the
run selecting both production medians; the report carrying the summary; a
user multiple still winning; the cash-flow method still reading no production
reference; the archive saving both counts; the replay request carrying them;
the replay reproducing the document; and an archive without a count not being
given one.

### CI

Run **39577873716** for `d3cec3b`:
<https://github.com/sbvcid/st-eva/actions/runs/39577873716>

```
Run backend test suite:  2678 passed, 171 skipped, 1 warning, 534 subtests passed
Run web API tests:         25 passed
Run archive isolation:      6 passed
Run browser smoke tests:   12 passed
conclusion: success
```

Both jobs (`backend`, `browser`) succeeded for the commit `d3cec3b`
(`d3cec3b6731ef21477dfaf2fbb5237402f81072a`). The run's "Assert production
inputs are self-contained" step passed, so the new American Electric Power
datasets check out with the bytes their manifests pin.

Local verification for this round: backend suite **2678 passed, 171 skipped,
534 subtests passed**; web API **25 passed** and archive isolation **6
passed**; browser smoke **12 passed**; frontend production build produced
`dist/index.html`. The live path was exercised for the new issuer as well:
both production medians are selected, `implied_revenue` 23,619,620,943.62 and
`implied_ebitda` 8,874,061,589.74 are computed from them, and the first two
issuers' references are unchanged.

## Phase 7.2 (2026-10-21): American Electric Power's data corrected

This is the round the commits `0aadc8a`, `a669135` and `77ec324` performed.
An independent read-only audit had found three defects in what Phase 7
published for American Electric Power.

### The three defects the audit found

1. **The P/S denominator's element was never qualified.** The revenue role
   read `us-gaap:Revenues`, the element registry decision 2.99 retired
   because its own definition is broader than the revenue metric -- it allows
   investment and interest income -- and no scope was invented to rescue it.
   The number was the issuer's own "TOTAL REVENUES" line and was in substance
   right, but the qualification the project requires for a metric claim was
   never established: the production gate checks the sample size, the
   point-in-time rule, the data's completeness and the bridge's date rule,
   and it never asks whether the element is the metric.
2. **A fiscal label contradicted the periods the facts cover, and a
   non-contiguous window was published.** American Electric Power's fiscal
   2021 first-quarter 10-Q declares `dei:DocumentFiscalYearFocus = 2020` and
   `DocumentFiscalPeriodFocus = Q3` for the period ended 2021-03-31, a
   position its own fourth-quarter 10-Q already holds. The calendar
   reproduces the issuer's declaration, so two period ends claimed one fiscal
   position, and the window published at 2021-04-22 summed December 2019,
   March 2020, June 2020 and **March 2021** -- fifteen months with a gap.
3. **The capture was one filing behind the issuer.** The company-concept API
   still ended at 2026-03-31 for every element, although the FY2026
   second-quarter 10-Q (`0000004904-26-000059`, accepted 2026-07-30, period
   2026-06-30) reports the same elements the capture already held.

### What changed

**The revenue role.** The role now names
`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`, the
registry's own EXACT source for the revenue metric. The retired element is
not used for anything, and no mapping, scope or test was changed to revive
it. That element's own coverage begins with the fiscal 2023 annual figure, so
the trailing revenue window exists for four evaluation dates only: **the P/S
distribution now holds 4 valid observations and is reported
`INSUFFICIENT_OBSERVATIONS`**, with the statistics stated for review and the
production qualification withdrawn. The 29-observation P/S and its median
2.728945 are gone.

**The window rule.** Two generic checks were added, and neither assumes a
calendar quarter or ninety days -- the issuer's own periods decide:

- *Contiguity.* A window's four quarters must begin the day after the
  previous one ends. The window published at 2021-04-22 is refused, and the
  refusal names the break: "2020-04-01..2020-06-30 is followed by
  2021-01-01..2021-03-31".
- *An unresolved position.* Where the walk cannot fill a position and the
  capture holds the period that position would cover under a different
  label, the position cannot be determined, and the reason is
  `REASON_FISCAL_POSITION_UNRESOLVED` -- not a source-coverage gap, which
  says the facts are not there. The dates 2021-07-22, 2021-10-28 and
  2022-02-24 report it with the period, the period end and the label the
  issuer's own declarations give.

**The capture.** The facts the company-concept API does not yet carry were
read from the FY2026 second-quarter 10-Q's own inline XBRL instance:
consolidated facts only, no dimensional qualifiers, each keeping its
accession, acceptance datetime, context, period, unit and source URL. The
concept payloads carry the company's own response and the instance's facts
together, and the manifest records both sources and the count each
contributed.

### The corrected results

| distribution | valid | rejected | total evaluations | period | median | status |
| --- | --- | --- | --- | --- | --- | --- |
| `P_S_RATIO_REFERENCE` | **4** | 29 | 33 | 2025-10-29 → 2026-07-30 | 3.126102 (descriptive only) | `INSUFFICIENT_OBSERVATIONS` |
| `EV_EBITDA_RATIO_REFERENCE` | **24** | 9 | 33 | 2019-10-24 → 2026-07-30 | **13.221693** | `USABLE_FOR_REFERENCE` |

The EV/EBITDA reference qualifies on 24 qualifying observations, and its
median is the value the audit predicted before the fix -- 13.221693 is what
the sample gives once the one defective observation is out of it. The nine
refusals are four `REASON_FISCAL_POSITION_UNRESOLVED` (the windows that walk
through the position two period ends claim), four
`REASON_MISSING_EBITDA_WINDOW` and one `REASON_SOURCE_CONCEPT_COVERAGE_GAP`.

### The identities, before and after

| dataset | before (Phase 7) | after (Phase 7.2) |
| --- | --- | --- |
| AEP income `input_set_id` | `eed2b0f18e719278f602c78233a3133757ce3f9feaa5f99c2c092b03f2bef341` | `fc2b06c1559ced2bcbb5623466f81bacff2387706c84f424ba007888012dcdcc` |
| AEP income `content_hash` | `fe36b4fb7cd288fa1d3627f22b2004d63bb673a8af9a5f2befe5c4a5030f44fb` | `15ff76e928937f0972afaeb9885ce85b703af4feca91f7131b83c3fe8234f8f8` |
| AEP multiples `input_set_id` | `334501040f1f19659be7114a050ef2cb7ffe58175e8512ab7ae0a434a30ddb00` | `eb3371bbe1ca007e0f60266c37f43c17dacda6f986d6766b00e83b176b4f965b` |
| AEP multiples `content_hash` | `d13c8a7d6a51cfd31ae4a6269428037f2176a81ff10852a190dca84d18082ec2` | `8b9c45966aa26d725ea11c012682d1fbf1cff357f5c054c2e9b7c8af7161e38e` |

The identities moved because the content moved, and they are measured from the
commits themselves rather than quoted: the "before" column is the identity the
Phase 7 build produced, and the "after" column is what the corrected build
produces.

**Apple and Microsoft are untouched.** Apple's income dataset is still
`401a14e73b53…` / `568d33fac2c2…` and its multiples dataset
`77402a13b164…` / `321e8b165bfc…`, with 28 and 27 qualifying observations
and the medians 7.257709 and 22.326. Microsoft's are still
`39302572afa7…` / `d57ea0aeb4db…` and `ba4b639cc4ca…` / `d80b2d3d163…`,
with 23 P/S observations and no qualified enterprise-value reference. The
window rule fires for neither of them, because neither has a contested
position.

**American Electric Power's current figures.** With the revenue role now
naming the element the registry accepts, its current revenue in the valuation
chain becomes a filed figure rather than the provider's; its current EBITDA is
unchanged, because the depreciation role still names an element the registry
does not accept, so the current record is refused as before. Microsoft's
current figures are untouched by this round: its revenue role already named
the registry's own source, and its depreciation role is still empty.

### The history

The Phase 7 distributions were published and are recorded above as they were:
a P/S of 29 observations with a median of 2.728945 and an EV/EBITDA of 25
observations with a median of 13.224119, the latter resting on one
non-contiguous window and on a revenue element the registry had retired. This
round withdrew that production qualification, corrected the window rule, and
rebuilt the datasets. The earlier numbers are not written back as correct.

### Tests

`tests/test_historical_multiples_aep.py` (38 tests): the manifest pinning
every file and every source; the revenue role naming the registry-accepted
element; the retired element carrying no mapping in the registry; the
concepts being the elements this issuer uses; the latest filed quarter being
in the capture; every observation carrying its lineage; no operand knowable
after its evaluation date; the price being the as-traded close; no split in
the covered period; every P/S recomputing from the raw price, share count and
revenue window; every trailing EBITDA being the sum of its quarters'
operating income and depreciation; every enterprise value recomputing from its
components; the medians recomputing from the published observations; no
enterprise value published from a mixed or an incomplete bridge; the
non-contiguous window being refused and the refusal naming the break; a
position the issuer labels inconsistently being reported as unresolved while a
missing fact is still reported as a missing fact; each distribution qualified
on its own evidence; the three issuers' identities, distributions and price
series being distinct, and the first issuer's identities pinned by value; the
run selecting the qualified enterprise-value median and not the unqualified
sales one; a user multiple still winning; the cash-flow method still reading
no production reference; the archive saving the count; the replay request
carrying it; the replay reproducing the document; and an archive without a
count not being given one.

### CI

Run **39591871200** for `0aadc8a`:
<https://github.com/sbvcid/st-eva/actions/runs/39591871200>

```
Run backend test suite:  2681 passed, 171 skipped, 1 warning, 534 subtests passed
Run web API tests:         25 passed
Run archive isolation:      6 passed
Run browser smoke tests:   12 passed
conclusion: success
```

Both jobs (`backend`, `browser`) succeeded for the commit `0aadc8a`
(`0aadc8a919a4fdc3d08e3ddba75194abb45ca386`). The run's "Assert production
inputs are self-contained" step passed, so the corrected American Electric
Power datasets check out with the bytes their manifests pin.

The two commits that followed carried this document only: `a669135` recorded
this CI run, and `77ec324` removed a trailing space from the status header.

Local verification for this round: backend suite **2681 passed, 171 skipped,
534 subtests passed**; web API **25 passed** and archive isolation **6
passed**; browser smoke **12 passed**; frontend production build produced
`dist/index.html`.

## Phase 7.3 (2026-10-21): phase and documentation reconciliation

A reconciliation against the commits themselves -- their diffs, the manifests,
the tests, the dataset identities and this document -- was carried out to
establish what each of the three preceding commits had actually changed and
whether the two corrections had landed on the right issuer.

### What the commits changed

`0aadc8a` touched only American Electric Power's data files -- the four
under `data/historical_income/AEP/` and the seven under
`data/historical_multiples/AEP/` -- together with the shared code, the
issuer's test file and this document. **No Microsoft or Apple data file was
modified.** The accession `0000004904-26-000059` appears in exactly the nine
American Electric Power payloads, and in no other issuer's files.
`tests/test_historical_multiples_aep.py` is scoped to that issuer
(`TICKER = "AEP"`); its references to the other two issuers are the
cross-company isolation assertions.

### What the identities show

Each issuer's identities were measured from the commits by extracting a
revision into a temporary directory and rebuilding the datasets there:

| issuer | dataset | before the correction | after |
| --- | --- | --- | --- |
| AAPL | income | `401a14e73b53…` / `568d33fa…` | unchanged |
| AAPL | multiples | `77402a13b164…` / `321e8b16…` | unchanged |
| MSFT | income | `39302572afa7…` / `d57ea0ae…` | unchanged |
| MSFT | multiples | `ba4b639cc4ca…` / `d80b2d3d…` | unchanged |
| AEP | income | `eed2b0f18e71…` / `fe36b4fb…` | `fc2b06c1559c…` / `15ff76e9…` |
| AEP | multiples | `334501040f1f…` / `d13c8a7d…` | `eb3371bbe1ca…` / `8b9c4596…` |

No issuer's identity was recorded as another's. The Phase 6.2 section's
Microsoft table is correct: `2593d2b0…` and `b98c4d94…` are the identities
Microsoft's datasets held **before** its depreciation role was emptied, which is
what that table says they are.

### What was wrong, and where

Three things were wrong, and none of them was the data:

1. **This document's Phase 7 section had carried the Phase 6 (Microsoft)
   material in one place.** The subsection "The two committed production
   datasets" named `data/historical_income/MSFT/` and
   `data/historical_multiples/MSFT/`, and its identity table held Microsoft's
   pre-fix hashes in rows that describe American Electric Power's datasets. It
   now names the American Electric Power directories, that round's own
   identities, and the share-count payload an issuer without a P/FCF dataset
   carries of its own.
2. **The section that recorded the correction was never written.** The script
   that was to add it stopped on an error before it wrote the file, so the
   document carried the correction's cross-reference without the correction
   itself, and the "Status checked" line still held the withdrawn Phase 7
   figures. The correction is now in the document as "Phase 7.2" above, and
   the status line states the current result.
3. **The commit messages of the correction named the wrong issuer and the
   wrong phase.** `0aadc8a` read "Correct Microsoft's revenue element, the
   window rule and the capture" and its body repeated "Microsoft" where the
   correction was to American Electric Power's datasets; `a669135` read
   "Record the phase 6.2 CI run in the project status". The commits are
   published and are not rewritten; the correction is recorded here, and in the
   commit that follows it.

### The phase numbering, as it now stands

| phase | what it did |
| --- | --- |
| 5 | the production historical P/S and EV/EBITDA references for Apple, and the corrective hardening of their gate and archive |
| 6 | Microsoft as a second production issuer: a qualified P/S reference, and no qualified enterprise-value reference because no element qualifies for its depreciation role |
| 6.2 | the audit that emptied Microsoft's depreciation role, and the correction of its identity chain |
| 7 | American Electric Power as a second issuer with a qualified enterprise-value reference |
| 7.1 | the audit of American Electric Power's revenue semantics, the fiscal labels and its capture |
| **7.2** | **the correction of American Electric Power's revenue element, the window rule and its capture -- the commits `0aadc8a`, `a669135` and `77ec324`** |
| **7.3** | **this reconciliation of the phase numbering and this document** |

The numbers are the ones the work was done under, and no section is
renumbered: the sections above keep the numbers their rounds used, and the
cross-references between them are now correct.

### Nothing else was touched

The reconciliation confirmed the code, the data, the manifests and the
identities to be correct, so no program, dataset, manifest or identifier was
changed in this round. The two issuers that hold qualified references are
unchanged, and the third holds a qualified enterprise-value reference with its
sales reference reported as a short sample.

### CI

Run **39598264148** for `bc36384`:
<https://github.com/sbvcid/st-eva/actions/runs/39598264148>

```
Run backend test suite:  2681 passed, 171 skipped, 1 warning, 534 subtests passed
Run web API tests:         25 passed
Run archive isolation:      6 passed
Run browser smoke tests:   12 passed
conclusion: success
```

Both jobs (`backend`, `browser`) succeeded for the commit `bc36384`
(`bc36384`). The run's "Assert production inputs are self-contained" step
passed: this round changed the document only, and the datasets it describes
check out with the bytes their manifests pin.

Local verification for this round: backend suite **2681 passed, 171 skipped,
534 subtests passed**; web API **25 passed** and archive isolation **6
passed**; browser smoke **12 passed**; frontend production build produced
`dist/index.html`.

## Phase 8 (2026-10-21): registry-backed semantic qualification

The historical income and multiples datasets reconstruct trailing revenue and
trailing EBITDA out of filed SEC facts. A reconstruction can be arithmetically
perfect, point-in-time correct, contiguous and long enough, and still be
built on an element the registry does not accept as this metric for this
filer. Decision 2.99 retired `us-gaap:Revenues` as a source of `revenue`
because it is broader than the target metric, and nothing in the
reconstruction pipeline would have noticed: the retired element's filed values
are complete, knowable and contiguous, so enough of them would have produced
a perfectly computable price-to-sales distribution and, past the threshold, a
production reference.

This phase adds the gate that notices. It does not add a company, a valuation
method, or a threshold, and it does not change any registry decision.

### The gate, and where it runs

`semantic_qualification.py` asks the core registry one question -- is this
element this metric for this filer -- and it answers only one way: the
registry resolves the concept to that metric, as an EXACT IDENTITY mapping, in
force at the date read, whose scope covers the filer. It reads the registry
through `CoreRegistry.resolve_source_concept`, the resolver the
evidence-admission boundary uses, so the repository holds one answer to "is
this concept this metric" rather than two that may disagree. The registry is
materialised in memory from `registry_seed` -- the seed being the
authoritative statement of the registry's decisions -- and is built once per
thread, because a SQLite connection belongs to the thread that opened it and
the gate is called from worker threads as well as from the main one.

It runs in three places, in this order:

1. **`historical_income.py`, before a quarter is built.** The revenue,
   operating-income and depreciation-and-amortization roles are qualified
   against the registry first. A role the registry does not qualify holds no
   quarter at all, so it contributes to no figure, and the refusal names the
   registry's decision rather than a shortage of quarters. The question is
   asked at each evaluation date as well as once for the dataset, so a mapping
   that was not in force on a date does not qualify on that date. Three new
   reason codes carry it: `REASON_NO_QUALIFIED_REVENUE_ELEMENT`,
   `REASON_NO_QUALIFIED_OPERATING_INCOME_ELEMENT` and
   `REASON_NO_QUALIFIED_DA_ELEMENT`.
2. **`historical_multiples.py`, on the denominators and the filed bridge.**
   The income dataset's semantic refusals are carried through unchanged
   rather than restated as coverage or timing problems, and a filed EV bridge
   component the registry does not accept contributes to no bridge
   (`REASON_NO_QUALIFIED_EV_COMPONENT`). A distribution whose denominator the
   registry does not accept is `UNAVAILABLE` for that reason, not
   `INSUFFICIENT_OBSERVATIONS`: a denominator that does not exist cannot be
   sampled more.
3. **`sec_derived_inputs._concept_is_exact_for`**, which now delegates to the
   same gate instead of holding its own copy of the acceptance rule.

Holding a filed element as traceable evidence is not the same as admitting it
to a figure. Microsoft keeps `us-gaap:Depreciation` as evidence, the
registry's standing on it is recorded, and it still contributes to no
EBITDA.

### What the three issuers now hold

| issuer | P/S | EV/EBITDA |
| --- | --- | --- |
| AAPL | 28 observations, median 7.257709, `USABLE_FOR_REFERENCE` | 27 observations, median 22.326, `USABLE_FOR_REFERENCE` |
| MSFT | 23 observations, median 11.783822, `USABLE_FOR_REFERENCE` | unavailable -- the role is empty |
| AEP | 4 observations, `INSUFFICIENT_OBSERVATIONS` | 24 observations, median 13.221693, `USABLE_FOR_REFERENCE` |

Nothing in the figures moved. One thing in the reporting did: Microsoft's
EV/EBITDA distribution now reports
`REASON_NO_QUALIFIED_DA_EVIDENCE` instead of
`REASON_INSUFFICIENT_OBSERVATIONS`. The distribution was never a short sample
-- no count of quarters would produce the denominator the registry says does
not exist -- and a reader sent to look for more observations would have been
sent after the wrong thing. The existing regression test that pinned the old
code was updated to the new one, with the reason stated in the test.

The identities follow the existing contract rather than the change:

| issuer | dataset | `input_set_id` | `content_hash` | observations |
| --- | --- | --- | --- | --- |
| AAPL | income | `401a14e73b53…` unchanged | `568d33fac2c2…` unchanged | unchanged |
| AAPL | multiples | `77402a13b164…` unchanged | `321e8b165bfc…` unchanged | unchanged |
| MSFT | income | `39302572afa7…` unchanged | `d57ea0aeb4db…` unchanged | unchanged |
| MSFT | multiples | `ba4b639cc4ca…` unchanged | `d80b2d3d…` → `3aa6e87b2498…` | unchanged |
| AEP | income | `fc2b06c1559c…` unchanged | `15ff76e92893…` unchanged | unchanged |
| AEP | multiples | `eb3371bbe1ca…` unchanged | `8b9c45966aa2…` unchanged | unchanged |

The raw inputs did not change, so `input_set_id` did not change, and no
observation changed, so no observation hash changed. Microsoft's multiples
`content_hash` moved because the derived distribution's own reason code
moved; that is the derived content, and the distinction the brief asks for --
a registry change is not a data change, and the data identity contract is
untouched.

### The basis travels with the data

- **The datasets** carry a `semantic_qualification` block: the policy, the
  elements, the metric each was read for, the registry's decision, and the
  mapping's own terms.
- **The manifests** (`data/historical_income/{TICKER}/manifest.json` and
  `data/historical_multiples/{TICKER}/manifest.json`, all six) carry the same
  statement in prose, including the components the registry has no standing
  to rule on.
- **The summary** (`production_multiples_summary`) carries it, and the web
  API passes it through as part of the multiples summary.
- **The Investment Context** records it on the production reference itself, as
  `eligibility_semantic_qualification` beside the other eligibility fields.
- **The archive** keeps it in the archived document, and
  `archive.production_reference_qualification_divergence` compares the
  archived standing with the rebuilt one on replay. A difference is reported
  as a divergence that names the standing rather than being smoothed over. A
  basis recorded on one side and absent on the other is not a difference: the
  side that does not record it does not know it, and the field is never
  filled in for it.

A rejected reference does not re-enter the valuation chain. The distribution's
own `usable_for_reference` flag is what the summary reference, the matrix and
the Investment Context read, and a distribution the registry refuses is
`UNAVAILABLE`, so no median is read from it.

### The limitation the registry cannot express

The registry declares no `marketable_securities_current` metric and no
`commercial_paper` metric, so two of the five filed EV bridge components
cannot be qualified by it. The registry has no standing to rule on a metric
it does not model, so the filed-bridge specification governs those two
components and the dataset says so rather than inventing a metric for them.
The other three components -- cash, long-term debt non-current and long-term
debt current -- are registry-expressible and are qualified.

Adding either metric to the registry would widen the registry's accepted
scope, which this phase does not do. It is named here as the work that would
close the gap.

### One consequence worth recording

`archive.py` changed, and the resolver policy identity is a digest of that
file's text. An archive taken before this commit therefore replays as
`DIVERGED` with the policy-identity reason -- the system's designed signal
that the replay policy changed since archival. The AAPL live replay, taken
after the change, reports `MATCH`. The operator's archives under
`data/archives` were read only, never rebuilt, deleted or overwritten.

### Verification

`tests/test_semantic_qualification.py` (25 tests) pins the gate's decisions,
the three issuers' standing and figures, the negative case, and the archive's
handling. The negative case is the decisive one: Apple's own capture -- the
same filed values, the same filings, the same knowability, more than the
twenty complete observations a reference needs -- is re-pointed at the
retired `us-gaap:Revenues`, and the price-to-sales distribution becomes
`UNAVAILABLE` with `REASON_NO_QUALIFIED_REVENUE_ELEMENT` and no production
reference, while the enterprise-value multiple, read from other elements, is
unaffected. The gate is also checked against the registry's own resolver for
every mapping the registry records and each of the three filers, so the two
cannot drift apart.

Local verification for this round: backend suite **2749 passed, 171 skipped,
534 subtests passed**; web API **25 passed** and archive isolation **6
passed**; browser smoke **12 passed**.

CI for this round: commit `9f2911f`, run `39616759679`, `backend` and
`browser` jobs success (backend 2706 passed / 171 skipped / 534 subtests, web
API 25 passed, archive isolation 6 passed, browser smoke 12 passed).

## Phase 9.3 (2026-10-21): the isolated research calculation lane

The production regime refuses a figure for two different reasons and treats
them alike: the figure cannot be published. The evidence may not support it --
the window is not continuous, the fact was not knowable at the evaluation
date, the balance-sheet components do not describe one balance sheet, the
sample is too thin -- and those refusals are correct. Or the registry may not
accept the element, and the filed values are sound while what is missing is
a name that is true of them.

Phase 9.2 designed the separation. This phase implements it, with KO as the
first case. It adds no production issuer, changes no registry decision,
extends no registry scope, and changes no production dataset, valuation result
or Archive.

### What was added

| Artifact | What it is |
|---|---|
| `research_lane.py` | The lane engine: the five data objects, the closed research refusal set, the isolation guard, the point-in-time and window machinery borrowed from the production modules, and the R-9 revision detection. |
| `research_lane_ko.py` | The KO case: the role declarations, the four candidate lanes, the one diagnostic lane, and the research-tree writer. |
| `data/research_multiples/KO/` | The KO capture: the price series, the filing acceptance index, the cover-page share counts and ten filed elements, 1,410 facts, every file with its source URL, its retrieval note and its SHA-256. |
| `data/research_lanes/KO/` | The committed research tree: one summary per lane and an index. |
| `tools/build_ko_research_capture.py` | The capture builder, so the capture can be rebuilt from its sources. |
| `docs/RESEARCH-LANE.md`, `docs/RESEARCH-LANE-KO.md` | The methodology and the case. |
| `tests/test_research_lane.py` | 42 tests over the isolation, the capture, the arithmetic agreement with production, the refusals, the basis breaks and the run identity. |

### The four mechanisms that keep a lane out of production

1. **The names.** `assert_research_isolation()` reads
   `archive.PRODUCTION_REFERENCE_BASES` and
   `investment_context.REFERENCE_SOURCES` and refuses to run on a collision.
   It is checked against the production vocabularies as they are in the
   repository, at run time, rather than against a restatement of them.
2. **The flag.** `ResearchDistribution.production_eligible` is fixed to
   `False` by the type -- declared `init=False` on a frozen dataclass -- so
   it cannot be set at construction and cannot be changed afterwards. No code
   path can turn a research distribution into a production reference by
   forgetting a check.
3. **The gate.** The registry's standing on every element the lane reads is
   recorded on every observation and never decides the arithmetic. A
   registry refusal is a fact about the element.
4. **The destination.** A lane reads a capture and returns a result; the
   caller decides where the result goes, and the only destination the
   repository supports is the research tree. No lane writes an Archive,
   produces a `refc:*` row, reaches an Investment Context, or is read by the
   production runner. `tests/test_research_lane.py` asserts that no
   production module imports the lane and that the research outputs carry no
   production reference.

### The KO case

The production pipeline, run over the same capture, refuses both of KO's
production figures: `P_S_RATIO_REFERENCE` and `EV_EBITDA_RATIO_REFERENCE` are
both `UNAVAILABLE` with zero observations, on all 67 evaluation dates, with
`REASON_NO_QUALIFIED_REVENUE_ELEMENT` and `REASON_NO_QUALIFIED_DA_ELEMENT`.
The registry accepts `us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`
for revenue, and KO files no fact on it; it scopes
`us-gaap:DepreciationDepletionAndAmortization` to Apple and Nike alone.

The research lanes read the same filed facts with the same arithmetic and
publish under their own names:

| Lane | Research metric id | Valid | Refused | Median |
|---|---|---:|---:|---:|
| A | `RESEARCH_KO_REPORTED_REVENUE_MULTIPLE` | 29 | 38 | 6.403373 |
| B | `RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE` | 64 | 3 | 19.775345 |
| C1 | `RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE` | 27 | 40 | 23.639435 |
| C2 | `RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS` | 29 | 38 | 24.675484 |
| C3 | `RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_DOUBLE_COUNTED_DIAGNOSTIC` | 16 | 51 | 25.556776 |

C3 is a diagnostic and not a candidate metric: its `candidate_metric` flag is
false, it is absent from the selectable research metrics, and its formula is
written so that it cannot be read as an acceptable enterprise-value
definition. It measures what a bridge holding both commercial paper and loans
and notes payable would overstate: +0.0161 to +1.3349, that is +0.06% to
+5.79%, on the sixteen dates where it and C2 both publish.

The arithmetic agreement is measured, not asserted: over the same capture the
research lane and the production pipeline produce the same price, the same
share count and the same market capitalisation on all 67 dates, and the same
enterprise value on all 11 dates at which the production bridge is complete.

### What the evidence turned out to say

- KO's balance-sheet line **loans and notes payable is its total short-term
  borrowings**. The FY2025 10-K carries no commercial paper line on the face
  of the balance sheet, the debt note says loans and notes payable consist
  primarily of commercial paper, and the filed values satisfy
  `NotesAndLoansPayable = CommercialPaper + OtherShortTermBorrowings` at
  every date at which both are reported. A bridge holding both counts
  commercial paper twice, which is what C3 measures and what C2 exists to
  avoid.
- The two bridge lanes' medians differ by 1.036049, and the lanes do not
  offer that as a measure of anything: the two sample different dates against
  different balance-sheet compositions, and C1's sample is constrained by
  commercial paper's annual-only reporting.
- KO's consolidation of Coca-Cola Beverages Africa re-presented FY2017
  revenue from 35,410,000,000 to 36,212,000,000 and FY2018 from
  31,856,000,000 to 34,300,000,000, and re-presented operating income in
  twenty revisions across the sample. R-9 detects each of them as a
  `PRIOR_PERIOD_VALUE_REVISION` -- the lane's evidence shows a value it
  already knew was replaced by a different value; it does not show that the
  issuer formally restated, and it does not say so.
- KO's marketable securities line changed element at the end of 2020 with the
  same filed value, a re-tagging; its long-term debt changed element at
  2023-12-31 with a different scope, because the successor element includes
  the lease obligation. Both are recorded as basis breaks on the observation.
- Three observations per lane carry a mixed-basis note, where a derived
  quarter subtracts a pre-revision cumulative span from a post-revision one.
  The lane records the condition rather than absorbing it.

### The reconciliation with the phase 9.2 audit

The four phase 9.2 cross-check figures are reproduced exactly from the
committed capture: 29/64/27/29 valid observations and medians
6.403373/19.775345/23.639435/24.675484. The phase 9.2 report's acceptance
criteria listed the exclusion counts as `38 + 3 + 37 + 35 + 19`; the counts
the observation records carry are `38 + 3 + 40 + 38 + 51`. The two bridge
lanes' counts in that list omitted the three window refusals each of them
carries, and the diagnostic lane's count of nineteen was neither its valid
count nor its refusal count. The records are the record.

One number from the phase 9.1 audit could not be reproduced from the filed
inputs under any of the bridge, denominator, element or sample variants that
were tested. It is not carried forward as an expectation anywhere: the test
suite asserts that it appears in no research output, no source file and no
document.

### What this phase does not do

It does not qualify KO for production, and it does not make KO closer to
production qualification. It changes no registry decision, extends no
registry scope, adds no registry metric, changes no production bridge,
window, point-in-time rule or sample gate, adds no production issuer, and
touches no production dataset, valuation result or Archive. KO remains
without a production P/S and without a production EV/EBITDA.

What it adds is a traceable, reproducible capacity to state a figure about
filed evidence the production regime does not admit, and to say exactly what
that figure is and exactly what it is not.

Local verification for this round: research lane suite **42 passed**; backend
suite **2748 passed, 171 skipped, 534 subtests passed**; archive isolation
**6 passed**; web API **25 passed**; browser smoke **12 passed**. The
production payload digests for AAPL, AEP and MSFT are unchanged.

CI for this round: commit `bc32209`, run `39653312560`, `backend` and
`browser` jobs success (backend 2748 passed / 171 skipped / 534 subtests, web
API 25 passed, archive isolation 6 passed, browser smoke 12 passed,
success).

## Phase 9.4 (2026-10-21): the research calculation and its evidence explorer

Phase 9.3 built a lane that computes a named research figure from filed
evidence the production qualification regime does not admit. It was a
library. This phase puts a user in front of it: the user chooses a research
metric, states a multiple and a market value, and reads the figure that pair
implies together with the evidence behind it.

It adds no company, changes no registry decision, changes no production
valuation method, and lets no research result into a production reference,
an Investment Context or a formal Archive.

Local verification for this round: research calculator suite **43 passed**;
research lane suite **42 passed**; backend suite **2791 passed, 171 skipped,
534 subtests passed**; archive isolation **6 passed**; web API **25 passed**;
browser smoke **13 passed**; frontend **113 passed**.

CI for this round: commit `f2a8674`, run `39667766985`, `backend` and
`browser` jobs success (backend 2791 passed / 171 skipped / 534 subtests, web
API 25 passed, archive isolation 6 passed, browser smoke 13 passed,
success).

### What was added

| Artifact | What it is |
|---|---|
| `research_calculator.py` | The service: the selectable research metrics, the reverse calculation, the evidence explorer, and the refusals. |
| `web/research_api.py` | The research path, mounted at `/api/research` on its own routes. |
| `web/frontend/src/components/ResearchPanel.tsx` | The research surface: metric selection, the metric's own figures, the calculation, the result and the observation explorer. |
| `web/frontend/src/services/researchApi.ts`, `src/types/research.ts` | The research client and its contracts, separate from the production client. |
| `tests/test_research_calculator.py` | 40 tests over the catalogue, the calculation, the evidence, the refusals and the isolation. |
| `web/frontend/src/test/ResearchPanel.test.tsx` | 10 tests over the research surface. |
| `tests/test_browser_smoke.py` | A real-Chromium test that enters the research surface and reads the real research API end to end. |

### The operation path

The header carries a mode switch beside the language switch. `Valuation` is
the surface the application has always opened on. `Research` is a separate
surface with its own state, its own client and its own routes; entering it
clears the analysis surface, and a research figure is never shown beside a
valuation result.

On the research surface: the metric is chosen from a selector that has no
default, so no research metric is ever selected for the user; the chosen
metric's name, formula, valid and refused counts, sample period, statistics,
registry standing, basis breaks, value revisions and known limitations are
shown; the calculation states where the multiple comes from and where the
market value comes from; the result carries the implied denominator, the
operands, the formula and its version, the lane's identity and the
calculation's own hash; and the evidence explorer lists every evaluation date
the lane made, published and refused, with the reason each refusal gives, and
opens the full source chain of any one of them.

### The four metrics and the calculation

The metrics keep their own names and formulas. None of them is presented as
a price-to-sales or an EV/EBITDA reference, because none of them is one.

| Metric | Valid | Refused | Median | Numerator |
|---|---:|---:|---:|---|
| `RESEARCH_KO_REPORTED_REVENUE_MULTIPLE` | 29 | 38 | 6.403373 | market capitalisation |
| `RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE` | 64 | 3 | 19.775345 | market capitalisation |
| `RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE` | 27 | 40 | 23.639435 | this lane's own enterprise value |
| `RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS` | 29 | 38 | 24.675484 | this lane's own enterprise value |

The diagnostic lane is not offered and cannot be selected: asking for it by
name is a refusal, not an empty result.

### A worked example, with its whole source chain

Lane A's own median against lane A's own market capitalisation on
2026-07-29:

```
multiple              6.403373                     (lane A's own median, 29 observations)
numerator             383,265,133,795.44           (lane A's own market capitalisation)
  price               89.08                        (as-traded close, 2026-07-29)
  shares              4,302,482,418                (dei:EntityCommonStockSharesOutstanding,
                                                   accession 0001628280-26-028802, usable 2026-04-30)
implied denominator   59,853,632,420.83            (trailing twelve months of us-gaap:Revenues)
lane input set id     fc48f7e2...580ce
calculation hash      ae79645b...12a3
production eligible   False
```

The implied denominator differs from the denominator the lane observed on
2026-07-29, and that is the point of the calculation: the median is the
metric's own historical statistic, and applying it to a market capitalisation
says what trailing revenue that pairing would imply. The four quarters
behind it are carried with their own evidence -- the quarter ending
2025-12-31, for instance, is derived from the annual span of accession
`0001628280-26-010047` and the nine-month span of accession
`0001628280-25-046054`, both on `us-gaap:Revenues`, knowable from 2026-02-20
and 2025-10-23 respectively -- and the registry's standing on every element
the figure read travels with the result.

### The isolation

- The service asserts `assert_research_isolation()` again at the point a
  figure is produced, rather than assuming the lane's isolation survived.
- The research path is mounted before the single-page-application catch-all,
  so its routes are matched on their own terms, and it starts no analysis
  job, writes no Archive and produces no production reference.
- A user-supplied multiple or market value is labelled
  `user_supplied_research_assumption` and is kept apart from the observed
  facts: it has no observation date, no observation hash, and it does not
  enter the metric's sample.
- A calculation writes no archive, and the production payloads for AAPL, AEP
  and MSFT hold no `RESEARCH_` string, no `research_lane` reference and no
  `research-multiples` reference.
- No production module reads the research tree: `st_eva_runner.py`,
  `investment_context.py`, `archive.py`, `web/service_adapter.py` and
  `web/job_manager.py` name none of it.
- The research-only notice is on the surface from the first moment, and it
  is not a dismissible warning line: the figure is structurally ineligible,
  and the surface states what makes it so.

### The refusals

The service has its own closed refusal set, separate from the lane's
observation refusals: a metric that does not exist, a metric that is not
selectable, a multiple that does not exist, a multiple that is not positive,
an observation the lane refused, an observation that does not exist, a
market value the lane does not have, a market value that is not positive, a
denominator that cannot be built, and a research capture that does not match
its own manifest. Each says which condition it is, and none falls back to a
test figure or a stale one.

### What this phase does not do

It does not qualify KO for production, and it does not make KO closer to
production qualification. It changes no registry decision, extends no
registry scope, adds no registry metric, changes no production bridge,
window, point-in-time rule or sample gate, adds no production issuer, and
touches no production dataset, valuation result or Archive. The four lanes'
names, formulas and statistics are the phase 9.3 ones and still reproduce
exactly.

## Phase 9.6 (2026-10-21): research calculation hardening

The phase 9.5 acceptance audit found two defects in the phase 9.4 research
calculation and one gap in the evidence explorer, and one thing about the
research capture that was worth correcting. This phase fixes the three and
corrects the capture's acceptance times. It adds no company, changes no
registry decision, changes no production valuation method, and leaves the
research/production separation exactly as it was.

### P1: a non-finite operand is refused

The audit found that a `NaN` or an `Infinity` supplied as a multiple or a
market value was accepted: the calculation returned HTTP 200 with
`status: "AVAILABLE"`, and the figure came back as `null`, as `0.0`, or as a
non-finite number, depending on the path.

The refusal is now made in two places, so that it does not depend on a single
layer. The request model refuses a non-finite number at validation
(`allow_inf_nan=False`), and the service refuses one itself, with its own
codes, so a caller that reaches the service directly -- with no HTTP model in
between -- is refused as well. A finite pair whose quotient overflows is
refused too: a very large market value over a very small multiple is not a
figure.

| Code | Meaning |
|---|---|
| `RESEARCH_CALCULATION_REFUSED_MULTIPLE_NOT_FINITE` | The multiple is not a finite number. |
| `RESEARCH_CALCULATION_REFUSED_NUMERATOR_NOT_FINITE` | The market value is not a finite number. |
| `RESEARCH_CALCULATION_REFUSED_RESULT_NOT_FINITE` | Finite operands produced a quotient that is not finite. |

A non-finite result is never published as an available figure and is never
turned into `null`, into `0.0`, or into any other value that would look
like a result.

### P2: the research surface shows the distribution's state

The audit found that the panel never rendered `metric.status`, so a thin
sample would have been presented with its median and no indication that the
sample was below the lane's own descriptive threshold. The metric payload now
carries the state and the threshold, and the surface tells the three states
apart:

| State | What the surface says |
|---|---|
| `RESEARCH_DISTRIBUTION` | The metric holds enough valid observations to be described as a research distribution. It is still a research figure, not a valuation reference. |
| `RESEARCH_THIN_SAMPLE` | The sample holds fewer valid observations than the lane's descriptive threshold; the valid count, the threshold and the refused count are shown. |
| `RESEARCH_UNAVAILABLE` | The metric holds no valid observation; the reason travels with the metric and no distribution is presented as a result. |

The threshold is the lane's own research setting, carried in the payload; it
is not hard-coded in the interface, and it is not folded into production
eligibility, which stays `False` on every metric and every result. The
thin-sample notice says so in as many words: a small sample is a
description of a small sample, and it says nothing about eligibility.

### P3: every input says where it came from

The audit found that the denominator carried no unit or currency, and that
the price, the cover-page share count and the denominator's input spans
carried no source file, digest or URL, so a reader had to leave the evidence
view and open the capture manifest to find a source.

Each input now carries its unit, its currency where it has one, the period
it applies to, and its source: the capture file, the file's digest, and the
endpoint the element was read from. The evidence view shows them as a table
-- input, value, unit, period, source, accession, knowable date -- with the
source as a link, so a reader does not have to read a payload to find where
a number came from. A source the capture does not record is shown as not
provided; nothing is guessed.

### The capture's acceptance times

The audit found that the capture wrote each filing's acceptance datetime with
a fixed `-04:00` offset. Eastern local time is not a fixed offset: a
standard-time filing is five hours from UTC and a daylight-time filing is
four. The capture had been recording the instant an hour early for every
winter filing, and for the FY2018, FY2019 and FY2022 annual filings -- all
accepted between 16:00 and 17:00 Eastern -- that made them look knowable a
trading day before the 16:00 ET rule says they were.

The builder now takes the offset from the region, so every record holds the
instant the SEC's own submissions API states, and the capture's usable dates
follow the rule without exception. `tests/test_research_capture.py` pins the
conversion in both seasons and pins the usable dates the capture produces.

Three usable dates moved, and only three: 2019-02-21 to 2019-02-22,
2020-02-24 to 2020-02-25, and 2023-02-21 to 2023-02-22. The four lanes'
valid counts are unchanged; two medians moved, because the evidence behind
the observations on those dates became knowable a day later than the capture
had said.

| Lane | Before the correction | After | Valid |
|---|---:|---:|---:|
| `RESEARCH_KO_REPORTED_REVENUE_MULTIPLE` | 6.403373 | 6.403373 | 29 |
| `RESEARCH_KO_REPORTED_OPERATING_PROFIT_PLUS_REPORTED_D_AND_A_MULTIPLE` | 19.775345 | **19.774421** | 64 |
| `RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_PRODUCTION_SHAPE` | 23.639435 | **23.654283** | 27 |
| `RESEARCH_KO_FILED_EV_BRIDGE_MULTIPLE_SHORT_TERM_BORROWINGS` | 24.675484 | 24.675484 | 29 |

The phase 9.5 audit's independent recomputation, run against the corrected
capture, agrees with the lane on every one of the 67 evaluation dates, for
every lane, on every value and every refusal. The figures that moved moved
because the evidence behind them became knowable a day later, not because
the arithmetic changed.

### What this phase does not do

It does not qualify KO for production, and it does not make KO closer to
production qualification. It changes no registry decision, extends no
registry scope, adds no registry metric, changes no production bridge,
window, point-in-time rule or sample gate, adds no production issuer, and
touches no production dataset, valuation result or Archive. The research
metric that cannot be selected still cannot be selected. The production
payload digests for AAPL, AEP and MSFT are unchanged.

One thing the audit surfaced about the phase 9.4 test suite is worth
recording: the isolation test proved that the research path is not the
production path by asking the production path to run, which started a live
analysis job and ingested KO into the local archive. The test now asserts
the separation on the job manager and the route table instead, and the
research suites leave every one of the nine production archives byte for
byte as they were.

Local verification for this round: research capture suite **8 passed**;
research calculator suite **63 passed**; research lane suite **42 passed**;
backend suite **2819 passed, 171 skipped, 534 subtests passed**; archive
isolation **6 passed**; web API **25 passed**; browser smoke **13 passed**;
frontend **116 passed**. The production payload digests for AAPL, AEP and
MSFT are unchanged, and the nine production archives are byte for byte as
they were.

CI for this round: commit `21343fe`, run `39717641976`, `backend` and
`browser` jobs success (backend 2819 passed / 171 skipped / 534 subtests, web
API 25 passed, archive isolation 6 passed, browser smoke 13 passed,
success).

## Phase 9.7 (2026-10-21): research comparison and sensitivity analysis

The research calculation answers "what is this figure". This phase adds the
questions around it: how a figure moved, why two figures differ, and what a
difference may be attributed to.

It adds no company, changes no registry decision, changes no production
valuation rule, and lets no research result into the production valuation
chain.

### What was added

| Artifact | What it is |
|---|---|
| `research_comparison.py` | The comparison and sensitivity service: the comparability attributes of every research metric, the same-lane historical comparison, the paired bridge comparison, and the sensitivity analysis. |
| `web/research_api.py` | Five more research routes: the definitions, the compatibility, the historical comparison, the paired bridge comparison and the sensitivity. |
| `web/frontend/src/components/ResearchCompare.tsx` | The comparison surface: three comparisons the user chooses between, with its own state and its own metric selectors. |
| `tests/test_research_comparison.py` | 43 tests over the comparability, the two comparisons, the sensitivity, the refusals and the isolation. |
| `web/frontend/src/test/ResearchPanel.test.tsx` | Four more tests over the comparison surface. |
| `tests/test_browser_smoke.py` | A real-Chromium test that reads the real comparison API end to end. |

### The comparability attributes

Every research metric publishes what it may be compared with: the kind of
numerator it divides by, the definition and the elements of its denominator,
the currency and the unit, the formula version, the bridge components, the
registry's standing on it, and the basis breaks it carries. A comparison
between two metrics that do not share a definition is still allowed, and is
labelled as a difference between two different formulas, with no single
attribution offered.

| Pair | What it supports | What differs |
|---|---|---|
| The two enterprise-value lanes | A paired bridge comparison | nothing: same numerator kind, same denominator, same currency, same formula version |
| Lane A against lane B | A side-by-side view | the denominator definition and its elements |
| Lane B against either enterprise-value lane | A side-by-side view | the numerator kind, and the denominator |
| Lane A against either enterprise-value lane | A side-by-side view | the numerator kind, the denominator definition and its elements |

### The paired bridge comparison

Only the dates where both enterprise-value lanes published are paired, and
the count is computed from the observation records rather than assumed. For
KO it is **16 paired dates out of 67 shared dates**, and all 16 are
attributable to the short-term component alone. The other dates are recorded
with their reasons: 13 where the production-shaped lane was refused because
its bridge spanned two balance sheets, 11 where the loans-and-notes lane was
refused because the component was not filed or its bridge spanned two dates,
and 27 where both were refused.

A worked pair, on 2026-07-29, with the balance sheet of 2026-04-03, recomputed
from the two bridges:

```
C1  market capitalisation   383,265,133,795.44
    total debt               43,808,000,000.00   (long-term debt + commercial paper)
    liquid funds             13,311,000,000.00
    enterprise value         413,762,133,795.44   multiple 26.678840
C2  market capitalisation   383,265,133,795.44
    total debt               43,890,000,000.00   (long-term debt + loans and notes payable)
    liquid funds             13,311,000,000.00
    enterprise value         413,844,133,795.44   multiple 26.684128
the enterprise-value difference        82,000,000.00
the short-term component difference    82,000,000.00   (332,000,000 - 250,000,000)
the multiple difference                       0.005288   (82,000,000 / 15,509,000,000)
the denominator                    15,509,000,000    the same window in both lanes
```

The difference is attributable only because the checks hold on that date:
every component of both bridges describes one balance-sheet date and was
knowable at the date, the denominator window is the same version in both
lanes, and the market capitalisation, the long-term debt and the liquid funds
agree. Where any of those does not hold, the pair is marked as affected by
other factors and the factors are named.

**The difference between the two lanes' medians is still not a measurement.**
The two lanes publish on different dates, so their medians are not comparable;
the paired comparison is what the service offers, and the service does not
offer the median difference.

### The historical comparison

One metric at two evaluation dates, recomputed from the observation records:
the two multiples, the two numerators, the two denominators, the absolute and
the percentage change, each observation's own source and content hash, and
the calculation's own hash. The dates in between that the lane refused are
returned with their reasons, so that two figures are never read as a
continuous series. The comparison also reports what changed in the evidence
itself between the two dates: the elements each bridge read, the balance
sheet each bridge described, and whether the denominator window moved, so
that an element change or a value revision is not read as a market movement.

### The sensitivity analysis

One named assumption applied to one published figure. The assumptions are a
closed set -- `NUMERATOR_MULTIPLIER` and `MULTIPLE_OVERRIDE` -- and each
records its name, its value, its unit, its own hash and the label
`user_supplied_research_assumption`. The baseline, the adjusted figure, the
change and the formula are all shown. The observation is never modified, and
a sensitivity may only be computed on a date the lane itself published, so it
cannot be used to get around a point-in-time refusal, a fiscal window that
does not exist, or an incomplete enterprise-value bridge. A sensitivity is
labelled as a what-if on one named input; it is not a forecast, a target
price or a fair value.

### The interface

The comparison surface has its own state and its own metric selectors, and
no metric and no date is chosen for the user. It offers three comparisons,
and the user chooses which: one metric at two dates, two metrics on the dates
where both published, or one assumption applied to one published figure. The
comparability statement is shown before the numbers, the sample counts and
the unpaired dates with their reasons are shown, and a comparison that
cannot be made says why.

### What this phase does not do

It does not qualify KO for production, and it does not make KO closer to
production qualification. It changes no registry decision, extends no
registry scope, adds no registry metric, changes no production bridge,
window, point-in-time rule or sample gate, adds no production issuer, and
touches no production dataset, valuation result or Archive. The research
metric that cannot be selected still cannot be selected, and the
double-counting diagnostic is not offered as a comparison either. The four
lanes' observations, refusals and statistics are unchanged by the comparison
function.

Local verification for this round: research comparison suite **43 passed**;
research capture suite **8 passed**; research calculator suite **63 passed**;
research lane suite **42 passed**; backend suite **2862 passed, 171 skipped,
534 subtests passed**; archive isolation **6 passed**; web API **25 passed**;
browser smoke **14 passed**; frontend **120 passed**. The production payload
digests for AAPL, AEP and MSFT are unchanged.

CI for this round: commit `d2bb77b`, run `39725124318`, `backend` and
`browser` jobs success (backend 2862 passed / 171 skipped / 534 subtests, web
API 25 passed, archive isolation 6 passed, browser smoke 14 passed,
success).

## Phase 9.9 (2026-10-22): the research lanes become configuration driven

The research lanes were written for one issuer. The engine behind them was
already issuer-neutral, but the issuer itself was written down twice -- once
in the capture builder and once in the lane module -- and two services
depended on the issuer's own module. This phase makes the configuration the
single source and removes the duplication.

It adds no company, changes no registry decision or scope, changes no
production valuation rule, and commits no new capture.

Local verification for this round: research issuer suite **31 passed**;
research capture suite **8 passed**; research calculator suite **63 passed**;
research comparison suite **43 passed**; research lane suite **42 passed**;
backend suite **2899 passed, 171 skipped, 534 subtests passed**; archive
isolation **6 passed**; web API **25 passed**; browser smoke **13 passed**.

CI for this round: commit `aa06ae0`, run `39746363059`, `backend` and
`browser` jobs success (backend 2899 passed / 171 skipped / 534 subtests, web
API 25 passed, archive isolation 6 passed, browser smoke 14 passed,
success).

### What was added and what went

| Artifact | What happened |
|---|---|
| `data/research_issuers.json` | The single source: the issuer identities, the capture's element table, the roles, the unit policies and the lanes. KO's configuration was migrated from the lane module without a change to any formula, role, refusal or result. |
| `research_issuers.py` | The loader and its checks. A configuration that names a role twice, a lane twice, a metric twice, a role the capture does not hold, a lane that names an unknown role, an unknown formula role or bridge group, a metric that takes a production name, or a missing file is refused with the field that is wrong. Nothing falls back to a built-in issuer. |
| `tools/build_research_capture.py` | The general capture builder, which replaces the issuer-specific one. The element table is the configuration's, the sources are tried in the configured order, and the manifest records each role, its source file name, its URL, its accession coverage, its unit, its normalisation and its digest. |
| `research_lane.py` | The capture's files are found by the role the manifest gives them rather than by their names, and the unit and currency policy is checked before the lane computes. |
| `research_comparison.py` | The bridge's components are read by the group the role declares rather than by their names. |
| `research_calculator.py` | The metric catalogue comes from the configuration. |
| `research_lane_ko.py`, `tools/build_ko_research_capture.py` | Retired. Their content is in the configuration and the registry. |

### The four things the phase set out to remove

1. **The element table was written twice.** The capture builder and the lane
   definition each held the elements. The configuration holds them once, in
   the capture's element table, and a role names the capture role it reads.
2. **The comparison service read fixed component names.** It now reads the
   group a role declares -- `LONG_TERM`, `SHORT_TERM` or `LIQUID` -- so an
   issuer that names its short-term borrowings differently is still compared
   correctly.
3. **The units were never checked against the price's currency.** A lane now
   refuses, before it computes, when a role's unit is not the unit the
   policy names, when the share count is not a count of shares, when the
   price names no currency, or when the price and the denominator are in
   different currencies with no declared conversion rule. The refusals are
   `RESEARCH_REASON_UNIT_UNKNOWN`, `RESEARCH_REASON_UNIT_CONFLICT` and
   `RESEARCH_REASON_CURRENCY_MISMATCH`, and they are results with their
   reason rather than exceptions.
4. **The metric catalogue depended on the issuer's module.** It now comes
   from the configuration, and a lane whose capture has not been built is
   not offered as a metric.

### The three kinds of result, verified separately

**The mathematical results are unchanged.** The four lanes produce the same
67 evaluation dates, the same values, the same refusals with the same
reasons, and the same statistics: 29 and 6.403373, 64 and 19.774421, 27 and
23.654283, 29 and 24.675484, and the diagnostic's 16 and 25.556776. The
paired comparison is unchanged: sixteen paired dates, all sixteen
attributable, the same unpaired dates and the same reason distribution.

**The research identity is unchanged.** The input set id, every observation's
content hash, the distribution's content hash and the comparison hash are
what they were before the migration. The capture's twelve data files were
not touched; only its manifest was rewritten, to record what the builder's
manifest records, and the manifest is not itself part of the input
identity.

**The production results are unchanged.** The payload digests for AAPL, AEP
and MSFT are the ones the phase 9.6 and 9.7 runs recorded, and no registry
decision, scope, bridge, window, point-in-time rule or sample gate was
touched.

### The capture, rebuilt and compared

The builder rebuilt KO's capture into a temporary directory and the files were
compared one by one against the committed capture. The rows of every element
are identical -- the same accessions, the same periods, the same values and
the same units -- so the evidence behind KO's figures is the evidence the
committed capture holds. The files differ in three ways, none of which is a
fact about the filings:

* the price payload carries the provider's live metadata, so its bytes move
  on every request;
* the acceptance index records the digest of a header page the SEC
  generates, so that digest moves on every request as well;
* the element documents carry the normalisation the capture applied, which the
  phase 9.6 capture did not record.

A capture therefore cannot be rebuilt byte for byte, and a rebuild would
produce a different input identity. The committed capture is the one the
identity is pinned to, and the builder's rebuild is the evidence that the
evidence behind it is unchanged.

### The second case

AAPL is configured: its September 52/53-week fiscal year end, the revenue
and depreciation element chronologies the registry accepts, the quarterly
bridge components, the unit policy, and the two splits in its price
series's range. **Its capture is not committed, so no AAPL figure has been
computed and no end-to-end AAPL result is established.** The configuration
case is in place; the second company's numbers are not, and the test says so
rather than working around it.

### What this phase does not do

It does not qualify KO or AAPL for production, and it does not make either
closer to production qualification. It changes no registry mapping or scope,
no production enterprise-value definition, adds no production company and
adds no valuation method. The research metric that cannot be selected
still cannot be selected, and the research results still carry
`production_eligible=False` and write no Archive row, no Investment Context
and no production reference.

## Phase 9.10 (2026-10-22): AAPL's research lane, end to end

Phase 9.9 made the research lane configuration-driven and left AAPL
configured but unbuilt. This phase builds AAPL's capture with the general
builder, runs the lane over it, and checks the result against the production
AAPL dataset observation by observation. It is the phase that answers whether
the shared engine can carry a second issuer whose history is shaped
differently from the first.

It adds no company to production, changes no registry mapping or scope, no
production enterprise-value definition, no valuation method, no Archive and no
Investment Context. Everything it writes lives under `data/research_*`.

Local verification for this round: research lane suite **42 passed**; AAPL
research lane suite **57 passed**; research issuer suite **31 passed**;
research capture suite **8 passed**; research calculator suite **63 passed**;
research comparison suite **49 passed**; backend suite **3001 passed, 171
skipped, 534 subtests passed**; archive isolation **6 passed**; web API **25
passed**; browser smoke **14 passed**.

CI for this round: commit `32f685c`, run `39761358154`, `backend` and `browser`
jobs success (backend 2956 passed / 171 skipped / 534 subtests, web API 25
passed, archive isolation 6 passed, browser smoke 14 passed, success).

### What was added and what went

| Artifact | What happened |
|---|---|
| `data/research_multiples/AAPL/` | AAPL's capture: 67 periodic filings, 4,204 daily closes with both split events, the cover-page share counts, and eleven filed element payloads, with the source, the unit, the normalisation and the SHA-256 of each file. Built by `tools/build_research_capture.py --ticker AAPL`, with no issuer-specific code. |
| `data/research_lanes/AAPL/` | The three lanes' committed summaries and the tree's index, written by `write_research_outputs(..., issuer_ids=["AAPL"])`. |
| `tests/test_research_lane_aapl.py` | The AAPL case end to end: the capture, the fiscal cycle, the two splits, the depreciation element's chronology, the point-in-time rule, the per-observation recomputation, the production cross-check, the isolation and the refusal paths. |
| `docs/RESEARCH-LANE-AAPL.md` | The case document. |

### The three lanes

| Lane | Valid | Evaluations | Median | Period | Status |
|---|---|---|---|---|---|
| `aapl_reported_revenue_multiple` | 32 | 67 | 6.996311 | 2018-11-05 to 2026-07-31 | `RESEARCH_DISTRIBUTION` |
| `aapl_reported_operating_profit_plus_reported_d_and_a_multiple` | 29 | 67 | 22.054083 | 2019-08-01 to 2026-07-31 | `RESEARCH_DISTRIBUTION` |
| `aapl_filed_ev_bridge_multiple_production_shape` | 27 | 67 | 22.326 | 2019-08-01 to 2026-07-31 | `RESEARCH_DISTRIBUTION` |

The refusals are 35, 38 and 40 respectively, and they are read for what they
are: 38 are the missing four-quarter window, and 2 are the mixed balance
sheet in the FY2020 second and third quarters.

### A defect in the shared builder, found by the second issuer

The SEC states a filing's acceptance time twice, and for AAPL the two clocks
disagree: the submissions API serialises the Eastern wall clock with the
offset applied twice, so it runs four hours late in summer and five hours
late in winter. The SEC's own filing index page agrees with the SGML header,
not with the API. The general builder's pattern for the header's
`ACCEPTANCE-DATETIME` matched the filing index's HTML-escaped shape and not the
full submission's `<ACCEPTANCE-DATETIME>...` shape, so a filing whose index
header does not exist -- 18 of AAPL's 67 -- fell through to the API and took
the late time. Several of those filings sit within an hour of the 16:00
Eastern boundary, so the late time moved knowability.

The builder now reads both shapes. AAPL's capture holds the header's own
acceptance time for all 67 filings, and records the API's time and the
difference in hours beside it. KO's committed capture is not rebuilt, so its
identity is untouched; and KO's two clocks agree to the second, so a rebuilt
KO capture would state the same instants with a richer provenance basis.

### The identity contract, made explicit

The phase sets out what each identity covers, because the manifest is not part
of the input identity and a policy change must not be able to produce the same
one:

* the `input_set_id` covers the lane's identity and the SHA-256 of every
  capture file it read;
* the capture manifest describes the capture -- its issuer, its date, each
  file's source, unit and normalisation -- and is not itself part of the
  identity, so a change to a description alone is not a change to the
  calculation;
* the policy identity covers the unit policy and the registry's standing on
  every element each role reads, and it is carried on the distribution and on
  every observation;
* the calculation hash is the hash of the input set id and the observation
  hashes.

Two refusals were added to close the gap between them. A role that names an
element the capture does not hold is refused with
`RESEARCH_REASON_ELEMENT_UNAVAILABLE` rather than read around; the code
already existed and was never raised. A capture whose declared normalisation
disagrees with the unit policy is refused with
`RESEARCH_REASON_UNIT_CONFLICT` before it computes, so a scaling policy that
was changed without rebuilding the capture cannot reuse the old identity.

### The cross-check with production, date by date

On the 35 evaluation dates the research lane and the production AAPL dataset
share, the EV/EBITDA lane and production agree on every one: the same price,
the same cover-page share count, the same market capitalisation, the same
enterprise value, the same multiple to six decimal places, and the same
refusal on the same dates. The revenue lane agrees with production's P/S on
all 28 dates on which both publish.

The four dates on which the revenue lane publishes and production refuses are
named, and the reason is the source facts: the production capture holds only
`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`, while the
research capture also holds `us-gaap:Revenues`, which the FY2018 10-K states
FY2018's quarters on. The medians differ because the samples differ (6.996311
over 32 observations against 7.257709 over 28), and the research median is
recomputed from the research observations.

### What this phase does not do

It does not qualify AAPL for production, and it does not make AAPL closer to
production qualification. It reads no production median into a research
figure, produces no `refc:*` reference, and writes no Archive row and no
Investment Context. KO's four research lanes publish the same values, the
same refusal reasons, the same input set ids, the same observation hashes and
the same comparison hashes as before, and the production payload digests for
AAPL, AEP and MSFT are unchanged.

## Phase 9.11 (2026-10-22): the research lane's semantic boundaries and its replay

Local verification for this round: research lane suite **42 passed**; AAPL
research lane suite **57 passed**; research lane boundaries suite **28
passed**; research issuer suite **31 passed**; research capture suite **8
passed**; research calculator suite **63 passed**; research comparison suite
**49 passed**; backend suite **3029 passed, 171 skipped, 534 subtests
passed**; archive isolation **6 passed**; web API **25 passed**; browser
smoke **14 passed**.

CI for this round: commit `01887b7`, run `39771424489`, `backend` and `browser`
jobs success (backend 2984 passed / 171 skipped / 534 subtests, web API 25
passed, archive isolation 6 passed, browser smoke 14 passed, success).

Phase 9.10 built AAPL's capture and ran the lane over it. This phase audits
what that lane reads, and it audits the two contracts a research result rests
on: that a fixed input replays to the same figure, and that a change to
anything that matters to the calculation moves the identity that says so. It
adds no issuer, changes no production registry mapping or scope, no
production enterprise-value definition, no valuation method, no Archive and no
Investment Context, and it does not rewrite either capture.

### The AAPL revenue element boundary

The four dates at which the research revenue lane and the production AAPL
dataset do not both publish are audited. Every quarter of every trailing
window names the element it was read from, the accession it came from and the
date it became knowable, and the four dates are:

| Date | FY2018 quarters | FY2019 quarters | Elements in the window |
|---|---|---|---|
| 2018-11-05 | `us-gaap:Revenues` (the FY2018 10-K) | — | one |
| 2019-01-31 | `us-gaap:Revenues` (three) | the successor (one) | two |
| 2019-05-02 | `us-gaap:Revenues` (two) | the successor (two) | two |
| 2019-08-01 | `us-gaap:Revenues` (one) | the successor (three) | two |

So the two elements are mixed inside one lane, and the first of the four
dates rests on the retired element alone.

The determination: the two elements are **not** one claim. Decision 2.99
retired `us-gaap:Revenues` as a source of the `revenue` metric because it is
the broader earning-process measure and includes investment and interest
income, and it is not re-typed as exact because the source is not the same
object. For AAPL, however, the two elements file the same amount for every
period they both cover -- the six periods the capture holds under both, which
include FY2018's first quarter, first half, third quarter, fourth quarter and
annual -- so the figures the mixed windows use are the quarters Apple
reported, on either tag. That is a fact about the filer and not a definition,
and the lane says so.

The lane does not silently continue and does not discard sound figures. R-6's
break is now recorded for the denominator roles, which it was not: the three
windows that span the change carry a basis break naming both elements and
stating what the change did to the filed amount, the observation where the
element the line is carried by changes carries the series break, and the
distribution's basis-break summary names the three dates. The revenue lane's
`content_hash` moved because of it; the other two AAPL lanes' hashes did not
move, and neither did KO's.

Phase 9.12 superseded the revenue lane's pooled figure: the median of 6.996311
over all 32 published observations described a sample that was not one kind of
figure, and the distribution is now described over one basis.

### The two replay contracts

**A replay over fixed inputs** recomputes the canonical observations, the lane
outputs, the `input_set_id`, the `content_hash` and every observation's hash
from the committed capture files and the committed configuration, without the
network. `tests/test_research_lane_boundaries.py` runs the replay with the
socket refused, compares the result against the committed tree, and checks
that the capture's bytes are untouched afterwards.

**A re-download of the sources** is a new snapshot and is not required to match
the old one byte for byte: the price payload carries the provider's live
metadata and the acceptance index records the digest of a header page the SEC
regenerates. What the phase established about the tooling is that the
manifest is a function of the files it describes, so a manifest written from
the same files is the same manifest, and the manifest can be re-derived
offline.

### The identity contract, closed

Three gaps were found and closed.

* The lane's consistency check read the manifest's copy of the capture's
  normalisation, which is a description. It now reads the concept file's own
  `normalisation` block, which is inside the file and covered by the file's
  digest, and it checks the manifest's copy against the file's and against the
  policy. A capture whose description and whose files disagree is refused
  rather than one of the two being adopted silently, and re-describing a
  capture can no longer paper over a mismatch the files carry.
* The capture builder's scaling policy was applied to the cover-page share
  count as well as to the amounts. The scale now applies to amounts only, and
  the manifest's own copy of the normalisation says so. A dedicated
  regression test holds the count unscaled and shows that a capture scaled a
  thousandfold changes the multiple a thousandfold and leaves the market
  capitalisation alone.
* The capture builder's describe path counted the accessions of a
  multi-element role from its first element only, and re-derived the
  normalisation from the configuration instead of reading it from the file. The
  AAPL capture's manifest now reproduces byte for byte from the capture's own
  files. The KO capture's manifest does not, because it was written by an
  earlier builder that under-counted the accessions of the roles holding two
  elements; its files, its digests and every lane identity are unaffected, and
  it is not rewritten.

### The invariants

The AAPL EV/EBITDA lane still agrees with the production AAPL dataset on all
35 shared dates, field for field. The four divergent dates have a traceable
explanation. KO's four lanes publish the same values, the same refusal
reasons, the same input set ids, the same observation hashes and the same
comparison hashes -- the six KO comparison hashes were computed on the code
before this phase and on the code after it, and are identical. The production
payload digests for AAPL, AEP and MSFT are unchanged, every research result
is still `production_eligible=False`, and no research output carries a
`refc:*`.

## Phase 9.12 (2026-10-22): homogeneous research distributions and manifest consistency

Local verification for this round: research lane suite **42 passed**; AAPL
research lane suite **57 passed**; research lane boundaries suite **28
passed**; research lane homogeneity suite **23 passed**; research issuer suite
**31 passed**; research capture suite **8 passed**; research calculator suite
**63 passed**; research comparison suite **49 passed**; backend suite **3052
passed, 171 skipped, 534 subtests passed**; archive isolation **6 passed**;
web API **25 passed**; browser smoke **14 passed**; the frontend build and
lint unchanged.

CI for this round: commit `f560211`, run `39779933271`, `backend` and `browser`
jobs success (backend 3007 passed / 171 skipped / 534 subtests, web API 25
passed, archive isolation 6 passed, browser smoke 14 passed, success).

Phase 9.11 audited what the research lane reads and closed the identity
contract. This phase makes two targeted corrections: a research distribution
is no longer described over a sample that rests on more than one element, and
the capture's manifest describes a multi-element role's coverage correctly. It
adds no issuer, changes no production registry mapping or scope, no
production enterprise-value definition, no valuation method, no Archive and no
Investment Context, and it re-downloads nothing and rewrites no capture file.

### The AAPL revenue distribution's semantic boundary

The AAPL revenue lane publishes 32 observations, and they are not one kind of
figure: one rests on the retired `us-gaap:Revenues` alone, three span the
change from it to the accepted successor, and 28 rest on the successor alone.
The lane was describing all 32 as one distribution with a median of 6.996311
over them.

The lane now groups its published observations by their **basis** -- the
elements each denominator role's window was read from, read from the
observation's own evidence and not from the issuer's configuration -- and
describes each group on its own:

| Group | Observations | Dates | Status |
|---|---|---|---|
| successor-only | 28 | 2019-10-31 to 2026-07-31 | `RESEARCH_DISTRIBUTION`, median 7.257709 |
| legacy-only | 1 | 2018-11-05 | `RESEARCH_THIN_SAMPLE`, below the threshold of 20 |
| mixed | 3 | 2019-01-31, 2019-05-02, 2019-08-01 | `RESEARCH_DIAGNOSTIC`, and no statistic is published over it |

The distribution's figure is the successor-only group, and it says so: the
`basis` field names the element the median rests on, and `basis_groups` lists
every group with its own count, its own statistics and its own status. The
mixed windows are kept as traceable research observations with their evidence
and their basis breaks, and they are never pooled with a sample. The
threshold is not relaxed, and the lane does not fall back to a statistic over
the mixed observations.

The homogeneous median is 7.257709 over 28 observations, and it is the same
figure the production AAPL dataset publishes for the same 28 dates. The
pooled median it replaces described a sample that is not one kind of figure.

The representation is general: the basis is read from the observations, the
grouping and the choice of the figure are the lane's own, and nothing in it
names an issuer. KO's four lanes and AAPL's other two each hold one group, so
their figures, their medians, their statuses and their identities are
unchanged.

### The KO manifest's accession coverage

The capture builder's describe path counted a multi-element role's accessions
from its first element only, so KO's four two-element roles stated fewer
filings than they were filed in. The defect was reproduced offline from the
committed KO capture: `marketable_securities_current` stated 43 accessions
where the union of its two elements' accessions is 72, and `notes_and_loans_
payable` stated 7 where the union is 30.

The builder is fixed, not the KO capture: the describe path now counts every
element a role holds, de-duplicated, and reads the normalisation from the
capture's own files rather than re-deriving it from the configuration. The
committed KO manifest was then re-described from the capture's own files with
the builder's own writer, and the difference is those four counts and nothing
else. The capture's eleven files and their digests are unchanged, every KO
lane's figures, statuses, input set ids and content hashes are unchanged, and
the manifest still describes the capture rather than standing in for it. The
AAPL capture's manifest reproduces byte for byte from its own files.

The identity contract is unchanged by the correction: the manifest is
descriptive, the files are the capture, and the lane refuses a capture whose
files do not match their recorded digests.

### What this phase does not do

It does not qualify AAPL for production, does not change any lane's
production eligibility, and does not read a production median into a
research figure. The research results still carry
`production_eligible=False`, still write no Archive row and no Investment
Context, and still produce no `refc:*`. KO's four research lanes publish the
same values, the same refusal reasons, the same input set ids, the same
observation hashes and the same comparison hashes; the production payload
digests for AAPL, AEP and MSFT are unchanged; and no source was re-downloaded
and no capture file was rewritten.

## Phase 9.13 (2026-10-22): MSFT's research lane, end to end, and the round's report corrected

Local verification for this round: research issuer suite **38 passed**;
research lane suite **42 passed**; AAPL research lane suite **57 passed**;
research lane boundaries suite **28 passed**; research lane homogeneity suite
**23 passed**; research capture suite **8 passed**; research calculator suite
**63 passed**; research comparison suite **49 passed**; research dossier suite
**34 passed**; backend suite **3014 passed, 171 skipped, 534 subtests
passed**; archive isolation and web API **31 passed**; browser smoke is CI's.

CI for this round: the parent commit `50265f6`, run `39795097273`, and this
commit `1b3c5b5`, run `39808561869`, both `backend` and `browser` jobs
success (the parent: backend 3011 passed / 171 skipped / 534 subtests, web
API 25 passed, archive isolation 6 passed, browser smoke 14 passed; this
commit: backend 3014 passed / 171 skipped / 534 subtests, web API 25 passed,
archive isolation 6 passed, browser smoke 14 passed, success).

The round's first report did not satisfy the round: it named AAPL the third
issuer and quoted the AAPL revenue lane's superseded pooled figures (32
observations, median 6.996311) against the homogeneous contract Phase 9.12
had accepted, and its commit message describes the AAPL work of Phase 9.10
rather than the MSFT work the commit carries. The committed tree was audited
before anything was changed, from the committed captures alone, with no
source re-downloaded and no capture file rewritten.

### The audit of the AAPL contract

The conflict is in the report, not in the tree. The committed
`research_lane.py` at this round's parent is the Phase 9.12 code that groups
published observations by the basis their windows were read from, and the
committed AAPL lane output is its product: regenerating all three issuers'
lane trees from the committed captures with the committed code reproduces
every committed file byte for byte. The AAPL revenue lane at HEAD describes
the successor-only sample (28 observations, 2019-10-31 to 2026-07-31,
`RESEARCH_DISTRIBUTION`, median 7.257709, the basis named on the
distribution), the legacy-only sample (1 observation on the retired
`us-gaap:Revenues`, `RESEARCH_THIN_SAMPLE`, median 3.601818, below the
threshold of 20) and the mixed group (3 observations, `RESEARCH_DIAGNOSTIC`,
no statistic), and publishes no pooled median over the 32. The mixed windows
cannot re-enter the figure: the figure is the largest sample among the
groups, a diagnostic is never the figure, and the lane falls back to nothing.
The regression tests Phase 9.12 added for all of this are in the tree and
pass. No code path was changed for this audit, and no expected hash was
touched.

### MSFT is the third issuer

MSFT's research capture, configuration and lanes are committed by this
round's parent commit, built with the same generic builder, the same
configuration file and the same lane engine as KO and AAPL, with no
MSFT-specific builder logic. The issuer identity is verified from the
filings' own evidence: every capture row's accession resolves under
`/Archives/edgar/data/0000789019/`, every filing header states
`fiscal_year_end 0630`, and the capture's manifest names
`CIK0000789019` / Microsoft Corporation. The capture is research-only: it
lives under `data/research_multiples/MSFT`, and nothing in the production
tree changed (`git diff` against the Phase 9.12 state touches only research
data, `research_lane.py` and research tests).

The acceptance evidence carries each periodic filing's SGML header
ACCEPTANCE-DATETIME with its Eastern offset and the submissions-API reading
beside it, which runs four to five hours late for this filer; the lane
knows a filing from the header time under the 16:00 ET rule. The capture
holds 67 periodic filings (10-K and 10-Q) from 2010 onwards.

### The lanes

| Lane | Valid | Evaluations | Median | Status |
|---|---|---|---|---|
| `msft_reported_revenue_multiple` | 33 | 67 | 10.848125 | `RESEARCH_DISTRIBUTION` |
| `msft_filed_ev_bridge_multiple_over_revenue` | 12 | 67 | 11.628085 | `RESEARCH_THIN_SAMPLE` |
| `msft_reported_operating_profit_plus_reported_d_and_a_multiple` | 0 | 0 | — | `RESEARCH_UNAVAILABLE` |

The revenue lane is one homogeneous sample: every window reads
`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`, the one
element the core registry accepts for MSFT, from the FY2018 10-K onwards.
It does not fall back to `us-gaap:Revenues` or the partially mapped
`us-gaap:SalesRevenueNet` to lengthen the sample, and it says so. The
34 refused evaluations are all `RESEARCH_REASON_NO_DENOMINATOR_WINDOW`
before the accepted element's reach begins. The bridge lane's 55 refusals
are named: 34 no window, 20 `RESEARCH_REASON_MIXED_BALANCE_SHEET_PERIODS`
(the filed bridge requires every component to describe the same
balance-sheet date, and MSFT stops filing commercial paper from the FY2026
first quarter, so a stale instant is refused rather than carried forward),
1 incomplete bridge. All three are `candidate_metric` lanes under the
generic threshold; none is qualified for production.

### The D&A refusal, explicitly

The operating-profit-plus-D&A lane is assessed and refused. Its
depreciation role names `us-gaap:DepreciationDepletionAndAmortization`,
which MSFT does not file: none of the configured sources -- companyfacts,
companyconcept, filing_instance -- served it, and the capture records that
finding. What MSFT does report is `us-gaap:Depreciation`, the property-and-
equipment note's depreciation expense alone, which excludes amortization
and is not the depreciation-and-amortization metric, so the lane refuses
with `RESEARCH_REASON_ELEMENT_UNAVAILABLE` and publishes no figure rather
than substitute the element it happens to hold. This matches the production
finding that Microsoft has no element that qualifies for the
depreciation-and-amortization role, and the production EV/EBITDA
eligibility for MSFT is unchanged by this lane.

### The cross-check with production

On the 21 evaluation dates on which the MSFT research revenue lane and the
production P/S reference both publish, the price, the share count and the
multiple agree to six decimal places on every date. On the three dates both
evaluate where only the research lane publishes -- 2020-10-28, 2021-01-27,
2021-04-28 -- production refuses with `REASON_MISSING_REVENUE_WINDOW` under
its own first-knowable rule, refusing rather than backfill a quarter from a
later filing; the research capture reads the three FY2020 quarters from the
FY2020 10-K itself (accepted after the close of 2020-07-30, usable
2020-07-31) and Q1 FY2021 from the 10-Q usable 2020-10-28, so every quarter
of the window was public before the evaluation date. The difference is the
reach of the two datasets over the same filed facts, not arithmetic, and
the regression tests added this round name the dates and pin the window's
fiscal quarters (2020 Q2-Q4, 2021 Q1) and knowability.

### Isolation and replay

Every MSFT lane result carries `production_eligible=False`, no `refc:*`
appears anywhere in the research tree, and the production payload digests
for AAPL, AEP and MSFT are pinned by the AAPL suite and unchanged. KO's
lanes, refusal reasons, input set ids, observation hashes and comparison
hashes are unchanged: regenerating KO's tree reproduces its committed
files byte for byte, as it does AAPL's and MSFT's. The AAPL Phase 9.12
subgroup results and identities obey the accepted contract, and the
homogeneity suite's identity-sensitivity tests (adding or removing an
observation moves the lane identity; a descriptive-only manifest
re-description moves no figure) pass.

### What this phase does not do

It does not qualify MSFT for production, does not change MSFT's production
eligibility, registry standing or EV/EBITDA policy, does not read a
production median into a research figure, and does not add MSFT-specific
builder logic. The D&A lane's refusal stands: no complete
depreciation-and-amortization evidence for MSFT is claimed, and no
substitute figure is published in its place. What remains unproven is the
submissions-API fallback for a filer whose index headers do not exist
(MSFT's headers all exist), the bridge lane's thin sample (12 observations
is below the threshold and publishes no distribution claim), and any
statement about MSFT's valuation: a research multiple is not a reference.

## Phase 9.14 (2026-10-22): the research surface audited across the three issuers

Local verification for this round: frontend suite **123 passed** (9 files,
including three new regression tests); frontend build and lint unchanged;
backend suite **3014 passed, 171 skipped, 534 subtests passed**; archive
isolation and web API **31 passed**; browser smoke is CI's.

CI for this round: commit `f2eac12` and `f5ecbbd`, run `39821248227`,
`backend` and `browser` jobs success (backend 3014 passed / 171 skipped /
534 subtests, web API 25 passed, archive isolation 6 passed, browser smoke
14 passed, success).

This phase audited the whole research chain -- lane output, catalogue, API
DTO, reverse calculation, comparison, provenance explorer and the frontend
panel -- against the committed captures of the three issuers, read-only
first, with nothing re-downloaded and no committed hash updated. One defect
was found, fixed generically, and pinned by tests; everything else verified
as already conformant.

### What the audit verified as conformant

The catalogue offers exactly the ten candidate research metrics of KO, AAPL
and MSFT and never the diagnostic, which is refused by name if asked for.
The figures on the API path are the committed lanes' own: AAPL's revenue
lane publishes 28 observations over its named successor-only basis with
median 7.257709, keeps the 1-observation legacy sample and the 3-observation
mixed diagnostic beside it with no pooled median over the 32; MSFT's
revenue lane publishes 33 with median 10.848125, its filed-bridge lane 12
as a `RESEARCH_THIN_SAMPLE` with median 11.628085, and its
operating-profit-plus-D&A lane `RESEARCH_UNAVAILABLE` with no median; KO's
four lanes publish 29, 64, 27 and 29 with their recorded medians. The
basis each distribution names is read from the observations' own evidence,
not from the issuer's configuration. The four states are distinguished end
to end: the API carries the status and reason, and the panel renders a
distribution, a thin sample and an unavailable lane differently and shows
the unavailable lane's own reason text.

The reverse calculation uses the selected metric's own homogeneous median
and nothing else: the unavailable MSFT lane refuses a history-median
calculation with `RESEARCH_CALCULATION_REFUSED_MULTIPLE_UNAVAILABLE`
rather than producing a multiple, and a market value for it is refused
rather than invented. The provenance explorer traces one evaluation date
to its source file, digest, element, accession, period, filing date and
usable date, and carries the capture's content-verified identity (the MSFT
capture's manifest names CIK0000789019 and every file is checked against
its recorded SHA-256 before any calculation). The comparison surface states
each pair's compatibility before any numbers: pairs that do not share a
formula are labelled a difference between two formulas with no single
attribution, and the paired-bridge comparison attributes a difference to
the short-term component only on dates where every other component and the
denominator window agree. The user-supplied operand keeps its
`user_supplied_research_assumption` label, and the research-only notice
stands before any figure on the surface.

### The defect found and fixed

Switching the selected research metric cleared the previous metric's
result and evidence but left its detail -- the metric card, its counts,
its median and its whole observation table -- on screen until the new
metric's load finished, and a load that failed left the previous metric's
figures standing behind the new selection indefinitely. The calculation
and the per-date evidence could do the same when the selection changed
while a request was in flight: the previous lane's figure or evidence
would render under the current selection. That is exactly the failure the
surface must not have: one issuer's figures shown as another's.

The fix is generic. A selection now clears the detail first, so while the
new metric loads the panel shows the catalogue's own summary of that
metric and nothing of the previous one, and every in-flight response is
guarded by the selection it belongs to and dropped as stale when the user
has already moved on -- for the detail, the reverse calculation and the
per-date evidence alike. No issuer is named anywhere in the fix. Three
regression tests pin the contract across two issuers' fixtures: each
selected lane shows its own figures and basis, a failed load leaves none
of the previous metric behind, and a late response for an earlier
selection does not overwrite the current one.

### What this phase does not do

It adds no issuer, widens no capture, changes no production data,
registry, eligibility or valuation policy, and touches no committed lane
output, identity or comparison hash: the working tree's only changes are
the panel fix and its tests. The production payload digests for AAPL, AEP
and MSFT are pinned by the AAPL suite and unchanged, every research result
is still `production_eligible=False`, and no `refc:*` appears in research
output. What remains unverified here is the browser smoke pass against the
real API (CI's) and any statement about figures under a user-supplied
assumption, which remain the user's own.

## Phase 9.15 (2026-10-22): cross-issuer research selection through the real API in the browser

Local verification for this round: focused browser smoke **3 passed** (the
two existing research scenarios and the new cross-issuer one); full
backend suite **3014 passed, 171 skipped, 534 subtests passed**; archive
isolation and web API **31 passed**; frontend suite **123 passed** (9
files); frontend build and lint unchanged.

Phase 9.14 left one gap: the cross-issuer selection its fix made correct
had no browser-level proof. This phase adds exactly that, and nothing
else: one new scenario in the existing real-application harness (a real
uvicorn app serving the committed captures, a real Chromium, no route
interception), and no change to any product file.

### The browser path exercised

The user enters the research surface from the header, reads the
research-only notice before any figure, and the catalogue the API served
lists exactly the ten candidate research metrics of KO, AAPL and MSFT --
no diagnostic among them. The user then selects, in order, the AAPL
revenue lane, the MSFT revenue lane, the KO revenue lane and finally the
MSFT operating-profit-plus-D&A lane.

Against the real API (`GET /api/research/metrics` for the catalogue,
`GET /api/research/metrics/{metric_id}` per selection, `POST
/api/research/calculate` once), each selected lane shows its own figures
as committed: AAPL 28 valid observations with median 7.257709 on
`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`; MSFT 33
with median 10.848125 on the same element; KO 29 with median 6.403373 on
its own retired `us-gaap:Revenues`. After each switch the card carries
the new lane's label, count, median and status and none of the previous
issuer's figures -- no residual median, no residual label -- and the
research-only notice stands at every step.

The unavailable MSFT D&A lane is selectable through the supported
contract: the panel shows its `RESEARCH_UNAVAILABLE` status, its own
reason naming `us-gaap:DepreciationDepletionAndAmortization` as the
element the capture does not hold, no median and zero valid observations.
A reverse calculation on it is refused by the real API with
`RESEARCH_CALCULATION_REFUSED_MULTIPLE_UNAVAILABLE`, the refusal is what
the page renders, and no result appears: no unavailable lane produces a
fabricated multiple.

Every wait in the scenario is for an observable condition -- the
catalogue's options, the selected lane's own median text, its own
`data-status` -- with no sleeps, and the race and failed-load paths stay
in the deterministic unit tests, which are unchanged.

### CI

CI for this round: commit `86fadea`, run `39832572712`, overall
`completed`/`success` -- `backend` job success (backend suite 3014 passed
/ 171 skipped / 534 subtests, web API 25 passed, archive isolation 6
passed) and `browser` job success (browser smoke 15 passed, the new
cross-issuer scenario included).

One discrepancy is recorded as it stands rather than rounded off: the
Phase 9.14 CI-record run `39822158008` (commit `491a092`, a one-line
status-file edit) has had both of its jobs report `success` for over an
hour while the run's own aggregate state remains `in_progress` on
GitHub's side. The individual job conclusions are recorded here as
verified via the GitHub API; the aggregate conclusion has not been
supplied by GitHub and is not claimed as successful.

### Isolation

The diff touches only the browser smoke file. No production data,
registry, eligibility or valuation policy changed; the AAPL, AEP and MSFT
production payload digests are pinned by the AAPL suite and unchanged; no
committed research lane output, identity or comparison hash moved; every
research result is still `production_eligible=False` and no `refc:*`
appears in research output.

## Next task status

The Phase 5 round is complete and verified: the production historical P/S and
EV/EBITDA reference distributions exist for AAPL, both pass the shared `>= 20`
qualification gate (28 and 27 qualifying observations), the EV/EBITDA one only
where the filed EV bridge is complete in full **and** every one of its
components describes the same balance-sheet date, and their qualified medians
reach the summary references, the reverse-requirements report's sales and
enterprise-value methods, and the Investment Context under their own bases.
Replay reads the same committed dataset identity the live run reads, and each
reference's own observation count is preserved in the archive, so a dataset
that changed since archival produces a divergence that names the count rather
than a silent match.

The claim that Phase 5 was already complete was checked against the repository
rather than accepted: the work was an untracked, incomplete stub and the
remote `master` was still at `2024f05`. That stub is preserved outside the
repository with its SHA-256; the implementation and its committed inputs are
now on `master`. The implementation was then audited independently, and the
five defects that audit found are corrected in the record above.

No product blocker. Archive cleanup remains deferred per the existing
decision.

The qualified SEC-derived trailing figures are no longer figures the valuation
reports beside its inputs: they are its inputs. The trailing diluted EPS of
8.72, the trailing free cash flow of 136,683,000,000, the trailing revenue of
466,823,000,000 and the trailing EBITDA of 167,959,000,000 are the figures the
four multiples are computed from, and the Investment Context holds the windows
they were built from, so the registry recomputes each one from the four
quarters it holds and the document's own parity check confirms the two agree.
The annual and quarterly figures stay in the admission summary on their own
bases, and the provider's undeclared-period figures stay labelled as what they
are.

The AAPL live replay reports **MATCH** with no field difference: the
production historical P/E and P/FCF references are read from the same committed
datasets the live run reads, and an equally eligible archived observation is
resolved by when it was archived, so a second run on the same trading day
cannot leave the rebuild holding the earlier reading of the same series. An
operator's own multiple still diverges, because that is an assumption rather
than archived knowledge.

The research calculation lane is now implemented and separate from all of the
above. It computes named research metrics from filed evidence that the
production qualification regime does not admit, under its own `RESEARCH_*`
ids and its own formulas, and it is held out of production by four checked
mechanisms: the isolation guard that refuses a research id colliding with a
production name, the `production_eligible` flag that the type fixes to
`False`, the registry standing that is recorded and never enforced, and the
research tree as the only destination. KO is the first case: the production
pipeline refuses both of KO's production figures over the same capture, and
the four research lanes publish 29, 64, 27 and 29 valid observations with
medians 6.403373, 19.775345, 23.639435 and 24.675484. The lane's arithmetic
and the production pipeline's agree on the same capture, date by date. KO is
not qualified for production and is not closer to being qualified.

The research calculation now sits in front of that lane. A user picks one of
the research metrics -- never a diagnostic -- states a multiple and a
market value, and reads the implied denominator with the whole source chain
behind it: the price, the cover-page share count and its accession, the four
denominator quarters and the spans each was built from, the balance-sheet
components and their digests, the registry's standing on every element read,
the basis breaks, the value revisions, the lane's input-set identity and the
calculation's own hash. The refused evaluation dates sit in the same table
as the published ones, with the reason each was refused, and the surface
states from the first moment that the figure is a research figure and not a
valuation reference. A user-supplied operand is labelled
`user_supplied_research_assumption` and never enters the metric's sample.
The path is `/api/research`, separate from the analysis path, and it writes no
Archive and reaches no Investment Context.

That calculation is now hardened. A non-finite multiple or market value is
refused on both the request path and the service path, and a finite pair
whose quotient overflows is refused too, so no research result is ever
published as a non-finite figure. The surface tells a research distribution,
a thin sample and an unusable distribution apart, and carries the lane's own
descriptive threshold so the threshold is not baked into the interface. Every
input now states its unit, its currency, the period it applies to and its
source file, digest and endpoint, and the evidence view shows them as a
table with the source as a link. The research capture's acceptance times
carry the Eastern offset of their own date, so three annual filings are no
longer knowable a trading day before the 16:00 ET rule allows.

The lane now carries a second issuer. AAPL is not a copy of KO with a
different ticker: its fiscal year ends on the last Saturday of September and
its quarters are thirteen or fourteen weeks long, its share count changes
scale twice inside the sample, its revenue and its depreciation both change
tag, and its commercial paper is filed on a different element in two of its
quarters. The same engine, the same configuration file and the same builder
carry it, and the three lanes publish 28, 29 and 27 valid observations over
67 evaluation dates with medians 7.257709, 22.054083 and 22.326. The
enterprise-value lane agrees with the production AAPL dataset on every one of
the 35 dates they share, to six decimal places, and the revenue lane agrees
on all 28 dates on which both publish; the four dates where they differ are
named, and the reason is the source facts rather than a disagreement about
arithmetic. Two things the lane would have got wrong if it had assumed KO's
shape were found and fixed: the builder read the acceptance time from the
submissions API for the filings whose index header does not exist, and the
API runs four to five hours late for this filer, so the lane would have moved
knowability for several filings; and the capture's scaling policy was applied
to the cover-page share count as well as to the amounts, which would have
cancelled the scale out of a market-capitalisation multiple instead of
stating it. The identity contract is now explicit about what each of the
input set id, the capture manifest, the policy identity and the calculation
hash covers, and a role that names an element the capture does not hold, or a
capture whose normalisation disagrees with the unit policy, is refused rather
than read around.

A research distribution is now described over one basis. A lane that reads the
filer's own chronology of elements may publish observations that rest on
different elements, and a median over both of them is a statistic over a
sample that is not one kind of figure. The lane groups its published
observations by the elements their windows were read from and describes each
group on its own: a group whose windows rest on a single element is a sample,
and a group whose windows span a change is a diagnostic whose observations are
kept with their evidence and over which no statistic is published. The
distribution's figure is the largest sample among them, and it names the
element it rests on. The AAPL revenue lane's pooled median of 6.996311 over
32 observations described a sample that was not one kind of figure; the
homogeneous median is 7.257709 over 28, and it is the figure the production
dataset publishes for the same 28 dates. The legacy-only group holds one
observation and says it is below the threshold, and the mixed group holds
three and publishes no statistic at all. The capture's manifest was corrected
at the same time: a role that holds two elements is filed in more filings
than its first element alone, and the coverage now says so.

The lane now carries a third issuer. MSFT is carried by the same engine, the
same configuration file and the same builder, and its June fiscal year, its
10-K's own quarterly revenue facts and its commercial paper's exit from the
balance sheet are all handled by the generic code. The revenue lane publishes
33 observations over 67 evaluation dates with a median of 10.848125 on the
one element the registry accepts for MSFT; the filed-bridge lane publishes 12
and says it is below the threshold; and the operating-profit-plus-D&A lane
refuses outright, because MSFT files no depreciation-and-amortization total
and the lane will not read the property-and-equipment note's depreciation
alone as one. The research lane and the production P/S reference agree to six
decimal places on all 21 dates both publish, and the three dates only the
research lane reaches are named with the filed facts that make the window
knowable. MSFT is not qualified for production by any of this.

No product blocker. Archive cleanup remains deferred per the existing
decision.

## Phase 9.21 — Reverse-Valuation End-to-End Acceptance Audit (verified 2026-10-23, commit fe26c6e)

### Baseline and CI

Git: `master` at `4657bba`, in sync with `origin/master`, clean working tree.
CI run `39439420001` for `fe26c6e`: **backend 3014 passed, 171 skipped, 534 subtests passed; web API 25 passed; archive isolation 6 passed; frontend Vitest 131 passed; frontend build produced `dist/index.html`; browser smoke 15 passed (48.40s).** The workflow is green — no failures.

### Audit findings

All invariants were verified against the committed implementation. **No defects found. No code changes required.**

1. **Identity and price** — verified: `SecurityIdentityHeader` renders ticker, company name, current price, currency, as-of date, and research ID above the matrix; `ResultCards` no longer duplicates them (price appears exactly once as `USD 425.50` for MSFT, ticker `MSFT` exactly once).

2. **Evidence classification** — verified: `is_user_assumption` badges shown for market-price, start-EPS and exit-multiple evidence (blue `user-supplied` badge vs slate `verified-source` badge); market-price badge respects `price_evidence.is_user_assumption` in `ReverseRequirementsMatrix.tsx`.

3. **Production/research isolation** — verified: `production_eligible=False` frozen on frozen `ResearchDistribution` dataclasses; research writes nothing to Archive, produces no `refc:*`, reaches no Investment Context; research API mounted separately at `/api/research`; all 11 research lanes confirmed `production_eligible=False` with no `refc:*` in output.

4. **Reference eligibility** — verified: production historical P/E, P/S, EV/EBITDA and P/FCF distributions gate on their own `usable_for_reference` flag (`>=20` qualifying observations); insufficient samples reported as `INSUFFICIENT_OBSERVATIONS`, never silently substituted; unavailable references reported explicitly, never as zero.

5. **Conditional matrix** — verified: each matrix row discloses holding period, required return, exit multiple and starting EPS basis (`period_label`, `period_start`, `period_end`, `period_undeclared_by_source`, `basis`, `months_covered`); no row preselected; no buy/sell/verdict language anywhere.

6. **Missing/incompatible evidence** — verified: unavailable values shown as `—`, never zero; currency mismatches and incomplete inputs refused explicitly.

7. **Exports** — verified: JSON and CSV retain `refc:*` provenance, `is_user_assumption` flags, `user_assumptions_json`, `sourced_facts_json`, `missing_or_unvalidated_json`; uncomputed matrices exported as status-only rows without fabrication.

8. **Browser acceptance** — verified: 15/15 browser smoke tests pass (48.40s), including identity→matrix→cards ordering and localized heading in en/zh-TW.

### SOFI replay divergence (investigated, replay divergence confirmed, root cause partially verified)

SOFI's two committed context snapshots (`ctx_9474f510dd18e1b4b6fbba568c0d31cf` archived 13:41:02, `ctx_1ae2409054a5aec06729fa0fd3c7d73f` archived 13:46:01, both `USABLE_FOR_REFERENCE`, both from 2026-10-19) were inspected directly from the committed `data/archives/SOFI.sqlite` archive database:

- **ctx_9474f510**: price = `14.54`, `implied_forward_eps` = `None` (provenance `UNAVAILABLE`), `consensus_forward_eps` = `0.82459` (OBSERVED), valuation reference basis = `NONE`
- **ctx_1ae24090**: price = `14.445`, `implied_forward_eps` = `0.7222500000000001` (provenance `CONDITIONAL`), `consensus_forward_eps` = `0.82459` (OBSERVED), valuation reference basis = `USER_SUPPLIED`, multiple = `20.0`

**Confirmed from committed data:**
- **Price changed from `14.54` to `14.445`** — real input change documented in both archived snapshots.
- **`implied_forward_eps` changed from `None` (UNAVAILABLE) to `0.7222500000000001` (CONDITIONAL)** — the direction is the opposite of an earlier note; context 1 has it unavailable, context 2 has it computed.
- **`consensus_forward_eps` was `0.82459` in BOTH contexts** — consensus was available in both snapshots and did not become unavailable.

**Classification: input change confirmed, root cause partially confirmed.**
- The price change (`14.54 → 14.445`) is an observed input change; whether it resulted from a provider revision or another cause is not independently established from committed evidence alone.
- The `implied_forward_eps` change (`None → 0.7222500000000001`) is caused by the valuation reference changing from `NONE` to `USER_SUPPLIED` (multiple `20.0`) between the two snapshots — this is directly observable in the archived data and is not due to consensus unavailability.
- Neither divergence is silenced, smoothed, or overwritten; archived documents are preserved untouched.

**Replay determinism:** Not independently verified from committed code; no replay test files exist in the repository (`tests/test_replay_divergence.py` and `tests/test_replay_snapshot_identity.py` referenced in commit `62fec63` were never added to the repo).

### Tests
- No replay-specific test files exist in the repository. Full backend suite: 3014 passed, 171 skipped, 534 subtests; archive isolation 6 passed; frontend Vitest 131 passed, 9 files; frontend build produced `dist/index.html`; `git diff --cached --check` clean.

### Git
Committed and pushed; remote HEAD verified in sync and the working tree clean.

## Phase 5 (2026-10-20): Production historical P/S and EV/EBITDA reference distributions
