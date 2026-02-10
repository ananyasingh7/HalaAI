import logging
import time
import uuid
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

from app.config import settings
from app.logging_setup import setup_logging


class Memory:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Memory, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        setup_logging()
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing Memory Cortex...")
        db_path = Path(__file__).resolve().parents[1] / "data" / "vector_db"
        db_path.mkdir(parents=True, exist_ok=True)
        self.client = self._create_persistent_client(str(db_path))
        self.collection = self.client.get_or_create_collection(name="hala_ai_knowledge")
        self.embedder = SentenceTransformer("all-MiniLM-L6-v2")
        self._initialized = True
        self.logger.info("Memory Online")

    def _build_chroma_settings(self):
        cfg = settings.chroma_memory
        memory_limit = int(cfg.memory_limit_bytes or 0)
        if memory_limit <= 0:
            return None

        try:
            from chromadb.config import Settings as ChromaSettings
        except Exception:
            self.logger.warning("Could not import chromadb.config.Settings; skipping memory cap settings.")
            return None

        policy = (cfg.segment_cache_policy or "").strip().upper()
        if policy and policy != "LRU":
            self.logger.warning("Unsupported Chroma cache policy '%s'; forcing LRU.", policy)
        policy = "LRU"

        self.logger.info(
            "Applying Chroma memory cap: policy=%s, limit=%.1fMB",
            policy,
            memory_limit / (1024 * 1024),
        )
        return ChromaSettings(
            chroma_segment_cache_policy=policy,
            chroma_memory_limit_bytes=memory_limit,
        )

    def _create_persistent_client(self, db_path: str):
        chroma_settings = self._build_chroma_settings()
        if chroma_settings is None:
            return chromadb.PersistentClient(path=db_path)

        try:
            return chromadb.PersistentClient(path=db_path, settings=chroma_settings)
        except TypeError:
            self.logger.warning(
                "PersistentClient(settings=...) unsupported in this Chroma runtime; falling back to defaults."
            )
            return chromadb.PersistentClient(path=db_path)

    def memorize(self, text: str, source: str = "user_chat", metadata: dict = None, doc_id: str | None = None) -> str:
        """
        Saves a piece of text into long-term storage
        """
        if metadata is None:
            metadata = {}

        metadata["source"] = source
        metadata["timestamp"] = time.time()

        # Vectorize
        vector = self.embedder.encode(text).tolist()

        # Save
        doc_id = doc_id or str(uuid.uuid4())
        self.collection.add(
            documents=[text],
            embeddings=[vector],
            metadatas=[metadata],
            ids=[doc_id]
        )
        self.logger.info("Memorized: '%s...' from %s", text[:30], source)
        return doc_id

    def recall(self, query: str, n_results: int = 3, threshold: float = 1.2):
        """
        Threshold: 
        - Lower is STRICTER (closer distance).
        - 0.0 = Identical text.
        - 1.5 = Vaguely related.
        - ChromaDB uses L2 distance by default. A generic 'good' cutoff is often ~1.0 - 1.3
        """
        query_vec = self.embedder.encode(query).tolist()
        
        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=n_results
        )
        
        documents = results['documents'][0]
        distances = results['distances'][0]
        
        relevant_memories = []
        
        for doc, dist in zip(documents, distances):
            # If distance is too high (too far away), ignore it.
            if dist < threshold:
                relevant_memories.append(doc)
            else:
                self.logger.info("Discarded irrelevent memory: '%s' (Dist: %.2f)", doc, dist)
                
        return relevant_memories

    def recall_with_metadata(
        self,
        query: str,
        n_results: int = 5,
        threshold: float | None = None,
        source: str | None = None,
    ) -> list[dict]:
        query_vec = self.embedder.encode(query).tolist()

        results = self.collection.query(
            query_embeddings=[query_vec],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        output = []
        for doc, meta, doc_id, dist in zip(documents, metadatas, ids, distances):
            if source and (meta or {}).get("source") != source:
                continue
            if threshold is not None and dist >= threshold:
                continue
            output.append(
                {
                    "id": doc_id,
                    "document": doc,
                    "metadata": meta or {},
                    "distance": dist,
                }
            )
        return output
    
memory = Memory()

def memorize(text: str, source: str = "user_chat", metadata: dict = None, doc_id: str | None = None):
    return memory.memorize(text, source=source, metadata=metadata, doc_id=doc_id)

def recall(query: str, n_results: int = 3):
    return memory.recall(query, n_results=n_results)


def recall_with_metadata(
    query: str,
    n_results: int = 5,
    threshold: float | None = None,
    source: str | None = None,
):
    return memory.recall_with_metadata(
        query, n_results=n_results, threshold=threshold, source=source
    )
