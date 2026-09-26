"""Persisted-order recovery: synthetic databases and fake GET transport only."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.infra.repositories.orders import OrdersRepo
from backend.infra.schemas import (
    AuditLog,
    Execution,
    Order,
    OutboxEvent,
    PositionLot,
    RealizedTrade,
)
from backend.services import order_recovery_service as recovery


@pytest.fixture
async def sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        for table in (
            Order.__table__,
            OutboxEvent.__table__,
            Execution.__table__,
            PositionLot.__table__,
            RealizedTrade.__table__,
            AuditLog.__table__,
        ):
            await conn.run_sync(lambda sync, table=table: table.create(sync))
    recovery._services.clear()
    try:
        yield sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        recovery._services.clear()
        await engine.dispose()


def make_order(number=1, *, owned=True, status="accepted"):
    old = datetime.now(UTC) - timedelta(days=10)
    return Order(
        id=uuid.UUID(f"a0000000-0000-4000-8000-{number:012x}"),
        user_id="synthetic",
        client_idempotency_key=f"synthetic-{number}",
        symbol="SYNTH",
        side="buy",
        qty=Decimal(10),
        filled_qty=Decimal(0),
        status=status,
        order_type="market",
        tif="day",
        broker_order_id=str(uuid.UUID(int=10000 + number)),
        submitted_at=old,
        created_at=old,
        updated_at=old,
        attributes={"source": "organism"} if owned else {},
    )


def snapshot(row, *, status="filled", filled="10", price="100"):
    return {
        "id": row.broker_order_id,
        "client_order_id": row.client_idempotency_key,
        "symbol": row.symbol,
        "side": row.side,
        "qty": str(row.qty),
        "status": status,
        "filled_qty": filled,
        "filled_avg_price": price,
    }


async def seed(sessions, *rows):
    async with sessions() as session:
        session.add_all(rows)
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["filled", "canceled", "expired"])
async def test_old_owned_order_recovers_terminal_fills_once(sessions, status):
    row = make_order()
    await seed(sessions, row)
    expected_qty = 10 if status == "filled" else 4
    fetch = AsyncMock(return_value=snapshot(row, status=status, filled=str(expected_qty)))
    service = recovery.OrderRecoveryService()
    first = await service.recover(sessions, fetch)
    second = await service.recover(sessions, fetch)
    assert first["applied"] == 1 and first["sweep_complete"]
    assert second["attempted"] == 0 and fetch.await_count == 1
    async with sessions() as session:
        assert (await session.execute(select(Execution.fill_qty))).scalar_one() == expected_qty
        assert (
            await session.execute(select(PositionLot.remaining_qty))
        ).scalar_one() == expected_qty
        assert (await session.get(Order, row.id)).status == (
            "cancelled" if status == "canceled" else status
        )


@pytest.mark.asyncio
async def test_unowned_legacy_and_old_terminal_are_not_migrated(sessions):
    rows = [
        make_order(1, owned=False),
        make_order(2, owned=False, status="failed"),
        make_order(3, status="filled"),
        make_order(4, status="cancelled"),
    ]
    rows[-1].filled_qty, rows[-1].avg_fill_price = Decimal(4), Decimal(100)
    await seed(sessions, *rows)
    fetch = AsyncMock()
    assert (await recovery.OrderRecoveryService().recover(sessions, fetch))["attempted"] == 0
    fetch.assert_not_awaited()
    async with sessions() as session:
        assert not list((await session.execute(select(Execution))).scalars())
        assert [(await session.get(Order, row.id)).status for row in rows] == [
            r.status for r in rows
        ]


@pytest.mark.asyncio
async def test_outbox_lineage_requires_matching_order_and_client_key(sessions):
    rows = [make_order(i, owned=False) for i in range(1, 4)]
    await seed(sessions, *rows)
    async with sessions() as session:
        for row, key in [(rows[0], rows[0].client_idempotency_key), (rows[1], "wrong")]:
            session.add(
                OutboxEvent(
                    topic="order.submitted",
                    status="sent",
                    payload={"order_id": str(row.id), "client_key": key},
                )
            )
        session.add(
            OutboxEvent(
                topic="unrelated",
                status="sent",
                payload={"order_id": str(rows[2].id), "client_key": rows[2].client_idempotency_key},
            )
        )
        await session.commit()
    fetch = AsyncMock(return_value=snapshot(rows[0]))
    result = await recovery.OrderRecoveryService().recover(sessions, fetch)
    assert result["attempted"] == result["applied"] == 1
    fetch.assert_awaited_once_with(rows[0].broker_order_id)


@pytest.mark.asyncio
async def test_keyset_progress_covers_more_than100_despite_early_errors(sessions):
    rows = [make_order(i) for i in range(1, 104)]
    await seed(sessions, *rows)
    by_id = {r.broker_order_id: r for r in rows}
    visited = []

    async def fetch(broker_id):
        visited.append(broker_id)
        if broker_id == rows[0].broker_order_id:
            raise ValueError("Synthetic404")
        return snapshot(by_id[broker_id], status="accepted", filled="0", price=None)

    service = recovery.OrderRecoveryService()
    for _ in range(6):
        result = await service.recover(sessions, fetch)
        assert result["attempted"] <= 20
    assert visited == [r.broker_order_id for r in rows]
    assert result["sweep_complete"] and service.cursor is None
    await service.recover(sessions, fetch)
    assert visited[103] == rows[0].broker_order_id
    restarted = recovery.OrderRecoveryService()
    await restarted.recover(sessions, fetch)
    assert visited[123] == rows[0].broker_order_id  # Deliberately process-local progress.


@pytest.mark.asyncio
async def test_new_row_behind_cursor_is_found_after_wrap(sessions, monkeypatch):
    monkeypatch.setattr(recovery, "MAX_REQUESTS", 1)
    rows = [make_order(2), make_order(3)]
    await seed(sessions, *rows)
    by_id = {r.broker_order_id: r for r in rows}
    visited = []

    async def fetch(broker_id):
        visited.append(broker_id)
        return snapshot(by_id[broker_id], status="accepted", filled="0", price=None)

    service = recovery.OrderRecoveryService()
    await service.recover(sessions, fetch)
    inserted = make_order(1)
    by_id[inserted.broker_order_id] = inserted
    await seed(sessions, inserted)
    assert (await service.recover(sessions, fetch))["sweep_complete"]
    await service.recover(sessions, fetch)
    assert visited == [rows[0].broker_order_id, rows[1].broker_order_id, inserted.broker_order_id]


@pytest.mark.asyncio
@pytest.mark.parametrize("status,filled", [("replaced", "0"), ("filled", "4")])
async def test_unsupported_terminal_snapshot_stays_unresolved(sessions, status, filled):
    row = make_order()
    await seed(sessions, row)
    fetch = AsyncMock(return_value=snapshot(row, status=status, filled=filled))
    service = recovery.OrderRecoveryService()
    for _ in range(2):
        result = await service.recover(sessions, fetch)
        assert result["attempted"] == result["errors"] == 1
    async with sessions() as session:
        saved = await session.get(Order, row.id)
        assert saved.status == "accepted" and saved.filled_qty == 0
        assert not list((await session.execute(select(Execution))).scalars())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("id", str(uuid.UUID(int=999))),
        ("client_order_id", "other"),
        ("symbol", "OTHER"),
        ("side", "sell"),
        ("qty", "11"),
        ("filled_qty", "NaN"),
        ("filled_qty", "11"),
        ("filled_qty", "-1"),
        ("filled_qty", True),
        ("filled_avg_price", "Infinity"),
        ("filled_avg_price", None),
        ("status", "unknown"),
        ("status", "replaced"),
    ],
)
async def test_invalid_or_unrelated_snapshot_never_changes_order(sessions, field, value):
    row = make_order()
    await seed(sessions, row)
    data = {**snapshot(row), field: value}
    result = await recovery.OrderRecoveryService().recover(sessions, AsyncMock(return_value=data))
    assert result["errors"] == 1 and result["applied"] == 0
    async with sessions() as session:
        saved = await session.get(Order, row.id)
        assert saved.status == "accepted" and saved.filled_qty == 0
        assert not list((await session.execute(select(Execution))).scalars())


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code,body", [(404, {}), (429, {}), (200, []), (200, None)])
async def test_exact_get_errors_never_infer_cancel_or_submit(sessions, status_code, body):
    row = make_order()
    await seed(sessions, row)
    transport = SimpleNamespace(
        get=AsyncMock(return_value=httpx.Response(status_code, json=body)),
        post=AsyncMock(),
        delete=AsyncMock(),
    )
    broker = SimpleNamespace(
        client=transport, base_url="https://paper.invalid", _get_auth_headers=lambda: {}
    )
    result = await recovery.recover_persisted_orders(sessions, broker)
    assert result["errors"] == 1
    assert transport.get.call_args.args[0].endswith("/v2/orders/" + row.broker_order_id)
    transport.post.assert_not_awaited()
    transport.delete.assert_not_awaited()
    async with sessions() as session:
        assert (await session.get(Order, row.id)).status == "accepted"


@pytest.mark.asyncio
async def test_missing_or_unsafe_broker_identity_is_never_looked_up(sessions):
    a, b = make_order(1), make_order(2)
    a.broker_order_id = None
    b.broker_order_id = "../account"
    await seed(sessions, a, b)
    fetch = AsyncMock()
    result = await recovery.OrderRecoveryService().recover(sessions, fetch)
    assert result["attempted"] == result["errors"] == 1
    fetch.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["identity", "terminal", "ownership"])
async def test_order_race_revalidated_under_lock(sessions, change):
    row = make_order()
    await seed(sessions, row)

    async def fetch(_):
        async with sessions() as session:
            current = await session.get(Order, row.id)
            if change == "identity":
                current.client_idempotency_key = "changed"
            elif change == "terminal":
                current.status = "cancelled"
            else:
                current.attributes = {}
            await session.commit()
        return snapshot(row)

    result = await recovery.OrderRecoveryService().recover(sessions, fetch)
    assert result["changed"] == 1 and result["applied"] == 0
    async with sessions() as session:
        assert not list((await session.execute(select(Execution))).scalars())


@pytest.mark.asyncio
async def test_accounting_failure_rolls_back_then_retry_is_idempotent(sessions, monkeypatch):
    from backend.services.lot_tracker_service import LotTracker

    row = make_order()
    await seed(sessions, row)
    original = LotTracker.create_lot
    monkeypatch.setattr(LotTracker, "create_lot", AsyncMock(side_effect=RuntimeError("Synthetic")))
    service = recovery.OrderRecoveryService()
    fetch = AsyncMock(return_value=snapshot(row))
    assert (await service.recover(sessions, fetch))["errors"] == 1
    async with sessions() as session:
        assert (await session.get(Order, row.id)).filled_qty == 0
        assert not list((await session.execute(select(Execution))).scalars())
    monkeypatch.setattr(LotTracker, "create_lot", original)
    assert (await service.recover(sessions, fetch))["applied"] == 1
    assert (await service.recover(sessions, fetch))["attempted"] == 0


@pytest.mark.asyncio
async def test_lookup_timeout_advances_to_later_row(sessions, monkeypatch):
    rows = [make_order(1), make_order(2)]
    await seed(sessions, *rows)
    monkeypatch.setattr(recovery, "LOOKUP_BUDGET_SECONDS", 0.01)

    async def fetch(broker_id):
        if broker_id == rows[0].broker_order_id:
            await asyncio.Event().wait()
        return snapshot(rows[1])

    result = await recovery.OrderRecoveryService().recover(sessions, fetch)
    assert result["attempted"] == 2 and result["errors"] == 1 and result["applied"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_at", ["page", "lock", "commit"])
async def test_total_deadline_covers_database_waits(sessions, monkeypatch, blocked_at):
    row = make_order()
    await seed(sessions, row)
    monkeypatch.setattr(recovery, "PASS_BUDGET_SECONDS", 0.03)

    async def block(*args, **kwargs):
        await asyncio.Event().wait()

    if blocked_at == "page":
        monkeypatch.setattr(OrdersRepo, "get_recovery_orders_page", block)
    elif blocked_at == "lock":
        monkeypatch.setattr(OrdersRepo, "lock_recovery_order", block)
    else:
        monkeypatch.setattr(AsyncSession, "commit", block)
    service = recovery.OrderRecoveryService()
    result = await asyncio.wait_for(
        service.recover(sessions, AsyncMock(return_value=snapshot(row))), 0.5
    )
    assert result["state"] == "deadline" and result["backlog"]
    assert service.cursor == (None if blocked_at == "page" else row.id)
    async with sessions() as session:
        assert (await session.get(Order, row.id)).filled_qty == 0
        assert not list((await session.execute(select(Execution))).scalars())


@pytest.mark.asyncio
async def test_concurrent_pass_is_single_flight(sessions):
    row = make_order()
    await seed(sessions, row)
    entered, release = asyncio.Event(), asyncio.Event()

    async def fetch(_):
        entered.set()
        await release.wait()
        return snapshot(row)

    service = recovery.OrderRecoveryService()
    task = asyncio.create_task(service.recover(sessions, fetch))
    await asyncio.wait_for(entered.wait(), 1)
    assert (await service.recover(sessions, fetch))["state"] == "already_running"
    release.set()
    assert (await task)["applied"] == 1


@pytest.mark.asyncio
async def test_periodic_recovery_runs_even_without_filled_position_summary(sessions, monkeypatch):
    from backend.services import scheduled_reconciliation as scheduled

    recover = AsyncMock(return_value={"attempted": 1, "applied": 1})
    summary = AsyncMock(return_value={"total_filled_buys": 0, "discrepancies": []})
    monkeypatch.setattr(recovery, "recover_persisted_orders", recover)
    monkeypatch.setattr(scheduled, "get_sessionmaker", lambda: sessions)
    monkeypatch.setattr(scheduled, "AlpacaBrokerClient", lambda: object())
    monkeypatch.setattr(
        scheduled.PositionReconciliationService, "get_reconciliation_summary", summary
    )
    result = await scheduled.run_scheduled_reconciliation()
    recover.assert_awaited_once_with(sessions)
    assert result["order_recovery"]["applied"] == 1


@pytest.mark.asyncio
async def test_startup_recovery_precedes_empty_latest500_response(sessions, monkeypatch):
    from backend.api.lifespan import _sync_orders

    row = make_order()
    await seed(sessions, row)

    async def get(url, **kwargs):
        return httpx.Response(200, json=snapshot(row) if url.endswith(row.broker_order_id) else [])

    broker = SimpleNamespace(
        client=SimpleNamespace(get=get),
        base_url="https://paper.invalid",
        _get_auth_headers=lambda: {},
    )
    monkeypatch.setattr(
        "backend.integrations.alpaca_broker.get_alpaca_broker_client", lambda: broker
    )
    await _sync_orders(SimpleNamespace(state=SimpleNamespace(sessionmaker=sessions)))
    async with sessions() as session:
        assert (await session.get(Order, row.id)).filled_qty == 10


@pytest.mark.asyncio
async def test_reconnect_keeps_prior_clock_and_invokes_persisted_recovery(sessions, monkeypatch):
    from backend.integrations import alpaca_stream as stream

    client = stream.AlpacaStreamClient.__new__(stream.AlpacaStreamClient)
    client.api_key, client.api_secret, client.ws_url = (
        "synthetic",
        "synthetic",
        "wss://paper.invalid",
    )
    client._last_connected_at = 1000.0
    client._gap_recovery_anchor = 0.0
    client._authenticate = AsyncMock(return_value=True)
    client._subscribe_to_trade_updates = AsyncMock(return_value=True)
    client._start_background_tasks = AsyncMock()
    monkeypatch.setattr(stream.time, "time", lambda: 10000.0)
    monkeypatch.setattr(stream.websockets, "connect", AsyncMock(return_value=object()))
    assert await client.connect()
    assert client._last_connected_at == 10000 and client._gap_recovery_anchor == 1000
    calls = []
    original = OrdersRepo.get_orders_since

    async def observe(self, cutoff):
        calls.append(cutoff)
        return await original(self, cutoff)

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    recover = AsyncMock(return_value={"attempted": 0})
    monkeypatch.setattr(recovery, "recover_persisted_orders", recover)
    monkeypatch.setattr(stream, "get_session_context", context)
    monkeypatch.setattr(OrdersRepo, "get_orders_since", observe)
    before = datetime.now(UTC)
    await client._gap_fill_after_reconnect()
    assert 3599 <= (before - calls[0]).total_seconds() <= 3601
    assert client._gap_recovery_anchor == 0
    recover.assert_awaited_once_with(context)
