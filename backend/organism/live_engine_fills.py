"""DB fill-lookup helpers for the live engine.

Strategy outcomes require an identified entry and conserved quantities across
every attributed order. Legacy entry/final-exit lookups remain available for
excluded orphan bookkeeping. A lifetime closed outside the engine's exit orders
is classified for reconciliation-artifact bookkeeping (``ExternalClose``).
Database access is read-only with one exception: once such a close is
recordable, its lot repair (``alpaca_stream.repair_external_close_lots``) is
committed before the lookup returns, so before the artifact can release the
symbol's entry gate.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)

# These are accounting-eligible terminal states, not the broker's complete
# lifecycle vocabulary. `replaced` is terminal for an old order but says nothing
# about its successor. Current ingestion does not retain authoritative lineage,
# and its Execution rows derive from cumulative Order summaries. Neither flat
# positions nor conserved summary quantities can prove replacement cash flows.
ACCOUNTABLE_TERMINAL_STATUSES = frozenset({"filled", "canceled", "cancelled", "expired", "rejected"})
REPLACEMENT_PENDING_REASON = "replacement_lineage_unverified"
AMBIGUOUS_ORDER_REASON_PREFIX = "ambiguous_order:"

# Audit 2026-10-05 C08-01: an unresolved or replaced order can only change an
# identified lifetime while it can still execute at the broker. A
# session-bounded (DAY/IOC/FOK/OPG/CLS) order stops working at the
# extended-hours close of its eligible NYSE session. An order the broker never
# acknowledged (no broker order id on the row) is bounded by the session of its
# submission, so a dead letter touched later (for example by a remediation
# status) cannot hold every later close of the symbol. Known limit: the row
# alone cannot show an ambiguous submission (EXE-04) that reached the broker
# later without a broker id being persisted; such an order may still work
# after that session. The backstop is the lifetime's own legs: exits are sized
# from the broker position and _closed_position_fills requires them to be
# terminal and flat-to-flat, so a stray fill from it keeps the close pending.
# A replaced DAY predecessor is bounded the same way, on the assumption that
# its successor kept a session-bounded TIF (replacement lineage and the
# successor's TIF are not ingested). Acknowledged GTC/other/unknown-TIF orders
# stay conservative: they block until a terminal status is ingested.
SESSION_BOUNDED_TIFS = frozenset({"day", "ioc", "fok", "opg", "cls"})
# Broker cancellation latency and DB/broker clock skew after the session end.
SESSION_END_SLACK = timedelta(hours=1)
# POST latency and app-clock lag at the regular-close cut-off: an order entered
# or acknowledged this close to the close may already be queued for the next
# session, so the session is picked from the basis time plus this slack.
SESSION_CUTOFF_SLACK = timedelta(minutes=5)
_SESSION_SEARCH_DAYS = 14

# Audit 2026-10-05 C06-01: an identified strategy position closed by anything
# other than an organism exit order. The platform's own close routes (POST
# /positions/{symbol}/close and POST /orders/{id}/close-position) book their
# leg with ``close_position: true`` and no organism source; the Alpaca dashboard
# or app and broker liquidations book no row at all. Such a close is recorded as
# a reconciliation artifact, never a strategy outcome (no learner, Kelly,
# calibration, symbol counts, bans, evolution or edge-monitor input): exactly
# when close-route legs complete the lifetime, and approximately (the quantity
# no DB leg closed priced at the best available mark, labelled so) once it has
# stayed unresolved for EXTERNAL_CLOSE_APPROXIMATE_AFTER.
EXTERNAL_CLOSE_EXIT_REASON = "external_close"
EXTERNAL_CLOSE_EXACT_SOURCE = "external_close_db_fills"
EXTERNAL_CLOSE_APPROXIMATE_SOURCE_PREFIX = "external_close_approximate_"
EXTERNAL_CLOSE_UNBOOKED_REASON = "external_close_unbooked"
# Well beyond fill-ingestion latency (stream, reconnect gap-fill, persisted
# order recovery) and shorter than the engine's 30-minute pending-close page.
EXTERNAL_CLOSE_APPROXIMATE_AFTER = timedelta(minutes=15)
# Review: the lot repair must commit before the artifact releases the gate. A
# failed repair keeps the close pending under this hold reason; every pass
# retries it.
EXTERNAL_CLOSE_LOT_REPAIR_FAILED_REASON = "external_close_lot_repair_failed"


def _replacement_pending(meta: dict[str, Any]) -> None:
    """Expose a diagnostic through existing pending status without finalizing it."""
    pending = meta.get("pending_close")
    if isinstance(pending, dict):
        pending["accounting_hold_reason"] = REPLACEMENT_PENDING_REASON


def _as_utc(value: datetime) -> datetime:
    # PostgreSQL returns aware values; SQLite fixtures can return naive UTC.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _eligible_session_end(moment: datetime) -> datetime | None:
    """Last instant an order entered (or last touched) at ``moment`` can work.

    Orders entered after the regular close, overnight, on weekends or on
    holidays queue for the next session, so the eligible session is the first
    NYSE trading day whose regular close (early closes included) is after
    ``moment``. Extended-hours DAY orders can work until 20:00 ET that day.
    """
    from backend.utils.market_hours import ET, EXTENDED_CLOSE, is_trading_day, market_close_time

    local = _as_utc(moment).astimezone(ET)
    day = local.date()
    for _ in range(_SESSION_SEARCH_DAYS):
        if is_trading_day(day) and local < datetime.combine(day, market_close_time(day), tzinfo=ET):
            return datetime.combine(day, EXTENDED_CLOSE, tzinfo=ET).astimezone(UTC)
        day += timedelta(days=1)
    return None


def _order_may_affect_lifetime(row: Any, entry_time: datetime) -> bool:
    """Fail closed unless the order stopped working before the entry.

    The eligible session is picked from a basis time plus SESSION_CUTOFF_SLACK
    and ends at its 20:00 ET close plus SESSION_END_SLACK. An acknowledged
    order's basis is the later of submitted_at and updated_at: a delayed
    delivery is acknowledged (and touched) later, never earlier. A
    never-acknowledged order's basis is its submission: a later touch (e.g.
    remediation marking a dead letter 'failed') does not revive it. That rests
    on the row's only recorded delivery attempt; an ambiguous submission that
    reached the broker later without a persisted broker id is not visible here
    (see the module note above for the backstop).
    """
    try:
        submitted = _as_utc(row["submitted_at"])
        if str(row["broker_order_id"] or "").strip():
            if str(row["tif"] or "").strip().lower() not in SESSION_BOUNDED_TIFS:
                return True
            basis = max(submitted, _as_utc(row["updated_at"] or submitted))
        else:
            basis = submitted
        session_end = _eligible_session_end(basis + SESSION_CUTOFF_SLACK)
        return session_end is None or session_end + SESSION_END_SLACK >= _as_utc(entry_time)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return True


def _pending_close_time(meta: dict[str, Any]) -> datetime | None:
    """Observed close time the caller accounts this lifetime to, if known."""
    pending = meta.get("pending_close")
    try:
        return _as_utc(datetime.fromisoformat(str(pending["observed_at"])))
    except (TypeError, KeyError, ValueError, AttributeError, OverflowError):
        return None


def _hold_close(meta: dict[str, Any], symbol: str, reason: str) -> None:
    """Name the blocking evidence in pending status; warn once per reason."""
    pending = meta.get("pending_close")
    if isinstance(pending, dict):
        if pending.get("accounting_hold_reason") == reason:
            return
        pending["accounting_hold_reason"] = reason
    logger.warning("Exact close accounting for %s held: %s", symbol, reason)


@dataclass(frozen=True)
class ClosedPositionFills:
    """Quantity-conserved, attributed order-fill cash flows for one position."""

    shares: int
    entry_price: float
    exit_price: float
    pnl: float
    had_partial_exits: bool
    price_source: str = "db_position_fills"


def _is_close_route_leg(attributes: Any) -> bool:
    """A leg booked by the platform's own close routes, not by the engine."""
    return (isinstance(attributes, dict) and attributes.get("close_position") is True
            and attributes.get("source") != "organism")


def _finite_decimal(value: Any) -> Decimal:
    value = Decimal(str(value))
    if not value.is_finite():
        raise ValueError("nonfinite fill value")
    return value


@dataclass(frozen=True)
class _LifetimeLegs:
    """Validated fill legs of one identified lifetime up to its observed close."""

    entries: Decimal
    entry_cash: Decimal
    exits: Decimal
    exit_cash: Decimal
    exit_orders: int
    close_route_orders: int
    finished: bool
    # Close-route rows in the window, filled or not (a refused or canceled
    # operator Close that raced the engine's own exit has no fill).
    close_route_rows: int = 0


def _lifetime_legs(
    rows: list[dict[str, Any]], *, entry_order_id: uuid.UUID, symbol: str,
    direction: float, closed_at: datetime, close_route_exits: bool = False,
) -> _LifetimeLegs | None:
    """Every order from the identified entry to ``closed_at``, or None.

    Shared by exact accounting and the external-close classification. Every
    order in the window must be attributable, terminal and quantity-consistent;
    the first positive fill must be the identified entry, exits never exceed
    entries, and nothing may fill after the position went flat. Attributable
    means organism-sourced; with ``close_route_exits`` also an exit-side leg
    booked by a platform close route (``_is_close_route_leg``).
    """
    try:
        anchors = [row for row in rows if str(row["id"]) == str(entry_order_id)]
        if len(anchors) != 1 or direction not in (-1, 1):
            return None
        # PostgreSQL returns aware values; SQLite test fixtures can return naive
        # values for the same timezone=True schema, whose contract is UTC.
        anchor_time = _as_utc(anchors[0]["submitted_at"])
        end = _as_utc(closed_at)
        if anchor_time > end:
            return None
        selected = [row for row in rows if anchor_time <= _as_utc(row["submitted_at"]) <= end]
        selected.sort(key=lambda row: (_as_utc(row["submitted_at"]), str(row["id"])))
        entry_side = "buy" if direction > 0 else "sell"
        exit_side = "sell" if direction > 0 else "buy"
        seen_ids, seen_broker_ids = set(), set()
        entries = exits = entry_cash = exit_cash = Decimal(0)
        exit_orders = close_route_orders = close_route_rows = 0
        finished = False
        for row in selected:
            attributes = row.get("attributes") or {}
            close_route = close_route_exits and _is_close_route_leg(attributes)
            if row["symbol"] != symbol or not (attributes.get("source") == "organism" or close_route):
                return None
            if close_route and row["side"] != exit_side:
                return None
            identity = str(row["id"])
            if identity in seen_ids:
                return None
            seen_ids.add(identity)
            status = str(row["status"]).lower()
            if status not in ACCOUNTABLE_TERMINAL_STATUSES:
                return None
            qty, requested = _finite_decimal(row["filled_qty"]), _finite_decimal(row["qty"])
            if qty < 0 or requested <= 0 or qty > requested:
                return None
            if status == "filled" and qty != requested:
                return None
            close_route_rows += int(close_route)
            if qty == 0:
                if status == "filled":
                    return None
                continue
            broker_id = str(row.get("broker_order_id") or "")
            if not broker_id or broker_id in seen_broker_ids or status == "rejected":
                return None
            seen_broker_ids.add(broker_id)
            price = _finite_decimal(row["avg_fill_price"])
            if price <= 0 or finished:
                return None
            # The first positive fill must be the identified entry, not an old
            # same-symbol position or a conflicting simultaneous order.
            if entries == 0 and (identity != str(entry_order_id) or row["side"] != entry_side):
                return None
            if row["side"] == entry_side:
                entries += qty
                entry_cash += qty * price
            elif row["side"] == exit_side:
                exits += qty
                exit_cash += qty * price
                exit_orders += 1
                close_route_orders += int(close_route)
            else:
                return None
            if exits > entries:
                return None
            finished = entries > 0 and entries == exits
        return _LifetimeLegs(entries, entry_cash, exits, exit_cash,
                             exit_orders, close_route_orders, finished, close_route_rows)
    except (KeyError, ValueError, TypeError, AttributeError, InvalidOperation):
        return None


def _closed_position_fills(
    rows: list[dict[str, Any]], *, entry_order_id: uuid.UUID, symbol: str,
    direction: float, closed_at: datetime,
) -> ClosedPositionFills | None:
    """Refuse exact accounting when attribution or quantity evidence is incomplete.

    The entry-order ID anchors the lifetime. Subsequent orders must form exactly
    one flat-to-flat position, with no remaining active order that could fill
    later. Terminal canceled/expired orders contribute any confirmed fills.
    Reason labels are deliberately irrelevant to scale-out accounting. Replaced
    legs remain unsupported until complete authoritative lineage is ingested;
    even reciprocal attributes alone do not prove nonduplicated cash flows.
    Only organism-sourced legs count (``_lifetime_legs``).
    """
    legs = _lifetime_legs(rows, entry_order_id=entry_order_id, symbol=symbol,
                          direction=direction, closed_at=closed_at)
    try:
        if legs is None or not legs.finished or legs.entries != legs.entries.to_integral_value():
            # TradeRecord.shares is integer-valued; do not silently round an
            # unsupported fractional position and call it exact accounting.
            return None
        entries, entry_cash, exit_cash = legs.entries, legs.entry_cash, legs.exit_cash
        pnl = exit_cash - entry_cash if direction > 0 else entry_cash - exit_cash
        return ClosedPositionFills(
            shares=int(entries), entry_price=float(entry_cash / entries),
            exit_price=float(exit_cash / legs.exits), pnl=float(pnl),
            had_partial_exits=legs.exit_orders > 1,
        )
    except (KeyError, ValueError, TypeError, AttributeError, InvalidOperation):
        return None


@dataclass(frozen=True)
class ExternalClose:
    """An identified lifetime closed outside the engine's exit orders (C06-01).

    Entry and booked exit amounts are the DB legs' own (exact).
    ``unbooked_qty`` is the quantity no DB leg closed (Alpaca dashboard or
    app, broker liquidation); zero when platform close routes booked it all.
    """

    shares: int
    direction: int
    entry_cash: Decimal
    booked_exit_qty: Decimal
    booked_exit_cash: Decimal
    booked_exit_orders: int
    close_route_orders: int

    @property
    def unbooked_qty(self) -> Decimal:
        return Decimal(self.shares) - self.booked_exit_qty

    def waiting(self, closed_at: datetime, now: datetime) -> bool:
        """An unbooked quantity is recorded only EXTERNAL_CLOSE_APPROXIMATE_AFTER
        after the observed close (the lifetime's legs get time to land)."""
        return (self.unbooked_qty > 0
                and _as_utc(now) - _as_utc(closed_at) < EXTERNAL_CLOSE_APPROXIMATE_AFTER)

    def fills(self, mark: Any = None, mark_source: str = "") -> ClosedPositionFills | None:
        """Exact cash flows, or the unbooked quantity at ``mark`` (labelled)."""
        try:
            shares = Decimal(self.shares)
            exit_cash, legs = self.booked_exit_cash, self.booked_exit_orders
            source = EXTERNAL_CLOSE_EXACT_SOURCE
            unbooked = self.unbooked_qty
            if unbooked:
                price = _finite_decimal(mark)
                if unbooked < 0 or price <= 0 or not mark_source:
                    return None
                exit_cash += unbooked * price
                legs += 1
                source = EXTERNAL_CLOSE_APPROXIMATE_SOURCE_PREFIX + mark_source
            pnl = exit_cash - self.entry_cash if self.direction > 0 else self.entry_cash - exit_cash
            return ClosedPositionFills(
                shares=self.shares, entry_price=float(self.entry_cash / shares),
                exit_price=float(exit_cash / shares), pnl=float(pnl),
                had_partial_exits=legs > 1, price_source=source,
            )
        except (TypeError, ValueError, ArithmeticError):
            return None


def _external_close(
    rows: list[dict[str, Any]], *, entry_order_id: uuid.UUID, symbol: str,
    direction: float, closed_at: datetime,
) -> ExternalClose | None:
    """Classify a lifetime that exact accounting refused (audit 2026-10-05 C06-01).

    ``rows`` are the symbol's orders from the entry on, with no upper bound.
    Exact: the lifetime is flat-to-flat by ``closed_at`` and a platform
    close-route row is among its legs. Either such legs booked (part of) the
    close, or an operator Close raced the engine's own exit and was refused
    (the outbox exit guard) or canceled without a fill; exact strategy
    accounting refuses any non-organism row, so the DB cash flows are recorded
    as an artifact instead of leaving the close pending for good. Unbooked:
    every leg up to ``closed_at`` is attributable and terminal and the lifetime
    is still open in the DB, although the broker is flat (the caller asks only
    for symbols it saw flat). Any order after ``closed_at`` refuses the
    unbooked case: it could hold the missing legs (a late exit of this
    lifetime, an operator trade) and cannot be attributed here. None refuses:
    the close stays pending.
    """
    legs = _lifetime_legs(rows, entry_order_id=entry_order_id, symbol=symbol,
                          direction=direction, closed_at=closed_at, close_route_exits=True)
    try:
        if legs is None or legs.entries <= 0 or legs.entries != legs.entries.to_integral_value():
            return None
        if legs.finished:
            if not (legs.close_route_orders or legs.close_route_rows):
                return None  # Every leg is the engine's own: exact accounting owns it.
        elif any(_as_utc(row["submitted_at"]) > _as_utc(closed_at) for row in rows):
            return None
        return ExternalClose(
            shares=int(legs.entries), direction=int(direction), entry_cash=legs.entry_cash,
            booked_exit_qty=legs.exits, booked_exit_cash=legs.exit_cash,
            booked_exit_orders=legs.exit_orders, close_route_orders=legs.close_route_orders,
        )
    except (KeyError, ValueError, TypeError, AttributeError, InvalidOperation):
        return None


class _FillLookupMixin:
    """Authoritative broker fill lookups from the orders table.

    Requires the host class to provide ``self._sessionmaker`` (an async
    SQLAlchemy sessionmaker or ``None``).
    """

    async def _lifetime_held(
        self, session: Any, symbol: str, meta: dict[str, Any], *,
        entry_time: datetime, closed_at: datetime,
    ) -> bool:
        """True while an order outside the lifetime's own legs could change it.

        Shared by the exact and the external-close lookups. Names the blocking
        evidence in ``pending_close.accounting_hold_reason`` (one WARNING per
        new reason) and clears a stale reason once it no longer holds.
        """
        from sqlalchemy import func, select
        from backend.infra.schemas import Order

        pending = meta.get("pending_close")
        # A replaced predecessor can hide a missing/active successor,
        # and an older active order can still execute during this
        # lifetime. Either holds the close only while it can still work
        # at the broker after the entry (C08-01: a dead-lettered April
        # row must not make every later close of the symbol pending).
        # A replaced DAY row is bounded by its own session on the
        # assumption that its successor kept a session-bounded TIF.
        unresolved_stmt = select(
            Order.id, Order.status, Order.tif, Order.submitted_at,
            Order.updated_at, Order.broker_order_id,
        ).where(
            Order.symbol == symbol, Order.submitted_at <= closed_at,
            func.lower(Order.status).not_in(ACCOUNTABLE_TERMINAL_STATUSES),
        ).order_by(Order.submitted_at.desc(), Order.id)
        live = [
            row for row in (await session.execute(unresolved_stmt)).mappings().all()
            if _order_may_affect_lifetime(row, entry_time)
        ]
        replaced = next((row for row in live if str(row["status"]).lower() == "replaced"), None)
        if replaced is not None:
            if not (isinstance(pending, dict)
                    and pending.get("accounting_hold_reason") == REPLACEMENT_PENDING_REASON):
                logger.warning("Exact close accounting for %s held: %s (order %s)",
                               symbol, REPLACEMENT_PENDING_REASON, replaced["id"])
            _replacement_pending(meta)
            return True
        if isinstance(pending, dict) and pending.get("accounting_hold_reason") == REPLACEMENT_PENDING_REASON:
            pending.pop("accounting_hold_reason", None)
        # Older fills updated since entry: their attribution cannot be
        # established here (unchanged, deliberately unbounded).
        late_fill_stmt = select(Order.id).where(
            Order.symbol == symbol, Order.submitted_at <= closed_at,
            Order.submitted_at < entry_time, Order.filled_qty > 0,
            Order.updated_at >= entry_time,
        ).limit(1)
        blocker = live[0]["id"] if live else (
            await session.execute(late_fill_stmt)).scalar_one_or_none()
        if blocker is not None:
            _hold_close(meta, symbol, f"{AMBIGUOUS_ORDER_REASON_PREFIX}{blocker}")
            return True
        if isinstance(pending, dict) and str(
                pending.get("accounting_hold_reason") or "").startswith(AMBIGUOUS_ORDER_REASON_PREFIX):
            pending.pop("accounting_hold_reason", None)
        return False

    async def _entry_verified_unfilled(self, symbol: str, meta: dict[str, Any]) -> bool:
        """Only a terminal, identified entry with no execution can be discarded.

        Any other order in its lifetime (submitted from the entry up to the
        observed close in ``pending_close.observed_at``) makes cleanup
        uncertain; a later order for the symbol is not part of this lifetime
        (C08-01). Without a parseable observed close the scan stays unbounded.
        This is deliberately stricter than missing position data or a missing
        DB row.
        """
        if not self._sessionmaker:
            return False
        try:
            from sqlalchemy import select
            from backend.infra.schemas import Execution, Order
            entry_id = uuid.UUID(str(meta.get("entry_order_id") or ""))
            async with self._sessionmaker() as session:
                row = (await session.execute(select(Order).where(
                    Order.id == entry_id, Order.symbol == symbol,
                ))).scalar_one_or_none()
                if row is None or (row.attributes or {}).get("source") != "organism":
                    return False
                status = str(row.status).lower()
                if status == "replaced":
                    _replacement_pending(meta)
                    return False  # Zero predecessor fills do not prove a zero-fill successor.
                if status not in ACCOUNTABLE_TERMINAL_STATUSES - {"filled"}:
                    return False
                if row.filled_qty is None or Decimal(str(row.filled_qty)) != 0:
                    return False
                executions = (await session.execute(select(Execution.id).where(
                    Execution.order_id == entry_id,
                ).limit(1))).scalar_one_or_none()
                if executions is not None:
                    return False  # Order summaries can lag individual fills.
                other_stmt = select(Order.id).where(
                    Order.symbol == symbol, Order.submitted_at >= row.submitted_at,
                    Order.id != entry_id,
                )
                closed_at = _pending_close_time(meta)
                if closed_at is not None:
                    other_stmt = other_stmt.where(Order.submitted_at <= closed_at)
                other = (await session.execute(other_stmt.limit(1))).scalar_one_or_none()
                return other is None
        except Exception as exc:  # noqa: BLE001 - any lookup failure must retain unresolved accounting.
            logger.debug("Zero-fill verification unavailable for %s: %s", symbol, exc)
            return False

    async def _lookup_closed_position_fills_from_db(
        self, symbol: str, meta: dict[str, Any], *, closed_at: datetime,
    ) -> ClosedPositionFills | None:
        """Read all confirmed fill legs for an identified, closed position.

        Read-only. Fill legs are bounded to the DB entry timestamp and this
        reconciliation time. Unresolved and replaced orders (including
        pre-entry ones) block exact accounting only while they could still
        execute during this lifetime (``_order_may_affect_lifetime``); stale
        history no longer holds every later close of the symbol. The blocking
        row is named in ``pending_close.accounting_hold_reason``. Unknown
        identity, incomplete quantities or DB failure leaves the strategy close
        pending; no stored order/corpus is edited.
        """
        if not self._sessionmaker or meta.get("entry_source") == "reconciliation_orphan":
            return None
        try:
            entry_id = uuid.UUID(str(meta.get("entry_order_id") or ""))
            direction = float(meta.get("direction", 1.0))
        except (ValueError, TypeError):
            return None
        try:
            from sqlalchemy import select
            from backend.infra.schemas import Order

            async with self._sessionmaker() as session:
                anchor_stmt = select(Order.submitted_at).where(
                    Order.id == entry_id, Order.symbol == symbol,
                )
                entry_time = (await session.execute(anchor_stmt)).scalar_one_or_none()
                if entry_time is None:
                    return None
                if await self._lifetime_held(
                        session, symbol, meta, entry_time=entry_time, closed_at=closed_at):
                    return None
                stmt = select(
                    Order.id, Order.symbol, Order.side, Order.qty, Order.filled_qty,
                    Order.avg_fill_price, Order.status, Order.submitted_at,
                    Order.broker_order_id, Order.attributes,
                ).where(
                    Order.symbol == symbol, Order.submitted_at >= entry_time,
                    Order.submitted_at <= closed_at,
                )
                # Include conflicting attribution and active orders so they
                # cannot be hidden by a filled/source-only SQL filter.
                rows = list((await session.execute(stmt)).mappings().all())
                result = _closed_position_fills(
                    rows, entry_order_id=entry_id, symbol=symbol,
                    direction=direction, closed_at=closed_at,
                )
                if result is None:
                    logger.warning("Complete position fill accounting unavailable for %s", symbol)
                return result
        except Exception as exc:  # noqa: BLE001 — preserve best-effort reconciliation on DB failures
            logger.warning("Closed-position fill lookup failed for %s: %s", symbol, exc)
            return None

    async def _lookup_external_close_from_db(
        self, symbol: str, meta: dict[str, Any], *, closed_at: datetime,
    ) -> ExternalClose | None:
        """Audit 2026-10-05 C06-01: was this lifetime closed outside the engine?

        For an identified close the exact lookup refused and the broker shows
        flat. The same holds as the exact lookup apply (``_lifetime_held``),
        then ``_external_close`` classifies the symbol's orders from the entry
        on. None (unknown identity, holds, DB failure, ambiguous legs) leaves
        the close pending.

        Review: once the evidence is recordable (exact, or unbooked after
        EXTERNAL_CLOSE_APPROXIMATE_AFTER), the lot ledger is repaired and
        committed here, before the caller's artifact commit releases the entry
        gate (``_repair_external_close_lots``). Otherwise the lifetime's open
        lot would block the next entry's pending identity and be FIFO-matched
        by its exit. A failed repair returns None: the close stays pending and
        gated (``EXTERNAL_CLOSE_LOT_REPAIR_FAILED_REASON``) and the next pass
        retries. The caller measures the wait from its own earlier clock
        reading, so it never records evidence this lookup still saw waiting.
        """
        if not self._sessionmaker or meta.get("entry_source") == "reconciliation_orphan":
            return None
        try:
            entry_id = uuid.UUID(str(meta.get("entry_order_id") or ""))
            direction = float(meta.get("direction", 1.0))
        except (ValueError, TypeError):
            return None
        evidence = await self._classify_external_close(
            symbol, meta, entry_id=entry_id, direction=direction, closed_at=closed_at)
        if evidence is not None and not evidence.waiting(closed_at, self._fill_lookup_now()):
            if not await self._repair_external_close_lots(
                    symbol, meta, entry_id=entry_id, direction=direction, closed_at=closed_at):
                return None
        pending = meta.get("pending_close")
        if (isinstance(pending, dict)
                and pending.get("accounting_hold_reason") == EXTERNAL_CLOSE_LOT_REPAIR_FAILED_REASON):
            pending.pop("accounting_hold_reason", None)  # repaired, or not needed this pass
        return evidence

    def _fill_lookup_now(self) -> datetime:
        now_fn = getattr(self, "_now_fn", None)
        return now_fn() if callable(now_fn) else datetime.now(UTC)

    async def _repair_external_close_lots(
        self, symbol: str, meta: dict[str, Any], *, entry_id: uuid.UUID,
        direction: float, closed_at: datetime,
    ) -> bool:
        """Commit the external close's lot repair; False keeps the close pending.

        One WARNING per new failure (the hold reason carries it into status and
        into the 30-minute page); a later success clears the reason.
        """
        from backend.integrations.alpaca_stream import repair_external_close_lots

        pending = meta.get("pending_close")
        try:
            mark = float((pending or {}).get("observed_bar_close"))
            if not 0.0 < mark < float("inf"):
                mark = None
        except (TypeError, ValueError, AttributeError):
            mark = None
        try:
            async with self._sessionmaker() as session:
                report = await repair_external_close_lots(
                    session, symbol=symbol, entry_order_id=entry_id, closed_at=closed_at,
                    direction=direction, mark=mark,
                    mark_source="observed_bar_close" if mark is not None else "",
                )
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - the close stays pending and is retried
            if isinstance(pending, dict):
                if pending.get("accounting_hold_reason") != EXTERNAL_CLOSE_LOT_REPAIR_FAILED_REASON:
                    logger.warning(
                        "External close of %s held: %s (%s: %s); it stays pending and "
                        "entry-gated and the repair is retried every pass",
                        symbol, EXTERNAL_CLOSE_LOT_REPAIR_FAILED_REASON, type(exc).__name__, exc)
                pending["accounting_hold_reason"] = EXTERNAL_CLOSE_LOT_REPAIR_FAILED_REASON
            return False
        if report["netted"] or report["written_off"]:
            logger.warning(
                "External close lot repair for %s (entry %s, owner %s): %d close-route "
                "match(es) netted against the lifetime's lots, %d lot(s) written off "
                "(no DB row closed them; position.adjusted audit rows); committed before "
                "the artifact releases the entry gate",
                symbol, entry_id, report["owner"], len(report["netted"]), len(report["written_off"]))
        return True

    async def _classify_external_close(
        self, symbol: str, meta: dict[str, Any], *, entry_id: uuid.UUID,
        direction: float, closed_at: datetime,
    ) -> ExternalClose | None:
        """Read-only holds and classification for ``_lookup_external_close_from_db``."""
        try:
            from sqlalchemy import select
            from backend.infra.schemas import Order

            async with self._sessionmaker() as session:
                entry_time = (await session.execute(select(Order.submitted_at).where(
                    Order.id == entry_id, Order.symbol == symbol,
                ))).scalar_one_or_none()
                if entry_time is None or await self._lifetime_held(
                        session, symbol, meta, entry_time=entry_time, closed_at=closed_at):
                    return None
                # No upper bound: an order after the observed close refuses
                # the unbooked case instead of being silently left out.
                rows = list((await session.execute(select(
                    Order.id, Order.symbol, Order.side, Order.qty, Order.filled_qty,
                    Order.avg_fill_price, Order.status, Order.submitted_at,
                    Order.broker_order_id, Order.attributes,
                ).where(
                    Order.symbol == symbol, Order.submitted_at >= entry_time,
                ))).mappings().all())
            return _external_close(
                rows, entry_order_id=entry_id, symbol=symbol,
                direction=direction, closed_at=closed_at,
            )
        except Exception as exc:  # noqa: BLE001 - a failed lookup keeps the close pending
            logger.warning("External close lookup failed for %s: %s", symbol, exc)
            return None

    async def _lookup_entry_fill_from_db(
        self,
        symbol: str,
        meta: dict[str, Any] | None = None,
    ) -> tuple[float, float] | None:
        """Look up actual entry fill price/quantity for a trade record.

        Entry orders are submitted asynchronously, so the live tick only has a
        decision-time quote when it creates exit state.  At close/reconcile time
        the DB order row has the broker's authoritative fill; use it so brain
        trade PnL matches order/execution accounting.
        """
        if not self._sessionmaker:
            return None
        meta = meta or {}
        if meta.get("entry_source") == "reconciliation_orphan":
            return None

        order_id = str(meta.get("entry_order_id") or "").strip()
        entry_since: datetime | None = None
        raw_submitted_at = str(meta.get("entry_submitted_at") or "").strip()
        if raw_submitted_at:
            try:
                entry_since = datetime.fromisoformat(
                    raw_submitted_at.replace("Z", "+00:00"),
                )
            except ValueError:
                entry_since = None
        if entry_since is None:
            try:
                raw_entry_time = float(meta.get("entry_time", 0) or 0)
                if raw_entry_time > 0:
                    entry_since = datetime.fromtimestamp(raw_entry_time, tz=UTC)
            except (TypeError, ValueError, OSError):
                entry_since = None

        try:
            from sqlalchemy import select, text as sa_text
            from backend.infra.schemas import Order

            async with self._sessionmaker() as session:
                rows = []
                if entry_since is not None:
                    entry_side = (
                        "sell"
                        if float(meta.get("direction", 1.0) or 1.0) < 0
                        else "buy"
                    )
                    stmt = (
                        select(Order.avg_fill_price, Order.filled_qty)
                        .where(
                            Order.symbol == symbol,
                            Order.side == entry_side,
                            Order.status == "filled",
                            Order.submitted_at
                            >= entry_since - timedelta(minutes=2),
                            sa_text("attributes->>'source' = 'organism'"),
                        )
                        .order_by(Order.submitted_at.asc())
                    )
                    rows = list((await session.execute(stmt)).all())

                if not rows and order_id:
                    try:
                        order_uuid = uuid.UUID(order_id)
                    except ValueError:
                        order_uuid = None
                    if order_uuid is not None:
                        stmt = (
                            select(Order.avg_fill_price, Order.filled_qty)
                            .where(
                                Order.id == order_uuid,
                                Order.symbol == symbol,
                                Order.status == "filled",
                                sa_text("attributes->>'source' = 'organism'"),
                            )
                        )
                        rows = list((await session.execute(stmt)).all())

                total_qty = 0.0
                total_notional = 0.0
                for price_raw, qty_raw in rows:
                    if price_raw is None or qty_raw is None:
                        continue
                    price = float(price_raw)
                    qty = float(qty_raw)
                    if price <= 0 or qty <= 0:
                        continue
                    total_qty += qty
                    total_notional += price * qty
                if total_qty > 0:
                    avg_price = total_notional / total_qty
                    logger.info(
                        "DB fill price for %s entry: $%.2f qty=%.4f",
                        symbol,
                        avg_price,
                        total_qty,
                    )
                    return avg_price, total_qty
        except Exception as e:
            logger.debug("DB entry fill lookup failed for %s: %s", symbol, e)
        return None

    async def _lookup_exit_fill_from_db(self, symbol: str) -> float | None:
        """Look up actual exit fill price from DB for a recently closed position.

        Queries the most recent filled sell order for this symbol with
        organism source attribution.  Returns the avg_fill_price if found,
        or None if no DB session is available or no matching order exists.
        """
        if not self._sessionmaker:
            return None
        try:
            from sqlalchemy import select, text as sa_text
            from backend.infra.schemas import Order

            async with self._sessionmaker() as session:
                stmt = (
                    select(Order.avg_fill_price)
                    .where(
                        Order.symbol == symbol,
                        Order.side == "sell",
                        Order.status == "filled",
                        sa_text("attributes->>'source' = 'organism'"),
                    )
                    .order_by(Order.updated_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.scalar_one_or_none()
                if row is not None and float(row) > 0:
                    price = float(row)
                    logger.info(
                        "DB fill price for %s exit: $%.2f", symbol, price,
                    )
                    return price
        except Exception as e:
            logger.debug("DB exit fill lookup failed for %s: %s", symbol, e)
        return None
