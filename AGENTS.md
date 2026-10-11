# Agent Guidelines

## Project Priority and Scope

- The user's current explicit request is the highest-priority source of project requirements. Do not infer new requirements from general engineering conventions, other projects' policies, hypothetical external users, public distribution, downloads, demos, reviewers, or imagined audiences unless the user asks for them or they are directly necessary to satisfy the current request.
- The project's core quality requirements are correct data, correct numbers, correct calculations, and traceable sources. Preserve relevant time, period, currency, provenance, and uncertainty semantics. Missing or unverified evidence must remain explicit rather than guessed.
- Work on actual blockers to the requested outcome. Do not turn tools, infrastructure, test coverage, documentation organization, modernization, refactoring, language migration, or CI status into independent goals without a demonstrated need.
- Existing documentation is not automatically authoritative. Prefer the user's current instructions and verified current implementation. Treat archived, retired, superseded, or historical documents as records of the past, not current rules. Do not import requirements from another project's conventions.
- Solve routine technical questions directly from the code, tests, configuration, and reproducible behavior. Do not ask the user to classify ordinary files or choose among routine implementation details. Ask for a decision only when there is a genuine product-level ambiguity, a material trade-off in scope/cost, or an external blocker the agent cannot resolve.
- Do not create additional work for the user by leaving avoidable half-finished changes, temporary scaffolding, broken references, generated artifacts, or routine cleanup.

## Verification and CI

- Tests are a means of checking the user's requested behavior, not a goal in themselves. Run focused tests relevant to the change and broader tests when the scope or risk warrants them.
- Continuous Integration (CI) is an existing verification tool, not a project objective. Do not make "all CI checks green" an independent task or let CI maintenance displace work on the user's requested research functionality.
- Do not add, expand, split, or repeatedly diagnose CI workflows unless the user asks or concrete evidence shows the workflow itself blocks the requested task. A red CI status alone does not establish a product defect.
- If a CI failure is relevant, inspect the actual failing step and available logs once, determine whether it demonstrates a real defect in the requested behavior, and fix confirmed defects directly. Do not guess, perform repeated blind reruns, or create diagnostic commits without a clear stopping condition.
- If an unresolved failure is limited to unrelated infrastructure or cannot be investigated because of a genuine external access limitation, stop the investigation, preserve the working implementation, and report the specific blocker briefly. Do not make the user decide routine technical matters or keep the project blocked solely to obtain a green badge.
- Verify the actual outcomes of tests that were run. Never claim a check passed without evidence.

## Task Closure and Repository Hygiene

- Inspect actual local and remote state before acting. Do not assume previously reported HEAD or status is still current.
- Preserve unrelated pre-existing user changes and persistent data. Never reset, overwrite, or discard them merely to obtain a clean working tree.
- Finish implementation, validation, and cleanup instead of returning routine unfinished work.
- Commit logically complete changes and push them to the existing remote branch when appropriate, without force-pushing or rewriting shared history.
- Verify local/remote synchronization and the outcome of checks relevant to the requested task. A separate, unrelated CI failure does not automatically prevent the requested task from being completed.
- Remove task-specific diagnostic code and temporary files before completing work.
- Leave no uncommitted changes introduced by the agent after a completed run. If pre-existing user changes must remain untouched, identify them as pre-existing and do not conflate them with agent-created residue.
- Report a genuine external blocker accurately instead of claiming success.

## Historical Documentation Archive

`docs/archive/` contains historical records only. Its contents have no current normative or authoritative status.

- During routine repository scans, planning, coding, testing and implementation, do not read, search, summarize or derive instructions or tasks from files under `docs/archive/`.
- Do not use archived documents to determine current project state, restrict implementation or override the user's current instructions.
- Base decisions on the user's current instructions, current source code, tests, active configuration and verified runtime behavior.
- Read a specific archived document only when the user explicitly requests historical research or examination of that record.
- Do not modify, delete or reorganize archived contents unless explicitly requested by the user.
