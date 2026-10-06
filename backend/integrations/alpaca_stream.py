"""
Alpaca WebSocket Stream Integration for Real-time Order Updates

This module provides real-time order status updates via Alpaca's WebSocket stream.
Handles trade_updates events and updates the local database with order status changes.

Key Features:
- Real-time order status updates (new -> filled -> etc)
- Automatic reconnection with exponential backoff
- Backpressure handling for high-frequency updates
- Comprehensive error handling and logging
- Integration with existing order repository
"""

import asyncio
import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
import os
import time
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from backend.config import get_settings
from backend.infra.db import get_session_context
from backend.infra.repositories.orders import OrdersRepo
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _dict_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _order_attributes(order: Any) -> dict[str, Any]:
    attrs = getattr(order, "attributes", None)
    return attrs if isinstance(attrs, dict) else {}


def _alpaca_response(order: Any) -> dict[str, Any]:
    return _dict_or_empty(_order_attributes(order).get("alpaca_response"))


def _position_intent(
    order: Any,
    *,
    broker_order_data: dict[str, Any] | None = None,
) -> str:
    broker_intent = _dict_or_empty(broker_order_data).get("position_intent")
    if isinstance(broker_intent, str) and broker_intent:
        return broker_intent

    attrs = _order_attributes(order)
    direct = attrs.get("position_intent")
    if isinstance(direct, str) and direct:
        return direct

    response_intent = _alpaca_response(order).get("position_intent")
    if isinstance(response_intent, str) and response_intent:
        return response_intent

    side = str(getattr(order, "side", "")).lower()
    return "buy_to_open" if side == "buy" else "sell_to_close"


def _accounting_action(
    order: Any,
    *,
    broker_order_data: dict[str, Any] | None = None,
) -> str:
    intent = _position_intent(order, broker_order_data=broker_order_data)
    side = str(getattr(order, "side", "")).lower()
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


def _owner(attributes: Any, column_user_id: Any) -> str:
    """Lot owner: attributes.user_id, then the order's user_id, then 'system'."""
    return (
        (attributes.get("user_id") if isinstance(attributes, dict) else None)
        or column_user_id
        or "system"
    )


def _order_user_id(order: Any) -> str:
    return _owner(_order_attributes(order), getattr(order, "user_id", None))


# Audit 2026-10-05 C07-01: ingestion paths are not globally ordered (recovery
# pages by id, gap-fill by update time, startup sync runs recovery before its
# page), so a close can be applied before the opening fill it consumes. Two
# rules keep the lot ledger convergent whatever the delay:
# 1. Deferral. While an earlier same-owner opening that persisted-order
#    recovery retries is unresolved, the close stays retryable as before. The
#    window is anchored to the close (the opening was submitted at or before
#    it and at most LOT_ORDERING_GRACE earlier), so a restart after any outage
#    shorter than LOT_ORDERING_MAX_AGE still applies both legs in order. The
#    cap bounds how long a stuck opening row can keep a broker-confirmed close
#    unpersisted.
# 2. Late netting. Otherwise the close is persisted and its deficit recorded
#    in attributes.lot_accounting. An opening lot ingested later is netted
#    against that record (_net_recorded_unmatched_closes), so an opening that
#    was never acknowledged, is outside recovery scope or is older than the cap
#    cannot leave a phantom open lot either.
# Both rules order legs by submission time; broker fill times are not ingested.
LOT_ORDERING_GRACE = timedelta(days=5)
LOT_ORDERING_MAX_AGE = timedelta(days=45)
_LOT_QUANTUM = Decimal("0.000001")  # DECIMAL(18, 6), as the ledger columns


class LotAccountingDeferred(ValueError):
    """A close outran an earlier opening fill that can still be ingested.

    Raised before any lot changes, so every caller rolls back and retries the
    snapshot exactly as it did before for lot errors (stream retry, persisted
    order recovery, reconnect gap-fill, startup sync, outbox acknowledgement).
    It must stay a ValueError: startup sync catches a fixed list of exception
    types and goes on with the rest of its page.
    """


async def _unsettled_earlier_opening(
    session: AsyncSession,
    *,
    close_order_id: Any,
    close_submitted_at: datetime | None,
    user_id: str,
    symbol: str,
    open_side: str,
) -> Any | None:
    """Earlier same-owner opening order whose broker fill may still arrive.

    Qualifies: an opening-side order in persisted-order recovery's scope
    (unresolved, broker-acknowledged, organism or outbox lineage, so recovery
    keeps retrying it), submitted at or before the close and at most
    LOT_ORDERING_GRACE before it, and less than LOT_ORDERING_MAX_AGE old. Any
    other row cannot be relied on to settle and must not keep a
    broker-confirmed close unpersisted; if its fill lands later anyway, its
    lot is netted against the recorded unmatched close.
    """
    from backend.infra.schemas import Order

    now = datetime.now(UTC)
    anchor = close_submitted_at if close_submitted_at is not None else now
    rows = await session.execute(
        select(Order.id, Order.user_id, Order.attributes)
        .where(
            # The same row scope persisted-order recovery pages through.
            *OrdersRepo._recovery_scope(),
            Order.symbol == symbol,
            Order.side == open_side,
            Order.id != close_order_id,
            Order.submitted_at <= anchor,
            Order.submitted_at >= anchor - LOT_ORDERING_GRACE,
            Order.submitted_at >= now - LOT_ORDERING_MAX_AGE,
        )
        .order_by(Order.submitted_at.asc(), Order.id.asc())
    )
    for order_id, column_user_id, attributes in rows.all():
        if _owner(attributes, column_user_id) == user_id:
            return order_id
    return None


def _realized_trade(
    *,
    lot: Any,
    qty: Decimal,
    close_price: Decimal,
    close_order_id: Any,
    close_date: datetime,
    user_id: str,
    symbol: str,
    position_side: str,
    attributes: dict[str, Any] | None = None,
) -> Any:
    """One RealizedTrade closing ``qty`` of ``lot`` at ``close_price``."""
    from backend.infra.schemas import RealizedTrade

    if position_side == "short":
        realized_pnl = qty * (lot.cost_basis - close_price)
        realized_pnl_percent = (
            ((lot.cost_basis - close_price) / lot.cost_basis * 100)
            if lot.cost_basis != 0
            else Decimal("0")
        )
        trade_attributes = {"position_side": "short"}
    else:
        realized_pnl = qty * (close_price - lot.cost_basis)
        realized_pnl_percent = (
            ((close_price - lot.cost_basis) / lot.cost_basis * 100)
            if lot.cost_basis != 0
            else Decimal("0")
        )
        trade_attributes = {}
    return RealizedTrade(
        user_id=user_id,
        symbol=symbol,
        qty=qty,
        open_price=lot.cost_basis,
        close_price=close_price,
        realized_pnl=realized_pnl,
        realized_pnl_percent=realized_pnl_percent,
        open_order_id=lot.order_id,
        close_order_id=close_order_id,
        lot_id=lot.id,
        open_date=lot.open_date,
        close_date=close_date,
        attributes={**trade_attributes, **(attributes or {})},
    )


async def _close_position_lots_fifo(
    session: AsyncSession,
    *,
    user_id: str,
    symbol: str,
    qty_to_close: Decimal,
    close_price: Decimal,
    close_order_id: Any,
    close_date: datetime,
    open_side: str,
    position_side: str,
    close_submitted_at: datetime | None = None,
) -> tuple[list[Any], Decimal]:
    """FIFO-close the owner's open lots; return realized trades and the remainder.

    A broker-confirmed close is never refused for missing lots (C07-01): any
    quantity without an open lot is returned unmatched for the caller to record.
    It is deferred (LotAccountingDeferred, before any change) only while an
    earlier same-owner opening fill can still be ingested
    (_unsettled_earlier_opening).
    """
    from backend.infra.schemas import Order, PositionLot

    stmt = (
        select(PositionLot)
        .join(Order, PositionLot.order_id == Order.id)
        .where(
            PositionLot.user_id == user_id,
            PositionLot.symbol == symbol,
            PositionLot.status == "open",
            PositionLot.remaining_qty > 0,
            Order.side == open_side,
        )
        .order_by(PositionLot.open_date.asc())
        .with_for_update()
    )
    result = await session.execute(stmt)
    open_lots = list(result.scalars().all())

    total_available = sum((lot.remaining_qty for lot in open_lots), Decimal("0"))
    if total_available < qty_to_close:
        pending_open = await _unsettled_earlier_opening(
            session,
            close_order_id=close_order_id,
            close_submitted_at=close_submitted_at,
            user_id=user_id,
            symbol=symbol,
            open_side=open_side,
        )
        if pending_open is not None:
            raise LotAccountingDeferred(
                f"Close of {qty_to_close} {symbol} for {user_id} deferred: "
                f"{total_available} open {position_side} lots while earlier "
                f"opening order {pending_open} is unresolved"
            )

    remaining_to_close = qty_to_close
    realized_trades = []
    for lot in open_lots:
        if remaining_to_close <= 0:
            break

        qty_from_lot = min(lot.remaining_qty, remaining_to_close)
        realized_trade = _realized_trade(
            lot=lot,
            qty=qty_from_lot,
            close_price=close_price,
            close_order_id=close_order_id,
            close_date=close_date,
            user_id=user_id,
            symbol=symbol,
            position_side=position_side,
        )
        session.add(realized_trade)
        realized_trades.append(realized_trade)

        lot.remaining_qty -= qty_from_lot
        if lot.remaining_qty == 0:
            lot.status = "closed"
        remaining_to_close -= qty_from_lot

    await session.flush()
    return realized_trades, remaining_to_close


def _quantized(value: Decimal) -> str:
    return str(value.quantize(_LOT_QUANTUM))


def _record_decimal(record: dict[str, Any], key: str, default: Decimal = Decimal("0")) -> Decimal:
    value = _decimal_or_none(record.get(key))
    return value if value is not None and value.is_finite() else default


def _record_count(record: dict[str, Any], key: str) -> int:
    try:
        return max(int(record.get(key) or 0), 0)
    except (TypeError, ValueError):
        return 0


def _lot_accounting_record(order: Any, discrepancy: dict[str, Any]) -> dict[str, Any]:
    """Durable, cumulative ``attributes.lot_accounting`` for an unmatched close.

    Quantities, prices and notionals are stored at the ledger's 6 dp. The
    unmatched notional (sum of unmatched quantity x leg price) prices a later
    late match. Late-match history of the same close is kept.
    """
    previous = _order_attributes(order).get("lot_accounting")
    if not isinstance(previous, dict) or previous.get("status") not in ("unmatched", "matched_late"):
        previous = {}
    unmatched_leg = Decimal(discrepancy["unmatched_qty"])
    leg_price = Decimal(discrepancy["fill_price"])
    return {
        **previous,
        "status": "unmatched",
        "repair": "required",
        "reason": discrepancy["reason"],
        "owner": discrepancy["owner"],
        "position_side": discrepancy["position_side"],
        "unmatched_qty": _quantized(_record_decimal(previous, "unmatched_qty") + unmatched_leg),
        "unmatched_notional": _quantized(
            _record_decimal(previous, "unmatched_notional") + unmatched_leg * leg_price
        ),
        "matched_qty": _quantized(
            _record_decimal(previous, "matched_qty") + Decimal(discrepancy["matched_qty"])
        ),
        "events": _record_count(previous, "events") + 1,
        "last_fill_qty": _quantized(Decimal(discrepancy["fill_qty"])),
        "last_fill_price": _quantized(leg_price),
        "last_execution_id": discrepancy["execution_id"],
        "recorded_at": datetime.now(UTC).isoformat(),
    }


def _open_unmatched_record(attributes: Any, user_id: str, position_side: str) -> dict[str, Any] | None:
    """The close's lot_accounting record if it still has unmatched quantity for this owner/side."""
    record = attributes.get("lot_accounting") if isinstance(attributes, dict) else None
    if (
        isinstance(record, dict)
        and record.get("status") == "unmatched"
        and record.get("owner") == user_id
        and record.get("position_side") == position_side
        and _record_decimal(record, "unmatched_qty") > 0
    ):
        return record
    return None


async def _net_recorded_unmatched_closes(
    session: AsyncSession,
    *,
    lot: Any,
    opening: Any,
    user_id: str,
    close_side: str,
    position_side: str,
) -> list[dict[str, Any]]:
    """Net a newly opened lot against closes already recorded unmatched (C07-01).

    A close applied before its opening fill is recorded unmatched when no
    deferral applied (the opening was never acknowledged, is outside recovery
    scope or is older than LOT_ORDERING_MAX_AGE). When that opening fill lands,
    its lot is closed FIFO against the owner's unmatched closes of this symbol
    and position side submitted at or after the opening and at most
    LOT_ORDERING_GRACE later, as FIFO would have matched them in order: one
    RealizedTrade per match at the close's unmatched VWAP, and the record moves
    to ``matched_late`` once nothing remains unmatched. A close submitted before
    the opening never consumes it.

    Locking: the caller already holds the opening row; each candidate close row
    is locked and re-read here before its record changes, so a concurrent
    ingestion of that close serializes with the netting. Should that ingestion
    be FIFO-locking an earlier lot of this same opening, PostgreSQL reports a
    deadlock and the losing transaction is retried by its ingress like any
    other transient failure.
    """
    from backend.infra.schemas import Order

    opened_at = getattr(opening, "submitted_at", None)
    if opened_at is None or not lot.remaining_qty > 0:
        return []
    candidates = await session.execute(
        select(Order.id, Order.attributes)
        .where(
            Order.symbol == opening.symbol,
            Order.side == close_side,
            Order.id != opening.id,
            Order.submitted_at >= opened_at,
            Order.submitted_at <= opened_at + LOT_ORDERING_GRACE,
        )
        .order_by(Order.submitted_at.asc(), Order.id.asc())
    )
    close_ids = [
        order_id
        for order_id, attributes in candidates.all()
        if _open_unmatched_record(attributes, user_id, position_side) is not None
    ]
    matches: list[dict[str, Any]] = []
    for close_id in close_ids:
        if not lot.remaining_qty > 0:
            break
        close = (
            await session.execute(
                select(Order)
                .where(Order.id == close_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        record = _open_unmatched_record(getattr(close, "attributes", None), user_id, position_side)
        if record is None:
            continue
        unmatched = _record_decimal(record, "unmatched_qty")
        notional = _record_decimal(
            record, "unmatched_notional", unmatched * _record_decimal(record, "last_fill_price")
        )
        price = (notional / unmatched).quantize(_LOT_QUANTUM)
        if not price.is_finite() or price <= 0:
            continue  # A malformed record stays unmatched for repair.
        qty = min(unmatched, lot.remaining_qty)
        trade = _realized_trade(
            lot=lot,
            qty=qty,
            close_price=price,
            close_order_id=close.id,
            close_date=close.submitted_at,
            user_id=user_id,
            symbol=opening.symbol,
            position_side=position_side,
            attributes={"lot_accounting": "matched_late"},
        )
        session.add(trade)
        lot.remaining_qty -= qty
        if lot.remaining_qty == 0:
            lot.status = "closed"
        left = unmatched - qty
        updated = {
            **record,
            "status": "unmatched" if left > 0 else "matched_late",
            "repair": "required" if left > 0 else "none",
            "unmatched_qty": _quantized(left),
            "unmatched_notional": _quantized(notional - qty * price if left > 0 else Decimal("0")),
            "matched_late_qty": _quantized(_record_decimal(record, "matched_late_qty") + qty),
            "late_matches": _record_count(record, "late_matches") + 1,
            "last_late_match": {
                "opening_order_id": str(opening.id),
                "lot_id": str(lot.id),
                "qty": _quantized(qty),
                "price": _quantized(price),
                "matched_at": datetime.now(UTC).isoformat(),
            },
        }
        await OrdersRepo(session).attach_broker_result(close.id, attributes={"lot_accounting": updated})
        matches.append({
            "symbol": str(opening.symbol),
            "owner": user_id,
            "position_side": position_side,
            "opening_order_id": str(opening.id),
            "close_order_id": str(close.id),
            "qty": _quantized(qty),
            "price": _quantized(price),
            "realized_pnl": str(trade.realized_pnl),
            "close_status": updated["status"],
            "close_unmatched_qty": updated["unmatched_qty"],
        })
    if matches:
        await session.flush()
    return matches


def log_lot_accounting_discrepancy(accounting: dict[str, Any] | None, *, ingress: str) -> None:
    """Report lot-accounting outcomes of a committed snapshot; callers invoke it after commit.

    A persisted unmatched close pages once (CRITICAL). A late match of a new
    opening lot against an earlier unmatched close is logged at WARNING: it
    resolves (part of) a discrepancy that has already paged.
    """
    for match in (accounting or {}).get("lot_late_matches") or ():
        logger.warning(
            "LOT ACCOUNTING LATE MATCH: %s %s of opening order %s closed against close order %s, "
            "which was recorded unmatched earlier; %s shares of that close remain unmatched "
            "(ingress=%s)",
            match.get("qty"), match.get("symbol"), match.get("opening_order_id"),
            match.get("close_order_id"), match.get("close_unmatched_qty"), ingress,
            owner=match.get("owner"),
            price=match.get("price"),
            realized_pnl=match.get("realized_pnl"),
            close_status=match.get("close_status"),
        )
    discrepancy = (accounting or {}).get("lot_discrepancy")
    if not discrepancy:
        return
    logger.critical(
        "LOT ACCOUNTING DISCREPANCY: broker-confirmed %s fill of %s %s persisted for order %s, "
        "but %s shares matched no open %s lots for owner %s; recorded in "
        "orders.attributes.lot_accounting for repair (ingress=%s)",
        discrepancy.get("side"), discrepancy.get("fill_qty"), discrepancy.get("symbol"),
        discrepancy.get("order_id"), discrepancy.get("unmatched_qty"),
        discrepancy.get("position_side"), discrepancy.get("owner"), ingress,
        reason=discrepancy.get("reason"),
        execution_id=discrepancy.get("execution_id"),
    )


async def apply_incremental_fill_accounting(
    session: AsyncSession,
    order: Any,
    *,
    previous_filled_qty: Any,
    cumulative_filled_qty: Any,
    avg_fill_price: Any,
    status: str,
    fill_time: datetime | None = None,
    venue: str = "alpaca",
    broker_order_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist execution + lot accounting for the positive incremental fill.

    Alpaca reports cumulative ``filled_qty``.  This helper is intentionally
    side-effect-free for duplicate/stale updates and records exactly the
    delta that has not already been represented by execution rows. A close
    whose owner has no (or too few) open lots still records its execution and
    any matched lots; the unmatched remainder is returned as ``lot_discrepancy``.
    A new opening lot is first netted against earlier-recorded unmatched closes
    it precedes (``lot_late_matches``).
    """
    if status not in ("filled", "partially_filled", "canceled", "cancelled", "expired"):
        return {"applied": False, "reason": "non_fill_status"}

    cumulative = _decimal_or_none(cumulative_filled_qty)
    previous = _decimal_or_none(previous_filled_qty) or Decimal("0")
    price = _decimal_or_none(avg_fill_price)
    if (
        isinstance(cumulative_filled_qty, bool)
        or cumulative is None
        or not cumulative.is_finite()
        or cumulative < 0
    ):
        raise ValueError("Invalid cumulative fill quantity")
    if cumulative == 0:
        return {"applied": False, "reason": "missing_cumulative_fill_qty"}
    if isinstance(avg_fill_price, bool) or price is None or not price.is_finite() or price <= 0:
        raise ValueError("Invalid cumulative fill price")
    if not getattr(order, "id", None):
        return {"applied": False, "reason": "missing_order_id"}
    if not getattr(order, "symbol", None) or not getattr(order, "side", None):
        return {"applied": False, "reason": "missing_symbol_or_side"}
    side = str(order.side).lower()
    if side not in ("buy", "sell"):
        return {"applied": False, "reason": f"unsupported_side:{order.side}"}
    action = _accounting_action(order, broker_order_data=broker_order_data)

    from backend.infra.schemas import Execution, Order, PositionLot

    # Every ingestion path locks the same persisted order before reading its
    # accounting watermark. Locks remain held until the caller commits all
    # summary/execution/lot effects together (SQLite fixtures serialize writes).
    locked = await session.execute(select(Order.id).where(Order.id == order.id).with_for_update())
    if locked.scalar_one_or_none() is None:
        raise ValueError("Cannot account a missing order")

    existing_stmt = select(func.coalesce(func.sum(Execution.fill_qty), 0)).where(
        Execution.order_id == order.id
    )
    existing_result = await session.execute(existing_stmt)
    existing_execution_qty = _decimal_or_none(existing_result.scalar_one_or_none()) or Decimal("0")
    cash_result = await session.execute(
        select(func.coalesce(func.sum(Execution.fill_qty * Execution.fill_price), 0)).where(
            Execution.order_id == order.id
        )
    )
    existing_cash = _decimal_or_none(cash_result.scalar_one_or_none()) or Decimal("0")
    if not existing_execution_qty.is_finite() or not existing_cash.is_finite():
        raise ValueError("Nonfinite persisted fill cashflow")
    incremental = cumulative - existing_execution_qty
    target_cash = cumulative * price
    cash_delta = target_cash - existing_cash
    # Stored DECIMAL prices have six decimal places. Permit only the rounding
    # envelope of that representation, not a material correction to history.
    tolerance = cumulative * Decimal("0.0000005") + Decimal("0.000001")
    if incremental < 0:
        return {"applied": False, "reason": "duplicate_or_stale_fill"}
    if incremental == 0:
        if abs(cash_delta) > tolerance:
            raise ValueError("Fill cashflow correction requires reconciliation")
        return {
            "applied": False,
            "reason": "duplicate_or_stale_fill",
            "previous_filled_qty": str(previous),
            "existing_execution_qty": str(existing_execution_qty),
            "cumulative_filled_qty": str(cumulative),
        }
    # The broker price is cumulative VWAP, not the latest leg's price.
    price = cash_delta / incremental
    if not price.is_finite() or price <= 0:
        raise ValueError("Incremental fill cashflow requires reconciliation")

    fill_dt = (
        fill_time
        or getattr(order, "filled_at", None)
        or getattr(order, "submitted_at", None)
        or datetime.now(UTC)
    )
    execution = Execution(
        order_id=order.id,
        fill_qty=incremental,
        fill_price=price,
        ts=fill_dt,
        venue=venue,
    )
    session.add(execution)

    from backend.services.lot_tracker_service import LotTracker

    lot_tracker = LotTracker(session)
    user_id = _order_user_id(order)

    realized = []
    unmatched = Decimal("0")
    late_matches: list[dict[str, Any]] = []
    if action == "open_long":
        lot = await lot_tracker.create_lot(
            user_id=user_id,
            symbol=order.symbol,
            qty=incremental,
            cost_basis=price,
            order_id=order.id,
            open_date=fill_dt,
        )
        position_side = "long"
        late_matches = await _net_recorded_unmatched_closes(
            session, lot=lot, opening=order, user_id=user_id,
            close_side="sell", position_side=position_side,
        )
    elif action == "close_long":
        realized, unmatched = await _close_position_lots_fifo(
            session,
            user_id=user_id,
            symbol=order.symbol,
            qty_to_close=incremental,
            close_price=price,
            close_order_id=order.id,
            close_date=fill_dt,
            open_side="buy",
            position_side="long",
            close_submitted_at=getattr(order, "submitted_at", None),
        )
        position_side = "long"
    elif action == "open_short":
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
        await session.flush()
        position_side = "short"
        late_matches = await _net_recorded_unmatched_closes(
            session, lot=lot, opening=order, user_id=user_id,
            close_side="buy", position_side=position_side,
        )
    elif action == "close_short":
        realized, unmatched = await _close_position_lots_fifo(
            session,
            user_id=user_id,
            symbol=order.symbol,
            qty_to_close=incremental,
            close_price=price,
            close_order_id=order.id,
            close_date=fill_dt,
            open_side="sell",
            position_side="short",
            close_submitted_at=getattr(order, "submitted_at", None),
        )
        position_side = "short"
    else:
        return {"applied": False, "reason": f"unsupported_action:{action}"}

    await session.flush()
    outcome = {
        "applied": True,
        "side": side,
        "action": action,
        "position_side": position_side,
        "incremental_qty": str(incremental),
        "price": str(price),
        "execution_id": str(execution.id),
        "realized_count": len(realized),
        "realized_pnl": str(sum(t.realized_pnl for t in realized)),
        "previous_filled_qty": str(previous),
        "existing_execution_qty": str(existing_execution_qty),
        "cumulative_filled_qty": str(cumulative),
    }
    if unmatched > 0:
        outcome["lot_discrepancy"] = {
            "status": "unmatched",
            "reason": "no_open_lots" if unmatched == incremental else "insufficient_open_lots",
            "order_id": str(order.id),
            "symbol": str(order.symbol),
            "side": side,
            "owner": user_id,
            "position_side": position_side,
            "fill_qty": str(incremental),
            "matched_qty": str(incremental - unmatched),
            "unmatched_qty": str(unmatched),
            "fill_price": str(price),
            "execution_id": str(execution.id),
        }
    if late_matches:
        outcome["lot_late_matches"] = late_matches
    return outcome


async def apply_order_fill_snapshot(
    session: AsyncSession,
    order: Any,
    *,
    status: str,
    cumulative_filled_qty: Any,
    avg_fill_price: Any,
    broker_order_id: str | None = None,
    broker_order_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stage one serialized order summary and its accounting; caller commits.

    Identical summaries still repair missing execution/lot rows. Any failure
    must roll back the complete transaction and remain retryable. Unsupported
    same-quantity cash corrections are explicit reconciliation errors, never
    silent changes to lots that may already have realized outcomes.

    Audit 2026-10-05 C07-01: a close with no (or too few) open lots for its
    owner is not a failure. Broker truth (status, filled quantity, price and
    execution) is staged with any matched lots, and the remainder is recorded
    in ``attributes.lot_accounting`` for repair. A close that outran an
    earlier opening recovery can still settle is deferred instead
    (LotAccountingDeferred), and an opening lot ingested after its close was
    recorded is netted against that record. The result carries
    ``lot_discrepancy`` and ``lot_late_matches``; callers report them with
    log_lot_accounting_discrepancy() after their commit.
    """
    from backend.infra.schemas import Execution, Order

    result = await session.execute(
        select(Order)
        .where(Order.id == order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    current = result.scalar_one_or_none()
    if current is None:
        raise ValueError("Cannot reconcile a missing order")
    quantity = _decimal_or_none(cumulative_filled_qty)
    if (
        isinstance(cumulative_filled_qty, bool)
        or quantity is None
        or not quantity.is_finite()
        or quantity < 0
    ):
        raise ValueError("Invalid broker cumulative quantity")
    previous = _decimal_or_none(current.filled_qty) or Decimal("0")
    if not previous.is_finite():
        raise ValueError("Invalid persisted cumulative quantity")
    accounted = (
        await session.execute(
            select(func.coalesce(func.sum(Execution.fill_qty), 0)).where(
                Execution.order_id == current.id
            )
        )
    ).scalar_one()
    if quantity < max(previous, Decimal(str(accounted))):
        return {"applied": False, "reason": "stale_snapshot", "status": current.status}
    # Audit 2026-10-05 C04-01 (review NB1): a fill or broker order id for a row the
    # outbox finalized as never placed pages before it is staged (every ingress).
    from backend.infra.outbox_worker import finalized_order_attachment_alert

    late = finalized_order_attachment_alert(
        current, previous_filled_qty=previous, cumulative_filled_qty=quantity,
        broker_order_id=broker_order_id,
    )
    if late is not None:
        logger.critical(late["message"], **late["fields"])
    terminal = {"filled", "canceled", "cancelled", "expired", "rejected", "replaced"}
    if current.status in terminal and status not in terminal and quantity == previous:
        # A late acknowledgement cannot reopen a broker-terminal summary.
        status = current.status
    if quantity > 0 and status in ("rejected", "replaced"):
        raise ValueError("Unsupported terminal fill lineage requires reconciliation")
    accounting = await apply_incremental_fill_accounting(
        session,
        current,
        previous_filled_qty=previous,
        cumulative_filled_qty=quantity,
        avg_fill_price=avg_fill_price,
        status=status,
        broker_order_data=broker_order_data,
    )
    if quantity > 0 and accounting.get("reason") in {
        "non_fill_status",
        "missing_order_id",
        "missing_symbol_or_side",
    }:
        raise ValueError("Positive fill snapshot cannot be accounted safely")
    price = _decimal_or_none(avg_fill_price)
    if quantity > 0 and (price is None or not price.is_finite() or price <= 0):
        raise ValueError("Invalid broker cumulative price")
    discrepancy = accounting.get("lot_discrepancy")
    await OrdersRepo(session).attach_broker_result(
        current.id,
        broker_order_id=broker_order_id,
        status=status,
        filled_qty=quantity,
        avg_fill_price=price if quantity > 0 else None,
        attributes=(
            {"lot_accounting": _lot_accounting_record(current, discrepancy)}
            if discrepancy
            else None
        ),
    )
    if accounting["applied"] and accounting["side"] == "sell":
        # YY-2: ORDER_FILLED remains durable in the same accounting transaction.
        # Failure must be retryable; a committed execution cannot lose its audit.
        from backend.services.audit_service import AuditAction, AuditEntity, ComplianceAuditService

        await ComplianceAuditService(session).log(
            action=AuditAction.ORDER_FILLED,
            entity=AuditEntity.ORDER,
            entity_id=str(current.id),
            actor="system:alpaca_stream",
            payload={
                "symbol": current.symbol,
                "side": current.side,
                "qty": float(accounting["incremental_qty"]),
                "price": float(accounting["price"]),
                "status": status,
                "broker_order_id": broker_order_id or current.broker_order_id,
            },
        )
    return {**accounting, "status": status}


class AlpacaStreamClient:
    """
    WebSocket client for Alpaca trade updates stream.

    Connects to Alpaca's trade_updates WebSocket and processes order status changes
    in real-time, updating the local database with the latest order information.
    """

    def __init__(self):
        """Initialize the Alpaca stream client."""
        self.settings = get_settings()

        # Alpaca WebSocket configuration
        # §12.8 FIX: Accept both ALPACA_API_KEY_ID and ALPACA_API_KEY for compatibility
        self.api_key = os.getenv("ALPACA_API_KEY_ID") or os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
        self.api_secret = os.getenv("ALPACA_API_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
        self.is_paper = os.getenv("ALPACA_PAPER", "true").lower() in ("true", "1", "yes")

        # WebSocket URL
        if self.is_paper:
            self.ws_url = os.getenv("ALPACA_STREAM_URL", "wss://paper-api.alpaca.markets/stream")
        else:
            self.ws_url = os.getenv("ALPACA_STREAM_URL", "wss://api.alpaca.markets/stream")

        # Connection management
        self.websocket: websockets.WebSocketClientProtocol | None = None
        self.is_connected = False
        self.is_authenticated = False
        self.should_reconnect = True

        # Reconnection configuration
        self.reconnect_delay = 1.0
        self.max_reconnect_delay = 60.0
        self.reconnect_multiplier = 2.0
        self.max_reconnect_attempts = 10
        self.reconnect_attempts = 0

        # Update queue for backpressure handling.
        # UNBOUNDED for trade updates — we must NEVER drop fill/cancel/reject
        # messages as that causes state divergence and missed exits.
        # Non-critical messages (heartbeats, etc.) are not queued.
        self.update_queue: asyncio.Queue = asyncio.Queue()
        self.queue_processor_task = None
        self._queue_high_water_mark = 0
        self._queue_overflow_count = 0

        # REMEDIATION: Track order IDs that reached terminal state
        # (rejected/cancelled/expired) so the engine can clear pending entries early.
        self._terminal_order_ids: set[str] = set()

        # B1: Dead-letter queue for permanently failed trade updates
        self._dlq_path = Path(os.getenv("INTRA_DLQ_PATH", "/tmp/intra_trade_update_dlq.jsonl"))
        self._dlq_count: int = 0

        # B2: Track connection timestamps and reconnect count for gap-fill
        self._last_connected_at: float = 0.0
        self._gap_recovery_anchor: float = 0.0
        self._reconnect_count: int = 0

        # Heartbeat configuration
        self.heartbeat_interval = 30.0
        self.last_heartbeat = time.time()
        self.heartbeat_task = None

        logger.info("AlpacaStreamClient initialized",
                   is_paper=self.is_paper,
                   ws_url=self.ws_url)

    async def connect(self) -> bool:
        """
        Connect to Alpaca WebSocket stream.

        Returns:
            bool: True if connected successfully, False otherwise
        """
        if not self.api_key or not self.api_secret:
            logger.error("Alpaca API credentials not configured")
            return False

        try:
            logger.info("Connecting to Alpaca WebSocket stream", url=self.ws_url)

            # Connect to WebSocket
            self.websocket = await websockets.connect(
                self.ws_url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=10
            )

            self.is_connected = True
            self.reconnect_attempts = 0
            # Retain the previous connection boundary until gap recovery has
            # used it. A fresh connect must not erase a long outage's lookback.
            if not getattr(self, "_gap_recovery_anchor", 0):
                self._gap_recovery_anchor = self._last_connected_at
            self._last_connected_at = time.time()

            logger.info("Connected to Alpaca WebSocket stream")

            # Authenticate
            if await self._authenticate():
                # Subscribe to trade updates
                await self._subscribe_to_trade_updates()

                # Start background tasks
                await self._start_background_tasks()

                return True
            else:
                await self._disconnect()
                return False

        except Exception as e:
            logger.error("Failed to connect to Alpaca WebSocket",
                        error=str(e),
                        error_type=type(e).__name__)
            self.is_connected = False
            return False

    async def _authenticate(self) -> bool:
        """
        Authenticate with Alpaca WebSocket stream.

        Returns:
            bool: True if authenticated successfully, False otherwise
        """
        try:
            auth_message = {
                "action": "auth",
                "key": self.api_key,
                "secret": self.api_secret
            }

            await self.websocket.send(json.dumps(auth_message))

            # Wait for authentication response
            response = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            auth_data = json.loads(response)

            # Handle both old and new Alpaca API response formats
            # Old format: {"T": "success", "msg": "authenticated"}
            # New format: {"stream": "authorization", "data": {"action": "authenticate", "status": "authorized"}}
            is_authenticated = False

            if auth_data.get("T") == "success" and auth_data.get("msg") == "authenticated":
                # Old API format
                is_authenticated = True
            elif (auth_data.get("stream") == "authorization" and
                  auth_data.get("data", {}).get("status") == "authorized"):
                # New API format
                is_authenticated = True

            if is_authenticated:
                self.is_authenticated = True
                logger.info("Successfully authenticated with Alpaca stream",
                           response_format="new_api" if "stream" in auth_data else "old_api")
                return True
            else:
                logger.error("Authentication failed", response=auth_data)
                return False

        except Exception as e:
            logger.error("Authentication error",
                        error=str(e),
                        error_type=type(e).__name__)
            return False

    async def _subscribe_to_trade_updates(self) -> bool:
        """
        Subscribe to trade_updates stream.

        Returns:
            bool: True if subscribed successfully, False otherwise
        """
        try:
            subscribe_message = {
                "action": "listen",
                "data": {
                    "streams": ["trade_updates"]
                }
            }

            await self.websocket.send(json.dumps(subscribe_message))

            # Wait for subscription confirmation
            response = await asyncio.wait_for(self.websocket.recv(), timeout=10.0)
            sub_data = json.loads(response)

            # Handle both old and new Alpaca API response formats
            # Old format: {"T": "listening", "data": {"streams": ["trade_updates"]}}
            # New format: {"stream": "listening", "data": {"streams": ["trade_updates"]}}
            is_subscribed = False

            if sub_data.get("T") == "listening":
                # Old API format
                is_subscribed = True
            elif sub_data.get("stream") == "listening":
                # New API format
                is_subscribed = True

            if is_subscribed:
                logger.info("Successfully subscribed to trade_updates stream",
                           streams=sub_data.get("data", {}).get("streams", []),
                           response_format="new_api" if "stream" in sub_data else "old_api")
                return True
            else:
                logger.error("Subscription failed - unexpected response format", response=sub_data)
                return False

        except Exception as e:
            logger.error("Subscription error",
                        error=str(e),
                        error_type=type(e).__name__)
            return False

    async def _start_background_tasks(self):
        """Start background tasks for message processing and heartbeat."""
        # Start queue processor
        if not self.queue_processor_task:
            self.queue_processor_task = asyncio.create_task(self._process_update_queue())

        # Start heartbeat
        if not self.heartbeat_task:
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_background_tasks(self):
        """Stop background tasks."""
        if self.queue_processor_task:
            self.queue_processor_task.cancel()
            try:
                await self.queue_processor_task
            except asyncio.CancelledError:
                pass
            self.queue_processor_task = None

        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
            self.heartbeat_task = None

    async def listen(self):
        """
        Main listening loop for processing WebSocket messages.

        This method handles incoming trade_updates and queues them for processing.
        """
        if not self.is_connected or not self.is_authenticated:
            logger.error("Cannot listen - not connected or authenticated")
            return

        try:
            logger.info("Starting to listen for trade updates")

            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)

                except json.JSONDecodeError as e:
                    logger.warning("Invalid JSON received", message=message[:200], error=str(e))
                    continue

                except Exception as e:
                    logger.error("Error processing message",
                               message=message[:200],
                               error=str(e),
                               error_type=type(e).__name__)
                    continue

        except ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.is_connected = False
            self.is_authenticated = False

        except WebSocketException as e:
            logger.error("WebSocket error", error=str(e))
            self.is_connected = False
            self.is_authenticated = False

        except Exception as e:
            logger.error("Unexpected error in listen loop",
                        error=str(e),
                        error_type=type(e).__name__)
            self.is_connected = False
            self.is_authenticated = False

    async def _handle_message(self, data: dict[str, Any]):
        """
        Handle incoming WebSocket message.

        Args:
            data: Parsed message data
        """
        # Handle both old and new Alpaca API message formats
        # Old format: {"T": "trade_updates", ...}
        # New format: {"stream": "trade_updates", ...}
        msg_type = data.get("T") or data.get("stream")

        if msg_type == "trade_updates":
            # Queue trade update for processing.
            # The queue is unbounded — trade updates must NEVER be dropped
            # because missed fills/cancels/rejects cause state divergence.
            await self.update_queue.put(data)
            qsize = self.update_queue.qsize()
            self._queue_high_water_mark = max(self._queue_high_water_mark, qsize)
            if qsize > 500:
                self._queue_overflow_count += 1
                logger.warning(
                    "Trade update queue depth high: %d (hwm=%d, overflow_events=%d)",
                    qsize, self._queue_high_water_mark, self._queue_overflow_count,
                )
            logger.info("Queued trade update for processing",
                       order_id=data.get("data", {}).get("id"),
                       status=data.get("data", {}).get("status"))

        elif msg_type == "success":
            logger.debug("Success message received", msg=data.get("msg"))

        elif msg_type == "error":
            logger.error("Error message from stream", error=data)

        else:
            logger.debug("Unknown message type", msg_type=msg_type, data=data)

    async def _process_update_queue(self):
        """
        Process queued trade updates with retry on failure.

        This runs in a separate task to handle backpressure and ensure
        database updates don't block the WebSocket message loop.
        EXEC-001 FIX: Retries failed updates up to 3 times with backoff.
        """
        logger.info("Starting update queue processor")
        MAX_RETRIES = 3

        while True:
            try:
                # Get update from queue with timeout
                update = await asyncio.wait_for(
                    self.update_queue.get(),
                    timeout=0.5
                )

                # EXEC-001: Retry loop for transient failures
                last_error = None
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        await self._process_trade_update(update)
                        last_error = None
                        break
                    except Exception as e:
                        last_error = e
                        if attempt < MAX_RETRIES:
                            backoff = 0.5 * (2 ** (attempt - 1))  # 0.5s, 1s
                            logger.warning(
                                "Trade update processing failed (attempt %d/%d), retrying in %.1fs",
                                attempt, MAX_RETRIES, backoff,
                                error=str(e),
                                error_type=type(e).__name__,
                            )
                            await asyncio.sleep(backoff)

                if last_error is not None:
                    logger.error(
                        "Trade update PERMANENTLY FAILED after %d attempts — writing to DLQ",
                        MAX_RETRIES,
                        error=str(last_error),
                        error_type=type(last_error).__name__,
                        update_summary=str(update)[:200],
                    )
                    # B1: Write to dead-letter queue file
                    self._write_to_dlq(update, MAX_RETRIES, last_error)

            except TimeoutError:
                # No update in queue, continue
                continue

            except Exception as e:
                logger.error("Unexpected error in update queue processor",
                           error=str(e),
                           error_type=type(e).__name__)
                continue

    def _write_to_dlq(self, update: dict[str, Any], attempts: int, error: Exception) -> None:
        """B1: Append a permanently failed trade update to the dead-letter queue file."""
        try:
            dlq_record = {
                "timestamp": datetime.now(UTC).isoformat(),
                "attempt_count": attempts,
                "error": str(error),
                "error_type": type(error).__name__,
                "update": update,
            }
            with open(self._dlq_path, "a") as f:
                f.write(json.dumps(dlq_record, default=str) + "\n")
            self._dlq_count += 1
            logger.warning(
                "Trade update written to DLQ (total=%d): %s",
                self._dlq_count,
                self._dlq_path,
            )
        except Exception as dlq_err:
            logger.error("Failed to write to DLQ file: %s", dlq_err)

    async def _process_trade_update(self, update: dict[str, Any]):
        """
        Process a single trade update and update database.

        Args:
            update: Trade update data from Alpaca
        """
        try:
            # Extract order information
            # Alpaca v2 format: {"data": {"event": "fill", "order": {"id": ..., "status": ...}}}
            event_data = update.get("data", {})
            if not event_data:
                logger.warning("Empty order data in trade update", update=update)
                return

            # Order fields are nested under the "order" key
            order_data = event_data.get("order", event_data)

            broker_order_id = order_data.get("id")
            client_order_id = order_data.get("client_order_id")
            status = order_data.get("status")
            _raw_qty = order_data.get("filled_qty")
            filled_qty = Decimal("0") if _raw_qty in (None, "") else _raw_qty
            avg_fill_price = order_data.get("filled_avg_price") or order_data.get("avg_fill_price")

            if not broker_order_id or not status:
                logger.warning("Missing required fields in trade update",
                             broker_order_id=broker_order_id,
                             status=status,
                             update=update)
                return

            # Map Alpaca status to internal status
            internal_status = self._map_alpaca_status(status)

            logger.info("Processing trade update",
                       broker_order_id=broker_order_id,
                       client_order_id=client_order_id,
                       alpaca_status=status,
                       internal_status=internal_status,
                       filled_qty=filled_qty,
                       avg_fill_price=avg_fill_price)

            # Update database
            async with get_session_context() as session:
                orders_repo = OrdersRepo(session)

                # Find order by broker_order_id, with fallback to client_order_id.
                # The outbox worker may not have written broker_order_id to DB yet
                # (race condition), but client_idempotency_key is written *before*
                # the order is sent to Alpaca, so it's always available.
                order = await orders_repo.get_by_broker_order_id(broker_order_id)
                if not order and client_order_id:
                    order = await orders_repo.get_by_client_key(client_order_id)
                    if order:
                        logger.info(
                            "Order matched via client_order_id fallback, backfilled broker_order_id",
                            order_id=order.id,
                            broker_order_id=broker_order_id,
                            client_order_id=client_order_id,
                        )
                if not order:
                    logger.warning("Order not found for broker_order_id or client_order_id",
                                 broker_order_id=broker_order_id,
                                 client_order_id=client_order_id)
                    return

                accounting = await apply_order_fill_snapshot(
                    session, order, status=internal_status,
                    cumulative_filled_qty=filled_qty, avg_fill_price=avg_fill_price,
                    broker_order_id=broker_order_id, broker_order_data=order_data,
                )
                await session.commit()
                log_lot_accounting_discrepancy(accounting, ingress="trade_update_stream")
                internal_status = accounting["status"]
                if accounting.get("reason") == "stale_snapshot":
                    return
                logger.info("Order summary and fill accounting committed", order_id=str(order.id),
                            broker_order_id=broker_order_id, status=internal_status,
                            accounting_applied=accounting["applied"])

                if internal_status == "filled":
                    await self._sync_positions_after_terminal_fill(
                        order_id=str(order.id),
                        broker_order_id=broker_order_id,
                        symbol=str(order.symbol),
                    )

                # REMEDIATION: Track terminal order statuses for early pending-entry cleanup.
                # V4 H-1 / Wave-16d (2026-05-02): record BOTH the broker
                # `order_data["id"]` AND the internal DB UUID
                # `str(order.id)`. The previous code only stored the
                # broker id, but live_engine._pending_entry_order_ids[sym]
                # tracks the internal DB UUID — `is_order_terminal(uuid)`
                # therefore never matched, and the early-clear path was
                # dead. Symbols stayed locked for the full 30-tick
                # cooldown after every reject. With both ids in the
                # set, `is_order_terminal()` answers correctly regardless
                # of which id the caller has. The cap doubles to 2000-keep-1000
                # to preserve the previous effective horizon (~500 orders).
                if internal_status in ("rejected", "cancelled", "expired"):
                    broker_oid = order_data.get("id", "")
                    if broker_oid:
                        self._terminal_order_ids.add(broker_oid)
                    try:
                        # `order.id` is the internal DB UUID. Store as
                        # str so set lookups by either form match.
                        if order is not None and getattr(order, "id", None):
                            self._terminal_order_ids.add(str(order.id))
                    except Exception:
                        # Defensive: never let a tracking failure break
                        # the WS handler.
                        pass
                    # Cap set size to prevent unbounded growth.
                    if len(self._terminal_order_ids) > 2000:
                        self._terminal_order_ids = set(
                            list(self._terminal_order_ids)[-1000:]
                        )

                # ✅ FIX: Broadcast order update to frontend via WebSocket
                try:
                    import os

                    from backend.api.socketio_server import broadcast_order_update

                    # Get user_id - try order.user_id first, then DEFAULT_USER_ID from env
                    user_id = getattr(order, 'user_id', None) or os.getenv('DEFAULT_USER_ID', 'demo')

                    logger.info(f"🔔 Preparing to broadcast order update for user_id: '{user_id}'",
                               order_id=order.id,
                               status=internal_status)

                    # Prepare order data for broadcast
                    order_data = {
                        'order_id': str(order.id),
                        'broker_order_id': broker_order_id,
                        'symbol': order.symbol,
                        'side': order.side,
                        'qty': float(order.qty),
                        'filled_qty': filled_qty,
                        'avg_fill_price': avg_fill_price,
                        'status': internal_status,
                        'order_type': order.order_type,
                        'submitted_at': order.submitted_at.isoformat() if order.submitted_at else None,
                        'updated_at': datetime.now(UTC).isoformat()
                    }

                    # Broadcast to user's WebSocket clients
                    await broadcast_order_update(user_id, order_data)

                    logger.info(f"✅ Broadcasted order update to user {user_id} via WebSocket",
                               order_id=order.id,
                               status=internal_status)

                except Exception as broadcast_error:
                    # Don't fail order update if broadcast fails
                    logger.warning(f"⚠️ Failed to broadcast order update (order still updated in DB): {broadcast_error}")

        except Exception as e:
            logger.error("Failed to process trade update",
                        update=update,
                        error=str(e),
                        error_type=type(e).__name__)
            raise

    async def _sync_positions_after_terminal_fill(
        self,
        *,
        order_id: str,
        broker_order_id: str,
        symbol: str,
    ) -> None:
        """Refresh local positions after a broker-confirmed terminal fill."""
        try:
            from backend.services.portfolio_sync_service import get_portfolio_sync_service

            sync_service = get_portfolio_sync_service()
            result = await sync_service.sync_full_portfolio("system:alpaca_stream")
            if result.get("success"):
                positions = result.get("positions") or []
                logger.info(
                    "P7.6: local positions synced after filled trade update",
                    order_id=order_id,
                    broker_order_id=broker_order_id,
                    symbol=symbol,
                    position_count=len(positions),
                )
            else:
                logger.warning(
                    "P7.6: post-fill local position sync returned failure",
                    order_id=order_id,
                    broker_order_id=broker_order_id,
                    symbol=symbol,
                    error=result.get("error"),
                )
        except Exception as exc:
            logger.warning(
                "P7.6: post-fill local position sync failed for order %s "
                "(broker=%s, symbol=%s): %s",
                order_id,
                broker_order_id,
                symbol,
                exc,
            )

    def is_order_terminal(self, order_id: str) -> bool:
        """Check if an order reached terminal state (rejected/cancelled/expired).

        Accepts EITHER the broker `order_id` (Alpaca's id) or the internal
        DB UUID (`Order.id`). V4 H-1 / Wave-16d (2026-05-02): the
        `_on_trade_update` recorder pushes both forms into
        `_terminal_order_ids` so this lookup answers correctly regardless
        of which form the caller has — `live_engine` carries the internal
        UUID; broker / API consumers carry the broker id. Parameter
        renamed from `broker_order_id` to `order_id` to reflect the
        unified semantics.
        """
        return order_id in self._terminal_order_ids

    async def _gap_fill_after_reconnect(self) -> None:
        """EXEC-002: Poll recent orders for missed fills after WebSocket reconnect.

        B2: Uses actual gap duration (time since last connection) instead of
        a fixed 5-minute window. Minimum 5 minutes, capped at 1 hour.
        """
        try:
            from datetime import timedelta
            from backend.services.order_recovery_service import recover_persisted_orders

            await recover_persisted_orders(get_session_context)

            # B2: Compute actual gap duration
            anchor = getattr(self, "_gap_recovery_anchor", 0) or self._last_connected_at
            if anchor > 0:
                gap_seconds = time.time() - anchor
            else:
                gap_seconds = 300  # Default 5 minutes if no prior connection

            # Minimum 5 min, extend to cover gap + 1 min buffer, cap at 1 hour
            lookback_seconds = min(max(gap_seconds + 60, 300), 3600)

            logger.info(
                "EXEC-002 gap-fill: gap_duration=%.0fs, lookback_window=%.0fs",
                gap_seconds,
                lookback_seconds,
            )

            cutoff = datetime.now(UTC) - timedelta(seconds=lookback_seconds)
            async with get_session_context() as session:
                orders_repo = OrdersRepo(session)
                # Fetch orders that may have changed during the gap
                recent_orders = await orders_repo.get_orders_since(cutoff)
                if not recent_orders:
                    logger.info("EXEC-002 gap-fill: no recent orders to reconcile")
                    return

                reconciled = 0
                # Rollback expires ORM instances; keep immutable identities so
                # one failed order cannot prevent recovery of the next order.
                identities = [(item.id, item.broker_order_id) for item in recent_orders]
                for order_id, broker_identity in identities:
                    if not broker_identity:
                        continue
                    try:
                        from backend.infra.schemas import Order

                        order = await session.get(Order, order_id)
                        if order is None:
                            continue
                        # Query broker for current status
                        import httpx

                        base_url = (
                            "https://paper-api.alpaca.markets"
                            if self.is_paper
                            else "https://api.alpaca.markets"
                        )
                        async with httpx.AsyncClient() as client:
                            resp = await client.get(
                                f"{base_url}/v2/orders/{broker_identity}",
                                headers={
                                    "APCA-API-KEY-ID": self.api_key,
                                    "APCA-API-SECRET-KEY": self.api_secret,
                                },
                                timeout=10.0,
                            )
                            if resp.status_code == 200:
                                broker_data = resp.json()
                                broker_status = self._map_alpaca_status(broker_data.get("status", ""))
                                current_db_status = order.status
                                accounting = await apply_order_fill_snapshot(
                                    session,
                                    order,
                                    status=broker_status,
                                    cumulative_filled_qty=broker_data.get("filled_qty") or "0",
                                    avg_fill_price=broker_data.get("filled_avg_price"),
                                    broker_order_data=broker_data,
                                )
                                await session.commit()
                                log_lot_accounting_discrepancy(
                                    accounting, ingress="reconnect_gap_fill"
                                )
                                broker_status = accounting["status"]
                                if accounting.get("reason") != "stale_snapshot":
                                    reconciled += 1
                                    logger.info(
                                        "Gap-fill snapshot reconciled atomically",
                                        order_id=str(order.id),
                                        previous_status=current_db_status,
                                        status=broker_status,
                                        accounting_applied=accounting["applied"],
                                    )

                                    # V5 S-WS-GAP-1 / Wave-17c (2026-05-03):
                                    # the steady-state path
                                    # (`_on_trade_update`) records terminal
                                    # ids into `_terminal_order_ids` so
                                    # live_engine's early-clear path can
                                    # un-stick rejected symbols. Across a
                                    # WS gap, that path doesn't fire — the
                                    # terminal status was discovered by
                                    # gap-fill REST polling instead. We
                                    # must re-populate `_terminal_order_ids`
                                    # here too, otherwise wave-16d's
                                    # H-1 unification holds in-process but
                                    # regresses across every WS reconnect:
                                    # the symbol stays locked for the full
                                    # 30-tick TTL after a gap-window reject.
                                    if broker_status in ("rejected", "cancelled", "expired"):
                                        broker_oid = order.broker_order_id
                                        if broker_oid:
                                            self._terminal_order_ids.add(broker_oid)
                                        try:
                                            if order.id is not None:
                                                self._terminal_order_ids.add(str(order.id))
                                        except Exception:
                                            pass
                                        if len(self._terminal_order_ids) > 2000:
                                            self._terminal_order_ids = set(
                                                list(self._terminal_order_ids)[-1000:]
                                            )
                    except Exception as e:
                        await session.rollback()
                        logger.warning(
                            "EXEC-002 gap-fill: failed to reconcile order %s: %s", broker_identity, e
                        )
                        continue

                logger.info(
                    "EXEC-002 gap-fill complete: %d orders reconciled out of %d checked",
                    reconciled,
                    len(recent_orders),
                )

        except Exception as e:
            logger.error("EXEC-002 gap-fill failed (non-fatal): %s", e)
        finally:
            self._gap_recovery_anchor = 0.0

    def _map_alpaca_status(self, alpaca_status: str) -> str:
        """
        Map Alpaca order status to internal status.

        Args:
            alpaca_status: Alpaca order status

        Returns:
            Internal order status
        """
        status_mapping = {
            "new": "submitted",
            "accepted": "accepted",
            "partially_filled": "partially_filled",
            "filled": "filled",
            "canceled": "cancelled",
            "expired": "expired",
            "rejected": "rejected",
            "pending_new": "pending",
            "pending_cancel": "pending_cancel",
            "pending_replace": "pending_replace"
        }

        return status_mapping.get(alpaca_status.lower(), alpaca_status)

    async def _heartbeat_loop(self):
        """Send periodic heartbeat to keep connection alive."""
        while self.is_connected:
            try:
                current_time = time.time()

                # Check if we've received any messages recently
                if current_time - self.last_heartbeat > self.heartbeat_interval * 2:
                    logger.warning("No heartbeat received, connection may be stale")

                # Send ping if connection is active
                if self.websocket and self.is_connected:
                    try:
                        await self.websocket.ping()
                        self.last_heartbeat = current_time
                    except Exception as ping_error:
                        logger.warning("Ping failed, connection may be closed", error=str(ping_error))
                        break

                await asyncio.sleep(self.heartbeat_interval)

            except Exception as e:
                logger.error("Heartbeat error", error=str(e))
                break

    async def _disconnect(self):
        """Disconnect from WebSocket stream."""
        logger.info("Disconnecting from Alpaca stream")

        self.is_connected = False
        self.is_authenticated = False

        # Stop background tasks
        await self._stop_background_tasks()

        # Close WebSocket connection
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.warning("Error closing websocket", error=str(e))
            finally:
                self.websocket = None

    async def start_with_reconnect(self):
        """
        Start the stream client with automatic reconnection.

        This method will attempt to maintain a connection to the Alpaca stream,
        automatically reconnecting if the connection is lost.
        """
        logger.info("Starting Alpaca stream with reconnect capability")

        while self.should_reconnect:
            try:
                # Attempt connection
                if await self.connect():
                    # Reset reconnection delay on successful connect
                    self.reconnect_delay = 1.0
                    self.reconnect_attempts = 0
                    # P&L-033: Reset slow-retry counter on successful connection
                    self._slow_retry_cycles = 0

                    # EXEC-002: Gap-fill after reconnect — check for missed fills
                    await self._gap_fill_after_reconnect()

                    # Listen for messages
                    await self.listen()

                # Connection lost, attempt reconnection
                if self.should_reconnect:
                    self.reconnect_attempts += 1

                    # B2: Track total reconnect count across the session
                    self._reconnect_count += 1
                    if self._reconnect_count > 10:
                        logger.critical(
                            "Stream instability: %d reconnects this session — "
                            "order update reliability degraded",
                            self._reconnect_count,
                        )

                    if self.reconnect_attempts >= self.max_reconnect_attempts:
                        logger.error("Max reconnection attempts reached, entering cooldown before retry cycle")
                        # H-09 FIX: Emit critical alert when max reconnects reached
                        await self._emit_max_reconnect_alert()
                        # P&L-033: Slow-retry mode — after exhausting fast retries,
                        # switch to progressively longer cooldowns (5m → 10m → 20m,
                        # capped at 30m).  This avoids hammering a flaky endpoint
                        # while still eventually recovering.
                        slow_cycles = getattr(self, "_slow_retry_cycles", 0)
                        slow_delay = min(1800, 300 * (2 ** slow_cycles))  # 5m, 10m, 20m, 30m
                        self._slow_retry_cycles = slow_cycles + 1
                        logger.info(
                            "Slow-retry cooldown activated",
                            extra={"delay_s": slow_delay, "cycle": self._slow_retry_cycles},
                        )
                        await asyncio.sleep(slow_delay)
                        self.reconnect_attempts = 0
                        self.reconnect_delay = 1.0
                        logger.info("Cooldown complete, restarting reconnection cycle")
                        continue

                    logger.info("Attempting reconnection",
                              attempt=self.reconnect_attempts,
                              delay=self.reconnect_delay)

                    await asyncio.sleep(self.reconnect_delay)

                    # Exponential backoff
                    self.reconnect_delay = min(
                        self.reconnect_delay * self.reconnect_multiplier,
                        self.max_reconnect_delay
                    )

            except Exception as e:
                logger.error("Unexpected error in stream client",
                           error=str(e),
                           error_type=type(e).__name__)

                if self.should_reconnect:
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    break

        logger.info("Alpaca stream client stopped")

    async def _emit_max_reconnect_alert(self) -> None:
        """
        H-09 FIX: Emit critical alert when max WebSocket reconnection attempts reached.
        
        This indicates potential order update loss and requires immediate attention.
        """
        try:
            # V4 P-P0-4 (2026-05-02): the previous code imported
            # `emit_alert` from backend.monitoring.slo_monitor and
            # `increment_counter` from backend.observability.metrics —
            # neither symbol exists. Both `except ImportError: pass`
            # branches always fired, dropping the alert and skipping
            # the metric on every WS max-reconnect event. Use the
            # canonical send_alert API; metric becomes a Prometheus
            # Counter declared on the global REGISTRY (visible at
            # /metrics post wave-12e).
            try:
                from backend.infra.alerting import (
                    AlertCategory, AlertSeverity, send_alert,
                )
                await send_alert(
                    AlertCategory.CONNECTIVITY,
                    AlertSeverity.CRITICAL,
                    "Alpaca WebSocket Max Reconnects Reached",
                    (
                        f"WebSocket connection to Alpaca failed after {self.max_reconnect_attempts} "
                        "reconnection attempts. Order updates may be lost. "
                        "Manual intervention required."
                    ),
                    details={
                        "attempts": self.reconnect_attempts,
                        "max_attempts": self.max_reconnect_attempts,
                        "last_reconnect_delay": self.reconnect_delay,
                        "is_paper": self.is_paper,
                    },
                )
            except Exception as _alert_err:
                logger.warning(
                    "WS max-reconnect alert dispatch failed: %s",
                    _alert_err,
                )

            try:
                from prometheus_client import Counter
                global _WS_MAX_RECONNECT_COUNTER
                try:
                    _WS_MAX_RECONNECT_COUNTER  # type: ignore[name-defined]
                except NameError:
                    _WS_MAX_RECONNECT_COUNTER = Counter(
                        "websocket_max_reconnects_total",
                        "Total times the Alpaca WS gave up after max reconnects",
                        ["stream_type", "is_paper"],
                    )
                _WS_MAX_RECONNECT_COUNTER.labels(
                    stream_type="alpaca_trades",
                    is_paper=str(self.is_paper),
                ).inc()
            except Exception:
                pass
            
            # Log at critical level for log-based alerting
            logger.critical(
                "ALERT: Alpaca WebSocket max reconnects reached - order updates may be lost",
                extra={
                    "alert_type": "WebSocketMaxReconnects",
                    "severity": "critical",
                    "attempts": self.reconnect_attempts,
                    "max_attempts": self.max_reconnect_attempts,
                    "is_paper": self.is_paper,
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to emit max reconnect alert: {e}")

    async def stop(self):
        """Stop the stream client."""
        logger.info("Stopping Alpaca stream client")
        self.should_reconnect = False
        await self._disconnect()


# Global stream client instance
_stream_client: AlpacaStreamClient | None = None


def get_stream_client() -> AlpacaStreamClient:
    """
    Get the global stream client instance.

    Returns:
        AlpacaStreamClient: The stream client instance
    """
    global _stream_client
    if _stream_client is None:
        _stream_client = AlpacaStreamClient()
    return _stream_client


async def start_stream_client():
    """Start the global stream client."""
    client = get_stream_client()
    await client.start_with_reconnect()


async def stop_stream_client():
    """Stop the global stream client."""
    global _stream_client
    if _stream_client:
        await _stream_client.stop()
        _stream_client = None
