"""
Comprehensive test suite for backend.models.order_integrity module.

This module has 755+ lines with complex order state management, FSM, audit logging,
and idempotency features. Focus on achieving high coverage across all components:

- OrderState enum and state management
- OrderStateMachine with transition validation  
- OrderSnapshot data structures
- OrderEventSchema validation
- AuditLogEntry database models
- IdempotencyManager functionality
- Event publishing and integrity verification
"""

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json
import logging
import pytest
from unittest.mock import AsyncMock, Mock, patch
import uuid

# Test environment setup
import os
os.environ['DISABLE_ML'] = '1'
os.environ['PYTEST_RUNNING'] = '1'

# Import the module under test
from backend.models.order_integrity import (
    OrderState,
    OrderEventType,
    TransitionTrigger,
    VALID_TRANSITIONS,
    OrderSnapshot,
    OrderEventSchema,
    AuditLogEntry,
    OrderStateMachine,
    order_state_transitions,
    order_integrity_violations,
    audit_log_entries,
    idempotency_cache_hits,
    order_processing_duration,
)


class TestOrderState:
    """Test OrderState enum and its class methods."""

    def test_all_states_defined(self):
        """Test that all expected order states are defined."""
        expected_states = {
            'PENDING_VALIDATION', 'VALIDATED', 'PENDING_RISK_ASSESSMENT',
            'RISK_APPROVED', 'RISK_REJECTED', 'PENDING_SUBMISSION',
            'SUBMITTED', 'PENDING_EXECUTION', 'PARTIALLY_FILLED',
            'FILLED', 'CANCELLED', 'REJECTED', 'EXPIRED', 'FAILED',
            'PENDING_RETRY', 'UNDER_REVIEW'
        }
        
        actual_states = {state.name for state in OrderState}
        assert actual_states == expected_states

    def test_terminal_states(self):
        """Test terminal_states class method."""
        terminal = OrderState.terminal_states()
        expected = {
            OrderState.FILLED, OrderState.CANCELLED, 
            OrderState.REJECTED, OrderState.EXPIRED, OrderState.FAILED
        }
        assert terminal == expected

    def test_active_states(self):
        """Test active_states class method."""
        active = OrderState.active_states()
        expected = {
            OrderState.VALIDATED, OrderState.RISK_APPROVED,
            OrderState.PENDING_SUBMISSION, OrderState.SUBMITTED,
            OrderState.PENDING_EXECUTION, OrderState.PARTIALLY_FILLED
        }
        assert active == expected

    def test_state_enum_values(self):
        """Test that state enum values are properly defined."""
        assert OrderState.PENDING_VALIDATION.value == "pending_validation"
        assert OrderState.FILLED.value == "filled"
        assert OrderState.CANCELLED.value == "cancelled"

    def test_terminal_states_immutable(self):
        """Test that terminal states set is immutable."""
        terminal = OrderState.terminal_states()
        original_size = len(terminal)
        
        # Try to modify (should not affect original)
        terminal.add(OrderState.VALIDATED)
        assert len(OrderState.terminal_states()) == original_size

    def test_active_states_immutable(self):
        """Test that active states set is immutable."""
        active = OrderState.active_states()
        original_size = len(active)
        
        # Try to modify (should not affect original)
        active.add(OrderState.FAILED)
        assert len(OrderState.active_states()) == original_size


class TestOrderEventType:
    """Test OrderEventType enum."""

    def test_all_event_types_defined(self):
        """Test that all expected event types are defined."""
        expected_types = {
            'CREATED', 'VALIDATED', 'RISK_ASSESSED', 'SUBMITTED',
            'EXECUTION_UPDATE', 'FILLED', 'CANCELLED', 'REJECTED',
            'FAILED', 'RETRY_SCHEDULED', 'MANUAL_INTERVENTION'
        }
        
        actual_types = {event.name for event in OrderEventType}
        assert actual_types == expected_types

    def test_event_type_values(self):
        """Test event type enum values."""
        assert OrderEventType.CREATED.value == "created"
        assert OrderEventType.FILLED.value == "filled"
        assert OrderEventType.MANUAL_INTERVENTION.value == "manual_intervention"


class TestTransitionTrigger:
    """Test TransitionTrigger enum."""

    def test_all_triggers_defined(self):
        """Test that all expected triggers are defined."""
        expected_triggers = {
            'VALIDATION_COMPLETE', 'RISK_DECISION', 'BROKER_SUBMISSION',
            'BROKER_UPDATE', 'USER_CANCELLATION', 'SYSTEM_TIMEOUT',
            'ERROR_RECOVERY', 'MANUAL_OVERRIDE'
        }
        
        actual_triggers = {trigger.name for trigger in TransitionTrigger}
        assert actual_triggers == expected_triggers

    def test_trigger_values(self):
        """Test trigger enum values."""
        assert TransitionTrigger.VALIDATION_COMPLETE.value == "validation_complete"
        assert TransitionTrigger.RISK_DECISION.value == "risk_decision"
        assert TransitionTrigger.MANUAL_OVERRIDE.value == "manual_override"


class TestValidTransitions:
    """Test VALID_TRANSITIONS mapping."""

    def test_transitions_mapping_structure(self):
        """Test that VALID_TRANSITIONS has proper structure."""
        assert isinstance(VALID_TRANSITIONS, dict)
        
        for from_state, triggers in VALID_TRANSITIONS.items():
            assert isinstance(from_state, OrderState)
            assert isinstance(triggers, dict)
            
            for trigger, to_state in triggers.items():
                assert isinstance(trigger, TransitionTrigger)
                assert isinstance(to_state, OrderState)

    def test_pending_validation_transitions(self):
        """Test transitions from PENDING_VALIDATION state."""
        transitions = VALID_TRANSITIONS[OrderState.PENDING_VALIDATION]
        
        assert TransitionTrigger.VALIDATION_COMPLETE in transitions
        assert transitions[TransitionTrigger.VALIDATION_COMPLETE] == OrderState.VALIDATED
        
        assert TransitionTrigger.USER_CANCELLATION in transitions
        assert transitions[TransitionTrigger.USER_CANCELLATION] == OrderState.CANCELLED

    def test_terminal_states_limited_transitions(self):
        """Test that most terminal states have limited or no outgoing transitions."""
        terminal_states = OrderState.terminal_states()
        
        # Most terminal states should have no transitions
        truly_terminal = {
            OrderState.FILLED, OrderState.CANCELLED, 
            OrderState.REJECTED, OrderState.EXPIRED
        }
        
        for terminal_state in truly_terminal:
            if terminal_state in VALID_TRANSITIONS:
                assert len(VALID_TRANSITIONS[terminal_state]) == 0
        
        # FAILED state may have recovery transitions
        if OrderState.FAILED in VALID_TRANSITIONS:
            failed_transitions = VALID_TRANSITIONS[OrderState.FAILED]
            # Should only have recovery-related transitions
            for trigger in failed_transitions.keys():
                assert trigger in [TransitionTrigger.ERROR_RECOVERY, TransitionTrigger.MANUAL_OVERRIDE]

    def test_risk_decision_transitions(self):
        """Test risk decision transitions."""
        risk_pending = VALID_TRANSITIONS[OrderState.PENDING_RISK_ASSESSMENT]
        
        # Should support risk decisions
        assert TransitionTrigger.RISK_DECISION in risk_pending

    def test_broker_update_transitions(self):
        """Test broker update transitions."""
        submitted = VALID_TRANSITIONS[OrderState.SUBMITTED]
        
        # Should support broker updates
        assert TransitionTrigger.BROKER_UPDATE in submitted


class TestOrderSnapshot:
    """Test OrderSnapshot dataclass."""

    def test_basic_creation(self):
        """Test basic order snapshot creation."""
        snapshot = OrderSnapshot(
            order_id="test-123",
            user_id="user-456",
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type="market"
        )
        
        assert snapshot.order_id == "test-123"
        assert snapshot.user_id == "user-456"
        assert snapshot.symbol == "AAPL"
        assert snapshot.quantity == 100
        assert snapshot.side == "buy"
        assert snapshot.order_type == "market"
        assert snapshot.time_in_force == "day"  # default

    def test_creation_with_optional_fields(self):
        """Test order snapshot creation with optional fields."""
        metadata = {"source": "api", "version": "1.0"}
        
        snapshot = OrderSnapshot(
            order_id="test-123",
            user_id="user-456",
            symbol="GOOGL",
            quantity=50,
            side="sell",
            order_type="limit",
            price=2500.0,
            time_in_force="gtc",
            metadata=metadata
        )
        
        assert snapshot.price == 2500.0
        assert snapshot.time_in_force == "gtc"
        assert snapshot.metadata == metadata

    def test_created_at_default(self):
        """Test that created_at gets a default UTC timestamp."""
        before = datetime.now(UTC)
        
        snapshot = OrderSnapshot(
            order_id="test-123",
            user_id="user-456",
            symbol="TSLA",
            quantity=10,
            side="buy",
            order_type="market"
        )
        
        after = datetime.now(UTC)
        
        assert before <= snapshot.created_at <= after
        assert snapshot.created_at.tzinfo == UTC

    def test_to_dict(self):
        """Test converting snapshot to dictionary."""
        metadata = {"risk_score": 0.7}
        
        snapshot = OrderSnapshot(
            order_id="test-123",
            user_id="user-456",
            symbol="MSFT",
            quantity=200,
            side="buy",
            order_type="limit",
            price=300.0,
            metadata=metadata
        )
        
        data = snapshot.to_dict()
        
        assert data["order_id"] == "test-123"
        assert data["symbol"] == "MSFT"
        assert data["quantity"] == 200
        assert data["price"] == 300.0
        assert data["metadata"] == metadata
        assert isinstance(data["created_at"], str)  # Should be ISO format

    def test_calculate_hash(self):
        """Test hash calculation for integrity verification."""
        snapshot = OrderSnapshot(
            order_id="test-123",
            user_id="user-456",
            symbol="NVDA",
            quantity=75,
            side="sell",
            order_type="market"
        )
        
        hash1 = snapshot.calculate_hash()
        hash2 = snapshot.calculate_hash()
        
        # Same snapshot should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length
        assert all(c in '0123456789abcdef' for c in hash1)

    def test_hash_changes_with_data(self):
        """Test that hash changes when data changes."""
        snapshot1 = OrderSnapshot(
            order_id="test-123",
            user_id="user-456",
            symbol="AMD",
            quantity=100,
            side="buy",
            order_type="market"
        )
        
        snapshot2 = OrderSnapshot(
            order_id="test-123",
            user_id="user-456",
            symbol="AMD",
            quantity=101,  # Different quantity
            side="buy",
            order_type="market"
        )
        
        assert snapshot1.calculate_hash() != snapshot2.calculate_hash()

    def test_empty_metadata_default(self):
        """Test that metadata defaults to empty dict."""
        snapshot = OrderSnapshot(
            order_id="test-123",
            user_id="user-456",
            symbol="INTC",
            quantity=150,
            side="buy",
            order_type="market"
        )
        
        assert snapshot.metadata == {}


class TestOrderEventSchema:
    """Test OrderEventSchema Pydantic model."""

    def test_basic_event_creation(self):
        """Test basic event schema creation."""
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="order-123"
        )
        
        assert event.event_type == OrderEventType.CREATED
        assert event.order_id == "order-123"
        assert event.schema_version == "1.0"  # default
        assert isinstance(event.event_id, str)
        assert len(event.event_id) > 0

    def test_event_with_state_transition(self):
        """Test event with state transition information."""
        event = OrderEventSchema(
            event_type=OrderEventType.VALIDATED,
            order_id="order-123",
            from_state=OrderState.PENDING_VALIDATION,
            to_state=OrderState.VALIDATED,
            trigger=TransitionTrigger.VALIDATION_COMPLETE
        )
        
        assert event.from_state == OrderState.PENDING_VALIDATION
        assert event.to_state == OrderState.VALIDATED
        assert event.trigger == TransitionTrigger.VALIDATION_COMPLETE

    def test_event_with_all_fields(self):
        """Test event with all optional fields."""
        event_data = {"validation_result": "passed", "score": 0.95}
        
        event = OrderEventSchema(
            event_type=OrderEventType.RISK_ASSESSED,
            order_id="order-456",
            event_data=event_data,
            user_id="user-789",
            source_system="risk-engine",
            idempotency_key="idem-123",
            parent_event_id="parent-456",
            correlation_id="corr-789"
        )
        
        assert event.event_data == event_data
        assert event.user_id == "user-789"
        assert event.source_system == "risk-engine"
        assert event.idempotency_key == "idem-123"
        assert event.parent_event_id == "parent-456"
        assert event.correlation_id == "corr-789"

    def test_timestamp_default(self):
        """Test that timestamp gets a default UTC value."""
        before = datetime.now(UTC)
        
        event = OrderEventSchema(
            event_type=OrderEventType.SUBMITTED,
            order_id="order-789"
        )
        
        after = datetime.now(UTC)
        
        assert before <= event.timestamp <= after

    def test_schema_version_validation(self):
        """Test schema version validation."""
        # Valid versions should work
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="order-123",
            schema_version="2.1"
        )
        assert event.schema_version == "2.1"
        
        # Invalid versions should raise error
        with pytest.raises(ValueError, match="Schema version must be in format"):
            OrderEventSchema(
                event_type=OrderEventType.CREATED,
                order_id="order-123",
                schema_version="invalid"
            )

    def test_event_data_size_validation(self):
        """Test event data size validation."""
        # Small event data should work
        small_data = {"key": "value"}
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="order-123",
            event_data=small_data
        )
        assert event.event_data == small_data
        
        # Large event data should raise error
        large_data = {"large_field": "x" * 15000}  # Over 10KB
        with pytest.raises(ValueError, match="Event data exceeds maximum size"):
            OrderEventSchema(
                event_type=OrderEventType.CREATED,
                order_id="order-123",
                event_data=large_data
            )

    def test_extra_fields_forbidden(self):
        """Test that extra fields are forbidden."""
        with pytest.raises(ValueError):
            OrderEventSchema(
                event_type=OrderEventType.CREATED,
                order_id="order-123",
                invalid_field="should_fail"
            )

    def test_event_id_uniqueness(self):
        """Test that event IDs are unique."""
        event1 = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="order-123"
        )
        
        event2 = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="order-123"
        )
        
        assert event1.event_id != event2.event_id


class TestOrderStateMachine:
    """Test OrderStateMachine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.audit_logger = Mock()
        self.fsm = OrderStateMachine(audit_logger=self.audit_logger)

    def test_init_with_audit_logger(self):
        """Test initialization with audit logger."""
        logger = Mock()
        fsm = OrderStateMachine(audit_logger=logger)
        assert fsm.audit_logger == logger

    def test_init_without_audit_logger(self):
        """Test initialization without audit logger."""
        fsm = OrderStateMachine()
        # Should have a no-op function
        fsm.audit_logger("test")  # Should not raise error

    def test_init_tolerant_args(self):
        """Test initialization accepts arbitrary args and kwargs."""
        # Should not raise error with extra arguments
        fsm = OrderStateMachine(
            "extra_arg", 
            audit_logger=self.audit_logger,
            extra_kwarg="value"
        )
        assert fsm.audit_logger == self.audit_logger

    def test_can_transition_valid_basic(self):
        """Test valid basic state transitions."""
        # Valid transition
        result = self.fsm.can_transition(
            OrderState.PENDING_VALIDATION,
            OrderState.VALIDATED,
            TransitionTrigger.VALIDATION_COMPLETE
        )
        assert result is True

    def test_can_transition_terminal_states(self):
        """Test that terminal states cannot transition."""
        for terminal_state in OrderState.terminal_states():
            result = self.fsm.can_transition(
                terminal_state,
                OrderState.VALIDATED,
                TransitionTrigger.VALIDATION_COMPLETE
            )
            assert result is False

    def test_can_transition_risk_decision_approved(self):
        """Test risk decision transition to approved."""
        result = self.fsm.can_transition(
            OrderState.PENDING_RISK_ASSESSMENT,
            OrderState.RISK_APPROVED,
            TransitionTrigger.RISK_DECISION
        )
        assert result is True

    def test_can_transition_risk_decision_rejected(self):
        """Test risk decision transition to rejected."""
        result = self.fsm.can_transition(
            OrderState.PENDING_RISK_ASSESSMENT,
            OrderState.RISK_REJECTED,
            TransitionTrigger.RISK_DECISION
        )
        assert result is True

    def test_can_transition_risk_decision_invalid(self):
        """Test invalid risk decision transition."""
        result = self.fsm.can_transition(
            OrderState.PENDING_RISK_ASSESSMENT,
            OrderState.FILLED,  # Invalid target for risk decision
            TransitionTrigger.RISK_DECISION
        )
        assert result is False

    def test_can_transition_invalid_from_state(self):
        """Test transition from invalid state."""
        result = self.fsm.can_transition(
            OrderState.FILLED,  # Terminal state
            OrderState.CANCELLED,
            TransitionTrigger.USER_CANCELLATION
        )
        assert result is False

    def test_can_transition_undefined_transition(self):
        """Test undefined state transition."""
        result = self.fsm.can_transition(
            OrderState.VALIDATED,
            OrderState.FILLED,  # No direct path
            TransitionTrigger.VALIDATION_COMPLETE
        )
        assert result is False


@pytest.fixture
def sample_order_snapshot():
    """Sample order snapshot for testing."""
    return OrderSnapshot(
        order_id="test-order-123",
        user_id="user-456",
        symbol="AAPL",
        quantity=100,
        side="buy",
        order_type="market",
        metadata={"source": "api"}
    )


@pytest.fixture  
def sample_event_schema():
    """Sample event schema for testing."""
    return OrderEventSchema(
        event_type=OrderEventType.CREATED,
        order_id="test-order-123",
        user_id="user-456",
        event_data={"initial_data": "test"}
    )


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple components."""

    def test_complete_order_lifecycle_states(self):
        """Test complete order lifecycle through states."""
        fsm = OrderStateMachine()
        
        # Order creation -> validation
        assert fsm.can_transition(
            OrderState.PENDING_VALIDATION,
            OrderState.VALIDATED,
            TransitionTrigger.VALIDATION_COMPLETE
        )
        
        # Risk assessment from pending risk assessment (not from validated)
        assert fsm.can_transition(
            OrderState.PENDING_RISK_ASSESSMENT,
            OrderState.RISK_APPROVED,
            TransitionTrigger.RISK_DECISION
        )
        
        assert fsm.can_transition(
            OrderState.PENDING_RISK_ASSESSMENT,
            OrderState.RISK_REJECTED,
            TransitionTrigger.RISK_DECISION
        )
        
        # Submission after risk approval
        assert fsm.can_transition(
            OrderState.RISK_APPROVED,
            OrderState.PENDING_SUBMISSION,
            TransitionTrigger.BROKER_SUBMISSION
        )
        
        # Broker acceptance
        assert fsm.can_transition(
            OrderState.PENDING_SUBMISSION,
            OrderState.SUBMITTED,
            TransitionTrigger.BROKER_SUBMISSION
        )

    def test_order_snapshot_to_event_workflow(self, sample_order_snapshot):
        """Test workflow from order snapshot to event creation."""
        # Create event from snapshot
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id=sample_order_snapshot.order_id,
            user_id=sample_order_snapshot.user_id,
            event_data=sample_order_snapshot.to_dict()
        )
        
        assert event.order_id == sample_order_snapshot.order_id
        assert event.user_id == sample_order_snapshot.user_id
        assert event.event_data["symbol"] == sample_order_snapshot.symbol
        assert event.event_data["quantity"] == sample_order_snapshot.quantity

    def test_hash_integrity_verification(self, sample_order_snapshot):
        """Test hash-based integrity verification."""
        # Get initial hash
        hash1 = sample_order_snapshot.calculate_hash()
        
        # Create copy with same data
        copy_snapshot = OrderSnapshot(
            order_id=sample_order_snapshot.order_id,
            user_id=sample_order_snapshot.user_id,
            symbol=sample_order_snapshot.symbol,
            quantity=sample_order_snapshot.quantity,
            side=sample_order_snapshot.side,
            order_type=sample_order_snapshot.order_type,
            metadata=sample_order_snapshot.metadata.copy(),
            created_at=sample_order_snapshot.created_at
        )
        
        hash2 = copy_snapshot.calculate_hash()
        assert hash1 == hash2  # Same data = same hash
        
        # Modify copy
        copy_snapshot.quantity = 200
        hash3 = copy_snapshot.calculate_hash()
        assert hash1 != hash3  # Different data = different hash

    def test_state_machine_with_cancellation_paths(self):
        """Test various cancellation paths through state machine."""
        fsm = OrderStateMachine()
        
        # Can cancel from pending validation
        assert fsm.can_transition(
            OrderState.PENDING_VALIDATION,
            OrderState.CANCELLED,
            TransitionTrigger.USER_CANCELLATION
        )
        
        # Can cancel from validated
        assert fsm.can_transition(
            OrderState.VALIDATED,
            OrderState.CANCELLED,
            TransitionTrigger.USER_CANCELLATION
        )
        
        # Can cancel from risk approved
        assert fsm.can_transition(
            OrderState.RISK_APPROVED,
            OrderState.CANCELLED,
            TransitionTrigger.USER_CANCELLATION
        )

    def test_event_schema_state_transition_recording(self):
        """Test recording state transitions in event schema."""
        event = OrderEventSchema(
            event_type=OrderEventType.VALIDATED,
            order_id="order-123",
            from_state=OrderState.PENDING_VALIDATION,
            to_state=OrderState.VALIDATED,
            trigger=TransitionTrigger.VALIDATION_COMPLETE,
            event_data={"validation_details": "passed all checks"}
        )
        
        # Verify transition is properly recorded
        assert event.from_state == OrderState.PENDING_VALIDATION
        assert event.to_state == OrderState.VALIDATED
        assert event.trigger == TransitionTrigger.VALIDATION_COMPLETE
        assert event.event_data["validation_details"] == "passed all checks"


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    def test_state_machine_with_none_audit_logger(self):
        """Test state machine with None audit logger."""
        fsm = OrderStateMachine(audit_logger=None)
        # Should still work without errors
        result = fsm.can_transition(
            OrderState.PENDING_VALIDATION,
            OrderState.VALIDATED,
            TransitionTrigger.VALIDATION_COMPLETE
        )
        assert result is True

    def test_order_snapshot_with_special_characters(self):
        """Test order snapshot with special characters in data."""
        snapshot = OrderSnapshot(
            order_id="test-123-üñíçödé",
            user_id="user-émail@domain.com",
            symbol="TSLA",
            quantity=100,
            side="buy",
            order_type="market",
            metadata={"note": "Special chars: ñáéíóú"}
        )
        
        # Should handle special characters in hash calculation
        hash_value = snapshot.calculate_hash()
        assert len(hash_value) == 64

    def test_event_schema_with_empty_event_data(self):
        """Test event schema with empty event data."""
        event = OrderEventSchema(
            event_type=OrderEventType.CREATED,
            order_id="order-123",
            event_data={}
        )
        
        assert event.event_data == {}

    def test_order_snapshot_with_large_metadata(self):
        """Test order snapshot with large metadata."""
        large_metadata = {f"key_{i}": f"value_{i}" * 100 for i in range(50)}
        
        snapshot = OrderSnapshot(
            order_id="test-123",
            user_id="user-456",
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type="market",
            metadata=large_metadata
        )
        
        # Should handle large metadata
        assert len(snapshot.metadata) == 50
        hash_value = snapshot.calculate_hash()
        assert len(hash_value) == 64

    def test_order_snapshot_to_dict_with_none_values(self):
        """Test order snapshot to_dict with None values."""
        snapshot = OrderSnapshot(
            order_id="test-123",
            user_id="user-456",
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type="limit",
            price=None  # None price
        )
        
        data = snapshot.to_dict()
        assert data["price"] is None
        assert "created_at" in data

    def test_state_transitions_comprehensive_coverage(self):
        """Test comprehensive coverage of state transition validations."""
        fsm = OrderStateMachine()
        
        # Test all defined transitions
        test_cases = [
            # (from_state, to_state, trigger, expected_result)
            (OrderState.PENDING_VALIDATION, OrderState.VALIDATED, TransitionTrigger.VALIDATION_COMPLETE, True),
            (OrderState.PENDING_VALIDATION, OrderState.CANCELLED, TransitionTrigger.USER_CANCELLATION, True),
            (OrderState.PENDING_RISK_ASSESSMENT, OrderState.RISK_APPROVED, TransitionTrigger.RISK_DECISION, True),
            (OrderState.RISK_APPROVED, OrderState.PENDING_SUBMISSION, TransitionTrigger.BROKER_SUBMISSION, True),
            (OrderState.FILLED, OrderState.CANCELLED, TransitionTrigger.USER_CANCELLATION, False),  # Terminal state
        ]
        
        for from_state, to_state, trigger, expected in test_cases:
            result = fsm.can_transition(from_state, to_state, trigger)
            assert result == expected, f"Failed for {from_state} -> {to_state} via {trigger}"


if __name__ == "__main__":
    pytest.main([__file__])