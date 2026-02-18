"""
DEPRECATED: This module is a legacy stub. Use backend.config.get_settings() instead.
Kept only for backward compatibility with existing tests.
"""
import os
import warnings

if os.getenv("BACKEND_EMIT_DEPRECATION_WARNINGS", "0") == "1":
    warnings.warn(
        "backend.config_helpers is deprecated. Use backend.config.get_settings() instead.",
        DeprecationWarning,
        stacklevel=2,
    )


class Config:
    pass

def load_config_from_env():
    return Config()
