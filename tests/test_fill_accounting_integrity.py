"""Synthetic transactional regressions; no broker/network or saved model state."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.infra.schemas import AuditLog, Execution, Order, PositionLot, RealizedTrade
from backend.integrations import alpaca_stream as stream


@pytest.fixture
async def sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (
            Order.__table__,
            Execution.__table__,
            PositionLot.__table__,
            RealizedTrade.__table__,
            AuditLog.__table__,
        ):
            await connection.run_sync(lambda conn, table=table: table.create(conn))
    try:
        yield sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    finally:
        await engine.dispose()


def make_order(side="buy"):
    return Order(
        id=uuid.uuid4(),
        user_id="fixture",
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
        attributes={"user_id": "fixture"},
    )


async def fill(session, order, previous, quantity, price, status="filled"):
    return await stream.apply_incremental_fill_accounting(
        session,
        order,
        previous_filled_qty=previous,
        cumulative_filled_qty=quantity,
        avg_fill_price=price,
        status=status,
    )


@pytest.mark.asyncio
async def test_partial_buy_cashflow_and_sell_realized_pnl_match_cumulative_average(sessions):
    async with sessions() as session:
        buy, sell = make_order(), make_order("sell")
        session.add_all([buy, sell])
        await session.flush()
        await fill(session, buy, 0, 5, 100, "partially_filled")
        await fill(session, buy, 5, 10, 110)
        await fill(session, sell, 0, 5, 120, "partially_filled")
        await fill(session, sell, 5, 10, 115)
        await session.commit()
        executions = list((await session.execute(select(Execution))).scalars())
        buy_cash = sum(x.fill_qty * x.fill_price for x in executions if x.order_id == buy.id)
        sell_cash = sum(x.fill_qty * x.fill_price for x in executions if x.order_id == sell.id)
        realized = list((await session.execute(select(RealizedTrade))).scalars())
        assert buy_cash == Decimal(1100)
        assert sell_cash == Decimal(1150)
        assert sum(x.realized_pnl for x in realized) == Decimal(50)
        assert all(
            x.remaining_qty == 0 for x in (await session.execute(select(PositionLot))).scalars()
        )


@pytest.mark.asyncio
async def test_precommitted_summary_does_not_hide_missing_execution(sessions):
    async with sessions() as session:
        order = make_order()
        order.filled_qty = Decimal(10)
        order.avg_fill_price = Decimal(100)
        order.status = "filled"
        session.add(order)
        await session.commit()
        outcome = await fill(session, order, 10, 10, 100)
        assert outcome["applied"] is True
        assert (await session.execute(select(Execution.fill_qty))).scalar_one() == 10
        assert (await session.execute(select(PositionLot.remaining_qty))).scalar_one() == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["cancelled", "canceled", "expired"])
async def test_terminal_partial_fill_recovers_missed_partial_event(sessions, terminal):
    async with sessions() as session:
        order = make_order()
        session.add(order)
        await session.flush()
        outcome = await fill(session, order, 0, 4, 100, terminal)
        assert outcome["applied"] is True
        assert (await session.execute(select(Execution.fill_qty))).scalar_one() == 4


@pytest.mark.asyncio
async def test_duplicate_and_lower_cumulative_snapshot_do_not_add_accounting(sessions):
    async with sessions() as session:
        order = make_order()
        session.add(order)
        await session.flush()
        await fill(session, order, 0, 5, 100, "partially_filled")
        duplicate = await fill(session, order, 5, 5, 100, "partially_filled")
        stale = await fill(session, order, 5, 3, 99, "partially_filled")
        assert not duplicate["applied"] and not stale["applied"]
        assert len(list((await session.execute(select(Execution))).scalars())) == 1


@pytest.mark.asyncio
async def test_equal_quantity_cash_correction_requires_reconciliation_without_rewriting_lots(
    sessions,
):
    async with sessions() as session:
        order = make_order()
        session.add(order)
        await session.flush()
        await fill(session, order, 0, 5, 100, "partially_filled")
        await session.commit()
        with pytest.raises(ValueError, match="cashflow"):
            await fill(session, order, 5, 5, 101, "partially_filled")
        assert (await session.execute(select(PositionLot.cost_basis))).scalar_one() == 100


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "quantity,price",
    [(True, 100), ("NaN", 100), ("Infinity", 100), (1, "NaN"), (1, "Infinity"), (1, None)],
)
async def test_invalid_positive_fill_numbers_do_not_reach_accounting(sessions, quantity, price):
    async with sessions() as session:
        order = make_order()
        session.add(order)
        await session.flush()
        with pytest.raises(ValueError):
            await fill(session, order, 0, quantity, price)
        assert not list((await session.execute(select(Execution))).scalars())


@pytest.mark.asyncio
async def test_websocket_lot_failure_rolls_back_summary_and_raises_for_retry(sessions, monkeypatch):
    async with sessions() as session:
        order = make_order()
        session.add(order)
        await session.commit()
        order_id, broker_id, client_id = (
            order.id,
            order.broker_order_id,
            order.client_idempotency_key,
        )

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr(stream, "get_session_context", context)
    monkeypatch.setattr("backend.api.socketio_server.broadcast_order_update", AsyncMock())
    client = stream.AlpacaStreamClient.__new__(stream.AlpacaStreamClient)
    client._terminal_order_ids = set()
    client._sync_positions_after_terminal_fill = AsyncMock()
    event = {
        "data": {
            "event": "fill",
            "order": {
                "id": broker_id,
                "client_order_id": client_id,
                "status": "filled",
                "filled_qty": "10",
                "filled_avg_price": "100",
            },
        }
    }
    from backend.services.lot_tracker_service import LotTracker

    original = LotTracker.create_lot
    monkeypatch.setattr(
        LotTracker, "create_lot", AsyncMock(side_effect=RuntimeError("synthetic lot failure"))
    )
    with pytest.raises(RuntimeError, match="synthetic lot failure"):
        await client._process_trade_update(event)
    async with sessions() as session:
        saved = await session.get(Order, order_id)
        assert saved.status == "accepted" and saved.filled_qty == 0
        assert not list((await session.execute(select(Execution))).scalars())
    monkeypatch.setattr(LotTracker, "create_lot", original)
    await client._process_trade_update(event)
    await client._process_trade_update(event)
    async with sessions() as session:
        saved = await session.get(Order, order_id)
        assert saved.status == "filled" and saved.filled_qty == 10
        assert len(list((await session.execute(select(Execution))).scalars())) == 1
        assert len(list((await session.execute(select(PositionLot))).scalars())) == 1


@pytest.mark.asyncio
async def test_fractional_delta_cashflow_stays_within_storage_rounding_and_retries_idempotently(
    sessions,
):
    async with sessions() as session:
        buy = make_order()
        session.add(buy)
        await session.flush()
        await fill(session, buy, 0, 4, 120, "partially_filled")
        await fill(session, buy, 4, 10, 115)
        await session.commit()
        result = await fill(session, buy, 10, 10, 115)
        assert result["applied"] is False
        rows = list((await session.execute(select(Execution))).scalars())
        assert len(rows) == 2
        assert abs(sum(x.fill_qty * x.fill_price for x in rows) - Decimal(1150)) <= Decimal(
            "0.000006"
        )


async def recovery_ingress(monkeypatch, sessions, rows, ingress):
    """Run the real recovery path, replacing only DB context and HTTP transport."""
    import httpx

    @asynccontextmanager
    async def context():
        async with sessions() as session:
            yield session

    monkeypatch.setattr(stream, "get_session_context", context)
    monkeypatch.setattr("backend.api.socketio_server.broadcast_order_update", AsyncMock())
    if ingress == "startup":
        from backend.api.lifespan import _sync_orders

        broker = SimpleNamespace(
            base_url="https://paper.invalid",
            _get_auth_headers=lambda: {},
            client=SimpleNamespace(get=AsyncMock(return_value=httpx.Response(200, json=rows))),
        )
        monkeypatch.setattr(
            "backend.integrations.alpaca_broker.get_alpaca_broker_client", lambda: broker
        )
        await _sync_orders(SimpleNamespace(state=SimpleNamespace(sessionmaker=sessions)))
    else:

        async def get(url, **kwargs):
            return httpx.Response(200, json=next(x for x in rows if url.endswith(x["id"])))

        http_client = SimpleNamespace(get=get)

        @asynccontextmanager
        async def transport(*args, **kwargs):
            yield http_client

        monkeypatch.setattr(httpx, "AsyncClient", transport)
        client = stream.AlpacaStreamClient.__new__(stream.AlpacaStreamClient)
        client._last_connected_at = 0
        client._terminal_order_ids = set()
        client.api_key, client.api_secret, client.is_paper = "synthetic", "synthetic", True
        await client._gap_fill_after_reconnect()


@pytest.mark.asyncio
@pytest.mark.parametrize("ingress", ["startup", "reconnect"])
@pytest.mark.parametrize("status", ["filled", "canceled"])
async def test_recovery_repairs_identical_summary_and_does_not_double_account(
    sessions, monkeypatch, ingress, status
):
    async with sessions() as session:
        order = make_order()
        order.status = "filled" if status == "filled" else "cancelled"
        order.filled_qty, order.avg_fill_price = Decimal(4), Decimal(100)
        session.add(order)
        await session.commit()
        identity = order.id
        rows = [
            {
                "id": order.broker_order_id,
                "status": status,
                "filled_qty": "4",
                "filled_avg_price": "100",
            }
        ]
    await recovery_ingress(monkeypatch, sessions, rows, ingress)
    await recovery_ingress(monkeypatch, sessions, rows, ingress)
    async with sessions() as session:
        assert (
            await session.execute(select(Execution.fill_qty).where(Execution.order_id == identity))
        ).scalar_one() == 4
        assert (await session.execute(select(PositionLot.remaining_qty))).scalar_one() == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("ingress", ["startup", "reconnect"])
async def test_failed_recovery_rolls_back_whole_order_but_next_order_and_retry_succeed(
    sessions, monkeypatch, ingress
):
    from backend.services.lot_tracker_service import LotTracker

    async with sessions() as session:
        first, second = make_order(), make_order()
        session.add_all([first, second])
        await session.commit()
        identities = [first.id, second.id]
        rows = [
            {
                "id": x.broker_order_id,
                "status": "filled",
                "filled_qty": "10",
                "filled_avg_price": "100",
            }
            for x in (first, second)
        ]
    original = LotTracker.create_lot

    async def fail_first(self, **kwargs):
        if kwargs["order_id"] == identities[0]:
            raise RuntimeError("synthetic lot failure")
        return await original(self, **kwargs)

    monkeypatch.setattr(LotTracker, "create_lot", fail_first)
    await recovery_ingress(monkeypatch, sessions, rows, ingress)
    async with sessions() as session:
        assert (await session.get(Order, identities[0])).filled_qty == 0
        assert (await session.get(Order, identities[1])).filled_qty == 10
        assert len(list((await session.execute(select(Execution))).scalars())) == 1
    monkeypatch.setattr(LotTracker, "create_lot", original)
    await recovery_ingress(monkeypatch, sessions, rows, ingress)
    async with sessions() as session:
        assert len(list((await session.execute(select(Execution))).scalars())) == 2
        assert len(list((await session.execute(select(PositionLot))).scalars())) == 2


@pytest.mark.asyncio
async def test_exit_audit_is_atomic_durable_and_not_duplicated_on_retry(sessions, monkeypatch):
    from backend.services.audit_service import ComplianceAuditService

    async with sessions() as session:
        buy, sell = make_order(), make_order("sell")
        session.add_all([buy, sell])
        await session.flush()
        await fill(session, buy, 0, 10, 100)
        await session.commit()
        sell_id = sell.id
    original = ComplianceAuditService.log
    monkeypatch.setattr(
        ComplianceAuditService,
        "log",
        AsyncMock(side_effect=RuntimeError("synthetic audit failure")),
    )
    async with sessions() as session:
        with pytest.raises(RuntimeError, match="synthetic audit failure"):
            await stream.apply_order_fill_snapshot(
                session,
                await session.get(Order, sell_id),
                status="filled",
                cumulative_filled_qty="10",
                avg_fill_price="110",
            )
        await session.rollback()
    async with sessions() as session:
        assert (await session.get(Order, sell_id)).filled_qty == 0
        assert (await session.execute(select(PositionLot.remaining_qty))).scalar_one() == 10
        assert not list((await session.execute(select(RealizedTrade))).scalars())
    monkeypatch.setattr(ComplianceAuditService, "log", original)
    for _ in range(2):
        async with sessions() as session:
            await stream.apply_order_fill_snapshot(
                session,
                await session.get(Order, sell_id),
                status="filled",
                cumulative_filled_qty="10",
                avg_fill_price="110",
            )
            await session.commit()
    async with sessions() as session:
        audit = (await session.execute(select(AuditLog))).scalar_one()
        assert audit.action == "order.filled" and audit.entity_id == str(sell_id)
        assert audit.payload["qty"] == 10 and audit.payload["price"] == 110
        assert (
            audit.hash_chain
            and (await session.execute(select(RealizedTrade.realized_pnl))).scalar_one() == 100
        )


@pytest.mark.asyncio
async def test_late_lower_or_nonterminal_snapshot_cannot_regress_accounted_summary(sessions):
    async with sessions() as session:
        order = make_order()
        session.add(order)
        await session.flush()
        await stream.apply_order_fill_snapshot(
            session, order, status="filled", cumulative_filled_qty="10", avg_fill_price="100"
        )
        await session.commit()
        stale = await stream.apply_order_fill_snapshot(
            session, order, status="accepted", cumulative_filled_qty="0", avg_fill_price=None
        )
        late = await stream.apply_order_fill_snapshot(
            session,
            order,
            status="partially_filled",
            cumulative_filled_qty="10",
            avg_fill_price="100",
        )
        await session.commit()
        await session.refresh(order)
        assert stale["reason"] == "stale_snapshot" and late["status"] == "filled"
        assert order.filled_qty == 10 and order.status == "filled"
        assert len(list((await session.execute(select(Execution))).scalars())) == 1
