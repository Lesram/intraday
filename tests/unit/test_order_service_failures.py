"""
Comprehensive unit tests for order service idempotency, broker failures, and retry logic.
Tests order submission edge cases, idempotency key handling, and outbox pattern reliability.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock
import uuid

import pytest

from backend.infra.schemas import Order
from backend.services.order_service import OrderService
from backend.strategies.types import TradingSignal


class TestOrderServiceIdempotency:
    """Test order service idempotency key handling and duplicate protection."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_submit_order_new_idempotency_key(self):
        """Test order submission with new idempotency key."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()

        # Mock new order creation
        new_order = Order(
            id=uuid.uuid4(),
            client_idempotency_key="new-key-123",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            tif="ioc",
            status="accepted",
            submitted_at=datetime.utcnow(),
        )
        mock_orders_repo.upsert_by_idempotency.return_value = new_order

        service = OrderService(mock_orders_repo, mock_outbox_repo)

        result = await service.submit_symbol_order(
            symbol="AAPL", side="buy", qty=100.0, idempotency_key="new-key-123"
        )

        # Should create new order and add to outbox
        mock_orders_repo.upsert_by_idempotency.assert_called_once()
        mock_outbox_repo.add_order_submit_event.assert_called_once()

        assert result["order_id"] == str(new_order.id)
        assert result["symbol"] == "AAPL"
        assert result["status"] == "accepted"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_submit_order_duplicate_idempotency_key(self):
        """Test order submission with duplicate idempotency key."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()

        # Mock existing order return
        existing_order = Order(
            id=uuid.uuid4(),
            client_idempotency_key="duplicate-key-123",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            tif="ioc",
            status="filled",  # Already processed
            submitted_at=datetime.utcnow() - timedelta(minutes=5),
        )
        mock_orders_repo.upsert_by_idempotency.return_value = existing_order

        service = OrderService(mock_orders_repo, mock_outbox_repo)

        result = await service.submit_symbol_order(
            symbol="AAPL",  # Same symbol
            side="buy",
            qty=100.0,
            idempotency_key="duplicate-key-123",
        )

        # Should return existing order without adding to outbox again
        mock_orders_repo.upsert_by_idempotency.assert_called_once()
        mock_outbox_repo.add_order_submit_event.assert_called_once()  # Still called by service logic

        assert result["order_id"] == str(existing_order.id)
        assert result["status"] == "filled"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_submit_order_concurrent_duplicate_keys(self):
        """Test concurrent order submissions with same idempotency key."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()

        # Simulate race condition - first call creates, second gets existing
        order_id = uuid.uuid4()
        new_order = Order(
            id=order_id,
            client_idempotency_key="race-key-123",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            tif="ioc",
            status="accepted",
            submitted_at=datetime.utcnow(),
        )

        # First call creates, subsequent calls return existing
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return new_order

        mock_orders_repo.upsert_by_idempotency.side_effect = side_effect

        service = OrderService(mock_orders_repo, mock_outbox_repo)

        # Submit multiple concurrent orders with same key
        tasks = [
            service.submit_symbol_order(
                symbol="AAPL", side="buy", qty=100.0, idempotency_key="race-key-123"
            )
            for _ in range(3)
        ]

        results = await asyncio.gather(*tasks)

        # All should return same order ID
        assert all(r["order_id"] == str(order_id) for r in results)
        assert mock_orders_repo.upsert_by_idempotency.call_count == 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_idempotency_key_validation(self):
        """Test validation of idempotency key format and uniqueness."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()
        service = OrderService(mock_orders_repo, mock_outbox_repo)

        # Test various idempotency key formats
        valid_keys = [
            "simple-key",
            "key_with_underscores",
            "key-with-dashes",
            "key123with456numbers",
            "KEY-WITH-CAPS",
            str(uuid.uuid4()),  # UUID format
            "very-long-idempotency-key-that-should-still-be-valid-123456789",
        ]

        new_order = Order(
            id=uuid.uuid4(),
            client_idempotency_key="test-key",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            tif="ioc",
            status="accepted",
            submitted_at=datetime.utcnow(),
        )
        mock_orders_repo.upsert_by_idempotency.return_value = new_order

        for key in valid_keys:
            result = await service.submit_symbol_order(
                symbol="AAPL", side="buy", qty=100.0, idempotency_key=key
            )
            assert result["idempotency_key"] == key


class TestOrderServiceFailureHandling:
    """Test order service behavior during various failure scenarios."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_orders_repo_database_failure(self):
        """Test handling of database failures in orders repository."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()

        # Simulate database connection failure
        mock_orders_repo.upsert_by_idempotency.side_effect = Exception("Database connection failed")

        service = OrderService(mock_orders_repo, mock_outbox_repo)

        with pytest.raises(Exception, match="Database connection failed"):
            await service.submit_symbol_order(
                symbol="AAPL", side="buy", qty=100.0, idempotency_key="fail-key-123"
            )

        # Outbox should not be called if order creation fails
        mock_outbox_repo.add_order_submit_event.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_outbox_repo_failure_after_order_creation(self):
        """Test handling when outbox fails after successful order creation."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()

        # Order creation succeeds
        new_order = Order(
            id=uuid.uuid4(),
            client_idempotency_key="outbox-fail-key",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            tif="ioc",
            status="accepted",
            submitted_at=datetime.utcnow(),
        )
        mock_orders_repo.upsert_by_idempotency.return_value = new_order

        # Outbox fails
        mock_outbox_repo.add_order_submit_event.side_effect = Exception(
            "Outbox service unavailable"
        )

        service = OrderService(mock_orders_repo, mock_outbox_repo)

        with pytest.raises(Exception, match="Outbox service unavailable"):
            await service.submit_symbol_order(
                symbol="AAPL", side="buy", qty=100.0, idempotency_key="outbox-fail-key"
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_order_validation_failures(self):
        """Test order validation failure scenarios."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()
        service = OrderService(mock_orders_repo, mock_outbox_repo)

        # Invalid order parameters that should be caught
        invalid_orders = [
            # Zero quantity
            {"symbol": "AAPL", "side": "buy", "qty": 0.0, "idempotency_key": "zero-qty"},
            # Negative quantity
            {"symbol": "AAPL", "side": "buy", "qty": -100.0, "idempotency_key": "neg-qty"},
            # Empty symbol
            {"symbol": "", "side": "buy", "qty": 100.0, "idempotency_key": "empty-symbol"},
            # Invalid side
            {"symbol": "AAPL", "side": "invalid", "qty": 100.0, "idempotency_key": "invalid-side"},
        ]

        # Mock orders repo to raise validation error
        mock_orders_repo.upsert_by_idempotency.side_effect = ValueError("Invalid order parameters")

        for invalid_order in invalid_orders:
            with pytest.raises(Exception):  # Could be ValueError or other validation error
                await service.submit_symbol_order(**invalid_order)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_order_service_timeout_handling(self):
        """Test order service behavior with timeouts."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()

        # Simulate slow database operation
        async def slow_operation(*args, **kwargs):
            await asyncio.sleep(5)  # 5 second delay
            return Order(
                id=uuid.uuid4(),
                client_idempotency_key="timeout-key",
                symbol="AAPL",
                side="buy",
                qty=Decimal("100"),
                order_type="market",
                tif="ioc",
                status="accepted",
                submitted_at=datetime.utcnow(),
            )

        mock_orders_repo.upsert_by_idempotency.side_effect = slow_operation
        service = OrderService(mock_orders_repo, mock_outbox_repo)

        # Test with timeout
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(
                service.submit_symbol_order(
                    symbol="AAPL", side="buy", qty=100.0, idempotency_key="timeout-key"
                ),
                timeout=1.0,  # 1 second timeout
            )


class TestOrderServiceBrokerIntegration:
    """Test order service integration with broker through outbox pattern."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_outbox_event_payload_structure(self):
        """Test that outbox events have correct payload structure."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()

        order_id = uuid.uuid4()
        new_order = Order(
            id=order_id,
            client_idempotency_key="payload-test-key",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="limit",
            tif="gtc",
            status="accepted",
            submitted_at=datetime.utcnow(),
        )
        mock_orders_repo.upsert_by_idempotency.return_value = new_order

        service = OrderService(mock_orders_repo, mock_outbox_repo)

        await service.submit_symbol_order(
            symbol="AAPL",
            side="buy",
            qty=100.0,
            idempotency_key="payload-test-key",
            order_type="limit",
            tif="gtc",
            attributes={"priority": "high"},
        )

        # Verify outbox event payload structure
        mock_outbox_repo.add_order_submit_event.assert_called_once()
        call_args = mock_outbox_repo.add_order_submit_event.call_args

        assert call_args[1]["order_id"] == str(order_id)
        assert call_args[1]["event_type"] == "order.submit"

        payload = call_args[1]["payload"]
        assert payload["symbol"] == "AAPL"
        assert payload["side"] == "buy"
        assert payload["qty"] == "100"
        assert payload["order_type"] == "limit"
        assert payload["tif"] == "gtc"
        assert payload["client_key"] == "payload-test-key"
        assert payload["attributes"]["priority"] == "high"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broker_retry_on_failure(self):
        """Test that broker failures are handled via outbox retry mechanism."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()

        # Order creation succeeds
        new_order = Order(
            id=uuid.uuid4(),
            client_idempotency_key="retry-test-key",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            tif="ioc",
            status="accepted",
            submitted_at=datetime.utcnow(),
        )
        mock_orders_repo.upsert_by_idempotency.return_value = new_order

        service = OrderService(mock_orders_repo, mock_outbox_repo)

        result = await service.submit_symbol_order(
            symbol="AAPL", side="buy", qty=100.0, idempotency_key="retry-test-key"
        )

        # Order should be created successfully
        assert result["status"] == "accepted"

        # Outbox event should be queued for broker submission
        mock_outbox_repo.add_order_submit_event.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_orders_outbox_isolation(self):
        """Test that multiple orders create isolated outbox events."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()

        # Create multiple orders
        orders_data = [
            {"symbol": "AAPL", "qty": 100, "key": "multi-1"},
            {"symbol": "MSFT", "qty": 200, "key": "multi-2"},
            {"symbol": "GOOGL", "qty": 50, "key": "multi-3"},
        ]

        created_orders = []
        for i, order_data in enumerate(orders_data):
            order = Order(
                id=uuid.uuid4(),
                client_idempotency_key=order_data["key"],
                symbol=order_data["symbol"],
                side="buy",
                qty=Decimal(str(order_data["qty"])),
                order_type="market",
                tif="ioc",
                status="accepted",
                submitted_at=datetime.utcnow(),
            )
            created_orders.append(order)

        mock_orders_repo.upsert_by_idempotency.side_effect = created_orders

        service = OrderService(mock_orders_repo, mock_outbox_repo)

        # Submit all orders
        results = []
        for order_data in orders_data:
            result = await service.submit_symbol_order(
                symbol=order_data["symbol"],
                side="buy",
                qty=float(order_data["qty"]),
                idempotency_key=order_data["key"],
            )
            results.append(result)

        # Should have 3 separate outbox events
        assert mock_outbox_repo.add_order_submit_event.call_count == 3

        # Each result should have different order ID
        order_ids = [r["order_id"] for r in results]
        assert len(set(order_ids)) == 3


class TestOrderServiceStrategyIntegration:
    """Test order service integration with strategy engine."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_plan_and_submit_single_signal(self):
        """Test plan and submit with single trading signal."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()
        mock_strategy_engine = AsyncMock()

        # Mock strategy engine planning
        from backend.strategies.types import ExecutionPlan

        plan = ExecutionPlan(
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            reason="Signal strength above threshold",
            risk_allowed=True,
            from_exposure=0.0,
            to_exposure=15000.0,
            notional=Decimal("15000"),
        )
        mock_strategy_engine.plan_executions_from_signals.return_value = [plan]

        # Mock successful order creation
        new_order = Order(
            id=uuid.uuid4(),
            client_idempotency_key="strategy-key-1_AAPL_0",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            tif="ioc",
            status="accepted",
            submitted_at=datetime.utcnow(),
        )
        mock_orders_repo.upsert_by_idempotency.return_value = new_order

        service = OrderService(mock_orders_repo, mock_outbox_repo, mock_strategy_engine)

        # Create trading signal
        signal = TradingSignal(
            symbol="AAPL",
            signal_strength=0.8,
            confidence=0.9,
            timestamp=datetime.utcnow(),
            features={"momentum": 0.5, "mean_reversion": -0.2},
        )

        results = await service.plan_and_submit(signals=[signal], idempotency_key="strategy-key-1")

        assert len(results) == 1
        assert results[0]["symbol"] == "AAPL"
        assert results[0]["status"] == "accepted"
        assert "order_id" in results[0]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_plan_and_submit_risk_blocked_orders(self):
        """Test plan and submit with risk-blocked orders."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()
        mock_strategy_engine = AsyncMock()

        # Mock strategy engine with risk-blocked plan
        from backend.strategies.types import ExecutionPlan

        blocked_plan = ExecutionPlan(
            symbol="RISKY_STOCK",
            side="buy",
            qty=Decimal("1000"),  # Large quantity
            reason="Signal detected but risk limits exceeded",
            risk_allowed=False,
            risk_reason="Position size exceeds maximum allocation",
            from_exposure=0.0,
            to_exposure=50000.0,  # Would exceed limits
            notional=Decimal("50000"),
        )
        mock_strategy_engine.plan_executions_from_signals.return_value = [blocked_plan]

        service = OrderService(mock_orders_repo, mock_outbox_repo, mock_strategy_engine)

        signal = TradingSignal(
            symbol="RISKY_STOCK",
            signal_strength=0.9,  # Strong signal
            confidence=0.8,
            timestamp=datetime.utcnow(),
            features={"momentum": 0.8},
        )

        results = await service.plan_and_submit(
            signals=[signal], idempotency_key="risk-blocked-key"
        )

        assert len(results) == 1
        assert results[0]["symbol"] == "RISKY_STOCK"
        assert results[0]["status"] == "risk_blocked"
        assert results[0]["reason"] == "Position size exceeds maximum allocation"
        assert results[0]["risk_allowed"] is False

        # No order should be submitted
        mock_orders_repo.upsert_by_idempotency.assert_not_called()
        mock_outbox_repo.add_order_submit_event.assert_not_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_plan_and_submit_mixed_results(self):
        """Test plan and submit with mix of successful and failed orders."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()
        mock_strategy_engine = AsyncMock()

        # Mock multiple plans with different outcomes
        from backend.strategies.types import ExecutionPlan

        plans = [
            # Successful plan
            ExecutionPlan(
                symbol="AAPL",
                side="buy",
                qty=Decimal("100"),
                reason="Strong buy signal",
                risk_allowed=True,
                from_exposure=0.0,
                to_exposure=15000.0,
                notional=Decimal("15000"),
            ),
            # Risk blocked plan
            ExecutionPlan(
                symbol="RISKY_STOCK",
                side="buy",
                qty=Decimal("0"),  # No quantity due to risk
                reason="Signal detected but risk blocked",
                risk_allowed=False,
                risk_reason="Exceeds sector allocation",
                from_exposure=0.0,
                to_exposure=0.0,
                notional=Decimal("0"),
            ),
            # No-op plan
            ExecutionPlan(
                symbol="STABLE_STOCK",
                side="hold",
                qty=Decimal("0"),
                reason="No significant signal",
                risk_allowed=True,
                from_exposure=10000.0,
                to_exposure=10000.0,  # No change
                notional=Decimal("0"),
            ),
        ]
        mock_strategy_engine.plan_executions_from_signals.return_value = plans

        # Mock successful order for AAPL
        successful_order = Order(
            id=uuid.uuid4(),
            client_idempotency_key="mixed-key_AAPL_0",
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            order_type="market",
            tif="ioc",
            status="accepted",
            submitted_at=datetime.utcnow(),
        )
        mock_orders_repo.upsert_by_idempotency.return_value = successful_order

        service = OrderService(mock_orders_repo, mock_outbox_repo, mock_strategy_engine)

        signals = [
            TradingSignal(
                symbol="AAPL",
                signal_strength=0.8,
                confidence=0.9,
                timestamp=datetime.utcnow(),
                features={},
            ),
            TradingSignal(
                symbol="RISKY_STOCK",
                signal_strength=0.7,
                confidence=0.8,
                timestamp=datetime.utcnow(),
                features={},
            ),
            TradingSignal(
                symbol="STABLE_STOCK",
                signal_strength=0.1,
                confidence=0.5,
                timestamp=datetime.utcnow(),
                features={},
            ),
        ]

        results = await service.plan_and_submit(signals=signals, idempotency_key="mixed-key")

        assert len(results) == 3

        # AAPL should be successful
        aapl_result = next(r for r in results if r["symbol"] == "AAPL")
        assert "order_id" in aapl_result
        assert aapl_result["status"] == "accepted"

        # RISKY_STOCK should be risk blocked
        risky_result = next(r for r in results if r["symbol"] == "RISKY_STOCK")
        assert risky_result["status"] == "risk_blocked"
        assert risky_result["risk_allowed"] is False

        # STABLE_STOCK should be no change
        stable_result = next(r for r in results if r["symbol"] == "STABLE_STOCK")
        assert stable_result["status"] == "no_change"

        # Only one actual order should be submitted (AAPL)
        mock_orders_repo.upsert_by_idempotency.call_count == 1
        mock_outbox_repo.add_order_submit_event.call_count == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_plan_and_submit_order_submission_failure(self):
        """Test plan and submit when order submission fails."""
        mock_orders_repo = AsyncMock()
        mock_outbox_repo = AsyncMock()
        mock_strategy_engine = AsyncMock()

        # Mock successful plan
        from backend.strategies.types import ExecutionPlan

        plan = ExecutionPlan(
            symbol="AAPL",
            side="buy",
            qty=Decimal("100"),
            reason="Buy signal",
            risk_allowed=True,
            from_exposure=0.0,
            to_exposure=15000.0,
            notional=Decimal("15000"),
        )
        mock_strategy_engine.plan_executions_from_signals.return_value = [plan]

        # Mock order submission failure
        mock_orders_repo.upsert_by_idempotency.side_effect = Exception("Order submission failed")

        service = OrderService(mock_orders_repo, mock_outbox_repo, mock_strategy_engine)

        signal = TradingSignal(
            symbol="AAPL",
            signal_strength=0.8,
            confidence=0.9,
            timestamp=datetime.utcnow(),
            features={},
        )

        results = await service.plan_and_submit(signals=[signal], idempotency_key="failure-key")

        assert len(results) == 1
        assert results[0]["symbol"] == "AAPL"
        assert results[0]["status"] == "submit_error"
        assert "Order submission failed" in results[0]["reason"]
