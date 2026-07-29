"""Experimental exit policies for the offline exit-logic A/B (Audit 2026-06-09 §8.2).

NOT imported by the live trading path. Loaded only by scripts/edge_experiments.py
when ORGANISM_EXIT_POLICY is set, to swap the engine's exit policy in costed replay.

Motivation (live data, 567 trades to 2026-06-18): active exits
(stop_loss/trailing_stop/failure_to_follow/pyramid) lost ~$1,760 while passive/time
exits earned ~$968; 63% of trades that reached positive MFE still closed red,
giving back ~$1,425 of favorable excursion. These variants test whether replacing
the active engine-driven exits with time-based / MFE-retracement logic retains more.
"""

from __future__ import annotations

import os

from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitSignal


class AltExitEngine(AdaptiveExitEngine):
    """Drop-in AdaptiveExitEngine whose ``check_exit`` implements an alternative
    exit policy selected by the ``ORGANISM_EXIT_POLICY`` env var:

      ``time_only``    no ATR stop / trailing / failure-to-follow; only a wide
                       disaster stop + a hard time cap (+ take-profit and the
                       learning-mode horizon barrier, as in production).
      ``retracement``  exit when price gives back more than F of the peak
                       favorable excursion (MFE-based trailing), once a minimum
                       favorable excursion is reached; wide disaster stop + time cap.

    Any other / unset value falls back to the production ``check_exit`` unchanged,
    so this class is safe to substitute for AdaptiveExitEngine everywhere.

    The disaster stop and the highest_favorable / worst_adverse trackers are
    preserved, so the persisted TradeRecord's MFE/MAE remain valid measurements.
    Inline exits in live_engine (ml_reversal, eod_flatten, pyramid_*) are NOT
    affected by this swap — they bypass the exit engine entirely (by design;
    those are net-positive).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.alt_policy = os.getenv("ORGANISM_EXIT_POLICY", "").strip()
        self.alt_disaster_pct = self._envf("ORGANISM_ALT_DISASTER_PCT", float(self.max_loss_pct))
        self.alt_retrace_frac = self._envf("ORGANISM_ALT_RETRACE_FRAC", 0.5)
        self.alt_min_fav_r = self._envf("ORGANISM_ALT_MIN_FAVORABLE_R", 0.5)
        self.alt_time_cap = self._envi("ORGANISM_ALT_TIME_CAP_BARS", 120)

    # ── env helpers ──
    @staticmethod
    def _envf(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, default))
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _envi(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, default))
        except (TypeError, ValueError):
            return int(default)

    def _track(self, levels, price: float) -> None:
        """Mirror the base engine's per-tick peak/worst tracking so MFE/MAE
        stay correct even though we bypass the rest of base check_exit."""
        d = levels.direction
        if d > 0:
            levels.highest_favorable = max(levels.highest_favorable, price)
        else:
            if levels.highest_favorable == levels.entry_price:
                levels.highest_favorable = price
            levels.highest_favorable = min(levels.highest_favorable, price)
        if levels.worst_adverse <= 0:
            levels.worst_adverse = price
        elif d > 0:
            levels.worst_adverse = min(levels.worst_adverse, price)
        else:
            levels.worst_adverse = max(levels.worst_adverse, price)

    def check_exit(self, levels, current_price, current_regime="unknown", is_new_bar=True):
        if self.alt_policy not in ("time_only", "retracement"):
            return super().check_exit(levels, current_price, current_regime, is_new_bar)

        d = levels.direction
        self._track(levels, current_price)

        # Wide disaster stop — the only price-based stop in these policies; every tick.
        if levels.entry_price > 0:
            pnl_pct = (current_price - levels.entry_price) / levels.entry_price * d
            if pnl_pct <= -self.alt_disaster_pct:
                return ExitSignal(True, "alt_disaster_stop", current_price)

        if not is_new_bar:
            return ExitSignal(False)

        levels.bars_held += 1
        if levels.bars_held < self._min_hold_bars(levels.prediction_horizon):
            return ExitSignal(False)

        # Keep take-profit where production would (disabled in learning mode).
        if not self.learning_mode:
            if d > 0 and current_price >= levels.take_profit:
                return ExitSignal(True, "take_profit", levels.take_profit)
            if d < 0 and current_price <= levels.take_profit:
                return ExitSignal(True, "take_profit", levels.take_profit)

        # MFE-retracement lock (retracement policy only).
        if self.alt_policy == "retracement":
            risk = levels.initial_risk_at_entry or max(
                abs(levels.entry_price - levels.stop_loss), 1e-6
            )
            peak_exc = (levels.highest_favorable - levels.entry_price) * d
            if peak_exc > 0 and peak_exc >= self.alt_min_fav_r * risk:
                cur_exc = (current_price - levels.entry_price) * d
                if cur_exc <= (1.0 - self.alt_retrace_frac) * peak_exc:
                    return ExitSignal(True, "alt_retracement", current_price)

        # Learning-mode horizon barrier (kept identical to production).
        if self.learning_mode and levels.bars_held >= 18:
            return ExitSignal(True, "horizon_timeout", current_price)

        # Hard time cap (both policies).
        if levels.bars_held >= self.alt_time_cap:
            return ExitSignal(True, "alt_time_cap", current_price)

        return ExitSignal(False)
