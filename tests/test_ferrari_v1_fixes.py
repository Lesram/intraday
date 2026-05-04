"""Ferrari v1 — Day-1 production fixes.

Covers the four code changes applied after May 1 production observations:
  1. MR scanner: min_stop_bps caps R:R micro-stop edge case
  2. MR scanner: tightened displacement default 2.5 → 4.0
  3. live_engine: predicted_return floor threshold 1e-6 → 1e-4
  4. live_engine: DROP_ML_FROM_GATE flag (default True) extends H2's
     learning-mode-no-ML-confidence rule to production
"""

from __future__ import annotations

from pathlib import Path


def _engine_source() -> str:
    return (
        Path(__file__).parent.parent / "backend" / "organism" / "live_engine.py"
    ).read_text()


def _scanner_source() -> str:
    return (
        Path(__file__).parent.parent
        / "backend" / "organism" / "mean_reversion_scanner.py"
    ).read_text()


# ── #1: MR R:R micro-stop floor ──────────────────────────────────


def test_mr_scanner_has_min_stop_bps_constant():
    src = _scanner_source()
    assert "DEFAULT_MIN_STOP_BPS" in src
    assert "min_stop_bps" in src


def test_mr_scanner_applies_stop_floor():
    src = _scanner_source()
    # Verify the actual flooring math is present in scan()
    assert "min_stop_distance = self.min_stop_bps * current_price / 10000" in src
    assert "actual_stop_distance = max(atr_stop_distance, min_stop_distance)" in src


def test_mr_min_stop_bps_env_wired():
    src = _engine_source()
    assert 'MR_MIN_STOP_BPS = _env_float("ORGANISM_MR_MIN_STOP_BPS", 5.0)' in src
    # Verify it's plumbed to scanner construction
    assert "min_stop_bps=MR_MIN_STOP_BPS" in src


# ── #2: MR threshold tightening ──────────────────────────────────


def test_mr_displacement_default_tightened_to_4():
    src = _engine_source()
    # ORGANISM_MR_MIN_DISPLACEMENT_ATR default in env-bind line is 4.0
    assert 'MR_MIN_DISPLACEMENT_ATR", 4.0' in src
    assert 'tightened from 2.5' in src  # comment trail


# ── #3: predicted_return threshold raised ─────────────────────────


def test_predicted_return_threshold_raised_to_1e4():
    src = _engine_source()
    # Old threshold (1e-6) gone, new threshold (1e-4) present
    assert "abs(ml_sig.predicted_return) > 1e-4" in src
    # Clean removal of the original 0.003 floor
    assert "max(ml_sig.predicted_return, 0.003)" not in src


def test_predicted_return_fallback_uses_breakout_derived():
    src = _engine_source()
    # The fallback formula should be present (used by both ML-silent and
    # learning-mode paths)
    assert "0.005 + 0.015 * bs.composite_score" in src


# ── #4: DROP_ML_FROM_GATE — surgical fix #2 ──────────────────────


def test_drop_ml_from_gate_constant_present_default_true():
    src = _engine_source()
    assert (
        'DROP_ML_FROM_GATE = _env_bool("ORGANISM_DROP_ML_FROM_GATE", True)'
        in src
    )


def test_drop_ml_gate_uses_h2_learning_mode_formula():
    """When DROP_ML_FROM_GATE active, gate uses 0.65×breakout + 0.35×tension
    (mirroring H2's learning-mode formula)."""
    src = _engine_source()
    # Check the actual gating substitution is present
    assert "if DROP_ML_FROM_GATE and not self._is_learning_mode:" in src
    assert "0.65 * breakout_score" in src
    assert "0.35 * min(tension, 1.0)" in src


def test_drop_ml_gate_preserves_composite_for_ranking():
    """The composite (with ML) should still be used for ranking_score so
    relative ordering benefits from any ML signal that does exist."""
    src = _engine_source()
    # ranking_score should reference composite_score (the with-ML composite),
    # not breakout_score directly
    assert '"ranking_score": c.composite_score' in src


# ── Imports / constants smoke ────────────────────────────────────


def test_all_ferrari_v1_constants_importable():
    from backend.organism.live_engine import (
        MEAN_REVERSION_LIVE_ENABLED,
        MR_MIN_DISPLACEMENT_ATR,
        MR_TARGET_RETRACEMENT,
        MR_STOP_EXTENSION_ATR,
        MR_MIN_STOP_BPS,
        MR_COOLDOWN_MINUTES,
        MR_TOP_N,
        DROP_ML_FROM_GATE,
    )
    assert MEAN_REVERSION_LIVE_ENABLED is False  # shadow until promoted
    assert MR_MIN_DISPLACEMENT_ATR == 4.0
    assert MR_STOP_EXTENSION_ATR == 1.0
    assert MR_MIN_STOP_BPS == 5.0
    assert DROP_ML_FROM_GATE is True  # surgical fix #2 active by default
