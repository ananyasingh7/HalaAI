import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest
from unittest.mock import patch

from core.search import brave_browse


class BraveBrowseTests(unittest.IsolatedAsyncioTestCase):
    def test_prioritize_wikipedia(self):
        results = [
            {"url": "https://example.com"},
            {"url": "https://en.wikipedia.org/wiki/Test"},
        ]
        ordered = brave_browse._prioritize_wikipedia(results)
        self.assertIn("wikipedia.org", ordered[0]["url"])

    def test_is_error_content(self):
        self.assertTrue(brave_browse._is_error_content("[Error: bad]"))
        self.assertTrue(brave_browse._is_error_content("[Browser Error: bad]"))
        self.assertFalse(brave_browse._is_error_content("ok"))

    def test_sanitize_result(self):
        item = {"title": "T", "url": "U", "description": "D", "extra_snippets": ["x"], "page_age": "1d"}
        sanitized = brave_browse._sanitize_result(item)
        self.assertEqual(sanitized["title"], "T")
        self.assertEqual(sanitized["url"], "U")
        self.assertEqual(sanitized["extra_snippets"], ["x"])

    async def test_fetch_content_sets_content(self):
        item = {"url": "https://example.com"}
        with patch("core.search.brave_browse.visit_page", return_value="hello"):
            await brave_browse._fetch_content(item, max_chars=10)
        self.assertEqual(item.get("content"), "hello")

    async def test_search_and_browse_missing_api_key(self):
        with patch.object(brave_browse, "BRAVE_API_KEY", None):
            result = await brave_browse.search_and_browse("test")
        self.assertIn("Brave API Key missing", result)


if __name__ == "__main__":
    unittest.main()
