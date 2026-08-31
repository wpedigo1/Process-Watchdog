# Process Watchdog — Project Instructions

## Project

Process Watchdog is a local-first Windows desktop utility that monitors selected applications and removes leftover background processes after the applications close.

The normal workflow is:

```text
Selected application has a visible window
                ↓
Visible window disappears
                ↓
Configurable grace-period countdown
                ↓
Application reopens? ── Yes → Cancel cleanup
                │
                No
                ↓
Kill configured processes and related helpers
Core principle:
Safe, predictable cleanup with minimal user effort.
Do not expand kill behavior, alter matching semantics, or redesign settled application behavior unless repository evidence or an explicit task requires it.
Source of Truth
Before changing code:
1. Read this file.
2. Verify the repository root, current branch, HEAD, working-tree status, and relevant refs.
3. Inspect the relevant implementation and surrounding call paths.
4. Inspect existing tests and build configuration.
5. Search for an existing working pattern before inventing a new one.
6. Prefer observed repository and runtime behavior over comments, task descriptions, old builds, or previous reports.
7. If documentation conflicts with implementation, report the conflict instead of silently choosing one.
Do not assume an existing executable was built from the current source merely because it is present in dist.
Do not assume a branch, commit, build, configuration migration, or runtime behavior exists without verifying it.
Current Architecture Baseline
Unless an explicit approved change says otherwise:
- The application is Windows-focused.
- The desktop UI uses Tkinter.
- The system-tray integration uses pystray.
- Process discovery and termination use psutil.
- Windows window detection and visual effects use Win32 APIs through ctypes.
- The application is packaged as a windowed, one-file executable with PyInstaller.
- User configuration is stored in:
  %USERPROFILE%\.process_watchdog\config.json
- The main configuration window owns the live in-memory configuration.
- A daemon watcher thread polls process/window state.
- Tkinter UI operations must run on the Tkinter thread.
- Tray or watcher callbacks that affect the UI must marshal work through root.after(...).
- Closing the main window hides it to the tray rather than quitting.
- The tray menu is the authoritative path for fully quitting the application.
- Start-with-Windows is opt-in and uses the current-user Windows Run registry key.
- The application must remain usable without administrator privileges, while honestly handling processes it cannot inspect or terminate.
Treat this as the existing baseline, not permission for unrelated refactoring.
Watchdog Behavior Contract
A configured watchdog contains:
- a stable unique ID;
- a user-visible name;
- an enabled state;
- one or more process identities;
- trigger entries;
- kill entries.
A process identity may contain:
{
  "name": "example.exe",
  "exe": "C:\\Exact\\Install\\Path\\example.exe"
}
Matching rules:
- When an executable path is available, match by normalized exact path.
- Use name-only matching only for legacy entries or cases where the executable path was unavailable.
- Do not silently broaden exact-path matching to every process sharing the same filename.
- Preserve selected processes that are temporarily not running when editing a watchdog.
- Process names and Windows paths must be compared case-insensitively.
Trigger behavior:
- A selected application is considered open when a matching process owns a visible, titled top-level window.
- Merely finding a background process does not necessarily mean the application is visibly open.
- Cleanup is scheduled only after a running/open state transitions to not open.
- Reopening during the grace period cancels pending cleanup.
- Starting Process Watchdog while the target application is already closed must not immediately kill processes without a verified open-to-closed transition.
- Disabled watchdogs must not schedule or perform cleanup.
Do not casually replace visible-window detection with process-existence detection. That changes product behavior and requires an explicit decision plus regression coverage.
Process-Termination Safety
Process termination is the highest-risk behavior in this project.
Before changing it, trace:
1. How selected entries become process identities.
2. How identities are matched to live processes.
3. How visible-window ownership affects trigger state.
4. How grace-period state is scheduled and canceled.
5. How matched processes expand to descendants or neighboring executables.
6. Which processes ultimately receive kill().
Current cleanup may include:
- directly matched processes;
- recursive child processes;
- other executables beneath the matched process’s installation directory.
Do not broaden this scope without explicit approval.
In particular:
- Never match unrelated applications solely because they share an executable name.
- Never terminate Process Watchdog itself unless the requested behavior explicitly requires it.
- Avoid killing system processes, protected processes, or processes outside the intended application boundary.
- Handle NoSuchProcess and AccessDenied honestly.
- Do not report a process as killed unless the termination operation was actually observed.
- Do not fake process lists, window ownership, kill counts, or permissions.
- Do not exercise destructive kill behavior against the user’s real applications merely to validate a change.
- Prefer mocked/unit-level verification for termination selection logic.
- Use a controlled disposable process only when runtime termination testing is necessary and safe.
Changes to install-directory expansion require special scrutiny because directory-based matching can affect more processes than the user explicitly selected.
Configuration Compatibility
Existing user configurations are durable product data.
The current configuration contract uses keys including:
{
  "poll_interval": 2.0,
  "grace_seconds": 10.0,
  "watchdogs": []
}
The persisted key is watchdogs. Configurations written by older versions use rules, and
load_config migrates a legacy rules key into watchdogs on read. Both must continue to load.
Do not drop legacy rules support, change process-entry shapes, or otherwise alter persisted
fields without a backward-compatible migration.
Any configuration schema change must:
1. Load existing configurations without losing watchdogs.
2. Preserve IDs, names, enabled states, triggers, and kill targets.
3. Preserve legacy string process entries where supported.
4. Define a version or reliable migration rule.
5. Avoid silently replacing a malformed configuration with an empty configuration when data recovery is possible.
6. Avoid partial writes that could corrupt the only configuration copy.
7. Include regression coverage using representative legacy configuration data.
Never report a migration as successful unless the migrated data was read back and verified.
Do not expose full user process paths or configuration contents in logs or final reports unless required for diagnosis.
Threading and UI Integrity
Tkinter is not generally thread-safe.
Maintain these boundaries:
- The watcher may inspect process state in its background thread.
- Tkinter widgets must be created, updated, shown, hidden, or destroyed on the UI thread.
- Tray callbacks must schedule UI work through Tkinter.
- Shared watcher state must not be mutated in ways that can produce inconsistent countdown or status displays.
- Stopping the application must stop the watcher and tray icon without leaving a background instance behind.
- New polling or background work must support clean shutdown.
- Avoid holding locks while calling Tkinter, Win32 APIs, psutil.kill(), or other potentially blocking operations.
The status column should honestly distinguish:
- disabled;
- watching;
- currently open and which process names are blocking cleanup;
- grace-period countdown;
- cleanup result or failure if that behavior is added.
Do not freeze the UI with process enumeration, long waits, blocking joins, or build/runtime diagnostics.
Windows and Tray Behavior
Preserve Windows-specific behavior deliberately:
- Resource loading must work from source and PyInstaller’s temporary _MEIPASS directory.
- Missing icons should fail gracefully where a fallback exists.
- First launch should expose a usable setup window.
- Later launches may start hidden when the tray icon is available.
- If tray initialization fails, the main window should remain accessible.
- Start-with-Windows must remain user-controlled.
- Registry state must be read from the registry rather than trusted from a stale configuration flag.
- Do not write startup registration automatically on first launch.
- Registry failures must not crash the whole application.
A PyInstaller one-file application may appear as a parent/child process pair. Do not automatically classify that as duplicate application startup without inspecting parentage and command lines.
Crash Handling and Diagnostics
Windowed builds do not have a visible console.
Preserve useful crash reporting:
- Unexpected startup failures should be written somewhere the user can find.
- Logs must include enough context to diagnose the failure.
- Do not include sensitive configuration contents unnecessarily.
- Do not swallow errors that materially change behavior without leaving useful evidence.
- Expected transient process errors such as disappearance during enumeration may be handled quietly.
- Configuration, tray, registry, and termination failures should be distinguishable when practical.
Do not claim a failure’s root cause from an exception message alone.
Keep separate:
- verified fact;
- observation;
- hypothesis;
- decision;
- open question.
Repository Change Rules
- Keep changes focused on the requested behavior.
- Preserve unrelated user changes.
- Follow existing naming and error-handling conventions unless the task explicitly improves them.
- Do not broadly reformat or rewrite watchdog_app.py.
- Do not introduce speculative frameworks, services, databases, installers, or dependencies.
- Do not upgrade dependencies unless required.
- Do not edit generated build artifacts as source.
- Do not commit build or dist changes unless the task explicitly requires packaged artifacts.
- Do not change icons or branding unless requested.
- Do not remove the themed window animation or user guide as incidental cleanup.
- Do not silently change grace-period limits, polling intervals, startup behavior, process grouping, matching, or kill scope.
- Prefer the smallest coherent implementation that fully satisfies the request.
The application is currently compact, but watchdog_app.py contains persistence, process logic, Win32 integration, threading, UI, tray behavior, and startup registration. Split code only when doing so materially supports the requested change and preserves behavior.
Git Rules
Before modifying the repository, verify:
repository root
current branch
HEAD commit
working-tree status
configured remotes
required base ref or commit
Do not:
- invent branches or commits;
- overwrite unrelated work;
- amend, rebase, merge, force-push, or rewrite history unless explicitly required;
- assume local main matches origin/main;
- assume a remote-tracking ref is current without fetching when current remote state matters;
- push unless requested.
If asked to push:
1. Verify the remote.
2. Push the intended commit.
3. Verify the destination remote ref resolves to that exact commit.
4. Only then report the push as successful.
A local commit is not a remote commit.
Investigation Before Editing
Before implementing a change:
1. Inspect the applicable instructions.
2. Inspect the relevant source.
3. Inspect nearby tests or confirm that none exist.
4. Search for similar behavior.
5. Trace the affected state and callbacks.
6. Identify configuration compatibility implications.
7. Identify whether real process termination could occur during validation.
8. Determine the smallest safe change.
Search specifically before creating parallel implementations for:
- configuration loading and saving;
- process identity normalization;
- process enumeration and grouping;
- visible-window detection;
- pending grace-period state;
- process-tree termination;
- install-directory expansion;
- tray callbacks;
- Tkinter scheduling;
- startup registration;
- resource loading;
- crash logging.
Do not begin with a broad rewrite.
Questions and Ambiguity
Ask for clarification only when ambiguity would materially affect behavior or safety.
Clarification is required when reasonable interpretations would change:
- which processes are watched;
- which processes are killed;
- whether visible windows or process existence controls triggering;
- configuration compatibility;
- startup behavior;
- deletion or migration of user data;
- registry behavior;
- packaging or distribution;
- administrator privilege expectations.
Otherwise, use repository evidence, choose the least invasive reasonable interpretation, state material assumptions, and proceed.
Testing and Validation
Changed behavior should receive focused automated coverage.
Because process termination is destructive, separate pure decision logic from actual operating-system actions when practical.
Useful coverage includes:
- legacy and current configuration loading;
- configuration migration and round-trip persistence;
- exact-path versus name-only matching;
- case-insensitive Windows path handling;
- visible-window trigger transitions;
- grace-period scheduling;
- cancellation when an application reopens;
- disabled watchdog behavior;
- descendant and install-directory target selection;
- inaccessible or disappearing processes;
- preservation of temporarily missing selections;
- startup registry decision logic;
- PyInstaller resource path resolution.
Validation must use observed commands and results.
Run in proportion to the change:
1. Syntax/import validation.
2. Narrow relevant automated tests.
3. Broader project tests when available.
4. Safe source-level startup or UI checks when appropriate.
5. PyInstaller build when packaging is affected.
6. Packaged executable smoke testing when explicitly required and safe.
The existing build.bat kills running ProcessWatchdog.exe instances and deletes build outputs before rebuilding. Do not run it casually. Running it is appropriate only when the task requires a clean packaged build and interruption of the running application is within scope.
If validation fails:
- report the exact command and useful error;
- determine whether the failure is change-related, pre-existing, or environmental when evidence permits;
- do not hide the failure;
- do not claim PASS.
A test passes only when its successful result was directly observed.
Definition of Done
A task is complete only when:
1. The requested behavior is implemented.
2. Process matching and termination remain within the intended boundary.
3. Existing configurations remain usable.
4. Tkinter and watcher-thread boundaries remain safe.
5. Relevant regression coverage was added when warranted.
6. Required validation was actually run.
7. Observed failures were reported honestly.
8. The diff contains no accidental unrelated changes.
9. No sensitive configuration data was exposed.
10. The final report distinguishes completed work from unresolved issues.
Final Report
When implementation work is finished, report concisely:
- result: PASS, PARTIAL, or FAIL when appropriate;
- what changed;
- important files changed;
- tests and validation actually run, with observed results;
- commit SHA if a commit was created;
- remote verification only if it was actually performed;
- remaining risks, failures, or unresolved issues.
Do not claim:
- fixed;
- tested;
- built;
- running;
- killed;
- migrated;
- committed;
- pushed;
- installed;
- PASS;
unless the relevant result was directly verified.
Task Prompts vs. This File
This file contains permanent Process Watchdog engineering rules.
Individual task prompts should contain only:
- objective;
- verified starting state or base;
- relevant constraints;
- required behavior;
- safety boundaries;
- acceptance criteria;
- required validation;
- expected deliverable.
Do not add one-off feature requirements or temporary mission history to this file.
Project instructions describe Process Watchdog. Task prompts describe the requested change.