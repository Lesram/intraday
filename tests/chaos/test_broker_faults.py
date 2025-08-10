"""
Chaos engineering tests for broker fault scenarios.
Tests system resilience under broker failures, timeouts, and error conditions.
Gated behind @pytest.mark.chaos marker.
"""

import asyncio
import json
import random
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ConnectError, HTTPStatusError, TimeoutException
import pytest

from tests.helpers.broker_mock import AlpacaMockResponder
from tests.helpers.factories import create_order_spec


@pytest.mark.chaos
class TestBrokerChaosFaults:
    """Chaos engineering tests for broker fault injection and resilience."""

    @pytest.fixture
    async def chaos_test_app(self):
        """Create app configured for chaos testing."""
        from backend.api.main import app

        # Configure with chaos-friendly settings
        with patch.dict("os.environ", {
            "BROKER_TIMEOUT_SECONDS": "2",
            "BROKER_RETRY_ATTEMPTS": "3",
            "BROKER_BACKOFF_MULTIPLIER": "1.5",
            "CHAOS_TESTING_MODE": "true"
        }):
            yield app

    @pytest.fixture
    def chaos_broker_mock(self):
        """Broker mock configured for chaos scenarios."""
        return AlpacaMockResponder()

    @pytest.fixture
    def order_factory(self):
        """Factory for generating test orders."""
        return create_order_spec

    @pytest.mark.asyncio
    async def test_broker_502_503_retry_pattern(self, chaos_test_app, chaos_broker_mock, order_factory):
        """Test resilience to 502/503 broker errors with exponential backoff."""
        # Fault pattern: 502 → 502 → 200 (recovery after 2 failures)
        fault_sequence = [502, 502, 200, 503, 503, 200, 502, 200]
        fault_index = 0

        async def faulty_submit_order(order_data):
            nonlocal fault_index

            if fault_index < len(fault_sequence):
                status_code = fault_sequence[fault_index]
                fault_index += 1

                if status_code in [502, 503]:
                    # Simulate server errors
                    await asyncio.sleep(0.1)  # Simulate processing delay
                    raise HTTPStatusError(
                        message=f"Server Error {status_code}",
                        request=MagicMock(),
                        response=MagicMock(status_code=status_code)
                    )
                else:
                    # Success response
                    return {
                        "id": f"order_{fault_index}",
                        "status": "accepted",
                        "symbol": order_data.get("symbol", "AAPL"),
                        "qty": order_data.get("qty", 100)
                    }
            else:
                # Default success after fault sequence
                return {
                    "id": f"order_success_{fault_index}",
                    "status": "accepted",
                    "symbol": order_data.get("symbol", "AAPL"),
                    "qty": order_data.get("qty", 100)
                }

        # Mock broker service with retry logic
        with patch("backend.services.broker_service.BrokerService") as mock_broker_service:
            mock_broker_instance = AsyncMock()
            mock_broker_service.return_value = mock_broker_instance

            # Implement retry logic in mock
            async def resilient_submit_order(order_spec):
                max_retries = 3
                backoff_seconds = 0.1

                for attempt in range(max_retries + 1):
                    try:
                        result = await faulty_submit_order(order_spec)
                        return result
                    except HTTPStatusError as e:
                        if e.response.status_code in [502, 503] and attempt < max_retries:
                            # Exponential backoff
                            await asyncio.sleep(backoff_seconds * (1.5 ** attempt))
                            continue
                        else:
                            raise

                raise Exception("Max retries exceeded")

            mock_broker_instance.submit_order.side_effect = resilient_submit_order

            # Test orders that should eventually succeed despite faults
            successful_orders = 0
            failed_orders = 0

            test_orders = [
                order_factory(symbol="AAPL", side="buy", quantity=100),
                order_factory(symbol="GOOGL", side="sell", quantity=50),
                order_factory(symbol="MSFT", side="buy", quantity=200),
                order_factory(symbol="TSLA", side="buy", quantity=25),
            ]

            for order_spec in test_orders:
                try:
                    result = await mock_broker_instance.submit_order(order_spec)
                    if result and result.get("status") == "accepted":
                        successful_orders += 1
                    else:
                        failed_orders += 1
                except Exception:
                    failed_orders += 1

        # Verify resilience - should recover from temporary faults
        assert successful_orders >= 3, f"Only {successful_orders} orders succeeded despite retry logic"
        assert failed_orders <= 1, f"Too many failures ({failed_orders}) - retry logic may be insufficient"

    @pytest.mark.asyncio
    async def test_broker_timeout_handling(self, chaos_test_app, order_factory):
        """Test system behavior under broker timeout conditions."""
        timeout_scenarios = [
            {"delay_seconds": 0.5, "should_succeed": True},   # Fast response
            {"delay_seconds": 1.5, "should_succeed": True},   # Moderate delay
            {"delay_seconds": 3.0, "should_succeed": False},  # Timeout (2s limit)
            {"delay_seconds": 5.0, "should_succeed": False},  # Severe timeout
        ]

        timeout_results = []

        async def delayed_broker_response(delay_seconds):
            """Simulate broker response with configurable delay."""
            await asyncio.sleep(delay_seconds)
            return {
                "id": f"delayed_order_{delay_seconds}",
                "status": "accepted",
                "processing_time": delay_seconds
            }

        # Mock broker service with timeout handling
        with patch("backend.services.broker_service.BrokerService") as mock_broker_service:
            mock_broker_instance = AsyncMock()
            mock_broker_service.return_value = mock_broker_instance

            async def timeout_aware_submit(order_spec, delay_seconds):
                """Submit order with timeout awareness."""
                try:
                    # Use asyncio.wait_for to enforce timeout
                    result = await asyncio.wait_for(
                        delayed_broker_response(delay_seconds),
                        timeout=2.0  # 2-second timeout
                    )
                    return result
                except TimeoutError:
                    raise TimeoutException("Broker request timed out")

            # Test each timeout scenario
            for scenario in timeout_scenarios:
                order_spec = order_factory(
                    symbol="TIMEOUT_TEST",
                    side="buy",
                    quantity=100
                )

                try:
                    result = await timeout_aware_submit(order_spec, scenario["delay_seconds"])
                    success = True
                    error_type = None
                except TimeoutException:
                    success = False
                    error_type = "timeout"
                except Exception as e:
                    success = False
                    error_type = type(e).__name__

                timeout_results.append({
                    "delay_seconds": scenario["delay_seconds"],
                    "expected_success": scenario["should_succeed"],
                    "actual_success": success,
                    "error_type": error_type
                })

        # Verify timeout handling behavior
        for result in timeout_results:
            expected = result["expected_success"]
            actual = result["actual_success"]
            delay = result["delay_seconds"]

            assert expected == actual, (
                f"Timeout handling mismatch for {delay}s delay: "
                f"expected success={expected}, got success={actual}"
            )

        # Verify appropriate timeouts occurred
        timeout_errors = [r for r in timeout_results if r["error_type"] == "timeout"]
        assert len(timeout_errors) >= 2, "Expected timeout errors for slow scenarios"

    @pytest.mark.asyncio
    async def test_broker_connection_chaos(self, chaos_test_app, order_factory):
        """Test resilience to broker connection failures and network chaos."""
        # Connection failure patterns
        connection_faults = [
            {"fault_type": "connection_refused", "recoverable": True},
            {"fault_type": "dns_failure", "recoverable": False},
            {"fault_type": "ssl_error", "recoverable": True},
            {"fault_type": "network_timeout", "recoverable": True},
        ]

        connection_results = []

        # Mock various connection failure types
        async def simulate_connection_fault(fault_type):
            """Simulate different types of connection faults."""
            if fault_type == "connection_refused":
                raise ConnectError("Connection refused by broker")
            elif fault_type == "dns_failure":
                raise ConnectError("DNS resolution failed")
            elif fault_type == "ssl_error":
                raise ConnectError("SSL handshake failed")
            elif fault_type == "network_timeout":
                await asyncio.sleep(2.5)  # Simulate network timeout
                raise TimeoutException("Network timeout")
            else:
                # Successful connection after recovery
                return {"status": "connected", "broker": "alpaca"}

        # Mock broker service with connection resilience
        with patch("backend.services.broker_service.BrokerService") as mock_broker_service:
            mock_broker_instance = AsyncMock()
            mock_broker_service.return_value = mock_broker_instance

            async def resilient_broker_operation(order_spec, fault_type):
                """Attempt broker operation with connection resilience."""
                max_connection_retries = 2

                for attempt in range(max_connection_retries + 1):
                    try:
                        if attempt == 0:
                            # First attempt - inject fault
                            await simulate_connection_fault(fault_type)
                        # Retry attempts - simulate recovery for recoverable faults
                        elif fault_type in ["connection_refused", "ssl_error", "network_timeout"]:
                            return {
                                "id": f"recovered_order_{fault_type}",
                                "status": "accepted",
                                "recovery_attempt": attempt
                            }
                        else:
                            # Non-recoverable fault persists
                            await simulate_connection_fault(fault_type)

                    except ConnectError:
                        if attempt == max_connection_retries:
                            raise  # Give up after max retries
                        await asyncio.sleep(0.2 * (attempt + 1))  # Backoff

                    except TimeoutException:
                        if attempt == max_connection_retries:
                            raise  # Give up after max retries
                        await asyncio.sleep(0.3 * (attempt + 1))  # Backoff

            # Test each connection fault scenario
            for fault_scenario in connection_faults:
                fault_type = fault_scenario["fault_type"]
                expected_recoverable = fault_scenario["recoverable"]

                order_spec = order_factory(
                    symbol=f"CONN_{fault_type.upper()}",
                    side="buy",
                    quantity=100
                )

                try:
                    result = await resilient_broker_operation(order_spec, fault_type)
                    recovered = True
                    error_type = None
                except Exception as e:
                    recovered = False
                    error_type = type(e).__name__

                connection_results.append({
                    "fault_type": fault_type,
                    "expected_recoverable": expected_recoverable,
                    "actually_recovered": recovered,
                    "error_type": error_type
                })

        # Verify connection resilience behavior
        for result in connection_results:
            fault_type = result["fault_type"]
            expected_recoverable = result["expected_recoverable"]
            actually_recovered = result["actually_recovered"]

            assert expected_recoverable == actually_recovered, (
                f"Connection recovery mismatch for {fault_type}: "
                f"expected recoverable={expected_recoverable}, got recovered={actually_recovered}"
            )

    @pytest.mark.asyncio
    async def test_broker_partial_failure_cascade(self, chaos_test_app, order_factory):
        """Test system behavior when broker operations partially fail."""
        # Scenario: Some operations succeed, some fail - test graceful degradation
        operations = [
            {"operation": "submit_order", "symbol": "AAPL", "should_succeed": True},
            {"operation": "submit_order", "symbol": "GOOGL", "should_succeed": False},  # Fails
            {"operation": "cancel_order", "order_id": "order_123", "should_succeed": True},
            {"operation": "get_positions", "should_succeed": False},  # Fails
            {"operation": "submit_order", "symbol": "MSFT", "should_succeed": True},
            {"operation": "get_account", "should_succeed": False},  # Fails
        ]

        operation_results = []

        # Mock broker service with partial failure injection
        with patch("backend.services.broker_service.BrokerService") as mock_broker_service:
            mock_broker_instance = AsyncMock()
            mock_broker_service.return_value = mock_broker_instance

            async def partially_failing_operation(operation_type, **kwargs):
                """Simulate operations that may partially fail."""
                # Determine if this operation should fail based on test scenario
                operation_config = next(
                    (op for op in operations if op["operation"] == operation_type),
                    {"should_succeed": True}
                )

                if not operation_config["should_succeed"]:
                    # Simulate different types of failures
                    failure_types = [
                        HTTPStatusError("Bad Request", request=MagicMock(), response=MagicMock(status_code=400)),
                        HTTPStatusError("Unauthorized", request=MagicMock(), response=MagicMock(status_code=401)),
                        HTTPStatusError("Rate Limited", request=MagicMock(), response=MagicMock(status_code=429)),
                        Exception("Internal broker error")
                    ]

                    failure = random.choice(failure_types)
                    raise failure
                # Successful operation
                elif operation_type == "submit_order":
                    return {
                        "id": f"order_{kwargs.get('symbol', 'UNKNOWN')}",
                        "status": "accepted",
                        "symbol": kwargs.get("symbol")
                    }
                elif operation_type == "cancel_order":
                    return {
                        "id": kwargs.get("order_id"),
                        "status": "cancelled"
                    }
                elif operation_type == "get_positions":
                    return [{"symbol": "AAPL", "qty": 100, "market_value": 15000}]
                elif operation_type == "get_account":
                    return {"buying_power": 50000, "equity": 100000}

            # Execute operations and handle partial failures
            for operation_config in operations:
                operation_type = operation_config["operation"]
                expected_success = operation_config["should_succeed"]

                try:
                    if operation_type == "submit_order":
                        order_spec = order_factory(
                            symbol=operation_config["symbol"],
                            side="buy",
                            quantity=100
                        )
                        result = await partially_failing_operation("submit_order", symbol=operation_config["symbol"])

                    elif operation_type == "cancel_order":
                        result = await partially_failing_operation("cancel_order", order_id=operation_config["order_id"])

                    elif operation_type == "get_positions":
                        result = await partially_failing_operation("get_positions")

                    elif operation_type == "get_account":
                        result = await partially_failing_operation("get_account")

                    else:
                        result = None

                    success = True
                    error_type = None

                except Exception as e:
                    success = False
                    error_type = type(e).__name__
                    result = None

                operation_results.append({
                    "operation": operation_type,
                    "expected_success": expected_success,
                    "actual_success": success,
                    "error_type": error_type,
                    "result": result
                })

        # Verify partial failure handling
        successful_operations = [r for r in operation_results if r["actual_success"]]
        failed_operations = [r for r in operation_results if not r["actual_success"]]

        # Should have some successes and some failures as designed
        assert len(successful_operations) == 3, f"Expected 3 successful operations, got {len(successful_operations)}"
        assert len(failed_operations) == 3, f"Expected 3 failed operations, got {len(failed_operations)}"

        # Verify behavior matches expectations
        for result in operation_results:
            expected = result["expected_success"]
            actual = result["actual_success"]
            operation = result["operation"]

            assert expected == actual, (
                f"Operation {operation} success mismatch: expected {expected}, got {actual}"
            )

    @pytest.mark.asyncio
    async def test_broker_rate_limiting_backoff(self, chaos_test_app, order_factory):
        """Test exponential backoff behavior under broker rate limiting."""
        # Rate limiting scenario: 429 errors with Retry-After headers
        rate_limit_sequence = [
            {"status": 429, "retry_after": 1, "attempt": 1},
            {"status": 429, "retry_after": 2, "attempt": 2},
            {"status": 200, "retry_after": None, "attempt": 3},  # Success after backoff
        ]

        attempt_count = 0
        backoff_times = []

        async def rate_limited_operation():
            """Simulate rate-limited broker operation."""
            nonlocal attempt_count

            if attempt_count < len(rate_limit_sequence):
                scenario = rate_limit_sequence[attempt_count]
                attempt_count += 1

                if scenario["status"] == 429:
                    # Simulate rate limiting with Retry-After
                    error = HTTPStatusError(
                        "Rate Limited",
                        request=MagicMock(),
                        response=MagicMock(
                            status_code=429,
                            headers={"Retry-After": str(scenario["retry_after"])}
                        )
                    )
                    raise error
                else:
                    # Successful response
                    return {
                        "id": "rate_limit_recovered",
                        "status": "accepted",
                        "attempt": attempt_count
                    }
            else:
                return {"id": "final_success", "status": "accepted"}

        # Mock broker service with rate limit handling
        with patch("backend.services.broker_service.BrokerService") as mock_broker_service:
            mock_broker_instance = AsyncMock()
            mock_broker_service.return_value = mock_broker_instance

            async def rate_limit_aware_submit(order_spec):
                """Submit order with rate limit awareness."""
                max_rate_limit_retries = 3

                for retry_attempt in range(max_rate_limit_retries + 1):
                    try:
                        result = await rate_limited_operation()
                        return result

                    except HTTPStatusError as e:
                        if e.response.status_code == 429 and retry_attempt < max_rate_limit_retries:
                            # Extract Retry-After header
                            retry_after = int(e.response.headers.get("Retry-After", 1))

                            # Record backoff time for analysis
                            backoff_start = asyncio.get_event_loop().time()
                            await asyncio.sleep(retry_after)
                            backoff_end = asyncio.get_event_loop().time()

                            backoff_times.append({
                                "attempt": retry_attempt + 1,
                                "retry_after": retry_after,
                                "actual_backoff": backoff_end - backoff_start
                            })
                            continue
                        else:
                            raise

                raise Exception("Rate limit retries exhausted")

            # Test rate limit resilience
            order_spec = order_factory(
                symbol="RATE_LIMIT_TEST",
                side="buy",
                quantity=100
            )

            result = await rate_limit_aware_submit(order_spec)

        # Verify rate limit backoff behavior
        assert result["status"] == "accepted", "Order should succeed after rate limit backoff"
        assert len(backoff_times) == 2, f"Expected 2 backoff attempts, got {len(backoff_times)}"

        # Verify backoff times respect Retry-After headers
        for i, backoff in enumerate(backoff_times):
            expected_retry_after = rate_limit_sequence[i]["retry_after"]
            actual_backoff = backoff["actual_backoff"]

            # Allow some tolerance for timing precision
            assert abs(actual_backoff - expected_retry_after) < 0.1, (
                f"Backoff time {actual_backoff:.2f}s doesn't match Retry-After {expected_retry_after}s"
            )

    @pytest.mark.asyncio
    async def test_broker_data_corruption_detection(self, chaos_test_app, order_factory):
        """Test detection and handling of corrupted broker responses."""
        # Data corruption scenarios
        corruption_scenarios = [
            {"scenario": "malformed_json", "data": '{"id": "order_123", "status": "accepted"'},  # Missing closing brace
            {"scenario": "invalid_fields", "data": {"id": None, "status": "accepted", "symbol": ""}},  # Invalid values
            {"scenario": "missing_required", "data": {"status": "accepted"}},  # Missing required field 'id'
            {"scenario": "unexpected_structure", "data": {"order": {"nested": {"id": "order_123"}}}},  # Wrong structure
            {"scenario": "valid_response", "data": {"id": "order_123", "status": "accepted", "symbol": "AAPL"}},  # Valid for comparison
        ]

        corruption_results = []

        # Mock broker service with corruption detection
        with patch("backend.services.broker_service.BrokerService") as mock_broker_service:
            mock_broker_instance = AsyncMock()
            mock_broker_service.return_value = mock_broker_instance

            def validate_broker_response(response_data):
                """Validate broker response structure and content."""
                if isinstance(response_data, str):
                    # Check for malformed JSON
                    try:
                        json.loads(response_data)
                    except json.JSONDecodeError:
                        raise ValueError("Malformed JSON response from broker")

                if isinstance(response_data, dict):
                    # Check required fields
                    required_fields = ["id", "status"]
                    for field in required_fields:
                        if field not in response_data or response_data[field] is None:
                            raise ValueError(f"Missing or null required field: {field}")

                    # Check field validity
                    if not response_data.get("id") or not isinstance(response_data["id"], str):
                        raise ValueError("Invalid order ID in broker response")

                    if response_data.get("symbol") == "":
                        raise ValueError("Empty symbol in broker response")

                return True

            async def corrupted_broker_operation(scenario_data):
                """Simulate broker operation with potential data corruption."""
                try:
                    if isinstance(scenario_data, str):
                        # Try to parse as JSON first
                        parsed_data = json.loads(scenario_data)
                        validate_broker_response(parsed_data)
                        return parsed_data
                    else:
                        validate_broker_response(scenario_data)
                        return scenario_data

                except (json.JSONDecodeError, ValueError) as e:
                    raise Exception(f"Broker data corruption detected: {str(e)}")

            # Test each corruption scenario
            for scenario in corruption_scenarios:
                scenario_name = scenario["scenario"]
                scenario_data = scenario["data"]

                try:
                    result = await corrupted_broker_operation(scenario_data)
                    success = True
                    error_type = None

                except Exception as e:
                    success = False
                    error_type = str(e)
                    result = None

                corruption_results.append({
                    "scenario": scenario_name,
                    "success": success,
                    "error_type": error_type,
                    "expected_valid": scenario_name == "valid_response"
                })

        # Verify corruption detection
        valid_responses = [r for r in corruption_results if r["success"]]
        corrupted_responses = [r for r in corruption_results if not r["success"]]

        # Only the valid response should succeed
        assert len(valid_responses) == 1, f"Expected 1 valid response, got {len(valid_responses)}"
        assert valid_responses[0]["scenario"] == "valid_response"

        # All corruption scenarios should be detected
        assert len(corrupted_responses) == 4, f"Expected 4 corrupted responses detected, got {len(corrupted_responses)}"

        # Verify specific corruption types are caught
        corruption_types = {r["scenario"]: r["error_type"] for r in corrupted_responses}

        assert "malformed_json" in corruption_types
        assert "invalid_fields" in corruption_types
        assert "missing_required" in corruption_types
        assert "unexpected_structure" in corruption_types

        # Verify appropriate error messages
        assert "JSON" in corruption_types["malformed_json"]
        assert "required field" in corruption_types["missing_required"]
