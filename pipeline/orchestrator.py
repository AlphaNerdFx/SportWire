import asyncio
import logging
import uuid
from typing import List, Dict, Any, Callable, Awaitable, Optional
from datetime import datetime, timezone

from ingestion.deduplicator import SportsNewsDeduplicator
from tests.conftest import  NewsArticle
from storage.vector_store import BaseVectorStore, VectorDocument

logger = logging.getLogger("OpenClaw.PipelineOrchestrator")

class IngestionPipelineOrchestrator:
    def __init__(
        self,
        deduplicator: SportsNewsDeduplicator,
        vector_store: BaseVectorStore,
        embedding_client: Any
    ):
        self.deduplicator = deduplicator
        self.vector_store = vector_store
        self.embedding_client = embedding_client
        self.registry: List[Callable[[], Awaitable[List[Dict[str, Any]]]]] = []

    def register_source(self, fetch_coroutine: Callable[[], Awaitable[List[Dict[str, Any]]]]):
        """Registers an asynchronous source scraper fetcher callback function."""
        self.registry.append(fetch_coroutine)

    async def run_cycle(self) -> Dict[str, int]:
        """Runs one full concurrent polling iteration across all registered providers."""
        logger.info("Starting OpenClaw global ingestion synchronization cycle.")

        # Step 1: Execute concurrent scraping/API tasks safely
        tasks = [asyncio.create_task(source()) for source in self.registry]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        raw_pulled_items: List[Dict[str, Any]] = []
        for index, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Source registry execution index {index} failed critically: {str(result)}")
            elif result:
                raw_pulled_items.extend(result)

        # Initialize metrics tracking
        metrics = {"total_fetched": len(raw_pulled_items), "saved": 0, "duplicates_dropped": 0}

        # Step 2: Normalize and Process individual payloads
        for raw_item in raw_pulled_items:
            try:
                print(f"\n--- Processing: {raw_item.get('title')} ---")
                
                # Rule 1: Always normalize immediately into NewsArticle model first
                article = NewsArticle.model_validate(raw_item)
                print(f"-> [SUCCESS] Normalized to NewsArticle object.")
                
                # Rule 2: Check for semantic/exact duplication
                is_dup_res = await self.deduplicator.check_duplicate(article)
                print(f"-> Deduplicator returned: raw_result = {is_dup_res}")
                
                # Safely extract boolean if deduplicator returns a tuple (is_duplicate, reason)
                is_dup = is_dup_res[0] if isinstance(is_dup_res, tuple) else is_dup_res
                
                if is_dup:
                    metrics["duplicates_dropped"] += 1
                    logger.info(f"Duplicate article dropped: {article.title}")
                    print(f"-> [DROPPED] Duplicate detected.")
                    continue
                
                # Rule 3: Persist unique articles to vector database
                await self.vector_store.add_article(article)
                print("-> [SUCCESS] Saved to Vector DB!")
                metrics["saved"] += 1
                
            except Exception as e:
                print(f"-> [ERROR] Failed during loop execution: {str(e)}")
                logger.error(f"Failed to process raw item pipeline flow: {str(e)}")
                continue

        return metrics

    async def _normalize_item(self, raw: Dict[str, Any]) -> Optional[NewsArticle]:
        """
        Data Normalization Layer: Coerces dirty API payloads/scrapes into clean schema definition items.
        """
        title = raw.get("title") or raw.get("headline")
        content = raw.get("content") or raw.get("body") or raw.get("description")
        
        if not title or not content:
            return None

        # Build vectors on demand if not pre-populated by incoming scraping system context
        embedding = raw.get("embedding")
        if not embedding:
            # Reuses verified async guard mechanism from deduplicator updates
            res = self.embedding_client.get_embedding(f"{title} {content}")
            embedding = await res if asyncio.iscoroutine(res) else res

        return NewsArticle(
            title=title.strip(),
            content=content.strip(),
            embedding=embedding
        )