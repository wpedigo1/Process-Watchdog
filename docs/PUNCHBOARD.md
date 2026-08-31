Process Watchdog Punch Board
Status key: ⬜ Planned · 🟨 Active · ✅ Verified · 🟥 Blocked
Mission 1 — Lightweight Foundation
Status: ⬜ Planned
Depends on: Nothing
Resource baseline
- Measure current packaged executable size.
- Measure idle working-set memory.
- Measure idle CPU across several polling cycles.
- Record thread count, handle count, and polling interval.
- Confirm current startup time.
- Preserve results for final before/after comparison.
Hard resource limits
- Add no new runtime dependencies.
- Increase executable size by no more than 1 MB.
- Increase idle memory by no more than 5 MB.
- Add no permanent background threads.
- Keep the default two-second polling interval.
- Keep CPU effectively idle between polls.
- Add no database, telemetry, persistent history, or background logging loop.
Focused structure
- Keep watchdog_app.py for startup, tray behavior, and application lifecycle.
- Create watchdog_core.py for configuration, process protection, feeding decisions, watcher state, and results.
- Create watchdog_ui.py for windows, dialogs, theme handling, logos, controls, and animations.
- Preserve behavior while moving code before adding new behavior.
- Keep the PyInstaller one-file build working.
- Keep source-mode resource loading working.
- Add characterization tests before moving dangerous process logic.
Acceptance gate
- Existing app still starts.
- Existing tray behavior still works.
- Existing configuration still loads.
- No process is terminated during structural testing.
- Automated tests pass.
- Resource use has not meaningfully changed.
Mission 2 — Train and Retrain Watchdogs
Status: ✅ Verified (Mission 2: watch/meal model, Retrain dialog, config migration all implemented and tested; one item — "Show a visible 40×40 logo in the header" below — is NOT done and is deferred to Mission 5's project-wide logo/theming, not bolted on early. See docs/missions/2-watch-meal-model.md.)
Depends on: Mission 1
Watchdog model
- Every Watchdog watches exactly one application.
- The watched application is automatically included in its meal list.
- The watched application cannot be removed from the meal list.
- Each Watchdog may have any number of additional meal targets.
- Every identity stores an executable name and exact path when available.
- Name-only matching remains a clearly labeled fallback.
Configuration migration
- Preserve all existing Watchdogs and IDs.
- Support legacy rules configurations.
- Support existing watchdogs configurations.
- Preserve names, enabled states, triggers, kill targets, and exact paths.
- Convert the watched application into the required meal target.
- Convert every other existing selection into an additional meal target.
- If a legacy Watchdog has multiple possible watched applications, do not guess.
- Keep that Watchdog’s data intact and require the user to choose its single watched application during Retrain.
- Never modify the live configuration during tests.
- Verify migration using copied configuration data.
- Verify migrated data by reading it back.
Add/Retrain window
- Rename editing to Retrain.
- Show a visible 40×40 logo in the header. [DEFERRED to Mission 5 — see Mission 2 status line]
- Use the heading Train a Watchdog when adding.
- Use Retrain [Watchdog name] when editing.
- Provide a dedicated Watch This App section.
- Allow exactly one watched application.
- Provide a separate Eat These Leftovers section.
- Show the watched application as a locked meal target.
- Allow unlimited additional meal targets.
- Keep Filter and Refresh controls.
- Remove Hide system processes.
- Never show protected processes.
- Preserve selections that are not currently running.
- Provide Browse for .exe.
- Allow safe configuration without launching the target first.
- Provide filename-only entry as a secondary fallback.
- Clearly identify entries using name-only matching.
- Prevent duplicate meal entries.
- Validate the Watchdog name and watched application before saving.
Acceptance gate
- One watched application is enforced.
- Watched application is always a meal target.
- Additional unrelated processes can be selected.
- Offline executables can be added safely.
- Existing Watchdogs survive migration.
- Protected targets cannot be added through any UI path.
- Tests cover migration and selection behavior.
Mission 3 — Safe Feeding Engine
Status: ✅ Verified (partial: feeding-engine self-exclusion closed by Mission 1C; same-directory-neighbor kill expansion removed by Mission 1D; meal-list watch/meal model + Train/Retrain + config migration closed by Mission 2; protected-executable/path + core-engine enforcement + offline Browse/manual rejection closed by Mission 3 — see notes under Permanent protection; picker-display self-hiding was also closed by Mission 2, not Mission 3: get_process_groups excludes pid == os.getpid(); username-based SYSTEM/LOCAL/NETWORK SERVICE feeding filter closed by Mission 3B — see docs/missions/3b-username-owner-exclusion.md)
Depends on: Mission 2
Trigger behavior
- Preserve current Windows visible-window logic.
- Consider the watched app open while its matched process owns a visible, titled window.
- Begin feeding only after a verified open-to-closed transition.
- Do not feed immediately when Process Watchdog starts and the watched app is already closed.
- Use the one global grace period for every Watchdog.
- Keep the existing permitted grace-period range unless testing reveals a defect.
- Cancel pending feeding if the watched application reopens.
- Disabled Watchdogs never schedule or perform feeding.
Target behavior
- Always attempt the watched application meal target.
- Always attempt every explicitly selected additional meal target.
- Eat selected targets even when they are unrelated to the watched app’s process tree.
- Match exact executable paths whenever available.
- Use case-insensitive Windows path comparisons.
- Use name-only matching only for fallback identities.
- Eat child processes belonging to explicitly selected targets.
- Do not automatically eat unselected executables from the same installation folder.
- Remove the current same-directory expansion behavior.
- [CLOSED by Mission 1D] kill_processes no longer enumerates every running process or kills
  unselected same-folder neighbors; it only targets direct matches and their recursive
  descendants (plus Mission 1C self-exclusion). Directory-expansion mechanism removed entirely;
  psutil.process_iter is no longer called from kill_processes.
- Deduplicate targets by PID before feeding.
- Handle processes that disappear during enumeration.
- Handle access-denied results honestly.
- Never count an unsuccessful termination as eaten.
Permanent protection
- Never show or target ProcessWatchdog.exe.
- Never allow Process Watchdog to eat itself.
- [CLOSED for the feeding engine by Mission 1C] kill_processes excludes
  Process Watchdog's own process (by pid == os.getpid() OR exe ==
  sys.executable, normalized) at the single merge point where all kill
  sources (direct match, descendants) converge.
- [CLOSED by Mission 3] Protected/self rejection now lives in the core
  engine (`is_protected_entry`, identity-only) and is enforced at the same
  single merge point in kill_processes alongside the Mission 1C self check;
  it also rejects self by name-only and by protected name/path. Offline
  Browse/manual entry in both sections (Watch This App and Eat These
  Leftovers) is rejected before adding. See
  docs/missions/3-protected-target-enforcement.md. The picker-display
  "never show ProcessWatchdog.exe" hiding was already closed by Mission 2
  (`get_process_groups` excludes `pid == os.getpid()`), not by Mission 3.
- Exclude SYSTEM, LOCAL SERVICE, and NETWORK SERVICE processes.
  [CLOSED by Mission 3B] _is_protected_owner calls proc.username() live at
  the kill_processes merge point, reusing SYSTEM_USERNAMES. Covers both direct
  matches and recursive children. AccessDenied on username() is NOT treated as
  protected (honest skip, mirrors existing kill() handling). See
  docs/missions/3b-username-owner-exclusion.md.
- [CLOSED by Mission 3] Exclude protected Windows executables.
- [CLOSED by Mission 3] Exclude executables under protected Windows system
  directories.
- [CLOSED by Mission 3 for browsing, manual entry, and the feeding engine]
  Apply protection to the picker, filter, browsing, manual entry, migration,
  and feeding engine. Migration is deliberately not rewritten (enforcement
  lives in the core engine; see Mission 3 doc). Picker/filter display-level
  hiding of ProcessWatchdog.exe was already closed by Mission 2
  (`get_process_groups` excludes `pid == os.getpid()`).
- Keep normal user applications under Program Files available.
- [CLOSED by Mission 3] Enforce protection inside the core engine, not only
  in the UI.
Safe testing
- Unit-test target selection without terminating real applications.
- Test unrelated selected targets.
- Test child-process inclusion.
- Test that same-folder neighbors are excluded.
- Test Process Watchdog self-protection.
- Test protected Windows-process rejection.
- Test access denied and disappearing processes.
- Use a disposable controlled process only if runtime termination verification is necessary.
Acceptance gate
- Every explicitly selected target is attempted.
- No unselected same-folder process is targeted.
- Protected processes cannot reach the termination boundary.
- Reopening cancels feeding.
- No feeding occurs without an open-to-closed transition.
- Actual results distinguish eaten, absent, and failed targets.
Mission 4 — Dog Language and Honest Status
Status: ✅ Verified (Main controls, Rehome confirmation, Table, Tray rename, and ALL Dog Status states — including eaten/absent/partial-failure/access-denied — closed by Mission 4A + Mission 4B; see docs/missions/4a-dog-language-labels.md and docs/missions/4b-feeding-results.md. Guide timer/rewrite deferred to Mission 6.)
Depends on: Mission 3
Main controls
- Keep Add Watchdog. [CLOSED by Mission 4A]
- Rename Edit to Retrain. [CLOSED by Mission 4A]
- Use dynamic Watchdog toggle labels. [CLOSED by Mission 4A — <<TreeviewSelect>> binding + _update_toggle_label]
- Show Call Dog Off Watch when the selected Watchdog is watching. [CLOSED by Mission 4A]
- Show Put Dog on Watch when it is not watching. [CLOSED by Mission 4A]
- Never use Turn Off on a button. [CLOSED by Mission 4A — grep-verified no "Turn Off" in code]
- Rename Delete to Rehome Dog. [CLOSED by Mission 4A]
- Rename User Guide to Trainer's Guide. [CLOSED by Mission 4A]
- Rename Hide to Tray to Hide Dogs in the Doghouse. [CLOSED by Mission 4A]
Rehome confirmation
- Require confirmation before rehoming. [CLOSED by Mission 4A]
- Show: [CLOSED by Mission 4A — RehomeDialog with exact template text]
  Rehome "{name}"?
  
  This removes the Watchdog and its meal list.
  The dog cannot come back unless you train it again.
- Use Keep Dog and Rehome Dog actions. [CLOSED by Mission 4A]
- Preserve the Watchdog if the user chooses Keep Dog. [CLOSED by Mission 4A]
Table
- Keep exactly three columns. [CLOSED by Mission 4A]
- Rename Watchdog to Watchdogs. [CLOSED by Mission 4A]
- Rename Enabled to Watching. [CLOSED by Mission 4A]
- Rename Status to Dog Status. [CLOSED by Mission 4A]
- Show Yes or No in Watching. [CLOSED by Mission 4A — unchanged]
- Do not add another permanent column. [CLOSED by Mission 4A]
Dog Status states
- Before the watched app has been observed: Waiting for app to open. [CLOSED by Mission 4A — _tick_status idle string]
- While open: Waiting to eat: claude.exe. [CLOSED by Mission 4A — _tick_status open-names string]
- During grace period: Hungry — eating in 7s. [CLOSED by Mission 4A — _tick_status pending string]
- When disabled: use dog-language indicating the dog is off watch. [CLOSED by Mission 4A — "Off watch."]
- After verified termination: Eaten by Claude Watchdog: Claude.exe, cowork-svc.exe. [CLOSED by Mission 4B — _render_result from real kill detail]
- When targets were already absent: Nothing left to eat. [CLOSED by Mission 4B — zero kill detail reported]
- On partial failure: identify what was eaten and what could not be eaten. [CLOSED by Mission 4B — combined killed+failed render]
- On access denial: Couldn't eat: Access denied. [CLOSED by Mission 4B — failed list render]
- Never claim Eaten merely because a process is absent. [CLOSED by Mission 4B — only actually-killed names reported]
- Summarize long lists with +N. [CLOSED by Mission 4A — existing +N logic preserved, surrounding text updated]
- Make full target details available outside the compact table cell. [CLOSED by Mission 4B — double-click row opens details popup]
- Keep the last feeding result visible until the watched application opens again. [CLOSED by Mission 4B — _last_result retired on fresh open]
- Keep feeding results in memory only. [CLOSED by Mission 4B — plain instance dict, never persisted]
- Reset feeding results when Process Watchdog restarts. [CLOSED by Mission 4B — instance attribute, reset on new ConfigWindow]
Tray behavior
- Keep an explicit tray Quit command. [CLOSED — already true since before Mission 4A]
- Tray Quit fully exits Process Watchdog. [CLOSED — already true]
- Keep startup-with-Windows control in the tray. [CLOSED — already true]
- Use dog-language for opening the hidden window. [CLOSED by Mission 4A — "Open the Doghouse"]
- Main-window X never exits the application. [CLOSED — already true (WM_DELETE_WINDOW → hide)]
- Doghouse button never exits the application. [CLOSED by Mission 4A — "Hide Dogs in the Doghouse" → hide]
- Only tray Quit, Windows shutdown, or external termination ends the process. [CLOSED — already true]
Acceptance gate
- No user-facing Rule, Kill, Delete, Edit, User Guide, or Hide to Tray language remains. [CLOSED by Mission 4A — grep-verified]
- No button says Turn Off. [CLOSED by Mission 4A — grep-verified]
- Dynamic toggle labels match the selected Watchdog. [CLOSED by Mission 4A]
- Status never claims an unverified feeding. [CLOSED by Mission 4B — status renders only from real kill detail]
- Tray Quit remains functional. [CLOSED — already true]
Mission 5 — Lightweight System-Themed Interface
Status: ✅ Verified (theming + logo + layout pass closed by Mission 5; see docs/missions/5-theming-logo-layout.md. Items below note what is closed. Contrast and scaling checked by source/color-value inspection only — actual rendered visuals require manual verification and are marked inspection-pending, not claimed verified.)
Depends on: Mission 4
System theme
- Use Windows light/dark application preference. [CLOSED by Mission 5 — detect_windows_theme from AppsUseLightTheme]
- Detect theme at launch. [CLOSED by Mission 5 — ConfigWindow.__init__]
- Recheck theme whenever dogs leave the doghouse. [CLOSED by Mission 5 — ConfigWindow.show() re-runs detection/apply]
- Do not add a registry-watching thread. [CLOSED by Mission 5 — only the two explicit moments; no polling/thread added]
- Use the current Windows accent color for selections and primary actions. [CLOSED by Mission 5 — Treeview selection = accent; button activebackground = accent; no new button semantics invented]
- Use neutral system-themed surfaces elsewhere. [CLOSED by Mission 5 — palette bg/fg per mode]
- Use consistent ttk controls where practical. [NOT DONE BY DESIGN — app uses plain tk widgets; mission 5 route explicitly forbade converting to ttk (high blast radius). Themed via one recursive plain-tk color pass + ttk.Style for Treeview only. See docs/missions/5-theming-logo-layout.md.]
- Add no theming dependency. [CLOSED by Mission 5 — Pillow already a dependency; no new dep]
- Maintain readable contrast in light and dark modes. [CLOSED by value inspection only — light bg #F3F3F3/fg #000000, dark bg #202020/fg #FFFFFF; actual rendered look is inspection-pending]
- Keep keyboard navigation and focus indicators usable. [inspection-pending — untouched default focus behavior retained]
Main window
- Display the existing logo prominently. [CLOSED by Mission 5 — 48×48 upper-left + APP_NAME beside it]
- Use a 48×48 logo at the upper left. [CLOSED by Mission 5]
- Place Process Watchdog beside the logo. [CLOSED by Mission 5 — reuses APP_NAME, no hardcoded copy]
- Add one concise pack-status line. [CLOSED by Mission 5 — "{enabled} of {total} watchdogs on watch" recomputed in refresh_tree]
- Improve spacing, alignment, hierarchy, and button grouping. [PARTIAL — added logo header + pack-status line for hierarchy; existing button row already grouped (actions left, hide/guide right) and left as-is to avoid redesign]
- Reduce excessive empty visual space. [PARTIAL — see above; no redesign]
- Keep the window compact. [CLOSED by Mission 5 — resizing and min-size untouched, no new panels]
- Keep the three-column table readable. [CLOSED by Mission 5 — Treeview themed, three columns preserved]
- Ensure dynamic button labels fit. [CLOSED — unchanged layout, labels preserved verbatim]
- Avoid dashboards, cards, telemetry panels, and visual clutter. [CLOSED by Mission 5 — none added]
Supporting windows
- Use a 40×40 logo in Add/Retrain. [CLOSED by Mission 5 — watchdogDialog header]
- Use a 32×32 logo in Trainer’s Guide. [CLOSED by Mission 5 — UserGuideWindow header]
- Apply the same system theme to every window. [CLOSED by Mission 5 — ConfigWindow, watchdogDialog, RehomeDialog, UserGuideWindow all apply_theme]
- Apply the application icon consistently. [CLOSED — apply_window_icon already on every window; unchanged]
- Make dialogs visually related to the main window. [CLOSED by Mission 5 — same palette applied to dialogs]
- Keep controls usable at Windows display scaling settings. [inspection-pending — plain tk widgets; no scaling changes made]
- Preserve resizing and minimum-size behavior. [CLOSED by Mission 5 — geometry/minsize untouched]
Acceptance gate
- Main, Add, Retrain, and Trainer’s Guide visibly use the logo. [CLOSED by source inspection — each holds _logo_img PhotoImage reference; rendered visibility is inspection-pending]
- Light mode is readable. [inspection-pending]
- Dark mode is readable. [inspection-pending]
- Windows accent is visible but restrained. [CLOSED by value inspection — accent only on tree selection + button activebackground]
- No new dependency was added. [CLOSED by Mission 5 — verified imports]
- Resource budget remains intact. [CLOSED — no new dependency/thread; theme reads are once-per-window registry reads, not polled]
- Controls do not clip at supported scaling. [inspection-pending]
Mission 6 — Doghouse Animation, Trainer’s Guide, and Release QA
Status: 🟨 Active (content/timing half — bite-animation sizing/timing, guide timer rewrite —
closed by Mission 6A; see docs/missions/6a-guide-timer-animation.md. The Final verification /
release-QA half is a separate follow-up mission and remains OPEN below.)
Depends on: Mission 5
Bite animation
- Keep the existing Win32 window-region technique. [CLOSED — unchanged]
- Make missing chunks look like obvious dog bites. [CLOSED — unchanged technique, existing]
- Use larger, more visible bite shapes. [CLOSED by Mission 6A — bite_r = max(14, h // 3)]
- Complete the animation in approximately 0.8 seconds. [CLOSED by Mission 6A — bites=5,
  bite_delay_ms=160 → 5 × 160 = 800 ms]
- Keep the animation non-blocking. [CLOSED — unchanged, win.after scheduling retained]
- Restore the full window region before the window is shown again. [CLOSED — already true;
  SetWindowRgn(hwnd, None, True) verified pre-existing, untouched]
- Fall back safely to immediate hiding/destruction if animation fails. [CLOSED — already true;
  non-Windows/missing-API/exception fallback to on_done() verified pre-existing, untouched]
- Test repeatedly for leaked GDI regions or broken window shapes. [NOT CLOSED — deferred to
  release-QA mission]
Apply animation to
- Main-window X. [CLOSED — already correctly wired through ConfigWindow.hide(), verified pre-existing]
- Hide Dogs in the Doghouse. [CLOSED — already correctly wired through ConfigWindow.hide(), verified pre-existing]
- Trainer’s Guide close button. [CLOSED — already correctly wired through UserGuideWindow._close_now, verified pre-existing]
- Trainer’s Guide X. [CLOSED — already correctly wired through UserGuideWindow._close_now, verified pre-existing]
- Trainer’s Guide timer expiration. [CLOSED — already correctly wired through _tick, verified pre-existing]
- Do not create extra animations for unrelated tray actions. [CLOSED — no new wiring added]
Trainer’s Guide
- Rename it to Trainer’s Guide. [CLOSED by Mission 4A]
- Change the timer from 15 seconds to 30 seconds. [CLOSED by Mission 6A — COUNTDOWN_SECONDS = 30]
- Keep the visible countdown. [CLOSED — unchanged, _tick retained]
- Rewrite the guide around the final Watch/Eat model. [CLOSED by Mission 6A — GUIDE_TEXT rewritten]
- Explain one watched application and unlimited meal targets. [CLOSED by Mission 6A — "ONE WATCHED APP + THE MEAL LIST"]
- Explain the automatic watched-app meal target. [CLOSED by Mission 6A — "ONE WATCHED APP + THE MEAL LIST"]
- Explain the global grace period. [CLOSED by Mission 6A — "GRACE PERIOD (GLOBAL)"]
- Explain doghouse behavior. [CLOSED by Mission 6A — "THE DOGHOUSE"]
- Explain dynamic Watchdog toggling. [CLOSED by Mission 6A — "CALL DOG OFF WATCH / PUT DOG ON WATCH"]
- Explain Retrain and Rehome. [CLOSED by Mission 6A — "RETRAIN / REHOME"]
- Explain exact-path matching and protected-process exclusions. [CLOSED by Mission 6A — "EXACT MATCH VS. NAME MATCH" and "PROTECTED PROCESSES"]
- Use playful, mischievous dog humor. [CLOSED by Mission 6A]
- Avoid corporate language, childish prose, and profanity. [CLOSED by Mission 6A]
- Keep instructions concise and accurate. [CLOSED by Mission 6A]
- End manual or timed closure with the bite animation. [CLOSED — already true; wiring verified pre-existing]
Final verification
- Run the complete automated test suite. [PASS by Mission 6D — 89/89 on the real Windows machine]
- Run syntax and import validation. [PASS by Missions 6B/6C — ast.parse + import OK; 89 source-level test methods]
- Verify copied real configuration migration. [PASS by Mission 6D — real legacy `rules` config migrated via copy; all 5 watchdogs and every identity preserved; real file hash-verified untouched]
- Confirm the live configuration remains unchanged during testing. [PASS by Mission 6D — sha256 identical before/after the whole mission]
- Verify Add, Retrain, toggle, Rehome, and grace-period behavior. [FAIL by Mission 6D — Add crashes (defect 2), Retrain-with-watched-app crashes and Retrain-ambiguous silently drops meal targets (defect 3); toggle PASS; Rehome PASS (exact dialog text, Keep/Rehome both verified); grace countdown PASS; the kill-engine crash (defect 4) is now FIXED by Mission 6E with real-process regression tests, but the end-to-end grace-kill walkthrough has not been re-run — re-verify in the next release-QA pass]
- Verify unrelated selected leftovers are eaten in a controlled test. [BLOCKED at runtime by Mission 6D's defect 4 (now FIXED by Mission 6E — real parent+child kill verified at the engine level in tests/test_kill_real_processes.py); the full end-to-end leftover walkthrough still needs the next release-QA re-run]
- Verify unselected same-folder processes survive. [UNVERIFIED at runtime by Mission 6D — vacuous pass only (defect 4 prevented any kill); scoping logic unit-covered]
- Verify protected processes and Process Watchdog never appear. [PARTIAL by Mission 6D — own pid excluded (verified); Browse + name-only protected rejection verified with exact Mission 3 message; BUT defect 1: the packaged app's own parent ProcessWatchdog.exe IS listed in its picker (display-level violation; kill boundary still protected)]
- Verify main X hides without exiting. [PASS by Mission 6D — real WM_DELETE_WINDOW path, animation, withdrawn, process alive]
- Verify doghouse button hides without exiting. [PASS by Mission 6D — real button command, same checks]
- Verify tray Quit exits. [UNVERIFIED — tray menu not scriptable from CLI; documented taskkill deviation used; not claimed]
- Verify Start with Windows behavior. [PARTIAL by Mission 6D — real Run key contains the app's exact-format registration (user's own setting); read logic verified against the real key frozen-simulated; source-level non-frozen no-op guard verified; tray UI round-trip itself not scriptable; user setting deliberately untouched]
- Verify light and dark themes. [PASS by Mission 6D — controlled registry flip: light at construction, dark rendered after; exe rendered dark while system dark; two independent light/dark launch observations]
- Verify theme refresh after leaving the doghouse. [PASS by Mission 6D — hide→show re-detect: 49,636 dark-palette pixels post-show vs 2 before, root bg #202020, registry restored]
- Verify logo visibility in all required windows. [PASS by Mission 6D — measured pixel analysis: rendered logo patches at exact positions in ConfigWindow, watchdogDialog, Trainer's Guide, and the packaged exe; screenshots saved as artifacts]
- Verify every bite-animation path. [PASS by Mission 6D — main X x2, doghouse x2, guide Close, guide X, guide 30s timer; window shape restored (GetWindowRgn=0, 500x460) after every path; GDI counter inconclusive (read 0), region/no-broken-shape evidence is the substantive check]
- Build the one-file executable. [DONE by Missions 6B and 6D — build.bat completed both times]
- Smoke-test the packaged executable. [PASS by Mission 6D — exe launches, first-run window opens and renders (native child HWNDs, exact palette bg, logo), no crash, hidden-to-tray idle run measured; the 6B startup crash is confirmed fixed in the packaged build]
- Verify bundled icons and images. [PASS by Mission 6D — window icon + logo verified in the packaged exe capture; tray icon not directly observed (not scriptable) — noted]
- Compare final executable size against baseline. [PASS by Mission 6D — 31,528,986 bytes vs 32,548,945 ceiling (+28,617 vs baseline)]
- Compare idle memory against baseline. [PASS by Mission 6D — child RSS 46,551,040-46,600,192 (below baseline's ~48.3 MB, well under the ~53.3 MB ceiling); parent 8.7 MB unchanged]
- Compare CPU, threads, handles, and polling behavior. [PASS by Mission 6D — CPU min/median 0.00 both pids (one 1.60% max sample on the dormant bootloader parent, reported honestly); threads 4/9 exactly matches baseline (no new permanent threads); handles 100/524]
- Confirm every hard resource limit passes. [PASS by Mission 6D — size, memory, threads all within limits; no new dependency (versions identical to baseline)]
- Inspect the final diff for unrelated changes. [PASS by Mission 6D — clean working tree throughout; QA scripts/artifacts kept in temp]
- Commit only verified work. [PASS by Missions 6B/6C/6D — docs and fixes only as scoped]
Final acceptance gate
- All requested behavior is present. [NOT MET — defects 2, 3, 4 break Add, Retrain, and the feeding engine]
- All automated tests pass. [PASS — 89/89]
- Packaged runtime checks pass. [PARTIAL — launch/window/theme/animations/tray-hide PASS; feeding engine broken (defect 4)]
- Existing Watchdogs remain usable. [PARTIAL — migration and display verified; Retrain can silently drop meal targets (defect 3)]
- Destructive behavior stays inside the approved boundary. [PASS — disposable-only rule held; no real app touched; real config untouched; user Run setting untouched]
- Dog terminology is consistent. [PASS — observed live in the driven UI: Call Dog Off Watch / Put Dog on Watch / Off watch. / Hungry — eating in Ns. / Rehome texts / Hide Dogs in the Doghouse / Trainer's Guide countdown title]
- Resource limits pass. [PASS — all measured values within limits]
- Repository is clean. [PASS]
- Local and remote state are reported accurately. [PASS — commit/push verified per mission]
- [BLOCKER — defect 4 — FIXED by Mission 6E] kill_processes' protection filter
  read .info on descendant processes from proc.children(), which are plain
  psutil.Process objects without .info → AttributeError → the Watcher thread
  died → no kill ever happened for any matched process with descendants.
  Mission 6E added _live_identity (live name()/exe() calls with honest
  NoSuchProcess/AccessDenied fallbacks) and used it in _is_self, the
  merge-point protection filter, and the kill-loop name read (a third .info
  site the original brief missed, fixed and documented as a boundary
  conflict). tests/test_kill_real_processes.py proves the fix with REAL
  psutil.Process objects and a real spawned parent+child kill — the exact
  shape FakeProc cannot represent. 94/94 tests pass (89 unchanged + 5 new).
  See docs/missions/6e-fix-kill-engine-info-crash.md.
- [BLOCKER — defect 2, found by Mission 6D — FIXED by Mission 6F]
  watchdogDialog.__init__ now normalizes watchdog=None before the header reads it.
  Real-Tk Add and named-Retrain construction tests pass. See
  docs/missions/6f-fix-add-and-retrain-crashes.md.
- [BLOCKER — defect 3, found by Mission 6D — FIXED by Mission 6F]
  ProcessPicker's watched-app row now uses a supported Treeview tag instead of
  disabled=True. Real-Tk tests verify locked refresh and preservation of a manually
  added meal target. See docs/missions/6f-fix-add-and-retrain-crashes.md.
- [DEFECT — picker parent self-display, found by Mission 6D — FIXED by Mission 6G]
  get_process_groups now reuses _is_self, excluding both the running child PID and a
  different-PID PyInstaller parent with the same executable path. A mocked process-group
  regression test covers the exe-path match. See
  docs/missions/6g-fix-picker-parent-display.md.
- All four defects found by Mission 6D are closed by Missions 6E, 6F, and 6G. The Final
  acceptance gate is NOT met until the full release-QA checklist is rerun end-to-end
  against this fixed code. See docs/missions/6d-final-release-qa-rerun.md.
This is the complete punch board and contains the approved product behavior, safety boundaries, visual direction, resource limits, migration requirements, and final verification gates.
