import os
from asyncio import current_task
from typing import AsyncGenerator
# pyrefly: ignore [missing-import]
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    async_scoped_session
)
from storage.models import Base

# Fallback string matching your docker-compose parameters
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://sports_user:sports_password@localhost:5432/sports_db"
)

# Build high-performance async engine with connection pooling parameters
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True
)

# Session factory configuration
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection lifecycle provider for async database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    """Utility function to bootstrap relational tables (useful for fast local prototyping)."""
    async with engine.begin() as conn:
        # Note: In a production run, you'll eventually want to migrate to Alembic.
        await conn.run_sync(Base.metadata.create_all)