"""
Process Watchdog
-----------------
Runs in the system tray. Define Watchdogs like:
  "When claude.exe disappears, force-kill claude.exe / claude_helper.exe"
and it handles the cleanup automatically instead of you double-clicking
a .bat file every time.

Build to a Windows .exe with PyInstaller (see build.bat).
"""

import json
import os
import random
import sys
import time
import uuid
import ctypes
import traceback
from ctypes import wintypes
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import psutil

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None

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


def animate_eaten(win, on_done, bites=7, bite_delay_ms=150):
    """Visually 'eats' a Tk window in ragged bites — like a dog chewing
    through it — using real Win32 window regions (not a fake shrink/fade),
    then calls on_done(). Purely cosmetic: any failure (non-Windows,
    missing APIs, zero-size window) just skips straight to on_done()."""
    try:
        win.update_idletasks()
        w = win.winfo_width()
        h = win.winfo_height()
        hwnd = win.winfo_id()
        if _user32 is None or _gdi32 is None or w <= 1 or h <= 1:
            on_done()
            return

        RGN_DIFF = 4

        def chomp(i):
            if i > bites:
                try:
                    _user32.SetWindowRgn(hwnd, None, True)  # restore full shape for next time it's shown
                except Exception:
                    pass
                on_done()
                return
            eaten_x = int(w * i / bites)
            region = _gdi32.CreateRectRgn(eaten_x, 0, w, h)
            bite_r = max(10, h // 4)
            for _ in range(3):
                cy = random.randint(0, h)
                bite = _gdi32.CreateEllipticRgn(eaten_x - bite_r, cy - bite_r, eaten_x + bite_r, cy + bite_r)
                _gdi32.CombineRgn(region, region, bite, RGN_DIFF)
                _gdi32.DeleteObject(bite)
            _user32.SetWindowRgn(hwnd, region, True)  # SetWindowRgn now owns `region` — don't delete it
            win.after(bite_delay_ms, lambda: chomp(i + 1))

        chomp(1)
    except Exception:
        try:
            on_done()
        except Exception:
            pass


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
# Process picker widget (with "hide system processes" toggle)
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


class ProcessPicker(tk.Frame):
    """Task-Manager-style grouped tree of running processes. Extended
    multi-select: click a group to grab every process under it, expand to
    pick individual helper processes, Ctrl/Shift-click to combine any
    number of groups and/or individual processes into one watchdog. Includes
    a live filter box and a scrollbar (the list can be 100+ entries long).

    Selections are tracked by (name, exe_path) identity rather than name
    alone, and any selected process that isn't currently running (e.g.
    editing a watchdog while the app is closed) is kept in its own section so
    Save never silently drops it."""

    def __init__(self, master, initial=None):
        super().__init__(master)
        self.hide_system = tk.BooleanVar(value=True)
        self._preselect = {(e.get("name", ""), e.get("exe", "") or "") for e in (initial or [])}
        self._leaf_ident = {}  # iid -> (name, exe)

        top = tk.Frame(self)
        top.pack(fill="x")
        tk.Checkbutton(
            top, text="Hide system processes", variable=self.hide_system,
            command=self.refresh
        ).pack(side="left")
        tk.Button(top, text="Refresh", command=self.refresh).pack(side="right")

        filter_row = tk.Frame(self)
        filter_row.pack(fill="x", pady=(4, 0))
        tk.Label(filter_row, text="Filter:").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self.refresh())
        filter_entry = tk.Entry(filter_row, textvariable=self.filter_var)
        filter_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))

        tk.Label(
            self,
            text="Select any process(es) or whole groups — Ctrl/Shift-click to combine as many as you want:",
            fg="gray", wraplength=420, justify="left"
        ).pack(anchor="w", pady=(4, 0))

        tree_row = tk.Frame(self)
        tree_row.pack(fill="both", expand=True, pady=(4, 0))

        self.tree = ttk.Treeview(tree_row, show="tree", selectmode="extended")
        vsb = ttk.Scrollbar(tree_row, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.refresh()

    def _current_identities(self):
        idents = set()
        for iid in self.tree.selection():
            if iid in self._leaf_ident:
                idents.add(self._leaf_ident[iid])
            else:
                for child in self.tree.get_children(iid):
                    if child in self._leaf_ident:
                        idents.add(self._leaf_ident[child])
        return idents

    def refresh(self):
        prev_selected = self._current_identities() | self._preselect
        self.tree.delete(*self.tree.get_children())
        self._leaf_ident = {}
        live_idents = set()

        query = self.filter_var.get().strip().lower()
        groups = get_process_groups(hide_system=self.hide_system.get())

        for label, entries in groups:
            if query:
                entries = [(n, e) for n, e in entries if query in n.lower()]
                if not entries and query not in label.lower():
                    continue
            if len(entries) > 1:
                gid = self.tree.insert("", tk.END, text=f"\U0001F4C1 {label}  ({len(entries)})", open=bool(query))
                for n, e in entries:
                    leaf = self.tree.insert(gid, tk.END, text=n)
                    self._leaf_ident[leaf] = (n, e)
                    live_idents.add((n, e))
            elif entries:
                n, e = entries[0]
                leaf = self.tree.insert("", tk.END, text=n)
                self._leaf_ident[leaf] = (n, e)
                live_idents.add((n, e))

        missing = sorted(
            {ident for ident in prev_selected if ident[0] and ident not in live_idents},
            key=lambda t: t[0].lower()
        )
        if missing:
            gid = self.tree.insert(
                "", tk.END,
                text=f"\u23F8 Not running right now ({len(missing)}) — still kept in this Watchdog",
                open=True
            )
            for n, e in missing:
                leaf = self.tree.insert(gid, tk.END, text=n)
                self._leaf_ident[leaf] = (n, e)

        to_select = [iid for iid, ident in self._leaf_ident.items() if ident in prev_selected]
        if to_select:
            self.tree.selection_set(to_select)
            for iid in to_select:
                parent = self.tree.parent(iid)
                if parent:
                    self.tree.item(parent, open=True)
        self._preselect = set()

    def get_selected(self):
        idents = self._current_identities()
        return [{"name": n, "exe": e} for n, e in sorted(idents, key=lambda t: t[0].lower())]


# ---------------------------------------------------------------------------
# watchdog edit dialog
# ---------------------------------------------------------------------------

class watchdogDialog(tk.Toplevel):
    """Pick the process(es) this watchdog watches. Trigger and kill-target are
    the same process(es) — when they stop running, they get force-killed
    after the grace period (handles the case where they don't fully exit
    on their own)."""

    def __init__(self, master, watchdog=None):
        super().__init__(master)
        self.title("Watchdog")
        self.result = None
        self.geometry("480x660")
        self.minsize(420, 520)
        apply_window_icon(self)

        watchdog = watchdog or {}
        existing = watchdog.get("trigger") or watchdog.get("kill") or []

        tk.Label(self, text="Watchdog name:").pack(anchor="w", padx=8, pady=(8, 0))
        self.name_entry = tk.Entry(self)
        self.name_entry.insert(0, watchdog.get("name", ""))
        self.name_entry.pack(fill="x", padx=8)

        self.picker = ProcessPicker(self, initial=existing)
        self.picker.pack(fill="both", expand=True, padx=8, pady=(8, 0))

        note = ("This Watchdog fires once every selected process has no open window. "
                "Matching is by exact install location, so picking a process like "
                "\u201cchrome.exe\u201d bundled inside another app's folder won't "
                "accidentally also match your real browser, even though they share a name.")
        tk.Label(self, text=note, fg="#666", wraplength=440, justify="left").pack(
            anchor="w", padx=8, pady=(6, 0))

        btn_row = tk.Frame(self)
        btn_row.pack(fill="x", padx=8, pady=8, side="bottom")
        tk.Button(btn_row, text="Save", command=self._save).pack(side="right")
        tk.Button(btn_row, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 6))

        self.transient(master)
        self.grab_set()

    def _save(self):
        name = self.name_entry.get().strip()
        selected = self.picker.get_selected()
        if not name:
            messagebox.showerror(APP_NAME, "Give the Watchdog a name.")
            return
        if not selected:
            messagebox.showerror(APP_NAME, "Select at least one process.")
            return
        self.result = {
            "id": str(uuid.uuid4()),
            "name": name,
            "enabled": True,
            "trigger": selected,
            "kill": selected,
        }
        self.destroy()


# ---------------------------------------------------------------------------
# User guide (with a themed easter egg — see _tick below)
# ---------------------------------------------------------------------------

class UserGuideWindow(tk.Toplevel):
    """A short in-app guide. Themed easter egg: the title bar counts down
    and Watchdog 'eats' the guide window itself when it hits zero — same
    bite animation as Hide to Tray — because of course it does."""

    GUIDE_TEXT = (
        "Built by Black Anvil\n"
        "\n"
        "WHAT THIS APP DOES\n"
        "Process Watchdog was built to eat stupid background processes, "
        "freeing up resources. It watches apps you pick and eats its "
        "leftover background processes a few seconds after you close the "
        "app itself — no more hunting down zombie processes by hand. "
        "LET THE DOG EAT!!!\n"
        "\n"
        "ADDING A WATCHDOG\n"
        "Click Add Watchdog, give it a name, then select the process(es) "
        "you want it to eat from the list (Ctrl/Shift-click to pick several, "
        "or click a folder group to grab everything under it at once). "
        "Click Save.\n"
        "\n"
        "GRACE PERIOD\n"
        "After the app's window closes, Watchdog waits 10 seconds by "
        "default before eating anything. This can be adjusted to feed "
        "Watchdog as you like.\n"
        "\n"
        "EDIT / TOGGLE ENABLED / DELETE\n"
        "Select a Watchdog first, then use these buttons to change, pause, "
        "or remove it.\n"
        "\n"
        "HIDE TO TRAY\n"
        "Closes the window but keeps Watchdog running in the background. "
        "Right-click the tray icon to reopen it, turn on Start with "
        "Windows, or Quit for real and starve your Watchdog. Your Call!\n"
    )

    COUNTDOWN_SECONDS = 15

    def __init__(self, master):
        super().__init__(master)
        self.geometry("420x480")
        self.minsize(360, 400)
        apply_window_icon(self)

        text = tk.Text(self, wrap="word", padx=12, pady=10, borderwidth=0)
        text.insert("1.0", self.GUIDE_TEXT)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

        tk.Button(self, text="Close", command=self._close_now).pack(pady=8)

        self.protocol("WM_DELETE_WINDOW", self._close_now)
        self._remaining = self.COUNTDOWN_SECONDS
        self._tick()

    def _tick(self):
        if self._remaining <= 0:
            animate_eaten(self, on_done=self._safe_destroy)
            return
        self.title(f"Watchdog will eat this process in {self._remaining} seconds")
        self._remaining -= 1
        self.after(1000, self._tick)

    def _close_now(self):
        animate_eaten(self, on_done=self._safe_destroy)

    def _safe_destroy(self):
        try:
            self.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main config window
# ---------------------------------------------------------------------------

class ConfigWindow:
    def __init__(self, cfg, on_change, watcher=None):
        self.cfg = cfg
        self.on_change = on_change
        self.watcher = watcher
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("500x460")
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        apply_window_icon(self.root)
        self.root.withdraw()  # start hidden — only the tray icon opens it

        grace_row = tk.Frame(self.root)
        grace_row.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(grace_row, text="Grace period after an app closes, before its processes get killed:").pack(side="left")
        self.grace_var = tk.IntVar(value=int(self.cfg.get("grace_seconds", 10)))
        grace_spin = tk.Spinbox(grace_row, from_=1, to=120, width=4, textvariable=self.grace_var,
                                 command=self._save_grace)
        grace_spin.pack(side="left", padx=(6, 2))
        tk.Label(grace_row, text="sec").pack(side="left")
        grace_spin.bind("<FocusOut>", lambda e: self._save_grace())
        grace_spin.bind("<Return>", lambda e: self._save_grace())

        tk.Label(self.root, text="Watchdogs", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=10, pady=(10, 0))

        self.tree = ttk.Treeview(self.root, columns=("name", "enabled", "status"), show="headings", height=10)
        self.tree.heading("name", text="Watchdog")
        self.tree.heading("enabled", text="Enabled")
        self.tree.heading("status", text="Status")
        self.tree.column("name", width=180, anchor="w")
        self.tree.column("enabled", width=70, anchor="center")
        self.tree.column("status", width=220, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)

        if self.watcher:
            self._tick_status()

        btn_row = tk.Frame(self.root)
        btn_row.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btn_row, text="Add Watchdog", command=self.add_watchdog).pack(side="left")
        tk.Button(btn_row, text="Edit", command=self.edit_watchdog).pack(side="left", padx=6)
        tk.Button(btn_row, text="Toggle Enabled", command=self.toggle_watchdog).pack(side="left")
        tk.Button(btn_row, text="Delete", command=self.delete_watchdog).pack(side="left", padx=6)
        tk.Button(btn_row, text="Hide to Tray", command=self.hide).pack(side="right")
        tk.Button(btn_row, text="User Guide", command=self.open_guide).pack(side="right", padx=(0, 6))

        self.refresh_tree()

    def _save_grace(self):
        try:
            val = int(self.grace_var.get())
        except (tk.TclError, ValueError):
            return
        val = max(1, min(120, val))
        self.cfg["grace_seconds"] = val
        save_config(self.cfg)
        self.on_change(self.cfg)

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for watchdog in self.cfg["watchdogs"]:
            self.tree.insert("", tk.END, iid=watchdog["id"],
                              values=(watchdog.get("name", ""),
                                      "Yes" if watchdog.get("enabled", True) else "No",
                                      "Watching" if watchdog.get("enabled", True) else "Disabled"))

    def _tick_status(self):
        """Runs every second: updates the Status column with a live countdown
        for any watchdog whose trigger just closed, OR — if the watchdog hasn't
        closed — exactly which process(es) are still keeping it open. That
        second part matters: a watchdog that looks 'stuck' should tell you why
        instead of just sitting there saying 'Watching' forever."""
        pending = self.watcher.get_pending() if self.watcher else {}
        opens = self.watcher.get_open() if self.watcher else {}
        for watchdog in self.cfg["watchdogs"]:
            rid = watchdog["id"]
            if not self.tree.exists(rid):
                continue
            if not watchdog.get("enabled", True):
                status = "Disabled"
            elif rid in pending:
                status = f"Killing in {int(pending[rid]) + 1}s"
            else:
                open_names = opens.get(rid, [])
                if open_names:
                    shown = ", ".join(open_names[:2])
                    extra = "" if len(open_names) <= 2 else f" +{len(open_names) - 2}"
                    status = f"Open: {shown}{extra}"
                else:
                    status = "Watching"
            vals = list(self.tree.item(rid, "values"))
            if len(vals) == 3 and vals[2] != status:
                vals[2] = status
                self.tree.item(rid, values=vals)
        self.root.after(500, self._tick_status)

    def _selected_watchdog(self):
        sel = self.tree.selection()
        if not sel:
            return None
        rid = sel[0]
        for watchdog in self.cfg["watchdogs"]:
            if watchdog["id"] == rid:
                return watchdog
        return None

    def add_watchdog(self):
        dlg = watchdogDialog(self.root)
        self.root.wait_window(dlg)
        if dlg.result:
            self.cfg["watchdogs"].append(dlg.result)
            save_config(self.cfg)
            self.on_change(self.cfg)
            self.refresh_tree()

    def edit_watchdog(self):
        watchdog = self._selected_watchdog()
        if not watchdog:
            messagebox.showinfo(APP_NAME, "Select a watchdog first.")
            return
        dlg = watchdogDialog(self.root, watchdog=watchdog)
        self.root.wait_window(dlg)
        if dlg.result:
            dlg.result["id"] = watchdog["id"]
            dlg.result["enabled"] = watchdog.get("enabled", True)
            self.cfg["watchdogs"] = [dlg.result if r["id"] == watchdog["id"] else r for r in self.cfg["watchdogs"]]
            save_config(self.cfg)
            self.on_change(self.cfg)
            self.refresh_tree()

    def toggle_watchdog(self):
        watchdog = self._selected_watchdog()
        if not watchdog:
            return
        watchdog["enabled"] = not watchdog.get("enabled", True)
        save_config(self.cfg)
        self.on_change(self.cfg)
        self.refresh_tree()

    def delete_watchdog(self):
        watchdog = self._selected_watchdog()
        if not watchdog:
            return
        if messagebox.askyesno(APP_NAME, f"Delete Watchdog '{watchdog['name']}'?"):
            self.cfg["watchdogs"] = [r for r in self.cfg["watchdogs"] if r["id"] != watchdog["id"]]
            save_config(self.cfg)
            self.on_change(self.cfg)
            self.refresh_tree()

    def show(self):
        self.root.deiconify()
        self.root.lift()

    def hide(self):
        animate_eaten(self.root, on_done=self.root.withdraw)

    def open_guide(self):
        UserGuideWindow(self.root)

    def mainloop(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Tray icon
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


def make_icon_image():
    """Tray icon. Uses the real logo (icon_tray.png, bundled alongside the
    exe) when available; falls back to a simple drawn shield if it's
    missing for any reason (e.g. running from source without the asset)."""
    try:
        return Image.open(resource_path("icon_tray.png")).convert("RGBA")
    except Exception:
        pass
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Shield outline — "guarding" motif
    shield = [(32, 3), (58, 14), (58, 33), (32, 61), (6, 33), (6, 14)]
    d.polygon(shield, fill=(32, 36, 46, 255), outline=(90, 150, 255, 255), width=3)
    # Eye — "watching" motif
    d.ellipse((16, 23, 48, 39), fill=(235, 240, 250, 255))
    d.ellipse((27, 26, 37, 36), fill=(32, 36, 46, 255))
    return img


def log_crash(text):
    """--windowed builds have no console, so an unhandled exception on
    launch is otherwise completely silent — exactly the 'nothing happens'
    symptom. Write it somewhere findable instead."""
    try:
        log_path = os.path.join(os.path.dirname(CONFIG_PATH), "crash.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{text}\n")
    except Exception:
        pass


def is_startup_registered():
    """Checks the HKCU Run key directly rather than trusting a saved flag,
    so the tray checkbox always reflects reality even if the registry was
    edited/cleared outside the app (e.g. by antivirus)."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        try:
            current, _ = winreg.QueryValueEx(key, APP_NAME)
        except FileNotFoundError:
            current = None
        winreg.CloseKey(key)
        return current == sys.executable
    except Exception:
        return False


def set_startup_registered(enabled):
    """User-triggered only (tray menu toggle) — NOT called automatically
    on launch. An unsigned exe silently writing itself into the Windows
    startup registry the moment it first runs is a classic antivirus
    false-positive trigger; making this opt-in avoids that entirely."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, sys.executable)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception:
        pass


def main():
    is_first_run = not os.path.exists(CONFIG_PATH)
    cfg = load_config()

    def on_kill(watchdog_name, count):
        print(f"[watchdog] {watchdog_name}: killed {count} process(es)")

    watcher = Watcher(get_config=lambda: config_window.cfg, on_kill=on_kill)
    config_window = ConfigWindow(cfg, on_change=lambda c: None, watcher=watcher)
    watcher.start()

    tray_ok = False
    if pystray:
        try:
            def open_config(icon=None, item=None):
                config_window.root.after(0, config_window.show)

            def quit_app(icon=None, item=None):
                watcher.stop()
                icon.stop()
                config_window.root.after(0, config_window.root.destroy)

            def toggle_startup(icon=None, item=None):
                set_startup_registered(not is_startup_registered())

            menu = pystray.Menu(
                pystray.MenuItem("Open Watchdog", open_config, default=True),
                pystray.MenuItem("Start with Windows", toggle_startup,
                                  checked=lambda item: is_startup_registered()),
                pystray.MenuItem("Quit", quit_app),
            )
            icon = pystray.Icon(APP_NAME, make_icon_image(), APP_NAME, menu)
            threading.Thread(target=icon.run, daemon=True).start()
            tray_ok = True
        except Exception:
            log_crash(traceback.format_exc())

    if is_first_run or not tray_ok:
        # First launch ever (no config yet) — show the window so there's
        # actually something to set up watchdogs with, instead of silently
        # dropping into the tray with nothing configured. Every launch
        # after that stays hidden as usual. Also shown as a fallback if
        # the tray icon itself failed to start (see above).
        config_window.show()

    config_window.mainloop()
    watcher.stop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_crash(traceback.format_exc())
        raise
