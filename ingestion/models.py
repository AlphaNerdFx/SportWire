from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional

class NewsSource(str, Enum):
    ESPN = "ESPN"
    HOOPSHYPE = "HoopsHype"
    SPORTSTRACKER = "SportsTracker"

class LeagueType(str, Enum):
    NBA = "NBA"
    NFL = "NFL"
    GENERAL = "GENERAL"

@dataclass(frozen=True)
class NewsArticle:
    article_id: str          # Normalized unique identifier (e.g., 'espn_12345')
    title: str
    content: str
    url: str
    source: NewsSource
    league: LeagueType
    published_at: datetime
    tags: List[str] = field(default_factory=list)