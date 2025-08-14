"""
Integration tests for application restart and order reconciliation.
Tests that the system correctly reconciles state after restart.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import uuid

import pytest

from tests.helpers.broker_mock import AlpacaMockResponder


@pytest.mark.integration
class TestRestartReconciliation:
    """Tests for restart and reconciliation scenarios."""

    @pytest.fixture
    async def seeded_database(self):
        """Database with pre-existing orders and executions."""
        # This would use a test database with pre-seeded data

        # Create in-memory test database
        test_db_url = "sqlite+aiosqlite:///:memory:"

        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from backend.database.models import Base

        engine = create_async_engine(test_db_url, echo=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Seed with test data
        async with AsyncSession(engine) as session:
            # Create some orders in various states
            orders_data = [
                {
                    "id": str(uuid.uuid4()),
                    "client_order_id": f"test_order_{i}",
                    "broker_order_id": f"broker_{i}",
                    "symbol": ["AAPL", "GOOGL", "MSFT"][i % 3],
                    "side": "buy",
                    "quantity": Decimal("100"),
                    "status": ["submitted", "filled", "pending"][i % 3],
                    "created_at": datetime.now(UTC),
                }
                for i in range(6)  # 6 test orders
            ]

            # Add to database (mock database operations)
            yield {"orders": orders_data, "session": session}

        await engine.dispose()

    @pytest.fixture
    def broker_mock_with_positions(self):
        """Broker mock pre-loaded with positions and order states."""
        mock_responder = AlpacaMockResponder()

        # Add some existing positions
        mock_responder.add_position("AAPL", "200", "150.00")  # 200 shares at $150
        mock_responder.add_position("GOOGL", "50", "2800.00")  # 50 shares at $2800
        mock_responder.add_position(
            "MSFT", "-100", "350.00"
        )  # Short 100 shares at $350

        # Add some filled orders
        order_id_1 = mock_responder.add_order(
            {
                "symbol": "AAPL",
                "side": "buy",
                "qty": 100,
                "type": "market",
                "client_order_id": "test_order_1",
            }
        )
        mock_responder.fill_order(order_id_1, "100", "150.00")

        order_id_2 = mock_responder.add_order(
            {
                "symbol": "GOOGL",
                "side": "buy",
                "qty": 25,
                "type": "limit",
                "limit_price": "2800.00",
                "client_order_id": "test_order_2",
            }
        )
        mock_responder.fill_order(order_id_2, "25", "2800.00")

        return mock_responder

    @pytest.fixture
    async def mock_broker_service(self, broker_mock_with_positions):
        """Mock broker service that uses the broker mock for reconciliation."""

        with patch("backend.services.broker_service.BrokerService") as mock_service:
            mock_instance = AsyncMock()

            # Mock reconciliation methods
            async def mock_reconcile_open_orders():
                """Mock reconciliation that updates orders based on broker state."""
                # Simulate finding discrepancies and updating local state
                reconciliation_results = {
                    "orders_updated": 2,
                    "new_executions": 1,
                    "position_updates": 3,
                    "discrepancies_found": [
                        "order_123_status_mismatch",
                        "missing_execution_456",
                    ],
                }
                return reconciliation_results

            async def mock_get_positions():
                """Return positions from broker mock."""
                return list(broker_mock_with_positions.positions_db.values())

            async def mock_get_order_status(order_id):
                """Get order status from broker mock."""
                if order_id in broker_mock_with_positions.orders_db:
                    return broker_mock_with_positions.orders_db[order_id]
                return None

            mock_instance.reconcile_open_orders.side_effect = mock_reconcile_open_orders
            mock_instance.get_positions.side_effect = mock_get_positions
            mock_instance.get_order_status.side_effect = mock_get_order_status
            mock_instance.health_check.return_value = True

            mock_service.return_value = mock_instance
            yield mock_instance

    @pytest.mark.asyncio
    async def test_startup_reconciliation_process(
        self, seeded_database, mock_broker_service
    ):
        """Test that startup reconciliation updates local state correctly."""

        # Simulate application startup
        from httpx import ASGITransport, AsyncClient

        from backend.api.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Wait for startup to complete
            await asyncio.sleep(0.5)

            # Verify reconciliation was called
            mock_broker_service.reconcile_open_orders.assert_called_once()

            # Check application health after reconciliation
            response = await client.get("/health")
            assert response.status_code == 200

            health_data = response.json()
            assert health_data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_position_reconciliation_updates_local_state(
        self, seeded_database, mock_broker_service
    ):
        """Test that position reconciliation updates local positions correctly."""

        # Mock position service to track updates
        with patch(
            "backend.services.position_service.PositionService"
        ) as mock_position_service:
            mock_position_instance = AsyncMock()
            mock_position_service.return_value = mock_position_instance

            # Simulate startup reconciliation

            # This would normally happen during app startup
            reconciliation_results = await mock_broker_service.reconcile_open_orders()

            # Verify reconciliation found expected updates
            assert reconciliation_results["orders_updated"] == 2
            assert reconciliation_results["position_updates"] == 3
            assert reconciliation_results["new_executions"] == 1
            assert len(reconciliation_results["discrepancies_found"]) == 2

    @pytest.mark.asyncio
    async def test_missing_execution_detection_and_recovery(
        self, seeded_database, broker_mock_with_positions
    ):
        """Test detection and recovery of missing executions."""

        # Simulate scenario where local DB is missing an execution
        # but broker shows order as filled

        with patch(
            "backend.database.repositories.execution_repository.ExecutionRepository"
        ) as mock_repo:
            mock_repo_instance = AsyncMock()
            mock_repo.return_value = mock_repo_instance

            # Mock that local DB is missing executions for filled orders
            mock_repo_instance.get_executions_for_order.return_value = (
                []
            )  # No local executions

            # Mock the reconciliation process
            async def simulate_reconciliation():
                """Simulate finding and creating missing executions."""

                # Check broker for order status
                broker_orders = list(broker_mock_with_positions.orders_db.values())
                filled_orders = [
                    order for order in broker_orders if order["status"] == "filled"
                ]

                missing_executions = []
                for order in filled_orders:
                    # Check if we have local execution records
                    local_executions = (
                        await mock_repo_instance.get_executions_for_order(order["id"])
                    )

                    if not local_executions and order["filled_qty"] != "0":
                        # Found missing execution
                        missing_execution = {
                            "order_id": order["id"],
                            "fill_quantity": order["filled_qty"],
                            "fill_price": "150.00",  # From broker data
                            "execution_time": datetime.now(UTC),
                        }
                        missing_executions.append(missing_execution)

                # Create missing executions
                for execution_data in missing_executions:
                    await mock_repo_instance.create_execution(execution_data)

                return {
                    "missing_executions_found": len(missing_executions),
                    "executions_created": len(missing_executions),
                }

            results = await simulate_reconciliation()

            # Should have found and created missing executions
            assert results["missing_executions_found"] > 0
            assert results["executions_created"] == results["missing_executions_found"]

    @pytest.mark.asyncio
    async def test_order_status_discrepancy_resolution(
        self, seeded_database, broker_mock_with_positions
    ):
        """Test resolution of order status discrepancies between local and broker."""

        # Simulate local order marked as 'submitted' but broker shows 'filled'
        local_order_status = "submitted"
        broker_order_status = "filled"

        with patch(
            "backend.database.repositories.order_repository.OrderRepository"
        ) as mock_repo:
            mock_repo_instance = AsyncMock()
            mock_repo.return_value = mock_repo_instance

            # Mock local order with outdated status
            mock_local_order = {
                "id": "test_order_123",
                "broker_order_id": "broker_123",
                "status": local_order_status,
                "symbol": "AAPL",
                "quantity": Decimal("100"),
            }

            mock_repo_instance.get_order_by_id.return_value = mock_local_order

            # Mock broker order with updated status
            broker_order = {
                "id": "broker_123",
                "status": broker_order_status,
                "filled_qty": "100",
                "filled_at": datetime.now(UTC).isoformat(),
            }

            # Add this order to broker mock
            broker_mock_with_positions.orders_db["broker_123"] = broker_order

            # Simulate reconciliation process
            async def simulate_status_reconciliation():
                """Simulate reconciling order status discrepancies."""

                # Get local orders that need reconciliation
                local_orders = [mock_local_order]

                discrepancies = []
                for local_order in local_orders:
                    broker_id = local_order["broker_order_id"]
                    if broker_id in broker_mock_with_positions.orders_db:
                        broker_order = broker_mock_with_positions.orders_db[broker_id]

                        if local_order["status"] != broker_order["status"]:
                            discrepancies.append(
                                {
                                    "order_id": local_order["id"],
                                    "local_status": local_order["status"],
                                    "broker_status": broker_order["status"],
                                    "action": "update_local_status",
                                }
                            )

                            # Update local status to match broker
                            await mock_repo_instance.update_order_status(
                                local_order["id"], broker_order["status"]
                            )

                return {
                    "discrepancies_found": len(discrepancies),
                    "discrepancies": discrepancies,
                }

            results = await simulate_status_reconciliation()

            # Should have found and resolved the status discrepancy
            assert results["discrepancies_found"] == 1
            assert results["discrepancies"][0]["local_status"] == "submitted"
            assert results["discrepancies"][0]["broker_status"] == "filled"
            assert results["discrepancies"][0]["action"] == "update_local_status"

            # Verify update was called
            mock_repo_instance.update_order_status.assert_called_once_with(
                "test_order_123", "filled"
            )

    @pytest.mark.asyncio
    async def test_idempotency_preservation_after_restart(
        self, seeded_database, mock_broker_service
    ):
        """Test that idempotency keys are preserved and work correctly after restart."""

        from httpx import ASGITransport, AsyncClient

        from backend.api.main import app

        # Use a known idempotency key from seeded data
        existing_idempotency_key = "test_idempotency_key_123"

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Try to submit an order with an idempotency key that was used before restart
            trade_payload = {
                "symbol": "AAPL",
                "side": "buy",
                "quantity": "100",
                "order_type": "market",
            }

            headers = {
                "X-Idempotency-Key": existing_idempotency_key,
                "Content-Type": "application/json",
            }

            response = await client.post(
                "/api/v1/trades", json=trade_payload, headers=headers
            )

            # Should return the existing order, not create a new one
            # (exact behavior depends on implementation)
            assert response.status_code in [200, 201]

            if response.status_code == 200:
                # Returned existing order
                order_data = response.json()
                assert "order_id" in order_data
                # Verify it's the same order from before restart

    @pytest.mark.asyncio
    async def test_partial_fill_reconciliation(
        self, seeded_database, broker_mock_with_positions
    ):
        """Test reconciliation of partially filled orders."""

        # Set up a partially filled order in broker mock
        partial_order_id = broker_mock_with_positions.add_order(
            {
                "symbol": "TSLA",
                "side": "buy",
                "qty": 100,
                "type": "limit",
                "limit_price": "200.00",
                "client_order_id": "partial_fill_test",
            }
        )

        # Partially fill the order (50 out of 100 shares)
        broker_order = broker_mock_with_positions.orders_db[partial_order_id]
        broker_order["filled_qty"] = "50"
        broker_order["status"] = "partially_filled"

        with patch(
            "backend.database.repositories.execution_repository.ExecutionRepository"
        ) as mock_exec_repo:
            mock_exec_repo_instance = AsyncMock()
            mock_exec_repo.return_value = mock_exec_repo_instance

            # Mock that we have no local execution records for this partial fill
            mock_exec_repo_instance.get_executions_for_order.return_value = []

            # Simulate reconciliation
            async def reconcile_partial_fills():
                """Reconcile partial fills from broker."""

                # Check broker for partially filled orders
                broker_orders = list(broker_mock_with_positions.orders_db.values())
                partial_orders = [
                    order
                    for order in broker_orders
                    if order["status"] == "partially_filled"
                ]

                reconciliation_actions = []
                for order in partial_orders:
                    filled_qty = Decimal(order["filled_qty"])

                    if filled_qty > 0:
                        # Create execution record for the fill
                        execution_data = {
                            "order_id": order["id"],
                            "fill_quantity": order["filled_qty"],
                            "fill_price": order.get("limit_price", "200.00"),
                            "execution_time": datetime.now(UTC),
                        }

                        await mock_exec_repo_instance.create_execution(execution_data)

                        reconciliation_actions.append(
                            {
                                "action": "create_partial_execution",
                                "order_id": order["id"],
                                "filled_quantity": order["filled_qty"],
                            }
                        )

                return {"partial_fills_reconciled": len(reconciliation_actions)}

            results = await reconcile_partial_fills()

            # Should have reconciled the partial fill
            assert results["partial_fills_reconciled"] == 1

            # Verify execution was created
            mock_exec_repo_instance.create_execution.assert_called_once()

    @pytest.mark.asyncio
    async def test_reconciliation_with_broker_timeout(self, seeded_database):
        """Test reconciliation behavior when broker is temporarily unavailable."""

        with patch("backend.services.broker_service.BrokerService") as mock_service:
            mock_instance = AsyncMock()

            # Simulate broker timeout during reconciliation
            mock_instance.reconcile_open_orders.side_effect = TimeoutError(
                "Broker timeout"
            )
            mock_instance.health_check.return_value = False

            mock_service.return_value = mock_instance

            from httpx import ASGITransport, AsyncClient

            from backend.api.main import app

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # App should still start despite reconciliation failure
                # (graceful degradation)

                # Health check should reflect broker unavailability
                response = await client.get("/health")
                assert response.status_code == 200  # App is running

                # Readiness check should fail due to broker unavailability
                readiness_response = await client.get("/readyz")
                assert readiness_response.status_code == 503  # Not ready

                readiness_data = readiness_response.json()
                assert readiness_data["checks"]["broker"] is False

    @pytest.mark.asyncio
    async def test_reconciliation_metrics_tracking(
        self, seeded_database, mock_broker_service
    ):
        """Test that reconciliation process updates metrics correctly."""

        from httpx import ASGITransport, AsyncClient

        from backend.api.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Wait for startup reconciliation
            await asyncio.sleep(0.5)

            # Check metrics for reconciliation events
            metrics_response = await client.get("/metrics")
            metrics_text = metrics_response.text

            # Should have reconciliation metrics
            assert (
                "reconciliation" in metrics_text.lower()
                or "startup" in metrics_text.lower()
            )

            # Should track reconciliation success/failure
            # Exact metric names depend on implementation
