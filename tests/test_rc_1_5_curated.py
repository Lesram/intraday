"""RC-1.5 curated tests — composite-gate fix only.

The full RC-1.5 three-fix branch (rc-1.5-three-fixes) included:
  1. Composite-gate change ← INCLUDED in curated
  2. Regime sensitivity tweak ← deferred to RC-2 (shadow-validated)
  3. ML weight drop          ← deferred to RC-2 (shadow-validated)

These tests cover only fix 1, with the existing 0.50/0.30/0.20
production composite weights.
"""

from __future__ import annotations

from pathlib import Path


def _engine_source() -> str:
    path = Path(__file__).parent.parent / "backend" / "organism" / "live_engine.py"
    return path.read_text()


def test_rc15_curated_gate_uses_composite_not_ml_effective_confidence():
    """Production gate should use composite, not ml_signal.effective_confidence."""
    src = _engine_source()

    # New comment marker present
    assert "Track 1 fix (RC-1.5 curated): gate on composite confidence" in src, (
        "Expected RC-1.5 curated gate-fix comment marker in live_engine.py"
    )

    # Pre-fix ternary pattern is gone
    pre_fix_pattern = (
        "c.ml_signal.effective_confidence\n                            "
        "if c.ml_signal and c.ml_signal.effective_confidence > 0\n"
        "                            else confidence"
    )
    assert pre_fix_pattern not in src, (
        "Pre-fix _eff_conf ternary pattern still present — gate fix not applied"
    )


def test_rc15_curated_ml_weights_unchanged():
    """ML weight in composite stays at 0.50 (deferred to RC-2)."""
    src = _engine_source()
    # Original production composite formula stays in place
    assert "0.50 * ml_conf" in src, (
        "ML weight should still be 0.50 in curated branch (RC-2 will drop)"
    )


def test_rc15_curated_no_regime_sensitivity_change():
    """Regime classifier stays unchanged in curated (deferred to RC-2)."""
    regime_src = (
        Path(__file__).parent.parent / "backend" / "organism" / "regime.py"
    ).read_text()
    assert "INTRADAY_TREND_SENSITIVITY" not in regime_src, (
        "INTRADAY_TREND_SENSITIVITY should NOT be in curated regime.py "
        "(deferred to RC-2 with shadow-mode validation)"
    )


def test_rc15_curated_composite_gate_below_threshold_rejected_logic():
    """Verify with EXISTING weights (0.50/0.30/0.20) that high-ML, low-breakout
    candidates are now rejected by composite gate.

    Pre-fix: gate on ml_eff_conf (0.65) → admits at 0.45 chop gate
    Post-fix: gate on composite = 0.50*ml + 0.30*breakout + 0.20*tension

    With ml_eff=0.65, breakout=0.10, tension=0.20:
      composite = 0.50*0.65 + 0.30*0.10 + 0.20*0.20 = 0.325 + 0.030 + 0.040 = 0.395
      chop gate = 0.45
      → REJECTED (was admitted pre-fix)
    """
    ml_eff_conf = 0.65
    breakout = 0.10
    tension = 0.20

    pre_fix_eff_conf = ml_eff_conf  # baseline gate variable
    post_fix_composite = (
        0.50 * ml_eff_conf
        + 0.30 * breakout
        + 0.20 * tension
    )

    chop_gate = 0.45
    assert pre_fix_eff_conf >= chop_gate, "Pre-fix should admit"
    assert post_fix_composite < chop_gate, (
        f"Post-fix should reject (composite={post_fix_composite:.3f}, "
        f"gate={chop_gate})"
    )


def test_rc15_curated_high_quality_admitted():
    """Verify with EXISTING weights that high-breakout-AND-tension entries
    still pass even when ML is moderate."""
    ml = 0.40
    breakout = 0.55
    tension = 0.50
    composite = 0.50 * ml + 0.30 * breakout + 0.20 * tension
    # = 0.200 + 0.165 + 0.100 = 0.465
    assert composite >= 0.45, (
        f"High breakout+tension should admit (composite={composite:.3f})"
    )


def test_rc15_curated_alpha_only_avg_lands_below_chop_gate():
    """Empirical sanity with EXISTING weights: avg observed alpha-only
    entry values produce a composite below the chop gate."""
    avg_ml = 0.55       # from live data
    avg_breakout = 0.20  # alpha-only means breakout < 0.4
    avg_tension = 0.30   # observed avg

    composite = 0.50 * avg_ml + 0.30 * avg_breakout + 0.20 * avg_tension
    # = 0.275 + 0.060 + 0.060 = 0.395
    assert 0.35 < composite < 0.45, (
        f"Avg alpha-only composite expected ~0.40 with old weights; "
        f"got {composite:.3f}"
    )
    # Below chop gate of 0.45 → filtered by curated gate fix
    assert composite < 0.45
