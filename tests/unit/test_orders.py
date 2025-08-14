"""
Unit tests for order state machine and order management.

Tests order lifecycle: new → partial → filled/canceled/rejected
Tests order validation, state transitions, and error handling.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from backend.models.order_integrity import OrderIntegrityService, OrderStateMachine
from backend.risk.types import OrderSpec, OrderStatus, OrderType, Side, TimeInForce
from backend.services.order_service import OrderService


class TestOrderStateMachine:
    """Test order state machine transitions and validation."""

    @pytest.fixture
    def order_state_machine(self):
        """Create OrderStateMachine instance for testing."""
        return OrderStateMachine()

    @pytest.fixture
    def sample_order(self):
        """Sample order for testing."""
        return {
            "id": "order_123",
            "client_order_id": "client_456",
            "symbol": "AAPL",
            "side": Side.BUY,
            "qty": Decimal("100"),
            "price": Decimal("185.00"),
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.DAY,
            "status": OrderStatus.NEW,
            "created_at": datetime.now(),
        }

    @pytest.mark.unit
    def test_new_order_creation(self, order_state_machine, sample_order):
        """Test creation of new order in initial state."""
        order = order_state_machine.create_order(sample_order)

        assert order["status"] == OrderStatus.NEW
        assert order["filled_qty"] == Decimal("0")
        assert order["remaining_qty"] == order["qty"]
        assert order["avg_fill_price"] is None
        assert "created_at" in order

    @pytest.mark.unit
    def test_valid_state_transitions(self, order_state_machine, sample_order):
        """Test valid order state transitions."""
        order = order_state_machine.create_order(sample_order)

        # NEW → PENDING_NEW
        order = order_state_machine.transition_to(order, OrderStatus.PENDING_NEW)
        assert order["status"] == OrderStatus.PENDING_NEW

        # PENDING_NEW → ACCEPTED
        order = order_state_machine.transition_to(order, OrderStatus.ACCEPTED)
        assert order["status"] == OrderStatus.ACCEPTED

        # ACCEPTED → PARTIALLY_FILLED
        order = order_state_machine.transition_to(
            order,
            OrderStatus.PARTIALLY_FILLED,
            filled_qty=Decimal("50"),
            avg_fill_price=Decimal("185.25"),
        )
        assert order["status"] == OrderStatus.PARTIALLY_FILLED
        assert order["filled_qty"] == Decimal("50")
        assert order["remaining_qty"] == Decimal("50")
        assert order["avg_fill_price"] == Decimal("185.25")

        # PARTIALLY_FILLED → FILLED
        order = order_state_machine.transition_to(
            order,
            OrderStatus.FILLED,
            filled_qty=Decimal("50"),  # Additional fill
            avg_fill_price=Decimal("185.30"),  # New average
        )
        assert order["status"] == OrderStatus.FILLED
        assert order["filled_qty"] == order["qty"]
        assert order["remaining_qty"] == Decimal("0")

    @pytest.mark.unit
    def test_invalid_state_transitions(self, order_state_machine, sample_order):
        """Test prevention of invalid state transitions."""
        order = order_state_machine.create_order(sample_order)

        # Cannot go directly from NEW to FILLED
        with pytest.raises(ValueError, match="Invalid state transition"):
            order_state_machine.transition_to(order, OrderStatus.FILLED)

        # Cannot go backwards from FILLED to PARTIAL
        order = order_state_machine.transition_to(order, OrderStatus.PENDING_NEW)
        order = order_state_machine.transition_to(order, OrderStatus.ACCEPTED)
        order = order_state_machine.transition_to(
            order,
            OrderStatus.FILLED,
            filled_qty=Decimal("100"),
            avg_fill_price=Decimal("185.00"),
        )

        with pytest.raises(ValueError, match="Invalid state transition"):
            order_state_machine.transition_to(order, OrderStatus.PARTIALLY_FILLED)

    @pytest.mark.unit
    def test_order_cancellation(self, order_state_machine, sample_order):
        """Test order cancellation from various states."""
        order = order_state_machine.create_order(sample_order)

        # Can cancel from NEW
        order = order_state_machine.transition_to(order, OrderStatus.CANCELED)
        assert order["status"] == OrderStatus.CANCELED
        assert order["canceled_at"] is not None

        # Test cancellation from PARTIALLY_FILLED
        order2 = order_state_machine.create_order(sample_order)
        order2 = order_state_machine.transition_to(order2, OrderStatus.PENDING_NEW)
        order2 = order_state_machine.transition_to(order2, OrderStatus.ACCEPTED)
        order2 = order_state_machine.transition_to(
            order2, OrderStatus.PARTIALLY_FILLED, filled_qty=Decimal("30")
        )
        order2 = order_state_machine.transition_to(order2, OrderStatus.CANCELED)

        assert order2["status"] == OrderStatus.CANCELED
        assert order2["filled_qty"] == Decimal("30")  # Keeps partial fill

    @pytest.mark.unit
    def test_order_rejection(self, order_state_machine, sample_order):
        """Test order rejection scenarios."""
        order = order_state_machine.create_order(sample_order)

        # Reject with reason
        order = order_state_machine.transition_to(
            order, OrderStatus.REJECTED, rejection_reason="insufficient_buying_power"
        )

        assert order["status"] == OrderStatus.REJECTED
        assert order["rejection_reason"] == "insufficient_buying_power"
        assert order["rejected_at"] is not None

    @pytest.mark.unit
    def test_partial_fill_calculations(self, order_state_machine, sample_order):
        """Test partial fill quantity and price calculations."""
        order = order_state_machine.create_order(sample_order)
        order = order_state_machine.transition_to(order, OrderStatus.PENDING_NEW)
        order = order_state_machine.transition_to(order, OrderStatus.ACCEPTED)

        # First partial fill: 30 @ 185.00
        order = order_state_machine.transition_to(
            order,
            OrderStatus.PARTIALLY_FILLED,
            filled_qty=Decimal("30"),
            avg_fill_price=Decimal("185.00"),
        )

        assert order["filled_qty"] == Decimal("30")
        assert order["remaining_qty"] == Decimal("70")
        assert order["avg_fill_price"] == Decimal("185.00")

        # Second partial fill: 20 @ 185.50 (should average)
        order = order_state_machine.add_fill(
            order, fill_qty=Decimal("20"), fill_price=Decimal("185.50")
        )

        # Weighted average: (30 * 185.00 + 20 * 185.50) / 50 = 185.20
        expected_avg = (
            Decimal("30") * Decimal("185.00") + Decimal("20") * Decimal("185.50")
        ) / Decimal("50")

        assert order["filled_qty"] == Decimal("50")
        assert order["remaining_qty"] == Decimal("50")
        assert abs(order["avg_fill_price"] - expected_avg) < Decimal("0.01")

    @pytest.mark.unit
    def test_order_expiration(self, order_state_machine, sample_order):
        """Test order expiration handling."""
        # Create day order
        order = order_state_machine.create_order(sample_order)
        order["time_in_force"] = TimeInForce.DAY

        # Simulate market close expiration
        order = order_state_machine.transition_to(
            order, OrderStatus.EXPIRED, expiration_reason="market_close"
        )

        assert order["status"] == OrderStatus.EXPIRED
        assert order["expiration_reason"] == "market_close"
        assert order["expired_at"] is not None

    @pytest.mark.unit
    def test_order_replacement(self, order_state_machine, sample_order):
        """Test order replacement/modification."""
        original_order = order_state_machine.create_order(sample_order)

        # Create replacement order
        replacement_spec = sample_order.copy()
        replacement_spec["qty"] = Decimal("150")  # Increase quantity
        replacement_spec["price"] = Decimal("184.00")  # Lower price

        replacement_order = order_state_machine.replace_order(
            original_order, replacement_spec
        )

        # Original should be replaced
        assert original_order["status"] == OrderStatus.REPLACED
        assert original_order["replaced_by"] == replacement_order["id"]

        # Replacement should reference original
        assert replacement_order["replaces"] == original_order["id"]
        assert replacement_order["qty"] == Decimal("150")
        assert replacement_order["price"] == Decimal("184.00")


class TestOrderValidation:
    """Test order validation and business rules."""

    @pytest.fixture
    def order_validator(self):
        """Create OrderIntegrityService instance for testing."""
        return OrderIntegrityService()

    @pytest.mark.unit
    def test_valid_market_order(self, order_validator):
        """Test validation of valid market orders."""
        order_spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )

        result = order_validator.validate(order_spec)

        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.unit
    def test_valid_limit_order(self, order_validator):
        """Test validation of valid limit orders."""
        order_spec = OrderSpec(
            symbol="AAPL",
            side=Side.SELL,
            qty=Decimal("50"),
            price=Decimal("190.00"),
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
        )

        result = order_validator.validate(order_spec)

        assert result["is_valid"] is True
        assert len(result["errors"]) == 0

    @pytest.mark.unit
    def test_invalid_negative_quantity(self, order_validator):
        """Test validation rejects negative quantities."""
        order_spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("-100"),  # Invalid
            order_type=OrderType.MARKET,
        )

        result = order_validator.validate(order_spec)

        assert result["is_valid"] is False
        assert any(error["field"] == "qty" for error in result["errors"])
        assert any("negative" in error["message"].lower() for error in result["errors"])

    @pytest.mark.unit
    def test_invalid_zero_quantity(self, order_validator):
        """Test validation rejects zero quantities."""
        order_spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("0"),  # Invalid
            order_type=OrderType.MARKET,
        )

        result = order_validator.validate(order_spec)

        assert result["is_valid"] is False
        assert any(error["field"] == "qty" for error in result["errors"])

    @pytest.mark.unit
    def test_limit_order_missing_price(self, order_validator):
        """Test validation requires price for limit orders."""
        order_spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            order_type=OrderType.LIMIT,
            # price=None - Missing!
        )

        result = order_validator.validate(order_spec)

        assert result["is_valid"] is False
        assert any(error["field"] == "price" for error in result["errors"])
        assert any(
            "limit order" in error["message"].lower() for error in result["errors"]
        )

    @pytest.mark.unit
    def test_market_order_with_price_warning(self, order_validator):
        """Test validation warns about price on market orders."""
        order_spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            price=Decimal("185.00"),  # Ignored for market orders
            order_type=OrderType.MARKET,
        )

        result = order_validator.validate(order_spec)

        # Should be valid but with warning
        assert result["is_valid"] is True
        assert len(result["warnings"]) > 0
        assert any(
            "market order" in warning["message"].lower()
            for warning in result["warnings"]
        )

    @pytest.mark.unit
    def test_invalid_symbol_format(self, order_validator):
        """Test validation of symbol format."""
        invalid_symbols = ["", "A", "TOOLONG", "123ABC", "A@PL"]

        for symbol in invalid_symbols:
            order_spec = OrderSpec(
                symbol=symbol,
                side=Side.BUY,
                qty=Decimal("100"),
                order_type=OrderType.MARKET,
            )

            result = order_validator.validate(order_spec)

            assert result["is_valid"] is False
            assert any(error["field"] == "symbol" for error in result["errors"])

    @pytest.mark.unit
    def test_fractional_shares_validation(self, order_validator):
        """Test fractional share quantity validation."""
        # Some brokers allow fractional shares
        order_spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("10.5"),  # Fractional
            order_type=OrderType.MARKET,
        )

        # Should be valid for supported symbols
        with patch.object(
            order_validator, "_supports_fractional_shares", return_value=True
        ):
            result = order_validator.validate(order_spec)
            assert result["is_valid"] is True

        # Should be invalid for unsupported symbols
        with patch.object(
            order_validator, "_supports_fractional_shares", return_value=False
        ):
            result = order_validator.validate(order_spec)
            assert result["is_valid"] is False

    @pytest.mark.unit
    def test_minimum_notional_validation(self, order_validator):
        """Test minimum order notional value validation."""
        # Order below minimum notional ($1)
        order_spec = OrderSpec(
            symbol="PENNY",
            side=Side.BUY,
            qty=Decimal("10"),
            price=Decimal("0.05"),  # $0.50 total
            order_type=OrderType.LIMIT,
        )

        result = order_validator.validate(order_spec)

        # Should warn or reject based on configuration
        if not result["is_valid"]:
            assert any(
                "minimum" in error["message"].lower() for error in result["errors"]
            )
        else:
            assert any(
                "minimum" in warning["message"].lower()
                for warning in result["warnings"]
            )


class TestOrderService:
    """Test order service integration and business logic."""

    @pytest.fixture
    def order_service(self, mock_database, mock_alpaca_client):
        """Create OrderService instance with mocked dependencies."""
        return OrderService(
            db_session=mock_database,
            broker_client=mock_alpaca_client,
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_submit_order_success(self, order_service):
        """Test successful order submission."""
        order_spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            order_type=OrderType.MARKET,
        )

        # Mock broker response
        order_service.broker_client.submit_order.return_value = {
            "id": "broker_123",
            "status": "accepted",
            "client_order_id": "client_456",
        }

        result = await order_service.submit_order(order_spec, user_id="user_123")

        assert result["success"] is True
        assert result["order_id"] == "broker_123"
        assert result["status"] == "accepted"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_submit_order_broker_failure(self, order_service):
        """Test order submission with broker failure."""
        order_spec = OrderSpec(
            symbol="AAPL",
            side=Side.BUY,
            qty=Decimal("100"),
            order_type=OrderType.MARKET,
        )

        # Mock broker failure
        order_service.broker_client.submit_order.side_effect = Exception(
            "Broker connection failed"
        )

        result = await order_service.submit_order(order_spec, user_id="user_123")

        assert result["success"] is False
        assert "error" in result
        assert "broker" in result["error"].lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cancel_order_success(self, order_service):
        """Test successful order cancellation."""
        order_id = "order_123"

        # Mock broker response
        order_service.broker_client.cancel_order.return_value = {
            "id": order_id,
            "status": "canceled",
            "canceled_at": "2024-01-02T10:30:00Z",
        }

        result = await order_service.cancel_order(order_id, user_id="user_123")

        assert result["success"] is True
        assert result["order_id"] == order_id
        assert result["status"] == "canceled"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_order_status(self, order_service):
        """Test order status retrieval."""
        order_id = "order_123"

        # Mock database response
        order_service.db_session.fetch_one.return_value = {
            "id": order_id,
            "status": "partially_filled",
            "filled_qty": "50",
            "remaining_qty": "50",
        }

        result = await order_service.get_order_status(order_id)

        assert result["id"] == order_id
        assert result["status"] == "partially_filled"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_order_history(self, order_service):
        """Test order history retrieval with pagination."""
        user_id = "user_123"

        # Mock database response
        order_service.db_session.fetch_all.return_value = [
            {"id": "order_1", "symbol": "AAPL", "status": "filled"},
            {"id": "order_2", "symbol": "GOOGL", "status": "canceled"},
        ]

        result = await order_service.get_order_history(
            user_id=user_id, limit=10, offset=0, status_filter="all"
        )

        assert len(result["orders"]) == 2
        assert result["orders"][0]["id"] == "order_1"
        assert result["orders"][1]["id"] == "order_2"
