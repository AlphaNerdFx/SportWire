import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

# Absolute Path Resolution Anchors
BASE_DIR = Path(__file__).resolve().parent.parent

class AppSettings(BaseSettings):
    """
    Validates framework boundaries, environment variables, and external tokens.
    Ensures incorrect variable definitions cause failures at pipeline startup.
    """
    APP_ENV: str = "development"
    DEBUG: bool = True
    
    # Execution Intervals (Strict 8-Hour Sliding Windows)
    POLLING_INTERVAL_SECONDS: int = 28800 
    
    # Database Configuration Properties
    # Defaults to a persistent local SQLite file anchored inside the root directory
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/database/openclaw_state.db"
    
    # Narrative Data Ingestion Secrets (Apify Engine Platforms)
    APIFY_API_TOKEN: Optional[str] = None
    
    # Downstream Delivery Transport Gateways (Meta Developer Engine)
    META_WHATSAPP_API_TOKEN: Optional[str] = None
    WHATSAPP_BUSINESS_PHONE_NUMBER_ID: Optional[str] = None
    TARGET_RECIPIENT_PHONE_NUMBER: Optional[str] = None
    
    # LLM & Vector Framework Settings
    OPENAI_API_KEY: Optional[str] = None
    LLM_MODEL_NAME: str = "gpt-4o-mini"

    # Pydantic v2 Environment File Injection Parameters
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Singleton Instance for Absolute Imports Across Application Nodes
settings = AppSettings()