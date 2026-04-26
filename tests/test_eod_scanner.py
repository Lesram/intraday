"""Tests for EOD Momentum Scanner."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from datetime import time as dtime


def _make_eod_df(
    days: int = 2,
    bars_per_day: int = 390,
    today_drift_pct: float = 0.5,
) -> pd.DataFrame:
    """Build a 2-day timestamped 1-min OHLCV df.

    Today (last day): open=100, drifts to 100*(1+today_drift_pct/100) by end of day.
    Bars 9:30 ET to 16:00 ET (390 bars).
    """
    rows = []
    base = pd.Timestamp("2026-04-24 09:30:00", tz="America/New_York")

    for day_offset in range(days):
        day_start = base + pd.Timedelta(days=day_offset)
        is_today = (day_offset == days - 1)
        if is_today:
            target_close = 100.0 * (1 + today_drift_pct / 100.0)
            closes = np.linspace(100.0, target_close, bars_per_day)
        else:
            closes = 100.0 + np.random.default_rng(day_offset).normal(0, 0.05, bars_per_day)
        for bar_idx in range(bars_per_day):
            ts = day_start + pd.Timedelta(minutes=bar_idx)
            c = closes[bar_idx]
            rows.append({
                "timestamp": ts.tz_convert("UTC"),
                "open": c if bar_idx == 0 else closes[bar_idx - 1],
                "high": c * 1.0005,
                "low": c * 0.9995,
                "close": c,
                "volume": 100_000.0,
                "atr_14": 0.5,
            })
    return pd.DataFrame(rows)


def test_eod_decision_window_recognition():
    from backend.organism.eod_scanner import EODMomentumScanner
    s = EODMomentumScanner()
    assert not s._is_in_decision_window(dtime(15, 29))
    assert s._is_in_decision_window(dtime(15, 30))
    assert s._is_in_decision_window(dtime(15, 49))
    assert not s._is_in_decision_window(dtime(15, 50))
    assert not s._is_in_decision_window(dtime(9, 30))


def test_eod_returns_empty_outside_window():
    from backend.organism.eod_scanner import EODMomentumScanner
    s = EODMomentumScanner()
    df = _make_eod_df(today_drift_pct=1.0)
    cands = s.scan({"TEST": df}, pd.Timestamp("2026-04-25 13:30:00", tz="UTC"))
    assert cands == []


def test_eod_long_signal_on_positive_drift():
    from backend.organism.eod_scanner import EODMomentumScanner
    s = EODMomentumScanner(min_day_return_pct=0.30)
    df = _make_eod_df(today_drift_pct=0.8)
    now_utc = pd.Timestamp("2026-04-25 19:30:00", tz="UTC")
    cands = s.scan({"TEST": df}, now_utc)
    assert len(cands) == 1
    c = cands[0]
    assert c.direction == 1.0
    assert 0.7 < c.day_return_pct < 0.9


def test_eod_short_signal_on_negative_drift():
    from backend.organism.eod_scanner import EODMomentumScanner
    s = EODMomentumScanner(min_day_return_pct=0.30)
    df = _make_eod_df(today_drift_pct=-0.6)
    now_utc = pd.Timestamp("2026-04-25 19:30:00", tz="UTC")
    cands = s.scan({"TEST": df}, now_utc)
    assert len(cands) == 1
    assert cands[0].direction == -1.0


def test_eod_no_signal_below_threshold():
    from backend.organism.eod_scanner import EODMomentumScanner
    s = EODMomentumScanner(min_day_return_pct=0.30)
    df = _make_eod_df(today_drift_pct=0.10)
    now_utc = pd.Timestamp("2026-04-25 19:30:00", tz="UTC")
    cands = s.scan({"TEST": df}, now_utc)
    assert cands == []


def test_eod_top_n_filtering():
    from backend.organism.eod_scanner import EODMomentumScanner
    s = EODMomentumScanner(top_n=2, min_day_return_pct=0.20)
    drifts = {"A": 0.5, "B": 1.0, "C": 0.3, "D": 0.8}
    fb = {sym: _make_eod_df(today_drift_pct=d) for sym, d in drifts.items()}
    now_utc = pd.Timestamp("2026-04-25 19:30:00", tz="UTC")
    cands = s.scan(fb, now_utc)
    assert len(cands) == 2
    syms = [c.symbol for c in cands]
    assert "B" in syms
    assert "D" in syms


def test_eod_mark_fired_prevents_refire():
    from backend.organism.eod_scanner import EODMomentumScanner
    s = EODMomentumScanner(min_day_return_pct=0.30)
    df = _make_eod_df(today_drift_pct=0.8)
    now_utc = pd.Timestamp("2026-04-25 19:30:00", tz="UTC")
    c1 = s.scan({"TEST": df}, now_utc)
    assert len(c1) == 1
    s.mark_fired("TEST")
    c2 = s.scan({"TEST": df}, pd.Timestamp("2026-04-25 19:32:00", tz="UTC"))
    assert all(c.symbol != "TEST" for c in c2)


def test_eod_session_reset_clears_fired():
    from backend.organism.eod_scanner import EODMomentumScanner
    s = EODMomentumScanner(min_day_return_pct=0.30)
    s._fired_today.add("FOO")
    s._current_session_date = "2026-04-24"
    df = _make_eod_df(today_drift_pct=0.8)
    s.scan({"TEST": df}, pd.Timestamp("2026-04-25 19:30:00", tz="UTC"),
           session_date="2026-04-25")
    assert "FOO" not in s._fired_today


def test_eod_imports_cleanly():
    from backend.organism.eod_scanner import (
        EODMomentumScanner, EODCandidate,
        DEFAULT_DECISION_HOUR_ET, DEFAULT_MIN_DAY_RETURN_PCT,
    )
    assert DEFAULT_DECISION_HOUR_ET == 15
    assert DEFAULT_MIN_DAY_RETURN_PCT == 0.30
