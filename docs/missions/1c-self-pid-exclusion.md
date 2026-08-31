# Mission 1C — Self-PID Exclusion in kill_processes

Route: Big Pickle (OpenCode Zen)
Base: `main` @ `afeb9192464878e3cc88b42e6654de9b136ea0e1` (Mission 1B)
Scope: narrow slice of punch board Mission 3 "Permanent protection" — feeding-engine
self-protection only. The full permanent-protection section (SYSTEM / protected paths /
picker-filter-UI-wide enforcement) remains a separate, larger mission.

## Result: PASS

## Root cause (already proven before this mission)

`tests/test_kill_selection.py::test_own_pid_not_excluded_current_behavior` (Mission 1A)
proved the gap deterministically with zero real termination risk: it builds a `FakeProc`
whose `pid` is literally `os.getpid()` (the PID of the test process itself), injects it as a
"matched" process via `patch.object(watchdog_app, "find_matching_processes", return_value=[own])`,
calls `kill_processes`, and asserts `own.kill_calls == 1`. The old code had no check anywhere
against the calling process's own identity, so if Process Watchdog's own process were ever
matched (direct match, recursive child, or install-directory expansion), `kill()` would be
called on itself. This violates `AGENTS.md`: "Never terminate Process Watchdog itself unless the
requested behavior explicitly requires it."

## What changed

### `watchdog_core.py` — `kill_processes` (+ a small helper)

- Added `_is_self(proc)` helper. It reports True when EITHER `proc.pid == os.getpid()` OR
  `_norm_path(proc.info.get("exe")) == _norm_path(sys.executable)`. It calls `os.getpid()` and
  `sys.executable` fresh on each invocation (not import-time frozen constants), so tests can
  exercise it by matching against the test runner's own PID. Path comparison reuses the existing
  `_norm_path` helper (the codebase's single path-normalization approach) — no second
  normalization was invented.
- At the point where all three kill sources (direct matches, recursive descendants, and other
  binaries installed beneath a matched project) have already merged into `to_kill`, the merged
  dict is filtered to drop any self process:
  `to_kill = {pid: proc for pid, proc in to_kill.items() if not _is_self(proc)}`.
  One exclusion check at the single merge point, before the kill loop. Self is therefore never
  entered into the kill set at all (not added-then-skipped), never counted, and never logged as a
  normal target. The return value (count killed) does not reflect self's presence.

Both checks are required: PID alone would miss a self process reported under a different PID;
exe-path alone would miss the case where `proc.info.get("exe")` is unavailable (access denied),
consistent with this file's existing honest handling of that case.

## PyInstaller parent/child investigation (Required Behavior item 4)

Static inspection of `build.bat` and `ProcessWatchdog.spec`:

- `build.bat` builds with `--onefile --windowed`, named `ProcessWatchdog`. The one-file mode
  extracts the bundle to a temporary directory (default `%TEMP%\_MEIxxxxxx`) and launches a
  child process that runs the Python interpreter / bundled `watchdog_app.py`.
- `ProcessWatchdog.spec` is a standard one-file `EXE(pyz, a.scripts, a.binaries, a.datas, ...)`
  with `console=False`, confirming the one-file bootloader packaging.

Finding (what is verifiable statically vs. not):

- Inside the running child, `sys.executable` is the bootloader executable under the temporary
  `_MEI` extraction directory, NOT the original `dist\ProcessWatchdog.exe`. The child's PID is
  what `os.getpid()` returns, and its `exe` equals `sys.executable`, so the child itself IS
  reliably excluded by the new `_is_self` check.
- The **parent bootloader** process is a separate OS process whose executable path is
  `dist\ProcessWatchdog.exe`. Its exe path differs from the child's `sys.executable` (a temp
  `_MEI` path), and its PID differs from the child's `os.getpid()`. Therefore, IF the parent
  bootloader were ever enumerated and matched — for example by install-directory expansion when
  a legitimately-matched target happens to live in the same directory as the installed
  `dist\ProcessWatchdog.exe`, or by a direct/child source — neither the pid check nor the
  exe-path check in `_is_self` would catch it.

That is a **known residual gap**, not solved in this mission. Whether it can actually be hit at
runtime depends on facts that cannot be confirmed without a live Windows one-file build +
process-tree inspection (e.g. whether the parent bootloader's `exe` is resolvable by
`psutil.process_iter`, and whether any configured target's install directory coincides with the
installed exe's directory). This mirrors how `guardrails.close_stream` residual risk was
handled in the reference project: reported as a residual gap for a future mission rather than
guessed away. This mission did not attempt to solve it.

## Tests and validation (observed output)

Baseline (pre-change): `python -m unittest discover -s tests -t . -v` — `Ran 40 tests ... OK`

After change:
```
python -c "import ast;ast.parse(open('watchdog_core.py',encoding='utf-8').read());print('CORE SYNTAX OK')"  -> CORE SYNTAX OK
python -c "import watchdog_core;print('CORE IMPORT OK')"                                                     -> CORE IMPORT OK
python -m unittest discover -s tests -t . -v                                                                  -> Ran 42 tests ... OK
```

Test-count math: 40 baseline − 1 renamed/no-net-change + 2 new tests = 42.

`tests/test_kill_selection.py` (`python -m unittest tests.test_kill_selection -v`) — 9 tests, all ok:
- `test_directly_matched_processes_are_selected` (unchanged)
- `test_recursive_children_selected` (unchanged)
- `test_same_directory_neighbor_is_killed_current_behavior` (UNCHANGED — the separate,
  still-open mission-3 defect; still kills the neighbor, still asserts `== 2`)
- `test_kill_raising_no_such_process_not_counted` (unchanged)
- `test_kill_raising_access_denied_not_counted` (unchanged)
- `test_same_pid_reached_by_direct_match_and_child_killed_once` (unchanged)
- `test_own_pid_is_excluded_from_kill` (RENAMED + INVERTED from
  `test_own_pid_not_excluded_current_behavior`) — now asserts `result == 0` and
  `own.kill_calls == 0`
- `test_self_excluded_by_exe_path_even_with_different_pid` (NEW) — FakeProc with a different PID
  but `exe == sys.executable`; asserts `kill_calls == 0`
- `test_self_excluded_when_reached_via_install_directory_expansion` (NEW) — self reached via the
  install-directory expansion path; asserts the legitimate target is still killed (`result == 1`,
  `target.kill_calls == 1`) while self (`self_proc.kill_calls == 0`) is excluded

Acceptance criteria confirmation:
1. Renamed/inverted `test_own_pid_not_excluded_current_behavior` -> `test_own_pid_is_excluded_from_kill`;
   asserts `own.kill_calls == 0`.
2. exe-path self exclusion with different PID — `test_self_excluded_by_exe_path_even_with_different_pid`.
3. Self reached via install-directory expansion — `test_self_excluded_when_reached_via_install_directory_expansion`.
4. All other pre-existing `test_kill_selection.py` tests (direct match, children, install-dir
   neighbor, access-denied, no-such-process) pass with UNCHANGED assertions.
5. `test_same_directory_neighbor_is_killed_current_behavior` untouched and still passing — this
   mission did not alter that unrelated (still-open) behavior.
6. Full suite passes: 42 tests, all OK. No other test file's assertions changed.

## Files changed

- `watchdog_core.py` — added `_is_self`, added single merge-point exclusion in `kill_processes`.
- `tests/test_kill_selection.py` — 1 test renamed/inverted, 2 new tests. No other test file touched.
- `docs/PUNCHBOARD.md` — annotated that feeding-engine self-exclusion is now closed (Mission 1C),
  without marking overall Mission 3 as done.
- `docs/missions/1c-self-pid-exclusion.md` — this report (new).

## Confirmation of unchanged behavior

- install-directory expansion logic itself is untouched (still kills same-folder neighbors —
  evidenced by the still-passing `test_same_directory_neighbor_is_killed_current_behavior`).
- `find_matching_processes` matching semantics (exact-path vs. name-only fallback) untouched.
- No trigger/visibility logic touched: `find_matching_processes`, `open_trigger_names`,
  `_get_visible_window_pids` unchanged.
- `watchdog_ui.py` untouched.
- No dependency added; `build.bat` NOT run.
