"""
Repository layer for data access.
Provides async CRUD operations with proper error handling.
"""

from .audits import AuditNotFoundError, AuditsRepo
from .executions import DuplicateExecutionError, ExecutionNotFoundError, ExecutionsRepo
from .models import DuplicateModelError, ModelNotFoundError, ModelsRepo
from .orders import DuplicateOrderError, OrderNotFoundError, OrdersRepo
from .positions import DuplicatePositionError, PositionNotFoundError, PositionsRepo
from .signals import DuplicateSignalError, SignalNotFoundError, SignalsRepo

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
    "AuditNotFoundError"
]
