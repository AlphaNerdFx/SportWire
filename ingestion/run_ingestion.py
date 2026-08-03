import asyncio
import logging
from ingestion.scheduler import ConcurrentPollingEngine
from ingestion.normalizer import NormalizationIngestionPipeline
from ingestion.deduplicator import SportsNewsDeduplicator
from ingestion.adapters.nba_api_adapter import NbaApiAdapter
from ingestion.adapters.apify_news_adapter import ApifyNewsAdapter

# Setup standard logger outputs
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Mock Client targets to simulate external retrievals
async def mock_fetch_nba_scores():
    # Simulates active scoring checks
    return {"scoreboard": {"games": []}}

async def mock_fetch_espn_apify():
    # Simulates an active Apify scraper execution payload
    return [{"id": "trade_99", "title": "Lakers acquire depth piece", "content": "Full text body details...", "publishedAt": "2026-03-30T12:00:00Z"}]

async def main():
    # 1. Instantiate persistence layer repository from Sprint 1 (Mocked placeholder here)
    class MockRepo:
        async def get_articles_since(self, cutoff): return []
        async def save_news_article(self, data): return True
        async def save_or_update_game(self, data): return True
    
    class MockEmbedding:
        async def generate_embedding(self, text): return [0.1] * 1536

    repository = MockRepo()
    embedding_client = MockEmbedding()

    # 2. Wire up deduplication and normalization pipelines
    deduplicator = SportsNewsDeduplicator(repository=repository)
    pipeline = NormalizationIngestionPipeline(repository, deduplicator, embedding_client)

    # 3. Setup the orchestration engine
    scheduler_engine = ConcurrentPollingEngine(pipeline=pipeline)

    # 4. Declare your independent collection workers
    active_sources = [
        {
            "name": "NBA_Live_Scores",
            "interval": 30,  # Live box-scores update every 30 seconds
            "fetch_function": mock_fetch_nba_scores,
            "adapter": NbaApiAdapter(),
            "is_news": False
        },
        {
            "name": "Apify_ESPN_NBA_News",
            "interval": 300,  # Scraping queries news feeds every 5 minutes
            "fetch_function": mock_fetch_espn_apify,
            "adapter": ApifyNewsAdapter(provider_tag="ESPN_NBA"),
            "is_news": True
        }
    ]

    # Start the continuous asynchronous collection loop
    scheduler_engine.start(active_sources)

    try:
        # Keep the application context running alive
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        await scheduler_engine.stop()

if __name__ == "__main__":
    asyncio.run(main())