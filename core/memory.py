import chromadb
from sentence_transformers import SentenceTransformer
from pathlib import Path
import uuid
import time

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
        
        print("Initializing Memory Cortex...")
        db_path = Path(__file__).resolve().parents[1] / "data" / "vector_db"
        db_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(db_path))
        self.collection = self.client.get_or_create_collection(name="hala_ai_knowledge")
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        self._initialized = True
        print("Memory Online")

    def memorize(self, text: str, source: str = "user_chat", metadata: dict = None):
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
        self.collection.add(
            documents=[text],
            embeddings=[vector],
            metadatas=[metadata],
            ids=[str(uuid.uuid4())]
        )
        print(f"Memorized: '{text[:30]}...' from {source}")

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
                print(f"Discarded irrelevent memory: '{doc}' (Dist: {dist:.2f})")
                
        return relevant_memories
    
memory = Memory()

def memorize(text: str, source: str = "user_chat", metadata: dict = None):
    return memory.memorize(text, source=source, metadata=metadata)

def recall(query: str, n_results: int = 3):
    return memory.recall(query, n_results=n_results)
