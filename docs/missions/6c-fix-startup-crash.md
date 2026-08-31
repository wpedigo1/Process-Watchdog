# Mission 6C — Fix Startup Crash: toggle_btn Ordering

Fix for the release-QA blocker found in Mission 6B. Result: PASS — the crash is fixed, covered
by a real-instantiation regression test, and the app now starts.

## The fix (`watchdog_ui.py`, `ConfigWindow.__init__` only)

The `btn_row` frame and its contents **through the `self.toggle_btn.pack(side="left")` line**
now are constructed BEFORE the `if self.watcher: self._tick_status()` guard. The three remaining
buttons (Rehome Dog, Hide Dogs in the Doghouse, Trainer's Guide) stay in their exact prior
position — moving them too would have reordered construction the mission's hard boundary
forbids, and they are not needed by `_tick_status`. Pack order on each side is unchanged
(left group: Add, Retrain, toggle, Rehome; right group: Hide then Guide), so the rendered layout
is identical. No button text, spacing, widget construction, or any other method changed.

Full diff:

```diff
@@ -664,15 +664,16 @@ class ConfigWindow:
         self.tree.column("status", width=220, anchor="w")
         self.tree.pack(fill="both", expand=True, padx=10, pady=6)

-        if self.watcher:
-            self._tick_status()
-
         btn_row = tk.Frame(self.root)
         btn_row.pack(fill="x", padx=10, pady=(0, 10))
         tk.Button(btn_row, text="Add Watchdog", command=self.add_watchdog).pack(side="left")
         tk.Button(btn_row, text="Retrain", command=self.edit_watchdog).pack(side="left", padx=6)
         self.toggle_btn = tk.Button(btn_row, text="Put Dog on Watch", command=self.toggle_watchdog)
         self.toggle_btn.pack(side="left")
+
+        if self.watcher:
+            self._tick_status()
+
         tk.Button(btn_row, text="Rehome Dog", command=self.delete_watchdog).pack(side="left", padx=6)
         tk.Button(btn_row, text="Hide Dogs in the Doghouse", command=self.hide).pack(side="right")
         tk.Button(btn_row, text="Trainer's Guide", command=self.open_guide).pack(side="right", padx=(0, 6))
```

## The regression test (`tests/test_configwindow_init.py`)

A deliberate, narrow exception to this codebase's no-UI-test precedent: an `__init__`-time crash
can ONLY be caught by actually instantiating `ConfigWindow` with a real `Watcher` — source
review and mocked unit tests both passed while the app was unlaunchable (that is precisely the
coverage gap that let Mission 6B's defect through). The `Watcher` is constructed but never
`.start()`ed, so no background thread and no kill logic runs; each test destroys its Tk window.

Two cases:
- empty `watchdogs` list;
- one ENABLED watchdog (exercises `_tick_status`'s loop path, not just the empty-list early-out).

Both assert construction did not raise, `toggle_btn` exists, and the watcher thread was never
started; then `win.root.destroy()` cleans up.

## Validation (observed)

- `python -c "import ast;ast.parse(...)"` → `UI OK`
- `python -c "import watchdog_ui;print('IMPORT OK')"` → `IMPORT OK`
- `python -m unittest tests.test_configwindow_init -v` → `Ran 2 tests ... OK` (real Tk
  instantiation on the real Windows desktop session; no virtual display needed; a pre-existing
  PIL ResourceWarning from `load_logo_img` appears but does not fail)
- `python -m unittest discover -s tests -t . -v` → **Ran 89 tests ... OK** (87 prior + 2 new)
- `git diff -- watchdog_ui.py` → only the reordering shown above
- `git status --short` → `M watchdog_ui.py`, `?? tests/test_configwindow_init.py` (plus docs)

## Confirmation the app now starts

Real source-level launch (the same `main()` path that crashed in 6B):
`Start-Process python watchdog_app.py` → process stayed alive 12+ seconds
(`exited: False`), started hidden to tray as expected (`MainWindowTitle: []`),
and `%USERPROFILE%\.process_watchdog\crash.log` was byte-for-byte unchanged
(1400 bytes before and after — no new crash entry). It was then stopped via
`Stop-Process` (the documented forced-termination deviation — tray Quit is not
scriptable from the command line, same as Missions 1A/6B); the PID was confirmed
gone and `tasklist` reported no remaining `ProcessWatchdog.exe`.

Packaged-build note: this confirmation ran from source. The packaged-exe smoke test belongs to
Mission 6B's re-run.

## Explicit note: Mission 6B must be RE-RUN

This mission fixes the blocker but does NOT itself re-run Mission 6B's release-QA gate. Once
this lands, Mission 6B (full suite, fresh `build.bat`, resource measurement against the Mission
1A baseline, and the Part 3 functional checklist) must be re-run from a fresh build; only after
that passes can the punch board's Final acceptance gate be declared met.
