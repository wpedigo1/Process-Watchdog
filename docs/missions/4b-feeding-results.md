# Mission 4B — Eaten/Absent/Failed Feeding Results

Route: Big Pickle (OpenCode Zen)
Base: `main` @ `72817e4fceb1ca274dad856a922db2228f0ba59a`
Scope: Mission 4 Dog Status states that require per-target feeding result
tracking — eaten, nothing-left-to-eat, partial-failure, access-denied — with a
result that stays visible until the watched app is observed open again.

## Result: PASS

## What changed

### `watchdog_core.py`

- New `KillResult` class with `.killed` and `.failed` lists (sorted,
  deduplicated process names).
- `kill_processes(entries, detail=False)` — new optional parameter, default
  behavior identical: `detail=False` returns the same int count as before.
  `detail=True` additionally records, at the existing single kill loop:
  - `killed`: names actually terminated successfully;
  - `failed`: names that reached the kill attempt (not filtered out by
    `_is_self`/`is_protected_entry`/`_is_protected_owner`) but raised
    `AccessDenied` on `.kill()`.
  `NoSuchProcess` during kill is silently not counted, exactly as before.
  Processes excluded by the protection filters are invisible to reporting too.
  Returns a `KillResult` when `detail=True`.
- `Watcher.run()`: calls `kill_processes(kill_list, detail=True)` and invokes
  `self.on_kill(...)` on EVERY grace-elapse event (including zero results). The
  callback signature became `(rid, name, killed, failed)`. `rid` is added so
  the UI can key the result by watchdog id. No other part of `Watcher` changed.

### `watchdog_app.py::main`

- `on_kill(rid, name, killed, failed)` now calls
  `config_window.root.after(0, config_window.record_kill_result, rid, name, killed, failed)`.
  This uses the same late-binding closure pattern as `get_config` and marshals
  the background-thread callback onto the Tkinter thread via `root.after`.

### `watchdog_ui.py` — `ConfigWindow`

- New `self._last_result` dict: watchdog_id -> `{"name", "killed", "failed"}`.
  In-memory only; a plain instance attribute, so it resets naturally on
  restart.
- New `record_kill_result(rid, watchdog_name, killed, failed)` — stores the
  result; only ever called through the `root.after` marshal.
- `_tick_status` precedence per watchdog:
  1. disabled -> `"Off watch."`
  2. pending -> `"Hungry — eating in {N}s."`
  3. open -> `"Waiting to eat: ..."` AND clears `_last_result[rid]` (fresh open
     retires the previous result)
  4. stored result -> rendered via `_render_result`
  5. else -> `"Waiting for app to open."`
- `_render_result` builds the message from the stored killed/failed lists.
- `_show_result_details` — `<<Double-1>>` on the tree opens a `messagebox.showinfo`
  with the full untruncated killed/failed lists for the selected watchdog.

## Exact message templates

- Killed only: `f"Eaten by {watchdog_name}: {shown}{'+N' if truncated}."`
- Failed only: `f"Couldn't eat: {shown}{'+N' if truncated} (access denied)."`
- Partial (both): `f"Eaten by {watchdog_name}: {killed}. Couldn't eat: {failed} (access denied)."`
- Both empty: `"Nothing left to eat."`
- `+N` truncation: show first 2 names, `+N` for the rest — applied to `killed`
  and `failed` independently (reuses existing pattern).

## Tests

Suite went from 70 (baseline) to 78 (PASS on all 78).

- `test_kill_selection.py`:
  - `test_detail_false_returns_int_unchanged` — criteria 1 (default int return).
  - `test_detail_true_successful_kill_lists_killed` — criterion 2.
  - `test_detail_true_access_denied_lists_failed` — criterion 3.
  - `test_detail_true_no_match_both_empty` — criterion 4.
  - `test_detail_true_protected_identity_invisible` — criterion 5.
  - `test_detail_true_dedupes_and_sorts_names` — dedupe/sort of `.killed`.
- `test_watcher.py`:
  - Updated `_drive` helper mock return to `KillResult([], [])` and the
    `mock_kill.assert_called_once_with(..., detail=True)` assertion.
  - `test_kill_called_with_detail_true` — criterion 6a.
  - `test_on_kill_fires_even_with_nothing_found` — criterion 6b.

## Default contract confirmation

`kill_processes(entries)` with no `detail` argument returns an int, exactly as
before this mission. All pre-existing tests calling it without `detail=True`
pass completely unchanged — their assertions were not edited.

## UI wiring (by inspection)

- `main()` `on_kill` -> `config_window.root.after(0, ...)` -> `record_kill_result`
  (thread-safe, never touches UI directly from the watcher thread).
- `_tick_status` reads `_last_result` on the Tkinter thread each tick.
- Double-click on a row -> `_show_result_details` -> `messagebox.showinfo` with
  full lists.

## Validation actually run (observed)

```
python -c "import ast;ast.parse(open('watchdog_core.py',encoding='utf-8').read());print('CORE OK')"
→ CORE OK

python -c "import ast;ast.parse(open('watchdog_ui.py',encoding='utf-8').read());print('UI OK')"
→ UI OK

python -c "import ast;ast.parse(open('watchdog_app.py',encoding='utf-8').read());print('APP OK')"
→ APP OK

python -c "import watchdog_core, watchdog_ui, watchdog_app;print('IMPORT OK')"
→ IMPORT OK

python -m unittest discover -s tests -t . -v
→ Ran 78 tests in 0.048s OK
```

## Not changed / out of scope

- `kill_processes` default (`detail=False`) behavior and return type — unchanged.
- `_is_self`, `is_protected_entry`, `_is_protected_owner`, `find_matching_processes`,
  `open_trigger_names`, `effective_trigger`, `effective_kill` — untouched.
- `Watcher` trigger-transition / grace-period logic — untouched.
- Feeding results never persisted to `config.json` — in-memory only.
- No new dependency. `build.bat` was not run.
