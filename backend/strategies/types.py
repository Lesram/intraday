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
    FLAT = "flat"


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
    """Execution plan with legacy-friendly constructor.

    Two families of tests exist:
    1. Legacy (Module39) creating ExecutionPlan(symbol, side, quantity, price, order_type)
       expecting attributes: symbol, side, quantity, price, order_type
    2. New engine pathways expecting exposure based fields and notional maths.

    We unify these by making exposure fields optional; when a simple legacy
    construction is used we infer notional = quantity * price and default
    exposures to 0 -> sign(quantity).
    """

    # Core identifiers
    symbol: str
    side: Side
    quantity: Decimal | int | float
    price: Decimal | int | float
    order_type: str = "market"

    # Advanced / engine fields (optional for legacy tests)
    ts: datetime | None = None
    from_exposure: float | None = None
    to_exposure: float | None = None
    notional: Decimal | None = None
    qty: Decimal | None = None  # alias for quantity (signed broker qty)
    reason: str = ""
    risk_allowed: bool = True
    risk_reason: str | None = None

    def __post_init__(self):
        # Timestamp default
        if self.ts is None:
            object.__setattr__(self, "ts", datetime.utcnow())

        # Normalise decimal types
        def _to_decimal(v):
            return v if isinstance(v, Decimal) else Decimal(str(v))
        q_dec = _to_decimal(self.quantity)
        p_dec = _to_decimal(self.price)
        object.__setattr__(self, "quantity", q_dec)
        object.__setattr__(self, "price", p_dec)

        # Mirror to qty alias if not provided
        if self.qty is None:
            object.__setattr__(self, "qty", q_dec)

        # Derive notional if missing
        if self.notional is None:
            object.__setattr__(self, "notional", q_dec * p_dec)

        # Exposure inference for legacy simple plans
        if self.from_exposure is None:
            object.__setattr__(self, "from_exposure", 0.0)
        if self.to_exposure is None:
            sign = 0.0
            if q_dec > 0:
                sign = 1.0
            elif q_dec < 0:
                sign = -1.0
            object.__setattr__(self, "to_exposure", sign)

        # Bounds check exposures
        if not (-1.0 <= self.from_exposure <= 1.0):  # type: ignore[arg-type]
            raise ValueError("from_exposure out of range")
        if not (-1.0 <= self.to_exposure <= 1.0):  # type: ignore[arg-type]
            raise ValueError("to_exposure out of range")
