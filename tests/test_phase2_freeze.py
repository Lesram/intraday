"""Candidate surface validation is separate from active-cutoff authority.

Drift blocks candidate acceptance. Generation never activates or resets a clock;
that requires a separately approved release and an active deployment receipt.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.phase2_freeze as phase2_freeze
from scripts.phase2_freeze import (
    CANDIDATE_FREEZE_PATH, N_TARGET_RANGE, PROVENANCE, compute_surface, verify,
)


@pytest.fixture(autouse=True)
def documented_frozen_environment(monkeypatch):
    """Supply the certified deployment inputs only within this test module.

    The values are explicit, not read from the artifact being verified.  CI's
    general defaults are not the deployed paper configuration.  Production
    verification must still inspect its own actual environment.
    """
    for key in phase2_freeze.EXIT_ENV_VARS + phase2_freeze.ROUTING_DATA_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    monkeypatch.setenv("ORGANISM_MIN_AVG_DOLLAR_VOLUME", "50000")
    monkeypatch.setenv("ORGANISM_FRAMEWORK_ROUTING_V2", "true")
    monkeypatch.setenv("ORGANISM_ROUTING_RANK_POLICY", "flat_policy")
    monkeypatch.setenv("ORGANISM_APPROVED_POLICY_BASELINE", "/app/artifacts/phase2/research_policy_baseline.json")
    monkeypatch.setenv("ORGANISM_OPERATOR_CONTROL_STATE", "/app/data/operator_control_state.json")


@pytest.fixture(scope="module")
def freeze():
    if not Path(CANDIDATE_FREEZE_PATH).exists():
        pytest.fail("candidate_param_freeze.json missing — candidate evidence is required")
    return json.loads(Path(CANDIDATE_FREEZE_PATH).read_text())


def test_freeze_is_complete_and_permanent(freeze):
    # The metadata that makes the freeze a non-re-litigable fact.
    assert freeze["VALIDATED_AT"] and freeze["git_sha"]
    assert "FROZEN_AT" not in freeze
    assert freeze["candidate_only"] is True and freeze["deployment_approved"] is False
    assert N_TARGET_RANGE[0] <= freeze["n_target"] <= N_TARGET_RANGE[1]  # pinned to the prior
    # The no-provenance finding is recorded verbatim (the reason the clock is zero).
    assert freeze["provenance"] == PROVENANCE


def test_freeze_covers_full_decision_surface(freeze):
    # Gap-2: not just the four thresholds — entry direction, exits, regime, gates,
    # sizing; Phase 3 adds the selector routing path, the regime policy and the
    # routing/data env (the data feed is a first-class frozen fact — Task 0).
    sh = freeze["surface"]["source_hashes"]
    assert set(sh) == {
        "entry_direction", "exit_engine", "regime_detector",
        "kelly_sizer", "entry_gates_dispatch", "selector_routing",
    }
    assert "strategy_config" in freeze["surface"]
    assert "exit_env" in freeze["surface"]
    assert "regime_policy" in freeze["surface"]
    assert set(freeze["surface"]["data_pipeline_sources"]) == {
        "market_scanner", "streaming_data_provider", "live_engine_data",
        "staleness_admission",
    }
    assert freeze["surface"]["research_policy"]["locked"] is True
    assert freeze["surface"]["research_policy"]["qualified_trade_count"] is None
    assert set(freeze["surface"]["research_policy_sources"]) == {
        "policy", "phase", "trainer", "startup", "sync_training", "phase_resolution",
        "ml_isolation", "fixed_risk", "settings_update",
        "baseline_verification", "model_fingerprint",
        "parameter_application", "settings_api", "scheduler",
        "operator_controls", "governance", "entry_admission", "operator_api",
        "entry_frame_capture", "entry_evidence", "entry_freshness", "entry_submission",
        "emergency_stop_api", "emergency_stop_service", "entry_cancellation",
    }
    rde = freeze["surface"]["routing_data_env"]
    assert set(rde) >= {"ALPACA_DATA_FEED", "ORGANISM_MIN_AVG_DOLLAR_VOLUME",
                        "ORGANISM_FRAMEWORK_ROUTING_V2",
                        "ORGANISM_ROUTING_RANK_POLICY"}


def test_decision_surface_unchanged(freeze):
    """Candidate acceptance must detect any decision-surface drift."""
    assert compute_surface() == freeze["surface"], (
        "Candidate surface drifted: regenerate and review candidate evidence; "
        "do not modify the approved active cutoff."
    )


# ── Work order 2026-07-23, global rule #2: read-only --verify drift check ──
# Behavioral probes, not marker-greps: they exercise verify()'s return code on
# both the matching and the drifted case, and prove it never mutates the artifact.


def test_verify_mode_passes_on_unchanged_surface(freeze):
    """--verify returns 0 when the live surface still matches the freeze."""
    assert verify(candidate=True) == 0


def test_verify_mode_detects_drift_and_is_read_only(tmp_path, monkeypatch):
    """--verify returns 1 on a drifted artifact and NEVER writes to disk.

    Neither generation nor verification may re-stamp FROZEN_AT — that would silently
    reset the forward clock. We point the module at a mutated COPY and assert
    (a) it reports drift via exit code 1, and (b) the file is byte-identical
    afterwards.
    """
    real = json.loads(Path(CANDIDATE_FREEZE_PATH).read_text())
    mutated = json.loads(json.dumps(real))
    mutated["surface"]["source_hashes"]["exit_engine"] = "DELIBERATELY_WRONG_HASH"
    fake = tmp_path / "param_freeze.json"
    fake.write_text(json.dumps(mutated))
    before = fake.read_bytes()

    monkeypatch.setattr(phase2_freeze, "CANDIDATE_FREEZE_PATH", fake)
    rc = verify(candidate=True)

    assert rc == 1, "verify() must return 1 when the surface has drifted"
    assert fake.read_bytes() == before, "verify() must be read-only (no re-stamp)"


def test_verify_mode_reports_missing_artifact(tmp_path, monkeypatch):
    """--verify returns 2 (not 0) when there is no artifact to check against."""
    monkeypatch.setattr(phase2_freeze, "FREEZE_PATH", tmp_path / "does_not_exist.json")
    assert verify() == 2


def test_verify_detects_model_fingerprint_source_drift(tmp_path, monkeypatch):
    """The complete fingerprint implementation is frozen, including helpers."""
    from backend.organism import model_fingerprint

    stored = {"FROZEN_AT": "2026-09-21T10:10:39.684894+00:00",
              "surface": compute_surface()}
    artifact = tmp_path / "param_freeze.json"
    artifact.write_text(json.dumps(stored))
    before = artifact.read_bytes()
    monkeypatch.setattr(phase2_freeze, "FREEZE_PATH", artifact)
    assert verify() == 0

    original_getsource = phase2_freeze.inspect.getsource

    def changed_helper_source(obj):
        source = original_getsource(obj)
        if obj is model_fingerprint:
            return source + "\n# Simulated fingerprint helper implementation drift\n"
        return source

    monkeypatch.setattr(phase2_freeze.inspect, "getsource", changed_helper_source)
    assert verify() == 1
    current = compute_surface()
    assert current["source_hashes"] == stored["surface"]["source_hashes"]
    assert current["research_policy_sources"]["model_fingerprint"] != stored["surface"]["research_policy_sources"]["model_fingerprint"]
    assert artifact.read_bytes() == before, "source drift must not rewrite the cutoff"


def test_verify_detects_policy_unlock_without_rewriting_boundary(monkeypatch):
    from backend.organism import research_policy
    before = Path(CANDIDATE_FREEZE_PATH).read_bytes()
    monkeypatch.setattr(research_policy, "RESEARCH_POLICY_LOCKED", False)
    assert verify(candidate=True) == 1
    assert Path(CANDIDATE_FREEZE_PATH).read_bytes() == before


@pytest.mark.parametrize("key", [
    "ALPACA_DATA_FEED",
    "ORGANISM_MIN_AVG_DOLLAR_VOLUME",
    "ORGANISM_FRAMEWORK_ROUTING_V2",
    "ORGANISM_ROUTING_RANK_POLICY",
    "ORGANISM_APPROVED_POLICY_BASELINE",
    "ORGANISM_OPERATOR_CONTROL_STATE",
])
def test_verify_mode_detects_missing_deployment_env(key, monkeypatch):
    """Missing deployed inputs must still fail without changing the freeze."""
    before = Path(CANDIDATE_FREEZE_PATH).read_bytes()
    monkeypatch.delenv(key)
    assert verify(candidate=True) == 1
    assert Path(CANDIDATE_FREEZE_PATH).read_bytes() == before


@pytest.mark.parametrize("module_name", ["entry_freshness", "entry_evidence"])
def test_verify_detects_freshness_dependency_drift(tmp_path, monkeypatch, module_name):
    """Changing capture or final validation must invalidate the frozen surface."""
    import importlib
    module = importlib.import_module("backend.organism." + module_name)
    artifact = tmp_path / "param_freeze.json"
    stored = {"FROZEN_AT": "2026-09-22T00:00:00+00:00", "surface": compute_surface()}
    artifact.write_text(json.dumps(stored))
    original_bytes = artifact.read_bytes()
    monkeypatch.setattr(phase2_freeze, "FREEZE_PATH", artifact)
    assert verify() == 0
    original_getsource = phase2_freeze.inspect.getsource

    def changed_source(obj):
        source = original_getsource(obj)
        return source + "\n# changed dependency\n" if obj is module else source

    monkeypatch.setattr(phase2_freeze.inspect, "getsource", changed_source)
    assert verify() == 1
    assert artifact.read_bytes() == original_bytes


@pytest.mark.parametrize("module_name", [
    "market_scanner", "streaming_data_provider", "live_engine_data", "staleness_admission",
])
def test_pipeline_source_drift_invalidates_freeze_without_reset(tmp_path, monkeypatch, module_name):
    """Discovery/data changes must not evade the original six-function guard."""
    import importlib

    if module_name == "staleness_admission":
        from backend.organism.live_engine import OrganismLiveEngine
        module = OrganismLiveEngine._stage_update_data_staleness
    else:
        module = importlib.import_module("backend.organism." + module_name)
    artifact = tmp_path / "param_freeze.json"
    surface = compute_surface()
    artifact.write_text(json.dumps({"FROZEN_AT": "2026-09-22T08:49:11Z", "surface": surface}))
    before = artifact.read_bytes()
    monkeypatch.setattr(phase2_freeze, "FREEZE_PATH", artifact)
    assert verify() == 0
    original_getsource = phase2_freeze.inspect.getsource

    def changed_source(obj):
        source = original_getsource(obj)
        return source + "\n# changed upstream decision dependency\n" if obj is module else source

    monkeypatch.setattr(phase2_freeze.inspect, "getsource", changed_source)
    assert verify() == 1
    changed = compute_surface()
    assert changed["source_hashes"] == surface["source_hashes"]
    assert changed["data_pipeline_sources"][module_name] != surface["data_pipeline_sources"][module_name]
    assert artifact.read_bytes() == before


@pytest.fixture
def isolated_references(tmp_path, monkeypatch):
    active = tmp_path / "active.json"
    candidate = tmp_path / "candidate.json"
    active.write_text(json.dumps({"FROZEN_AT": "2026-09-22T08:49:11Z", "surface": {"v": 1}}))
    monkeypatch.setattr(phase2_freeze, "FREEZE_PATH", active)
    monkeypatch.setattr(phase2_freeze, "CANDIDATE_FREEZE_PATH", candidate)
    monkeypatch.setattr(phase2_freeze, "compute_surface", lambda: {"source_hashes": {}, "v": 2})
    monkeypatch.setattr(phase2_freeze, "_git_sha", lambda: "test-source")
    return active, candidate


def test_default_generation_never_activates_or_overwrites_cutoff(isolated_references):
    active, candidate = isolated_references
    before = active.read_bytes()
    assert phase2_freeze.main([]) == 0
    generated = json.loads(candidate.read_text())
    assert generated["candidate_only"] is True
    assert generated["deployment_approved"] is False
    assert generated["active_forward_cutoff"] == "2026-09-22T08:49:11Z"
    assert "FROZEN_AT" not in generated
    assert phase2_freeze.verify(candidate=True) == 0
    assert phase2_freeze.verify() == 1
    assert active.read_bytes() == before
    # Repeated unchanged generation preserves validation time, not active authority.
    assert phase2_freeze.main([]) == 0
    assert json.loads(candidate.read_text())["VALIDATED_AT"] == generated["VALIDATED_AT"]
    assert active.read_bytes() == before


def test_drifted_generation_retains_candidate_flags(isolated_references, monkeypatch):
    active, candidate = isolated_references
    before = active.read_bytes()
    assert phase2_freeze.main([]) == 0
    monkeypatch.setattr(phase2_freeze, "compute_surface", lambda: {"source_hashes": {}, "v": 3})
    assert phase2_freeze.verify(candidate=True) == 1
    assert phase2_freeze.main([]) == 0
    generated = json.loads(candidate.read_text())
    assert generated["surface"]["v"] == 3
    assert generated["candidate_only"] is True and generated["deployment_approved"] is False
    assert "FROZEN_AT" not in generated
    assert active.read_bytes() == before


@pytest.mark.parametrize("flags", [
    {"candidate_only": True}, {"deployment_approved": False},
    {"candidate_only": "false"}, {"deployment_approved": 1},
])
def test_nonactive_canonical_cannot_be_laundered_by_generation(isolated_references, flags):
    active, candidate = isolated_references
    record = json.loads(active.read_text())
    record.update(flags)
    active.write_text(json.dumps(record))
    before = active.read_bytes()
    assert phase2_freeze.main([]) == 2
    assert phase2_freeze.verify() == 2
    assert active.read_bytes() == before
    assert not candidate.exists()


@pytest.mark.parametrize("mutation", [
    {"VALIDATED_AT": "2026-09-23T07:00:00"}, {"VALIDATED_AT": "invalid"},
    {"candidate_only": False}, {"candidate_only": 1},
    {"deployment_approved": True}, {"deployment_approved": 0},
    {"FROZEN_AT": "2026-09-23T07:00:00Z"}, {"surface": []},
])
def test_invalid_candidate_neither_verifies_nor_regenerates(isolated_references, mutation):
    active, candidate = isolated_references
    assert phase2_freeze.main([]) == 0
    record = json.loads(candidate.read_text())
    record.update(mutation)
    candidate.write_text(json.dumps(record))
    before = active.read_bytes(), candidate.read_bytes()
    assert phase2_freeze.verify(candidate=True) == 2
    assert phase2_freeze.main([]) == 2
    assert (active.read_bytes(), candidate.read_bytes()) == before


def test_candidate_cannot_share_active_destination(isolated_references, monkeypatch):
    active, _ = isolated_references
    before = active.read_bytes()
    monkeypatch.setattr(phase2_freeze, "CANDIDATE_FREEZE_PATH", active)
    assert phase2_freeze.main([]) == 2
    assert active.read_bytes() == before


def test_absent_active_reference_generates_only_nonactive_candidate(isolated_references):
    active, candidate = isolated_references
    active.unlink()
    assert phase2_freeze.main([]) == 0
    record = json.loads(candidate.read_text())
    assert record["active_forward_cutoff"] is None
    assert "FROZEN_AT" not in record
    assert not active.exists()
    assert phase2_freeze.verify() == 2
