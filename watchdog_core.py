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
PROTECTED_PROCESS_NAMES = (
    "system", "registry", "idle", "svchost.exe", "wininit.exe", "csrss.exe",
    "smss.exe", "lsass.exe", "services.exe", "dwm.exe", "fontdrvhost.exe",
    "winlogon.exe",
)

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
            _migrate_watchdog(watchdog)
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
        if name in PROTECTED_PROCESS_NAMES:
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


def _live_identity(proc):
    """Read a process's name/exe via live calls, not the .info cache (which
    is only populated for process_iter results, not .children()). Honest
    fallback on NoSuchProcess/AccessDenied, matching this file's existing
    error-handling convention elsewhere."""
    try:
        name = proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        name = ""
    try:
        exe = proc.exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        exe = ""
    return name, exe


def _is_self(proc):
    """True if the given process identity is Process Watchdog itself.

    Matched on EITHER the pid (os.getpid()) OR the exe path normalized
    through _norm_path against sys.executable. Both are checked because a
    process that is really us might be reported under a different pid, or
    its exe might be unavailable (access denied), mirroring this file's
    existing honest handling of that case."""
    if proc.pid == os.getpid():
        return True
    if _norm_path(_live_identity(proc)[1]) == _norm_path(sys.executable):
        return True
    return False


def is_protected_entry(entry):
    """True if this {"name","exe"} identity is Process Watchdog itself or a
    protected core OS executable/path. Works without a live process, so it
    covers offline Browse/manual entries as well as matched processes."""
    name = (entry.get("name") or "").lower()
    exe = (entry.get("exe") or "").lower()

    if exe == _norm_path(sys.executable):
        return True
    if not exe and name == os.path.basename(sys.executable).lower():
        return True
    for hint in SYSTEM_PATH_HINTS:
        if hint in exe:
            return True
    if name in PROTECTED_PROCESS_NAMES:
        return True
    return False


def _is_protected_owner(proc):
    """True if the live process is owned by SYSTEM, LOCAL SERVICE, or NETWORK
    SERVICE.  Requires a live psutil.Process, so it only runs at kill time,
    covering both direct matches and recursive children uniformly."""
    try:
        username = (proc.username() or "").upper()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    return any(sysname in username for sysname in SYSTEM_USERNAMES)


# ---------------------------------------------------------------------------
# Watched-app / meal-target model
# ---------------------------------------------------------------------------

def _entry_key(e):
    """Dedup identity for a process entry: (normalized name, normalized exe).
    "" and None both normalize to '', so a name-only entry never collides with
    an exact-path entry of a different name."""
    return (_norm_path(e.get("name")), _norm_path(e.get("exe")))


def _dedupe_entries(entries):
    """Dedupe process entries by (name, exe) identity, preserving order."""
    seen = set()
    out = []
    for e in entries:
        key = _entry_key(e)
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def effective_trigger(watchdog):
    """The entries a watchdog actually triggers on: just [watched_app] when a
    watched app is set, [] otherwise (a watched_app of None means the watchdog
    is ambiguous and never triggers until Retrain sets one)."""
    app = watchdog.get("watched_app")
    return [app] if app else []


def effective_kill(watchdog):
    """Everything a watchdog kills: the watched app (always an implicit kill
    target) plus its meal_targets, deduplicated by (name, exe). With no
    watched_app (ambiguous, not yet retrained) it is meal_targets verbatim — no
    dedup, mirroring what was persisted."""
    app = watchdog.get("watched_app")
    if not app:
        return watchdog.get("meal_targets", [])
    candidates = [app]
    candidates.extend(watchdog.get("meal_targets", []))
    return _dedupe_entries(candidates)


def _migrate_watchdog(watchdog):
    """Migrate one watchdog in place from the legacy trigger/kill schema to the
    watched_app/meal_targets schema.

    - Already has watched_app: leave as-is (already migrated); drop any leftover
      trigger/kill keys and ensure meal_targets never duplicates the watched app.
    - Exactly 1 distinct (name, exe) in trigger: that is watched_app; meal_targets
      is kill minus the watched app, deduped.
    - 0 distinct in trigger: watched_app = None; meal_targets is kill as-is
      (unchanged). Ambiguous — needs Retrain.
    - 2+ distinct in trigger: watched_app = None; meal_targets is dedup(trigger +
      kill) preserving every candidate. Ambiguous — needs Retrain.
    """
    if "watched_app" in watchdog:
        watchdog.pop("trigger", None)
        watchdog.pop("kill", None)
        app = watchdog.get("watched_app")
        app = _normalize_process_entry(app) if app is not None else None
        watchdog["watched_app"] = app
        meal = [_normalize_process_entry(e) for e in watchdog.get("meal_targets", [])]
        if app is not None:
            akey = _entry_key(app)
            meal = [e for e in meal if _entry_key(e) != akey]
        watchdog["meal_targets"] = _dedupe_entries(meal)
        return

    trigger = watchdog.get("trigger", [])
    kill = watchdog.get("kill", [])
    distinct_trigger = {_entry_key(e) for e in trigger if e.get("name")}

    if len(distinct_trigger) == 1:
        app_source = next(e for e in trigger if e.get("name"))
        app = _normalize_process_entry(app_source)
        akey = _entry_key(app)
        meal = _dedupe_entries([e for e in kill if _entry_key(e) != akey])
    else:
        # 0 or 2+ distinct trigger entries -> ambiguous, watched_app stays None
        app = None
        meal = kill if len(trigger) == 0 else _dedupe_entries(trigger + kill)

    watchdog["watched_app"] = app
    watchdog["meal_targets"] = meal
    watchdog.pop("trigger", None)
    watchdog.pop("kill", None)


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


class KillResult:
    """Outcome of a kill_processes call when detail=True. killed/failed are
    sorted, deduplicated lists of process names."""
    __slots__ = ("killed", "failed")

    def __init__(self, killed, failed):
        self.killed = killed
        self.failed = failed


def kill_processes(entries, detail=False):
    """Force-kill every running process matching the given identity entries,
    plus every descendant in its process tree (spawned child/helper processes).

    By default (detail=False) returns the count killed — an int, exactly as
    before. With detail=True, additionally tracks per-name outcomes and
    returns a KillResult exposing .killed and .failed:
    - killed: names of processes actually terminated successfully;
    - failed: names of processes that reached the kill attempt (not filtered
      out by _is_self/is_protected_entry/_is_protected_owner) but raised
      AccessDenied on .kill(). NoSuchProcess is silently not counted, exactly
      as before. Processes excluded by the protection filters are invisible to
      this reporting too — they were never a real kill attempt."""
    matched = find_matching_processes(entries)

    to_kill = {}
    for proc in matched:
        to_kill[proc.pid] = proc
        try:
            for child in proc.children(recursive=True):
                to_kill[child.pid] = child
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Never terminate Process Watchdog itself or a protected core OS
    # identity. Filter once at the point where all kill sources (direct
    # matches and descendants) have already merged, so self and protected
    # identities are excluded from the kill set entirely — there is exactly
    # one place to verify, and neither can ever be reached via any source
    # path.
    def _unprotected(proc):
        if _is_self(proc):
            return False
        name, exe = _live_identity(proc)
        if is_protected_entry({"name": name, "exe": exe}):
            return False
        return not _is_protected_owner(proc)

    to_kill = {
        pid: proc
        for pid, proc in to_kill.items()
        if _unprotected(proc)
    }

    killed = 0
    killed_names = []
    failed_names = []
    for proc in to_kill.values():
        name = _live_identity(proc)[0]
        try:
            proc.kill()
            killed += 1
            if name:
                killed_names.append(name)
        except psutil.AccessDenied:
            if name:
                failed_names.append(name)
            continue
        except psutil.NoSuchProcess:
            continue

    if not detail:
        return killed

    def _dedupe(names):
        seen = set()
        out = []
        for n in names:
            if not n or n in seen:
                continue
            seen.add(n)
            out.append(n)
        return sorted(out, key=str.lower)

    return KillResult(_dedupe(killed_names), _dedupe(failed_names))


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
                trigger = effective_trigger(watchdog)
                kill_list = effective_kill(watchdog)

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
                    result = kill_processes(kill_list, detail=True)
                    if self.on_kill:
                        # Report every grace-elapse outcome, including the
                        # "nothing to eat" case, so the UI can show an honest
                        # per-target result either way.
                        self.on_kill(rid, watchdog.get("name", "watchdog"),
                                     result.killed, result.failed)

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
    for proc in psutil.process_iter(attrs=["pid", "name", "exe"]):
        try:
            if hide_system and is_system_process(proc):
                continue
            if proc.info.get("pid") == os.getpid():
                # Never offer Process Watchdog's own running instance as a target.
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


# ---------------------------------------------------------------------------
# Windows theme / accent helpers (read-only, fail safe)
# ---------------------------------------------------------------------------

def _read_reg_dword(key, value_name, default=None):
    """Read a DWORD from HKCU, returning default on any failure (missing key,
    missing value, wrong type). Never raises."""
    if os.name != "nt":
        return default
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ) as hkey:
            value, value_type = winreg.QueryValueEx(hkey, value_name)
        if value_type != winreg.REG_DWORD:
            return default
        return value
    except Exception:
        return default


def detect_windows_theme():
    """Return "light" or "dark" from the Windows AppsUseLightTheme setting.
    A missing key/value is the Windows default (light) — never an error."""
    apps_theme = _read_reg_dword(
        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        "AppsUseLightTheme",
        default=1,
    )
    return "light" if apps_theme else "dark"


def get_accent_color():
    """Return the Windows accent color as "#RRGGBB". DWM AccentColor is stored
    as 0xAABBGGRR (alpha, then B, G, R). On any failure fall back to Windows'
    own default Fluent accent blue. Never raises."""
    accent = _read_reg_dword(r"Software\Microsoft\Windows\DWM", "AccentColor")
    if accent is None:
        return "#0078D4"
    r = (accent >> 0) & 0xFF
    g = (accent >> 8) & 0xFF
    b = (accent >> 16) & 0xFF
    return "#%02X%02X%02X" % (r, g, b)
