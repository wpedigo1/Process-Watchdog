import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import watchdog_app


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
                    "trigger": [{"name": "legacy.exe", "exe": ""}],
                    "kill": [
                        {
                            "name": "helper.exe",
                            "exe": r"C:\Apps\Legacy\helper.exe",
                        }
                    ],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
