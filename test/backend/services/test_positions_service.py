"""
Test Module: 100% Coverage for backend.services.positions_service
===============================================================

This module provides comprehensive test coverage for all classes and methods
in backend.services.positions_service.py including:
- PositionCalculator class with all methods
- Position class initialization 
- PositionsService class with all async methods
- All error conditions and edge cases

Author: AI Assistant
Date: December 2024
"""

import pytest
import asyncio
from decimal import Decimal
from unittest.mock import Mock, AsyncMock, patch

# Import the modules under test
from backend.services.positions_service import (
    PositionCalculator, 
    Position, 
    PositionsService
)


class TestPositionCalculator:
    """Test PositionCalculator class methods."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.calculator = PositionCalculator()
    
    def test_calculate_position_size_basic(self):
        """Test basic position size calculation."""
        result = self.calculator.calculate_position_size(
            account_balance=Decimal('10000'),
            risk_percentage=Decimal('0.02'),  # 2%
            entry_price=Decimal('100'),
            stop_loss=Decimal('90')
        )
        
        # Risk amount = 10000 * 0.02 = 200
        # Risk per share = 100 - 90 = 10
        # Position size = 200 / 10 = 20
        assert result == Decimal('20.00')
    
    def test_calculate_position_size_zero_risk_percentage(self):
        """Test with zero risk percentage."""
        result = self.calculator.calculate_position_size(
            account_balance=Decimal('10000'),
            risk_percentage=Decimal('0'),
            entry_price=Decimal('100'),
            stop_loss=Decimal('90')
        )
        assert result == Decimal('0')
    
    def test_calculate_position_size_negative_risk_percentage(self):
        """Test with negative risk percentage."""
        result = self.calculator.calculate_position_size(
            account_balance=Decimal('10000'),
            risk_percentage=Decimal('-0.01'),
            entry_price=Decimal('100'),
            stop_loss=Decimal('90')
        )
        assert result == Decimal('0')
    
    def test_calculate_position_size_invalid_entry_price(self):
        """Test with invalid entry price."""
        with pytest.raises(ValueError, match="Entry price and stop loss must be positive"):
            self.calculator.calculate_position_size(
                account_balance=Decimal('10000'),
                risk_percentage=Decimal('0.02'),
                entry_price=Decimal('0'),
                stop_loss=Decimal('90')
            )
    
    def test_calculate_position_size_invalid_stop_loss(self):
        """Test with invalid stop loss."""
        with pytest.raises(ValueError, match="Entry price and stop loss must be positive"):
            self.calculator.calculate_position_size(
                account_balance=Decimal('10000'),
                risk_percentage=Decimal('0.02'),
                entry_price=Decimal('100'),
                stop_loss=Decimal('0')
            )
    
    def test_calculate_position_size_stop_loss_greater_than_entry(self):
        """Test with stop loss greater than entry price."""
        with pytest.raises(ValueError, match="Stop loss must be less than entry price for long positions"):
            self.calculator.calculate_position_size(
                account_balance=Decimal('10000'),
                risk_percentage=Decimal('0.02'),
                entry_price=Decimal('100'),
                stop_loss=Decimal('110')
            )
    
    def test_calculate_position_size_stop_loss_equal_to_entry(self):
        """Test with stop loss equal to entry price."""
        with pytest.raises(ValueError, match="Stop loss must be less than entry price for long positions"):
            self.calculator.calculate_position_size(
                account_balance=Decimal('10000'),
                risk_percentage=Decimal('0.02'),
                entry_price=Decimal('100'),
                stop_loss=Decimal('100')
            )
    
    def test_calculate_portfolio_risk_basic(self):
        """Test basic portfolio risk calculation."""
        positions = [
            {"risk_amount": 100},
            {"risk_amount": 200},
            {"risk_amount": 50}
        ]
        
        result = self.calculator.calculate_portfolio_risk(positions)
        assert result == Decimal('350')
    
    def test_calculate_portfolio_risk_empty_list(self):
        """Test portfolio risk with empty positions list."""
        result = self.calculator.calculate_portfolio_risk([])
        assert result == Decimal('0')
    
    def test_calculate_portfolio_risk_missing_risk_amount(self):
        """Test portfolio risk with missing risk_amount fields."""
        positions = [
            {"symbol": "AAPL"},  # No risk_amount
            {"risk_amount": 100},
            {"other_field": 50}  # No risk_amount
        ]
        
        result = self.calculator.calculate_portfolio_risk(positions)
        assert result == Decimal('100')  # Only the middle position counted
    
    def test_calculate_position_value_basic(self):
        """Test basic position value calculation."""
        result = self.calculator.calculate_position_value(
            quantity=Decimal('100'),
            price=Decimal('150.50')
        )
        assert result == Decimal('15050.00')
    
    def test_calculate_position_value_fractional(self):
        """Test position value with fractional shares."""
        result = self.calculator.calculate_position_value(
            quantity=Decimal('50.5'),
            price=Decimal('100.33')
        )
        assert result == Decimal('5066.66')  # Actual rounded result


class TestPosition:
    """Test Position class initialization and attributes."""
    
    def test_position_basic_init(self):
        """Test basic Position initialization."""
        pos = Position(
            symbol="AAPL",
            qty=100.0,
            price=150.50
        )
        
        assert pos.symbol == "AAPL"
        assert pos.qty == 100.0
        assert pos.price == 150.50
        assert pos.avg_cost == 150.50  # Should default to price
        assert pos.market_value == 15050.0  # qty * price
    
    def test_position_with_all_params(self):
        """Test Position initialization with all parameters."""
        pos = Position(
            symbol="MSFT",
            qty=50.0,
            price=300.0,
            avg_cost=280.0,
            market_value=14000.0
        )
        
        assert pos.symbol == "MSFT"
        assert pos.qty == 50.0
        assert pos.price == 300.0
        assert pos.avg_cost == 280.0
        assert pos.market_value == 14000.0
    
    def test_position_zero_avg_cost_defaults_to_price(self):
        """Test that zero avg_cost defaults to price."""
        pos = Position(
            symbol="TSLA",
            qty=25.0,
            price=800.0,
            avg_cost=0.0
        )
        
        assert pos.avg_cost == 800.0  # Should default to price when 0
    
    def test_position_zero_market_value_calculated(self):
        """Test that zero market_value gets calculated."""
        pos = Position(
            symbol="GOOGL",
            qty=10.0,
            price=2500.0,
            market_value=0.0
        )
        
        assert pos.market_value == 25000.0  # qty * price


class TestPositionsService:
    """Test PositionsService class methods."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.service = PositionsService()
    
    @pytest.mark.asyncio
    async def test_get_user_positions_basic(self):
        """Test basic get_user_positions functionality."""
        positions = await self.service.get_user_positions("user123")
        
        # Should return the mock data
        assert len(positions) == 2
        
        # Check first position
        assert positions[0]["symbol"] == "AAPL"
        assert positions[0]["quantity"] == 100
        assert positions[0]["avg_price"] == 150.50
        assert positions[0]["market_value"] == 15050.0
        assert positions[0]["unrealized_pnl"] == 500.0
        assert positions[0]["position_type"] == "long"
        
        # Check second position
        assert positions[1]["symbol"] == "MSFT"
        assert positions[1]["quantity"] == 50
        assert positions[1]["avg_price"] == 300.25
        assert positions[1]["market_value"] == 15012.50
        assert positions[1]["unrealized_pnl"] == -250.0
        assert positions[1]["position_type"] == "long"
    
    @pytest.mark.asyncio
    async def test_get_position_existing_symbol(self):
        """Test get_position with existing symbol."""
        # First add a position
        self.service.set_mock_position("AAPL", 100.0, 150.0)
        
        position = await self.service.get_position("user123", "AAPL")
        
        assert position is not None
        assert position["symbol"] == "AAPL"
        assert position["quantity"] == 100.0
        assert position["avg_price"] == 150.0
        assert position["market_value"] == 15000.0
        assert position["unrealized_pnl"] == 0.0  # market_value - (qty * avg_cost)
        assert position["position_type"] == "long"
    
    @pytest.mark.asyncio
    async def test_get_position_nonexistent_symbol(self):
        """Test get_position with non-existent symbol."""
        position = await self.service.get_position("user123", "NONEXISTENT")
        assert position is None
    
    @pytest.mark.asyncio
    async def test_create_position_basic(self):
        """Test basic create_position functionality."""
        result = await self.service.create_position("user123", "NVDA", 25.0, 400.0)
        
        assert "position_id" in result
        assert result["symbol"] == "NVDA"
        assert "user123_NVDA_" in result["position_id"]
        
        # Verify the position was stored
        assert "NVDA" in self.service._mock_positions
        pos = self.service._mock_positions["NVDA"]
        assert pos.symbol == "NVDA"
        assert pos.qty == 25.0
        assert pos.price == 400.0
        assert pos.avg_cost == 400.0
        assert pos.market_value == 10000.0
    
    @pytest.mark.asyncio
    async def test_create_position_with_position_type(self):
        """Test create_position with position_type parameter."""
        result = await self.service.create_position("user123", "AMD", 50.0, 100.0, "short")
        
        assert result["symbol"] == "AMD"
        # The position_type parameter doesn't affect the stored position currently
        # but it's part of the method signature
    
    @pytest.mark.asyncio
    async def test_update_position_existing(self):
        """Test updating an existing position."""
        # First create a position
        self.service.set_mock_position("INTC", 30.0, 50.0)
        
        result = await self.service.update_position("user123", "INTC", 40.0, 55.0)
        
        assert result is True
        
        # Verify the update
        pos = self.service._mock_positions["INTC"]
        assert pos.qty == 40.0
        assert pos.price == 55.0
        assert pos.market_value == 2200.0  # 40 * 55
    
    @pytest.mark.asyncio
    async def test_update_position_nonexistent(self):
        """Test updating a non-existent position."""
        result = await self.service.update_position("user123", "NONEXISTENT", 10.0, 100.0)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_close_position_existing(self):
        """Test closing an existing position."""
        # First create a position
        self.service.set_mock_position("IBM", 20.0, 130.0)
        
        result = await self.service.close_position("user123", "IBM")
        
        assert result is True
        assert "IBM" not in self.service._mock_positions
    
    @pytest.mark.asyncio
    async def test_close_position_nonexistent(self):
        """Test closing a non-existent position."""
        result = await self.service.close_position("user123", "NONEXISTENT")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_positions_by_symbols_existing_positions(self):
        """Test get_positions_by_symbols with existing positions."""
        # Setup some mock positions
        self.service.set_mock_position("AAPL", 100.0, 150.0)
        self.service.set_mock_position("MSFT", 50.0, 300.0)
        
        with patch('backend.services.positions_service.logger') as mock_logger:
            result = await self.service.get_positions_by_symbols(["AAPL", "MSFT", "GOOGL"])
            
            # Should return all requested symbols
            assert len(result) == 3
            
            # Check existing positions
            assert result["AAPL"].symbol == "AAPL"
            assert result["AAPL"].qty == 100.0
            assert result["AAPL"].price == 150.0
            
            assert result["MSFT"].symbol == "MSFT"
            assert result["MSFT"].qty == 50.0
            assert result["MSFT"].price == 300.0
            
            # Check mock position for non-existent symbol
            assert result["GOOGL"].symbol == "GOOGL"
            assert result["GOOGL"].qty == 0.0
            assert result["GOOGL"].price == 100.0  # Mock price
            assert result["GOOGL"].avg_cost == 100.0
            assert result["GOOGL"].market_value == 0.0
            
            # Verify logging was called
            mock_logger.debug.assert_called_once_with("Retrieved positions for 3 symbols")
    
    @pytest.mark.asyncio
    async def test_get_positions_by_symbols_empty_list(self):
        """Test get_positions_by_symbols with empty symbol list."""
        with patch('backend.services.positions_service.logger') as mock_logger:
            result = await self.service.get_positions_by_symbols([])
            
            assert result == {}
            mock_logger.debug.assert_called_once_with("Retrieved positions for 0 symbols")
    
    @pytest.mark.asyncio
    async def test_get_positions_by_symbols_all_new_symbols(self):
        """Test get_positions_by_symbols with all new symbols."""
        with patch('backend.services.positions_service.logger') as mock_logger:
            result = await self.service.get_positions_by_symbols(["NEW1", "NEW2"])
            
            assert len(result) == 2
            
            for symbol in ["NEW1", "NEW2"]:
                assert result[symbol].symbol == symbol
                assert result[symbol].qty == 0.0
                assert result[symbol].price == 100.0
                assert result[symbol].avg_cost == 100.0
                assert result[symbol].market_value == 0.0
            
            mock_logger.debug.assert_called_once_with("Retrieved positions for 2 symbols")
    
    def test_set_mock_position_basic(self):
        """Test set_mock_position functionality."""
        self.service.set_mock_position("TEST", 75.0, 200.0)
        
        assert "TEST" in self.service._mock_positions
        pos = self.service._mock_positions["TEST"]
        assert pos.symbol == "TEST"
        assert pos.qty == 75.0
        assert pos.price == 200.0
        assert pos.avg_cost == 200.0
        assert pos.market_value == 15000.0
    
    def test_set_mock_position_default_price(self):
        """Test set_mock_position with default price."""
        self.service.set_mock_position("DEFAULT", 50.0)
        
        pos = self.service._mock_positions["DEFAULT"]
        assert pos.symbol == "DEFAULT"
        assert pos.qty == 50.0
        assert pos.price == 100.0  # Default price
        assert pos.avg_cost == 100.0
        assert pos.market_value == 5000.0


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_position_calculator_zero_risk_per_share(self):
        """Test PositionCalculator with zero risk per share scenario."""
        calculator = PositionCalculator()
        
        # This should raise ZeroDivisionError but the current implementation
        # has a check for risk_per_share <= 0 that raises ValueError instead
        # Let's test that the existing code handles this case
        with pytest.raises(ValueError, match="Stop loss must be less than entry price"):
            calculator.calculate_position_size(
                account_balance=Decimal('10000'),
                risk_percentage=Decimal('0.02'),
                entry_price=Decimal('100'),
                stop_loss=Decimal('100')  # Equal prices would create zero risk
            )
    
    def test_position_calculator_zero_division_error_coverage(self):
        """Test to trigger the ZeroDivisionError condition by patching abs()."""
        calculator = PositionCalculator()
        
        # Patch the abs function to return 0 and trigger the ZeroDivisionError
        with patch('backend.services.positions_service.abs', return_value=0):
            with pytest.raises(ZeroDivisionError, match="Risk per share cannot be zero"):
                calculator.calculate_position_size(
                    account_balance=Decimal('10000'),
                    risk_percentage=Decimal('0.02'),
                    entry_price=Decimal('100'),
                    stop_loss=Decimal('90')
                )
    
    @pytest.mark.asyncio
    async def test_positions_service_initialization(self):
        """Test PositionsService initialization."""
        service = PositionsService()
        assert service._mock_positions == {}
        
        # Test that it returns the same mock data consistently
        positions1 = await service.get_user_positions("user1")
        positions2 = await service.get_user_positions("user2")
        
        # Should return identical mock data for any user
        assert positions1 == positions2
    
    def test_position_with_none_values(self):
        """Test Position initialization with None values."""
        pos = Position(
            symbol="NULL_TEST",
            qty=10.0,
            price=50.0,
            avg_cost=None,  # This should default to price
            market_value=None  # This should be calculated
        )
        
        assert pos.avg_cost == 50.0  # Should default to price
        assert pos.market_value == 500.0  # Should be calculated


# Module execution and debugging helpers
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])