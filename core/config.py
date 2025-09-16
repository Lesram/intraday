"""
Core configuration module stub for infrastructure compatibility.
Provides configuration management that tests expect to find.
"""

from typing import Dict, Any, Optional
import os

class Config:
    """Configuration class stub."""
    
    def __init__(self):
        self.data = {}
        self._load_defaults()
        
    def _load_defaults(self) -> None:
        """Load default configuration values."""
        self.data = {
            # Database configuration
            "database": {
                "url": "sqlite:///test.db",
                "pool_size": 10,
                "max_overflow": 20,
                "echo": False
            },
            
            # API configuration  
            "api": {
                "host": "0.0.0.0",
                "port": 8000,
                "debug": False,
                "cors_origins": ["*"]
            },
            
            # Trading configuration
            "trading": {
                "paper_trading": True,
                "max_position_size": 10000.0,
                "risk_tolerance": 0.02,
                "default_stop_loss": 0.05
            },
            
            # ML configuration
            "ml": {
                "model_path": "./models",
                "retrain_interval": 3600,
                "feature_window": 100,
                "prediction_horizon": 5
            },
            
            # Logging configuration
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "file": "trading.log",
                "max_size": "10MB",
                "backup_count": 5
            },
            
            # Security configuration
            "security": {
                "secret_key": "test-secret-key-for-development",
                "jwt_expiration": 3600,
                "rate_limit": 100,
                "cors_enabled": True
            }
        }
        
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        keys = key.split('.')
        value = self.data
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
                
        return value
        
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        keys = key.split('.')
        config = self.data
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
            
        config[keys[-1]] = value
        
    def update(self, updates: Dict[str, Any]) -> None:
        """Update configuration with dict."""
        self.data.update(updates)
        
    def get_database_url(self) -> str:
        """Get database URL."""
        return self.get("database.url", "sqlite:///test.db")
        
    def get_api_config(self) -> Dict[str, Any]:
        """Get API configuration."""
        return self.get("api", {})
        
    def get_trading_config(self) -> Dict[str, Any]:
        """Get trading configuration."""
        return self.get("trading", {})
        
    def get_ml_config(self) -> Dict[str, Any]:
        """Get ML configuration."""
        return self.get("ml", {})
        
    def is_paper_trading(self) -> bool:
        """Check if paper trading is enabled."""
        return self.get("trading.paper_trading", True)
        
    def get_log_level(self) -> str:
        """Get logging level."""
        return self.get("logging.level", "INFO")

# Module-level functions and variables for direct imports
def load_config(config_file: Optional[str] = None) -> Config:
    """Load configuration from file."""
    return Config()

def get_config() -> Config:
    """Get global configuration instance."""
    return _global_config

def get_database_url() -> str:
    """Get database URL."""
    return _global_config.get_database_url()

def get_setting(key: str, default: Any = None) -> Any:
    """Get configuration setting."""
    return _global_config.get(key, default)

def set_setting(key: str, value: Any) -> None:
    """Set configuration setting."""
    _global_config.set(key, value)

def is_development() -> bool:
    """Check if running in development mode."""
    return get_setting("api.debug", False)

def is_production() -> bool:
    """Check if running in production mode."""
    return not is_development()

# Environment variable helpers
def get_env(key: str, default: str = "") -> str:
    """Get environment variable."""
    return os.getenv(key, default)

def get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    value = os.getenv(key, str(default)).lower()
    return value in ('true', '1', 'yes', 'on')

def get_env_int(key: str, default: int = 0) -> int:
    """Get integer environment variable."""
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

# Create global instance
_global_config = Config()

# Compatibility aliases
config = _global_config
settings = _global_config
CONFIG = _global_config
