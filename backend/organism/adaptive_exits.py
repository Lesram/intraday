"""
Module 5 — Adaptive Exit Engine **v2**.

Complete overhaul: the v1 trailing stop (1 %-start, 50 %-trail) cut every
winner at ~$225 avg.  v2 uses ATR-distance trailing that lets winners run:

    1. Initial stop       — 1.5× ATR (tighter = smaller per-loss bite)
    2. Trailing activation — after price moves **3× ATR** in our favour
    3. Trail distance      — fixed **2.5× ATR** from highest close
                             (3.5× in trending, 1.5× in chop)
    4. Partial take-profit — sell 30 % at 3R, let 70 % ride
    5. Full TP             — 6R trending / 4R normal / 2.5R chop
    6. Time limit          — disabled in trending; 40 bars normal; 25 chop
    7. Regime stress       — tighten 40 % on stress/crisis transition

Ref: docs/blueprints/BREAKOUT_ALPHA_BLUEPRINT.md §Module-C
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# ── data classes ──────────────────────────────────────────────────────────

@dataclass
class ExitLevels:
    """Exit prices and trailing state for one position."""

    symbol: str
    direction: float          # +1 long, −1 short
    entry_price: float
    stop_loss: float          # Hard stop
    take_profit: float        # Full target
    trailing_stop: float      # Current trailing level
    atr_at_entry: float
    regime_at_entry: str
    highest_favorable: float  # Best price since entry
    bars_held: int = 0

    # ── v2 additions ──
    partial_tp_price: float = 0.0    # Price at which to take partial TP
    partial_tp_taken: bool = False   # True after partials are sold
    trailing_active: bool = False    # True once trail kicks in (3× ATR move)
    stress_tightened: bool = False   # True after one-time stress regime tightening

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry": round(self.entry_price, 4),
            "stop_loss": round(self.stop_loss, 4),
            "take_profit": round(self.take_profit, 4),
            "trailing_stop": round(self.trailing_stop, 4),
            "atr": round(self.atr_at_entry, 4),
            "bars_held": self.bars_held,
            "partial_tp_taken": self.partial_tp_taken,
            "trailing_active": self.trailing_active,
        }


@dataclass
class ExitSignal:
    """Whether to exit and why."""

    should_exit: bool
    reason: str = ""
    exit_price: float = 0.0
    # v2: partial exits
    partial_exit: bool = False   # True → only sell partial_pct of position
    partial_pct: float = 0.0     # e.g. 0.30 = sell 30 %

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "should_exit": self.should_exit,
            "reason": self.reason,
            "exit_price": round(self.exit_price, 4),
        }
        if self.partial_exit:
            d["partial_exit"] = True
            d["partial_pct"] = self.partial_pct
        return d


# ── engine ────────────────────────────────────────────────────────────────

class AdaptiveExitEngine:
    """ATR-based exits that let winners run.

    v2 key differences vs v1:
        * Trail starts after **3× ATR** favorable move (not 1 %)
        * Trail distance = fixed ATR multiple from peak (not % of profit)
        * Partial TP at 3R (sell 30 %, let 70 % ride)
        * Regime-adaptive TP, trail distance, and time limits
        * Initial stop tighter (1.5× ATR) for smaller per-loss bite
    """

    # ── regime lookup tables ──
    # Stop width  (ATR multiplier for initial SL)
    REGIME_STOP_ATR = {
        "trending_up": 2.0,
        "trending":    1.8,
        "normal":      1.5,
        "trending_down": 1.3,
        "chop":        1.2,
        "high_vol":    1.0,
        "stress":      0.9,
        "crisis":      0.8,
    }
    # Take-profit R-multiple
    REGIME_TP_R = {
        "trending_up": 6.0,
        "trending":    5.0,
        "normal":      4.0,
        "trending_down": 3.0,
        "chop":        2.5,
        "high_vol":    3.0,
        "stress":      2.0,
        "crisis":      1.5,
    }
    # Trail distance (ATR multiple from highest close)
    REGIME_TRAIL_ATR = {
        "trending_up": 3.5,
        "trending":    3.0,
        "normal":      2.5,
        "trending_down": 2.0,
        "chop":        1.5,
        "high_vol":    2.0,
        "stress":      1.5,
        "crisis":      1.0,
    }
    # Max bars held (0 = disabled)
    REGIME_MAX_BARS = {
        "trending_up": 0,
        "trending":    0,
        "normal":      40,
        "trending_down": 30,
        "chop":        25,
        "high_vol":    30,
        "stress":      20,
        "crisis":      15,
    }
    # Time-decay start bar
    REGIME_DECAY_START = {
        "trending_up": 0,     # no decay in strong trends
        "trending":    0,
        "normal":      30,
        "trending_down": 20,
        "chop":        15,
        "high_vol":    20,
        "stress":      10,
        "crisis":      8,
    }

    def __init__(
        self,
        atr_multiplier: float = 1.5,        # Tighter initial stop (was 2.0)
        profit_r_multiple: float = 4.0,      # Default TP R (regime overrides)
        trailing_start_atr: float = 3.0,     # Trail after 3× ATR move
        trailing_distance_atr: float = 2.5,  # Trail 2.5× ATR from peak
        max_bars_held: int = 40,             # Default (regime overrides)
        time_decay_start: int = 30,          # Default (regime overrides)
        partial_tp_r: float = 3.0,           # Partial TP at 3R
        partial_tp_pct: float = 0.30,        # Sell 30 % at partial TP
        # Legacy compat — ignored in v2 logic but kept for API compat
        trailing_start_pct: float | None = None,
        trailing_step_pct: float | None = None,
    ):
        self.atr_multiplier = atr_multiplier
        self.profit_r_multiple = profit_r_multiple
        self.trailing_start_atr = trailing_start_atr
        self.trailing_distance_atr = trailing_distance_atr
        self.max_bars_held = max_bars_held
        self.time_decay_start = time_decay_start
        self.partial_tp_r = partial_tp_r
        self.partial_tp_pct = partial_tp_pct

    # ── public API ────────────────────────────────────────────────────────

    def create_exit_levels(
        self,
        symbol: str,
        direction: float,
        entry_price: float,
        predicted_return: float,
        features_df: pd.DataFrame,
        regime: str = "normal",
    ) -> ExitLevels:
        """Create initial exit levels for a new position.

        Parameters
        ----------
        symbol : ticker
        direction : +1 long, −1 short
        entry_price : fill price
        predicted_return : ML-predicted return (positive = favorable)
        features_df : feature DataFrame for ATR computation
        regime : current market regime
        """
        atr = self._compute_atr(features_df, period=14)
        if atr < 1e-6:
            atr = entry_price * 0.02  # 2 % fallback

        # Regime-adjusted stop distance
        stop_atr_mult = self.REGIME_STOP_ATR.get(regime, self.atr_multiplier)
        risk_distance = atr * stop_atr_mult

        # Regime-adjusted R-multiple for full TP
        tp_r = self.REGIME_TP_R.get(regime, self.profit_r_multiple)

        # Partial TP distance (always 3R)
        partial_r = self.partial_tp_r

        if direction > 0:  # Long
            stop_loss = entry_price - risk_distance
            tp_from_risk = entry_price + risk_distance * tp_r
            tp_from_ml = entry_price * (1 + abs(predicted_return))
            take_profit = max(tp_from_risk, tp_from_ml)
            partial_tp_price = entry_price + risk_distance * partial_r
        else:  # Short
            stop_loss = entry_price + risk_distance
            tp_from_risk = entry_price - risk_distance * tp_r
            tp_from_ml = entry_price * (1 - abs(predicted_return))
            take_profit = min(tp_from_risk, tp_from_ml)
            partial_tp_price = entry_price - risk_distance * partial_r

        return ExitLevels(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop=stop_loss,  # Initially same as hard stop
            atr_at_entry=atr,
            regime_at_entry=regime,
            highest_favorable=entry_price,
            bars_held=0,
            partial_tp_price=partial_tp_price,
            partial_tp_taken=False,
            trailing_active=False,
        )

    def check_exit(
        self,
        levels: ExitLevels,
        current_price: float,
        current_regime: str = "normal",
    ) -> ExitSignal:
        """Check if any exit condition is triggered.

        Parameters
        ----------
        levels : current ExitLevels (will be mutated for trailing updates)
        current_price : latest price
        current_regime : current regime (for dynamic adjustments)

        Returns
        -------
        ExitSignal with should_exit flag and reason.
        """
        levels.bars_held += 1
        direction = levels.direction

        # Update highest favorable price
        if direction > 0:
            levels.highest_favorable = max(levels.highest_favorable, current_price)
        else:
            if levels.highest_favorable == levels.entry_price:
                levels.highest_favorable = current_price
            levels.highest_favorable = min(levels.highest_favorable, current_price)

        # 1. Hard stop-loss check
        if direction > 0 and current_price <= levels.stop_loss:
            return ExitSignal(True, "stop_loss", levels.stop_loss)
        if direction < 0 and current_price >= levels.stop_loss:
            return ExitSignal(True, "stop_loss", levels.stop_loss)

        # 2. Partial take-profit at 3R (sell 30 %, let rest ride)
        partial_signal = self._check_partial_tp(levels, current_price)
        if partial_signal.should_exit:
            return partial_signal

        # 3. Full take-profit check
        if direction > 0 and current_price >= levels.take_profit:
            return ExitSignal(True, "take_profit", levels.take_profit)
        if direction < 0 and current_price <= levels.take_profit:
            return ExitSignal(True, "take_profit", levels.take_profit)

        # 4. ATR-based trailing stop update and check
        trail_signal = self._update_trailing_stop(levels, current_price, current_regime)
        if trail_signal.should_exit:
            return trail_signal

        # 5. Time-based exit (regime-adaptive — disabled in trending)
        max_bars = self.REGIME_MAX_BARS.get(current_regime, self.max_bars_held)
        if max_bars > 0 and levels.bars_held >= max_bars:
            # Only force exit if position is in profit — give losers more room
            # to recover rather than locking in a loss at time limit
            pnl_dir = (current_price - levels.entry_price) * direction
            if pnl_dir > 0:
                return ExitSignal(True, "max_holding_period", current_price)

        # 6. Time decay — very gentle, only in non-trending
        decay_start = self.REGIME_DECAY_START.get(current_regime, self.time_decay_start)
        if decay_start > 0 and levels.bars_held >= decay_start:
            self._apply_time_decay(levels, decay_start)

        # 7. Regime change — if regime went to stress/crisis, tighten ONCE
        if (
            not levels.stress_tightened
            and current_regime in ("stress", "crisis")
            and levels.regime_at_entry not in ("stress", "crisis")
        ):
            self._tighten_for_stress(levels, current_price)
            levels.stress_tightened = True

        return ExitSignal(False)

    # ── private helpers ───────────────────────────────────────────────────

    def _check_partial_tp(
        self, levels: ExitLevels, current_price: float
    ) -> ExitSignal:
        """Take partial profits at 3R — sell 30 %, let 70 % ride."""
        if levels.partial_tp_taken:
            return ExitSignal(False)

        direction = levels.direction
        hit = False
        if direction > 0 and current_price >= levels.partial_tp_price:
            hit = True
        elif direction < 0 and current_price <= levels.partial_tp_price:
            hit = True

        if hit:
            levels.partial_tp_taken = True
            # After partial TP, move stop to breakeven
            levels.stop_loss = levels.entry_price
            return ExitSignal(
                should_exit=True,
                reason="partial_take_profit",
                exit_price=current_price,
                partial_exit=True,
                partial_pct=self.partial_tp_pct,
            )
        return ExitSignal(False)

    def _update_trailing_stop(
        self,
        levels: ExitLevels,
        current_price: float,
        current_regime: str = "normal",
    ) -> ExitSignal:
        """ATR-distance trailing from highest favorable close.

        Key change from v1: trail distance is a fixed ATR multiple from the
        peak price, NOT a percentage of profit.  This lets winners run much
        further in trending markets.
        """
        direction = levels.direction
        atr = levels.atr_at_entry

        if atr < 1e-6:
            return ExitSignal(False)

        # Favorable excursion in ATR units
        if direction > 0:
            excursion_atr = (levels.highest_favorable - levels.entry_price) / atr
        else:
            excursion_atr = (levels.entry_price - levels.highest_favorable) / atr

        # Only activate trailing after 3× ATR move (not 1 % like v1)
        if excursion_atr < self.trailing_start_atr:
            return ExitSignal(False)

        levels.trailing_active = True

        # Regime-adaptive trail distance
        trail_atr = self.REGIME_TRAIL_ATR.get(
            current_regime, self.trailing_distance_atr
        )
        trail_distance = atr * trail_atr

        if direction > 0:
            new_trail = levels.highest_favorable - trail_distance
            # Never trail below breakeven once trailing is active
            new_trail = max(new_trail, levels.entry_price)
            levels.trailing_stop = max(levels.trailing_stop, new_trail)

            if current_price <= levels.trailing_stop:
                return ExitSignal(True, "trailing_stop", levels.trailing_stop)
        else:
            new_trail = levels.highest_favorable + trail_distance
            new_trail = min(new_trail, levels.entry_price)
            levels.trailing_stop = min(levels.trailing_stop, new_trail)

            if current_price >= levels.trailing_stop:
                return ExitSignal(True, "trailing_stop", levels.trailing_stop)

        return ExitSignal(False)

    def _apply_time_decay(self, levels: ExitLevels, decay_start: int) -> None:
        """Gentle stop tightening — 1 % per bar (was 2 % in v1)."""
        decay_bars = levels.bars_held - decay_start
        decay_factor = 1.0 - decay_bars * 0.01  # 1 % per bar (gentler)
        decay_factor = max(decay_factor, 0.6)    # Don't tighten more than 40 %

        if levels.direction > 0:
            range_ = levels.entry_price - levels.stop_loss
            if range_ > 0:
                levels.stop_loss = levels.entry_price - range_ * decay_factor
        else:
            range_ = levels.stop_loss - levels.entry_price
            if range_ > 0:
                levels.stop_loss = levels.entry_price + range_ * decay_factor

    def _tighten_for_stress(self, levels: ExitLevels, current_price: float) -> None:
        """Regime went to stress/crisis — tighten exit by 40 %."""
        if levels.direction > 0:
            range_ = current_price - levels.stop_loss
            if range_ > 0:
                levels.stop_loss = current_price - range_ * 0.6
        else:
            range_ = levels.stop_loss - current_price
            if range_ > 0:
                levels.stop_loss = current_price + range_ * 0.6

    @staticmethod
    def _compute_atr(df: pd.DataFrame, period: int = 14) -> float:
        """Average True Range from OHLCV data."""
        if len(df) < period + 1:
            if "close" in df.columns and len(df) >= 2:
                return float(df["close"].diff().abs().mean())
            return 0.0

        high = df["high"].values if "high" in df.columns else df["close"].values
        low = df["low"].values if "low" in df.columns else df["close"].values
        close = df["close"].values

        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )

        if len(tr) < period:
            return float(np.mean(tr))

        # EMA-based ATR
        atr = np.mean(tr[:period])
        alpha = 2.0 / (period + 1)
        for i in range(period, len(tr)):
            atr = alpha * tr[i] + (1 - alpha) * atr
        return float(atr)
