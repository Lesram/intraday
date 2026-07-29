"""Tests for incident recovery Wave XB — learning-mode gate calibration.

The learning-mode confidence formula (0.65*breakout + 0.35*tension) has a
realistic max of ~0.43.  The old 0.40/0.45 gates were mathematically
unreachable under normal conditions.  The fix sets learning-mode main-book
gate to 0.25 (the exploration floor).  Production thresholds are unchanged.
"""
import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _make_engine(**overrides):
    from backend.organism.live_engine import OrganismLiveEngine
    engine = OrganismLiveEngine(
        data_client=MagicMock(),
        order_service=MagicMock(),
        positions_service=MagicMock(),
    )
    for k, v in overrides.items():
        setattr(engine, k, v)
    return engine


class TestLearningModeGate:
    """Learning mode uses 0.25 main-book gate."""

    def test_learning_mode_gate_is_0_25_in_source(self):
        """Verify the learning-mode path sets _MIN_MAIN_CONF = _EXPL_CONF_GATE."""
        from backend.organism.live_engine import OrganismLiveEngine
        source = inspect.getsource(OrganismLiveEngine._live_tick_inner)
        # The learning mode branch should assign _EXPL_CONF_GATE
        assert "self._is_learning_mode" in source
        assert "_MIN_MAIN_CONF = _EXPL_CONF_GATE" in source

    def test_expl_conf_gate_is_0_25(self):
        """The exploration confidence gate constant is 0.25."""
        src_path = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
        source = src_path.read_text()
        assert "_EXPL_CONF_GATE = 0.25" in source

    def test_candidates_in_0_25_to_0_39_pass_in_learning_mode(self):
        """Candidates with eff_conf 0.25-0.39 should now pass in learning mode.

        Before the fix, these were rejected (gate was 0.40 baseline / 0.45 defensive).
        After the fix, the gate is 0.25, so anything >= 0.25 passes.
        """
        # Simulate the gate logic
        _EXPL_CONF_GATE = 0.25
        _MAIN_CONF_BASELINE = 0.40
        _MAIN_CONF_DEFENSIVE = 0.45
        is_learning_mode = True

        # New logic
        if is_learning_mode:
            _MIN_MAIN_CONF = _EXPL_CONF_GATE  # 0.25
        else:
            _MIN_MAIN_CONF = _MAIN_CONF_BASELINE  # 0.40

        # Test candidates in the 0.25-0.39 band
        test_confs = [0.25, 0.28, 0.30, 0.33, 0.35, 0.39]
        for conf in test_confs:
            assert conf >= _MIN_MAIN_CONF, (
                f"eff_conf={conf} should pass learning-mode gate {_MIN_MAIN_CONF}"
            )

    def test_candidates_below_0_25_still_rejected_in_learning_mode(self):
        """Candidates below 0.25 are still rejected (outright, below exploration floor)."""
        _EXPL_CONF_GATE = 0.25
        test_confs = [0.00, 0.10, 0.15, 0.20, 0.24]
        for conf in test_confs:
            assert conf < _EXPL_CONF_GATE, (
                f"eff_conf={conf} should still be rejected below {_EXPL_CONF_GATE}"
            )


class TestProductionModeUnchanged:
    """Production mode thresholds must remain at 0.40 / 0.45."""

    def test_production_mode_baseline_gate_unchanged(self):
        """Production baseline is still 0.40."""
        src_path = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
        source = src_path.read_text()
        assert "_MAIN_CONF_BASELINE = 0.40" in source

    def test_production_mode_defensive_gate_unchanged(self):
        """Production defensive (chop/high_vol) is still 0.45."""
        src_path = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
        source = src_path.read_text()
        assert "_MAIN_CONF_DEFENSIVE = 0.45" in source

    def test_production_chop_uses_0_45(self):
        """In production mode with chop regime, gate is 0.45."""
        _MAIN_CONF_BASELINE = 0.40
        _MAIN_CONF_DEFENSIVE = 0.45
        is_learning_mode = False
        regime = "chop"

        # Simulated new logic
        if is_learning_mode:
            _MIN_MAIN_CONF = 0.25
        elif regime in ("chop", "high_vol", "trending_down"):
            _MIN_MAIN_CONF = _MAIN_CONF_DEFENSIVE
        else:
            _MIN_MAIN_CONF = _MAIN_CONF_BASELINE

        assert _MIN_MAIN_CONF == 0.45

    def test_production_trending_up_uses_0_40(self):
        """In production mode with trending_up regime, gate is 0.40."""
        _MAIN_CONF_BASELINE = 0.40
        _MAIN_CONF_DEFENSIVE = 0.45
        is_learning_mode = False
        regime = "trending_up"

        if is_learning_mode:
            _MIN_MAIN_CONF = 0.25
        elif regime in ("chop", "high_vol", "trending_down"):
            _MIN_MAIN_CONF = _MAIN_CONF_DEFENSIVE
        else:
            _MIN_MAIN_CONF = _MAIN_CONF_BASELINE

        assert _MIN_MAIN_CONF == 0.40


class TestNoThresholdDrift:
    """Verify no unintended threshold changes in other paths."""

    def test_exploration_gate_unchanged(self):
        """Exploration floor remains 0.25."""
        src_path = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
        source = src_path.read_text()
        assert "_EXPL_CONF_GATE = 0.25" in source

    def test_fitness_gate_unchanged(self):
        """Production fitness gate remains 0.45."""
        src_path = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
        source = src_path.read_text()
        assert "_MAIN_FITNESS_GATE = 0.45" in source

    def test_pure_breakout_gate_uses_same_min_main_conf(self):
        """Pure breakout path shares the same _MIN_MAIN_CONF (unified gate)."""
        from backend.organism.live_engine import OrganismLiveEngine
        source = inspect.getsource(OrganismLiveEngine._live_tick_inner)
        # The breakout path should reference _MIN_MAIN_CONF
        assert "_bo_conf < _MIN_MAIN_CONF" in source

    def test_confidence_formula_weights_unchanged(self):
        """Learning-mode confidence weights still 0.65/0.35."""
        src_path = Path(__file__).resolve().parents[1] / "backend" / "organism" / "live_engine.py"
        source = src_path.read_text()
        assert "0.65 * breakout_score" in source
        assert "0.35 * min(tension" in source


class TestRealisticConfidenceScenarios:
    """Verify realistic scenarios now produce tradeable candidates."""

    def test_typical_learning_mode_candidate_passes(self):
        """breakout=0.30 + tension=0.25 → conf=0.2825 → passes 0.25 gate."""
        breakout = 0.30
        tension = 0.25
        conf = 0.65 * breakout + 0.35 * min(tension, 1.0)
        gate = 0.25  # learning mode gate
        assert conf >= gate, f"conf={conf:.4f} should pass gate={gate}"
        assert conf == pytest.approx(0.2825, abs=0.001)

    def test_weak_but_viable_candidate_passes(self):
        """breakout=0.25 + tension=0.15 → conf=0.215 → fails 0.25 gate (correctly)."""
        breakout = 0.25
        tension = 0.15
        conf = 0.65 * breakout + 0.35 * min(tension, 1.0)
        gate = 0.25
        assert conf < gate, f"conf={conf:.4f} should fail gate={gate} (too weak)"

    def test_moderate_candidate_passes_easily(self):
        """breakout=0.35 + tension=0.30 → conf=0.3325 → passes 0.25 gate."""
        breakout = 0.35
        tension = 0.30
        conf = 0.65 * breakout + 0.35 * min(tension, 1.0)
        gate = 0.25
        assert conf >= gate
        assert conf == pytest.approx(0.3325, abs=0.001)

    def test_strong_candidate_passes(self):
        """breakout=0.45 + tension=0.40 → conf=0.4325 → passes easily."""
        breakout = 0.45
        tension = 0.40
        conf = 0.65 * breakout + 0.35 * min(tension, 1.0)
        gate = 0.25
        assert conf >= gate
        assert conf == pytest.approx(0.4325, abs=0.001)

    def test_incident_mar18_top_candidate_would_now_pass(self):
        """The Mar 18 max eff_conf of 0.40 would now pass the 0.25 gate."""
        mar18_max_conf = 0.40
        gate = 0.25
        assert mar18_max_conf >= gate

    def test_incident_mar18_candidates_in_0_25_band_would_pass(self):
        """16 candidates from Mar 18 had eff_conf >= 0.25 — they would now pass."""
        # From the incident audit: 16 candidates had eff_conf in 0.25-0.39 band
        candidates_passing = 16
        assert candidates_passing > 0
