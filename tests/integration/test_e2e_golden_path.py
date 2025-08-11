"""
E2E Golden Path Test - Complete flow from auth to order execution.
Tests the full pipeline: auth → feature ingest → risk check → order service → outbox event
with comprehensive metrics and logging assertions.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry
import pytest

from backend.api.factory import create_app
from tests.helpers.metrics import collect_metrics, get_metric_value


class TestE2EGoldenPath:
    """End-to-end test covering the complete trading flow."""

    @pytest.fixture
    def isolated_registry(self):
        """Isolated metrics registry for this test."""
        return CollectorRegistry()

    @pytest.fixture
    def app(self, isolated_registry):
        """FastAPI app with isolated metrics."""
        return create_app(registry=isolated_registry)

    @pytest.fixture
    def client(self, app):
        """Test client for the app."""
        return TestClient(app)

    @pytest.fixture
    def mock_dependencies(self):
        """Mock external dependencies."""
        mocks = {
            "alpaca_client": AsyncMock(),
            "db_session": AsyncMock(),
            "redis_client": AsyncMock(),
            "risk_manager": AsyncMock(),
            "order_service": AsyncMock(),
            "outbox_repo": AsyncMock(),
        }
        return mocks

    @pytest.mark.integration
    def test_e2e_golden_path_complete_flow(self, client, isolated_registry, mock_dependencies):
        """
        Test complete golden path: auth → feature ingest → risk check → order submission → outbox.
        Validates metrics, logging, and business logic at each step.
        """

        # Step 1: Authentication
        auth_response = client.post(
            "/auth/login", json={"username": "test_user", "password": "test_pass"}
        )

        # Should succeed (mocked)
        assert auth_response.status_code == 200
        token_data = auth_response.json()
        assert "access_token" in token_data

        # Verify auth metrics
        auth_attempts = get_metric_value(isolated_registry, "auth_attempts_total")
        assert auth_attempts >= 1

        headers = {"Authorization": f"Bearer {token_data['access_token']}"}

        # Step 2: Feature Ingestion
        feature_payload = {
            "symbol": "AAPL",
            "timestamp": "2025-08-10T14:30:00Z",
            "features": {
                "close_price": 150.25,
                "volume": 1000000,
                "volatility_20d": 0.25,
                "rsi_14": 65.5,
                "bollinger_position": 0.8,
            },
            "technical_indicators": {"sma_20": 148.50, "ema_12": 149.75, "macd_signal": 0.15},
        }

        feature_response = client.post("/features/ingest", json=feature_payload, headers=headers)

        assert feature_response.status_code == 201

        # Verify feature metrics
        feature_ingests = get_metric_value(isolated_registry, "feature_ingests_total")
        assert feature_ingests >= 1

        # Step 3: Strategy Signal Generation (mock)
        with patch("backend.strategies.engine.StrategyEngine.generate_signal") as mock_signal:
            mock_signal.return_value = {
                "symbol": "AAPL",
                "source": "momentum",
                "target_exposure": 0.15,  # 15% long position
                "confidence": 0.85,
                "reasoning": "Strong momentum + technical breakout",
            }

            signal_response = client.post(
                "/strategies/execute",
                json={"symbol": "AAPL", "strategy": "momentum"},
                headers=headers,
            )

            assert signal_response.status_code == 200
            signal_data = signal_response.json()
            assert signal_data["target_exposure"] == 0.15

        # Verify strategy metrics
        strategy_signals = get_metric_value(isolated_registry, "strategy_signals_total")
        assert strategy_signals >= 1

        # Step 4: Risk Check
        with patch("backend.risk.risk_manager.AsyncRiskManager.before_order") as mock_risk:
            mock_risk.return_value = MagicMock(
                allowed=True,
                reason="approved",
                adjusted_qty=Decimal("10"),
                limits={"max_position": "1000"},
            )

            order_payload = {
                "symbol": "AAPL",
                "side": "buy",
                "qty": 10,
                "order_type": "market",
                "client_idempotency_key": "test-order-12345",
            }

            # Test risk check endpoint directly
            risk_response = client.post("/risk/check", json=order_payload, headers=headers)

            assert risk_response.status_code == 200
            risk_data = risk_response.json()
            assert risk_data["allowed"] is True
            assert risk_data["reason"] == "approved"

        # Verify risk metrics
        risk_decisions = get_metric_value(isolated_registry, "risk_decisions_total")
        assert risk_decisions >= 1

        # Step 5: Order Submission
        with patch("backend.services.order_service.OrderService.submit_order") as mock_submit:
            mock_submit.return_value = {
                "order_id": "order-12345",
                "status": "accepted",
                "submitted_at": "2025-08-10T14:35:00Z",
            }

            order_response = client.post("/orders/submit", json=order_payload, headers=headers)

            assert order_response.status_code == 201
            order_data = order_response.json()
            assert order_data["order_id"] == "order-12345"
            assert order_data["status"] == "accepted"

        # Verify order metrics
        order_submissions = get_metric_value(isolated_registry, "order_submissions_total")
        assert order_submissions >= 1

        # Step 6: Outbox Event Generation
        with patch("backend.infra.outbox.OutboxRepo.enqueue_event") as mock_outbox:
            mock_outbox.return_value = {
                "event_id": "evt-67890",
                "topic": "order_submitted",
                "payload": order_data,
            }

            # Outbox events should be triggered automatically by order submission
            # Verify the outbox was called
            mock_outbox.assert_called_once()
            call_args = mock_outbox.call_args[1]
            assert call_args["topic"] == "order_submitted"
            assert "order_id" in call_args["payload"]

        # Verify outbox metrics
        outbox_events = get_metric_value(isolated_registry, "outbox_enqueued_total")
        assert outbox_events >= 1

        # Step 7: Comprehensive Metrics Validation
        all_metrics = collect_metrics(isolated_registry)

        # Ensure all expected metrics are present
        expected_metrics = [
            "auth_attempts_total",
            "feature_ingests_total",
            "strategy_signals_total",
            "risk_decisions_total",
            "order_submissions_total",
            "outbox_enqueued_total",
            "http_requests_total",  # From HTTP middleware
        ]

        for metric in expected_metrics:
            assert metric in all_metrics, f"Missing metric: {metric}"
            assert all_metrics[metric] > 0, f"Metric {metric} was not incremented"

    @pytest.mark.integration
    def test_e2e_risk_rejection_flow(self, client, isolated_registry, mock_dependencies):
        """Test E2E flow when risk manager rejects the order."""

        # Setup auth
        auth_response = client.post(
            "/auth/login", json={"username": "test_user", "password": "test_pass"}
        )
        headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}

        # Risk manager rejects order
        with patch("backend.risk.risk_manager.AsyncRiskManager.before_order") as mock_risk:
            mock_risk.return_value = MagicMock(
                allowed=False,
                reason="position_limit_exceeded",
                adjusted_qty=Decimal("0"),
                limits={"max_position": "1000"},
                original_qty=Decimal("5000"),  # Over limit
            )

            order_payload = {
                "symbol": "TSLA",
                "side": "buy",
                "qty": 5000,  # Way over limit
                "order_type": "market",
                "client_idempotency_key": "risky-order-999",
            }

            # Should be rejected by risk check
            risk_response = client.post("/risk/check", json=order_payload, headers=headers)

            assert risk_response.status_code == 200
            risk_data = risk_response.json()
            assert risk_data["allowed"] is False
            assert risk_data["reason"] == "position_limit_exceeded"

        # Order submission should fail
        with patch("backend.services.order_service.OrderService.submit_order") as mock_submit:
            # Order service should respect risk decision
            mock_submit.side_effect = Exception("Risk check failed")

            order_response = client.post("/orders/submit", json=order_payload, headers=headers)

            # Should be rejected
            assert order_response.status_code in [400, 403, 422]

        # Verify risk block metrics
        risk_blocks = get_metric_value(isolated_registry, "risk_blocks_total")
        assert risk_blocks >= 1

        # No order should have been submitted
        order_submissions = get_metric_value(isolated_registry, "order_submissions_total")
        assert order_submissions == 0  # Should be 0 since order was blocked

    @pytest.mark.integration
    def test_e2e_authentication_failure_flow(self, client, isolated_registry):
        """Test E2E flow when authentication fails."""

        # Invalid credentials
        auth_response = client.post(
            "/auth/login", json={"username": "invalid_user", "password": "wrong_password"}
        )

        # Should fail authentication
        assert auth_response.status_code == 401

        # Try to access protected endpoint without auth
        order_payload = {"symbol": "AAPL", "side": "buy", "qty": 10, "order_type": "market"}

        # Should be rejected due to missing auth
        order_response = client.post("/orders/submit", json=order_payload)
        assert order_response.status_code == 401

        # Verify auth failure metrics
        auth_failures = get_metric_value(isolated_registry, "auth_failures_total")
        assert auth_failures >= 1

    @pytest.mark.integration
    def test_e2e_feature_validation_errors(self, client, isolated_registry):
        """Test E2E flow when feature data is invalid."""

        # Setup auth
        auth_response = client.post(
            "/auth/login", json={"username": "test_user", "password": "test_pass"}
        )
        headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}

        # Invalid feature payload
        invalid_feature_payload = {
            "symbol": "INVALID_SYMBOL_TOO_LONG",  # Invalid symbol
            "timestamp": "invalid-timestamp",  # Invalid timestamp
            "features": {
                "close_price": -150.25,  # Negative price
                "volume": "not_a_number",  # Invalid type
                "volatility_20d": 2.5,  # Volatility > 1 (invalid)
            },
        }

        feature_response = client.post(
            "/features/ingest", json=invalid_feature_payload, headers=headers
        )

        # Should be rejected due to validation errors
        assert feature_response.status_code == 422

        # Verify validation error metrics
        validation_errors = get_metric_value(isolated_registry, "feature_validation_errors_total")
        assert validation_errors >= 1

    @pytest.mark.integration
    def test_e2e_websocket_integration(self, client, isolated_registry):
        """Test E2E WebSocket integration for real-time updates."""

        # Test WebSocket connection
        with client.websocket_connect("/ws/market-data") as websocket:
            # Send subscription message
            websocket.send_json({"action": "subscribe", "symbols": ["AAPL", "TSLA"]})

            # Should receive confirmation
            response = websocket.receive_json()
            assert response["status"] == "subscribed"
            assert "AAPL" in response["symbols"]

            # Simulate market data update
            with patch("backend.api.websockets.broadcast_market_update") as mock_broadcast:
                mock_broadcast.return_value = None

                # Trigger market data update via HTTP
                auth_response = client.post(
                    "/auth/login", json={"username": "test_user", "password": "test_pass"}
                )
                headers = {"Authorization": f"Bearer {auth_response.json()['access_token']}"}

                # Ingest new market data
                market_update = {
                    "symbol": "AAPL",
                    "price": 151.50,
                    "timestamp": "2025-08-10T14:45:00Z",
                }

                update_response = client.post(
                    "/market-data/update", json=market_update, headers=headers
                )
                assert update_response.status_code == 200

        # Verify WebSocket metrics
        ws_connections = get_metric_value(isolated_registry, "websocket_connections_total")
        ws_messages = get_metric_value(isolated_registry, "websocket_messages_total")

        assert ws_connections >= 1
        assert ws_messages >= 2  # Subscribe + market data messages

    @pytest.mark.integration
    async def test_e2e_async_background_processing(self, isolated_registry):
        """Test E2E async background processing (outbox dispatcher)."""

        with patch("backend.infra.outbox.OutboxDispatcher") as mock_dispatcher:
            # Setup mock dispatcher
            mock_instance = AsyncMock()
            mock_dispatcher.return_value = mock_instance

            # Simulate background outbox processing
            mock_instance.poll_and_dispatch.return_value = {
                "processed": 5,
                "successful": 4,
                "failed": 1,
            }

            # Create app with background tasks
            app = create_app(registry=isolated_registry)

            # Simulate background task execution
            await mock_instance.poll_and_dispatch()

            # Verify dispatcher was called
            mock_instance.poll_and_dispatch.assert_called_once()

        # Verify background processing metrics
        outbox_processed = get_metric_value(isolated_registry, "outbox_processed_total")
        assert outbox_processed >= 4  # Successful processes
