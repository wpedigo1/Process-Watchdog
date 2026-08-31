# Mission 6G — Fix Picker Parent Self-Display

Result: PASS.

## Root cause and fix

`get_process_groups` excluded Process Watchdog only when a process PID equaled `os.getpid()`.
A PyInstaller one-file parent has a different PID but the same executable path as the running
child, so the parent could remain visible and selectable in the process picker. The kill boundary
was already protected by `_is_self` and was not changed.

The picker now calls `_is_self(proc)` instead of duplicating a PID-only check. This reuses the
existing PID-or-normalized-executable-path identity and its established process-access handling.

## Regression coverage

The process-group fake now implements the real `psutil.Process` interface used by `_is_self`.
A new test supplies an external process plus a distinct-PID process whose executable path equals
`sys.executable`, then verifies only the external process appears in picker groups.

Before Mission 6G: 98 tests. After Mission 6G: 99 tests.

## Remaining

All four defects reported by Mission 6D are closed by Missions 6E, 6F, and 6G. The Final
acceptance gate remains unmet until Mission 6D's full checklist is rerun end-to-end against the
fixed code.
