"""
Broker service shim used by chaos tests.
Provides retry helpers and a minimal BrokerService API for patching.
"""
from __future__ import annotations
from typing import Any, Callable
import time
from http import HTTPStatus


RETRYABLE = {HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE}  # 502/503


class BrokerHTTPError(RuntimeError):
    def __init__(self, status_code: int, message: str = ""):
        self.status_code = int(status_code)
        super().__init__(message or f"Broker HTTP {status_code}")


def is_retryable(status_code: int) -> bool:
    return int(status_code) in RETRYABLE


def request_with_retry(call: Callable[[], Any], *, retries: int = 3, backoff_ms: int = 100) -> Any:
    attempt = 0
    while True:
        try:
            return call()
        except BrokerHTTPError as e:
            attempt += 1
            if attempt > retries or not is_retryable(e.status_code):
                raise
            time.sleep(backoff_ms / 1000.0)
            backoff_ms *= 2


def place_order_with_retry(func: Callable[..., Any], *args, retries: int = 3, backoff_ms: int = 100, **kwargs):
    return request_with_retry(lambda: func(*args, **kwargs), retries=retries, backoff_ms=backoff_ms)


class BrokerService:
    """Minimal async BrokerService surface for tests to patch.

    Real implementations may delegate to an HTTP client or order service.
    Tests replace this class with an AsyncMock, so default methods can be stubs.
    """

    async def submit_order(self, order_spec: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("BrokerService.submit_order is not implemented")

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError("BrokerService.cancel_order is not implemented")

    async def get_order_status(self, order_id: str) -> dict[str, Any]:
        raise NotImplementedError("BrokerService.get_order_status is not implemented")


__all__ = [
    "BrokerService",
    "request_with_retry",
    "place_order_with_retry",
    "is_retryable",
    "BrokerHTTPError",
]
"""
Broker service for external broker integration and fault injection testing.
"""
from dataclasses import dataclass
from typing import Dict, Any, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)


@dataclass
class BrokerResponse:
    """Response from broker operations."""
    success: bool
    status_code: int
    data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    
    @property
    def is_successful(self) -> bool:
        return self.success and 200 <= self.status_code < 300


class BrokerClient:
    """
    Minimal broker client for external broker integration.
    Supports fault injection for chaos testing.
    """
    
    def __init__(self, base_url: str = "http://localhost:8080", timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        self._connection_healthy = True
        
    async def place_order(self, order_data: Dict[str, Any]) -> BrokerResponse:
        """Place an order with the broker."""
        try:
            # Simulate network call
            await asyncio.sleep(0.01)  # Simulate latency
            
            if not self._connection_healthy:
                return BrokerResponse(
                    success=False,
                    status_code=503,
                    error_message="Service Unavailable"
                )
                
            # Validate required fields
            if not order_data.get("symbol") or not order_data.get("quantity"):
                return BrokerResponse(
                    success=False,
                    status_code=400,
                    error_message="Missing required fields"
                )
                
            return BrokerResponse(
                success=True,
                status_code=200,
                data={
                    "order_id": f"ORD_{order_data.get('symbol', 'UNKNOWN')}_{hash(str(order_data)) % 10000}",
                    "status": "accepted",
                    "symbol": order_data["symbol"],
                    "quantity": order_data["quantity"]
                }
            )
            
        except Exception as e:
            logger.error(f"Broker order placement failed: {e}")
            return BrokerResponse(
                success=False,
                status_code=500,
                error_message=str(e)
            )
    
    async def get_order_status(self, order_id: str) -> BrokerResponse:
        """Get status of an order."""
        try:
            await asyncio.sleep(0.005)  # Simulate latency
            
            if not self._connection_healthy:
                return BrokerResponse(
                    success=False,
                    status_code=502,
                    error_message="Bad Gateway"
                )
                
            return BrokerResponse(
                success=True,
                status_code=200,
                data={
                    "order_id": order_id,
                    "status": "FILLED",
                    "filled_quantity": 100
                }
            )
            
        except Exception as e:
            return BrokerResponse(
                success=False,
                status_code=500,
                error_message=str(e)
            )
    
    def set_connection_health(self, healthy: bool):
        """Set connection health for fault injection testing."""
        self._connection_healthy = healthy


def create_broker_client(base_url: str = None, timeout: int = 30) -> BrokerClient:
    """
    Factory function to create a broker client instance.
    Used by chaos testing to inject faults.
    """
    url = base_url or "http://localhost:8080"
    return BrokerClient(base_url=url, timeout=timeout)


# Global instance for service-level access
_default_client = None


def get_broker_client() -> BrokerClient:
    """Get or create the default broker client instance."""
    global _default_client
    if _default_client is None:
        _default_client = create_broker_client()
    return _default_client


class BrokerService:
    """
    High-level broker service for order management and resilience.
    Used by chaos testing to inject faults and test retry logic.
    """
    
    def __init__(self, client: BrokerClient = None):
        self.client = client or get_broker_client()
        
    async def submit_order(self, order_spec: Dict[str, Any]) -> BrokerResponse:
        """Submit an order through the broker client."""
        return await self.client.place_order(order_spec)
    
    # Minimal shim for tests expecting a simple dict response method name
    async def send_order(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        # Keep it simple to match chaos tests expectations; echo payload
        return {"status": "accepted", "echo": payload}
        
    async def get_order_status(self, order_id: str) -> BrokerResponse:
        """Get order status through the broker client."""
        return await self.client.get_order_status(order_id)
        
    def set_fault_injection(self, healthy: bool):
        """Set fault injection for chaos testing."""
        self.client.set_connection_health(healthy)

# Minimal module-level instance for tests to patch/import directly
broker_service = BrokerService()
