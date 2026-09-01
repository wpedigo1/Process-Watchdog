"""
Process Watchdog - UI module.

Holds the windows, dialogs, picker control, user guide, and the themed
window animation. This is a pure structural extraction from watchdog_app.py;
no behavior was changed. Core logic lives in watchdog_core.py and the entry
point / tray wiring lives in watchdog_app.py.
"""

import os
import random
import uuid
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from PIL import Image, ImageTk

from watchdog_core import (
    APP_NAME,
    _user32,
    _gdi32,
    apply_window_icon,
    detect_windows_theme,
    get_accent_color,
    get_process_groups,
    is_protected_entry,
    resource_path,
    save_config,
)


# ---------------------------------------------------------------------------
# Theme palettes + application
# ---------------------------------------------------------------------------

_PALETTES = {
    "light": {"bg": "#F3F3F3", "fg": "#000000", "entry_bg": "#FFFFFF"},
    "dark": {"bg": "#202020", "fg": "#FFFFFF", "entry_bg": "#2D2D30"},
}


def _blend(hex_color_a, hex_color_b, t):
    """Mix two #RRGGBB colors; t=0 returns a, t=1 returns b. Used for subtle
    separators that must stay visible in both palettes without a new palette
    entry or dependency."""
    a = tuple(int(hex_color_a[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(hex_color_b[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02X%02X%02X" % tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _build_palette():
    pal = dict(_PALETTES[detect_windows_theme()])
    pal["accent"] = get_accent_color()
    return pal


def apply_theme(widget, palette):
    """Recursively theme a widget tree using a plain-tk color pass. Plain tk
    widgets are recolored by type via config(bg/fg); ttk.Treeview is themed
    through ttk.Style (selection background = accent). Unknown widget types are
    left untouched. Safe to call at any time — just recolors in place."""
    try:
        widget.config(bg=palette["bg"])
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        cls = child.__class__.__name__
        if cls == "Button":
            child.config(bg=palette["bg"], fg=palette["fg"], activebackground=palette["accent"])
        elif cls == "Label":
            child.config(bg=palette["bg"], fg=palette["fg"])
        elif cls == "Frame":
            child.config(bg=palette["bg"])
        elif cls == "Toplevel":
            child.config(bg=palette["bg"])
        elif cls == "Entry":
            child.config(bg=palette["entry_bg"], fg=palette["fg"], insertbackground=palette["fg"])
        elif cls == "Spinbox":
            child.config(bg=palette["entry_bg"], fg=palette["fg"],
                         insertbackground=palette["fg"],
                         buttonbackground=palette["entry_bg"])
        elif cls == "Text":
            child.config(bg=palette["entry_bg"], fg=palette["fg"], insertbackground=palette["fg"])
        elif isinstance(child, ttk.Treeview):
            style = ttk.Style()
            style.theme_use("clam")
            style.configure("Treeview", background=palette["entry_bg"],
                            foreground=palette["fg"],
                            fieldbackground=palette["entry_bg"])
            style.map("Treeview",
                      background=[("selected", palette["accent"])],
                      foreground=[("selected", "#FFFFFF")])
        apply_theme(child, palette)
    return widget


def load_logo_img(pixels):
    """Load icon.ico, resize to exact pixels, return an ImageTk.PhotoImage.
    Caller MUST keep a reference (e.g. as instance attribute) or Tkinter GCs it."""
    img = Image.open(resource_path("icon.ico")).resize((pixels, pixels), Image.LANCZOS)
    return ImageTk.PhotoImage(img)


def animate_eaten(win, on_done, bites=5, bite_delay_ms=160):
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
            bite_r = max(14, h // 3)
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

    def __init__(self, master, initial=None, selectmode="extended", hint=None,
                 locked=None, on_select=None):
        super().__init__(master)
        self._preselect = {(e.get("name", ""), e.get("exe", "") or "") for e in (initial or [])}
        self._leaf_ident = {}  # iid -> (name, exe)
        self._manual = set()   # manually added (name, exe) identities kept across refreshes
        self._locked = locked  # display-only (name, exe) shown disabled, never selectable
        self._on_select = on_select

        top = tk.Frame(self)
        top.pack(fill="x")
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
            text=hint or "Select any process(es) or whole groups — Ctrl/Shift-click to combine as many as you want:",
            fg="gray", wraplength=420, justify="left"
        ).pack(anchor="w", pady=(4, 0))

        tree_row = tk.Frame(self)
        tree_row.pack(fill="both", expand=True, pady=(4, 0))

        self.tree = ttk.Treeview(tree_row, show="tree", selectmode=selectmode)
        self.tree.tag_configure("locked", foreground="#888888")
        vsb = ttk.Scrollbar(tree_row, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        if self._on_select:
            self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        self.refresh()

    def set_locked(self, name, exe=""):
        """Show a disabled, always-present entry for the watched app. Used to
        keep the watched app visible in the Eat These Leftovers list while
        keeping it out of the leftover selection itself."""
        self._locked = (name, exe) if name else None
        self.refresh()

    def add_manual(self, name, exe=""):
        if not name:
            return
        self._manual.add((name, exe))
        if self.tree["selectmode"] == "browse":
            # Single-select picker: a manually added entry replaces the
            # current selection rather than append to it.
            self.tree.selection_remove(*self.tree.selection())
            self._preselect = {(name, exe)}
        else:
            self._preselect.add((name, exe))
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

        if self._locked:
            n, e = self._locked
            self.tree.insert("", tk.END, text=f"{n}  \u2014 watched app (always eaten)",
                             tags=("locked",))
            live_idents.add((n, e))

        query = self.filter_var.get().strip().lower()
        groups = get_process_groups(hide_system=True)

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
            {ident for ident in prev_selected | self._manual if ident[0] and ident not in live_idents},
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
# watchdog add / retrain dialog
# ---------------------------------------------------------------------------

class watchdogDialog(tk.Toplevel):
    """Train (add) or Retrain (edit) a watchdog. The user picks ONE app to
    watch — its window closing is what triggers cleanup — and any number of
    leftover processes to eat when the watched app closes. The watched app is
    always itself a kill target, shown locked at the top of the leftovers list.
    Stored as watched_app / meal_targets (see watchdog_core)."""

    def __init__(self, master, watchdog=None):
        super().__init__(master)
        self.result = None
        self.geometry("520x760")
        self.minsize(480, 500)
        apply_window_icon(self)
        watchdog = watchdog or {}

        # Save/Cancel are packed FIRST with side="bottom": the pack manager
        # reserves bottom-anchored space in packing order, so the button row
        # stays reachable no matter how tall the content above it grows.
        btn_row = tk.Frame(self)
        tk.Button(btn_row, text="Save", command=self._save).pack(side="right")
        tk.Button(btn_row, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 6))
        btn_row.pack(side="bottom", fill="x", padx=8, pady=8)

        # Everything between the header and the buttons lives in a
        # scrollable container (Canvas + Scrollbar + inner Frame) so the
        # dialog remains usable at any font, DPI scaling, or content height.
        mid = tk.Frame(self)
        canvas = tk.Canvas(mid, highlightthickness=0)
        vsb = ttk.Scrollbar(mid, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas)
        canvas.create_window((0, 0), window=body, anchor="nw", tags="body")
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure("body", width=e.width))
        canvas.bind("<MouseWheel>", lambda e: canvas.yview_scroll(-e.delta // 120, "units"))
        mid.pack(fill="both", expand=True)

        self._logo_img = load_logo_img(40)
        header = tk.Frame(body)
        header.pack(fill="x", padx=8, pady=(8, 0))
        tk.Label(header, image=self._logo_img).pack(side="left")
        tk.Label(
            header,
            text=("Retrain " + (watchdog.get("name", "")).strip())
            if watchdog.get("name") else "Train a Watchdog",
            font=("Segoe UI", 12, "bold"),
        ).pack(side="left", padx=(8, 0))

        existing_app = watchdog.get("watched_app")
        existing_meal = watchdog.get("meal_targets", [])
        existing_app_ident = (existing_app.get("name", ""), existing_app.get("exe", "") or "") if existing_app else None

        self.title(f"Retrain {watchdog.get('name', '')}".strip()
                   if watchdog.get("name") else "Train a Watchdog")

        tk.Label(body, text="Watchdog name:").pack(anchor="w", padx=8, pady=(8, 0))
        self.name_entry = tk.Entry(body)
        self.name_entry.insert(0, watchdog.get("name", ""))
        self.name_entry.pack(fill="x", padx=8)

        # --- Watch This App (single-select) ---
        tk.Label(body, text="Watch this app", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=8, pady=(8, 0))
        tk.Label(
            body,
            text="Pick the ONE app to watch. Its window closing is what triggers cleanup.",
            fg="gray", wraplength=460, justify="left"
        ).pack(anchor="w", padx=8)
        self.watch_picker = ProcessPicker(
            body, initial=[existing_app] if existing_app else None,
            selectmode="browse",
            hint="Pick one app from the list to watch. Its matching is by exact install location.",
            on_select=self._watch_changed,
        )
        self.watch_picker.pack(fill="x", padx=8, pady=(4, 0))

        watch_add_row = tk.Frame(body)
        watch_add_row.pack(fill="x", padx=8, pady=(4, 0))
        tk.Button(watch_add_row, text="Browse for .exe\u2026",
                  command=self._browse_watch_exe).pack(side="left")
        self.watch_manual_var = tk.StringVar()
        watch_manual_entry = tk.Entry(watch_add_row, textvariable=self.watch_manual_var)
        watch_manual_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        watch_manual_entry.bind("<Return>", lambda e: self._add_watch_manual())
        tk.Button(watch_add_row, text="Add filename",
                  command=self._add_watch_manual).pack(side="left", padx=(6, 0))

        # --- Eat These Leftovers (multi-select, locked watched app) ---
        tk.Label(body, text="Eat these leftovers", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=8, pady=(8, 0))
        tk.Label(
            body,
            text="Extra processes to force-kill when the watched app closes "
                 "(the watched app itself is always eaten, shown below as locked).",
            fg="gray", wraplength=460, justify="left"
        ).pack(anchor="w", padx=8)
        self.meal_picker = ProcessPicker(
            body, initial=existing_meal, locked=existing_app_ident,
            hint="Ctrl/Shift-click to combine as many leftovers as you want.",
        )
        self.meal_picker.pack(fill="x", padx=8, pady=(4, 0))

        add_row = tk.Frame(body)
        add_row.pack(fill="x", padx=8, pady=(4, 0))
        tk.Button(add_row, text="Browse for .exe\u2026", command=self._browse_exe).pack(side="left")
        self.manual_var = tk.StringVar()
        manual_entry = tk.Entry(add_row, textvariable=self.manual_var)
        manual_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
        manual_entry.bind("<Return>", lambda e: self._add_manual())
        tk.Button(add_row, text="Add filename", command=self._add_manual).pack(side="left", padx=(6, 0))

        note = ("The watched app is matched by exact install location, so picking an app "
                "like \u201cfoo.exe\u201d won't accidentally also match another app that "
                "shares its name. Leftovers added by filename only are matched by name.")
        tk.Label(body, text=note, fg="#666", wraplength=460, justify="left").pack(
            anchor="w", padx=8, pady=(6, 0))

        self.transient(master)
        self.grab_set()

        self._palette = _build_palette()
        apply_theme(self, self._palette)

    def _watch_changed(self):
        """Reflect the chosen watched app into the leftovers list as a locked,
        always-eaten entry."""
        app = self.watch_picker.get_selected()
        if app:
            self.meal_picker.set_locked(app[0]["name"], app[0]["exe"] or "")

    def _identity(self, entry):
        return ((entry.get("name") or "").lower(), (entry.get("exe") or "").lower())

    def _dedupe(self, entries, exclude=None):
        exclude_key = self._identity(exclude) if exclude else None
        seen = set()
        out = []
        for e in entries:
            key = self._identity(e)
            if key == exclude_key or key in seen:
                continue
            seen.add(key)
            out.append(e)
        return out

    def _guard_protected(self, name, exe):
        if is_protected_entry({"name": name, "exe": exe}):
            messagebox.showerror(
                APP_NAME,
                f"'{name}' is Process Watchdog itself or a protected system "
                "process. It cannot be added as a target.",
            )
            return True
        return False

    def _browse_exe(self):
        path = filedialog.askopenfilename(
            parent=self, title="Choose an executable to add to leftovers",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")],
        )
        if path and not self._guard_protected(os.path.basename(path), path):
            self.meal_picker.add_manual(os.path.basename(path), path)

    def _add_manual(self):
        name = self.manual_var.get().strip()
        if not name:
            return
        if not self._guard_protected(name, ""):
            self.meal_picker.add_manual(name, "")
        self.manual_var.set("")

    def _browse_watch_exe(self):
        path = filedialog.askopenfilename(
            parent=self, title="Choose an executable to watch",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")],
        )
        if path and not self._guard_protected(os.path.basename(path), path):
            self.watch_picker.add_manual(os.path.basename(path), path)
            self._watch_changed()

    def _add_watch_manual(self):
        name = self.watch_manual_var.get().strip()
        if not name:
            return
        if not self._guard_protected(name, ""):
            self.watch_picker.add_manual(name, "")
            self._watch_changed()
        self.watch_manual_var.set("")

    def _save(self):
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror(APP_NAME, "Give the Watchdog a name.")
            return
        watched = self.watch_picker.get_selected()
        if not watched:
            messagebox.showerror(APP_NAME, "Pick an app to watch first.")
            return
        watched_app = watched[0]
        meal = self._dedupe(self.meal_picker.get_selected(), exclude=watched_app)
        self.result = {
            "id": str(uuid.uuid4()),
            "name": name,
            "enabled": True,
            "watched_app": watched_app,
            "meal_targets": meal,
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
        "Process Watchdog is a hungry dog that eats leftover background "
        "processes for you. You pick one app it keeps its eye on, plus any "
        "helper processes that should go away when that app closes. LET THE "
        "DOG EAT!!!\n"
        "\n"
        "ONE WATCHED APP + THE MEAL LIST\n"
        "Every Watchdog watches exactly one app, which is always on its own "
        "meal list automatically — you cannot remove it. On top of that you "
        "can add unlimited 'leftover' meal targets: pick a running process "
        "from the list, browse to an offline .exe file, or just type a "
        "filename. Add as many as you like.\n"
        "\n"
        "GRACE PERIOD (GLOBAL)\n"
        "When the watched app's window closes, Watchdog waits a grace period "
        "before eating anything, and cancels if the app reopens in time. "
        "There is ONE grace-period setting for every Watchdog — default 10 "
        "seconds, adjustable — not a separate setting per dog.\n"
        "\n"
        "THE DOGHOUSE\n"
        "Closing the window (the X, or Hide Dogs in the Doghouse) keeps "
        "every Watchdog running in the background. Right-click the tray icon "
        "to reopen, or use the tray Quit to actually exit and starve your "
        "dogs. Only tray Quit truly stops them.\n"
        "\n"
        "CALL DOG OFF WATCH / PUT DOG ON WATCH\n"
        "This toggle turns a single Watchdog on or off. Off means it stops "
        "watching and never eats anything; on means it watches again. The "
        "button flips between the two.\n"
        "\n"
        "RETRAIN / REHOME\n"
        "Select a Watchdog first. Retrain lets you edit it (change the "
        "watched app or its meal list, fix an ambiguous one). Rehome Dog "
        "deletes it for good, after an on-screen confirmation. Each has its "
        "own confirm text, so this guide won't recite it.\n"
        "\n"
        "EXACT MATCH VS. NAME MATCH\n"
        "When the app's exact install location is known, Watchdog matches by "
        "that path — so two different apps that share a filename are never "
        "mixed up. When no path is known, name-only matching is the fallback, "
        "and the picker clearly labels those entries as such.\n"
        "\n"
        "PROTECTED PROCESSES\n"
        "Watchdog will never target itself, core Windows system processes, or "
        "anything owned by SYSTEM or a service account — no matter what you "
        "select. The safe ones stay safe.\n"
    )

    COUNTDOWN_SECONDS = 30

    def __init__(self, master):
        super().__init__(master)
        self.geometry("420x480")
        self.minsize(360, 400)
        apply_window_icon(self)

        self._logo_img = load_logo_img(32)
        header = tk.Frame(self)
        header.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(header, image=self._logo_img).pack(side="left")
        tk.Label(header, text="Trainer's Guide", font=("Segoe UI", 12, "bold")).pack(
            side="left", padx=(8, 0))

        text = tk.Text(self, wrap="word", padx=12, pady=10, borderwidth=0)
        text.insert("1.0", self.GUIDE_TEXT)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)

        tk.Button(self, text="Close", command=self._close_now).pack(pady=8)

        self.protocol("WM_DELETE_WINDOW", self._close_now)
        self._remaining = self.COUNTDOWN_SECONDS
        self._palette = _build_palette()
        apply_theme(self, self._palette)
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

class RehomeDialog(tk.Toplevel):
    """Confirmation dialog for deleting a watchdog. Safe default: Keep Dog."""

    def __init__(self, master, name):
        super().__init__(master)
        self.result = False
        self.title("Rehome Dog")
        self.geometry("360x180")
        self.resizable(False, False)
        apply_window_icon(self)

        tk.Label(self, text=f'Rehome "{name}"?', font=("Segoe UI", 10, "bold"),
                 wraplength=330, justify="left").pack(anchor="w", padx=12, pady=(12, 4))
        tk.Label(self,
                 text="This removes the Watchdog and its meal list.\n"
                      "The dog cannot come back unless you train it again.",
                 wraplength=330, justify="left").pack(anchor="w", padx=12)

        btn_row = tk.Frame(self)
        btn_row.pack(fill="x", padx=12, pady=12, side="bottom")
        tk.Button(btn_row, text="Rehome Dog", command=self._confirm).pack(side="right")
        tk.Button(btn_row, text="Keep Dog", command=self._cancel).pack(side="right", padx=(0, 6))

        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._palette = _build_palette()
        apply_theme(self, self._palette)

    def _confirm(self):
        self.result = True
        self.destroy()

    def _cancel(self):
        self.result = False
        self.destroy()


class ConfigWindow:
    def __init__(self, cfg, on_change, watcher=None):
        self.cfg = cfg
        self.on_change = on_change
        self.watcher = watcher
        self._last_result = {}  # watchdog_id -> {"name": str, "killed": [..], "failed": [..]}
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("640x480")
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        apply_window_icon(self.root)
        self.root.withdraw()  # start hidden — only the tray icon opens it

        self._logo_img = load_logo_img(48)
        header = tk.Frame(self.root)
        header.pack(fill="x", padx=10, pady=(10, 0))
        tk.Label(header, image=self._logo_img).pack(side="left")
        tk.Label(header, text=APP_NAME, font=("Segoe UI", 14, "bold")).pack(side="left", padx=(8, 0))

        self._pack_status = tk.StringVar()
        tk.Label(self.root, textvariable=self._pack_status, font=("Segoe UI", 9)).pack(
            anchor="w", padx=12, pady=(4, 0))

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
        self.tree.heading("name", text="Watchdogs")
        self.tree.heading("enabled", text="Watching")
        self.tree.heading("status", text="Dog Status")
        self.tree.column("name", width=180, anchor="w")
        self.tree.column("enabled", width=70, anchor="center")
        self.tree.column("status", width=220, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=6)

        # Two button rows: per-watchdog management actions, then whole-window
        # actions. Six multi-word buttons cannot fit one 640px line — the
        # split is what guarantees every button stays visible.
        btn_row = tk.Frame(self.root)
        btn_row.pack(fill="x", padx=10)
        tk.Button(btn_row, text="Add Watchdog", command=self.add_watchdog).pack(side="left")
        tk.Button(btn_row, text="Retrain", command=self.edit_watchdog).pack(side="left", padx=6)
        self.toggle_btn = tk.Button(btn_row, text="Put Dog on Watch", command=self.toggle_watchdog)
        self.toggle_btn.pack(side="left")

        if self.watcher:
            self._tick_status()

        tk.Button(btn_row, text="Rehome Dog", command=self.delete_watchdog).pack(side="left", padx=6)

        # Deliberate two-section look: a thin separator line between the
        # per-watchdog row and the whole-window row, colored to stay visible
        # in both palettes (recolored after apply_theme below, which would
        # otherwise repaint every Frame to the window background).
        self._row_separator = tk.Frame(self.root, height=1, bd=0, highlightthickness=0)
        self._row_separator.pack(fill="x", padx=10, pady=(3, 6))

        window_row = tk.Frame(self.root)
        window_row.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(window_row, text="Hide Dogs in the Doghouse", command=self.hide).pack(side="right")
        tk.Button(window_row, text="Trainer's Guide", command=self.open_guide).pack(side="right", padx=(0, 6))

        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_toggle_label())
        self.tree.bind("<Double-1>", lambda e: self._show_result_details())
        self._update_toggle_label()

        self.refresh_tree()

        self._palette = _build_palette()
        apply_theme(self.root, self._palette)
        # apply_theme repaints every Frame to the window bg; recolor the
        # separator AFTER it so the divider stays visible in both themes.
        self._row_separator.config(bg=_blend(self._palette["bg"], self._palette["fg"], 0.25))

    def show(self):
        self._palette = _build_palette()
        apply_theme(self.root, self._palette)
        self._row_separator.config(bg=_blend(self._palette["bg"], self._palette["fg"], 0.25))
        self.root.deiconify()
        self.root.lift()
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
                                      "Watching" if watchdog.get("enabled", True) else "Off watch."))
        self._update_pack_status()
        self._update_toggle_label()

    def _update_pack_status(self):
        watchdogs = self.cfg["watchdogs"]
        total = len(watchdogs)
        enabled = sum(1 for w in watchdogs if w.get("enabled", True))
        self._pack_status.set(f"{enabled} of {total} watchdogs on watch")

    def _tick_status(self):
        """Runs every second: updates the Status column with a live state for
        each watchdog. Precedence: disabled, then a pending kill countdown,
        then currently-open (blocking), then a stored post-feed result, then
        the pre-feeding default. A fresh open event retires the stored result
        (the result stays visible until the watched app is observed open)."""
        pending = self.watcher.get_pending() if self.watcher else {}
        opens = self.watcher.get_open() if self.watcher else {}
        for watchdog in self.cfg["watchdogs"]:
            rid = watchdog["id"]
            if not self.tree.exists(rid):
                continue
            if watchdog.get("watched_app") is None:
                # Deliberately first, ahead of disabled/pending/open: a dog
                # that can never watch anything must not be mistaken for a
                # correctly-configured, currently-idle one.
                status = "Needs setup — pick a Watch app in Retrain."
            elif not watchdog.get("enabled", True):
                status = "Off watch."
            elif rid in pending:
                status = f"Hungry \u2014 eating in {int(pending[rid]) + 1}s."
            else:
                open_names = opens.get(rid, [])
                if open_names:
                    self._last_result.pop(rid, None)
                    shown = ", ".join(open_names[:2])
                    extra = "" if len(open_names) <= 2 else f" +{len(open_names) - 2}"
                    status = f"Waiting to eat: {shown}{extra}."
                elif rid in self._last_result:
                    status = self._render_result(self._last_result[rid])
                else:
                    status = "Waiting for app to open."
            vals = list(self.tree.item(rid, "values"))
            if len(vals) == 3 and vals[2] != status:
                vals[2] = status
                self.tree.item(rid, values=vals)
        self._update_toggle_label()
        self.root.after(500, self._tick_status)

    @staticmethod
    def _truncate_names(names):
        shown = ", ".join(names[:2])
        extra = "" if len(names) <= 2 else f" +{len(names) - 2}"
        return f"{shown}{extra}"

    @classmethod
    def _render_result(cls, result):
        """Render a stored feed result into a Dog Status string. result is a
        dict with keys name/killed/failed."""
        killed = result.get("killed", [])
        failed = result.get("failed", [])
        name = result.get("name", "watchdog")
        if killed and not failed:
            return f"Eaten by {name}: {cls._truncate_names(killed)}."
        if not killed and failed:
            return f"Couldn't eat: {cls._truncate_names(failed)} (access denied)."
        if killed and failed:
            return (f"Eaten by {name}: {cls._truncate_names(killed)}. "
                    f"Couldn't eat: {cls._truncate_names(failed)} (access denied).")
        return "Nothing left to eat."

    def record_kill_result(self, rid, watchdog_name, killed, failed):
        """Store the latest feeding outcome for a watchdog (called from the
        Tkinter thread via root.after marshal from main). In-memory only."""
        self._last_result[rid] = {
            "name": watchdog_name,
            "killed": list(killed),
            "failed": list(failed),
        }

    def _show_result_details(self):
        watchdog = self._selected_watchdog()
        if not watchdog:
            return
        rid = watchdog["id"]
        result = self._last_result.get(rid)
        if not result:
            return
        killed = result.get("killed", [])
        failed = result.get("failed", [])
        lines = []
        if killed:
            lines.append(f"Eaten by {result.get('name', 'watchdog')}:")
            lines.extend(f"  {n}" for n in killed)
        if failed:
            lines.append(f"Couldn't eat (access denied):")
            lines.extend(f"  {n}" for n in failed)
        if not lines:
            lines.append("Nothing left to eat.")
        messagebox.showinfo(APP_NAME, "\n".join(lines))

    def _update_toggle_label(self):
        watchdog = self._selected_watchdog()
        if watchdog and watchdog.get("enabled", True):
            self.toggle_btn.config(text="Call Dog Off Watch")
        else:
            self.toggle_btn.config(text="Put Dog on Watch")

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
        dlg = RehomeDialog(self.root, watchdog["name"])
        self.root.wait_window(dlg)
        if dlg.result:
            self.cfg["watchdogs"] = [r for r in self.cfg["watchdogs"] if r["id"] != watchdog["id"]]
            save_config(self.cfg)
            self.on_change(self.cfg)
            self.refresh_tree()

    def hide(self):
        animate_eaten(self.root, on_done=self.root.withdraw)

    def open_guide(self):
        UserGuideWindow(self.root)

    def mainloop(self):
        self.root.mainloop()
