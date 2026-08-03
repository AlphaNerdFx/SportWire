import pytest
from datetime import datetime
from pydantic import ValidationError
from schemas.normalized import GameStatus, GameDataSchema, NormalizedArticleSchema

def test_game_data_status_normalization():
    payload_scheduled = {
        "game_id": "nba_12345",
        "home_team": "Celtics",
        "away_team": "Lakers",
        "home_score": 0,
        "away_score": 0,
        "status": "Pregame",
        "game_datetime": "2026-11-15T19:30:00Z",
        "sport": "NBA"
    }
    
    payload_live = payload_scheduled.copy()
    payload_live["status"] = "IN PROGRESS"
    payload_live["home_score"] = 102
    
    model_scheduled = GameDataSchema(**payload_scheduled)
    assert model_scheduled.status == GameStatus.SCHEDULED
    
    model_live = GameDataSchema(**payload_live)
    assert model_live.status == GameStatus.LIVE

def test_game_data_invalid_constraints():
    bad_payload = {
        "game_id": "nba_12345",
        "home_team": "Celtics",
        "away_team": "Lakers",
        "home_score": -10,
        "away_score": 85,
        "status": "FINAL",
        "game_datetime": "2026-11-15T19:30:00Z",
        "sport": "NBA"
    }
    
    with pytest.raises(ValidationError) as exc_info:
        GameDataSchema(**bad_payload)
    
    assert "home_score" in str(exc_info.value)

def test_article_deterministic_id_generation():
    article_data = {
        "title": "LeBron James Breaks Another Scoring Record",
        "url": "https://www.espn.com/nba/story/example",
        "source": "ESPN",
        "content": "Body text excerpt goes here.",
        "published_at": "2026-07-02T12:00:00Z",
        "sport": "NBA"
    }
    
    article_1 = NormalizedArticleSchema(**article_data)
    assert article_1.deterministic_id is not None
    assert isinstance(article_1.deterministic_id, str)
    
    article_2 = NormalizedArticleSchema(**article_data)
    assert article_1.deterministic_id == article_2.deterministic_id

def test_article_preserves_provided_id():
    specific_id = "custom_scraped_hash_999"
    article_data = {
        "deterministic_id": specific_id,
        "title": "NFL Draft Shocking Trades Shake Up Round 1",
        "url": "https://sports.yahoo.com/nfl-draft",
        "source": "HoopsHype",
        "content": "Body text content.",
        "published_at": "2026-04-25T10:00:00Z",
        "sport": "NFL"
    }
    
    model = NormalizedArticleSchema(**article_data)
    assert model.deterministic_id == specific_id