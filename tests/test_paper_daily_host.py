"""Host adapter acceptance uses the real collector with isolated, mock inputs."""
import fcntl
import json
from pathlib import Path
import plistlib
from types import SimpleNamespace

import pytest

from scripts.ops import paper_daily_host as host_runner
from scripts.ops import paper_daily_evidence as daily
from tests.test_paper_daily_evidence import DAY, NOW, FakeTransport, host  # noqa: F401


def write_json(path, value):
    path.write_bytes(daily.encoded(value))
    path.chmod(0o600)
    return {"path": str(path), "sha256": daily.digest(path.read_bytes())}


@pytest.fixture
def configured(host, tmp_path_factory, monkeypatch):  # noqa: F811 - Imported pytest fixture.
    root, freeze, activation, _ = host
    private = tmp_path_factory.mktemp("private-host-binding")
    private.chmod(0o700)
    baseline = private / "retained-baseline"
    baseline.mkdir(mode=0o700)
    ledger = (root / "organism_brain/trade_history.csv").read_bytes()
    (baseline / "trade_history.csv").write_bytes(ledger)
    write_json(baseline / "backup_manifest.json", {"files": {"trade_history.csv": {
        "sha256": daily.digest(ledger), "bytes": len(ledger)}}})
    baseline_hash = daily.digest((baseline / "backup_manifest.json").read_bytes())
    original = json.loads(activation.read_bytes())
    original["backups"] = {"brain": {"manifest_sha256": baseline_hash}}
    original_ref = write_json(private / "original-activation.json", original)
    policy = {"schema_version": 1, "policy_id": "paper_research_locked_v1",
              "runtime_identity": {"model_generation": 390, "trained": True, "ensemble_trained": True},
              "effective_policy_params": {"alpha_weight_ml": 0.35, "shorts_enabled": False}}
    policy["effective_policy_hash"] = host_runner.policy_hash(policy["effective_policy_params"])
    policy_ref = write_json(private / "policy-baseline.json", policy)
    flags = {"locked": True, "automatic_promotion_enabled": False, "frozen_models": True}
    frozen = json.loads(freeze.read_bytes())
    frozen["FROZEN_AT"] = "2026-09-21T06:45:00+00:00"
    frozen["surface"].update(effective_policy_baseline={
        "effective_policy_hash": policy["effective_policy_hash"],
        "effective_policy_params": policy["effective_policy_params"],
        "artifact_sha256": policy_ref["sha256"]}, research_policy=flags)
    frozen_ref = write_json(freeze, frozen)
    updated = {**original, "activation_timestamp_utc": frozen["FROZEN_AT"], "active_freeze_sha256": frozen_ref["sha256"]}
    updated["historical_baseline"] = {"path": str(baseline), "manifest_sha256": baseline_hash}
    updated["backups"] = {"brain": {"manifest_sha256": "f" * 64, "path": "/fresh/recovery/snapshot"}}
    activation_ref = write_json(activation, updated)
    binding = {
        "schema": host_runner.SCHEMA, "approval_reference": "Synthetic test approval; no live data",
        "approved_at": "2026-09-21T06:44:00+00:00", "measurement_cutoff": frozen["FROZEN_AT"],
        "source_sha": "a" * 40, "image_sha": "a" * 40, "image_digest": "sha256:" + "b" * 64,
        "runtime_config_hash": "c" * 16, "timeframe": "1Min", "effective_policy_hash": policy["effective_policy_hash"],
        "policy_baseline": policy_ref,
        "root": str(root), "output": str(private / "packs"), "freeze": frozen_ref,
        "activation": activation_ref, "original_activation": original_ref,
        "baseline": {"path": str(baseline), "manifest_sha256": baseline_hash},
    }
    binding_path = private / "binding.json"
    write_json(binding_path, binding)
    credentials = private / "observer.json"
    write_json(credentials, {"username": "private-observer", "password": "SECRET_PASSWORD"})
    transport = FakeTransport()
    transport.responses["/api/v1/paper-monitor/deploy"] = {
        key: binding[key] for key in ("source_sha", "image_sha", "runtime_config_hash")}
    engine = transport.responses["/api/v1/paper-monitor/organism/status"]["live_engine"]["engine"]
    engine.update(policy_lock={**flags, **policy, "baseline": {
        "configured": True, "verified": True, "sha256": policy_ref["sha256"]}},
        ml_influence_enabled=False, fixed_risk_sizing=True)
    transport.container_identity = lambda: daily.encoded({"name": "/intra-api-1", "project": "intra", "service": "api", "image_digest": binding["image_digest"]})
    monkeypatch.setattr(host_runner, "container_credentials", lambda _: ("SECRET_KEY", "SECRET_SECRET"))
    monkeypatch.setattr(host_runner, "observer_token", lambda _: "SECRET_TOKEN")
    monkeypatch.setattr(daily, "GetTransport", lambda *args: transport)
    return SimpleNamespace(binding=binding, path=binding_path, credentials=credentials,
                           transport=transport, root=root, engine=engine, private=private)


def run(configured):
    return host_runner.execute(configured.path, configured.credentials, DAY, now=NOW)


def test_real_collector_bound_to_new_cutoff_original_baseline_and_locked_policy(configured):
    before = {p: p.read_bytes() for p in (configured.root / "organism_brain").iterdir()}
    result = run(configured)
    assert result["status"] == "READY_FOR_REVIEW"
    pack = Path(result["pack"])
    inputs, collection = daily.verify_pack(pack)
    assert json.loads(inputs["local/freeze.json"])["FROZEN_AT"] == configured.binding["measurement_cutoff"]
    assert json.loads(inputs["local/release.json"])["effective_policy_hash"] == configured.binding["effective_policy_hash"]
    assert daily.analyze(inputs, collection)["status"] == "READY_FOR_REVIEW"
    activation = json.loads(inputs["local/activation.json"])
    assert activation["backups"]["brain"]["manifest_sha256"] != activation["historical_baseline"]["manifest_sha256"]
    assert before == {p: p.read_bytes() for p in before}
    assert Path(result["run_receipt"]).stat().st_mode & 0o077 == 0
    assert "SECRET_" not in json.dumps(result)


@pytest.mark.parametrize("field,value", [("source_sha", "d" * 40), ("image_sha", "d" * 40), ("runtime_config_hash", "d" * 16)])
def test_wrong_authenticated_release_blocks_before_broker_or_analysis(configured, monkeypatch, field, value):
    configured.transport.responses["/api/v1/paper-monitor/deploy"][field] = value
    monkeypatch.setattr(daily, "analyze", lambda *a: pytest.fail("unapproved identity reached analysis"))
    result = run(configured)
    assert result["reason"] == "authenticated_release_identity_mismatch"
    assert not any(call[0] == "paper" for call in configured.transport.calls)


@pytest.mark.parametrize("field,value", [("locked", False), ("automatic_promotion_enabled", True), ("frozen_models", False), ("locked", 1)])
def test_policy_flags_fail_closed(configured, monkeypatch, field, value):
    configured.engine["policy_lock"][field] = value
    monkeypatch.setattr(daily, "analyze", lambda *a: pytest.fail("unlocked policy reached analysis"))
    assert run(configured)["reason"] == "research_policy_not_locked"


def test_reported_hash_cannot_hide_changed_effective_params(configured):
    configured.engine["policy_lock"]["effective_policy_params"]["alpha_weight_ml"] = 0.9
    assert run(configured)["reason"] == "runtime_effective_policy_mismatch"


@pytest.mark.parametrize("field,value", [("configured", False), ("verified", False), ("sha256", "f" * 64), ("verified", 1)])
def test_unpinned_model_baseline_cannot_qualify(configured, field, value):
    configured.engine["policy_lock"]["baseline"][field] = value
    assert run(configured)["reason"] == "runtime_model_baseline_unverified"


def test_policy_changed_during_collection_withholds_native_gate(configured, monkeypatch):
    original = daily.collect
    def changed(*args, **kwargs):
        inputs, collection, paths = original(*args, **kwargs)
        status = json.loads(inputs["runtime/status.json"])
        status["live_engine"]["engine"]["policy_lock"]["locked"] = False
        inputs["runtime/status.json"] = daily.encoded(status)
        return inputs, collection, paths
    monkeypatch.setattr(daily, "collect", changed)
    monkeypatch.setattr(daily, "analyze", lambda *a: pytest.fail("drifted policy reached analysis"))
    result = run(configured)
    assert result["status"] == "BLOCKED" and "pack" not in result


def test_no_session_publishes_calendar_pack_and_preclose_is_blocked(configured):
    configured.transport.responses["/v2/calendar"] = []
    assert run(configured)["status"] == "NO_SESSION"
    configured.transport.responses["/v2/calendar"] = [{"date": DAY, "open": "09:30", "close": "16:00"}]
    result = host_runner.execute(configured.path, configured.credentials, DAY, now=NOW.replace(hour=19))
    assert result["reason"] == "before_authoritative_close"


@pytest.mark.parametrize("mutation", ["cutoff", "original_baseline", "freeze_bytes", "permissions", "pruned_baseline", "policy_artifact"])
def test_unapproved_binding_inputs_fail_before_credentials(configured, monkeypatch, mutation):
    if mutation == "cutoff":
        configured.binding["measurement_cutoff"] = "2026-09-20T00:00:00+00:00"
    elif mutation == "original_baseline":
        configured.binding["baseline"]["manifest_sha256"] = "e" * 64
    elif mutation == "freeze_bytes":
        Path(configured.binding["freeze"]["path"]).write_text("{}")
    elif mutation == "pruned_baseline":
        configured.binding["baseline"]["path"] = str(configured.root / "organism_brain_archive/snapshot")
    elif mutation == "policy_artifact":
        configured.binding["effective_policy_hash"] = "e" * 64
    write_json(configured.path, configured.binding)
    if mutation == "permissions":
        configured.path.chmod(0o644)
    monkeypatch.setattr(host_runner, "container_credentials", lambda *a: pytest.fail("bad binding reached credentials"))
    with pytest.raises((daily.EvidenceError, KeyError)):
        run(configured)


def test_duplicate_job_and_output_symlink_do_not_touch_brain(configured):
    output = Path(configured.binding["output"])
    output.mkdir(mode=0o700)
    with (output / ".host-run.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert run(configured)["reason"] == "host_run_already_active"
    (output / ".host-run.lock").unlink()
    output.rmdir()
    before = set((configured.root / "organism_brain").iterdir())
    output.symlink_to(configured.root / "organism_brain", target_is_directory=True)
    with pytest.raises(daily.EvidenceError):
        run(configured)
    assert set((configured.root / "organism_brain").iterdir()) == before


def test_transport_failure_is_sanitized_and_persisted(configured, monkeypatch, capsys):
    monkeypatch.setattr(host_runner, "observer_token", lambda _: (_ for _ in ()).throw(RuntimeError("SECRET_PASSWORD SECRET_BODY")))
    assert host_runner.main(["--binding", str(configured.path), "--credentials-file", str(configured.credentials), "--session", DAY]) == 1
    output = capsys.readouterr().out
    assert "SECRET" not in output
    result = json.loads(output)
    assert result["reason"] == "host_collection_failed"
    assert "SECRET" not in Path(result["run_receipt"]).read_text()


def test_credential_reader_uses_only_fixed_paper_container(monkeypatch):
    inspected = {"name": "/intra-api-1", "project": "intra", "service": "api", "running": True,
                 "image": "sha256:" + "b" * 64,
                 "environment": ["ALPACA_PAPER=true", "ALPACA_BASE_URL=https://paper-api.alpaca.markets",
                                 "ALPACA_API_KEY_ID=SECRET_KEY", "ALPACA_API_SECRET_KEY=SECRET_SECRET"]}
    def inspect(args, **kwargs):
        assert args[:3] == ["docker", "inspect", "--format"] and args[-1] == "intra-api-1"
        assert kwargs["capture_output"] is True
        return SimpleNamespace(returncode=0, stdout=daily.encoded(inspected))
    monkeypatch.setattr(host_runner.subprocess, "run", inspect)
    assert host_runner.container_credentials({"image_digest": inspected["image"]}) == ("SECRET_KEY", "SECRET_SECRET")
    inspected["environment"].append("APCA_API_BASE_URL=https://api.alpaca.markets")
    with pytest.raises(daily.EvidenceError, match="fixed_paper_mode_required"):
        host_runner.container_credentials({"image_digest": inspected["image"]})
    inspected["project"] = "other"
    with pytest.raises(daily.EvidenceError, match="paper_container_identity_mismatch"):
        host_runner.container_credentials({"image_digest": inspected["image"]})


def test_local_login_requires_private_observer_role_and_never_redirects(tmp_path, monkeypatch):
    credentials = tmp_path / "observer.json"
    write_json(credentials, {"username": "actual-monitor-account", "password": "SECRET_PASSWORD"})
    login = {"access_token": "SECRET_TOKEN", "user": {"username": "actual-monitor-account", "roles": ["paper_monitor"]}}
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit): return daily.encoded(login)
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == "http://127.0.0.1:8000/api/v1/auth/login"
            assert request.method == "POST" and timeout == 20
            return Response()
    def build(*handlers):
        assert isinstance(handlers[1], daily.NoRedirect)
        assert handlers[0].proxies == {}
        return Opener()
    monkeypatch.setattr(host_runner.urllib.request, "build_opener", build)
    assert host_runner.observer_token(credentials) == "SECRET_TOKEN"
    login["user"]["roles"] = ["admin", "paper_monitor"]
    with pytest.raises(daily.EvidenceError, match="dedicated_observer_role_required"):
        host_runner.observer_token(credentials)
    credentials.chmod(0o644)
    with pytest.raises(daily.EvidenceError, match="private_file_permissions_required"):
        host_runner.observer_token(credentials)


def test_launchd_template_has_no_secrets_or_recovery_and_runs_after_close():
    path = host_runner.ROOT / "ops/launchd/com.intra.paper.daily-evidence.plist"
    job = plistlib.loads(path.read_bytes())
    assert job["StartCalendarInterval"] == {"Hour": 13, "Minute": 10}
    assert job["RunAtLoad"] is False
    assert job["ProgramArguments"][2].endswith("scripts/ops/paper_daily_host.py")
    assert set(job["EnvironmentVariables"]) == {"PATH"}
    assert "--recover" not in job["ProgramArguments"]
