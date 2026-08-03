from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class NormalizedNews(BaseModel):
    source_provider: str = Field(..., min_length=2, max_length=50)
    source_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=3)
    content: str = Field(..., min_length=5)
    url: Optional[str] = None
    published_at: Optional[datetime] = None

class NormalizedGame(BaseModel):
    league: str = Field(..., pattern="^(NBA|NFL)$")
    game_id: str = Field(..., min_length=1, max_length=50)
    home_team: str = Field(..., min_length=2, max_length=100)
    away_team: str = Field(..., min_length=2, max_length=100)
    home_score: Optional[int] = Field(None, ge=0)
    away_score: Optional[int] = Field(None, ge=0)
    game_status: str = Field(..., pattern="^(SCHEDULED|LIVE|FINAL)$")
    scheduled_at: datetime