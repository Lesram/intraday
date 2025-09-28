"""
backend.config package

Preserves legacy imports and provides:
  - from backend.config import settings, Settings, ...
  - from backend.config.settings import settings
  - import backend.config.settings

Primary API is re-exported from .settings; a minimal fallback is provided if
that import fails during early boot to avoid hard errors in integration runs.
"""

try:
        # Re-export everything from .settings for backward compatibility
        from .settings import *  # type: ignore  # noqa: F401,F403
        # Ensure Settings is explicitly available
        from .settings import Settings, AppSettings, settings, get_settings
except Exception as e:
        # Minimal fallback matching the old module-level shim behavior
        try:
                from pydantic import BaseSettings as _BaseSettings  # type: ignore
        except Exception:  # pragma: no cover - ultra fallback
                class _BaseSettings:  # type: ignore
                        pass

        class Settings(_BaseSettings):  # type: ignore
                pass

        AppSettings = Settings  # type: ignore
        settings = Settings()  # type: ignore
        get_settings = lambda: Settings()  # type: ignore

# Export the imported names
__all__ = ['Settings', 'AppSettings', 'settings', 'get_settings'] + [name for name in globals().keys() if not name.startswith('_')]
