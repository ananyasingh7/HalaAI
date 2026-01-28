import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest
from unittest.mock import patch

import app.logging_setup as logging_setup


class LoggingSetupTests(unittest.TestCase):
    def setUp(self):
        logging_setup._CONFIGURED = False

    def test_setup_logging_is_idempotent(self):
        with patch("app.logging_setup.logging.config.fileConfig") as file_config:
            logging_setup.setup_logging()
            logging_setup.setup_logging()

        self.assertEqual(file_config.call_count, 1)
        self.assertTrue(logging_setup._CONFIGURED)


if __name__ == "__main__":
    unittest.main()
