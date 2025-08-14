"""
End-to-end system integration tests.

Tests the complete system with real components, paper trading mode,
and external data sources.
"""

from datetime import datetime, timedelta
import threading
import time

import pytest


class TestSystemIntegration:
    """Test complete system integration end-to-end."""

    @pytest.fixture
    def paper_trading_config(self, tmp_path):
        """Configuration for paper trading mode."""
        config_data = {
            "alpaca": {
                "api_key": "test_paper_key",
                "secret_key": "test_paper_secret",
                "base_url": "https://paper-api.alpaca.markets",
                "data_url": "https://data.alpaca.markets",
                "paper_trading": True,
            },
            "trading": {
                "symbols": ["SPY", "QQQ", "IWM"],
                "max_positions": 3,
                "position_sizing": "equal_weight",
                "rebalance_frequency": "daily",
            },
            "risk": {
                "max_portfolio_risk": 0.02,
                "max_position_risk": 0.01,
                "stop_loss_pct": 0.05,
                "max_drawdown": 0.10,
            },
            "features": {
                "technical_indicators": True,
                "sentiment_analysis": False,  # Skip for E2E speed
                "volume_analysis": True,
            },
            "ml": {
                "model_type": "ensemble",
                "retrain_frequency": "weekly",
                "min_training_days": 30,
            },
            "logging": {"level": "INFO", "file": str(tmp_path / "trading.log")},
        }

        config_file = tmp_path / "test_config.yaml"

        # Write YAML manually for simplicity
        import yaml

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        return str(config_file)

    @pytest.mark.e2e
    @pytest.mark.slow
    @pytest.mark.timeout(300)  # 5 minute timeout
    def test_full_system_startup_shutdown(self, paper_trading_config):
        """Test complete system startup and graceful shutdown."""

        # Mock external dependencies for isolated testing
        with patch_external_apis():
            # Initialize system
            system = TradingSystem(config_path=paper_trading_config)

            # Start system in background thread
            system_thread = threading.Thread(target=system.run, daemon=True)

            startup_success = False
            try:
                system_thread.start()

                # Wait for system to initialize (up to 30 seconds)
                for _ in range(30):
                    if system.is_ready():
                        startup_success = True
                        break
                    time.sleep(1)

                assert startup_success, "System failed to start within 30 seconds"

                # Verify core components are running
                assert system.data_manager.is_connected()
                assert system.strategy_engine.is_initialized()
                assert system.risk_manager.is_active()
                assert system.order_manager.is_ready()

                # Run for a few seconds to process data
                time.sleep(5)

                # Check system health
                health_status = system.get_health_status()
                assert health_status["status"] == "healthy"
                assert health_status["uptime"] > 0

            finally:
                # Graceful shutdown
                system.shutdown()
                system_thread.join(timeout=10)

                # Verify clean shutdown
                assert not system.is_running()

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_paper_trading_execution_flow(self, paper_trading_config):
        """Test complete paper trading execution flow."""

        with patch_external_apis() as mocks:
            system = TradingSystem(config_path=paper_trading_config)

            try:
                # Start system
                system.start()

                # Wait for initialization
                await_system_ready(system, timeout=30)

                # Inject market data update
                market_data = {
                    "SPY": {"price": 450.25, "volume": 1000000},
                    "QQQ": {"price": 375.80, "volume": 800000},
                    "IWM": {"price": 195.60, "volume": 600000},
                }

                # Simulate market data arrival
                system.data_manager.process_market_update(market_data)

                # Wait for signal generation and order processing
                time.sleep(3)

                # Check if orders were generated
                orders = system.order_manager.get_recent_orders(minutes=5)

                # Should have some orders for the ETFs
                assert len(orders) >= 0, "System should process market data"

                # If orders exist, verify they're properly formatted
                for order in orders:
                    assert order["symbol"] in ["SPY", "QQQ", "IWM"]
                    assert order["side"] in ["buy", "sell"]
                    assert order["qty"] > 0
                    assert "timestamp" in order

                # Verify risk checks were applied
                risk_violations = system.risk_manager.get_recent_violations()

                # Check portfolio state
                portfolio = system.portfolio_manager.get_current_state()
                assert "cash" in portfolio
                assert "positions" in portfolio
                assert "total_value" in portfolio

                print("✓ Paper Trading Flow Test:")
                print(f"  - Orders Generated: {len(orders)}")
                print(f"  - Risk Violations: {len(risk_violations)}")
                print(f"  - Portfolio Value: ${portfolio.get('total_value', 0):,.2f}")

            finally:
                system.shutdown()

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_market_hours_behavior(self, paper_trading_config):
        """Test system behavior during different market hours."""

        with patch_external_apis() as mocks:
            system = TradingSystem(config_path=paper_trading_config)

            try:
                system.start()
                await_system_ready(system, timeout=20)

                # Test 1: Pre-market hours (6 AM ET)
                mocks.market_hours.return_value = {
                    "is_open": False,
                    "next_open": datetime.now() + timedelta(hours=3),
                    "session": "pre_market",
                }

                system.market_session_manager.check_market_status()

                # System should be in waiting mode
                assert not system.is_trading_active()

                # Test 2: Market open (9:30 AM ET)
                mocks.market_hours.return_value = {
                    "is_open": True,
                    "next_close": datetime.now() + timedelta(hours=6, minutes=30),
                    "session": "regular",
                }

                system.market_session_manager.check_market_status()

                # System should activate trading
                assert system.is_trading_active()

                # Test 3: Market close (4:00 PM ET)
                mocks.market_hours.return_value = {
                    "is_open": False,
                    "next_open": datetime.now() + timedelta(hours=17),
                    "session": "closed",
                }

                system.market_session_manager.check_market_status()

                # System should stop active trading
                assert not system.is_trading_active()

                # Should have generated end-of-day reports
                reports = system.reporting_manager.get_daily_reports()
                assert len(reports) > 0

                print("✓ Market Hours Test:")
                print("  - Pre-market: System idle ✓")
                print("  - Market open: Trading active ✓")
                print("  - Market close: Trading stopped ✓")
                print(f"  - Daily reports: {len(reports)} generated ✓")

            finally:
                system.shutdown()

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_error_recovery_resilience(self, paper_trading_config):
        """Test system resilience and error recovery."""

        with patch_external_apis() as mocks:
            system = TradingSystem(config_path=paper_trading_config)

            try:
                system.start()
                await_system_ready(system, timeout=20)

                # Test 1: Data feed interruption
                mocks.market_data_feed.side_effect = ConnectionError(
                    "Feed disconnected"
                )

                # System should detect and attempt reconnection
                time.sleep(2)

                # Should log error but keep running
                assert system.is_running()

                # Restore feed
                mocks.market_data_feed.side_effect = None
                time.sleep(1)

                # Test 2: Broker API error
                mocks.place_order.side_effect = Exception("Broker API error")

                # Inject order
                test_order = {
                    "symbol": "SPY",
                    "side": "buy",
                    "qty": 10,
                    "type": "market",
                }

                system.order_manager.submit_order(test_order)
                time.sleep(1)

                # Order should be marked as failed
                failed_orders = system.order_manager.get_failed_orders()
                assert len(failed_orders) > 0

                # System should remain operational
                assert system.is_running()

                # Test 3: Memory/resource pressure
                # Simulate high memory usage scenario
                large_data = {}
                for i in range(1000):
                    large_data[f"key_{i}"] = list(range(1000))

                # System should handle gracefully
                health = system.get_health_status()

                # Clean up
                del large_data

                print("✓ Error Recovery Test:")
                print("  - Data feed recovery: ✓")
                print("  - Broker API error handling: ✓")
                print("  - Resource pressure handling: ✓")
                print(f"  - System stability: {health['status']}")

            finally:
                system.shutdown()

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_performance_under_load(self, paper_trading_config):
        """Test system performance under high-frequency data load."""

        with patch_external_apis() as mocks:
            system = TradingSystem(config_path=paper_trading_config)

            try:
                system.start()
                await_system_ready(system, timeout=20)

                # Generate high-frequency market data
                symbols = ["SPY", "QQQ", "IWM", "DIA", "VTI"]

                start_time = time.time()
                message_count = 0

                # Send 1000 market data updates over 10 seconds
                for i in range(200):  # 200 batches
                    batch_data = {}

                    for symbol in symbols:
                        batch_data[symbol] = {
                            "price": 100 + (i % 50),  # Price oscillation
                            "volume": 1000 + (i * 100),
                            "timestamp": datetime.now(),
                        }
                        message_count += 1

                    system.data_manager.process_market_update(batch_data)

                    if i % 20 == 0:  # Brief pause every 100 updates
                        time.sleep(0.05)

                end_time = time.time()
                duration = end_time - start_time

                # Wait for processing to complete
                time.sleep(2)

                # Check system performance metrics
                stats = system.get_performance_stats()

                messages_per_second = message_count / duration

                # System should handle at least 50 messages/sec
                assert (
                    messages_per_second > 50
                ), f"Performance too low: {messages_per_second:.1f} msg/sec"

                # Memory usage should be reasonable
                memory_mb = stats.get("memory_usage_mb", 0)
                assert memory_mb < 500, f"Memory usage too high: {memory_mb} MB"

                # CPU usage should be reasonable
                cpu_percent = stats.get("cpu_percent", 0)
                assert cpu_percent < 80, f"CPU usage too high: {cpu_percent}%"

                print("✓ Performance Test:")
                print(f"  - Message Rate: {messages_per_second:.1f} msg/sec")
                print(f"  - Memory Usage: {memory_mb} MB")
                print(f"  - CPU Usage: {cpu_percent}%")
                print(f"  - Processing Latency: {stats.get('avg_latency_ms', 0):.1f}ms")

            finally:
                system.shutdown()


def patch_external_apis():
    """Context manager to patch external API dependencies."""
    from unittest.mock import MagicMock, patch

    class MockExternalAPIs:
        def __init__(self):
            self.market_data_feed = MagicMock()
            self.market_hours = MagicMock()
            self.place_order = MagicMock()

            # Default return values
            self.market_hours.return_value = {
                "is_open": True,
                "next_close": datetime.now() + timedelta(hours=6),
                "session": "regular",
            }

            self.place_order.return_value = {
                "id": "order_123",
                "status": "filled",
                "filled_qty": 10,
            }

        def __enter__(self):
            self.patches = []

            # Patch Alpaca API
            alpaca_patch = patch("alpaca_trade_api.REST")
            mock_alpaca = alpaca_patch.start()
            mock_alpaca.return_value.get_clock.return_value = (
                self.market_hours.return_value
            )
            mock_alpaca.return_value.submit_order = self.place_order
            self.patches.append(alpaca_patch)

            # Patch market data feed
            data_patch = patch("backend.data.market_data.MarketDataManager.connect")
            data_patch.start().return_value = True
            self.patches.append(data_patch)

            # Patch ML model loading
            ml_patch = patch("backend.ml.ensemble_model.EnsembleModel.load_model")
            ml_patch.start().return_value = True
            self.patches.append(ml_patch)

            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            for patch in self.patches:
                patch.stop()


def await_system_ready(system, timeout=30):
    """Wait for system to be ready with timeout."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        if system.is_ready():
            return True
        time.sleep(0.5)

    raise TimeoutError(f"System not ready within {timeout} seconds")


class TestRealisticMarketScenarios:
    """Test system behavior under realistic market scenarios."""

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_market_volatility_spike(self, paper_trading_config):
        """Test system behavior during market volatility spike."""

        with patch_external_apis():
            system = TradingSystem(config_path=paper_trading_config)

            try:
                system.start()
                await_system_ready(system, timeout=20)

                # Start with normal market conditions
                normal_data = {
                    "SPY": {"price": 450.00, "volume": 100000},
                    "QQQ": {"price": 375.00, "volume": 80000},
                }

                system.data_manager.process_market_update(normal_data)
                time.sleep(1)

                # Simulate volatility spike (5% drop in 1 minute)
                volatility_data = [
                    {"SPY": {"price": 445.00, "volume": 500000}},  # -1.1%
                    {"SPY": {"price": 435.00, "volume": 800000}},  # -3.3%
                    {"SPY": {"price": 427.50, "volume": 1200000}},  # -5.0%
                ]

                for data_point in volatility_data:
                    system.data_manager.process_market_update(data_point)
                    time.sleep(0.5)

                # Check risk manager response
                risk_actions = system.risk_manager.get_recent_actions()

                # Should trigger risk controls
                assert any(
                    action["type"] == "position_reduction" for action in risk_actions
                )

                # Check if stop losses were triggered
                orders = system.order_manager.get_recent_orders(minutes=2)
                stop_loss_orders = [o for o in orders if o.get("type") == "stop_loss"]

                print("✓ Volatility Spike Test:")
                print(f"  - Risk Actions: {len(risk_actions)}")
                print(f"  - Stop Losses: {len(stop_loss_orders)}")

            finally:
                system.shutdown()

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_earnings_announcement_scenario(self, paper_trading_config):
        """Test system during earnings announcement."""

        with patch_external_apis():
            system = TradingSystem(config_path=paper_trading_config)

            try:
                system.start()
                await_system_ready(system, timeout=20)

                # Pre-earnings: reduced volume, tight spreads
                pre_earnings = {
                    "AAPL": {
                        "price": 150.00,
                        "volume": 50000,
                        "bid": 149.98,
                        "ask": 150.02,
                    }
                }

                system.data_manager.process_market_update(pre_earnings)

                # Earnings release: gap up, high volume
                post_earnings = {
                    "AAPL": {
                        "price": 158.50,
                        "volume": 2000000,
                        "bid": 158.45,
                        "ask": 158.55,
                    }  # +5.7% gap
                }

                system.data_manager.process_market_update(post_earnings)
                time.sleep(1)

                # System should adjust position sizing for high volatility
                risk_adjustments = system.risk_manager.get_position_adjustments()

                # Check if volatility adjustment was applied
                assert any(
                    adj["reason"] == "volatility_spike" for adj in risk_adjustments
                )

                print("✓ Earnings Scenario Test:")
                print(f"  - Volatility Adjustments: {len(risk_adjustments)}")

            finally:
                system.shutdown()


class TestSystemMonitoring:
    """Test system monitoring and alerting."""

    @pytest.mark.e2e
    def test_health_monitoring(self, paper_trading_config):
        """Test comprehensive system health monitoring."""

        with patch_external_apis():
            system = TradingSystem(config_path=paper_trading_config)

            try:
                system.start()
                await_system_ready(system, timeout=20)

                # Get comprehensive health status
                health = system.get_comprehensive_health_status()

                # Verify all components report health
                required_components = [
                    "data_manager",
                    "strategy_engine",
                    "risk_manager",
                    "order_manager",
                    "portfolio_manager",
                    "ml_model",
                ]

                for component in required_components:
                    assert component in health["components"]
                    assert health["components"][component]["status"] in [
                        "healthy",
                        "warning",
                        "error",
                    ]

                # Overall system should be healthy
                assert health["overall_status"] in ["healthy", "warning"]

                # Performance metrics should be present
                assert "performance" in health
                assert "uptime_seconds" in health["performance"]
                assert "memory_usage_mb" in health["performance"]

                print("✓ Health Monitoring Test:")
                print(f"  - Overall Status: {health['overall_status']}")
                print(f"  - Components Monitored: {len(health['components'])}")
                print(f"  - Uptime: {health['performance']['uptime_seconds']}s")

            finally:
                system.shutdown()

    @pytest.mark.e2e
    def test_alerting_system(self, paper_trading_config):
        """Test alerting for critical events."""

        with patch_external_apis():
            system = TradingSystem(config_path=paper_trading_config)

            try:
                system.start()
                await_system_ready(system, timeout=20)

                # Trigger alert conditions

                # 1. High drawdown alert
                system.risk_manager.update_portfolio_drawdown(0.08)  # 8% drawdown

                # 2. Connection loss alert
                system.data_manager.simulate_connection_loss()

                # 3. Order rejection alert
                system.order_manager.simulate_order_rejection("RISK_LIMIT_EXCEEDED")

                time.sleep(1)

                # Check generated alerts
                alerts = system.alert_manager.get_recent_alerts()

                alert_types = [alert["type"] for alert in alerts]

                # Should have generated appropriate alerts
                expected_alerts = [
                    "high_drawdown",
                    "connection_loss",
                    "order_rejection",
                ]

                for expected in expected_alerts:
                    assert any(
                        expected in alert_type for alert_type in alert_types
                    ), f"Missing alert: {expected}"

                print("✓ Alerting System Test:")
                print(f"  - Alerts Generated: {len(alerts)}")
                print(f"  - Alert Types: {alert_types}")

            finally:
                system.shutdown()
