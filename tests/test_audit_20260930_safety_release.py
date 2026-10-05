"""Audit 2026-09-30 safety release: one file per finding group.

EXE-05 broker read failure is unknown (never flat); OPS-04 daily-loss baseline
survives a same-day restart; EXE-06 late-day thresholds follow early closes;
EXE-03 pending-entry age escalation; EXE-04 dead-lettered exit alert;
SEC-03 trade-capable routes need trader/admin; SEC-04 self-registration off
by default; CFG-01 runtime hash covers admission settings; TEL-01 blocked log
names its reason.
"""
from __future__ import annotations

import inspect
import json
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from fastapi import HTTPException

from backend.organism.replay_simulator import SimulatedBroker
from backend.services.positions_service import PositionReadError, PositionsService


# ── shared helpers ────────────────────────────────────────────────────────────
class _Client:
    """Minimal Alpaca TradingClient stand-in for PositionsService."""

    def __init__(self, result):
        self.result = result

    def get_all_positions(self):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _alpaca_position(symbol, qty, price=100.0):
    return SimpleNamespace(symbol=symbol, qty=str(qty), market_value=str(qty * price),
                           cost_basis=str(qty * price), unrealized_pl="0",
                           avg_entry_price=str(price))


class _FlakyBroker(SimulatedBroker):
    """SimulatedBroker with the production strict-read contract."""

    fail_positions = False

    async def get_all_positions_strict(self):
        if self.fail_positions:
            raise PositionReadError("simulated broker outage")
        return await self.get_all_positions()


def _engine(tmp_path, broker=None, universe=None):
    from tests.test_organism_engine_scenarios import _make_engine
    return _make_engine(broker or _FlakyBroker(initial_cash=100_000),
                        brain_dir=str(tmp_path / "brain"), universe=universe)


# ── EXE-05: unknown is not flat ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_strict_read_raises_and_legacy_read_stays_empty():
    failing = PositionsService(_Client(ConnectionError("down")))
    with pytest.raises(PositionReadError):
        await failing.get_all_positions_strict()
    assert await failing.get_all_positions() == {}
    with pytest.raises(PositionReadError):
        await PositionsService(None).get_all_positions_strict()
    ok = PositionsService(_Client([_alpaca_position("AAPL", 5)]))
    assert (await ok.get_all_positions_strict())["AAPL"]["qty"] == 5.0
    assert await PositionsService(_Client([])).get_all_positions_strict() == {}


@pytest.mark.asyncio
async def test_read_helper_separates_unknown_from_flat(tmp_path, caplog):
    engine = _engine(tmp_path)
    engine._positions_service = PositionsService(_Client([]))
    assert await engine._read_broker_positions() == {}
    engine._positions_service = PositionsService(_Client(ConnectionError("down")))
    assert await engine._read_broker_positions() is None
    # Services without the strict method keep their contract.
    legacy = SimpleNamespace(get_all_positions=AsyncMock(side_effect=RuntimeError("x")))
    engine._positions_service = legacy
    assert await engine._read_broker_positions() is None
    legacy.get_all_positions = AsyncMock(return_value={})
    assert await engine._read_broker_positions() == {}
    # One CRITICAL per episode of consecutive failed tick reads.
    engine._positions_service = PositionsService(_Client(ConnectionError("down")))
    with caplog.at_level(logging.WARNING):
        for _ in range(engine._POSITIONS_UNKNOWN_CRITICAL_TICKS + 3):
            assert await engine._read_broker_positions(track=True) is None
    critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical) == 1 and "BROKER POSITIONS UNKNOWN" in critical[0].getMessage()
    engine._positions_service = PositionsService(_Client([]))
    assert await engine._read_broker_positions(track=True) == {}
    assert engine._positions_unknown_streak == 0


@pytest.mark.asyncio
async def test_full_tick_blocks_entries_and_holds_sells_while_unknown(tmp_path):
    from backend.organism.adaptive_exits import ExitLevels

    broker = _FlakyBroker(initial_cash=100_000)
    engine = _engine(tmp_path, broker)
    await engine.initialize()
    for _ in range(engine._WARMUP_TICKS + 1):
        await engine.live_tick()
    broker.add_position("AAPL", qty=10, avg_entry_price=150.0)
    broker.set_price("AAPL", 143.0)  # -4.7%: stop breached, far from the 15% max-loss net
    engine._exit_levels["AAPL"] = ExitLevels(
        symbol="AAPL", direction=1.0, entry_price=150.0, stop_loss=145.0, take_profit=180.0,
        trailing_stop=145.0, atr_at_entry=5.0, regime_at_entry="unknown", highest_favorable=150.0)
    engine._entry_metadata["AAPL"] = {"entry_price": 150.0, "entry_tick": 0, "direction": 1.0,
                                      "predicted_return": 0.02, "confidence": 0.6}
    engine._last_positions = {"AAPL": {"symbol": "AAPL", "qty": 10.0, "side": "long",
                                       "avg_entry_price": 150.0, "current_price": 143.0}}
    filled_before, rejected_before = len(broker.filled_orders), len(broker.rejected_orders)

    broker.fail_positions = True
    sync_spy = AsyncMock(wraps=engine._sync_streaming_subscriptions)
    engine._sync_streaming_subscriptions = sync_spy
    await engine.live_tick()
    assert engine._last_entries_blocked_reason == "broker_positions_unknown"
    assert engine.status()["broker_positions"]["unknown"] is True
    # Nothing reached the broker: no entry, and the stop-loss sell was held.
    # (result.orders_submitted counts exit attempts, including held ones.)
    assert len(broker.filled_orders) == filled_before
    assert len(broker.rejected_orders) == rejected_before
    assert "AAPL" in engine._entry_metadata                # no close inferred
    assert (await broker.get_all_positions())["AAPL"]["qty"] == 10
    # No exit attempt ran from the stale snapshot, so no cooldown was armed.
    assert "AAPL" not in engine._pending_exit and "AAPL" not in engine._exit_cooldown
    # Held names from the last confirmed snapshot stayed in the subscription request.
    assert "AAPL" in sync_spy.await_args_list[-1].args[0]

    broker.fail_positions = False
    await engine.live_tick()
    assert engine.status()["broker_positions"]["unknown"] is False
    sells = [o for o in broker.filled_orders[filled_before:] if o.get("side") == "sell"]
    # The first answered tick exits: nothing armed during the outage delays it.
    assert sells and sells[0]["symbol"] == "AAPL"


@pytest.mark.asyncio
async def test_reconcile_never_infers_a_close_from_an_unknown_read(tmp_path):
    engine = _engine(tmp_path)
    engine.brain.brain_dir.mkdir(parents=True, exist_ok=True)
    engine._tick_count = 10                                   # past the grace window
    engine._positions_service = PositionsService(_Client(ConnectionError("down")))
    engine._entry_metadata["AAPL"] = {"entry_price": 100.0, "direction": 1.0, "entry_tick": 0}
    engine._last_positions = {"AAPL": {"qty": 5}}
    await engine._reconcile_fills({})
    assert "pending_close" not in engine._entry_metadata["AAPL"]
    assert engine._last_positions == {"AAPL": {"qty": 5}}
    # The same state on a CONFIRMED flat read does start a close (the test is not vacuous):
    # attribution is kept and the pending-close marker is created.
    engine._positions_service = PositionsService(_Client([]))
    await engine._reconcile_fills({})
    assert "AAPL" in engine._entry_metadata
    assert engine._entry_metadata["AAPL"].get("pending_close")


@pytest.mark.asyncio
async def test_sell_guard_rereads_and_holds_only_while_unknown(tmp_path):
    engine = _engine(tmp_path)
    engine._order_service = SimpleNamespace(submit_symbol_order=AsyncMock(return_value={"order_id": "x"}))
    engine._positions_service = PositionsService(_Client(ConnectionError("down")))
    engine._positions_unknown = True
    stale = {"AAPL": {"qty": 10.0, "side": "long"}}
    held = await engine._submit_exit_order("AAPL", 10, reason="stop", direction=1.0, broker_positions=stale)
    assert held == {"status": "blocked", "reason": "broker_positions_unknown"}
    engine._order_service.submit_symbol_order.assert_not_awaited()
    # The broker answers: the guard uses the fresh quantity, not the stale one.
    engine._positions_service = PositionsService(_Client([_alpaca_position("AAPL", 4)]))
    await engine._submit_exit_order("AAPL", 10, reason="stop", direction=1.0, broker_positions=stale)
    assert engine._order_service.submit_symbol_order.await_args.kwargs["qty"] == 4


# ── OPS-04: the day's loss baseline survives a restart ───────────────────────
def test_daily_loss_baseline_restores_only_for_the_same_session(tmp_path):
    engine = _engine(tmp_path)
    saved = {"daily_loss_session_date": "2026-09-30", "daily_starting_equity": 100_000.0,
             "daily_loss_halt": True}
    assert engine._restore_daily_loss_baseline(saved, "2026-09-30") is True
    assert (engine._daily_loss_date, engine._daily_starting_equity, engine._daily_loss_halt) == (
        "2026-09-30", 100_000.0, True)
    fresh = _engine(tmp_path)
    assert fresh._restore_daily_loss_baseline(saved, "2026-10-01") is False
    assert fresh._daily_loss_date == "" and fresh._daily_starting_equity == 0.0
    assert fresh._daily_loss_halt is True                       # carried over to the next roll
    assert fresh._restore_daily_loss_baseline({**saved, "daily_starting_equity": 0}, "2026-09-30") is False


def test_daily_loss_state_is_persisted_atomically_without_touching_other_keys(tmp_path):
    engine = _engine(tmp_path)
    engine.brain.brain_dir.mkdir(parents=True, exist_ok=True)
    path = engine.brain.brain_dir / "extra_counters.json"
    path.write_text(json.dumps({"exit_levels": {"AAPL": {}}, "tick_count": 7}))
    engine._daily_loss_date, engine._daily_starting_equity, engine._daily_loss_halt = "2026-09-30", 98_500.0, True
    engine._persist_daily_loss_state()
    data = json.loads(path.read_text())
    assert data["exit_levels"] == {"AAPL": {}} and data["tick_count"] == 7
    assert (data["daily_loss_session_date"], data["daily_starting_equity"], data["daily_loss_halt"]) == (
        "2026-09-30", 98_500.0, True)


def test_daily_loss_persist_failure_pages(tmp_path, monkeypatch, caplog):
    """PR #35 review: a failed immediate write is CRITICAL (the watchdog pages), never silent."""
    import backend.organism.brain_persistence as bp
    engine = _engine(tmp_path)
    engine.brain.brain_dir.mkdir(parents=True, exist_ok=True)
    engine._daily_loss_date, engine._daily_starting_equity, engine._daily_loss_halt = "2026-09-30", 98_500.0, True

    def _boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(bp, "_write_text_atomic", _boom)
    with caplog.at_level(logging.CRITICAL):
        engine._persist_daily_loss_state()                     # never raises into the tick
    assert any(r.levelno == logging.CRITICAL and "DAILY LOSS STATE NOT PERSISTED" in r.getMessage()
               for r in caplog.records)
    assert engine._daily_loss_halt is True                     # the in-memory halt stays in force


@pytest.mark.asyncio
async def test_confirmed_reads_refresh_the_unknown_fallback_snapshot(tmp_path):
    """PR #35 review: any confirmed read (not only reconciliation's) refreshes the fallback."""
    engine = _engine(tmp_path)
    engine._last_positions = {}
    engine._positions_service = PositionsService(_Client([_alpaca_position("AAPL", 4)]))
    opened, _ = await engine._entry_positions_recheck([], set())
    assert opened == {"AAPL"} and engine._last_positions["AAPL"]["qty"] == 4.0
    engine._positions_service = PositionsService(_Client(ConnectionError("down")))
    current, subscription = await engine._positions_for_tick()
    assert current == {} and "AAPL" in subscription            # held name stays subscribed
    assert engine._last_positions["AAPL"]["qty"] == 4.0          # unknown never overwrites it


def test_earlier_session_halt_is_carried_over_and_same_session_halt_reapplies_governance(tmp_path):
    engine = _engine(tmp_path)
    assert engine._restore_daily_loss_baseline(
        {"daily_loss_session_date": "2026-09-29", "daily_starting_equity": 90_000.0,
         "daily_loss_halt": True}, "2026-09-30") is False
    assert engine._daily_loss_halt is True                     # the first tick clears it
    assert engine._daily_loss_halt_session == "2026-09-29"
    assert engine._daily_loss_date == "" and engine._daily_starting_equity == 0.0
    same = _engine(tmp_path)
    assert not same.governance.is_trading_halted
    assert same._restore_daily_loss_baseline(
        {"daily_loss_session_date": "2026-09-30", "daily_starting_equity": 90_000.0,
         "daily_loss_halt": True}, "2026-09-30") is True
    assert same.governance.is_trading_halted                   # halt write outran governance save
    # The baseline's own key wins; a stale daily_session_date cannot vouch for it.
    stale = _engine(tmp_path)
    assert stale._restore_daily_loss_baseline(
        {"daily_session_date": "2026-09-30", "daily_loss_session_date": "2026-09-29",
         "daily_starting_equity": 90_000.0}, "2026-09-30") is False


@pytest.mark.asyncio
async def test_first_roll_clears_a_carried_halt_and_missing_baseline_is_retaken(tmp_path, monkeypatch):
    import backend.organism.live_engine as le
    monkeypatch.setattr(le, "MAX_DAILY_LOSS", 500.0)
    broker = _FlakyBroker(initial_cash=100_000)
    engine = _engine(tmp_path, broker)
    await engine.initialize()
    engine._tick_count = engine._WARMUP_TICKS + 1
    # Carried-over halt from an earlier session: the roll resumes trading.
    engine._daily_loss_halt = True
    engine.governance.halt_trading()
    engine._daily_loss_date = ""
    await engine.live_tick()
    assert not engine.governance.is_trading_halted and engine._daily_loss_halt is False
    # Same session date restored without a baseline (close-accounting checkpoint):
    # the breaker takes a baseline instead of measuring against zero.
    engine._daily_starting_equity = 0.0
    await engine.live_tick()
    assert engine._daily_starting_equity > 0


async def _halted_yesterday(tmp_path, broker):
    from backend.organism import close_accounting
    first = _engine(tmp_path, broker)
    await first.initialize()
    today = close_accounting.session_date(first._now_fn())
    yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
    first.governance.halt_trading()
    first._daily_loss_halt, first._daily_loss_halt_session = True, yesterday
    first._daily_loss_date, first._daily_starting_equity = yesterday, 100_000.0
    first._save_brain()
    return today


@pytest.mark.asyncio
async def test_carried_halt_survives_two_restarts_before_the_first_tick(tmp_path):
    broker = SimulatedBroker(initial_cash=100_000)
    await _halted_yesterday(tmp_path, broker)
    first = _engine(tmp_path, broker)
    await first.initialize()                                     # morning deploy
    assert first._daily_loss_halt is True
    await first.shutdown()                                       # second deploy, graceful
    second = _engine(tmp_path, broker)
    await second.initialize()
    assert second._daily_loss_halt is True                       # still carried
    for _ in range(second._WARMUP_TICKS + 2):
        await second.live_tick()
    assert not second.governance.is_trading_halted


@pytest.mark.asyncio
async def test_carried_halt_clears_after_a_crash_restart(tmp_path):
    broker = SimulatedBroker(initial_cash=100_000)
    today = await _halted_yesterday(tmp_path, broker)
    crashed = _engine(tmp_path, broker)
    await crashed.initialize()                                   # republishes today's checkpoint
    restarted = _engine(tmp_path, broker)                        # no shutdown, no save
    await restarted.initialize()
    assert restarted._daily_loss_date == today                   # date restored: no roll
    for _ in range(restarted._WARMUP_TICKS + 2):
        await restarted.live_tick()
    assert not restarted.governance.is_trading_halted
    assert restarted._daily_starting_equity > 0                  # baseline taken, not zero


def test_roll_write_does_not_relabel_other_session_keys(tmp_path):
    engine = _engine(tmp_path)
    engine.brain.brain_dir.mkdir(parents=True, exist_ok=True)
    path = engine.brain.brain_dir / "extra_counters.json"
    path.write_text(json.dumps({"daily_session_date": "2026-09-29", "symbol_banned": ["XOM"]}))
    engine._daily_loss_date, engine._daily_starting_equity = "2026-09-30", 100_000.0
    engine._persist_daily_loss_state()
    data = json.loads(path.read_text())
    assert data["daily_session_date"] == "2026-09-29"           # bans stay yesterday's
    assert data["daily_loss_session_date"] == "2026-09-30"


@pytest.mark.asyncio
async def test_overnight_flag_survives_an_unknown_read(tmp_path):
    engine = _engine(tmp_path)
    engine.brain.brain_dir.mkdir(parents=True, exist_ok=True)
    engine._positions_service = PositionsService(_Client(ConnectionError("down")))
    engine._last_positions = {"AAPL": {"symbol": "AAPL", "qty": 10.0, "side": "long"}}
    # The tick hands position management nothing while unknown; only the
    # subscription set keeps the last confirmed names.
    current, subscribed = await engine._positions_for_tick()
    assert current == {} and "AAPL" in subscribed and engine._positions_unknown is True
    assert engine._last_entries_blocked_reason == "broker_positions_unknown"
    # Even if a caller passes a stale snapshot, the forced exit keeps the flag.
    engine._order_service = SimpleNamespace(submit_symbol_order=AsyncMock(return_value={"order_id": "x"}))
    engine._now_fn = lambda: datetime(2026, 9, 30, 14, 0, tzinfo=UTC)          # 10:00 ET
    engine._record_unflattened_positions(["AAPL"], "2026-09-29", "2026-09-29T20:00:00+00:00")
    result = SimpleNamespace(trades_closed=0, orders_submitted=0, activity=[], errors=[])
    await engine._force_exit_overnight_stragglers(engine._last_positions, result, "2026-09-30T14:00:00+00:00")
    engine._order_service.submit_symbol_order.assert_not_awaited()
    assert engine._overnight_flag_path().is_file() and result.trades_closed == 0


@pytest.mark.asyncio
async def test_post_close_unknown_without_a_snapshot_is_critical_once(tmp_path, caplog):
    engine = _engine(tmp_path)
    engine._positions_service = PositionsService(_Client(ConnectionError("down")))
    engine._last_positions = {}
    engine._record_unflattened_positions = MagicMock()
    now_et = pd.Timestamp("2026-09-30 16:02", tz="America/New_York")
    with caplog.at_level(logging.CRITICAL):
        await engine._stage_post_close_escalation(now_et, "2026-09-30T20:02:00+00:00")
        await engine._stage_post_close_escalation(now_et, "2026-09-30T20:02:10+00:00")
    critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical) == 1 and "POST-CLOSE FLATNESS UNVERIFIED" in critical[0].getMessage()
    engine._record_unflattened_positions.assert_not_called()


def test_pending_entry_inside_the_fill_cooldown_never_pages(tmp_path, caplog, monkeypatch):
    monkeypatch.setenv("ORGANISM_TICK_INTERVAL_SECONDS", "60")   # slow ticks: cooldown is 30 min
    engine = _engine(tmp_path)
    assert engine._pending_entry_escalate_after() == 3600.0
    t0 = datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
    clock = {"now": t0}
    engine._now_fn = lambda: clock["now"]
    engine._tick_count = 100
    engine._pending_entry = {"AAPL": 100}                       # just submitted
    engine._pending_entry_order_ids = {"AAPL": "o-1"}
    engine._track_pending_entry_ages()
    clock["now"] = t0 + timedelta(minutes=45)                   # still inside 2x the cooldown
    with caplog.at_level(logging.CRITICAL):
        engine._track_pending_entry_ages()
    assert not [r for r in caplog.records if r.levelno == logging.CRITICAL]


# ── EXE-06: late-day thresholds follow the session's close ───────────────────
@pytest.mark.parametrize("stamp,phase", [
    ("2026-09-30 15:44", "open"), ("2026-09-30 15:45", "late_block"),
    ("2026-09-30 15:58", "flatten"), ("2026-09-30 16:00", "post_close"),
    ("2026-11-27 12:44", "open"), ("2026-11-27 12:45", "late_block"),
    ("2026-11-27 12:58", "flatten"), ("2026-11-27 13:00", "post_close"),
    ("2026-12-24 12:59", "flatten"), ("2026-12-24 15:45", "post_close"),
])
def test_eod_phase_follows_early_closes(stamp, phase):
    from backend.organism.live_engine import OrganismLiveEngine
    now_et = pd.Timestamp(stamp, tz="America/New_York").to_pydatetime()
    assert OrganismLiveEngine._eod_session_phase(now_et) == phase


# ── EXE-03: pending entries age by wall clock and escalate once ──────────────
def test_pending_entry_escalates_once_and_keeps_its_age_across_restart(tmp_path, caplog, monkeypatch):
    monkeypatch.setenv("ORGANISM_TICK_INTERVAL_SECONDS", "10")   # production interval
    engine = _engine(tmp_path)
    t0 = datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
    clock = {"now": t0}
    engine._now_fn = lambda: clock["now"]
    engine._pending_entry = {"AAPL": 5}
    engine._pending_entry_order_ids = {"AAPL": "o-1"}
    assert engine._track_pending_entry_ages()[0]["age_seconds"] == 0.0
    clock["now"] = t0 + timedelta(minutes=31)
    with caplog.at_level(logging.CRITICAL):
        engine._track_pending_entry_ages()
        engine._track_pending_entry_ages()
    critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical) == 1 and "PENDING ENTRY UNRESOLVED" in critical[0].getMessage()
    status = engine.status()["pending_entries"]
    assert status["count"] == 1 and status["stale"][0]["symbol"] == "AAPL"
    # Restart: the saved first-seen time survives for the same identity only.
    saved = dict(engine._pending_entry_since)
    restarted = _engine(tmp_path)
    restarted._now_fn = lambda: clock["now"]
    restarted._tick_count = 0
    restarted._pending_entry = {"AAPL": 0, "MSFT": 0}
    restarted._pending_entry_order_ids = {"AAPL": "o-1", "MSFT": "o-2"}
    restarted._restore_pending_entry_since({**saved, "MSFT": {"order_id": "old", "since": t0.isoformat()}})
    ages = {r["symbol"]: r["age_seconds"] for r in restarted._track_pending_entry_ages()}
    assert ages == {"AAPL": 31 * 60.0, "MSFT": 0.0}
    # Resolution removes the identity; nothing is retired by age.
    restarted._pending_entry.pop("AAPL"); restarted._pending_entry_order_ids.pop("AAPL")
    assert [r["symbol"] for r in restarted._track_pending_entry_ages()] == ["MSFT"]
    assert "AAPL" not in restarted._pending_entry_since


# ── EXE-04: dead-lettered exits page the operator ────────────────────────────
def test_dead_lettered_exit_and_ambiguous_submissions_raise_an_alert():
    from backend.infra.outbox_worker import dlq_exposure_alert
    exit_event = {"id": "e1", "payload": {"symbol": "AAPL", "side": "sell", "qty": 10,
                                          "client_key": "organism_exit_AAPL_x"}}
    alert = dlq_exposure_alert(exit_event, {"error": "timeout"})
    assert alert["message"].startswith("EXIT ORDER DEAD-LETTERED")
    assert alert["fields"]["symbol"] == "AAPL" and alert["fields"]["qty"] == 10
    nested = {"id": "e2", "payload": {"payload": {"symbol": "MSFT", "side": "buy"}}}
    assert dlq_exposure_alert(nested, {"error": "rejected"}) is None
    ambiguous = dlq_exposure_alert(nested, {"error": "ack lost", "submission_ambiguous": True})
    assert ambiguous["message"].startswith("ORDER SUBMISSION AMBIGUOUS")
    from backend.infra.outbox_worker import OutboxWorker
    assert "dlq_exposure_alert(event, error_result)" in inspect.getsource(OutboxWorker._move_to_dlq)


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_fails", [False, True])
async def test_dead_letter_alert_pages_only_after_the_commit(monkeypatch, commit_fails):
    """PR #35 review: a failed DLQ commit leaves the event for retry and must not page."""
    import backend.infra.outbox as outbox_mod
    import backend.infra.outbox_worker as worker_mod

    calls = []

    class _Repo:
        def __init__(self, session):
            pass

        async def mark_failed(self, **kwargs):
            calls.append("mark_failed")

    class _Session:
        async def commit(self):
            calls.append("commit")
            if commit_fails:
                raise RuntimeError("db down")

        async def rollback(self):
            calls.append("rollback")

        async def close(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    log = MagicMock()
    log.critical.side_effect = lambda *a, **k: calls.append("critical")
    monkeypatch.setattr(outbox_mod, "OutboxRepo", _Repo)
    monkeypatch.setattr(worker_mod, "logger", log)
    worker = worker_mod.OutboxWorker(lambda: _Session())
    event = {"id": "00000000-0000-0000-0000-000000000001", "retry_count": 5,
             "payload": {"symbol": "AAPL", "side": "sell", "qty": 10, "client_key": "organism_exit_AAPL_x"}}
    await worker._move_to_dlq(event, {"error": "timeout"})
    if commit_fails:
        assert "critical" not in calls and "rollback" in calls
    else:
        assert calls.index("commit") < calls.index("critical")


# ── SEC-03 / SEC-04: who may trade, who may register ─────────────────────────
def test_trade_capable_routes_require_trader_or_admin():
    from backend.api.routes import positions, signals
    from backend.infra.security import AuthenticatedUser, require_trader

    user = AuthenticatedUser(username="u", roles=["user"], token_id="t")
    trader = AuthenticatedUser(username="t", roles=["trader"], token_id="t")
    with pytest.raises(HTTPException) as denied:
        signals.require_trader_user(user)
    assert denied.value.status_code == 403
    assert signals.require_trader_user(trader) is trader
    act = inspect.signature(signals.act_on_signal).parameters["current_user"].default
    assert act.dependency is signals.require_trader_user
    for endpoint in (positions.close_position, positions.import_positions_endpoint):
        assert inspect.signature(endpoint).parameters["current_user"].default.dependency is require_trader


@pytest.mark.asyncio
async def test_self_registration_is_off_unless_enabled(monkeypatch):
    from backend.api.routes import auth
    monkeypatch.delenv("AUTH_ALLOW_SELF_REGISTRATION", raising=False)
    assert auth.self_registration_enabled() is False
    repo = MagicMock()
    request = SimpleNamespace(email="a@example.com", password="Str0ng!Passw0rd")
    with pytest.raises(HTTPException) as denied:
        await auth.register(request, repo)
    assert denied.value.status_code == 403
    assert not repo.method_calls
    monkeypatch.setenv("AUTH_ALLOW_SELF_REGISTRATION", "true")
    assert auth.self_registration_enabled() is True
    # Through the app, the gate is a route dependency resolved before the
    # user-store dependency, so a disabled deployment never opens the DB.
    route = next(r for r in auth.router.routes if getattr(r, "path", "").endswith("/register"))
    assert route.dependant.dependencies[0].call is auth.require_self_registration


# ── CFG-01 / TEL-01 ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("name,a,b", [
    ("SCANNER_ENABLED", "true", "false"), ("ORGANISM_STREAM_MAX_SYMBOLS", "28", "20"),
    ("ORGANISM_SCANNER_WINDOW_MAX", "8", "4"), ("ORGANISM_SCANNER_WINDOW_TTL_SCANS", "5", "3"),
    ("ORGANISM_STREAM_CRITICAL_SYMBOLS", "SPY,QQQ", "SPY"),
])
def test_runtime_hash_covers_admission_settings(monkeypatch, name, a, b):
    from backend.infra.runtime_identity import runtime_config_hash
    monkeypatch.setenv(name, a)
    first = runtime_config_hash()
    monkeypatch.setenv(name, b)
    assert runtime_config_hash() != first


def test_entries_blocked_log_names_the_reason():
    from backend.organism.live_engine import OrganismLiveEngine
    source = inspect.getsource(OrganismLiveEngine._live_tick_inner)
    assert '"Entries blocked (halt/drawdown/insufficient data) — "' not in source
    assert 'self._last_entries_blocked_reason or "unknown", exits_submitted' in source
