"""
Advanced Slippage Modeling (M-43)

Provides realistic slippage estimation based on:
- Order size relative to average volume
- Market volatility
- Bid-ask spread
- Time of day (market open/close)
- Asset liquidity

Extends the partial implementation in backtest_service.py with a comprehensive model.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, time
from enum import Enum
from typing import Any
import logging
import math

import numpy as np

logger = logging.getLogger(__name__)


class MarketCondition(Enum):
    """Market condition for slippage adjustment."""
    NORMAL = "normal"
    HIGH_VOLATILITY = "high_volatility"
    LOW_LIQUIDITY = "low_liquidity"
    MARKET_STRESS = "market_stress"


class OrderUrgency(Enum):
    """Order urgency level affecting execution quality."""
    PASSIVE = "passive"      # Willing to wait for better price
    NORMAL = "normal"        # Standard execution
    AGGRESSIVE = "aggressive"  # Need immediate fill
    URGENT = "urgent"        # Must fill regardless of cost


@dataclass
class SlippageEstimate:
    """Detailed slippage estimation result."""
    # Core estimates
    base_slippage_bps: float       # Base slippage in basis points
    market_impact_bps: float       # Price impact from order size
    spread_cost_bps: float         # Half the bid-ask spread
    volatility_cost_bps: float     # Additional cost from volatility
    timing_adjustment_bps: float   # Time-of-day adjustment
    
    # Total
    total_slippage_bps: float
    total_slippage_pct: float
    
    # Adjusted execution price
    estimated_fill_price: float
    
    # Confidence
    confidence_low_bps: float      # 10th percentile
    confidence_high_bps: float     # 90th percentile
    
    # Metadata
    market_condition: MarketCondition
    order_urgency: OrderUrgency
    
    # Details
    factors: dict[str, float] = field(default_factory=dict)


@dataclass
class LiquidityProfile:
    """Liquidity characteristics of an asset."""
    symbol: str
    avg_daily_volume: float        # Average daily volume in shares
    avg_spread_bps: float          # Average bid-ask spread in bps
    avg_trade_size: float          # Average trade size
    volatility_20d: float          # 20-day realized volatility
    volume_profile: dict[str, float] = field(default_factory=dict)  # Hour -> relative volume
    
    @property
    def liquidity_score(self) -> float:
        """Calculate liquidity score (0-1, 1 is most liquid)."""
        # Higher volume and lower spread = more liquid
        volume_score = min(1.0, self.avg_daily_volume / 10_000_000)  # 10M shares = max
        spread_score = max(0.0, 1.0 - self.avg_spread_bps / 50)  # 50 bps = min
        return (volume_score + spread_score) / 2


class SlippageModel:
    """
    Comprehensive slippage estimation model.
    
    Combines multiple factors:
    1. Market impact (order size vs ADV)
    2. Bid-ask spread crossing
    3. Volatility adjustment
    4. Time-of-day effects
    5. Market condition adjustments
    
    Based on industry-standard models including:
    - Square-root market impact model
    - Almgren-Chriss optimal execution framework
    
    Usage:
        model = SlippageModel()
        
        # Register asset liquidity profiles
        model.register_profile(LiquidityProfile(
            symbol="AAPL",
            avg_daily_volume=50_000_000,
            avg_spread_bps=1.0,
            ...
        ))
        
        # Estimate slippage
        estimate = model.estimate(
            symbol="AAPL",
            side="buy",
            quantity=1000,
            current_price=150.0,
        )
    """
    
    # Default parameters
    DEFAULT_ADV = 1_000_000  # 1M shares
    DEFAULT_SPREAD_BPS = 5.0  # 5 basis points
    DEFAULT_VOLATILITY = 0.20  # 20% annualized
    
    # Market impact model parameters
    IMPACT_COEFFICIENT = 0.1  # Alpha in square-root model
    IMPACT_EXPONENT = 0.5     # Typically 0.5 for square-root
    
    # Time-of-day adjustments (market hours in ET)
    TIME_ADJUSTMENTS = {
        "pre_market": 2.0,    # 4:00-9:30 ET
        "open_auction": 1.5,  # 9:30-10:00 ET
        "morning": 0.9,       # 10:00-11:30 ET
        "midday": 1.0,        # 11:30-14:00 ET
        "afternoon": 0.95,    # 14:00-15:30 ET
        "close_auction": 1.3, # 15:30-16:00 ET
        "after_hours": 2.5,   # 16:00-20:00 ET
    }
    
    # Market condition multipliers
    CONDITION_MULTIPLIERS = {
        MarketCondition.NORMAL: 1.0,
        MarketCondition.HIGH_VOLATILITY: 1.5,
        MarketCondition.LOW_LIQUIDITY: 2.0,
        MarketCondition.MARKET_STRESS: 3.0,
    }
    
    # Urgency multipliers
    URGENCY_MULTIPLIERS = {
        OrderUrgency.PASSIVE: 0.5,
        OrderUrgency.NORMAL: 1.0,
        OrderUrgency.AGGRESSIVE: 1.5,
        OrderUrgency.URGENT: 2.5,
    }
    
    def __init__(
        self,
        base_slippage_bps: float = 1.0,
        impact_coefficient: float | None = None,
        spread_crossing_pct: float = 0.5,
    ):
        """
        Initialize slippage model.
        
        Args:
            base_slippage_bps: Minimum slippage in basis points
            impact_coefficient: Market impact coefficient (default 0.1)
            spread_crossing_pct: Fraction of spread expected to cross (0-1)
        """
        self.base_slippage_bps = base_slippage_bps
        self.impact_coefficient = impact_coefficient or self.IMPACT_COEFFICIENT
        self.spread_crossing_pct = spread_crossing_pct
        
        # Asset-specific profiles
        self._profiles: dict[str, LiquidityProfile] = {}
        
        # Historical slippage for calibration
        self._slippage_history: list[tuple[float, float]] = []  # (estimated, actual)
    
    def register_profile(self, profile: LiquidityProfile) -> None:
        """Register liquidity profile for an asset."""
        self._profiles[profile.symbol] = profile
        logger.debug(f"Registered liquidity profile for {profile.symbol}")
    
    def get_profile(self, symbol: str) -> LiquidityProfile:
        """Get or create liquidity profile for symbol."""
        if symbol not in self._profiles:
            # Create default profile
            self._profiles[symbol] = LiquidityProfile(
                symbol=symbol,
                avg_daily_volume=self.DEFAULT_ADV,
                avg_spread_bps=self.DEFAULT_SPREAD_BPS,
                avg_trade_size=1000,
                volatility_20d=self.DEFAULT_VOLATILITY,
            )
        return self._profiles[symbol]
    
    def estimate(
        self,
        symbol: str,
        side: str,  # "buy" or "sell"
        quantity: float,
        current_price: float,
        urgency: OrderUrgency = OrderUrgency.NORMAL,
        market_condition: MarketCondition = MarketCondition.NORMAL,
        current_time: datetime | None = None,
        current_volatility: float | None = None,
        current_spread_bps: float | None = None,
    ) -> SlippageEstimate:
        """
        Estimate slippage for an order.
        
        Args:
            symbol: Asset symbol
            side: "buy" or "sell"
            quantity: Number of shares
            current_price: Current market price
            urgency: Order urgency level
            market_condition: Current market condition
            current_time: Order time (for time-of-day adjustment)
            current_volatility: Current volatility override
            current_spread_bps: Current spread override
            
        Returns:
            SlippageEstimate with detailed breakdown
        """
        profile = self.get_profile(symbol)
        current_time = current_time or datetime.now(UTC)
        
        # 1. Calculate market impact
        order_value = quantity * current_price
        participation_rate = quantity / profile.avg_daily_volume if profile.avg_daily_volume > 0 else 0.01
        
        # Square-root market impact model: impact = alpha * sigma * sqrt(Q/V)
        volatility = current_volatility or profile.volatility_20d
        market_impact_bps = (
            self.impact_coefficient *
            volatility * 10000 *  # Convert to bps
            math.sqrt(participation_rate)
        )
        
        # 2. Spread cost (half-spread if crossing)
        spread_bps = current_spread_bps or profile.avg_spread_bps
        spread_cost_bps = spread_bps * self.spread_crossing_pct
        
        # 3. Volatility cost (uncertainty premium)
        # Higher volatility = more price movement during execution
        volatility_cost_bps = volatility * 100 * 0.1  # 10% of daily vol as uncertainty
        
        # 4. Time-of-day adjustment
        time_period = self._get_time_period(current_time)
        timing_multiplier = self.TIME_ADJUSTMENTS.get(time_period, 1.0)
        timing_adjustment_bps = (self.base_slippage_bps * (timing_multiplier - 1))
        
        # 5. Apply condition and urgency multipliers
        condition_mult = self.CONDITION_MULTIPLIERS[market_condition]
        urgency_mult = self.URGENCY_MULTIPLIERS[urgency]
        
        # Calculate total
        raw_total = (
            self.base_slippage_bps +
            market_impact_bps +
            spread_cost_bps +
            volatility_cost_bps +
            timing_adjustment_bps
        )
        
        total_slippage_bps = raw_total * condition_mult * urgency_mult
        total_slippage_pct = total_slippage_bps / 10000
        
        # Calculate fill price (adverse to trade direction)
        if side.lower() == "buy":
            estimated_fill_price = current_price * (1 + total_slippage_pct)
        else:
            estimated_fill_price = current_price * (1 - total_slippage_pct)
        
        # Calculate confidence interval (roughly 10th/90th percentile)
        # Uncertainty scales with volatility and order size
        uncertainty_factor = 1 + math.sqrt(participation_rate) + volatility
        confidence_low_bps = total_slippage_bps * 0.5
        confidence_high_bps = total_slippage_bps * uncertainty_factor
        
        estimate = SlippageEstimate(
            base_slippage_bps=self.base_slippage_bps,
            market_impact_bps=market_impact_bps * condition_mult * urgency_mult,
            spread_cost_bps=spread_cost_bps * condition_mult * urgency_mult,
            volatility_cost_bps=volatility_cost_bps * condition_mult * urgency_mult,
            timing_adjustment_bps=timing_adjustment_bps * condition_mult * urgency_mult,
            total_slippage_bps=total_slippage_bps,
            total_slippage_pct=total_slippage_pct,
            estimated_fill_price=estimated_fill_price,
            confidence_low_bps=confidence_low_bps,
            confidence_high_bps=confidence_high_bps,
            market_condition=market_condition,
            order_urgency=urgency,
            factors={
                "participation_rate": participation_rate,
                "volatility": volatility,
                "spread_bps": spread_bps,
                "time_period": time_period,
                "condition_multiplier": condition_mult,
                "urgency_multiplier": urgency_mult,
            },
        )
        
        logger.debug(
            f"Slippage estimate for {side} {quantity} {symbol}: "
            f"{total_slippage_bps:.1f} bps ({total_slippage_pct:.4%})"
        )
        
        return estimate
    
    def _get_time_period(self, dt: datetime) -> str:
        """Determine time period for time-of-day adjustment."""
        # Convert to Eastern Time (simplified - in production use pytz)
        # Assuming UTC, subtract 5 hours for EST
        hour = (dt.hour - 5) % 24
        minute = dt.minute
        time_minutes = hour * 60 + minute
        
        # Market hours in minutes from midnight ET
        if time_minutes < 9 * 60 + 30:
            return "pre_market"
        elif time_minutes < 10 * 60:
            return "open_auction"
        elif time_minutes < 11 * 60 + 30:
            return "morning"
        elif time_minutes < 14 * 60:
            return "midday"
        elif time_minutes < 15 * 60 + 30:
            return "afternoon"
        elif time_minutes < 16 * 60:
            return "close_auction"
        else:
            return "after_hours"
    
    def record_actual_slippage(
        self,
        estimated_bps: float,
        actual_bps: float,
    ) -> None:
        """Record actual slippage for model calibration."""
        self._slippage_history.append((estimated_bps, actual_bps))
        
        # Keep last 1000 observations
        if len(self._slippage_history) > 1000:
            self._slippage_history = self._slippage_history[-1000:]
    
    def get_calibration_stats(self) -> dict[str, float]:
        """Get model calibration statistics."""
        if len(self._slippage_history) < 10:
            return {
                "sample_size": len(self._slippage_history),
                "bias": 0.0,
                "rmse": 0.0,
                "correlation": 0.0,
            }
        
        estimated = [e for e, a in self._slippage_history]
        actual = [a for e, a in self._slippage_history]
        
        errors = [e - a for e, a in self._slippage_history]
        bias = sum(errors) / len(errors)
        rmse = math.sqrt(sum(e**2 for e in errors) / len(errors))
        
        # Correlation
        try:
            corr_matrix = np.corrcoef(estimated, actual)
            correlation = float(corr_matrix[0, 1])
        except Exception:
            correlation = 0.0
        
        return {
            "sample_size": len(self._slippage_history),
            "bias": bias,
            "rmse": rmse,
            "correlation": correlation,
        }
    
    def estimate_for_backtest(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        volatility: float | None = None,
    ) -> float:
        """
        Simplified slippage estimation for backtesting.
        
        Args:
            symbol: Asset symbol
            side: "buy" or "sell"
            quantity: Number of shares
            price: Execution price
            volatility: Optional volatility override
            
        Returns:
            Estimated slippage as a decimal (e.g., 0.001 for 0.1%)
        """
        estimate = self.estimate(
            symbol=symbol,
            side=side,
            quantity=quantity,
            current_price=price,
            urgency=OrderUrgency.NORMAL,
            market_condition=MarketCondition.NORMAL,
            current_volatility=volatility,
        )
        
        return estimate.total_slippage_pct


# Singleton instance
_slippage_model: SlippageModel | None = None


def get_slippage_model() -> SlippageModel:
    """Get or create the slippage model singleton."""
    global _slippage_model
    if _slippage_model is None:
        _slippage_model = SlippageModel()
    return _slippage_model


def estimate_slippage(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    **kwargs,
) -> SlippageEstimate:
    """Convenience function for quick slippage estimation."""
    return get_slippage_model().estimate(
        symbol=symbol,
        side=side,
        quantity=quantity,
        current_price=price,
        **kwargs,
    )
