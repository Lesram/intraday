"""Phase 2 PRECONDITION — Task 0 acceptance: the freeze is complete and the FULL
decision surface is unchanged since FROZEN_AT.

If `test_decision_surface_unchanged` goes RED, that is NOT a flaky test — it is the
designed signal that a param affecting which trades happen / how they resolve has
changed, so the forward corpus is contaminated. The fix is: re-run
`scripts/phase2_freeze.py` (which re-stamps FROZEN_AT) and RESET the accumulation
clock. Do not silence it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.phase2_freeze as phase2_freeze
from scripts.phase2_freeze import (
    FREEZE_PATH, N_TARGET_RANGE, PROVENANCE, compute_surface, verify,
)


@pytest.fixture(scope="module")
def freeze():
    if not Path(FREEZE_PATH).exists():
        pytest.skip("param_freeze.json not present — run scripts/phase2_freeze.py")
    return json.loads(Path(FREEZE_PATH).read_text())


def test_freeze_is_complete_and_permanent(freeze):
    # The metadata that makes the freeze a non-re-litigable fact.
    assert freeze["FROZEN_AT"] and freeze["git_sha"]
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
    rde = freeze["surface"]["routing_data_env"]
    assert set(rde) >= {"ALPACA_DATA_FEED", "ORGANISM_MIN_AVG_DOLLAR_VOLUME",
                        "ORGANISM_FRAMEWORK_ROUTING_V2",
                        "ORGANISM_ROUTING_RANK_POLICY"}


def test_decision_surface_unchanged(freeze):
    """Drift ANYWHERE in the surface ⇒ fail ⇒ the clock must reset."""
    current = compute_surface()
    assert current == freeze["surface"], (
        "DECISION-SURFACE DRIFT since FROZEN_AT — the forward corpus is "
        "contaminated. Re-run scripts/phase2_freeze.py to re-stamp FROZEN_AT and "
        "RESET the accumulation clock. (This is the designed reset signal, not a "
        "flake.)"
    )


# ── Work order 2026-07-23, global rule #2: read-only --verify drift check ──
# Behavioral probes, not marker-greps: they exercise verify()'s return code on
# both the matching and the drifted case, and prove it never mutates the artifact.


def test_verify_mode_passes_on_unchanged_surface(freeze):
    """--verify returns 0 when the live surface still matches the freeze."""
    assert verify() == 0


def test_verify_mode_detects_drift_and_is_read_only(tmp_path, monkeypatch):
    """--verify returns 1 on a drifted artifact and NEVER writes to disk.

    Unlike main(), verify() must not re-stamp FROZEN_AT — that would silently
    reset the forward clock. We point the module at a mutated COPY and assert
    (a) it reports drift via exit code 1, and (b) the file is byte-identical
    afterwards.
    """
    real = json.loads(Path(FREEZE_PATH).read_text())
    mutated = json.loads(json.dumps(real))
    mutated["surface"]["source_hashes"]["exit_engine"] = "DELIBERATELY_WRONG_HASH"
    fake = tmp_path / "param_freeze.json"
    fake.write_text(json.dumps(mutated))
    before = fake.read_bytes()

    monkeypatch.setattr(phase2_freeze, "FREEZE_PATH", fake)
    rc = verify()

    assert rc == 1, "verify() must return 1 when the surface has drifted"
    assert fake.read_bytes() == before, "verify() must be read-only (no re-stamp)"


def test_verify_mode_reports_missing_artifact(tmp_path, monkeypatch):
    """--verify returns 2 (not 0) when there is no artifact to check against."""
    monkeypatch.setattr(phase2_freeze, "FREEZE_PATH", tmp_path / "does_not_exist.json")
    assert verify() == 2
