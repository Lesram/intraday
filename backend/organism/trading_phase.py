"""Shared trading-phase resolver.

Single source of truth for learning vs production mode determination.
All modules must use this instead of per-module thresholds.

Two distinct thresholds:
  ML_ISOLATION_TRADES (200): ML weight = 0 in confidence formula,
      alpha scanner zeros ML, exit engine uses horizon_timeout,
      Kelly uses fixed risk-budget sizing. This is because ML is
      untrained and anti-predictive below 200 trades (H2, H3).

  EVOLUTION_FREEZE_TRADES (300): Evolution engine frozen, no param
      evolution, no warm-start transfer learning. This is because
      the adaptation space is too wide to validate with < 300 trades.

  PROMOTION GATE (Phase 2): after 300 trades, full production behavior
      requires realized strategy health.  A losing brain is demoted to
      ``production_guarded``: strict production entry gates remain, but
      ML influence and full Kelly sizing stay disabled until expectancy
      clears the configured floors.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ML-isolation threshold: below this, ML weight = 0 in confidence,
# Kelly uses risk-budget sizing, exit engine uses horizon_timeout.
ML_ISOLATION_TRADES = 200

# Evolution freeze threshold: below this, no param evolution,
# no warm-start, only bookkeeping.
EVOLUTION_FREEZE_TRADES = 300

# Backward compat alias — callsites that imported LEARNING_MODE_TRADES
LEARNING_MODE_TRADES = ML_ISOLATION_TRADES

# Phase 2 promotion floors.  These intentionally start simple and
# operator-readable: full production requires non-negative lifetime and
# rolling expectancy plus a minimally acceptable rolling win rate.
PROMOTION_MIN_TOTAL_PNL = 0.0
PROMOTION_MIN_LAST_50_MEAN_PNL = 0.0
PROMOTION_MIN_LAST_50_WIN_RATE = 0.35
PROMOTION_MIN_SHARPE_PER_TRADE = 0.0


def _float(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def promotion_blockers(
    strategy_expectancy: dict[str, Any] | None,
    *,
    min_total_pnl: float = PROMOTION_MIN_TOTAL_PNL,
    min_last_50_mean_pnl: float = PROMOTION_MIN_LAST_50_MEAN_PNL,
    min_last_50_win_rate: float = PROMOTION_MIN_LAST_50_WIN_RATE,
    min_sharpe_per_trade: float = PROMOTION_MIN_SHARPE_PER_TRADE,
    min_samples: int = EVOLUTION_FREEZE_TRADES,
) -> list[str]:
    """Return reasons the brain is not eligible for full production.

    Missing/immature expectancy data does not block here; the trade-count
    thresholds already handle immature brains.  The gate becomes active
    only when the expectancy payload itself has enough closed trades.
    """
    if not strategy_expectancy:
        return []
    n_trades = int(_float(strategy_expectancy, "n_trades", 0.0))
    if n_trades < min_samples:
        return []

    blockers: list[str] = []
    total_pnl = _float(strategy_expectancy, "total_pnl")
    last_50_mean = _float(strategy_expectancy, "last_50_mean_pnl")
    last_50_win_rate = _float(strategy_expectancy, "last_50_win_rate")
    sharpe = _float(strategy_expectancy, "sharpe_ratio_per_trade")

    if total_pnl < min_total_pnl:
        blockers.append(
            f"total_pnl {total_pnl:.2f} < floor {min_total_pnl:.2f}"
        )
    if last_50_mean < min_last_50_mean_pnl:
        blockers.append(
            f"last_50_mean_pnl {last_50_mean:.4f} < floor "
            f"{min_last_50_mean_pnl:.4f}"
        )
    if last_50_win_rate < min_last_50_win_rate:
        blockers.append(
            f"last_50_win_rate {last_50_win_rate:.3f} < floor "
            f"{min_last_50_win_rate:.3f}"
        )
    if sharpe < min_sharpe_per_trade:
        blockers.append(
            f"sharpe_ratio_per_trade {sharpe:.4f} < floor "
            f"{min_sharpe_per_trade:.4f}"
        )
    return blockers


def resolve_trading_phase(
    total_trades: int,
    strategy_expectancy: dict[str, Any] | None = None,
    freeze_threshold: int = EVOLUTION_FREEZE_TRADES,
    ml_isolation_threshold: int = ML_ISOLATION_TRADES,
) -> dict:
    """Resolve the current trading phase from trade count.

    Returns a dict with:
        is_learning: bool — True if < ml_isolation_threshold (ML off)
        is_frozen: bool — True if < freeze_threshold (evolution off)
        phase: str — "learning", "production_frozen",
            "production_guarded", or "production"
        is_guarded: bool — True when expectancy blocks full production
        ml_influence_enabled: bool — False in learning / guarded modes
        fixed_risk_sizing: bool — True when Kelly must be bypassed
        total_trades: int
        ml_isolation_threshold: int
        freeze_threshold: int
        trades_to_ml_exit: int
        trades_to_freeze_exit: int
        promotion_blockers: list[str]
    """
    is_learning = total_trades < ml_isolation_threshold
    is_frozen = total_trades < freeze_threshold
    blockers = (
        promotion_blockers(strategy_expectancy, min_samples=freeze_threshold)
        if not is_learning and not is_frozen
        else []
    )
    is_guarded = bool(blockers)

    if is_learning:
        phase = "learning"
    elif is_frozen:
        phase = "production_frozen"
    elif is_guarded:
        phase = "production_guarded"
    else:
        phase = "production"

    ml_influence_enabled = not is_learning and not is_guarded
    fixed_risk_sizing = is_learning or is_guarded

    return {
        "is_learning": is_learning,
        "is_frozen": is_frozen,
        "is_guarded": is_guarded,
        "phase": phase,
        "ml_influence_enabled": ml_influence_enabled,
        "fixed_risk_sizing": fixed_risk_sizing,
        "total_trades": total_trades,
        "ml_isolation_threshold": ml_isolation_threshold,
        "freeze_threshold": freeze_threshold,
        "trades_to_ml_exit": max(0, ml_isolation_threshold - total_trades),
        "trades_to_freeze_exit": max(0, freeze_threshold - total_trades),
        "promotion_blockers": blockers,
    }


def log_trading_phase(
    total_trades: int,
    strategy_expectancy: dict[str, Any] | None = None,
    **kwargs,
) -> dict:
    """Resolve and log the current trading phase."""
    phase = resolve_trading_phase(
        total_trades,
        strategy_expectancy=strategy_expectancy,
        **kwargs,
    )
    logger.info(
        "Trading phase: %s (trades=%d, ML_isolation_exit=%d, "
        "freeze_exit=%d, ml_enabled=%s, fixed_risk=%s)",
        phase["phase"],
        phase["total_trades"],
        phase["trades_to_ml_exit"],
        phase["trades_to_freeze_exit"],
        phase["ml_influence_enabled"],
        phase["fixed_risk_sizing"],
    )
    if phase["promotion_blockers"]:
        logger.warning(
            "Full production promotion blocked: %s",
            "; ".join(phase["promotion_blockers"]),
        )
    return phase
