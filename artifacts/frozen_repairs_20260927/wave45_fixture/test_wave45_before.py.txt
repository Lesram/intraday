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
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _stream_health_engine(*, tick: int = 30, provider=None):
    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._streaming_provider = provider
    engine._tick_count = tick
    return engine


def _staleness_engine(
    *,
    provider,
    data_stale: bool = False,
    now: float = 250.0,
    threshold: float = 120.0,
):
    from backend.organism.live_engine import OrganismLiveEngine

    engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
    engine._streaming_provider = provider
    engine._data_stale = data_stale
    engine._DATA_STALE_THRESHOLD_S = threshold
    engine._time_fn = lambda: now
    return engine


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
    """The extracted staleness stage must call provider.stale_symbols."""
    from backend.organism.live_engine import OrganismLiveEngine
    assert hasattr(OrganismLiveEngine, "_stage_update_data_staleness"), (
        "P7.2 regression: stream staleness stage helper removed."
    )
    src = inspect.getsource(OrganismLiveEngine._stage_update_data_staleness)
    assert "PP-6" in src, "PP-6 marker missing"
    assert "stale_symbols" in src, (
        "PP-6 regression: staleness stage no longer calls "
        "streaming_provider.stale_symbols."
    )


@pytest.mark.asyncio
async def test_p7_stream_health_recovery_appends_activity_event():
    """Every 30 ticks, a recovered stale stream surfaces operator activity."""
    from backend.organism.live_engine import LiveTickResult

    provider = SimpleNamespace(
        check_and_recover_stale_stream=AsyncMock(return_value=True),
    )
    engine = _stream_health_engine(tick=30, provider=provider)
    result = LiveTickResult()

    await engine._stage_check_stream_health(result, "2026-05-06T05:00:00Z")

    provider.check_and_recover_stale_stream.assert_awaited_once()
    assert len(result.activity) == 1
    assert result.activity[0].event_type == "stream"
    assert "reconnect attempted" in result.activity[0].message
    assert result.activity[0].timestamp == "2026-05-06T05:00:00Z"


@pytest.mark.asyncio
async def test_p7_stream_health_skips_between_probe_ticks():
    """Stream recovery check keeps the existing every-30-tick cadence."""
    from backend.organism.live_engine import LiveTickResult

    provider = SimpleNamespace(
        check_and_recover_stale_stream=AsyncMock(return_value=True),
    )
    engine = _stream_health_engine(tick=29, provider=provider)
    result = LiveTickResult()

    await engine._stage_check_stream_health(result, "2026-05-06T05:00:00Z")

    provider.check_and_recover_stale_stream.assert_not_awaited()
    assert result.activity == []


def test_p7_staleness_stage_marks_aggregate_stale():
    """Aggregate provider staleness flips the live entry data flag on."""
    provider = SimpleNamespace(last_update_time=100.0)
    engine = _staleness_engine(provider=provider, now=250.0, threshold=120.0)

    engine._stage_update_data_staleness()

    assert engine._data_stale is True


def test_p7_staleness_stage_clears_when_stream_recovers():
    """A fresh aggregate timestamp clears a prior stale-data state."""
    provider = SimpleNamespace(last_update_time=240.0)
    engine = _staleness_engine(
        provider=provider,
        data_stale=True,
        now=250.0,
        threshold=120.0,
    )

    engine._stage_update_data_staleness()

    assert engine._data_stale is False


def test_p7_staleness_stage_marks_per_symbol_stale_when_aggregate_fresh():
    """PP-6: per-symbol stalls still block entries behind fresh aggregate data."""
    calls = []

    def stale_symbols(*, threshold_s, now):
        calls.append((threshold_s, now))
        return [("AAA", 150.0)]

    provider = SimpleNamespace(
        last_update_time=240.0,
        stale_symbols=stale_symbols,
    )
    engine = _staleness_engine(provider=provider, now=250.0, threshold=120.0)

    engine._stage_update_data_staleness()

    assert engine._data_stale is True
    assert calls == [(120.0, 250.0)]
