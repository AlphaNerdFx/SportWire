import pytest
from unittest.mock import AsyncMock, MagicMock
from ingestion.normalizer import NormalizationIngestionPipeline
from tests.conftest import NewsArticle
from unittest.mock import AsyncMock, MagicMock

async def test_pipeline_successful_normalization_and_insert(sample_raw_apify_payload, mock_article_repository):
    # Setup standard pipeline dependencies
    mock_dedup = AsyncMock()
    mock_dedup.check_duplicate.return_value = (False, None) # Not a duplicate
    
    pipeline = NormalizationIngestionPipeline(
        repository=mock_article_repository,
        deduplicator=mock_dedup,
        embedding_client=AsyncMock()  
    )
    
    mock_adapter = MagicMock()
    
    mock_article = MagicMock(spec=NewsArticle)
    mock_article.title = "LeBron James shines in Lakers victory over Warriors"
    mock_article.content = "LeBron James scored 35 points..."
    mock_article.metadata = {}
    mock_article.source_provider = "ESPN NBA NEWS API on Apify"
    
    mock_article.url = "https://example.com/news/lebron-warriors-2026"
    
    mock_adapter.transform_news.return_value = [mock_article] 
    
    await pipeline.ingest_news_feed(mock_adapter, sample_raw_apify_payload)

async def test_pipeline_duplicate_metadata_merge_routing(sample_raw_apify_payload, mock_article_repository):
    mock_dedup = AsyncMock()
    existing_record = NewsArticle(
        title="LeBron James shines in Lakers victory over Warriors",
        body="...", source="nba_api", url="...", published_at=MagicMock(), metadata={"historical_trackers": ["nba_api_core"]}
    )
    mock_dedup.check_duplicate.return_value = (True, existing_record)
    
    pipeline = NormalizationIngestionPipeline(
        repository=mock_article_repository,
        deduplicator=mock_dedup,
        embedding_client=AsyncMock()
    )
    
    mock_adapter = MagicMock()
    
    mock_article = MagicMock(spec=NewsArticle)
    mock_article.title = "LeBron James shines in Lakers victory over Warriors"
    mock_article.content = "LeBron James scored 35 points..."
    mock_article.metadata = {}
    mock_article.source_provider = "ESPN NBA NEWS API on Apify"
    
    mock_article.url = "https://example.com/news/lebron-warriors-2026"
    
    mock_adapter.transform_news.return_value = [mock_article]
    
    await pipeline.ingest_news_feed(mock_adapter, sample_raw_apify_payload)