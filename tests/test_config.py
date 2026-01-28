import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
import tempfile
import unittest

from app import config as config_module


class ConfigTests(unittest.TestCase):
    def test_load_config_defaults_when_missing(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                settings = config_module.load_config()
            finally:
                os.chdir(cwd)

        self.assertEqual(settings.queue.max_size, 100)
        self.assertTrue(settings.queue.starvation_prevention)
        self.assertEqual(settings.queue.aging_interval_sec, 60)
        self.assertEqual(settings.queue.default_priority, 10)
        self.assertEqual(settings.priorities.ui, 0)
        self.assertEqual(settings.priorities.critical, 1)
        self.assertEqual(settings.priorities.standard, 10)
        self.assertEqual(settings.priorities.background, 20)

    def test_load_config_from_yaml(self):
        settings_yaml = """
queue:
  max_size: 5
  starvation_prevention: false
  aging_interval_sec: 30
  default_priority: 7
priorities:
  ui: 0
  critical: 2
  standard: 11
  background: 42
"""
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with open("settings.yaml", "w", encoding="utf-8") as handle:
                    handle.write(settings_yaml)
                settings = config_module.load_config()
            finally:
                os.chdir(cwd)

        self.assertEqual(settings.queue.max_size, 5)
        self.assertFalse(settings.queue.starvation_prevention)
        self.assertEqual(settings.queue.aging_interval_sec, 30)
        self.assertEqual(settings.queue.default_priority, 7)
        self.assertEqual(settings.priorities.critical, 2)
        self.assertEqual(settings.priorities.standard, 11)
        self.assertEqual(settings.priorities.background, 42)


if __name__ == "__main__":
    unittest.main()
