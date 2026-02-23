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
        current_regime: str = "normal",
    ) -> list[AlphaCandidate]:
        """Score all symbols, return top-N candidates sorted by alpha.

        Parameters
        ----------
        features_by_symbol : {symbol: DataFrame with features}
        ml_signals : {symbol: MLSignal from MLSignalGenerator}
        current_regime : regime label from RegimeDetector

        Returns
        -------
        List of top-N AlphaCandidates, sorted by composite_score descending.
        """
        candidates: list[AlphaCandidate] = []
        self._scan_count += 1

        # Pre-compute cross-sectional momentum rank
        mom_ranks = self._rank_momentum(features_by_symbol)

        for symbol, df in features_by_symbol.items():
            if len(df) < 50:
                continue

            row = df.iloc[-1]
            ml_sig = ml_signals.get(symbol)

            # 1. ML score
            ml_score = 0.0
            direction = 0.0
            if ml_sig and ml_sig.direction != 0:
                ml_score = ml_sig.confidence * abs(ml_sig.predicted_return) * 20  # Scale up
                ml_score = min(ml_score, 1.0)
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
            regime_score = self._regime_alignment(row, direction, current_regime)

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

            # Composite
            composite = (
                self.WEIGHT_ML * ml_score
                + self.WEIGHT_BREAKOUT * breakout_score
                + self.WEIGHT_INSTITUTIONAL * inst_score
                + self.WEIGHT_MOMENTUM * momentum_score
                + self.WEIGHT_MOM_QUALITY * mom_quality
                + self.WEIGHT_VOLUME * volume_score
                + self.WEIGHT_REGIME * regime_score
            )

            # If ML says hold, penalize heavily
            if direction == 0:
                composite *= 0.3

            # Symbol fitness: evolved from historical performance
            # (set by EvolutionEngine via apply_evolved_params)
            if hasattr(self, "_symbol_fitness") and self._symbol_fitness:
                fitness = self._symbol_fitness.get(symbol, 0.5)
                # Scale: 0.5 = neutral, >0.5 = boost, <0.5 = penalize
                composite *= 0.5 + fitness  # range [0.6, 1.45]

            # Cap composite to [0, 1] after fitness scaling
            composite = min(composite, 1.0)

            # Final NaN guard on composite — drop the symbol entirely if NaN.
            if not np.isfinite(composite):
                logger.warning("NaN/Inf composite for %s — skipping candidate", symbol)
                continue

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
                ml_signal=ml_sig,
                direction=direction,
            ))

        # Sort by composite score, take top N
        candidates.sort(key=lambda c: c.composite_score, reverse=True)
        self._last_full_scan = list(candidates)
        result = [c for c in candidates[:self.top_n] if c.composite_score >= self.MIN_COMPOSITE]

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
        self, row: pd.Series, direction: float, regime: str
    ) -> float:
        """Score how well the signal aligns with the current regime."""
        adx = float(row.get("adx_14", 20))
        trend_str = float(row.get("trend_strength", 0.2))
        vol_regime = int(row.get("vol_regime", 1))

        score = 0.5  # Neutral

        if regime in ("trending_up", "trending") and direction > 0:
            score = 0.7 + trend_str * 0.3  # Strong trend + buy = aligned
        elif regime in ("trending_down",) and direction < 0:
            score = 0.7 + trend_str * 0.3
        elif regime == "chop" and abs(direction) > 0:
            # Mean reversion in chop is good
            z_score = float(row.get("z_score_20", 0))
            if (z_score < -1.5 and direction > 0) or (z_score > 1.5 and direction < 0):
                score = 0.8
            else:
                score = 0.3  # Chop + momentum = bad
        elif regime in ("high_vol", "stress"):
            score = 0.2  # Reduce in high vol

        return min(max(score, 0.0), 1.0)
