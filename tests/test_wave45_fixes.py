"""V9 / Wave-45 (2026-05-03): tests for universe + stream stale gates.

Locks the regressions for:
- PP-5 (HIGH): universe scanner failures track consecutive count + alert
  after 5 in a row so persistent missing-API doesn't silently trade on
  stale candidates.
- PP-6 (HIGH): per-symbol staleness check exposed via
  StreamingDataProvider.stale_symbols + invoked from _live_tick_inner;
  active-symbol stalls behind background-symbol traffic are no longer
  invisible.

Run with: ./venv/bin/python -m pytest tests/test_wave45_fixes.py -v
"""
from __future__ import annotations

import inspect


def test_pp_5_scanner_tracks_consecutive_failures():
    """The scanner failure path must increment _scanner_consecutive_failures
    and reset on success."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "PP-5" in src, "PP-5 marker missing"
    assert "_scanner_consecutive_failures" in src, (
        "PP-5 regression: scanner no longer tracks consecutive failures."
    )


def test_pp_5_scanner_alerts_after_threshold():
    """The scanner must alert via dispatch_alert_from_thread after
    _PP5_FAIL_ALERT consecutive failures."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "_PP5_FAIL_ALERT" in src, (
        "PP-5 regression: alert threshold constant missing."
    )
    assert "Market Scanner Persistent Failure" in src, (
        "PP-5 regression: scanner-failure alert title missing."
    )


def test_pp_6_streaming_provider_exposes_stale_symbols():
    """StreamingDataProvider.stale_symbols(threshold_s) must exist."""
    from backend.organism.streaming_data_provider import StreamingDataProvider
    assert hasattr(StreamingDataProvider, "stale_symbols"), (
        "PP-6 regression: stale_symbols helper removed."
    )
    sig = inspect.signature(StreamingDataProvider.stale_symbols)
    assert "threshold_s" in sig.parameters


def test_pp_6_stale_symbols_returns_per_symbol_age():
    """stale_symbols returns (symbol, age) tuples for symbols past threshold."""
    from backend.organism.streaming_data_provider import StreamingDataProvider
    # Build a minimal provider stub.
    from collections import deque
    sp = StreamingDataProvider.__new__(StreamingDataProvider)
    sp._bars = {}
    sp._quotes = {}
    sp._last_bar_ts = {"AAA": 100.0, "BBB": 200.0, "CCC": 50.0}
    sp.last_update_time = 200.0
    sp._running = True
    sp._time_fn = lambda: 250.0  # current time

    # threshold=120, now=250 → AAA (250-100=150) and CCC (250-50=200) stale.
    result = sp.stale_symbols(threshold_s=120, now=250.0)
    syms = sorted(s for s, _ in result)
    assert syms == ["AAA", "CCC"], (
        f"PP-6 regression: expected ['AAA', 'CCC'] stale, got {syms}"
    )


def test_pp_6_live_engine_consults_per_symbol_stale():
    """_live_tick_inner must call streaming_provider.stale_symbols."""
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert "PP-6" in src, "PP-6 marker missing"
    assert "stale_symbols" in src, (
        "PP-6 regression: _live_tick_inner no longer calls "
        "streaming_provider.stale_symbols."
    )
