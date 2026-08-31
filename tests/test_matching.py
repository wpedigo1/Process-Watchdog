import unittest
from unittest.mock import patch

import psutil

import watchdog_app


class FakeProc:
    def __init__(self, pid, info):
        self.pid = pid
        self.info = info


class RaisingFakeProc:
    def __init__(self, pid, exc):
        self.pid = pid
        self._exc = exc

    @property
    def info(self):
        raise self._exc


class NormPathTests(unittest.TestCase):
    def test_norm_path_lowercases_strips_path(self):
        self.assertEqual(
            watchdog_app._norm_path("  C:\\Apps\\Render\\Node.Exe  "),
            "c:\\apps\\render\\node.exe",
        )

    def test_norm_path_handles_none(self):
        self.assertEqual(watchdog_app._norm_path(None), "")

    def test_norm_path_handles_empty_string(self):
        self.assertEqual(watchdog_app._norm_path(""), "")


class FindMatchingProcessesTests(unittest.TestCase):
    def test_exact_path_entry_matches_same_path_different_case(self):
        entry = {"name": "node.exe", "exe": r"C:\Apps\Render\node.exe"}
        fake = FakeProc(1, {"name": "node.exe", "exe": r"c:\apps\render\NODE.EXE"})
        with patch.object(watchdog_app.psutil, "process_iter", return_value=[fake]):
            result = watchdog_app.find_matching_processes([entry])
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], fake)

    def test_exact_path_entry_does_not_match_shared_name_different_path(self):
        entry = {"name": "node.exe", "exe": r"C:\Apps\MyApp\node.exe"}
        fake = FakeProc(2, {"name": "node.exe", "exe": r"D:\Other\node.exe"})
        with patch.object(watchdog_app.psutil, "process_iter", return_value=[fake]):
            result = watchdog_app.find_matching_processes([entry])
        self.assertEqual(result, [])

    def test_empty_exe_falls_back_to_name_only_and_matches(self):
        entry = {"name": "node.exe", "exe": ""}
        fake = FakeProc(3, {"name": "NODE.EXE", "exe": r"D:\Other\node.exe"})
        with patch.object(watchdog_app.psutil, "process_iter", return_value=[fake]):
            result = watchdog_app.find_matching_processes([entry])
        self.assertEqual(len(result), 1)
        self.assertIs(result[0], fake)

    def test_no_such_process_during_iteration_is_skipped(self):
        entry = {"name": "node.exe", "exe": r"C:\Apps\node.exe"}
        ok = FakeProc(4, {"name": "node.exe", "exe": r"C:\Apps\node.exe"})
        bad = RaisingFakeProc(99, psutil.NoSuchProcess(99))
        with patch.object(watchdog_app.psutil, "process_iter", return_value=[ok, bad]):
            result = watchdog_app.find_matching_processes([entry])
        self.assertEqual([p.pid for p in result], [4])

    def test_access_denied_during_iteration_is_skipped(self):
        entry = {"name": "node.exe", "exe": r"C:\Apps\node.exe"}
        ok = FakeProc(5, {"name": "node.exe", "exe": r"C:\Apps\node.exe"})
        bad = RaisingFakeProc(98, psutil.AccessDenied(98))
        with patch.object(watchdog_app.psutil, "process_iter", return_value=[ok, bad]):
            result = watchdog_app.find_matching_processes([entry])
        self.assertEqual([p.pid for p in result], [5])

    def test_same_pid_matched_twice_returned_once(self):
        entry = {"name": "node.exe", "exe": r"C:\Apps\node.exe"}
        first = FakeProc(6, {"name": "node.exe", "exe": r"C:\Apps\node.exe"})
        second = FakeProc(6, {"name": "node.exe", "exe": r"C:\Apps\node.exe"})
        with patch.object(watchdog_app.psutil, "process_iter", return_value=[first, second]):
            result = watchdog_app.find_matching_processes([entry])
        self.assertEqual(len(result), 1, "same pid should be deduplicated to one result")


if __name__ == "__main__":
    unittest.main()
