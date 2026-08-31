# Mission 3B — Username-Based SYSTEM/Service Owner Exclusion

Route: Big Pickle (OpenCode Zen)
Base: `main` @ `f3694775fb4bc1e6d7c51b58fbf5135c2e9fb3c5`
Scope: the punch-board Mission 3 residual gap — exclude SYSTEM, LOCAL SERVICE,
and NETWORK SERVICE process owners from `kill_processes` using a live
`proc.username()` check at the single merge point.

## Result: PASS

## Root cause / motivation

Mission 3 closed the identity-only (name/path) protection gap, but
`is_protected_entry` works without a live process and therefore cannot inspect
the process owner. `is_system_process` CAN check `username` via `.info` but is
only called from `get_process_groups` / `list_processes` for display — it is
never called from `kill_processes`. A matched process or recursive child whose
identity does not match any protected name or system path would still be killed,
even if it was owned by SYSTEM, LOCAL SERVICE, or NETWORK SERVICE.

Adding `username` to the `process_iter(attrs=...)` call inside
`find_matching_processes` would NOT cover recursive children, which are fresh
`psutil.Process` objects with no cached `.info`. A live `proc.username()` call
inside `kill_processes` is the only approach that correctly covers both direct
matches and children uniformly.

## What changed

### `watchdog_core.py`

- New `_is_protected_owner(proc)` function — calls `proc.username()` live,
  uppercases the result, and returns True if any `SYSTEM_USERNAMES` substring
  is found. On `NoSuchProcess` or `AccessDenied`, returns False (see judgment
  call below). Reuses the existing `SYSTEM_USERNAMES` constant; does not
  redefine it.

- `kill_processes` merge-point filter expanded: the existing `not _is_self(proc)
  and not is_protected_entry(...)` now includes `and not _is_protected_owner
  (proc)` as a third condition in the same single-pass dict comprehension. No
  separate loop was added.

### `tests/test_kill_selection.py`

- `FakeProc` updated with optional `username_val` / `username_exc` constructor
  parameters and a `username()` method to support the new tests.
- Six new tests added (criteria 1-6 below).

## AccessDenied judgment call

When `proc.username()` raises `AccessDenied`, the process owner cannot be
determined. This is treated the same honest way `kill_processes` already handles
`AccessDenied` elsewhere — the process is NOT protected purely on that basis,
and proceeds to the normal `proc.kill()` call, which may itself hit
`AccessDenied` and skip without crashing.

Rationale: `AccessDenied` means "I don't know who owns this," not "this is
definitely a system process." Treating unknown ownership as automatically
protected would be an overcorrection that could leave user processes alive that
the user explicitly targeted. The existing codebase convention is to handle
`AccessDenied` honestly by not pretending the signal is there when it isn't.

## Tests

Test suite went from 64 (baseline) to 70 (PASS on all 70).

- `test_system_owned_username_is_not_killed` — criterion 1: a matched process
  with `username()` returning `"NT AUTHORITY\SYSTEM"` is never killed.
- `test_local_service_username_is_not_killed` — criterion 2a: LOCAL SERVICE
  account is excluded.
- `test_network_service_username_is_not_killed` — criterion 2b: NETWORK SERVICE
  account is excluded.
- `test_system_owned_recursive_child_is_not_killed` — criterion 3: a recursive
  child (not the direct match) with SYSTEM ownership is also excluded; the
  parent (non-SYSTEM) is still killed. Proves the check covers children.
- `test_access_denied_on_username_does_not_protect` — criterion 4: AccessDenied
  on `username()` does NOT protect the process; it reaches `proc.kill()`
  normally and is killed in this test (no `kill_exc` set), proving it was not
  filtered out.
- `test_normal_user_owned_process_is_killed` — criterion 5: a normal
  `DOMAIN\user` process is unaffected; kill count is 1.

## Validation actually run (observed)

```
python -c "import watchdog_core;print('IMPORT OK')"
→ IMPORT OK

python -m unittest discover -s tests -t . -v
→ Ran 70 tests in 0.056s OK

git status --short
git diff --stat
git diff -- watchdog_core.py
```

## Not changed / out of scope

- `is_protected_entry`, `is_system_process`, `_is_self`,
  `find_matching_processes`, `open_trigger_names`, `Watcher`, `get_process_groups`.
- `SYSTEM_USERNAMES` constant — reused, not redefined.
- No `username` added to any `process_iter(attrs=...)` call.
- No new dependency. `build.bat` was not run.
- Supporting docs (`AGENTS.md`, `CLAUDE.md`, `BASELINE.md`) were not modified.
