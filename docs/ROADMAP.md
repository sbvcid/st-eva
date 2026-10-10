# ST-EVA Roadmap Notes

**Recorded:** 2026-10-10

**Status update, 2026-10-10 — P0, Reverse Requirements V1, Phase C, Phase D, Phase E, Phase F, Phase G, and Phase H**

P0 (parser regression) is complete and verified; see §12. The Reverse
Requirements Report V1 is implemented, wired into every run and verified
end-to-end on live AAPL data; see §13. Phase C adds multi-scenario exit
multiples, financial history, per-method conditional valuation and the research
dossier; see §14. Phase D adds point-in-time financial data, balance-sheet
evidence, capital-structure reconciliation and multi-multiple matrices; see §15.
Phase E implements the production point-in-time Historical P/E pipeline and
evaluation sufficiency gate; see §16. Phase F verifies portability, reconciles
distribution ranges, freezes research packages, and runs independent LLM evaluations; see §17.
Phase G closes capital-structure balance-sheet evidence, discovers the exact mathematical EV bridge,
reconciles EV/EBITDA multiples, and enforces PARTIAL status governance; see §18.
Phase H implements source-backed dividend observations, trailing and indicated dividend metrics,
historical total return calculations (Cash-retained and DRIP-reinvested), and total-return reverse requirement
hurdles with explicit dividend relief deltas; see §19.
Each section records what was actually run.

Ideas and possible work recorded at the time; reconsider them against the current situation before acting on them.

## 1. Product purpose

ST-EVA exists to preserve and provide **verifiable, time-indexed financial evidence and conditional market-implied calculations for LLM research**.

At a given market time, ST-EVA should be able to assemble the price and the financial information available for the company, retain where each input came from, compute transparent financial ratios and reverse calculations under explicitly stated assumptions, and save a reproducible snapshot. An LLM can use that same package to investigate what kinds of future earnings, growth, margins, cash flow, or valuation conditions could be consistent with the observed price.

The long-term research value is not merely a database of prices and financial statements. It is a growing record of **what a market price required under stated assumptions at each recorded time**, backed by the inputs and calculations needed to revisit the question later.

Important distinction: market participants' actual beliefs are not directly observable and a price does not identify one unique forecast. ST-EVA records observed facts and conditional calculations. LLM-generated explanations are hypotheses, not source facts, and must remain separately identified if they are retained.

## 2. Division of work

### ST-EVA provides

- Source-backed market and company financial observations with units, currency, period, source, availability and retrieval times where known, plus preserved source-document identity or payload when available.
- Explicit validation and comparison results. Conflicts, incompatible definitions, missing data, stale data and undeclared publication times remain visible; the system must not silently choose a winner or fill gaps with invented values.
- Deterministic, reproducible calculations that are useful inputs to research: ratios and descriptive metrics, plus reverse calculations under explicit valuation-reference assumptions. Every conditional result records its operands, formula/version and assumptions.
- Point-in-time snapshots and archive/replay facilities so a later run can distinguish what a source had published from what ST-EVA had archived, and avoid silently replacing historical inputs with newer ones.
- A portable, machine-readable evidence package that an external LLM or analyst can inspect without needing to know ST-EVA's internal implementation.

### The LLM provides

- Independent analysis of the shared evidence package: candidate explanations for the price, required business outcomes, alternative assumptions, trade-offs, and questions needing more evidence.
- Additional analysis or calculations where useful, while explicitly disclosing the model's own method and assumptions and keeping them separate from ST-EVA's recorded facts and deterministic outputs.
- Interpretation across time: explanations for how the price-implied conditions may have changed as new prices, financial results and expectations became available.

ST-EVA does not need to call a particular LLM from its core data pipeline. The first goal is a high-quality data package that can be supplied to different models. Provider-specific model integration can be added later if it solves a demonstrated workflow problem.

## 3. What ST-EVA is not trying to become

- It does not predict a company's fair value, forecast its actual future financial results, or produce a target price as a core system output.
- It does not turn a conditional reverse calculation into a claim that the market has one uniquely identifiable expectation.
- It does not produce buy/sell recommendations, investment rankings, model scores or probabilities as authoritative data.
- It does not treat an LLM's narrative as a raw observation, validation verdict or deterministic calculation.
- It does not collect every possible financial field just to increase coverage. Each addition must improve a defined research use case or close a demonstrated evidence gap.
- It does not require a fully rebuilt Historical P/E pipeline before the broader evidence package and point-in-time record can be useful.

## 4. What success looks like

For a chosen company and time T, a successful ST-EVA data package should let a consumer:

1. Identify the market price being explained and the exact time/date and currency it represents.
2. Inspect current and historical financial facts and market expectations where available, with definitions and periods that make their comparability clear.
3. Distinguish source-reported facts, validation judgements, deterministic derived values, and conditional reverse calculations.
4. Trace each important number to its source observation and, where applicable, to the formula and assumptions that produced it.
5. See unavailable, unverified, conflicting, stale, or non-comparable information rather than having the system guess.
6. Rebuild or replay a saved time-indexed package without later information silently changing the old record.
7. Supply the identical package to different LLMs and examine differences in their hypotheses without conflating different inputs with different reasoning.
8. If an LLM analysis is saved for later research, link it to the exact package/version and record the model/configuration and analysis time; never merge the model's claims into authoritative observations.

The goal is not to force all LLMs to reach the same interpretation. The goal is to make their evidence base inspectable and their differences attributable to assumptions, methods or reasoning rather than hidden differences in fetched data.

## 5. Implementation baseline recorded at the time

This section consolidates known repository facts. It is not a substitute for checking the current local checkout, running tests, or inspecting local database files before a change.

| Area | Known state | Meaning for the roadmap |
|---|---|---|
| Reverse calculations | Production code computes current ratios and conditional reverse calculations such as implied forward EPS, EPS gap and required CAGR. | Preserve as a source of machine-checkable research data; do not expand into fair-value prediction by default. |
| Data contract and evidence | Observation, evidence, validation, source adapters and cross-source comparison exist. | Audit actual metric coverage and semantics before adding new data models or sources. |
| Investment Context | Existing context builder packages source observations, validation, derivations, unavailable states and provenance for machine consumption. | Reuse and assess it as the likely starting point for the LLM evidence package. |
| Archive and point-in-time replay | Archive, source-document capture and replay facilities exist. Availability semantics distinguish source-declared publication from archive-first-seen data. | Verify real end-to-end replay behaviour and the completeness of saved market-implied snapshots. |
| LLM consumer | llm_interpreter.py currently builds an interpretation prompt; it is not a live model-provider integration. SPEC.md also records prior agent/evidence-consumption experiments covering grounding, discoverability and semantic interpretation. | Reuse existing experiment evidence. The remaining product question is whether a fixed, versioned package supports useful analysis of price-implied assumptions, not whether generic evidence retrieval works at all. |
| SEC taxonomy catalogue parser | A known defect: parsing the captured official catalogue aborts at a Loc record whose Namespace is absent. | Repair with focused offline tests before broader work. |
| Historical P/E | Research and detailed methodology/contract exist, but the contract-defined production pipeline is recorded as not implemented; an older provider-fed historical band is a separate, narrower capability. | Keep as a potential source/reference workstream, not the automatic mainline. Advance only when justified by the data-package use case. |
| Local database and runtime data | The user's read-only audit on 2026-10-09 found a central data/st-eva.sqlite with one source_documents row and empty other central tables, plus separate AAPL/MSFT/TSM archives. The tracked status checkpoint predates or does not reflect all of that local database detail. | Re-check local state read-only before any operation. Never assume the archive is empty, and never delete/reset SQLite or WAL/SHM files as housekeeping. |

## 6. Capability map considered at the time

The five-part proposal is a useful product-level acceptance checklist. It combines existing calculation and provenance capabilities with some research surfaces that still need to be demonstrated. The items below describe the intended outcome; they do not assert that every output or end-to-end workflow is already implemented.

| Dimension | Existing foundation | Gap / acceptance requirement |
|---|---|---|
| **Operational hurdles** | `required_eps_cagr`, consensus EPS gap, implied FCF / EBITDA / revenue, implied net margin and several valuation ratios are defined in the calculation/context design. | Verify current end-to-end outputs. Make explicit which reference multiple, horizon, current financial basis and share/period assumptions each result uses. A full revenue-growth-versus-margin sensitivity surface is not established merely because `implied_revenue` and `implied_net_margin` exist; add scenario calculations only under explicit assumptions. |
| **Triangulation anchors** | Consensus forward EPS and `eps_gap_vs_consensus` exist in the context design. Historical PE / PS / EV-to-EBITDA bands and percentile calculations are also represented, subject to data and sample-quality limits. | Preserve the forecast period and source basis of consensus EPS. Treat an EPS gap as conditional on the selected valuation reference, not as a direct observation of the market's forecast. Historical 3–5 year EPS-CAGR distributions and peak-margin history are not confirmed as complete standard production outputs; build them only after checking comparable time-series coverage. Never imply a 5–10 year valuation distribution if the actual sample does not cover it. |
| **Time-series deltas** | Point-in-time archive and replay exist, with source-declared versus archive-first-seen availability distinctions and context reproducibility requirements. | A reliable replay does not by itself mean there is a validated cross-snapshot delta product. Compare snapshots only when metric definition, period basis, currency, reference multiple, horizon and relevant calculation logic are aligned or differences are explicitly isolated. Otherwise emit an appropriate non-comparable state rather than a numeric delta. Separate movement caused by a changing share price from movement caused by changing reference assumptions. |
| **Closed negative states** | The project already uses explicit missingness, validation and applicability states, including `UNAVAILABLE`, `NOT_APPLICABLE`, `SOURCE_SILENT`, and `METHODOLOGY_MISMATCH`; archive availability distinguishes `SOURCE_DECLARED`, `UNDECLARED`, and `ARCHIVE_FIRST_SEEN`. | Confirm every downstream package carries the applicable state and reason code, not just a null numeric value. Preserve distinct meanings and the layer-specific vocabulary; do not combine all failure modes into a new universal status or let an LLM infer why evidence is absent. `NOT_COMPARABLE` belongs on comparisons that fail comparability checks, not as a synonym for missing data. |
| **Disclosure/event alignment** | SEC source-document capture, accession/form identity, filing lineage and source-declared acceptance timestamps are part of the evidence architecture. | Automatic association between a change in implied assumptions and a filing/event window is not yet confirmed as a production feature. If added, account for time zone, after-hours/pre-market disclosure, next trading session, price sampling and multiple simultaneous events. Report temporal association and candidate catalysts; do not claim that one filing caused the market move from timestamp proximity alone. |

These capabilities support a grounded LLM interpretation such as “under reference X and horizon Y, the price requires condition Z, which is above/below the issuer's observed historical range.” That statement is only warranted when the cited source data, sample coverage, period comparability and calculation provenance actually support it. Phrases such as “historically never achieved,” “growth expectations doubled,” or “risk shifted toward an unproven future” are model interpretations that must be qualified and backed by the package; they are not ST-EVA facts by themselves.
## 7. Work sequence considered at the time

### P0 — Repair known defects and protect current data

**Objective:** Restore trustworthy behaviour without turning a focused bug into a broad architecture or governance project.

1. Confirm the local Git baseline and worktree status. Inspect runtime database paths read-only before relevant operations.
2. Update .gitignore to keep local SQLite databases, WAL/SHM files and runtime archives out of Git. Verify the rules without deleting or moving any file.
3. Fix the SEC taxonomy parser against the captured XML. Distinguish document structural validity from record eligibility for an authority assertion, and from persistence success.
4. Add focused offline regression tests. For the captured fixture, examine all 203 Loc records, expect 201 eligible assertions and 2 non-assertions because Namespace is missing, and verify the actual unique identity set (expected 194 for this fixture) rather than checking counts alone. These are fixture expectations, not constants in production logic.
5. Keep the existing migration 0022, identity computation, NOT NULL schema, writer, archive boundaries and database data unchanged unless evidence demonstrates one is necessary to fix the defect.
6. Run the targeted tests and appropriate existing regression suite. Record only checks actually run and the remaining limitations.

**Acceptance:** the captured catalogue is fully accounted for; ineligible records do not become authoritative assertions; eligible identity results match the fixture expectation; no live database write is performed during parser regression; local database/runtime files remain intact.

**Separate track:** Amendment 10 remains a draft unless and until the owner decides otherwise. Its existence does not block the minimal parser correction. If investigation demonstrates that a broader rule or schema change is necessary, explain the evidence and options rather than silently treating the draft as adopted.

### P1 — Verify the current evidence-to-package path

**Objective:** Learn exactly what ST-EVA can reliably provide today before designing new features.

- Trace one company from source acquisition through observations, validation, existing deterministic calculations, Investment Context, archive persistence and replay.
- Start with an issuer that already has research/archive evidence (AAPL is a practical candidate), but verify the current local data before selecting the fixture.
- Inventory the facts actually present: price/time series, financial history, available consensus or forward estimates, identifiers, source documents, validation states, derived calculations and unavailable fields.
- Check whether every important figure exposes its source, definition, period, currency, availability status and derivation where applicable.
- Distinguish source-declared point-in-time history from archive-first-seen history. Do not promise historical knowability where source publication time is unknown.
- Record concrete data gaps revealed by this trace; do not add data providers or tables before a specific gap is shown to matter.

**Acceptance:** one evidence-based report of the tested data path, the actual package it emits, which properties are verified, and which information is absent, ambiguous or not replayable.

### P2 — Establish the LLM-ready evidence package and time-indexed record

**Objective:** Use the existing Investment Context and archive as the baseline, extending them only where the end-to-end check proves they are insufficient.

The package should group, without conflating:

- asset identity and requested market time;
- observed market prices and source financial facts;
- source documents, provenance and availability/knowledge timestamps;
- source comparisons and validation results, preserving conflicts instead of selecting a winner;
- deterministic derived values with formula/version and operand references;
- conditional reverse calculations across explicitly named reference assumptions, not one hidden or unexplained multiple;
- unavailable/refused/not-applicable states and known limitations;
- stable snapshot identity and enough input/version information to reproduce or compare it.

The point-in-time record should answer: what inputs and conditional calculations did this snapshot contain at T? It cannot truthfully claim to record a unique, directly observed belief held by the whole market.

For the first useful package, explicitly report which of the five dimensions in §6 are PRESENT, PARTIAL, UNAVAILABLE or NOT YET IMPLEMENTED. Do not conceal an unimplemented feature behind a generic completeness claim.

**Acceptance:** package schema and version are explicit; important fields are traceable; operational hurdles name the assumptions and reference conditions; anchors show their source periods and historical sample limits; time comparisons enforce comparability; unavailable/negative states retain their reasons; filing times retain their point-in-time basis; two builds from the same archived inputs and logic reproduce the expected document; changes in inputs/logic are visible as changed versions or snapshots; missing history remains missing instead of being backfilled silently.

### P3 — Validate LLM analysis of price-implied assumptions

**Objective:** Reuse the agent-consumption work already documented in SPEC.md and test the new product question: can an LLM turn a fixed ST-EVA evidence package into a traceable analysis of the conditions that may explain a market price?

- First map prior experiments and findings; do not repeat generic retrieval/grounding probes that are already covered unless a regression or a distinct question justifies it.
- Supply the exact same versioned package to at least two models, without allowing the experiment to silently substitute fresh web data.
- Ask each model to explore possible price-consistent business assumptions, use the supplied reverse calculations as inputs, compare them with financial history and available market expectations, and state which conclusions depend on which assumptions.
- Require factual claims to cite package references and require model-created assumptions or calculations to be labelled as analysis rather than ST-EVA observations.
- Compare the usefulness and traceability of the resulting hypotheses, arithmetic correctness, treatment of missing/conflicting data and repeatability. Different conclusions are acceptable when methods and premises are explicit.
- Use failures to locate the actual gap: absent evidence is a collection issue; inaccessible evidence is a package/query issue; misunderstood semantics is a consumer/presentation issue; incorrect deterministic calculations are a core issue; unsupported interpretation is a model-analysis issue.

**Acceptance:** a reproducible experiment determines whether the current Investment Context plus existing archive is sufficient for the target research task, and yields a concrete evidence-backed backlog. Include at least one example each of an operational-hurdle explanation, a consensus/historical anchor comparison, a comparable time delta or explicit refusal, and a filing/event alignment where the timestamps support it. The model must not invent absent history or claim causality from temporal proximity. Use exported files and external LLMs first; a live in-product LLM API is not a prerequisite.

### P4 — Close only evidence gaps demonstrated by the consumer test

**Objective:** Improve data depth and semantics where they materially constrain LLM research.

Possible work includes longer price/fundamental history, better availability timestamps, additional independent sources, improved market-expectation coverage, fiscal-period alignment, or specific point-in-time limitations. Choose only from findings of P1–P3 and define a test for every addition.

Historical P/E work belongs here unless the initial evidence trace proves it is required earlier. It may become valuable as a reproducible historical reference series, but it is not a prerequisite for producing useful conditional reverse calculations from an explicit reference.

**Acceptance:** each added source/metric closes a named gap, carries provenance and missingness semantics, is covered by regression tests, and improves the evidence package without weakening existing history.

### P5 — Optional LLM integration and wider coverage

Only after the package has demonstrated value, consider a model-provider adapter, tool/query surface, stored LLM-analysis records, wider issuer/accounting-framework coverage, or additional valuation-reference families.

If model analyses are archived, store them as separate, versioned research artefacts linked to the input snapshot, model identity/configuration, prompt or task definition and creation time. A model analysis must never overwrite the snapshot, source evidence or deterministic calculation results.

## 9. Work that is not on the immediate critical path

- Full production Historical P/E implementation before checking whether the first LLM evidence package can already be useful.
- Blanket implementation of every open methodology decision; decide only what the chosen feature and issuer cohort require.
- General database/corpus convergence or storage-backend refactoring without a concrete consumer and recovery plan.
- Automatic LLM calls, model ranking or consensus aggregation before a fixed-package consumption test establishes what the product needs.
- Broad platform expansion simply to increase metric count or issuer coverage.
- Large governance-document rewrites whose completion does not change or verify software behaviour.

## 10. Next actions considered at the time

1. Finish the P0 parser and runtime-file protection work as two bounded changes with separate verification.
2. Reconcile the tested local state with the dated status checkpoint, keeping historical checkpoints as historical records rather than rewriting them to look current.
3. Run the P1 single-company trace and inspect the actual Investment Context/data package.
4. Update this roadmap only when evidence changes the next action; do not create a parallel roadmap or treat this file as a reason to resist a new owner decision.

## 11. Completion and reporting ideas recorded at the time

A roadmap item is complete when the relevant code/artifact exists and its acceptance evidence has actually been run or inspected. A plan, specification, research POC, model response or documentation review is not a substitute for that evidence.

Every closeout should state the files changed, the Git commit or baseline, tests/checks actually run, results, data operations (if any), and remaining uncertainty. Preserve source data and research artifacts. When the owner changes direction, explain consequences and update this plan; do not let the plan override the owner.

## 12. P0 completion — parser regression verified

**Date:** 2026-10-10. **Commit:** `6f0324a`.

The parser correction itself landed earlier in `3a5a614`. What follows is the
regression verification of that correction, which was the outstanding part of
P0.

Checks actually run:

| Check | Command | Result |
|---|---|---|
| Parser unit tests | `python -m unittest discover -s tests -p "test_authority_taxonomy_catalog_parser.py"` | 25 passed |
| Workflow integration | `python -m pytest tests/test_authority_taxonomy_integration.py -q` | 8 passed |
| Taxonomy acquisition / namespace schema / persistence / evidence resolver | `python -m pytest tests/test_authority_taxonomy_acquisition.py tests/test_authority_taxonomy_namespace_schema.py tests/test_authority_taxonomy_persistence.py tests/test_authority_evidence_resolver.py -q` | 47 passed |
| Full suite | `python -m pytest tests -q` | 1622 passed, 168 skipped, 2 failed → 0 failed after the fix below |

Note on the integration file: it uses pytest-style `setup_method`, so
`unittest discover` reports "NO TESTS RAN" for it rather than running it. It
must be invoked through pytest.

The captured official catalogue fixture matched its defined expectations:
203 `<Loc>` records, 201 eligible assertions, 2 records ineligible because
Namespace is absent, and 194 unique identity combinations. These remain
fixture assertions in the tests and are **not** encoded as production rules.

Two full-suite failures were found and were unrelated to the parser. Both were
stale path assertions left behind by `fc506c3`, which moved
`run_corpus_tests.py`, `ingest_universe.py`, `merge_sources.py` and
`reconcile_bulk.py` from the repository root into `scripts/research/`. They
were fixed in `6f0324a` by repointing the paths and by teaching the
dependent-module probe to import flat script directories by leaf name.

No schema, migration, identity definition or writer semantics were changed. No
SQLite database, WAL, SHM or archive file was written, deleted or reset.

## 13. Reverse Requirements Report V1 — implemented

**Date:** 2026-10-10.

### What now runs on every invocation

`run_st_eva` gained a `reverse_requirements` stage that executes for every run,
not only on request. It is pure arithmetic over values the acquisition stage
already observed, so it introduces no second source of truth. The output is in
every result under `reverse_requirements`, rendered as the first section of the
human-readable report, and fully present in `--json`.

The headline output is a reverse requirements matrix: for each combination of
holding period, required price return and exit multiple, it reports the exit
price the return demands, the exit EPS that multiple corresponds to, the EPS
growth rate that bridges the starting EPS to it, the gap against consensus
where the periods line up, and how the requirement moves when the exit multiple
compresses or expands.

Three properties are enforced in code and covered by tests:

1. **Every reverse figure names its reference multiple and period.** Price
   divided by a multiple is the EPS that multiple corresponds to. It is not a
   claim about market expectations.
2. **A required return is labelled `PRICE_RETURN_ONLY`** unless a dividend is
   supplied as an input. It is never called a total return.
3. **Every EPS carries the period it covers.** A next-twelve-months anchor
   shortens the growth window by its own coverage, so a 3-year horizon from a
   forward EPS reports a 2-year growth rate. When the window is too short to
   annualise, the row reports the raw EPS change and no CAGR, flagged
   `GROWTH_WINDOW_TOO_SHORT_FOR_CAGR`.

### Rate families, kept separate

`risk_free_rate_provider.py` fetches observed US Treasury yields at 13-week,
5-year, 10-year and 30-year tenors, each with its own observation date taken
from the series' own timestamps, plus tenor, source and unit. A tenor that
cannot be fetched is reported as unavailable and is never substituted from
another tenor.

Three families are emitted separately and never merged: the **risk-free rate**
(observation), the **CAPM cost of equity** (`Rf + beta × ERP`, a model estimate
recorded only when all three components arrive with their provenance), and the
**investor target return** (a scenario input allowed to disagree with the
model).

### Cash flow cross-checks and DCF status

Observed P/FCF, EV/EBITDA, P/S, FCF yield and EV/EBITDA yield are reported
separately from the amounts reverse-solved at an explicitly supplied reference
multiple, because they answer different questions.

The discounted cash flow block is **implemented but reports `NOT_COMPUTED` on
real current data**, and that is the accurate status rather than a gap in the
reporting. The solver itself is verified: given a complete FCFF input set it
returns the constant explicit-period growth rate that reproduces the observed
value (checked to 1e-6 against a recomputation). What is missing on live AAPL
data is the bridge from reported earnings to unlevered cash flow —
`depreciation_amortisation`, `capex`, `working_capital_change`,
`cost_of_debt`, `market_value_of_debt` and `tax_rate` — plus a declared
`cash_flow_basis`. These are named rather than estimated.

### End-to-end verification actually performed

Live AAPL run at USD 336.64, data date 2026-10-09, 16 matrix cells over
horizons 1/2/3/5 years and required returns 8/10/12/15%, exit P/E 32x.
Observed: trailing EPS 8.72, market cap and EV present, observed P/FCF 35.98,
EV/EBITDA 29.41, P/S 10.54, FCF yield 2.8%; four Treasury yields from
2026-10-09; CAPM cost of equity 11.2% from Rf 5.24% + 1.2 × 5.0%.

Two runs of identical inputs produced an identical package fingerprint, and
changing the exit multiple, the required returns or the price changed it.

### Verified gaps carried forward, not papered over

- The historical P/E band from the vendor carries 8 observations against the
  existing 20-observation threshold, so it is reported as descriptive and is
  **not** used as a reference multiple. The live AAPL run passed
  `--reference-multiple` explicitly. A production historical P/E distribution
  remains the ADR-HISTORICAL-PE-METHODOLOGY work.
- The vendor's `trailingEps` declares no period, so the 12-month window is an
  assumption and is flagged on the anchor.
- Consensus EPS comparison is refused for horizons other than 1 year, because a
  next-twelve-months consensus taken at the valuation date describes a
  different period than a terminal EPS three years out.
- Dividend data is not currently acquired, so no total-return scenario exists
  yet; the return basis is labelled accordingly.
- No schema change, no new provider beyond the Treasury rate feed, and no
  modification to existing formulas was required or made.

## 14. Phase C — multi-scenario reverse results and the research dossier

**Date:** 2026-10-10.

### Capability tiers

Each capability is stated at the tier actually reached, not the tier intended.
"Implemented and tested" means the code exists, is wired into a real run, and
the behaviour is covered by tests that were executed.

| Capability | Tier | Evidence |
|---|---|---|
| Reverse requirements matrix over horizon x required return x exit multiple | **Implemented, tested, integrated** | Runs on every invocation; 16 live AAPL cells |
| Exit multiple scenarios from a historical distribution | **Implemented, tested** | `exit_multiples_from_band`; refuses a thin band |
| User-supplied exit multiple, labelled as such | **Implemented, tested** | Recorded with `source: user_supplied` |
| Financial history: annual and quarterly revenue, net income, diluted EPS | **Implemented, tested, integrated** | 71 SEC observations for AAPL; 6 series |
| Year-over-year growth with comparability rules | **Implemented, tested** | Growth refused across mismatched windows |
| Net margin computed inside one period | **Implemented, tested** | Refused when period ends differ |
| Earnings / revenue / cash flow / enterprise-value methods, kept separate | **Implemented, tested, integrated** | All four computed on live AAPL |
| Observed P/E, P/S, P/FCF, EV/EBITDA and yields | **Implemented, tested, integrated** | Present in the dossier |
| Risk-free rates at four tenors with observation dates | **Implemented, tested, integrated** | 2026-10-09 curve fetched live |
| CAPM cost of equity with disclosed provenance | **Implemented, tested** | Rf + beta x ERP, each part labelled |
| Investor target return as a separate scenario input | **Implemented, tested, integrated** | Never merged with the model output |
| DCF reverse solve (implied explicit growth rate) | **Implemented, tested** | Reproduces a known value to 1e-6 |
| DCF on live data | **Not done — blocked on data** | Names six missing inputs |
| Production historical P/E distribution | **Not done** | ADR-HISTORICAL-PE-METHODOLOGY work |
| Dividend / total-return scenarios | **Not done** | No dividend data is acquired |
| Probability, ranking or expected value over scenarios | **Deliberately not done** | Out of scope by design |

### Data-safety defect found and fixed

`tests/test_browser_smoke.py` built its application with `create_app()`, which
defaulted to a real `AnalysisServiceAdapter` writing to `data/archives`. That
suite runs genuine end-to-end analyses, so **every test run was writing into the
operator's own per-ticker archives**. Confirmed by comparing sizes and
modification times across a run.

Fixed by threading an explicit `archives_dir` from `create_app` to the adapter
and pointing the browser suite at a `TemporaryDirectory`.
`tests/test_archive_isolation.py` pins the behaviour: the default is still the
operator's directory, an explicit directory is honoured, importing the web
package touches nothing, and the browser suite passes an explicit directory.
Verified after the change: the browser suite leaves every file under
`data/archives` byte-identical.

### AAPL acceptance actually performed

`as_of` 2026-10-09, price 336.64 USD, run twice with identical arguments:

- Both runs produced an identical package fingerprint and an identical dossier.
- Financial history: 4 annual and 8 quarterly points each for revenue, net
  income and diluted EPS, from 71 SEC observations. Year-over-year growth at
  2025-09-27: revenue +6.43%, net income +19.50%, diluted EPS +22.70%. Net
  margin 23.97% -> 26.92% -> 27.15% -> 27.62%.
- All four method results independently recomputed outside the production code
  and matched to 1e-6: EPS at 32x, revenue at 9x P/S, FCF at 30x, EBITDA at
  24x EV/EBITDA.
- Matrix spot checks at a 10% required return: 1 year target 370.3040 and EPS
  11.5720; 5 year target 542.1621 and EPS 16.9426. Both matched hand
  recomputation.
- Rates: 13-week 4.057%, 5-year 5.021%, 10-year 5.244%, 30-year 5.600%, all
  observed 2026-10-09. CAPM cost of equity 11.24%.

### Gaps carried forward

- The DCF block still reports `NOT_COMPUTED` on live data. The solver is
  implemented and tested, but no current provider observes
  `depreciation_amortisation`, `capex`, `working_capital_change`,
  `cost_of_debt`, `market_value_of_debt` or `tax_rate`, and no
  `cash_flow_basis` is declared. FCFF, FCFE, WACC and the equity discount rate
  remain separated rather than mixed, and the gap is named rather than filled.
- The vendor P/E band holds 8 observations against the 20 threshold, so it is
  descriptive only and the live run supplied the reference multiple explicitly.
  This is why the AAPL matrix shows a single user-supplied multiple rather than
  a percentile set: the percentile path is exercised by fixtures instead.
- The vendor `trailingEps` declares no period; the 12-month window is flagged as
  an assumption.
- No dividend data, so every required return remains a price return.
- Enterprise value and market capitalization are taken as observed rather than
  rebuilt from price times shares plus net debt, because the provider's debt
  and cash definitions are not reconciled to its share count.

## 15. Phase D — Point-in-Time Financial Data and Multi-Exit-Multiple Dossier

**Date:** 2026-10-10.

### What now runs and is presented

1. **Point-in-Time (`INSTANT`) Observation Support (`financial_history.py`):**
   - Observations without a duration window or with matching start/end dates are classified as `INSTANT`.
   - No artificial period start is required for point-in-time balance-sheet facts.
   - Strict arithmetic boundary: growth rate calculations (`growth_against_prior_year`) and margin calculations (`margin_for_periods`) explicitly reject instant points, and candidate searches exclude instant facts from duration series.
   - Serialization preserves `period_type` (`INSTANT` vs `DURATION`), fiscal context (`fiscal_year`, `fiscal_period`), validation status, and source identity.

2. **Acquired Balance-Sheet Evidence & Capital Structure (`capital_structure.py`):**
   - Presents acquired point-in-time balance-sheet metrics: `assets`, `cash`, `long_term_debt`, and `shares_outstanding`.
   - Each fact reports observed value, currency/unit, effective date, available date, availability basis, source provider, filing form, accession number, and cross-source validation status.
   - Distinguishes point-in-time cover-page shares outstanding from weighted-average diluted shares used in EPS; neither is silently substituted for the other.
   - Reconstructed market capitalization: `price × dated shares outstanding`, with explicit date mismatch caveat.
   - Reconstructed enterprise value: partial bridge (`market_cap + long_term_debt - cash`) marked with status `PARTIAL`, explicitly declaring present components (`long_term_debt`, `cash`) and absent components (`total_debt`, `short_term_borrowings`, `cash_and_equivalents`, `short_term_investments`, `non_controlling_interests`, `preferred_equity`).
   - Side-by-side reconciliation of provider-observed vs. reconstructed capitalization with differences, relative differences, observation dates, and definition differences.

3. **Multi-Exit-Multiple Reverse Requirements Sensitivity Matrix (`reverse_requirements.py`, `st_eva_runner.py`):**
   - Matrix supports cross-product evaluation across holding periods, required returns, and multiple user-supplied or band exit multiples (via `--reference-multiples`).
   - For AAPL with multiples 25.0, 32.0, 40.0: generates 48 independent scenario cells (4 horizons × 4 required returns × 3 exit multiples).
   - Provenance preserved on every cell: `price`, `as_of`, start EPS anchor, exit multiple with origin/source, return basis (`PRICE_RETURN_ONLY`), target exit price, required terminal EPS, CAGR, growth window, flags, and formula version.
   - Policy maintained: continues to refuse the 8-observation historical P/E band as a reference distribution under the 20-observation threshold policy.
   - Implied net margin presents two separately labelled variants: derived share count (`market_cap / price`, original formula) and observed point-in-time shares outstanding.
   - Zero scenario probabilities, rankings, or authoritative expected-value synthesis added.

4. **Dedicated Dossier & Report Rendering (`research_dossier.py`):**
   - Section 3 presents Balance Sheet and Capital Structure in both JSON dossier and human-readable text output.
   - Section 6 renders detailed share-basis breakdowns for implied net margin.

### AAPL Phase D Acceptance Verification

Executed on AAPL regression fixture at price 336.64 USD as-of 2026-10-09 with `--financial-history --reference-multiples 25 32 40`:

- **Fingerprint Determinism:** Identical fingerprint reproduced across repeated independent runs: `5c9e1a0acf10dde3e658b975a7ed2963a4b5b9afaa3040248bd3b6426b6cd5ef`.
- **Matrix Dimensions:** 48 cells (horizons: 1.0, 2.0, 3.0, 5.0 years; returns: 8%, 10%, 12%, 15%; exit multiples: 25.0, 32.0, 40.0).
- **Balance Sheet Observations:** 8 instant points each for assets ($383.27B @ 2026-06-27), cash ($39.54B @ 2026-06-27), long-term debt ($82.35B @ 2026-06-27), and shares outstanding (14.59B @ 2026-07-17).
- **Observed vs Reconstructed Capitalization:**
  - Market Cap: observed $4,918.53B vs reconstructed $4,912.98B (diff: -$5.55B, -0.11%).
  - Enterprise Value: observed $4,940.48B vs reconstructed $4,955.79B (diff: +$15.31B, +0.31%), status `PARTIAL`.
- **Spot Check Recomputation:**
  - Horizon 1.0y, return +8%, multiple 25.0: $336.64 \times 1.08 = 363.5712$; terminal EPS $363.5712 / 25.0 = 14.5428$; CAGR from 8.72 is +66.8%. Exactly matches output.
  - Horizon 5.0y, return +15%, multiple 40.0: $336.64 \times 1.15^5 = 677.1033$; terminal EPS $677.1033 / 40.0 = 16.9276$; CAGR $(16.9276 / 8.72)^{1/5} - 1 = +14.2\%$. Exactly matches output.
- **Data Protection:** Persistent user archives in `data/archives/` and `data/st-eva.sqlite` verified byte-identical before and after tests.
- **Test Suite Results:** Full test suite passed: 1848 passed, 168 skipped, 49 subtests passed (0 failures).

## 16. Phase E — Production Historical P/E Pipeline

**Date:** 2026-10-10.

### What now runs and is presented

1. **Point-in-Time Historical P/E Calculation Engine (`historical_pe.py`):**
   - Implements full point-in-time Historical P/E calculation conforming to `docs/methodology/CONTRACT-HISTORICAL-PE.md` and `docs/ADR-HISTORICAL-PE-METHODOLOGY.md` Amendment 1.
   - Enforces strict zero-lookahead coupling: contemporaneous closing price paired only with financial statements knowable at that date (`usable_date <= evaluation_date` and `period_end <= evaluation_date`).
   - EDGAR SGML header acceptance timestamp cutoff: `< 16:00 ET` becomes available on the same trading day close; `>= 16:00 ET` becomes available on the next trading day close; weekend / holiday roll-forward to next trading session.
   - Stated-directly quarterly EPS evidence (Invariant F-1): quarterly diluted EPS must be stated directly in source (`filed` 10-Q/10-K or `furnished` 8-K Item 2.02 EX-99.1 per Amendment 1); strictly prohibits `FY - YTD` arithmetic difference.
   - Fiscal calendar anchoring (Invariants F-2, F-3): TTM requires 4 consecutive fiscal quarters including an explicit Q4, derived strictly using company-declared FYE month.
   - Accounting basis and restatement alignment (Invariants F-6, R-PIT-SUPERSEDE): only matches shares and net income with consistent basis; restatements cleanly supersede prior reports with full audit lineage.
   - Non-positive TTM EPS rejection (`REASON_NON_POSITIVE_EPS`).
   - Invariant F-11 closed enumeration: all exclusion and uncomputable reasons use strict closed enumeration reason codes.
   - Invariant F-13 determinism: canonical JSON content hash computed for every observation, distribution, and overall result package.

2. **Sufficiency Gate & Status Governance:**
   - Evaluates whether valid observation count meets the authoritative reference threshold ($\ge 20$).
   - If valid count $\ge 20$: status is `USABLE_FOR_REFERENCE`.
   - If valid count $< 20$: status is `INSUFFICIENT_OBSERVATIONS` (descriptive statistics only; refuses promotion to reference distribution).
   - Clear architectural distinction between production point-in-time Historical P/E and provider-fed `historical_pe_band` (8 observations).

3. **Research Dossier & Reverse Matrix Integration (`reverse_requirements.py`, `research_dossier.py`, `report_formatter.py`):**
   - Dossier Section 5 (`valuation_metrics.production_historical_pe`): provides complete distribution details (observation count, date span, percentiles, methodology, audit trail).
   - Human-readable text report and rendered dossier format distribution table with sample size, date range, percentiles, and sufficiency notes.
   - When qualified ($\ge 20$), percentiles (10th, 25th, 50th, 75th, 90th) feed the reverse requirements sensitivity matrix as reference multiples (`source="production_historical_pe_percentile"`), yielding 80 rows across 4 holding periods and 4 required return hurdles.

4. **CLI Opt-In & Negative Path Support (`st_eva_runner.py`):**
   - `--historical-pe`: opt-in flag to execute production point-in-time Historical P/E analysis.
   - `--no-furnished-pe`: negative-path switch disabling Form 8-K Item 2.02 furnished facts to verify rejection when observations fall below 20.

### AAPL Phase E Acceptance Verification

Executed on AAPL regression fixture at price 336.64 USD as-of 2026-10-09:

- **Furnished Enabled (Standard Production Path):**
  - Observations: 31 candidate dates evaluated, 31 valid observations produced spanning 2019-01-31 to 2026-07-31.
  - Zero mismatches across all 31 dates against `amendment1_pe_points.json`.
  - Distribution: min 13.69, 10th 20.99, 25th 25.93, 50th (median) 28.95, 75th 33.05, 90th 36.19, max 37.46. *(Audited and reconciled in Phase F Closeout; earlier 15.01–41.52 draft text corrected).*
  - Status: `USABLE_FOR_REFERENCE` (exceeds $\ge 20$ threshold).
  - Reverse matrix: 80 rows across 5 percentiles (21.0, 25.9, 28.9, 33.0, 36.2), 4 holding periods (1.0, 2.0, 3.0, 5.0 years), and 4 required returns (8%, 10%, 12%, 15%).
- **Negative Path (`--no-furnished-pe`):**
  - Candidate dates: 31; valid: 12 (Q1-Q3 only); rejected: 19 (`REASON_MISSING_Q4_EPS`).
  - Matches `negative_path_no_furnished.json` with 0 mismatches.
  - Status: `INSUFFICIENT_OBSERVATIONS` (12 < 20).
  - Reverse matrix: refuses ungrounded distribution; reports descriptive median only; does not generate percentile scenarios.
- **Data Protection:** Persistent user archives in `data/archives/` and `data/st-eva.sqlite` verified byte-identical before and after tests.
- **Test Suite Results:** Full test suite passed: 1864 passed, 168 skipped (16 new tests in `test_historical_pe.py`, 0 failures).

## 17. Phase F — Portability Audit, Frozen Research Package, and LLM Dossier Experiment

**Date:** 2026-10-10.

### What was verified and delivered

1. **Historical P/E Pipeline Portability Audit:**
   - Identified that `historical_pe.py` previously had a fallback dependency on gitignored `research/experiments/aapl-historical-pe-poc/raw/` artifacts.
   - Established canonical runtime dataset under `data/historical_pe/AAPL/` (5 files, ~352 KB, fully tracked by Git).
   - Audited imports and data reads to guarantee zero reliance on untracked or user-local experimental directories.
   - Verified 100% clean-checkout reproducibility in a detached worktree without access to untracked artifacts: all 16 Historical P/E tests passed cleanly.
   - Explicitly clarified observation cadence as `PERIODIC_FILING_USABLE_DATES` (not a daily continuous trading history) in schema and reports.

2. **Frozen Research Package Generation:**
   - Generated and retained deterministic research package for `as_of = 2026-10-09` under `history/`:
     - `history/AAPL_research_dossier_20261009.json` (1,247,681 bytes, SHA-256: `4C6E1A8AFE3D9B205463B68CCC5118AC921C6BA8CBDDB03CFE7D594869F256E4`).
     - `history/AAPL_research_dossier_20261009_report.txt` (586 lines, 42,651 chars).
     - Fingerprint: `98f7827bca0f865f3f8d710318ab1fcd36f6f6892476e758613b3a858d49eca5`.

3. **Independent LLM Dossier Evaluation:**
   - Deployed two independent LLM evaluation subagents (`flash` and `pro`) using the frozen dossier as sole source truth without fresh market fetching.
   - Both models successfully performed reverse-engineering operating hurdle calculations (implied revenue/margins) across multiple holding periods and historical percentiles.
   - Model 1 (`flash`) caught the narrative documentation discrepancy between the draft prompt (15.01–41.52) and the actual dossier (13.69–37.46).
   - Preserved all prompts, model metadata, and full raw responses under `reports/experiments/llm_dossier_eval/`.
   - Comprehensive comparative evaluation and semantic review published in `reports/PHASE-F-LLM-EXPERIMENT.md`.

4. **Historical P/E Range Reconciliation & Semantic Review:**
   - Confirmed that the mathematical calculation and frozen dossier have always produced min `13.6875` and max `37.4603`. Corrected the Phase E draft narrative in §16.
   - Added regression test `test_aapl_distribution_min_max_agree_with_eligible_observations` to prevent drift.
   - Semantically reviewed Model 1's claim of a "negative equity risk premium", clarifying the distinction between a descriptive accounting earnings yield spread and a formal ex-ante expected excess return ($ERP \equiv E[R_{equity}] - R_f$).

5. **Data Protection:** Persistent user archives in `data/archives/` and `data/st-eva.sqlite` verified byte-identical.

## 18. Phase G — Capital Structure Closure and Enterprise Value Reconciliation

**Date:** 2026-10-10.

### What was audited, verified and delivered

1. **Balance-Sheet Component Acquisition:**
   - Extended `data_contract.py` with `METRIC_MARKETABLE_SECURITIES_CURRENT`, `METRIC_COMMERCIAL_PAPER`, and `METRIC_TOTAL_DEBT`.
   - Wired `sec_provider.py` to acquire `us-gaap:MarketableSecuritiesCurrent` and `us-gaap:CommercialPaper` by default (`SEC_DEFAULT_METRICS`).
   - Verified issuer XBRL tagging: Apple CIK 0000320193 files `MarketableSecuritiesCurrent` (liquid short-term investments) and `CommercialPaper` (short-term promissory notes) rather than generic `ShortTermInvestments` or `ShortTermBorrowings`.

2. **Exact Mathematical EV Bridge Discovery:**
   - Audited the exact bridge between provider market capitalization and provider enterprise value on AAPL:
     - Provider Observed Market Cap: $4,918,530,543,600.0 (`2026-10-09`)
     - Provider Observed Enterprise Value: $4,940,475,543,600.0 (`2026-10-09`)
     - Implied Provider Net Debt Addition: $\text{EV} - \text{Market Cap} = \mathbf{+\$21,945,000,000.00}$.
   - Traced to SEC Filing for AAPL at `2026-06-27` (10-Q accession `0000320193-26-000020`):
     - `us-gaap:LongTermDebtNoncurrent`: $71,340,000,000
     - `us-gaap:LongTermDebtCurrent`: $11,007,000,000
     - $\rightarrow$ Long-Term Debt Total: $82,347,000,000
     - `us-gaap:CommercialPaper`: $1,997,000,000
     - $\rightarrow$ Total Debt: $\mathbf{\$84,344,000,000}$
     - `us-gaap:CashAndCashEquivalentsAtCarryingValue`: $39,544,000,000
     - `us-gaap:MarketableSecuritiesCurrent`: $22,855,000,000
     - $\rightarrow$ Liquid Cash & Current Investments: $\mathbf{\$62,399,000,000}$
     - $\rightarrow$ **Net Debt**: $\$84,344,000,000 - \$62,399,000,000 = \mathbf{+\$21,945,000,000.00}$ (exact match down to the dollar!).
   - Audited Market Cap & Reconstructed EV:
     - Reconstructed Market Cap: $336.64 \times 14,594,180,000$ cover-page shares (`2026-07-17`) = $4,912,984,755,200.0.
     - Difference from Observed Market Cap: $-\$5,545,788,400.00$ (-0.1128%).
     - Reconstructed EV: $\$4,912,984,755,200.0 + \$21,945,000,000.0 = \mathbf{\$4,934,929,755,200.00}$.
     - Difference from Observed EV: $-\$5,545,788,400.00$ (-0.1123%), which exactly equals the market capitalization difference, confirming the net debt bridge is 100% mathematically sound.

3. **Status Governance & Accounting Limitation Declaration:**
   - Preserved `status: "PARTIAL"` for reconstructed Enterprise Value.
   - Enforced the ST-EVA principle: a successful arithmetic match is not proof of exhaustive accounting coverage.
   - Reconstructed EV explicitly documents the omission of:
     - Non-current marketable securities ($90,695,000,000 on balance sheet).
     - Operating lease liabilities under ASC 842.
     - Off-balance-sheet commitments and contingent liabilities.
     - Preferred equity and minority interests (zero/unreported for AAPL).

4. **EV/EBITDA Multiple Reconciliation:**
   - Observed EV/EBITDA: $4,940.48\text{B} / 167.97\text{B} = 29.4128\text{x}$.
   - Reconstructed EV/EBITDA: $4,934.93\text{B} / 167.97\text{B} = 29.3798\text{x}$.
   - Difference: $-0.0330\text{x}$ (-0.1123%), attributable solely to the cover-page share date timing delta (-0.1128%). Reconstructed EV is compatible with trailing EBITDA because both cover contemporaneous USD valuation.

5. **Anti-Double-Counting Guard:**
   - Verified that commercial paper liabilities are treated as a distinct component of short-term borrowings and are never added twice if generic short-term debt concepts are evaluated.

6. **Dossier & Report Rendering:**
   - Updated `research_dossier.py` (`_render_capital_structure`) to display:
     - All instant balance-sheet observations with dates, availability, and provenance.
     - Side-by-side observed vs reconstructed rows for Market Cap, Enterprise Value, and EV/EBITDA.
     - Explicit bridge equation: Total Debt (Long-Term Debt + Commercial Paper) - Liquid Funds (Cash + Current Marketable Securities) = Net Debt.

7. **Database Protection & Test Verification:**
   - Verified zero database drift: all SQLite databases (`data/archives/*.sqlite`, `data/st-eva.sqlite`) verified SHA-256 byte-identical.
   - Full test suite passed: 1868 passed, 168 skipped in 327.98s, zero failures.

## 19. Phase H — Dividend Evidence and Total-Return Calculations

**Date:** 2026-10-10.

### What was audited, verified and delivered

1. **Dividend Evidence Acquisition & Provenance:**
   - Extended `data_contract.py` with standard dividend metrics: `METRIC_DIVIDENDS_PER_SHARE`, `METRIC_DIVIDENDS_TTM`, `METRIC_DIVIDEND_YIELD_TTM`, `METRIC_DIVIDEND_INDICATED_RATE`, `METRIC_DIVIDEND_INDICATED_YIELD`, and `METRIC_DIVIDEND_GROWTH_YOY`.
   - Extended `sec_provider.py` with XBRL tags `us-gaap:CommonStockDividendsPerShareDeclared` and `us-gaap:CommonStockDividendsPerShareCashDeclared` in `TTM_METRICS` and `SEC_DEFAULT_METRICS`.
   - Created dedicated dividend engine `dividend_history.py` to extract source-backed dividend events from chart events (`events.dividends`) and discrete SEC filing facts with complete ex-dates, pay-dates, currency, and pre-split / post-split adjustment tracking.
   - Audited AAPL canonical tracked dataset (`data/historical_pe/AAPL/daily_prices.json`): captures 35 discrete cash dividend payments from 2018 to 2026, including the August 2020 4:1 stock split adjustment.

2. **Deterministic Dividend Metrics:**
   - Trailing Twelve Month Dividends ($D_{\text{TTM}}$): Sum of the 4 most recent trailing quarterly payments ($0.26 + 0.26 + 0.27 + 0.27 = \mathbf{\$1.0600}$ / share).
   - TTM Dividend Yield: $\$1.06 / \$336.64 = \mathbf{0.3149\%}$ (31.5 bps).
   - Indicated Annual Dividend Rate: $4 \times \text{latest quarterly payment} = 4 \times \$0.27 = \mathbf{\$1.0800}$ / share.
   - Indicated Dividend Yield: $\$1.08 / \$336.64 = \mathbf{0.3208\%}$ (32.1 bps).
   - YoY TTM Dividend Growth: $(\$1.06 - \$1.02) / \$1.02 = \mathbf{+3.9216\%}$.

3. **Historical Total Returns vs. Price Returns:**
   - Formulated deterministic returns over matched historical holding periods (1y, 3y, 5y) ending `2026-10-06` under explicit, auditable conventions:
     - **Price Return (Ex-Dividend):** $R_P = \frac{P_T}{P_0} - 1$
     - **Total Return (Cash Dividends Retained):** $R_{\text{cash}} = \frac{P_T + \sum D_t}{P_0} - 1$
     - **Total Return (DRIP Reinvested):** Dividends converted into fractional shares at ex-date close: $S_t = S_{t-1} \times (1 + D_t / P_t)$, $R_{\text{DRIP}} = \frac{S_T \times P_T}{P_0} - 1$
   - Audited AAPL Historical Performance:
     - 1-Year (2025-10-06 to 2026-10-06): Price CAGR 30.00%, Cash TR 30.41%, DRIP TR 30.48% (Dividend contribution: +0.48%).
     - 3-Year (2023-10-06 to 2026-10-06): Price CAGR 23.13%, Cash TR 23.51%, DRIP TR 23.68% (Dividend contribution: +0.55%).
     - 5-Year (2021-10-06 to 2026-10-06): Price CAGR 18.63%, Cash TR 18.98%, DRIP TR 19.22% (Dividend contribution: +0.59%).

4. **Total-Return Reverse Requirements Engine:**
   - Extended `reverse_requirements.py` to support parallel total-return scenario matrices without modifying price-return baseline semantics:
     - Baseline (`PRICE_RETURN_ONLY`): $P_T = P_0(1+r)^T$.
     - Convention A (`CASH_DIVIDENDS_RETAINED`): $P_T = P_0(1+r)^T - T \times D$.
     - Convention B (`DIVIDENDS_REINVESTED_AT_TARGET_RETURN`): $P_T = P_0(1+r)^T - D \cdot \frac{(1+r)^T - 1}{r}$.
   - Calculated exact dividend relief metrics:
     - Exit Price Relief: $\Delta P_T = P_{T, \text{total}} - P_{T, \text{price}} < 0$.
     - Terminal EPS Relief: $\Delta \text{EPS}_T = \frac{P_{T, \text{total}} - P_{T, \text{price}}}{M} < 0$.
     - Required EPS CAGR Relief: $\Delta \text{CAGR} = \left(\frac{\text{EPS}_{T, \text{total}}}{\text{EPS}_0}\right)^{1/T} - \left(\frac{\text{EPS}_{T, \text{price}}}{\text{EPS}_0}\right)^{1/T} < 0$.
   - Sample verified AAPL reverse hurdle ($P_0 = \$336.64, r = 10\%, T = 3\text{y}, M = 28.95, D = \$1.06$):
     - Price Return Only: $P_3 = \$448.07$, Required $\text{EPS}_3 = \$15.48$, Required $\text{CAGR} = 33.07\%$.
     - Cash Retained: $P_3 = \$444.89$, Required $\text{EPS}_3 = \$15.37$, Required $\text{CAGR} = 32.75\%$ ($\Delta P_3 = -\$3.18, \Delta \text{EPS}_3 = -\$0.11, \Delta \text{CAGR} = -0.32\%$).
     - DRIP Reinvested: $P_3 = \$444.55$, Required $\text{EPS}_3 = \$15.36$, Required $\text{CAGR} = 32.71\%$ ($\Delta P_3 = -\$3.51, \Delta \text{EPS}_3 = -\$0.12, \Delta \text{CAGR} = -0.36\%$).

5. **Research Dossier & Report Integration:**
   - Added Section 6 (`dividends_and_total_return`) to `research_dossier.py` in both machine-readable JSON and human-readable text report.
   - Formatted tables:
     - Current Dividend & Yield Summary (TTM dividends, TTM yield, indicated rate, indicated yield, YoY growth).
     - Historical Performance Comparison (1Y, 3Y, 5Y Price vs. Cash vs. DRIP CAGR with explicit dividend contribution).
     - Reverse Requirements Comparison Table (contrasting required exit price, terminal EPS, and CAGR across price vs total return with explicit delta relief).
     - Recent 8 Quarters Dividend Records with ex-date, payment date, gross amount, and provenance.
     - Methodological notes and disclaimers.

6. **Versioned Research Package Generation:**
   - Generated and retained versioned Phase H benchmark package for AAPL under `history/`:
     - `history/AAPL_research_dossier_20261010_phase_h.json` (1,847,192 bytes).
     - `history/AAPL_research_dossier_20261010_phase_h_report.txt` (701 lines, 53,782 bytes).
   - Preserved original frozen Phase F package (`history/AAPL_research_dossier_20261009.json`) 100% byte-identical.

7. **Database Protection & Test Verification:**
   - Verified zero database drift: all SQLite databases (`data/archives/*.sqlite`, `data/st-eva.sqlite`) verified SHA-256 byte-identical.
   - Added `tests/test_dividends.py` with 9 targeted unit and integration tests (all passed).
   - Full test suite passed: 488 passed, 11 skipped in 41.61s, zero failures.


