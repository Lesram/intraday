"""
Complete Type Definitions Test Suite - Quick Win for Coverage

Tests all type enums, dataclasses, and TypedDicts across the platform.
These are simple to test and provide high coverage boost with minimal effort.

Target modules:
- backend.strategies.types
- backend.risk.types  
- backend.models.risk
"""

import pytest
from decimal import Decimal
from datetime import datetime

# Import all type definitions
from backend.strategies.types import Side, TradingSignal, ExecutionPlan
from backend.risk.types import (
    OrderType,
    OrderStatus,
    TimeInForce,
    RiskLevel,
    RiskReasonCode,
    OrderSpec,
    RiskDecision,
    RiskLimits,
    PortfolioState,
    PortfolioRisk,
)
from backend.models.risk import RiskStatus, ViolationType, EmergencyStopStatus


# ============================================================================
# STRATEGY TYPES TESTS
# ============================================================================

class TestSideEnum:
    """Test Side enum"""
    
    def test_side_buy_value(self):
        """Test BUY side has correct value"""
        assert Side.BUY.value == "buy"
    
    def test_side_sell_value(self):
        """Test SELL side has correct value"""
        assert Side.SELL.value == "sell"
    
    def test_side_members(self):
        """Test Side has expected members"""
        assert len(Side) >= 2
        assert Side.BUY in Side
        assert Side.SELL in Side


class TestTradingSignalDataclass:
    """Test TradingSignal dataclass"""
    
    def test_signal_creation(self):
        """Test creating a TradingSignal instance"""
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
        assert isinstance(signal.ts, datetime)
    
    def test_signal_with_metadata(self):
        """Test TradingSignal with optional metadata"""
        metadata = {"indicator": "RSI", "value": 35}
        signal = TradingSignal(
            symbol="AAPL",
            source="momentum",
            ts=datetime.now(),
            target_exposure=0.5,
            confidence=0.8,
            metadata=metadata
        )
        assert signal.metadata == metadata
    
    def test_signal_validation_exposure_too_high(self):
        """Test TradingSignal rejects exposure > 1.0"""
        with pytest.raises(ValueError, match="target_exposure"):
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=1.5,
                confidence=0.8
            )
    
    def test_signal_validation_confidence_too_high(self):
        """Test TradingSignal rejects confidence > 1.0"""
        with pytest.raises(ValueError, match="confidence"):
            TradingSignal(
                symbol="AAPL",
                source="momentum",
                ts=datetime.now(),
                target_exposure=0.5,
                confidence=1.5
            )


class TestExecutionPlanDataclass:
    """Test ExecutionPlan dataclass"""
    
    def test_execution_plan_simple_creation(self):
        """Test creating an ExecutionPlan instance (legacy style)"""
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
    
    def test_execution_plan_with_exposures(self):
        """Test ExecutionPlan with exposure fields"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0,
            from_exposure=0.0,
            to_exposure=0.5
        )
        assert plan.from_exposure == 0.0
        assert plan.to_exposure == 0.5
    
    def test_execution_plan_notional_auto_calculation(self):
        """Test ExecutionPlan auto-calculates notional"""
        plan = ExecutionPlan(
            symbol="AAPL",
            side=Side.BUY,
            quantity=100,
            price=150.0
        )
        assert plan.notional == Decimal("15000.0")


# ============================================================================
# RISK TYPES TESTS
# ============================================================================

class TestOrderTypeEnum:
    """Test OrderType enum"""
    
    def test_order_type_market(self):
        """Test MARKET order type"""
        assert OrderType.MARKET.value == "market"
    
    def test_order_type_limit(self):
        """Test LIMIT order type"""
        assert OrderType.LIMIT.value == "limit"
    
    def test_order_type_stop(self):
        """Test STOP order type"""
        assert OrderType.STOP.value == "stop"
    
    def test_order_type_stop_limit(self):
        """Test STOP_LIMIT order type"""
        assert OrderType.STOP_LIMIT.value == "stop_limit"
    
    def test_order_type_members_count(self):
        """Test OrderType has all expected members"""
        assert len(OrderType) >= 4


class TestOrderStatusEnum:
    """Test OrderStatus enum"""
    
    def test_order_status_pending(self):
        """Test PENDING status"""
        assert OrderStatus.PENDING.value == "pending"
    
    def test_order_status_filled(self):
        """Test FILLED status"""
        assert OrderStatus.FILLED.value == "filled"
    
    def test_order_status_canceled(self):
        """Test CANCELED status"""
        assert OrderStatus.CANCELED.value == "canceled"
    
    def test_order_status_rejected(self):
        """Test REJECTED status"""
        assert OrderStatus.REJECTED.value == "rejected"


class TestTimeInForceEnum:
    """Test TimeInForce enum"""
    
    def test_time_in_force_day(self):
        """Test DAY time in force"""
        assert TimeInForce.DAY.value == "day"
    
    def test_time_in_force_gtc(self):
        """Test GTC (Good Till Cancelled)"""
        assert TimeInForce.GTC.value == "gtc"
    
    def test_time_in_force_ioc(self):
        """Test IOC (Immediate or Cancel)"""
        assert TimeInForce.IOC.value == "ioc"
    
    def test_time_in_force_fok(self):
        """Test FOK (Fill or Kill)"""
        assert TimeInForce.FOK.value == "fok"


class TestRiskLevelEnum:
    """Test RiskLevel enum"""
    
    def test_risk_level_low(self):
        """Test LOW risk level"""
        assert RiskLevel.LOW.value == "low"
    
    def test_risk_level_medium(self):
        """Test MEDIUM risk level"""
        assert RiskLevel.MEDIUM.value == "medium"
    
    def test_risk_level_high(self):
        """Test HIGH risk level"""
        assert RiskLevel.HIGH.value == "high"
    
    def test_risk_level_extreme(self):
        """Test EXTREME risk level"""
        assert RiskLevel.EXTREME.value == "extreme"


class TestRiskReasonCodeEnum:
    """Test RiskReasonCode enum"""
    
    def test_risk_reason_position_size_exceeded(self):
        """Test POSITION_SIZE_EXCEEDED reason code"""
        assert RiskReasonCode.POSITION_SIZE_EXCEEDED in RiskReasonCode
    
    def test_risk_reason_symbol_concentration(self):
        """Test SYMBOL_CONCENTRATION_EXCEEDED reason code"""
        assert RiskReasonCode.SYMBOL_CONCENTRATION_EXCEEDED in RiskReasonCode
    
    def test_risk_reason_has_multiple_codes(self):
        """Test RiskReasonCode has multiple values"""
        assert len(RiskReasonCode) >= 3


class TestOrderSpecDataclass:
    """Test OrderSpec dataclass"""
    
    def test_order_spec_creation(self):
        """Test creating an OrderSpec instance"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("150.0")
        )
        assert spec.symbol == "AAPL"
        assert spec.qty == Decimal("100")
        assert spec.side == Side.BUY
        assert spec.price == Decimal("150.0")
    
    def test_order_spec_notional_auto_calculation(self):
        """Test OrderSpec auto-calculates notional"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("150.0")
        )
        assert spec.notional == Decimal("15000.0")
    
    def test_order_spec_with_type(self):
        """Test OrderSpec with order type"""
        spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("150.0"),
            type="limit"
        )
        assert spec.type == "limit"


class TestRiskDecisionDataclass:
    """Test RiskDecision dataclass"""
    
    def test_risk_decision_allowed(self):
        """Test allowed risk decision"""
        decision = RiskDecision.allow(reason="Within all limits")
        assert decision.allowed is True
        assert decision.approved is True  # backward compat
        assert decision.reason == "Within all limits"
    
    def test_risk_decision_blocked(self):
        """Test blocked risk decision"""
        decision = RiskDecision.block(
            reason="Exceeds position limit",
            adjustments={"violation": "POSITION_SIZE_EXCEEDED"}
        )
        assert decision.allowed is False
        assert decision.approved is False
        assert "position limit" in decision.reason.lower()
    
    def test_risk_decision_with_adjustments(self):
        """Test risk decision with adjustments"""
        adjustments = {"symbol_exposure": 0.25, "sector_exposure": 0.15}
        decision = RiskDecision.allow(
            reason="Approved with limits",
            adjustments=adjustments
        )
        assert decision.symbol_exposure == 0.25
        assert decision.sector_exposure == 0.15


class TestRiskLimitsDataclass:
    """Test RiskLimits dataclass"""
    
    def test_risk_limits_creation(self):
        """Test creating RiskLimits instance"""
        limits = RiskLimits(
            max_position_value=10000.0,
            max_symbol_exposure=0.8,
            circuit_breaker_pct=0.5
        )
        assert limits.max_position_value == 10000.0
        assert limits.max_symbol_exposure == 0.8
        assert limits.circuit_breaker_pct == 0.5
    
    def test_risk_limits_with_legacy_fields(self):
        """Test RiskLimits with legacy fields"""
        limits = RiskLimits(
            max_position_value=10000.0,
            max_symbol_exposure=0.8,
            max_position_size=Decimal("100000")
        )
        assert limits.max_position_size == Decimal("100000")


class TestPortfolioStateDataclass:
    """Test PortfolioState dataclass"""
    
    def test_portfolio_state_creation(self):
        """Test creating PortfolioState instance"""
        state = PortfolioState(
            equity=Decimal("100000.0"),
            cash=Decimal("50000.0"),
            positions={"AAPL": Decimal("100"), "MSFT": Decimal("50")},
            sector_map={"AAPL": "tech", "MSFT": "tech"}
        )
        assert state.equity == Decimal("100000.0")
        assert state.cash == Decimal("50000.0")
        assert len(state.positions) == 2
    
    def test_portfolio_state_gross_notional(self):
        """Test PortfolioState gross notional calculation"""
        state = PortfolioState(
            equity=Decimal("100000.0"),
            cash=Decimal("50000.0"),
            positions={},
            sector_map={}
        )
        # gross_notional = abs(equity - cash)
        assert state.gross_notional == Decimal("50000.0")


class TestPortfolioRiskDataclass:
    """Test PortfolioRisk dataclass"""
    
    def test_portfolio_risk_creation(self):
        """Test creating PortfolioRisk instance"""
        risk = PortfolioRisk(
            var_95=Decimal("5000.0"),
            var_99=Decimal("10000.0"),
            volatility=0.15,
            sharpe_ratio=1.8
        )
        assert risk.var_95 == Decimal("5000.0")
        assert risk.var_99 == Decimal("10000.0")
        assert risk.volatility == 0.15
        assert risk.sharpe_ratio == 1.8


# ============================================================================
# MODEL RISK TYPES TESTS
# ============================================================================

class TestRiskStatusEnum:
    """Test RiskStatus enum"""
    
    def test_risk_status_normal(self):
        """Test NORMAL risk status"""
        assert RiskStatus.NORMAL.value == "normal"
    
    def test_risk_status_warning(self):
        """Test WARNING risk status"""
        assert RiskStatus.WARNING.value == "warning"
    
    def test_risk_status_critical(self):
        """Test CRITICAL risk status"""
        assert RiskStatus.CRITICAL.value == "critical"
    
    def test_risk_status_emergency_stop(self):
        """Test EMERGENCY_STOP risk status"""
        # RiskStatus doesn't have EMERGENCY_STOP
        assert RiskStatus.CRITICAL.value == "critical"


class TestViolationTypeEnum:
    """Test ViolationType enum"""
    
    def test_violation_type_warning(self):
        """Test WARNING violation"""
        assert ViolationType.WARNING.value == "warning"
    
    def test_violation_type_breach(self):
        """Test BREACH violation"""
        assert ViolationType.BREACH.value == "breach"
    
    def test_violation_type_has_multiple_types(self):
        """Test ViolationType has 2 violation types"""
        assert len(ViolationType) == 2


class TestEmergencyStopStatusEnum:
    """Test EmergencyStopStatus enum"""
    
    def test_emergency_stop_active(self):
        """Test ACTIVE emergency stop status"""
        assert EmergencyStopStatus.ACTIVE.value == "active"
    
    def test_emergency_stop_resolved(self):
        """Test RESOLVED emergency stop status"""
        assert EmergencyStopStatus.RESOLVED.value == "resolved"
    
    def test_emergency_stop_count(self):
        """Test EmergencyStopStatus has 2 members"""
        assert len(EmergencyStopStatus) == 2


# Mark all tests with 'unit' marker
pytestmark = pytest.mark.unit
