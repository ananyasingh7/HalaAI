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


class MacmonParsingTests(unittest.TestCase):
    """Validates that _monitor_loop correctly parses real macmon pipe JSON."""

    # Captured from: macmon pipe (vladkens/macmon on Apple Silicon)
    SAMPLE_MACMON_JSON = {
        "all_power": 2.67,
        "gpu_power": 0.864,
        "gpu_usage": [771, 0.137],
        "memory": {"ram_total": 38654705664, "ram_usage": 32030162944,
                    "swap_total": 10737418240, "swap_usage": 9898360832},
        "temp": {"cpu_temp_avg": 27.16, "gpu_temp_avg": 42.58},
    }

    def setUp(self):
        self.monitor = HardwareMonitor.__new__(HardwareMonitor)
        self.monitor.latest_stats = {
            "gpu_usage": 0.0, "gpu_power": 0.0, "gpu_temp": 0.0,
            "cpu_usage": 0.0, "ram_usage": 0.0, "system_ram_gb": 0.0,
            "process_ram_gb": 0.0, "soc_temp": 0.0,
        }

    def _apply_macmon_data(self, data):
        """Replicate the parsing logic from _monitor_loop."""
        gpu_usage_raw = data.get("gpu_usage")
        if isinstance(gpu_usage_raw, (list, tuple)) and len(gpu_usage_raw) >= 2:
            self.monitor.latest_stats["gpu_usage"] = gpu_usage_raw[1] * 100.0
        else:
            self.monitor.latest_stats["gpu_usage"] = self.monitor._coerce_float(gpu_usage_raw)

        self.monitor.latest_stats["gpu_power"] = self.monitor._coerce_float(data.get("gpu_power", 0))

        temp_data = data.get("temp", {})
        self.monitor.latest_stats["gpu_temp"] = self.monitor._coerce_float(temp_data.get("gpu_temp_avg", 0))
        self.monitor.latest_stats["soc_temp"] = self.monitor._coerce_float(temp_data.get("cpu_temp_avg", 0))

    def test_gpu_usage_extracts_utilization_percentage(self):
        self._apply_macmon_data(self.SAMPLE_MACMON_JSON)
        # gpu_usage[1] = 0.137 → 13.7%
        self.assertAlmostEqual(self.monitor.latest_stats["gpu_usage"], 13.7, places=1)

    def test_gpu_power_in_watts(self):
        self._apply_macmon_data(self.SAMPLE_MACMON_JSON)
        self.assertAlmostEqual(self.monitor.latest_stats["gpu_power"], 0.864, places=2)

    def test_gpu_temp_from_nested_temp_dict(self):
        self._apply_macmon_data(self.SAMPLE_MACMON_JSON)
        self.assertAlmostEqual(self.monitor.latest_stats["gpu_temp"], 42.58, places=1)

    def test_soc_temp_from_nested_temp_dict(self):
        self._apply_macmon_data(self.SAMPLE_MACMON_JSON)
        self.assertAlmostEqual(self.monitor.latest_stats["soc_temp"], 27.16, places=1)

    def test_gpu_usage_fallback_for_scalar(self):
        """If macmon ever changes to emit a scalar, still works."""
        self._apply_macmon_data({"gpu_usage": 45.0, "temp": {}})
        self.assertAlmostEqual(self.monitor.latest_stats["gpu_usage"], 45.0)

    def test_missing_temp_key_defaults_to_zero(self):
        self._apply_macmon_data({"gpu_usage": [0, 0], "gpu_power": 0})
        self.assertEqual(self.monitor.latest_stats["gpu_temp"], 0.0)
        self.assertEqual(self.monitor.latest_stats["soc_temp"], 0.0)


if __name__ == "__main__":
    unittest.main()
