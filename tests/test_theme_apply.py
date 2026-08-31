"""Tests for window-self theming in apply_theme (Mission 5-FIX).

apply_theme must color the passed widget's own background (the window canvas),
not just its children's. A real Tk instance is used here on purpose: this test
verifies actual widget config, not application logic.
"""

import tkinter as tk
import unittest

import watchdog_ui
from watchdog_ui import apply_theme


class ApplyThemeOwnBgTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_sets_widgets_own_background(self):
        frame = tk.Frame(self.root, bg="#000000")
        palette = {"bg": "#123456", "fg": "#000000", "accent": "#0078D4"}

        apply_theme(frame, palette)

        self.assertEqual(frame.cget("bg"), "#123456")


if __name__ == "__main__":
    unittest.main()
