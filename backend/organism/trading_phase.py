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
"""

import logging

logger = logging.getLogger(__name__)

# ML-isolation threshold: below this, ML weight = 0 in confidence,
# Kelly uses risk-budget sizing, exit engine uses horizon_timeout.
ML_ISOLATION_TRADES = 200

# Evolution freeze threshold: below this, no param evolution,
# no warm-start, only bookkeeping.
EVOLUTION_FREEZE_TRADES = 300

# Backward compat alias — callsites that imported LEARNING_MODE_TRADES
LEARNING_MODE_TRADES = ML_ISOLATION_TRADES


def resolve_trading_phase(
    total_trades: int,
    freeze_threshold: int = EVOLUTION_FREEZE_TRADES,
    ml_isolation_threshold: int = ML_ISOLATION_TRADES,
) -> dict:
    """Resolve the current trading phase from trade count.

    Returns a dict with:
        is_learning: bool — True if < ml_isolation_threshold (ML off)
        is_frozen: bool — True if < freeze_threshold (evolution off)
        phase: str — "learning", "production_frozen", or "production"
        total_trades: int
        ml_isolation_threshold: int
        freeze_threshold: int
        trades_to_ml_exit: int
        trades_to_freeze_exit: int
    """
    is_learning = total_trades < ml_isolation_threshold
    is_frozen = total_trades < freeze_threshold

    if is_learning:
        phase = "learning"
    elif is_frozen:
        phase = "production_frozen"
    else:
        phase = "production"

    return {
        "is_learning": is_learning,
        "is_frozen": is_frozen,
        "phase": phase,
        "total_trades": total_trades,
        "ml_isolation_threshold": ml_isolation_threshold,
        "freeze_threshold": freeze_threshold,
        "trades_to_ml_exit": max(0, ml_isolation_threshold - total_trades),
        "trades_to_freeze_exit": max(0, freeze_threshold - total_trades),
    }


def log_trading_phase(total_trades: int, **kwargs) -> dict:
    """Resolve and log the current trading phase."""
    phase = resolve_trading_phase(total_trades, **kwargs)
    logger.info(
        "Trading phase: %s (trades=%d, ML_isolation_exit=%d, freeze_exit=%d)",
        phase["phase"],
        phase["total_trades"],
        phase["trades_to_ml_exit"],
        phase["trades_to_freeze_exit"],
    )
    return phase
