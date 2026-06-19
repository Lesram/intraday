"""Audit 2026-06-09 plan 1.4 — startup timeframe assert + risk snapshot.

Verifies the engine loudly errors when time-of-day-gated strategies are
live-enabled on a non-intraday timeframe, and that a runtime risk snapshot
is logged at startup.
"""

import inspect
import logging

from backend.organism import live_engine as le
from backend.organism.live_engine import OrganismLiveEngine


class _Shim:
    _warn_if_timeframe_strands_strategies = (
        OrganismLiveEngine._warn_if_timeframe_strands_strategies
    )

    def __init__(self, is_intraday):
        self._is_intraday = is_intraday
        self._timeframe = "1Min" if is_intraday else "1Day"


def test_error_logged_when_intraday_strategy_stranded(monkeypatch, caplog):
    monkeypatch.setattr(le, "ORB_LIVE_ENABLED", True)
    monkeypatch.setattr(le, "EOD_LIVE_ENABLED", False)
    monkeypatch.setattr(le, "MEAN_REVERSION_LIVE_ENABLED", False)
    with caplog.at_level(logging.ERROR, logger="backend.organism.live_engine"):
        _Shim(is_intraday=False)._warn_if_timeframe_strands_strategies()
    assert any("TIMEFRAME MISMATCH" in r.message for r in caplog.records)
    assert any("ORB" in r.message for r in caplog.records)


def test_no_error_on_intraday_timeframe(monkeypatch, caplog):
    monkeypatch.setattr(le, "ORB_LIVE_ENABLED", True)
    with caplog.at_level(logging.ERROR, logger="backend.organism.live_engine"):
        _Shim(is_intraday=True)._warn_if_timeframe_strands_strategies()
    assert not any("TIMEFRAME MISMATCH" in r.message for r in caplog.records)


def test_no_error_when_nothing_live_enabled(monkeypatch, caplog):
    monkeypatch.setattr(le, "ORB_LIVE_ENABLED", False)
    monkeypatch.setattr(le, "EOD_LIVE_ENABLED", False)
    monkeypatch.setattr(le, "MEAN_REVERSION_LIVE_ENABLED", False)
    with caplog.at_level(logging.ERROR, logger="backend.organism.live_engine"):
        _Shim(is_intraday=False)._warn_if_timeframe_strands_strategies()
    assert not any("TIMEFRAME MISMATCH" in r.message for r in caplog.records)


def test_risk_snapshot_wired_into_init():
    src = inspect.getsource(OrganismLiveEngine.__init__)
    assert "RUNTIME RISK SNAPSHOT" in src
    assert "_warn_if_timeframe_strands_strategies()" in src
