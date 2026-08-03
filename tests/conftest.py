import pytest
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel

# Mocked Pydantic boundary schema for matching normalizer outputs
class NewsArticle(BaseModel):
    title: str
    body: str
    source: str
    published_at: datetime
    url: str
    metadata: dict = {}
    embedding: Optional[List[float]] = None

@pytest.fixture
def mock_embedding_client():
    """Mocks the vector embedding generator."""
    client = MagicMock()
    # Stub embedding generator to return deterministic lists based on title
    client.get_embedding.side_effect = lambda text: [0.1, 0.2, 0.3] if "LeBron" in text else [0.9, 0.8, 0.7]
    return client

@pytest.fixture
def mock_article_repository():
    """Mocks pgvector/PostgreSQL article layer lookup actions."""
    repo = AsyncMock()
    # Mock lookup returning an empty list by default (no historical duplicates found)
    repo.get_articles_in_time_window.return_value = []
    return repo

@pytest.fixture
def sample_raw_apify_payload():
    """Simulates a messy JSON scrape result from Apify/HoopsHype."""
    return {
        "headline_text": "LeBron James shines in Lakers victory over Warriors",
        "story_body": "LeBron James scored 35 points tonight pushing the Lakers past Golden State...",
        "source_api": "ESPN NBA NEWS API on Apify",
        "created_timestamp": "2026-07-05T02:00:00Z",
        "article_link": "https://espn.com/nba/lakers-vs-warriors"
    }