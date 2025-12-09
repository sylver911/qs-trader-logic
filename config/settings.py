"""Application configuration from environment variables."""

import os
from dataclasses import dataclass


@dataclass
class Settings:
    """Application settings loaded from environment variables."""

    # MongoDB
    MONGO_URL: str = os.getenv("MONGO_URL", "mongodb://localhost:27017/")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", os.getenv("QS_DB", "qs"))
    SETTINGS_DB: str = os.getenv("SETTINGS_DB", "app_settings")  # For prompts
    THREADS_COLLECTION: str = "discord_threads"

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    QUEUE_KEY: str = "queue:threads:pending"
    PROCESSING_KEY: str = "queue:threads:processing"
    CONFIG_PREFIX: str = "config:trading:"

    # LiteLLM
    LITELLM_URL: str = os.getenv("LITELLM_URL", "http://localhost:4000")
    LITELLM_API_KEY: str = os.getenv("LITELLM_API_KEY", "")

    # IBind / IBKR
    IBEAM_URL: str = os.getenv("IBEAM_URL", "http://localhost:5000")
    IB_ACCOUNT_ID: str = os.getenv("IB_ACCOUNT_ID", "")

    # Market Data Source
    # Set to "true" when you have IBKR market data subscription
    # Default "false" uses yfinance (free, delayed data)
    USE_IBKR_MARKET_DATA: bool = os.getenv("USE_IBKR_MARKET_DATA", "false").lower() in ("true", "1", "yes")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_WEBHOOK_URL: str = os.getenv("LOG_WEBHOOK_URL", "")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    def validate(self) -> None:
        """Validate required settings."""
        errors = []

        if not self.MONGO_URL:
            errors.append("MONGO_URL is required")
        if not self.REDIS_URL:
            errors.append("REDIS_URL is required")
        if not self.LITELLM_URL:
            errors.append("LITELLM_URL is required")
        if not self.IB_ACCOUNT_ID:
            errors.append("IB_ACCOUNT_ID is required")

        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")


config = Settings()
