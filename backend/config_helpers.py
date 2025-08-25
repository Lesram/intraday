"""
Configuration helpers for the trading platform.
Provides minimal configuration loading from environment variables.
"""

import os
from typing import Any, Dict


class Config:
    """Configuration class for tests and application."""
    
    def __init__(self, **kwargs: Any):
        """Initialize config with keyword arguments."""
        # Set defaults first
        self.environment = kwargs.get('environment', 'development')
        self.log_level = kwargs.get('log_level', 'INFO')
        self.trading_mode = kwargs.get('trading_mode', 'DRY_RUN')
        
        # Then update with all provided kwargs
        self.__dict__.update(kwargs)
        
        # Always validate - if users want to create a minimal config for testing,
        # they should provide the required fields
        self._validate_required_fields()
        self._validate_values()
    
    def _validate_required_fields(self):
        """Validate that required fields are present."""
        required_fields = ['database_url', 'alpaca_api_key', 'alpaca_secret', 'jwt_secret_key']
        
        # Check if we're in a test scenario that expects validation
        missing_fields = []
        for field in required_fields:
            if not hasattr(self, field) or not getattr(self, field):
                missing_fields.append(field)
        
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
    
    def _validate_values(self):
        """Validate configuration values."""
        # Validate environment
        if hasattr(self, 'environment'):
            valid_environments = ['development', 'test', 'production']
            if self.environment not in valid_environments:
                raise ValueError(f"Invalid environment: {self.environment}")
        
        # Validate log level  
        if hasattr(self, 'log_level'):
            valid_log_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
            if self.log_level not in valid_log_levels:
                raise ValueError(f"Invalid log level: {self.log_level}")
        
        # Validate trading mode
        if hasattr(self, 'trading_mode'):
            valid_trading_modes = ['DRY_RUN', 'LIVE']
            if self.trading_mode not in valid_trading_modes:
                raise ValueError(f"Invalid trading mode: {self.trading_mode}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value with optional default."""
        return getattr(self, key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        setattr(self, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}


def load_config_from_env() -> Config:
    """Load configuration from environment variables."""
    return Config(
        # Core config that tests expect
        environment=os.getenv("ENVIRONMENT", "development"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///test.db"),
        alpaca_api_key=os.getenv("ALPACA_API_KEY", "test-alpaca-key"),
        alpaca_secret=os.getenv("ALPACA_SECRET", "test-alpaca-secret"),
        jwt_secret_key=os.getenv("JWT_SECRET_KEY", "test-jwt-secret"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        trading_mode=os.getenv("TRADING_MODE", "DRY_RUN"),
        
        # Additional configs
        ENV=os.getenv("ENV", "test"),
        API_KEY=os.getenv("API_KEY", "test-key"),
        REDIS_URL=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        DEBUG=os.getenv("DEBUG", "false").lower() == "true",
        TESTING=os.getenv("TESTING", "false").lower() == "true",
        
        # Trading specific configs
        ALPACA_BASE_URL=os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets"),
        
        # Risk management configs
        MAX_POSITION_SIZE=float(os.getenv("MAX_POSITION_SIZE", "10000.0")),
        MAX_DAILY_LOSS=float(os.getenv("MAX_DAILY_LOSS", "5000.0")),
        
        # WebSocket configs
        WS_HEARTBEAT_INTERVAL=int(os.getenv("WS_HEARTBEAT_INTERVAL", "30")),
        WS_MAX_QUEUE_SIZE=int(os.getenv("WS_MAX_QUEUE_SIZE", "1000")),
    )
