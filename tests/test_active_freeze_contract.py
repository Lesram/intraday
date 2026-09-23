"""Candidate verification times must never become active reporting cutoffs."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from backend.organism.freeze_contract import load_active_freeze, validate_active_freeze
from scripts import phase2_gate, phase3_attribution_report
from scripts.ops import paper_daily_evidence as daily
from scripts.ops import paper_daily_host as host_runner
from scripts.research import paper_fill_reconciliation as fills
from tests.test_paper_daily_evidence import DAY, NOW, FakeTransport, host, run_host  # noqa: F401
from tests.test_paper_daily_host import configured, write_json  # noqa: F401

CUTOFF = "2026-09-22T08:49:11.247316+00:00"
REJECTED_FLAGS = [
    {"candidate_only": True},
    {"deployment_approved": False},
    {"candidate_only": True, "deployment_approved": True},
    {"candidate_only": "false"},
    {"deployment_approved": "true"},
]


@pytest.mark.parametrize("flags", [
    {}, {"candidate_only": False}, {"deployment_approved": True},
    {"candidate_only": False, "deployment_approved": True},
])
@pytest.mark.parametrize("cutoff", [CUTOFF, "2026-09-22T08:49:11Z", "2026-09-22T01:49:11-07:00"])
def test_legacy_and_explicit_active_cutoffs_are_not_rewritten(flags, cutoff, tmp_path):
    value = {"FROZEN_AT": cutoff, "active_forward_cutoff": "untrusted alternate", **flags}
    before = copy.deepcopy(value)
    assert validate_active_freeze(value) == before
    assert value == before
    path = tmp_path / "active.json"
    path.write_text(json.dumps(value))
    raw = path.read_bytes()
    assert load_active_freeze(path) == before
    assert path.read_bytes() == raw


@pytest.mark.parametrize("payload", [None, [], "2026-09-22T00:00Z", 1, True, {}])
def test_non_object_or_missing_cutoff_refused(payload):
    with pytest.raises(ValueError, match="invalid_active_freeze"):
        validate_active_freeze(payload)


@pytest.mark.parametrize("flag", ["candidate_only", "deployment_approved"])
@pytest.mark.parametrize("value", [None, 0, 1, "true", "false", [], {}])
def test_boolean_flags_are_not_coerced(flag, value):
    with pytest.raises(ValueError, match="invalid_active_freeze_flags"):
        validate_active_freeze({"FROZEN_AT": CUTOFF, flag: value})


@pytest.mark.parametrize("flags", REJECTED_FLAGS)
def test_candidate_never_falls_back_to_an_old_active_cutoff(flags):
    with pytest.raises(ValueError):
        validate_active_freeze({"FROZEN_AT": CUTOFF, "active_forward_cutoff": "2026-01-01T00:00:00Z", **flags})


@pytest.mark.parametrize("cutoff", [None, 1, True, "", "SECRET-invalid-date", "NaT", "2026-09-22", "2026-09-22T08:49:11", "2026-09-22T08:49:11+99:00"])
def test_cutoff_requires_a_valid_aware_timestamp(cutoff):
    with pytest.raises(ValueError, match="invalid_active_freeze_cutoff") as caught:
        validate_active_freeze({"FROZEN_AT": cutoff})
    assert "SECRET" not in str(caught.value)


@pytest.mark.parametrize("content", [b"{SECRET", b"\xff", b"null", b"[]", b'{"FROZEN_AT":null}'])
def test_bad_file_inputs_are_sanitized_and_unchanged(tmp_path, content):
    path = tmp_path / "freeze.json"
    path.write_bytes(content)
    with pytest.raises(ValueError) as caught:
        load_active_freeze(path)
    assert "SECRET" not in str(caught.value)
    assert path.read_bytes() == content


def test_missing_or_directory_file_refused(tmp_path):
    for path in (tmp_path / "missing.json", tmp_path):
        with pytest.raises(ValueError, match="invalid_or_unavailable_active_freeze"):
            load_active_freeze(path)


@pytest.mark.parametrize("module", [phase2_gate, phase3_attribution_report])
@pytest.mark.parametrize("flags", REJECTED_FLAGS)
def test_native_clis_refuse_before_any_history_read(tmp_path, monkeypatch, capsys, module, flags):
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps({"FROZEN_AT": CUTOFF, **flags}))
    before = path.read_bytes()
    monkeypatch.setattr(module, "FREEZE", path)

    class UnreadHistory:
        def exists(self):
            pytest.fail("invalid cutoff must be rejected before touching history")

    monkeypatch.setattr(module, "TRADES", UnreadHistory())
    monkeypatch.setattr(module, "load_forward_corpus", lambda *a: pytest.fail("candidate reached corpus"))
    assert module.main() == 2
    output = capsys.readouterr().out
    assert "approved active cutoff is required" in output
    assert "forward trades=" not in output and "CAPITAL" not in output and "state=" not in output
    assert path.read_bytes() == before


@pytest.mark.parametrize("flags", REJECTED_FLAGS[:3])
def test_reconciliation_cli_refuses_before_broker_or_ledger_reads(tmp_path, monkeypatch, capsys, flags):
    freeze = tmp_path / "candidate.json"
    freeze.write_text(json.dumps({"FROZEN_AT": CUTOFF, **flags}))
    orders, ledger, output = [tmp_path / name for name in ("orders.json", "ledger.csv", "report.json")]
    original = Path.read_bytes

    def read_checked(path):
        assert path not in (orders, ledger), "candidate must not select a reconciliation cohort"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read_checked)
    assert fills.main(["--orders", str(orders), "--ledger", str(ledger), "--freeze", str(freeze),
                       "--output", str(output)]) == 2
    assert "validation failed" in capsys.readouterr().out
    assert not output.exists()


@pytest.mark.parametrize("flags", REJECTED_FLAGS[:3])
def test_collector_refuses_before_network_container_or_history(host, monkeypatch, flags):  # noqa: F811
    root, freeze, activation, release = host
    value = json.loads(freeze.read_bytes()) | flags
    freeze.write_bytes(daily.encoded(value))
    before = {p: p.read_bytes() for p in (root / "organism_brain").iterdir()}
    monkeypatch.setattr(daily, "capture_local", lambda *a, **k: pytest.fail("candidate reached history capture"))
    transport = FakeTransport()
    transport.container_identity = lambda: pytest.fail("candidate reached container inspection")
    inputs, collection, _ = daily.collect(root, freeze, activation, release, None, DAY, transport, now=NOW)
    assert collection["issues"] == ["collection_input_failure"]
    assert transport.calls == [] and collection["requests"] == []
    assert inputs["local/freeze.json"] == freeze.read_bytes()
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("flags", REJECTED_FLAGS[:3])
def test_coherent_candidate_pack_is_blocked_before_ledger_or_gate(host, monkeypatch, tmp_path, flags):  # noqa: F811
    inputs, collection, paths = run_host(host)
    assert daily.analyze(inputs, collection)["status"] == "READY_FOR_REVIEW"
    inputs["local/freeze.json"] = daily.encoded(json.loads(inputs["local/freeze.json"]) | flags)
    activation = json.loads(inputs["local/activation.json"])
    activation["active_freeze_sha256"] = daily.digest(inputs["local/freeze.json"])
    inputs["local/activation.json"] = daily.encoded(activation)
    monkeypatch.setattr(daily, "rows_from", lambda *a: pytest.fail("candidate reached ledger parsing"))
    gate = lambda *a: pytest.fail("candidate reached verdict")
    report = daily.analyze(inputs, collection, gate_fn=gate)
    assert report["status"] == "BLOCKED"
    assert report["strategy_gate"] == {"state": "WITHHELD", "reason": "evidence_quality"}
    assert "missing_or_invalid_analysis_input" in report["issues"]
    pack = daily.publish(tmp_path / "packs", inputs, collection, report, paths, [host[0] / "organism_brain"])
    replay_inputs, replay_collection = daily.verify_pack(pack)
    assert daily.analyze(replay_inputs, replay_collection, gate_fn=gate)["status"] == "BLOCKED"


@pytest.mark.parametrize("flags", REJECTED_FLAGS[:3])
def test_bound_candidate_refused_before_authentication_even_with_matching_hashes(configured, monkeypatch, flags):  # noqa: F811
    freeze = Path(configured.binding["freeze"]["path"])
    configured.binding["freeze"] = write_json(freeze, json.loads(freeze.read_bytes()) | flags)
    activation = Path(configured.binding["activation"]["path"])
    active = json.loads(activation.read_bytes())
    active["active_freeze_sha256"] = configured.binding["freeze"]["sha256"]
    configured.binding["activation"] = write_json(activation, active)
    write_json(configured.path, configured.binding)
    monkeypatch.setattr(host_runner, "container_credentials", lambda *a: pytest.fail("candidate reached credentials"))
    monkeypatch.setattr(host_runner, "observer_token", lambda *a: pytest.fail("candidate reached login"))
    with pytest.raises(ValueError, match="nonactive_freeze"):
        host_runner.execute(configured.path, configured.credentials, DAY, now=NOW)
    assert configured.transport.calls == []


def test_legacy_no_session_replay_without_freeze_is_not_a_gate_claim(host):  # noqa: F811
    inputs, collection, _ = run_host(host, FakeTransport(calendar=[]))
    inputs.pop("local/freeze.json")  # Historical NO_SESSION packs omitted it.
    report = daily.analyze(inputs, collection, gate_fn=lambda *a: pytest.fail("no session cannot run gate"))
    assert report["status"] == "NO_SESSION"
    assert report["strategy_gate"]["state"] == "WITHHELD"
    assert report["promotion_authorized"] is False
