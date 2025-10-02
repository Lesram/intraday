"""
Repository layer for data access.
Provides async CRUD operations with proper error handling.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from .audits import AuditNotFoundError, AuditsRepo
from .executions import DuplicateExecutionError, ExecutionNotFoundError, ExecutionsRepo
from .models import DuplicateModelError, ModelNotFoundError, ModelsRepo
from .orders import DuplicateOrderError, OrderNotFoundError, OrdersRepo
from .positions import DuplicatePositionError, PositionNotFoundError, PositionsRepo
from .signals import DuplicateSignalError, SignalNotFoundError, SignalsRepo


# Dependency injection functions
def get_user_repo():
    """Dependency to get user repository instance."""
    # In a real implementation, this would return a proper repository instance
    # For now, this will be mocked in tests
    from backend.infra.users import UsersRepo
    return UsersRepo()


def get_portfolio_repo(session: AsyncSession = Depends(get_session)):
    """Dependency to get portfolio repository instance."""
    # In a real implementation, this would return a proper repository instance
    # For now, this will be mocked in tests
    return PositionsRepo(session)


__all__ = [
    # Repository classes
    "OrdersRepo",
    "ExecutionsRepo",
    "PositionsRepo",
    "SignalsRepo",
    "ModelsRepo",
    "AuditsRepo",
    # Exception classes
    "OrderNotFoundError",
    "DuplicateOrderError",
    "ExecutionNotFoundError",
    "DuplicateExecutionError",
    "PositionNotFoundError",
    "DuplicatePositionError",
    "SignalNotFoundError",
    "DuplicateSignalError",
    "ModelNotFoundError",
    "DuplicateModelError",
    "AuditNotFoundError",
    # Dependency functions
    "get_user_repo",
    "get_portfolio_repo",
]
