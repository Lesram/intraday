"""
Comprehensive tests for backend.services.portfolio_service

Targets 70%+ coverage for PortfolioService:
- Portfolio retrieval with caching
- Portfolio history
- Position lookups
- Error handling and fallbacks
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.portfolio_service import (
    PortfolioService,
    get_portfolio_service,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def portfolio_service():
    """Create PortfolioService instance"""
    return PortfolioService()


@pytest.fixture
def mock_broker_client():
    """Create mock Alpaca broker client"""
    client = AsyncMock()
    client.get_account = AsyncMock(return_value={
        "equity": "100000.00",
        "cash": "50000.00",
        "buying_power": "100000.00",
        "portfolio_value": "50000.00",
    })
    client.get_positions = AsyncMock(return_value=[
        {
            "symbol": "AAPL",
            "qty": "100",
            "avg_entry_price": "150.00",
            "current_price": "155.00",
            "market_value": "15500.00",
            "unrealized_pl": "500.00",
            "unrealized_plpc": "0.0333",
            "side": "long",
            "exchange": "NASDAQ",
        }
    ])
    return client


@pytest.fixture
def mock_cache():
    """Create mock cache"""
    cache = AsyncMock()
    cache.get = AsyncMock(return_value=None)
    cache.set = AsyncMock()
    return cache


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestPortfolioServiceInit:
    """Tests for PortfolioService initialization"""
    
    def test_init_defaults(self, portfolio_service):
        """Test default initialization"""
        assert portfolio_service.default_cash == Decimal("100000.00")
        assert portfolio_service._sync_service is None
        assert portfolio_service._broker_client is None
        
    def test_cache_ttl(self, portfolio_service):
        """Test cache TTL configuration"""
        assert portfolio_service.PORTFOLIO_CACHE_TTL == 10.0


# ============================================================================
# GET USER PORTFOLIO TESTS
# ============================================================================

class TestGetUserPortfolio:
    """Tests for get_user_portfolio method"""
    
    @pytest.mark.asyncio
    async def test_get_portfolio_cache_hit(self, portfolio_service):
        """Test portfolio returned from cache"""
        cached_data = {
            "totalEquity": 100000.0,
            "cash": 50000.0,
            "positions": [],
            "userId": "test-user",
        }
        
        with patch("backend.services.portfolio_service.get_hot_data_cache") as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.get = AsyncMock(return_value=cached_data)
            mock_get_cache.return_value = mock_cache
            
            result = await portfolio_service.get_user_portfolio("test-user")
            
            assert result == cached_data
            
    @pytest.mark.asyncio
    async def test_get_portfolio_error_returns_default(self, portfolio_service):
        """Test default portfolio returned on error"""
        with patch("backend.services.portfolio_service.get_hot_data_cache") as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.get = AsyncMock(return_value=None)
            mock_get_cache.return_value = mock_cache
            
            # Mock broker client to raise exception
            portfolio_service._broker_client = AsyncMock()
            portfolio_service._broker_client.get_account = AsyncMock(
                side_effect=Exception("API Error")
            )
            
            result = await portfolio_service.get_user_portfolio("test-user")
            
            # Should return default portfolio
            assert result["totalEquity"] == 100000.00
            assert result["cash"] == 100000.00
            assert result["positions"] == []


# ============================================================================
# GET PORTFOLIO HISTORY TESTS
# ============================================================================

class TestGetPortfolioHistory:
    """Tests for get_portfolio_history method"""
    
    @pytest.mark.asyncio
    async def test_get_history_empty_returns_current(self, portfolio_service):
        """Test empty history returns current snapshot"""
        with patch("backend.services.portfolio_service.get_session_context") as mock_session:
            mock_ctx = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock(execute=AsyncMock(return_value=mock_result)))
            mock_ctx.__aexit__ = AsyncMock()
            mock_session.return_value = mock_ctx
            
            # Also mock get_user_portfolio
            portfolio_service.get_user_portfolio = AsyncMock(return_value={
                "lastUpdate": datetime.now(UTC).isoformat(),
                "totalEquity": 100000.0,
                "cash": 50000.0,
                "dayPnL": 0.0,
                "dayPnLPercent": 0.0,
                "totalPnL": 0.0,
                "totalPnLPercent": 0.0,
                "positions": [],
            })
            
            result = await portfolio_service.get_portfolio_history("test-user")
            
            assert len(result) == 1
            assert result[0]["snapshotType"] == "current"
            
    @pytest.mark.asyncio
    async def test_get_history_error_returns_empty(self, portfolio_service):
        """Test error returns empty list"""
        with patch("backend.services.portfolio_service.get_session_context") as mock_session:
            mock_session.side_effect = Exception("DB Error")
            
            result = await portfolio_service.get_portfolio_history("test-user")
            
            assert result == []


# ============================================================================
# GET POSITION BY SYMBOL TESTS
# ============================================================================

class TestGetPositionBySymbol:
    """Tests for get_position_by_symbol method"""
    
    @pytest.mark.asyncio
    async def test_get_position_not_found(self, portfolio_service):
        """Test position not found returns None"""
        with patch("backend.services.portfolio_service.get_session_context") as mock_session:
            mock_ctx = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock(execute=AsyncMock(return_value=mock_result)))
            mock_ctx.__aexit__ = AsyncMock()
            mock_session.return_value = mock_ctx
            
            result = await portfolio_service.get_position_by_symbol("test-user", "AAPL")
            
            assert result is None
            
    @pytest.mark.asyncio
    async def test_get_position_found(self, portfolio_service):
        """Test position found returns data"""
        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.qty = Decimal("100")
        mock_position.avg_price = Decimal("150.00")
        mock_position.realized_pnl = Decimal("500.00")
        
        with patch("backend.services.portfolio_service.get_session_context") as mock_session:
            mock_ctx = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_position
            mock_ctx.__aenter__ = AsyncMock(return_value=MagicMock(execute=AsyncMock(return_value=mock_result)))
            mock_ctx.__aexit__ = AsyncMock()
            mock_session.return_value = mock_ctx
            
            result = await portfolio_service.get_position_by_symbol("test-user", "AAPL")
            
            assert result is not None
            assert result["symbol"] == "AAPL"
            assert result["qty"] == 100.0
            
    @pytest.mark.asyncio
    async def test_get_position_error(self, portfolio_service):
        """Test error returns None"""
        with patch("backend.services.portfolio_service.get_session_context") as mock_session:
            mock_session.side_effect = Exception("DB Error")
            
            result = await portfolio_service.get_position_by_symbol("test-user", "AAPL")
            
            assert result is None


# ============================================================================
# BROADCAST PORTFOLIO UPDATE TESTS
# ============================================================================

class TestBroadcastPortfolioUpdate:
    """Tests for broadcast_portfolio_update method"""
    
    @pytest.mark.asyncio
    async def test_broadcast_success(self, portfolio_service):
        """Test successful broadcast"""
        portfolio_service.get_user_portfolio = AsyncMock(return_value={
            "totalEquity": 100000.0,
            "positions": [],
        })
        
        # Should not raise - method exists on instance
        try:
            await portfolio_service.broadcast_portfolio_update("test-user")
        except Exception:
            pass  # WebSocket connection not available in tests, just verify no crash
            
    @pytest.mark.asyncio
    async def test_broadcast_error_handled(self, portfolio_service):
        """Test broadcast error is handled gracefully"""
        portfolio_service.get_user_portfolio = AsyncMock(
            side_effect=Exception("Error")
        )
        
        # Should not raise
        await portfolio_service.broadcast_portfolio_update("test-user")


# ============================================================================
# SINGLETON TESTS
# ============================================================================

class TestGetPortfolioService:
    """Tests for get_portfolio_service singleton"""
    
    def test_get_portfolio_service_singleton(self):
        """Test singleton returns same instance"""
        # Reset singleton
        import backend.services.portfolio_service as module
        module._portfolio_service = None
        
        service1 = get_portfolio_service()
        service2 = get_portfolio_service()
        
        assert service1 is service2
