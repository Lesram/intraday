"""Audit 2026-09-29 R8: identical broker snapshots must not touch updated_at.

Startup order sync calls ``attach_broker_result`` for every synced order. It
used to stamp ``updated_at = now`` unconditionally, so each restart made older
same-symbol fills look "updated since entry" to the closed-position lookup and
any position open across the restart could never be accounted.
Synthetic IDs and isolated SQLite databases only.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from backend.infra.repositories.orders import OrderNotFoundError, OrdersRepo
from backend.infra.schemas import Execution, Order
import test_live_engine_fill_accounting as fill_fixtures
from test_live_engine_fill_accounting import ANCHOR, CLOSE, START, lookup, order, store_rows

database = fill_fixtures.database


async def stored(maker, order_id):
    async with maker() as session:
        return (await session.execute(select(Order).where(Order.id == order_id))).scalar_one()


async def attach(maker, order_id, **fields):
    async with maker() as session:
        await OrdersRepo(session).attach_broker_result(order_id, **fields)
        await session.commit()


def row_id(i):
    return order(i, "buy", 1, 1)["id"]


@pytest.mark.parametrize("fields", [
    {"broker_order_id": "synthetic-1", "status": "filled",
     "filled_qty": Decimal("6"), "avg_fill_price": Decimal("321")},
    # Same values at the column's DECIMAL(18, 6) storage precision.
    {"filled_qty": Decimal("6.000000"), "avg_fill_price": Decimal("321.0000001")},
    {"attributes": {"source": "organism"}},
    {},
])
async def test_identical_snapshot_leaves_row_and_updated_at_untouched(database, fields):
    await store_rows(database, [order(1, "buy", 6, 321)])
    before = await stored(database, ANCHOR)
    await attach(database, ANCHOR, **fields)
    after = await stored(database, ANCHOR)
    assert after.updated_at == before.updated_at
    assert (after.status, after.filled_qty, after.avg_fill_price, after.broker_order_id, after.attributes) == (
        before.status, before.filled_qty, before.avg_fill_price, before.broker_order_id, before.attributes)


@pytest.mark.parametrize("fields,column,expected", [
    ({"status": "cancelled"}, "status", "cancelled"),
    ({"status": "filled", "filled_qty": Decimal("7")}, "filled_qty", Decimal("7")),
    ({"avg_fill_price": Decimal("321.5")}, "avg_fill_price", Decimal("321.5")),
    ({"broker_order_id": "synthetic-other"}, "broker_order_id", "synthetic-other"),
    ({"limit_price": Decimal("320")}, "limit_price", Decimal("320")),
    ({"stop_price": Decimal("300")}, "stop_price", Decimal("300")),
    ({"attributes": {"note": "ack"}}, "attributes",
     {"source": "organism", "reason": "ml_reversal", "note": "ack"}),
])
async def test_changed_field_is_written_and_bumps_updated_at(database, fields, column, expected):
    await store_rows(database, [order(1, "buy", 6, 321, qty=Decimal(7))])
    before = await stored(database, ANCHOR)
    await attach(database, ANCHOR, **fields)
    after = await stored(database, ANCHOR)
    assert getattr(after, column) == expected
    assert after.updated_at > before.updated_at


@pytest.mark.parametrize("fields", [{}, {"status": "filled"}, {"attributes": {"note": "ack"}}])
async def test_missing_order_still_raises(database, fields):
    with pytest.raises(OrderNotFoundError):
        await attach(database, uuid.UUID(int=999), **fields)


async def simulated_restart_sync(maker, rows):
    """Mirror lifespan._sync_orders: identical broker snapshots re-applied."""
    from backend.integrations.alpaca_stream import apply_order_fill_snapshot

    for row in rows:
        async with maker() as session:
            db_order = await OrdersRepo(session).get_by_broker_order_id(row["broker_order_id"])
            accounting = await apply_order_fill_snapshot(
                session, db_order, status="filled",
                cumulative_filled_qty=str(row["filled_qty"]),
                avg_fill_price=str(row["avg_fill_price"]),
                broker_order_id=row["broker_order_id"],
                broker_order_data={"id": row["broker_order_id"], "status": "filled"},
            )
            await session.commit()
            assert accounting["applied"] is False  # already-accounted fill


async def test_position_open_across_restart_sync_remains_accountable(database, tmp_path):
    from backend.organism.live_engine import OrganismLiveEngine

    older = [order(10, "buy", 3, 90, submitted_at=START - timedelta(days=1)),
             order(11, "sell", 3, 91, submitted_at=START - timedelta(hours=1))]
    lifetime = [order(1, "buy", 6, 321), order(2, "sell", 1, 322.73), order(3, "sell", 5, 321.81)]
    rows = older + lifetime
    await store_rows(database, rows)
    async with database() as session:
        # Fills were already ingested before the restart (execution rows exist).
        session.add_all([Execution(order_id=row["id"], fill_qty=row["filled_qty"],
                                   fill_price=row["avg_fill_price"], ts=row["submitted_at"],
                                   venue="fixture") for row in rows])
        await session.commit()
    before = {row["id"]: (await stored(database, row["id"])).updated_at for row in rows}

    await simulated_restart_sync(database, rows)

    for row in rows:
        assert (await stored(database, row["id"])).updated_at == before[row["id"]]
    meta = {"entry_order_id": str(ANCHOR), "entry_price": 321, "entry_tick": 1,
            "filled_shares": 6, "direction": 1, "entry_source": "alpha",
            "entry_time": START.timestamp()}
    fills = await lookup(database)._lookup_closed_position_fills_from_db("TSLA", meta, closed_at=CLOSE)
    assert fills is not None and fills.pnl == pytest.approx(5.78)

    broker = MagicMock()
    broker.get_all_positions = AsyncMock(return_value={})
    engine = OrganismLiveEngine(
        data_client=MagicMock(), order_service=broker, positions_service=broker,
        brain_dir=str(tmp_path / "brain"), universe=["TSLA"], sessionmaker=database,
    )
    engine._now_fn = lambda: CLOSE
    engine._time_fn = lambda: CLOSE.timestamp()
    engine._tick_count = 10
    engine._entry_metadata = {"TSLA": dict(meta)}
    engine._save_brain = MagicMock()
    await engine._reconcile_fills({})
    assert [trade.symbol for trade in engine._all_trades] == ["TSLA"]
    assert engine._all_trades[0].pnl == pytest.approx(5.78)
    assert engine._all_trades[0].price_source == "db_position_fills"
    assert "TSLA" not in engine._entry_metadata
    assert not broker.submit_order.called


async def test_real_restart_bump_is_what_made_the_close_unaccountable(database):
    """Control: a genuine post-entry update of an older fill stays ambiguous."""
    older = order(10, "buy", 3, 90, submitted_at=START - timedelta(days=1))
    rows = [older, order(11, "sell", 3, 91, submitted_at=START - timedelta(hours=1)),
            order(1, "buy", 6, 321), order(2, "sell", 1, 322.73), order(3, "sell", 5, 321.81)]
    await store_rows(database, rows)
    await attach(database, older["id"], status="cancelled")  # a real change -> updated_at = now
    meta = {"entry_order_id": str(ANCHOR), "direction": 1}
    assert await lookup(database)._lookup_closed_position_fills_from_db("TSLA", meta, closed_at=CLOSE) is None
