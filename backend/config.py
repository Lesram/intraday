"""
Configuration module for the Algorithmic Trading Platform.
Handles environment variables and application settings.
"""

import os
from typing import List, Optional

from decouple import config
from pydantic import Field, ConfigDict, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = ConfigDict(env_file=".env", case_sensitive=False)

    # Alpaca Trading API Configuration
    alpaca_api_key: str = config("ALPACA_API_KEY", default="")
    alpaca_secret_key: str = config("ALPACA_SECRET_KEY", default="")
    alpaca_paper_trading: bool = config("ALPACA_PAPER_TRADING", default=True, cast=bool)

    # Twitter API Configuration
    twitter_api_key: str = config("TWITTER_API_KEY", default="")
    twitter_api_secret: str = config("TWITTER_API_SECRET", default="")
    twitter_bearer_token: str = config("TWITTER_BEARER_TOKEN", default="")

    # Reddit API Configuration
    reddit_client_id: str = config("REDDIT_CLIENT_ID", default="")
    reddit_client_secret: str = config("REDDIT_CLIENT_SECRET", default="")
    reddit_user_agent: str = config(
        "REDDIT_USER_AGENT", default="AlgoTradingPlatform/1.0"
    )

    # Redis Configuration
    redis_host: str = config("REDIS_HOST", default="localhost")
    redis_port: int = config("REDIS_PORT", default=6379, cast=int)
    redis_db: int = config("REDIS_DB", default=0, cast=int)

    # Database Configuration
    database_url: str = config(
        "DATABASE_URL", default="sqlite:///./trading_platform.db"
    )

    # API Security
    api_secret_key: str = config(
        "API_SECRET_KEY", default="your-secret-key-change-in-production"
    )
    algorithm: str = config("ALGORITHM", default="HS256")

    # Risk Management Configuration
    max_daily_loss_pct: float = config("MAX_DAILY_LOSS_PCT", default=0.03, cast=float)
    max_drawdown_pct: float = config("MAX_DRAWDOWN_PCT", default=0.06, cast=float)
    max_position_pct: float = config("MAX_POSITION_PCT", default=0.10, cast=float)
    max_leverage: float = config("MAX_LEVERAGE", default=2.0, cast=float)

    # Monitoring Configuration
    prometheus_port: int = config("PROMETHEUS_PORT", default=8000, cast=int)
    log_level: str = config("LOG_LEVEL", default="INFO")

    # Model Configuration
    model_registry_path: str = config(
        "MODEL_REGISTRY_PATH", default="backend/models/saved_models"
    )
    drift_detection_threshold: float = config(
        "DRIFT_DETECTION_THRESHOLD", default=0.05, cast=float
    )

    # Trading Configuration
    default_symbols: List[str] = Field(
        default=[
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "TSLA",
            "BTC/USD",
            "ETH/USD",
        ]
    )
    trading_hours_start: str = "09:30"
    trading_hours_end: str = "16:00"
    timezone: str = "America/New_York"

    @field_validator('default_symbols', mode='before')
    @classmethod
    def parse_comma_separated_list(cls, v):
        """Parse comma-separated string into list"""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # Strategy Configuration
    ensemble_weights: dict = {"lstm": 0.5, "xgboost": 0.3, "random_forest": 0.2}

    # Feature Engineering Configuration
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bollinger_period: int = 20
    bollinger_std: float = 2.0

    # Sentiment Analysis Configuration
    subreddit_list: List[str] = [
        "StockMarket",
        "investing",
        "wallstreetbets",
        "cryptocurrency",
        "Bitcoin",
    ]
    sentiment_update_interval: int = 300  # 5 minutes

    # Model weights
    lstm_weight: float = config("LSTM_WEIGHT", default=0.4, cast=float)
    xgboost_weight: float = config("XGBOOST_WEIGHT", default=0.4, cast=float)
    random_forest_weight: float = config("RANDOM_FOREST_WEIGHT", default=0.2, cast=float)

    # Performance settings
    workers: int = config("WORKERS", default=4, cast=int)
    max_connections: int = config("MAX_CONNECTIONS", default=1000, cast=int)
    request_timeout: int = config("REQUEST_TIMEOUT", default=30, cast=int)


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


def validate_required_settings() -> bool:
    """Validate that all required settings are present."""
    required_fields = [
        "alpaca_api_key",
        "alpaca_secret_key",
    ]

    missing_fields = []
    for field in required_fields:
        if not getattr(settings, field):
            missing_fields.append(field)

    if missing_fields:
        raise ValueError(f"Missing required configuration: {', '.join(missing_fields)}")

    return True


# Validate settings on import
if os.getenv("SKIP_VALIDATION") != "true":
    try:
        validate_required_settings()
    except ValueError as e:
        print(f"Configuration Warning: {e}")
        print("Please set the required environment variables or create a .env file.")
