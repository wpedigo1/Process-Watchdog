# -*- coding: utf-8 -*-
"""Mission 7 regression tests: geometric/visual assertions, not "doesn't raise".

Each test renders real widgets and queries actual positions/sizes/colors â€”
the standard that would have caught the five Mission 7 defects before they
reached the repository owner.
"""

import os
import unittest
from unittest.mock import patch

import watchdog_core
import watchdog_ui


def all_descendants(widget):
    out = []
    stack = [widget]
    while stack:
        w = stack.pop()
        for child in w.winfo_children():
            out.append(child)
            stack.append(child)
    return out


class DialogButtonsReachableTests(unittest.TestCase):
    """Defect A: Save/Cancel must be inside the dialog's visible bounds at
    BOTH the default size and a deliberately tiny size."""

    def _assert_save_cancel_inside(self, dlg):
        dlg.update_idletasks()
        dlg.update()
        top = dlg.winfo_rooty()
        bottom = top + dlg.winfo_height()
        left = dlg.winfo_rootx()
        right = left + dlg.winfo_width()
        found = {}
        for btn in all_descendants(dlg):
            if btn.winfo_class() == "TButton" or btn.__class__.__name__ == "Button":
                if btn.cget("text") in ("Save", "Cancel"):
                    found[btn.cget("text")] = btn
        self.assertEqual(set(found), {"Save", "Cancel"})
        for name, btn in found.items():
            btn_top = btn.winfo_rooty()
            btn_bottom = btn_top + btn.winfo_height()
            btn_left = btn.winfo_rootx()
            btn_right = btn_left + btn.winfo_width()
            self.assertGreaterEqual(btn_top, top, f"{name} above dialog top")
            self.assertLessEqual(btn_bottom, bottom, f"{name} clipped below dialog bottom")
            self.assertGreaterEqual(btn_left, left, f"{name} left of dialog")
            self.assertLessEqual(btn_right, right, f"{name} clipped right")

    def test_save_cancel_inside_at_default_size(self):
        root = watchdog_ui.tk.Tk()
        root.withdraw()
        try:
            dlg = watchdog_ui.watchdogDialog(root, watchdog=None)
            self._assert_save_cancel_inside(dlg)
            dlg.destroy()
        finally:
            root.destroy()

    def test_save_cancel_inside_at_tiny_size(self):
        root = watchdog_ui.tk.Tk()
        root.withdraw()
        try:
            dlg = watchdog_ui.watchdogDialog(root, watchdog=None)
            dlg.geometry("460x500")
            self._assert_save_cancel_inside(dlg)
            dlg.destroy()
        finally:
            root.destroy()

    def test_dialog_minsize_is_generous_floor(self):
        root = watchdog_ui.tk.Tk()
        root.withdraw()
        try:
            dlg = watchdog_ui.watchdogDialog(root, watchdog=None)
            self.assertEqual(tuple(dlg.minsize()), (480, 500))
            dlg.destroy()
        finally:
            root.destroy()


class MainWindowButtonsVisibleTests(unittest.TestCase):
    """Defect B: every button fully inside the main window at default size."""

    def test_all_buttons_inside_window_bounds(self):
        cfg = {"poll_interval": 2.0, "grace_seconds": 10.0, "watchdogs": []}
        watcher = watchdog_core.Watcher(get_config=lambda: cfg)
        win = watchdog_ui.ConfigWindow(cfg, on_change=lambda c: None, watcher=watcher)
        try:
            win.show()
            win.root.update_idletasks()
            win.root.update()
            left = win.root.winfo_rootx()
            right = left + win.root.winfo_width()
            top = win.root.winfo_rooty()
            bottom = top + win.root.winfo_height()
            texts = []
            for w in all_descendants(win.root):
                if w.__class__.__name__ == "Button":
                    texts.append(w.cget("text"))
                    w_right = w.winfo_rootx() + w.winfo_width()
                    w_bottom = w.winfo_rooty() + w.winfo_height()
                    self.assertLessEqual(w_right, right,
                                         f"button {w.cget('text')!r} clipped right")
                    self.assertLessEqual(w_bottom, bottom,
                                         f"button {w.cget('text')!r} clipped below")
            for expected in ("Add Watchdog", "Retrain", "Rehome Dog",
                             "Hide Dogs in the Doghouse", "Trainer's Guide"):
                self.assertIn(expected, texts)
        finally:
            win.root.destroy()


class NeedsSetupStatusTests(unittest.TestCase):
    """Defect C: watched_app None shows an explicit, actionable status that
    takes precedence over disabled/pending/open."""

    RID = "needs-setup-dog"
    MSG = "Needs setup \u2014 pick a Watch app in Retrain."

    class _FakeWatcher:
        def __init__(self, pending=None, open_names=None):
            self._pending = pending or {}
            self._open = open_names or {}

        def get_pending(self):
            return dict(self._pending)

        def get_open(self):
            return dict(self._open)

    def _status_for(self, watched_app, enabled=True, pending=None, open_names=None):
        cfg = {"poll_interval": 2.0, "grace_seconds": 10.0, "watchdogs": [
            {"id": self.RID, "name": "NS Dog", "enabled": enabled,
             "watched_app": watched_app, "meal_targets": []},
        ]}
        win = watchdog_ui.ConfigWindow(
            cfg, on_change=lambda c: None,
            watcher=self._FakeWatcher(pending, open_names))
        try:
            win.show()
            win.root.update_idletasks()
            win._tick_status()
            win.root.update()
            return list(win.tree.item(self.RID, "values"))[2]
        finally:
            win.root.destroy()

    def test_none_watched_app_shows_needs_setup(self):
        self.assertEqual(self._status_for(None), self.MSG)

    def test_none_watched_app_takes_precedence_over_disabled(self):
        self.assertEqual(self._status_for(None, enabled=False), self.MSG)

    def test_none_watched_app_takes_precedence_over_pending(self):
        self.assertEqual(
            self._status_for(None, pending={self.RID: 3.0}), self.MSG)

    def test_none_watched_app_takes_precedence_over_open(self):
        self.assertEqual(
            self._status_for(None, open_names={self.RID: ["app.exe"]}), self.MSG)

    def test_other_statuses_unchanged(self):
        app = {"name": "app.exe", "exe": ""}
        self.assertEqual(self._status_for(app, enabled=False), "Off watch.")
        self.assertEqual(
            self._status_for(app, pending={self.RID: 3.0}),
            "Hungry \u2014 eating in 4s.")
        self.assertEqual(self._status_for(app), "Waiting for app to open.")


class SpinboxThemeTests(unittest.TestCase):
    """Defect D: Spinbox gets explicit fg/entry colors in both palettes."""

    def _spinbox_vs_entry(self, palette):
        root = watchdog_ui.tk.Tk()
        root.withdraw()
        try:
            frame = watchdog_ui.tk.Frame(root)
            spin = watchdog_ui.tk.Spinbox(frame, from_=1, to=10)
            entry = watchdog_ui.tk.Entry(frame)
            spin.pack()
            entry.pack()
            frame.pack()
            watchdog_ui.apply_theme(frame, dict(palette, accent="#0078D7"))
            frame.update_idletasks()
            return {"spin_fg": spin.cget("fg"), "spin_bg": spin.cget("bg"),
                    "entry_fg": entry.cget("fg"), "entry_bg": entry.cget("bg")}
        finally:
            root.destroy()

    def test_dark_theme_spinbox_fg_is_white(self):
        got = self._spinbox_vs_entry(watchdog_ui._PALETTES["dark"])
        self.assertEqual(got["spin_fg"], watchdog_ui._PALETTES["dark"]["fg"])

    def test_light_theme_spinbox_fg_is_black(self):
        got = self._spinbox_vs_entry(watchdog_ui._PALETTES["light"])
        self.assertEqual(got["spin_fg"], watchdog_ui._PALETTES["light"]["fg"])

    def test_spinbox_mirrors_entry_exactly(self):
        # Spec: mirror the existing Entry branch. Both end up with the same
        # fg AND the same (recursion-overridden) background.
        for pal in (watchdog_ui._PALETTES["dark"], watchdog_ui._PALETTES["light"]):
            got = self._spinbox_vs_entry(pal)
            self.assertEqual(got["spin_fg"], got["entry_fg"])
            self.assertEqual(got["spin_bg"], got["entry_bg"])


class SpinboxButtonBackgroundTests(unittest.TestCase):
    """Mission 8 defect G: the arrow area has its own Tk option,
    buttonbackground, which Mission 7's fix did not set."""

    def _spinbox_opts(self, palette):
        root = watchdog_ui.tk.Tk()
        root.withdraw()
        try:
            frame = watchdog_ui.tk.Frame(root)
            spin = watchdog_ui.tk.Spinbox(frame, from_=1, to=10)
            spin.pack()
            frame.pack()
            watchdog_ui.apply_theme(frame, dict(palette, accent="#0078D7"))
            frame.update_idletasks()
            return {"buttonbackground": spin.cget("buttonbackground"),
                    "bg": spin.cget("bg"), "fg": spin.cget("fg")}
        finally:
            root.destroy()

    def test_buttonbackground_set_for_both_palettes(self):
        for name in ("dark", "light"):
            pal = watchdog_ui._PALETTES[name]
            got = self._spinbox_opts(pal)
            self.assertEqual(got["buttonbackground"], pal["entry_bg"], name)


class TextThemeTests(unittest.TestCase):
    """Mission 8 defect F: tk.Text (Trainer's Guide body) was never in the
    apply_theme dispatch, leaving black text on a darkened background."""

    def _text_opts(self, palette):
        root = watchdog_ui.tk.Tk()
        root.withdraw()
        try:
            frame = watchdog_ui.tk.Frame(root)
            txt = watchdog_ui.tk.Text(frame)
            txt.pack()
            frame.pack()
            watchdog_ui.apply_theme(frame, dict(palette, accent="#0078D7"))
            frame.update_idletasks()
            return {"fg": txt.cget("fg"), "bg": txt.cget("bg"),
                    "insertbackground": txt.cget("insertbackground")}
        finally:
            root.destroy()

    def test_dark_theme_text_fg_is_white(self):
        got = self._text_opts(watchdog_ui._PALETTES["dark"])
        self.assertEqual(got["fg"], watchdog_ui._PALETTES["dark"]["fg"])

    def test_light_theme_text_fg_is_black(self):
        got = self._text_opts(watchdog_ui._PALETTES["light"])
        self.assertEqual(got["fg"], watchdog_ui._PALETTES["light"]["fg"])

    def test_insertbackground_matches_fg(self):
        for name in ("dark", "light"):
            pal = watchdog_ui._PALETTES[name]
            got = self._text_opts(pal)
            self.assertEqual(got["insertbackground"], pal["fg"], name)


class ButtonRowSeparatorTests(unittest.TestCase):
    """Mission 8 defect H: the two button rows must read as two intentional
    sections — a separator frame exists between them and is visibly distinct
    from the window background after theming."""

    def test_separator_present_and_distinct(self):
        cfg = {"poll_interval": 2.0, "grace_seconds": 10.0, "watchdogs": []}
        watcher = watchdog_core.Watcher(get_config=lambda: cfg)
        win = watchdog_ui.ConfigWindow(cfg, on_change=lambda c: None, watcher=watcher)
        try:
            win.show()
            win.root.update_idletasks()
            win.root.update()
            sep = win._row_separator
            self.assertEqual(int(sep.cget("height")), 1)
            palette = win._palette
            self.assertNotEqual(sep.cget("bg").lower(), palette["bg"].lower())
            self.assertEqual(sep.cget("bg").upper(),
                             watchdog_ui._blend(palette["bg"], palette["fg"], 0.25).upper())
            # geometric: the separator sits BETWEEN the two button rows
            ys = {}
            for w in all_descendants(win.root):
                if w.__class__.__name__ == "Button" and w.winfo_toplevel() is win.root:
                    ys.setdefault(w.cget("text"), w.winfo_rooty())
            sep_y = sep.winfo_rooty()
            self.assertLess(ys["Rehome Dog"], sep_y, "separator must be below management row")
            self.assertLess(sep_y, ys["Trainer's Guide"], "separator must be above window row")
        finally:
            win.root.destroy()

    def test_blend_helper(self):
        self.assertEqual(watchdog_ui._blend("#202020", "#202020", 0.5), "#202020")
        self.assertEqual(watchdog_ui._blend("#000000", "#FFFFFF", 0.5), "#808080")
        self.assertEqual(watchdog_ui._blend("#000000", "#FFFFFF", 0.0), "#000000")
        self.assertEqual(watchdog_ui._blend("#000000", "#FFFFFF", 1.0), "#FFFFFF")


class GroupLabelTests(unittest.TestCase):
    """Defect E: multi-exe group label is the SHORTEST exe name in the group,
    not the (often opaque MSIX hash) install-directory basename."""

    class _FakeProc:
        def __init__(self, pid, name, exe, username="wpedi"):
            self.pid = pid
            self.info = {"pid": pid, "name": name, "exe": exe, "username": username}

        def name(self):
            return self.info["name"]

        def exe(self):
            return self.info["exe"]

    def test_msix_group_label_is_shortest_exe(self):
        d = r"C:\Program Files\WindowsApps\b993306303521e97e_1.0.0.0_x64__0ac2c3f4a5b6c"
        procs = [
            self._FakeProc(100, "chatgpt-native-host.exe", d + r"\chatgpt-native-host.exe"),
            self._FakeProc(101, "ChatGPT.exe", d + r"\ChatGPT.exe"),
        ]
        with patch.object(watchdog_core.psutil, "process_iter", return_value=procs):
            groups = watchdog_core.get_process_groups(hide_system=True)
        labels = [label for label, entries in groups]
        self.assertIn("ChatGPT.exe", labels)
        self.assertNotIn("b993306303521e97e_1.0.0.0_x64__0ac2c3f4a5b6c", labels)

    def test_traditional_group_label_is_shortest_exe(self):
        d = r"C:\Program Files\Microsoft Visual Studio"
        procs = [
            self._FakeProc(200, "PerfWatson2.exe", d + r"\PerfWatson2.exe"),
            self._FakeProc(201, "devenv.exe", d + r"\devenv.exe"),
        ]
        with patch.object(watchdog_core.psutil, "process_iter", return_value=procs):
            groups = watchdog_core.get_process_groups(hide_system=True)
        labels = [label for label, entries in groups]
        self.assertIn("devenv.exe", labels)
        self.assertNotIn("Microsoft Visual Studio", labels)

    def test_tie_broken_alphabetically(self):
        d = r"C:\Apps\Whatever"
        procs = [
            self._FakeProc(300, "bbb.exe", d + r"\bbb.exe"),
            self._FakeProc(301, "aaa.exe", d + r"\aaa.exe"),
        ]
        with patch.object(watchdog_core.psutil, "process_iter", return_value=procs):
            groups = watchdog_core.get_process_groups(hide_system=True)
        self.assertEqual([label for label, _ in groups], ["aaa.exe"])


if __name__ == "__main__":
    unittest.main()
