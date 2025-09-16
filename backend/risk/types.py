"""
Risk management data types with strong typing and validation.
Provides structured data containers for risk decisions, order specs, and portfolio state.
"""

from dataclasses import dataclass
from datetime import datetime, UTC
from decimal import Decimal
from enum import Enum
from typing import Any, Literal, Optional

# Contract-Adapter Patch F: Import Side enum for test compatibility
from backend.strategies.types import Side

# Legacy type alias (kept for backward compatibility)
# Side = Literal["buy", "sell"]  # Now imported from strategies.types


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
    """Risk limits configuration with legacy compatibility."""

    max_position_value: float = 0.0
    max_symbol_exposure: float = 1.0
    circuit_breaker_pct: float = 0.5
    # legacy/optional
    max_portfolio_exposure: Optional[float] = None
    
    # Legacy fields for backward compatibility
    max_position_size: Optional[Decimal] = None
    max_daily_loss: Optional[Decimal] = None
    max_sector_concentration: Optional[float] = None
    max_single_position: Optional[Decimal] = None
    var_limit_95: Optional[Decimal] = None
    var_limit_99: Optional[Decimal] = None

    def __init__(self, **kwargs: Any):
        # accept both new and legacy names
        self.max_position_value = float(kwargs.get("max_position_value", 0.0))
        
        # Prioritize max_symbol_exposure over max_portfolio_exposure
        if "max_symbol_exposure" in kwargs:
            self.max_symbol_exposure = float(kwargs["max_symbol_exposure"])
        elif "max_portfolio_exposure" in kwargs:
            self.max_symbol_exposure = float(kwargs["max_portfolio_exposure"])
        else:
            self.max_symbol_exposure = 1.0
            
        self.circuit_breaker_pct = float(kwargs.get("circuit_breaker_pct", 0.5))
        self.max_portfolio_exposure = kwargs.get("max_portfolio_exposure", None)
        
        # Legacy field compatibility
        self.max_position_size = kwargs.get("max_position_size", Decimal("100000") if "max_position_size" in kwargs else None)
        self.max_daily_loss = kwargs.get("max_daily_loss", Decimal("10000") if "max_daily_loss" in kwargs else None)
        self.max_sector_concentration = kwargs.get("max_sector_concentration", None)
        self.max_single_position = kwargs.get("max_single_position", Decimal("50000") if "max_single_position" in kwargs else None)
        self.var_limit_95 = kwargs.get("var_limit_95", Decimal("25000") if "var_limit_95" in kwargs else None)
        self.var_limit_99 = kwargs.get("var_limit_99", Decimal("50000") if "var_limit_99" in kwargs else None)


@dataclass(frozen=True)
class OrderSpec:
    """Specification for an order to be risk-checked."""

    symbol: str
    side: Side
    qty: Decimal  # Absolute quantity
    # Contract-Adapter Patch F: Make notional optional for legacy test compatibility
    notional: Decimal | None = None  # Expected notional value (auto-calculated if None)
    price: Decimal | None = None  # Limit/last price, None for market orders
    tif: str | None = None  # Time in force
    attributes: dict[str, Any] | None = None  # Additional order attributes
    # E2: Add type field that can accept order_type alias
    type: str | None = None  # Order type (market, limit, etc.)

    def __init__(self, **kw):
        # E2: OrderSpec accept order_type and quantity aliases
        # Handle the type/order_type alias - prefer canonical, fallback to alias
        order_type = kw.get("type") or kw.get("order_type")
        # Handle the qty/quantity alias - prefer canonical, fallback to alias  
        quantity = kw.get("qty") or kw.get("quantity")
        
        # Remove aliases from kwargs if present since we only keep the canonical names
        kw.pop("order_type", None)
        kw.pop("quantity", None)
        
        # Set all the fields using object.__setattr__ since frozen=True
        object.__setattr__(self, 'symbol', kw.get('symbol'))
        object.__setattr__(self, 'side', kw.get('side'))
        object.__setattr__(self, 'qty', quantity)
        object.__setattr__(self, 'notional', kw.get('notional'))
        object.__setattr__(self, 'price', kw.get('price'))
        object.__setattr__(self, 'tif', kw.get('tif'))
        object.__setattr__(self, 'attributes', kw.get('attributes'))
        object.__setattr__(self, 'type', order_type)
        
        # Call __post_init__ manually since we're overriding __init__
        self.__post_init__()

    def __post_init__(self):
        """Validate order specification invariants."""
        if self.qty < 0:
            raise ValueError("qty must be non-negative, use side for direction")
        
        # Contract-Adapter Patch F: Auto-calculate notional if not provided
        if self.notional is None and self.price is not None:
            # Auto-calculate notional from qty * price
            object.__setattr__(self, 'notional', self.qty * self.price)
        elif self.notional is None:
            # Default fallback notional if no price provided
            object.__setattr__(self, 'notional', self.qty * Decimal('100.0'))
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
        # E2: Support quantity alias for backward compatibility
        if key == "quantity":
            return self.qty
        if key == "price":
            return self.price
        if key == "tif":
            return self.tif
        if key == "type":
            return self.type
        # E2: Support order_type alias for backward compatibility
        if key == "order_type":
            return self.type
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

    @property
    def approved(self) -> bool:
        """Backward compatibility property for tests."""
        return self.allowed

    @property
    def symbol_exposure(self) -> float:
        """Get symbol exposure from adjustments for test compatibility."""
        return self.adjustments.get("symbol_exposure", 0.0)

    @property
    def sector_exposure(self) -> float:
        """Get sector exposure from adjustments for test compatibility."""
        return self.adjustments.get("sector_exposure", 0.0)

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
            timestamp=datetime.now(UTC),
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
            timestamp=datetime.now(UTC),
            **kwargs,
        )
