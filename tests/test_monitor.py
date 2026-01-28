import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest

from app.monitor import HardwareMonitor


class MonitorTests(unittest.TestCase):
    def setUp(self):
        # Avoid starting background threads by bypassing __init__.
        self.monitor = HardwareMonitor.__new__(HardwareMonitor)

    def test_coerce_float_numbers(self):
        self.assertEqual(self.monitor._coerce_float(3), 3.0)
        self.assertEqual(self.monitor._coerce_float(3.5), 3.5)

    def test_coerce_float_strings(self):
        self.assertEqual(self.monitor._coerce_float("2.5"), 2.5)
        self.assertEqual(self.monitor._coerce_float("bad"), 0.0)

    def test_coerce_float_lists(self):
        self.assertEqual(self.monitor._coerce_float([1, 2, 3]), 2.0)
        self.assertEqual(self.monitor._coerce_float([]), 0.0)

    def test_coerce_float_dicts(self):
        self.assertEqual(self.monitor._coerce_float({"value": 4}), 4.0)
        self.assertEqual(self.monitor._coerce_float({"avg": 6}), 6.0)
        self.assertEqual(self.monitor._coerce_float({"a": 2, "b": 4}), 3.0)
        self.assertEqual(self.monitor._coerce_float({}), 0.0)


if __name__ == "__main__":
    unittest.main()
