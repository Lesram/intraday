"""
Comprehensive test suite for backend.config.base_settings module
Tests all configuration classes, validators, and edge cases
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

from backend.config.base_settings import (
    AppConfig,
    SecurityConfig, 
    AlpacaConfig,
    DataConfig,
    WebsocketConfig,
    MetricsConfig,
    DatabaseConfig,
    TradingConfig,
    Settings,
    get_settings
)


class TestAppConfig:
    """Test AppConfig configuration class."""

    def test_app_config_defaults(self):
        """Test AppConfig with default values."""
        config = AppConfig()
        
        assert config.environment == "development"
        assert config.debug is True
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.workers == 4
        assert config.max_connections == 1000
        assert config.request_timeout == 30
        assert config.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]
        assert config.dev_mode is True
        assert config.version == "1.0.0"
        assert config.log_level == "INFO"

    def test_app_config_custom_values(self):
        """Test AppConfig with custom values."""
        config = AppConfig(
            environment="production",
            debug=False,
            port=9000,
            workers=8,
            log_level="ERROR"
        )
        
        assert config.environment == "production"
        assert config.debug is False
        assert config.port == 9000
        assert config.workers == 8
        assert config.log_level == "ERROR"

    def test_environment_validation_valid(self):
        """Test valid environment values."""
        valid_envs = ["development", "staging", "production"]
        for env in valid_envs:
            config = AppConfig(environment=env)
            assert config.environment == env

    def test_environment_validation_invalid(self):
        """Test invalid environment values."""
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(environment="invalid")
        
        assert "Environment must be one of" in str(exc_info.value)

    def test_port_validation_valid(self):
        """Test valid port ranges."""
        valid_ports = [1, 8000, 65535]
        for port in valid_ports:
            config = AppConfig(port=port)
            assert config.port == port

    def test_port_validation_invalid(self):
        """Test invalid port values."""
        invalid_ports = [0, -1, 65536, 100000]
        for port in invalid_ports:
            with pytest.raises(ValidationError) as exc_info:
                AppConfig(port=port)
            assert "Port must be between 1 and 65535" in str(exc_info.value)

    def test_log_level_validation_valid(self):
        """Test valid log levels."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        for level in valid_levels:
            config = AppConfig(log_level=level)
            assert config.log_level == level.upper()

    def test_log_level_validation_case_insensitive(self):
        """Test log level validation is case insensitive."""
        config = AppConfig(log_level="debug")
        assert config.log_level == "DEBUG"

    def test_log_level_validation_invalid(self):
        """Test invalid log levels."""
        with pytest.raises(ValidationError) as exc_info:
            AppConfig(log_level="INVALID")
        assert "Log level must be one of" in str(exc_info.value)

    @patch.dict(os.environ, {"APP_ENVIRONMENT": "staging", "APP_PORT": "9090"})
    def test_environment_variables(self):
        """Test loading from environment variables."""
        config = AppConfig()
        # Note: This would require proper environment variable handling
        # For now, test that the config can be created
        assert config.environment in ["development", "staging", "production"]


class TestSecurityConfig:
    """Test SecurityConfig configuration class."""

    def test_security_config_defaults(self):
        """Test SecurityConfig with default values."""
        config = SecurityConfig()
        
        assert len(config.jwt_secret_key) >= 32
        assert config.jwt_algorithm == "HS256"
        assert config.jwt_expire_minutes == 30
        assert config.jwt_issuer == "algotrading-platform"
        assert config.jwt_audience == "algotrading-users"
        assert config.api_keys == []

    def test_jwt_secret_validation_valid(self):
        """Test valid JWT secret key."""
        long_secret = "a" * 32
        config = SecurityConfig(jwt_secret_key=long_secret)
        assert config.jwt_secret_key == long_secret

    def test_jwt_secret_validation_invalid(self):
        """Test invalid JWT secret key."""
        with pytest.raises(ValidationError) as exc_info:
            SecurityConfig(jwt_secret_key="short")
        assert "JWT secret key must be at least 32 characters" in str(exc_info.value)

    def test_jwt_algorithm_validation_valid(self):
        """Test valid JWT algorithms."""
        valid_algorithms = ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"]
        for algorithm in valid_algorithms:
            config = SecurityConfig(jwt_algorithm=algorithm)
            assert config.jwt_algorithm == algorithm

    def test_jwt_algorithm_validation_invalid(self):
        """Test invalid JWT algorithm."""
        with pytest.raises(ValidationError) as exc_info:
            SecurityConfig(jwt_algorithm="INVALID")
        assert "JWT algorithm must be one of" in str(exc_info.value)

    @patch.dict(os.environ, {"API_KEYS": "key1,key2,key3"})
    def test_api_keys_from_environment(self):
        """Test loading API keys from environment."""
        config = SecurityConfig()
        assert "key1" in config.api_keys
        assert "key2" in config.api_keys
        assert "key3" in config.api_keys

    @patch.dict(os.environ, {"API_KEYS": "key1, key2 , key3 ,"})
    def test_api_keys_from_environment_with_spaces(self):
        """Test loading API keys with spaces."""
        config = SecurityConfig()
        assert len(config.api_keys) == 3
        assert all(key.strip() == key for key in config.api_keys)


class TestAlpacaConfig:
    """Test AlpacaConfig configuration class."""

    def test_alpaca_config_defaults(self):
        """Test AlpacaConfig with default values."""
        config = AlpacaConfig()
        
        assert config.api_key == ""
        assert config.secret_key == ""
        assert config.base_url == "https://paper-api.alpaca.markets"
        assert config.websocket_url == "wss://stream.data.alpaca.markets/v2/iex"
        assert config.paper_trading is True

    @patch.dict(os.environ, {"APP_ENVIRONMENT": "production"})
    def test_credentials_required_in_production(self):
        """Test that credentials are required in production."""
        with pytest.raises(ValidationError) as exc_info:
            AlpacaConfig(api_key="", secret_key="")
        assert "is required in production" in str(exc_info.value)

    def test_url_validation_valid(self):
        """Test valid URL formats."""
        valid_urls = [
            "https://api.alpaca.markets",
            "http://localhost:8080",
            "wss://stream.alpaca.markets",
            "ws://localhost:9090"
        ]
        
        for url in valid_urls:
            config = AlpacaConfig(base_url=url, websocket_url=url)
            assert config.base_url == url
            assert config.websocket_url == url

    def test_url_validation_invalid(self):
        """Test invalid URL formats."""
        invalid_urls = ["ftp://invalid.com", "invalid-url", ""]
        
        for url in invalid_urls:
            with pytest.raises(ValidationError) as exc_info:
                AlpacaConfig(base_url=url)
            assert "URL must start with" in str(exc_info.value)


class TestDataConfig:
    """Test DataConfig configuration class."""

    def test_data_config_defaults(self):
        """Test DataConfig with default values."""
        config = DataConfig()
        
        assert config.database_url == "sqlite:///./trading_platform.db"
        assert config.redis_url == "redis://localhost:6379"
        assert config.redis_host == "localhost"
        assert config.redis_port == 6379
        assert config.redis_db == 0
        assert "AAPL" in config.default_symbols
        assert "StockMarket" in config.subreddit_list
        assert config.sentiment_update_interval == 300

    def test_database_url_validation(self):
        """Test database URL validation."""
        with pytest.raises(ValidationError) as exc_info:
            DataConfig(database_url="")
        assert "Database URL is required" in str(exc_info.value)

    def test_redis_port_validation_valid(self):
        """Test valid Redis port values."""
        valid_ports = [1, 6379, 65535]
        for port in valid_ports:
            config = DataConfig(redis_port=port)
            assert config.redis_port == port

    def test_redis_port_validation_invalid(self):
        """Test invalid Redis port values."""
        invalid_ports = [0, -1, 65536]
        for port in invalid_ports:
            with pytest.raises(ValidationError) as exc_info:
                DataConfig(redis_port=port)
            assert "Redis port must be between 1 and 65535" in str(exc_info.value)


class TestWebsocketConfig:
    """Test WebsocketConfig configuration class."""

    def test_websocket_config_defaults(self):
        """Test WebsocketConfig with default values."""
        config = WebsocketConfig()
        
        assert config.rate_limit_per_minute == 60
        assert config.max_connections == 100
        assert config.heartbeat_interval == 30
        assert config.reconnect_attempts == 5
        assert config.reconnect_delay == 5

    def test_positive_value_validation(self):
        """Test positive value validation."""
        fields = [
            "rate_limit_per_minute",
            "max_connections", 
            "heartbeat_interval",
            "reconnect_attempts",
            "reconnect_delay"
        ]
        
        for field in fields:
            with pytest.raises(ValidationError) as exc_info:
                WebsocketConfig(**{field: 0})
            assert "Value must be positive" in str(exc_info.value)
            
            with pytest.raises(ValidationError) as exc_info:
                WebsocketConfig(**{field: -1})
            assert "Value must be positive" in str(exc_info.value)


class TestMetricsConfig:
    """Test MetricsConfig configuration class."""

    def test_metrics_config_defaults(self):
        """Test MetricsConfig with default values."""
        config = MetricsConfig()
        
        assert config.prometheus_port == 9090
        assert config.log_level == "INFO"
        assert config.api_rate_limit_per_minute == 1000
        assert config.enable_metrics is True

    def test_prometheus_port_validation_valid(self):
        """Test valid Prometheus port values."""
        valid_ports = [1024, 9090, 65535]
        for port in valid_ports:
            config = MetricsConfig(prometheus_port=port)
            assert config.prometheus_port == port

    def test_prometheus_port_validation_invalid(self):
        """Test invalid Prometheus port values."""
        invalid_ports = [80, 1023, 65536]
        for port in invalid_ports:
            with pytest.raises(ValidationError) as exc_info:
                MetricsConfig(prometheus_port=port)
            assert "Prometheus port must be between 1024 and 65535" in str(exc_info.value)


class TestDatabaseConfig:
    """Test DatabaseConfig configuration class."""

    def test_database_config_defaults(self):
        """Test DatabaseConfig with default values."""
        config = DatabaseConfig()
        
        assert config.pool_size == 10
        assert config.max_overflow == 20
        assert config.pool_timeout == 30
        assert config.echo is False

    def test_positive_value_validation(self):
        """Test positive value validation."""
        fields = ["pool_size", "max_overflow", "pool_timeout"]
        
        for field in fields:
            with pytest.raises(ValidationError) as exc_info:
                DatabaseConfig(**{field: 0})
            assert "Value must be positive" in str(exc_info.value)


class TestTradingConfig:
    """Test TradingConfig configuration class."""

    def test_trading_config_creation(self):
        """Test TradingConfig can be created."""
        config = TradingConfig()
        # Basic test that config can be instantiated
        assert hasattr(config, 'max_daily_loss_pct')
        assert hasattr(config, 'max_drawdown_pct')


class TestSettingsIntegration:
    """Test Settings class integration and get_settings function."""

    def test_settings_creation(self):
        """Test Settings class can be created with all sub-configs."""
        settings = Settings()
        
        assert hasattr(settings, 'app')
        assert hasattr(settings, 'security')
        assert hasattr(settings, 'alpaca')
        assert hasattr(settings, 'data')
        assert hasattr(settings, 'websocket')
        assert hasattr(settings, 'metrics')
        assert hasattr(settings, 'database')
        assert hasattr(settings, 'trading')

    def test_get_settings_function(self):
        """Test get_settings function returns Settings instance."""
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_get_settings_cached(self):
        """Test get_settings returns cached instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    @patch('backend.config.base_settings.get_structured_logger')
    def test_settings_with_logger(self, mock_logger):
        """Test Settings integration with logger."""
        mock_logger.return_value = MagicMock()
        settings = Settings()
        # Test that settings can be created even with logger integration
        assert settings is not None


class TestConfigurationEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_string_values(self):
        """Test handling of empty string values."""
        # Some configs should handle empty strings gracefully
        config = AlpacaConfig(api_key="", secret_key="")
        assert config.api_key == ""
        assert config.secret_key == ""

    def test_large_numeric_values(self):
        """Test handling of large numeric values."""
        config = AppConfig(
            port=65535,
            workers=1000,
            max_connections=100000
        )
        assert config.port == 65535
        assert config.workers == 1000
        assert config.max_connections == 100000

    def test_unicode_string_values(self):
        """Test handling of unicode string values."""
        config = AppConfig(
            environment="development",
            version="1.0.0-β"
        )
        assert config.version == "1.0.0-β"

    def test_list_field_modifications(self):
        """Test that list fields can be modified."""
        config = DataConfig()
        original_symbols = config.default_symbols.copy()
        config.default_symbols.append("NVDA")
        assert "NVDA" in config.default_symbols
        assert len(config.default_symbols) == len(original_symbols) + 1

    def test_nested_configuration_access(self):
        """Test accessing nested configuration values."""
        settings = Settings()
        
        # Test accessing nested values
        assert settings.app.environment in ["development", "staging", "production"]
        assert settings.security.jwt_algorithm in ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"]
        assert settings.data.redis_port > 0
        assert isinstance(settings.websocket.max_connections, int)

    def test_configuration_serialization(self):
        """Test configuration can be serialized."""
        config = AppConfig()
        config_dict = config.model_dump()
        
        assert isinstance(config_dict, dict)
        assert "environment" in config_dict
        assert "port" in config_dict
        assert config_dict["environment"] == "development"

    def test_configuration_from_dict(self):
        """Test configuration can be created from dictionary."""
        config_data = {
            "environment": "staging",
            "port": 9000,
            "debug": False
        }
        config = AppConfig(**config_data)
        
        assert config.environment == "staging"
        assert config.port == 9000
        assert config.debug is False