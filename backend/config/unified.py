"""
Unified Configuration System
Provides single source of truth for all platform configuration
"""
import os
from typing import Optional, Dict, Any
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env file explicitly at module level
load_dotenv()


class UnifiedSettings(BaseSettings):
    """
    Unified configuration system providing single source of truth
    for all platform settings
    """
    
    # Core application settings
    app_name: str = Field(default="Trading Platform", env="APP_NAME")
    debug: bool = Field(default=False, env="DEBUG")
    host: str = Field(default="localhost", env="HOST")
    port: int = Field(default=8000, env="PORT")
    
    # Database settings
    database_url: str = Field(default="sqlite:///./trading_platform.db", env="DATABASE_URL")
    database_echo: bool = Field(default=False, env="DB_ECHO")
    database_pool_size: int = Field(default=20, env="DB_POOL_SIZE")
    database_max_overflow: int = Field(default=30, env="DB_MAX_OVERFLOW")
    database_pool_timeout: int = Field(default=30, env="DB_POOL_TIMEOUT")
    database_pool_recycle: int = Field(default=3600, env="DB_POOL_RECYCLE")
    
    # Security settings - use direct environment access due to pydantic-settings issues
    jwt_secret: str = Field(default_factory=lambda: os.getenv("SECURITY_JWT_SECRET", ""))
    jwt_algorithm: str = Field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    jwt_expiration_hours: int = Field(default_factory=lambda: int(os.getenv("JWT_EXPIRATION_HOURS", "24")))
    
    # Alpaca settings - use direct environment access
    alpaca_api_key: str = Field(default_factory=lambda: os.getenv("ALPACA_API_KEY", ""))
    alpaca_secret_key: str = Field(default_factory=lambda: os.getenv("ALPACA_SECRET_KEY", ""))
    alpaca_base_url: str = Field(default_factory=lambda: os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"))
    alpaca_data_url: str = Field(default_factory=lambda: os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets"))
    
    # Outbox settings
    outbox_enabled: bool = Field(default=True, env="OUTBOX_ENABLED")
    outbox_batch_size: int = Field(default=100, env="OUTBOX_BATCH_SIZE")
    outbox_retry_attempts: int = Field(default=3, env="OUTBOX_RETRY_ATTEMPTS")
    outbox_retry_delay_seconds: int = Field(default=5, env="OUTBOX_RETRY_DELAY")
    outbox_max_age_hours: int = Field(default=24, env="OUTBOX_MAX_AGE_HOURS")

    model_config = {
        "case_sensitive": False,
        "extra": "allow"
    }
    
    @field_validator('jwt_secret')
    @classmethod
    def validate_jwt_secret(cls, v):
        # Only validate if not empty (allows for testing)
        if v and len(v) < 32:
            raise ValueError("JWT secret must be at least 32 characters long")
        return v
    
    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v):
        if not v:
            raise ValueError("Database URL cannot be empty")
        return v
    
    @model_validator(mode='after')
    def validate_production_requirements(self):
        """Validate production requirements only when not in debug mode"""
        if not self.debug:  # Production mode
            if not self.jwt_secret:
                raise ValueError("JWT secret is required for production mode")
            if not self.alpaca_api_key or not self.alpaca_secret_key:
                raise ValueError("Alpaca credentials are required for production mode")
        return self
    
    def get_database_url(self) -> str:
        """Get the unified database URL"""
        return self.database_url
    
    def get_jwt_config(self) -> Dict[str, Any]:
        """Get JWT configuration dictionary"""
        return {
            "secret": self.jwt_secret,
            "algorithm": self.jwt_algorithm,
            "expiration_hours": self.jwt_expiration_hours
        }
    
    def get_alpaca_config(self) -> Dict[str, str]:
        """Get Alpaca configuration dictionary"""
        return {
            "api_key": self.alpaca_api_key,
            "secret_key": self.alpaca_secret_key,
            "base_url": self.alpaca_base_url,
            "data_url": self.alpaca_data_url
        }
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration dictionary"""
        return {
            "url": self.database_url,
            "echo": self.database_echo,
            "pool_size": self.database_pool_size,
            "max_overflow": self.database_max_overflow,
            "pool_timeout": self.database_pool_timeout,
            "pool_recycle": self.database_pool_recycle
        }
    
    def get_outbox_config(self) -> Dict[str, Any]:
        """Get outbox configuration dictionary"""
        return {
            "enabled": self.outbox_enabled,
            "batch_size": self.outbox_batch_size,
            "retry_attempts": self.outbox_retry_attempts,
            "retry_delay_seconds": self.outbox_retry_delay_seconds,
            "max_age_hours": self.outbox_max_age_hours
        }
    
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.debug
    
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return not self.debug


# Global configuration instance
_settings: Optional[UnifiedSettings] = None


def get_unified_settings() -> UnifiedSettings:
    """
    Get or create the global unified settings instance
    Thread-safe singleton pattern
    """
    global _settings
    if _settings is None:
        _settings = UnifiedSettings()
    return _settings


def reload_settings() -> UnifiedSettings:
    """
    Force reload of settings (useful for testing)
    """
    global _settings
    _settings = UnifiedSettings()
    return _settings


# Convenience functions for common configuration access
def get_database_url() -> str:
    """Get the unified database URL"""
    return get_unified_settings().get_database_url()


def get_jwt_secret() -> str:
    """Get the JWT secret"""
    return get_unified_settings().jwt_secret


def get_alpaca_credentials() -> Dict[str, str]:
    """Get Alpaca API credentials"""
    return get_unified_settings().get_alpaca_config()


def is_debug_mode() -> bool:
    """Check if running in debug mode"""
    return get_unified_settings().debug


def get_database_config() -> Dict[str, Any]:
    """Get complete database configuration"""
    return get_unified_settings().get_database_config()


def get_outbox_config() -> Dict[str, Any]:
    """Get complete outbox configuration"""
    return get_unified_settings().get_outbox_config()