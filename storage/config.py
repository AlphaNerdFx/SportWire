import os

class StorageConfig:
    DB_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/openclaw")
    MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
    VECTOR_DIMENSION: int = int(os.getenv("VECTOR_DIMENSION", "384"))  # MiniLM outputs 384 dims
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))             # Chars or tokens limit
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "100"))