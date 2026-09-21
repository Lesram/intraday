#!/usr/bin/env python3
"""Private host credential adapter for the read-only paper evidence collector.

Only local observer authentication uses POST. Broker access remains GET-only.
No deployment, recovery, notification, model loading, or scheduler installation.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.ops import paper_daily_evidence as daily

PRIVATE = Path.home() / "Library/Application Support/Intra"
DEFAULT_BINDING = PRIVATE / "daily-evidence-binding.json"
DEFAULT_CREDENTIALS = PRIVATE / "paper-observer.json"
SCHEMA = "paper_daily_host_v1"


def private_json(path: Path) -> tuple[dict, bytes]:
    raw = daily.stable_read(path)
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise daily.EvidenceError("private_file_permissions_required")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise daily.EvidenceError("invalid_private_document")
    return value, raw


def absolute_path(value) -> Path:
    if not isinstance(value, str) or not value:
        raise daily.EvidenceError("absolute_path_required")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise daily.EvidenceError("absolute_path_required")
    return path


def pinned_json(reference: dict) -> tuple[dict, bytes, Path]:
    path = absolute_path(reference["path"])
    raw = daily.stable_read(path)
    if daily.digest(raw) != reference["sha256"]:
        raise daily.EvidenceError("binding_input_checksum_mismatch")
    return json.loads(raw), raw, path


def load_binding(path: Path) -> tuple[dict, dict, list[Path]]:
    binding, raw = private_json(path)
    if binding.get("schema") != SCHEMA or not binding.get("approval_reference"):
        raise daily.EvidenceError("reviewed_binding_required")
    daily.timestamp(binding["approved_at"])
    for key in ("source_sha", "image_sha"):
        if not re.fullmatch(r"[a-f0-9]{40}", str(binding.get(key, ""))):
            raise daily.EvidenceError("invalid_release_identity")
    if (not re.fullmatch(r"sha256:[a-f0-9]{64}", str(binding.get("image_digest", "")))
            or not re.fullmatch(r"[a-f0-9]{16,64}", str(binding.get("runtime_config_hash", "")))
            or not isinstance(binding.get("timeframe"), str) or not binding["timeframe"]):
        raise daily.EvidenceError("invalid_release_identity")
    if not re.fullmatch(r"[a-f0-9]{64}", str(binding.get("effective_policy_hash", ""))):
        raise daily.EvidenceError("invalid_effective_policy_identity")
    root, output = absolute_path(binding["root"]), absolute_path(binding["output"])
    freeze, freeze_raw, freeze_path = pinned_json(binding["freeze"])
    activation, _, activation_path = pinned_json(binding["activation"])
    original, _, original_path = pinned_json(binding["original_activation"])
    policy, _, policy_path = pinned_json(binding["policy_baseline"])
    frozen_baseline = freeze["surface"]["effective_policy_baseline"]
    if (type(policy.get("schema_version")) is not int or policy["schema_version"] != 1
            or policy.get("policy_id") != "paper_research_locked_v1"
            or not isinstance(policy.get("runtime_identity"), dict)
            or policy.get("effective_policy_hash") != binding["effective_policy_hash"]
            or policy_hash(policy.get("effective_policy_params")) != binding["effective_policy_hash"]
            or frozen_baseline.get("effective_policy_hash") != binding["effective_policy_hash"]
            or frozen_baseline.get("effective_policy_params") != policy["effective_policy_params"]
            or frozen_baseline.get("artifact_sha256") != binding["policy_baseline"]["sha256"]):
        raise daily.EvidenceError("approved_policy_baseline_mismatch")
    verify_policy_flags(freeze["surface"]["research_policy"])
    if (binding.get("operator_control_path") != "/app/data/operator_control_state.json"
            or freeze["surface"]["research_policy_enforcement_env"].get(
                "ORGANISM_OPERATOR_CONTROL_STATE") != binding["operator_control_path"]):
        raise daily.EvidenceError("approved_operator_control_path_required")
    cutoff = binding["measurement_cutoff"]
    if (freeze["FROZEN_AT"] != cutoff or activation["activation_timestamp_utc"] != cutoff
            or activation["active_freeze_sha256"] != daily.digest(freeze_raw)
            or daily.timestamp(cutoff) < daily.timestamp(original["activation_timestamp_utc"])):
        raise daily.EvidenceError("approved_cutoff_binding_mismatch")
    before = activation["broker_before_transition"]
    if (before.get("paper_endpoint_verified") is not True or before.get("positions") != 0
            or before.get("open_orders") != 0):
        raise daily.EvidenceError("approved_cutoff_not_verified_flat")
    baseline = absolute_path(binding["baseline"]["path"])
    # The original archive is automatically pruned. Require a retained private
    # copy outside the operating checkout and its archive tree.
    if (baseline.resolve().is_relative_to(root.resolve())
            or "organism_brain_archive" in baseline.parts):
        raise daily.EvidenceError("baseline_must_be_retained_outside_pruned_tree")
    baseline_info = baseline.stat()
    if baseline_info.st_uid != os.getuid() or stat.S_IMODE(baseline_info.st_mode) & 0o077:
        raise daily.EvidenceError("private_baseline_directory_required")
    baseline_raw = daily.stable_read(baseline / "backup_manifest.json")
    baseline_hash = daily.digest(baseline_raw)
    if any(value != baseline_hash for value in (
            binding["baseline"]["manifest_sha256"],
            daily.historical_baseline_reference(original)["manifest_sha256"],
            daily.historical_baseline_reference(activation)["manifest_sha256"])):
        raise daily.EvidenceError("original_baseline_binding_mismatch")
    ledger = daily.stable_read(baseline / "trade_history.csv")
    expected = json.loads(baseline_raw)["files"]["trade_history.csv"]
    if daily.digest(ledger) != expected["sha256"] or len(ledger) != expected["bytes"]:
        raise daily.EvidenceError("retained_baseline_ledger_checksum")
    files = [path, freeze_path, activation_path, original_path, policy_path, baseline / "backup_manifest.json",
             baseline / "trade_history.csv"]
    daily.safe_output(output, files, [root / "organism_brain", baseline])
    paths = {"root": root, "output": output, "freeze": freeze_path, "activation": activation_path,
             "baseline": baseline, "binding_sha256": daily.digest(raw)}
    return binding, paths, files


def container_credentials(binding: dict) -> tuple[str, str]:
    # Credentials are captured only inside this process, never in argv, logs,
    # artifacts or a child's environment. No container command is executed.
    template = ('{"name":{{json .Name}},"image":{{json .Image}},"running":{{json .State.Running}},'
                '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
                '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
                '"environment":{{json .Config.Env}}}')
    result = subprocess.run(["docker", "inspect", "--format", template, "intra-api-1"],
                            capture_output=True, timeout=10, check=False)
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise daily.EvidenceError("paper_container_unavailable")
    container = json.loads(result.stdout)
    if ((container.get("name"), container.get("project"), container.get("service"))
            != ("/intra-api-1", "intra", "api") or container.get("running") is not True
            or container.get("image") != binding["image_digest"]):
        raise daily.EvidenceError("paper_container_identity_mismatch")
    env = {}
    for item in container["environment"]:
        key, value = item.split("=", 1)
        if key in env:
            raise daily.EvidenceError("ambiguous_container_environment")
        env[key] = value
    bases = [env[key].rstrip("/") for key in ("ALPACA_BASE_URL", "APCA_API_BASE_URL") if env.get(key)]
    if env.get("ALPACA_PAPER", "").lower() != "true" or not bases or any(base != daily.PAPER_BASE for base in bases):
        raise daily.EvidenceError("fixed_paper_mode_required")
    key = env.get("ALPACA_API_KEY_ID") or env.get("ALPACA_API_KEY")
    secret = env.get("ALPACA_API_SECRET_KEY") or env.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise daily.EvidenceError("paper_credentials_missing")
    return key, secret


def observer_token(credentials_path: Path) -> str:
    credentials, _ = private_json(credentials_path)
    if any(not isinstance(credentials.get(key), str) or not credentials[key] for key in ("username", "password")):
        raise daily.EvidenceError("dedicated_observer_credentials_required")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), daily.NoRedirect())
    request = urllib.request.Request(daily.LOCAL_BASE + "/api/v1/auth/login",
                                     data=daily.encoded({"username": credentials["username"],
                                                         "password": credentials["password"]}),
                                     headers={"Content-Type": "application/json"}, method="POST")
    with opener.open(request, timeout=20) as response:
        if response.status != 200:
            raise daily.EvidenceError("observer_authentication_failed")
        raw = response.read(65537)
    if len(raw) > 65536:
        raise daily.EvidenceError("observer_response_size_limit")
    login = json.loads(raw)
    user = login.get("user") or {}
    if user.get("username") != credentials["username"] or user.get("roles") != ["paper_monitor"]:
        raise daily.EvidenceError("dedicated_observer_role_required")
    token = login.get("access_token")
    if not isinstance(token, str) or not token:
        raise daily.EvidenceError("observer_token_missing")
    return token


def policy_hash(params: dict) -> str:
    if not isinstance(params, dict) or not params:
        raise daily.EvidenceError("effective_policy_params_missing")
    return daily.digest(json.dumps(params, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def verify_policy_flags(policy: dict) -> None:
    if (policy.get("locked") is not True or policy.get("automatic_promotion_enabled") is not False
            or policy.get("frozen_models") is not True):
        raise daily.EvidenceError("research_policy_not_locked")


def verify_policy_status(status: dict, binding: dict) -> None:
    engine = status["live_engine"]["engine"]
    policy = engine["policy_lock"]
    verify_policy_flags(policy)
    baseline = policy.get("baseline") or {}
    if (baseline.get("configured") is not True or baseline.get("verified") is not True
            or baseline.get("sha256") != binding["policy_baseline"]["sha256"]):
        raise daily.EvidenceError("runtime_model_baseline_unverified")
    if (policy.get("effective_policy_hash") != binding["effective_policy_hash"]
            or policy_hash(policy.get("effective_policy_params")) != binding["effective_policy_hash"]):
        raise daily.EvidenceError("runtime_effective_policy_mismatch")
    if engine.get("ml_influence_enabled") is not False or engine.get("fixed_risk_sizing") is not True:
        raise daily.EvidenceError("runtime_risk_mode_mismatch")
    governance = engine.get("governance") or {}
    control = governance.get("operator_control") or {}
    if (control.get("configured") is not True or control.get("persistence") != "verified"
            or control.get("path") != binding["operator_control_path"]
            or governance.get("operator_control_fault") is not False
            or type(governance.get("operator_halted")) is not bool):
        raise daily.EvidenceError("runtime_operator_control_unverified")
    # A manual halt is valid. Verify its current durable record instead of
    # pinning the initial (mutable) latch or requiring it to remain resumed.
    raw = daily.stable_read(Path(binding["root"]) / "data/operator_control_state.json")
    record = json.loads(raw)
    payload = {key: value for key, value in record.items() if key != "checksum"}
    if (set(payload) != {"schema", "operator_halted", "reason", "changed_at"}
            or payload.get("schema") != "intra_operator_controls_v1"
            or type(payload.get("operator_halted")) is not bool
            or not isinstance(payload.get("reason"), str) or not payload["reason"]
            or record.get("checksum") != policy_hash(payload)
            or any(record.get(key) != control.get(key) for key in ("checksum", "changed_at", "reason"))
            or payload["operator_halted"] != governance["operator_halted"]):
        raise daily.EvidenceError("operator_control_record_mismatch")
    daily.timestamp(payload["changed_at"])


def verify_runtime(transport, binding: dict) -> None:
    deployment = json.loads(transport.get("local", "/api/v1/paper-monitor/deploy", {}))
    if any(deployment.get(key) != binding[key] for key in ("source_sha", "image_sha", "runtime_config_hash")):
        raise daily.EvidenceError("authenticated_release_identity_mismatch")
    container = json.loads(transport.container_identity())
    if ((container.get("name"), container.get("project"), container.get("service"))
            != ("/intra-api-1", "intra", "api") or container.get("image_digest") != binding["image_digest"]):
        raise daily.EvidenceError("paper_container_identity_changed")
    status = json.loads(transport.get("local", "/api/v1/paper-monitor/organism/status", {}))
    verify_policy_status(status, binding)


def execute(binding_path: Path, credentials_path: Path, day: str | None = None,
            *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    day = day or now.astimezone(daily.ET).date().isoformat()
    binding, paths, files = load_binding(binding_path)
    daily.safe_output(paths["output"], files + [credentials_path], [paths["root"] / "organism_brain", paths["baseline"]])
    anchor = os.open(paths["output"].anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    output_fd = lock_fd = None
    try:
        output_fd = daily.open_directories(anchor, paths["output"].parts[1:], create=True)
        output_info = os.fstat(output_fd)
        if output_info.st_uid != os.getuid() or stat.S_IMODE(output_info.st_mode) & 0o077:
            raise daily.EvidenceError("private_output_directory_required")
        lock_fd = os.open(".host-run.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK,
                          0o600, dir_fd=output_fd)
        lock_info = os.fstat(lock_fd)
        if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_nlink != 1:
            raise daily.EvidenceError("unsafe_run_lock")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"status": "BLOCKED", "reason": "host_run_already_active", "session_date": day}
        result = {"session_date": day, "observed_at": now.isoformat(),
                  "binding_sha256": paths["binding_sha256"], "broker_mutations": False}
        try:
            key, secret = container_credentials(binding)
            token = observer_token(credentials_path)
            transport = daily.GetTransport(key, secret, token)
            verify_runtime(transport, binding)
            calendar = json.loads(transport.get("paper", "/v2/calendar", {"start": day, "end": day}))
            session = daily.calendar_session(day, calendar, now)
            if session["state"] == "BEFORE_CLOSE":
                raise daily.EvidenceError("before_authoritative_close")
            inputs, collection, captured_paths = daily.collect(
                paths["root"], paths["freeze"], paths["activation"], binding_path, paths["baseline"],
                day, transport, now=now, log_timezone=binding.get("log_timezone"))
            # The binding and its inputs must remain the exact approved bytes
            # across authentication/collection; a replacement cannot bless a run.
            _, rechecked, _ = load_binding(binding_path)
            if rechecked["binding_sha256"] != paths["binding_sha256"]:
                raise daily.EvidenceError("binding_changed_during_run")
            if "runtime/status.json" in inputs:
                verify_policy_status(json.loads(inputs["runtime/status.json"]), binding)
            report = daily.analyze(inputs, collection)
            pack = daily.publish(paths["output"], inputs, collection, report,
                                 captured_paths + files, [paths["root"] / "organism_brain", paths["baseline"]])
            result.update(status=report["status"], pack=str(pack), issues=report["issues"])
        except daily.EvidenceError as exc:
            result.update(status="BLOCKED", reason=str(exc))
        except Exception:  # noqa: BLE001 - Never disclose private transport bodies or credentials.
            result.update(status="BLOCKED", reason="host_collection_failed")
        receipt = Path("host-runs") / (now.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex + ".json")
        daily.durable_write_at(output_fd, receipt, daily.encoded(result))
        result["run_receipt"] = str(paths["output"] / receipt)
        return result
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        if output_fd is not None:
            os.close(output_fd)
        os.close(anchor)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", type=Path, default=DEFAULT_BINDING)
    parser.add_argument("--credentials-file", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--session", help="Default: today's US Eastern calendar date")
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        result = execute(args.binding, args.credentials_file, args.session)
    except Exception:  # noqa: BLE001 - Invalid binding has no trusted output destination yet.
        result = {"status": "BLOCKED", "reason": "invalid_or_unavailable_private_binding"}
    print(json.dumps(result))
    return 0 if result["status"] in {"READY_FOR_REVIEW", "NO_SESSION"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
