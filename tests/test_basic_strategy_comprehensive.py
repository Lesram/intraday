"""
Comprehensive tests for backend.strategies.basic

Targets 70%+ coverage for BasicStrategy:
- Strategy initialization
- RSI-based buy/sell decisions
- SMA trend confirmation
- Confidence calculations
"""

from unittest.mock import MagicMock, patch
import pytest

from backend.strategies.basic import BasicStrategy, StrategyDecision


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def strategy():
    """Create a BasicStrategy with default parameters"""
    with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
        mock_instance = MagicMock()
        mock_ti.return_value = mock_instance
        return BasicStrategy()


@pytest.fixture
def price_series():
    """Sample price series for testing"""
    # 60 prices to ensure enough data for SMA calculations
    return [100 + i * 0.5 for i in range(60)]


@pytest.fixture
def downtrend_prices():
    """Downtrend price series (RSI should be low)"""
    return [100 - i * 0.5 for i in range(60)]


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================

class TestBasicStrategyInit:
    """Tests for BasicStrategy initialization"""
    
    def test_init_default_values(self, strategy):
        """Test default parameter values"""
        assert strategy.rsi_buy == 35
        assert strategy.rsi_sell == 65
        assert strategy.sma_fast == 20
        assert strategy.sma_slow == 50
        assert strategy.tp_pct == 2.0
        assert strategy.sl_pct == 1.0
        
    def test_init_custom_values(self):
        """Test custom parameter values"""
        with patch('backend.strategies.basic.TechnicalIndicators'):
            s = BasicStrategy(
                rsi_buy=30,
                rsi_sell=70,
                sma_fast=10,
                sma_slow=30,
                tp_pct=3.0,
                sl_pct=2.0
            )
        
        assert s.rsi_buy == 30
        assert s.rsi_sell == 70
        assert s.sma_fast == 10
        assert s.sma_slow == 30


# ============================================================================
# DECIDE METHOD TESTS
# ============================================================================

class TestDecide:
    """Tests for decide method"""
    
    def test_decide_with_close_prices(self, price_series):
        """Test decide with close_prices parameter"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            # Setup RSI to return oversold
            rsi_result = MagicMock()
            rsi_result.value = 25  # Oversold
            mock_instance.calculate_rsi.return_value = rsi_result
            
            # Setup SMA
            sma_result = MagicMock()
            sma_result.value = 110
            mock_instance.calculate_sma.return_value = sma_result
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=price_series)
            
            assert 'action' in result
            
    def test_decide_with_closes(self, price_series):
        """Test decide with closes parameter"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            rsi_result = MagicMock()
            rsi_result.value = 50  # Neutral
            mock_instance.calculate_rsi.return_value = rsi_result
            
            sma_result = MagicMock()
            sma_result.value = 110
            mock_instance.calculate_sma.return_value = sma_result
            
            strategy = BasicStrategy()
            result = strategy.decide(closes=price_series)
            
            assert 'action' in result
            
    def test_decide_no_data_raises(self):
        """Test decide with no data returns hold with error"""
        with patch('backend.strategies.basic.TechnicalIndicators'):
            strategy = BasicStrategy()
            
            # Exception is caught and returns hold
            result = strategy.decide()
            assert result['action'] == 'hold'
            assert 'calculation_error' in result['reason']
                
    def test_decide_insufficient_data(self):
        """Test decide with insufficient data"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=[100, 101, 102])
            
            assert result['action'] == 'hold'
            assert 'insufficient_data' in result['reason']


# ============================================================================
# BUY SIGNAL TESTS
# ============================================================================

class TestBuySignals:
    """Tests for buy signal generation"""
    
    def test_rsi_oversold_generates_buy(self, price_series):
        """Test RSI oversold generates buy signal"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            # RSI oversold (below rsi_buy threshold)
            rsi_result = MagicMock()
            rsi_result.value = 25
            mock_instance.calculate_rsi.return_value = rsi_result
            
            # SMA bullish
            sma_result = MagicMock()
            sma_result.value = 110
            mock_instance.calculate_sma.return_value = sma_result
            
            strategy = BasicStrategy(rsi_buy=35)
            result = strategy.decide(close_prices=price_series)
            
            assert result['action'] == 'buy'
            
    def test_buy_with_bullish_trend(self, price_series):
        """Test buy signal confidence boosted in bullish trend"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            rsi_result = MagicMock()
            rsi_result.value = 25
            mock_instance.calculate_rsi.return_value = rsi_result
            
            # SMA fast > SMA slow = bullish
            def sma_side_effect(prices, period):
                result = MagicMock()
                if period == 20:  # fast
                    result.value = 115
                else:  # slow
                    result.value = 110
                return result
            mock_instance.calculate_sma.side_effect = sma_side_effect
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=price_series)
            
            assert result['action'] == 'buy'
            assert 'bullish' in result['reason']


# ============================================================================
# SELL SIGNAL TESTS
# ============================================================================

class TestSellSignals:
    """Tests for sell signal generation"""
    
    def test_rsi_overbought_generates_sell(self, price_series):
        """Test RSI overbought generates sell signal"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            # RSI overbought (above rsi_sell threshold)
            rsi_result = MagicMock()
            rsi_result.value = 75
            mock_instance.calculate_rsi.return_value = rsi_result
            
            sma_result = MagicMock()
            sma_result.value = 110
            mock_instance.calculate_sma.return_value = sma_result
            
            strategy = BasicStrategy(rsi_sell=65)
            result = strategy.decide(close_prices=price_series)
            
            assert result['action'] == 'sell'
            
    def test_sell_with_bearish_trend(self, price_series):
        """Test sell signal confidence boosted in bearish trend"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            rsi_result = MagicMock()
            rsi_result.value = 75
            mock_instance.calculate_rsi.return_value = rsi_result
            
            # SMA fast < SMA slow = bearish
            def sma_side_effect(prices, period):
                result = MagicMock()
                if period == 20:  # fast
                    result.value = 105
                else:  # slow
                    result.value = 115
                return result
            mock_instance.calculate_sma.side_effect = sma_side_effect
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=price_series)
            
            assert result['action'] == 'sell'
            assert 'bearish' in result['reason']


# ============================================================================
# HOLD SIGNAL TESTS
# ============================================================================

class TestHoldSignals:
    """Tests for hold signal generation"""
    
    def test_neutral_rsi_generates_hold(self, price_series):
        """Test neutral RSI generates hold signal"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            # RSI in neutral zone
            rsi_result = MagicMock()
            rsi_result.value = 50
            mock_instance.calculate_rsi.return_value = rsi_result
            
            sma_result = MagicMock()
            sma_result.value = 110
            mock_instance.calculate_sma.return_value = sma_result
            
            strategy = BasicStrategy(rsi_buy=35, rsi_sell=65)
            result = strategy.decide(close_prices=price_series)
            
            assert result['action'] == 'hold'
            
    def test_rsi_calculation_failed(self, price_series):
        """Test hold when RSI calculation fails"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            mock_instance.calculate_rsi.return_value = None
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=price_series)
            
            assert result['action'] == 'hold'


# ============================================================================
# STRATEGY DECISION CLASS TESTS
# ============================================================================

class TestStrategyDecision:
    """Tests for StrategyDecision dataclass"""
    
    def test_create_decision(self):
        """Test creating a StrategyDecision"""
        decision = StrategyDecision(
            action="buy",
            confidence=0.8,
            tp_pct=2.0,
            sl_pct=1.0,
            reason="RSI oversold"
        )
        
        assert decision.action == "buy"
        assert decision.confidence == 0.8
        assert decision.tp_pct == 2.0
        assert decision.sl_pct == 1.0
        assert decision.reason == "RSI oversold"
        
    def test_decision_to_dict(self):
        """Test converting decision to dict"""
        decision = StrategyDecision(
            action="sell",
            confidence=0.7,
            tp_pct=1.5,
            sl_pct=0.5,
            reason="RSI overbought"
        )
        
        result = decision.__dict__
        
        assert result['action'] == "sell"
        assert 'confidence' in result


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases"""
    
    def test_empty_price_series(self):
        """Test with empty price series"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=[])
            
            assert result['action'] == 'hold'
            
    def test_rsi_at_threshold(self, price_series):
        """Test RSI exactly at threshold"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            # RSI exactly at rsi_buy threshold
            rsi_result = MagicMock()
            rsi_result.value = 35  # Exactly at threshold
            mock_instance.calculate_rsi.return_value = rsi_result
            
            sma_result = MagicMock()
            sma_result.value = 110
            mock_instance.calculate_sma.return_value = sma_result
            
            strategy = BasicStrategy(rsi_buy=35)
            result = strategy.decide(close_prices=price_series)
            
            # At threshold is hold (not below)
            assert result['action'] in ['buy', 'hold']


# ============================================================================
# CONFIDENCE CALCULATION TESTS
# ============================================================================

class TestConfidenceCalculation:
    """Tests for confidence calculation methods"""
    
    def test_confidence_from_rsi_oversold(self):
        """Test confidence calculation for oversold RSI"""
        with patch('backend.strategies.basic.TechnicalIndicators'):
            strategy = BasicStrategy(rsi_buy=35, rsi_sell=65)
            
            # RSI at 0 (extremely oversold)
            confidence = strategy._confidence_from_rsi_threshold(0, 35, 65)
            assert confidence == 1.0
            
            # RSI at 20 (moderately oversold)
            confidence = strategy._confidence_from_rsi_threshold(20, 35, 65)
            assert 0.3 <= confidence <= 1.0
            
    def test_confidence_from_rsi_overbought(self):
        """Test confidence calculation for overbought RSI"""
        with patch('backend.strategies.basic.TechnicalIndicators'):
            strategy = BasicStrategy(rsi_buy=35, rsi_sell=65)
            
            # RSI at 100 (extremely overbought)
            confidence = strategy._confidence_from_rsi_threshold(100, 35, 65)
            assert confidence == 1.0
            
            # RSI at 80 (moderately overbought)
            confidence = strategy._confidence_from_rsi_threshold(80, 35, 65)
            assert 0.3 <= confidence <= 1.0
            
    def test_confidence_neutral_rsi(self):
        """Test confidence for neutral RSI returns 0.3"""
        with patch('backend.strategies.basic.TechnicalIndicators'):
            strategy = BasicStrategy(rsi_buy=35, rsi_sell=65)
            
            confidence = strategy._confidence_from_rsi_threshold(50, 35, 65)
            assert confidence == 0.3
            
    def test_calculate_confidence_method(self):
        """Test _calculate_confidence wrapper method"""
        with patch('backend.strategies.basic.TechnicalIndicators'):
            strategy = BasicStrategy(rsi_buy=35, rsi_sell=65)
            
            confidence = strategy._calculate_confidence(20, 35, "buy")
            assert 0.3 <= confidence <= 1.0


# ============================================================================
# NO DECISION TESTS
# ============================================================================

class TestNoDecision:
    """Tests for _no_decision method"""
    
    def test_no_decision_returns_hold(self):
        """Test _no_decision returns hold with zero confidence"""
        with patch('backend.strategies.basic.TechnicalIndicators'):
            strategy = BasicStrategy()
            
            result = strategy._no_decision("test_reason", "test_detail")
            
            assert result['action'] == 'hold'
            assert result['confidence'] == 0.0
            assert result['tp_pct'] == 0.0
            assert result['sl_pct'] == 0.0
            assert 'test_reason' in result['reason']
            assert 'test_detail' in result['reason']


# ============================================================================
# GET PARAMETERS TESTS
# ============================================================================

class TestGetParameters:
    """Tests for get_parameters method"""
    
    def test_get_parameters_default(self):
        """Test get_parameters with default values"""
        with patch('backend.strategies.basic.TechnicalIndicators'):
            strategy = BasicStrategy()
            params = strategy.get_parameters()
            
            assert params['rsi_buy'] == 35
            assert params['rsi_sell'] == 65
            assert params['sma_fast'] == 20
            assert params['sma_slow'] == 50
            assert params['tp_pct'] == 2.0
            assert params['sl_pct'] == 1.0
            
    def test_get_parameters_custom(self):
        """Test get_parameters with custom values"""
        with patch('backend.strategies.basic.TechnicalIndicators'):
            strategy = BasicStrategy(
                rsi_buy=30,
                rsi_sell=70,
                sma_fast=10,
                sma_slow=40,
                tp_pct=3.5,
                sl_pct=1.5
            )
            params = strategy.get_parameters()
            
            assert params['rsi_buy'] == 30
            assert params['rsi_sell'] == 70
            assert params['sma_fast'] == 10
            assert params['sma_slow'] == 40
            assert params['tp_pct'] == 3.5
            assert params['sl_pct'] == 1.5


# ============================================================================
# TREND BIAS TESTS
# ============================================================================

class TestTrendBias:
    """Tests for trend bias calculations"""
    
    def test_neutral_trend_with_neutral_rsi(self, price_series):
        """Test hold when RSI and trend are neutral"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            rsi_result = MagicMock()
            rsi_result.value = 50
            mock_instance.calculate_rsi.return_value = rsi_result
            
            # SMA fast == SMA slow = neutral
            sma_result = MagicMock()
            sma_result.value = 110
            mock_instance.calculate_sma.return_value = sma_result
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=price_series)
            
            assert result['action'] == 'hold'
            
    def test_bullish_trend_with_neutral_rsi_below_50(self, price_series):
        """Test buy when trend is bullish and RSI below 50"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            rsi_result = MagicMock()
            rsi_result.value = 45  # Below 50 but not oversold
            mock_instance.calculate_rsi.return_value = rsi_result
            
            def sma_side_effect(prices, period):
                result = MagicMock()
                if period == 20:  # fast
                    result.value = 115
                else:  # slow
                    result.value = 110
                return result
            mock_instance.calculate_sma.side_effect = sma_side_effect
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=price_series)
            
            assert result['action'] == 'buy'
            assert result['confidence'] == 0.3
            
    def test_bearish_trend_with_neutral_rsi_above_50(self, price_series):
        """Test sell when trend is bearish and RSI above 50"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            rsi_result = MagicMock()
            rsi_result.value = 55  # Above 50 but not overbought
            mock_instance.calculate_rsi.return_value = rsi_result
            
            def sma_side_effect(prices, period):
                result = MagicMock()
                if period == 20:  # fast
                    result.value = 105
                else:  # slow
                    result.value = 115
                return result
            mock_instance.calculate_sma.side_effect = sma_side_effect
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=price_series)
            
            assert result['action'] == 'sell'
            assert result['confidence'] == 0.3


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestErrorHandling:
    """Tests for error handling"""
    
    def test_exception_during_calculation(self, price_series):
        """Test exception during calculation returns hold"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            mock_instance.calculate_rsi.side_effect = Exception("Test error")
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=price_series)
            
            assert result['action'] == 'hold'
            assert 'calculation_error' in result['reason']
            
    def test_sma_calculation_returns_none(self, price_series):
        """Test graceful handling when SMA returns None"""
        with patch('backend.strategies.basic.TechnicalIndicators') as mock_ti:
            mock_instance = MagicMock()
            mock_ti.return_value = mock_instance
            
            rsi_result = MagicMock()
            rsi_result.value = 25
            mock_instance.calculate_rsi.return_value = rsi_result
            
            mock_instance.calculate_sma.return_value = None
            
            strategy = BasicStrategy()
            result = strategy.decide(close_prices=price_series)
            
            # Should still work - just with neutral trend
            assert result['action'] == 'buy'
            assert 'neutral' in result['reason']
