"""
Module 5 — Adaptive Exit Engine **v2**.

Complete overhaul: the v1 trailing stop (1 %-start, 50 %-trail) cut every
winner at ~$225 avg.  v2 uses ATR-distance trailing that lets winners run:

    1. Initial stop       — 1.5× ATR (tighter = smaller per-loss bite)
    2. Trailing activation — after price moves **3× ATR** in our favour
    3. Trail distance      — fixed **2.5× ATR** from highest close
                             (3.5× in trending_up, 2.0× in trending_down, 1.5× in chop)
    4. Partial take-profit — sell 30 % at 3R, let 70 % ride
    5. Full TP             — 6R trending_up/down / 4R low_vol / 2.5R chop
    6. Time limit          — disabled in trending_up/down; 40 bars low_vol; 25 chop
    7. Regime stress       — tighten 40 % on stress transition

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
    # Audit 2026-06-11 (measurement integrity): worst price since entry —
    # enables a REAL max-adverse-excursion. The trade record's mae was
    # previously a static stop-distance proxy, never a measurement.
    worst_adverse: float = 0.0  # 0.0 = uninitialized (legacy state)

    # ── v2 additions ──
    partial_tp_price: float = 0.0    # Price at which to take partial TP
    partial_tp_taken: bool = False   # True after partials are sold
    trailing_active: bool = False    # True once trail kicks in (3× ATR move)
    stress_tightened: bool = False   # True after one-time stress regime tightening
    profit_locked: bool = False      # True after one-time profit lock at 2R

    # ── v3 additions (improve4) ──
    last_bar_time: str = ""          # Timestamp of last bar boundary seen
    prediction_horizon: int = 15     # ML prediction horizon in bars
    price_at_prior_bar: float = 0.0  # Price at previous bar (for FTF momentum check)

    # ── v4 additions (improve7) ──
    ftf_stop_tightened: bool = False  # True after FTF tightened stop in chop (one-shot)
    price_two_bars_ago: float = 0.0   # Price 2 bars ago (for multi-bar momentum)

    # ── v5 additions (patch-queue-e2) ──
    initial_risk_at_entry: float = 0.0   # Stable risk denominator for FTF R-calc

    def to_dict(self) -> dict[str, Any]:
        # Audit-I finding I-4 (2026-05-02): cast to native types to keep
        # JSON serialization safe from np.float64 / np.bool_ inputs.
        return {
            "symbol": str(self.symbol),
            "direction": float(self.direction),
            "entry": round(float(self.entry_price), 4),
            "stop_loss": round(float(self.stop_loss), 4),
            "take_profit": round(float(self.take_profit), 4),
            "trailing_stop": round(float(self.trailing_stop), 4),
            "atr": round(float(self.atr_at_entry), 4),
            "regime_at_entry": str(self.regime_at_entry),
            "highest_favorable": round(float(self.highest_favorable), 4),
            "worst_adverse": round(float(self.worst_adverse), 4),
            "bars_held": int(self.bars_held),
            "partial_tp_price": round(float(self.partial_tp_price), 4),
            "partial_tp_taken": bool(self.partial_tp_taken),
            "trailing_active": bool(self.trailing_active),
            "stress_tightened": bool(self.stress_tightened),
            "profit_locked": bool(self.profit_locked),
            "last_bar_time": self.last_bar_time,
            "prediction_horizon": int(self.prediction_horizon),
            "price_at_prior_bar": round(float(self.price_at_prior_bar), 4),
            "ftf_stop_tightened": bool(self.ftf_stop_tightened),
            "price_two_bars_ago": round(float(self.price_two_bars_ago), 4),
            "initial_risk_at_entry": round(float(self.initial_risk_at_entry), 6),
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
        # Audit-I finding I-4 (2026-05-02): native-type casts.
        d: dict[str, Any] = {
            "should_exit": bool(self.should_exit),
            "reason": str(self.reason),
            "exit_price": round(float(self.exit_price), 4),
        }
        if self.partial_exit:
            d["partial_exit"] = True
            d["partial_pct"] = float(self.partial_pct)
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
    # Scaled for 1-min bars: original values (1.2-2.0) were designed for
    # daily ATR. With 14-period ATR on 1-min bars, those create stops
    # only a few cents away, causing ~55% stop-loss exits.
    # Multiplied ~2x to accommodate intraday noise over 15-bar horizon.
    REGIME_STOP_ATR = {
        "trending_up":   3.5,   # was 2.0 — trends need room to breathe
        "trending_down": 2.5,   # was 1.3 — still tighter than trending_up
        "chop":          2.5,   # was 1.2 — chop whipsaws need more room
        "high_vol":      4.0,   # was 2.0 — high vol = wide intraday swings
        "low_vol":       3.0,   # was 1.8 — calm but still needs room
        "stress":        2.5,   # was 1.2 — stress exits were far too tight
        "unknown":       3.0,   # was 1.5 — moderate default
    }
    # Take-profit R-multiple
    REGIME_TP_R = {
        "trending_up":   6.0,
        "trending_down": 3.0,
        "chop":          2.5,
        "high_vol":      3.0,
        "low_vol":       5.0,   # calm → bigger targets
        "stress":        2.0,
        "unknown":       4.0,
    }
    # Trail distance (ATR multiple from highest close)
    # Scaled ~2x for 1-min ATR (same rationale as REGIME_STOP_ATR)
    REGIME_TRAIL_ATR = {
        "trending_up":   5.0,   # was 3.5 — let trends run
        "trending_down": 3.5,   # was 2.0 — tighter but not whipsaw-tight
        "chop":          3.0,   # was 1.5 — chop needs room
        "high_vol":      4.5,   # was 2.5 — wide for volatility
        "low_vol":       4.5,   # was 3.0 — calm → wide trail
        "stress":        3.0,   # was 1.5 — match wider stops
        "unknown":       4.0,   # was 2.5 — moderate
    }
    # Max bars held (0 = disabled) — calibrated in 1-min bars (not 10s ticks)
    REGIME_MAX_BARS = {
        "trending_up":   0,
        "trending_down": 45,    # 45 min (was 30 ticks = 5 min)
        "chop":          30,    # 30 min (was 25 ticks = 4.2 min)
        "high_vol":      45,    # 45 min (was 30 ticks = 5 min)
        "low_vol":       0,     # calm → let positions run
        "stress":        20,    # 20 min (was 20 ticks = 3.3 min)
        "unknown":       60,    # 60 min (was 40 ticks = 6.7 min)
    }
    # Time-decay start bar — calibrated in 1-min bars
    REGIME_DECAY_START = {
        "trending_up":   0,     # no decay in strong trends
        "trending_down": 30,    # 30 min (was 20 ticks = 3.3 min)
        "chop":          20,    # 20 min (was 15 ticks = 2.5 min)
        "high_vol":      30,    # 30 min (was 20 ticks = 3.3 min)
        "low_vol":       0,     # calm → no decay
        "stress":        15,    # 15 min (was 10 ticks = 1.7 min)
        "unknown":       40,    # 40 min (was 30 ticks = 5 min)
    }

    # Time-decay rate per bar (0.3%/bar instead of 1%/tick to avoid 6x over-decay)
    TIME_DECAY_RATE = 0.003

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
        max_loss_pct: float = 0.15,          # Absolute safety net
        profit_lock_r: float = 2.0,          # Lock stop to 1R after 2R move
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
        self.max_loss_pct = max_loss_pct
        self.profit_lock_r = profit_lock_r

        # Base values for evolution scaling — evolution multiplies these
        self._base_atr_multiplier = atr_multiplier
        self._base_trailing_start_atr = trailing_start_atr
        self._base_trailing_distance_atr = trailing_distance_atr
        self._base_partial_tp_r = partial_tp_r
        self._base_profit_lock_r = profit_lock_r

        # improve9: Learning-mode flag — controls horizon timeout and
        # partial TP disable. Set by live_engine before each tick.
        self.learning_mode: bool = False

    @classmethod
    def for_timeframe(cls, timeframe: str) -> "AdaptiveExitEngine":
        """Factory that returns an exit engine tuned for the given bar timeframe.

        Audit 2026-06-09 (plan 3.1): key exit parameters are
        env-overridable so the exit-logic A/B experiment can vary them
        per-arm (subprocess + env) without code edits. Defaults unchanged.
        Live trade data motivated this: active exits (stop/trail/FTF) lost
        −$1,115 while passive exits made +$739, and 63% of trades that
        reached positive MFE still closed red.
        """
        import os

        def _f(name: str, default: float) -> float:
            try:
                return float(os.getenv(name, default))
            except (TypeError, ValueError):
                return default

        def _i(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, default))
            except (TypeError, ValueError):
                return default

        is_intraday = timeframe in ("1Min", "5Min", "15Min", "1Hour")
        if is_intraday:
            engine = cls(
                atr_multiplier=_f("ORGANISM_EXIT_ATR_MULT", 1.0),
                profit_r_multiple=_f("ORGANISM_EXIT_PROFIT_R", 3.0),
                trailing_start_atr=_f("ORGANISM_EXIT_TRAIL_START_ATR", 2.0),
                trailing_distance_atr=_f("ORGANISM_EXIT_TRAIL_DIST_ATR", 1.5),
                max_bars_held=_i("ORGANISM_EXIT_MAX_BARS", 60),
                time_decay_start=_i("ORGANISM_EXIT_DECAY_START", 40),
                partial_tp_r=_f("ORGANISM_EXIT_PARTIAL_TP_R", 3.0),
                partial_tp_pct=_f("ORGANISM_EXIT_PARTIAL_TP_PCT", 0.20),
                max_loss_pct=0.08,
                profit_lock_r=_f("ORGANISM_EXIT_PROFIT_LOCK_R", 2.0),
            )
        else:  # daily
            engine = cls(
                atr_multiplier=_f("ORGANISM_EXIT_ATR_MULT", 1.5),
                profit_r_multiple=_f("ORGANISM_EXIT_PROFIT_R", 4.0),
                trailing_start_atr=_f("ORGANISM_EXIT_TRAIL_START_ATR", 2.0),
                trailing_distance_atr=_f("ORGANISM_EXIT_TRAIL_DIST_ATR", 2.5),
                max_bars_held=_i("ORGANISM_EXIT_MAX_BARS", 40),
                time_decay_start=_i("ORGANISM_EXIT_DECAY_START", 30),
                partial_tp_r=_f("ORGANISM_EXIT_PARTIAL_TP_R", 3.0),
                partial_tp_pct=_f("ORGANISM_EXIT_PARTIAL_TP_PCT", 0.25),
                max_loss_pct=0.08,
                profit_lock_r=_f("ORGANISM_EXIT_PROFIT_LOCK_R", 2.0),
            )
        cls._apply_regime_env_overrides(engine)
        return engine

    @staticmethod
    def _apply_regime_env_overrides(engine: "AdaptiveExitEngine") -> None:
        """Audit 2026-06-09 Task B: scale the per-regime exit dicts by env
        multipliers, as INSTANCE copies.

        Root cause this fixes: the scalar ``ORGANISM_EXIT_*`` overrides (read
        in ``for_timeframe``) only set the fallback scalars
        (``self.atr_multiplier`` etc.), which are never reached because the
        engine selects via ``self.REGIME_*.get(regime, scalar)`` and every
        regime — including ``chop`` — has a dict entry. Replay windows are
        ~100% chop, so the scalar knobs never bind (``wide_exits`` was
        byte-identical to ``baseline``). These multipliers scale the dicts
        themselves.

        All multipliers default to 1.0 ⇒ env-unset behavior is byte-identical,
        and the class dicts are never mutated (instance copies only), so the
        replay-immutability guard holds.
        """
        import os

        def _mult(name: str) -> float:
            try:
                return float(os.getenv(name, 1.0))
            except (TypeError, ValueError):
                return 1.0

        stop_m = _mult("ORGANISM_EXIT_STOP_ATR_MULT")
        trail_m = _mult("ORGANISM_EXIT_TRAIL_ATR_MULT")
        bars_m = _mult("ORGANISM_EXIT_MAX_BARS_MULT")
        decay_m = _mult("ORGANISM_EXIT_DECAY_START_MULT")

        if stop_m != 1.0:
            engine.REGIME_STOP_ATR = {
                k: v * stop_m for k, v in engine.REGIME_STOP_ATR.items()
            }
        if trail_m != 1.0:
            engine.REGIME_TRAIL_ATR = {
                k: v * trail_m for k, v in engine.REGIME_TRAIL_ATR.items()
            }
        if bars_m != 1.0:
            # 0 = "no time limit" must stay 0; round to whole bars.
            engine.REGIME_MAX_BARS = {
                k: int(round(v * bars_m)) for k, v in engine.REGIME_MAX_BARS.items()
            }
        if decay_m != 1.0:
            engine.REGIME_DECAY_START = {
                k: int(round(v * decay_m)) for k, v in engine.REGIME_DECAY_START.items()
            }

    # ── public API ────────────────────────────────────────────────────────

    def create_exit_levels(
        self,
        symbol: str,
        direction: float,
        entry_price: float,
        predicted_return: float,
        features_df: pd.DataFrame,
        regime: str = "unknown",
        prediction_horizon: int = 15,
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
        prediction_horizon : ML prediction horizon in bars
        """
        atr = self._compute_atr(features_df, period=14)
        if atr < 1e-6 or np.isnan(atr):
            atr = entry_price * 0.02  # 2 % fallback

        # V11 prep / Wave-60 (DD4-3 closure): use symbol-aware effective
        # regime so SH/PSQ/DOG/RWM get the flipped-regime stop math
        # instead of un-flipped market regime (which produced too-wide
        # stops on inverse-ETF longs in trending_up = "favourable for
        # short" markets).
        from backend.organism.regime import effective_regime_for_symbol
        _eff_regime = effective_regime_for_symbol(regime, symbol)

        # Regime-adjusted stop distance
        stop_atr_mult = self.REGIME_STOP_ATR.get(_eff_regime, self.atr_multiplier)
        risk_distance = atr * stop_atr_mult

        # Regime-adjusted R-multiple for full TP
        tp_r = self.REGIME_TP_R.get(_eff_regime, self.profit_r_multiple)

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
            prediction_horizon=prediction_horizon,
            initial_risk_at_entry=risk_distance,
        )

    def update_levels_for_pyramid(
        self,
        levels: ExitLevels,
        new_avg_entry: float,
        regime: str = "unknown",
    ) -> None:
        """Recalculate exit levels after a pyramid add.

        Re-anchors stop_loss (only tightens via max for longs / min for
        shorts), take_profit, and partial_tp_price from the new weighted
        average entry.  Preserves trailing state and flags.
        """
        atr = levels.atr_at_entry
        if atr < 1e-6:
            return

        stop_atr_mult = self.REGIME_STOP_ATR.get(regime, self.atr_multiplier)
        tp_r = self.REGIME_TP_R.get(regime, self.profit_r_multiple)
        risk_distance = atr * stop_atr_mult

        if levels.direction > 0:
            new_stop = new_avg_entry - risk_distance
            # Only tighten (raise) the stop — never loosen it
            levels.stop_loss = max(levels.stop_loss, new_stop)
            levels.take_profit = new_avg_entry + risk_distance * tp_r
            levels.partial_tp_price = new_avg_entry + risk_distance * self.partial_tp_r
        else:
            new_stop = new_avg_entry + risk_distance
            levels.stop_loss = min(levels.stop_loss, new_stop)
            levels.take_profit = new_avg_entry - risk_distance * tp_r
            levels.partial_tp_price = new_avg_entry - risk_distance * self.partial_tp_r

        levels.entry_price = new_avg_entry

    @staticmethod
    def _min_hold_bars(prediction_horizon: int) -> int:
        """Dynamic minimum hold: H//3 bars, floor 3."""
        return max(prediction_horizon // 3, 3)

    def check_exit(
        self,
        levels: ExitLevels,
        current_price: float,
        current_regime: str = "unknown",
        is_new_bar: bool = True,
    ) -> ExitSignal:
        """Check if any exit condition is triggered.

        Parameters
        ----------
        levels : current ExitLevels (will be mutated for trailing updates)
        current_price : latest price
        current_regime : current regime (for dynamic adjustments)
        is_new_bar : True when a new 1-min bar boundary has been detected.
            Risk checks (max_loss, stop_loss) run every tick.
            Time/profit exits only run on new bars.

        Returns
        -------
        ExitSignal with should_exit flag and reason.
        """
        direction = levels.direction

        # ── ALWAYS (every 10s tick): update tracking + risk checks ──

        # Update highest favorable price
        if direction > 0:
            levels.highest_favorable = max(levels.highest_favorable, current_price)
        else:
            if levels.highest_favorable == levels.entry_price:
                levels.highest_favorable = current_price
            levels.highest_favorable = min(levels.highest_favorable, current_price)

        # Audit 2026-06-11: track worst ADVERSE price (real MAE source).
        if levels.worst_adverse <= 0:
            levels.worst_adverse = current_price
        elif direction > 0:
            levels.worst_adverse = min(levels.worst_adverse, current_price)
        else:
            levels.worst_adverse = max(levels.worst_adverse, current_price)

        # 0. ABSOLUTE MAX LOSS — safety net regardless of ATR calculations.
        if levels.entry_price > 0:
            pnl_pct = (current_price - levels.entry_price) / levels.entry_price * direction
            if pnl_pct <= -self.max_loss_pct:
                return ExitSignal(True, "max_loss_limit", current_price)

        # 1. Hard stop-loss check — always active
        if direction > 0 and current_price <= levels.stop_loss:
            return ExitSignal(True, "stop_loss", levels.stop_loss)
        if direction < 0 and current_price >= levels.stop_loss:
            return ExitSignal(True, "stop_loss", levels.stop_loss)

        # ── Sub-tick fast path: skip time/profit exits until next bar ──
        if not is_new_bar:
            return ExitSignal(False)

        # ── NEW BAR: advance bars_held, update prior-bar price tracker ──
        _prev_price = levels.price_at_prior_bar
        _two_bars_ago = levels.price_two_bars_ago
        levels.price_two_bars_ago = _prev_price  # shift window
        levels.price_at_prior_bar = current_price
        levels.bars_held += 1

        # 1a. MINIMUM HOLD TIME — all profit exits require minimum bars held.
        # Stop-loss (priority 1) and max_loss (priority 0) remain always active.
        min_hold = self._min_hold_bars(levels.prediction_horizon)
        if levels.bars_held < min_hold:
            return ExitSignal(False)

        # 1.5. PROFIT LOCK — at 2R, move stop to 1R (one-shot).
        # Disabled in learning mode: profit lock tightens stops early,
        # clipping winners before the 18-bar thesis horizon plays out.
        # Learning-mode exit stack: hard stop → max-loss → trailing →
        # FTF → horizon_timeout → EOD flatten. No profit lock, partial TP,
        # or full TP.
        if not self.learning_mode:
            self._check_profit_lock(levels, current_price)

        # 2. Partial take-profit at 3R (sell 30 %, let rest ride)
        # improve9 A4: Disabled in learning mode — stops clipping
        # already-too-small winners before thesis fully expresses.
        if not self.learning_mode:
            partial_signal = self._check_partial_tp(levels, current_price)
            if partial_signal.should_exit:
                return partial_signal

        # 3. Full take-profit check
        # Disabled in learning mode: same rationale as profit lock and
        # partial TP -- learning-mode trades must run to horizon_timeout
        # so the thesis expresses fully, giving clean fitness signal.
        if not self.learning_mode:
            if direction > 0 and current_price >= levels.take_profit:
                return ExitSignal(True, "take_profit", levels.take_profit)
            if direction < 0 and current_price <= levels.take_profit:
                return ExitSignal(True, "take_profit", levels.take_profit)

        # 4. ATR-based trailing stop update and check
        trail_signal = self._update_trailing_stop(levels, current_price, current_regime)
        if trail_signal.should_exit:
            return trail_signal

        # 4b. Failure to follow through — horizon-delay + regime-dependent R.
        # Disabled for trending_up, low_vol, and high_vol — let winners run.
        # Skip when trailing is active (trailing governs once activated).
        # v4 (improve7): In chop, FTF only exits losers with confirmed
        # multi-bar negative momentum. Winners get stop tightened instead.
        max_bars = self.REGIME_MAX_BARS.get(current_regime, self.max_bars_held)
        _FTF_DISABLED_REGIMES = {"trending_up", "low_vol", "high_vol"}
        if current_regime not in _FTF_DISABLED_REGIMES and not levels.trailing_active:
            # In chop, use longer delay (~prediction horizon) to give
            # the thesis time to play out. Other regimes: H//2.
            if current_regime == "chop":
                early_check = max(levels.prediction_horizon * 4 // 5, 5)  # ~12 bars for H=15
            else:
                early_check = max(levels.prediction_horizon // 2, 3)
            if levels.bars_held >= early_check:
                pnl_dir = (current_price - levels.entry_price) * direction
                initial_risk = levels.initial_risk_at_entry if levels.initial_risk_at_entry > 0 else max(abs(levels.entry_price - levels.stop_loss), 0.01)
                r_achieved = pnl_dir / initial_risk
                # Regime-dependent R threshold
                _FTF_R_THRESHOLDS = {
                    "chop": 0.15,
                    "stress": 0.10,
                    "trending_down": 0.25, "unknown": 0.25,
                }
                r_threshold = _FTF_R_THRESHOLDS.get(current_regime, 0.25)
                # Multi-bar momentum confirmation: negative momentum over
                # BOTH prior bars (not just one) to avoid noise exits.
                _has_momentum = (
                    _prev_price > 0
                    and (current_price - _prev_price) * direction > 0
                )
                _multi_bar_neg_momentum = (
                    _prev_price > 0
                    and _two_bars_ago > 0
                    and (current_price - _prev_price) * direction <= 0
                    and (_prev_price - _two_bars_ago) * direction <= 0
                )

                if r_achieved < r_threshold:
                    if current_regime == "chop":
                        # Chop-specific FTF: only exit if LOSING + multi-bar
                        # negative momentum. Winners get stop tightened.
                        if pnl_dir <= 0 and _multi_bar_neg_momentum:
                            return ExitSignal(True, "failure_to_follow", current_price)
                        elif pnl_dir > 0 and not levels.ftf_stop_tightened:
                            # Tighten stop instead of exiting — preserve
                            # the chance for the trade to reach trailing/TP.
                            self._ftf_tighten_stop(levels, current_price)
                            levels.ftf_stop_tightened = True
                        # else: already tightened or losing without momentum → hold
                    else:
                        # Non-chop regimes: original FTF logic with momentum
                        if not _has_momentum:
                            return ExitSignal(True, "failure_to_follow", current_price)

        # 4c. HORIZON TIMEOUT — learning-mode hard barrier at thesis horizon.
        # Placed after trailing/FTF so those exits take priority when active.
        # If neither trailing nor FTF fires by bar 18, horizon forces exit.
        _HORIZON_TIMEOUT_BARS = 18
        if self.learning_mode and levels.bars_held >= _HORIZON_TIMEOUT_BARS:
            return ExitSignal(True, "horizon_timeout", current_price)

        # 5. Time-based exit (regime-adaptive — disabled in trending)
        if max_bars > 0 and levels.bars_held >= max_bars:
            # Only force exit if position is in profit — give losers more room
            # to recover rather than locking in a loss at time limit
            pnl_dir = (current_price - levels.entry_price) * direction
            if pnl_dir > 0:
                return ExitSignal(True, "max_holding_period", current_price)

        # 5b. Loser time-stop — losers get 1.5× max_bars then forced exit.
        # For ∞ regimes (trending_up/low_vol), use a universal cap (120 bars = 2 hrs)
        _LOSER_MAX_FALLBACK = 120  # 2 hours at 1-min bars
        loser_ref = max_bars if max_bars > 0 else _LOSER_MAX_FALLBACK
        loser_max = int(loser_ref * 1.5)
        if levels.bars_held >= loser_max:
            pnl_dir = (current_price - levels.entry_price) * direction
            if pnl_dir <= 0:
                return ExitSignal(True, "loser_time_stop", current_price)

        # 6. Time decay — 0.3% per bar (was 1%/tick — 6x too fast)
        decay_start = self.REGIME_DECAY_START.get(current_regime, self.time_decay_start)
        if decay_start > 0 and levels.bars_held >= decay_start:
            self._apply_time_decay(levels, decay_start)

        # 7. Regime change — if regime went to stress/crisis, tighten ONCE
        if (
            not levels.stress_tightened
            and current_regime == "stress"
            and levels.regime_at_entry != "stress"
        ):
            self._tighten_for_stress(levels, current_price)
            levels.stress_tightened = True

        return ExitSignal(False)

    # ── private helpers ───────────────────────────────────────────────────

    def _ftf_tighten_stop(self, levels: ExitLevels, current_price: float) -> None:
        """FTF stop tighten in chop: move stop to halfway between entry and current.

        This preserves winning positions while reducing downside risk,
        converting FTF from an exit event to a risk-management modifier.
        """
        direction = levels.direction
        if direction > 0:
            # Tighten stop to midpoint between entry and current price
            new_stop = (levels.entry_price + current_price) / 2
            levels.stop_loss = max(levels.stop_loss, new_stop)
        else:
            new_stop = (levels.entry_price + current_price) / 2
            levels.stop_loss = min(levels.stop_loss, new_stop)

    def _check_profit_lock(self, levels: ExitLevels, current_price: float) -> None:
        """At 2R favorable move, lock stop to 1R profit (one-shot)."""
        if levels.profit_locked or self.profit_lock_r <= 0:
            return
        direction = levels.direction
        atr = levels.atr_at_entry
        if atr < 1e-6:
            return
        stop_atr_mult = self.REGIME_STOP_ATR.get(levels.regime_at_entry, self.atr_multiplier)
        initial_risk = atr * stop_atr_mult
        favorable_move = (current_price - levels.entry_price) * direction
        if favorable_move >= initial_risk * self.profit_lock_r:
            new_stop = levels.entry_price + initial_risk * direction
            if direction > 0:
                levels.stop_loss = max(levels.stop_loss, new_stop)
            else:
                levels.stop_loss = min(levels.stop_loss, new_stop)
            levels.profit_locked = True

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
            # After partial TP, move stop to at least breakeven
            # (never downgrade an existing profit lock)
            breakeven = levels.entry_price
            if direction > 0:
                levels.stop_loss = max(levels.stop_loss, breakeven)
            else:
                levels.stop_loss = min(levels.stop_loss, breakeven)
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
        current_regime: str = "unknown",
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
        # EXPERIMENT 4: In chop, widen trailing stop to reduce giveback.
        # Giveback analysis (Apr 7-13) shows trailing_stop has the worst
        # avg giveback ($10.17/trade), with one NVDA trade giving back
        # $13.81 of MFE. The 3.0× ATR trail distance in chop is too
        # tight — normal chop oscillation routinely retraces 3× ATR.
        #
        # Variant A: widen to 5.0× ATR in chop
        # Variant B: disable trailing entirely in chop (rely on timeout)
        # Active variant controlled by _EXP4_CHOP_TRAIL_MODE:
        #   "widen" = Variant A (default)
        #   "disable" = Variant B
        _EXP4_CHOP_TRAIL_MODE = "widen"  # "widen" or "disable"
        _EXP4_CHOP_TRAIL_ATR = 5.0       # Variant A trail distance

        if current_regime == "chop":
            if _EXP4_CHOP_TRAIL_MODE == "disable":
                # Variant B: skip trailing entirely in chop
                import logging as _lg
                _lg.getLogger(__name__).debug(
                    "Exp4: trailing_stop disabled in chop for %s "
                    "(excursion=%.1f ATR, mode=disable)",
                    getattr(levels, 'symbol', '?'), excursion_atr,
                )
                return ExitSignal(False)
            else:
                # Variant A: widened trail
                trail_atr = _EXP4_CHOP_TRAIL_ATR
                import logging as _lg
                _lg.getLogger(__name__).debug(
                    "Exp4: trailing_stop widened in chop for %s "
                    "(excursion=%.1f ATR, trail=%.1f ATR, mode=widen)",
                    getattr(levels, 'symbol', '?'), excursion_atr, trail_atr,
                )
        else:
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
        """Gentle stop tightening — 0.3% per bar (was 1%/tick — 6x too fast)."""
        decay_bars = levels.bars_held - decay_start
        decay_factor = 1.0 - decay_bars * self.TIME_DECAY_RATE
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
