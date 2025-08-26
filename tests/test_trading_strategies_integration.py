"""
Trading Strategies Integration Tests
Comprehensive test suite for trading strategies module covering integration scenarios,
StrategyManager, and complex workflow testing.
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch, AsyncMock
import numpy as np
import asyncio

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


class TestRebalancingStrategy:
    """Test RebalancingStrategy implementation"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_risk_manager = Mock()
        # Configure risk_manager methods to return proper numeric values
        self.mock_risk_manager.get_portfolio_value.return_value = 100000.0  # $100k portfolio
        self.mock_risk_manager.get_positions.return_value = {
            "AAPL": {"market_value": 30000.0},  # $30k in AAPL = 30% weight
            "GOOGL": {"market_value": 70000.0}  # $70k in GOOGL = 70% weight
        }
        
    def test_rebalancing_initialization(self):
        """Test RebalancingStrategy initialization"""
        target_weights = {"AAPL": 0.4, "GOOGL": 0.3, "MSFT": 0.3}
        strategy = RebalancingStrategy(
            self.mock_risk_manager, 
            target_weights=target_weights
        )
        
        assert strategy.target_weights == target_weights
        assert strategy.rebalance_threshold == 0.05  # default value
        assert strategy.name == "RebalancingStrategy"

    @pytest.mark.asyncio
    async def test_rebalancing_buy_signal(self):
        """Test rebalancing BUY signal generation"""
        target_weights = {"AAPL": 0.5, "GOOGL": 0.5}
        strategy = RebalancingStrategy(self.mock_risk_manager, target_weights=target_weights)
        
        price_data = pd.DataFrame({
            'close': [150.0],
            'volume': [1000]
        })
        features = pd.DataFrame({'feature1': [1]})

        with patch('backend.strategies.trading_strategies.get_settings') as mock_settings:
            mock_settings.return_value.trading.max_position_size = 1000.0
            
            signal = await strategy.generate_signal("AAPL", price_data, features)
            
            assert signal.symbol == "AAPL"
            # AAPL is 30% but target is 50%, should generate BUY
            assert signal.signal_type == SignalType.BUY
            assert signal.confidence > 0

    @pytest.mark.asyncio
    async def test_rebalancing_sell_signal(self):
        """Test rebalancing SELL signal generation"""
        target_weights = {"AAPL": 0.1, "GOOGL": 0.9}  # Target much lower AAPL
        strategy = RebalancingStrategy(self.mock_risk_manager, target_weights=target_weights)
        
        price_data = pd.DataFrame({
            'close': [150.0],
            'volume': [1000]
        })
        features = pd.DataFrame({'feature1': [1]})

        with patch('backend.strategies.trading_strategies.get_settings') as mock_settings:
            mock_settings.return_value.trading.max_position_size = 1000.0
            
            signal = await strategy.generate_signal("AAPL", price_data, features)
            
            assert signal.symbol == "AAPL"
            # AAPL is 30% but target is 10%, should generate SELL
            assert signal.signal_type == SignalType.SELL
            assert signal.confidence > 0

    @pytest.mark.asyncio
    async def test_rebalancing_hold_signal(self):
        """Test rebalancing HOLD signal when weights are balanced"""
        target_weights = {"AAPL": 0.3, "GOOGL": 0.7}  # Matches current positions exactly
        strategy = RebalancingStrategy(self.mock_risk_manager, target_weights=target_weights)
        
        price_data = pd.DataFrame({
            'close': [150.0],
            'volume': [1000]
        })
        features = pd.DataFrame({'feature1': [1]})
        
        signal = await strategy.generate_signal("AAPL", price_data, features)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.HOLD  # Within threshold
        assert signal.confidence >= 0

    @pytest.mark.asyncio
    async def test_rebalancing_unknown_symbol(self):
        """Test rebalancing with symbol not in target weights"""
        target_weights = {"AAPL": 0.5, "GOOGL": 0.5}
        strategy = RebalancingStrategy(self.mock_risk_manager, target_weights=target_weights)
        
        price_data = pd.DataFrame({
            'close': [150.0],
            'volume': [1000]
        })
        features = pd.DataFrame({'feature1': [1]})

        signal = await strategy.generate_signal("TSLA", price_data, features)  # Not in target weights
        
        assert signal.symbol == "TSLA"
        assert signal.signal_type == SignalType.HOLD  # Default for unknown symbols

    def test_rebalancing_required_features(self):
        """Test RebalancingStrategy required features"""
        strategy = RebalancingStrategy(self.mock_risk_manager, target_weights={"AAPL": 1.0})
        features = strategy.get_required_features()
        assert features == []


class TestStrategyManager:
    """Test StrategyManager comprehensive functionality"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_risk_manager = Mock()
        self.mock_ensemble_model = Mock()
        
    def test_strategy_manager_initialization(self):
        """Test StrategyManager initialization"""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        assert manager.risk_manager == self.mock_risk_manager
        assert manager.ensemble_model == self.mock_ensemble_model
        assert len(manager.strategies) == 4  # ensemble, mean_reversion, momentum, stat_arb
        assert "ensemble" in manager.strategies
        assert "mean_reversion" in manager.strategies
        assert "momentum" in manager.strategies
        assert "stat_arb" in manager.strategies

    @pytest.mark.asyncio
    async def test_combined_signal_all_active(self):
        """Test combined signal generation with all strategies active"""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Mock signals from each strategy
        mock_signals = {
            "ensemble": TradingSignal("AAPL", SignalType.BUY, 0.8, 150.0, position_size=100),
            "mean_reversion": TradingSignal("AAPL", SignalType.HOLD, 0.3, 148.0, position_size=0),
            "momentum": TradingSignal("AAPL", SignalType.BUY, 0.9, 152.0, position_size=150),
            "stat_arb": TradingSignal("AAPL", SignalType.SELL, 0.6, 145.0, position_size=75)
        }
        
        # Patch strategy generate_signal methods
        with patch.multiple(
            manager.strategies["ensemble"],
            generate_signal=AsyncMock(return_value=mock_signals["ensemble"]),
            is_active=True
        ), patch.multiple(
            manager.strategies["mean_reversion"],
            generate_signal=AsyncMock(return_value=mock_signals["mean_reversion"]),
            is_active=True
        ), patch.multiple(
            manager.strategies["momentum"],
            generate_signal=AsyncMock(return_value=mock_signals["momentum"]),
            is_active=True
        ), patch.multiple(
            manager.strategies["stat_arb"],
            generate_signal=AsyncMock(return_value=mock_signals["stat_arb"]),
            is_active=True
        ), patch('backend.strategies.trading_strategies.get_settings') as mock_settings:
            
            mock_settings.return_value.trading.max_position_size = 1000.0

            price_data = pd.DataFrame({'close': [150.0]})
            features = pd.DataFrame({'feature1': [1]})

            combined_signal = await manager.generate_combined_signal("AAPL", price_data, features)
            
            assert combined_signal.symbol == "AAPL"
            # With 2 BUY votes vs 1 SELL vote, should be BUY
            assert combined_signal.signal_type == SignalType.BUY
            assert combined_signal.confidence > 0

    def test_update_strategy_weights(self):
        """Test strategy weight updates based on performance"""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Mock performance data
        performance_data = {
            "ensemble": StrategyPerformance(
                strategy_name="ensemble",
                total_returns=0.15,
                sharpe_ratio=1.2,
                max_drawdown=-0.05,
                win_rate=0.65,
                total_trades=100,
                avg_trade_duration=timedelta(hours=4),
                last_updated=datetime.now()
            ),
            "momentum": StrategyPerformance(
                strategy_name="momentum",
                total_returns=0.20,
                sharpe_ratio=1.5,
                max_drawdown=-0.03,
                win_rate=0.70,
                total_trades=120,
                avg_trade_duration=timedelta(hours=2),
                last_updated=datetime.now()
            )
        }

        original_weights = manager.strategy_weights.copy()

        manager.update_strategy_weights(performance_data)

        # Weights should have changed
        assert manager.strategy_weights != original_weights
    
        # Total weights should still sum to approximately 1.0 (allowing floating point errors)
        total_weight = sum(manager.strategy_weights.values())
        assert abs(total_weight - 1.0) < 0.01  # More lenient tolerance

    def test_get_strategy_status(self):
        """Test strategy status reporting"""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Mock some performance metrics
        manager.strategies["ensemble"].performance_metrics = StrategyPerformance(
            strategy_name="ensemble",
            total_returns=0.10,
            sharpe_ratio=1.0,
            max_drawdown=-0.05,
            win_rate=0.60,
            total_trades=50,
            avg_trade_duration=timedelta(hours=3),
            last_updated=datetime.now()
        )
        
        status = manager.get_strategy_status()
        
        assert "ensemble" in status
        assert "mean_reversion" in status
        assert "momentum" in status
        assert "stat_arb" in status
        
        # Check ensemble status details
        ensemble_status = status["ensemble"]
        assert "is_active" in ensemble_status
        assert "weight" in ensemble_status
        assert "performance" in ensemble_status
        assert "trade_count" in ensemble_status
        assert "required_features" in ensemble_status
        
        assert ensemble_status["performance"] is not None

    def test_activate_deactivate_strategy(self):
        """Test strategy activation/deactivation"""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Initially all strategies should be active
        assert all(strategy.is_active for strategy in manager.strategies.values())
        
        # Deactivate a strategy
        manager.deactivate_strategy("mean_reversion")
        assert not manager.strategies["mean_reversion"].is_active
        assert manager.strategies["ensemble"].is_active  # Others still active
        
        # Reactivate
        manager.activate_strategy("mean_reversion")
        assert manager.strategies["mean_reversion"].is_active


class TestStrategyIntegrationWorkflows:
    """Test complex integration workflows and edge cases"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.mock_risk_manager = Mock()
        self.mock_ensemble_model = Mock()

    @pytest.mark.asyncio
    async def test_complete_trading_workflow(self):
        """Test complete trading signal generation workflow"""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)

        # Mock ensemble model with controlled behavior
        self.mock_ensemble_model.predict_async.return_value = {
            'prediction': 0.7,
            'confidence': 0.8
        }
        self.mock_ensemble_model.get_feature_names.return_value = ['feature1']

        # Create simple market data
        price_data = pd.DataFrame({
            'close': [100.0, 101.0, 102.0, 103.0, 104.0],
            'volume': [1000, 1100, 1200, 1000, 900],
            'high': [100.5, 101.5, 102.5, 103.5, 104.5],
            'low': [99.5, 100.5, 101.5, 102.5, 103.5],
            'open': [100.0, 101.0, 102.0, 103.0, 104.0]
        })

        features = pd.DataFrame({
            'feature1': [0.1, 0.2, 0.3, 0.4, 0.5]
        })

        # Mock all strategy dependencies properly
        with patch('backend.strategies.trading_strategies.get_settings') as mock_settings:
            mock_settings.return_value.trading.max_position_size = 1000.0
            
            # Mock strategy methods to avoid complex dependencies
            for strategy_name, strategy in manager.strategies.items():
                strategy.generate_signal = AsyncMock(
                    return_value=TradingSignal(
                        "AAPL", SignalType.BUY, 0.5, 104.0, position_size=50
                    )
                )

            # Generate combined signal
            signal = await manager.generate_combined_signal("AAPL", price_data, features)

            # Validate signal structure
            assert signal.symbol == "AAPL"
            assert signal.signal_type in [SignalType.BUY, SignalType.SELL, SignalType.HOLD]
            assert 0.0 <= signal.confidence <= 1.0
            assert hasattr(signal, 'target_price')

    def test_strategy_performance_tracking_workflow(self):
        """Test strategy performance tracking and weight adjustment"""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)

        # Simulate trading history and performance
        initial_weights = manager.strategy_weights.copy()

        # Mock performance metrics for different strategies
        performance_data = {
            "ensemble": StrategyPerformance(
                strategy_name="ensemble",
                total_returns=0.12,
                sharpe_ratio=1.1,
                max_drawdown=-0.04,
                win_rate=0.62,
                total_trades=30,
                avg_trade_duration=timedelta(hours=3),
                last_updated=datetime.now()
            ),
            "momentum": StrategyPerformance(
                strategy_name="momentum",
                total_returns=0.18,
                sharpe_ratio=1.4,
                max_drawdown=-0.03,
                win_rate=0.68,
                total_trades=40,
                avg_trade_duration=timedelta(hours=2),
                last_updated=datetime.now()
            )
        }

        # Apply performance updates
        manager.update_strategy_weights(performance_data)

        # Verify weights are valid
        total_weight = sum(manager.strategy_weights.values())
        assert abs(total_weight - 1.0) < 0.01  # More lenient tolerance for floating point

        # Verify momentum (better performer) got higher weight
        assert manager.strategy_weights["momentum"] >= manager.strategy_weights["ensemble"]

        # Verify weights changed from initial state
        assert manager.strategy_weights != initial_weights

    @pytest.mark.asyncio
    async def test_strategy_error_handling_workflow(self):
        """Test strategy error handling and recovery"""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)

        # Mock one strategy to work, others to fail
        working_signal = TradingSignal("AAPL", SignalType.BUY, 0.8, 150.0, position_size=100)

        with patch.multiple(
            manager.strategies["ensemble"],
            generate_signal=AsyncMock(return_value=working_signal),
            is_active=True
        ), patch.multiple(
            manager.strategies["mean_reversion"],
            generate_signal=AsyncMock(side_effect=Exception("Strategy error")),
            is_active=True
        ), patch.multiple(
            manager.strategies["momentum"],
            generate_signal=AsyncMock(side_effect=Exception("Another error")),
            is_active=True
        ), patch.multiple(
            manager.strategies["stat_arb"],
            generate_signal=AsyncMock(side_effect=Exception("Third error")),
            is_active=True
        ), patch('backend.strategies.trading_strategies.get_settings') as mock_settings:

            mock_settings.return_value.trading.max_position_size = 1000.0

            price_data = pd.DataFrame({'close': [150.0]})
            features = pd.DataFrame({'feature1': [1]})

            combined_signal = await manager.generate_combined_signal("AAPL", price_data, features)
            
            # Should still work with one functioning strategy
            assert combined_signal.symbol == "AAPL"
            assert combined_signal.signal_type == SignalType.BUY
            # Allow for slight floating point differences
            assert abs(combined_signal.confidence - 0.8) < 0.01

    def test_empty_portfolio_scenario(self):
        """Test handling of empty portfolio scenario"""
        manager = StrategyManager(self.mock_risk_manager, self.mock_ensemble_model)
        
        # Test with empty performance data
        empty_performance = {}
        original_weights = manager.strategy_weights.copy()
        
        manager.update_strategy_weights(empty_performance)
        
        # Weights should remain unchanged with empty data
        assert manager.strategy_weights == original_weights
        
        # Total should still sum to 1
        total_weight = sum(manager.strategy_weights.values())
        assert abs(total_weight - 1.0) < 0.001
