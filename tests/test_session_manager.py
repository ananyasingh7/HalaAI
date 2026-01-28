import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio
import sys
import types
import unittest
from unittest.mock import Mock, patch


# Stub core.memory before importing session_manager to avoid heavy deps.
fake_memory = types.SimpleNamespace(memorize=Mock())
_ORIGINAL_CORE_MEMORY = sys.modules.get("core.memory")
sys.modules["core.memory"] = fake_memory

from app import session_manager


class SessionManagerHelpersTests(unittest.TestCase):
    def test_parse_json_payload(self):
        payload = session_manager._parse_json_payload("prefix {\"title\": \"Hi\"} suffix")
        self.assertEqual(payload, {"title": "Hi"})
        self.assertIsNone(session_manager._parse_json_payload("no json"))

    def test_format_transcript(self):
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        text = session_manager._format_transcript(history)
        self.assertIn("USER: Hello", text)
        self.assertIn("ASSISTANT: Hi", text)

    def test_parse_summary_response_json(self):
        title, summary = session_manager._parse_summary_response('{"title": "T", "summary": "S"}')
        self.assertEqual(title, "T")
        self.assertEqual(summary, "S")

    def test_parse_summary_response_fallback(self):
        title, summary = session_manager._parse_summary_response("Title\nLine two")
        self.assertEqual(title, "Title")
        self.assertIn("Line two", summary)


class SessionManagerAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fake_memory.memorize.reset_mock()

    async def test_ensure_session_invalid_uuid(self):
        result = await session_manager.ensure_session("not-a-uuid")
        self.assertIsNone(result)

    async def test_ensure_session_calls_create(self):
        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch("app.session_manager.create_session") as create_session, patch(
            "asyncio.to_thread", new=fake_to_thread
        ):
            create_session.return_value = object()
            result = await session_manager.ensure_session("11111111-1111-1111-1111-111111111111")

        self.assertIsNotNone(result)
        create_session.assert_called_once()

    async def test_summarise_session_updates_summary_and_memory(self):
        class FakeEngine:
            async def generate_stream(self, request):
                yield '{"title": "Summary", "summary": "Done"}'

        class FakeSession:
            def __init__(self):
                self.history = [{"role": "user", "content": "Hello"}]
                self.is_summarized = False

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch("app.session_manager.get_session", return_value=FakeSession()), patch(
            "app.session_manager.update_session_summary"
        ) as update_summary, patch("asyncio.to_thread", new=fake_to_thread):
            await session_manager.summarise_session(
                session_id=session_manager.uuid.uuid4(),
                engine=FakeEngine(),
            )

        update_summary.assert_called_once()
        fake_memory.memorize.assert_called_once()

    async def test_summarise_session_empty_history(self):
        class FakeEngine:
            async def generate_stream(self, request):
                if False:
                    yield None

        class FakeSession:
            def __init__(self):
                self.history = []
                self.is_summarized = False

        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        with patch("app.session_manager.get_session", return_value=FakeSession()), patch(
            "app.session_manager.update_session_summary"
        ) as update_summary, patch("asyncio.to_thread", new=fake_to_thread):
            await session_manager.summarise_session(
                session_id=session_manager.uuid.uuid4(),
                engine=FakeEngine(),
            )

        update_summary.assert_called_once()
        fake_memory.memorize.assert_not_called()

    async def test_sweep_stale_sessions_calls_summarise(self):
        async def fake_to_thread(func, *args, **kwargs):
            return func(*args, **kwargs)

        fake_session = types.SimpleNamespace(id=session_manager.uuid.uuid4())

        with patch(
            "app.session_manager.list_active_sessions_older_than", return_value=[fake_session]
        ), patch("app.session_manager.summarise_session") as summarise_session, patch(
            "asyncio.to_thread", new=fake_to_thread
        ):
            engine = object()
            await session_manager.sweep_stale_sessions(engine=engine, idle_seconds=1)

        summarise_session.assert_called_once_with(fake_session.id, engine)


def tearDownModule():
    if _ORIGINAL_CORE_MEMORY is not None:
        sys.modules["core.memory"] = _ORIGINAL_CORE_MEMORY
    else:
        sys.modules.pop("core.memory", None)


if __name__ == "__main__":
    unittest.main()
