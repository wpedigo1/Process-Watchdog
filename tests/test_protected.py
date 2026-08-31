import os
import sys
import unittest

import watchdog_core


class IsProtectedEntryTests(unittest.TestCase):
    def test_self_by_exe_path_is_protected(self):
        entry = {"name": "any.exe", "exe": sys.executable}
        self.assertTrue(watchdog_core.is_protected_entry(entry))

    def test_self_by_name_only_is_protected(self):
        own_name = os.path.basename(sys.executable)
        entry = {"name": own_name, "exe": ""}
        self.assertTrue(watchdog_core.is_protected_entry(entry))

    def test_path_under_system_directory_is_protected(self):
        for hint in watchdog_core.SYSTEM_PATH_HINTS:
            exe = "c:" + hint + "\\something.exe"
            self.assertTrue(
                watchdog_core.is_protected_entry({"name": "something.exe", "exe": exe}),
                msg=f"path hint {hint} should be flagged protected",
            )

    def test_known_protected_name_without_exe_is_protected(self):
        for name in watchdog_core.PROTECTED_PROCESS_NAMES:
            self.assertTrue(
                watchdog_core.is_protected_entry({"name": name, "exe": ""}),
                msg=f"protected name {name!r} should be flagged protected",
            )

    def test_ordinary_app_is_not_protected(self):
        entry = {"name": "app.exe", "exe": r"C:\App\app.exe"}
        self.assertFalse(watchdog_core.is_protected_entry(entry))


if __name__ == "__main__":
    unittest.main()
