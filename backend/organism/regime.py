"""
Phase 6 — Regime-Conditioned Ensemble Blending.

Provides:
1. Multi-model regime detection (trend/chop/volatile/stress)
2. Per-regime weight vectors for strategy blending
3. Regime churn detection + smoothing
4. Drift detection across feature distributions

The regime engine acts as the "perception layer" of the organism:
it observes market state and conditions the policy accordingly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pandas as pd

from backend.utils.logger import get_logger

logger = get_logger(__name__)


# ── Regime definitions ──────────────────────────────────────────────

class RegimeLabel:
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    CHOP = "chop"
    HIGH_VOL = "high_vol"
    LOW_VOL = "low_vol"
    STRESS = "stress"
    UNKNOWN = "unknown"


@dataclass
class RegimeState:
    """Current detected regime with probability vector."""
    primary: str = RegimeLabel.UNKNOWN
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    features_used: dict[str, float] = field(default_factory=dict)
    churn_rate: float = 0.0  # how often regime flips (0 = stable)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "probabilities": {k: round(v, 4) for k, v in self.probabilities.items()},
            "confidence": round(self.confidence, 4),
            "features_used": {k: round(v, 6) for k, v in self.features_used.items()},
            "churn_rate": round(self.churn_rate, 4),
            "timestamp": self.timestamp,
        }


@dataclass
class DriftReport:
    """Feature drift detection report."""
    drifted: bool = False
    feature_scores: dict[str, float] = field(default_factory=dict)
    overall_score: float = 0.0
    threshold: float = 0.10
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "drifted": self.drifted,
            "feature_scores": {k: round(v, 4) for k, v in self.feature_scores.items()},
            "overall_score": round(self.overall_score, 4),
            "threshold": self.threshold,
            "timestamp": self.timestamp,
        }


class RegimeDetector:
    """Multi-signal regime detector.

    Uses simple, robust indicators:
    - Trend: SMA slope direction + ADX-like trend strength
    - Volatility: ATR ratio + realized vol percentile
    - Stress: gap frequency + volume anomalies + correlation breakdown proxy

    Outputs a probability vector over regime labels.
    """

    def __init__(
        self,
        *,
        sma_period: int = 50,
        vol_lookback: int = 20,
        trend_threshold: float = 0.02,
        churn_window: int = 20,
        smoothing_alpha: float = 0.3,
        is_intraday: bool = False,
        bars_per_day: int = 1,
        intraday_trend_sensitivity: float = 1.0,
        now_fn: Any = None,
    ) -> None:
        # V5 U-3 / Wave-17b (2026-05-03): inject a clock so replay
        # sees the replay clock instead of wall clock. `now_fn` returns
        # an aware datetime in UTC. Default is the canonical wall clock
        # for live use; replay supplies a synthetic clock.
        if now_fn is None:
            def _default_now() -> datetime:
                return datetime.now(UTC)
            self._now_fn = _default_now
        else:
            self._now_fn = now_fn
        # Scale lookbacks for intraday bars to reduce noise.
        # 4x makes SMA_200 (~3.3hrs on 1-min) roughly analogous to a
        # multi-day moving average — still responsive but filters noise.
        scale = 4 if is_intraday else 1
        self._sma_period = sma_period * scale
        self._vol_lookback = vol_lookback * scale
        self._churn_window = churn_window * scale
        self._alpha = smoothing_alpha
        self._is_intraday = is_intraday
        self._bars_per_day = bars_per_day
        self._intraday_trend_sensitivity = intraday_trend_sensitivity

        # v4 (improve7): Scale trend threshold for intraday.
        # SMA slope over 10 intraday bars is much smaller than daily —
        # the 0.02 daily threshold effectively prevents trending_up from
        # ever triggering on 1-min bars, keeping the system stuck in chop.
        # Divide by sqrt(bars_per_day) to make thresholds comparable.
        tf_scale = 1.0 / math.sqrt(bars_per_day) if is_intraday else 1.0
        # RC-1.5 shadow: optional intraday_trend_sensitivity multiplier.
        # Default 1.0 preserves baseline behavior. Shadow detector in
        # live_engine instantiates this with 0.50 to log what regime
        # would fire under proposed RC-2 calibration. Empirical 50-run
        # synthetic: factor=0.50 → 28% noise FPR, 78% TPR on mild trend.
        intraday_factor = (
            self._intraday_trend_sensitivity if is_intraday else 1.0
        )
        self._trend_threshold = (
            trend_threshold * tf_scale * intraday_factor
            if is_intraday else trend_threshold
        )

        # Scale vol/atr thresholds for intraday — per-bar returns are
        # sqrt(bars_per_day) times smaller than daily returns.
        self._atr_high_thresh = 0.04 * tf_scale
        self._atr_low_thresh = 0.015 * tf_scale
        self._ret_vol_thresh = 0.03 * tf_scale
        self._pct_above_thresh = (
            0.02 * tf_scale * intraday_factor if is_intraday else 0.02 * tf_scale
        )

        # Running state
        self._history: list[str] = []
        self._smoothed_probs: dict[str, float] = {}
        self._last_state: RegimeState | None = None
        # V8 DD2-3 / Wave-34 (2026-05-03): aggregate-level history for the
        # market / cross-asset regime outputs.  The per-symbol detect()
        # calls inside detect_market_regime save/restore `_history` to
        # avoid cross-contamination, which means the actual emitted
        # market regime never accumulates.  Track it separately here so
        # `churn_rate` reflects the live aggregate sequence.
        self._aggregate_history: list[str] = []
        # V8 DD2-4 / Wave-34 (2026-05-03): hysteresis band on argmax to
        # prevent regime flapping at threshold boundaries.  A new label
        # only wins if it leads the previous primary by `_hysteresis_band`.
        # 0.05 is conservative; lower would flap, higher would lag.
        self._hysteresis_band = 0.05

    @property
    def current_regime(self) -> str:
        """Return the most recently detected primary regime label.

        Returns ``RegimeLabel.UNKNOWN`` if no detections have occurred yet.
        """
        if self._history:
            return self._history[-1]
        return RegimeLabel.UNKNOWN

    def detect(self, features_df: pd.DataFrame) -> RegimeState:
        """Detect current regime from features DataFrame.

        Expects columns: close, sma_50, atr_ratio (or similar).
        """
        # V5 U-3 / Wave-17b (2026-05-03): clock injection.
        now = self._now_fn()

        if features_df.empty or len(features_df) < 10:
            return RegimeState(
                primary=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timestamp=now.isoformat(),
            )

        # Extract signals
        close = features_df["close"].iloc[-1] if "close" in features_df.columns else 0

        # SIG-006 fix: compute raw SMA from close prices directly.
        # The features_df sma_50 column is normalized (sma/close ≈ 1.0)
        # which is correct for ML but wrong for regime price-vs-SMA checks.
        close_series = features_df["close"] if "close" in features_df.columns else pd.Series(dtype=float)
        if len(close_series) >= self._sma_period:
            sma = float(close_series.rolling(self._sma_period, min_periods=1).mean().iloc[-1])
        else:
            sma = float(close_series.mean()) if len(close_series) > 0 else float(close)

        # Trend strength: slope of raw SMA
        trend_slope = 0.0
        if len(close_series) >= 5:
            raw_sma_series = close_series.rolling(self._sma_period, min_periods=1).mean().dropna().tail(10)
            if len(raw_sma_series) >= 2:
                first = float(raw_sma_series.iloc[0])
                last = float(raw_sma_series.iloc[-1])
                if first > 0:
                    trend_slope = (last - first) / first

        # Volatility.
        # V7 DD-2 / Wave-24 (2026-05-03): the previous default
        # `atr_ratio = 0.02` was 10× the intraday `atr_high_thresh`
        # (≈ 0.04 / sqrt(390) ≈ 0.002). Any feature DataFrame missing
        # ATR columns was misclassified as `high_vol`, raising entry
        # gates and changing Kelly's regime_scale. Now: track whether
        # we found a valid ATR; if not, return UNKNOWN regime instead
        # of synthesizing a high-vol value. Callers downstream already
        # handle UNKNOWN gracefully (entries blocked / neutral signal).
        atr_ratio: float | None = None
        for c in ["atr_14", "atr_14_ratio", "ATR_ratio"]:
            if c in features_df.columns:
                val = features_df[c].iloc[-1]
                if not pd.isna(val):
                    atr_ratio = float(val)
                    break  # found a valid value — stop looking
        if atr_ratio is None:
            # No ATR available → refuse to grade volatility regime.
            return RegimeState(
                primary=RegimeLabel.UNKNOWN,
                probabilities={RegimeLabel.UNKNOWN: 1.0},
                confidence=0.0,
                features_used={"reason": "atr_missing"},
                churn_rate=0.0,
                timestamp=self._now_fn().isoformat(),
            )

        # Returns volatility
        returns_vol = 0.0
        if "close" in features_df.columns and len(features_df) >= self._vol_lookback:
            closes = features_df["close"].tail(self._vol_lookback)
            rets = closes.pct_change().dropna()
            if len(rets) > 1:
                returns_vol = float(rets.std())

        # Volume anomaly
        vol_anomaly = 0.0
        if "volume" in features_df.columns and len(features_df) >= 20:
            recent_vol = float(features_df["volume"].tail(5).mean())
            hist_vol = float(features_df["volume"].tail(50).mean())
            if hist_vol > 0:
                vol_anomaly = (recent_vol / hist_vol) - 1.0

        # Build probability vector
        probs = self._compute_probabilities(
            trend_slope=trend_slope,
            atr_ratio=atr_ratio,
            returns_vol=returns_vol,
            vol_anomaly=vol_anomaly,
            close=float(close),
            sma=sma,
        )

        # Smooth probabilities
        self._smooth_probabilities(probs)
        # V8 DD2-4 / Wave-34 (2026-05-03): hysteresis band on argmax.  A
        # one-bar slope flip at `_trend_threshold` previously flapped the
        # primary label even after EMA smoothing.  Stay on the previous
        # primary unless a new label leads it by `_hysteresis_band`.
        new_argmax = max(self._smoothed_probs, key=self._smoothed_probs.get)
        if (
            self._last_state is not None
            and self._last_state.primary != new_argmax
            and self._last_state.primary in self._smoothed_probs
        ):
            last_prob = self._smoothed_probs.get(self._last_state.primary, 0.0)
            new_prob = self._smoothed_probs[new_argmax]
            if new_prob - last_prob < self._hysteresis_band:
                primary = self._last_state.primary
            else:
                primary = new_argmax
        else:
            primary = new_argmax
        confidence = self._smoothed_probs.get(primary, 0.0)

        # Track churn
        self._history.append(primary)
        if len(self._history) > self._churn_window * 2:
            self._history = self._history[-self._churn_window * 2:]

        churn = self._compute_churn()

        state = RegimeState(
            primary=primary,
            probabilities=dict(self._smoothed_probs),
            confidence=confidence,
            features_used={
                "trend_slope": trend_slope,
                "atr_ratio": atr_ratio,
                "returns_vol": returns_vol,
                "vol_anomaly": vol_anomaly,
            },
            churn_rate=churn,
            timestamp=now.isoformat(),
        )

        self._last_state = state
        return state

    def _compute_probabilities(
        self,
        *,
        trend_slope: float,
        atr_ratio: float,
        returns_vol: float,
        vol_anomaly: float,
        close: float,
        sma: float,
    ) -> dict[str, float]:
        """Convert feature signals into a probability vector."""
        scores: dict[str, float] = {
            RegimeLabel.TRENDING_UP: 0.0,
            RegimeLabel.TRENDING_DOWN: 0.0,
            RegimeLabel.CHOP: 0.0,
            RegimeLabel.HIGH_VOL: 0.0,
            RegimeLabel.LOW_VOL: 0.0,
            RegimeLabel.STRESS: 0.0,
        }

        # Trend scoring
        if trend_slope > self._trend_threshold:
            scores[RegimeLabel.TRENDING_UP] += 2.0
        elif trend_slope < -self._trend_threshold:
            scores[RegimeLabel.TRENDING_DOWN] += 2.0
        else:
            scores[RegimeLabel.CHOP] += 1.5

        # Price vs SMA
        if sma > 0:
            pct_above = (close - sma) / sma
            if pct_above > self._pct_above_thresh:
                scores[RegimeLabel.TRENDING_UP] += 1.0
            elif pct_above < -self._pct_above_thresh:
                scores[RegimeLabel.TRENDING_DOWN] += 1.0
            else:
                scores[RegimeLabel.CHOP] += 0.5

        # Volatility scoring
        if atr_ratio > self._atr_high_thresh:
            scores[RegimeLabel.HIGH_VOL] += 2.0
        elif atr_ratio < self._atr_low_thresh:
            scores[RegimeLabel.LOW_VOL] += 1.5
        if returns_vol > self._ret_vol_thresh:
            scores[RegimeLabel.HIGH_VOL] += 1.0

        # Stress scoring
        if vol_anomaly > 0.5 and atr_ratio > self._atr_high_thresh:
            scores[RegimeLabel.STRESS] += 2.0
        elif vol_anomaly > 1.0:
            scores[RegimeLabel.STRESS] += 1.0

        # Normalize to probabilities (softmax with log-sum-exp stability)
        max_s = max(scores.values()) if scores else 0
        total = sum(math.exp(s - max_s) for s in scores.values())
        if total > 0:
            probs = {k: math.exp(v - max_s) / total for k, v in scores.items()}
        else:
            n = len(scores)
            probs = {k: 1.0 / n for k in scores}

        return probs

    def _smooth_probabilities(self, new_probs: dict[str, float]) -> None:
        """EMA smoothing to avoid regime whipsaw."""
        if not self._smoothed_probs:
            self._smoothed_probs = dict(new_probs)
            return

        for k in new_probs:
            old = self._smoothed_probs.get(k, new_probs[k])
            self._smoothed_probs[k] = (1 - self._alpha) * old + self._alpha * new_probs[k]

        # Re-normalize
        total = sum(self._smoothed_probs.values())
        if total > 0:
            self._smoothed_probs = {k: v / total for k, v in self._smoothed_probs.items()}

    def _compute_churn(self) -> float:
        """Fraction of regime changes in the recent history window."""
        window = self._history[-self._churn_window:]
        if len(window) < 2:
            return 0.0
        changes = sum(1 for i in range(1, len(window)) if window[i] != window[i - 1])
        return changes / (len(window) - 1)

    # ── persistence (Phase 1.3) ──────────────────────────────────

    def to_persistence_dict(self) -> dict[str, Any]:
        """Serialize regime detector running state for brain persistence."""
        return {
            "history": list(self._history),
            "smoothed_probs": dict(self._smoothed_probs),
            "sma_period": self._sma_period,
            "vol_lookback": self._vol_lookback,
            "trend_threshold": self._trend_threshold,
            "churn_window": self._churn_window,
            "smoothing_alpha": self._alpha,
        }

    def from_persistence_dict(self, data: dict[str, Any]) -> None:
        """Restore regime detector state from brain persistence."""
        self._history = data.get("history", [])
        self._smoothed_probs = data.get("smoothed_probs", {})
        # Restore all tuning params that were persisted
        if "sma_period" in data:
            self._sma_period = data["sma_period"]
        if "vol_lookback" in data:
            self._vol_lookback = data["vol_lookback"]
        if "trend_threshold" in data:
            self._trend_threshold = data["trend_threshold"]
        if "churn_window" in data:
            self._churn_window = data["churn_window"]
        if "smoothing_alpha" in data:
            self._alpha = data["smoothing_alpha"]
        logger.info(
            "Regime detector state restored: %d history entries",
            len(self._history),
        )

    # ------------------------------------------------------------------
    # P&L-027: Market-level regime detection
    # ------------------------------------------------------------------
    def detect_market_regime(
        self,
        per_symbol_features: dict[str, pd.DataFrame],
    ) -> RegimeState:
        """Aggregate per-symbol regimes into a single market-level regime.

        This prevents a single outlier symbol from driving the entire
        portfolio's regime classification.  The market regime is the
        probability-weighted average of individual symbol regimes.
        """
        if not per_symbol_features:
            return RegimeState(
                primary=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timestamp=self._now_fn().isoformat(),
            )

        agg_probs: dict[str, float] = {}
        n = 0
        # Save instance state — detect() mutates _smoothed_probs, _history, _last_state
        saved_probs = dict(self._smoothed_probs)
        saved_history = list(self._history)
        saved_last = self._last_state
        try:
            for sym, feat_df in per_symbol_features.items():
                # Restore pristine state before each detect to prevent cross-contamination
                self._smoothed_probs = dict(saved_probs)
                self._history = list(saved_history)
                state = self.detect(feat_df)
                if state.probabilities:
                    for label, prob in state.probabilities.items():
                        agg_probs[label] = agg_probs.get(label, 0.0) + prob
                    n += 1
        finally:
            self._smoothed_probs = saved_probs
            self._history = saved_history
            self._last_state = saved_last

        if n == 0:
            return RegimeState(
                primary=RegimeLabel.UNKNOWN,
                confidence=0.0,
                timestamp=self._now_fn().isoformat(),
            )

        # Average across symbols
        agg_probs = {k: v / n for k, v in agg_probs.items()}
        primary = max(agg_probs, key=agg_probs.get)  # type: ignore[arg-type]
        # V8 DD2-3 / Wave-34 (2026-05-03): accumulate the aggregate primary
        # in `_aggregate_history` so churn_rate reflects the actually-emitted
        # market regime.  Per-symbol detect()s save/restore `_history`, so
        # without a separate accumulator the market churn was hard-zeroed.
        self._aggregate_history.append(primary)
        if len(self._aggregate_history) > self._churn_window * 2:
            self._aggregate_history = self._aggregate_history[-self._churn_window * 2:]
        churn = self._compute_aggregate_churn()
        state = RegimeState(
            primary=primary,
            probabilities=agg_probs,
            confidence=agg_probs.get(primary, 0.0),
            features_used={"symbols_aggregated": n},
            churn_rate=churn,
            timestamp=self._now_fn().isoformat(),
        )
        self._last_state = state
        return state

    def _compute_aggregate_churn(self) -> float:
        """V8 DD2-3 / Wave-34: churn over the aggregate-history window."""
        if len(self._aggregate_history) < 2:
            return 0.0
        window = self._aggregate_history[-self._churn_window:]
        if len(window) < 2:
            return 0.0
        transitions = sum(
            1 for a, b in zip(window, window[1:]) if a != b
        )
        return transitions / (len(window) - 1)

    # ------------------------------------------------------------------
    # Phase 4.3: Cross-asset regime conditioning
    # ------------------------------------------------------------------

    # Sector ETFs used for cross-asset analysis
    SECTOR_ETFS = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLU", "XLP", "XLY", "XLB", "XLRE"]

    def detect_cross_asset_regime(
        self,
        per_symbol_features: dict[str, pd.DataFrame],
        sector_features: dict[str, pd.DataFrame] | None = None,
    ) -> RegimeState:
        """Enhanced market regime detection using sector ETF conditioning.

        Parameters
        ----------
        per_symbol_features : {symbol → features_df} for active universe
        sector_features : {etf_symbol → features_df} for sector ETFs.
                          If None, falls back to detect_market_regime().

        Returns
        -------
        RegimeState with cross-asset-conditioned probability vector.

        The conditioning logic:
        - Compute per-sector regime states from sector ETF data.
        - Build a *breadth* score: fraction of sectors in trending_up.
        - Build a *stress* score: fraction of sectors in stress/high_vol.
        - Blend the breadth/stress conditioning into the market regime.
        """
        # Base market-level regime
        base = self.detect_market_regime(per_symbol_features)

        if not sector_features:
            return base

        # Compute per-sector regime (save/restore state before each detect)
        sector_regimes: list[RegimeState] = []
        saved_probs = dict(self._smoothed_probs) if self._smoothed_probs is not None else {}
        saved_history = list(self._history)
        saved_last = self._last_state
        for etf, feat_df in sector_features.items():
            if feat_df is not None and len(feat_df) >= 10:
                # Restore pristine state before each detect to prevent cross-contamination
                self._smoothed_probs = dict(saved_probs)
                self._history = list(saved_history)
                sr = self.detect(feat_df)
                sector_regimes.append(sr)
        self._smoothed_probs = saved_probs
        self._history = saved_history
        self._last_state = saved_last

        if not sector_regimes:
            return base

        # Breadth: fraction of sectors trending up
        n_sectors = len(sector_regimes)
        n_up = sum(1 for s in sector_regimes if s.primary == RegimeLabel.TRENDING_UP)
        n_down = sum(1 for s in sector_regimes if s.primary == RegimeLabel.TRENDING_DOWN)
        n_stress = sum(
            1 for s in sector_regimes
            if s.primary in (RegimeLabel.STRESS, RegimeLabel.HIGH_VOL)
        )

        breadth_up = n_up / n_sectors
        breadth_down = n_down / n_sectors
        stress_pct = n_stress / n_sectors

        # Condition the base probabilities
        conditioned = dict(base.probabilities)

        # If broad sector strength → boost trending_up, reduce stress
        if breadth_up > 0.5:
            conditioned[RegimeLabel.TRENDING_UP] = conditioned.get(
                RegimeLabel.TRENDING_UP, 0
            ) * (1 + 0.3 * breadth_up)
            conditioned[RegimeLabel.STRESS] = conditioned.get(
                RegimeLabel.STRESS, 0
            ) * 0.7

        # If broad sector weakness → boost trending_down
        if breadth_down > 0.5:
            conditioned[RegimeLabel.TRENDING_DOWN] = conditioned.get(
                RegimeLabel.TRENDING_DOWN, 0
            ) * (1 + 0.3 * breadth_down)
            conditioned[RegimeLabel.TRENDING_UP] = conditioned.get(
                RegimeLabel.TRENDING_UP, 0
            ) * 0.7

        # Stress conditioning
        if stress_pct > 0.4:
            conditioned[RegimeLabel.STRESS] = conditioned.get(
                RegimeLabel.STRESS, 0
            ) * (1 + 0.5 * stress_pct)

        # Re-normalise
        total = sum(conditioned.values())
        if total > 0:
            conditioned = {k: v / total for k, v in conditioned.items()}

        primary = max(conditioned, key=conditioned.get)  # type: ignore[arg-type]

        # V8 DD2-3 / Wave-34 (2026-05-03): if the cross-asset conditioning
        # changed the primary vs the unconditioned market regime, replace
        # the last aggregate-history entry so churn reflects the truly-
        # emitted regime (not the unconditioned one appended by
        # detect_market_regime).
        if self._aggregate_history and primary != self._aggregate_history[-1]:
            self._aggregate_history[-1] = primary
        churn = self._compute_aggregate_churn()
        state = RegimeState(
            primary=primary,
            probabilities=conditioned,
            confidence=conditioned.get(primary, 0.0),
            features_used={
                "symbols_aggregated": base.features_used.get("symbols_aggregated", 0),
                "sectors_analysed": n_sectors,
                "breadth_up": round(breadth_up, 3),
                "breadth_down": round(breadth_down, 3),
                "stress_pct": round(stress_pct, 3),
            },
            churn_rate=churn,
            timestamp=self._now_fn().isoformat(),
        )
        self._last_state = state
        return state


class DriftDetector:
    """Detect feature distribution drift between reference and current windows.

    Uses a simple Population Stability Index (PSI) approximation.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.10,
        n_bins: int = 10,
        now_fn: Any = None,
    ) -> None:
        self._threshold = threshold
        self._n_bins = n_bins
        # V6 Z3 obs / Wave-22 (2026-05-03): clock injection so the drift
        # report's metadata timestamp respects replay's clock. Default
        # is wall clock for live use.
        if now_fn is None:
            self._now_fn = lambda: datetime.now(UTC)
        else:
            self._now_fn = now_fn

    def check_drift(
        self,
        reference_df: pd.DataFrame,
        current_df: pd.DataFrame,
    ) -> DriftReport:
        """Compare feature distributions between reference and current."""
        now = self._now_fn()
        feature_scores: dict[str, float] = {}

        numeric_cols = set(reference_df.select_dtypes(include=[np.number]).columns) & \
                       set(current_df.select_dtypes(include=[np.number]).columns)

        for col in sorted(numeric_cols):
            ref = reference_df[col].dropna()
            cur = current_df[col].dropna()
            if len(ref) < 10 or len(cur) < 10:
                continue

            psi = self._compute_psi(ref.values, cur.values)
            feature_scores[col] = psi

        overall = float(np.mean(list(feature_scores.values()))) if feature_scores else 0.0
        drifted = overall > self._threshold

        return DriftReport(
            drifted=drifted,
            feature_scores=feature_scores,
            overall_score=overall,
            threshold=self._threshold,
            timestamp=now.isoformat(),
        )

    def _compute_psi(self, ref: np.ndarray, cur: np.ndarray) -> float:
        """Population Stability Index between two distributions."""
        try:
            # Create bins from reference
            min_val = min(ref.min(), cur.min())
            max_val = max(ref.max(), cur.max())
            if min_val == max_val:
                return 0.0

            bins = np.linspace(min_val, max_val, self._n_bins + 1)
            ref_hist, _ = np.histogram(ref, bins=bins)
            cur_hist, _ = np.histogram(cur, bins=bins)

            # Avoid division by zero
            eps = 1e-6
            ref_pct = (ref_hist + eps) / (ref_hist.sum() + eps * len(ref_hist))
            cur_pct = (cur_hist + eps) / (cur_hist.sum() + eps * len(cur_hist))

            psi = float(np.sum((cur_pct - ref_pct) * np.log(cur_pct / ref_pct)))
            return max(0.0, psi)
        except Exception:
            return 0.0


class RegimeConditionedEnsemble:
    """Apply regime-specific weight vectors to strategy blending.

    Given the current regime state, selects or interpolates between
    per-regime weight vectors to produce final strategy weights.
    """

    # Default per-regime strategy preferences
    DEFAULT_REGIME_WEIGHTS: dict[str, dict[str, float]] = {
        RegimeLabel.TRENDING_UP: {
            "momentum": 1.4, "regime_momentum": 1.5, "breakout": 1.3,
            "mean_reversion": 0.7, "stat_arb": 0.8,
        },
        RegimeLabel.TRENDING_DOWN: {
            "momentum": 1.3, "regime_momentum": 1.4, "breakout": 0.9,
            "mean_reversion": 0.8, "stat_arb": 0.9,
        },
        RegimeLabel.CHOP: {
            "momentum": 0.7, "mean_reversion": 1.4, "stat_arb": 1.3,
            "regime_momentum": 0.8, "breakout": 0.6,
        },
        RegimeLabel.HIGH_VOL: {
            "momentum": 0.9, "mean_reversion": 1.1, "stat_arb": 1.0,
            "regime_momentum": 1.0, "breakout": 0.8,
        },
        RegimeLabel.LOW_VOL: {
            "momentum": 1.1, "mean_reversion": 1.2, "stat_arb": 1.1,
            "regime_momentum": 1.0, "breakout": 1.2,
        },
        RegimeLabel.STRESS: {
            "momentum": 0.5, "mean_reversion": 0.6, "stat_arb": 0.5,
            "regime_momentum": 0.5, "breakout": 0.3,
        },
    }

    def __init__(
        self,
        regime_weights: dict[str, dict[str, float]] | None = None,
    ) -> None:
        self._regime_weights = regime_weights or dict(self.DEFAULT_REGIME_WEIGHTS)

    def blend(
        self,
        regime_state: RegimeState,
        base_weights: dict[str, float],
    ) -> dict[str, float]:
        """Produce final blended weights from regime probabilities.

        Uses probability-weighted interpolation across all regime weight vectors.
        """
        all_sources = set(base_weights.keys())
        for rw in self._regime_weights.values():
            all_sources |= set(rw.keys())

        blended: dict[str, float] = {s: 0.0 for s in all_sources}

        if not regime_state.probabilities:
            return dict(base_weights)

        # Probability-weighted blend
        for regime, prob in regime_state.probabilities.items():
            rw = self._regime_weights.get(regime, {})
            for src in all_sources:
                regime_w = rw.get(src, 1.0)
                base_w = base_weights.get(src, 0.0)  # default 0 for unknown sources
                blended[src] += prob * base_w * regime_w

        # Clamp
        blended = {k: max(0.10, min(2.50, v)) for k, v in blended.items()}

        return blended
