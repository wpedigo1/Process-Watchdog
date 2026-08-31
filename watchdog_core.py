"""
Process Watchdog - core logic module.

Holds the non-UI behavior: configuration persistence, process discovery and
matching, visible-window detection, termination selection, the background
watcher thread, and Windows HWND / image-resource helpers shared with the UI.

This is a pure structural extraction from watchdog_app.py. No behavior was
changed. watchdog_app.py remains the entry point; watchdog_ui.py holds the
windows, dialogs and animations.
"""

import json
import os
import sys
import time
import threading
import ctypes
from ctypes import wintypes

import psutil

APP_NAME = "Process Watchdog"
APP_VERSION = "2026-08-23-pathfix1"
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".process_watchdog", "config.json")
SYSTEM_USERNAMES = ("SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE")
SYSTEM_PATH_HINTS = ("\\windows\\", "\\windows\\system32", "\\windows\\syswow64")

DEFAULT_CONFIG = {
    "poll_interval": 2.0,
    "grace_seconds": 10.0,
    "watchdogs": []
}


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

def _normalize_process_entry(e):
    """Old Watchdogs stored plain strings; new ones store {"name","exe"} so
    matching can use the exact install path. Accept both transparently."""
    if isinstance(e, dict):
        return {"name": e.get("name") or "", "exe": e.get("exe") or ""}
    return {"name": str(e), "exe": ""}


def load_config():
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    if not os.path.exists(CONFIG_PATH):
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("poll_interval", DEFAULT_CONFIG["poll_interval"])
        data.setdefault("grace_seconds", DEFAULT_CONFIG["grace_seconds"])
        legacy_watchdogs = data.pop("rules", [])
        if not data.get("watchdogs") and legacy_watchdogs:
            data["watchdogs"] = legacy_watchdogs
        else:
            data.setdefault("watchdogs", [])
        for watchdog in data["watchdogs"]:
            watchdog["trigger"] = [_normalize_process_entry(e) for e in watchdog.get("trigger", [])]
            watchdog["kill"] = [_normalize_process_entry(e) for e in watchdog.get("kill", [])]
        return data
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


# ---------------------------------------------------------------------------
# Process helpers
# ---------------------------------------------------------------------------

def is_system_process(proc):
    """Best-effort heuristic for 'boring OS process' so it can be hidden."""
    try:
        username = (proc.info.get("username") or "").upper()
        exe = (proc.info.get("exe") or "").lower()
        name = (proc.info.get("name") or "").lower()

        for sysname in SYSTEM_USERNAMES:
            if sysname in username:
                return True
        for hint in SYSTEM_PATH_HINTS:
            if hint in exe:
                return True
        if name in ("system", "registry", "idle", "svchost.exe", "wininit.exe",
                    "csrss.exe", "smss.exe", "lsass.exe", "services.exe",
                    "dwm.exe", "fontdrvhost.exe", "winlogon.exe"):
            return True
    except Exception:
        pass
    return False


def list_processes(hide_system=True):
    """Return a de-duplicated, sorted list of (name, exe_path) tuples."""
    seen = {}
    for proc in psutil.process_iter(attrs=["name", "username", "exe"]):
        try:
            if hide_system and is_system_process(proc):
                continue
            name = proc.info.get("name") or ""
            if not name:
                continue
            seen[name.lower()] = name
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return sorted(seen.values(), key=str.lower)


def _norm_path(p):
    return (p or "").strip().lower()


def _is_self(proc):
    """True if the given process identity is Process Watchdog itself.

    Matched on EITHER the pid (os.getpid()) OR the exe path normalized
    through _norm_path against sys.executable. Both are checked because a
    process that is really us might be reported under a different pid, or
    its exe might be unavailable (access denied), mirroring this file's
    existing honest handling of that case."""
    if proc.pid == os.getpid():
        return True
    if _norm_path(proc.info.get("exe")) == _norm_path(sys.executable):
        return True
    return False


def find_matching_processes(entries):
    """Currently running processes that match any of the given identity
    entries — each entry is {"name": ..., "exe": ...}.

    An entry with a recorded exe path is matched by that EXACT path. This
    is what tells apart two different apps that happen to share an
    executable name — e.g. a bundled 'chrome.exe' shipped inside another
    app's install folder vs. the real Google Chrome browser. Matching by
    name alone (the old behavior) could not distinguish these and would
    silently also catch the wrong one.

    An entry with no path recorded (rare — access was denied when it was
    first picked, or it's an old watchdog saved before path-tracking existed)
    falls back to matching by name only, same as before."""
    path_targets = set()
    name_only_targets = set()
    for e in entries:
        exe = _norm_path(e.get("exe"))
        if exe:
            path_targets.add(exe)
        else:
            name_only_targets.add((e.get("name") or "").lower())

    matches = {}
    for proc in psutil.process_iter(attrs=["name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            exe = _norm_path(proc.info.get("exe"))
            if exe and exe in path_targets:
                matches[proc.pid] = proc
            if name and name in name_only_targets:
                matches[proc.pid] = proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return list(matches.values())


_user32 = ctypes.windll.user32 if os.name == "nt" else None
_gdi32 = ctypes.windll.gdi32 if os.name == "nt" else None


def _get_visible_window_pids():
    """PIDs that currently own at least one visible, titled top-level window —
    i.e. processes that actually look 'open' to the user, as opposed to
    background/zombie processes with no window."""
    pids = set()
    if _user32 is None:
        return pids

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def enum_handler(hwnd, _lparam):
        if _user32.IsWindowVisible(hwnd) and _user32.GetWindowTextLengthW(hwnd) > 0:
            pid = wintypes.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pids.add(pid.value)
        return True

    _user32.EnumWindows(EnumWindowsProc(enum_handler), 0)
    return pids


def open_trigger_names(entries):
    """Names of processes (from the given identity entries) that currently
    own a visible top-level window — i.e. what's actually keeping this watchdog
    from firing right now. Empty list means nothing in the set looks 'open',
    so the grace-period countdown should be running."""
    procs = find_matching_processes(entries)
    if not procs:
        return []
    if _user32 is None:
        # Non-Windows fallback (dev/testing off Windows) — best effort.
        return sorted({(p.info.get("name") or "") for p in procs if p.info.get("name")}, key=str.lower)
    visible_pids = _get_visible_window_pids()
    if not visible_pids:
        return []
    names = set()
    for proc in procs:
        if proc.pid in visible_pids:
            n = proc.info.get("name") or ""
            if n:
                names.add(n)
    return sorted(names, key=str.lower)


def kill_processes(entries):
    """Force-kill every running process matching the given identity entries,
    plus:
      - every descendant in its process tree (spawned child/helper processes)
      - every OTHER running process installed in the same folder (catches
        helper services that aren't actual child processes — just separate
        binaries living next to the main exe).
    Returns count killed."""
    matched = find_matching_processes(entries)
    install_dirs = set()
    for proc in matched:
        exe = proc.info.get("exe")
        if exe:
            install_dirs.add(os.path.dirname(exe).lower())

    to_kill = {}
    for proc in matched:
        to_kill[proc.pid] = proc
        try:
            for child in proc.children(recursive=True):
                to_kill[child.pid] = child
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if install_dirs:
        for proc in psutil.process_iter(attrs=["pid", "exe"]):
            try:
                exe = proc.info.get("exe")
                if not exe:
                    continue
                exe_dir = os.path.dirname(exe).lower()
                if any(exe_dir == d or exe_dir.startswith(d + os.sep) for d in install_dirs):
                    to_kill[proc.info["pid"]] = proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    # Never terminate Process Watchdog itself. Filter once at the point
    # where all three kill sources (direct matches, descendants, and other
    # binaries installed beneath a matched project) have already merged, so
    # self is excluded from the kill set entirely — there is exactly one
    # place to verify, and self can never be reached via any source path.
    to_kill = {pid: proc for pid, proc in to_kill.items() if not _is_self(proc)}

    killed = 0
    for proc in to_kill.values():
        try:
            proc.kill()
            killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return killed


# ---------------------------------------------------------------------------
# Background watcher thread
# ---------------------------------------------------------------------------

class Watcher(threading.Thread):
    def __init__(self, get_config, on_kill=None):
        super().__init__(daemon=True)
        self.get_config = get_config
        self.on_kill = on_kill
        self._stop = threading.Event()
        self._was_running = {}  # watchdog_id -> bool
        self._pending_kill_at = {}  # watchdog_id -> timestamp
        self._open_names = {}  # watchdog_id -> [names currently blocking the watchdog]

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            cfg = self.get_config()
            grace = float(cfg.get("grace_seconds", 3.0))
            now = time.time()

            for watchdog in cfg.get("watchdogs", []):
                rid = watchdog["id"]
                if not watchdog.get("enabled", True):
                    self._open_names.pop(rid, None)
                    continue
                trigger = watchdog.get("trigger", [])
                kill_list = watchdog.get("kill", [])

                open_names = open_trigger_names(trigger)
                self._open_names[rid] = open_names
                running_now = bool(open_names)
                was_running = self._was_running.get(rid, running_now)

                if was_running and not running_now:
                    # Just closed -> schedule a kill after grace period
                    self._pending_kill_at[rid] = now + grace
                elif running_now:
                    # Reopened before grace expired -> cancel pending kill
                    self._pending_kill_at.pop(rid, None)

                self._was_running[rid] = running_now

                pending_at = self._pending_kill_at.get(rid)
                if pending_at and now >= pending_at:
                    self._pending_kill_at.pop(rid, None)
                    count = kill_processes(kill_list)
                    if count and self.on_kill:
                        self.on_kill(watchdog.get("name", "watchdog"), count)

            time.sleep(float(cfg.get("poll_interval", 2.0)))

    def get_pending(self):
        """watchdog_id -> seconds remaining until kill (only for watchdogs currently pending)."""
        now = time.time()
        return {rid: max(0.0, at - now) for rid, at in self._pending_kill_at.items()}

    def get_open(self):
        """watchdog_id -> names currently keeping that watchdog from firing (empty
        list = nothing is blocking it). Lets the UI show exactly why a watchdog
        looks stuck instead of a generic 'Watching' with no explanation."""
        return dict(self._open_names)


# ---------------------------------------------------------------------------
# Process picker data
# ---------------------------------------------------------------------------

def get_process_groups(hide_system=True):
    """Groups running processes the way Task Manager visually nests them —
    by shared install folder — so a multi-binary app (main exe + bundled
    runtime + helper services) can be selected as one unit, or expanded to
    pick pieces individually. Returns [(label, [(name, exe_path), ...]), ...]
    — exe_path is carried through so selections can be matched exactly,
    not just by name (two different apps can ship an identically-named
    exe, e.g. a bundled Chromium runtime vs. the real Google Chrome)."""
    procs = []
    for proc in psutil.process_iter(attrs=["name", "exe"]):
        try:
            if hide_system and is_system_process(proc):
                continue
            name = proc.info.get("name") or ""
            if not name:
                continue
            procs.append((name, proc.info.get("exe") or ""))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    by_dir = {}
    no_dir = {}
    for name, exe in procs:
        if exe:
            d = os.path.dirname(exe)
            by_dir.setdefault(d, {})[name] = exe
        else:
            no_dir[name] = ""

    groups = []
    for d, name_to_exe in by_dir.items():
        if len(name_to_exe) >= 2:
            label = os.path.basename(d.rstrip("\\/")) or d
            entries = sorted(name_to_exe.items(), key=lambda t: t[0].lower())
            groups.append((label, entries))
        else:
            n, e = next(iter(name_to_exe.items()))
            groups.append((n, [(n, e)]))
    for n, e in no_dir.items():
        groups.append((n, [(n, e)]))

    groups.sort(key=lambda g: g[0].lower())
    return groups


# ---------------------------------------------------------------------------
# Resource / icon helpers (shared with the UI)
# ---------------------------------------------------------------------------

def resource_path(filename):
    """Works both running from source and from a PyInstaller --onefile exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, filename)


def apply_window_icon(win):
    """Best-effort — replaces Tk's default feather icon with icon.ico."""
    try:
        win.iconbitmap(default=resource_path("icon.ico"))
    except Exception:
        pass
