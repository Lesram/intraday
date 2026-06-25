"""
Background ML Trainer — process-isolated retraining that never blocks ticks.

Moves ``_retrain_and_evolve()`` off the hot path so that at 5-second tick
intervals the engine never misses a tick due to model training.

Uses ``concurrent.futures.ProcessPoolExecutor(max_workers=1)`` for CPU
isolation and ``loop.run_in_executor()`` for async integration.

Usage::

    trainer = BackgroundTrainer()
    await trainer.start()

    # In tick loop:
    if trainer.is_training:
        done, result = trainer.get_result()
        if done and result:
            trainer.apply_result(signal_gen, evolution_engine, ...)
    elif bars_since_retrain >= RETRAIN_INTERVAL:
        await trainer.submit_retrain(features, regime, trades, ...)
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Work order Task F (2026-06-25): ML is confirmed noise (corr≈0) and already
# dropped from the entry gate (DROP_ML_FROM_GATE), yet the background trainer
# kept retraining + persisting models every interval — pure compute and added
# brain-corruption surface for an unused model. When disabled, retrain is a
# no-op; the corr(pred, actual) early-warning is still computed cheaply by the
# edge monitor (GET /api/v1/health/edge), so a future real signal isn't missed.
# Default True = byte-identical behavior.
import os as _os
ML_RETRAIN_ENABLED = _os.getenv("ORGANISM_ML_RETRAIN_ENABLED", "true").strip().lower() in ("1", "true", "yes", "y")


@dataclass
class TrainResult:
    """Result from a background training run."""
    accepted: bool = False
    train_metrics: dict[str, Any] | None = None
    new_clf_state: Any = None       # pickled classifier state
    new_reg_state: Any = None       # pickled regressor state
    new_ensemble_state: Any = None  # pickled ensemble state
    evolved_params_dict: dict[str, Any] | None = None
    feature_cols: list[str] | None = None
    duration_s: float = 0.0
    is_trained: bool | None = None       # worker's actual _is_trained outcome
    error: str | None = None             # actual training failure
    rejection_reason: str | None = None  # quality-gate rejection (not a training error)


def _train_in_process(
    features_by_symbol_pickle: dict[str, Any],
    regime: str,
    trades_pickle: list[Any],
    signal_gen_state: dict[str, Any],
    evolution_state: dict[str, Any],
    learner_state: dict[str, Any],
) -> dict[str, Any]:
    """Standalone training function that runs in a separate process.

    Receives serialized state, trains, and returns serialized results.
    This function must be importable at module level for ProcessPoolExecutor.
    """
    import copy
    import time
    import pickle

    import pandas as pd

    t0 = time.time()

    try:
        from backend.organism.ml_signal import MLSignalGenerator
        from backend.organism.ml_features import compute_ml_features, FEATURE_COLUMNS
        from backend.organism.continuous_learner import ContinuousLearner
        from backend.organism.self_evolution import (
            EvolutionEngine, EvolvedParams, apply_evolved_params,
        )

        # Reconstruct features
        features_by_symbol = {}
        for sym, data in features_by_symbol_pickle.items():
            features_by_symbol[sym] = pd.DataFrame(data)

        # Reconstruct signal generator with saved params (full xgb_params surface)
        xgb_p = signal_gen_state.get("xgb_params", {})
        signal_gen = MLSignalGenerator(
            train_window=signal_gen_state.get("train_window", 200),
            n_estimators=xgb_p.get("n_estimators", signal_gen_state.get("n_estimators", 200)),
            max_depth=xgb_p.get("max_depth", signal_gen_state.get("max_depth", 5)),
            learning_rate=xgb_p.get("learning_rate", signal_gen_state.get("learning_rate", 0.05)),
            min_child_weight=xgb_p.get("min_child_weight", 5),
            subsample=xgb_p.get("subsample", 0.8),
            colsample_bytree=xgb_p.get("colsample_bytree", 0.8),
            reg_alpha=xgb_p.get("reg_alpha", 0.1),
            reg_lambda=xgb_p.get("reg_lambda", 1.0),
        )

        # Restore model state if available
        if signal_gen_state.get("clf_pickle"):
            signal_gen._clf = pickle.loads(signal_gen_state["clf_pickle"])
        if signal_gen_state.get("reg_pickle"):
            signal_gen._reg = pickle.loads(signal_gen_state["reg_pickle"])
        if signal_gen_state.get("is_trained"):
            signal_gen._is_trained = True

        # Audit 2026-06-09 finding 3.2: materialize INDEPENDENT copies of the
        # OLD model artifacts so the incumbent can be re-scored on the NEW
        # model's validation holdout (same-holdout comparison — mirrors
        # continuous_learner._validate_new_model S17). NB: train() calls
        # .fit() on self._clf/_reg IN PLACE, so holding a reference to the
        # restored objects would alias the retrained model — deserialize
        # fresh copies from the pickles instead.
        old_clf = (
            pickle.loads(signal_gen_state["clf_pickle"])
            if signal_gen_state.get("clf_pickle") else None
        )
        old_reg = (
            pickle.loads(signal_gen_state["reg_pickle"])
            if signal_gen_state.get("reg_pickle") else None
        )
        old_was_trained = bool(signal_gen_state.get("is_trained"))
        if signal_gen_state.get("feature_cols"):
            signal_gen._feature_cols = signal_gen_state["feature_cols"]

        # Restore full signal generator state
        signal_gen.prediction_horizon = signal_gen_state.get("prediction_horizon", 1)
        signal_gen._direction_threshold_buy = signal_gen_state.get("direction_threshold_buy", 0.52)
        signal_gen._direction_threshold_sell = signal_gen_state.get("direction_threshold_sell", 0.48)
        if signal_gen_state.get("calibration_counts"):
            signal_gen._calibration_counts = signal_gen_state["calibration_counts"]
        if signal_gen_state.get("calibration_map"):
            signal_gen._calibration_map = signal_gen_state["calibration_map"]
        if signal_gen_state.get("evolved_feature_weights"):
            signal_gen._evolved_feature_weights = signal_gen_state["evolved_feature_weights"]

        # Train
        metrics = signal_gen.train(features_by_symbol)

        # V6 X-8 / Wave-20b (2026-05-03): leave `evaluated_at` empty
        # in the worker; the parent process stamps it via the engine's
        # injected clock so replay sees the replay clock, not wall.
        # Workers run in a separate process and can't reach `_now_fn`.
        if metrics is not None and not getattr(metrics, "evaluated_at", ""):
            metrics.evaluated_at = ""

        if metrics is None:
            return {"error": "Training returned None metrics", "duration_s": time.time() - t0}

        # Acceptance gate — delegates to the shared acceptance_gate() function
        # so background and sync paths enforce identical rules.
        from backend.organism.continuous_learner import acceptance_gate
        from backend.organism.ml_signal import ModelMetrics as _MM

        # Audit 2026-06-09 finding 3.2 — preferred path: same-holdout
        # comparison. Score the OLD model on the NEW model's validation set
        # (train() above cached it as _last_val_*). Only when this succeeds
        # is the relative "beat the incumbent" promotion path trustworthy.
        old_metrics_obj = None
        fair_baseline = False
        if old_was_trained and old_clf is not None and old_reg is not None:
            try:
                old_metrics_obj = signal_gen.evaluate_external_clf_reg(old_clf, old_reg)
                if old_metrics_obj is not None:
                    fair_baseline = True
            except Exception:  # noqa: BLE001 - model libs raise mixed types
                old_metrics_obj = None

        # Fallback: historical metrics dict from a DIFFERENT window
        # (apples-to-oranges). Kept for diagnostics, but the relative path
        # stays disabled (allow_relative=False) so a deflated stale baseline
        # cannot wave through a weak challenger (Data Leakage Audit Concern 1).
        old_metrics_dict = learner_state.get("old_model_metrics")
        if old_metrics_obj is None and old_metrics_dict:
            old_metrics_obj = _MM(
                generation=old_metrics_dict.get("generation", 0),
                accuracy=old_metrics_dict.get("accuracy", 0),
                precision=old_metrics_dict.get("precision", 0),
                recall=old_metrics_dict.get("recall", 0),
                f1=old_metrics_dict.get("f1", 0),
                direction_accuracy=old_metrics_dict.get("direction_accuracy", 0),
                mean_pred_return=old_metrics_dict.get("mean_pred_return", 0),
                hit_rate=old_metrics_dict.get("hit_rate", 0),
                calibration_sample_count=old_metrics_dict.get("calibration_sample_count", 0),
                calibration_monotonic=old_metrics_dict.get("calibration_monotonic", True),
                calibration_error=old_metrics_dict.get("calibration_error", 0.0),
                effective_mean_pred_return=old_metrics_dict.get("effective_mean_pred_return", 0.0),
                candidate_calibration_sample_count=old_metrics_dict.get("candidate_calibration_sample_count", 0),
                candidate_calibration_monotonic=old_metrics_dict.get("candidate_calibration_monotonic", True),
                candidate_calibration_error=old_metrics_dict.get("candidate_calibration_error", 0.0),
            )

        accepted, rejection_reason = acceptance_gate(
            metrics,
            old_metrics=old_metrics_obj,
            # Relative promotion only after a verified same-holdout eval
            # (audit 2026-06-09 finding 3.2).
            allow_relative=fair_baseline,
        )

        # Helper to build train_metrics dict (includes calibration + effective fields)
        def _build_train_metrics(m):
            return {
                "accuracy": getattr(m, "accuracy", 0),
                "precision": getattr(m, "precision", 0),
                "recall": getattr(m, "recall", 0),
                "f1": getattr(m, "f1", 0),
                "direction_accuracy": getattr(m, "direction_accuracy", 0),
                "mean_pred_return": getattr(m, "mean_pred_return", 0),
                "effective_mean_pred_return": getattr(m, "effective_mean_pred_return", 0.0),
                "hit_rate": getattr(m, "hit_rate", 0),
                "generation": getattr(m, "generation", 0),
                "calibration_sample_count": getattr(m, "calibration_sample_count", 0),
                "calibration_monotonic": getattr(m, "calibration_monotonic", True),
                "calibration_error": getattr(m, "calibration_error", 0.0),
                "candidate_calibration_sample_count": getattr(m, "candidate_calibration_sample_count", 0),
                "candidate_calibration_monotonic": getattr(m, "candidate_calibration_monotonic", True),
                "candidate_calibration_error": getattr(m, "candidate_calibration_error", 0.0),
                # Plan 2.2: realized-correlation gate field must survive the
                # worker→parent round trip.
                "val_pred_actual_corr": getattr(m, "val_pred_actual_corr", None),
                "val_pred_actual_corr_n": getattr(m, "val_pred_actual_corr_n", 0),
                "evaluated_at": getattr(m, "evaluated_at", ""),
            }

        if not accepted:
            return {
                "accepted": False,
                "rejection_reason": f"Model rejected by quality gate ({rejection_reason})",
                "train_metrics": _build_train_metrics(metrics),
                "duration_s": time.time() - t0,
            }

        # Evolve params — gated by evolution freeze (300 trades)
        evolved_params_dict = None
        _total_trades = evolution_state.get("total_trades", 0)
        if _total_trades < 300:
            logging.getLogger(__name__).info(
                "Evolution freeze active (%d < 300 trades) — skipping evolution in background trainer",
                _total_trades,
            )
        elif trades_pickle:
            from backend.organism.continuous_learner import TradeRecord
            trades = [TradeRecord(**t) if isinstance(t, dict) else t for t in trades_pickle]
            # V4 R-F-6 (2026-05-02): filter reconciliation artifacts before
            # evolution. The synchronous fallback in live_engine._maybe_evolve
            # already filters; the BG path is the primary evolution route in
            # production and was previously unfiltered, leaking
            # cross-session-cleanup bookkeeping into evolved params and
            # creating an organism-level split between sync and BG fitness.
            trades = [
                t for t in trades
                if not getattr(t, "is_reconciliation_artifact", False)
            ]
            recent_trades = trades[-200:]

            if recent_trades:
                evo_engine = EvolutionEngine(
                    alpha=evolution_state.get("alpha", 0.30),
                    max_shift=evolution_state.get("max_shift", 0.20),
                    min_trades=evolution_state.get("min_trades", 8),
                )
                prev_params = EvolvedParams.from_dict(evolution_state.get("evolved_params", {}))
                fi = signal_gen._get_feature_importance()
                new_params = evo_engine.evolve(
                    params=prev_params,
                    trades=recent_trades,
                    feature_importances=fi if fi else None,
                    epoch_regime=regime,
                    all_feature_names=list(FEATURE_COLUMNS),
                )
                evolved_params_dict = new_params.to_dict()

        result = {
            "accepted": True,
            "train_metrics": _build_train_metrics(metrics),
            "clf_pickle": pickle.dumps(signal_gen._clf),
            "reg_pickle": pickle.dumps(signal_gen._reg),
            "feature_cols": signal_gen._feature_cols,
            "evolved_params_dict": evolved_params_dict,
            "is_trained": signal_gen._is_trained,
            "duration_s": time.time() - t0,
        }

        # Include ensemble if available
        if signal_gen._ensemble is not None and hasattr(signal_gen._ensemble, "is_trained"):
            if signal_gen._ensemble.is_trained:
                try:
                    result["ensemble_pickle"] = pickle.dumps(signal_gen._ensemble)
                except Exception:
                    pass

        return result

    except Exception as e:
        return {"error": str(e), "duration_s": time.time() - t0}


class BackgroundTrainer:
    """Manages background ML training in a separate process."""

    def __init__(self, *, now_fn=None) -> None:
        # V6 X-8 / Wave-20b (2026-05-03): clock injection so retrain
        # evaluation timestamps respect replay's clock. The worker
        # process can't see the engine's `_now_fn` directly (separate
        # memory space); instead the worker leaves `evaluated_at` empty
        # and the parent process stamps it with `self._now_fn()` after
        # results return.
        if now_fn is None:
            from datetime import datetime as _dt, timezone as _tz
            self._now_fn = lambda: _dt.now(_tz.utc)
        else:
            self._now_fn = now_fn

        self._executor: ProcessPoolExecutor | None = None
        self._future: asyncio.Future | None = None
        self._is_training = False
        self._last_result: TrainResult | None = None
        self._train_count = 0

    async def start(self) -> None:
        """Initialize the process pool executor."""
        self._executor = ProcessPoolExecutor(max_workers=1)
        logger.info("BackgroundTrainer started (ProcessPoolExecutor, max_workers=1)")

    async def stop(self) -> None:
        """Shut down the executor.

        Audit-J finding J-1 (2026-05-02): executor.shutdown(wait=True) is
        a SYNC blocking call. Calling it inside an async function froze
        the event loop for 10-60s during lifespan shutdown, undermining
        the Phase 1 brain-save-first ordering. Now: offload to a thread
        via asyncio.to_thread so the event loop keeps running.
        """
        if self._executor:
            executor = self._executor
            self._executor = None
            try:
                await asyncio.to_thread(executor.shutdown, wait=True)
            except Exception as e:
                # Don't let shutdown failure cascade — brain_save already ran
                logger.warning("BackgroundTrainer executor shutdown error: %s", e)

    @property
    def is_training(self) -> bool:
        return self._is_training

    @property
    def last_result(self) -> TrainResult | None:
        return self._last_result

    async def submit_retrain(
        self,
        features_by_symbol: dict[str, Any],
        regime: str,
        trades: list[Any],
        signal_gen: Any,
        evolution_engine: Any,
        evolved_params: Any,
        total_trades: int = 0,
    ) -> None:
        """Submit a retrain job to the background process pool.

        Serializes the current state and submits to the executor.
        Non-blocking — returns immediately.
        """
        if not ML_RETRAIN_ENABLED:
            if not getattr(self, "_ml_retrain_disabled_logged", False):
                logger.info(
                    "ML retrain DISABLED (ORGANISM_ML_RETRAIN_ENABLED=false): "
                    "skipping retrain+persist while ML is benched (corr still "
                    "monitored via the edge monitor).",
                )
                self._ml_retrain_disabled_logged = True
            return

        if self._is_training:
            logger.debug("BackgroundTrainer: training already in progress, skipping")
            return

        if self._executor is None:
            logger.warning("BackgroundTrainer not started, running synchronously")
            return

        import pickle

        # Serialize features to dicts for pickling
        features_pickle = {}
        for sym, df in features_by_symbol.items():
            try:
                features_pickle[sym] = df.to_dict(orient="list")
            except Exception:
                continue

        # Serialize model state — include full _xgb_params surface for config parity
        signal_gen_state = {
            "train_window": signal_gen.train_window,
            "xgb_params": {k: v for k, v in signal_gen._xgb_params.items()},
            # Legacy keys for backward compatibility with older workers
            "n_estimators": signal_gen._xgb_params.get("n_estimators", 200),
            "max_depth": signal_gen._xgb_params.get("max_depth", 5),
            "learning_rate": signal_gen._xgb_params.get("learning_rate", 0.05),
            "is_trained": signal_gen._is_trained,
            "feature_cols": signal_gen._feature_cols,
            "prediction_horizon": signal_gen.prediction_horizon,
            "direction_threshold_buy": signal_gen._direction_threshold_buy,
            "direction_threshold_sell": signal_gen._direction_threshold_sell,
            "calibration_counts": signal_gen._calibration_counts,
            "calibration_map": signal_gen._calibration_map,
        }
        if hasattr(signal_gen, "_evolved_feature_weights") and signal_gen._evolved_feature_weights:
            signal_gen_state["evolved_feature_weights"] = signal_gen._evolved_feature_weights
        try:
            signal_gen_state["clf_pickle"] = pickle.dumps(signal_gen._clf)
            signal_gen_state["reg_pickle"] = pickle.dumps(signal_gen._reg)
        except Exception as e:
            logger.warning("Failed to pickle model state: %s", e)

        # Serialize trades
        trades_pickle = []
        for t in trades[-200:]:
            if hasattr(t, "__dict__"):
                trades_pickle.append(
                    {k: v for k, v in t.__dict__.items() if not k.startswith("_")}
                )
            elif isinstance(t, dict):
                trades_pickle.append(t)

        # Evolution state
        evolution_state = {
            "alpha": getattr(evolution_engine, "alpha", 0.30),
            "max_shift": getattr(evolution_engine, "max_shift", 0.20),
            "min_trades": getattr(evolution_engine, "min_trades", 8),
            "evolved_params": evolved_params.to_dict() if hasattr(evolved_params, "to_dict") else {},
            "total_trades": total_trades,
        }

        # Pass old model metrics for acceptance comparison
        learner_state = {}
        if signal_gen._latest_metrics:
            learner_state["old_model_metrics"] = signal_gen._latest_metrics.to_dict()

        self._is_training = True
        loop = asyncio.get_running_loop()

        try:
            self._future = loop.run_in_executor(
                self._executor,
                _train_in_process,
                features_pickle,
                regime,
                trades_pickle,
                signal_gen_state,
                evolution_state,
                learner_state,
            )
            self._train_count += 1
            logger.info("BackgroundTrainer: training job #%d submitted", self._train_count)
        except Exception as e:
            self._is_training = False
            logger.error("BackgroundTrainer submit failed: %s", e)

    def get_result(self) -> tuple[bool, TrainResult | None]:
        """Non-blocking poll for training completion.

        Returns (done, result). If not done, result is None.
        """
        if not self._is_training or self._future is None:
            return False, None

        if not self._future.done():
            return False, None

        # Training complete
        self._is_training = False
        try:
            raw = self._future.result()
        except Exception as e:
            logger.error("BackgroundTrainer process error: %s", e)
            self._last_result = TrainResult(error=str(e))
            # V11 prep / Wave-62 (YY-4 closure): counter symmetry.
            try:
                from backend.organism.live_engine import (
                    ML_RETRAIN_FAILURES, _PROMETHEUS_AVAILABLE,
                )
                if _PROMETHEUS_AVAILABLE:
                    ML_RETRAIN_FAILURES.labels(phase="executor").inc()
            except Exception:
                pass
            # V6 V-T-2 / Wave-20a (2026-05-03): wave-14 shipped this
            # site with the same broken wave-8c anti-pattern — works
            # today only because `get_result()` is polled from the main
            # loop, but the comment anticipates threadpool callers. Use
            # the canonical cross-thread dispatcher.
            try:
                from backend.infra.alerting import (
                    AlertCategory, AlertSeverity, send_alert,
                    dispatch_alert_from_thread,
                )
                _err = e
                ok = dispatch_alert_from_thread(
                    lambda: send_alert(
                        AlertCategory.SYSTEM_ERROR,
                        AlertSeverity.WARNING,
                        "ML Retrain Failed",
                        f"Background trainer raised: {_err}",
                        details={"error_type": type(_err).__name__},
                    )
                )
                if not ok:
                    logger.warning(
                        "ML Retrain Failed alert dropped (no main loop ref)"
                    )
            except Exception:
                pass
            return True, self._last_result

        # Distinguish true training errors from quality-gate rejections.
        # Training errors: raw has "error" but no "rejection_reason" and no "accepted" key.
        # Quality-gate rejections: raw has "rejection_reason" (and accepted=False).
        if isinstance(raw, dict) and raw.get("error") and "accepted" not in raw:
            self._last_result = TrainResult(
                error=raw["error"],
                duration_s=raw.get("duration_s", 0),
            )
            logger.warning("BackgroundTrainer training failed: %s", raw["error"])
            # V11 prep / Wave-62 (YY-4 closure, 2026-05-03): the training-
            # internal-error path was alert-silent + counter-less.
            # Operators relying on dashboards / Slack to spot retrain
            # failures had no signal.  Wire counter + alert.
            try:
                from backend.organism.live_engine import (
                    ML_RETRAIN_FAILURES, _PROMETHEUS_AVAILABLE,
                )
                if _PROMETHEUS_AVAILABLE:
                    ML_RETRAIN_FAILURES.labels(phase="training").inc()
            except Exception:
                pass
            try:
                from backend.infra.alerting import (
                    AlertCategory, AlertSeverity, send_alert,
                    dispatch_alert_from_thread,
                )
                _err = raw["error"]
                ok = dispatch_alert_from_thread(
                    lambda: send_alert(
                        AlertCategory.SYSTEM_ERROR,
                        AlertSeverity.WARNING,
                        "ML Retrain Internal Failure",
                        f"BackgroundTrainer training-internal error: {_err}",
                        details={"phase": "training-internal"},
                    )
                )
                if not ok:
                    logger.warning(
                        "YY-4: ML Retrain Internal alert dropped (no main loop ref)"
                    )
            except Exception as _alert_err:
                logger.warning(
                    "YY-4: ML retrain alert dispatch failed: %s",
                    _alert_err,
                )
            return True, self._last_result

        # Quality-gate rejection: training succeeded but model was rejected
        if isinstance(raw, dict) and raw.get("rejection_reason"):
            self._last_result = TrainResult(
                accepted=False,
                train_metrics=raw.get("train_metrics"),
                rejection_reason=raw["rejection_reason"],
                duration_s=raw.get("duration_s", 0),
            )
            logger.info(
                "BackgroundTrainer: model rejected by quality gate: %s",
                raw["rejection_reason"],
            )
            return True, self._last_result

        self._last_result = TrainResult(
            accepted=raw.get("accepted", False),
            train_metrics=raw.get("train_metrics"),
            new_clf_state=raw.get("clf_pickle"),
            new_reg_state=raw.get("reg_pickle"),
            new_ensemble_state=raw.get("ensemble_pickle"),
            evolved_params_dict=raw.get("evolved_params_dict"),
            feature_cols=raw.get("feature_cols"),
            is_trained=raw.get("is_trained"),
            duration_s=raw.get("duration_s", 0),
        )

        # V6 X-8 / Wave-20b (2026-05-03): stamp evaluation time on the
        # parent-process side using the injected clock so replay sees
        # replay-clock timestamps in evaluation_event_history.json.
        try:
            tm = self._last_result.train_metrics
            if isinstance(tm, dict) and not tm.get("evaluated_at"):
                tm["evaluated_at"] = self._now_fn().isoformat()
        except Exception:
            pass

        logger.info(
            "BackgroundTrainer: training #%d completed in %.1fs (accepted=%s)",
            self._train_count,
            self._last_result.duration_s,
            self._last_result.accepted,
        )
        return True, self._last_result

    def _preserve_incumbent_for_rollback(
        self, signal_gen: Any, result: Any,
    ) -> None:
        """Plan 2.3: snapshot the incumbent model + append a swap-audit
        record before a retrained artifact replaces live inference.

        Writes to ``<brain_dir>/previous_model/`` (clf/reg pickles +
        incumbent metrics) and appends to
        ``<brain_dir>/model_swap_audit.jsonl``. Rollback = load the
        previous_model pickles back into the signal generator.
        """
        import json
        import os
        import pickle
        from pathlib import Path

        brain_dir = Path(os.environ.get("ORGANISM_BRAIN_DIR", "organism_brain"))
        if not brain_dir.is_dir():
            return
        prev_dir = brain_dir / "previous_model"
        prev_dir.mkdir(parents=True, exist_ok=True)

        old_metrics = None
        if getattr(signal_gen, "_latest_metrics", None) is not None:
            try:
                old_metrics = signal_gen._latest_metrics.to_dict()
            except Exception:
                old_metrics = None

        if getattr(signal_gen, "_clf", None) is not None:
            (prev_dir / "clf.pkl").write_bytes(pickle.dumps(signal_gen._clf))
        if getattr(signal_gen, "_reg", None) is not None:
            (prev_dir / "reg.pkl").write_bytes(pickle.dumps(signal_gen._reg))
        (prev_dir / "metrics.json").write_text(json.dumps({
            "generation": getattr(signal_gen, "generation", None),
            "metrics": old_metrics,
        }))

        audit_entry = {
            "swapped_at": self._now_fn().isoformat(),
            "old_generation": getattr(signal_gen, "generation", None),
            "new_metrics": result.train_metrics or {},
            "rejection_reason": result.rejection_reason,
            "rollback_artifacts": str(prev_dir),
        }
        with open(brain_dir / "model_swap_audit.jsonl", "a") as fh:
            fh.write(json.dumps(audit_entry) + "\n")
        logger.info(
            "Model-swap audit: incumbent gen=%s preserved at %s",
            audit_entry["old_generation"], prev_dir,
        )

    def apply_result(
        self,
        signal_gen: Any,
        evolution_engine: Any,
        evolved_params: Any,
        alpha_scanner: Any,
        breakout_scanner: Any,
        kelly_sizer: Any,
        exit_engine: Any,
        total_trades: int = 0,
    ) -> Any:
        """Atomically swap trained model weights into the live engine.

        Returns the new evolved_params (or the original if no change).
        """
        import pickle

        result = self._last_result
        if result is None or not result.accepted:
            return evolved_params

        # Audit 2026-06-09 (plan 2.3): before any swap, preserve the
        # INCUMBENT artifacts and write a swap-audit record. Retrained
        # models previously replaced live inference with no staging and no
        # one-command rollback path. The saved artifacts + audit trail
        # enable instant rollback, and the live edge monitor
        # (backend/organism/edge_monitor.py) provides the post-swap
        # detection: a mature rolling window with corr <= 0 after a swap
        # is the rollback trigger.
        try:
            self._preserve_incumbent_for_rollback(signal_gen, result)
        except Exception as _preserve_err:
            logger.warning(
                "Model-swap audit: incumbent preservation failed "
                "(swap proceeds): %s", _preserve_err,
            )

        # Swap classifier
        if result.new_clf_state:
            try:
                signal_gen._clf = pickle.loads(result.new_clf_state)
            except Exception as e:
                logger.warning("Failed to restore classifier: %s", e)

        # Swap regressor
        if result.new_reg_state:
            try:
                signal_gen._reg = pickle.loads(result.new_reg_state)
            except Exception as e:
                logger.warning("Failed to restore regressor: %s", e)

        # Swap ensemble
        if result.new_ensemble_state and signal_gen._ensemble is not None:
            try:
                signal_gen._ensemble = pickle.loads(result.new_ensemble_state)
            except Exception:
                pass

        # Update feature cols
        if result.feature_cols:
            signal_gen._feature_cols = result.feature_cols

        # Use the worker's actual _is_trained outcome when available.
        # Do not infer trained state from pickle presence.
        if result.is_trained is not None:
            signal_gen._is_trained = result.is_trained

        # Update metrics and generation from accepted training result
        if result.train_metrics:
            from backend.organism.ml_signal import ModelMetrics
            tm = result.train_metrics
            signal_gen._latest_metrics = ModelMetrics(
                generation=tm.get("generation", signal_gen.generation),
                accuracy=tm.get("accuracy", 0),
                precision=tm.get("precision", 0),
                recall=tm.get("recall", 0),
                f1=tm.get("f1", 0),
                direction_accuracy=tm.get("direction_accuracy", 0),
                mean_pred_return=tm.get("mean_pred_return", 0),
                hit_rate=tm.get("hit_rate", 0),
                calibration_sample_count=tm.get("calibration_sample_count", 0),
                calibration_monotonic=tm.get("calibration_monotonic", True),
                calibration_error=tm.get("calibration_error", 0.0),
                effective_mean_pred_return=tm.get("effective_mean_pred_return", 0.0),
                candidate_calibration_sample_count=tm.get("candidate_calibration_sample_count", 0),
                candidate_calibration_monotonic=tm.get("candidate_calibration_monotonic", True),
                candidate_calibration_error=tm.get("candidate_calibration_error", 0.0),
                val_pred_actual_corr=tm.get("val_pred_actual_corr"),
                val_pred_actual_corr_n=tm.get("val_pred_actual_corr_n", 0),
                evaluated_at=tm.get("evaluated_at", ""),
            )
            if "generation" in tm:
                signal_gen.generation = tm["generation"]

        # Apply evolved params — gated by evolution freeze (300 trades)
        if result.evolved_params_dict and total_trades >= 300:
            try:
                from backend.organism.self_evolution import (
                    EvolvedParams, apply_evolved_params,
                )
                new_params = EvolvedParams.from_dict(result.evolved_params_dict)
                apply_evolved_params(
                    new_params,
                    alpha_scanner=alpha_scanner,
                    breakout_scanner=breakout_scanner,
                    kelly_sizer=kelly_sizer,
                    exit_engine=exit_engine,
                    signal_gen=signal_gen,
                )
                if new_params.feature_weights:
                    signal_gen._evolved_feature_weights = new_params.feature_weights
                logger.info(
                    "BackgroundTrainer: model swap complete (gen=%d)",
                    new_params.evolution_generation,
                )
                return new_params
            except Exception as e:
                logger.warning("Failed to apply evolved params: %s", e)
        elif result.evolved_params_dict and total_trades < 300:
            logger.warning(
                "Evolution freeze active (%d < 300 trades) — skipping evolved params application",
                total_trades,
            )

        return evolved_params

    def get_last_evaluation_event(self) -> dict | None:
        """Build an evaluation event dict from the last training result.

        Returns None if no result, or if the result was a training error
        (not a quality-gate evaluation).
        """
        result = self._last_result
        if result is None:
            return None
        # Training errors are not evaluation events
        if result.error and not result.train_metrics:
            return None

        tm = result.train_metrics or {}
        return {
            "evaluated_at": tm.get("evaluated_at", ""),
            "accepted": result.accepted,
            "rejection_reason": result.rejection_reason or "",
            "generation": tm.get("generation", 0),
            "accuracy": tm.get("accuracy", 0),
            "precision": tm.get("precision", 0),
            "direction_accuracy": tm.get("direction_accuracy", 0),
            "hit_rate": tm.get("hit_rate", 0),
            "mean_pred_return": tm.get("mean_pred_return", 0),
            "effective_mean_pred_return": tm.get("effective_mean_pred_return", 0.0),
        }

    def get_stats(self) -> dict[str, Any]:
        """Return trainer statistics."""
        return {
            "is_training": self._is_training,
            "train_count": self._train_count,
            "last_result": {
                "accepted": self._last_result.accepted if self._last_result else None,
                "duration_s": self._last_result.duration_s if self._last_result else None,
                "error": self._last_result.error if self._last_result else None,
            } if self._last_result else None,
        }
