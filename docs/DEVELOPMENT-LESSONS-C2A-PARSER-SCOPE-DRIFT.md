# Development Lessons: C2A Parser Scope Drift

**Date:** 2026-10-09  
**Type:** Retrospective / maintenance lesson  
**Scope:** SEC taxonomy catalog C2A parser and the work that followed  
**Authority:** Historical learning record. This document does not amend the formal ADR or authorize code, schema, or database changes.

## What happened

The captured SEC catalog `doc_eb3d9eb2f741a4e844f7ed11` (SHA-256 `c639c18647c52a594c74eb60573851de15b7391de84a723cd3b7cced15f0341b`) stopped the existing parser at `Loc` record 127 because `Namespace` was absent.

The parser had treated `Family`, `Version`, and `Namespace` as mandatory for every `Loc`. The v10 draft's schema review records that SEC's `erxl.xsd` makes those fields optional, while `Href` and `Elements` are mandatory. The design error was mixing two different questions:

1. Is the source document structurally valid under the source format?
2. Does a particular record contain enough identity fields to become this project's database assertion?

A record can be valid source data yet be ineligible for `authority_taxonomy_namespaces`, whose identity fields are `NOT NULL`. It should be retained and reported as a non-assertion, not treated as a fatal document error and not inserted as an incomplete assertion.

The intended acceptance result for the captured fixture is 203 source `Loc` records examined, 201 eligible records, and 2 records classified as non-assertions due to missing `Namespace`. These are regression expectations for that captured payload, not constants to hard-code into general parser logic.

## Why the work took the wrong direction

- **The task was not bounded early.** The concrete failure did not get reduced immediately to a small, executable acceptance test: parse the captured payload completely, retain all records in accounting, classify eligibility, and send only eligible assertions to the writer.
- **A local bug expanded into an end-to-end specification.** Amendment 10 v10 grew to 1,533 lines and 84 decision clauses. It includes useful safety ideas, but many were not prerequisites for correcting the optional-field assumption.
- **Documentation state became a workstream of its own.** After the draft was merged as a draft, several follow-up commits reconciled the roadmap and project-status language around draft, review, ratification, ADR append, and authorization. This improved terminology but did not repair or test the parser.
- **Historical protection was over-generalized.** “Frozen” decisions and statements that a prior execution made zero changes were at risk of being treated as a blanket prohibition on the owner correcting a defect. They should prevent an agent from silently changing the baseline, not prevent an explicitly directed correction.
- **The review target drifted.** Readiness and consistency of a large document became a proxy for progress, even though the original acceptance result had not been achieved. A later focused reading also found substantive gaps, including incomplete behavior-change coverage and no explicit expected-versus-produced identity-set equality check.

## What to do differently next time

1. **Start with the smallest problem statement and acceptance test.** Write down the observed failure, the source of truth, the expected behaviour, and what must remain unchanged before designing more rules.
2. **Verify source rules early.** Check the relevant official schema/specification against the captured bytes. Distinguish full schema validation from a parser that checks only selected structures; never claim full conformance unless it was actually tested.
3. **Separate validity, eligibility, and persistence.** Source-format validity is not the same as a record being eligible for an assertion, and neither is the same as a database write succeeding.
4. **Make the smallest sufficient change.** Prefer parser logic and targeted regression tests. Do not change schema, migrations, writer, identity, cross-archive behavior, or unrelated modules unless investigation proves the change is necessary or the owner directs it.
5. **Use ADRs to record real decisions, not to create process around every bug.** If a correction changes an established architectural rule, record the correction additively and preserve history. Keep the decision proportionate to the change; do not turn a narrow repair into a large amendment merely to enumerate every conceivable edge case.
6. **Apply authority narrowly.** Before blocking work on authorization, identify the exact existing rule and the specific operation it governs. A roadmap is a planning hint, a status checkpoint is a snapshot, and an unratified draft has no authority. A prior “zero changes” statement records that execution; it is not automatically a permanent no-change rule.
7. **Keep agent restraint separate from owner authority.** Agents must not silently rewrite stable code or decisions. When an existing rule appears wrong, they should identify the evidence, explain the impact, and propose the minimum correction. The owner may explicitly correct or supersede a decision while retaining its history.
8. **Use a stop rule for scope expansion.** If a proposed next step will not reproduce the defect, establish the required rule, implement the correction, test acceptance, or protect a specifically identified data risk, defer it instead of making it a prerequisite.
9. **Close the loop on evidence, not paperwork.** Report the exact changed files, tests actually run, results, and remaining risks. Do not claim completion because a draft was reviewed, a roadmap was aligned, or a checklist was filled in.

## Application to the current C2A repair

The next technical work should begin with the captured XML and focused regression tests. The parser should account for every `Loc`; records without the required assertion identity fields should be reported as non-assertions and excluded from database writes. The existing `NOT NULL` schema and identity preimage should remain unchanged unless new evidence proves otherwise.

Before any live workflow or database write, inspect the actual local archive state read-only and follow the specific operational restrictions that apply. Do not assume the archive is empty, and do not delete or clean up database or WAL/SHM files as part of this repair.

The success criterion is restored, tested behaviour—not completion of a governance document.
