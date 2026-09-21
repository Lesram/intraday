"""Operator stop must never report DB-only or unconfirmed broker cancellation."""
from __future__ import annotations

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.organism import operator_cancellation as cancellation


HALT = {'operator_halted': True, 'entries_halted': True, 'drained': True,
        'persistence': {'configured': True, 'persistence': 'verified'}, 'halt_epoch': 1,
        'governance': {'operator_control_fault': False}, 'runtime_ready': True, 'protective_exits_active': True}


def entry(**changes):
    return SimpleNamespace(id=uuid4(), broker_order_id=str(uuid4()), symbol='AAPL', side='buy',
                           qty=Decimal('10'), filled_qty=Decimal('0'), status='new',
                           client_idempotency_key='organism_AAPL_actual-client-key',
                           attributes={'source': 'organism', 'reason': 'organism_entry'}, **changes)


def broker_row(row, state='new', filled='0', **changes):
    return {'id': row.broker_order_id, 'client_order_id': row.client_idempotency_key,
            'symbol': row.symbol, 'side': row.side, 'qty': str(row.qty), 'filled_qty': filled,
            'status': state, **changes}


def fixtures(rows):
    engine = SimpleNamespace(_pending_entry={}, _pending_entry_order_ids={})
    inventory = MagicMock(); inventory.scalars.return_value.all.return_value = rows
    db = AsyncMock(); db.execute.return_value = inventory
    broker = SimpleNamespace(is_paper=True, base_url='https://paper-api.alpaca.markets',
                             get_order=AsyncMock(), cancel_order=AsyncMock(),
                             _make_request_with_retry=AsyncMock(return_value=SimpleNamespace(status_code=200, json=lambda: [])))
    return engine, db, broker


async def execute(rows, outcomes, **kwargs):
    engine, db, broker = fixtures(rows)
    broker.get_order.side_effect = outcomes
    result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker, **kwargs)
    return result, engine, db, broker


@pytest.mark.asyncio
async def test_exact_broker_confirmation_without_db_or_tracking_mutation():
    row = entry(); engine, db, broker = fixtures([row])
    engine._pending_entry = {'AAPL': 42}; engine._pending_entry_order_ids = {'AAPL': str(row.id)}
    broker.get_order.side_effect = [broker_row(row), broker_row(row, 'canceled')]
    result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker)
    assert result['status'] == 'complete' and result['confirmed_cancelled'] == 1
    broker.cancel_order.assert_awaited_once_with(row.broker_order_id)
    assert str(row.id) != row.broker_order_id
    assert row.status == 'new' and row.filled_qty == 0
    assert engine._pending_entry_order_ids == {'AAPL': str(row.id)}
    assert engine._pending_entry == {'AAPL': 42}
    db.commit.assert_not_awaited(); db.add.assert_not_called()


@pytest.mark.asyncio
async def test_empty_completion_requires_independent_empty_broker_inventory(monkeypatch):
    engine, db, broker = fixtures([])
    factory = MagicMock(return_value=broker)
    monkeypatch.setattr('backend.integrations.alpaca_broker.get_alpaca_broker_client', factory)
    result = await cancellation.cancel_entry_orders(engine, db, HALT)
    assert result['status'] == 'complete' and result['confirmed_cancelled'] == 0
    factory.assert_called_once()
    assert broker._make_request_with_retry.await_count == 2
    assert result['broker_open_before'] == result['broker_open_after'] == {'complete': True, 'count': 0}
    broker.get_order.assert_not_awaited(); broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_protective_exit_and_unrelated_manual_orders_are_preserved():
    exit_order = entry(); exit_order.attributes = {'source': 'organism', 'reason': 'stop_loss'}
    exit_order.client_idempotency_key = 'organism_exit_AAPL_protected'
    manual = entry(); manual.attributes = {'source': 'manual'}
    result, _, _, broker = await execute([exit_order, manual], [])
    assert result['status'] == 'complete' and result['preserved_orders'] == 2
    broker.get_order.assert_not_awaited(); broker.cancel_order.assert_not_awaited()
    assert exit_order.status == manual.status == 'new'


@pytest.mark.asyncio
@pytest.mark.parametrize('state,filled', [('partially_filled', '3'), ('new', '3')])
async def test_partial_fill_remainder_cancelled_but_exposure_stays_incomplete(state, filled):
    row = entry(); row.status = state
    result, _, _, broker = await execute([row], [broker_row(row, state, filled), broker_row(row, 'canceled', filled)])
    assert result['confirmed_cancelled'] == 1 and result['status'] == 'incomplete'
    assert result['issues'] == ['fill_reconciliation_required']
    assert result['orders'][0]['filled_qty'] == '3'
    assert row.filled_qty == 0 and row.status == state
    broker.cancel_order.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['pending_cancel', 'new', 'accepted'])
async def test_acknowledgement_without_terminal_confirmation_is_incomplete(state):
    row = entry()
    result, _, _, _ = await execute([row], [broker_row(row), *[broker_row(row, state)] * 3])
    assert result['status'] == 'incomplete' and result['confirmed_cancelled'] == 0
    assert 'cancellation_not_confirmed' in result['issues'] and row.status == 'new'


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [
    {'id': 'different-broker'}, {'client_order_id': 'different-client'}, {'symbol': 'MSFT'},
    {'side': 'sell'}, {'qty': '9'}, {'qty': 'NaN'}, {'filled_qty': 'Infinity'},
    {'filled_qty': True}, {'filled_qty': '11'}, {'replaced_by': 'successor'},
    {'replaces': 'predecessor'}, {'order_class': 'bracket'}, {'legs': [{'id': 'protective'}]},
])
async def test_unverified_identity_or_linkage_never_cancelled(changes):
    row = entry()
    result, _, _, broker = await execute([row], [broker_row(row, **changes)])
    assert result['status'] == 'incomplete' and result['confirmed_cancelled'] == 0
    broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['replaced', 'done_for_day', 'unknown'])
async def test_unknown_or_replaced_terminal_vocabulary_is_not_success(state):
    row = entry()
    result, _, _, broker = await execute([row], [broker_row(row, state)])
    assert result['status'] == 'incomplete' and result['confirmed_cancelled'] == 0
    broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_replaced_db_order_is_not_reinterpreted_as_confirmed_cancel():
    row = entry(); row.status = 'replaced'
    result, _, _, broker = await execute([row], [broker_row(row, 'canceled')])
    assert result['status'] == 'incomplete'
    broker.get_order.assert_not_awaited(); broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_broker_error_and_fill_race_are_not_fabricated_cancellations():
    for state, filled in [('filled', '10'), ('new', '0')]:
        row = entry(); engine, db, broker = fixtures([row])
        broker.get_order.side_effect = [broker_row(row), *[broker_row(row, state, filled)] * 3]
        broker.cancel_order.side_effect = HTTPException(422, 'private broker error')
        result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker)
        assert result['status'] == 'incomplete' and result['confirmed_cancelled'] == 0
        assert 'private broker error' not in str(result) and row.status == 'new'


@pytest.mark.asyncio
async def test_cancel_timeout_can_be_confirmed_by_later_terminal_get():
    row = entry(); engine, db, broker = fixtures([row])
    broker.get_order.side_effect = [broker_row(row), broker_row(row, 'canceled')]
    broker.cancel_order.side_effect = TimeoutError()
    result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker)
    assert result['status'] == 'complete' and result['confirmed_cancelled'] == 1


@pytest.mark.asyncio
async def test_missing_mapping_or_row_and_orphan_pending_remain_incomplete():
    row = entry(); row.broker_order_id = None
    engine, db, broker = fixtures([row])
    engine._pending_entry = {'AAPL': 1, 'MSFT': 1}
    engine._pending_entry_order_ids = {'AAPL': str(uuid4())}
    result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker)
    assert result['status'] == 'incomplete'
    assert {'broker_dispatch_unresolved', 'tracked_entry_database_row_missing', 'pending_entry_identity_missing'} <= set(result['issues'])
    broker.cancel_order.assert_not_awaited()
    assert len(engine._pending_entry) == 2


@pytest.mark.asyncio
async def test_ambiguous_identity_and_inventory_overflow_block_before_mutation(monkeypatch):
    first = entry(); second = entry(); second.broker_order_id = first.broker_order_id
    result, _, _, broker = await execute([first, second], [])
    assert result['issues'] == ['ambiguous_entry_identity']
    broker.cancel_order.assert_not_awaited()
    monkeypatch.setattr(cancellation, 'INVENTORY_LIMIT', 1)
    result, _, _, broker = await execute([first, second], [])
    assert result['issues'] == ['entry_inventory_limit']; broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_unverified_halt_never_queries_or_calls_broker():
    engine, db, broker = fixtures([entry()])
    result = await cancellation.cancel_entry_orders(engine, db, {**HALT, 'drained': False}, broker=broker)
    assert result['issues'] == ['authoritative_drained_halt_required']
    db.execute.assert_not_awaited(); broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_deadline_is_explicit_and_keeps_tracking(monkeypatch):
    row = entry(); engine, db, broker = fixtures([row])
    async def hang(*args): await asyncio.sleep(1)
    db.execute.side_effect = hang
    monkeypatch.setattr(cancellation, 'TOTAL_TIMEOUT', 0.001)
    result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker)
    assert result['status'] == 'incomplete' and result['issues'] == ['cancellation_deadline_exceeded']
    broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_halts_before_db_initialization_failure(monkeypatch):
    from backend.api.routes import risk
    from backend.organism import operator_controls
    sequence = []
    async def halt(app): sequence.append('halt'); return dict(HALT)
    async def unavailable():
        sequence.append('db'); raise RuntimeError('private DB credentials')
        yield  # async generator contract
    monkeypatch.setattr(operator_controls, 'halt_entries', halt)
    monkeypatch.setattr(operator_controls, 'control_status', lambda app: dict(HALT))
    monkeypatch.setattr(risk, 'get_db_session', unavailable)
    with pytest.raises(HTTPException) as error:
        await risk.trigger_emergency_stop(SimpleNamespace(reason='operator stop test'), SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
                                          SimpleNamespace(roles=['admin'], username='admin'))
    assert sequence == ['halt', 'db'] and error.value.status_code == 503
    assert error.value.detail['control']['operator_halted'] is True
    assert 'private DB credentials' not in str(error.value.detail)


@pytest.mark.asyncio
async def test_api_incomplete_cancellation_returns_audit_id_and_retained_halt(monkeypatch):
    from backend.api.routes import risk
    from backend.organism import operator_controls
    from backend.models.risk import EmergencyStop
    from datetime import datetime, timezone
    db = AsyncMock()
    async def sessions(): yield db
    monkeypatch.setattr(risk, 'get_db_session', sessions)
    monkeypatch.setattr(operator_controls, 'halt_entries', AsyncMock(return_value=dict(HALT)))
    monkeypatch.setattr(operator_controls, 'control_status', lambda app: dict(HALT))
    monkeypatch.setattr(risk, 'get_user_id_from_username', AsyncMock(return_value=1))
    outcome = {'scope': 'attributed_organism_entries', 'status': 'incomplete', 'confirmed_cancelled': 0,
               'issues': ['cancellation_not_confirmed']}
    monkeypatch.setattr(cancellation, 'cancel_entry_orders', AsyncMock(return_value=outcome))
    audit = EmergencyStop(id=uuid4(), user_id=1, triggered_by=1, reason='test', strategies_stopped=0,
                          orders_cancelled=0, status='active', triggered_at=datetime.now(timezone.utc), resolved_at=None, resolved_by=None)
    record = AsyncMock(return_value=audit)
    monkeypatch.setattr(risk.RiskManager, 'trigger_emergency_stop', record)
    with pytest.raises(HTTPException) as error:
        await risk.trigger_emergency_stop(SimpleNamespace(reason='operator stop test'), SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
                                          SimpleNamespace(roles=['admin'], username='admin'))
    assert error.value.status_code == 503 and error.value.detail['audit_id'] == str(audit.id)
    assert error.value.detail['control']['operator_halted'] is True
    record.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('broker_id', ['../orders', 'not-an-id', '', True])
async def test_invalid_broker_identifier_cannot_reach_transport(broker_id):
    row = entry(); row.broker_order_id = broker_id
    result, _, _, broker = await execute([row], [])
    assert result['status'] == 'incomplete' and result['confirmed_cancelled'] == 0
    broker.get_order.assert_not_awaited(); broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_actual_halt_persistence_route_and_flat_cancellation_integration(monkeypatch, tmp_path):
    from backend.api.routes import risk
    from backend.organism import operator_controls
    from backend.organism.governance import GovernanceController
    from backend.models.risk import EmergencyStop
    from datetime import datetime, timezone
    control_file = tmp_path / 'authority.json'
    monkeypatch.setenv(operator_controls.STATE_ENV, str(control_file))
    operator_controls.initialize_control_state(control_file, operator_halted=False, reason='isolated fixture')
    engine, db, broker = fixtures([])
    engine.governance = GovernanceController(); engine._tick_lock = asyncio.Lock(); engine._initialized = True
    engine.brain = SimpleNamespace(brain_dir=tmp_path / 'brain')
    app = SimpleNamespace(state=SimpleNamespace(organism_scheduler=SimpleNamespace(_engine=engine, is_running=True),
                                               organism_governance=GovernanceController()))
    async def sessions(): yield db
    monkeypatch.setattr(risk, 'get_db_session', sessions)
    monkeypatch.setattr(risk, 'get_user_id_from_username', AsyncMock(return_value=1))
    monkeypatch.setattr('backend.integrations.alpaca_broker.get_alpaca_broker_client',
                        MagicMock(return_value=broker))
    audit = EmergencyStop(id=uuid4(), user_id=1, triggered_by=1, reason='isolated fixture', strategies_stopped=0,
                          orders_cancelled=0, status='active', triggered_at=datetime.now(timezone.utc), resolved_at=None, resolved_by=None)
    record = AsyncMock(return_value=audit)
    monkeypatch.setattr(risk.RiskManager, 'trigger_emergency_stop', record)
    result = await risk.trigger_emergency_stop(SimpleNamespace(reason='operator stop test'), SimpleNamespace(app=app),
                                              SimpleNamespace(roles=['admin'], username='admin'))
    assert result['control']['operator_halted'] is True and result['control']['drained'] is True
    assert result['control']['cancellation']['status'] == 'complete'
    assert result['control']['cancellation']['confirmed_cancelled'] == 0
    assert engine.governance.is_trading_halted and app.state.organism_governance.is_trading_halted
    assert operator_controls.read_record(control_file)['operator_halted'] is True
    assert not engine._tick_lock.locked() and not operator_controls.operation_lock(app).locked()
    record.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_waits_for_emergency_cancellation_without_blocking_exit_tick(monkeypatch, tmp_path):
    from backend.api.routes import risk
    from backend.organism import operator_controls
    from backend.organism.governance import GovernanceController
    from backend.models.risk import EmergencyStop
    from datetime import datetime, timezone
    control_file = tmp_path / 'authority.json'
    monkeypatch.setenv(operator_controls.STATE_ENV, str(control_file))
    operator_controls.initialize_control_state(control_file, operator_halted=False, reason='isolated fixture')
    engine, db, _ = fixtures([])
    engine.governance = GovernanceController(); engine._tick_lock = asyncio.Lock(); engine._initialized = True
    engine.brain = SimpleNamespace(brain_dir=tmp_path / 'brain')
    app = SimpleNamespace(state=SimpleNamespace(organism_scheduler=SimpleNamespace(_engine=engine, is_running=True)))
    async def sessions(): yield db
    monkeypatch.setattr(risk, 'get_db_session', sessions)
    monkeypatch.setattr(risk, 'get_user_id_from_username', AsyncMock(return_value=1))
    started, release = asyncio.Event(), asyncio.Event()
    async def slow_cancel(*args):
        started.set(); await release.wait()
        return {'status': 'complete', 'confirmed_cancelled': 0, 'scope': 'attributed_organism_entries'}
    monkeypatch.setattr(cancellation, 'cancel_entry_orders', slow_cancel)
    audit = EmergencyStop(id=uuid4(), user_id=1, triggered_by=1, reason='isolated fixture', strategies_stopped=0,
                          orders_cancelled=0, status='active', triggered_at=datetime.now(timezone.utc), resolved_at=None, resolved_by=None)
    monkeypatch.setattr(risk.RiskManager, 'trigger_emergency_stop', AsyncMock(return_value=audit))
    stopping = asyncio.create_task(risk.trigger_emergency_stop(SimpleNamespace(reason='operator stop test'), SimpleNamespace(app=app),
                                                               SimpleNamespace(roles=['admin'], username='admin')))
    await asyncio.wait_for(started.wait(), 1)
    resuming = asyncio.create_task(operator_controls.resume_entries(app))
    await asyncio.sleep(0)
    assert not resuming.done() and engine.governance.is_trading_halted
    await asyncio.wait_for(engine._tick_lock.acquire(), 0.1)
    engine._tick_lock.release()  # Risk exits can still acquire the normal engine tick lock.
    release.set()
    result = await stopping
    assert result['control']['operator_halted'] is True
    await resuming
    assert not engine.governance._operator_halted


@pytest.mark.asyncio
async def test_active_status_uses_actual_durable_engine_without_db_or_legacy_audit(monkeypatch, tmp_path):
    from backend.api.routes import risk
    from backend.organism import operator_controls
    from backend.organism.governance import GovernanceController
    path = tmp_path / 'operator-control.json'
    monkeypatch.setenv(operator_controls.STATE_ENV, str(path))
    operator_controls.initialize_control_state(path, operator_halted=False, reason='isolated status fixture')
    engine = SimpleNamespace(governance=GovernanceController(), _tick_lock=asyncio.Lock(), _initialized=True,
                             brain=SimpleNamespace(brain_dir=tmp_path / 'brain'))
    operator_controls.restore_engine_controls(engine)
    legacy = GovernanceController(); legacy._operator_halted = True
    app = SimpleNamespace(state=SimpleNamespace(organism_scheduler=SimpleNamespace(_engine=engine, is_running=True), organism_governance=legacy))
    request = SimpleNamespace(app=app)
    user = SimpleNamespace(roles=['viewer'], username='reader')
    monkeypatch.setattr(risk, 'get_db_session', MagicMock(side_effect=AssertionError('read must not use DB')))
    monkeypatch.setattr(risk, 'get_user_id_from_username', AsyncMock(side_effect=AssertionError('no user DB lookup')))
    assert await risk.check_emergency_stop_active(request, user) is False
    await operator_controls.halt_entries(app)
    assert await risk.check_emergency_stop_active(request, user) is True
    await operator_controls.resume_entries(app)
    assert await risk.check_emergency_stop_active(request, user) is False
    route = next(item for item in risk.router.routes if item.path == '/risk/emergency-stop/active')
    assert [dependency.call for dependency in route.dependant.dependencies] == [risk.get_authenticated_user]


@pytest.mark.asyncio
@pytest.mark.parametrize('halted,fault,configured,persistence,expected', [
    (False, False, True, 'verified', False),
    (True, False, True, 'verified', True),
    (True, True, True, 'failed', True),
    (False, True, True, 'failed', True),
    (False, False, False, 'unconfigured', None),
    (False, False, True, 'failed', None),
    (False, False, 'true', 'verified', None),
    (False, None, True, 'verified', None),
    ('false', False, True, 'verified', None),
])
async def test_active_status_never_infers_false_from_unknown_control(monkeypatch, halted, fault, configured, persistence, expected):
    from backend.api.routes import risk
    from backend.organism import operator_controls
    app = SimpleNamespace(state=SimpleNamespace(organism_scheduler=SimpleNamespace(_engine=SimpleNamespace(governance=object()))))
    control = {'available': True, 'operator_halted': halted, 'entries_halted': True,
               'governance': {'operator_control_fault': fault},
               'persistence': {'configured': configured, 'persistence': persistence}}
    monkeypatch.setattr(operator_controls, 'control_status', lambda app: control)
    if expected is None:
        with pytest.raises(HTTPException) as error:
            await risk.check_emergency_stop_active(SimpleNamespace(app=app), SimpleNamespace())
        assert error.value.status_code == 503 and error.value.detail['error'] == 'operator_control_unverified'
    else:
        # entries_halted can be automatic risk state; it does not masquerade as a manual halt.
        assert await risk.check_emergency_stop_active(SimpleNamespace(app=app), SimpleNamespace()) is expected


@pytest.mark.asyncio
async def test_active_status_refuses_legacy_only_governance_and_sanitizes_errors(monkeypatch):
    from backend.api.routes import risk
    from backend.organism import operator_controls
    app = SimpleNamespace(state=SimpleNamespace(organism_governance=SimpleNamespace(_operator_halted=False)))
    with pytest.raises(HTTPException) as error:
        await risk.check_emergency_stop_active(SimpleNamespace(app=app), SimpleNamespace())
    assert error.value.status_code == 503
    app.state.organism_scheduler = SimpleNamespace(_engine=SimpleNamespace(governance=object()))
    monkeypatch.setattr(operator_controls, 'control_status', MagicMock(side_effect=RuntimeError('private credential')))
    with pytest.raises(HTTPException) as error:
        await risk.check_emergency_stop_active(SimpleNamespace(app=app), SimpleNamespace())
    assert error.value.status_code == 503 and 'private credential' not in str(error.value.detail)


def open_response(rows):
    return SimpleNamespace(status_code=200, json=lambda: rows)


@pytest.mark.asyncio
@pytest.mark.parametrize('db_status', ['canceled', 'cancelled', 'filled', 'expired', 'rejected'])
async def test_historical_db_terminal_entry_is_found_by_real_query_and_broker_inventory(db_status):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from backend.infra.schemas import Order
    store = create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with store.begin() as connection:
            await connection.run_sync(Order.__table__.create)
        async with async_sessionmaker(store, expire_on_commit=False)() as db:
            row = Order(id=uuid4(), broker_order_id=str(uuid4()), symbol='AAPL', side='buy', qty=Decimal('10'),
                        filled_qty=Decimal('0'), status=db_status, client_idempotency_key='organism_AAPL_historical',
                        order_type='market', tif='day', attributes={'source': 'organism', 'reason': 'organism_entry'})
            db.add(row); await db.commit()
            engine, _, broker = fixtures([])
            broker._make_request_with_retry.side_effect = [open_response([broker_row(row)]), open_response([])]
            broker.get_order.side_effect = [broker_row(row), broker_row(row, 'canceled')]
            result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker)
            assert result['status'] == 'complete' and result['confirmed_cancelled'] == 1
            broker.cancel_order.assert_awaited_once_with(row.broker_order_id)
            await db.refresh(row)
            assert row.status == db_status and row.filled_qty == 0
            assert engine._pending_entry_order_ids == {}
    finally:
        await store.dispose()


@pytest.mark.asyncio
async def test_empty_db_broker_failure_or_unknown_open_order_cannot_report_complete():
    for observation in [TimeoutError('private broker secret'), open_response([broker_row(entry())])]:
        engine, db, broker = fixtures([])
        broker._make_request_with_retry.side_effect = [observation, open_response([])]
        result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker)
        assert result['status'] == 'incomplete' and result['confirmed_cancelled'] == 0
        assert 'private broker secret' not in str(result)
        broker.cancel_order.assert_not_awaited(); broker.get_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_broker_inventory_preserves_exact_protective_and_foreign_orders():
    protected = entry(); protected.client_idempotency_key = 'organism_exit_AAPL_protect'
    protected.attributes = {'source': 'organism', 'reason': 'stop_loss'}
    foreign = entry(); foreign.client_idempotency_key = 'manual-operator'; foreign.attributes = {'source': 'manual'}
    engine, db, broker = fixtures([protected, foreign])
    observed = [broker_row(protected, legs=[{'id': str(uuid4())}]), broker_row(foreign)]
    broker._make_request_with_retry.side_effect = [open_response(observed), open_response(observed)]
    result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker)
    assert result['status'] == 'complete' and result['preserved_orders'] == 2
    broker.cancel_order.assert_not_awaited(); broker.get_order.assert_not_awaited()
    assert protected.status == foreign.status == 'new'
    args, kwargs = broker._make_request_with_retry.await_args
    assert args == ('GET', 'https://paper-api.alpaca.markets/v2/orders')
    assert kwargs['params'] == {'status': 'open', 'limit': 257, 'nested': 'true'}


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['full_page', 'duplicate', 'invalid_id', 'not_list'])
async def test_broker_inventory_invalid_or_full_page_blocks_before_db_or_cancel(case, monkeypatch):
    engine, db, broker = fixtures([]); row = broker_row(entry())
    monkeypatch.setattr(cancellation, 'INVENTORY_LIMIT', 1)
    rows = {'full_page': [row, broker_row(entry())], 'duplicate': [row, row],
            'invalid_id': [{**row, 'id': '../orders'}], 'not_list': {'orders': []}}[case]
    broker._make_request_with_retry.return_value = open_response(rows)
    result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker)
    assert result['status'] == 'incomplete'
    db.execute.assert_not_awaited(); broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_broker_entry_during_cancellation_withholds_completion():
    engine, db, broker = fixtures([])
    broker._make_request_with_retry.side_effect = [open_response([]), open_response([broker_row(entry())])]
    result = await cancellation.cancel_entry_orders(engine, db, HALT, broker=broker)
    assert result['status'] == 'incomplete' and result['issues'] == ['broker_open_inventory_changed']
    broker.cancel_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_newer_halt_persistence_failure_during_cancellation_cannot_acknowledge_success(monkeypatch, tmp_path):
    from backend.api.routes import risk
    from backend.organism import operator_controls
    from backend.organism.governance import GovernanceController
    from backend.models.risk import EmergencyStop
    from datetime import datetime, timezone
    path = tmp_path / 'control.json'; monkeypatch.setenv(operator_controls.STATE_ENV, str(path))
    operator_controls.initialize_control_state(path, operator_halted=False, reason='fixture')
    engine, db, _ = fixtures([])
    engine.governance = GovernanceController(); engine._tick_lock = asyncio.Lock(); engine._initialized = True
    engine.brain = SimpleNamespace(brain_dir=tmp_path / 'brain')
    app = SimpleNamespace(state=SimpleNamespace(organism_scheduler=SimpleNamespace(_engine=engine, is_running=True)))
    async def sessions(): yield db
    monkeypatch.setattr(risk, 'get_db_session', sessions)
    monkeypatch.setattr(risk, 'get_user_id_from_username', AsyncMock(return_value=1))
    async def superseding_halt(*args):
        monkeypatch.setattr(operator_controls, 'write_record', MagicMock(side_effect=OSError('private path')))
        with pytest.raises(operator_controls.OperatorControlError):
            await operator_controls.halt_entries(app)
        return {'status': 'complete', 'confirmed_cancelled': 0, 'scope': 'attributed_organism_entries'}
    monkeypatch.setattr(cancellation, 'cancel_entry_orders', superseding_halt)
    audit = EmergencyStop(id=uuid4(), user_id=1, triggered_by=1, reason='fixture', strategies_stopped=0,
                          orders_cancelled=0, status='active', triggered_at=datetime.now(timezone.utc), resolved_at=None, resolved_by=None)
    monkeypatch.setattr(risk.RiskManager, 'trigger_emergency_stop', AsyncMock(return_value=audit))
    with pytest.raises(HTTPException) as error:
        await risk.trigger_emergency_stop(SimpleNamespace(reason='operator stop'), SimpleNamespace(app=app),
                                          SimpleNamespace(roles=['admin'], username='admin'))
    assert error.value.status_code == 503 and error.value.detail['audit_id'] == str(audit.id)
    assert error.value.detail['issues'] == ['operator_halt_changed_or_unverified']
    assert error.value.detail['control']['persistence']['persistence'] == 'failed'
    assert error.value.detail['control']['governance']['operator_control_fault'] is True
    assert engine.governance.is_trading_halted and not engine._tick_lock.locked()
