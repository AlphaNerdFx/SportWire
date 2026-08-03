import re
import math
import inspect
import logging
import difflib
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from ingestion.schemas import NormalizedNews
from models.schemas import NewsArticle

logger = logging.getLogger("Deduplicator")

class SportsNewsDeduplicator:
    def __init__(self, repository: Any, embedding_client=None,title_threshold: float = 0.45, semantic_threshold: float = 0.85, epsilon: float = 1e-7):
        """
        :param repository: Your Sprint 1 SportsPersistenceRepository instance.
        :param title_threshold: Token Jaccard threshold to flag candidate title matches.
        :param semantic_threshold: Vector cosine similarity threshold for full confirmation.
        """
        self.repository = repository
        self.embedding_client = embedding_client
        self.title_threshold = title_threshold
        self.semantic_threshold = semantic_threshold
        self.epsilon = epsilon

    def _is_lexical_duplicate(self, incoming: NormalizedNews, existing: NormalizedNews) -> bool:
        """
        Cheap text-based similarity pass utilizing a normalized sequence alignment ratio
        to isolate highly similar text headlines before running expensive model lookups.
        """
        if not incoming.title or not existing.title:
            return False
            
        a = incoming.title.lower().strip()
        b = existing.title.lower().strip()
        
        if a == b:
            return True
            
        # SequenceMatcher handles word reordering and typos reliably across lengths
        return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8
    
    async def check_duplicate(self, incoming_article: NormalizedNews) -> tuple[bool, Optional[NormalizedNews]]:
        """
        Public deduplication gateway checking both lexical and semantic
        vectors against windowed repository items.
        """
        # Fetch articles strictly within the temporal processing window (e.g., 48 hours)
        existing_articles = await self.repository.get_articles_in_time_window(incoming_article.published_at)
    
        # ---------------------------------------------------------------------
        # PASS 1: Cheap Lexical Check (Title/Text Matching)
        # ---------------------------------------------------------------------
        # If it's a lexical duplicate, return early without requiring embeddings
        for existing in existing_articles:
            if self._is_lexical_duplicate(incoming_article, existing):
                return True, existing
    
        # ---------------------------------------------------------------------
        # PASS 2: Semantic Check (Vector Embeddings)
        # ---------------------------------------------------------------------
        # Ensure the incoming article has valid embeddings by fetching if None
        if incoming_article.embedding is None:
            # Generate embedding using the title/body via the client
            embedding_response = self.embedding_client.get_embedding(
                f"{incoming_article.title} {incoming_article.body}"
            )
            
            # Safe-guard against test fixtures/mocks that return a plain list object instead of a coroutine
            if inspect.isawaitable(embedding_response):
                incoming_article.embedding = await embedding_response
            else:
                incoming_article.embedding = embedding_response
                
        # Perform semantic vector similarity check against windowed articles
        for existing in existing_articles:
            if existing.embedding is not None:
                # Shape validation to catch model/upstream dimension shifts early
                if len(incoming_article.embedding) != len(existing.embedding):
                    raise ValueError(
                        f"Mismatched embedding dimensions: incoming={len(incoming_article.embedding)}, "
                        f"existing={len(existing.embedding)}"
                    )
                
                similarity = self._calculate_cosine_similarity(incoming_article.embedding, existing.embedding)
                
                # Extract plain scalar value from potential numpy types or lists safely
                if hasattr(similarity, "item"):
                    sim_val = similarity.item()
                elif isinstance(similarity, (list, np.ndarray)) and len(similarity) > 0:
                    sim_val = similarity[0]
                else:
                    sim_val = similarity
                
                # Apply semantic threshold with epsilon tolerance for floating-point noise
                if sim_val + self.epsilon >= self.semantic_threshold:
                    return True, existing
                    
        return False, None
    
    def is_duplicate(self, article: NewsArticle) -> bool:
        """
        Performs a semantic similarity search to check for near-duplicates.
        """
        # 1. Search for existing articles with high cosine similarity
        results = self.vector_store.similarity_search(
            query=article.title, 
            k=1, 
            filter={"source": {"$ne": article.source}} # Ensure we don't match the same article from the same source
        )

        if not results:
            return False

        # 2. Check if the match is above our threshold
        best_match = results[0]
        if best_match.score >= self.similarity_threshold:
            logger.info(f"Duplicate detected: '{article.title}' matches '{best_match.title}'")
            return True
            
        return False
    
    def _calculate_similarity(self, vec1: list, vec2: list) -> float:
        # Explicit length check to detect schema/shape shifts
        if len(vec1) != len(vec2):
            raise ValueError(
                f"Embedding shape mismatch: Cannot compute similarity between "
                f"vector of size {len(vec1)} and vector of size {len(vec2)}."
            )
        
        # Safe math operations once lengths are verified
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm_a = sum(a * a for a in vec1) ** 0.5
        norm_b = sum(b * b for b in vec2) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
            
        return dot_product / (norm_a * norm_b)
        
    def _normalize_text(self, text: str) -> str:
        """Removes punctuation, casing, and common sports news prefixes."""
        text = text.lower()
        text = re.sub(r'^(breaking|update|report|sources|just in|insider):\s*', '', text)
        return re.sub(r'[^a-z0-9\s]', '', text).strip()

    def _calculate_jaccard(self, title_a: str, title_b: str) -> float:
        """Calculates token-level Jaccard similarity between two titles."""
        set_a = set(self._normalize_text(title_a).split())
        set_b = set(self._normalize_text(title_b).split())
        
        if not set_a or not set_b:
            return 0.0
            
        intersection = len(set_a.intersection(set_b))
        union = len(set_a.union(set_b))
        return intersection / union

    def _calculate_cosine_similarity(self, vec_a: List[float], vec_b: List[float]) -> float:
        """Computes cosine similarity between two dense embedding vectors."""
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot_product = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def _calculate_jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculates token-based Jaccard similarity for title lexical matching."""
        set1 = set(text1.lower().split())
        set2 = set(text2.lower().split())
        if not set1 and not set2:
            return 1.0
        return len(set1.intersection(set2)) / len(set1.union(set2))
    
    async def find_duplicate_id(self, incoming_title: str, incoming_vector: List[float]) -> Optional[str]:
        """
        Runs the cascading lookup over articles matching a 48-hour time window.
        Returns the ID of the matched database record if it's a duplicate, else None.
        """
        # Temporal bounding: limit comparison to the last 48 hours
        time_cutoff = datetime.utcnow() - timedelta(hours=48)
        recent_articles = await self.repository.get_articles_since(time_cutoff)

        for existing in recent_articles:
            # Stage 1: Fast Lexical Title Match
            jaccard_score = self._calculate_jaccard(incoming_title, existing["title"])
            
            if jaccard_score >= self.title_threshold:
                # Stage 2: Deep Semantic Verification
                existing_vector = existing.get("embedding")
                if existing_vector:
                    similarity = self._calculate_cosine_similarity(incoming_vector, existing_vector)
                    if similarity >= self.semantic_threshold:
                        return existing["id"]
                        
        return None