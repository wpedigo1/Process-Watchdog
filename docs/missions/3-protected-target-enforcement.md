# Mission 3 — Protected-Target Enforcement + Offline Watch-App Entry

Route: Big Pickle (OpenCode Zen)
Base: `main` @ `fb2a82c1fd10ceb9bb4ad1f6ea752b5722b91b7d` (Mission 2-FIX)
Scope: the punch-board Mission 3 "Permanent protection" slice — enforce
system/self protected-target rejection inside the core engine, not only the UI,
and apply it to the picker/browsing/manual entry paths. Also closes the Mission 2
gap where Browse-for-.exe / manual entry only existed on the Eat These Leftovers
section, not the Watch This App section.

## Result: PASS

## Root cause / motivation

A protected or self identity could still be fed/added in three ways:

- `kill_processes` only filtered `_is_self`. Any protected identity that reached
  a watchdog's `meal_targets` through Browse, manual entry, or a legacy config
  would actually be killed.
- `_browse_exe` / `_add_manual` in `watchdogDialog` called
  `self.meal_picker.add_manual(...)` directly with zero protection check, so a
  user could browse to `csrss.exe` or anything under
  `C:\Windows\System32\` and add it as a kill target with no warning.
- `is_system_process` requires a live `psutil` process (`.info["username"]`),
  so it could not be applied to an offline Browse/manual entry that only has a
  name and a path.

## What changed

### `watchdog_core.py`

- New shared module constant `PROTECTED_PROCESS_NAMES`, extracted verbatim from
  the name-list that was inlined in `is_system_process`. `is_system_process`
  now reads from it. Its live-process (username) logic and control flow are
  otherwise unchanged.
- New `is_protected_entry(entry)` — an identity-only check (no live process)
  that returns True when the `{"name","exe"}` identity is Process Watchdog
  itself or a protected core OS executable/path:
  - `exe` (normalized) equals normalized `sys.executable`;
  - or `exe` empty and `name` (lowercased) equals the basename of
    `sys.executable`;
  - or `exe` contains any `SYSTEM_PATH_HINTS` substring;
  - or `name` is in `PROTECTED_PROCESS_NAMES`.
  - False otherwise. The protected-name list is not expanded.
- `kill_processes` hardened: the self filter now also rejects
  `is_protected_entry(...)` at the same single merge point where all kill
  sources (direct matches and descendants) converge — `to_kill` is filtered by
  `not _is_self(proc) and not is_protected_entry({...})`. Nothing else in
  `kill_processes` was touched.

### `watchdog_ui.py`

- Imported `is_protected_entry` from `watchdog_core`.
- `ProcessPicker.add_manual` now handles single-select (`selectmode="browse"`)
  pickers: a manually added entry replaces the current selection instead of
  appending to it. Multi-select (`extended`) behavior is unchanged.
- `watchdogDialog._browse_exe` and `_add_manual` now check
  `is_protected_entry` before `meal_picker.add_manual(...)`; a protected entry
  shows a `messagebox.showerror` and is not added. The check covers both
  name-only and full-path entries.
- Added the same Browse-for-.exe button + manual-filename entry to the Watch
  This App section, wired to `self.watch_picker.add_manual(...)` with the
  identical protection check. Because `watch_picker` is single-select, the new
  offline entry replaces any existing single selection, and `_watch_changed` is
  called so the lock-the-leftovers behavior fires exactly as it does for a live
  selection.

## Deliberate decision: migration NOT touched

Migrated data is preserved as-is. Legacy configs are intentionally not
rewritten here. Regardless of what survives in a legacy config, the core kill
engine (`kill_processes`) is the authoritative backstop: any protected or self
identity that reaches `meal_targets` is refused at feed time. This is a
deliberate decision, not a gap — enforcement lives in the engine, not the
migration.

## Tests

Test suite went from 58 (baseline) to 64 (PASS on all 64).

- New `tests/test_protected.py` — `IsProtectedEntryTests`, covering the five
  `is_protected_entry` acceptance criteria:
  - self by exe path → True;
  - self by name-only → True;
  - path under every `SYSTEM_PATH_HINTS` directory → True;
  - every `PROTECTED_PROCESS_NAMES` name (name-only) → True;
  - an ordinary app → False.
- `tests/test_kill_selection.py` — added
  `test_protected_system_identity_is_never_killed`, which proves a matched
  entry resolving to a protected `System32` identity (explicitly NOT self) is
  never killed — the defense-in-depth gap that `_is_self` alone would not have
  caught. All existing kill-selection tests pass unchanged.

## Edge cases handled

- A protected identity added with a full path and the same app added by
  name-only are both rejected.
- Self is protected by both exact exe path and name-only (the latter covers a
  resolved process whose exe is unavailable).
- A name-only protected OS process (e.g. `csrss.exe`) with no path is rejected.
- An ordinary user application under Program Files is unaffected.
- Single-select watch picker: adding via Browse/manual replaces the prior
  selection rather than accumulating multiple watched-app identities.

## Validation actually run (observed)

- `python -c "import ast; ast.parse(open('watchdog_core.py',encoding='utf-8').read())"` → CORE OK
- `python -c "import ast; ast.parse(open('watchdog_ui.py',encoding='utf-8').read())"` → UI OK
- `python -c "import watchdog_core, watchdog_ui, watchdog_app"` → IMPORT OK
- `python -m unittest discover -s tests -t .` → Ran 64 tests, OK
- `git status --short`, `git diff --stat` reviewed; diff is focused on
  `watchdog_core.py`, `watchdog_ui.py`, `tests/test_protected.py` (new), and
  `tests/test_kill_selection.py`.

## Not changed / out of scope

- `is_system_process`'s live-process (username) logic — only its name-list
  constant was extracted for reuse.
- `find_matching_processes`, `open_trigger_names`, `Watcher`,
  `effective_trigger`, `effective_kill`, and `get_process_groups`'s existing
  pid/system-process filtering.
- Config migration in this mission (see deliberate-decision note above).
- Mission 4/5/6 language, theming, animation — not implemented.
- No new dependency added. `build.bat` was not run.
- Supporting docs (`AGENTS.md`, `CLAUDE.md`, `BASELINE.md`) were not modified.
