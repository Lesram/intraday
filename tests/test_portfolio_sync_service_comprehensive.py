"""
Comprehensive tests for PortfolioSyncService
Tests Alpaca portfolio sync to local database
"""

import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.portfolio_sync_service import (
    PortfolioSyncService,
    get_portfolio_sync_service,
)


class TestPortfolioSyncServiceInit:
    """Test PortfolioSyncService initialization"""
    
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    def test_init_gets_broker_client(self, mock_get_client):
        """Test initialization gets broker client"""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        
        service = PortfolioSyncService()
        
        assert service.broker_client == mock_client
        mock_get_client.assert_called_once()


class TestSyncPositions:
    """Test sync_positions method"""
    
    @pytest.fixture
    def mock_session(self):
        """Create mock async database session"""
        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.rollback = AsyncMock()
        return mock_db
        
    @pytest.fixture
    def mock_broker_client(self):
        """Create mock broker client"""
        mock_client = MagicMock()
        mock_client.get_account = AsyncMock(return_value={
            "cash": "50000.00",
            "equity": "100000.00",
            "portfolio_value": "100000.00",
            "buying_power": "200000.00"
        })
        mock_client.get_positions = AsyncMock(return_value=[])
        return mock_client
        
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    @pytest.mark.asyncio
    async def test_sync_empty_positions(self, mock_get_client, mock_session, mock_broker_client):
        """Test sync with no positions"""
        mock_get_client.return_value = mock_broker_client
        mock_broker_client.get_positions = AsyncMock(return_value=[])
        
        service = PortfolioSyncService()
        positions, account_data = await service.sync_positions(mock_session)
        
        assert positions == []
        assert "cash" in account_data
        mock_session.commit.assert_called_once()
        
    @patch("backend.services.portfolio_sync_service.delete")
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    @pytest.mark.asyncio
    async def test_sync_with_positions(self, mock_get_client, mock_delete, mock_session, mock_broker_client):
        """Test sync with existing positions"""
        mock_get_client.return_value = mock_broker_client
        mock_broker_client.get_positions = AsyncMock(return_value=[
            {"symbol": "AAPL", "qty": "100", "avg_entry_price": "150.00"},
            {"symbol": "MSFT", "qty": "50", "avg_entry_price": "300.00"},
        ])
        mock_delete.return_value = MagicMock()
        
        with patch("backend.services.portfolio_sync_service.Position") as MockPosition:
            MockPosition.return_value = MagicMock()
            
            service = PortfolioSyncService()
            positions, account_data = await service.sync_positions(mock_session)
            
        # Should add 2 positions
        assert mock_session.add.call_count == 2
        mock_session.commit.assert_called_once()
        
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    @pytest.mark.asyncio
    async def test_sync_deletes_existing_positions(self, mock_get_client, mock_session, mock_broker_client):
        """Test sync deletes existing positions first"""
        mock_get_client.return_value = mock_broker_client
        
        service = PortfolioSyncService()
        await service.sync_positions(mock_session)
        
        # Should call execute with delete statement
        mock_session.execute.assert_called()
        
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    @pytest.mark.asyncio
    async def test_sync_rollback_on_error(self, mock_get_client, mock_session, mock_broker_client):
        """Test sync rolls back on error"""
        mock_get_client.return_value = mock_broker_client
        mock_broker_client.get_account = AsyncMock(side_effect=Exception("API error"))
        
        service = PortfolioSyncService()
        
        with pytest.raises(Exception):
            await service.sync_positions(mock_session)
            
        mock_session.rollback.assert_called_once()


class TestSyncFullPortfolio:
    """Test sync_full_portfolio method"""
    
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    @patch("backend.services.portfolio_sync_service.get_session_context")
    @pytest.mark.asyncio
    async def test_full_sync_success(self, mock_get_session, mock_get_client):
        """Test successful full portfolio sync"""
        # Mock session context
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context
        
        # Mock broker client
        mock_client = MagicMock()
        mock_client.get_account = AsyncMock(return_value={
            "cash": "50000.00",
            "equity": "100000.00",
            "last_equity": "99000.00",
            "buying_power": "200000.00"
        })
        mock_client.get_positions = AsyncMock(return_value=[])
        mock_get_client.return_value = mock_client
        
        service = PortfolioSyncService()
        result = await service.sync_full_portfolio(user_id="user-123")
        
        assert result["success"] == True
        assert result["user_id"] == "user-123"
        assert "portfolio" in result
        assert "synced_at" in result
        
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    @patch("backend.services.portfolio_sync_service.get_session_context")
    @pytest.mark.asyncio
    async def test_full_sync_failure(self, mock_get_session, mock_get_client):
        """Test failed full portfolio sync"""
        # Mock session that raises error
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=Exception("DB error"))
        mock_session.rollback = AsyncMock()
        
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context
        
        mock_client = MagicMock()
        mock_client.get_account = AsyncMock(side_effect=Exception("API error"))
        mock_get_client.return_value = mock_client
        
        service = PortfolioSyncService()
        result = await service.sync_full_portfolio()
        
        assert result["success"] == False
        assert "error" in result
        
    @patch("backend.services.portfolio_sync_service.delete")
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    @patch("backend.services.portfolio_sync_service.get_session_context")
    @pytest.mark.asyncio
    async def test_full_sync_with_positions(self, mock_get_session, mock_get_client, mock_delete):
        """Test full sync returns position details"""
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_delete.return_value = MagicMock()
        
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context
        
        mock_client = MagicMock()
        mock_client.get_account = AsyncMock(return_value={
            "cash": "50000.00",
            "equity": "100000.00",
            "last_equity": "99000.00",
            "buying_power": "200000.00"
        })
        
        # Return positions
        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.qty = Decimal("100")
        mock_position.avg_price = Decimal("150.00")
        
        mock_client.get_positions = AsyncMock(return_value=[
            {"symbol": "AAPL", "qty": "100", "avg_entry_price": "150.00"}
        ])
        mock_get_client.return_value = mock_client
        
        with patch("backend.services.portfolio_sync_service.Position") as MockPosition:
            MockPosition.return_value = mock_position
            
            service = PortfolioSyncService()
            result = await service.sync_full_portfolio()
        
        assert result["success"] == True
        assert len(result["positions"]) == 1
        assert result["positions"][0]["symbol"] == "AAPL"


class TestGetPortfolioSyncService:
    """Test singleton getter function"""
    
    @patch("backend.services.portfolio_sync_service._sync_service", None)
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    def test_creates_instance_if_none(self, mock_get_client):
        """Test creates new instance if none exists"""
        mock_get_client.return_value = MagicMock()
        
        service = get_portfolio_sync_service()
        
        assert service is not None
        assert isinstance(service, PortfolioSyncService)
        
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    def test_returns_same_instance(self, mock_get_client):
        """Test returns same instance on subsequent calls"""
        mock_get_client.return_value = MagicMock()
        
        # Reset global
        import backend.services.portfolio_sync_service as module
        module._sync_service = None
        
        service1 = get_portfolio_sync_service()
        service2 = get_portfolio_sync_service()
        
        assert service1 is service2


class TestPositionDataMapping:
    """Test position data mapping from Alpaca"""
    
    @patch("backend.services.portfolio_sync_service.delete")
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    @pytest.mark.asyncio
    async def test_position_qty_converted_to_decimal(self, mock_get_client, mock_delete):
        """Test qty string converted to Decimal"""
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_delete.return_value = MagicMock()
        
        mock_client = MagicMock()
        mock_client.get_account = AsyncMock(return_value={"cash": "100"})
        mock_client.get_positions = AsyncMock(return_value=[
            {"symbol": "TEST", "qty": "123.456", "avg_entry_price": "100.00"}
        ])
        mock_get_client.return_value = mock_client
        
        with patch("backend.services.portfolio_sync_service.Position") as MockPosition:
            MockPosition.return_value = MagicMock()
            
            service = PortfolioSyncService()
            await service.sync_positions(mock_session)
            
            # Check Position was called with Decimal qty
            call_kwargs = MockPosition.call_args.kwargs
            assert isinstance(call_kwargs["qty"], Decimal)
            assert call_kwargs["qty"] == Decimal("123.456")
            
    @patch("backend.services.portfolio_sync_service.delete")
    @patch("backend.services.portfolio_sync_service.get_alpaca_broker_client")
    @pytest.mark.asyncio
    async def test_position_avg_price_converted(self, mock_get_client, mock_delete):
        """Test avg_entry_price converted to Decimal"""
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_delete.return_value = MagicMock()
        
        mock_client = MagicMock()
        mock_client.get_account = AsyncMock(return_value={"cash": "100"})
        mock_client.get_positions = AsyncMock(return_value=[
            {"symbol": "TEST", "qty": "10", "avg_entry_price": "99.99"}
        ])
        mock_get_client.return_value = mock_client
        
        with patch("backend.services.portfolio_sync_service.Position") as MockPosition:
            MockPosition.return_value = MagicMock()
            
            service = PortfolioSyncService()
            await service.sync_positions(mock_session)
            
            call_kwargs = MockPosition.call_args.kwargs
            assert isinstance(call_kwargs["avg_price"], Decimal)
            assert call_kwargs["avg_price"] == Decimal("99.99")
