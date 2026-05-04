"""Apr-10 Patch F3 — break-glass reset + suspicious-write instrumentation + read-back invariant.

Tests:
1. force=True without allow_reset still blocks
2. force=True + allow_reset=True + reset_reason allows and logs warning
3. suspicious-write instrumentation fires with stack trace fields
4. read-back invariant passes on healthy write
5. read-back invariant fails loudly on mismatched write
6. normal trained save still succeeds
7. normal essential save still succeeds
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.organism.brain_persistence import (
    BRAIN_FORMAT_VERSION,
    MANIFEST_FILE,
    OrganismBrain,
)


def _make_learner(total_trades=0, generation=0, cumulative_pnl=0.0,
                  best_sharpe=float("-inf")):
    return SimpleNamespace(
        state=SimpleNamespace(
            generation=generation,
            total_trades=total_trades,
            cumulative_pnl=cumulative_pnl,
            best_sharpe=best_sharpe,
            total_bars_seen=0,
            retrain_count=0,
            drift_events=0,
            best_generation=0,
            generation_accuracies=[],
            model_metrics=[],
            evaluation_events=[],
        ),
        trade_history=[],
        _reference_features=None,
        _bars_since_retrain=0,
    )


def _make_signal_gen(is_trained=False, feature_count=0):
    return SimpleNamespace(
        _is_trained=is_trained,
        _feature_cols=[f"f{i}" for i in range(feature_count)],
        _xgb_params={},
        _clf=None,
        _reg=None,
        generation=0,
        train_window=1000,
        _latest_metrics=None,
    )


def _read_manifest(brain):
    return json.loads((brain.brain_dir / MANIFEST_FILE).read_text())


def _seed_brain(tmp_path, *, total_trades=195, feature_count=79):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    # Use break-glass to seed a trained brain with fresh mocks
    brain.save(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=feature_count),
        learner=_make_learner(total_trades=total_trades, generation=27,
                              cumulative_pnl=-492.33, best_sharpe=3.4363),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=True,
        allow_reset=True,
        reset_reason="test seed",
    )
    return brain


# ─────────────────────────────────────────────────────────────
# Test 1: force=True without allow_reset STILL BLOCKS
# ─────────────────────────────────────────────────────────────

def test_force_without_allow_reset_blocks(tmp_path, caplog):
    brain = _seed_brain(tmp_path, total_trades=195)
    before = _read_manifest(brain)
    assert before["total_trades"] == 195

    with caplog.at_level(logging.ERROR):
        brain.save(
            signal_gen=_make_signal_gen(is_trained=False),
            learner=_make_learner(total_trades=0),
            equity_curve=[100000.0],
            all_trades=[],
            epoch_metrics=[],
            force=True,          # force alone is not enough
            allow_reset=False,   # missing
        )

    assert any("BRAIN SAVE BLOCKED" in r.getMessage() for r in caplog.records)
    after = _read_manifest(brain)
    assert after["total_trades"] == 195


# ─────────────────────────────────────────────────────────────
# Test 2: full break-glass triad ALLOWS and logs warning
# ─────────────────────────────────────────────────────────────

def test_break_glass_triad_allows(tmp_path, caplog):
    brain = _seed_brain(tmp_path, total_trades=195)

    with caplog.at_level(logging.WARNING):
        brain.save(
            signal_gen=_make_signal_gen(is_trained=False),
            learner=_make_learner(total_trades=0),
            equity_curve=[100000.0],
            all_trades=[],
            epoch_metrics=[],
            force=True,
            allow_reset=True,
            reset_reason="intentional test reset",
        )

    # Check the break-glass warning fired
    assert any(
        "BRAIN BREAK-GLASS RESET" in r.getMessage()
        for r in caplog.records
    ), f"Expected break-glass WARNING. Got: {[r.getMessage() for r in caplog.records]}"

    after = _read_manifest(brain)
    assert after["total_trades"] == 0  # overwritten


# ─────────────────────────────────────────────────────────────
# Test 3: suspicious-write instrumentation fires with fields
# ─────────────────────────────────────────────────────────────

def test_suspicious_write_instrumentation_fires(tmp_path, caplog):
    brain = _seed_brain(tmp_path, total_trades=195)

    with caplog.at_level(logging.WARNING):
        # This will be BLOCKED (no allow_reset), but instrumentation fires first
        brain.save(
            signal_gen=_make_signal_gen(is_trained=False),
            learner=_make_learner(total_trades=0),
            equity_curve=[100000.0],
            all_trades=[],
            epoch_metrics=[],
            force=True,
            allow_reset=False,
        )

    suspicious_msgs = [
        r for r in caplog.records
        if "SUSPICIOUS MANIFEST WRITE" in r.getMessage()
    ]
    assert len(suspicious_msgs) >= 1, (
        f"Expected SUSPICIOUS MANIFEST WRITE log. Got: "
        f"{[r.getMessage()[:80] for r in caplog.records]}"
    )

    msg = suspicious_msgs[0].getMessage()
    # Verify forensic fields are present
    assert "pid=" in msg
    assert "thread=" in msg
    assert "force=True" in msg
    assert "allow_reset=False" in msg
    assert "Stack:" in msg
    assert "existing=" in msg
    assert "incoming=" in msg


# ─────────────────────────────────────────────────────────────
# Test 4: read-back invariant passes on healthy write
# ─────────────────────────────────────────────────────────────

def test_readback_invariant_passes_healthy(tmp_path, caplog):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.brain_dir.mkdir(parents=True, exist_ok=True)

    with caplog.at_level(logging.CRITICAL):
        result = brain._write_manifest_guarded(
            brain.brain_dir,
            _make_signal_gen(is_trained=True, feature_count=42),
            _make_learner(total_trades=100, generation=5,
                          cumulative_pnl=-200.0, best_sharpe=2.5),
            caller="test_healthy",
        )

    assert result is True
    # No CRITICAL log
    assert not any(
        "READ-BACK INVARIANT FAILED" in r.getMessage()
        for r in caplog.records
    )


# ─────────────────────────────────────────────────────────────
# Test 5: read-back invariant fails on mismatched write
# ─────────────────────────────────────────────────────────────

def test_readback_invariant_fails_on_mismatch(tmp_path, caplog):
    brain = OrganismBrain(brain_dir=tmp_path / "brain")
    brain.brain_dir.mkdir(parents=True, exist_ok=True)

    learner = _make_learner(total_trades=100, generation=5,
                            cumulative_pnl=-200.0, best_sharpe=2.5)
    sig = _make_signal_gen(is_trained=True, feature_count=42)

    # Monkey-patch _write_json to write a corrupted manifest
    from backend.organism import brain_persistence as bp
    original_write = bp._write_json

    def corrupted_write(path: Path, data: dict):
        if str(path).endswith(MANIFEST_FILE):
            corrupted = dict(data)
            corrupted["generation"] = 999  # WRONG
            original_write(path, corrupted)
        else:
            original_write(path, data)

    with caplog.at_level(logging.CRITICAL):
        with patch.object(bp, "_write_json", side_effect=corrupted_write):
            result = brain._write_manifest_guarded(
                brain.brain_dir, sig, learner,
                caller="test_mismatch",
            )

    assert result is False
    assert any(
        "READ-BACK INVARIANT FAILED" in r.getMessage()
        for r in caplog.records
    ), f"Expected CRITICAL log. Got: {[r.getMessage()[:80] for r in caplog.records]}"


# ─────────────────────────────────────────────────────────────
# Test 6: normal trained save still succeeds
# ─────────────────────────────────────────────────────────────

def test_normal_trained_save_succeeds(tmp_path):
    brain = _seed_brain(tmp_path, total_trades=195)
    brain.save(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=79),
        learner=_make_learner(total_trades=200, generation=28,
                              cumulative_pnl=-480.0, best_sharpe=3.5),
        equity_curve=[100000.0],
        all_trades=[],
        epoch_metrics=[],
        force=False,
    )
    m = _read_manifest(brain)
    assert m["total_trades"] == 200
    assert m["ml_is_trained"] is True


# ─────────────────────────────────────────────────────────────
# Test 7: normal essential save still succeeds
# ─────────────────────────────────────────────────────────────

def test_normal_essential_save_succeeds(tmp_path):
    brain = _seed_brain(tmp_path, total_trades=195)
    brain.save_essential_state(
        signal_gen=_make_signal_gen(is_trained=True, feature_count=79),
        learner=_make_learner(total_trades=200, generation=28,
                              cumulative_pnl=-480.0, best_sharpe=3.5),
        all_trades=[],
        equity_curve=[100000.0],
    )
    m = _read_manifest(brain)
    assert m["total_trades"] == 200
    assert m["ml_is_trained"] is True
