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

from scripts.phase2_freeze import (
    FREEZE_PATH, N_TARGET_RANGE, PROVENANCE, compute_surface,
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
    # Gap-2: not just the four thresholds — entry direction, exits, regime, gates, sizing.
    sh = freeze["surface"]["source_hashes"]
    assert set(sh) == {
        "entry_direction", "exit_engine", "regime_detector",
        "kelly_sizer", "entry_gates_dispatch",
    }
    assert "strategy_config" in freeze["surface"]
    assert "exit_env" in freeze["surface"]


def test_decision_surface_unchanged(freeze):
    """Drift ANYWHERE in the surface ⇒ fail ⇒ the clock must reset."""
    current = compute_surface()
    assert current == freeze["surface"], (
        "DECISION-SURFACE DRIFT since FROZEN_AT — the forward corpus is "
        "contaminated. Re-run scripts/phase2_freeze.py to re-stamp FROZEN_AT and "
        "RESET the accumulation clock. (This is the designed reset signal, not a "
        "flake.)"
    )
