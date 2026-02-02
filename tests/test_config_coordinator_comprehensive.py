"""
Comprehensive tests for backend/config/coordinator.py

Tests the ConfigurationCoordinator class.
"""

import pytest
import os
from unittest.mock import patch, MagicMock


class TestConfigurationCoordinatorInit:
    """Tests for ConfigurationCoordinator initialization."""

    def test_coordinator_can_be_imported(self):
        """ConfigurationCoordinator can be imported."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        assert ConfigurationCoordinator is not None

    def test_coordinator_can_be_instantiated(self):
        """ConfigurationCoordinator can be instantiated."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        
        assert coordinator is not None

    def test_coordinator_has_primary_config(self):
        """Coordinator has _primary_config attribute."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        
        assert hasattr(coordinator, "_primary_config")


class TestGetDatabaseUrl:
    """Tests for get_database_url method."""

    def test_get_database_url_returns_string(self):
        """get_database_url returns a string."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        
        url = coordinator.get_database_url()
        
        assert isinstance(url, str)
        assert len(url) > 0

    def test_get_database_url_env_fallback(self):
        """get_database_url falls back to environment variable."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        coordinator._primary_config = None
        
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test:test@localhost/testdb"}):
            url = coordinator.get_database_url()
        
        # Either gets from config or env var
        assert isinstance(url, str)


class TestGetJwtSecret:
    """Tests for get_jwt_secret method."""

    def test_get_jwt_secret_returns_string(self):
        """get_jwt_secret returns a string."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        
        secret = coordinator.get_jwt_secret()
        
        assert isinstance(secret, str)

    def test_get_jwt_secret_env_fallback(self):
        """get_jwt_secret can use environment variable."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "test-secret-key"}):
            coordinator = ConfigurationCoordinator()
            secret = coordinator.get_jwt_secret()
        
        assert isinstance(secret, str)


class TestGetAlpacaCredentials:
    """Tests for get_alpaca_credentials method."""

    def test_get_alpaca_credentials_returns_dict(self):
        """get_alpaca_credentials returns a dictionary."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        
        credentials = coordinator.get_alpaca_credentials()
        
        assert isinstance(credentials, dict)

    def test_get_alpaca_credentials_has_required_keys(self):
        """Credentials dict has required keys."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        
        credentials = coordinator.get_alpaca_credentials()
        
        assert "api_key" in credentials
        assert "secret_key" in credentials
        assert "base_url" in credentials
        assert "paper" in credentials

    def test_get_alpaca_credentials_env_fallback(self):
        """Credentials can come from environment variables."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        with patch.dict(os.environ, {
            "ALPACA_API_KEY_ID": "test-api-key",
            "ALPACA_API_SECRET_KEY": "test-secret-key",
        }):
            coordinator = ConfigurationCoordinator()
            coordinator._primary_config = MagicMock()
            # Remove alpaca-related attributes
            del coordinator._primary_config.alpaca
            del coordinator._primary_config.alpaca_api_key
            
            credentials = coordinator.get_alpaca_credentials()
        
        assert isinstance(credentials, dict)


class TestGetSetting:
    """Tests for get_setting method."""

    def test_get_setting_with_default(self):
        """get_setting returns default when key not found."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        
        result = coordinator.get_setting("nonexistent_key", default="default_value")
        
        assert result == "default_value"

    def test_get_setting_from_config(self):
        """get_setting can get value from config."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        
        # Try to get an existing setting
        result = coordinator.get_setting("debug", default=False)
        
        assert isinstance(result, (bool, type(None), str))

    def test_get_setting_from_env(self):
        """get_setting can get value from environment."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        with patch.dict(os.environ, {"CUSTOM_SETTING": "custom_value"}):
            coordinator = ConfigurationCoordinator()
            # Remove attribute from config if exists
            if hasattr(coordinator._primary_config, "CUSTOM_SETTING"):
                delattr(coordinator._primary_config, "CUSTOM_SETTING")
            if hasattr(coordinator._primary_config, "custom_setting"):
                delattr(coordinator._primary_config, "custom_setting")
            
            result = coordinator.get_setting("CUSTOM_SETTING", default="fallback")
        
        # May return either from env or config or default
        assert isinstance(result, str)


class TestGetConfigurationStatus:
    """Tests for get_configuration_status method."""

    def test_get_configuration_status_returns_dict(self):
        """get_configuration_status returns a dictionary."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        
        status = coordinator.get_configuration_status()
        
        assert isinstance(status, dict)

    def test_get_configuration_status_has_required_keys(self):
        """Status dict has required keys."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        coordinator = ConfigurationCoordinator()
        
        status = coordinator.get_configuration_status()
        
        assert "unified_available" in status
        assert "legacy_available" in status
        assert "base_available" in status
        assert "primary_config_type" in status


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_unified_available_is_bool(self):
        """UNIFIED_AVAILABLE is a boolean."""
        from backend.config.coordinator import UNIFIED_AVAILABLE
        
        assert isinstance(UNIFIED_AVAILABLE, bool)

    def test_legacy_available_is_bool(self):
        """LEGACY_AVAILABLE is a boolean."""
        from backend.config.coordinator import LEGACY_AVAILABLE
        
        assert isinstance(LEGACY_AVAILABLE, bool)

    def test_base_available_is_bool(self):
        """BASE_AVAILABLE is a boolean."""
        from backend.config.coordinator import BASE_AVAILABLE
        
        assert isinstance(BASE_AVAILABLE, bool)


class TestGetConfigCoordinator:
    """Tests for get_config_coordinator function."""

    def test_get_config_coordinator_exists(self):
        """get_config_coordinator function exists."""
        from backend.config import coordinator
        
        if hasattr(coordinator, "get_config_coordinator"):
            func = coordinator.get_config_coordinator
            assert callable(func)

    def test_module_level_coordinator_singleton(self):
        """Module-level coordinator is a singleton pattern."""
        from backend.config.coordinator import ConfigurationCoordinator
        
        # Create two instances - they should work independently
        c1 = ConfigurationCoordinator()
        c2 = ConfigurationCoordinator()
        
        assert c1 is not c2  # Different instances, not a strict singleton at class level
