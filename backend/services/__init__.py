"""
Services Package

This services package contains both active runtime services and placeholder modules.

ACTIVE SERVICES (kept in runtime):
- order_service.py: Core order management and execution service
- signal_service.py: Trading signal processing and management service

DEPRECATED SERVICES:
All other service modules are deprecated placeholder/blueprint modules and should be
moved to docs/blueprints/services/ as they are not actively used in the runtime.
"""

from __future__ import annotations

try:
    from . import broker_service as broker_service  # noqa: F401
except Exception:
    class _BrokerServiceStub: ...
    broker_service = _BrokerServiceStub()  # type: ignore
