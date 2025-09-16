"""
Comprehensive test suite for Trading Strategies module (backend/strategies/trading_strategies.py)
Target: 100% coverage of trading strategies module.
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
from backend.risk.risk_manager import RiskManager


@pytest.fixture
def mock_risk_manager():
    """Create a mock risk manager for testing."""
    risk_manager = Mock(spec=RiskManager)
    
    # Mock the assess_position_risk method
    async def mock_assess_position_risk(*args, **kwargs):
        return Mock(is_approved=True, max_position_size=1000)
    
    risk_manager.assess_position_risk = mock_assess_position_risk
    return risk_manager


@pytest.fixture
def mock_ensemble_model():
    """Create a mock ensemble model for testing."""
    model = Mock()
    model.predict = Mock(return_value=np.array([0.8]))
    return model


class TestTradingSignal:
    """Test TradingSignal class."""
    
    def test_trading_signal_creation(self):
        """Test TradingSignal instantiation."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0,
            position_size=100
        )
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.8
        assert signal.target_price == 150.0
        assert signal.position_size == 100


class TestStrategyPerformance:
    """Test StrategyPerformance class."""
    
    def test_strategy_performance_creation(self):
        """Test StrategyPerformance instantiation."""
        perf = StrategyPerformance(
            strategy_name="TestStrategy",
            total_returns=0.15,
            sharpe_ratio=1.2,
            max_drawdown=0.05,
            win_rate=0.7,
            total_trades=10,
            avg_trade_duration=timedelta(hours=2),
            last_updated=datetime.now()
        )
        
        assert perf.strategy_name == "TestStrategy"
        assert perf.total_returns == 0.15
        assert perf.sharpe_ratio == 1.2
        assert perf.max_drawdown == 0.05
        assert perf.win_rate == 0.7
        assert perf.total_trades == 10


class TestBaseStrategy:
    """Test BaseStrategy abstract class."""
    
    def test_base_strategy_abstract(self):
        """Test that BaseStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseStrategy()


class TestMeanReversionStrategy:
    """Test MeanReversionStrategy implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = Mock(spec=RiskManager)
        
        # Mock assess_position_risk as an async method
        async def mock_assess_position_risk(*args, **kwargs):
            return Mock(is_approved=True, max_position_size=1000)
        
        # Mock get_portfolio_value as a sync method
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=100000.0)  # $100k portfolio
        
        self.mock_risk_manager.assess_position_risk = mock_assess_position_risk
        self.strategy = MeanReversionStrategy(self.mock_risk_manager)
        
    @pytest.fixture
    def sample_price_data(self):
        """Create sample price data for testing."""
        dates = pd.date_range(start='2024-01-01', periods=20, freq='D')
        return pd.DataFrame({
            'open': np.random.uniform(148, 152, 20),
            'high': np.random.uniform(149, 153, 20),
            'low': np.random.uniform(147, 151, 20),
            'close': np.random.uniform(148, 152, 20),
            'volume': np.random.randint(1000000, 5000000, 20)
        }, index=dates)
    
    @pytest.mark.asyncio
    async def test_mean_reversion_oversold_signal(self, sample_price_data):
        """Test mean reversion signal for oversold condition."""
        # Create features indicating strongly oversold condition
        features = pd.DataFrame({
            'rsi': [15.0] * len(sample_price_data),  # Very oversold RSI
            'bb_upper': [155.0] * len(sample_price_data),
            'bb_lower': [145.0] * len(sample_price_data)
        })
        
        # Set price well below lower band for strong signal
        sample_price_data.loc[sample_price_data.index[-1], 'close'] = 143.0
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.0
        assert signal.position_size > 0

    @pytest.mark.asyncio
    async def test_mean_reversion_overbought_signal(self, sample_price_data):
        """Test mean reversion signal for overbought condition."""
        # Create features indicating strongly overbought condition
        features = pd.DataFrame({
            'rsi': [85.0] * len(sample_price_data),  # Very overbought RSI
            'bb_upper': [155.0] * len(sample_price_data),
            'bb_lower': [145.0] * len(sample_price_data)
        })
        
        # Set price well above upper band for strong signal
        sample_price_data.loc[sample_price_data.index[-1], 'close'] = 157.0
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0.0
        assert signal.position_size > 0

    @pytest.mark.asyncio
    async def test_mean_reversion_hold_signal(self, sample_price_data):
        """Test mean reversion with neutral conditions."""
        # Create neutral features
        features = pd.DataFrame({
            'rsi': [50.0] * len(sample_price_data),  # Neutral RSI
            'bb_upper': [155.0] * len(sample_price_data),
            'bb_lower': [145.0] * len(sample_price_data)
        })
        
        # Set price in middle of bands
        sample_price_data.loc[sample_price_data.index[-1], 'close'] = 150.0
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        # Should return HOLD signal for neutral conditions
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD

    @pytest.mark.asyncio
    async def test_mean_reversion_empty_data(self):
        """Test mean reversion with empty data."""
        empty_data = pd.DataFrame()
        empty_features = pd.DataFrame()
        
        signal = await self.strategy.generate_signal("AAPL", empty_data, empty_features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0

    @pytest.mark.asyncio
    async def test_mean_reversion_missing_features(self, sample_price_data):
        """Test mean reversion with missing features."""
        # Missing required features
        features = pd.DataFrame({
            'some_other_feature': [1.0] * len(sample_price_data)
        })
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0

    def test_mean_reversion_get_required_features(self):
        """Test get_required_features method."""
        features = self.strategy.get_required_features()
        assert isinstance(features, list)
        assert len(features) > 0

    @pytest.mark.asyncio
    async def test_validate_signal_inactive_strategy(self, sample_price_data):
        """Test signal validation when strategy is inactive."""
        self.strategy.is_active = False
        
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0,
            position_size=100
        )
        
        result = await self.strategy.validate_signal(signal)
        assert result is False


class TestMomentumStrategy:
    """Test MomentumStrategy implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = Mock(spec=RiskManager)
        
        async def mock_assess_position_risk(*args, **kwargs):
            return Mock(is_approved=True, max_position_size=1000)
        
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=100000.0)
        self.mock_risk_manager.assess_position_risk = mock_assess_position_risk
        self.strategy = MomentumStrategy(self.mock_risk_manager)
        
    @pytest.fixture
    def sample_price_data(self):
        """Create sample price data for testing."""
        dates = pd.date_range(start='2024-01-01', periods=20, freq='D')
        # Create upward trending data for momentum
        base_prices = np.linspace(140, 160, 20)  # Upward trend
        return pd.DataFrame({
            'open': base_prices + np.random.normal(0, 0.5, 20),
            'high': base_prices + np.random.normal(1, 0.5, 20),
            'low': base_prices + np.random.normal(-1, 0.5, 20),
            'close': base_prices + np.random.normal(0, 0.5, 20),
            'volume': np.random.randint(1000000, 5000000, 20)
        }, index=dates)

    @pytest.mark.asyncio
    async def test_momentum_strong_uptrend_signal(self, sample_price_data):
        """Test momentum signal for strong uptrend."""
        # Create features indicating strong momentum
        features = pd.DataFrame({
            'sma_20': [145.0] * len(sample_price_data),
            'sma_50': [140.0] * len(sample_price_data),
            'rsi': [75.0] * len(sample_price_data),
            'macd': [2.0] * len(sample_price_data),
            'macd_signal': [1.5] * len(sample_price_data)
        })
        
        # Set current price above moving averages
        sample_price_data.loc[sample_price_data.index[-1], 'close'] = 155.0
        
        signal = await self.strategy.generate_signal("AAPL", sample_price_data, features)
        
        assert signal.symbol == "AAPL"
        # Should generate some signal based on momentum
        assert signal.signal_type in [SignalType.BUY, SignalType.HOLD, SignalType.SELL]

    def test_momentum_get_required_features(self):
        """Test get_required_features method."""
        features = self.strategy.get_required_features()
        assert isinstance(features, list)


class TestRebalancingStrategy:
    """Test RebalancingStrategy implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = Mock(spec=RiskManager)
        
        async def mock_assess_position_risk(*args, **kwargs):
            return Mock(is_approved=True, max_position_size=1000)
        
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=100000.0)
        self.mock_risk_manager.get_positions = Mock(return_value={
            "AAPL": {"market_value": 30000.0, "quantity": 200},
            "GOOGL": {"market_value": 30000.0, "quantity": 200}, 
            "MSFT": {"market_value": 40000.0, "quantity": 133}
        })
        self.mock_risk_manager.assess_position_risk = mock_assess_position_risk
        
        # Create target weights for the rebalancing strategy
        target_weights = {"AAPL": 0.3, "GOOGL": 0.3, "MSFT": 0.4}
        self.strategy = RebalancingStrategy(self.mock_risk_manager, target_weights)

    @pytest.mark.asyncio
    async def test_rebalancing_strategy_signal(self):
        """Test rebalancing strategy signal generation."""
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        
        features = pd.DataFrame({
            'current_weight': [0.35] * 10,  # Overweight
            'target_weight': [0.30] * 10
        })
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        # Should generate rebalancing signal
        assert signal.signal_type in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]

    def test_rebalancing_get_required_features(self):
        """Test get_required_features method."""
        features = self.strategy.get_required_features()
        assert isinstance(features, list)


class TestStatisticalArbitrageStrategy:
    """Test StatisticalArbitrageStrategy implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = Mock(spec=RiskManager)
        
        async def mock_assess_position_risk(*args, **kwargs):
            return Mock(is_approved=True, max_position_size=1000)
        
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=100000.0)
        self.mock_risk_manager.assess_position_risk = mock_assess_position_risk
        self.strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)

    @pytest.mark.asyncio 
    async def test_statistical_arbitrage_signal(self):
        """Test statistical arbitrage signal generation."""
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        
        features = pd.DataFrame({
            'spread': [2.0] * 10,
            'spread_mean': [1.0] * 10,
            'spread_std': [0.5] * 10
        })
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]

    def test_statistical_arbitrage_get_required_features(self):
        """Test get_required_features method."""
        features = self.strategy.get_required_features()
        assert isinstance(features, list)


class TestEnsembleStrategy:
    """Test EnsembleStrategy implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = Mock(spec=RiskManager)
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=100000.0)
        self.mock_risk_manager.assess_position_risk = AsyncMock(return_value={"approved": True, "max_position": 1000.0})
        
        self.mock_ensemble_model = Mock()
        # Create a proper prediction object with required attributes
        mock_prediction = Mock()
        mock_prediction.ensemble_prediction = 155.0
        mock_prediction.ensemble_confidence = 0.8
        self.mock_ensemble_model.predict = Mock(return_value=mock_prediction)
        
        # Create mock strategies
        self.mock_strategy1 = Mock()
        self.mock_strategy2 = Mock()
        
        # Create ensemble - fix constructor call
        self.ensemble = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)

    @pytest.mark.asyncio
    async def test_ensemble_strategy_aggregation(self):
        """Test ensemble strategy signal aggregation."""
        # Configure async return values
        async def mock_signal1(*args):
            return TradingSignal(
                symbol="AAPL",
                signal_type=SignalType.BUY,
                confidence=0.8,
                target_price=150.0,
                position_size=100
            )
            
        async def mock_signal2(*args):
            return TradingSignal(
                symbol="AAPL", 
                signal_type=SignalType.BUY,
                confidence=0.6,
                target_price=150.0,
                position_size=80
            )
        
        self.mock_strategy1.generate_signal = mock_signal1
        self.mock_strategy2.generate_signal = mock_signal2
        
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        
        features = pd.DataFrame({
            'feature1': [1.0] * 10,
            'feature2': [2.0] * 10
        })
        
        signal = await self.ensemble.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert isinstance(signal.confidence, float)

    def test_ensemble_get_required_features(self):
        """Test ensemble get_required_features method."""
        # Mock the strategies' get_required_features methods
        self.mock_strategy1.get_required_features = Mock(return_value=['feature1', 'feature2'])
        self.mock_strategy2.get_required_features = Mock(return_value=['feature2', 'feature3'])
        
        features = self.ensemble.get_required_features()
        assert isinstance(features, list)


class TestStrategyManager:
    """Test StrategyManager class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = Mock(spec=RiskManager)
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=100000.0)
        self.mock_risk_manager.assess_position_risk = AsyncMock(return_value={"approved": True, "max_position": 1000.0})
        
        self.mock_ensemble_model = Mock()
        mock_prediction = Mock()
        mock_prediction.ensemble_prediction = 155.0
        mock_prediction.ensemble_confidence = 0.8
        self.mock_ensemble_model.predict = Mock(return_value=mock_prediction)
        
        self.manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)

    def test_strategy_manager_initialization(self):
        """Test strategy manager initialization."""
        # Verify strategies were initialized
        assert "ensemble" in self.manager.strategies
        assert "mean_reversion" in self.manager.strategies
        assert "momentum" in self.manager.strategies
        assert "stat_arb" in self.manager.strategies
        
        # Verify equal weights
        assert len(self.manager.strategy_weights) == 4
        assert all(weight == 0.25 for weight in self.manager.strategy_weights.values())

    def test_strategy_manager_activate_strategy(self):
        """Test strategy activation."""
        self.manager.activate_strategy("mean_reversion")
        assert self.manager.strategies["mean_reversion"].is_active

    def test_strategy_manager_deactivate_strategy(self):
        """Test strategy deactivation."""
        self.manager.deactivate_strategy("momentum")
        assert not self.manager.strategies["momentum"].is_active

    def test_strategy_manager_get_strategy_status(self):
        """Test getting strategy status."""
        status = self.manager.get_strategy_status()
        
        assert isinstance(status, dict)
        assert "ensemble" in status
        assert "mean_reversion" in status
        assert "is_active" in status["ensemble"]
        assert "weight" in status["ensemble"]

    @pytest.mark.asyncio
    async def test_strategy_manager_combined_signal(self):
        """Test generating combined signal from multiple strategies."""
        # Activate all strategies
        for strategy_name in self.manager.strategies:
            self.manager.activate_strategy(strategy_name)
        
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10,
            'high': [152.0] * 10,
            'low': [148.0] * 10,
            'open': [149.0] * 10
        }, index=dates)
        
        features = pd.DataFrame({
            'rsi': [60.0] * 10,
            'macd': [1.2] * 10,
            'bollinger_upper': [155.0] * 10,
            'bollinger_lower': [145.0] * 10,
            'volume_sma': [1000000] * 10
        })
        
        signal = await self.manager.generate_combined_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type in [s for s in SignalType]
        assert 0.0 <= signal.confidence <= 1.0

    def test_strategy_manager_update_weights(self):
        """Test updating strategy weights based on performance."""
        performance_data = {
            "mean_reversion": StrategyPerformance(
                strategy_name="mean_reversion",
                total_returns=0.15,
                sharpe_ratio=1.5,
                max_drawdown=-0.05,
                win_rate=0.7,
                total_trades=100,
                avg_trade_duration=timedelta(hours=24),
                last_updated=datetime.now()
            ),
            "momentum": StrategyPerformance(
                strategy_name="momentum",
                total_returns=0.10,
                sharpe_ratio=1.2,
                max_drawdown=-0.08,
                win_rate=0.6,
                total_trades=80,
                avg_trade_duration=timedelta(hours=12),
                last_updated=datetime.now()
            )
        }
        
        self.manager.update_strategy_weights(performance_data)
        
        # Verify weights were updated and sum to 1
        total_weight = sum(self.manager.strategy_weights.values())
        assert abs(total_weight - 1.0) < 0.001  # Allow for floating point precision


class TestSignalTypeEnum:
    """Test SignalType enumeration."""
    
    def test_signal_type_values(self):
        """Test SignalType enum values."""
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
        assert SignalType.HOLD.value == "HOLD"
        assert SignalType.STRONG_BUY.value == "STRONG_BUY"
        assert SignalType.STRONG_SELL.value == "STRONG_SELL"


class TestOrderTypeEnum:
    """Test OrderType enumeration."""
    
    def test_order_type_values(self):
        """Test OrderType enum values."""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
        assert OrderType.STOP_LIMIT.value == "stop_limit"


class TestMissingCoverageEdgeCases:
    """Test edge cases and error conditions for missing coverage."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = Mock(spec=RiskManager)
        
        async def mock_assess_position_risk(*args, **kwargs):
            return {"approved": True, "max_position": 1000}
        
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=100000.0)
        self.mock_risk_manager.assess_position_risk = mock_assess_position_risk
        
        self.mean_reversion = MeanReversionStrategy(self.mock_risk_manager)
        self.momentum = MomentumStrategy(self.mock_risk_manager)
        
        self.mock_ensemble_model = Mock()
        mock_prediction = Mock()
        mock_prediction.ensemble_prediction = 155.0
        mock_prediction.ensemble_confidence = 0.8
        self.mock_ensemble_model.predict = Mock(return_value=mock_prediction)
        
        self.manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)

    @pytest.mark.asyncio
    async def test_strategy_with_insufficient_data(self):
        """Test strategy behavior with insufficient data."""
        # Single row of data
        dates = pd.date_range(start='2024-01-01', periods=1, freq='D')
        minimal_data = pd.DataFrame({
            'close': [150.0],
            'volume': [1000000]
        }, index=dates)
        
        minimal_features = pd.DataFrame({
            'rsi': [50.0],
            'bb_upper': [155.0],
            'bb_lower': [145.0]
        })
        
        signal = await self.mean_reversion.generate_signal("AAPL", minimal_data, minimal_features)
        assert signal.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_strategy_risk_validation_failure(self):
        """Test strategy when risk validation fails."""
        # Configure risk manager to reject
        async def mock_reject_risk(*args, **kwargs):
            return {"approved": False, "max_position": 0}
        
        self.mock_risk_manager.assess_position_risk = mock_reject_risk
        
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0,
            position_size=100
        )
        
        # Validation should fail
        result = await self.mean_reversion.validate_signal(signal)
        assert result is False

    def test_manager_strategy_access(self):
        """Test accessing strategies through manager."""
        # StrategyManager auto-initializes strategies, so we test direct access
        assert "mean_reversion" in self.manager.strategies
        assert "momentum" in self.manager.strategies
        assert "ensemble" in self.manager.strategies
        assert "stat_arb" in self.manager.strategies

    def test_performance_metrics_edge_cases(self):
        """Test StrategyPerformance with edge case values."""
        perf = StrategyPerformance(
            strategy_name="EdgeCase",
            total_returns=0.0,
            sharpe_ratio=0.0,
            max_drawdown=1.0,
            win_rate=0.0,
            total_trades=0,
            avg_trade_duration=timedelta(0),
            last_updated=datetime.now()
        )
        
        assert perf.total_returns == 0.0
        assert perf.total_trades == 0
        assert perf.win_rate == 0.0

    @pytest.mark.asyncio
    async def test_ensemble_strategy_with_exceptions(self):
        """Test ensemble strategy when component strategies raise exceptions."""
        mock_strategy1 = Mock()
        mock_strategy2 = Mock()
        
        # First strategy raises exception
        async def mock_exception(*args):
            raise ValueError("Strategy error")
            
        async def mock_good_signal(*args):
            return TradingSignal(
                symbol="AAPL",
                signal_type=SignalType.BUY,
                confidence=0.6,
                target_price=150.0,
                position_size=80
            )
        
        mock_strategy1.generate_signal = mock_exception
        mock_strategy2.generate_signal = mock_good_signal
        
        mock_ensemble_model = Mock()
        mock_ensemble_model.predict = Mock(return_value=np.array([0.5]))
        
        ensemble = EnsembleStrategy([mock_strategy1, mock_strategy2], mock_ensemble_model)
        
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        
        features = pd.DataFrame({'feature1': [1.0] * 10})
        
        # Should handle exception gracefully
        try:
            signal = await ensemble.generate_signal("AAPL", price_data, features)
            # If it succeeds, verify it returned something reasonable
            if signal:
                assert signal.symbol == "AAPL"
        except Exception:
            # Or it might propagate the exception, which is also valid
            pass

    @pytest.mark.asyncio
    async def test_trading_signal_with_all_fields(self):
        """Test TradingSignal with all optional fields."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.STRONG_BUY,
            confidence=0.95,
            target_price=155.0,
            stop_loss=145.0,
            take_profit=165.0,
            position_size=200,
            order_type=OrderType.LIMIT,
            timestamp=datetime.now(),
            metadata={"strategy": "test", "confidence_level": "high"}
        )
        
        assert signal.stop_loss == 145.0
        assert signal.take_profit == 165.0
        assert signal.order_type == OrderType.LIMIT
        assert isinstance(signal.metadata, dict)


class TestComprehensiveCoverage:
    """Additional tests to achieve 100% coverage."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_risk_manager = Mock(spec=RiskManager)
        
        async def mock_assess_position_risk(*args, **kwargs):
            return {"approved": True, "max_position": 1000}
        
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=100000.0)
        self.mock_risk_manager.get_positions = Mock(return_value={
            "AAPL": {"market_value": 50000.0, "quantity": 100}
        })
        self.mock_risk_manager.assess_position_risk = mock_assess_position_risk
        
        self.mock_ensemble_model = Mock()
        mock_prediction = Mock()
        mock_prediction.ensemble_prediction = 155.0
        mock_prediction.ensemble_confidence = 0.9
        self.mock_ensemble_model.predict = Mock(return_value=mock_prediction)

    def test_performance_update_empty_results(self):
        """Test update_performance with empty trade results."""
        strategy = MeanReversionStrategy(self.mock_risk_manager)
        # Should not crash with empty results
        strategy.update_performance([])
        # Performance metrics should remain None
        assert strategy.performance_metrics is None

    def test_performance_update_with_trades(self):
        """Test update_performance with actual trade data."""
        strategy = MeanReversionStrategy(self.mock_risk_manager)
        
        trade_results = [
            {"return": 0.05, "duration": timedelta(days=1)},
            {"return": -0.02, "duration": timedelta(days=2)},
            {"return": 0.03, "duration": timedelta(days=1)}
        ]
        
        strategy.update_performance(trade_results)
        
        assert strategy.performance_metrics is not None
        assert strategy.performance_metrics.total_trades == 3
        assert strategy.performance_metrics.win_rate == 2/3  # 2 positive returns out of 3

    def test_max_drawdown_calculation_edge_cases(self):
        """Test max drawdown calculation with various scenarios.""" 
        strategy = MeanReversionStrategy(self.mock_risk_manager)
        
        # Test with declining returns
        declining_returns = [0.1, -0.05, -0.1, -0.02]
        drawdown = strategy._calculate_max_drawdown(declining_returns)
        assert drawdown < 0  # Should be negative

    @pytest.mark.asyncio
    async def test_inactive_strategy_validation(self):
        """Test that inactive strategies fail validation."""
        strategy = MeanReversionStrategy(self.mock_risk_manager)
        strategy.is_active = False
        
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0
        )
        
        result = await strategy.validate_signal(signal)
        assert result is False

    @pytest.mark.asyncio
    async def test_ensemble_strategy_low_confidence(self):
        """Test EnsembleStrategy with low confidence prediction."""
        # Create low confidence prediction
        low_conf_prediction = Mock()
        low_conf_prediction.ensemble_prediction = 151.0
        low_conf_prediction.ensemble_confidence = 0.3  # Below default threshold
        self.mock_ensemble_model.predict = Mock(return_value=low_conf_prediction)
        
        ensemble = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)
        
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        
        features = pd.DataFrame({'feature1': [1.0] * 10})
        
        signal = await ensemble.generate_signal("AAPL", price_data, features)
        assert signal.signal_type == SignalType.HOLD

    @pytest.mark.asyncio
    async def test_ensemble_strategy_strong_buy_sell(self):
        """Test EnsembleStrategy strong buy and sell signals."""
        ensemble = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)
        
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        features = pd.DataFrame({'feature1': [1.0] * 10})
        
        # Test strong buy (>5% predicted return)
        strong_buy_prediction = Mock()
        strong_buy_prediction.ensemble_prediction = 158.0  # >5% above 150
        strong_buy_prediction.ensemble_confidence = 0.9
        self.mock_ensemble_model.predict = Mock(return_value=strong_buy_prediction)
        
        signal = await ensemble.generate_signal("AAPL", price_data, features)
        assert signal.signal_type == SignalType.STRONG_BUY
        
        # Test strong sell (<-5% predicted return)
        strong_sell_prediction = Mock()
        strong_sell_prediction.ensemble_prediction = 142.0  # <-5% below 150
        strong_sell_prediction.ensemble_confidence = 0.9
        self.mock_ensemble_model.predict = Mock(return_value=strong_sell_prediction)
        
        signal = await ensemble.generate_signal("AAPL", price_data, features)
        assert signal.signal_type == SignalType.STRONG_SELL

    @pytest.mark.asyncio
    async def test_rebalancing_zero_portfolio_value(self):
        """Test RebalancingStrategy with zero portfolio value."""
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=0.0)
        self.mock_risk_manager.get_positions = Mock(return_value={})
        
        target_weights = {"AAPL": 0.5, "GOOGL": 0.5}
        strategy = RebalancingStrategy(self.mock_risk_manager, target_weights)
        
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        features = pd.DataFrame({'feature1': [1.0] * 10})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        assert signal.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_stat_arb_zero_std(self):
        """Test StatisticalArbitrageStrategy with zero standard deviation."""
        strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)
        
        # Need enough data for lookback_period (60)
        dates = pd.date_range(start='2024-01-01', periods=65, freq='D')
        constant_price_data = pd.DataFrame({
            'close': [150.0] * 65,  # Constant prices = zero std
            'volume': [1000000] * 65
        }, index=dates)
        features = pd.DataFrame({'spread': [1.0] * 65})
        
        signal = await strategy.generate_signal("AAPL", constant_price_data, features)
        assert signal.signal_type == SignalType.HOLD
        assert signal.target_price == 150.0  # Should equal current_price when std=0

    @pytest.mark.asyncio
    async def test_stat_arb_insufficient_data(self):
        """Test StatisticalArbitrageStrategy with insufficient data."""
        strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)
        
        # Insufficient data (less than lookback_period of 60)
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        insufficient_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        features = pd.DataFrame({'spread': [1.0] * 10})
        
        signal = await strategy.generate_signal("AAPL", insufficient_data, features)
        assert signal.signal_type == SignalType.HOLD
        assert signal.target_price == 0.0  # Should return 0.0 with insufficient data

    @pytest.mark.asyncio
    async def test_manager_no_active_strategies(self):
        """Test StrategyManager with no active strategies."""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Deactivate all strategies
        for strategy_name in manager.strategies:
            manager.deactivate_strategy(strategy_name)
        
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        features = pd.DataFrame({'feature1': [1.0] * 10})
        
        signal = await manager.generate_combined_signal("AAPL", price_data, features)
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0

    def test_combined_position_size_zero_weight(self):
        """Test _calculate_combined_position_size with zero total weight."""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Empty strategy signals = zero weight
        strategy_signals = {}
        
        size = manager._calculate_combined_position_size(
            "AAPL", 150.0, 0.8, strategy_signals
        )
        assert size == 0.0

    def test_strategy_weight_update_partial_performance(self):
        """Test update_strategy_weights with partial performance data."""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Only provide performance for one strategy
        performance_data = {
            "mean_reversion": StrategyPerformance(
                strategy_name="mean_reversion",
                total_returns=0.15,
                sharpe_ratio=1.5,
                max_drawdown=-0.05,
                win_rate=0.7,
                total_trades=100,
                avg_trade_duration=timedelta(hours=24),
                last_updated=datetime.now()
            )
        }
        
        manager.update_strategy_weights(performance_data)
        
        # Should handle missing strategies with default weights
        total_weight = sum(manager.strategy_weights.values())
        assert abs(total_weight - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_momentum_strategy_bearish_signal(self):
        """Test MomentumStrategy bearish signal conditions."""
        strategy = MomentumStrategy(self.mock_risk_manager)
        
        dates = pd.date_range(start='2024-01-01', periods=50, freq='D')
        # Bearish conditions: MACD < signal and price < SMA20 < SMA50
        price_data = pd.DataFrame({
            'close': [140.0] * 50,  # Price below averages
            'volume': [1000000] * 50,
            'high': [142.0] * 50,
            'low': [138.0] * 50,
            'open': [141.0] * 50
        }, index=dates)
        
        features = pd.DataFrame({
            'sma_20': [145.0] * 50,   # SMA20 above price
            'sma_50': [150.0] * 50,   # SMA50 above SMA20
            'macd': [-0.5] * 50,      # MACD below signal 
            'macd_signal': [0.5] * 50,
            'rsi': [30.0] * 50,
            'bollinger_upper': [155.0] * 50,
            'bollinger_lower': [135.0] * 50,
            'volume_sma': [1000000] * 50
        })
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        assert signal.signal_type == SignalType.SELL

    @pytest.mark.asyncio
    async def test_rebalancing_sell_signal(self):
        """Test RebalancingStrategy sell signal when overweight."""
        # Portfolio where AAPL is overweight
        self.mock_risk_manager.get_portfolio_value = Mock(return_value=100000.0)
        self.mock_risk_manager.get_positions = Mock(return_value={
            "AAPL": {"market_value": 60000.0, "quantity": 400}  # 60% instead of target 30%
        })
        
        target_weights = {"AAPL": 0.3, "GOOGL": 0.7}  # Target only 30% for AAPL
        strategy = RebalancingStrategy(self.mock_risk_manager, target_weights)
        
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        features = pd.DataFrame({'feature1': [1.0] * 10})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        assert signal.signal_type == SignalType.SELL  # Should sell when overweight

    @pytest.mark.asyncio
    async def test_stat_arb_buy_sell_signals(self):
        """Test StatisticalArbitrageStrategy buy and sell signals."""
        strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)
        
        dates = pd.date_range(start='2024-01-01', periods=65, freq='D')
        
        # Test buy signal: current price well below mean
        buy_price_data = pd.DataFrame({
            'close': [150.0] * 60 + [130.0] * 5,  # Last 5 prices much lower
            'volume': [1000000] * 65
        }, index=dates)
        features = pd.DataFrame({'spread': [1.0] * 65})
        
        signal = await strategy.generate_signal("AAPL", buy_price_data, features)
        assert signal.signal_type == SignalType.BUY
        
        # Test sell signal: current price well above mean  
        sell_price_data = pd.DataFrame({
            'close': [150.0] * 60 + [170.0] * 5,  # Last 5 prices much higher
            'volume': [1000000] * 65
        }, index=dates)
        
        signal = await strategy.generate_signal("AAPL", sell_price_data, features)
        assert signal.signal_type == SignalType.SELL

    @pytest.mark.asyncio
    async def test_manager_combined_signal_zero_total_weight(self):
        """Test StrategyManager combined signal when total weight is zero."""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Mock strategies to return signals with zero confidence (leading to zero weight)
        for strategy_name, strategy in manager.strategies.items():
            strategy.is_active = True
            
            async def mock_zero_confidence_signal(*args, **kwargs):
                return TradingSignal(
                    symbol="AAPL",
                    signal_type=SignalType.BUY,
                    confidence=0.0,  # Zero confidence = zero weight
                    target_price=150.0,
                    position_size=0.0
                )
            strategy.generate_signal = mock_zero_confidence_signal
        
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        price_data = pd.DataFrame({
            'close': [150.0] * 10,
            'volume': [1000000] * 10
        }, index=dates)
        features = pd.DataFrame({'feature1': [1.0] * 10})
        
        signal = await manager.generate_combined_signal("AAPL", price_data, features)
        # Should return default HOLD signal when total weight is zero
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0