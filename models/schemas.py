from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, HttpUrl

class NewsArticle(BaseModel):
    id: Optional[str] = Field(None, description="Unique hash string generated from source URL/Title to prevent duplicates")
    title: str = Field(..., min_length=5, description="Headline of the story or news update")
    body: str = Field(..., description="Full text body, parsed markdown, or description snippet")
    summary: Optional[str] = Field(None, description="Optional LLM generated or source-provided summary")
    url: Optional[HttpUrl] = Field(None, description="Original reference link if available")
    source: str = Field(..., description="Explicit identifier of source (e.g., 'apify_espn_nba', 'hoopshype')")
    sport: str = Field(..., description="Must be either 'NBA' or 'NFL'")
    tags: List[str] = Field(default_factory=list, description="Targeted keywords like player names, teams, or categories")
    published_at: datetime = Field(default_factory=datetime.utcnow, description="Standardized UTC timestamp for sorting")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary raw storage to preserve unique variables")

class GameData(BaseModel):
    game_id: str = Field(..., description="Unique code or internal league index string for the match")
    sport: str = Field(..., description="'NBA' or 'NFL'")
    home_team: str = Field(..., description="Full name or tricode of the home franchise")
    away_team: str = Field(..., description="Full name or tricode of the visitor franchise")
    home_score: int = Field(0, ge=0)
    away_score: int = Field(0, ge=0)
    status: str = Field(..., description="Game status: 'Scheduled', 'Live', 'Finished', or 'Postponed'")
    game_clock: Optional[str] = Field(None, description="Remaining period time if game is currently live (e.g., 'Q3 04:12')")
    game_time_utc: datetime = Field(..., description="Standardized kickoff/tip-off timeline")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw fallback payload dictionary")