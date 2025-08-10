"""
Repository layer for data access.
Provides async CRUD operations with proper error handling.
"""

from .orders import OrdersRepo, OrderNotFoundError, DuplicateOrderError
from .executions import ExecutionsRepo, ExecutionNotFoundError, DuplicateExecutionError
from .positions import PositionsRepo, PositionNotFoundError, DuplicatePositionError
from .signals import SignalsRepo, SignalNotFoundError, DuplicateSignalError
from .models import ModelsRepo, ModelNotFoundError, DuplicateModelError
from .audits import AuditsRepo, AuditNotFoundError

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
