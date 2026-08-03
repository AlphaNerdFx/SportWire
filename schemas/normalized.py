import hashlib
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator

# --- Enums for Consistent State Control ---
class ArticleSource(str, Enum):
    ESPN = "ESPN"
    HOOPSHYPE = "HoopsHype"
    SPORTSTRACKER = "SportsTracker"

class SportType(str, Enum):
    NBA = "NBA"
    NFL = "NFL"


class GameStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    FINAL = "FINAL"


# --- 1. Game Data Validation Schema ---
class GameDataSchema(BaseModel):
    game_id: str = Field(
        ..., description="Unique identifier for the game parsed from the source API"
    )
    sport: SportType
    home_team: str = Field(..., min_length=1, description="Normalized home team name")
    away_team: str = Field(..., min_length=1, description="Normalized away team name")
    game_datetime: datetime = Field(
        ..., description="Game kickoff/tip-off time in UTC"
    )
    status: GameStatus
    home_score: int = Field(default=0, ge=0)
    away_score: int = Field(default=0, ge=0)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # Coerce and standardize sport strings (e.g., 'nba ' -> 'NBA')
    @field_validator("sport", mode="before")
    @classmethod
    def standardize_sport(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    # Normalize messy scraper / raw API statuses into clean Enums
    @field_validator("status", mode="before")
    @classmethod
    def standardize_status(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        
        status_clean = value.strip().upper()
        
        # Mapping rules for different structures (e.g., nba_api vs Apify vs nflreadpy)
        if status_clean in ["SCHEDULED", "PREGAME", "STATUS_SCHEDULED", "1"]:
            return "SCHEDULED"
        if status_clean in ["LIVE", "IN_PROGRESS", "IN PROGRESS", "HALFTIME", "Q1", "Q2", "Q3", "Q4", "2"]:
            return "LIVE"
        if status_clean in ["FINAL", "CLOSED", "COMPLETE", "STATUS_FINAL", "3"]:
            return "FINAL"
            
        return status_clean


# --- 2. Normalized Articles Validation Schema ---
class NormalizedArticleSchema(BaseModel):
    deterministic_id: Optional[str] = Field(
        default=None, 
        description="SHA-256 hash generated automatically to prevent database duplication"
    )
    sport: SportType
    source: str = Field(..., description="Source origin, e.g., 'ESPN', 'HoopsHype', 'Sportstracker'")
    title: str = Field(..., min_length=3, description="Article headline")
    content: str = Field(..., min_length=1, description="Full body content or primary excerpt text")
    url: Optional[str] = Field(default=None, description="Direct web link to source article")
    published_at: datetime = Field(..., description="Timestamp when article was published")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("sport", mode="before")
    @classmethod
    def standardize_sport(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip().upper()
        return value

    @field_validator("source", mode="before")
    @classmethod
    def clean_source_name(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    # Automatically generate the deterministic_id if it's missing
    @model_validator(mode="after")
    def enforce_deterministic_id(self) -> "NormalizedArticleSchema":
        if not self.deterministic_id:
            # Create a string representation combining source, title, and timestamp
            unique_fingerprint = f"{self.source.lower()}_{self.title.lower()}_{self.published_at.isoformat()}"
            # Generate a SHA-256 hash out of it
            self.deterministic_id = hashlib.sha256(unique_fingerprint.encode("utf-8")).hexdigest()
        return self