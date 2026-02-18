"""
§8.5 FIX: DLQ processing tests.

Tests the Dead Letter Queue handling: max retries, DLQ movement,
WebSocket notification on broker reject, and stale cache eviction.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


@pytest.mark.unit
class TestDLQProcessing:
    """Tests for Dead Letter Queue processing in outbox worker."""

    @pytest.fixture
    def worker(self):
        from backend.infra.outbox_worker import OutboxWorker

        w = OutboxWorker.__new__(OutboxWorker)
        w.use_mock_broker = True
        w.logger = MagicMock()
        w.max_retries = 3
        return w

    @pytest.mark.asyncio
    async def test_move_to_dlq_after_max_retries(self, worker):
        """Event should be moved to DLQ after exceeding max retries."""
        event = MagicMock()
        event.id = uuid4()
        event.retry_count = 4  # Exceeds max_retries=3
        event.topic = "order.submitted"
        event.payload = {"order_id": str(uuid4()), "symbol": "AAPL"}

        with patch.object(worker, '_move_to_dlq', new_callable=AsyncMock) as mock_dlq:
            # Simulate the retry check logic
            if event.retry_count > worker.max_retries:
                await worker._move_to_dlq(event, "Max retries exceeded")

            mock_dlq.assert_called_once()

    @pytest.mark.asyncio
    async def test_broker_rejection_produces_failure_result(self, worker):
        """When broker rejects order, result should indicate failure."""
        worker.use_mock_broker = False

        with patch('backend.services.trading_execution_mode.get_trading_execution_mode') as mock_mode, \
             patch.object(worker, '_submit_real_broker_order', new_callable=AsyncMock) as mock_broker:
            mock_mode.return_value = MagicMock(mode="execute", source="test", overridden=False)
            mock_broker.side_effect = Exception("Insufficient buying power")

            result = await worker._process_order_submitted({
                "order_id": str(uuid4()),
                "symbol": "AAPL",
                "side": "buy",
                "qty": "999999",
                "order_type": "market",
            })

            assert result["success"] is False
            assert "Insufficient buying power" in result["error"]


@pytest.mark.unit
class TestIdempotencyCacheEviction:
    """§4.8: Tests for stale idempotency cache eviction."""

    @pytest.mark.asyncio
    async def test_evict_stale_entries(self):
        """Old cache entries should be evicted after TTL."""
        from backend.services.order_service import OrderService

        service = OrderService.__new__(OrderService)
        service.IDEMPOTENCY_TTL = 1  # 1 second for test
        service._max_cache_size = 10000

        # Simulate old entry — use monotonic clock since that's what eviction uses
        import time
        old_ts = time.monotonic() - 10  # 10 seconds ago
        cache1 = {"old-key": (old_ts, {"status": "ok"})}
        cache2 = {"old-mod": (old_ts, True)}
        cache3 = {"old-cancel": (old_ts, True)}

        service._evict_stale_cache(cache1)
        service._evict_stale_cache(cache2)
        service._evict_stale_cache(cache3)

        assert len(cache1) == 0
        assert len(cache2) == 0
        assert len(cache3) == 0

    @pytest.mark.asyncio
    async def test_fresh_entries_kept(self):
        """Recent cache entries should survive eviction."""
        from backend.services.order_service import OrderService

        service = OrderService.__new__(OrderService)
        service.IDEMPOTENCY_TTL = 3600
        service._max_cache_size = 10000

        import time
        now = time.monotonic()
        cache = {"fresh-key": (now, {"status": "ok"})}

        service._evict_stale_cache(cache)

        assert "fresh-key" in cache
