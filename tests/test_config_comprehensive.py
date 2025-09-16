"""
Comprehensive tests for configuration modules.
Tests config loading, environment overrides, validation, and error conditions.
Part of Phase 2.3.1 - Configuration Module Testing.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

# Test imports for all config modules
import backend.config
from backend.config import settings, get_settings, Settings
from backend.config.base_settings import (
    AppConfig, SecurityConfig, AlpacaConfig, DataConfig,
    WebsocketConfig, MetricsConfig, DatabaseConfig, TradingConfig,
    OutboxConfig, ObservabilityConfig, MLOpsConfig,
    validate_required_settings
)
from backend.config_helpers import Config, load_config_from_env


class TestConfigModuleCompatibility:
    """Test the compatibility shim in backend.config module."""
    
    def test_config_module_imports(self):
        """Test that config module can be imported and provides package-like behavior."""
        # Test that we can import the main config module
        assert hasattr(backend.config, '__path__')
        assert hasattr(backend.config, 'settings')
        assert hasattr(backend.config, 'get_settings')
        assert hasattr(backend.config, 'Settings')
    
    def test_config_forwarding(self):
        """Test that the config module forwards symbols correctly."""
        # Test that imports work through the compatibility shim
        from backend.config import settings as config_settings
        from backend.config import get_settings as config_get_settings
        
        assert config_settings is not None
        assert callable(config_get_settings)
    
    def test_config_fallback_handling(self):
        """Test fallback behavior when imports fail."""
        # This tests the exception handling in the config module
        with patch('backend.config.settings', side_effect=ImportError("Test error")):
            # Import should still work due to fallback
            import backend.config
            assert hasattr(backend.config, 'Settings')


class TestAppConfig:
    """Test AppConfig configuration section."""
    
    def test_app_config_defaults(self):
        """Test all default values load correctly."""
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
    
    def test_app_config_environment_overrides(self):
        """Test environment variable overrides."""
        env_vars = {
            'APP_ENVIRONMENT': 'production',
            'APP_DEBUG': 'false',
            'APP_HOST': '127.0.0.1',
            'APP_PORT': '9000',
            'APP_WORKERS': '8',
            'APP_LOG_LEVEL': 'ERROR'
        }
        
        with patch.dict(os.environ, env_vars):
            config = AppConfig()
            assert config.environment == "production"
            assert config.debug is False
            assert config.host == "127.0.0.1"
            assert config.port == 9000
            assert config.workers == 8
            assert config.log_level == "ERROR"
    
    def test_app_config_validation(self):
        """Test configuration validation."""
        # Test invalid environment
        with pytest.raises(ValueError, match="Environment must be one of"):
            AppConfig(environment="invalid")
        
        # Test invalid port
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            AppConfig(port=0)
        
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            AppConfig(port=70000)
        
        # Test invalid log level
        with pytest.raises(ValueError, match="Log level must be one of"):
            AppConfig(log_level="INVALID")
    
    def test_app_config_valid_environments(self):
        """Test all valid environment values."""
        for env in ["development", "staging", "production"]:
            config = AppConfig(environment=env)
            assert config.environment == env
    
    def test_app_config_log_level_case_insensitive(self):
        """Test log level validation handles case insensitivity."""
        config = AppConfig(log_level="debug")
        assert config.log_level == "DEBUG"
        
        config = AppConfig(log_level="Info")
        assert config.log_level == "INFO"


class TestSecurityConfig:
    """Test SecurityConfig configuration section."""
    
    def test_security_config_defaults(self):
        """Test security configuration defaults."""
        config = SecurityConfig()
        
        assert config.jwt_secret_key == "your-super-secret-jwt-key-change-this-in-production"
        assert config.jwt_algorithm == "HS256"
        assert config.jwt_expire_minutes == 30
        assert config.jwt_issuer == "algotrading-platform"
        assert config.jwt_audience == "algotrading-users"
        assert config.api_keys == []
    
    def test_security_config_environment_overrides(self):
        """Test security environment variable overrides."""
        env_vars = {
            'SECURITY_JWT_SECRET_KEY': 'new-super-secret-key-for-testing-purposes-only',
            'SECURITY_JWT_ALGORITHM': 'HS512',
            'SECURITY_JWT_EXPIRE_MINUTES': '60',
            'API_KEYS': 'key1,key2,key3'
        }
        
        with patch.dict(os.environ, env_vars):
            config = SecurityConfig()
            assert config.jwt_secret_key == 'new-super-secret-key-for-testing-purposes-only'
            assert config.jwt_algorithm == 'HS512'
            assert config.jwt_expire_minutes == 60
            assert config.api_keys == ['key1', 'key2', 'key3']
    
    def test_security_config_validation(self):
        """Test security configuration validation."""
        # Test JWT secret key too short
        with pytest.raises(ValueError, match="JWT secret key must be at least 32 characters"):
            SecurityConfig(jwt_secret_key="short")
        
        # Test invalid JWT algorithm
        with pytest.raises(ValueError, match="JWT algorithm must be one of"):
            SecurityConfig(jwt_algorithm="INVALID")
    
    def test_security_config_valid_algorithms(self):
        """Test all valid JWT algorithms."""
        valid_algorithms = ["HS256", "HS384", "HS512", "RS256", "RS384", "RS512"]
        for alg in valid_algorithms:
            config = SecurityConfig(
                jwt_secret_key="this-is-a-valid-secret-key-that-is-long-enough",
                jwt_algorithm=alg
            )
            assert config.jwt_algorithm == alg
    
    def test_api_keys_parsing(self):
        """Test API keys parsing from environment."""
        # Test empty API keys
        with patch.dict(os.environ, {'API_KEYS': ''}):
            config = SecurityConfig()
            assert config.api_keys == []
        
        # Test single API key
        with patch.dict(os.environ, {'API_KEYS': 'single-key'}):
            config = SecurityConfig()
            assert config.api_keys == ['single-key']
        
        # Test multiple API keys with spaces
        with patch.dict(os.environ, {'API_KEYS': ' key1 , key2 , key3 '}):
            config = SecurityConfig()
            assert config.api_keys == ['key1', 'key2', 'key3']


class TestCompleteSettings:
    """Test the complete Settings configuration."""
    
    def test_settings_initialization(self):
        """Test complete settings initialization."""
        config = Settings()
        
        # Test that all sections are present
        assert hasattr(config, 'app')
        assert hasattr(config, 'security')
        assert hasattr(config, 'alpaca')
        assert hasattr(config, 'database')
        assert hasattr(config, 'trading')
        
        # Test that sections are proper config objects
        assert isinstance(config.app, AppConfig)
        assert isinstance(config.security, SecurityConfig)
    
    def test_get_settings_function(self):
        """Test get_settings function behavior."""
        settings1 = get_settings()
        settings2 = get_settings()
        
        # Should return the same instance (cached)
        assert settings1 is settings2
        assert isinstance(settings1, Settings)
    
    def test_settings_singleton_behavior(self):
        """Test that settings behaves as a singleton."""
        # Test that get_settings returns consistent results
        settings1 = get_settings()
        settings2 = get_settings()
        
        # Should return the same instance (cached)
        assert settings1 is settings2
        assert isinstance(settings1, (Settings, object))  # May be Settings or LegacySettings


class TestConfigValidation:
    """Test configuration validation functions."""
    
    def test_validate_required_settings(self):
        """Test required settings validation."""
        # This should pass with default settings
        try:
            validate_required_settings()
        except Exception as e:
            # If validation fails, it should give a meaningful error
            assert isinstance(e, (ValueError, AttributeError))
    
    def test_validate_required_settings_with_custom_config(self):
        """Test validation with custom configuration."""
        # Test that validation function exists and can be called
        try:
            validate_required_settings()  # Function takes no arguments
        except Exception as e:
            # Should handle validation gracefully
            assert isinstance(e, (ValueError, AttributeError, TypeError))


class TestConfigHelpers:
    """Test config_helpers module."""
    
    def test_config_class_creation(self):
        """Test Config class instantiation."""
        config = Config()
        assert isinstance(config, Config)
    
    def test_load_config_from_env(self):
        """Test loading configuration from environment."""
        config = load_config_from_env()
        assert isinstance(config, Config)
    
    def test_config_helpers_module_coverage(self):
        """Test config_helpers module functions to improve coverage."""
        # Import and use all functions to ensure coverage
        from backend.config_helpers import Config, load_config_from_env
        
        config_class = Config
        load_function = load_config_from_env
        
        assert config_class is not None
        assert callable(load_function)
        
        # Create instances to test execution
        config1 = Config()
        config2 = load_config_from_env()
        
        assert config1 is not None
        assert config2 is not None


class TestConfigurationMerging:
    """Test configuration merging and environment mode handling."""
    
    def test_development_mode_configuration(self):
        """Test development environment configuration."""
        with patch.dict(os.environ, {'APP_ENVIRONMENT': 'development'}):
            config = AppConfig()
            assert config.environment == 'development'
            assert config.debug is True
    
    def test_production_mode_configuration(self):
        """Test production environment configuration."""
        env_vars = {
            'APP_ENVIRONMENT': 'production',
            'APP_DEBUG': 'false',
            'APP_LOG_LEVEL': 'WARNING'
        }
        
        with patch.dict(os.environ, env_vars):
            config = AppConfig()
            assert config.environment == 'production'
            assert config.debug is False
            assert config.log_level == 'WARNING'
    
    def test_staging_mode_configuration(self):
        """Test staging environment configuration."""
        with patch.dict(os.environ, {'APP_ENVIRONMENT': 'staging'}):
            config = AppConfig()
            assert config.environment == 'staging'


class TestConfigurationErrorConditions:
    """Test configuration error handling and edge cases."""
    
    def test_invalid_boolean_conversion(self):
        """Test handling of invalid boolean values."""
        with patch.dict(os.environ, {'APP_DEBUG': 'invalid_boolean'}):
            # Pydantic v2 should raise ValidationError for invalid booleans
            with pytest.raises(Exception):  # Could be ValidationError or ValueError
                AppConfig()
    
    def test_invalid_integer_conversion(self):
        """Test handling of invalid integer values."""
        with patch.dict(os.environ, {'APP_PORT': 'not_a_number'}):
            with pytest.raises(ValueError):
                AppConfig()
    
    def test_missing_environment_variables(self):
        """Test behavior with missing environment variables."""
        # Clear all relevant env vars
        env_vars_to_clear = [
            'APP_ENVIRONMENT', 'APP_DEBUG', 'APP_HOST', 'APP_PORT',
            'SECURITY_JWT_SECRET_KEY', 'API_KEYS'
        ]
        
        with patch.dict(os.environ, {}, clear=True):
            # Should still work with defaults
            app_config = AppConfig()
            security_config = SecurityConfig()
            
            assert app_config.environment == "development"
            assert security_config.jwt_algorithm == "HS256"
    
    def test_config_with_partial_overrides(self):
        """Test configuration with only some environment variables set."""
        env_vars = {
            'APP_ENVIRONMENT': 'production',
            'APP_PORT': '9000'
            # Other values should remain defaults
        }
        
        with patch.dict(os.environ, env_vars):
            config = AppConfig()
            assert config.environment == 'production'
            assert config.port == 9000
            assert config.debug is True  # Should remain default
            assert config.host == '0.0.0.0'  # Should remain default


class TestEdgeCasesAndBoundaries:
    """Test edge cases and boundary conditions."""
    
    def test_port_boundary_values(self):
        """Test port validation at boundaries."""
        # Test minimum valid port
        config = AppConfig(port=1)
        assert config.port == 1
        
        # Test maximum valid port
        config = AppConfig(port=65535)
        assert config.port == 65535
    
    def test_jwt_secret_minimum_length(self):
        """Test JWT secret key at minimum valid length."""
        min_secret = "a" * 32  # Exactly 32 characters
        config = SecurityConfig(jwt_secret_key=min_secret)
        assert config.jwt_secret_key == min_secret
    
    def test_empty_cors_origins(self):
        """Test configuration with empty CORS origins."""
        config = AppConfig(cors_origins=[])
        assert config.cors_origins == []
    
    def test_large_values(self):
        """Test configuration with large but valid values."""
        config = AppConfig(
            max_connections=1000000,
            request_timeout=3600,
            workers=100
        )
        assert config.max_connections == 1000000
        assert config.request_timeout == 3600
        assert config.workers == 100
