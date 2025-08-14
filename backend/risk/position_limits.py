"""
Position Limits Module

Defines position and risk limit configurations for the trading platform.
"""

from decimal import Decimal
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class PositionLimits:
    """Position limits configuration for risk management"""
    
    # Maximum position size limits
    max_position_size: Decimal = Decimal('1000000')  # $1M default
    max_position_count: int = 100  # Max 100 positions
    
    # Concentration limits
    max_sector_concentration: Decimal = Decimal('0.25')  # 25% max per sector
    max_symbol_concentration: Decimal = Decimal('0.10')  # 10% max per symbol
    
    # Risk limits
    max_daily_loss: Decimal = Decimal('50000')  # $50K daily loss limit
    max_drawdown: Decimal = Decimal('0.15')  # 15% max drawdown
    
    # Position sizing limits
    min_position_size: Decimal = Decimal('1000')  # $1K minimum
    position_size_step: Decimal = Decimal('100')  # $100 increments
    
    # Leverage limits
    max_leverage: Decimal = Decimal('4.0')  # 4:1 max leverage
    maintenance_margin: Decimal = Decimal('0.25')  # 25% maintenance
    
    # Additional configuration
    allowed_symbols: Optional[list] = None
    restricted_symbols: Optional[list] = None
    
    def __post_init__(self):
        """Initialize default values"""
        if self.allowed_symbols is None:
            self.allowed_symbols = []
        if self.restricted_symbols is None:
            self.restricted_symbols = []
    
    def validate_position_size(self, size: Decimal) -> bool:
        """Validate if position size is within limits"""
        return (self.min_position_size <= size <= self.max_position_size)
    
    def validate_symbol(self, symbol: str) -> bool:
        """Validate if symbol is allowed for trading"""
        if self.restricted_symbols and symbol in self.restricted_symbols:
            return False
        if self.allowed_symbols and symbol not in self.allowed_symbols:
            return False
        return True
    
    def get_max_position_for_symbol(self, symbol: str, portfolio_value: Decimal) -> Decimal:
        """Calculate maximum allowed position size for a symbol"""
        symbol_limit = portfolio_value * self.max_symbol_concentration
        return min(symbol_limit, self.max_position_size)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "max_position_size": str(self.max_position_size),
            "max_position_count": self.max_position_count,
            "max_sector_concentration": str(self.max_sector_concentration),
            "max_symbol_concentration": str(self.max_symbol_concentration),
            "max_daily_loss": str(self.max_daily_loss),
            "max_drawdown": str(self.max_drawdown),
            "min_position_size": str(self.min_position_size),
            "position_size_step": str(self.position_size_step),
            "max_leverage": str(self.max_leverage),
            "maintenance_margin": str(self.maintenance_margin),
            "allowed_symbols": self.allowed_symbols,
            "restricted_symbols": self.restricted_symbols,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PositionLimits":
        """Create from dictionary"""
        return cls(
            max_position_size=Decimal(data.get("max_position_size", "1000000")),
            max_position_count=data.get("max_position_count", 100),
            max_sector_concentration=Decimal(data.get("max_sector_concentration", "0.25")),
            max_symbol_concentration=Decimal(data.get("max_symbol_concentration", "0.10")),
            max_daily_loss=Decimal(data.get("max_daily_loss", "50000")),
            max_drawdown=Decimal(data.get("max_drawdown", "0.15")),
            min_position_size=Decimal(data.get("min_position_size", "1000")),
            position_size_step=Decimal(data.get("position_size_step", "100")),
            max_leverage=Decimal(data.get("max_leverage", "4.0")),
            maintenance_margin=Decimal(data.get("maintenance_margin", "0.25")),
            allowed_symbols=data.get("allowed_symbols", []),
            restricted_symbols=data.get("restricted_symbols", []),
        )


# Default conservative limits for production
DEFAULT_POSITION_LIMITS = PositionLimits()

# More aggressive limits for development/testing
DEVELOPMENT_POSITION_LIMITS = PositionLimits(
    max_position_size=Decimal('100000'),  # $100K
    max_daily_loss=Decimal('5000'),       # $5K
    max_drawdown=Decimal('0.05'),         # 5%
)

__all__ = [
    "PositionLimits",
    "DEFAULT_POSITION_LIMITS", 
    "DEVELOPMENT_POSITION_LIMITS",
]
