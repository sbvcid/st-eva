# ST-EVA — Current Project Status

**Status checked:** 2026-10-11  
**Repository:** `sbvcid/st-eva`, branch `master`  
**Code baseline reviewed:** `9a43f9f`; the commits after it through `36f2363` changed documentation only.

This is the current, changeable implementation/status record. The root [README](../README.md) defines the enduring product purpose and rules. Historical status snapshots under `docs/archive/` are not current status.

## Product goal

Deliver a usable reverse-valuation web workflow: a user enters a company, inspects the observed price and sourced inputs, specifies or inspects the assumptions, and sees a transparent matrix of the financial requirements implied by each scenario. Every result must be traceable and independently recomputable. ST-EVA reports numbers and data states; it does not judge the assumptions or issue investment conclusions.

## Current implementation

- `reverse_requirements.py` contains deterministic conditional calculations for reverse-requirement scenarios, including holding period, required return, exit multiple, EPS anchor and growth-window semantics.
- `st_eva_runner.py` wires reverse-requirement calculations into the run result. The codebase also has observation/data contracts, source adapters, source comparisons, a historical P/E pipeline for configured issuers, and archive/replay facilities.
- The existing web page accepts a ticker and shows summary valuation metrics, evidence/source identifiers, admission status, and replay status.
- The browser interface is not yet the complete reverse-valuation product. Backend functionality and schemas do not by themselves mean a user can access that functionality from the web page.

## Confirmed gaps from code review

1. **The reverse-requirements matrix is not presented in the web UI.** `ResultCards.tsx` displays summary values; it does not render the full scenario matrix.
2. **The web form does not pass the scenario controls.** `web/frontend/src/App.tsx` sends ticker and mode, but does not pass `reference_multiple` or `horizon_years`; it has no controls for the complete scenario dimensions.
3. **Regression/live mode is misleadingly hard-coded for some examples.** The frontend chooses `regression` for `MSFT` and `0700.HK`, while using `auto` for other symbols. The user must be able to tell fixtures from live observations.
4. **The calculation labels are not yet a single unambiguous contract.** The summary engine's `required_eps_cagr` is not equivalent to a full reverse scenario CAGR, which depends on required return, horizon, exit multiple, and the declared EPS anchor/growth window. Keep both only when their meanings are clearly distinguished; do not use the same label as if they answer the same question.
5. **The matrix does not yet have complete end-to-end trace integration.** `run_st_eva()` places the matrix in `reverse_requirements`, but `_build_context_if_requested()` does not pass that matrix into the Investment Context builder. `SnapshotManager.save()` does not persist the matrix as a dedicated snapshot field. The displayed scenario therefore still needs an end-to-end path back to the actual inputs, formulas, versions and source lineage.
6. **Historical reference-multiple eligibility needs one live policy.** Descriptive availability of a historical band and eligibility to use it as a scenario reference must be separate. Do not let permissive test fixtures silently weaken the production quality gate.

## Most recent completed CI result

[GitHub Actions run 38137689648](https://github.com/sbvcid/st-eva/actions/runs/38137689648), for `cdd5c82`, completed on 2026-10-11 and **failed** in the backend test suite. The browser job passed.

Backend summary: **3 failed, 1,893 passed, 168 skipped, 140 subtests passed**. The failures are:

- `tests/test_2_4_3_traceability.py::TestS3DerivedFigureTraceability::test_a_derived_figure_carries_state_flags_only_when_something_is_wrong`: missing `consensus_price_gap`; the same traceability area also exposes engine/context disagreement over absent percentile fields.
- `tests/test_investment_context.py::TestUnavailableContract::test_engine_and_context_agree_on_what_is_missing`: the context omits unavailable fields that the engine represents as null/unavailable.
- `tests/test_investment_context.py::TestConditionalContract::test_the_reference_states_its_basis_and_source`: a user-supplied reference multiple of `30.0` is represented with a null multiple in the context.

These are unresolved code/test-contract discrepancies, not documentation failures. Fix the underlying contract and behavior rather than weakening assertions merely to turn CI green.

## Work sequence

1. **Protect persistent SQLite data.** Do not delete, reset, or overwrite `data/st-eva.sqlite` or existing files under `data/archives/` as part of cleanup or testing. Inspect destructive/reset paths and run isolation tests against temporary databases. Preserve current records.
2. **Resolve the current CI failures.** Align engine, context, and traceability semantics, including how unavailable fields and user-supplied references are represented.
3. **Make reverse-requirement semantics explicit.** Keep the simpler price/reference-multiple-implied EPS result distinct from the full required-return/horizon/exit-multiple scenario. Give every result one clear name and formula contract.
4. **Complete one end-to-end web scenario path.** Send user-selected assumptions through the API, render the full matrix, and expose each row's inputs, source/period/unit/currency metadata, formula version, and computability reason.
5. **Verify the real AAPL web path.** Check sourced live inputs, calculations against independent recomputation, missing/conflicting inputs, fixture/live separation, and trace details before expanding the same workflow to more issuers or methods.

## Data protection note

The runtime database `data/st-eva.sqlite` may contain persistent local records and is not a disposable test fixture. Never infer that it is safe to reset from its untracked status, a migration convenience, or a test setup. Use explicit temporary database paths for tests.
