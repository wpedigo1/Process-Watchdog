import os
import sys
import unittest
from unittest.mock import patch

import psutil

import watchdog_core as watchdog_app


class FakeProc:
    def __init__(self, pid, info=None, children=(), kill_exc=None,
                 username_val=None, username_exc=None):
        self.pid = pid
        self._info = info if info is not None else {"name": "x.exe", "exe": ""}
        self._children = list(children)
        self.kill_calls = 0
        self._kill_exc = kill_exc
        self._username_val = username_val
        self._username_exc = username_exc

    @property
    def info(self):
        return self._info

    def name(self):
        # Real psutil.Process exposes name()/exe() as live-call methods;
        # FakeProc originally lacked them because production code only read
        # the .info cache. They mirror the same values.
        return self._info.get("name", "")

    def exe(self):
        return self._info.get("exe", "")

    def children(self, recursive=True):
        return list(self._children)

    def kill(self):
        self.kill_calls += 1
        if self._kill_exc is not None:
            raise self._kill_exc
        return None

    def username(self):
        if self._username_exc is not None:
            raise self._username_exc
        return self._username_val


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


    def test_protected_system_identity_is_never_killed(self):
        # A matched entry whose live resolution is a protected core OS
        # identity (here a system32 path, explicitly NOT self) must never be
        # killed. The _is_self check alone would not catch this identity --
        # the is_protected_entry filter closes that defense-in-depth gap.
        sys_proc = FakeProc(777, info={"pid": 777, "name": "something.exe",
                                        "exe": r"C:\Windows\System32\something.exe"})
        with patch.object(watchdog_app, "find_matching_processes", return_value=[sys_proc]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 0)
        self.assertEqual(sys_proc.kill_calls, 0,
                         "protected system identity must never receive kill()")

    def test_system_owned_username_is_not_killed(self):
        # Criterion 1: a matched process whose username() returns a
        # SYSTEM-owned account is never killed.
        proc = FakeProc(10, info={"name": "app.exe", "exe": APP_EXE},
                        username_val="NT AUTHORITY\\SYSTEM")
        with patch.object(watchdog_app, "find_matching_processes", return_value=[proc]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 0)
        self.assertEqual(proc.kill_calls, 0,
                         "SYSTEM-owned process must not be killed")

    def test_local_service_username_is_not_killed(self):
        # Criterion 2: LOCAL SERVICE account is also excluded.
        proc = FakeProc(11, info={"name": "app.exe", "exe": APP_EXE},
                        username_val="NT AUTHORITY\\LOCAL SERVICE")
        with patch.object(watchdog_app, "find_matching_processes", return_value=[proc]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 0)
        self.assertEqual(proc.kill_calls, 0,
                         "LOCAL SERVICE process must not be killed")

    def test_network_service_username_is_not_killed(self):
        # Criterion 2: NETWORK SERVICE account is also excluded.
        proc = FakeProc(12, info={"name": "app.exe", "exe": APP_EXE},
                        username_val="NT AUTHORITY\\NETWORK SERVICE")
        with patch.object(watchdog_app, "find_matching_processes", return_value=[proc]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 0)
        self.assertEqual(proc.kill_calls, 0,
                         "NETWORK SERVICE process must not be killed")

    def test_system_owned_recursive_child_is_not_killed(self):
        # Criterion 3: a recursive child (not the direct match) whose
        # username() returns SYSTEM is also excluded -- proves the check
        # covers children, not just direct matches.
        parent = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE},
                          username_val="DOMAIN\\user")
        system_child = FakeProc(20, info={"name": "svc.exe", "exe": r"C:\App\svc.exe"},
                                username_val="NT AUTHORITY\\SYSTEM")
        parent._children = [system_child]
        with patch.object(watchdog_app, "find_matching_processes", return_value=[parent]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 1)
        self.assertEqual(parent.kill_calls, 1,
                         "non-SYSTEM parent must be killed")
        self.assertEqual(system_child.kill_calls, 0,
                         "SYSTEM-owned recursive child must not be killed")

    def test_access_denied_on_username_does_not_protect(self):
        # Criterion 4: AccessDenied on username() does NOT make the process
        # protected. It proceeds to the normal kill attempt, which may itself
        # hit AccessDenied and be honestly skipped.
        proc = FakeProc(30, info={"name": "app.exe", "exe": APP_EXE},
                        username_exc=psutil.AccessDenied(30))
        with patch.object(watchdog_app, "find_matching_processes", return_value=[proc]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        # AccessDenied on username() means "cannot determine" -- NOT protected.
        # The process reaches the kill loop, where proc.kill() is called
        # normally. In this test kill() succeeds (no kill_exc set).
        self.assertEqual(result, 1)
        self.assertEqual(proc.kill_calls, 1,
                         "AccessDenied on username() must not protect the process")

    def test_normal_user_owned_process_is_killed(self):
        # Criterion 5: a normal, non-SYSTEM-owned process is unaffected.
        proc = FakeProc(40, info={"name": "app.exe", "exe": APP_EXE},
                        username_val="DOMAIN\\jsmith")
        with patch.object(watchdog_app, "find_matching_processes", return_value=[proc]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertEqual(result, 1)
        self.assertEqual(proc.kill_calls, 1,
                         "normal user-owned process must be killed as before")

    # --- Mission 4B: detail=True feeding results ---

    def test_detail_false_returns_int_unchanged(self):
        # Criterion 1: default call with no detail arg returns an int, exactly
        # as before this mission.
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE})
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY])
        self.assertIsInstance(result, int)
        self.assertEqual(result, 1)

    def test_detail_true_successful_kill_lists_killed(self):
        # Criterion 2: detail=True with a successful kill -> .killed has name,
        # .failed empty.
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE})
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY], detail=True)
        self.assertEqual(result.killed, ["app.exe"])
        self.assertEqual(result.failed, [])

    def test_detail_true_access_denied_lists_failed(self):
        # Criterion 3: detail=True with AccessDenied on .kill() -> .failed has
        # the name, .killed does not.
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE},
                        kill_exc=psutil.AccessDenied(1))
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY], detail=True)
        self.assertEqual(result.killed, [])
        self.assertEqual(result.failed, ["app.exe"])

    def test_detail_true_no_match_both_empty(self):
        # Criterion 4: nothing matched at all -> both killed and failed empty.
        with patch.object(watchdog_app, "find_matching_processes", return_value=[]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY], detail=True)
        self.assertEqual(result.killed, [])
        self.assertEqual(result.failed, [])

    def test_detail_true_protected_identity_invisible(self):
        # Criterion 5: a protected/self identity filtered by existing checks
        # does NOT appear in either killed or failed with detail=True.
        sys_proc = FakeProc(777, info={"pid": 777, "name": "svc.exe",
                                        "exe": r"C:\Windows\System32\svc.exe"})
        with patch.object(watchdog_app, "find_matching_processes", return_value=[sys_proc]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY], detail=True)
        self.assertEqual(result.killed, [])
        self.assertEqual(result.failed, [],
                         "protected identity must not be reported as failed")

    def test_detail_true_dedupes_and_sorts_names(self):
        # Same process reached by both direct match and child is deduped in
        # killed; names are sorted case-insensitively.
        child = FakeProc(2, info={"name": "zchild.exe", "exe": r"C:\App\zchild.exe"})
        fake = FakeProc(1, info={"name": "app.exe", "exe": APP_EXE}, children=[child])
        with patch.object(watchdog_app, "find_matching_processes", return_value=[fake, child]), \
             patch.object(watchdog_app.psutil, "process_iter", return_value=[]):
            result = watchdog_app.kill_processes([ENTRY], detail=True)
        self.assertEqual(result.killed, ["app.exe", "zchild.exe"])


if __name__ == "__main__":
    unittest.main()
