"""
Module 7 — Organism Brain Persistence.

Saves / loads the organism's entire learned state so each run
picks up exactly where the last one left off:

    ┌─────────────────────────────────────────────────────────────────┐
    │  organism_brain/                                                 │
    │    manifest.json        ← version, timestamp, generation #      │
    │    ml_classifier.joblib ← trained XGBClassifier                 │
    │    ml_regressor.joblib  ← trained XGBRegressor                  │
    │    ml_state.json        ← feature_cols, xgb_params, generation  │
    │    learning_state.json  ← LearningState (gen, PnL, best Sharpe) │
    │    trade_history.csv    ← All historical trades                  │
    │    reference_feats.csv  ← Drift-detection reference features    │
    │    equity_curve.csv     ← Full equity curve across all runs      │
    │    epoch_metrics.csv    ← All epoch metrics across all runs      │
    │    backups/             ← Last 5 brain snapshots (safety net)    │
    └─────────────────────────────────────────────────────────────────┘

Safety guarantees:
    * Per-file atomic writes (same-directory temp → fsync → rename)
    * Full saves stage a complete generation in ``.tmp_save`` and publish it
      through a journaled swap (audit 2026-10-05 C12-01): a crash mid-swap is
      rolled forward by the next load()/save() unless HEAD changed after the
      journal was written (then HEAD is kept and the journal retired), and a
      HEAD whose completion inventory lists a missing, unsigned or torn file
      is rejected (backup fallback) instead of loading that state as empty
    * Backup before every full save (and hourly from essential saves) —
      keep last 5 snapshots
    * Version manifest — detect incompatible brain formats
    * Graceful degradation — if brain is missing or corrupt, start fresh

Usage:
    brain = OrganismBrain(brain_dir="organism_brain")
    # Load previous state (or start fresh)
    brain.load()
    # ... run organism ...
    # Save everything
    brain.save(
        signal_gen=signal_gen,
        learner=learner,
        equity_curve=equity_curve,
        all_trades=all_trades,
        epoch_metrics=epoch_metrics,
        peak_equity=peak_equity,
        extra_counters={...},
    )
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from backend.organism.schema.candidate_signal import infer_strategy_id

logger = logging.getLogger(__name__)

# ── Brain format version — bump if we change what we persist ─────
BRAIN_FORMAT_VERSION = 2          # bumped from 1 → 2 for Phase 3
MANIFEST_FILE = "manifest.json"
MAX_BACKUPS = 5
MAX_TRADE_ROWS = 10_000          # Phase 3.2: keep latest N trades in active CSV
ARCHIVE_PREFIX = "trade_history_archive_"
LOCK_FILE = ".brain.lock"
# Audit 2026-06-09 finding 3.6: save() deletes this before its swap and
# rewrites it after — a brain dir without it was interrupted mid-swap.
# Audit 2026-10-05 C12-01: save() now writes the generation's file inventory
# into it (HEAD_INVENTORY_FORMAT JSON). Older code only checks that the file
# exists, so a brain saved this way still loads after a rollback; a legacy
# timestamp sentinel (or none) keeps the legacy load path.
SAVE_COMPLETE_SENTINEL = ".save_complete"
HEAD_INVENTORY_FORMAT = "brain-head-inventory-v1"
# C12-01: write-ahead journal of a full-save swap — present only while a swap
# is in flight or after a crash interrupted one. The staging dir and the
# directory-replacement trash both live INSIDE brain_dir (same filesystem,
# private to this brain: C12-08). The ".brain_" prefix keeps the journal out of
# the host-side archive (scripts/runtime/rotate_brain_backup.py).
# v2 (C12 review) also records the pre-swap identity (size, sha256) of every
# HEAD file the swap replaces or deletes, so a roll-forward never publishes
# staged files over state written after the journal (older code after a
# rollback, or a write outside a save).
SWAP_JOURNAL_FILE = ".brain_swap_journal.json"
SWAP_JOURNAL_FORMAT = "brain-swap-journal-v2"
SWAP_STAGING_DIR = ".tmp_save"
SWAP_TRASH_DIR = ".brain_old"
# Forensic copy of a retired journal: the "corrupt_head_" prefix keeps it in
# place across every swap (this code and older code), out of the host archive
# and inside the existing prune of at most MAX_CORRUPT_HEAD_SNAPSHOTS.
SWAP_FORENSIC_SUFFIX = "_swap_journal"
MAX_CORRUPT_HEAD_SNAPSHOTS = 5
# C12 review: written (durably) before a STALE swap journal is retired with
# HEAD kept, and removed only when a full save (or a roll-forward) commits a
# complete generation. HEAD may mix two generations meanwhile; the marker keeps
# full_save_required() true across restarts. Not ".brain_"-prefixed, so the
# host archive keeps it with the HEAD it describes; older code's full save
# removes it together with every other file it replaces.
FULL_SAVE_REQUIRED_MARKER = ".full_save_required"
FULL_SAVE_REQUIRED_FORMAT = "brain-full-save-required-v1"
# C12-02: an essential save stages a CHANGED ensemble here and publishes it only
# when every model pair serialized (never a reduced ensemble_manifest.json). The
# publication is a sequence of renames, not a crash-safe commit; under the
# research lock (frozen models) essential saves never publish an ensemble.
ENSEMBLE_STAGING_DIR = ".brain_ensemble_stage"
CANDIDATE_FILTER_SHADOW_TELEMETRY_FILE = "candidate_filter_shadow_telemetry.jsonl"
STRATEGY_EVIDENCE_TELEMETRY_FILE = "strategy_evidence_events.jsonl"
# Work order 2026-07-23 Task 2 — append-only sidecar telemetry + the model
# rollback dir. These live in the brain head but are NOT regenerated by the
# _save_* methods, so save()'s file-by-file swap used to move them to
# .brain_old and then rmtree them (they were absent from `preserved_names`).
# candidate_filter / strategy_evidence survived ONLY because they were listed;
# these three were the ones that kept vanishing. Treat all five identically:
# preserved in place across the swap, and captured in backups + corrupt-head
# snapshots so a restore brings them back.
SHADOW_EXIT_TELEMETRY_FILE = "shadow_exit_telemetry.jsonl"
MODEL_SWAP_AUDIT_FILE = "model_swap_audit.jsonl"
PREVIOUS_MODEL_DIR = "previous_model"
SIDECAR_TELEMETRY_NAMES = frozenset({
    "close_accounting.json",  # Authoritative close projection: never stage an older copy.
    "entry_evidence.jsonl",  # Append-only prospective decision/submission receipts.
    CANDIDATE_FILTER_SHADOW_TELEMETRY_FILE,
    STRATEGY_EVIDENCE_TELEMETRY_FILE,
    SHADOW_EXIT_TELEMETRY_FILE,
    MODEL_SWAP_AUDIT_FILE,
    PREVIOUS_MODEL_DIR,
})
# Audit 2026-09-29 R7 — head entries written by OTHER components, never by the
# _save_* helpers into tmp_dir. The swap moved them to .brain_old and rmtree'd
# them on every full save:
#   diagnostics/             DiagnosticReportStore history.json + edge tracker
#   overnight_positions.json EOD-flatten-failure flag -> forced next-open exit
#   transfer_knowledge.json  TransferLearningEngine store (_save_brain rewrote
#                            it after the swap; force_save_brain never did)
#   *_quarantined.jsonl      reversible quarantine (clean_brain_sidecars.py)
# They stay in place across the swap. Brain-state files the save owns (models,
# evolved_params, trade history, ...) are still swapped out even when a save
# omits them, so a break-glass reset cannot resurrect stale state.
EXTERNAL_HEAD_ENTRIES = frozenset({
    "diagnostics",
    "overnight_positions.json",
    "transfer_knowledge.json",
})
QUARANTINED_SIDECAR_SUFFIX = "_quarantined.jsonl"
# Head entries a full save never swaps out or deletes: the swap's own journal and
# staging dirs, the lock, backups, append-only sidecars (Task 2, 2026-07-23),
# entries owned by other components (R7, 2026-09-29), forensic snapshots,
# archives and quarantined sidecars (matched by prefix/suffix below).
_SWAP_PRESERVED_NAMES = frozenset({
    SWAP_STAGING_DIR,
    SWAP_TRASH_DIR,
    SWAP_JOURNAL_FILE,
    LOCK_FILE,
    "backups",
}) | SIDECAR_TELEMETRY_NAMES | EXTERNAL_HEAD_ENTRIES


def _preserved_during_swap(name: str) -> bool:
    return (
        name in _SWAP_PRESERVED_NAMES
        or name.startswith("corrupt_head_")
        or name.startswith(ARCHIVE_PREFIX)
        or name.endswith(QUARANTINED_SIDECAR_SUFFIX)
    )


# C12 review (P2): the HEAD files a save writes — the _save_* helpers' files
# (the same names in every version of this module), the model pickles
# (ml_*.joblib) and the ensemble files. Only these count toward a swap
# journal's staleness, and a swap deletes no other file: anything else in HEAD
# is foreign (Finder's .DS_Store on the macOS bind mount, an editor's swap file,
# an operator's copy) and is left alone.
_BRAIN_OWNED_FILES = frozenset({
    MANIFEST_FILE,
    "ml_state.json",
    "evaluation_event_history.json",
    "learning_state.json",
    "reference_feats.csv",
    "trade_history.csv",
    "equity_curve.csv",
    "epoch_metrics.csv",
    "extra_counters.json",
    "evolved_params.json",
    "governance_state.json",
    "regime_state.json",
    "ensemble_manifest.json",
})


def _brain_owned(name: str) -> bool:
    """Is ``name`` a HEAD file that a brain save writes (C12 review)?"""
    if _preserved_during_swap(name):
        return False
    return (
        name in _BRAIN_OWNED_FILES
        or (name.startswith("ml_") and name.endswith(".joblib"))
        or (name.startswith("ensemble_") and name.endswith(".joblib"))
    )


class BrainHeadIncomplete(RuntimeError):
    """A brain directory is not one complete generation (audit 2026-10-05 C12-01).

    Raised inside the load path so it falls through to the PP-2 backup
    fallback instead of loading missing state files as empty.
    """


def _float_or_none(value: Any) -> "float | None":
    """CSV-safe float parse: ''/NaN/None → None (2026-06-11 fields)."""
    try:
        if value is None or value == "":
            return None
        f = float(value)
        import math as _math
        return f if _math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _truthy_cell(value: Any) -> bool:
    """CSV-safe bool parse for the 2026-06-11 fidelity flags."""
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _truthy_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _is_reconciliation_artifact_trade(trade: Any) -> bool:
    """Return True for bookkeeping rows that should not count as strategy PnL."""
    if isinstance(trade, dict):
        artifact_flag = trade.get("is_reconciliation_artifact")
        exit_reason = str(trade.get("exit_reason", "")).strip()
        entry_source = str(trade.get("entry_source", "")).strip()
    else:
        artifact_flag = getattr(trade, "is_reconciliation_artifact", None)
        exit_reason = str(getattr(trade, "exit_reason", "")).strip()
        entry_source = str(getattr(trade, "entry_source", "")).strip()
    return (
        _truthy_flag(artifact_flag)
        or exit_reason == "reconciliation_adjustment"
        or entry_source == "reconciliation_orphan"
    )


# ── Cross-platform file locking (Phase 3.1) ─────────────────────
class _BrainLock:
    """Exclusive file lock — one writer at a time.

    Uses ``msvcrt`` on Windows and ``fcntl`` on POSIX.
    Falls back to a no-op if neither is available.
    """

    def __init__(self, lock_path: Path):
        self._path = lock_path
        self._fh = None

    def acquire(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self._path, "w")  # noqa: SIM115
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            self._fh.close()
            self._fh = None
            raise RuntimeError(
                f"Brain lock already held: {self._path}"
            ) from exc

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                try:
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


class OrganismBrain:
    """Persist and restore the organism's full learned state.

    Thread-safe, atomic writes, automatic backups.
    """

    def __init__(
        self,
        brain_dir: str | Path = "organism_brain",
        *,
        now_fn=None,
    ):
        # V6 X-3 / Wave-20b (2026-05-03): clock injection for replay
        # determinism. The previous direct `datetime.now(UTC)` calls
        # (manifest `saved_at`, etc.) polluted the brain artifacts'
        # hashes in replay. Default is wall clock for live use.
        if now_fn is None:
            def _default_now() -> datetime:
                return datetime.now(timezone.utc)
            self._now_fn = _default_now
        else:
            self._now_fn = now_fn

        self.brain_dir = Path(brain_dir).resolve()
        self.backup_dir = self.brain_dir / "backups"
        self._loaded = False
        self._manifest: dict[str, Any] = {}
        # C12-01: the directory the restored state came from (HEAD, or the
        # backup the PP-2 fallback used), so model caches and the ensemble
        # are read from the SAME generation as the rest of the state.
        self._loaded_from: Path | None = None
        # C12-02: (ensemble object, state version) known to be in HEAD, so
        # essential saves never rewrite an unchanged (frozen) ensemble.
        self._ensemble_on_disk: tuple[Any, int] | None = None
        self._staged_ensemble_key: tuple[Any, int] | None = None
        # C12 review: set when HEAD was kept over a stale swap journal (it may
        # mix two generations) until the next full save rewrites every file.
        self._head_mixed_reason: str | None = None
        # C12 review (P3): set when an interrupted swap was rolled forward
        # while the in-memory state came from a backup (the load could not
        # take the brain lock). HEAD then holds a complete generation newer
        # than that state. It is copied into backups/ at once; while that copy
        # is still owed, save() retries it and refuses to replace HEAD.
        self._unbacked_roll_forward: str | None = None

        # ── Restored state containers ────────────────────────────
        # ML models (joblib objects)
        self.clf: Any = None
        self.reg: Any = None
        # ML config
        self.ml_state: dict[str, Any] = {}
        # Learning state
        self.learning_state: dict[str, Any] = {}
        # Reference features for drift detection
        self.reference_features: pd.DataFrame | None = None
        # Cumulative data
        self.trade_history: list[dict[str, Any]] = []
        self.equity_curve: list[float] = []
        self.epoch_metrics: list[dict[str, Any]] = []
        # Engine counters
        self.extra_counters: dict[str, Any] = {}
        # Dedicated evolved params (Phase 1.1)
        self.evolved_params: dict[str, Any] = {}
        # Governance state (Phase 1.2)
        self.governance_state: dict[str, Any] = {}
        # Regime detector state (Phase 1.3)
        self.regime_state: dict[str, Any] = {}
        # Evaluation event history (J4)
        self.evaluation_event_history: list[dict] = []

    # ═════════════════════════════════════════════════════════════
    #  PUBLIC API
    # ═════════════════════════════════════════════════════════════

    @property
    def exists(self) -> bool:
        """Does a saved brain already exist on disk?

        C12-01: a full-save swap journal also counts — an interrupted first
        save is a recoverable brain, and callers (live_engine.initialize:
        ``load() if exists else False``) must reach load(), which rolls the
        swap forward, instead of starting fresh.
        """
        return (
            (self.brain_dir / MANIFEST_FILE).is_file()
            or (self.brain_dir / SWAP_JOURNAL_FILE).is_file()
        )

    @property
    def generation(self) -> int:
        """Last saved generation number."""
        return self._manifest.get("generation", 0)

    @property
    def last_saved(self) -> str:
        """ISO timestamp of last save."""
        return self._manifest.get("saved_at", "never")

    @property
    def total_runs(self) -> int:
        """How many runs have been saved."""
        return self._manifest.get("total_runs", 0)

    def load(self) -> bool:
        """Load the organism's brain from disk.

        Returns True if a previous brain was loaded, False if starting fresh.
        """
        if not self.exists:
            logger.info("No previous brain found at %s — starting fresh", self.brain_dir)
            print("  🧠 No previous brain found — starting fresh")
            self._loaded = False
            return False

        # Audit 2026-06-09 finding 3.6 (root cause of the 2026-06-09
        # corrupt_head_* snapshots): load() previously ran LOCKLESS while
        # save()'s "atomic" swap is really a file-by-file shutil.move loop.
        # A load racing a save observed a half-swapped directory, threw,
        # and quarantined a perfectly good brain as corrupt — then the
        # backup restore raced the still-running save. Now: load takes the
        # same exclusive lock save() holds (briefly retrying while a save
        # finishes its swap), so a mid-swap state can never be observed.
        import time as _time

        _lock = _BrainLock(self.brain_dir / LOCK_FILE)
        _lock_acquired = False
        for _attempt in range(40):  # up to ~20 s for a slow save to finish
            try:
                _lock.acquire()
                _lock_acquired = True
                break
            except RuntimeError:
                if _attempt == 0:
                    logger.info(
                        "Brain load: save in progress (lock held) — waiting"
                    )
                _time.sleep(0.5)
        if not _lock_acquired:
            logger.warning(
                "Brain load: could not acquire lock after 20s — "
                "proceeding unlocked (legacy behavior)"
            )

        try:
            return self._load_locked(lock_held=_lock_acquired)
        finally:
            if _lock_acquired:
                _lock.release()

    def _load_locked(self, lock_held: bool = True) -> bool:
        """Body of load(); caller holds the brain lock (``lock_held``)."""
        _sentinel = self.brain_dir / SAVE_COMPLETE_SENTINEL
        _manifest_file = self.brain_dir / MANIFEST_FILE
        self._loaded_from = None
        self._unbacked_roll_forward = None

        try:
            # Audit 2026-10-05 C12-01: finish a full-save swap that a crash
            # interrupted BEFORE anything is read, so the load sees one
            # complete generation — unless HEAD changed after the journal was
            # written (older code after a rollback, a write outside a save):
            # then HEAD holds the newer state and is kept, and the stale
            # journal is retired with a forensic copy. Without the lock
            # (another holder for 20 s) an in-flight swap cannot be resolved
            # safely: reject the HEAD (PP-2 backup fallback below) instead of
            # reading it half-swapped. The journal stays; when it is rolled
            # forward later, that generation is copied into backups/ before
            # any save replaces it with the restored state (C12 review).
            if (self.brain_dir / SWAP_JOURNAL_FILE).is_file():
                if not lock_held:
                    raise BrainHeadIncomplete(
                        "full-save swap journal present and the brain lock "
                        "is unavailable"
                    )
                self._resolve_pending_swap(caller="load")

            # C12 review: HEAD was kept over a stale swap journal and no full
            # save has rewritten it since (possibly two generations mixed).
            marker = _full_save_marker_reason(self.brain_dir)
            if marker:
                logger.warning(
                    "C12-01: HEAD carries %s (%s); the engine's next brain "
                    "save is a full save", FULL_SAVE_REQUIRED_MARKER, marker,
                )

            # Audit 2026-06-09 finding 3.6: no sentinel (and no journal) means
            # either a legacy (pre-sentinel) brain or a save by older code
            # that died mid-swap. We log loudly and attempt the normal load —
            # a genuinely half-swapped directory still fails into the backup-
            # restore path; a legacy-but-healthy brain loads fine and gains a
            # sentinel below.
            if _manifest_file.is_file() and not _sentinel.is_file():
                logger.warning(
                    "Brain HEAD has no save-completion sentinel — either a "
                    "legacy (pre-sentinel) brain or the previous save() died "
                    "mid-swap. Attempting load; if it fails, the corrupt-head "
                    "snapshot should be read as a MID-SWAP CRASH, not data "
                    "corruption."
                )
            # C12-01: a generation published by save() lists its files in the
            # sentinel; a listed file that is missing — or a listed pickle
            # that is unsigned or torn (C12-04) — makes the HEAD incomplete:
            # it is never loaded as empty state.
            self._verify_generation_inventory(self.brain_dir)

            self._load_manifest()
            self._load_ml_models()
            self._load_ml_state()
            self._load_learning_state()
            self._load_reference_features()
            self._load_trade_history()
            self._load_equity_curve()
            self._load_epoch_metrics()
            self._load_extra_counters()
            self._load_evolved_params()
            self._load_governance_state()
            self._load_regime_state()
            self._load_evaluation_event_history()
            self._loaded = True
            self._loaded_from = self.brain_dir

            # 3.6: a successful load proves the HEAD is coherent — ensure
            # the completion sentinel exists (upgrades legacy brains; the
            # legacy timestamp form carries no inventory).
            try:
                if not _sentinel.is_file():
                    _write_text_atomic(
                        _sentinel, datetime.now(timezone.utc).isoformat()
                    )
            except Exception:
                pass

            gen = self._manifest.get("generation", 0)
            runs = self._manifest.get("total_runs", 0)
            trades = len(self.trade_history)
            saved = self._manifest.get("saved_at", "unknown")
            print(f"  🧠 Brain loaded: generation {gen}, {runs} previous runs, "
                  f"{trades} historical trades")
            print(f"     Last saved: {saved}")
            logger.info(
                "Brain loaded: gen=%d, runs=%d, trades=%d",
                gen, runs, trades,
            )
            return True

        except Exception as e:
            # V9 PP-2 / Wave-41 (2026-05-03): try the most-recent backup
            # before falling through to "starting fresh". The previous
            # behavior — single bad save = lose 161 generations / 482
            # trades — was a single-OOM-kill bomb. Now: walk
            # `backups/` newest-first, attempt each, restore the first
            # one that loads cleanly.
            logger.warning(
                "PP-2: HEAD brain load failed (%s); attempting backup fallback",
                e,
            )
            if self._restore_from_latest_backup():
                gen = self._manifest.get("generation", 0)
                trades = len(self.trade_history)
                logger.warning(
                    "PP-2: brain restored from backup; gen=%d trades=%d "
                    "(HEAD save was corrupt)", gen, trades,
                )
                print(
                    f"  🧠 HEAD brain corrupt; restored from backup: "
                    f"generation {gen}, {trades} historical trades"
                )
                self._loaded = True
                return True
            logger.error(
                "PP-2: all backup attempts failed — starting fresh "
                "(HEAD error: %s)", e,
            )
            print(f"  ⚠️  Brain load failed ({e}) — no usable backup — starting fresh")
            self._loaded = False
            return False

    def _restore_from_latest_backup(self) -> bool:
        """V9 PP-2 / Wave-41 (2026-05-03): walk backups/ newest-first;
        return True if a backup loads cleanly; False if none usable.

        Each backup is a snapshot directory. The state is LOADED from the
        backup in place (``self.brain_dir`` is repointed temporarily); HEAD
        is not modified — the next save rewrites it. Audit 2026-10-05
        C12-01: a backup whose completion inventory lists a missing file is
        skipped, and ``self._loaded_from`` records the backup so the model
        caches and the ensemble are read from the same generation.
        """
        backups_dir = self.brain_dir / "backups"
        if not backups_dir.is_dir():
            logger.warning("PP-2: no backups/ dir at %s", backups_dir)
            return False

        # V10 PP2-2 / Wave-56 (2026-05-03): copy corrupt HEAD to a
        # sticky forensic snapshot before the next save() overwrites
        # it.  Operator's only forensic record was previously a single
        # logger.warning line.  Keep at most 5 corrupt-head snapshots
        # to avoid disk bloat.
        try:
            from datetime import datetime as _dt
            forensic_ts = _dt.now().strftime("%Y%m%d_%H%M%S_%f")
            forensic_dir = self.brain_dir / f"corrupt_head_{forensic_ts}"
            forensic_dir.mkdir(parents=True, exist_ok=True)
            for f in self.brain_dir.iterdir():
                if f.name == LOCK_FILE:
                    continue
                try:
                    if f.is_file():
                        shutil.copy2(str(f), str(forensic_dir / f.name))
                    elif f.is_dir() and f.name == PREVIOUS_MODEL_DIR:
                        # Task 2: keep the rollback dir with its forensic head.
                        shutil.copytree(
                            str(f), str(forensic_dir / f.name), dirs_exist_ok=True
                        )
                except Exception:
                    pass
            # Prune old corrupt-head snapshots — keep at most 5.
            corrupts = sorted(
                [d for d in self.brain_dir.iterdir()
                 if d.is_dir() and d.name.startswith("corrupt_head_")],
                key=lambda d: d.stat().st_mtime,
            )
            while len(corrupts) > 5:
                old = corrupts.pop(0)
                shutil.rmtree(old, ignore_errors=True)
            logger.critical(
                "PP2-2: corrupt-HEAD captured to %s (operator should "
                "investigate; next save() would have overwritten)",
                forensic_dir.name,
            )
        except Exception as _forensic_err:
            logger.warning(
                "PP2-2: forensic snapshot failed (non-fatal): %s",
                _forensic_err,
            )

        # Task 6 (2026-07-23): only real backups are restore candidates. Backups
        # are named ``brain_gen*``; the ``quarantine/`` subdir (moved-aside
        # corrupt heads) and any other non-backup dir must never be loaded.
        candidates = sorted(
            (p for p in backups_dir.iterdir()
             if p.is_dir() and p.name.startswith("brain_gen")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for backup in candidates:
            try:
                logger.info("PP-2: trying backup %s", backup.name)
                # Try loading from the backup directory directly without
                # mutating the live brain_dir. We do this by temporarily
                # repointing self.brain_dir; reset on success/failure.
                original_dir = self.brain_dir
                self.brain_dir = backup
                try:
                    self._verify_generation_inventory(backup)
                    self._load_manifest()
                    self._load_ml_models()
                    self._load_ml_state()
                    self._load_learning_state()
                    self._load_reference_features()
                    self._load_trade_history()
                    self._load_equity_curve()
                    self._load_epoch_metrics()
                    self._load_extra_counters()
                    self._load_evolved_params()
                    self._load_governance_state()
                    self._load_regime_state()
                    self._load_evaluation_event_history()
                    self._loaded_from = backup
                    return True
                finally:
                    self.brain_dir = original_dir
            except Exception as backup_err:
                logger.warning(
                    "PP-2: backup %s also failed: %s",
                    backup.name, backup_err,
                )
                continue
        return False

    def save(
        self,
        signal_gen: Any,            # MLSignalGenerator
        learner: Any,               # ContinuousLearner
        equity_curve: list[float],
        all_trades: list[Any],      # list[TradeRecord]
        epoch_metrics: list[Any],   # list[EpochMetrics]
        peak_equity: float = 0.0,
        extra_counters: dict[str, Any] | None = None,
        evolved_params: dict[str, Any] | None = None,
        governance_controller: Any | None = None,
        regime_detector: Any | None = None,
        force: bool = False,
        allow_reset: bool = False,
        reset_reason: str | None = None,
    ) -> bool:
        """Save the organism's full learned state to disk.

        Stages the complete generation in ``.tmp_save`` and publishes it with
        a journaled swap (audit 2026-10-05 C12-01, ``_commit_staged_generation``):
        a crash at any point leaves either the previous complete generation or
        a journal that the next load()/save() rolls forward to the new one.
        Backs up the previous brain before overwriting — unless HEAD is not a
        generation a restart would load (C12 review: a rejected HEAD never
        displaces a good backup). A generation that was rolled forward after
        the state was restored from a backup is never replaced before it has
        been copied into ``backups/`` (C12 review).
        Thread-safe via cross-platform file lock (Phase 3.1).

        Returns True when the new generation was published and False when no
        save happened — the brain lock is held elsewhere, the trained-
        overwrite guard blocked it, or that required backup of a rolled-
        forward generation failed (C12-06: never reported as a save). Write
        failures raise.

        The ``force`` flag is audit-only: ``save()`` always performs the
        same full atomic save regardless of the flag. The walk-forward
        gate lives in the caller (``LiveEngine._save_brain``). ``force=True``
        is set by ``LiveEngine.force_save_brain()`` to signal an explicit
        admin-initiated recovery save for logging/audit trail.

        F3 break-glass: to intentionally overwrite a trained brain with
        fresh state, ALL THREE must be set: ``force=True``,
        ``allow_reset=True``, and a non-empty ``reset_reason``.
        """
        self.brain_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        lock = _BrainLock(self.brain_dir / LOCK_FILE)
        try:
            lock.acquire()
        except RuntimeError as e:
            logger.warning("Skipping brain save — lock held: %s", e)
            return False

        try:
            # V10 PP2-3 / Wave-56 (2026-05-03): sweep orphan .tmp files left
            # by a previous SIGKILL'd save.  _write_json / _write_csv_atomic
            # only unlink on caught exception; SIGKILL leaves them.
            # Cosmetic but accumulates. (C12: runs under the brain lock, so
            # another lock holder's in-flight temp file is never swept.)
            try:
                for f in self.brain_dir.iterdir():
                    if f.is_file() and f.name.endswith(".tmp"):
                        try:
                            f.unlink()
                        except Exception:
                            pass
            except Exception:
                pass

            # C12-01: finish a swap that a crash interrupted before this save
            # reads HEAD (guard, backup) or reuses the staging directory. A
            # stale journal (HEAD changed after it was written) is retired
            # inside _resolve_pending_swap and HEAD is kept. A journal that
            # cannot be applied is dealt with below, once the guard allowed
            # this save: it rewrites every brain-owned file.
            unusable_journal: BrainHeadIncomplete | None = None
            try:
                self._resolve_pending_swap(caller="save")
            except BrainHeadIncomplete as exc:
                unusable_journal = exc

            # DEFENSIVE GUARD (Patch E, refactored in F1 to use shared check).
            # Refuse to overwrite a trained manifest with untrained state.
            # Uses _check_trained_overwrite_guard for consistent logic across
            # save() and (in F2) save_essential_state().
            should_block, reason = self._check_trained_overwrite_guard(
                self.brain_dir, signal_gen, learner,
                force=force, allow_reset=allow_reset, reset_reason=reset_reason,
            )
            if should_block:
                # F3: suspicious-write instrumentation fires on block
                self._log_suspicious_manifest_write(
                    caller="save", target=self.brain_dir,
                    signal_gen=signal_gen, learner=learner,
                    force=force, allow_reset=allow_reset,
                    reset_reason=reset_reason,
                )
                logger.error(
                    "BRAIN SAVE BLOCKED (save): refusing to overwrite trained "
                    "manifest with untrained state (%s). "
                    "Break-glass reset requires force=True AND allow_reset=True "
                    "AND reset_reason.",
                    reason,
                )
                # Alert wiring: emit guard-fire alert.
                # V5 S-J3-1 / Wave-17a (2026-05-03): wave-8c's J-3 fix
                # caught the RuntimeError but routed every alert to
                # logger.warning because get_running_loop() always raises
                # in worker threads. Use the canonical cross-thread
                # dispatcher which schedules on the captured main loop via
                # asyncio.run_coroutine_threadsafe.
                try:
                    from backend.infra.alerting import (
                        AlertCategory, AlertSeverity, send_alert,
                        dispatch_alert_from_thread,
                    )
                    _r = reason
                    ok = dispatch_alert_from_thread(
                        lambda: send_alert(
                            AlertCategory.SYSTEM_ERROR, AlertSeverity.ERROR,
                            "Brain Save Blocked",
                            f"Trained manifest overwrite blocked (save). {_r}",
                        )
                    )
                    if not ok:
                        logger.warning(
                            "Brain Save Blocked alert dropped (no main loop ref): %s",
                            _r,
                        )
                except Exception as _alert_err:
                    # V9 UU-3 / Wave-41 (2026-05-03): surface the alert path
                    # exception at WARNING (was bare pass) so a broken
                    # alerter doesn't get masked by a brain-save block.
                    logger.warning(
                        "UU-3: brain-save-blocked alert path raised: %s",
                        _alert_err,
                    )
                return False

            # C12 review (P3): a generation rolled forward after the state had
            # been restored from a backup is newer than what this save writes.
            # Its copy into backups/ is retried here when the immediate one
            # failed; without that copy HEAD is not replaced.
            owed_ok, owed_backup = self._back_up_unbacked_roll_forward()
            if not owed_ok:
                logger.error(
                    "Brain save NOT performed: HEAD holds a rolled-forward "
                    "generation that is newer than the restored state and has "
                    "no copy in backups/ (the next save retries the copy)",
                )
                return False

            backup_skip: str | None = None
            if unusable_journal is not None:
                # The interrupted generation cannot be published intact. Keep
                # the evidence (journal, staged files, HEAD's brain-owned
                # files); the journal itself stays until this save's own
                # journal replaces it, so a crash before then still rejects
                # the half-swapped HEAD at load (PP-2 backup fallback).
                forensic = self._quarantine_swap_journal(
                    reason=f"save: {unusable_journal}", remove_journal=False,
                )
                logger.critical(
                    "C12-01: the interrupted full-save swap cannot be completed "
                    "(%s); this save rewrites every brain-owned file and skips "
                    "the pre-save backup of the half-swapped HEAD (forensic "
                    "copy: %s)", unusable_journal,
                    forensic.name if forensic is not None else "not taken",
                )
                backup_skip = "an interrupted full-save swap could not be completed"
            elif self.exists and owed_backup is None:
                backup_skip = self._head_rejection_reason()

            # 1. Backup current brain (if it exists as a complete generation;
            # a rolled-forward generation was just copied above).
            if self.exists and backup_skip is None and owed_backup is None:
                self._create_backup()
            elif self.exists and backup_skip is not None:
                logger.warning(
                    "Pre-save backup skipped: %s (the PP-2 fallback must keep "
                    "its complete backups)", backup_skip,
                )

            # 2. Write the complete new generation to the staging dir first.
            tmp_dir = self.brain_dir / SWAP_STAGING_DIR
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
            tmp_dir.mkdir(parents=True)

            progress = {"journal_written": False}
            try:
                self._save_ml_models(tmp_dir, signal_gen)
                # C12-05 (review): ml_state.json is written once, with the
                # model-metrics history in it.
                self._save_ml_state(tmp_dir, signal_gen, learner)
                self._save_evaluation_event_history(tmp_dir, learner)
                self._save_learning_state(tmp_dir, learner)
                self._save_reference_features(tmp_dir, learner)
                self._save_trade_history(tmp_dir, all_trades)
                self._save_equity_curve(tmp_dir, equity_curve)
                self._save_epoch_metrics(tmp_dir, epoch_metrics)
                self._save_extra_counters(tmp_dir, peak_equity, extra_counters)
                self._save_evolved_params(tmp_dir, evolved_params)
                self._save_governance_state(tmp_dir, governance_controller)
                self._save_regime_state(tmp_dir, regime_detector)
                self._save_manifest(
                    tmp_dir, signal_gen, learner,
                    force=force, allow_reset=allow_reset, reset_reason=reset_reason,
                )

                # 3. Journaled swap of the staged generation into HEAD (C12-01).
                self._commit_staged_generation(tmp_dir, progress)
                self._ensemble_on_disk = self._staged_ensemble_key
                # HEAD now holds exactly the in-memory state as one complete
                # generation: a backup fallback or a kept stale HEAD is over.
                self._loaded_from = self.brain_dir
                self._head_mixed_reason = None
                self._unbacked_roll_forward = None

                gen = learner.state.generation if hasattr(learner, "state") else 0
                eq_str = f", equity ${equity_curve[-1]:,.0f}" if equity_curve else ""
                print(f"  💾 Brain saved: generation {gen}, "
                      f"{len(all_trades)} trades{eq_str}")
                logger.info(
                    "Brain saved successfully to %s%s",
                    self.brain_dir,
                    " (forced)" if force else "",
                )
                return True

            except Exception as e:
                self._ensemble_on_disk = None
                logger.error("Brain save failed: %s", e)
                print(f"  ⚠️  Brain save failed: {e}")
                # The journal this save wrote still needs the staged
                # generation: the next load()/save() rolls it forward. Before
                # that point the staging dir is only this save's partial work.
                if not progress["journal_written"]:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                raise
        finally:
            try:
                lock.release()
            except Exception as _rel_err:
                # V9 UU-3 / Wave-41: lock-release failure here can leak
                # into next save attempt; log at WARNING.
                logger.warning(
                    "UU-3: brain-save lock.release() failed: %s — next "
                    "save attempt may also fail. Manual intervention may "
                    "be needed if this persists.", _rel_err,
                )

    # ═════════════════════════════════════════════════════════════
    #  FULL-SAVE SWAP JOURNAL (audit 2026-10-05 C12-01 / C12-08 / C12-09)
    # ═════════════════════════════════════════════════════════════

    def _commit_staged_generation(
        self, tmp_dir: Path, progress: dict[str, bool] | None = None,
    ) -> None:
        """Publish the generation staged in ``tmp_dir`` into HEAD.

        Write-ahead protocol (caller holds the brain lock):

        1. Every staged file was fsynced when written; fsync ``tmp_dir``,
           then atomically write the journal: the staged entry names in
           publish order (``manifest.json`` last) with each file's size and
           sha256, plus the pre-swap identity (size, sha256; null = absent)
           of every HEAD file the swap replaces (``head``) or deletes
           (``delete``: the brain-owned files the new generation does not
           have — a swap never deletes a foreign file). From here a crash is
           rolled FORWARD by the next load()/save() (``_resolve_pending_swap``)
           — but only while every one of those HEAD files is still either its
           pre-swap version or its staged copy (C12 review: never over newer
           state).
        2. ``_apply_swap``: drop the completion sentinel, replace each HEAD
           entry with its staged copy (files by ``os.replace`` — an entry
           present in both generations is never missing), delete the previous
           generation's brain-owned files the new one does not have, fsync
           HEAD, write the sentinel with the new inventory and remove the
           journal.

        An exception during step 2 propagates with the journal kept, so the
        staged generation is published by the next load()/save().
        ``progress["journal_written"]`` turns True once the journal is on disk.
        """
        brain_dir = self.brain_dir
        names = sorted(
            (entry.name for entry in tmp_dir.iterdir()),
            key=lambda name: (name == MANIFEST_FILE, name),
        )
        new_names = set(names)
        files: dict[str, dict[str, Any]] = {}
        for name in names:
            identity = _file_identity(tmp_dir / name)
            if identity is not None and "sha256" in identity:
                files[name] = identity
        head = {name: _file_identity(brain_dir / name) for name in names}
        delete: dict[str, dict[str, Any]] = {}
        for entry in brain_dir.iterdir():
            name = entry.name
            if name in new_names or not _brain_owned(name):
                continue
            identity = _file_identity(entry)
            if identity is not None and "sha256" in identity:
                delete[name] = identity
        _fsync_dir(tmp_dir)
        journal = {
            "format": SWAP_JOURNAL_FORMAT,
            "started_at": self._now_fn().isoformat(),
            "entries": names,
            "files": files,
            "head": head,
            "delete": delete,
        }
        _write_text_atomic(
            brain_dir / SWAP_JOURNAL_FILE, json.dumps(journal, sort_keys=True)
        )
        if progress is not None:
            progress["journal_written"] = True
        self._apply_swap(journal)

    def _apply_swap(self, journal: dict[str, Any]) -> None:
        """Publish the journaled staged generation into HEAD (idempotent).

        Used by a save's own commit and by crash recovery: every step can be
        repeated after an interruption. Staged entries already published are
        skipped, the deletions and the sentinel write are idempotent, and the
        journal is removed only after the sentinel records the new inventory.
        HEAD then holds one complete generation, so a full-save-required
        marker (C12 review) is removed before the journal.
        """
        brain_dir = self.brain_dir
        stage = brain_dir / SWAP_STAGING_DIR
        trash = brain_dir / SWAP_TRASH_DIR
        entries = [str(name) for name in journal["entries"]]
        new_names = set(entries)

        # 3.6: no completion sentinel while HEAD is between generations. The
        # unlink is made durable before the first rename (C12 review), so a
        # durable rename implies a durable unlink. A timestamp sentinel next to
        # a journal proves nothing on its own: a crash before this unlink
        # leaves the previous one (older code, or this code's load of a HEAD
        # without an inventory, writes timestamps).
        try:
            os.unlink(brain_dir / SAVE_COMPLETE_SENTINEL)
        except FileNotFoundError:
            pass
        _fsync_dir(brain_dir)

        for name in entries:
            src = stage / name
            if not os.path.lexists(src):
                continue  # published before an interruption
            dest = brain_dir / name
            if src.is_dir() or dest.is_dir():
                # Only a preserved name can be a directory here; the
                # regenerated copy replaces it (R7). The old one is parked in
                # the trash first so the move cannot nest the new tree, and is
                # put back if the move fails.
                parked = None
                if os.path.lexists(dest):
                    trash.mkdir(parents=True, exist_ok=True)
                    parked = _unused_child(trash, name)
                    shutil.move(str(dest), str(parked))
                try:
                    shutil.move(str(src), str(dest))
                except BaseException:
                    if parked is not None and not os.path.lexists(dest):
                        shutil.move(str(parked), str(dest))
                    raise
            else:
                os.replace(src, dest)

        # The previous generation's brain-owned files that this generation
        # does not have (a break-glass reset cannot resurrect stale models)
        # and this brain's own leftover ensemble staging dir. Nothing else is
        # deleted (C12 review): foreign files stay where they are.
        for entry in list(brain_dir.iterdir()):
            name = entry.name
            if name in new_names or not (
                _brain_owned(name) or name == ENSEMBLE_STAGING_DIR
            ):
                continue
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()

        # C12-09: the renames are durable before the sentinel vouches for them.
        _fsync_dir(brain_dir)
        inventory = {
            "format": HEAD_INVENTORY_FORMAT,
            "completed_at": self._now_fn().isoformat(),
            # Brain-owned entries only: a preserved name a save happened to
            # regenerate belongs to another component, which may remove it.
            "files": sorted(n for n in entries if not _preserved_during_swap(n)),
        }
        _write_text_atomic(
            brain_dir / SAVE_COMPLETE_SENTINEL, json.dumps(inventory, sort_keys=True)
        )
        # C12 review: one complete generation is committed — HEAD no longer
        # mixes generations. Removed before the journal: a crash in between
        # repeats this idempotent step on the next roll-forward.
        try:
            os.unlink(brain_dir / FULL_SAVE_REQUIRED_MARKER)
        except FileNotFoundError:
            pass
        self._head_mixed_reason = None
        try:
            os.unlink(brain_dir / SWAP_JOURNAL_FILE)
        except FileNotFoundError:
            pass
        _fsync_dir(brain_dir)
        shutil.rmtree(trash, ignore_errors=True)
        shutil.rmtree(stage, ignore_errors=True)

    def _resolve_pending_swap(self, *, caller: str) -> str:
        """Settle a full-save swap that a crash or an error interrupted (C12-01).

        Caller holds the brain lock. Every file the swap touches is checked by
        size and sha256 against the journal (``_swap_journal_findings``).
        Returns:

        * ``"none"`` — no journal;
        * ``"rolled_forward"`` — the journaled generation was published. When
          the in-memory state had been restored from a backup (a load without
          the brain lock), that newer generation is copied into ``backups/``
          at once, and save() does not replace it before a copy exists (C12
          review);
        * ``"kept_head"`` — the journal is STALE (C12 review): HEAD changed
          after it was written — a file the swap replaces or deletes is
          neither its recorded pre-swap version nor its staged copy, or a
          brain-owned file appeared. Foreign files (Finder's ``.DS_Store``,
          an editor's swap file) never count. HEAD then holds newer state
          than the staged generation (older code ran after a rollback, or a
          write outside a save), so nothing is published: HEAD is kept as it
          is, a durable full-save-required marker is written, the journal is
          retired with a forensic copy (CRITICAL) and the next full save
          rewrites every brain-owned file. A timestamp-format
          ``.save_complete`` makes a journal stale only where size and sha256
          cannot decide (a staged directory); otherwise it is only logged.

        Raises ``BrainHeadIncomplete`` when the journal is unreadable, when a
        brain-owned file that HEAD held before the swap is missing (checked
        first: kept as it is, that HEAD would load the file as empty state,
        so load uses the newest complete backup instead), or when a journal
        that is not stale can no longer be published intact (a staged copy
        still needed is missing or altered); the journal and the staging dir
        are then left for the caller to decide.
        """
        journal_path = self.brain_dir / SWAP_JOURNAL_FILE
        if not journal_path.is_file():
            return "none"
        # What is on disk is about to change: the next essential save must
        # write the ensemble rather than assume HEAD holds it (C12-02).
        self._ensemble_on_disk = None
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
            if (
                not isinstance(journal, dict)
                or journal.get("format") != SWAP_JOURNAL_FORMAT
                or not isinstance(journal.get("entries"), list)
                or not isinstance(journal.get("files"), dict)
                or not isinstance(journal.get("head"), dict)
                or not isinstance(journal.get("delete"), dict)
            ):
                raise ValueError("unsupported swap journal format")
        except Exception as exc:
            logger.critical(
                "C12-01 (%s): brain swap journal %s is unreadable (%s)",
                caller, journal_path, exc,
            )
            raise BrainHeadIncomplete(f"unreadable swap journal: {exc}") from exc

        findings = self._swap_journal_findings(journal)
        started = journal.get("started_at")
        missing, stale = findings["missing"], findings["stale"]
        if missing:
            # C12 review (P3): stale or not, never keep a HEAD that lacks a
            # file it had — it would load as empty state (no inventory).
            logger.critical(
                "C12-01 (%s): the full brain save interrupted at %s left HEAD "
                "without file(s) it held before the swap: %s%s. HEAD is never "
                "loaded with that state empty (a load uses the newest complete "
                "backup); only a full save rewrites it.",
                caller, started, "; ".join(missing),
                f" (HEAD was also changed: {'; '.join(stale)})" if stale else "",
            )
            raise BrainHeadIncomplete(
                "interrupted swap left HEAD incomplete: " + "; ".join(missing)
            )
        if stale:
            mixed = (
                f"HEAD was kept over a stale full-save swap journal "
                f"({started}) and may mix two generations"
            )
            self._head_mixed_reason = mixed
            # Durable before the journal goes (Copilot review): a restart
            # before the next full save still knows that HEAD needs one.
            self._write_full_save_marker(mixed, journal_started_at=started)
            forensic = self._quarantine_swap_journal(
                reason=f"{caller}: stale swap journal: " + "; ".join(stale),
                remove_journal=True,
            )
            logger.critical(
                "C12-01 (%s): STALE full-save swap journal from %s: %s. HEAD "
                "holds newer state than the staged generation (older code or "
                "a write outside a save changed it after the interruption), so "
                "the roll-forward is REFUSED: HEAD is kept as it is and the "
                "journal was retired (forensic copy: %s). The next full save "
                "rewrites every brain-owned file.",
                caller, started, "; ".join(stale),
                forensic.name if forensic is not None else "not taken",
            )
            return "kept_head"
        if findings["incomplete"]:
            logger.critical(
                "C12-01 (%s): the full brain save interrupted at %s cannot be "
                "completed: %s",
                caller, started, "; ".join(findings["incomplete"]),
            )
            raise BrainHeadIncomplete(
                "interrupted swap cannot be completed: "
                + "; ".join(findings["incomplete"])
            )
        self._apply_swap(journal)
        logger.warning(
            "C12-01 (%s): the full brain save interrupted at %s was rolled "
            "forward — HEAD holds the complete new generation%s",
            caller, started,
            f" ({'; '.join(findings['notes'])})" if findings["notes"] else "",
        )
        loaded_from = getattr(self, "_loaded_from", None)
        if loaded_from is not None and loaded_from != self.brain_dir:
            # C12 review (P3): the load could not take the lock and restored
            # older state from a backup; HEAD now holds a newer generation.
            self._unbacked_roll_forward = (
                f"the full brain save interrupted at {started} was rolled "
                f"forward after the state had been restored from "
                f"{loaded_from.name}"
            )
            logger.critical(
                "C12-01 (%s): %s — HEAD now holds a complete generation that "
                "can be NEWER than the in-memory state; it is copied into "
                "backups/ before any save replaces it",
                caller, self._unbacked_roll_forward,
            )
            self._back_up_unbacked_roll_forward()
        return "rolled_forward"

    def _swap_journal_findings(
        self, journal: dict[str, Any],
    ) -> dict[str, list[str]]:
        """Check every file a journaled swap touches (C12-01, C12 review).

        Each file the swap replaces must be either its staged copy (already
        published) or its recorded pre-swap version (not yet published, so
        its staged copy must still be intact); each brain-owned file it
        deletes must be gone or still its pre-swap version. Identity is size
        and sha256, so a byte-identical rewrite carries no information.
        Returns reason lists by kind:

        * ``missing`` — a brain-owned file that HEAD held before the swap is
          gone (this code's renames never leave a gap: an interrupted
          non-atomic writer or an external deletion removed it);
        * ``stale`` — HEAD was written after the journal: another version of
          such a file, or a new brain-owned file. Anything else in HEAD is
          foreign and never counts. A timestamp-format ``.save_complete``
          (older code writes one on every load and full save, this code when
          it loads a HEAD without an inventory) counts only together with an
          entry that size and sha256 cannot check (a staged directory);
        * ``incomplete`` — a staged copy that is still needed is missing or
          altered (or a published file of a name that is not brain-owned);
        * ``notes`` — that timestamp sentinel, when the checksums decided.
        """
        brain_dir = self.brain_dir
        stage = brain_dir / SWAP_STAGING_DIR
        files = journal["files"]
        head = journal["head"]
        delete = journal["delete"]
        entries = [str(name) for name in journal["entries"]]
        missing: list[str] = []
        stale: list[str] = []
        incomplete: list[str] = []
        notes: list[str] = []
        unchecked: list[str] = []
        for name in entries:
            meta = files.get(name)
            published = brain_dir / name
            staged = stage / name
            if meta is None:  # a staged directory (preserved name, R7)
                unchecked.append(name)
                if not (staged.is_dir() or published.is_dir()):
                    incomplete.append(f"{name}: directory missing")
                continue
            target = {"size": meta.get("size"), "sha256": meta.get("sha256")}
            current = _file_identity(published)
            if current == target:
                continue  # published, or unchanged between the generations
            before = head.get(name)
            if current == before:
                # Not published yet and HEAD's copy is untouched.
                if isinstance(before, dict) and "sha256" not in before:
                    unchecked.append(name)  # not a regular file in HEAD
                if _file_identity(staged) != target:
                    incomplete.append(f"{name}: staged copy missing or altered")
                continue
            if current is None and _brain_owned(name):
                missing.append(f"{name}: missing although HEAD held it before the swap")
            elif current is None:
                incomplete.append(f"{name}: published copy missing")
            else:
                stale.append(f"{name}: changed after the journal was written")
        for name, recorded in delete.items():
            if not _brain_owned(str(name)):
                continue  # a swap never deletes a foreign file
            current = _file_identity(brain_dir / str(name))
            if current is not None and current != recorded:
                stale.append(f"{name}: changed after the journal was written")
        expected = set(entries) | {str(name) for name in delete}
        for entry in brain_dir.iterdir():
            name = entry.name
            if name in expected or not _brain_owned(name):
                continue
            if entry.is_file() and not entry.is_symlink():
                stale.append(f"{name}: created after the journal was written")
        if _sentinel_kind(brain_dir / SAVE_COMPLETE_SENTINEL) == "legacy":
            sentinel = (
                f"{SAVE_COMPLETE_SENTINEL} holds a timestamp, not this code's "
                "inventory (written by older code, or by a load of a HEAD "
                "without an inventory)"
            )
            if unchecked:
                stale.append(
                    f"{sentinel}, and {sorted(set(unchecked))} cannot be "
                    "checked by size and sha256"
                )
            else:
                notes.append(f"{sentinel}; every file the swap touches checked out")
        return {
            "missing": missing, "stale": stale,
            "incomplete": incomplete, "notes": notes,
        }

    def _classify_swap_journal(
        self, journal: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        """``(stale, incomplete)`` view of ``_swap_journal_findings``, with a
        missing published file counted as incomplete (tests, review probes)."""
        findings = self._swap_journal_findings(journal)
        return findings["stale"], findings["missing"] + findings["incomplete"]

    def _swap_journal_problems(self, journal: dict[str, Any]) -> list[str]:
        """Every reason a journaled generation must not be rolled forward
        (missing, stale and incomplete together; empty = the roll-forward is
        safe)."""
        findings = self._swap_journal_findings(journal)
        return findings["missing"] + findings["stale"] + findings["incomplete"]

    def _write_full_save_marker(self, reason: str, **details: Any) -> None:
        """Durably record that only a full save can repair HEAD (Copilot
        review of C12): ``FULL_SAVE_REQUIRED_MARKER`` in HEAD, removed by
        ``_apply_swap`` once a complete generation is committed. Best effort:
        if the write fails, the in-memory reason still holds for this
        process and the failure is logged."""
        payload = {
            "format": FULL_SAVE_REQUIRED_FORMAT,
            "reason": reason,
            "since": self._now_fn().isoformat(),
            **details,
        }
        try:
            _write_text_atomic(
                self.brain_dir / FULL_SAVE_REQUIRED_MARKER,
                json.dumps(payload, sort_keys=True, default=str),
            )
        except Exception as exc:
            logger.error(
                "C12-01: could not write %s (%s); until the next full save only "
                "this process knows that HEAD may mix two generations",
                FULL_SAVE_REQUIRED_MARKER, exc,
            )

    def _back_up_unbacked_roll_forward(self) -> tuple[bool, Path | None]:
        """Copy a rolled-forward generation that is newer than the restored
        in-memory state into ``backups/`` (C12 review, P3). Caller holds the
        brain lock.

        Returns ``(ok, backup)``: ``ok`` is False only while that copy is
        owed and could not be made (save() then refuses to replace HEAD);
        ``backup`` is the copy this call made. A HEAD that has meanwhile lost
        a listed file is no loadable generation and is not copied.
        """
        reason = getattr(self, "_unbacked_roll_forward", None)
        if not reason:
            return True, None
        problems = _generation_inventory_problems(self.brain_dir)
        if problems:
            logger.critical(
                "C12-01: %s, but HEAD is no longer a complete generation (%s); "
                "it is not copied into backups/", reason, "; ".join(problems),
            )
            self._unbacked_roll_forward = None
            return True, None
        backup = self._create_backup(generation=_manifest_generation(self.brain_dir))
        if backup is None:
            logger.error(
                "C12-01: %s; copying that generation into backups/ failed", reason,
            )
            return False, None
        logger.warning(
            "C12-01: %s; that generation was copied to backups/%s before any "
            "save replaces it", reason, backup.name,
        )
        self._unbacked_roll_forward = None
        return True, backup

    def _quarantine_swap_journal(
        self, *, reason: str, remove_journal: bool,
    ) -> Path | None:
        """Keep the evidence of an interrupted swap, then (optionally) retire
        its journal (C12 review: discarding destroyed the only evidence).

        ``corrupt_head_<ts>_swap_journal/`` receives ``REASON.txt``, a copy of
        the journal, copies of HEAD's brain-owned files under ``head/``, and
        the staging dir (``staged/``) and directory trash (``trash/``), moved
        (same filesystem). The prefix keeps it in place across every swap
        (this code and older code), out of the host archive, and inside the
        prune of at most ``MAX_CORRUPT_HEAD_SNAPSHOTS``. A failed copy never
        blocks the caller. With ``remove_journal`` the journal is then
        unlinked (directory fsynced). Returns the forensic directory.
        """
        brain_dir = self.brain_dir
        journal_path = brain_dir / SWAP_JOURNAL_FILE
        forensic: Path | None = None
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            candidate = brain_dir / f"corrupt_head_{ts}{SWAP_FORENSIC_SUFFIX}"
            candidate.mkdir(parents=True)
            forensic = candidate
            (forensic / "REASON.txt").write_text(reason + "\n", encoding="utf-8")
            if journal_path.is_file():
                shutil.copy2(str(journal_path), str(forensic / SWAP_JOURNAL_FILE))
            head_copy = forensic / "head"
            head_copy.mkdir()
            for entry in brain_dir.iterdir():
                if (
                    entry.is_file()
                    and not entry.is_symlink()
                    and entry.name != SWAP_JOURNAL_FILE
                    and not entry.name.endswith(".tmp")
                    and not _preserved_during_swap(entry.name)
                ):
                    shutil.copy2(str(entry), str(head_copy / entry.name))
            for name, label in ((SWAP_STAGING_DIR, "staged"), (SWAP_TRASH_DIR, "trash")):
                source = brain_dir / name
                if source.is_dir() and not source.is_symlink():
                    os.rename(source, forensic / label)
        except Exception as exc:
            logger.warning(
                "C12-01: forensic copy of the swap journal failed (non-fatal): %s",
                exc,
            )
        if remove_journal:
            try:
                os.unlink(journal_path)
            except FileNotFoundError:
                pass
            _fsync_dir(brain_dir)
            shutil.rmtree(brain_dir / SWAP_STAGING_DIR, ignore_errors=True)
            shutil.rmtree(brain_dir / SWAP_TRASH_DIR, ignore_errors=True)
        _prune_corrupt_head_snapshots(brain_dir)
        return forensic

    def _verify_generation_inventory(self, directory: Path) -> None:
        """Raise ``BrainHeadIncomplete`` when ``directory``'s completion
        inventory lists an entry that is missing (C12-01), or a pickle that
        is unsigned or torn (C12-04 review: handled exactly like a missing
        file, so the PP-2 fallback uses the newest complete backup). Legacy
        (timestamp) and absent sentinels carry no inventory and are not
        checked."""
        problems = _generation_inventory_problems(directory)
        if problems:
            logger.critical(
                "C12-01: brain generation at %s is incomplete — %s; it is not "
                "loaded as empty state",
                directory, "; ".join(problems),
            )
            raise BrainHeadIncomplete(
                "generation incomplete: " + "; ".join(problems)
            )

    def resolve_pending_swap(self) -> bool:
        """Settle an interrupted full-save swap before a write outside a save
        touches a journaled file (C12 review: the engine's standalone
        exit-level write used to change a published file and wedge every
        following essential save). Rolls the swap forward, or retires a stale
        journal with HEAD kept, under the brain lock. Returns True when no
        journal remains. Never raises: a busy lock or a swap that cannot be
        completed is logged and left to the next full save.
        """
        if not (self.brain_dir / SWAP_JOURNAL_FILE).is_file():
            return True
        lock = _BrainLock(self.brain_dir / LOCK_FILE)
        try:
            lock.acquire()
        except (RuntimeError, OSError) as exc:
            logger.warning(
                "C12-01: interrupted full-save swap not settled — brain lock "
                "unavailable: %s", exc,
            )
            return False
        try:
            self._resolve_pending_swap(caller="resolve_pending_swap")
            return True
        except Exception as exc:
            logger.error(
                "C12-01: interrupted full-save swap not settled (%s); the next "
                "full save rewrites HEAD", exc,
            )
            return False
        finally:
            try:
                lock.release()
            except Exception as rel_err:
                logger.warning(
                    "resolve_pending_swap lock.release() failed: %s", rel_err,
                )

    def full_save_required(self) -> str | None:
        """Why only a FULL save can leave a HEAD that a restart loads (C12
        review), or None.

        An essential save writes runtime state only — never models, caches
        or evolved params — so it cannot repair: a pending interrupted swap,
        a HEAD kept over a stale swap journal (possibly two generations
        mixed; recorded durably in ``FULL_SAVE_REQUIRED_MARKER``, so this
        holds across restarts until a full save commits), a HEAD the last
        load rejected (state restored from a backup), or a HEAD whose
        completion inventory lists a missing, unsigned or torn file. Reads
        only the directory, the marker, file sizes and pickle headers.
        """
        if (self.brain_dir / SWAP_JOURNAL_FILE).is_file():
            return "an interrupted full-save swap is pending"
        marker = _full_save_marker_reason(self.brain_dir)
        if marker:
            return marker
        mixed = getattr(self, "_head_mixed_reason", None)
        if mixed:
            return mixed
        return self._head_rejection_reason()

    def _head_rejection_reason(self) -> str | None:
        """Why HEAD is not a generation a restart would load, or None (C12
        review). Such a HEAD is never copied into ``backups/``: it would only
        displace a complete backup from the retained ``MAX_BACKUPS`` (the PP-2
        fallback skips it anyway).
        """
        loaded_from = getattr(self, "_loaded_from", None)
        if loaded_from is not None and loaded_from != self.brain_dir:
            return (
                f"the last load rejected HEAD and restored the state from "
                f"{loaded_from.name}"
            )
        problems = _generation_inventory_problems(self.brain_dir)
        if problems:
            return "HEAD is not a complete generation (" + "; ".join(problems) + ")"
        return None

    def apply_to_signal_generator(self, signal_gen: Any) -> bool:
        """Restore saved ML models into a MLSignalGenerator instance.

        Returns True if models were restored.
        Calibration is restored even when model artifacts are absent.
        """
        # Restore calibration first — works even without saved models
        calibration_data = self.ml_state.get("calibration")
        if calibration_data and hasattr(signal_gen, "load_calibration"):
            try:
                signal_gen.load_calibration(calibration_data)
            except Exception as e:
                logger.warning("Failed to restore ML calibration: %s", e)

        if self.clf is None or self.reg is None:
            return False

        # C12-01: the caches and the ensemble come from the directory the
        # state was loaded from — after a PP-2 backup fallback that is the
        # backup, never the rejected HEAD, so generations are not mixed.
        source_dir = getattr(self, "_loaded_from", None) or self.brain_dir

        # Audit-C concern 2 (2026-05-02): restore S17 same-holdout cache.
        for attr_name in ("_last_val_X", "_last_val_y_dir", "_last_val_y_ret"):
            cache_path = source_dir / f"ml_{attr_name.lstrip('_')}.joblib"
            if cache_path.is_file():
                try:
                    # C12-04: an unsigned cache is never deserialized; it is
                    # handled exactly like a missing one (a cache listed in
                    # the generation's inventory already failed the load).
                    signed, value = _read_signed_brain_pickle(cache_path, "S17 cache")
                    if signed:
                        setattr(signal_gen, attr_name, value)
                except Exception as e:
                    logger.debug(
                        "Failed to restore S17 cache %s: %s", attr_name, e,
                    )

        # Audit-C concern 1 (2026-05-02): restore RF/LGBM ensemble.
        # Closes axis-8 parity bug: post-restart predict() now uses
        # the full 60/40 blend immediately, not XGB-only-until-retrain.
        ensemble = getattr(signal_gen, "_ensemble", None)
        if ensemble is not None and hasattr(ensemble, "load"):
            try:
                if ensemble.load(source_dir):
                    logger.info(
                        "Restored RF/LGBM ensemble from brain (axis-8 parity)"
                    )
                    # C12-02: HEAD holds exactly what was just read from it,
                    # so essential saves need not rewrite it while unchanged.
                    if source_dir == self.brain_dir:
                        self._ensemble_on_disk = _ensemble_state_key(ensemble)
            except Exception as e:
                logger.warning(
                    "Failed to restore ensemble: %s", e,
                )

        try:
            signal_gen._clf = self.clf
            signal_gen._reg = self.reg
            signal_gen._is_trained = True
            signal_gen.generation = self.ml_state.get("generation", 0)
            signal_gen._feature_cols = self.ml_state.get("feature_cols", [])

            # Restore XGB hyperparams and train window if saved
            saved_xgb = self.ml_state.get("xgb_params")
            if saved_xgb and hasattr(signal_gen, "_xgb_params"):
                signal_gen._xgb_params.update(saved_xgb)
            saved_tw = self.ml_state.get("train_window")
            if saved_tw is not None:
                signal_gen.train_window = int(saved_tw)

            # Restore metrics if available
            metrics_data = self.ml_state.get("latest_metrics")
            if metrics_data:
                from backend.organism.ml_signal import ModelMetrics
                # JSON converts tuples to lists — convert back
                raw_fi = metrics_data.get("feature_importance_top10", [])
                fi_tuples = [tuple(x) for x in raw_fi] if raw_fi else []
                signal_gen._latest_metrics = ModelMetrics(
                    generation=metrics_data.get("generation", 0),
                    accuracy=metrics_data.get("accuracy", 0),
                    precision=metrics_data.get("precision", 0.0),
                    recall=metrics_data.get("recall", 0.0),
                    f1=metrics_data.get("f1", 0.0),
                    direction_accuracy=metrics_data.get("direction_accuracy", 0),
                    mean_pred_return=metrics_data.get("mean_pred_return", 0.0),
                    hit_rate=metrics_data.get("hit_rate", 0),
                    feature_importance_top10=fi_tuples,
                )

            logger.info("ML models restored into signal generator")
            return True

        except Exception as e:
            logger.error("Failed to apply ML models: %s", e)
            return False

    def apply_to_learner(self, learner: Any) -> bool:
        """Restore saved learning state into a ContinuousLearner.

        Returns True if state was restored.
        """
        if not self.learning_state:
            return False

        try:
            from backend.organism.continuous_learner import LearningState, TradeRecord

            ls = self.learning_state
            # best_sharpe is saved as None when -inf — restore properly
            raw_sharpe = ls.get("best_sharpe")
            best_sharpe = -np.inf if raw_sharpe is None else float(raw_sharpe)

            learner.state = LearningState(
                generation=ls.get("generation", 0),
                total_bars_seen=ls.get("total_bars_seen", 0),
                total_trades=ls.get("total_trades", 0),
                cumulative_pnl=ls.get("cumulative_pnl", 0.0),
                best_sharpe=best_sharpe,
                best_generation=ls.get("best_generation", 0),
                retrain_count=ls.get("retrain_count", 0),
                drift_events=ls.get("drift_events", 0),
                generation_accuracies=ls.get("generation_accuracies", []),
            )

            # V5 B-T-2 / Wave-17d (2026-05-03): cumulative_pnl /
            # trade_history.csv reconciliation. Sum the per-trade pnls
            # from the loaded CSV; the result, rounded to 2dp, must
            # equal the saved cumulative_pnl. Surface any drift as a
            # warning so we can detect schema/save-path bugs early.
            # Pre-Wave-17d CSVs stored 2dp pnls; the 6dp upgrade only
            # affects new writes — drift on legacy data is expected
            # and the threshold reflects that (10c tolerance for the
            # ~498-trade ledger; tighten over time as old rows roll out).
            try:
                _csv_pnl_sum = sum(
                    float(td.get("pnl", 0.0) or 0.0)
                    for td in (self.trade_history or [])
                )
                _state_pnl = float(learner.state.cumulative_pnl or 0.0)
                _drift = abs(round(_csv_pnl_sum, 2) - round(_state_pnl, 2))
                if _drift > 0.10:
                    logger.warning(
                        "cumulative_pnl reconciliation drift on load: "
                        "state=%.2f csv_sum=%.2f drift=$%.2f "
                        "(B-T-2; tolerance $0.10 — investigate if growing)",
                        _state_pnl, _csv_pnl_sum, _drift,
                    )
                else:
                    logger.info(
                        "cumulative_pnl reconciles: state=%.2f csv_sum=%.2f "
                        "drift=$%.2f within tolerance",
                        _state_pnl, _csv_pnl_sum, _drift,
                    )
            except Exception as _reconcile_err:
                logger.debug(
                    "cumulative_pnl reconcile check skipped: %s",
                    _reconcile_err,
                )

            # Restore model metrics history
            from backend.organism.ml_signal import ModelMetrics
            for mm in self.ml_state.get("model_metrics_history", []):
                raw_fi = mm.get("feature_importance_top10", [])
                fi_tuples = [tuple(x) for x in raw_fi] if raw_fi else []
                learner.state.model_metrics.append(ModelMetrics(
                    generation=mm.get("generation", 0),
                    accuracy=mm.get("accuracy", 0.0),
                    precision=mm.get("precision", 0.0),
                    recall=mm.get("recall", 0.0),
                    f1=mm.get("f1", 0.0),
                    direction_accuracy=mm.get("direction_accuracy", 0.0),
                    mean_pred_return=mm.get("mean_pred_return", 0.0),
                    hit_rate=mm.get("hit_rate", 0.0),
                    feature_importance_top10=fi_tuples,
                    calibration_sample_count=mm.get("calibration_sample_count", 0),
                    calibration_monotonic=mm.get("calibration_monotonic", True),
                    calibration_error=mm.get("calibration_error", 0.0),
                    effective_mean_pred_return=mm.get("effective_mean_pred_return", 0.0),
                    candidate_calibration_sample_count=mm.get("candidate_calibration_sample_count", 0),
                    candidate_calibration_monotonic=mm.get("candidate_calibration_monotonic", True),
                    candidate_calibration_error=mm.get("candidate_calibration_error", 0.0),
                    evaluated_at=mm.get("evaluated_at", ""),
                ))

            # Restore trade history
            learner.trade_history = []
            for td in self.trade_history:
                # Audit-G v2 GAP-2 + GAP-5 (2026-05-02): restore the
                # is_reconciliation_artifact flag from saved trades; if
                # missing (legacy rows), DERIVE it from exit_reason so that
                # historical reconciliation_adjustment trades are correctly
                # excluded from learning consumers post-restart.
                # V4 R-F-1 (2026-05-02): legacy CSVs without the column
                # derive the flag from BOTH triggers used at runtime. Keep
                # that derivation even if a stale flag is false so strategy
                # accounting cannot re-include orphan/reconciliation rows.
                _saved_artifact = _is_reconciliation_artifact_trade(td)
                learner.trade_history.append(TradeRecord(
                    symbol=td.get("symbol", ""),
                    direction=td.get("direction", 0),
                    entry_price=td.get("entry_price", 0),
                    exit_price=td.get("exit_price", 0),
                    entry_bar=td.get("entry_bar", 0),
                    exit_bar=td.get("exit_bar", 0),
                    shares=td.get("shares", 0),
                    pnl=td.get("pnl", 0),
                    exit_reason=td.get("exit_reason", ""),
                    predicted_return=td.get("predicted_return", 0),
                    actual_return=td.get("actual_return", 0),
                    confidence=td.get("confidence", 0),
                    is_exploration=td.get("is_exploration", False),
                    is_reconciliation_artifact=bool(_saved_artifact),
                    entry_source=td.get("entry_source", ""),
                    strategy_id=td.get(
                        "strategy_id",
                        infer_strategy_id(td.get("entry_source", "")),
                    ),
                    regime_at_entry=td.get("regime_at_entry", ""),
                    regime_at_exit=td.get("regime_at_exit", ""),
                    mfe=td.get("mfe", 0.0),
                    mae=td.get("mae", 0.0),
                    bars_held_at_exit=td.get("bars_held_at_exit", 0),
                    time_in_trade_seconds=td.get("time_in_trade_seconds", 0.0),
                    closed_at=td.get("closed_at", ""),
                    # 2026-06-11 measurement-integrity fields (absent in
                    # legacy rows → None/False defaults).
                    predicted_return_signed=_float_or_none(
                        td.get("predicted_return_signed")
                    ),
                    ml_spoke=_truthy_cell(td.get("ml_spoke")),
                    entry_order_id=str(td.get("entry_order_id", "") or ""),
                    price_source=str(td.get("price_source", "") or ""),
                    had_partial_exits=_truthy_cell(
                        td.get("had_partial_exits")
                    ),
                ))

            # Restore evaluation event history (J4)
            learner.state.evaluation_events = list(self.evaluation_event_history)

            # Restore reference features for drift detection
            if self.reference_features is not None:
                learner._reference_features = self.reference_features.copy()

            learner._bars_since_retrain = ls.get("bars_since_retrain", 0)

            logger.info(
                "Learner state restored: gen=%d, trades=%d",
                learner.state.generation,
                len(learner.trade_history),
            )
            return True

        except Exception as e:
            logger.error("Failed to apply learner state: %s", e)
            return False

    # ═════════════════════════════════════════════════════════════
    #  ESSENTIAL STATE SAVE (bypasses walk-forward gate)
    # ═════════════════════════════════════════════════════════════

    def save_essential_state(
        self,
        signal_gen: Any,
        learner: Any,
        all_trades: list[Any],
        equity_curve: list[float] | None = None,
        epoch_metrics: list[Any] | None = None,
        peak_equity: float = 0.0,
        extra_counters: dict[str, Any] | None = None,
        governance_controller: Any | None = None,
        regime_detector: Any | None = None,
    ) -> bool:
        """Persist all runtime truth directly to brain_dir when the
        walk-forward gate blocks a full (atomic-swap) brain save.

        Writes everything needed for a coherent restart EXCEPT
        promotion-gated artifacts (ML model binaries + evolved_params).
        Those remain gated: only a full save() promotes them.

        Always persisted (runtime truth):
          - trade_history.csv          (closed trades + forensic fields)
          - learning_state.json        (total_trades, cumulative_pnl)
          - evaluation_event_history   (ML accept/reject events)
          - equity_curve.csv           (historical equity)
          - extra_counters.json        (tick_count, universe, kelly, calibration)
          - governance_state.json      (frozen/halted flags)
          - regime_state.json          (detector history)
          - ml_state.json              (feature config + model metrics
                                        history, NOT model weights)
          - manifest.json              (updated trade count + pnl)

        NOT written (promotion-gated):
          - ml_classifier.joblib       (model binary — only on gate pass)
          - ml_regressor.joblib        (model binary — only on gate pass)
          - evolved_params.json        (evolved strategy params — only on gate pass)

        The RF/LGBM ensemble is written only when it differs from what HEAD
        holds (audit 2026-10-05 C12-02) and only while models are not frozen:
        under the research lock an essential save never publishes ensemble
        files — the next full save writes them in its journaled swap (C12
        review). Where it is published, a pair that cannot be serialized
        publishes nothing, but the publication itself is a sequence of
        renames, not a crash-safe commit (``_publish_ensemble``).

        Returns True when everything above was persisted and False when it
        was not — brain lock held elsewhere, the brain directory or its lock
        file cannot be created, an interrupted full save that cannot be
        completed, a HEAD that a restart would reject (only a full save can
        repair it: ``full_save_required``), the trained-overwrite guard, a
        changed ensemble that could not be written, or any write error
        (logged). Never raises (C12-06: a save that did not happen is
        reported, not claimed).
        """
        # C12-06: the same lock as save()/load(): an essential save never
        # interleaves with a full-save swap or a host-side brain snapshot.
        lock = _BrainLock(self.brain_dir / LOCK_FILE)
        try:
            self.brain_dir.mkdir(parents=True, exist_ok=True)
            lock.acquire()
        except RuntimeError as e:
            logger.warning("Essential brain save NOT persisted — lock held: %s", e)
            return False
        except OSError as e:
            logger.error(
                "Essential brain save NOT persisted — cannot create the brain "
                "directory or open its lock file: %s", e,
            )
            return False

        try:
            # C12-01: never write runtime files into a half-swapped HEAD; an
            # interrupted full save is completed first, or a stale journal is
            # retired with HEAD kept (or this save fails).
            try:
                self._resolve_pending_swap(caller="save_essential_state")
            except BrainHeadIncomplete as exc:
                logger.error(
                    "Essential brain save NOT persisted — the interrupted "
                    "full-save swap cannot be completed (%s); only a full save "
                    "can repair HEAD", exc,
                )
                return False

            # C12 review: runtime files written into a HEAD that a restart
            # rejects (after a backup fallback, or with a listed file missing,
            # unsigned or torn) are not persisted state: the restart loads the
            # same older backup again. Report it; the engine takes a full save.
            rejection = self._head_rejection_reason()
            if rejection:
                logger.error(
                    "Essential brain save NOT persisted — %s; an essential save "
                    "cannot repair HEAD (models, caches and evolved params are "
                    "written only by a full save). No file was written.",
                    rejection,
                )
                return False

            # F2: the trained-state guard lives in _write_manifest_guarded,
            # which also unifies total_runs sourcing with the full save path
            # (the in-memory vs on-disk divergence behind the Apr 8/9 wipe
            # incidents). C12-03: it is evaluated here too, BEFORE any file
            # is written — a blocked save must not leave regressed runtime
            # files behind a protected manifest.
            should_block, reason = self._check_trained_overwrite_guard(
                self.brain_dir, signal_gen, learner,
            )
            if should_block:
                self._log_suspicious_manifest_write(
                    caller="save_essential_state", target=self.brain_dir,
                    signal_gen=signal_gen, learner=learner,
                    force=False, allow_reset=False, reset_reason=None,
                )
                logger.error(
                    "BRAIN SAVE BLOCKED (save_essential_state): refusing to "
                    "overwrite trained manifest with untrained state (%s). "
                    "No file was written.",
                    reason,
                )
                return False

            # Runtime truth — always persist
            self._save_trade_history(self.brain_dir, all_trades)
            self._save_learning_state(self.brain_dir, learner)
            self._save_evaluation_event_history(self.brain_dir, learner)
            if equity_curve is not None:
                self._save_equity_curve(self.brain_dir, equity_curve)
            if epoch_metrics is not None:
                self._save_epoch_metrics(self.brain_dir, epoch_metrics)
            if extra_counters is not None:
                self._save_extra_counters(
                    self.brain_dir, peak_equity, extra_counters
                )
            self._save_governance_state(self.brain_dir, governance_controller)
            self._save_regime_state(self.brain_dir, regime_detector)
            # ML feature config (not model weights) WITH the model-metrics
            # history, in one write (C12-05: two writes erased the history on
            # every essential save, and the review found a kill between the
            # write and the merge still dropped it).
            self._save_ml_state(self.brain_dir, signal_gen, learner)

            # V4 R-F-5 (2026-05-02): persist the RF/LGBM ensemble even
            # when the walk-forward gate blocks a full save.
            # The wave-11d ensemble.save() invocation lives inside
            # _save_ml_models, which save_essential_state intentionally
            # skips because the main clf/reg are promotion-gated. But
            # ensemble persistence is idempotent runtime state (not a
            # promotion), and skipping it means: every tick where the
            # gate blocks the full save, the ensemble files stay absent
            # on disk. After restart, predict() runs XGB-only and the
            # axis-8 parity bug wave-11d closed silently re-opens.
            # C12-02: only when it changed since HEAD last received it —
            # re-pickling and re-signing an unchanged ensemble on every
            # essential save was pure risk (0-byte models on a kill).
            # C12 review (Copilot): _publish_ensemble's renames are not one
            # crash-safe commit, so under the research lock (frozen models:
            # no production path retrains the ensemble) an essential save
            # never publishes one. HEAD keeps the ensemble files it holds,
            # and the next full save writes them in its journaled swap.
            ensemble_ok = True
            ensemble = getattr(signal_gen, "_ensemble", None)
            if (
                ensemble is not None
                and hasattr(ensemble, "save")
                and getattr(ensemble, "_is_trained", None) is not False
                and not self._ensemble_unchanged_on_disk(ensemble)
            ):
                if _models_frozen():
                    logger.info(
                        "save_essential_state: the in-memory ensemble is not "
                        "confirmed in HEAD; models are frozen (research lock), "
                        "so it is left to the next full save's journaled swap",
                    )
                else:
                    key = _ensemble_state_key(ensemble)
                    try:
                        ensemble_ok = self._publish_ensemble(ensemble)
                    except Exception as e:
                        ensemble_ok = False
                        logger.warning(
                            "save_essential_state: ensemble persist failed: %s",
                            e,
                        )
                    self._ensemble_on_disk = key if ensemble_ok else None

            # Manifest write through the unified guarded helper (F1/F2).
            # force=False: essential-save path is unconditionally guarded.
            wrote = self._write_manifest_guarded(
                self.brain_dir, signal_gen, learner,
                caller="save_essential_state",
                force=False,
            )
            if not wrote:
                # Guard or manifest read-back invariant failed (already
                # logged by the helper): the save is NOT complete.
                return False

            logger.info(
                "Essential state saved (all runtime truth, "
                "ML models + evolved_params gated): %d trades, PnL=$%.2f",
                learner.state.total_trades if hasattr(learner, "state") else 0,
                learner.state.cumulative_pnl if hasattr(learner, "state") else 0,
            )

            # V10 WW-1 / Wave-51 (2026-05-03): essential-save now ALSO mints
            # a backup snapshot.  Previously _create_backup was only called
            # from full save(), but live_engine routes most saves through
            # save_essential_state (walk-forward gate).  Production had
            # ZERO backups/ directory, so V9 PP-2's corrupt-HEAD fallback
            # safety net was empty.  Cadence: mint a backup at most once
            # per WW1_BACKUP_INTERVAL_SECONDS (default 1 hour) to avoid
            # disk thrash on every tick.
            try:
                import time as _time
                _now_ts = _time.time()
                _last = getattr(self, "_ww1_last_backup_ts", 0.0)
                _interval = float(
                    os.environ.get("WW1_BACKUP_INTERVAL_SECONDS", "3600")
                )
                if (_now_ts - _last) >= _interval:
                    self._create_backup()
                    self._ww1_last_backup_ts = _now_ts
                    logger.info(
                        "WW-1: minted essential-save backup snapshot",
                    )
            except Exception as _bk_err:
                logger.warning(
                    "WW-1: essential-save backup failed (non-fatal): %s",
                    _bk_err,
                )
            return ensemble_ok
        except Exception as e:
            logger.error("Failed to save essential state: %s", e)
            return False
        finally:
            try:
                lock.release()
            except Exception as _rel_err:
                logger.warning(
                    "Essential brain save lock.release() failed: %s", _rel_err,
                )

    def _ensemble_unchanged_on_disk(self, ensemble: Any) -> bool:
        """C12-02: HEAD already holds exactly this ensemble state."""
        recorded = getattr(self, "_ensemble_on_disk", None)
        current = _ensemble_state_key(ensemble)
        return (
            recorded is not None
            and current is not None
            and recorded[0] is current[0]
            and recorded[1] == current[1]
        )

    def _publish_ensemble(self, ensemble: Any) -> bool:
        """C12-02: write a changed ensemble into HEAD from an essential save.

        The ensemble is serialized into a private staging dir first; only
        when EVERY model pair and the manifest were written are the files
        renamed into HEAD (pairs first, ``ensemble_manifest.json`` last), so
        a serialization failure never publishes a reduced manifest or a
        truncated model. The renames are NOT one crash-safe commit (C12
        review): a kill between them leaves new pair files next to the old
        manifest, and no journal completes or undoes them. Essential saves
        therefore never call this under the research lock (frozen models);
        only the full save's journaled swap is crash-safe. Returns True when
        the ensemble was published, False when HEAD kept its previous
        ensemble (untrained ensembles never reach this).
        """
        stage = self.brain_dir / ENSEMBLE_STAGING_DIR
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True)
        try:
            if not ensemble.save(stage) or not _ensemble_written_completely(stage, ensemble):
                logger.warning(
                    "save_essential_state: the ensemble could not be fully "
                    "serialized; HEAD keeps its previous ensemble files",
                )
                return False
            manifest_name = "ensemble_manifest.json"
            for entry in sorted(stage.iterdir(), key=lambda p: (p.name == manifest_name, p.name)):
                os.replace(entry, self.brain_dir / entry.name)
            _fsync_dir(self.brain_dir)
            return True
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    # ═════════════════════════════════════════════════════════════
    #  PRIVATE — SAVE HELPERS
    # ═════════════════════════════════════════════════════════════

    def _check_trained_overwrite_guard(
        self,
        target: Path,
        signal_gen: Any,
        learner: Any,
        force: bool = False,
        allow_reset: bool = False,
        reset_reason: str | None = None,
    ) -> tuple[bool, str]:
        """Check whether an incoming save would overwrite a trained manifest
        with an untrained/fresh state.

        Returns ``(should_block, reason)``. The caller decides what to do
        (e.g. release a lock, abort, log). This is a pure predicate — it
        does NOT write, log, or mutate anything.

        F3 break-glass semantics: ``force=True`` alone is NOT enough to
        permit a trained→fresh overwrite. The full triad is required:
        ``force=True AND allow_reset=True AND reset_reason`` (non-empty).

        Resolves existing state from the best available source:
        ``self._manifest`` (in-memory) > on-disk ``manifest.json`` > empty.
        The regression test itself is ``_regresses_trained_state`` (audit
        2026-10-05 C12-03 added the trained→untrained model leg).
        """
        # Resolve best available existing state
        existing: dict[str, Any] = {}
        if self._manifest:
            existing = self._manifest
        else:
            manifest_path = target / MANIFEST_FILE
            if manifest_path.is_file():
                try:
                    existing = _read_json(manifest_path)
                except Exception:
                    existing = {}

        if not existing:
            return False, ""  # nothing to protect yet

        regresses, reason = _regresses_trained_state(existing, signal_gen, learner)
        if regresses:
            # F3 break-glass: require the full triad to override.
            # force=True alone is NOT sufficient.
            break_glass_ok = bool(
                force and allow_reset and reset_reason
            )
            if not break_glass_ok:
                return True, reason

        return False, ""

    def _write_manifest_guarded(
        self,
        target: Path,
        signal_gen: Any,
        learner: Any,
        *,
        caller: str,
        force: bool = False,
        allow_reset: bool = False,
        reset_reason: str | None = None,
    ) -> bool:
        """The unified manifest write path. Both ``save()`` (via
        ``_save_manifest``) and (in F2) ``save_essential_state()`` route
        their manifest writes through this method.

        - Resolves ``total_runs`` from a single source (in-memory >
          on-disk > 0) so the full-save and essential-save paths never
          diverge.
        - Applies ``_apply_live_manifest_fields`` for authoritative
          field values from live ``learner.state`` / ``signal_gen``.
        - Applies the trained→fresh overwrite guard as a defense-in-depth
          safety net (the primary guard for ``save()`` fires earlier in
          the caller to preserve lock semantics).
        - Syncs ``self._manifest`` after successful write.

        Returns ``True`` on success, ``False`` if the guard blocked.
        """
        # Defense-in-depth guard (primary guard for save() fires earlier,
        # but this catches any caller that reaches the write path without
        # an early check — including save_essential_state via F2).
        should_block, reason = self._check_trained_overwrite_guard(
            target, signal_gen, learner,
            force=force, allow_reset=allow_reset, reset_reason=reset_reason,
        )
        if should_block:
            # F3: always log suspicious-write instrumentation first,
            # regardless of block/allow outcome.
            self._log_suspicious_manifest_write(
                caller=caller, target=target,
                signal_gen=signal_gen, learner=learner,
                force=force, allow_reset=allow_reset,
                reset_reason=reset_reason,
            )
            logger.error(
                "BRAIN SAVE BLOCKED (%s): refusing to overwrite trained "
                "manifest with untrained state (%s). "
                "Break-glass reset requires force=True AND allow_reset=True "
                "AND reset_reason.",
                caller, reason,
            )
            return False

        # F3: check if this is a break-glass reset that passed the guard.
        # If so, the guard check returned (False, reason) because break_glass_ok
        # was True. We still want the instrumentation + loud warning.
        # Detect this by re-evaluating the trained→fresh predicate directly.
        _existing_for_bg = self._manifest if self._manifest else {}
        if not _existing_for_bg:
            mp = target / MANIFEST_FILE
            if mp.is_file():
                try:
                    _existing_for_bg = _read_json(mp)
                except Exception:
                    _existing_for_bg = {}
        _ex_tr = _existing_for_bg.get("total_trades", 0) or 0
        _ex_ml = bool(_existing_for_bg.get("ml_is_trained", False))
        if _existing_for_bg and _regresses_trained_state(
            _existing_for_bg, signal_gen, learner,
        )[0]:
            # Break-glass passed. Log instrumentation + loud warning.
            self._log_suspicious_manifest_write(
                caller=caller, target=target,
                signal_gen=signal_gen, learner=learner,
                force=force, allow_reset=allow_reset,
                reset_reason=reset_reason,
            )
            logger.warning(
                "BRAIN BREAK-GLASS RESET (%s): intentionally overwriting "
                "trained manifest (total_trades=%d, ml_is_trained=%s). "
                "Reason: %s",
                caller, _ex_tr, _ex_ml, reset_reason,
            )

        # Resolve total_runs from uniform source: in-memory > on-disk > 0
        base_total_runs = self._manifest.get("total_runs") if self._manifest else None
        if base_total_runs is None:
            manifest_path = target / MANIFEST_FILE
            if manifest_path.is_file():
                try:
                    disk = _read_json(manifest_path)
                    base_total_runs = disk.get("total_runs", 0)
                except Exception:
                    base_total_runs = 0
            else:
                base_total_runs = 0

        manifest: dict[str, Any] = {
            "brain_format_version": BRAIN_FORMAT_VERSION,
            # V6 X-3 / Wave-20b (2026-05-03): use injected clock.
            "saved_at": self._now_fn().isoformat(),
            "total_runs": base_total_runs + 1,
        }
        self._apply_live_manifest_fields(manifest, signal_gen, learner)
        _write_json(target / MANIFEST_FILE, manifest)
        # Keep in-memory copy in sync
        self._manifest = dict(manifest)

        # F3: read-back invariant — verify what we wrote matches live state
        try:
            written = _read_json(target / MANIFEST_FILE)
            mismatches: list[str] = []
            if learner is not None and hasattr(learner, "state"):
                st = learner.state
                if written.get("generation") != int(getattr(st, "generation", 0)):
                    mismatches.append(
                        f"generation {written.get('generation')} != "
                        f"{int(getattr(st, 'generation', 0))}"
                    )
                if written.get("total_trades") != int(getattr(st, "total_trades", 0)):
                    mismatches.append(
                        f"total_trades {written.get('total_trades')} != "
                        f"{int(getattr(st, 'total_trades', 0))}"
                    )
                bs_live = getattr(st, "best_sharpe", None)
                if bs_live is not None and np.isfinite(bs_live):
                    bs_expected = round(float(bs_live), 4)
                    if written.get("best_sharpe") != bs_expected:
                        mismatches.append(
                            f"best_sharpe {written.get('best_sharpe')} != "
                            f"{bs_expected}"
                        )
            if signal_gen is not None:
                expected_trained = bool(getattr(signal_gen, "_is_trained", False))
                if written.get("ml_is_trained") != expected_trained:
                    mismatches.append(
                        f"ml_is_trained {written.get('ml_is_trained')} != "
                        f"{expected_trained}"
                    )
                fc = getattr(signal_gen, "_feature_cols", None)
                expected_fc = len(fc) if fc is not None else 0
                if written.get("feature_count") != expected_fc:
                    mismatches.append(
                        f"feature_count {written.get('feature_count')} != "
                        f"{expected_fc}"
                    )
            if mismatches:
                logger.critical(
                    "BRAIN MANIFEST READ-BACK INVARIANT FAILED (%s): %s",
                    caller, "; ".join(mismatches),
                )
                return False
        except Exception as e:
            logger.error(
                "Brain manifest read-back check failed (%s): %s", caller, e,
            )
            # Do not fail the save on read-back exceptions — just log

        return True

    def _log_suspicious_manifest_write(
        self,
        *,
        caller: str,
        target: Path,
        signal_gen: Any,
        learner: Any,
        force: bool,
        allow_reset: bool,
        reset_reason: str | None,
    ) -> None:
        """F3: log detailed forensic information when a manifest write
        would regress a trained brain to fresh/untrained state.

        Fires on EVERY regressive attempt regardless of whether the
        break-glass path then allows it. Captures the caller's stack
        trace so the exact triggering code path can be identified on
        the next recurrence.
        """
        import os
        import threading
        import traceback

        existing = self._manifest if self._manifest else {}
        if not existing:
            mp = target / MANIFEST_FILE
            if mp.is_file():
                try:
                    existing = _read_json(mp)
                except Exception:
                    existing = {}

        existing_summary = {
            k: existing.get(k)
            for k in (
                "generation", "total_trades", "cumulative_pnl",
                "best_sharpe", "ml_is_trained", "feature_count", "total_runs",
            )
        }
        live_state = getattr(learner, "state", None)
        incoming_summary = {
            "generation": getattr(live_state, "generation", None),
            "total_trades": getattr(live_state, "total_trades", None),
            "cumulative_pnl": getattr(live_state, "cumulative_pnl", None),
            "best_sharpe": getattr(live_state, "best_sharpe", None),
            "ml_is_trained": bool(getattr(signal_gen, "_is_trained", False)),
            "feature_count": len(getattr(signal_gen, "_feature_cols", []) or []),
        }
        stack = "".join(traceback.format_stack())
        logger.warning(
            "SUSPICIOUS MANIFEST WRITE (%s): would regress trained brain. "
            "pid=%d thread=%s force=%s allow_reset=%s reset_reason=%r "
            "existing=%s incoming=%s\nStack:\n%s",
            caller,
            os.getpid(),
            threading.current_thread().name,
            force,
            allow_reset,
            reset_reason,
            existing_summary,
            incoming_summary,
            stack,
        )

    def _apply_live_manifest_fields(
        self,
        manifest: dict[str, Any],
        signal_gen: Any,
        learner: Any,
    ) -> None:
        """PATCH B: write manifest fields from live learner.state and
        signal_gen. Used by both the full save path (_save_manifest) and
        the essential-save path (save_essential_state) so both paths
        produce identical authoritative values and self._manifest can
        never drift from the truth.

        Fallback safety: when learner or signal_gen is None, or when an
        attribute is missing, fall back to the existing self._manifest
        value, then to a safe default. Never crash callers.
        """
        if learner is not None and hasattr(learner, "state"):
            state = learner.state
            manifest["generation"] = int(getattr(state, "generation", 0))
            manifest["total_trades"] = int(getattr(state, "total_trades", 0))
            manifest["cumulative_pnl"] = round(
                float(getattr(state, "cumulative_pnl", 0.0)), 2
            )
            raw_bs = getattr(state, "best_sharpe", None)
            if raw_bs is not None and np.isfinite(raw_bs):
                manifest["best_sharpe"] = round(float(raw_bs), 4)
            else:
                manifest["best_sharpe"] = self._manifest.get(
                    "best_sharpe", 0
                )
        else:
            manifest.setdefault(
                "generation", self._manifest.get("generation", 0)
            )
            manifest.setdefault(
                "total_trades", self._manifest.get("total_trades", 0)
            )
            manifest.setdefault(
                "cumulative_pnl", self._manifest.get("cumulative_pnl", 0)
            )
            manifest.setdefault(
                "best_sharpe", self._manifest.get("best_sharpe", 0)
            )

        if signal_gen is not None:
            manifest["ml_is_trained"] = bool(
                getattr(signal_gen, "_is_trained", False)
            )
            feature_cols = getattr(signal_gen, "_feature_cols", None)
            if feature_cols is not None:
                manifest["feature_count"] = len(feature_cols)
            else:
                manifest["feature_count"] = self._manifest.get(
                    "feature_count", 0
                )
        else:
            manifest.setdefault(
                "ml_is_trained", self._manifest.get("ml_is_trained", False)
            )
            manifest.setdefault(
                "feature_count", self._manifest.get("feature_count", 0)
            )

        # V12 W71 (EXT-1): strategy expectancy gate.  External auditor
        # caught this as the single most important miss across 11
        # internal audits — manifest verified execution-correctness
        # without ever recording realized PnL/Sharpe/win-rate.  Compute
        # the full expectancy payload and embed under "strategy_expectancy"
        # so any reader (operator, /health/strategy endpoint, dashboard)
        # can see whether the brain is actually profitable.
        try:
            from backend.organism import strategy_expectancy as _sx
            # Prefer the learner's trade_history (richer source of truth);
            # fall back to brain_persistence's loaded list (which is the
            # CSV view).  Both ultimately resolve to the same closed-trade
            # set so either is correct.
            trades_src: Any = []
            if learner is not None and getattr(learner, "trade_history", None):
                trades_src = learner.trade_history
            elif self.trade_history:
                trades_src = self.trade_history
            all_trades_src = list(trades_src or [])
            strategy_trades_src = [
                t for t in all_trades_src
                if not _is_reconciliation_artifact_trade(t)
            ]
            manifest["strategy_expectancy"] = _sx.compute_from_trades(
                strategy_trades_src
            )
            manifest["all_records_expectancy"] = _sx.compute_from_trades(
                all_trades_src
            )
            manifest["excluded_reconciliation_artifacts"] = (
                len(all_trades_src) - len(strategy_trades_src)
            )
            # Phase 2: persist bounded attribution so strategy health is
            # actionable, not just a headline PnL number.
            from backend.organism import strategy_attribution as _attr
            manifest["strategy_attribution"] = _attr.compute_from_trades(
                strategy_trades_src
            )
            try:
                from backend.organism.strategy_alerts import (
                    maybe_dispatch_low_win_rate_alert,
                )
                maybe_dispatch_low_win_rate_alert(manifest["strategy_expectancy"])
            except Exception as alert_exc:  # noqa: BLE001
                logger.warning(
                    "V13 W94: strategy health alert dispatch failed (%s)",
                    alert_exc,
                )
        except Exception as e:
            # Manifest writes must never crash on expectancy compute —
            # the manifest is too important to block on a math error.
            logger.warning(
                "V12 W71: strategy_expectancy compute failed (%s); "
                "manifest written without expectancy fields", e,
            )

    def _save_manifest(
        self, target: Path, signal_gen: Any, learner: Any,
        *, force: bool = False,
        allow_reset: bool = False,
        reset_reason: str | None = None,
    ) -> None:
        # F1: delegate to the unified guarded write helper.
        self._write_manifest_guarded(
            target, signal_gen, learner,
            caller="save._save_manifest",
            force=force,
            allow_reset=allow_reset,
            reset_reason=reset_reason,
        )

    def _save_ml_models(self, target: Path, signal_gen: Any) -> None:
        # C12-02: which ensemble state this generation holds once committed.
        self._staged_ensemble_key = None
        if signal_gen._is_trained:
            # Every model write is atomic (temp file → fsync → os.replace;
            # same bytes as before): secure_dump_to_path, audit 2026-10-05.
            from backend.utils.secure_pickle import secure_dump_to_path
            secure_dump_to_path(
                signal_gen._clf, target / "ml_classifier.joblib"
            )
            secure_dump_to_path(
                signal_gen._reg, target / "ml_regressor.joblib"
            )
            # Audit-C concern 2 (2026-05-02): persist S17 same-holdout
            # validation cache.
            for attr_name in (
                "_last_val_X", "_last_val_y_dir", "_last_val_y_ret",
            ):
                arr = getattr(signal_gen, attr_name, None)
                if arr is not None:
                    try:
                        secure_dump_to_path(
                            arr, target / f"ml_{attr_name.lstrip('_')}.joblib"
                        )
                    except Exception as e:
                        logger.debug(
                            "Failed to persist %s: %s", attr_name, e,
                        )

            # Audit-C concern 1 (2026-05-02): persist RF/LGBM ensemble.
            # Without this, post-restart predict() runs XGB-only until
            # next retrain — same input produced 0.349 raw-conf swing
            # across restart (axis-8 parity bug from v2 audit).
            ensemble = getattr(signal_gen, "_ensemble", None)
            if ensemble is not None and hasattr(ensemble, "save"):
                try:
                    key = _ensemble_state_key(ensemble)
                    if ensemble.save(target) and _ensemble_written_completely(
                        target, ensemble,
                    ):
                        self._staged_ensemble_key = key
                except Exception as e:
                    logger.warning(
                        "Failed to persist ensemble: %s", e,
                    )

    def _save_ml_state(
        self, target: Path, signal_gen: Any, learner: Any = None,
    ) -> None:
        """Write ml_state.json. With ``learner``, the model-metrics history
        is part of the same single write (audit 2026-10-05 C12-05 review: a
        second read-merge-write left a window in which a kill dropped it)."""
        ml_state = {
            "generation": signal_gen.generation,
            "feature_cols": signal_gen._feature_cols,
            "xgb_params": signal_gen._xgb_params,
            "is_trained": signal_gen._is_trained,
            "train_window": signal_gen.train_window,
        }
        # Latest metrics
        if signal_gen._latest_metrics:
            m = signal_gen._latest_metrics
            ml_state["latest_metrics"] = {
                "generation": m.generation,
                "accuracy": m.accuracy,
                "precision": m.precision,
                "recall": m.recall,
                "f1": m.f1,
                "direction_accuracy": m.direction_accuracy,
                "mean_pred_return": m.mean_pred_return,
                "hit_rate": m.hit_rate,
                "feature_importance_top10": m.feature_importance_top10,
            }
        # Persist ML calibration state.
        # Audit-D finding D-23 (2026-05-02): calibration is also written
        # to extra_counters.json["ml_calibration"] by live_engine's
        # _build_extra_counters. ml_state.json["calibration"] (here) is
        # the CANONICAL source of truth — apply_to_signal_generator at
        # line 417 reads from ml_state first. The extra_counters mirror
        # is kept for backwards compat with consumers that read from
        # there directly. Both are kept in sync via a single
        # signal_gen.calibration_to_dict() call upstream.
        if hasattr(signal_gen, "calibration_to_dict"):
            try:
                ml_state["calibration"] = signal_gen.calibration_to_dict()
            except Exception:
                pass  # calibration is optional
        if learner is not None:
            ml_state["model_metrics_history"] = _model_metrics_history(learner)
        _write_json(target / "ml_state.json", ml_state)

    def _save_model_metrics_history(
        self, target: Path, learner: Any
    ) -> None:
        """Merge the full model metrics history into an existing
        ml_state.json. The save paths write it inside ``_save_ml_state``
        (one write); this read-merge-write remains for direct callers."""
        history = _model_metrics_history(learner)
        # Store inside ml_state.json (reload it, add, rewrite)
        ml_state_path = target / "ml_state.json"
        if ml_state_path.is_file():
            ml_state = _read_json(ml_state_path)
        else:
            ml_state = {}
        ml_state["model_metrics_history"] = history
        _write_json(ml_state_path, ml_state)

    def _save_evaluation_event_history(
        self, target: Path, learner: Any
    ) -> None:
        """J4: Save evaluation event history (accepted + rejected)."""
        events = getattr(learner.state, "evaluation_events", [])
        if events:
            _write_json(target / "evaluation_event_history.json", events)

    def _save_learning_state(self, target: Path, learner: Any) -> None:
        state = learner.state
        ls = {
            "generation": state.generation,
            "total_bars_seen": state.total_bars_seen,
            "total_trades": state.total_trades,
            "cumulative_pnl": round(state.cumulative_pnl, 2),
            "best_sharpe": (
                round(state.best_sharpe, 4)
                if state.best_sharpe != -np.inf else None
            ),
            "best_generation": state.best_generation,
            "retrain_count": state.retrain_count,
            "drift_events": state.drift_events,
            "generation_accuracies": [
                round(a, 4) for a in state.generation_accuracies
            ],
            "bars_since_retrain": learner._bars_since_retrain,
        }
        _write_json(target / "learning_state.json", ls)

    def _save_reference_features(self, target: Path, learner: Any) -> None:
        ref = getattr(learner, "_reference_features", None)
        if ref is not None and isinstance(ref, pd.DataFrame) and len(ref) > 0:
            # V9 PP-1 / Wave-41 (2026-05-03): atomic write-then-rename.
            _write_csv_atomic(ref, target / "reference_feats.csv")

    def _save_trade_history(
        self, target: Path, all_trades: list[Any]
    ) -> None:
        if not all_trades:
            return
        records = []
        for t in all_trades:
            records.append({
                "symbol": t.symbol,
                "direction": t.direction,
                "entry_price": round(t.entry_price, 4),
                "exit_price": round(t.exit_price, 4),
                "entry_bar": t.entry_bar,
                "exit_bar": t.exit_bar,
                "shares": t.shares,
                # V5 B-T-2 / Wave-17d (2026-05-03): the CSV used to
                # store `round(t.pnl, 2)` per trade. learning_state.json
                # stores `round(sum(raw), 2)` as cumulative_pnl. After
                # restart, recomputing `sum(CSV.pnl)` produced 2¢ drift
                # versus the saved cumulative_pnl (sum-of-rounded vs
                # round-of-sum asymmetry; banker's rounding adds bias).
                # Storing 6 decimals here is well within float precision
                # for dollar P&L and lets `round(sum(CSV.pnl), 2)`
                # reconcile to the saved cumulative_pnl exactly across
                # restart. Display layers format to 2dp on render.
                "pnl": round(t.pnl, 6),
                "exit_reason": t.exit_reason,
                "predicted_return": round(t.predicted_return, 6),
                "actual_return": round(t.actual_return, 6),
                "confidence": round(t.confidence, 4),
                "correct_direction": t.correct_direction,
                "is_exploration": getattr(t, "is_exploration", False),
                # V4 R-F-1 (2026-05-02): persist the runtime flag so the
                # audit-G isolation survives a restart. Without this column,
                # only `exit_reason == "reconciliation_adjustment"` rows are
                # recovered via the load-side fallback; orphan-adopted exits
                # (entry_source="reconciliation_orphan") with normal exit
                # reasons would silently lose the flag and re-enter learning.
                "is_reconciliation_artifact": bool(
                    _is_reconciliation_artifact_trade(t)
                ),
                "entry_source": getattr(t, "entry_source", ""),
                "strategy_id": getattr(
                    t,
                    "strategy_id",
                    infer_strategy_id(getattr(t, "entry_source", "")),
                ),
                "regime_at_entry": getattr(t, "regime_at_entry", ""),
                "regime_at_exit": getattr(t, "regime_at_exit", ""),
                "mfe": round(getattr(t, "mfe", 0.0), 4),
                "mae": round(getattr(t, "mae", 0.0), 4),
                "bars_held_at_exit": getattr(t, "bars_held_at_exit", 0),
                "time_in_trade_seconds": round(getattr(t, "time_in_trade_seconds", 0.0), 2),
                "closed_at": getattr(t, "closed_at", ""),
                # Audit 2026-06-11 (measurement integrity): fidelity fields.
                "predicted_return_signed": getattr(
                    t, "predicted_return_signed", None
                ),
                "ml_spoke": bool(getattr(t, "ml_spoke", False)),
                "entry_order_id": getattr(t, "entry_order_id", ""),
                "price_source": getattr(t, "price_source", ""),
                "had_partial_exits": bool(
                    getattr(t, "had_partial_exits", False)
                ),
            })
        df = pd.DataFrame(records)

        # Phase 3.2: If more than MAX_TRADE_ROWS, archive older rows
        if len(df) > MAX_TRADE_ROWS:
            archive_df = df.iloc[:-MAX_TRADE_ROWS]
            df = df.iloc[-MAX_TRADE_ROWS:]  # keep latest

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = (
                self.brain_dir / f"{ARCHIVE_PREFIX}{ts}.csv.gz"
            )
            try:
                archive_df.to_csv(
                    archive_path, index=False, compression="gzip"
                )
                logger.info(
                    "Archived %d old trades to %s",
                    len(archive_df),
                    archive_path.name,
                )
                # Keep at most 10 archive files
                archives = sorted(
                    self.brain_dir.glob(f"{ARCHIVE_PREFIX}*.csv.gz")
                )
                while len(archives) > 10:
                    old = archives.pop(0)
                    old.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Trade archive failed (non-fatal): %s", e)

        # Audit-H finding H-8 (2026-05-02): atomic write — write to .tmp
        # then rename. SIGKILL during pandas streaming write would have
        # left a truncated CSV; on next startup _load_trade_history would
        # fail or lose the latest trades. Now: write-then-rename guarantees
        # the on-disk file is either the previous full state or the new
        # full state — never partial. Audit 2026-10-05 C12-09:
        # _write_csv_atomic adds the fsyncs this path lacked (same
        # ``trade_history.csv.tmp`` temp name, cleanup and re-raise).
        _write_csv_atomic(df, target / "trade_history.csv")

    def _save_equity_curve(
        self, target: Path, equity_curve: list[float]
    ) -> None:
        if equity_curve:
            df = pd.DataFrame({"equity": equity_curve})
            # V9 PP-1 / Wave-41 (2026-05-03): atomic write-then-rename.
            # Previously direct df.to_csv could leave a truncated CSV on
            # SIGKILL or disk-full. Same pattern as trade_history.csv
            # (audit-H H-8). One OOM-kill could lose 161 generations of
            # equity history under the old behavior.
            _write_csv_atomic(df, target / "equity_curve.csv")

    def _save_epoch_metrics(
        self, target: Path, epoch_metrics: list[Any]
    ) -> None:
        if not epoch_metrics:
            return
        records = []
        for m in epoch_metrics:
            if hasattr(m, "to_dict"):
                records.append(m.to_dict())
            elif isinstance(m, dict):
                records.append(m)
        if records:
            df = pd.DataFrame(records)
            # V9 PP-1 / Wave-41 (2026-05-03): atomic write-then-rename.
            _write_csv_atomic(df, target / "epoch_metrics.csv")

    def _save_extra_counters(
        self,
        target: Path,
        peak_equity: float,
        extra_counters: dict[str, Any] | None,
    ) -> None:
        data = {"peak_equity": round(peak_equity, 2)}
        if extra_counters:
            # Strip evolved_params from extra_counters (now in own file)
            cleaned = {k: v for k, v in extra_counters.items()
                       if k != "evolved_params"}
            # Ensure entry_timestamps are serializable (list of floats)
            if "entry_timestamps" in cleaned:
                cleaned["entry_timestamps"] = [
                    float(t) for t in cleaned["entry_timestamps"]
                ]
            data.update(cleaned)
        _write_json(target / "extra_counters.json", data)

    def _save_evolved_params(
        self,
        target: Path,
        evolved_params: dict[str, Any] | None,
    ) -> None:
        """Phase 1.1: Persist evolved_params to its own dedicated file."""
        if evolved_params:
            _write_json(target / "evolved_params.json", evolved_params)

    def _save_governance_state(
        self,
        target: Path,
        governance_controller: Any | None,
    ) -> None:
        """Phase 1.2: Persist governance controller state."""
        if governance_controller is None:
            return
        try:
            state = governance_controller.to_persistence_dict()
            _write_json(target / "governance_state.json", state)
        except AttributeError:
            # Fallback: use to_dict() if to_persistence_dict() not available
            try:
                state = governance_controller.to_dict()
                _write_json(target / "governance_state.json", state)
            except Exception as e:
                logger.warning("Failed to save governance state: %s", e)

    def _save_regime_state(
        self,
        target: Path,
        regime_detector: Any | None,
    ) -> None:
        """Phase 1.3: Persist regime detector running state."""
        if regime_detector is None:
            return
        try:
            state = regime_detector.to_persistence_dict()
            _write_json(target / "regime_state.json", state)
        except AttributeError as e:
            logger.warning("Failed to save regime state: %s", e)

    # ═════════════════════════════════════════════════════════════
    #  PRIVATE — LOAD HELPERS
    # ═════════════════════════════════════════════════════════════

    def _load_manifest(self) -> None:
        self._manifest = _read_json(self.brain_dir / MANIFEST_FILE)
        version = self._manifest.get("brain_format_version", 0)

        if version == BRAIN_FORMAT_VERSION:
            return  # We're current — nothing to do

        if version > BRAIN_FORMAT_VERSION:
            raise ValueError(
                f"Brain was saved by a newer version (v{version}); "
                f"this code only supports v{BRAIN_FORMAT_VERSION}. "
                "Upgrade the platform before loading."
            )

        # ── Auto-migrate older formats ───────────────────────────
        logger.info("Migrating brain from v%d → v%d …", version, BRAIN_FORMAT_VERSION)

        if version < 1:
            # Pre-versioned brain — treat as v1.
            self._manifest["brain_format_version"] = 1
            version = 1

        if version == 1:
            # v1→v2: added evolved_params / governance / regime state files.
            # If they don't exist the individual loaders already default
            # to empty dicts, so we just bump the version marker.
            self._manifest["brain_format_version"] = 2
            version = 2

        # Persist the bumped manifest so next load is seamless.
        # F4 BYPASS AUDIT: this is the only direct manifest write
        # outside the guarded helper. It is SAFE because it writes
        # self._manifest (just read from disk at line 1282) with only
        # brain_format_version bumped. No learner/signal_gen fields are
        # synthesized. Only fires during load() on an older-format brain.
        _write_json(self.brain_dir / MANIFEST_FILE, self._manifest)
        logger.info("Brain migration complete — now at v%d", version)

    def _load_ml_models(self) -> None:
        clf_path = self.brain_dir / "ml_classifier.joblib"
        reg_path = self.brain_dir / "ml_regressor.joblib"
        if clf_path.is_file() and reg_path.is_file():
            # Verify HMAC to guard against pickle-bomb injection. Audit
            # 2026-10-05 C12-04: an unsigned file is never deserialized. An
            # unsigned or torn (truncated signed) model makes this generation
            # unusable (C12 review), exactly as the pre-C12 code's failing
            # joblib.load did: the PP-2 fallback restores the newest backup
            # with signed models instead of loading this one without models.
            models: dict[str, Any] = {}
            for path, attr in [(clf_path, "clf"), (reg_path, "reg")]:
                signed, value = _read_signed_brain_pickle(path, "ML model")
                if not signed:
                    self.clf = None
                    self.reg = None
                    raise BrainHeadIncomplete(
                        f"unsigned or torn ML model pickle {path.name}"
                    )
                models[attr] = value
            self.clf = models["clf"]
            self.reg = models["reg"]
        else:
            self.clf = None
            self.reg = None

    def _load_ml_state(self) -> None:
        path = self.brain_dir / "ml_state.json"
        self.ml_state = _read_json(path) if path.is_file() else {}

    def _load_learning_state(self) -> None:
        path = self.brain_dir / "learning_state.json"
        self.learning_state = _read_json(path) if path.is_file() else {}

    def _load_reference_features(self) -> None:
        path = self.brain_dir / "reference_feats.csv"
        if path.is_file():
            self.reference_features = pd.read_csv(path)
        else:
            self.reference_features = None

    def _load_trade_history(self) -> None:
        path = self.brain_dir / "trade_history.csv"
        if path.is_file():
            df = pd.read_csv(path)
            self.trade_history = df.to_dict("records")
        else:
            self.trade_history = []

    def _load_equity_curve(self) -> None:
        path = self.brain_dir / "equity_curve.csv"
        if path.is_file():
            df = pd.read_csv(path)
            self.equity_curve = df["equity"].tolist()
        else:
            self.equity_curve = []

    def _load_epoch_metrics(self) -> None:
        path = self.brain_dir / "epoch_metrics.csv"
        if path.is_file():
            df = pd.read_csv(path)
            self.epoch_metrics = df.to_dict("records")
        else:
            self.epoch_metrics = []

    def _load_extra_counters(self) -> None:
        path = self.brain_dir / "extra_counters.json"
        self.extra_counters = _read_json(path) if path.is_file() else {}

    def _load_evolved_params(self) -> None:
        """Phase 1.1: Load dedicated evolved_params file.

        Falls back to extra_counters['evolved_params'] for backward compat.
        """
        path = self.brain_dir / "evolved_params.json"
        if path.is_file():
            self.evolved_params = _read_json(path)
        elif "evolved_params" in self.extra_counters:
            # Backward compat: migrate from extra_counters
            self.evolved_params = self.extra_counters.pop("evolved_params")
        else:
            self.evolved_params = {}

    def _load_governance_state(self) -> None:
        """Phase 1.2: Load governance controller state."""
        path = self.brain_dir / "governance_state.json"
        self.governance_state = _read_json(path) if path.is_file() else {}

    def _load_regime_state(self) -> None:
        """Phase 1.3: Load regime detector running state."""
        path = self.brain_dir / "regime_state.json"
        self.regime_state = _read_json(path) if path.is_file() else {}

    def _load_evaluation_event_history(self) -> None:
        """J4: Load evaluation event history."""
        path = self.brain_dir / "evaluation_event_history.json"
        if path.is_file():
            data = _read_json(path)
            self.evaluation_event_history = data if isinstance(data, list) else []
        else:
            self.evaluation_event_history = []

    # ═════════════════════════════════════════════════════════════
    #  BRAIN QUALITY GATES (Phase 1.6)
    # ═════════════════════════════════════════════════════════════

    def validate_brain(self) -> list[str]:
        """Validate brain integrity after loading.

        Returns a list of warning messages. Empty list = all checks passed.
        """
        warnings: list[str] = []

        # Gate 1: Check evolved params for NaN/Inf
        if self.evolved_params:
            for key, val in self.evolved_params.items():
                if isinstance(val, float) and (
                    np.isnan(val) or np.isinf(val)
                ):
                    warnings.append(
                        f"NaN/Inf in evolved_params['{key}'] = {val}"
                    )
                elif isinstance(val, dict):
                    for k2, v2 in val.items():
                        if isinstance(v2, float) and (
                            np.isnan(v2) or np.isinf(v2)
                        ):
                            warnings.append(
                                f"NaN/Inf in evolved_params['{key}']['{k2}'] = {v2}"
                            )

        # Gate 2: Weight normalization checks
        if self.evolved_params:
            alpha_keys = [
                "alpha_weight_ml", "alpha_weight_volume",
                "alpha_weight_momentum", "alpha_weight_breakout",
                "alpha_weight_regime",
            ]
            alpha_vals = [
                self.evolved_params.get(k)
                for k in alpha_keys
                if isinstance(self.evolved_params.get(k), (int, float))
            ]
            if len(alpha_vals) == 5:
                s = sum(alpha_vals)
                if abs(s - 1.0) > 0.05:
                    warnings.append(
                        f"Alpha weights sum={s:.4f}, expected ~1.0"
                    )

            brk_keys = [
                "breakout_weight_squeeze", "breakout_weight_volume",
                "breakout_weight_contraction", "breakout_weight_rs",
                "breakout_weight_pivot", "breakout_weight_flow",
            ]
            brk_vals = [
                self.evolved_params.get(k)
                for k in brk_keys
                if isinstance(self.evolved_params.get(k), (int, float))
            ]
            if len(brk_vals) == 6:
                s = sum(brk_vals)
                if abs(s - 1.0) > 0.05:
                    warnings.append(
                        f"Breakout weights sum={s:.4f}, expected ~1.0"
                    )

        # Gate 3: ML model sanity
        if self.clf is not None:
            try:
                dummy = np.zeros((1, len(self.ml_state.get("feature_cols", []))))
                if dummy.shape[1] > 0:
                    self.clf.predict_proba(dummy)
            except Exception as e:
                warnings.append(f"ML classifier sanity check failed: {e}")

        if self.reg is not None:
            try:
                dummy = np.zeros((1, len(self.ml_state.get("feature_cols", []))))
                if dummy.shape[1] > 0:
                    self.reg.predict(dummy)
            except Exception as e:
                warnings.append(f"ML regressor sanity check failed: {e}")

        # Gate 4: Trade count monotonicity
        manifest_trades = self._manifest.get("total_trades", 0)
        actual_trades = len(self.trade_history)
        if manifest_trades > 0 and actual_trades < manifest_trades * 0.9:
            warnings.append(
                f"Trade count regression: manifest={manifest_trades}, "
                f"actual={actual_trades}"
            )

        # Gate 5: Feature column consistency
        saved_cols = set(self.ml_state.get("feature_cols", []))
        if saved_cols:
            try:
                from backend.organism.ml_features import FEATURE_COLUMNS
                current_cols = set(FEATURE_COLUMNS)
                added = current_cols - saved_cols
                removed = saved_cols - current_cols
                if added:
                    warnings.append(
                        f"Feature schema drift: {len(added)} new feature(s) "
                        f"added since last brain save"
                    )
                if removed:
                    warnings.append(
                        f"Feature schema drift: {len(removed)} feature(s) "
                        f"removed since last brain save"
                    )
            except ImportError:
                pass  # ml_features not available — skip check

        return warnings

    def apply_governance_state(self, governance_controller: Any) -> bool:
        """Phase 1.2: Restore governance state from brain.

        Returns True if state was restored.
        """
        if not self.governance_state:
            return False
        try:
            if hasattr(governance_controller, "from_persistence_dict"):
                governance_controller.from_persistence_dict(self.governance_state)
                return True
        except Exception as e:
            logger.error("Failed to restore governance state: %s", e)
        return False

    def apply_regime_state(self, regime_detector: Any) -> bool:
        """Phase 1.3: Restore regime detector state from brain.

        Returns True if state was restored.
        """
        if not self.regime_state:
            return False
        try:
            if hasattr(regime_detector, "from_persistence_dict"):
                regime_detector.from_persistence_dict(self.regime_state)
                return True
        except Exception as e:
            logger.error("Failed to restore regime state: %s", e)
        return False

    # ═════════════════════════════════════════════════════════════
    #  WALK-FORWARD GATE (Phase 2.6)
    # ═════════════════════════════════════════════════════════════

    def walk_forward_gate(
        self,
        recent_trades: list[Any],
        *,
        min_trades: int = 10,
        regression_threshold: float = 0.95,
        learner: Any = None,
    ) -> tuple[bool, str]:
        """Validate that brain performance hasn't regressed before saving.

        Compares recent live Sharpe against the brain's historical best.
        Returns (should_save, reason).

        Args:
            recent_trades: Recent TradeRecord objects from the current session.
            min_trades: Minimum trades needed to evaluate.
            regression_threshold: brain_N+1.sharpe must be >= best * threshold.
        """
        # Not enough trades to judge
        if len(recent_trades) < min_trades:
            return True, f"Insufficient trades for gate ({len(recent_trades)}<{min_trades})"

        # Calculate current session Sharpe.
        # NOTE: We use *per-trade* returns annualised with sqrt(252).
        # This matches ContinuousLearner._compute_attribution() which
        # computes best_sharpe the same way — so the comparison is
        # apples-to-apples even though it is not a true daily Sharpe.
        returns = []
        for t in recent_trades:
            _dir = float(getattr(t, "direction", 1.0))
            if hasattr(t, "actual_return"):
                # Direction-adjusted: profitable shorts contribute positive return
                returns.append(float(t.actual_return) * _dir)
            elif hasattr(t, "pnl") and hasattr(t, "entry_price"):
                ep = float(t.entry_price) if t.entry_price else 1
                shares = float(getattr(t, "shares", 1)) or 1
                # PnL is already direction-neutral (positive = profitable)
                returns.append(
                    float(t.pnl) / (ep * shares) if ep > 0 else 0
                )
        if not returns:
            return True, "No returns to evaluate"

        import numpy as _np

        arr = _np.array(returns, dtype=float)
        arr = arr[~_np.isnan(arr)]
        if len(arr) < min_trades:
            return True, "Too few valid returns"

        mean_r = float(_np.mean(arr))
        std_r = float(_np.std(arr, ddof=1)) if len(arr) > 1 else 1e-9
        if std_r < 1e-9:
            std_r = 1e-9
        current_sharpe = mean_r / std_r * _np.sqrt(252)

        # Apr-8 Patch C: read the authoritative high-water mark directly
        # from learner.state.best_sharpe when available. The previous
        # implementation read self._manifest["best_sharpe"] and decayed
        # it *= 0.95 on every gated save attempt, compounding to a ~250x
        # collapse in one session (2.776 -> 0.011 on 2026-04-07).
        # learner.state.best_sharpe is maintained by ContinuousLearner as
        # a monotonic high-water mark and must not be mutated here.
        best_sharpe: float = 0.0
        if learner is not None:
            ls = getattr(learner, "state", None)
            lbs = getattr(ls, "best_sharpe", None) if ls is not None else None
            if lbs is not None and _np.isfinite(lbs):
                best_sharpe = float(lbs)
        if best_sharpe <= 0:
            # Fallback for callers that don't pass a learner (e.g. legacy
            # call sites or tests). Read-only — never mutated.
            fallback = self._manifest.get("best_sharpe", 0)
            try:
                best_sharpe = float(fallback) if fallback is not None else 0.0
            except (TypeError, ValueError):
                best_sharpe = 0.0

        if best_sharpe <= 0:
            # No meaningful baseline — always save
            return True, f"No baseline Sharpe, current={current_sharpe:.3f}"

        ratio = current_sharpe / best_sharpe if best_sharpe != 0 else 1.0
        if ratio >= regression_threshold:
            return True, (
                f"Walk-forward passed: current={current_sharpe:.3f}, "
                f"best={best_sharpe:.3f}, ratio={ratio:.3f}"
            )

        logger.warning(
            "Walk-forward regression: current_sharpe=%.3f, "
            "best_sharpe=%.3f, ratio=%.3f < %.3f",
            current_sharpe,
            best_sharpe,
            ratio,
            regression_threshold,
        )
        return False, (
            f"Walk-forward FAIL: current={current_sharpe:.3f}, "
            f"best={best_sharpe:.3f}, ratio={ratio:.3f}"
        )

    # ═════════════════════════════════════════════════════════════
    #  PRIVATE — BACKUP
    # ═════════════════════════════════════════════════════════════

    def _create_backup(self, *, generation: int | None = None) -> Path | None:
        """Backup current brain state before overwrite.

        Returns the new backup directory, or None when the backup failed
        (logged, non-fatal). ``generation`` names the backup when HEAD holds
        another generation than the in-memory manifest (C12 review: a
        rolled-forward generation after a backup fallback).

        V10 WW-2 / Wave-56 (2026-05-03): timestamp uses microsecond
        resolution so 5 backup attempts within one second don't
        collapse onto a single directory via mkdir(exist_ok=True).
        Hazard scenario: startup retry storm or rapid force_save_brain
        admin clicks would silently lose all but the last backup.

        V10 PP2-2 / Wave-56: if a corrupt-HEAD restore was just done
        (see _restore_from_latest_backup), the next periodic save
        would overwrite the corrupt manifest.json with a fresh one,
        losing forensic record.  Capture corrupt HEAD first if a
        marker file says so.

        Audit 2026-10-05 C12-01: the snapshot is copied under a temporary
        ``.partial_*`` name and published with one rename, so an interrupted
        copy (crash, full disk) never leaves a partial ``brain_gen*`` restore
        candidate for the PP-2 fallback to load with missing files.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        gen = generation if generation is not None else self._manifest.get("generation", 0)
        backup_name = f"brain_gen{gen}_{ts}"
        backup_path = self.backup_dir / backup_name
        staging_path = self.backup_dir / f".partial_{backup_name}"

        try:
            for stale in self.backup_dir.glob(".partial_brain_gen*"):
                shutil.rmtree(stale, ignore_errors=True)
            staging_path.mkdir(parents=True, exist_ok=True)
            # Copy all brain files (not backups dir, not lock file). Task 2
            # (2026-07-23): also capture the previous_model/ rollback dir so a
            # backup restore brings it back — _create_backup previously copied
            # only files, so previous_model/ was never in any backup.
            for f in self.brain_dir.iterdir():
                if f.name == LOCK_FILE:
                    continue
                if f.is_file():
                    shutil.copy2(str(f), str(staging_path / f.name))
                elif f.is_dir() and f.name == PREVIOUS_MODEL_DIR:
                    shutil.copytree(
                        str(f), str(staging_path / f.name), dirs_exist_ok=True
                    )
            os.rename(staging_path, backup_path)

            # Prune old backups — keep only the latest MAX_BACKUPS. Task 6
            # (2026-07-23): count only real ``brain_gen*`` backups so the
            # ``quarantine/`` subdir is never pruned (and never displaces a real
            # backup from the retained set).
            backups = sorted(
                [d for d in self.backup_dir.iterdir()
                 if d.is_dir() and d.name.startswith("brain_gen")],
                key=lambda d: d.stat().st_mtime,
            )
            while len(backups) > MAX_BACKUPS:
                old = backups.pop(0)
                shutil.rmtree(old, ignore_errors=True)

            logger.info("Backup created: %s", backup_path.name)
            return backup_path

        except Exception as e:
            logger.warning("Backup failed (non-fatal): %s", e)
            shutil.rmtree(staging_path, ignore_errors=True)
            return None

    def get_trade_records(self) -> list[Any]:
        """Convert stored trade history dicts back to TradeRecord objects.

        Use this to seed engine.all_trades for cumulative accumulation.
        """
        if not self.trade_history:
            return []
        try:
            from backend.organism.continuous_learner import TradeRecord
            records = []
            for td in self.trade_history:
                records.append(TradeRecord(
                    symbol=td.get("symbol", ""),
                    direction=td.get("direction", 0),
                    entry_price=td.get("entry_price", 0),
                    exit_price=td.get("exit_price", 0),
                    entry_bar=td.get("entry_bar", 0),
                    exit_bar=td.get("exit_bar", 0),
                    shares=td.get("shares", 0),
                    pnl=td.get("pnl", 0),
                    exit_reason=td.get("exit_reason", ""),
                    predicted_return=td.get("predicted_return", 0),
                    actual_return=td.get("actual_return", 0),
                    confidence=td.get("confidence", 0),
                    is_exploration=td.get("is_exploration", False),
                    is_reconciliation_artifact=bool(
                        td.get(
                            "is_reconciliation_artifact",
                            (
                                td.get("exit_reason", "") == "reconciliation_adjustment"
                                or td.get("entry_source", "") == "reconciliation_orphan"
                            ),
                        )
                    ),
                    entry_source=td.get("entry_source", ""),
                    strategy_id=td.get(
                        "strategy_id",
                        infer_strategy_id(td.get("entry_source", "")),
                    ),
                    regime_at_entry=td.get("regime_at_entry", ""),
                    regime_at_exit=td.get("regime_at_exit", ""),
                    mfe=td.get("mfe", 0.0),
                    mae=td.get("mae", 0.0),
                    bars_held_at_exit=td.get("bars_held_at_exit", 0),
                    time_in_trade_seconds=td.get("time_in_trade_seconds", 0.0),
                    closed_at=td.get("closed_at", ""),
                    predicted_return_signed=_float_or_none(
                        td.get("predicted_return_signed")
                    ),
                    ml_spoke=_truthy_cell(td.get("ml_spoke")),
                    entry_order_id=str(td.get("entry_order_id", "") or ""),
                    price_source=str(td.get("price_source", "") or ""),
                    had_partial_exits=_truthy_cell(
                        td.get("had_partial_exits")
                    ),
                ))
            return records
        except Exception as e:
            logger.error("Failed to convert trade history: %s", e)
            return []

    def print_brain_status(self) -> None:
        if not self.exists:
            print("  🧠 Brain: empty (first run)")
            return

        try:
            manifest = _read_json(self.brain_dir / MANIFEST_FILE)
        except Exception:
            print("  🧠 Brain: corrupt or unreadable")
            return

        gen = manifest.get("generation", 0)
        runs = manifest.get("total_runs", 0)
        trades = manifest.get("total_trades", 0)
        pnl = manifest.get("cumulative_pnl", 0)
        sharpe = manifest.get("best_sharpe", 0)
        saved = manifest.get("saved_at", "unknown")
        trained = manifest.get("ml_is_trained", False)

        print("  🧠 Brain Status:")
        print(f"     Generation:     {gen}")
        print(f"     Total Runs:     {runs}")
        print(f"     Total Trades:   {trades}")
        print(f"     Cumulative PnL: ${pnl:,.2f}")
        print(f"     Best Sharpe:    {sharpe:.4f}")
        print(f"     ML Trained:     {trained}")
        print(f"     Last Saved:     {saved}")

        # Count backups
        if self.backup_dir.is_dir():
            n_backups = len([d for d in self.backup_dir.iterdir() if d.is_dir()])
            print(f"     Backups:        {n_backups}")


# ═════════════════════════════════════════════════════════════════
# Utility functions
# ═════════════════════════════════════════════════════════════════

def _sanitize_for_json(obj: Any) -> Any:
    """Recursively replace Python float NaN/Inf that json.dump can't handle.

    json.dump's ``default`` callback is only invoked for types it cannot
    serialise natively.  Python ``float`` IS native, so NaN and ±Inf slip
    through and produce invalid JSON (``NaN``, ``Infinity``).  This pre-pass
    converts them to safe representations *before* json.dump sees them.
    """
    if isinstance(obj, float):
        if obj != obj:          # NaN
            return None
        if obj == float("inf"):
            return "Infinity"
        if obj == float("-inf"):
            return "-Infinity"
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    return obj


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON with pretty formatting.

    V5 S-DISK-1 / Wave-19 (2026-05-03): atomic write-then-rename. The
    previous direct open(path, 'w') would leave a partial / truncated
    file if the process died mid-write OR if the disk filled mid-write.
    Writing to `path.tmp` then `os.replace`-ing into place is atomic on
    POSIX — readers see either the previous full state or the new full
    state, never partial. This is the same pattern audit-H H-8 applied
    to trade_history.csv; extending it to every JSON save covers every
    `save_essential_state` companion file (learning_state, governance,
    regime, manifest, evaluation events, ml_state, extra_counters,
    evolved_params).
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(_sanitize_for_json(data), f, indent=2, default=_json_serializer)
            f.flush()
            try:
                import os as _os
                _os.fsync(f.fileno())
            except Exception:
                # fsync isn't critical for atomicity; skip if unavailable.
                pass
        tmp_path.replace(path)
    except Exception:
        # Best-effort cleanup; let the caller see the error.
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise
    _fsync_dir(path.parent)  # C12-09: make the rename durable


def _write_text_atomic(path: Path, text: str) -> None:
    """Replace ``path`` with ``text`` atomically (audit 2026-09-29 R11).

    Same mechanics as ``_write_json`` (same-directory temp file, flush, fsync,
    ``os.replace``) for callers that must keep their own serialization. The
    temp name is unique per call and ends in ``.tmp`` so an orphan left by a
    SIGKILL is swept by save() (PP2-3). On any failure the temp file is
    removed and the previous ``path`` is untouched.
    """
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{os.urandom(6).hex()}.tmp")
    try:
        with open(tmp_path, "x", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
    _fsync_dir(path.parent)  # C12-09: make the rename durable


def _write_csv_atomic(df: "pd.DataFrame", path: Path) -> None:
    """V9 PP-1 / Wave-41 (2026-05-03): atomic write-then-rename for CSVs.

    Same pattern as `_write_json`: write to `<path>.tmp`, fsync, then
    `os.replace` (atomic on POSIX). Readers see either the previous
    full state or the new full state — never partial. Required by
    PP-1 because `df.to_csv(path)` was leaving truncated files on
    SIGKILL or disk-full, and the brain `load()` path then either
    failed or silently reset state to "fresh".
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        df.to_csv(tmp_path, index=False)
        # fsync the tmp file before rename for durability.
        try:
            import os as _os
            with open(tmp_path, "rb") as _f:
                _os.fsync(_f.fileno())
        except Exception:
            pass
        tmp_path.replace(path)
    except Exception:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        raise
    _fsync_dir(path.parent)  # C12-09: make the rename durable


def _fsync_dir(path: Path) -> None:
    """Best-effort fsync of a directory so renames inside it are durable
    (audit 2026-10-05 C12-09). Platforms or filesystems that cannot fsync a
    directory are ignored — atomicity never depends on this, only durability.
    """
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _file_sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unused_child(directory: Path, name: str) -> Path:
    """``directory/name``, or a suffixed sibling name if that is taken."""
    candidate = directory / name
    index = 1
    while os.path.lexists(candidate):
        candidate = directory / f"{name}.{index}"
        index += 1
    return candidate


def _parse_head_inventory(text: str) -> list[str] | None:
    """Entry names of an inventory-format sentinel text, else None."""
    if not text.lstrip().startswith("{"):
        return None  # legacy ISO-timestamp sentinel
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if (
        not isinstance(data, dict)
        or data.get("format") != HEAD_INVENTORY_FORMAT
        or not isinstance(data.get("files"), list)
    ):
        return None
    return [str(name) for name in data["files"]]


def _read_head_inventory(sentinel: Path) -> list[str] | None:
    """Entry names listed by a save-completion sentinel, or None for a
    legacy (timestamp), absent or unreadable sentinel (C12-01)."""
    try:
        text = sentinel.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("C12-01: cannot read %s (%s)", sentinel, exc)
        return None
    listed = _parse_head_inventory(text)
    if listed is None and text.lstrip().startswith("{"):
        logger.warning("C12-01: unparseable save-completion sentinel %s", sentinel)
    return listed


def _sentinel_kind(sentinel: Path) -> str:
    """``"absent"``, ``"inventory"`` (written by this code's swap),
    ``"legacy"`` (anything else that is readable — the pre-fix code writes an
    ISO timestamp on every load and full save) or ``"unreadable"``."""
    try:
        text = sentinel.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return "absent"
    except (OSError, UnicodeDecodeError):
        return "unreadable"
    return "inventory" if _parse_head_inventory(text) is not None else "legacy"


def _full_save_marker_reason(brain_dir: Path) -> str | None:
    """The reason recorded in ``brain_dir``'s full-save-required marker (C12
    review), or None when there is no marker. A marker that cannot be read or
    parsed still counts: only a committed full save removes it."""
    marker = brain_dir / FULL_SAVE_REQUIRED_MARKER
    try:
        text = marker.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None
    except (OSError, UnicodeDecodeError) as exc:
        return f"{FULL_SAVE_REQUIRED_MARKER} is present but unreadable ({exc})"
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    reason = data.get("reason") if isinstance(data, dict) else None
    if isinstance(reason, str) and reason:
        return reason
    return f"{FULL_SAVE_REQUIRED_MARKER} is present"


def _manifest_generation(directory: Path) -> int | None:
    """``generation`` recorded in ``directory``'s manifest.json, or None."""
    try:
        value = _read_json(directory / MANIFEST_FILE).get("generation")
    except Exception:
        return None
    return value if type(value) is int else None


def _file_identity(path: Path) -> dict[str, Any] | None:
    """``{"size", "sha256"}`` of a regular file, ``{"type": "other"}`` for
    any other kind of entry, None when nothing is there (C12-01 journal)."""
    import stat as _stat
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if not _stat.S_ISREG(st.st_mode):
        return {"type": "other"}
    return {"size": st.st_size, "sha256": _file_sha256(path)}


def _generation_inventory_problems(directory: Path) -> list[str] | None:
    """What makes ``directory`` an incomplete generation, per its completion
    inventory: listed entries that are missing (C12-01) and listed pickles
    that are unsigned or torn (C12-04 review — a header check, nothing is
    unpickled). ``[]`` when complete; None when the sentinel carries no
    inventory (legacy timestamp or absent: not checked)."""
    from backend.utils.secure_pickle import is_signed_pickle_file
    listed = _read_head_inventory(directory / SAVE_COMPLETE_SENTINEL)
    if listed is None:
        return None
    problems: list[str] = []
    missing = sorted(n for n in listed if not os.path.lexists(directory / n))
    if missing:
        problems.append(f"missing {missing}")
    unsigned = sorted(
        n for n in listed
        if n.endswith(".joblib") and n not in missing
        and not is_signed_pickle_file(directory / n)
    )
    if unsigned:
        problems.append(f"unsigned or torn pickle(s) {unsigned}")
    return problems


def _prune_corrupt_head_snapshots(brain_dir: Path) -> None:
    """Keep at most MAX_CORRUPT_HEAD_SNAPSHOTS ``corrupt_head_*`` forensic
    dirs in HEAD (newest by mtime), as the PP2-2 path does."""
    try:
        snapshots = sorted(
            (d for d in brain_dir.iterdir()
             if d.is_dir() and d.name.startswith("corrupt_head_")),
            key=lambda d: d.stat().st_mtime,
        )
        while len(snapshots) > MAX_CORRUPT_HEAD_SNAPSHOTS:
            shutil.rmtree(snapshots.pop(0), ignore_errors=True)
    except Exception as exc:
        logger.warning("corrupt_head snapshot prune failed (non-fatal): %s", exc)


def _model_metrics_history(learner: Any) -> list[dict[str, Any]]:
    """The learner's accepted-model metrics history, as persisted in
    ml_state.json['model_metrics_history']."""
    history = []
    for mm in getattr(learner.state, "model_metrics", []):
        history.append({
            "generation": mm.generation,
            "accuracy": mm.accuracy,
            "precision": mm.precision,
            "recall": mm.recall,
            "f1": mm.f1,
            "direction_accuracy": mm.direction_accuracy,
            "mean_pred_return": mm.mean_pred_return,
            "hit_rate": mm.hit_rate,
            "feature_importance_top10": mm.feature_importance_top10,
            "calibration_sample_count": getattr(mm, "calibration_sample_count", 0),
            "calibration_monotonic": getattr(mm, "calibration_monotonic", True),
            "calibration_error": getattr(mm, "calibration_error", 0.0),
            "effective_mean_pred_return": getattr(mm, "effective_mean_pred_return", 0.0),
            "candidate_calibration_sample_count": getattr(mm, "candidate_calibration_sample_count", 0),
            "candidate_calibration_monotonic": getattr(mm, "candidate_calibration_monotonic", True),
            "candidate_calibration_error": getattr(mm, "candidate_calibration_error", 0.0),
            "evaluated_at": getattr(mm, "evaluated_at", ""),
            "accepted": True,  # only accepted models are in model_metrics (J3)
        })
    return history


def _read_signed_brain_pickle(path: Path, component: str) -> tuple[bool, Any]:
    """Deserialize a brain pickle only when it is in the HMAC-signed format.

    Audit 2026-10-05 C12-04: every pickle the platform writes into a brain
    (models, S17 caches, ensemble pairs) is signed by secure_dump_to_path, and
    every model/cache file the production brain loads was found signed, so an
    unsigned file is foreign or tampered. It is never deserialized (pickle
    executes code on load): a CRITICAL line is logged and ``(False, None)`` is
    returned. The main model pair then makes the generation unusable
    (``_load_ml_models`` raises: backup fallback); an S17 cache is handled
    like a missing one. A torn (truncated) signed file fails the same format
    check. A signed file whose signature does not verify still raises
    ``TamperedPickleError`` as before. The bytes that were checked are the
    bytes that are verified and loaded (no second read).
    """
    from backend.utils.secure_pickle import is_signed_pickle, secure_loads
    raw = path.read_bytes()
    if not is_signed_pickle(raw):
        logger.critical(
            "C12-04: refusing to deserialize unsigned or torn brain pickle %s "
            "(%s) — restore a signed copy",
            path, component,
        )
        return False, None
    return True, secure_loads(raw)


def _models_frozen() -> bool:
    """Are the models frozen by the research lock (no production path
    retrains them)? Then an essential save never publishes an ensemble: only
    the full save's journaled swap writes model files (C12 review)."""
    from backend.organism import research_policy
    return bool(research_policy.RESEARCH_POLICY_LOCKED)


def _ensemble_state_key(ensemble: Any) -> tuple[Any, int] | None:
    """(object, state version) of an ensemble, or None when it does not track
    a state version (then essential saves always write it) — C12-02."""
    version = getattr(ensemble, "_state_version", None)
    if type(version) is not int:
        return None
    return (ensemble, version)


def _ensemble_written_completely(target: Path, ensemble: Any) -> bool:
    """Did ``ensemble.save(target)`` write EVERY model pair (C12-02)?"""
    try:
        manifest = json.loads(
            (target / "ensemble_manifest.json").read_text(encoding="utf-8")
        )
        names = [str(entry.get("name")) for entry in manifest.get("models", [])]
    except Exception:
        return False
    expected = [str(name) for name in (getattr(ensemble, "model_names", None) or [])]
    return bool(names) and names == expected and all(
        (target / f"ensemble_{name}_{kind}.joblib").is_file()
        for name in names for kind in ("clf", "reg")
    )


def _regresses_trained_state(
    existing: dict[str, Any], signal_gen: Any, learner: Any,
) -> tuple[bool, str]:
    """Would an incoming save regress the trained state in ``existing``?

    Patch E / F1: the incoming state is completely fresh — total_trades 0,
    untrained ML and generation 0 — while the existing manifest has trades,
    a trained model or a generation.

    Audit 2026-10-05 C12-03: close_accounting restores the learner's
    total_trades/cumulative_pnl at startup even when the brain load FAILED,
    which defeated that test (incoming trades > 0). So a manifest that
    records a trained model is also protected from any incoming state whose
    signal generator is untrained, whatever the trade count. (A save with no
    signal generator at all carries no model information and keeps the
    original test.)
    """
    existing_trades = existing.get("total_trades", 0) or 0
    existing_trained = bool(existing.get("ml_is_trained", False))
    existing_generation = existing.get("generation", 0) or 0
    has_state = learner is not None and hasattr(learner, "state")
    incoming_trades = learner.state.total_trades if has_state else 0
    incoming_trained = bool(getattr(signal_gen, "_is_trained", False))
    incoming_generation = learner.state.generation if has_state else 0

    is_trained_existing = (
        existing_trades > 0 or existing_trained or existing_generation > 0
    )
    is_fresh_incoming = (
        incoming_trades == 0 and not incoming_trained and incoming_generation == 0
    )
    model_regression = (
        existing_trained and signal_gen is not None and not incoming_trained
    )
    reason = (
        f"existing: total_trades={existing_trades}, "
        f"ml_is_trained={existing_trained}, generation={existing_generation}; "
        f"incoming: total_trades={incoming_trades}, "
        f"ml_is_trained={incoming_trained}, generation={incoming_generation}"
    )
    return (is_trained_existing and is_fresh_incoming) or model_regression, reason


def _read_json(path: Path) -> dict[str, Any]:
    """Read JSON safely, restoring special float values."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _restore_special_floats(data)


def _restore_special_floats(obj: Any) -> Any:
    """Walk a JSON-loaded structure and convert Infinity strings back to floats."""
    if isinstance(obj, str):
        if obj == "Infinity":
            return float("inf")
        if obj == "-Infinity":
            return float("-inf")
        return obj
    if isinstance(obj, dict):
        return {k: _restore_special_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_restore_special_floats(v) for v in obj]
    return obj


def _json_serializer(obj: Any) -> Any:
    """Handle numpy / special types in JSON."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if v == -np.inf:
            return "-Infinity"
        if v == np.inf:
            return "Infinity"
        if np.isnan(v):
            return None
        return v
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, float):
        if obj == -np.inf:
            return "-Infinity"
        if obj == np.inf:
            return "Infinity"
    if obj == -np.inf:
        return "-Infinity"
    if obj == np.inf:
        return "Infinity"
    raise TypeError(f"Not JSON serializable: {type(obj)}")
