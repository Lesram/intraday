"""
Module 8 — Self-Evolution Engine.

The organism's meta-learning brain: after every epoch (or every N trades),
analyses what worked vs. what didn't, and **adapts every tunable parameter**
of the trading system so the next epoch performs better.

This is NOT periodic refitting of the same model — this is genuine
self-evolution where the *strategy itself* changes:

    1. SIGNAL WEIGHTS    — which signals (ML, breakout, volume, momentum, regime)
                           actually predict profitable trades?  Re-weight.
    2. EXIT PARAMETERS   — are stops too tight?  trailing too close?
                           partial TP at wrong level?  Tune from outcomes.
    3. POSITION SIZING   — which regimes are actually profitable?
                           Scale up in good regimes, scale down in bad.
    4. FEATURE SELECTION — which features have real predictive power?
                           Prune weak features, boost strong ones.
    5. SYMBOL FITNESS    — which symbols are we good at trading?
                           Allocate more to winners, less to losers.
    6. ENTRY THRESHOLDS  — is 0.55 the right confidence threshold?
                           Calibrate from hit rate data.
    7. BREAKOUT WEIGHTS  — which breakout detectors predict real moves?

All adaptation uses EMA smoothing (alpha=0.3) to prevent overfitting
to recent noise.  Parameters shift by at most 20 % per epoch — evolution
is gradual, not revolutionary.

Persistence: EvolvedParams serialises to/from dict for brain persistence.

Ref: docs/blueprints/SELF_LEARNING_ORGANISM_BLUEPRINT.md §4
"""

from __future__ import annotations

import logging
import math
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── EMA smoothing factor (higher = faster adaptation, more noise) ────
DEFAULT_ALPHA = 0.30
# ── Max parameter shift per epoch (safety clamp) ─────────────────────
MAX_SHIFT_PCT = 0.20
# ── Minimum trades needed before adapting a parameter ────────────────
MIN_TRADES_FOR_ADAPTATION = 8


# ═════════════════════════════════════════════════════════════════
#  Evolved Parameters
# ═════════════════════════════════════════════════════════════════

@dataclass
class EvolvedParams:
    """Every learnable parameter in the organism.

    Defaults = conservative starting point.  The EvolutionEngine updates
    these from trade outcome evidence.
    """

    # ── Alpha scanner signal weights (must sum to ~1.0) ──────────
    alpha_weight_ml: float = 0.35
    alpha_weight_volume: float = 0.20
    alpha_weight_momentum: float = 0.20
    alpha_weight_breakout: float = 0.15
    alpha_weight_regime: float = 0.10

    # ── ML signal direction thresholds ───────────────────────────
    direction_threshold_buy: float = 0.55
    direction_threshold_sell: float = 0.45

    # ── Exit parameter multipliers (applied on top of defaults) ──
    stop_atr_scale: float = 1.0           # scale on base stop distance
    trailing_start_atr_scale: float = 1.0  # scale on trailing activation
    trailing_distance_scale: float = 1.0   # scale on trailing distance
    partial_tp_r_scale: float = 1.0        # scale on partial TP R-multiple
    partial_tp_pct: float = 0.30           # fraction to sell at partial TP

    # ── Regime-specific position sizing scales ───────────────────
    regime_size_scales: dict[str, float] = field(default_factory=lambda: {
        "trending_up": 1.20,
        "trending": 1.00,
        "normal": 0.85,
        "trending_down": 0.60,
        "chop": 0.50,
        "high_vol": 0.70,      # was 0.40 — too conservative for intraday
        "stress": 0.30,        # was 0.20
        "crisis": 0.10,
    })

    # ── Feature importance weights (1.0 = keep, 0.0 = drop) ─────
    feature_weights: dict[str, float] = field(default_factory=dict)

    # ── Symbol fitness scores (higher = allocate more) ───────────
    symbol_fitness: dict[str, float] = field(default_factory=dict)

    # ── Breakout scanner weights ─────────────────────────────────
    breakout_weight_squeeze: float = 0.25
    breakout_weight_volume: float = 0.25
    breakout_weight_contraction: float = 0.15
    breakout_weight_rs: float = 0.15
    breakout_weight_pivot: float = 0.15
    breakout_weight_flow: float = 0.05

    # ── Breakout indicator periods (Phase 3.8) ───────────────────
    breakout_bb_period: int = 20          # Bollinger Band lookback
    breakout_atr_short: int = 10          # ATR short window
    breakout_atr_long: int = 50           # ATR long window
    breakout_pivot_lookback: int = 20     # Pivot high/low lookback
    breakout_vol_avg_period: int = 20     # Volume average lookback
    breakout_rs_period: int = 20          # Relative-strength lookback

    # ── Short-side control (Phase 4.5) ───────────────────────────
    shorts_enabled: bool = False          # starts disabled — must prove profitable
    short_win_rate: float = 0.0           # tracked EMA of short-trade win rate
    short_avg_pnl: float = 0.0           # tracked EMA of short-trade avg PnL
    short_trade_count: int = 0            # cumulative short trades observed

    # ── XGBoost hyperparameters (Phase 4.6) ──────────────────────
    xgb_n_estimators: int = 200
    xgb_max_depth: int = 5
    xgb_learning_rate: float = 0.05
    xgb_subsample: float = 0.80
    xgb_colsample_bytree: float = 0.80

    # ── Metadata ─────────────────────────────────────────────────
    evolution_generation: int = 0
    total_adaptations: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise for brain persistence."""
        return {
            "alpha_weight_ml": round(self.alpha_weight_ml, 4),
            "alpha_weight_volume": round(self.alpha_weight_volume, 4),
            "alpha_weight_momentum": round(self.alpha_weight_momentum, 4),
            "alpha_weight_breakout": round(self.alpha_weight_breakout, 4),
            "alpha_weight_regime": round(self.alpha_weight_regime, 4),
            "direction_threshold_buy": round(self.direction_threshold_buy, 4),
            "direction_threshold_sell": round(self.direction_threshold_sell, 4),
            "stop_atr_scale": round(self.stop_atr_scale, 4),
            "trailing_start_atr_scale": round(self.trailing_start_atr_scale, 4),
            "trailing_distance_scale": round(self.trailing_distance_scale, 4),
            "partial_tp_r_scale": round(self.partial_tp_r_scale, 4),
            "partial_tp_pct": round(self.partial_tp_pct, 4),
            "regime_size_scales": {
                k: round(v, 4) for k, v in self.regime_size_scales.items()
            },
            "feature_weights": {
                k: round(v, 4) for k, v in self.feature_weights.items()
            },
            "symbol_fitness": {
                k: round(v, 4) for k, v in self.symbol_fitness.items()
            },
            "breakout_weight_squeeze": round(self.breakout_weight_squeeze, 4),
            "breakout_weight_volume": round(self.breakout_weight_volume, 4),
            "breakout_weight_contraction": round(self.breakout_weight_contraction, 4),
            "breakout_weight_rs": round(self.breakout_weight_rs, 4),
            "breakout_weight_pivot": round(self.breakout_weight_pivot, 4),
            "breakout_weight_flow": round(self.breakout_weight_flow, 4),
            "breakout_bb_period": self.breakout_bb_period,
            "breakout_atr_short": self.breakout_atr_short,
            "breakout_atr_long": self.breakout_atr_long,
            "breakout_pivot_lookback": self.breakout_pivot_lookback,
            "breakout_vol_avg_period": self.breakout_vol_avg_period,
            "breakout_rs_period": self.breakout_rs_period,
            "shorts_enabled": self.shorts_enabled,
            "short_win_rate": round(self.short_win_rate, 4),
            "short_avg_pnl": round(self.short_avg_pnl, 2),
            "short_trade_count": self.short_trade_count,
            "xgb_n_estimators": self.xgb_n_estimators,
            "xgb_max_depth": self.xgb_max_depth,
            "xgb_learning_rate": round(self.xgb_learning_rate, 6),
            "xgb_subsample": round(self.xgb_subsample, 4),
            "xgb_colsample_bytree": round(self.xgb_colsample_bytree, 4),
            "evolution_generation": self.evolution_generation,
            "total_adaptations": self.total_adaptations,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvolvedParams":
        """Restore from brain persistence."""
        params = cls()
        for key in [
            "alpha_weight_ml", "alpha_weight_volume", "alpha_weight_momentum",
            "alpha_weight_breakout", "alpha_weight_regime",
            "direction_threshold_buy", "direction_threshold_sell",
            "stop_atr_scale", "trailing_start_atr_scale",
            "trailing_distance_scale", "partial_tp_r_scale", "partial_tp_pct",
            "breakout_weight_squeeze", "breakout_weight_volume",
            "breakout_weight_contraction", "breakout_weight_rs",
            "breakout_weight_pivot", "breakout_weight_flow",
            "breakout_bb_period", "breakout_atr_short",
            "breakout_atr_long", "breakout_pivot_lookback",
            "breakout_vol_avg_period", "breakout_rs_period",
            "shorts_enabled", "short_win_rate", "short_avg_pnl",
            "short_trade_count",
            "xgb_n_estimators", "xgb_max_depth", "xgb_learning_rate",
            "xgb_subsample", "xgb_colsample_bytree",
            "evolution_generation", "total_adaptations",
        ]:
            if key in d:
                setattr(params, key, d[key])
        if "regime_size_scales" in d and isinstance(d["regime_size_scales"], dict):
            params.regime_size_scales.update(d["regime_size_scales"])
        if "feature_weights" in d and isinstance(d["feature_weights"], dict):
            params.feature_weights = d["feature_weights"]
        if "symbol_fitness" in d and isinstance(d["symbol_fitness"], dict):
            params.symbol_fitness = d["symbol_fitness"]
        return params

    def get_selected_features(self, all_features: list[str]) -> list[str]:
        """Return features that pass the selection threshold (weight >= 0.2).

        If no weights are stored yet (first run), return all features.
        """
        if not self.feature_weights:
            return list(all_features)
        selected = [
            f for f in all_features
            if self.feature_weights.get(f, 1.0) >= 0.20
        ]
        # Safety: never drop below 15 features
        if len(selected) < 15:
            # Fallback: keep top 30 by weight
            ranked = sorted(
                all_features,
                key=lambda f: self.feature_weights.get(f, 1.0),
                reverse=True,
            )
            return ranked[:30]
        return selected


# ═════════════════════════════════════════════════════════════════
#  Evolution Engine
# ═════════════════════════════════════════════════════════════════

class EvolutionEngine:
    """Bayesian-style parameter evolution from trade outcomes.

    After each epoch, call ``evolve()`` with recent trade data.
    The engine analyses outcomes and returns an updated
    :class:`EvolvedParams` for the next epoch.

    All updates use **EMA smoothing** and **clamp** to prevent
    wild swings.  Evolution is *gradual*, not revolutionary.

    Usage::

        evo = EvolutionEngine()
        params = EvolvedParams()          # or restore from brain

        for epoch in range(N):
            # ... run trading epoch ...
            params = evo.evolve(
                params, trades, feature_importances, epoch_pnl, regime
            )
            apply_params(params, scanner, sizer, exits, signal_gen)
    """

    def __init__(
        self,
        alpha: float = DEFAULT_ALPHA,
        max_shift: float = MAX_SHIFT_PCT,
        min_trades: int = MIN_TRADES_FOR_ADAPTATION,
    ):
        self.alpha = alpha
        self.max_shift = max_shift
        self.min_trades = min_trades
        self._evolution_log: list[dict[str, Any]] = []

    @property
    def log(self) -> list[dict[str, Any]]:
        """History of evolution steps for diagnostics."""
        return self._evolution_log

    def evolve(
        self,
        params: EvolvedParams,
        trades: list[Any],
        feature_importances: dict[str, float] | None = None,
        epoch_regime: str = "normal",
        all_feature_names: list[str] | None = None,
    ) -> EvolvedParams:
        """Run one evolution step.  Returns updated EvolvedParams.

        Parameters
        ----------
        params : current EvolvedParams
        trades : list of TradeRecord from the completed epoch
        feature_importances : {feature: importance} from the latest ML model
        epoch_regime : dominant regime during this epoch
        all_feature_names : canonical feature list for selection
        """
        if len(trades) < self.min_trades:
            logger.info(
                "Evolution skipped: only %d trades (need %d)",
                len(trades), self.min_trades,
            )
            return params

        new_params = deepcopy(params)
        new_params.evolution_generation += 1
        changes: dict[str, str] = {}

        # ── 1. Signal weight adaptation ──────────────────────────
        self._evolve_signal_weights(new_params, trades, changes)

        # ── 2. Exit parameter tuning ─────────────────────────────
        self._evolve_exit_params(new_params, trades, changes)

        # ── 3. Regime-size scaling ───────────────────────────────
        self._evolve_regime_scales(new_params, trades, epoch_regime, changes)

        # ── 4. Feature selection / weighting ─────────────────────
        if feature_importances and all_feature_names:
            self._evolve_feature_weights(
                new_params, trades, feature_importances,
                all_feature_names, changes,
            )

        # ── 5. Symbol fitness ────────────────────────────────────
        self._evolve_symbol_fitness(new_params, trades, changes)

        # ── 6. Direction threshold calibration ───────────────────
        self._evolve_direction_thresholds(new_params, trades, changes)

        # ── 7. Breakout weight adaptation ────────────────────────
        self._evolve_breakout_weights(new_params, trades, changes)

        # ── 8. Breakout indicator period adaptation ──────────────
        self._evolve_breakout_periods(new_params, trades, changes)
        # ── 9. Short-side resurrection (Phase 4.5) ──────────────
        self._evolve_short_side(new_params, trades, changes)

        # ── 10. XGBoost hyperparameter evolution (Phase 4.6) ────
        self._evolve_xgb_hyperparams(new_params, trades, changes)

        new_params.total_adaptations += 1

        # Log
        log_entry = {
            "generation": new_params.evolution_generation,
            "trades_analysed": len(trades),
            "regime": epoch_regime,
            "changes": changes,
        }
        self._evolution_log.append(log_entry)
        logger.info(
            "Evolution gen %d: %d changes from %d trades",
            new_params.evolution_generation,
            len(changes),
            len(trades),
        )

        return new_params

    # ═════════════════════════════════════════════════════════════
    #   1. SIGNAL WEIGHT ADAPTATION
    # ═════════════════════════════════════════════════════════════

    def _evolve_signal_weights(
        self,
        params: EvolvedParams,
        trades: list[Any],
        changes: dict[str, str],
    ) -> None:
        """Adjust alpha scanner weights based on signal attribution.

        For each trade, we check whether high-confidence signals
        (ML, breakout, volume, momentum) predicted the right direction.
        Signals that correlated with wins get more weight.
        """
        # Bucketise trades by signal present at entry
        # We use confidence ≈ breakout_score proxy plus predicted_return
        win_pnl = [t.pnl for t in trades if t.pnl > 0]
        loss_pnl = [t.pnl for t in trades if t.pnl <= 0]

        if not win_pnl and not loss_pnl:
            return

        avg_win = float(np.mean(win_pnl)) if win_pnl else 0.0
        avg_loss = float(np.mean(loss_pnl)) if loss_pnl else 0.0
        total_pnl = sum(t.pnl for t in trades)

        # Heuristic: if ML-predicted trades (high confidence) won more
        high_conf_trades = [t for t in trades if t.confidence > 0.6]
        low_conf_trades = [t for t in trades if t.confidence <= 0.6]

        high_conf_wr = (
            sum(1 for t in high_conf_trades if t.pnl > 0)
            / max(len(high_conf_trades), 1)
        )
        low_conf_wr = (
            sum(1 for t in low_conf_trades if t.pnl > 0)
            / max(len(low_conf_trades), 1)
        )

        # If high-confidence (ML-driven) trades have better win rate,
        # increase ML weight at the expense of the weakest signal
        if high_conf_wr > low_conf_wr + 0.05 and len(high_conf_trades) >= 3:
            ml_boost = min(0.05, (high_conf_wr - low_conf_wr) * 0.15)
            params.alpha_weight_ml = self._ema_update(
                params.alpha_weight_ml,
                params.alpha_weight_ml + ml_boost,
            )
            changes["alpha_weight_ml"] = f"+{ml_boost:.3f} (high-conf WR {high_conf_wr:.1%})"

        # Direction accuracy of trades → boost momentum if direction is right
        correct_dir = [t for t in trades if t.correct_direction]
        dir_accuracy = len(correct_dir) / max(len(trades), 1)

        if dir_accuracy > 0.6:
            # Momentum is working — boost it
            params.alpha_weight_momentum = self._ema_update(
                params.alpha_weight_momentum,
                min(params.alpha_weight_momentum + 0.03, 0.35),
            )
            changes["alpha_weight_momentum"] = f"boost (dir_acc={dir_accuracy:.1%})"
        elif dir_accuracy < 0.4:
            # Momentum failing — reduce it, boost mean-reversion (regime)
            params.alpha_weight_momentum = self._ema_update(
                params.alpha_weight_momentum,
                max(params.alpha_weight_momentum - 0.03, 0.05),
            )
            params.alpha_weight_regime = self._ema_update(
                params.alpha_weight_regime,
                min(params.alpha_weight_regime + 0.03, 0.25),
            )
            changes["alpha_weight_momentum"] = f"reduce (dir_acc={dir_accuracy:.1%})"

        # Normalise weights to sum to 1.0
        self._normalize_alpha_weights(params)

    # ═════════════════════════════════════════════════════════════
    #   2. EXIT PARAMETER TUNING
    # ═════════════════════════════════════════════════════════════

    def _evolve_exit_params(
        self,
        params: EvolvedParams,
        trades: list[Any],
        changes: dict[str, str],
    ) -> None:
        """Tune exit parameters from trade outcome analysis.

        Key insights we extract:
        - Too many stop_loss exits → stops too tight → widen
        - Trailing stops locking in big profits → keep or tighten trail
        - Partial TP helping? → adjust fraction
        - Time-based exits rare and profitable → no change needed
        """
        exit_reasons: dict[str, list[float]] = {}
        for t in trades:
            reason = getattr(t, "exit_reason", "unknown")
            exit_reasons.setdefault(reason, []).append(t.pnl)

        total = len(trades)
        if total < self.min_trades:
            return

        # ── Stop loss analysis ───────────────────────────────────
        sl_trades = exit_reasons.get("stop_loss", [])
        sl_pct = len(sl_trades) / total

        if sl_pct > 0.45:
            # Too many stops being hit — stops are too tight
            params.stop_atr_scale = self._ema_update(
                params.stop_atr_scale,
                min(params.stop_atr_scale * 1.10, 1.8),
            )
            changes["stop_atr_scale"] = f"widen (stop_rate={sl_pct:.1%})"
        elif sl_pct < 0.15 and len(sl_trades) >= 2:
            # Very few stops — could tighten slightly for faster loss cutting
            params.stop_atr_scale = self._ema_update(
                params.stop_atr_scale,
                max(params.stop_atr_scale * 0.95, 0.6),
            )
            changes["stop_atr_scale"] = f"tighten (stop_rate={sl_pct:.1%})"

        # ── Trailing stop analysis ───────────────────────────────
        trail_trades = exit_reasons.get("trailing_stop", [])
        if trail_trades:
            trail_avg_pnl = float(np.mean(trail_trades))
            if trail_avg_pnl > 0:
                # Trailing is profitable → maybe tighten trail to lock more
                # But if average is very high, trail is good as-is
                trail_avg_vs_all = trail_avg_pnl / max(
                    abs(float(np.mean([t.pnl for t in trades]))), 1.0
                )
                if trail_avg_vs_all > 2.0:
                    # Trail captures big winners — widen trail slightly to let
                    # even bigger moves run
                    params.trailing_distance_scale = self._ema_update(
                        params.trailing_distance_scale,
                        min(params.trailing_distance_scale * 1.05, 1.6),
                    )
                    changes["trailing_distance_scale"] = (
                        f"widen (trail avg ${trail_avg_pnl:.0f})"
                    )
            else:
                # Trail exits are actually losing money → tighten
                params.trailing_distance_scale = self._ema_update(
                    params.trailing_distance_scale,
                    max(params.trailing_distance_scale * 0.90, 0.5),
                )
                changes["trailing_distance_scale"] = (
                    f"tighten (trail avg ${trail_avg_pnl:.0f})"
                )

        # ── Partial TP analysis ──────────────────────────────────
        partial_trades = exit_reasons.get("partial_take_profit", [])
        full_tp_trades = exit_reasons.get("take_profit", [])

        if partial_trades and full_tp_trades:
            partial_avg = float(np.mean(partial_trades))
            full_avg = float(np.mean(full_tp_trades))

            # If full TP avg >> partial avg, we're selling partials too early
            if full_avg > partial_avg * 2.5 and len(full_tp_trades) >= 2:
                params.partial_tp_r_scale = self._ema_update(
                    params.partial_tp_r_scale,
                    min(params.partial_tp_r_scale * 1.10, 1.8),
                )
                params.partial_tp_pct = self._ema_update(
                    params.partial_tp_pct,
                    max(params.partial_tp_pct - 0.03, 0.15),
                )
                changes["partial_tp"] = (
                    f"delay (full_avg=${full_avg:.0f} vs partial=${partial_avg:.0f})"
                )
            elif partial_avg > full_avg * 1.5:
                # Partials are more profitable per share — sell more
                params.partial_tp_pct = self._ema_update(
                    params.partial_tp_pct,
                    min(params.partial_tp_pct + 0.03, 0.50),
                )
                changes["partial_tp"] = (
                    f"increase (partial=${partial_avg:.0f} > full=${full_avg:.0f})"
                )

    # ═════════════════════════════════════════════════════════════
    #   3. REGIME-SIZE SCALING
    # ═════════════════════════════════════════════════════════════

    def _evolve_regime_scales(
        self,
        params: EvolvedParams,
        trades: list[Any],
        epoch_regime: str,
        changes: dict[str, str],
    ) -> None:
        """Adapt sizing per regime based on actual PnL.

        If the organism is profitable in a regime → scale up.
        If losing → scale down.
        """
        if epoch_regime not in params.regime_size_scales:
            return

        epoch_pnl = sum(t.pnl for t in trades)
        n = len(trades)
        avg_pnl = epoch_pnl / max(n, 1)

        current_scale = params.regime_size_scales[epoch_regime]

        # Positive average → this regime is working, scale up (gently)
        if avg_pnl > 0:
            new_scale = min(current_scale * 1.08, 1.5)
        elif avg_pnl < 0:
            new_scale = max(current_scale * 0.90, 0.05)
        else:
            return

        params.regime_size_scales[epoch_regime] = self._ema_update(
            current_scale, new_scale,
        )
        changes[f"regime_scale_{epoch_regime}"] = (
            f"{current_scale:.2f}→{params.regime_size_scales[epoch_regime]:.2f} "
            f"(avg_pnl=${avg_pnl:.0f})"
        )

    # ═════════════════════════════════════════════════════════════
    #   4. FEATURE SELECTION / WEIGHTING
    # ═════════════════════════════════════════════════════════════

    def _evolve_feature_weights(
        self,
        params: EvolvedParams,
        trades: list[Any],
        feature_importances: dict[str, float],
        all_features: list[str],
        changes: dict[str, str],
    ) -> None:
        """Dynamic feature selection using XGBoost importance × direction accuracy.

        Features that the model considers important AND lead to correct
        direction predictions get weight boosted.  Features that are
        unimportant or misleading get weight reduced.
        """
        dir_accuracy = (
            sum(1 for t in trades if t.correct_direction) / max(len(trades), 1)
        )

        # Combine ML importance with outcome accuracy
        # If model is accurate, trust its feature importances more
        accuracy_trust = max(dir_accuracy - 0.45, 0.0) * 4.0  # [0, ~2.2]
        accuracy_trust = min(accuracy_trust, 1.0)

        updated = 0
        for feat in all_features:
            importance = feature_importances.get(feat, 0.0)
            current_weight = params.feature_weights.get(feat, 1.0)

            if importance > 0.02:
                # Feature is important to the model
                target = 1.0 + importance * accuracy_trust
            elif importance > 0.005:
                # Marginal importance
                target = 0.7 + importance * accuracy_trust
            else:
                # Very low importance — gradually reduce
                target = max(0.3, current_weight * 0.9)

            target = max(0.0, min(target, 2.0))
            new_weight = self._ema_update(current_weight, target)
            if abs(new_weight - current_weight) > 0.01:
                updated += 1
            params.feature_weights[feat] = new_weight

        if updated > 0:
            changes["feature_weights"] = f"{updated} features updated"

    # ═════════════════════════════════════════════════════════════
    #   5. SYMBOL FITNESS
    # ═════════════════════════════════════════════════════════════

    def _evolve_symbol_fitness(
        self,
        params: EvolvedParams,
        trades: list[Any],
        changes: dict[str, str],
    ) -> None:
        """Track per-symbol profitability.  Scale future allocation.

        Fitness is a rolling [0, 1] score where:
            0.5 = neutral (new/unknown)
            > 0.5 = historically profitable → allocate more
            < 0.5 = historically unprofitable → allocate less
        """
        # Group trades by symbol
        by_symbol: dict[str, list[float]] = {}
        for t in trades:
            sym = t.symbol
            by_symbol.setdefault(sym, []).append(t.pnl)

        updated = 0
        for sym, pnls in by_symbol.items():
            current = params.symbol_fitness.get(sym, 0.5)
            win_rate = sum(1 for p in pnls if p > 0) / len(pnls)
            avg_pnl = float(np.mean(pnls))

            # Fitness = sigmoid-like mapping of win_rate × avg_pnl_sign
            if avg_pnl > 0:
                target = 0.5 + min(win_rate * 0.3, 0.4)
            else:
                target = 0.5 - min((1 - win_rate) * 0.3, 0.4)

            target = max(0.1, min(target, 0.95))
            new_fitness = self._ema_update(current, target)
            if abs(new_fitness - current) > 0.01:
                updated += 1
            params.symbol_fitness[sym] = new_fitness

        if updated > 0:
            changes["symbol_fitness"] = f"{updated} symbols updated"

    # ═════════════════════════════════════════════════════════════
    #   6. DIRECTION THRESHOLD CALIBRATION
    # ═════════════════════════════════════════════════════════════

    def _evolve_direction_thresholds(
        self,
        params: EvolvedParams,
        trades: list[Any],
        changes: dict[str, str],
    ) -> None:
        """Calibrate buy/sell confidence thresholds.

        If high-confidence trades (above threshold) are frequently wrong,
        raise the threshold.  If marginal trades (near threshold) are
        often correct, lower it to capture more opportunities.
        """
        # We only have post-entry data — infer from confidence + outcome
        high_conf = [t for t in trades if t.confidence >= 0.65]
        med_conf = [t for t in trades if 0.45 <= t.confidence < 0.65]
        low_conf = [t for t in trades if t.confidence < 0.45]

        if len(high_conf) >= 3:
            high_wr = sum(1 for t in high_conf if t.pnl > 0) / len(high_conf)
            if high_wr < 0.45:
                # High confidence trades are losing — raise buy threshold
                params.direction_threshold_buy = self._ema_update(
                    params.direction_threshold_buy,
                    min(params.direction_threshold_buy + 0.02, 0.70),
                )
                changes["threshold_buy"] = (
                    f"raise (high_conf WR={high_wr:.1%})"
                )
            elif high_wr > 0.65:
                # High confidence is reliable — could lower threshold slightly
                params.direction_threshold_buy = self._ema_update(
                    params.direction_threshold_buy,
                    max(params.direction_threshold_buy - 0.01, 0.50),
                )
                changes["threshold_buy"] = (
                    f"lower (high_conf WR={high_wr:.1%})"
                )

        if len(med_conf) >= 3:
            med_wr = sum(1 for t in med_conf if t.pnl > 0) / len(med_conf)
            if med_wr > 0.55:
                # Medium confidence trades are actually winning — lower threshold
                params.direction_threshold_buy = self._ema_update(
                    params.direction_threshold_buy,
                    max(params.direction_threshold_buy - 0.015, 0.50),
                )
                changes["threshold_buy_med"] = (
                    f"lower (med_conf WR={med_wr:.1%})"
                )

        # Sell threshold: loosely coupled to buy via EMA, NOT a hard mirror.
        # This allows independent evolution while still maintaining a
        # reasonable relationship between buy and sell thresholds.
        buy = params.direction_threshold_buy
        target_sell = 1.0 - buy
        params.direction_threshold_sell = self._ema_update(
            params.direction_threshold_sell, target_sell,
        )

    # ═════════════════════════════════════════════════════════════
    #   7. BREAKOUT WEIGHT ADAPTATION
    # ═════════════════════════════════════════════════════════════

    def _evolve_breakout_weights(
        self,
        params: EvolvedParams,
        trades: list[Any],
        changes: dict[str, str],
    ) -> None:
        """Adjust breakout scanner weights based on breakout trade outcomes.

        Trades with high breakout_score that were profitable → boost
        the breakout signals.  Trades with low breakout_score that won →
        reduce over-reliance on breakout.
        """
        # We can infer breakout involvement from confidence (which is
        # boosted by breakout_score in the master script)
        high_brk = [t for t in trades if t.confidence > 0.7]
        low_brk = [t for t in trades if t.confidence <= 0.5]

        if len(high_brk) < 3:
            return

        brk_win_rate = sum(1 for t in high_brk if t.pnl > 0) / len(high_brk)
        brk_avg_pnl = float(np.mean([t.pnl for t in high_brk]))
        non_brk_avg = (
            float(np.mean([t.pnl for t in low_brk]))
            if low_brk else 0.0
        )

        if brk_avg_pnl > non_brk_avg * 1.5 and brk_win_rate > 0.5:
            # Breakout trades outperform — increase volume & squeeze weights
            params.breakout_weight_volume = self._ema_update(
                params.breakout_weight_volume,
                min(params.breakout_weight_volume + 0.02, 0.40),
            )
            params.breakout_weight_squeeze = self._ema_update(
                params.breakout_weight_squeeze,
                min(params.breakout_weight_squeeze + 0.02, 0.40),
            )
            self._normalize_breakout_weights(params)
            changes["breakout_weights"] = (
                f"boost (brk_pnl=${brk_avg_pnl:.0f} > "
                f"non_brk=${non_brk_avg:.0f})"
            )
        elif brk_avg_pnl < 0 and len(high_brk) >= 3:
            # Breakout trades losing — reduce weights
            params.breakout_weight_volume = self._ema_update(
                params.breakout_weight_volume,
                max(params.breakout_weight_volume - 0.02, 0.10),
            )
            params.breakout_weight_squeeze = self._ema_update(
                params.breakout_weight_squeeze,
                max(params.breakout_weight_squeeze - 0.02, 0.10),
            )
            self._normalize_breakout_weights(params)
            changes["breakout_weights"] = (
                f"reduce (brk_pnl=${brk_avg_pnl:.0f})"
            )

    # ═════════════════════════════════════════════════════════════
    #   8. BREAKOUT INDICATOR PERIOD ADAPTATION  (Phase 3.8)
    # ═════════════════════════════════════════════════════════════

    # Allowed period ranges (guards against nonsensical values)
    _PERIOD_BOUNDS: dict[str, tuple[int, int]] = {
        "breakout_bb_period":       (10, 40),
        "breakout_atr_short":       (5,  20),
        "breakout_atr_long":        (20, 80),
        "breakout_pivot_lookback":  (10, 40),
        "breakout_vol_avg_period":  (10, 40),
        "breakout_rs_period":       (10, 40),
    }

    def _evolve_breakout_periods(
        self,
        params: EvolvedParams,
        trades: list[Any],
        changes: dict[str, str],
    ) -> None:
        """Nudge breakout indicator periods toward more profitable settings.

        Heuristic:
        - If breakout-attributed trades are profitable on average, the
          current periods are "working" — leave them alone.
        - If they are losing, try shortening or lengthening the lookback
          slightly (±1 or ±2) to adapt to the current volatility regime.
        - High average holding-period → indicators may be too slow → shorten.
        - Very short holding-period → may be too fast → lengthen.
        """
        brk_trades = [t for t in trades if t.confidence > 0.6]
        if len(brk_trades) < 5:
            return

        avg_pnl = float(np.mean([t.pnl for t in brk_trades]))
        avg_hold = float(np.mean([
            (t.exit_bar - t.entry_bar) if t.exit_bar > t.entry_bar else 0
            for t in brk_trades
        ]))

        # Determine direction: shorten (-1) or lengthen (+1) periods
        if avg_pnl > 0:
            # Profitable — leave periods alone
            return

        # Losing money — try to adapt
        if avg_hold > 15:
            step = -1  # Indicators may be lagging → shorten
            reason = f"shorten (avg_hold={avg_hold:.0f}d, pnl=${avg_pnl:.0f})"
        elif avg_hold < 3:
            step = +1  # Too twitchy → lengthen
            reason = f"lengthen (avg_hold={avg_hold:.0f}d, pnl=${avg_pnl:.0f})"
        else:
            step = -1 if avg_pnl < -50 else +1
            reason = f"nudge (avg_pnl=${avg_pnl:.0f})"

        any_changed = False
        for attr, (lo, hi) in self._PERIOD_BOUNDS.items():
            old_val = getattr(params, attr)
            new_val = max(lo, min(old_val + step, hi))
            if new_val != old_val:
                setattr(params, attr, new_val)
                any_changed = True

        if any_changed:
            changes["breakout_periods"] = reason

    # ═════════════════════════════════════════════════════════════
    #   9. SHORT-SIDE RESURRECTION  (Phase 4.5)
    # ═════════════════════════════════════════════════════════════

    # Thresholds for enabling / disabling shorts
    _SHORT_ENABLE_WR = 0.55       # need 55% win rate on shorts to enable
    _SHORT_ENABLE_PNL = 10.0      # need avg PnL > $10 on shorts
    _SHORT_DISABLE_WR = 0.35      # disable if WR drops below 35%
    _SHORT_MIN_TRADES = 10        # minimum short trades to judge

    def _evolve_short_side(
        self,
        params: EvolvedParams,
        trades: list[Any],
        changes: dict[str, str],
    ) -> None:
        """Enable or disable short-selling based on historical performance.

        Shorts start disabled.  They are enabled only when the organism
        has accumulated enough evidence that bearish trades are profitable
        in the current regime.  They can be disabled again if performance
        degrades.
        """
        alpha = 0.3
        # Identify short-direction trades (direction == -1)
        short_trades = [
            t for t in trades
            if getattr(t, "direction", 1) < 0
            or getattr(t, "side", "") == "short"
        ]

        if not short_trades:
            return

        # Update EMA statistics
        wins = sum(1 for t in short_trades if t.pnl > 0)
        wr = wins / len(short_trades)
        avg_pnl = float(np.mean([t.pnl for t in short_trades]))

        params.short_win_rate = (1 - alpha) * params.short_win_rate + alpha * wr
        params.short_avg_pnl = (1 - alpha) * params.short_avg_pnl + alpha * avg_pnl
        params.short_trade_count += len(short_trades)

        # Decision: enable or disable
        if params.short_trade_count < self._SHORT_MIN_TRADES:
            return  # Not enough data

        if not params.shorts_enabled:
            # Check if we should enable
            if (
                params.short_win_rate >= self._SHORT_ENABLE_WR
                and params.short_avg_pnl >= self._SHORT_ENABLE_PNL
            ):
                params.shorts_enabled = True
                changes["shorts_enabled"] = (
                    f"ENABLED (WR={params.short_win_rate:.1%}, "
                    f"avg_pnl=${params.short_avg_pnl:.0f})"
                )
                logger.info("Short-side ENABLED by evolution engine")
        else:
            # Check if we should disable
            if params.short_win_rate < self._SHORT_DISABLE_WR:
                params.shorts_enabled = False
                changes["shorts_enabled"] = (
                    f"DISABLED (WR={params.short_win_rate:.1%})"
                )
                logger.info("Short-side DISABLED by evolution engine")

    # ═════════════════════════════════════════════════════════════
    #   10. XGB HYPERPARAMETER EVOLUTION  (Phase 4.6)
    # ═════════════════════════════════════════════════════════════

    # Hyperparameter bounds: (min, max)
    _XGB_BOUNDS: dict[str, tuple[float, float]] = {
        "xgb_n_estimators": (100, 500),
        "xgb_max_depth": (3, 8),
        "xgb_learning_rate": (0.01, 0.15),
        "xgb_subsample": (0.60, 1.0),
        "xgb_colsample_bytree": (0.60, 1.0),
    }

    def _evolve_xgb_hyperparams(
        self,
        params: EvolvedParams,
        trades: list[Any],
        changes: dict[str, str],
    ) -> None:
        """Evolve XGBoost hyperparameters based on prediction accuracy.

        Strategy:
        - Compute directional hit rate (did the model predict the right direction?).
        - If accuracy is *above* 60 %  → increase capacity (more trees, deeper).
        - If accuracy is *below* 50 %  → regularise harder (fewer trees, lower lr,
          higher subsample / colsample).
        - Near 50-60 % → nudge toward more regularisation gently.

        All changes are small per epoch (EMA-clamped) so the organism
        doesn't leap into unstable configurations.
        """
        if len(trades) < self.min_trades:
            return

        # Estimate directional accuracy from trade outcomes
        # Use actual trade direction (sign of pnl with shares direction)
        correct = sum(
            1 for t in trades
            if (
                (getattr(t, "direction", 1) > 0 and t.pnl > 0)
                or (getattr(t, "direction", 1) < 0 and t.pnl < 0)
            )
        )
        accuracy = correct / len(trades)

        alpha = self.alpha
        any_changed = False
        reason_parts: list[str] = []

        if accuracy >= 0.60:
            # Good accuracy → increase model capacity slightly
            new_n = params.xgb_n_estimators + int(
                alpha * (min(params.xgb_n_estimators * 1.05, 500) - params.xgb_n_estimators)
            )
            new_depth = params.xgb_max_depth + (
                1 if accuracy >= 0.65 and params.xgb_max_depth < 8 else 0
            )
            new_lr = params.xgb_learning_rate  # keep LR stable when working
            new_sub = params.xgb_subsample  # keep regularisation stable
            new_col = params.xgb_colsample_bytree
        elif accuracy < 0.50:
            # Poor accuracy → regularise harder
            new_n = params.xgb_n_estimators + int(
                alpha * (max(params.xgb_n_estimators * 0.90, 100) - params.xgb_n_estimators)
            )
            new_depth = max(params.xgb_max_depth - 1, 3) if accuracy < 0.45 else params.xgb_max_depth
            new_lr = (1 - alpha) * params.xgb_learning_rate + alpha * max(
                params.xgb_learning_rate * 0.85, 0.01
            )
            new_sub = (1 - alpha) * params.xgb_subsample + alpha * min(
                params.xgb_subsample * 1.05, 1.0
            )
            new_col = (1 - alpha) * params.xgb_colsample_bytree + alpha * min(
                params.xgb_colsample_bytree * 1.05, 1.0
            )
        else:
            # Middling accuracy (50-60%) → gentle nudge toward regularisation
            new_n = params.xgb_n_estimators  # hold steady
            new_depth = params.xgb_max_depth
            new_lr = (1 - alpha) * params.xgb_learning_rate + alpha * max(
                params.xgb_learning_rate * 0.95, 0.01
            )
            new_sub = (1 - alpha) * params.xgb_subsample + alpha * min(
                params.xgb_subsample * 1.02, 1.0
            )
            new_col = (1 - alpha) * params.xgb_colsample_bytree + alpha * min(
                params.xgb_colsample_bytree * 1.02, 1.0
            )

        # Clamp all to bounds
        bounds = self._XGB_BOUNDS
        new_n = int(max(bounds["xgb_n_estimators"][0], min(new_n, bounds["xgb_n_estimators"][1])))
        new_depth = int(max(bounds["xgb_max_depth"][0], min(new_depth, bounds["xgb_max_depth"][1])))
        new_lr = max(bounds["xgb_learning_rate"][0], min(new_lr, bounds["xgb_learning_rate"][1]))
        new_sub = max(bounds["xgb_subsample"][0], min(new_sub, bounds["xgb_subsample"][1]))
        new_col = max(bounds["xgb_colsample_bytree"][0], min(new_col, bounds["xgb_colsample_bytree"][1]))

        # Apply if changed
        if new_n != params.xgb_n_estimators:
            reason_parts.append(f"n_est {params.xgb_n_estimators}→{new_n}")
            params.xgb_n_estimators = new_n
            any_changed = True
        if new_depth != params.xgb_max_depth:
            reason_parts.append(f"depth {params.xgb_max_depth}→{new_depth}")
            params.xgb_max_depth = new_depth
            any_changed = True
        if abs(new_lr - params.xgb_learning_rate) > 1e-6:
            reason_parts.append(f"lr {params.xgb_learning_rate:.4f}→{new_lr:.4f}")
            params.xgb_learning_rate = round(new_lr, 6)
            any_changed = True
        if abs(new_sub - params.xgb_subsample) > 1e-4:
            reason_parts.append(f"sub {params.xgb_subsample:.3f}→{new_sub:.3f}")
            params.xgb_subsample = round(new_sub, 4)
            any_changed = True
        if abs(new_col - params.xgb_colsample_bytree) > 1e-4:
            reason_parts.append(f"col {params.xgb_colsample_bytree:.3f}→{new_col:.3f}")
            params.xgb_colsample_bytree = round(new_col, 4)
            any_changed = True

        if any_changed:
            changes["xgb_hyperparams"] = (
                f"acc={accuracy:.1%}; " + "; ".join(reason_parts)
            )
            logger.info(
                "XGB hyperparams evolved (accuracy=%.1f%%): %s",
                accuracy * 100, ", ".join(reason_parts),
            )

    # ═════════════════════════════════════════════════════════════
    #   UTILITIES
    # ═════════════════════════════════════════════════════════════

    def _ema_update(self, old: float, new: float) -> float:
        """EMA w/ max-shift clamp to prevent wild swings."""
        target = self.alpha * new + (1 - self.alpha) * old
        # Clamp the shift
        max_delta = abs(old) * self.max_shift + 0.005  # +0.005 for near-zero
        delta = target - old
        delta = max(-max_delta, min(delta, max_delta))
        return old + delta

    @staticmethod
    def _normalize_alpha_weights(params: EvolvedParams) -> None:
        """Ensure alpha weights sum to 1.0."""
        total = (
            params.alpha_weight_ml
            + params.alpha_weight_volume
            + params.alpha_weight_momentum
            + params.alpha_weight_breakout
            + params.alpha_weight_regime
        )
        if total > 0:
            params.alpha_weight_ml /= total
            params.alpha_weight_volume /= total
            params.alpha_weight_momentum /= total
            params.alpha_weight_breakout /= total
            params.alpha_weight_regime /= total

    @staticmethod
    def _normalize_breakout_weights(params: EvolvedParams) -> None:
        """Ensure breakout weights sum to 1.0."""
        total = (
            params.breakout_weight_squeeze
            + params.breakout_weight_volume
            + params.breakout_weight_contraction
            + params.breakout_weight_rs
            + params.breakout_weight_pivot
            + params.breakout_weight_flow
        )
        if total > 0:
            params.breakout_weight_squeeze /= total
            params.breakout_weight_volume /= total
            params.breakout_weight_contraction /= total
            params.breakout_weight_rs /= total
            params.breakout_weight_pivot /= total
            params.breakout_weight_flow /= total


# ═════════════════════════════════════════════════════════════════
#  Param applicator — pushes evolved values into live components
# ═════════════════════════════════════════════════════════════════

def apply_evolved_params(
    params: EvolvedParams,
    alpha_scanner: Any | None = None,
    breakout_scanner: Any | None = None,
    kelly_sizer: Any | None = None,
    exit_engine: Any | None = None,
    signal_gen: Any | None = None,
) -> None:
    """Push evolved parameters into live organism components.

    Call this at the start of each epoch after :meth:`EvolutionEngine.evolve`.
    """
    # ── Alpha Scanner ────────────────────────────────────────────
    if alpha_scanner is not None:
        alpha_scanner.WEIGHT_ML = params.alpha_weight_ml
        alpha_scanner.WEIGHT_VOLUME = params.alpha_weight_volume
        alpha_scanner.WEIGHT_MOMENTUM = params.alpha_weight_momentum
        alpha_scanner.WEIGHT_BREAKOUT = params.alpha_weight_breakout
        alpha_scanner.WEIGHT_REGIME = params.alpha_weight_regime
        # Symbol fitness for candidate prioritisation
        if params.symbol_fitness:
            alpha_scanner._symbol_fitness = params.symbol_fitness

    # ── Breakout Scanner ─────────────────────────────────────────
    if breakout_scanner is not None:
        breakout_scanner.W_SQUEEZE = params.breakout_weight_squeeze
        breakout_scanner.W_VOLUME = params.breakout_weight_volume
        breakout_scanner.W_CONTRACTION = params.breakout_weight_contraction
        breakout_scanner.W_RS = params.breakout_weight_rs
        breakout_scanner.W_PIVOT = params.breakout_weight_pivot
        breakout_scanner.W_FLOW = params.breakout_weight_flow
        # Phase 3.8 — tunable indicator periods
        breakout_scanner.BB_PERIOD = params.breakout_bb_period
        breakout_scanner.ATR_SHORT = params.breakout_atr_short
        breakout_scanner.ATR_LONG = params.breakout_atr_long
        breakout_scanner.PIVOT_LOOKBACK = params.breakout_pivot_lookback
        breakout_scanner.VOL_AVG_PERIOD = params.breakout_vol_avg_period
        breakout_scanner.RS_PERIOD = params.breakout_rs_period

    # ── Kelly Sizer ──────────────────────────────────────────────
    if kelly_sizer is not None:
        # Override the regime scale method with evolved values
        kelly_sizer._evolved_regime_scales = params.regime_size_scales

    # ── Exit Engine ──────────────────────────────────────────────
    if exit_engine is not None:
        exit_engine.atr_multiplier = 1.5 * params.stop_atr_scale
        exit_engine.trailing_start_atr = 3.0 * params.trailing_start_atr_scale
        exit_engine.trailing_distance_atr = 2.5 * params.trailing_distance_scale
        exit_engine.partial_tp_r = 3.0 * params.partial_tp_r_scale
        exit_engine.partial_tp_pct = params.partial_tp_pct

    # ── ML Signal Generator ──────────────────────────────────────
    if signal_gen is not None:
        signal_gen._direction_threshold_buy = params.direction_threshold_buy
        signal_gen._direction_threshold_sell = params.direction_threshold_sell

        # Phase 4.6 — push evolved XGBoost hyperparameters
        # Merge into existing dict to preserve keys like min_child_weight,
        # reg_alpha, reg_lambda, random_state, verbosity.  Do NOT call
        # _init_models() here — that would destroy the currently-trained
        # classifier/regressor.  The new params take effect at the next
        # retrain cycle when _init_models() is called by the learner.
        if hasattr(signal_gen, "_xgb_params"):
            signal_gen._xgb_params.update({
                "n_estimators": params.xgb_n_estimators,
                "max_depth": params.xgb_max_depth,
                "learning_rate": params.xgb_learning_rate,
                "subsample": params.xgb_subsample,
                "colsample_bytree": params.xgb_colsample_bytree,
            })
