# Working Guidelines for ST-EVA

## Start from the current task

- Work from the user's current request and the behavior of the actual code.
- Inspect the relevant implementation and tests. Read documentation only when it helps answer the current question or change.
- Keep changes limited to what the current task requires. Do not add adjacent refactors, checks, process steps, or documentation work by default.

## How to treat documentation

- Files under `docs/` are optional records and references: they may capture past design discussions, experiments, findings, proposals, or the state at a particular time.
- They are not required reading and do not automatically govern current work, even if a file calls itself a contract, constitution, frozen decision, current status, or roadmap.
- A roadmap is a memory aid, not an instruction queue. Reconsider an item against the user's current goal and the actual system before acting on it.
- When documents disagree or are out of date, do not reconcile them automatically. Check code, tests, and relevant runtime behavior only when the disagreement affects the task.
- Do not create or update reports, plans, checklists, or other documents merely to keep the repository consistent. Document something only when the user asks or when it is necessary to complete the current task or preserve a material decision.

## Protect data and verify changes

- Do not delete, reset, migrate, or overwrite runtime databases or persistent data unless the task requires it and the user has authorized that operation.
- For changes affecting persistent data or schema, inspect the relevant code and migrations and use read-only inspection where practical before making changes.
- Run relevant tests when practical. Report the files changed, commands actually run, results, and remaining uncertainty accurately.
- Do not claim a test or verification was performed unless it actually was.
