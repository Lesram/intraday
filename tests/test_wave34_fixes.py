"""V8 / Wave-34 (2026-05-03): behavioral tests for regime + Kelly + telemetry fixes.

Locks the regressions for:
- DD2-3: detect_market_regime / detect_cross_asset_regime now accumulate
  `_aggregate_history` and compute churn_rate from it (was hard-coded 0).
- DD2-4: detect() applies a hysteresis band so primary doesn't flap on
  one-bar slope flips at threshold boundaries.
- DD2-5: Kelly's _regime_eligible branch refuses to size when atr_var is
  below _ATR_VAR_MIN (was bypassing wave-18's zero-vol refusal).
- NN-HIGH-1: tick_telemetry write failures now log at WARNING (were DEBUG).

Deferred to wave 38 / 36:
- DD2-6: inverse-ETF regime flip refactor (multi-site; replay-determinism risk)
- BB2-F2: 6 dark tables (executions, positions, order_events, risk_violations,
  daily_ledger) wire-or-drop decision

Run with: ./venv/bin/python -m pytest tests/test_wave34_fixes.py -v
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pandas as pd
import pytest


# ─────────────────────────────────────────────────────────────────────
# DD2-3 — aggregate-level churn accumulates
# ─────────────────────────────────────────────────────────────────────


def test_dd2_3_aggregate_history_field_present():
    """RegimeDetector tracks an _aggregate_history list separate from
    the per-symbol _history (which the per-symbol detect()s save/restore)."""
    from backend.organism.regime import RegimeDetector
    det = RegimeDetector()
    assert hasattr(det, "_aggregate_history"), (
        "DD2-3 regression: RegimeDetector lost _aggregate_history. "
        "Market-level churn would be hard-zeroed again."
    )
    assert isinstance(det._aggregate_history, list)


def test_dd2_3_market_regime_appends_to_aggregate_history():
    """detect_market_regime must append the aggregate primary to
    _aggregate_history so churn accumulates across calls."""
    from backend.organism.regime import RegimeDetector

    det = RegimeDetector()
    # Build minimal feature DataFrames with valid ATR and stable trend.
    df_up = _make_features(closes=[100.0 + i * 0.01 for i in range(20)])
    df_down = _make_features(closes=[100.0 - i * 0.01 for i in range(20)])

    state1 = det.detect_market_regime({"AAA": df_up, "BBB": df_up})
    n_after_first = len(det._aggregate_history)
    state2 = det.detect_market_regime({"AAA": df_down, "BBB": df_down})
    n_after_second = len(det._aggregate_history)
    assert n_after_first == 1, (
        f"DD2-3 regression: first detect_market_regime did not append "
        f"to _aggregate_history (len={n_after_first}, expected 1)"
    )
    assert n_after_second == 2, (
        f"DD2-3 regression: second detect_market_regime did not append "
        f"(len={n_after_second}, expected 2)"
    )


def test_dd2_3_churn_rate_nonzero_when_regime_flips():
    """When the aggregate primary alternates, churn_rate must be > 0
    (was hard-coded 0.0 in V7-era market regime)."""
    from backend.organism.regime import RegimeDetector
    det = RegimeDetector()
    # Drive 20 alternating flips to build up churn signal.
    df_up = _make_features(closes=[100.0 + i * 0.5 for i in range(40)])
    df_flat = _make_features(closes=[100.0] * 40)
    last_state = None
    for i in range(20):
        feats = df_up if i % 2 == 0 else df_flat
        last_state = det.detect_market_regime({"AAA": feats, "BBB": feats})
    assert last_state is not None
    # We don't assert exact value, but it must be > 0 if alternation occurred.
    assert last_state.churn_rate >= 0.0, (
        "Got negative churn_rate, math is broken"
    )
    # If history has at least 2 distinct labels, churn must be > 0.
    if len(set(det._aggregate_history)) >= 2:
        assert last_state.churn_rate > 0.0, (
            f"DD2-3 regression: aggregate_history has multiple labels "
            f"({set(det._aggregate_history)}) but churn_rate={last_state.churn_rate}. "
            "Should be > 0."
        )


# ─────────────────────────────────────────────────────────────────────
# DD2-4 — regime hysteresis
# ─────────────────────────────────────────────────────────────────────


def test_dd2_4_hysteresis_band_attribute_exists():
    """Wave-34 introduces _hysteresis_band on RegimeDetector."""
    from backend.organism.regime import RegimeDetector
    det = RegimeDetector()
    assert hasattr(det, "_hysteresis_band"), (
        "DD2-4 regression: RegimeDetector lost _hysteresis_band. "
        "Argmax flapping at threshold boundaries returns."
    )
    assert det._hysteresis_band > 0.0, (
        f"DD2-4 regression: _hysteresis_band={det._hysteresis_band} "
        "must be > 0 to suppress one-bar flips."
    )


def test_dd2_4_detect_uses_hysteresis_in_argmax():
    """detect() source must reference _hysteresis_band — guards against
    a future refactor that removes the band."""
    import inspect
    from backend.organism.regime import RegimeDetector
    src = inspect.getsource(RegimeDetector.detect)
    assert "_hysteresis_band" in src, (
        "DD2-4 regression: detect() does not consult _hysteresis_band."
    )


# ─────────────────────────────────────────────────────────────────────
# DD2-5 — Kelly _regime_eligible respects zero-vol refusal
# ─────────────────────────────────────────────────────────────────────


def test_dd2_5_regime_eligible_branch_checks_atr_var():
    """Kelly's regime_eligible decision must include an atr_var floor
    check (parity with the unconditional path's _ATR_VAR_MIN gate)."""
    import inspect
    from backend.organism.kelly_sizer import KellySizer
    src = inspect.getsource(KellySizer)
    # Locate the production branch and check for _ATR_VAR_MIN reference
    # in the eligibility condition.
    assert "_atr_var_squared_pre" in src, (
        "DD2-5 regression: Kelly's _regime_eligible no longer evaluates "
        "atr_var up-front. Zero-volatility bars can size from regime_kelly."
    )
    # The _regime_eligible expression should reference the floor check.
    eligible_block = src[src.find("_regime_eligible = ("):src.find("_regime_eligible = (") + 400]
    assert "_ATR_VAR_MIN" in eligible_block or "_atr_var_squared_pre" in eligible_block, (
        "DD2-5 regression: _regime_eligible does not gate on atr_var."
    )


# ─────────────────────────────────────────────────────────────────────
# NN-HIGH-1 — tick_telemetry surfaces errors at WARNING
# ─────────────────────────────────────────────────────────────────────


def test_nn_high_1_telemetry_write_logs_at_warning_on_failure():
    """The tick_telemetry write block must log at WARNING (not DEBUG)
    when DB writes fail.  The V7-era DEBUG silently masked the
    zero-rows-in-DB issue."""
    import inspect
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    # Locate the telemetry write block and verify it warns on failure.
    idx = src.find("Telemetry DB write")
    assert idx > 0, (
        "NN-HIGH-1 regression: telemetry write block missing"
    )
    # Pull a window around the catch site.
    window = src[idx - 200:idx + 200]
    assert "logger.warning" in window, (
        "NN-HIGH-1 regression: telemetry write failures still logged at "
        "DEBUG (or other suppressed level). Operator should see WARN."
    )


async def test_nn_high_1_telemetry_write_failure_warns_behaviorally(monkeypatch):
    """Behavioral: a DB write failure increments the visible error counter
    and emits the telemetry warning instead of disappearing silently."""
    import backend.infra.db as db
    from backend.organism import live_engine

    class BrokenSessionContext:
        async def __aenter__(self):
            raise RuntimeError("telemetry db unavailable")

        async def __aexit__(self, exc_type, exc, tb):
            return False

    warnings: list[tuple[str, tuple[object, ...]]] = []

    def fake_warning(msg, *args, **kwargs):
        warnings.append((msg, args))

    filtering = SimpleNamespace(
        entries_blocked_reason=None,
        orders_submitted=0,
        to_dict=lambda: {"rejections": {"risk": 1}},
    )
    snap = SimpleNamespace(
        tick_number=42,
        regime="neutral",
        equity=100_000.0,
        drawdown_pct=0.0,
        open_positions=0,
        filtering=filtering,
        alpha_details=[],
        exit_details=[],
    )
    engine = SimpleNamespace(
        _sessionmaker=object(),
        _telemetry=SimpleNamespace(latest=snap),
    )

    monkeypatch.setattr(db, "get_session_context", lambda: BrokenSessionContext())
    monkeypatch.setattr(live_engine.logger, "warning", fake_warning)

    await live_engine.OrganismLiveEngine._persist_telemetry_to_db(engine)

    assert engine._telemetry_write_errors == 1
    assert warnings
    assert warnings[0][0].startswith("Telemetry DB write FAILED")


# ─────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────


def _make_features(closes: list[float]) -> pd.DataFrame:
    """Build a minimal feature DataFrame with the columns RegimeDetector reads."""
    return pd.DataFrame({
        "close": closes,
        "atr_14": [c * 0.01 for c in closes],
        "volume": [1000] * len(closes),
    })
