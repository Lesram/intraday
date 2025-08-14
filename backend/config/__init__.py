"""Configuration package public API.

This package exposes the strongly-typed Pydantic settings and helpers from
``backend.config.base_settings`` so callers can use::

    from backend.config import Settings, get_settings, AlpacaConfig, ...

Compatibility: ``backend.config.settings`` continues to work via the dedicated
module that re-exports from this package namespace.
"""

from .base_settings import (
    AppConfig,
    SecurityConfig,
    AlpacaConfig,
    DataConfig,
    WebsocketConfig,
    MetricsConfig,
    DatabaseConfig,
    TradingConfig,
    OutboxConfig,
    ObservabilityConfig,
    MLOpsConfig,
    Settings,
    get_settings,
    get_legacy_settings,
    validate_required_settings,
)

__all__ = [
    "AppConfig",
    "SecurityConfig",
    "AlpacaConfig",
    "DataConfig",
    "WebsocketConfig",
    "MetricsConfig",
    "DatabaseConfig",
    "TradingConfig",
    "OutboxConfig",
    "ObservabilityConfig",
    "MLOpsConfig",
    "Settings",
    "get_settings",
    "get_legacy_settings",
    "validate_required_settings",
]

