"""Behavioral tests for Phase 7.7 data-integrity remediation tooling."""
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

from backend.infra.schemas import Order, OutboxEvent, Position, PositionLot, RealizedTrade

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "db" / "phase7_data_integrity_remediation.py"
spec = importlib.util.spec_from_file_location("phase7_data_integrity_remediation", SCRIPT_PATH)
remediate = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = remediate
spec.loader.exec_module(remediate)


@pytest.fixture
async def integrity_sessionmaker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        for table in (
            Order.__table__,
            OutboxEvent.__table__,
            Position.__table__,
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
    status: str = "filled",
    side: str = "buy",
    symbol: str = "AAPL",
    qty: str = "10",
    filled_qty: str = "10",
    broker_order_id: str | None = "broker-1",
    created_at: datetime | None = None,
) -> Order:
    return Order(
        id=uuid.uuid4(),
        user_id="audit-user",
        client_idempotency_key=f"phase7-{uuid.uuid4()}",
        symbol=symbol,
        side=side,
        qty=Decimal(qty),
        order_type="market",
        tif="day",
        status=status,
        filled_qty=Decimal(filled_qty),
        avg_fill_price=Decimal("100"),
        broker_order_id=broker_order_id,
        submitted_at=created_at or datetime(2026, 5, 1, tzinfo=UTC),
        created_at=created_at or datetime(2026, 5, 1, tzinfo=UTC),
        attributes={},
    )


def _lot(open_order: Order) -> PositionLot:
    return PositionLot(
        id=uuid.uuid4(),
        user_id=open_order.user_id,
        symbol=open_order.symbol,
        qty=Decimal("10"),
        remaining_qty=Decimal("0"),
        cost_basis=Decimal("100"),
        order_id=open_order.id,
        open_date=open_order.submitted_at,
        status="closed",
    )


def _realized(
    *,
    open_order: Order,
    close_order: Order,
    lot: PositionLot,
    qty: str = "2",
    close_date: datetime | None = None,
    created_at: datetime | None = None,
) -> RealizedTrade:
    close_dt = close_date or datetime(2026, 5, 1, 15, tzinfo=UTC)
    return RealizedTrade(
        id=uuid.uuid4(),
        user_id=open_order.user_id,
        symbol=open_order.symbol,
        qty=Decimal(qty),
        open_price=Decimal("100"),
        close_price=Decimal("101"),
        realized_pnl=Decimal(qty),
        realized_pnl_percent=Decimal("1.0000"),
        open_order_id=open_order.id,
        close_order_id=close_order.id,
        lot_id=lot.id,
        open_date=open_order.submitted_at,
        close_date=close_dt,
        created_at=created_at or close_dt,
        attributes={},
    )


def _failed_outbox(order: Order) -> OutboxEvent:
    created_at = order.created_at + timedelta(seconds=1)
    return OutboxEvent(
        id=uuid.uuid4(),
        topic="order.submitted",
        payload={"order_id": str(order.id), "symbol": order.symbol},
        status="failed",
        attempts=5,
        next_attempt_at=created_at + timedelta(minutes=1),
        created_at=created_at,
        last_error="403: potential wash trade detected",
    )


async def _all(session: AsyncSession, model):
    result = await session.execute(select(model))
    return result.scalars().all()


@pytest.mark.asyncio
async def test_phase7_integrity_dry_run_classifies_safe_and_ambiguous_duplicates(
    integrity_sessionmaker,
):
    now = datetime(2026, 5, 6, tzinfo=UTC)
    async with integrity_sessionmaker() as session:
        open_order = _order(side="buy", created_at=now - timedelta(days=2))
        close_order = _order(side="sell", created_at=now - timedelta(days=2))
        ambiguous_close = _order(side="sell", created_at=now - timedelta(days=2))
        lot = _lot(open_order)
        ambiguous_lot = _lot(open_order)
        exact_a = _realized(open_order=open_order, close_order=close_order, lot=lot)
        exact_b = _realized(open_order=open_order, close_order=close_order, lot=lot)
        partial_a = _realized(
            open_order=open_order,
            close_order=ambiguous_close,
            lot=ambiguous_lot,
            qty="1",
        )
        partial_b = _realized(
            open_order=open_order,
            close_order=ambiguous_close,
            lot=ambiguous_lot,
            qty="3",
            close_date=datetime(2026, 5, 1, 15, 1, tzinfo=UTC),
        )
        session.add_all([
            open_order,
            close_order,
            ambiguous_close,
            lot,
            ambiguous_lot,
            exact_a,
            exact_b,
            partial_a,
            partial_b,
        ])
        await session.commit()

        report = await remediate.collect_report(session, now=now)

        assert report.exact_duplicate_rows_to_remove == 1
        assert len(report.exact_duplicate_groups) == 1
        assert len(report.relation_duplicate_groups) == 2
        ambiguous = [
            group for group in report.relation_duplicate_groups
            if not group.exact_duplicate
        ]
        assert len(ambiguous) == 1
        assert ambiguous[0].row_count == 2


@pytest.mark.asyncio
async def test_phase7_integrity_remediation_marks_only_failed_stale_orders(
    integrity_sessionmaker,
):
    now = datetime(2026, 5, 6, tzinfo=UTC)
    async with integrity_sessionmaker() as session:
        stale = _order(
            status="accepted",
            side="sell",
            symbol="XLE",
            qty="21",
            filled_qty="0",
            broker_order_id=None,
            created_at=now - timedelta(days=7),
        )
        young = _order(
            status="accepted",
            side="sell",
            symbol="XLE",
            filled_qty="0",
            broker_order_id=None,
            created_at=now - timedelta(minutes=5),
        )
        no_failed_outbox = _order(
            status="accepted",
            side="sell",
            symbol="XLE",
            filled_qty="0",
            broker_order_id=None,
            created_at=now - timedelta(days=7),
        )
        session.add_all([stale, young, no_failed_outbox, _failed_outbox(stale)])
        await session.commit()

        report = await remediate.collect_report(session, now=now)

        assert report.stale_orders_to_mark_failed == 1
        assert report.stale_accepted_orders[0].order_id == str(stale.id)


@pytest.mark.asyncio
async def test_phase7_integrity_apply_requires_confirmation(integrity_sessionmaker):
    async with integrity_sessionmaker() as session:
        with pytest.raises(ValueError, match=remediate.CONFIRM_TOKEN):
            await remediate.run_remediation(session, apply=True)


@pytest.mark.asyncio
async def test_phase7_integrity_apply_removes_exact_duplicates_and_marks_stale(
    integrity_sessionmaker,
):
    now = datetime(2026, 5, 6, tzinfo=UTC)
    async with integrity_sessionmaker() as session:
        open_order = _order(side="buy", created_at=now - timedelta(days=2))
        close_order = _order(side="sell", created_at=now - timedelta(days=2))
        lot = _lot(open_order)
        exact_a = _realized(open_order=open_order, close_order=close_order, lot=lot)
        exact_b = _realized(open_order=open_order, close_order=close_order, lot=lot)
        stale = _order(
            status="accepted",
            side="sell",
            symbol="XLE",
            filled_qty="0",
            broker_order_id=None,
            created_at=now - timedelta(days=7),
        )
        session.add_all([
            open_order,
            close_order,
            lot,
            exact_a,
            exact_b,
            stale,
            _failed_outbox(stale),
        ])
        await session.commit()

        report = await remediate.run_remediation(
            session,
            apply=True,
            confirm=remediate.CONFIRM_TOKEN,
        )

        assert report.applied is True
        assert len(report.deleted_realized_trade_ids) == 1
        assert report.marked_failed_order_ids == [str(stale.id)]
        realized = await _all(session, RealizedTrade)
        assert len(realized) == 1
        orders = {str(order.id): order for order in await _all(session, Order)}
        assert orders[str(stale.id)].status == "failed"
        cleanup = orders[str(stale.id)].attributes["phase7_data_integrity_cleanup"]
        assert cleanup["previous_status"] == "accepted"
        assert cleanup["reason"] == "failed_outbox_no_broker_id_zero_fill"
