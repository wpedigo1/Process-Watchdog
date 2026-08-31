import unittest
from unittest.mock import patch

import watchdog_app


class FakeProc:
    def __init__(self, pid, name):
        self.pid = pid
        self.info = {"name": name}


class OpenTriggerNamesTests(unittest.TestCase):
    def test_matched_processes_but_none_visible_returns_empty(self):
        procs = [FakeProc(1, "app.exe"), FakeProc(2, "app.exe")]
        with patch.object(watchdog_app, "find_matching_processes", return_value=procs), \
             patch.object(watchdog_app, "_get_visible_window_pids", return_value={99}):
            result = watchdog_app.open_trigger_names([{"name": "app.exe", "exe": ""}])
        self.assertEqual(result, [])

    def test_one_matched_process_owns_visible_window_returns_that_name(self):
        procs = [FakeProc(1, "app.exe")]
        with patch.object(watchdog_app, "find_matching_processes", return_value=procs), \
             patch.object(watchdog_app, "_get_visible_window_pids", return_value={1}):
            result = watchdog_app.open_trigger_names([{"name": "app.exe", "exe": ""}])
        self.assertEqual(result, ["app.exe"])

    def test_no_matched_processes_returns_empty(self):
        with patch.object(watchdog_app, "find_matching_processes", return_value=[]):
            result = watchdog_app.open_trigger_names([{"name": "app.exe", "exe": ""}])
        self.assertEqual(result, [])

    def test_names_sorted_case_insensitively_and_deduplicated(self):
        procs = [
            FakeProc(10, "zebra.exe"),
            FakeProc(11, "alpha.exe"),
            FakeProc(12, "Alpha.exe"),
            FakeProc(13, "beta.exe"),
            FakeProc(14, "zebra.exe"),
        ]
        # all visible by pid
        with patch.object(watchdog_app, "find_matching_processes", return_value=procs), \
             patch.object(watchdog_app, "_get_visible_window_pids", return_value={10, 11, 12, 13, 14}):
            result = watchdog_app.open_trigger_names([{"name": "app.exe", "exe": ""}])
        # documents current behavior: exact-case set dedup, then sort by key=str.lower
        self.assertEqual(result, ["alpha.exe", "Alpha.exe", "beta.exe", "zebra.exe"])


if __name__ == "__main__":
    unittest.main()
