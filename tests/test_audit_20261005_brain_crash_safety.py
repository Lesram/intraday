"""Audit 2026-10-05 C12 — crash safety of the brain persistence.

C12-01  a crash during save()'s swap left a HEAD that load() accepted with
        missing state files loaded as empty. The swap is now journaled: a crash
        at any step loads as the complete previous generation or is rolled
        forward to the complete new one; an inventory in the completion
        sentinel rejects a HEAD (or backup) with a missing file.
C12-02  essential saves re-pickled and re-signed the frozen ensemble into HEAD
        with truncating writes. Unchanged ensembles are no longer written; every
        model write that remains is atomic and all-or-nothing.
C12-03  the trained-overwrite guard no longer protected a trained brain once
        close_accounting restored the learner totals of an engine whose brain
        load failed.
C12-04  unsigned pickles were deserialized with joblib.load. Every production
        model/cache file is signed, so unsigned files now fail closed (CRITICAL,
        handled like a missing file, never deserialized).
C12-05  every essential save erased ml_state.json['model_metrics_history'].
C12-06  saves that did not happen were reported as saves.
C12-09  renames were not fsynced (files and directory).

Review of the fix (2026-10-05):
- a roll-forward never publishes staged files over HEAD state written after
  the journal (pre-fix code after a rollback, a write outside a save): the
  journal records each replaced/deleted HEAD file's pre-swap identity; a
  stale journal is retired with a forensic copy and HEAD is kept;
- an unsigned or torn pickle listed in a generation's inventory makes it
  incomplete (backup fallback), as a missing file does;
- after a backup fallback the engine takes a full save; essential saves into
  a rejected HEAD and backups of it are refused; ml_state.json is written once
  per save; save_essential_state reports OSError; the engine's standalone
  exit-level write settles a pending journal first;
- scripts/ops/check_brain_pickles_signed.py: read-only pre-deploy check.

Compatibility: a copy of the production brain loads exactly as with the code
before this change, and a brain saved by this code loads with that code.
"""
from __future__ import annotations

import errno
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
import warnings
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from sklearn.linear_model import LinearRegression, LogisticRegression

from backend.organism import brain_persistence as bp
from backend.organism.brain_persistence import (
    LOCK_FILE,
    MANIFEST_FILE,
    SAVE_COMPLETE_SENTINEL,
    SWAP_JOURNAL_FILE,
    SWAP_STAGING_DIR,
    OrganismBrain,
    _BrainLock,
)
from backend.organism.ensemble_models import EnsemblePredictor

REPO_ROOT = Path(__file__).resolve().parents[1]
PRE_FIX_COMMIT = "ee023515"  # intra-2.0-phase1, the rollback target
PRODUCTION_BRAIN_COPY = Path(os.environ.get(
    "INTRA_PRODUCTION_BRAIN_COPY", "/mnt/user-data/uploads/intra/organism_brain"))

_RNG = np.random.default_rng(20261005)
_X = _RNG.normal(size=(80, 4))
_Y_DIR = (_X[:, 0] > 0).astype(int)
_Y_RET = _X[:, 1] * 0.01


# ── Fixtures: real models that are fork-safe to pickle ──────────────────────
# (scikit-learn linear models and numpy arrays; XGBoost/OpenMP is not
# fork-safe once the parent process has used it, so the crash harness avoids it.)

def _ensemble(weight: float = 1.0) -> EnsemblePredictor:
    ensemble = EnsemblePredictor(n_estimators=3, max_depth=2)
    ensemble._models = [
        (LogisticRegression().fit(_X, _Y_DIR), LinearRegression().fit(_X, _Y_RET), "lin", weight),
        (LogisticRegression(C=0.5).fit(_X, _Y_DIR), LinearRegression().fit(_X, -_Y_RET), "lin2", 1.0),
    ]
    ensemble._is_trained = True
    ensemble._bump_state_version()
    return ensemble


def _signal_gen(gen: int = 5, *, trained: bool = True, ensemble=None):
    calibration = {"counts": [[0, 0]] * 5, "map": [1.0] * 5}
    sg = SimpleNamespace(
        _is_trained=trained,
        _clf=LogisticRegression().fit(_X, _Y_DIR) if trained else None,
        _reg=LinearRegression().fit(_X, _Y_RET) if trained else None,
        _ensemble=ensemble,
        _feature_cols=["f0", "f1", "f2", "f3"] if trained else [],
        _xgb_params={"max_depth": 3},
        generation=gen,
        train_window=100,
        _latest_metrics=None,
        calibration_to_dict=lambda: calibration,
        load_calibration=lambda data: None,
    )
    if trained:
        sg._last_val_X, sg._last_val_y_dir, sg._last_val_y_ret = _X[:10], _Y_DIR[:10], _Y_RET[:10]
    return sg


def _learner(n: int = 5, *, generation: int | None = None, metrics=None):
    return SimpleNamespace(
        state=SimpleNamespace(
            generation=n if generation is None else generation,
            total_trades=n,
            cumulative_pnl=-1.0 * n,
            best_sharpe=0.5,
            total_bars_seen=0,
            retrain_count=0,
            drift_events=0,
            best_generation=0,
            generation_accuracies=[],
            model_metrics=list(metrics or []),
            evaluation_events=[{"generation": n, "accepted": True}],
        ),
        trade_history=[],
        _reference_features=None,
        _bars_since_retrain=0,
    )


class _Persisted:
    def __init__(self, payload):
        self.payload = payload

    def to_persistence_dict(self):
        return dict(self.payload)


def _full_save(brain: OrganismBrain, n: int, *, ensemble=None, **overrides):
    kwargs = dict(
        signal_gen=_signal_gen(n, ensemble=ensemble),
        learner=_learner(n),
        equity_curve=[100_000.0 + i for i in range(n)],
        all_trades=[],
        epoch_metrics=[{"epoch": i} for i in range(n)],
        peak_equity=100_000.0 + n,
        extra_counters={"tick_count": 100 + n, "daily_loss_halt": True,
                        "pending_entry_order_ids": {"AAPL": f"ord-{n}"}},
        evolved_params={"atr_multiplier": 2.0 + n / 10},
        governance_controller=_Persisted({"trading_halted": True, "generation_marker": n}),
        regime_detector=_Persisted({"history": [n], "sma_period": 200}),
    )
    kwargs.update(overrides)
    return brain.save(**kwargs)


def _essential_save(brain: OrganismBrain, n: int, *, signal_gen=None, learner=None, **overrides):
    kwargs = dict(
        signal_gen=signal_gen if signal_gen is not None else _signal_gen(n),
        learner=learner if learner is not None else _learner(n),
        all_trades=[],
        equity_curve=[100_000.0 + i for i in range(n)],
        epoch_metrics=[{"epoch": i} for i in range(n)],
        peak_equity=100_000.0 + n,
        extra_counters={"tick_count": 100 + n, "daily_loss_halt": True},
        governance_controller=_Persisted({"trading_halted": True, "generation_marker": n}),
        regime_detector=_Persisted({"history": [n], "sma_period": 200}),
    )
    kwargs.update(overrides)
    return brain.save_essential_state(**kwargs)


def _digest(brain: OrganismBrain) -> dict:
    """Every restored container, reduced to the values each generation sets."""
    return {
        "learning": brain.learning_state.get("total_trades"),
        "extra_counters": brain.extra_counters.get("tick_count"),
        "halt": brain.extra_counters.get("daily_loss_halt"),
        "pending": brain.extra_counters.get("pending_entry_order_ids"),
        "governance": brain.governance_state.get("generation_marker"),
        "regime": brain.regime_state.get("history"),
        "evolved": brain.evolved_params.get("atr_multiplier"),
        "ml_state": brain.ml_state.get("generation"),
        "equity": len(brain.equity_curve),
        "epochs": len(brain.epoch_metrics),
        "evaluations": [e.get("generation") for e in brain.evaluation_event_history],
        "manifest": brain._manifest.get("total_trades"),
        "models": (brain.clf is not None, brain.reg is not None),
    }


def _head_files(brain_dir: Path) -> dict[str, bytes]:
    return {
        p.name: p.read_bytes() for p in sorted(brain_dir.iterdir())
        if p.is_file() and p.name not in {LOCK_FILE, "close_accounting.json"}
    }


def _inventory(brain_dir: Path) -> list[str] | None:
    return bp._read_head_inventory(brain_dir / SAVE_COMPLETE_SENTINEL)


class _Crash(BaseException):
    """Escapes every ``except Exception`` handler, like a kill (the brain lock
    is released by the ``finally``, as a dead process releases its flock)."""


def _crash_full_save_before_publishing(monkeypatch, brain: OrganismBrain, name: str,
                                       n: int, **kwargs) -> None:
    """A full save of generation ``n`` that dies just before the staged
    ``name`` replaces its HEAD copy: the journal and the staging dir stay."""
    real_replace = os.replace
    target = brain.brain_dir / name

    def crash(src, dst, *a, **kw):
        if Path(src).parent.name == SWAP_STAGING_DIR and Path(dst) == target:
            raise _Crash()
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(bp.os, "replace", crash)
    try:
        with pytest.raises(_Crash):
            _full_save(brain, n, **kwargs)
    finally:
        monkeypatch.setattr(bp.os, "replace", real_replace)
    assert (brain.brain_dir / SWAP_JOURNAL_FILE).is_file()


def _swap_forensics(brain_dir: Path) -> list[Path]:
    return sorted(brain_dir.glob(f"corrupt_head_*{bp.SWAP_FORENSIC_SUFFIX}"))


# ═════════════════════════════════════════════════════════════════════════
# C12-01 — a real crash (fork + SIGKILL) at every step of the save swap
# ═════════════════════════════════════════════════════════════════════════

_EXIT_SAVE_COMPLETED = 3
_EXIT_CHILD_ERROR = 4


def _install_kill_hooks(brain_dir: Path, kill_at: int, scope: str) -> None:
    """In the forked child: SIGKILL the process just before the ``kill_at``-th
    filesystem mutation of HEAD (``scope="head"``: replace/unlink/move/rmtree
    of a top-level brain entry) or of the staging dir (``scope="stage"``)."""
    root = str(brain_dir)
    stage = str(brain_dir / SWAP_STAGING_DIR)
    counter = {"n": 0}

    def in_scope(path) -> bool:
        p = os.fspath(path)
        base = root if scope == "head" else stage
        return p.startswith(base + os.sep) and os.sep not in p[len(base) + 1:]

    def hit(path) -> None:
        if in_scope(path):
            if counter["n"] == kill_at:
                os.kill(os.getpid(), signal.SIGKILL)
            counter["n"] += 1

    real_replace, real_unlink = os.replace, os.unlink
    real_rmtree, real_move = shutil.rmtree, shutil.move

    def replace(src, dst, *a, **kw):
        hit(dst)
        return real_replace(src, dst, *a, **kw)

    def unlink(path, *a, **kw):
        if kw.get("dir_fd") is None:
            hit(path)
        return real_unlink(path, *a, **kw)

    def rmtree(path, *a, **kw):
        hit(path)
        return real_rmtree(path, *a, **kw)

    def move(src, dst, *a, **kw):
        hit(dst)
        return real_move(src, dst, *a, **kw)

    os.replace, os.unlink, shutil.rmtree, shutil.move = replace, unlink, rmtree, move


def _crash_save(brain_dir: Path, save, kill_at: int, scope: str) -> bool:
    """Fork; the child runs ``save(brain_dir)`` and is SIGKILLed at the chosen
    step. Returns True when the save completed before reaching that step."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        pid = os.fork()
    if pid == 0:  # child: never returns into pytest
        try:
            sys.stdout = sys.stderr = open(os.devnull, "w")
            logging.disable(logging.CRITICAL)
            _install_kill_hooks(brain_dir, kill_at, scope)
            save(brain_dir)
            os._exit(_EXIT_SAVE_COMPLETED)
        except BaseException:
            os._exit(_EXIT_CHILD_ERROR)
    deadline = time.monotonic() + 60
    while True:
        done, status = os.waitpid(pid, os.WNOHANG)
        if done:
            break
        if time.monotonic() > deadline:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
            pytest.fail(f"crash-harness child hung (kill point {kill_at})")
        time.sleep(0.01)
    if os.WIFSIGNALED(status):
        assert os.WTERMSIG(status) == signal.SIGKILL
        return False
    assert os.WEXITSTATUS(status) == _EXIT_SAVE_COMPLETED, "child save raised"
    return True


def _new_generation_save(brain_dir: Path) -> None:
    _full_save(OrganismBrain(brain_dir), 6, ensemble=_ensemble(0.5))


def _seed_previous_generation(root: Path, *, staged_dir: bool = False) -> Path:
    base = root / "base" / "brain"
    assert _full_save(OrganismBrain(base), 5, ensemble=_ensemble(1.0)) is True
    if staged_dir:
        (base / "diagnostics").mkdir()
        (base / "diagnostics" / "history.json").write_bytes(b'["old"]')
    return base


def _expected_digest(brain_dir: Path) -> dict:
    brain = OrganismBrain(brain_dir)
    assert brain.load() is True
    return _digest(brain)


def _run_crash_matrix(tmp_path: Path, *, staged_dir: bool = False, first_save: bool = False):
    """Every kill point of a full save; returns the per-case observations."""
    if first_save:
        base = tmp_path / "base" / "brain"
        base.mkdir(parents=True)
        old = None
    else:
        base = _seed_previous_generation(tmp_path, staged_dir=staged_dir)
        old = _expected_digest(base)

    def save(brain_dir: Path) -> None:
        if not staged_dir:
            _new_generation_save(brain_dir)
            return
        # A save that also regenerates a preserved directory (R7 shape).
        original = OrganismBrain._save_regime_state

        def regenerate(self, target, regime_detector):
            original(self, target, regime_detector)
            (target / "diagnostics").mkdir()
            (target / "diagnostics" / "history.json").write_bytes(b'["new"]')

        OrganismBrain._save_regime_state = regenerate
        try:
            _new_generation_save(brain_dir)
        finally:
            OrganismBrain._save_regime_state = original

    new_dir = tmp_path / "complete" / "brain"
    shutil.copytree(base, new_dir)
    save(new_dir)
    new = _expected_digest(new_dir)
    assert new != old

    cases = []
    points = [("stage", 0), ("stage", 5)] + [("head", i) for i in range(200)]
    for scope, kill_at in points:
        case_dir = tmp_path / f"{scope}{kill_at:03d}" / "brain"
        shutil.copytree(base, case_dir)
        completed = _crash_save(case_dir, save, kill_at, scope)
        if completed:
            shutil.rmtree(case_dir.parent)
            if scope == "head":
                break
            continue
        journal_at_crash = (case_dir / SWAP_JOURNAL_FILE).is_file()
        manifest_at_crash = (case_dir / MANIFEST_FILE).is_file()
        brain = OrganismBrain(case_dir)
        loaded = brain.load() if brain.exists else False
        cases.append({
            "point": (scope, kill_at),
            "journal_at_crash": journal_at_crash,
            "manifest_at_crash": manifest_at_crash,
            "exists": brain.exists,
            "loaded": loaded,
            "digest": _digest(brain) if loaded else None,
            "from_head": brain._loaded_from == brain.brain_dir,
            "journal_after": (case_dir / SWAP_JOURNAL_FILE).exists(),
            "inventory": _inventory(case_dir),
            "dir": case_dir,
            "diagnostics": (case_dir / "diagnostics" / "history.json").read_bytes()
            if (case_dir / "diagnostics" / "history.json").exists() else None,
            "corrupt_snapshots": sorted(p.name for p in case_dir.glob("corrupt_head_*")),
        })
    assert any(c["journal_at_crash"] for c in cases), "harness never crashed mid-swap"
    return old, new, cases


def _assert_complete_generation(case: dict) -> None:
    listed = case["inventory"]
    assert listed, f"{case['point']}: no completion inventory after recovery"
    missing = [n for n in listed if not (case["dir"] / n).exists()]
    assert not missing, f"{case['point']}: inventory lists missing {missing}"


fork_only = pytest.mark.skipif(not hasattr(os, "fork"), reason="needs os.fork")


@pytest.fixture
def fast_hmac_key(monkeypatch):
    """The crash harness signs and verifies ~20 pickles per kill point; derive
    the (unchanged) PBKDF2 key once per secret instead of once per file."""
    from backend.utils import secure_pickle
    real = secure_pickle._get_hmac_key
    cache: dict = {}

    def cached() -> bytes:
        secret = os.environ.get(secure_pickle.HMAC_KEY_ENV)
        if secret not in cache:
            cache[secret] = real()
        return cache[secret]

    monkeypatch.setattr(secure_pickle, "_get_hmac_key", cached)


@fork_only
def test_crash_at_every_swap_step_loads_one_complete_generation(tmp_path, fast_hmac_key):
    old, new, cases = _run_crash_matrix(tmp_path)
    for case in cases:
        point = case["point"]
        assert case["loaded"] is True, point
        assert case["from_head"], f"{point}: fell back to a backup"
        assert not case["corrupt_snapshots"], point
        assert not case["journal_after"], f"{point}: journal left after load"
        if case["journal_at_crash"]:
            # Rolled forward: the complete NEW generation, never a mix.
            assert case["digest"] == new, point
            _assert_complete_generation(case)
        else:
            assert case["digest"] in (old, new), point
            if case["digest"] == new:
                _assert_complete_generation(case)
        # Never silently empty state.
        assert case["digest"]["extra_counters"] and case["digest"]["governance"], point
        assert case["digest"]["halt"] is True and case["digest"]["pending"], point
    staged = [c for c in cases if c["point"][0] == "stage"]
    assert staged and all(c["digest"] == old for c in staged)


@fork_only
def test_crash_while_replacing_a_staged_directory_keeps_one_generation(tmp_path, fast_hmac_key):
    old, new, cases = _run_crash_matrix(tmp_path, staged_dir=True)
    for case in cases:
        point = case["point"]
        assert case["loaded"] is True and case["from_head"], point
        assert case["digest"] in (old, new), point
        if case["journal_at_crash"]:
            assert case["digest"] == new, point
        expected = b'["new"]' if case["digest"] == new else b'["old"]'
        assert case["diagnostics"] == expected, point
        assert not case["journal_after"], point


@fork_only
def test_crash_during_the_first_ever_save_is_rolled_forward_or_absent(tmp_path, fast_hmac_key):
    _old, new, cases = _run_crash_matrix(tmp_path, first_save=True)
    for case in cases:
        point = case["point"]
        if case["journal_at_crash"]:
            # manifest.json may not be in HEAD yet: the journal makes the brain
            # exist, and load() rolls the save forward.
            assert case["exists"] and case["loaded"] is True, point
            assert case["digest"] == new, point
        else:
            assert case["loaded"] is False or case["digest"] == new, point
    # The case that used to report "no previous brain": journal written,
    # manifest.json not yet published (it is published last).
    assert any(c["journal_at_crash"] and not c["manifest_at_crash"] and c["loaded"]
               for c in cases)


def test_inventory_rejects_head_with_a_missing_state_file(tmp_path, caplog):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    assert _full_save(brain, 6) is True  # backup of generation 5 minted first
    assert "extra_counters.json" in _inventory(brain_dir)
    (brain_dir / "extra_counters.json").unlink()

    fresh = OrganismBrain(brain_dir)
    with caplog.at_level(logging.CRITICAL, logger="backend.organism.brain_persistence"):
        assert fresh.load() is True
    # Never generation 6 with extra_counters loaded as {}: the complete backup.
    assert fresh.extra_counters.get("tick_count") == 105
    assert fresh.learning_state["total_trades"] == 5
    assert fresh._loaded_from is not None and fresh._loaded_from.parent.name == "backups"
    assert any("is incomplete" in r.getMessage() for r in caplog.records)
    assert list(brain_dir.glob("corrupt_head_*"))


def test_incomplete_head_without_backups_fails_closed(tmp_path):
    brain_dir = tmp_path / "brain"
    assert _full_save(OrganismBrain(brain_dir), 5) is True
    shutil.rmtree(brain_dir / "backups")
    (brain_dir / "governance_state.json").unlink()
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is False
    assert fresh.governance_state == {} and fresh._loaded is False


def test_backup_with_missing_listed_file_is_skipped(tmp_path):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    for n in (4, 5, 6):
        assert _full_save(brain, n) is True
    backups = sorted((brain_dir / "backups").iterdir(), key=lambda p: p.stat().st_mtime)
    newest = backups[-1]
    (newest / "learning_state.json").unlink()  # damaged newest backup (generation 5)
    (brain_dir / MANIFEST_FILE).write_text("{not json")  # corrupt HEAD
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True
    assert fresh._loaded_from.name == backups[-2].name
    assert fresh.learning_state["total_trades"] == 4


def test_backup_fallback_reads_models_from_the_same_backup(tmp_path):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5, ensemble=_ensemble(1.0)) is True
    assert _full_save(brain, 6, ensemble=_ensemble(1.0)) is True
    for name in ("ml_last_val_X.joblib", "ensemble_manifest.json"):
        (brain_dir / name).unlink()  # HEAD is incomplete -> rejected
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True and fresh._loaded_from.parent.name == "backups"
    target = SimpleNamespace(load_calibration=lambda c: None, _ensemble=EnsemblePredictor(),
                             _xgb_params={})
    assert fresh.apply_to_signal_generator(target) is True
    assert target._ensemble.model_names == ["lin", "lin2"]
    assert np.array_equal(target._last_val_X, _X[:10])
    # HEAD did not provide the ensemble, so the next essential save writes it.
    assert fresh._ensemble_on_disk is None


def test_interrupted_backup_copy_never_becomes_a_restore_candidate(tmp_path, monkeypatch):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    real_copy2 = shutil.copy2
    calls = {"n": 0}

    def failing_copy2(src, dst, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_copy2(src, dst, *a, **kw)

    monkeypatch.setattr(bp.shutil, "copy2", failing_copy2)
    brain._create_backup()
    monkeypatch.setattr(bp.shutil, "copy2", real_copy2)
    entries = sorted(p.name for p in (brain_dir / "backups").iterdir())
    assert not any(n.startswith("brain_gen") for n in entries), entries
    assert not any(n.startswith(".partial_") for n in entries), entries


def test_unusable_journal_rejects_head_and_next_save_repairs_it(tmp_path, caplog):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    assert _full_save(brain, 6) is True
    (brain_dir / SWAP_JOURNAL_FILE).write_text('{"format": "something-else"}')
    (brain_dir / "learning_state.json").unlink()  # a swap that cannot be completed

    loader = OrganismBrain(brain_dir)
    with caplog.at_level(logging.CRITICAL, logger="backend.organism.brain_persistence"):
        assert loader.load() is True
    assert loader._loaded_from.parent.name == "backups"
    assert any("unreadable" in r.getMessage() for r in caplog.records)

    # The next full save discards the journal and publishes a complete generation.
    assert _full_save(loader, 7) is True
    assert not (brain_dir / SWAP_JOURNAL_FILE).exists()
    reloaded = OrganismBrain(brain_dir)
    assert reloaded.load() is True and reloaded._loaded_from == reloaded.brain_dir
    assert reloaded.learning_state["total_trades"] == 7


def test_essential_save_refuses_to_write_into_an_unrecoverable_swap(tmp_path):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    (brain_dir / SWAP_JOURNAL_FILE).write_text("not json")
    before = _head_files(brain_dir)
    assert _essential_save(brain, 6) is False
    assert _head_files(brain_dir) == before


def test_failed_swap_in_process_is_rolled_forward_by_the_next_save(tmp_path, monkeypatch):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    real_replace = os.replace
    failed = {"done": False}

    def flaky_replace(src, dst, *a, **kw):
        # The swap's rename of the staged file into HEAD (not the staging write).
        if (not failed["done"] and Path(src).parent.name == SWAP_STAGING_DIR
                and Path(dst) == brain.brain_dir / "learning_state.json"):
            failed["done"] = True
            raise OSError(errno.EIO, "injected I/O error")
        return real_replace(src, dst, *a, **kw)

    monkeypatch.setattr(bp.os, "replace", flaky_replace)
    with pytest.raises(OSError, match="injected"):
        _full_save(brain, 6)
    assert (brain_dir / SWAP_JOURNAL_FILE).is_file()
    assert not (brain_dir / SAVE_COMPLETE_SENTINEL).exists()
    # The next essential save completes the interrupted generation first.
    assert _essential_save(brain, 7) is True
    assert not (brain_dir / SWAP_JOURNAL_FILE).exists()
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True
    assert fresh.evolved_params["atr_multiplier"] == pytest.approx(2.6)  # gen 6 (full save)
    assert fresh.learning_state["total_trades"] == 7                      # essential save


# ── Review: a roll-forward never publishes over state written after the journal ──

def test_journal_records_the_pre_swap_identity_of_replaced_and_deleted_files(tmp_path, monkeypatch):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    before = {p.name: bp._file_identity(p) for p in brain_dir.iterdir() if p.is_file()}
    # Generation 6 has no epoch metrics: the swap deletes epoch_metrics.csv.
    _crash_full_save_before_publishing(monkeypatch, brain, "equity_curve.csv", 6, epoch_metrics=[])
    journal = json.loads((brain_dir / SWAP_JOURNAL_FILE).read_text())
    assert journal["format"] == bp.SWAP_JOURNAL_FORMAT
    assert set(journal["head"]) == set(journal["entries"])
    assert journal["head"]["learning_state.json"] == before["learning_state.json"]
    assert journal["delete"] == {"epoch_metrics.csv": before["epoch_metrics.csv"]}
    assert all(meta == bp._file_identity(brain_dir / SWAP_STAGING_DIR / name)
               for name, meta in journal["files"].items())
    # Nothing changed since: the next load rolls generation 6 forward.
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True and fresh.learning_state["total_trades"] == 6
    assert not (brain_dir / "epoch_metrics.csv").exists()
    assert not _swap_forensics(brain_dir)


def test_head_file_changed_before_its_publication_is_kept(tmp_path, monkeypatch, caplog):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    _crash_full_save_before_publishing(monkeypatch, brain, "epoch_metrics.csv", 6)
    # A write outside a save (or older code) updates HEAD's still-old copy.
    newer = json.loads((brain_dir / "extra_counters.json").read_text())
    newer["pending_entry_order_ids"] = {"NVDA": "ord-newer"}
    (brain_dir / "extra_counters.json").write_text(json.dumps(newer))

    fresh = OrganismBrain(brain_dir)
    with caplog.at_level(logging.CRITICAL, logger="backend.organism.brain_persistence"):
        assert fresh.load() is True
    assert fresh._loaded_from == fresh.brain_dir                       # HEAD, not a backup
    assert fresh.extra_counters["pending_entry_order_ids"] == {"NVDA": "ord-newer"}
    assert not (brain_dir / SWAP_JOURNAL_FILE).exists()
    assert any("STALE" in r.getMessage() and "extra_counters.json" in r.getMessage()
               for r in caplog.records)
    (forensic,) = _swap_forensics(brain_dir)
    assert (forensic / SWAP_JOURNAL_FILE).is_file()
    assert (forensic / "staged" / "extra_counters.json").is_file()
    assert json.loads((forensic / "head" / "extra_counters.json").read_text()) == newer
    assert "kept over a stale" in fresh.full_save_required()


def test_published_file_changed_after_the_crash_is_kept(tmp_path, monkeypatch):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    _crash_full_save_before_publishing(monkeypatch, brain, "governance_state.json", 6)
    # extra_counters.json (generation 6) was published, then rewritten.
    (brain_dir / "extra_counters.json").write_text(json.dumps({"tick_count": 999}))
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True and fresh._loaded_from == fresh.brain_dir
    assert fresh.extra_counters == {"tick_count": 999}
    assert fresh.governance_state["generation_marker"] == 5   # never published
    assert not (brain_dir / SWAP_JOURNAL_FILE).exists() and len(_swap_forensics(brain_dir)) == 1


def test_file_created_after_the_journal_is_not_deleted_by_a_roll_forward(tmp_path, monkeypatch):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5, equity_curve=[]) is True
    _crash_full_save_before_publishing(monkeypatch, brain, "epoch_metrics.csv", 6, equity_curve=[])
    assert not (brain_dir / "equity_curve.csv").exists()
    (brain_dir / "equity_curve.csv").write_text("equity\n1.0\n2.0\n")   # written after the crash
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True
    assert fresh.equity_curve == [1.0, 2.0]
    assert not (brain_dir / SWAP_JOURNAL_FILE).exists()


def test_timestamp_sentinel_next_to_a_journal_blocks_the_roll_forward(tmp_path, monkeypatch, caplog):
    """Only pre-fix code writes a timestamp .save_complete (on every load):
    it loaded this brain after the crash, so the journal is stale."""
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    _crash_full_save_before_publishing(monkeypatch, brain, "learning_state.json", 6)
    assert not (brain_dir / SAVE_COMPLETE_SENTINEL).exists()
    (brain_dir / SAVE_COMPLETE_SENTINEL).write_text("2026-10-05T12:00:00+00:00")
    journal = json.loads((brain_dir / SWAP_JOURNAL_FILE).read_text())
    assert any(SAVE_COMPLETE_SENTINEL in p for p in OrganismBrain(brain_dir)._swap_journal_problems(journal))
    fresh = OrganismBrain(brain_dir)
    with caplog.at_level(logging.CRITICAL, logger="backend.organism.brain_persistence"):
        assert fresh.load() is True
    assert fresh.learning_state["total_trades"] == 5            # HEAD as the old code saw it
    assert fresh.extra_counters["tick_count"] == 106            # published before the crash
    assert any("STALE" in r.getMessage() for r in caplog.records)
    assert not (brain_dir / SWAP_JOURNAL_FILE).exists()


def test_altered_staged_file_rejects_head_and_keeps_the_journal_until_replaced(tmp_path, monkeypatch, caplog):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    _crash_full_save_before_publishing(monkeypatch, brain, "governance_state.json", 6)
    staged = brain_dir / SWAP_STAGING_DIR / "learning_state.json"
    damaged = staged.read_text().replace("6", "9")
    staged.write_text(damaged)   # damaged staging, not newer HEAD state

    loader = OrganismBrain(brain_dir)
    with caplog.at_level(logging.CRITICAL, logger="backend.organism.brain_persistence"):
        assert loader.load() is True
    assert loader._loaded_from.parent.name == "backups"       # the complete generation 5
    assert loader.learning_state["total_trades"] == 5
    assert any("cannot be completed" in r.getMessage() and "learning_state.json" in r.getMessage()
               for r in caplog.records)
    assert (brain_dir / SWAP_JOURNAL_FILE).is_file()           # a load never retires it

    # A full save that dies while staging keeps the journal: HEAD is still rejected.
    real = OrganismBrain._save_ml_models

    def dies(self, target, signal_gen):
        raise _Crash()

    monkeypatch.setattr(OrganismBrain, "_save_ml_models", dies)
    with pytest.raises(_Crash):
        _full_save(loader, 7)
    monkeypatch.setattr(OrganismBrain, "_save_ml_models", real)
    (forensic,) = _swap_forensics(brain_dir)
    assert (forensic / "staged" / "learning_state.json").read_text() == damaged
    assert (forensic / SWAP_JOURNAL_FILE).is_file() and (forensic / "head" / "manifest.json").is_file()
    assert (brain_dir / SWAP_JOURNAL_FILE).is_file()
    again = OrganismBrain(brain_dir)
    assert again.load() is True and again._loaded_from.parent.name == "backups"

    # The next full save replaces the journal and publishes a complete generation.
    assert _full_save(again, 8) is True
    assert not (brain_dir / SWAP_JOURNAL_FILE).exists()
    reloaded = OrganismBrain(brain_dir)
    assert reloaded.load() is True and reloaded._loaded_from == reloaded.brain_dir
    assert reloaded.learning_state["total_trades"] == 8


def test_unlocked_load_with_a_pending_journal_uses_a_backup(tmp_path, monkeypatch):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    _crash_full_save_before_publishing(monkeypatch, brain, "governance_state.json", 6)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)   # skip the 20 s lock wait
    holder = _BrainLock(brain_dir / LOCK_FILE)
    holder.acquire()
    try:
        fresh = OrganismBrain(brain_dir)
        assert fresh.load() is True
    finally:
        holder.release()
    assert fresh._loaded_from.parent.name == "backups"          # never read half-swapped
    assert fresh.learning_state["total_trades"] == 5
    assert (brain_dir / SWAP_JOURNAL_FILE).is_file()            # not settled without the lock


# ═════════════════════════════════════════════════════════════════════════
# C12-02 — frozen models are not rewritten; remaining model writes are atomic
# ═════════════════════════════════════════════════════════════════════════

def _model_file_identity(brain_dir: Path) -> dict:
    return {
        p.name: (p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes())
        for p in sorted(brain_dir.glob("*.joblib")) + [brain_dir / "ensemble_manifest.json"]
    }


def _loaded_engine_like(brain_dir: Path):
    brain = OrganismBrain(brain_dir)
    assert brain.load() is True
    sg = _signal_gen(5, ensemble=EnsemblePredictor(n_estimators=3, max_depth=2))
    assert brain.apply_to_signal_generator(sg) is True
    return brain, sg


def test_essential_saves_never_rewrite_an_unchanged_ensemble(tmp_path, monkeypatch):
    brain_dir = tmp_path / "brain"
    assert _full_save(OrganismBrain(brain_dir), 5, ensemble=_ensemble()) is True
    brain, sg = _loaded_engine_like(brain_dir)
    before = _model_file_identity(brain_dir)

    from backend.utils import secure_pickle
    dumps = []
    real_dumps = secure_pickle.secure_dumps
    monkeypatch.setattr(secure_pickle, "secure_dumps",
                        lambda obj: dumps.append(type(obj).__name__) or real_dumps(obj))
    for n in (6, 7, 8):
        assert _essential_save(brain, n, signal_gen=sg) is True
    assert dumps == [], "an essential save pickled/signed a model"
    assert _model_file_identity(brain_dir) == before


def test_changed_ensemble_is_written_atomically_by_the_essential_save(tmp_path):
    brain_dir = tmp_path / "brain"
    assert _full_save(OrganismBrain(brain_dir), 5, ensemble=_ensemble()) is True
    brain, sg = _loaded_engine_like(brain_dir)
    before = _model_file_identity(brain_dir)
    sg._ensemble.set_weights({"lin": 3.0, "lin2": 1.0})  # a real change
    assert _essential_save(brain, 6, signal_gen=sg) is True
    after = _model_file_identity(brain_dir)
    assert after["ensemble_lin_clf.joblib"][0] != before["ensemble_lin_clf.joblib"][0]  # replaced
    manifest = json.loads((brain_dir / "ensemble_manifest.json").read_text())
    assert [m["weight"] for m in manifest["models"]] == pytest.approx([0.75, 0.25])
    assert not (brain_dir / bp.ENSEMBLE_STAGING_DIR).exists()
    reloaded = EnsemblePredictor()
    assert reloaded.load(brain_dir) and reloaded.get_weights() == pytest.approx({"lin": 0.75, "lin2": 0.25})
    # Unchanged again: the next essential save leaves the files alone.
    again = _model_file_identity(brain_dir)
    assert _essential_save(brain, 7, signal_gen=sg) is True
    assert _model_file_identity(brain_dir) == again


class _Unpicklable:
    def __reduce__(self):
        raise RuntimeError("cannot pickle this model")


def test_partially_serializable_changed_ensemble_never_reaches_head(tmp_path, caplog):
    brain_dir = tmp_path / "brain"
    assert _full_save(OrganismBrain(brain_dir), 5, ensemble=_ensemble()) is True
    brain, sg = _loaded_engine_like(brain_dir)
    before = _model_file_identity(brain_dir)
    clf, _reg, name, weight = sg._ensemble._models[1]
    sg._ensemble._models[1] = (clf, _Unpicklable(), name, weight)
    sg._ensemble._bump_state_version()
    with caplog.at_level(logging.WARNING, logger="backend.organism.brain_persistence"):
        assert _essential_save(brain, 6, signal_gen=sg) is False  # reported, not claimed
    assert any("could not be fully serialized" in r.getMessage() for r in caplog.records)
    assert _model_file_identity(brain_dir) == before  # no reduced manifest, no partial model
    assert not (brain_dir / bp.ENSEMBLE_STAGING_DIR).exists()
    assert json.loads((brain_dir / "learning_state.json").read_text())["total_trades"] == 6


def test_model_writes_never_truncate_the_existing_file(tmp_path):
    from backend.utils.secure_pickle import secure_dump_to_path, secure_dumps
    path = tmp_path / "ml_classifier.joblib"
    model = LogisticRegression().fit(_X, _Y_DIR)
    secure_dump_to_path(model, path)
    before = path.read_bytes()
    assert before == secure_dumps(model)  # file bytes unchanged by the atomic write
    with pytest.raises(RuntimeError, match="cannot pickle"):
        secure_dump_to_path(_Unpicklable(), path)
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["ml_classifier.joblib"]


def test_full_save_publishes_model_files_with_unchanged_bytes_and_fingerprints(tmp_path):
    from backend.organism.research_baseline import _fingerprint
    from backend.utils.secure_pickle import secure_dumps, secure_loads
    brain_dir = tmp_path / "brain"
    sg = _signal_gen(5, ensemble=_ensemble())
    assert _full_save(OrganismBrain(brain_dir), 5, signal_gen=sg) is True
    # Same file name and format as before: [length][pickle][HMAC] of the object.
    assert (brain_dir / "ml_classifier.joblib").read_bytes() == secure_dumps(sg._clf)
    assert (brain_dir / "ml_last_val_X.joblib").read_bytes() == secure_dumps(sg._last_val_X)
    clf = secure_loads((brain_dir / "ml_classifier.joblib").read_bytes())
    assert _fingerprint(clf) == _fingerprint(sg._clf)
    pair = secure_loads((brain_dir / "ensemble_lin_clf.joblib").read_bytes())
    assert _fingerprint(pair) == _fingerprint(sg._ensemble._models[0][0])


# ═════════════════════════════════════════════════════════════════════════
# C12-03 — the trained-overwrite guard holds after a close_accounting restore
# ═════════════════════════════════════════════════════════════════════════

def test_guard_blocks_untrained_overwrite_even_with_restored_trade_totals(tmp_path, caplog):
    brain_dir = tmp_path / "brain"
    assert _full_save(OrganismBrain(brain_dir), 5, ensemble=_ensemble()) is True
    before = _head_files(brain_dir)
    # A brain object whose load failed, with learner totals restored by
    # close_accounting (generation 0, untrained models, default params).
    fresh = OrganismBrain(brain_dir)
    restored = _learner(7, generation=0)
    untrained = _signal_gen(0, trained=False)
    with caplog.at_level(logging.ERROR, logger="backend.organism.brain_persistence"):
        assert fresh.save(signal_gen=untrained, learner=restored, equity_curve=[1.0],
                          all_trades=[], epoch_metrics=[], force=True) is False
        assert _essential_save(fresh, 7, signal_gen=untrained, learner=restored) is False
    assert _head_files(brain_dir) == before  # no model removed, no runtime file written
    messages = [r.getMessage() for r in caplog.records]
    assert any("BRAIN SAVE BLOCKED (save)" in m for m in messages)
    assert any("BRAIN SAVE BLOCKED (save_essential_state)" in m and "No file was written" in m
               for m in messages)
    # Break-glass still works.
    assert fresh.save(signal_gen=untrained, learner=restored, equity_curve=[1.0],
                      all_trades=[], epoch_metrics=[], force=True, allow_reset=True,
                      reset_reason="test break-glass") is True
    assert not (brain_dir / "ml_classifier.joblib").exists()


def _trained_engine(brain_dir: Path):
    from unittest.mock import MagicMock
    from backend.organism.continuous_learner import TradeRecord
    from backend.organism.live_engine import OrganismLiveEngine
    engine = OrganismLiveEngine(
        data_client=MagicMock(), order_service=MagicMock(), positions_service=MagicMock(),
        brain_dir=str(brain_dir), universe=["AAPL"],
    )
    sg = engine.signal_gen
    sg._clf = LogisticRegression().fit(_X, _Y_DIR)
    sg._reg = LinearRegression().fit(_X, _Y_RET)
    sg._is_trained = True
    sg._feature_cols = ["f0", "f1", "f2", "f3"]
    sg.generation = 3
    sg._last_val_X, sg._last_val_y_dir, sg._last_val_y_ret = _X[:10], _Y_DIR[:10], _Y_RET[:10]
    sg._ensemble = _ensemble()
    trades = [TradeRecord(symbol="AAPL", direction=1, entry_price=100.0, exit_price=101.0,
                          entry_bar=i, exit_bar=i + 1, shares=1, pnl=1.0, exit_reason="tp",
                          predicted_return=0.01, actual_return=0.01, confidence=0.6)
              for i in range(7)]
    engine._all_trades = list(trades)
    engine.learner.trade_history = list(trades)
    engine.learner.state.total_trades = 7
    engine.learner.state.cumulative_pnl = 7.0
    engine.learner.state.generation = 3
    engine.evolved_params.stop_atr_scale = 0.985
    return engine


def test_failed_load_plus_close_accounting_restore_cannot_wipe_a_trained_brain(tmp_path, monkeypatch):
    """The verifier's v3 scenario end to end: HMAC secret changed -> load()
    False -> close_accounting.restore(startup) restores learner totals -> the
    engine's tick save, shutdown save and admin force save must all be refused
    and leave the trained HEAD byte-identical."""
    from unittest.mock import MagicMock
    from backend.organism import close_accounting
    from backend.organism.live_engine import OrganismLiveEngine

    brain_dir = tmp_path / "brain"
    original_secret = os.environ["PICKLE_HMAC_SECRET"]
    first = _trained_engine(brain_dir)
    assert first.force_save_brain()["success"] is True
    assert first.force_save_brain()["success"] is True  # a backup exists too
    before = _head_files(brain_dir)
    counters_before = json.loads(before.pop("extra_counters.json"))

    monkeypatch.setenv("PICKLE_HMAC_SECRET", "a-rotated-secret")
    engine = OrganismLiveEngine(
        data_client=MagicMock(), order_service=MagicMock(), positions_service=MagicMock(),
        brain_dir=str(brain_dir), universe=["AAPL"],
    )
    assert engine.brain.load() is False
    close_accounting.restore(engine, close_accounting.read(brain_dir), startup=True)
    assert engine.learner.state.total_trades == 7 and not engine.signal_gen.is_trained
    watchdog = engine._watchdog_last_brain_save_tick = 41
    engine._tick_count = 99

    engine._save_brain()                                   # gate passes -> full save
    engine.brain.walk_forward_gate = lambda *a, **k: (False, "regression")
    engine._save_brain()                                   # gate blocks -> essential save
    assert engine.force_save_brain()["success"] is False   # admin / shutdown save
    after = _head_files(brain_dir)
    counters_after = json.loads(after.pop("extra_counters.json"))
    assert after == before  # models, evolved params, manifest, ml/learning state intact
    # extra_counters.json: only the engine's CORE-013 standalone exit-level
    # persistence (outside the brain save, unchanged here) may touch it.
    standalone = {"exit_levels", "entry_metadata", "pending_entry_order_ids", "pending_entry_since"}
    assert {k: v for k, v in counters_after.items() if k not in standalone} == \
        {k: v for k, v in counters_before.items() if k not in standalone}
    assert engine._watchdog_last_brain_save_tick == watchdog
    assert engine._brain_save_consecutive_failures == 3

    # With the original secret the trained brain is still there.
    monkeypatch.setenv("PICKLE_HMAC_SECRET", original_secret)
    restored = OrganismBrain(brain_dir)
    assert restored.load() is True and restored._loaded_from == restored.brain_dir
    assert restored.clf is not None and restored.evolved_params["stop_atr_scale"] == 0.985


def test_existing_trained_incoming_untrained_with_trades_is_blocked(tmp_path):
    brain = OrganismBrain(tmp_path / "brain")
    assert _full_save(brain, 5) is True
    blocked, reason = brain._check_trained_overwrite_guard(
        brain.brain_dir, _signal_gen(5, trained=False), _learner(10, generation=5))
    assert blocked and "ml_is_trained=True" in reason and "incoming" in reason
    blocked, _ = brain._check_trained_overwrite_guard(
        brain.brain_dir, _signal_gen(5), _learner(10, generation=5))
    assert not blocked


# ═════════════════════════════════════════════════════════════════════════
# C12-04 — unsigned pickles fail closed (production pickles are all signed)
# ═════════════════════════════════════════════════════════════════════════

class _SideEffect:
    """Unpickling this creates ``marker`` — proof that a file was deserialized."""

    def __init__(self, marker: Path):
        self.marker = str(marker)

    def __reduce__(self):
        return (Path.touch, (Path(self.marker),))


def _write_unsigned(path: Path, marker: Path) -> None:
    import pickle
    path.write_bytes(pickle.dumps(_SideEffect(marker)))


def test_unsigned_main_model_is_never_deserialized_and_falls_back(tmp_path, caplog):
    """C12-04 review: an unsigned listed model makes the generation incomplete
    (as a missing one does): the newest complete backup is used, never this
    HEAD without models; without a usable backup the load fails closed."""
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    assert _full_save(brain, 6) is True  # the backup of generation 5 is minted first
    marker = tmp_path / "deserialized"
    _write_unsigned(brain_dir / "ml_classifier.joblib", marker)
    fresh = OrganismBrain(brain_dir)
    with caplog.at_level(logging.CRITICAL, logger="backend.organism.brain_persistence"):
        assert fresh.load() is True
    assert not marker.exists()
    assert fresh._loaded_from.parent.name == "backups"
    assert fresh.clf is not None and fresh.reg is not None and fresh.learning_state["total_trades"] == 5
    assert any("unsigned or torn pickle" in r.getMessage() and "ml_classifier.joblib" in r.getMessage()
               for r in caplog.records if r.levelno == logging.CRITICAL)

    shutil.rmtree(brain_dir / "backups")
    assert OrganismBrain(brain_dir).load() is False   # fail closed, nothing deserialized
    assert not marker.exists()


def test_unsigned_main_model_in_a_brain_without_inventory_also_falls_back(tmp_path):
    """A legacy brain (timestamp sentinel, no inventory): _load_ml_models raises
    for the unsigned model, so the PP-2 fallback runs, as with older code."""
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    assert _full_save(brain, 6) is True
    (brain_dir / SAVE_COMPLETE_SENTINEL).write_text("2026-09-28T19:55:00+00:00")
    marker = tmp_path / "deserialized"
    _write_unsigned(brain_dir / "ml_regressor.joblib", marker)
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True and not marker.exists()
    assert fresh._loaded_from.parent.name == "backups" and fresh.reg is not None


@pytest.mark.parametrize("damage", ["half", "zero_bytes"])
def test_torn_signed_model_recovers_from_the_backup_like_the_pre_fix_code(tmp_path, damage):
    """The reviewer's probe A: a torn (truncated) signed classifier failed the
    'signed' length check, so the fix loaded HEAD without models where the
    pre-fix code's joblib.load raised and the PP-2 fallback recovered."""
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    assert _full_save(brain, 6) is True
    clf = brain_dir / "ml_classifier.joblib"
    raw = clf.read_bytes()
    clf.write_bytes(raw[: len(raw) // 2] if damage == "half" else b"")
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True
    assert fresh._loaded_from.parent.name == "backups"
    assert _digest(fresh)["models"] == (True, True)
    assert fresh.learning_state["total_trades"] == 5 and fresh.extra_counters["tick_count"] == 105


def test_unsigned_listed_cache_or_ensemble_pair_uses_the_backups_signed_copies(tmp_path, caplog):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5, ensemble=_ensemble()) is True
    assert _full_save(brain, 6, ensemble=_ensemble()) is True
    marker = tmp_path / "deserialized"
    _write_unsigned(brain_dir / "ml_last_val_X.joblib", marker)
    _write_unsigned(brain_dir / "ensemble_lin2_reg.joblib", marker)
    fresh = OrganismBrain(brain_dir)
    with caplog.at_level(logging.CRITICAL, logger="backend.organism.brain_persistence"):
        assert fresh.load() is True
    assert fresh._loaded_from.parent.name == "backups"
    critical = [r.getMessage() for r in caplog.records if r.levelno == logging.CRITICAL]
    assert any("ml_last_val_X.joblib" in m and "ensemble_lin2_reg.joblib" in m for m in critical)
    target = SimpleNamespace(load_calibration=lambda c: None,
                             _ensemble=EnsemblePredictor(n_estimators=3, max_depth=2), _xgb_params={})
    assert fresh.apply_to_signal_generator(target) is True
    assert not marker.exists()
    assert np.array_equal(target._last_val_X, _X[:10])           # the backup's signed copy
    assert target._ensemble.model_names == ["lin", "lin2"]
    assert "rejected HEAD" in fresh.full_save_required()


def test_unsigned_cache_and_ensemble_pair_in_a_brain_without_inventory_are_skipped(tmp_path, caplog):
    """No inventory (a brain last saved by older code): an unsigned S17 cache or
    ensemble file is never deserialized and is skipped like a missing one."""
    brain_dir = tmp_path / "brain"
    assert _full_save(OrganismBrain(brain_dir), 5, ensemble=_ensemble()) is True
    (brain_dir / SAVE_COMPLETE_SENTINEL).write_text("2026-09-28T19:55:00+00:00")
    marker = tmp_path / "deserialized"
    _write_unsigned(brain_dir / "ml_last_val_X.joblib", marker)
    _write_unsigned(brain_dir / "ensemble_lin2_reg.joblib", marker)
    brain = OrganismBrain(brain_dir)
    assert brain.load() is True and brain._loaded_from == brain.brain_dir
    target = SimpleNamespace(load_calibration=lambda c: None,
                             _ensemble=EnsemblePredictor(n_estimators=3, max_depth=2), _xgb_params={})
    with caplog.at_level(logging.CRITICAL):
        assert brain.apply_to_signal_generator(target) is True
    assert not marker.exists()
    assert getattr(target, "_last_val_X", None) is None          # like a missing cache
    assert np.array_equal(target._last_val_y_dir, _Y_DIR[:10])   # signed caches load
    assert target._ensemble.model_names == ["lin"]               # pair skipped like missing
    critical = [r.getMessage() for r in caplog.records if r.levelno == logging.CRITICAL]
    assert any("ml_last_val_X.joblib" in m for m in critical)
    assert any("ensemble_lin2_reg.joblib" in m for m in critical)


def test_header_only_signed_check_matches_is_signed_pickle(tmp_path):
    from backend.utils.secure_pickle import is_signed_pickle, is_signed_pickle_file, secure_dumps
    signed = secure_dumps({"a": list(range(50))})
    import pickle
    samples = [signed, signed[: len(signed) // 2], signed[:-1], signed + b"x", b"", b"\x00" * 3,
               pickle.dumps({"a": 1}), signed[:4] + b"\x00" * 40]
    for index, data in enumerate(samples):
        path = tmp_path / f"s{index}.joblib"
        path.write_bytes(data)
        assert is_signed_pickle_file(path) is is_signed_pickle(data), index
    assert is_signed_pickle_file(tmp_path / "absent.joblib") is False


def test_signed_file_with_a_foreign_key_still_fails_the_load(tmp_path, monkeypatch):
    brain_dir = tmp_path / "brain"
    assert _full_save(OrganismBrain(brain_dir), 5) is True
    shutil.rmtree(brain_dir / "backups")
    monkeypatch.setenv("PICKLE_HMAC_SECRET", "another-secret")
    assert OrganismBrain(brain_dir).load() is False


# ═════════════════════════════════════════════════════════════════════════
# C12-05 — model_metrics_history survives essential saves
# ═════════════════════════════════════════════════════════════════════════

def test_model_metrics_history_survives_essential_saves(tmp_path):
    from backend.organism.ml_signal import ModelMetrics
    metrics = [ModelMetrics(generation=g, accuracy=0.5 + g / 100, f1=0.4) for g in (1, 2)]
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5, learner=_learner(5, metrics=metrics)) is True
    for n in (6, 7):
        assert _essential_save(brain, n, learner=_learner(n, metrics=metrics)) is True
    history = json.loads((brain_dir / "ml_state.json").read_text())["model_metrics_history"]
    assert [h["generation"] for h in history] == [1, 2]
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True
    target = SimpleNamespace(state=None, trade_history=[], _reference_features=None,
                             _bars_since_retrain=0)
    assert fresh.apply_to_learner(target) is True
    assert [m.generation for m in target.state.model_metrics] == [1, 2]


def test_ml_state_is_written_once_per_save_with_its_history(tmp_path, monkeypatch):
    """Review: a second read-merge-write of ml_state.json left a window in
    which a kill dropped the history again."""
    from backend.organism.ml_signal import ModelMetrics
    metrics = [ModelMetrics(generation=3, accuracy=0.55)]
    writes: list[dict] = []
    real_write_json = bp._write_json

    def recording(path, data):
        if Path(path).name == "ml_state.json":
            writes.append(json.loads(json.dumps(data, default=str)))
        return real_write_json(path, data)

    monkeypatch.setattr(bp, "_write_json", recording)
    brain = OrganismBrain(tmp_path / "brain")
    assert _full_save(brain, 5, learner=_learner(5, metrics=metrics)) is True
    assert _essential_save(brain, 6, learner=_learner(6, metrics=metrics)) is True
    assert len(writes) == 2
    assert all([h["generation"] for h in w["model_metrics_history"]] == [3] for w in writes)


# ═════════════════════════════════════════════════════════════════════════
# C12-06 — saves that did not happen are reported, not claimed
# ═════════════════════════════════════════════════════════════════════════

def test_essential_save_write_failure_is_reported(tmp_path, monkeypatch, caplog):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    real_write_json = bp._write_json

    def disk_full(path, data):
        if Path(path).name == "extra_counters.json":
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_write_json(path, data)

    monkeypatch.setattr(bp, "_write_json", disk_full)
    with caplog.at_level(logging.ERROR, logger="backend.organism.brain_persistence"):
        assert _essential_save(brain, 6) is False
    assert any("Failed to save essential state" in r.getMessage() for r in caplog.records)


def test_save_with_the_lock_held_elsewhere_is_reported(tmp_path):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    before = _head_files(brain_dir)
    holder = _BrainLock(brain_dir / LOCK_FILE)
    holder.acquire()
    try:
        assert _full_save(brain, 6) is False
        assert _essential_save(brain, 6) is False
    finally:
        holder.release()
    assert _head_files(brain_dir) == before
    assert _full_save(brain, 6) is True


def test_essential_save_reports_an_unopenable_lock_or_directory(tmp_path, monkeypatch, caplog):
    """Review: mkdir() and the lock file's open() ran outside the try, so an
    OSError escaped save_essential_state despite its 'never raises'."""
    brain = OrganismBrain(tmp_path / "brain")
    assert _full_save(brain, 5) is True

    def denied(self):
        raise PermissionError(errno.EACCES, "Permission denied", str(self._path))

    monkeypatch.setattr(_BrainLock, "acquire", denied)
    with caplog.at_level(logging.ERROR, logger="backend.organism.brain_persistence"):
        assert _essential_save(brain, 6) is False
    monkeypatch.undo()
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x")
    with caplog.at_level(logging.ERROR, logger="backend.organism.brain_persistence"):
        assert _essential_save(OrganismBrain(blocker / "brain"), 6) is False
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert sum("cannot create the brain directory or open its lock file" in m for m in errors) == 2


def _head_rejected_by_a_missing_cache(brain_dir: Path, *, ensemble=None) -> OrganismBrain:
    """Generation 6 in HEAD lacks a listed cache: a load restores generation 5."""
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5, ensemble=ensemble) is True
    assert _full_save(brain, 6, ensemble=ensemble) is True
    (brain_dir / "ml_last_val_X.joblib").unlink()
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True and fresh._loaded_from.parent.name == "backups"
    return fresh


def test_essential_save_into_a_rejected_head_is_reported_not_claimed(tmp_path, caplog):
    """The reviewer's probe F: after a backup fallback, essential saves wrote
    into the HEAD every load rejects and returned True; WW-1 backed it up."""
    brain_dir = tmp_path / "brain"
    fresh = _head_rejected_by_a_missing_cache(brain_dir)
    before = _head_files(brain_dir)
    backups = sorted(p.name for p in (brain_dir / "backups").iterdir())
    assert "rejected HEAD" in fresh.full_save_required()
    with caplog.at_level(logging.ERROR, logger="backend.organism.brain_persistence"):
        assert _essential_save(fresh, 7, signal_gen=_signal_gen(5)) is False
    assert any("NOT persisted" in r.getMessage() and "rejected HEAD" in r.getMessage()
               for r in caplog.records)
    assert _head_files(brain_dir) == before                                  # nothing written
    assert sorted(p.name for p in (brain_dir / "backups").iterdir()) == backups  # no WW-1 copy

    # A full save repairs HEAD without backing the rejected HEAD up.
    assert _full_save(fresh, 7) is True
    assert sorted(p.name for p in (brain_dir / "backups").iterdir()) == backups
    assert fresh.full_save_required() is None
    assert _essential_save(fresh, 8) is True
    reloaded = OrganismBrain(brain_dir)
    assert reloaded.load() is True and reloaded._loaded_from == reloaded.brain_dir
    assert reloaded.learning_state["total_trades"] == 8


def _engine_on(brain_dir: Path):
    from unittest.mock import MagicMock
    from backend.organism.live_engine import OrganismLiveEngine
    return OrganismLiveEngine(
        data_client=MagicMock(), order_service=MagicMock(), positions_service=MagicMock(),
        brain_dir=str(brain_dir), universe=["AAPL"],
    )


def test_engine_takes_a_full_save_after_a_backup_fallback(tmp_path, caplog):
    from backend.organism import close_accounting
    brain_dir = tmp_path / "brain"
    first = _trained_engine(brain_dir)
    assert first.force_save_brain()["success"] and first.force_save_brain()["success"]
    (brain_dir / "ml_last_val_X.joblib").unlink()                # HEAD now rejected
    engine = _engine_on(brain_dir)
    # The restart path of initialize(): brain load (backup fallback), models,
    # learner, then the close-accounting restore of the trade ledger.
    assert engine.brain.load() is True and engine.brain._loaded_from.parent.name == "backups"
    assert engine.brain.apply_to_signal_generator(engine.signal_gen) is True
    assert engine.brain.apply_to_learner(engine.learner) is True
    close_accounting.restore(engine, close_accounting.read(brain_dir), startup=True)
    backups = sorted(p.name for p in (brain_dir / "backups").iterdir())
    engine.brain.walk_forward_gate = lambda *a, **k: (False, "regression")
    engine._tick_count, engine._watchdog_last_brain_save_tick = 500, 400
    with caplog.at_level(logging.WARNING):
        engine._save_brain()
    assert any("taking a gated full save" in r.getMessage() for r in caplog.records)
    assert engine._consecutive_wf_skips == 0 and engine._watchdog_last_brain_save_tick == 500
    assert engine.brain.full_save_required() is None
    assert sorted(p.name for p in (brain_dir / "backups").iterdir()) == backups
    reloaded = OrganismBrain(brain_dir)
    assert reloaded.load() is True and reloaded._loaded_from == reloaded.brain_dir
    assert reloaded.clf is not None and (brain_dir / "ml_last_val_X.joblib").is_file()
    # From then on the gate's essential saves apply again.
    engine._tick_count = 520
    engine._save_brain()
    assert engine._consecutive_wf_skips == 1 and engine._watchdog_last_brain_save_tick == 520


def test_standalone_exit_level_write_settles_a_pending_journal(tmp_path):
    """The reviewer's probe B2: after a swap failed in-process, the engine's
    standalone exit-level write changed the published extra_counters.json and
    every essential save failed until the forced full save (cycle 12)."""
    brain_dir = tmp_path / "brain"
    engine = _gated_engine(brain_dir)
    assert engine.force_save_brain()["success"] is True
    real_replace = os.replace

    def eio(src, dst, *a, **kw):
        if Path(src).parent.name == SWAP_STAGING_DIR and Path(dst) == brain_dir / "governance_state.json":
            raise OSError(errno.EIO, "injected EIO on publish")
        return real_replace(src, dst, *a, **kw)

    bp.os.replace = eio
    try:
        assert engine.force_save_brain()["success"] is False
    finally:
        bp.os.replace = real_replace
    assert (brain_dir / SWAP_JOURNAL_FILE).is_file()
    engine.brain.walk_forward_gate = lambda *a, **k: (False, "regression")
    engine._pending_entry_order_ids["NVDA"] = "ord-new"   # changed before the next cycle
    engine._tick_count += 20
    engine._save_brain()
    assert not (brain_dir / SWAP_JOURNAL_FILE).exists()
    assert engine._watchdog_last_brain_save_tick == engine._tick_count   # the cycle persisted
    assert engine._brain_save_consecutive_failures == 0
    assert not _swap_forensics(brain_dir)                                 # rolled forward
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True and fresh._loaded_from == fresh.brain_dir
    assert fresh.extra_counters["pending_entry_order_ids"]["NVDA"] == "ord-new"


def test_daily_loss_write_during_a_pending_journal_does_not_wedge_saves(tmp_path):
    """_persist_daily_loss_state (frozen surface) also writes extra_counters.json
    outside a save: the next essential save keeps that newer HEAD and saves."""
    brain_dir = tmp_path / "brain"
    engine = _gated_engine(brain_dir)
    real_replace = os.replace

    def eio(src, dst, *a, **kw):
        if Path(src).parent.name == SWAP_STAGING_DIR and Path(dst) == brain_dir / "governance_state.json":
            raise OSError(errno.EIO, "injected EIO on publish")
        return real_replace(src, dst, *a, **kw)

    bp.os.replace = eio
    try:
        assert engine.force_save_brain()["success"] is False
    finally:
        bp.os.replace = real_replace
    engine._daily_loss_date, engine._daily_starting_equity = "2026-10-05", 98_765.0
    engine._persist_daily_loss_state()
    assert engine.brain.save_essential_state(
        signal_gen=engine.signal_gen, learner=engine.learner, all_trades=engine._all_trades,
        extra_counters=engine._build_extra_counters(), governance_controller=engine.governance,
        regime_detector=engine.regime_detector,
    ) is True
    assert not (brain_dir / SWAP_JOURNAL_FILE).exists() and len(_swap_forensics(brain_dir)) == 1
    assert "kept over a stale" in engine.brain.full_save_required()
    fresh = OrganismBrain(brain_dir)
    assert fresh.load() is True and fresh._loaded_from == fresh.brain_dir
    assert fresh.extra_counters["daily_starting_equity"] == 98_765.0


def test_shutdown_save_that_did_not_persist_logs_an_error(monkeypatch):
    import asyncio
    from backend.api import lifespan

    records: list[tuple[str, str]] = []

    class _Recorder:
        def _log(self, level, msg, *args, **_kw):
            records.append((level, msg % args if args else msg))

        def info(self, msg, *args, **kw):
            self._log("info", msg, *args, **kw)

        def warning(self, msg, *args, **kw):
            self._log("warning", msg, *args, **kw)

        def error(self, msg, *args, **kw):
            self._log("error", msg, *args, **kw)

    monkeypatch.setattr(lifespan, "logger", _Recorder())

    def ctx(force_save_brain):
        engine = SimpleNamespace(force_save_brain=force_save_brain)
        return {"organism_scheduler": SimpleNamespace(_engine=engine)}

    def boom():
        raise RuntimeError("disk gone")

    asyncio.run(lifespan._shut_brain_save(None, ctx(lambda: {"success": False, "error": "lock held"})))
    assert records == [("error", "Defensive brain save at shutdown did NOT persist: lock held")]
    records.clear()
    asyncio.run(lifespan._shut_brain_save(None, ctx(lambda: {"success": True})))
    assert records == [("info", "Brain saved at shutdown (lifespan defensive save)")]
    records.clear()
    asyncio.run(lifespan._shut_brain_save(None, ctx(boom)))
    assert records == [("error", "Defensive brain save failed at shutdown: disk gone")]


def _gated_engine(brain_dir: Path):
    engine = _trained_engine(brain_dir)
    assert engine.force_save_brain()["success"] is True
    engine._tick_count = 500
    engine._watchdog_last_brain_save_tick = 400
    return engine


def test_engine_does_not_claim_failed_essential_saves(tmp_path, monkeypatch, caplog):
    engine = _gated_engine(tmp_path / "brain")
    engine.brain.walk_forward_gate = lambda *a, **k: (False, "regression")
    real_write_json = bp._write_json

    def disk_full(path, data):
        if Path(path).name == "extra_counters.json":
            raise OSError(errno.ENOSPC, "No space left on device")
        return real_write_json(path, data)

    monkeypatch.setattr(bp, "_write_json", disk_full)
    with caplog.at_level(logging.WARNING):
        for tick in (520, 540, 560):
            engine._tick_count = tick
            engine._save_brain()  # never raises into the tick
    assert engine._watchdog_last_brain_save_tick == 400
    errors = [r for r in caplog.records if "BRAIN SAVE NOT PERSISTED" in r.getMessage()]
    assert len(errors) == 3 and all(r.levelno == logging.ERROR for r in errors)
    critical = [r for r in caplog.records if r.levelno == logging.CRITICAL
                and "BRAIN SAVES FAILING REPEATEDLY" in r.getMessage()]
    assert len(critical) == 1  # the watchdog's CRITICAL scan pages on this

    monkeypatch.setattr(bp, "_write_json", real_write_json)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        engine._tick_count = 580
        engine._save_brain()
    assert engine._watchdog_last_brain_save_tick == 580
    assert engine._brain_save_consecutive_failures == 0
    assert any("persisted again after 3" in r.getMessage() for r in caplog.records)


def test_engine_does_not_claim_a_full_save_skipped_by_the_lock(tmp_path):
    engine = _gated_engine(tmp_path / "brain")
    engine._consecutive_wf_skips = 12  # at the walk-forward ceiling
    engine.brain.walk_forward_gate = lambda *a, **k: (False, "regression")
    holder = _BrainLock(engine.brain.brain_dir / LOCK_FILE)
    holder.acquire()
    try:
        engine._save_brain()
        assert engine._consecutive_wf_skips == 13      # not reset: no save landed
        assert engine._watchdog_last_brain_save_tick == 400
        result = engine.force_save_brain()
        assert result["success"] is False and "did not publish" in result["error"]
    finally:
        holder.release()
    engine._save_brain()
    assert engine._consecutive_wf_skips == 0
    assert engine._watchdog_last_brain_save_tick == engine._tick_count


# ═════════════════════════════════════════════════════════════════════════
# C12-09 — durability: files, then the directory, then the sentinel
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not Path("/proc/self/fd").is_dir(), reason="needs /proc fd links")
def test_full_save_fsyncs_files_then_directory_then_sentinel(tmp_path, monkeypatch):
    brain_dir = (tmp_path / "brain").resolve()
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5) is True
    events: list[tuple[str, str]] = []
    real_fsync, real_replace, real_unlink = os.fsync, os.replace, os.unlink

    def fsync(fd):
        try:
            events.append(("fsync", os.readlink(f"/proc/self/fd/{fd}")))
        except OSError:
            pass
        return real_fsync(fd)

    def replace(src, dst, *a, **kw):
        events.append(("replace", os.fspath(dst)))
        return real_replace(src, dst, *a, **kw)

    def unlink(path, *a, **kw):
        events.append(("unlink", os.fspath(path)))
        return real_unlink(path, *a, **kw)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(os, "unlink", unlink)
    assert _full_save(brain, 6) is True

    stage = str(brain_dir / SWAP_STAGING_DIR)
    staged = [(i, p) for i, (k, p) in enumerate(events)
              if k == "replace" and Path(p).parent == Path(stage)]
    assert staged, "no staged file was written"
    for index, path in staged:
        # Each staged file's temp copy was fsynced before its rename.
        assert any(
            kind == "fsync" and Path(p).parent == Path(stage) and Path(path).name in Path(p).name
            and p.endswith(".tmp") for kind, p in events[:index]
        ), f"{path} renamed without fsync"
    journal = [i for i, (k, p) in enumerate(events)
               if k == "replace" and Path(p) == brain_dir / SWAP_JOURNAL_FILE]
    assert journal and any(k == "fsync" and p == stage for k, p in events[:journal[0]]), \
        "staging dir not fsynced before the journal"
    published = [i for i, (k, p) in enumerate(events)
                 if k == "replace" and Path(p).parent == brain_dir
                 and Path(p).name not in {SAVE_COMPLETE_SENTINEL, SWAP_JOURNAL_FILE}]
    sentinel = [i for i, (k, p) in enumerate(events)
                if k == "replace" and Path(p) == brain_dir / SAVE_COMPLETE_SENTINEL]
    dir_syncs = [i for i, (k, p) in enumerate(events) if k == "fsync" and Path(p) == brain_dir]
    assert published and sentinel
    # Review: the old sentinel's unlink is durable before the first rename, so
    # a timestamp sentinel next to a journal can only be newer (older code).
    dropped = [i for i, (k, p) in enumerate(events)
               if k == "unlink" and Path(p) == brain_dir / SAVE_COMPLETE_SENTINEL]
    assert dropped and dropped[0] < published[0]
    assert any(dropped[0] < i < published[0] for i in dir_syncs), \
        "brain_dir was not fsynced between the sentinel unlink and the first rename"
    assert any(published[-1] < i < sentinel[0] for i in dir_syncs), \
        "brain_dir was not fsynced between the last rename and the sentinel"
    assert any(k == "fsync" and Path(p).parent == brain_dir and SAVE_COMPLETE_SENTINEL in Path(p).name
               for k, p in events[:sentinel[0]]), "sentinel not fsynced before its rename"
    assert any(i > sentinel[0] for i in dir_syncs), "sentinel rename not made durable"


def test_trade_history_temp_file_is_fsynced(tmp_path, monkeypatch):
    from backend.organism.continuous_learner import TradeRecord
    synced = []
    real_fsync = os.fsync

    def fsync(fd):
        try:
            synced.append(os.readlink(f"/proc/self/fd/{fd}"))
        except OSError:
            synced.append(fd)
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    trade = TradeRecord(symbol="AAPL", direction=1, entry_price=1.0, exit_price=2.0, entry_bar=0,
                        exit_bar=1, shares=1, pnl=1.0, exit_reason="tp", predicted_return=0.0,
                        actual_return=1.0, confidence=0.5)
    OrganismBrain(tmp_path / "b")._save_trade_history(tmp_path, [trade])
    if Path("/proc/self/fd").is_dir():
        assert any(str(p).endswith("trade_history.csv.tmp") for p in synced)
    assert (tmp_path / "trade_history.csv").is_file()
    assert not (tmp_path / "trade_history.csv.tmp").exists()


# ═════════════════════════════════════════════════════════════════════════
# Compatibility — production copy and rollback to the pre-fix code
# ═════════════════════════════════════════════════════════════════════════

_SUMMARY_SCRIPT = r"""
import hashlib, json, sys
from pathlib import Path
import numpy as np
from backend.organism.brain_persistence import OrganismBrain
from backend.organism.ml_signal import MLSignalGenerator

def norm(value):
    return json.loads(json.dumps(value, sort_keys=True, default=str))

brain = OrganismBrain(Path(sys.argv[1]))
loaded = brain.load() if brain.exists else False
sg = MLSignalGenerator()
applied = brain.apply_to_signal_generator(sg)
ensemble = sg._ensemble
prediction = None
if applied:
    x = np.linspace(-1.0, 1.0, 4).reshape(1, -1)
    prediction = [float(sg._clf.predict_proba(x)[0][1]), float(sg._reg.predict(x)[0])]
print(json.dumps({
    "loaded": loaded,
    "applied": applied,
    "manifest": norm(brain._manifest),
    "ml_state": norm(brain.ml_state),
    "learning_state": norm(brain.learning_state),
    "extra_counters": norm(brain.extra_counters),
    "evolved_params": norm(brain.evolved_params),
    "governance": norm(brain.governance_state),
    "regime": norm(brain.regime_state),
    "evaluations": norm(brain.evaluation_event_history),
    "trades": hashlib.sha256(json.dumps(brain.trade_history, sort_keys=True, default=str).encode()).hexdigest(),
    "n_trades": len(brain.trade_history),
    "equity": norm(brain.equity_curve),
    "epochs": norm(brain.epoch_metrics),
    "reference": None if brain.reference_features is None else list(brain.reference_features.shape),
    "models": [type(brain.clf).__name__ if brain.clf is not None else None,
               type(brain.reg).__name__ if brain.reg is not None else None],
    "prediction": prediction,
    "ensemble": ensemble.model_names if applied and getattr(ensemble, "is_trained", False) else [],
    "ensemble_weights": norm(ensemble.get_weights()) if applied else {},
    "s17": [getattr(sg, a, None) is not None for a in ("_last_val_X", "_last_val_y_dir", "_last_val_y_ret")],
}, sort_keys=True))
"""


def _summary(code_root: Path, brain_dir: Path) -> dict:
    env = dict(os.environ, PYTHONPATH=str(code_root), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "-c", _SUMMARY_SCRIPT, str(brain_dir)],
        cwd=str(code_root), env=env, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def pre_fix_code(tmp_path_factory) -> Path:
    """The backend tree at the rollback target, extracted from git history."""
    try:
        subprocess.run(["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{PRE_FIX_COMMIT}^{{commit}}"],
                       check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pytest.skip(f"pre-fix commit {PRE_FIX_COMMIT} not available (shallow clone)")
    root = tmp_path_factory.mktemp("pre_fix_code")
    archive = subprocess.run(["git", "-C", str(REPO_ROOT), "archive", PRE_FIX_COMMIT, "backend"],
                             check=True, capture_output=True, timeout=120).stdout
    subprocess.run(["tar", "-x", "-C", str(root)], input=archive, check=True, timeout=120)
    assert "SWAP_JOURNAL_FILE" not in (root / "backend/organism/brain_persistence.py").read_text()
    return root


def test_brain_saved_by_this_code_loads_with_the_pre_fix_code(tmp_path, pre_fix_code):
    brain_dir = tmp_path / "brain"
    brain = OrganismBrain(brain_dir)
    from backend.organism.ml_signal import ModelMetrics
    metrics = [ModelMetrics(generation=1, accuracy=0.6)]
    assert _full_save(brain, 5, ensemble=_ensemble(), learner=_learner(5, metrics=metrics)) is True
    assert _essential_save(brain, 6, learner=_learner(6, metrics=metrics)) is True
    assert _full_save(brain, 7, ensemble=_ensemble(), learner=_learner(7, metrics=metrics)) is True
    assert _essential_save(brain, 8, learner=_learner(8, metrics=metrics)) is True
    for name in ("new", "old"):
        shutil.copytree(brain_dir, tmp_path / name, ignore=shutil.ignore_patterns("backups"))
    new = _summary(REPO_ROOT, tmp_path / "new")
    old = _summary(pre_fix_code, tmp_path / "old")
    assert old == new
    assert old["loaded"] and old["applied"] and old["models"] == ["LogisticRegression", "LinearRegression"]
    assert old["ensemble"] == ["lin", "lin2"] and all(old["s17"])
    assert old["learning_state"]["total_trades"] == 8 and old["extra_counters"]["tick_count"] == 108
    assert len(old["ml_state"]["model_metrics_history"]) == 1


_PRE_FIX_ESSENTIAL_SCRIPT = r"""
import json, sys
from types import SimpleNamespace
import numpy as np
from sklearn.linear_model import LinearRegression, LogisticRegression
from backend.organism.brain_persistence import OrganismBrain
from backend.organism.ensemble_models import EnsemblePredictor

rng = np.random.default_rng(20261005)
X = rng.normal(size=(80, 4))
Y_DIR, Y_RET = (X[:, 0] > 0).astype(int), X[:, 1] * 0.01
n = int(sys.argv[2])


class Persisted:
    def __init__(self, payload):
        self.payload = payload

    def to_persistence_dict(self):
        return dict(self.payload)


calibration = {"counts": [[0, 0]] * 5, "map": [1.0] * 5}
brain = OrganismBrain(sys.argv[1])
loaded = brain.load() if brain.exists else False
sg = SimpleNamespace(
    _is_trained=True, _clf=LogisticRegression().fit(X, Y_DIR), _reg=LinearRegression().fit(X, Y_RET),
    _ensemble=EnsemblePredictor(n_estimators=3, max_depth=2), _feature_cols=["f0", "f1", "f2", "f3"],
    _xgb_params={"max_depth": 3}, generation=n, train_window=100, _latest_metrics=None,
    calibration_to_dict=lambda: calibration, load_calibration=lambda data: None,
)
applied = brain.apply_to_signal_generator(sg)
learner = SimpleNamespace(
    state=SimpleNamespace(generation=n, total_trades=n, cumulative_pnl=-1.0 * n, best_sharpe=0.5,
                          total_bars_seen=0, retrain_count=0, drift_events=0, best_generation=0,
                          generation_accuracies=[], model_metrics=[],
                          evaluation_events=[{"generation": n, "accepted": True}]),
    trade_history=[], _reference_features=None, _bars_since_retrain=0,
)
before = brain.learning_state.get("total_trades")
brain.save_essential_state(
    signal_gen=sg, learner=learner, all_trades=[], equity_curve=[100_000.0 + i for i in range(n)],
    epoch_metrics=[{"epoch": i} for i in range(n)], peak_equity=100_000.0 + n,
    extra_counters={"tick_count": 100 + n, "daily_loss_halt": True,
                    "pending_entry_order_ids": {"MSFT": f"ord-{n}"}},
    governance_controller=Persisted({"trading_halted": True, "generation_marker": n}),
    regime_detector=Persisted({"history": [n], "sma_period": 200}),
)
print(json.dumps({"loaded": loaded, "applied": applied, "loaded_total": before}))
"""


def test_rollback_to_pre_fix_code_mid_swap_is_never_rolled_forward_over_its_state(
        tmp_path, pre_fix_code, monkeypatch, caplog):
    """Review blocking item (probe C2), with the real ee023515 code: the fixed
    code dies mid-swap after publishing the (frozen) ensemble; a rollback
    starts the pre-fix code, which ignores the journal, loads HEAD and stores
    newer runtime state (halt, pending MSFT entry) in an essential save,
    re-pickling the ensemble byte-identically; the fixed code is redeployed.
    The roll-forward used to put generation 6 back over that state."""
    from backend.utils.secure_pickle import secure_dumps, secure_loads
    brain_dir = tmp_path / "brain"
    ensemble = _ensemble()
    # Production property: frozen models loaded from disk re-pickle identically.
    ensemble._models = [(secure_loads(secure_dumps(c)), secure_loads(secure_dumps(r)), name, w)
                        for c, r, name, w in ensemble._models]
    ensemble._bump_state_version()
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5, ensemble=ensemble) is True
    _crash_full_save_before_publishing(monkeypatch, brain, "epoch_metrics.csv", 6, ensemble=ensemble)

    env = dict(os.environ, PYTHONPATH=str(pre_fix_code), PYTHONDONTWRITEBYTECODE="1")
    old = subprocess.run([sys.executable, "-c", _PRE_FIX_ESSENTIAL_SCRIPT, str(brain_dir), "7"],
                         cwd=str(pre_fix_code), env=env, capture_output=True, text=True, timeout=300)
    assert old.returncode == 0, old.stderr[-4000:]
    ran = json.loads(old.stdout.strip().splitlines()[-1])
    assert ran["loaded"] and ran["applied"] and ran["loaded_total"] == 5
    assert (brain_dir / SWAP_JOURNAL_FILE).is_file()                 # ignored by the old code
    assert bp._sentinel_kind(brain_dir / SAVE_COMPLETE_SENTINEL) == "legacy"
    head_before = _head_files(brain_dir)

    fresh = OrganismBrain(brain_dir)
    with caplog.at_level(logging.CRITICAL, logger="backend.organism.brain_persistence"):
        assert fresh.load() is True
    digest = _digest(fresh)
    assert fresh._loaded_from == fresh.brain_dir
    assert digest["learning"] == 7 and digest["governance"] == 7 and digest["halt"] is True
    assert digest["pending"] == {"MSFT": "ord-7"} and digest["models"] == (True, True)
    assert fresh.governance_state["trading_halted"] is True
    assert not (brain_dir / SWAP_JOURNAL_FILE).exists()
    assert any("STALE" in r.getMessage() and "REFUSED" in r.getMessage() for r in caplog.records)
    # HEAD kept exactly as the old code left it; only the journal is gone.
    after = _head_files(brain_dir)
    assert after == {k: v for k, v in head_before.items() if k != SWAP_JOURNAL_FILE}
    (forensic,) = _swap_forensics(brain_dir)
    assert (forensic / SWAP_JOURNAL_FILE).is_file() and (forensic / "staged" / MANIFEST_FILE).is_file()
    assert (forensic / "head" / "learning_state.json").read_bytes() == after["learning_state.json"]
    assert "kept over a stale" in fresh.full_save_required()

    # The pre-fix code still loads the kept HEAD (forensic dir present) ...
    shutil.copytree(brain_dir, tmp_path / "old_view", ignore=shutil.ignore_patterns("backups"))
    assert _summary(pre_fix_code, tmp_path / "old_view")["learning_state"]["total_trades"] == 7
    # ... and the next full save by the fixed code restores the inventory.
    sg = _signal_gen(7, ensemble=EnsemblePredictor(n_estimators=3, max_depth=2))
    assert fresh.apply_to_signal_generator(sg) is True
    assert _full_save(fresh, 8, signal_gen=sg) is True
    assert fresh.full_save_required() is None and _inventory(brain_dir)


@pytest.mark.skipif(not (PRODUCTION_BRAIN_COPY / MANIFEST_FILE).is_file(),
                    reason="private production brain copy not present")
def test_production_brain_copy_loads_exactly_as_before(tmp_path, pre_fix_code):
    before = {p.name: p.stat().st_mtime_ns for p in PRODUCTION_BRAIN_COPY.rglob("*")}
    for name in ("new", "old"):
        shutil.copytree(PRODUCTION_BRAIN_COPY, tmp_path / name)
        for path in (tmp_path / name).rglob("*"):
            path.chmod(0o755 if path.is_dir() else 0o644)
    new = _summary(REPO_ROOT, tmp_path / "new")
    old = _summary(pre_fix_code, tmp_path / "old")
    assert new == old
    assert new["loaded"] is True and new["n_trades"] > 0
    assert before == {p.name: p.stat().st_mtime_ns for p in PRODUCTION_BRAIN_COPY.rglob("*")}


@pytest.mark.skipif(not (PRODUCTION_BRAIN_COPY / MANIFEST_FILE).is_file(),
                    reason="private production brain copy not present")
def test_production_state_resaved_by_this_code_loads_with_the_pre_fix_code(tmp_path, pre_fix_code):
    from backend.organism.continuous_learner import ContinuousLearner
    from backend.organism.ml_signal import MLSignalGenerator
    source = tmp_path / "source"
    shutil.copytree(PRODUCTION_BRAIN_COPY, source)
    for path in source.rglob("*"):
        path.chmod(0o755 if path.is_dir() else 0o644)
    loaded = OrganismBrain(source)
    assert loaded.load() is True
    sg = MLSignalGenerator()
    learner = ContinuousLearner(sg)
    loaded.apply_to_signal_generator(sg)
    assert loaded.apply_to_learner(learner) is True
    target = OrganismBrain(tmp_path / "resaved")
    assert target.save(
        signal_gen=sg, learner=learner, equity_curve=list(loaded.equity_curve),
        all_trades=loaded.get_trade_records(), epoch_metrics=list(loaded.epoch_metrics),
        extra_counters=dict(loaded.extra_counters), evolved_params=dict(loaded.evolved_params),
    ) is True
    old = _summary(pre_fix_code, tmp_path / "resaved")
    assert old["loaded"] is True
    assert old["learning_state"]["total_trades"] == loaded.learning_state["total_trades"]
    assert old["extra_counters"] == json.loads(json.dumps(loaded.extra_counters, default=str))
    assert old["evolved_params"] == json.loads(json.dumps(loaded.evolved_params, default=str))
    assert old["n_trades"] == len(loaded.trade_history)


# ═════════════════════════════════════════════════════════════════════════
# Review — read-only pre-deploy check for unsigned pickles (C12-04 premise)
# ═════════════════════════════════════════════════════════════════════════

def _load_check_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_brain_pickles_signed", REPO_ROOT / "scripts/ops/check_brain_pickles_signed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tree_state(root: Path) -> dict:
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_pickle_check_script_reports_unsigned_and_torn_pickles_read_only(tmp_path, capsys):
    check = _load_check_script()
    brain_dir = tmp_path / "organism_brain"
    brain = OrganismBrain(brain_dir)
    assert _full_save(brain, 5, ensemble=_ensemble()) is True
    assert _full_save(brain, 6, ensemble=_ensemble()) is True      # backups/ has generation 5
    marker = tmp_path / "deserialized"
    (brain_dir / "previous_model").mkdir()
    _write_unsigned(brain_dir / "previous_model" / "clf.pkl", marker)  # never loaded: info only
    archive = tmp_path / "organism_brain_archive"
    skip = shutil.ignore_patterns("backups", "corrupt_head_*", ".brain*")
    shutil.copytree(brain_dir, archive / "2026-10-04T233000.000000Z", ignore=skip)
    shutil.copytree(brain_dir, archive / "2026-10-05T233000.000000Z", ignore=skip)
    _write_unsigned(archive / "2026-10-04T233000.000000Z" / "ml_regressor.joblib", marker)

    args = ["--brain-dir", str(brain_dir), "--archive-dir", str(archive)]
    assert check.main(args) == 0                                     # newest snapshot only
    out = capsys.readouterr().out
    assert "OK: every pickle the engine loads is signed" in out
    assert "previous_model/clf.pkl is not signed (never loaded by the engine)" in out
    assert check.main(args + ["--all-archives"]) == 1
    out = capsys.readouterr().out
    assert "UNSIGNED OR TORN" in out and "ml_regressor.joblib" in out

    clf = brain_dir / "ml_classifier.joblib"
    raw = clf.read_bytes()
    clf.write_bytes(raw[: len(raw) // 2])                            # torn signed model
    _write_unsigned(brain_dir / "ensemble_lin_reg.joblib", marker)    # unsigned ensemble file
    before = _tree_state(tmp_path)
    assert check.main(["--brain-dir", str(brain_dir), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    head, *backups = report["locations"]
    assert head["kind"] == "head"
    assert head["unsigned"] == ["ensemble_lin_reg.joblib", "ml_classifier.joblib"]
    assert head["info_unsigned"] == ["previous_model/clf.pkl"] and head["loaded_checked"] == 9
    assert backups and all(b["kind"] == "backup" and not b["unsigned"] for b in backups)
    assert report["status"] == "unsigned" and report["unsigned_loaded_pickles"] == 2
    assert not marker.exists()                                       # nothing was unpickled
    assert _tree_state(tmp_path) == before                           # nothing was modified

    assert check.main(["--brain-dir", str(tmp_path / "missing")]) == 2
    assert check.main(["--brain-dir", str(brain_dir), "--archive-dir", str(tmp_path / "nope")]) == 2
    capsys.readouterr()
