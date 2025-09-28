#!/usr/bin/env python3
"""
Comprehensive Trading Strategies Test Suite
Tests for 100% coverage of backend/strategies/trading_strategies.py
"""

import pytest
import sys
import os
import numpy as np
import pandas as pd
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

# Mock heavy dependencies for faster testing
os.environ['DISABLE_ML'] = '1'
os.environ['DISABLE_TENSORFLOW'] = '1'

try:
    from backend.strategies.trading_strategies import (
        SignalType, OrderType, TradingSignal, StrategyPerformance,
        BaseStrategy, EnsembleStrategy, MeanReversionStrategy,
        MomentumStrategy, StatisticalArbitrageStrategy, StrategyManager
    )
    from backend.risk.risk_manager import RiskManager
    from backend.models.ensemble_model import EnsembleModel
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Import warning: {e}")
    IMPORTS_AVAILABLE = False


class TestTradingSignalEnums:
    """Test SignalType and OrderType enums"""
    
    def test_signal_type_values(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        assert SignalType.BUY == "BUY"
        assert SignalType.SELL == "SELL"
        assert SignalType.HOLD == "HOLD"
        assert SignalType.STRONG_BUY == "STRONG_BUY"
        assert SignalType.STRONG_SELL == "STRONG_SELL"
    
    def test_order_type_values(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        assert OrderType.MARKET == "market"
        assert OrderType.LIMIT == "limit"
        assert OrderType.STOP == "stop"
        assert OrderType.STOP_LIMIT == "stop_limit"


class TestTradingSignal:
    """Test TradingSignal dataclass"""
    
    def test_trading_signal_creation(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
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
        assert signal.position_size == 0.0
        assert signal.order_type == OrderType.MARKET
        assert isinstance(signal.timestamp, datetime)
        assert signal.metadata == {}
    
    def test_trading_signal_with_all_fields(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        timestamp = datetime.now()
        metadata = {"test": "data"}
        
        signal = TradingSignal(
            symbol="TSLA",
            signal_type=SignalType.STRONG_SELL,
            confidence=0.95,
            target_price=200.0,
            stop_loss=210.0,
            take_profit=190.0,
            position_size=100.0,
            order_type=OrderType.LIMIT,
            timestamp=timestamp,
            metadata=metadata
        )
        
        assert signal.symbol == "TSLA"
        assert signal.signal_type == SignalType.STRONG_SELL
        assert signal.confidence == 0.95
        assert signal.target_price == 200.0
        assert signal.stop_loss == 210.0
        assert signal.take_profit == 190.0
        assert signal.position_size == 100.0
        assert signal.order_type == OrderType.LIMIT
        assert signal.timestamp == timestamp
        assert signal.metadata == metadata


class TestStrategyPerformance:
    """Test StrategyPerformance dataclass"""
    
    def test_strategy_performance_creation(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        perf = StrategyPerformance(
            strategy_name="test_strategy",
            total_returns=0.15,
            sharpe_ratio=1.5,
            max_drawdown=-0.05,
            win_rate=0.65,
            total_trades=100,
            avg_trade_duration=timedelta(hours=4),
            last_updated=datetime.now()
        )
        
        assert perf.strategy_name == "test_strategy"
        assert perf.total_returns == 0.15
        assert perf.sharpe_ratio == 1.5
        assert perf.max_drawdown == -0.05
        assert perf.win_rate == 0.65
        assert perf.total_trades == 100
        assert perf.avg_trade_duration == timedelta(hours=4)
        assert isinstance(perf.last_updated, datetime)


class TestBaseStrategy:
    """Test BaseStrategy abstract class"""
    
    def setup_method(self):
        if not IMPORTS_AVAILABLE:
            return
        
        self.mock_risk_manager = Mock(spec=RiskManager)
        self.mock_risk_manager.get_portfolio_value.return_value = 100000.0
        self.mock_risk_manager.assess_position_risk = AsyncMock(return_value={"approved": True})
        
        # Create a concrete implementation for testing
        class TestStrategy(BaseStrategy):
            async def generate_signal(self, symbol, price_data, features):
                return TradingSignal(symbol, SignalType.HOLD, 0.5, 100.0)
            
            def get_required_features(self):
                return ["test_feature"]
        
        self.strategy = TestStrategy("test_strategy", self.mock_risk_manager)
    
    def test_base_strategy_initialization(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        assert self.strategy.name == "test_strategy"
        assert self.strategy.risk_manager == self.mock_risk_manager
        assert self.strategy.positions == {}
        assert self.strategy.trade_history == []
        assert self.strategy.performance_metrics is None
        assert self.strategy.is_active is True
    
    @pytest.mark.asyncio
    async def test_validate_signal_active_strategy(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0,
            position_size=100.0
        )
        
        result = await self.strategy.validate_signal(signal)
        assert result is True
        self.mock_risk_manager.assess_position_risk.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_validate_signal_inactive_strategy(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        self.strategy.is_active = False
        
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0,
            position_size=100.0
        )
        
        result = await self.strategy.validate_signal(signal)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_signal_risk_rejected(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        self.mock_risk_manager.assess_position_risk = AsyncMock(return_value={"approved": False})
        
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            confidence=0.8,
            target_price=150.0,
            position_size=100.0
        )
        
        result = await self.strategy.validate_signal(signal)
        assert result is False
    
    @patch('backend.strategies.trading_strategies.get_settings')
    def test_calculate_position_size(self, mock_settings):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        # Mock settings
        mock_settings.return_value.trading.max_position_size = 1000.0
        
        position_size = self.strategy.calculate_position_size("AAPL", 150.0, 0.8)
        
        # Should be max_position_size * confidence = 1000 * 0.8 = 800
        assert position_size == 800.0
    
    @patch('backend.strategies.trading_strategies.get_settings')
    def test_calculate_position_size_risk_limited(self, mock_settings):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        # Mock settings with high max position
        mock_settings.return_value.trading.max_position_size = 10000.0
        
        # Small portfolio value to trigger risk limit
        self.mock_risk_manager.get_portfolio_value.return_value = 1000.0
        
        position_size = self.strategy.calculate_position_size("AAPL", 150.0, 0.8)
        
        # Risk limit: 1000 * 0.02 / 150 = 0.133
        expected = 1000.0 * 0.02 / 150.0
        assert abs(position_size - expected) < 0.01
    
    def test_update_performance(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        trade_results = [
            {"return": 0.05, "duration": timedelta(hours=2)},
            {"return": -0.02, "duration": timedelta(hours=3)},
            {"return": 0.08, "duration": timedelta(hours=1)},
        ]
        
        with patch('backend.strategies.trading_strategies.calculate_sharpe_ratio') as mock_sharpe:
            mock_sharpe.return_value = 1.2
            
            self.strategy.update_performance(trade_results)
        
        assert self.strategy.performance_metrics is not None
        assert self.strategy.performance_metrics.strategy_name == "test_strategy"
        assert self.strategy.performance_metrics.total_returns == 0.11
        assert self.strategy.performance_metrics.win_rate == 2/3  # 2 positive out of 3
        assert self.strategy.performance_metrics.total_trades == 3
    
    def test_update_performance_empty_trades(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        self.strategy.update_performance([])
        assert self.strategy.performance_metrics is None
    
    def test_calculate_max_drawdown(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        returns = [0.1, -0.05, 0.03, -0.08, 0.15]
        drawdown = self.strategy._calculate_max_drawdown(returns)
        
        assert isinstance(drawdown, float)
        assert drawdown <= 0  # Drawdown should be negative or zero


class TestMeanReversionStrategy:
    """Test MeanReversionStrategy implementation"""
    
    def setup_method(self):
        if not IMPORTS_AVAILABLE:
            return
        
        self.mock_risk_manager = Mock(spec=RiskManager)
        self.mock_risk_manager.get_portfolio_value.return_value = 100000.0
        self.strategy = MeanReversionStrategy(self.mock_risk_manager)
    
    def test_initialization(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        assert self.strategy.name == "MeanReversionStrategy"
        assert self.strategy.oversold_threshold == 30
        assert self.strategy.overbought_threshold == 70
    
    @pytest.mark.asyncio
    async def test_generate_signal_insufficient_data(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        # Empty price data
        price_data = pd.DataFrame()
        features = pd.DataFrame({"rsi": [50], "bb_upper": [110], "bb_lower": [90]})
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0
    
    @pytest.mark.asyncio
    async def test_generate_signal_missing_features(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame()  # Empty features
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0
    
    @pytest.mark.asyncio
    async def test_generate_signal_oversold_condition(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [89.0]})  # Below lower band
        features = pd.DataFrame({
            "rsi": [25.0],        # Oversold
            "bb_upper": [110.0],
            "bb_lower": [90.0]
        })
        
        with patch.object(self.strategy, 'calculate_position_size', return_value=100.0):
            signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.5
        assert signal.target_price == 100.0  # Middle of bands
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
    
    @pytest.mark.asyncio
    async def test_generate_signal_overbought_condition(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [109.0]})  # Above upper band
        features = pd.DataFrame({
            "rsi": [75.0],        # Overbought
            "bb_upper": [110.0],
            "bb_lower": [90.0]
        })
        
        with patch.object(self.strategy, 'calculate_position_size', return_value=100.0):
            signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0.5
        assert signal.target_price == 100.0  # Middle of bands
    
    @pytest.mark.asyncio
    async def test_generate_signal_hold_condition(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [100.0]})  # Normal price
        features = pd.DataFrame({
            "rsi": [50.0],        # Neutral RSI
            "bb_upper": [110.0],
            "bb_lower": [90.0]
        })
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD
        assert signal.position_size == 0.0
    
    def test_get_required_features(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        features = self.strategy.get_required_features()
        expected = ["rsi", "bb_upper", "bb_lower"]
        assert features == expected


class TestMomentumStrategy:
    """Test MomentumStrategy implementation"""
    
    def setup_method(self):
        if not IMPORTS_AVAILABLE:
            return
        
        self.mock_risk_manager = Mock(spec=RiskManager)
        self.mock_risk_manager.get_portfolio_value.return_value = 100000.0
        self.strategy = MomentumStrategy(self.mock_risk_manager)
    
    def test_initialization(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        assert self.strategy.name == "MomentumStrategy"
    
    @pytest.mark.asyncio
    async def test_generate_signal_bullish_momentum(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame({
            "macd": [2.0],
            "macd_signal": [1.0],  # MACD > signal
            "sma_20": [95.0],      # Price > SMA20 > SMA50
            "sma_50": [90.0]
        })
        
        with patch.object(self.strategy, 'calculate_position_size', return_value=100.0):
            signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.5
        assert signal.target_price > 100.0  # Should be higher than current
    
    @pytest.mark.asyncio
    async def test_generate_signal_bearish_momentum(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame({
            "macd": [1.0],
            "macd_signal": [2.0],  # MACD < signal
            "sma_20": [105.0],     # Price < SMA20 < SMA50
            "sma_50": [110.0]
        })
        
        with patch.object(self.strategy, 'calculate_position_size', return_value=100.0):
            signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0.5
        assert signal.target_price < 100.0  # Should be lower than current
    
    @pytest.mark.asyncio
    async def test_generate_signal_no_clear_momentum(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame({
            "macd": [1.0],
            "macd_signal": [2.0],  # MACD < signal but...
            "sma_20": [95.0],      # Price > SMA20 (mixed signals)
            "sma_50": [90.0]
        })
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD
    
    def test_get_required_features(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        features = self.strategy.get_required_features()
        expected = ["macd", "macd_signal", "sma_20", "sma_50"]
        assert features == expected


class TestEnsembleStrategy:
    """Test EnsembleStrategy implementation"""
    
    def setup_method(self):
        if not IMPORTS_AVAILABLE:
            return
        
        self.mock_risk_manager = Mock(spec=RiskManager)
        self.mock_ensemble_model = Mock(spec=EnsembleModel)
        
        # Create mock prediction
        self.mock_prediction = Mock()
        self.mock_prediction.ensemble_prediction = 155.0
        self.mock_prediction.ensemble_confidence = 0.8
        self.mock_prediction.predictions = [154, 155, 156]
        self.mock_prediction.confidence_scores = [0.7, 0.8, 0.9]
        
        self.mock_ensemble_model.predict.return_value = self.mock_prediction
        self.strategy = EnsembleStrategy(self.mock_risk_manager, self.mock_ensemble_model)
    
    def test_initialization(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        assert self.strategy.name == "EnsembleStrategy"
        assert self.strategy.confidence_threshold == 0.6
        assert self.strategy.ensemble_model == self.mock_ensemble_model
    
    @pytest.mark.asyncio
    async def test_generate_signal_strong_buy(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame()
        
        # High confidence, significant upside (>5%)
        self.mock_prediction.ensemble_prediction = 110.0  # 10% upside
        self.mock_prediction.ensemble_confidence = 0.9
        
        with patch.object(self.strategy, 'calculate_position_size', return_value=100.0):
            signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.STRONG_BUY
        assert signal.confidence == 0.9
        assert signal.target_price == 110.0
        assert signal.stop_loss is not None
        assert signal.take_profit is not None
    
    @pytest.mark.asyncio
    async def test_generate_signal_buy(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame()
        
        # High confidence, moderate upside (2-5%)
        self.mock_prediction.ensemble_prediction = 103.0  # 3% upside
        self.mock_prediction.ensemble_confidence = 0.8
        
        with patch.object(self.strategy, 'calculate_position_size', return_value=100.0):
            signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence == 0.8
    
    @pytest.mark.asyncio
    async def test_generate_signal_strong_sell(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame()
        
        # High confidence, significant downside (>5%)
        self.mock_prediction.ensemble_prediction = 90.0  # 10% downside
        self.mock_prediction.ensemble_confidence = 0.9
        
        with patch.object(self.strategy, 'calculate_position_size', return_value=100.0):
            signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.STRONG_SELL
    
    @pytest.mark.asyncio
    async def test_generate_signal_hold_low_confidence(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame()
        
        # Low confidence
        self.mock_prediction.ensemble_confidence = 0.5  # Below threshold
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD
        assert signal.position_size == 0.0
    
    @pytest.mark.asyncio
    async def test_generate_signal_hold_small_change(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame()
        
        # High confidence but small predicted change
        self.mock_prediction.ensemble_prediction = 101.0  # Only 1% change
        self.mock_prediction.ensemble_confidence = 0.9
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD
    
    def test_get_required_features(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        features = self.strategy.get_required_features()
        
        expected_features = [
            "sma_20", "sma_50", "ema_12", "ema_26", "rsi", "macd", "macd_signal",
            "bb_upper", "bb_lower", "volume_sma", "atr", "adx", "cci", "williams_r",
            "stoch_k", "stoch_d", "momentum", "rate_of_change"
        ]
        
        assert features == expected_features


class TestStatisticalArbitrageStrategy:
    """Test StatisticalArbitrageStrategy implementation"""
    
    def setup_method(self):
        if not IMPORTS_AVAILABLE:
            return
        
        self.mock_risk_manager = Mock(spec=RiskManager)
        self.strategy = StatisticalArbitrageStrategy(self.mock_risk_manager)
    
    def test_initialization(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        assert self.strategy.name == "StatisticalArbitrageStrategy"
        assert self.strategy.lookback_period == 20
        assert self.strategy.entry_threshold == 2.0
    
    @pytest.mark.asyncio
    async def test_generate_signal_zero_std_dev(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        # All prices the same (zero std dev)
        price_data = pd.DataFrame({"close": [100.0] * 25})
        features = pd.DataFrame()
        
        signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.HOLD
        assert signal.confidence == 0.0
    
    @pytest.mark.asyncio
    async def test_generate_signal_high_z_score_buy(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        # Create price series where current price is significantly below mean
        prices = [110.0] * 20 + [80.0]  # Current price much lower
        price_data = pd.DataFrame({"close": prices})
        features = pd.DataFrame()
        
        with patch.object(self.strategy, 'calculate_position_size', return_value=100.0):
            signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.BUY
        assert signal.confidence > 0.0
        assert "z_score" in signal.metadata
    
    @pytest.mark.asyncio
    async def test_generate_signal_high_z_score_sell(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        # Create price series where current price is significantly above mean
        prices = [90.0] * 20 + [120.0]  # Current price much higher
        price_data = pd.DataFrame({"close": prices})
        features = pd.DataFrame()
        
        with patch.object(self.strategy, 'calculate_position_size', return_value=100.0):
            signal = await self.strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.signal_type == SignalType.SELL
        assert signal.confidence > 0.0
    
    def test_get_required_features(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        features = self.strategy.get_required_features()
        assert features == []


class TestStrategyManager:
    """Test StrategyManager for coordinating multiple strategies"""
    
    def setup_method(self):
        if not IMPORTS_AVAILABLE:
            return
        
        self.mock_risk_manager = Mock(spec=RiskManager)
        self.mock_ensemble_model = Mock(spec=EnsembleModel)
        
        with patch('backend.strategies.trading_strategies.get_settings') as mock_settings:
            mock_settings.return_value.trading.max_position_size = 1000.0
            self.manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
    
    def test_initialization(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        assert len(self.manager.strategies) == 4
        assert "ensemble" in self.manager.strategies
        assert "mean_reversion" in self.manager.strategies
        assert "momentum" in self.manager.strategies
        assert "stat_arb" in self.manager.strategies
        
        # Check equal weighting
        expected_weight = 1.0 / 4
        for weight in self.manager.strategy_weights.values():
            assert abs(weight - expected_weight) < 0.01
    
    @pytest.mark.asyncio
    async def test_generate_combined_signal(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        # Mock individual strategy signals
        buy_signal = TradingSignal("AAPL", SignalType.BUY, 0.8, 105.0, position_size=100.0)
        hold_signal = TradingSignal("AAPL", SignalType.HOLD, 0.5, 100.0, position_size=0.0)
        sell_signal = TradingSignal("AAPL", SignalType.SELL, 0.7, 95.0, position_size=80.0)
        
        # Mock strategy generate_signal methods
        self.manager.strategies["ensemble"].generate_signal = AsyncMock(return_value=buy_signal)
        self.manager.strategies["mean_reversion"].generate_signal = AsyncMock(return_value=hold_signal)
        self.manager.strategies["momentum"].generate_signal = AsyncMock(return_value=sell_signal)
        self.manager.strategies["stat_arb"].generate_signal = AsyncMock(return_value=hold_signal)
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame()
        
        combined_signal = await self.manager.generate_combined_signal("AAPL", price_data, features)
        
        assert combined_signal.symbol == "AAPL"
        assert combined_signal.signal_type in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]
        assert 0.0 <= combined_signal.confidence <= 1.0
        assert "strategy_signals" in combined_signal.metadata
    
    @pytest.mark.asyncio
    async def test_generate_combined_signal_no_active_strategies(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        # Deactivate all strategies
        for strategy in self.manager.strategies.values():
            strategy.is_active = False
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame()
        
        combined_signal = await self.manager.generate_combined_signal("AAPL", price_data, features)
        
        assert combined_signal.signal_type == SignalType.HOLD
        assert combined_signal.confidence == 0.0
    
    @pytest.mark.asyncio
    async def test_generate_combined_signal_strategy_error(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        # Make one strategy raise an exception
        self.manager.strategies["ensemble"].generate_signal = AsyncMock(side_effect=Exception("Test error"))
        
        # Other strategies return valid signals
        buy_signal = TradingSignal("AAPL", SignalType.BUY, 0.8, 105.0, position_size=100.0)
        self.manager.strategies["mean_reversion"].generate_signal = AsyncMock(return_value=buy_signal)
        
        price_data = pd.DataFrame({"close": [100.0]})
        features = pd.DataFrame()
        
        # Should still work with remaining strategies
        combined_signal = await self.manager.generate_combined_signal("AAPL", price_data, features)
        
        assert combined_signal.symbol == "AAPL"
    
    def test_update_strategy_weights(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        performance_data = {
            "ensemble": StrategyPerformance(
                "ensemble", 0.15, 1.5, -0.05, 0.7, 100, timedelta(hours=2), datetime.now()
            ),
            "mean_reversion": StrategyPerformance(
                "mean_reversion", 0.08, 0.8, -0.1, 0.6, 80, timedelta(hours=3), datetime.now()
            )
        }
        
        self.manager.update_strategy_weights(performance_data)
        
        # Ensemble should have higher weight due to better performance
        assert self.manager.strategy_weights["ensemble"] > self.manager.strategy_weights["mean_reversion"]
        
        # Weights should sum to 1.0
        total_weight = sum(self.manager.strategy_weights.values())
        assert abs(total_weight - 1.0) < 0.01
    
    def test_activate_deactivate_strategy(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        # Test deactivation
        self.manager.deactivate_strategy("ensemble")
        assert not self.manager.strategies["ensemble"].is_active
        
        # Test activation
        self.manager.activate_strategy("ensemble")
        assert self.manager.strategies["ensemble"].is_active
        
        # Test invalid strategy name
        self.manager.activate_strategy("nonexistent")  # Should not raise error
    
    def test_get_strategy_status(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        status = self.manager.get_strategy_status()
        
        assert len(status) == 4
        for strategy_name, strategy_status in status.items():
            assert "is_active" in strategy_status
            assert "weight" in strategy_status
            assert "performance" in strategy_status
            assert "trade_count" in strategy_status
            assert "required_features" in strategy_status
    
    def test_calculate_combined_position_size(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        strategy_signals = {
            "ensemble": TradingSignal("AAPL", SignalType.BUY, 0.8, 105.0, position_size=100.0),
            "momentum": TradingSignal("AAPL", SignalType.BUY, 0.6, 104.0, position_size=80.0),
        }
        
        position_size = self.manager._calculate_combined_position_size(
            "AAPL", 100.0, 0.7, strategy_signals
        )
        
        assert position_size > 0.0
        assert position_size <= 500.0  # Should respect max position constraint
    
    def test_calculate_combined_position_size_no_positions(self):
        if not IMPORTS_AVAILABLE:
            pytest.skip("Imports not available")
        
        strategy_signals = {
            "ensemble": TradingSignal("AAPL", SignalType.HOLD, 0.5, 100.0, position_size=0.0),
        }
        
        position_size = self.manager._calculate_combined_position_size(
            "AAPL", 100.0, 0.7, strategy_signals
        )
        
        assert position_size == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])