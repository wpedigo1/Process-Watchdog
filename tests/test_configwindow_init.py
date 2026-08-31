"""Regression test for the Mission 6B startup crash (fixed in Mission 6C).

ConfigWindow.__init__ used to call self._tick_status() (via the
`if self.watcher:` guard) BEFORE self.toggle_btn was created, so every real
launch — main() always passes a real Watcher — crashed with
AttributeError: 'ConfigWindow' object has no attribute 'toggle_btn'.

This file is a DELIBERATE, NARROW exception to this codebase's no-UI-test
precedent: an __init__-time crash like this can ONLY be caught by actually
instantiating ConfigWindow with a real Watcher, not by source review or
mocked unit tests (the 87-test suite passed while the app was unlaunchable).
The Watcher is constructed but never .start()ed, so no background thread and
no kill logic ever runs. Each test destroys its Tk window so nothing leaks.
"""

import unittest

import watchdog_core
import watchdog_ui


class ConfigWindowInitTests(unittest.TestCase):
    def _construct_and_destroy(self, cfg):
        watcher = watchdog_core.Watcher(get_config=lambda: cfg)
        win = watchdog_ui.ConfigWindow(cfg, on_change=lambda c: None,
                                       watcher=watcher)
        try:
            # The attribute whose late assignment caused the crash must exist
            # immediately after construction, and the scheduled status tick
            # must not have raised during __init__.
            self.assertTrue(hasattr(win, "toggle_btn"))
            self.assertFalse(watcher.is_alive())
        finally:
            win.root.destroy()

    def test_instantiates_with_real_watcher_and_empty_watchdogs(self):
        cfg = {"poll_interval": 2.0, "grace_seconds": 10.0, "watchdogs": []}
        self._construct_and_destroy(cfg)

    def test_instantiates_with_real_watcher_and_enabled_watchdog(self):
        # At least one ENABLED watchdog so _tick_status runs its full loop
        # body path, not just the empty-list early-out.
        cfg = {
            "poll_interval": 2.0,
            "grace_seconds": 10.0,
            "watchdogs": [
                {
                    "id": "regression-dog-1",
                    "name": "Regression Dog",
                    "enabled": True,
                    "watched_app": {"name": "dummy.exe",
                                    "exe": "C:\\Dummy\\dummy.exe"},
                    "meal_targets": [],
                }
            ],
        }
        self._construct_and_destroy(cfg)


if __name__ == "__main__":
    unittest.main()
