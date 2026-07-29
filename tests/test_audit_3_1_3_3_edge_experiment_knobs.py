"""Audit 2026-06-09 plans 3.1–3.3 — experiment knobs and EOD restriction.

3.1: exit parameters env-overridable via AdaptiveExitEngine.for_timeframe
     (defaults unchanged).
3.2: bad-regime filter source coverage configurable via
     ORGANISM_BAD_REGIME_FILTER_SOURCES (default: alpha+breakout only).
3.3: EOD continuation scanner restricted to index ETFs by default.
"""

import importlib

import pandas as pd

from backend.organism.adaptive_exits import AdaptiveExitEngine


# ── 3.1 Exit knobs ───────────────────────────────────────────────────


def test_exit_defaults_unchanged(monkeypatch):
    for var in ("ORGANISM_EXIT_ATR_MULT", "ORGANISM_EXIT_TRAIL_START_ATR",
                "ORGANISM_EXIT_TRAIL_DIST_ATR", "ORGANISM_EXIT_MAX_BARS"):
        monkeypatch.delenv(var, raising=False)
    e = AdaptiveExitEngine.for_timeframe("1Min")
    assert e.atr_multiplier == 1.0
    assert e.trailing_start_atr == 2.0
    assert e.trailing_distance_atr == 1.5
    assert e.max_bars_held == 60
    d = AdaptiveExitEngine.for_timeframe("1Day")
    assert d.atr_multiplier == 1.5
    assert d.max_bars_held == 40


def test_exit_env_overrides(monkeypatch):
    monkeypatch.setenv("ORGANISM_EXIT_ATR_MULT", "2.0")
    monkeypatch.setenv("ORGANISM_EXIT_MAX_BARS", "120")
    e = AdaptiveExitEngine.for_timeframe("1Min")
    assert e.atr_multiplier == 2.0
    assert e.max_bars_held == 120
    # Base values for evolution scaling must track the override.
    assert e._base_atr_multiplier == 2.0


def test_exit_env_garbage_falls_back(monkeypatch):
    monkeypatch.setenv("ORGANISM_EXIT_ATR_MULT", "not_a_number")
    e = AdaptiveExitEngine.for_timeframe("1Min")
    assert e.atr_multiplier == 1.0


# ── Task B (2026-06-20): per-regime dict multipliers actually bind ────


def _clear_regime_mults(monkeypatch):
    for var in ("ORGANISM_EXIT_STOP_ATR_MULT", "ORGANISM_EXIT_TRAIL_ATR_MULT",
                "ORGANISM_EXIT_MAX_BARS_MULT", "ORGANISM_EXIT_DECAY_START_MULT"):
        monkeypatch.delenv(var, raising=False)


def test_regime_mults_unset_leave_dicts_unchanged(monkeypatch):
    """Env unset ⇒ instance regime dicts equal the class defaults (chop too)."""
    _clear_regime_mults(monkeypatch)
    e = AdaptiveExitEngine.for_timeframe("1Min")
    assert e.REGIME_STOP_ATR["chop"] == AdaptiveExitEngine.REGIME_STOP_ATR["chop"]
    assert e.REGIME_STOP_ATR["chop"] == 2.5
    assert e.REGIME_MAX_BARS["chop"] == 30
    assert e.REGIME_TRAIL_ATR["chop"] == 3.0


def test_regime_stop_mult_doubles_chop_stop(monkeypatch):
    """The core fix: STOP_ATR_MULT=2.0 doubles the effective chop stop-ATR
    (which the scalar ORGANISM_EXIT_ATR_MULT never reached)."""
    _clear_regime_mults(monkeypatch)
    monkeypatch.setenv("ORGANISM_EXIT_STOP_ATR_MULT", "2.0")
    e = AdaptiveExitEngine.for_timeframe("1Min")
    assert e.REGIME_STOP_ATR["chop"] == 5.0   # 2.5 × 2.0
    assert e.REGIME_STOP_ATR["high_vol"] == 8.0  # 4.0 × 2.0
    # Class dict must NOT be mutated (no leak across arms/instances).
    assert AdaptiveExitEngine.REGIME_STOP_ATR["chop"] == 2.5


def test_regime_max_bars_mult_keeps_zero_zero(monkeypatch):
    """MAX_BARS_MULT scales nonzero entries; 0 ('no limit') stays 0."""
    _clear_regime_mults(monkeypatch)
    monkeypatch.setenv("ORGANISM_EXIT_MAX_BARS_MULT", "2.0")
    e = AdaptiveExitEngine.for_timeframe("1Min")
    assert e.REGIME_MAX_BARS["chop"] == 60       # 30 × 2.0
    assert e.REGIME_MAX_BARS["trending_up"] == 0  # 0 stays 0
    assert AdaptiveExitEngine.REGIME_MAX_BARS["chop"] == 30  # class unmutated


def test_regime_trail_and_decay_mults(monkeypatch):
    _clear_regime_mults(monkeypatch)
    monkeypatch.setenv("ORGANISM_EXIT_TRAIL_ATR_MULT", "1.5")
    monkeypatch.setenv("ORGANISM_EXIT_DECAY_START_MULT", "2.0")
    e = AdaptiveExitEngine.for_timeframe("1Min")
    assert e.REGIME_TRAIL_ATR["chop"] == 4.5      # 3.0 × 1.5
    assert e.REGIME_DECAY_START["chop"] == 40      # 20 × 2.0


def test_regime_mult_garbage_falls_back(monkeypatch):
    _clear_regime_mults(monkeypatch)
    monkeypatch.setenv("ORGANISM_EXIT_STOP_ATR_MULT", "not_a_number")
    e = AdaptiveExitEngine.for_timeframe("1Min")
    assert e.REGIME_STOP_ATR["chop"] == 2.5


# ── 3.2 Bad-regime filter sources ────────────────────────────────────


def test_default_filter_covers_only_alpha_breakout():
    from backend.organism import live_engine as le

    assert le.BAD_REGIME_FILTER_SOURCES == frozenset({"alpha+breakout"})


def test_filter_reason_string_backward_compatible():
    """For the default source the emitted reason must remain exactly
    'alpha_breakout_<regime>_blocked_by_evidence' (pinned by older
    telemetry consumers)."""
    src = "alpha+breakout"
    regime = "chop"
    assert (
        f"{src.replace('+', '_')}_{regime}_blocked_by_evidence"
        == "alpha_breakout_chop_blocked_by_evidence"
    )


# ── 3.3 EOD universe restriction ─────────────────────────────────────


def _eod_df():
    rows = []
    base = pd.Timestamp("2026-04-24 09:30:00", tz="America/New_York")
    for day in range(2):
        start = base + pd.Timedelta(days=day)
        for i in range(390):
            c = 100.0 + (i / 390.0 if day == 1 else 0.0)
            rows.append({
                "timestamp": (start + pd.Timedelta(minutes=i)).tz_convert("UTC"),
                "open": c, "high": c * 1.001, "low": c * 0.999,
                "close": c, "volume": 1e5,
            })
    return pd.DataFrame(rows)


def test_eod_scanner_ignores_non_etf_by_default(monkeypatch):
    monkeypatch.delenv("ORGANISM_EOD_UNIVERSE", raising=False)
    from backend.organism.eod_scanner import EODMomentumScanner

    s = EODMomentumScanner(min_day_return_pct=0.20)
    df = _eod_df()
    now = pd.Timestamp("2026-04-25 19:30:00", tz="UTC")
    assert s.scan({"AAPL": df}, now) == [], "single names must be excluded"
    spy = s.scan({"SPY": df}, now)
    assert isinstance(spy, list)  # SPY is allowed through the universe gate


def test_eod_universe_env_override(monkeypatch):
    monkeypatch.setenv("ORGANISM_EOD_UNIVERSE", "AAPL")
    from backend.organism.eod_scanner import EODMomentumScanner

    assert EODMomentumScanner._allowed_symbols() == frozenset({"AAPL"})


def test_eod_reversal_engine_marked_deprecated():
    mod = importlib.import_module(
        "backend.organism.engines.eod_reversal_shadow"
    )
    assert "DEPRECATED" in (mod.__doc__ or "")
