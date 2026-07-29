"""V8 / Wave-33 (2026-05-03): behavioral tests for reachability + ML calibration fixes.

Locks the regressions for:
- NN-CRIT-1: backend/api/routes/position_import.py was an unmounted duplicate
  of /positions/import endpoints in positions.py; deleted in wave-33.
- DD2-2: ML calibration outcome-binning must use raw_confidence axis to
  match calibrate_confidence's lookup. Previously used calibrated, causing
  silent feedback loop with wrong-distribution multipliers.
- NN-HIGH-2 (deferred to wave 36): OrderStateMachine + OrderIntegrityService
  orphan; folded into the decorative-cleanup wave.

Run with: ./venv/bin/python -m pytest tests/test_wave33_fixes.py -v
"""
from __future__ import annotations

import os

import pytest


# ─────────────────────────────────────────────────────────────────────
# NN-CRIT-1 — orphan position_import.py removed
# ─────────────────────────────────────────────────────────────────────


def test_nn_crit_1_orphan_position_import_deleted():
    """The duplicate position_import.py router file must not exist.
    The canonical /positions/import endpoints live in positions.py."""
    assert not os.path.isfile("backend/api/routes/position_import.py"), (
        "NN-CRIT-1 regression: backend/api/routes/position_import.py "
        "exists again. This file was an unmounted duplicate of the "
        "/positions/import endpoints in positions.py. Mounting it would "
        "shadow the canonical implementation; keeping it unmounted is "
        "dead code with audit-surface cost."
    )


def test_nn_crit_1_no_imports_of_orphan():
    """No backend code imports from the deleted position_import module."""
    import subprocess
    out = subprocess.run(
        [
            "bash", "-c",
            "grep -rn 'from backend.api.routes.position_import' "
            "backend/ --include='*.py' || true",
        ],
        capture_output=True, text=True, timeout=10,
    )
    hits = [
        line for line in out.stdout.splitlines()
        if line.strip() and "test_" not in line
    ]
    assert len(hits) == 0, (
        f"NN-CRIT-1 regression: {len(hits)} import(s) of the deleted "
        f"position_import module:\n" + "\n".join(hits)
    )


def test_nn_crit_1_canonical_import_endpoints_still_present():
    """The canonical mounted endpoints in positions.py must survive."""
    import inspect
    from backend.api.routes import positions
    src = inspect.getsource(positions)
    assert '@router.get("/import/preview"' in src, (
        "NN-CRIT-1 regression: the canonical /positions/import/preview "
        "endpoint is missing from positions.py."
    )
    assert '@router.post("/import"' in src, (
        "NN-CRIT-1 regression: the canonical /positions/import endpoint "
        "is missing from positions.py."
    )


# ─────────────────────────────────────────────────────────────────────
# DD2-2 — ML calibration axes alignment
# ─────────────────────────────────────────────────────────────────────


def test_dd2_2_record_prediction_outcome_accepts_raw_confidence_kwarg():
    """The wave-33 fix adds an optional raw_confidence keyword to
    record_prediction_outcome so outcomes can bin on the raw axis (the
    same axis calibrate_confidence indexes by)."""
    import inspect
    from backend.organism.ml_signal import MLSignalGenerator
    sig = inspect.signature(MLSignalGenerator.record_prediction_outcome)
    assert "raw_confidence" in sig.parameters, (
        "DD2-2 regression: record_prediction_outcome no longer accepts "
        "the raw_confidence kwarg. The wave-33 axis-alignment fix has "
        "been reverted and the calibration feedback loop is back."
    )


def test_dd2_2_record_prediction_outcome_uses_raw_axis_when_provided():
    """When raw_confidence is provided, it MUST be used as the binning
    axis (overriding the legacy `confidence` parameter)."""
    # Build a minimal MLSignalGenerator subclass-ish object that exposes
    # the method without requiring full ML state.
    class _Stub:
        def __init__(self):
            self._calibration_counts = [[0, 0] for _ in range(5)]
        # Reuse the real method by binding it.
        from backend.organism.ml_signal import MLSignalGenerator
        record_prediction_outcome = MLSignalGenerator.record_prediction_outcome

    stub = _Stub()
    # raw=0.1 (bin 0), calibrated=0.95 (bin 4) — should land in bin 0 if
    # raw is the axis (DD2-2 fix), or bin 4 if calibrated is the axis (bug).
    stub.record_prediction_outcome(0.95, True, raw_confidence=0.1)
    assert stub._calibration_counts[0][1] == 1, (
        "DD2-2 regression: outcome did not land in bin 0 (raw axis). "
        f"Counts: {stub._calibration_counts}"
    )
    assert stub._calibration_counts[4][1] == 0, (
        "DD2-2 regression: outcome leaked into bin 4 (calibrated axis). "
        f"Counts: {stub._calibration_counts}"
    )


def test_dd2_2_legacy_path_still_bins_when_raw_missing():
    """When raw_confidence is None, fall back to the calibrated axis
    so legacy callers don't silently drop outcomes."""
    class _Stub:
        def __init__(self):
            self._calibration_counts = [[0, 0] for _ in range(5)]
        from backend.organism.ml_signal import MLSignalGenerator
        record_prediction_outcome = MLSignalGenerator.record_prediction_outcome

    stub = _Stub()
    stub.record_prediction_outcome(0.7, True)  # calibrated bin 3
    assert stub._calibration_counts[3][1] == 1


def test_dd2_2_live_engine_passes_ml_raw_confidence_to_recorder():
    """live_engine.py:5335 (record_prediction_outcome call site) must
    forward meta.get('ml_raw_confidence') so the recording axis matches
    calibrate_confidence's lookup."""
    import inspect
    from backend.organism import live_engine
    src = inspect.getsource(live_engine)
    # The call must mention raw_confidence kwarg.
    assert "ml_raw_confidence" in src, (
        "DD2-2 regression: live_engine.py does not store/forward "
        "ml_raw_confidence in entry meta. The calibration recording "
        "axis is back to calibrated, recreating the feedback loop."
    )
    # And the call site must pass raw_confidence kwarg.
    assert "raw_confidence=meta.get(\"ml_raw_confidence\"" in src \
        or "raw_confidence=meta.get('ml_raw_confidence'" in src, (
        "DD2-2 regression: record_prediction_outcome call site does not "
        "pass raw_confidence kwarg."
    )


def test_dd2_2_calibration_loop_axis_consistent_under_synthetic_load():
    """End-to-end: feed (raw → calibrate → record(raw)) cycle 100 times.
    After the cycle, the bin counts must accumulate on the raw side."""
    class _Stub:
        def __init__(self):
            self._calibration_counts = [[0, 0] for _ in range(5)]
            self._calibration_map = [1.0] * 5
        from backend.organism.ml_signal import MLSignalGenerator
        record_prediction_outcome = MLSignalGenerator.record_prediction_outcome
        calibrate_confidence = MLSignalGenerator.calibrate_confidence
        update_calibration_map = MLSignalGenerator.update_calibration_map

    stub = _Stub()
    # 100 predictions with raw=0.7 (bin 3) and 80% accuracy.
    for i in range(100):
        raw = 0.7
        calibrated = stub.calibrate_confidence(raw)
        was_correct = (i % 5) < 4  # 80% accuracy
        stub.record_prediction_outcome(
            calibrated, was_correct, raw_confidence=raw,
        )
    stub.update_calibration_map()
    # Bin 3 should have 100 samples and ~80 correct.
    assert stub._calibration_counts[3][1] == 100, (
        f"DD2-2 axis-consistency: bin 3 has "
        f"{stub._calibration_counts[3][1]} samples; expected 100."
    )
    assert 75 <= stub._calibration_counts[3][0] <= 85, (
        f"DD2-2 axis-consistency: bin 3 correct count "
        f"{stub._calibration_counts[3][0]} outside expected 75-85 range."
    )
    # Other bins must be empty (axis isolation).
    for i in [0, 1, 2, 4]:
        assert stub._calibration_counts[i][1] == 0, (
            f"DD2-2 axis-consistency: bin {i} accumulated "
            f"{stub._calibration_counts[i][1]} samples — should be 0 "
            "(all predictions were raw=0.7, bin 3)."
        )
