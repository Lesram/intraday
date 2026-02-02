"""
Comprehensive tests for backend/integrations/alpaca_outbox.py

Tests the AlpacaOutboxDispatcher for routing order events to brokers.
Covers: TIF selection, mock/live broker dispatch, error handling.

Phase 3: Alpaca Integrations - Outbox Dispatcher Tests
"""

import asyncio
from datetime import datetime, time
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_settings():
    """Mock settings for outbox dispatcher."""
    settings = MagicMock()
    settings.USE_MOCK_BROKER = False
    return settings


@pytest.fixture
def mock_env_vars(monkeypatch):
    """Set environment variables."""
    monkeypatch.setenv("USE_MOCK_BROKER", "false")


@pytest.fixture
def sample_order_event():
    """Sample order event data."""
    return {
        "order_id": "order-123",
        "symbol": "AAPL",
        "side": "buy",
        "qty": 100,
        "order_type": "market",
        "tif": "day",
        "client_key": "client-key-abc"
    }


# ============================================================================
# SMART TIF SELECTION TESTS
# ============================================================================

class TestGetSmartTif:
    """Tests for get_smart_tif function."""

    def test_smart_tif_with_explicit_gtc(self):
        """Test explicit GTC TIF is honored."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        result = get_smart_tif("gtc")
        
        assert result == "gtc"

    def test_smart_tif_with_explicit_ioc(self):
        """Test explicit IOC TIF is honored."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        result = get_smart_tif("ioc")
        
        assert result == "ioc"

    def test_smart_tif_with_explicit_fok(self):
        """Test explicit FOK TIF is honored."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        result = get_smart_tif("fok")
        
        assert result == "fok"

    def test_smart_tif_market_hours_returns_day(self):
        """Test market hours returns 'day' TIF."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        # Mock market hours (11 AM ET on Monday)
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 6, 11, 0, 0, tzinfo=ZoneInfo("America/New_York"))  # Monday
            mock_dt.now.return_value = mock_now
            
            result = get_smart_tif(None)
            
            assert result == "day"

    def test_smart_tif_after_hours_returns_gtc(self):
        """Test after hours returns 'gtc' TIF."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        # Mock after hours (6 PM ET on Monday)
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 6, 18, 0, 0, tzinfo=ZoneInfo("America/New_York"))  # Monday
            mock_dt.now.return_value = mock_now
            
            result = get_smart_tif(None)
            
            assert result == "gtc"

    def test_smart_tif_before_market_returns_gtc(self):
        """Test before market hours returns 'gtc' TIF."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        # Mock before market (8 AM ET on Monday)
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 6, 8, 0, 0, tzinfo=ZoneInfo("America/New_York"))  # Monday
            mock_dt.now.return_value = mock_now
            
            result = get_smart_tif(None)
            
            assert result == "gtc"

    def test_smart_tif_weekend_returns_gtc(self):
        """Test weekend returns 'gtc' TIF."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        # Mock Saturday
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 4, 11, 0, 0, tzinfo=ZoneInfo("America/New_York"))  # Saturday
            mock_dt.now.return_value = mock_now
            
            result = get_smart_tif(None)
            
            assert result == "gtc"

    def test_smart_tif_sunday_returns_gtc(self):
        """Test Sunday returns 'gtc' TIF."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        # Mock Sunday
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 5, 11, 0, 0, tzinfo=ZoneInfo("America/New_York"))  # Sunday
            mock_dt.now.return_value = mock_now
            
            result = get_smart_tif(None)
            
            assert result == "gtc"

    def test_smart_tif_handles_exception(self):
        """Test exception handling defaults to 'gtc'."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_dt.now.side_effect = Exception("TZ error")
            
            result = get_smart_tif(None)
            
            assert result == "gtc"

    def test_smart_tif_day_honored_during_market_hours(self):
        """Test explicit 'day' TIF during market hours."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        # Even with explicit 'day', if market closed, still gtc
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 6, 11, 0, 0, tzinfo=ZoneInfo("America/New_York"))
            mock_dt.now.return_value = mock_now
            
            result = get_smart_tif("day")
            
            assert result == "day"

    def test_smart_tif_market_open_edge(self):
        """Test exactly at market open (9:30 AM ET)."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 6, 9, 30, 0, tzinfo=ZoneInfo("America/New_York"))  # Monday
            mock_dt.now.return_value = mock_now
            
            result = get_smart_tif(None)
            
            assert result == "day"

    def test_smart_tif_market_close_edge(self):
        """Test exactly at market close (4:00 PM ET)."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 6, 16, 0, 0, tzinfo=ZoneInfo("America/New_York"))  # Monday
            mock_dt.now.return_value = mock_now
            
            result = get_smart_tif(None)
            
            assert result == "day"


# ============================================================================
# AlpacaOutboxDispatcher INITIALIZATION TESTS
# ============================================================================

class TestAlpacaOutboxDispatcherInit:
    """Tests for AlpacaOutboxDispatcher initialization."""

    def test_init_with_mock_broker_env(self, monkeypatch):
        """Test initialization with USE_MOCK_BROKER=true from env."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            assert dispatcher.use_mock_broker is True

    def test_init_with_mock_broker_settings(self, monkeypatch):
        """Test initialization with USE_MOCK_BROKER from settings."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=True)
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            assert dispatcher.use_mock_broker is True

    def test_init_prefers_env_over_settings(self, monkeypatch):
        """Test that env variable takes precedence."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            # Env = true should override settings = False
            assert dispatcher.use_mock_broker is True

    def test_init_defaults_to_live(self, monkeypatch):
        """Test initialization defaults to live broker."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            assert dispatcher.use_mock_broker is False


# ============================================================================
# DISPATCH ORDER EVENT TESTS
# ============================================================================

class TestAlpacaOutboxDispatcherDispatch:
    """Tests for dispatch_order_event method."""

    @pytest.mark.asyncio
    async def test_dispatch_to_mock_broker(self, monkeypatch, sample_order_event):
        """Test dispatching to mock broker."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            result = await dispatcher.dispatch_order_event(sample_order_event)
            
            assert result["success"] is True
            assert result["broker"] == "mock"
            assert result["broker_order_id"].startswith("MOCK_")

    @pytest.mark.asyncio
    async def test_dispatch_to_alpaca_broker(self, monkeypatch, sample_order_event):
        """Test dispatching to Alpaca broker."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_broker.get_alpaca_broker_client") as mock_broker:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            mock_broker_client = AsyncMock()
            mock_broker_client.place_order.return_value = {
                "id": "alpaca-order-456",
                "status": "accepted"
            }
            mock_broker.return_value = mock_broker_client
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            result = await dispatcher.dispatch_order_event(sample_order_event)
            
            assert result["success"] is True
            assert result["broker"] == "alpaca"
            assert result["broker_order_id"] == "alpaca-order-456"

    @pytest.mark.asyncio
    async def test_dispatch_exception_handling(self, monkeypatch, sample_order_event):
        """Test dispatch handles exceptions gracefully."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_broker.get_alpaca_broker_client") as mock_broker:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            mock_broker.side_effect = Exception("Connection failed")
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            result = await dispatcher.dispatch_order_event(sample_order_event)
            
            assert result["success"] is False
            assert result["status"] == "failed"
            assert "Connection failed" in result["error"]


# ============================================================================
# MOCK BROKER DISPATCH TESTS
# ============================================================================

class TestAlpacaOutboxDispatcherMockBroker:
    """Tests for mock broker dispatch."""

    @pytest.mark.asyncio
    async def test_mock_broker_generates_id(self, monkeypatch, sample_order_event):
        """Test mock broker generates unique order ID."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            result = await dispatcher._dispatch_to_mock_broker(sample_order_event)
            
            assert result["broker_order_id"].startswith("MOCK_AAPL_")

    @pytest.mark.asyncio
    async def test_mock_broker_returns_accepted_status(self, monkeypatch, sample_order_event):
        """Test mock broker returns accepted status."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            result = await dispatcher._dispatch_to_mock_broker(sample_order_event)
            
            assert result["status"] == "accepted"
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_mock_broker_simulates_delay(self, monkeypatch, sample_order_event):
        """Test mock broker simulates processing delay."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            import time
            start = time.time()
            await dispatcher._dispatch_to_mock_broker(sample_order_event)
            elapsed = time.time() - start
            
            # Should have some delay
            assert elapsed >= 0.05  # At least 50ms


# ============================================================================
# ALPACA BROKER DISPATCH TESTS
# ============================================================================

class TestAlpacaOutboxDispatcherAlpacaBroker:
    """Tests for Alpaca broker dispatch."""

    @pytest.mark.asyncio
    async def test_alpaca_broker_places_order(self, monkeypatch, sample_order_event):
        """Test Alpaca broker places order correctly."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_broker.get_alpaca_broker_client") as mock_broker, \
             patch("backend.integrations.alpaca_outbox.get_smart_tif", return_value="day"):
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            mock_broker_client = AsyncMock()
            mock_broker_client.place_order.return_value = {
                "id": "order-xyz",
                "status": "new"
            }
            mock_broker.return_value = mock_broker_client
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            result = await dispatcher._dispatch_to_alpaca_broker(sample_order_event)
            
            mock_broker_client.place_order.assert_called_once()
            call_kwargs = mock_broker_client.place_order.call_args[1]
            
            assert call_kwargs["symbol"] == "AAPL"
            assert call_kwargs["side"] == "buy"
            assert call_kwargs["qty"] == 100

    @pytest.mark.asyncio
    async def test_alpaca_broker_uses_smart_tif(self, monkeypatch, sample_order_event):
        """Test Alpaca broker uses smart TIF selection."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_broker.get_alpaca_broker_client") as mock_broker, \
             patch("backend.integrations.alpaca_outbox.get_smart_tif", return_value="gtc") as mock_tif:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            mock_broker_client = AsyncMock()
            mock_broker_client.place_order.return_value = {"id": "123", "status": "new"}
            mock_broker.return_value = mock_broker_client
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            await dispatcher._dispatch_to_alpaca_broker(sample_order_event)
            
            mock_tif.assert_called_once_with("day")  # Original TIF from event
            
            call_kwargs = mock_broker_client.place_order.call_args[1]
            assert call_kwargs["tif"] == "gtc"  # Smart TIF result

    @pytest.mark.asyncio
    async def test_alpaca_broker_handles_failure(self, monkeypatch, sample_order_event):
        """Test Alpaca broker handles order failure."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_broker.get_alpaca_broker_client") as mock_broker:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            mock_broker_client = AsyncMock()
            mock_broker_client.place_order.side_effect = Exception("Insufficient funds")
            mock_broker.return_value = mock_broker_client
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            result = await dispatcher._dispatch_to_alpaca_broker(sample_order_event)
            
            assert result["success"] is False
            assert result["status"] == "failed"
            assert "Insufficient funds" in result["error"]

    @pytest.mark.asyncio
    async def test_alpaca_broker_with_limit_order(self, monkeypatch):
        """Test Alpaca broker with limit order parameters."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        limit_order = {
            "order_id": "order-limit",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 50,
            "order_type": "limit",
            "limit_price": 150.00,
            "tif": "day",
            "client_key": "client-abc"
        }
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_broker.get_alpaca_broker_client") as mock_broker, \
             patch("backend.integrations.alpaca_outbox.get_smart_tif", return_value="day"):
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            mock_broker_client = AsyncMock()
            mock_broker_client.place_order.return_value = {"id": "123", "status": "new"}
            mock_broker.return_value = mock_broker_client
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            await dispatcher._dispatch_to_alpaca_broker(limit_order)
            
            call_kwargs = mock_broker_client.place_order.call_args[1]
            assert call_kwargs["type"] == "limit"
            assert call_kwargs["limit_price"] == 150.00

    @pytest.mark.asyncio
    async def test_alpaca_broker_with_stop_order(self, monkeypatch):
        """Test Alpaca broker with stop order parameters."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        stop_order = {
            "order_id": "order-stop",
            "symbol": "TSLA",
            "side": "sell",
            "qty": 25,
            "order_type": "stop",
            "stop_price": 200.00,
            "tif": "gtc"
        }
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_broker.get_alpaca_broker_client") as mock_broker, \
             patch("backend.integrations.alpaca_outbox.get_smart_tif", return_value="gtc"):
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            mock_broker_client = AsyncMock()
            mock_broker_client.place_order.return_value = {"id": "456", "status": "new"}
            mock_broker.return_value = mock_broker_client
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            await dispatcher._dispatch_to_alpaca_broker(stop_order)
            
            call_kwargs = mock_broker_client.place_order.call_args[1]
            assert call_kwargs["type"] == "stop"
            assert call_kwargs["stop_price"] == 200.00


# ============================================================================
# GLOBAL INSTANCE TESTS
# ============================================================================

class TestAlpacaOutboxDispatcherGlobalInstance:
    """Tests for global dispatcher instance functions."""

    def test_get_alpaca_outbox_dispatcher_singleton(self, monkeypatch):
        """Test get_alpaca_outbox_dispatcher returns singleton."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations import alpaca_outbox
            
            # Reset global
            alpaca_outbox._outbox_dispatcher = None
            
            dispatcher1 = alpaca_outbox.get_alpaca_outbox_dispatcher()
            dispatcher2 = alpaca_outbox.get_alpaca_outbox_dispatcher()
            
            assert dispatcher1 is dispatcher2
            
            # Cleanup
            alpaca_outbox._outbox_dispatcher = None

    def test_get_alpaca_outbox_dispatcher_creates_new(self, monkeypatch):
        """Test get_alpaca_outbox_dispatcher creates new instance."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations import alpaca_outbox
            
            alpaca_outbox._outbox_dispatcher = None
            
            dispatcher = alpaca_outbox.get_alpaca_outbox_dispatcher()
            
            assert dispatcher is not None
            
            # Cleanup
            alpaca_outbox._outbox_dispatcher = None


# ============================================================================
# HANDLE ORDER SUBMITTED EVENT TESTS
# ============================================================================

class TestHandleOrderSubmittedEvent:
    """Tests for handle_order_submitted_event function."""

    @pytest.mark.asyncio
    async def test_handle_order_submitted_event(self, monkeypatch, sample_order_event):
        """Test handle_order_submitted_event dispatches correctly."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations import alpaca_outbox
            
            # Reset global
            alpaca_outbox._outbox_dispatcher = None
            
            result = await alpaca_outbox.handle_order_submitted_event(sample_order_event)
            
            assert result["success"] is True
            assert result["broker"] == "mock"
            
            # Cleanup
            alpaca_outbox._outbox_dispatcher = None

    @pytest.mark.asyncio
    async def test_handle_order_submitted_uses_dispatcher(self, monkeypatch, sample_order_event):
        """Test handle_order_submitted_event uses global dispatcher."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations import alpaca_outbox
            
            # Reset and get fresh dispatcher
            alpaca_outbox._outbox_dispatcher = None
            
            result1 = await alpaca_outbox.handle_order_submitted_event(sample_order_event)
            result2 = await alpaca_outbox.handle_order_submitted_event(sample_order_event)
            
            # Both should succeed
            assert result1["success"] is True
            assert result2["success"] is True
            
            # Cleanup
            alpaca_outbox._outbox_dispatcher = None


# ============================================================================
# EDGE CASE TESTS
# ============================================================================

class TestAlpacaOutboxDispatcherEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_dispatch_with_float_qty(self, monkeypatch):
        """Test dispatch handles float quantity by converting to int."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        float_qty_order = {
            "order_id": "order-float",
            "symbol": "AAPL",
            "side": "buy",
            "qty": "100.5",  # String float
            "order_type": "market"
        }
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_broker.get_alpaca_broker_client") as mock_broker, \
             patch("backend.integrations.alpaca_outbox.get_smart_tif", return_value="day"):
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            mock_broker_client = AsyncMock()
            mock_broker_client.place_order.return_value = {"id": "123", "status": "new"}
            mock_broker.return_value = mock_broker_client
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            await dispatcher._dispatch_to_alpaca_broker(float_qty_order)
            
            call_kwargs = mock_broker_client.place_order.call_args[1]
            assert call_kwargs["qty"] == 100  # Converted to int

    @pytest.mark.asyncio
    async def test_dispatch_with_missing_fields(self, monkeypatch):
        """Test dispatch handles missing optional fields."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        minimal_order = {
            "order_id": "order-minimal",
            "symbol": "AAPL",
            "side": "buy",
            "qty": 100
        }
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_broker.get_alpaca_broker_client") as mock_broker, \
             patch("backend.integrations.alpaca_outbox.get_smart_tif", return_value="day"):
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            mock_broker_client = AsyncMock()
            mock_broker_client.place_order.return_value = {"id": "123", "status": "new"}
            mock_broker.return_value = mock_broker_client
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            result = await dispatcher._dispatch_to_alpaca_broker(minimal_order)
            
            assert result["success"] is True
            
            call_kwargs = mock_broker_client.place_order.call_args[1]
            assert call_kwargs["type"] == "market"  # Default
            assert call_kwargs["limit_price"] is None
            assert call_kwargs["stop_price"] is None

    @pytest.mark.asyncio
    async def test_dispatch_empty_event(self, monkeypatch):
        """Test dispatch handles empty event data gracefully with error."""
        monkeypatch.setenv("USE_MOCK_BROKER", "true")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get:
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            result = await dispatcher.dispatch_order_event({})
            
            # Empty event should fail with error
            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_alpaca_response_contains_full_data(self, monkeypatch, sample_order_event):
        """Test Alpaca response includes full alpaca_response."""
        monkeypatch.setenv("USE_MOCK_BROKER", "false")
        
        with patch("backend.integrations.alpaca_outbox.get_settings") as mock_get, \
             patch("backend.integrations.alpaca_broker.get_alpaca_broker_client") as mock_broker, \
             patch("backend.integrations.alpaca_outbox.get_smart_tif", return_value="day"):
            mock_get.return_value = MagicMock(USE_MOCK_BROKER=False)
            
            alpaca_response = {
                "id": "order-123",
                "status": "accepted",
                "symbol": "AAPL",
                "qty": "100",
                "filled_qty": "0"
            }
            
            mock_broker_client = AsyncMock()
            mock_broker_client.place_order.return_value = alpaca_response
            mock_broker.return_value = mock_broker_client
            
            from backend.integrations.alpaca_outbox import AlpacaOutboxDispatcher
            
            dispatcher = AlpacaOutboxDispatcher()
            
            result = await dispatcher._dispatch_to_alpaca_broker(sample_order_event)
            
            assert result["alpaca_response"] == alpaca_response


# ============================================================================
# TIF EDGE CASE TESTS
# ============================================================================

class TestSmartTifEdgeCases:
    """Edge case tests for TIF selection."""

    def test_smart_tif_uppercase_input(self):
        """Test TIF input is case-insensitive."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        assert get_smart_tif("GTC") == "gtc"
        assert get_smart_tif("IOC") == "ioc"
        assert get_smart_tif("FOK") == "fok"

    def test_smart_tif_mixed_case_input(self):
        """Test TIF with mixed case - non-day TIFs are honored."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        assert get_smart_tif("Gtc") == "gtc"
        assert get_smart_tif("Ioc") == "ioc"
        assert get_smart_tif("FoK") == "fok"  # Mixed case non-day honored

    def test_smart_tif_none_input(self):
        """Test TIF with None uses smart selection."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 6, 11, 0, 0, tzinfo=ZoneInfo("America/New_York"))
            mock_dt.now.return_value = mock_now
            
            result = get_smart_tif(None)
            
            # Should use smart selection (market hours = day)
            assert result == "day"

    def test_smart_tif_empty_string(self):
        """Test TIF with empty string uses smart selection."""
        from backend.integrations.alpaca_outbox import get_smart_tif
        
        with patch("backend.integrations.alpaca_outbox.datetime") as mock_dt:
            mock_now = datetime(2025, 1, 6, 11, 0, 0, tzinfo=ZoneInfo("America/New_York"))
            mock_dt.now.return_value = mock_now
            
            # Empty string should be falsy, use smart selection
            result = get_smart_tif("")
            
            assert result == "day"
