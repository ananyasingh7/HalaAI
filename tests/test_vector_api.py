import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sys
import types
import unittest
from unittest.mock import Mock


fake_memory = types.SimpleNamespace(
    memory=types.SimpleNamespace(recall_with_metadata=Mock(return_value=[{"id": "1"}]))
)
_original_core_memory = sys.modules.get("core.memory")
sys.modules["core.memory"] = fake_memory

from data.service import vector_api


class VectorApiTests(unittest.TestCase):
    def test_vector_search_returns_results(self):
        payload = vector_api.VectorQueryRequest(query="test")
        result = vector_api.vector_search(payload)
        self.assertEqual(result["query"], "test")
        self.assertEqual(result["results"], [{"id": "1"}])


def tearDownModule():
    if _original_core_memory is not None:
        sys.modules["core.memory"] = _original_core_memory
    else:
        sys.modules.pop("core.memory", None)


if __name__ == "__main__":
    unittest.main()
