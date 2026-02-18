"""
Module 4 — Kelly Position Sizer **v2**.

v2 changes (per BREAKOUT_ALPHA_BLUEPRINT.md §Module-D):
    * max_position_pct  5% → 12%  (bigger bets on high-conviction)
    * min_position_usd  $500 → $2 000  (no micro-positions)
    * Breakout-score bonus sizing: 1.5× if score >0.7, 2.0× if >0.85
    * Confidence scaling widened: [0.3, 1.5] (was [0.5, 1.0])
    * Regime scaling more aggressive in trending (1.2× trending_up)
    * Pyramid-aware: initial entry = 60% of target (pyramider adds rest)

Ref: docs/blueprints/BREAKOUT_ALPHA_BLUEPRINT.md §Module-D
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class PositionSize:
    """Computed position sizing recommendation."""
    symbol: str
    target_weight: float        # % of portfolio
    shares: int                 # Discrete share count
    notional: float             # Dollar value
    kelly_raw: float            # Raw Kelly fraction
    kelly_half: float           # Half-Kelly (what we actually use)
    drawdown_scale: float       # [0, 1] drawdown multiplier
    vol_scale: float            # Volatility-target multiplier
    regime_scale: float         # Regime-based multiplier
    direction: float            # +1 long, -1 short

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "target_weight": round(self.target_weight, 4),
            "shares": self.shares,
            "notional": round(self.notional, 2),
            "kelly_raw": round(self.kelly_raw, 4),
            "kelly_half": round(self.kelly_half, 4),
            "drawdown_scale": round(self.drawdown_scale, 4),
            "vol_scale": round(self.vol_scale, 4),
            "regime_scale": round(self.regime_scale, 4),
            "direction": self.direction,
        }


class KellySizer:
    """Half-Kelly position sizing with breakout bonuses.

    v2 pipeline:
        1. Raw Kelly  = mean_return / variance
        2. Half-Kelly = Kelly × 0.5
        3. Scale by drawdown level
        4. Scale by volatility target (15 % annualised)
        5. Scale by regime (more aggressive in trending)
        6. Scale by confidence [0.3 … 1.5] (wider than v1)
        7. **NEW** — breakout score bonus (1.5× / 2.0×)
        8. Enforce per-position max (12 %), total portfolio max (95 %)
        9. Convert to shares; min position $2 000
    """

    def __init__(
        self,
        max_position_pct: float = 0.12,      # 12 % max per position (was 5 %)
        max_portfolio_pct: float = 0.95,      # 95 % max total invested
        vol_target: float = 0.15,             # 15 % annualised vol target
        drawdown_floor: float = 0.1,          # Scale to 10 % at max dd
        max_drawdown_cutoff: float = 0.25,    # Full risk-off threshold
        min_position_usd: float = 2000.0,     # Min position (was $500)
    ):
        self.max_position_pct = max_position_pct
        self.max_portfolio_pct = max_portfolio_pct
        self.vol_target = vol_target
        self.drawdown_floor = drawdown_floor
        self.max_drawdown_cutoff = max_drawdown_cutoff
        self.min_position_usd = min_position_usd

    def size_positions(
        self,
        candidates: list[dict[str, Any]],
        portfolio_value: float,
        current_drawdown: float,
        features_by_symbol: dict[str, pd.DataFrame],
        current_regime: str = "normal",
    ) -> list[PositionSize]:
        """Size positions for a list of alpha candidates.

        Parameters
        ----------
        candidates : list of dicts with keys:
            symbol, direction, confidence, predicted_return,
            breakout_score (optional, 0-1 from BreakoutScanner)
        portfolio_value : current portfolio equity
        current_drawdown : current drawdown as positive fraction (0.10 = 10 %)
        features_by_symbol : {symbol: feature DataFrame} for vol data
        current_regime : from regime detector

        Returns
        -------
        List of PositionSize objects, sorted by target_weight descending.
        """
        if portfolio_value <= 0 or current_drawdown >= self.max_drawdown_cutoff:
            return []

        # Sort candidates by conviction (highest first) so best entries
        # get allocation priority before portfolio cap is consumed.
        candidates = sorted(
            candidates,
            key=lambda c: abs(c.get("predicted_return", 0.0)) * c.get("confidence", 0.5),
            reverse=True,
        )

        sizes: list[PositionSize] = []
        total_weight = 0.0

        for cand in candidates:
            symbol = cand["symbol"]
            direction = cand.get("direction", 0.0)
            predicted_return = abs(cand.get("predicted_return", 0.0))
            confidence = cand.get("confidence", 0.5)
            breakout_score = cand.get("breakout_score", 0.0)

            # Guard against NaN / Inf / invalid values
            if (
                direction == 0
                or predicted_return < 1e-6
                or math.isnan(direction)
                or math.isnan(predicted_return)
                or math.isinf(direction)
                or math.isinf(predicted_return)
            ):
                continue

            # Get recent returns for Kelly calculation
            df = features_by_symbol.get(symbol)
            if df is None or len(df) < 30:
                continue

            ret_col = "ret_1d" if "ret_1d" in df.columns else None
            if ret_col is None:
                if "close" in df.columns:
                    returns = df["close"].pct_change().dropna().values[-60:]
                else:
                    continue
            else:
                returns = df[ret_col].dropna().values[-60:]

            if len(returns) < 20:
                continue

            # Directional returns based on signal
            dir_returns = returns * direction

            # 1. Raw Kelly
            mean_r = float(np.mean(dir_returns))
            var_r = float(np.var(dir_returns, ddof=1))

            if var_r < 1e-10 or mean_r <= 0:
                kelly_raw = 0.0
            else:
                kelly_raw = mean_r / var_r

            # 2. Half-Kelly
            kelly_half = kelly_raw * 0.5

            # 3. Drawdown scaling
            drawdown_scale = self._drawdown_scale(current_drawdown)

            # 4. Volatility targeting
            ann_vol = float(np.std(returns, ddof=1)) * np.sqrt(252)
            vol_scale = min(self.vol_target / max(ann_vol, 0.01), 2.0)

            # 5. Regime scaling (v2: more aggressive in trending)
            regime_scale = self._regime_scale(current_regime)

            # 6. Confidence scaling — wider range [0.3, 1.5] (was [0.5, 1.0])
            confidence_scale = 0.3 + min(confidence, 1.0) * 1.2

            # 7. **NEW** — Breakout score bonus
            breakout_bonus = self._breakout_bonus(breakout_score)

            # Combine all factors
            target_weight = (
                kelly_half
                * drawdown_scale
                * vol_scale
                * regime_scale
                * confidence_scale
                * breakout_bonus
            )

            # Enforce per-position cap
            target_weight = max(0.0, min(target_weight, self.max_position_pct))

            # Check portfolio-level cap
            if total_weight + target_weight > self.max_portfolio_pct:
                target_weight = max(0.0, self.max_portfolio_pct - total_weight)

            if target_weight < 0.001:
                continue

            # Convert to shares
            current_price = float(df["close"].iloc[-1]) if "close" in df.columns else 0
            if current_price <= 0:
                continue

            notional = portfolio_value * target_weight
            if notional < self.min_position_usd:
                continue

            shares = int(notional / current_price)
            if shares < 1:
                continue

            actual_notional = shares * current_price
            actual_weight = actual_notional / portfolio_value

            total_weight += actual_weight

            sizes.append(PositionSize(
                symbol=symbol,
                target_weight=actual_weight,
                shares=shares,
                notional=actual_notional,
                kelly_raw=kelly_raw,
                kelly_half=kelly_half,
                drawdown_scale=drawdown_scale,
                vol_scale=vol_scale,
                regime_scale=regime_scale,
                direction=direction,
            ))

        sizes.sort(key=lambda s: s.target_weight, reverse=True)
        return sizes

    def _drawdown_scale(self, drawdown: float) -> float:
        """Map current drawdown to position scale factor.

        Linear scale: 0% dd → 1.0, max_drawdown_cutoff → drawdown_floor
        """
        if drawdown <= 0:
            return 1.0
        if drawdown >= self.max_drawdown_cutoff:
            return self.drawdown_floor

        frac = drawdown / self.max_drawdown_cutoff
        return 1.0 - frac * (1.0 - self.drawdown_floor)

    def _regime_scale(self, regime: str) -> float:
        """Reduce sizing in unfavorable regimes — v2 more aggressive in trends.

        If EvolutionEngine has set ``_evolved_regime_scales``, those
        override the static defaults (EvolutionEngine learns which
        regimes are truly profitable from trade outcomes).
        """
        # Use evolved scales if available
        if hasattr(self, "_evolved_regime_scales") and self._evolved_regime_scales:
            scale = self._evolved_regime_scales.get(regime)
            if scale is not None:
                return float(scale)

        scales = {
            "trending_up": 1.2,     # was 1.0 — lean in
            "trending": 1.0,        # was 0.9
            "normal": 0.85,         # was 0.8
            "trending_down": 0.6,
            "chop": 0.5,
            "high_vol": 0.4,
            "stress": 0.2,
            "crisis": 0.1,
        }
        return scales.get(regime, 0.7)

    @staticmethod
    def _breakout_bonus(breakout_score: float) -> float:
        """Bonus sizing multiplier for high breakout scores.

        Returns
        -------
        1.0 if score < 0.5 (no bonus)
        1.5 if score >= 0.7 (confirmed breakout)
        2.0 if score >= 0.85 (high-conviction breakout)
        Linear interpolation in between.
        """
        if breakout_score < 0.5:
            return 1.0
        if breakout_score >= 0.85:
            return 2.0
        if breakout_score >= 0.7:
            # Interpolate 1.5 → 2.0 for 0.7 → 0.85
            return 1.5 + (breakout_score - 0.7) / 0.15 * 0.5
        # Interpolate 1.0 → 1.5 for 0.5 → 0.7
        return 1.0 + (breakout_score - 0.5) / 0.2 * 0.5
