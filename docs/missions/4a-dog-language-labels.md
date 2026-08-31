# Mission 4A — Dog Language: Labels, Table, Rehome Confirmation

Route: Big Pickle (OpenCode Zen)
Base: `main` @ `473bdc82713d3f53e4a8c6b74fd27897e198defb`
Scope: Mission 4 subset — Main controls rename, Rehome confirmation dialog,
Table headers, dynamic toggle label, dog-language status strings, tray menu
rename, and GUIDE_TEXT stale-button fix. Does NOT include richer
eaten/absent/failed Dog Status states (separate follow-up mission).

## Result: PASS

## String change inventory

### Buttons (watchdog_ui.py, ConfigWindow)

| Line (approx) | Old | New |
|---|---|---|
| button row | `"Edit"` | `"Retrain"` |
| button row | `"Toggle Enabled"` | `"Put Dog on Watch"` / `"Call Dog Off Watch"` (dynamic) |
| button row | `"Delete"` | `"Rehome Dog"` |
| button row | `"Hide to Tray"` | `"Hide Dogs in the Doghouse"` |
| button row | `"User Guide"` | `"Trainer's Guide"` |
| `"Add Watchdog"` | unchanged | unchanged |

### Table headings (watchdog_ui.py, ConfigWindow)

| Column | Old heading | New heading |
|---|---|---|
| name | `"Watchdog"` | `"Watchdogs"` |
| enabled | `"Enabled"` | `"Watching"` |
| status | `"Status"` | `"Dog Status"` |

### Dynamic toggle label (watchdog_ui.py)

- `self.toggle_btn` is a `tk.Button` stored as an instance attribute.
- `self.tree.bind("<<TreeviewSelect>>", ...)` calls `self._update_toggle_label()`
  whenever the tree selection changes.
- `_update_toggle_label()` reads `_selected_watchdog()`: if selected watchdog
  is enabled, label is `"Call Dog Off Watch"`; otherwise `"Put Dog on Watch"`.
  With nothing selected, defaults to `"Put Dog on Watch"`.
- Also called after `refresh_tree()` and at the end of `_tick_status()` so the
  label stays current after toggle/retrain/rehome actions.

### Status strings (watchdog_ui.py, _tick_status)

| Old | New |
|---|---|
| `"Disabled"` | `"Off watch."` |
| `"Watching"` (idle) | `"Waiting for app to open."` |
| `"Open: {names}{+N}"` | `"Waiting to eat: {names}{+N}."` |
| `"Killing in {N}s"` | `"Hungry — eating in {N}s."` |

### Rehome confirmation (watchdog_ui.py)

- New `RehomeDialog(tk.Toplevel)` class with body text:
  ```
  Rehome "{name}"?

  This removes the Watchdog and its meal list.
  The dog cannot come back unless you train it again.
  ```
- Two buttons: `"Keep Dog"` (cancel, safe default) and `"Rehome Dog"` (confirm).
- Keep Dog destroys the dialog with `self.result = False`; watchdog is untouched.
- Rehome Dog sets `self.result = True`; `delete_watchdog` proceeds with deletion.
- `WM_DELETE_WINDOW` (X button) wired to `_cancel` — same as Keep Dog.

### GUIDE_TEXT (watchdog_ui.py)

- `"EDIT / TOGGLE ENABLED / DELETE"` → `"RETRAIN / TOGGLE WATCH / REHOME DOG"`
- `"or remove it."` → `"or rehome it."`
- `"HIDE TO TRAY"` → `"HIDE DOGS IN THE DOGHOUSE"`
- Nothing else in GUIDE_TEXT changed.

### Tray menu (watchdog_app.py)

- `"Open Watchdog"` → `"Open the Doghouse"`
- `"Start with Windows"` — unchanged.
- `"Quit"` — unchanged.

## Validation actually run (observed)

```
python -c "import ast;ast.parse(open('watchdog_ui.py',encoding='utf-8').read());print('UI OK')"
→ UI OK

python -c "import ast;ast.parse(open('watchdog_app.py',encoding='utf-8').read());print('APP OK')"
→ APP OK

python -c "import watchdog_core, watchdog_ui, watchdog_app;print('IMPORT OK')"
→ IMPORT OK

python -m unittest discover -s tests -t . -v
→ Ran 70 tests in 0.044s OK
```

grep for stale strings: no occurrences of `"Edit"`, `"Toggle Enabled"`, `"Delete"`,
`"Hide to Tray"`, `"User Guide"`, `"Open Watchdog"`, or `"Turn Off"` remain as
user-facing button/menu/window text in `watchdog_ui.py` or `watchdog_app.py`.

## Not changed / out of scope

- `watchdog_core.py` — untouched (UI-layer mission).
- Per-target eaten/absent/failed Dog Status tracking — separate mission.
- GUIDE_TEXT content beyond the one stale section — Mission 6.
- Guide countdown timer and bite-animation behavior — Mission 6.
- No new dependency. `build.bat` was not run.
