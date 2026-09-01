import unittest
from unittest.mock import patch

import watchdog_core
import watchdog_ui


class FeedingStatePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.watchdog = {
            "id": "dog-1",
            "name": "Dog",
            "enabled": True,
            "watched_app": {"name": "app.exe", "exe": ""},
            "meal_targets": [{"name": "helper.exe", "exe": ""}],
            "has_had_first_bite": False,
            "dog_sick": False,
            "last_error": [],
        }
        self.cfg = {
            "poll_interval": 2.0,
            "grace_seconds": 10.0,
            "watchdogs": [self.watchdog],
        }
        self.win = watchdog_ui.ConfigWindow(
            self.cfg,
            on_change=lambda c: None,
            watcher=watchdog_core.Watcher(get_config=lambda: self.cfg),
        )

    def tearDown(self):
        self.win.root.destroy()

    def test_successful_feed_persists_first_bite_and_clears_sickness(self):
        self.watchdog["dog_sick"] = True
        self.watchdog["last_error"] = ["old-error.exe"]
        with patch.object(watchdog_ui, "save_config"):
            self.win.record_kill_result("dog-1", "Dog", ["app.exe"], [])
        self.assertIs(self.watchdog["has_had_first_bite"], True)
        self.assertIs(self.watchdog["dog_sick"], False)
        self.assertEqual(self.watchdog["last_error"], [])

    def test_failed_feed_persists_sick_alert_and_error_details(self):
        with patch.object(watchdog_ui, "save_config"):
            self.win.record_kill_result(
                "dog-1", "Dog", ["app.exe"], ["helper.exe"])
        self.assertIs(self.watchdog["has_had_first_bite"], True)
        self.assertIs(self.watchdog["dog_sick"], True)
        self.assertEqual(self.watchdog["last_error"], ["helper.exe"])

    def test_close_transition_persists_first_bite_before_feeding(self):
        with patch.object(watchdog_ui, "save_config") as save:
            self.win.record_app_closed("dog-1")
        self.assertIs(self.watchdog["has_had_first_bite"], True)
        save.assert_called_once_with(self.cfg)


if __name__ == "__main__":
    unittest.main()
