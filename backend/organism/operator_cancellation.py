"""Bounded broker-confirmed cancellation of attributed organism entries.

The emergency endpoint requires durable operator halt and tick drain. The
engine's tracked-entry reconciliation runs under its tick/startup authority;
ordinary ticks observe, while EOD/startup/drawdown may cancel exact entries.
Protective exits, DB order statuses and fill evidence are never mutated here.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import func, or_, select

from backend.infra.schemas import Execution, Order, PositionLot

INVENTORY_LIMIT = 256
CALL_TIMEOUT = 2.0
TOTAL_TIMEOUT = 12.0
CONFIRM_ATTEMPTS = 3
DB_TERMINAL = ('filled', 'canceled', 'cancelled', 'expired', 'rejected')
CANCELLED = {'canceled', 'cancelled'}
ACTIVE = {'new', 'accepted', 'pending_new', 'accepted_for_bidding', 'partially_filled', 'pending_cancel', 'held'}


class CancellationUnverified(Exception):
    """Fixed reason code; never contains broker response bodies or secrets."""


def _number(value):
    if isinstance(value, bool):
        raise CancellationUnverified('invalid_order_quantity')
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise CancellationUnverified('invalid_order_quantity') from None
    if not parsed.is_finite() or parsed < 0:
        raise CancellationUnverified('invalid_order_quantity')
    return parsed


def _validate_order(observed, row):
    if (not isinstance(observed, dict) or observed.get('id') != row.broker_order_id
            or observed.get('client_order_id') != row.client_idempotency_key
            or observed.get('symbol') != row.symbol or observed.get('side') != row.side
            or _number(observed.get('qty')) != _number(row.qty)):
        raise CancellationUnverified('broker_identity_mismatch')
    if (observed.get('replaces') or observed.get('replaced_by') or observed.get('legs')
            or observed.get('order_class') not in (None, '', 'simple')
            or observed.get('status') == 'replaced'):
        raise CancellationUnverified('replacement_or_linked_order_unverified')
    filled, qty = _number(observed.get('filled_qty')), _number(observed.get('qty'))
    if qty <= 0 or filled > qty or (observed['status'] == 'filled' and filled != qty):
        raise CancellationUnverified('invalid_order_quantity')
    return observed['status'], filled


async def _one_order(broker, row, *, cancel=True):
    receipt = {'entry_order_id': str(row.id), 'broker_order_id': row.broker_order_id,
               'symbol': row.symbol, 'cancel_requested': False, 'cancel_confirmed': False}
    if row.status == 'replaced':
        receipt['issue'] = 'replacement_or_linked_order_unverified'
        return receipt
    if not row.broker_order_id:
        receipt['issue'] = 'broker_dispatch_unresolved'
        return receipt
    try:
        if (not isinstance(row.broker_order_id, str) or str(UUID(row.broker_order_id)) != row.broker_order_id
                or row.side not in {'buy', 'sell'} or not isinstance(row.symbol, str) or not row.symbol
                or not isinstance(row.client_idempotency_key, str) or not row.client_idempotency_key):
            raise CancellationUnverified('invalid_database_order_identity')
        observed = await asyncio.wait_for(broker.get_order(row.broker_order_id), CALL_TIMEOUT)
        state, filled = _validate_order(observed, row)
        if cancel and state not in CANCELLED | {'expired', 'rejected', 'filled'}:
            if state not in ACTIVE:
                raise CancellationUnverified('unknown_broker_order_status')
            if state != 'pending_cancel':
                receipt['cancel_requested'] = True
                try:
                    await asyncio.wait_for(broker.cancel_order(row.broker_order_id), CALL_TIMEOUT)
                except Exception:  # noqa: BLE001 - Confirm uncertain transport outcomes via GET.
                    receipt['cancel_request_error'] = True
            for attempt in range(CONFIRM_ATTEMPTS):
                observed = await asyncio.wait_for(broker.get_order(row.broker_order_id), CALL_TIMEOUT)
                state, filled = _validate_order(observed, row)
                if state in CANCELLED | {'expired', 'rejected', 'filled'}:
                    break
                if state not in ACTIVE:
                    raise CancellationUnverified('unknown_broker_order_status')
                if attempt + 1 < CONFIRM_ATTEMPTS:
                    await asyncio.sleep(0.1)
        receipt.update(broker_status=state, filled_qty=str(filled), cancel_confirmed=state in CANCELLED)
        if filled > 0 and observed.get('filled_avg_price') is not None:
            receipt['fill_price'] = str(_number(observed['filled_avg_price']))
        if filled > 0 or state == 'filled':
            receipt['issue'] = 'fill_reconciliation_required'
        elif state not in CANCELLED | {'expired', 'rejected'}:
            receipt['issue'] = 'cancellation_not_confirmed'
    except CancellationUnverified as exc:
        receipt['issue'] = str(exc)
    except Exception:  # noqa: BLE001 - Withhold success; never expose private transport errors.
        receipt['issue'] = 'broker_confirmation_unavailable'
    return receipt


async def _accounted_entry_fill(db, row, receipt, engine, broker):
    """Read-only proof before releasing a filled order's submission blocker.

    Preserve execution/lot identity and the engine's position tracking. A closed
    lot's original quantity/cost remains evidence after partial or full exits;
    remaining quantity is deliberately not equated with original fill quantity.
    """
    filled, price = _number(receipt['filled_qty']), _number(receipt.get('fill_price'))
    terminal = CANCELLED | {'expired', 'rejected', 'filled'}
    if (receipt['broker_status'] not in terminal or row.status not in terminal
            or filled <= 0 or price <= 0 or _number(row.filled_qty) != filled):
        return False
    tolerance = filled * Decimal('0.0000005') + Decimal('0.000001')
    expected_cash = filled * price
    if abs(filled * _number(row.avg_fill_price) - expected_cash) > tolerance:
        return False
    for quantity, cash, model in (
        (Execution.fill_qty, Execution.fill_qty * Execution.fill_price, Execution),
        (PositionLot.qty, PositionLot.qty * PositionLot.cost_basis, PositionLot),
    ):
        observed_qty, observed_cash = (await db.execute(select(
            func.coalesce(func.sum(quantity), 0), func.coalesce(func.sum(cash), 0),
        ).where(model.order_id == row.id))).one()
        if (_number(observed_qty) != filled
                or abs(_number(observed_cash) - expected_cash) > tolerance):
            return False
    positions = await asyncio.wait_for(broker.get_positions(), CALL_TIMEOUT)
    if (not isinstance(positions, list) or len(positions) > INVENTORY_LIMIT
            or any(not isinstance(item, dict) or not isinstance(item.get('symbol'), str)
                   for item in positions)
            or len({item['symbol'] for item in positions}) != len(positions)):
        return False
    position = next((item for item in positions if item['symbol'] == row.symbol), None)
    if position is None:
        # A stale completed-ID alone may predate later fills. Require the exact
        # closed trade quantity/cost plus exhausted original lots and fresh flat.
        # Audit 2026-10-05 C06-01: a close outside the engine never exhausts the
        # engine's own lots (a platform close route books it under the operator's
        # owner; the Alpaca dashboard or a broker liquidation books nothing). Its
        # 'external_close' reconciliation artifact, with the same identity,
        # quantity and entry cost, proves this fill was accounted instead.
        completed = getattr(engine, '_accounting_completed_entries', {}).get(str(row.id))
        remaining = (await db.execute(select(func.coalesce(func.sum(PositionLot.remaining_qty), 0))
                                      .where(PositionLot.order_id == row.id))).scalar_one()
        exhausted = _number(remaining) == 0
        return any(
            trade.entry_order_id == str(row.id) and trade.closed_at == completed
            and (not trade.is_reconciliation_artifact and exhausted
                 or trade.is_reconciliation_artifact
                 and getattr(trade, 'exit_reason', None) == 'external_close')
            and _number(trade.shares) == filled
            and abs(_number(trade.entry_price) * filled - expected_cash) <= tolerance
            for trade in getattr(engine, '_all_trades', [])
        )
    meta = getattr(engine, '_entry_metadata', {}).get(row.symbol, {})
    level = getattr(engine, '_exit_levels', {}).get(row.symbol)
    direction = 1 if row.side == 'buy' else -1
    if (level is None or not isinstance(position, dict) or not meta or meta.get('pending_close')
            or meta.get('direction') != direction or getattr(level, 'direction', None) != direction
            or getattr(level, 'symbol', None) != row.symbol):
        return False
    if str(meta.get('entry_order_id')) != str(row.id):
        if row.attributes.get('reason') != 'pyramid_add':
            return False
        anchor = await db.get(Order, UUID(str(meta.get('entry_order_id'))))
        if (anchor is None or anchor.symbol != row.symbol or anchor.side != row.side
                or anchor.user_id != row.user_id or not isinstance(anchor.attributes, dict)
                or anchor.attributes.get('source') != 'organism'
                or anchor.attributes.get('reason') != 'organism_entry'
                or _number(anchor.filled_qty) <= 0):
            return False
    quantity = Decimal(str(position.get('qty')))
    expected_side = 'long' if row.side == 'buy' else 'short'
    remaining = (await db.execute(select(func.coalesce(func.sum(PositionLot.remaining_qty), 0))
                                 .where(PositionLot.user_id == row.user_id,
                                        PositionLot.symbol == row.symbol))).scalar_one()
    return (quantity.is_finite() and quantity * direction > 0
            and position.get('side') == expected_side and _number(remaining) == abs(quantity))



async def confirm_tracked_entries(engine, *, cancel=False, broker=None):
    """Resolve only exact tracked entry identities, under the engine tick lock.

    EOD/startup/drawdown may request cancellation. Ordinary reconciliation only
    observes. No DB summary writes, replacement guesses, or order submissions.
    Uncertain results never authorize removal from the engine's pending maps.
    """
    result = {'orders': [], 'issues': [], 'db_modified': False}
    pending = dict(getattr(engine, '_pending_entry_order_ids', {}))
    if set(getattr(engine, '_pending_entry', {})) - set(pending):
        result['issues'].append('pending_entry_identity_missing')
    if not pending:
        return result
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT):
            if len(pending) > INVENTORY_LIMIT:
                raise CancellationUnverified('entry_inventory_limit')
            ids = [UUID(value) for value in pending.values()]
            if (len(set(ids)) != len(ids)
                    or any(str(identity) != value for identity, value in zip(ids, pending.values()))):
                raise CancellationUnverified('invalid_tracked_entry_identity')
            factory = getattr(engine, '_sessionmaker', None)
            if factory is None:
                raise CancellationUnverified('entry_database_unavailable')
            if broker is None:
                from backend.integrations.alpaca_broker import get_alpaca_broker_client
                broker = get_alpaca_broker_client()
            if (getattr(broker, 'is_paper', None) is not True
                    or getattr(broker, 'base_url', '').rstrip('/') != 'https://paper-api.alpaca.markets'):
                raise CancellationUnverified('verified_paper_broker_required')
            async with factory() as db:
                rows = list((await db.execute(select(Order).where(Order.id.in_(ids)))).scalars().all())
                by_id = {str(row.id): row for row in rows}
                # A slow prefix must not starve later orders on every bounded
                # retry. Advance before awaiting so timeouts/cancellation also
                # yield the next turn; the cursor never removes attribution.
                entries = list(pending.items())
                last = getattr(engine, '_pending_entry_confirmation_cursor', None)
                last_index = next((i for i, (_, identity) in enumerate(entries) if identity == last), -1)
                start = (last_index + 1) % len(entries)
                for symbol, identity in entries[start:] + entries[:start]:
                    engine._pending_entry_confirmation_cursor = identity
                    row = by_id.get(identity)
                    attrs = row.attributes if row is not None and isinstance(row.attributes, dict) else {}
                    if (row is None or row.symbol != symbol or attrs.get('source') != 'organism'
                            or attrs.get('reason') not in {'organism_entry', 'pyramid_add'}
                            or not str(row.client_idempotency_key).startswith('organism_')
                            or str(row.client_idempotency_key).startswith('organism_exit_')):
                        result['issues'].append('tracked_entry_attribution_unverified')
                        continue
                    receipt = await _one_order(broker, row, cancel=cancel)
                    receipt['release_pending'] = False
                    state = receipt.get('broker_status')
                    if state in CANCELLED | {'expired', 'rejected', 'filled'}:
                        filled = _number(receipt.get('filled_qty'))
                        if filled == 0 and state != 'filled' and not receipt.get('issue'):
                            # Contradictory local fill evidence must not disappear
                            # merely because a broker response currently says zero.
                            no_fills = _number(row.filled_qty) == 0
                            for model in (Execution, PositionLot):
                                count = (await db.execute(select(func.count()).select_from(model)
                                                         .where(model.order_id == row.id))).scalar_one()
                                no_fills = no_fills and count == 0
                            receipt['release_pending'] = no_fills
                            receipt['resolution'] = 'verified_unfilled' if no_fills else 'unverified'
                        elif filled > 0:
                            try:
                                receipt['release_pending'] = await _accounted_entry_fill(db, row, receipt, engine, broker)
                                if receipt['release_pending']:
                                    receipt['resolution'] = 'accounted_fill'
                                    receipt.pop('issue', None)
                            except (CancellationUnverified, InvalidOperation, ValueError, TypeError):
                                pass
                    result['orders'].append(receipt)
                    if not receipt['release_pending']:
                        result['issues'].append(receipt.get('issue', 'entry_resolution_unverified'))
    except CancellationUnverified as exc:
        result['issues'].append(str(exc))
    except TimeoutError:
        result['issues'].append('cancellation_deadline_exceeded')
    except Exception:  # noqa: BLE001 - Keep attribution; never expose transport payloads.
        result['issues'].append('entry_confirmation_unavailable')
    result['issues'] = sorted(set(result['issues']))
    return result


async def _open_inventory(broker):
    """A bounded complete page or an explicit refusal; never infer truncation away."""
    response = await asyncio.wait_for(broker._make_request_with_retry(
        'GET', 'https://paper-api.alpaca.markets/v2/orders',
        params={'status': 'open', 'limit': INVENTORY_LIMIT + 1, 'nested': 'true'}), CALL_TIMEOUT)
    if response.status_code != 200:
        raise CancellationUnverified('broker_open_inventory_unavailable')
    rows = response.json()
    if not isinstance(rows, list) or len(rows) > INVENTORY_LIMIT:
        raise CancellationUnverified('broker_open_inventory_unbounded')
    ids, clients = set(), set()
    for row in rows:
        if not isinstance(row, dict):
            raise CancellationUnverified('broker_open_inventory_invalid')
        identifier, client = row.get('id'), row.get('client_order_id')
        try:
            valid = isinstance(identifier, str) and str(UUID(identifier)) == identifier
        except ValueError:
            valid = False
        if (not valid or not isinstance(client, str) or not client
                or identifier in ids or client in clients or row.get('status') not in ACTIVE):
            raise CancellationUnverified('broker_open_inventory_invalid')
        ids.add(identifier); clients.add(client)
    return rows


async def cancel_entry_orders(engine, db, control, *, broker=None):
    """Return explicit complete/incomplete result, retaining all fill tracking.

    The inventory includes broker-open IDs even when DB status claims terminal,
    nonterminal DB orders, and exact IDs still tracked by the drained engine.
    Limits, missing attribution/IDs and broker ambiguity are
    incomplete. A broker-confirmed partial cancellation still needs fill/position
    reconciliation and is never presented as flat or fully resolved.
    """
    result = {'scope': 'attributed_organism_entries', 'status': 'incomplete',
              'confirmed_cancelled': 0, 'preserved_orders': 0, 'orders': [], 'issues': [],
              'protective_exits_preserved': True, 'db_order_statuses_modified': False}
    if (control.get('operator_halted') is not True or control.get('entries_halted') is not True
            or control.get('drained') is not True or engine is None):
        result['issues'].append('authoritative_drained_halt_required')
        return result
    try:
        async with asyncio.timeout(TOTAL_TIMEOUT):
            if broker is None:
                from backend.integrations.alpaca_broker import get_alpaca_broker_client
                broker = get_alpaca_broker_client()
            if getattr(broker, 'is_paper', None) is not True or getattr(broker, 'base_url', '').rstrip('/') != 'https://paper-api.alpaca.markets':
                result['issues'].append('verified_paper_broker_required')
                return result
            opened = await _open_inventory(broker)
            result['broker_open_before'] = {'complete': True, 'count': len(opened)}
            pending = dict(getattr(engine, '_pending_entry_order_ids', {}))
            pending_symbols = set(getattr(engine, '_pending_entry', {}))
            if pending_symbols - set(pending):
                result['issues'].append('pending_entry_identity_missing')
            ids = {UUID(str(value)) for value in pending.values()}
            query = (select(Order).where(or_(Order.status.not_in(DB_TERMINAL), Order.id.in_(ids),
                     Order.broker_order_id.in_([item['id'] for item in opened]),
                     Order.client_idempotency_key.in_([item['client_order_id'] for item in opened])))
                     .order_by(Order.created_at, Order.id).limit(INVENTORY_LIMIT + 1))
            rows = list((await db.execute(query)).scalars().all())
            if len(rows) > INVENTORY_LIMIT:
                result['issues'].append('entry_inventory_limit')
                return result
            if ids - {row.id for row in rows}:
                result['issues'].append('tracked_entry_database_row_missing')
            # Historical fake DB cancellations are not evidence of broker closure.
            # Unmapped broker rows are preserved, never guessed to be safe entries.
            for observed in opened:
                matches = [row for row in rows if row.broker_order_id == observed['id']
                           or row.client_idempotency_key == observed['client_order_id']]
                if len(matches) != 1:
                    result['issues'].append('broker_open_identity_unmatched')
                    continue
                try:
                    row = matches[0]
                    if (row.broker_order_id != observed['id'] or row.client_idempotency_key != observed['client_order_id']
                            or row.symbol != observed.get('symbol') or row.side != observed.get('side')
                            or _number(row.qty) != _number(observed.get('qty'))):
                        raise CancellationUnverified('broker_open_identity_mismatch')
                except CancellationUnverified as exc:
                    result['issues'].append(str(exc))
            candidates = []
            for row in rows:
                attrs = row.attributes if isinstance(row.attributes, dict) else {}
                entry = (attrs.get('source') == 'organism' and attrs.get('reason') in {'organism_entry', 'pyramid_add'}
                         and isinstance(row.client_idempotency_key, str)
                         and row.client_idempotency_key.startswith('organism_')
                         and not row.client_idempotency_key.startswith('organism_exit_'))
                if entry:
                    if row.id in ids and pending.get(row.symbol) != str(row.id):
                        result['issues'].append('tracked_entry_symbol_mismatch')
                        continue
                    candidates.append(row)
                else:
                    result['preserved_orders'] += 1
                    if row.id in ids or (attrs.get('source') == 'organism'
                                         and not str(row.client_idempotency_key).startswith('organism_exit_')):
                        result['issues'].append('entry_role_unverified')
            broker_ids = [row.broker_order_id for row in candidates if row.broker_order_id]
            client_ids = [row.client_idempotency_key for row in candidates]
            if len(set(broker_ids)) != len(broker_ids) or len(set(client_ids)) != len(client_ids):
                result['issues'].append('ambiguous_entry_identity')
                return result
            for row in candidates:
                receipt = await _one_order(broker, row)
                result['orders'].append(receipt)
                result['confirmed_cancelled'] += int(receipt['cancel_confirmed'])
                if receipt.get('issue'):
                    result['issues'].append(receipt['issue'])
            final_open = await _open_inventory(broker)
            result['broker_open_after'] = {'complete': True, 'count': len(final_open)}
            final_ids = {item['id'] for item in final_open}
            if final_ids - {item['id'] for item in opened}:
                result['issues'].append('broker_open_inventory_changed')
            if final_ids & set(broker_ids):
                result['issues'].append('attributed_entry_still_open')
    except CancellationUnverified as exc:
        result['issues'].append(str(exc))
    except TimeoutError:
        result['issues'].append('cancellation_deadline_exceeded')
    except Exception:  # noqa: BLE001 - Any inventory failure remains explicitly incomplete.
        result['issues'].append('entry_inventory_unavailable')
    result['issues'] = sorted(set(result['issues']))
    result['status'] = 'complete' if not result['issues'] else 'incomplete'
    return result
