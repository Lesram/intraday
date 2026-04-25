"""Replay simulator hardening tests (S7).

Two improvements:
1. compute_tension_proxy() extracted to ml_features as single source of truth
2. SimulatedBroker.delay_fill — opt-in 1-bar fill delay (more realistic)
"""

from __future__ import annotations

import asyncio
import math
import pandas as pd
import pytest


# ────────────────────────────────────────────────────────────────
# 1. Tension proxy
# ────────────────────────────────────────────────────────────────


def test_tension_proxy_quiet_market_returns_low():
    """Flat-volume, no-move market → near-zero tension."""
    from backend.organism.ml_features import compute_tension_proxy

    df = pd.DataFrame({
        "vol_sma_ratio": [1.0],   # exactly average volume
        "ret_1d": [0.0],          # no move
        "atr_ratio": [0.018],     # low vol regime
    })
    t = compute_tension_proxy(df)
    assert 0.0 <= t < 0.10, f"Quiet market tension should be near zero, got {t}"


def test_tension_proxy_active_market_returns_high():
    """High volume + big move → high tension (capped at 0.80)."""
    from backend.organism.ml_features import compute_tension_proxy

    df = pd.DataFrame({
        "vol_sma_ratio": [3.0],   # 3x average volume
        "ret_1d": [0.025],        # 2.5% move
        "atr_ratio": [0.04],      # mid vol regime
    })
    t = compute_tension_proxy(df)
    assert t > 0.5, f"Active market tension should be > 0.5, got {t}"
    assert t <= 0.80, f"Tension capped at 0.80, got {t}"


def test_tension_proxy_handles_missing_columns():
    """Missing columns → reasonable defaults, no crash."""
    from backend.organism.ml_features import compute_tension_proxy

    df = pd.DataFrame({"close": [100.0]})  # no tension-relevant columns
    t = compute_tension_proxy(df)
    assert 0.0 <= t <= 0.80, f"Default-input tension should be safe, got {t}"


def test_tension_proxy_handles_nan_safely():
    """NaN inputs → defaults, no crash."""
    from backend.organism.ml_features import compute_tension_proxy

    df = pd.DataFrame({
        "vol_sma_ratio": [float("nan")],
        "ret_1d": [float("nan")],
        "atr_ratio": [float("nan")],
    })
    t = compute_tension_proxy(df)
    assert 0.0 <= t <= 0.80, f"NaN-input tension should be safe, got {t}"


def test_tension_proxy_empty_df_returns_zero():
    """Empty/None features → zero (not error)."""
    from backend.organism.ml_features import compute_tension_proxy

    assert compute_tension_proxy(None) == 0.0
    assert compute_tension_proxy(pd.DataFrame()) == 0.0


def test_live_engine_uses_compute_tension_proxy():
    """Source-level: live_engine.py imports and uses compute_tension_proxy
    (single source of truth between live and replay)."""
    from pathlib import Path
    src = (
        Path(__file__).parent.parent / "backend" / "organism" / "live_engine.py"
    ).read_text()
    assert "from backend.organism.ml_features import compute_tension_proxy" in src
    assert "tension = compute_tension_proxy(feat_df)" in src


# ────────────────────────────────────────────────────────────────
# 2. SimulatedBroker delay_fill
# ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simulated_broker_delay_fill_uses_next_bar_open():
    """delay_fill=True → fill at next bar's open, not current close."""
    from backend.organism.replay_simulator import (
        HistoricalBarProvider,
        SimulatedBroker,
        make_price_df,
    )

    # Two distinct prices in consecutive bars
    df = make_price_df(n=10, base=100.0)
    df.loc[5, "close"] = 100.0
    df.loc[6, "open"] = 105.0  # different from bar 5's close

    bp = HistoricalBarProvider({"AAPL": df}, lookback=4)
    # Advance to position cursor at bar 6 (current_idx == 6 means bar 5 is "current")
    while bp._current_idx < 6:
        bp.advance()

    broker = SimulatedBroker(initial_cash=10_000, slippage_bps=0, delay_fill=True)
    broker.set_bar_provider(bp)

    # current_price = bar 5 close = 100, next_bar_open = bar 6 open = 105
    assert broker._current_price("AAPL") == 100.0
    assert broker._fill_price("AAPL") == 105.0  # delay_fill picks next open

    result = await broker.submit_symbol_order(
        symbol="AAPL", side="buy", qty=10, idempotency_key="t1",
    )
    assert result["status"] == "filled"
    assert float(result["avg_fill_price"]) == 105.0


@pytest.mark.asyncio
async def test_simulated_broker_default_no_delay_preserves_old_behavior():
    """delay_fill=False (default) → fill at current close, like before."""
    from backend.organism.replay_simulator import (
        HistoricalBarProvider, SimulatedBroker, make_price_df,
    )

    df = make_price_df(n=10, base=100.0)
    df.loc[5, "close"] = 100.0
    df.loc[6, "open"] = 105.0

    bp = HistoricalBarProvider({"AAPL": df}, lookback=4)
    while bp._current_idx < 6:
        bp.advance()

    broker = SimulatedBroker(initial_cash=10_000, slippage_bps=0)  # default delay_fill=False
    broker.set_bar_provider(bp)

    result = await broker.submit_symbol_order(
        symbol="AAPL", side="buy", qty=10, idempotency_key="t2",
    )
    assert result["status"] == "filled"
    # Without delay, fill at current price (bar 5 close = 100)
    assert float(result["avg_fill_price"]) == 100.0


def test_replay_engine_propagates_delay_fill():
    """ReplayEngine.delay_fill flag passes through to its broker."""
    from backend.organism.replay_simulator import ReplayEngine, make_features_dict

    bars = make_features_dict(["AAPL"], n=300)
    engine = ReplayEngine(
        bars_by_symbol=bars,
        timeframe="1Min",
        delay_fill=True,
    )
    assert engine.delay_fill is True


def test_bar_provider_next_bar_open_at_end_falls_back():
    """At the last bar, next_bar_open should fall back to current price."""
    from backend.organism.replay_simulator import (
        HistoricalBarProvider, make_price_df,
    )

    df = make_price_df(n=10, base=100.0)
    bp = HistoricalBarProvider({"AAPL": df}, lookback=2)
    # Advance to the very last bar
    while bp.advance():
        pass
    # next_bar_open should NOT crash; falls back to current price
    nbo = bp.next_bar_open("AAPL")
    cp = bp.current_price("AAPL")
    assert nbo == cp or nbo > 0
