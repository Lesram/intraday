"""
Strategy Engine Types - Branch 2.7

Dataclasses for TradingSignal and ExecutionPlan to support deterministic
strategy netting, throttling, and risk gating.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class Side(Enum):
    """Order side enumeration"""

    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class TradingSignal:
    """
    Input signal from a strategy source.

    Args:
        symbol: Trading symbol (e.g., "BTCUSD")
        source: Strategy identifier (e.g., "momentum", "mean_reversion", "ensemble")
        ts: Signal timestamp
        target_exposure: Desired net exposure [-1.0, 1.0] where 1=100% long, -1=100% short
        confidence: Signal confidence [0, 1]
        metadata: Optional strategy-specific data
    """

    symbol: str
    source: str
    ts: datetime
    target_exposure: float  # [-1.0, 1.0]
    confidence: float  # [0, 1]
    metadata: dict[str, object] | None = None

    def __post_init__(self) -> None:
        """Validate signal constraints."""
        if not (-1.0 <= self.target_exposure <= 1.0):
            raise ValueError(
                f"target_exposure must be in [-1.0, 1.0], got {self.target_exposure}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")


@dataclass(frozen=True)
class ExecutionPlan:
    """
    Netted execution plan after signal aggregation, throttling, and risk gating.

    Args:
        symbol: Trading symbol
        ts: Plan timestamp
        from_exposure: Current portfolio exposure [-1.0, 1.0]
        to_exposure: Planned target exposure after netting/throttles
        side: Order side after translation to broker format
        notional: Dollar notional amount
        qty: Signed quantity, broker-ready with proper precision
        reason: Human-readable execution summary
        risk_allowed: Whether risk manager approved this plan
        risk_reason: Risk manager rejection reason if blocked
    """

    symbol: str
    ts: datetime
    from_exposure: float  # current portfolio exposure
    to_exposure: float  # planned target after netting/throttles
    side: Side  # "long" | "short" | "flat"
    notional: Decimal
    qty: Decimal  # signed; broker-ready sizing after risk
    reason: str  # brief summary: "netted: momentum+mr; throttle=ok; risk=allow"
    risk_allowed: bool
    risk_reason: str | None = None

    def __post_init__(self) -> None:
        """Validate plan constraints."""
        if not (-1.0 <= self.from_exposure <= 1.0):
            raise ValueError(
                f"from_exposure must be in [-1.0, 1.0], got {self.from_exposure}"
            )
        if not (-1.0 <= self.to_exposure <= 1.0):
            raise ValueError(
                f"to_exposure must be in [-1.0, 1.0], got {self.to_exposure}"
            )
