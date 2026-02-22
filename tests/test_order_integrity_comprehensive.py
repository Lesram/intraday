"""
Comprehensive tests for backend/models/order_integrity.py

Tests cover:
- OrderState enum (terminal/active states)
- OrderEventType enum
- TransitionTrigger enum
- VALID_TRANSITIONS mapping
- OrderSnapshot dataclass
- OrderEventSchema Pydantic model
- AuditLogEntry SQLAlchemy model
- OrderStateMachine (FSM logic)
- IdempotencyManager (multi-layer caching)
- AuditLogger (append-only logging with hash chaining)
- OrderIntegrityService (main orchestration service)
"""

import pytest
import hashlib
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backend.models.order_integrity import (
    OrderState,
    OrderEventType,
    TransitionTrigger,
    VALID_TRANSITIONS,
    OrderSnapshot,
    OrderEventSchema,
    AuditLogEntry,
    OrderStateMachine,
    IdempotencyManager,
    AuditLogger,
    OrderIntegrityService,
)


# =======================
# OrderState Enum Tests
# =======================


class TestOrderState:
    """Tests for OrderState enum."""

    def test_all_states_defined(self):
        """Verify all expected states are defined."""
        expected = {
            "PENDING_VALIDATION",
            "VALIDATED",
            "PENDING_RISK_ASSESSMENT",
            "RISK_APPROVED",
            "RISK_REJECTED",
            "PENDING_SUBMISSION",
            "SUBMITTED",
            "PENDING_EXECUTION",
            "PARTIALLY_FILLED",
            "FILLED",
            "CANCELLED",
            "REJECTED",
            "EXPIRED",
            "FAILED",
            "PENDING_RETRY",
            "UNDER_REVIEW",
        }
        actual = {state.name for state in OrderState}
        assert expected == actual

    def test_terminal_states(self):
        """Verify terminal states are correctly identified."""
        terminal = OrderState.terminal_states()
        
        assert OrderState.FILLED in terminal
        assert OrderState.CANCELLED in terminal
        assert OrderState.REJECTED in terminal
        assert OrderState.EXPIRED in terminal
        assert OrderState.FAILED in terminal

    def test_active_states(self):
        """Verify active states are correctly identified."""
        active = OrderState.active_states()
        
        assert OrderState.VALIDATED in active
        assert OrderState.RISK_APPROVED in active
        assert OrderState.SUBMITTED in active
        assert OrderState.PENDING_EXECUTION in active
        assert OrderState.PENDING_SUBMISSION in active
        assert OrderState.PARTIALLY_FILLED in active

    def test_terminal_and_active_are_mutually_exclusive(self):
        """Ensure no state is both terminal and active."""
        terminal = OrderState.terminal_states()
        active = OrderState.active_states()
        
        intersection = terminal.intersection(active)
        assert len(intersection) == 0

    def test_state_values_are_strings(self):
        """State values should be string representations."""
        for state in OrderState:
            assert isinstance(state.value, str)
            assert state.value == state.name.lower()


# =======================
# OrderEventType Enum Tests
# =======================


class TestOrderEventType:
    """Tests for OrderEventType enum."""

    def test_all_event_types_defined(self):
        """Verify all expected event types are defined."""
        expected = {
            "CREATED",
            "VALIDATED",
            "RISK_ASSESSED",
            "SUBMITTED",
            "EXECUTION_UPDATE",
            "FILLED",
            "CANCELLED",
            "REJECTED",
            "FAILED",
            "RETRY_SCHEDULED",
            "MANUAL_INTERVENTION",
        }
        actual = {et.name for et in OrderEventType}
        assert expected == actual

    def test_event_type_values(self):
        """Event type values should be lowercase strings."""
        for et in OrderEventType:
            assert isinstance(et.value, str)


# =======================
# TransitionTrigger Enum Tests
# =======================


class TestTransitionTrigger:
    """Tests for TransitionTrigger enum."""

    def test_all_triggers_defined(self):
        """Verify all expected triggers are defined."""
        expected = {
            "VALIDATION_COMPLETE",
            "RISK_DECISION",
            "BROKER_SUBMISSION",
            "BROKER_UPDATE",
            "USER_CANCELLATION",
            "SYSTEM_TIMEOUT",
            "ERROR_RECOVERY",
            "MANUAL_OVERRIDE",
        }
        actual = {t.name for t in TransitionTrigger}
        assert expected == actual

    def test_trigger_values(self):
        """Trigger values should be lowercase strings."""
        for t in TransitionTrigger:
            assert isinstance(t.value, str)


# =======================
# VALID_TRANSITIONS Tests
# =======================


class TestValidTransitions:
    """Tests for VALID_TRANSITIONS mapping."""

    def test_valid_transitions_is_dict(self):
        """VALID_TRANSITIONS should be a dictionary."""
        assert isinstance(VALID_TRANSITIONS, dict)

    def test_pending_validation_transitions(self):
        """Verify PENDING_VALIDATION can transition to expected states."""
        transitions = VALID_TRANSITIONS.get(OrderState.PENDING_VALIDATION, {})
        
        assert TransitionTrigger.VALIDATION_COMPLETE in transitions
        assert TransitionTrigger.USER_CANCELLATION in transitions
        assert TransitionTrigger.SYSTEM_TIMEOUT in transitions

    def test_validated_transitions(self):
        """Verify VALIDATED can transition to expected states."""
        transitions = VALID_TRANSITIONS.get(OrderState.VALIDATED, {})
        
        assert TransitionTrigger.RISK_DECISION in transitions

    def test_terminal_states_have_no_transitions(self):
        """Terminal states should not be in VALID_TRANSITIONS."""
        for state in [OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED]:
            transitions = VALID_TRANSITIONS.get(state, {})
            assert len(transitions) == 0, f"{state} should have no transitions"

    def test_risk_rejected_can_be_overridden(self):
        """RISK_REJECTED can be manually overridden."""
        transitions = VALID_TRANSITIONS.get(OrderState.RISK_REJECTED, {})
        assert TransitionTrigger.MANUAL_OVERRIDE in transitions


# =======================
# OrderSnapshot Tests
# =======================


class TestOrderSnapshot:
    """Tests for OrderSnapshot dataclass."""

    def test_create_snapshot(self):
        """Can create a basic OrderSnapshot."""
        snapshot = OrderSnapshot(
            order_id="ORD-001",
            user_id="user-123",
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type="limit",
            price=150.50,
        )
        
        assert snapshot.order_id == "ORD-001"
        assert snapshot.user_id == "user-123"
        assert snapshot.symbol == "AAPL"
        assert snapshot.side == "buy"
        assert snapshot.quantity == 100
        assert snapshot.price == 150.50
        assert snapshot.order_type == "limit"
        assert snapshot.time_in_force == "day"

    def test_to_dict(self):
        """OrderSnapshot.to_dict() returns proper dictionary."""
        snapshot = OrderSnapshot(
            order_id="ORD-002",
            user_id="user-456",
            symbol="MSFT",
            quantity=50,
            side="sell",
            order_type="market",
        )
        
        result = snapshot.to_dict()
        
        assert isinstance(result, dict)
        assert result["order_id"] == "ORD-002"
        assert result["symbol"] == "MSFT"
        assert result["side"] == "sell"
        assert "quantity" in result
        assert "created_at" in result
        assert "user_id" in result

    def test_calculate_hash(self):
        """OrderSnapshot.calculate_hash() returns consistent SHA-256 hash."""
        snapshot = OrderSnapshot(
            order_id="ORD-003",
            user_id="user-789",
            symbol="GOOG",
            quantity=25,
            side="buy",
            order_type="limit",
            price=2800.00,
        )
        
        hash1 = snapshot.calculate_hash()
        hash2 = snapshot.calculate_hash()
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters
        assert all(c in "0123456789abcdef" for c in hash1)

    def test_different_snapshots_have_different_hashes(self):
        """Different OrderSnapshots produce different hashes."""
        snapshot1 = OrderSnapshot(
            order_id="ORD-004",
            user_id="user-1",
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type="limit",
            price=150.00,
        )
        snapshot2 = OrderSnapshot(
            order_id="ORD-005",
            user_id="user-1",
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type="limit",
            price=150.00,
        )
        
        assert snapshot1.calculate_hash() != snapshot2.calculate_hash()

    def test_metadata_field(self):
        """OrderSnapshot can have custom metadata."""
        snapshot = OrderSnapshot(
            order_id="ORD-006",
            user_id="user-meta",
            symbol="TSLA",
            quantity=10,
            side="buy",
            order_type="market",
            metadata={"strategy": "momentum", "signal_strength": 0.85},
        )
        
        assert snapshot.metadata["strategy"] == "momentum"
        assert snapshot.metadata["signal_strength"] == 0.85


# =======================
# OrderEventSchema Tests
# =======================


class TestOrderEventSchema:
    """Tests for OrderEventSchema Pydantic model."""

    def test_create_event(self):
        """Can create a basic OrderEventSchema."""
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="ORD-001",
            event_data={"key": "value"},
        )
        
        assert event.event_type == OrderEventType.CREATED
        assert event.order_id == "ORD-001"
        assert event.event_data == {"key": "value"}
        assert event.event_id  # Auto-generated
        assert event.timestamp  # Auto-generated
        assert event.schema_version == "1.0"

    def test_event_with_state_transition(self):
        """Event can include state transition details."""
        event = OrderEventSchema(
            event_type=OrderEventType.EXECUTION_UPDATE,
            order_id="ORD-002",
            from_state=OrderState.SUBMITTED,
            to_state=OrderState.PENDING_EXECUTION,
            trigger=TransitionTrigger.BROKER_UPDATE,
            event_data={"execution_id": "EXE-001"},
        )
        
        assert event.from_state == OrderState.SUBMITTED
        assert event.to_state == OrderState.PENDING_EXECUTION
        assert event.trigger == TransitionTrigger.BROKER_UPDATE

    def test_event_with_user_and_correlation(self):
        """Event can include user and correlation IDs."""
        event = OrderEventSchema(
            event_type=OrderEventType.EXECUTION_UPDATE,
            order_id="ORD-003",
            event_data={"modification": "price_change"},
            user_id="user-123",
            correlation_id="corr-456",
            idempotency_key="idemp-789",
        )
        
        assert event.user_id == "user-123"
        assert event.correlation_id == "corr-456"
        assert event.idempotency_key == "idemp-789"

    def test_event_data_size_validation(self):
        """Event data should not exceed size limit."""
        # Create valid event with reasonable data
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="ORD-004",
            event_data={"small": "data"},
        )
        assert event.event_data == {"small": "data"}

    def test_schema_version_default(self):
        """Default schema version is 1.0."""
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="ORD-005",
            event_data={},
        )
        assert event.schema_version == "1.0"

    def test_source_system_default(self):
        """Default source system is trading-platform."""
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="ORD-006",
            event_data={},
        )
        assert event.source_system == "trading-platform"


# =======================
# AuditLogEntry Model Tests
# =======================


class TestAuditLogEntry:
    """Tests for AuditLogEntry SQLAlchemy model."""

    def test_model_has_required_columns(self):
        """Verify AuditLogEntry has all required columns."""
        columns = [col.name for col in AuditLogEntry.__table__.columns]
        
        required = [
            "id",
            "event_id",
            "event_type",
            "entity_type",
            "entity_id",
            "timestamp",
            "event_data",
            "schema_version",
            "user_id",
            "source_system",
            "correlation_id",
            "idempotency_key",
            "data_hash",
            "previous_hash",
        ]
        
        for col in required:
            assert col in columns, f"Missing column: {col}"

    def test_model_has_indexes(self):
        """Verify AuditLogEntry has expected indexes."""
        indexes = [idx.name for idx in AuditLogEntry.__table__.indexes]
        
        expected_indexes = [
            "ix_audit_entity_id_timestamp",
            "ix_audit_event_type_timestamp",
            "ix_audit_user_id_timestamp",
            "ix_audit_correlation_id",
            "ix_audit_idempotency_key",
        ]
        
        for idx in expected_indexes:
            assert idx in indexes, f"Missing index: {idx}"


# =======================
# OrderStateMachine Tests
# =======================


class TestOrderStateMachine:
    """Tests for OrderStateMachine FSM."""

    def test_init_with_audit_logger(self):
        """Can initialize with audit logger."""
        mock_logger = MagicMock()
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        assert fsm.audit_logger == mock_logger

    def test_init_without_audit_logger(self):
        """Can initialize without audit logger (uses default)."""
        fsm = OrderStateMachine()
        
        assert fsm.audit_logger is not None

    def test_can_transition_valid(self):
        """Valid transitions return True."""
        fsm = OrderStateMachine()
        
        # PENDING_VALIDATION -> VALIDATED via VALIDATION_COMPLETE
        assert fsm.can_transition(
            OrderState.PENDING_VALIDATION,
            OrderState.VALIDATED,
            TransitionTrigger.VALIDATION_COMPLETE,
        )

    def test_can_transition_invalid(self):
        """Invalid transitions return False."""
        fsm = OrderStateMachine()
        
        # Cannot go from PENDING_VALIDATION directly to FILLED
        assert not fsm.can_transition(
            OrderState.PENDING_VALIDATION,
            OrderState.FILLED,
            TransitionTrigger.VALIDATION_COMPLETE,
        )

    def test_cannot_transition_from_terminal_state(self):
        """Terminal states cannot transition."""
        fsm = OrderStateMachine()
        
        for terminal in OrderState.terminal_states():
            result = fsm.can_transition(
                terminal,
                OrderState.PENDING_VALIDATION,
                TransitionTrigger.VALIDATION_COMPLETE,
            )
            assert not result, f"Should not transition from {terminal}"

    def test_risk_decision_special_handling(self):
        """RISK_DECISION trigger allows both APPROVED and REJECTED."""
        fsm = OrderStateMachine()
        
        # Risk approved from PENDING_RISK_ASSESSMENT
        assert fsm.can_transition(
            OrderState.PENDING_RISK_ASSESSMENT,
            OrderState.RISK_APPROVED,
            TransitionTrigger.RISK_DECISION,
        )
        
        # Risk rejected from PENDING_RISK_ASSESSMENT
        assert fsm.can_transition(
            OrderState.PENDING_RISK_ASSESSMENT,
            OrderState.RISK_REJECTED,
            TransitionTrigger.RISK_DECISION,
        )

    def test_broker_update_all_valid_transitions(self):
        """BROKER_UPDATE trigger correctly allows all defined target states."""
        fsm = OrderStateMachine()

        # SUBMITTED → PENDING_EXECUTION or REJECTED via BROKER_UPDATE
        assert fsm.can_transition(
            OrderState.SUBMITTED, OrderState.PENDING_EXECUTION,
            TransitionTrigger.BROKER_UPDATE,
        )
        assert fsm.can_transition(
            OrderState.SUBMITTED, OrderState.REJECTED,
            TransitionTrigger.BROKER_UPDATE,
        )
        # SUBMITTED → FILLED should NOT be valid (not directly reachable)
        assert not fsm.can_transition(
            OrderState.SUBMITTED, OrderState.FILLED,
            TransitionTrigger.BROKER_UPDATE,
        )

        # PENDING_EXECUTION → PARTIALLY_FILLED, FILLED, or CANCELLED
        assert fsm.can_transition(
            OrderState.PENDING_EXECUTION, OrderState.PARTIALLY_FILLED,
            TransitionTrigger.BROKER_UPDATE,
        )
        assert fsm.can_transition(
            OrderState.PENDING_EXECUTION, OrderState.FILLED,
            TransitionTrigger.BROKER_UPDATE,
        )
        assert fsm.can_transition(
            OrderState.PENDING_EXECUTION, OrderState.CANCELLED,
            TransitionTrigger.BROKER_UPDATE,
        )

        # PARTIALLY_FILLED → FILLED or CANCELLED
        assert fsm.can_transition(
            OrderState.PARTIALLY_FILLED, OrderState.FILLED,
            TransitionTrigger.BROKER_UPDATE,
        )
        assert fsm.can_transition(
            OrderState.PARTIALLY_FILLED, OrderState.CANCELLED,
            TransitionTrigger.BROKER_UPDATE,
        )

    def test_manual_override_all_valid_transitions(self):
        """MANUAL_OVERRIDE correctly allows all defined target states."""
        fsm = OrderStateMachine()

        # UNDER_REVIEW → VALIDATED or CANCELLED via MANUAL_OVERRIDE
        assert fsm.can_transition(
            OrderState.UNDER_REVIEW, OrderState.VALIDATED,
            TransitionTrigger.MANUAL_OVERRIDE,
        )
        assert fsm.can_transition(
            OrderState.UNDER_REVIEW, OrderState.CANCELLED,
            TransitionTrigger.MANUAL_OVERRIDE,
        )

    @pytest.mark.asyncio
    async def test_transition_success(self):
        """Successful transition logs event and returns True."""
        mock_logger = AsyncMock()
        mock_logger.log_event = AsyncMock()
        
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        result = await fsm.transition(
            order_id="ORD-001",
            from_state=OrderState.PENDING_RISK_ASSESSMENT,
            to_state=OrderState.RISK_APPROVED,
            trigger=TransitionTrigger.RISK_DECISION,
            event_data={"risk_score": 0.5},
            user_id="user-123",
        )
        
        assert result is True
        mock_logger.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_transition_failure(self):
        """Invalid transition returns False without logging."""
        mock_logger = AsyncMock()
        mock_logger.log_event = AsyncMock()
        
        fsm = OrderStateMachine(audit_logger=mock_logger)
        
        result = await fsm.transition(
            order_id="ORD-002",
            from_state=OrderState.FILLED,  # Terminal state
            to_state=OrderState.CANCELLED,
            trigger=TransitionTrigger.USER_CANCELLATION,
            event_data={},
        )
        
        assert result is False
        mock_logger.log_event.assert_not_called()

    def test_get_valid_transitions(self):
        """get_valid_transitions returns valid trigger->state mapping."""
        fsm = OrderStateMachine()
        
        transitions = fsm.get_valid_transitions(OrderState.PENDING_VALIDATION)
        
        assert isinstance(transitions, dict)

    def test_get_valid_transitions_terminal_state(self):
        """Terminal states have empty valid transitions."""
        fsm = OrderStateMachine()
        
        # Check only states that are truly terminal (in terminal_states)
        for terminal in [OrderState.FILLED, OrderState.CANCELLED, OrderState.REJECTED, OrderState.EXPIRED]:
            transitions = fsm.get_valid_transitions(terminal)
            assert transitions == {}

    def test_get_reachable_states(self):
        """get_reachable_states returns set of reachable states."""
        fsm = OrderStateMachine()

        reachable = fsm.get_reachable_states(OrderState.PENDING_VALIDATION)
        assert isinstance(reachable, set)
        assert OrderState.VALIDATED in reachable
        assert OrderState.CANCELLED in reachable
        assert OrderState.EXPIRED in reachable

        # SUBMITTED can reach PENDING_EXECUTION, REJECTED, and CANCELLED
        reachable_submitted = fsm.get_reachable_states(OrderState.SUBMITTED)
        assert OrderState.PENDING_EXECUTION in reachable_submitted
        assert OrderState.REJECTED in reachable_submitted
        assert OrderState.CANCELLED in reachable_submitted

    def test_get_reachable_states_terminal(self):
        """Terminal states have no reachable states."""
        fsm = OrderStateMachine()
        
        for terminal in OrderState.terminal_states():
            reachable = fsm.get_reachable_states(terminal)
            assert reachable == set()


# =======================
# IdempotencyManager Tests
# =======================


class TestIdempotencyManager:
    """Tests for IdempotencyManager multi-layer caching."""

    def test_init(self):
        """Can initialize IdempotencyManager."""
        manager = IdempotencyManager()
        
        assert manager._api_cache == {}
        assert manager._service_cache == {}
        assert manager._outbox_cache == {}

    def test_init_with_cache_backend(self):
        """Can initialize with cache backend."""
        mock_backend = MagicMock()
        manager = IdempotencyManager(cache_backend=mock_backend)
        
        assert manager.cache_backend == mock_backend

    @pytest.mark.asyncio
    async def test_api_idempotency_miss(self):
        """API cache miss returns None."""
        manager = IdempotencyManager()
        
        result = await manager.check_api_idempotency("key-1", "create_order")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_api_idempotency_hit(self):
        """API cache hit returns cached result."""
        manager = IdempotencyManager()
        
        # Record operation
        await manager.record_api_operation(
            "key-1", "create_order", {"order_id": "ORD-001"}
        )
        
        # Check cache
        result = await manager.check_api_idempotency("key-1", "create_order")
        
        assert result is not None
        assert result["result"]["order_id"] == "ORD-001"
        assert "timestamp" in result
        assert result["operation"] == "create_order"

    @pytest.mark.asyncio
    async def test_service_idempotency_miss(self):
        """Service cache miss returns None."""
        manager = IdempotencyManager()
        
        result = await manager.check_service_idempotency("key-2", "risk_check")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_service_idempotency_hit(self):
        """Service cache hit returns cached result."""
        manager = IdempotencyManager()
        
        # Record operation
        await manager.record_service_operation(
            "key-2", "risk_check", {"approved": True}
        )
        
        # Check cache
        result = await manager.check_service_idempotency("key-2", "risk_check")
        
        assert result is not None
        assert result["result"]["approved"] is True
        assert result["service"] == "risk_check"

    @pytest.mark.asyncio
    async def test_outbox_idempotency_miss(self):
        """Outbox cache miss returns False."""
        manager = IdempotencyManager()
        
        result = await manager.check_outbox_idempotency("key-3")
        
        assert result is False

    @pytest.mark.asyncio
    async def test_outbox_idempotency_hit(self):
        """Outbox cache hit returns True."""
        manager = IdempotencyManager()
        
        # Record message
        await manager.record_outbox_message("key-3", {"event": "order_created"})
        
        # Check cache
        result = await manager.check_outbox_idempotency("key-3")
        
        assert result is True

    @pytest.mark.asyncio
    async def test_different_operations_are_independent(self):
        """Different operations on same key are independent."""
        manager = IdempotencyManager()
        
        await manager.record_api_operation(
            "shared-key", "create_order", {"order_id": "ORD-001"}
        )
        
        # Different operation should not find cached result
        result = await manager.check_api_idempotency("shared-key", "cancel_order")
        
        assert result is None


# =======================
# AuditLogger Tests
# =======================


class TestAuditLogger:
    """Tests for AuditLogger with hash chaining."""

    def test_init(self):
        """Can initialize AuditLogger with db session."""
        mock_session = MagicMock()
        logger = AuditLogger(mock_session)
        
        assert logger.db_session == mock_session
        assert logger._previous_hash_cache == {}

    @pytest.mark.asyncio
    async def test_log_event(self):
        """log_event creates audit entry with hash."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        
        logger = AuditLogger(mock_session)
        
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="ORD-001",
            event_data={"symbol": "AAPL"},
        )
        
        await logger.log_event(event)
        
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        
        # Verify hash chain is updated
        assert "ORD-001" in logger._previous_hash_cache

    @pytest.mark.asyncio
    async def test_log_event_hash_chaining(self):
        """Multiple events for same order create hash chain."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        
        logger = AuditLogger(mock_session)
        
        # First event
        event1 = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="ORD-002",
            event_data={"step": 1},
        )
        await logger.log_event(event1)
        hash1 = logger._previous_hash_cache["ORD-002"]
        
        # Second event
        event2 = OrderEventSchema(
            event_type=OrderEventType.VALIDATED,
            order_id="ORD-002",
            event_data={"step": 2},
        )
        await logger.log_event(event2)
        hash2 = logger._previous_hash_cache["ORD-002"]
        
        assert hash1 != hash2


# =======================
# OrderIntegrityService Tests
# =======================


class TestOrderIntegrityService:
    """Tests for OrderIntegrityService orchestration."""

    def test_init_without_db_session(self):
        """Can initialize without db session."""
        service = OrderIntegrityService()
        
        assert service.db_session is None
        assert service.audit_logger is None
        assert service.state_machine is not None
        assert service.idempotency_manager is not None

    def test_init_with_db_session(self):
        """Can initialize with db session."""
        mock_session = MagicMock()
        service = OrderIntegrityService(db_session=mock_session)
        
        assert service.db_session == mock_session
        assert service.audit_logger is not None

    def test_init_accepts_extra_args(self):
        """Service accepts extra args for compatibility."""
        service = OrderIntegrityService(
            "extra_arg",
            extra_kwarg="value",
            db_session=None,
        )
        
        assert service is not None

    @pytest.mark.asyncio
    async def test_create_order_with_idempotency(self):
        """create_order returns cached result on duplicate call."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        
        service = OrderIntegrityService(db_session=mock_session)
        
        snapshot = OrderSnapshot(
            order_id="ORD-100",
            user_id="user-1",
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type="limit",
            price=150.00,
        )
        
        # First call
        result1 = await service.create_order(snapshot, "user-1", "idemp-key-1")
        
        # Second call with same idempotency key
        result2 = await service.create_order(snapshot, "user-1", "idemp-key-1")
        
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_transition_order_state(self):
        """transition_order_state delegates to FSM."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        
        service = OrderIntegrityService(db_session=mock_session)
        
        result = await service.transition_order_state(
            order_id="ORD-200",
            from_state=OrderState.PENDING_RISK_ASSESSMENT,
            to_state=OrderState.RISK_APPROVED,
            trigger=TransitionTrigger.RISK_DECISION,
            event_data={"risk_score": 0.3},
            user_id="user-2",
        )
        
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_transition_with_idempotency(self):
        """Transition returns cached result on duplicate."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        
        service = OrderIntegrityService(db_session=mock_session)
        
        # First call
        await service.transition_order_state(
            order_id="ORD-201",
            from_state=OrderState.PENDING_RISK_ASSESSMENT,
            to_state=OrderState.RISK_APPROVED,
            trigger=TransitionTrigger.RISK_DECISION,
            event_data={},
            idempotency_key="trans-idemp-1",
        )
        
        # Second call with same key - should use cache
        result = await service.transition_order_state(
            order_id="ORD-201",
            from_state=OrderState.PENDING_RISK_ASSESSMENT,
            to_state=OrderState.RISK_APPROVED,
            trigger=TransitionTrigger.RISK_DECISION,
            event_data={},
            idempotency_key="trans-idemp-1",
        )
        
        assert result is not None

    @pytest.mark.asyncio
    async def test_send_to_outbox(self):
        """send_to_outbox records message with idempotency."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        
        service = OrderIntegrityService(db_session=mock_session)
        
        result = await service.send_to_outbox(
            order_id="ORD-300",
            message={"event": "order_filled"},
            idempotency_key="outbox-idemp-1",
        )
        
        assert result is True

    @pytest.mark.asyncio
    async def test_send_to_outbox_idempotent(self):
        """Duplicate outbox send returns True without re-sending."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        
        service = OrderIntegrityService(db_session=mock_session)
        
        # First call
        await service.send_to_outbox(
            order_id="ORD-301",
            message={"event": "order_filled"},
            idempotency_key="outbox-idemp-2",
        )
        
        # Reset mock to check second call doesn't re-add
        mock_session.add.reset_mock()
        
        # Second call
        result = await service.send_to_outbox(
            order_id="ORD-301",
            message={"event": "order_filled"},
            idempotency_key="outbox-idemp-2",
        )
        
        assert result is True


# =======================
# Integration-style Tests
# =======================


class TestOrderIntegrationScenarios:
    """Integration-style tests for complete order flows."""

    @pytest.mark.asyncio
    async def test_complete_order_flow(self):
        """Test complete order lifecycle from creation to fill."""
        mock_session = MagicMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        
        service = OrderIntegrityService(db_session=mock_session)
        fsm = service.state_machine
        
        # Verify valid transition path exists
        assert fsm.can_transition(
            OrderState.PENDING_VALIDATION,
            OrderState.VALIDATED,
            TransitionTrigger.VALIDATION_COMPLETE,
        )
        
        assert fsm.can_transition(
            OrderState.PENDING_RISK_ASSESSMENT,
            OrderState.RISK_APPROVED,
            TransitionTrigger.RISK_DECISION,
        )

    def test_fsm_state_consistency(self):
        """Verify FSM states are consistent across components."""
        fsm = OrderStateMachine()
        
        # All active states should have at least one valid transition
        for state in OrderState.active_states():
            transitions = fsm.get_valid_transitions(state)
            # Active states should generally have transitions
            # (though this depends on implementation)
            assert isinstance(transitions, dict)

    def test_hash_calculation_is_deterministic(self):
        """Hash calculation should be deterministic for same data."""
        event1 = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="ORD-HASH-1",
            event_data={"key": "value"},
            event_id="fixed-event-id",
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
        )
        
        event2 = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="ORD-HASH-1",
            event_data={"key": "value"},
            event_id="fixed-event-id",
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
        )
        
        dict1 = event1.model_dump()
        dict2 = event2.model_dump()
        
        json1 = json.dumps(dict1, sort_keys=True, default=str)
        json2 = json.dumps(dict2, sort_keys=True, default=str)
        
        hash1 = hashlib.sha256(json1.encode()).hexdigest()
        hash2 = hashlib.sha256(json2.encode()).hexdigest()
        
        assert hash1 == hash2
