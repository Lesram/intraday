"""Nonvacuous replay adapter checks using actual simulated execution receipts."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from backend.organism import close_accounting
from backend.organism.live_engine import LiveTickResult, OrganismLiveEngine
from backend.organism.replay_simulator import (
    HistoricalBarProvider, ReplayEngine, SimulatedBroker, make_features_dict,
)

NOW = datetime(2026, 8, 3, 16, tzinfo=UTC)


def real_engine(tmp_path, broker, now=NOW):
    engine = OrganismLiveEngine(
        data_client=MagicMock(), order_service=broker, positions_service=broker,
        brain_dir=str(tmp_path / "brain"), universe=["TSLA"],
    )
    engine._tick_count = 10
    engine._now_fn = lambda: now
    engine._time_fn = lambda: now.timestamp()
    engine._lookup_closed_position_fills_from_db = broker.lookup_closed_position_fills
    engine._entry_verified_unfilled = broker.entry_verified_unfilled
    engine._save_brain = MagicMock()
    engine._bg_trainer.start = AsyncMock()
    engine._reconstruct_position_state = AsyncMock()
    broker._now_fn = engine._now_fn
    return engine


def track(engine, entry):
    engine._entry_metadata["TSLA"] = {
        "entry_order_id": entry["order_id"], "entry_price": float(entry["avg_fill_price"]),
        "filled_shares": int(entry["filled_qty"]), "entry_tick": 1,
        "entry_time": NOW.timestamp() - 60, "direction": 1, "entry_source": "alpha",
        "confidence": 0.6,
    }
    engine._last_exit_reason["TSLA"] = "stop_loss"


async def execute(broker, side, qty, price):
    broker.set_price("TSLA", price)
    return await broker.submit_symbol_order(symbol="TSLA", side=side, qty=qty)


async def test_actual_partial_receipts_reach_ledger_learner_and_restart_once(tmp_path):
    broker = SimulatedBroker()
    engine = real_engine(tmp_path, broker)
    entry = await execute(broker, "buy", 6, 100)
    track(engine, entry)
    partial = await execute(broker, "sell", 2, 101)
    await execute(broker, "sell", 4, 99)
    # Model delayed receipt availability, not an invented missing execution.
    broker.filled_orders.remove(partial)
    await engine._reconcile_fills({})
    assert engine.learner.state.total_trades == 0
    assert engine._all_trades == []
    assert engine._entry_metadata["TSLA"]["pending_close"]
    broker.filled_orders.insert(1, partial)
    await engine._reconcile_fills({})
    assert len(engine._all_trades) == engine.learner.state.total_trades == 1
    assert engine._all_trades[0].pnl == engine.learner.state.cumulative_pnl == -2
    assert engine._all_trades[0].price_source == "simulated_position_fills"
    assert engine._all_trades[0].had_partial_exits
    assert engine._all_trades[0].entry_order_id == entry["order_id"]
    await engine._reconcile_fills({})
    restarted = real_engine(tmp_path, broker)
    await restarted.initialize()
    await restarted._reconcile_fills({})
    assert len(restarted._all_trades) == restarted.learner.state.total_trades == 1
    assert restarted.learner.state.cumulative_pnl == -2
    assert restarted._all_trades[0].price_source == "simulated_position_fills"


async def test_pyramid_and_clipped_exit_use_actual_executions_not_requested_qty(tmp_path):
    broker = SimulatedBroker(commission_per_share=0.01)
    engine = real_engine(tmp_path, broker)
    entry = await execute(broker, "buy", 2, 100)
    track(engine, entry)
    await execute(broker, "buy", 4, 103)
    await execute(broker, "sell", 2, 104)
    last = await execute(broker, "sell", 100, 101)
    assert last["filled_qty"] == last["qty"] == "4"
    await engine._reconcile_fills({})
    assert len(engine._all_trades) == 1
    # Entry cash 612; exit cash 208 + 404 = 612. Commissions remain separate.
    assert engine._all_trades[0].pnl == 0
    assert engine._all_trades[0].shares == 6
    assert engine._all_trades[0].entry_price == 102
    assert broker.total_commission == pytest.approx(0.12)
    assert broker.cash == pytest.approx(broker.initial_cash - 0.12)


async def test_same_timestamp_multiple_lifetimes_keep_execution_order(tmp_path):
    broker = SimulatedBroker()
    engine = real_engine(tmp_path, broker)
    for entry_price, exit_price in ((100, 102), (110, 107)):
        entry = await execute(broker, "buy", 2, entry_price)
        track(engine, entry)
        await execute(broker, "sell", 2, exit_price)
        await engine._reconcile_fills({})
    assert [trade.pnl for trade in engine._all_trades] == [4, -6]
    assert engine.learner.state.total_trades == 2
    assert engine.learner.state.cumulative_pnl == -2
    assert len({row["id"] for row in broker.filled_orders}) == 4
    assert len({row["submitted_at"] for row in broker.filled_orders}) == 1


async def test_next_open_model_uses_actual_costed_fill_receipts(tmp_path):
    # Existing delay_fill is synchronous execution at the next-open PRICE,
    # not a queued asynchronous order lifecycle; keep that limitation explicit.
    bars = pd.DataFrame({"open": [100, 100, 105, 99], "high": [100, 100, 105, 99],
                         "low": [100, 100, 105, 99], "close": [100, 100, 105, 99],
                         "volume": [10000] * 4})
    provider = HistoricalBarProvider({"TSLA": bars}, lookback=2)
    broker = SimulatedBroker(delay_fill=True, slippage_bps=1, half_spread_bps=2)
    broker.set_bar_provider(provider)
    engine = real_engine(tmp_path, broker)
    entry = await execute(broker, "buy", 6, 100)
    track(engine, entry)
    provider.advance()
    exit_order = await execute(broker, "sell", 6, 105)
    await engine._reconcile_fills({})
    assert float(entry["avg_fill_price"]) == pytest.approx(105 * 1.0003)
    assert float(exit_order["avg_fill_price"]) == pytest.approx(99 * 0.9997)
    assert engine.learner.state.total_trades == 1
    assert engine.learner.state.cumulative_pnl == pytest.approx((99 * 0.9997 - 105 * 1.0003) * 6)
    assert not engine._entry_metadata


async def test_future_or_conflicting_receipts_never_become_exact(tmp_path):
    broker = SimulatedBroker()
    engine = real_engine(tmp_path, broker)
    entry = await execute(broker, "buy", 6, 100)
    track(engine, entry)
    broker._now_fn = lambda: NOW + timedelta(minutes=1)
    exit_order = await execute(broker, "sell", 6, 101)
    await engine._reconcile_fills({})
    assert engine.learner.state.total_trades == 0
    assert engine._all_trades == []
    exit_order["submitted_at"] = NOW.isoformat()
    exit_order["attributes"]["source"] = "manual"
    await engine._reconcile_fills({})
    assert engine.learner.state.total_trades == 0


async def test_replay_run_wires_actual_receipts_to_real_engine_consumers(tmp_path, monkeypatch):
    observed = []
    async def controlled_tick(engine):
        engine._tick_count += 10
        if not observed:
            broker = engine._order_service
            entry = await execute(broker, "buy", 6, 100)
            track(engine, entry)
            await execute(broker, "sell", 2, 101)
            await execute(broker, "sell", 4, 99)
        # Real reconciliation and all real consumers; only signal generation is
        # scripted, so this wiring test cannot pass with zero executions.
        await engine._reconcile_fills({})
        observed.append((engine.learner.state.total_trades, engine.learner.state.cumulative_pnl,
                         len(engine._all_trades), engine._all_trades[0].price_source))
        return LiveTickResult()
    monkeypatch.setattr(OrganismLiveEngine, "live_tick", controlled_tick)
    monkeypatch.setattr(OrganismLiveEngine, "initialize", AsyncMock(return_value=False))
    replay = ReplayEngine(make_features_dict(["TSLA"], n=20), slippage_bps=0,
                          lookback=10, brain_dir=str(tmp_path / "brain"))
    result = await replay.run(max_ticks=2)
    assert len(result.orders) == 3 and len(result.trades) == 2
    assert result.total_pnl == -2
    assert len(result.accounted_trades) == 1
    assert result.accounted_trades[0]["price_source"] == "simulated_position_fills"
    assert not result.accounting_pending
    assert observed == [(1, -2, 1, "simulated_position_fills")] * 2
    checkpoint = close_accounting.read(tmp_path / "brain")
    assert checkpoint["learner_total"] == 1
    assert checkpoint["all_trades"][0].price_source == "simulated_position_fills"


async def test_broker_namespaces_prevent_identity_reuse_across_replays():
    first, second = SimulatedBroker(), SimulatedBroker()
    first_receipt = await execute(first, "buy", 1, 100)
    second_receipt = await execute(second, "buy", 1, 100)
    assert first_receipt["id"] != second_receipt["id"]


async def test_rejected_simulation_entry_is_verified_empty_before_later_close(tmp_path):
    broker = SimulatedBroker(initial_cash=0)
    engine = real_engine(tmp_path, broker)
    rejected = await execute(broker, "buy", 6, 100)
    assert rejected["status"] == "rejected"
    assert rejected["order_id"] == rejected["id"]
    # The frozen caller records optimistic quantity even for a rejection.
    engine._entry_metadata["TSLA"] = {
        "entry_order_id": rejected["order_id"], "entry_tick": 1,
        "entry_price": 100, "filled_shares": 6, "direction": 1,
        "entry_source": "alpha", "entry_time": NOW.timestamp() - 60,
    }
    await engine._reconcile_fills({})
    assert not engine._entry_metadata
    assert engine.learner.state.total_trades == 0
    assert not broker.filled_orders
    broker.cash = 100000
    entry = await execute(broker, "buy", 6, 100)
    track(engine, entry)
    await execute(broker, "sell", 2, 101)
    await execute(broker, "sell", 4, 99)
    await engine._reconcile_fills({})
    assert len(engine._all_trades) == engine.learner.state.total_trades == 1
    assert engine.learner.state.cumulative_pnl == -2
