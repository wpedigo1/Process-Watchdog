"""Regression tests for the Mission 6D defect 4 / Mission 6E fix: the kill
engine's protection filter read proc.info on descendant processes obtained
from proc.children(), which are plain psutil.Process objects with NO .info
attribute (only process_iter results carry .info). Every kill of a matched
process with children raised AttributeError and killed the Watcher thread.

These tests deliberately use REAL psutil.Process objects and REAL disposable
subprocesses spawned by the tests themselves — FakeProc in
test_kill_selection.py always provides .info, so it cannot represent the
crashing shape no matter how it is configured (that is exactly the coverage
gap that hid the bug through an 89-test green suite).

The multi-process kill test uses a uniquely-named COPY of the Python
interpreter in a temp dir as its disposable target, because killing anything
whose exe equals sys.executable is impossible by design (self-exe-path
protection, Mission 1C) and System32 executables are protected paths
(Mission 3). The unique temp path guarantees the identity can only match
processes this test spawned. No real user application is ever targeted, and
every spawned process is cleaned up unconditionally in finally.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

import psutil

import watchdog_core as core


def _wait_for(predicate, timeout=12.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(step)
    return False


class _DisposableDog:
    """Context manager: a copied-interpreter exe with a unique path, running
    a parent that spawns one child of its own, so a REAL psutil.Process with
    no .info is available via .children()."""

    EXE_NAME = "pw_killtest_dog.exe"
    PARENT_CODE = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "time.sleep(60)"
    )

    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="pw_6e_test_")
        self.exe = os.path.join(self.tmp, self.EXE_NAME)
        self.parent = None
        self.child_pids = []

    def __enter__(self):
        shutil.copy(sys.executable, self.exe)
        dll_name = "python%d%d.dll" % (sys.version_info.major, sys.version_info.minor)
        dll = os.path.join(os.path.dirname(sys.executable), dll_name)
        if os.path.exists(dll):
            shutil.copy(dll, os.path.join(self.tmp, dll_name))
        env = dict(os.environ, PYTHONHOME=os.path.dirname(sys.executable))
        self.parent = subprocess.Popen([self.exe, "-c", self.PARENT_CODE], env=env)
        ok = _wait_for(lambda: self._live_children())
        if not ok:
            raise AssertionError("disposable dog failed to spawn its child")
        return self

    def _live_children(self):
        try:
            kids = psutil.Process(self.parent.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            return []
        self.child_pids = [k.pid for k in kids]
        return kids

    def entry(self):
        return {"name": self.EXE_NAME, "exe": self.exe}

    def all_pids(self):
        return [self.parent.pid] + self.child_pids

    def __exit__(self, *exc):
        for pid in self.all_pids():
            try:
                psutil.Process(pid).kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        try:
            self.parent.kill()
        except Exception:
            pass
        try:
            self.parent.wait(timeout=10)
        except Exception:
            pass
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


class LiveIdentityTests(unittest.TestCase):
    def test_live_identity_on_real_process_without_info(self):
        # A real psutil.Process NOT obtained from process_iter has no .info
        # attribute at all - the shape FakeProc cannot represent.
        proc = psutil.Process(os.getpid())
        self.assertFalse(hasattr(proc, "info"))
        name, exe = core._live_identity(proc)
        self.assertIsInstance(name, str)
        self.assertIsInstance(exe, str)
        self.assertTrue(name)
        self.assertEqual(exe.lower(), sys.executable.lower())

    def test_is_self_on_own_pid_real_process(self):
        self.assertTrue(core._is_self(psutil.Process(os.getpid())))

    def test_is_self_on_real_process_without_info_no_raise(self):
        # The exact crash site (watchdog_core.py _is_self, formerly
        # proc.info.get("exe")): a real non-process_iter Process object that
        # is NOT self must evaluate to False without AttributeError.
        proc = psutil.Process(os.getpid())
        # Construct the not-self shape directly: a live object with our pid is
        # self; use the parent process (a shell, different exe, not us).
        ppid = psutil.Process(os.getpid()).ppid()
        other = psutil.Process(ppid)
        self.assertFalse(hasattr(other, "info"))
        self.assertFalse(core._is_self(other))


@unittest.skipUnless(os.name == "nt", "copied-exe disposable target is Windows-specific")
class RealKillWithChildrenTests(unittest.TestCase):
    def test_live_identity_and_is_self_on_real_child_process(self):
        with _DisposableDog() as dog:
            parent_proc = psutil.Process(dog.parent.pid)
            kids = parent_proc.children(recursive=True)
            self.assertEqual(len(kids), 1)
            child = kids[0]
            # The crashing shape, for the record:
            self.assertFalse(hasattr(child, "info"))
            name, exe = core._live_identity(child)
            self.assertEqual(name.lower(), dog.EXE_NAME.lower())
            self.assertEqual(exe.lower(), dog.exe.lower())
            # Pre-fix this raised AttributeError inside _is_self:
            self.assertFalse(core._is_self(child))
            self.assertFalse(core._is_self(parent_proc))

    def test_kill_processes_kills_real_parent_and_child_without_raising(self):
        # Acceptance criterion 3: a matched process with a REAL child must
        # complete without raising, and both must actually die.
        with _DisposableDog() as dog:
            parent_pid = dog.parent.pid
            child_pid = dog._live_children()[0].pid
            result = core.kill_processes([dog.entry()], detail=True)
            self.assertIsInstance(result, core.KillResult)
            self.assertEqual(result.failed, [])
            self.assertIn(dog.EXE_NAME.lower(),
                          [n.lower() for n in result.killed])
            gone = _wait_for(lambda: not psutil.pid_exists(parent_pid)
                             and not psutil.pid_exists(child_pid), timeout=10)
            self.assertTrue(gone, "parent pid=%s child pid=%s still alive"
                            % (parent_pid, child_pid))


if __name__ == "__main__":
    unittest.main()
