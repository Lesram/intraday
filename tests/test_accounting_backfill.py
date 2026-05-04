"""Behavioral tests for historical fill-accounting backfill tooling."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.infra.schemas import Execution, Order, PositionLot, RealizedTrade

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKFILL_PATH = REPO_ROOT / "scripts" / "db" / "backfill_fill_accounting.py"
spec = importlib.util.spec_from_file_location("backfill_fill_accounting", BACKFILL_PATH)
backfill = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = backfill
spec.loader.exec_module(backfill)


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
    qty: str = "10",
    price: str | None = "100",
    status: str = "filled",
    submitted_at: datetime | None = None,
    user_id: str = "audit-user",
    position_intent: str | None = None,
) -> Order:
    attrs = {"user_id": user_id}
    if position_intent:
        attrs["alpaca_response"] = repr({"position_intent": position_intent})
    return Order(
        id=uuid.uuid4(),
        user_id=user_id,
        client_idempotency_key=f"backfill-{uuid.uuid4()}",
        symbol=symbol,
        side=side,
        qty=Decimal(qty),
        order_type="market",
        tif="day",
        filled_qty=Decimal(qty),
        avg_fill_price=Decimal(price) if price is not None else None,
        status=status,
        submitted_at=submitted_at or datetime.now(UTC),
        attributes=attrs,
    )


async def _rows(session: AsyncSession, model):
    result = await session.execute(select(model))
    return result.scalars().all()


@pytest.mark.asyncio
async def test_backfill_dry_run_reports_without_writing(accounting_sessionmaker):
    start = datetime(2026, 5, 1, tzinfo=UTC)
    async with accounting_sessionmaker() as session:
        session.add_all([
            _order(side="buy", qty="10", price="100", submitted_at=start),
            _order(side="sell", qty="4", price="105", submitted_at=start + timedelta(minutes=1)),
        ])
        await session.commit()

        report = await backfill.run_backfill(session)

        assert report.dry_run is True
        assert report.applied is False
        assert report.errors == []
        assert report.executions_to_create == 2
        assert report.position_lots_to_create == 1
        assert report.realized_trades_to_create == 1
        assert report.open_lots_after == 1
        assert await _rows(session, Execution) == []
        assert await _rows(session, PositionLot) == []
        assert await _rows(session, RealizedTrade) == []


@pytest.mark.asyncio
async def test_backfill_apply_creates_execution_lot_and_realized_trade(
    accounting_sessionmaker,
):
    start = datetime(2026, 5, 1, tzinfo=UTC)
    async with accounting_sessionmaker() as session:
        session.add_all([
            _order(side="buy", qty="10", price="100", submitted_at=start),
            _order(side="sell", qty="4", price="105", submitted_at=start + timedelta(minutes=1)),
        ])
        await session.commit()

        report = await backfill.run_backfill(
            session,
            apply=True,
            confirm=backfill.CONFIRM_TOKEN,
        )

        assert report.applied is True
        executions = await _rows(session, Execution)
        lots = await _rows(session, PositionLot)
        realized = await _rows(session, RealizedTrade)
        assert len(executions) == 2
        assert {e.venue for e in executions} == {"alpaca_backfill"}
        assert len(lots) == 1
        assert lots[0].remaining_qty == Decimal("6.000000")
        assert len(realized) == 1
        assert realized[0].realized_pnl == Decimal("20.000000")


@pytest.mark.asyncio
async def test_backfill_dry_run_handles_short_round_trip(accounting_sessionmaker):
    start = datetime(2026, 4, 8, 13, 36, tzinfo=UTC)
    async with accounting_sessionmaker() as session:
        session.add_all([
            _order(
                side="sell",
                symbol="XLE",
                qty="37",
                price="56.52",
                submitted_at=start,
                position_intent="sell_to_open",
            ),
            _order(
                side="buy",
                symbol="XLE",
                qty="37",
                price="58.06",
                submitted_at=start + timedelta(hours=6),
                position_intent="buy_to_close",
            ),
        ])
        await session.commit()

        report = await backfill.run_backfill(session)

        assert report.errors == []
        assert report.executions_to_create == 2
        assert report.short_lots_to_create == 1
        assert report.short_realized_trades_to_create == 1
        assert report.open_short_lots_after == 0
        assert report.realized_pnl == "-56.980000"
        assert await _rows(session, Execution) == []


@pytest.mark.asyncio
async def test_backfill_apply_creates_short_lot_and_short_realized_trade(
    accounting_sessionmaker,
):
    start = datetime(2026, 4, 8, 13, 36, tzinfo=UTC)
    async with accounting_sessionmaker() as session:
        session.add_all([
            _order(
                side="sell",
                symbol="XLE",
                qty="37",
                price="56.52",
                submitted_at=start,
                position_intent="sell_to_open",
            ),
            _order(
                side="buy",
                symbol="XLE",
                qty="37",
                price="58.06",
                submitted_at=start + timedelta(hours=6),
                position_intent="buy_to_close",
            ),
        ])
        await session.commit()

        report = await backfill.run_backfill(
            session,
            apply=True,
            confirm=backfill.CONFIRM_TOKEN,
        )

        assert report.applied is True
        executions = await _rows(session, Execution)
        lots = await _rows(session, PositionLot)
        realized = await _rows(session, RealizedTrade)
        assert len(executions) == 2
        assert len(lots) == 1
        assert lots[0].status == "closed"
        assert lots[0].remaining_qty == Decimal("0.000000")
        assert len(realized) == 1
        assert realized[0].realized_pnl == Decimal("-56.980000")
        assert realized[0].attributes == {"position_side": "short"}


@pytest.mark.asyncio
async def test_backfill_handles_mixed_xle_long_then_short_sequence(
    accounting_sessionmaker,
):
    start = datetime(2026, 4, 8, 13, 29, tzinfo=UTC)
    async with accounting_sessionmaker() as session:
        session.add_all([
            _order(side="buy", symbol="XLE", qty="58", price="56.459310", submitted_at=start),
            _order(
                side="sell",
                symbol="XLE",
                qty="21",
                price="56.317619",
                submitted_at=start + timedelta(minutes=4),
                position_intent="sell_to_close",
            ),
            _order(
                side="sell",
                symbol="XLE",
                qty="37",
                price="56.32",
                submitted_at=start + timedelta(minutes=7),
                position_intent="sell_to_close",
            ),
            _order(
                side="sell",
                symbol="XLE",
                qty="37",
                price="56.52",
                submitted_at=start + timedelta(minutes=8),
                position_intent="sell_to_open",
            ),
            _order(
                side="buy",
                symbol="XLE",
                qty="37",
                price="58.06",
                submitted_at=start + timedelta(hours=6),
                position_intent="buy_to_close",
            ),
        ])
        await session.commit()

        report = await backfill.run_backfill(session)

        assert report.errors == []
        assert report.position_lots_to_create == 1
        assert report.short_lots_to_create == 1
        assert report.realized_trades_to_create == 2
        assert report.short_realized_trades_to_create == 1
        assert report.open_lots_after == 0
        assert report.open_short_lots_after == 0


@pytest.mark.asyncio
async def test_backfill_is_idempotent_after_apply(accounting_sessionmaker):
    async with accounting_sessionmaker() as session:
        session.add(_order(side="buy", qty="5", price="99"))
        await session.commit()

        first = await backfill.run_backfill(
            session,
            apply=True,
            confirm=backfill.CONFIRM_TOKEN,
        )
        second = await backfill.run_backfill(session)

        assert first.applied is True
        assert second.executions_to_create == 0
        assert second.skipped_existing_execution == 1
        assert len(await _rows(session, Execution)) == 1
        assert len(await _rows(session, PositionLot)) == 1


@pytest.mark.asyncio
async def test_backfill_refuses_apply_when_fifo_sequence_is_invalid(
    accounting_sessionmaker,
):
    async with accounting_sessionmaker() as session:
        session.add(_order(side="sell", qty="4", price="105"))
        await session.commit()

        dry_run = await backfill.run_backfill(session)
        assert len(dry_run.errors) == 1
        assert dry_run.errors[0].reason.startswith("insufficient_lots")

        with pytest.raises(ValueError, match="simulation has errors"):
            await backfill.run_backfill(
                session,
                apply=True,
                confirm=backfill.CONFIRM_TOKEN,
            )
        assert await _rows(session, Execution) == []
        assert await _rows(session, RealizedTrade) == []


@pytest.mark.asyncio
async def test_backfill_apply_requires_confirmation(accounting_sessionmaker):
    async with accounting_sessionmaker() as session:
        session.add(_order(side="buy", qty="1", price="100"))
        await session.commit()

        with pytest.raises(ValueError, match=backfill.CONFIRM_TOKEN):
            await backfill.run_backfill(session, apply=True)

        assert await _rows(session, Execution) == []
