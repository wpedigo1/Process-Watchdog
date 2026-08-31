import os
import unittest
from unittest.mock import patch

import watchdog_core as watchdog_app

APP_IDENT = {"name": "app.exe", "exe": r"C:\Apps\App\app.exe"}
HELPER_IDENT = {"name": "helper.exe", "exe": r"C:\Apps\App\helper.exe"}


class EffectiveTriggerTests(unittest.TestCase):
    def test_returns_watched_app_when_set(self):
        watchdog = {"watched_app": APP_IDENT, "meal_targets": [HELPER_IDENT]}
        self.assertEqual(watchdog_app.effective_trigger(watchdog), [APP_IDENT])

    def test_returns_empty_when_no_watched_app(self):
        watchdog = {"watched_app": None, "meal_targets": [HELPER_IDENT]}
        self.assertEqual(watchdog_app.effective_trigger(watchdog), [])


class EffectiveKillTests(unittest.TestCase):
    def test_watched_app_plus_meal_targets_deduped(self):
        watchdog = {
            "watched_app": APP_IDENT,
            # watched app appears twice in meal_targets -> deduped to a single kill
            "meal_targets": [APP_IDENT, APP_IDENT, HELPER_IDENT],
        }
        self.assertEqual(
            watchdog_app.effective_kill(watchdog), [APP_IDENT, HELPER_IDENT]
        )

    def test_watched_app_is_always_a_kill_target(self):
        watchdog = {"watched_app": APP_IDENT, "meal_targets": []}
        self.assertEqual(watchdog_app.effective_kill(watchdog), [APP_IDENT])

    def test_no_watched_app_uses_meal_targets_verbatim(self):
        # Without a watched app there is no dedup; whatever was persisted is
        # returned as-is (ambiguity until Retrain picks a watched app).
        watchdog = {
            "watched_app": None,
            "meal_targets": [HELPER_IDENT, HELPER_IDENT],
        }
        self.assertEqual(watchdog_app.effective_kill(watchdog), [HELPER_IDENT, HELPER_IDENT])


class ProcessGroupSelfExclusionTests(unittest.TestCase):
    """Criterion 8: the app must never offer its own running instance as a
    selectable target in the process picker, even when the OS reports it as a
    normal running process."""

    class _FakeProc:
        def __init__(self, pid, name, exe="", username="wpedi"):
            self.info = {"pid": pid, "name": name, "exe": exe, "username": username}

    def test_self_process_is_excluded_from_groups(self):
        external = self._FakeProc(999999, "app.exe", r"C:\Apps\App\app.exe")
        own = self._FakeProc(os.getpid(), "ProcessWatchdog.exe", r"C:\App\ProcessWatchdog.exe")
        with patch.object(watchdog_app.psutil, "process_iter", return_value=[external, own]):
            groups = watchdog_app.get_process_groups(hide_system=True)
        names = {n for label, entries in groups for n, _ in entries}
        self.assertIn("app.exe", names)
        self.assertNotIn("ProcessWatchdog.exe", names)

    def test_all_running_processes_are_excluded_when_everything_is_self(self):
        own = self._FakeProc(os.getpid(), "ProcessWatchdog.exe")
        with patch.object(watchdog_app.psutil, "process_iter", return_value=[own]):
            groups = watchdog_app.get_process_groups(hide_system=True)
        self.assertEqual(groups, [])


if __name__ == "__main__":
    unittest.main()
