"""Compatibility re-exports so ``from backend.config.settings import settings`` works.

This module forwards symbols from the package ``backend.config`` (``__init__``)
so code importing the legacy path continues to function without changes.
"""

from . import (  # re-export from the package namespace
    settings,
    get_settings,
    Settings,
    AppConfig,
    SecurityConfig,
    validate_required_settings,
)

__all__ = [
    "settings",
    "get_settings",
    "Settings",
    "AppConfig",
    "SecurityConfig",
    "validate_required_settings",
]
