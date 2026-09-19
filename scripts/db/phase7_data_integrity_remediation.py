#!/usr/bin/env python3
"""Phase 7.7 dry-run-first paper data integrity remediation.

The default mode is read-only.  Apply mode requires an explicit confirmation
token and intentionally fixes only low-ambiguity issues:

* exact duplicate realized_trades rows, keeping the oldest row in each group;
* stale local orders that never reached a broker id and have a matching failed
  outbox order.submitted event.

It does not attempt to repair partial-fill accounting groups, rebuild PnL, or
delete outbox history.  Those require a separate accounting backfill plan.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.infra.db import init_db
from backend.infra.schemas import Order, OutboxEvent, Position, RealizedTrade

CONFIRM_TOKEN = "PHASE7_DATA_INTEGRITY_REMEDIATE"


@dataclass
class ExactDuplicateGroup:
    keep_id: str
    duplicate_ids: list[str]
    symbol: str
    qty: str
    realized_pnl: str
    close_order_id: str
    lot_id: str


@dataclass
class RelationDuplicateGroup:
    open_order_id: str
    close_order_id: str
    lot_id: str
    row_count: int
    exact_duplicate: bool


@dataclass
class StaleAcceptedOrder:
    order_id: str
    symbol: str
    side: str
    qty: str
    created_at: str
    outbox_event_id: str
    last_error: str


@dataclass
class RemediationReport:
    dry_run: bool
    applied: bool = False
    generated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    orders_by_status: dict[str, int] = field(default_factory=dict)
    nonzero_positions: int = 0
    outbox_by_status: dict[str, int] = field(default_factory=dict)
    realized_trades_count: int = 0
    exact_duplicate_groups: list[ExactDuplicateGroup] = field(default_factory=list)
    relation_duplicate_groups: list[RelationDuplicateGroup] = field(default_factory=list)
    stale_accepted_orders: list[StaleAcceptedOrder] = field(default_factory=list)
    exact_duplicate_rows_to_remove: int = 0
    stale_orders_to_mark_failed: int = 0
    deleted_realized_trade_ids: list[str] = field(default_factory=list)
    marked_failed_order_ids: list[str] = field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        return asdict(self)


def _iso(dt: datetime | None) -> str:
    return dt.isoformat() if dt is not None else ""


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _decimal_key(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.normalize(), "f")


def _json_key(value: Any) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"))


def _exact_realized_key(row: RealizedTrade) -> tuple[Any, ...]:
    return (
        row.user_id,
        row.symbol,
        _decimal_key(row.qty),
        _decimal_key(row.open_price),
        _decimal_key(row.close_price),
        _decimal_key(row.realized_pnl),
        _decimal_key(row.realized_pnl_percent),
        str(row.open_order_id),
        str(row.close_order_id),
        str(row.lot_id),
        _iso(row.open_date),
        _iso(row.close_date),
        _json_key(row.attributes),
    )


def _relation_key(row: RealizedTrade) -> tuple[str, str, str]:
    return (str(row.open_order_id), str(row.close_order_id), str(row.lot_id))


async def _all_realized(session: AsyncSession) -> list[RealizedTrade]:
    result = await session.execute(
        select(RealizedTrade).order_by(
            RealizedTrade.close_date.asc(),
            RealizedTrade.created_at.asc(),
            RealizedTrade.id.asc(),
        )
    )
    return list(result.scalars().all())


async def _status_counts(session: AsyncSession, model: Any) -> dict[str, int]:
    result = await session.execute(select(model.status))
    counts: dict[str, int] = {}
    for (status,) in result.all():
        counts[str(status)] = counts.get(str(status), 0) + 1
    return dict(sorted(counts.items()))


async def _nonzero_position_count(session: AsyncSession) -> int:
    result = await session.execute(select(Position.qty))
    count = 0
    for (qty,) in result.all():
        if Decimal(str(qty or 0)) != 0:
            count += 1
    return count


def _group_exact_duplicates(rows: list[RealizedTrade]) -> list[ExactDuplicateGroup]:
    by_key: dict[tuple[Any, ...], list[RealizedTrade]] = {}
    for row in rows:
        by_key.setdefault(_exact_realized_key(row), []).append(row)

    groups: list[ExactDuplicateGroup] = []
    for members in by_key.values():
        if len(members) <= 1:
            continue
        ordered = sorted(members, key=lambda r: (_aware(r.created_at) or datetime.min.replace(tzinfo=UTC), str(r.id)))
        keep = ordered[0]
        dupes = ordered[1:]
        groups.append(
            ExactDuplicateGroup(
                keep_id=str(keep.id),
                duplicate_ids=[str(row.id) for row in dupes],
                symbol=keep.symbol,
                qty=_decimal_key(keep.qty),
                realized_pnl=_decimal_key(keep.realized_pnl),
                close_order_id=str(keep.close_order_id),
                lot_id=str(keep.lot_id),
            )
        )
    return groups


def _group_relation_duplicates(
    rows: list[RealizedTrade],
    exact_groups: list[ExactDuplicateGroup],
) -> list[RelationDuplicateGroup]:
    exact_relation_keys = {
        (group.close_order_id, group.lot_id)
        for group in exact_groups
    }
    by_key: dict[tuple[str, str, str], list[RealizedTrade]] = {}
    for row in rows:
        by_key.setdefault(_relation_key(row), []).append(row)

    groups: list[RelationDuplicateGroup] = []
    for key, members in by_key.items():
        if len(members) <= 1:
            continue
        _open_id, close_id, lot_id = key
        groups.append(
            RelationDuplicateGroup(
                open_order_id=key[0],
                close_order_id=close_id,
                lot_id=lot_id,
                row_count=len(members),
                exact_duplicate=(close_id, lot_id) in exact_relation_keys,
            )
        )
    return groups


async def _failed_outbox_by_order(session: AsyncSession) -> dict[str, OutboxEvent]:
    result = await session.execute(
        select(OutboxEvent).where(
            OutboxEvent.topic == "order.submitted",
            OutboxEvent.status == "failed",
        )
    )
    by_order: dict[str, OutboxEvent] = {}
    for event in result.scalars().all():
        payload = event.payload or {}
        order_id = payload.get("order_id")
        if order_id:
            by_order[str(order_id)] = event
    return by_order


async def _stale_accepted_orders(
    session: AsyncSession,
    *,
    min_age: timedelta,
    now: datetime,
) -> list[StaleAcceptedOrder]:
    failed_by_order = await _failed_outbox_by_order(session)
    result = await session.execute(
        select(Order).where(
            Order.status == "accepted",
            Order.broker_order_id.is_(None),
            Order.filled_qty == 0,
        )
    )
    stale: list[StaleAcceptedOrder] = []
    for order in result.scalars().all():
        created = _aware(order.created_at) or now
        if now - created < min_age:
            continue
        event = failed_by_order.get(str(order.id))
        if event is None:
            continue
        stale.append(
            StaleAcceptedOrder(
                order_id=str(order.id),
                symbol=order.symbol,
                side=order.side,
                qty=_decimal_key(order.qty),
                created_at=_iso(order.created_at),
                outbox_event_id=str(event.id),
                last_error=(event.last_error or "")[:240],
            )
        )
    return stale


async def collect_report(
    session: AsyncSession,
    *,
    min_stale_order_age_hours: int = 24,
    now: datetime | None = None,
) -> RemediationReport:
    now = now or datetime.now(UTC)
    rows = await _all_realized(session)
    exact_groups = _group_exact_duplicates(rows)
    stale_orders = await _stale_accepted_orders(
        session,
        min_age=timedelta(hours=min_stale_order_age_hours),
        now=now,
    )
    report = RemediationReport(dry_run=True)
    report.orders_by_status = await _status_counts(session, Order)
    report.nonzero_positions = await _nonzero_position_count(session)
    report.outbox_by_status = await _status_counts(session, OutboxEvent)
    report.realized_trades_count = len(rows)
    report.exact_duplicate_groups = exact_groups
    report.relation_duplicate_groups = _group_relation_duplicates(rows, exact_groups)
    report.stale_accepted_orders = stale_orders
    report.exact_duplicate_rows_to_remove = sum(
        len(group.duplicate_ids) for group in exact_groups
    )
    report.stale_orders_to_mark_failed = len(stale_orders)
    return report


async def run_remediation(
    session: AsyncSession,
    *,
    apply: bool = False,
    confirm: str | None = None,
    min_stale_order_age_hours: int = 24,
) -> RemediationReport:
    report = await collect_report(
        session,
        min_stale_order_age_hours=min_stale_order_age_hours,
    )
    report.dry_run = not apply
    if not apply:
        return report
    if confirm != CONFIRM_TOKEN:
        raise ValueError(f"--apply requires --confirm {CONFIRM_TOKEN}")

    duplicate_ids = [
        uuid.UUID(row_id)
        for group in report.exact_duplicate_groups
        for row_id in group.duplicate_ids
    ]
    if duplicate_ids:
        result = await session.execute(
            select(RealizedTrade).where(RealizedTrade.id.in_(duplicate_ids))
        )
        for row in result.scalars().all():
            report.deleted_realized_trade_ids.append(str(row.id))
            await session.delete(row)

    stale_by_id = {row.order_id: row for row in report.stale_accepted_orders}
    if stale_by_id:
        result = await session.execute(
            select(Order).where(Order.id.in_([uuid.UUID(key) for key in stale_by_id]))
        )
        for order in result.scalars().all():
            stale = stale_by_id[str(order.id)]
            attrs = dict(order.attributes or {})
            attrs["phase7_data_integrity_cleanup"] = {
                "previous_status": order.status,
                "new_status": "failed",
                "reason": "failed_outbox_no_broker_id_zero_fill",
                "outbox_event_id": stale.outbox_event_id,
                "cleaned_at": datetime.now(UTC).isoformat(),
            }
            order.attributes = attrs
            order.status = "failed"
            report.marked_failed_order_ids.append(str(order.id))

    await session.commit()
    report.applied = True
    return report


async def _main_async(args: argparse.Namespace) -> int:
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        database_url = (
            "postgresql+asyncpg://trading:trading_password@localhost:5432/algotrading"
        )

    engine, sessionmaker = init_db(database_url)
    try:
        async with sessionmaker() as session:
            report = await run_remediation(
                session,
                apply=args.apply,
                confirm=args.confirm,
                min_stale_order_age_hours=args.min_stale_order_age_hours,
            )
        payload = report.to_jsonable()
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Database URL; defaults to DATABASE_URL")
    parser.add_argument("--output", help="Optional JSON report path")
    parser.add_argument("--apply", action="store_true", help="Apply safe remediation")
    parser.add_argument(
        "--confirm",
        help=f"Required with --apply; must equal {CONFIRM_TOKEN}",
    )
    parser.add_argument(
        "--min-stale-order-age-hours",
        type=int,
        default=24,
        help="Accepted orders younger than this are never marked terminal",
    )
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
