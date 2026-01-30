import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sys
import types
import unittest
from unittest.mock import patch

from core.search import browser


class BrowserTests(unittest.TestCase):
    def test_visit_page_with_trafilatura(self):
        fake_trafilatura = types.SimpleNamespace(
            fetch_url=lambda url: "<html>hi</html>",
            extract=lambda html, include_comments=False, include_tables=True, no_fallback=False: "content",
        )
        sys.modules["trafilatura"] = fake_trafilatura

        with patch("core.search.browser.requests.get") as requests_get:
            text = browser.visit_page("https://example.com", max_chars=10, include_header=False)
            requests_get.assert_not_called()

        self.assertEqual(text, "content")
        sys.modules.pop("trafilatura", None)

    def test_visit_page_fallback_to_requests(self):
        fake_trafilatura = types.SimpleNamespace(
            fetch_url=lambda url: None,
            extract=lambda html, include_comments=False, include_tables=True, no_fallback=False: "fallback",
        )
        sys.modules["trafilatura"] = fake_trafilatura

        class FakeResponse:
            status_code = 200
            text = "<html>fallback</html>"

        with patch("core.search.browser.requests.get", return_value=FakeResponse()):
            text = browser.visit_page("https://example.com", max_chars=10, include_header=False)

        self.assertEqual(text, "fallback")
        sys.modules.pop("trafilatura", None)

    def test_visit_page_no_text(self):
        fake_trafilatura = types.SimpleNamespace(
            fetch_url=lambda url: "<html>hi</html>",
            extract=lambda *args, **kwargs: None,
        )
        sys.modules["trafilatura"] = fake_trafilatura

        text = browser.visit_page("https://example.com", max_chars=10, include_header=False)
        self.assertIn("no readable text", text)
        sys.modules.pop("trafilatura", None)


if __name__ == "__main__":
    unittest.main()
