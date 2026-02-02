"""
Comprehensive tests for backend.services.positions_service

Targets 70%+ coverage for PositionsService which:
- Manages portfolio positions via Alpaca API
- Provides position queries (single, multiple, all)
- Tracks portfolio value and buying power
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.services.positions_service import (
    PositionsService,
    create_positions_service,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_position():
    """Create a mock Alpaca Position object"""
    position = MagicMock()
    position.symbol = "AAPL"
    position.qty = "100"
    position.market_value = "15000.00"
    position.cost_basis = "14000.00"
    position.unrealized_pl = "1000.00"
    position.avg_entry_price = "140.00"
    return position


@pytest.fixture
def mock_positions():
    """Create multiple mock positions"""
    positions = []
    for symbol, qty, value in [
        ("AAPL", "100", "15000.00"),
        ("MSFT", "50", "20000.00"),
        ("GOOGL", "10", "13500.00"),
    ]:
        pos = MagicMock()
        pos.symbol = symbol
        pos.qty = qty
        pos.market_value = value
        pos.cost_basis = str(float(value) - 500)
        pos.unrealized_pl = "500.00"
        pos.avg_entry_price = str(float(value) / float(qty))
        positions.append(pos)
    return positions


@pytest.fixture
def mock_trading_client(mock_positions):
    """Create mock trading client"""
    client = MagicMock()
    client.get_all_positions.return_value = mock_positions
    
    account = MagicMock()
    account.portfolio_value = "100000.00"
    account.buying_power = "50000.00"
    client.get_account.return_value = account
    
    return client


@pytest.fixture
def positions_service(mock_trading_client):
    """Create PositionsService with mock client"""
    return PositionsService(trading_client=mock_trading_client)


@pytest.fixture
def positions_service_no_client():
    """Create PositionsService without trading client"""
    return PositionsService(trading_client=None)


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestPositionsServiceInit:
    """Tests for PositionsService initialization"""
    
    def test_init_with_client(self, mock_trading_client):
        """Test initialization with trading client"""
        service = PositionsService(trading_client=mock_trading_client)
        
        assert service.trading_client is mock_trading_client
        assert service._positions_cache == {}
        assert service._cache_timestamp is None
        
    def test_init_without_client(self):
        """Test initialization without trading client"""
        service = PositionsService(trading_client=None)
        
        assert service.trading_client is None
        assert service._positions_cache == {}


# ============================================================================
# GET POSITIONS BY SYMBOLS TESTS
# ============================================================================

class TestGetPositionsBySymbols:
    """Tests for get_positions_by_symbols method"""
    
    @pytest.mark.asyncio
    async def test_get_positions_for_held_symbols(self, positions_service, mock_trading_client):
        """Test getting positions for symbols we hold"""
        result = await positions_service.get_positions_by_symbols(["AAPL", "MSFT"])
        
        assert "AAPL" in result
        assert "MSFT" in result
        assert result["AAPL"]["qty"] == 100.0
        assert result["MSFT"]["qty"] == 50.0
        
    @pytest.mark.asyncio
    async def test_get_positions_for_unheld_symbols(self, positions_service):
        """Test getting positions for symbols we don't hold"""
        result = await positions_service.get_positions_by_symbols(["TSLA", "NVDA"])
        
        assert "TSLA" in result
        assert "NVDA" in result
        assert result["TSLA"]["qty"] == 0.0
        assert result["NVDA"]["qty"] == 0.0
        assert result["TSLA"]["side"] is None
        
    @pytest.mark.asyncio
    async def test_get_positions_mixed(self, positions_service):
        """Test getting positions for mix of held and unheld symbols"""
        result = await positions_service.get_positions_by_symbols(["AAPL", "TSLA"])
        
        assert result["AAPL"]["qty"] == 100.0
        assert result["AAPL"]["side"] == "long"
        assert result["TSLA"]["qty"] == 0.0
        assert result["TSLA"]["side"] is None
        
    @pytest.mark.asyncio
    async def test_get_positions_no_client(self, positions_service_no_client):
        """Test with no trading client"""
        result = await positions_service_no_client.get_positions_by_symbols(["AAPL"])
        
        assert result == {}
        
    @pytest.mark.asyncio
    async def test_get_positions_api_error(self, positions_service, mock_trading_client):
        """Test handling API error"""
        mock_trading_client.get_all_positions.side_effect = Exception("API Error")
        
        result = await positions_service.get_positions_by_symbols(["AAPL"])
        
        # Should return empty position for symbol
        assert "AAPL" in result
        assert result["AAPL"]["qty"] == 0.0


# ============================================================================
# GET ALL POSITIONS TESTS
# ============================================================================

class TestGetAllPositions:
    """Tests for get_all_positions method"""
    
    @pytest.mark.asyncio
    async def test_get_all_positions(self, positions_service):
        """Test getting all positions"""
        result = await positions_service.get_all_positions()
        
        assert len(result) == 3
        assert "AAPL" in result
        assert "MSFT" in result
        assert "GOOGL" in result
        
    @pytest.mark.asyncio
    async def test_get_all_positions_no_client(self, positions_service_no_client):
        """Test with no trading client"""
        result = await positions_service_no_client.get_all_positions()
        
        assert result == {}
        
    @pytest.mark.asyncio
    async def test_get_all_positions_api_error(self, positions_service, mock_trading_client):
        """Test handling API error"""
        mock_trading_client.get_all_positions.side_effect = Exception("API Error")
        
        result = await positions_service.get_all_positions()
        
        assert result == {}


# ============================================================================
# GET SINGLE POSITION TESTS
# ============================================================================

class TestGetPosition:
    """Tests for get_position method"""
    
    @pytest.mark.asyncio
    async def test_get_position_exists(self, positions_service, mock_trading_client, mock_position):
        """Test getting a position that exists"""
        mock_trading_client.get_open_position.return_value = mock_position
        
        result = await positions_service.get_position("AAPL")
        
        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["qty"] == 100.0
        assert result["side"] == "long"
        
    @pytest.mark.asyncio
    async def test_get_position_not_exists(self, positions_service, mock_trading_client):
        """Test getting a position that doesn't exist"""
        mock_trading_client.get_open_position.side_effect = Exception("No position")
        
        result = await positions_service.get_position("TSLA")
        
        assert result is None
        
    @pytest.mark.asyncio
    async def test_get_position_no_client(self, positions_service_no_client):
        """Test with no trading client"""
        result = await positions_service_no_client.get_position("AAPL")
        
        assert result is None
        
    @pytest.mark.asyncio
    async def test_get_position_short(self, positions_service, mock_trading_client):
        """Test getting a short position"""
        short_position = MagicMock()
        short_position.symbol = "TSLA"
        short_position.qty = "-50"
        short_position.market_value = "-10000.00"
        short_position.cost_basis = "-9500.00"
        short_position.unrealized_pl = "-500.00"
        short_position.avg_entry_price = "190.00"
        mock_trading_client.get_open_position.return_value = short_position
        
        result = await positions_service.get_position("TSLA")
        
        assert result["side"] == "short"
        assert result["qty"] == -50.0


# ============================================================================
# PORTFOLIO VALUE TESTS
# ============================================================================

class TestGetTotalPortfolioValue:
    """Tests for get_total_portfolio_value method"""
    
    @pytest.mark.asyncio
    async def test_get_portfolio_value(self, positions_service):
        """Test getting total portfolio value"""
        result = await positions_service.get_total_portfolio_value()
        
        assert result == 100000.0
        
    @pytest.mark.asyncio
    async def test_get_portfolio_value_no_client(self, positions_service_no_client):
        """Test with no trading client"""
        result = await positions_service_no_client.get_total_portfolio_value()
        
        assert result == 0.0
        
    @pytest.mark.asyncio
    async def test_get_portfolio_value_api_error(self, positions_service, mock_trading_client):
        """Test handling API error"""
        mock_trading_client.get_account.side_effect = Exception("API Error")
        
        result = await positions_service.get_total_portfolio_value()
        
        assert result == 0.0


# ============================================================================
# BUYING POWER TESTS
# ============================================================================

class TestGetBuyingPower:
    """Tests for get_buying_power method"""
    
    @pytest.mark.asyncio
    async def test_get_buying_power(self, positions_service):
        """Test getting buying power"""
        result = await positions_service.get_buying_power()
        
        assert result == 50000.0
        
    @pytest.mark.asyncio
    async def test_get_buying_power_no_client(self, positions_service_no_client):
        """Test with no trading client"""
        result = await positions_service_no_client.get_buying_power()
        
        assert result == 0.0
        
    @pytest.mark.asyncio
    async def test_get_buying_power_api_error(self, positions_service, mock_trading_client):
        """Test handling API error"""
        mock_trading_client.get_account.side_effect = Exception("API Error")
        
        result = await positions_service.get_buying_power()
        
        assert result == 0.0


# ============================================================================
# FACTORY FUNCTION TESTS
# ============================================================================

class TestCreatePositionsService:
    """Tests for create_positions_service factory function"""
    
    def test_create_with_client(self, mock_trading_client):
        """Test factory with trading client"""
        service = create_positions_service(trading_client=mock_trading_client)
        
        assert isinstance(service, PositionsService)
        assert service.trading_client is mock_trading_client
        
    def test_create_without_client(self):
        """Test factory without trading client"""
        service = create_positions_service()
        
        assert isinstance(service, PositionsService)
        assert service.trading_client is None


# ============================================================================
# POSITION DATA STRUCTURE TESTS
# ============================================================================

class TestPositionDataStructure:
    """Tests for position data structure"""
    
    @pytest.mark.asyncio
    async def test_position_has_all_fields(self, positions_service, mock_trading_client, mock_position):
        """Test position data has all required fields"""
        mock_trading_client.get_open_position.return_value = mock_position
        
        result = await positions_service.get_position("AAPL")
        
        required_fields = ['symbol', 'qty', 'side', 'market_value', 'cost_basis', 'unrealized_pl', 'avg_entry_price']
        for field in required_fields:
            assert field in result
            
    @pytest.mark.asyncio
    async def test_empty_position_structure(self, positions_service):
        """Test empty position has correct structure"""
        result = await positions_service.get_positions_by_symbols(["NONEXISTENT"])
        
        pos = result["NONEXISTENT"]
        assert pos["symbol"] == "NONEXISTENT"
        assert pos["qty"] == 0.0
        assert pos["side"] is None
        assert pos["market_value"] == 0.0
        assert pos["cost_basis"] == 0.0
        assert pos["unrealized_pl"] == 0.0
        assert pos["avg_entry_price"] == 0.0
