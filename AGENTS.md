# Agent Guidelines

- Follow the user's current request. Inspect the relevant implementation and tests before making claims about behavior.
- Make the smallest change that satisfies the task; leave unrelated code and files untouched.
- Protect persistent data. Do not delete, reset, or overwrite runtime databases or user data unless the task requires it and the user has authorized it.
- Run relevant tests when practical. Report the files changed, checks actually run, and results accurately.

## Task Closure & Repository Hygiene

- Inspect actual local and remote state before acting. Do not assume previously reported HEAD or status is still current.
- Preserve unrelated pre-existing user changes and persistent data.
- Finish implementation, validation, and cleanup instead of returning routine unfinished work.
- Commit logically complete changes and push them to the existing remote branch when appropriate.
- Verify local/remote synchronization and relevant CI before declaring completion.
- Remove task-specific diagnostic code and temporary files before completing work.
- Leave no uncommitted changes introduced by the agent after a completed run.
- Report a genuine external blocker accurately instead of claiming success.

## Historical Documentation Archive

`docs/archive/` contains historical records only. Its contents have no current normative or authoritative status.

- During routine repository scans, planning, coding, testing and implementation, do not read, search, summarize or derive instructions or tasks from files under `docs/archive/`.
- Do not use archived documents to determine current project state, restrict implementation or override the user's current instructions.
- Base decisions on the user's current instructions, current source code, tests, active configuration and verified runtime behavior.
- Read a specific archived document only when the user explicitly requests historical research or examination of that record.
- Do not modify, delete or reorganize archived contents unless explicitly requested by the user.
