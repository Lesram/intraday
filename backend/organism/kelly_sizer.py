"""
Module 4 — Kelly Position Sizer **v2**.

v2 changes (per BREAKOUT_ALPHA_BLUEPRINT.md §Module-D):
    * max_position_pct  5% → 10%  (bigger bets on high-conviction; was 12%, reduced)
    * min_position_usd  $500 → $2 000  (no micro-positions)
    * Breakout-score bonus sizing: 1.5× if score >0.7, 2.0× if >0.85
    * Confidence scaling widened: [0.3, 1.5] (was [0.5, 1.0])
    * Regime scaling more aggressive in trending (1.2× trending_up)
    * Pyramid-aware: initial entry = 60% of target (pyramider adds rest)

Ref: docs/blueprints/BREAKOUT_ALPHA_BLUEPRINT.md §Module-D
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

_logger = logging.getLogger(__name__)


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
    """Half-Kelly position sizing with breakout bonuses + regime stratification.

    v2 pipeline:
        1. Raw Kelly  = mean_return / variance
        2. Half-Kelly = Kelly × 0.5
        3. Scale by drawdown level
        4. Scale by volatility target (15 % annualised)
        5. Scale by regime (more aggressive in trending)
        6. Scale by confidence [0.3 … 1.5] (wider than v1)
        7. **NEW** — breakout score bonus (1.5× / 2.0×)
        8. Enforce per-position max (10 %), total portfolio max (95 %)
        9. Convert to shares; min position $2 000

    v3 addition: regime-stratified Kelly — per-regime win_rate/payoff tracking.
    """

    def __init__(
        self,
        max_position_pct: float = 0.10,      # 10 % max per position (was 12 %)
        max_portfolio_pct: float = 0.95,      # 95 % max total invested
        vol_target: float = 0.15,             # 15 % annualised vol target
        drawdown_floor: float = 0.1,          # Scale to 10 % at max dd
        max_drawdown_cutoff: float = 0.25,    # Full risk-off threshold
        min_position_usd: float = 2000.0,     # Min position (was $500)
        bars_per_day: int = 1,                # 390 for 1Min, 78 for 5Min, etc.
    ):
        self.max_position_pct = max_position_pct
        self.max_portfolio_pct = max_portfolio_pct
        self.vol_target = vol_target
        self.drawdown_floor = drawdown_floor
        self.max_drawdown_cutoff = max_drawdown_cutoff
        self.min_position_usd = min_position_usd
        self._bars_per_day = bars_per_day

        # ML confidence floor: when trained ML has confidence >= _ML_CONFIDENCE_MIN,
        # allow a small position so signals aren't silenced.
        # Trained: 0.04 × conf, Untrained: 0.02 × conf (inline in size_positions)
        # Both require edge_clears_cost gate to pass.
        self._ML_CONFIDENCE_MIN = 0.5

        # Regime-stratified Kelly stats: {regime: {wins, losses, total_pnl, total_win_pnl, total_loss_pnl}}
        self._regime_stats: dict[str, dict[str, float]] = {}
        # Last sizing intermediates for telemetry (confidence_scale, breakout_bonus per symbol)
        self._last_intermediates: dict[str, dict[str, float]] = {}

    def _estimate_spread_cost(
        self,
        symbol: str,
        quote_provider: Callable[[str], dict[str, Any]] | None,
        features_by_symbol: dict[str, pd.DataFrame],
    ) -> float:
        """Per-symbol dynamic spread cost from live quote, time-of-day, and liquidity.

        Returns spread_cost_pct clamped to [3bps, 50bps].
        """
        from backend.utils.market_hours import get_slippage_multiplier

        # 1. Base spread from live bid/ask (fallback: 10bps)
        base_spread = 0.0010
        if quote_provider is not None:
            try:
                quote = quote_provider(symbol)
                bid = quote.get("bid")
                ask = quote.get("ask")
                if bid and ask and bid > 0 and ask > 0:
                    mid = (bid + ask) / 2.0
                    base_spread = (ask - bid) / mid
            except Exception:
                pass  # keep default

        # 2. Time-of-day multiplier
        time_mult = get_slippage_multiplier()

        # 3. Liquidity adjustment from vol_sma_ratio
        liquidity_mult = 1.0
        df = features_by_symbol.get(symbol)
        if df is not None and "vol_sma_ratio" in df.columns and len(df) > 0:
            vol_ratio = float(df["vol_sma_ratio"].iloc[-1])
            if math.isfinite(vol_ratio) and vol_ratio > 0:
                liquidity_mult = 1.0 + max(0.0, 1.0 - vol_ratio) * 0.5

        cost = base_spread * time_mult * liquidity_mult
        return max(0.0003, min(cost, 0.0050))

    def size_positions(
        self,
        candidates: list[dict[str, Any]],
        portfolio_value: float,
        current_drawdown: float,
        features_by_symbol: dict[str, pd.DataFrame],
        current_regime: str = "unknown",
        ml_is_trained: bool = True,
        quote_provider: Callable[[str], dict[str, Any]] | None = None,
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
        self._last_intermediates = {}

        for cand in candidates:
            symbol = cand["symbol"]
            direction = cand.get("direction", 0.0)
            predicted_return = abs(cand.get("predicted_return", 0.0))
            confidence = cand.get("confidence", 0.5)
            breakout_score = cand.get("breakout_score", 0.0)

            # Floor predicted_return: when ML is untrained, breakout signals
            # arrive with predicted_return=0. Use a conservative default so
            # the sizer can still allocate based on breakout score + confidence.
            untrained_floor = 0.005 if not ml_is_trained else 0.01
            if predicted_return < 1e-6 and breakout_score > 0:
                predicted_return = untrained_floor

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

            # 1. Raw Kelly (try regime-stratified first, fallback to global)
            regime_kelly = self.get_regime_kelly(current_regime)
            if regime_kelly is not None:
                kelly_raw = min(regime_kelly, 1.0)
            else:
                mean_r = float(np.mean(dir_returns))
                var_r = float(np.var(dir_returns, ddof=1))

                if var_r < 1e-8 or mean_r <= 0 or not math.isfinite(mean_r) or not math.isfinite(var_r):
                    kelly_raw = 0.0
                else:
                    kelly_raw = min(mean_r / var_r, 1.0)  # Cap raw Kelly at 100%

            # 2. Half-Kelly
            kelly_half = kelly_raw * 0.5
            ml_floor_applied = False

            # Edge-over-cost gate: predicted edge must clear 2x estimated
            # round-trip spread+slippage cost to justify the trade.
            spread_cost_pct = self._estimate_spread_cost(
                symbol, quote_provider, features_by_symbol,
            )
            _COST_MULT = 2.0
            edge_clears_cost = predicted_return >= spread_cost_pct * _COST_MULT

            # Breakout floor — halved, requires edge to clear cost
            if kelly_half < 0.005 and breakout_score >= 0.55:
                if edge_clears_cost:
                    kelly_half = max(kelly_half, 0.003 * breakout_score)

            # ML confidence floor — halved, requires edge to clear cost.
            # Guard: suppress floor when the current regime has a track
            # record of negative expectancy (>= 5 trades, total_pnl <= 0).
            _regime_has_edge = True
            _rs = self._regime_stats.get(current_regime)
            if _rs:
                _total_trades = _rs["wins"] + _rs["losses"]
                if _total_trades >= 5 and _rs["total_pnl"] <= 0:
                    _regime_has_edge = False

            if kelly_half < 0.005 and confidence >= self._ML_CONFIDENCE_MIN and _regime_has_edge and edge_clears_cost:
                if ml_is_trained:
                    ml_floor = 0.04 * confidence  # halved from 0.08
                else:
                    ml_floor = 0.02 * confidence
                kelly_half = max(kelly_half, ml_floor)
                ml_floor_applied = True
                _logger.info(
                    "ML confidence floor for %s: kelly_half=%.4f "
                    "(conf=%.2f, floor=%.4f, trained=%s)",
                    symbol, kelly_half, confidence, ml_floor, ml_is_trained,
                )
            elif not _regime_has_edge and kelly_half < 0.005:
                _logger.info(
                    "ML floor suppressed for %s: regime=%s has negative expectancy "
                    "(trades=%d, pnl=%.2f)",
                    symbol, current_regime,
                    int(_rs["wins"] + _rs["losses"]) if _rs else 0,
                    _rs["total_pnl"] if _rs else 0,
                )

            # If edge doesn't clear cost and kelly is near-zero, skip trade
            if not edge_clears_cost and kelly_half < 0.005:
                kelly_half = 0.0

            # 3. Drawdown scaling
            drawdown_scale = self._drawdown_scale(current_drawdown)

            # 4. Volatility targeting
            ann_vol = float(np.std(returns, ddof=1)) * np.sqrt(252 * self._bars_per_day)
            vol_scale = min(self.vol_target / max(ann_vol, 0.01), 2.0)

            # 5. Regime scaling (v2: more aggressive in trending)
            regime_scale = self._regime_scale(current_regime)

            # 6. Confidence scaling — wider range [0.3, 1.5] (was [0.5, 1.0])
            confidence_scale = 0.3 + min(confidence, 1.0) * 1.2
            if not ml_is_trained:
                confidence_scale = min(confidence_scale, 0.6)

            # 7. **NEW** — Breakout score bonus
            breakout_bonus = self._breakout_bonus(breakout_score)
            if not ml_is_trained:
                breakout_bonus = 1.0

            # Store intermediates for telemetry
            self._last_intermediates[symbol] = {
                "confidence_scale": confidence_scale,
                "breakout_bonus": breakout_bonus,
                "ml_floor_applied": ml_floor_applied,
                "kelly_raw": kelly_raw,
                "kelly_half": kelly_half,
                "spread_cost_pct": spread_cost_pct,
            }

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

            if target_weight < 0.0005:  # was 0.001 — too aggressive in stress
                continue

            # Convert to shares
            current_price = float(df["close"].iloc[-1]) if "close" in df.columns else 0
            if current_price <= 0:
                continue

            notional = portfolio_value * target_weight
            if notional < self.min_position_usd:
                _logger.info("Kelly skip %s: notional=%.0f < min=%d", symbol, notional, self.min_position_usd)
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
            "trending_up": 1.2,
            "trending_down": 0.6,
            "chop": 0.5,
            "high_vol": 0.8,    # was 0.5 — winners undersized while stops deliver full-sized losses
            "low_vol": 1.0,         # calm market → full sizing
            "stress": 0.4,           # was 0.3 — still 60% reduction, avoids 0-sizing cascade
            "unknown": 0.7,         # insufficient data → conservative
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

    # ── Regime-stratified Kelly ──────────────────────────────────

    def record_trade(self, regime: str, pnl: float) -> None:
        """Record a completed trade outcome for regime-stratified Kelly."""
        if regime not in self._regime_stats:
            self._regime_stats[regime] = {
                "wins": 0, "losses": 0,
                "total_pnl": 0.0, "total_win_pnl": 0.0, "total_loss_pnl": 0.0,
            }
        stats = self._regime_stats[regime]
        stats["total_pnl"] += pnl
        if pnl > 0:
            stats["wins"] += 1
            stats["total_win_pnl"] += pnl
        else:
            stats["losses"] += 1
            stats["total_loss_pnl"] += abs(pnl)

    def get_regime_kelly(self, regime: str) -> float | None:
        """Compute Kelly fraction for a specific regime.

        Returns None if insufficient data (< 10 trades in regime).
        """
        stats = self._regime_stats.get(regime)
        if not stats:
            return None
        total = stats["wins"] + stats["losses"]
        if total < 10:
            return None
        win_rate = stats["wins"] / total
        if stats["losses"] == 0 or stats["total_loss_pnl"] < 1e-8:
            return None
        avg_win = stats["total_win_pnl"] / max(stats["wins"], 1)
        avg_loss = stats["total_loss_pnl"] / max(stats["losses"], 1)
        payoff_ratio = avg_win / avg_loss
        if payoff_ratio <= 0:
            return None  # No wins in this regime — cannot compute Kelly
        # Kelly: W - (1-W)/B
        kelly = win_rate - (1 - win_rate) / payoff_ratio
        return max(kelly, 0.0)

    def regime_stats_to_dict(self) -> dict[str, Any]:
        """Serialize regime stats for brain persistence."""
        return dict(self._regime_stats)

    def load_regime_stats(self, data: dict[str, Any]) -> None:
        """Restore regime stats from brain."""
        if data and isinstance(data, dict):
            self._regime_stats = {
                k: {
                    "wins": float(v.get("wins", 0)),
                    "losses": float(v.get("losses", 0)),
                    "total_pnl": float(v.get("total_pnl", 0)),
                    "total_win_pnl": float(v.get("total_win_pnl", 0)),
                    "total_loss_pnl": float(v.get("total_loss_pnl", 0)),
                }
                for k, v in data.items()
                if isinstance(v, dict)
            }
