"""Paper uptime probes and recovery with no real Docker or notifications."""
import copy
import importlib.util
import io
import json
from pathlib import Path
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
