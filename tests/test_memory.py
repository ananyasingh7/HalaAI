import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import importlib
import sys
import types
import unittest


class FakeVector:
    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


class FakeCollection:
    def __init__(self):
        self.add_calls = []

    def add(self, documents, embeddings, metadatas, ids):
        self.add_calls.append(
            {
                "documents": documents,
                "embeddings": embeddings,
                "metadatas": metadatas,
                "ids": ids,
            }
        )

    def query(self, query_embeddings, n_results, include=None):
        return {
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"source": "chat_summary"}, {"source": "other"}]],
            "ids": [["id1", "id2"]],
            "distances": [[0.5, 1.6]],
        }


class FakeClient:
    def __init__(self, path):
        self.path = path
        self.collection = FakeCollection()

    def get_or_create_collection(self, name):
        return self.collection


class FakeEmbedder:
    def encode(self, text):
        return FakeVector([float(len(text))])


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.original_chromadb = sys.modules.get("chromadb")
        self.original_sentence = sys.modules.get("sentence_transformers")

        fake_chromadb = types.SimpleNamespace(PersistentClient=FakeClient)
        fake_sentence = types.SimpleNamespace(SentenceTransformer=lambda name: FakeEmbedder())

        sys.modules["chromadb"] = fake_chromadb
        sys.modules["sentence_transformers"] = fake_sentence

        if "core.memory" in sys.modules:
            del sys.modules["core.memory"]

        self.memory_module = importlib.import_module("core.memory")

    def tearDown(self):
        if self.original_chromadb is not None:
            sys.modules["chromadb"] = self.original_chromadb
        else:
            sys.modules.pop("chromadb", None)

        if self.original_sentence is not None:
            sys.modules["sentence_transformers"] = self.original_sentence
        else:
            sys.modules.pop("sentence_transformers", None)

        sys.modules.pop("core.memory", None)

    def test_memorize_writes_metadata(self):
        memory = self.memory_module.Memory()
        doc_id = memory.memorize("hello", source="test", metadata={"foo": "bar"}, doc_id="doc-1")
        self.assertEqual(doc_id, "doc-1")

        collection = memory.collection
        self.assertEqual(len(collection.add_calls), 1)
        payload = collection.add_calls[0]
        self.assertEqual(payload["documents"], ["hello"])
        self.assertEqual(payload["ids"], ["doc-1"])
        self.assertEqual(payload["metadatas"][0]["source"], "test")
        self.assertIn("timestamp", payload["metadatas"][0])

    def test_recall_filters_by_threshold(self):
        memory = self.memory_module.Memory()
        results = memory.recall("query", n_results=2, threshold=1.0)
        self.assertEqual(results, ["doc1"])

    def test_recall_with_metadata_filters_source_and_threshold(self):
        memory = self.memory_module.Memory()
        results = memory.recall_with_metadata("query", n_results=2, threshold=1.0, source="chat_summary")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "id1")


if __name__ == "__main__":
    unittest.main()
