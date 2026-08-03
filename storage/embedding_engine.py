# storage/embedding_engine.py
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from storage.config import StorageConfig

class LocalEmbeddingEngine:
    def __init__(self):
        # Lazy initialization so the model loads into memory only when invoked
        self._model = None

    @property
    def model(self):
        if self._model is None:
            # Dynamically pulls 'all-MiniLM-L6-v2' as defined in your config
            self._model = SentenceTransformer(StorageConfig.MODEL_NAME)
        return self._model

    def _chunk_text_by_chars(self, text: str) -> List[str]:
        """
        Splits sports logs/articles based on character sizes, ensuring paragraphs 
        or sentences share structural overlap between chunks.
        """
        chunks = []
        start = 0
        text_len = len(text)
        
        if text_len == 0:
            return chunks

        while start < text_len:
            end = start + StorageConfig.CHUNK_SIZE
            chunk = text[start:end]
            chunks.append(chunk)
            
            # Slide window forward minus the overlap parameter
            start += (StorageConfig.CHUNK_SIZE - StorageConfig.CHUNK_OVERLAP)
            
            # Absolute break guard if the step ceases to progress
            if StorageConfig.CHUNK_SIZE <= StorageConfig.CHUNK_OVERLAP:
                break
                
        return chunks

    async def process_document(self, content: str) -> List[Dict[str, Any]]:
        """
        Public contract consumed by your repository layout.
        Chunks input text and evaluates vectors locally on your system hardware.
        """
        text_chunks = self._chunk_text_by_chars(content)
        processed_data = []

        if not text_chunks:
            return processed_data

        # Generate structural embeddings locally via sentence-transformers
        # running synchronously inside an async context wrapper is fine for basic threads,
        # or can be moved to an executor loop if handling high parallel traffic.
        embeddings = self.model.encode(text_chunks)

        for index, (text, vector) in enumerate(zip(text_chunks, embeddings)):
            processed_data.append({
                "index": index,
                "text": text,
                "vector": vector.tolist() # Coerces numpy float arrays into native python float lists
            })

        return processed_data

# Instantiated globally for singleton tracking across workers
embedding_engine = LocalEmbeddingEngine()