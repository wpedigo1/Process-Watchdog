# Mission 1C-VERIFY — PyInstaller Parent/Child Exe-Path Check

Route: Big Pickle (OpenCode Zen)
Base: `main` @ `4adda2830f121c63b713f08d50b6a694911ed4ee` (Mission 1C)
Type: read-only verification. No `watchdog_app.py`, `watchdog_core.py`, `watchdog_ui.py`, or test
file was modified.

## Result: PASS

## Objective settled

Mission 1C reported, purely from static inspection (no live build), an unconfirmed residual gap:
that the PyInstaller one-file bootloader parent process would report a different `exe` than the
child, and would therefore NOT be caught by `_is_self`'s exe-path check. This mission settled the
claim empirically by building and enumerating a live process tree.

## Raw pid/ppid/exe table observed

```
=== Processes named ProcessWatchdog.exe ===
     pid     ppid  exe-matches-installed  exe path
   17660    18272  True                   C:\Users\wpedi\Process Watchdog\dist\ProcessWatchdog.exe
   18272    31864  True                   C:\Users\wpedi\Process Watchdog\dist\ProcessWatchdog.exe

Total processes named ProcessWatchdog.exe found: 2
Finding: CONFIRMED — all parent/child processes report the IDENTICAL exe path.
```

The installed path is `C:\Users\wpedi\Process Watchdog\dist\ProcessWatchdog.exe`. `psutil`
enumerated two `ProcessWatchdog.exe` processes:
- pid `18272` — the parent bootloader (spawned externally by this script; its `ppid` is the
  launching shell).
- pid `17660` — `ppid = 18272`, the child app process spawned by the parent bootloader.

Both processes report the identical `exe` value `dist\ProcessWatchdog.exe`, and both match the
known installed path case-insensitively.

## Finding statement

**Confirmed: parent and child report the identical exe path. Mission 1C's `_is_self` exe-path
check already covers the parent process. The residual gap reported in Mission 1C's mission report
does not exist as described.**

Because PyInstaller sets `sys.executable` inside the frozen child to the actual launched
executable path (not the `sys._MEIPASS` temp extraction directory), and because the parent
bootloader is the same binary file reported externally with that same path, a process matching
the parent would satisfy `_norm_path(proc.info.get("exe")) == _norm_path(sys.executable)`. Both
the parent and child are therefore excluded by the existing single-point `_is_self` check added
in Mission 1C. The PID check (`proc.pid == os.getpid()`) additionally covers the child. No change
to any kill logic is warranted by this finding.

## What was done

- Ran `build.bat` (authorized in this mission) to produce a fresh `dist\ProcessWatchdog.exe` from
  the current source.
- Added `tools/check_parent_child_exe.py` — a standalone diagnostic (NOT wired into the app) that
  launches the exe, waits for the tree to settle, enumerates every `ProcessWatchdog.exe` process
  with `pid`/`ppid`/`exe` via `psutil.process_iter`, prints whether each exe (normalized
  case-insensitively) equals the installed path, reports the parent/child relationship, and then
  cleans up.
- The script performs enumeration only; it never terminates any process beyond closing the exact
  PIDs it launched for this check. Because tray-Quit cannot be driven scriptably from this
  context, cleanup used `taskkill /PID <pid> /F` on those specific PIDs (deviation
  pre-authorized by the mission; stated plainly in the script output).

## Validation (raw output)

`python -m unittest discover -s tests -t .` — `Ran 42 tests ... OK` (unchanged; no source or test
file was modified in this mission).

`tasklist /FI "IMAGENAME eq ProcessWatchdog.exe"` after cleanup —
`INFO: No tasks are running which match the specified criteria.` (no instances left running).

## Files changed

- `tools/check_parent_child_exe.py` — new standalone diagnostic tool (only new file).
- `docs/missions/1c-verify-parent-child.md` — this report (new).

No source, test, `_is_self`, or kill logic was modified. `dist/`, `build/`, `*.spec` are
gitignored and were not committed.
