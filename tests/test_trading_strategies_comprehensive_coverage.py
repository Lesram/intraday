"""
Comprehensive test suite for Trading Strategies module (backend/strategies/trading_strategies.py)
Phase 10: Critical Business Logic Module Testing

This test suite validates the core trading strategy framework including strategy 
implementations, signal generation, performance metrics, and strategy management.
Target: 40-60% coverage of the 320-statement trading strategies module.
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from typing import Dict, Any

# Import the trading strategies module
from backend.strategies.trading_strategies import (
    SignalType, OrderType, TradingSignal, StrategyPerformance, BaseStrategy,
    EnsembleStrategy, MeanReversionStrategy, MomentumStrategy, 
    RebalancingStrategy, StatisticalArbitrageStrategy, StrategyManager
)


class MockRiskManager:
    """Mock risk manager for testing."""
    
    def __init__(self):
        self.portfolio_value = 100000.0
        self.positions = {
            "AAPL": {"market_value": 10000.0, "quantity": 50},
            "MSFT": {"market_value": 8000.0, "quantity": 25}
        }
        
    async def assess_position_risk(self, symbol: str, quantity: float, side: str) -> Dict[str, Any]:
        """Mock risk assessment."""
        return {
            "approved": True,
            "max_quantity": quantity * 2,
            "risk_score": 0.3,
            "warnings": []
        }
        
    def get_portfolio_value(self) -> float:
        """Mock portfolio value."""
        return self.portfolio_value
        
    def get_positions(self) -> Dict[str, Dict[str, float]]:
        """Mock positions."""
        return self.positions


class MockEnsembleModel:
    """Mock ensemble model for testing."""
    
    def __init__(self):
        self.prediction_value = 155.0
        self.confidence_value = 0.75
        
    def predict(self, price_data: pd.DataFrame, features: pd.DataFrame, symbol: str):
        """Mock prediction."""
        mock_prediction = Mock()
        mock_prediction.ensemble_prediction = self.prediction_value
        mock_prediction.ensemble_confidence = self.confidence_value
        mock_prediction.predictions = [150.0, 155.0, 160.0]
        mock_prediction.confidence_scores = [0.7, 0.75, 0.8]
        return mock_prediction


@pytest.fixture
def mock_risk_manager():
    """Fixture for mock risk manager."""
    return MockRiskManager()


@pytest.fixture
def mock_ensemble_model():
    """Fixture for mock ensemble model."""
    return MockEnsembleModel()


@pytest.fixture
def sample_price_data():
    """Fixture for sample price data."""
    dates = pd.date_range(start='2025-01-01', periods=100, freq='D')
    prices = 150 + np.random.randn(100).cumsum() * 2
    
    return pd.DataFrame({
        'open': prices + np.random.randn(100) * 0.5,
        'high': prices + np.random.randn(100) * 0.5 + 1,
        'low': prices + np.random.randn(100) * 0.5 - 1,
        'close': prices,
        'volume': np.random.randint(1000, 10000, 100)
    }, index=dates)


@pytest.fixture
def sample_features():
    """Fixture for sample technical features."""
    data_length = 100
    
    return pd.DataFrame({
        'sma_20': 150 + np.random.randn(data_length) * 0.5,
        'sma_50': 149 + np.random.randn(data_length) * 0.3,
        'ema_12': 151 + np.random.randn(data_length) * 0.4,
        'ema_26': 150.5 + np.random.randn(data_length) * 0.3,
        'rsi': np.random.uniform(20, 80, data_length),
        'macd': np.random.randn(data_length) * 0.5,
        'macd_signal': np.random.randn(data_length) * 0.3,
        'bb_upper': 155 + np.random.randn(data_length) * 0.5,
        'bb_lower': 145 + np.random.randn(data_length) * 0.5,
        'volume_sma': np.random.randint(2000, 8000, data_length),
        'atr': np.random.uniform(1, 5, data_length),
        'adx': np.random.uniform(10, 50, data_length),
        'cci': np.random.uniform(-200, 200, data_length),
        'williams_r': np.random.uniform(-100, 0, data_length),
        'stoch_k': np.random.uniform(0, 100, data_length),
        'stoch_d': np.random.uniform(0, 100, data_length),
        'momentum': np.random.randn(data_length) * 2,
        'rate_of_change': np.random.uniform(-5, 5, data_length)
    })


class TestSignalAndPerformanceTypes:
    """Test signal types, enums, and performance dataclasses."""
    
    def test_signal_type_enum(self):
        """Test SignalType enum values."""
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
        assert SignalType.HOLD.value == "HOLD"
        assert SignalType.STRONG_BUY.value == "STRONG_BUY"
        assert SignalType.STRONG_SELL.value == "STRONG_SELL"
        
    def test_order_type_enum(self):
        """Test OrderType enum values."""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
        assert OrderType.STOP_LIMIT.value == "stop_limit"
        
    def test_trading_signal_creation(self):
        """Test TradingSignal dataclass creation."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.85,
            target_price=155.0,
            stop_loss=145.0,
            take_profit=160.0,
            position_size=100.0
        )
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.85
        assert signal.target_price == 155.0
        assert signal.stop_loss == 145.0
        assert signal.take_profit == 160.0
        assert signal.position_size == 100.0
        assert signal.order_type == OrderType.MARKET  # Default value
        assert isinstance(signal.timestamp, datetime)
        assert isinstance(signal.metadata, dict)
        
    def test_trading_signal_defaults(self):
        """Test TradingSignal default values."""
        signal = TradingSignal(
            symbol="MSFT",
            signal_type=SignalType.HOLD,
            confidence=0.5,
            target_price=300.0
        )
        
        assert signal.stop_loss is None
        assert signal.take_profit is None
        assert signal.position_size == 0.0
        assert signal.order_type == OrderType.MARKET
        assert len(signal.metadata) == 0
        
    def test_strategy_performance_dataclass(self):
        """Test StrategyPerformance dataclass."""
        performance = StrategyPerformance(
            strategy_name="TestStrategy",
            total_returns=0.15,
            sharpe_ratio=1.2,
            max_drawdown=-0.08,
            win_rate=0.65,
            total_trades=100,
            avg_trade_duration=timedelta(hours=24),
            last_updated=datetime.now()
        )
        
        assert performance.strategy_name == "TestStrategy"
        assert performance.total_returns == 0.15
        assert performance.sharpe_ratio == 1.2
        assert performance.max_drawdown == -0.08
        assert performance.win_rate == 0.65
        assert performance.total_trades == 100
        assert isinstance(performance.avg_trade_duration, timedelta)
        assert isinstance(performance.last_updated, datetime)


class TestBaseStrategy:
    """Test BaseStrategy abstract base class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = MockRiskManager()
        
    def test_base_strategy_initialization(self):
        """Test BaseStrategy initialization."""
        # Create a concrete implementation for testing
        class TestStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(symbol=symbol, signal_type=SignalType.HOLD, confidence=0.5, target_price=100.0)
                
            def get_required_features(self):
                return ["sma_20", "rsi"]
        
        strategy = TestStrategy("TestStrategy", self.mock_risk_manager)
        
        assert strategy.name == "TestStrategy"
        assert strategy.risk_manager == self.mock_risk_manager
        assert isinstance(strategy.positions, dict)
        assert isinstance(strategy.trade_history, list)
        assert strategy.performance_metrics is None
        assert strategy.is_active is True
        
    @pytest.mark.asyncio
    async def test_validate_signal_active_strategy(self):
        """Test signal validation for active strategy."""
        class TestStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(symbol=symbol, signal_type=SignalType.BUY, confidence=0.7, target_price=150.0)
                
            def get_required_features(self):
                return []
        
        strategy = TestStrategy("TestStrategy", self.mock_risk_manager)
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=155.0,
            position_size=50.0
        )
        
        result = await strategy.validate_signal(signal)
        assert result is True
        
    @pytest.mark.asyncio
    async def test_validate_signal_inactive_strategy(self):
        """Test signal validation for inactive strategy."""
        class TestStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(symbol=symbol, signal_type=SignalType.BUY, confidence=0.7, target_price=150.0)
                
            def get_required_features(self):
                return []
        
        strategy = TestStrategy("TestStrategy", self.mock_risk_manager)
        strategy.is_active = False
        
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=155.0,
            position_size=50.0
        )
        
        result = await strategy.validate_signal(signal)
        assert result is False
        
    def test_calculate_position_size(self):
        """Test position size calculation."""
        class TestStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(symbol=symbol, signal_type=SignalType.BUY, confidence=0.7, target_price=150.0)
                
            def get_required_features(self):
                return []
        
        strategy = TestStrategy("TestStrategy", self.mock_risk_manager)
        
        # Mock settings
        strategy.settings = Mock()
        strategy.settings.trading = Mock()
        strategy.settings.trading.max_position_size = 1000.0
        
        position_size = strategy.calculate_position_size("AAPL", 150.0, 0.8)
        
        # Should be scaled by confidence and risk constraints
        assert position_size > 0
        assert position_size <= 1000.0  # Max position constraint
        
    def test_update_performance_empty_trades(self):
        """Test performance update with empty trade results."""
        class TestStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(symbol=symbol, signal_type=SignalType.BUY, confidence=0.7, target_price=150.0)
                
            def get_required_features(self):
                return []
        
        strategy = TestStrategy("TestStrategy", self.mock_risk_manager)
        strategy.update_performance([])
        
        assert strategy.performance_metrics is None
        
    def test_update_performance_with_trades(self):
        """Test performance update with trade results."""
        class TestStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(symbol=symbol, signal_type=SignalType.BUY, confidence=0.7, target_price=150.0)
                
            def get_required_features(self):
                return []
        
        strategy = TestStrategy("TestStrategy", self.mock_risk_manager)
        
        trade_results = [
            {"return": 0.05, "duration": timedelta(hours=24)},
            {"return": -0.02, "duration": timedelta(hours=48)},
            {"return": 0.03, "duration": timedelta(hours=12)}
        ]
        
        strategy.update_performance(trade_results)
        
        assert strategy.performance_metrics is not None
        assert strategy.performance_metrics.strategy_name == "TestStrategy"
        assert strategy.performance_metrics.total_returns == 0.06  # Sum of returns
        assert strategy.performance_metrics.total_trades == 3
        assert strategy.performance_metrics.win_rate == 2/3  # 2 positive out of 3
        
    def test_calculate_max_drawdown(self):
        """Test maximum drawdown calculation."""
        class TestStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(symbol=symbol, signal_type=SignalType.BUY, confidence=0.7, target_price=150.0)
                
            def get_required_features(self):
                return []
        
        strategy = TestStrategy("TestStrategy", self.mock_risk_manager)
        
        returns = [0.1, -0.05, -0.1, 0.08, -0.03]
        max_drawdown = strategy._calculate_max_drawdown(returns)
        
        assert isinstance(max_drawdown, float)
        assert max_drawdown <= 0  # Drawdown should be negative


class TestEnsembleStrategy:
    """Test EnsembleStrategy implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = MockRiskManager()
        self.mock_ensemble_model = MockEnsembleModel()
        self.strategy = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)
        
    @pytest.mark.asyncio
    async def test_ensemble_signal_generation_buy(self, sample_price_data, sample_features):
        """Test ensemble signal generation for buy signal."""
        # Set prediction for strong buy signal
        self.mock_ensemble_model.prediction_value = 165.0  # 10% above current price
        self.mock_ensemble_model.confidence_value = 0.85
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, sample_features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]
        assert signal.confidence == 0.85
        assert signal.target_price == 165.0
        assert signal.position_size > 0
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
        
    @pytest.mark.asyncio
    async def test_ensemble_signal_generation_sell(self, sample_price_data, sample_features):
        """Test ensemble signal generation for sell signal."""
        # Set prediction for strong sell signal - need much lower prediction
        current_price = sample_price_data["close"].iloc[-1]
        self.mock_ensemble_model.prediction_value = current_price * 0.85  # 15% below current price
        self.mock_ensemble_model.confidence_value = 0.9
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, sample_features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]
        assert signal.confidence == 0.9
        assert signal.target_price == self.mock_ensemble_model.prediction_value
        assert signal.position_size > 0
        
    @pytest.mark.asyncio
    async def test_ensemble_signal_generation_hold(self, sample_price_data, sample_features):
        """Test ensemble signal generation for hold signal."""
        # Set prediction for hold signal (low confidence)
        self.mock_ensemble_model.prediction_value = 151.0  # Small change
        self.mock_ensemble_model.confidence_value = 0.4  # Below threshold
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, sample_features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.4
        assert signal.position_size == 0.0
        
    def test_ensemble_required_features(self):
        """Test ensemble strategy required features."""
        features = self.strategy.get_required_features()
        
        expected_features = [
            "sma_20", "sma_50", "ema_12", "ema_26", "rsi", "macd", "macd_signal",
            "bb_upper", "bb_lower", "volume_sma", "atr", "adx", "cci", "williams_r",
            "stoch_k", "stoch_d", "momentum", "rate_of_change"
        ]
        
        assert len(features) == len(expected_features)
        for feature in expected_features:
            assert feature in features


class TestMeanReversionStrategy:
    """Test MeanReversionStrategy implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = MockRiskManager()
        self.strategy = MeanReversionStrategy(self.mock_risk_manager)
        
    @pytest.mark.asyncio
    async def test_mean_reversion_oversold_signal(self, sample_price_data):
        """Test mean reversion signal for oversold condition."""
        # Create features indicating oversold condition
        features = pd.DataFrame({
            'rsi': [25.0] * len(sample_price_data),  # Oversold RSI
            'bb_upper': [155.0] * len(sample_price_data),
            'bb_lower': [145.0] * len(sample_price_data)
        })
        
        # Set price near lower band
        sample_price_data.loc[sample_price_data.index[-1], 'close'] = 146.0
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.5
        assert signal.position_size > 0
        
    @pytest.mark.asyncio
    async def test_mean_reversion_overbought_signal(self, sample_price_data):
        """Test mean reversion signal for overbought condition."""
        # Create features indicating overbought condition
        features = pd.DataFrame({
            'rsi': [75.0] * len(sample_price_data),  # Overbought RSI
            'bb_upper': [155.0] * len(sample_price_data),
            'bb_lower': [145.0] * len(sample_price_data)
        })
        
        # Set price near upper band
        sample_price_data.loc[sample_price_data.index[-1], 'close'] = 154.0
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0.5
        assert signal.position_size > 0
        
    @pytest.mark.asyncio
    async def test_mean_reversion_hold_signal(self, sample_price_data):
        """Test mean reversion hold signal for neutral conditions."""
        # Create features indicating neutral condition
        features = pd.DataFrame({
            'rsi': [50.0] * len(sample_price_data),  # Neutral RSI
            'bb_upper': [155.0] * len(sample_price_data),
            'bb_lower': [145.0] * len(sample_price_data)
        })
        
        # Set price in middle of bands
        sample_price_data.loc[sample_price_data.index[-1], 'close'] = 150.0
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        
    @pytest.mark.asyncio
    async def test_mean_reversion_insufficient_data(self):
        """Test mean reversion with insufficient data."""
        empty_price_data = pd.DataFrame(columns=['close'])
        empty_features = pd.DataFrame(columns=['rsi', 'bb_upper', 'bb_lower'])
        
        signal = await self.strategy.generate_signal("AAPL", empty_price_data, empty_features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0
        assert signal.target_price == 0.0
        
    def test_mean_reversion_required_features(self):
        """Test mean reversion strategy required features."""
        features = self.strategy.get_required_features()
        
        expected_features = ["rsi", "bb_upper", "bb_lower"]
        assert features == expected_features


class TestMomentumStrategy:
    """Test MomentumStrategy implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = MockRiskManager()
        self.strategy = MomentumStrategy(self.mock_risk_manager)
        
    @pytest.mark.asyncio
    async def test_momentum_bullish_signal(self, sample_price_data):
        """Test momentum strategy bullish signal."""
        # Create features indicating bullish momentum
        features = pd.DataFrame({
            'macd': [0.5] * len(sample_price_data),  # MACD above signal
            'macd_signal': [0.3] * len(sample_price_data),
            'sma_20': [152.0] * len(sample_price_data),  # Bullish MA trend
            'sma_50': [150.0] * len(sample_price_data)
        })
        
        # Set price above moving averages
        sample_price_data.loc[sample_price_data.index[-1], 'close'] = 155.0
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.5
        assert signal.position_size > 0
        assert signal.metadata["strategy"] == "momentum"
        
    @pytest.mark.asyncio
    async def test_momentum_bearish_signal(self, sample_price_data):
        """Test momentum strategy bearish signal."""
        # Create features indicating bearish momentum
        features = pd.DataFrame({
            'macd': [-0.5] * len(sample_price_data),  # MACD below signal
            'macd_signal': [-0.3] * len(sample_price_data),
            'sma_20': [148.0] * len(sample_price_data),  # Bearish MA trend
            'sma_50': [150.0] * len(sample_price_data)
        })
        
        # Set price below moving averages
        sample_price_data.loc[sample_price_data.index[-1], 'close'] = 145.0
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0.5
        assert signal.position_size > 0
        
    @pytest.mark.asyncio
    async def test_momentum_hold_signal(self, sample_price_data):
        """Test momentum strategy hold signal."""
        # Create features indicating no clear momentum
        features = pd.DataFrame({
            'macd': [0.1] * len(sample_price_data),  # Weak MACD signal
            'macd_signal': [0.05] * len(sample_price_data),
            'sma_20': [150.5] * len(sample_price_data),  # Weak MA trend
            'sma_50': [150.0] * len(sample_price_data)
        })
        
        sample_price_data.loc[sample_price_data.index[-1], 'close'] = 151.0
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        
    def test_momentum_required_features(self):
        """Test momentum strategy required features."""
        features = self.strategy.get_required_features()
        
        expected_features = ["macd", "macd_signal", "sma_20", "sma_50"]
        assert features == expected_features


class TestRebalancingStrategy:
    """Test RebalancingStrategy implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = MockRiskManager()
        self.target_weights = {"AAPL": 0.3, "MSFT": 0.2, "GOOGL": 0.5}
        self.strategy = RebalancingStrategy(self.mock_risk_manager, self.target_weights)
        
    @pytest.mark.asyncio
    async def test_rebalancing_buy_signal(self, sample_price_data, sample_features):
        """Test rebalancing buy signal when underweight."""
        # AAPL is currently 10% (10000/100000) but target is 30%
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, sample_features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.5  # Significant deviation
        assert signal.position_size > 0
        assert signal.order_type == OrderType.MARKET
        assert signal.metadata["strategy"] == "rebalancing"
        
    @pytest.mark.asyncio
    async def test_rebalancing_sell_signal(self, sample_price_data, sample_features):
        """Test rebalancing sell signal when overweight."""
        # Set MSFT to be overweight
        self.mock_risk_manager.positions["MSFT"]["market_value"] = 30000.0  # 30% vs 20% target
        
        signal = await self.strategy.generate_signal("MSFT", sample_price_data, sample_features)
        
        assert signal.symbol == "MSFT"
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0.5
        assert signal.position_size > 0
        
    @pytest.mark.asyncio
    async def test_rebalancing_hold_signal(self, sample_price_data, sample_features):
        """Test rebalancing hold signal when near target weight."""
        # Set up a symbol with near-target allocation
        self.mock_risk_manager.positions["BALANCED"] = {"market_value": 19500.0}  # ~19.5% vs 20% target
        
        signal = await self.strategy.generate_signal("BALANCED", sample_price_data, sample_features)
        
        assert signal.symbol == "BALANCED"
        assert signal.signal_type == SignalType.HOLD
        assert signal.position_size == 0.0
        
    @pytest.mark.asyncio
    async def test_rebalancing_new_symbol(self, sample_price_data, sample_features):
        """Test rebalancing for new symbol not in portfolio."""
        signal = await self.strategy.generate_signal("NVDA", sample_price_data, sample_features)
        
        assert signal.symbol == "NVDA"
        assert signal.signal_type == SignalType.HOLD  # No target weight = no signal
        
    def test_rebalancing_required_features(self):
        """Test rebalancing strategy required features."""
        features = self.strategy.get_required_features()
        
        assert features == []  # Rebalancing doesn't need technical features


class TestStatisticalArbitrageStrategy:
    """Test StatisticalArbitrageStrategy implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = MockRiskManager()
        self.strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)
        
    @pytest.mark.asyncio
    async def test_stat_arb_buy_signal(self):
        """Test statistical arbitrage buy signal for undervalued asset."""
        # Create price data where current price is well below mean
        prices = [150.0] * 60 + [140.0]  # Last price significantly below mean
        dates = pd.date_range(start='2025-01-01', periods=61, freq='D')
        
        price_data = pd.DataFrame({
            'close': prices
        }, index=dates)
        
        features = pd.DataFrame()  # Not used by stat arb
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.5
        assert signal.position_size > 0
        assert signal.target_price == 150.0  # Mean price
        assert "z_score" in signal.metadata
        
    @pytest.mark.asyncio
    async def test_stat_arb_sell_signal(self):
        """Test statistical arbitrage sell signal for overvalued asset."""
        # Create price data where current price is well above mean
        prices = [150.0] * 60 + [160.0]  # Last price significantly above mean
        dates = pd.date_range(start='2025-01-01', periods=61, freq='D')
        
        price_data = pd.DataFrame({
            'close': prices
        }, index=dates)
        
        features = pd.DataFrame()
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0.5
        assert signal.position_size > 0
        
    @pytest.mark.asyncio
    async def test_stat_arb_insufficient_data(self):
        """Test statistical arbitrage with insufficient data."""
        # Create price data with less than lookback period
        dates = pd.date_range(start='2025-01-01', periods=30, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 30
        }, index=dates)
        
        features = pd.DataFrame()
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0
        
    @pytest.mark.asyncio
    async def test_stat_arb_zero_volatility(self):
        """Test statistical arbitrage with zero price volatility."""
        # All prices are identical (zero standard deviation)
        prices = [150.0] * 61
        dates = pd.date_range(start='2025-01-01', periods=61, freq='D')
        
        price_data = pd.DataFrame({
            'close': prices
        }, index=dates)
        
        features = pd.DataFrame()
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0
        
    def test_stat_arb_required_features(self):
        """Test statistical arbitrage required features."""
        features = self.strategy.get_required_features()
        
        assert features == []  # Stat arb doesn't need technical features


class TestStrategyManager:
    """Test StrategyManager for managing multiple strategies."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = MockRiskManager()
        self.mock_ensemble_model = MockEnsembleModel()
        self.manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
    def test_strategy_manager_initialization(self):
        """Test strategy manager initialization."""
        assert len(self.manager.strategies) == 4  # All strategies initialized
        assert "ensemble" in self.manager.strategies
        assert "mean_reversion" in self.manager.strategies
        assert "momentum" in self.manager.strategies
        assert "stat_arb" in self.manager.strategies
        
        # Check equal weights
        assert len(self.manager.strategy_weights) == 4
        for weight in self.manager.strategy_weights.values():
            assert weight == 0.25  # Equal weighting
            
    @pytest.mark.asyncio
    async def test_combined_signal_generation(self, sample_price_data, sample_features):
        """Test combined signal generation from all strategies."""
        signal = await self.manager.generate_combined_signal("AAPL", sample_price_data, sample_features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type in SignalType
        assert 0.0 <= signal.confidence <= 1.0
        assert signal.target_price > 0
        assert "strategy_signals" in signal.metadata
        assert "signal_votes" in signal.metadata
        assert "strategy_weights" in signal.metadata
        
    @pytest.mark.asyncio
    async def test_combined_signal_no_active_strategies(self, sample_price_data, sample_features):
        """Test combined signal when no strategies are active."""
        # Deactivate all strategies
        for strategy in self.manager.strategies.values():
            strategy.is_active = False
            
        signal = await self.manager.generate_combined_signal("AAPL", sample_price_data, sample_features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0
        assert signal.target_price == 0.0
        
    def test_strategy_activation_deactivation(self):
        """Test strategy activation and deactivation."""
        # Deactivate a strategy
        self.manager.deactivate_strategy("mean_reversion")
        assert not self.manager.strategies["mean_reversion"].is_active
        
        # Activate it back
        self.manager.activate_strategy("mean_reversion")
        assert self.manager.strategies["mean_reversion"].is_active
        
        # Test invalid strategy name
        self.manager.activate_strategy("nonexistent")  # Should not raise error
        self.manager.deactivate_strategy("nonexistent")  # Should not raise error
        
    def test_strategy_weights_update(self):
        """Test strategy weights update based on performance."""
        performance_data = {
            "ensemble": StrategyPerformance(
                strategy_name="ensemble",
                total_returns=0.2,
                sharpe_ratio=1.5,
                max_drawdown=-0.05,
                win_rate=0.7,
                total_trades=50,
                avg_trade_duration=timedelta(hours=24),
                last_updated=datetime.now()
            ),
            "mean_reversion": StrategyPerformance(
                strategy_name="mean_reversion",
                total_returns=0.1,
                sharpe_ratio=0.8,
                max_drawdown=-0.1,
                win_rate=0.6,
                total_trades=30,
                avg_trade_duration=timedelta(hours=48),
                last_updated=datetime.now()
            )
        }
        
        self.manager.update_strategy_weights(performance_data)
        
        # Ensemble should have higher weight due to better performance
        assert self.manager.strategy_weights["ensemble"] > self.manager.strategy_weights["mean_reversion"]
        
        # All weights should sum to 1.0
        total_weight = sum(self.manager.strategy_weights.values())
        assert abs(total_weight - 1.0) < 1e-6
        
    def test_get_strategy_status(self):
        """Test getting strategy status information."""
        status = self.manager.get_strategy_status()
        
        assert len(status) == 4
        for strategy_name, strategy_status in status.items():
            assert "is_active" in strategy_status
            assert "weight" in strategy_status
            assert "performance" in strategy_status
            assert "trade_count" in strategy_status
            assert "required_features" in strategy_status
            
            assert isinstance(strategy_status["is_active"], bool)
            assert isinstance(strategy_status["weight"], float)
            assert isinstance(strategy_status["trade_count"], int)
            assert isinstance(strategy_status["required_features"], list)
            
    def test_calculate_combined_position_size(self, sample_price_data):
        """Test combined position size calculation."""
        # Create mock strategy signals
        strategy_signals = {
            "ensemble": TradingSignal(
                symbol="AAPL",
                signal_type=SignalType.BUY,
                confidence=0.8,
                target_price=155.0,
                position_size=100.0
            ),
            "momentum": TradingSignal(
                symbol="AAPL",
                signal_type=SignalType.BUY,
                confidence=0.7,
                target_price=153.0,
                position_size=80.0
            )
        }
        
        current_price = sample_price_data["close"].iloc[-1]
        combined_confidence = 0.75
        
        position_size = self.manager._calculate_combined_position_size(
            "AAPL", current_price, combined_confidence, strategy_signals
        )
        
        assert position_size > 0
        assert isinstance(position_size, float)
        
    def test_calculate_combined_position_size_no_signals(self):
        """Test combined position size calculation with no position signals."""
        strategy_signals = {
            "ensemble": TradingSignal(
                symbol="AAPL",
                signal_type=SignalType.HOLD,
                confidence=0.8,
                target_price=155.0,
                position_size=0.0
            )
        }
        
        position_size = self.manager._calculate_combined_position_size(
            "AAPL", 150.0, 0.75, strategy_signals
        )
        
        assert position_size == 0.0


class TestStrategyIntegration:
    """Test strategy integration and error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = MockRiskManager()
        self.mock_ensemble_model = MockEnsembleModel()
        
    @pytest.mark.asyncio
    async def test_strategy_with_risk_rejection(self, sample_price_data, sample_features):
        """Test strategy behavior when risk manager rejects signal."""
        # Mock risk manager to reject signals
        self.mock_risk_manager.assess_position_risk = AsyncMock(return_value={"approved": False})
        
        strategy = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=155.0,
            position_size=100.0
        )
        
        is_valid = await strategy.validate_signal(signal)
        assert is_valid is False
        
    @pytest.mark.asyncio
    async def test_strategy_manager_with_strategy_error(self, sample_price_data, sample_features):
        """Test strategy manager handling of strategy errors."""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Mock one strategy to raise an exception
        manager.strategies["ensemble"].generate_signal = AsyncMock(side_effect=Exception("Test error"))
        
        # Should still generate signal from other strategies
        signal = await manager.generate_combined_signal("AAPL", sample_price_data, sample_features)
        
        assert signal.symbol == "AAPL"
        # Should get signal from remaining strategies
        assert signal.signal_type in SignalType


if __name__ == "__main__":
    pytest.main([__file__])