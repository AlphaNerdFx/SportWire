import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from database.models import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://openclaw_user:openclaw_password@localhost:5432/openclaw_sports"
)

async_engine = create_async_engine(DATABASE_URL, echo=False)

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_local_database():
    """Bootstraps database extensions and verifies schema states."""
    async with async_engine.begin() as conn:
        # Resolve pgvector critical edge-case
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)