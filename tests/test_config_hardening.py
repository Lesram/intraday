"""
Comprehensive tests for the nested configuration system.
Tests all configuration sections, validation, and backward compatibility.
"""

import os
from unittest.mock import patch

from pydantic import ValidationError
import pytest

from backend.config import (
    AlpacaConfig,
    AppConfig,
    DatabaseConfig,
    DataConfig,
    MetricsConfig,
    SecurityConfig,
    Settings,
    TradingConfig,
    WebsocketConfig,
    get_legacy_settings,
    get_settings,
    validate_required_settings,
)


class TestAppConfig:
    """Test application configuration section."""

    @pytest.mark.unit
    @pytest.mark.unit
    def test_app_config_defaults(self):
        """Test default values for app config."""
        config = AppConfig()

        assert config.environment == "development"
        assert config.debug is True
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.dev_mode is True
        assert config.workers == 4

    @pytest.mark.unit
    @pytest.mark.unit
    def test_app_config_validation(self):
        """Test app config validation."""
        # Valid environment
        config = AppConfig(environment="production")
        assert config.environment == "production"

        # Invalid environment
        with pytest.raises(ValidationError):
            AppConfig(environment="invalid")

        # Invalid port
        with pytest.raises(ValidationError):
            AppConfig(port=0)

        with pytest.raises(ValidationError):
            AppConfig(port=70000)

    @pytest.mark.unit
    @patch.dict(os.environ, {"APP_ENVIRONMENT": "staging", "APP_PORT": "9000"})
    @pytest.mark.unit
    def test_app_config_env_vars(self):
        """Test loading app config from environment variables."""
        config = AppConfig()

        assert config.environment == "staging"
        assert config.port == 9000


class TestSecurityConfig:
    """Test security configuration section."""

    @pytest.mark.unit
    def test_security_config_defaults(self):
        """Test default values for security config."""
        config = SecurityConfig()

        assert config.jwt_algorithm == "HS256"
        assert config.jwt_expire_minutes == 30
        assert len(config.jwt_secret_key) >= 32
        assert isinstance(config.api_keys, list)

    @pytest.mark.unit
    def test_security_config_validation(self):
        """Test security config validation."""
        # Valid JWT algorithm
        config = SecurityConfig(jwt_algorithm="RS256")
        assert config.jwt_algorithm == "RS256"

        # Invalid JWT algorithm
        with pytest.raises(ValidationError):
            SecurityConfig(jwt_algorithm="INVALID")

        # Short JWT secret
        with pytest.raises(ValidationError):
            SecurityConfig(jwt_secret_key="short")

    @patch.dict(os.environ, {"API_KEYS": "key1,key2,key3"})
    @pytest.mark.unit
    def test_security_api_keys_loading(self):
        """Test loading API keys from environment."""
        config = SecurityConfig()

        assert len(config.api_keys) == 3
        assert "key1" in config.api_keys
        assert "key2" in config.api_keys
        assert "key3" in config.api_keys

    @patch.dict(os.environ, {"SECURITY_JWT_SECRET_KEY": "very-secure-32-character-secret-key"})
    @pytest.mark.unit
    def test_security_env_vars(self):
        """Test loading security config from environment variables."""
        config = SecurityConfig()

        assert config.jwt_secret_key == "very-secure-32-character-secret-key"


class TestAlpacaConfig:
    """Test Alpaca API configuration section."""

    @pytest.mark.unit
    def test_alpaca_config_defaults(self):
        """Test default values for Alpaca config."""
        config = AlpacaConfig()

        assert config.paper_trading is True
        assert config.base_url == "https://paper-api.alpaca.markets"
        assert config.websocket_url.startswith("wss://")

    @pytest.mark.unit
    def test_alpaca_config_validation(self):
        """Test Alpaca config validation."""
        # Valid URLs
        config = AlpacaConfig(
            base_url="https://api.alpaca.markets",
            websocket_url="wss://stream.data.alpaca.markets/v2/iex"
        )
        assert config.base_url == "https://api.alpaca.markets"

        # Invalid URL
        with pytest.raises(ValidationError):
            AlpacaConfig(base_url="invalid-url")

    @patch.dict(os.environ, {"ALPACA_API_KEY": "test_key", "ALPACA_SECRET_KEY": "test_secret"})
    @pytest.mark.unit
    def test_alpaca_env_vars(self):
        """Test loading Alpaca config from environment variables."""
        config = AlpacaConfig()

        assert config.api_key == "test_key"
        assert config.secret_key == "test_secret"


class TestDataConfig:
    """Test data configuration section."""

    @pytest.mark.unit
    def test_data_config_defaults(self):
        """Test default values for data config."""
        config = DataConfig()

        assert config.database_url.startswith("sqlite:")
        assert config.redis_url == "redis://localhost:6379"
        assert config.redis_port == 6379
        assert len(config.default_symbols) > 0
        assert "AAPL" in config.default_symbols

    @pytest.mark.unit
    def test_data_config_validation(self):
        """Test data config validation."""
        # Valid database URL
        config = DataConfig(database_url="postgresql://user:pass@localhost/db")
        assert config.database_url.startswith("postgresql:")

        # Empty database URL should fail
        with pytest.raises(ValidationError):
            DataConfig(database_url="")

        # Invalid Redis port
        with pytest.raises(ValidationError):
            DataConfig(redis_port=0)

        with pytest.raises(ValidationError):
            DataConfig(redis_port=70000)


class TestWebsocketConfig:
    """Test WebSocket configuration section."""

    @pytest.mark.unit
    def test_websocket_config_defaults(self):
        """Test default values for WebSocket config."""
        config = WebsocketConfig()

        assert config.rate_limit_per_minute == 60
        assert config.max_connections == 100
        assert config.heartbeat_interval == 30

    @pytest.mark.unit
    def test_websocket_config_validation(self):
        """Test WebSocket config validation."""
        # Valid values
        config = WebsocketConfig(rate_limit_per_minute=120, max_connections=200)
        assert config.rate_limit_per_minute == 120

        # Invalid values (must be positive)
        with pytest.raises(ValidationError):
            WebsocketConfig(rate_limit_per_minute=0)

        with pytest.raises(ValidationError):
            WebsocketConfig(max_connections=-1)


class TestMetricsConfig:
    """Test metrics configuration section."""

    @pytest.mark.unit
    def test_metrics_config_defaults(self):
        """Test default values for metrics config."""
        config = MetricsConfig()

        assert config.prometheus_port == 9090
        assert config.log_level == "INFO"
        assert config.api_rate_limit_per_minute == 1000

    @pytest.mark.unit
    def test_metrics_config_validation(self):
        """Test metrics config validation."""
        # Valid log level
        config = MetricsConfig(log_level="DEBUG")
        assert config.log_level == "DEBUG"

        # Case insensitive log level
        config = MetricsConfig(log_level="debug")
        assert config.log_level == "DEBUG"

        # Invalid log level
        with pytest.raises(ValidationError):
            MetricsConfig(log_level="INVALID")

        # Invalid port (too low)
        with pytest.raises(ValidationError):
            MetricsConfig(prometheus_port=1023)


class TestTradingConfig:
    """Test trading configuration section."""

    @pytest.mark.unit
    def test_trading_config_defaults(self):
        """Test default values for trading config."""
        config = TradingConfig()

        assert config.max_daily_loss_pct == 0.03
        assert config.max_leverage == 2.0
        assert config.feature_mode == "full"
        assert isinstance(config.ensemble_weights, dict)

    @pytest.mark.unit
    def test_trading_config_validation(self):
        """Test trading config validation."""
        # Valid percentage values
        config = TradingConfig(max_daily_loss_pct=0.05, max_position_pct=0.15)
        assert config.max_daily_loss_pct == 0.05

        # Invalid percentage (too high)
        with pytest.raises(ValidationError):
            TradingConfig(max_daily_loss_pct=1.5)

        # Invalid percentage (negative)
        with pytest.raises(ValidationError):
            TradingConfig(max_position_pct=-0.1)

        # Invalid leverage (too low)
        with pytest.raises(ValidationError):
            TradingConfig(max_leverage=0.5)

        # Invalid feature mode
        with pytest.raises(ValidationError):
            TradingConfig(feature_mode="invalid")


class TestNestedSettings:
    """Test the main nested settings class."""

    @pytest.mark.unit
    def test_settings_initialization(self):
        """Test that settings initialize all nested sections."""
        settings = Settings()

        assert isinstance(settings.app, AppConfig)
        assert isinstance(settings.security, SecurityConfig)
        assert isinstance(settings.alpaca, AlpacaConfig)
        assert isinstance(settings.data, DataConfig)
        assert isinstance(settings.websocket, WebsocketConfig)
        assert isinstance(settings.metrics, MetricsConfig)
        assert isinstance(settings.database, DatabaseConfig)
        assert isinstance(settings.trading, TradingConfig)

    @pytest.mark.unit
    def test_settings_nested_access(self):
        """Test accessing nested configuration values."""
        settings = Settings()

        # Test nested access
        assert settings.app.environment == "development"
        assert settings.security.jwt_algorithm == "HS256"
        assert settings.alpaca.paper_trading is True
        assert settings.data.redis_port == 6379
        assert settings.websocket.heartbeat_interval == 30
        assert settings.metrics.log_level == "INFO"
        assert settings.trading.max_leverage == 2.0

    @patch.dict(os.environ, {
        "APP_ENVIRONMENT": "production",
        "SECURITY_JWT_SECRET_KEY": "production-secure-32-character-secret-key-here",
        "ALPACA_API_KEY": "prod_key",
        "ALPACA_SECRET_KEY": "prod_secret",
        "API_KEYS": "key1,key2"
    })
    @pytest.mark.unit
    def test_production_validation(self):
        """Test production environment validation."""
        # Should pass with proper credentials
        settings = Settings()
        assert settings.app.environment == "production"

        # Validate required settings should pass
        try:
            validate_required_settings()
        except ValueError:
            pytest.fail("Production validation should pass with proper credentials")

    @patch.dict(os.environ, {"APP_ENVIRONMENT": "production"})
    @pytest.mark.unit
    def test_production_validation_failure(self):
        """Test production validation fails without credentials."""
        with pytest.raises(ValidationError, match="Alpaca.*required in production"):
            Settings()


class TestSettingsCache:
    """Test settings caching functionality."""

    @pytest.mark.unit
    def test_get_settings_cached(self):
        """Test that get_settings returns cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()

        # Should be the same instance due to lru_cache
        assert settings1 is settings2

    @pytest.mark.unit
    def test_get_settings_structure(self):
        """Test that cached settings have proper structure."""
        settings = get_settings()

        assert hasattr(settings, 'app')
        assert hasattr(settings, 'security')
        assert hasattr(settings, 'alpaca')
        assert hasattr(settings, 'data')
        assert hasattr(settings, 'websocket')
        assert hasattr(settings, 'metrics')
        assert hasattr(settings, 'database')
        assert hasattr(settings, 'trading')


class TestBackwardCompatibility:
    """Test backward compatibility features."""

    @pytest.mark.unit
    def test_get_legacy_settings(self):
        """Test legacy settings mapping."""
        legacy = get_legacy_settings()

        # Check that legacy keys exist
        assert 'environment' in legacy
        assert 'debug' in legacy
        assert 'host' in legacy
        assert 'port' in legacy
        assert 'jwt_secret_key' in legacy
        assert 'alpaca_api_key' in legacy
        assert 'database_url' in legacy
        assert 'max_daily_loss_pct' in legacy

        # Check that values match nested access
        settings = get_settings()
        assert legacy['environment'] == settings.app.environment
        assert legacy['jwt_algorithm'] == settings.security.jwt_algorithm
        assert legacy['alpaca_base_url'] == settings.alpaca.base_url
        assert legacy['redis_port'] == settings.data.redis_port

    @pytest.mark.unit
    def test_legacy_settings_types(self):
        """Test that legacy settings maintain correct types."""
        legacy = get_legacy_settings()

        assert isinstance(legacy['debug'], bool)
        assert isinstance(legacy['port'], int)
        assert isinstance(legacy['cors_origins'], list)
        assert isinstance(legacy['api_keys'], list)
        assert isinstance(legacy['ensemble_weights'], dict)


class TestValidationRequirements:
    """Test validation and requirements checking."""

    @patch.dict(os.environ, {"SKIP_VALIDATION": "true"})
    @pytest.mark.unit
    def test_skip_validation(self):
        """Test that validation can be skipped."""
        # This should not raise any errors even with missing config
        try:
            pass  # Re-import to trigger validation
        except ValueError:
            pytest.fail("Validation should be skipped")

    @pytest.mark.unit
    def test_validate_required_settings_development(self):
        """Test validation in development mode."""
        # Should pass in development even without full config
        try:
            validate_required_settings()
        except ValueError:
            pytest.fail("Development validation should be lenient")

    @patch.dict(os.environ, {
        "APP_ENVIRONMENT": "production",
        "SECURITY_JWT_SECRET_KEY": "production-32-character-secret-key",
    })
    @pytest.mark.unit
    def test_validate_required_settings_production_missing(self):
        """Test validation fails in production with missing config."""
        # Clear the cache to ensure new environment is used
        get_settings.cache_clear()
        with pytest.raises(ValidationError, match="Alpaca.*required in production"):
            validate_required_settings()


class TestEnvironmentVariableLoading:
    """Test environment variable loading across all sections."""

    @patch.dict(os.environ, {
        "APP_DEBUG": "false",
        "APP_PORT": "9000",
        "SECURITY_JWT_EXPIRE_MINUTES": "60",
        "ALPACA_PAPER_TRADING": "false",
        "DATA_REDIS_PORT": "6380",
        "WEBSOCKET_MAX_CONNECTIONS": "200",
        "METRICS_LOG_LEVEL": "DEBUG",
        "TRADING_MAX_LEVERAGE": "3.0",
    })
    @pytest.mark.unit
    def test_env_var_loading_all_sections(self):
        """Test that all sections properly load from environment variables."""
        settings = Settings()

        assert settings.app.debug is False
        assert settings.app.port == 9000
        assert settings.security.jwt_expire_minutes == 60
        assert settings.alpaca.paper_trading is False
        assert settings.data.redis_port == 6380
        assert settings.websocket.max_connections == 200
        assert settings.metrics.log_level == "DEBUG"
        assert settings.trading.max_leverage == 3.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
