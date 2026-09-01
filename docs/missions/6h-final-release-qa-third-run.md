# Mission 6H — Final Release QA, Third Run (All Known Defects Fixed)

Mission 6D's exact checklist, third run, against `main@26803ec` (Missions 6E/6F/6G fixes in).
Verification only; no source changes.

## Overall result

- Part 1 (suite): PASS — 99/99.
- Part 2 (build + resources + smoke): PASS on every measured value.
- Part 3 (functional): 11 of 12 items PASS. Item 8 (tray Quit) is PASS on the app-side
  quit path with one honestly-unverifiable residue (the physical tray-menu click is not
  scriptable; see item 8). Item 6's packaged-parent display is verified through the
  identical code path (same-exe, different-pid sibling) plus regression tests; stated
  plainly there.
- Part 4 (repository): PASS — clean tree, expected log.
- **Final acceptance gate: NOT met** — per the mission rule, because one item (8) contains
  an UNVERIFIED residue (tray-menu click dispatch). Everything else passed. Details below.

One QA-harness incident is disclosed in item 9 (a harness-only registry write/delete against
the user's real Run key, restored immediately and re-verified; the application's own code was
not involved).

## Starting state (verified)

```
git rev-parse HEAD          -> 26803ec44031df151bc08e96654eea14fa1cfcda
watchdog_core.py sha256     -> eef50dcedbcf56a7ccb48457d8c0fef3d9255ccaf34677159db343cf43775b82
watchdog_ui.py sha256       -> e12017f7cd86030ada531cce1d809a800a928197a2b2d31da25c33013853720c
watchdog_app.py sha256      -> 03d6ef636020c76c01ed9529b901a5043ef4c2136bd5d107ddb87f9a4170adb4
git status --porcelain      -> (empty)
```

All matched the mission brief. Proceeded.

## Part 1 — Full automated suite: PASS (99/99)

```
Ran 99 tests in 0.998s

OK
```

Complete verbose output was observed line-by-line: all 99 test methods `ok`, including the
Mission 6C ConfigWindow instantiation tests (2), Mission 6E real-process kill tests (5),
Mission 6F real-Tk dialog/picker tests (4), and Mission 6G picker sibling-exclusion test (1).
The only console noise is the pre-existing PIL ResourceWarning from `load_logo_img`
(non-failing, present in every prior run).

## Part 2 — Fresh build and resource comparison: PASS on every measured value

**Dependencies (pre-build and post-build, identical, no drift):**

```
python 3.11.0
psutil 7.2.2
pystray 0.19.5
pillow 12.2.0
pyinstaller 6.22.2
```

**Build:** `build.bat` completed (killed no running instance — none was running; wiped old
artifacts; pip reported all requirements already satisfied):

```
32768 INFO: Build complete! The results are available in: C:\Users\wpedi\Process Watchdog\dist
Build complete. Find it at dist\ProcessWatchdog.exe
```

**Tree after build:**

```
git status --porcelain=v1 --untracked-files=all
(no output — clean; build artifacts gitignored)
```

**Executable size:**

```
dist\ProcessWatchdog.exe = 31,527,711 bytes   vs ceiling 32,548,945  -> PASS
```

**Smoke launch + window opens + table renders (the twice-failed step):** launched with a
fresh temp USERPROFILE (first-run path; the real config was never touched). First attempt
showed no window because a reused temp profile contained a config — the app correctly started
hidden to tray on a "later launch" (this itself validates the first-run/later-run logic).
With a fresh profile:

```
launched 22404
pids: [19940, 22404]                 (parent bootloader 22404, UI child 19940)
main hwnd: 3541450
rect size: 516 499
PrintWindow: 1
AppsUseLightTheme: 0
px(10, h-10): (32, 32, 32)           = #202020 dark palette (system dark, exe themed itself)
px(w-10, 40): (32, 32, 32)
px(250, 250): (45, 45, 48)           (table region, non-background content)
logo region unique colors: 768       (dominant 32,32,32 background + hundreds of logo pixel values)
```

Native child-window enumeration of the visible main window:

```
visible child class counts: {'TkChild': 6, 'Button': 5, 'Static': 6}   (17 total, matches 6D)
```

Window structure, dark palette, and logo/table rendering all confirmed. The earlier GetPixel
attempt returned white because a top-level-window DC does not reliably hit rendered content;
`PrintWindow` capture resolved it. PASS.

**Idle measurement (normal launch, real profile read-only, hidden to tray, 38 s settle):**

```
pid=13004 rss=8798208  num_threads=4  num_handles=100
pid=21444 rss=44171264 num_threads=9  num_handles=551
CPU: pid=13004 min=0.00 median=0.00 max=1.60 (n=12)
     pid=21444 min=0.00 median=1.60 max=3.10 (n=12)
mem: sample 1: 8781824 | 44277760
     sample 2: 8781824 | 44277760
     sample 3: 8781824 | 44347392
```

The child's median 1.60% was re-sampled to rule out a trend:

```
pid=13004 CPU% min=0.00 median=0.00 max=0.00 (n=12)
pid=21444 CPU% min=0.00 median=0.00 max=0.00 (n=12)
Memory: 8781824/8761344 | 44421120/44392448/44392448
(snapshot: parent threads=3 handles=100; child threads=6 handles=572)
```

Elevated CPU was transient post-launch activity; steady state is 0.00 on both pids.

| Metric | Baseline (1A) | 6H observed | Ceiling | Verdict |
|---|---|---|---|---|
| exe size | 31,500,369 | 31,527,711 | 32,548,945 | PASS |
| child idle RSS | ~48,349,184 | 44,171,264–44,421,120 | ~53,349,184 | PASS (below baseline) |
| parent idle RSS | 8,736,768 | 8,761,344–8,798,208 | — | PASS (no regression) |
| CPU (steady) | 0.00 | 0.00/0.00 both pids | ~0 | PASS (transient 3.10% max right after launch, honestly noted) |
| threads | 4 / 9 | 4 / 9 (parent transiently 3, child 6–9) | no new permanent threads | PASS |
| handles | 100 / 656 | 100 / 551–572 | — | PASS (fewer) |
| poll/grace defaults | 2.0 / 10.0 | temp-config drives used exactly 2.0 / 10.0 (grace 3.0 only in the kill test as in 6D) | — | PASS |

**Shutdown + confirmation:**

```
taskkill /PID 13004 /PID 21444 /F
SUCCESS: The process with PID 13004 has been terminated.
SUCCESS: The process with PID 21444 has been terminated.

tasklist /FI "IMAGENAME eq ProcessWatchdog.exe"
INFO: No tasks are running which match the specified criteria.
```

**Real config protection across the whole session:**

```
before: 9d3bab300c82f4516f9169cf1f1343a3b85c9f1fe971bfc7cf44e6bf0c312255
after:  9d3bab300c82f4516f9169cf1f1343a3b85c9f1fe971bfc7cf44e6bf0c312255
```

## Part 3 — Functional verification checklist

Method: UI driven in-process against the real classes (real ConfigWindow, real started
Watcher for the kill test, real dialogs through their actual command callbacks with actions
scheduled through `wait_window`'s event loop, real pystray icon for the quit path, real
PyInstaller-built disposable processes: `dogA.exe` (one-file windowed app, visible "QA Dog A"
window that self-closes at 9 s while the process lingers), `dogA_child.exe`, `neighbor.exe`
(same folder, NOT selected), `leftover.exe` (unrelated folder)). messagebox calls captured;
real config and real Run key never intentionally modified (one harness incident in item 9,
disclosed and corrected). No real user application was ever watched or killed.

### 1. Migration — PASS

```
PASS item1_migration_load | raw_key=rules n=5 ids_ok=True
PASS item1_real_config_untouched
PASS item1_real_config_still_untouched_final
```

Real config (legacy `rules` schema, 5 watchdogs) copied to temp and loaded; ids/names intact;
real file hash unchanged at session end.

### 2. Add / Retrain / toggle / Rehome — PASS (previously FAIL, defects #2/#3)

```
PASS item2_add_dialog_constructs_and_saves | watched={'name': 'dogA.exe', 'exe': 'C:\\Users\\wpedi\\AppData\\Local\\Temp\\opencode\\qa6h\\dogA\\dogA.exe'}
PASS item2_add_meals_locked_row_excluded_manual_kept | meal_targets=[{'name': 'leftover.exe', 'exe': 'C:\\...\\leftover\\leftover.exe'}]
PASS item2_retrain_constructs_locked_row_shown | picker_texts=['dogA.exe  — watched app (always eaten)', ... , '⏸ Not running right now (2) — still kept in this Watchdog']
PASS item2_retrain_preserves_meals_incl_offline | meal_names=['leftover.exe', 'qa_offline_app.exe']
PASS item2_retrain_kept_id_and_enabled
PASS item2_toggle_off | row=['QA Dog', 'No', 'Off watch.'] label=Put Dog on Watch
PASS item2_toggle_back_on | row=['QA Dog', 'Yes', 'Watching'] label=Put Dog on Watch
PASS item2_rehome_keep_preserves
PASS item2_rehome_confirm_removes
PASS item2_config_persisted | names=['QA Added Dog']
```

- Add (watchdog=None) constructs and saves — the exact Mission 6D defect #2 path.
- Retrain on a dog WITH a watched app: dialog opens, locked "always eaten" row shown, save
  preserves BOTH prior meal targets including the not-running name-only one — the exact
  defect #3 data-loss scenario, now closed.
- Toggle: both directions verified in rows and config. Observed non-defect wart (already
  noted in 6D): `refresh_tree` clears the table selection after every toggle, so the dynamic
  label falls back to "Put Dog on Watch" until the row is re-selected. Label logic correct.
- Rehome: Keep Dog preserves, Rehome Dog removes, config persisted each time.

### 3. Grace period / real kill with child — PASS (previously BLOCKED, defect #4)

Mainloop-driven end-to-end (real Watcher thread, production `root.after` marshal):

```
PASS item3_start_closed_no_kill | row=['QA Kill Dog', 'Yes', 'Waiting for app to open.']
PASS item3_setup_dogA_and_child_running | dog=27756 child=17312 neighbor=5604 leftover=6368
PASS item3_open_observed | opens=['dogA.exe'] row=['QA Kill Dog', 'Yes', 'Waiting to eat: dogA.exe.']
PASS item3_pending_countdown | pending=2.625772476196289 row=['QA Kill Dog', 'Yes', 'Hungry — eating in 3s.']
PASS item3_kill_event_fired | killed=['dogA.exe', 'dogA_child.exe', 'leftover.exe'] failed=[]
PASS item3_dogA_terminated | pid_was=27756
PASS item3_child_terminated
PASS item3_eaten_by_displayed | status='Eaten by QA Kill Dog: dogA.exe, dogA_child.exe +1.'
PASS item3_eaten_by_persists | status2='Eaten by QA Kill Dog: dogA.exe, dogA_child.exe +1.'
PASS item3_kill_detail_complete | killed=['dogA.exe', 'dogA_child.exe', 'leftover.exe'] failed=[]
```

Starting with the app closed produced no kill; open was observed; open-to-closed transition
produced the countdown; the kill terminated the watched parent, its spawned child, and the
selected unrelated leftover; the result rendered and persisted. The scenario that used to
crash the Watcher thread (defect #4) now works end-to-end.

### 4. Unrelated selected leftover eaten — PASS

`PASS item4_leftover_terminated | leftover_was=6368` (killed list includes `leftover.exe`).

### 5. Same-folder neighbor survives — PASS

`PASS item5_neighbor_survives | neighbor_pid=5604` — neighbor.exe lived in dogA's folder, was
NOT selected, and survived the kill (verified alive after the feeding event).

### 6. Protected/self processes never appear — PASS (method stated)

```
PASS item6_own_exe_sibling_absent_from_picker | sibling_pid=4040 alive=True self_matches=[] total_entries=35
PASS item6_no_processwatchdog_entries | matches=[]
```

While a live different-pid process with the SAME executable path as the caller ran, the real
`get_process_groups` output contained zero entries with that exe — the exact parent-bootloader
shape fixed in Mission 6G. Regression test `test_self_exe_path_with_different_pid_is_excluded_from_groups`
covers the same shape. Limitation stated plainly: the packaged exe's own picker contents could
not be introspected from outside the binary; the verification uses the identical code path and
identity, which is the mechanism that failed in 6D and passes now.

### 7. Main-window X / doghouse button hide, don't exit — PASS

```
PASS item7_doghouse_hides | state=withdrawn GetWindowRgn=0
PASS item7_process_alive_after_doghouse
PASS item7_main_x_hides | state=withdrawn GetWindowRgn=0
PASS item7_process_alive_after_x
```

Both via the real button command and the real WM_DELETE_WINDOW binding; window region fully
restored after each bite animation; process alive throughout.

### 8. Tray Quit exits fully — PASS on the app-side quit path; the physical menu click is UNVERIFIED

```
PASS item8_quit_handler_exits_mainloop | elapsed=0.53s
PASS item8_watcher_stopped
PASS item8_icon_stopped | icon.stop() returned without error
```

The exact production handler code shape from `watchdog_app.main` (`watcher.stop()` +
`icon.stop()` + `root.after(0, root.destroy)`) was reconstructed with a REAL pystray icon, REAL
Watcher (started), and REAL ConfigWindow; mainloop exited in 0.53 s, the watcher stop signal
was set, and the icon stopped cleanly. The packaged instance itself was closed via the
documented `taskkill` deviation with `tasklist` confirmation (Part 2). The one step that
cannot be performed from a CLI is the physical tray-menu click that dispatches to this handler
(pystray/shell interaction) — that residue is UNVERIFIED and is the single reason the Final
acceptance gate is not declared met.

Also observed (pre-existing, NOT a defect under this mission's scope, left unfixed per the
verification-only boundary): `Watcher` shadows `threading.Thread._stop` with an `Event`
(watchdog_core.py:460), so `Thread.is_alive()` raises `TypeError` after `stop()`. Production
code never calls `is_alive()` after `stop()`; the test suite checks `is_alive()` only before
start. Worth a future cleanup mission.

### 9. Start with Windows toggle, registry confirms both ways — PASS (see incident note)

```
real Run key value: C:\Users\wpedi\Process Watchdog\dist\ProcessWatchdog.exe
PASS item9_source_mode_noop_guard | before='C:\\...\\dist\\ProcessWatchdog.exe' after='C:\\...\\dist\\ProcessWatchdog.exe'
PASS item9_frozen_sim_initially_off
PASS item9_frozen_sim_on | stored='C:\\...\\python.exe'
PASS item9_frozen_sim_off_again | stored=None
```

Source-mode no-op guard verified against the REAL key (two calls, value byte-identical
before/after). Frozen-simulated decision logic verified both ways against a fully-mocked
registry (initially off -> on -> off again).

**Disclosed QA-harness incident:** the first run of this check mocked `winreg.OpenKey`/
`CloseKey` only, so the frozen-simulated `SetValueEx`/`DeleteValue` hit the REAL Run key —
writing python.exe over the user's value and then deleting it. This was harness error, not
application behavior (the application's own frozen guard was bypassed by the incomplete mock).
The value was restored immediately to the exact original
`C:\Users\wpedi\Process Watchdog\dist\ProcessWatchdog.exe` and re-verified at session end:

```
(Get-ItemProperty 'HKCU:\...Run').'Process Watchdog'
C:\Users\wpedi\Process Watchdog\dist\ProcessWatchdog.exe
```

The check was then re-run with ALL winreg functions mocked (output above) and cannot touch
real registry state. The user's Start-with-Windows setting is intact and was never changed by
the application.

### 10. Light/dark theme + refresh on doghouse-leave — PASS

```
original AppsUseLightTheme: 0
PASS item10_light_bg_after_flip | light_bg=#F3F3F3
PASS item10_dark_bg_after_reshow | dark_bg=#202020
PASS item10_registry_restored | restored=0 original=0
```

Controlled registry flip (light at construction -> #F3F3F3; flip to dark then `show()` ->
#202020), original value restored and re-read. Also independently observed in the packaged
exe smoke (dark palette #202020 rendered under a dark system theme).

### 11. Logo visibility — PASS

```
PASS item11_logo_configwindow
PASS item11_logo_watchdogdialog
PASS item11_logo_userguide
```

Each window holds a real `_logo_img` PhotoImage referenced by a visible Label. The fourth
surface is the packaged exe, whose 46x46 logo region was pixel-verified in Part 2 (768 unique
colors vs uniform background). Note: `RehomeDialog` deliberately has no logo (it never did, in
any mission) and is not one of the four logo surfaces.

### 12. Bite-animation paths, no leaked region — PASS (with one stated limit)

```
PASS item12_guide_close_destroyed
PASS item12_guide_timer_auto_closed
PASS item7_doghouse_hides | state=withdrawn GetWindowRgn=0
PASS item7_main_x_hides | state=withdrawn GetWindowRgn=0
```

Doghouse-button and main-X paths verified with `GetWindowRgn == 0` (no residual region) after
each animation. Guide Close and the 30 s→1 s timer path both animated to complete destruction.
Limitation stated plainly: the guide window is destroyed by the animation, so no post-hoc
region read is possible there; the region check applies to the two paths whose window
persists. GDI-object counting was inconclusive in 6D and was not repeated; the region check is
the substantive leak check, same as 6D.

## Part 4 — Repository cleanliness: PASS

```
git status --porcelain=v1 --untracked-files=all
(no output — clean)
```

`git log --oneline main -30`: history matches expectations, tip = 26803ec (Mission 6G), all
mission commits present, no stray commits.

## Final acceptance gate

- All requested behavior is present: YES by Part 3 evidence (previous blockers now verified
  end-to-end).
- All automated tests pass: 99/99 (Part 1).
- Packaged runtime checks pass: launch, render, resources, shutdown all PASS (Part 2).
- Existing Watchdogs remain usable: migration + Retrain preserve all data (items 1, 2).
- Destructive behavior stayed inside the approved boundary: only PyInstaller-built disposable
  processes were ever killed; no real application was watched or killed; the real config file
  was never modified (hash-identical).
- Dog terminology consistent: observed in live status strings ("Off watch.", "Waiting to
  eat:", "Hungry — eating in 3s.", "Eaten by", "Put Dog on Watch").
- Resource limits pass: all values within ceilings (Part 2 table).
- Repository clean: PASS (Part 4).
- **NOT MET: the physical tray-menu click for Quit is UNVERIFIED** (not scriptable from CLI;
  the app-side quit path it dispatches to is fully verified — item 8). Per this mission's
  hard rule, the gate is therefore left NOT MET. Accepting the long-standing documented
  deviation (as baseline 1A/6B/6D did) or performing one manual click-through would close it.

## Residue for the record

1. Tray-menu click dispatch — UNVERIFIED (item 8); everything it dispatches to is verified.
2. `Watcher._stop` shadows `Thread._stop` (watchdog_core.py:460) — pre-existing quirk; makes
   `is_alive()` unusable after `stop()`. Unfixed here (verification-only). Cleanup candidate.
3. Post-toggle selection clear (label falls back until re-select) — pre-existing UX wart,
   noted in 6D, unchanged.
4. GDI-object counting remains inconclusive (same as 6D); region-restore check is the
   substantive leak evidence.
