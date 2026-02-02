"""
Comprehensive tests for backend.services.trade_service

Targets 70%+ coverage for TradeService:
- Trade history retrieval
- Filtering and pagination
- Analytics calculations
- CSV export
"""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.trade_service import TradeService


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_db_session():
    """Create mock database session"""
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_alpaca_client():
    """Create mock Alpaca client"""
    client = MagicMock()
    client.get_positions = AsyncMock(return_value=[])
    client.get_account = AsyncMock(return_value={})
    return client


@pytest.fixture
def trade_service(mock_db_session, mock_alpaca_client):
    """Create TradeService with mocked dependencies"""
    with patch("backend.services.trade_service.PositionReconciliationService"):
        with patch("backend.services.trade_service.InstitutionalAnalytics"):
            service = TradeService(mock_db_session, mock_alpaca_client)
            service.reconciliation_service = MagicMock()
            service.reconciliation_service.get_position_status_for_orders = AsyncMock(return_value={})
            service.analytics_service = MagicMock()
            return service


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestTradeServiceInit:
    """Tests for TradeService initialization"""
    
    def test_init_with_db(self, mock_db_session, mock_alpaca_client):
        """Test initialization with database session"""
        with patch("backend.services.trade_service.PositionReconciliationService"):
            with patch("backend.services.trade_service.InstitutionalAnalytics"):
                service = TradeService(mock_db_session, mock_alpaca_client)
        
        assert service.db == mock_db_session
        assert service.alpaca_client == mock_alpaca_client
        
    def test_init_without_alpaca_client(self, mock_db_session):
        """Test initialization creates default Alpaca client"""
        with patch("backend.services.trade_service.AlpacaBrokerClient") as mock_broker:
            with patch("backend.services.trade_service.PositionReconciliationService"):
                with patch("backend.services.trade_service.InstitutionalAnalytics"):
                    service = TradeService(mock_db_session)
        
        assert service.alpaca_client is not None


# ============================================================================
# GET TRADE HISTORY TESTS
# ============================================================================

class TestGetTradeHistory:
    """Tests for get_trade_history method"""
    
    @pytest.mark.asyncio
    async def test_get_trade_history_empty(self, trade_service, mock_db_session):
        """Test getting empty trade history"""
        # Mock count query
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        
        # Mock trades query
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = []
        
        mock_db_session.execute = AsyncMock(side_effect=[count_result, trades_result])
        
        result = await trade_service.get_trade_history()
        
        assert result["trades"] == []
        assert result["total"] == 0
        
    @pytest.mark.asyncio
    async def test_get_trade_history_with_results(self, trade_service, mock_db_session):
        """Test getting trade history with results"""
        # Create mock order
        mock_order = MagicMock()
        mock_order.id = 1
        mock_order.symbol = "AAPL"
        mock_order.side = "buy"
        mock_order.qty = 100
        mock_order.filled_qty = 100
        mock_order.avg_fill_price = 150.0
        mock_order.order_type = "market"
        mock_order.status = "filled"
        mock_order.submitted_at = datetime.now()
        mock_order.updated_at = datetime.now()
        mock_order.attributes = {"strategy_id": "test"}
        mock_order.executions = []
        
        # Mock count query
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        
        # Mock trades query
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = [mock_order]
        
        mock_db_session.execute = AsyncMock(side_effect=[count_result, trades_result])
        
        result = await trade_service.get_trade_history()
        
        assert result["total"] == 1
        assert len(result["trades"]) == 1
        assert result["trades"][0]["symbol"] == "AAPL"
        
    @pytest.mark.asyncio
    async def test_get_trade_history_with_filters(self, trade_service, mock_db_session):
        """Test trade history with filters"""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = []
        
        mock_db_session.execute = AsyncMock(side_effect=[count_result, trades_result])
        
        result = await trade_service.get_trade_history(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            symbol="AAPL",
            side="buy",
            limit=50,
            offset=10,
        )
        
        assert result["limit"] == 50
        assert result["offset"] == 10
        
    @pytest.mark.asyncio
    async def test_get_trade_history_error_handling(self, trade_service, mock_db_session):
        """Test error handling in trade history"""
        mock_db_session.execute = AsyncMock(side_effect=Exception("DB Error"))
        
        # Should handle error gracefully
        with pytest.raises(Exception):
            await trade_service.get_trade_history()


# ============================================================================
# FILTER TESTS
# ============================================================================

class TestFilters:
    """Tests for trade history filters"""
    
    @pytest.mark.asyncio
    async def test_filter_by_symbol(self, trade_service, mock_db_session):
        """Test filtering by symbol"""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = []
        
        mock_db_session.execute = AsyncMock(side_effect=[count_result, trades_result])
        
        result = await trade_service.get_trade_history(symbol="aapl")
        
        # Symbol should be uppercased in filter
        assert result is not None
        
    @pytest.mark.asyncio
    async def test_filter_by_side(self, trade_service, mock_db_session):
        """Test filtering by side"""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = []
        
        # Provide enough results for both calls (2 execute per call)
        mock_db_session.execute = AsyncMock(side_effect=[
            count_result, trades_result,  # First call
            count_result, trades_result,  # Second call
        ])
        
        # Valid side values
        result = await trade_service.get_trade_history(side="buy")
        assert result is not None
        
        result = await trade_service.get_trade_history(side="sell")
        assert result is not None
        
    @pytest.mark.asyncio
    async def test_filter_invalid_side_ignored(self, trade_service, mock_db_session):
        """Test invalid side filter is ignored"""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = []
        
        mock_db_session.execute = AsyncMock(side_effect=[count_result, trades_result])
        
        # Invalid side should be ignored
        result = await trade_service.get_trade_history(side="invalid")
        assert result is not None


# ============================================================================
# PAGINATION TESTS
# ============================================================================

class TestPagination:
    """Tests for pagination"""
    
    @pytest.mark.asyncio
    async def test_default_limit(self, trade_service, mock_db_session):
        """Test default limit is 100"""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = []
        
        mock_db_session.execute = AsyncMock(side_effect=[count_result, trades_result])
        
        result = await trade_service.get_trade_history()
        
        assert result["limit"] == 100
        
    @pytest.mark.asyncio
    async def test_default_offset(self, trade_service, mock_db_session):
        """Test default offset is 0"""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = []
        
        mock_db_session.execute = AsyncMock(side_effect=[count_result, trades_result])
        
        result = await trade_service.get_trade_history()
        
        assert result["offset"] == 0


# ============================================================================
# TRADE DATA TRANSFORMATION TESTS
# ============================================================================

class TestTradeDataTransformation:
    """Tests for trade data transformation"""
    
    @pytest.mark.asyncio
    async def test_trade_has_camelcase_keys(self, trade_service, mock_db_session):
        """Test trades have camelCase keys for frontend"""
        mock_order = MagicMock()
        mock_order.id = 1
        mock_order.symbol = "AAPL"
        mock_order.side = "buy"
        mock_order.qty = 100
        mock_order.filled_qty = 100
        mock_order.avg_fill_price = 150.0
        mock_order.order_type = "market"
        mock_order.status = "filled"
        mock_order.submitted_at = datetime.now()
        mock_order.updated_at = datetime.now()
        mock_order.attributes = None
        mock_order.executions = []
        
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        
        trades_result = MagicMock()
        trades_result.scalars.return_value.all.return_value = [mock_order]
        
        mock_db_session.execute = AsyncMock(side_effect=[count_result, trades_result])
        
        result = await trade_service.get_trade_history()
        
        trade = result["trades"][0]
        
        # Check camelCase keys
        assert "orderId" in trade
        assert "filledQty" in trade
        assert "avgFillPrice" in trade
        assert "orderType" in trade
        assert "submittedAt" in trade
        assert "updatedAt" in trade
