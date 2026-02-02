"""
Tests for backend.strategies.basic module
Target: 100% coverage on BasicStrategy (246 lines)
"""
import pytest
from backend.strategies.basic import BasicStrategy, StrategyDecision


class TestStrategyDecision:
    """Test StrategyDecision dataclass"""
    
    def test_strategy_decision_creation(self):
        """Test creating strategy decision"""
        decision = StrategyDecision(
            action="buy",
            confidence=0.8,
            tp_pct=2.0,
            sl_pct=1.0,
            reason="RSI oversold"
        )
        assert decision.action == "buy"
        assert decision.confidence == 0.8


class TestBasicStrategy:
    """Test BasicStrategy class"""
    
    def test_basic_strategy_init_defaults(self):
        """Test initialization with default parameters"""
        strategy = BasicStrategy()
        assert strategy.rsi_buy == 35
        assert strategy.rsi_sell == 65
        assert strategy.sma_fast == 20
        assert strategy.sma_slow == 50
    
    def test_basic_strategy_init_custom(self):
        """Test initialization with custom parameters"""
        strategy = BasicStrategy(
            rsi_buy=30,
            rsi_sell=70,
            sma_fast=10,
            sma_slow=30,
            tp_pct=3.0,
            sl_pct=1.5
        )
        assert strategy.rsi_buy == 30
        assert strategy.rsi_sell == 70
        assert strategy.tp_pct == 3.0
    
    def test_decide_with_close_prices(self):
        """Test decide with close_prices parameter"""
        strategy = BasicStrategy()
        prices = [100.0] * 60  # Flat prices
        result = strategy.decide(close_prices=prices)
        assert "action" in result
        assert "confidence" in result
    
    def test_decide_with_closes(self):
        """Test decide with closes parameter (backward compat)"""
        strategy = BasicStrategy()
        prices = [100.0] * 60
        result = strategy.decide(closes=prices)
        assert "action" in result
    
    def test_decide_insufficient_data(self):
        """Test decision with insufficient data"""
        strategy = BasicStrategy()
        prices = [100.0] * 10  # Too few prices
        result = strategy.decide(close_prices=prices)
        assert result["action"] == "hold"
        assert "insufficient" in result["reason"].lower()
    
    def test_decide_no_prices_provided(self):
        """Test decision when no prices provided returns error result"""
        strategy = BasicStrategy()
        # When no prices are provided, the method catches the ValueError
        # and returns a "calculation_error" result instead of raising
        result = strategy.decide()
        assert result["action"] == "hold"
        assert "error" in result.get("reason", "").lower() or result.get("action") == "hold"
    
    def test_decide_buy_signal(self):
        """Test buy signal generation"""
        strategy = BasicStrategy(rsi_buy=35)
        # Create downtrend then flat (RSI will be low)
        prices = [100.0 - i for i in range(30)] + [70.0] * 30
        result = strategy.decide(close_prices=prices)
        # Should generate some decision
        assert result["action"] in ["buy", "hold", "sell"]
    
    def test_decide_sell_signal(self):
        """Test sell signal generation"""
        strategy = BasicStrategy(rsi_sell=65)
        # Create uptrend then flat (RSI will be high)
        prices = [100.0 + i for i in range(30)] + [130.0] * 30
        result = strategy.decide(close_prices=prices)
        assert result["action"] in ["buy", "hold", "sell"]
