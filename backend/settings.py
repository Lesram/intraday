"""
Settings alias for backward compatibility.
"""

# Import settings using the existing get_settings function
from .config import get_settings

# Create a settings object for import compatibility
class SettingsProxy:
    def __getattr__(self, name):
        return getattr(get_settings(), name)

settings = SettingsProxy()

# Also make get_settings available
__all__ = ["settings", "get_settings"]
