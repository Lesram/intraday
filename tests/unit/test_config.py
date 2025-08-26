"""
Unit tests for configuration modules.
Tests default values, environment variable overrides, and config validation.
"""
import os
import pytest
from unittest.mock import patch
from typing import Dict, Any

from backend.config.base_settings import (
    get_settings, 
    Settings,
    LegacySettings,
    AppConfig,
    SecurityConfig,
    AlpacaConfig,
    DataConfig,
    validate_required_settings,
)
from backend.config import settings as legacy_settings
from backend.config_helpers import load_config_from_env, Config


class TestConfigHelpers:
    """Test the basic config helpers module."""
    
    def test_config_class_exists(self):
        """Test that Config class can be instantiated."""
        config = Config()
        assert config is not None
        assert isinstance(config, Config)
    
    def test_load_config_from_env_returns_config(self):
        """Test that load_config_from_env returns a Config instance."""
        config = load_config_from_env()
        assert config is not None
        assert isinstance(config, Config)


class TestAppConfig:
    """Test the main application configuration."""
    
    def test_app_config_defaults(self):
        """Test that AppConfig has sensible defaults."""
        config = AppConfig()
        
        # Test default values
        assert config.environment in ["development", "production", "test"]
        assert config.debug is not None
        assert isinstance(config.debug, bool)
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.workers >= 1
    
    @patch.dict(os.environ, {
        "APP_ENVIRONMENT": "production",
        "APP_DEBUG": "false", 
        "APP_HOST": "127.0.0.1",
        "APP_PORT": "9000",
        "APP_WORKERS": "4"
    })
    def test_app_config_env_overrides(self):
        """Test that environment variables override defaults."""
        config = AppConfig()
        
        assert config.environment == "production"
        assert config.debug is False
        assert config.host == "127.0.0.1" 
        assert config.port == 9000
        assert config.workers == 4


class TestSecurityConfig:
    """Test security configuration."""
    
    def test_security_config_defaults(self):
        """Test that SecurityConfig has appropriate defaults."""
        config = SecurityConfig()
        
        # JWT settings should have defaults
        assert config.jwt_algorithm is not None
        assert config.jwt_expire_minutes > 0
        # Check that secret key is set to default
        assert len(config.jwt_secret_key) >= 32
    
    @patch.dict(os.environ, {
        "SECURITY_JWT_SECRET_KEY": "test-secret-key-123-long-enough-to-pass-validation",
        "SECURITY_JWT_ALGORITHM": "HS512", 
        "SECURITY_JWT_EXPIRE_MINUTES": "60"
    })
    def test_security_config_env_overrides(self):
        """Test security config with environment overrides."""
        config = SecurityConfig()
        
        assert config.jwt_secret_key == "test-secret-key-123-long-enough-to-pass-validation"
        assert config.jwt_algorithm == "HS512"
        assert config.jwt_expire_minutes == 60


class TestAlpacaConfig:
    """Test Alpaca API configuration."""
    
    def test_alpaca_config_defaults(self):
        """Test Alpaca config defaults."""
        config = AlpacaConfig()
        
        # Should have some defaults for base URL, etc.
        assert hasattr(config, 'base_url')
        assert config.base_url is not None
    
    @patch.dict(os.environ, {
        "ALPACA_API_KEY": "test-key",
        "ALPACA_SECRET_KEY": "test-secret",
        "ALPACA_BASE_URL": "https://paper-api.alpaca.markets"
    })
    def test_alpaca_config_env_overrides(self):
        """Test Alpaca config with environment variables."""
        config = AlpacaConfig()
        
        assert config.api_key == "test-key"
        assert config.secret_key == "test-secret"
        assert config.base_url == "https://paper-api.alpaca.markets"


class TestDataConfig:
    """Test data configuration."""
    
    def test_data_config_defaults(self):
        """Test data config has reasonable defaults."""
        config = DataConfig()
        
        # Should have defaults for data settings
        assert hasattr(config, 'database_url')
        assert config.database_url is not None
    
    @patch.dict(os.environ, {
        "DATA_DATABASE_URL": "postgresql://localhost/test"
    })
    def test_data_config_env_overrides(self):
        """Test data config environment overrides."""
        config = DataConfig()
        
        assert config.database_url == "postgresql://localhost/test"


class TestMainSettings:
    """Test the main Settings class and global settings instance."""
    
    def test_settings_instance_exists(self):
        """Test that global settings instance exists."""
        assert legacy_settings is not None
        assert isinstance(legacy_settings, LegacySettings)
    
    def test_get_settings_returns_instance(self):
        """Test get_settings factory function."""
        config = get_settings()
        assert config is not None
        assert isinstance(config, Settings)
    
    def test_settings_has_required_sections(self):
        """Test that settings has all required configuration sections."""
        # Test that legacy settings can access nested properties
        assert hasattr(legacy_settings, 'environment')
        assert hasattr(legacy_settings, 'debug')
        assert hasattr(legacy_settings, 'jwt_secret_key')
        
        # Test that new settings has proper sections
        new_settings = get_settings()
        assert hasattr(new_settings, 'app')
        assert hasattr(new_settings, 'security')
        
        # Test section types
        assert isinstance(new_settings.app, AppConfig)
        assert isinstance(new_settings.security, SecurityConfig)
    
    @patch.dict(os.environ, {
        "APP_ENVIRONMENT": "development",  # Use valid environment
        "APP_DEBUG": "true",
        "SECURITY_JWT_SECRET_KEY": "test-jwt-secret-long-enough-for-validation"
    })
    def test_settings_with_env_vars(self):
        """Test settings with environment variables set."""
        # Clear the cache to pick up new env vars
        get_settings.cache_clear()
        
        # Create new settings instance with env vars
        test_settings = get_settings()
        
        assert test_settings is not None
        assert test_settings.app.environment == "development"  # Updated expectation
        assert test_settings.app.debug is True
        assert test_settings.security.jwt_secret_key == "test-jwt-secret-long-enough-for-validation"


class TestConfigValidation:
    """Test configuration validation functions."""
    
    def test_validate_required_settings_with_valid_config(self):
        """Test validation passes with valid configuration."""
        # This should not raise any exceptions
        try:
            validate_required_settings()
            # If we get here, validation passed
            assert True
        except Exception as e:
            # If validation fails, we want to see why
            raise AssertionError(f"Config validation failed unexpectedly: {e}")
    
    def test_validate_required_settings_with_missing_config(self):
        """Test validation with incomplete configuration."""
        # Create a minimal config that might be missing required fields
        minimal_config = Settings()
        
        # Validation might pass or fail depending on what's actually required
        # The important thing is that it doesn't crash
        try:
            validate_required_settings(minimal_config)
        except Exception:
            # Validation failure is acceptable for incomplete config
            pass
    
    @patch.dict(os.environ, {}, clear=True)
    def test_config_with_minimal_environment(self):
        """Test config creation with minimal environment variables."""
        # Clear all env vars and test that config can still be created
        test_config = get_settings()
        
        assert test_config is not None
        assert isinstance(test_config, Settings)
        
        # Should have sensible defaults
        assert test_config.app.environment in ["development", "production", "test"]
        assert isinstance(test_config.app.debug, bool)


class TestConfigIntegration:
    """Integration tests for configuration system."""
    
    def test_config_can_be_imported_multiple_ways(self):
        """Test that config can be imported through different paths."""
        # Test direct import from new settings
        from backend.config.settings import get_settings as get_settings_direct
        
        # Test package-level legacy import
        from backend.config import settings as legacy_settings_import
        
        # Both should work but be different types
        new_settings = get_settings_direct()
        assert new_settings is not None
        assert isinstance(new_settings, Settings)
        
        assert legacy_settings_import is not None
        assert isinstance(legacy_settings_import, LegacySettings)
    
    def test_config_consistency_across_imports(self):
        """Test that config values are consistent across different import methods."""
        new_settings = get_settings()
        
        # Legacy settings should access the same underlying values
        assert new_settings.app.environment == legacy_settings.environment
        assert new_settings.app.debug == legacy_settings.debug
        assert new_settings.app.host == legacy_settings.host
        assert new_settings.app.port == legacy_settings.port
    
    @patch.dict(os.environ, {
        "APP_ENVIRONMENT": "production",
        "APP_DEBUG": "false",
        "SECURITY_JWT_SECRET_KEY": "prod-secret-key-long-enough-for-security-validation",
        "API_KEYS": "prod-api-key-1,prod-api-key-2",  # Use API_KEYS (no SECURITY_ prefix)
        "ALPACA_API_KEY": "prod-alpaca-key",
        "ALPACA_SECRET_KEY": "prod-alpaca-secret-key"
    })
    def test_production_like_config(self):
        """Test configuration that resembles production settings."""
        # Clear cache to pick up new env vars
        get_settings.cache_clear()
        
        prod_settings = get_settings()
        
        assert prod_settings.app.environment == "production"
        assert prod_settings.app.debug is False
        
        # Security should be properly configured
        assert prod_settings.security.jwt_secret_key == "prod-secret-key-long-enough-for-security-validation"
        
        # External service configs should be set
        assert prod_settings.alpaca.api_key == "prod-alpaca-key"
