"""
Configuration settings for the algorithmic trading platform.
Uses pydantic-settings BaseSettings pattern with nested configuration sections.
"""

import os
from functools import lru_cache
from typing import List, Dict, Optional
from pydantic import Field, field_validator, model_validator, ConfigDict
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    """Application configuration section."""
    
    environment: str = Field(default="development", description="Application environment")
    debug: bool = Field(default=True, description="Enable debug mode")
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=4, description="Number of workers")
    max_connections: int = Field(default=1000, description="Maximum connections")
    request_timeout: int = Field(default=30, description="Request timeout in seconds")
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="CORS allowed origins"
    )
    dev_mode: bool = Field(default=True, description="Development mode")
    
    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v):
        allowed_envs = ['development', 'staging', 'production']
        if v not in allowed_envs:
            raise ValueError(f'Environment must be one of {allowed_envs}')
        return v
        
    @field_validator('port')
    @classmethod
    def validate_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError('Port must be between 1 and 65535')
        return v

    model_config = ConfigDict(env_prefix="APP_", case_sensitive=False)


class SecurityConfig(BaseSettings):
    """Security configuration section."""
    
    jwt_secret_key: str = Field(
        default="your-super-secret-jwt-key-change-this-in-production",
        description="JWT secret key"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expire_minutes: int = Field(default=30, description="JWT expiration minutes")
    api_keys: List[str] = Field(default_factory=list, description="API keys for authentication")
    
    @field_validator('jwt_secret_key')
    @classmethod
    def validate_jwt_secret(cls, v):
        if len(v) < 32:
            raise ValueError('JWT secret key must be at least 32 characters')
        return v
        
    @field_validator('jwt_algorithm')
    @classmethod
    def validate_jwt_algorithm(cls, v):
        allowed_algorithms = ['HS256', 'HS384', 'HS512', 'RS256', 'RS384', 'RS512']
        if v not in allowed_algorithms:
            raise ValueError(f'JWT algorithm must be one of {allowed_algorithms}')
        return v

    @model_validator(mode='after')
    def validate_production_security(self):
        """Validate production-specific security requirements."""
        # This will be validated at the main Settings level
        return self

    def __init__(self, **data):
        super().__init__(**data)
        # Load API keys from environment
        api_keys_env = os.getenv("API_KEYS", "")
        if api_keys_env:
            self.api_keys = [key.strip() for key in api_keys_env.split(",") if key.strip()]

    model_config = ConfigDict(env_prefix="SECURITY_", case_sensitive=False)


class AlpacaConfig(BaseSettings):
    """Alpaca API configuration section."""
    
    api_key: str = Field(default="", description="Alpaca API key")
    secret_key: str = Field(default="", description="Alpaca secret key")
    base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca API base URL"
    )
    websocket_url: str = Field(
        default="wss://stream.data.alpaca.markets/v2/iex",
        description="Alpaca WebSocket URL"
    )
    paper_trading: bool = Field(default=True, description="Enable paper trading")
    
    @validator('api_key', 'secret_key')
    def validate_credentials(cls, v, field):
        if not v and os.getenv('APP_ENVIRONMENT') == 'production':
            raise ValueError(f'Alpaca {field.name} is required in production')
        return v

    @validator('base_url', 'websocket_url')
    def validate_urls(cls, v):
        if not v.startswith(('http://', 'https://', 'ws://', 'wss://')):
            raise ValueError('URL must start with http://, https://, ws://, or wss://')
        return v

    class Config:
        env_prefix = "ALPACA_"
        case_sensitive = False


class DataConfig(BaseSettings):
    """Data sources configuration section."""
    
    # Database configuration
    database_url: str = Field(
        default="sqlite:///./trading_platform.db",
        description="Database connection URL"
    )
    redis_url: str = Field(default="redis://localhost:6379", description="Redis connection URL")
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    
    # Social media API configuration
    reddit_client_id: str = Field(default="", description="Reddit API client ID")
    reddit_client_secret: str = Field(default="", description="Reddit API client secret")
    reddit_user_agent: str = Field(default="AlgoTradingPlatform/1.0", description="Reddit user agent")
    
    twitter_api_key: str = Field(default="", description="Twitter API key")
    twitter_api_secret: str = Field(default="", description="Twitter API secret")
    twitter_bearer_token: str = Field(default="", description="Twitter API bearer token")
    
    # Data feed settings
    default_symbols: List[str] = Field(
        default=[
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "BTC/USD", "ETH/USD"
        ],
        description="Default trading symbols"
    )
    subreddit_list: List[str] = Field(
        default=["StockMarket", "investing", "wallstreetbets", "cryptocurrency", "Bitcoin"],
        description="List of subreddits for sentiment analysis"
    )
    sentiment_update_interval: int = Field(default=300, description="Sentiment update interval in seconds")
    
    @validator('database_url')
    def validate_database_url(cls, v):
        if not v:
            raise ValueError('Database URL is required')
        return v

    @validator('redis_port')
    def validate_redis_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError('Redis port must be between 1 and 65535')
        return v

    class Config:
        env_prefix = "DATA_"
        case_sensitive = False


class WebsocketConfig(BaseSettings):
    """WebSocket configuration section."""
    
    rate_limit_per_minute: int = Field(default=60, description="WebSocket rate limit per minute")
    max_connections: int = Field(default=100, description="Maximum WebSocket connections")
    heartbeat_interval: int = Field(default=30, description="WebSocket heartbeat interval in seconds")
    reconnect_attempts: int = Field(default=5, description="WebSocket reconnection attempts")
    reconnect_delay: int = Field(default=5, description="WebSocket reconnection delay in seconds")
    
    @validator('rate_limit_per_minute', 'max_connections', 'heartbeat_interval', 'reconnect_attempts', 'reconnect_delay')
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError('Value must be positive')
        return v

    class Config:
        env_prefix = "WEBSOCKET_"
        case_sensitive = False


class MetricsConfig(BaseSettings):
    """Metrics and monitoring configuration section."""
    
    prometheus_port: int = Field(default=9090, description="Prometheus metrics port")
    log_level: str = Field(default="INFO", description="Logging level")
    api_rate_limit_per_minute: int = Field(default=1000, description="API rate limit per minute")
    enable_metrics: bool = Field(default=True, description="Enable metrics collection")
    
    @validator('log_level')
    def validate_log_level(cls, v):
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed_levels:
            raise ValueError(f'Log level must be one of {allowed_levels}')
        return v.upper()
        
    @validator('prometheus_port')
    def validate_prometheus_port(cls, v):
        if not 1024 <= v <= 65535:
            raise ValueError('Prometheus port must be between 1024 and 65535')
        return v

    class Config:
        env_prefix = "METRICS_"
        case_sensitive = False


class DatabaseConfig(BaseSettings):
    """Database-specific configuration section."""
    
    pool_size: int = Field(default=10, description="Database connection pool size")
    max_overflow: int = Field(default=20, description="Database connection max overflow")
    pool_timeout: int = Field(default=30, description="Database connection pool timeout")
    echo: bool = Field(default=False, description="Enable SQL query logging")
    
    @validator('pool_size', 'max_overflow', 'pool_timeout')
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError('Value must be positive')
        return v

    class Config:
        env_prefix = "DB_"
        case_sensitive = False


class TradingConfig(BaseSettings):
    """Trading strategy and risk management configuration."""
    
    # Risk Management Configuration
    max_daily_loss_pct: float = Field(default=0.03, description="Maximum daily loss percentage")
    max_drawdown_pct: float = Field(default=0.06, description="Maximum drawdown percentage")
    max_position_pct: float = Field(default=0.10, description="Maximum position size percentage")
    max_leverage: float = Field(default=2.0, description="Maximum leverage")
    
    # Trading hours
    trading_hours_start: str = Field(default="09:30", description="Trading hours start time")
    trading_hours_end: str = Field(default="16:00", description="Trading hours end time")
    timezone: str = Field(default="America/New_York", description="Trading timezone")
    
    # Model Configuration
    model_registry_path: str = Field(
        default="backend/models/saved_models",
        description="Model registry path"
    )
    drift_detection_threshold: float = Field(default=0.05, description="Model drift detection threshold")
    
    # Strategy Configuration
    ensemble_weights: Dict[str, float] = Field(
        default={"lstm": 0.5, "xgboost": 0.3, "random_forest": 0.2},
        description="Ensemble model weights"
    )
    
    # Feature Engineering Configuration
    rsi_period: int = Field(default=14, description="RSI period")
    macd_fast: int = Field(default=12, description="MACD fast period")
    macd_slow: int = Field(default=26, description="MACD slow period")
    macd_signal: int = Field(default=9, description="MACD signal period")
    bollinger_period: int = Field(default=20, description="Bollinger bands period")
    bollinger_std: float = Field(default=2.0, description="Bollinger bands standard deviation")
    
    # Model weights
    lstm_weight: float = Field(default=0.4, description="LSTM model weight")
    xgboost_weight: float = Field(default=0.4, description="XGBoost model weight")
    random_forest_weight: float = Field(default=0.2, description="Random Forest model weight")
    
    # Feature engineering configuration
    feature_mode: str = Field(default="full", description="Feature mode (full/realtime_light)")
    enable_heavy_features: bool = Field(default=True, description="Enable heavy features")
    max_rolling_window: int = Field(default=252, description="Maximum rolling window")
    enable_autocorr_features: bool = Field(default=True, description="Enable autocorrelation features")
    
    # Risk management configuration
    allow_mock_fallbacks: bool = Field(default=True, description="Allow mock fallbacks")
    mock_fallback_warning: bool = Field(default=True, description="Show mock fallback warnings")
    
    # Strategy scaling configuration
    volatility_scale_factor: float = Field(default=10.0, description="Volatility scale factor")
    momentum_scale_factor: float = Field(default=100.0, description="Momentum scale factor")
    
    @validator('max_daily_loss_pct', 'max_drawdown_pct', 'max_position_pct')
    def validate_percentages(cls, v):
        if not 0 < v <= 1:
            raise ValueError('Percentage values must be between 0 and 1')
        return v
        
    @validator('max_leverage')
    def validate_leverage(cls, v):
        if v < 1:
            raise ValueError('Leverage must be at least 1')
        return v

    @validator('feature_mode')
    def validate_feature_mode(cls, v):
        allowed_modes = ['full', 'realtime_light']
        if v not in allowed_modes:
            raise ValueError(f'Feature mode must be one of {allowed_modes}')
        return v

    class Config:
        env_prefix = "TRADING_"
        case_sensitive = False


class Settings(BaseSettings):
    """Main settings class with nested configuration sections."""
    
    app: AppConfig = Field(default_factory=AppConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    alpaca: AlpacaConfig = Field(default_factory=AlpacaConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    websocket: WebsocketConfig = Field(default_factory=WebsocketConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    
    @root_validator
    def validate_cross_section_dependencies(cls, values):
        """Validate dependencies between different configuration sections."""
        app = values.get('app')
        security = values.get('security')
        alpaca = values.get('alpaca')
        
        if app and security:
            # Pass environment to security config for production validation
            if hasattr(security, 'environment'):
                security.environment = app.environment
        
        # Validate that production environment has required credentials
        if app and app.environment == 'production':
            if alpaca and (not alpaca.api_key or not alpaca.secret_key):
                raise ValueError('Alpaca credentials are required in production')
            if security and not security.api_keys:
                raise ValueError('API keys are required in production')
        
        return values

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def validate_required_settings() -> bool:
    """Validate that all required settings are present."""
    settings = get_settings()
    
    required_checks = []
    
    # Check Alpaca credentials in production
    if settings.app.environment == 'production':
        if not settings.alpaca.api_key or not settings.alpaca.secret_key:
            required_checks.append("Alpaca API credentials")
        
        if not settings.security.api_keys:
            required_checks.append("API keys")
            
        if settings.security.jwt_secret_key == "your-super-secret-jwt-key-change-this-in-production":
            required_checks.append("JWT secret key must be changed")
    
    if required_checks:
        raise ValueError(f"Missing required configuration: {', '.join(required_checks)}")
    
    return True


def get_legacy_settings() -> dict:
    """
    Provide backward compatibility mapping for existing code.
    Returns a dictionary with flat keys for legacy access patterns.
    """
    settings = get_settings()
    
    return {
        # App settings
        'environment': settings.app.environment,
        'debug': settings.app.debug,
        'host': settings.app.host,
        'port': settings.app.port,
        'dev_mode': settings.app.dev_mode,
        'cors_origins': settings.app.cors_origins,
        'workers': settings.app.workers,
        'max_connections': settings.app.max_connections,
        'request_timeout': settings.app.request_timeout,
        
        # Security settings
        'jwt_secret_key': settings.security.jwt_secret_key,
        'jwt_algorithm': settings.security.jwt_algorithm,
        'jwt_expire_minutes': settings.security.jwt_expire_minutes,
        'api_keys': settings.security.api_keys,
        
        # Alpaca settings
        'alpaca_api_key': settings.alpaca.api_key,
        'alpaca_secret_key': settings.alpaca.secret_key,
        'alpaca_base_url': settings.alpaca.base_url,
        'alpaca_websocket_url': settings.alpaca.websocket_url,
        'alpaca_paper_trading': settings.alpaca.paper_trading,
        
        # Data settings
        'database_url': settings.data.database_url,
        'redis_url': settings.data.redis_url,
        'redis_host': settings.data.redis_host,
        'redis_port': settings.data.redis_port,
        'redis_db': settings.data.redis_db,
        'reddit_client_id': settings.data.reddit_client_id,
        'reddit_client_secret': settings.data.reddit_client_secret,
        'reddit_user_agent': settings.data.reddit_user_agent,
        'twitter_api_key': settings.data.twitter_api_key,
        'twitter_api_secret': settings.data.twitter_api_secret,
        'twitter_bearer_token': settings.data.twitter_bearer_token,
        'default_symbols': settings.data.default_symbols,
        'subreddit_list': settings.data.subreddit_list,
        'sentiment_update_interval': settings.data.sentiment_update_interval,
        
        # WebSocket settings
        'websocket_rate_limit_per_minute': settings.websocket.rate_limit_per_minute,
        
        # Metrics settings
        'prometheus_port': settings.metrics.prometheus_port,
        'log_level': settings.metrics.log_level,
        'api_rate_limit_per_minute': settings.metrics.api_rate_limit_per_minute,
        
        # Trading settings
        'max_daily_loss_pct': settings.trading.max_daily_loss_pct,
        'max_drawdown_pct': settings.trading.max_drawdown_pct,
        'max_position_pct': settings.trading.max_position_pct,
        'max_leverage': settings.trading.max_leverage,
        'trading_hours_start': settings.trading.trading_hours_start,
        'trading_hours_end': settings.trading.trading_hours_end,
        'timezone': settings.trading.timezone,
        'model_registry_path': settings.trading.model_registry_path,
        'drift_detection_threshold': settings.trading.drift_detection_threshold,
        'ensemble_weights': settings.trading.ensemble_weights,
    }


# Validate settings on import (unless explicitly skipped)
if os.getenv("SKIP_VALIDATION") != "true":
    try:
        validate_required_settings()
    except ValueError as e:
        print(f"Configuration Warning: {e}")
        print("Please set the required environment variables or create a .env file.")
