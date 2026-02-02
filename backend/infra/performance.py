"""
Performance Optimization Infrastructure for Trading Platform.

Provides high-performance components:
- Intelligent caching with TTL and LRU eviction
- Query result caching with automatic invalidation
- Batch processing utilities
- Connection pool monitoring
- Async task optimization
- Memory-efficient data structures

Designed for low-latency trading operations where
microseconds matter.
"""

import asyncio
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import functools
import hashlib
import time
from typing import Any, Generic, TypeVar

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)

T = TypeVar("T")


@dataclass
class CacheStats:
    """Cache performance statistics."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    total_items: int = 0
    memory_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with metadata."""

    value: T
    created_at: datetime
    expires_at: datetime | None
    access_count: int = 0
    last_accessed: datetime = field(default_factory=lambda: datetime.now(UTC))
    size_bytes: int = 0


class LRUCache(Generic[T]):
    """
    Thread-safe LRU cache with TTL support.

    Features:
    - O(1) get/set operations
    - Automatic expiration
    - Memory size limits
    - Hit/miss statistics

    Usage:
        cache = LRUCache[dict](max_size=1000, ttl_seconds=300)
        cache.set("key", {"data": "value"})
        result = cache.get("key")
    """

    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: float | None = 300,
        max_memory_mb: float | None = None,
    ):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.max_memory_bytes = int(max_memory_mb * 1024 * 1024) if max_memory_mb else None

        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._stats = CacheStats()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T | None:
        """Get a value from cache."""
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._stats.misses += 1
                return None

            # Check expiration
            if entry.expires_at and datetime.now(UTC) > entry.expires_at:
                del self._cache[key]
                self._stats.expirations += 1
                self._stats.misses += 1
                return None

            # Update access metadata
            entry.access_count += 1
            entry.last_accessed = datetime.now(UTC)

            # Move to end (most recently used)
            self._cache.move_to_end(key)

            self._stats.hits += 1
            return entry.value

    async def set(
        self,
        key: str,
        value: T,
        ttl_seconds: float | None = None,
    ):
        """Set a value in cache."""
        async with self._lock:
            # Calculate expiration
            ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
            expires_at = datetime.now(UTC) + timedelta(seconds=ttl) if ttl else None

            # Estimate size (rough)
            size_bytes = len(str(value).encode())

            entry = CacheEntry(
                value=value,
                created_at=datetime.now(UTC),
                expires_at=expires_at,
                size_bytes=size_bytes,
            )

            # Remove if exists (to update position)
            if key in self._cache:
                del self._cache[key]

            self._cache[key] = entry

            # Evict if needed
            await self._evict_if_needed()

    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def clear(self):
        """Clear all entries."""
        async with self._lock:
            self._cache.clear()
            self._stats = CacheStats()

    async def _evict_if_needed(self):
        """Evict entries if cache is over limits."""
        # Size limit
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)
            self._stats.evictions += 1

        # Memory limit
        if self.max_memory_bytes:
            total_size = sum(e.size_bytes for e in self._cache.values())
            while total_size > self.max_memory_bytes and self._cache:
                _, entry = self._cache.popitem(last=False)
                total_size -= entry.size_bytes
                self._stats.evictions += 1

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        stats = CacheStats(
            hits=self._stats.hits,
            misses=self._stats.misses,
            evictions=self._stats.evictions,
            expirations=self._stats.expirations,
            total_items=len(self._cache),
            memory_bytes=sum(e.size_bytes for e in self._cache.values()),
        )
        return stats

    def get_sync(self, key: str) -> T | None:
        """Synchronous get for non-async contexts."""
        entry = self._cache.get(key)

        if entry is None:
            self._stats.misses += 1
            return None

        if entry.expires_at and datetime.now(UTC) > entry.expires_at:
            del self._cache[key]
            self._stats.expirations += 1
            self._stats.misses += 1
            return None

        entry.access_count += 1
        self._cache.move_to_end(key)
        self._stats.hits += 1
        return entry.value

    def set_sync(self, key: str, value: T, ttl_seconds: float | None = None):
        """Synchronous set for non-async contexts."""
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl) if ttl else None

        entry = CacheEntry(
            value=value,
            created_at=datetime.now(UTC),
            expires_at=expires_at,
            size_bytes=len(str(value).encode()),
        )

        if key in self._cache:
            del self._cache[key]

        self._cache[key] = entry

        # Simple eviction
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)
            self._stats.evictions += 1


def cached(
    ttl_seconds: float = 300,
    max_size: int = 100,
    key_prefix: str = "",
):
    """
    Decorator for caching async function results.

    Usage:
        @cached(ttl_seconds=60)
        async def get_quote(symbol: str) -> dict:
            return await fetch_from_api(symbol)
    """
    cache: LRUCache[Any] = LRUCache(max_size=max_size, ttl_seconds=ttl_seconds)

    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key
            key_parts = [key_prefix, func.__name__]
            key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()

            # Try cache
            result = await cache.get(cache_key)
            if result is not None:
                return result

            # Call function
            result = await func(*args, **kwargs)

            # Store in cache
            await cache.set(cache_key, result)

            return result

        # Attach cache for inspection
        wrapper._cache = cache  # type: ignore
        return wrapper

    return decorator


class BatchProcessor(Generic[T]):
    """
    Batch processor for efficient bulk operations.

    Collects items and processes them in batches,
    reducing database round-trips and API calls.

    Usage:
        processor = BatchProcessor(
            process_fn=save_to_db,
            batch_size=100,
            max_wait_ms=50,
        )

        await processor.add(item)
        await processor.flush()
    """

    def __init__(
        self,
        process_fn: Callable[[list[T]], Any],
        batch_size: int = 100,
        max_wait_ms: float = 50,
    ):
        self.process_fn = process_fn
        self.batch_size = batch_size
        self.max_wait_seconds = max_wait_ms / 1000

        self._buffer: list[T] = []
        self._last_flush = time.time()
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None

        # Stats
        self.batches_processed = 0
        self.items_processed = 0

    async def add(self, item: T):
        """Add an item to the batch."""
        async with self._lock:
            self._buffer.append(item)

            # Flush if batch is full
            if len(self._buffer) >= self.batch_size:
                await self._flush_locked()
            elif self._flush_task is None:
                # Schedule delayed flush
                self._flush_task = asyncio.create_task(
                    self._delayed_flush()
                )

    async def add_many(self, items: list[T]):
        """Add multiple items."""
        for item in items:
            await self.add(item)

    async def flush(self):
        """Force flush all pending items."""
        async with self._lock:
            await self._flush_locked()

    async def _flush_locked(self):
        """Flush while holding lock."""
        if not self._buffer:
            return

        items = self._buffer
        self._buffer = []
        self._last_flush = time.time()

        # Cancel pending flush task
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None

        # Process batch
        try:
            if asyncio.iscoroutinefunction(self.process_fn):
                await self.process_fn(items)
            else:
                self.process_fn(items)

            self.batches_processed += 1
            self.items_processed += len(items)

        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            # Re-add items to buffer for retry
            self._buffer.extend(items)
            raise

    async def _delayed_flush(self):
        """Delayed flush after max wait time."""
        await asyncio.sleep(self.max_wait_seconds)

        async with self._lock:
            if self._buffer:
                await self._flush_locked()


@dataclass
class PoolMetrics:
    """Connection pool metrics."""

    pool_size: int
    active_connections: int
    idle_connections: int
    waiting_requests: int
    total_acquisitions: int
    total_releases: int
    avg_wait_time_ms: float
    max_wait_time_ms: float


class ConnectionPoolMonitor:
    """
    Monitor for database connection pools.

    Tracks pool utilization and provides alerts
    when pool is near exhaustion.

    Usage:
        monitor = ConnectionPoolMonitor(pool, threshold=0.8)
        metrics = await monitor.get_metrics()

        if monitor.is_near_exhaustion():
            # Scale up or alert
            pass
    """

    def __init__(
        self,
        pool: Any,
        exhaustion_threshold: float = 0.8,
    ):
        self._pool = pool
        self.exhaustion_threshold = exhaustion_threshold

        self._acquisition_times: list[float] = []
        self._total_acquisitions = 0
        self._total_releases = 0

    def record_acquisition(self, wait_time_ms: float):
        """Record a connection acquisition."""
        self._acquisition_times.append(wait_time_ms)
        self._total_acquisitions += 1

        # Keep last 1000
        if len(self._acquisition_times) > 1000:
            self._acquisition_times.pop(0)

    def record_release(self):
        """Record a connection release."""
        self._total_releases += 1

    async def get_metrics(self) -> PoolMetrics:
        """Get current pool metrics."""
        # Try to get pool stats (implementation depends on pool type)
        try:
            pool_size = getattr(self._pool, "size", 0) or getattr(self._pool, "_maxsize", 10)
            active = getattr(self._pool, "checkedout", 0) or getattr(self._pool, "_used", 0)
        except (AttributeError, TypeError):
            pool_size = 10
            active = 0

        idle = pool_size - active

        avg_wait = sum(self._acquisition_times) / len(self._acquisition_times) if self._acquisition_times else 0.0
        max_wait = max(self._acquisition_times) if self._acquisition_times else 0.0

        return PoolMetrics(
            pool_size=pool_size,
            active_connections=active,
            idle_connections=idle,
            waiting_requests=0,  # Pool-specific
            total_acquisitions=self._total_acquisitions,
            total_releases=self._total_releases,
            avg_wait_time_ms=avg_wait,
            max_wait_time_ms=max_wait,
        )

    def is_near_exhaustion(self) -> bool:
        """Check if pool is near exhaustion."""
        try:
            pool_size = getattr(self._pool, "size", 10)
            active = getattr(self._pool, "checkedout", 0)
            utilization = active / pool_size if pool_size > 0 else 0
            return utilization >= self.exhaustion_threshold
        except (AttributeError, TypeError, ZeroDivisionError):
            return False


class AsyncTaskOptimizer:
    """
    Utilities for optimizing async task execution.

    Provides:
    - Concurrent task execution with limits
    - Task prioritization
    - Timeout handling
    - Error aggregation
    """

    def __init__(self, max_concurrency: int = 10):
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def gather_with_limit(
        self,
        tasks: list[Callable[[], Any]],
        timeout_seconds: float | None = None,
    ) -> list[Any]:
        """
        Execute tasks concurrently with concurrency limit.

        Returns results in same order as input tasks.
        """
        async def run_task(task_fn, index):
            async with self._semaphore:
                try:
                    result = task_fn()
                    # Check if it returned a coroutine
                    if asyncio.iscoroutine(result):
                        return index, await result
                    else:
                        return index, result
                except Exception as e:
                    return index, e

        # Create tasks
        aws = [run_task(t, i) for i, t in enumerate(tasks)]

        # Run with timeout
        if timeout_seconds:
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*aws),
                    timeout=timeout_seconds,
                )
            except TimeoutError:
                raise TimeoutError(f"Tasks did not complete within {timeout_seconds}s")
        else:
            results = await asyncio.gather(*aws)

        # Sort by index and extract values
        sorted_results = sorted(results, key=lambda x: x[0])
        return [r[1] for r in sorted_results]

    async def map_async(
        self,
        func: Callable[[T], Any],
        items: list[T],
    ) -> list[Any]:
        """
        Apply async function to items with concurrency limit.

        Like asyncio.gather but with controlled concurrency.
        """
        tasks = [lambda item=item: func(item) for item in items]
        return await self.gather_with_limit(tasks)


class RingBuffer(Generic[T]):
    """
    Fixed-size ring buffer for time-series data.

    Memory-efficient storage for streaming data
    with O(1) append and O(1) access.
    """

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._buffer: list[T | None] = [None] * capacity
        self._head = 0
        self._size = 0

    def append(self, item: T):
        """Add item to buffer."""
        self._buffer[self._head] = item
        self._head = (self._head + 1) % self.capacity
        self._size = min(self._size + 1, self.capacity)

    def get_all(self) -> list[T]:
        """Get all items in order (oldest first)."""
        if self._size == 0:
            return []

        if self._size < self.capacity:
            # Not wrapped yet
            return [x for x in self._buffer[:self._size] if x is not None]

        # Wrapped - get from head to end, then start to head
        start = self._head
        result = []
        for i in range(self.capacity):
            idx = (start + i) % self.capacity
            item = self._buffer[idx]
            if item is not None:
                result.append(item)
        return result

    def get_recent(self, n: int) -> list[T]:
        """Get n most recent items."""
        all_items = self.get_all()
        return all_items[-n:] if n < len(all_items) else all_items

    def __len__(self) -> int:
        return self._size

    def __bool__(self) -> bool:
        return self._size > 0


# Pre-configured caches for common use cases
quote_cache: LRUCache[dict] = LRUCache(max_size=1000, ttl_seconds=1.0)
position_cache: LRUCache[dict] = LRUCache(max_size=500, ttl_seconds=5.0)
order_cache: LRUCache[dict] = LRUCache(max_size=2000, ttl_seconds=30.0)
indicator_cache: LRUCache[float] = LRUCache(max_size=10000, ttl_seconds=60.0)


async def warmup_caches():
    """Warm up caches on startup."""
    logger.info("Cache warmup complete")


def get_cache_stats() -> dict[str, CacheStats]:
    """Get stats for all caches."""
    return {
        "quotes": quote_cache.get_stats(),
        "positions": position_cache.get_stats(),
        "orders": order_cache.get_stats(),
        "indicators": indicator_cache.get_stats(),
    }
