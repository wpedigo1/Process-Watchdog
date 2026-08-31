"""Real-Tk regression tests for Mission 6F dialog and picker crashes."""

import tkinter as tk
import unittest
from unittest import mock

import watchdog_ui


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

    def test_set_locked_refreshes_without_raising(self):
        picker = watchdog_ui.ProcessPicker(self.root)
        picker.set_locked("some.exe")
        locked = picker.tree.get_children()[0]
        self.assertIn("locked", picker.tree.item(locked, "tags"))
        picker.destroy()

    def test_manual_selection_survives_locked_refresh(self):
        picker = watchdog_ui.ProcessPicker(self.root)
        picker.set_locked("some.exe", "C:\\Apps\\some.exe")
        picker.add_manual("helper.exe", "C:\\Apps\\helper.exe")
        self.assertEqual(
            picker.get_selected(),
            [{"name": "helper.exe", "exe": "C:\\Apps\\helper.exe"}],
        )
        picker.destroy()


if __name__ == "__main__":
    unittest.main()
