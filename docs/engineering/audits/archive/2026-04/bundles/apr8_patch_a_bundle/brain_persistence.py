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
    * Atomic writes (write to .tmp → rename) — never corrupt the brain
    * Automatic backup before every save — keep last 5 snapshots
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

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Brain format version — bump if we change what we persist ─────
BRAIN_FORMAT_VERSION = 2          # bumped from 1 → 2 for Phase 3
MANIFEST_FILE = "manifest.json"
MAX_BACKUPS = 5
MAX_TRADE_ROWS = 10_000          # Phase 3.2: keep latest N trades in active CSV
ARCHIVE_PREFIX = "trade_history_archive_"
LOCK_FILE = ".brain.lock"


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

    def __init__(self, brain_dir: str | Path = "organism_brain"):
        self.brain_dir = Path(brain_dir).resolve()
        self.backup_dir = self.brain_dir / "backups"
        self._loaded = False
        self._manifest: dict[str, Any] = {}

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
        """Does a saved brain already exist on disk?"""
        return (self.brain_dir / MANIFEST_FILE).is_file()

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
            print(f"  🧠 No previous brain found — starting fresh")
            self._loaded = False
            return False

        try:
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
            logger.error("Failed to load brain: %s — starting fresh", e)
            print(f"  ⚠️  Brain load failed ({e}) — starting fresh")
            self._loaded = False
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
    ) -> None:
        """Save the organism's full learned state to disk.

        Atomic: writes to temp dir first, then renames.
        Backs up the previous brain before overwriting.
        Thread-safe via cross-platform file lock (Phase 3.1).

        The ``force`` flag is audit-only: ``save()`` always performs the
        same full atomic save regardless of the flag. The walk-forward
        gate lives in the caller (``LiveEngine._save_brain``). ``force=True``
        is set by ``LiveEngine.force_save_brain()`` to signal an explicit
        admin-initiated recovery save for logging/audit trail.
        """
        self.brain_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        lock = _BrainLock(self.brain_dir / LOCK_FILE)
        try:
            lock.acquire()
        except RuntimeError as e:
            logger.warning("Skipping brain save — lock held: %s", e)
            return

        # 1. Backup current brain (if it exists)
        if self.exists:
            self._create_backup()

        # 2. Write everything to a temp directory first (atomic)
        tmp_dir = self.brain_dir / ".tmp_save"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True)

        try:
            self._save_ml_models(tmp_dir, signal_gen)
            self._save_ml_state(tmp_dir, signal_gen)
            self._save_model_metrics_history(tmp_dir, learner)
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
            self._save_manifest(tmp_dir, signal_gen, learner)

            # 3. Atomic swap: rename temp dir to active dir.
            #    First, swap the current brain dir to a staging path,
            #    then move tmp into place, then clean up the old dir.
            #    This minimises the window for corruption.
            old_dir = self.brain_dir.with_name(".brain_old")
            if old_dir.exists():
                shutil.rmtree(old_dir, ignore_errors=True)

            # Move current brain -> old, tmp -> brain
            has_existing = any(
                f for f in self.brain_dir.iterdir()
                if f.name not in (".tmp_save", ".brain_old", LOCK_FILE)
            )
            try:
                if has_existing:
                    # Move current files to old_dir
                    old_dir.mkdir(parents=True, exist_ok=True)
                    for f in list(self.brain_dir.iterdir()):
                        if f.name in (".tmp_save", ".brain_old", LOCK_FILE):
                            continue
                        shutil.move(str(f), str(old_dir / f.name))

                # Move new files from tmp to brain dir
                for f in tmp_dir.iterdir():
                    shutil.move(str(f), str(self.brain_dir / f.name))
            except Exception:
                # Restore from old if anything went wrong
                if old_dir.exists():
                    for f in old_dir.iterdir():
                        dest = self.brain_dir / f.name
                        if not dest.exists():
                            shutil.move(str(f), str(dest))
                raise
            finally:
                shutil.rmtree(old_dir, ignore_errors=True)

            shutil.rmtree(tmp_dir, ignore_errors=True)

            gen = learner.state.generation if hasattr(learner, "state") else 0
            eq_str = f", equity ${equity_curve[-1]:,.0f}" if equity_curve else ""
            print(f"  💾 Brain saved: generation {gen}, "
                  f"{len(all_trades)} trades{eq_str}")
            logger.info(
                "Brain saved successfully to %s%s",
                self.brain_dir,
                " (forced)" if force else "",
            )

        except Exception as e:
            logger.error("Brain save failed: %s", e)
            print(f"  ⚠️  Brain save failed: {e}")
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        finally:
            lock.release()

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
                    entry_source=td.get("entry_source", ""),
                    regime_at_entry=td.get("regime_at_entry", ""),
                    regime_at_exit=td.get("regime_at_exit", ""),
                    mfe=td.get("mfe", 0.0),
                    mae=td.get("mae", 0.0),
                    bars_held_at_exit=td.get("bars_held_at_exit", 0),
                    time_in_trade_seconds=td.get("time_in_trade_seconds", 0.0),
                    closed_at=td.get("closed_at", ""),
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
    ) -> None:
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
          - ml_state.json              (feature config, NOT model weights)
          - manifest.json              (updated trade count + pnl)

        NOT written (promotion-gated):
          - ml_classifier.joblib       (model binary — only on gate pass)
          - ml_regressor.joblib        (model binary — only on gate pass)
          - evolved_params.json        (evolved strategy params — only on gate pass)
        """
        self.brain_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Runtime truth — always persist
            self._save_trade_history(self.brain_dir, all_trades)
            self._save_learning_state(self.brain_dir, learner)
            self._save_evaluation_event_history(self.brain_dir, learner)
            self._save_model_metrics_history(self.brain_dir, learner)
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
            # ML feature config (not model weights)
            self._save_ml_state(self.brain_dir, signal_gen)

            # Update manifest — PATCH B: write authoritative live values
            # from learner.state and signal_gen, not stale self._manifest.
            # The recovery incident (2026-04-08) showed learning_state.json
            # healthy while manifest.json was stale (gen=0, best_sharpe=0,
            # ml_is_trained=false) because this path previously only
            # touched total_trades and cumulative_pnl.
            manifest_path = self.brain_dir / MANIFEST_FILE
            if manifest_path.is_file():
                manifest = _read_json(manifest_path)
            else:
                manifest = {"brain_format_version": BRAIN_FORMAT_VERSION}
            manifest["saved_at"] = datetime.now(timezone.utc).isoformat()
            manifest["total_runs"] = manifest.get("total_runs", 0) + 1
            self._apply_live_manifest_fields(manifest, signal_gen, learner)
            _write_json(manifest_path, manifest)
            # Keep in-memory copy in sync with what we just wrote
            self._manifest = dict(manifest)

            logger.info(
                "Essential state saved (all runtime truth, "
                "ML models + evolved_params gated): %d trades, PnL=$%.2f",
                learner.state.total_trades if hasattr(learner, "state") else 0,
                learner.state.cumulative_pnl if hasattr(learner, "state") else 0,
            )
        except Exception as e:
            logger.error("Failed to save essential state: %s", e)

    # ═════════════════════════════════════════════════════════════
    #  PRIVATE — SAVE HELPERS
    # ═════════════════════════════════════════════════════════════

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

    def _save_manifest(
        self, target: Path, signal_gen: Any, learner: Any
    ) -> None:
        manifest = {
            "brain_format_version": BRAIN_FORMAT_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "total_runs": self._manifest.get("total_runs", 0) + 1,
        }
        self._apply_live_manifest_fields(manifest, signal_gen, learner)
        _write_json(target / MANIFEST_FILE, manifest)
        # Keep in-memory copy in sync with what we just wrote
        self._manifest = dict(manifest)

    def _save_ml_models(self, target: Path, signal_gen: Any) -> None:
        if signal_gen._is_trained:
            from backend.utils.secure_pickle import secure_dump_to_path
            secure_dump_to_path(
                signal_gen._clf, target / "ml_classifier.joblib"
            )
            secure_dump_to_path(
                signal_gen._reg, target / "ml_regressor.joblib"
            )

    def _save_ml_state(self, target: Path, signal_gen: Any) -> None:
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
        # Persist ML calibration state
        if hasattr(signal_gen, "calibration_to_dict"):
            try:
                ml_state["calibration"] = signal_gen.calibration_to_dict()
            except Exception:
                pass  # calibration is optional
        _write_json(target / "ml_state.json", ml_state)

    def _save_model_metrics_history(
        self, target: Path, learner: Any
    ) -> None:
        """Save the full model metrics history for continuity."""
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
            ref.to_csv(target / "reference_feats.csv", index=False)

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
                "pnl": round(t.pnl, 2),
                "exit_reason": t.exit_reason,
                "predicted_return": round(t.predicted_return, 6),
                "actual_return": round(t.actual_return, 6),
                "confidence": round(t.confidence, 4),
                "correct_direction": t.correct_direction,
                "is_exploration": getattr(t, "is_exploration", False),
                "entry_source": getattr(t, "entry_source", ""),
                "regime_at_entry": getattr(t, "regime_at_entry", ""),
                "regime_at_exit": getattr(t, "regime_at_exit", ""),
                "mfe": round(getattr(t, "mfe", 0.0), 4),
                "mae": round(getattr(t, "mae", 0.0), 4),
                "bars_held_at_exit": getattr(t, "bars_held_at_exit", 0),
                "time_in_trade_seconds": round(getattr(t, "time_in_trade_seconds", 0.0), 2),
                "closed_at": getattr(t, "closed_at", ""),
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

        df.to_csv(target / "trade_history.csv", index=False)

    def _save_equity_curve(
        self, target: Path, equity_curve: list[float]
    ) -> None:
        if equity_curve:
            df = pd.DataFrame({"equity": equity_curve})
            df.to_csv(target / "equity_curve.csv", index=False)

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
            df.to_csv(target / "epoch_metrics.csv", index=False)

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

        # Persist the bumped manifest so next load is seamless
        _write_json(self.brain_dir / MANIFEST_FILE, self._manifest)
        logger.info("Brain migration complete — now at v%d", version)

    def _load_ml_models(self) -> None:
        clf_path = self.brain_dir / "ml_classifier.joblib"
        reg_path = self.brain_dir / "ml_regressor.joblib"
        if clf_path.is_file() and reg_path.is_file():
            # Verify HMAC to guard against pickle-bomb injection
            from backend.utils.secure_pickle import (
                secure_load_from_path,
                is_signed_pickle,
            )
            for path, attr in [(clf_path, "clf"), (reg_path, "reg")]:
                raw = path.read_bytes()
                if is_signed_pickle(raw):
                    setattr(self, attr, secure_load_from_path(path))
                else:
                    # Legacy unsigned file — load and re-sign on next save
                    logger.warning(
                        "Loading unsigned ML model %s — will re-sign on "
                        "next brain save",
                        path.name,
                    )
                    setattr(self, attr, joblib.load(path))
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

    def _create_backup(self) -> None:
        """Backup current brain state before overwrite."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        gen = self._manifest.get("generation", 0)
        backup_name = f"brain_gen{gen}_{ts}"
        backup_path = self.backup_dir / backup_name

        try:
            backup_path.mkdir(parents=True, exist_ok=True)
            # Copy all brain files (not backups dir, not lock file)
            for f in self.brain_dir.iterdir():
                if f.is_file() and f.name != LOCK_FILE:
                    shutil.copy2(str(f), str(backup_path / f.name))

            # Prune old backups — keep only the latest MAX_BACKUPS
            backups = sorted(
                [d for d in self.backup_dir.iterdir() if d.is_dir()],
                key=lambda d: d.stat().st_mtime,
            )
            while len(backups) > MAX_BACKUPS:
                old = backups.pop(0)
                shutil.rmtree(old, ignore_errors=True)

            logger.info("Backup created: %s", backup_path.name)

        except Exception as e:
            logger.warning("Backup failed (non-fatal): %s", e)

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
                    entry_source=td.get("entry_source", ""),
                    regime_at_entry=td.get("regime_at_entry", ""),
                    regime_at_exit=td.get("regime_at_exit", ""),
                    mfe=td.get("mfe", 0.0),
                    mae=td.get("mae", 0.0),
                    bars_held_at_exit=td.get("bars_held_at_exit", 0),
                    time_in_trade_seconds=td.get("time_in_trade_seconds", 0.0),
                    closed_at=td.get("closed_at", ""),
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

        print(f"  🧠 Brain Status:")
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
    """Write JSON with pretty formatting."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_sanitize_for_json(data), f, indent=2, default=_json_serializer)


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
