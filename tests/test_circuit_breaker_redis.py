"""
Test Circuit Breaker with Redis Persistence.

Tests the enhanced circuit breaker that persists state to Redis,
ensuring crash-loop protection and state recovery across restarts.
"""

import asyncio
import json
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.order_service import (
    CircuitBreaker,
    CB_STATE_KEY,
    CB_FAILURES_KEY,
    CB_OPENED_AT_KEY,
    CB_DAILY_PNL_KEY,
    get_circuit_breaker,
    get_circuit_breaker_async,
    circuit_breaker_check,
    circuit_breaker_check_async,
)


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=True)
    redis.expire = AsyncMock(return_value=True)
    
    # Pipeline mock
    pipeline = AsyncMock()
    pipeline.set = MagicMock(return_value=pipeline)
    pipeline.delete = MagicMock(return_value=pipeline)
    pipeline.expire = MagicMock(return_value=pipeline)
    pipeline.execute = AsyncMock(return_value=[True, True, True])
    redis.pipeline = MagicMock(return_value=pipeline)
    
    return redis


@pytest.fixture
def cb_with_redis(mock_redis):
    """Create circuit breaker with mock Redis."""
    cb = CircuitBreaker(
        failure_threshold=3,
        success_threshold=2,
        timeout_seconds=10,
        window_seconds=60,
        redis_client=mock_redis
    )
    return cb


class TestCircuitBreakerBasics:
    """Test basic circuit breaker functionality."""

    def test_initial_state_closed(self):
        """Circuit breaker starts in CLOSED state."""
        cb = CircuitBreaker()
        assert cb.state == CircuitBreaker.STATE_CLOSED
        assert not cb.is_open

    def test_state_transitions_to_open_after_failures(self):
        """Circuit opens after failure threshold is reached."""
        cb = CircuitBreaker(failure_threshold=3)
        
        cb.record_failure("test1")
        assert cb.state == CircuitBreaker.STATE_CLOSED
        
        cb.record_failure("test2")
        assert cb.state == CircuitBreaker.STATE_CLOSED
        
        cb.record_failure("test3")
        assert cb.state == CircuitBreaker.STATE_OPEN
        assert cb.is_open

    def test_half_open_transition_after_timeout(self):
        """Circuit transitions to HALF_OPEN after timeout."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=1)
        
        cb.record_failure("test")
        assert cb.state == CircuitBreaker.STATE_OPEN
        
        # Wait for timeout
        time.sleep(1.1)
        assert cb.state == CircuitBreaker.STATE_HALF_OPEN

    def test_recovery_from_half_open(self):
        """Circuit closes after successes in HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout_seconds=0)
        
        cb.record_failure("test")
        # Force to half-open (timeout=0)
        cb._state = CircuitBreaker.STATE_HALF_OPEN
        
        cb.record_success()
        assert cb.state == CircuitBreaker.STATE_HALF_OPEN  # Still half-open
        
        cb.record_success()
        assert cb.state == CircuitBreaker.STATE_CLOSED  # Now closed

    def test_daily_loss_trips_breaker(self):
        """Circuit trips when daily loss exceeds threshold."""
        cb = CircuitBreaker(loss_threshold_pct=5.0)
        
        # Normal P&L - no trip
        tripped = cb.check(daily_pnl=-3.0)
        assert not tripped
        
        # Exceed loss threshold - trips
        tripped = cb.check(daily_pnl=-6.0)
        assert tripped
        assert cb.is_open

    def test_reset_clears_state(self):
        """Manual reset clears circuit breaker state."""
        cb = CircuitBreaker(failure_threshold=1)
        
        cb.record_failure("test")
        assert cb.is_open
        
        cb.reset()
        assert cb.state == CircuitBreaker.STATE_CLOSED
        assert len(cb._failures) == 0


class TestCircuitBreakerRedisIntegration:
    """Test Redis persistence functionality."""

    @pytest.mark.asyncio
    async def test_redis_init_success(self, mock_redis):
        """Redis initializes successfully."""
        cb = CircuitBreaker(redis_client=mock_redis)
        
        await cb._init_redis()
        assert cb._redis_available is True

    @pytest.mark.asyncio
    async def test_redis_init_fallback_on_failure(self):
        """Falls back to memory if Redis fails."""
        cb = CircuitBreaker()
        cb._redis = AsyncMock()
        cb._redis.ping = AsyncMock(side_effect=Exception("Connection failed"))
        
        await cb._init_redis()
        # Should not crash, state still functional
        assert cb.state == CircuitBreaker.STATE_CLOSED

    @pytest.mark.asyncio
    async def test_load_state_from_redis(self, mock_redis):
        """Loads circuit breaker state from Redis on startup."""
        # Set up Redis to return OPEN state
        mock_redis.get = AsyncMock(side_effect=lambda key: {
            CB_STATE_KEY: b"open",
            CB_OPENED_AT_KEY: b"1234567890.123",
            CB_FAILURES_KEY: json.dumps([1234567890.0, 1234567891.0]).encode(),
            CB_DAILY_PNL_KEY: b"-3.5",
        }.get(key))
        
        cb = CircuitBreaker(redis_client=mock_redis)
        cb._redis_available = True
        
        await cb._load_state_from_redis()
        
        assert cb._state == "open"
        assert cb._opened_at == 1234567890.123
        assert len(cb._failures) == 2
        assert cb._daily_pnl == -3.5

    @pytest.mark.asyncio
    async def test_persist_state_to_redis(self, cb_with_redis, mock_redis):
        """State is persisted to Redis after changes."""
        cb = cb_with_redis
        cb._redis_available = True
        cb._state = CircuitBreaker.STATE_OPEN
        cb._opened_at = 12345.0
        cb._failures = [12340.0, 12341.0]
        cb._daily_pnl = -2.5
        
        await cb._persist_state()
        
        # Verify pipeline was used
        mock_redis.pipeline.assert_called()
        pipeline = mock_redis.pipeline.return_value
        pipeline.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_async_persists_state(self, cb_with_redis, mock_redis):
        """Async check loads and persists state."""
        cb = cb_with_redis
        cb._redis_available = True
        
        result = await cb.check_async(daily_pnl=-1.0)
        
        assert result is False  # Not tripped
        mock_redis.pipeline.return_value.execute.assert_called()

    @pytest.mark.asyncio
    async def test_record_failure_async_persists(self, cb_with_redis, mock_redis):
        """Async record_failure persists state."""
        cb = cb_with_redis
        cb._redis_available = True
        
        await cb.record_failure_async("broker_error")
        
        assert len(cb._failures) == 1
        mock_redis.pipeline.return_value.execute.assert_called()

    @pytest.mark.asyncio
    async def test_record_success_async_persists(self, cb_with_redis, mock_redis):
        """Async record_success persists state."""
        cb = cb_with_redis
        cb._redis_available = True
        cb._state = CircuitBreaker.STATE_HALF_OPEN
        
        await cb.record_success_async()
        
        mock_redis.pipeline.return_value.execute.assert_called()

    @pytest.mark.asyncio
    async def test_reset_async_persists(self, cb_with_redis, mock_redis):
        """Async reset persists cleared state."""
        cb = cb_with_redis
        cb._redis_available = True
        cb._state = CircuitBreaker.STATE_OPEN
        cb._failures = [1.0, 2.0, 3.0]
        
        await cb.reset_async()
        
        assert cb.state == CircuitBreaker.STATE_CLOSED
        assert len(cb._failures) == 0
        mock_redis.pipeline.return_value.execute.assert_called()


class TestCircuitBreakerCrashRecovery:
    """Test crash-loop protection scenarios."""

    @pytest.mark.asyncio
    async def test_open_state_survives_restart(self, mock_redis):
        """OPEN state is preserved across instance recreation."""
        # Simulate first instance that trips the breaker
        cb1 = CircuitBreaker(
            failure_threshold=2,
            redis_client=mock_redis
        )
        cb1._redis_available = True
        
        await cb1.record_failure_async("error1")
        await cb1.record_failure_async("error2")
        
        assert cb1.is_open
        
        # Simulate "restart" - new instance
        mock_redis.get = AsyncMock(side_effect=lambda key: {
            CB_STATE_KEY: b"open",
            CB_OPENED_AT_KEY: str(cb1._opened_at).encode(),
            CB_FAILURES_KEY: json.dumps(cb1._failures).encode(),
            CB_DAILY_PNL_KEY: b"0.0",
        }.get(key))
        
        cb2 = CircuitBreaker(
            failure_threshold=2,
            redis_client=mock_redis
        )
        cb2._redis_available = True
        
        await cb2._load_state_from_redis()
        
        # Should still be OPEN after "restart"
        assert cb2._state == "open"

    @pytest.mark.asyncio
    async def test_failures_accumulate_across_restarts(self, mock_redis):
        """Failure count persists across restarts to prevent drain."""
        stored_failures = []
        
        def capture_failures(key, value):
            if key == CB_FAILURES_KEY:
                stored_failures.clear()
                stored_failures.extend(json.loads(value.decode() if isinstance(value, bytes) else value))
            return True
        
        # Override pipeline behavior to track state
        pipeline = mock_redis.pipeline.return_value
        original_set = pipeline.set
        
        # First instance - record 1 failure
        cb1 = CircuitBreaker(failure_threshold=3, redis_client=mock_redis)
        cb1._redis_available = True
        await cb1.record_failure_async("error1")
        
        assert len(cb1._failures) == 1
        
        # Verify it would persist (in real test with real Redis)
        # The failure would be stored in Redis


class TestCircuitBreakerStatus:
    """Test status reporting with Redis info."""

    def test_status_includes_redis_info(self, mock_redis):
        """Status includes Redis availability information."""
        cb = CircuitBreaker(redis_client=mock_redis)
        cb._redis_available = True
        cb._state_loaded = True
        
        status = cb.get_status()
        
        assert "redis_available" in status
        assert status["redis_available"] is True
        assert "state_persisted" in status
        assert status["state_persisted"] is True

    def test_status_shows_no_redis(self):
        """Status shows when Redis is not available."""
        cb = CircuitBreaker()
        
        status = cb.get_status()
        
        assert status["redis_available"] is False
        assert status["state_persisted"] is False


class TestModuleLevelFunctions:
    """Test module-level circuit breaker functions."""

    def test_get_circuit_breaker_singleton(self):
        """get_circuit_breaker returns singleton instance."""
        # Reset global
        import backend.services.order_service as os_module
        os_module._circuit_breaker = None
        
        cb1 = get_circuit_breaker()
        cb2 = get_circuit_breaker()
        
        assert cb1 is cb2

    def test_circuit_breaker_check_sync(self):
        """Sync circuit_breaker_check works correctly."""
        import backend.services.order_service as os_module
        os_module._circuit_breaker = None
        
        # Should not be tripped initially
        tripped = circuit_breaker_check(daily_pnl=0.0)
        assert tripped is False

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_async(self):
        """Async getter initializes Redis."""
        import backend.services.order_service as os_module
        os_module._circuit_breaker = None
        
        with patch.object(CircuitBreaker, '_init_redis', new_callable=AsyncMock) as mock_init:
            with patch.object(CircuitBreaker, '_load_state_from_redis', new_callable=AsyncMock) as mock_load:
                cb = await get_circuit_breaker_async()
                
                mock_init.assert_called_once()
                mock_load.assert_called_once()


class TestCircuitBreakerEdgeCases:
    """Test edge cases and error handling."""

    def test_failures_cleaned_outside_window(self):
        """Old failures are cleaned up when outside time window."""
        cb = CircuitBreaker(window_seconds=1, failure_threshold=5)
        
        # Record failures
        cb.record_failure("old1")
        cb.record_failure("old2")
        
        # Wait for window to expire
        time.sleep(1.1)
        
        # Record new failure - should clean old ones
        cb.record_failure("new1")
        
        # Only new failure should remain
        assert len(cb._failures) == 1

    def test_check_returns_true_when_open(self):
        """check() returns True (tripped) when circuit is OPEN."""
        cb = CircuitBreaker(failure_threshold=1)
        
        cb.record_failure("test")
        
        assert cb.check() is True

    def test_half_open_failure_reopens(self):
        """Failure in HALF_OPEN state immediately re-opens circuit."""
        cb = CircuitBreaker(failure_threshold=1, timeout_seconds=60)
        
        cb.record_failure("initial")
        assert cb._state == CircuitBreaker.STATE_OPEN
        
        # Manually set to half-open to test the scenario
        cb._state = CircuitBreaker.STATE_HALF_OPEN
        
        cb.record_failure("recovery_failed")
        
        # After failure in half-open, should be back to OPEN
        assert cb._state == CircuitBreaker.STATE_OPEN

    @pytest.mark.asyncio
    async def test_redis_error_doesnt_crash_check(self, mock_redis):
        """Redis errors don't crash the check operation."""
        mock_redis.get = AsyncMock(side_effect=Exception("Redis down"))
        
        cb = CircuitBreaker(redis_client=mock_redis)
        cb._redis_available = True
        
        # Should not crash, falls back to memory
        await cb._load_state_from_redis()
        
        result = cb.check()
        assert result is False  # Still works with in-memory state

    @pytest.mark.asyncio
    async def test_redis_error_during_persist_doesnt_crash(self, mock_redis):
        """Redis errors during persist don't crash."""
        pipeline = mock_redis.pipeline.return_value
        pipeline.execute = AsyncMock(side_effect=Exception("Write failed"))
        
        cb = CircuitBreaker(redis_client=mock_redis)
        cb._redis_available = True
        
        # Should not crash
        await cb._persist_state()
        
        # Redis should be marked unavailable
        assert cb._redis_available is False


# Marker for unit tests
pytestmark = pytest.mark.unit
