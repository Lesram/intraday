"""
Config module alias/shim for tests that import backend.config.settings
without requiring repo restructuring.
"""
# Instantiate settings for tests expecting module-level `settings`
try:
    Settings  # type: ignore[name-defined]
except NameError:
    from pydantic import BaseSettings
    class Settings(BaseSettings):
        pass

settings = Settings()

# Create an import alias so `from backend.config.settings import settings` works
import sys as _sys
_sys.modules[f"{__name__}.settings"] = _sys.modules[__name__]
