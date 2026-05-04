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
import ast
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
from backend.infra.schemas import Execution, Order, PositionLot, RealizedTrade
from backend.integrations.alpaca_stream import _decimal_or_none

CONFIRM_TOKEN = "BACKFILL_FILL_ACCOUNTING"
FILL_STATUSES = frozenset({"filled", "partially_filled", "expired"})
MONEY_QUANT = Decimal("0.000001")


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
    short_lots_to_create: int = 0
    realized_trades_to_create: int = 0
    short_realized_trades_to_create: int = 0
    open_lots_after: int = 0
    open_short_lots_after: int = 0
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


def _alpaca_response(order: Order) -> dict[str, Any]:
    attrs = getattr(order, "attributes", None) or {}
    raw = attrs.get("alpaca_response")
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _position_intent(order: Order) -> str:
    attrs = getattr(order, "attributes", None) or {}
    direct = attrs.get("position_intent")
    if isinstance(direct, str) and direct:
        return direct
    resp_intent = _alpaca_response(order).get("position_intent")
    if isinstance(resp_intent, str) and resp_intent:
        return resp_intent
    side = str(order.side).lower()
    return "buy_to_open" if side == "buy" else "sell_to_close"


def _accounting_action(order: Order) -> str:
    intent = _position_intent(order)
    side = str(order.side).lower()
    if intent == "sell_to_open":
        return "open_short"
    if intent == "buy_to_close":
        return "close_short"
    if intent == "buy_to_open":
        return "open_long"
    if intent == "sell_to_close":
        return "close_long"
    if side == "buy":
        return "open_long"
    if side == "sell":
        return "close_long"
    return f"unsupported:{side}"


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
    short: bool = False,
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
        if short:
            realized_pnl += qty_from_lot * (lot.cost_basis - close_price)
        else:
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
    sim_short_lots: dict[tuple[str, str], list[SimLot]] = {}
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

        action = _accounting_action(order)
        if action.startswith("unsupported:"):
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

        if action == "open_long":
            lots = sim_lots.setdefault(key, [])
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

        if action == "open_short":
            short_lots = sim_short_lots.setdefault(key, [])
            report.short_lots_to_create += 1
            short_lots.append(SimLot(
                user_id=user_id,
                symbol=order.symbol,
                qty=pending_qty,
                remaining_qty=pending_qty,
                cost_basis=price,
                order_id=str(order.id),
                open_date=order.submitted_at,
            ))
            continue

        lots = (
            sim_short_lots.setdefault(key, [])
            if action == "close_short"
            else sim_lots.setdefault(key, [])
        )
        realized_rows, realized_pnl, available = _close_sim_lots(
            lots,
            qty=pending_qty,
            close_price=price,
            short=action == "close_short",
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
        if action == "close_short":
            report.short_realized_trades_to_create += realized_rows
        else:
            report.realized_trades_to_create += realized_rows
        total_realized_pnl += realized_pnl

    report.open_lots_after = sum(
        1 for lots in sim_lots.values() for lot in lots if lot.remaining_qty > 0
    )
    report.open_short_lots_after = sum(
        1 for lots in sim_short_lots.values() for lot in lots if lot.remaining_qty > 0
    )
    report.realized_pnl = str(total_realized_pnl.quantize(MONEY_QUANT))
    return report, orders, existing_qty


async def _open_short_lots(
    session: AsyncSession,
    *,
    user_id: str,
    symbol: str,
) -> list[PositionLot]:
    stmt = (
        select(PositionLot)
        .join(Order, PositionLot.order_id == Order.id)
        .where(
            PositionLot.user_id == user_id,
            PositionLot.symbol == symbol,
            PositionLot.status == "open",
            PositionLot.remaining_qty > 0,
            Order.side == "sell",
        )
        .order_by(PositionLot.open_date.asc())
        .with_for_update()
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _open_long_lots(
    session: AsyncSession,
    *,
    user_id: str,
    symbol: str,
) -> list[PositionLot]:
    stmt = (
        select(PositionLot)
        .join(Order, PositionLot.order_id == Order.id)
        .where(
            PositionLot.user_id == user_id,
            PositionLot.symbol == symbol,
            PositionLot.status == "open",
            PositionLot.remaining_qty > 0,
            Order.side == "buy",
        )
        .order_by(PositionLot.open_date.asc())
        .with_for_update()
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _pending_incremental_fill(
    session: AsyncSession,
    order: Order,
    *,
    previous_filled_qty: Any,
    cumulative_filled_qty: Any,
    avg_fill_price: Any,
) -> tuple[Decimal, Decimal, Decimal] | dict[str, Any]:
    cumulative = _decimal_or_none(cumulative_filled_qty)
    previous = _decimal_or_none(previous_filled_qty) or Decimal("0")
    price = _decimal_or_none(avg_fill_price)
    if cumulative is None or cumulative <= 0:
        return {"applied": False, "reason": "missing_cumulative_fill_qty"}
    if price is None or price <= 0:
        return {"applied": False, "reason": "missing_avg_fill_price"}

    existing_stmt = select(func.coalesce(func.sum(Execution.fill_qty), 0)).where(
        Execution.order_id == order.id
    )
    existing_result = await session.execute(existing_stmt)
    existing_execution_qty = (
        _decimal_or_none(existing_result.scalar_one_or_none()) or Decimal("0")
    )
    effective_previous = (
        existing_execution_qty
        if existing_execution_qty > previous
        else previous
    )
    incremental = cumulative - effective_previous
    if incremental <= 0:
        return {"applied": False, "reason": "duplicate_or_stale_fill"}
    return incremental, price, existing_execution_qty


async def apply_long_fill_accounting(
    session: AsyncSession,
    order: Order,
    *,
    previous_filled_qty: Any,
    cumulative_filled_qty: Any,
    avg_fill_price: Any,
    fill_time: datetime | None = None,
    venue: str = "alpaca_backfill",
) -> dict[str, Any]:
    pending = await _pending_incremental_fill(
        session,
        order,
        previous_filled_qty=previous_filled_qty,
        cumulative_filled_qty=cumulative_filled_qty,
        avg_fill_price=avg_fill_price,
    )
    if isinstance(pending, dict):
        return pending
    incremental, price, _existing_execution_qty = pending

    fill_dt = fill_time or order.submitted_at or datetime.now()
    execution = Execution(
        order_id=order.id,
        fill_qty=incremental,
        fill_price=price,
        ts=fill_dt,
        venue=venue,
    )
    session.add(execution)

    user_id = _order_user_id(order)
    action = _accounting_action(order)
    realized = []
    if action == "open_long":
        lot = PositionLot(
            user_id=user_id,
            symbol=order.symbol,
            qty=incremental,
            remaining_qty=incremental,
            cost_basis=price,
            order_id=order.id,
            open_date=fill_dt,
            status="open",
        )
        session.add(lot)
    elif action == "close_long":
        remaining_to_close = incremental
        open_lots = await _open_long_lots(
            session, user_id=user_id, symbol=order.symbol
        )
        total_available = sum(lot.remaining_qty for lot in open_lots)
        if total_available < remaining_to_close:
            raise ValueError(
                f"Insufficient long lots for {user_id}/{order.symbol}: "
                f"need {remaining_to_close}, available {total_available}"
            )
        for lot in open_lots:
            if remaining_to_close <= 0:
                break
            qty_from_lot = min(lot.remaining_qty, remaining_to_close)
            realized_pnl = qty_from_lot * (price - lot.cost_basis)
            realized_pnl_percent = (
                ((price - lot.cost_basis) / lot.cost_basis * 100)
                if lot.cost_basis != 0
                else Decimal("0")
            )
            rt = RealizedTrade(
                user_id=user_id,
                symbol=order.symbol,
                qty=qty_from_lot,
                open_price=lot.cost_basis,
                close_price=price,
                realized_pnl=realized_pnl,
                realized_pnl_percent=realized_pnl_percent,
                open_order_id=lot.order_id,
                close_order_id=order.id,
                lot_id=lot.id,
                open_date=lot.open_date,
                close_date=fill_dt,
                attributes={},
            )
            session.add(rt)
            realized.append(rt)
            lot.remaining_qty -= qty_from_lot
            if lot.remaining_qty == 0:
                lot.status = "closed"
            remaining_to_close -= qty_from_lot
    else:
        return {"applied": False, "reason": f"not_long_action:{action}"}

    await session.flush()
    return {
        "applied": True,
        "side": str(order.side).lower(),
        "position_side": "long",
        "action": action,
        "incremental_qty": str(incremental),
        "execution_id": str(execution.id),
        "realized_count": len(realized),
        "realized_pnl": str(sum(t.realized_pnl for t in realized)),
    }


async def apply_short_fill_accounting(
    session: AsyncSession,
    order: Order,
    *,
    previous_filled_qty: Any,
    cumulative_filled_qty: Any,
    avg_fill_price: Any,
    fill_time: datetime | None = None,
    venue: str = "alpaca_backfill",
) -> dict[str, Any]:
    pending = await _pending_incremental_fill(
        session,
        order,
        previous_filled_qty=previous_filled_qty,
        cumulative_filled_qty=cumulative_filled_qty,
        avg_fill_price=avg_fill_price,
    )
    if isinstance(pending, dict):
        return pending
    incremental, price, _existing_execution_qty = pending

    fill_dt = fill_time or order.submitted_at or datetime.now()
    execution = Execution(
        order_id=order.id,
        fill_qty=incremental,
        fill_price=price,
        ts=fill_dt,
        venue=venue,
    )
    session.add(execution)

    user_id = _order_user_id(order)
    action = _accounting_action(order)
    realized = []
    if action == "open_short":
        lot = PositionLot(
            user_id=user_id,
            symbol=order.symbol,
            qty=incremental,
            remaining_qty=incremental,
            cost_basis=price,
            order_id=order.id,
            open_date=fill_dt,
            status="open",
        )
        session.add(lot)
    elif action == "close_short":
        remaining_to_close = incremental
        open_lots = await _open_short_lots(
            session, user_id=user_id, symbol=order.symbol
        )
        total_available = sum(lot.remaining_qty for lot in open_lots)
        if total_available < remaining_to_close:
            raise ValueError(
                f"Insufficient short lots for {user_id}/{order.symbol}: "
                f"need {remaining_to_close}, available {total_available}"
            )
        for lot in open_lots:
            if remaining_to_close <= 0:
                break
            qty_from_lot = min(lot.remaining_qty, remaining_to_close)
            realized_pnl = qty_from_lot * (lot.cost_basis - price)
            realized_pnl_percent = (
                ((lot.cost_basis - price) / lot.cost_basis * 100)
                if lot.cost_basis != 0
                else Decimal("0")
            )
            rt = RealizedTrade(
                user_id=user_id,
                symbol=order.symbol,
                qty=qty_from_lot,
                open_price=lot.cost_basis,
                close_price=price,
                realized_pnl=realized_pnl,
                realized_pnl_percent=realized_pnl_percent,
                open_order_id=lot.order_id,
                close_order_id=order.id,
                lot_id=lot.id,
                open_date=lot.open_date,
                close_date=fill_dt,
                attributes={"position_side": "short"},
            )
            session.add(rt)
            realized.append(rt)
            lot.remaining_qty -= qty_from_lot
            if lot.remaining_qty == 0:
                lot.status = "closed"
            remaining_to_close -= qty_from_lot
    else:
        return {"applied": False, "reason": f"not_short_action:{action}"}

    await session.flush()
    return {
        "applied": True,
        "side": str(order.side).lower(),
        "position_side": "short",
        "action": action,
        "incremental_qty": str(incremental),
        "execution_id": str(execution.id),
        "realized_count": len(realized),
        "realized_pnl": str(sum(t.realized_pnl for t in realized)),
    }


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
        action = _accounting_action(order)
        if action in ("open_short", "close_short"):
            result = await apply_short_fill_accounting(
                session,
                order,
                previous_filled_qty=already_executed,
                cumulative_filled_qty=filled_qty,
                avg_fill_price=order.avg_fill_price,
                fill_time=order.submitted_at,
            )
        else:
            result = await apply_long_fill_accounting(
                session,
                order,
                previous_filled_qty=already_executed,
                cumulative_filled_qty=filled_qty,
                avg_fill_price=order.avg_fill_price,
                fill_time=order.submitted_at,
            )
        report.applied_results.append({
            k: v for k, v in result.items()
            if k in {
                "action",
                "applied",
                "reason",
                "side",
                "position_side",
                "incremental_qty",
                "execution_id",
            }
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
