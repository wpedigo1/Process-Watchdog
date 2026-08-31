# Process Watchdog — Resource Baseline

Baseline measured from the freshly built executable created during **MISSION 1A**,
committed at HEAD `342349183ff3c303532c86d521948a4aabfc4cb6`.
`dist\ProcessWatchdog.exe` was built in this mission from that source.

Every value below is followed by the exact command that produced it.

## Environment

| Item | Value | Command |
|------|-------|---------|
| Python | 3.11.0 | `python --version` |
| OS build | Windows 10.0.26200.9278 | `cmd /c ver` |
| psutil | 7.2.2 | `python -m pip show psutil` |
| pystray | 0.19.5 | `python -m pip show pystray` |
| Pillow | 12.2.0 | `python -m pip show Pillow` |
| pyinstaller | 6.22.2 | `python -m pip show pyinstaller` |
| watchdog_app.py lines | 997 | `python -c "import os;d=open('watchdog_app.py','rb').read().replace(b'\r\n',b'\n');print('lines',d.count(b'\n'))"` |
| watchdog_app.py bytes on disk | 39418 | `python -c "import os;print(os.path.getsize('watchdog_app.py'))"` |
| watchdog_app.py LF-normalized sha256 | `5c19584ba32cefe6dcf87e91ca6ede2070aca509f0e6bb2a67d8b9a34f03eb95` | python hashlib over CRLF-stripped content |

The four dependency versions above are the **post-build** values; all four were unchanged by
`build.bat` (identical before and after), so there was no pip side-effect.

## Packaged executable

| Item | Value | Command |
|------|-------|---------|
| dist\ProcessWatchdog.exe size (bytes) | 31500369 | `(Get-Item 'dist\ProcessWatchdog.exe').Length` |
| dist\ProcessWatchdog.exe last modified | 2026-08-30 22:15:48 | `Get-Item 'dist\ProcessWatchdog.exe'` |
| Built from HEAD | `342349183ff3c303532c86d521948a4aabfc4cb6` | `git rev-parse HEAD` at build time |

## Idle memory

Measured with `python tools/measure_baseline.py` while the app was idle for 30+ seconds.
A PyInstaller --onefile exe appears as a parent/child pair; both are reported.

| Sample | pid 25668 (parent) RSS | pid 26380 (child) RSS |
|--------|------------------------|-----------------------|
| 1 | 8736768 | 48336896 |
| 2 | 8736768 | 48349184 |
| 3 | 8736768 | 48349184 |

Values are `p.memory_info().rss` from the memory-sampling section of `tools/measure_baseline.py`
(`python tools/measure_baseline.py`). Both PIDs are stable across the 3 samples ~10s apart.

## Idle CPU

`python tools/measure_baseline.py` — 12 samples of `cpu_percent(interval=1.0)` each.

| pid | min | median | max | n |
|-----|-----|--------|-----|---|
| 25668 (parent) | 0.00 | 0.00 | 0.00 | 12 |
| 26380 (child) | 0.00 | 0.00 | 0.00 | 12 |

## Thread and handle count

From the per-process snapshot section of `tools/measure_baseline.py`.

| pid | num_threads | num_handles | create_time |
|-----|-------------|-------------|-------------|
| 25668 (parent) | 4 | 100 | 1788146256.25 |
| 26380 (child) | 9 | 656 | 1788146258.47 |

## poll_interval and grace_seconds currently in effect

**UNMEASURED.** Reading the real user configuration at
`%USERPROFILE%\.process_watchdog\config.json` is forbidden by this mission's absolute
constraints, so the in-effect values could not be verified. This is a documented conflict
between Step 5 (report the values) and the absolute constraints (do not read the real config);
the stricter read-prohibition was honored.

For reference only, the source-code defaults in `watchdog_app.DEFAULT_CONFIG` are
`poll_interval: 2.0` and `grace_seconds: 10.0`. These were NOT verified as the in-effect values.

## Cold start time (launch to visible window)

**UNMEASURED / NOT APPLICABLE.** The app was launched with
`Start-Process -FilePath 'dist\ProcessWatchdog.exe'`. On non-first-run launches Process Watchdog
starts hidden to the system tray and shows no visible window. After a 30s settle, both
ProcessWatchdog processes reported an empty `MainWindowTitle`
(`Get-Process -Name 'ProcessWatchdog' | Select-Object Id,MainWindowTitle`), confirming the app
ran hidden to tray with no visible top-level window. Because no window is shown on this launch
path, a launch-to-visible-window time is not observable; that metric would only apply to a
first-run launch or opening the window via the tray.

## Post-measurement shutdown

The app was closed by terminating the two measured PIDs (25668, 26380) with
`taskkill /PID 25668 /PID 26380 /F`. Verification commands showed no remaining instance:
`tasklist /FI "IMAGENAME eq ProcessWatchdog.exe"` reported "No tasks are running", and psutil
reported `[]`. NOTE: the tray-Quit menu path could not be invoked programmatically from the
command line; the process was stopped via forced termination instead, which is a deviation from
the mission's preferred tray-Quit shutdown. No `ProcessWatchdog.exe` remains running.
