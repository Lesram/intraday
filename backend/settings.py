"""
Settings alias for backward compatibility.
"""

# Import settings using the existing get_settings function
from .config import get_settings

# Create a settings object for import compatibility
class SettingsProxy:
    def __getattr__(self, name):
        return getattr(get_settings(), name)

    # Legacy flat attribute used in some tests
    @property
    def DATABASE_URL(self) -> str:
        return get_settings().data.database_url

    @DATABASE_URL.setter
    def DATABASE_URL(self, value: str) -> None:
        get_settings().data.database_url = value

    @DATABASE_URL.deleter
    def DATABASE_URL(self) -> None:
        # No-op deleter for compatibility with patch.object teardown
        # Optionally reset to a safe default if needed
        return None

settings = SettingsProxy()

# Also make get_settings available
__all__ = ["settings", "get_settings"]
