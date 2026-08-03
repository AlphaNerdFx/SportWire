import datetime
from typing import List, Optional
from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector
from storage.config import StorageConfig

class Base(DeclarativeBase):
    pass

class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_provider: Mapped[str] = mapped_column(String(50), nullable=False)  # ESPN, HoopsHype, etc.
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)       # Original system unique ID
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Strictly enforced natural hash key for absolute idempotency guardrails
    unique_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    # Relationship to normalized text chunks
    chunks: Mapped[List["ArticleChunk"]] = relationship(
        "ArticleChunk", back_populates="article", cascade="all, delete-orphan"
    )

class ArticleChunk(Base):
    __tablename__ = "article_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Vector column leveraging pgvector type definition
    embedding: Mapped[list] = mapped_column(Vector(StorageConfig.VECTOR_DIMENSION), nullable=False)

    article: Mapped["NewsArticle"] = relationship("NewsArticle", back_populates="chunks")

class GameData(Base):
    __tablename__ = "game_data"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    league: Mapped[str] = mapped_column(String(10), nullable=False)  # NBA or NFL
    game_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    home_team: Mapped[str] = mapped_column(String(100), nullable=False)
    away_team: Mapped[str] = mapped_column(String(100), nullable=False)
    home_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    away_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    game_status: Mapped[str] = mapped_column(String(20), nullable=False)  # SCHEDULED, LIVE, FINAL
    scheduled_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_updated: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())