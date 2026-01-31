import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import unittest

from app import search_probe


class SearchProbeTests(unittest.TestCase):
    def test_should_probe_for_recency_terms(self):
        self.assertTrue(search_probe.should_probe_search("What is the S&P 500 today?"))
        self.assertTrue(search_probe.should_probe_search("Latest earnings update for Apple"))
        self.assertTrue(search_probe.should_probe_search("Weather forecast for NYC"))

    def test_should_probe_for_explicit_browse(self):
        self.assertTrue(search_probe.should_probe_search("Search for the NFL standings"))
        self.assertTrue(search_probe.should_probe_search("Look up the score"))
        self.assertTrue(search_probe.should_probe_search("[SEARCH: bitcoin price]"))

    def test_should_probe_for_year(self):
        self.assertTrue(search_probe.should_probe_search("S&P 500 close on 2025-12-31"))

    def test_should_not_probe_for_timeless(self):
        self.assertFalse(search_probe.should_probe_search("Who is Elon Musk?"))
        self.assertFalse(search_probe.should_probe_search("Explain gravity in simple terms."))


if __name__ == "__main__":
    unittest.main()
