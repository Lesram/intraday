"""V10 / Wave-56 (2026-05-03): tests for cleanup batch.

Locks regressions for:
- WW-2 (MEDIUM): backup naming uses microsecond resolution to prevent
  same-second collision.
- WW-3 (LOW): _save_brain has a WW-3 marker for the freshness-tracking
  attribute (full implementation tracked for V11).
- PP2-2 (MEDIUM): _restore_from_latest_backup copies corrupt HEAD to
  forensic snapshot dir before swap.
- PP2-3 (LOW): save() sweeps orphan .tmp files at top.
- Z8-1 (LOW): WAVE_COMMIT_RE has Z8-1 marker (em-dash tolerance comment).

Run with: ./venv/bin/python -m pytest tests/test_wave56_fixes.py -v
"""
from __future__ import annotations

import inspect


def test_ww_2_backup_naming_microsecond_resolution():
    from backend.organism.brain_persistence import OrganismBrain
    src = inspect.getsource(OrganismBrain._create_backup)
    assert "WW-2" in src, "WW-2 marker missing"
    # Must use %f (microseconds) in strftime.
    assert "%Y%m%d_%H%M%S_%f" in src or '"%f"' in src, (
        "WW-2 regression: backup naming dropped microsecond resolution; "
        "5 backups in 1 sec will collide via mkdir(exist_ok=True)."
    )


def test_pp2_2_restore_captures_corrupt_head_forensic():
    from backend.organism.brain_persistence import OrganismBrain
    src = inspect.getsource(OrganismBrain._restore_from_latest_backup)
    assert "PP2-2" in src, "PP2-2 marker missing"
    assert "corrupt_head_" in src, (
        "PP2-2 regression: corrupt HEAD no longer captured to forensic dir."
    )


def test_pp2_3_save_sweeps_tmp_orphans():
    from backend.organism.brain_persistence import OrganismBrain
    src = inspect.getsource(OrganismBrain.save)
    assert "PP2-3" in src, "PP2-3 marker missing"
    assert ".tmp" in src and "unlink" in src, (
        "PP2-3 regression: save() no longer sweeps .tmp orphans."
    )


def test_ww_3_save_brain_marker_present():
    from backend.organism.live_engine import OrganismLiveEngine
    src = inspect.getsource(OrganismLiveEngine._save_brain)
    assert "WW-3" in src, (
        "WW-3 regression: marker for ticks-since-last-full-save tracking removed."
    )


def test_z8_1_wave_commit_re_em_dash_marker():
    from scripts.ci import check_wave_markers
    src = inspect.getsource(check_wave_markers)
    assert "Z8-1" in src, "Z8-1 marker missing"
