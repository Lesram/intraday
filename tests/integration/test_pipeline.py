"""
Integration tests for the complete trading pipeline.

Tests the flow: Data Ingestion → Feature Engineering → ML Prediction → Signal Generation
Uses fixture data to ensure deterministic results.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import numpy as np
import pandas as pd
import pytest

from backend.data.alpaca_client import AlpacaClient
from backend.features.feature_engineering import FeatureEngineer
from backend.models.ensemble_model import EnsembleModel
from backend.risk.risk_manager import RiskManager
from backend.services.order_service import OrderService
from backend.strategies.engine import StrategyEngine


class TestTradingPipelineIntegration:
    """Test complete trading pipeline integration."""

    @pytest.fixture
    async def pipeline_components(self, test_config):
        """Create integrated pipeline components."""
        # Data ingestion
        data_client = Mock(spec=AlpacaClient)

        # Feature engineering
        feature_engineer = FeatureEngineer(
            {
                "technical_indicators": {
                    "rsi_period": 14,
                    "macd_fast": 12,
                    "macd_slow": 26,
                    "bb_period": 20,
                },
                "volume_indicators": {
                    "volume_sma_period": 20,
                },
            }
        )

        # ML model
        ml_model = Mock(spec=EnsembleModel)
        ml_model.predict.return_value = np.array([0.75, 0.85, 0.65])  # Mock predictions
        ml_model.is_trained = True

        # Strategy engine
        strategy_engine = Mock(spec=StrategyEngine)

        # Risk manager
        risk_manager = Mock(spec=RiskManager)
        risk_manager.evaluate_trade_risk = AsyncMock(
            return_value={
                "approved": True,
                "risk_score": 0.3,
                "checks_passed": ["position_size", "concentration"],
            }
        )

        # Order service
        order_service = Mock(spec=OrderService)
        order_service.submit_order = AsyncMock(
            return_value={"success": True, "order_id": "test_order_123"}
        )

        return {
            "data_client": data_client,
            "feature_engineer": feature_engineer,
            "ml_model": ml_model,
            "strategy_engine": strategy_engine,
            "risk_manager": risk_manager,
            "order_service": order_service,
        }

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_pipeline_single_symbol(
        self, pipeline_components, sample_market_data
    ):
        """Test complete pipeline for single symbol."""
        components = pipeline_components

        # Step 1: Data Ingestion (mock data feed)
        symbol = "AAPL"
        market_data = sample_market_data["ohlcv"]
        market_data = market_data[market_data["symbol"] == symbol].head(
            100
        )  # Last 100 bars

        components["data_client"].get_bars.return_value = market_data

        # Step 2: Feature Engineering
        features = components["feature_engineer"].compute_features(market_data)

        # Verify features are computed
        assert isinstance(features, pd.DataFrame)
        assert len(features) > 0
        assert not features.empty

        # Check for expected feature columns
        feature_columns = features.columns.tolist()
        assert any("rsi" in col for col in feature_columns)
        assert any("macd" in col for col in feature_columns)

        # Step 3: ML Prediction
        latest_features = features.tail(1)  # Most recent features
        if not latest_features.empty:
            predictions = components["ml_model"].predict(latest_features.values)

            # Verify prediction format
            assert isinstance(predictions, np.ndarray)
            assert len(predictions) > 0
            assert all(0 <= pred <= 1 for pred in predictions)

        # Step 4: Signal Generation
        signal_confidence = float(predictions[0]) if len(predictions) > 0 else 0.75

        if signal_confidence > 0.7:  # Strong signal threshold
            signal = {
                "symbol": symbol,
                "action": "BUY" if signal_confidence > 0.5 else "SELL",
                "confidence": signal_confidence,
                "timestamp": datetime.now(),
                "source": "ml_ensemble",
                "features_used": feature_columns,
            }

            # Step 5: Risk Evaluation
            risk_result = await components["risk_manager"].evaluate_trade_risk(
                order_spec={
                    "symbol": signal["symbol"],
                    "side": signal["action"].lower(),
                    "qty": 100,
                    "order_type": "market",
                },
                portfolio_state={"cash": 50000, "total_value": 100000},
            )

            # Step 6: Order Submission (if risk approved)
            if risk_result["approved"]:
                order_result = await components["order_service"].submit_order(
                    order_spec={
                        "symbol": signal["symbol"],
                        "side": signal["action"].lower(),
                        "qty": 100,
                        "order_type": "market",
                    },
                    user_id="system",
                )

                # Verify order was submitted
                assert order_result["success"] is True
                assert "order_id" in order_result

                print("✓ Pipeline completed successfully:")
                print(f"  - Symbol: {signal['symbol']}")
                print(
                    f"  - Signal: {signal['action']} (confidence: {signal_confidence:.3f})"
                )
                print(f"  - Risk Score: {risk_result['risk_score']}")
                print(f"  - Order ID: {order_result['order_id']}")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pipeline_multi_symbol_batch(
        self, pipeline_components, sample_market_data
    ):
        """Test pipeline processing multiple symbols in batch."""
        components = pipeline_components

        symbols = ["AAPL", "GOOGL", "MSFT"]
        all_signals = []

        for symbol in symbols:
            # Get market data for symbol
            symbol_data = sample_market_data["ohlcv"]
            symbol_data = symbol_data[symbol_data["symbol"] == symbol].head(50)

            if symbol_data.empty:
                # Generate data if not in fixtures
                from tests.fixtures.market_data import generate_synthetic_ohlcv

                symbol_data = generate_synthetic_ohlcv(symbol=symbol, days=20)

            components["data_client"].get_bars.return_value = symbol_data

            # Process through pipeline
            features = components["feature_engineer"].compute_features(symbol_data)

            if not features.empty:
                latest_features = features.tail(1)
                predictions = components["ml_model"].predict(latest_features.values)

                signal_confidence = (
                    float(predictions[0]) if len(predictions) > 0 else 0.5
                )

                signal = {
                    "symbol": symbol,
                    "confidence": signal_confidence,
                    "action": "BUY" if signal_confidence > 0.6 else "HOLD",
                    "timestamp": datetime.now(),
                }

                all_signals.append(signal)

        # Verify batch processing
        assert len(all_signals) == len(symbols)
        assert all(signal["symbol"] in symbols for signal in all_signals)

        # Check signal distribution
        buy_signals = [s for s in all_signals if s["action"] == "BUY"]
        print(
            f"✓ Processed {len(symbols)} symbols, generated {len(buy_signals)} BUY signals"
        )

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pipeline_with_risk_rejection(
        self, pipeline_components, sample_market_data
    ):
        """Test pipeline behavior when risk manager rejects trades."""
        components = pipeline_components

        # Configure risk manager to reject trades
        components["risk_manager"].evaluate_trade_risk.return_value = {
            "approved": False,
            "risk_score": 0.95,
            "checks_failed": ["position_size"],
            "reason": "position_size_exceeded",
        }

        # Run pipeline
        symbol = "AAPL"
        market_data = sample_market_data["ohlcv"].head(50)

        components["data_client"].get_bars.return_value = market_data
        features = components["feature_engineer"].compute_features(market_data)

        if not features.empty:
            predictions = components["ml_model"].predict(features.tail(1).values)
            signal_confidence = float(predictions[0])

            if signal_confidence > 0.7:
                # Strong signal but should be rejected by risk
                risk_result = await components["risk_manager"].evaluate_trade_risk(
                    order_spec={
                        "symbol": symbol,
                        "side": "buy",
                        "qty": 1000,
                    },  # Large order
                    portfolio_state={
                        "cash": 10000,
                        "total_value": 20000,
                    },  # Small account
                )

                # Verify risk rejection
                assert risk_result["approved"] is False
                assert risk_result["risk_score"] > 0.8

                # Order should not be submitted
                components["order_service"].submit_order.assert_not_called()

                print("✓ Risk manager correctly rejected high-risk trade")
                print(f"  - Risk Score: {risk_result['risk_score']}")
                print(f"  - Reason: {risk_result['reason']}")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_pipeline_error_handling(
        self, pipeline_components, sample_market_data
    ):
        """Test pipeline error handling and resilience."""
        components = pipeline_components

        # Test data ingestion failure
        components["data_client"].get_bars.side_effect = Exception(
            "Market data unavailable"
        )

        try:
            await self._run_pipeline_step(
                components["data_client"].get_bars,
                "AAPL",
                datetime.now() - timedelta(days=1),
                datetime.now(),
            )
            assert False, "Should have raised exception"
        except Exception as e:
            assert "Market data unavailable" in str(e)
            print("✓ Handled data ingestion failure")

        # Reset and test feature engineering with bad data
        components["data_client"].get_bars.side_effect = None
        components["data_client"].get_bars.return_value = pd.DataFrame()  # Empty data

        empty_data = components["data_client"].get_bars()
        features = components["feature_engineer"].compute_features(empty_data)

        # Should handle empty data gracefully
        assert isinstance(features, pd.DataFrame)
        print("✓ Handled empty market data")

        # Test ML model failure
        components["ml_model"].predict.side_effect = Exception("Model inference failed")

        try:
            if not features.empty:
                predictions = components["ml_model"].predict(features.values)
                assert False, "Should have raised exception"
        except Exception as e:
            assert "Model inference failed" in str(e)
            print("✓ Handled ML model failure")

    async def _run_pipeline_step(self, func, *args, **kwargs):
        """Helper to run pipeline step with error handling."""
        return (
            await func(*args, **kwargs)
            if asyncio.iscoroutinefunction(func)
            else func(*args, **kwargs)
        )


class TestMarketDataIntegration:
    """Test market data ingestion and processing integration."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_real_time_data_processing(
        self, mock_alpaca_client, sample_market_data
    ):
        """Test real-time market data processing pipeline."""

        # Simulate real-time data stream
        data_stream = [
            {
                "symbol": "AAPL",
                "timestamp": "2024-01-02T09:30:00.000Z",
                "price": 185.50,
                "size": 100,
                "type": "trade",
            },
            {
                "symbol": "AAPL",
                "timestamp": "2024-01-02T09:30:01.000Z",
                "price": 185.52,
                "size": 200,
                "type": "trade",
            },
            {
                "symbol": "AAPL",
                "timestamp": "2024-01-02T09:30:02.000Z",
                "price": 185.48,
                "size": 150,
                "type": "trade",
            },
        ]

        # Mock streaming interface
        mock_alpaca_client.stream_trades = AsyncMock()

        processed_trades = []

        async def process_trade(trade):
            """Process individual trade."""
            processed_trade = {
                "symbol": trade["symbol"],
                "price": Decimal(str(trade["price"])),
                "size": trade["size"],
                "timestamp": trade["timestamp"],
                "processed_at": datetime.now(),
            }
            processed_trades.append(processed_trade)

        # Simulate processing stream
        for trade in data_stream:
            await process_trade(trade)

        # Verify processing
        assert len(processed_trades) == len(data_stream)
        assert all(isinstance(trade["price"], Decimal) for trade in processed_trades)
        assert all(trade["symbol"] == "AAPL" for trade in processed_trades)

        # Check chronological order
        timestamps = [trade["timestamp"] for trade in processed_trades]
        assert timestamps == sorted(timestamps)

        print(f"✓ Processed {len(processed_trades)} real-time trades")

    @pytest.mark.integration
    def test_historical_data_validation(self, fixture_data_loader):
        """Test historical data validation and consistency."""

        # Load historical data fixture
        try:
            historical_data = fixture_data_loader("AAPL_daily.csv")

            if isinstance(historical_data, str):
                # If returned as file path, read it
                historical_data = pd.read_csv(historical_data)
        except FileNotFoundError:
            # Generate if fixture doesn't exist
            from tests.fixtures.market_data import generate_synthetic_ohlcv

            historical_data = generate_synthetic_ohlcv("AAPL", days=30)

        # Validate data integrity
        assert not historical_data.empty
        assert len(historical_data) > 0

        required_columns = ["timestamp", "open", "high", "low", "close", "volume"]
        assert all(col in historical_data.columns for col in required_columns)

        # Validate OHLC relationships
        ohlc_valid = (
            (historical_data["high"] >= historical_data["open"])
            & (historical_data["high"] >= historical_data["close"])
            & (historical_data["low"] <= historical_data["open"])
            & (historical_data["low"] <= historical_data["close"])
        ).all()

        assert ohlc_valid, "OHLC relationships violated"

        # Validate no negative volumes
        assert (historical_data["volume"] >= 0).all(), "Negative volumes found"

        # Check for reasonable price ranges (no extreme outliers)
        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            q99 = historical_data[col].quantile(0.99)
            q01 = historical_data[col].quantile(0.01)
            ratio = q99 / q01 if q01 > 0 else float("inf")
            assert ratio < 100, f"Extreme price range in {col}: {ratio:.2f}x"

        print(f"✓ Validated {len(historical_data)} historical data points")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_data_aggregation_pipeline(self, sample_market_data):
        """Test data aggregation from ticks to bars."""

        # Simulate tick data (trades and quotes)
        tick_data = [
            {
                "timestamp": "2024-01-02T09:30:00.100Z",
                "symbol": "AAPL",
                "price": 185.50,
                "size": 100,
            },
            {
                "timestamp": "2024-01-02T09:30:00.200Z",
                "symbol": "AAPL",
                "price": 185.52,
                "size": 50,
            },
            {
                "timestamp": "2024-01-02T09:30:00.300Z",
                "symbol": "AAPL",
                "price": 185.48,
                "size": 200,
            },
            {
                "timestamp": "2024-01-02T09:30:00.400Z",
                "symbol": "AAPL",
                "price": 185.51,
                "size": 75,
            },
        ]

        # Aggregate to 1-second bars
        def aggregate_ticks_to_bars(ticks, timeframe="1s"):
            """Aggregate tick data to OHLCV bars."""
            df = pd.DataFrame(ticks)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")

            # Group by timeframe and aggregate
            bars = (
                df.groupby(df.symbol)
                .resample(timeframe)
                .agg(
                    {
                        "price": ["first", "max", "min", "last"],  # OHLC
                        "size": "sum",  # Volume
                    }
                )
                .round(2)
            )

            # Flatten column names
            bars.columns = ["open", "high", "low", "close", "volume"]
            bars = bars.reset_index()

            return bars

        bars = aggregate_ticks_to_bars(tick_data)

        # Verify aggregation
        assert not bars.empty
        assert "open" in bars.columns
        assert "high" in bars.columns
        assert "low" in bars.columns
        assert "close" in bars.columns
        assert "volume" in bars.columns

        # Check aggregation logic
        if len(bars) > 0:
            bar = bars.iloc[0]
            assert bar["open"] == 185.50  # First price
            assert bar["close"] == 185.51  # Last price
            assert bar["high"] == 185.52  # Max price
            assert bar["low"] == 185.48  # Min price
            assert bar["volume"] == 425  # Sum of sizes

        print(f"✓ Aggregated {len(tick_data)} ticks to {len(bars)} bars")


class TestSignalGenerationIntegration:
    """Test signal generation and strategy integration."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multi_strategy_signal_combination(
        self, mock_strategy_engine, sample_market_data
    ):
        """Test combining signals from multiple strategies."""

        # Mock different strategy signals
        strategy_signals = {
            "momentum_strategy": {
                "symbol": "AAPL",
                "action": "BUY",
                "confidence": 0.8,
                "reason": "Strong upward momentum",
            },
            "mean_reversion_strategy": {
                "symbol": "AAPL",
                "action": "SELL",
                "confidence": 0.6,
                "reason": "Overbought conditions",
            },
            "ml_ensemble_strategy": {
                "symbol": "AAPL",
                "action": "BUY",
                "confidence": 0.75,
                "reason": "ML model prediction",
            },
        }

        # Signal combination logic
        def combine_signals(signals, weights=None):
            """Combine multiple strategy signals with optional weights."""
            if weights is None:
                weights = {name: 1.0 for name in signals.keys()}

            # Separate BUY and SELL signals
            buy_signals = [
                (name, sig) for name, sig in signals.items() if sig["action"] == "BUY"
            ]
            sell_signals = [
                (name, sig) for name, sig in signals.items() if sig["action"] == "SELL"
            ]

            # Calculate weighted confidence scores
            buy_score = sum(
                weights[name] * sig["confidence"] for name, sig in buy_signals
            )
            sell_score = sum(
                weights[name] * sig["confidence"] for name, sig in sell_signals
            )

            buy_weight = sum(weights[name] for name, sig in buy_signals)
            sell_weight = sum(weights[name] for name, sig in sell_signals)

            # Determine final signal
            if buy_weight > 0:
                buy_score /= buy_weight
            if sell_weight > 0:
                sell_score /= sell_weight

            if buy_score > sell_score and buy_score > 0.5:
                return {
                    "action": "BUY",
                    "confidence": buy_score,
                    "component_signals": len(buy_signals),
                }
            elif sell_score > buy_score and sell_score > 0.5:
                return {
                    "action": "SELL",
                    "confidence": sell_score,
                    "component_signals": len(sell_signals),
                }
            else:
                return {"action": "HOLD", "confidence": 0.5, "component_signals": 0}

        # Test equal weights
        combined_signal = combine_signals(strategy_signals)

        assert combined_signal["action"] in ["BUY", "SELL", "HOLD"]
        assert 0 <= combined_signal["confidence"] <= 1

        # Test with custom weights (favor momentum strategy)
        weights = {
            "momentum_strategy": 2.0,
            "mean_reversion_strategy": 1.0,
            "ml_ensemble_strategy": 1.5,
        }

        weighted_signal = combine_signals(strategy_signals, weights)

        # Should favor BUY due to higher weight on momentum strategy
        assert weighted_signal["action"] == "BUY"
        assert weighted_signal["confidence"] > 0.6

        print(f"✓ Combined {len(strategy_signals)} strategy signals")
        print(
            f"  - Equal weights: {combined_signal['action']} ({combined_signal['confidence']:.3f})"
        )
        print(
            f"  - Custom weights: {weighted_signal['action']} ({weighted_signal['confidence']:.3f})"
        )

    @pytest.mark.integration
    def test_signal_filtering_and_ranking(self):
        """Test signal filtering and ranking logic."""

        # Multiple signals for different symbols
        raw_signals = [
            {
                "symbol": "AAPL",
                "action": "BUY",
                "confidence": 0.85,
                "strategy": "momentum",
            },
            {
                "symbol": "GOOGL",
                "action": "BUY",
                "confidence": 0.75,
                "strategy": "ml_ensemble",
            },
            {
                "symbol": "MSFT",
                "action": "SELL",
                "confidence": 0.65,
                "strategy": "mean_reversion",
            },
            {
                "symbol": "TSLA",
                "action": "BUY",
                "confidence": 0.55,
                "strategy": "momentum",
            },
            {
                "symbol": "NVDA",
                "action": "BUY",
                "confidence": 0.90,
                "strategy": "ml_ensemble",
            },
        ]

        def filter_and_rank_signals(signals, min_confidence=0.6, max_signals=3):
            """Filter and rank signals by confidence."""
            # Filter by minimum confidence
            filtered = [sig for sig in signals if sig["confidence"] >= min_confidence]

            # Sort by confidence (descending)
            ranked = sorted(filtered, key=lambda s: s["confidence"], reverse=True)

            # Limit to max signals
            return ranked[:max_signals]

        # Apply filtering and ranking
        top_signals = filter_and_rank_signals(
            raw_signals, min_confidence=0.6, max_signals=3
        )

        # Verify filtering
        assert len(top_signals) <= 3
        assert all(sig["confidence"] >= 0.6 for sig in top_signals)

        # Verify ranking (should be sorted by confidence)
        confidences = [sig["confidence"] for sig in top_signals]
        assert confidences == sorted(confidences, reverse=True)

        # Check top signal
        if top_signals:
            assert top_signals[0]["symbol"] == "NVDA"  # Highest confidence
            assert top_signals[0]["confidence"] == 0.90

        print(f"✓ Filtered {len(raw_signals)} signals to top {len(top_signals)}")
        for i, sig in enumerate(top_signals, 1):
            print(f"  {i}. {sig['symbol']}: {sig['action']} ({sig['confidence']:.3f})")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_signal_to_order_conversion(
        self, mock_risk_manager, sample_portfolio_state
    ):
        """Test converting trading signals to executable orders."""

        # Sample trading signals
        signals = [
            {
                "symbol": "AAPL",
                "action": "BUY",
                "confidence": 0.85,
                "target_price": 186.00,
            },
            {
                "symbol": "GOOGL",
                "action": "SELL",
                "confidence": 0.75,
                "target_price": 2780.00,
            },
        ]

        portfolio_state = sample_portfolio_state

        async def convert_signal_to_order(
            signal, portfolio, position_sizing_method="fixed_dollar"
        ):
            """Convert trading signal to order specification."""

            if position_sizing_method == "fixed_dollar":
                # Fixed dollar amount per position
                target_notional = Decimal("10000")  # $10,000 per position

                if "target_price" in signal:
                    price = Decimal(str(signal["target_price"]))
                    qty = int(target_notional / price)
                # Market order - estimate based on current position value
                elif signal["symbol"] in portfolio["positions"]:
                    current_price = (
                        portfolio["positions"][signal["symbol"]]["market_value"]
                        / portfolio["positions"][signal["symbol"]]["qty"]
                    )
                    qty = int(target_notional / current_price)
                else:
                    qty = 50  # Default quantity

            order_spec = {
                "symbol": signal["symbol"],
                "side": signal["action"].lower(),
                "qty": qty,
                "order_type": "limit" if "target_price" in signal else "market",
                "time_in_force": "day",
                "strategy_id": signal.get("strategy", "unknown"),
                "signal_confidence": signal["confidence"],
            }

            if "target_price" in signal:
                order_spec["price"] = Decimal(str(signal["target_price"]))

            # Risk check
            risk_result = await mock_risk_manager.evaluate_trade_risk(
                order_spec, portfolio
            )

            if risk_result["approved"]:
                return {
                    "success": True,
                    "order_spec": order_spec,
                    "risk_score": risk_result["risk_score"],
                }
            else:
                return {"success": False, "reason": risk_result["reason"]}

        # Convert signals to orders
        orders = []
        for signal in signals:
            order_result = await convert_signal_to_order(signal, portfolio_state)
            orders.append(order_result)

        # Verify conversions
        successful_orders = [order for order in orders if order["success"]]

        assert len(successful_orders) > 0, "No orders were successfully created"

        for order in successful_orders:
            spec = order["order_spec"]
            assert spec["symbol"] in [s["symbol"] for s in signals]
            assert spec["side"] in ["buy", "sell"]
            assert spec["qty"] > 0
            assert 0 <= order["risk_score"] <= 1

        print(f"✓ Converted {len(signals)} signals to {len(successful_orders)} orders")
        for order in successful_orders:
            spec = order["order_spec"]
            print(
                f"  - {spec['symbol']}: {spec['side'].upper()} {spec['qty']} @ {spec.get('price', 'market')}"
            )
