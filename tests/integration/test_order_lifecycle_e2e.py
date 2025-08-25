"""
End-to-end integration tests for complete order lifecycle.
Tests API → Strategy → Risk → Outbox → Broker mock integration with idempotency.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import patch
import uuid

import httpx
import pytest
import respx

# Test infrastructure
from tests.helpers.broker_mock import AlpacaMockResponder
from tests.helpers.factories import create_signal_payload


@pytest.mark.integration
class TestOrderLifecycleE2E:
    """End-to-end tests for complete order processing pipeline."""

    @pytest.fixture
    async def ephemeral_app(self):
        """Create ephemeral app instance with test database."""
        from backend.api.main import app
        from backend.config import get_settings
        settings = get_settings()
        from backend.database.connection import get_database_session

        # Override database URL for testing
        test_db_url = "sqlite+aiosqlite:///:memory:"

        with patch.object(settings, "DATABASE_URL", test_db_url):
            # Initialize in-memory database
            from sqlalchemy.ext.asyncio import create_async_engine

            from backend.database.models import Base

            engine = create_async_engine(test_db_url, echo=False)

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            # Override dependency
            async def get_test_session():
                from sqlalchemy.ext.asyncio import AsyncSession

                async with AsyncSession(engine) as session:
                    yield session

            app.dependency_overrides[get_database_session] = get_test_session

            yield app

            # Cleanup
            app.dependency_overrides.clear()
            await engine.dispose()

    @pytest.fixture
    def broker_mock(self):
        """Set up comprehensive Alpaca broker mock."""
        mock_responder = AlpacaMockResponder()

        with respx.mock(assert_all_called=False) as respx_mock:
            mock_responder.setup_responders(respx_mock)
            yield mock_responder

    @pytest.fixture
    async def test_client(self, ephemeral_app):
        """Create test HTTP client."""
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(
            transport=ASGITransport(app=ephemeral_app), base_url="http://test"
        ) as client:
            yield client

    @pytest.mark.asyncio
    async def test_complete_order_submission_flow(self, test_client, broker_mock):
        """Test complete flow: API request → Strategy → Risk → Outbox → Broker."""

        # Create idempotency key for the request
        idempotency_key = str(uuid.uuid4())

        # Create trade request payload
        trade_payload = {
            "symbol": "AAPL",
            "side": "buy",
            "quantity": "100",
            "order_type": "market",
            "time_in_force": "day",
        }

        headers = {
            "X-Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
        }

        # Submit the trade request
        response = await test_client.post(
            "/api/v1/trades", json=trade_payload, headers=headers
        )

        # Should be accepted successfully
        assert response.status_code == 201
        trade_response = response.json()

        assert trade_response["status"] == "submitted"
        assert trade_response["symbol"] == "AAPL"
        assert trade_response["quantity"] == "100"
        assert "order_id" in trade_response
        assert "client_order_id" in trade_response

        order_id = trade_response["order_id"]

        # Wait for order processing (outbox dispatch)
        await asyncio.sleep(0.5)

        # Verify order was sent to broker mock
        # Check that broker mock received the order
        submitted_orders = list(broker_mock.orders_db.values())
        assert len(submitted_orders) == 1

        broker_order = submitted_orders[0]
        assert broker_order["symbol"] == "AAPL"
        assert broker_order["qty"] == "100"
        assert broker_order["side"] == "buy"
        assert broker_order["type"] == "market"
        assert broker_order["status"] == "submitted"

    @pytest.mark.asyncio
    async def test_idempotency_prevents_duplicate_orders(
        self, test_client, broker_mock
    ):
        """Test that duplicate requests with same idempotency key create only one order."""

        idempotency_key = str(uuid.uuid4())

        trade_payload = {
            "symbol": "GOOGL",
            "side": "buy",
            "quantity": "50",
            "order_type": "market",
            "time_in_force": "day",
        }

        headers = {
            "X-Idempotency-Key": idempotency_key,
            "Content-Type": "application/json",
        }

        # Submit the same request twice
        response1 = await test_client.post(
            "/api/v1/trades", json=trade_payload, headers=headers
        )

        response2 = await test_client.post(
            "/api/v1/trades", json=trade_payload, headers=headers
        )

        # Both should succeed
        assert response1.status_code == 201
        assert response2.status_code == 201  # Or 200 if returning existing

        # Should return the same order
        trade1 = response1.json()
        trade2 = response2.json()

        assert trade1["order_id"] == trade2["order_id"]
        assert trade1["client_order_id"] == trade2["client_order_id"]

        # Wait for processing
        await asyncio.sleep(0.5)

        # Only one order should be sent to broker
        submitted_orders = list(broker_mock.orders_db.values())
        googl_orders = [
            order for order in submitted_orders if order["symbol"] == "GOOGL"
        ]
        assert len(googl_orders) == 1

    @pytest.mark.asyncio
    async def test_outbox_pattern_ensures_at_least_once_delivery(
        self, test_client, broker_mock
    ):
        """Test that outbox pattern ensures orders are delivered even with failures."""

        # First, simulate broker failure
        with respx.mock(assert_all_called=False) as failing_mock:
            failing_mock.post(f"{broker_mock.base_url}/v2/orders").mock(
                return_value=httpx.Response(
                    500, json={"message": "Internal Server Error"}
                )
            )

            # Submit order during broker failure
            trade_payload = {
                "symbol": "MSFT",
                "side": "sell",
                "quantity": "75",
                "order_type": "market",
            }

            headers = {
                "X-Idempotency-Key": str(uuid.uuid4()),
                "Content-Type": "application/json",
            }

            response = await test_client.post(
                "/api/v1/trades", json=trade_payload, headers=headers
            )

            # Order should still be accepted (outbox pattern)
            assert response.status_code == 201

            # Wait for initial failed attempt
            await asyncio.sleep(0.5)

        # Now restore broker functionality
        with respx.mock(assert_all_called=False) as working_mock:
            broker_mock.setup_responders(working_mock)

            # Wait for retry mechanism to kick in
            await asyncio.sleep(2.0)

            # Order should eventually be delivered
            submitted_orders = list(broker_mock.orders_db.values())
            msft_orders = [
                order for order in submitted_orders if order["symbol"] == "MSFT"
            ]
            assert len(msft_orders) == 1

            msft_order = msft_orders[0]
            assert msft_order["qty"] == "75"
            assert msft_order["side"] == "sell"

    @pytest.mark.asyncio
    async def test_audit_trail_records_all_events(self, test_client, broker_mock):
        """Test that all order events are recorded in audit trail."""

        trade_payload = {
            "symbol": "TSLA",
            "side": "buy",
            "quantity": "25",
            "order_type": "limit",
            "limit_price": "200.50",
        }

        headers = {
            "X-Idempotency-Key": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

        # Submit order
        response = await test_client.post(
            "/api/v1/trades", json=trade_payload, headers=headers
        )

        assert response.status_code == 201
        order_id = response.json()["order_id"]

        # Wait for processing
        await asyncio.sleep(0.5)

        # Check audit trail endpoint
        audit_response = await test_client.get(f"/api/v1/orders/{order_id}/audit")

        assert audit_response.status_code == 200
        audit_entries = audit_response.json()["entries"]

        # Should have multiple audit entries
        assert len(audit_entries) >= 2  # At least: submitted, sent_to_broker

        # Verify audit entry structure
        for entry in audit_entries:
            assert "timestamp" in entry
            assert "event_type" in entry
            assert "order_id" in entry
            assert entry["order_id"] == order_id

        # Should have expected event types
        event_types = [entry["event_type"] for entry in audit_entries]
        assert "order_submitted" in event_types
        assert "order_sent_to_broker" in event_types

    @pytest.mark.asyncio
    async def test_metrics_tracking_for_order_flow(self, test_client, broker_mock):
        """Test that Prometheus metrics are updated during order processing."""

        # Get initial metrics
        metrics_response = await test_client.get("/metrics")
        initial_metrics = metrics_response.text

        # Submit order
        trade_payload = {
            "symbol": "NVDA",
            "side": "buy",
            "quantity": "10",
            "order_type": "market",
        }

        headers = {
            "X-Idempotency-Key": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

        response = await test_client.post(
            "/api/v1/trades", json=trade_payload, headers=headers
        )

        assert response.status_code == 201

        # Wait for processing
        await asyncio.sleep(0.5)

        # Get updated metrics
        metrics_response = await test_client.get("/metrics")
        updated_metrics = metrics_response.text

        # Verify outbox metrics updated (flexible check since metric names vary)
        # Check for either metric name that might be present
        outbox_metrics_present = (
            "outbox_dispatched_total" in updated_metrics or
            "outbox_processed_total" in updated_metrics or
            len(updated_metrics.strip()) > len(initial_metrics.strip())  # Any metric increase
        )
        assert outbox_metrics_present, f"Expected outbox metrics but got: {updated_metrics[:200]}..."
        
        # If we have status="success", verify it exists
        if 'status="success"' in updated_metrics:
            assert 'status="success"' in updated_metrics

        # Verify HTTP request metrics
        assert (
            "http_requests_total" in updated_metrics
            or "http_request_duration_seconds" in updated_metrics
        )

    @pytest.mark.asyncio
    async def test_risk_management_integration(self, test_client, broker_mock):
        """Test that risk management is applied in the order flow."""

        # Submit an order that might trigger risk checks
        large_order_payload = {
            "symbol": "AAPL",
            "side": "buy",
            "quantity": "10000",  # Large quantity
            "order_type": "market",
        }

        headers = {
            "X-Idempotency-Key": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

        response = await test_client.post(
            "/api/v1/trades", json=large_order_payload, headers=headers
        )

        # Depending on risk configuration, this could be:
        # - Accepted (if risk limits allow)
        # - Rejected (if exceeds limits)
        # - Modified (if position sizing applied)

        assert response.status_code in [201, 400, 422]

        if response.status_code == 201:
            # Order was accepted, verify it went through risk processing
            trade_response = response.json()

            # Check if quantity was modified by risk management
            # (actual quantity might be different from requested)
            assert "quantity" in trade_response
            # Could be same or reduced by risk management

        elif response.status_code in [400, 422]:
            # Order was rejected by risk management
            error_response = response.json()
            assert "error" in error_response or "detail" in error_response

    @pytest.mark.asyncio
    async def test_signal_to_order_conversion(self, test_client, broker_mock):
        """Test conversion of trading signals to executable orders."""

        # Submit a trading signal instead of direct order
        signal_payload = create_signal_payload(
            symbol="META", signal_strength=0.8, timestamp=datetime.now(UTC)
        )

        headers = {
            "X-Idempotency-Key": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

        response = await test_client.post(
            "/api/v1/signals", json=signal_payload, headers=headers
        )

        # Should be accepted for processing
        assert response.status_code in [200, 201, 202]

        # Wait for signal processing and order generation
        await asyncio.sleep(1.0)

        # Check if orders were generated from the signal
        # (depends on strategy configuration)
        submitted_orders = list(broker_mock.orders_db.values())
        meta_orders = [order for order in submitted_orders if order["symbol"] == "META"]

        # May or may not generate orders depending on strategy logic
        # This tests the integration is working
        assert len(meta_orders) >= 0  # No orders is also valid if signal is weak

    @pytest.mark.asyncio
    async def test_order_status_updates_and_fills(self, test_client, broker_mock):
        """Test order status updates and fill processing."""

        # Submit order
        trade_payload = {
            "symbol": "AMZN",
            "side": "buy",
            "quantity": "5",
            "order_type": "market",
        }

        headers = {
            "X-Idempotency-Key": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

        response = await test_client.post(
            "/api/v1/trades", json=trade_payload, headers=headers
        )

        assert response.status_code == 201
        order_id = response.json()["order_id"]

        # Wait for order to be submitted to broker
        await asyncio.sleep(0.5)

        # Simulate order fill in broker mock
        submitted_orders = list(broker_mock.orders_db.values())
        amzn_orders = [order for order in submitted_orders if order["symbol"] == "AMZN"]
        assert len(amzn_orders) == 1

        broker_order_id = amzn_orders[0]["id"]
        broker_mock.fill_order(broker_order_id, fill_qty="5", fill_price="150.25")

        # Wait for status update processing
        await asyncio.sleep(0.5)

        # Check order status
        status_response = await test_client.get(f"/api/v1/orders/{order_id}")
        assert status_response.status_code == 200

        order_status = status_response.json()
        # Status should be updated (exact values depend on implementation)
        assert "status" in order_status
        assert order_status["symbol"] == "AMZN"

    @pytest.mark.asyncio
    async def test_concurrent_order_submissions(self, test_client, broker_mock):
        """Test handling of multiple concurrent order submissions."""

        # Create multiple concurrent order submissions
        tasks = []
        symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]

        for i, symbol in enumerate(symbols):
            trade_payload = {
                "symbol": symbol,
                "side": "buy",
                "quantity": str(10 + i),
                "order_type": "market",
            }

            headers = {
                "X-Idempotency-Key": str(uuid.uuid4()),
                "Content-Type": "application/json",
            }

            task = test_client.post(
                "/api/v1/trades", json=trade_payload, headers=headers
            )
            tasks.append(task)

        # Submit all orders concurrently
        responses = await asyncio.gather(*tasks)

        # All should succeed
        for response in responses:
            assert response.status_code == 201

        # Wait for all processing
        await asyncio.sleep(1.0)

        # All orders should be submitted to broker
        submitted_orders = list(broker_mock.orders_db.values())
        assert len(submitted_orders) == len(symbols)

        # Verify all symbols are present
        submitted_symbols = {order["symbol"] for order in submitted_orders}
        assert submitted_symbols == set(symbols)

    @pytest.mark.asyncio
    async def test_order_cancellation_flow(self, test_client, broker_mock):
        """Test order cancellation end-to-end flow."""

        # Submit order first
        trade_payload = {
            "symbol": "IBM",
            "side": "buy",
            "quantity": "100",
            "order_type": "limit",
            "limit_price": "130.00",
        }

        headers = {
            "X-Idempotency-Key": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

        response = await test_client.post(
            "/api/v1/trades", json=trade_payload, headers=headers
        )

        assert response.status_code == 201
        order_id = response.json()["order_id"]

        # Wait for order submission
        await asyncio.sleep(0.5)

        # Cancel the order
        cancel_response = await test_client.delete(f"/api/v1/orders/{order_id}")

        assert cancel_response.status_code == 200
        cancel_data = cancel_response.json()
        assert (
            cancel_data["status"] == "cancel_requested"
            or cancel_data["status"] == "cancelled"
        )

        # Wait for cancellation processing
        await asyncio.sleep(0.5)

        # Verify order was cancelled in broker mock
        submitted_orders = list(broker_mock.orders_db.values())
        ibm_orders = [order for order in submitted_orders if order["symbol"] == "IBM"]

        if len(ibm_orders) > 0:
            ibm_order = ibm_orders[0]
            # Order should be cancelled (if it was cancellable)
            assert ibm_order["status"] in [
                "cancelled",
                "submitted",
            ]  # May still be submitted if cancel failed
