"""
Comprehensive tests for backend/integrations/alpaca_stream_production.py

Tests the RobustAlpacaStream production WebSocket client with gap-filling.
Covers: StreamState, connection, gap-filling, trade events, error handling.

Phase 3: Alpaca Integrations - Production Stream Tests
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(autouse=True)
def mock_orders_repo():
    """Auto-use fixture to patch OrdersRepo for all tests."""
    with patch("backend.integrations.alpaca_stream_production.OrdersRepo") as mock_repo:
        mock_repo.return_value = MagicMock()
        yield mock_repo


@pytest.fixture(autouse=True)
def mock_alpaca_broker_client():
    """Auto-use fixture to patch AlpacaBrokerClient for all tests."""
    with patch("backend.integrations.alpaca_stream_production.AlpacaBrokerClient") as mock_client:
        mock_client.return_value = MagicMock()
        yield mock_client


@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def sample_trade_update():
    """Sample trade update data."""
    return {
        "order": {
            "id": "broker-order-123",
            "symbol": "AAPL",
            "side": "buy",
            "qty": "100"
        },
        "event": "fill",
        "timestamp": "2025-01-15T14:30:00.000000Z",
        "qty": "100",
        "price": "150.50"
    }


@pytest.fixture
def mock_order():
    """Mock order object."""
    order = MagicMock()
    order.id = "order-123"
    order.broker_order_id = "broker-order-123"
    order.symbol = "AAPL"
    order.side = "buy"
    order.qty = 100
    order.status = "submitted"
    order.filled_qty = 0
    order.order_type = "market"
    order.submitted_at = datetime.now(UTC)
    order.attributes = {"user_id": "test_user"}
    return order


# ============================================================================
# StreamState TESTS
# ============================================================================

class TestStreamState:
    """Tests for StreamState class."""

    def test_init(self):
        """Test StreamState initialization."""
        from backend.integrations.alpaca_stream_production import StreamState
        
        state = StreamState()
        
        assert state.last_event_ts is None
        assert state.connection_count == 0
        assert state.total_messages_processed == 0
        assert state.last_heartbeat is None

    @pytest.mark.asyncio
    async def test_load_from_db_with_events(self):
        """Test loading state from database with existing events."""
        with patch("backend.integrations.alpaca_stream_production.get_db_session") as mock_db:
            from backend.integrations.alpaca_stream_production import StreamState
            
            # Mock session context manager
            mock_session = AsyncMock()
            mock_result = MagicMock()
            last_time = datetime.now(UTC)
            mock_result.scalar_one_or_none.return_value = last_time
            mock_session.execute.return_value = mock_result
            
            # Make it an async generator
            async def mock_gen():
                yield mock_session
            mock_db.return_value = mock_gen()
            
            state = StreamState()
            await state.load_from_db()
            
            assert state.last_event_ts == last_time

    @pytest.mark.asyncio
    async def test_load_from_db_no_events(self):
        """Test loading state from database with no events."""
        with patch("backend.integrations.alpaca_stream_production.get_db_session") as mock_db:
            from backend.integrations.alpaca_stream_production import StreamState
            
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_session.execute.return_value = mock_result
            
            async def mock_gen():
                yield mock_session
            mock_db.return_value = mock_gen()
            
            state = StreamState()
            await state.load_from_db()
            
            # Should default to 1 hour ago
            assert state.last_event_ts is not None
            assert (datetime.now(UTC) - state.last_event_ts).seconds < 3700  # ~1 hour

    @pytest.mark.asyncio
    async def test_update_last_event(self):
        """Test updating last event timestamp."""
        from backend.integrations.alpaca_stream_production import StreamState
        
        state = StreamState()
        state.last_event_ts = datetime(2025, 1, 1, tzinfo=UTC)
        
        new_time = datetime(2025, 1, 15, tzinfo=UTC)
        await state.update_last_event(new_time)
        
        assert state.last_event_ts == new_time
        assert state.total_messages_processed == 1

    @pytest.mark.asyncio
    async def test_update_last_event_older_ignored(self):
        """Test older event timestamps are ignored."""
        from backend.integrations.alpaca_stream_production import StreamState
        
        state = StreamState()
        current_time = datetime(2025, 1, 15, tzinfo=UTC)
        state.last_event_ts = current_time
        
        older_time = datetime(2025, 1, 1, tzinfo=UTC)
        await state.update_last_event(older_time)
        
        assert state.last_event_ts == current_time  # Not updated


# ============================================================================
# RobustAlpacaStream INITIALIZATION TESTS
# ============================================================================

class TestRobustAlpacaStreamInit:
    """Tests for RobustAlpacaStream initialization."""

    def test_init(self):
        """Test RobustAlpacaStream initialization."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(
            api_key="test_key",
            api_secret="test_secret",
            base_url="wss://stream.data.alpaca.markets/v2/iex",
            paper=True
        )
        
        assert stream.api_key == "test_key"
        assert stream.api_secret == "test_secret"
        assert stream.paper is True
        assert stream.is_running is False
        assert stream.should_stop is False

    def test_init_default_values(self):
        """Test initialization with default values."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(
            api_key="key",
            api_secret="secret"
        )
        
        assert stream.min_backoff == 1.0
        assert stream.max_backoff == 300.0
        assert stream.backoff_multiplier == 1.5
        assert stream.jitter_factor == 0.1

    def test_init_stream_state(self):
        """Test stream state is initialized."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(
            api_key="key",
            api_secret="secret"
        )
        
        assert stream.stream_state is not None
        assert stream.stream_state.connection_count == 0


# ============================================================================
# START AND STOP TESTS
# ============================================================================

class TestRobustAlpacaStreamStartStop:
    """Tests for start and stop methods."""

    @pytest.mark.asyncio
    async def test_stop(self, mock_websocket):
        """Test stopping the stream."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        stream.is_running = True
        
        await stream.stop()
        
        assert stream.should_stop is True
        assert stream.is_running is False
        mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_no_websocket(self):
        """Test stopping when no websocket."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.websocket = None
        
        # Should not raise
        await stream.stop()
        
        assert stream.should_stop is True


# ============================================================================
# CONNECTION ERROR HANDLING TESTS
# ============================================================================

class TestRobustAlpacaStreamErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_handle_connection_closed_error(self):
        """Test handling ConnectionClosed error."""
        from websockets.exceptions import ConnectionClosed
        
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.is_running = True
        stream.guardrails = MagicMock()
        stream.guardrails.record_broker_error = MagicMock()
        
        with patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            await stream._handle_connection_error(ConnectionClosed(None, None))
        
        assert stream.is_running is False

    @pytest.mark.asyncio
    async def test_handle_timeout_error(self):
        """Test handling timeout error."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.is_running = True
        stream.guardrails = MagicMock()
        stream.guardrails.record_broker_error = MagicMock()
        
        with patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            await stream._handle_connection_error(asyncio.TimeoutError())
        
        assert stream.is_running is False

    @pytest.mark.asyncio
    async def test_handle_unknown_error(self):
        """Test handling unknown error."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.is_running = True
        
        with patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            await stream._handle_connection_error(Exception("Unknown error"))
        
        assert stream.is_running is False


# ============================================================================
# GET STATUS TESTS
# ============================================================================

class TestRobustAlpacaStreamStatus:
    """Tests for get_status method."""

    def test_get_status(self):
        """Test get_status returns correct data."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.is_running = True
        stream.should_stop = False
        stream.reconnect_count = 3
        stream.current_backoff = 5.0
        stream.connect_time = datetime.now(UTC)
        stream.stream_state.connection_count = 10
        stream.stream_state.total_messages_processed = 500
        stream.stream_state.last_event_ts = datetime.now(UTC)
        stream.stream_state.last_heartbeat = datetime.now(UTC)
        
        status = stream.get_status()
        
        assert status["is_running"] is True
        assert status["should_stop"] is False
        assert status["connection_count"] == 10
        assert status["reconnect_count"] == 3
        assert status["total_messages_processed"] == 500
        assert status["current_backoff"] == 5.0
        assert status["uptime_seconds"] is not None

    def test_get_status_no_connect_time(self):
        """Test get_status when never connected."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.connect_time = None
        
        status = stream.get_status()
        
        assert status["uptime_seconds"] is None

    def test_get_status_no_timestamps(self):
        """Test get_status when no timestamps available."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.stream_state.last_event_ts = None
        stream.stream_state.last_heartbeat = None
        
        status = stream.get_status()
        
        assert status["last_event_ts"] is None
        assert status["last_heartbeat"] is None


# ============================================================================
# PROCESS MESSAGE TESTS
# ============================================================================

class TestRobustAlpacaStreamProcessMessage:
    """Tests for message processing."""

    @pytest.mark.asyncio
    async def test_process_message_trade_updates(self, sample_trade_update):
        """Test processing trade_updates message."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        with patch.object(stream, "_process_trade_update", new_callable=AsyncMock) as mock_process, \
             patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            message = json.dumps({
                "stream": "trade_updates",
                "data": sample_trade_update
            })
            
            await stream._process_message(message)
            
            mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_authorization(self):
        """Test processing authorization message."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        with patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            message = json.dumps({
                "stream": "authorization",
                "data": {"status": "authorized"}
            })
            
            # Should not raise
            await stream._process_message(message)

    @pytest.mark.asyncio
    async def test_process_message_listening(self):
        """Test processing listening confirmation."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        with patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            message = json.dumps({
                "stream": "listening",
                "data": {"streams": ["trade_updates"]}
            })
            
            # Should not raise
            await stream._process_message(message)

    @pytest.mark.asyncio
    async def test_process_message_invalid_json(self):
        """Test processing invalid JSON."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        # Should not raise
        await stream._process_message("not valid json")

    @pytest.mark.asyncio
    async def test_process_message_updates_heartbeat(self):
        """Test message processing updates heartbeat."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        with patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            message = json.dumps({"stream": "unknown", "data": {}})
            
            await stream._process_message(message)
            
            assert stream.stream_state.last_heartbeat is not None


# ============================================================================
# PROCESS TRADE UPDATE TESTS
# ============================================================================

class TestRobustAlpacaStreamProcessTradeUpdate:
    """Tests for trade update processing."""

    @pytest.mark.asyncio
    async def test_process_trade_update_missing_fields(self):
        """Test processing trade update with missing fields."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        # Missing order ID
        await stream._process_trade_update({"event": "fill"})
        
        # Missing event type
        await stream._process_trade_update({"order": {"id": "123"}})

    @pytest.mark.asyncio
    async def test_process_trade_update_order_not_found(self, sample_trade_update):
        """Test processing trade update when order not found."""
        with patch("backend.integrations.alpaca_stream_production.get_db_session") as mock_db, \
             patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            from backend.integrations.alpaca_stream_production import RobustAlpacaStream
            
            mock_session = AsyncMock()
            
            async def mock_gen():
                yield mock_session
            mock_db.return_value = mock_gen()
            
            stream = RobustAlpacaStream(api_key="key", api_secret="secret")
            stream.orders_repo = MagicMock()
            stream.orders_repo.get_by_broker_order_id = AsyncMock(return_value=None)
            
            # Should not raise
            await stream._process_trade_update(sample_trade_update)


# ============================================================================
# UPDATE ORDER FROM TRADE EVENT TESTS
# ============================================================================

class TestRobustAlpacaStreamUpdateOrder:
    """Tests for order update from trade events."""

    @pytest.mark.asyncio
    async def test_update_order_fill(self, mock_order, sample_trade_update):
        """Test updating order on fill event."""
        with patch("backend.integrations.alpaca_stream_production.LotTracker") as mock_tracker:
            from backend.integrations.alpaca_stream_production import RobustAlpacaStream
            
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.create_lot = AsyncMock()
            mock_tracker.return_value = mock_tracker_instance
            
            stream = RobustAlpacaStream(api_key="key", api_secret="secret")
            
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            
            await stream._update_order_from_trade_event(
                mock_session, mock_order, sample_trade_update
            )
            
            assert mock_order.status == "filled"
            assert mock_order.filled_at is not None

    @pytest.mark.asyncio
    async def test_update_order_partial_fill(self, mock_order):
        """Test updating order on partial fill event."""
        with patch("backend.integrations.alpaca_stream_production.LotTracker") as mock_tracker:
            from backend.integrations.alpaca_stream_production import RobustAlpacaStream
            
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.create_lot = AsyncMock()
            mock_tracker.return_value = mock_tracker_instance
            
            stream = RobustAlpacaStream(api_key="key", api_secret="secret")
            
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            
            trade_data = {
                "event": "partial_fill",
                "qty": "50",
                "price": "150.00"
            }
            
            await stream._update_order_from_trade_event(
                mock_session, mock_order, trade_data
            )
            
            assert mock_order.status == "partially_filled"
            assert mock_order.filled_qty == 50

    @pytest.mark.asyncio
    async def test_update_order_canceled(self, mock_order):
        """Test updating order on canceled event."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        trade_data = {"event": "canceled"}
        
        await stream._update_order_from_trade_event(
            mock_session, mock_order, trade_data
        )
        
        assert mock_order.status == "canceled"
        assert mock_order.canceled_at is not None

    @pytest.mark.asyncio
    async def test_update_order_cancelled_alternate(self, mock_order):
        """Test updating order on 'cancelled' (with double l) event."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        trade_data = {"event": "cancelled"}  # British spelling
        
        await stream._update_order_from_trade_event(
            mock_session, mock_order, trade_data
        )
        
        assert mock_order.status == "canceled"

    @pytest.mark.asyncio
    async def test_update_order_rejected(self, mock_order):
        """Test updating order on rejected event."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        trade_data = {"event": "rejected", "reason": "Insufficient funds"}
        
        await stream._update_order_from_trade_event(
            mock_session, mock_order, trade_data
        )
        
        assert mock_order.status == "rejected"
        assert mock_order.error_message == "Insufficient funds"


# ============================================================================
# GAP FILL TESTS
# ============================================================================

class TestRobustAlpacaStreamGapFill:
    """Tests for gap-filling functionality."""

    @pytest.mark.asyncio
    async def test_fill_gaps_no_previous_events(self):
        """Test gap-fill with no previous events."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.stream_state.last_event_ts = None
        
        # Should return early
        await stream._fill_gaps()

    @pytest.mark.asyncio
    async def test_fill_gaps_with_previous_events(self):
        """Test gap-fill with previous events."""
        with patch("backend.integrations.alpaca_stream_production.get_db_session") as mock_db, \
             patch("backend.integrations.alpaca_stream_production.select") as mock_select:
            from backend.integrations.alpaca_stream_production import RobustAlpacaStream
            
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result
            
            async def mock_gen():
                yield mock_session
            mock_db.return_value = mock_gen()
            
            stream = RobustAlpacaStream(api_key="key", api_secret="secret")
            stream.stream_state.last_event_ts = datetime.now(UTC) - timedelta(hours=1)
            
            await stream._fill_gaps()

    @pytest.mark.asyncio
    async def test_gap_fill_single_order_status_changed(self, mock_order):
        """Test gap-fill updates order with different status."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.alpaca_client = MagicMock()
        stream.alpaca_client.get_order = AsyncMock(return_value={
            "status": "filled",
            "filled_qty": "100",
            "filled_avg_price": "150.50"
        })
        stream.guardrails = None
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        mock_order.status = "submitted"  # Different from broker
        
        await stream._gap_fill_single_order(mock_session, mock_order)
        
        assert mock_order.status == "filled"

    @pytest.mark.asyncio
    async def test_gap_fill_single_order_same_status(self, mock_order):
        """Test gap-fill skips order with same status."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.alpaca_client = MagicMock()
        stream.alpaca_client.get_order = AsyncMock(return_value={
            "status": "submitted"
        })
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        mock_order.status = "submitted"  # Same as broker
        
        await stream._gap_fill_single_order(mock_session, mock_order)
        
        # commit should not be called if status unchanged
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_gap_fill_single_order_not_found(self, mock_order):
        """Test gap-fill when order not found in broker."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.alpaca_client = MagicMock()
        stream.alpaca_client.get_order = AsyncMock(return_value=None)
        
        mock_session = MagicMock()
        
        await stream._gap_fill_single_order(mock_session, mock_order)

    @pytest.mark.asyncio
    async def test_gap_fill_single_order_error(self, mock_order):
        """Test gap-fill handles error gracefully."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.alpaca_client = MagicMock()
        stream.alpaca_client.get_order = AsyncMock(side_effect=Exception("API error"))
        
        mock_session = MagicMock()
        
        # Should not raise
        await stream._gap_fill_single_order(mock_session, mock_order)


# ============================================================================
# SUBSCRIBE TO TRADE UPDATES TESTS
# ============================================================================

class TestRobustAlpacaStreamSubscribe:
    """Tests for subscription functionality."""

    @pytest.mark.asyncio
    async def test_subscribe_to_trade_updates(self, mock_websocket):
        """Test subscribing to trade updates."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.websocket = mock_websocket
        
        await stream._subscribe_to_trade_updates()
        
        # Should send auth and subscribe messages
        assert mock_websocket.send.call_count == 2


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestRobustAlpacaStreamEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_update_order_lot_tracking_error(self, mock_order, sample_trade_update):
        """Test order update handles lot tracking error gracefully."""
        with patch("backend.integrations.alpaca_stream_production.LotTracker") as mock_tracker:
            from backend.integrations.alpaca_stream_production import RobustAlpacaStream
            
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.create_lot = AsyncMock(side_effect=Exception("DB error"))
            mock_tracker.return_value = mock_tracker_instance
            
            stream = RobustAlpacaStream(api_key="key", api_secret="secret")
            
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            
            # Should not raise, order status still updated
            await stream._update_order_from_trade_event(
                mock_session, mock_order, sample_trade_update
            )
            
            assert mock_order.status == "filled"

    @pytest.mark.asyncio
    async def test_update_order_sell_side(self, sample_trade_update):
        """Test order update for sell side creates appropriate lot action."""
        with patch("backend.integrations.alpaca_stream_production.LotTracker") as mock_tracker:
            from backend.integrations.alpaca_stream_production import RobustAlpacaStream
            
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.close_lots_fifo = AsyncMock(return_value=[
                MagicMock(realized_pnl=Decimal("50.00"))
            ])
            mock_tracker.return_value = mock_tracker_instance
            
            stream = RobustAlpacaStream(api_key="key", api_secret="secret")
            
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            
            # Create sell order
            sell_order = MagicMock()
            sell_order.id = "sell-123"
            sell_order.side = "sell"
            sell_order.symbol = "AAPL"
            sell_order.status = "submitted"
            sell_order.filled_qty = 0
            sell_order.attributes = {"user_id": "test"}
            
            await stream._update_order_from_trade_event(
                mock_session, sell_order, sample_trade_update
            )
            
            mock_tracker_instance.close_lots_fifo.assert_called_once()

    @pytest.mark.asyncio
    async def test_gap_fill_with_guardrails(self, mock_order):
        """Test gap-fill records event with guardrails."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.alpaca_client = MagicMock()
        stream.alpaca_client.get_order = AsyncMock(return_value={
            "status": "filled",
            "filled_qty": "100"
        })
        stream.guardrails = MagicMock()
        stream.guardrails.record_trade_event = AsyncMock()
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        mock_order.status = "submitted"
        
        await stream._gap_fill_single_order(mock_session, mock_order)
        
        stream.guardrails.record_trade_event.assert_called_once()

# ============================================================================
# ADDITIONAL COVERAGE - Connection Loop and Start
# ============================================================================

class TestRobustAlpacaStreamConnectionLoop:
    """Tests for the connection loop."""

    @pytest.mark.asyncio
    async def test_connection_loop_exits_on_should_stop(self):
        """Test connection loop exits when should_stop is True."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.should_stop = True
        
        await stream._connection_loop()
        
        # Should exit immediately
        assert stream.should_stop is True

    @pytest.mark.asyncio
    async def test_connection_loop_reconnects_on_error(self):
        """Test connection loop attempts reconnect on error."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.min_backoff = 0.01
        stream.max_backoff = 0.02
        
        call_count = 0
        
        async def mock_connect():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                stream.should_stop = True
            raise Exception("Connection failed")
        
        with patch.object(stream, "_connect_and_listen", side_effect=mock_connect), \
             patch.object(stream, "_handle_connection_error", new_callable=AsyncMock), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            await stream._connection_loop()
        
        assert call_count >= 2


class TestRobustAlpacaStreamStart:
    """Tests for the start method."""

    @pytest.mark.asyncio
    async def test_start_loads_state_and_fills_gaps(self):
        """Test start loads state from DB and fills gaps."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        with patch.object(stream.stream_state, "load_from_db", new_callable=AsyncMock), \
             patch.object(stream, "_fill_gaps", new_callable=AsyncMock), \
             patch.object(stream, "_connection_loop", new_callable=AsyncMock):
            
            mock_guardrails = MagicMock()
            await stream.start(guardrails=mock_guardrails)
            
            stream.stream_state.load_from_db.assert_called_once()
            stream._fill_gaps.assert_called_once()
            stream._connection_loop.assert_called_once()
            assert stream.guardrails == mock_guardrails


class TestRobustAlpacaStreamConnectAndListen:
    """Tests for connect_and_listen method."""

    @pytest.mark.asyncio
    async def test_connect_and_listen_success(self, mock_websocket):
        """Test successful connection and listening."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        async def mock_iter():
            stream.should_stop = True
            if False:
                yield  # Make this a generator
        
        mock_websocket.__aiter__ = lambda self: mock_iter()
        
        with patch("backend.integrations.alpaca_stream_production.websockets.connect") as mock_connect, \
             patch.object(stream, "_subscribe_to_trade_updates", new_callable=AsyncMock), \
             patch.object(stream, "_process_message", new_callable=AsyncMock), \
             patch("backend.integrations.alpaca_stream_production.slo_monitor") as mock_slo:
            
            mock_connect.return_value.__aenter__ = AsyncMock(return_value=mock_websocket)
            mock_connect.return_value.__aexit__ = AsyncMock()
            
            stream.should_stop = True  # Exit immediately
            
            # Should complete without error
            try:
                await stream._connect_and_listen()
            except StopAsyncIteration:
                pass


class TestRobustAlpacaStreamProcessTradeUpdateBroadcast:
    """Tests for trade update processing with broadcast."""

    @pytest.mark.asyncio
    async def test_process_trade_update_broadcasts_to_user(self, mock_order, sample_trade_update):
        """Test trade update broadcasts to user WebSocket."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        with patch("backend.integrations.alpaca_stream_production.get_db_session") as mock_db, \
             patch("backend.api.socketio_server.broadcast_order_update", new_callable=AsyncMock) as mock_broadcast, \
             patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            stream.orders_repo = MagicMock()
            stream.orders_repo.get_by_broker_order_id = AsyncMock(return_value=mock_order)
            
            async def mock_gen():
                yield mock_session
            mock_db.return_value = mock_gen()
            
            with patch.object(stream, "_update_order_from_trade_event", new_callable=AsyncMock), \
                 patch.object(stream.stream_state, "update_last_event", new_callable=AsyncMock):
                await stream._process_trade_update(sample_trade_update)
                
                # Should broadcast to user
                mock_broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_trade_update_handles_broadcast_error(self, mock_order, sample_trade_update):
        """Test trade update handles broadcast errors gracefully."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        with patch("backend.integrations.alpaca_stream_production.get_db_session") as mock_db, \
             patch("backend.api.socketio_server.broadcast_order_update", 
                   new_callable=AsyncMock, side_effect=Exception("Broadcast failed")), \
             patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            stream.orders_repo = MagicMock()
            stream.orders_repo.get_by_broker_order_id = AsyncMock(return_value=mock_order)
            
            async def mock_gen():
                yield mock_session
            mock_db.return_value = mock_gen()
            
            with patch.object(stream, "_update_order_from_trade_event", new_callable=AsyncMock), \
                 patch.object(stream.stream_state, "update_last_event", new_callable=AsyncMock):
                # Should not raise
                await stream._process_trade_update(sample_trade_update)


class TestRobustAlpacaStreamGuardrailsDedupe:
    """Tests for guardrails deduplication."""

    @pytest.mark.asyncio
    async def test_process_trade_update_skips_duplicate_event(self, mock_order, sample_trade_update):
        """Test duplicate events are skipped via guardrails."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.guardrails = MagicMock()
        stream.guardrails.record_trade_event = AsyncMock(return_value=False)  # Duplicate
        
        with patch("backend.integrations.alpaca_stream_production.get_db_session") as mock_db, \
             patch("backend.integrations.alpaca_stream_production.slo_monitor"):
            
            mock_session = MagicMock()
            stream.orders_repo = MagicMock()
            stream.orders_repo.get_by_broker_order_id = AsyncMock(return_value=mock_order)
            
            async def mock_gen():
                yield mock_session
            mock_db.return_value = mock_gen()
            
            with patch.object(stream, "_update_order_from_trade_event", new_callable=AsyncMock) as mock_update:
                await stream._process_trade_update(sample_trade_update)
                
                # Should not call update since it was a duplicate
                mock_update.assert_not_called()


class TestRobustAlpacaStreamFillGapsComplete:
    """Additional gap filling tests."""

    @pytest.mark.asyncio
    async def test_fill_gaps_with_guardrails_recording(self):
        """Test fill_gaps records events via guardrails."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.guardrails = MagicMock()
        stream.guardrails.record_trade_event = AsyncMock(return_value=True)
        stream.alpaca_client = MagicMock()
        stream.alpaca_client.get_order = AsyncMock(return_value={
            "status": "filled",
            "filled_qty": "100"
        })
        
        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.broker_order_id = "broker-123"
        mock_order.status = "submitted"
        mock_order.filled_qty = 0
        mock_order.symbol = "AAPL"
        mock_order.side = "buy"
        mock_order.order_type = "market"
        mock_order.submitted_at = None
        mock_order.attributes = {}
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        with patch.object(stream, "_update_order_from_trade_event", new_callable=AsyncMock):
            await stream._gap_fill_single_order(mock_session, mock_order)
            
            stream.guardrails.record_trade_event.assert_called_once()


class TestRobustAlpacaStreamHandleConnectionError:
    """Tests for connection error handling."""

    @pytest.mark.asyncio
    async def test_handle_connection_error_connection_closed(self):
        """Test handle_connection_error classifies ConnectionClosed."""
        from websockets.exceptions import ConnectionClosed
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.is_running = True
        stream.guardrails = MagicMock()
        stream.guardrails.record_broker_error = MagicMock()
        
        with patch("backend.integrations.alpaca_stream_production.slo_monitor") as mock_slo:
            error = ConnectionClosed(None, None)
            await stream._handle_connection_error(error)
            
            assert stream.is_running is False
            mock_slo.record_stream_reconnect.assert_called_with("connection_closed")
            stream.guardrails.record_broker_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_connection_error_invalid_uri(self):
        """Test handle_connection_error classifies InvalidURI."""
        from websockets.exceptions import InvalidURI
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.is_running = True
        
        with patch("backend.integrations.alpaca_stream_production.slo_monitor") as mock_slo:
            error = InvalidURI("invalid://url", "Invalid URI")
            await stream._handle_connection_error(error)
            
            assert stream.is_running is False
            mock_slo.record_stream_reconnect.assert_called_with("invalid_uri")

    @pytest.mark.asyncio
    async def test_handle_connection_error_timeout(self):
        """Test handle_connection_error classifies timeout."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.is_running = True
        stream.guardrails = MagicMock()
        stream.guardrails.record_broker_error = MagicMock()
        
        with patch("backend.integrations.alpaca_stream_production.slo_monitor") as mock_slo:
            error = asyncio.TimeoutError()
            await stream._handle_connection_error(error)
            
            assert stream.is_running is False
            mock_slo.record_stream_reconnect.assert_called_with("timeout")
            stream.guardrails.record_broker_error.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_connection_error_unknown(self):
        """Test handle_connection_error classifies unknown error."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.is_running = True
        
        with patch("backend.integrations.alpaca_stream_production.slo_monitor") as mock_slo:
            error = ValueError("Unknown error")
            await stream._handle_connection_error(error)
            
            assert stream.is_running is False
            mock_slo.record_stream_reconnect.assert_called_with("unknown_error")


class TestRobustAlpacaStreamPartialFillTracking:
    """Tests for partial fill lot tracking."""

    @pytest.mark.asyncio
    async def test_partial_fill_buy_creates_lot(self, mock_order, sample_trade_update):
        """Test partial buy fill creates a lot."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        with patch("backend.integrations.alpaca_stream_production.LotTracker") as mock_tracker:
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.create_lot = AsyncMock()
            mock_tracker.return_value = mock_tracker_instance
            
            stream = RobustAlpacaStream(api_key="key", api_secret="secret")
            
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            
            buy_order = MagicMock()
            buy_order.id = "buy-123"
            buy_order.side = "buy"
            buy_order.symbol = "AAPL"
            buy_order.status = "submitted"
            buy_order.filled_qty = 0
            buy_order.attributes = {"user_id": "test-user"}
            
            partial_fill_update = {
                "event": "partial_fill",
                "qty": "50",
                "price": "150.00",
                "timestamp": "2025-01-01T00:00:00Z"
            }
            
            await stream._update_order_from_trade_event(mock_session, buy_order, partial_fill_update)
            
            mock_tracker_instance.create_lot.assert_called_once()
            assert buy_order.status == "partially_filled"

    @pytest.mark.asyncio
    async def test_partial_fill_sell_closes_lots(self, mock_order, sample_trade_update):
        """Test partial sell fill closes lots FIFO."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        with patch("backend.integrations.alpaca_stream_production.LotTracker") as mock_tracker:
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.close_lots_fifo = AsyncMock(return_value=[
                MagicMock(realized_pnl=Decimal("10.00"))
            ])
            mock_tracker.return_value = mock_tracker_instance
            
            stream = RobustAlpacaStream(api_key="key", api_secret="secret")
            
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            
            sell_order = MagicMock()
            sell_order.id = "sell-123"
            sell_order.side = "sell"
            sell_order.symbol = "AAPL"
            sell_order.status = "submitted"
            sell_order.filled_qty = 0
            sell_order.attributes = {"user_id": "test-user"}
            
            partial_fill_update = {
                "event": "partial_fill",
                "qty": "30",
                "price": "155.00",
                "timestamp": "2025-01-01T00:00:00Z"
            }
            
            await stream._update_order_from_trade_event(mock_session, sell_order, partial_fill_update)
            
            mock_tracker_instance.close_lots_fifo.assert_called_once()
            assert sell_order.status == "partially_filled"

    @pytest.mark.asyncio
    async def test_partial_fill_lot_tracking_error(self, mock_order, sample_trade_update):
        """Test partial fill handles lot tracking error gracefully."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        with patch("backend.integrations.alpaca_stream_production.LotTracker") as mock_tracker:
            mock_tracker_instance = MagicMock()
            mock_tracker_instance.create_lot = AsyncMock(side_effect=Exception("Lot error"))
            mock_tracker.return_value = mock_tracker_instance
            
            stream = RobustAlpacaStream(api_key="key", api_secret="secret")
            
            mock_session = MagicMock()
            mock_session.commit = AsyncMock()
            
            buy_order = MagicMock()
            buy_order.id = "buy-123"
            buy_order.side = "buy"
            buy_order.symbol = "AAPL"
            buy_order.status = "submitted"
            buy_order.filled_qty = 0
            buy_order.attributes = {"user_id": "test-user"}
            
            partial_fill_update = {
                "event": "partial_fill",
                "qty": "50",
                "price": "150.00",
                "timestamp": "2025-01-01T00:00:00Z"
            }
            
            # Should not raise
            await stream._update_order_from_trade_event(mock_session, buy_order, partial_fill_update)
            
            # Order status should still be updated despite lot error
            assert buy_order.status == "partially_filled"


class TestRobustAlpacaStreamCanceledRejected:
    """Tests for canceled and rejected order events."""

    @pytest.mark.asyncio
    async def test_canceled_order_update(self, mock_order):
        """Test canceled order status update."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        order = MagicMock()
        order.status = "submitted"
        order.filled_qty = 0
        order.attributes = {}
        
        canceled_update = {
            "event": "canceled",
            "timestamp": "2025-01-01T00:00:00Z"
        }
        
        await stream._update_order_from_trade_event(mock_session, order, canceled_update)
        
        assert order.status == "canceled"
        assert order.canceled_at is not None

    @pytest.mark.asyncio
    async def test_cancelled_spelling_order_update(self, mock_order):
        """Test cancelled (British spelling) order status update."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        order = MagicMock()
        order.status = "submitted"
        order.filled_qty = 0
        order.attributes = {}
        
        cancelled_update = {
            "event": "cancelled",
            "timestamp": "2025-01-01T00:00:00Z"
        }
        
        await stream._update_order_from_trade_event(mock_session, order, cancelled_update)
        
        assert order.status == "canceled"

    @pytest.mark.asyncio
    async def test_rejected_order_update(self, mock_order):
        """Test rejected order status update."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        order = MagicMock()
        order.status = "submitted"
        order.filled_qty = 0
        order.attributes = {}
        
        rejected_update = {
            "event": "rejected",
            "reason": "Insufficient funds",
            "timestamp": "2025-01-01T00:00:00Z"
        }
        
        await stream._update_order_from_trade_event(mock_session, order, rejected_update)
        
        assert order.status == "rejected"
        assert order.error_message == "Insufficient funds"

    @pytest.mark.asyncio
    async def test_rejected_order_default_reason(self, mock_order):
        """Test rejected order with default reason."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        order = MagicMock()
        order.status = "submitted"
        order.filled_qty = 0
        order.attributes = {}
        
        rejected_update = {
            "event": "rejected",
            "timestamp": "2025-01-01T00:00:00Z"
            # No reason provided
        }
        
        await stream._update_order_from_trade_event(mock_session, order, rejected_update)
        
        assert order.status == "rejected"
        assert order.error_message == "Order rejected by broker"


class TestRobustAlpacaStreamFillGapsNoLastEvent:
    """Tests for gap filling when no last event exists."""

    @pytest.mark.asyncio
    async def test_fill_gaps_no_last_event(self):
        """Test fill_gaps returns early when no last event timestamp."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.stream_state.last_event_ts = None
        
        with patch("backend.integrations.alpaca_stream_production.get_db_session") as mock_db:
            await stream._fill_gaps()
            
            # Should not call get_db_session since no last event
            mock_db.assert_not_called()


class TestRobustAlpacaStreamGapFillError:
    """Tests for gap fill error handling."""

    @pytest.mark.asyncio
    async def test_gap_fill_single_order_error(self):
        """Test gap_fill_single_order handles errors gracefully."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.alpaca_client = MagicMock()
        stream.alpaca_client.get_order = AsyncMock(side_effect=Exception("API error"))
        
        mock_session = MagicMock()
        mock_order = MagicMock()
        mock_order.broker_order_id = "broker-123"
        
        # Should not raise
        await stream._gap_fill_single_order(mock_session, mock_order)

    @pytest.mark.asyncio
    async def test_gap_fill_single_order_no_broker_order(self):
        """Test gap_fill_single_order handles missing broker order."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.alpaca_client = MagicMock()
        stream.alpaca_client.get_order = AsyncMock(return_value=None)
        
        mock_session = MagicMock()
        mock_order = MagicMock()
        mock_order.broker_order_id = "broker-123"
        
        # Should not raise
        await stream._gap_fill_single_order(mock_session, mock_order)


class TestRobustAlpacaStreamGapFillStatusMatch:
    """Tests for gap fill when status matches."""

    @pytest.mark.asyncio
    async def test_gap_fill_status_matches_no_update(self):
        """Test gap_fill does not update when status matches."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.alpaca_client = MagicMock()
        stream.alpaca_client.get_order = AsyncMock(return_value={
            "status": "filled"  # Same as order status
        })
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        mock_order = MagicMock()
        mock_order.broker_order_id = "broker-123"
        mock_order.status = "filled"  # Same as broker status
        
        await stream._gap_fill_single_order(mock_session, mock_order)
        
        # Should not commit since status matches
        mock_session.commit.assert_not_called()


class TestRobustAlpacaStreamGapFillPartiallyFilled:
    """Tests for gap fill with partially filled orders."""

    @pytest.mark.asyncio
    async def test_gap_fill_partially_filled_update(self):
        """Test gap_fill updates partially filled orders."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        stream.guardrails = MagicMock()
        stream.guardrails.record_trade_event = AsyncMock(return_value=True)
        stream.alpaca_client = MagicMock()
        stream.alpaca_client.get_order = AsyncMock(return_value={
            "status": "partially_filled",
            "filled_qty": "50",
            "filled_avg_price": "150.00"
        })
        
        mock_session = MagicMock()
        mock_session.commit = AsyncMock()
        
        mock_order = MagicMock()
        mock_order.id = "order-123"
        mock_order.broker_order_id = "broker-123"
        mock_order.status = "submitted"
        
        await stream._gap_fill_single_order(mock_session, mock_order)
        
        assert mock_order.status == "partially_filled"
        assert mock_order.filled_qty == 50.0
        assert mock_order.filled_price == 150.0
        mock_session.commit.assert_called_once()


class TestRobustAlpacaStreamProcessMessageBreak:
    """Tests for process message break on should_stop."""

    @pytest.mark.asyncio
    async def test_connection_loop_breaks_on_should_stop(self):
        """Test that message loop breaks when should_stop is set."""
        from backend.integrations.alpaca_stream_production import RobustAlpacaStream
        
        stream = RobustAlpacaStream(api_key="key", api_secret="secret")
        
        # Create mock websocket that sets should_stop after first message
        class MockWebSocket:
            def __init__(self):
                self.messages = ['{"T": "auth", "msg": "authenticated"}']
                self.index = 0
            
            async def send(self, msg):
                pass
            
            async def recv(self):
                if self.index >= len(self.messages):
                    await asyncio.sleep(0.1)
                    return None
                msg = self.messages[self.index]
                self.index += 1
                stream.should_stop = True
                return msg
            
            def __aiter__(self):
                return self
            
            async def __anext__(self):
                if stream.should_stop:
                    raise StopAsyncIteration
                return await self.recv()
        
        mock_ws = MockWebSocket()
        
        with patch("websockets.connect", new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value.__aenter__.return_value = mock_ws
            
            with patch.object(stream, "_process_message", new_callable=AsyncMock):
                with patch("backend.integrations.alpaca_stream_production.slo_monitor"):
                    # Run connection loop with timeout
                    task = asyncio.create_task(stream._connection_loop())
                    await asyncio.sleep(0.2)
                    
                    stream.should_stop = True
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass