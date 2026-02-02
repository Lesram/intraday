"""
Comprehensive tests for Risk Types
Tests OrderSpec, PortfolioState, RiskDecision, and related types
"""

import pytest
from decimal import Decimal
from datetime import datetime

from backend.risk.types import (
    OrderType,
    OrderStatus,
    TimeInForce,
    RiskLevel,
    RiskReasonCode,
    RiskLimits,
    OrderSpec,
)
from backend.strategies.types import Side


class TestOrderTypeEnum:
    """Test OrderType enumeration"""
    
    def test_market_value(self):
        """Test MARKET enum value"""
        assert OrderType.MARKET.value == "market"
        
    def test_limit_value(self):
        """Test LIMIT enum value"""
        assert OrderType.LIMIT.value == "limit"
        
    def test_stop_value(self):
        """Test STOP enum value"""
        assert OrderType.STOP.value == "stop"
        
    def test_stop_limit_value(self):
        """Test STOP_LIMIT enum value"""
        assert OrderType.STOP_LIMIT.value == "stop_limit"


class TestOrderStatusEnum:
    """Test OrderStatus enumeration"""
    
    def test_new_status(self):
        """Test NEW status"""
        assert OrderStatus.NEW.value == "new"
        
    def test_filled_status(self):
        """Test FILLED status"""
        assert OrderStatus.FILLED.value == "filled"
        
    def test_canceled_status(self):
        """Test CANCELED status"""
        assert OrderStatus.CANCELED.value == "canceled"
        
    def test_rejected_status(self):
        """Test REJECTED status"""
        assert OrderStatus.REJECTED.value == "rejected"
        
    def test_partial_status(self):
        """Test PARTIAL status"""
        assert OrderStatus.PARTIAL.value == "partial"


class TestTimeInForceEnum:
    """Test TimeInForce enumeration"""
    
    def test_day(self):
        """Test DAY value"""
        assert TimeInForce.DAY.value == "day"
        
    def test_gtc(self):
        """Test GTC (Good Till Canceled)"""
        assert TimeInForce.GTC.value == "gtc"
        
    def test_ioc(self):
        """Test IOC (Immediate or Cancel)"""
        assert TimeInForce.IOC.value == "ioc"
        
    def test_fok(self):
        """Test FOK (Fill or Kill)"""
        assert TimeInForce.FOK.value == "fok"


class TestRiskLevelEnum:
    """Test RiskLevel enumeration"""
    
    def test_low(self):
        """Test LOW level"""
        assert RiskLevel.LOW.value == "low"
        
    def test_medium(self):
        """Test MEDIUM level"""
        assert RiskLevel.MEDIUM.value == "medium"
        
    def test_high(self):
        """Test HIGH level"""
        assert RiskLevel.HIGH.value == "high"
        
    def test_extreme(self):
        """Test EXTREME level"""
        assert RiskLevel.EXTREME.value == "extreme"


class TestRiskReasonCodeEnum:
    """Test RiskReasonCode enumeration"""
    
    def test_symbol_concentration(self):
        """Test SYMBOL_CONCENTRATION_EXCEEDED"""
        assert RiskReasonCode.SYMBOL_CONCENTRATION_EXCEEDED.value == "SYMBOL_CONCENTRATION_EXCEEDED"
        
    def test_portfolio_limit(self):
        """Test PORTFOLIO_LIMIT_EXCEEDED"""
        assert RiskReasonCode.PORTFOLIO_LIMIT_EXCEEDED.value == "PORTFOLIO_LIMIT_EXCEEDED"
        
    def test_circuit_breaker(self):
        """Test CIRCUIT_BREAKER_TRIPPED"""
        assert RiskReasonCode.CIRCUIT_BREAKER_TRIPPED.value == "CIRCUIT_BREAKER_TRIPPED"
        
    def test_daily_loss(self):
        """Test DAILY_LOSS_EXCEEDED"""
        assert RiskReasonCode.DAILY_LOSS_EXCEEDED.value == "DAILY_LOSS_EXCEEDED"


class TestRiskLimits:
    """Test RiskLimits dataclass"""
    
    def test_default_values(self):
        """Test default risk limits"""
        limits = RiskLimits()
        
        assert limits.max_position_value == 0.0
        assert limits.max_symbol_exposure == 1.0
        assert limits.circuit_breaker_pct == 0.5
        assert limits.allow_admin_override == False
        
    def test_custom_values(self):
        """Test custom risk limits"""
        limits = RiskLimits(
            max_position_value=100000.0,
            max_symbol_exposure=0.25,
            circuit_breaker_pct=0.10
        )
        
        assert limits.max_position_value == 100000.0
        assert limits.max_symbol_exposure == 0.25
        assert limits.circuit_breaker_pct == 0.10
        
    def test_admin_override(self):
        """Test admin override flag"""
        limits = RiskLimits(allow_admin_override=True)
        
        assert limits.allow_admin_override == True
        
    def test_legacy_field_max_portfolio_exposure(self):
        """Test legacy max_portfolio_exposure fallback"""
        limits = RiskLimits(max_portfolio_exposure=0.5)
        
        # Should map to max_symbol_exposure
        assert limits.max_symbol_exposure == 0.5
        
    def test_legacy_position_size(self):
        """Test legacy max_position_size field"""
        limits = RiskLimits(max_position_size=Decimal("50000"))
        
        assert limits.max_position_size == Decimal("50000")


class TestOrderSpec:
    """Test OrderSpec dataclass"""
    
    def test_basic_creation(self):
        """Test basic order spec creation"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            notional=Decimal("15000")
        )
        
        assert spec.symbol == "AAPL"
        assert spec.side == Side.BUY
        assert spec.qty == Decimal("100")
        
    def test_with_price(self):
        """Test order spec with price"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("150.00")
        )
        
        assert spec.price == Decimal("150.00")
        # Notional should be auto-calculated
        assert spec.notional == Decimal("15000.00")
        
    def test_quantity_alias(self):
        """Test quantity alias for qty"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            quantity=Decimal("50")
        )
        
        assert spec.qty == Decimal("50")
        
    def test_order_type_alias(self):
        """Test order_type alias for type"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            order_type="limit"
        )
        
        assert spec.type == "limit"
        
    def test_get_method(self):
        """Test dict-like get method"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            notional=Decimal("15000")
        )
        
        assert spec.get("symbol") == "AAPL"
        assert spec.get("qty") == Decimal("100")
        assert spec.get("nonexistent", "default") == "default"
        
    def test_get_quantity_alias(self):
        """Test get with quantity alias"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100")
        )
        
        assert spec.get("quantity") == Decimal("100")
        
    def test_get_order_type_alias(self):
        """Test get with order_type alias"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            type="market"
        )
        
        assert spec.get("order_type") == "market"
        
    def test_negative_qty_rejected(self):
        """Test negative qty is rejected"""
        with pytest.raises(ValueError, match="qty must be non-negative"):
            OrderSpec(
                symbol="AAPL",
                side=Side.BUY,
                qty=Decimal("-100"),
                notional=Decimal("15000")
            )
            
    def test_negative_notional_rejected(self):
        """Test negative notional is rejected"""
        with pytest.raises(ValueError, match="notional must be non-negative"):
            OrderSpec(
                symbol="AAPL",
                side=Side.BUY,
                qty=Decimal("100"),
                notional=Decimal("-15000")
            )
            
    def test_zero_price_rejected(self):
        """Test zero or negative price is rejected"""
        with pytest.raises(ValueError, match="price must be positive"):
            OrderSpec(
                symbol="AAPL",
                side=Side.BUY,
                qty=Decimal("100"),
                price=Decimal("0")
            )
            
    def test_with_attributes(self):
        """Test order spec with attributes"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            attributes={"client_order_id": "123", "strategy": "momentum"}
        )
        
        assert spec.attributes["client_order_id"] == "123"
        assert spec.get("client_order_id") == "123"
        
    def test_with_tif(self):
        """Test order spec with time in force"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            tif="gtc"
        )
        
        assert spec.tif == "gtc"
        
    def test_auto_notional_no_price(self):
        """Test auto-calculated notional when no price provided"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100")
        )
        
        # Default fallback: qty * 100
        assert spec.notional == Decimal("10000.0")
        
    def test_immutable(self):
        """Test order spec is immutable (frozen)"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100")
        )
        
        with pytest.raises(AttributeError):
            spec.symbol = "MSFT"
