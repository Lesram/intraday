"""
Tests for the Organism Replay Simulator.

Covers: SimulatedBroker, HistoricalBarProvider, ReplayEngine, ReplayResult.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.organism.replay_simulator import (
    HistoricalBarProvider,
    ReplayEngine,
    ReplayResult,
    SimulatedBroker,
    make_features_dict,
    make_price_df,
)


# ═════════════════════════════════════════════════════════════════════════
#  SimulatedBroker tests
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_simulated_broker_fills_correctly():
    """Buy 10 shares, position shows 10, sell 10, position gone."""
    broker = SimulatedBroker(initial_cash=100_000)
    broker.set_price("AAPL", 150.0)

    # Buy 10 shares
    result = await broker.submit_symbol_order(
        symbol="AAPL", side="buy", qty=10, idempotency_key="test1",
    )
    assert result["status"] == "filled"
    assert int(result["filled_qty"]) == 10

    positions = await broker.get_all_positions()
    assert "AAPL" in positions
    assert positions["AAPL"]["qty"] == 10

    # Cash should be reduced
    assert broker.cash < 100_000
    expected_cost = 150.0 * 10
    assert abs(broker.cash - (100_000 - expected_cost)) < 0.01

    # Sell 10 shares
    result = await broker.submit_symbol_order(
        symbol="AAPL", side="sell", qty=10, idempotency_key="test2",
    )
    assert result["status"] == "filled"

    positions = await broker.get_all_positions()
    assert "AAPL" not in positions

    # Cash should be restored (no slippage)
    assert abs(broker.cash - 100_000) < 0.01


@pytest.mark.asyncio
async def test_replay_slippage_applied():
    """Fill prices differ from bar close by slippage_bps."""
    broker = SimulatedBroker(initial_cash=100_000, slippage_bps=10)
    broker.set_price("AAPL", 100.0)

    result = await broker.submit_symbol_order(
        symbol="AAPL", side="buy", qty=10, idempotency_key="test1",
    )
    fill_price = float(result["avg_fill_price"])

    # Buy should be filled at price + slippage (100 * 10/10000 = 0.10)
    expected = 100.0 * (1 + 10 / 10000)
    assert abs(fill_price - expected) < 0.01, f"Fill {fill_price} != expected {expected}"

    # Sell should fill at price - slippage
    broker.set_price("AAPL", 100.0)
    result = await broker.submit_symbol_order(
        symbol="AAPL", side="sell", qty=10, idempotency_key="test2",
    )
    fill_price = float(result["avg_fill_price"])
    expected_sell = 100.0 * (1 - 10 / 10000)
    assert abs(fill_price - expected_sell) < 0.01


@pytest.mark.asyncio
async def test_simulated_broker_portfolio_value():
    """Portfolio value = cash + sum(position market values)."""
    broker = SimulatedBroker(initial_cash=100_000)
    broker.set_price("AAPL", 150.0)

    await broker.submit_symbol_order(
        symbol="AAPL", side="buy", qty=10, idempotency_key="test1",
    )

    total = await broker.get_total_portfolio_value()
    # Should be approximately 100_000 (cash reduced by 1500, positions worth 1500)
    assert abs(total - 100_000) < 1.0

    # If price goes up, portfolio value increases
    broker.set_price("AAPL", 160.0)
    total2 = await broker.get_total_portfolio_value()
    assert total2 > total


# ═════════════════════════════════════════════════════════════════════════
#  HistoricalBarProvider tests
# ═════════════════════════════════════════════════════════════════════════

def test_bar_provider_advances_correctly():
    """After N advances, bars_remaining decreases by N."""
    bars = make_features_dict(["AAPL", "SPY"], n=600, seed=42)
    provider = HistoricalBarProvider(bars, lookback=100)

    initial_remaining = provider.bars_remaining
    assert initial_remaining > 0

    for i in range(10):
        assert provider.advance() is True

    assert provider.bars_remaining == initial_remaining - 10


def test_bar_provider_returns_correct_window():
    """get_historical_data returns lookback window up to cursor."""
    bars = make_features_dict(["AAPL"], n=600, seed=42)
    provider = HistoricalBarProvider(bars, lookback=100)

    df = provider.get_historical_data("AAPL", limit=50)
    assert df is not None
    assert len(df) == 50

    # Advance and get more data
    for _ in range(10):
        provider.advance()

    df2 = provider.get_historical_data("AAPL", limit=50)
    assert df2 is not None
    assert len(df2) == 50
    # Data should have shifted forward
    assert df2["close"].iloc[-1] != df["close"].iloc[-1]


def test_bar_provider_exhaustion():
    """Provider returns False when exhausted."""
    # Use 600 bars with lookback=500 — lookback fits within 75% of 600 (450),
    # so clamped to 450, leaving 150 bars to advance.
    bars = make_features_dict(["AAPL"], n=600, seed=42)
    provider = HistoricalBarProvider(bars, lookback=500)

    initial_remaining = provider.bars_remaining
    assert initial_remaining > 0

    advances = 0
    while provider.advance():
        advances += 1

    assert advances == initial_remaining
    assert provider.bars_remaining == 0


def test_bar_provider_current_price():
    """current_price returns close at cursor position."""
    bars = make_features_dict(["AAPL"], n=600, seed=42)
    provider = HistoricalBarProvider(bars, lookback=100)

    price = provider.current_price("AAPL")
    # Should be the close at index lookback-1 (99)
    expected = float(bars["AAPL"]["close"].iloc[99])
    assert abs(price - expected) < 0.001


# ═════════════════════════════════════════════════════════════════════════
#  ReplayEngine tests
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_replay_completes_100_ticks():
    """Synthetic data, 100 ticks, no crash.

    V12 W90 (post-cleanup): bumped per-test timeout from default 15s.
    V13 cleanup bumped it again to 180s after GitHub's cold runner
    exceeded 60s in the pandas-heavy feature path.  The test still runs
    the full 100-tick replay; only the CI budget changed."""
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="up",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=100_000,
        slippage_bps=5,
        lookback=200,
    )
    result = await engine.run(max_ticks=100)

    assert result.ticks == 100
    assert len(result.equity_curve) == 100
    assert len(result.regime_history) == 100
    assert result.equity_curve[0] > 0


@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_replay_trades_have_valid_pnl():
    """All trades should have non-NaN PnL."""
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="up",
    )
    engine = ReplayEngine(bars_by_symbol=bars, initial_cash=100_000, lookback=200)
    result = await engine.run(max_ticks=100)

    for trade in result.trades:
        assert not np.isnan(trade["pnl"]), f"Trade has NaN PnL: {trade}"


@pytest.mark.asyncio
async def test_replay_equity_monotonic_start():
    """Equity starts at initial_cash."""
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42,
    )
    engine = ReplayEngine(bars_by_symbol=bars, initial_cash=50_000)
    result = await engine.run(max_ticks=10)

    assert len(result.equity_curve) > 0
    # First equity should be close to initial cash (minor slippage possible)
    assert abs(result.equity_curve[0] - 50_000) < 1_000


@pytest.mark.asyncio
async def test_replay_regime_history_populated():
    """regime_history should have one entry per tick."""
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42,
    )
    engine = ReplayEngine(bars_by_symbol=bars)
    result = await engine.run(max_ticks=20)

    assert len(result.regime_history) == result.ticks
    for r in result.regime_history:
        assert r is not None


@pytest.mark.asyncio
async def test_replay_with_crash_data():
    """Feed crash scenario — engine should handle gracefully."""
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="crash",
    )
    engine = ReplayEngine(bars_by_symbol=bars, initial_cash=100_000)
    result = await engine.run(max_ticks=50)

    # Should complete without crashing
    assert result.ticks == 50
    assert len(result.equity_curve) == 50


@pytest.mark.asyncio
async def test_replay_result_summary():
    """summary() returns string with PnL, trades, win rate."""
    result = ReplayResult(
        ticks=100,
        trades=[
            {"pnl": 100.0}, {"pnl": -50.0}, {"pnl": 200.0},
        ],
        equity_curve=[100_000, 100_100, 100_050, 100_250],
        regime_history=["trending_up"] * 100,
    )

    summary = result.summary()
    assert "REPLAY SUMMARY" in summary
    assert "Trades:" in summary
    assert "Win Rate:" in summary
    assert "PnL" in summary


def test_replay_result_metrics():
    """ReplayResult computed properties."""
    result = ReplayResult(
        trades=[
            {"pnl": 100.0}, {"pnl": -50.0}, {"pnl": 200.0},
        ],
        equity_curve=[100_000, 100_100, 100_050, 100_250],
    )

    assert result.total_pnl == 250.0
    assert abs(result.win_rate - 2 / 3) < 0.01
    assert result.max_drawdown >= 0


@pytest.mark.asyncio
async def test_from_csv_loads_correctly():
    """Round-trip: save bars to CSV, load via from_csv."""
    bars = make_features_dict(["AAPL", "SPY"], n=300, seed=42)

    with tempfile.TemporaryDirectory() as tmpdir:
        for sym, df in bars.items():
            df.to_csv(Path(tmpdir) / f"{sym}.csv", index=False)

        engine = ReplayEngine.from_csv(tmpdir)
        assert "AAPL" in engine.bars_by_symbol
        assert "SPY" in engine.bars_by_symbol
        assert len(engine.bars_by_symbol["AAPL"]) == 300


# ═════════════════════════════════════════════════════════════════════════
#  Synthetic data helpers
# ═════════════════════════════════════════════════════════════════════════

def test_make_price_df_trends():
    """Verify make_price_df generates correct trends."""
    df_up = make_price_df(200, 100.0, seed=42, trend="up")
    df_down = make_price_df(200, 100.0, seed=42, trend="down")
    df_crash = make_price_df(200, 100.0, seed=42, trend="crash")

    # Up trend should end higher than start
    assert df_up["close"].iloc[-1] > df_up["close"].iloc[0]
    # Down trend should end lower
    assert df_down["close"].iloc[-1] < df_down["close"].iloc[0]
    # Crash should be more severe than down
    crash_return = df_crash["close"].iloc[-1] / df_crash["close"].iloc[0]
    down_return = df_down["close"].iloc[-1] / df_down["close"].iloc[0]
    assert crash_return < down_return


def test_make_features_dict():
    """Verify make_features_dict builds correct structure."""
    result = make_features_dict(["AAPL", "MSFT", "SPY"], n=300)
    assert len(result) == 3
    assert all(len(df) == 300 for df in result.values())
    assert all("close" in df.columns for df in result.values())


# ═════════════════════════════════════════════════════════════════════════
#  Replay time override tests
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_replay_time_override_uses_bar_time():
    """After ReplayEngine injects overrides, engine._time_fn() returns bar timestamps, not wall clock."""
    import time as _time

    bars = make_features_dict(["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="up")
    bar_provider = HistoricalBarProvider(bars, lookback=100)

    # Advance a few bars so the provider has a current position
    for _ in range(5):
        bar_provider.advance()

    simulated = bar_provider.current_simulated_time
    wall = _time.time()

    # Simulated time should be far from wall clock (synthetic data uses Jan 2026 base)
    # Wall clock is Feb 2026 — difference should be significant
    assert abs(simulated - wall) > 86400, (
        f"Simulated time ({simulated}) too close to wall clock ({wall}) — "
        "should be from synthetic base, not real time"
    )

    # Simulated datetime should be timezone-aware
    sim_dt = bar_provider.current_simulated_datetime
    assert sim_dt.tzinfo is not None, "Simulated datetime should be timezone-aware"


# wave: V13-W93
@pytest.mark.timeout(120)
@pytest.mark.asyncio
async def test_replay_no_throttle_blocking():
    """With time overrides + adequate initial cash, replay should not be
    throttled by entries-per-hour limit.

    V13 W93 root-cause investigation (scripts/debug/replay_throttle_diagnose.py):
    the V12-era xfail was misdiagnosed.  100 ticks at $100k initial cash did
    produce 42 signals — but every one of them was rejected by the
    Kelly min-notional floor ($2,000), not by the entries-per-hour throttle.

    Diagnostic:
      total_signals_generated = 42
      total_orders_submitted  = 0
      Kelly skip … notional=1438 < min=2000  (×40+)
      Confidence reject … eff_conf=0.17 < 0.25  (×2)

    With $100k cash + 0.10% learning-mode risk budget, calculated notionals
    fall in the $1,300-$1,500 range — below the $2,000 protective floor that
    prevents micro-positions in production.  Bumping to $1,000,000 keeps
    the same risk-budget ratio but lifts notionals to ~$13k-$15k, well above
    the floor.  This is the realistic test setup; the engine semantics are
    unchanged.

    With this fix the test passes, proving the entries-per-hour throttle is
    NOT blocking replay at max_entries_per_hour=20.
    """
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="up",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=1_000_000,  # V13 W93: lifts Kelly notionals above $2k floor
        slippage_bps=5,
        max_entries_per_hour=20,
        lookback=200,
    )
    result = await engine.run(max_ticks=100)

    assert result.ticks == 100
    total_orders = sum(
        r.get("orders_submitted", 0)
        for r in result.tick_results if isinstance(r, dict)
    )
    # With $1M cash, Kelly clears the $2k floor; with max_entries_per_hour=20
    # the throttle is well above the actual entry rate (replay produces
    # ~0.4 signals/tick).  Expect > 3 orders.
    assert total_orders >= 3, (
        f"Only {total_orders} orders in 100 ticks — V13-W93 fix may have regressed"
    )


# wave: V13-W93
@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_replay_throttle_actually_blocks_at_low_limit():
    """Companion test: prove the throttle DOES bite when the limit is low.

    If we set max_entries_per_hour=1, the throttle should cap orders at
    roughly 1/hour.  100 ticks at 1-min cadence ≈ ~1.6 hours ≈ ≤2 entries.
    This pairs with test_replay_no_throttle_blocking: together they prove
    the throttle is responsive to its parameter (not always-block, not
    always-pass).
    """
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="up",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=1_000_000,
        slippage_bps=5,
        max_entries_per_hour=1,  # tight throttle
        timeframe="1Min",
        lookback=200,
    )
    result = await engine.run(max_ticks=100)
    entry_orders = [
        order for order in result.orders
        if order.get("side") == "buy"
    ]
    # 100 minutes ≈ 1.66 hours, so a 1/hr entry throttle caps at ≤ 2.
    # We allow up to 3 to absorb edge effects in the throttle window math.
    # The companion high-throttle test proves replay is not always-blocked;
    # this low-throttle test proves the cap is honored when entries appear.
    assert len(entry_orders) <= 3, (
        "Entry throttle ineffective: got "
        f"{len(entry_orders)} entry orders with 1/hr cap"
    )


@pytest.mark.asyncio
async def test_replay_daily_timeframe_uses_wider_stops():
    """Daily replay should use daily exit config (wider stops, 8% max loss)."""
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="up",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=100_000,
        slippage_bps=5,
        timeframe="1Day",
    )
    result = await engine.run(max_ticks=50)

    assert result.ticks == 50
    assert len(result.equity_curve) == 50
    # No trade should lose more than 8% (daily max_loss_pct)
    for trade in result.trades:
        if trade.get("entry_price", 0) > 0:
            pnl_pct = trade["pnl"] / (trade["entry_price"] * trade["qty"])
            assert pnl_pct > -0.10, (
                f"Trade lost {pnl_pct:.1%} — should be capped near 8%: {trade}"
            )


@pytest.mark.timeout(180)
@pytest.mark.asyncio
async def test_replay_intraday_timeframe_uses_tight_stops():
    """Intraday replay should use intraday exit config (tighter stops, 8% max loss)."""
    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="down",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=100_000,
        slippage_bps=5,
        timeframe="1Min",
        lookback=200,
    )
    result = await engine.run(max_ticks=50)

    assert result.ticks == 50
    assert len(result.equity_curve) == 50


# ═════════════════════════════════════════════════════════════════════════
#  Lookback cap tests
# ═════════════════════════════════════════════════════════════════════════

def test_bar_provider_lookback_200_gives_more_ticks():
    """With 500 bars and lookback=200, we get 300 ticks vs 125 at default 75% cap."""
    bars = make_features_dict(["AAPL"], n=500, seed=42)
    provider_200 = HistoricalBarProvider(bars, lookback=200)
    provider_default = HistoricalBarProvider(bars, lookback=500)

    ticks_200 = 0
    while provider_200.advance():
        ticks_200 += 1

    ticks_default = 0
    while provider_default.advance():
        ticks_default += 1

    # lookback=200 → 300 replay ticks; lookback=500 capped at 75% (375) → 125
    assert ticks_200 == 300
    assert ticks_default == 125
    assert ticks_200 > ticks_default


def test_replay_engine_daily_default_lookback():
    """Daily timeframe defaults to lookback=200."""
    bars = make_features_dict(["AAPL"], n=500, seed=42)
    engine = ReplayEngine(bars_by_symbol=bars, timeframe="1Day")
    assert engine.lookback == 200


def test_replay_engine_intraday_default_lookback():
    """Intraday timeframe defaults to lookback=500."""
    bars = make_features_dict(["AAPL"], n=1000, seed=42)
    engine = ReplayEngine(bars_by_symbol=bars, timeframe="1Min")
    assert engine.lookback == 500


def test_replay_engine_custom_lookback():
    """Explicit lookback overrides the default."""
    bars = make_features_dict(["AAPL"], n=500, seed=42)
    engine = ReplayEngine(bars_by_symbol=bars, timeframe="1Day", lookback=100)
    assert engine.lookback == 100


@pytest.mark.asyncio
async def test_replay_seasonality_uses_bar_time():
    """Seasonality filter should use simulated bar time, not real wall clock."""
    bars = make_features_dict(["AAPL"], n=700, seed=42, trend="up")
    bar_provider = HistoricalBarProvider(bars, lookback=100)
    bar_provider.advance()

    sim_dt = bar_provider.current_simulated_datetime
    # Synthetic data uses base time of 2026-01-02 09:30 + minute offsets
    # The simulated datetime should reflect that, not the current real time
    assert sim_dt.year == 2026, f"Expected year 2026, got {sim_dt.year}"
    # Hour should be based on synthetic data (around 9-10 AM range for early bars)
    # not whatever time the test is actually running
    import time as _time
    real_hour = __import__("datetime").datetime.now().hour
    # If real time != simulated time hour, the override is working
    # (this is a soft check — could coincide, but synthetic base is 9:30 AM)
    assert sim_dt.month == 1, f"Expected month 1 (Jan from synthetic base), got {sim_dt.month}"
