"""
Contract tests for Order Finite State Machine (FSM).

Tests valid/invalid state transitions and idempotency preservation
using mocks to ensure contract compliance.
"""

from enum import Enum

import pytest


class MockOrderStateMachine:
    """Mock implementation of order state machine for contract testing."""

    class State(Enum):
        NEW = "new"
        SUBMITTED = "submitted"
        PARTIALLY_FILLED = "partially_filled"
        FILLED = "filled"
        CANCELED = "canceled"
        REJECTED = "rejected"
        EXPIRED = "expired"
        PENDING_CANCEL = "pending_cancel"
        PENDING_REPLACE = "pending_replace"

    VALID_TRANSITIONS = {
        State.NEW: {State.SUBMITTED, State.CANCELED, State.REJECTED},
        State.SUBMITTED: {
            State.PARTIALLY_FILLED,
            State.FILLED,
            State.CANCELED,
            State.REJECTED,
            State.EXPIRED,
            State.PENDING_CANCEL,
            State.PENDING_REPLACE,
        },
        State.PARTIALLY_FILLED: {
            State.FILLED,
            State.CANCELED,
            State.REJECTED,
            State.PENDING_CANCEL,
            State.PENDING_REPLACE,
        },
        State.FILLED: set(),  # Terminal state
        State.CANCELED: set(),  # Terminal state
        State.REJECTED: set(),  # Terminal state
        State.EXPIRED: set(),  # Terminal state
        State.PENDING_CANCEL: {State.CANCELED, State.FILLED, State.PARTIALLY_FILLED},
        State.PENDING_REPLACE: {State.SUBMITTED, State.CANCELED, State.REJECTED},
    }

    def __init__(self, order_id: str, initial_state: State = State.NEW):
        self.order_id = order_id
        self.current_state = initial_state
        self.state_history = [initial_state]
        self.transition_count = 0

    def transition_to(self, new_state: State, idempotent: bool = False) -> bool:
        """
        Attempt state transition with idempotency support.

        Args:
            new_state: Target state
            idempotent: If True, allow transition to same state without error

        Returns:
            True if transition successful, False otherwise
        """
        # Idempotency check - same state transition
        if self.current_state == new_state:
            if idempotent:
                return True
            else:
                raise ValueError(
                    f"Idempotent transition to same state {new_state} not allowed without idempotent=True"
                )

        # Check if transition is valid
        if new_state not in self.VALID_TRANSITIONS[self.current_state]:
            raise ValueError(
                f"Invalid transition from {self.current_state} to {new_state}"
            )

        # Perform transition
        self.current_state = new_state
        self.state_history.append(new_state)
        self.transition_count += 1

        return True

    def get_valid_transitions(self):
        """Get valid transitions from current state."""
        return self.VALID_TRANSITIONS[self.current_state]

    def is_terminal(self) -> bool:
        """Check if current state is terminal."""
        return len(self.VALID_TRANSITIONS[self.current_state]) == 0


class TestOrderFSMContracts:
    """Contract tests for order state machine behavior."""

    @pytest.fixture
    def fresh_order(self):
        """Create a fresh order in NEW state."""
        return MockOrderStateMachine("order_123", MockOrderStateMachine.State.NEW)

    def test_valid_transitions_from_new_state(self, fresh_order):
        """Test all valid transitions from NEW state."""
        State = MockOrderStateMachine.State

        # NEW -> SUBMITTED
        order1 = MockOrderStateMachine("order_1", State.NEW)
        assert order1.transition_to(State.SUBMITTED) is True
        assert order1.current_state == State.SUBMITTED

        # NEW -> CANCELED
        order2 = MockOrderStateMachine("order_2", State.NEW)
        assert order2.transition_to(State.CANCELED) is True
        assert order2.current_state == State.CANCELED
        assert order2.is_terminal() is True

        # NEW -> REJECTED
        order3 = MockOrderStateMachine("order_3", State.NEW)
        assert order3.transition_to(State.REJECTED) is True
        assert order3.current_state == State.REJECTED
        assert order3.is_terminal() is True

    def test_invalid_transitions_from_new_state(self, fresh_order):
        """Test invalid transitions from NEW state are rejected."""
        State = MockOrderStateMachine.State

        invalid_transitions = [
            State.FILLED,
            State.PARTIALLY_FILLED,
            State.EXPIRED,
            State.PENDING_CANCEL,
            State.PENDING_REPLACE,
        ]

        for invalid_state in invalid_transitions:
            order = MockOrderStateMachine("order_invalid", State.NEW)

            with pytest.raises(
                ValueError,
                match=f"Invalid transition from {State.NEW} to {invalid_state}",
            ):
                order.transition_to(invalid_state)

            # Verify state didn't change
            assert order.current_state == State.NEW

    def test_valid_transitions_from_submitted_state(self):
        """Test valid transitions from SUBMITTED state."""
        State = MockOrderStateMachine.State

        valid_transitions = [
            State.PARTIALLY_FILLED,
            State.FILLED,
            State.CANCELED,
            State.REJECTED,
            State.EXPIRED,
            State.PENDING_CANCEL,
            State.PENDING_REPLACE,
        ]

        for valid_state in valid_transitions:
            order = MockOrderStateMachine("order_submitted", State.SUBMITTED)
            assert order.transition_to(valid_state) is True
            assert order.current_state == valid_state

    def test_terminal_states_have_no_valid_transitions(self):
        """Test terminal states cannot transition to any other state."""
        State = MockOrderStateMachine.State

        terminal_states = [State.FILLED, State.CANCELED, State.REJECTED, State.EXPIRED]

        for terminal_state in terminal_states:
            order = MockOrderStateMachine("order_terminal", terminal_state)
            assert order.is_terminal() is True

            # Try to transition to any other state - should all fail
            for target_state in State:
                if target_state != terminal_state:
                    with pytest.raises(
                        ValueError, match=f"Invalid transition from {terminal_state}"
                    ):
                        order.transition_to(target_state)

    def test_idempotent_transitions_same_state(self):
        """Test idempotent transitions to same state."""
        State = MockOrderStateMachine.State

        order = MockOrderStateMachine("order_idempotent", State.SUBMITTED)
        initial_transition_count = order.transition_count

        # Same state transition without idempotent flag should fail
        with pytest.raises(ValueError, match="Idempotent transition to same state"):
            order.transition_to(State.SUBMITTED, idempotent=False)

        # Same state transition with idempotent flag should succeed
        result = order.transition_to(State.SUBMITTED, idempotent=True)
        assert result is True
        assert order.current_state == State.SUBMITTED

        # Verify no state change was recorded
        assert order.transition_count == initial_transition_count

    def test_state_history_preservation(self):
        """Test state transition history is preserved."""
        State = MockOrderStateMachine.State

        order = MockOrderStateMachine("order_history", State.NEW)

        # Perform sequence of transitions
        transitions = [
            State.SUBMITTED,
            State.PARTIALLY_FILLED,
            State.PENDING_CANCEL,
            State.CANCELED,
        ]

        expected_history = [State.NEW] + transitions

        for state in transitions:
            order.transition_to(state)

        assert order.state_history == expected_history
        assert order.transition_count == len(transitions)

    def test_partial_fill_to_full_fill_workflow(self):
        """Test realistic partial fill to full fill workflow."""
        State = MockOrderStateMachine.State

        order = MockOrderStateMachine("order_partial", State.NEW)

        # Realistic workflow
        order.transition_to(State.SUBMITTED)
        order.transition_to(State.PARTIALLY_FILLED)
        order.transition_to(State.FILLED)  # Final fill

        # Verify final state
        assert order.current_state == State.FILLED
        assert order.is_terminal() is True

        # Verify history
        expected_history = [
            State.NEW,
            State.SUBMITTED,
            State.PARTIALLY_FILLED,
            State.FILLED,
        ]
        assert order.state_history == expected_history

    def test_cancel_workflow_from_different_states(self):
        """Test cancel workflow from various non-terminal states."""
        State = MockOrderStateMachine.State

        # Cancel from SUBMITTED
        order1 = MockOrderStateMachine("order_cancel_1", State.SUBMITTED)
        order1.transition_to(State.PENDING_CANCEL)
        order1.transition_to(State.CANCELED)
        assert order1.is_terminal() is True

        # Cancel from PARTIALLY_FILLED
        order2 = MockOrderStateMachine("order_cancel_2", State.PARTIALLY_FILLED)
        order2.transition_to(State.PENDING_CANCEL)
        order2.transition_to(State.CANCELED)
        assert order2.is_terminal() is True

        # Direct cancel from SUBMITTED (immediate cancel)
        order3 = MockOrderStateMachine("order_cancel_3", State.SUBMITTED)
        order3.transition_to(State.CANCELED)
        assert order3.is_terminal() is True

    def test_replace_order_workflow(self):
        """Test order replacement workflow."""
        State = MockOrderStateMachine.State

        order = MockOrderStateMachine("order_replace", State.SUBMITTED)

        # Request replacement
        order.transition_to(State.PENDING_REPLACE)

        # Replacement accepted - order becomes new submitted order
        order.transition_to(State.SUBMITTED)

        # Can continue normal workflow
        order.transition_to(State.FILLED)

        assert order.current_state == State.FILLED
        assert order.is_terminal() is True

    def test_order_expiration_workflow(self):
        """Test order expiration from valid states."""
        State = MockOrderStateMachine.State

        # Can expire from SUBMITTED
        order1 = MockOrderStateMachine("order_exp_1", State.SUBMITTED)
        order1.transition_to(State.EXPIRED)
        assert order1.is_terminal() is True

        # Cannot expire from other states
        invalid_expire_from = [
            State.NEW,
            State.PARTIALLY_FILLED,
            State.PENDING_CANCEL,
            State.PENDING_REPLACE,
        ]

        for invalid_state in invalid_expire_from:
            order = MockOrderStateMachine("order_exp_invalid", invalid_state)

            with pytest.raises(
                ValueError,
                match=f"Invalid transition from {invalid_state} to {State.EXPIRED}",
            ):
                order.transition_to(State.EXPIRED)

    def test_concurrent_modification_protection(self):
        """Test FSM behavior under concurrent modification scenarios."""
        State = MockOrderStateMachine.State

        order = MockOrderStateMachine("order_concurrent", State.SUBMITTED)

        # Simulate race condition - order filled while cancel pending
        order.transition_to(State.PENDING_CANCEL)

        # Broker reports fill before cancel processed
        order.transition_to(State.FILLED)
        assert order.current_state == State.FILLED
        assert order.is_terminal() is True

        # Subsequent cancel should fail (terminal state)
        with pytest.raises(ValueError, match="Invalid transition from"):
            order.transition_to(State.CANCELED)

    def test_fsm_contract_invariants(self):
        """Test FSM contract invariants are maintained."""
        State = MockOrderStateMachine.State

        order = MockOrderStateMachine("order_invariants", State.NEW)

        # Invariant 1: State history always starts with initial state
        assert order.state_history[0] == State.NEW

        # Invariant 2: Current state is always last in history
        order.transition_to(State.SUBMITTED)
        assert order.current_state == order.state_history[-1]

        order.transition_to(State.FILLED)
        assert order.current_state == order.state_history[-1]

        # Invariant 3: Transition count matches history length - 1
        assert order.transition_count == len(order.state_history) - 1

        # Invariant 4: Terminal states have no valid transitions
        assert len(order.get_valid_transitions()) == 0

    def test_fsm_deterministic_behavior(self, test_seed):
        """Test FSM behavior is deterministic given same inputs."""
        State = MockOrderStateMachine.State

        # Create two identical orders
        order1 = MockOrderStateMachine("order_det_1", State.NEW)
        order2 = MockOrderStateMachine("order_det_2", State.NEW)

        # Apply same sequence of transitions
        transitions = [State.SUBMITTED, State.PARTIALLY_FILLED, State.FILLED]

        for state in transitions:
            order1.transition_to(state)
            order2.transition_to(state)

        # Should have identical final states and histories
        assert order1.current_state == order2.current_state
        assert order1.state_history == order2.state_history
        assert order1.transition_count == order2.transition_count

    @pytest.mark.parametrize(
        "initial_state,target_state,should_succeed",
        [
            # Valid transitions
            ("NEW", "SUBMITTED", True),
            ("NEW", "CANCELED", True),
            ("SUBMITTED", "FILLED", True),
            ("PARTIALLY_FILLED", "FILLED", True),
            ("PENDING_CANCEL", "CANCELED", True),
            # Invalid transitions
            ("NEW", "FILLED", False),
            ("FILLED", "CANCELED", False),
            ("CANCELED", "SUBMITTED", False),
            ("REJECTED", "FILLED", False),
            ("EXPIRED", "SUBMITTED", False),
        ],
    )
    def test_transition_matrix_compliance(
        self, initial_state, target_state, should_succeed
    ):
        """Test transition matrix compliance with parameterized tests."""
        State = MockOrderStateMachine.State

        order = MockOrderStateMachine("order_matrix", State[initial_state])

        if should_succeed:
            result = order.transition_to(State[target_state])
            assert result is True
            assert order.current_state == State[target_state]
        else:
            with pytest.raises(ValueError, match="Invalid transition"):
                order.transition_to(State[target_state])

            # Verify state unchanged
            assert order.current_state == State[initial_state]
