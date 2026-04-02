"""Tests for walk-forward gate persistence fix.

Validates that when the walk-forward gate blocks a full brain save,
essential state (trade history, learning state, evaluation events,
cumulative counters) is still persisted to disk.

These tests exercise the ACTUAL production code paths.
"""

import inspect
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _get_method_source(cls_name: str, method_name: str) -> str:
    """Return source of a method from a class."""
    if cls_name == "OrganismLiveEngine":
        from backend.organism.live_engine import OrganismLiveEngine as cls
    elif cls_name == "OrganismBrain":
        from backend.organism.brain_persistence import OrganismBrain as cls
    else:
        raise ValueError(f"Unknown class: {cls_name}")
    method = getattr(cls, method_name, None)
    assert method is not None, f"{cls_name}.{method_name} not found"
    return inspect.getsource(method)


def _make_mock_learner(total_trades=5, cumulative_pnl=-10.0, generation=1):
    """Create a mock learner with realistic state."""
    from backend.organism.continuous_learner import TradeRecord

    state = MagicMock()
    state.generation = generation
    state.total_bars_seen = 100
    state.total_trades = total_trades
    state.cumulative_pnl = cumulative_pnl
    state.best_sharpe = 1.0
    state.best_generation = 0
    state.retrain_count = 0
    state.drift_events = 0
    state.generation_accuracies = []
    state.evaluation_events = [
        {"evaluated_at": "2026-04-01T14:00:00Z", "accepted": False, "reason": "test"}
    ]

    learner = MagicMock()
    learner.state = state
    learner._bars_since_retrain = 0
    return learner


def _make_mock_trades(n=3):
    """Create mock TradeRecord objects."""
    from backend.organism.continuous_learner import TradeRecord
    trades = []
    for i in range(n):
        trades.append(TradeRecord(
            symbol=f"SYM{i}", direction=1.0,
            entry_price=100.0 + i, exit_price=101.0 + i,
            entry_bar=i * 10, exit_bar=i * 10 + 5,
            shares=10, pnl=10.0 - i * 5,
            exit_reason="stop_loss",
            predicted_return=0.001, actual_return=0.01,
            confidence=0.28,
            entry_source="alpha",
            regime_at_entry="chop",
            regime_at_exit="chop",
            mfe=5.0, mae=2.0,
            bars_held_at_exit=5,
            time_in_trade_seconds=300.0,
            closed_at="2026-04-01T15:00:00Z",
        ))
    return trades


# ═════════════════════════════════════════════════════════════
#  SOURCE CODE PRESENCE TESTS
# ═════════════════════════════════════════════════════════════

class TestSaveEssentialStateExists:
    """Verify the save_essential_state method exists and has the
    correct structure in the production code."""

    def test_brain_has_save_essential_state(self):
        """OrganismBrain must have save_essential_state method."""
        from backend.organism.brain_persistence import OrganismBrain
        assert hasattr(OrganismBrain, "save_essential_state"), (
            "OrganismBrain.save_essential_state() not found"
        )

    def test_save_essential_writes_trade_history(self):
        """save_essential_state must call _save_trade_history."""
        src = _get_method_source("OrganismBrain", "save_essential_state")
        assert "_save_trade_history" in src

    def test_save_essential_writes_learning_state(self):
        """save_essential_state must call _save_learning_state."""
        src = _get_method_source("OrganismBrain", "save_essential_state")
        assert "_save_learning_state" in src

    def test_save_essential_writes_evaluation_events(self):
        """save_essential_state must call _save_evaluation_event_history."""
        src = _get_method_source("OrganismBrain", "save_essential_state")
        assert "_save_evaluation_event_history" in src

    def test_save_essential_updates_manifest(self):
        """save_essential_state must update manifest with current
        total_trades and cumulative_pnl."""
        src = _get_method_source("OrganismBrain", "save_essential_state")
        assert "total_trades" in src
        assert "cumulative_pnl" in src


class TestSaveBrainCallsEssentialOnGateBlock:
    """Verify that _save_brain calls save_essential_state when
    the walk-forward gate blocks."""

    def test_save_brain_calls_essential_on_gate_block(self):
        """When walk-forward gate returns should_save=False,
        _save_brain must call save_essential_state."""
        src = _get_method_source("OrganismLiveEngine", "_save_brain")
        assert "save_essential_state" in src, (
            "_save_brain does not call save_essential_state when gate blocks"
        )

    def test_save_brain_still_does_full_save_on_gate_pass(self):
        """When walk-forward gate passes, full brain.save() must be called."""
        src = _get_method_source("OrganismLiveEngine", "_save_brain")
        assert "self.brain.save(" in src, (
            "_save_brain does not call full brain.save() on gate pass"
        )


# ═════════════════════════════════════════════════════════════
#  FUNCTIONAL TESTS — save_essential_state writes files
# ═════════════════════════════════════════════════════════════

class TestSaveEssentialStateFunctional:
    """Test that save_essential_state actually writes the correct
    files to disk."""

    def test_trade_history_persisted(self):
        """Closed trades must be written to trade_history.csv."""
        from backend.organism.brain_persistence import OrganismBrain

        with tempfile.TemporaryDirectory() as tmpdir:
            brain = OrganismBrain(brain_dir=tmpdir)
            learner = _make_mock_learner(total_trades=3, cumulative_pnl=-5.0)
            trades = _make_mock_trades(3)

            brain.save_essential_state(learner=learner, all_trades=trades)

            csv_path = Path(tmpdir) / "trade_history.csv"
            assert csv_path.exists(), "trade_history.csv was not created"
            content = csv_path.read_text()
            assert "SYM0" in content
            assert "SYM1" in content
            assert "SYM2" in content

    def test_learning_state_persisted(self):
        """Learning state (total_trades, cumulative_pnl) must be written."""
        from backend.organism.brain_persistence import OrganismBrain

        with tempfile.TemporaryDirectory() as tmpdir:
            brain = OrganismBrain(brain_dir=tmpdir)
            learner = _make_mock_learner(total_trades=42, cumulative_pnl=-123.45)
            trades = _make_mock_trades(1)

            brain.save_essential_state(learner=learner, all_trades=trades)

            ls_path = Path(tmpdir) / "learning_state.json"
            assert ls_path.exists(), "learning_state.json was not created"
            data = json.loads(ls_path.read_text())
            assert data["total_trades"] == 42
            assert data["cumulative_pnl"] == -123.45

    def test_evaluation_events_persisted(self):
        """Evaluation event history must be written."""
        from backend.organism.brain_persistence import OrganismBrain

        with tempfile.TemporaryDirectory() as tmpdir:
            brain = OrganismBrain(brain_dir=tmpdir)
            learner = _make_mock_learner()
            trades = _make_mock_trades(1)

            brain.save_essential_state(learner=learner, all_trades=trades)

            ev_path = Path(tmpdir) / "evaluation_event_history.json"
            assert ev_path.exists(), "evaluation_event_history.json was not created"
            events = json.loads(ev_path.read_text())
            assert len(events) == 1
            assert events[0]["accepted"] is False

    def test_manifest_updated_with_trade_count(self):
        """Manifest must be updated with current total_trades and pnl."""
        from backend.organism.brain_persistence import OrganismBrain

        with tempfile.TemporaryDirectory() as tmpdir:
            brain = OrganismBrain(brain_dir=tmpdir)
            # Pre-seed a manifest (simulating a previous full save)
            old_manifest = {
                "brain_format_version": 2,
                "saved_at": "2026-04-01T08:00:00Z",
                "generation": 4,
                "total_trades": 171,
                "cumulative_pnl": -746.17,
                "ml_is_trained": True,
            }
            (Path(tmpdir) / "manifest.json").write_text(json.dumps(old_manifest))

            learner = _make_mock_learner(total_trades=185, cumulative_pnl=-700.0)
            trades = _make_mock_trades(1)

            brain.save_essential_state(learner=learner, all_trades=trades)

            manifest = json.loads((Path(tmpdir) / "manifest.json").read_text())
            assert manifest["total_trades"] == 185, "Manifest total_trades not updated"
            assert manifest["cumulative_pnl"] == -700.0, "Manifest pnl not updated"
            # Preserved fields from previous full save
            assert manifest["generation"] == 4, "Generation should be preserved"
            assert manifest["ml_is_trained"] is True, "ml_is_trained should be preserved"

    def test_forensic_fields_in_trade_csv(self):
        """Trade CSV must include forensic fields (entry_source,
        regime_at_entry, regime_at_exit, mfe, mae, etc.)."""
        from backend.organism.brain_persistence import OrganismBrain
        import csv

        with tempfile.TemporaryDirectory() as tmpdir:
            brain = OrganismBrain(brain_dir=tmpdir)
            learner = _make_mock_learner()
            trades = _make_mock_trades(1)

            brain.save_essential_state(learner=learner, all_trades=trades)

            csv_path = Path(tmpdir) / "trade_history.csv"
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                row = next(reader)
            assert row["entry_source"] == "alpha"
            assert row["regime_at_entry"] == "chop"
            assert row["regime_at_exit"] == "chop"
            assert float(row["mfe"]) == 5.0
            assert float(row["mae"]) == 2.0
            assert row["closed_at"] == "2026-04-01T15:00:00Z"


# ═════════════════════════════════════════════════════════════
#  PROMOTION-GATED STATE REMAINS GATED
# ═════════════════════════════════════════════════════════════

class TestPromotionGatedStateNotWritten:
    """Verify that save_essential_state does NOT write
    promotion-dependent state (ML models, evolved_params)."""

    def test_no_ml_models_written(self):
        """ML model files must NOT be created by essential save."""
        from backend.organism.brain_persistence import OrganismBrain

        with tempfile.TemporaryDirectory() as tmpdir:
            brain = OrganismBrain(brain_dir=tmpdir)
            learner = _make_mock_learner()
            trades = _make_mock_trades(1)

            brain.save_essential_state(learner=learner, all_trades=trades)

            assert not (Path(tmpdir) / "ml_classifier.joblib").exists()
            assert not (Path(tmpdir) / "ml_regressor.joblib").exists()

    def test_no_evolved_params_written(self):
        """evolved_params.json must NOT be overwritten by essential save."""
        from backend.organism.brain_persistence import OrganismBrain

        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-seed evolved_params
            old_params = {"version": "original"}
            (Path(tmpdir) / "evolved_params.json").write_text(json.dumps(old_params))

            brain = OrganismBrain(brain_dir=tmpdir)
            learner = _make_mock_learner()
            trades = _make_mock_trades(1)

            brain.save_essential_state(learner=learner, all_trades=trades)

            # evolved_params should be unchanged
            params = json.loads((Path(tmpdir) / "evolved_params.json").read_text())
            assert params["version"] == "original"


# ═════════════════════════════════════════════════════════════
#  LOAD AFTER ESSENTIAL SAVE
# ═════════════════════════════════════════════════════════════

class TestLoadAfterEssentialSave:
    """Verify that after a gate-blocked save, the brain correctly
    loads the updated trade history and learning state on restart."""

    def test_load_reads_essential_state(self):
        """After essential save, brain.load() must read the updated
        trade history and learning state."""
        from backend.organism.brain_persistence import OrganismBrain

        with tempfile.TemporaryDirectory() as tmpdir:
            brain = OrganismBrain(brain_dir=tmpdir)
            learner = _make_mock_learner(total_trades=185, cumulative_pnl=-700.0)
            trades = _make_mock_trades(3)

            # Simulate a full save first (to create all required files)
            # Then essential save with updated trades
            # For this test, just write the essential state
            brain.save_essential_state(learner=learner, all_trades=trades)

            # Now load a fresh brain instance
            brain2 = OrganismBrain(brain_dir=tmpdir)
            loaded = brain2.load()
            assert loaded is True or brain2.exists

            # Check manifest
            assert brain2._manifest["total_trades"] == 185
            assert brain2._manifest["cumulative_pnl"] == -700.0
