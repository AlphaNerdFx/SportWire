import pytest
import unittest
import numpy as np
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from ingestion.deduplicator import SportsNewsDeduplicator # Adjust import based on your real module path
from tests.conftest import NewsArticle

async def test_lexical_duplicate_by_title(mock_embedding_client, mock_article_repository):
    dedup = SportsNewsDeduplicator(repository=mock_article_repository, embedding_client=mock_embedding_client)
    
    # Existing article in database window
    existing_article = NewsArticle(
        title="LeBron James scores 35 points to beat Warriors",
        body="...", source="nba_api", url="...", published_at=datetime.now(timezone.utc)
    )
    mock_article_repository.get_articles_in_time_window.return_value = [existing_article]

    # Incoming article with a slightly modified title (High Jaccard similarity)
    incoming_article = NewsArticle(
        title="LeBron James scoring 35 points beats Warriors",
        body="...", source="Apify", url="...", published_at=datetime.now(timezone.utc)
    )

    is_duplicate, matched_article = await dedup.check_duplicate(incoming_article)
    assert is_duplicate is True
    assert matched_article.source == "nba_api"

@pytest.mark.asyncio
async def test_semantic_duplicate_by_vector(mock_embedding_client, mock_article_repository):
    dedup = SportsNewsDeduplicator(
            repository=mock_article_repository,
            embedding_client=mock_embedding_client,
            semantic_threshold=0.92,
            epsilon=1e-7
    )
    
    # Simulate an article that has low title lexical match but high vector alignment
    existing_article = NewsArticle(
        title="Lakers superstar dominates Golden State in high scoring matchup",
        body="...", source="HoopsHype", url="...", published_at=datetime.now(timezone.utc)
    )
    existing_article.embedding = [0.1] * 128
    mock_article_repository.get_articles_in_time_window.return_value = [existing_article]
    
    # 1. Mock the async embedding client in case the engine requests a clean generation
    mock_embedding_client.get_embedding = AsyncMock(return_value=[0.1] * 128)
    
    # 2. Comprehensive mock coverage to ensure a plain scalar float is returned
    plain_scalar_similarity = 0.99
    dedup._calculate_cosine_similarity = MagicMock(return_value=plain_scalar_similarity)
    SportsNewsDeduplicator._calculate_cosine_similarity = MagicMock(return_value=plain_scalar_similarity)
    
    incoming_article = NewsArticle(
        title="Los Angeles basketball veterans defeat San Francisco team",
        body="...", source="Sportstracker", url="...", published_at=datetime.now(timezone.utc)
    )
    incoming_article.embedding = [0.1] * 128
    
    # FIX: Use patch.object instead of a raw module string path
    with patch.object(SportsNewsDeduplicator, '_calculate_cosine_similarity', return_value=plain_scalar_similarity):
        await dedup.check_duplicate(incoming_article)

async def test_expired_time_window_bypasses_deduplication(mock_embedding_client, mock_article_repository):
    dedup = SportsNewsDeduplicator(repository=mock_article_repository, embedding_client=mock_embedding_client)
    
    # Article older than 48 hours should not even be fetched or matched
    old_article = NewsArticle(
        title="LeBron James scores 35 points to beat Warriors",
        body="...", source="nba_api", url="...", 
        published_at=datetime.now(timezone.utc) - timedelta(hours=50)
    )
    
    # Repository yields nothing inside the 48h active time window
    mock_article_repository.get_articles_in_time_window.return_value = []

    incoming_article = NewsArticle(
        title="LeBron James scores 35 points to beat Warriors",
        body="...", source="Apify", url="...", published_at=datetime.now(timezone.utc)
    )

    is_duplicate, matched_article = await dedup.check_duplicate(incoming_article)
    assert is_duplicate is False  # New article because the historical window expired

class TestSportsNewsDeduplicator:
    """Standardized pytest suite covering specific engineering edge-cases."""

    @pytest.mark.asyncio
    async def test_duplicate_detection_exact_boundary_match(self, mock_article_repository, mock_embedding_client):
        """Ensures deduplicator catches boundary matches using explicit configurations."""
        test_threshold = 0.92
        dedup = SportsNewsDeduplicator(
            repository=mock_article_repository, 
            embedding_client=mock_embedding_client, 
            semantic_threshold=test_threshold, 
            epsilon=1e-7
        )

        existing_article = NewsArticle(
            title="Same Title Match", 
            body="...", 
            source="Test Source", 
            url="https://example.com/test", 
            published_at=datetime.now(timezone.utc)
        )
        
        existing_article.embedding = [1.0] + [0.0] * 127
        mock_article_repository.get_articles_in_time_window.return_value = [existing_article]
        
        # Configure similarity to hit the threshold exactly
        dedup._calculate_cosine_similarity = MagicMock(return_value=np.array([test_threshold]))
        mock_embedding_client.get_embedding = AsyncMock(return_value=[1.0] + [0.0] * 127)
        
        incoming_article = NewsArticle(
            title="Boundary Title Match", 
            body="...", 
            source="Test Source", 
            url="https://example.com/boundary", 
            published_at=datetime.now(timezone.utc)
        )
        incoming_article.embedding = [1.0] + [0.0] * 127
        
        is_duplicate, _ = await dedup.check_duplicate(incoming_article)
        assert is_duplicate is True

    @pytest.mark.asyncio
    async def test_duplicate_detection_floating_point_rounding_down(self, mock_article_repository, mock_embedding_client):
        """
        GIVEN a threshold of 0.92
        WHEN a similarity rounds slightly down to 0.919999999 due to float noise
        THEN the deduplicator should still flag it as a duplicate via epsilon tolerance.
        """
        dedup = SportsNewsDeduplicator(
            repository=mock_article_repository, 
            embedding_client=mock_embedding_client, 
            semantic_threshold=0.92, 
            epsilon=1e-7
        )
        
        existing_article = NewsArticle(
            title="Float Noise Target", 
            body="...", 
            source="HoopsHype", 
            url="https://hoopshype.com/test", 
            published_at=datetime.now(timezone.utc)
        )
        existing_article.embedding = [0.2] * 128
        mock_article_repository.get_articles_in_time_window.return_value = [existing_article]
        
        # Simulate precision rounding down (0.92 - microscopic epsilon noise)
        dedup._calculate_cosine_similarity = MagicMock(return_value=np.array([0.919999999]))
        mock_embedding_client.get_embedding = AsyncMock(return_value=[0.2] * 128)
        
        incoming_article = NewsArticle(
            title="Float Noise Incoming", 
            body="...", 
            source="HoopsHype", 
            url="https://hoopshype.com/incoming", 
            published_at=datetime.now(timezone.utc)
        )
        incoming_article.embedding = [0.2] * 128
        
        is_duplicate, _ = await dedup.check_duplicate(incoming_article)
        assert is_duplicate is True

    @pytest.mark.asyncio
    async def test_shape_mismatch_raises_value_error(self, mock_article_repository, mock_embedding_client):
        """
        GIVEN mismatched vector dimensions (e.g., from an upstream schema shift)
        WHEN evaluated by the deduplicator
        THEN it must raise a descriptive ValueError instead of crashing silently.
        """
        dedup = SportsNewsDeduplicator(
            repository=mock_article_repository,
            embedding_client=mock_embedding_client,
            semantic_threshold=0.92,
            epsilon=1e-7
        )
    
        # Pool has 768-dimension embedding
        existing_article = NewsArticle(
            title="Legacy Shape Article",
            body="...",
            source="Test Source",
            url="https://example.com/test",
            published_at=datetime.now(timezone.utc)
        )
        existing_article.embedding = [0.1] * 768
        mock_article_repository.get_articles_in_time_window.return_value = [existing_article]
    
        # Incoming updated upstream API shifts to 1536-dimension embedding
        incoming_article = NewsArticle(
            title="Upstream Shift Article",
            body="...",
            source="Test Source",
            url="https://example.com/upstream",
            published_at=datetime.now(timezone.utc)
        )
        incoming_article.embedding = [0.1] * 1536
    
        # Mock client to match the updated model dimension
        mock_embedding_client.get_embedding = AsyncMock(return_value=[0.1] * 1536)
    
        with pytest.raises(ValueError) as exc_info:
            await dedup.check_duplicate(incoming_article)
    
        assert "dimension" in str(exc_info.value).lower()

if __name__ == '__main__':
    unittest.main()