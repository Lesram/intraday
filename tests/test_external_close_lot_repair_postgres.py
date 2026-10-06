"""Opt-in PostgreSQL proof of the external-close lot repair (audit 2026-10-05 C06-01 review).

SQLite ignores row locks, so the repair's lock clauses (FOR NO KEY UPDATE on the
window's closing-side order rows, then FOR UPDATE OF position_lots) and its
serialization with a concurrent ingestion of the same close only show on
PostgreSQL. The cases use the guarded disposable-database harness of
tests/test_fill_accounting_postgres.py (INTRA_FILL_TEST_DATABASE_URL, one
dedicated schema per case); without that database they are skipped visibly.
Synthetic identities only.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select

from backend.infra.schemas import AuditLog, Order, PositionLot, RealizedTrade
from backend.integrations import alpaca_stream as stream

try:  # The guarded harness fixture (skips unless the dedicated URL is supplied).
    from test_fill_accounting_postgres import pg_sessions  # noqa: F401
except ImportError:
    @pytest.fixture
    async def pg_sessions():
        pytest.skip("Disposable PostgreSQL harness (tests/test_fill_accounting_postgres.py) not present")
        yield


ROUTE = {"close_position": True, "position_type": "long", "partial_close": False}


def _row(symbol, side, qty, *, at, user="system", attributes=None):
    return Order(
        id=uuid.uuid4(), user_id=user, client_idempotency_key=f"repair_{uuid.uuid4().hex}",
        symbol=symbol, side=side, qty=Decimal(qty), filled_qty=Decimal(0), status="accepted",
        order_type="market", tif="day", submitted_at=at, created_at=at, updated_at=at,
        broker_order_id=str(uuid.uuid4()),
        attributes=attributes if attributes is not None else {"source": "organism", "reason": "organism_entry"},
    )


async def _ingest(session, order_id, qty, price):
    current = await session.get(Order, order_id)
    return await stream.apply_order_fill_snapshot(
        session, current, status="filled", cumulative_filled_qty=str(qty),
        avg_fill_price=str(price), broker_order_id=current.broker_order_id)


async def _route_closed_lifetime(sessions):
    """Engine entry buy 6 @ 100; the operator's close route sells 6 @ 97 (unmatched)."""
    t0 = datetime.now(UTC)
    entry = _row("TSLA", "buy", 6, at=t0 - timedelta(minutes=30))
    route = _row("TSLA", "sell", 6, at=t0 - timedelta(minutes=5), user="ops@example.com",
                 attributes=dict(ROUTE))
    async with sessions() as session:
        session.add_all([entry, route])
        await session.commit()
    for order_id, price in ((entry.id, 100), (route.id, 97)):
        async with sessions() as session:
            await _ingest(session, order_id, 6, price)
            await session.commit()
    return t0, entry, route


async def _repair(session, entry, closed_at):
    return await stream.repair_external_close_lots(
        session, symbol="TSLA", entry_order_id=entry.id, closed_at=closed_at, direction=1.0)


async def _assert_repaired(sessions, entry, route):
    async with sessions() as session:
        lots = list((await session.execute(select(PositionLot))).scalars())
        realized = list((await session.execute(select(RealizedTrade))).scalars())
        close = await session.get(Order, route.id)
        audits = list((await session.execute(select(AuditLog).where(
            AuditLog.actor == stream.EXTERNAL_CLOSE_REPAIR_ACTOR))).scalars())
    assert [(lot.order_id, lot.remaining_qty, lot.status) for lot in lots] == [(entry.id, 0, "closed")]
    assert [(r.open_order_id, r.close_order_id, r.qty, r.realized_pnl, r.attributes["lot_accounting"])
            for r in realized] == [(entry.id, route.id, 6, -18, "external_close_repair")]
    record = close.attributes["lot_accounting"]
    assert (record["status"], record["repair"], record["matched_late_qty"]) == ("matched_late", "none", "6.000000")
    assert audits == []


async def scenario_repair_runs_and_is_idempotent(sessions):
    t0, entry, route = await _route_closed_lifetime(sessions)
    async with sessions() as session:
        report = await _repair(session, entry, t0)
        await session.commit()
    assert len(report["netted"]) == 1 and report["written_off"] == []
    await _assert_repaired(sessions, entry, route)
    async with sessions() as session:
        again = await _repair(session, entry, t0)
        await session.commit()
    assert again["netted"] == [] and again["written_off"] == []
    await _assert_repaired(sessions, entry, route)


async def scenario_repair_waits_for_a_concurrent_ingestion_of_the_close(sessions):
    # A re-delivered fill of the route close holds its order row; the repair
    # waits for it, then nets the committed record.
    t0, entry, route = await _route_closed_lifetime(sessions)
    async with sessions() as ingestion:
        outcome = await _ingest(ingestion, route.id, 6, 97)
        assert outcome["applied"] is False  # duplicate: the row lock is still held
        async with sessions() as repair_session:
            repair = asyncio.create_task(_repair(repair_session, entry, t0))
            await asyncio.sleep(0.5)
            assert not repair.done(), "the repair must wait for the close's row lock"
            await ingestion.commit()
            report = await asyncio.wait_for(repair, 5)
            await repair_session.commit()
    assert len(report["netted"]) == 1
    await _assert_repaired(sessions, entry, route)


async def scenario_concurrent_ingestion_waits_for_the_repair_and_keeps_its_record(sessions):
    t0, entry, route = await _route_closed_lifetime(sessions)
    async with sessions() as repair_session:
        await _repair(repair_session, entry, t0)
        async with sessions() as ingestion:
            late = asyncio.create_task(_ingest(ingestion, route.id, 6, 97))
            await asyncio.sleep(0.5)
            assert not late.done(), "the ingestion must wait for the repair's row lock"
            await repair_session.commit()
            outcome = await asyncio.wait_for(late, 5)
            await ingestion.commit()
    assert outcome["applied"] is False
    await _assert_repaired(sessions, entry, route)  # the record stays matched_late


async def scenario_unbooked_write_off_is_audited(sessions):
    t0 = datetime.now(UTC)
    entry = _row("TSLA", "buy", 6, at=t0 - timedelta(minutes=30))
    async with sessions() as session:
        session.add(entry)
        await session.commit()
    async with sessions() as session:
        await _ingest(session, entry.id, 6, 100)
        await session.commit()
    async with sessions() as session:
        report = await stream.repair_external_close_lots(
            session, symbol="TSLA", entry_order_id=entry.id, closed_at=t0, direction=1.0,
            mark=96.0, mark_source="observed_bar_close")
        await session.commit()
    assert report["netted"] == [] and [item["qty"] for item in report["written_off"]] == ["6.000000"]
    async with sessions() as session:
        lots = list((await session.execute(select(PositionLot))).scalars())
        (audit,) = (await session.execute(select(AuditLog).where(
            AuditLog.actor == stream.EXTERNAL_CLOSE_REPAIR_ACTOR))).scalars()
    assert [(lot.remaining_qty, lot.status) for lot in lots] == [(0, "closed")]
    assert (audit.action, audit.payload["reason"], audit.payload["mark"]) == (
        "position.adjusted", "external_close_unbooked_write_off", 96.0)


SCENARIOS = (
    scenario_repair_runs_and_is_idempotent,
    scenario_repair_waits_for_a_concurrent_ingestion_of_the_close,
    scenario_concurrent_ingestion_waits_for_the_repair_and_keeps_its_record,
    scenario_unbooked_write_off_is_audited,
)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda scenario: scenario.__name__)
async def test_external_close_lot_repair_on_postgresql(pg_sessions, scenario):
    await scenario(pg_sessions)
