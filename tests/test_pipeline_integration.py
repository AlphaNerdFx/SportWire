import pytest
import asyncio
from pipeline.orchestrator import IngestionPipelineOrchestrator
from storage.vector_store import BaseVectorStore, VectorDocument
from ingestion.deduplicator import SportsNewsDeduplicator
from typing import List, Dict, Any
from tests.conftest import NewsArticle

class MockEmbeddingClient:
    async def get_embedding(self, text: str) -> list[float]:
        import random
        
        # 1. Save current random state to avoid side-effects in other tests
        state = random.getstate()
        
        # 2. Seed randomly using a deterministic integer unique to the text string
        # (summing ord() guarantees the same text always yields the same vector)
        string_seed = sum(ord(char) for char in text)
        random.seed(string_seed)
        
        # 3. Create a vector of the matching dimension (e.g., 128 dimensions)
        vector = [random.uniform(-1.0, 1.0) for _ in range(128)]
        
        # 4. Restore original random state
        random.setstate(state)
        
        return vector

class InMemoryVectorStore:
    def __init__(self):
        self.articles = []  # Ensure this matches your actual internal storage attribute

    async def add_article(self, article):  # Or whatever your store method is called
        self.articles.append(article)

    # Add the missing method expected by the orchestrator flow
    async def get_articles_in_time_window(self, start_time=None, end_time=None):
        # For a mock store, you can just return all articles, or filter them if dates are provided
        if start_time and end_time:
            return [a for a in self.articles if start_time <= a.published_at <= end_time]
        return self.articles

@pytest.mark.asyncio
async def test_orchestrator_pipeline_flow():
    # Setup test infrastructure targets
    mock_embed = MockEmbeddingClient()
    vector_db = InMemoryVectorStore()
    
    # Simple existing db state tracker function for deduplication verification
    async def mock_fetch_existing_embeddings():
        return []

    dedup = SportsNewsDeduplicator(
        repository=vector_db,
        embedding_client=mock_embed,
        semantic_threshold=0.92
    )

    orchestrator = IngestionPipelineOrchestrator(dedup, vector_db, mock_embed)

    # Register two mock scraping endpoints returning overlapping titles asynchronously
    async def mock_nba_scraper():
        return [
            {
                "title": "LeBron James shines in Lakers victory", 
                "body": "Scored 35 points against Warriors.", 
                "source": "nba_api", 
                "published_at": "2026-07-07T00:00:00Z",
                "url": "https://example.com/lakers-victory"
            },
            {
                "title": "Breaking News: Trade updates", 
                "body": "DeMar DeRozan trade finalized.", 
                "source": "Apify Scraper", 
                "published_at": "2026-07-07T01:00:00Z",
                "url": "https://example.com/trade-updates"
            }
        ]

    async def mock_duplicate_hoopshype_scraper():
        return [
            # Exact duplicate title to test out execution threshold rejections
            {
                "title": "LeBron James shines in Lakers victory", 
                "body": "Scored 35 points against Warriors.", 
                "source": "HoopsHype", 
                "published_at": "2026-07-07T00:00:00Z",
                "url": "https://example.com/lakers-victory-duplicate"
            }
        ]

    orchestrator.register_source(mock_nba_scraper)
    orchestrator.register_source(mock_duplicate_hoopshype_scraper)

    # Trigger async pipeline orchestration process evaluation run
    run_metrics = await orchestrator.run_cycle()

    # Asset checks
    assert run_metrics["total_fetched"] == 3
    assert run_metrics["saved"] == 2
    assert run_metrics["duplicates_dropped"] == 1
    assert len(vector_db.articles) == 2
    print("\n[SUCCESS] Integration flow runs pipeline clean and blocks duplicates!")