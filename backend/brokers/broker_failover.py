"""
H-22 FIX: Broker Abstraction and Failover Framework

This module provides:
1. Abstract broker interface (Protocol) for consistent broker implementations
2. Failover broker manager that can switch between primary and secondary brokers
3. Health monitoring for broker connections

Usage:
    from backend.brokers.broker_failover import BrokerManager, get_broker_manager
    
    # Get the global broker manager
    manager = get_broker_manager()
    
    # Submit order through failover-aware manager
    result = await manager.submit_order(order_request)
    
Configuration via environment variables:
    PRIMARY_BROKER: "alpaca" (default)
    SECONDARY_BROKER: Optional secondary broker (e.g., "tradier", "ibkr")
    BROKER_FAILOVER_ENABLED: "true" to enable automatic failover
    BROKER_HEALTH_CHECK_INTERVAL: Seconds between health checks (default: 60)
"""

import asyncio
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from backend.utils.logger import get_logger

logger = get_logger(__name__)


class BrokerStatus(Enum):
    """Broker connection status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class BrokerHealth:
    """Health status of a broker connection."""
    broker_name: str
    status: BrokerStatus
    last_check: datetime
    consecutive_failures: int = 0
    latency_ms: float | None = None
    error_message: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderRequest:
    """Standard order request format for broker abstraction."""
    symbol: str
    qty: float
    side: str  # "buy" or "sell"
    type: str  # "market", "limit", "stop", "stop_limit"
    time_in_force: str = "day"  # "day", "gtc", "ioc", "fok"
    limit_price: float | None = None
    stop_price: float | None = None
    client_order_id: str | None = None
    extended_hours: bool = False


@dataclass
class OrderResponse:
    """Standard order response format from brokers."""
    broker_order_id: str
    client_order_id: str | None
    symbol: str
    qty: float
    filled_qty: float
    status: str
    side: str
    type: str
    submitted_at: datetime
    filled_at: datetime | None = None
    filled_avg_price: float | None = None
    broker_name: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BrokerProtocol(Protocol):
    """
    Protocol defining the interface that all broker implementations must follow.
    
    Implement this protocol to add support for new brokers.
    """
    
    @property
    def name(self) -> str:
        """Return the broker name identifier."""
        ...
    
    async def health_check(self) -> BrokerHealth:
        """Check broker connection health."""
        ...
    
    async def submit_order(self, order: OrderRequest) -> OrderResponse:
        """Submit an order to the broker."""
        ...
    
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an order by its broker order ID."""
        ...
    
    async def get_order(self, broker_order_id: str) -> OrderResponse | None:
        """Get order status by broker order ID."""
        ...
    
    async def get_positions(self) -> list[dict[str, Any]]:
        """Get current positions."""
        ...
    
    async def get_account(self) -> dict[str, Any]:
        """Get account information."""
        ...


class BaseBroker(ABC):
    """
    Abstract base class for broker implementations.
    
    Provides common functionality and enforces the BrokerProtocol interface.
    """
    
    def __init__(self, name: str):
        self._name = name
        self._health = BrokerHealth(
            broker_name=name,
            status=BrokerStatus.UNKNOWN,
            last_check=datetime.now(timezone.utc)
        )
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def health(self) -> BrokerHealth:
        return self._health
    
    @abstractmethod
    async def health_check(self) -> BrokerHealth:
        """Check broker connection health."""
        pass
    
    @abstractmethod
    async def submit_order(self, order: OrderRequest) -> OrderResponse:
        """Submit an order to the broker."""
        pass
    
    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an order."""
        pass
    
    @abstractmethod
    async def get_order(self, broker_order_id: str) -> OrderResponse | None:
        """Get order status."""
        pass
    
    @abstractmethod
    async def get_positions(self) -> list[dict[str, Any]]:
        """Get current positions."""
        pass
    
    @abstractmethod
    async def get_account(self) -> dict[str, Any]:
        """Get account information."""
        pass


class AlpacaBrokerAdapter(BaseBroker):
    """
    Adapter that wraps AlpacaBrokerClient to conform to BrokerProtocol.
    """
    
    def __init__(self):
        super().__init__("alpaca")
        # Lazy import to avoid circular dependencies
        from backend.integrations.alpaca_broker import AlpacaBrokerClient
        self._client = AlpacaBrokerClient()
    
    async def health_check(self) -> BrokerHealth:
        """Check Alpaca connection health by hitting the account endpoint."""
        import time
        start = time.perf_counter()  # L-24: Use perf_counter for precise timing
        
        try:
            account = await self._client.get_account()
            latency = (time.perf_counter() - start) * 1000
            
            self._health = BrokerHealth(
                broker_name=self.name,
                status=BrokerStatus.HEALTHY,
                last_check=datetime.now(timezone.utc),
                consecutive_failures=0,
                latency_ms=latency,
                extra={"account_status": account.get("status", "unknown")}
            )
        except Exception as e:
            self._health = BrokerHealth(
                broker_name=self.name,
                status=BrokerStatus.UNHEALTHY,
                last_check=datetime.now(timezone.utc),
                consecutive_failures=self._health.consecutive_failures + 1,
                error_message=str(e)
            )
        
        return self._health
    
    async def submit_order(self, order: OrderRequest) -> OrderResponse:
        """Submit order through Alpaca."""
        order_data = {
            "symbol": order.symbol,
            "qty": str(order.qty),
            "side": order.side,
            "type": order.type,
            "time_in_force": order.time_in_force,
        }
        
        if order.limit_price is not None:
            order_data["limit_price"] = str(order.limit_price)
        if order.stop_price is not None:
            order_data["stop_price"] = str(order.stop_price)
        if order.client_order_id:
            order_data["client_order_id"] = order.client_order_id
        if order.extended_hours:
            order_data["extended_hours"] = True
        
        result = await self._client.submit_order(**order_data)
        
        return OrderResponse(
            broker_order_id=result.get("id", ""),
            client_order_id=result.get("client_order_id"),
            symbol=result.get("symbol", order.symbol),
            qty=float(result.get("qty", order.qty)),
            filled_qty=float(result.get("filled_qty", 0)),
            status=result.get("status", "unknown"),
            side=result.get("side", order.side),
            type=result.get("type", order.type),
            submitted_at=datetime.fromisoformat(result["submitted_at"].replace("Z", "+00:00")) if result.get("submitted_at") else datetime.now(timezone.utc),
            filled_at=datetime.fromisoformat(result["filled_at"].replace("Z", "+00:00")) if result.get("filled_at") else None,
            filled_avg_price=float(result["filled_avg_price"]) if result.get("filled_avg_price") else None,
            broker_name=self.name,
            raw_response=result
        )
    
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel order through Alpaca."""
        try:
            await self._client.cancel_order(broker_order_id)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {broker_order_id}: {e}")
            return False
    
    async def get_order(self, broker_order_id: str) -> OrderResponse | None:
        """Get order status from Alpaca."""
        result = await self._client.get_order(broker_order_id)
        if not result:
            return None
        
        return OrderResponse(
            broker_order_id=result.get("id", broker_order_id),
            client_order_id=result.get("client_order_id"),
            symbol=result.get("symbol", ""),
            qty=float(result.get("qty", 0)),
            filled_qty=float(result.get("filled_qty", 0)),
            status=result.get("status", "unknown"),
            side=result.get("side", ""),
            type=result.get("type", ""),
            submitted_at=datetime.fromisoformat(result["submitted_at"].replace("Z", "+00:00")) if result.get("submitted_at") else datetime.now(timezone.utc),
            filled_at=datetime.fromisoformat(result["filled_at"].replace("Z", "+00:00")) if result.get("filled_at") else None,
            filled_avg_price=float(result["filled_avg_price"]) if result.get("filled_avg_price") else None,
            broker_name=self.name,
            raw_response=result
        )
    
    async def get_positions(self) -> list[dict[str, Any]]:
        """Get positions from Alpaca."""
        return await self._client.get_positions()
    
    async def get_account(self) -> dict[str, Any]:
        """Get account info from Alpaca."""
        return await self._client.get_account()


class BrokerManager:
    """
    H-22 FIX: Broker manager with failover support.
    
    Manages primary and secondary brokers, handles health monitoring,
    and automatically fails over when the primary broker becomes unhealthy.
    """
    
    def __init__(
        self,
        primary_broker: BaseBroker,
        secondary_broker: BaseBroker | None = None,
        failover_enabled: bool = True
    ):
        self.primary = primary_broker
        self.secondary = secondary_broker
        self.failover_enabled = failover_enabled
        self._active_broker = primary_broker
        self._health_check_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        
        logger.info(
            f"H-22: BrokerManager initialized - "
            f"Primary: {primary_broker.name}, "
            f"Secondary: {secondary_broker.name if secondary_broker else 'None'}, "
            f"Failover: {failover_enabled}"
        )
    
    @property
    def active_broker(self) -> BaseBroker:
        """Get the currently active broker."""
        return self._active_broker
    
    def get_status(self) -> dict[str, Any]:
        """Get current broker manager status."""
        return {
            "active_broker": self._active_broker.name,
            "primary_broker": self.primary.name,
            "primary_health": self.primary.health.status.value,
            "secondary_broker": self.secondary.name if self.secondary else None,
            "secondary_health": self.secondary.health.status.value if self.secondary else None,
            "failover_enabled": self.failover_enabled,
            "failover_active": self._active_broker != self.primary
        }
    
    async def check_health(self) -> dict[str, BrokerHealth]:
        """Check health of all brokers."""
        results = {}
        
        results[self.primary.name] = await self.primary.health_check()
        
        if self.secondary:
            results[self.secondary.name] = await self.secondary.health_check()
        
        return results
    
    async def _maybe_failover(self) -> bool:
        """
        Check if failover is needed and perform it if necessary.
        
        Returns True if failover occurred.
        """
        if not self.failover_enabled or not self.secondary:
            return False
        
        primary_health = self.primary.health
        secondary_health = self.secondary.health
        
        # Failover to secondary if primary is unhealthy and secondary is healthy
        if (
            self._active_broker == self.primary
            and primary_health.status == BrokerStatus.UNHEALTHY
            and primary_health.consecutive_failures >= 3
            and secondary_health.status == BrokerStatus.HEALTHY
        ):
            logger.warning(
                f"H-22: FAILOVER - Switching from {self.primary.name} to {self.secondary.name} "
                f"(primary failures: {primary_health.consecutive_failures})"
            )
            self._active_broker = self.secondary
            return True
        
        # Fail back to primary if it's healthy again
        if (
            self._active_broker == self.secondary
            and primary_health.status == BrokerStatus.HEALTHY
        ):
            logger.info(
                f"H-22: FAILBACK - Switching back to {self.primary.name} from {self.secondary.name}"
            )
            self._active_broker = self.primary
            return True
        
        return False
    
    async def submit_order(self, order: OrderRequest) -> OrderResponse:
        """
        Submit order through the active broker with failover support.
        """
        try:
            result = await self._active_broker.submit_order(order)
            return result
        except Exception as e:
            logger.error(f"Order submission failed on {self._active_broker.name}: {e}")
            
            # Try failover if enabled
            if self.failover_enabled and self.secondary:
                await self.check_health()
                if await self._maybe_failover():
                    logger.info(f"H-22: Retrying order on {self._active_broker.name} after failover")
                    return await self._active_broker.submit_order(order)
            
            raise
    
    async def cancel_order(self, broker_order_id: str, broker_name: str | None = None) -> bool:
        """
        Cancel order. If broker_name is specified, cancel on that specific broker.
        """
        if broker_name:
            if broker_name == self.primary.name:
                return await self.primary.cancel_order(broker_order_id)
            elif self.secondary and broker_name == self.secondary.name:
                return await self.secondary.cancel_order(broker_order_id)
        
        return await self._active_broker.cancel_order(broker_order_id)
    
    async def get_order(self, broker_order_id: str, broker_name: str | None = None) -> OrderResponse | None:
        """
        Get order status. If broker_name is specified, query that specific broker.
        """
        if broker_name:
            if broker_name == self.primary.name:
                return await self.primary.get_order(broker_order_id)
            elif self.secondary and broker_name == self.secondary.name:
                return await self.secondary.get_order(broker_order_id)
        
        return await self._active_broker.get_order(broker_order_id)
    
    async def get_positions(self) -> list[dict[str, Any]]:
        """Get positions from active broker."""
        return await self._active_broker.get_positions()
    
    async def get_account(self) -> dict[str, Any]:
        """Get account info from active broker."""
        return await self._active_broker.get_account()
    
    async def start_health_monitoring(self, interval_seconds: int = 60) -> None:
        """Start background health monitoring task."""
        if self._health_check_task is not None and not self._health_check_task.done():
            logger.warning("H-22: Health monitoring already running")
            return
        
        self._stop_event = asyncio.Event()
        
        async def _monitor_loop():
            while not self._stop_event.is_set():
                try:
                    await self.check_health()
                    await self._maybe_failover()
                except Exception as e:
                    logger.error(f"H-22: Health monitoring error: {e}")
                
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=interval_seconds
                    )
                except asyncio.TimeoutError:
                    pass
        
        self._health_check_task = asyncio.create_task(
            _monitor_loop(),
            name="broker_health_monitor"
        )
        logger.info(f"H-22: Broker health monitoring started (interval: {interval_seconds}s)")
    
    async def stop_health_monitoring(self) -> None:
        """Stop background health monitoring.

        Audit-J finding J-5 (2026-05-02): cancel was issued without
        awaiting the cancellation, so the task could still be running
        when self._health_check_task = None overwrote the reference.
        Now: cancel + await CancelledError so cleanup completes before
        return.
        """
        if self._stop_event:
            self._stop_event.set()

        if self._health_check_task:
            try:
                await asyncio.wait_for(self._health_check_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._health_check_task.cancel()
                # Wait for cancellation to actually finish so any
                # in-flight broker.cancel_order() / httpx session release
                # completes before we drop the reference.
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            self._health_check_task = None

        logger.info("H-22: Broker health monitoring stopped")


# Global broker manager instance
_broker_manager: BrokerManager | None = None


def get_broker_manager() -> BrokerManager:
    """
    Get or create the global broker manager instance.
    
    Configuration via environment variables:
        PRIMARY_BROKER: "alpaca" (default)
        SECONDARY_BROKER: Optional, not implemented yet
        BROKER_FAILOVER_ENABLED: "true" or "false"
    """
    global _broker_manager
    
    if _broker_manager is None:
        primary_name = os.environ.get("PRIMARY_BROKER", "alpaca").lower()
        secondary_name = os.environ.get("SECONDARY_BROKER", "").lower()
        failover_enabled = os.environ.get("BROKER_FAILOVER_ENABLED", "true").lower() in ("true", "1", "yes")
        
        # Create primary broker
        if primary_name == "alpaca":
            primary = AlpacaBrokerAdapter()
        else:
            logger.warning(f"Unknown primary broker '{primary_name}', defaulting to Alpaca")
            primary = AlpacaBrokerAdapter()
        
        # Create secondary broker if specified
        secondary = None
        if secondary_name:
            if secondary_name == "alpaca":
                # Could be a different Alpaca account/mode
                secondary = AlpacaBrokerAdapter()
                logger.info("H-22: Secondary broker configured as Alpaca (may use different credentials)")
            else:
                logger.warning(
                    f"H-22: Secondary broker '{secondary_name}' not implemented yet. "
                    "Implement a BaseBroker subclass for this broker."
                )
        
        _broker_manager = BrokerManager(
            primary_broker=primary,
            secondary_broker=secondary,
            failover_enabled=failover_enabled
        )
    
    return _broker_manager


async def initialize_broker_manager() -> BrokerManager:
    """
    Initialize and start the broker manager with health monitoring.
    
    Call this during application startup.
    """
    manager = get_broker_manager()
    
    # Perform initial health check
    await manager.check_health()
    
    # Start background monitoring
    interval = int(os.environ.get("BROKER_HEALTH_CHECK_INTERVAL", "60"))
    await manager.start_health_monitoring(interval)
    
    return manager


async def shutdown_broker_manager() -> None:
    """
    Shutdown the broker manager gracefully.
    
    Call this during application shutdown.
    """
    global _broker_manager
    
    if _broker_manager:
        await _broker_manager.stop_health_monitoring()
        _broker_manager = None
