"""
Compatibility shim so that "backend.config" behaves like a package and
"from backend.config.settings import settings" works reliably.

We expose __path__ to make this module package-like, and forward common
symbols from the real package module under backend/config/.
"""

from __future__ import annotations

import os as _os

# Treat this module as a package so submodule imports are allowed
__path__ = [_os.path.join(_os.path.dirname(__file__), "config")]  # type: ignore[var-annotated]

# Re-export common names from the real package implementation if available
try:  # pragma: no cover - simple forwarding
    from .config.settings import (  # type: ignore
        settings,  # noqa: F401
        get_settings,  # noqa: F401
        Settings,  # noqa: F401
        AppConfig,  # noqa: F401
        SecurityConfig,  # noqa: F401
        LegacySettings,  # noqa: F401
        validate_required_settings,  # noqa: F401
    )
except Exception:
    # Minimal fallback to avoid hard failures during early import
    try:
        from pydantic import BaseSettings as _BaseSettings  # type: ignore
    except Exception:  # pragma: no cover - ultra fallback
        class _BaseSettings:  # type: ignore
            pass

    class Settings(_BaseSettings):  # type: ignore
        pass

    settings = Settings()  # type: ignore
