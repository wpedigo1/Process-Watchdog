# Mission 6B — Final Release QA and Baseline Comparison

## Result: FAIL / BLOCKED — genuine startup defect found

Final release QA found a real, reproducible startup crash in the current `main` source. The
packaged application cannot be launched or operated at all, which blocks the runtime measurement
(Part 2) and every functional check (Part 3). Per the mission boundaries, no fix is attempted
here; this defect must get its own focused follow-up mission.

---

## The defect (blocking Parts 2 and 3)

**Symptoms:** launching `dist\ProcessWatchdog.exe` (fresh PyInstaller build from `main@9e02665`)
shows a window titled "Unhandled exception in script" and the process exits almost immediately.
No `ProcessWatchdog` process remains running.

**Root cause (source-level traceback, from `%USERPROFILE%\.process_watchdog\crash.log`):**

```
File "watchdog_app.py", line 130, in main
    config_window = ConfigWindow(cfg, on_change=lambda c: None, watcher=watcher)
File "watchdog_ui.py", line 668, in __init__
    self._tick_status()
File "watchdog_ui.py", line 753, in _tick_status
    self._update_toggle_label()
File "watchdog_ui.py", line 813, in _update_toggle_label
    self.toggle_btn.config(text="Put Dog on Watch")
AttributeError: 'ConfigWindow' object has no attribute 'toggle_btn'
```

**Mechanism:** `ConfigWindow.__init__` calls `self._tick_status()` at `watchdog_ui.py:668`
(guarded only by `if self.watcher:`), but `_tick_status` calls `_update_toggle_label()` which
configures `self.toggle_btn` — and `self.toggle_btn` is first assigned later, at
`watchdog_ui.py:674` (the `tk.Button` in `btn_row` built after the watcher block). `main()`
(`watchdog_app.py:129-130`) always creates and passes a `Watcher`, so the crash fires on every
launch path, first-run and tray alike, before `show()` is ever reached.

**Why the test suite does not catch it:** no test instantiates `ConfigWindow` with a real watcher.
`tests/*.py` reference `Watcher` directly (a controller class, not the Tk UI), and the Tk
`ConfigWindow` is never constructed in any test. The GUI init path
(`__init__` → `_tick_status` → `_update_toggle_label` → `toggle_btn`) is untested — a coverage gap.

**Reproducibility:** observed twice, two independent crash.log entries with identical tracebacks
(timestamps 15:54:06 and 15:57:53), each from a fresh launch of the freshly built exe.

---

## Part 1 — Full automated suite: PASS

`python -m unittest discover -s tests -t . -v` → complete output showed **Ran 87 tests ... OK**.
Source-level count of `def test_` lines across `tests/*.py` = **87** (ground truth), matching.

## Part 2 — Fresh build and resource comparison: PARTIAL / BLOCKED

### Environment and dependency versions (post-build, unchanged by build.bat)

- Python 3.11.0, OS Windows 10.0.26200.9278 (same as Mission 1A).
- psutil 7.2.2, pystray 0.19.5, Pillow 12.2.0, pyinstaller 6.22.2 — all four identical before and
  after `build.bat`, and identical to Mission 1A's baseline. **No version drift.** PASS.

### Build

- `build.bat` ran (authorized for this mission; terminated no running instance since none was
  running — `tasklist` reported none before the build). Build completed:
  `Build complete. Find it at dist\ProcessWatchdog.exe`.
- `git status --porcelain=v1 --untracked-files=all` after build → **empty**. Build artifacts
  (`dist`, `build`, `ProcessWatchdog.spec`) are gitignored as documented. PASS.

### Packaged executable size: PASS

- `dist\ProcessWatchdog.exe` size = **31,528,998 bytes**.
- Baseline `docs/BASELINE.md` = 31,500,369 bytes. Hard ceiling = **32,548,945 bytes**
  (+1 MB).
- 31,528,998 ≤ 32,548,945 → **within ceiling by 1,019,947 bytes. PASS.**
- Delta from baseline: +28,629 bytes.

### Idle memory / CPU / threads / handles: BLOCKED (UNVERIFIED)

The app crashes on startup and never reaches an idle, running state, so
`tools/measure_baseline.py` cannot sample anything. Launch + 35s settle produced a crashing
process ("Unhandled exception in script"), and after crash the process was already gone.
**No idle memory, CPU, thread, or handle samples could be taken.** Every comparison in this
section is therefore UNVERIFIED/BLOCKED, not FAIL — the measurement tool never got a live
target, and the cause is a source defect, not a measurement failure.

### Close and confirm no instance remains: PASS

After the crash (and per the documented `taskkill`-free observation), `tasklist /FI
"IMAGENAME eq ProcessWatchdog.exe"` reported **"No tasks are running"**, and `Get-Process`
returned nothing. The app self-terminated on the exception; no manual shutdown was even needed.

## Part 3 — Functional verification checklist: BLOCKED (all items UNVERIFIED)

Every functional check requires a running application. Because the app crashes on startup, none
of these could be exercised. Each is UNVERIFIED due to the blocking startup defect, not due to a
failure of the specific behavior:

1. Migration — UNVERIFIED (app cannot run; config load is unit-covered but not exercised at
   runtime).
2. Add / Retrain / toggle / Rehome — UNVERIFIED.
3. Grace period / real kill — UNVERIFIED.
4. Unrelated selected leftover eaten — UNVERIFIED.
5. Same-folder neighbor survives — UNVERIFIED.
6. Protected processes never appear/never targeted — UNVERIFIED.
7. Main-window X / doghouse button hide — UNVERIFIED.
8. Tray Quit exits fully — UNVERIFIED.
9. Start with Windows — UNVERIFIED.
10. Light/dark theme + refresh on doghouse-leave — UNVERIFIED.
11. Logo visibility — UNVERIFIED.
12. Every bite-animation path — UNVERIFIED.

No disposable process was launched and no real user application was touched. **Nothing was
killed or modified during this entire mission.** The real
`%USERPROFILE%\.process_watchdog\config.json` was never read for content and never modified.

## Part 4 — Repository cleanliness: PASS

- `git status --porcelain=v1 --untracked-files=all` → **empty** (clean working tree, including
  after the build — artifacts gitignored).
- `git log --oneline main -20` → the expected mission sequence from `9e02665` (Mission 6A) back
  through Missions 5-FIX, 5, 4B, 4A, ..., 1A at `3423491` base — no stray commits, no accidental
  artifacts. HEAD = `9e026653c976341c7dc576a6a0c77dea4d6ac256`.

---

## Conclusion and deferral

The punch board's **Final acceptance gate is NOT met**, and per the mission's own rule the
overall "done" declaration is deferred to the reviewer. The application is currently **unable to
start**, so:

- Part 1 (unit suite) and Part 4 (repo hygiene) PASS.
- Part 2 exe size / deps / build cleanliness PASS; runtime resource measurement BLOCKED.
- Part 3 (all functional behavior) BLOCKED/UNVERIFIED.

A focused follow-up mission is required to fix the `ConfigWindow.__init__` → `_tick_status` →
`_update_toggle_label` → `toggle_btn` ordering defect (and to add a regression test that
instantiates `ConfigWindow` with a watcher so this class of GUI-init crash is caught), after
which this 6B verification must be re-run from a working build.
