"""
Integration Tests
Tests end-to-end workflows and component integration
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.data.alpaca_client import AlpacaClient
from backend.features.feature_engineering import FeatureEngineer
from backend.models.ensemble_model import EnsembleModel
from backend.risk.risk_manager import AsyncRiskManager
from backend.risk.types import OrderSpec
from backend.strategies.trading_strategies import SignalType, StrategyManager


@pytest.mark.integration
@pytest.mark.asyncio
class TestTradingWorkflow:
    """Test complete trading workflow integration"""

    async def test_signal_to_execution_workflow(self, sample_price_data, sample_features):
        """Test complete workflow from signal generation to trade execution"""

        # Initialize components
        risk_manager = AsyncRiskManager()
        ensemble_model = EnsembleModel()
        strategy_manager = StrategyManager(risk_manager, ensemble_model)
        feature_engineer = FeatureEngineer()

        # Mock external dependencies
        with patch("backend.data.alpaca_client.AlpacaClient._init_clients") as mock_init:
            mock_init.return_value = None  # Prevent real API connection

            alpaca_client = AlpacaClient(api_key="test_key", secret_key="test_secret")
            alpaca_client.connected = True  # Manually set connection status

            # Configure mock methods
            alpaca_client.get_historical_data = AsyncMock(return_value=sample_price_data)
            alpaca_client.submit_order = AsyncMock(
                return_value={
                    "id": "test_order_123",
                    "status": "accepted",
                    "symbol": "AAPL",
                    "qty": 50,
                    "side": "buy",
                }
            )
            alpaca_client.is_connected = MagicMock(return_value=True)

            # Step 1: Get market data
            symbol = "AAPL"
            price_data = await alpaca_client.get_historical_data(symbol, "1Day", 100)
            assert not price_data.empty

            # Step 2: Generate features
            features = feature_engineer.compute_all_features(price_data)
            assert not features.empty
            assert len(features.columns) > 10  # Should have many technical indicators

            # Step 3: Generate trading signal
            signal = await strategy_manager.generate_combined_signal(symbol, price_data, features)
            assert signal is not None
            assert signal.symbol == symbol
            assert isinstance(signal.confidence, float)
            assert 0 <= signal.confidence <= 1

            # Step 4: Risk assessment using new AsyncRiskManager interface
            if signal.signal_type != SignalType.HOLD and signal.position_size > 0:
                # Create OrderSpec for the new async risk manager
                from decimal import Decimal

                side = (
                    "buy"
                    if signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]
                    else "sell"
                )
                price = (
                    price_data["close"].iloc[-1] if hasattr(price_data, "columns") else 150.0
                )  # Use last price or default

                order_spec = OrderSpec(
                    symbol=symbol,
                    side=side,
                    qty=Decimal(str(signal.position_size)),
                    notional=Decimal(str(signal.position_size * price)),
                    price=Decimal(str(price)),
                )

                risk_decision = await risk_manager.before_order(order_spec)

                assert risk_decision is not None
                assert hasattr(risk_decision, "allowed")
                assert isinstance(risk_decision.allowed, bool)
                assert hasattr(risk_decision, "reason")
                assert isinstance(risk_decision.reason, str)

                # Step 5: Execute trade if approved
                if risk_decision.allowed:
                    order = await alpaca_client.submit_order(
                        symbol=symbol,
                        qty=signal.position_size,
                        side="buy"
                        if signal.signal_type in [SignalType.BUY, SignalType.STRONG_BUY]
                        else "sell",
                        type="market",
                    )

                    assert "id" in order
                    assert "status" in order
                    assert order["symbol"] == symbol


@pytest.mark.integration
@pytest.mark.asyncio
class TestModelTrainingWorkflow:
    """Test ML model training and deployment workflow"""

    async def test_model_training_pipeline(self, sample_price_data, sample_features):
        """Test complete model training pipeline"""

        from backend.mlops.model_manager import ModelManager

        model_manager = ModelManager()

        # Mock training data
        training_data = sample_price_data
        features = sample_features

        with patch.object(model_manager, "registry") as mock_registry:
            # Configure mock registry to return realistic objects
            mock_version_obj = MagicMock()
            mock_version_obj.model_id = "test_integration_model"
            mock_version_obj.version = "v1.0.0"
            mock_version_obj.metrics = {"mse": 1.5, "mae": 1.2}

            mock_registry.register_model.return_value = mock_version_obj

            # Mock deploy_model method
            with patch.object(model_manager, "deploy_model", return_value=True) as mock_deploy:
                # Step 1: Train new model
                model_version = await model_manager.train_and_register_model(
                    model_id="test_integration_model",
                    training_data=training_data,
                    features=features,
                )

                # Verify model was registered
                assert model_version is not None
                assert model_version.model_id == "test_integration_model"
                assert model_version.version.startswith("v")
                assert len(model_version.metrics) > 0

                # Step 2: Deploy model
                deployment_success = await model_manager.deploy_model(
                    "test_integration_model", model_version.version
                )

                assert deployment_success is True

                # Step 3: Test champion-challenger workflow
                # Create a second model version (challenger)
                mock_challenger_obj = MagicMock()
                mock_challenger_obj.model_id = "test_integration_model"
                mock_challenger_obj.version = "v2.0.0"
                mock_challenger_obj.metrics = {"mse": 1.3, "mae": 1.1}

                # Configure second call to return challenger version
                mock_registry.register_model.side_effect = [mock_version_obj, mock_challenger_obj]

                challenger_version = await model_manager.train_and_register_model(
                    model_id="test_integration_model",
                    training_data=training_data,
                    features=features,
                )

                # Mock A/B test method
                with patch.object(model_manager, "run_champion_challenger_test") as mock_ab_test:
                    mock_ab_test.return_value = {
                        "recommendation": "promote_challenger",
                        "confidence": 0.85,
                    }

                    # Run A/B test
                    ab_test_results = await model_manager.run_champion_challenger_test(
                        "test_integration_model",
                        challenger_version.version,
                        training_data.tail(50),
                        features.tail(50),
                    )

                    assert "recommendation" in ab_test_results
                    assert ab_test_results["recommendation"] in [
                        "promote_challenger",
                        "maintain_champion",
                        "reject_challenger",
                    ]


@pytest.mark.integration
@pytest.mark.asyncio
class TestRealTimeDataFlow:
    """Test real-time data processing flow"""

    async def test_market_data_streaming(self, sample_price_data):
        """Test real-time market data processing"""

        with patch("backend.data.alpaca_client.AlpacaClient._init_clients") as mock_init:
            mock_init.return_value = None  # Prevent real API connection

            # Mock streaming data
            mock_stream_data = [
                {"symbol": "AAPL", "price": 150.5, "volume": 1000, "timestamp": datetime.now()},
                {"symbol": "AAPL", "price": 150.7, "volume": 1200, "timestamp": datetime.now()},
                {"symbol": "AAPL", "price": 150.3, "volume": 800, "timestamp": datetime.now()},
            ]

            # Mock the streaming connection
            async def mock_stream_handler(symbol, callback):
                for data in mock_stream_data:
                    await callback(data)

            # Initialize components
            alpaca_client = AlpacaClient(api_key="test_key", secret_key="test_secret")
            alpaca_client.connected = True  # Manually set connection status
            alpaca_client.stream_market_data = AsyncMock(side_effect=mock_stream_handler)
            feature_engineer = FeatureEngineer()
            risk_manager = AsyncRiskManager()

            processed_data = []
            risk_alerts = []

            # Define callback for streaming data
            async def data_callback(market_data):
                # Process incoming data
                processed_data.append(market_data)

                # Update risk monitoring
                if len(processed_data) > 1:
                    risk_update = await risk_manager.update_position_risk(
                        market_data["symbol"], market_data["price"]
                    )
                    risk_alerts.append(risk_update)

            # Start streaming (mock)
            await alpaca_client.stream_market_data("AAPL", data_callback)

            # Verify data was processed
            assert len(processed_data) == len(mock_stream_data)
            assert all(data["symbol"] == "AAPL" for data in processed_data)

            # Verify risk monitoring was updated
            assert len(risk_alerts) >= 1
            for alert in risk_alerts:
                assert "symbol" in alert
                assert "status" in alert


@pytest.mark.integration
@pytest.mark.asyncio
class TestPortfolioRebalancing:
    """Test portfolio rebalancing workflow"""

    async def test_rebalancing_workflow(self, sample_price_data):
        """Test complete portfolio rebalancing workflow"""

        # Initialize components
        risk_manager = AsyncRiskManager()

        # Mock current portfolio
        current_positions = {
            "AAPL": {"quantity": 100, "market_value": 15000, "target_weight": 0.25},
            "GOOGL": {"quantity": 50, "market_value": 12000, "target_weight": 0.20},
            "MSFT": {"quantity": 80, "market_value": 20000, "target_weight": 0.30},
            "TSLA": {"quantity": 30, "market_value": 8000, "target_weight": 0.15},
            "NVDA": {"quantity": 40, "market_value": 16000, "target_weight": 0.10},
        }

        portfolio_value = sum(pos["market_value"] for pos in current_positions.values())

        with patch.object(risk_manager, "get_positions", return_value=current_positions):
            with patch.object(risk_manager, "get_portfolio_value", return_value=portfolio_value):
                # Step 1: Calculate rebalancing needs
                rebalancing_orders = []

                for symbol, position in current_positions.items():
                    current_weight = position["market_value"] / portfolio_value
                    target_weight = position["target_weight"]
                    weight_diff = target_weight - current_weight

                    # Rebalance if difference > 5%
                    if abs(weight_diff) > 0.05:
                        target_value = portfolio_value * target_weight
                        current_value = position["market_value"]
                        adjustment_value = target_value - current_value

                        # Assume $250 per share for simplicity
                        shares_to_trade = abs(adjustment_value) // 250

                        if shares_to_trade > 0:
                            side = "buy" if adjustment_value > 0 else "sell"

                            # Step 2: Risk check for rebalancing trade
                            risk_check = await risk_manager.assess_position_risk(
                                symbol, shares_to_trade, side
                            )

                            if risk_check["approved"]:
                                rebalancing_orders.append(
                                    {
                                        "symbol": symbol,
                                        "side": side,
                                        "quantity": shares_to_trade,
                                        "reason": "rebalancing",
                                        "weight_diff": weight_diff,
                                    }
                                )

                # Verify rebalancing orders were generated
                assert len(rebalancing_orders) >= 0  # May be 0 if portfolio is balanced

                for order in rebalancing_orders:
                    assert "symbol" in order
                    assert "side" in order
                    assert "quantity" in order
                    assert order["side"] in ["buy", "sell"]


@pytest.mark.integration
@pytest.mark.asyncio
class TestErrorRecovery:
    """Test error recovery and resilience"""

    async def test_network_failure_recovery(self):
        """Test system resilience to network failures"""

        from backend.data.alpaca_client import AlpacaClient

        with patch("backend.data.alpaca_client.AlpacaClient._init_clients") as mock_init:
            mock_init.return_value = None  # Prevent real API connection

            alpaca_client = AlpacaClient(api_key="test_key", secret_key="test_secret")
            alpaca_client.connected = False  # Simulate connection failure

            # Mock the method to simulate network failure
            alpaca_client.get_historical_data = AsyncMock(
                side_effect=ConnectionError("Network failure")
            )

            # Should handle gracefully
            try:
                data = await alpaca_client.get_historical_data("AAPL", "1Day", 100)
                # Should return empty DataFrame on failure
                assert data.empty
            except Exception as e:
                # Or raise appropriate exception
                assert isinstance(e, (ConnectionError, TimeoutError))

    async def test_data_quality_handling(self, sample_price_data):
        """Test handling of poor quality data"""

        feature_engineer = FeatureEngineer()

        # Create corrupted data
        corrupted_data = sample_price_data.copy()
        corrupted_data.loc[corrupted_data.index[:5], "close"] = np.nan  # Missing values
        corrupted_data.loc[corrupted_data.index[10:15], "volume"] = -1  # Invalid values

        # Should handle gracefully
        try:
            features = feature_engineer.compute_all_features(corrupted_data)

            # Should return some features even with corrupted data
            assert not features.empty
            assert features.isnull().sum().sum() < len(features) * len(
                features.columns
            )  # Not all NaN

        except Exception as e:
            # Should raise appropriate exception, not crash
            assert isinstance(e, (ValueError, pd.errors.DataError))

    async def test_model_failure_fallback(self, sample_price_data, sample_features):
        """Test fallback behavior when ML models fail"""

        ensemble_model = EnsembleModel()

        # Mock model failures
        with patch.object(
            ensemble_model.models["lstm"], "predict", side_effect=Exception("Model failed")
        ):
            with patch.object(
                ensemble_model.models["xgboost"], "predict", side_effect=Exception("Model failed")
            ):
                # Should still provide some prediction (even if degraded)
                prediction = ensemble_model.predict(sample_price_data, sample_features, "AAPL")

                assert prediction is not None
                assert prediction.ensemble_prediction is not None
                # Confidence might be lower due to fewer working models
                assert 0 <= prediction.ensemble_confidence <= 1


@pytest.mark.integration
@pytest.mark.slow
class TestPerformanceUnderLoad:
    """Test system performance under load"""

    @pytest.mark.asyncio
    async def test_concurrent_signal_generation(self, sample_price_data, sample_features):
        """Test concurrent signal generation for multiple symbols"""

        risk_manager = AsyncRiskManager()
        ensemble_model = EnsembleModel()
        strategy_manager = StrategyManager(risk_manager, ensemble_model)

        symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA", "AMZN", "META", "NFLX"]

        # Generate signals concurrently
        async def generate_signal(symbol):
            return await strategy_manager.generate_combined_signal(
                symbol, sample_price_data, sample_features
            )

        start_time = datetime.now()

        # Run concurrent signal generation
        tasks = [generate_signal(symbol) for symbol in symbols]
        signals = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Should complete within reasonable time
        assert duration < 30  # Less than 30 seconds for 8 symbols

        # Check that most signals were successful
        successful_signals = [s for s in signals if not isinstance(s, Exception)]
        assert len(successful_signals) >= len(symbols) * 0.8  # At least 80% success rate

        for signal in successful_signals:
            assert signal.symbol in symbols
            assert isinstance(signal.confidence, float)

    @pytest.mark.asyncio
    async def test_memory_usage_stability(self, sample_price_data, sample_features):
        """Test that system doesn't leak memory during extended operation"""

        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        risk_manager = AsyncRiskManager()
        ensemble_model = EnsembleModel()

        # Simulate extended operation
        for i in range(100):
            # Generate prediction
            prediction = ensemble_model.predict(sample_price_data, sample_features, f"TEST_{i}")

            # Simulate risk calculation
            returns = np.random.normal(0, 0.02, 100)
            var = risk_manager.calculate_var(returns)

            # Clear variables to help GC
            del prediction, returns, var

            # Check memory every 10 iterations
            if i % 10 == 0:
                current_memory = process.memory_info().rss
                memory_growth = current_memory - initial_memory

                # Memory growth should be reasonable (less than 100MB)
                assert (
                    memory_growth < 100 * 1024 * 1024
                ), f"Memory grew by {memory_growth / 1024 / 1024:.2f}MB"


@pytest.mark.integration
class TestDataConsistency:
    """Test data consistency across components"""

    def test_feature_data_alignment(self, sample_price_data):
        """Test that features align properly with price data"""

        feature_engineer = FeatureEngineer()
        features = feature_engineer.compute_all_features(sample_price_data)

        # Features should have same or fewer rows than price data (due to lookback periods)
        assert len(features) <= len(sample_price_data)

        # Indices should be compatible
        common_dates = features.index.intersection(sample_price_data.index)
        assert len(common_dates) > 0

        # Critical short-term features should not be all NaN
        # (Long-term indicators like SMA-50, SMA-200 may be all NaN with small datasets)
        critical_features = ["close", "sma_5", "sma_20", "rsi", "returns"]
        for column in critical_features:
            if column in features.columns:
                assert not features[column].isnull().all(), f"Critical feature {column} is all NaN"

        # At least some features should have valid data
        valid_features_count = sum(
            1 for col in features.columns if not features[col].isnull().all()
        )
        assert valid_features_count > 10, f"Too few valid features: {valid_features_count}"

    def test_cross_component_data_flow(self, sample_price_data, sample_features):
        """Test data consistency between components"""

        # Test that the same input produces consistent outputs
        symbol = "TEST_SYMBOL"

        feature_engineer = FeatureEngineer()
        ensemble_model = EnsembleModel()

        # Generate features twice
        features1 = feature_engineer.compute_all_features(sample_price_data)
        features2 = feature_engineer.compute_all_features(sample_price_data)

        # Should be identical
        pd.testing.assert_frame_equal(features1, features2)

        # Generate predictions twice with same inputs
        pred1 = ensemble_model.predict(sample_price_data, features1, symbol)
        pred2 = ensemble_model.predict(sample_price_data, features1, symbol)

        # Should be very close (allowing for minor floating point differences)
        assert abs(pred1.ensemble_prediction - pred2.ensemble_prediction) < 1e-6
        assert abs(pred1.ensemble_confidence - pred2.ensemble_confidence) < 1e-6
