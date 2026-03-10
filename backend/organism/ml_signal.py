"""
Module 2 — ML Signal Generator.

XGBoost ensemble that predicts next-day return direction + magnitude.
Trains on rolling windows; retrains every epoch with walk-forward validation.

Ref: docs/blueprints/SELF_LEARNING_ORGANISM_BLUEPRINT.md §3.2
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

ML_DECAY_RATE = float(os.getenv("ORGANISM_ML_DECAY_RATE", "0.005"))

try:
    from xgboost import XGBClassifier, XGBRegressor
    _HAS_XGB = True
except ImportError:
    _HAS_XGB = False

try:
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
    _HAS_SKLEARN = True
except ImportError:
    _HAS_SKLEARN = False

from backend.organism.ml_features import FEATURE_COLUMNS


# ─── Data Structures ───────────────────────────────────────────────

@dataclass
class MLSignal:
    """One ML-generated trading signal.

    Confidence pipeline (three distinct stages):
        1. raw_confidence    — abs(p_up - 0.5) * 2, direct model output
        2. confidence        — after calibration correction (calibrate_confidence()),
                               this is what most downstream consumers use
        3. effective_confidence — min(calibrated, empirical_precision) or
                               calibrated * 0.75 if insufficient calibration data;
                               used for sizing/gating

    Predicted return pipeline (two stages):
        1. predicted_return          — raw regressor output, may be over-optimistic
        2. effective_predicted_return — damped by calibration_factor * confidence_factor;
                                       used for economic decisions
    """
    symbol: str
    direction: float       # +1 buy, -1 sell, 0 hold
    confidence: float      # [0, 1] — calibrated model confidence (post calibrate_confidence())
    predicted_return: float  # raw regressor output — may be over-optimistic
    feature_importance: dict[str, float] = field(default_factory=dict)
    raw_confidence: float = 0.0       # [0, 1] — pre-calibration model confidence
    effective_confidence: float = 0.0  # min(calibrated, empirical_precision) or calibrated * 0.75
    effective_predicted_return: float = 0.0  # damped by calibration quality + confidence


@dataclass
class ModelMetrics:
    """Training/validation metrics for a model generation.

    Calibration fields (calibration_sample_count, calibration_monotonic,
    calibration_error) reflect the generator's **system-level rolling
    calibration state** — accumulated across all past predictions, not
    derived from this candidate model's validation set alone.  This means
    they measure the *system's* calibration maturity, which determines
    how much trust the acceptance gate places in the model's confidence
    claims.  A fresh system with zero calibration history will have
    calibration_sample_count=0 regardless of the candidate model's
    validation quality.

    Effective mean predicted return (effective_mean_pred_return) uses only
    the calibration sample factor: raw * min(1, cal_samples/30).  This is
    intentionally different from the per-signal effective_predicted_return
    (which also multiplies by confidence_factor) because at the aggregate
    model-evaluation level there is no single per-signal confidence to
    apply — the damping reflects only system calibration maturity.
    """
    generation: int
    accuracy: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    direction_accuracy: float = 0.0
    mean_pred_return: float = 0.0       # raw regressor mean — may be over-optimistic
    hit_rate: float = 0.0  # % of predictions with correct sign
    feature_importance_top10: list[tuple[str, float]] = field(default_factory=list)
    # System-level calibration maturity fields (H1).
    # Source: generator's rolling _calibration_counts, NOT candidate validation.
    calibration_sample_count: int = 0    # total observations across all bins
    calibration_monotonic: bool = True   # are bucket win-rates non-decreasing?
    calibration_error: float = 0.0       # mean abs(expected - actual) across bins
    # Effective (damped) mean predicted return (H3).
    # Damped by system calibration maturity only: raw * min(1, cal_samples/30).
    # Distinct from per-signal effective_predicted_return which also uses
    # confidence_factor.  This is the value the acceptance gate uses for
    # edge verification.
    effective_mean_pred_return: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "direction_accuracy": round(self.direction_accuracy, 4),
            "mean_pred_return": round(self.mean_pred_return, 6),
            "effective_mean_pred_return": round(self.effective_mean_pred_return, 6),
            "hit_rate": round(self.hit_rate, 4),
            "feature_importance_top10": self.feature_importance_top10[:10],
            "calibration_sample_count": self.calibration_sample_count,
            "calibration_monotonic": self.calibration_monotonic,
            "calibration_error": round(self.calibration_error, 4),
        }


# ─── ML Signal Generator ──────────────────────────────────────────

class MLSignalGenerator:
    """XGBoost ensemble for direction + magnitude prediction.

    Architecture:
    - Model A: XGBClassifier for direction (up/down)
    - Model B: XGBRegressor for magnitude (predicted return)
    - Combined signal: direction × confidence × magnitude

    Training:
    - Rolling window: train_size=250, no lookahead
    - Target A: 1 if next-day return > 0, else 0
    - Target B: next-day return (regression)
    - Regularization: max_depth=5, min_child_weight=5, subsample=0.8
    """

    RANDOM_SEED = 42

    def __init__(
        self,
        train_window: int = 250,
        n_estimators: int = 200,
        max_depth: int = 5,
        learning_rate: float = 0.05,
        min_child_weight: int = 5,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        reg_alpha: float = 0.1,
        reg_lambda: float = 1.0,
        prediction_horizon: int = 1,
    ):
        self.train_window = train_window
        self.prediction_horizon = max(1, prediction_horizon)
        self.generation = 0
        self._feature_cols: list[str] = []
        self._is_trained = False
        self._latest_metrics: ModelMetrics | None = None

        self._xgb_params = {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "min_child_weight": min_child_weight,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "reg_alpha": reg_alpha,
            "reg_lambda": reg_lambda,
            "random_state": self.RANDOM_SEED,
            "verbosity": 0,
        }

        # Dynamic direction thresholds (set by EvolutionEngine)
        # HFT-tuned: tighter band = more signals for intraday
        self._direction_threshold_buy: float = 0.52
        self._direction_threshold_sell: float = 0.48

        # Confidence calibration: tracks P(actual_win | predicted_confidence_bin)
        # 5 bins: [0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0]
        self._calibration_counts: list[list[int]] = [[0, 0] for _ in range(5)]  # [correct, total]
        self._calibration_map: list[float] = [1.0] * 5  # multiplier per bin

        self._init_models()

        # Phase 4.4: Ensemble expansion (RF + optional LightGBM)
        self._ensemble: Any = None
        try:
            from backend.organism.ensemble_models import EnsemblePredictor
            self._ensemble = EnsemblePredictor(
                n_estimators=n_estimators,
                max_depth=max_depth,
                learning_rate=learning_rate,
            )
        except Exception:
            pass  # Ensemble not available — single-model mode

    def _init_models(self) -> None:
        """Initialize direction classifier + return regressor."""
        if _HAS_XGB:
            self._clf = XGBClassifier(
                eval_metric="logloss",
                **self._xgb_params,
            )
            self._reg = XGBRegressor(
                objective="reg:squarederror",
                **self._xgb_params,
            )
        elif _HAS_SKLEARN:
            self._clf = GradientBoostingClassifier(
                n_estimators=self._xgb_params["n_estimators"],
                max_depth=self._xgb_params["max_depth"],
                learning_rate=self._xgb_params["learning_rate"],
                subsample=self._xgb_params["subsample"],
                random_state=self.RANDOM_SEED,
            )
            self._reg = GradientBoostingRegressor(
                n_estimators=self._xgb_params["n_estimators"],
                max_depth=self._xgb_params["max_depth"],
                learning_rate=self._xgb_params["learning_rate"],
                subsample=self._xgb_params["subsample"],
                random_state=self.RANDOM_SEED,
            )
        else:
            raise ImportError("Need xgboost or sklearn for ML signal generation")

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    @property
    def metrics(self) -> ModelMetrics | None:
        return self._latest_metrics

    def train(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
        val_ratio: float = 0.2,
    ) -> ModelMetrics:
        """Train ML models on multi-symbol feature data.

        Parameters
        ----------
        features_by_symbol : {symbol: DataFrame with feature columns + close}
        val_ratio : fraction of training data to hold out for validation

        Returns
        -------
        ModelMetrics with in-sample performance.
        """
        self.generation += 1

        # Determine available feature columns
        self._feature_cols = self._select_feature_columns(features_by_symbol)

        # Build training matrix (stack all symbols)
        X_all, y_dir_all, y_ret_all = self._build_training_data(features_by_symbol)

        if len(X_all) < 50:
            self._is_trained = False
            return ModelMetrics(generation=self.generation)

        # Train/val split — per-symbol temporal split to avoid cross-symbol
        # data leakage.  Each symbol's data was appended in chronological
        # order by _build_training_data, so we split within each symbol
        # chunk: first (1 - val_ratio) bars → train, rest → validation.
        X_train, X_val = self._temporal_split(X_all, y_dir_all, y_ret_all, val_ratio)
        y_dir_train = X_train[1]
        y_ret_train = X_train[2]
        X_train = X_train[0]
        y_dir_val = X_val[1]
        y_ret_val = X_val[2]
        X_val = X_val[0]

        # Time-decay sample weights: recent bars get more weight
        weights = self._compute_sample_weights(len(X_train))

        # Train direction classifier
        self._clf.fit(X_train, y_dir_train, sample_weight=weights)

        # Train return regressor
        self._reg.fit(X_train, y_ret_train, sample_weight=weights)

        # Phase 4.4: Train ensemble models
        if self._ensemble is not None:
            try:
                self._ensemble.train(X_train, y_dir_train, y_ret_train)
            except Exception:
                pass  # Ensemble training failure is non-fatal

        # Evaluate on validation set
        metrics = self._evaluate(X_val, y_dir_val, y_ret_val)
        self._latest_metrics = metrics
        self._is_trained = True

        return metrics

    def predict(self, features_df: pd.DataFrame, symbol: str = "") -> MLSignal:
        """Generate ML signal for the latest bar.

        Parameters
        ----------
        features_df : DataFrame with feature columns (only uses last row)
        symbol : symbol name for the signal

        Returns
        -------
        MLSignal with direction, confidence, predicted_return.
        """
        if not self._is_trained:
            return MLSignal(symbol=symbol, direction=0, confidence=0, predicted_return=0, raw_confidence=0, effective_confidence=0)

        # Use only feature columns that were available during training
        available_cols = [c for c in self._feature_cols if c in features_df.columns]
        if not available_cols:
            return MLSignal(symbol=symbol, direction=0, confidence=0, predicted_return=0)

        if len(available_cols) < len(self._feature_cols):
            logger.warning(
                "Feature column mismatch for %s: %d/%d available — zero-padding missing columns",
                symbol,
                len(available_cols),
                len(self._feature_cols),
            )

        # Build full-width feature row: use available columns, zero-pad missing ones
        # so XGBoost always receives the correct feature count.
        row = features_df[available_cols].iloc[-1:]
        full_row = pd.DataFrame(0.0, index=row.index, columns=self._feature_cols)
        full_row[available_cols] = row[available_cols]
        X = full_row.values

        # Replace nan/inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Predict direction probability
        try:
            dir_proba = self._clf.predict_proba(X)[0]
            # dir_proba = [P(down), P(up)]
            p_up = float(dir_proba[1] if len(dir_proba) > 1 else dir_proba[0])
        except Exception as e:
            logger.warning("Direction model inference failed for %s: %s — defaulting to neutral", symbol, e)
            p_up = 0.5

        # Predict return magnitude
        try:
            pred_return = float(self._reg.predict(X)[0])
        except Exception:
            pred_return = 0.0

        # Phase 4.4: Blend ensemble predictions
        if self._ensemble is not None and self._ensemble.is_trained:
            try:
                ens_p_up, ens_ret = self._ensemble.predict(X)
                # Weighted blend: 60% primary XGB, 40% ensemble
                p_up = 0.6 * p_up + 0.4 * ens_p_up
                pred_return = 0.6 * pred_return + 0.4 * ens_ret
            except Exception:
                pass  # Fall back to primary model

        # Direction: dynamic thresholds (evolved by EvolutionEngine)
        if p_up > self._direction_threshold_buy:
            direction = 1.0
        elif p_up < self._direction_threshold_sell:
            direction = -1.0
        else:
            direction = 0.0

        # Stage 1: raw confidence — how far from 0.5
        raw_confidence = abs(p_up - 0.5) * 2  # [0, 1]
        raw_confidence = min(raw_confidence, 1.0)

        # Stage 2: calibrated confidence — apply calibration correction
        calibrated_confidence = self.calibrate_confidence(raw_confidence)

        # Feature importance
        fi = self._get_feature_importance()

        # Stage 3: effective confidence — cap calibrated confidence by
        # empirical precision from calibration data when available.
        eff_conf = self._compute_effective_confidence(calibrated_confidence)

        # H1: effective_predicted_return — damp raw prediction when
        # system calibration maturity is weak or confidence is low.
        eff_pred_return = self._compute_effective_predicted_return(
            pred_return, eff_conf,
        )

        return MLSignal(
            symbol=symbol,
            direction=direction,
            confidence=calibrated_confidence,
            predicted_return=pred_return,
            feature_importance=fi,
            raw_confidence=raw_confidence,
            effective_confidence=eff_conf,
            effective_predicted_return=eff_pred_return,
        )

    def predict_batch(
        self, features_by_symbol: dict[str, pd.DataFrame]
    ) -> dict[str, MLSignal]:
        """Generate signals for multiple symbols."""
        signals = {}
        for symbol, df in features_by_symbol.items():
            signals[symbol] = self.predict(df, symbol)
        return signals

    # ── Internal ───────────────────────────────────────────────────

    def record_prediction_outcome(self, confidence: float, was_correct: bool) -> None:
        """Record whether a prediction at a given confidence was correct."""
        bin_idx = min(int(confidence * 5), 4)
        self._calibration_counts[bin_idx][1] += 1  # total
        if was_correct:
            self._calibration_counts[bin_idx][0] += 1  # correct

    def update_calibration_map(self) -> None:
        """Recompute calibration multipliers from accumulated outcomes."""
        for i in range(5):
            total = self._calibration_counts[i][1]
            if total < 10:
                self._calibration_map[i] = 1.0  # Not enough data
                continue
            actual_rate = self._calibration_counts[i][0] / total
            # Bin midpoint represents the "expected" accuracy
            bin_midpoint = (i * 0.2 + (i + 1) * 0.2) / 2
            if bin_midpoint < 0.01:
                self._calibration_map[i] = 1.0
            else:
                self._calibration_map[i] = min(actual_rate / bin_midpoint, 2.0)

    def _compute_effective_confidence(self, calibrated_confidence: float) -> float:
        """Compute effective_confidence from calibrated (not raw) confidence.

        If calibration data exists (>= 10 observations in bin), cap
        calibrated confidence by the actual empirical precision rate.
        Otherwise, apply a 0.75 discount to account for untested predictions.

        Input is calibrated_confidence (post calibrate_confidence()), not
        the raw model output.
        """
        bin_idx = min(int(calibrated_confidence * 5), 4)
        total = self._calibration_counts[bin_idx][1]
        if total >= 10:
            empirical = self._calibration_counts[bin_idx][0] / total
            return min(calibrated_confidence, empirical)
        return calibrated_confidence * 0.75

    # Minimum calibration samples for full trust in predicted_return.
    # Below this, predicted_return is damped by (samples / threshold).
    MIN_CALIBRATION_SAMPLES = 30

    def _compute_effective_predicted_return(
        self, raw_return: float, effective_confidence: float,
    ) -> float:
        """Per-signal effective predicted return — damps raw by two factors.

        Damping = calibration_factor * confidence_factor
        - calibration_factor: min(1.0, total_samples / MIN_CALIBRATION_SAMPLES)
          where total_samples is from the system-level rolling calibration state
        - confidence_factor: max(effective_confidence, 0.1) — floor prevents
          zeroing out

        Note: this is the per-signal version.  The aggregate model-level
        version (effective_mean_pred_return in ModelMetrics) uses only
        calibration_factor because there is no single per-signal confidence
        at the aggregate level.
        """
        total_samples = sum(c[1] for c in self._calibration_counts)
        cal_factor = min(1.0, total_samples / self.MIN_CALIBRATION_SAMPLES)
        conf_factor = max(effective_confidence, 0.1)  # floor to avoid zeroing out
        damping = cal_factor * conf_factor
        return raw_return * damping

    def calibrate_confidence(self, raw_confidence: float) -> float:
        """Apply calibration correction to raw confidence."""
        bin_idx = min(int(raw_confidence * 5), 4)
        return float(min(raw_confidence * self._calibration_map[bin_idx], 1.0))

    def calibration_quality(self) -> tuple[int, bool, float]:
        """Compute calibration quality summary.

        Returns (total_samples, is_monotonic, calibration_error):
        - total_samples: total observations across all 5 bins
        - is_monotonic: True if bucket win-rates are non-decreasing
          (higher confidence bins should have higher accuracy)
        - calibration_error: mean |expected_rate - actual_rate| across
          bins with >= 10 samples (0.0 if no bins qualify)
        """
        total_samples = sum(c[1] for c in self._calibration_counts)

        # Compute per-bin actual win rates for bins with data
        win_rates: list[float] = []
        errors: list[float] = []
        for i in range(5):
            total = self._calibration_counts[i][1]
            bin_midpoint = (i * 0.2 + (i + 1) * 0.2) / 2
            if total >= 10:
                actual = self._calibration_counts[i][0] / total
                win_rates.append(actual)
                errors.append(abs(bin_midpoint - actual))
            else:
                win_rates.append(float("nan"))

        # Monotonicity: check that non-nan win rates are non-decreasing
        valid = [r for r in win_rates if not math.isnan(r)]
        is_monotonic = all(a <= b + 1e-9 for a, b in zip(valid, valid[1:])) if len(valid) >= 2 else True

        cal_error = float(sum(errors) / len(errors)) if errors else 0.0

        return total_samples, is_monotonic, cal_error

    def calibration_to_dict(self) -> dict[str, Any]:
        """Serialize calibration state for brain persistence."""
        return {
            "counts": self._calibration_counts,
            "map": self._calibration_map,
        }

    def load_calibration(self, data: dict[str, Any]) -> None:
        """Restore calibration state from brain."""
        if not data or not isinstance(data, dict):
            return
        counts = data.get("counts")
        if counts and len(counts) == 5:
            self._calibration_counts = [[int(c[0]), int(c[1])] for c in counts]
        cal_map = data.get("map")
        if cal_map and len(cal_map) == 5:
            self._calibration_map = [float(m) for m in cal_map]

    @staticmethod
    def _compute_sample_weights(n: int) -> np.ndarray:
        """Exponential decay weights — recent samples get 3-5x weight.

        Formula: w_i = exp(-decay_rate * (n - 1 - i))
        where i=0 is oldest, i=n-1 is newest.
        """
        if n <= 1:
            return np.ones(n)
        indices = np.arange(n)
        weights = np.exp(-ML_DECAY_RATE * (n - 1 - indices))
        # Normalize so mean weight = 1 (preserves effective sample size feel)
        weights /= weights.mean()
        return weights

    def _select_feature_columns(
        self, features_by_symbol: dict[str, pd.DataFrame]
    ) -> list[str]:
        """Find feature columns present in all symbol DataFrames.

        If EvolutionEngine has set ``_evolved_feature_weights``,
        features below the selection threshold are dropped —
        the model trains only on features that have proven predictive.
        """
        # Start with the canonical list
        candidates = list(FEATURE_COLUMNS)

        # If evolution has provided feature weights, filter low-weight features
        if hasattr(self, "_evolved_feature_weights") and self._evolved_feature_weights:
            candidates = [
                c for c in candidates
                if self._evolved_feature_weights.get(c, 1.0) >= 0.20
            ]
            # Safety: never drop below 15 features
            if len(candidates) < 15:
                ranked = sorted(
                    FEATURE_COLUMNS,
                    key=lambda f: self._evolved_feature_weights.get(f, 1.0),
                    reverse=True,
                )
                candidates = ranked[:30]

        # Keep only columns that exist in all DataFrames
        for df in features_by_symbol.values():
            candidates = [c for c in candidates if c in df.columns]

        return candidates

    def _build_training_data(
        self, features_by_symbol: dict[str, pd.DataFrame]
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Stack all symbols into training matrices with targets.

        Target direction: 1 if close[t+H] > close[t], else 0
        Target return: (close[t+H] - close[t]) / close[t]
        where H = prediction_horizon (default 1 = next bar).

        Also stores ``_chunk_sizes`` for temporal splitting.
        """
        all_X, all_y_dir, all_y_ret = [], [], []
        chunk_sizes: list[int] = []
        H = self.prediction_horizon

        for symbol, df in features_by_symbol.items():
            if len(df) < max(60, H + 10) or "close" not in df.columns:
                continue

            # Features (current bar) — drop last H bars (no target available)
            X = df[self._feature_cols].values[:-H]
            close = df["close"].values

            # Targets (H bars ahead)
            future_close = close[H:]
            current_close = close[:-H]

            y_dir = (future_close > current_close).astype(int)
            y_ret = (future_close - current_close) / np.where(
                current_close > 0, current_close, 1.0
            )

            # Use only the most recent train_window bars
            if len(X) > self.train_window:
                X = X[-self.train_window:]
                y_dir = y_dir[-self.train_window:]
                y_ret = y_ret[-self.train_window:]

            # Clean
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
            y_ret = np.clip(y_ret, -0.5, 0.5)  # Cap extreme returns

            all_X.append(X)
            all_y_dir.append(y_dir)
            all_y_ret.append(y_ret)
            chunk_sizes.append(len(X))

        if not all_X:
            self._chunk_sizes: list[int] = []
            return np.array([]), np.array([]), np.array([])

        self._chunk_sizes = chunk_sizes

        return (
            np.vstack(all_X),
            np.concatenate(all_y_dir),
            np.concatenate(all_y_ret),
        )

    def _temporal_split(
        self,
        X_all: np.ndarray,
        y_dir_all: np.ndarray,
        y_ret_all: np.ndarray,
        val_ratio: float,
    ) -> tuple[tuple[np.ndarray, np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray, np.ndarray]]:
        """Per-symbol temporal split to avoid cross-symbol data leakage.

        Each symbol's chunk is split independently: first (1 - val_ratio)
        bars go to train, the rest to validation.  This ensures no future
        data from any symbol leaks into the training set.
        """
        chunks = getattr(self, "_chunk_sizes", [])
        if not chunks or sum(chunks) != len(X_all):
            # Fallback to simple temporal split
            split_idx = int(len(X_all) * (1 - val_ratio))
            return (
                (X_all[:split_idx], y_dir_all[:split_idx], y_ret_all[:split_idx]),
                (X_all[split_idx:], y_dir_all[split_idx:], y_ret_all[split_idx:]),
            )

        train_X, train_dir, train_ret = [], [], []
        val_X, val_dir, val_ret = [], [], []
        offset = 0
        for size in chunks:
            s = int(size * (1 - val_ratio))
            train_X.append(X_all[offset : offset + s])
            train_dir.append(y_dir_all[offset : offset + s])
            train_ret.append(y_ret_all[offset : offset + s])
            val_X.append(X_all[offset + s : offset + size])
            val_dir.append(y_dir_all[offset + s : offset + size])
            val_ret.append(y_ret_all[offset + s : offset + size])
            offset += size

        return (
            (np.vstack(train_X), np.concatenate(train_dir), np.concatenate(train_ret)),
            (np.vstack(val_X), np.concatenate(val_dir), np.concatenate(val_ret)),
        )

    def _evaluate(
        self,
        X_val: np.ndarray,
        y_dir_val: np.ndarray,
        y_ret_val: np.ndarray,
    ) -> ModelMetrics:
        """Evaluate models on validation data."""
        metrics = ModelMetrics(generation=self.generation)

        if len(X_val) < 5:
            return metrics

        # Direction accuracy
        try:
            dir_pred = self._clf.predict(X_val)
            metrics.accuracy = float(np.mean(dir_pred == y_dir_val))
            metrics.direction_accuracy = metrics.accuracy

            # Precision / recall for class 1 (up)
            tp = np.sum((dir_pred == 1) & (y_dir_val == 1))
            fp = np.sum((dir_pred == 1) & (y_dir_val == 0))
            fn = np.sum((dir_pred == 0) & (y_dir_val == 1))
            metrics.precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            metrics.recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            if metrics.precision + metrics.recall > 0:
                metrics.f1 = 2 * metrics.precision * metrics.recall / (metrics.precision + metrics.recall)
        except Exception:
            pass

        # Return prediction accuracy (sign match)
        try:
            ret_pred = self._reg.predict(X_val)
            correct_sign = np.sign(ret_pred) == np.sign(y_ret_val)
            metrics.hit_rate = float(np.mean(correct_sign))
            metrics.mean_pred_return = float(np.mean(ret_pred))
        except Exception:
            pass

        # Feature importance
        metrics.feature_importance_top10 = list(self._get_feature_importance().items())[:10]

        # System-level calibration maturity (H1) — snapshot from generator's
        # rolling _calibration_counts, NOT from this candidate model's
        # validation predictions.  These measure how much the *system* has
        # been calibrated by live outcome feedback, which determines how
        # much trust the acceptance gate places in the model.
        cal_samples, cal_mono, cal_err = self.calibration_quality()
        metrics.calibration_sample_count = cal_samples
        metrics.calibration_monotonic = cal_mono
        metrics.calibration_error = cal_err

        # Effective mean predicted return (H3) — damp raw by system calibration
        # maturity only (cal_factor).  Unlike per-signal effective_predicted_return
        # which also multiplies by confidence_factor, this aggregate metric has
        # no single per-signal confidence to apply.
        cal_factor = min(1.0, cal_samples / self.MIN_CALIBRATION_SAMPLES)
        metrics.effective_mean_pred_return = metrics.mean_pred_return * cal_factor

        return metrics

    def _get_feature_importance(self) -> dict[str, float]:
        """Get feature importance from the classifier."""
        fi: dict[str, float] = {}
        try:
            if hasattr(self._clf, "feature_importances_"):
                importances = self._clf.feature_importances_
                for i, col in enumerate(self._feature_cols):
                    if i < len(importances):
                        fi[col] = round(float(importances[i]), 4)
                # Sort descending
                fi = dict(sorted(fi.items(), key=lambda x: x[1], reverse=True))
        except Exception:
            pass
        return fi
