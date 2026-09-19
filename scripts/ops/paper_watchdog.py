"""Bounded local paper-service recovery. Never recreates containers or config."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import re
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
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/readyz", timeout=5) as response:
            readiness = json.load(response)
        result["readiness"] = {"status": readiness.get("status"), "reachable": True}
        if readiness.get("status") != "ready":
            result["problems"].append("api_not_ready")
    except urllib.error.HTTPError:
        # A responding readiness endpoint can report an upstream broker failure.
        # Restarting the API would not fix that and could disturb paper state.
        result["readiness"] = {"status": "not_ready", "reachable": True}
        result["problems"].append("api_not_ready")
    except (OSError, ValueError, TypeError, AttributeError):
        result["readiness"] = {"status": "unreachable", "reachable": False}
        result["problems"].append("api_readiness_unreachable")
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


def run_watchdog(root: Path, *, recover: bool = False, reopen_docker: bool = False,
                 local_notifications: bool = False) -> dict:
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
    changed = previous.get("problems") != result["problems"] or previous.get("healthy") != result["healthy"]
    pending_events = monitor.get("pending_events", monitor["new_events"])
    prior_notice = previous.get("notification") or {}
    retry_notice = isinstance(prior_notice, dict) and prior_notice.get("attempted") and not prior_notice.get("delivered")
    if local_notifications and (changed or pending_events or retry_notice) and not paused:
        if pending_events:
            message = f"Paper API logged {pending_events} critical alert(s) awaiting notification. Review application logs."
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
                              local_notifications=args.notify_local)
    print(json.dumps(result))
    return 0 if result["healthy"] or result["paused"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
