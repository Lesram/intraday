"""Fault-injected, isolated integration tests for close accounting authority."""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.organism import close_accounting
from backend.organism.live_engine import OrganismLiveEngine
from backend.organism.live_engine_fills import ClosedPositionFills
import test_live_engine_fill_accounting as fill_fixtures
from test_live_engine_fill_accounting import ANCHOR, CLOSE, START, order, store_rows

# Register the shared isolated SQLite fixture without shadowing an import in
# every test's fixture argument list.
database = fill_fixtures.database


def engine_at(tmp_path, database=None, now=CLOSE):
    broker = MagicMock()
    broker.get_all_positions = AsyncMock(return_value={})
    engine = OrganismLiveEngine(
        data_client=MagicMock(), order_service=broker, positions_service=broker,
        brain_dir=str(tmp_path / "brain"), universe=["TSLA", "AMD"],
        sessionmaker=database,
    )
    engine._now_fn = lambda: now
    engine._time_fn = lambda: now.timestamp()
    engine._tick_count = 10
    engine._daily_loss_date = close_accounting.session_date(now)
    engine._save_brain = MagicMock()
    engine._bg_trainer.start = AsyncMock()
    engine._reconstruct_position_state = AsyncMock()
    return engine


def track(engine, symbol="TSLA", entry_id=ANCHOR):
    engine._entry_metadata[symbol] = {
        "entry_order_id": str(entry_id), "entry_price": 100,
        "entry_tick": 1, "filled_shares": 6, "direction": 1,
        "entry_source": "alpha", "entry_time": START.timestamp(),
        "confidence": 0.6, "regime_at_entry": "trending_up",
    }
    engine._last_exit_reason[symbol] = "stop_loss"


def assert_consumers(engine, count, pnl):
    assert len(engine._all_trades) == count
    assert len(engine.learner.trade_history) == count
    assert engine.learner.state.total_trades == count
    assert engine.learner.state.cumulative_pnl == pytest.approx(pnl)
    assert sum(v[1] for v in engine.signal_gen.calibration_to_dict()["counts"]) == count
    assert sum(v["total_pnl"] for v in engine.kelly_sizer.regime_stats_to_dict().values()) == pytest.approx(pnl)


async def missing_partial(database):
    await store_rows(database, [order(1, "buy", 6, 100), order(3, "sell", 4, 99)])


async def complete_partial(database):
    await store_rows(database, [order(2, "sell", 2, 101)])


async def test_delayed_partial_resolves_once_with_original_time_and_reason(database, tmp_path):
    await missing_partial(database)
    engine = engine_at(tmp_path, database)
    track(engine)
    await engine._reconcile_fills({})
    assert_consumers(engine, 0, 0)
    assert engine._entry_metadata["TSLA"]["pending_close"]["observed_at"] == CLOSE.isoformat()
    assert not engine._symbol_daily_pnl
    await complete_partial(database)
    later = CLOSE + timedelta(minutes=10)
    engine._now_fn = lambda: later
    engine._time_fn = lambda: later.timestamp()
    engine._tick_count = 70
    await engine._reconcile_fills({})
    assert_consumers(engine, 1, -2)
    trade = engine._all_trades[0]
    assert trade.closed_at == CLOSE.isoformat()
    assert trade.exit_reason == "stop_loss" and trade.exit_bar == 10
    assert trade.entry_order_id == str(ANCHOR)
    assert trade.pnl - (600 * 0.0006) == pytest.approx(-2.36)
    assert engine._symbol_daily_pnl == {"TSLA": -2}
    assert engine._symbol_exit_tick == {"TSLA": 10}
    assert engine._symbol_stop_loss_times == {"TSLA": [CLOSE.timestamp()]}
    await engine._reconcile_fills({})
    assert_consumers(engine, 1, -2)
    assert not engine._order_service.submit_order.called


async def test_pending_and_resolved_restart_restore_all_consumers(database, tmp_path):
    await missing_partial(database)
    first = engine_at(tmp_path, database)
    track(first)
    await first._reconcile_fills({})
    restarted = engine_at(tmp_path, database)
    await restarted.initialize()
    assert "TSLA" in restarted._entry_metadata
    assert_consumers(restarted, 0, 0)
    await complete_partial(database)
    await restarted._reconcile_fills({})
    assert_consumers(restarted, 1, -2)
    assert not restarted._all_trades[0].is_reconciliation_artifact
    again = engine_at(tmp_path, database)
    await again.initialize()
    await again._reconcile_fills({})
    assert_consumers(again, 1, -2)
    assert again._symbol_daily_pnl == {"TSLA": -2}
    assert not again._entry_metadata


@pytest.mark.parametrize("stage", ["learner", "kelly", "calibration", "replace"])
async def test_failed_commit_restores_pending_and_every_consumer(database, tmp_path, monkeypatch, stage):
    await missing_partial(database)
    engine = engine_at(tmp_path, database)
    track(engine)
    await engine._reconcile_fills({})
    before = (engine.brain.brain_dir / close_accounting.CHECKPOINT_FILE).read_bytes()
    await complete_partial(database)
    with monkeypatch.context() as patch:
        def fail(*args, **kwargs):
            raise OSError("injected failure")
        if stage == "replace":
            patch.setattr(close_accounting.os, "replace", fail)
        else:
            target, method = {
                "learner": (engine.learner, "record_trade"),
                "kelly": (engine.kelly_sizer, "record_trade"),
                "calibration": (engine.signal_gen, "record_prediction_outcome"),
            }[stage]
            original = getattr(target, method)
            def mutate_then_fail(*args, **kwargs):
                original(*args, **kwargs)
                fail()
            patch.setattr(target, method, mutate_then_fail)
        with pytest.raises(OSError, match="injected"):
            await engine._reconcile_fills({})
    assert_consumers(engine, 0, 0)
    assert not engine._symbol_daily_pnl
    assert not engine._symbol_closed_today
    assert not engine._symbol_trade_counts_runtime
    assert (engine.brain.brain_dir / close_accounting.CHECKPOINT_FILE).read_bytes() == before
    assert engine._entry_metadata["TSLA"]["pending_close"]
    restarted = engine_at(tmp_path, database)
    await restarted.initialize()
    await restarted._reconcile_fills({})
    assert_consumers(restarted, 1, -2)


async def test_pending_checkpoint_failure_never_consumes_outcome(database, tmp_path, monkeypatch):
    await missing_partial(database)
    await complete_partial(database)
    engine = engine_at(tmp_path, database)
    track(engine)
    monkeypatch.setattr(close_accounting.os, "replace", MagicMock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        await engine._reconcile_fills({})
    assert_consumers(engine, 0, 0)
    assert "TSLA" in engine._entry_metadata
    assert not (engine.brain.brain_dir / close_accounting.CHECKPOINT_FILE).exists()


async def test_cross_session_resolution_keeps_old_close_out_of_today_risk(database, tmp_path):
    await missing_partial(database)
    first = engine_at(tmp_path, database)
    track(first)
    await first._reconcile_fills({})
    await complete_partial(database)
    second = engine_at(tmp_path, database, now=CLOSE + timedelta(days=1))
    await second.initialize()
    second._symbol_daily_pnl = {"AMD": 7}
    await second._reconcile_fills({})
    assert_consumers(second, 1, -2)
    assert second._symbol_daily_pnl == {"AMD": 7}
    assert not second._symbol_closed_today
    assert not second._symbol_stop_loss_times
    assert not second._symbol_exit_tick
    assert second._all_trades[0].closed_at == CLOSE.isoformat()


async def test_reappearing_position_clears_pending_and_preserves_management(database, tmp_path):
    await missing_partial(database)
    engine = engine_at(tmp_path, database)
    track(engine)
    await engine._reconcile_fills({})
    engine._positions_service.get_all_positions.return_value = {"TSLA": {"qty": 4, "avg_entry_price": 100}}
    await engine._reconcile_fills({})
    assert "pending_close" not in engine._entry_metadata["TSLA"]
    assert not close_accounting.read(engine.brain.brain_dir)["tracking"]["_entry_metadata"]["TSLA"].get("pending_close")
    await complete_partial(database)
    engine._positions_service.get_all_positions.return_value = {}
    later = CLOSE + timedelta(minutes=2)
    engine._now_fn = lambda: later
    await engine._reconcile_fills({})
    assert_consumers(engine, 1, -2)
    assert engine._all_trades[0].closed_at == later.isoformat()


async def test_complete_later_close_waits_for_earlier_close_and_ties_are_stable(tmp_path):
    engine = engine_at(tmp_path)
    # Reverse insertion order and lexical symbol order vs entry identity.
    track(engine, "AMD", uuid.UUID(int=2))
    track(engine, "TSLA", uuid.UUID(int=1))
    complete = False
    async def fills(symbol, meta, *, closed_at):
        if symbol == "TSLA" and not complete:
            return None
        return ClosedPositionFills(6, 100, 99, -6, False)
    engine._lookup_closed_position_fills_from_db = fills
    await engine._reconcile_fills({})
    assert_consumers(engine, 0, 0)
    assert {meta["pending_close"]["observed_at"] for meta in engine._entry_metadata.values()} == {CLOSE.isoformat()}
    complete = True
    await engine._reconcile_fills({})
    assert [trade.symbol for trade in engine.learner.trade_history] == ["TSLA", "AMD"]
    assert_consumers(engine, 2, -12)


@pytest.mark.parametrize("status,filled,cleared", [("rejected", 0, True), ("canceled", 0, True), ("new", 0, False), ("canceled", 1, False)])
async def test_only_verified_terminal_zero_fill_cleans_up(database, tmp_path, status, filled, cleared):
    await store_rows(database, [order(1, "buy", filled, 100, qty=Decimal(6), status=status)])
    engine = engine_at(tmp_path, database)
    track(engine)
    await engine._reconcile_fills({})
    assert ("TSLA" not in engine._entry_metadata) is cleared
    assert_consumers(engine, 0, 0)


@pytest.mark.parametrize("damage", ["checksum", "version", "json"])
async def test_invalid_authority_aborts_startup_without_legacy_fallback(tmp_path, damage):
    engine = engine_at(tmp_path)
    close_accounting.write(engine)
    path = engine.brain.brain_dir / close_accounting.CHECKPOINT_FILE
    content = json.loads(path.read_bytes())
    if damage == "checksum":
        content["state"]["learner_total"] = 999
    else:
        content["version"] = 999
    path.write_text("{" if damage == "json" else json.dumps(content))
    restarted = engine_at(tmp_path)
    restarted.brain.load = MagicMock()
    with pytest.raises((ValueError, json.JSONDecodeError)):
        await restarted.initialize()
    restarted.brain.load.assert_not_called()
    assert not restarted._initialized


async def test_legacy_files_torn_after_commit_cannot_override_accounting(database, tmp_path):
    await missing_partial(database)
    await complete_partial(database)
    engine = engine_at(tmp_path, database)
    track(engine)
    # A failure AFTER authoritative commit is not a reason to reverse it.
    engine._save_brain = MagicMock(side_effect=OSError("legacy save interrupted"))
    await engine._reconcile_fills({})
    assert_consumers(engine, 1, -2)
    root = engine.brain.brain_dir
    (root / "learning_state.json").write_text('{"total_trades":999,"cumulative_pnl":999}')
    (root / "trade_history.csv").write_text("symbol,pnl\nBAD,999\n")
    restarted = engine_at(tmp_path, database)
    await restarted.initialize()
    assert_consumers(restarted, 1, -2)
    assert restarted._symbol_daily_pnl == {"TSLA": -2}
    assert not restarted._entry_metadata


async def test_upgrade_preserves_historical_record_and_inherited_learner_state(tmp_path):
    from backend.organism.continuous_learner import TradeRecord
    engine = engine_at(tmp_path)
    legacy = TradeRecord("OLD", 1, 10, 11, 0, 1, 1, 1, "legacy", 0, 0.1, 0.5)
    legacy.predicted_return_signed = float("nan")
    engine._all_trades = [legacy]
    engine.learner.trade_history = [legacy]
    engine.learner.state.total_trades = 609
    engine.learner.state.cumulative_pnl = 123.4
    close_accounting.write(engine)
    fresh = engine_at(tmp_path)
    await fresh.initialize()
    assert fresh.learner.state.total_trades == 609
    assert fresh.learner.state.cumulative_pnl == 123.4
    assert len(fresh._all_trades) == 1
    assert fresh._all_trades[0].closed_at == ""
    assert fresh._all_trades[0].entry_order_id == ""
    assert fresh._all_trades[0].pnl == 1


def test_serialized_saves_cannot_publish_during_accounting_commit(tmp_path):
    engine = engine_at(tmp_path)
    entered, completed = threading.Event(), threading.Event()
    @close_accounting.serialized
    def save_projection(host):
        entered.set()
        close_accounting.write(host)
        completed.set()
    with engine._accounting_lock:
        worker = threading.Thread(target=save_projection, args=(engine,))
        worker.start()
        assert not entered.wait(0.05)
        engine.learner.state.cumulative_pnl = 17
    worker.join(timeout=2)
    assert completed.is_set()
    assert close_accounting.read(engine.brain.brain_dir)["learner_pnl"] == 17


async def test_zero_order_summary_cannot_override_confirmed_execution(database, tmp_path):
    from backend.infra.schemas import Execution
    await store_rows(database, [order(1, "buy", 0, 100, qty=Decimal(6), status="canceled")])
    async with database() as session:
        session.add(Execution(order_id=ANCHOR, fill_qty=Decimal(1), fill_price=Decimal(100),
                              ts=START, venue="fixture"))
        await session.commit()
    engine = engine_at(tmp_path, database)
    track(engine)
    await engine._reconcile_fills({})
    assert "TSLA" in engine._entry_metadata
    assert_consumers(engine, 0, 0)


async def test_stale_legacy_ticks_cannot_bypass_pending_barrier_or_refresh_cooldown(database, tmp_path, monkeypatch):
    monkeypatch.setenv("ORGANISM_TICK_INTERVAL_SECONDS", "10")
    await missing_partial(database)
    first = engine_at(tmp_path, database)
    first._tick_count = 500
    track(first)
    first._entry_metadata["TSLA"]["entry_tick"] = 495
    await first._reconcile_fills({})
    later = CLOSE + timedelta(hours=2)
    restarted = engine_at(tmp_path, database, now=later)
    restarted._tick_count = 400
    await restarted.initialize()
    assert restarted._tick_count >= 500
    # Even if an external legacy caller supplies an older tick after init,
    # an existing durable pending close must bypass entry grace.
    restarted._tick_count = 400
    track(restarted, "AMD", uuid.UUID(int=2))
    async def fills(symbol, meta, *, closed_at):
        if symbol == "TSLA":
            return None
        return ClosedPositionFills(6, 100, 99, -6, False)
    restarted._lookup_closed_position_fills_from_db = fills
    await restarted._reconcile_fills({})
    assert_consumers(restarted, 0, 0)
    await complete_partial(database)
    restarted._lookup_closed_position_fills_from_db = OrganismLiveEngine._lookup_closed_position_fills_from_db.__get__(restarted)
    await restarted._reconcile_fills({})
    assert_consumers(restarted, 1, -2)
    assert restarted._symbol_exit_tick["TSLA"] <= restarted._tick_count - restarted._STOP_LOSS_REENTRY_TICKS


async def test_save_worker_captures_on_owner_loop_and_cannot_overwrite_newer_commit(tmp_path):
    engine = engine_at(tmp_path)
    engine._accounting_owner_loop = asyncio.get_running_loop()
    owner_thread = threading.get_ident()
    capture_threads = []
    original_capture = close_accounting.capture
    from unittest.mock import patch
    def observed_capture(host):
        capture_threads.append(threading.get_ident())
        return original_capture(host)
    @close_accounting.save_serialized
    def legacy_save(host):
        assert threading.get_ident() != owner_thread
        # The legacy mirror may be arbitrarily old; it cannot replace authority.
        (host.brain.brain_dir / "learning_state.json").write_text('{"cumulative_pnl":-999}')
    engine.learner.state.cumulative_pnl = 3
    with patch.object(close_accounting, "capture", observed_capture):
        await asyncio.to_thread(legacy_save, engine)
    assert capture_threads == [owner_thread]
    assert close_accounting.read(engine.brain.brain_dir)["learner_pnl"] == 3


async def test_full_brain_swap_preserves_latest_accounting_authority(tmp_path):
    engine = engine_at(tmp_path)
    engine.learner.state.cumulative_pnl = 3
    close_accounting.write(engine)
    before = (engine.brain.brain_dir / close_accounting.CHECKPOINT_FILE).read_bytes()
    engine.brain.save(
        signal_gen=engine.signal_gen, learner=engine.learner, equity_curve=[],
        all_trades=[], epoch_metrics=[], extra_counters={},
    )
    assert (engine.brain.brain_dir / close_accounting.CHECKPOINT_FILE).read_bytes() == before


async def test_legacy_recovery_cannot_replace_preloaded_authority(tmp_path, monkeypatch):
    engine = engine_at(tmp_path)
    engine.learner.state.total_trades = 7
    engine.learner.state.cumulative_pnl = 11
    close_accounting.write(engine)
    restarted = engine_at(tmp_path)
    # Force the legacy load path, then simulate backup recovery replacing the
    # checkpoint with an older copy before initialize performs its overlay.
    monkeypatch.setattr(type(restarted.brain), "exists", property(lambda _: True))
    def recover_legacy():
        # A backup restore copies its older bytes; it does not pass through
        # the live monotonic publication guard.
        (restarted.brain.brain_dir / close_accounting.CHECKPOINT_FILE).unlink()
        return False
    restarted.brain.load = recover_legacy
    await restarted.initialize()
    assert restarted.learner.state.total_trades == 7
    assert restarted.learner.state.cumulative_pnl == 11
    assert close_accounting.read(restarted.brain.brain_dir)["learner_pnl"] == 11


async def test_idle_reconciliation_never_copies_history_or_writes_checkpoint(tmp_path, monkeypatch):
    engine = engine_at(tmp_path)
    monkeypatch.setattr(close_accounting, "capture", MagicMock(side_effect=AssertionError("idle capture")))
    monkeypatch.setattr(close_accounting, "write", MagicMock(side_effect=AssertionError("idle write")))
    await engine._reconcile_fills({})


@pytest.mark.parametrize("existing_authority", [False, True])
async def test_regressed_learner_cannot_poison_authority_before_legacy_save_guard(tmp_path, existing_authority):
    engine = engine_at(tmp_path)
    engine.learner.state.total_trades = 609
    engine.learner.state.cumulative_pnl = 123
    engine.brain.brain_dir.mkdir(parents=True)
    manifest = engine.brain.brain_dir / "manifest.json"
    manifest.write_text('{"total_trades":609}')
    path = engine.brain.brain_dir / close_accounting.CHECKPOINT_FILE
    if existing_authority:
        close_accounting.write(engine)
    before = path.read_bytes() if path.exists() else None
    engine.learner.state.total_trades = 0
    engine.learner.state.cumulative_pnl = 0
    with pytest.raises(ValueError, match="publication refused"):
        OrganismLiveEngine._save_brain(engine)
    assert (path.read_bytes() if path.exists() else None) == before
    with pytest.raises(ValueError, match="publication refused"):
        engine.force_save_brain()
    assert (path.read_bytes() if path.exists() else None) == before


@pytest.mark.parametrize("damage_head", [False, True])
async def test_real_legacy_save_interruption_and_backup_recovery_preserve_authority(database, tmp_path, monkeypatch, damage_head):
    from backend.organism.continuous_learner import TradeRecord
    engine = engine_at(tmp_path, database)
    old = TradeRecord("OLD", 1, 10, 13, 0, 1, 1, 3, "legacy", 0, 0.3, 0.5)
    engine._all_trades.append(old)
    engine.learner.record_trade(old)
    assert engine.force_save_brain()["success"]
    assert engine.force_save_brain()["success"]  # Creates an older valid backup.
    assert engine.brain.exists
    assert list(engine.brain.backup_dir.iterdir())
    await missing_partial(database)
    await complete_partial(database)
    track(engine)
    engine._save_brain = OrganismLiveEngine._save_brain.__get__(engine)
    engine.brain.walk_forward_gate = MagicMock(return_value=(False, "fixture gate"))
    # The real essential save publishes the new CSV and is then interrupted.
    monkeypatch.setattr(engine.brain, "_save_learning_state", MagicMock(side_effect=OSError("after csv")))
    await engine._reconcile_fills({})
    assert engine.learner.state.total_trades == 2
    assert engine.learner.state.cumulative_pnl == 1
    root = engine.brain.brain_dir
    assert "TSLA" in (root / "trade_history.csv").read_text()
    assert json.loads((root / "learning_state.json").read_text())["total_trades"] == 1
    if damage_head:
        (root / "manifest.json").write_text("{broken")
    restarted = engine_at(tmp_path, database)
    await restarted.initialize()  # Real brain.load(), including recovery if corrupt.
    assert len(restarted._all_trades) == 2
    assert restarted.learner.state.total_trades == 2
    assert restarted.learner.state.cumulative_pnl == 1
    assert restarted._symbol_daily_pnl == {"TSLA": -2}
    assert restarted._all_trades[-1].entry_order_id == str(ANCHOR)
    await restarted._reconcile_fills({})
    assert len(restarted._all_trades) == 2


async def test_save_snapshot_waits_for_owner_loop_daily_roll_to_finish(tmp_path):
    engine = engine_at(tmp_path)
    loop = asyncio.get_running_loop()
    engine._accounting_owner_loop = loop
    engine._symbol_daily_pnl = {"OLD": -7}
    engine._symbol_closed_today = {"OLD": 3}
    engine._symbol_banned = {"OLD"}
    @close_accounting.save_serialized
    def legacy_save(host):
        pass
    # Ordinary tick mutation is a synchronous owner-loop section. A worker's
    # publication callback cannot observe it halfway through this section.
    worker = loop.run_in_executor(None, legacy_save, engine)
    engine._symbol_daily_pnl.clear()
    engine._symbol_closed_today.clear()
    engine._symbol_banned.clear()
    engine._daily_loss_date = close_accounting.session_date(CLOSE)
    await worker
    state = close_accounting.read(engine.brain.brain_dir)
    assert state["daily"]["_symbol_daily_pnl"] == {}
    assert state["daily"]["_symbol_closed_today"] == {}
    assert state["daily"]["_symbol_banned"] == set()


async def test_position_closing_while_process_is_down_retains_identified_entry(database, tmp_path):
    engine = engine_at(tmp_path, database)
    track(engine)
    engine._positions_service.get_all_positions.return_value = {"TSLA": {"qty": 6, "avg_entry_price": 100}}
    # A real brain checkpoint while still open contains no pending close.
    assert engine.force_save_brain()["success"]
    await missing_partial(database)
    await complete_partial(database)
    later = CLOSE + timedelta(minutes=5)
    restarted = engine_at(tmp_path, database, now=later)
    await restarted.initialize()
    assert "TSLA" in restarted._entry_metadata
    assert "pending_close" not in restarted._entry_metadata["TSLA"]
    await restarted._reconcile_fills({})
    assert_consumers(restarted, 1, -2)
    assert restarted._all_trades[0].closed_at == later.isoformat()
    assert restarted._all_trades[0].entry_order_id == str(ANCHOR)
    assert not restarted._all_trades[0].is_reconciliation_artifact
