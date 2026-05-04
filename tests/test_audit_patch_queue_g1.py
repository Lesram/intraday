"""Tests for Patch Queue G1 -- distinguish background trainer rejection from true failure in live_engine."""
from __future__ import annotations

import inspect
import pytest

from backend.organism import live_engine as le_module


# ==============================================================================
# Helpers — extract source for the bg-trainer result handling block
# ==============================================================================

def _get_step11_source() -> str:
    """Return the source of _step_tick (or _tick, or the method containing
    'bg_trainer.get_result') so we can inspect the branching logic."""
    # The bg result handling is inside the main tick method.
    # We search for the method that contains '_bg_trainer.get_result'
    src = inspect.getsource(le_module.OrganismLiveEngine)
    return src


def _get_bg_result_block(src: str) -> str:
    """Extract the block from 'done, train_result' to the submission elif."""
    start = src.index("done, train_result = self._bg_trainer.get_result()")
    # Find a safe end marker — the submission branch
    end = src.index("elif self._bars_since_retrain >= _retrain_threshold:", start)
    return src[start:end]


# ==============================================================================
# Test 1: Source structure — three branches exist
# ==============================================================================

class TestBranchStructure:

    def test_three_distinct_branches_exist(self):
        """The bg result handling must have three branches:
        1. accepted
        2. error (true failure)
        3. rejection (quality gate)
        """
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        assert "train_result.accepted" in block, "Must have accepted branch"
        assert "train_result.error" in block, "Must have error branch"
        assert "train_result.rejection_reason" in block or "rejection" in block, \
            "Must have rejection branch"

    def test_error_branch_before_generic_elif(self):
        """The error branch (train_result.error) must come before the generic
        rejection branch so errors are caught first."""
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        error_pos = block.index("train_result.error")
        # The generic 'elif done and train_result:' for rejection comes after
        rejection_elif_pos = block.index("elif done and train_result:", block.index("train_result.error"))
        assert error_pos < rejection_elif_pos


# ==============================================================================
# Test 2: Error path triggers sync retrain fallback
# ==============================================================================

class TestErrorPathSyncFallback:

    def test_error_branch_calls_retrain_and_evolve(self):
        """True training error must fall back to _retrain_and_evolve."""
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        # Find the error branch
        error_start = block.index("train_result.error")
        # Find the next elif (rejection branch)
        next_elif = block.index("elif done and train_result:", error_start)
        error_block = block[error_start:next_elif]

        assert "_retrain_and_evolve" in error_block, \
            "Error branch must call _retrain_and_evolve for sync fallback"

    def test_error_branch_sets_status_error(self):
        """Error branch must set status='error' in metadata."""
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        error_start = block.index("train_result.error")
        next_elif = block.index("elif done and train_result:", error_start)
        error_block = block[error_start:next_elif]

        assert '"error"' in error_block or "'error'" in error_block, \
            "Error branch must set status to 'error'"


# ==============================================================================
# Test 3: Rejection path does NOT trigger sync retrain
# ==============================================================================

class TestRejectionPathNoSyncFallback:

    def test_rejection_branch_does_not_call_retrain(self):
        """Quality-gate rejection must NOT fall back to _retrain_and_evolve."""
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        # Find the rejection branch (the final elif done and train_result:)
        error_start = block.index("train_result.error")
        rejection_start = block.index("elif done and train_result:", error_start)
        rejection_block = block[rejection_start:]

        assert "_retrain_and_evolve" not in rejection_block, \
            "Rejection branch must NOT call _retrain_and_evolve"

    def test_rejection_branch_sets_status_rejected(self):
        """Rejection branch must set status='rejected' in metadata."""
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        error_start = block.index("train_result.error")
        rejection_start = block.index("elif done and train_result:", error_start)
        rejection_block = block[rejection_start:]

        assert '"rejected"' in rejection_block, \
            "Rejection branch must set status to 'rejected'"

    def test_rejection_branch_stores_rejection_reason(self):
        """Rejection branch must store rejection_reason in metadata."""
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        error_start = block.index("train_result.error")
        rejection_start = block.index("elif done and train_result:", error_start)
        rejection_block = block[rejection_start:]

        assert "rejection_reason" in rejection_block, \
            "Rejection branch must store rejection_reason"

    def test_rejection_branch_emits_activity_event(self):
        """Rejection branch must emit an ActivityEvent."""
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        error_start = block.index("train_result.error")
        rejection_start = block.index("elif done and train_result:", error_start)
        rejection_block = block[rejection_start:]

        assert "ActivityEvent" in rejection_block or "activity.append" in rejection_block, \
            "Rejection branch must emit an activity event"


# ==============================================================================
# Test 4: Metadata status values are distinct
# ==============================================================================

class TestMetadataStatusValues:

    def test_three_distinct_status_values(self):
        """The bg result handling must use three distinct status values:
        'completed', 'error', 'rejected'."""
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        assert '"completed"' in block, "Must have status='completed'"
        assert '"error"' in block, "Must have status='error'"
        assert '"rejected"' in block, "Must have status='rejected'"

    def test_error_metadata_has_error_field(self):
        """Error metadata must include 'error' field."""
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        error_start = block.index("train_result.error")
        next_elif = block.index("elif done and train_result:", error_start)
        error_block = block[error_start:next_elif]

        assert '"error":' in error_block or "'error':" in error_block

    def test_rejection_metadata_has_train_metrics(self):
        """Rejection metadata must include train_metrics for forensic analysis."""
        src = _get_step11_source()
        block = _get_bg_result_block(src)

        error_start = block.index("train_result.error")
        rejection_start = block.index("elif done and train_result:", error_start)
        rejection_block = block[rejection_start:]

        assert "train_metrics" in rejection_block, \
            "Rejection metadata must include train_metrics"
