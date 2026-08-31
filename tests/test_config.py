import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import watchdog_core as watchdog_app


class NormalizeProcessEntryTests(unittest.TestCase):
    def test_full_dict_preserves_name_and_exe(self):
        self.assertEqual(
            watchdog_app._normalize_process_entry(
                {"name": "node.exe", "exe": r"C:\Apps\Render\node.exe"}
            ),
            {"name": "node.exe", "exe": r"C:\Apps\Render\node.exe"},
        )

    def test_dict_missing_exe_gets_empty_exe(self):
        self.assertEqual(
            watchdog_app._normalize_process_entry({"name": "node.exe"}),
            {"name": "node.exe", "exe": ""},
        )

    def test_dict_missing_name_gets_empty_name(self):
        self.assertEqual(
            watchdog_app._normalize_process_entry({"exe": r"C:\Apps\node.exe"}),
            {"name": "", "exe": r"C:\Apps\node.exe"},
        )

    def test_empty_dict_yields_empty_name_and_exe(self):
        self.assertEqual(
            watchdog_app._normalize_process_entry({}),
            {"name": "", "exe": ""},
        )

    def test_plain_string_becomes_dict_with_empty_exe(self):
        self.assertEqual(
            watchdog_app._normalize_process_entry("node.exe"),
            {"name": "node.exe", "exe": ""},
        )


class LoadConfigTests(unittest.TestCase):
    def test_load_config_creates_missing_file_and_returns_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with patch.object(watchdog_app, "CONFIG_PATH", str(config_path)):
                loaded = watchdog_app.load_config()
            self.assertTrue(config_path.exists(), "load_config should create the config file")
            self.assertEqual(loaded, dict(watchdog_app.DEFAULT_CONFIG))

    def test_load_config_watchdogs_wins_when_both_rules_and_watchdogs_present(self):
        content = {
            "poll_interval": 2.0,
            "grace_seconds": 10.0,
            "rules": [{"id": "legacy", "name": "Legacy", "enabled": True,
                       "trigger": ["old.exe"], "kill": ["old.exe"]}],
            "watchdogs": [{"id": "new", "name": "New", "enabled": True,
                           "trigger": ["new.exe"], "kill": ["new.exe"]}],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps(content), encoding="utf-8")
            with patch.object(watchdog_app, "CONFIG_PATH", str(config_path)):
                loaded = watchdog_app.load_config()
        self.assertEqual(len(loaded["watchdogs"]), 1)
        self.assertEqual(loaded["watchdogs"][0]["id"], "new")
        inherited_rules = [w for w in loaded["watchdogs"] if w.get("id") == "legacy"]
        self.assertEqual(inherited_rules, [], "legacy rules should be discarded when watchdogs is non-empty")

    def test_load_config_normalizes_legacy_string_entries_in_trigger_and_kill(self):
        content = {
            "watchdogs": [{
                "id": "wd1", "name": "WD", "enabled": True,
                "trigger": ["app.exe"],
                "kill": ["helper.exe"],
            }],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps(content), encoding="utf-8")
            with patch.object(watchdog_app, "CONFIG_PATH", str(config_path)):
                loaded = watchdog_app.load_config()
        wd = loaded["watchdogs"][0]
        self.assertEqual(wd["trigger"], [{"name": "app.exe", "exe": ""}])
        self.assertEqual(wd["kill"], [{"name": "helper.exe", "exe": ""}])

    def test_load_config_preserves_id_name_and_enabled(self):
        content = {
            "watchdogs": [{
                "id": "abc-123", "name": "My Watchdog", "enabled": False,
                "trigger": [{"name": "app.exe", "exe": ""}],
                "kill": [{"name": "app.exe", "exe": ""}],
            }],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps(content), encoding="utf-8")
            with patch.object(watchdog_app, "CONFIG_PATH", str(config_path)):
                loaded = watchdog_app.load_config()
        wd = loaded["watchdogs"][0]
        self.assertEqual(wd["id"], "abc-123")
        self.assertEqual(wd["name"], "My Watchdog")
        self.assertIs(wd["enabled"], False)

    def test_malformed_json_returns_defaults_current_behavior(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text("{not valid json", encoding="utf-8")
            with patch.object(watchdog_app, "CONFIG_PATH", str(config_path)):
                loaded = watchdog_app.load_config()
        self.assertEqual(loaded, dict(watchdog_app.DEFAULT_CONFIG))


class SaveLoadRoundTripTests(unittest.TestCase):
    def test_save_then_load_round_trip_preserves_watchdogs(self):
        original = {
            "poll_interval": 3.0,
            "grace_seconds": 25.0,
            "watchdogs": [
                {
                    "id": "wd-1", "name": "First", "enabled": True,
                    "trigger": [{"name": "a.exe", "exe": r"C:\Apps\A\a.exe"}],
                    "kill": [{"name": "a.exe", "exe": r"C:\Apps\A\a.exe"},
                             {"name": "helper.exe", "exe": r"C:\Apps\A\helper.exe"}],
                },
                {
                    "id": "wd-2", "name": "Second", "enabled": False,
                    "trigger": [{"name": "b.exe", "exe": ""}],
                    "kill": [{"name": "b.exe", "exe": ""}],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with patch.object(watchdog_app, "CONFIG_PATH", str(config_path)):
                watchdog_app.save_config(original)
                loaded = watchdog_app.load_config()
        self.assertEqual(loaded["watchdogs"], original["watchdogs"])
        self.assertEqual(loaded["poll_interval"], 3.0)
        self.assertEqual(loaded["grace_seconds"], 25.0)
        self.assertEqual([w["id"] for w in loaded["watchdogs"]], ["wd-1", "wd-2"])
        self.assertEqual([w["name"] for w in loaded["watchdogs"]], ["First", "Second"])
        self.assertEqual([w["enabled"] for w in loaded["watchdogs"]], [True, False])
        self.assertEqual(loaded["watchdogs"][0]["trigger"], original["watchdogs"][0]["trigger"])
        self.assertEqual(loaded["watchdogs"][0]["kill"], original["watchdogs"][0]["kill"])

    def test_save_config_output_is_valid_json(self):
        cfg = dict(watchdog_app.DEFAULT_CONFIG)
        cfg["watchdogs"] = [{"id": "x", "name": "X", "enabled": True,
                             "trigger": [{"name": "t.exe", "exe": ""}],
                             "kill": [{"name": "k.exe", "exe": ""}]}]
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            with patch.object(watchdog_app, "CONFIG_PATH", str(config_path)):
                watchdog_app.save_config(cfg)
                raw = config_path.read_text(encoding="utf-8")
            parsed = json.loads(raw)
        self.assertEqual(parsed["watchdogs"][0]["id"], "x")


if __name__ == "__main__":
    unittest.main()
