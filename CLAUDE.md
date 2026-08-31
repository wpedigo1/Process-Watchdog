# Claude Code — Process Watchdog

@AGENTS.md

`AGENTS.md` is the canonical Process Watchdog project instruction file.
Follow it as the source of truth.
Do not duplicate or reinterpret those rules here.

## Working Rules

Before editing:

1. Read `AGENTS.md`.
2. Inspect the relevant implementation and tests.
3. Search the repository for an existing working pattern before inventing a new one.
4. Trace the affected state and call path before introducing new abstractions.
5. Prefer the smallest change that fully satisfies the request.

For routine, well-defined tasks, inspect and proceed without stopping for plan approval.

Ask before implementing only when a material ambiguity, destructive action, or product decision
cannot be resolved from the repository and the project instructions. In particular, ask when the
answer would change which processes are watched, which processes are terminated, or whether
existing user configurations remain loadable.

For changes to configuration persistence, process matching, termination scope, or the watcher
threading model, provide a short implementation plan before editing.

## Repository Behavior

Do not treat previous sessions, mission reports, summaries, commit SHAs, branch names, or PASS
statements as proof of current repository state. Inspect the actual repository.

Do not:

- create a second implementation beside an existing working path;
- broaden a focused task into cleanup or redesign;
- broadly reformat or rewrite `watchdog_app.py`;
- add dependencies, frameworks, services, or databases that the task does not require;
- silently change grace-period limits, polling intervals, startup behavior, process matching,
  or termination scope.

When project documentation and repository behavior conflict, identify the conflict instead of
silently resolving it.

## Validation

Use the repository's actual commands and configuration. Do not invent test, lint, or build
commands.

Run the narrowest relevant validation first, then broader validation justified by the change.

Never report a command as successful unless its successful result was observed.

Process termination is destructive. Verify termination selection logic with mocked unit tests.
Do not terminate the user's real applications to validate a change. `build.bat` terminates any
running `ProcessWatchdog.exe` and deletes build output, so do not run it unless the task
explicitly calls for a clean packaged build.

Before reporting completion, review the final diff for unintended files, unrelated refactors,
accidental formatting churn, and exposed user configuration paths.

## Completion Report

Keep it short. Include:

- what changed;
- files changed;
- validation actually run, with observed results;
- material assumptions;
- unresolved failures or risks.

Never claim an external action or a successful state that was not directly verified.
