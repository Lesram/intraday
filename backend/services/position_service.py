"""
Compatibility alias for tests expecting backend.services.position_service.PositionService
"""

from .positions_service import PositionsService as PositionService  # noqa: F401

__all__ = ["PositionService"]
