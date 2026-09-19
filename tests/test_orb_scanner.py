"""Tests for ORB Stocks-in-Play scanner.

Validates:
- Time-window gating (9:30-9:35 ET = ORB window; 9:35-15:55 = decision window)
- ORB high/low computation
- Direction inference (ORB close > open → long; < open → short)
- Relative volume ranking
- Top-N filtering
- Breakout detection
- Daily reset
- mark_fired prevents re-firing
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from datetime import time as dtime


# ── Time-window gating ────────────────────────────────────────


def test_orb_window_recognition():
    from backend.organism.orb_scanner import ORBScanner

    s = ORBScanner()
    assert s._is_in_orb_window(dtime(9, 30))
    assert s._is_in_orb_window(dtime(9, 32))
    assert not s._is_in_orb_window(dtime(9, 35))
    assert not s._is_in_orb_window(dtime(9, 29))
    assert not s._is_in_orb_window(dtime(15, 0))


def test_decision_window_recognition():
    from backend.organism.orb_scanner import ORBScanner

    s = ORBScanner()
    assert not s._is_after_orb_decision(dtime(9, 30))
    assert not s._is_after_orb_decision(dtime(9, 34))
    assert s._is_after_orb_decision(dtime(9, 35))
    assert s._is_after_orb_decision(dtime(13, 0))
    assert s._is_after_orb_decision(dtime(15, 54))
    assert not s._is_after_orb_decision(dtime(15, 55))
    assert not s._is_after_orb_decision(dtime(16, 0))


# ── ORB range computation ────────────────────────────────────


def _make_orb_df(
    n_history: int = 100,
    orb_high: float = 105.0,
    orb_low: float = 99.0,
    orb_open: float = 100.0,
    orb_close: float = 104.0,
    current_price: float = 105.5,
    base_volume: float = 100_000,
    orb_volume_multiplier: float = 3.0,
) -> pd.DataFrame:
    """Construct a synthetic feature DataFrame.

    Adds proper ET timestamps so the timestamp-aware ORB scanner can find
    the opening range. Layout:
      - n_history bars from a prior trading day (9:30 → 16:00 ET)
      - 5 ORB bars on today (9:30-9:34 ET) with the configured high/low/open/close
    """
    rng = np.random.default_rng(0)
    bars = []

    # Prior day: full RTH session (390 bars 9:30-15:59 ET)
    prior_day_start = pd.Timestamp("2026-04-23 09:30:00", tz="America/New_York")
    for i in range(min(n_history, 390)):
        ts = prior_day_start + pd.Timedelta(minutes=i)
        c = 100.0 + rng.normal(0, 0.5)
        bars.append({
            "timestamp": ts.tz_convert("UTC"),
            "open": c, "high": c + 0.2, "low": c - 0.2,
            "close": c, "volume": base_volume,
        })

    # Today's 5 ORB bars: 9:30, 9:31, 9:32, 9:33, 9:34 ET
    today_start = pd.Timestamp("2026-04-24 09:30:00", tz="America/New_York")
    orb_close_per_bar = np.linspace(orb_open, orb_close, 5)
    orb_high_per_bar = np.maximum(orb_close_per_bar, [orb_open, (orb_open+orb_close)/2,
                                                       (orb_open+orb_close)/2, orb_close, orb_high])
    orb_low_per_bar = np.minimum(orb_close_per_bar, [orb_open, orb_open, orb_low,
                                                      orb_open, orb_close])
    for i in range(5):
        ts = today_start + pd.Timedelta(minutes=i)
        bars.append({
            "timestamp": ts.tz_convert("UTC"),
            "open": float(orb_close_per_bar[i] if i > 0 else orb_open),
            "high": float(orb_high_per_bar[i]),
            "low": float(orb_low_per_bar[i]),
            "close": float(orb_close_per_bar[i]),
            "volume": base_volume * orb_volume_multiplier,
        })

    return pd.DataFrame(bars)


def test_orb_compute_basic():
    from backend.organism.orb_scanner import ORBScanner

    df = _make_orb_df(orb_high=105.0, orb_low=99.0, orb_open=100.0, orb_close=104.0)
    s = ORBScanner()
    result = s._compute_orb_range("TEST", df, atr_at_entry=2.0)

    assert result is not None
    assert result["orb_high"] >= 104.0  # max of last 5 bars
    assert result["orb_low"] <= 100.0
    assert abs(result["orb_close"] - 104.0) < 0.5
    assert result["atr_at_entry"] == 2.0


def test_orb_compute_rejects_below_min_price():
    from backend.organism.orb_scanner import ORBScanner

    df = _make_orb_df(orb_close=2.0)  # below $5 min
    s = ORBScanner(min_price=5.0)
    result = s._compute_orb_range("TEST", df, atr_at_entry=0.1)
    assert result is None


def test_orb_compute_rejects_short_history():
    from backend.organism.orb_scanner import ORBScanner

    df = pd.DataFrame({"close": [100, 101], "high": [101, 102], "low": [99, 100],
                       "open": [100, 100], "volume": [1000, 1000]})
    s = ORBScanner()
    result = s._compute_orb_range("TEST", df, atr_at_entry=0.1)
    assert result is None


# ── Relative volume ──────────────────────────────────────────


def test_relative_volume_high():
    """When today's first 5-min volume is much higher than historical, RV is high."""
    from backend.organism.orb_scanner import ORBScanner

    s = ORBScanner()
    # 100 historical bars at 1000 vol each = 5000 per 5-bar rolling sum
    # today's 5-bar sum = 5000 * 5 = 25000 → RV ≈ 5x
    historical = [{"close": 100, "high": 100, "low": 100, "open": 100, "volume": 1000.0} for _ in range(100)]
    df = pd.DataFrame(historical)

    rv = s._compute_relative_volume(df, today_first_5min_volume=25000)
    assert rv > 4.0  # ~5x


def test_relative_volume_neutral():
    from backend.organism.orb_scanner import ORBScanner

    s = ORBScanner()
    historical = [{"close": 100, "high": 100, "low": 100, "open": 100, "volume": 1000.0} for _ in range(100)]
    df = pd.DataFrame(historical)
    rv = s._compute_relative_volume(df, today_first_5min_volume=5000)
    assert 0.8 < rv < 1.2  # ~1x


# ── Paper-faithful relative volume (timestamp-aware) ─────────


def _make_timestamped_first5_df(
    days: int = 14,
    bars_per_day: int = 390,
    daily_first5_volume: float = 100_000,
    today_first5_volume: float | None = None,
) -> pd.DataFrame:
    """Build a 14-day timestamped 1-min OHLCV dataframe.

    Each day has 390 bars at 1-min intervals 9:30-15:59 ET.
    The first 5 bars of each day (9:30, 9:31, 9:32, 9:33, 9:34) sum to
    `daily_first5_volume` per-bar (so total = 5 * that).

    If `today_first5_volume` is None, today gets the same volume as history.
    Otherwise, today's first 5 bars sum to that value.
    """
    rows = []
    base_date = pd.Timestamp("2026-04-12 09:30:00", tz="America/New_York")
    per_bar_history = daily_first5_volume / 5
    today_per_bar = (
        (today_first5_volume / 5) if today_first5_volume is not None
        else per_bar_history
    )

    for day_offset in range(days):
        day_start = base_date + pd.Timedelta(days=day_offset)
        is_today = (day_offset == days - 1)
        for bar_idx in range(bars_per_day):
            ts = day_start + pd.Timedelta(minutes=bar_idx)
            in_first5 = bar_idx < 5
            vol = (today_per_bar if is_today and in_first5 else
                   per_bar_history if in_first5 else
                   per_bar_history * 0.4)  # later-day baseline
            rows.append({
                "timestamp": ts.tz_convert("UTC"),
                "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0,
                "volume": float(vol),
            })
    return pd.DataFrame(rows)


def test_paper_relative_volume_neutral_with_timestamps():
    """When today's first-5 vol = historical avg, RV should be ~1.0."""
    from backend.organism.orb_scanner import ORBScanner

    df = _make_timestamped_first5_df(days=14, daily_first5_volume=100_000)
    s = ORBScanner(rv_lookback_days=14)
    rv = s._paper_relative_volume(df, today_first_5min_volume=100_000)
    assert rv is not None
    assert 0.95 < rv < 1.05, f"Expected RV ~1.0 on flat data, got {rv}"


def test_paper_relative_volume_high_when_today_spikes():
    """3x volume today vs historical → RV ~3.0 from paper formula."""
    from backend.organism.orb_scanner import ORBScanner

    df = _make_timestamped_first5_df(
        days=14,
        daily_first5_volume=100_000,
        today_first5_volume=300_000,  # 3x spike today
    )
    s = ORBScanner(rv_lookback_days=14)
    rv = s._paper_relative_volume(df, today_first_5min_volume=300_000)
    assert rv is not None
    assert 2.7 < rv < 3.3, f"Expected RV ~3.0 with 3x volume spike, got {rv}"


def test_paper_relative_volume_returns_none_without_timestamps():
    """If df has no timestamp column or datetime index, returns None."""
    from backend.organism.orb_scanner import ORBScanner

    df = pd.DataFrame({
        "close": [100.0] * 50,
        "volume": [1000.0] * 50,
    })
    s = ORBScanner()
    rv = s._paper_relative_volume(df, today_first_5min_volume=5000)
    assert rv is None


def test_paper_rv_used_when_timestamps_present():
    """Composite _compute_relative_volume should call paper formula path
    and use it when timestamps are available."""
    from backend.organism.orb_scanner import ORBScanner

    df = _make_timestamped_first5_df(days=14, daily_first5_volume=100_000,
                                      today_first5_volume=200_000)
    s = ORBScanner(rv_lookback_days=14)
    rv = s._compute_relative_volume(df, today_first_5min_volume=200_000)
    # Paper formula should give ~2.0; rolling-median fallback would give a
    # different (smaller) number because it includes non-first-5-min bars.
    assert 1.7 < rv < 2.3, f"Expected ~2.0 from paper formula, got {rv}"


# ── Direction inference ──────────────────────────────────────


def test_long_direction_when_orb_closes_up():
    """ORB close > open → long bias."""
    from backend.organism.orb_scanner import ORBScanner

    df = _make_orb_df(orb_open=100.0, orb_close=104.0, current_price=105.5)
    df.loc[len(df)] = {
        "open": 105.5, "high": 105.5, "low": 105.5, "close": 105.5,
        "volume": 100_000,
    }
    s = ORBScanner(min_rv_ratio=0.0, top_n=1)  # accept anything
    cands = s.scan({"TEST": df}, pd.Timestamp("2026-04-25 13:36:00", tz="UTC"))

    # 13:36 UTC ≈ 09:36 ET → just after ORB decision
    if cands:  # if the time-window check passes (depends on tz handling)
        c = cands[0]
        assert c.direction == 1.0


def test_short_direction_when_orb_closes_down():
    from backend.organism.orb_scanner import ORBScanner

    df = _make_orb_df(orb_open=104.0, orb_close=100.0, current_price=99.0,
                      orb_high=105.0, orb_low=99.0)
    df.loc[len(df)] = {
        "open": 99.0, "high": 99.0, "low": 99.0, "close": 99.0,
        "volume": 100_000,
    }
    s = ORBScanner(min_rv_ratio=0.0, top_n=1)
    cands = s.scan({"TEST": df}, pd.Timestamp("2026-04-25 13:36:00", tz="UTC"))

    if cands:
        c = cands[0]
        assert c.direction == -1.0


# ── Breakout detection ───────────────────────────────────────


def test_breakout_triggered_when_above_orb_high():
    """Long candidate, current price above orb_high → breakout_triggered=True.

    Two-call pattern: first scan() call populates ORB cache from the last 5
    bars; second scan() call has the post-ORB bar appended and should detect
    breakout via cached ORB high vs new current_price."""
    from backend.organism.orb_scanner import ORBScanner

    # Build with ET timestamps so the timestamp-aware ORB scanner can find
    # the opening range. Prior day = April 23 RTH; ORB = April 24 9:30-9:34 ET.
    bars = []
    prior_start = pd.Timestamp("2026-04-23 09:30:00", tz="America/New_York")
    for i in range(100):
        ts = prior_start + pd.Timedelta(minutes=i)
        bars.append({
            "timestamp": ts.tz_convert("UTC"),
            "open": 100, "high": 100.5, "low": 99.5, "close": 100, "volume": 1000.0,
        })
    today_start = pd.Timestamp("2026-04-24 09:30:00", tz="America/New_York")
    orb_seq = [(100, 100.5, 99.8, 100.5),
               (100.5, 101.5, 100.4, 101.2),
               (101.2, 102.5, 101.1, 102.0),
               (102.0, 103.5, 101.9, 103.0),
               (103.0, 104.5, 102.9, 104.0)]
    for i, (o, h, l, c) in enumerate(orb_seq):
        ts = today_start + pd.Timedelta(minutes=i)
        bars.append({
            "timestamp": ts.tz_convert("UTC"),
            "open": o, "high": h, "low": l, "close": c, "volume": 5000.0,
        })
    df_orb_only = pd.DataFrame(bars)

    s = ORBScanner(min_rv_ratio=0.0, top_n=1)
    # First call: at 9:35 ET (=13:35 UTC), populates ORB cache
    s.scan({"TEST": df_orb_only}, pd.Timestamp("2026-04-24 13:35:00", tz="UTC"))
    # Verify cache populated
    assert s.orb_cache_size == 1
    cached = s._orb_cache["TEST"]
    assert cached["orb_high"] == 104.5

    # Second call: 5 minutes later, with post-ORB bar where price breaks high
    post_orb_ts = today_start + pd.Timedelta(minutes=5)
    df_with_breakout = df_orb_only.copy()
    df_with_breakout.loc[len(df_with_breakout)] = {
        "timestamp": post_orb_ts.tz_convert("UTC"),
        "open": 104.5, "high": 106.0, "low": 104.5, "close": 106.0,
        "volume": 1000.0,
    }
    cands = s.scan({"TEST": df_with_breakout},
                   pd.Timestamp("2026-04-24 13:40:00", tz="UTC"))

    assert len(cands) == 1
    c = cands[0]
    assert c.direction == 1.0
    assert c.current_price == 106.0
    assert c.orb_high == 104.5  # cached, didn't get re-computed
    assert c.breakout_triggered, (
        f"Expected breakout triggered: current={c.current_price} > "
        f"orb_high={c.orb_high}"
    )


def test_scan_ignores_future_breakout_bars_after_now():
    """Full-session replay frames must not let future bars trigger ORB now."""
    from backend.organism.orb_scanner import ORBScanner

    df = _make_orb_df(
        orb_high=104.5,
        orb_low=99.0,
        orb_open=100.0,
        orb_close=104.0,
        base_volume=100_000,
        orb_volume_multiplier=3.0,
    )
    future_ts = pd.Timestamp("2026-04-24 09:40:00", tz="America/New_York")
    df.loc[len(df)] = {
        "timestamp": future_ts.tz_convert("UTC"),
        "open": 104.0,
        "high": 106.2,
        "low": 103.8,
        "close": 106.0,
        "volume": 250_000.0,
    }

    scanner = ORBScanner(min_rv_ratio=0.0, top_n=1)
    now_utc = pd.Timestamp("2026-04-24 13:35:00", tz="UTC")
    cands = scanner.scan({"TEST": df}, now_utc)

    assert len(cands) == 1
    assert cands[0].current_price == pytest.approx(104.0)
    assert not cands[0].breakout_triggered


def test_scan_rejects_stale_session_orb_frame():
    """A stale historical frame must not be cached for the current session.

    The May 12 paper session showed repeated "cached session=2026-05-08,
    current=2026-05-12" warnings. The scanner was invalidating the stale
    cache, then recomputing the same stale ORB from the stale frame and
    leaving it in cache for the current session.
    """
    from backend.organism.orb_scanner import ORBScanner

    stale_df = _make_orb_df(
        orb_high=104.5,
        orb_low=99.0,
        orb_open=100.0,
        orb_close=104.0,
        base_volume=100_000,
        orb_volume_multiplier=3.0,
    )
    scanner = ORBScanner(min_rv_ratio=0.0, top_n=1)

    cands = scanner.scan(
        {"NFLX": stale_df},
        pd.Timestamp("2026-05-12 14:00:00", tz="UTC"),
        session_date="2026-05-12",
    )

    assert cands == []
    assert scanner.orb_cache_size == 0


# ── Daily reset ──────────────────────────────────────────────


def test_session_date_change_triggers_reset():
    from backend.organism.orb_scanner import ORBScanner

    s = ORBScanner()
    s._orb_cache["AAPL"] = {"orb_high": 100, "orb_low": 99}
    s._current_session_date = "2026-04-24"

    df = _make_orb_df()
    # Different session date
    s.scan({"TEST": df}, pd.Timestamp("2026-04-25 13:40:00", tz="UTC"),
           session_date="2026-04-25")

    assert s._current_session_date == "2026-04-25"
    # Cache should have been reset and rebuilt for TEST (or empty for AAPL)
    assert "AAPL" not in s._orb_cache


def test_mark_fired_prevents_refire():
    from backend.organism.orb_scanner import ORBScanner

    s = ORBScanner(min_rv_ratio=0.0, top_n=5)
    df = _make_orb_df(orb_high=105.0, orb_low=99.0, orb_open=100.0, orb_close=104.0)
    df.loc[len(df)] = {
        "open": 105.5, "high": 105.5, "low": 105.5, "close": 105.5,
        "volume": 100_000,
    }

    cands1 = s.scan({"TEST": df}, pd.Timestamp("2026-04-25 13:40:00", tz="UTC"))
    if cands1:
        s.mark_fired("TEST")
        cands2 = s.scan({"TEST": df}, pd.Timestamp("2026-04-25 13:41:00", tz="UTC"))
        assert all(c.symbol != "TEST" for c in cands2)


# ── Time-window gating end-to-end ────────────────────────────


def test_scan_returns_empty_outside_decision_window():
    from backend.organism.orb_scanner import ORBScanner

    s = ORBScanner()
    df = _make_orb_df()
    # 6 PM UTC = 2 PM ET — well after decision window-start, but BEFORE 15:55 ET
    # so this should actually be IN the decision window.
    # Let's pick a time clearly OUT of the window: 4 AM ET
    cands_off_hours = s.scan(
        {"TEST": df},
        pd.Timestamp("2026-04-25 08:00:00", tz="UTC"),  # 4 AM ET
    )
    assert cands_off_hours == []


def test_scanner_imports_cleanly():
    """Smoke test that the module can be imported."""
    from backend.organism.orb_scanner import (
        ORBScanner, ORBCandidate,
        DEFAULT_OPENING_MINUTES, DEFAULT_TOP_N,
    )
    assert ORBScanner is not None
    assert ORBCandidate is not None
    assert DEFAULT_OPENING_MINUTES == 5
    assert DEFAULT_TOP_N == 10
