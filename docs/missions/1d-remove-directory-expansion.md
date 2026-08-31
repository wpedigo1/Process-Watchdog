# Mission 1D — Remove Same-Directory-Neighbor Kill Expansion

Route: Big Pickle (OpenCode Zen)
Base: `main` @ `ed53ad0883335aa7524a7e54880514e63f0a38cb` (Mission 1C-VERIFY)
Scope: narrow slice of punch board Mission 3 Target behavior — the directory-expansion removal
ONLY. The full Mission 3 (Permanent protection, meal-list model) remains blocked on Mission 2.

## Result: PASS

## What was removed

In `kill_processes` in `watchdog_core.py`:

1. The `install_dirs` construction block — a set of every matched process's install directory.
2. The directory-expansion enumeration block — when `install_dirs` was non-empty, it enumerated
   ALL running processes via `psutil.process_iter` and added any process whose exe directory was
   equal to, or beneath, a matched process's install directory, regardless of whether that
   process was ever explicitly selected.

Both mechanisms are gone entirely (not gated behind a flag, not narrowed, removed).

The function now reduces to: find matches -> add each match and its recursive children to
`to_kill` -> exclude self via the Mission 1C `_is_self` single-merge-point filter (unchanged) ->
kill what remains. The function's docstring was updated to drop the now-false claim about killing
"every OTHER running process installed in the same folder"; the stale inline comment above the
self-exclusion filter was corrected to name only the two kill sources that remain (direct matches
and descendants). The self-exclusion filter logic itself is byte-for-byte unchanged, as is the
final kill loop's `NoSuchProcess`/`AccessDenied` exception handling.

`find_matching_processes`, `_is_self`, `watchdog_ui.py`, `watchdog_app.py`, and the kill loop's
exception handling were not touched.

The full diff is captured below (raw `git diff -- watchdog_core.py`):

```diff
diff --git a/watchdog_core.py b/watchdog_core.py
index 4772e47..1308e0f 100644
--- a/watchdog_core.py
+++ b/watchdog_core.py
@@ -222,18 +222,9 @@
 def kill_processes(entries):
     """Force-kill every running process matching the given identity entries,
-    plus:
-      - every descendant in its process tree (spawned child/helper processes)
-      - every OTHER running process installed in the same folder (catches
-        helper services that aren't actual child processes — just separate
-        binaries living next to the main exe).
+    plus every descendant in its process tree (spawned child/helper processes).
     Returns count killed."""
     matched = find_matching_processes(entries)
-    install_dirs = set()
-    for proc in matched:
-        exe = proc.info.get("exe")
-        if exe:
-            install_dirs.add(os.path.dirname(exe).lower())
 
     to_kill = {}
     for proc in matched:
@@ -244,23 +235,11 @@
         except (psutil.NoSuchProcess, psutil.AccessDenied):
             continue
 
-    if install_dirs:
-        for proc in psutil.process_iter(attrs=["pid", "exe"]):
-            try:
-                exe = proc.info.get("exe")
-                if not exe:
-                    continue
-                exe_dir = os.path.dirname(exe).lower()
-                if any(exe_dir == d or exe_dir.startswith(d + os.sep) for d in install_dirs):
-                    to_kill[proc.info["pid"]] = proc
-            except (psutil.NoSuchProcess, psutil.AccessDenied):
-                continue
-
     # Never terminate Process Watchdog itself. Filter once at the point
-    # where all three kill sources (direct matches, descendants, and other
-    # binaries installed beneath a matched project) have already merged, so
-    # self is excluded from the kill set entirely — there is exactly one
-    # place to verify, and self can never be reached via any source path.
+    # where all kill sources (direct matches and descendants) have already
+    # merged, so self is excluded from the kill set entirely — there is
+    # exactly one place to verify, and self can never be reached via any
+    # source path.
     to_kill = {pid: proc for pid, proc in to_kill.items() if not _is_self(proc)}
 
     killed = 0
```

## Acceptance criteria

1. **Renamed/inverted** `test_same_directory_neighbor_is_killed_current_behavior` ->
   `test_same_directory_neighbor_is_not_killed`. Now asserts `result == 1` and
   `neighbor.kill_calls == 0` — the neighbor is no longer in the kill set.
2. **Already covered by unchanged tests.** `test_directly_matched_processes_are_selected` and
   `test_recursive_children_selected` both still pass with unchanged assertions, proving direct
   matches and recursive children are killed normally. No new test was added for this; the two
   existing unchanged tests cover it.
3. **New test** `test_kill_processes_does_not_call_process_iter` asserts, via a Mock, that
   `kill_processes` does not call `watchdog_app.psutil.process_iter` at all for a plain
   direct-match scenario. Since the ONLY caller of `process_iter` inside `kill_processes` was the
   removed directory-expansion block, this proves the enumeration path is actually gone, not just
   its result ignored.
4. **Mission 1C's three self-exclusion tests still pass.** The third one,
   `test_self_excluded_when_reached_via_install_directory_expansion`, could no longer test what
   its name said because the install-directory-expansion path was removed. It was RENAMED to
   `test_self_excluded_when_reached_as_recursive_child` and now proves the same invariant across
   the only non-direct kill source remaining after this mission: a self-owned process returned as
   a recursive child of a legitimately matched target is still excluded. It was not deleted;
   self-protection coverage is retained for both direct-match (criterion-4 tests 1 and 2) and
   descendant sources. The other two Mission 1C tests
   (`test_own_pid_is_excluded_from_kill`, `test_self_excluded_by_exe_path_even_with_different_pid`)
   are unchanged and still pass.
5. **Full suite passes** with an adjusted, explained count: 42 baseline -> 43. Timeline:
   42 baseline; `test_same_directory_neighbor_is_killed_current_behavior` -> renamed (no net
   change); `test_self_excluded_when_reached_via_install_directory_expansion` -> renamed (no net
   change); +1 new `test_kill_processes_does_not_call_process_iter` = 43. No other existing
   test's assertions changed.

## Test count and names (tests/test_kill_selection.py — 10 tests, all pass)

- test_directly_matched_processes_are_selected (unchanged)
- test_recursive_children_selected (unchanged)
- test_same_directory_neighbor_is_not_killed (RENAMED + INVERTED)
- test_kill_processes_does_not_call_process_iter (NEW)
- test_kill_raising_no_such_process_not_counted (unchanged)
- test_kill_raising_access_denied_not_counted (unchanged)
- test_same_pid_reached_by_direct_match_and_child_killed_once (unchanged)
- test_own_pid_is_excluded_from_kill (unchanged)
- test_self_excluded_by_exe_path_even_with_different_pid (unchanged)
- test_self_excluded_when_reached_as_recursive_child (RENAMED, was ..._via_install_directory_expansion)

## Validation (raw output)

Baseline (before change): `python -m unittest discover -s tests -t . -v` — `Ran 42 tests ...
OK`.

After change:
```
python -c "import ast;ast.parse(open('watchdog_core.py',encoding='utf-8').read());print('CORE SYNTAX OK')"  -> CORE SYNTAX OK
python -c "import watchdog_core;print('CORE IMPORT OK')"                                                     -> CORE IMPORT OK
python -m unittest discover -s tests -t . -v                                                                  -> Ran 43 tests ... OK
```

`python -m unittest tests.test_kill_selection -v` — 10 tests, all ok.

`git status --short`:
```
 M tests/test_kill_selection.py
 M watchdog_core.py
```

`git diff --stat`:
```
 tests/test_kill_selection.py | 45 +++++++++++++++++++++---------
 watchdog_core.py             | 31 ++++++-------------------
 2 files changed, 34 insertions(+), 42 deletions(-)
```

## Confirmation of unchanged behavior

- Direct matches and recursive children are still killed (unchanged tests).
- Self-exclusion (Mission 1C `_is_self`) is unchanged and still passes for own-PID, exe-path,
  and descendant sources.
- `find_matching_processes` matching semantics (exact-path vs. name-only fallback) untouched.
- No trigger/visibility logic touched. `watchdog_ui.py` / `watchdog_app.py` untouched.
- No dependency added; `build.bat` NOT run.
