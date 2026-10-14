# Agent Guidelines

## Scope

- Follow the user's current request and verify relevant behavior against the current implementation.
- Make the changes needed to fulfill the request; do not import requirements from other projects or treat historical documents as current authority.
- Preserve existing user data and unrelated changes.
- Verify the behavior affected by a change and report actual results accurately.
- Finish the requested work and remove temporary changes introduced by the task.

## Default task loop (close the loop)

For every task that may modify this repository, completing the task means the
whole loop, not just a passing implementation:

1. Inspect the branch, working tree, uncommitted changes, remote state, and any
   existing work before editing.
2. Implement, and run the tests the change requires.
3. Review the full diff, the staged diff, the changed-file list, and security risk.
4. Run the necessary diff checks (`git diff --check`) and confirm no unrelated
   edits, credentials, private data, or stray artifacts are included.
5. Create an appropriate commit.
6. Push to the remote normally.
7. Verify the remote contains this task's commit and that the local branch is in
   sync with its upstream.
8. Report the tests actually run, the commit, the push, and the final Git state.

Do not stop after implementing or testing to ask whether to commit or push.
Committing and pushing are part of the default task, not an extra option, unless
the user explicitly says not to commit or push.

## Safety rules

- Never overwrite, discard, or commit pre-existing changes of unknown origin.
- Commit only reviewed changes that belong to the current task.
- Before pushing, confirm that every commit by which the local branch leads the
  remote is safe to publish.
- Push with a normal `git push`. If it is rejected, fetch first, integrate the
  remote changes safely, resolve conflicts, re-test, and push.
- Never force-push to overwrite remote history and never bypass branch protection.
- In a PR or protected-branch flow, complete every step you are authorized to perform.
- If a conflict, permission blocker, or security risk cannot be resolved safely,
  finish whatever else can be done safely and report the blocker precisely.
- Report only verification that actually ran and passed; never overstate tests,
  builds, or environment acceptance results.

## Explicit instructions override

- Follow explicit task instructions over these defaults. If the user asks for
  read-only work, or to not modify, commit, or push, obey that task.
- Such an exception applies only to that task. It must not be read as a standing
  ban on committing or pushing for future tasks.
