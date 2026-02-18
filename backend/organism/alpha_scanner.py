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
            "direction": self.direction,
        }


class AlphaScanner:
    """Scan universe for highest-conviction trades.

    Scoring system (each [0,1], then weighted sum):
        1. ML prediction confidence × direction accuracy  (35%)
        2. Volume breakout strength                       (20%)
        3. Price momentum (cross-sectional rank)          (20%)
        4. Bollinger squeeze expansion probability        (15%)
        5. Regime alignment bonus                         (10%)
    """

    WEIGHT_ML = 0.35
    WEIGHT_VOLUME = 0.20
    WEIGHT_MOMENTUM = 0.20
    WEIGHT_BREAKOUT = 0.15
    WEIGHT_REGIME = 0.10

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

            # 2. Volume breakout score
            vol_ratio = float(row.get("vol_sma_ratio", 1.0))
            volume_score = min(max(vol_ratio - 1.0, 0.0) / 2.0, 1.0)

            # 3. Momentum score (cross-sectional rank)
            momentum_score = mom_ranks.get(symbol, 0.5)

            # 4. Breakout score (squeeze expansion)
            bb_sq = float(row.get("bb_squeeze", 0.5))
            vol_exp = float(row.get("vol_expansion", 0.0))
            # Low squeeze percentile + positive vol expansion = breakout imminent
            breakout_score = (1.0 - bb_sq) * 0.6 + min(max(vol_exp, 0), 1.0) * 0.4

            # 5. Regime alignment score
            regime_score = self._regime_alignment(row, direction, current_regime)

            # Composite
            composite = (
                self.WEIGHT_ML * ml_score
                + self.WEIGHT_VOLUME * volume_score
                + self.WEIGHT_MOMENTUM * momentum_score
                + self.WEIGHT_BREAKOUT * breakout_score
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

            candidates.append(AlphaCandidate(
                symbol=symbol,
                composite_score=composite,
                ml_score=ml_score,
                breakout_score=breakout_score,
                volume_score=volume_score,
                momentum_score=momentum_score,
                regime_score=regime_score,
                ml_signal=ml_sig,
                direction=direction,
            ))

        # Sort by composite score, take top N
        candidates.sort(key=lambda c: c.composite_score, reverse=True)
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
