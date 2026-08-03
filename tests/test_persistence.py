import pytest
import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from storage.repository import SportsPersistenceRepository
from storage.models import NewsArticle

@pytest.mark.asyncio
async def test_repository_deduplication_logic():
    """Verifies repository drops execution flow if specific hash match returns positive."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    
    # Simulate database finding an existing row with the same unique hash
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_return_value = 42  # Dummy existing ID found
    mock_session.execute.return_value = mock_result

    repo = SportsPersistenceRepository(session=mock_session)
    
    stub_article = {
        "source_provider": "ESPN",
        "source_id": "nba_news_99101",
        "title": "LeBron James Hits Game Winner",
        "content": "A spectacular performance at the buzzer...",
        "url": "https://espn.com/nba/1"
    }

    # Execute system save pipeline
    is_saved = await repo.save_news_article(stub_article)

    assert is_saved is False
    # Validate embedding engine wasn't called unnecessarily
    mock_session.add.assert_not_called()


@pytest.mark.asyncio
@patch("storage.repository.embedding_engine")
async def test_repository_successful_save_flow(mock_embed_engine):
    """Verifies fresh articles are stored along with their vectorized fragments."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    
    # Simulate no duplicate hash found in the DB
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    # Mock return values from the embedding engine
    mock_embed_engine.process_document = AsyncMock(return_value=[
        {"index": 0, "text": "Fragment content sample", "vector": [0.1, -0.2, 0.4]}
    ])

    repo = SportsPersistenceRepository(session=mock_session)
    
    stub_article = {
        "source_provider": "HoopsHype",
        "source_id": "hh_article_12",
        "title": "Trade Rumors Heat Up",
        "content": "Fragment content sample",
        "url": "https://hoopshype.com/rumor"
    }

    is_saved = await repo.save_news_article(stub_article)

    assert is_saved is True
    assert mock_session.add.call_count == 2  # Once for article metadata, once for the vector chunk
    mock_session.commit.assert_called_once()