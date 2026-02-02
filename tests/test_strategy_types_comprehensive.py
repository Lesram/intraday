"""
Comprehensive tests for Strategy Types
Tests TradingSignal and ExecutionPlan dataclasses
"""

import pytest
from datetime import datetime
from decimal import Decimal

from backend.strategies.types import TradingSignal, ExecutionPlan, Side


class TestSideEnum:
    """Test Side enumeration"""
    
    def test_buy_value(self):
        """Test BUY enum value"""
        assert Side.BUY.value == "buy"
        
    def test_sell_value(self):
        """Test SELL enum value"""
        assert Side.SELL.value == "sell"
        
    def test_flat_value(self):
        """Test FLAT enum value"""
        assert Side.FLAT.value == "flat"
        
    def test_side_from_string(self):
        """Test creating Side from string"""
        assert Side("buy") == Side.BUY
        assert Side("sell") == Side.SELL


class TestTradingSignal:
    """Test TradingSignal dataclass"""
    
    def test_basic_creation(self):
        """Test basic signal creation"""
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8
        )
        
        assert signal.symbol == "AAPL"
        assert signal.source == "momentum"
        assert signal.target_exposure == 0.5
        assert signal.confidence == 0.8
        
    def test_full_long_exposure(self):
        """Test maximum long exposure"""
        signal = TradingSignal(
            symbol="AAPL",
            source="test",
            ts=datetime.now(),
            target_exposure=1.0,
            confidence=1.0
        )
        
        assert signal.target_exposure == 1.0
        
    def test_full_short_exposure(self):
        """Test maximum short exposure"""
        signal = TradingSignal(
            symbol="AAPL",
            source="test",
            ts=datetime.now(),
            target_exposure=-1.0,
            confidence=0.9
        )
        
        assert signal.target_exposure == -1.0
        
    def test_flat_exposure(self):
        """Test flat (zero) exposure"""
        signal = TradingSignal(
            symbol="AAPL",
            source="test",
            ts=datetime.now(),
            target_exposure=0.0,
            confidence=0.5
        )
        
        assert signal.target_exposure == 0.0
        
    def test_invalid_exposure_too_high(self):
        """Test rejection of exposure > 1.0"""
        with pytest.raises(ValueError, match="target_exposure"):
            TradingSignal(
                symbol="AAPL",
                source="test",
                ts=datetime.now(),
                target_exposure=1.5,
                confidence=0.5
            )
            
    def test_invalid_exposure_too_low(self):
        """Test rejection of exposure < -1.0"""
        with pytest.raises(ValueError, match="target_exposure"):
            TradingSignal(
                symbol="AAPL",
                source="test",
                ts=datetime.now(),
                target_exposure=-1.5,
                confidence=0.5
            )
            
    def test_invalid_confidence_too_high(self):
        """Test rejection of confidence > 1.0"""
        with pytest.raises(ValueError, match="confidence"):
            TradingSignal(
                symbol="AAPL",
                source="test",
                ts=datetime.now(),
                target_exposure=0.5,
                confidence=1.5
            )
            
    def test_invalid_confidence_negative(self):
        """Test rejection of negative confidence"""
        with pytest.raises(ValueError, match="confidence"):
            TradingSignal(
                symbol="AAPL",
                source="test",
                ts=datetime.now(),
                target_exposure=0.5,
                confidence=-0.1
            )
            
    def test_with_metadata(self):
        """Test signal with metadata"""
        metadata = {"indicator": "RSI", "value": 70}
        signal = TradingSignal(
            symbol="AAPL",
            source="test",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8,
            metadata=metadata
        )
        
        assert signal.metadata == metadata
        assert signal.metadata["indicator"] == "RSI"
        
    def test_immutable(self):
        """Test signal is immutable (frozen)"""
        signal = TradingSignal(
            symbol="AAPL",
            source="test",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8
        )
        
        with pytest.raises(AttributeError):
            signal.symbol = "MSFT"


class TestExecutionPlan:
    """Test ExecutionPlan dataclass"""
    
    def test_basic_creation(self):
        """Test basic plan creation"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0
        )
        
        assert plan.symbol == "AAPL"
        assert plan.side == Side.BUY
        assert plan.quantity == Decimal("100")
        assert plan.price == Decimal("150.0")
        
    def test_default_order_type(self):
        """Test default order type is market"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0
        )
        
        assert plan.order_type == "market"
        
    def test_limit_order_type(self):
        """Test explicit limit order type"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0,
            order_type="limit"
        )
        
        assert plan.order_type == "limit"
        
    def test_quantity_converted_to_decimal(self):
        """Test quantity is converted to Decimal"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0
        )
        
        assert isinstance(plan.quantity, Decimal)
        
    def test_price_converted_to_decimal(self):
        """Test price is converted to Decimal"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0
        )
        
        assert isinstance(plan.price, Decimal)
        
    def test_notional_calculated(self):
        """Test notional is calculated from quantity * price"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0
        )
        
        assert plan.notional == Decimal("15000")
        
    def test_qty_alias(self):
        """Test qty is aliased from quantity"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0
        )
        
        assert plan.qty == Decimal("100")
        
    def test_timestamp_auto_generated(self):
        """Test timestamp is auto-generated if not provided"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0
        )
        
        assert plan.ts is not None
        assert isinstance(plan.ts, datetime)
        
    def test_exposure_inferred_for_buy(self):
        """Test exposure is inferred for buy orders"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0
        )
        
        assert plan.from_exposure == 0.0
        assert plan.to_exposure == 1.0
        
    def test_exposure_inferred_for_sell(self):
        """Test exposure is inferred for sell orders"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.SELL,
            quantity=-100,
            price=150.0
        )
        
        assert plan.from_exposure == 0.0
        assert plan.to_exposure == -1.0
        
    def test_exposure_inferred_for_zero_quantity(self):
        """Test exposure for zero quantity"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.FLAT,
            quantity=0,
            price=150.0
        )
        
        assert plan.to_exposure == 0.0
        
    def test_explicit_exposure_values(self):
        """Test explicit exposure values are preserved"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=50,
            price=150.0,
            from_exposure=0.25,
            to_exposure=0.75
        )
        
        assert plan.from_exposure == 0.25
        assert plan.to_exposure == 0.75
        
    def test_invalid_from_exposure(self):
        """Test rejection of invalid from_exposure"""
        with pytest.raises(ValueError, match="from_exposure"):
            ExecutionPlan(
                symbol="AAPL",
                side=Side.BUY,
                quantity=100,
                price=150.0,
                from_exposure=1.5
            )
            
    def test_invalid_to_exposure(self):
        """Test rejection of invalid to_exposure"""
        with pytest.raises(ValueError, match="to_exposure"):
            ExecutionPlan(
                symbol="AAPL",
                side=Side.BUY,
                quantity=100,
                price=150.0,
                to_exposure=2.0
            )
            
    def test_with_reason(self):
        """Test plan with reason"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0,
            reason="Momentum signal"
        )
        
        assert plan.reason == "Momentum signal"
        
    def test_risk_allowed_default(self):
        """Test risk_allowed defaults to True"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0
        )
        
        assert plan.risk_allowed == True
        
    def test_risk_blocked(self):
        """Test risk can be blocked"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0,
            risk_allowed=False,
            risk_reason="Exceeded daily loss limit"
        )
        
        assert plan.risk_allowed == False
        assert plan.risk_reason == "Exceeded daily loss limit"


class TestExecutionPlanWithDecimals:
    """Test ExecutionPlan with Decimal inputs"""
    
    def test_decimal_quantity(self):
        """Test Decimal quantity is preserved"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=Decimal("100.5"),
            price=Decimal("150.25")
        )
        
        assert plan.quantity == Decimal("100.5")
        assert plan.price == Decimal("150.25")
        
    def test_fractional_shares(self):
        """Test fractional shares"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=Decimal("0.5"),
            price=Decimal("150.00")
        )
        
        assert plan.quantity == Decimal("0.5")
        assert plan.notional == Decimal("75.00")


class TestExecutionPlanLegacyCompat:
    """Test ExecutionPlan legacy compatibility"""
    
    def test_legacy_construction(self):
        """Test legacy construction pattern"""
        # Legacy tests expect: symbol, side, quantity, price, order_type
        plan = ExecutionPlan("AAPL", Side.BUY, 100, 150.0, "market")
        
        assert plan.symbol == "AAPL"
        assert plan.side == Side.BUY
        assert plan.quantity == Decimal("100")
        assert plan.price == Decimal("150.0")
        assert plan.order_type == "market"
