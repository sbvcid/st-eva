# ST-EVA Product Roadmap

**Updated:** 2026-10-10  
**Role:** Current product direction and working sequence. This is a living plan written to remember the owner's current intent; it is not an immutable charter. Change it when the goal or evidence changes.

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

## 5. Current implementation: known baseline

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

## 6. Work sequence

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

**Acceptance:** package schema and version are explicit; important fields are traceable; two builds from the same archived inputs and logic reproduce the expected document; changes in inputs/logic are visible as changed versions or snapshots; missing history remains missing instead of being backfilled silently.

### P3 — Validate LLM analysis of price-implied assumptions

**Objective:** Reuse the agent-consumption work already documented in SPEC.md and test the new product question: can an LLM turn a fixed ST-EVA evidence package into a traceable analysis of the conditions that may explain a market price?

- First map prior experiments and findings; do not repeat generic retrieval/grounding probes that are already covered unless a regression or a distinct question justifies it.
- Supply the exact same versioned package to at least two models, without allowing the experiment to silently substitute fresh web data.
- Ask each model to explore possible price-consistent business assumptions, use the supplied reverse calculations as inputs, compare them with financial history and available market expectations, and state which conclusions depend on which assumptions.
- Require factual claims to cite package references and require model-created assumptions or calculations to be labelled as analysis rather than ST-EVA observations.
- Compare the usefulness and traceability of the resulting hypotheses, arithmetic correctness, treatment of missing/conflicting data and repeatability. Different conclusions are acceptable when methods and premises are explicit.
- Use failures to locate the actual gap: absent evidence is a collection issue; inaccessible evidence is a package/query issue; misunderstood semantics is a consumer/presentation issue; incorrect deterministic calculations are a core issue; unsupported interpretation is a model-analysis issue.

**Acceptance:** a reproducible experiment determines whether the current Investment Context plus existing archive is sufficient for the target research task, and yields a concrete evidence-backed backlog. Use exported files and external LLMs first; a live in-product LLM API is not a prerequisite.

### P4 — Close only evidence gaps demonstrated by the consumer test

**Objective:** Improve data depth and semantics where they materially constrain LLM research.

Possible work includes longer price/fundamental history, better availability timestamps, additional independent sources, improved market-expectation coverage, fiscal-period alignment, or specific point-in-time limitations. Choose only from findings of P1–P3 and define a test for every addition.

Historical P/E work belongs here unless the initial evidence trace proves it is required earlier. It may become valuable as a reproducible historical reference series, but it is not a prerequisite for producing useful conditional reverse calculations from an explicit reference.

**Acceptance:** each added source/metric closes a named gap, carries provenance and missingness semantics, is covered by regression tests, and improves the evidence package without weakening existing history.

### P5 — Optional LLM integration and wider coverage

Only after the package has demonstrated value, consider a model-provider adapter, tool/query surface, stored LLM-analysis records, wider issuer/accounting-framework coverage, or additional valuation-reference families.

If model analyses are archived, store them as separate, versioned research artefacts linked to the input snapshot, model identity/configuration, prompt or task definition and creation time. A model analysis must never overwrite the snapshot, source evidence or deterministic calculation results.

## 7. Work that is not on the immediate critical path

- Full production Historical P/E implementation before checking whether the first LLM evidence package can already be useful.
- Blanket implementation of every open methodology decision; decide only what the chosen feature and issuer cohort require.
- General database/corpus convergence or storage-backend refactoring without a concrete consumer and recovery plan.
- Automatic LLM calls, model ranking or consensus aggregation before a fixed-package consumption test establishes what the product needs.
- Broad platform expansion simply to increase metric count or issuer coverage.
- Large governance-document rewrites whose completion does not change or verify software behaviour.

## 8. Immediate next actions

1. Finish the P0 parser and runtime-file protection work as two bounded changes with separate verification.
2. Reconcile the tested local state with the dated status checkpoint, keeping historical checkpoints as historical records rather than rewriting them to look current.
3. Run the P1 single-company trace and inspect the actual Investment Context/data package.
4. Update this roadmap only when evidence changes the next action; do not create a parallel roadmap or treat this file as a reason to resist a new owner decision.

## 9. Completion and reporting

A roadmap item is complete when the relevant code/artifact exists and its acceptance evidence has actually been run or inspected. A plan, specification, research POC, model response or documentation review is not a substitute for that evidence.

Every closeout should state the files changed, the Git commit or baseline, tests/checks actually run, results, data operations (if any), and remaining uncertainty. Preserve source data and research artifacts. When the owner changes direction, explain consequences and update this plan; do not let the plan override the owner.