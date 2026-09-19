"""Task S — log-only retracement shadow exit (SHADOW_EXIT_AND_CORPUS_BRIEF).

Covers: (1) flag-off => the evaluator is a no-op, no telemetry; (2) the mixin
records a shadow trigger and writes ONE comparison row on real close;
(3) the real AltExitEngine retracement policy fires on a peak-then-retrace path.
"""
from __future__ import annotations

from types import SimpleNamespace

from backend.organism.adaptive_exits import ExitLevels
from backend.organism.experimental.alt_exit_engine import AltExitEngine
from backend.organism.experimental.shadow_exit import (
    ShadowExitTelemetryRecorder,
    _ShadowExitMixin,
)


def _levels(sym="AAPL", entry=100.0):
    return ExitLevels(
        symbol=sym, direction=1.0, entry_price=entry, stop_loss=entry - 1,
        take_profit=entry + 100, trailing_stop=entry - 1, atr_at_entry=1.0,
        regime_at_entry="trending_up", highest_favorable=entry,
        initial_risk_at_entry=1.0,
    )


def _host(recorder, engine):
    """Minimal host exposing the attributes _shadow_evaluate_exits reads."""
    return SimpleNamespace(
        _shadow_exit=recorder,
        _shadow_engine=engine,
        _shadow_levels={}, _shadow_pending={}, _shadow_prev_syms=set(),
        _shadow_last_price={}, _shadow_bar_seen={},
        exit_engine=SimpleNamespace(learning_mode=False),
        _exit_levels={}, _last_prices={}, _last_regime="trending_up",
        _last_positions={}, _last_bar_times={}, _symbol_exit_type={},
        _tick_count=0, _now_fn=lambda: __import__("datetime").datetime(2026, 6, 23),
    )


def _eval(host):
    _ShadowExitMixin._shadow_evaluate_exits(host, SimpleNamespace())


def test_flag_off_is_noop(tmp_path):
    host = _host(None, None)
    host._exit_levels = {"AAPL": _levels()}
    host._last_prices = {"AAPL": 105.0}
    host._last_bar_times = {"AAPL": "t1"}
    _eval(host)  # _shadow_exit is None => returns immediately
    assert not list(tmp_path.glob("*.jsonl"))


def test_records_and_reconciles_on_close(tmp_path):
    rec = ShadowExitTelemetryRecorder(tmp_path / "shadow.jsonl")
    # Stub engine: forces an exit signal (isolates the mixin's record/reconcile).
    eng = SimpleNamespace(
        learning_mode=False, alt_policy="retracement",
        alt_retrace_frac=0.6, alt_min_fav_r=1.0,
        check_exit=lambda lv, p, r, is_new_bar: SimpleNamespace(
            should_exit=True, reason="alt_retracement"),
    )
    host = _host(rec, eng)
    host._exit_levels = {"AAPL": _levels()}
    host._last_positions = {"AAPL": {"qty": 10}}
    host._last_prices = {"AAPL": 103.0}
    host._last_bar_times = {"AAPL": "t1"}

    _eval(host)  # tick 1: position open, stub triggers => pending stashed
    assert "AAPL" in host._shadow_pending
    assert rec.rows_written == 0  # nothing written until the real close

    host._exit_levels = {}  # tick 2: real position closed
    host._symbol_exit_type = {"AAPL": "stop_loss"}
    _eval(host)

    assert rec.rows_written == 1
    row = (tmp_path / "shadow.jsonl").read_text().strip()
    import json
    d = json.loads(row)
    assert d["symbol"] == "AAPL"
    assert d["shadow_triggered"] is True
    assert d["shadow_reason"] == "alt_retracement"
    assert d["real_exit_reason"] == "stop_loss"
    assert "delta_gross" in d
    # cleaned up after reconcile
    assert "AAPL" not in host._shadow_levels


def test_retracement_policy_fires_on_peak_then_retrace():
    """The real AltExitEngine retracement policy: rise past min_fav_R, then
    give back > frac of the peak => alt_retracement."""
    eng = AltExitEngine.for_timeframe("1Min")
    eng.alt_policy = "retracement"
    eng.alt_retrace_frac = 0.6
    eng.alt_min_fav_r = 1.0
    eng.learning_mode = False
    lv = _levels()  # entry 100, risk 1.0, take_profit 200 (far)

    # Climb to a peak (>=1R favorable), one new bar each step, past min-hold (5).
    fired = None
    for p in (100.5, 101.0, 101.5, 102.0, 102.0, 102.0):
        sig = eng.check_exit(lv, p, "trending_up", is_new_bar=True)
        assert not sig.should_exit, f"unexpected early exit at {p}: {sig.reason}"
    # Retrace to 100.5: cur_exc=0.5 <= (1-0.6)*peak(2.0)=0.8 => trigger.
    sig = eng.check_exit(lv, 100.5, "trending_up", is_new_bar=True)
    fired = sig
    assert fired.should_exit and fired.reason == "alt_retracement", fired.reason
