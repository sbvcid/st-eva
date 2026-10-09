# ST-EVA Project Roadmap

**Status:** Initial project-level plan — not an implementation authorization.
**Review date:** 2026-10-09
**Master baseline checked for this document:** `468083941357efeb54e4cb61a607d6b08039a2ca`
**Separate Amendment 10 draft reviewed:** branch `draft/amendment-10-v10`, commit `fb57e593b1b6187e2e8b518d4f91616684c00a07`
**Scope:** Sequence work across governance, Historical P/E productization, core data platform and user-facing integration.

> **Authority boundary:** This roadmap does not ratify Amendment 10, append anything to an ADR, settle an OPEN methodology decision, authorize an implementation, authorize a migration, or authorize a database operation. Each such step remains subject to its governing document and any required explicit approval. A roadmap status cannot override an ADR or contract.

## 1. Executive direction

ST-EVA already has a substantial deterministic reverse-valuation engine, data/evidence contracts, an append-only archive architecture, cross-source validation, research artifacts, a web/PWA foundation, and extensive methodology documentation. The key near-term problem is not a lack of possible features; it is making the current state and the next critical path unambiguous.

The current strategic priority is:

1. Establish a trustworthy, current project baseline and preserve the separation between draft governance work and the production branch.
2. Complete the Amendment 10 governance review as its own workstream, without treating semantic review as ratification or implementation permission.
3. Advance the approved Historical P/E design toward a production capability, resolving only those methodology and data-model decisions required by the explicitly chosen initial scope.
4. Implement and verify that capability through the existing evidence architecture and conformance requirements.
5. Integrate it into CLI/Web surfaces only after the core workflow and its tests meet their acceptance criteria.
6. Defer broad platform expansion until there is a demonstrated dependency or use case.

## 2. Workstream overview

| ID | Workstream | Initial state | Priority | Next gate |
|---|---|---|---|---|
| RM-0 | Current baseline and status reconciliation | NEEDS REVALIDATION | P0 | Confirm current master, governing documents, tests and known gaps |
| GOV-1 | Amendment 10 governance | Draft-only; targeted semantic review reported complete | P0, separate track | Full approval-readiness review and explicit ratification decision |
| HPE-1 | Historical P/E scope and design prerequisites | Methodology/contract exist; production path not yet implemented per architecture/status documents | P1 | Identify blocking decisions for the first release and record decisions through the required governance path |
| HPE-2 | Historical P/E data-model design | Blocked by HPE-1 decisions and data-layer gaps | P1 | Approved design with provenance fields, identity/basis handling and migration scope |
| HPE-3 | Historical P/E production pipeline | Not started per existing status documents; revalidate before execution | P1 | Contract-conformant implementation and archive integration |
| HPE-4 | Historical P/E conformance and regression | Required acceptance suite documented; production suite must be confirmed against current tree | P1 | All required deterministic and negative-path checks pass |
| HPE-5 | CLI and Web/PWA integration | Web Historical P/E surface recorded as not implemented; revalidate current tree | P2 | Present only validated outputs with provenance and missing-data status |
| PLAT-1 | Long-term evidence-platform improvements | Research items recorded; not all are on the first-release critical path | P3 / case-dependent | Add only when a named consumer or correctness blocker justifies the work |

Priority labels indicate recommended sequencing, not permission to execute.

## 3. RM-0 — Reconcile the current baseline

**Objective:** Stop relying on stale completion summaries and establish an auditable starting point for subsequent work.

### Required work

- Confirm the current `master` SHA and working-tree state locally before any implementation work.
- Reconcile `docs/ST-EVA-PROJECT-STATUS.md` (dated 2026-10-07) with the current tracked tree. Its findings remain historical evidence, not automatically current measurements.
- Confirm the state of the architecture constitution, methodology contract, formal ADRs, migrations, test suite, web surface and the separately maintained Amendment 10 branch.
- Classify each major capability as `SPECIFIED`, `RESEARCH-VALIDATED`, `IMPLEMENTED`, `TESTED`, or `PRODUCTION-INTEGRATED`. These labels must not be used interchangeably.
- Carry unresolved inventory, worktree and research-retention questions forward without deleting or moving material merely to simplify the report.

### Acceptance evidence

A dated status checkpoint with the exact Git baseline, links to source documents, commands or tests actually run, explicit `UNVERIFIED` entries, and a list of any discrepancies found. No migration or production change is required to complete this stage.

## 4. GOV-1 — Amendment 10 governance track

**Objective:** Determine whether the standalone Amendment 10 draft is suitable for formal ratification consideration while preserving the formal ADR and production baseline until the authorized steps occur.

### Current evidence and next actions

- The latest draft is on `draft/amendment-10-v10` at `fb57e593b1b6187e2e8b518d4f91616684c00a07`; it is not part of `master` and remains `DRAFT — NOT IN FORCE`.
- The targeted independent review of Decision 10.30(d) reports that its four counterexamples pass. This is a targeted review, not a substitute for the final whole-draft approval checklist.
- Before any ratification decision, conduct a final review of all disclosed normative gaps, cross-references, the output contract, decision counts, and the distinction between the draft and formal ADR.
- Keep the existing normative-gap identifiers stable. If a review report classifies a limitation differently, reconcile the classification against the governing draft rather than silently renumbering gaps in an audit report.

### Gates and non-authorizations

1. **GOV-1a — Whole-draft readiness review:** check the draft at an exact commit; produce a list of remaining defects and disclosed limitations.
2. **GOV-1b — Ratification decision:** requires an explicit human decision. A clean review report alone does not ratify the draft.
3. **GOV-1c — Formal ADR append:** requires the separate explicit authorization stated by the governing draft; preserve the existing baseline bytes and verify the resulting append.
4. **GOV-1d — Implementation authorization:** a distinct gate before any production code, test, schema, migration or database work governed by the amendment.

Do not merge this draft branch to `master`, edit the formal ADR, or execute a database workflow merely because the targeted review passed.

## 5. HPE-1 — Scope and close required Historical P/E design decisions

**Objective:** Turn the approved Historical P/E method and contract into a buildable, testable production plan without inventing rules that the methodology has left OPEN.

The architecture constitution and existing status documents distinguish the legacy provider-fed `historical_pe_band` from the Contract-defined Historical P/E evidence pipeline. The former does not establish that the latter exists.

### Known prerequisite areas

The data-layer audit and reconciliation documents identify four material gaps on the Historical P/E path:

1. **Evidence class:** a machine-observable distinction between filed and furnished evidence.
2. **Audit status and legal-status note:** a three-valued status model and the required accompanying note, without inferring audit status from form alone.
3. **Fiscal calendar:** resolution of the applicable fiscal-year end on the correct time axis.
4. **Acceptance-instant provenance:** the ability to tell which source supplied the acceptance time, including the contract-required distinction between SGML-header data and a non-conformant alternative.

The Historical P/E ADR and contract also record open decision areas, including reference sufficiency, observation-window/sample requirements, sampling frequency, corporate-action evidence and split adjustment, FPI annual fallback, furnished-evidence treatment in other valuation contexts, XBRL fact-unavailable observability, competing admissible instances, and non-USD currency handling.

The first design task is **not** to close every open question indiscriminately. It is to classify each item as (a) blocking the chosen first release, (b) explicitly deferred with a safe refusal/unavailable path, or (c) outside scope. Any normative choice must be made through its required ADR/contract process, not by an implementation agent.

### Acceptance evidence

- A bounded first-release scope and non-goals.
- A decision register mapping each relevant OPEN item to its governing source, owner/decision route, status and dependency.
- A data-model design demonstrating that required provenance and semantic distinctions can actually be represented.
- Explicit treatment of unavailable, refused and inapplicable evidence.
- No code or migration work before required design decisions and authorization are complete.

## 6. HPE-2 — Approve the data-model and integration design

**Dependency:** HPE-1 decisions that affect the selected first-release path.

Design the smallest conforming representation needed for a Historical P/E observation and its evidence lineage. Cover instrument identity, price basis, corporate-action/split evidence, fiscal-calendar resolution, filed/furnished class, audit status, legal-status note, acceptance-instant provenance, derived-value dependencies and replay.

The design must respect the existing boundaries among source documents, observations, evidence, validation, admission, derived values and replay. It must not weaken append-only behaviour, identity rules, immutable source records or migration checksums to make the first implementation easier.

### Acceptance evidence

- An approved ADR/design update where required.
- A field-to-contract traceability matrix.
- Migration and rollback/recovery implications documented within the existing forward-only policy.
- An explicit list of tables/files/identities that change and those that must not change.
- A review of how old records behave when required attributes are absent.

No schema or migration is authorized by this roadmap.

## 7. HPE-3 — Implement the Contract-defined Historical P/E pipeline

**Dependency:** Approved HPE-1 decisions and HPE-2 design, plus explicit implementation authorization where required.

Recommended implementation sequence:

1. Establish the contract-facing production types and validation boundary.
2. Reconstruct quarter-level price/EPS evidence with source documents and required timing/basis metadata.
3. Implement the historical reference calculation only as specified by the approved contract.
4. Integrate the pipeline with the current core registry, archive, admission and replay path at explicit interfaces.
5. Preserve missing-data/refusal states rather than supplying inferred or synthetic values.
6. Ensure the legacy provider-fed `historical_pe_band` remains clearly distinguished from the new contract-defined path until a separately verified integration decision says otherwise.

### Acceptance evidence

- Traceable mapping from each contract obligation to implementation and test.
- Deterministic recomputation from preserved inputs.
- No silent fallback to an unapproved reference or data source.
- Replay that does not substitute newer inputs for historical ones.
- Migration checksums, idempotence and preservation behaviour verified where applicable.

## 8. HPE-4 — Conformance and regression gate

**Dependency:** A production implementation exists on a controlled branch.

The Historical P/E contract documents a conformance suite covering, at minimum:

- point-in-time replay;
- independent recomputation;
- negative/refusal path;
- look-ahead prevention;
- window integrity;
- provenance completeness;
- evidence-class integrity.

Confirm the exact test names and coverage from the current contract before implementation; do not assume a proof-of-concept or old validation script is an equivalent production test.

### Acceptance evidence

- Offline deterministic tests for expected, missing, contradictory and invalid cases.
- Negative-path assertions showing that invalid evidence refuses or remains unavailable rather than being coerced.
- At least one independent recomputation path.
- Regression results recorded against a named commit and fixture/input hashes.
- Relevant existing suite passes; live provider checks are supplementary and must be clearly separated from deterministic tests.

## 9. HPE-5 — CLI and Web/PWA integration

**Dependency:** HPE-3 and HPE-4 acceptance gates pass.

Only then expose the new Historical P/E workflow to users. Keep the current deterministic engine as the owner of valuation arithmetic; any LLM component remains interpretation-only. The interface should show the valuation reference, source/time basis, provenance, missing fields and verification status, and should not turn conditional inferences into ratings, targets, probabilities or buy/sell instructions.

### Acceptance evidence

- CLI output and machine-readable schema are consistent.
- Web/API output has documented field provenance and missing-data semantics.
- UI labels distinguish observed inputs from derived and conditional-inference values.
- End-to-end tests cover the supported path and refusal/unavailable states.
- Existing reverse-valuation output compatibility is assessed explicitly.

## 10. PLAT-1 — Long-term platform work, only when justified

These topics are real architecture concerns, not automatic commitments to immediate implementation:

| Topic | Why it exists | Sequencing rule |
|---|---|---|
| Research-run and research-artifact relations | Findings and verification evidence do not yet have a canonical first-class relation in the audited data layer | Revisit when several active studies need queryable provenance and lifecycle tracking |
| First-class price time series and instrument identity | Price and EPS need an explicit instrument/basis relationship for more complex securities and long histories | Design only against a named consumer and its contract requirements |
| Corporate-action/split-adjustment evidence | Historical comparisons can be invalid if price and EPS bases are not reconcilable | Resolve for Historical P/E only when the required evidence and decision basis are sufficient |
| Archive/corpus convergence | Existing CLI, web and research workflows have used different database-file conventions | Do not undertake a broad unification without a migration, compatibility and recovery plan |
| Wider issuer/framework support | TSM/IFRS and NU/financial-sector cases differ materially from the initial US-GAAP cross-company set | Add one bounded cohort at a time, with explicit coverage and refusal criteria |
| Storage-backend interface injection | The architecture notes that some engine paths still depend directly on SQLite implementation details | Defer until a second backend or concrete testing/isolation requirement justifies the work |
| Additional valuation methods | Other multiples/models could broaden the tool | Do not pre-build before Historical P/E is production-conformant and a real consumer is identified |

## 11. Operating protocol for agents and contributors

Every new work item must use this sequence:

1. **Read:** current architecture constitution, project structure contract, relevant governing ADR/contract and this roadmap.
2. **Baseline:** state exact branch, HEAD, worktree and files in scope. Do not assume a status checkpoint is current.
3. **Classify:** distinguish observation, design question, implementation task, test task and authorization gate.
4. **Propose:** state expected edits, non-edits, dependencies, failure modes and acceptance evidence before consequential changes.
5. **Authorize:** obtain required explicit decision/approval before changing a governed artifact, schema, migration, production behaviour or database.
6. **Implement and verify:** make bounded changes; run the prescribed tests and checks; preserve data and historical artifacts.
7. **Report:** include commit, exact changed files, tests actually run, limitations and any state not verified.
8. **Update roadmap:** change status only when acceptance evidence supports it.

The repository structure contract remains controlling: research goes under `research/`, governed methodology belongs in its established location, and existing research/data artifacts must not be deleted merely because they are untracked or inconvenient.

## 12. Definition of roadmap completion

A roadmap item is not complete because an agent says it is done. Mark it **DONE — verified** only when:

- its specified deliverables exist at a named commit;
- all required reviews/decisions and authorization gates are satisfied;
- acceptance evidence is recorded and reproducible;
- required tests pass, or any non-run test is explicitly disclosed;
- known limitations and follow-on work remain visible;
- the change respects the project structure, immutable evidence and governing methodology.

This roadmap is expected to evolve as evidence and authorized decisions change. It should be updated at milestone boundaries, not expanded into a speculative catalogue of every possible feature.
