"""
Configuration settings for the algorithmic trading platform.
Uses pydantic-settings BaseSettings pattern with nested configuration sections.
Compatible with Pydantic V2.
"""

from functools import lru_cache
import os

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    """Application configuration section."""

    model_config = ConfigDict(env_prefix="APP_", case_sensitive=False)

    environment: str = Field(default="development", description="Application environment")
    debug: bool = Field(default=True, description="Enable debug mode")
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=4, description="Number of workers")
    max_connections: int = Field(default=1000, description="Maximum connections")
    request_timeout: int = Field(default=30, description="Request timeout in seconds")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="CORS allowed origins"
    )
    dev_mode: bool = Field(default=True, description="Development mode")
    version: str = Field(default="1.0.0", description="Application version")
    log_level: str = Field(default="INFO", description="Application log level")

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

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed_levels:
            raise ValueError(f'Log level must be one of {allowed_levels}')
        return v.upper()


class SecurityConfig(BaseSettings):
    """Security configuration section."""

    model_config = ConfigDict(env_prefix="SECURITY_", case_sensitive=False)

    jwt_secret_key: str = Field(
        default="your-super-secret-jwt-key-change-this-in-production",
        description="JWT secret key"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expire_minutes: int = Field(default=30, description="JWT expiration minutes")
    jwt_issuer: str = Field(default="algotrading-platform", description="JWT issuer")
    jwt_audience: str = Field(default="algotrading-users", description="JWT audience")
    api_keys: list[str] = Field(default_factory=list, description="API keys for authentication")

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

    def __init__(self, **data):
        super().__init__(**data)
        # Load API keys from environment
        api_keys_env = os.getenv("API_KEYS", "")
        if api_keys_env:
            self.api_keys = [key.strip() for key in api_keys_env.split(",") if key.strip()]


class AlpacaConfig(BaseSettings):
    """Alpaca API configuration section."""

    model_config = ConfigDict(env_prefix="ALPACA_", case_sensitive=False)

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

    @field_validator('api_key', 'secret_key')
    @classmethod
    def validate_credentials(cls, v, info):
        if not v and os.getenv('APP_ENVIRONMENT') == 'production':
            raise ValueError(f'Alpaca {info.field_name} is required in production')
        return v

    @field_validator('base_url', 'websocket_url')
    @classmethod
    def validate_urls(cls, v):
        if not v.startswith(('http://', 'https://', 'ws://', 'wss://')):
            raise ValueError('URL must start with http://, https://, ws://, or wss://')
        return v


class DataConfig(BaseSettings):
    """Data sources configuration section."""

    model_config = ConfigDict(env_prefix="DATA_", case_sensitive=False)

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
    default_symbols: list[str] = Field(
        default=[
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "BTC/USD", "ETH/USD"
        ],
        description="Default trading symbols"
    )
    subreddit_list: list[str] = Field(
        default=["StockMarket", "investing", "wallstreetbets", "cryptocurrency", "Bitcoin"],
        description="List of subreddits for sentiment analysis"
    )
    sentiment_update_interval: int = Field(default=300, description="Sentiment update interval in seconds")

    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v):
        if not v:
            raise ValueError('Database URL is required')
        return v

    @field_validator('redis_port')
    @classmethod
    def validate_redis_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError('Redis port must be between 1 and 65535')
        return v


class WebsocketConfig(BaseSettings):
    """WebSocket configuration section."""

    model_config = ConfigDict(env_prefix="WEBSOCKET_", case_sensitive=False)

    rate_limit_per_minute: int = Field(default=60, description="WebSocket rate limit per minute")
    max_connections: int = Field(default=100, description="Maximum WebSocket connections")
    heartbeat_interval: int = Field(default=30, description="WebSocket heartbeat interval in seconds")
    reconnect_attempts: int = Field(default=5, description="WebSocket reconnection attempts")
    reconnect_delay: int = Field(default=5, description="WebSocket reconnection delay in seconds")

    @field_validator('rate_limit_per_minute', 'max_connections', 'heartbeat_interval', 'reconnect_attempts', 'reconnect_delay')
    @classmethod
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError('Value must be positive')
        return v


class MetricsConfig(BaseSettings):
    """Metrics and monitoring configuration section."""

    model_config = ConfigDict(env_prefix="METRICS_", case_sensitive=False)

    prometheus_port: int = Field(default=9090, description="Prometheus metrics port")
    log_level: str = Field(default="INFO", description="Logging level")
    api_rate_limit_per_minute: int = Field(default=1000, description="API rate limit per minute")
    enable_metrics: bool = Field(default=True, description="Enable metrics collection")

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        allowed_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in allowed_levels:
            raise ValueError(f'Log level must be one of {allowed_levels}')
        return v.upper()

    @field_validator('prometheus_port')
    @classmethod
    def validate_prometheus_port(cls, v):
        if not 1024 <= v <= 65535:
            raise ValueError('Prometheus port must be between 1024 and 65535')
        return v


class DatabaseConfig(BaseSettings):
    """Database-specific configuration section."""

    model_config = ConfigDict(env_prefix="DB_", case_sensitive=False)

    pool_size: int = Field(default=10, description="Database connection pool size")
    max_overflow: int = Field(default=20, description="Database connection max overflow")
    pool_timeout: int = Field(default=30, description="Database connection pool timeout")
    echo: bool = Field(default=False, description="Enable SQL query logging")

    @field_validator('pool_size', 'max_overflow', 'pool_timeout')
    @classmethod
    def validate_positive(cls, v):
        if v <= 0:
            raise ValueError('Value must be positive')
        return v


class TradingConfig(BaseSettings):
    """Trading strategy and risk management configuration."""

    model_config = ConfigDict(env_prefix="TRADING_", case_sensitive=False)

    # Risk Management Configuration
    max_daily_loss_pct: float = Field(default=0.03, description="Maximum daily loss percentage")
    max_drawdown_pct: float = Field(default=0.06, description="Maximum drawdown percentage")
    max_position_pct: float = Field(default=0.10, description="Maximum position size percentage")
    max_position_size: float = Field(default=10000.0, description="Maximum position size in dollars")
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
    ensemble_weights: dict[str, float] = Field(
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

    @field_validator('max_daily_loss_pct', 'max_drawdown_pct', 'max_position_pct')
    @classmethod
    def validate_percentages(cls, v):
        if not 0 < v <= 1:
            raise ValueError('Percentage values must be between 0 and 1')
        return v

    @field_validator('max_leverage')
    @classmethod
    def validate_leverage(cls, v):
        if v < 1:
            raise ValueError('Leverage must be at least 1')
        return v

    @field_validator('feature_mode')
    @classmethod
    def validate_feature_mode(cls, v):
        allowed_modes = ['full', 'realtime_light']
        if v not in allowed_modes:
            raise ValueError(f'Feature mode must be one of {allowed_modes}')
        return v


class OutboxConfig(BaseSettings):
    """Outbox and idempotency configuration."""

    model_config = ConfigDict(env_prefix="OUTBOX_", case_sensitive=False)

    enabled: bool = Field(default=True, description="Enable outbox pattern")
    poll_interval_ms: int = Field(default=200, description="Poll interval in milliseconds")
    batch_size: int = Field(default=100, description="Batch size for processing")
    max_attempts: int = Field(default=6, description="Maximum retry attempts")
    base_delay_ms: int = Field(default=200, description="Base delay for exponential backoff")
    max_delay_ms: int = Field(default=10000, description="Maximum delay between retries")
    jitter_ms: int = Field(default=150, description="Jitter for backoff randomization")
    broker_idempotency_header: str = Field(
        default="X-Idempotency-Key",
        description="HTTP header name for broker idempotency"
    )

    @field_validator('batch_size')
    @classmethod
    def validate_batch_size(cls, v):
        if v <= 0:
            raise ValueError('Batch size must be greater than 0')
        return v

    @field_validator('max_attempts')
    @classmethod
    def validate_max_attempts(cls, v):
        if not 1 <= v <= 10:
            raise ValueError('Max attempts must be between 1 and 10')
        return v

    @field_validator('base_delay_ms', 'max_delay_ms')
    @classmethod
    def validate_delays(cls, v):
        if v <= 0:
            raise ValueError('Delay values must be greater than 0')
        return v

    @model_validator(mode='after')
    def validate_delay_ordering(self):
        if self.base_delay_ms > self.max_delay_ms:
            raise ValueError('Base delay must not exceed max delay')
        return self


class ObservabilityConfig(BaseSettings):
    """Observability configuration for OpenTelemetry, Prometheus, and logging."""

    model_config = ConfigDict(env_prefix="OBS_", case_sensitive=False)

    # General observability settings
    enabled: bool = Field(default=True, description="Enable observability features")

    # Prometheus metrics settings
    prometheus_enabled: bool = Field(default=True, description="Enable Prometheus metrics")
    prometheus_path: str = Field(default="/metrics", description="Prometheus metrics endpoint path")
    metric_namespace: str = Field(default="intraday", description="Prometheus metric namespace")
    latency_buckets_ms: str = Field(
        default="5,10,25,50,100,250,500,1000,2500,5000",
        description="Prometheus latency histogram buckets in milliseconds"
    )

    # OpenTelemetry tracing settings
    otel_enabled: bool = Field(default=True, description="Enable OpenTelemetry tracing")
    otel_service_name: str = Field(default="intraday-backend", description="OpenTelemetry service name")
    otel_exporter_otlp_endpoint: str | None = Field(
        default="http://localhost:4317",
        description="OpenTelemetry OTLP exporter endpoint"
    )
    otel_exporter_protocol: str = Field(
        default="grpc",
        description="OpenTelemetry exporter protocol (grpc or http/protobuf)"
    )
    otel_sampler: str = Field(
        default="parentbased_traceidratio",
        description="OpenTelemetry sampler type"
    )
    otel_sampler_arg: float = Field(
        default=0.1,
        description="OpenTelemetry sampler argument (e.g., sampling ratio)"
    )

    # Log correlation settings
    log_trace_correlation: bool = Field(
        default=True,
        description="Enable trace/span correlation in logs"
    )

    @field_validator('latency_buckets_ms')
    @classmethod
    def validate_latency_buckets(cls, v):
        """Validate and parse latency buckets."""
        try:
            buckets = [int(x.strip()) for x in v.split(',')]
            if not all(b > 0 for b in buckets):
                raise ValueError('All latency buckets must be positive')
            if buckets != sorted(buckets):
                raise ValueError('Latency buckets must be in ascending order')
            return v
        except (ValueError, AttributeError) as e:
            raise ValueError(f'Invalid latency buckets format: {e}')

    @field_validator('prometheus_path')
    @classmethod
    def validate_prometheus_path(cls, v):
        """Validate Prometheus metrics path."""
        if not v.startswith('/'):
            raise ValueError('Prometheus path must start with /')
        return v

    @field_validator('otel_exporter_protocol')
    @classmethod
    def validate_otel_protocol(cls, v):
        """Validate OpenTelemetry exporter protocol."""
        allowed_protocols = ['grpc', 'http/protobuf']
        if v not in allowed_protocols:
            raise ValueError(f'OpenTelemetry protocol must be one of {allowed_protocols}')
        return v

    @field_validator('otel_sampler_arg')
    @classmethod
    def validate_sampler_arg(cls, v):
        """Validate OpenTelemetry sampler argument."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('OpenTelemetry sampler argument must be between 0.0 and 1.0')
        return v

    @model_validator(mode='after')
    def validate_otel_endpoint(self):
        """Validate OTEL endpoint is provided when tracing is enabled in production."""
        if (self.otel_enabled and
            getattr(self, '_env', 'dev') == 'prod' and
            not self.otel_exporter_otlp_endpoint):
            raise ValueError('OpenTelemetry OTLP endpoint is required in production')
        return self

    def get_latency_buckets(self) -> list[float]:
        """Get parsed latency buckets as floats (in seconds)."""
        buckets_ms = [int(x.strip()) for x in self.latency_buckets_ms.split(',')]
        return [b / 1000.0 for b in buckets_ms]  # Convert to seconds


class MLOpsConfig(BaseSettings):
    """MLOps configuration for model registry, drift detection, and inference telemetry."""

    model_config = ConfigDict(env_prefix="MLOPS_", case_sensitive=False)

    # Model registry settings
    registry_root: str = Field(
        default="artifacts",
        description="Root directory for on-disk model registry"
    )

    # Drift detection thresholds
    drift_psi_warn: float = Field(
        default=0.1,
        description="PSI threshold for drift warning"
    )
    drift_psi_alert: float = Field(
        default=0.25,
        description="PSI threshold for drift alert"
    )
    perf_epsilon: float = Field(
        default=0.01,
        description="Performance epsilon for stability checks"
    )
    perf_alert_drop: float = Field(
        default=0.05,
        description="Performance drop threshold for alert (5% degradation)"
    )

    # Inference telemetry settings
    inference_log_max_rows: int = Field(
        default=200000,
        description="Maximum rows in inference log before rotation"
    )
    inference_telemetry_enabled: bool = Field(
        default=True,
        description="Enable inference telemetry logging"
    )

    # Model deployment settings
    auto_promotion_enabled: bool = Field(
        default=False,
        description="Enable automatic model promotion based on performance"
    )
    champion_challenger_enabled: bool = Field(
        default=True,
        description="Enable champion-challenger testing"
    )

    # Retraining settings
    auto_retrain_enabled: bool = Field(
        default=False,
        description="Enable automatic model retraining on drift"
    )
    retrain_drift_threshold: float = Field(
        default=0.7,
        description="Drift severity threshold (0-1) to trigger retraining"
    )

    @field_validator('drift_psi_warn', 'drift_psi_alert')
    @classmethod
    def validate_psi_thresholds(cls, v, info):
        """Validate PSI threshold values."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f'PSI threshold {info.field_name} must be between 0.0 and 1.0')
        return v

    @field_validator('perf_alert_drop')
    @classmethod
    def validate_perf_drop(cls, v):
        """Validate performance drop threshold."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('Performance drop threshold must be between 0.0 and 1.0')
        return v

    @field_validator('retrain_drift_threshold')
    @classmethod
    def validate_retrain_threshold(cls, v):
        """Validate drift threshold for retraining."""
        if not 0.0 <= v <= 1.0:
            raise ValueError('Retrain drift threshold must be between 0.0 and 1.0')
        return v

    @field_validator('inference_log_max_rows')
    @classmethod
    def validate_log_max_rows(cls, v):
        """Validate max rows for inference log."""
        if v < 1000:
            raise ValueError('Inference log max rows must be at least 1000')
        return v

    @model_validator(mode='after')
    def validate_psi_order(self):
        """Validate PSI thresholds are in correct order."""
        if self.drift_psi_warn >= self.drift_psi_alert:
            raise ValueError('PSI warning threshold must be less than alert threshold')
        return self


class Settings(BaseSettings):
    """Main settings class with nested configuration sections."""

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra='ignore'  # Ignore extra fields from environment
    )

    app: AppConfig = Field(default_factory=AppConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    alpaca: AlpacaConfig = Field(default_factory=AlpacaConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    websocket: WebsocketConfig = Field(default_factory=WebsocketConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    outbox: OutboxConfig = Field(default_factory=OutboxConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    mlops: MLOpsConfig = Field(default_factory=MLOpsConfig)

    def __init__(self, **data):
        """Initialize with legacy environment variable mapping."""
        super().__init__(**data)

        # Map legacy environment variables to nested structure
        self._map_legacy_env_vars()

    def _map_legacy_env_vars(self):
        """Map legacy flat environment variables to nested structure."""
        # Map legacy variables that might not have proper prefixes
        legacy_mappings = {
            # App mappings
            'ENVIRONMENT': 'app.environment',
            'DEBUG': 'app.debug',
            'HOST': 'app.host',
            'PORT': 'app.port',
            'WORKERS': 'app.workers',
            'MAX_CONNECTIONS': 'app.max_connections',
            'REQUEST_TIMEOUT': 'app.request_timeout',
            'DEV_MODE': 'app.dev_mode',

            # Security mappings
            'JWT_SECRET_KEY': 'security.jwt_secret_key',
            'API_SECRET_KEY': 'security.jwt_secret_key',  # Legacy alias
            'JWT_ALGORITHM': 'security.jwt_algorithm',
            'ALGORITHM': 'security.jwt_algorithm',  # Legacy alias
            'JWT_EXPIRE_MINUTES': 'security.jwt_expire_minutes',

            # Alpaca mappings
            'ALPACA_API_KEY': 'alpaca.api_key',
            'ALPACA_SECRET_KEY': 'alpaca.secret_key',
            'ALPACA_BASE_URL': 'alpaca.base_url',
            'ALPACA_PAPER_TRADING': 'alpaca.paper_trading',

            # Data mappings
            'DATABASE_URL': 'data.database_url',
            'REDIS_URL': 'data.redis_url',
            'REDIS_HOST': 'data.redis_host',
            'REDIS_PORT': 'data.redis_port',
            'REDIS_DB': 'data.redis_db',
            'REDDIT_CLIENT_ID': 'data.reddit_client_id',
            'REDDIT_CLIENT_SECRET': 'data.reddit_client_secret',
            'REDDIT_USER_AGENT': 'data.reddit_user_agent',
            'TWITTER_API_KEY': 'data.twitter_api_key',
            'TWITTER_API_SECRET': 'data.twitter_api_secret',
            'TWITTER_BEARER_TOKEN': 'data.twitter_bearer_token',

            # Metrics mappings
            'LOG_LEVEL': 'metrics.log_level',
            'PROMETHEUS_PORT': 'metrics.prometheus_port',

            # Trading mappings
            'MAX_DAILY_LOSS_PCT': 'trading.max_daily_loss_pct',
            'MAX_DRAWDOWN_PCT': 'trading.max_drawdown_pct',
            'MAX_POSITION_PCT': 'trading.max_position_pct',
            'MAX_POSITION_SIZE': 'trading.max_position_size',
            'MAX_LEVERAGE': 'trading.max_leverage',
            'MODEL_REGISTRY_PATH': 'trading.model_registry_path',
            'DRIFT_DETECTION_THRESHOLD': 'trading.drift_detection_threshold',
        }

        for env_var, nested_path in legacy_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                self._set_nested_value(nested_path, env_value)

    def _set_nested_value(self, path: str, value: str):
        """Set a nested value using dot notation path."""
        parts = path.split('.')
        if len(parts) == 2:
            section_name, field_name = parts
            section = getattr(self, section_name)

            # Convert string values to appropriate types based on field annotation
            field_info = section.__class__.model_fields.get(field_name)
            if field_info:
                # Handle type conversion
                if field_info.annotation == bool:
                    value = value.lower() in ('true', '1', 'yes', 'on')
                elif field_info.annotation == int:
                    value = int(value)
                elif field_info.annotation == float:
                    value = float(value)

                setattr(section, field_name, value)

    @model_validator(mode='after')
    def validate_cross_section_dependencies(self):
        """Validate dependencies between different configuration sections."""
        # Validate that production environment has required credentials
        if self.app.environment == 'production':
            if not self.alpaca.api_key or not self.alpaca.secret_key:
                raise ValueError('Alpaca credentials are required in production')
            if not self.security.api_keys:
                raise ValueError('API keys are required in production')
            if self.security.jwt_secret_key == "your-super-secret-jwt-key-change-this-in-production":
                raise ValueError('JWT secret key must be changed in production')

        return self


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
        'security_dev_mode': settings.app.dev_mode,  # Legacy alias
        'cors_origins': settings.app.cors_origins,
        'workers': settings.app.workers,
        'max_connections': settings.app.max_connections,
        'request_timeout': settings.app.request_timeout,

        # Security settings
        'jwt_secret_key': settings.security.jwt_secret_key,
        'jwt_algorithm': settings.security.jwt_algorithm,
        'jwt_expire_minutes': settings.security.jwt_expire_minutes,
        'jwt_access_token_expire_minutes': settings.security.jwt_expire_minutes,  # Legacy alias
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
        'max_position_size': settings.trading.max_position_size,
        'max_leverage': settings.trading.max_leverage,
        'trading_hours_start': settings.trading.trading_hours_start,
        'trading_hours_end': settings.trading.trading_hours_end,
        'timezone': settings.trading.timezone,
        'model_registry_path': settings.trading.model_registry_path,
        'drift_detection_threshold': settings.trading.drift_detection_threshold,
        'ensemble_weights': settings.trading.ensemble_weights,
    }


class LegacySettings:
    """Legacy settings wrapper for backward compatibility."""

    def __init__(self):
        self._settings = get_settings()
        self._legacy_map = get_legacy_settings()

    def __getattr__(self, name: str):
        """Get attribute using legacy naming."""
        if name in self._legacy_map:
            return self._legacy_map[name]

        # Check if it exists in nested structure
        if name == 'security_dev_mode':
            return self._settings.app.dev_mode
        elif name == 'jwt_access_token_expire_minutes':
            return self._settings.security.jwt_expire_minutes

        # Try to find in nested settings
        for section_name in ['app', 'security', 'alpaca', 'data', 'websocket', 'metrics', 'database', 'trading']:
            section = getattr(self._settings, section_name)
            if hasattr(section, name):
                return getattr(section, name)

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


# Legacy support - provide instance for backward compatibility
settings = LegacySettings()

# Validate settings on import (unless explicitly skipped)
if os.getenv("SKIP_VALIDATION") != "true":
    try:
        validate_required_settings()
    except ValueError as e:
        print(f"Configuration Warning: {e}")
        print("Please set the required environment variables or create a .env file.")
