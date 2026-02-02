"""
DEPRECATED: Use backend.ml.model_manager instead.
This module is kept for backwards compatibility.

All public symbols are intentionally re-exported from the canonical
backend.ml.model_manager module to maintain backwards compatibility
with code that imports from backend.mlops.model_manager.
"""

# Intentional wildcard re-export for backwards compatibility
# The canonical implementation is in backend.ml.model_manager
from ..ml.model_manager import *  # noqa: F401,F403