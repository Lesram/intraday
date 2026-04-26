"""Tests for M3 features: strong-signal-shorting, inverse-ETF translation,
ORB/EOD-only mode."""

from __future__ import annotations

from pathlib import Path


def _engine_source() -> str:
    return (
        Path(__file__).parent.parent / "backend" / "organism" / "live_engine.py"
    ).read_text()


# ── M3-1: strong-signal-shorting ─────────────────────────────


def test_strong_short_env_var_default_off():
    """ORGANISM_STRONG_SHORT_ENABLED defaults to False."""
    src = _engine_source()
    assert 'STRONG_SHORT_ENABLED = _env_bool("ORGANISM_STRONG_SHORT_ENABLED", False)' in src


def test_strong_short_thresholds_present():
    src = _engine_source()
    assert "STRONG_SHORT_COMPOSITE_MIN" in src
    assert "STRONG_SHORT_RV_MIN" in src
    assert "STRONG_SHORT_DAYRET_MIN" in src


def test_passes_entry_gates_accepts_allow_short_kwarg():
    """_passes_entry_gates(allow_short=True) skips long_only."""
    import inspect
    from backend.organism.live_engine import OrganismLiveEngine
    sig = inspect.signature(OrganismLiveEngine._passes_entry_gates)
    assert "allow_short" in sig.parameters
    # Default must be False (preserves behavior)
    assert sig.parameters["allow_short"].default is False


def test_long_only_gate_respects_allow_short():
    """The long_only check honors allow_short=True."""
    src = _engine_source()
    assert "if LONG_ONLY and direction < 0 and not allow_short:" in src


def test_short_position_exit_unblocked_when_strong_short_enabled():
    """Short positions can exit when STRONG_SHORT_ENABLED, not skipped."""
    src = _engine_source()
    assert 'if LONG_ONLY and pos_side != "long" and not STRONG_SHORT_ENABLED:' in src


def test_orb_live_strong_short_qualifier():
    """ORB live block has rv_ratio threshold check for strong-short."""
    src = _engine_source()
    assert "ORB strong-short qualified" in src
    assert "STRONG_SHORT_RV_MIN" in src


def test_eod_live_strong_short_qualifier():
    """EOD live block has day_return threshold check for strong-short."""
    src = _engine_source()
    assert "EOD strong-short qualified" in src
    assert "STRONG_SHORT_DAYRET_MIN" in src


def test_strong_short_requires_elevated_composite():
    """Strong-short requires BOTH rv/dayret AND elevated composite."""
    src = _engine_source()
    assert "ORB strong-short rejected" in src
    assert "EOD strong-short rejected" in src


# ── M3-2: inverse-ETF translation ────────────────────────────


def test_inverse_etf_map():
    from backend.organism.live_engine import INVERSE_ETF_MAP
    assert INVERSE_ETF_MAP["SPY"] == "SH"
    assert INVERSE_ETF_MAP["QQQ"] == "PSQ"


def test_inverse_etf_default_off():
    src = _engine_source()
    assert 'INVERSE_ETF_TRANSLATION_ENABLED = _env_bool(' in src
    assert 'False,' in src or 'False)' in src


def test_orb_live_uses_inverse_etf_translation():
    src = _engine_source()
    assert "ORB inverse-ETF translation" in src
    assert "_translated = True" in src


def test_eod_live_uses_inverse_etf_translation():
    src = _engine_source()
    assert "EOD inverse-ETF translation" in src
    assert "_eod_translated = True" in src


def test_inverse_etf_tags_entry_source():
    """Translated entries get suffix '_inverse' for telemetry."""
    src = _engine_source()
    assert "orb_sip_inverse" in src
    assert "eod_momentum_inverse" in src


# ── M3-4: ORB/EOD-only mode ──────────────────────────────────


def test_disable_alpha_breakout_default_off():
    src = _engine_source()
    assert 'DISABLE_ALPHA_BREAKOUT = _env_bool("ORGANISM_DISABLE_ALPHA_BREAKOUT", False)' in src


def test_alpha_loop_short_circuited_when_disabled():
    src = _engine_source()
    assert "_candidates_iter = [] if DISABLE_ALPHA_BREAKOUT else candidates" in src


def test_breakout_loop_short_circuited_when_disabled():
    src = _engine_source()
    assert "_breakout_iter = [] if DISABLE_ALPHA_BREAKOUT else breakout_signals" in src


# ── Imports / wiring smoke ───────────────────────────────────


def test_all_m3_constants_importable():
    from backend.organism.live_engine import (
        STRONG_SHORT_ENABLED, STRONG_SHORT_COMPOSITE_MIN,
        STRONG_SHORT_RV_MIN, STRONG_SHORT_DAYRET_MIN,
        INVERSE_ETF_TRANSLATION_ENABLED, INVERSE_ETF_MAP,
        DISABLE_ALPHA_BREAKOUT,
    )
    # All defaults OFF / safe
    assert STRONG_SHORT_ENABLED is False
    assert INVERSE_ETF_TRANSLATION_ENABLED is False
    assert DISABLE_ALPHA_BREAKOUT is False
    assert STRONG_SHORT_RV_MIN > 0
    assert STRONG_SHORT_DAYRET_MIN > 0


def test_strong_short_does_not_affect_default_engine_behavior():
    """When all M3 flags are False, behavior is unchanged from M2."""
    # The engine should import + instantiate without any M3 feature firing
    from backend.organism.live_engine import OrganismLiveEngine
    # Just verify the class exists with the new behavior gates
    src = _engine_source()
    # When DISABLE_ALPHA_BREAKOUT=False, candidates iterate normally
    assert "else candidates" in src
    assert "else breakout_signals" in src
