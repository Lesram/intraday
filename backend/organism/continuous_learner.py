"""
Module 6 — Continuous Learning Engine.

Orchestrates the full self-improvement loop:
    train → trade → attribute → evaluate → retrain → gate → promote

Works in backtest mode (synchronous, simulated data) or can be
extended for live mode (async, real broker).

Ref: docs/blueprints/SELF_LEARNING_ORGANISM_BLUEPRINT.md §3.6
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backend.organism.ml_features import FEATURE_COLUMNS, compute_ml_features
from backend.organism.ml_signal import MLSignalGenerator, MLSignal, ModelMetrics

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared acceptance gate — used by both ContinuousLearner (sync) and
# BackgroundTrainer (async process).  Extracted as a module-level function
# so that both paths enforce identical rules.
# ---------------------------------------------------------------------------

# Minimum calibration samples for full acceptance confidence.
# Below this, the composite score threshold is raised from 0.25 to 0.35,
# requiring stronger statistical evidence from uncalibrated models.
MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE = 30


def acceptance_gate(
    new_metrics: "ModelMetrics",
    old_metrics: "ModelMetrics | None" = None,
    improvement_threshold: float = 0.05,
) -> tuple[bool, str]:
    """Unified model acceptance gate.

    Returns (accepted, reason).

    Composite score:
        score = hit_rate * 0.4 + accuracy * 0.3 + (direction_acc - 0.5) * 0.6

    Quality constraints (all must hold):
        1. effective_mean_pred_return > 0 -- damped predicted edge must be positive
           (damped by system calibration maturity, NOT per-signal confidence)
        2. precision >= 0.45             -- minimum classification precision
        3. candidate calibration honesty -- if the candidate model's own
           validation calibration has sufficient samples (>= 30), its
           confidence monotonicity must not be inverted
        4. candidate calibration error   -- if candidate calibration has
           sufficient samples, calibration_error must be < 0.25

    Two calibration scopes:
        - System-level (calibration_sample_count, calibration_monotonic,
          calibration_error): from the generator's rolling live state.
          Used for system maturity gate (score threshold adjustment).
        - Candidate-level (candidate_calibration_sample_count,
          candidate_calibration_monotonic, candidate_calibration_error):
          from this model's validation predictions in _evaluate().
          Used for model quality gate (honesty and error checks).

    When system calibration_sample_count < 30 (system immature), the
    minimum composite score threshold is raised from 0.25 to 0.35.
    When candidate calibration sample count < 30, score threshold is
    also raised to 0.35 (candidate unverified).
    """

    def _score(m: "ModelMetrics") -> float:
        return (
            m.hit_rate * 0.4
            + m.accuracy * 0.3
            + max(m.direction_accuracy - 0.5, 0.0) * 0.6
        )

    new_score = _score(new_metrics)

    # Economic and statistical quality constraints.
    has_positive_edge = new_metrics.effective_mean_pred_return > 0
    has_min_precision = new_metrics.precision >= 0.45
    quality_ok = has_positive_edge and has_min_precision

    # System-level calibration maturity gate — determines score threshold.
    sys_cal_samples = new_metrics.calibration_sample_count
    sys_mature = sys_cal_samples >= MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE

    # Candidate-level calibration honesty gate (I1) — uses the candidate
    # model's own validation-set calibration, not the system-level state.
    cand_cal_samples = getattr(new_metrics, "candidate_calibration_sample_count", 0)
    cand_cal_mono = getattr(new_metrics, "candidate_calibration_monotonic", True)
    cand_cal_err = getattr(new_metrics, "candidate_calibration_error", 0.0)
    cand_sufficient = cand_cal_samples >= MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE

    # If candidate calibration is sufficiently sampled but inverted, reject.
    if cand_sufficient and not cand_cal_mono:
        quality_ok = False

    # If candidate calibration error is too high, reject.
    if cand_sufficient and cand_cal_err >= 0.25:
        quality_ok = False

    # Score threshold: raised if either system or candidate calibration
    # is immature (insufficient samples).
    min_score = 0.25 if (sys_mature and cand_sufficient) else 0.35

    # No old model — first model acceptance
    if old_metrics is None:
        accepted = new_score > min_score and quality_ok
        reason = (
            "accepted" if accepted
            else f"score={new_score:.3f}<{min_score}, precision={new_metrics.precision:.3f}, "
                 f"eff_mean_pred_return={new_metrics.effective_mean_pred_return:.4f}, "
                 f"cand_cal_mono={cand_cal_mono}, cand_cal_err={cand_cal_err:.3f}, "
                 f"cand_cal_samples={cand_cal_samples}, sys_cal_samples={sys_cal_samples}"
        )
        return accepted, reason

    old_score = _score(old_metrics)

    # New model must beat old by threshold, OR be above absolute bar
    improved = (new_score - old_score) >= improvement_threshold
    good_enough = new_score >= 0.40 and new_metrics.hit_rate >= 0.48

    accepted = (improved or good_enough) and quality_ok
    reason = (
        "accepted" if accepted
        else f"score={new_score:.3f}, old={old_score:.3f}, precision={new_metrics.precision:.3f}, "
             f"eff_mean_pred_return={new_metrics.effective_mean_pred_return:.4f}, "
             f"cand_cal_mono={cand_cal_mono}, cand_cal_err={cand_cal_err:.3f}, "
             f"cand_cal_samples={cand_cal_samples}, sys_cal_samples={sys_cal_samples}"
    )
    return accepted, reason


@dataclass
class LearningState:
    """Tracks the learner's state across generations."""
    generation: int = 0
    total_bars_seen: int = 0
    total_trades: int = 0
    cumulative_pnl: float = 0.0
    best_sharpe: float = -np.inf
    best_generation: int = 0
    retrain_count: int = 0
    drift_events: int = 0
    model_metrics: list[ModelMetrics] = field(default_factory=list)
    # Rolling accuracy for each generation
    generation_accuracies: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "total_bars_seen": self.total_bars_seen,
            "total_trades": self.total_trades,
            "cumulative_pnl": round(self.cumulative_pnl, 2),
            "best_sharpe": round(self.best_sharpe, 4),
            "best_generation": self.best_generation,
            "retrain_count": self.retrain_count,
            "drift_events": self.drift_events,
            "generation_accuracies": [
                round(a, 4) for a in self.generation_accuracies
            ],
        }


@dataclass
class TradeRecord:
    """Single trade outcome for attribution."""
    symbol: str
    direction: float  # +1 long, -1 short
    entry_price: float
    exit_price: float
    entry_bar: int
    exit_bar: int
    shares: int
    pnl: float
    exit_reason: str
    predicted_return: float
    actual_return: float
    confidence: float
    is_exploration: bool = False

    # v4 (improve7): causal provenance fields for forensic analysis
    entry_source: str = ""         # "alpha", "breakout", "exploration"
    regime_at_entry: str = ""      # regime label at position open
    regime_at_exit: str = ""       # regime label at position close
    mfe: float = 0.0              # max favorable excursion ($)
    mae: float = 0.0              # max adverse excursion ($)
    bars_held_at_exit: int = 0    # actual bars held when exited
    time_in_trade_seconds: float = 0.0  # wall-clock seconds in trade

    @property
    def correct_direction(self) -> bool:
        return (self.direction > 0 and self.actual_return > 0) or \
               (self.direction < 0 and self.actual_return < 0)


class ContinuousLearner:
    """Self-improvement engine that retrains ML models based on outcomes.

    Responsibilities:
        1. Track trade outcomes (predicted vs actual returns)
        2. Compute attribution: which features / predictions were accurate
        3. Detect drift: is the feature distribution shifting?
        4. Trigger retrain: on schedule (every N bars) or on drift
        5. Walk-forward gate: new model must beat old on holdout
        6. Update model weights and feature importance
    """

    def __init__(
        self,
        signal_generator: MLSignalGenerator,
        retrain_every_n_bars: int = 60,   # Retrain every 60 bars
        min_trades_for_eval: int = 10,    # Need 10+ trades to evaluate
        improvement_threshold: float = 0.05,  # 5% improvement required
        drift_threshold: float = 0.10,    # PSI threshold for drift
        drift_check_window: int = 30,     # Check drift every 30 bars
        max_generations: int = 50,        # Safety cap
    ):
        self.signal_gen = signal_generator
        self.retrain_interval = retrain_every_n_bars
        self.min_trades = min_trades_for_eval
        self.improvement_threshold = improvement_threshold
        self.drift_threshold = drift_threshold
        self.drift_check_window = drift_check_window
        self.max_generations = max_generations

        self.state = LearningState()
        self.trade_history: list[TradeRecord] = []
        self._bars_since_retrain = 0
        self._reference_features: pd.DataFrame | None = None

    def record_trade(self, trade: TradeRecord) -> None:
        """Record a completed trade for attribution."""
        self.trade_history.append(trade)
        self.state.total_trades += 1
        self.state.cumulative_pnl += trade.pnl

    def should_retrain(
        self, features_by_symbol: dict[str, pd.DataFrame]
    ) -> tuple[bool, str]:
        """Decide whether to retrain the ML model.

        Returns (should_retrain, reason).
        """
        self._bars_since_retrain += 1
        self.state.total_bars_seen += 1

        # Safety cap
        if self.state.generation >= self.max_generations:
            return False, "max_generations_reached"

        # 1. Scheduled retrain
        if self._bars_since_retrain >= self.retrain_interval:
            return True, "scheduled"

        # 2. Drift detection
        if (self._bars_since_retrain >= self.drift_check_window and
                self._reference_features is not None):
            current_features = self._aggregate_features(features_by_symbol)
            if current_features is not None and len(current_features) > 20:
                drifted, psi_score = self._check_drift(
                    self._reference_features, current_features
                )
                if drifted:
                    self.state.drift_events += 1
                    return True, f"drift_detected(psi={psi_score:.3f})"

        # 3. Performance degradation
        recent_trades = self.trade_history[-20:]
        if len(recent_trades) >= self.min_trades:
            recent_accuracy = sum(
                1 for t in recent_trades if t.correct_direction
            ) / len(recent_trades)
            if recent_accuracy < 0.40:  # Below chance
                return True, f"performance_degraded(acc={recent_accuracy:.2f})"

        return False, "not_needed"

    def retrain(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
    ) -> tuple[bool, ModelMetrics | None]:
        """Execute a retrain cycle with walk-forward validation.

        Returns (accepted, metrics) — accepted=True if new model passed gates.
        """
        self.state.generation += 1
        self.state.retrain_count += 1
        self._bars_since_retrain = 0

        # Save reference features for future drift detection
        agg_features = self._aggregate_features(features_by_symbol)
        if agg_features is not None and len(agg_features) > 0:
            self._reference_features = agg_features.copy()

        # Save old model state for rollback
        import copy
        old_clf = copy.deepcopy(self.signal_gen._clf)
        old_reg = copy.deepcopy(self.signal_gen._reg)
        old_trained = self.signal_gen._is_trained

        # Train new model
        metrics = self.signal_gen.train(features_by_symbol)

        if metrics is None:
            # Training failed — rollback
            self.signal_gen._clf = old_clf
            self.signal_gen._reg = old_reg
            self.signal_gen._is_trained = old_trained
            return False, None

        # Walk-forward validation gate
        accepted = self._validate_new_model(
            features_by_symbol, metrics, old_clf
        )

        if not accepted:
            # Rollback to old model
            self.signal_gen._clf = old_clf
            self.signal_gen._reg = old_reg
            self.signal_gen._is_trained = old_trained
            logger.info(
                "Gen %d: model rejected (acc=%.3f), rolled back",
                self.state.generation, metrics.accuracy,
            )
            return False, metrics

        # Accepted — update state
        self.state.model_metrics.append(metrics)
        if metrics.accuracy > 0:
            self.state.generation_accuracies.append(metrics.accuracy)

        logger.info(
            "Gen %d: model accepted (acc=%.3f, hit=%.3f)",
            self.state.generation, metrics.accuracy, metrics.hit_rate,
        )

        return True, metrics

    def compute_attribution(self, last_n: int = 50) -> dict[str, Any]:
        """Compute performance attribution over recent trades.

        Returns metrics dict with accuracy, avg PnL, feature importance, etc.
        """
        trades = self.trade_history[-last_n:]
        if not trades:
            return {"trade_count": 0}

        correct = sum(1 for t in trades if t.correct_direction)
        total_pnl = sum(t.pnl for t in trades)
        pnl_list = [t.pnl for t in trades]
        # Direction-adjusted returns: profitable trades (long or short)
        # contribute positive return. A profitable short has direction=-1
        # and actual_return<0 (price fell), so actual_return * direction > 0.
        returns_list = [t.actual_return * t.direction for t in trades]

        # Sharpe-like metric on trade returns
        if len(returns_list) > 1:
            mean_r = np.mean(returns_list)
            std_r = np.std(returns_list, ddof=1)
            sharpe_proxy = (mean_r / std_r * np.sqrt(252)) if std_r > 1e-8 else 0.0
        else:
            sharpe_proxy = 0.0

        # Track best
        if sharpe_proxy > self.state.best_sharpe:
            self.state.best_sharpe = sharpe_proxy
            self.state.best_generation = self.state.generation

        # By-symbol breakdown
        by_symbol: dict[str, dict[str, float]] = {}
        for t in trades:
            if t.symbol not in by_symbol:
                by_symbol[t.symbol] = {"pnl": 0, "trades": 0, "correct": 0}
            by_symbol[t.symbol]["pnl"] += t.pnl
            by_symbol[t.symbol]["trades"] += 1
            if t.correct_direction:
                by_symbol[t.symbol]["correct"] += 1

        # Exit reason breakdown
        exit_reasons: dict[str, int] = {}
        for t in trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

        return {
            "trade_count": len(trades),
            "accuracy": correct / len(trades),
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(np.mean(pnl_list), 2),
            "sharpe_proxy": round(sharpe_proxy, 4),
            "generation": self.state.generation,
            "best_sharpe": round(self.state.best_sharpe, 4),
            "best_generation": self.state.best_generation,
            "by_symbol": by_symbol,
            "exit_reasons": exit_reasons,
        }

    # Keep class-level constant for backward compatibility with existing tests.
    MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE = MIN_CALIBRATION_SAMPLES_FOR_ACCEPTANCE

    def _validate_new_model(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
        new_metrics: ModelMetrics,
        old_clf: Any,
    ) -> bool:
        """Walk-forward validation: delegates to the shared acceptance_gate().

        Note: this is the LIVE acceptance gate, used by both the synchronous
        retrain path and the background trainer. walk_forward.py provides a
        richer offline evaluation but is not used for live model promotion.
        """
        # Determine old metrics for comparison
        old_m: ModelMetrics | None = None
        if old_clf and self.state.model_metrics:
            old_m = self.state.model_metrics[-1]

        accepted, _reason = acceptance_gate(
            new_metrics,
            old_metrics=old_m,
            improvement_threshold=self.improvement_threshold,
        )
        return accepted

    def _check_drift(
        self,
        reference: pd.DataFrame,
        current: pd.DataFrame,
    ) -> tuple[bool, float]:
        """PSI-based drift detection on feature distributions."""
        psi_scores = []

        for col in reference.columns:
            if col not in current.columns:
                continue
            ref_vals = reference[col].dropna().values
            cur_vals = current[col].dropna().values
            if len(ref_vals) < 10 or len(cur_vals) < 10:
                continue
            psi = self._compute_psi(ref_vals, cur_vals)
            psi_scores.append(psi)

        if not psi_scores:
            return False, 0.0

        mean_psi = float(np.mean(psi_scores))
        return mean_psi > self.drift_threshold, mean_psi

    @staticmethod
    def _compute_psi(
        reference: np.ndarray, current: np.ndarray, n_bins: int = 10
    ) -> float:
        """Population Stability Index."""
        eps = 1e-6

        # Use reference quantiles as bin edges
        quantiles = np.linspace(0, 100, n_bins + 1)
        bins = np.percentile(reference, quantiles)
        bins[0] = -np.inf
        bins[-1] = np.inf
        # Remove duplicate edges
        bins = np.unique(bins)
        if len(bins) < 3:
            return 0.0

        ref_counts = np.histogram(reference, bins=bins)[0].astype(float)
        cur_counts = np.histogram(current, bins=bins)[0].astype(float)

        ref_pct = ref_counts / (ref_counts.sum() + eps)
        cur_pct = cur_counts / (cur_counts.sum() + eps)

        # Avoid log(0)
        ref_pct = np.clip(ref_pct, eps, None)
        cur_pct = np.clip(cur_pct, eps, None)

        psi = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
        return max(psi, 0.0)

    @staticmethod
    def _aggregate_features(
        features_by_symbol: dict[str, pd.DataFrame],
    ) -> pd.DataFrame | None:
        """Combine latest features across symbols for drift detection."""
        rows = []
        for symbol, df in features_by_symbol.items():
            if len(df) < 1:
                continue
            # Take last row
            row = df.iloc[-1]
            feature_cols = [c for c in FEATURE_COLUMNS if c in df.columns]
            if feature_cols:
                rows.append(row[feature_cols])

        if not rows:
            return None
        return pd.DataFrame(rows)
