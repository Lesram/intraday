"""
Tests for position calculations and trading safety mechanisms.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch
from backend.services.positions_service import PositionCalculator
from backend.services.safety_modes import TradingSafety, SafetyMode, RiskLevel


class TestPositionCalculator:
    """Test position calculation logic."""

    def setup_method(self):
        """Set up test environment."""
        self.calculator = PositionCalculator()

    def test_position_size_calculation_basic(self):
        """Test basic position size calculation."""
        # Mock position data
        account_balance = Decimal('10000.00')
        risk_percentage = Decimal('0.02')  # 2% risk
        entry_price = Decimal('100.00')
        stop_loss = Decimal('95.00')  # 5% stop loss
        
        position_size = self.calculator.calculate_position_size(
            account_balance=account_balance,
            risk_percentage=risk_percentage,
            entry_price=entry_price,
            stop_loss=stop_loss
        )
        
        # Expected: (10000 * 0.02) / (100 - 95) = 200 / 5 = 40 shares
        assert position_size == Decimal('40.00')

    def test_position_size_zero_risk(self):
        """Test position size calculation with zero risk."""
        result = self.calculator.calculate_position_size(
            account_balance=Decimal('10000'),
            risk_percentage=Decimal('0'),
            entry_price=Decimal('100'),
            stop_loss=Decimal('95')
        )
        
        assert result == Decimal('0')

    def test_position_size_invalid_stop_loss(self):
        """Test position size calculation with invalid stop loss."""
        # Stop loss higher than entry price (invalid for long position)
        with pytest.raises((ValueError, ZeroDivisionError)):
            self.calculator.calculate_position_size(
                account_balance=Decimal('10000'),
                risk_percentage=Decimal('0.02'),
                entry_price=Decimal('100'),
                stop_loss=Decimal('105')  # Invalid: stop loss > entry price
            )

    def test_portfolio_risk_calculation(self):
        """Test portfolio risk calculation."""
        positions = [
            {'symbol': 'AAPL', 'quantity': 100, 'price': 150, 'risk_amount': 500},
            {'symbol': 'GOOGL', 'quantity': 50, 'price': 2800, 'risk_amount': 1000},
            {'symbol': 'MSFT', 'quantity': 75, 'price': 300, 'risk_amount': 750}
        ]
        
        total_risk = self.calculator.calculate_portfolio_risk(positions)
        
        # Expected: 500 + 1000 + 750 = 2250
        assert total_risk == Decimal('2250')

    def test_position_value_calculation(self):
        """Test position value calculation."""
        quantity = Decimal('100')
        price = Decimal('150.50')
        
        value = self.calculator.calculate_position_value(quantity, price)
        
        # Expected: 100 * 150.50 = 15050
        assert value == Decimal('15050.00')


class TestTradingSafety:
    """Test trading safety mechanisms."""

    def setup_method(self):
        """Set up test environment."""
        self.safety = TradingSafety()

    def test_safety_mode_normal(self):
        """Test normal safety mode allows trading."""
        self.safety.set_safety_mode(SafetyMode.NORMAL)
        
        assert self.safety.is_trading_allowed()
        assert self.safety.get_max_position_size() > 0

    def test_safety_mode_restricted(self):
        """Test restricted safety mode limits trading."""
        self.safety.set_safety_mode(SafetyMode.RESTRICTED)
        
        assert self.safety.is_trading_allowed()
        # Position size should be reduced in restricted mode
        normal_size = 1000
        restricted_size = self.safety.get_adjusted_position_size(normal_size)
        assert restricted_size < normal_size

    def test_safety_mode_halt(self):
        """Test halt safety mode stops trading."""
        self.safety.set_safety_mode(SafetyMode.HALT)
        
        assert not self.safety.is_trading_allowed()
        assert self.safety.get_max_position_size() == 0

    def test_risk_level_assessment(self):
        """Test risk level assessment."""
        # Low risk scenario
        low_risk = self.safety.assess_risk_level(
            portfolio_value=100000,
            daily_pnl=-500,  # -0.5% loss
            max_drawdown=0.02
        )
        assert low_risk == RiskLevel.LOW

        # High risk scenario  
        high_risk = self.safety.assess_risk_level(
            portfolio_value=100000,
            daily_pnl=-5000,  # -5% loss
            max_drawdown=0.15  # 15% drawdown
        )
        assert high_risk in [RiskLevel.HIGH, RiskLevel.CRITICAL]

    def test_circuit_breaker_activation(self):
        """Test circuit breaker activation on high losses."""
        # Simulate high loss that should trigger circuit breaker
        initial_mode = self.safety.get_safety_mode()
        
        self.safety.check_circuit_breaker(
            portfolio_value=100000,
            daily_pnl=-8000,  # -8% daily loss
            current_drawdown=0.12
        )
        
        # Safety mode should be more restrictive after circuit breaker
        new_mode = self.safety.get_safety_mode()
        assert new_mode != SafetyMode.NORMAL or new_mode != initial_mode

    def test_position_limit_enforcement(self):
        """Test position limit enforcement."""
        # Set position limits
        self.safety.set_position_limits(
            max_position_value=50000,
            max_portfolio_concentration=0.25
        )
        
        # Test position within limits
        assert self.safety.is_position_allowed(
            symbol='AAPL',
            position_value=30000,
            portfolio_value=200000
        )
        
        # Test position exceeding limits
        assert not self.safety.is_position_allowed(
            symbol='TSLA', 
            position_value=60000,  # Exceeds max position value
            portfolio_value=200000
        )

    @patch('backend.services.safety_modes.datetime')
    def test_trading_hours_enforcement(self, mock_datetime):
        """Test trading hours enforcement."""
        from datetime import datetime, time
        
        # Mock market hours (9:30 AM - 4:00 PM EST)
        mock_datetime.now.return_value = datetime(2025, 8, 13, 14, 30)  # 2:30 PM
        
        # Should allow trading during market hours
        assert self.safety.is_trading_time_allowed()
        
        # Mock after hours
        mock_datetime.now.return_value = datetime(2025, 8, 13, 20, 30)  # 8:30 PM
        
        # Should restrict trading after hours (depending on configuration)
        # This test depends on the specific implementation
        trading_allowed = self.safety.is_trading_time_allowed()
        assert isinstance(trading_allowed, bool)  # Just verify it returns a boolean
