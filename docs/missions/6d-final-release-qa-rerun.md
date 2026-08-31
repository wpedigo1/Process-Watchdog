# Mission 6D — Final Release QA Re-Run (Post-6C Fix)

Mission 6B's exact scope, re-run against fixed code at `main@51be967`.

## Overall result: FAIL as a release gate — four genuine defects found

Part 1 (suite), Part 2 (build + resources + smoke), and Part 4 (repository) all PASS. Part 3
functional verification found **four defects** (one of them breaks the core feeding feature
end-to-end). Per the mission's hard boundary, nothing was fixed here; each defect is reported
precisely below and needs its own focused follow-up mission.

---

## Defects found (in verification order)

### DEFECT 1 — Picker lists Process Watchdog's own parent process (display level)

While the freshly built exe ran as its PyInstaller parent/child pair (pids 31528/26168), a live
call to the picker's own data source returned:

```
groups_total: 28
processwatchdog_entries: [('ProcessWatchdog.exe', [('ProcessWatchdog.exe',
    'C:\\Users\\wpedi\\Process Watchdog\\dist\\ProcessWatchdog.exe')])]
```

`get_process_groups` (watchdog_core.py:517) excludes only `pid == os.getpid()` — the packaged
app's parent bootloader (different pid, same exe, and `processwatchdog.exe` is NOT in
`PROTECTED_PROCESS_NAMES`, watchdog_core.py:28) is listed in the picker. Display-level violation
of "Never show or target ProcessWatchdog.exe". Kill-boundary protection still holds
(`is_protected_entry` protects by `exe == sys.executable`). Scope: display only; severity: low.

### DEFECT 2 — Add Watchdog crashes: watchdogDialog.__init__ on watchdog=None

Real `add_watchdog()` call, observed twice (drive rev 4 and rev 6):

```
FAIL DEFECT2_add_watchdog_dialog_crash | AttributeError in watchdogDialog.__init__
    (watchdog=None): 'NoneType' object has no attribute 'get'
```

`watchdog_ui.py:300` calls `watchdog.get("name")` in the header label BEFORE the
`watchdog = watchdog or {}` normalization at :305. Introduced by Mission 5 (`2e87354`,
git -L verified). In the packaged app the exception is swallowed by Tk's callback handler, so
the Add Watchdog button silently does nothing. Minimal repro confirmed both paths:

```
--- Add path (watchdog=None) ---
AttributeError: 'NoneType' object has no attribute 'get'
--- Retrain path (watchdog=dict) ---
constructed OK, title: Retrain Some Dog
```

### DEFECT 3 — Retrain locked-entry crash + silent meal-target loss

`ProcessPicker.set_locked` passes `disabled=True` to `ttk.Treeview.item()` (watchdog_ui.py:224),
which is not a valid item option. Introduced by Mission 2 (`c36917b`, git -L verified). Two
observed consequences:

1. Real retrain of a watchdog WITH a watched_app:
```
FAIL DEFECT3_retrain_locked_entry_crash | TclError: unknown option "-disabled"
    (watchdog_ui.py:224 disabled=True)
```
2. Any watched-app selection in any dialog goes through `_watch_changed` -> `set_locked`, which
crashes AFTER `self.tree.delete(*self.tree.get_children())` — the meal list is emptied and never
refilled. In the real app the exception is swallowed and the user can still click Save, which
then persists the empty meal list. Observed in the retrain-ambiguous flow (the dialog constructs
fine without a watched app; the crash fires on selection):
```
WATCH_CHANGED_RAISED (defect #3, swallowed in real app): TclError unknown option "-disabled"
FAIL retrain_ambiguous_real_dialog_flow | name=QA Ambiguous Retrained watched=dogA.exe meal=[]
```
The pre-existing meal targets (`leftover.exe`, `qa_offline_app.exe` — both present in the dialog
before selection, `RETRAIN_DIALOG_KEPT_ENTRIES: ['leftover.exe', 'qa_offline_app.exe']`) were
silently dropped on save. **Data loss through the retrain UI.**

### DEFECT 4 — Feeding engine crashes on real descendants: no kill ever happens

The core feature is broken end-to-end. Observed live during the grace-kill test (drive rev 4,
real Watcher thread, real disposable processes):

```
Traceback (most recent call last):
  File "watchdog_core.py", line 478, in run
    result = kill_processes(kill_list, detail=True)
  File "watchdog_core.py", line 388, in kill_processes
    to_kill = {
  File "watchdog_core.py", line 391, in <dictcomp>
    if not _is_self(proc)
  File "watchdog_core.py", line 137, in _is_self
    if _norm_path(proc.info.get("exe")) == _norm_path(sys.executable):
AttributeError: 'Process' object has no attribute 'info'
```

Mechanism: `kill_processes` merges direct matches (from `psutil.process_iter`, which carry
`.info`) with descendants from `proc.children(recursive=True)` (plain `psutil.Process`, **no**
`.info`), then the protection filter at watchdog_core.py:388-394 reads `proc.info`/`_is_self`
on every entry. Any matched process with a child — which includes every PyInstaller-style
parent/child pair and essentially every multi-process app, the product's primary use case —
raises AttributeError, **the Watcher thread dies, and nothing is killed**. Observed aftermath:
dogA's surviving background processes stayed alive (3 before -> 2 after: only the WM_CLOSE'd
window process was gone), the leftover meal target stayed alive, the status never reached
"Eaten by". The 89-test suite passes because the kill tests fake child processes WITH `.info`
attributes — the tests encode a world real psutil does not provide.

Items 3/4/5 (grace-kill / unrelated-leftover / same-folder-neighbor) are BLOCKED by this
defect. The countdown status itself was verified working before the crash
(`status='Hungry — eating in 3s.'`).

---

## Part 1 — Full automated suite: PASS (89/89)

```
Ran 89 tests in 0.364s
OK
```
Complete `python -m unittest discover -s tests -t . -v` output: all 89 test methods `ok`
(including the two Mission 6C ConfigWindow instantiation tests; the only console noise is a
pre-existing PIL ResourceWarning from `load_logo_img`, non-failing). Source-level
`def test_` count = 89.

## Part 2 — Fresh build and resource comparison: PASS on every measured value

**Deps (pre- and post-build, identical to Mission 1A baseline, no drift):**
psutil 7.2.2, pystray 0.19.5, Pillow 12.2.0, pyinstaller 6.22.2 (Python 3.11.0,
OS 10.0.26200.9278).

**Build:** `build.bat` completed ("Build complete. Find it at dist\ProcessWatchdog.exe").
`git status --porcelain=v1 --untracked-files=all` after build: empty (artifacts gitignored).

**Executable size:** `dist\ProcessWatchdog.exe` = **31,528,986 bytes** vs ceiling 32,548,945
(+1 MB) -> **PASS** (1,019,959 bytes under; +28,617 vs baseline 31,500,369).

**Smoke + window opens (the step 6B never reached):** launched the exe with a temp
USERPROFILE (empty profile -> documented first-run path -> visible window; the real config was
never touched). Observed: process pair alive, `MainWindowTitle: Process Watchdog`, window rect
(182,182)-(698,681). The window demonstrably renders: 17 native child HWNDs enumerated inside
it (5+ `Button` controls in the button row, `Static` labels, a native spinbox, client-sized
`TkChild`), window background sampled at exactly (32,32,32) = dark palette `#202020` (the
system theme was dark, `AppsUseLightTheme 0x0` — the exe themed itself correctly), and the
48x48 logo region shows a 23-unique-color rendered patch at the exact expected client
position while flat background areas are 1 uniform color. No crash: real crash.log stayed
1400 bytes; the temp profile's own crash.log was never created. (Note: this session cannot
visually inspect images, so rendering was verified by measured pixel/child-window analysis;
all screenshots are saved as artifacts under the QA temp area for the reviewer.)
A duplicate instance accidentally launched by a failed tool call (second pair, started hidden
because the first instance had already created the temp config) was killed; noted for
completeness.

**Idle measurement** (normal launch, real profile read-only, hidden to tray, 35 s settle,
`python tools/measure_baseline.py`, complete output):

```
pid=2808  rss=8732672   num_threads=4  num_handles=100
pid=17560 rss=46600192  num_threads=9  num_handles=524
CPU: pid=2808  min=0.00 median=0.00 max=1.60 (n=12)
     pid=17560 min=0.00 median=0.00 max=0.00 (n=12)
mem: sample 1: 8716288 | 46551040
     sample 2: 8716288 | 46551040
     sample 3: 8716288 | 46551040
```

| Metric | Baseline (1A) | 6D observed | Ceiling | Verdict |
|---|---|---|---|---|
| exe size | 31,500,369 | 31,528,986 | 32,548,945 | PASS |
| child idle RSS | ~48,349,184 | 46,551,040-46,600,192 | ~53,349,184 | PASS (below baseline) |
| parent idle RSS | 8,736,768 | 8,716,288-8,732,672 | — | PASS (no regression) |
| CPU | 0.00/0.00/0.00 both | 0.00/0.00/0.00 child; 0.00/0.00/**1.60 max** parent | effectively idle | PASS (one 1.6% sample on the dormant bootloader; median 0.00; reported honestly) |
| threads | 4 / 9 | 4 / 9 | no new permanent threads | PASS |
| handles | 100 / 656 | 100 / 524 | — | PASS (fewer) |
| poll/grace defaults | 2.0 / 10.0 | source `DEFAULT_CONFIG` 2.0 / 10.0 | — | unchanged (source-level, same constraint as 1A) |

**Shutdown:** tray Quit is not scriptable from the CLI (documented deviation, same as 1A/6B):
`taskkill /PID 2808 /PID 17560 /F` -> both terminated; `tasklist` reported no instance.
Real config sha256 identical before/after the whole session; crash.log unchanged.

## Part 3 — Functional verification checklist

Method, stated plainly: UI behavior was driven in-process against the repo's real classes
(real ConfigWindow, real started Watcher, real modal dialogs via their actual command
callbacks, real Win32 animations) with real disposable processes built in the temp area from
`disposable_app.py` (`dogA.exe` + self-spawned no-window background child, `neighbor.exe` in
the same folder, `leftover.exe` in an unrelated folder). The real user config was never
touched (CONFIG_PATH patched to temp for the whole drive; real file hash-verified before and
after). Error popups were captured instead of displayed (the app's decision logic still ran;
every captured message printed). The OS file picker's return value was injected for the
Browse tests (the app's rejection logic under test ran for real). No real user application
was ever watched or killed.

1. **Migration — PASS.** The real config (legacy `rules` schema, 5 watchdogs) copied to temp
   and run through `load_config` with patched CONFIG_PATH:
   `raw_schema_key: rules`, 5 -> 5 watchdogs, every raw trigger+kill identity set == migrated
   meal_targets set per watchdog (5/2/2/2/2 identities, all `identical=True`), ids/names/
   enabled all kept, `all_identities_preserved: True`, copy unchanged after load, real config
   unchanged. (An initial "hash mismatch" was a case-bug in my own comparison script —
   uppercase vs lowercase hex — corrected and re-verified with both files byte-identical.)

2. **Add / Retrain / toggle / Rehome — FAIL (defects #2 and #3).**
   - Add: real `add_watchdog()` -> AttributeError (defect #2). FAIL.
   - Retrain (with watched_app): real `edit_watchdog()` -> TclError (defect #3). FAIL.
   - Retrain (ambiguous, no watched_app — the real legacy-user path): dialog opens, meal
     entries preserved and displayed (`RETRAIN_DIALOG_KEPT_ENTRIES: ['leftover.exe',
     'qa_offline_app.exe']` — including the not-currently-running `qa_offline_app.exe` under
     the kept-entries section), but selecting a watched app fires defect #3 and save then
     silently drops the meal targets (observed `meal=[]`). FAIL (data loss).
   - Toggle: **PASS** — `on='Call Dog Off Watch'`; after toggle: row `['QA Dog A','No',
     'Off watch.']`, label `'Put Dog on Watch'`; re-select + toggle back: `'Yes'`, label
     `'Call Dog Off Watch'`.
   - Rehome: **PASS** — real RehomeDialog, exact on-screen text captured:
     `['Rehome "QA Dog Temp"?', 'This removes the Watchdog and its meal list.\nThe dog cannot
     come back unless you train it again.']`; Keep Dog preserves the watchdog; Rehome Dog
     removes it; config saved to disk each time.
   - Observed non-defect UX wart, noted: `refresh_tree` clears the table selection after every
     toggle, so the dynamic label falls back to "Put Dog on Watch" until the user re-selects a
     row. Label logic itself is correct.

3. **Grace period / real kill — BLOCKED (defect #4).** The countdown genuinely works
   (`status='Hungry — eating in 3s.'` observed live from the real status renderer after the
   watched app's window closed), but the kill never happens: the Watcher thread dies inside
   `kill_processes` (traceback above), the watched app's background processes survive
   (3 before -> 2 after: only the window process the QA closed exited), and "Eaten by..."
   never displays. FAIL/BLOCKED pending the defect #4 fix mission.

4. **Unrelated selected leftover eaten — BLOCKED (defect #4).** leftover.exe (separate folder,
   unrelated process tree, explicit meal target) survived the grace period — because nothing
   at all was killed. FAIL/BLOCKED.

5. **Same-folder neighbor survives — UNVERIFIED at runtime (defect #4).** neighbor.exe
   (same folder as dogA.exe, never selected) survived — but vacuously, since no kill occurred.
   The scoping logic itself is covered by `test_same_directory_neighbor_is_not_killed`
   (mocked). Honest verdict: blocked, not verified in real conditions.

6. **Protected processes — PARTIAL.** Own process never appears in the picker (verified: the
   drive's own python.exe identity absent from the picker's live entries; also live-checked
   earlier with `python_entries: NONE`). Browse and manual protected-entry rejection —
   **PASS**, three real rejections with the exact Mission 3 message:
   `'svchost.exe' is Process Watchdog itself or a protected system process. It cannot be added
   as a target.` (System32 svchost.exe via Browse->leftovers, System32 csrss.exe via Browse->
   watched-app, and name-only `svchost.exe` via Add filename). A non-protected manual entry
   (`qa_dummy_app.exe`) was accepted and kept in the picker (name-only fallback path). BUT
   defect #1: the packaged app's own parent `ProcessWatchdog.exe` IS listed in its picker.
   Display-level FAIL on that sub-item.

7. **Main-window X / doghouse button hide, don't exit — PASS.** Both trigger the bite
   animation and hide (window `withdrawn` observed), the process keeps running, and reopening
   restores the full window: `GetWindowRgn` returns 0 (no residual region) and size 500x460.
   Both paths repeated twice. (X invoked via the real WM_DELETE_WINDOW protocol using
   WM_CLOSE; the doghouse path via the real button's command.)

8. **Tray Quit exits fully — UNVERIFIED.** The tray menu cannot be invoked from the CLI
   (same documented limitation as Missions 1A/6B); app shutdowns in this mission used the
   `taskkill` deviation with `tasklist`-verified cleanup. Not claimed.

9. **Start with Windows — PARTIAL.** The real HKCU Run key currently contains
   `Process Watchdog = C:\Users\wpedi\Process Watchdog\dist\ProcessWatchdog.exe` (REG_SZ) —
   the user's own setting, in exactly the format `set_startup_registered` writes, so the
   write path has demonstrably worked in practice. Read logic verified against the real key,
   read-only, frozen-simulated: `is_startup_registered()` -> True, and the real value equals
   the dist exe path. Source-level (non-frozen) guard verified: both functions no-op from
   source (False before and after a set-True attempt — no registry writes happened from
   source). The tray UI toggle round-trip itself is not scriptable -> UNVERIFIED; the user's
   real setting was deliberately left untouched.

10. **Light/dark theme + refresh on doghouse-leave — PASS.** Controlled, fully-restored
    registry flip inside the drive: with `AppsUseLightTheme=1` at construction the window
    rendered light (uniform (243,243,243) = `#F3F3F3`); flipping to 0 and leaving the
    doghouse (hide -> show), the window re-detected and re-rendered dark — post-show
    captures contain **49,636 dark-palette pixels vs 2 before** (19.3% of the window at the
    exact palette color), `root cget bg = #202020`, registry 0 before and after, and the
    registry was restored to its original value (verified). Two launch-level observations
    corroborate theme-following: the packaged exe rendered dark while the system was dark,
    and an earlier drive run rendered light during a genuinely-light system moment. Note: a
    single-sample spot check initially read light due to a foreign overlay window occluding
    that exact band on this busy desktop (~4% of the capture); whole-image palette-pixel
    counting is the evidence cited above. Also observed (cosmetic, non-blocking): the
    Trainer's Guide `Text` widget is not in `apply_theme`'s widget list, so its text area
    keeps Tk's default light background in dark mode; noted as an observation for the
    reviewer, not a gate item.

11. **Logo visibility — PASS** (measured, not eyeballed — this session cannot view images;
    screenshots saved as artifacts). Exact-position logo patches contain 1,024-2,304
    non-palette pixels (21-662 unique colors) in all four required windows: ConfigWindow
    (48x48), watchdogDialog (40x40, from the retrain-ambiguous dialog capture), Trainer's
    Guide (32x32), and the packaged exe's first-run window. Flat background areas measure
    exactly one uniform palette color.

12. **Every bite-animation path — PASS.** All five paths triggered: main-window X (x2),
    doghouse button (x2), guide Close button, guide X, guide 30-second timer expiration
    (real 30s wait, countdown title observed: `'Watchdog will eat this process in 30
    seconds'`). Every path hid/destroyed the window via the animation, and the window
    reopened/displayed normally afterwards with full rectangular shape
    (`GetWindowRgn` = 0, size 500x460; final full-window capture shows 49,701 palette
    pixels with a clean, complete window). GDI-object counter returned 0 before and after
    (the counter read is likely not valid from this context — noted as inconclusive; the
    no-residual-region + repeated-reopen evidence is the substantive check). Six animation
    runs total, no broken shapes.

Drive summary line (rev 6): `SUMMARY: 25/32 checks passed` — the 7 non-passing entries are
precisely the four defects (recorded as FAIL observations), the items_3_4_5_blocked marker,
and two measurement-artifact FAILs corrected post-hoc by whole-image analysis (theme-refresh
spot occlusion; logo control-region occlusion) as documented above.

## Part 4 — Repository cleanliness: PASS

`git status --porcelain=v1 --untracked-files=all` -> empty (clean tree throughout; build
artifacts gitignored; all QA scripts/artifacts lived in the temp area). `git log --oneline
main -25` shows exactly the mission sequence (51be967 6C, ba8e220 6B, 9e02665 6A, 112150a
5-FIX, 2e87354 5, bb856f4 4B, 72817e4 4A, 473bdc8 3B, f369477, 269a9f9 3, fb2a82c, c36917b 2,
865fc04 1D, ed53ad0, 4adda28 1C, afeb919, d0a29d9, 3423491, ba4807d, 6e77b40, 6c8ede7,
959d772, 035275b) — no stray commits, no accidental artifacts.

## Boundaries honored

- No source file was modified at any point (verification only; `git status` clean).
- No real user application was watched or killed; only disposable temp-built exes.
- The real `%USERPROFILE%\.process_watchdog\config.json` was never modified — sha256
  identical before and after the entire mission (the migration test ran on a copy).
- The user's existing Start-with-Windows Run value was deliberately left untouched.
- The system theme registry was flipped only inside the drive and restored to its original
  value (verified).
- All disposable processes cleaned up (verified none remain); no ProcessWatchdog.exe
  instance remains.

## Conclusion

The Final acceptance gate is **NOT met**. A focused follow-up mission (or sequence) must fix,
with regression tests that use REAL process/dialog shapes: defect #4 (feeding engine —
highest severity, core feature), defect #2 (Add dialog), defect #3 (locked-entry + silent
meal loss), and defect #1 (picker self-display), then re-run this QA. Parts 1, 2, and 4 pass
on every measured value; the resource budget is fully intact.
