"""
Service layer for business logic and orchestration.
Ensures submodules like `backend.services.broker_service` are importable for patching.
"""

from .order_service import OrderService

# Ensure `backend.services.broker_service` can be resolved by patch() and imports.
from importlib import import_module as _import_module
try:  # load eagerly so attribute exists on `backend.services`
	broker_service = _import_module(".broker_service", __name__)
except Exception:  # pragma: no cover
	broker_service = None  # still creates attribute for patch resolution

__all__ = ["OrderService", "broker_service"]
