import subprocess
import sys
import types
import unittest
from unittest.mock import patch

import watchdog_app


class ElevatedStartupTaskTests(unittest.TestCase):
    @staticmethod
    def _fake_winreg():
        return types.SimpleNamespace(
            HKEY_CURRENT_USER=object(), KEY_READ=1, KEY_SET_VALUE=2,
            REG_SZ=1,
            OpenKey=lambda *args: object(),
            QueryValueEx=lambda *args: (None, 1),
            SetValueEx=lambda *args: None,
            DeleteValue=lambda *args: None,
            CloseKey=lambda *args: None,
        )

    def test_query_reports_registered_only_for_current_executable(self):
        xml = (
            '<?xml version="1.0"?>'
            '<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
            '<Actions><Exec><Command>C:\\Apps\\ProcessWatchdog.exe</Command>'
            '</Exec></Actions></Task>'
        )
        completed = subprocess.CompletedProcess([], 0, stdout=xml, stderr="")
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", r"C:\Apps\ProcessWatchdog.exe"), \
             patch.dict(sys.modules, {"winreg": self._fake_winreg()}), \
             patch.object(subprocess, "run", return_value=completed):
            self.assertTrue(watchdog_app.is_startup_registered())

    def test_enable_creates_highest_privilege_logon_task(self):
        completed = subprocess.CompletedProcess([], 0, stdout="SUCCESS", stderr="")
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", r"C:\Apps\ProcessWatchdog.exe"), \
             patch.dict(sys.modules, {"winreg": self._fake_winreg()}), \
             patch.object(subprocess, "run", return_value=completed) as run:
            self.assertTrue(watchdog_app.set_startup_registered(True))
        command = run.call_args.args[0]
        self.assertIn("/CREATE", [part.upper() for part in command])
        self.assertIn("ONLOGON", [part.upper() for part in command])
        self.assertIn("HIGHEST", [part.upper() for part in command])
        self.assertIn(r'"C:\Apps\ProcessWatchdog.exe"', command)

    def test_disable_deletes_startup_task(self):
        completed = subprocess.CompletedProcess([], 0, stdout="SUCCESS", stderr="")
        with patch.object(sys, "frozen", True, create=True), \
             patch.dict(sys.modules, {"winreg": self._fake_winreg()}), \
             patch.object(subprocess, "run", return_value=completed) as run:
            self.assertTrue(watchdog_app.set_startup_registered(False))
        self.assertIn("/DELETE", [part.upper() for part in run.call_args.args[0]])

    def test_legacy_run_entry_is_removed_only_after_task_creation_succeeds(self):
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", r"C:\Apps\ProcessWatchdog.exe"), \
             patch.object(watchdog_app, "_read_legacy_startup",
                          return_value=r"C:\Apps\ProcessWatchdog.exe"), \
             patch.object(watchdog_app, "set_startup_registered", return_value=True), \
             patch.object(watchdog_app, "_delete_legacy_startup") as delete:
            self.assertTrue(watchdog_app.migrate_legacy_startup())
        delete.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
