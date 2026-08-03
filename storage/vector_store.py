import abc
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import numpy as np

@dataclass
class VectorDocument:
    id: str
    text: str
    embedding: List[float]
    metadata: Dict[str, Any]

class BaseVectorStore(abc.ABC):
    @abc.abstractmethod
    async def upsert_articles(self, documents: List[VectorDocument]) -> None:
        """Persist a batch of documents and their corresponding vector embeddings."""
        pass

    @abc.abstractmethod
    async def query_similar(
        self, 
        query_embedding: List[float], 
        top_k: int = 5, 
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve context matches filtered by attributes (e.g., sport='NBA')."""
        pass


# Production-grade Implementation using ChromaDB (or alternative local vector runtime)
import chromadb
from chromadb.config import Settings

class ChromaSportsVectorStore(BaseVectorStore):
    def __init__(self, persist_directory: str = "./data/chroma_db"):
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False, allow_reset=True)
        )
        # Create or fetch our target collections
        self.collection = self.client.get_or_create_collection(
            name="openclaw_sports_news",
            metadata={"hnsw:space": "cosine"} # Exact match to our deduplicator metric space
        )

    async def upsert_articles(self, documents: List[VectorDocument]) -> None:
        if not documents:
            return

        ids = [doc.id for doc in documents]
        documents_text = [doc.text for doc in documents]
        embeddings = [doc.embedding for doc in documents]
        metadatas = [doc.metadata for doc in documents]

        # Sync wrapper execution for Chroma's underlying native bindings
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents_text,
            metadatas=metadatas
        )

    async def query_similar(
        self, 
        query_embedding: List[float], 
        top_k: int = 5, 
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        
        # Format filters to ChromaDB syntax format if provided
        where_clause = filters if filters else None

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause
        )

        formatted_results = []
        if results and results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                formatted_results.append({
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i] if results["distances"] else None
                })
        return formatted_results