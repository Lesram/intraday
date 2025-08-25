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
except Exception:
        # Minimal fallback matching the old module-level shim behavior
        try:
                from pydantic import BaseSettings as _BaseSettings  # type: ignore
        except Exception:  # pragma: no cover - ultra fallback
                class _BaseSettings:  # type: ignore
                        pass

        class Settings(_BaseSettings):  # type: ignore
                pass

        settings = Settings()  # type: ignore

__all__ = list(globals().keys())
