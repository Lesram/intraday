"""Opt-in PostgreSQL contention proof, using only a dedicated disposable database.

Ordinary pytest visibly skips the database cases. The isolated runner supplies
INTRA_FILL_TEST_DATABASE_URL; DATABASE_URL never authorizes these tests.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from backend.infra.repositories.orders import OrdersRepo
from backend.infra.schemas import (
    AuditLog,
    Execution,
    Order,
    OutboxEvent,
    PositionLot,
    RealizedTrade,
)
from backend.integrations import alpaca_stream as stream
from backend.integrations.alpaca_stream import apply_order_fill_snapshot
from backend.services.order_recovery_service import OrderRecoveryService


def dedicated_url(value):
    """Reject application databases, arbitrary hosts and URL option injection."""
    try:
        url = make_url(value)
    except Exception:
        raise ValueError("Invalid dedicated fill-test database URL") from None
    if (
        url.drivername != "postgresql+asyncpg"
        or url.host != "intra-fill-postgres"
        or url.port not in (None, 5432)
        or url.database != "test_fill_accounting"
        or url.username != "test_fill_accounting"
        or not url.password
        or url.query
    ):
        raise ValueError("Refusing non-dedicated fill-test database URL")
    return url


@pytest.mark.parametrize(
    "value",
    [
        "postgresql+asyncpg://app:synthetic@intra-fill-postgres/test_fill_accounting",
        "postgresql+asyncpg://test_fill_accounting:synthetic@localhost/test_fill_accounting",
        "postgresql+asyncpg://test_fill_accounting:synthetic@intra-fill-postgres/production",
        "postgresql+asyncpg://test_fill_accounting:synthetic@intra-fill-postgres/test_fill_accounting?ssl=disable",
        "not-a-database-url",
    ],
)
def test_refuses_non_dedicated_database(value):
    with pytest.raises(ValueError):
        dedicated_url(value)


@pytest.fixture
async def pg_sessions():
    value = os.environ.get("INTRA_FILL_TEST_DATABASE_URL")
    if not value:
        pytest.skip("Dedicated disposable PostgreSQL not supplied (INTRA_FILL_TEST_DATABASE_URL)")
    url = dedicated_url(value)
    schema = "fill_case_" + uuid.uuid4().hex
    admin = create_async_engine(url, connect_args={"timeout": 5})
    engine = None
    try:
        async with admin.begin() as conn:
            assert (
                await conn.execute(text("SELECT current_database()"))
            ).scalar_one() == "test_fill_accounting"
            assert (
                await conn.execute(text("SELECT current_user"))
            ).scalar_one() == "test_fill_accounting"
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(
            url,
            pool_size=2,
            max_overflow=0,
            connect_args={
                "timeout": 5,
                "server_settings": {
                    "search_path": schema,
                    "statement_timeout": "5000",
                    "lock_timeout": "4000",
                    "idle_in_transaction_session_timeout": "10000",
                },
            },
        )
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
        yield sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        if engine is not None:
            await engine.dispose()
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await admin.dispose()


def order(side="buy"):
    return Order(
        id=uuid.uuid4(),
        user_id="synthetic",
        client_idempotency_key=str(uuid.uuid4()),
        symbol="SYNTH",
        side=side,
        qty=Decimal(10),
        order_type="market",
        tif="day",
        status="accepted",
        filled_qty=Decimal(0),
        broker_order_id=str(uuid.uuid4()),
        submitted_at=datetime.now(UTC),
        attributes={"user_id": "synthetic"},
    )


async def snapshot(session, item, quantity, price, status="filled"):
    return await apply_order_fill_snapshot(
        session, item, status=status, cumulative_filled_qty=str(quantity), avg_fill_price=str(price)
    )


async def contend(factory, identity, *, first, second, rollback=False):
    """Prove a real lock wait via PostgreSQL, then release the first transaction."""
    async with factory() as one, factory() as two:
        item_one = await one.get(Order, identity)
        # Preload an old ORM summary; populate_existing must refresh it after wait.
        item_two = await two.get(Order, identity)
        first_pid = (await one.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        second_pid = (await two.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        assert first_pid != second_pid
        first_result = await snapshot(one, item_one, *first)
        task = asyncio.create_task(snapshot(two, item_two, *second))
        try:
            deadline = asyncio.get_running_loop().time() + 2
            while True:
                blockers = (
                    await one.execute(text("SELECT pg_blocking_pids(:pid)"), {"pid": second_pid})
                ).scalar_one()
                if first_pid in blockers:
                    break
                assert not task.done(), "Second writer bypassed the first order lock"
                assert asyncio.get_running_loop().time() < deadline, (
                    "No PostgreSQL lock wait observed"
                )
                await asyncio.sleep(0.01)
            assert not task.done()
            if rollback:
                await one.rollback()
            else:
                await one.commit()
            second_result = await asyncio.wait_for(task, timeout=5)
            await two.commit()
            return first_result, second_result
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await one.rollback()
            await two.rollback()


async def seed(factory, side="buy"):
    async with factory() as session:
        item = order(side)
        session.add(item)
        await session.commit()
        return item.id


@pytest.mark.asyncio
async def test_same_order_lock_and_duplicate_fill_are_idempotent(pg_sessions):
    identity = await seed(pg_sessions)
    first, second = await contend(pg_sessions, identity, first=(10, 100), second=(10, 100))
    assert first["applied"] and not second["applied"]
    async with pg_sessions() as session:
        execution = (await session.execute(select(Execution))).scalar_one()
        lot = (await session.execute(select(PositionLot))).scalar_one()
        saved = await session.get(Order, identity)
        assert (execution.fill_qty, execution.fill_price) == (10, 100)
        assert (lot.qty, lot.remaining_qty, lot.cost_basis) == (10, 10, 100)
        assert (saved.status, saved.filled_qty, saved.avg_fill_price) == ("filled", 10, 100)


@pytest.mark.asyncio
async def test_overlapping_cumulative_fills_refresh_waiting_watermark(pg_sessions):
    identity = await seed(pg_sessions)
    first, second = await contend(
        pg_sessions, identity, first=(4, 100, "partially_filled"), second=(10, 112)
    )
    assert Decimal(first["incremental_qty"]) == 4 and Decimal(second["incremental_qty"]) == 6
    async with pg_sessions() as session:
        executions = list((await session.execute(select(Execution))).scalars())
        lots = list((await session.execute(select(PositionLot))).scalars())
        assert sorted((x.fill_qty, x.fill_price) for x in executions) == [(4, 100), (6, 120)]
        assert sum(x.fill_qty * x.fill_price for x in executions) == 1120
        assert sum(x.remaining_qty * x.cost_basis for x in lots) == 1120
        saved = await session.get(Order, identity)
        assert (saved.filled_qty, saved.avg_fill_price, saved.status) == (10, 112, "filled")


@pytest.mark.asyncio
async def test_rollback_releases_lock_without_leaving_execution_or_lot_watermark(pg_sessions):
    identity = await seed(pg_sessions)
    _, second = await contend(
        pg_sessions, identity, first=(4, 100, "partially_filled"), second=(10, 112), rollback=True
    )
    assert Decimal(second["incremental_qty"]) == 10
    async with pg_sessions() as session:
        execution = (await session.execute(select(Execution))).scalar_one()
        lot = (await session.execute(select(PositionLot))).scalar_one()
        assert (execution.fill_qty, execution.fill_price) == (10, 112)
        assert (lot.qty, lot.remaining_qty, lot.cost_basis) == (10, 10, 112)
        saved = await session.get(Order, identity)
        assert (saved.filled_qty, saved.status) == (10, "filled")


@pytest.mark.asyncio
async def test_concurrent_duplicate_exit_closes_lots_and_audits_once(pg_sessions):
    buy = await seed(pg_sessions)
    async with pg_sessions() as session:
        await snapshot(session, await session.get(Order, buy), 10, 100)
        await session.commit()
    sell = await seed(pg_sessions, "sell")
    first, second = await contend(pg_sessions, sell, first=(10, 110), second=(10, 110))
    assert first["applied"] and not second["applied"]
    async with pg_sessions() as session:
        assert (
            await session.execute(select(Execution).where(Execution.order_id == sell))
        ).scalar_one().fill_qty == 10
        lot = (await session.execute(select(PositionLot))).scalar_one()
        realized = (await session.execute(select(RealizedTrade))).scalar_one()
        audit = (await session.execute(select(AuditLog))).scalar_one()
        assert (lot.remaining_qty, lot.status) == (0, "closed")
        assert (realized.qty, realized.realized_pnl) == (10, 100)
        assert audit.action == "order.filled" and audit.entity_id == str(sell) and audit.hash_chain


@pytest.mark.asyncio
async def test_recovery_lineage_json_and_uuid_keyset_on_postgres(pg_sessions):
    rows = [order() for _ in range(4)]
    for number, item in enumerate(rows, 1):
        item.id = uuid.UUID(f"a0000000-0000-4000-8000-{number:012x}")
        item.created_at = item.updated_at = item.submitted_at = datetime.now(UTC) - timedelta(
            days=10
        )
    rows[0].attributes = {"source": "organism"}
    async with pg_sessions() as session:
        session.add_all(rows)
        session.add(
            OutboxEvent(
                topic="order.submitted",
                status="sent",
                payload={
                    "order_id": str(rows[1].id),
                    "client_key": rows[1].client_idempotency_key,
                },
            )
        )
        session.add(
            OutboxEvent(
                topic="order.submitted",
                status="sent",
                payload={
                    "order_id": str(rows[2].id),
                    "client_key": "wrong-key",
                },
            )
        )
        await session.commit()
    async with pg_sessions() as session:
        repo = OrdersRepo(session)
        first = await repo.get_recovery_orders_page(limit=1)
        second = await repo.get_recovery_orders_page(after_id=first[0].id, limit=1)
        assert [row.id for row in first + second] == [rows[0].id, rows[1].id]
        assert await repo.get_recovery_orders_page(after_id=second[0].id) == []
        assert await repo.lock_recovery_order(rows[2].id) is None
        assert await repo.lock_recovery_order(rows[3].id) is None


@pytest.mark.asyncio
async def test_recovery_waits_for_stream_fill_then_applies_only_increment_on_postgres(
    pg_sessions, monkeypatch
):
    identity = await seed(pg_sessions)
    async with pg_sessions() as session:
        item = await session.get(Order, identity)
        item.attributes = {"source": "organism"}
        await session.commit()
        broker_snapshot = {
            "id": item.broker_order_id,
            "client_order_id": item.client_idempotency_key,
            "symbol": item.symbol,
            "side": item.side,
            "qty": "10",
            "status": "filled",
            "filled_qty": "10",
            "filled_avg_price": "112",
        }
    waiting_pid = asyncio.Future()
    original_lock = OrdersRepo.lock_recovery_order

    async def observed_lock(repo, order_id):
        waiting_pid.set_result(
            (await repo.session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        )
        return await original_lock(repo, order_id)

    monkeypatch.setattr(OrdersRepo, "lock_recovery_order", observed_lock)

    async def fetch(broker_id):
        assert broker_id == broker_snapshot["id"]
        return broker_snapshot

    async with pg_sessions() as stream_session:
        first_pid = (await stream_session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        await snapshot(
            stream_session, await stream_session.get(Order, identity), 4, 100, "partially_filled"
        )
        task = asyncio.create_task(OrderRecoveryService().recover(pg_sessions, fetch))
        try:
            second_pid = await asyncio.wait_for(waiting_pid, timeout=2)
            assert second_pid != first_pid
            deadline = asyncio.get_running_loop().time() + 2
            while (
                first_pid
                not in (
                    await stream_session.execute(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": second_pid}
                    )
                ).scalar_one()
            ):
                assert not task.done()
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.01)
            await stream_session.commit()
            result = await asyncio.wait_for(task, timeout=5)
            assert result["reconciled"] == result["applied"] == 1 and result["errors"] == 0
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await stream_session.rollback()
    async with pg_sessions() as session:
        executions = list((await session.execute(select(Execution))).scalars())
        lots = list((await session.execute(select(PositionLot))).scalars())
        assert sorted((x.fill_qty, x.fill_price) for x in executions) == [(4, 100), (6, 120)]
        assert sum(x.remaining_qty * x.cost_basis for x in lots) == 1120
        saved = await session.get(Order, identity)
        assert (saved.status, saved.filled_qty, saved.avg_fill_price) == ("filled", 10, 112)


@pytest.mark.asyncio
async def test_real_ack_waits_for_stream_fill_then_late_ack_preserves_terminal_on_postgres(
    pg_sessions, monkeypatch
):
    from backend.infra.outbox_worker import OutboxWorker

    identity = await seed(pg_sessions)
    async with pg_sessions() as session:
        item = await session.get(Order, identity)
        broker_id = item.broker_order_id
        details = {
            "broker": "alpaca",
            "status": "filled",
            "broker_order_id": broker_id,
            "alpaca_response": {
                "id": broker_id,
                "client_order_id": item.client_idempotency_key,
                "symbol": item.symbol,
                "side": item.side,
                "qty": "10",
                "status": "filled",
                "filled_qty": "10",
                "filled_avg_price": "112",
            },
        }
    waiting_pid = asyncio.Future()

    @asynccontextmanager
    async def worker_session():
        async with pg_sessions() as session:
            pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            if not waiting_pid.done():
                waiting_pid.set_result(pid)
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", worker_session)
    worker = OutboxWorker.__new__(OutboxWorker)
    async with pg_sessions() as stream_session:
        first_pid = (await stream_session.execute(text("SELECT pg_backend_pid()"))).scalar_one()
        await snapshot(
            stream_session, await stream_session.get(Order, identity), 4, 100, "partially_filled"
        )
        task = asyncio.create_task(
            worker._update_order_status(str(identity), "filled", broker_id, details)
        )
        try:
            second_pid = await asyncio.wait_for(waiting_pid, timeout=2)
            assert second_pid != first_pid
            deadline = asyncio.get_running_loop().time() + 2
            while (
                first_pid
                not in (
                    await stream_session.execute(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": second_pid}
                    )
                ).scalar_one()
            ):
                assert not task.done(), "Acknowledgement bypassed active stream order lock"
                assert asyncio.get_running_loop().time() < deadline
                await asyncio.sleep(0.01)
            await stream_session.commit()
            await asyncio.wait_for(task, timeout=5)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await stream_session.rollback()
    late = {
        **details,
        "status": "new",
        "alpaca_response": {
            **details["alpaca_response"],
            "status": "new",
            "filled_qty": "0",
            "filled_avg_price": None,
        },
    }
    await worker._update_order_status(str(identity), "new", broker_id, late)
    async with pg_sessions() as session:
        executions = list((await session.execute(select(Execution))).scalars())
        lots = list((await session.execute(select(PositionLot))).scalars())
        assert sorted((x.fill_qty, x.fill_price) for x in executions) == [(4, 100), (6, 120)]
        assert sum(x.remaining_qty * x.cost_basis for x in lots) == 1120
        saved = await session.get(Order, identity)
        assert (saved.status, saved.filled_qty, saved.avg_fill_price) == ("filled", 10, 112)


# ── C07-01 review: concurrent ingestion of an opening and its close ─────────


def leg(side, qty, at, *, source=None, status="accepted"):
    """One leg of a synthetic round trip (owner 'synthetic'); ``source`` puts it
    in persisted-order recovery's scope."""
    attributes = {"user_id": "synthetic"}
    if source:
        attributes["source"] = source
    return Order(
        id=uuid.uuid4(),
        user_id="synthetic",
        client_idempotency_key=str(uuid.uuid4()),
        symbol="SYNTH",
        side=side,
        qty=Decimal(qty),
        order_type="market",
        tif="day",
        status=status,
        filled_qty=Decimal(0),
        broker_order_id=str(uuid.uuid4()),
        submitted_at=at,
        created_at=at,
        updated_at=at,
        attributes=attributes,
    )


async def seed_rows(factory, *rows):
    async with factory() as session:
        session.add_all(rows)
        await session.commit()


async def backend_pid(session):
    return (await session.execute(text("SELECT pg_backend_pid()"))).scalar_one()


async def wait_blocked(executor, waiter, holder, task, message):
    """Return once PostgreSQL reports ``waiter`` blocked by ``holder``."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 3
    while holder not in (
        await executor.execute(text("SELECT pg_blocking_pids(:pid)"), {"pid": waiter})
    ).scalar_one():
        assert not task.done(), message
        assert loop.time() < deadline, message
        await asyncio.sleep(0.01)


@asynccontextmanager
async def lock_monitor(factory):
    """A third connection that only reads lock state (the fixture pool holds two)."""
    engine = create_async_engine(
        factory.kw["bind"].url, poolclass=NullPool, connect_args={"timeout": 5}
    )
    try:
        async with engine.connect() as connection:
            yield connection
    finally:
        await engine.dispose()


async def settle(*tasks):
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def round_trip_state(factory, close_id):
    async with factory() as session:
        close = await session.get(Order, close_id)
        lots = list((await session.execute(select(PositionLot))).scalars())
        realized = list((await session.execute(select(RealizedTrade))).scalars())
        return close, lots, realized


@pytest.mark.parametrize("first", ["close", "opening"])
@pytest.mark.asyncio
async def test_concurrent_opening_and_close_fills_converge_on_postgres(pg_sessions, first):
    """An opening outside recovery scope and its close are ingested at the same
    moment on two paths. Whichever transaction locks the close row first, the
    other waits for its commit: the opening's netting then nets the close's
    committed unmatched record, or the close's FIFO consumes the opening's lot.
    No phantom open lot or unmatched record is left (review race, case a)."""
    t0 = datetime.now(UTC) - timedelta(minutes=30)
    opening = leg("buy", 6, t0)
    close = leg("sell", 6, t0 + timedelta(minutes=10), source="organism")
    await seed_rows(pg_sessions, opening, close)
    legs = {"opening": (opening, 100), "close": (close, 101)}
    second = "opening" if first == "close" else "close"
    async with pg_sessions() as one, pg_sessions() as two:
        one_pid, two_pid = await backend_pid(one), await backend_pid(two)
        row, price = legs[first]
        await snapshot(one, await one.get(Order, row.id), 6, price)  # staged; row locks held
        row, price = legs[second]
        task = asyncio.create_task(snapshot(two, await two.get(Order, row.id), 6, price))
        try:
            await wait_blocked(one, two_pid, one_pid, task, f"The {second} did not wait for the {first}")
            await one.commit()
            second_result = await asyncio.wait_for(task, timeout=5)
            await two.commit()
        finally:
            await settle(task)
            await one.rollback()
            await two.rollback()
    saved, lots, realized = await round_trip_state(pg_sessions, close.id)
    assert (saved.status, saved.filled_qty) == ("filled", 6)
    assert [(lot.order_id, lot.remaining_qty, lot.status) for lot in lots] == [(opening.id, 0, "closed")]
    assert [(x.open_order_id, x.close_order_id, x.qty, x.close_price, x.realized_pnl) for x in realized] == [
        (opening.id, close.id, 6, 101, 6)
    ]
    record = saved.attributes.get("lot_accounting")
    if first == "close":  # recorded unmatched, then netted once the opening's lot landed
        assert len(second_result["lot_late_matches"]) == 1
        assert (record["status"], record["unmatched_qty"], record["matched_late_qty"]) == (
            "matched_late", "0.000000", "6.000000"
        )
    else:  # the close waited for the opening's commit and consumed its lot
        assert record is None and second_result["realized_count"] == 1


@pytest.mark.asyncio
async def test_close_paused_before_its_deferral_check_still_converges_on_postgres(
    pg_sessions, monkeypatch
):
    """Opening in recovery scope: the close found no lot, and the opening's fill
    lands on another path before the close's deferral query. The opening's
    netting waits for the close row, so the close still sees the opening
    unresolved and defers; its retry then consumes the lot (review race, case b)."""
    t0 = datetime.now(UTC) - timedelta(minutes=30)
    opening = leg("buy", 6, t0, source="organism")
    close = leg("sell", 6, t0 + timedelta(minutes=10), source="organism")
    await seed_rows(pg_sessions, opening, close)
    at_check, release = asyncio.Event(), asyncio.Event()
    original = stream._unsettled_earlier_opening

    async def paused_check(session, **kwargs):
        if not at_check.is_set():
            at_check.set()
            await release.wait()
        return await original(session, **kwargs)

    monkeypatch.setattr(stream, "_unsettled_earlier_opening", paused_check)
    close_pid, outcome = [], []

    async def close_tx():
        async with pg_sessions() as session:
            close_pid.append(await backend_pid(session))
            try:
                await snapshot(session, await session.get(Order, close.id), 6, 101)
                await session.commit()
                outcome.append("committed")
            except stream.LotAccountingDeferred:
                await session.rollback()
                outcome.append("deferred")

    close_task = asyncio.create_task(close_tx())
    await asyncio.wait_for(at_check.wait(), timeout=5)
    async with lock_monitor(pg_sessions) as watch, pg_sessions() as session:
        opening_pid = await backend_pid(session)
        opening_task = asyncio.create_task(
            snapshot(session, await session.get(Order, opening.id), 6, 100)
        )
        try:
            await wait_blocked(
                watch, opening_pid, close_pid[0], opening_task,
                "The opening's netting did not wait for the close row",
            )
            release.set()
            await asyncio.wait_for(close_task, timeout=5)
            opened = await asyncio.wait_for(opening_task, timeout=5)
            await session.commit()
        finally:
            release.set()
            await settle(opening_task, close_task)
            await session.rollback()
    assert outcome == ["deferred"] and "lot_late_matches" not in opened
    async with pg_sessions() as session:  # the close's retry, as any ingress retries it
        await snapshot(session, await session.get(Order, close.id), 6, 101)
        await session.commit()
    saved, lots, realized = await round_trip_state(pg_sessions, close.id)
    assert (saved.status, saved.filled_qty) == ("filled", 6)
    assert "lot_accounting" not in saved.attributes
    assert [(lot.order_id, lot.remaining_qty, lot.status) for lot in lots] == [(opening.id, 0, "closed")]
    assert [(x.open_order_id, x.qty, x.realized_pnl) for x in realized] == [(opening.id, 6, 6)]


@pytest.mark.asyncio
async def test_two_openings_racing_for_one_recorded_close_net_it_once_on_postgres(pg_sessions):
    """Concurrent netting: the second opening waits on the close row, re-reads
    the record the first committed (matched_late) and nets nothing."""
    t0 = datetime.now(UTC) - timedelta(minutes=30)
    first = leg("buy", 6, t0)
    second = leg("buy", 6, t0 + timedelta(minutes=1))
    close = leg("sell", 6, t0 + timedelta(minutes=10), source="organism")
    await seed_rows(pg_sessions, first, second, close)
    async with pg_sessions() as session:
        recorded = await snapshot(session, await session.get(Order, close.id), 6, 101)
        await session.commit()
    assert recorded["lot_discrepancy"]["unmatched_qty"] == "6"
    async with pg_sessions() as one, pg_sessions() as two:
        one_pid, two_pid = await backend_pid(one), await backend_pid(two)
        netted = await snapshot(one, await one.get(Order, first.id), 6, 100)
        task = asyncio.create_task(snapshot(two, await two.get(Order, second.id), 6, 99))
        try:
            await wait_blocked(one, two_pid, one_pid, task, "The second opening did not wait")
            await one.commit()
            late = await asyncio.wait_for(task, timeout=5)
            await two.commit()
        finally:
            await settle(task)
            await one.rollback()
            await two.rollback()
    assert len(netted["lot_late_matches"]) == 1 and "lot_late_matches" not in late
    saved, lots, realized = await round_trip_state(pg_sessions, close.id)
    record = saved.attributes["lot_accounting"]
    assert (record["status"], record["matched_late_qty"], record["late_matches"]) == (
        "matched_late", "6.000000", 1
    )
    assert sorted((lot.order_id == first.id, lot.remaining_qty, lot.status) for lot in lots) == [
        (False, 6, "open"), (True, 0, "closed")
    ]
    assert [(x.open_order_id, x.qty, x.close_price) for x in realized] == [(first.id, 6, 101)]


@pytest.mark.parametrize("ingress", ["snapshot", "recovery", "outbox"])
@pytest.mark.asyncio
async def test_close_fifo_and_opening_netting_do_not_deadlock_on_postgres(
    pg_sessions, monkeypatch, ingress
):
    """The opening's next partial fill and its close arrive together. The close
    FIFO-consumes the opening's earlier lot while the opening's netting waits
    for the close row. Order rows are locked FOR NO KEY UPDATE on every fill
    path (snapshot, persisted-order recovery, outbox acknowledgement) and the
    FIFO locks lot rows only, so the RealizedTrade foreign-key check on the
    opening row does not wait for the opening: both commit, no deadlock."""
    from backend.infra.outbox_worker import OutboxWorker

    t0 = datetime.now(UTC) - timedelta(minutes=30)
    opening = leg("buy", 10, t0, source="organism")
    close = leg("sell", 4, t0 + timedelta(minutes=10))  # outside recovery scope
    await seed_rows(pg_sessions, opening, close)
    async with pg_sessions() as session:  # the opening's earlier partial fill: lot of 4
        await snapshot(session, await session.get(Order, opening.id), 4, 100, "partially_filled")
        await session.commit()
    at_fifo, release = asyncio.Event(), asyncio.Event()
    original_fifo = stream._close_position_lots_fifo

    async def paused_fifo(session, **kwargs):
        at_fifo.set()
        await release.wait()
        return await original_fifo(session, **kwargs)

    monkeypatch.setattr(stream, "_close_position_lots_fifo", paused_fifo)
    close_pid = []

    async def close_tx():
        async with pg_sessions() as session:
            close_pid.append(await backend_pid(session))
            result = await snapshot(session, await session.get(Order, close.id), 4, 101)
            await session.commit()
            return result

    opening_pid = asyncio.get_running_loop().create_future()
    broker = {
        "id": opening.broker_order_id,
        "client_order_id": opening.client_idempotency_key,
        "symbol": "SYNTH",
        "side": "buy",
        "qty": "10",
        "status": "partially_filled",
        "filled_qty": "8",
        "filled_avg_price": "100",
    }

    async def ingest_opening():
        if ingress == "snapshot":
            async with pg_sessions() as session:
                opening_pid.set_result(await backend_pid(session))
                await snapshot(session, await session.get(Order, opening.id), 8, 100, "partially_filled")
                await session.commit()
        elif ingress == "recovery":
            original_lock = OrdersRepo.lock_recovery_order

            async def observed_lock(repo, order_id):
                opening_pid.set_result(await backend_pid(repo.session))
                return await original_lock(repo, order_id)

            monkeypatch.setattr(OrdersRepo, "lock_recovery_order", observed_lock)

            async def fetch(broker_id):
                assert broker_id == broker["id"]
                return broker

            result = await OrderRecoveryService().recover(pg_sessions, fetch)
            assert (result["errors"], result["applied"]) == (0, 1)
        else:
            @asynccontextmanager
            async def worker_session():
                async with pg_sessions() as session:
                    opening_pid.set_result(await backend_pid(session))
                    yield session

            monkeypatch.setattr("backend.infra.db.get_session_context", worker_session)
            details = {"broker": "alpaca", "status": "partially_filled",
                       "broker_order_id": broker["id"], "alpaca_response": broker}
            await OutboxWorker.__new__(OutboxWorker)._update_order_status(
                str(opening.id), "partially_filled", broker["id"], details
            )

    close_task = asyncio.create_task(close_tx())
    opening_task = None
    try:
        await asyncio.wait_for(at_fifo.wait(), timeout=5)
        opening_task = asyncio.create_task(ingest_opening())
        async with lock_monitor(pg_sessions) as watch:
            waiter = await asyncio.wait_for(opening_pid, timeout=5)
            await wait_blocked(
                watch, waiter, close_pid[0], opening_task,
                "The opening's netting did not wait for the close row",
            )
        release.set()
        closed = await asyncio.wait_for(close_task, timeout=10)
        await asyncio.wait_for(opening_task, timeout=10)
    finally:
        release.set()
        await settle(*(t for t in (close_task, opening_task) if t is not None))
    assert closed["realized_count"] == 1 and "lot_discrepancy" not in closed
    async with pg_sessions() as session:
        lots = sorted(
            (lot.qty, lot.remaining_qty, lot.status)
            for lot in (await session.execute(select(PositionLot))).scalars()
        )
        realized = [(x.qty, x.realized_pnl) for x in (await session.execute(select(RealizedTrade))).scalars()]
        saved_opening = await session.get(Order, opening.id)
        saved_close = await session.get(Order, close.id)
    assert lots == [(4, 0, "closed"), (4, 4, "open")]
    assert realized == [(4, 4)]
    assert (saved_opening.status, saved_opening.filled_qty) == ("partially_filled", 8)
    assert (saved_close.status, saved_close.filled_qty) == ("filled", 4)
    assert "lot_accounting" not in saved_close.attributes
