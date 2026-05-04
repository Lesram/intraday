"""
Module 3 — Alpha Scanner.

Scans the universe for the highest-conviction trading candidates.
Combines ML prediction, technical breakout, volume, relative strength,
and regime alignment into a composite alpha score.

Ref: docs/blueprints/SELF_LEARNING_ORGANISM_BLUEPRINT.md §3.3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backend.organism.ml_signal import MLSignal
from backend.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class AlphaCandidate:
    """A symbol scored for trading potential."""
    symbol: str
    composite_score: float  # [0, 1] — total alpha potential
    ml_score: float = 0.0
    breakout_score: float = 0.0
    volume_score: float = 0.0
    momentum_score: float = 0.0
    regime_score: float = 0.0
    institutional_score: float = 0.0
    momentum_quality_score: float = 0.0
    ml_signal: MLSignal | None = None
    direction: float = 0.0  # +1 buy, -1 sell
    expected_return_source: str = "heuristic"  # "ml", "calibrated_breakout", "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "composite": round(self.composite_score, 4),
            "ml": round(self.ml_score, 4),
            "breakout": round(self.breakout_score, 4),
            "volume": round(self.volume_score, 4),
            "momentum": round(self.momentum_score, 4),
            "regime": round(self.regime_score, 4),
            "institutional": round(self.institutional_score, 4),
            "momentum_quality": round(self.momentum_quality_score, 4),
            "direction": self.direction,
            "expected_return_source": self.expected_return_source,
        }


class AlphaScanner:
    """Scan universe for highest-conviction trades.

    Enhanced scoring system using composite indicators:
        1. ML prediction confidence × direction accuracy  (25%)
        2. Composite breakout readiness + squeeze         (20%)
        3. Institutional accumulation flow                (15%)
        4. Price momentum (cross-sectional rank)          (15%)
        5. Momentum quality (sustainable vs fading)       (10%)
        6. Volume-price divergence                        (10%)
        7. Regime alignment bonus                          (5%)
    """

    WEIGHT_ML = 0.25
    WEIGHT_BREAKOUT = 0.20
    WEIGHT_INSTITUTIONAL = 0.15
    WEIGHT_MOMENTUM = 0.15
    WEIGHT_MOM_QUALITY = 0.10
    WEIGHT_VOLUME = 0.10
    WEIGHT_REGIME = 0.05

    MIN_COMPOSITE = 0.15  # HFT: lower gate = more intraday candidates (was 0.25)

    # improve9 B4: Inverse ETFs — long-only bearish participation.
    # Buying these is economically equivalent to being short the index.
    INVERSE_ETFS = {"SH", "PSQ", "DOG", "RWM"}

    def __init__(self, top_n: int = 5):
        self.top_n = top_n
        self._hit_count = 0
        self._scan_count = 0

    @property
    def hit_rate(self) -> float:
        return self._hit_count / max(self._scan_count, 1)

    def scan(
        self,
        features_by_symbol: dict[str, pd.DataFrame],
        ml_signals: dict[str, MLSignal],
        current_regime: str = "unknown",
        ml_is_trained: bool = True,
        learning_mode: bool = False,
    ) -> list[AlphaCandidate]:
        """Score all symbols, return top-N candidates sorted by alpha.

        Parameters
        ----------
        features_by_symbol : {symbol: DataFrame with features}
        ml_signals : {symbol: MLSignal from MLSignalGenerator}
        current_regime : regime label from RegimeDetector
        ml_is_trained : whether the ML model has been trained
        learning_mode : whether the organism is in learning mode

        Returns
        -------
        List of top-N AlphaCandidates, sorted by composite_score descending.
        """
        candidates: list[AlphaCandidate] = []
        self._scan_count += 1

        # Hardening: zero ML weight when in learning mode OR when the
        # model is untrained. The previous check on ml_is_trained alone
        # allowed ML influence after retraining while still in learning
        # mode (< 200 trades), which is anti-predictive.
        if learning_mode or not ml_is_trained:
            effective_ml_weight = 0.0
            effective_breakout_weight = 0.40
            effective_momentum_weight = 0.20
        else:
            # Dynamic ML weight: reduce when ML model has low confidence
            avg_ml_conf = 0.0
            if ml_signals:
                confs = [s.confidence for s in ml_signals.values() if s.confidence > 0]
                avg_ml_conf = sum(confs) / len(confs) if confs else 0.0

            if avg_ml_conf < 0.10:
                effective_ml_weight = 0.05
                ml_excess = self.WEIGHT_ML - 0.05
                effective_breakout_weight = self.WEIGHT_BREAKOUT + ml_excess * 0.6
                effective_momentum_weight = self.WEIGHT_MOMENTUM + ml_excess * 0.4
            else:
                effective_ml_weight = self.WEIGHT_ML
                effective_breakout_weight = self.WEIGHT_BREAKOUT
                effective_momentum_weight = self.WEIGHT_MOMENTUM

        # Pre-compute cross-sectional momentum rank
        mom_ranks = self._rank_momentum(features_by_symbol)

        for symbol, df in features_by_symbol.items():
            if len(df) < 50:
                continue

            row = df.iloc[-1]
            ml_sig = ml_signals.get(symbol)

            # 1. ML score — use effective_confidence (B2 improve8)
            ml_score = 0.0
            direction = 0.0
            if ml_sig and ml_sig.direction != 0:
                _eff_conf = ml_sig.effective_confidence if ml_sig.effective_confidence > 0 else ml_sig.confidence
                ml_score = _eff_conf * abs(ml_sig.predicted_return) * 20  # Scale up
                ml_score = min(ml_score, 1.0)
                if not learning_mode:
                    direction = ml_sig.direction

            # 2. Breakout readiness (composite: squeeze + coil + resistance proximity)
            breakout_readiness = float(row.get("comp_breakout_readiness", 0.0))
            squeeze_momentum = float(row.get("comp_squeeze_momentum", 0.0))
            breakout_score = breakout_readiness * 0.6 + squeeze_momentum * 0.4

            # 3. Institutional accumulation
            inst_score = float(row.get("comp_institutional_acc", 0.5))

            # 4. Momentum score (cross-sectional rank)
            momentum_score = mom_ranks.get(symbol, 0.5)

            # 5. Momentum quality (sustainable vs fading)
            mom_quality = float(row.get("comp_momentum_quality", 0.5))

            # 6. Volume-price divergence (smart money detection)
            vol_div = float(row.get("comp_vol_price_div", 0.5))
            # Also use raw volume ratio
            vol_ratio = float(row.get("vol_sma_ratio", 1.0))
            volume_score = min(max(vol_ratio - 1.0, 0.0) / 2.0, 1.0) * 0.5 + vol_div * 0.5

            # 7. Regime alignment score
            regime_score = self._regime_alignment(row, direction, current_regime, symbol)

            # NaN guard: sanitize every factor before composing.
            # A single NaN from missing data would silently produce a NaN
            # composite, creating "silent non-trading" or unstable candidates.
            for _name, _val in [
                ("ml_score", ml_score), ("breakout_score", breakout_score),
                ("inst_score", inst_score), ("momentum_score", momentum_score),
                ("mom_quality", mom_quality), ("volume_score", volume_score),
                ("regime_score", regime_score),
            ]:
                if not np.isfinite(_val):
                    logger.warning("NaN/Inf in alpha factor %s for %s — zeroed", _name, symbol)
            ml_score = ml_score if np.isfinite(ml_score) else 0.0
            breakout_score = breakout_score if np.isfinite(breakout_score) else 0.0
            inst_score = inst_score if np.isfinite(inst_score) else 0.5
            momentum_score = momentum_score if np.isfinite(momentum_score) else 0.5
            mom_quality = mom_quality if np.isfinite(mom_quality) else 0.5
            volume_score = volume_score if np.isfinite(volume_score) else 0.0
            regime_score = regime_score if np.isfinite(regime_score) else 0.5

            # Composite (uses effective weights for ML/breakout/momentum)
            composite = (
                effective_ml_weight * ml_score
                + effective_breakout_weight * breakout_score
                + self.WEIGHT_INSTITUTIONAL * inst_score
                + effective_momentum_weight * momentum_score
                + self.WEIGHT_MOM_QUALITY * mom_quality
                + self.WEIGHT_VOLUME * volume_score
                + self.WEIGHT_REGIME * regime_score
            )

            # If ML says hold, penalize — but less when ML is isolated or
            # untrained.  Phase 2 guarded-production mode reuses
            # learning_mode to mean "ML must not influence the main book";
            # in that state direction is derived from observable
            # momentum/breakout, not the model's direction output.
            if direction == 0:
                if learning_mode or not ml_is_trained:
                    # Derive direction from momentum/breakout when ML is untrained
                    ret_5d = float(row.get("ret_5d", 0.0))
                    _bo_readiness = float(row.get("comp_breakout_readiness", 0.0))
                    if ret_5d > 0.005 or _bo_readiness > 0.6:
                        direction = 1.0
                    elif ret_5d < -0.005:
                        direction = -1.0
                    composite *= 0.7  # Mild penalty (was 0.3x)
                else:
                    composite *= 0.3

            # Symbol fitness: evolved from historical performance
            # (set by EvolutionEngine via apply_evolved_params)
            # improve9 B1: Narrower range — fitness is a soft ranking
            # multiplier, not a dramatic swing. Session bans in live_engine
            # handle hard protection.
            if hasattr(self, "_symbol_fitness") and self._symbol_fitness:
                fitness = self._symbol_fitness.get(symbol, 0.5)
                # Scale: 0.5 = neutral (1.0x), 0.1 = 0.88x, 0.95 = 1.09x
                # Old range was [0.6, 1.45] — too wide for bootstrap data
                composite *= 0.8 + fitness * 0.4  # range [0.84, 1.18]

            # improve9 B3: Stocks in Play overlay — boost names with
            # abnormal relative volume and/or notable gap. Literature shows
            # short-horizon intraday alpha concentrates in "stocks in play."
            _in_play_boost = self._stocks_in_play_score(row)
            composite *= _in_play_boost  # range [1.0, 1.25]

            # Cap composite to [0, 1] after fitness + in-play scaling
            composite = min(composite, 1.0)

            # Final NaN guard on composite — drop the symbol entirely if NaN.
            if not np.isfinite(composite):
                logger.warning("NaN/Inf composite for %s — skipping candidate", symbol)
                continue

            # B1 (improve8): Determine expected_return_source
            # "ml" if trained model produced a real signal
            # "calibrated_breakout" if breakout + ML confirms direction
            # "heuristic" if no ML or synthetic floor
            _exp_ret_source = "heuristic"
            if (
                not learning_mode
                and ml_is_trained
                and ml_sig
                and ml_sig.direction != 0
                and abs(ml_sig.predicted_return) > 1e-6
            ):
                _exp_ret_source = "ml"
            elif (
                not learning_mode
                and breakout_score >= 0.4
                and ml_is_trained
                and ml_sig
                and ml_sig.direction != 0
            ):
                _exp_ret_source = "calibrated_breakout"
            candidate_ml_signal = None if learning_mode else ml_sig

            candidates.append(AlphaCandidate(
                symbol=symbol,
                composite_score=composite,
                ml_score=ml_score,
                breakout_score=breakout_score,
                volume_score=volume_score,
                momentum_score=momentum_score,
                regime_score=regime_score,
                institutional_score=inst_score,
                momentum_quality_score=mom_quality,
                ml_signal=candidate_ml_signal,
                direction=direction,
                expected_return_source=_exp_ret_source,
            ))

        # Sort by composite score, take top N
        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        self._last_full_scan = list(candidates)

        # Regime-gated threshold: raise the bar in defensive regimes so
        # only truly exceptional signals pass during high_vol/stress.
        min_threshold = self.MIN_COMPOSITE  # 0.15 default
        if current_regime in ("high_vol", "stress"):
            min_threshold = 0.25 if current_regime == "high_vol" else 0.50

        result = [c for c in candidates[:self.top_n] if c.composite_score >= min_threshold]

        if result:
            self._hit_count += 1

        return result

    def _rank_momentum(
        self, features_by_symbol: dict[str, pd.DataFrame]
    ) -> dict[str, float]:
        """Cross-sectional momentum rank [0,1] where 1 = strongest."""
        mom_values: dict[str, float] = {}
        for symbol, df in features_by_symbol.items():
            if len(df) < 20:
                continue
            ret_20 = float(df.iloc[-1].get("ret_20d", 0.0))
            # NaN from missing data would corrupt the ranking — replace
            # with 0.0 so the symbol sorts neutrally rather than last.
            if not np.isfinite(ret_20):
                ret_20 = 0.0
            mom_values[symbol] = ret_20

        if not mom_values:
            return {}

        # Rank
        sorted_syms = sorted(mom_values.keys(), key=lambda s: mom_values[s])
        n = len(sorted_syms)
        return {sym: (i / max(n - 1, 1)) for i, sym in enumerate(sorted_syms)}

    def _regime_alignment(
        self, row: pd.Series, direction: float, regime: str,
        symbol: str = "",
    ) -> float:
        """Score how well the signal aligns with the current regime.

        improve9 B4: Inverse ETFs (SH, PSQ) get inverted regime logic —
        buying them in trending_down is aligned, not counter-trend.
        """
        trend_str = float(row.get("trend_strength", 0.2))

        # B4: For inverse ETFs, flip the regime interpretation.
        # Buying SH in trending_down is economically = shorting S&P = aligned.
        _is_inverse = symbol in self.INVERSE_ETFS
        _effective_regime = regime
        if _is_inverse:
            if regime == "trending_down":
                _effective_regime = "trending_up"
            elif regime == "trending_up":
                _effective_regime = "trending_down"

        score = 0.5  # Neutral

        if _effective_regime == "trending_up" and direction > 0:
            score = 0.7 + trend_str * 0.3  # Strong trend + buy = aligned
        elif _effective_regime == "trending_down" and direction < 0:
            score = 0.7 + trend_str * 0.3
        elif _effective_regime == "trending_down" and direction > 0:
            score = 0.3  # Counter-trend penalty: buying in a downtrend
        elif _effective_regime == "low_vol":
            score = 0.7  # Calm market — favorable for entries
        elif _effective_regime == "chop" and abs(direction) > 0:
            # Mean reversion in chop is good
            z_score = float(row.get("z_score_20", 0))
            if (z_score < -1.5 and direction > 0) or (z_score > 1.5 and direction < 0):
                score = 0.8
            else:
                score = 0.3  # Chop + momentum = bad
        elif _effective_regime == "high_vol":
            score = 0.5  # Neutral — high_vol still tradeable, not stress
        elif _effective_regime == "stress":
            score = 0.2  # Reduce in stress

        return min(max(score, 0.0), 1.0)

    @staticmethod
    def _stocks_in_play_score(row: pd.Series) -> float:
        """Compute a Stocks-in-Play boost from relative volume and gap.

        improve9 B3: Literature shows short-horizon intraday alpha
        concentrates in names with abnormal activity. We use two
        features already computed in ml_features:
        - vol_sma_ratio: current volume / 20-bar SMA volume
        - gap_pct: (open - prev_close) / prev_close

        Returns a multiplicative boost in [1.0, 1.25]:
        - 1.0 = normal stock, no boost
        - 1.25 = highly in-play (2x+ relative volume AND 1%+ gap)
        """
        rvol = float(row.get("vol_sma_ratio", 1.0))
        gap = abs(float(row.get("gap_pct", 0.0)))

        if not np.isfinite(rvol):
            rvol = 1.0
        if not np.isfinite(gap):
            gap = 0.0

        # Relative volume score: 1.5x = starts boosting, 3x = max
        # Linear ramp: (rvol - 1.5) / 1.5, clamped [0, 1]
        rvol_score = max(0.0, min((rvol - 1.5) / 1.5, 1.0))

        # Gap score: 0.5% = starts boosting, 2% = max
        # Linear ramp: (gap - 0.005) / 0.015, clamped [0, 1]
        gap_score = max(0.0, min((gap - 0.005) / 0.015, 1.0))

        # Combined: average of both signals, scaled to [1.0, 1.25]
        in_play = (rvol_score * 0.6 + gap_score * 0.4)
        return 1.0 + in_play * 0.25
