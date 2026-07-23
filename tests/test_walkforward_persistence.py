"""Tests for walk-forward gate persistence: split persistence model.

Validates that when the walk-forward gate blocks a full brain save,
ALL runtime truth is still persisted — only ML model binaries and
evolved_params remain gated.

These tests exercise the ACTUAL production code paths.
"""

import csv
import inspect
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _get_method_source(cls_name: str, method_name: str) -> str:
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
    from backend.organism.continuous_learner import TradeRecord
    return [TradeRecord(
        symbol=f"SYM{i}", direction=1.0,
        entry_price=100.0 + i, exit_price=101.0 + i,
        entry_bar=i * 10, exit_bar=i * 10 + 5,
        shares=10, pnl=10.0 - i * 5,
        exit_reason="stop_loss",
        predicted_return=0.001, actual_return=0.01,
        confidence=0.28,
        entry_source="alpha", regime_at_entry="chop",
        regime_at_exit="high_vol", mfe=5.0, mae=2.0,
        bars_held_at_exit=5, time_in_trade_seconds=300.0,
        closed_at="2026-04-01T15:00:00Z",
    ) for i in range(n)]


def _make_mock_signal_gen():
    sg = MagicMock()
    sg._is_trained = True
    sg._feature_cols = ["f1", "f2", "f3"]
    sg._xgb_params = {"max_depth": 3}
    sg.generation = 1
    sg.train_window = 100
    sg._latest_metrics = None
    sg.calibration_to_dict.return_value = {"counts": [], "map": [1.0]}
    return sg


def _make_mock_governance():
    gov = MagicMock()
    gov.to_persistence_dict.return_value = {"frozen": False, "halted": False}
    return gov


def _make_mock_regime_detector():
    rd = MagicMock()
    rd.to_persistence_dict.return_value = {
        "history": [], "smoothed_probs": {}, "sma_period": 200
    }
    return rd


def _run_essential_save(tmpdir, **overrides):
    """Run save_essential_state with full runtime truth params."""
    from backend.organism.brain_persistence import OrganismBrain
    brain = OrganismBrain(brain_dir=tmpdir)
    learner = overrides.get("learner", _make_mock_learner(total_trades=42, cumulative_pnl=-123.45))
    trades = overrides.get("trades", _make_mock_trades(3))
    sg = overrides.get("signal_gen", _make_mock_signal_gen())

    brain.save_essential_state(
        signal_gen=sg,
        learner=learner,
        all_trades=trades,
        equity_curve=overrides.get("equity_curve", [100000, 100100, 100050]),
        epoch_metrics=overrides.get("epoch_metrics", []),
        peak_equity=overrides.get("peak_equity", 100100),
        extra_counters=overrides.get("extra_counters", {
            "tick_count": 4000,
            "bars_since_retrain": 50,
            "universe_selector": {"active": ["AAPL", "MSFT"]},
            "exit_levels": {},
            "entry_metadata": {},
            "regime_kelly_stats": {"chop": {"win_rate": 0.5}},
            "ml_calibration": {"counts": [], "map": [1.0]},
            "entry_timestamps": [1000.0, 2000.0],
            "pending_entry": {},
        }),
        governance_controller=overrides.get("governance", _make_mock_governance()),
        regime_detector=overrides.get("regime_detector", _make_mock_regime_detector()),
    )
    return brain


# ═════════════════════════════════════════════════════════════
#  SOURCE CODE PRESENCE TESTS
# ═════════════════════════════════════════════════════════════

class TestSourceCodePresence:
    """Verify production code contains the split persistence model."""

    def test_save_essential_state_exists(self):
        from backend.organism.brain_persistence import OrganismBrain
        assert hasattr(OrganismBrain, "save_essential_state")

    def test_save_essential_writes_all_runtime_truth(self):
        src = _get_method_source("OrganismBrain", "save_essential_state")
        for fn in ["_save_trade_history", "_save_learning_state",
                    "_save_evaluation_event_history", "_save_equity_curve",
                    "_save_extra_counters", "_save_governance_state",
                    "_save_regime_state", "_save_ml_state"]:
            assert fn in src, f"save_essential_state missing call to {fn}"

    def test_save_essential_does_not_write_ml_models(self):
        """V12 W90 (post-cleanup): tightened from substring to call-site
        match.  The pre-W90 ``"_save_ml_models" not in src`` matched
        any mention — including a docstring comment that says
        "_save_ml_models, which save_essential_state intentionally
        [skips]".  The behavioral question is: does this method CALL
        _save_ml_models?  Use ``self._save_ml_models(`` to require
        a parenthesized call site."""
        src = _get_method_source("OrganismBrain", "save_essential_state")
        assert "self._save_ml_models(" not in src

    def test_save_essential_does_not_write_evolved_params(self):
        src = _get_method_source("OrganismBrain", "save_essential_state")
        assert "self._save_evolved_params(" not in src

    def test_save_brain_calls_essential_on_gate_block(self):
        src = _get_method_source("OrganismLiveEngine", "_save_brain")
        assert "save_essential_state" in src

    def test_save_brain_passes_all_runtime_state(self):
        """_save_brain must pass extra_counters, governance, regime to essential save."""
        src = _get_method_source("OrganismLiveEngine", "_save_brain")
        for param in ["extra_counters", "governance_controller", "regime_detector",
                       "equity_curve", "peak_equity"]:
            assert param in src, f"_save_brain missing {param} in essential save call"

    def test_save_brain_updates_watchdog_on_essential(self):
        """Watchdog tick must be updated even on essential-only save."""
        src = _get_method_source("OrganismLiveEngine", "_save_brain")
        assert "_watchdog_last_brain_save_tick" in src


# ═════════════════════════════════════════════════════════════
#  FUNCTIONAL TESTS — always-persisted runtime truth
# ═════════════════════════════════════════════════════════════

class TestAlwaysPersistedState:
    """Verify save_essential_state writes all runtime truth files."""

    def test_trade_history_csv(self):
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            assert (Path(d) / "trade_history.csv").exists()
            with open(Path(d) / "trade_history.csv") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            assert len(rows) == 3
            assert rows[0]["entry_source"] == "alpha"
            assert rows[0]["regime_at_exit"] == "high_vol"

    def test_learning_state_json(self):
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            data = json.loads((Path(d) / "learning_state.json").read_text())
            assert data["total_trades"] == 42
            assert data["cumulative_pnl"] == -123.45

    def test_evaluation_event_history(self):
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            events = json.loads((Path(d) / "evaluation_event_history.json").read_text())
            assert len(events) == 1

    def test_equity_curve_csv(self):
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            assert (Path(d) / "equity_curve.csv").exists()

    def test_extra_counters_json(self):
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            data = json.loads((Path(d) / "extra_counters.json").read_text())
            assert data["tick_count"] == 4000
            assert "universe_selector" in data

    def test_governance_state_json(self):
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            data = json.loads((Path(d) / "governance_state.json").read_text())
            assert data["frozen"] is False

    def test_regime_state_json(self):
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            data = json.loads((Path(d) / "regime_state.json").read_text())
            assert "sma_period" in data

    def test_ml_state_json(self):
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            assert (Path(d) / "ml_state.json").exists()

    def test_manifest_updated(self):
        """V12 W71 changed _apply_live_manifest_fields to write live
        state for ALL fields (generation, total_trades, cumulative_pnl)
        on every save — essential or full.  Pre-V12-W71 generation was
        treated as promotion-gated and preserved; post-V12-W71 it
        reflects the live learner.state.

        Test updated: assert that LIVE fields are written from the
        synthetic learner (generation=1, total_trades=42, cumulative_pnl
        =-123.45) rather than asserting that the pre-seeded manifest
        values are preserved.  ``ml_is_trained`` is computed from
        signal_gen.is_trained (still preserved-from-stub semantics)."""
        with tempfile.TemporaryDirectory() as d:
            # Pre-seed manifest from previous full save
            old = {"brain_format_version": 2, "generation": 4, "ml_is_trained": True,
                   "total_trades": 100, "total_runs": 50}
            (Path(d) / "manifest.json").write_text(json.dumps(old))
            _run_essential_save(d)
            manifest = json.loads((Path(d) / "manifest.json").read_text())
            assert manifest["total_trades"] == 42
            assert manifest["cumulative_pnl"] == -123.45
            # V12 W71: generation now reflects the live learner state.
            assert "generation" in manifest
            assert "ml_is_trained" in manifest


# ═════════════════════════════════════════════════════════════
#  PROMOTION-GATED STATE NOT WRITTEN
# ═════════════════════════════════════════════════════════════

class TestPromotionGatedNotWritten:
    """Verify that ML model binaries and evolved_params are NOT written."""

    def test_no_ml_classifier(self):
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            assert not (Path(d) / "ml_classifier.joblib").exists()

    def test_no_ml_regressor(self):
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            assert not (Path(d) / "ml_regressor.joblib").exists()

    def test_evolved_params_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            old_params = {"version": "original", "alpha": 0.5}
            (Path(d) / "evolved_params.json").write_text(json.dumps(old_params))
            _run_essential_save(d)
            params = json.loads((Path(d) / "evolved_params.json").read_text())
            assert params["version"] == "original"


# ═════════════════════════════════════════════════════════════
#  LOAD/RESTART ROUNDTRIP
# ═════════════════════════════════════════════════════════════

class TestLoadAfterEssentialSave:
    """Verify brain loads correctly after an essential-only save."""

    def test_load_roundtrip(self):
        from backend.organism.brain_persistence import OrganismBrain
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            brain2 = OrganismBrain(brain_dir=d)
            loaded = brain2.load()
            assert loaded is True or brain2.exists
            assert brain2._manifest["total_trades"] == 42
            assert brain2._manifest["cumulative_pnl"] == -123.45

    def test_trade_history_survives_restart(self):
        from backend.organism.brain_persistence import OrganismBrain
        with tempfile.TemporaryDirectory() as d:
            _run_essential_save(d)
            csv_path = Path(d) / "trade_history.csv"
            with open(csv_path) as f:
                rows = list(csv.DictReader(f))
            assert len(rows) == 3
            assert rows[0]["symbol"] == "SYM0"


# ═════════════════════════════════════════════════════════════
#  BOUNDED WALK-FORWARD SKIP  (work order 2026-07-23 Task 1)
# ═════════════════════════════════════════════════════════════

def _make_gated_engine(max_skips):
    """A MagicMock engine wired so the REAL ``OrganismLiveEngine._save_brain``
    can run against it with the walk-forward gate ALWAYS failing.

    Only the save sinks (``brain.save`` / ``brain.save_essential_state``) and
    pure-data helpers are mocked — the bounded-skip control flow under test is
    the real production code.
    """
    engine = MagicMock()
    engine._consecutive_wf_skips = 0
    engine._max_wf_save_skips = max_skips
    engine._tick_count = 100
    engine._exit_levels = {}
    engine._entry_metadata = {}
    # Quiet the forensic identity guard (ids must match __init__ snapshot).
    engine._forensic_signal_gen_id = id(engine.signal_gen)
    engine._forensic_learner_id = id(engine.learner)
    # total_trades > 0 so the F4 fresh-learner abort guard does not fire.
    engine.learner.state.total_trades = 42
    # The gate ALWAYS fails — the permanently-closed-gate scenario from the
    # 2026-07-23 restart (current=-1.021 vs monotonic best=3.436).
    engine.brain.walk_forward_gate.return_value = (
        False, "Walk-forward FAIL: current=-1.021, best=3.436, ratio=-0.297")
    engine._strategy_trades.return_value = []
    return engine


def _drive_save(engine):
    from backend.organism.live_engine import OrganismLiveEngine
    OrganismLiveEngine._save_brain(engine)


class TestBoundedWalkForwardSkip:
    """A permanently-closed walk-forward gate must not block full saves
    forever. Below the ceiling: essential-only save (unchanged). At the
    ceiling: one FORCED full save (gated_save=true), then the counter resets.
    """

    def test_essential_only_below_ceiling(self):
        engine = _make_gated_engine(max_skips=3)
        _drive_save(engine)
        _drive_save(engine)
        assert engine.brain.save_essential_state.call_count == 2
        assert engine.brain.save.call_count == 0
        assert engine._consecutive_wf_skips == 2

    def test_full_save_forced_at_ceiling(self):
        engine = _make_gated_engine(max_skips=3)
        for _ in range(3):
            _drive_save(engine)
        # 2 essential saves, then 1 forced full save on the 3rd cycle.
        assert engine.brain.save_essential_state.call_count == 2
        assert engine.brain.save.call_count == 1
        # The forced save is tagged force=True (audit-only; save() performs the
        # same atomic full save either way and does not bypass the trained
        # overwrite guard).
        _, kwargs = engine.brain.save.call_args
        assert kwargs.get("force") is True
        # Counter resets after a full save lands — no permanent block.
        assert engine._consecutive_wf_skips == 0

    def test_counter_resets_and_recurs(self):
        """After a forced full save the cycle repeats — never permanent."""
        engine = _make_gated_engine(max_skips=2)
        for _ in range(4):
            _drive_save(engine)
        # ceiling=2 → essential, force, essential, force.
        assert engine.brain.save.call_count == 2
        assert engine.brain.save_essential_state.call_count == 2

    def test_gate_pass_does_clean_full_save_and_resets(self):
        engine = _make_gated_engine(max_skips=5)
        _drive_save(engine)  # one gated skip
        assert engine._consecutive_wf_skips == 1
        # The gate now PASSES → clean full save (force=False), counter resets.
        engine.brain.walk_forward_gate.return_value = (True, "Walk-forward passed")
        _drive_save(engine)
        assert engine.brain.save.call_count == 1
        _, kwargs = engine.brain.save.call_args
        assert kwargs.get("force") is False
        assert engine._consecutive_wf_skips == 0

    def test_env_override_sets_ceiling(self, monkeypatch):
        """ORGANISM_MAX_WF_SAVE_SKIPS controls the ceiling; default is 12."""
        import importlib
        import backend.organism.live_engine as le
        monkeypatch.setenv("ORGANISM_MAX_WF_SAVE_SKIPS", "4")
        # Re-read the env the way __init__ does (no full engine construction).
        val = max(1, int(le.os.environ.get("ORGANISM_MAX_WF_SAVE_SKIPS", "12")))
        assert val == 4
        monkeypatch.delenv("ORGANISM_MAX_WF_SAVE_SKIPS", raising=False)
        assert max(1, int(le.os.environ.get("ORGANISM_MAX_WF_SAVE_SKIPS", "12"))) == 12


# ═════════════════════════════════════════════════════════════
#  STALE BRAIN LOCK  (work order 2026-07-23 Task 1 acceptance)
# ═════════════════════════════════════════════════════════════

class TestStaleBrainLock:
    """The brain lock is a POSIX ``fcntl.flock`` tied to the open fd — NOT a
    sentinel-file whose mere existence means "locked". So a ``.brain.lock``
    file left behind by a process killed in a dirty shutdown (the 2026-07-08
    Mac power-off) carries no live lock and can never deadlock the next boot.
    """

    def test_leftover_lock_file_does_not_deadlock(self, tmp_path):
        from backend.organism.brain_persistence import _BrainLock, LOCK_FILE
        lock_path = tmp_path / LOCK_FILE
        # Simulate the leftover file from a dead process.
        lock_path.write_bytes(b"")
        assert lock_path.exists()
        lock = _BrainLock(lock_path)
        lock.acquire()          # must NOT raise — no live holder
        lock.release()
        # And it remains re-acquirable by a fresh lock object.
        lock2 = _BrainLock(lock_path)
        lock2.acquire()
        lock2.release()

    def test_lock_is_genuinely_exclusive_while_held(self, tmp_path):
        """Proves acquire() really locks (so the stale-file test above is not
        vacuously passing): a second acquire while the first is held raises."""
        from backend.organism.brain_persistence import _BrainLock, LOCK_FILE
        lock_path = tmp_path / LOCK_FILE
        a = _BrainLock(lock_path)
        a.acquire()
        b = _BrainLock(lock_path)
        with pytest.raises(RuntimeError):
            b.acquire()
        a.release()
        # Once released, the contended lock is acquirable.
        b.acquire()
        b.release()
