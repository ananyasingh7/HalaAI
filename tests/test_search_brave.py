import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from core.search import brave_search


class BraveSearchTests(unittest.IsolatedAsyncioTestCase):
    def test_period_start_and_next(self):
        today = date(2026, 1, 15)
        start = brave_search._period_start(today, billing_day=10)
        self.assertEqual(start, date(2026, 1, 10))
        next_start = brave_search._next_period_start(start, billing_day=10)
        self.assertEqual(next_start, date(2026, 2, 10))

    def test_check_quota_blocks_when_limit_reached(self):
        with tempfile.TemporaryDirectory() as tmp:
            limits = {"monthly_limit": 1, "billing_day": 1, "daily_limit_strategy": "remaining_per_day"}
            usage = {"period_start": "2026-01-01", "count": 1, "daily": {"date": "2026-01-15", "count": 1}}

            limits_path = Path(tmp) / "limits.json"
            usage_path = Path(tmp) / "usage.json"
            limits_path.write_text(json.dumps(limits))
            usage_path.write_text(json.dumps(usage))

            class FakeDate(date):
                @classmethod
                def today(cls):
                    return date(2026, 1, 15)

            with patch.object(brave_search, "LIMITS_PATH", limits_path), patch.object(
                brave_search, "USAGE_PATH", usage_path
            ), patch.object(brave_search, "date", FakeDate):
                error, payload = brave_search._check_quota()

        self.assertIsNotNone(error)
        self.assertIsNone(payload)

    def test_consume_quota_updates_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            usage_path = Path(tmp) / "usage.json"
            usage = {"period_start": "2026-01-01", "count": 0, "daily": {"date": "2026-01-15", "count": 0}}
            usage_path.write_text(json.dumps(usage))

            with patch.object(brave_search, "USAGE_PATH", usage_path):
                brave_search._consume_quota(usage)

            saved = json.loads(usage_path.read_text())
        self.assertEqual(saved["count"], 1)
        self.assertEqual(saved["daily"]["count"], 1)

    async def test_search_brave_missing_api_key(self):
        with patch.object(brave_search, "BRAVE_API_KEY", None):
            result = await brave_search.search_brave("test")
        self.assertIn("Brave API Key missing", result)


if __name__ == "__main__":
    unittest.main()
