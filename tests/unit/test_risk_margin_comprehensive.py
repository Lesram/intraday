"""
Comprehensive tests for backend.risk.margin_calculator module.

Tests cover:
- MarginRequirement dataclass
- MarginCalculator initialization
- Stock margin calculations
- Option margin calculations
- Portfolio margin calculations
- Available buying power
- Position validation

Target: 90%+ coverage
"""

from decimal import Decimal

import pytest

from backend.risk.margin_calculator import (
    MarginCalculator,
    MarginRequirement,
    create_margin_calculator,
)


# ==============================================================================
# MarginRequirement Dataclass Tests
# ==============================================================================

class TestMarginRequirement:
    """Tests for MarginRequirement dataclass."""

    def test_margin_requirement_creation(self):
        """Test creating MarginRequirement with all fields."""
        req = MarginRequirement(
            initial_margin=Decimal('5000'),
            maintenance_margin=Decimal('2500'),
            buying_power_used=Decimal('5000'),
            excess_liquidity=Decimal('95000')
        )
        
        assert req.initial_margin == Decimal('5000')
        assert req.maintenance_margin == Decimal('2500')
        assert req.buying_power_used == Decimal('5000')
        assert req.excess_liquidity == Decimal('95000')

    def test_margin_requirement_zero_values(self):
        """Test MarginRequirement with zero values."""
        req = MarginRequirement(
            initial_margin=Decimal('0'),
            maintenance_margin=Decimal('0'),
            buying_power_used=Decimal('0'),
            excess_liquidity=Decimal('100000')
        )
        
        assert req.initial_margin == Decimal('0')
        assert req.maintenance_margin == Decimal('0')

    def test_margin_requirement_high_values(self):
        """Test MarginRequirement with high values."""
        req = MarginRequirement(
            initial_margin=Decimal('500000'),
            maintenance_margin=Decimal('250000'),
            buying_power_used=Decimal('500000'),
            excess_liquidity=Decimal('-400000')  # Over-leveraged
        )
        
        assert req.initial_margin == Decimal('500000')
        assert req.excess_liquidity == Decimal('-400000')


# ==============================================================================
# MarginCalculator Initialization Tests
# ==============================================================================

class TestMarginCalculatorInit:
    """Tests for MarginCalculator initialization."""

    def test_default_initialization(self):
        """Test default initialization with $100,000 equity."""
        calc = MarginCalculator()
        
        assert calc.account_equity == Decimal('100000')
        assert calc.initial_margin_rate == Decimal('0.5')
        assert calc.maintenance_margin_rate == Decimal('0.25')

    def test_custom_equity(self):
        """Test initialization with custom account equity."""
        calc = MarginCalculator(account_equity=Decimal('250000'))
        
        assert calc.account_equity == Decimal('250000')

    def test_small_account(self):
        """Test initialization with small account."""
        calc = MarginCalculator(account_equity=Decimal('5000'))
        
        assert calc.account_equity == Decimal('5000')

    def test_large_account(self):
        """Test initialization with large account."""
        calc = MarginCalculator(account_equity=Decimal('10000000'))
        
        assert calc.account_equity == Decimal('10000000')


# ==============================================================================
# Stock Margin Calculation Tests
# ==============================================================================

class TestCalculateStockMargin:
    """Tests for calculate_stock_margin method."""

    @pytest.fixture
    def calculator(self):
        """Create a margin calculator with $100,000 equity."""
        return MarginCalculator(account_equity=Decimal('100000'))

    def test_basic_stock_margin(self, calculator):
        """Test basic stock margin calculation."""
        margin = calculator.calculate_stock_margin('AAPL', 100, Decimal('150'))
        
        # Position value = 100 * 150 = 15,000
        # Initial margin = 15,000 * 0.5 = 7,500
        # Maintenance margin = 15,000 * 0.25 = 3,750
        assert margin.initial_margin == Decimal('7500')
        assert margin.maintenance_margin == Decimal('3750')
        assert margin.buying_power_used == Decimal('7500')
        assert margin.excess_liquidity == Decimal('92500')  # 100,000 - 7,500

    def test_stock_margin_single_share(self, calculator):
        """Test margin for single share."""
        margin = calculator.calculate_stock_margin('AAPL', 1, Decimal('150'))
        
        assert margin.initial_margin == Decimal('75')  # 150 * 0.5
        assert margin.maintenance_margin == Decimal('37.5')

    def test_stock_margin_large_position(self, calculator):
        """Test margin for large position."""
        margin = calculator.calculate_stock_margin('AAPL', 1000, Decimal('200'))
        
        # Position value = 200,000
        assert margin.initial_margin == Decimal('100000')  # 200,000 * 0.5
        assert margin.maintenance_margin == Decimal('50000')
        assert margin.excess_liquidity == Decimal('0')  # Uses all equity

    def test_stock_margin_over_equity(self, calculator):
        """Test margin exceeding account equity."""
        margin = calculator.calculate_stock_margin('AAPL', 2000, Decimal('200'))
        
        # Position value = 400,000
        assert margin.initial_margin == Decimal('200000')
        assert margin.excess_liquidity == Decimal('-100000')  # Negative = insufficient

    def test_stock_margin_short_position(self, calculator):
        """Test margin for short position (negative quantity)."""
        margin = calculator.calculate_stock_margin('AAPL', -100, Decimal('150'))
        
        # Should use absolute value
        assert margin.initial_margin == Decimal('7500')
        assert margin.maintenance_margin == Decimal('3750')

    def test_stock_margin_cheap_stock(self, calculator):
        """Test margin for cheap stock."""
        margin = calculator.calculate_stock_margin('CHEAP', 1000, Decimal('0.50'))
        
        # Position value = 500
        assert margin.initial_margin == Decimal('250')
        assert margin.maintenance_margin == Decimal('125')

    def test_stock_margin_expensive_stock(self, calculator):
        """Test margin for expensive stock like BRK.A."""
        margin = calculator.calculate_stock_margin('BRK.A', 1, Decimal('500000'))
        
        # Position value = 500,000
        assert margin.initial_margin == Decimal('250000')
        assert margin.maintenance_margin == Decimal('125000')


# ==============================================================================
# Option Margin Calculation Tests
# ==============================================================================

class TestCalculateOptionMargin:
    """Tests for calculate_option_margin method."""

    @pytest.fixture
    def calculator(self):
        """Create a margin calculator."""
        return MarginCalculator(account_equity=Decimal('100000'))

    def test_long_call_margin(self, calculator):
        """Test margin for long call option."""
        margin = calculator.calculate_option_margin(
            symbol='AAPL',
            quantity=1,
            premium=Decimal('5'),
            underlying_price=Decimal('150'),
            strike=Decimal('155'),
            option_type='CALL'
        )
        
        # Long call margin = premium * 100 = 5 * 100 = 500
        assert margin.initial_margin == Decimal('500')
        assert margin.maintenance_margin == Decimal('0')

    def test_long_put_margin(self, calculator):
        """Test margin for long put option."""
        margin = calculator.calculate_option_margin(
            symbol='AAPL',
            quantity=1,
            premium=Decimal('3'),
            underlying_price=Decimal('150'),
            strike=Decimal('145'),
            option_type='PUT'
        )
        
        # Long put margin = premium * 100 = 3 * 100 = 300
        assert margin.initial_margin == Decimal('300')
        assert margin.maintenance_margin == Decimal('0')

    def test_short_call_margin(self, calculator):
        """Test margin for short call option."""
        margin = calculator.calculate_option_margin(
            symbol='AAPL',
            quantity=-1,
            premium=Decimal('5'),
            underlying_price=Decimal('150'),
            strike=Decimal('155'),
            option_type='SHORT_CALL'
        )
        
        # Short option margin is more complex
        # Uses the greater of two formulas
        assert margin.initial_margin > Decimal('500')
        assert margin.maintenance_margin > Decimal('0')

    def test_short_put_margin(self, calculator):
        """Test margin for short put option."""
        margin = calculator.calculate_option_margin(
            symbol='AAPL',
            quantity=-1,
            premium=Decimal('3'),
            underlying_price=Decimal('150'),
            strike=Decimal('145'),
            option_type='SHORT_PUT'
        )
        
        # Short option margin calculation
        assert margin.initial_margin > Decimal('300')

    def test_option_margin_multiple_contracts(self, calculator):
        """Test margin for multiple option contracts."""
        margin = calculator.calculate_option_margin(
            symbol='AAPL',
            quantity=10,
            premium=Decimal('5'),
            underlying_price=Decimal('150'),
            strike=Decimal('155'),
            option_type='CALL'
        )
        
        # 10 contracts * $5 * 100 = $5,000
        assert margin.initial_margin == Decimal('5000')

    def test_option_margin_lowercase_type(self, calculator):
        """Test option margin with lowercase type."""
        margin = calculator.calculate_option_margin(
            symbol='AAPL',
            quantity=1,
            premium=Decimal('5'),
            underlying_price=Decimal('150'),
            strike=Decimal('155'),
            option_type='call'  # lowercase
        )
        
        # Should still work
        assert margin.initial_margin == Decimal('500')

    def test_option_margin_put_lowercase(self, calculator):
        """Test option margin with lowercase put."""
        margin = calculator.calculate_option_margin(
            symbol='AAPL',
            quantity=1,
            premium=Decimal('3'),
            underlying_price=Decimal('150'),
            strike=Decimal('145'),
            option_type='put'  # lowercase
        )
        
        assert margin.initial_margin == Decimal('300')


# ==============================================================================
# Portfolio Margin Calculation Tests
# ==============================================================================

class TestCalculatePortfolioMargin:
    """Tests for calculate_portfolio_margin method."""

    @pytest.fixture
    def calculator(self):
        """Create a margin calculator."""
        return MarginCalculator(account_equity=Decimal('100000'))

    def test_empty_portfolio(self, calculator):
        """Test margin for empty portfolio."""
        margin = calculator.calculate_portfolio_margin({})
        
        assert margin.initial_margin == Decimal('0')
        assert margin.maintenance_margin == Decimal('0')
        assert margin.excess_liquidity == Decimal('100000')

    def test_single_stock_portfolio(self, calculator):
        """Test margin for single stock portfolio."""
        positions = {
            'AAPL': {
                'type': 'stock',
                'symbol': 'AAPL',
                'quantity': 100,
                'price': 150
            }
        }
        
        margin = calculator.calculate_portfolio_margin(positions)
        
        assert margin.initial_margin == Decimal('7500')
        assert margin.maintenance_margin == Decimal('3750')

    def test_multiple_stock_portfolio(self, calculator):
        """Test margin for multiple stock portfolio."""
        positions = {
            'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 100, 'price': 150},
            'GOOGL': {'type': 'stock', 'symbol': 'GOOGL', 'quantity': 50, 'price': 100},
            'MSFT': {'type': 'stock', 'symbol': 'MSFT', 'quantity': 200, 'price': 300}
        }
        
        margin = calculator.calculate_portfolio_margin(positions)
        
        # AAPL: 15000 * 0.5 = 7500
        # GOOGL: 5000 * 0.5 = 2500
        # MSFT: 60000 * 0.5 = 30000
        # Total: 40000
        assert margin.initial_margin == Decimal('40000')
        assert margin.excess_liquidity == Decimal('60000')

    def test_mixed_portfolio_stock_and_option(self, calculator):
        """Test margin for mixed stock and option portfolio."""
        positions = {
            'AAPL_STOCK': {
                'type': 'stock',
                'symbol': 'AAPL',
                'quantity': 100,
                'price': 150
            },
            'AAPL_CALL': {
                'type': 'option',
                'symbol': 'AAPL',
                'quantity': 2,
                'premium': 5,
                'underlying_price': 150,
                'strike': 155,
                'option_type': 'CALL'
            }
        }
        
        margin = calculator.calculate_portfolio_margin(positions)
        
        # Stock: 7500
        # Option: 2 * 5 * 100 = 1000
        # Total: 8500
        assert margin.initial_margin == Decimal('8500')

    def test_portfolio_ignores_unknown_types(self, calculator):
        """Test that unknown position types are ignored."""
        positions = {
            'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 100, 'price': 150},
            'CRYPTO': {'type': 'crypto', 'symbol': 'BTC', 'quantity': 1, 'price': 50000}
        }
        
        margin = calculator.calculate_portfolio_margin(positions)
        
        # Only stock is counted
        assert margin.initial_margin == Decimal('7500')

    def test_portfolio_leveraged_position(self, calculator):
        """Test portfolio with leveraged position exceeding equity."""
        positions = {
            'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 1000, 'price': 300}
        }
        
        margin = calculator.calculate_portfolio_margin(positions)
        
        # Position value = 300,000, Initial margin = 150,000
        assert margin.initial_margin == Decimal('150000')
        assert margin.excess_liquidity == Decimal('-50000')  # Over-leveraged


# ==============================================================================
# Available Buying Power Tests
# ==============================================================================

class TestGetAvailableBuyingPower:
    """Tests for get_available_buying_power method."""

    @pytest.fixture
    def calculator(self):
        """Create a margin calculator."""
        return MarginCalculator(account_equity=Decimal('100000'))

    def test_buying_power_no_positions(self, calculator):
        """Test buying power with no positions."""
        bp = calculator.get_available_buying_power()
        
        assert bp == Decimal('100000')

    def test_buying_power_none_positions(self, calculator):
        """Test buying power with None positions."""
        bp = calculator.get_available_buying_power(current_positions=None)
        
        assert bp == Decimal('100000')

    def test_buying_power_with_positions(self, calculator):
        """Test buying power with existing positions."""
        positions = {
            'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 100, 'price': 150}
        }
        
        bp = calculator.get_available_buying_power(current_positions=positions)
        
        # 100,000 - 7,500 (initial margin) = 92,500
        assert bp == Decimal('92500')

    def test_buying_power_multiple_positions(self, calculator):
        """Test buying power with multiple positions."""
        positions = {
            'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 100, 'price': 150},
            'GOOGL': {'type': 'stock', 'symbol': 'GOOGL', 'quantity': 50, 'price': 100}
        }
        
        bp = calculator.get_available_buying_power(current_positions=positions)
        
        # 100,000 - 7,500 - 2,500 = 90,000
        assert bp == Decimal('90000')

    def test_buying_power_negative(self, calculator):
        """Test buying power when over-leveraged."""
        positions = {
            'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 2000, 'price': 150}
        }
        
        bp = calculator.get_available_buying_power(current_positions=positions)
        
        # Position = 300,000, Margin = 150,000
        # 100,000 - 150,000 = -50,000
        assert bp == Decimal('-50000')


# ==============================================================================
# Position Validation Tests
# ==============================================================================

class TestValidateNewPosition:
    """Tests for validate_new_position method."""

    @pytest.fixture
    def calculator(self):
        """Create a margin calculator."""
        return MarginCalculator(account_equity=Decimal('100000'))

    def test_validate_small_position(self, calculator):
        """Test validation of small position that fits."""
        valid = calculator.validate_new_position('AAPL', 100, Decimal('150'))
        
        # Needs 7,500 margin, have 100,000
        assert valid is True

    def test_validate_large_position_fails(self, calculator):
        """Test validation of position that doesn't fit."""
        valid = calculator.validate_new_position('AAPL', 2000, Decimal('150'))
        
        # Needs 150,000 margin, have 100,000
        assert valid is False

    def test_validate_position_exactly_fits(self, calculator):
        """Test validation of position that exactly fits."""
        # Need 100,000 margin = position of 200,000 at 50% margin
        # 200,000 / 150 = ~1333 shares
        valid = calculator.validate_new_position('AAPL', 1333, Decimal('150'))
        
        # 1333 * 150 = 199,950, margin = 99,975 < 100,000
        assert valid is True

    def test_validate_with_existing_positions(self, calculator):
        """Test validation with existing positions reducing buying power."""
        current = {
            'GOOGL': {'type': 'stock', 'symbol': 'GOOGL', 'quantity': 500, 'price': 100}
        }
        
        # Current uses 25,000 margin, leaving 75,000
        valid = calculator.validate_new_position('AAPL', 100, Decimal('150'), current)
        
        # Needs 7,500 margin, have 75,000
        assert valid is True

    def test_validate_with_existing_positions_fails(self, calculator):
        """Test validation fails when not enough buying power."""
        current = {
            'GOOGL': {'type': 'stock', 'symbol': 'GOOGL', 'quantity': 1000, 'price': 150}
        }
        
        # Current uses 75,000 margin, leaving 25,000
        valid = calculator.validate_new_position('AAPL', 1000, Decimal('100'), current)
        
        # Needs 50,000 margin, only have 25,000
        assert valid is False

    def test_validate_zero_quantity(self, calculator):
        """Test validation with zero quantity."""
        valid = calculator.validate_new_position('AAPL', 0, Decimal('150'))
        
        # Zero position needs zero margin
        assert valid is True

    def test_validate_short_position(self, calculator):
        """Test validation with short (negative) quantity."""
        valid = calculator.validate_new_position('AAPL', -100, Decimal('150'))
        
        # Should use absolute value
        assert valid is True


# ==============================================================================
# Factory Function Tests
# ==============================================================================

class TestCreateMarginCalculator:
    """Tests for create_margin_calculator factory function."""

    def test_create_default(self):
        """Test creating calculator with default parameters."""
        calc = create_margin_calculator()
        
        assert isinstance(calc, MarginCalculator)
        assert calc.account_equity == Decimal('100000')

    def test_create_custom_equity(self):
        """Test creating calculator with custom equity."""
        calc = create_margin_calculator(account_equity=Decimal('500000'))
        
        assert calc.account_equity == Decimal('500000')

    def test_create_small_account(self):
        """Test creating calculator for small account."""
        calc = create_margin_calculator(account_equity=Decimal('1000'))
        
        assert calc.account_equity == Decimal('1000')


# ==============================================================================
# Edge Cases and Integration Tests
# ==============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_zero_price(self):
        """Test margin with zero price."""
        calc = MarginCalculator()
        margin = calc.calculate_stock_margin('FREE', 100, Decimal('0'))
        
        assert margin.initial_margin == Decimal('0')
        assert margin.maintenance_margin == Decimal('0')

    def test_decimal_precision(self):
        """Test margin maintains decimal precision."""
        calc = MarginCalculator(account_equity=Decimal('100000.00'))
        margin = calc.calculate_stock_margin('AAPL', 1, Decimal('123.456'))
        
        # Should maintain precision
        assert isinstance(margin.initial_margin, Decimal)
        assert margin.initial_margin == Decimal('61.728')

    def test_fractional_shares(self):
        """Test margin with fractional quantities (as int)."""
        calc = MarginCalculator()
        # Quantity must be int, but let's test boundary
        margin = calc.calculate_stock_margin('AAPL', 1, Decimal('150.50'))
        
        assert margin.initial_margin == Decimal('75.25')


class TestIntegration:
    """Integration tests for margin calculator workflow."""

    def test_complete_trading_workflow(self):
        """Test complete workflow: check BP, validate, calculate margin."""
        calc = create_margin_calculator(account_equity=Decimal('100000'))
        
        # Check initial buying power
        initial_bp = calc.get_available_buying_power()
        assert initial_bp == Decimal('100000')
        
        # Validate first position
        valid1 = calc.validate_new_position('AAPL', 100, Decimal('150'))
        assert valid1 is True
        
        # Calculate margin for position
        margin1 = calc.calculate_stock_margin('AAPL', 100, Decimal('150'))
        
        # Simulate adding to portfolio
        positions = {'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 100, 'price': 150}}
        
        # Check remaining buying power
        remaining_bp = calc.get_available_buying_power(positions)
        assert remaining_bp == Decimal('92500')
        
        # Validate second position with reduced BP
        valid2 = calc.validate_new_position('GOOGL', 100, Decimal('100'), positions)
        assert valid2 is True

    def test_portfolio_rebalance(self):
        """Test margin calculations during portfolio rebalance."""
        calc = create_margin_calculator(account_equity=Decimal('100000'))
        
        # Initial portfolio: total value 40,000
        positions_before = {
            'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 200, 'price': 100},  # 20,000
            'GOOGL': {'type': 'stock', 'symbol': 'GOOGL', 'quantity': 200, 'price': 100}  # 20,000
        }
        
        margin_before = calc.calculate_portfolio_margin(positions_before)
        
        # After rebalance (same total value, different allocation)
        positions_after = {
            'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 100, 'price': 100},   # 10,000
            'GOOGL': {'type': 'stock', 'symbol': 'GOOGL', 'quantity': 300, 'price': 100}  # 30,000
        }
        
        margin_after = calc.calculate_portfolio_margin(positions_after)
        
        # Same total value, same margin
        assert margin_before.initial_margin == margin_after.initial_margin

    def test_margin_call_scenario(self):
        """Test margin call scenario when equity drops."""
        # Start with position at full margin
        calc = create_margin_calculator(account_equity=Decimal('50000'))
        
        positions = {
            'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 500, 'price': 150}
        }
        
        # Initial: Position = 75,000, Margin = 37,500 < 50,000 equity
        margin = calc.calculate_portfolio_margin(positions)
        assert margin.excess_liquidity == Decimal('12500')
        
        # Price drops to 120 (maintaining same shares)
        positions_down = {
            'AAPL': {'type': 'stock', 'symbol': 'AAPL', 'quantity': 500, 'price': 120}
        }
        
        # New: Position = 60,000, Margin = 30,000 < 50,000 equity
        margin_down = calc.calculate_portfolio_margin(positions_down)
        assert margin_down.excess_liquidity == Decimal('20000')

    def test_option_covered_call_strategy(self):
        """Test margin for covered call strategy."""
        calc = create_margin_calculator(account_equity=Decimal('100000'))
        
        # Own 100 shares + sold 1 call
        positions = {
            'AAPL_STOCK': {
                'type': 'stock',
                'symbol': 'AAPL',
                'quantity': 100,
                'price': 150
            },
            'AAPL_SHORT_CALL': {
                'type': 'option',
                'symbol': 'AAPL',
                'quantity': -1,
                'premium': 5,
                'underlying_price': 150,
                'strike': 160,
                'option_type': 'SHORT_CALL'
            }
        }
        
        margin = calc.calculate_portfolio_margin(positions)
        
        # Stock margin + short call margin
        assert margin.initial_margin > Decimal('7500')  # More than just stock
