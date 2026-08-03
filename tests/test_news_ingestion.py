import pytest
from datetime import datetime
from ingestion.news_clients import ESPNNewsClient, HoopsHypeClient, SportsTrackerClient
from ingestion.models import NewsSource, LeagueType

def test_espn_client_normalization():
    raw_apify_espn_payload = [
        {
            "id": "887766",
            "title": "Celtics eye back-to-back title run as training camp nears",
            "text": "The Boston Celtics are heavily favored to repeat their strong defensive metrics...",
            "url": "https://www.espn.com/nba/story/_/id/887766",
            "publishedAt": "2026-07-04T12:00:00Z",
            "categories": ["Celtics", "Preview"]
        }
    ]
    
    client = ESPNNewsClient()
    normalized = client.normalize(raw_apify_espn_payload)
    
    assert len(normalized) == 1
    article = normalized[0]
    assert article.article_id == "espn_887766"
    assert article.title == "Celtics eye back-to-back title run as training camp nears"
    assert article.source == NewsSource.ESPN
    assert article.league == LeagueType.NBA
    assert article.published_at.year == 2026
    assert "Celtics" in article.tags


def test_hoopshype_client_normalization():
    raw_hoopshype_payload = [
        {
            "title": "Lakers discussed trade parameters surrounding veteran depth",
            "link": "https://hoopshype.com/rumor/lakers-guard-updates/",
            "description": "Internal sources report active trade desk calls...",
            "time": "2026-07-04T15:45:00"
        }
    ]
    
    client = HoopsHypeClient()
    normalized = client.normalize(raw_hoopshype_payload)
    
    assert len(normalized) == 1
    article = normalized[0]
    assert article.article_id.startswith("hoopshype_")
    assert article.source == NewsSource.HOOPSHYPE
    assert article.league == LeagueType.NBA
    assert article.content == "Internal sources report active trade desk calls..."


def test_sportstracker_client_normalization():
    raw_sportstracker_payload = [
        {
            "article_title": "Breaking down the elite edge rushers in the NFL North",
            "source_url": "https://sportstracker.com/nfl/edge-rushers-analysis",
            "body": "Film study indicates significant schema variation up front...",
            "pub_date": "2026-07-04 18:30:00",
            "metadata_tags": ["NFL", "Defense"]
        }
    ]
    
    client = SportsTrackerClient()
    normalized = client.normalize(raw_sportstracker_payload)
    
    assert len(normalized) == 1
    article = normalized[0]
    assert article.article_id.startswith("sportstracker_")
    assert article.source == NewsSource.SPORTSTRACKER
    assert article.league == LeagueType.NFL
    assert article.published_at.hour == 18
    assert article.published_at.minute == 30