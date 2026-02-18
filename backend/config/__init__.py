"""Core package initialization."""

from .base_settings import LegacySettings, Settings
from .settings import AppSettings, get_settings


def __getattr__(name: str):
    if name in {"Config", "get_config", "load_config"}:
        from . import config as legacy_config
        return getattr(legacy_config, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'Config',
    'get_config',
    'load_config',
    'get_settings',
    'AppSettings',
    'Settings',
    'LegacySettings',
]
