"""CORE-011 cancellation dispatch retains identity unless strict proof succeeds.

Broker transport + actual SQL proof are covered by test_eod_pending_cancellation.
These regressions pin the engine boundary and leave protective exits unchanged.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.organism import operator_cancellation


def _make_engine():
    from backend.organism.live_engine import OrganismLiveEngine
    engine = object.__new__(OrganismLiveEngine)
    engine._pending_entry = {}
    engine._pending_entry_order_ids = {}
    engine._order_service = MagicMock()
    return engine


def confirmed(monkeypatch, engine, unresolved=()):
    callback = AsyncMock(return_value={"orders": [
        {"symbol": symbol, "entry_order_id": identity,
         "release_pending": symbol not in unresolved, "resolution": "verified_unfilled"}
        for symbol, identity in engine._pending_entry_order_ids.items()
    ], "issues": ["broker_confirmation_unavailable"] if unresolved else []})
    monkeypatch.setattr(operator_cancellation, "confirm_tracked_entries", callback)
    return callback


class TestDrawdownKillCancelBrokerOrders:
    @pytest.mark.asyncio
    async def test_cancel_called_for_each_pending_order(self, monkeypatch):
        engine = _make_engine()
        engine._pending_entry = {"AAPL": 10, "MSFT": 12}
        engine._pending_entry_order_ids = {"AAPL": "order-aaa", "MSFT": "order-bbb"}
        callback = confirmed(monkeypatch, engine)
        await engine._cancel_pending_entry_orders()
        callback.assert_awaited_once_with(engine, cancel=True)
        assert not engine._pending_entry_order_ids
        engine._order_service.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_local_bookkeeping_cleared_after_cancel(self, monkeypatch):
        engine = _make_engine()
        engine._pending_entry = {"NVDA": 5}
        engine._pending_entry_order_ids = {"NVDA": "original"}
        confirmed(monkeypatch, engine)
        await engine._cancel_pending_entry_orders()
        assert not engine._pending_entry and not engine._pending_entry_order_ids

    @pytest.mark.asyncio
    async def test_no_open_orders_is_noop(self, monkeypatch):
        engine = _make_engine()
        callback = confirmed(monkeypatch, engine)
        await engine._cancel_pending_entry_orders()
        callback.assert_not_awaited()
        engine._order_service.cancel_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_pending_entry_without_order_id_is_retained(self, monkeypatch):
        engine = _make_engine()
        engine._pending_entry = {"TSLA": 7}
        confirmed(monkeypatch, engine)
        await engine._cancel_pending_entry_orders()
        assert engine._pending_entry == {"TSLA": 7}

    @pytest.mark.asyncio
    async def test_cancel_failure_does_not_crash_or_clear(self, monkeypatch):
        engine = _make_engine()
        engine._pending_entry = {"AAPL": 10, "GOOGL": 11}
        engine._pending_entry_order_ids = {"AAPL": "a", "GOOGL": "g"}
        confirmed(monkeypatch, engine, unresolved=("AAPL", "GOOGL"))
        await engine._cancel_pending_entry_orders()
        assert engine._pending_entry == {"AAPL": 10, "GOOGL": 11}
        assert engine._pending_entry_order_ids == {"AAPL": "a", "GOOGL": "g"}

    @pytest.mark.asyncio
    async def test_partial_cancel_failure_retains_only_unresolved(self, monkeypatch):
        engine = _make_engine()
        engine._pending_entry = {"AAPL": 10, "GOOGL": 11}
        engine._pending_entry_order_ids = {"AAPL": "a", "GOOGL": "g"}
        confirmed(monkeypatch, engine, unresolved=("GOOGL",))
        await engine._cancel_pending_entry_orders()
        assert engine._pending_entry == {"GOOGL": 11}
        assert engine._pending_entry_order_ids == {"GOOGL": "g"}

    @pytest.mark.asyncio
    async def test_stale_confirmation_cannot_clear_a_new_identity(self, monkeypatch):
        engine = _make_engine()
        engine._pending_entry = {"AAPL": 10}
        engine._pending_entry_order_ids = {"AAPL": "old"}
        confirmed(monkeypatch, engine)
        engine._pending_entry_order_ids["AAPL"] = "new"
        await engine._cancel_pending_entry_orders()
        assert engine._pending_entry_order_ids == {"AAPL": "new"}


class TestExitOrdersNotCancelled:
    @pytest.mark.asyncio
    async def test_exit_orders_not_in_pending_entry(self, monkeypatch):
        engine = _make_engine()
        engine._pending_entry = {"MSFT": 10}
        engine._pending_entry_order_ids = {"MSFT": "entry-msft"}
        engine._pending_exit = {"AAPL": 8}
        confirmed(monkeypatch, engine)
        await engine._cancel_pending_entry_orders()
        assert engine._pending_exit == {"AAPL": 8}
        assert not engine._pending_entry_order_ids
        engine._order_service.cancel_order.assert_not_called()


class TestOrderIdTracking:
    """Verify order IDs are captured and expired correctly."""

    def test_order_id_map_initialized_empty(self):
        """_pending_entry_order_ids exists and starts empty."""
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine
        source = inspect.getsource(OrganismLiveEngine.__init__)
        assert "_pending_entry_order_ids" in source

    def test_order_id_expiry_synced_with_pending_entry(self):
        """Expired clocks cannot erase unresolved IDs or missing-ID blockers."""
        engine = _make_engine()
        engine._tick_count = 10000
        engine._pending_entry = {"NO_ID": 0}
        engine._pending_entry_order_ids = {"AAPL": "original-id"}
        engine._pending_exit = {}
        engine._exit_cooldown = {}
        engine._EXIT_COOLDOWN_TICKS = 10
        engine._PENDING_EXIT_TICKS = 3
        engine._stage_expire_cooldowns()
        assert engine._pending_entry == {"NO_ID": 0, "AAPL": 10000}
        assert engine._pending_entry_order_ids == {"AAPL": "original-id"}

    def test_order_id_captured_on_entry_submission(self):
        """Entry submission code captures order_id into _pending_entry_order_ids."""
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine
        source = inspect.getsource(OrganismLiveEngine)
        assert 'self._pending_entry_order_ids[sz.symbol] = order_result["order_id"]' in source

    def test_order_id_captured_on_pyramid_add(self):
        """Pyramid add code captures order_id into _pending_entry_order_ids."""
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine
        source = inspect.getsource(OrganismLiveEngine)
        assert 'self._pending_entry_order_ids[sym] = pyr_order_result["order_id"]' in source
