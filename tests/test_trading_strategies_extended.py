"""
Comprehensive tests for backend.strategies.trading_strategies

Targets 70%+ coverage for trading strategies module:
- SignalType and OrderType enums
- TradingSignal and StrategyPerformance dataclasses
- BaseStrategy abstract class
- MeanReversionStrategy
- MomentumStrategy
- RebalancingStrategy
- EnsembleStrategy
- StatisticalArbitrageStrategy
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

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
    StatisticalArbitrageStrategy,
    StrategyPerformance,
    TradingSignal,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_risk_manager():
    """Create a mock RiskManager"""
    rm = MagicMock()
    rm.get_portfolio_value = MagicMock(return_value=100000)
    rm.get_positions = AsyncMock(return_value={})
    rm.assess_position_risk = AsyncMock(return_value={"approved": True})
    return rm


@pytest.fixture
def mock_settings():
    """Create mock settings"""
    settings = MagicMock()
    settings.trading = MagicMock()
    settings.trading.max_position_size = 1000
    return settings


@pytest.fixture
def sample_price_data():
    """Create sample price DataFrame"""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    return pd.DataFrame(
        {
            "close": [100 + i * 0.5 + np.sin(i / 10) * 5 for i in range(100)],
            "open": [100 + i * 0.5 for i in range(100)],
            "high": [101 + i * 0.5 for i in range(100)],
            "low": [99 + i * 0.5 for i in range(100)],
            "volume": [1000000 + i * 1000 for i in range(100)],
        },
        index=dates,
    )


@pytest.fixture
def sample_features():
    """Create sample features DataFrame"""
    dates = pd.date_range(start="2024-01-01", periods=100, freq="D")
    return pd.DataFrame(
        {
            "rsi": [50 + np.sin(i / 10) * 30 for i in range(100)],
            "bb_upper": [110 + i * 0.5 for i in range(100)],
            "bb_lower": [90 + i * 0.5 for i in range(100)],
            "macd": [0.5 + np.sin(i / 5) * 0.5 for i in range(100)],
            "macd_signal": [0.4 + np.sin(i / 5) * 0.3 for i in range(100)],
            "sma_20": [100 + i * 0.4 for i in range(100)],
            "sma_50": [100 + i * 0.3 for i in range(100)],
        },
        index=dates,
    )


# ============================================================================
# ENUM TESTS
# ============================================================================

class TestSignalType:
    """Tests for SignalType enum"""

    def test_all_signal_values(self):
        """Test all signal type values"""
        assert SignalType.BUY.value == "BUY"
        assert SignalType.SELL.value == "SELL"
        assert SignalType.HOLD.value == "HOLD"
        assert SignalType.STRONG_BUY.value == "STRONG_BUY"
        assert SignalType.STRONG_SELL.value == "STRONG_SELL"


class TestOrderType:
    """Tests for OrderType enum"""

    def test_all_order_values(self):
        """Test all order type values"""
        assert OrderType.MARKET.value == "market"
        assert OrderType.LIMIT.value == "limit"
        assert OrderType.STOP.value == "stop"
        assert OrderType.STOP_LIMIT.value == "stop_limit"


# ============================================================================
# DATACLASS TESTS
# ============================================================================

class TestTradingSignal:
    """Tests for TradingSignal dataclass"""

    def test_create_minimal_signal(self):
        """Test creating signal with required fields"""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0,
        )

        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.8
        assert signal.target_price == 150.0
        assert signal.stop_loss is None
        assert signal.take_profit is None
        assert signal.position_size == 0.0
        assert signal.order_type == OrderType.MARKET

    def test_create_full_signal(self):
        """Test creating signal with all fields"""
        ts = datetime.now()
        signal = TradingSignal(
            symbol="GOOG",
            signal_type=SignalType.STRONG_SELL,
            confidence=0.95,
            target_price=140.0,
            stop_loss=155.0,
            take_profit=130.0,
            position_size=100.0,
            order_type=OrderType.LIMIT,
            timestamp=ts,
            metadata={"reason": "overbought"},
        )

        assert signal.symbol == "GOOG"
        assert signal.stop_loss == 155.0
        assert signal.take_profit == 130.0
        assert signal.position_size == 100.0
        assert signal.order_type == OrderType.LIMIT
        assert signal.timestamp == ts
        assert signal.metadata["reason"] == "overbought"


class TestStrategyPerformance:
    """Tests for StrategyPerformance dataclass"""

    def test_create_performance(self):
        """Test creating performance metrics"""
        perf = StrategyPerformance(
            strategy_name="TestStrategy",
            total_returns=0.15,
            sharpe_ratio=1.5,
            max_drawdown=-0.10,
            win_rate=0.65,
            total_trades=100,
            avg_trade_duration=timedelta(hours=4),
            last_updated=datetime.now(),
        )

        assert perf.strategy_name == "TestStrategy"
        assert perf.total_returns == 0.15
        assert perf.sharpe_ratio == 1.5
        assert perf.max_drawdown == -0.10
        assert perf.win_rate == 0.65
        assert perf.total_trades == 100


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
            target_price=100.0,
        )

    def get_required_features(self):
        return ["rsi", "macd"]


class TestBaseStrategy:
    """Tests for BaseStrategy abstract class"""

    def test_init_with_defaults(self, mock_risk_manager):
        """Test initialization with default parameters"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = ConcreteStrategy("TestStrategy", mock_risk_manager)

        assert strategy.name == "TestStrategy"
        assert strategy.risk_manager == mock_risk_manager
        assert strategy.is_active is True
        assert strategy.max_risk_per_trade == 0.02
        assert strategy.stop_loss_pct == 0.05
        assert strategy.take_profit_pct == 0.02

    def test_init_with_custom_params(self, mock_risk_manager):
        """Test initialization with custom risk parameters"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = ConcreteStrategy(
                "CustomStrategy",
                mock_risk_manager,
                max_risk_per_trade=0.05,
                stop_loss_pct=0.10,
                take_profit_pct=0.03,
            )

        assert strategy.max_risk_per_trade == 0.05
        assert strategy.stop_loss_pct == 0.10
        assert strategy.take_profit_pct == 0.03

    def test_calculate_position_size(self, mock_risk_manager):
        """Test position size calculation"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = ConcreteStrategy("TestStrategy", mock_risk_manager)

            # Calculate position size
            size = strategy.calculate_position_size("AAPL", 150.0, 0.8)

            assert size > 0

    def test_calculate_position_size_risk_limit(self, mock_risk_manager):
        """Test position size limited by risk"""
        mock_risk_manager.get_portfolio_value.return_value = 10000

        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 10000  # Large position
            mock_get.return_value = settings

            strategy = ConcreteStrategy("TestStrategy", mock_risk_manager)
            strategy.max_risk_per_trade = 0.01  # 1% max risk = $100

            size = strategy.calculate_position_size("AAPL", 150.0, 1.0)

            # Position value should not exceed $100
            assert size * 150.0 <= 100

    @pytest.mark.asyncio
    async def test_validate_signal_approved(self, mock_risk_manager):
        """Test signal validation when approved"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = ConcreteStrategy("TestStrategy", mock_risk_manager)

            signal = TradingSignal(
                symbol="AAPL",
                signal_type=SignalType.BUY,
                confidence=0.8,
                target_price=150.0,
                position_size=100.0,
            )

            result = await strategy.validate_signal(signal)

            assert result is True

    @pytest.mark.asyncio
    async def test_validate_signal_inactive(self, mock_risk_manager):
        """Test signal validation when strategy is inactive"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = ConcreteStrategy("TestStrategy", mock_risk_manager)
            strategy.is_active = False

            signal = TradingSignal(
                symbol="AAPL",
                signal_type=SignalType.BUY,
                confidence=0.8,
                target_price=150.0,
            )

            result = await strategy.validate_signal(signal)

            assert result is False

    def test_update_performance(self, mock_risk_manager):
        """Test performance update"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = ConcreteStrategy("TestStrategy", mock_risk_manager)

            trade_results = [
                {"return": 0.05, "duration": timedelta(hours=2)},
                {"return": -0.02, "duration": timedelta(hours=3)},
                {"return": 0.03, "duration": timedelta(hours=1)},
            ]

            strategy.update_performance(trade_results)

            assert strategy.performance_metrics is not None
            assert strategy.performance_metrics.total_trades == 3
            assert strategy.performance_metrics.strategy_name == "TestStrategy"

    def test_update_performance_empty(self, mock_risk_manager):
        """Test performance update with empty results"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = ConcreteStrategy("TestStrategy", mock_risk_manager)

            strategy.update_performance([])

            assert strategy.performance_metrics is None

    def test_calculate_max_drawdown(self, mock_risk_manager):
        """Test max drawdown calculation"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = ConcreteStrategy("TestStrategy", mock_risk_manager)

            returns = [0.05, 0.03, -0.10, 0.02, -0.05]
            drawdown = strategy._calculate_max_drawdown(returns)

            assert drawdown < 0  # Drawdown should be negative


# ============================================================================
# MEAN REVERSION STRATEGY TESTS
# ============================================================================

class TestMeanReversionStrategy:
    """Tests for MeanReversionStrategy"""

    def test_init_defaults(self, mock_risk_manager):
        """Test default initialization"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = MeanReversionStrategy(mock_risk_manager)

        assert strategy.name == "MeanReversionStrategy"
        assert strategy.oversold_threshold == 30.0
        assert strategy.overbought_threshold == 70.0

    def test_init_custom_thresholds(self, mock_risk_manager):
        """Test custom initialization"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = MeanReversionStrategy(
                mock_risk_manager,
                oversold_threshold=25.0,
                overbought_threshold=75.0,
            )

        assert strategy.oversold_threshold == 25.0
        assert strategy.overbought_threshold == 75.0

    @pytest.mark.asyncio
    async def test_generate_signal_buy(self, mock_risk_manager):
        """Test buy signal generation when oversold"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = MeanReversionStrategy(mock_risk_manager)

            # Price near lower band, RSI oversold
            price_data = pd.DataFrame({"close": [90.5]})  # Near lower band
            features = pd.DataFrame({
                "rsi": [25.0],  # Oversold
                "bb_upper": [110.0],
                "bb_lower": [90.0],
            })

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type == SignalType.BUY
            assert signal.stop_loss is not None

    @pytest.mark.asyncio
    async def test_generate_signal_sell(self, mock_risk_manager):
        """Test sell signal generation when overbought"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = MeanReversionStrategy(mock_risk_manager)

            # Price near upper band, RSI overbought
            price_data = pd.DataFrame({"close": [109.5]})  # Near upper band
            features = pd.DataFrame({
                "rsi": [75.0],  # Overbought
                "bb_upper": [110.0],
                "bb_lower": [90.0],
            })

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type == SignalType.SELL

    @pytest.mark.asyncio
    async def test_generate_signal_hold(self, mock_risk_manager):
        """Test hold signal when conditions are neutral"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = MeanReversionStrategy(mock_risk_manager)

            # Neutral conditions
            price_data = pd.DataFrame({"close": [100.0]})
            features = pd.DataFrame({
                "rsi": [50.0],  # Neutral
                "bb_upper": [110.0],
                "bb_lower": [90.0],
            })

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type == SignalType.HOLD

    @pytest.mark.asyncio
    async def test_generate_signal_missing_data(self, mock_risk_manager):
        """Test signal with missing data"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = MeanReversionStrategy(mock_risk_manager)

            # Empty data
            price_data = pd.DataFrame({"close": []})
            features = pd.DataFrame({"rsi": [], "bb_upper": [], "bb_lower": []})

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type == SignalType.HOLD
            assert signal.confidence == 0.0

    def test_get_required_features(self, mock_risk_manager):
        """Test required features list"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = MeanReversionStrategy(mock_risk_manager)

            features = strategy.get_required_features()

            assert "rsi" in features
            assert "bb_upper" in features
            assert "bb_lower" in features


# ============================================================================
# MOMENTUM STRATEGY TESTS
# ============================================================================

class TestMomentumStrategy:
    """Tests for MomentumStrategy"""

    def test_init_defaults(self, mock_risk_manager):
        """Test default initialization"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = MomentumStrategy(mock_risk_manager)

        assert strategy.name == "MomentumStrategy"
        assert strategy.momentum_multiplier == 0.1
        assert strategy.stop_loss_pct == 0.03

    @pytest.mark.asyncio
    async def test_generate_signal_bullish(self, mock_risk_manager):
        """Test buy signal in bullish momentum"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = MomentumStrategy(mock_risk_manager)

            # Bullish: MACD > signal, price > sma_20 > sma_50
            price_data = pd.DataFrame({"close": [110.0]})
            features = pd.DataFrame({
                "macd": [0.8],
                "macd_signal": [0.5],
                "sma_20": [105.0],
                "sma_50": [100.0],
            })

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type == SignalType.BUY
            assert signal.metadata["sma_trend"] == "bullish"

    @pytest.mark.asyncio
    async def test_generate_signal_bearish(self, mock_risk_manager):
        """Test sell signal in bearish momentum"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = MomentumStrategy(mock_risk_manager)

            # Bearish: MACD < signal, price < sma_20 < sma_50
            price_data = pd.DataFrame({"close": [90.0]})
            features = pd.DataFrame({
                "macd": [0.3],
                "macd_signal": [0.6],
                "sma_20": [95.0],
                "sma_50": [100.0],
            })

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type == SignalType.SELL
            assert signal.metadata["sma_trend"] == "bearish"

    def test_get_required_features(self, mock_risk_manager):
        """Test required features"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()
            strategy = MomentumStrategy(mock_risk_manager)

            features = strategy.get_required_features()

            assert "macd" in features
            assert "macd_signal" in features
            assert "sma_20" in features
            assert "sma_50" in features


# ============================================================================
# REBALANCING STRATEGY TESTS
# ============================================================================

class TestRebalancingStrategy:
    """Tests for RebalancingStrategy"""

    def test_init(self, mock_risk_manager):
        """Test initialization"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            target_weights = {"AAPL": 0.3, "GOOG": 0.3, "MSFT": 0.4}
            strategy = RebalancingStrategy(mock_risk_manager, target_weights)

        assert strategy.name == "RebalancingStrategy"
        assert strategy.target_weights == target_weights
        assert strategy.rebalance_threshold == 0.05

    @pytest.mark.asyncio
    async def test_generate_signal_needs_buy(self, mock_risk_manager):
        """Test buy signal when underweight"""
        mock_risk_manager.get_portfolio_value = AsyncMock(return_value=100000)
        mock_risk_manager.get_positions = AsyncMock(
            return_value={"AAPL": {"market_value": 10000}}  # 10%, target 30%
        )

        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = RebalancingStrategy(
                mock_risk_manager,
                {"AAPL": 0.3},
                rebalance_threshold=0.05,
            )

            price_data = pd.DataFrame({"close": [150.0]})
            features = pd.DataFrame()

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type == SignalType.BUY
            assert signal.metadata["current_weight"] == 0.1
            assert signal.metadata["target_weight"] == 0.3

    @pytest.mark.asyncio
    async def test_generate_signal_needs_sell(self, mock_risk_manager):
        """Test sell signal when overweight"""
        mock_risk_manager.get_portfolio_value = AsyncMock(return_value=100000)
        mock_risk_manager.get_positions = AsyncMock(
            return_value={"AAPL": {"market_value": 50000}}  # 50%, target 30%
        )

        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = RebalancingStrategy(
                mock_risk_manager,
                {"AAPL": 0.3},
                rebalance_threshold=0.05,
            )

            price_data = pd.DataFrame({"close": [150.0]})
            features = pd.DataFrame()

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type == SignalType.SELL

    def test_get_required_features(self, mock_risk_manager):
        """Test required features (none)"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            strategy = RebalancingStrategy(mock_risk_manager, {})

            assert strategy.get_required_features() == []


# ============================================================================
# ENSEMBLE STRATEGY TESTS
# ============================================================================

class TestEnsembleStrategy:
    """Tests for EnsembleStrategy"""

    def test_init(self, mock_risk_manager):
        """Test initialization"""
        mock_ensemble = MagicMock()

        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            strategy = EnsembleStrategy(
                mock_risk_manager,
                mock_ensemble,
                confidence_threshold=0.7,
            )

        assert strategy.name == "EnsembleStrategy"
        assert strategy.confidence_threshold == 0.7

    @pytest.mark.asyncio
    async def test_generate_signal_buy(self, mock_risk_manager):
        """Test buy signal generation"""
        mock_ensemble = MagicMock()
        prediction = MagicMock()
        prediction.ensemble_prediction = 165.0  # Predict price increase
        prediction.ensemble_confidence = 0.85
        prediction.predictions = [160.0, 165.0, 170.0]
        prediction.confidence_scores = [0.8, 0.85, 0.9]
        mock_ensemble.predict.return_value = prediction

        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = EnsembleStrategy(
                mock_risk_manager,
                mock_ensemble,
                confidence_threshold=0.6,
                return_threshold=0.02,
            )

            price_data = pd.DataFrame({"close": [150.0]})
            features = pd.DataFrame()

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]
            assert signal.confidence == 0.85
            assert signal.stop_loss is not None
            assert signal.take_profit is not None

    @pytest.mark.asyncio
    async def test_generate_signal_sell(self, mock_risk_manager):
        """Test sell signal generation"""
        mock_ensemble = MagicMock()
        prediction = MagicMock()
        prediction.ensemble_prediction = 135.0  # Predict price decrease
        prediction.ensemble_confidence = 0.80
        prediction.predictions = [130.0, 135.0, 140.0]
        prediction.confidence_scores = [0.75, 0.80, 0.85]
        mock_ensemble.predict.return_value = prediction

        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = EnsembleStrategy(
                mock_risk_manager,
                mock_ensemble,
                confidence_threshold=0.6,
                return_threshold=0.02,
            )

            price_data = pd.DataFrame({"close": [150.0]})
            features = pd.DataFrame()

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type in [SignalType.SELL, SignalType.STRONG_SELL]

    @pytest.mark.asyncio
    async def test_generate_signal_hold_low_confidence(self, mock_risk_manager):
        """Test hold signal when confidence too low"""
        mock_ensemble = MagicMock()
        prediction = MagicMock()
        prediction.ensemble_prediction = 165.0
        prediction.ensemble_confidence = 0.4  # Below threshold
        prediction.predictions = []
        prediction.confidence_scores = []
        mock_ensemble.predict.return_value = prediction

        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            settings = MagicMock()
            settings.trading.max_position_size = 1000
            mock_get.return_value = settings

            strategy = EnsembleStrategy(
                mock_risk_manager,
                mock_ensemble,
                confidence_threshold=0.6,
            )

            price_data = pd.DataFrame({"close": [150.0]})
            features = pd.DataFrame()

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type == SignalType.HOLD

    def test_get_required_features(self, mock_risk_manager):
        """Test required features list"""
        mock_ensemble = MagicMock()

        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            strategy = EnsembleStrategy(mock_risk_manager, mock_ensemble)

            features = strategy.get_required_features()

            assert len(features) > 10
            assert "sma_20" in features
            assert "rsi" in features
            assert "macd" in features


# ============================================================================
# STATISTICAL ARBITRAGE STRATEGY TESTS
# ============================================================================

class TestStatisticalArbitrageStrategy:
    """Tests for StatisticalArbitrageStrategy"""

    def test_init(self, mock_risk_manager):
        """Test initialization"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            strategy = StatisticalArbitrageStrategy(
                mock_risk_manager,
                reference_symbol="SPY",
                lookback_period=60,
            )

        assert strategy.name == "StatArbStrategy"
        assert strategy.reference_symbol == "SPY"
        assert strategy.lookback_period == 60

    @pytest.mark.asyncio
    async def test_generate_signal_insufficient_data(self, mock_risk_manager):
        """Test hold signal with insufficient data"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            strategy = StatisticalArbitrageStrategy(
                mock_risk_manager,
                lookback_period=60,
            )

            # Only 30 rows, need 60
            price_data = pd.DataFrame({"close": [100 + i for i in range(30)]})
            features = pd.DataFrame()

            signal = await strategy.generate_signal("AAPL", price_data, features)

            assert signal.signal_type == SignalType.HOLD

    def test_get_required_features(self, mock_risk_manager):
        """Test required features"""
        with patch("backend.strategies.trading_strategies.get_settings") as mock_get:
            mock_get.return_value = MagicMock()

            strategy = StatisticalArbitrageStrategy(mock_risk_manager)

            # StatArb may need different features - check it returns a list
            features = strategy.get_required_features()
            assert isinstance(features, list)
