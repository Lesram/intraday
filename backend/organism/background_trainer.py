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

        if metrics is None:
            return {"error": "Training returned None metrics", "duration_s": time.time() - t0}

        # Acceptance gate — delegates to the shared acceptance_gate() function
        # so background and sync paths enforce identical rules.
        from backend.organism.continuous_learner import acceptance_gate
        from backend.organism.ml_signal import ModelMetrics as _MM

        # Reconstruct old metrics for comparison (if available)
        old_metrics_obj = None
        old_metrics_dict = learner_state.get("old_model_metrics")
        if old_metrics_dict:
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

    def __init__(self) -> None:
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
        """Shut down the executor."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

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

        logger.info(
            "BackgroundTrainer: training #%d completed in %.1fs (accepted=%s)",
            self._train_count,
            self._last_result.duration_s,
            self._last_result.accepted,
        )
        return True, self._last_result

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
