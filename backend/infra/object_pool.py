"""
Object Pooling for Frequently Created Objects (L-22)

Provides object pools to reduce allocation overhead for frequently
created/destroyed objects in hot paths.

Usage:
    from backend.infra.object_pool import OrderPool, get_order_pool
    
    # Get a pooled order
    pool = get_order_pool()
    order = pool.acquire()
    order.reset(symbol="AAPL", side="buy", qty=100)
    
    # ... use order ...
    
    # Return to pool
    pool.release(order)
    
    # Or use context manager
    with pool.acquire_context() as order:
        order.reset(symbol="AAPL", side="buy", qty=100)
        # ... use order ...
    # Automatically released
"""

import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Generic, TypeVar

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Metrics
pool_acquisitions = Counter(
    "object_pool_acquisitions_total",
    "Total object pool acquisitions",
    ["pool_name", "source"],  # source: pool, new
)

pool_releases = Counter(
    "object_pool_releases_total",
    "Total object pool releases",
    ["pool_name"],
)

pool_size = Gauge(
    "object_pool_size",
    "Current objects in pool",
    ["pool_name"],
)

pool_acquisition_time = Histogram(
    "object_pool_acquisition_seconds",
    "Time to acquire object from pool",
    ["pool_name"],
    buckets=[0.00001, 0.00005, 0.0001, 0.0005, 0.001, 0.005, 0.01],
)

T = TypeVar("T")


class Poolable(ABC):
    """Interface for objects that can be pooled."""

    @abstractmethod
    def reset(self, **kwargs) -> None:
        """Reset object state for reuse."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear object state before returning to pool."""
        pass


@dataclass
class PoolConfig:
    """Configuration for object pool."""

    initial_size: int = 10
    max_size: int = 100
    name: str = "default"


class ObjectPool(Generic[T]):
    """
    Thread-safe object pool implementation.
    
    Reduces allocation overhead by reusing objects instead of
    creating new ones for each use.
    """

    def __init__(
        self,
        factory: type[T],
        config: PoolConfig | None = None,
    ):
        """
        Initialize object pool.
        
        Args:
            factory: Class to instantiate for new objects
            config: Pool configuration
        """
        self.factory = factory
        self.config = config or PoolConfig()
        self._pool: deque[T] = deque()
        self._lock = threading.Lock()
        self._created_count = 0
        
        # Pre-populate pool
        self._initialize_pool()

    def _initialize_pool(self) -> None:
        """Pre-create initial objects."""
        for _ in range(self.config.initial_size):
            obj = self.factory()
            self._pool.append(obj)
            self._created_count += 1
        
        pool_size.labels(pool_name=self.config.name).set(len(self._pool))
        logger.debug(
            f"Initialized pool '{self.config.name}' with {self.config.initial_size} objects"
        )

    def acquire(self) -> T:
        """
        Acquire an object from the pool.
        
        Returns a pooled object if available, otherwise creates a new one.
        """
        import time
        start = time.perf_counter()
        
        with self._lock:
            if self._pool:
                obj = self._pool.popleft()
                pool_acquisitions.labels(
                    pool_name=self.config.name, source="pool"
                ).inc()
            else:
                # Pool empty, create new if under max
                if self._created_count < self.config.max_size:
                    obj = self.factory()
                    self._created_count += 1
                    pool_acquisitions.labels(
                        pool_name=self.config.name, source="new"
                    ).inc()
                else:
                    # At max capacity, still create but log warning
                    obj = self.factory()
                    pool_acquisitions.labels(
                        pool_name=self.config.name, source="overflow"
                    ).inc()
                    logger.warning(
                        f"Pool '{self.config.name}' at max capacity ({self.config.max_size})"
                    )
            
            pool_size.labels(pool_name=self.config.name).set(len(self._pool))
        
        pool_acquisition_time.labels(pool_name=self.config.name).observe(
            time.perf_counter() - start
        )
        return obj

    def release(self, obj: T) -> None:
        """
        Return an object to the pool.
        
        Clears the object state before pooling if it implements Poolable.
        """
        # Clear object state
        if isinstance(obj, Poolable):
            obj.clear()
        
        with self._lock:
            if len(self._pool) < self.config.max_size:
                self._pool.append(obj)
            # If pool is full, just let the object be garbage collected
            
            pool_size.labels(pool_name=self.config.name).set(len(self._pool))
        
        pool_releases.labels(pool_name=self.config.name).inc()

    @contextmanager
    def acquire_context(self):
        """Context manager for automatic release."""
        obj = self.acquire()
        try:
            yield obj
        finally:
            self.release(obj)

    def stats(self) -> dict:
        """Get pool statistics."""
        with self._lock:
            return {
                "name": self.config.name,
                "available": len(self._pool),
                "created": self._created_count,
                "max_size": self.config.max_size,
            }


class AsyncObjectPool(Generic[T]):
    """
    Async-compatible object pool.
    
    Similar to ObjectPool but uses asyncio locks for async contexts.
    """

    def __init__(
        self,
        factory: type[T],
        config: PoolConfig | None = None,
    ):
        self.factory = factory
        self.config = config or PoolConfig()
        self._pool: deque[T] = deque()
        self._lock = asyncio.Lock()
        self._created_count = 0
        
        # Sync initialization (can't be async in __init__)
        for _ in range(self.config.initial_size):
            obj = self.factory()
            self._pool.append(obj)
            self._created_count += 1

    async def acquire(self) -> T:
        """Acquire an object from the pool (async)."""
        async with self._lock:
            if self._pool:
                return self._pool.popleft()
            else:
                self._created_count += 1
                return self.factory()

    async def release(self, obj: T) -> None:
        """Return an object to the pool (async)."""
        if isinstance(obj, Poolable):
            obj.clear()
        
        async with self._lock:
            if len(self._pool) < self.config.max_size:
                self._pool.append(obj)

    @asynccontextmanager
    async def acquire_context(self):
        """Async context manager for automatic release."""
        obj = await self.acquire()
        try:
            yield obj
        finally:
            await self.release(obj)


# ============================================================================
# Poolable Order Object
# ============================================================================

@dataclass
class PooledOrder(Poolable):
    """
    Poolable order object for high-frequency order creation.
    
    Instead of creating new Order objects for each trade, reuse
    pooled instances to reduce GC pressure.
    """
    
    # Order fields
    symbol: str = ""
    side: str = ""  # buy, sell
    qty: Decimal = field(default_factory=lambda: Decimal(0))
    order_type: str = "market"
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "day"
    
    # Metadata
    client_order_id: str = ""
    strategy_id: str | None = None
    created_at: datetime | None = None
    
    # Internal
    _is_active: bool = False

    def reset(
        self,
        symbol: str,
        side: str,
        qty: Decimal | float | int,
        order_type: str = "market",
        limit_price: Decimal | float | None = None,
        stop_price: Decimal | float | None = None,
        time_in_force: str = "day",
        client_order_id: str = "",
        strategy_id: str | None = None,
    ) -> "PooledOrder":
        """Reset order with new values."""
        self.symbol = symbol
        self.side = side
        self.qty = Decimal(str(qty))
        self.order_type = order_type
        self.limit_price = Decimal(str(limit_price)) if limit_price else None
        self.stop_price = Decimal(str(stop_price)) if stop_price else None
        self.time_in_force = time_in_force
        self.client_order_id = client_order_id
        self.strategy_id = strategy_id
        self.created_at = datetime.now(UTC)
        self._is_active = True
        return self

    def clear(self) -> None:
        """Clear all fields before returning to pool."""
        self.symbol = ""
        self.side = ""
        self.qty = Decimal(0)
        self.order_type = "market"
        self.limit_price = None
        self.stop_price = None
        self.time_in_force = "day"
        self.client_order_id = ""
        self.strategy_id = None
        self.created_at = None
        self._is_active = False

    def to_dict(self) -> dict:
        """Convert to dictionary for API submission."""
        result = {
            "symbol": self.symbol,
            "side": self.side,
            "qty": str(self.qty),
            "type": self.order_type,
            "time_in_force": self.time_in_force,
        }
        if self.limit_price:
            result["limit_price"] = str(self.limit_price)
        if self.stop_price:
            result["stop_price"] = str(self.stop_price)
        if self.client_order_id:
            result["client_order_id"] = self.client_order_id
        return result


# ============================================================================
# Pool Singletons
# ============================================================================

_order_pool: ObjectPool[PooledOrder] | None = None
_order_pool_lock = threading.Lock()


def get_order_pool() -> ObjectPool[PooledOrder]:
    """Get or create the global order pool singleton."""
    global _order_pool
    if _order_pool is None:
        with _order_pool_lock:
            if _order_pool is None:
                _order_pool = ObjectPool(
                    PooledOrder,
                    PoolConfig(
                        initial_size=20,
                        max_size=200,
                        name="orders",
                    ),
                )
    return _order_pool


# ============================================================================
# Convenience Functions
# ============================================================================

def acquire_order() -> PooledOrder:
    """Acquire a pooled order object."""
    return get_order_pool().acquire()


def release_order(order: PooledOrder) -> None:
    """Release an order back to the pool."""
    get_order_pool().release(order)


@contextmanager
def pooled_order():
    """Context manager for pooled order with automatic release."""
    with get_order_pool().acquire_context() as order:
        yield order
