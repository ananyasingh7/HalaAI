import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest
import uuid
from unittest.mock import patch

from data.sql import expander


class FakeDbSession:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, model, session_id):
        return self._session


class ExpanderTests(unittest.TestCase):
    def test_fetch_full_session_formats_history(self):
        session_id = uuid.uuid4()
        fake_session = type(
            "FakeSession",
            (),
            {"history": [{"role": "user", "content": "Hello"}]},
        )()

        with patch("data.sql.expander.Session", return_value=FakeDbSession(fake_session)):
            transcript = expander.fetch_full_session(str(session_id))

        self.assertIn("FULL TRANSCRIPT", transcript)
        self.assertIn("USER: Hello", transcript)

    def test_fetch_full_session_handles_missing(self):
        session_id = uuid.uuid4()
        fake_session = type("FakeSession", (), {"history": []})()

        with patch("data.sql.expander.Session", return_value=FakeDbSession(fake_session)):
            transcript = expander.fetch_full_session(str(session_id))

        self.assertIn("Session not found", transcript)


if __name__ == "__main__":
    unittest.main()
