import os
import sys
import unittest
from unittest.mock import patch

import psutil

import watchdog_core as watchdog_app


class FakeProc:
    def __init__(self, pid, info=None, children=(), kill_exc=None):
        self.pid = pid
        self._info = info if info is not None else {"name": "x.exe", "exe": ""}
        self._children = list(children)
        self.kill_calls = 0
        self._kill_exc = kill_exc

    @property
    def info(self):
        return self._info

    def children(self, recursive=True):
        return list(self._children)

    def kill(self):
        self.kill_calls += 1
        if self._kill_exc is not None:
            raise self._kill_exc
        return None


APP_EXE = r"C:\App\app.exe"
ENTRY = {"name": "app.exe", "exe": APP_EXE}


class KillSelectionTests(unittest.TestCase):
    def test_directly_matched_processes_are_selected(self):
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE})
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 1)
        self.assertEqual(fake.kill_calls, 1)

    def test_recursive_children_selected(self):
        child = FakeProc(2, info={"name": "child.exe", "exe": r"C:\App\child.exe"})
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE}, children=[child])
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 2)
        self.assertEqual(fake.kill_calls, 1)
        self.assertEqual(child.kill_calls, 1)

    def test_same_directory_neighbor_is_not_killed(self):
        # Punch board Mission 3 removes same-directory neighbor killing.
        # A neighbor sharing the install directory is never enumerated into
        # the kill set — only the directly matched process is killed.
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE})
        neighbor = FakeProc(3, info={"pid": 3, "name": "helper.exe", "exe": r"C:\App\helper.exe"})
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[neighbor]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 1)
        self.assertEqual(neighbor.kill_calls, 0, "same-directory neighbor is not killed")

    def test_kill_processes_does_not_call_process_iter(self):
        # The only caller of psutil.process_iter inside kill_processes was the
        # removed directory-expansion block. kill_processes must not enumerate
        # all system processes for a plain direct-match scenario.
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE})
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake]), \
             patch.object(watchdog_app.psutil, "process_iter") as mock_iter:
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 1)
        self.assertEqual(fake.kill_calls, 1)
        mock_iter.assert_not_called()

    def test_kill_raising_no_such_process_not_counted(self):
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE},
                        kill_exc=psutil.NoSuchProcess(1))
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 0)
        self.assertEqual(fake.kill_calls, 1)

    def test_kill_raising_access_denied_not_counted(self):
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE},
                        kill_exc=psutil.AccessDenied(1))
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 0)
        self.assertEqual(fake.kill_calls, 1)

    def test_same_pid_reached_by_direct_match_and_child_killed_once(self):
        child = FakeProc(2, info={"name": "child.exe", "exe": r"C:\App\child.exe"})
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE}, children=[child])
        # child is both directly matched and returned as a descendant of fake
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake, child]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 2)
        self.assertEqual(fake.kill_calls, 1)
        self.assertEqual(child.kill_calls, 1, "same pid reached twice must be killed once")

    def test_own_pid_is_excluded_from_kill(self):
        # Process Watchdog must never terminate itself, even if its own
        # process were ever matched by a kill list. The own PID is excluded
        # before the kill loop, so it is never entered into the kill set.
        self_pid = os.getpid()
        own = FakeProc(self_pid, info={"pid": self_pid, "name": "app.exe", "exe": APP_EXE})
        with patch.object(watchdog_app, "find_matching_processes", return_value=[own]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 0)
        self.assertEqual(own.kill_calls, 0, "own PID must never receive kill()")

    def test_self_excluded_by_exe_path_even_with_different_pid(self):
        # A process that is really Process Watchdog but reported under a
        # different PID is still excluded by matching its exe path against
        # sys.executable through the same normalization used everywhere else.
        own = FakeProc(99999, info={"pid": 99999, "name": "watchdog.exe", "exe": sys.executable})
        with patch.object(watchdog_app, "find_matching_processes", return_value=[own]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 0)
        self.assertEqual(own.kill_calls, 0, "self matched by exe path must never receive kill()")

    def test_self_excluded_when_reached_as_recursive_child(self):
        # Self-protection must hold even when self is reached via the
        # descendant kill-source: a self-owned process returned as a recursive
        # child of a legitimately matched target. The former third test relied
        # on install-directory expansion (removed by Mission 1D), so this has
        # been renamed to cover the descendant source that remains.
        self_pid = os.getpid()
        own_child = FakeProc(self_pid, info={"pid": self_pid, "name": "watchdog.exe", "exe": sys.executable})
        target = FakeProc(1, info={"pid": 1, "name": "app.exe", "exe": APP_EXE}, children=[own_child])
        with patch.object(watchdog_app, "find_matching_processes", return_value=[target]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 1, "legitimately matched target is still killed")
        self.assertEqual(target.kill_calls, 1)
        self.assertEqual(own_child.kill_calls, 0,
                         "self reached as a recursive child must never receive kill()")


if __name__ == "__main__":
    unittest.main()
