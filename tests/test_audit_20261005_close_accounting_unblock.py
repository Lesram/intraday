"""Audit 2026-10-05 close-accounting unblock (C08-01, C07-01).

Isolated SQLite databases, synthetic identities and fake transports only: no
broker, network, saved brain state or production data.
"""
from __future__ import annotations

import itertools
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.infra.schemas import (
    AuditLog,
    Execution,
    Order,
    OutboxEvent,
    PositionLot,
    RealizedTrade,
)
from backend.integrations import alpaca_stream as stream
from backend.organism import live_engine_fills as fills
from backend.organism.live_engine_fills import (
    AMBIGUOUS_ORDER_REASON_PREFIX,
    REPLACEMENT_PENDING_REASON,
    ClosedPositionFills,
    _FillLookupMixin,
)

# Tuesday 2026-10-06 10:05 ET entry; Monday 2026-10-05 is the prior session.
ENTRY = datetime(2026, 10, 6, 14, 5, tzinfo=UTC)
EXIT = ENTRY + timedelta(minutes=40)
CLOSED = EXIT + timedelta(seconds=20)
APRIL = datetime(2026, 4, 8, 13, 33, tzinfo=UTC)
REMEDIATED = datetime(2026, 5, 6, 15, 0, tzinfo=UTC)
_ids = itertools.count(1)


@pytest.fixture
async def db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ledger.db'}")
    async with engine.begin() as connection:
        for table in (
            Order.__table__,
            Execution.__table__,
            PositionLot.__table__,
            RealizedTrade.__table__,
            AuditLog.__table__,
            OutboxEvent.__table__,
        ):
            await connection.run_sync(lambda sync, table=table: table.create(sync))
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def make_row(symbol, side, qty, *, at, status="filled", filled=None, price=None,
             broker=True, source="organism", tif="day", user="system", updated=None):
    """One synthetic order row; ids always contain hex letters (SQLite affinity)."""
    n = next(_ids)
    filled = (qty if status == "filled" else 0) if filled is None else filled
    attributes = {"reason": "fixture"}
    if source:
        attributes["source"] = source
    return Order(
        id=uuid.UUID(f"c0de{n:04x}-aaaa-4bbb-8ccc-{n:012x}"), user_id=user,
        client_idempotency_key=f"fixture-{n}-{uuid.uuid4().hex[:8]}", symbol=symbol,
        side=side, qty=Decimal(str(qty)), filled_qty=Decimal(str(filled)),
        avg_fill_price=Decimal(str(price)) if price is not None else None,
        status=status, order_type="market", tif=tif,
        submitted_at=at, created_at=at, updated_at=updated or at,
        broker_order_id=str(uuid.uuid4()) if broker else None, attributes=attributes,
    )


async def store(db, rows):
    async with db() as session:
        session.add_all(rows)
        await session.commit()


async def round_trip(db, symbol="XLE", qty=10, entry_px="62.40", exit_px="62.80"):
    entry = make_row(symbol, "buy", qty, at=ENTRY, price=entry_px)
    exit_ = make_row(symbol, "sell", qty, at=EXIT, price=exit_px)
    await store(db, [entry, exit_])
    return entry, exit_


def pending_meta(entry):
    return {"entry_order_id": str(entry.id), "direction": 1.0, "entry_source": "alpha",
            "pending_close": {"observed_at": CLOSED.isoformat()}}


def lookup(db):
    host = _FillLookupMixin()
    host._sessionmaker = db
    return host


# ── C08-01: stale history must not hold every later close of a symbol ──────


async def test_stale_history_no_longer_blocks_a_new_positions_exact_close(db):
    entry, _ = await round_trip(db)
    stale = [  # Production shape: four 2026-04-08 XLE dead letters, 'failed' on 05-06.
        make_row("XLE", "sell", 40 + i, at=APRIL + timedelta(minutes=i % 3), status="failed",
                 broker=False, source="organism" if i < 2 else None, updated=REMEDIATED)
        for i in range(4)
    ]
    stale += [
        make_row("XLE", "sell", 8, at=datetime(2026, 7, 15, 15, tzinfo=UTC),
                 status="accepted", broker=False),                      # dead letter
        make_row("XLE", "sell", 5, at=APRIL, status="replaced"),        # old DAY lineage
        make_row("XLE", "sell", 6, at=ENTRY - timedelta(days=7),
                 status="accepted"),                                    # stuck last week
        make_row("XLE", "buy", 5, at=APRIL, status="done_for_day"),     # broker-terminal
        make_row("XLE", "sell", 3, at=ENTRY - timedelta(days=30), status="accepted",
                 tif="gtc", broker=False),                              # never acknowledged
        make_row("XLE", "sell", 2, at=APRIL, status="failed", broker=False,
                 updated=ENTRY - timedelta(hours=1)),                   # remediated today
    ]
    await store(db, stale)
    meta = pending_meta(entry)
    result = await lookup(db)._lookup_closed_position_fills_from_db("XLE", meta, closed_at=CLOSED)
    assert result is not None
    assert (result.shares, result.entry_price, result.exit_price) == (10, 62.4, 62.8)
    assert result.pnl == pytest.approx(4.0) and result.price_source == "db_position_fills"
    assert "accounting_hold_reason" not in meta["pending_close"]


@pytest.mark.parametrize("case", [
    "same_session_acknowledged", "same_session_unacknowledged", "queued_after_prior_close",
    "delivered_late", "acknowledged_gtc", "late_fill_of_pre_entry_order",
    "same_session_replaced",
])
async def test_recent_genuinely_ambiguous_orders_still_defer(db, case):
    entry, _ = await round_trip(db)
    blocker = {
        "same_session_acknowledged": lambda: make_row(
            "XLE", "buy", 5, at=ENTRY - timedelta(minutes=30), status="accepted"),
        "same_session_unacknowledged": lambda: make_row(
            "XLE", "sell", 5, at=ENTRY - timedelta(hours=2), status="accepted", broker=False),
        # Created last week, delivered and acknowledged this morning (outbox delay).
        "delivered_late": lambda: make_row(
            "XLE", "sell", 5, at=ENTRY - timedelta(days=7), status="accepted",
            updated=ENTRY - timedelta(minutes=20)),
        # Monday 17:30 ET: a DAY order queued for Tuesday's session.
        "queued_after_prior_close": lambda: make_row(
            "XLE", "sell", 5, at=datetime(2026, 10, 5, 21, 30, tzinfo=UTC), status="new"),
        "acknowledged_gtc": lambda: make_row(
            "XLE", "sell", 5, at=ENTRY - timedelta(days=60), status="accepted", tif="gtc"),
        "late_fill_of_pre_entry_order": lambda: make_row(
            "XLE", "sell", 3, at=ENTRY - timedelta(days=3), price="62.50",
            updated=ENTRY + timedelta(minutes=5)),
        "same_session_replaced": lambda: make_row(
            "XLE", "sell", 5, at=ENTRY - timedelta(minutes=30), status="replaced"),
    }[case]()
    await store(db, [blocker])
    meta = pending_meta(entry)
    assert await lookup(db)._lookup_closed_position_fills_from_db(
        "XLE", meta, closed_at=CLOSED) is None
    expected = (REPLACEMENT_PENDING_REASON if case == "same_session_replaced"
                else f"{AMBIGUOUS_ORDER_REASON_PREFIX}{blocker.id}")
    assert meta["pending_close"]["accounting_hold_reason"] == expected


def test_eligible_session_follows_the_nyse_calendar():
    def at_et(*parts):
        from zoneinfo import ZoneInfo
        return datetime(*parts, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)

    row = {"broker_order_id": "acknowledged", "tif": "day", "updated_at": None}
    # Friday before Labor Day, after the close: queued for Tuesday 2026-09-08.
    row["submitted_at"] = at_et(2026, 9, 4, 17, 0)
    assert fills._eligible_session_end(row["submitted_at"]) == at_et(2026, 9, 8, 20, 0)
    assert fills._order_may_affect_lifetime(row, at_et(2026, 9, 8, 10, 0))
    assert not fills._order_may_affect_lifetime(row, at_et(2026, 9, 9, 10, 0))
    # During the session it cannot outlive that day's extended hours.
    row["submitted_at"] = at_et(2026, 9, 4, 11, 0)
    assert not fills._order_may_affect_lifetime(row, at_et(2026, 9, 8, 10, 0))
    # After the 13:00 early close on 2026-11-27 it queues for Monday.
    assert fills._eligible_session_end(at_et(2026, 11, 27, 14, 0)) == at_et(2026, 11, 30, 20, 0)
    # A later acknowledgement (updated_at) moves the session later, never earlier.
    row["updated_at"] = at_et(2026, 9, 8, 9, 0)
    assert fills._order_may_affect_lifetime(row, at_et(2026, 9, 8, 10, 0))
    # A never-acknowledged row is not revived by a later touch.
    row["broker_order_id"] = None
    assert not fills._order_may_affect_lifetime(row, at_et(2026, 9, 8, 10, 0))
    # Unknown evidence fails closed.
    assert fills._order_may_affect_lifetime({"broker_order_id": None}, ENTRY)


async def test_hold_reason_names_the_blocker_once_and_clears_when_it_resolves(db, monkeypatch):
    entry, _ = await round_trip(db)
    blocker = make_row("XLE", "buy", 5, at=ENTRY - timedelta(minutes=30), status="accepted")
    await store(db, [blocker])
    log = MagicMock()
    monkeypatch.setattr(fills, "logger", log)
    meta = pending_meta(entry)
    for _ in range(2):
        assert await lookup(db)._lookup_closed_position_fills_from_db(
            "XLE", meta, closed_at=CLOSED) is None
    held = [c for c in log.warning.call_args_list if "held" in str(c.args[0])]
    assert len(held) == 1 and str(blocker.id) in str(held[0].args)
    async with db() as session:
        (await session.get(Order, blocker.id)).status = "canceled"
        await session.commit()
    result = await lookup(db)._lookup_closed_position_fills_from_db("XLE", meta, closed_at=CLOSED)
    assert result is not None and result.pnl == pytest.approx(4.0)
    assert "accounting_hold_reason" not in meta["pending_close"]


def make_engine(tmp_path, db, now):
    from backend.organism import close_accounting
    from backend.organism.live_engine import OrganismLiveEngine

    broker = MagicMock()
    broker.get_all_positions = AsyncMock(return_value={})
    engine = OrganismLiveEngine(
        data_client=MagicMock(), order_service=broker, positions_service=broker,
        brain_dir=str(tmp_path / "brain"), universe=["XLE", "TSLA"], sessionmaker=db,
    )
    engine._now_fn = lambda: now
    engine._time_fn = lambda: now.timestamp()
    engine._daily_loss_date = close_accounting.session_date(now)
    engine._tick_count = 200
    engine._save_brain = MagicMock()
    # Legacy orphan lookups use PostgreSQL JSON SQL; exact accounting never needs them.
    engine._lookup_exit_fill_from_db = AsyncMock(return_value=None)
    engine._lookup_entry_fill_from_db = AsyncMock(return_value=None)
    return engine


def track(engine, symbol, entry, entry_time):
    engine._entry_metadata[symbol] = {
        "entry_order_id": str(entry.id), "entry_price": float(entry.avg_fill_price or 100),
        "entry_tick": 10, "filled_shares": int(entry.qty), "direction": 1.0,
        "entry_source": "alpha", "strategy_id": "momentum",
        "entry_time": entry_time.timestamp(), "confidence": 0.6,
    }
    engine._last_exit_reason[symbol] = "trailing_stop"


@pytest.mark.parametrize("live_blocker", [False, True])
async def test_engine_accounts_despite_stale_history_and_defers_on_live_ambiguity(
    db, tmp_path, live_blocker,
):
    entry, _ = await round_trip(db)
    rows = [make_row("XLE", "sell", 40, at=APRIL, status="failed", broker=False,
                     updated=REMEDIATED)]
    if live_blocker:
        rows.append(make_row("XLE", "buy", 5, at=ENTRY - timedelta(minutes=30), status="accepted"))
    await store(db, rows)
    engine = make_engine(tmp_path, db, CLOSED)
    track(engine, "XLE", entry, ENTRY)
    await engine._reconcile_fills({})
    if live_blocker:
        assert engine._all_trades == [] and "XLE" in engine._entry_metadata
        reason = engine._unresolved_close_status()["XLE"]["reason"]
        assert reason == f"{AMBIGUOUS_ORDER_REASON_PREFIX}{rows[-1].id}"
    else:
        assert len(engine._all_trades) == 1 and "XLE" not in engine._entry_metadata
        trade = engine._all_trades[0]
        assert trade.pnl == pytest.approx(4.0) and trade.price_source == "db_position_fills"
    assert not engine._order_service.submit_order.called


# ── C07-01: a broker-confirmed close is persisted even without matching lots ─


def now_rows():
    now = datetime.now(UTC)
    return now - timedelta(minutes=30), now - timedelta(minutes=10), now - timedelta(minutes=1)


def broker_snapshot(row, *, filled, price, status="filled"):
    return {
        "id": row.broker_order_id, "client_order_id": row.client_idempotency_key,
        "symbol": row.symbol, "side": row.side, "qty": str(row.qty), "status": status,
        "filled_qty": str(filled), "filled_avg_price": str(price),
    }


async def apply_snapshot(db, row, *, filled, price, status="filled"):
    async with db() as session:
        current = await session.get(Order, row.id)
        outcome = await stream.apply_order_fill_snapshot(
            session, current, status=status, cumulative_filled_qty=str(filled),
            avg_fill_price=str(price), broker_order_id=row.broker_order_id,
        )
        await session.commit()
        return outcome


async def ledger(db, row):
    async with db() as session:
        order = await session.get(Order, row.id)
        executions = list((await session.execute(
            select(Execution).where(Execution.order_id == row.id))).scalars())
        realized = list((await session.execute(
            select(RealizedTrade).where(RealizedTrade.close_order_id == row.id))).scalars())
        lots = list((await session.execute(select(PositionLot))).scalars())
        return order, executions, realized, lots


def stream_client(monkeypatch, db):
    @asynccontextmanager
    async def context():
        async with db() as session:
            yield session

    monkeypatch.setattr(stream, "get_session_context", context)
    monkeypatch.setattr("backend.api.socketio_server.broadcast_order_update", AsyncMock())
    client = stream.AlpacaStreamClient.__new__(stream.AlpacaStreamClient)
    client._terminal_order_ids = set()
    client._sync_positions_after_terminal_fill = AsyncMock()
    return client


async def via_stream(db, monkeypatch, row, snapshot):
    client = stream_client(monkeypatch, db)
    await client._process_trade_update(
        {"stream": "trade_updates", "data": {"event": "fill", "order": snapshot}})


async def via_recovery(db, monkeypatch, row, snapshot):
    from backend.services import order_recovery_service as recovery

    result = await recovery.OrderRecoveryService().recover(db, AsyncMock(return_value=snapshot))
    assert (result["errors"], result["reconciled"]) == (0, 1)


async def via_gap_fill(db, monkeypatch, row, snapshot):
    from backend.services import order_recovery_service as recovery

    monkeypatch.setattr(recovery, "recover_persisted_orders", AsyncMock())
    stream_client(monkeypatch, db)

    async def get(url, **kwargs):
        assert url.endswith(snapshot["id"])
        return httpx.Response(200, json=snapshot)

    @asynccontextmanager
    async def transport(*args, **kwargs):
        yield SimpleNamespace(get=get)

    monkeypatch.setattr(httpx, "AsyncClient", transport)
    client = stream.AlpacaStreamClient.__new__(stream.AlpacaStreamClient)
    client._last_connected_at = 0
    client._terminal_order_ids = set()
    client.api_key, client.api_secret, client.is_paper = "synthetic", "synthetic", True
    await client._gap_fill_after_reconnect()


async def via_startup_sync(db, monkeypatch, row, snapshot):
    from backend.api.lifespan import _sync_orders
    from backend.services import order_recovery_service as recovery

    monkeypatch.setattr(recovery, "recover_persisted_orders", AsyncMock())
    monkeypatch.setattr("backend.api.socketio_server.broadcast_order_update", AsyncMock())
    broker = SimpleNamespace(
        base_url="https://paper.invalid", _get_auth_headers=lambda: {},
        client=SimpleNamespace(get=AsyncMock(return_value=httpx.Response(200, json=[snapshot]))),
    )
    monkeypatch.setattr("backend.integrations.alpaca_broker.get_alpaca_broker_client", lambda: broker)
    await _sync_orders(SimpleNamespace(state=SimpleNamespace(sessionmaker=db)))


async def via_outbox_ack(db, monkeypatch, row, snapshot):
    from backend.infra.outbox_worker import OutboxWorker

    @asynccontextmanager
    async def context():
        async with db() as session:
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", context)
    details = {"success": True, "broker": "alpaca", "broker_order_id": snapshot["id"],
               "status": snapshot["status"], "alpaca_response": snapshot}
    await OutboxWorker.__new__(OutboxWorker)._update_order_status(
        str(row.id), snapshot["status"], snapshot["id"], details)


INGRESS = {
    "trade_update_stream": via_stream,
    "persisted_order_recovery": via_recovery,
    "reconnect_gap_fill": via_gap_fill,
    "startup_order_sync": via_startup_sync,
    "outbox_acknowledgement": via_outbox_ack,
}


@pytest.mark.parametrize("ingress", sorted(INGRESS))
async def test_orphan_exit_without_lots_is_persisted_on_every_ingress(db, monkeypatch, ingress):
    _, submitted, touched = now_rows()
    exit_ = make_row("NVDA", "sell", 4, at=submitted, status="accepted", updated=touched)
    await store(db, [exit_])
    log = MagicMock()
    monkeypatch.setattr(stream, "logger", log)
    await INGRESS[ingress](db, monkeypatch, exit_, broker_snapshot(exit_, filled=4, price=50))
    order, executions, realized, lots = await ledger(db, exit_)
    assert (order.status, order.filled_qty, order.avg_fill_price) == ("filled", 4, 50)
    assert [(x.fill_qty, x.fill_price) for x in executions] == [(4, 50)]
    assert realized == [] and lots == []
    record = order.attributes["lot_accounting"]
    assert record["status"] == "unmatched" and record["repair"] == "required"
    assert record["reason"] == "no_open_lots" and record["owner"] == "system"
    assert Decimal(record["unmatched_qty"]) == 4 and Decimal(record["matched_qty"]) == 0
    assert record["events"] == 1 and record["last_execution_id"] == str(executions[0].id)
    assert order.attributes["source"] == "organism"  # merged, not replaced
    pages = [c for c in log.critical.call_args_list if "LOT ACCOUNTING DISCREPANCY" in c.args[0]]
    assert len(pages) == 1 and ingress in pages[0].args and str(exit_.id) in pages[0].args


async def test_operator_close_of_engine_position_is_persisted_with_discrepancy(db, monkeypatch):
    opened, closed, _ = now_rows()
    entry = make_row("TSLA", "buy", 6, at=opened, status="accepted")
    ui_close = make_row("TSLA", "sell", 6, at=closed, status="accepted", source=None,
                        user="ops@example.com")
    await store(db, [entry, ui_close])
    log = MagicMock()
    monkeypatch.setattr(stream, "logger", log)
    await via_stream(db, monkeypatch, entry, broker_snapshot(entry, filled=6, price=100))
    await via_stream(db, monkeypatch, ui_close, broker_snapshot(ui_close, filled=6, price=101))
    order, executions, realized, lots = await ledger(db, ui_close)
    assert (order.status, order.filled_qty, len(executions), realized) == ("filled", 6, 1, [])
    assert order.attributes["lot_accounting"]["owner"] == "ops@example.com"
    # Matching stays owner-scoped (follow-up): the engine's lot is left for repair.
    assert [(lot.user_id, lot.remaining_qty, lot.status) for lot in lots] == [("system", 6, "open")]
    assert len(log.critical.call_args_list) == 1


async def test_partial_deficit_closes_available_lots_and_records_the_remainder(db, monkeypatch):
    opened, closed, _ = now_rows()
    entry = make_row("TSLA", "buy", 4, at=opened, status="accepted")
    exit_ = make_row("TSLA", "sell", 6, at=closed, status="accepted")
    await store(db, [entry, exit_])
    await apply_snapshot(db, entry, filled=4, price=100)
    outcome = await apply_snapshot(db, exit_, filled=6, price=105)
    order, executions, realized, lots = await ledger(db, exit_)
    assert outcome["lot_discrepancy"]["reason"] == "insufficient_open_lots"
    assert [(x.qty, x.realized_pnl) for x in realized] == [(4, 20)]
    assert [(lot.remaining_qty, lot.status) for lot in lots] == [(0, "closed")]
    record = order.attributes["lot_accounting"]
    assert (Decimal(record["matched_qty"]), Decimal(record["unmatched_qty"])) == (4, 2)
    assert (order.status, order.filled_qty, sum(x.fill_qty for x in executions)) == ("filled", 6, 6)


async def test_close_defers_while_an_earlier_opening_fill_can_still_arrive(db, monkeypatch):
    opened, closed, _ = now_rows()
    exit_ = make_row("TSLA", "sell", 6, at=closed, status="accepted")  # lower id: recovered first
    entry = make_row("TSLA", "buy", 6, at=opened, status="accepted")
    await store(db, [exit_, entry])
    async with db() as session:
        with pytest.raises(stream.LotAccountingDeferred, match=str(entry.id)):
            await stream.apply_order_fill_snapshot(
                session, await session.get(Order, exit_.id), status="filled",
                cumulative_filled_qty="6", avg_fill_price="101",
                broker_order_id=exit_.broker_order_id,
            )
        await session.rollback()
    order, executions, _, lots = await ledger(db, exit_)
    assert (order.status, order.filled_qty, executions, lots) == ("accepted", 0, [], [])
    # Real recovery, rows paged by id: pass 1 defers the close and settles the
    # entry; pass 2 closes the entry's lot. The ledger converges as before.
    from backend.services import order_recovery_service as recovery

    snapshots = {exit_.broker_order_id: broker_snapshot(exit_, filled=6, price=101),
                 entry.broker_order_id: broker_snapshot(entry, filled=6, price=100)}
    service = recovery.OrderRecoveryService()
    fetch = AsyncMock(side_effect=lambda broker_id: snapshots[broker_id])
    first = await service.recover(db, fetch)
    second = await service.recover(db, fetch)
    assert (first["errors"], first["reconciled"]) == (1, 1)
    assert (second["errors"], second["reconciled"]) == (0, 1)
    order, executions, realized, lots = await ledger(db, exit_)
    assert order.status == "filled" and "lot_accounting" not in order.attributes
    assert [(x.qty, x.realized_pnl) for x in realized] == [(6, 6)]
    assert [(lot.remaining_qty, lot.status) for lot in lots] == [(0, "closed")]


@pytest.mark.parametrize("opening", ["stale", "unacknowledged", "other_owner", "terminal"])
async def test_openings_that_cannot_settle_do_not_hold_a_confirmed_close(db, opening):
    opened, closed, _ = now_rows()
    entry = {
        "stale": lambda: make_row("TSLA", "buy", 6, status="accepted",
                                  at=datetime.now(UTC) - timedelta(days=6)),
        "unacknowledged": lambda: make_row("TSLA", "buy", 6, at=opened, status="accepted",
                                           broker=False),
        "other_owner": lambda: make_row("TSLA", "buy", 6, at=opened, status="accepted",
                                        user="ops@example.com", source=None),
        "terminal": lambda: make_row("TSLA", "buy", 6, at=opened, status="canceled"),
    }[opening]()
    exit_ = make_row("TSLA", "sell", 6, at=closed, status="accepted")
    await store(db, [entry, exit_])
    outcome = await apply_snapshot(db, exit_, filled=6, price=101)
    assert outcome["lot_discrepancy"]["unmatched_qty"] == "6"
    order, executions, _, _ = await ledger(db, exit_)
    assert (order.status, order.filled_qty, len(executions)) == ("filled", 6, 1)


async def test_replayed_snapshot_neither_repeats_the_discrepancy_nor_pages(db, monkeypatch):
    _, submitted, touched = now_rows()
    exit_ = make_row("NVDA", "sell", 4, at=submitted, status="accepted", updated=touched)
    await store(db, [exit_])
    await apply_snapshot(db, exit_, filled=4, price=50)
    before, _, _, _ = await ledger(db, exit_)
    log = MagicMock()
    monkeypatch.setattr(stream, "logger", log)
    await via_startup_sync(db, monkeypatch, exit_, broker_snapshot(exit_, filled=4, price=50))
    after, executions, _, _ = await ledger(db, exit_)
    assert after.attributes == before.attributes and after.updated_at == before.updated_at
    assert after.attributes["lot_accounting"]["events"] == 1 and len(executions) == 1
    assert not log.critical.called


async def test_discrepancy_pages_only_after_commit(db, monkeypatch):
    _, submitted, touched = now_rows()
    exit_ = make_row("NVDA", "sell", 4, at=submitted, status="accepted", updated=touched)
    await store(db, [exit_])
    events = []
    log = MagicMock()
    log.critical.side_effect = lambda *args, **kwargs: events.append("critical")
    monkeypatch.setattr(stream, "logger", log)
    original = AsyncSession.commit

    async def failing_commit(self):
        events.append("commit_failed")
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)
    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        await via_stream(db, monkeypatch, exit_, broker_snapshot(exit_, filled=4, price=50))
    assert events == ["commit_failed"]
    order, executions, _, _ = await ledger(db, exit_)
    assert (order.status, order.filled_qty, executions) == ("accepted", 0, [])
    assert "lot_accounting" not in order.attributes

    async def recording_commit(self):
        await original(self)
        events.append("commit")

    monkeypatch.setattr(AsyncSession, "commit", recording_commit)
    await via_stream(db, monkeypatch, exit_, broker_snapshot(exit_, filled=4, price=50))
    assert events == ["commit_failed", "commit", "critical"]


async def test_startup_sync_applies_the_newest_first_page_oldest_first(db, monkeypatch):
    opened, closed, _ = now_rows()
    entry = make_row("TSLA", "buy", 6, at=opened, status="accepted")
    exit_ = make_row("TSLA", "sell", 6, at=closed, status="accepted")
    await store(db, [entry, exit_])
    from backend.api.lifespan import _sync_orders
    from backend.services import order_recovery_service as recovery

    monkeypatch.setattr(recovery, "recover_persisted_orders", AsyncMock())
    monkeypatch.setattr("backend.api.socketio_server.broadcast_order_update", AsyncMock())
    page = [broker_snapshot(exit_, filled=6, price=101), broker_snapshot(entry, filled=6, price=100)]
    broker = SimpleNamespace(
        base_url="https://paper.invalid", _get_auth_headers=lambda: {},
        client=SimpleNamespace(get=AsyncMock(return_value=httpx.Response(200, json=page))),
    )
    monkeypatch.setattr("backend.integrations.alpaca_broker.get_alpaca_broker_client", lambda: broker)
    await _sync_orders(SimpleNamespace(state=SimpleNamespace(sessionmaker=db)))
    order, _, realized, lots = await ledger(db, exit_)
    assert order.status == "filled" and "lot_accounting" not in order.attributes
    assert [(x.qty, x.realized_pnl) for x in realized] == [(6, 6)]
    assert [(lot.remaining_qty, lot.status) for lot in lots] == [(0, "closed")]


async def test_normal_engine_round_trip_is_unchanged(db, monkeypatch, tmp_path):
    opened, closed, _ = now_rows()
    entry = make_row("TSLA", "buy", 6, at=opened, status="accepted")
    exit_ = make_row("TSLA", "sell", 6, at=closed, status="accepted")
    await store(db, [entry, exit_])
    log = MagicMock()
    monkeypatch.setattr(stream, "logger", log)
    await via_stream(db, monkeypatch, entry, broker_snapshot(entry, filled=6, price=100))
    await via_stream(db, monkeypatch, exit_, broker_snapshot(exit_, filled=6, price=101))
    order, executions, realized, lots = await ledger(db, exit_)
    assert (order.status, order.filled_qty, len(executions)) == ("filled", 6, 1)
    assert [(x.user_id, x.qty, x.realized_pnl) for x in realized] == [("system", 6, 6)]
    assert [(lot.remaining_qty, lot.status) for lot in lots] == [(0, "closed")]
    async with db() as session:
        attrs = [row.attributes for row in (await session.execute(select(Order))).scalars()]
    assert all("lot_accounting" not in item for item in attrs)
    assert not log.critical.called
    # The engine's exact close accounting reads the same rows and releases TSLA.
    close_seen = datetime.now(UTC)
    exact = await lookup(db)._lookup_closed_position_fills_from_db(
        "TSLA", {"entry_order_id": str(entry.id), "direction": 1.0}, closed_at=close_seen)
    assert exact == ClosedPositionFills(shares=6, entry_price=100.0, exit_price=101.0,
                                        pnl=6.0, had_partial_exits=False)
    engine = make_engine(tmp_path, db, close_seen)
    track(engine, "TSLA", entry, opened)
    await engine._reconcile_fills({})
    assert len(engine._all_trades) == 1 and "TSLA" not in engine._entry_metadata
    trade = engine._all_trades[0]
    assert trade.pnl == pytest.approx(6.0) and trade.price_source == "db_position_fills"
    assert trade.is_reconciliation_artifact is False
