"""Opt-in PostgreSQL contention proof, using only a dedicated disposable database.

Ordinary pytest visibly skips the database cases. The isolated runner supplies
INTRA_FILL_TEST_DATABASE_URL; DATABASE_URL never authorizes these tests.
"""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
import os
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.infra.schemas import AuditLog, Execution, Order, PositionLot, RealizedTrade
from backend.integrations.alpaca_stream import apply_order_fill_snapshot


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
