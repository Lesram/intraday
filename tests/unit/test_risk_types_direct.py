"""
Tests for backend/risk/types.py - Risk management data types
Tests the enum definitions, dataclasses, and type validation using direct import.
"""

import os
import sys
import pytest
import importlib.util
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch, Mock


class TestRiskTypesDirect:
    """Test suite for risk management types using direct import."""
    
    def setup_method(self):
        """Set up direct module import."""
        backend_path = Path(__file__).parent.parent.parent / "backend"
        self.backend_path = str(backend_path.resolve())
        
        # Import the risk types module using importlib to avoid name conflicts
        risk_types_path = os.path.join(self.backend_path, 'risk', 'types.py')
        spec = importlib.util.spec_from_file_location("risk_types_module", risk_types_path)
        self.risk_types = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.risk_types)
    
    def teardown_method(self):
        """Clean up after each test."""
        self.risk_types = None

    def test_order_type_enum(self):
        """Test OrderType enum values."""
        # Test enum values
        assert self.risk_types.OrderType.MARKET.value == "market"
        assert self.risk_types.OrderType.LIMIT.value == "limit"
        assert self.risk_types.OrderType.STOP.value == "stop"
        assert self.risk_types.OrderType.STOP_LIMIT.value == "stop_limit"
        
        # Test enum instantiation
        market_order = self.risk_types.OrderType.MARKET
        assert isinstance(market_order, self.risk_types.OrderType)

    def test_order_status_enum(self):
        """Test OrderStatus enum values."""
        # Test enum values
        assert self.risk_types.OrderStatus.NEW.value == "new"
        assert self.risk_types.OrderStatus.SUBMITTED.value == "submitted" 
        assert self.risk_types.OrderStatus.PARTIAL.value == "partial"
        assert self.risk_types.OrderStatus.FILLED.value == "filled"
        assert self.risk_types.OrderStatus.CANCELED.value == "canceled"
        assert self.risk_types.OrderStatus.REJECTED.value == "rejected"
        assert self.risk_types.OrderStatus.PENDING.value == "pending"
        
        # Test enum instantiation
        new_status = self.risk_types.OrderStatus.NEW
        assert isinstance(new_status, self.risk_types.OrderStatus)

    def test_time_in_force_enum(self):
        """Test TimeInForce enum values."""
        # Test enum values
        assert self.risk_types.TimeInForce.DAY.value == "day"
        assert self.risk_types.TimeInForce.GTC.value == "gtc"
        assert self.risk_types.TimeInForce.IOC.value == "ioc"
        assert self.risk_types.TimeInForce.FOK.value == "fok"
        
        # Test enum instantiation  
        gtc_tif = self.risk_types.TimeInForce.GTC
        assert isinstance(gtc_tif, self.risk_types.TimeInForce)

    def test_risk_level_enum(self):
        """Test RiskLevel enum values."""
        # Test enum values
        assert self.risk_types.RiskLevel.LOW.value == "low"
        assert self.risk_types.RiskLevel.MEDIUM.value == "medium"
        assert self.risk_types.RiskLevel.HIGH.value == "high"
        assert self.risk_types.RiskLevel.EXTREME.value == "extreme"
        
        # Test enum instantiation
        high_risk = self.risk_types.RiskLevel.HIGH
        assert isinstance(high_risk, self.risk_types.RiskLevel)

    def test_risk_limits_initialization(self):
        """Test RiskLimits dataclass initialization."""
        # Test default initialization
        limits = self.risk_types.RiskLimits()
        
        assert limits.max_position_value == 0.0
        assert limits.max_symbol_exposure == 1.0
        assert limits.circuit_breaker_pct == 0.5
        assert limits.max_portfolio_exposure is None

    def test_risk_limits_with_values(self):
        """Test RiskLimits with custom values."""
        # Test with custom values
        limits = self.risk_types.RiskLimits(
            max_position_value=100000.0,
            max_symbol_exposure=0.3,
            circuit_breaker_pct=0.2
        )
        
        assert limits.max_position_value == 100000.0
        assert limits.max_symbol_exposure == 0.3
        assert limits.circuit_breaker_pct == 0.2

    def test_risk_limits_legacy_compatibility(self):
        """Test RiskLimits legacy field compatibility."""
        # Test with legacy fields
        limits = self.risk_types.RiskLimits(
            max_position_size=Decimal("50000"),
            max_daily_loss=Decimal("5000")
        )
        
        assert limits.max_position_size == Decimal("50000")
        assert limits.max_daily_loss == Decimal("5000")

    def test_order_spec_initialization(self):
        """Test OrderSpec dataclass initialization."""
        # Import Side for testing
        sys.path.insert(0, self.backend_path)
        try:
            from backend.strategies.types import Side
            
            # Test with basic values
            order_spec = self.risk_types.OrderSpec(
                symbol="AAPL",
                side=Side.BUY,
                qty=Decimal("100"),
                price=Decimal("150.0")
            )
            
            assert order_spec.symbol == "AAPL"
            assert order_spec.side == Side.BUY
            assert order_spec.qty == Decimal("100")
            assert order_spec.price == Decimal("150.0")
            assert order_spec.notional == Decimal("15000.0")  # Auto-calculated
            
        finally:
            if self.backend_path in sys.path:
                sys.path.remove(self.backend_path)

    def test_order_spec_aliases(self):
        """Test OrderSpec quantity and order_type aliases."""
        sys.path.insert(0, self.backend_path)
        try:
            from backend.strategies.types import Side
            
            # Test with aliases
            order_spec = self.risk_types.OrderSpec(
                symbol="MSFT",
                side=Side.SELL,
                quantity=Decimal("50"),  # Using alias
                order_type="limit"       # Using alias
            )
            
            assert order_spec.qty == Decimal("50")
            assert order_spec.type == "limit"
            
        finally:
            if self.backend_path in sys.path:
                sys.path.remove(self.backend_path)

    def test_order_spec_validation_negative_qty(self):
        """Test OrderSpec raises error for negative quantity."""
        sys.path.insert(0, self.backend_path)
        try:
            from backend.strategies.types import Side
            
            with pytest.raises(ValueError, match="qty must be non-negative"):
                self.risk_types.OrderSpec(
                    symbol="AAPL",
                    side=Side.BUY,
                    qty=Decimal("-100")
                )
                
        finally:
            if self.backend_path in sys.path:
                sys.path.remove(self.backend_path)

    def test_order_spec_validation_negative_price(self):
        """Test OrderSpec raises error for negative price."""
        sys.path.insert(0, self.backend_path)
        try:
            from backend.strategies.types import Side
            
            with pytest.raises(ValueError, match="notional must be non-negative"):
                self.risk_types.OrderSpec(
                    symbol="AAPL",
                    side=Side.BUY,
                    qty=Decimal("100"),
                    price=Decimal("-150.0")
                )
                
        finally:
            if self.backend_path in sys.path:
                sys.path.remove(self.backend_path)

    def test_order_spec_get_method(self):
        """Test OrderSpec dict-like get method."""
        sys.path.insert(0, self.backend_path)
        try:
            from backend.strategies.types import Side
            
            order_spec = self.risk_types.OrderSpec(
                symbol="GOOGL",
                side=Side.BUY,
                qty=Decimal("25"),
                price=Decimal("2000.0")
            )
            
            # Test get method
            assert order_spec.get("symbol") == "GOOGL"
            assert order_spec.get("qty") == Decimal("25")
            assert order_spec.get("quantity") == Decimal("25")  # Alias
            assert order_spec.get("nonexistent", "default") == "default"
            
        finally:
            if self.backend_path in sys.path:
                sys.path.remove(self.backend_path)

    def test_portfolio_state_initialization(self):
        """Test PortfolioState dataclass initialization."""
        portfolio = self.risk_types.PortfolioState(
            equity=Decimal("100000"),
            cash=Decimal("20000"),
            positions={"AAPL": Decimal("100"), "MSFT": Decimal("-50")},
            sector_map={"AAPL": "technology", "MSFT": "technology"}
        )
        
        assert portfolio.equity == Decimal("100000")
        assert portfolio.cash == Decimal("20000")
        assert portfolio.positions["AAPL"] == Decimal("100")
        assert portfolio.sector_map["AAPL"] == "technology"

    def test_portfolio_state_properties(self):
        """Test PortfolioState calculated properties."""
        portfolio = self.risk_types.PortfolioState(
            equity=Decimal("100000"),
            cash=Decimal("20000"),
            positions={"AAPL": Decimal("100")},
            sector_map={"AAPL": "technology"}
        )
        
        # Test properties
        assert portfolio.gross_notional == Decimal("80000")  # equity - cash
        assert portfolio.net_notional == Decimal("80000")

    def test_portfolio_risk_initialization(self):
        """Test PortfolioRisk dataclass initialization."""
        # Test default initialization
        risk = self.risk_types.PortfolioRisk()
        
        assert risk.var_95 == Decimal("0.0")
        assert risk.var_99 == Decimal("0.0")
        assert risk.volatility == 0.0
        assert risk.sharpe_ratio == 0.0
        assert risk.max_drawdown == Decimal("0.0")
        assert risk.beta == 1.0
        assert risk.concentration_risk == 0.0

    def test_risk_decision_allow_classmethod(self):
        """Test RiskDecision.allow classmethod."""
        decision = self.risk_types.RiskDecision.allow(
            reason="within limits",
            adjustments={"qty": "100"},
            limits={"max_position": "1000"}
        )
        
        assert decision.allowed is True
        assert decision.reason == "within limits"
        assert decision.adjustments == {"qty": "100"}
        assert decision.limits == {"max_position": "1000"}
        assert isinstance(decision.timestamp, datetime)

    def test_risk_decision_block_classmethod(self):
        """Test RiskDecision.block classmethod."""
        decision = self.risk_types.RiskDecision.block(
            reason="exceeds position limit",
            adjustments={},
            limits={"max_position": "1000"}
        )
        
        assert decision.allowed is False
        assert decision.reason == "exceeds position limit"
        assert decision.adjustments == {}
        assert decision.limits == {"max_position": "1000"}
        assert isinstance(decision.timestamp, datetime)

    def test_risk_decision_initialization(self):
        """Test RiskDecision direct initialization."""
        decision = self.risk_types.RiskDecision(
            allowed=True,
            reason="test decision",
            adjustments={"test": "value"},
            limits={"limit": "test"},
            original_qty=Decimal("100"),
            adjusted_qty=Decimal("90"),
            risk_score=0.5
        )
        
        assert decision.allowed is True
        assert decision.reason == "test decision"
        assert decision.original_qty == Decimal("100")
        assert decision.adjusted_qty == Decimal("90")
        assert decision.risk_score == 0.5
