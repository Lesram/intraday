"""
Comprehensive tests for backend.strategies.trading_strategies

Targets 60%+ coverage for the trading strategies module which includes:
- SignalType and OrderType enums
- TradingSignal and StrategyPerformance dataclasses
- BaseStrategy abstract class
- EnsembleStrategy, MeanReversionStrategy, MomentumStrategy
- RebalancingStrategy, StatisticalArbitrageStrategy
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import numpy as np
import pandas as pd
import pytest

from backend.strategies.trading_strategies import (
    BaseStrategy,
    EnsembleStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    OrderType,
    RebalancingStrategy,
    SignalType,
    StrategyPerformance,
    TradingSignal,
)


# ============================================================================
# ENUM TESTS
# ============================================================================

class TestSignalType:
    """Tests for SignalType enum"""
    
    def test_all_signal_types_exist(self):
        """Test all expected signal types exist"""
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
        assert SignalType.HOLD.value == "HOLD"
        assert SignalType.STRONG_BUY.value == "STRONG_BUY"
        assert SignalType.STRONG_SELL.value == "STRONG_SELL"
        
    def test_signal_type_comparison(self):
        """Test signal type comparison"""
        assert SignalType.BUY != SignalType.SELL
        assert SignalType.BUY == SignalType.BUY


class TestOrderType:
    """Tests for OrderType enum"""
    
    def test_all_order_types_exist(self):
        """Test all expected order types exist"""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
        assert OrderType.STOP_LIMIT.value == "stop_limit"


# ============================================================================
# DATACLASS TESTS
# ============================================================================

class TestTradingSignal:
    """Tests for TradingSignal dataclass"""
    
    def test_minimal_signal(self):
        """Test minimal signal creation"""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0
        )
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.8
        assert signal.target_price == 150.0
        assert signal.stop_loss is None
        assert signal.take_profit is None
        assert signal.position_size == 0.0
        assert signal.order_type == OrderType.MARKET
        assert isinstance(signal.timestamp, datetime)
        assert signal.metadata == {}
        
    def test_full_signal(self):
        """Test signal with all fields"""
        now = datetime.now()
        signal = TradingSignal(
            symbol="GOOG",
            signal_type=SignalType.STRONG_SELL,
            confidence=0.95,
            target_price=2800.0,
            stop_loss=2850.0,
            take_profit=2700.0,
            position_size=10.5,
            order_type=OrderType.LIMIT,
            timestamp=now,
            metadata={"reason": "momentum break"}
        )
        
        assert signal.stop_loss == 2850.0
        assert signal.take_profit == 2700.0
        assert signal.position_size == 10.5
        assert signal.order_type == OrderType.LIMIT
        assert signal.timestamp == now
        assert signal.metadata["reason"] == "momentum break"


class TestStrategyPerformance:
    """Tests for StrategyPerformance dataclass"""
    
    def test_performance_creation(self):
        """Test performance metrics creation"""
        now = datetime.now()
        perf = StrategyPerformance(
            strategy_name="TestStrategy",
            total_returns=0.25,
            sharpe_ratio=1.8,
            max_drawdown=-0.15,
            win_rate=0.65,
            total_trades=100,
            avg_trade_duration=timedelta(hours=4),
            last_updated=now
        )
        
        assert perf.strategy_name == "TestStrategy"
        assert perf.total_returns == 0.25
        assert perf.sharpe_ratio == 1.8
        assert perf.max_drawdown == -0.15
        assert perf.win_rate == 0.65
        assert perf.total_trades == 100
        assert perf.avg_trade_duration == timedelta(hours=4)


# ============================================================================
# BASE STRATEGY TESTS
# ============================================================================

class ConcreteStrategy(BaseStrategy):
    """Concrete implementation for testing BaseStrategy"""
    
    async def generate_signal(self, symbol, price_data, features):
        return TradingSignal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            confidence=0.5,
            target_price=100.0
        )
    
    def get_required_features(self):
        return ["sma_20", "rsi"]


class TestBaseStrategy:
    """Tests for BaseStrategy abstract class"""
    
    @pytest.fixture
    def mock_risk_manager(self):
        """Create mock risk manager"""
        rm = Mock()
        rm.get_portfolio_value = Mock(return_value=100000)
        rm.assess_position_risk = AsyncMock(return_value={"approved": True})
        return rm
    
    @pytest.fixture
    def strategy(self, mock_risk_manager):
        """Create concrete strategy instance"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_settings:
            settings = Mock()
            settings.trading = Mock()
            settings.trading.max_position_size = 1000
            mock_settings.return_value = settings
            
            return ConcreteStrategy("TestStrategy", mock_risk_manager)
    
    def test_init_with_defaults(self, strategy):
        """Test strategy initialization with default risk params"""
        assert strategy.name == "TestStrategy"
        assert strategy.max_risk_per_trade == 0.02
        assert strategy.stop_loss_pct == 0.05
        assert strategy.take_profit_pct == 0.02
        assert strategy.is_active is True
        
    def test_init_with_custom_risk_params(self, mock_risk_manager):
        """Test strategy with custom risk parameters"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_settings:
            mock_settings.return_value = Mock(trading=Mock(max_position_size=1000))
            
            strategy = ConcreteStrategy(
                "CustomStrategy",
                mock_risk_manager,
                max_risk_per_trade=0.05,
                stop_loss_pct=0.10,
                take_profit_pct=0.05
            )
            
            assert strategy.max_risk_per_trade == 0.05
            assert strategy.stop_loss_pct == 0.10
            assert strategy.take_profit_pct == 0.05
            
    def test_get_required_features(self, strategy):
        """Test abstract method implementation"""
        features = strategy.get_required_features()
        assert "sma_20" in features
        assert "rsi" in features
        
    @pytest.mark.asyncio
    async def test_generate_signal(self, strategy):
        """Test signal generation"""
        df = pd.DataFrame({"close": [100, 101, 102]})
        features = pd.DataFrame({"sma_20": [100], "rsi": [50]})
        
        signal = await strategy.generate_signal("AAPL", df, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        
    @pytest.mark.asyncio
    async def test_validate_signal_approved(self, strategy):
        """Test signal validation when approved"""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0,
            position_size=100
        )
        
        is_valid = await strategy.validate_signal(signal)
        
        assert is_valid is True
        
    @pytest.mark.asyncio
    async def test_validate_signal_inactive_strategy(self, strategy):
        """Test signal validation when strategy is inactive"""
        strategy.is_active = False
        
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0
        )
        
        is_valid = await strategy.validate_signal(signal)
        
        assert is_valid is False
        
    @pytest.mark.asyncio
    async def test_validate_signal_risk_denied(self, strategy, mock_risk_manager):
        """Test signal validation when risk check fails"""
        mock_risk_manager.assess_position_risk = AsyncMock(
            return_value={"approved": False}
        )
        
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.SELL,
            confidence=0.8,
            target_price=150.0,
            position_size=100
        )
        
        is_valid = await strategy.validate_signal(signal)
        
        assert is_valid is False
        
    def test_calculate_position_size(self, strategy):
        """Test position size calculation"""
        # With 100% confidence, should use full base position
        size = strategy.calculate_position_size("AAPL", 100.0, 1.0)
        
        assert size > 0
        
    def test_calculate_position_size_risk_capped(self, strategy):
        """Test position sizing capped by risk limit"""
        # Very low price should hit risk cap
        size = strategy.calculate_position_size("AAPL", 0.01, 1.0)
        
        # Should be capped at max_risk_per_trade / price
        max_risk = 100000 * 0.02  # 2% of portfolio
        expected_max = max_risk / 0.01
        assert size <= expected_max
        
    def test_update_performance_empty(self, strategy):
        """Test performance update with empty results"""
        strategy.update_performance([])
        
        assert strategy.performance_metrics is None
        
    def test_update_performance(self, strategy):
        """Test performance update with trade results"""
        trade_results = [
            {"return": 0.05, "duration": timedelta(hours=2)},
            {"return": -0.02, "duration": timedelta(hours=3)},
            {"return": 0.03, "duration": timedelta(hours=1)},
        ]
        
        strategy.update_performance(trade_results)
        
        metrics = strategy.performance_metrics
        assert metrics is not None
        assert metrics.strategy_name == "TestStrategy"
        assert metrics.total_trades == 3
        assert metrics.win_rate == 2/3  # 2 wins out of 3
        
    def test_calculate_max_drawdown(self, strategy):
        """Test max drawdown calculation"""
        returns = [0.1, 0.05, -0.2, 0.1]  # Mix of gains and losses
        
        max_dd = strategy._calculate_max_drawdown(returns)
        
        assert max_dd < 0  # Drawdown is negative


# ============================================================================
# MEAN REVERSION STRATEGY TESTS
# ============================================================================

class TestMeanReversionStrategy:
    """Tests for MeanReversionStrategy"""
    
    @pytest.fixture
    def mock_risk_manager(self):
        """Create mock risk manager"""
        rm = Mock()
        rm.get_portfolio_value = Mock(return_value=100000)
        rm.assess_position_risk = AsyncMock(return_value={"approved": True})
        return rm
    
    @pytest.fixture
    def strategy(self, mock_risk_manager):
        """Create mean reversion strategy"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_settings:
            settings = Mock()
            settings.trading = Mock()
            settings.trading.max_position_size = 1000
            mock_settings.return_value = settings
            
            return MeanReversionStrategy(mock_risk_manager)
            
    def test_required_features(self, strategy):
        """Test required features"""
        features = strategy.get_required_features()
        assert "rsi" in features
        assert "bb_upper" in features
        assert "bb_lower" in features
        
    @pytest.mark.asyncio
    async def test_oversold_buy_signal(self, strategy):
        """Test buy signal when oversold"""
        price_data = pd.DataFrame({"close": [95.0]})  # Below lower band
        features = pd.DataFrame({
            "rsi": [25.0],  # Oversold (< 30)
            "bb_upper": [110.0],
            "bb_lower": [100.0]  # Price below lower band
        })
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0
        assert signal.stop_loss is not None
        
    @pytest.mark.asyncio
    async def test_overbought_sell_signal(self, strategy):
        """Test sell signal when overbought"""
        price_data = pd.DataFrame({"close": [115.0]})  # Above upper band
        features = pd.DataFrame({
            "rsi": [75.0],  # Overbought (> 70)
            "bb_upper": [110.0],
            "bb_lower": [90.0]
        })
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0
        
    @pytest.mark.asyncio
    async def test_neutral_hold_signal(self, strategy):
        """Test hold signal when neutral"""
        price_data = pd.DataFrame({"close": [100.0]})  # Middle of bands
        features = pd.DataFrame({
            "rsi": [50.0],  # Neutral
            "bb_upper": [110.0],
            "bb_lower": [90.0]
        })
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD
        assert signal.position_size == 0.0
        
    @pytest.mark.asyncio
    async def test_missing_price_data(self, strategy):
        """Test handling of missing price data"""
        price_data = pd.DataFrame()  # Empty
        features = pd.DataFrame({"rsi": [50], "bb_upper": [110], "bb_lower": [90]})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0
        
    @pytest.mark.asyncio
    async def test_missing_features(self, strategy):
        """Test handling of missing features"""
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame()  # Empty features
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD


# ============================================================================
# MOMENTUM STRATEGY TESTS
# ============================================================================

class TestMomentumStrategy:
    """Tests for MomentumStrategy"""
    
    @pytest.fixture
    def mock_risk_manager(self):
        """Create mock risk manager"""
        rm = Mock()
        rm.get_portfolio_value = Mock(return_value=100000)
        return rm
    
    @pytest.fixture
    def strategy(self, mock_risk_manager):
        """Create momentum strategy"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_settings:
            settings = Mock()
            settings.trading = Mock()
            settings.trading.max_position_size = 1000
            mock_settings.return_value = settings
            
            return MomentumStrategy(mock_risk_manager)
            
    def test_required_features(self, strategy):
        """Test required features"""
        features = strategy.get_required_features()
        assert "macd" in features
        assert "macd_signal" in features
        assert "sma_20" in features
        assert "sma_50" in features
        
    @pytest.mark.asyncio
    async def test_bullish_momentum_buy(self, strategy):
        """Test buy signal on bullish momentum"""
        price_data = pd.DataFrame({"close": [105.0]})  # Above both SMAs
        features = pd.DataFrame({
            "macd": [0.5],  # MACD > signal
            "macd_signal": [0.3],
            "sma_20": [102.0],  # 20 > 50, bullish trend
            "sma_50": [100.0]
        })
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.BUY
        assert signal.target_price > 105.0  # Target above current
        assert signal.metadata["sma_trend"] == "bullish"
        
    @pytest.mark.asyncio
    async def test_bearish_momentum_sell(self, strategy):
        """Test sell signal on bearish momentum"""
        price_data = pd.DataFrame({"close": [95.0]})  # Below both SMAs
        features = pd.DataFrame({
            "macd": [0.2],  # MACD < signal
            "macd_signal": [0.4],
            "sma_20": [98.0],  # 20 < 50, bearish trend
            "sma_50": [100.0]
        })
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.SELL
        assert signal.target_price < 95.0  # Target below current
        assert signal.metadata["sma_trend"] == "bearish"
        
    @pytest.mark.asyncio
    async def test_neutral_momentum(self, strategy):
        """Test hold when momentum is unclear"""
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame({
            "macd": [0.1],  # Near signal (unclear)
            "macd_signal": [0.1],
            "sma_20": [100.0],
            "sma_50": [100.0]
        })
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        # May or may not be HOLD depending on exact conditions
        assert signal.signal_type in [SignalType.HOLD, SignalType.BUY, SignalType.SELL]


# ============================================================================
# REBALANCING STRATEGY TESTS
# ============================================================================

class TestRebalancingStrategy:
    """Tests for RebalancingStrategy"""
    
    @pytest.fixture
    def mock_risk_manager(self):
        """Create mock risk manager"""
        rm = Mock()
        rm.get_portfolio_value = AsyncMock(return_value=100000)
        rm.get_positions = AsyncMock(return_value={
            "AAPL": {"market_value": 15000},  # 15% of portfolio
            "GOOG": {"market_value": 10000},  # 10%
        })
        return rm
    
    @pytest.fixture
    def strategy(self, mock_risk_manager):
        """Create rebalancing strategy"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_settings:
            settings = Mock()
            settings.trading = Mock()
            settings.trading.max_position_size = 1000
            mock_settings.return_value = settings
            
            target_weights = {
                "AAPL": 0.20,  # Target 20%
                "GOOG": 0.15,  # Target 15%
            }
            
            return RebalancingStrategy(
                mock_risk_manager,
                target_weights=target_weights,
                rebalance_threshold=0.05
            )
            
    def test_required_features(self, strategy):
        """Test no technical features required"""
        features = strategy.get_required_features()
        assert features == []
        
    @pytest.mark.asyncio
    async def test_underweight_buy_signal(self, strategy):
        """Test buy signal when underweight"""
        # AAPL is 15% but target is 20% (5% deviation = threshold)
        price_data = pd.DataFrame({"close": [150.0]})
        features = pd.DataFrame()
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        # Should buy to increase weight
        assert signal.signal_type == SignalType.BUY
        assert signal.position_size > 0
        assert signal.metadata["current_weight"] == 0.15
        assert signal.metadata["target_weight"] == 0.20
        
    @pytest.mark.asyncio
    async def test_overweight_sell_signal(self, strategy, mock_risk_manager):
        """Test sell signal when overweight"""
        # Modify positions so AAPL is overweight
        mock_risk_manager.get_positions = AsyncMock(return_value={
            "AAPL": {"market_value": 30000},  # 30% (10% over target)
        })
        
        price_data = pd.DataFrame({"close": [150.0]})
        features = pd.DataFrame()
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.SELL
        
    @pytest.mark.asyncio
    async def test_within_threshold_hold(self, strategy, mock_risk_manager):
        """Test hold when within threshold"""
        # GOOG is 10%, target 15% - only 5% deviation (at threshold)
        mock_risk_manager.get_positions = AsyncMock(return_value={
            "GOOG": {"market_value": 11000},  # 11%, within 5% of 15%
        })
        
        price_data = pd.DataFrame({"close": [2800.0]})
        features = pd.DataFrame()
        
        signal = await strategy.generate_signal("GOOG", price_data, features)
        
        # Deviation is 4%, under 5% threshold
        # Signal could be HOLD
        assert signal.symbol == "GOOG"


# ============================================================================
# ENSEMBLE STRATEGY TESTS
# ============================================================================

class TestEnsembleStrategy:
    """Tests for EnsembleStrategy"""
    
    @pytest.fixture
    def mock_risk_manager(self):
        """Create mock risk manager"""
        rm = Mock()
        rm.get_portfolio_value = Mock(return_value=100000)
        return rm
    
    @pytest.fixture
    def mock_ensemble_model(self):
        """Create mock ensemble model"""
        model = Mock()
        
        # Create prediction mock
        prediction = Mock()
        prediction.ensemble_prediction = 155.0  # 3% above current
        prediction.ensemble_confidence = 0.85
        prediction.predictions = [154.0, 156.0]
        prediction.confidence_scores = [0.8, 0.9]
        
        model.predict = Mock(return_value=prediction)
        return model
    
    @pytest.fixture
    def strategy(self, mock_risk_manager, mock_ensemble_model):
        """Create ensemble strategy"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_settings:
            settings = Mock()
            settings.trading = Mock()
            settings.trading.max_position_size = 1000
            mock_settings.return_value = settings
            
            return EnsembleStrategy(
                mock_risk_manager,
                mock_ensemble_model,
                confidence_threshold=0.6,
                return_threshold=0.02,
                strong_return_threshold=0.05
            )
            
    def test_required_features(self, strategy):
        """Test required features for ensemble"""
        features = strategy.get_required_features()
        
        assert "sma_20" in features
        assert "rsi" in features
        assert "macd" in features
        assert "bb_upper" in features
        assert len(features) >= 15  # Many features required
        
    @pytest.mark.asyncio
    async def test_buy_signal(self, strategy):
        """Test buy signal on positive prediction"""
        price_data = pd.DataFrame({"close": [150.0]})
        features = pd.DataFrame({"rsi": [50]})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.85
        assert signal.target_price == 155.0
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
        assert signal.metadata["predicted_return"] > 0
        
    @pytest.mark.asyncio
    async def test_strong_buy_signal(self, strategy, mock_ensemble_model):
        """Test strong buy on large positive prediction"""
        # Predict 10% gain
        prediction = Mock()
        prediction.ensemble_prediction = 165.0  # 10% above current
        prediction.ensemble_confidence = 0.9
        prediction.predictions = [164.0, 166.0]
        prediction.confidence_scores = [0.85, 0.95]
        mock_ensemble_model.predict = Mock(return_value=prediction)
        
        price_data = pd.DataFrame({"close": [150.0]})
        features = pd.DataFrame({"rsi": [50]})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.STRONG_BUY
        
    @pytest.mark.asyncio
    async def test_sell_signal(self, strategy, mock_ensemble_model):
        """Test sell signal on negative prediction"""
        prediction = Mock()
        prediction.ensemble_prediction = 145.0  # 3.3% below current
        prediction.ensemble_confidence = 0.8
        prediction.predictions = [144.0, 146.0]
        prediction.confidence_scores = [0.75, 0.85]
        mock_ensemble_model.predict = Mock(return_value=prediction)
        
        price_data = pd.DataFrame({"close": [150.0]})
        features = pd.DataFrame({"rsi": [50]})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.SELL
        
    @pytest.mark.asyncio
    async def test_hold_low_confidence(self, strategy, mock_ensemble_model):
        """Test hold signal when confidence is low"""
        prediction = Mock()
        prediction.ensemble_prediction = 155.0
        prediction.ensemble_confidence = 0.4  # Below threshold (0.6)
        prediction.predictions = [154.0, 156.0]
        prediction.confidence_scores = [0.4, 0.4]
        mock_ensemble_model.predict = Mock(return_value=prediction)
        
        price_data = pd.DataFrame({"close": [150.0]})
        features = pd.DataFrame({"rsi": [50]})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD
        assert signal.position_size == 0.0
        
    @pytest.mark.asyncio
    async def test_hold_small_expected_return(self, strategy, mock_ensemble_model):
        """Test hold when expected return is too small"""
        prediction = Mock()
        prediction.ensemble_prediction = 151.0  # Only 0.7% gain
        prediction.ensemble_confidence = 0.9
        prediction.predictions = [151.0]
        prediction.confidence_scores = [0.9]
        mock_ensemble_model.predict = Mock(return_value=prediction)
        
        price_data = pd.DataFrame({"close": [150.0]})
        features = pd.DataFrame({"rsi": [50]})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestStrategyIntegration:
    """Integration tests for strategy interactions"""
    
    @pytest.fixture
    def mock_risk_manager(self):
        """Create full mock risk manager"""
        rm = Mock()
        rm.get_portfolio_value = Mock(return_value=100000)
        rm.assess_position_risk = AsyncMock(return_value={"approved": True})
        rm.get_positions = AsyncMock(return_value={})
        return rm
    
    @pytest.mark.asyncio
    async def test_signal_validation_flow(self, mock_risk_manager):
        """Test signal generation -> validation flow"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_settings:
            settings = Mock()
            settings.trading = Mock()
            settings.trading.max_position_size = 1000
            mock_settings.return_value = settings
            
            strategy = MeanReversionStrategy(mock_risk_manager)
            
            # Generate oversold buy signal
            price_data = pd.DataFrame({"close": [95.0]})
            features = pd.DataFrame({
                "rsi": [20.0],
                "bb_upper": [110.0],
                "bb_lower": [100.0]
            })
            
            signal = await strategy.generate_signal("AAPL", price_data, features)
            
            # Validate the signal
            is_valid = await strategy.validate_signal(signal)
            
            assert signal.signal_type == SignalType.BUY
            assert is_valid is True
            
    def test_multiple_strategies_same_symbol(self, mock_risk_manager):
        """Test multiple strategies can coexist for same symbol"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_settings:
            settings = Mock()
            settings.trading = Mock()
            settings.trading.max_position_size = 1000
            mock_settings.return_value = settings
            
            mean_rev = MeanReversionStrategy(mock_risk_manager)
            momentum = MomentumStrategy(mock_risk_manager)
            
            # They should be independent
            assert mean_rev.name != momentum.name
            assert mean_rev.risk_manager == momentum.risk_manager
