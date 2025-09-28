"""
Volatility Checker Module

Monitors and validates asset volatility for risk management purposes.
Implements volatility calculations and threshold-based warnings.
"""

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal


@dataclass
class VolatilityMetrics:
    """Volatility metrics for an asset."""
    symbol: str
    current_volatility: Decimal
    historical_volatility_30d: Decimal
    volatility_percentile: Decimal  # Current vol vs historical distribution
    risk_level: str  # LOW, MEDIUM, HIGH, EXTREME
    last_updated: datetime


class VolatilityChecker:
    """Calculates and monitors asset volatility for risk management."""
    
    # Risk thresholds (annualized volatility)
    VOLATILITY_THRESHOLDS = {
        'LOW': Decimal('0.15'),      # 15%
        'MEDIUM': Decimal('0.30'),   # 30%
        'HIGH': Decimal('0.50'),     # 50%
        'EXTREME': Decimal('0.75')   # 75%
    }
    
    def __init__(self, lookback_days: int = 30):
        """Initialize volatility checker with lookback period."""
        self.lookback_days = lookback_days
        self._price_history: dict[str, list[tuple[datetime, Decimal]]] = {}
    
    def add_price_data(self, symbol: str, price: Decimal, timestamp: datetime | None = None):
        """Add price data point for volatility calculation."""
        if timestamp is None:
            timestamp = datetime.now()
        
        if symbol not in self._price_history:
            self._price_history[symbol] = []
        
        self._price_history[symbol].append((timestamp, price))
        
        # Keep only recent data
        cutoff_date = timestamp - timedelta(days=self.lookback_days)
        self._price_history[symbol] = [
            (ts, price) for ts, price in self._price_history[symbol]
            if ts >= cutoff_date
        ]
    
    def calculate_volatility(self, symbol: str) -> Decimal | None:
        """Calculate annualized volatility from price history."""
        if symbol not in self._price_history or len(self._price_history[symbol]) < 2:
            return None
        
        prices = [price for _, price in self._price_history[symbol]]
        
        # Calculate daily returns
        returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                daily_return = (prices[i] - prices[i-1]) / prices[i-1]
                returns.append(float(daily_return))
        
        if len(returns) < 2:
            return None
        
        # Calculate standard deviation of returns
        volatility_daily = Decimal(str(statistics.stdev(returns)))
        
        # Annualize (252 trading days per year)
        volatility_annual = volatility_daily * Decimal('252').sqrt()
        
        return volatility_annual
    
    def get_risk_level(self, volatility: Decimal) -> str:
        """Classify risk level based on volatility."""
        if volatility <= self.VOLATILITY_THRESHOLDS['LOW']:
            return 'LOW'
        elif volatility <= self.VOLATILITY_THRESHOLDS['MEDIUM']:
            return 'MEDIUM'
        elif volatility <= self.VOLATILITY_THRESHOLDS['HIGH']:
            return 'HIGH'
        else:
            return 'EXTREME'
    
    def calculate_volatility_percentile(self, symbol: str, current_vol: Decimal) -> Decimal:
        """Calculate percentile of current volatility vs historical data."""
        if symbol not in self._price_history:
            return Decimal('50')  # Neutral if no history
        
        # For simplicity, return a fixed percentile
        # In production, this would calculate actual historical percentiles
        if current_vol <= self.VOLATILITY_THRESHOLDS['LOW']:
            return Decimal('25')
        elif current_vol <= self.VOLATILITY_THRESHOLDS['MEDIUM']:
            return Decimal('50')
        elif current_vol <= self.VOLATILITY_THRESHOLDS['HIGH']:
            return Decimal('75')
        else:
            return Decimal('95')
    
    def get_volatility_metrics(self, symbol: str) -> VolatilityMetrics | None:
        """Get comprehensive volatility metrics for a symbol."""
        current_vol = self.calculate_volatility(symbol)
        
        if current_vol is None:
            return None
        
        risk_level = self.get_risk_level(current_vol)
        percentile = self.calculate_volatility_percentile(symbol, current_vol)
        
        return VolatilityMetrics(
            symbol=symbol,
            current_volatility=current_vol,
            historical_volatility_30d=current_vol,  # Simplified
            volatility_percentile=percentile,
            risk_level=risk_level,
            last_updated=datetime.now()
        )
    
    def check_volatility_alerts(self, symbol: str, threshold: str = 'HIGH') -> bool:
        """Check if symbol volatility exceeds threshold."""
        metrics = self.get_volatility_metrics(symbol)
        
        if not metrics:
            return False
        
        threshold_value = self.VOLATILITY_THRESHOLDS[threshold]
        return metrics.current_volatility > threshold_value
    
    def get_portfolio_volatility_summary(self, symbols: list[str]) -> dict[str, VolatilityMetrics]:
        """Get volatility summary for a list of symbols."""
        summary = {}
        
        for symbol in symbols:
            metrics = self.get_volatility_metrics(symbol)
            if metrics:
                summary[symbol] = metrics
        
        return summary
    
    def validate_position_volatility(self, symbol: str, position_size: Decimal, 
                                   max_risk_level: str = 'HIGH') -> tuple[bool, str]:
        """Validate if position can be taken given volatility constraints."""
        metrics = self.get_volatility_metrics(symbol)
        
        if not metrics:
            return True, "No volatility data available"
        
        max_threshold = self.VOLATILITY_THRESHOLDS[max_risk_level]
        
        if metrics.current_volatility <= max_threshold:
            return True, f"Volatility {metrics.current_volatility:.2%} within limit"
        else:
            return False, f"Volatility {metrics.current_volatility:.2%} exceeds {max_risk_level} threshold"


# Factory function for easy instantiation
def create_volatility_checker(lookback_days: int = 30) -> VolatilityChecker:
    """Create a new volatility checker instance."""
    return VolatilityChecker(lookback_days)
