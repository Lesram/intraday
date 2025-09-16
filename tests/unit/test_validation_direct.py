"""
Tests for backend/infra/validation.py - Input validation utilities
Tests validation functions using direct import approach.
"""

import os
import sys
import pytest
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch, Mock


class TestValidationDirect:
    """Test suite for validation utilities using direct import."""
    
    def setup_method(self):
        """Set up direct module import."""
        backend_path = Path(__file__).parent.parent.parent / "backend"
        self.backend_path = str(backend_path.resolve())
        if self.backend_path not in sys.path:
            sys.path.insert(0, self.backend_path)
    
    def teardown_method(self):
        """Clean up after each test."""
        if self.backend_path in sys.path:
            sys.path.remove(self.backend_path)
        
        # Clean up imported modules
        validation_modules = [k for k in sys.modules.keys() if 'validation' in k.lower()]
        for name in validation_modules:
            if name in sys.modules:
                del sys.modules[name]

    def test_validate_symbol_success(self):
        """Test validate_symbol with valid symbols."""
        # Direct import from infra directory
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            # Test valid symbols
            assert validation.validate_symbol("AAPL") == "AAPL"
            assert validation.validate_symbol("aapl") == "AAPL"
            assert validation.validate_symbol("SPY") == "SPY"
            assert validation.validate_symbol("MSFT") == "MSFT"
            assert validation.validate_symbol("BRK.A") == "BRK.A"
            assert validation.validate_symbol("BRK-A") == "BRK-A"
            
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_symbol_empty(self):
        """Test validate_symbol raises error for empty symbol."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Symbol cannot be empty"):
                validation.validate_symbol("")
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_symbol_too_long(self):
        """Test validate_symbol raises error for symbol too long."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Symbol too long"):
                validation.validate_symbol("VERYLONGSYMBOL")  # 14 chars > 10
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_symbol_invalid_start(self):
        """Test validate_symbol raises error for symbol starting with number."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Symbol cannot start with number"):
                validation.validate_symbol("1AAPL")
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_symbol_invalid_chars(self):
        """Test validate_symbol raises error for invalid characters."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Invalid characters in symbol"):
                validation.validate_symbol("AAPL@")
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_price_success(self):
        """Test validate_price with valid prices."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            # Test valid prices
            assert validation.validate_price(100.0) == 100.0
            assert validation.validate_price(50.25) == 50.25
            assert validation.validate_price(0.0001) == 0.0001
            assert validation.validate_price(99999999) == 99999999.0
            
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_price_negative(self):
        """Test validate_price raises error for negative price."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Price must be positive"):
                validation.validate_price(-10.0)
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_price_zero(self):
        """Test validate_price raises error for zero price."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Price must be positive"):
                validation.validate_price(0.0)
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_price_too_large(self):
        """Test validate_price raises error for price too large."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Price too large"):
                validation.validate_price(200000000)  # > 1e8
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_price_too_many_decimals(self):
        """Test validate_price raises error for too many decimal places."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Too many decimal places"):
                validation.validate_price(10.12345)  # 5 decimal places > 4
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_quantity_success(self):
        """Test validate_quantity with valid quantities."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            # Test valid quantities
            assert validation.validate_quantity(100) == 100.0
            assert validation.validate_quantity(50.5) == 50.5
            assert validation.validate_quantity(-10) == -10.0  # Short position
            assert validation.validate_quantity(0.1, allow_fractional=True) == 0.1
            
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_quantity_zero(self):
        """Test validate_quantity raises error for zero quantity."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Quantity cannot be zero"):
                validation.validate_quantity(0)
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_quantity_too_large(self):
        """Test validate_quantity raises error for quantity too large."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Quantity too large"):
                validation.validate_quantity(200000000)  # > 1e8
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_quantity_fractional_not_allowed(self):
        """Test validate_quantity raises error when fractional shares not allowed."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            with pytest.raises(ValueError, match="Fractional shares not allowed"):
                validation.validate_quantity(10.5, allow_fractional=False)
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_order_success(self):
        """Test validate_order with valid order data."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            order_data = {
                "symbol": "AAPL",
                "quantity": 100,
                "price": 150.25,
                "order_type": "limit"
            }
            
            result = validation.validate_order(order_data)
            
            assert result["symbol"] == "AAPL"
            assert result["quantity"] == 100.0
            assert result["price"] == 150.25
            assert result["order_type"] == "limit"
            
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_order_missing_required_field(self):
        """Test validate_order raises error for missing required fields."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            order_data = {"symbol": "AAPL"}  # Missing quantity
            
            with pytest.raises(ValueError, match="Quantity is required"):
                validation.validate_order(order_data)
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_order_invalid_order_type(self):
        """Test validate_order raises error for invalid order type."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            order_data = {
                "symbol": "AAPL", 
                "quantity": 100,
                "order_type": "invalid_type"
            }
            
            with pytest.raises(ValueError, match="Invalid order type"):
                validation.validate_order(order_data)
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_portfolio_constraints_success(self):
        """Test validate_portfolio_constraints with valid portfolio."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            portfolio_data = {
                "positions": {
                    "AAPL": {"weight": 0.20},
                    "MSFT": {"weight": 0.20},
                    "GOOGL": {"weight": 0.20},
                    "AMZN": {"weight": 0.20},
                    "TSLA": {"weight": 0.20}
                },
                "total_value": 100000
            }
            
            violations = validation.validate_portfolio_constraints(portfolio_data)
            
            assert violations == []  # No violations
            
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_portfolio_constraints_concentration(self):
        """Test validate_portfolio_constraints detects excessive concentration."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            portfolio_data = {
                "positions": {
                    "AAPL": {"weight": 0.80},  # Excessive concentration
                    "MSFT": {"weight": 0.20}
                },
                "total_value": 100000
            }
            
            violations = validation.validate_portfolio_constraints(portfolio_data)
            
            assert len(violations) > 0
            assert any("concentration" in v.lower() for v in violations)
            
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_risk_limits_success(self):
        """Test validate_risk_limits with valid limits."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            risk_limits = {
                "max_position_size": 0.30,
                "min_position_size": 0.05,
                "max_var": 0.05,
                "max_drawdown": 0.20
            }
            
            result = validation.validate_risk_limits(risk_limits)
            
            assert result == risk_limits  # Should return unchanged
            
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_risk_limits_conflicting(self):
        """Test validate_risk_limits raises error for conflicting limits."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            risk_limits = {
                "max_position_size": 0.10,
                "min_position_size": 0.20  # min > max
            }
            
            with pytest.raises(ValueError, match="Conflicting risk limits"):
                validation.validate_risk_limits(risk_limits)
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_market_data_success(self):
        """Test validate_market_data with valid data."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            market_data = {
                "symbol": "AAPL",
                "price": 150.25,
                "timestamp": "2024-01-01T12:00:00Z",
                "volume": 1000000
            }
            
            result = validation.validate_market_data(market_data)
            
            assert result["symbol"] == "AAPL"
            assert result["price"] == 150.25
            
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_market_data_missing_field(self):
        """Test validate_market_data raises error for missing required field."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            market_data = {
                "symbol": "AAPL",
                "price": 150.25
                # Missing timestamp
            }
            
            with pytest.raises(ValueError, match="Timestamp is required"):
                validation.validate_market_data(market_data)
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))

    def test_validate_market_data_negative_volume(self):
        """Test validate_market_data raises error for negative volume."""
        sys.path.insert(0, os.path.join(self.backend_path, 'infra'))
        try:
            import validation
            
            market_data = {
                "symbol": "AAPL",
                "price": 150.25,
                "timestamp": "2024-01-01T12:00:00Z",
                "volume": -1000  # Negative volume
            }
            
            with pytest.raises(ValueError, match="Volume cannot be negative"):
                validation.validate_market_data(market_data)
                
        finally:
            if os.path.join(self.backend_path, 'infra') in sys.path:
                sys.path.remove(os.path.join(self.backend_path, 'infra'))
