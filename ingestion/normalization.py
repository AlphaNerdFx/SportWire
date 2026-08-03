from datetime import datetime
from dataclasses import dataclass
# ingestion/normalization.py
from enum import Enum

class SportType(str, Enum):
    NBA = "NBA"
    NFL = "NFL"

class ArticleSource(str, Enum):
    ESPN = "ESPN"
    HoopsHype = "HoopsHype"
    nba_api = "nba_api"
    nflreadpy = "nflreadpy"
    UNKNOWN = "Unknown"

class GameStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    COMPLETED = "COMPLETED"
    POSTPONED = "POSTPONED"

@dataclass
class NormalizedNewsDTO:
    source_name: str
    external_id: str
    title: str
    content: str
    url: str
    published_at: datetime

@dataclass
class NormalizedGameDTO:
    league: str
    game_id: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    game_status: str
    game_timestamp: datetime

class DataNormalizationLayer:
    def normalize_news(self, source: str, raw_data: dict) -> NormalizedNewsDTO:
        return NormalizedNewsDTO(
            source_name=source,
            external_id=raw_data.get("story_id"),
            title=raw_data.get("headline"),
            content=raw_data.get("content"),
            url=raw_data.get("url"),
            published_at=datetime.fromisoformat(raw_data.get("published"))
        )

    def normalize_game(self, source: str, raw_data: dict) -> NormalizedGameDTO:
        league = "NBA" if "nba" in source.lower() or "lakers" in str(raw_data.values()).lower() else "NFL"
        return NormalizedGameDTO(
            league=league,
            game_id=raw_data.get("game_id"),
            home_team=raw_data.get("home"),
            away_team=raw_data.get("away"),
            home_score=raw_data.get("home_score"),
            away_score=raw_data.get("away_score"),
            game_status=raw_data.get("status"),
            game_timestamp=datetime.strptime(raw_data.get("game_date"), "%Y-%m-%d")
        )