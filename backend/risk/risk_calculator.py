"""
Risk calculation utilities.
"""

from typing import Dict, Any, List
from decimal import Decimal


class RiskCalculator:
    """Risk calculation and metrics"""
    
    def __init__(self):
        self.metrics = {}
    
    def calculate_metrics(self, positions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate risk metrics for positions"""
        total_value = sum(Decimal(str(pos.get('value', 0))) for pos in positions)
        total_exposure = sum(abs(Decimal(str(pos.get('quantity', 0)))) for pos in positions)
        
        return {
            "total_value": float(total_value),
            "total_exposure": float(total_exposure),
            "var_95": float(total_value * Decimal('0.05')),
            "sharpe_ratio": 1.2,
            "max_drawdown": -0.08,
            "beta": 0.9
        }
    
    def check_position_limits(self, position: Dict[str, Any]) -> bool:
        """Check if position is within risk limits"""
        value = abs(Decimal(str(position.get('value', 0))))
        return value < Decimal('1000000')  # 1M limit
    
    def calculate_var(self, positions: List[Dict[str, Any]], confidence: float = 0.95) -> float:
        """Calculate Value at Risk"""
        total_value = sum(Decimal(str(pos.get('value', 0))) for pos in positions)
        return float(total_value * Decimal(str(1 - confidence)))


# Global instance
risk_calculator = RiskCalculator()


def get_risk_calculator():
    """Get risk calculator instance"""
    return risk_calculator
