import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from unittest.mock import ANY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from database.models import NormalizedArticle, GameDataModel
from ingestion.orchestrator import IngestionOrchestrator
from storage.models import GameData

# --- Mock Normalization Schemas ---

@pytest.fixture
def mock_normalized_article_data():
    mock_article = MagicMock()
    mock_article.source_name = "ESPN NBA NEWS API on Apify"
    mock_article.external_id = "nba_998231"
    mock_article.title = "Lakers secure narrow victory behind late-game heroics"
    mock_article.content = "Full article text detailing the fourth-quarter comeback..."
    mock_article.url = "https://espn.com/nba/story/1"
    mock_article.published_at = datetime(2026, 10, 25, 12, 0, 0)
    return mock_article

@pytest.fixture
def mock_normalized_game_data():
    mock_game = MagicMock()
    mock_game.league = "NBA"
    mock_game.game_id = "0022300001"
    mock_game.home_team = "LAL"
    mock_game.away_team = "GWS"
    mock_game.home_score = 102
    mock_game.away_score = 101
    mock_game.game_status = "Final"
    mock_game.game_timestamp = datetime(2026, 10, 25, 20, 0, 0)
    return mock_game

# --- Database Session Mock Fixtures ---

@pytest.fixture
def mock_session():
    """Mocks an active SQLAlchemy AsyncSession context manager."""
    session = AsyncMock(spec=AsyncSession)
    
    # Mocking the session.begin() async context manager block
    begin_ctx = AsyncMock()
    session.begin.return_value = begin_ctx
    
    return session

@pytest.fixture
def mock_session_factory(mock_session):
    """Mocks the async_sessionmaker factory."""
    factory = MagicMock(spec=async_sessionmaker)
    
    # Mocking the factory context manager block: async with session_factory() as session:
    factory.return_value.__aenter__.return_value = mock_session
    factory.return_value.__aexit__.return_value = AsyncMock()
    
    return factory

@pytest.fixture
def orchestrator(mock_session_factory):
    """Initializes the orchestrator with mocked database dependencies."""
    return IngestionOrchestrator(
        session_factory=mock_session_factory,
        repository=AsyncMock(),
        deduplicator=AsyncMock(),
        embedding_client=MagicMock()
    )


# --- Core Pipeline Execution Tests ---

@pytest.mark.asyncio
async def test_run_pipeline_cycle_success(orchestrator, mock_session):
    """Verifies that a healthy ingestion cycle queries collectors and commits successfully."""
    
    # Spy on individual processing pipelines
    orchestrator.save_articles = AsyncMock()
    orchestrator.save_games = AsyncMock()
    
    await orchestrator.run_pipeline_cycle()
    
    # Check that collectors were called and routed cleanly
    orchestrator.save_articles.assert_called_once_with(mock_session, ANY)
    orchestrator.save_games.assert_called_once_with(mock_session, ANY)
    
    # Ensure standard transaction lifecycle was triggered
    mock_session.begin.assert_called_once()


@pytest.mark.asyncio
async def test_run_pipeline_cycle_failure_rolls_back(orchestrator, mock_session):
    """Verifies that any unexpected runtime error bubbles up and handles logging transparently."""
    
    # Induce an intentional infrastructure crash inside processing logic
    orchestrator.save_articles = AsyncMock(side_effect=RuntimeError("Database Connection Lost"))
    try:
        await orchestrator.run_pipeline_cycle()
    except Exception as e:
        logger.error(f"Ingestion lifecycle anomaly recorded during pipeline execution: {e}")
        await session.rollback()
    mock_session.rollback.assert_called_once()
        
    # Ensure transaction context handles exceptions appropriately without a clean exit
    mock_session.begin.assert_called_once()


# --- Batch Parameter Ingestion & Upsert Tests ---

@pytest.mark.asyncio
async def test_save_articles_empty_payload(orchestrator, mock_session):
    """Ensures empty payload collections exit gracefully without making DB round-trips."""
    await orchestrator.save_articles(mock_session, [])
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_save_games_empty_payload(orchestrator, mock_session):
    """Ensures empty game collections exit gracefully without making DB round-trips."""
    await orchestrator.save_games(mock_session, [])
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_save_articles_compiles_single_batch_call(orchestrator, mock_session, mock_normalized_article_data):
    """Verifies O(1) multi-row bulk upsert mapping bindings."""
    
    # Setup mock behavior for normalization layer response
    orchestrator.normalizer.normalize_news = MagicMock(return_value=mock_normalized_article_data)
    
    test_payload = [
        {
            "source": "ESPN NBA NEWS API on Apify",
            "raw_data": {"story_id": "nba_998231", "headline": "Lakers Win"}
        },
        {
            "source": "ESPN NBA NEWS API on Apify",
            "raw_data": {"story_id": "nba_998232", "headline": "Celtics Win"}
        }
    ]
    
    await orchestrator.save_articles(mock_session, test_payload)
    
    # Ensure normalization execution occurred exactly N times matching the array bounds
    assert orchestrator.normalizer.normalize_news.call_count == 2
    
    # Crucial Assertion: Confirm session.execute was hit exactly once with multi-row binds
    mock_session.execute.assert_called_once()
    
    # Extract structural args passed to execution engine
    
    called_stmt = mock_session.execute.call_args[0][0]

    # Compile and extract embedded binds from the query execution object
    called_binds = called_stmt.compile().params  # or called_stmt.parameters

    assert called_stmt.table.name == NormalizedArticle.__tablename__
    assert "title_m0" in called_binds
    assert "title_m1" in called_binds


@pytest.mark.asyncio
async def test_save_games_compiles_single_batch_call(orchestrator, mock_session, mock_normalized_game_data):
    """Verifies O(1) multi-row bulk game score upsert bindings."""
    
    orchestrator.normalizer.normalize_game = MagicMock(return_value=mock_normalized_game_data)
    
    test_payload = [
        {
            "source": "nba_api",
            "raw_data": {"game_id": "0022300001"}
        }
    ]
    
    await orchestrator.save_games(mock_session, test_payload)
    mock_session.execute.assert_called_once()
    
    orchestrator.normalizer.normalize_game.assert_called_once()
    mock_session.execute.assert_called_once()
    
    called_stmt = mock_session.execute.call_args[0][0]

    # Compile and extract embedded binds from the query execution object
    called_binds = called_stmt.compile().params  # or called_stmt.parameters

    assert called_stmt.table.name == GameData.__tablename__
    assert len(called_binds) == 11
    assert "game_id_m0" in called_binds