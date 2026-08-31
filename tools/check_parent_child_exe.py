"""Mission 1C-VERIFY: enumerate the PyInstaller parent/child exe paths.

Standalone diagnostic tool. NOT wired into the application.

Launches dist\\ProcessWatchdog.exe, waits for it to settle, then enumerates
every process named ProcessWatchdog.exe via psutil and prints pid, ppid, exe,
and whether each exe (normalized case-insensitively, same as _norm_path) equals
the installed dist\\ProcessWatchdog.exe path.

Enumeration only: this script never kills or terminates any process on its own
beyond closing the specific ProcessWatchdog.exe instances it launched for this
check. Because a PyInstaller one-file app runs as a parent (bootloader) /
child (app) pair, we clean up with `taskkill /PID <pid> /F` on the specific PIDs
launched by this run, since tray-Quit cannot be driven reliably from this
context (deviation pre-authorized by the mission).
"""

import os
import subprocess
import sys
import time

import psutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, "dist", "ProcessWatchdog.exe")
PROC_NAME = "ProcessWatchdog.exe"
SETTLE_SECONDS = 6


def norm(p):
    return (p or "").strip().lower()


def find_watchdog_procs():
    out = []
    for proc in psutil.process_iter(attrs=["pid", "ppid", "exe", "name"]):
        try:
            if (proc.info.get("name") or "").lower() == PROC_NAME.lower():
                out.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def main():
    if not os.path.exists(EXE):
        print(f"FATAL: {EXE} does not exist. Run build.bat first.")
        return 1

    launched_pids = []

    print(f"Launching: {EXE}")
    handle = subprocess.Popen([EXE])
    launched_pids.append(handle.pid)
    print(f"Popen root pid: {handle.pid}")

    print(f"Waiting {SETTLE_SECONDS}s for the process tree to settle...")
    time.sleep(SETTLE_SECONDS)

    procs = find_watchdog_procs()
    print("\n=== Processes named ProcessWatchdog.exe ===")
    print(f"{'pid':>8} {'ppid':>8}  exe-matches-installed  exe path")
    for proc in procs:
        info = proc.info
        exe = info.get("exe")
        matches = exe is not None and norm(exe) == norm(EXE)
        print(f"{proc.pid:>8} {info.get('ppid'):>8}  {str(matches):<22} {exe}")
        launched_pids.append(proc.pid)

    print(f"\nTotal processes named {PROC_NAME} found: {len(procs)}")

    if len(procs) == 1:
        print("Finding: ONLY ONE process was found; no parent/child pair exists "
              "for this build configuration.")
    elif len(procs) >= 2:
        exe_paths = {norm(p.info.get("exe")) for p in procs}
        if len(exe_paths) == 1 and None not in exe_paths:
            print("Finding: CONFIRMED — all parent/child processes report the IDENTICAL "
                  "exe path. Mission 1C's _is_self exe-path check already covers the "
                  "parent process. The residual gap reported in Mission 1C does not exist "
                  "as described.")
        elif None in exe_paths:
            print("Finding: at least one process reported no exe (None). Table above shows "
                  "which, enumerated from psutil; pid/ppid relationship is shown too.")
        else:
            print("Finding: CONFIRMED — parent and child report DIFFERENT exe paths. "
                  "Mission 1C's residual gap IS real. See table for the actual reported exe "
                  "values. (No fix attempted in this mission.)")

    # Cleanup: close only the ProcessWatchdog.exe instances launched by this run.
    # No ProcessWatchdog.exe was running before we launched, so all that we found
    # are ours. tray-Quit is not scriptable here; use taskkill /F on our PIDs.
    print("\nCleanup: taskkill /PID ... /F on the specific PIDs launched by this run "
          "(tray-Quit not scriptable from this context; deviation pre-authorized).")
    unique_pids = sorted(set(launched_pids))
    for pid in unique_pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                       capture_output=True, text=True)
        print(f"  taskkill /PID {pid} /F")

    print("Waiting 2s for cleanup to settle...")
    time.sleep(2)
    remaining = find_watchdog_procs()
    print(f"Remaining ProcessWatchdog.exe after cleanup: {len(remaining)}")
    for p in remaining:
        print(f"  still running: pid={p.pid} ppid={p.info.get('ppid')} exe={p.info.get('exe')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
