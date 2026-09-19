"""Closed-position cash-flow accounting; synthetic IDs and isolated databases only."""
from __future__ import annotations

import copy
import json
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.infra.schemas import Execution, Order
from backend.organism.live_engine_fills import _FillLookupMixin, _closed_position_fills

START = datetime(2026, 8, 3, 14, tzinfo=UTC)
CLOSE = START + timedelta(hours=2)
ANCHOR = uuid.UUID("abcdef00-0000-0000-0000-000000000001")


def order(i, order_side, quantity, price, *, symbol="TSLA", **overrides):
    row = {
        "id": uuid.UUID(f"abcdef00-0000-0000-0000-{i:012x}"), "symbol": symbol, "side": order_side,
        "qty": Decimal(str(quantity)), "filled_qty": Decimal(str(quantity)),
        "avg_fill_price": Decimal(str(price)), "status": "filled",
        "submitted_at": START + timedelta(minutes=i - 1),
        "broker_order_id": f"synthetic-{i}",
        "attributes": {"source": "organism", "reason": "ml_reversal"},
    }
    row.update(overrides)
    return row


def calculate(rows, *, symbol="TSLA", direction=1):
    return _closed_position_fills(
        rows, entry_order_id=ANCHOR, symbol=symbol,
        direction=direction, closed_at=CLOSE,
    )


# Sanitized prices/quantities from the Sept-19 read-only paper order export.
# Six ml_reversal cases and the already-flagged XOM scale-out; IDs/times synthetic.
OBSERVED = [
    ("TSLA", "321", 6, 1, "322.73", "321.81", "5.78", "4.86"),
    ("AVGO", "388.12", 5, 1, "388.24", "387.94", "-0.60", "-0.90"),
    ("AMD", "471.48", 4, 1, "482.43", "480.08", "36.75", "34.40"),
    ("NVDA", "202.11", 9, 2, "207.08", "207", "44.17", "44.01"),
    ("MSFT", "487.19", 4, 1, "489.1", "488.533333", "5.939999", "5.373332"),
    ("NVDA", "210.264444", 9, 2, "210.625", "210.32", "1.110004", "0.500004"),
    ("XOM", "153.21", 13, 2, "153.33", "153.334545", "1.609995", "1.619085"),
]


@pytest.mark.parametrize("symbol,entry,qty,partial,p1,p2,expected,legacy", OBSERVED)
def test_observed_partial_positions_include_every_exit(symbol, entry, qty, partial, p1, p2, expected, legacy):
    rows = [order(1, "buy", qty, entry, symbol=symbol),
            order(2, "sell", partial, p1, symbol=symbol),
            order(3, "sell", qty - partial, p2, symbol=symbol)]
    before = copy.deepcopy(rows)
    result = calculate(rows, symbol=symbol)
    assert result is not None
    assert result.pnl == pytest.approx(float(expected), abs=1e-9)
    assert result.shares == qty
    assert result.entry_price == float(entry)
    assert result.exit_price == pytest.approx(float((Decimal(p1) * partial + Decimal(p2) * (qty - partial)) / qty))
    assert result.had_partial_exits is True
    assert float((Decimal(p2) - Decimal(entry)) * qty) == pytest.approx(float(legacy))
    assert rows == before


def test_weighted_entries_terminal_partial_orders_and_zero_cancel():
    rows = [order(1, "buy", 2, 100), order(2, "buy", 3, 110),
            order(3, "sell", 2, 120, qty=Decimal(3), status="canceled"),
            order(4, "sell", 3, 115),
            order(5, "sell", 0, 0, qty=Decimal(2), status="expired", avg_fill_price=None)]
    result = calculate(list(reversed(rows)))
    assert result is not None
    assert (result.shares, result.entry_price, result.exit_price, result.pnl) == (5, 106, 117, 55)
    assert result.had_partial_exits


def test_single_exit_and_short_direction_are_accounted_without_strategy_change():
    long = calculate([order(1, "buy", 2, 100), order(2, "sell", 2, 103)])
    short = calculate([order(1, "sell", 2, 100), order(2, "buy", 2, 97)], direction=-1)
    assert long is not None and short is not None
    assert long.pnl == short.pnl == 6
    assert not long.had_partial_exits and not short.had_partial_exits


def test_all_27_observed_positions_replay_to_broker_cash_flows_without_mutation():
    path = Path(__file__).parent / "fixtures/paper_fill_accounting_forward_20260919.json"
    before = path.read_bytes()
    cases = json.loads(before)["cases"]
    results = []
    for case in cases:
        rows = [order(i, leg["side"], leg["filled_qty"], leg["filled_avg_price"],
                      symbol=case["symbol"], status=leg["status"],
                      submitted_at=datetime.fromisoformat(leg["submitted_at"]))
                for i, leg in enumerate(case["orders"], 1)]
        result = _closed_position_fills(
            rows, entry_order_id=ANCHOR, symbol=case["symbol"], direction=1,
            closed_at=datetime.fromisoformat(case["closed_at"]),
        )
        assert result is not None
        assert result.pnl == pytest.approx(case["expected_gross_pnl"], abs=1e-8)
        results.append(result)
    assert len(results) == 27
    assert sum(x.pnl for x in results) == pytest.approx(89.819991, abs=1e-8)
    assert sum(x.had_partial_exits for x in results) == 7
    assert sum(x["historical_ledger_pnl"] for x in cases) == pytest.approx(84.922414, abs=1e-8)
    assert path.read_bytes() == before


@pytest.mark.parametrize("change", [
    {"filled_qty": Decimal(1)}, {"filled_qty": Decimal(3)},
    {"status": "partially_filled"}, {"status": "accepted"},
    {"avg_fill_price": Decimal("NaN")}, {"avg_fill_price": Decimal("Infinity")},
    {"avg_fill_price": Decimal(0)}, {"filled_qty": Decimal(-1)},
    {"broker_order_id": None}, {"broker_order_id": "synthetic-1"},
    {"attributes": {"source": "manual"}}, {"attributes": None},
    {"status": "rejected"}, {"symbol": "OTHER"}, {"side": "unknown"},
    {"submitted_at": CLOSE + timedelta(seconds=1)},
])
def test_uncertain_or_incomplete_exit_refuses_exact_accounting(change):
    rows = [order(1, "buy", 2, 100), order(2, "sell", 2, 103, **change)]
    assert calculate(rows) is None


@pytest.mark.parametrize("extra", [
    order(3, "buy", 2, 101),
    order(3, "sell", 1, 104),
    order(3, "sell", 0, 0, qty=Decimal(1), status="new"),
])
def test_no_later_position_or_unsettled_order_is_silently_aggregated(extra):
    assert calculate([order(1, "buy", 2, 100), order(2, "sell", 2, 103), extra]) is None


def test_missing_anchor_duplicate_anchor_fractional_or_unbalanced_position():
    assert calculate([order(2, "buy", 2, 100), order(3, "sell", 2, 103)]) is None
    entry = order(1, "buy", 2, 100)
    assert calculate([entry, entry, order(2, "sell", 2, 103)]) is None
    assert calculate([entry, order(2, "sell", 1, 103)]) is None
    assert calculate([entry, order(2, "sell", 3, 103)]) is None
    assert calculate([order(1, "buy", 1.5, 100), order(2, "sell", 1.5, 103)]) is None
    assert calculate([entry, order(2, "sell", 2, 103)], direction=0) is None


@pytest.fixture
async def database(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'orders.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Order.__table__.create)
        await conn.run_sync(Execution.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield maker
    finally:
        await engine.dispose()


async def store_rows(maker, rows):
    async with maker() as session:
        session.add_all([Order(**dict({"updated_at": row["submitted_at"]}, **row), user_id="fixture", order_type="market", tif="day",
                               client_idempotency_key=f"fixture-{row['id']}") for row in rows])
        await session.commit()


def lookup(maker):
    host = _FillLookupMixin()
    host._sessionmaker = maker
    return host


async def test_database_lookup_uses_entry_identity_and_is_read_only(database):
    rows = [order(10, "buy", 3, 90, submitted_at=START - timedelta(days=1)),
            order(11, "sell", 3, 91, submitted_at=START - timedelta(hours=1)),
            order(1, "buy", 6, 321), order(2, "sell", 1, 322.73), order(3, "sell", 5, 321.81),
            order(12, "buy", 1, 90, submitted_at=CLOSE + timedelta(minutes=1))]
    await store_rows(database, rows)
    async with database() as session:
        before = list((await session.execute(select(Order.__table__))).mappings().all())
    result = await lookup(database)._lookup_closed_position_fills_from_db(
        "TSLA", {"entry_order_id": str(ANCHOR), "direction": 1, "entry_time": CLOSE.timestamp()}, closed_at=CLOSE,
    )
    assert result is not None and result.pnl == 5.78
    async with database() as session:
        after = list((await session.execute(select(Order.__table__))).mappings().all())
    assert before == after


@pytest.mark.parametrize("extra", [
    order(3, "sell", 0, 0, qty=Decimal(1), status="new"),
    order(3, "sell", 0, 0, qty=Decimal(1), status="canceled", attributes={"source": "manual"}),
])
async def test_database_lookup_does_not_filter_out_conflicting_orders(database, extra):
    await store_rows(database, [order(1, "buy", 2, 100), order(2, "sell", 2, 103), extra])
    assert await lookup(database)._lookup_closed_position_fills_from_db(
        "TSLA", {"entry_order_id": str(ANCHOR)}, closed_at=CLOSE,
    ) is None


@pytest.mark.parametrize("extra", [
    order(3, "sell", 0, 0, qty=Decimal(1), status="new", submitted_at=START - timedelta(days=1)),
    order(3, "sell", 1, 103, submitted_at=START - timedelta(days=1), updated_at=START + timedelta(minutes=1)),
])
async def test_database_lookup_rejects_pre_entry_orders_that_can_affect_lifetime(database, extra):
    await store_rows(database, [order(1, "buy", 2, 100), order(2, "sell", 2, 103), extra])
    assert await lookup(database)._lookup_closed_position_fills_from_db(
        "TSLA", {"entry_order_id": str(ANCHOR)}, closed_at=CLOSE,
    ) is None


async def test_missing_identity_or_database_failure_is_unknown():
    host = lookup(MagicMock(side_effect=RuntimeError("fixture DB failure")))
    for meta in ({}, {"entry_order_id": "invalid"},
                 {"entry_order_id": str(ANCHOR), "entry_source": "reconciliation_orphan"}):
        assert await host._lookup_closed_position_fills_from_db("TSLA", meta, closed_at=CLOSE) is None
    host._sessionmaker.assert_not_called()
    assert await host._lookup_closed_position_fills_from_db(
        "TSLA", {"entry_order_id": str(ANCHOR)}, closed_at=CLOSE,
    ) is None


@pytest.mark.parametrize("complete,expected,source,partial,restarted", [
    (True, 5.78, "db_position_fills", True, False),
    (True, 5.78, "db_position_fills", True, True),
])
async def test_real_reconciliation_updates_future_risk_once_and_keeps_fallback(
    database, tmp_path, complete, expected, source, partial, restarted,
):
    from backend.organism.live_engine import OrganismLiveEngine

    rows = [order(1, "buy", 6, 321), order(3, "sell", 5, 321.81)]
    if complete:
        rows.append(order(2, "sell", 1, 322.73))
    await store_rows(database, rows)
    broker = MagicMock()
    broker.get_all_positions = AsyncMock(return_value={})
    engine = OrganismLiveEngine(
        data_client=MagicMock(), order_service=broker, positions_service=broker,
        brain_dir=str(tmp_path / "brain"), universe=["TSLA"], sessionmaker=database,
    )
    engine._now_fn = lambda: CLOSE
    engine._time_fn = lambda: CLOSE.timestamp()
    engine._tick_count = 10
    engine._entry_metadata = {"TSLA": {
        "entry_order_id": str(ANCHOR), "entry_price": 321, "entry_tick": 1,
        "filled_shares": 6, "direction": 1, "entry_source": "alpha",
        "entry_time": START.timestamp(), "had_partial_exits": False,
    }}
    engine._last_exit_reason = {} if restarted else {"TSLA": "trailing_stop"}
    engine._save_brain = MagicMock()
    engine.kelly_sizer.record_trade = MagicMock()
    # Legacy lookups are unchanged; exercise only their documented fallback
    # result here because PostgreSQL's legacy JSON SQL is not SQLite portable.
    engine._lookup_exit_fill_from_db = AsyncMock(return_value=321.81)
    engine._lookup_entry_fill_from_db = AsyncMock(return_value=(321, 6))

    await engine._reconcile_fills({})
    assert len(engine._all_trades) == 1
    trade = engine._all_trades[0]
    assert trade.pnl == pytest.approx(expected)
    assert trade.shares == 6 and trade.price_source == source
    assert trade.had_partial_exits is partial
    assert trade.is_reconciliation_artifact is False
    assert engine.learner.state.cumulative_pnl == pytest.approx(expected)
    assert engine._symbol_daily_pnl["TSLA"] == pytest.approx(expected)
    engine.kelly_sizer.record_trade.assert_called_once_with("unknown", pytest.approx(expected))
    engine._save_brain.assert_called_once()
    if complete:
        engine._lookup_exit_fill_from_db.assert_not_awaited()
        engine._lookup_entry_fill_from_db.assert_not_awaited()
    await engine._reconcile_fills({})
    assert len(engine._all_trades) == 1
    engine._save_brain.assert_called_once()
    assert not broker.submit_order.called
