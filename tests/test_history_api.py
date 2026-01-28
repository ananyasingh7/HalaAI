import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import datetime as dt
import unittest
import uuid
from unittest.mock import patch

from fastapi import HTTPException

from data.service import history_api


class HistoryApiTests(unittest.TestCase):
    def test_session_to_dict(self):
        session = history_api.ChatSession(
            id=uuid.uuid4(),
            title="Hello",
            created_at=dt.datetime(2026, 1, 1),
            last_active_at=dt.datetime(2026, 1, 2),
            updated_at=dt.datetime(2026, 1, 3),
            is_active=True,
            is_summarized=False,
            summary="Sum",
            history=[{"role": "user", "content": "Hi"}],
        )
        payload = history_api._session_to_dict(session)
        self.assertEqual(payload["title"], "Hello")
        self.assertEqual(payload["summary"], "Sum")
        self.assertEqual(payload["history"], [{"role": "user", "content": "Hi"}])

    def test_remove_session_invalid_uuid(self):
        with self.assertRaises(HTTPException):
            history_api.remove_session("bad-uuid")

    def test_remove_session_not_found(self):
        with patch("data.service.history_api.delete_session", return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                history_api.remove_session("11111111-1111-1111-1111-111111111111")
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
