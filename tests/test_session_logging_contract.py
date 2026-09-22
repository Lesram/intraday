"""Deployed YAML -> real logging records -> immutable collector, without services."""
from datetime import datetime, timedelta, timezone
import io
import json
import logging
from pathlib import Path
import subprocess
import sys

import pytest

from backend.infra.logging import JSONFormatter, SessionJSONFormatter, UTCSessionFileHandler
from scripts.ops import paper_daily_evidence as daily
from scripts.ops.standdown_session_row import session_log_name
from tests.test_paper_daily_evidence import DAY, NOW, host, run_host  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


def _produce_with_deployed_config(root):
    """Runs in a separate Python process so dictConfig cannot disturb pytest."""
    import logging.config
    import yaml
    from backend.api.logging_setup import configure_api_logging
    from backend.utils.logger import get_logger

    config = yaml.safe_load((ROOT / 'logging_config.yaml').read_text())
    config['handlers']['file']['filename'] = str(root / 'logs/application.log')
    config['handlers']['session']['directory'] = str(root / 'logs/sessions')
    config['handlers']['console']['stream'] = io.StringIO()
    logging.config.dictConfig(config)
    # Actual API bootstrap reconfigures root; backend's session handler must survive.
    configure_api_logging()
    logger = logging.getLogger('backend.organism.live_engine')
    structured = get_logger('backend.organism.live_engine')
    opened = NOW.replace(hour=13, minute=30)
    factory = logging.getLogRecordFactory()
    at = opened

    def record_factory(*args, **kwargs):
        record = factory(*args, **kwargs)
        record.created = at.timestamp()
        return record

    logging.setLogRecordFactory(record_factory)
    for index, seconds in enumerate(range(0, 23401, 120)):
        at = opened + timedelta(seconds=seconds)
        if index % 2:
            structured.info('Organism tick: regime=trending_up', detail='quoted "value"\nnext line\u0085\u2028\u2029')
        else:
            logger.info('Organism tick: regime=trending_up')
    at = opened + timedelta(seconds=30)
    logger.info('plain "quotes", backslash \\ and newline\ncontinued\u0085\u2028\u2029',
                extra={'authorization': 'synthetic_auth_value', 'password': 'synthetic_password_value'})
    try:
        raise ValueError('password=synthetic_exception_secret')
    except ValueError:
        logger.exception('Captured test exception')
    logging.shutdown()


def test_actual_yaml_formats_plain_structlog_and_exception_through_collector(host):  # noqa: F811 - Imported fixture.
    root, *_ = host
    canonical = root / session_log_name(DAY)
    canonical.unlink()  # replace synthetic fixture with actual deployed log production
    legacy_before = (root / 'logs/application.log.9').read_bytes()
    process = subprocess.run([sys.executable, str(Path(__file__).resolve()), str(root)],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    records = [json.loads(line) for line in canonical.read_text().split('\n') if line]
    assert len(records) == 198
    assert all(row['timestamp'].endswith('Z') and row['schema'] == daily.SESSION_LOG_SCHEMA for row in records)
    assert records[0]['timestamp'] == '2026-09-21T13:30:00Z'
    assert records[1]['message'] == 'Organism tick: regime=trending_up'
    assert records[1]['structured']['detail'] == 'quoted "value"\nnext line\u0085\u2028\u2029'
    assert records[-2]['message'] == 'plain "quotes", backslash \\ and newline\ncontinued\u0085\u2028\u2029'
    assert records[-1]['exception'] == {'type': 'ValueError'}
    assert 'extra' not in records[-2]
    assert (root / 'logs/application.log.9').read_bytes() == legacy_before
    # The ordinary rotating log also contains valid escaped JSON for new records.
    app_text = (root / 'logs/application.log').read_text()
    app_lines = app_text.split('\n')[1:-1]
    assert len(app_lines) == 198
    assert all(json.loads(line)['timestamp'].endswith('Z') for line in app_lines)
    for secret in ['synthetic_auth_value', 'synthetic_password_value', 'synthetic_exception_secret']:
        assert secret not in canonical.read_text() and secret not in app_text
    inputs, collection, paths = run_host(host)
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'READY_FOR_REVIEW', report['issues']
    assert report['standdown']['counts']['successful_ticks'] == 196
    assert report['standdown']['malformed']['logs'] == 0
    pack = daily.publish(root / 'evidence', inputs, collection, report, paths)
    replay_inputs, replay_collection = daily.verify_pack(pack)
    assert daily.analyze(replay_inputs, replay_collection) == report


@pytest.mark.parametrize('formatter', [JSONFormatter, SessionJSONFormatter])
def test_formatter_timestamp_is_record_creation_not_formatting_wall_clock(formatter):
    record = logging.LogRecord('backend.example', logging.INFO, __file__, 1, 'hello %s', ('"world"',), None)
    record.created = datetime(2001, 2, 3, 4, 5, 6, 123456, tzinfo=timezone.utc).timestamp()
    value = json.loads(formatter().format(record))
    assert value['timestamp'] == '2001-02-03T04:05:06.123456Z'
    assert value['message'] == 'hello "world"'


def test_nonfinite_diagnostic_values_remain_valid_json_strings():
    record = logging.LogRecord('backend.example', logging.INFO, __file__, 1,
                               '{"event":"diagnostic", "value":NaN, "overflow":1e999}', (), None)
    record.example_metric = float('inf')
    value = json.loads(SessionJSONFormatter().format(record),
                       parse_constant=lambda value: pytest.fail('nonstandard JSON number'))
    assert value['structured']['value'] == 'NaN'
    assert value['structured']['overflow'] == '1e999'
    assert 'extra' not in value


def test_handler_routes_by_utc_record_date_and_restart_appends_without_rotation(tmp_path):
    def emit(created, message):
        record = logging.LogRecord('backend.example', logging.INFO, __file__, 1, message, (), None)
        record.created = datetime.fromisoformat(created).timestamp()
        handler.handle(record)
    handler = UTCSessionFileHandler(str(tmp_path))
    handler.setFormatter(SessionJSONFormatter())
    emit('2026-09-21T16:59:59-07:00', 'before UTC midnight')
    emit('2026-09-21T17:00:00-07:00', 'after UTC midnight')
    handler.close()
    handler = UTCSessionFileHandler(str(tmp_path))
    handler.setFormatter(SessionJSONFormatter())
    emit('2026-09-22T00:00:01+00:00', 'after restart')
    handler.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == ['2026-09-21.jsonl', '2026-09-22.jsonl']
    assert len((tmp_path / '2026-09-21.jsonl').read_text().splitlines()) == 1
    assert [json.loads(s)['message'] for s in (tmp_path / '2026-09-22.jsonl').read_text().splitlines()] == [
        'after UTC midnight', 'after restart']


@pytest.mark.parametrize('defect', ['missing', 'rotated', 'malformed', 'unversioned', 'wrong_day', 'naive', 'truncated', 'gap', 'invalid_utf8', 'nonfinite', 'duplicate_key', 'overflow', 'deep_json', 'portable_depth'])
def test_canonical_stream_defects_block_even_with_old_logs_present(host, defect):  # noqa: F811
    root, *_ = host
    path = root / session_log_name(DAY)
    lines = path.read_bytes().splitlines(keepends=True)
    if defect == 'missing':
        path.unlink()
    elif defect == 'rotated':
        path.with_suffix('.jsonl.1').write_bytes(b'old rotated bytes\n')
    elif defect == 'malformed':
        path.write_bytes(path.read_bytes() + b'{"unclosed":\n')
    elif defect == 'truncated':
        path.write_bytes(path.read_bytes().rstrip(b'\n'))
    elif defect == 'gap':
        path.write_bytes(b''.join(lines[:50] + lines[52:]))
    elif defect == 'invalid_utf8':
        path.write_bytes(path.read_bytes() + b'{"message":"\xff"}\n')
    elif defect == 'nonfinite':
        value = json.loads(lines[0])
        value['metric'] = float('nan')
        path.write_bytes(json.dumps(value).encode() + b'\n' + b''.join(lines[1:]))
    elif defect == 'duplicate_key':
        path.write_bytes(b'{"schema":"invalid",' + lines[0][1:] + b''.join(lines[1:]))
    elif defect == 'overflow':
        path.write_bytes(b'{"metric":1e999,' + lines[0][1:] + b''.join(lines[1:]))
    elif defect in ('deep_json', 'portable_depth'):
        depth = 2000 if defect == 'deep_json' else 64
        # Keep all required fields valid: without the depth bound this record
        # would otherwise certify coverage on permissive Python decoders.
        path.write_bytes(b'{"nested":' + b'[' * depth + b'0' + b']' * depth + b','
                         + lines[0][1:] + b''.join(lines[1:]))
    else:
        value = json.loads(lines[0])
        if defect == 'unversioned':
            value.pop('schema')
        elif defect == 'wrong_day':
            value['timestamp'] = '2026-09-20T13:30:00Z'
        else:
            value['timestamp'] = '2026-09-21T13:30:00'
        path.write_bytes(json.dumps(value).encode() + b'\n' + b''.join(lines[1:]))
    inputs, collection, _ = run_host(host)
    report = daily.analyze(inputs, collection, gate_fn=lambda *a: pytest.fail('invalid session exposed gate'))
    assert report['status'] == 'BLOCKED'
    assert report['strategy_gate']['state'] == 'WITHHELD'


def test_rotation_during_capture_cannot_drop_earlier_records(host, monkeypatch):  # noqa: F811
    root, *_ = host
    path = root / session_log_name(DAY)
    read = daily.stable_read
    def rotate_after_read(source):
        raw = read(source)
        if source == path:
            source.with_suffix('.jsonl.1').write_bytes(b'rotated\n')
        return raw
    monkeypatch.setattr(daily, 'stable_read', rotate_after_read)
    inputs, collection, _ = run_host(host)
    assert 'log_rotation_during_capture' in collection['issues']
    assert daily.analyze(inputs, collection)['status'] == 'BLOCKED'


def test_legacy_replay_stays_blocked_and_does_not_claim_canonical_provenance(host):  # noqa: F811
    inputs, collection, _ = run_host(host)
    collection.pop('log_contract')
    inputs.pop(session_log_name(DAY))
    inputs['logs/application.log'] = b'{"timestamp":"2026-09-21T13:30:00","message":"{"event":"Organism tick: regime=x"}"}\n'
    original = inputs['logs/application.log']
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'BLOCKED'
    assert report['standdown']['malformed']['logs'] == 1
    assert 'log_contract' not in report['standdown']
    assert inputs['logs/application.log'] == original


def test_unexpected_log_input_never_upgrades_canonical_coverage(host):  # noqa: F811
    inputs, collection, _ = run_host(host)
    inputs['logs/application.log'] = b'legacy cannot be silently merged\n'
    report = daily.analyze(inputs, collection)
    assert report['status'] == 'BLOCKED'
    assert report['standdown']['log_contract_errors'] == ['canonical_session_log_set_mismatch']


if __name__ == '__main__':
    _produce_with_deployed_config(Path(sys.argv[1]))
