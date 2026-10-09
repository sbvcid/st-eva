# Agent Working Rules for ST-EVA

These rules constrain agent autonomy. They do not remove the project owner's ability to correct a design or explicitly authorize a change.

## 1. Start from the user's problem

- State the concrete defect or requested outcome, the smallest acceptance criteria, and the files/components likely involved before proposing a broad plan.
- Inspect the relevant source, tests, and governing clauses. Verify claims against the actual implementation; do not rely on status summaries alone.
- Prefer the smallest sufficient change. Leave working code and unrelated systems unchanged. Refactoring, hardening, extra checks, or new workflow stages are not automatically in scope.
- Keep moving toward observable acceptance evidence. If a proposed step does not resolve the defect, establish a necessary rule, test the result, or manage a specifically identified risk, treat it as optional or deferred—not as a new prerequisite.

## 2. Respect decisions without turning them into dogma

- Read the relevant architecture constitution, formal ADR and contracts before changing code, schemas, identities, or data behaviour.
- Do not silently change an established decision. If it appears wrong or conflicts with authoritative source evidence, identify the exact clause, evidence, consequences, and minimum correction.
- “Frozen” means an agent must not alter a decision unilaterally. It does not mean the owner can never correct or supersede it. Preserve history and record material corrections additively.
- Before treating authorization as a blocker, cite the specific rule and the exact operation it restricts. Do not turn a historical “zero changes” report into a permanent prohibition or infer a broader approval process than the governing text establishes.

## 3. Keep documentation useful and proportionate

- Formal ADRs and approved contracts record decisions; they should not be rewritten as the project evolves.
- Roadmaps are non-authoritative planning hints. Status reports are snapshots of a particular state. Drafts are proposals, not authority.
- Do not create a new roadmap, draft, checklist, review stage, or status document unless it resolves a real ambiguity, records a material decision, reduces a concrete risk, or the owner asks for it.
- Avoid duplicate sources of truth. Update a status snapshot only when its recorded state materially changes; do not keep rewriting it to narrate each intermediate discussion.
- A documentation review is not evidence that code is fixed. Prefer reproducible tests and observed behaviour as the completion criteria.

## 4. Separate source validity, eligibility, and persistence

- Do not assume every valid source record must become a database assertion.
- Check source-format requirements against the relevant authoritative specification. Claim full schema conformance only if full validation was actually performed.
- Distinguish: (a) whether input/source data is valid, (b) whether a record has enough evidence and identity fields for a particular assertion, and (c) whether persistence succeeds.
- Preserve source evidence and explicitly classify unfit records; do not silently discard them, invent missing values, or relax database constraints merely to accommodate a parser.
- Do not change migrations, database schemas, identity definitions, writers, cross-archive access, or production data paths unless the defect requires it or the owner directs it.

## 5. Verify and report honestly

- Build targeted regression tests around the observed defect and the smallest meaningful positive and negative cases.
- Report exact files changed, commands/tests actually run, results, and remaining uncertainty. Never claim a check was performed merely because a document specifies it.
- Treat the local data archive as unknown until inspected read-only. Do not assume it is empty; do not delete, replace, or clean up database, WAL, or SHM files without explicit permission.
- Keep code changes, formal decision updates, and live database operations distinct. Authorization for one does not imply authorization for the others.

## Required incident lesson

Before expanding a narrow defect into a broad governance or architecture project, read [the C2A Parser scope-drift retrospective](docs/DEVELOPMENT-LESSONS-C2A-PARSER-SCOPE-DRIFT.md). Its core lesson is to fix the evidenced problem, record only the decisions that genuinely need recording, and stop adding process when it no longer helps achieve or verify the requested result.
