"""
Tests for J6b — CORE-011 complete: cancel broker entry orders on drawdown kill.

Verifies that the drawdown kill switch actually cancels open organism entry
orders via the order service, not just clears local bookkeeping.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_engine():
    """Create a minimal OrganismLiveEngine for unit testing."""
    from backend.organism.live_engine import OrganismLiveEngine

    engine = object.__new__(OrganismLiveEngine)
    engine._pending_entry = {}
    engine._pending_entry_order_ids = {}
    engine._order_service = MagicMock()
    engine._order_service.cancel_order = AsyncMock(return_value={"status": "cancelled"})
    return engine


class TestDrawdownKillCancelBrokerOrders:
    """CORE-011: drawdown kill must cancel open entry orders at the broker."""

    @pytest.mark.asyncio
    async def test_cancel_called_for_each_pending_order(self):
        """Each tracked order_id triggers an order service cancel call."""
        engine = _make_engine()
        engine._pending_entry = {"AAPL": 10, "MSFT": 12}
        engine._pending_entry_order_ids = {
            "AAPL": "order-aaa",
            "MSFT": "order-bbb",
        }

        await engine._cancel_pending_entry_orders()

        assert engine._order_service.cancel_order.call_count == 2
        called_ids = {
            call.args[0]
            for call in engine._order_service.cancel_order.call_args_list
        }
        assert called_ids == {"order-aaa", "order-bbb"}

    @pytest.mark.asyncio
    async def test_local_bookkeeping_cleared_after_cancel(self):
        """Both _pending_entry and _pending_entry_order_ids are emptied."""
        engine = _make_engine()
        engine._pending_entry = {"NVDA": 5}
        engine._pending_entry_order_ids = {"NVDA": "order-nnn"}

        await engine._cancel_pending_entry_orders()

        assert engine._pending_entry == {}
        assert engine._pending_entry_order_ids == {}

    @pytest.mark.asyncio
    async def test_no_open_orders_is_noop(self):
        """When no pending entries exist, nothing is cancelled."""
        engine = _make_engine()

        await engine._cancel_pending_entry_orders()

        engine._order_service.cancel_order.assert_not_called()
        assert engine._pending_entry == {}
        assert engine._pending_entry_order_ids == {}

    @pytest.mark.asyncio
    async def test_pending_entry_without_order_id_still_cleared(self):
        """Entries in _pending_entry but not in _pending_entry_order_ids
        (e.g. order submission returned no ID) are still cleared."""
        engine = _make_engine()
        engine._pending_entry = {"TSLA": 7}
        # No order ID tracked for TSLA

        await engine._cancel_pending_entry_orders()

        engine._order_service.cancel_order.assert_not_called()
        assert engine._pending_entry == {}

    @pytest.mark.asyncio
    async def test_cancel_failure_does_not_crash(self):
        """If cancel_order raises, the tick loop must not crash."""
        engine = _make_engine()
        engine._pending_entry = {"AAPL": 10, "GOOGL": 11}
        engine._pending_entry_order_ids = {
            "AAPL": "order-aaa",
            "GOOGL": "order-ggg",
        }
        engine._order_service.cancel_order = AsyncMock(
            side_effect=Exception("broker timeout")
        )

        # Must not raise
        await engine._cancel_pending_entry_orders()

        # Local bookkeeping still cleared despite failures
        assert engine._pending_entry == {}
        assert engine._pending_entry_order_ids == {}

    @pytest.mark.asyncio
    async def test_partial_cancel_failure(self):
        """One cancel succeeds, another fails — both cleared from bookkeeping."""
        engine = _make_engine()
        engine._pending_entry = {"AAPL": 10, "GOOGL": 11}
        engine._pending_entry_order_ids = {
            "AAPL": "order-aaa",
            "GOOGL": "order-ggg",
        }

        async def _side_effect(order_id):
            if order_id == "order-ggg":
                raise Exception("already filled")
            return {"status": "cancelled"}

        engine._order_service.cancel_order = AsyncMock(side_effect=_side_effect)

        await engine._cancel_pending_entry_orders()

        assert engine._pending_entry == {}
        assert engine._pending_entry_order_ids == {}
        assert engine._order_service.cancel_order.call_count == 2


class TestExitOrdersNotCancelled:
    """Exit/reduce-only orders must never be cancelled by drawdown kill."""

    @pytest.mark.asyncio
    async def test_exit_orders_not_in_pending_entry(self):
        """_pending_exit orders are not tracked in _pending_entry_order_ids
        and therefore cannot be cancelled by _cancel_pending_entry_orders."""
        engine = _make_engine()
        # Simulate: exit order pending for AAPL, entry order for MSFT
        engine._pending_entry = {"MSFT": 10}
        engine._pending_entry_order_ids = {"MSFT": "order-entry-msft"}
        # _pending_exit is a separate dict — not touched by the cancel method
        engine._pending_exit = {"AAPL": 8}

        await engine._cancel_pending_entry_orders()

        # Only MSFT entry order cancelled
        engine._order_service.cancel_order.assert_called_once_with("order-entry-msft")
        # _pending_exit untouched
        assert engine._pending_exit == {"AAPL": 8}


class TestOrderIdTracking:
    """Verify order IDs are captured and expired correctly."""

    def test_order_id_map_initialized_empty(self):
        """_pending_entry_order_ids exists and starts empty."""
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine
        source = inspect.getsource(OrganismLiveEngine.__init__)
        assert "_pending_entry_order_ids" in source

    def test_order_id_expiry_synced_with_pending_entry(self):
        """_pending_entry_order_ids cleanup is tied to _pending_entry expiry."""
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine
        source = inspect.getsource(OrganismLiveEngine)
        # The expiry code should reference both dicts
        assert "self._pending_entry_order_ids = {" in source
        assert "if sym in self._pending_entry" in source

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
