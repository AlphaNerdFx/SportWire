import uuid
from typing import Any, Dict, List
from ingestion.base import BaseIngestionAdapter
from ingestion.deduplicator import SportsNewsDeduplicator

class NormalizationIngestionPipeline:
    def __init__(self, repository: Any, deduplicator: SportsNewsDeduplicator, embedding_client: Any):
        self.repository = repository
        self.deduplicator = deduplicator
        self.embedding_client = embedding_client  # Client/Service to generate vector representations

    async def ingest_news_feed(self, adapter: BaseIngestionAdapter, raw_payload: Any) -> Dict[str, int]:
        normalized_items = adapter.transform_news(raw_payload)
        saved_count = 0
        merged_count = 0

        for item in normalized_items:
            # Generate the text embedding required for RAG and deduplication checks
            vector = await self.embedding_client.generate_embedding(f"{item.title} {item.content}")
            
            # Run through our Progressive Filtering Cascade Engine
            duplicate_id = await self.deduplicator.find_duplicate_id(item.title, vector)
            
            if duplicate_id:
                # Advanced Optimization: Consolidated Merge rather than dropping entirely
                await self.repository.merge_article_metadata(
                    existing_id=duplicate_id,
                    additional_source=item.source_provider,
                    additional_url=item.url
                )
                merged_count += 1
            else:
                # Fresh, unique news asset: save full body row
                article_data = item.model_dump()
                article_data["id"] = str(uuid.uuid4())
                article_data["embedding"] = vector
                await self.repository.save_news_article(article_data)
                saved_count += 1

        return {"processed": len(normalized_items), "saved": saved_count, "merged_duplicates": merged_count}

    async def ingest_game_metrics(self, adapter: BaseIngestionAdapter, raw_payload: Any) -> int:
        normalized_games = adapter.transform_games(raw_payload)
        for game in normalized_games:
            await self.repository.save_or_update_game(game.model_dump())
        return len(normalized_games)