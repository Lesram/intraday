"""Bounded broker-confirmed cancellation of attributed organism entries.

Caller must first durably latch operator halt and drain the current tick. The
scope is organism entries, never all account orders. Protective exits, DB order
statuses, fill evidence and engine tracking are left to their normal owners.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import or_, select

from backend.infra.schemas import Order

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
    if qty <= 0 or filled > qty:
        raise CancellationUnverified('invalid_order_quantity')
    return observed['status'], filled


async def _one_order(broker, row):
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
        if state not in CANCELLED | {'expired', 'rejected', 'filled'}:
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
        if filled > 0 or state == 'filled':
            receipt['issue'] = 'fill_reconciliation_required'
        elif state not in CANCELLED | {'expired', 'rejected'}:
            receipt['issue'] = 'cancellation_not_confirmed'
    except CancellationUnverified as exc:
        receipt['issue'] = str(exc)
    except Exception:  # noqa: BLE001 - Withhold success; never expose private transport errors.
        receipt['issue'] = 'broker_confirmation_unavailable'
    return receipt


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
