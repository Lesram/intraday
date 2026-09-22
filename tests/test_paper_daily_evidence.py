"""Actual collector shapes with isolated files and deterministic GET responses."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import csv
import io
import json
import pytest
from scripts.ops import paper_daily_evidence as daily

DAY = '2026-09-21'
NOW = datetime(2026, 9, 21, 20, 10, tzinfo=timezone.utc)
CUTOFF = '2026-09-19T21:55:01.857005+00:00'
FIELDS = ['symbol', 'closed_at', 'shares', 'entry_price', 'exit_price', 'pnl',
          'had_partial_exits', 'entry_source', 'regime_at_entry', 'price_source', 'entry_order_id']


def csv_bytes(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def order(identifier, side, qty, price, at, status='filled'):
    return {'id': identifier, 'client_order_id': 'organism_' + identifier, 'symbol': 'XYZ',
            'side': side, 'filled_qty': str(qty), 'filled_avg_price': str(price),
            'submitted_at': at, 'filled_at': at if qty else None, 'status': status}


def checkpoint(rows, completed=None, pending=None):
    state = {'all_trades': rows, 'completed': completed or {},
             'tracking': {'_entry_metadata': pending or {}}}
    return {'version': 1, 'policy': 'exact_position_fills_or_pending_v1',
            'state': state, 'sha256': daily.digest(json.dumps(state, sort_keys=True, separators=(',', ':')).encode())}


class FakeTransport:
    def __init__(self, orders=None, calendar=None):
        self.orders = orders or []
        self.calls = []
        self.calendar = [{'date': DAY, 'open': '09:30', 'close': '16:00'}] if calendar is None else calendar
        self.responses = {
            '/v2/calendar': self.calendar, '/v2/positions': [],
            '/v2/clock': {'is_open': False, 'timestamp': NOW.isoformat()},
            '/v2/account': {'status': 'ACTIVE', 'trading_blocked': False, 'account_blocked': False},
            '/api/v1/paper-monitor/deploy': {'source_sha': 'source', 'image_sha': 'source', 'runtime_config_hash': 'config'},
            '/api/v1/paper-monitor/organism/status': {'live_engine': {'running': True, 'engine': {
                'close_accounting': {'policy': 'exact_position_fills_or_pending_v1', 'error': None, 'pending': {}}}}},
        }

    def get(self, origin, path, params):
        self.calls.append((origin, path, params))
        if path == '/v2/orders':
            result = sorted(self.orders, key=lambda row: row['submitted_at'], reverse=True)
            if 'after' in params:
                result = [row for row in result if daily.timestamp(row['submitted_at']) > daily.timestamp(params['after'])]
            elif 'before_order_id' in params:
                index = next(i for i, row in enumerate(result) if row['id'] == params['before_order_id'])
                result = result[index + 1:]
            else:
                result = [row for row in result if row['submitted_at'] < params['until']]
            return daily.encoded(result[:params['limit']])
        return daily.encoded(self.responses[path])

    def container_identity(self):
        return daily.encoded({'name': '/intra-api-1', 'image_digest': 'sha256:image', 'project': 'intra', 'service': 'api'})


@pytest.fixture
def host(tmp_path):
    brain = tmp_path / 'organism_brain'
    brain.mkdir()
    logs = tmp_path / 'logs'
    logs.mkdir()
    (logs / 'sessions').mkdir()
    freeze = tmp_path / 'freeze.json'
    freeze.write_bytes(daily.encoded({'FROZEN_AT': CUTOFF, 'surface': {'routing_data_env': {'ALPACA_DATA_FEED': 'iex'}}}))
    activation = tmp_path / 'activation.json'
    activation.write_bytes(daily.encoded({
        'active_freeze_sha256': daily.digest(freeze.read_bytes()), 'activation_timestamp_utc': CUTOFF,
        'broker_before_transition': {'paper_endpoint_verified': True, 'positions': 0, 'open_orders': 0},
    }))
    release = tmp_path / 'release.json'
    release.write_bytes(daily.encoded({'source_sha': 'source', 'image_sha': 'source', 'image_digest': 'sha256:image', 'runtime_config_hash': 'config', 'timeframe': '1Min'}))
    (brain / 'trade_history.csv').write_bytes(csv_bytes([]))
    (brain / 'strategy_evidence_events.jsonl').write_bytes(b'')
    (brain / 'close_accounting.json').write_bytes(daily.encoded(checkpoint([])))
    opened = NOW.replace(hour=13, minute=30)
    lines = [daily.encoded({'schema': daily.SESSION_LOG_SCHEMA, 'logger': 'backend.organism.live_engine',
                           'timestamp': (opened + timedelta(seconds=n)).isoformat().replace('+00:00', 'Z'),
                           'message': 'Organism tick: regime=trending_up signals=0 orders=0 exits=0 0.1s'}).decode().replace('\n', '') + '\n'
             for n in range(0, 23401, 120)]
    (logs / 'sessions' / (DAY + '.jsonl')).write_text(''.join(lines))
    # Old malformed rotations stay intact, outside the versioned daily stream.
    (logs / 'application.log.9').write_text('{"message": "{"event": "legacy"}"}\n')
    (logs / 'application.log').write_text('legacy unzoned record\n')
    return tmp_path, freeze, activation, release


def run_host(host, transport=None):
    root, freeze, activation, release = host
    return daily.collect(root, freeze, activation, release, None, DAY, transport or FakeTransport(), now=NOW)


def test_complete_actual_collector_no_trade_is_not_missing_evidence(host):
    inputs, collection, _ = run_host(host)
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'READY_FOR_REVIEW', report['issues']
    assert report['trade_observation'] == 'NO_FORWARD_TRADES'
    assert report['strategy_gate']['momentum']['state'] == 'INSUFFICIENT'
    assert report['standdown']['counts']['successful_ticks'] == 196
    assert 'logs/sessions/' + DAY + '.jsonl' in inputs
    assert 'logs/application.log.9' not in inputs
    assert report['promotion_authorized'] is False


def test_independent_partial_cashflows_costs_and_positive_gate_withheld(host):
    root, *_ = host
    orders = [order('buy', 'buy', 6, 100, '2026-09-21T14:00:00Z'),
              order('partial', 'sell', 2, 101, '2026-09-21T15:00:00Z', 'canceled'),
              order('final', 'sell', 4, 99, '2026-09-21T16:00:00Z')]
    rows = [{'symbol': 'XYZ', 'closed_at': '2026-09-21T16:00:20Z', 'shares': 6,
             'entry_price': 100, 'exit_price': 99.6667, 'pnl': -2, 'had_partial_exits': True,
             'entry_source': 'alpha', 'regime_at_entry': 'trending_up',
             'price_source': 'db_position_fills', 'entry_order_id': 'buy'}]
    (root / 'organism_brain/trade_history.csv').write_bytes(csv_bytes(rows))
    (root / 'organism_brain/close_accounting.json').write_bytes(daily.encoded(checkpoint(rows, {'buy': rows[0]['closed_at']})))
    inputs, collection, _ = run_host(host, FakeTransport(orders))
    def never_run(*args):
        pytest.fail('invalid evidence must not expose a positive gate')
    report = daily.analyze(inputs, collection, gate_fn=never_run)
    assert report['status'] == 'BLOCKED'
    assert report['strategy_gate']['state'] == 'WITHHELD'
    assert report['reconciliation']['gross']['broker_pnl'] == -2
    assert report['reconciliation']['cost_scenarios']['6_bps_round_trip']['broker_modeled_net'] == -2.36
    assert report['reconciliation']['counts']['organism_filled_orders'] == 3


@pytest.mark.parametrize('kind', ['missing_logs', 'pending', 'bad_checksum', 'runtime_mismatch', 'trace_tamper', 'unscoped_row'])
def test_quality_failures_never_expose_pass(host, kind):
    inputs, collection, _ = run_host(host)
    if kind == 'missing_logs':
        del inputs['logs/sessions/' + DAY + '.jsonl']
    elif kind == 'pending':
        inputs['local/close_accounting.json'] = daily.encoded(checkpoint([], pending={'XYZ': {'pending_close': {'observed_at': NOW.isoformat()}}}))
    elif kind == 'bad_checksum':
        inputs['local/close_accounting.json'] = daily.encoded({'version': 1, 'policy': 'exact_position_fills_or_pending_v1', 'sha256': 'bad', 'state': {}})
    elif kind == 'runtime_mismatch':
        inputs['runtime/deploy.json'] = daily.encoded({'source_sha': 'wrong', 'image_sha': 'source', 'runtime_config_hash': 'config'})
    elif kind == 'trace_tamper':
        collection['order_inventory']['termination'] = 'complete=true'
    else:
        inputs['local/trades.csv'] = csv_bytes([dict.fromkeys(FIELDS, '')])
    report = daily.analyze(inputs, collection, gate_fn=lambda *args: pytest.fail('gate ran'))
    assert report['status'] == 'BLOCKED'
    assert report['strategy_gate']['state'] == 'WITHHELD'


def test_cursor_pagination_retains_identical_submission_timestamps_and_terminal_orders():
    orders = [order(str(i), 'buy', 0, 0, '2026-09-21T14:00:00Z', 'rejected') for i in range(5)]
    transport = FakeTransport(orders)
    recorder = daily.Recorder(transport, {})
    actual, inventory = daily.collect_orders(recorder, CUTOFF, NOW.isoformat(), page_size=2)
    assert len(actual) == 5 and inventory['pages'] == 3
    assert transport.calls[0][2]['until'] == NOW.isoformat()
    assert transport.calls[1][2]['before_order_id'] == '1'
    assert 'until' not in transport.calls[1][2]


def test_ignored_cursor_duplicate_page_and_page_cap_fail_closed():
    rows = [order(str(i), 'buy', 0, 0, '2026-09-21T14:00:00Z', 'rejected') for i in range(4)]
    class IgnoresCursor(FakeTransport):
        def get(self, origin, path, params):
            return daily.encoded(rows[:2])
    with pytest.raises(daily.EvidenceError, match='duplicate_order_or_cursor'):
        daily.collect_orders(daily.Recorder(IgnoresCursor(), {}), CUTOFF, NOW.isoformat(), page_size=2)
    with pytest.raises(daily.EvidenceError, match='order_page_limit'):
        daily.collect_orders(daily.Recorder(FakeTransport(rows), {}), CUTOFF, NOW.isoformat(), page_size=2, max_pages=1)


def test_host_mutation_during_snapshot_blocks_without_relabeling_bytes(host, monkeypatch):
    root, *_ = host
    real = daily.stable_read
    def read(path):
        raw = real(path)
        if path.name == 'strategy_evidence_events.jsonl':
            (root / 'organism_brain/trade_history.csv').write_bytes(csv_bytes([]) + b'\n')
        return raw
    monkeypatch.setattr(daily, 'stable_read', read)
    inputs, collection, _ = run_host(host)
    assert 'input_set_changed_during_capture' in collection['issues']
    assert inputs['local/trades.csv'] == csv_bytes([])
    assert daily.analyze(inputs, collection)['status'] == 'BLOCKED'


def test_immutable_idempotent_concurrent_publication_and_replay(host, tmp_path):
    inputs, collection, paths = run_host(host)
    report = daily.analyze(inputs, collection)
    output = tmp_path / 'packs'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: daily.publish(output, inputs, collection, report, paths), range(2)))
    assert results[0] == results[1]
    restored, restored_collection = daily.verify_pack(results[0])
    assert restored == inputs and restored_collection == collection
    assert daily.analyze(restored, restored_collection) == report
    changed = dict(inputs, extra=b'new')
    another = daily.publish(output, changed, collection, report, paths)
    assert another != results[0] and results[0].exists()
    assert not list(output.rglob('.incomplete-*'))


def test_interrupted_publish_never_creates_final_manifest_pack(host, tmp_path, monkeypatch):
    inputs, collection, paths = run_host(host)
    report = daily.analyze(inputs, collection)
    real = daily.os.rename
    def fail(source, target, *args, **kwargs):
        if str(source).startswith('.incomplete-'):
            raise OSError('injected interruption')
        return real(source, target, *args, **kwargs)
    monkeypatch.setattr(daily.os, 'rename', fail)
    output = tmp_path / 'packs'
    with pytest.raises(OSError):
        daily.publish(output, inputs, collection, report, paths)
    assert not list(output.rglob('manifest.json'))


def test_canonical_brain_output_alias_and_hardlinks_rejected(tmp_path):
    actual = tmp_path / 'state'
    actual.mkdir()
    alias = tmp_path / 'organism_brain'
    alias.symlink_to(actual, target_is_directory=True)
    source = alias / 'trade_history.csv'
    source.write_bytes(b'x')
    with pytest.raises(daily.EvidenceError):
        daily.safe_output(actual / 'evidence', [source])
    with pytest.raises(daily.EvidenceError):
        daily.safe_output(actual / 'evidence', [], [alias])
    link = tmp_path / 'hardlink'
    link.hardlink_to(source)
    with pytest.raises(daily.EvidenceError):
        daily.safe_output(link, [source])


def test_holiday_no_session_and_future_block_no_false_empty_pass(host):
    inputs, collection, _ = run_host(host, FakeTransport(calendar=[]))
    assert daily.analyze(inputs, collection)['status'] == 'NO_SESSION'
    root, freeze, activation, release = host
    inputs, collection, _ = daily.collect(root, freeze, activation, release, None,
                                          '2026-09-22', FakeTransport(calendar=[]), now=NOW)
    assert daily.analyze(inputs, collection)['status'] == 'BLOCKED'


def test_transport_rejects_mutating_or_arbitrary_paths_without_network():
    transport = daily.GetTransport('test-key', 'test-secret', 'test-token')
    for origin, path in [('live', '/v2/orders'), ('paper', '/v2/orders/id'), ('local', '/api/v1/organism/start')]:
        with pytest.raises(daily.EvidenceError, match='non_allowlisted_endpoint'):
            transport.get(origin, path, {})


def exact_trade_inputs(host):
    root, *_ = host
    row = {'symbol': 'XYZ', 'closed_at': '2026-09-21T16:00:20Z', 'shares': 6,
           'entry_price': 100, 'exit_price': 99.6667, 'pnl': -2, 'had_partial_exits': True,
           'entry_source': 'alpha', 'regime_at_entry': 'trending_up',
           'price_source': 'db_position_fills', 'entry_order_id': 'database-entry-id'}
    orders = [order('broker-buy', 'buy', 6, 100, '2026-09-21T14:00:01Z'),
              order('partial', 'sell', 2, 101, '2026-09-21T15:00:00Z'),
              order('final', 'sell', 4, 99, '2026-09-21T16:00:00Z')]
    receipt = {'schema': 'intra_entry_evidence_v1', 'entry_order_id': 'database-entry-id',
               'client_order_id': 'organism_broker-buy', 'broker_order_id': '',
               'symbol': 'XYZ', 'direction': 1.0, 'shares': 6, 'entry_source': 'alpha',
               'strategy_id': 'alpha_baseline', 'tick': 100,
               'captured_at': '2026-09-21T14:00:00Z', 'submitted_at': '2026-09-21T14:00:00Z',
               'recorded_at': '2026-09-21T14:00:02Z', 'git_sha': 'source', 'image_sha': 'source',
               'runtime_config_hash': 'config', 'feed': 'iex', 'timeframe': '1Min',
               'last_bar_at': '2026-09-21T13:59:00Z', 'bar_age_seconds': 60,
               'frame_hash': 'a' * 64, 'frame_rows': 100, 'timestamp_complete': True,
               'timestamp_ordered': True, 'gate_passed': True, 'status': 'OBSERVED',
               'reasons': [], 'method': 'pandas_hash_v1'}
    brain = root / 'organism_brain'
    (brain / 'trade_history.csv').write_bytes(csv_bytes([row]))
    (brain / 'close_accounting.json').write_bytes(daily.encoded(checkpoint([row], {'database-entry-id': row['closed_at']})))
    # JSONL receipt format is one compact JSON object per line.
    (brain / 'entry_evidence.jsonl').write_text(json.dumps(receipt) + '\n')
    return row, receipt, orders


def test_complete_order_to_checkpoint_to_entry_receipt_chain_uses_actual_shapes(host):
    row, receipt, orders = exact_trade_inputs(host)
    before = {path: path.read_bytes() for path in (host[0] / 'organism_brain').iterdir()}
    inputs, collection, _ = run_host(host, FakeTransport(orders))
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'READY_FOR_REVIEW', report['issues']
    assert report['decision_provenance']['verified_entries'] == 1
    assert report['strategy_gate']['momentum']['n'] == 1
    assert report['reconciliation']['cost_scenarios']['6_bps_round_trip']['broker_modeled_net'] == -2.36
    assert {path: path.read_bytes() for path in before} == before


@pytest.mark.parametrize('fault', ['stale', 'future', 'different_config', 'missing_client', 'duplicate_conflict', 'wrong_cycle', 'approximate', 'torn_csv'])
def test_receipt_and_accounting_adversarial_cases_withhold_gate(host, fault):
    row, receipt, orders = exact_trade_inputs(host)
    brain = host[0] / 'organism_brain'
    if fault == 'stale':
        receipt['last_bar_at'], receipt['bar_age_seconds'] = '2026-09-21T13:50:00Z', 600
    elif fault == 'future':
        receipt['last_bar_at'], receipt['bar_age_seconds'] = '2026-09-21T14:01:00Z', -60
    elif fault == 'different_config':
        receipt['runtime_config_hash'] = 'other'
    elif fault == 'missing_client':
        receipt['client_order_id'] = ''
    elif fault == 'wrong_cycle':
        receipt['client_order_id'] = 'organism_final'
    elif fault == 'approximate':
        row['price_source'] = 'db_fill'
        (brain / 'trade_history.csv').write_bytes(csv_bytes([row]))
    elif fault == 'torn_csv':
        (brain / 'trade_history.csv').write_bytes(csv_bytes([]))
    raw = json.dumps(receipt) + '\n'
    if fault == 'duplicate_conflict':
        raw += json.dumps({**receipt, 'frame_hash': 'b' * 64}) + '\n'
    (brain / 'entry_evidence.jsonl').write_text(raw)
    inputs, collection, _ = run_host(host, FakeTransport(orders))
    report = daily.analyze(inputs, collection, gate_fn=lambda *_: pytest.fail('positive gate must be withheld'))
    assert report['status'] == 'BLOCKED'
    assert report['strategy_gate']['state'] == 'WITHHELD'


def test_approved_baseline_exempts_only_exact_pinned_legacy_prefix(host):
    root, freeze, activation, release = host
    legacy = dict.fromkeys(FIELDS, '')
    legacy.update(symbol='OLD', entry_source='alpha')
    raw = csv_bytes([legacy])
    baseline = root / 'baseline'
    baseline.mkdir()
    (baseline / 'trade_history.csv').write_bytes(raw)
    receipt = daily.encoded({'files': {'trade_history.csv': {'sha256': daily.digest(raw), 'bytes': len(raw)}}})
    (baseline / 'backup_manifest.json').write_bytes(receipt)
    approved = json.loads(activation.read_bytes())
    approved['backups'] = {'brain': {'manifest_sha256': daily.digest(receipt)}}
    activation.write_bytes(daily.encoded(approved))
    (root / 'organism_brain/trade_history.csv').write_bytes(raw)
    (root / 'organism_brain/close_accounting.json').write_bytes(daily.encoded(checkpoint([legacy])))
    inputs, collection, _ = daily.collect(root, freeze, activation, release, baseline, DAY, FakeTransport(), now=NOW)
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'READY_FOR_REVIEW', report['issues']
    assert report['approved_historical_rows'] == 1
    inputs['baseline/trades.csv'] += b'\n'
    assert daily.analyze(inputs, collection)['status'] == 'BLOCKED'


def test_native_reporting_uses_six_bps_without_mutating_runtime_default(tmp_path):
    import os
    from backend.organism.costing import DEFAULT_COST_BPS
    from backend.organism.phase2_gate import load_forward_corpus
    row = {'symbol': 'XYZ', 'closed_at': '2026-09-21T16:00:20Z', 'shares': 6,
           'entry_price': 100, 'exit_price': 99.6667, 'pnl': -2, 'had_partial_exits': True,
           'entry_source': 'alpha', 'regime_at_entry': 'trending_up',
           'price_source': 'db_position_fills', 'entry_order_id': 'database-entry-id'}
    raw = csv_bytes([row])
    path = tmp_path / 'trades.csv'
    path.write_bytes(raw)
    before = dict(os.environ)
    assert load_forward_corpus(str(path), CUTOFF, cost_bps=6)['net_pnl'].tolist() == [-2.36]
    assert daily.native_gates(raw, CUTOFF)['momentum']['n'] == 1
    assert DEFAULT_COST_BPS == 3.0 and dict(os.environ) == before


def test_missing_fixed_endpoint_acquisition_receipt_blocks_retained_payload(host):
    inputs, collection, _ = run_host(host)
    collection['requests'] = [r for r in collection['requests'] if r['input'] != 'runtime/deploy.json']
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'BLOCKED'
    assert 'required_acquisition_trace_missing' in report['issues']


def test_valid_anchor_does_not_certify_unobserved_pyramid_add(host):
    row, receipt, orders = exact_trade_inputs(host)
    # Same total six-share entry cashflow, but two independent entry decisions.
    orders[0]['filled_qty'] = '3'
    orders.append(order('pyramid', 'buy', 3, 100, '2026-09-21T14:30:01Z'))
    inputs, collection, _ = run_host(host, FakeTransport(orders))
    report = daily.analyze(inputs, collection)
    assert report['reconciliation']['status'] == 'RECONCILED'
    assert report['status'] == 'BLOCKED'
    assert 'entry_decision_provenance_unverified:0' in report['issues']
    assert report['strategy_gate']['state'] == 'WITHHELD'


def test_symlink_date_directory_cannot_redirect_pack_into_brain(host):
    inputs, collection, paths = run_host(host)
    report = daily.analyze(inputs, collection)
    output = host[0] / 'packs'
    output.mkdir()
    (output / DAY).symlink_to(host[0] / 'organism_brain', target_is_directory=True)
    with pytest.raises(daily.EvidenceError, match='symlink_pack_destination'):
        daily.publish(output, inputs, collection, report, paths)


def test_transport_failure_emits_blocked_pack_with_partial_inputs(host):
    class FailingTransport(FakeTransport):
        def get(self, origin, path, params):
            if path == '/v2/account':
                raise daily.EvidenceError('transport_failure')
            return super().get(origin, path, params)
    inputs, collection, paths = run_host(host, FailingTransport())
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'BLOCKED' and 'transport_failure' in report['issues']
    pack = daily.publish(host[0] / 'packs', inputs, collection, report, paths)
    daily.verify_pack(pack)


@pytest.mark.parametrize('fault', [None, 'stale', 'reused_db_id', 'wrong_identity', 'oversized_fill'])
def test_every_pyramid_buy_requires_its_own_qualified_receipt(host, fault):
    row, initial, orders = exact_trade_inputs(host)
    orders[0]['filled_qty'] = '3'
    initial['shares'] = 3
    orders.append(order('pyramid', 'buy', 3, 100, '2026-09-21T14:30:01Z'))
    addition = {**initial, 'entry_order_id': 'database-pyramid-id', 'client_order_id': 'organism_pyramid',
                'captured_at': '2026-09-21T14:30:00Z', 'submitted_at': '2026-09-21T14:30:00Z',
                'recorded_at': '2026-09-21T14:30:02Z', 'last_bar_at': '2026-09-21T14:29:00Z', 'tick': 200}
    if fault == 'stale':
        addition['last_bar_at'], addition['bar_age_seconds'] = '2026-09-21T14:20:00Z', 600
    elif fault == 'reused_db_id':
        addition['entry_order_id'] = initial['entry_order_id']
    elif fault == 'wrong_identity':
        addition['runtime_config_hash'] = 'unapproved'
    elif fault == 'oversized_fill':
        addition['shares'] = 2
    (host[0] / 'organism_brain/entry_evidence.jsonl').write_text(json.dumps(initial) + '\n' + json.dumps(addition) + '\n')
    inputs, collection, _ = run_host(host, FakeTransport(orders))
    report = daily.analyze(inputs, collection)
    if fault is None:
        assert report['status'] == 'READY_FOR_REVIEW', report['issues']
        assert report['decision_provenance']['verified_buy_decisions'] == 2
        assert report['reconciliation']['cost_scenarios']['6_bps_round_trip']['broker_modeled_net'] == -2.36
    else:
        assert report['status'] == 'BLOCKED'
        assert report['strategy_gate']['state'] == 'WITHHELD'


def test_exact_capture_timestamp_order_is_detected_by_overlapping_probe(host):
    concurrent = order('boundary', 'buy', 0, 0, NOW.isoformat(), 'rejected')
    inputs, collection, _ = run_host(host, FakeTransport([concurrent]))
    assert json.loads(inputs['derived/orders.json']) == []
    assert json.loads(inputs['broker/final-order-probe.json'])[0]['id'] == 'boundary'
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'BLOCKED'
    assert 'orders_changed_during_collection' in report['issues']


@pytest.mark.asyncio
async def test_real_entry_observers_publish_receipt_accepted_by_daily_collector(host, monkeypatch):
    """Exercise producer→disk→collector→consumer; never fabricate the receipt."""
    from types import SimpleNamespace
    import pandas as pd
    from backend.organism import entry_evidence

    root, *_ = host
    brain = root / 'organism_brain'
    identity = {'git_sha': 'source', 'image_sha': 'source', 'runtime_config_hash': 'config'}
    monkeypatch.setattr(entry_evidence, 'runtime_identity_snapshot', lambda: dict(identity))
    monkeypatch.setenv('ALPACA_DATA_FEED', 'iex')
    row = {'symbol': 'XYZ', 'closed_at': '2026-09-21T16:00:20Z', 'shares': 6,
           'entry_price': 100, 'exit_price': 99.6667, 'pnl': -2, 'had_partial_exits': True,
           'entry_source': 'alpha', 'regime_at_entry': 'trending_up',
           'price_source': 'db_position_fills', 'entry_order_id': 'database-entry-id'}
    (brain / 'trade_history.csv').write_bytes(csv_bytes([row]))
    (brain / 'close_accounting.json').write_bytes(daily.encoded(checkpoint([row], {'database-entry-id': row['closed_at']})))
    orders = [order('broker-buy', 'buy', 6, 100, '2026-09-21T14:00:01Z'),
              order('partial', 'sell', 2, 101, '2026-09-21T15:00:00Z'),
              order('final', 'sell', 4, 99, '2026-09-21T16:00:00Z')]

    class ObservedEngine:
        def __init__(self):
            self.brain = SimpleNamespace(brain_dir=brain)
            self._tick_count = 100
            self._timeframe = '1Min'
            self.clock = datetime(2026, 9, 21, 14, 0, tzinfo=timezone.utc)
            self.submissions = 0

        def _now_fn(self):
            return self.clock

        @entry_evidence.observe_gate
        def passes_gate(self, symbol, direction, features_by_symbol):
            return True, 'accepted'

        @entry_evidence.observe_submission
        async def submit(self, symbol, shares, direction=1.0,
                         entry_source='alpha', strategy_id='alpha_baseline'):
            self.submissions += 1
            self.clock += timedelta(seconds=2)
            # Real OrderService shape: database order identity is distinct from
            # the broker ID; the actual idempotency key joins client_order_id.
            return {'order_id': 'database-entry-id', 'symbol': symbol, 'side': 'buy',
                    'qty': shares, 'status': 'submitted', 'idempotency_key': 'organism_broker-buy'}

    engine = ObservedEngine()
    frame = pd.DataFrame({'close': [100.0] * 100, 'volume': [1000] * 100},
                         index=pd.date_range(end='2026-09-21T13:59:00Z', periods=100, freq='min'))
    assert engine.passes_gate('XYZ', 1.0, {'XYZ': frame}) == (True, 'accepted')
    response = await engine.submit('XYZ', 6)
    assert response['order_id'] == 'database-entry-id' and engine.submissions == 1
    receipt_file = brain / 'entry_evidence.jsonl'
    before = receipt_file.read_bytes()
    emitted = json.loads(before)
    assert emitted['entry_order_id'] == 'database-entry-id'
    assert emitted['client_order_id'] == 'organism_broker-buy'
    assert emitted['status'] == 'OBSERVED' and emitted['bar_age_seconds'] == 60
    inputs, collection, _ = run_host(host, FakeTransport(orders))
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'READY_FOR_REVIEW', report['issues']
    assert report['decision_provenance']['verified_buy_decisions'] == 1
    assert report['strategy_gate']['momentum']['state'] == 'INSUFFICIENT'
    assert report['reconciliation']['cost_scenarios']['6_bps_round_trip']['broker_modeled_net'] == -2.36
    assert inputs['local/entry_evidence.jsonl'] == before == receipt_file.read_bytes()


@pytest.mark.parametrize('alias_kind', ['hardlink', 'symlink_parent', 'symlink_leaf'])
def test_stable_read_refuses_linked_input_paths(tmp_path, alias_kind):
    original = tmp_path / 'original'
    original.mkdir()
    source = original / 'ledger.csv'
    source.write_bytes(b'private fixture bytes\n')
    if alias_kind == 'hardlink':
        alias = tmp_path / 'linked-ledger.csv'
        alias.hardlink_to(source)
    elif alias_kind == 'symlink_parent':
        directory_alias = tmp_path / 'directory-alias'
        directory_alias.symlink_to(original, target_is_directory=True)
        alias = directory_alias / 'ledger.csv'
    else:
        alias = tmp_path / 'linked-ledger.csv'
        alias.symlink_to(source)
    with pytest.raises(daily.EvidenceError):
        daily.stable_read(alias)
    assert source.read_bytes() == b'private fixture bytes\n'


@pytest.mark.parametrize('field,value', [
    ('direction', float('nan')), ('direction', float('inf')), ('direction', True),
    ('frame_rows', float('nan')), ('frame_rows', float('inf')), ('frame_rows', True),
    ('frame_rows', 1.5), ('bar_age_seconds', float('nan')), ('bar_age_seconds', '60'),
    ('shares', '6'), ('shares', 6.5), ('tick', True), ('tick', float('nan')),
])
def test_hostile_receipt_numeric_fields_block_positive_gate(host, field, value):
    row, receipt, orders = exact_trade_inputs(host)
    receipt[field] = value
    # json.dumps deliberately admits NaN/Infinity to model externally supplied
    # invalid JSON constants accepted by the standard library decoder.
    (host[0] / 'organism_brain/entry_evidence.jsonl').write_text(json.dumps(receipt) + '\n')
    inputs, collection, _ = run_host(host, FakeTransport(orders))
    report = daily.analyze(inputs, collection, gate_fn=lambda *_: {'momentum': {'state': 'PASS'}})
    assert report['status'] == 'BLOCKED'
    assert report['strategy_gate']['state'] == 'WITHHELD'


@pytest.mark.parametrize('node_kind', ['fifo', 'directory', 'symlink_loop'])
@pytest.mark.timeout(2)
def test_stable_read_refuses_nonregular_and_looping_inputs_without_blocking(tmp_path, node_kind):
    path = tmp_path / 'input'
    if node_kind == 'fifo':
        daily.os.mkfifo(path)
    elif node_kind == 'directory':
        path.mkdir()
    else:
        path.symlink_to(path)
    with pytest.raises(daily.EvidenceError):
        daily.stable_read(path)


@pytest.mark.parametrize('replacement', ['symlink', 'fifo', 'hardlink'])
@pytest.mark.timeout(2)
def test_stable_read_refuses_path_replacement_between_stat_and_open(tmp_path, monkeypatch, replacement):
    source = tmp_path / 'input'
    source.write_bytes(b'approved input\n')
    other = tmp_path / 'unapproved'
    other.write_bytes(b'unapproved bytes\n')
    original_open = daily.os.open
    swapped = False

    def replace_before_open(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == source.name and kwargs.get('dir_fd') is not None and not swapped:
            swapped = True
            source.unlink()
            if replacement == 'symlink':
                source.symlink_to(other)
            elif replacement == 'hardlink':
                source.hardlink_to(other)
            else:
                daily.os.mkfifo(source)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(daily.os, 'open', replace_before_open)
    with pytest.raises(daily.EvidenceError):
        daily.stable_read(source)
    assert swapped and other.read_bytes() == b'unapproved bytes\n'


@pytest.mark.parametrize('field,value', [
    ('direction', '1'), ('direction', 10 ** 400), ('frame_rows', '100'),
    ('frame_rows', 100.0), ('frame_rows', -1), ('bar_age_seconds', float('inf')),
    ('bar_age_seconds', float('-inf')), ('shares', True), ('shares', float('nan')),
    ('tick', '100'), ('tick', 0.5), ('tick', -1), ('frame_hash', 'z' * 64),
])
def test_receipt_schema_rejects_coercible_counts_nonfinite_values_and_nonhex_hash(host, field, value):
    row, receipt, orders = exact_trade_inputs(host)
    receipt[field] = value
    (host[0] / 'organism_brain/entry_evidence.jsonl').write_text(json.dumps(receipt) + '\n')
    inputs, collection, _ = run_host(host, FakeTransport(orders))
    report = daily.analyze(inputs, collection, gate_fn=lambda *_: {'momentum': {'state': 'PASS'}})
    assert report['status'] == 'BLOCKED'
    assert report['strategy_gate']['state'] == 'WITHHELD'


def test_capture_set_detects_same_size_mutation_with_restored_mtime(host, monkeypatch):
    ledger = host[0] / 'organism_brain/trade_history.csv'
    original_bytes, original_stat = ledger.read_bytes(), ledger.stat()
    real_read = daily.stable_read

    def mutate_prior_input(path):
        raw = real_read(path)
        if path.name == 'strategy_evidence_events.jsonl':
            ledger.write_bytes(b'X' + original_bytes[1:])
            daily.os.utime(ledger, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        return raw

    monkeypatch.setattr(daily, 'stable_read', mutate_prior_input)
    inputs, collection, _ = run_host(host)
    assert inputs['local/trades.csv'] == original_bytes
    assert ledger.stat().st_size == original_stat.st_size
    assert ledger.stat().st_mtime_ns == original_stat.st_mtime_ns
    assert 'input_set_changed_during_capture' in collection['issues']
    assert daily.analyze(inputs, collection)['status'] == 'BLOCKED'


def test_pinned_read_does_not_follow_ancestor_swapped_during_open(tmp_path, monkeypatch):
    parent = tmp_path / 'source'
    parent.mkdir()
    source = parent / 'input'
    source.write_bytes(b'approved bytes\n')
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'input').write_bytes(b'unapproved bytes\n')
    moved = tmp_path / 'original-source'
    real_open = daily.os.open
    swapped = False

    def swap_ancestor(path, flags, *args, **kwargs):
        nonlocal swapped
        if path == 'input' and kwargs.get('dir_fd') is not None and not swapped:
            swapped = True
            parent.rename(moved)
            parent.symlink_to(other, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(daily.os, 'open', swap_ancestor)
    assert daily.stable_read(source) == b'approved bytes\n'
    assert swapped and source.read_bytes() == b'unapproved bytes\n'
    # A later independent read refuses the now-symlinked ancestor outright.
    with pytest.raises(daily.EvidenceError):
        daily.stable_read(source)


def test_publication_date_swap_cannot_redirect_writes_into_brain(host, monkeypatch):
    inputs, collection, paths = run_host(host)
    report = daily.analyze(inputs, collection)
    output = host[0] / 'packs'
    day = output / DAY
    day.mkdir(parents=True)
    brain = host[0] / 'organism_brain'
    before = {p.name: p.read_bytes() for p in brain.iterdir()}
    moved = output / 'original-day'
    real_mkdir = daily.os.mkdir
    swapped = False

    def swap_before_staging(path, mode=0o777, *, dir_fd=None):
        nonlocal swapped
        if str(path).startswith('.incomplete-') and dir_fd is not None and not swapped:
            swapped = True
            day.rename(moved)
            day.symlink_to(brain, target_is_directory=True)
        return real_mkdir(path, mode, dir_fd=dir_fd)

    monkeypatch.setattr(daily.os, 'mkdir', swap_before_staging)
    with pytest.raises(daily.EvidenceError):
        daily.publish(output, inputs, collection, report, paths)
    assert swapped
    assert {p.name: p.read_bytes() for p in brain.iterdir()} == before
    assert not list(moved.iterdir())


@pytest.mark.parametrize('filled_qty', ['0', '3'])
def test_every_replaced_order_withholds_verdict_until_lineage_is_available(host, filled_qty):
    replaced = order('replaced-predecessor', 'buy', int(filled_qty), 100,
                     '2026-09-21T14:00:00Z', 'replaced')
    inputs, collection, _ = run_host(host, FakeTransport([replaced]))
    report = daily.analyze(inputs, collection, gate_fn=lambda *_: {'momentum': {'state': 'PASS'}})
    assert report['status'] == 'BLOCKED'
    assert 'replacement_execution_lineage_unverified' in report['issues']
    assert report['strategy_gate']['state'] == 'WITHHELD'


def test_extreme_broker_cashflow_is_controlled_blocked_report(host):
    enormous = order('enormous', 'buy', 10 ** 400, 100, '2026-09-21T14:00:00Z')
    inputs, collection, paths = run_host(host, FakeTransport([enormous]))
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'BLOCKED'
    assert report['strategy_gate']['state'] == 'WITHHELD'
    pack = daily.publish(host[0] / 'packs', inputs, collection, report, paths)
    daily.verify_pack(pack)
