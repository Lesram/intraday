"""Synthetic transactional regressions for broker ACK and fill ordering."""

from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
from sqlalchemy import select

from tests.test_fill_accounting_integrity import make_order, sessions as sessions
from backend.infra.schemas import Order, Execution, PositionLot
from backend.integrations.alpaca_stream import apply_order_fill_snapshot
from backend.infra.outbox_worker import OutboxWorker


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "details", [None, {"filled_qty": "0"}, {"filled_qty": "5", "avg_fill_price": "90"}]
)
async def test_delayed_ack_cannot_overwrite_terminal_fill(sessions, monkeypatch, details):
    row = make_order()
    async with sessions() as session:
        session.add(row)
        await session.flush()
        await apply_order_fill_snapshot(
            session,
            row,
            status="filled",
            cumulative_filled_qty="10",
            avg_fill_price="100",
            broker_order_id=row.broker_order_id,
        )
        await session.commit()

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", context)
    worker = OutboxWorker.__new__(OutboxWorker)
    await worker._update_order_status(str(row.id), "submitted", row.broker_order_id, details)
    async with sessions() as session:
        current = await session.get(Order, row.id)
        executions = list((await session.execute(select(Execution))).scalars())
        lots = list((await session.execute(select(PositionLot))).scalars())
        assert sum(x.fill_qty for x in executions) == Decimal("10")
        assert sum(x.fill_qty * x.fill_price for x in executions) == Decimal("1000")
        assert sum(x.remaining_qty for x in lots) == Decimal("10")
        assert (current.status, current.filled_qty, current.avg_fill_price) == (
            "filled",
            Decimal("10"),
            Decimal("100"),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("pre_filled", [False, True])
async def test_real_alpaca_ack_shape_preserves_or_accounts_fill(sessions, monkeypatch, pre_filled):
    row = make_order()
    async with sessions() as session:
        session.add(row)
        await session.flush()
        if pre_filled:
            await apply_order_fill_snapshot(
                session,
                row,
                status="filled",
                cumulative_filled_qty="10",
                avg_fill_price="100",
                broker_order_id=row.broker_order_id,
            )
        await session.commit()

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", context)
    nested = {
        "id": row.broker_order_id,
        "client_order_id": row.client_idempotency_key,
        "symbol": row.symbol,
        "side": row.side,
        "qty": "10",
        "status": "new" if pre_filled else "filled",
        "filled_qty": "0" if pre_filled else "10",
        "filled_avg_price": None if pre_filled else "100",
    }
    result = {
        "success": True,
        "broker_order_id": row.broker_order_id,
        "status": nested["status"],
        "broker": "alpaca",
        "alpaca_response": nested,
    }
    await OutboxWorker.__new__(OutboxWorker)._update_order_status(
        str(row.id), result["status"], row.broker_order_id, result
    )
    async with sessions() as session:
        current = await session.get(Order, row.id)
        qty = sum(x.fill_qty for x in (await session.execute(select(Execution))).scalars())
        assert (current.status, current.filled_qty, qty) == ("filled", Decimal("10"), Decimal("10"))


def broker_ack(row, *, status="filled", quantity="10", price="100", broker_id=None):
    identity = broker_id or row.broker_order_id
    snapshot = {
        "id": identity,
        "client_order_id": row.client_idempotency_key,
        "symbol": row.symbol,
        "side": row.side,
        "qty": str(row.qty),
        "status": status,
        "filled_qty": quantity,
        "filled_avg_price": price,
    }
    return {
        "success": True,
        "broker": "alpaca",
        "broker_order_id": identity,
        "status": status,
        "alpaca_response": snapshot,
    }


async def attach(sessions, monkeypatch, row, data):
    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", context)
    await OutboxWorker.__new__(OutboxWorker)._update_order_status(
        str(row.id), data["status"], data["broker_order_id"], data
    )


async def seed(sessions, row):
    async with sessions() as session:
        session.add(row)
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["cancelled", "expired"])
async def test_delayed_partial_ack_preserves_terminal_partial(sessions, monkeypatch, terminal):
    row = make_order()
    await seed(sessions, row)
    async with sessions() as session:
        await apply_order_fill_snapshot(
            session,
            row,
            status=terminal,
            cumulative_filled_qty="4",
            avg_fill_price="100",
            broker_order_id=row.broker_order_id,
        )
        await session.commit()
    await attach(
        sessions,
        monkeypatch,
        row,
        broker_ack(row, status="partially_filled", quantity="2", price="90"),
    )
    async with sessions() as session:
        saved = await session.get(Order, row.id)
        assert (saved.status, saved.filled_qty, saved.avg_fill_price) == (
            terminal,
            Decimal(4),
            Decimal(100),
        )
        assert (await session.execute(select(Execution.fill_qty))).scalar_one() == 4


@pytest.mark.asyncio
async def test_first_ack_then_stream_fill_and_duplicate_ack_account_once(sessions, monkeypatch):
    row = make_order()
    broker_id = row.broker_order_id
    row.broker_order_id = None
    await seed(sessions, row)
    await attach(
        sessions,
        monkeypatch,
        row,
        broker_ack(row, status="new", quantity="0", price=None, broker_id=broker_id),
    )
    async with sessions() as session:
        saved = await session.get(Order, row.id)
        assert saved.status == "submitted" and saved.broker_order_id == broker_id
        assert not list((await session.execute(select(Execution))).scalars())
        await apply_order_fill_snapshot(
            session,
            saved,
            status="filled",
            cumulative_filled_qty="10",
            avg_fill_price="100",
            broker_order_id=broker_id,
        )
        await session.commit()
    for _ in range(2):
        await attach(sessions, monkeypatch, row, broker_ack(row, broker_id=broker_id))
    async with sessions() as session:
        assert len(list((await session.execute(select(Execution))).scalars())) == 1
        assert len(list((await session.execute(select(PositionLot))).scalars())) == 1


@pytest.mark.asyncio
async def test_first_sell_ack_and_duplicates_realize_and_audit_once(sessions, monkeypatch):
    from backend.infra.schemas import AuditLog, RealizedTrade

    buy, sell = make_order(), make_order("sell")
    await seed(sessions, buy)
    await seed(sessions, sell)
    await attach(sessions, monkeypatch, buy, broker_ack(buy))
    for _ in range(2):
        await attach(sessions, monkeypatch, sell, broker_ack(sell, price="110"))
    async with sessions() as session:
        assert len(list((await session.execute(select(Execution))).scalars())) == 2
        assert (
            sum(x.realized_pnl for x in (await session.execute(select(RealizedTrade))).scalars())
            == 100
        )
        assert len(list((await session.execute(select(AuditLog))).scalars())) == 1
        assert (await session.execute(select(PositionLot.remaining_qty))).scalar_one() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "unrelated"),
        ("client_order_id", "unrelated"),
        ("symbol", "OTHER"),
        ("side", "sell"),
        ("qty", "11"),
        ("filled_qty", "NaN"),
        ("filled_qty", "11"),
        ("filled_qty", True),
        ("filled_avg_price", "Infinity"),
        ("filled_avg_price", None),
        ("status", "replaced"),
    ],
)
async def test_unverified_real_ack_rolls_back(sessions, monkeypatch, field, value):
    row = make_order()
    await seed(sessions, row)
    data = broker_ack(row)
    data["alpaca_response"][field] = value
    with pytest.raises((ValueError, TypeError)):
        await attach(sessions, monkeypatch, row, data)
    async with sessions() as session:
        saved = await session.get(Order, row.id)
        assert saved.status == "accepted" and saved.filled_qty == 0
        assert not list((await session.execute(select(Execution))).scalars())
        assert saved.attributes == row.attributes


@pytest.mark.asyncio
async def test_broker_identity_cannot_be_reassigned(sessions, monkeypatch):
    import uuid

    row = make_order()
    await seed(sessions, row)
    with pytest.raises(ValueError, match="identity changed"):
        await attach(sessions, monkeypatch, row, broker_ack(row, broker_id=str(uuid.uuid4())))
    async with sessions() as session:
        assert (await session.get(Order, row.id)).broker_order_id == row.broker_order_id


@pytest.mark.asyncio
async def test_equal_quantity_cash_correction_remains_explicit(sessions, monkeypatch):
    row = make_order()
    await seed(sessions, row)
    await attach(sessions, monkeypatch, row, broker_ack(row))
    with pytest.raises(ValueError):
        await attach(sessions, monkeypatch, row, broker_ack(row, price="101"))
    async with sessions() as session:
        assert (await session.get(Order, row.id)).avg_fill_price == 100
        assert (await session.execute(select(Execution.fill_price))).scalar_one() == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["lot", "commit"])
async def test_failed_ack_transaction_rolls_back_then_retries_once(sessions, monkeypatch, failure):
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.services.lot_tracker_service import LotTracker
    from unittest.mock import AsyncMock

    row = make_order()
    await seed(sessions, row)
    owner, method = (LotTracker, "create_lot") if failure == "lot" else (AsyncSession, "commit")
    original = getattr(owner, method)
    monkeypatch.setattr(owner, method, AsyncMock(side_effect=RuntimeError("synthetic rollback")))
    with pytest.raises(RuntimeError, match="synthetic rollback"):
        await attach(sessions, monkeypatch, row, broker_ack(row))
    async with sessions() as session:
        saved = await session.get(Order, row.id)
        assert saved.status == "accepted" and saved.filled_qty == 0
        assert not list((await session.execute(select(Execution))).scalars())
        assert not list((await session.execute(select(PositionLot))).scalars())
    monkeypatch.setattr(owner, method, original)
    await attach(sessions, monkeypatch, row, broker_ack(row))
    async with sessions() as session:
        assert (await session.execute(select(Execution.fill_qty))).scalar_one() == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["shadow", "mock", "dry_run"])
async def test_non_alpaca_first_ack_preserves_existing_mode(sessions, monkeypatch, mode):
    row = make_order()
    row.broker_order_id = None
    await seed(sessions, row)
    data = {
        "broker": mode,
        "status": "shadow" if mode == "shadow" else "accepted",
        "broker_order_id": None if mode == "shadow" else "MOCK_SYNTH",
    }
    await attach(sessions, monkeypatch, row, data)
    async with sessions() as session:
        saved = await session.get(Order, row.id)
        assert saved.status == data["status"] and saved.broker_order_id == data["broker_order_id"]
        assert not list((await session.execute(select(Execution))).scalars())


@pytest.mark.asyncio
@pytest.mark.parametrize("details", [None, {"filled_qty": "4", "avg_fill_price": "100"}])
async def test_partial_fill_is_not_demoted_by_ack_without_new_fill(sessions, monkeypatch, details):
    row = make_order()
    await seed(sessions, row)
    async with sessions() as session:
        await apply_order_fill_snapshot(
            session,
            row,
            status="partially_filled",
            cumulative_filled_qty="4",
            avg_fill_price="100",
            broker_order_id=row.broker_order_id,
        )
        await session.commit()

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", context)
    await OutboxWorker.__new__(OutboxWorker)._update_order_status(
        str(row.id), "accepted", None, details
    )
    async with sessions() as session:
        saved = await session.get(Order, row.id)
        assert (saved.status, saved.filled_qty) == ("partially_filled", Decimal(4))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["mock", "dry_run", "shadow", "none"])
async def test_synthetic_ack_cannot_relabel_real_broker_identity(sessions, monkeypatch, mode):
    row = make_order()
    await seed(sessions, row)
    with pytest.raises(ValueError, match="Synthetic acknowledgement"):
        await attach(
            sessions,
            monkeypatch,
            row,
            {"broker": mode, "status": "shadow", "broker_order_id": None},
        )
    async with sessions() as session:
        saved = await session.get(Order, row.id)
        assert saved.status == "accepted" and saved.broker_order_id == row.broker_order_id


@pytest.mark.asyncio
@pytest.mark.parametrize("recovers", [True, False])
async def test_known_real_ack_persistence_failure_restarts_lookup_only(
    sessions, monkeypatch, recovers
):
    from datetime import UTC, datetime, timedelta
    from unittest.mock import AsyncMock
    import httpx
    import uuid
    from backend.infra.schemas import OutboxEvent
    from backend.services.lot_tracker_service import LotTracker
    from tests.test_broker_ack_reconciliation import broker_with, marker, process_one, wired_worker

    async with sessions() as session:
        await session.run_sync(lambda sync: OutboxEvent.__table__.create(sync.get_bind()))
        await session.commit()
    row = make_order()
    await seed(sessions, row)
    response = broker_ack(row)["alpaca_response"]
    broker = broker_with(httpx.Response(201, json=response), httpx.Response(200, json=response))
    event_id = uuid.uuid4()
    async with sessions() as session:
        session.add(
            OutboxEvent(
                id=event_id,
                topic="order.submitted",
                status="pending",
                attempts=0,
                next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
                payload={
                    "order_id": str(row.id),
                    "symbol": row.symbol,
                    "side": row.side,
                    "qty": "10",
                    "order_type": "market",
                    "client_key": row.client_idempotency_key,
                },
            )
        )
        await session.commit()

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", context)
    original = LotTracker.create_lot
    monkeypatch.setattr(
        LotTracker,
        "create_lot",
        AsyncMock(side_effect=RuntimeError("synthetic persistence failure")),
    )
    worker, _ = wired_worker(sessions, monkeypatch, broker, retries=1)
    del worker._update_order_status  # Exercise actual updater and wrapper, not a fake success.
    await process_one(worker)
    async with sessions() as session:
        pending = await session.get(OutboxEvent, event_id)
        assert pending.status == "pending" and pending.last_error == marker(
            row.client_idempotency_key
        )
        assert (await session.get(Order, row.id)).filled_qty == 0
        assert not list((await session.execute(select(Execution))).scalars())
    if recovers:
        monkeypatch.setattr(LotTracker, "create_lot", original)
    restarted, notices = wired_worker(sessions, monkeypatch, broker, retries=1)
    del restarted._update_order_status
    await process_one(restarted)
    async with sessions() as session:
        event = await session.get(OutboxEvent, event_id)
        saved = await session.get(Order, row.id)
        if recovers:
            assert event.status == "sent" and saved.status == "filled" and saved.filled_qty == 10
            assert (await session.execute(select(Execution.fill_qty))).scalar_one() == 10
        else:
            assert event.status == "failed" and event.last_error == marker(
                row.client_idempotency_key
            )
            assert saved.status == "accepted" and saved.filled_qty == 0
            assert notices.await_args.args[1]["type"] == "order.reconciliation_required"
    calls = broker._make_request_with_retry.await_args_list
    assert [call.args[0] for call in calls] == ["POST", "GET"]
    assert calls[1].kwargs == {"params": {"client_order_id": row.client_idempotency_key}}


@pytest.mark.asyncio
async def test_mark_sent_commit_failure_after_real_fill_preserves_lookup_only(
    sessions, monkeypatch
):
    from datetime import UTC, datetime, timedelta
    import httpx
    import uuid
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.infra.outbox import OutboxRepo
    from backend.infra.schemas import OutboxEvent
    from tests.test_broker_ack_reconciliation import broker_with, marker, process_one, wired_worker

    async with sessions() as session:
        await session.run_sync(lambda sync: OutboxEvent.__table__.create(sync.get_bind()))
        await session.commit()
    row = make_order()
    await seed(sessions, row)
    response = broker_ack(row)["alpaca_response"]
    broker = broker_with(httpx.Response(201, json=response), httpx.Response(200, json=response))
    event_id = uuid.uuid4()
    async with sessions() as session:
        session.add(
            OutboxEvent(
                id=event_id,
                topic="order.submitted",
                status="pending",
                attempts=0,
                next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
                payload={
                    "order_id": str(row.id),
                    "symbol": row.symbol,
                    "side": row.side,
                    "qty": "10",
                    "order_type": "market",
                    "client_key": row.client_idempotency_key,
                },
            )
        )
        await session.commit()

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", context)
    original_mark, original_commit = OutboxRepo.mark_sent, AsyncSession.commit

    async def mark(self, *args, **kwargs):
        result = await original_mark(self, *args, **kwargs)
        self.session.info["fail_mark_sent"] = True
        return result

    async def commit(self):
        if self.info.get("fail_mark_sent"):
            raise RuntimeError("synthetic sent commit failure")
        await original_commit(self)

    monkeypatch.setattr(OutboxRepo, "mark_sent", mark)
    monkeypatch.setattr(AsyncSession, "commit", commit)
    worker, _ = wired_worker(sessions, monkeypatch, broker)
    del worker._update_order_status
    await process_one(worker)
    async with sessions() as session:
        event = await session.get(OutboxEvent, event_id)
        assert event.status == "pending" and event.last_error == marker(row.client_idempotency_key)
        assert (await session.get(Order, row.id)).filled_qty == 10
    monkeypatch.setattr(OutboxRepo, "mark_sent", original_mark)
    monkeypatch.setattr(AsyncSession, "commit", original_commit)
    restarted, _ = wired_worker(sessions, monkeypatch, broker)
    del restarted._update_order_status
    await process_one(restarted)
    async with sessions() as session:
        assert (await session.get(OutboxEvent, event_id)).status == "sent"
        assert len(list((await session.execute(select(Execution))).scalars())) == 1
    assert [call.args[0] for call in broker._make_request_with_retry.await_args_list] == [
        "POST",
        "GET",
    ]
