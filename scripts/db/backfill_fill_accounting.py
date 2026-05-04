#!/usr/bin/env python3
"""Dry-run-first backfill for broker fill accounting tables.

Reconstructs missing ``executions``, ``position_lots``, and
``realized_trades`` from existing filled orders.  The default mode is a
read-only simulation.  Apply mode requires an explicit confirmation token
and aborts before writing if the simulated FIFO sequence has errors.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import init_db
from backend.infra.schemas import Execution, Order
from backend.integrations.alpaca_stream import (
    _decimal_or_none,
    apply_incremental_fill_accounting,
)

CONFIRM_TOKEN = "BACKFILL_FILL_ACCOUNTING"
FILL_STATUSES = frozenset({"filled", "partially_filled", "expired"})


@dataclass
class SimLot:
    user_id: str
    symbol: str
    qty: Decimal
    remaining_qty: Decimal
    cost_basis: Decimal
    order_id: str
    open_date: datetime | None


@dataclass
class BackfillError:
    order_id: str
    symbol: str
    side: str
    reason: str
    qty: str


@dataclass
class BackfillReport:
    dry_run: bool
    applied: bool = False
    orders_seen: int = 0
    candidate_orders: int = 0
    skipped_existing_execution: int = 0
    skipped_missing_price: int = 0
    skipped_unsupported_side: int = 0
    executions_to_create: int = 0
    position_lots_to_create: int = 0
    realized_trades_to_create: int = 0
    open_lots_after: int = 0
    realized_pnl: str = "0"
    errors: list[BackfillError] = field(default_factory=list)
    applied_results: list[dict[str, Any]] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        data = asdict(self)
        data["errors"] = [asdict(err) for err in self.errors]
        return data


def _order_user_id(order: Order) -> str:
    return (
        (order.attributes or {}).get("user_id")
        if getattr(order, "attributes", None)
        else None
    ) or getattr(order, "user_id", None) or "system"


async def _execution_qty_by_order(session: AsyncSession) -> dict[Any, Decimal]:
    stmt = select(
        Execution.order_id,
        func.coalesce(func.sum(Execution.fill_qty), 0),
    ).group_by(Execution.order_id)
    result = await session.execute(stmt)
    return {
        order_id: _decimal_or_none(qty) or Decimal("0")
        for order_id, qty in result.all()
    }


async def _filled_orders(session: AsyncSession, *, limit: int | None = None) -> list[Order]:
    stmt = (
        select(Order)
        .where(
            Order.filled_qty > 0,
            Order.status.in_(tuple(FILL_STATUSES)),
        )
        .order_by(Order.submitted_at.asc(), Order.created_at.asc(), Order.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _close_sim_lots(
    lots: list[SimLot],
    *,
    qty: Decimal,
    close_price: Decimal,
) -> tuple[int, Decimal, Decimal]:
    available = sum(lot.remaining_qty for lot in lots)
    if available < qty:
        return 0, Decimal("0"), available

    remaining = qty
    realized_rows = 0
    realized_pnl = Decimal("0")
    for lot in lots:
        if remaining <= 0:
            break
        qty_from_lot = min(lot.remaining_qty, remaining)
        lot.remaining_qty -= qty_from_lot
        remaining -= qty_from_lot
        realized_rows += 1
        realized_pnl += qty_from_lot * (close_price - lot.cost_basis)

    lots[:] = [lot for lot in lots if lot.remaining_qty > 0]
    return realized_rows, realized_pnl, available


async def plan_backfill(
    session: AsyncSession,
    *,
    limit: int | None = None,
) -> tuple[BackfillReport, list[Order], dict[Any, Decimal]]:
    report = BackfillReport(dry_run=True)
    orders = await _filled_orders(session, limit=limit)
    existing_qty = await _execution_qty_by_order(session)
    report.orders_seen = len(orders)

    sim_lots: dict[tuple[str, str], list[SimLot]] = {}
    total_realized_pnl = Decimal("0")

    for order in orders:
        filled_qty = _decimal_or_none(order.filled_qty) or Decimal("0")
        already_executed = existing_qty.get(order.id, Decimal("0"))
        pending_qty = filled_qty - already_executed
        if pending_qty <= 0:
            report.skipped_existing_execution += 1
            continue

        report.candidate_orders += 1
        price = _decimal_or_none(order.avg_fill_price)
        if price is None or price <= 0:
            report.skipped_missing_price += 1
            report.errors.append(BackfillError(
                order_id=str(order.id),
                symbol=order.symbol,
                side=order.side,
                reason="missing_avg_fill_price",
                qty=str(pending_qty),
            ))
            continue

        side = str(order.side).lower()
        if side not in ("buy", "sell"):
            report.skipped_unsupported_side += 1
            report.errors.append(BackfillError(
                order_id=str(order.id),
                symbol=order.symbol,
                side=order.side,
                reason=f"unsupported_side:{order.side}",
                qty=str(pending_qty),
            ))
            continue

        report.executions_to_create += 1
        user_id = _order_user_id(order)
        key = (user_id, order.symbol)
        lots = sim_lots.setdefault(key, [])

        if side == "buy":
            report.position_lots_to_create += 1
            lots.append(SimLot(
                user_id=user_id,
                symbol=order.symbol,
                qty=pending_qty,
                remaining_qty=pending_qty,
                cost_basis=price,
                order_id=str(order.id),
                open_date=order.submitted_at,
            ))
            continue

        realized_rows, realized_pnl, available = _close_sim_lots(
            lots,
            qty=pending_qty,
            close_price=price,
        )
        if realized_rows == 0:
            report.errors.append(BackfillError(
                order_id=str(order.id),
                symbol=order.symbol,
                side=order.side,
                reason=f"insufficient_lots:available={available}",
                qty=str(pending_qty),
            ))
            continue
        report.realized_trades_to_create += realized_rows
        total_realized_pnl += realized_pnl

    report.open_lots_after = sum(
        1 for lots in sim_lots.values() for lot in lots if lot.remaining_qty > 0
    )
    report.realized_pnl = str(total_realized_pnl)
    return report, orders, existing_qty


async def run_backfill(
    session: AsyncSession,
    *,
    apply: bool = False,
    confirm: str | None = None,
    limit: int | None = None,
) -> BackfillReport:
    report, orders, existing_qty = await plan_backfill(session, limit=limit)
    report.dry_run = not apply

    if not apply:
        return report
    if confirm != CONFIRM_TOKEN:
        raise ValueError(f"--apply requires --confirm {CONFIRM_TOKEN}")
    if report.errors:
        raise ValueError("backfill simulation has errors; refusing to apply")

    for order in orders:
        filled_qty = _decimal_or_none(order.filled_qty) or Decimal("0")
        already_executed = existing_qty.get(order.id, Decimal("0"))
        if filled_qty - already_executed <= 0:
            continue
        result = await apply_incremental_fill_accounting(
            session,
            order,
            previous_filled_qty=already_executed,
            cumulative_filled_qty=filled_qty,
            avg_fill_price=order.avg_fill_price,
            status=order.status,
            fill_time=order.submitted_at,
            venue="alpaca_backfill",
        )
        report.applied_results.append({
            k: v for k, v in result.items()
            if k in {"applied", "reason", "side", "incremental_qty", "execution_id"}
        })

    await session.commit()
    report.applied = True
    return report


async def _main_async(args: argparse.Namespace) -> int:
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        database_url = "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"

    engine, sessionmaker = init_db(database_url)
    try:
        async with sessionmaker() as session:
            report = await run_backfill(
                session,
                apply=args.apply,
                confirm=args.confirm,
                limit=args.limit,
            )
        payload = report.to_jsonable()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            mode = "APPLIED" if report.applied else "DRY-RUN"
            print(f"{mode}: {json.dumps(payload, indent=2, sort_keys=True)}")
        return 1 if report.errors else 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Database URL; defaults to DATABASE_URL")
    parser.add_argument("--limit", type=int, help="Limit filled orders for rehearsal")
    parser.add_argument("--json", action="store_true", help="Print pure JSON")
    parser.add_argument("--apply", action="store_true", help="Write missing accounting rows")
    parser.add_argument(
        "--confirm",
        help=f"Required with --apply; must equal {CONFIRM_TOKEN}",
    )
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
