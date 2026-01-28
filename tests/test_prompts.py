import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest

from app.prompts import (
    build_system_prompt,
    format_chat_history,
    format_expanded_transcripts,
    format_search_results,
    format_session_summaries,
)


class PromptTests(unittest.TestCase):
    def test_format_search_results_with_string_error(self):
        text = format_search_results("[Error: failed]")
        self.assertIn("SEARCH STATUS", text)
        self.assertIn("Error", text)

    def test_format_search_results_empty(self):
        text = format_search_results({"query": "test", "results": []})
        self.assertIn("No relevant results", text)

    def test_format_search_results_truncates(self):
        long_content = "a" * 20
        data = {
            "query": "long",
            "results": [
                {
                    "title": "Example",
                    "url": "https://example.com",
                    "content": long_content,
                }
            ],
        }
        text = format_search_results(data, max_chars_per_result=10)
        self.assertIn("CONTENT", text)
        self.assertIn("truncated", text)

    def test_build_system_prompt_includes_context_blocks(self):
        prompt = build_system_prompt(
            memories=["User likes tea"],
            chat_history=[{"role": "user", "content": "Hello"}],
            related_summaries=[{"id": "1", "title": "Chat", "summary": "Hi"}],
            expanded_transcripts=["USER: Hi"],
            search_context="SEARCH RESULT",
        )
        self.assertIn("VERIFIED USER PROFILE", prompt)
        self.assertIn("CURRENT DIALOGUE CONTEXT", prompt)
        self.assertIn("RELATED PAST CONVERSATIONS", prompt)
        self.assertIn("PAST CONVERSATION TRANSCRIPTS", prompt)
        self.assertIn("SEARCH RESULT", prompt)

    def test_format_chat_history_limits_messages(self):
        history = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        text = format_chat_history(history, max_messages=2)
        self.assertNotIn("a", text)
        self.assertIn("b", text)
        self.assertIn("c", text)

    def test_format_session_summaries(self):
        text = format_session_summaries([{"id": "abc", "title": "Title", "summary": "Sum"}])
        self.assertIn("SESSION abc", text)
        self.assertIn("Sum", text)
        self.assertIn("EXPAND", text)

    def test_format_expanded_transcripts(self):
        text = format_expanded_transcripts(["USER: Hi", "ASSISTANT: Hey"])
        self.assertIn("PAST CONVERSATION TRANSCRIPTS", text)
        self.assertIn("USER: Hi", text)


if __name__ == "__main__":
    unittest.main()
