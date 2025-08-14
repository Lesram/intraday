"""
Risk management data types with strong typing and validation.
Provides structured data containers for risk decisions, order specs, and portfolio state.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal

# Type aliases for clarity
Side = Literal["buy", "sell"]


class OrderType(Enum):
    """Order types for trading."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status enumeration."""

    NEW = "new"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    PENDING = "pending"


class TimeInForce(Enum):
    """Time in force enumeration."""

    DAY = "day"
    GTC = "gtc"  # Good till canceled
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill


class RiskLevel(Enum):
    """Risk level enumeration."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class RiskLimits:
    """Risk limits configuration."""

    max_position_size: Decimal = Decimal("100000")
    max_daily_loss: Decimal = Decimal("10000")
    max_sector_concentration: float = 0.3
    max_single_position: Decimal = Decimal("50000")
    var_limit_95: Decimal = Decimal("25000")
    var_limit_99: Decimal = Decimal("50000")


@dataclass(frozen=True)
class OrderSpec:
    """Specification for an order to be risk-checked."""

    symbol: str
    side: Side
    qty: Decimal  # Absolute quantity
    notional: Decimal  # Expected notional value
    price: Decimal | None = None  # Limit/last price, None for market orders
    tif: str | None = None  # Time in force
    attributes: dict[str, Any] | None = None  # Additional order attributes

    def __post_init__(self):
        """Validate order specification invariants."""
        if self.qty < 0:
            raise ValueError("qty must be non-negative, use side for direction")
        if self.notional < 0:
            raise ValueError("notional must be non-negative")
        if self.price is not None and self.price <= 0:
            raise ValueError("price must be positive when specified")

    # Provide dict-like access for tests/utilities that expect mapping semantics
    def get(self, key: str, default: Any | None = None) -> Any | None:  # type: ignore[override]
        if key == "symbol":
            return self.symbol
        if key == "qty":
            return self.qty
        if key == "price":
            return self.price
        if key == "tif":
            return self.tif
        # attributes may carry additional fields like client_order_id or order_type
        if key == "attributes":
            return self.attributes
        # Allow access into attributes when present
        if self.attributes and key in self.attributes:
            return self.attributes.get(key, default)
        return default


@dataclass(frozen=True)
class PortfolioState:
    """Current portfolio state for risk calculations."""

    equity: Decimal  # Total equity value
    cash: Decimal  # Available cash
    positions: dict[str, Decimal]  # symbol -> signed quantity
    sector_map: dict[str, str]  # symbol -> sector classification
    last_updated: datetime | None = None

    @property
    def gross_notional(self) -> Decimal:
        """Total gross notional exposure across all positions."""
        # This would need position prices to calculate properly
        # For now, return equity as approximation
        return abs(self.equity - self.cash)

    @property
    def net_notional(self) -> Decimal:
        """Total net notional exposure (long - short)."""
        # Simplified calculation - would need prices for accuracy
        return self.equity - self.cash


@dataclass(frozen=True)
class PortfolioRisk:
    """Portfolio risk metrics and calculations."""

    var_95: Decimal = Decimal("0.0")  # Value at Risk at 95% confidence
    var_99: Decimal = Decimal("0.0")  # Value at Risk at 99% confidence
    volatility: float = 0.0  # Portfolio volatility
    sharpe_ratio: float = 0.0  # Risk-adjusted return
    max_drawdown: Decimal = Decimal("0.0")  # Maximum drawdown
    beta: float = 1.0  # Market beta
    concentration_risk: float = 0.0  # Concentration risk score


@dataclass(frozen=True)
class RiskDecision:
    """Structured risk decision with detailed reasoning."""

    allowed: bool
    reason: str  # Primary reason for allow/block
    adjustments: dict[str, Any]  # Applied adjustments (qty caps, etc.)
    limits: dict[str, Any]  # Snapshot of active limits during decision

    # Additional decision context
    original_qty: Decimal | None = None
    adjusted_qty: Decimal | None = None
    risk_score: float | None = None
    timestamp: datetime | None = None

    @classmethod
    def allow(
        cls,
        reason: str = "approved",
        adjustments: dict[str, Any] | None = None,
        limits: dict[str, Any] | None = None,
        **kwargs,
    ) -> "RiskDecision":
        """Create an allowed decision."""
        return cls(
            allowed=True,
            reason=reason,
            adjustments=adjustments or {},
            limits=limits or {},
            timestamp=datetime.utcnow(),
            **kwargs,
        )

    @classmethod
    def block(
        cls,
        reason: str,
        adjustments: dict[str, Any] | None = None,
        limits: dict[str, Any] | None = None,
        **kwargs,
    ) -> "RiskDecision":
        """Create a blocked decision."""
        return cls(
            allowed=False,
            reason=reason,
            adjustments=adjustments or {},
            limits=limits or {},
            timestamp=datetime.utcnow(),
            **kwargs,
        )
