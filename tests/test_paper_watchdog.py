"""Paper uptime probes and recovery with no real Docker or notifications."""
import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import plistlib
import subprocess
import urllib.error

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def watchdog(monkeypatch):
    spec = importlib.util.spec_from_file_location("paper_watchdog_test", ROOT / "scripts/ops/paper_watchdog.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._scan_for_test = module.scan_critical_events
    monkeypatch.setattr(module, "scan_critical_events", lambda previous, now: {
        "available": True, "new_events": 0, "truncated": False, "seen": [],
    })
    return module


def healthy(module):
    return {"daemon": True, "containers": {
        service: {"name": name, "verified": True, "running": True, "health": "healthy", "age_seconds": 600}
        for service, name in module.SERVICES.items()
    }, "readiness": {"status": "ready", "reachable": True}, "problems": []}


def test_observe_checks_all_services_and_api_without_recovery(watchdog, monkeypatch):
    calls = []

    def command(args, timeout=10):
        calls.append(args)
        if args[1] == "info":
            return subprocess.CompletedProcess(args, 0, "27.0")
        service = next(key for key, value in watchdog.SERVICES.items() if value == args[-1])
        payload = [{"Name": "/" + args[-1], "Config": {"Labels": {
            "com.docker.compose.project": "intra", "com.docker.compose.service": service,
        }}, "State": {"Running": True, "StartedAt": "2026-09-01T00:00:00Z", "Health": {"Status": "healthy"}}}]
        return subprocess.CompletedProcess(args, 0, json.dumps(payload))

    monkeypatch.setattr(watchdog, "command", command)
    monkeypatch.setattr(watchdog.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b'{"status":"ready"}'))
    result = watchdog.observe(1_800_000_000)
    assert result["problems"] == []
    assert set(result["containers"]) == {"api", "redis", "postgres"}
    assert [call[1] for call in calls] == ["info", "inspect", "inspect", "inspect"]


@pytest.mark.parametrize("service", ["postgres", "redis", "api"])
def test_stopped_known_service_is_started_without_recreation(watchdog, service):
    result = healthy(watchdog)
    result["containers"][service]["running"] = False
    assert watchdog.choose_recovery(result, False) == ["docker", "start", watchdog.SERVICES[service]]


def test_missing_or_unverified_dependency_never_recreates_or_restarts_api(watchdog):
    result = healthy(watchdog)
    result["containers"]["postgres"]["verified"] = False
    result["containers"]["api"]["health"] = "unhealthy"
    assert watchdog.choose_recovery(result, True) is None


def test_broker_readiness_failure_does_not_restart_api(watchdog):
    result = healthy(watchdog)
    result["readiness"] = {"status": "not_ready", "reachable": True}
    result["problems"] = ["api_not_ready"]
    assert watchdog.choose_recovery(result, True) is None


@pytest.mark.parametrize("age", [0, 30, 59])
def test_api_has_at_least_sixty_seconds_to_start(watchdog, age):
    result = healthy(watchdog)
    result["containers"]["api"].update(health="unhealthy", age_seconds=age)
    result["readiness"] = {"status": "unreachable", "reachable": False}
    assert watchdog.choose_recovery(result, False) is None


def test_unreachable_mature_api_can_restart_bounded_known_name(watchdog):
    result = healthy(watchdog)
    result["readiness"] = {"status": "unreachable", "reachable": False}
    assert watchdog.choose_recovery(result, False) == ["docker", "restart", "--time", "60", "intra-api-1"]


def test_docker_reopen_requires_explicit_opt_in(watchdog):
    result = {"daemon": False, "containers": {}, "readiness": None, "problems": ["docker_daemon_unavailable"]}
    assert watchdog.choose_recovery(result, False) is None
    assert watchdog.choose_recovery(result, True) == ["open", "-g", "-a", "Docker"]


def test_recovery_persists_cooldown_before_command_and_runs_only_once(watchdog, monkeypatch, tmp_path):
    bad = healthy(watchdog)
    bad["containers"]["api"].update(health="unhealthy")
    bad["problems"] = ["api_unhealthy"]
    observations = iter([bad, healthy(watchdog)])
    monkeypatch.setattr(watchdog, "observe", lambda now: copy.deepcopy(next(observations)))
    monkeypatch.setattr(watchdog.time, "time", lambda: 10000)
    monkeypatch.setattr(watchdog.time, "sleep", lambda delay: None)
    calls = []

    def command(args, timeout=10):
        status = json.loads((tmp_path / "logs/paper_watchdog_status.json").read_text())
        assert status["last_recovery_at"] == 10000
        assert timeout >= 90
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(watchdog, "command", command)
    result = watchdog.run_watchdog(tmp_path, recover=True)
    assert result["healthy"] is True
    assert len(calls) == 1
    monkeypatch.setattr(watchdog, "observe", lambda now: copy.deepcopy(bad))
    result = watchdog.run_watchdog(tmp_path, recover=True)
    assert result["recovery_blocked"] == "cooldown"
    assert len(calls) == 1
    assert len((tmp_path / "logs/paper_watchdog_events.jsonl").read_text().splitlines()) == 2


@pytest.mark.parametrize("prior", ["{broken", '{"last_recovery_at": "NaN"}'])
def test_corrupt_prior_state_fails_closed(watchdog, monkeypatch, tmp_path, prior):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/paper_watchdog_status.json").write_text(prior)
    result = healthy(watchdog)
    result["containers"]["api"]["running"] = False
    result["problems"] = ["api_stopped"]
    monkeypatch.setattr(watchdog, "observe", lambda now: result)
    monkeypatch.setattr(watchdog, "command", lambda *a, **k: pytest.fail("recovery must not run"))
    assert watchdog.run_watchdog(tmp_path, recover=True)["recovery_blocked"] == "previous_status_unreadable"


def test_pause_file_suppresses_recovery_and_notifications(watchdog, monkeypatch, tmp_path):
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/paper_watchdog.pause").touch()
    result = healthy(watchdog)
    result["containers"]["api"]["running"] = False
    result["problems"] = ["api_stopped"]
    monkeypatch.setattr(watchdog, "observe", lambda now: result)
    monkeypatch.setattr(watchdog, "command", lambda *a, **k: pytest.fail("no recovery"))
    monkeypatch.setattr(watchdog, "notify_local", lambda *a: pytest.fail("no notification"))
    assert watchdog.run_watchdog(tmp_path, recover=True, local_notifications=True)["paused"] is True


def test_local_notification_only_on_state_change(watchdog, monkeypatch, tmp_path):
    result = healthy(watchdog)
    result["problems"] = ["api_not_ready"]
    monkeypatch.setattr(watchdog, "observe", lambda now: result)
    calls = []
    monkeypatch.setattr(watchdog, "notify_local", lambda message: calls.append(message) or True)
    assert watchdog.run_watchdog(tmp_path, local_notifications=True)["notification"]["delivered"] is True
    assert watchdog.run_watchdog(tmp_path, local_notifications=True)["notification"]["attempted"] is False
    assert len(calls) == 1


def test_http_readiness_failure_remains_visible(watchdog, monkeypatch):
    monkeypatch.setattr(watchdog, "command", lambda args, **kw: subprocess.CompletedProcess(args, 0, "[]" if args[1] == "inspect" else "27"))

    def unavailable(*args, **kwargs):
        raise urllib.error.HTTPError("http://127.0.0.1:8000/readyz", 503, "not ready", {}, None)

    monkeypatch.setattr(watchdog.urllib.request, "urlopen", unavailable)
    result = watchdog.observe(10000)
    assert result["readiness"] == {"status": "not_ready", "reachable": True}
    assert "api_not_ready" in result["problems"]


def test_critical_log_bridge_deduplicates_and_never_persists_payloads(watchdog, monkeypatch):
    line = "2026-09-19T18:00:00Z CRITICAL ALERT-NO-CHANNELS: private-account-detail"
    calls = []

    def logs(args, timeout):
        calls.append(args)
        assert timeout <= 10
        return subprocess.CompletedProcess(args, 0, line + "\n", "")

    monkeypatch.setattr(watchdog, "command", logs)
    first = watchdog._scan_for_test({}, 1800000000)
    assert first["new_events"] == 1
    second = watchdog._scan_for_test({"critical_monitor": first}, 1800000300)
    assert second["new_events"] == 0
    assert "private-account-detail" not in json.dumps(first)
    assert "--tail" in calls[0] and "--since" in calls[0]


@pytest.mark.parametrize("message,expected", [
    ("INFO All 5 critical tables present", 0),
    ("INFO PREFLIGHT 18/18 passed, 0 critical failures", 0),
    ("INFO PREFLIGHT 18/18 passed, 0 CRITICAL failures", 0),
    ('{"level":"info","message":"All 5 critical tables present"}', 0),
    ('{"level":"info","message":"0 critical failures"}', 0),
    ('{"level":"critical","message":"Risk gate failed"}', 1),
    ('{"levelname":"critical","message":"Risk gate failed"}', 1),
    ('{"severity":"critical","message":"Risk gate failed"}', 1),
    ("CRITICAL Risk gate failed", 1),
    ("ERROR Risk condition is CRITICAL", 1),
    ("ERROR ALERT-NO-CHANNELS: risk event", 1),
    ("ERROR ALERT-DELIVERY-FAILED: risk event", 1),
])
def test_critical_log_bridge_distinguishes_severity_from_startup_prose(watchdog, monkeypatch, message, expected):
    line = "2026-09-19T18:00:00Z " + message + "\n"
    monkeypatch.setattr(watchdog, "command", lambda args, **kwargs: subprocess.CompletedProcess(args, 0, line, ""))
    result = watchdog._scan_for_test({}, 1800000000)
    assert result["available"] is True
    assert result["new_events"] == expected
    assert result["pending_events"] == expected


def test_healthy_startup_checks_do_not_trigger_critical_notification(watchdog, monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, "observe", lambda now: healthy(watchdog))
    watchdog.run_watchdog(tmp_path)
    monkeypatch.setattr(watchdog, "scan_critical_events", watchdog._scan_for_test)
    lines = "INFO All 5 critical tables present\nINFO PREFLIGHT 18/18 passed, 0 critical failures\n"
    monkeypatch.setattr(watchdog, "command", lambda args, **kwargs: subprocess.CompletedProcess(args, 0, lines, ""))
    monkeypatch.setattr(watchdog, "notify_local", lambda message: pytest.fail("startup prose must not notify"))
    result = watchdog.run_watchdog(tmp_path, local_notifications=True)
    assert result["healthy"] is True
    assert result["critical_monitor"]["pending_events"] == 0
    assert result["notification"]["attempted"] is False


def test_new_critical_event_notifies_even_when_api_remains_healthy(watchdog, monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, "observe", lambda now: healthy(watchdog))
    calls = []
    monkeypatch.setattr(watchdog, "notify_local", lambda message: calls.append(message) or True)
    watchdog.run_watchdog(tmp_path)
    monkeypatch.setattr(watchdog, "scan_critical_events", lambda previous, now: {
        "available": True, "new_events": 1, "truncated": False, "seen": ["fingerprint"],
    })
    result = watchdog.run_watchdog(tmp_path, local_notifications=True)
    assert result["healthy"] is True
    assert len(calls) == 1 and "critical alert" in calls[0]


def test_pending_critical_notice_survives_log_failure_until_delivered(watchdog, monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, "observe", lambda now: healthy(watchdog))
    monkeypatch.setattr(watchdog, "scan_critical_events", watchdog._scan_for_test)
    line = "2026-09-19T18:00:00Z CRITICAL ALERT-NO-CHANNELS: risk event\n"
    outcomes = iter([0, 1, 0, 0])
    monkeypatch.setattr(watchdog, "command", lambda args, **kwargs: subprocess.CompletedProcess(args, next(outcomes), line, ""))
    notices = iter([False, False, True])
    delivered = []

    def notify(message):
        result = next(notices)
        if result:
            delivered.append(message)
        return result

    monkeypatch.setattr(watchdog, "notify_local", notify)
    first = watchdog.run_watchdog(tmp_path, local_notifications=True)
    second = watchdog.run_watchdog(tmp_path, local_notifications=True)
    third = watchdog.run_watchdog(tmp_path, local_notifications=True)
    fourth = watchdog.run_watchdog(tmp_path, local_notifications=True)
    assert first["critical_monitor"]["pending_events"] == 1
    assert second["critical_monitor"]["pending_events"] == 1
    assert not second["critical_monitor"]["available"]
    assert third["critical_monitor"]["pending_events"] == 0
    assert not fourth["notification"]["attempted"]
    assert len(delivered) == 1


@pytest.fixture
def backups(watchdog, monkeypatch, tmp_path):
    now = 1_800_000_000
    created = datetime.fromtimestamp(now, timezone.utc).isoformat()
    brain = tmp_path / "organism_brain_archive/2027-01-15T080000.000000Z"
    brain.mkdir(parents=True)
    (brain / "manifest.json").write_text(json.dumps({"saved_at": "2026-01-01T00:00:00Z", "ml_is_trained": False}))
    (brain / "learning_state.json").write_text('{}')
    (brain / ".save_complete").write_text('complete')
    (brain / "private-model.bin").write_bytes(b'private_payload')
    files = {path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in brain.iterdir()}
    brain_receipt = brain / "backup_manifest.json"
    brain_receipt.write_text(json.dumps({"created_at": created, "files": files, "source_saved_at": "2026-01-01T00:00:00Z"}))
    postgres = tmp_path / "private-postgres"
    postgres.mkdir()
    monkeypatch.setattr(watchdog, "POSTGRES_BACKUP_DIR", postgres)
    dump = postgres / "paper-postgres-20270115T080000000000Z.dump"
    dump.write_bytes(b'private_database_payload')
    postgres_receipt = dump.with_suffix('.json')
    postgres_receipt.write_text(json.dumps({"created_at": created, "bytes": dump.stat().st_size,
                                          "sha256": hashlib.sha256(dump.read_bytes()).hexdigest()}))
    return {"root": tmp_path, "now": now, "brain": brain_receipt, "postgres": postgres_receipt,
            "brain_data": brain / "private-model.bin", "postgres_data": dump}


def test_backup_monitor_accepts_fresh_receipts_despite_old_closed_market_source(watchdog, backups):
    result = watchdog.observe_backups(backups["root"], backups["now"])
    assert result["problems"] == []
    assert result["backups"]["brain"]["files_verified"] == 4
    assert result["backups"]["postgres"]["files_verified"] == 1
    assert "private_payload" not in json.dumps(result)
    assert "private_database_payload" not in json.dumps(result)


@pytest.mark.parametrize("kind", ["brain", "postgres"])
@pytest.mark.parametrize("fault,status", [
    ("missing", "missing"), ("malformed", "malformed_receipt"),
    ("checksum", "checksum_mismatch"), ("stale", "stale"),
])
def test_backup_monitor_detects_faults_with_fake_clock(watchdog, backups, kind, fault, status):
    receipt = backups[kind]
    if fault == "missing":
        receipt.unlink()
    elif fault == "malformed":
        receipt.write_text('{broken')
    elif fault == "checksum":
        data = backups[kind + "_data"]
        data.write_bytes(b'x' * data.stat().st_size)
    elif fault == "stale":
        payload = json.loads(receipt.read_text())
        payload["created_at"] = datetime.fromtimestamp(backups["now"] - 26 * 3600 - 1, timezone.utc).isoformat()
        receipt.write_text(json.dumps(payload))
    result = watchdog.observe_backups(backups["root"], backups["now"])
    assert result["backups"][kind]["status"] == status
    assert result["problems"] == [f"{kind}_backup_{status}"]


def test_backup_monitor_flags_missing_directories(watchdog, monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, "POSTGRES_BACKUP_DIR", tmp_path / 'absent-postgres')
    result = watchdog.observe_backups(tmp_path, 1_800_000_000)
    assert result["problems"] == ["brain_backup_missing", "postgres_backup_missing"]


def test_backup_monitor_checks_latest_publication_not_older_valid_archive(watchdog, backups):
    newest = backups['brain'].parent.with_name('2027-01-15T160000.000000Z')
    newest.mkdir()
    (newest / 'backup_manifest.json').write_text('{broken')
    result = watchdog.observe_backups(backups["root"], backups["now"])
    assert result["problems"] == ['brain_backup_malformed_receipt']


@pytest.mark.parametrize('fault,status', [('extra_file', 'checksum_mismatch'), ('symlink', 'invalid_file')])
def test_brain_receipt_must_describe_safe_complete_archive(watchdog, backups, fault, status):
    extra = backups['brain'].parent / 'unexpected.bin'
    if fault == 'symlink':
        extra.symlink_to(backups['brain_data'])
    else:
        extra.write_bytes(b'unrecorded')
    result = watchdog.observe_backups(backups['root'], backups['now'])
    assert result['problems'] == [f'brain_backup_{status}']


def test_backup_freshness_allows_twenty_six_hours_then_alerts(watchdog, backups):
    assert watchdog.observe_backups(backups['root'], backups['now'] + 26 * 3600)['problems'] == []
    assert watchdog.observe_backups(backups['root'], backups['now'] + 26 * 3600 + 1)['problems'] == [
        'brain_backup_stale', 'postgres_backup_stale',
    ]


def test_backup_monitor_bounds_bytes_and_time(watchdog, monkeypatch, backups):
    monkeypatch.setattr(watchdog, 'BACKUP_MAX_BYTES', 1)
    result = watchdog.observe_backups(backups['root'], backups['now'])
    assert result['problems'] == ['brain_backup_check_limit_exceeded', 'postgres_backup_check_limit_exceeded']
    ticks = iter([0, 11, 12])
    monkeypatch.setattr(watchdog.time, 'monotonic', lambda: next(ticks))
    result = watchdog.observe_backups(backups['root'], backups['now'])
    assert result['problems'] == ['brain_backup_check_limit_exceeded', 'postgres_backup_check_limit_exceeded']


def test_backup_checks_are_opt_in_and_do_not_access_host_by_default(watchdog, monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, 'observe', lambda now: healthy(watchdog))
    monkeypatch.setattr(watchdog, 'observe_backups', lambda *args: pytest.fail('backup paths require opt-in'))
    result = watchdog.run_watchdog(tmp_path)
    assert result['backup_monitor'] == {'enabled': False}


def test_backup_alerts_retry_deduplicate_and_never_recover_services(watchdog, monkeypatch, backups):
    monkeypatch.setattr(watchdog, 'observe', lambda now: healthy(watchdog))
    monkeypatch.setattr(watchdog.time, 'time', lambda: backups['now'])
    monkeypatch.setattr(watchdog, 'command', lambda *args, **kwargs: pytest.fail('no service action for backup problem'))
    original = backups['brain'].read_bytes()
    backups['brain'].write_text('{broken')
    notices = []
    delivered = iter([False, True, True])
    monkeypatch.setattr(watchdog, 'notify_local', lambda message: notices.append(message) or next(delivered))
    first = watchdog.run_watchdog(backups['root'], check_backups=True, recover=True, local_notifications=True)
    second = watchdog.run_watchdog(backups['root'], check_backups=True, recover=True, local_notifications=True)
    third = watchdog.run_watchdog(backups['root'], check_backups=True, recover=True, local_notifications=True)
    assert first['healthy'] is False and first['actions'] == []
    assert not first['notification']['delivered']
    assert second['notification']['delivered']
    assert not third['notification']['attempted']
    backups['brain'].write_bytes(original)
    recovered = watchdog.run_watchdog(backups['root'], check_backups=True, recover=True, local_notifications=True)
    assert recovered['healthy'] is True and recovered['actions'] == []
    assert recovered['notification']['delivered']
    assert len(notices) == 3
    assert 'private_payload' not in ''.join(notices)


def test_simultaneous_critical_alert_does_not_hide_backup_failure(watchdog, monkeypatch, backups):
    monkeypatch.setattr(watchdog, 'observe', lambda now: healthy(watchdog))
    monkeypatch.setattr(watchdog.time, 'time', lambda: backups['now'])
    monkeypatch.setattr(watchdog, 'scan_critical_events', lambda previous, now: {
        'available': True, 'new_events': 1, 'pending_events': 1, 'truncated': False, 'seen': ['fingerprint'],
    })
    backups['postgres'].unlink()
    notices = []
    monkeypatch.setattr(watchdog, 'notify_local', lambda message: notices.append(message) or True)
    watchdog.run_watchdog(backups['root'], check_backups=True, local_notifications=True)
    assert len(notices) == 1
    assert 'critical alert' in notices[0] and 'postgres_backup_missing' in notices[0]


def test_reviewed_watchdog_agent_enables_backup_check():
    template = plistlib.loads((ROOT / 'ops/launchd/com.intra.paper.watchdog.plist').read_bytes())
    assert '--check-backups' in template['ProgramArguments']


@pytest.fixture
def policy_probe(monkeypatch, tmp_path):
    """Actual shared verifier, with credentials/HTTP/Docker entirely replaced."""
    from scripts.ops import paper_daily_host as host

    params = {"stop_atr_scale": 0.985}
    baseline_sha = 'b' * 64
    binding = {"source_sha": '1' * 40, "image_sha": '2' * 40,
               "image_digest": 'sha256:' + '3' * 64, "runtime_config_hash": '4' * 64,
               "effective_policy_hash": host.policy_hash(params),
               "policy_baseline": {"sha256": baseline_sha}, "root": str(tmp_path),
               "operator_control_path": "/app/data/operator_control_state.json"}
    deployment = {key: binding[key] for key in ('source_sha', 'image_sha', 'runtime_config_hash')}
    container = {"name": "/intra-api-1", "project": "intra", "service": "api",
                 "image_digest": binding['image_digest']}
    engine = {"initialized": True, "ml_influence_enabled": False, "fixed_risk_sizing": True,
              "policy_lock": {"locked": True, "automatic_promotion_enabled": False,
                              "frozen_models": True, "effective_policy_params": params,
                              "effective_policy_hash": binding['effective_policy_hash'],
                              "baseline": {"configured": True, "verified": True, "sha256": baseline_sha}}}
    record = {"schema": "intra_operator_controls_v1", "operator_halted": False,
              "reason": "synthetic_bootstrap", "changed_at": "2026-09-21T06:44:00+00:00"}
    record["checksum"] = host.policy_hash(record)
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/operator_control_state.json').write_text(json.dumps(record))
    engine['governance'] = {"operator_halted": False, "operator_control_fault": False,
                            "operator_control": {"configured": True, "persistence": "verified",
                                                 "path": binding['operator_control_path'],
                                                 **{key: record[key] for key in ('checksum', 'reason', 'changed_at')}}}
    status = {"live_engine": {"running": True, "engine": engine}}
    calls = []
    monkeypatch.setattr(host, 'load_binding', lambda path: (copy.deepcopy(binding), {'binding_sha256': '5' * 64}, []))
    monkeypatch.setattr(host, 'observer_token', lambda path: 'private-observer-token')
    monkeypatch.setattr(host, 'container_credentials', lambda *args: pytest.fail('broker credentials forbidden'))
    monkeypatch.setattr(host.urllib.request.OpenerDirector, 'open', lambda *a, **kw: pytest.fail('real HTTP forbidden'))

    def get(transport, origin, path, params):
        assert transport.paper_headers == {'APCA-API-KEY-ID': '', 'APCA-API-SECRET-KEY': ''}
        assert transport.local_headers == {'Authorization': 'Bearer private-observer-token'}
        assert origin == 'local' and params == {}
        calls.append(path)
        return json.dumps(deployment if path.endswith('/deploy') else status).encode()

    monkeypatch.setattr(host.daily.GetTransport, 'get', get)
    monkeypatch.setattr(host.daily.GetTransport, 'container_identity', lambda self: json.dumps(container).encode())
    return {'host': host, 'binding': binding, 'deployment': deployment, 'container': container,
            'status': status, 'engine': engine, 'calls': calls}


def test_policy_probe_checks_actual_shared_identity_and_startup_contract(watchdog, policy_probe):
    result = watchdog.observe_policy()
    assert result == {'enabled': True, 'status': 'ok', 'problems': [], 'binding_sha256': '5' * 64}
    assert policy_probe['calls'] == ['/api/v1/paper-monitor/deploy', '/api/v1/paper-monitor/organism/status']
    assert 'private-observer-token' not in json.dumps(result)


@pytest.mark.parametrize('fault', [
    'source', 'image_source', 'image_digest', 'config', 'unlocked', 'promotion', 'models_unfrozen',
    'unconfigured_baseline', 'unverified_baseline', 'wrong_baseline', 'changed_params', 'ml_enabled',
    'kelly_enabled', 'no_scheduler', 'scheduler_stopped', 'uninitialized', 'running_integer',
    'control_fault', 'control_unconfigured', 'control_file_corrupt',
])
def test_policy_probe_rejects_healthy_api_with_wrong_runtime(watchdog, policy_probe, fault):
    p = policy_probe
    engine = p['engine']; policy = engine['policy_lock']
    if fault in {'source', 'image_source', 'config'}:
        p['deployment'][{'source': 'source_sha', 'image_source': 'image_sha', 'config': 'runtime_config_hash'}[fault]] = 'changed'
    elif fault == 'image_digest': p['container']['image_digest'] = 'changed'
    elif fault == 'unlocked': policy['locked'] = False
    elif fault == 'promotion': policy['automatic_promotion_enabled'] = True
    elif fault == 'models_unfrozen': policy['frozen_models'] = False
    elif fault == 'unconfigured_baseline': policy['baseline']['configured'] = False
    elif fault == 'unverified_baseline': policy['baseline']['verified'] = False
    elif fault == 'wrong_baseline': policy['baseline']['sha256'] = 'changed'
    elif fault == 'changed_params': policy['effective_policy_params']['stop_atr_scale'] = 9
    elif fault == 'ml_enabled': engine['ml_influence_enabled'] = True
    elif fault == 'kelly_enabled': engine['fixed_risk_sizing'] = False
    elif fault == 'control_fault': engine['governance']['operator_control_fault'] = True
    elif fault == 'control_unconfigured': engine['governance']['operator_control']['configured'] = False
    elif fault == 'control_file_corrupt':
        (Path(p['binding']['root']) / 'data/operator_control_state.json').write_text('{}')
    elif fault == 'no_scheduler': p['status']['live_engine'] = None
    elif fault == 'scheduler_stopped': p['status']['live_engine']['running'] = False
    elif fault == 'uninitialized': engine['initialized'] = False
    elif fault == 'running_integer': p['status']['live_engine']['running'] = 1
    result = watchdog.observe_policy()
    assert result['status'] != 'ok' and len(result['problems']) == 1
    observation = healthy(watchdog)
    observation['problems'].extend(result['problems'])
    assert watchdog.choose_recovery(observation, True) is None


@pytest.mark.parametrize('stage', ['binding', 'authentication', 'runtime_verification'])
def test_policy_probe_sanitizes_all_exception_bodies(watchdog, monkeypatch, policy_probe, stage):
    host = policy_probe['host']
    def fail(*args, **kwargs):
        raise ValueError('private-observer-token secret-password broker-body')
    monkeypatch.setattr(host, {'binding': 'load_binding', 'authentication': 'observer_token',
                              'runtime_verification': 'verify_runtime'}[stage], fail)
    result = watchdog.observe_policy()
    assert result['status'] == stage and result['problems'] == ['policy_' + stage]
    assert not any(secret in json.dumps(result) for secret in ('private-observer-token', 'secret-password', 'broker-body'))


def test_policy_probe_rejects_binding_changed_across_collection(watchdog, monkeypatch, policy_probe):
    receipts = iter(['5' * 64, '6' * 64])
    monkeypatch.setattr(policy_probe['host'], 'load_binding', lambda path: (
        policy_probe['binding'], {'binding_sha256': next(receipts)}, []))
    assert watchdog.observe_policy()['problems'] == ['policy_binding_changed']


def test_policy_transport_refuses_broker_routes_before_any_transport_call(watchdog, monkeypatch, policy_probe):
    monkeypatch.setattr(policy_probe['host'], 'verify_runtime', lambda transport, binding: transport.get('paper', '/v2/account', {}))
    assert watchdog.observe_policy()['problems'] == ['policy_runtime_verification']
    assert policy_probe['calls'] == []


def test_policy_probe_is_opt_in(watchdog, monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, 'observe', lambda now: healthy(watchdog))
    monkeypatch.setattr(watchdog, 'observe_policy', lambda: pytest.fail('private policy paths require opt-in'))
    assert watchdog.run_watchdog(tmp_path)['policy_monitor'] == {'enabled': False}


def test_policy_attention_retries_without_service_recovery_or_private_payloads(watchdog, monkeypatch, tmp_path, policy_probe):
    monkeypatch.setattr(watchdog, 'observe', lambda now: healthy(watchdog))
    monkeypatch.setattr(watchdog, 'command', lambda *a, **kw: pytest.fail('policy failure must not recover healthy service'))
    policy_probe['status']['live_engine']['running'] = False
    notices = []; deliveries = iter([False, True, True])
    monkeypatch.setattr(watchdog, 'notify_local', lambda message: notices.append(message) or next(deliveries))
    first = watchdog.run_watchdog(tmp_path, recover=True, local_notifications=True, check_policy=True)
    second = watchdog.run_watchdog(tmp_path, recover=True, local_notifications=True, check_policy=True)
    third = watchdog.run_watchdog(tmp_path, recover=True, local_notifications=True, check_policy=True)
    assert first['healthy'] is False and first['actions'] == []
    assert first['notification']['delivered'] is False
    assert second['notification']['delivered'] is True and third['notification']['attempted'] is False
    policy_probe['status']['live_engine']['running'] = True
    recovered = watchdog.run_watchdog(tmp_path, recover=True, local_notifications=True, check_policy=True)
    assert recovered['healthy'] is True and recovered['actions'] == []
    assert recovered['notification']['delivered'] is True and len(notices) == 3
    saved = (tmp_path / 'logs/paper_watchdog_events.jsonl').read_text()
    assert 'policy_scheduler_not_running' in saved
    assert 'private-observer-token' not in saved + ''.join(notices)


def test_policy_attention_respects_maintenance_pause(watchdog, monkeypatch, tmp_path, policy_probe):
    (tmp_path / 'logs').mkdir(); (tmp_path / 'logs/paper_watchdog.pause').touch()
    monkeypatch.setattr(watchdog, 'observe', lambda now: healthy(watchdog))
    monkeypatch.setattr(watchdog, 'command', lambda *a, **kw: pytest.fail('no service action'))
    monkeypatch.setattr(watchdog, 'notify_local', lambda *a: pytest.fail('no real notification'))
    policy_probe['engine']['initialized'] = False
    result = watchdog.run_watchdog(tmp_path, recover=True, local_notifications=True, check_policy=True)
    assert result['paused'] is True and result['healthy'] is False and result['actions'] == []
    assert result['problems'] == ['policy_engine_not_initialized']


def test_reviewed_watchdog_agent_enables_policy_check():
    template = plistlib.loads((ROOT / 'ops/launchd/com.intra.paper.watchdog.plist').read_bytes())
    assert '--check-policy' in template['ProgramArguments']


def test_cli_passes_policy_opt_in(watchdog, monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, 'ROOT', tmp_path)
    monkeypatch.setattr(watchdog.sys, 'argv', ['paper_watchdog.py', '--check-policy'])
    calls = []
    monkeypatch.setattr(watchdog, 'run_watchdog', lambda root, **kwargs: calls.append(kwargs) or {'healthy': False, 'paused': False})
    assert watchdog.main() == 1
    assert calls[0]['check_policy'] is True
