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
Status: ✅ Verified (Mission 2 complete — watch/meal model, Retrain dialog, config migration; see docs/missions/2-watch-meal-model.md)
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
- Show a visible 40×40 logo in the header.
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
Status: 🟨 Active (partial: feeding-engine self-exclusion closed by Mission 1C; same-directory-neighbor kill expansion removed by Mission 1D; meal-list watch/meal model + Train/Retrain + config migration closed by Mission 2 — see notes under Target behavior / Permanent protection; SYSTEM/protected/UI-wide protection still open)
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
  sources (direct match, descendants) converge. This governs the feeding
  engine only; the picker/filter/UI-wide
  "never show or target ProcessWatchdog.exe" enforcement, and the
  SYSTEM/protected-process/protected-path exclusions, remain open.
- Exclude SYSTEM, LOCAL SERVICE, and NETWORK SERVICE processes.
- Exclude protected Windows executables.
- Exclude executables under protected Windows system directories.
- Apply protection to the picker, filter, browsing, manual entry, migration, and feeding engine.
- Keep normal user applications under Program Files available.
- Enforce protection inside the core engine, not only in the UI.
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
Status: ⬜ Planned
Depends on: Mission 3
Main controls
- Keep Add Watchdog.
- Rename Edit to Retrain.
- Use dynamic Watchdog toggle labels.
- Show Call Dog Off Watch when the selected Watchdog is watching.
- Show Put Dog on Watch when it is not watching.
- Never use Turn Off on a button.
- Rename Delete to Rehome Dog.
- Rename User Guide to Trainer’s Guide.
- Rename Hide to Tray to Hide Dogs in the Doghouse.
Rehome confirmation
- Require confirmation before rehoming.
- Show:
  Rehome “Claude Watchdog”?
  
  This removes the Watchdog and its meal list.
  The dog cannot come back unless you train it again.
- Use Keep Dog and Rehome Dog actions.
- Preserve the Watchdog if the user chooses Keep Dog.
Table
- Keep exactly three columns.
- Rename Watchdog to Watchdogs.
- Rename Enabled to Watching.
- Rename Status to Dog Status.
- Show Yes or No in Watching.
- Do not add another permanent column.
Dog Status states
- Before the watched app has been observed: Waiting for app to open.
- While open: Waiting to eat: claude.exe.
- During grace period: Hungry — eating in 7s.
- After verified termination: Eaten by Claude Watchdog: Claude.exe, cowork-svc.exe.
- When targets were already absent: Nothing left to eat.
- On partial failure: identify what was eaten and what could not be eaten.
- On access denial: Couldn’t eat: Access denied.
- When disabled: use dog-language indicating the dog is off watch.
- Never claim Eaten merely because a process is absent.
- Summarize long lists with +N.
- Make full target details available outside the compact table cell.
- Keep the last feeding result visible until the watched application opens again.
- Keep feeding results in memory only.
- Reset feeding results when Process Watchdog restarts.
Tray behavior
- Keep an explicit tray Quit command.
- Tray Quit fully exits Process Watchdog.
- Keep startup-with-Windows control in the tray.
- Use dog-language for opening the hidden window.
- Main-window X never exits the application.
- Doghouse button never exits the application.
- Only tray Quit, Windows shutdown, or external termination ends the process.
Acceptance gate
- No user-facing Rule, Kill, Delete, Edit, User Guide, or Hide to Tray language remains.
- No button says Turn Off.
- Dynamic toggle labels match the selected Watchdog.
- Status never claims an unverified feeding.
- Tray Quit remains functional.
Mission 5 — Lightweight System-Themed Interface
Status: ⬜ Planned
Depends on: Mission 4
System theme
- Use Windows light/dark application preference.
- Detect theme at launch.
- Recheck theme whenever dogs leave the doghouse.
- Do not add a registry-watching thread.
- Use the current Windows accent color for selections and primary actions.
- Use neutral system-themed surfaces elsewhere.
- Use consistent ttk controls where practical.
- Add no theming dependency.
- Maintain readable contrast in light and dark modes.
- Keep keyboard navigation and focus indicators usable.
Main window
- Display the existing logo prominently.
- Use a 48×48 logo at the upper left.
- Place Process Watchdog beside the logo.
- Add one concise pack-status line.
- Improve spacing, alignment, hierarchy, and button grouping.
- Reduce excessive empty visual space.
- Keep the window compact.
- Keep the three-column table readable.
- Ensure dynamic button labels fit.
- Avoid dashboards, cards, telemetry panels, and visual clutter.
Supporting windows
- Use a 40×40 logo in Add/Retrain.
- Use a 32×32 logo in Trainer’s Guide.
- Apply the same system theme to every window.
- Apply the application icon consistently.
- Make dialogs visually related to the main window.
- Keep controls usable at Windows display scaling settings.
- Preserve resizing and minimum-size behavior.
Acceptance gate
- Main, Add, Retrain, and Trainer’s Guide visibly use the logo.
- Light mode is readable.
- Dark mode is readable.
- Windows accent is visible but restrained.
- No new dependency was added.
- Resource budget remains intact.
- Controls do not clip at supported scaling.
Mission 6 — Doghouse Animation, Trainer’s Guide, and Release QA
Status: ⬜ Planned
Depends on: Mission 5
Bite animation
- Keep the existing Win32 window-region technique.
- Make missing chunks look like obvious dog bites.
- Use larger, more visible bite shapes.
- Complete the animation in approximately 0.8 seconds.
- Keep the animation non-blocking.
- Restore the full window region before the window is shown again.
- Fall back safely to immediate hiding/destruction if animation fails.
- Test repeatedly for leaked GDI regions or broken window shapes.
Apply animation to
- Main-window X.
- Hide Dogs in the Doghouse.
- Trainer’s Guide close button.
- Trainer’s Guide X.
- Trainer’s Guide timer expiration.
- Do not create extra animations for unrelated tray actions.
Trainer’s Guide
- Rename it to Trainer’s Guide.
- Change the timer from 15 seconds to 30 seconds.
- Keep the visible countdown.
- Rewrite the guide around the final Watch/Eat model.
- Explain one watched application and unlimited meal targets.
- Explain the automatic watched-app meal target.
- Explain the global grace period.
- Explain doghouse behavior.
- Explain dynamic Watchdog toggling.
- Explain Retrain and Rehome.
- Explain exact-path matching and protected-process exclusions.
- Use playful, mischievous dog humor.
- Avoid corporate language, childish prose, and profanity.
- Keep instructions concise and accurate.
- End manual or timed closure with the bite animation.
Final verification
- Run the complete automated test suite.
- Run syntax and import validation.
- Verify copied real configuration migration.
- Confirm the live configuration remains unchanged during testing.
- Verify Add, Retrain, toggle, Rehome, and grace-period behavior.
- Verify unrelated selected leftovers are eaten in a controlled test.
- Verify unselected same-folder processes survive.
- Verify protected processes and Process Watchdog never appear.
- Verify main X hides without exiting.
- Verify doghouse button hides without exiting.
- Verify tray Quit exits.
- Verify Start with Windows behavior.
- Verify light and dark themes.
- Verify theme refresh after leaving the doghouse.
- Verify logo visibility in all required windows.
- Verify every bite-animation path.
- Build the one-file executable.
- Smoke-test the packaged executable.
- Verify bundled icons and images.
- Compare final executable size against baseline.
- Compare idle memory against baseline.
- Compare CPU, threads, handles, and polling behavior.
- Confirm every hard resource limit passes.
- Inspect the final diff for unrelated changes.
- Commit only verified work.
Final acceptance gate
- All requested behavior is present.
- All automated tests pass.
- Packaged runtime checks pass.
- Existing Watchdogs remain usable.
- Destructive behavior stays inside the approved boundary.
- Dog terminology is consistent.
- Resource limits pass.
- Repository is clean.
- Local and remote state are reported accurately.
This is the complete punch board and contains the approved product behavior, safety boundaries, visual direction, resource limits, migration requirements, and final verification gates.
