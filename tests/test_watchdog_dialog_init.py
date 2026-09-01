# -*- coding: utf-8 -*-
"""Real-Tk regression tests for dialog construction (Mission 6F) and the
Mission 9 single-picker watch-designation combobox."""

import tkinter as tk
import unittest
from unittest import mock

import watchdog_ui


class _MsgRecorder:
    def __init__(self):
        self.calls = []

    def showinfo(self, title, msg, **kw):
        self.calls.append(("info", title, msg))

    def showerror(self, title, msg, **kw):
        self.calls.append(("error", title, msg))

    def showwarning(self, title, msg, **kw):
        self.calls.append(("warn", title, msg))


class WatchdogDialogInitTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.groups_patch = mock.patch.object(watchdog_ui, "get_process_groups", return_value=[])
        self.groups_patch.start()

    def tearDown(self):
        self.groups_patch.stop()
        self.root.destroy()

    def test_add_dialog_constructs_without_watchdog(self):
        dialog = watchdog_ui.watchdogDialog(self.root, watchdog=None)
        self.assertEqual(dialog.title(), "Train a Watchdog")
        dialog.destroy()

    def test_retrain_dialog_constructs_with_named_watchdog(self):
        watchdog = {
            "name": "Regression Dog",
            "watched_app": {"name": "watched.exe", "exe": "C:\\Apps\\watched.exe"},
            "meal_targets": [{"name": "helper.exe", "exe": "C:\\Apps\\helper.exe"}],
        }
        dialog = watchdog_ui.watchdogDialog(self.root, watchdog=watchdog)
        self.assertEqual(dialog.title(), "Retrain Regression Dog")
        dialog.destroy()

    def test_retrain_prefills_selection_and_watch_designation(self):
        watchdog = {
            "name": "Regression Dog",
            "watched_app": {"name": "watched.exe", "exe": "C:\\Apps\\watched.exe"},
            "meal_targets": [{"name": "helper.exe", "exe": "C:\\Apps\\helper.exe"}],
        }
        dialog = watchdog_ui.watchdogDialog(self.root, watchdog=watchdog)
        try:
            names = [s["name"] for s in dialog.picker.get_selected()]
            self.assertEqual(sorted(names), ["helper.exe", "watched.exe"])
            self.assertEqual(dialog.watch_combo.get(), "watched.exe")
        finally:
            dialog.destroy()


class WatchDesignationTests(unittest.TestCase):
    """Mission 9: one multi-select picker; a read-only combobox designates
    which selected item's closing triggers cleanup."""

    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.groups_patch = mock.patch.object(watchdog_ui, "get_process_groups", return_value=[])
        self.groups_patch.start()
        self.msg = _MsgRecorder()
        self.msg_patch = mock.patch.object(watchdog_ui, "messagebox", self.msg)
        self.msg_patch.start()
        self.dialog = watchdog_ui.watchdogDialog(self.root, watchdog=None)
        self.dialog.name_entry.insert(0, "Combo Dog")

    def tearDown(self):
        self.msg_patch.stop()
        self.groups_patch.stop()
        if self.dialog.winfo_exists():
            self.dialog.destroy()
        self.root.destroy()

    def _add(self, name):
        self.dialog.picker.add_manual(name, f"C:\\Apps\\{name}")

    def _iids_by_name(self):
        out = {}
        stack = [self.dialog.picker.tree.get_children()]
        while stack:
            for iid in stack.pop():
                out[self.dialog.picker.tree.item(iid, "text")] = iid
                stack.append(self.dialog.picker.tree.get_children(iid))
        return out

    def _select_only(self, names):
        iids = self._iids_by_name()
        keep = [iids[n] for n in names]
        self.dialog.picker.tree.selection_set(keep)
        # programmatic selection changes don't emit the virtual event; the
        # real click does not; mimic it
        self.dialog.picker.tree.event_generate("<<TreeviewSelect>>")
        self.dialog.update()

    def test_selecting_three_items_populates_combobox_with_three_names(self):
        for n in ("app_b.exe", "app_a.exe", "app_c.exe"):
            self._add(n)
        values = list(self.dialog.watch_combo["values"])
        self.assertEqual(sorted(values), ["app_a.exe", "app_b.exe", "app_c.exe"])
        # spec: keep the current choice while it is still among the selected
        # names — app_b was first, so it stays designated
        self.assertEqual(self.dialog.watch_combo.get(), "app_b.exe")

    def test_combobox_choice_decides_watched_app_on_save(self):
        for n in ("app_a.exe", "app_b.exe", "app_c.exe"):
            self._add(n)
        self.dialog.watch_combo.set("app_b.exe")
        self.dialog._save()
        result = self.dialog.result
        self.assertIsNotNone(result)
        self.assertEqual(result["watched_app"]["name"], "app_b.exe")
        self.assertEqual(
            sorted(m["name"] for m in result["meal_targets"]),
            ["app_a.exe", "app_c.exe"])

    def test_deselecting_watched_falls_back_to_first_remaining(self):
        self._add("app_a.exe")
        self._add("app_b.exe")
        self._add("app_c.exe")
        self.dialog.watch_combo.set("app_b.exe")
        self._select_only(["app_a.exe", "app_c.exe"])
        self.assertEqual(list(self.dialog.watch_combo["values"]),
                         ["app_a.exe", "app_c.exe"])
        self.assertEqual(self.dialog.watch_combo.get(), "app_a.exe")

    def test_save_with_nothing_selected_shows_existing_error(self):
        # add one then deselect it so the combobox empties via the real path
        self._add("app_a.exe")
        self._select_only([])
        self.assertEqual(self.dialog.watch_combo.get(), "")
        self.dialog._save()
        self.assertIsNone(self.dialog.result)
        self.assertEqual(
            [c for c in self.msg.calls if c[0] == "error"][-1][2],
            "Pick an app to watch first.")

    def test_save_without_designation_shows_designation_error(self):
        self._add("app_a.exe")
        self.dialog.watch_combo.set("")
        self.dialog._save()
        self.assertIsNone(self.dialog.result)
        self.assertEqual(
            [c for c in self.msg.calls if c[0] == "error"][-1][2],
            "Pick which selected app should trigger cleanup.")


if __name__ == "__main__":
    unittest.main()
