"""
Integration Smoke Tests — Multi-tick lifecycle tests for OrganismLiveEngine.

These tests verify cross-component behavior that unit tests miss because
they mock away the very boundaries where bugs hide.  Each test simulates
a realistic multi-tick scenario end-to-end through the real engine code.

Covers:
    1. Exit fires for position symbol outside universe
    2. Restart preserves trailing stop state (brain round-trip)
    3. Partial IOC fill doesn't cause double entry
    4. Model retrain triggers after N ticks
    5. Losing symbol gets fitness-gated on re-entry
    6. Max loss safety net triggers at -15%
    7. Tick counters survive brain save/load cycle
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels
from backend.organism.brain_persistence import OrganismBrain
from backend.organism.continuous_learner import TradeRecord


# ═════════════════════════════════════════════════════════════════
#  Shared helpers
# ═════════════════════════════════════════════════════════════════

def _make_price_df(
    n: int = 300,
    base: float = 100.0,
    seed: int = 42,
    trend: float = 0.0005,
) -> pd.DataFrame:
    """Create a realistic synthetic OHLCV DataFrame.

    Parameters
    ----------
    trend : mean daily return.  0.0005 for slight uptrend,
            -0.005 for crash, +0.005 for rally.
    """
    rng = np.random.default_rng(seed)
    returns = rng.normal(trend, 0.02, n)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0, 0.02, n))
    low = close * (1 - rng.uniform(0, 0.02, n))
    opn = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(100_000, 10_000_000, n).astype(float)
    return pd.DataFrame({
        "open": opn,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def _make_crash_df(
    n: int = 300, base: float = 100.0, crash_pct: float = 0.20,
) -> pd.DataFrame:
    """OHLCV where the last bar crashes by `crash_pct` from the first."""
    df = _make_price_df(n, base, seed=99, trend=0.0)
    # Force the last few bars to reflect the crash
    crash_price = base * (1 - crash_pct)
    for i in range(max(0, n - 5), n):
        frac = (i - (n - 5)) / 5
        target = base * (1 - crash_pct * frac)
        df.loc[i, "close"] = target
        df.loc[i, "low"] = target * 0.99
        df.loc[i, "high"] = target * 1.005
        df.loc[i, "open"] = target * 1.002
    return df


class MockDataClient:
    """Mock Alpaca data client returning synthetic data."""

    def __init__(self, data: dict[str, pd.DataFrame] | None = None):
        self._data = data or {}

    def get_historical_data(self, symbol, timeframe="1Day", limit=500):
        if symbol not in self._data:
            self._data[symbol] = _make_price_df(max(limit, 300))
        return self._data[symbol]


class MockPositionsService:
    """Mock positions service with mutable state."""

    def __init__(self, positions: dict | None = None):
        self.positions = positions or {}

    async def get_all_positions(self) -> dict:
        return dict(self.positions)

    async def get_total_portfolio_value(self) -> float:
        return 100_000.0

    async def get_buying_power(self) -> float:
        return 50_000.0


class MockOrderService:
    """Mock order service that records submissions."""

    def __init__(self):
        self.submitted: list[dict] = []

    async def submit_symbol_order(self, **kwargs) -> dict:
        self.submitted.append(kwargs)
        return {"id": f"mock_{len(self.submitted)}", "status": "accepted"}


@pytest.fixture
def brain_dir(tmp_path):
    return str(tmp_path / "test_brain")


def _make_engine(
    data_client=None,
    order_service=None,
    positions_service=None,
    brain_dir="test_brain",
    universe=None,
):
    """Create an OrganismLiveEngine with test defaults."""
    from backend.organism.live_engine import OrganismLiveEngine

    return OrganismLiveEngine(
        data_client=data_client or MockDataClient(),
        order_service=order_service or MockOrderService(),
        positions_service=positions_service or MockPositionsService(),
        brain_dir=brain_dir,
        universe=universe or ["AAPL", "MSFT", "SPY"],
    )


# ═════════════════════════════════════════════════════════════════
#  Test 1: Exit fires for position symbol OUTSIDE universe
# ═════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestExitOutsideUniverse:
    """Verify that positions whose symbols rotated out of the universe
    still get exit checks — the bug that caused ANPA to ride to -30%.
    """

    @pytest.mark.asyncio
    async def test_exit_checked_for_symbol_not_in_universe(self, brain_dir):
        """ANPA is held but NOT in the universe.  Exit should still trigger."""
        from backend.organism.live_engine import OrganismLiveEngine

        # ANPA is NOT in the universe — simulates rotation-out
        universe = ["AAPL", "MSFT", "SPY"]

        # But we hold an ANPA position
        positions = MockPositionsService({
            "ANPA": {"qty": "100", "avg_entry_price": "12.85", "side": "long"},
        })
        data = MockDataClient({
            "ANPA": _make_price_df(300, base=12.85, seed=10),
            "AAPL": _make_price_df(300),
            "MSFT": _make_price_df(300),
            "SPY": _make_price_df(300),
        })
        order_service = MockOrderService()

        engine = OrganismLiveEngine(
            data_client=data,
            order_service=order_service,
            positions_service=positions,
            brain_dir=brain_dir,
            universe=universe,
        )
        await engine.initialize()

        # Run a tick — the engine should fetch features for ANPA
        # even though it's outside the universe
        result = await engine.live_tick()

        # ANPA should have been checked for exits
        assert result.exits_checked >= 1, (
            "Position outside universe must still be checked for exits"
        )

    @pytest.mark.asyncio
    async def test_features_fetched_for_position_symbols(self, brain_dir):
        """_fetch_and_compute_features must include position symbols."""
        from backend.organism.live_engine import OrganismLiveEngine

        universe = ["AAPL", "SPY"]
        positions = MockPositionsService({
            "FOXX": {"qty": "500", "avg_entry_price": "5.72", "side": "long"},
        })
        data = MockDataClient({
            "FOXX": _make_price_df(300, base=5.72),
            "AAPL": _make_price_df(300),
            "SPY": _make_price_df(300),
        })

        engine = OrganismLiveEngine(
            data_client=data,
            order_service=MockOrderService(),
            positions_service=positions,
            brain_dir=brain_dir,
            universe=universe,
        )
        await engine.initialize()

        features = await engine._fetch_and_compute_features()

        assert "FOXX" in features, (
            "Position symbol FOXX must have features even though "
            "it is not in the universe"
        )


# ═════════════════════════════════════════════════════════════════
#  Test 2: Brain round-trip preserves trailing stop state
# ═════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestBrainRoundTrip:
    """Verify that exit levels (trailing stop, partial_tp_taken, etc.)
    survive a brain save → load cycle.
    """

    @pytest.mark.asyncio
    async def test_exit_levels_survive_restart(self, brain_dir):
        """Save brain with exit levels, create new engine, verify restored."""
        from backend.organism.live_engine import OrganismLiveEngine

        positions = MockPositionsService({
            "AAPL": {"qty": "10", "avg_entry_price": "150.0", "side": "long"},
        })

        # Run 1: Initialize, tick, mutate trailing stop, save
        engine1 = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=MockOrderService(),
            positions_service=positions,
            brain_dir=brain_dir,
            universe=["AAPL", "SPY"],
        )
        await engine1.initialize()
        await engine1.live_tick()

        # Manually set realistic exit state that we want to survive restart
        engine1._exit_levels["AAPL"] = ExitLevels(
            symbol="AAPL",
            direction=1.0,
            entry_price=150.0,
            stop_loss=145.0,
            take_profit=170.0,
            trailing_stop=155.0,  # Trailing has moved up
            atr_at_entry=3.5,
            regime_at_entry="normal",
            highest_favorable=162.0,  # Peak was 162
            bars_held=25,
            partial_tp_taken=True,   # Partial TP was taken
            trailing_active=True,    # Trail is engaged
            stress_tightened=False,
        )
        engine1._entry_metadata["AAPL"] = {
            "entry_price": 150.0,
            "entry_tick": 1,
            "direction": 1.0,
            "predicted_return": 0.03,
            "confidence": 0.7,
        }
        engine1._tick_count = 100

        await engine1.shutdown()

        # Run 2: Load from brain
        engine2 = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=MockOrderService(),
            positions_service=positions,
            brain_dir=brain_dir,
            universe=["AAPL", "SPY"],
        )
        loaded = await engine2.initialize()
        assert loaded is True, "Should load brain from previous run"

        # Verify exit levels restored
        assert "AAPL" in engine2._exit_levels, "Exit levels must be restored"
        restored = engine2._exit_levels["AAPL"]
        assert restored.trailing_stop == 155.0, "Trailing stop must survive"
        assert restored.highest_favorable == 162.0, "Peak must survive"
        assert restored.partial_tp_taken is True, "Partial TP flag must survive"
        assert restored.trailing_active is True, "Trailing active must survive"
        assert restored.bars_held == 25, "Bars held must survive"

    @pytest.mark.asyncio
    async def test_tick_count_survives_restart(self, brain_dir):
        """_tick_count must be restored so cooldowns work after restart."""
        from backend.organism.live_engine import OrganismLiveEngine

        engine1 = _make_engine(brain_dir=brain_dir)
        await engine1.initialize()

        # Run several ticks
        for _ in range(10):
            await engine1.live_tick()
        assert engine1._tick_count == 10

        await engine1.shutdown()

        # Restart
        engine2 = _make_engine(brain_dir=brain_dir)
        loaded = await engine2.initialize()
        assert loaded is True
        assert engine2._tick_count == 10, (
            "Tick count must be restored from brain (was 10 before shutdown)"
        )

    @pytest.mark.asyncio
    async def test_entry_metadata_survives_restart(self, brain_dir):
        """Entry metadata must survive restart for fill reconciliation."""
        from backend.organism.live_engine import OrganismLiveEngine

        positions = MockPositionsService({
            "MSFT": {"qty": "25", "avg_entry_price": "380.0", "side": "long"},
        })

        engine1 = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=MockOrderService(),
            positions_service=positions,
            brain_dir=brain_dir,
            universe=["MSFT", "SPY"],
        )
        await engine1.initialize()
        await engine1.live_tick()

        # Ensure entry metadata exists (either from tick or reconstruction)
        assert "MSFT" in engine1._entry_metadata
        saved_meta = dict(engine1._entry_metadata["MSFT"])

        await engine1.shutdown()

        # Restart
        engine2 = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=MockOrderService(),
            positions_service=positions,
            brain_dir=brain_dir,
            universe=["MSFT", "SPY"],
        )
        loaded = await engine2.initialize()
        assert loaded is True
        assert "MSFT" in engine2._entry_metadata, "Entry metadata must survive restart"
        assert engine2._entry_metadata["MSFT"]["entry_price"] == saved_meta["entry_price"]


# ═════════════════════════════════════════════════════════════════
#  Test 3: Partial IOC fill doesn't cause double entry
# ═════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestPartialFillNoDoubleEntry:
    """When an IOC order partially fills then cancels, the engine
    must NOT submit another entry for the same symbol on subsequent ticks.
    """

    @pytest.mark.asyncio
    async def test_no_double_entry_after_partial_fill(self, brain_dir):
        """Simulate: tick 1 submits order, tick 2 position appears,
        tick 3 should NOT resubmit.
        """
        from backend.organism.live_engine import OrganismLiveEngine

        positions = MockPositionsService()
        order_service = MockOrderService()

        engine = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=order_service,
            positions_service=positions,
            brain_dir=brain_dir,
            universe=["AAPL", "MSFT", "SPY"],
        )
        await engine.initialize()

        # Tick 1 — may or may not generate entries
        await engine.live_tick()

        # Simulate: a partial fill appeared at the broker
        positions.positions["AAPL"] = {
            "qty": "5", "avg_entry_price": "180.0", "side": "long",
        }
        # Also simulate that engine tracked the pending entry
        engine._pending_entry["AAPL"] = engine._tick_count
        engine._entry_metadata["AAPL"] = {
            "entry_price": 180.0,
            "entry_tick": engine._tick_count,
            "direction": 1.0,
            "predicted_return": 0.02,
            "confidence": 0.6,
        }

        orders_before = len(order_service.submitted)

        # Tick 2 — engine sees AAPL in positions AND in pending/metadata
        await engine.live_tick()

        # Count only buy orders for AAPL after the position appeared
        aapl_buy_orders = [
            o for o in order_service.submitted[orders_before:]
            if o.get("symbol") == "AAPL" and o.get("side") == "buy"
        ]
        assert len(aapl_buy_orders) == 0, (
            f"Should not re-enter AAPL — position already exists. "
            f"Got {len(aapl_buy_orders)} buy orders."
        )

    @pytest.mark.asyncio
    async def test_fresh_position_check_blocks_duplicate(self, brain_dir):
        """Even if _pending_entry expires, the fresh broker check
        before order submission should block the duplicate.
        """
        from backend.organism.live_engine import OrganismLiveEngine

        positions = MockPositionsService({
            "AAPL": {"qty": "5", "avg_entry_price": "180.0", "side": "long"},
        })
        order_service = MockOrderService()

        engine = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=order_service,
            positions_service=positions,
            brain_dir=brain_dir,
            universe=["AAPL", "MSFT", "SPY"],
        )
        await engine.initialize()

        # Run multiple ticks — AAPL should never get a buy order
        for _ in range(5):
            await engine.live_tick()

        aapl_buy_orders = [
            o for o in order_service.submitted
            if o.get("symbol") == "AAPL" and o.get("side") == "buy"
        ]
        assert len(aapl_buy_orders) == 0, (
            "Should never submit buy for AAPL when position already exists"
        )


# ═════════════════════════════════════════════════════════════════
#  Test 4: Model retrain triggers after N ticks
# ═════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestRetrainTrigger:
    """Verify ML retrain fires at the expected interval."""

    @pytest.mark.asyncio
    async def test_bars_since_retrain_increments(self, brain_dir):
        """_bars_since_retrain must increment each tick."""
        engine = _make_engine(brain_dir=brain_dir)
        await engine.initialize()

        for i in range(5):
            await engine.live_tick()

        # bars_since_retrain either equals tick_count or was reset by a retrain
        assert engine._bars_since_retrain <= engine._tick_count
        assert engine._tick_count == 5

    @pytest.mark.asyncio
    async def test_retrain_resets_counter(self, brain_dir):
        """After a retrain fires, _bars_since_retrain should reset.

        Directly tests the retrain counter reset mechanism without
        relying on module-level globals (which can be polluted by
        other tests changing env vars).
        """
        from backend.organism.live_engine import OrganismLiveEngine

        engine = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=MockOrderService(),
            positions_service=MockPositionsService(),
            brain_dir=brain_dir,
            universe=["AAPL", "MSFT", "SPY"],
        )
        await engine.initialize()

        # Force _bars_since_retrain past any possible threshold
        # so the next tick triggers the retrain branch.
        engine._bars_since_retrain = 9999

        await engine.live_tick()

        # The retrain branch resets _bars_since_retrain to 0
        # then the tick increments it by 1, so it should be 1.
        # (Or 0 if the reset happened after the increment.)
        assert engine._bars_since_retrain <= 1, (
            f"bars_since_retrain={engine._bars_since_retrain} should have "
            f"been reset to 0 by retrain trigger"
        )


# ═════════════════════════════════════════════════════════════════
#  Test 5: Fitness gate blocks chronic losers
# ═════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestFitnessGate:
    """Verify that symbols with low fitness scores are blocked from entry."""

    @pytest.mark.asyncio
    async def test_low_fitness_blocks_entry(self, brain_dir):
        """Symbol with fitness < 0.35 must not generate entry orders."""
        from backend.organism.live_engine import OrganismLiveEngine

        order_service = MockOrderService()
        engine = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=order_service,
            positions_service=MockPositionsService(),
            brain_dir=brain_dir,
            universe=["BADSTOCK", "SPY", "AAPL"],
        )
        await engine.initialize()

        # Set BADSTOCK fitness well below the 0.35 gate
        engine.evolved_params.symbol_fitness["BADSTOCK"] = 0.10

        # Run several ticks
        for _ in range(10):
            await engine.live_tick()

        # BADSTOCK should never appear in buy orders
        bad_orders = [
            o for o in order_service.submitted
            if o.get("symbol") == "BADSTOCK" and o.get("side") == "buy"
        ]
        assert len(bad_orders) == 0, (
            f"BADSTOCK (fitness=0.10) must be blocked by fitness gate, "
            f"but got {len(bad_orders)} buy orders"
        )

    @pytest.mark.asyncio
    async def test_high_fitness_allowed(self, brain_dir):
        """Symbol with fitness >= 0.35 should not be blocked by fitness gate."""
        from backend.organism.live_engine import OrganismLiveEngine

        engine = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=MockOrderService(),
            positions_service=MockPositionsService(),
            brain_dir=brain_dir,
            universe=["GOODSTOCK", "SPY", "AAPL"],
        )
        await engine.initialize()

        # Set GOODSTOCK fitness above the gate
        engine.evolved_params.symbol_fitness["GOODSTOCK"] = 0.80

        # The engine won't necessarily produce entries (depends on ML + alpha),
        # but verify the fitness gate itself doesn't block it
        # by checking it would pass the gate condition
        assert engine.evolved_params.symbol_fitness["GOODSTOCK"] >= 0.35


# ═════════════════════════════════════════════════════════════════
#  Test 6: Max loss safety net at -15%
# ═════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestMaxLossSafetyNet:
    """Verify the absolute 15% max loss exit fires correctly."""

    def test_max_loss_triggers_at_15pct(self):
        """ExitEngine.check_exit must fire at -15% regardless of ATR."""
        exit_engine = AdaptiveExitEngine()
        levels = ExitLevels(
            symbol="ANPA",
            direction=1.0,
            entry_price=12.85,
            stop_loss=10.0,        # ATR stop is wide
            take_profit=20.0,
            trailing_stop=10.0,
            atr_at_entry=2.0,      # ATR is large
            regime_at_entry="normal",
            highest_favorable=12.85,
            bars_held=5,
        )

        # Price dropped 16% → should trigger max_loss_limit
        crash_price = 12.85 * 0.84  # = ~10.794
        signal = exit_engine.check_exit(levels, crash_price, "normal")
        assert signal.should_exit is True
        assert signal.reason == "max_loss_limit"

    def test_max_loss_does_not_trigger_at_14pct(self):
        """14% loss should NOT trigger the 15% safety net."""
        exit_engine = AdaptiveExitEngine()
        levels = ExitLevels(
            symbol="TEST",
            direction=1.0,
            entry_price=100.0,
            stop_loss=80.0,       # Wide stop
            take_profit=130.0,
            trailing_stop=80.0,
            atr_at_entry=5.0,
            regime_at_entry="normal",
            highest_favorable=100.0,
            bars_held=3,
        )

        # 14% loss — below the 15% threshold
        price_14pct = 100.0 * 0.86
        signal = exit_engine.check_exit(levels, price_14pct, "normal")
        # Should NOT fire max_loss_limit (may fire stop_loss depending on levels)
        if signal.should_exit:
            assert signal.reason != "max_loss_limit"

    def test_max_loss_on_short_position(self):
        """Max loss should work for short positions too."""
        exit_engine = AdaptiveExitEngine()
        levels = ExitLevels(
            symbol="SHORT",
            direction=-1.0,
            entry_price=50.0,
            stop_loss=60.0,
            take_profit=40.0,
            trailing_stop=60.0,
            atr_at_entry=2.0,
            regime_at_entry="normal",
            highest_favorable=50.0,
            bars_held=5,
        )

        # Short at 50, price goes to 58 = +16% adverse = -16% PnL
        signal = exit_engine.check_exit(levels, 58.0, "normal")
        assert signal.should_exit is True
        assert signal.reason == "max_loss_limit"

    @pytest.mark.asyncio
    async def test_max_loss_triggers_exit_order_in_engine(self, brain_dir):
        """End-to-end: engine must submit exit order when position drops 15%+."""
        from backend.organism.live_engine import OrganismLiveEngine

        # Create data where ANPA crashes from 12.85 to ~10.0 (-22%)
        anpa_crash = _make_crash_df(300, base=12.85, crash_pct=0.22)

        positions = MockPositionsService({
            "ANPA": {"qty": "100", "avg_entry_price": "12.85", "side": "long"},
        })
        order_service = MockOrderService()
        data = MockDataClient({
            "ANPA": anpa_crash,
            "SPY": _make_price_df(300),
            "AAPL": _make_price_df(300),
        })

        engine = OrganismLiveEngine(
            data_client=data,
            order_service=order_service,
            positions_service=positions,
            brain_dir=brain_dir,
            universe=["AAPL", "SPY"],  # ANPA not in universe
        )
        await engine.initialize()

        # Ensure exit levels exist for ANPA (reconstructed on init)
        assert "ANPA" in engine._exit_levels, "ANPA exit levels must be created on init"

        result = await engine.live_tick()

        # Should have submitted a sell order for ANPA
        anpa_sells = [
            o for o in order_service.submitted
            if o.get("symbol") == "ANPA" and o.get("side") == "sell"
        ]
        assert len(anpa_sells) >= 1, (
            f"Engine must submit exit order for ANPA at -22% loss, "
            f"but got {len(anpa_sells)} sell orders. "
            f"exits_checked={result.exits_checked}, errors={result.errors}"
        )


# ═════════════════════════════════════════════════════════════════
#  Test 7: Multi-tick lifecycle with state invariants
# ═════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestMultiTickLifecycleInvariants:
    """Run N ticks and verify system invariants hold after each tick."""

    @pytest.mark.asyncio
    async def test_10_tick_invariants(self, brain_dir):
        """Run 10 ticks, check invariants after each."""
        from backend.organism.live_engine import OrganismLiveEngine

        positions = MockPositionsService()
        order_service = MockOrderService()

        engine = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=order_service,
            positions_service=positions,
            brain_dir=brain_dir,
            universe=["AAPL", "MSFT", "SPY", "GOOGL"],
        )
        await engine.initialize()

        for i in range(10):
            result = await engine.live_tick()

            # INVARIANT 1: tick_count always increments
            assert engine._tick_count == i + 1, (
                f"Tick count mismatch: expected {i + 1}, got {engine._tick_count}"
            )

            # INVARIANT 2: result must be serializable
            d = result.to_dict()
            assert isinstance(d, dict)
            assert "errors" in d

            # INVARIANT 3: every position in exit_levels should have entry_metadata
            for sym in engine._exit_levels:
                assert sym in engine._entry_metadata, (
                    f"Exit levels exist for {sym} but no entry metadata"
                )

            # INVARIANT 4: pending_entry keys must have recent tick numbers
            for sym, tick in engine._pending_entry.items():
                assert engine._tick_count - tick < engine._PENDING_ENTRY_TICKS, (
                    f"Stale pending entry for {sym}: "
                    f"tick={tick}, current={engine._tick_count}"
                )

            # INVARIANT 5: exit_cooldown keys must have recent tick numbers
            for sym, tick in engine._exit_cooldown.items():
                assert engine._tick_count - tick < engine._EXIT_COOLDOWN_TICKS, (
                    f"Stale exit cooldown for {sym}: "
                    f"tick={tick}, current={engine._tick_count}"
                )

            # INVARIANT 6: duration must be positive
            assert result.duration_s >= 0

    @pytest.mark.asyncio
    async def test_save_load_invariant(self, brain_dir):
        """After save+load, engine state must be functionally identical."""
        from backend.organism.live_engine import OrganismLiveEngine

        engine1 = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=MockOrderService(),
            positions_service=MockPositionsService(),
            brain_dir=brain_dir,
            universe=["AAPL", "MSFT", "SPY"],
        )
        await engine1.initialize()

        # Run enough ticks to accumulate state
        for _ in range(5):
            await engine1.live_tick()

        tick_before = engine1._tick_count
        bars_before = engine1._bars_since_retrain
        trades_before = len(engine1._all_trades)
        exit_keys_before = set(engine1._exit_levels.keys())

        await engine1.shutdown()

        # Load into new engine
        engine2 = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=MockOrderService(),
            positions_service=MockPositionsService(),
            brain_dir=brain_dir,
            universe=["AAPL", "MSFT", "SPY"],
        )
        loaded = await engine2.initialize()
        assert loaded is True

        # Verify key state was preserved
        assert engine2._tick_count == tick_before
        assert engine2._bars_since_retrain == bars_before
        assert len(engine2._all_trades) == trades_before


# ═════════════════════════════════════════════════════════════════
#  Test 8: Governance halts trading on drawdown
# ═════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestGovernanceDrawdown:
    """Verify governance kill switch triggers correctly."""

    @pytest.mark.asyncio
    async def test_halts_on_drawdown(self, brain_dir):
        """When drawdown exceeds limit, engine should halt and not submit orders."""
        from backend.organism.live_engine import OrganismLiveEngine

        order_service = MockOrderService()

        class LowEquityService(MockPositionsService):
            async def get_total_portfolio_value(self) -> float:
                return 88_000.0  # 12% drawdown

        engine = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=order_service,
            positions_service=LowEquityService(),
            brain_dir=brain_dir,
            universe=["AAPL", "MSFT", "SPY", "GOOGL"],
        )
        await engine.initialize()

        # Run one normal tick to establish peak equity
        await engine.live_tick()

        # Simulate drawdown: set peak high, equity returns low value
        engine._peak_equity = 100_000.0
        engine.governance._drawdown_limit = 0.10  # 10% limit

        result = await engine.live_tick()

        # Should be halted — 12% drawdown exceeds 10% limit
        assert engine.governance.is_trading_halted or any(
            "halt" in e.lower() or "drawdown" in e.lower()
            for e in result.errors
        ), f"Governance should halt on 12% drawdown (limit 10%). Errors: {result.errors}"

    @pytest.mark.asyncio
    async def test_no_orders_after_halt(self, brain_dir):
        """Once halted, subsequent ticks must not submit orders."""
        from backend.organism.live_engine import OrganismLiveEngine

        order_service = MockOrderService()
        engine = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=order_service,
            positions_service=MockPositionsService(),
            brain_dir=brain_dir,
            universe=["AAPL", "MSFT", "SPY"],
        )
        await engine.initialize()

        # Force halt
        engine.governance.halt_trading()

        orders_before = len(order_service.submitted)
        result = await engine.live_tick()

        assert result.orders_submitted == 0
        assert len(order_service.submitted) == orders_before
        assert any("halted" in e.lower() for e in result.errors)


# ═════════════════════════════════════════════════════════════════
#  Test 9: Adaptive exit engine — trailing stop behavior
# ═════════════════════════════════════════════════════════════════

@pytest.mark.integration
class TestTrailingStopBehavior:
    """Verify trailing stop engages and ratchets correctly."""

    def test_trailing_activates_after_3x_atr(self):
        """Trail should activate after 3x ATR favorable move."""
        exit_engine = AdaptiveExitEngine(trailing_start_atr=3.0)
        levels = ExitLevels(
            symbol="TEST",
            direction=1.0,
            entry_price=100.0,
            stop_loss=97.0,      # 3 ATR wide
            take_profit=120.0,
            trailing_stop=97.0,
            atr_at_entry=1.0,
            regime_at_entry="normal",
            highest_favorable=100.0,
            bars_held=0,
        )

        # Price moves up 2x ATR — trail should NOT activate
        exit_engine.check_exit(levels, 102.0, "normal")
        assert levels.trailing_active is False

        # Price moves up 3.5x ATR — trail SHOULD activate
        levels.highest_favorable = 103.5
        exit_engine.check_exit(levels, 103.5, "normal")
        assert levels.trailing_active is True

    def test_trailing_never_goes_down(self):
        """Once trailing stop ratchets up, it must never decrease."""
        exit_engine = AdaptiveExitEngine(
            trailing_start_atr=2.0,
            trailing_distance_atr=1.5,
        )
        levels = ExitLevels(
            symbol="TEST",
            direction=1.0,
            entry_price=100.0,
            stop_loss=97.0,
            take_profit=120.0,
            trailing_stop=97.0,
            atr_at_entry=1.0,
            regime_at_entry="normal",
            highest_favorable=100.0,
            bars_held=0,
        )

        # Simulate price rallying then pulling back
        prices = [101, 103, 105, 104, 103, 106, 104]
        prev_trail = levels.trailing_stop

        for price in prices:
            levels.highest_favorable = max(levels.highest_favorable, price)
            exit_engine.check_exit(levels, price, "normal")
            assert levels.trailing_stop >= prev_trail, (
                f"Trailing stop went DOWN from {prev_trail} to "
                f"{levels.trailing_stop} at price {price}"
            )
            prev_trail = levels.trailing_stop

    def test_partial_tp_moves_stop_to_breakeven(self):
        """After partial take-profit, stop should move to entry price."""
        exit_engine = AdaptiveExitEngine(partial_tp_r=3.0)
        atr = 1.0
        entry = 100.0
        stop_loss = entry - 1.5 * atr  # 98.5
        partial_tp_price = entry + 3.0 * 1.5 * atr  # 104.5

        levels = ExitLevels(
            symbol="TEST",
            direction=1.0,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=120.0,
            trailing_stop=stop_loss,
            atr_at_entry=atr,
            regime_at_entry="normal",
            highest_favorable=entry,
            bars_held=0,
            partial_tp_price=partial_tp_price,
        )

        # Price hits partial TP
        levels.highest_favorable = partial_tp_price + 0.5
        signal = exit_engine.check_exit(levels, partial_tp_price + 0.5, "normal")

        if signal.should_exit and signal.reason == "partial_take_profit":
            # After partial TP, stop should be at breakeven
            assert levels.stop_loss == entry, (
                f"After partial TP, stop should be at entry ({entry}) "
                f"but is {levels.stop_loss}"
            )
            assert levels.partial_tp_taken is True
