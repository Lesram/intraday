from datetime import datetime
import pytest
from scripts.ops.standdown_session_row import calendar_session, log_record, session_diagnostics


def now(raw):
    return datetime.fromisoformat(raw.replace('Z', '+00:00'))


@pytest.mark.parametrize('day,close,utc_close', [
    ('2026-09-21', '16:00', '2026-09-21T20:00:00+00:00'),
    ('2026-11-23', '16:00', '2026-11-23T21:00:00+00:00'),
    ('2026-11-27', '13:00', '2026-11-27T18:00:00+00:00'),
])
def test_authoritative_calendar_handles_dst_and_early_close(day, close, utc_close):
    response = [{'date': day, 'open': '09:30', 'close': close}]
    from datetime import timedelta
    closed = now(utc_close)
    assert calendar_session(day, response, closed + timedelta(minutes=5))['state'] == 'CLOSED'
    assert calendar_session(day, response, closed + timedelta(minutes=4, seconds=59))['state'] == 'BEFORE_CLOSE'
    assert calendar_session(day, response, closed)['close'] == utc_close


def test_holiday_future_and_invalid_calendar_are_distinct():
    assert calendar_session('2026-12-25', [], now('2026-12-25T22:00:00Z'))['state'] == 'NO_SESSION'
    with pytest.raises(ValueError, match='future_session'):
        calendar_session('2026-12-28', [], now('2026-12-25T22:00:00Z'))
    with pytest.raises(ValueError):
        calendar_session('2026-12-25', [{'date': '2026-12-24'}], now('2026-12-25T22:00:00Z'))


def test_legacy_timezone_is_explicit_not_machine_guess():
    line = '2026-11-23 16:01:00,123 - INFO - Organism tick: regime=trend'
    with pytest.raises(ValueError, match='unknown_log_timezone'):
        log_record(line)
    when, _ = log_record(line, naive_timezone='America/New_York')
    assert when.hour == 21


def test_first_last_ticks_do_not_prove_full_session_coverage():
    session = {'open': '2026-09-21T13:30:00Z', 'close': '2026-09-21T20:00:00Z'}
    logs = {'application.log.9': b'2026-09-21T13:30:00Z Organism tick: regime=x\n',
            'application.log': b'2026-09-21T20:00:00Z Organism tick: regime=x\n'}
    report = session_diagnostics('2026-09-21', session, b'', b'closed_at\n', logs)
    assert report['coverage'] == 'UNVERIFIED'
    assert report['counts']['successful_ticks'] == 2
    assert report['max_successful_tick_gap_seconds'] == 23400


def test_unknown_or_missing_logs_never_become_complete_zero_counts():
    report = session_diagnostics('2026-09-21', {}, b'{bad}\n', b'closed_at\n\n', {})
    assert report['coverage'] == 'UNVERIFIED'
    assert report['malformed']['events'] == 1


def test_exact_submission_predicate_and_timestamp_not_substring():
    logs = {'application.log.8': (
        b'2026-09-20T20:00:00Z text mentions 2026-09-21 Order submitted successfully\n'
        b'2026-09-21T14:00:00Z Order submitted successfully\n'
        b'2026-09-21T14:00:01Z order submitted\n'
        b'2026-09-21T14:00:02Z submit_entry\n')}
    report = session_diagnostics('2026-09-21', {}, b'', b'closed_at\n', logs)
    assert report['counts']['orders'] == 1
