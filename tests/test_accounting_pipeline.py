"""Behavioral coverage for broker-fill accounting persistence.

The live failure shape is orders with filled quantities but zero
executions, zero position lots, and zero realized trades.  These tests
exercise the accounting writer itself and the startup Alpaca sync path
against a real SQLite database.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.infra.schemas import Execution, Order, PositionLot, RealizedTrade
from backend.integrations.alpaca_stream import apply_incremental_fill_accounting


@pytest.fixture
async def accounting_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        for table in (
            Order.__table__,
            Execution.__table__,
            PositionLot.__table__,
            RealizedTrade.__table__,
        ):
            await conn.run_sync(
                lambda sync_conn, table=table: table.create(sync_conn, checkfirst=True)
            )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield async_session
    finally:
        await engine.dispose()


def _order(
    *,
    side: str,
    symbol: str = "AAPL",
    user_id: str = "audit-user",
    broker_order_id: str | None = None,
    filled_qty: Decimal = Decimal("0"),
    position_intent: str | None = None,
) -> Order:
    attributes = {"user_id": user_id}
    if position_intent:
        attributes["position_intent"] = position_intent
    return Order(
        id=uuid.uuid4(),
        user_id=user_id,
        client_idempotency_key=f"test-{uuid.uuid4()}",
        symbol=symbol,
        side=side,
        qty=Decimal("10"),
        order_type="market",
        tif="day",
        filled_qty=filled_qty,
        status="accepted",
        broker_order_id=broker_order_id,
        submitted_at=datetime.now(UTC),
        attributes=attributes,
    )


async def _rows(session: AsyncSession, model):
    result = await session.execute(select(model))
    return result.scalars().all()


@pytest.mark.asyncio
async def test_incremental_buy_fill_creates_execution_and_lot(accounting_sessionmaker):
    async with accounting_sessionmaker() as session:
        order = _order(side="buy")
        session.add(order)
        await session.flush()

        result = await apply_incremental_fill_accounting(
            session,
            order,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("7"),
            avg_fill_price=Decimal("101.25"),
            status="filled",
        )

        assert result["applied"] is True
        executions = await _rows(session, Execution)
        lots = await _rows(session, PositionLot)
        assert len(executions) == 1
        assert executions[0].fill_qty == Decimal("7.000000")
        assert executions[0].fill_price == Decimal("101.250000")
        assert len(lots) == 1
        assert lots[0].remaining_qty == Decimal("7.000000")
        assert lots[0].cost_basis == Decimal("101.250000")


@pytest.mark.asyncio
async def test_duplicate_fill_does_not_create_second_execution_or_lot(
    accounting_sessionmaker,
):
    async with accounting_sessionmaker() as session:
        order = _order(side="buy")
        session.add(order)
        await session.flush()

        first = await apply_incremental_fill_accounting(
            session,
            order,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("5"),
            avg_fill_price=Decimal("100"),
            status="partially_filled",
        )
        second = await apply_incremental_fill_accounting(
            session,
            order,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("5"),
            avg_fill_price=Decimal("100"),
            status="partially_filled",
        )

        assert first["applied"] is True
        assert second["applied"] is False
        assert second["reason"] == "duplicate_or_stale_fill"
        assert len(await _rows(session, Execution)) == 1
        assert len(await _rows(session, PositionLot)) == 1


@pytest.mark.asyncio
async def test_unsupported_side_skips_without_pending_execution(accounting_sessionmaker):
    async with accounting_sessionmaker() as session:
        order = _order(side="hold")
        session.add(order)
        await session.flush()

        result = await apply_incremental_fill_accounting(
            session,
            order,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("5"),
            avg_fill_price=Decimal("100"),
            status="filled",
        )
        await session.flush()

        assert result["applied"] is False
        assert result["reason"] == "unsupported_side:hold"
        assert await _rows(session, Execution) == []
        assert await _rows(session, PositionLot) == []


@pytest.mark.asyncio
async def test_sell_fill_creates_execution_and_realized_trade(accounting_sessionmaker):
    async with accounting_sessionmaker() as session:
        buy = _order(side="buy")
        sell = _order(side="sell")
        session.add_all([buy, sell])
        await session.flush()

        await apply_incremental_fill_accounting(
            session,
            buy,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("10"),
            avg_fill_price=Decimal("100"),
            status="filled",
        )
        result = await apply_incremental_fill_accounting(
            session,
            sell,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("4"),
            avg_fill_price=Decimal("105"),
            status="filled",
        )

        assert result["applied"] is True
        assert result["realized_count"] == 1
        executions = await _rows(session, Execution)
        realized = await _rows(session, RealizedTrade)
        lots = await _rows(session, PositionLot)
        assert len(executions) == 2
        assert len(realized) == 1
        assert realized[0].realized_pnl == Decimal("20.000000")
        assert lots[0].remaining_qty == Decimal("6.000000")


@pytest.mark.asyncio
async def test_short_open_fill_creates_execution_and_short_lot(accounting_sessionmaker):
    async with accounting_sessionmaker() as session:
        short_open = _order(
            side="sell",
            symbol="XLE",
        )
        short_open.attributes["alpaca_response"] = repr({
            "position_intent": "sell_to_open",
        })
        session.add(short_open)
        await session.flush()

        result = await apply_incremental_fill_accounting(
            session,
            short_open,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("37"),
            avg_fill_price=Decimal("56.52"),
            status="filled",
        )

        assert result["applied"] is True
        assert result["action"] == "open_short"
        assert result["position_side"] == "short"
        executions = await _rows(session, Execution)
        lots = await _rows(session, PositionLot)
        assert len(executions) == 1
        assert executions[0].fill_qty == Decimal("37.000000")
        assert len(lots) == 1
        assert lots[0].order_id == short_open.id
        assert lots[0].remaining_qty == Decimal("37.000000")


@pytest.mark.asyncio
async def test_short_close_fill_creates_short_realized_trade(accounting_sessionmaker):
    async with accounting_sessionmaker() as session:
        short_open = _order(side="sell", symbol="XLE")
        short_close = _order(side="buy", symbol="XLE")
        session.add_all([short_open, short_close])
        await session.flush()

        await apply_incremental_fill_accounting(
            session,
            short_open,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("37"),
            avg_fill_price=Decimal("56.52"),
            status="filled",
            broker_order_data={"position_intent": "sell_to_open"},
        )
        result = await apply_incremental_fill_accounting(
            session,
            short_close,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("37"),
            avg_fill_price=Decimal("58.06"),
            status="filled",
            broker_order_data={"position_intent": "buy_to_close"},
        )

        assert result["applied"] is True
        assert result["action"] == "close_short"
        assert result["position_side"] == "short"
        executions = await _rows(session, Execution)
        realized = await _rows(session, RealizedTrade)
        lots = await _rows(session, PositionLot)
        assert len(executions) == 2
        assert len(realized) == 1
        assert realized[0].realized_pnl == Decimal("-56.980000")
        assert realized[0].attributes == {"position_side": "short"}
        assert lots[0].status == "closed"
        assert lots[0].remaining_qty == Decimal("0.000000")


@pytest.mark.asyncio
async def test_long_close_does_not_consume_open_short_lot(accounting_sessionmaker):
    async with accounting_sessionmaker() as session:
        long_open = _order(side="buy", symbol="XLE")
        short_open = _order(
            side="sell",
            symbol="XLE",
            position_intent="sell_to_open",
        )
        long_close = _order(
            side="sell",
            symbol="XLE",
            position_intent="sell_to_close",
        )
        session.add_all([long_open, short_open, long_close])
        await session.flush()

        await apply_incremental_fill_accounting(
            session,
            long_open,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("10"),
            avg_fill_price=Decimal("50"),
            status="filled",
        )
        await apply_incremental_fill_accounting(
            session,
            short_open,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("7"),
            avg_fill_price=Decimal("60"),
            status="filled",
        )
        result = await apply_incremental_fill_accounting(
            session,
            long_close,
            previous_filled_qty=Decimal("0"),
            cumulative_filled_qty=Decimal("10"),
            avg_fill_price=Decimal("55"),
            status="filled",
        )

        assert result["applied"] is True
        assert result["action"] == "close_long"
        lots = sorted(await _rows(session, PositionLot), key=lambda lot: lot.open_date)
        assert lots[0].order_id == long_open.id
        assert lots[0].status == "closed"
        assert lots[1].order_id == short_open.id
        assert lots[1].status == "open"
        assert lots[1].remaining_qty == Decimal("7.000000")


@pytest.mark.asyncio
async def test_startup_order_sync_persists_fill_accounting(
    accounting_sessionmaker,
    monkeypatch,
):
    from backend.api.lifespan import _sync_orders
    import backend.integrations.alpaca_broker as alpaca_broker

    async with accounting_sessionmaker() as session:
        session.add(_order(side="buy", broker_order_id="broker-buy-1"))
        await session.commit()

    class FakeResponse:
        status_code = 200

        def json(self):
            return [{
                "id": "broker-buy-1",
                "status": "filled",
                "filled_qty": "3",
                "filled_avg_price": "111.50",
            }]

    class FakeClient:
        async def get(self, *args, **kwargs):
            return FakeResponse()

    fake_broker = SimpleNamespace(
        base_url="https://paper-api.alpaca.invalid",
        client=FakeClient(),
        _get_auth_headers=lambda: {},
    )
    monkeypatch.setattr(
        alpaca_broker,
        "get_alpaca_broker_client",
        lambda: fake_broker,
    )

    app = SimpleNamespace(
        state=SimpleNamespace(sessionmaker=accounting_sessionmaker)
    )
    await _sync_orders(app)

    async with accounting_sessionmaker() as session:
        executions = await _rows(session, Execution)
        lots = await _rows(session, PositionLot)
        orders = await _rows(session, Order)

    assert len(executions) == 1
    assert executions[0].fill_qty == Decimal("3.000000")
    assert executions[0].fill_price == Decimal("111.500000")
    assert len(lots) == 1
    assert lots[0].remaining_qty == Decimal("3.000000")
    assert orders[0].status == "filled"
    assert orders[0].filled_qty == Decimal("3.000000")
