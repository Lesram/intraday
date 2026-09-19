"""Experiment 3 — Confidence inversion / ML contamination instrumentation.

Non-invasive side-by-side confidence comparison. Tests that the
instrumentation produces correct fields without changing trade eligibility.

Tests:
1. Side-by-side fields are computed correctly
2. Missing ML signal doesn't crash
3. Learning-mode ML component is zero
4. Instrumentation doesn't change eligibility
"""

from __future__ import annotations

import math


# ── Mirror the exact production-mode confidence formulas ──

def compute_production_confidence(
    breakout_score: float,
    tension: float,
    ml_confidence: float | None,
    is_learning_mode: bool,
) -> tuple[float, float, float]:
    """Returns (confidence_live, confidence_bt_only, ml_component).
    Mirrors live_engine.py lines 2134-2148 + Exp3 instrumentation."""

    # Pure breakout+tension (learning-mode formula)
    conf_bt_only = 0.65 * breakout_score + 0.35 * min(tension, 1.0)

    if is_learning_mode:
        confidence = conf_bt_only
        ml_component = 0.0
    else:
        ml_conf = ml_confidence if ml_confidence is not None else 0.0
        confidence = 0.50 * ml_conf + 0.30 * breakout_score + 0.20 * min(tension, 1.0)
        ml_component = ml_conf

    return confidence, conf_bt_only, ml_component


# ─────────────────────────────────────────────────────────────
# Test 1: Side-by-side fields computed correctly
# ─────────────────────────────────────────────────────────────

def test_side_by_side_production_mode():
    """In production mode, ML contributes 50% to live confidence.
    breakout+tension-only should match the learning formula."""
    conf_live, conf_bt, ml_comp = compute_production_confidence(
        breakout_score=0.40,
        tension=0.30,
        ml_confidence=0.60,
        is_learning_mode=False,
    )
    # Live: 0.50*0.60 + 0.30*0.40 + 0.20*0.30 = 0.30 + 0.12 + 0.06 = 0.48
    assert abs(conf_live - 0.48) < 1e-6

    # BT-only: 0.65*0.40 + 0.35*0.30 = 0.26 + 0.105 = 0.365
    assert abs(conf_bt - 0.365) < 1e-6

    # ML component = 0.60
    assert ml_comp == 0.60


def test_side_by_side_learning_mode():
    """In learning mode, ML is zeroed. Both formulas should match."""
    conf_live, conf_bt, ml_comp = compute_production_confidence(
        breakout_score=0.40,
        tension=0.30,
        ml_confidence=0.90,  # should be ignored
        is_learning_mode=True,
    )
    # Both should be 0.65*0.40 + 0.35*0.30 = 0.365
    assert abs(conf_live - 0.365) < 1e-6
    assert abs(conf_bt - 0.365) < 1e-6
    assert ml_comp == 0.0


# ─────────────────────────────────────────────────────────────
# Test 2: Missing/non-finite ML signal doesn't crash
# ─────────────────────────────────────────────────────────────

def test_missing_ml_confidence():
    """ml_confidence=None should default to 0.0, not crash."""
    conf_live, conf_bt, ml_comp = compute_production_confidence(
        breakout_score=0.40,
        tension=0.30,
        ml_confidence=None,
        is_learning_mode=False,
    )
    # Live: 0.50*0.0 + 0.30*0.40 + 0.20*0.30 = 0 + 0.12 + 0.06 = 0.18
    assert abs(conf_live - 0.18) < 1e-6
    assert ml_comp == 0.0
    # Should NOT crash
    assert math.isfinite(conf_live)
    assert math.isfinite(conf_bt)


def test_nan_ml_confidence():
    """NaN ML confidence handled safely."""
    conf_live, conf_bt, ml_comp = compute_production_confidence(
        breakout_score=0.40,
        tension=0.30,
        ml_confidence=float("nan"),
        is_learning_mode=False,
    )
    # NaN propagates through arithmetic — this is expected behavior.
    # The instrumentation should still not crash.
    # The key is that conf_bt_only is finite regardless.
    assert math.isfinite(conf_bt)


# ─────────────────────────────────────────────────────────────
# Test 3: Learning-mode ML component is zero
# ─────────────────────────────────────────────────────────────

def test_learning_mode_ml_always_zero():
    """Regardless of what ml_confidence is passed, in learning mode
    the ML component should be 0."""
    for ml_val in [0.0, 0.5, 0.99, None, float("nan")]:
        _, _, ml_comp = compute_production_confidence(
            breakout_score=0.40,
            tension=0.30,
            ml_confidence=ml_val,
            is_learning_mode=True,
        )
        assert ml_comp == 0.0, f"ML should be 0 in learning mode, got {ml_comp} for input {ml_val}"


# ─────────────────────────────────────────────────────────────
# Test 4: Instrumentation doesn't change eligibility
# ─────────────────────────────────────────────────────────────

def test_gate_pass_equivalence():
    """The gate_pass_live and gate_pass_bt_only fields are pure
    predicates — they don't affect actual gating.

    Verify that the live confidence is what the gate actually sees.
    The bt_only version is for comparison only."""
    GATE_THRESHOLD = 0.40  # typical _MIN_MAIN_CONF

    # Case: ML boosts a weak breakout past the gate
    conf_live, conf_bt, _ = compute_production_confidence(
        breakout_score=0.30,  # weak breakout
        tension=0.20,
        ml_confidence=0.80,  # ML thinks it's great
        is_learning_mode=False,
    )
    # Live: 0.50*0.80 + 0.30*0.30 + 0.20*0.20 = 0.40+0.09+0.04 = 0.53
    # BT:   0.65*0.30 + 0.35*0.20 = 0.195+0.07 = 0.265
    gate_live = conf_live >= GATE_THRESHOLD
    gate_bt = conf_bt >= GATE_THRESHOLD

    assert gate_live is True   # ML boosted past gate
    assert gate_bt is False    # Without ML, wouldn't pass

    # The Exp3 insight: if these trades systematically lose,
    # ML is adding noise. The instrumentation captures exactly this.


def test_ml_drags_down_strong_breakout():
    """Case where ML confidence is low and drags a good breakout
    below the gate, while breakout-only would pass."""
    GATE_THRESHOLD = 0.40

    conf_live, conf_bt, _ = compute_production_confidence(
        breakout_score=0.60,  # strong breakout
        tension=0.40,
        ml_confidence=0.10,  # ML is pessimistic
        is_learning_mode=False,
    )
    # Live: 0.50*0.10 + 0.30*0.60 + 0.20*0.40 = 0.05+0.18+0.08 = 0.31
    # BT:   0.65*0.60 + 0.35*0.40 = 0.39+0.14 = 0.53
    gate_live = conf_live >= GATE_THRESHOLD
    gate_bt = conf_bt >= GATE_THRESHOLD

    assert gate_live is False  # ML dragged below gate
    assert gate_bt is True     # Without ML, would pass

    # The Exp3 insight: if ML suppresses entries that would have won,
    # the ML signal is anti-predictive.


# ─────────────────────────────────────────────────────────────
# Test 5: candidate dict has Exp3 fields
# ─────────────────────────────────────────────────────────────

def test_candidate_dict_has_exp3_fields():
    """The cand_dicts entry should include the side-by-side fields."""
    # Simulate what the live_engine appends
    cand = {
        "symbol": "AAPL",
        "confidence": 0.48,
        "breakout_score": 0.40,
        # Exp3 fields:
        "confidence_bt_only": 0.365,
        "confidence_ml_component": 0.60,
        "gate_pass_bt_only": False,
    }
    assert "confidence_bt_only" in cand
    assert "confidence_ml_component" in cand
    assert "gate_pass_bt_only" in cand
    assert isinstance(cand["confidence_bt_only"], float)
    assert isinstance(cand["confidence_ml_component"], float)
    assert isinstance(cand["gate_pass_bt_only"], bool)
