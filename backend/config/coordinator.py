"""
Configuration Coordinator - Single Point of Configuration Access

.. deprecated::
    Use ``backend.config.settings.get_settings()`` directly.
    This module will be removed in a future release.
"""

import warnings
from functools import lru_cache
import os
from typing import Any

warnings.warn(
    "backend.config.coordinator is deprecated. Use backend.config.settings.get_settings() instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Import all configuration systems
try:
    from backend.config.unified import UnifiedSettings, get_unified_settings
    UNIFIED_AVAILABLE = True
except ImportError:
    UNIFIED_AVAILABLE = False
    UnifiedSettings = None

try:
    from backend.config.settings import AppSettings
    from backend.config.settings import get_settings as get_legacy_settings
    LEGACY_AVAILABLE = True
except ImportError:
    LEGACY_AVAILABLE = False
    AppSettings = None

try:
    from backend.config.base_settings import Settings as BaseSettings
    from backend.config.base_settings import get_settings as get_base_settings
    BASE_AVAILABLE = True
except ImportError:
    BASE_AVAILABLE = False
    BaseSettings = None


class ConfigurationCoordinator:
    """
    Unified configuration coordinator that consolidates all configuration systems
    """

    def __init__(self):
        self._primary_config = None
        self._fallback_configs = []
        self._initialize_configs()

    def _initialize_configs(self):
        """Initialize configuration systems in order of preference"""

        # Primary: Use unified.py if available (most robust)
        if UNIFIED_AVAILABLE:
            try:
                self._primary_config = get_unified_settings()
                print("✅ Configuration Coordinator: Using unified.py as primary")
                return
            except Exception as e:
                print(f"⚠️  Configuration Coordinator: Unified config failed: {e}")

        # Fallback 1: Legacy settings.py
        if LEGACY_AVAILABLE:
            try:
                config = get_legacy_settings()
                self._fallback_configs.append(('legacy', config))
                if not self._primary_config:
                    self._primary_config = config
                    print("✅ Configuration Coordinator: Using legacy settings.py as primary")
            except Exception as e:
                print(f"⚠️  Configuration Coordinator: Legacy config failed: {e}")

        # Fallback 2: Base settings.py
        if BASE_AVAILABLE:
            try:
                config = get_base_settings()
                self._fallback_configs.append(('base', config))
                if not self._primary_config:
                    self._primary_config = config
                    print("✅ Configuration Coordinator: Using base_settings.py as primary")
            except Exception as e:
                print(f"⚠️  Configuration Coordinator: Base config failed: {e}")

        if not self._primary_config:
            print("❌ Configuration Coordinator: No configuration system available!")

    def get_database_url(self) -> str:
        """Get database URL from any available config system"""

        # Try unified system first
        if UNIFIED_AVAILABLE and hasattr(self._primary_config, 'database_url'):
            return self._primary_config.database_url

        # Try legacy attribute access patterns
        for attr_name in ['database_url', 'DATABASE_URL']:
            if hasattr(self._primary_config, attr_name):
                value = getattr(self._primary_config, attr_name)
                if value:
                    return value

        # Try nested access patterns
        if hasattr(self._primary_config, 'database'):
            db_config = self._primary_config.database
            if hasattr(db_config, 'url'):
                return db_config.url
            if hasattr(db_config, 'database_url'):
                return db_config.database_url

        # Environment variable fallback (no hardcoded credentials)
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            raise ValueError("DATABASE_URL environment variable is required")
        return db_url

    def get_jwt_secret(self) -> str:
        """Get JWT secret from any available config system"""

        # Try unified system first
        if UNIFIED_AVAILABLE and hasattr(self._primary_config, 'jwt_secret_key'):
            secret = self._primary_config.jwt_secret_key
            if secret and secret != 'default-change-me':
                return secret

        # Try legacy patterns
        for attr_name in ['jwt_secret_key', 'JWT_SECRET_KEY', 'api_secret_key']:
            if hasattr(self._primary_config, attr_name):
                value = getattr(self._primary_config, attr_name)
                if value and value != 'default-change-me':
                    return value

        # Try nested access
        if hasattr(self._primary_config, 'security'):
            security_config = self._primary_config.security
            if hasattr(security_config, 'jwt_secret_key'):
                value = security_config.jwt_secret_key
                if value and value != 'default-change-me':
                    return value

        # Environment variable fallback
        return os.getenv('JWT_SECRET_KEY', os.getenv('API_SECRET_KEY', ''))

    def get_alpaca_credentials(self) -> dict[str, str]:
        """Get Alpaca credentials from any available config system"""
        credentials = {
            'api_key': '',
            'secret_key': '',
            'base_url': 'https://paper-api.alpaca.markets',
            'paper': True
        }

        # Try unified system first
        if UNIFIED_AVAILABLE and hasattr(self._primary_config, 'alpaca_api_key'):
            credentials['api_key'] = self._primary_config.alpaca_api_key or ''
            credentials['secret_key'] = self._primary_config.alpaca_secret_key or ''
            credentials['base_url'] = getattr(self._primary_config, 'alpaca_base_url', credentials['base_url'])
            credentials['paper'] = getattr(self._primary_config, 'alpaca_paper', True)
            return credentials

        # Try nested access
        if hasattr(self._primary_config, 'alpaca'):
            alpaca_config = self._primary_config.alpaca
            credentials['api_key'] = getattr(alpaca_config, 'api_key', '')
            credentials['secret_key'] = getattr(alpaca_config, 'secret_key', '')
            credentials['base_url'] = getattr(alpaca_config, 'base_url', credentials['base_url'])
            credentials['paper'] = getattr(alpaca_config, 'paper', True)
            return credentials

        # Environment variable fallback
        credentials['api_key'] = os.getenv('ALPACA_API_KEY_ID', '')
        credentials['secret_key'] = os.getenv('ALPACA_API_SECRET_KEY', '')
        credentials['base_url'] = os.getenv('ALPACA_BASE_URL', credentials['base_url'])
        credentials['paper'] = os.getenv('ALPACA_PAPER', 'true').lower() == 'true'

        return credentials

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Generic setting getter with intelligent fallback"""

        # Try direct attribute access
        if hasattr(self._primary_config, key):
            value = getattr(self._primary_config, key)
            if value is not None:
                return value

        # Try uppercase version
        upper_key = key.upper()
        if hasattr(self._primary_config, upper_key):
            value = getattr(self._primary_config, upper_key)
            if value is not None:
                return value

        # Try environment variable
        env_value = os.getenv(key) or os.getenv(upper_key)
        if env_value is not None:
            return env_value

        return default

    def get_configuration_status(self) -> dict[str, Any]:
        """Get status of all configuration systems"""
        return {
            'unified_available': UNIFIED_AVAILABLE,
            'legacy_available': LEGACY_AVAILABLE,
            'base_available': BASE_AVAILABLE,
            'primary_config_type': type(self._primary_config).__name__ if self._primary_config else 'None',
            'fallback_configs': [(name, type(config).__name__) for name, config in self._fallback_configs],
            'database_url': self.get_database_url(),
            'jwt_configured': bool(self.get_jwt_secret()),
            'alpaca_configured': bool(self.get_alpaca_credentials()['api_key'])
        }


# Global coordinator instance
@lru_cache(maxsize=1)
def get_configuration_coordinator() -> ConfigurationCoordinator:
    """Get the global configuration coordinator instance"""
    return ConfigurationCoordinator()


# Convenience functions for backward compatibility
def get_database_url() -> str:
    """Get database URL from unified configuration"""
    return get_configuration_coordinator().get_database_url()


def get_jwt_secret() -> str:
    """Get JWT secret from unified configuration"""
    return get_configuration_coordinator().get_jwt_secret()


def get_alpaca_credentials() -> dict[str, str]:
    """Get Alpaca credentials from unified configuration"""
    return get_configuration_coordinator().get_alpaca_credentials()


def get_setting(key: str, default: Any = None) -> Any:
    """Get any setting from unified configuration"""
    return get_configuration_coordinator().get_setting(key, default)


def get_configuration_status() -> dict[str, Any]:
    """Get configuration system status"""
    return get_configuration_coordinator().get_configuration_status()


if __name__ == "__main__":
    # Test the coordinator
    coordinator = get_configuration_coordinator()
    status = coordinator.get_configuration_status()

    print("🔧 Configuration Coordinator Status:")
    for key, value in status.items():
        print(f"   {key}: {value}")

    print(f"\n📊 Database URL: {coordinator.get_database_url()}")
    print(f"🔐 JWT Secret: {'configured' if coordinator.get_jwt_secret() else 'not configured'}")
    alpaca_creds = coordinator.get_alpaca_credentials()
    print(f"📈 Alpaca API: {'configured' if alpaca_creds['api_key'] else 'not configured'}")
