"""
Core Trading Strategies Tests
Comprehensive test suite for trading strategies module focusing on core functionality
without complex observability integration.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import numpy as np

# Direct imports for testing
from backend.strategies.trading_strategies import (
    SignalType,
    OrderType,
    TradingSignal,
    StrategyPerformance,
    BaseStrategy,
    EnsembleStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    RebalancingStrategy,
    StatisticalArbitrageStrategy,
    StrategyManager
)


class TestDataStructures:
    """Test trading strategy data structures"""

    def test_trading_signal_creation(self):
        """Test TradingSignal dataclass creation and validation"""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0,
            stop_loss=140.0,
            take_profit=160.0,
            position_size=100.0,
            metadata={"test": "data"}
        )
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.8
        assert signal.target_price == 150.0
        assert signal.stop_loss == 140.0
        assert signal.take_profit == 160.0
        assert signal.position_size == 100.0
        assert signal.metadata == {"test": "data"}

    def test_signal_type_enum(self):
        """Test SignalType enum values"""
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
        assert SignalType.HOLD.value == "HOLD"

    def test_order_type_enum(self):
        """Test OrderType enum values"""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"

    def test_strategy_performance_creation(self):
        """Test StrategyPerformance dataclass"""
        perf = StrategyPerformance(
            strategy_name="test_strategy",
            total_returns=0.15,
            sharpe_ratio=1.2,
            max_drawdown=-0.05,
            win_rate=0.65,
            total_trades=100,
            avg_trade_duration=timedelta(days=2),
            last_updated=datetime.now()
        )
        
        assert perf.strategy_name == "test_strategy"
        assert perf.total_returns == 0.15
        assert perf.sharpe_ratio == 1.2
        assert perf.max_drawdown == -0.05
        assert perf.win_rate == 0.65
        assert perf.total_trades == 100


class TestBaseStrategyAbstract:
    """Test BaseStrategy abstract class functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_risk_manager = Mock()
        
    def test_base_strategy_initialization(self):
        """Test BaseStrategy initialization"""
        # Cannot instantiate abstract class directly
        with pytest.raises(TypeError):
            BaseStrategy(self.mock_risk_manager)

    def test_base_strategy_abstract_methods(self):
        """Test abstract method requirements"""
        # Create concrete subclass for testing
        class TestStrategy(BaseStrategy):
            def get_required_features(self):
                return ["price", "volume"]
        
        # Should still fail without generate_signal implementation
        with pytest.raises(TypeError):
            TestStrategy(self.mock_risk_manager)

    def test_base_strategy_common_methods(self):
        """Test BaseStrategy common method implementations"""
        # Create fully concrete implementation
        class ConcreteStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.HOLD,
                    confidence=0.5,
                    target_price=100.0
                )
            
            def get_required_features(self):
                return ["price"]
        
        strategy = ConcreteStrategy("TestStrategy", self.mock_risk_manager)
        
        # Test initialization values
        assert strategy.name == "TestStrategy"
        assert strategy.risk_manager == self.mock_risk_manager
        assert strategy.is_active is True
        assert strategy.performance_metrics is None
        assert len(strategy.trade_history) == 0

    @pytest.mark.asyncio
    async def test_validate_signal_valid(self):
        """Test signal validation with valid signal"""
        class ConcreteStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    confidence=0.8,
                    target_price=100.0
                )
            
            def get_required_features(self):
                return []
        
        strategy = ConcreteStrategy("TestStrategy", self.mock_risk_manager)
        
        # Mock risk manager assess_position_risk as async
        async def mock_assess_risk(*args, **kwargs):
            return {"approved": True}
        self.mock_risk_manager.assess_position_risk = mock_assess_risk
        
        valid_signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0
        )
        
        # Should not raise exception
        result = await strategy.validate_signal(valid_signal)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_signal_invalid_confidence(self):
        """Test signal validation with invalid confidence"""
        class ConcreteStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    confidence=1.5,  # Invalid > 1.0
                    target_price=100.0
                )
            
            def get_required_features(self):
                return []
        
        strategy = ConcreteStrategy("TestStrategy", self.mock_risk_manager)
        
        # Mock risk manager assess_position_risk as async to reject
        async def mock_assess_risk(*args, **kwargs):
            return {"approved": False}
        self.mock_risk_manager.assess_position_risk = mock_assess_risk
        
        invalid_signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=1.5,  # Invalid
            target_price=150.0
        )
        
        result = await strategy.validate_signal(invalid_signal)
        assert result is False

    def test_calculate_position_size(self):
        """Test position size calculation"""
        class ConcreteStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    confidence=0.8,
                    target_price=100.0
                )
            
            def get_required_features(self):
                return []
        
        strategy = ConcreteStrategy("TestStrategy", self.mock_risk_manager)
        
        # Mock risk manager and settings
        self.mock_risk_manager.get_portfolio_value.return_value = 10000.0
        
        # Mock settings.trading.max_position_size directly
        with patch.object(strategy.settings, 'trading') as mock_trading:
            mock_trading.max_position_size = 1000.0
            
            # Test normal calculation
            size = strategy.calculate_position_size("AAPL", 100.0, 0.8)
            
            # Should be confidence * max_position but limited by risk
            # 2% of 10000 = 200, so max 2 shares at $100 each
            assert size > 0
            assert size <= 2.0  # Risk-limited position


class TestEnsembleStrategy:
    """Test EnsembleStrategy implementation"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_risk_manager = Mock()
        self.mock_ensemble_model = Mock()
        
    def test_ensemble_strategy_initialization(self):
        """Test EnsembleStrategy initialization"""
        strategy = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)
        
        assert strategy.risk_manager == self.mock_risk_manager
        assert strategy.ensemble_model == self.mock_ensemble_model
        assert strategy.is_active is True

    @pytest.mark.asyncio
    async def test_ensemble_generate_signal_buy(self):
        """Test ensemble signal generation for BUY signal"""
        strategy = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Mock ensemble model prediction - needs to return object with ensemble_prediction and ensemble_confidence
        mock_prediction = Mock()
        mock_prediction.ensemble_prediction = 110.0  # Higher than current price
        mock_prediction.ensemble_confidence = 0.9
        
        self.mock_ensemble_model.predict.return_value = mock_prediction
        
        # Create test data
        price_data = pd.DataFrame({
            'close': [100.0, 101.0, 102.0],
            'volume': [1000, 1100, 1200]
        })
        features = pd.DataFrame({'feature1': [1, 2, 3]})
        
        # Mock risk manager
        self.mock_risk_manager.get_portfolio_value.return_value = 10000.0
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]  # Could be either based on return
        assert signal.confidence == 0.9

    @pytest.mark.asyncio
    async def test_ensemble_generate_signal_sell(self):
        """Test ensemble signal generation for SELL signal"""
        strategy = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Mock ensemble model prediction - sell signal
        mock_prediction = Mock()
        mock_prediction.ensemble_prediction = 90.0  # Lower than current price
        mock_prediction.ensemble_confidence = 0.85
        
        self.mock_ensemble_model.predict.return_value = mock_prediction
        
        # Create test data
        price_data = pd.DataFrame({
            'close': [100.0, 99.0, 98.0],
            'volume': [1000, 1100, 1200]
        })
        features = pd.DataFrame({'feature1': [1, 2, 3]})
        
        # Mock risk manager
        self.mock_risk_manager.get_portfolio_value.return_value = 10000.0
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]  # Could be either
        assert signal.confidence == 0.85

    @pytest.mark.asyncio
    async def test_ensemble_generate_signal_hold(self):
        """Test ensemble signal generation for HOLD signal"""
        strategy = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Mock ensemble model prediction - low confidence
        mock_prediction = Mock()
        mock_prediction.ensemble_prediction = 101.0  # Close to current price
        mock_prediction.ensemble_confidence = 0.4  # Below confidence threshold
        
        self.mock_ensemble_model.predict.return_value = mock_prediction
        
        # Create test data
        price_data = pd.DataFrame({
            'close': [100.0, 100.5, 101.0],
            'volume': [1000, 1100, 1200]
        })
        features = pd.DataFrame({'feature1': [1, 2, 3]})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.4
        assert signal.position_size == 0.0

    def test_ensemble_get_required_features(self):
        """Test ensemble strategy required features"""
        strategy = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)
        
        features = strategy.get_required_features()
        
        # Should return the actual features from the implementation
        expected_features = [
            "sma_20", "sma_50", "ema_12", "ema_26", "rsi", "macd", "macd_signal",
            "bb_upper", "bb_lower", "volume_sma", "atr", "adx", "cci", "williams_r",
            "stoch_k", "stoch_d", "momentum", "rate_of_change"
        ]
        assert features == expected_features


class TestMeanReversionStrategy:
    """Test MeanReversionStrategy implementation"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_risk_manager = Mock()
        
    def test_mean_reversion_initialization(self):
        """Test MeanReversionStrategy initialization"""
        strategy = MeanReversionStrategy(self.mock_risk_manager)
        
        assert strategy.oversold_threshold == 30
        assert strategy.overbought_threshold == 70
        assert strategy.risk_manager == self.mock_risk_manager

    @pytest.mark.asyncio
    async def test_mean_reversion_buy_signal(self):
        """Test mean reversion BUY signal generation"""
        strategy = MeanReversionStrategy(self.mock_risk_manager)
        
        # Create price data and features for oversold condition
        price_data = pd.DataFrame({
            'close': [90.0],  # Current price near lower band
            'volume': [1000]
        })
        features = pd.DataFrame({
            'rsi': [25.0],  # Oversold RSI
            'bb_upper': [105.0],
            'bb_lower': [90.5]  # Price below lower band
        })
        
        # Mock risk manager
        self.mock_risk_manager.get_portfolio_value.return_value = 10000.0
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0
        assert signal.target_price == (105.0 + 90.5) / 2  # BB middle

    @pytest.mark.asyncio
    async def test_mean_reversion_sell_signal(self):
        """Test mean reversion SELL signal generation"""
        strategy = MeanReversionStrategy(self.mock_risk_manager)
        
        # Create price data and features for overbought condition
        price_data = pd.DataFrame({
            'close': [105.0],  # Current price near upper band
            'volume': [1000]
        })
        features = pd.DataFrame({
            'rsi': [80.0],  # Overbought RSI
            'bb_upper': [105.2],  # Price near upper band
            'bb_lower': [90.0]
        })
        
        # Mock risk manager
        self.mock_risk_manager.get_portfolio_value.return_value = 10000.0
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0
        assert signal.target_price == (105.2 + 90.0) / 2  # BB middle

    @pytest.mark.asyncio
    async def test_mean_reversion_hold_signal(self):
        """Test mean reversion HOLD signal generation"""
        strategy = MeanReversionStrategy(self.mock_risk_manager)
        
        # Create neutral conditions - RSI and price in middle range
        price_data = pd.DataFrame({
            'close': [100.0],
            'volume': [1000]
        })
        features = pd.DataFrame({
            'rsi': [50.0],  # Neutral RSI
            'bb_upper': [105.0],
            'bb_lower': [95.0]  # Price in middle range
        })
        
        # Mock risk manager to return proper numeric value
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=10000.0)
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.position_size == 0.0

    def test_mean_reversion_required_features(self):
        """Test mean reversion required features"""
        strategy = MeanReversionStrategy(self.mock_risk_manager)
        features = strategy.get_required_features()
        assert features == ["rsi", "bb_upper", "bb_lower"]


class TestMomentumStrategy:
    """Test MomentumStrategy implementation"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_risk_manager = Mock()
        
    def test_momentum_initialization(self):
        """Test MomentumStrategy initialization"""
        strategy = MomentumStrategy(self.mock_risk_manager)
        
        assert strategy.name == "MomentumStrategy"
        assert strategy.risk_manager == self.mock_risk_manager

    @pytest.mark.asyncio
    async def test_momentum_buy_signal(self):
        """Test momentum BUY signal generation"""
        strategy = MomentumStrategy(self.mock_risk_manager)
        
        # Create upward momentum data
        price_data = pd.DataFrame({
            'close': [100.0],
            'volume': [1000]
        })
        features = pd.DataFrame({
            'macd': [2.0],  # Positive MACD
            'macd_signal': [1.0],  # MACD above signal
            'sma_20': [95.0],  # Short MA above long MA
            'sma_50': [90.0]
        })
        
        # Mock risk manager
        self.mock_risk_manager.get_portfolio_value.return_value = 10000.0
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0

    @pytest.mark.asyncio
    async def test_momentum_sell_signal(self):
        """Test momentum SELL signal generation"""
        strategy = MomentumStrategy(self.mock_risk_manager)
        
        # Create downward momentum data
        price_data = pd.DataFrame({
            'close': [100.0],
            'volume': [1000]
        })
        features = pd.DataFrame({
            'macd': [-2.0],  # Negative MACD
            'macd_signal': [-1.0],  # MACD below signal
            'sma_20': [105.0],  # Short MA below long MA
            'sma_50': [110.0]
        })
        
        # Mock risk manager
        self.mock_risk_manager.get_portfolio_value.return_value = 10000.0
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0

    @pytest.mark.asyncio
    async def test_momentum_hold_signal(self):
        """Test momentum HOLD signal with neutral conditions"""
        strategy = MomentumStrategy(self.mock_risk_manager)
        
        # Create neutral momentum data
        price_data = pd.DataFrame({
            'close': [100.0],
            'volume': [1000]
        })
        features = pd.DataFrame({
            'macd': [0.1],  # Weak MACD
            'macd_signal': [0.0],  # Close to signal
            'sma_20': [100.0],  # MAs close together
            'sma_50': [100.5]
        })
        
        # Mock risk manager to return proper numeric value
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=10000.0)
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.position_size == 0.0

    def test_momentum_required_features(self):
        """Test momentum required features"""
        strategy = MomentumStrategy(self.mock_risk_manager)
        features = strategy.get_required_features()
        assert features == ["macd", "macd_signal", "sma_20", "sma_50"]


class TestStatisticalArbitrageStrategy:
    """Test StatisticalArbitrageStrategy implementation"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_risk_manager = Mock()
        
    def test_stat_arb_initialization(self):
        """Test StatisticalArbitrageStrategy initialization"""
        strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)
        
        assert strategy.name == "StatArbStrategy"
        assert strategy.lookback_period == 60
        assert strategy.entry_threshold == 2.0

    @pytest.mark.asyncio
    async def test_stat_arb_buy_signal(self):
        """Test statistical arbitrage BUY signal"""
        strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)
        
        # Create data where current price is well below mean (for z-score calculation)
        # Need 60+ data points for lookback period
        prices = [100.0] * 59 + [85.0]  # Current price significantly low
        price_data = pd.DataFrame({
            'close': prices,
            'volume': [1000] * 60
        })
        features = pd.DataFrame({'feature1': [1] * 60})
        
        # Mock risk manager
        self.mock_risk_manager.get_portfolio_value.return_value = 10000.0
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0
        assert "z_score" in signal.metadata
        assert signal.metadata["z_score"] < -2.0  # Negative z-score for buy

    @pytest.mark.asyncio
    async def test_stat_arb_sell_signal(self):
        """Test statistical arbitrage SELL signal"""
        strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)
        
        # Create data where current price is well above mean
        # Need 60+ data points for lookback period
        prices = [100.0] * 59 + [115.0]  # Current price significantly high
        price_data = pd.DataFrame({
            'close': prices,
            'volume': [1000] * 60
        })
        features = pd.DataFrame({'feature1': [1] * 60})
        
        # Mock risk manager
        self.mock_risk_manager.get_portfolio_value.return_value = 10000.0
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0
        assert "z_score" in signal.metadata
        assert signal.metadata["z_score"] > 2.0  # Positive z-score for sell

    @pytest.mark.asyncio
    async def test_stat_arb_zero_std_deviation(self):
        """Test statistical arbitrage with zero standard deviation"""
        strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)
        
        # All prices identical = zero std deviation
        prices = [100] * 10
        price_data = pd.DataFrame({
            'close': prices,
            'volume': [1000] * 10
        })
        features = pd.DataFrame({'feature1': [1] * 10})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0

    def test_stat_arb_required_features(self):
        """Test statistical arbitrage required features"""
        strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)
        features = strategy.get_required_features()
        assert features == []
