# Process Watchdog

Replaces your "Kill X.bat" shortcuts with one tray app that watches your apps
and force-kills the leftover processes automatically when the app closes.

## Build (one-time, on Windows)

1. Install Python 3.10+ from python.org if you don't have it (check "Add to PATH" during install).
2. Put `watchdog_app.py`, `requirements.txt`, and `build.bat` in one folder.
3. Double-click `build.bat` (or run it from a terminal in that folder).
4. When it finishes, `dist\ProcessWatchdog.exe` is your app. Copy it wherever you like
   (Desktop, Startup folder, etc.) — it's a single standalone file.

## Using it

- Launch `ProcessWatchdog.exe`. It opens a window and adds an icon to your system tray.
- Click **Add Watchdog**:
  - **Name** it (e.g. "Claude Desktop").
  - **Trigger process(es)**: pick the process(es) that represent "the app is open"
    (double-click in the list, or type the exe name manually if it's not currently running).
  - Use **Hide system processes** to toggle whether Windows/SYSTEM-owned processes
    (svchost.exe, dwm.exe, etc.) clutter the picker — on by default.
  - **Kill these**: pick the leftover process(es) you currently kill by hand
    (can be the same as trigger, or extra helper/background processes).
  - Save.
- Close the window (X) — it minimizes to tray, it keeps running.
- Right-click the tray icon → **Quit** to fully exit.

## How it decides when to kill

Every ~2 seconds it checks whether the trigger process(es) are running. When they go
from running → not running, it waits a grace period (10 sec by default — adjustable
in the app itself, top of the window) in case you're just relaunching the app, then
kills everything in the kill list.

The **Status** column shows a live countdown ("Killing in 7s"...) while a Watchdog is
in its grace period, so you can see exactly what's about to happen and when.

## Config file

Watchdogs are stored in `%USERPROFILE%\.process_watchdog\config.json` — you can back this
up or hand-edit it if you want to bulk-add Watchdogs.

## Startup on boot (optional)

Press `Win+R`, type `shell:startup`, hit enter, and drop a shortcut to
`ProcessWatchdog.exe` in that folder. It'll launch (minimized to tray) every login.
