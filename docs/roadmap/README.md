# ST-EVA Development Roadmap

**Status:** Planning document; not an implementation contract or authorization.
**Maintained:** 2026-10-09
**Scope:** Project-level sequencing across governance, methodology, data, engine, tests and product integration.

This directory answers: **what should ST-EVA work on next, why does it come next, what must precede it, and what evidence will show it is complete?**

It does not replace an ADR, an approved methodology contract, a data contract, the architecture constitution, or the project structure contract. It does not authorize code changes, migrations, database operations, deployment, or an ADR append.

## Start here

- [ROADMAP.md](ROADMAP.md) — priority order, workstreams, dependencies, gates and acceptance evidence.
- [Project status checkpoint](../ST-EVA-PROJECT-STATUS.md) — useful historical status record; its stated inspection date is 2026-10-07 and it must be revalidated before being treated as a current measurement.
- [Architecture constitution](../ST-EVA-ARCHITECTURE.md) — canonical architectural boundaries and explicit non-goals.
- [Project structure contract](../ST-EVA-PROJECT-STRUCTURE.md) — where files belong and how artifacts must be preserved.
- [Data-layer audit](../ST-EVA-DATA-LAYER-AUDIT.md) and [data-admission reconciliation](../ST-EVA-DATA-ADMISSION-RECONCILIATION.md) — recorded data-model gaps and evidence behind them.
- [Historical P/E methodology ADR](../ADR-HISTORICAL-PE-METHODOLOGY.md) and [Historical P/E contract](../methodology/CONTRACT-HISTORICAL-PE.md) — governed decisions and implementation constraints.
- [XBRL source-document provenance ADR](../ADR-XBRL-SOURCE-DOCUMENT-PROVENANCE.md) — formal baseline for the Amendment 10 governance workstream.

## Status vocabulary

Use these terms consistently:

- **DONE — verified:** required artifact exists and its stated acceptance evidence has been checked against a named repository state.
- **IN PROGRESS:** work has begun and has an explicit next action.
- **BLOCKED:** a named prerequisite prevents safe progress.
- **DECISION REQUIRED:** a human or authorized decision record must resolve the question before dependent work proceeds.
- **PLANNED:** accepted into the roadmap but not started.
- **DEFERRED:** intentionally postponed with a reason; not an implicit commitment.
- **NOT IN SCOPE:** explicitly excluded from the current milestone.

A document being written, a design being complete, and software being implemented are different completion states. Do not mark a software capability DONE solely because a specification, proof-of-concept, or research report exists.

## Update rules

1. Keep `ROADMAP.md` as the single project-level sequencing index; link to detailed specifications instead of copying them.
2. Every work item must state its objective, dependencies, deliverables, acceptance evidence, and authorization boundary.
3. Reconcile the roadmap with the current Git baseline and governing documents when a milestone closes or a material decision changes.
4. Preserve historical checkpoints and research artifacts according to the project structure contract; do not rewrite history merely to make old status notes appear current.
5. Where the evidence is incomplete, state `UNVERIFIED` or `NEEDS REVALIDATION`; do not infer completion.

The roadmap is a planning aid. Governing decisions and explicit authorization remain controlling.
