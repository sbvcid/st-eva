# ST-EVA Roadmap

**Maintained:** 2026-10-10  
**Role:** A concise record of the owner's current product direction, next steps and completion evidence. It should help a future session or coding agent remember what ST-EVA is being built to do and why the next task matters. It is a living plan and can change when the owner changes direction or new evidence appears.

## Product direction

ST-EVA preserves verifiable, time-indexed financial evidence and deterministic reverse calculations under explicit assumptions, then packages them for external LLM research. Its distinctive long-term purpose is to retain what the market price conditionally implied at a recorded time, with the inputs and assumptions needed to study changes later.

ST-EVA does not produce fair-value predictions. Its deterministic calculations are data supplied to the research process; an LLM uses the evidence package to analyse possible price-consistent assumptions. Observed facts, calculated values, conditional calculations and LLM interpretations must remain distinguishable.

## Start here

- [ROADMAP.md](ROADMAP.md) — current product purpose, known baseline, immediate repairs, phases, and acceptance conditions. Read this first when deciding what the project should do next.
- [Project status checkpoint](../ST-EVA-PROJECT-STATUS.md) — dated record of a specific inspected state, not necessarily current local state.
- [Architecture and implementation reference](../ST-EVA-ARCHITECTURE.md) — existing design rationale and code/data boundaries; useful context, but the owner may revise a prior design.
- [Project structure reference](../ST-EVA-PROJECT-STRUCTURE.md) — current directory and artifact conventions.
- [Investment Context specification](../ST-EVA-2.3-C-INVESTMENT-CONTEXT.md) and [Point-in-Time Archive & Replay specification](../ST-EVA-2.4-POINT-IN-TIME-ARCHIVE-REPLAY.md) — existing foundation for traceable agent-consumable data and historical reconstruction.
- [Data-layer audit](../ST-EVA-DATA-LAYER-AUDIT.md) and [data-admission reconciliation](../ST-EVA-DATA-ADMISSION-RECONCILIATION.md) — prior findings to verify against the actual current implementation before relying on them.
- [Historical P/E methodology](../ADR-HISTORICAL-PE-METHODOLOGY.md) and [contract](../methodology/CONTRACT-HISTORICAL-PE.md) — a possible evidence/reference workstream, not automatically the mainline.
- [XBRL source-document provenance ADR](../ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md) and [C2A parser retrospective](../DEVELOPMENT-LESSONS-C2A-PARSER-SCOPE-DRIFT.md) — relevant to the current known parser defect and its bounded repair.

## How to use this roadmap

1. Start from the owner's current goal and the immediate acceptance condition, not from a priority label in an old plan.
2. Check the actual code, tests, Git state and relevant local data before claiming a capability exists or is missing.
3. Use the listed phases to keep the work sequenced; do not expand a narrow fix into unrelated governance, refactoring or feature development.
4. Preserve historical documents as records of what was thought or observed then. Correct them when a current summary is materially misleading, without rewriting the past to make it appear that the new direction always existed.
5. Report what was inspected or tested, what actually changed, and what remains unknown.

Status words such as DONE, IN PROGRESS, BLOCKED or DEFERRED are summaries of evidence and intent, not immutable rules. The owner can change the plan. Agents should point out consequences and dependencies rather than silently ignoring the current direction or treating an old document as unchangeable.