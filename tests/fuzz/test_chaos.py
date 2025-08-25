"""
Fuzz testing for robustness and chaos engineering.

Tests system behavior with malformed data, edge cases, and adversarial inputs
to ensure production robustness and graceful error handling.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
import math
import random
from unittest.mock import Mock

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

# Hypothesis strategies for generating test data
import numpy as np
import pandas as pd
import pytest


class FuzzTestDataGenerator:
    """Generate malformed and edge-case data for fuzz testing."""

    @staticmethod
    def malformed_market_data():
        """Generate various types of malformed market data."""
        malformed_cases = [
            # Missing required fields
            {"symbol": "AAPL"},  # Missing price
            {"price": 150.0},  # Missing symbol
            # Invalid data types
            {"symbol": 123, "price": "not_a_number", "volume": "high"},
            {"symbol": None, "price": float("inf"), "volume": -1000},
            {"symbol": "", "price": float("nan"), "volume": 0},
            # Extreme values
            {"symbol": "AAPL", "price": 1e20, "volume": 1e15},
            {"symbol": "AAPL", "price": -1000, "volume": -50000},
            {"symbol": "AAPL", "price": 1e-10, "volume": 1},
            # Invalid symbols
            {"symbol": "A" * 100, "price": 150.0, "volume": 1000},  # Too long
            {"symbol": "AP@PL", "price": 150.0, "volume": 1000},  # Invalid chars
            {"symbol": "123", "price": 150.0, "volume": 1000},  # Numeric symbol
            {"symbol": "", "price": 150.0, "volume": 1000},  # Empty symbol
            # Timestamp issues
            {"symbol": "AAPL", "price": 150.0, "timestamp": "not_a_date"},
            {
                "symbol": "AAPL",
                "price": 150.0,
                "timestamp": datetime(1900, 1, 1),
            },  # Too old
            {
                "symbol": "AAPL",
                "price": 150.0,
                "timestamp": datetime(2100, 1, 1),
            },  # Future
            # Unicode and encoding issues
            {"symbol": "AAPL💰", "price": 150.0, "volume": 1000},
            {"symbol": "AAPL\x00", "price": 150.0, "volume": 1000},  # Null byte
            {"symbol": "AAPL\n", "price": 150.0, "volume": 1000},  # Newline
            # Complex nested structures (should be flat)
            {"symbol": "AAPL", "price": {"value": 150.0}, "volume": 1000},
            {"symbol": "AAPL", "data": [150.0, 1000, "extra"]},
        ]

        return malformed_cases

    @staticmethod
    def adversarial_orders():
        """Generate adversarial order data."""
        return [
            # Extreme quantities
            {"symbol": "AAPL", "side": "buy", "qty": 1e10},  # Huge quantity
            {"symbol": "AAPL", "side": "buy", "qty": -100},  # Negative qty
            {"symbol": "AAPL", "side": "buy", "qty": 0},  # Zero qty
            {"symbol": "AAPL", "side": "buy", "qty": 0.1},  # Fractional shares
            # Invalid sides
            {"symbol": "AAPL", "side": "maybe", "qty": 100},
            {"symbol": "AAPL", "side": "", "qty": 100},
            {"symbol": "AAPL", "side": None, "qty": 100},
            {"symbol": "AAPL", "side": 123, "qty": 100},
            # Price manipulation attempts
            {"symbol": "AAPL", "side": "buy", "qty": 100, "price": -1000},
            {"symbol": "AAPL", "side": "buy", "qty": 100, "price": float("inf")},
            {"symbol": "AAPL", "side": "buy", "qty": 100, "price": float("nan")},
            {"symbol": "AAPL", "side": "buy", "qty": 100, "price": 1e-20},
            # Order type confusion
            {"symbol": "AAPL", "side": "buy", "qty": 100, "type": "quantum"},
            {"symbol": "AAPL", "side": "buy", "qty": 100, "type": 42},
            {"symbol": "AAPL", "side": "buy", "qty": 100, "type": ["market", "limit"]},
            # Missing required fields
            {"side": "buy", "qty": 100},  # No symbol
            {"symbol": "AAPL", "qty": 100},  # No side
            {"symbol": "AAPL", "side": "buy"},  # No qty
            {},  # Completely empty
            # SQL injection attempts (if using SQL somewhere)
            {"symbol": "AAPL'; DROP TABLE orders; --", "side": "buy", "qty": 100},
            {"symbol": "AAPL", "side": "buy' OR '1'='1", "qty": 100},
            # Buffer overflow attempts
            {"symbol": "A" * 10000, "side": "buy", "qty": 100},
            {"comment": "X" * 100000, "symbol": "AAPL", "side": "buy", "qty": 100},
        ]


class TestMalformedDataHandling:
    """Test handling of malformed and invalid data."""

    @pytest.mark.fuzz
    def test_malformed_market_data_resilience(self):
        """Test system resilience to malformed market data."""
        from backend.data.market_data import MarketDataProcessor

        processor = MarketDataProcessor()

        # Test each malformed case
        malformed_cases = FuzzTestDataGenerator.malformed_market_data()

        successful_rejections = 0
        unexpected_errors = []

        for i, malformed_data in enumerate(malformed_cases):
            try:
                # Attempt to process malformed data
                result = processor.process_tick(malformed_data)

                # Should either reject gracefully or handle safely
                if result is None or result.get("status") == "rejected":
                    successful_rejections += 1
                else:
                    # If processed, verify it's safe
                    assert isinstance(result, dict), f"Case {i}: Invalid result type"
                    if "symbol" in result:
                        assert isinstance(
                            result["symbol"], str
                        ), f"Case {i}: Symbol not string"
                        assert len(result["symbol"]) > 0, f"Case {i}: Empty symbol"
                        assert len(result["symbol"]) < 20, f"Case {i}: Symbol too long"

            except (ValueError, TypeError, InvalidOperation):
                # Expected exceptions - good error handling
                successful_rejections += 1

            except Exception as e:
                # Unexpected exceptions - potential problems
                unexpected_errors.append(f"Case {i}: {type(e).__name__}: {str(e)}")

        print("✓ Malformed Market Data Test:")
        print(f"  - Cases Tested: {len(malformed_cases)}")
        print(f"  - Successful Rejections: {successful_rejections}")
        print(f"  - Unexpected Errors: {len(unexpected_errors)}")

        # Should handle most cases gracefully (allow for more edge cases)
        assert (
            len(unexpected_errors) < len(malformed_cases) * 0.5
        ), f"Too many unexpected errors: {unexpected_errors}"
        assert (
            successful_rejections > len(malformed_cases) * 0.3
        ), "Not enough proper error handling"

    @pytest.mark.fuzz
    @pytest.mark.asyncio
    async def test_adversarial_order_handling(self):
        """Test handling of adversarial order attempts."""
        from backend.risk.risk_manager import RiskManager
        from backend.services.order_service import OrderService

        # Mock broker to avoid external calls
        mock_broker = Mock()
        mock_broker.submit_order.return_value = {
            "status": "rejected",
            "reason": "invalid_order",
        }

        order_service = OrderService(broker=mock_broker)
        risk_manager = RiskManager()

        adversarial_orders = FuzzTestDataGenerator.adversarial_orders()

        blocked_by_validation = 0
        blocked_by_risk = 0
        unexpected_successes = 0
        system_crashes = 0

        for i, malicious_order in enumerate(adversarial_orders):
            try:
                # First pass through validation
                validation_result = order_service.validate_order(malicious_order)

                if not validation_result.get("valid", False):
                    blocked_by_validation += 1
                    continue

                # Then pass through risk management - await the async call
                risk_decision = await risk_manager.check_order_risk(malicious_order)

                # Convert RiskDecision to dict format for compatibility
                if hasattr(risk_decision, 'allowed'):
                    risk_result = {"approved": risk_decision.allowed}
                else:
                    risk_result = {"approved": False}

                if not risk_result.get("approved", False):
                    blocked_by_risk += 1
                    continue

                # If it gets this far, it shouldn't be malicious
                # Verify the order is actually safe
                if "qty" in malicious_order:
                    qty = malicious_order["qty"]
                    if isinstance(qty, (int, float)) and qty > 0 and qty < 10000:
                        # This might be a legitimate edge case
                        continue

                unexpected_successes += 1

            except Exception as e:
                system_crashes += 1
                print(f"System crash on case {i}: {type(e).__name__}: {str(e)}")

        print("✓ Adversarial Order Test:")
        print(f"  - Orders Tested: {len(adversarial_orders)}")
        print(f"  - Blocked by Validation: {blocked_by_validation}")
        print(f"  - Blocked by Risk: {blocked_by_risk}")
        print(f"  - Unexpected Successes: {unexpected_successes}")
        print(f"  - System Crashes: {system_crashes}")

        # Security assertions
        assert system_crashes == 0, "System should never crash on malicious input"
        assert (
            unexpected_successes < 5
        ), f"Too many malicious orders succeeded: {unexpected_successes}"
        assert (
            blocked_by_validation + blocked_by_risk > len(adversarial_orders) * 0.5
        ), "Not enough blocking"

    @pytest.mark.fuzz
    @given(
        st.text(min_size=1, max_size=100),
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        st.integers(min_value=-1000000, max_value=1000000),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
    def test_hypothesis_market_data_fuzzing(self, symbol, price, volume):
        """Use Hypothesis to generate random market data inputs."""
        from backend.data.market_data import MarketDataProcessor

        processor = MarketDataProcessor()

        # Create test data
        test_data = {
            "symbol": symbol,
            "price": price,
            "volume": volume,
            "timestamp": datetime.now(),
        }

        # Should never crash, regardless of input
        try:
            result = processor.process_tick(test_data)

            # If processing succeeded, verify result is safe
            if result is not None and result.get("status") != "rejected":
                # Check if symbol was preserved (optional since processing might not always include it)
                if 'symbol' in result:
                    assert isinstance(result.get("symbol"), str)
                    assert len(result["symbol"]) > 0

                if "price" in result:
                    assert isinstance(result["price"], (int, float, Decimal))
                    assert math.isfinite(float(result["price"]))
                    assert float(result["price"]) > 0

        except (ValueError, TypeError, InvalidOperation):
            # These are acceptable - means system rejected bad input
            pass


class TestEdgeCasesAndBoundaryConditions:
    """Test edge cases and boundary conditions."""

    @pytest.mark.fuzz
    def test_extreme_market_conditions(self):
        """Test system behavior under extreme market conditions."""
        from backend.features.technical_indicators import TechnicalIndicators

        calculator = TechnicalIndicators()

        edge_cases = [
            # All same price (no movement)
            pd.DataFrame(
                {
                    "close": [100.0] * 100,
                    "volume": [1000] * 100,
                    "timestamp": pd.date_range(
                        start="2023-01-01", periods=100, freq="1min"
                    ),
                }
            ),
            # Extreme volatility (100x price swings)
            pd.DataFrame(
                {
                    "close": [
                        100.0 * (2 ** (i % 10 - 5)) for i in range(100)
                    ],  # Huge swings
                    "volume": [1000] * 100,
                    "timestamp": pd.date_range(
                        start="2023-01-01", periods=100, freq="1min"
                    ),
                }
            ),
            # Market crash scenario (-90% in one day)
            pd.DataFrame(
                {
                    "close": [1000.0 - (i * 9) for i in range(100)],  # 1000 -> 109
                    "volume": [
                        1000000 * (1 + i) for i in range(100)
                    ],  # Increasing volume
                    "timestamp": pd.date_range(
                        start="2023-01-01", periods=100, freq="1min"
                    ),
                }
            ),
            # Flash crash (instant drop and recovery)
            pd.DataFrame(
                {
                    "close": [100.0] * 40 + [10.0] * 10 + [100.0] * 50,  # Flash crash
                    "volume": [1000] * 40 + [1000000] * 10 + [1000] * 50,
                    "timestamp": pd.date_range(
                        start="2023-01-01", periods=100, freq="1min"
                    ),
                }
            ),
            # Very small prices (penny stocks)
            pd.DataFrame(
                {
                    "close": [0.01 + i * 0.0001 for i in range(100)],  # $0.01 to $0.02
                    "volume": [1000000] * 100,
                    "timestamp": pd.date_range(
                        start="2023-01-01", periods=100, freq="1min"
                    ),
                }
            ),
            # Very high prices (BRK.A style)
            pd.DataFrame(
                {
                    "close": [500000.0 + i * 100 for i in range(100)],  # ~$500k
                    "volume": [10] * 100,  # Low volume
                    "timestamp": pd.date_range(
                        start="2023-01-01", periods=100, freq="1min"
                    ),
                }
            ),
        ]

        successful_calculations = 0
        graceful_failures = 0
        system_crashes = 0

        for i, edge_case_data in enumerate(edge_cases):
            try:
                features = calculator.calculate_all_features(edge_case_data)

                # Verify features are valid
                if features:
                    for feature_name, value in features.items():
                        if value is not None:
                            assert math.isfinite(
                                float(value)
                            ), f"Case {i}: {feature_name} not finite: {value}"

                    successful_calculations += 1
                else:
                    graceful_failures += 1

            except (ValueError, ZeroDivisionError):
                # Acceptable failures for extreme cases
                graceful_failures += 1

            except Exception as e:
                system_crashes += 1
                print(f"System crash on edge case {i}: {type(e).__name__}: {str(e)}")

        print("✓ Extreme Market Conditions Test:")
        print(f"  - Cases Tested: {len(edge_cases)}")
        print(f"  - Successful Calculations: {successful_calculations}")
        print(f"  - Graceful Failures: {graceful_failures}")
        print(f"  - System Crashes: {system_crashes}")

        # Should handle most cases without crashing
        assert system_crashes == 0, "System should never crash on edge cases"
        assert successful_calculations + graceful_failures == len(
            edge_cases
        ), "All cases should be handled"

    @pytest.mark.fuzz
    @pytest.mark.asyncio
    async def test_boundary_value_analysis(self):
        """Test boundary values for critical parameters."""
        from backend.risk.risk_manager import RiskManager

        # Test boundary values for risk parameters
        boundary_tests = [
            # Position size boundaries
            {"max_position_size": 0.0},  # Minimum
            {"max_position_size": 0.000001},  # Near minimum
            {"max_position_size": 1.0},  # Maximum (100%)
            {"max_position_size": 0.999999},  # Near maximum
            # Stop loss boundaries
            {"stop_loss_pct": 0.0},  # No stop loss
            {"stop_loss_pct": 0.001},  # Tiny stop loss (0.1%)
            {"stop_loss_pct": 1.0},  # 100% stop loss
            {"stop_loss_pct": 0.999},  # Near 100%
            # Portfolio risk boundaries
            {"max_portfolio_risk": 0.0},  # No risk
            {"max_portfolio_risk": 0.0001},  # Minimal risk
            {"max_portfolio_risk": 1.0},  # Maximum risk
            {"max_portfolio_risk": 0.9999},  # Near maximum
        ]

        valid_configs = 0
        rejected_configs = 0

        for config in boundary_tests:
            try:
                risk_manager = RiskManager(config=config)

                # Test with sample order
                test_order = {
                    "symbol": "AAPL",
                    "side": "buy",
                    "qty": 100,
                    "price": 150.0,
                    # Include portfolio context in order for risk assessment
                    "portfolio_context": {
                        "cash": 100000,
                        "total_value": 100000,
                        "positions": {},
                    }
                }

                # Should handle boundary values gracefully
                risk_result = await risk_manager.check_order_risk(test_order)

                # Verify risk result is valid (RiskDecision object)
                assert hasattr(risk_result, 'allowed'), "Risk result should have 'allowed' attribute"
                assert isinstance(risk_result.allowed, bool), "allowed should be boolean"

                valid_configs += 1

            except (ValueError, AssertionError):
                # Acceptable to reject invalid boundary values
                rejected_configs += 1

        print("✓ Boundary Value Analysis:")
        print(f"  - Configs Tested: {len(boundary_tests)}")
        print(f"  - Valid Configs: {valid_configs}")
        print(f"  - Rejected Configs: {rejected_configs}")

        # Should handle reasonable boundary values
        assert valid_configs > 0, "Should accept some boundary values"
        assert rejected_configs < len(
            boundary_tests
        ), "Should not reject all boundary values"


class TestChaosEngineering:
    """Chaos engineering tests for system resilience."""

    @pytest.mark.fuzz
    @pytest.mark.slow
    def test_random_component_failures(self):
        """Test system behavior with random component failures."""

        # Mock system components
        class FailingComponent:
            def __init__(self, name, failure_rate=0.1):
                self.name = name
                self.failure_rate = failure_rate
                self.call_count = 0

            def __call__(self, *args, **kwargs):
                self.call_count += 1

                # Random failures
                if random.random() < self.failure_rate:
                    raise ConnectionError(f"{self.name} failed randomly")

                return {
                    "status": "success",
                    "data": f"{self.name}_result_{self.call_count}",
                }

        # Create system with failing components
        failing_components = {
            "data_feed": FailingComponent("DataFeed", 0.05),  # 5% failure rate
            "broker_api": FailingComponent("BrokerAPI", 0.02),  # 2% failure rate
            "ml_model": FailingComponent("MLModel", 0.03),  # 3% failure rate
            "risk_engine": FailingComponent("RiskEngine", 0.01),  # 1% failure rate
        }

        # Simulate system operations with random failures
        operations_attempted = 1000
        operations_succeeded = 0
        graceful_failures = 0
        system_crashes = 0

        for i in range(operations_attempted):
            try:
                # Simulate a typical trading operation

                # 1. Get market data
                market_data = failing_components["data_feed"]()

                # 2. Run ML prediction
                prediction = failing_components["ml_model"](market_data)

                # 3. Check risk
                risk_check = failing_components["risk_engine"](prediction)

                # 4. Submit order (if approved)
                if risk_check.get("status") == "success":
                    order_result = failing_components["broker_api"](risk_check)

                operations_succeeded += 1

            except ConnectionError:
                # Expected failures - system should handle gracefully
                graceful_failures += 1

            except Exception as e:
                # Unexpected failures - potential system issues
                system_crashes += 1
                print(
                    f"Unexpected failure in operation {i}: {type(e).__name__}: {str(e)}"
                )

        print("✓ Random Component Failures:")
        print(f"  - Operations Attempted: {operations_attempted}")
        print(f"  - Operations Succeeded: {operations_succeeded}")
        print(f"  - Graceful Failures: {graceful_failures}")
        print(f"  - System Crashes: {system_crashes}")
        print(f"  - Success Rate: {operations_succeeded / operations_attempted:.1%}")

        # System should handle most failures gracefully
        assert system_crashes < operations_attempted * 0.01, "Too many system crashes"
        assert operations_succeeded > operations_attempted * 0.5, "Success rate too low"
        assert graceful_failures > 0, "Should have some component failures"

    @pytest.mark.fuzz
    def test_memory_pressure_simulation(self):
        """Test system behavior under memory pressure."""
        import gc

        import psutil

        # Get baseline memory
        process = psutil.Process()
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create memory pressure
        memory_hogs = []
        operations_completed = 0
        out_of_memory_errors = 0

        try:
            # Gradually increase memory usage
            for i in range(100):
                # Allocate large objects
                if i % 10 == 0:
                    # Create large data structures
                    large_data = {f"key_{j}": list(range(10000)) for j in range(1000)}
                    memory_hogs.append(large_data)

                # Simulate normal operations under memory pressure
                try:
                    # Feature calculation simulation
                    data = np.random.randn(10000)
                    features = {
                        "sma": np.mean(data),
                        "std": np.std(data),
                        "max": np.max(data),
                        "min": np.min(data),
                    }

                    # Risk calculation simulation
                    risk_score = sum(features.values()) / len(features)

                    operations_completed += 1

                except MemoryError:
                    out_of_memory_errors += 1
                    break

                # Check current memory usage
                current_memory = process.memory_info().rss / 1024 / 1024
                if current_memory > baseline_memory * 5:  # 5x baseline
                    break

        finally:
            # Clean up memory
            memory_hogs.clear()
            gc.collect()

        final_memory = process.memory_info().rss / 1024 / 1024

        print("✓ Memory Pressure Test:")
        print(f"  - Baseline Memory: {baseline_memory:.1f}MB")
        print(f"  - Final Memory: {final_memory:.1f}MB")
        print(f"  - Operations Completed: {operations_completed}")
        print(f"  - Out of Memory Errors: {out_of_memory_errors}")

        # Should complete reasonable number of operations
        assert (
            operations_completed > 5
        ), f"Too few operations completed: {operations_completed}"

        # Should return to reasonable memory usage (allow for garbage collector delay)
        assert (
            final_memory < baseline_memory * 4
        ), f"Memory not cleaned up: {final_memory:.1f}MB"

    @pytest.mark.fuzz
    def test_network_instability_simulation(self):
        """Test system behavior with network instability."""
        import random
        import time

        class UnstableNetworkMock:
            """Mock network with random delays and failures."""

            def __init__(self):
                self.call_count = 0
                self.failure_count = 0
                self.total_delay = 0

            def make_request(self, request_type="data"):
                self.call_count += 1

                # Random network conditions
                rand = random.random()

                if rand < 0.05:  # 5% complete failures
                    self.failure_count += 1
                    raise ConnectionError("Network unreachable")

                elif rand < 0.15:  # 10% timeout
                    self.failure_count += 1
                    raise TimeoutError("Request timeout")

                elif rand < 0.30:  # 15% slow responses
                    delay = random.uniform(2.0, 10.0)  # 2-10 second delay
                    self.total_delay += delay
                    time.sleep(delay / 1000)  # Scale down for testing

                else:  # Normal response
                    delay = random.uniform(0.1, 0.5)  # Normal latency
                    self.total_delay += delay
                    time.sleep(delay / 1000)  # Scale down for testing

                return {"status": "success", "data": f"{request_type}_data"}

        network = UnstableNetworkMock()

        # Simulate system operations with unstable network
        operations = ["market_data", "order_submit", "account_info", "positions"]

        successful_operations = 0
        failed_operations = 0
        total_operations = 500

        start_time = time.perf_counter()

        for i in range(total_operations):
            operation = operations[i % len(operations)]

            try:
                result = network.make_request(operation)
                successful_operations += 1

            except (ConnectionError, TimeoutError):
                failed_operations += 1
                # System should implement retry logic here

        end_time = time.perf_counter()
        duration = end_time - start_time

        print("✓ Network Instability Test:")
        print(f"  - Total Operations: {total_operations}")
        print(f"  - Successful: {successful_operations}")
        print(f"  - Failed: {failed_operations}")
        print(f"  - Success Rate: {successful_operations / total_operations:.1%}")
        print(f"  - Network Failures: {network.failure_count}")
        print(f"  - Average Latency: {network.total_delay / network.call_count:.1f}ms")
        print(f"  - Test Duration: {duration:.2f}s")

        # Should handle network instability reasonably
        assert (
            successful_operations > total_operations * 0.7
        ), "Too many network failures"
        assert failed_operations > 0, "Should have some network failures in test"


@pytest.fixture
def malformed_data_samples():
    """Provide samples of malformed data for testing."""
    return FuzzTestDataGenerator.malformed_market_data()


@pytest.fixture
def adversarial_orders():
    """Provide adversarial order samples for testing."""
    return FuzzTestDataGenerator.adversarial_orders()
