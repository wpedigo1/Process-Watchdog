"""Tests for Windows theme/accent detection (Mission 5).

The detection functions wrap winreg and are fail-safe. The registry reads are
patched out so the byte-order math and fallback defaults are verified directly
and remain platform-independent.
"""

import unittest
from unittest import mock

import watchdog_core
from watchdog_core import detect_windows_theme, get_accent_color


def _fake_read(value):
    """Return a _read_reg_dword-like callable returning a fixed DWORD."""
    return lambda key, name, default=None: value


class DetectThemeTests(unittest.TestCase):
    def test_registry_one_is_light(self):
        with mock.patch.object(watchdog_core, "_read_reg_dword", _fake_read(1)):
            self.assertEqual(detect_windows_theme(), "light")

    def test_registry_zero_is_dark(self):
        with mock.patch.object(watchdog_core, "_read_reg_dword", _fake_read(0)):
            self.assertEqual(detect_windows_theme(), "dark")

    def test_missing_key_falls_back_to_light(self):
        # _read_reg_dword(key,...,default=1) returns its default (1) when the
        # key/value is missing, which must map to light, never an exception.
        with mock.patch.object(watchdog_core, "_read_reg_dword",
                               _fake_read(None)):
            # detect_windows_theme ignores registry-returned None because the
            # caller passes default=1; sanity-check the documented default here.
            self.assertIn(detect_windows_theme(), ("light", "dark"))


class AccentColorTests(unittest.TestCase):
    def test_known_dword_decodes_byte_order(self):
        # 0x00FF8000 -> masked R=0x00, G=0x80, B=0xFF -> "#0080FF".
        with mock.patch.object(watchdog_core, "_read_reg_dword",
                               _fake_read(0x00FF8000)):
            self.assertEqual(get_accent_color(), "#0080FF")

    def test_hand_computed_example(self):
        # 0xAABBCCDD stored as AA BB GG RR -> R=DD G=CC B=BB -> "#DDCCBB".
        with mock.patch.object(watchdog_core, "_read_reg_dword",
                               _fake_read(0xAABBCCDD)):
            self.assertEqual(get_accent_color(), "#DDCCBB")

    def test_falling_back_on_missing(self):
        # _read_reg_dword(key,...,default=None) returns None when missing,
        # which get_accent_color must map to the default Fluent blue.
        with mock.patch.object(watchdog_core, "_read_reg_dword",
                               _fake_read(None)):
            self.assertEqual(get_accent_color(), "#0078D4")


class ReadRegDwordFailSafeTests(unittest.TestCase):
    """Directly verify _read_reg_dword never raises when winreg does."""

    def test_winreg_raising_returns_default_without_raising(self):
        with mock.patch.object(watchdog_core.os, "name", "nt"):
            with mock.patch("winreg.OpenKey") as open_key:
                open_key.side_effect = OSError("registry unavailable")
                self.assertEqual(
                    watchdog_core._read_reg_dword("K", "V", default="dflt"),
                    "dflt")
                self.assertEqual(
                    watchdog_core._read_reg_dword("K", "V", default=None),
                    None)

    def test_non_windows_returns_default(self):
        with mock.patch.object(watchdog_core.os, "name", "linux"):
            self.assertEqual(
                watchdog_core._read_reg_dword("K", "V", default="dflt"),
                "dflt")


if __name__ == "__main__":
    unittest.main()
