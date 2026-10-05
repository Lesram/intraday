"""Audit 2026-10-05 C06-01: closes outside the engine's exit orders.

A strategy position closed by a platform close route, the Alpaca dashboard or
a broker liquidation used to stay pending forever: no trade, the symbol
entry-gated across restarts. Isolated SQLite databases, the real close-route
handlers with a fake broker client, real fill ingestion and synthetic
identities only: no broker, network, saved brain state or production data.
"""
from __future__ import annotations

import copy
import csv
import itertools
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.infra.schemas import (
    AuditLog,
    Execution,
    Order,
    OutboxEvent,
    PositionLot,
    RealizedTrade,
)
from backend.integrations import alpaca_stream as stream
from backend.organism import close_accounting
from backend.organism import live_engine as live_engine_module
from backend.organism.continuous_learner import TradeRecord
from backend.organism.live_engine import OrganismLiveEngine
from backend.organism.live_engine_fills import (
    AMBIGUOUS_ORDER_REASON_PREFIX,
    EXTERNAL_CLOSE_APPROXIMATE_AFTER as BOUND,
    EXTERNAL_CLOSE_EXACT_SOURCE,
    EXTERNAL_CLOSE_EXIT_REASON,
    EXTERNAL_CLOSE_UNBOOKED_REASON,
    REPLACEMENT_PENDING_REASON,
    _closed_position_fills,
    _external_close,
    _FillLookupMixin,
)

_ids = itertools.count(1)
ESCALATE = timedelta(seconds=OrganismLiveEngine._UNRESOLVED_CLOSE_ESCALATE_SECONDS)


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ledger.db'}")
    async with engine.begin() as connection:
        for table in (Order.__table__, Execution.__table__, PositionLot.__table__,
                      RealizedTrade.__table__, AuditLog.__table__, OutboxEvent.__table__):
            await connection.run_sync(lambda sync, table=table: table.create(sync))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def order_row(symbol, side, qty, *, at, attributes=None, user="system", status="accepted",
              broker=True, client=None, filled=0, price=None):
    """One synthetic order row; ids always contain hex letters (SQLite affinity)."""
    n = next(_ids)
    return Order(
        id=uuid.UUID(f"e7c10{n:03x}-aaaa-4bbb-8ccc-{n:012x}"), user_id=user,
        client_idempotency_key=client or f"organism_{symbol}_{uuid.uuid4().hex[:12]}",
        symbol=symbol, side=side, qty=Decimal(str(qty)), filled_qty=Decimal(str(filled)),
        avg_fill_price=Decimal(str(price)) if price is not None else None,
        status=status, order_type="market", tif="day",
        submitted_at=at, created_at=at, updated_at=at,
        broker_order_id=str(uuid.uuid4()) if broker else None,
        attributes=attributes or {"source": "organism", "reason": "organism_entry"},
    )


async def store(db, rows):
    async with db() as session:
        session.add_all(rows)
        await session.commit()


async def ingest_fill(db, order_id, qty, price):
    """The broker's fill reaches the DB through the real ingestion path."""
    async with db() as session:
        current = await session.get(Order, order_id)
        await stream.apply_order_fill_snapshot(
            session, current, status="filled", cumulative_filled_qty=str(qty),
            avg_fill_price=str(price), broker_order_id=current.broker_order_id or str(uuid.uuid4()),
        )
        await session.commit()


async def filled_entry(db, t0, *, qty=6, price=100, symbol="TSLA"):
    entry = order_row(symbol, "buy", qty, at=t0 - timedelta(minutes=30))
    await store(db, [entry])
    await ingest_fill(db, entry.id, qty, price)
    return entry


class FakeAlpacaClient:
    """The close routes read the broker position before booking the order."""

    def __init__(self, *args, **kwargs):
        pass

    async def get_position(self, symbol):
        return {"symbol": symbol, "qty": "6", "side": "long", "avg_entry_price": "100"}


async def close_via_positions_route(db, monkeypatch, symbol="TSLA"):
    """POST /positions/{symbol}/close, the real handler (dashboard 'Close')."""
    from backend.api.routes.positions import close_position

    monkeypatch.setattr("backend.integrations.alpaca_broker.AlpacaBrokerClient", FakeAlpacaClient)
    async with db() as session:
        result = await close_position(
            symbol, current_user=SimpleNamespace(email="ops@example.com", roles=["trader"]),
            db=session, body=None)
        await session.commit()
    return uuid.UUID(result.order_id)


async def close_via_orders_route(db, monkeypatch, entry):
    """POST /orders/{id}/close-position, the real handler (order 'Close Position')."""
    from backend.api.routes.orders import close_position_from_order
    from backend.services import order_service

    monkeypatch.setattr("backend.integrations.alpaca_broker.AlpacaBrokerClient", FakeAlpacaClient)
    monkeypatch.setattr(order_service, "_circuit_breaker", order_service.CircuitBreaker())
    async with db() as session:
        result = await close_position_from_order(
            str(entry.id), db=session, user=SimpleNamespace(username="ops", sub="ops", roles=["admin"]))
    return uuid.UUID(result["close_order"]["order_id"])


class Clock:
    def __init__(self, now):
        self.now = now


def make_engine(tmp_path, db, clock):
    broker = MagicMock()
    broker.get_all_positions = AsyncMock(return_value={})  # the broker is flat
    engine = OrganismLiveEngine(
        data_client=MagicMock(), order_service=broker, positions_service=broker,
        brain_dir=str(tmp_path / "brain"), universe=["TSLA", "AMD"], sessionmaker=db,
    )
    engine._now_fn = lambda: clock.now
    engine._time_fn = lambda: clock.now.timestamp()
    engine._daily_loss_date = close_accounting.session_date(clock.now)
    engine._tick_count = 200
    engine._streaming_provider = None
    engine._save_brain = MagicMock()
    engine._bg_trainer.start = AsyncMock()
    engine._reconstruct_position_state = AsyncMock()
    # Legacy orphan lookups use PostgreSQL JSON SQL; external closes never need them.
    engine._lookup_exit_fill_from_db = AsyncMock(return_value=None)
    engine._lookup_entry_fill_from_db = AsyncMock(return_value=None)
    return engine


def track(engine, entry, symbol="TSLA"):
    engine._entry_metadata[symbol] = {
        "entry_order_id": str(entry.id), "entry_price": 100.0, "entry_tick": 10,
        "filled_shares": int(entry.qty), "direction": 1.0, "entry_source": "alpha",
        "strategy_id": "momentum", "entry_time": entry.submitted_at.timestamp(),
        "confidence": 0.6, "regime_at_entry": "trending_up",
    }


def bars(price):
    return {"TSLA": pd.DataFrame({"close": [price]})}


def consumers(engine):
    """Every learning/risk consumer a strategy outcome would move."""
    return copy.deepcopy({
        "learner_history": len(engine.learner.trade_history),
        "learner_total": engine.learner.state.total_trades,
        "learner_pnl": engine.learner.state.cumulative_pnl,
        "kelly": engine.kelly_sizer.regime_stats_to_dict(),
        "calibration": engine.signal_gen.calibration_to_dict(),
        "symbol_counts": engine.evolved_params.symbol_trade_counts,
        "runtime_counts": engine._symbol_trade_counts_runtime,
        "daily_pnl": engine._symbol_daily_pnl,
        "closed_today": engine._symbol_closed_today,
        "consecutive_losses": engine._symbol_consecutive_losses,
        "wins_today": engine._symbol_wins_today,
        "stop_loss_times": engine._symbol_stop_loss_times,
        "banned": engine._symbol_banned,
    })


def gate_reason(engine, symbol="TSLA"):
    return engine._passes_entry_gates(symbol, 1.0, {}, set(), set(),
                                      fitness_gate=0.45, min_trades_for_fitness=10)[1]


def logged(log, level, needle):
    return [c.args for c in getattr(log, level).call_args_list if c.args and needle in str(c.args[0])]


# ── the platform's own close routes: exact accounting ───────────────────────


@pytest.mark.parametrize("route", ["positions_route", "orders_route"])
async def test_ui_close_via_platform_route_is_accounted_exactly_and_releases_the_gate(
    db, tmp_path, monkeypatch, route,
):
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    if route == "positions_route":
        close_id = await close_via_positions_route(db, monkeypatch)
    else:
        close_id = await close_via_orders_route(db, monkeypatch, entry)
    await ingest_fill(db, close_id, 6, 97)
    clock = Clock(t0 + timedelta(minutes=1))
    engine = make_engine(tmp_path, db, clock)
    track(engine, entry)
    assert gate_reason(engine) == "entry_metadata"
    before = consumers(engine)

    await engine._reconcile_fills({})

    assert len(engine._all_trades) == 1
    trade = engine._all_trades[0]
    assert (trade.shares, trade.entry_price, trade.exit_price) == (6, 100.0, 97.0)
    assert trade.pnl == pytest.approx(-18.0)
    assert trade.price_source == EXTERNAL_CLOSE_EXACT_SOURCE == "external_close_db_fills"
    assert trade.exit_reason == EXTERNAL_CLOSE_EXIT_REASON == "external_close"
    assert trade.is_reconciliation_artifact is True
    assert (trade.entry_order_id, trade.entry_source) == (str(entry.id), "alpha")
    assert trade.closed_at == clock.now.isoformat()
    assert consumers(engine) == before
    assert "TSLA" not in engine._entry_metadata and "TSLA" not in engine._exit_levels
    assert engine._accounting_completed_entries[str(entry.id)] == trade.closed_at
    assert gate_reason(engine) != "entry_metadata"
    assert engine.status()["close_accounting"]["pending"] == {}
    durable = close_accounting.read(engine.brain.brain_dir)
    assert [t.price_source for t in durable["all_trades"]] == [EXTERNAL_CLOSE_EXACT_SOURCE]
    # Rows as production leaves them: no organism source on the close leg, booked
    # under the operator's owner, and the engine's own lot still open.
    async with db() as session:
        close = await session.get(Order, close_id)
        lots = list((await session.execute(select(PositionLot))).scalars())
    assert close.attributes["close_position"] is True and "source" not in close.attributes
    assert close.user_id != "system" and close.attributes["lot_accounting"]["status"] == "unmatched"
    assert [(lot.user_id, lot.remaining_qty) for lot in lots] == [("system", 6)]
    await engine._reconcile_fills({})
    assert len(engine._all_trades) == 1
    assert not engine._order_service.submit_order.called


async def test_engine_partial_exit_then_route_close_is_one_exact_artifact(db, tmp_path, monkeypatch):
    # The release oracle: buy 6 @ 100, sell 2 @ 101 (engine) and 4 @ 99 (route).
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    partial = order_row("TSLA", "sell", 2, at=t0 - timedelta(minutes=10),
                        attributes={"source": "organism", "reason": "partial_take_profit"},
                        client=f"organism_exit_TSLA_{uuid.uuid4().hex[:8]}")
    await store(db, [partial])
    await ingest_fill(db, partial.id, 2, 101)

    class FourLeft(FakeAlpacaClient):
        async def get_position(self, symbol):
            return {"symbol": symbol, "qty": "4", "side": "long", "avg_entry_price": "100"}

    from backend.api.routes.positions import close_position
    monkeypatch.setattr("backend.integrations.alpaca_broker.AlpacaBrokerClient", FourLeft)
    async with db() as session:
        result = await close_position("TSLA", current_user=SimpleNamespace(email="ops@example.com"),
                                      db=session, body=None)
        await session.commit()
    await ingest_fill(db, uuid.UUID(result.order_id), 4, 99)
    engine = make_engine(tmp_path, db, Clock(t0 + timedelta(minutes=1)))
    track(engine, entry)
    await engine._reconcile_fills({})
    trade = engine._all_trades[0]
    assert trade.pnl == pytest.approx(-2.0) and trade.shares == 6
    assert trade.exit_price == pytest.approx(99 + 2 / 3)
    assert trade.had_partial_exits is True and trade.price_source == EXTERNAL_CLOSE_EXACT_SOURCE
    assert trade.is_reconciliation_artifact and engine.learner.state.total_trades == 0


# ── no DB leg at all (Alpaca dashboard or app, broker liquidation) ──────────


async def test_close_with_no_db_row_becomes_a_labelled_approximate_artifact_after_the_bound(
    db, tmp_path, monkeypatch,
):
    log = MagicMock()
    monkeypatch.setattr(live_engine_module, "logger", log)
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    observed = t0 + timedelta(minutes=1)
    clock = Clock(observed)
    engine = make_engine(tmp_path, db, clock)
    track(engine, entry)

    await engine._reconcile_fills(bars(96.0))  # first observation keeps the nearest mark
    pending = engine._entry_metadata["TSLA"]["pending_close"]
    assert pending["observed_bar_close"] == 96.0
    for minutes in (0, 7, 14):
        clock.now = observed + timedelta(minutes=minutes, seconds=59)
        await engine._reconcile_fills(bars(99.0))
        assert engine._all_trades == [] and "TSLA" in engine._entry_metadata
        assert gate_reason(engine) == "entry_metadata"
        assert engine._unresolved_close_status()["TSLA"]["reason"] == EXTERNAL_CLOSE_UNBOOKED_REASON
    unresolved = logged(log, "warning", "Close accounting unresolved")
    assert [args[1:3] for args in unresolved] == [("TSLA", EXTERNAL_CLOSE_UNBOOKED_REASON)]

    clock.now = observed + BOUND
    before = consumers(engine)
    await engine._reconcile_fills(bars(99.0))

    assert len(engine._all_trades) == 1
    trade = engine._all_trades[0]
    assert trade.price_source == "external_close_approximate_observed_bar_close"
    assert (trade.shares, trade.entry_price, trade.exit_price) == (6, 100.0, 96.0)
    assert trade.pnl == pytest.approx(-24.0)
    assert trade.is_reconciliation_artifact is True and trade.exit_reason == "external_close"
    assert trade.closed_at == observed.isoformat()  # the original observation, not the bound
    assert trade.had_partial_exits is False
    assert consumers(engine) == before
    assert "TSLA" not in engine._entry_metadata and gate_reason(engine) != "entry_metadata"
    assert engine._accounting_completed_entries[str(entry.id)] == observed.isoformat()
    assert len(logged(log, "warning", "External close of %s recorded")) == 1
    assert not log.critical.called
    assert not engine._order_service.submit_order.called


async def test_liquidated_remainder_after_an_engine_partial_exit_keeps_the_exact_leg(db, tmp_path):
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    partial = order_row("TSLA", "sell", 2, at=t0 - timedelta(minutes=10),
                        attributes={"source": "organism", "reason": "partial_take_profit"},
                        client=f"organism_exit_TSLA_{uuid.uuid4().hex[:8]}")
    await store(db, [partial])
    await ingest_fill(db, partial.id, 2, 101)
    clock = Clock(t0 + timedelta(minutes=1))
    engine = make_engine(tmp_path, db, clock)
    track(engine, entry)
    await engine._reconcile_fills(bars(95.0))
    clock.now += BOUND
    await engine._reconcile_fills({})
    trade = engine._all_trades[0]
    # 2 @ 101 from the DB, the unbooked 4 at the observed mark 95.
    assert trade.exit_price == pytest.approx((2 * 101 + 4 * 95) / 6)
    assert trade.pnl == pytest.approx(2 * 101 + 4 * 95 - 600)
    assert trade.had_partial_exits is True
    assert trade.price_source == "external_close_approximate_observed_bar_close"


@pytest.mark.parametrize("available,source,price", [
    ("observed_bar", "observed_bar_close", 96.0),
    ("current_bar", "bar_close", 98.0),
    ("quote_both", "quote_mid", 97.5),
    ("quote_bid", "quote_bid", 97.0),
    ("quote_ask", "quote_ask", 98.0),
])
async def test_unbooked_mark_ladder_names_its_rung(db, tmp_path, available, source, price):
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    clock = Clock(t0 + timedelta(minutes=1))
    engine = make_engine(tmp_path, db, clock)
    track(engine, entry)
    quote = {"quote_both": {"bid": 97.0, "ask": 98.0}, "quote_bid": {"bid": 97.0, "ask": 0},
             "quote_ask": {"bid": None, "ask": 98.0}}.get(available)
    if quote is not None:
        engine._streaming_provider = SimpleNamespace(get_latest_quote=MagicMock(return_value=quote))
    await engine._reconcile_fills(bars(96.0) if available == "observed_bar" else {})
    clock.now += BOUND
    await engine._reconcile_fills(bars(98.0) if available == "current_bar" else {})
    trade = engine._all_trades[0]
    assert trade.price_source == f"external_close_approximate_{source}"
    assert trade.exit_price == pytest.approx(price)
    assert trade.pnl == pytest.approx((price - 100) * 6)


async def test_unbooked_close_without_any_mark_stays_pending_until_one_exists(db, tmp_path, monkeypatch):
    log = MagicMock()
    monkeypatch.setattr(live_engine_module, "logger", log)
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    clock = Clock(t0 + timedelta(minutes=1))
    engine = make_engine(tmp_path, db, clock)
    track(engine, entry)
    engine._streaming_provider = SimpleNamespace(get_latest_quote=MagicMock(side_effect=RuntimeError("feed")))
    await engine._reconcile_fills({})
    clock.now += BOUND
    await engine._reconcile_fills({})
    assert engine._all_trades == [] and "TSLA" in engine._entry_metadata
    assert engine._unresolved_close_status()["TSLA"]["reason"] == "no_exit_price"
    await engine._reconcile_fills(bars(101.0))
    trade = engine._all_trades[0]
    assert trade.price_source == "external_close_approximate_bar_close"
    assert trade.pnl == pytest.approx(6.0)


# ── nothing reaches a learning consumer ─────────────────────────────────────


async def test_artifacts_never_reach_learner_kelly_calibration_bans_evolution_or_edge_monitor(
    db, tmp_path, monkeypatch,
):
    from backend.api.routes.strategy_health import _strategy_rows
    from backend.organism import research_policy
    from backend.organism.edge_monitor import compute_edge_metrics

    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    clock = Clock(t0 + timedelta(minutes=1))
    engine = make_engine(tmp_path, db, clock)
    track(engine, entry)
    engine._last_exit_reason["TSLA"] = "stop_loss"
    engine._peak_equity = 100_000.0
    before = consumers(engine)
    # A -126 loss: as a strategy stop-loss it would ban the symbol (threshold -100)
    # and feed every consumer. As an artifact it must move none of them.
    await engine._reconcile_fills(bars(79.0))
    clock.now += BOUND
    await engine._reconcile_fills(bars(79.0))
    (artifact,) = engine._all_trades
    assert artifact.pnl == pytest.approx(-126.0) and artifact.is_reconciliation_artifact
    assert consumers(engine) == before
    assert "TSLA" not in engine._symbol_banned and not engine._symbol_stop_loss_times

    # Evolution (synchronous route): only strategy trades are offered.
    strategy = [TradeRecord("AMD", 1, 10, 11, 0, 1, 1, 1, "trailing_stop", 0, 0.1, 0.5)
                for _ in range(300)]
    engine._all_trades = strategy + [artifact]
    monkeypatch.setattr(research_policy, "RESEARCH_POLICY_LOCKED", False)
    monkeypatch.setattr(live_engine_module, "apply_evolved_params", MagicMock())
    engine.learner.retrain = MagicMock(return_value=(False, None))
    engine.learner.compute_attribution = MagicMock()
    engine.signal_gen.update_calibration_map = MagicMock()
    engine.signal_gen._get_feature_importance = MagicMock(return_value={})
    engine.evolution_engine.evolve = MagicMock(return_value=engine.evolved_params)
    engine._retrain_and_evolve({}, "chop")
    offered = engine.evolution_engine.evolve.call_args.kwargs["trades"]
    assert len(offered) == 200 and artifact not in offered
    assert not any(t.is_reconciliation_artifact for t in offered)

    # Edge monitor and strategy health read the persisted ledger.
    engine._all_trades = [artifact, strategy[0]]
    assert engine.force_save_brain()["success"]
    with open(engine.brain.brain_dir / "trade_history.csv", newline="") as stream_:
        rows = list(csv.DictReader(stream_))
    assert [row["is_reconciliation_artifact"] for row in rows] == ["True", "False"]
    assert compute_edge_metrics(rows)["full_sample"]["n"] == 1
    assert [row["symbol"] for row in _strategy_rows(rows)] == ["AMD"]


# ── genuinely ambiguous closes wait; the page fires once ────────────────────


@pytest.mark.parametrize("ambiguity", [
    "close_fill_not_ingested", "unattributed_order", "order_after_the_close",
    "replaced_order", "engine_exit_not_ingested",
])
async def test_ambiguous_close_waits_with_one_warning_and_pages_once(db, tmp_path, monkeypatch, ambiguity):
    log = MagicMock()
    monkeypatch.setattr(live_engine_module, "logger", log)
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    observed = t0 + timedelta(minutes=1)
    expected = "exact_fills_unavailable"
    if ambiguity == "close_fill_not_ingested":
        # The route booked the close; its fill has not reached the DB yet.
        blocker = await close_via_positions_route(db, monkeypatch)
        expected = f"{AMBIGUOUS_ORDER_REASON_PREFIX}{blocker}"
    elif ambiguity == "unattributed_order":
        manual = order_row("TSLA", "sell", 6, at=t0 - timedelta(minutes=5), user="ops@example.com",
                           attributes={"reason": "manual"})
        await store(db, [manual])
        await ingest_fill(db, manual.id, 6, 97)
    elif ambiguity == "order_after_the_close":
        late = order_row("TSLA", "sell", 6, at=observed + timedelta(seconds=30),
                         attributes={"source": "organism", "reason": "stop_loss"},
                         client=f"organism_exit_TSLA_{uuid.uuid4().hex[:8]}")
        await store(db, [late])
        await ingest_fill(db, late.id, 6, 97)
    elif ambiguity == "replaced_order":
        replaced = order_row("TSLA", "sell", 6, at=t0 - timedelta(minutes=5), status="replaced",
                             attributes={"source": "organism", "reason": "stop_loss"},
                             client=f"organism_exit_TSLA_{uuid.uuid4().hex[:8]}")
        await store(db, [replaced])
        expected = REPLACEMENT_PENDING_REASON
    else:
        exit_ = order_row("TSLA", "sell", 6, at=t0 - timedelta(minutes=5),
                          attributes={"source": "organism", "reason": "stop_loss"},
                          client=f"organism_exit_TSLA_{uuid.uuid4().hex[:8]}")
        await store(db, [exit_])
        expected = f"{AMBIGUOUS_ORDER_REASON_PREFIX}{exit_.id}"
    clock = Clock(observed)
    engine = make_engine(tmp_path, db, clock)
    track(engine, entry)
    for offset in (timedelta(0), timedelta(minutes=14), BOUND, ESCALATE - timedelta(seconds=1)):
        clock.now = observed + offset
        await engine._reconcile_fills(bars(96.0))
        assert engine._all_trades == [] and "TSLA" in engine._entry_metadata
        assert engine._unresolved_close_status()["TSLA"]["reason"] == expected
        assert not logged(log, "critical", "CLOSE ACCOUNTING UNRESOLVED")
    assert [args[1:3] for args in logged(log, "warning", "Close accounting unresolved")] == [("TSLA", expected)]
    for offset in (ESCALATE, ESCALATE + timedelta(minutes=15)):
        clock.now = observed + offset
        await engine._reconcile_fills(bars(96.0))
    pages = logged(log, "critical", "CLOSE ACCOUNTING UNRESOLVED")
    assert len(pages) == 1 and pages[0][2:5] == ("TSLA", expected, observed.isoformat())
    assert engine._all_trades == [] and gate_reason(engine) == "entry_metadata"
    assert not engine._order_service.submit_order.called


async def test_escalation_is_once_per_episode_and_a_new_episode_can_page_again(tmp_path, monkeypatch):
    # No database at all (the R9 shape): nothing can classify the close.
    log = MagicMock()
    monkeypatch.setattr(live_engine_module, "logger", log)
    observed = datetime(2026, 10, 6, 15, 0, tzinfo=UTC)
    clock = Clock(observed)
    engine = make_engine(tmp_path, None, clock)
    entry = SimpleNamespace(id=uuid.UUID(int=7), qty=6, submitted_at=observed - timedelta(hours=1))
    track(engine, entry)
    for minutes in range(0, 120, 10):
        clock.now = observed + timedelta(minutes=minutes)
        await engine._reconcile_fills({})
    assert len(logged(log, "critical", "CLOSE ACCOUNTING UNRESOLVED")) == 1
    assert len(logged(log, "warning", "Close accounting unresolved")) == 1
    # The position reappears (pending cleared) and closes again: a new episode.
    engine._positions_service.get_all_positions.return_value = {"TSLA": {"qty": 6, "avg_entry_price": 100}}
    await engine._reconcile_fills({})
    engine._positions_service.get_all_positions.return_value = {}
    second = clock.now
    for minutes in range(0, 50, 10):
        clock.now = second + timedelta(minutes=minutes)
        await engine._reconcile_fills({})
    pages = logged(log, "critical", "CLOSE ACCOUNTING UNRESOLVED")
    assert len(pages) == 2 and pages[1][4] == second.isoformat()


# ── restart preserves the outcome ───────────────────────────────────────────


@pytest.mark.parametrize("close", ["positions_route", "no_db_row"])
async def test_restart_preserves_the_recorded_artifact_and_the_released_gate(db, tmp_path, monkeypatch, close):
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    if close == "positions_route":
        await ingest_fill(db, await close_via_positions_route(db, monkeypatch), 6, 97)
    clock = Clock(t0 + timedelta(minutes=1))
    first = make_engine(tmp_path, db, clock)
    track(first, entry)
    await first._reconcile_fills(bars(96.0))
    if close == "no_db_row":
        clock.now += BOUND
        await first._reconcile_fills({})
    recorded = first._all_trades[0]
    clock.now += timedelta(hours=1)
    restarted = make_engine(tmp_path, db, clock)
    await restarted.initialize()
    assert [t.entry_order_id for t in restarted._all_trades] == [str(entry.id)]
    assert restarted._all_trades[0].price_source == recorded.price_source
    assert restarted._all_trades[0].is_reconciliation_artifact is True
    assert restarted._accounting_completed_entries[str(entry.id)] == recorded.closed_at
    assert "TSLA" not in restarted._entry_metadata
    assert restarted.learner.state.total_trades == 0
    await restarted._reconcile_fills({})
    assert len(restarted._all_trades) == 1 and gate_reason(restarted) != "entry_metadata"


async def test_failed_artifact_commit_restores_the_pending_close_and_records_once(db, tmp_path, monkeypatch):
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    await ingest_fill(db, await close_via_positions_route(db, monkeypatch), 6, 97)
    clock = Clock(t0 + timedelta(minutes=1))
    engine = make_engine(tmp_path, db, clock)
    track(engine, entry)
    # First pass persists the pending close; then the artifact commit fails.
    monkeypatch.setattr(engine, "_lookup_external_close_from_db", AsyncMock(return_value=None))
    await engine._reconcile_fills({})
    checkpoint = engine.brain.brain_dir / close_accounting.CHECKPOINT_FILE
    before_bytes, before = checkpoint.read_bytes(), consumers(engine)
    monkeypatch.undo()
    with monkeypatch.context() as patch:
        patch.setattr(close_accounting.os, "replace", MagicMock(side_effect=OSError("disk full")))
        with pytest.raises(OSError, match="disk full"):
            await engine._reconcile_fills({})
    assert engine._all_trades == [] and consumers(engine) == before
    assert engine._entry_metadata["TSLA"]["pending_close"]["observed_at"] == clock.now.isoformat()
    assert str(entry.id) not in engine._accounting_completed_entries
    assert checkpoint.read_bytes() == before_bytes
    restarted = make_engine(tmp_path, db, clock)
    await restarted.initialize()
    await restarted._reconcile_fills({})
    await restarted._reconcile_fills({})
    assert [t.price_source for t in restarted._all_trades] == [EXTERNAL_CLOSE_EXACT_SOURCE]
    assert "TSLA" not in restarted._entry_metadata


async def test_restart_during_the_wait_keeps_the_original_observation_and_mark(db, tmp_path):
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    observed = t0 + timedelta(minutes=1)
    clock = Clock(observed)
    first = make_engine(tmp_path, db, clock)
    track(first, entry)
    await first._reconcile_fills(bars(96.0))
    clock.now = observed + timedelta(minutes=10)
    restarted = make_engine(tmp_path, db, clock)
    await restarted.initialize()
    assert restarted._entry_metadata["TSLA"]["pending_close"]["observed_at"] == observed.isoformat()
    await restarted._reconcile_fills(bars(90.0))
    assert restarted._all_trades == []  # the bound runs from the observation, not the restart
    clock.now = observed + BOUND
    await restarted._reconcile_fills(bars(90.0))
    trade = restarted._all_trades[0]
    assert trade.closed_at == observed.isoformat() and trade.exit_price == 96.0
    assert trade.price_source == "external_close_approximate_observed_bar_close"


# ── the still-pending entry identity (operator_cancellation) ────────────────


def paper_broker(entry, *, positions=()):
    snapshot = {"id": entry.broker_order_id, "client_order_id": entry.client_idempotency_key,
                "symbol": entry.symbol, "side": entry.side, "qty": str(entry.qty),
                "status": "filled", "filled_qty": str(entry.qty), "filled_avg_price": "100"}
    return SimpleNamespace(is_paper=True, base_url="https://paper-api.alpaca.markets",
                           get_order=AsyncMock(return_value=snapshot), cancel_order=AsyncMock(),
                           get_positions=AsyncMock(return_value=list(positions)))


@pytest.mark.parametrize("close", ["positions_route", "orders_route", "no_db_row"])
async def test_pending_entry_identity_is_released_by_the_external_close_artifact(
    db, tmp_path, monkeypatch, close,
):
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    if close == "positions_route":
        await ingest_fill(db, await close_via_positions_route(db, monkeypatch), 6, 97)
    elif close == "orders_route":
        await ingest_fill(db, await close_via_orders_route(db, monkeypatch, entry), 6, 97)
    clock = Clock(t0 + timedelta(minutes=1))
    engine = make_engine(tmp_path, db, clock)
    track(engine, entry)
    engine._pending_entry = {"TSLA": engine._tick_count - engine._PENDING_ENTRY_TICKS}
    engine._pending_entry_order_ids = {"TSLA": str(entry.id)}
    monkeypatch.setattr("backend.integrations.alpaca_broker.get_alpaca_broker_client",
                        lambda: paper_broker(entry))
    # Before the close is accounted, nothing proves the fill: the identity stays.
    await engine._reconcile_pending_entry_orders()
    assert engine._pending_entry_order_ids == {"TSLA": str(entry.id)}
    await engine._reconcile_fills(bars(96.0))
    if close == "no_db_row":
        clock.now += BOUND
        await engine._reconcile_fills({})
    assert engine._all_trades[0].exit_reason == EXTERNAL_CLOSE_EXIT_REASON
    await engine._reconcile_pending_entry_orders()
    assert not engine._pending_entry_order_ids and "TSLA" not in engine._pending_entry
    assert engine._last_pending_entry_resolution["orders"][0]["resolution"] == "accounted_fill"
    # The proof is the artifact; the engine's own lot is still open in the ledger.
    async with db() as session:
        lots = list((await session.execute(select(PositionLot))).scalars())
    assert [(lot.user_id, lot.remaining_qty) for lot in lots] == [("system", 6)]


@pytest.mark.parametrize("trade_kind", [
    "orphan_artifact", "stale_adjustment_artifact", "strategy_trade_with_open_lot",
    "external_artifact_wrong_shares", "external_artifact_wrong_entry_cost",
    "external_artifact_other_identity",
])
async def test_flat_entry_release_still_refuses_unproven_records(db, tmp_path, monkeypatch, trade_kind):
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    engine = make_engine(tmp_path, db, Clock(t0 + timedelta(minutes=1)))
    engine._pending_entry = {"TSLA": engine._tick_count - engine._PENDING_ENTRY_TICKS}
    engine._pending_entry_order_ids = {"TSLA": str(entry.id)}
    closed_at = (t0 + timedelta(minutes=1)).isoformat()
    engine._accounting_completed_entries = {str(entry.id): closed_at}
    fields = dict(entry_order_id=str(entry.id), closed_at=closed_at, shares=6, entry_price=100.0,
                  is_reconciliation_artifact=True, exit_reason=EXTERNAL_CLOSE_EXIT_REASON)
    fields.update({
        "orphan_artifact": {"exit_reason": "stop_loss"},
        "stale_adjustment_artifact": {"exit_reason": "reconciliation_adjustment"},
        "strategy_trade_with_open_lot": {"is_reconciliation_artifact": False, "exit_reason": "stop_loss"},
        "external_artifact_wrong_shares": {"shares": 5},
        "external_artifact_wrong_entry_cost": {"entry_price": 101.0},
        "external_artifact_other_identity": {"entry_order_id": str(uuid.uuid4())},
    }[trade_kind])
    engine._all_trades = [SimpleNamespace(**fields)]
    monkeypatch.setattr("backend.integrations.alpaca_broker.get_alpaca_broker_client",
                        lambda: paper_broker(entry))
    await engine._reconcile_pending_entry_orders()
    assert engine._pending_entry_order_ids == {"TSLA": str(entry.id)}
    # Control: the same record as an external-close artifact releases it.
    engine._all_trades = [SimpleNamespace(**{**fields, **dict(
        entry_order_id=str(entry.id), shares=6, entry_price=100.0,
        is_reconciliation_artifact=True, exit_reason=EXTERNAL_CLOSE_EXIT_REASON)})]
    await engine._reconcile_pending_entry_orders()
    assert not engine._pending_entry_order_ids


# ── classification (pure) ───────────────────────────────────────────────────

ENTRY_ID = uuid.UUID("e7c1ffff-aaaa-4bbb-8ccc-000000000001")
START = datetime(2026, 10, 6, 14, 5, tzinfo=UTC)
CLOSED = START + timedelta(hours=1)
ROUTE = {"close_position": True, "position_type": "long", "partial_close": False}
ORDERS_ROUTE = {"close_position": True, "original_order_id": str(ENTRY_ID), "close_type": "manual"}


def leg(i, side, qty, price, *, attributes=None, **overrides):
    row = {"id": ENTRY_ID if i == 1 else uuid.UUID(f"e7c1ffff-aaaa-4bbb-8ccc-{i:012x}"),
           "symbol": "TSLA", "side": side, "qty": Decimal(str(qty)), "filled_qty": Decimal(str(qty)),
           "avg_fill_price": Decimal(str(price)), "status": "filled",
           "submitted_at": START + timedelta(minutes=i), "broker_order_id": f"broker-{i}",
           "attributes": attributes or {"source": "organism"}}
    row.update(overrides)
    return row


def classify(rows, direction=1):
    return _external_close(rows, entry_order_id=ENTRY_ID, symbol="TSLA",
                           direction=direction, closed_at=CLOSED)


def test_close_route_legs_complete_the_lifetime_exactly():
    for attributes in (ROUTE, ORDERS_ROUTE):
        result = classify([leg(1, "buy", 6, 100), leg(2, "sell", 2, 101),
                           leg(3, "sell", 4, 99, attributes=attributes)])
        assert result is not None and result.unbooked_qty == 0 and result.close_route_orders == 1
        exact = result.fills()
        assert (exact.shares, exact.entry_price, exact.pnl) == (6, 100.0, pytest.approx(-2.0))
        assert exact.had_partial_exits and exact.price_source == EXTERNAL_CLOSE_EXACT_SOURCE
        assert not result.waiting(CLOSED, CLOSED)
    # Short positions close with a buy-to-cover from the positions route.
    short = classify([leg(1, "sell", 2, 100), leg(2, "buy", 2, 97, attributes=ROUTE)], direction=-1)
    assert short.fills().pnl == pytest.approx(6.0)
    # Strategy accounting never accepts a close-route leg.
    assert _closed_position_fills([leg(1, "buy", 6, 100), leg(2, "sell", 6, 97, attributes=ROUTE)],
                                  entry_order_id=ENTRY_ID, symbol="TSLA", direction=1,
                                  closed_at=CLOSED) is None


def test_unbooked_quantity_is_priced_only_with_a_labelled_mark_after_the_bound():
    result = classify([leg(1, "buy", 6, 100), leg(2, "sell", 2, 101)])
    assert result.unbooked_qty == 4 and result.close_route_orders == 0
    assert result.waiting(CLOSED, CLOSED + BOUND - timedelta(seconds=1))
    assert not result.waiting(CLOSED, CLOSED + BOUND)
    # Naive timestamps (SQLite fixtures, legacy strings) are UTC.
    assert not result.waiting(CLOSED.replace(tzinfo=None), CLOSED + BOUND)
    priced = result.fills(95.0, "bar_close")
    assert priced.pnl == pytest.approx(2 * 101 + 4 * 95 - 600)
    assert priced.price_source == "external_close_approximate_bar_close" and priced.had_partial_exits
    for mark, source in ((None, "bar_close"), (0, "bar_close"), (-1, "bar_close"),
                         (float("nan"), "bar_close"), (float("inf"), "bar_close"), (95.0, "")):
        assert result.fills(mark, source) is None
    assert classify([leg(1, "buy", 6, 100)]).unbooked_qty == 6


@pytest.mark.parametrize("rows", [
    pytest.param([leg(1, "buy", 6, 100), leg(2, "buy", 6, 100, attributes=ROUTE)], id="close_route_entry_side"),
    pytest.param([leg(1, "buy", 6, 100), leg(2, "sell", 6, 97, attributes={"reason": "manual"})],
                 id="unattributed_leg"),
    pytest.param([leg(1, "buy", 6, 100), leg(2, "sell", 6, 97, attributes={"close_position": "true"})],
                 id="close_flag_not_boolean"),
    pytest.param([leg(1, "buy", 6, 100), leg(2, "sell", 0, 0, attributes=ROUTE, status="accepted",
                                             filled_qty=Decimal(0))], id="close_route_still_working"),
    pytest.param([leg(1, "buy", 6, 100), leg(2, "sell", 6, 97, attributes=ROUTE, status="replaced")],
                 id="replaced_close_route_leg"),
    pytest.param([leg(1, "buy", 6, 100), leg(2, "sell", 7, 97, attributes=ROUTE)], id="over_close"),
    pytest.param([leg(1, "buy", 6, 100, status="partially_filled")], id="entry_still_working"),
    pytest.param([leg(1, "buy", 6, 100), leg(2, "sell", 6, 97)], id="engine_only_lifetime"),
    pytest.param([leg(1, "buy", 1.5, 100)], id="fractional_position"),
    pytest.param([leg(1, "buy", 6, 100), leg(2, "sell", 6, 97, attributes=ROUTE, broker_order_id=None)],
                 id="close_leg_without_broker_id"),
    pytest.param([leg(1, "buy", 6, 100), leg(2, "sell", 6, 97, attributes=ROUTE, symbol="AMD")],
                 id="other_symbol"),
    pytest.param([leg(2, "buy", 6, 100), leg(3, "sell", 6, 97, attributes=ROUTE)], id="no_anchor"),
    pytest.param([leg(1, "buy", 0, 0, status="canceled", filled_qty=Decimal(0))], id="unfilled_entry"),
    pytest.param([leg(1, "buy", 6, 100), leg(2, "sell", 6, 97, submitted_at=CLOSED + timedelta(seconds=1))],
                 id="unbooked_with_a_later_order"),
])
def test_ambiguous_lifetimes_are_refused(rows):
    assert classify(rows) is None


def test_an_exact_close_ignores_orders_after_the_observed_close():
    rows = [leg(1, "buy", 6, 100), leg(2, "sell", 6, 97, attributes=ROUTE),
            leg(3, "buy", 6, 99, attributes={"reason": "manual"}, submitted_at=CLOSED + timedelta(minutes=5))]
    assert classify(rows).unbooked_qty == 0  # same window as exact strategy accounting


async def test_database_lookup_applies_holds_and_fails_closed(db):
    host = _FillLookupMixin()
    host._sessionmaker = db
    t0 = datetime.now(UTC)
    entry = await filled_entry(db, t0)
    meta = {"entry_order_id": str(entry.id), "direction": 1.0, "entry_source": "alpha",
            "pending_close": {"observed_at": (t0 + timedelta(minutes=1)).isoformat()}}
    closed_at = t0 + timedelta(minutes=1)
    unbooked = await host._lookup_external_close_from_db("TSLA", meta, closed_at=closed_at)
    assert unbooked is not None and unbooked.unbooked_qty == 6
    # A same-session working order from before the entry can still change it.
    working = order_row("TSLA", "sell", 6, at=t0 - timedelta(hours=1))
    await store(db, [working])
    assert await host._lookup_external_close_from_db("TSLA", meta, closed_at=closed_at) is None
    assert meta["pending_close"]["accounting_hold_reason"] == f"{AMBIGUOUS_ORDER_REASON_PREFIX}{working.id}"
    for bad in ({}, {"entry_order_id": "invalid"},
                {"entry_order_id": str(entry.id), "entry_source": "reconciliation_orphan"}):
        assert await host._lookup_external_close_from_db("TSLA", bad, closed_at=closed_at) is None
    failing = _FillLookupMixin()
    failing._sessionmaker = MagicMock(side_effect=RuntimeError("fixture DB failure"))
    assert await failing._lookup_external_close_from_db("TSLA", meta, closed_at=closed_at) is None
    nothing = _FillLookupMixin()
    nothing._sessionmaker = None
    assert await nothing._lookup_external_close_from_db("TSLA", meta, closed_at=closed_at) is None


def test_runtime_snapshot_reports_the_external_close_rules():
    from scripts.runtime.write_runtime_snapshot import _build_defaults_snapshot

    block = _build_defaults_snapshot()["external_close_accounting"]
    assert block["approximate_after_seconds"] == int(BOUND.total_seconds()) == 900
    assert block["escalate_after_seconds"] == ESCALATE.total_seconds() == 1800
    assert block["exit_reason"] == EXTERNAL_CLOSE_EXIT_REASON
    assert block["exact_price_source"] == EXTERNAL_CLOSE_EXACT_SOURCE
    assert block["wait_reason"] == EXTERNAL_CLOSE_UNBOOKED_REASON
    assert close_accounting.ACCOUNTING_POLICY == "exact_position_fills_or_pending_v1"
