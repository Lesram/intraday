"""
Position Limits Module

Defines position and risk limit configurations for the trading platform.
Updated to use Pydantic for backward compatibility and field validation.
"""

from decimal import Decimal
from typing import Optional, Dict, Any, Union
from pydantic import BaseModel, Field, model_validator, field_validator


class PositionLimits(BaseModel):
    """
    Position limits configuration for risk management.
    
    Supports backward compatibility for various field names and formats:
    - circuit_breaker_pct / circuit_breaker aliases 
    - Percent (0-100) or fraction (0-1) formats for percentages
    - max_position_value as alias for max_position_size
    """
    
    # Maximum position size limits
    max_position_size: Decimal = Field(
        default=Decimal('1000000'), 
        description="Maximum position size in dollars",
        alias="max_position_value"  # Backward compatibility
    )
    max_position_count: int = Field(default=100, description="Maximum number of positions")
    
    # Concentration limits  
    max_sector_concentration: Decimal = Field(
        default=Decimal('0.25'), 
        description="Maximum sector concentration as fraction (0.25 = 25%)"
    )
    max_symbol_concentration: Decimal = Field(
        default=Decimal('0.10'),
        description="Maximum symbol concentration as fraction (0.10 = 10%)"
    )
    
    # Risk limits
    max_daily_loss: Decimal = Field(
        default=Decimal('50000'),
        description="Maximum daily loss in dollars"
    )
    max_drawdown: Decimal = Field(
        default=Decimal('0.15'),
        description="Maximum drawdown as fraction (0.15 = 15%)"
    )
    
    # Circuit breaker - backward compatible field with aliases and normalization
    circuit_breaker_pct: Decimal = Field(
        default=Decimal('0.05'),
        description="Circuit breaker threshold as fraction (0.05 = 5%)",
        alias="circuit_breaker"  # Accept both names
    )
    
    # Position sizing limits
    min_position_size: Decimal = Field(
        default=Decimal('1000'),
        description="Minimum position size in dollars"
    )
    position_size_step: Decimal = Field(
        default=Decimal('100'),
        description="Position size increment in dollars"
    )
    
    # Leverage limits
    max_leverage: Decimal = Field(
        default=Decimal('4.0'),
        description="Maximum leverage ratio"
    )
    maintenance_margin: Decimal = Field(
        default=Decimal('0.25'),
        description="Maintenance margin as fraction (0.25 = 25%)"
    )
    
    # Additional configuration
    allowed_symbols: Optional[list] = Field(
        default_factory=list,
        description="List of allowed trading symbols (empty = all allowed)"
    )
    restricted_symbols: Optional[list] = Field(
        default_factory=list, 
        description="List of restricted trading symbols"
    )
    
    @field_validator('circuit_breaker_pct', mode='before')
    @classmethod
    def normalize_circuit_breaker_pct(cls, v: Union[str, int, float, Decimal]) -> Decimal:
        """
        Normalize circuit breaker percentage to fraction.
        Accepts values in 0-1 (fraction) or 0-100 (percent) format.
        """
        if v is None:
            return Decimal('0.05')  # Default 5%
            
        # Convert to Decimal
        value = Decimal(str(v))
        
        # If value > 1, assume it's in percentage format (e.g., 5 = 5%)
        if value > 1:
            value = value / 100
            
        return value
    
    @field_validator('max_sector_concentration', 'max_symbol_concentration', 'max_drawdown', 'maintenance_margin')
    @classmethod  
    def normalize_percentage_fields(cls, v: Union[str, int, float, Decimal]) -> Decimal:
        """
        Normalize percentage fields to fractions.
        Accepts values in 0-1 (fraction) or 0-100 (percent) format.
        """
        if v is None:
            return Decimal('0.0')
            
        # Convert to Decimal
        value = Decimal(str(v))
        
        # If value > 1, assume it's in percentage format
        if value > 1:
            value = value / 100
            
        return value
        
    @model_validator(mode='after')
    def validate_limits(self) -> 'PositionLimits':
        """Validate that all percentage fields are in valid ranges after normalization."""
        
        # Validate percentage fields are in [0.0, 1.0] range
        percentage_fields = [
            ('circuit_breaker_pct', self.circuit_breaker_pct),
            ('max_sector_concentration', self.max_sector_concentration), 
            ('max_symbol_concentration', self.max_symbol_concentration),
            ('max_drawdown', self.max_drawdown),
            ('maintenance_margin', self.maintenance_margin)
        ]
        
        for field_name, value in percentage_fields:
            if not (Decimal('0.0') <= value <= Decimal('1.0')):
                raise ValueError(f"{field_name} must be between 0.0 and 1.0 (fraction), got {value}")
        
        # Validate size limits
        if self.min_position_size >= self.max_position_size:
            raise ValueError("min_position_size must be less than max_position_size")
            
        return self
    
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
            "circuit_breaker_pct": str(self.circuit_breaker_pct),
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
            circuit_breaker_pct=Decimal(data.get("circuit_breaker_pct", "0.05")),
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
    circuit_breaker_pct=Decimal('0.03'),  # 3% circuit breaker
)

__all__ = [
    "PositionLimits",
    "DEFAULT_POSITION_LIMITS", 
    "DEVELOPMENT_POSITION_LIMITS",
]
