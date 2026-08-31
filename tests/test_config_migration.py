import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import watchdog_core as watchdog_app


class LoadConfigMigrationTests(unittest.TestCase):
    def test_loads_legacy_rules_as_watchdogs_without_losing_data(self):
        legacy_config = {
            "poll_interval": 2.0,
            "grace_seconds": 10.0,
            "rules": [
                {
                    "id": "legacy-id",
                    "name": "Legacy App",
                    "enabled": False,
                    "trigger": ["legacy.exe"],
                    "kill": [
                        {
                            "name": "helper.exe",
                            "exe": r"C:\Apps\Legacy\helper.exe",
                        }
                    ],
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps(legacy_config), encoding="utf-8")

            with patch.object(watchdog_app, "CONFIG_PATH", str(config_path)):
                loaded = watchdog_app.load_config()

        self.assertEqual(
            loaded["watchdogs"],
            [
                {
                    "id": "legacy-id",
                    "name": "Legacy App",
                    "enabled": False,
                    "watched_app": {"name": "legacy.exe", "exe": ""},
                    "meal_targets": [
                        {
                            "name": "helper.exe",
                            "exe": r"C:\Apps\Legacy\helper.exe",
                        }
                    ],
                }
            ],
        )

    def _load(self, content):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps(content), encoding="utf-8")
            with patch.object(watchdog_app, "CONFIG_PATH", str(config_path)):
                return watchdog_app.load_config()["watchdogs"]

    def test_single_distinct_trigger_promotes_to_watched_app(self):
        watchdog = {
            "id": "wd1", "name": "WD", "enabled": True,
            "trigger": [{"name": "app.exe", "exe": r"C:\Apps\App\app.exe"}],
            "kill": [{"name": "app.exe", "exe": r"C:\Apps\App\app.exe"},
                     {"name": "helper.exe", "exe": r"C:\Apps\App\helper.exe"}],
        }
        result = self._load({"watchdogs": [watchdog]})[0]
        # The single trigger becomes the watched app...
        self.assertEqual(result["watched_app"], {"name": "app.exe", "exe": r"C:\Apps\App\app.exe"})
        # ...and it is removed from meal_targets (never duplicated).
        self.assertEqual(result["meal_targets"], [{"name": "helper.exe", "exe": r"C:\Apps\App\helper.exe"}])
        self.assertNotIn("trigger", result)
        self.assertNotIn("kill", result)

    def test_zero_distinct_trigger_yields_null_watched_app_and_unchanged_meal(self):
        watchdog = {
            "id": "wd1", "name": "WD", "enabled": True,
            "trigger": [],
            "kill": [{"name": "helper.exe", "exe": ""}],
        }
        result = self._load({"watchdogs": [watchdog]})[0]
        self.assertIsNone(result["watched_app"])
        self.assertEqual(result["meal_targets"], [{"name": "helper.exe", "exe": ""}])

    def test_multiple_distinct_trigger_yields_null_watched_app_and_combined_meal(self):
        watchdog = {
            "id": "wd1", "name": "WD", "enabled": True,
            "trigger": [{"name": "a.exe", "exe": ""}, {"name": "b.exe", "exe": ""}],
            "kill": [{"name": "b.exe", "exe": ""}, {"name": "c.exe", "exe": ""}],
        }
        result = self._load({"watchdogs": [watchdog]})[0]
        self.assertIsNone(result["watched_app"])
        # Ambiguous trigger becomes part of the leftovers (deduped with kill).
        self.assertEqual(
            sorted(e["name"] for e in result["meal_targets"]),
            ["a.exe", "b.exe", "c.exe"],
        )

    def test_meal_targets_never_duplicate_watched_app(self):
        # Already-migrated config: meal_targets lists the watched app too.
        watchdog = {
            "id": "wd1", "name": "WD", "enabled": True,
            "watched_app": {"name": "app.exe", "exe": r"C:\Apps\App\app.exe"},
            "meal_targets": [{"name": "app.exe", "exe": r"C:\Apps\App\app.exe"},
                             {"name": "helper.exe", "exe": ""}],
        }
        result = self._load({"watchdogs": [watchdog]})[0]
        self.assertEqual(result["watched_app"], {"name": "app.exe", "exe": r"C:\Apps\App\app.exe"})
        self.assertEqual(result["meal_targets"], [{"name": "helper.exe", "exe": ""}])

    def test_already_migrated_config_passes_through(self):
        watchdog = {
            "id": "wd1", "name": "WD", "enabled": True,
            "watched_app": {"name": "app.exe", "exe": ""},
            "meal_targets": [{"name": "helper.exe", "exe": ""}],
        }
        result = self._load({"watchdogs": [watchdog]})[0]
        self.assertEqual(result["watched_app"], {"name": "app.exe", "exe": ""})
        self.assertEqual(result["meal_targets"], [{"name": "helper.exe", "exe": ""}])
        self.assertNotIn("trigger", result)
        self.assertNotIn("kill", result)


if __name__ == "__main__":
    unittest.main()
