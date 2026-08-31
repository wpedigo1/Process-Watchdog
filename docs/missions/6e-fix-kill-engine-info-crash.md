# Mission 6E — Fix Kill-Engine Crash on Child Processes

Fix for Mission 6D's defect 4 (most severe — the core feeding engine). Result: PASS.

## Corrected root-cause trace

`kill_processes` merges two sources into `to_kill`: direct matches from
`find_matching_processes` (via `psutil.process_iter`, whose yielded objects carry a populated
`.info` dict) and descendants from `proc.children(recursive=True)` (plain `psutil.Process`
objects with NO `.info` attribute — confirmed empirically; `psutil.Process(pid).info` raises
`AttributeError`, it does not return an empty dict). The protection filter then read `.info`
on every entry.

**Correction to Mission 6D's cited line (as this mission's brief also corrected):** the first
crash site for a real child is inside `_is_self` (`watchdog_core.py:137`,
`_norm_path(proc.info.get("exe"))`), not `is_protected_entry`'s caller-side dict — the `and`
chain evaluates left to right, so `_is_self(proc)` runs first. Both reads had the identical
`.info` dependency and both were fixed. `_is_protected_owner` was already correct (live
`proc.username()`, no `.info`) and is untouched.

**A third `.info` read this mission's boundary did not list:** the kill loop itself
(`watchdog_core.py:401`, `name = proc.info.get("name")`) — used for per-name kill/failed
reporting. The mission's hard boundary said "do not change anything about the actual
`proc.kill()` loop," but acceptance criterion 3 (`kill_processes` with `detail=True` on a
matched process with a real child "completes without raising") is unsatisfiable with that read
in place: the filter would pass the child and the very next statement would raise the same
`AttributeError`. Reporting the conflict rather than silently choosing: the fix applies the
same one-line `_live_identity` substitution there (reporting-only read; kill semantics,
ordering, and error handling unchanged). No other line of the loop was touched.

Why the 89-test suite stayed green throughout: `FakeProc` in `test_kill_selection.py` provides
`.info` unconditionally — including on fake children — which does not model real
`psutil.Process.children()` output. The defect was invisible to every mocked test.

## The fix (`watchdog_core.py` only)

1. New helper (placed after `_norm_path`):

```python
def _live_identity(proc):
    """Read a process's name/exe via live calls, not the .info cache (which
    is only populated for process_iter results, not .children()). Honest
    fallback on NoSuchProcess/AccessDenied, matching this file's existing
    error-handling convention elsewhere."""
    try:
        name = proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        name = ""
    try:
        exe = proc.exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        exe = ""
    return name, exe
```

2. `_is_self` now uses `_norm_path(_live_identity(proc)[1])` instead of
   `proc.info.get("exe")`.
3. The `kill_processes` merge-point filter now routes through a small local `_unprotected(proc)`
   predicate that calls `_is_self`, `is_protected_entry` (fed by `_live_identity`), and
   `_is_protected_owner` in the same order — one merge point, same semantics, no `.info`.
4. The kill-loop name read (`_ live_identity(proc)[0]`) — the documented boundary conflict
   above.

Nothing else changed: `to_kill` population, `find_matching_processes`, `open_trigger_names`,
`_is_protected_owner`, kill semantics, `watchdog_ui.py` (UI defects 2/3 are a separate
mission), and all other files untouched.

## Test-world alignment (`tests/test_kill_selection.py`)

`FakeProc` gained the two standard `psutil.Process` API methods it had always been missing —
`name()` and `exe()`, returning the same values its `.info` dict carries. Production code now
calls the real API, so the fake must model it. No existing test method, assertion, or behavior
changed; all 20 pre-existing kill-selection tests pass byte-identically.

## New regression tests (`tests/test_kill_real_processes.py`) — REAL psutil, not mocks

Why real objects were non-negotiable: the crashing shape is "a `Process` with no `.info`
attribute," which `FakeProc` cannot represent no matter how it is configured. The tests spawn
their own disposable processes only, and clean up unconditionally in `finally`:

- `_live_identity` on a real non-`process_iter` `Process` (the test runner itself — verified
  `hasattr(proc, "info") == False`) returns the correct name/exe without raising.
- `_is_self` on real no-`.info` `Process` objects (own pid -> True; the parent shell -> False)
  — the exact former crash site — no `AttributeError`.
- A real child obtained via `.children()` from a real spawned parent: verified it has no
  `.info`, `_live_identity` returns its true identity, `_is_self` is False without raising.
- Full criterion-3 reproduction: a uniquely-named COPY of the Python interpreter in a temp dir
  (unique path guarantees the identity can only match processes the test spawned; killing
  same-`sys.executable` processes is impossible by design — Mission 1C self-exe-path
  protection — and System32 exes are protected paths) runs a parent that spawns its own child;
  `kill_processes([entry], detail=True)` completes without raising, reports the dog in
  `killed` with `failed == []`, and BOTH pids are verified gone via psutil.

## Validation (observed)

- Before: `python -m unittest discover -s tests -t . -v` -> `Ran 89 tests ... OK`
- `python -c "import watchdog_core;print('IMPORT OK')"` -> `IMPORT OK`
- After: `python -m unittest discover -s tests -t . -v` -> **`Ran 94 tests ... OK`**
  (89 existing, all unchanged and green, + 5 new real-process tests)
- New test file alone: `python -m unittest tests.test_kill_real_processes -v` ->
  `Ran 5 tests ... OK`
- `git diff -- watchdog_core.py` — the complete diff is shown above in the mission report
  (helper + `_is_self` + filter + the one kill-loop name read).
- `git status --short` -> `M tests/test_kill_selection.py`, `M watchdog_core.py`,
  `?? tests/test_kill_real_processes.py`

## Remaining

Mission 6D defects 2 (Add dialog crash), 3 (Retrain locked-entry crash + silent meal-target
loss), and 1 (picker lists own parent exe) remain open for their follow-up missions. The Final
acceptance gate remains NOT met until those are fixed and the release QA is re-run.
