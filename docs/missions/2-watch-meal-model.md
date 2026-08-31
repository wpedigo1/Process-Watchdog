# Mission 2 — Train and Retrain Watchdogs (watch/meal model)

Route: Big Pickle (OpenCode Zen)
Base: `main` @ `865fc04cd5948131d7a5ea98e2db04226056719a` (Mission 1D)
Scope: the punch-board Mission 2 slice — split the single kill list into a
one-watched-app (`watched_app`) + `meal_targets` model, add the Train/Retrain
dialog with distinct Watch / Eat sections, and migrate legacy configs without
data loss. This also closes two Mission 3 items that were "blocked on Mission 2":
the meal-list model and Train/Retrain.

## Result: PASS

## Root cause / motivation

A watchdog previously stored one flat `trigger`/`kill` list, and the picker
forced the watched app and the leftover kill targets to be identical. There was
no way to say "watch A, but also eat unrelated leftovers B and C" — exactly the
trip-wire the punch board wanted. This change introduces a distinct watched-app
identity (`watched_app`) plus a separate leftovers list (`meal_targets`), and a
two-section Retrain dialog that lets the user pick one app to watch and any
number of leftovers to eat.

## Extra reader found during investigation

The reader audit for `Watcher.run()` also surfaced a second reader:
`watchdog_ui.py`'s `watchdogDialog.__init__` previously read
`watchdog.get("trigger") or watchdog.get("kill")` to pre-fill the picker. The
Retrain dialog now pre-fills from `watchdog.get("watched_app")` /
`watchdog.get("meal_targets")` instead. This reader was accounted for and
removed along with the dialog redesign. (Other readers of the old keys live only
in the migration path itself, which is intended.)

## What changed

### `watchdog_core.py`

New schema per watchdog: `watched_app: {"name","exe"} | null` and
`meal_targets: [{"name","exe"}, ...]`.

- `_entry_key(e)` — dedup identity `(normalized name, normalized exe)`; both
  `""` and `None` normalize to `''` so a name-only entry never collides with an
  exact-path entry of a different name.
- `_dedupe_entries(entries)` — order-preserving dedup by `(name, exe)`.
- `effective_trigger(watchdog)` — `[watched_app]` when set, else `[]`
  (a `watched_app: null` watchdog never triggers until Retrain).
- `effective_kill(watchdog)` — `dedup([watched_app] + meal_targets)` when a
  watched app is set; `meal_targets` verbatim (no dedup) when it is null.
- `_migrate_watchdog(watchdog)` — in-place per-watchdog migration, called from
  `load_config` after the existing per-entry normalization loop:
  - already migrated (`watched_app` present): drop leftover `trigger`/`kill`,
    normalize, and ensure `meal_targets` never duplicates the watched app;
  - exactly 1 distinct `(name, exe)` in `trigger`: that becomes `watched_app`;
    `meal_targets` = `kill` minus the watched app, deduped;
  - 0 distinct in `trigger`: `watched_app = null`, `meal_targets` = `kill`
    unchanged (ambiguous — needs Retrain);
  - 2+ distinct in `trigger`: `watched_app = null`, `meal_targets` =
    `dedup(trigger + kill)` (ambiguous — needs Retrain).
- `Watcher.run()` now reads `effective_trigger(watchdog)` and
  `effective_kill(watchdog)` instead of the legacy `trigger`/`kill` keys.
- `get_process_groups` now requests `pid` in `attrs` and excludes
  `proc.info.get("pid") == os.getpid()` so Process Watchdog's own running
  instance is never offered as a selectable target (picker self-exclusion).

`kill_processes`, `find_matching_processes`, `open_trigger_names`, and `_is_self`
were not touched.

### `watchdog_ui.py`

- `ProcessPicker`: removed the "Hide system processes" checkbox and its
  `BooleanVar`; `get_process_groups` is now always called with `hide_system=True`
  (system processes are unconditionally hidden). Added optional `selectmode`
  (single-select for the Watch picker), `hint`, `locked` (a disabled,
  always-present identity for the watched app), an `on_select` callback, a
  `set_locked(...)` method, and an `add_manual(name, exe)` method that keeps
  manually/browsed identities available across refreshes.
- `watchdogDialog` → Train/Retrain dialog:
  - heading **Train a Watchdog** when adding, **Retrain {name}** when editing;
  - **Watch This App** section — single-select;
  - **Eat These Leftovers** section — multi-select, with the watched app shown
    as a locked, always-eaten entry;
  - **Browse for .exe…** via `tkinter.filedialog` (`*.exe` filter) and a
    filename-only manual entry fallback (name-only matching);
  - dedupe by `(name, exe)`; validation errors for an empty name and for a
    missing watched app;
  - `_save` writes `watched_app` / `meal_targets` (not `trigger` / `kill`).
- Kept Filter and Refresh.

## Edge cases handled

- `watched_app: null` never triggers (verified at the watcher level).
- Ambiguous legacy watchdogs (0 or 2+ distinct trigger identities) are preserved
  intact rather than guessed at, and must be resolved during Retrain.
- Already-migrated configs pass through load unchanged, minus any
  `meal_targets` that duplicate the watched app.
- The watched app is always an implicit kill target and never duplicated in
  `meal_targets`.

## Tests

Test suite went from 43 (baseline) to 56 (PASS on all 56).

- Updated to the new schema: `tests/test_config.py`
  (`test_load_config_normalizes_legacy_string_entries_into_watched_app_and_meal_targets`,
  the save/load round-trip, and the valid-JSON check),
  `tests/test_config_migration.py` (legacy `rules` assertion), and
  `tests/test_watcher.py` (`_make_watchdog` now uses `watched_app`/`meal_targets`,
  plus a new `test_null_watched_app_never_triggers`).
- New coverage:
  - `tests/test_config_migration.py` — migration edge cases (single-distinct
    trigger → watched_app; zero-distinct → null watched_app; multi-distinct →
    null watched_app + combined meal; meal_targets never duplicate the watched
    app; already-migrated pass-through).
  - `tests/test_watch_meal_model.py` — `effective_trigger`, `effective_kill`
    (dedup with watched app, verbatim without, watched-app-always-a-kill-target),
    and `get_process_groups` self-exclusion (`pid == os.getpid()` never appears).

## Validation actually run (observed)

- `python -c "import ast; ast.parse(open('watchdog_core.py',encoding='utf-8').read())"` → CORE OK
- `python -c "import ast; ast.parse(open('watchdog_ui.py',encoding='utf-8').read())"` → UI OK
- `python -c "import watchdog_core, watchdog_ui, watchdog_app"` → IMPORT OK
- `python -m unittest discover -s tests -t .` → Ran 56 tests, OK
- `git status --short`, `git diff --stat` reviewed; diff is focused on
  `watchdog_core.py`, `watchdog_ui.py`, three test files, and one new test file.
- Residual old-schema reads confirmed only inside the migration path
  (`watchdog_core.py` `_migrate_watchdog` / the `load_config` normalization loop).

## Not changed / out of scope

- `kill_processes`, `find_matching_processes`, `open_trigger_names`, `_is_self`,
  visible-window trigger logic, process matching semantics.
- SYSTEM/protected-path expansion beyond the existing `is_system_process` hiding
  (that is a separate, still-open Mission 3 item).
- `pyinstaller`, `build.bat`, or packaged artifacts were not built.
- Supporting docs (`AGENTS.md`, `CLAUDE.md`, `BASELINE.md`) were not modified.
