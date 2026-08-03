import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import String, DateTime, Integer, Enum, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Import normalization enumerations to keep single source of truth across boundaries
from schemas.normalized import SportType, ArticleSource, GameStatus

class Base(DeclarativeBase):
    """Abstract foundational base containing default global metadata metadata configuration."""
    pass

class NormalizedArticle(Base):
    """
    Persistent relational mirror of the NewsArticle normalization layer.
    Configured for high-throughput UPSERT operations utilizing conflict resolution pipelines.
    """
    __tablename__ = "normalized_articles"

    # Primary key uses a standard internal auto-incrementing integer or sequential identifier
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # The clean deterministic string SHA-256 hash provided by our normalization layer
    deterministic_id: Mapped[str] = mapped_column(
        String(64), 
        nullable=False, 
        index=True,
        comment="Deterministic SHA-256 hash calculated from structural components to filter upstream duplicates."
    )
    
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    
    # SQLAlchemy native support for Native Postgres Enums
    source: Mapped[ArticleSource] = mapped_column(
        Enum(ArticleSource, name="article_source_enum", create_type=True), 
        nullable=False,
        index=True
    )
    sport: Mapped[SportType] = mapped_column(
        Enum(SportType, name="sport_type_enum", create_type=True), 
        nullable=False,
        index=True
    )
    
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    
    # JSONB field optimized for structural query transparency over unstructured source parameters
    raw_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    __table_args__ = (
        # Unique constraint to act as target for PG 'ON CONFLICT DO UPDATE' operations
        UniqueConstraint("deterministic_id", name="uq_articles_deterministic_id"),
    )

    def __repr__(self) -> str:
        return f"<NormalizedArticle sport={self.sport.value} source={self.source.value} title={self.title[:30]}...>"


class GameDataModel(Base):
    """
    Persistent relational mirror of the GameData normalization layer tracking scheduling, 
    live status metrics, and absolute scoring summaries across sports fields.
    """
    __tablename__ = "game_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Primary natural identifier derived cleanly from source API or Provider parameters
    game_id: Mapped[str] = mapped_column(
        String(100), 
        nullable=False, 
        index=True,
        comment="Provider-native unique match tracking string identifier."
    )
    
    sport: Mapped[SportType] = mapped_column(
        Enum(SportType, name="sport_type_enum", create_type=True), 
        nullable=False,
        index=True
    )
    
    home_team: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    away_team: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    home_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    away_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    status: Mapped[GameStatus] = mapped_column(
        Enum(GameStatus, name="game_status_enum", create_type=True), 
        nullable=False,
        index=True
    )
    
    game_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    venue: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    raw_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=datetime.utcnow, 
        onupdate=datetime.utcnow, 
        nullable=False
    )

    __table_args__ = (
        # Ensure compound uniquely scoped identifier blocks overlapping games cleanly on an active system
        UniqueConstraint("game_id", "sport", name="uq_games_game_id_sport"),
    )

    def __repr__(self) -> str:
        return f"<GameDataModel sport={self.sport.value} match='{self.away_team} @ {self.home_team}' status={self.status.value}>"