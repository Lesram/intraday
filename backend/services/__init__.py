from __future__ import annotations
try:
    from . import broker_service as broker_service  # noqa: F401
except Exception:
    class _BrokerServiceStub: ...
    broker_service = _BrokerServiceStub()  # type: ignore
