import pytest
from datetime import datetime
from ingestion.adapters.nba_api_adapter import NbaApiAdapter
from ingestion.adapters.apify_news_adapter import ApifyNewsAdapter

def test_nba_api_scoreboard_adapter_mapping():
    adapter = NbaApiAdapter()
    
    # Simulates a raw payload structure returned by nba_api scoreboard endpoints
    mock_payload = {
        "scoreboard": {
            "games": [
                {
                    "gameId": "0022500001",
                    "gameTimeUTC": "2026-03-29T23:30:00Z",
                    "gameStatusText": "Final",
                    "homeTeam": {"teamName": "Lakers", "score": 112},
                    "awayTeam": {"teamName": "Celtics", "score": 105}
                }
            ]
        }
    }

    results = adapter.transform_games(mock_payload)
    
    assert len(results) == 1
    assert results[0].league == "NBA"
    assert results[0].game_id == "0022500001"
    assert results[0].home_team == "Lakers"
    assert results[0].home_score == 112
    assert results[0].game_status == "FINAL"


def test_apify_news_adapter_malformed_drops():
    adapter = ApifyNewsAdapter(provider_tag="ESPN_NBA")
    
    # Explicitly verify that missing required schema blocks (like text body content) 
    # are caught and handled without throwing errors
    bad_payloads = [
        {
            "id": "news_1",
            "title": "Valid title entry",
            "content": None, # Should trigger validation drop
            "publishedAt": "2026-01-01T00:00:00Z"
        },
        {
            "id": "news_2",
            "title": "Another title entry",
            "content": "This story has legitimate text contents present.",
            "publishedAt": "2026-01-01T00:00:00Z"
        }
    ]

    results = adapter.transform_news(bad_payloads)
    assert len(results) == 1
    assert results[0].source_id == "news_2"
    assert results[0].source_provider == "ESPN_NBA"