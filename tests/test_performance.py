"""
Tests for Performance Optimization Infrastructure.

Tests cover:
- LRU cache operations and eviction
- Cache decorator functionality
- Batch processor operations
- Ring buffer data structure
- Async task optimization
"""

import asyncio
from datetime import datetime, timedelta, UTC

import pytest

from backend.infra.performance import (
    AsyncTaskOptimizer,
    BatchProcessor,
    CacheEntry,
    CacheStats,
    ConnectionPoolMonitor,
    LRUCache,
    PoolMetrics,
    RingBuffer,
    cached,
    get_cache_stats,
    indicator_cache,
    order_cache,
    position_cache,
    quote_cache,
)


class TestLRUCache:
    """Tests for LRU cache."""
    
    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Test basic set and get operations."""
        cache: LRUCache[str] = LRUCache(max_size=100)
        
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        
        assert result == "value1"
    
    @pytest.mark.asyncio
    async def test_get_missing_key(self):
        """Test getting a missing key returns None."""
        cache: LRUCache[str] = LRUCache()
        
        result = await cache.get("nonexistent")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache: LRUCache[str] = LRUCache(ttl_seconds=0.1)
        
        await cache.set("key1", "value1")
        
        # Should exist immediately
        assert await cache.get("key1") == "value1"
        
        # Wait for expiration
        await asyncio.sleep(0.15)
        
        # Should be expired
        assert await cache.get("key1") is None
    
    @pytest.mark.asyncio
    async def test_max_size_eviction(self):
        """Test LRU eviction when max size exceeded."""
        cache: LRUCache[int] = LRUCache(max_size=3, ttl_seconds=None)
        
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.set("c", 3)
        await cache.set("d", 4)  # Should evict "a"
        
        assert await cache.get("a") is None
        assert await cache.get("b") == 2
        assert await cache.get("c") == 3
        assert await cache.get("d") == 4
    
    @pytest.mark.asyncio
    async def test_lru_access_updates_order(self):
        """Test that accessing an entry moves it to end."""
        cache: LRUCache[int] = LRUCache(max_size=3, ttl_seconds=None)
        
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.set("c", 3)
        
        # Access "a" - should move to end
        await cache.get("a")
        
        # Add "d" - should evict "b" (now oldest)
        await cache.set("d", 4)
        
        assert await cache.get("a") == 1
        assert await cache.get("b") is None
        assert await cache.get("c") == 3
        assert await cache.get("d") == 4
    
    @pytest.mark.asyncio
    async def test_delete(self):
        """Test deleting a key."""
        cache: LRUCache[str] = LRUCache()
        
        await cache.set("key1", "value1")
        assert await cache.delete("key1")
        assert await cache.get("key1") is None
    
    @pytest.mark.asyncio
    async def test_delete_missing_key(self):
        """Test deleting a missing key returns False."""
        cache: LRUCache[str] = LRUCache()
        
        assert not await cache.delete("nonexistent")
    
    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing the cache."""
        cache: LRUCache[int] = LRUCache()
        
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.clear()
        
        assert await cache.get("a") is None
        assert await cache.get("b") is None
    
    @pytest.mark.asyncio
    async def test_stats(self):
        """Test cache statistics."""
        cache: LRUCache[str] = LRUCache(max_size=100)
        
        await cache.set("key1", "value1")
        await cache.get("key1")  # Hit
        await cache.get("key1")  # Hit
        await cache.get("missing")  # Miss
        
        stats = cache.get_stats()
        
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.total_items == 1
        assert stats.hit_rate == 2/3
    
    def test_sync_operations(self):
        """Test synchronous get/set operations."""
        cache: LRUCache[str] = LRUCache()
        
        cache.set_sync("key1", "value1")
        result = cache.get_sync("key1")
        
        assert result == "value1"


class TestCacheDecorator:
    """Tests for @cached decorator."""
    
    @pytest.mark.asyncio
    async def test_cached_function(self):
        """Test that function results are cached."""
        call_count = 0
        
        @cached(ttl_seconds=60)
        async def expensive_fn(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2
        
        # First call
        result1 = await expensive_fn(5)
        assert result1 == 10
        assert call_count == 1
        
        # Second call - should use cache
        result2 = await expensive_fn(5)
        assert result2 == 10
        assert call_count == 1  # Not called again
    
    @pytest.mark.asyncio
    async def test_cached_different_args(self):
        """Test that different args create different cache entries."""
        @cached(ttl_seconds=60)
        async def add(a: int, b: int) -> int:
            return a + b
        
        result1 = await add(1, 2)
        result2 = await add(3, 4)
        
        assert result1 == 3
        assert result2 == 7
    
    @pytest.mark.asyncio
    async def test_cached_expiration(self):
        """Test that cached results expire."""
        call_count = 0
        
        @cached(ttl_seconds=0.1)
        async def get_time() -> float:
            nonlocal call_count
            call_count += 1
            return call_count
        
        result1 = await get_time()
        assert result1 == 1
        
        await asyncio.sleep(0.15)
        
        result2 = await get_time()
        assert result2 == 2  # Called again after expiration


class TestBatchProcessor:
    """Tests for batch processor."""
    
    @pytest.mark.asyncio
    async def test_batch_processing(self):
        """Test that items are batched correctly."""
        processed_batches = []
        
        async def process(items):
            processed_batches.append(items.copy())
        
        processor = BatchProcessor(
            process_fn=process,
            batch_size=3,
            max_wait_ms=1000,
        )
        
        # Add items
        await processor.add(1)
        await processor.add(2)
        await processor.add(3)  # Should trigger batch
        
        # Wait for processing
        await asyncio.sleep(0.1)
        
        assert len(processed_batches) == 1
        assert processed_batches[0] == [1, 2, 3]
    
    @pytest.mark.asyncio
    async def test_flush(self):
        """Test manual flush."""
        processed = []
        
        processor = BatchProcessor(
            process_fn=lambda items: processed.extend(items),
            batch_size=100,
            max_wait_ms=1000,
        )
        
        await processor.add(1)
        await processor.add(2)
        
        # Not yet processed
        assert len(processed) == 0
        
        # Manual flush
        await processor.flush()
        
        assert processed == [1, 2]
    
    @pytest.mark.asyncio
    async def test_delayed_flush(self):
        """Test automatic delayed flush."""
        processed = []
        
        processor = BatchProcessor(
            process_fn=lambda items: processed.extend(items),
            batch_size=100,
            max_wait_ms=50,
        )
        
        await processor.add(1)
        
        # Wait for delayed flush
        await asyncio.sleep(0.1)
        
        assert processed == [1]
    
    @pytest.mark.asyncio
    async def test_stats(self):
        """Test batch processor statistics."""
        processor = BatchProcessor(
            process_fn=lambda items: None,
            batch_size=2,
        )
        
        await processor.add(1)
        await processor.add(2)  # Triggers batch
        await asyncio.sleep(0.05)
        await processor.add(3)
        await processor.flush()
        
        assert processor.batches_processed == 2
        assert processor.items_processed == 3


class TestRingBuffer:
    """Tests for ring buffer."""
    
    def test_append_and_get_all(self):
        """Test appending items and getting all."""
        buffer: RingBuffer[int] = RingBuffer(capacity=5)
        
        buffer.append(1)
        buffer.append(2)
        buffer.append(3)
        
        assert buffer.get_all() == [1, 2, 3]
    
    def test_overflow_wrapping(self):
        """Test that buffer wraps correctly on overflow."""
        buffer: RingBuffer[int] = RingBuffer(capacity=3)
        
        buffer.append(1)
        buffer.append(2)
        buffer.append(3)
        buffer.append(4)  # Overwrites 1
        buffer.append(5)  # Overwrites 2
        
        assert buffer.get_all() == [3, 4, 5]
    
    def test_get_recent(self):
        """Test getting recent items."""
        buffer: RingBuffer[int] = RingBuffer(capacity=10)
        
        for i in range(7):
            buffer.append(i)
        
        recent = buffer.get_recent(3)
        assert recent == [4, 5, 6]
    
    def test_len(self):
        """Test length tracking."""
        buffer: RingBuffer[int] = RingBuffer(capacity=5)
        
        assert len(buffer) == 0
        
        buffer.append(1)
        buffer.append(2)
        
        assert len(buffer) == 2
        
        # Overflow
        for i in range(10):
            buffer.append(i)
        
        assert len(buffer) == 5  # Capped at capacity
    
    def test_bool(self):
        """Test boolean evaluation."""
        buffer: RingBuffer[int] = RingBuffer(capacity=5)
        
        assert not buffer
        
        buffer.append(1)
        
        assert buffer


class TestAsyncTaskOptimizer:
    """Tests for async task optimizer."""
    
    @pytest.mark.asyncio
    async def test_gather_with_limit(self):
        """Test concurrent execution with limit."""
        optimizer = AsyncTaskOptimizer(max_concurrency=2)
        
        results = []
        
        async def task(n):
            await asyncio.sleep(0.01)
            return n * 2
        
        tasks = [lambda n=n: task(n) for n in range(5)]
        results = await optimizer.gather_with_limit(tasks)
        
        assert results == [0, 2, 4, 6, 8]
    
    @pytest.mark.asyncio
    async def test_concurrency_limit_enforced(self):
        """Test that concurrency limit is enforced."""
        optimizer = AsyncTaskOptimizer(max_concurrency=2)
        
        concurrent_count = 0
        max_concurrent = 0
        
        async def task():
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.05)
            concurrent_count -= 1
            return True
        
        tasks = [task for _ in range(5)]
        await optimizer.gather_with_limit(tasks)
        
        assert max_concurrent <= 2
    
    @pytest.mark.asyncio
    async def test_timeout(self):
        """Test timeout handling."""
        optimizer = AsyncTaskOptimizer(max_concurrency=2)
        
        async def slow_task():
            await asyncio.sleep(10)
            return True
        
        with pytest.raises(TimeoutError):
            await optimizer.gather_with_limit([slow_task], timeout_seconds=0.1)
    
    @pytest.mark.asyncio
    async def test_map_async(self):
        """Test map_async functionality."""
        optimizer = AsyncTaskOptimizer(max_concurrency=3)
        
        async def double(x):
            return x * 2
        
        results = await optimizer.map_async(double, [1, 2, 3, 4, 5])
        
        assert results == [2, 4, 6, 8, 10]


class TestConnectionPoolMonitor:
    """Tests for connection pool monitor."""
    
    def test_record_acquisition(self):
        """Test recording acquisitions."""
        mock_pool = type("MockPool", (), {"size": 10, "checkedout": 3})()
        monitor = ConnectionPoolMonitor(mock_pool)
        
        monitor.record_acquisition(5.5)
        monitor.record_acquisition(3.2)
        
        assert monitor._total_acquisitions == 2
    
    def test_record_release(self):
        """Test recording releases."""
        mock_pool = type("MockPool", (), {"size": 10, "checkedout": 3})()
        monitor = ConnectionPoolMonitor(mock_pool)
        
        monitor.record_release()
        monitor.record_release()
        
        assert monitor._total_releases == 2
    
    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Test getting pool metrics."""
        mock_pool = type("MockPool", (), {"size": 10, "checkedout": 3})()
        monitor = ConnectionPoolMonitor(mock_pool)
        
        monitor.record_acquisition(5.0)
        monitor.record_acquisition(10.0)
        
        metrics = await monitor.get_metrics()
        
        assert isinstance(metrics, PoolMetrics)
        assert metrics.pool_size == 10
        assert metrics.avg_wait_time_ms == 7.5
        assert metrics.max_wait_time_ms == 10.0
    
    def test_near_exhaustion(self):
        """Test exhaustion detection."""
        mock_pool = type("MockPool", (), {"size": 10, "checkedout": 9})()
        monitor = ConnectionPoolMonitor(mock_pool, exhaustion_threshold=0.8)
        
        assert monitor.is_near_exhaustion()
        
        mock_pool.checkedout = 5
        assert not monitor.is_near_exhaustion()


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""
    
    def test_cache_entry_creation(self):
        """Test creating a cache entry."""
        entry = CacheEntry(
            value="test",
            created_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        
        assert entry.value == "test"
        assert entry.access_count == 0


class TestCacheStats:
    """Tests for CacheStats dataclass."""
    
    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats(hits=75, misses=25)
        
        assert stats.hit_rate == 0.75
    
    def test_hit_rate_zero_total(self):
        """Test hit rate with no requests."""
        stats = CacheStats(hits=0, misses=0)
        
        assert stats.hit_rate == 0.0


class TestPreConfiguredCaches:
    """Tests for pre-configured cache instances."""
    
    def test_quote_cache_exists(self):
        """Test quote cache is configured."""
        assert quote_cache is not None
        assert quote_cache.ttl_seconds == 1.0
    
    def test_position_cache_exists(self):
        """Test position cache is configured."""
        assert position_cache is not None
        assert position_cache.ttl_seconds == 5.0
    
    def test_order_cache_exists(self):
        """Test order cache is configured."""
        assert order_cache is not None
        assert order_cache.ttl_seconds == 30.0
    
    def test_get_cache_stats(self):
        """Test getting all cache stats."""
        stats = get_cache_stats()
        
        assert "quotes" in stats
        assert "positions" in stats
        assert "orders" in stats
        assert "indicators" in stats
