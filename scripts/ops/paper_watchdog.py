"""Bounded local paper-service recovery. Never recreates containers or config."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import stat
import subprocess
import re
import sys
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[2]
SERVICES = {
    "postgres": "trading_platform_db_paper",
    "redis": "intra-redis-1",
    "api": "intra-api-1",
}
COOLDOWN_SECONDS = 900
STARTUP_GRACE_SECONDS = 60
BACKUP_MAX_AGE_SECONDS = 26 * 3600
BACKUP_MAX_BYTES = 512 * 1024 * 1024
POSTGRES_BACKUP_DIR = Path.home() / "Library/Application Support/Intra/backups/postgres"
READINESS_MAX_BYTES = 8192
READINESS_MAX_DEPTH = 16


class ReadinessPayloadError(ValueError):
    """Only fixed local codes may describe an unreadable response."""

    def __init__(self, code, *, legacy_unreadable=False):
        self.code = code if code in ("invalid_json", "body_too_large", "invalid_schema") else "invalid_json"
        self.legacy_unreadable = legacy_unreadable
        super().__init__(self.code)


def _read_readiness(response) -> dict:
    raw = response.read(READINESS_MAX_BYTES + 1)
    if not isinstance(raw, bytes):
        raise ReadinessPayloadError("invalid_json", legacy_unreadable=True)
    if len(raw) > READINESS_MAX_BYTES:
        raise ReadinessPayloadError("body_too_large")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ReadinessPayloadError("invalid_json")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ReadinessPayloadError("invalid_json")

    try:
        value = json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except ReadinessPayloadError:
        raise
    except RecursionError:
        raise ReadinessPayloadError("invalid_json") from None
    except (ValueError, UnicodeError):
        raise ReadinessPayloadError("invalid_json", legacy_unreadable=True) from None
    if not isinstance(value, dict):
        raise ReadinessPayloadError("invalid_schema", legacy_unreadable=True)
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        if depth > READINESS_MAX_DEPTH:
            raise ReadinessPayloadError("invalid_json")
        if isinstance(item, dict):
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
    return value


def _readiness_diagnostics(response, payload=None, *, body_status="parsed") -> dict:
    """Map the readyz contract to fixed codes; never copy response prose."""
    result = {"body_status": body_status, "checks": {}, "reasons": {}}
    status = getattr(response, "status", None)
    if type(status) is int and 100 <= status <= 599:
        result["http_status"] = status
    if payload is None:
        return result
    if payload.get("status") not in ("ready", "not ready", "not_ready"):
        result["body_status"] = "invalid_schema"
    checks = payload.get("checks", {})
    problems = payload.get("problems", {})
    if not isinstance(checks, dict) or not isinstance(problems, dict):
        result["body_status"] = "invalid_fields"
        return result
    for component in ("database", "broker", "brain_loaded", "tick_recent"):
        if component in checks:
            if type(checks[component]) is bool:
                result["checks"][component] = checks[component]
            else:
                result["body_status"] = "invalid_fields"
    for component in ("database", "broker", "brain", "tick_loop", "readiness_diag"):
        if component not in problems:
            continue
        message = problems[component]
        reason = "unclassified"
        if not isinstance(message, str):
            result["body_status"] = "invalid_fields"
        elif component in ("database", "broker"):
            label = "Database" if component == "database" else "Broker"
            if message == label + " connection failed":
                reason = "connection_failed"
            elif re.fullmatch(label + r" timeout \(\d{1,9}(?:\.\d{1,3})?ms > \d{1,9}ms\)", message):
                reason = "timeout"
        elif component == "brain" and message == "Brain not loaded":
            reason = "not_loaded"
        elif component == "tick_loop" and re.fullmatch(r"Last tick \d{1,9}s ago \(>60s\)", message):
            reason = "stale"
        elif component == "readiness_diag":
            reason = "diagnostic_error"
        result["reasons"][component] = reason
    return result


def command(args: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n")
    temporary.replace(path)


def observe(now: float) -> dict:
    result = {"daemon": False, "containers": {}, "readiness": None, "problems": []}
    try:
        daemon = command(["docker", "info", "--format", "{{.ServerVersion}}"])
    except (OSError, subprocess.TimeoutExpired):
        result["problems"].append("docker_daemon_unavailable")
        return result
    if daemon.returncode:
        result["problems"].append("docker_daemon_unavailable")
        return result
    result["daemon"] = True
    for service, name in SERVICES.items():
        item = {"name": name, "verified": False, "running": False, "health": "missing", "age_seconds": 0}
        try:
            inspected = command(["docker", "inspect", name])
            if inspected.returncode == 0:
                data = json.loads(inspected.stdout)[0]
                labels = data.get("Config", {}).get("Labels") or {}
                item["verified"] = (
                    data.get("Name", "").lstrip("/") == name
                    and labels.get("com.docker.compose.project") == "intra"
                    and labels.get("com.docker.compose.service") == service
                )
                state = data["State"]
                item["running"] = state.get("Running") is True
                item["health"] = state.get("Health", {}).get("Status", "unknown")
                started = state.get("StartedAt", "")
                if started and not started.startswith("0001-"):
                    item["age_seconds"] = max(0, now - datetime.fromisoformat(started.replace("Z", "+00:00")).timestamp())
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, IndexError, TypeError):
            item["health"] = "inspection_failed"
        result["containers"][service] = item
        if not item["verified"]:
            result["problems"].append(f"{service}_missing_or_unverified")
        elif not item["running"]:
            result["problems"].append(f"{service}_stopped")
        elif item["health"] != "healthy":
            result["problems"].append(f"{service}_{item['health']}")
    response = None
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/readyz", timeout=5) as response:
            readiness = _read_readiness(response)
        status = readiness.get("status")
        result["readiness"] = {"status": status if status in ("ready", "not ready", "not_ready")
                               else "not_ready", "reachable": True}
        if readiness.get("status") != "ready":
            result["readiness"]["diagnostics"] = _readiness_diagnostics(response, readiness)
            result["problems"].append("api_not_ready")
    except urllib.error.HTTPError as error:
        # A responding readiness endpoint can report an upstream broker failure.
        # Restarting the API would not fix that and could disturb paper state.
        try:
            with error:
                diagnostics = _readiness_diagnostics(error, _read_readiness(error))
        except ReadinessPayloadError as invalid:
            diagnostics = _readiness_diagnostics(error, body_status=invalid.code)
        except (OSError, ValueError, TypeError, AttributeError, http.client.HTTPException):
            diagnostics = _readiness_diagnostics(error, body_status="read_failed")
        result["readiness"] = {"status": "not_ready", "reachable": True,
                               "diagnostics": diagnostics}
        result["problems"].append("api_not_ready")
    except ReadinessPayloadError as invalid:
        # New diagnostic bounds/strictness cannot grant restart authority for
        # an API that responded. Preserve only the old JSON/schema failure path.
        result["readiness"] = {"status": "unreachable" if invalid.legacy_unreadable else "not_ready",
                               "reachable": not invalid.legacy_unreadable,
                               "diagnostics": _readiness_diagnostics(response, body_status=invalid.code)}
        result["problems"].append("api_readiness_unreachable" if invalid.legacy_unreadable else "api_not_ready")
    except (OSError, ValueError, TypeError, AttributeError):
        if response is not None:
            # Headers arrived: a timeout/reset while reading the body does not
            # make the API unreachable or authorize restarting a healthy API.
            result["readiness"] = {"status": "not_ready", "reachable": True,
                                   "diagnostics": _readiness_diagnostics(response, body_status="read_failed")}
            result["problems"].append("api_not_ready")
        else:
            result["readiness"] = {"status": "unreachable", "reachable": False}
            result["problems"].append("api_readiness_unreachable")
    except http.client.HTTPException:
        # A newly handled protocol/body failure is not new restart authority.
        # Without a response object, leave reachability unverified.
        if response is not None:
            result["readiness"] = {"status": "not_ready", "reachable": True,
                                   "diagnostics": _readiness_diagnostics(response, body_status="read_failed")}
            result["problems"].append("api_not_ready")
        else:
            result["problems"].append("api_readiness_unverified")
    return result


def choose_recovery(observation: dict, reopen_docker: bool) -> list[str] | None:
    if not observation["daemon"]:
        return ["open", "-g", "-a", "Docker"] if reopen_docker else None
    # Dependency order; at most one known container is touched per invocation.
    for service, item in observation["containers"].items():
        if not item["verified"]:
            return None
        if not item["running"]:
            return ["docker", "start", SERVICES[service]]
        if item["health"] == "unhealthy" or (
            service == "api" and observation["readiness"] is not None
            and not observation["readiness"]["reachable"]
        ):
            if item["age_seconds"] < STARTUP_GRACE_SECONDS:
                return None
            return ["docker", "restart", "--time", "60", SERVICES[service]]
        if item["health"] != "healthy":
            return None
    return None


def notify_local(message: str) -> bool:
    # Arguments, never interpolated AppleScript or shell text. Operator opt-in.
    script = 'on run argv\ndisplay notification (item 1 of argv) with title "Intra paper readiness"\nend run'
    try:
        return command(["osascript", "-e", script, message], timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def scan_critical_events(previous: dict, now: float) -> dict:
    """Bridge undelivered application alerts using bounded logs, without secrets."""
    previous_monitor = previous.get("critical_monitor") or {}
    if not isinstance(previous_monitor, dict):
        previous_monitor = {}
    seen = previous_monitor.get("seen", [])
    if not isinstance(seen, list):
        seen = []
    since = previous_monitor.get("scanned_at")
    if not isinstance(since, str):
        since = datetime.fromtimestamp(now - 900, timezone.utc).isoformat()
    pending = previous_monitor.get("pending_events", 0)
    pending = pending if isinstance(pending, int) and pending >= 0 else 0
    result = {"scanned_at": since,
              "available": False, "new_events": 0, "seen": seen[-1000:], "truncated": False,
              "pending_events": pending}
    try:
        logs = command(["docker", "logs", "--timestamps", "--since", since,
                        "--tail", "1000", SERVICES["api"]], timeout=10)
        if logs.returncode:
            return result
    except (OSError, subprocess.TimeoutExpired):
        return result
    content = (logs.stdout or "") + (logs.stderr or "")
    lines = content[-262144:].splitlines()
    result["truncated"] = len(content) > 262144 or len(lines) >= 1000
    hashes = list(result["seen"])
    for line in lines:
        # Startup INFO prose mentions critical tables and zero failures. Match
        # explicit uppercase severity/text or a structured logging level only.
        severity_text = re.sub(r"\b0\s+CRITICAL\s+failures?\b", "", line)
        if not (
            re.search(r"ALERT-(?:NO-CHANNELS|DELIVERY-FAILED)", line, re.IGNORECASE)
            or re.search(r"\bCRITICAL\b", severity_text)
            or re.search(r'"(?:level|levelname|severity)"\s*:\s*"critical"', line, re.IGNORECASE)
        ):
            continue
        fingerprint = hashlib.sha256(line.encode()).hexdigest()
        if fingerprint not in hashes:
            hashes.append(fingerprint)
            result["new_events"] += 1
    # Persist only fingerprints/counts. Alert payloads can include private
    # account details, so never copy raw lines into reports/notifications.
    result["seen"] = hashes[-1000:]
    result["available"] = True
    result["scanned_at"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    result["pending_events"] += result["new_events"]
    return result


class BackupCheckError(ValueError):
    """A fixed, non-sensitive monitoring failure code."""


def observe_backups(root: Path, now: float) -> dict:
    """Check published backups only; never import models or mutate archives."""
    deadline = time.monotonic() + 10
    remaining_bytes = BACKUP_MAX_BYTES

    def check_budget():
        if time.monotonic() >= deadline:
            raise BackupCheckError("check_limit_exceeded")

    def regular_file(path):
        check_budget()
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            raise BackupCheckError("invalid_file")
        return info

    def read_metadata(path):
        if regular_file(path).st_size > 1024 * 1024:
            raise BackupCheckError("check_limit_exceeded")
        with path.open("rb") as source:
            content = source.read(1024 * 1024 + 1)
        if len(content) > 1024 * 1024:
            raise BackupCheckError("check_limit_exceeded")
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise BackupCheckError("malformed_receipt")
        return payload

    def verify_file(path, expected):
        nonlocal remaining_bytes
        size, digest = expected["bytes"], expected["sha256"]
        if type(size) is not int or size < 0 or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise BackupCheckError("malformed_receipt")
        if regular_file(path).st_size != size:
            raise BackupCheckError("checksum_mismatch")
        if size > remaining_bytes:
            raise BackupCheckError("check_limit_exceeded")
        hashed = hashlib.sha256()
        with path.open("rb") as source:
            while True:
                check_budget()
                block = source.read(1024 * 1024)
                if not block:
                    break
                remaining_bytes -= len(block)
                if remaining_bytes < 0:
                    raise BackupCheckError("check_limit_exceeded")
                hashed.update(block)
        if hashed.hexdigest() != digest:
            raise BackupCheckError("checksum_mismatch")

    def latest(directory, pattern):
        if directory.is_symlink():
            raise BackupCheckError("invalid_file")
        candidates = []
        with os.scandir(directory) as entries:
            for index, entry in enumerate(entries):
                check_budget()
                if index >= 4096:
                    raise BackupCheckError("check_limit_exceeded")
                if re.fullmatch(pattern, entry.name):
                    candidates.append(Path(entry.path))
        if not candidates:
            raise BackupCheckError("missing")
        return max(candidates, key=lambda entry: entry.name)

    result = {"enabled": True, "max_age_seconds": BACKUP_MAX_AGE_SECONDS, "backups": {}, "problems": []}
    for kind in ("brain", "postgres"):
        item = {"status": "unknown"}
        try:
            if kind == "brain":
                backup = latest(root / "organism_brain_archive", r"\d{4}-\d{2}-\d{2}(?:T\d{6}\.\d{6}Z)?")
                if backup.is_symlink() or not backup.is_dir():
                    raise BackupCheckError("invalid_file")
                receipt = read_metadata(backup / "backup_manifest.json")
                files = receipt["files"]
                if not isinstance(files, dict) or not files:
                    raise BackupCheckError("malformed_receipt")
                if len(files) > 1024:
                    raise BackupCheckError("check_limit_exceeded")
                if not {"manifest.json", "learning_state.json", ".save_complete"} <= files.keys():
                    raise BackupCheckError("malformed_receipt")
                # A receipt must describe the complete published archive, not
                # a subset that silently omits a damaged or extra model file.
                actual_files, directories, entry_count = set(), [backup], 0
                while directories:
                    with os.scandir(directories.pop()) as entries:
                        for entry in entries:
                            check_budget()
                            entry_count += 1
                            if entry_count > 4096:
                                raise BackupCheckError("check_limit_exceeded")
                            if entry.is_symlink():
                                raise BackupCheckError("invalid_file")
                            if entry.is_dir(follow_symlinks=False):
                                directories.append(Path(entry.path))
                            else:
                                actual_files.add(str(Path(entry.path).relative_to(backup)))
                if actual_files - {"backup_manifest.json"} != set(files):
                    raise BackupCheckError("checksum_mismatch")
                for name, expected in files.items():
                    relative = Path(name)
                    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                        raise BackupCheckError("malformed_receipt")
                    if any(parent.is_symlink() for parent in (backup / relative).parents if parent != backup and backup in parent.parents):
                        raise BackupCheckError("invalid_file")
                    verify_file(backup / relative, expected)
                manifest = read_metadata(backup / "manifest.json")
                read_metadata(backup / "learning_state.json")
                if not manifest.get("saved_at") or (backup / ".save_complete").stat().st_size == 0:
                    raise BackupCheckError("malformed_receipt")
                datetime.fromisoformat(manifest["saved_at"].replace("Z", "+00:00"))
                if manifest.get("ml_is_trained"):
                    models = {"ml_classifier.joblib", "ml_regressor.joblib", "ml_state.json"}
                    if not models <= files.keys() or any(files[name]["bytes"] == 0 for name in models):
                        raise BackupCheckError("malformed_receipt")
                    read_metadata(backup / "ml_state.json")
                item["files_verified"] = len(files)
            else:
                selected = latest(POSTGRES_BACKUP_DIR, r"paper-postgres-\d{8}T\d{12}Z\.(?:dump|json)")
                receipt = read_metadata(selected.with_suffix(".json"))
                if receipt["bytes"] == 0:
                    raise BackupCheckError("malformed_receipt")
                verify_file(selected.with_suffix(".dump"), receipt)
                item["files_verified"] = 1
            created = datetime.fromisoformat(receipt["created_at"].replace("Z", "+00:00"))
            if created.tzinfo is None or created.timestamp() > now + 300:
                raise BackupCheckError("malformed_receipt")
            item["age_seconds"] = max(0, now - created.timestamp())
            item["status"] = "stale" if item["age_seconds"] > BACKUP_MAX_AGE_SECONDS else "ok"
        except BackupCheckError as exc:
            item["status"] = str(exc)
        except FileNotFoundError:
            item["status"] = "missing"
        except (ValueError, TypeError, KeyError, AttributeError):
            item["status"] = "malformed_receipt"
        except OSError:
            item["status"] = "unavailable"
        result["backups"][kind] = item
        if item["status"] != "ok":
            result["problems"].append(f"{kind}_backup_{item['status']}")
    return result


def observe_policy() -> dict:
    """Check the pinned paper policy using local observer access only.

    This check never acquires paper-broker credentials or chooses recovery.
    All external failures use fixed codes: exception bodies may contain secrets.
    """
    result = {"enabled": True, "status": "unavailable", "problems": []}
    stage = "binding"
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from scripts.ops import paper_daily_host as host

        binding, paths, _ = host.load_binding(host.DEFAULT_BINDING)
        result["binding_sha256"] = paths["binding_sha256"]

        class LocalObserverTransport(host.daily.GetTransport):
            captured_status = None

            def get(self, origin, path, params):
                if origin != "local" or params or path not in {
                    "/api/v1/paper-monitor/deploy",
                    "/api/v1/paper-monitor/organism/status",
                }:
                    raise ValueError("local_observer_routes_only")
                raw = super().get(origin, path, params)
                if path.endswith("/organism/status"):
                    self.captured_status = json.loads(raw)
                return raw

        stage = "authentication"
        token = host.observer_token(host.DEFAULT_CREDENTIALS)
        # Broker credentials are intentionally absent; the route guard above
        # also rejects any future attempt to use a broker transport route.
        transport = LocalObserverTransport("", "", token)
        stage = "runtime_verification"
        host.verify_runtime(transport, binding)
        scheduler = transport.captured_status["live_engine"]
        stage = "scheduler_not_running"
        if scheduler.get("running") is not True:
            raise ValueError("scheduler_not_running")
        stage = "engine_not_initialized"
        if scheduler["engine"].get("initialized") is not True:
            raise ValueError("engine_not_initialized")
        stage = "binding_changed"
        _, rechecked, _ = host.load_binding(host.DEFAULT_BINDING)
        if rechecked["binding_sha256"] != paths["binding_sha256"]:
            raise ValueError("binding_changed")
        result["status"] = "ok"
    except Exception:  # noqa: BLE001 - Never persist credentials or transport bodies.
        result["status"] = stage
        result["problems"] = ["policy_" + stage]
    return result


def run_watchdog(root: Path, *, recover: bool = False, reopen_docker: bool = False,
                 local_notifications: bool = False, check_backups: bool = False,
                 check_policy: bool = False) -> dict:
    logs = root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    status_path = logs / "paper_watchdog_status.json"
    previous = {}
    prior_corrupt = False
    if status_path.exists():
        try:
            previous = json.loads(status_path.read_text())
            if not isinstance(previous, dict):
                raise ValueError("invalid status")
        except (OSError, ValueError):
            prior_corrupt = True
            previous = {}
    now = time.time()
    observation = observe(now)
    paused = (logs / "paper_watchdog.pause").exists()
    result = {
        "checked_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        **observation, "healthy": not observation["problems"], "paused": paused,
        "last_recovery_at": previous.get("last_recovery_at"), "actions": [],
        "notification": {"enabled": local_notifications, "attempted": False, "delivered": False},
    }
    try:
        last_recovery = float(previous.get("last_recovery_at") or 0)
        if not math.isfinite(last_recovery):
            raise ValueError("invalid recovery time")
    except (TypeError, ValueError):
        prior_corrupt = True
        last_recovery = now
    if prior_corrupt:
        result["recovery_blocked"] = "previous_status_unreadable"
    elif now - last_recovery < COOLDOWN_SECONDS:
        result["recovery_blocked"] = "cooldown"
    elif recover and not paused:
        action = choose_recovery(observation, reopen_docker)
        if action:
            # Persist before issuing the action: a killed watchdog must not lose
            # its cooldown and repeatedly restart a slow-starting API.
            result["last_recovery_at"] = now
            result["actions"] = [{"command": action, "status": "attempting"}]
            write_json(status_path, result)
            try:
                completed = command(action, timeout=90)
                result["actions"][0]["status"] = "succeeded" if completed.returncode == 0 else "failed"
            except (OSError, subprocess.TimeoutExpired):
                result["actions"][0]["status"] = "failed"
            # Startup receives a full minute; subsequent invocations also
            # honor the persisted 15-minute cooldown.
            deadline = time.monotonic() + STARTUP_GRACE_SECONDS
            while time.monotonic() < deadline and result["actions"][0]["status"] == "succeeded":
                time.sleep(5)
                observation = observe(time.time())
                result.update(observation)
                result["healthy"] = not observation["problems"]
                if result["healthy"]:
                    break
    monitor = scan_critical_events(previous, now)
    result["critical_monitor"] = monitor
    if not monitor["available"] and result["daemon"]:
        result["problems"].append("critical_alert_monitor_unavailable")
        result["healthy"] = False
    if monitor["truncated"]:
        result["problems"].append("critical_alert_log_window_truncated")
        result["healthy"] = False
    # Backup failures are added only after service recovery decisions. They
    # share notification dedup/retry, but never start or restart a service.
    result["backup_monitor"] = observe_backups(root, now) if check_backups else {"enabled": False}
    if check_backups:
        result["problems"].extend(result["backup_monitor"]["problems"])
        result["healthy"] = not result["problems"]
    # Policy/scheduler failures use the existing attention path only. Adding
    # them after recovery decisions prevents a healthy API from being restarted
    # because its research baseline or scheduler needs operator review.
    result["policy_monitor"] = observe_policy() if check_policy else {"enabled": False}
    if check_policy:
        result["problems"].extend(result["policy_monitor"]["problems"])
        result["healthy"] = not result["problems"]
    changed = previous.get("problems") != result["problems"] or previous.get("healthy") != result["healthy"]
    pending_events = monitor.get("pending_events", monitor["new_events"])
    prior_notice = previous.get("notification") or {}
    retry_notice = isinstance(prior_notice, dict) and prior_notice.get("attempted") and not prior_notice.get("delivered")
    if local_notifications and (changed or pending_events or retry_notice) and not paused:
        if pending_events:
            message = f"Paper API logged {pending_events} critical alert(s) awaiting notification. Review application logs."
            if result["problems"]:
                message += " Other checks need attention: " + ", ".join(result["problems"])
        else:
            message = "Paper services recovered." if result["healthy"] else "Paper services need attention: " + ", ".join(result["problems"])
        result["notification"]["attempted"] = True
        result["notification"]["delivered"] = notify_local(message)
        if result["notification"]["delivered"]:
            monitor["pending_events"] = 0
    write_json(status_path, result)
    with (logs / "paper_watchdog_events.jsonl").open("a") as output:
        output.write(json.dumps(result) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--reopen-docker", action="store_true")
    parser.add_argument("--notify-local", action="store_true")
    parser.add_argument("--check-backups", action="store_true")
    parser.add_argument("--check-policy", action="store_true")
    args = parser.parse_args()
    logs = ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / "paper_watchdog.lock").open("a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Paper watchdog already running; no duplicate action.")
            return 0
        result = run_watchdog(ROOT, recover=args.recover, reopen_docker=args.reopen_docker,
                              local_notifications=args.notify_local, check_backups=args.check_backups,
                              check_policy=args.check_policy)
    print(json.dumps(result))
    return 0 if result["healthy"] or result["paused"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
