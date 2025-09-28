"""
Risk metrics calculation module.

Provides comprehensive risk and performance metrics including:
- Risk-adjusted returns (Sharpe, Sortino, Calmar ratios)
- Volatility and correlation metrics
- Drawdown analysis
- Market risk metrics (Beta, Alpha)
- Portfolio risk assessment
"""

import numpy as np
from typing import List, Dict, Any, Optional, Union
from decimal import Decimal
import logging

from .math import (
    value_at_risk, conditional_var, parametric_var, 
    coherent_risk_measures, _to_series
)

logger = logging.getLogger(__name__)


class RiskMetrics:
    """Comprehensive risk metrics calculator."""
    
    def __init__(self):
        """Initialize risk metrics calculator."""
        self.cache = {}
        
    def sharpe_ratio(
        self, 
        returns: Union[List[float], np.ndarray], 
        risk_free_rate: float = 0.02
    ) -> float:
        """
        Calculate Sharpe ratio.
        
        Args:
            returns: Portfolio returns
            risk_free_rate: Risk-free rate (default 2%)
            
        Returns:
            Sharpe ratio value
        """
        r = _to_series(returns)
        if r.size < 2:
            return 0.0
            
        excess_returns = r - risk_free_rate / 252  # Daily risk-free rate
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)
        
        if std_excess == 0 or np.isclose(std_excess, 0):
            return 0.0
            
        return float(mean_excess / std_excess * np.sqrt(252))  # Annualized
    
    def sortino_ratio(
        self, 
        returns: Union[List[float], np.ndarray], 
        risk_free_rate: float = 0.02,
        target_return: Optional[float] = None
    ) -> float:
        """
        Calculate Sortino ratio.
        
        Args:
            returns: Portfolio returns
            risk_free_rate: Risk-free rate (default 2%)
            target_return: Target return (defaults to risk-free rate)
            
        Returns:
            Sortino ratio value
        """
        r = _to_series(returns)
        if r.size < 2:
            return 0.0
            
        target = target_return if target_return is not None else risk_free_rate / 252
        excess_returns = r - target
        mean_excess = np.mean(excess_returns)
        
        # Downside deviation
        downside_returns = excess_returns[excess_returns < 0]
        if downside_returns.size == 0:
            return float('inf') if mean_excess > 0 else 0.0
            
        downside_std = np.sqrt(np.mean(downside_returns ** 2))
        if downside_std == 0:
            return 0.0
            
        return float(mean_excess / downside_std * np.sqrt(252))  # Annualized
    
    def calmar_ratio(
        self, 
        returns: Union[List[float], np.ndarray], 
        risk_free_rate: float = 0.02
    ) -> float:
        """
        Calculate Calmar ratio (annual return / max drawdown).
        
        Args:
            returns: Portfolio returns
            risk_free_rate: Risk-free rate for excess returns
            
        Returns:
            Calmar ratio value
        """
        r = _to_series(returns)
        if r.size < 2:
            return 0.0
            
        annual_return = np.mean(r) * 252 - risk_free_rate
        max_dd = self.maximum_drawdown(r)
        
        if max_dd == 0:
            return float('inf') if annual_return > 0 else 0.0
            
        return float(annual_return / abs(max_dd))
    
    def maximum_drawdown(self, returns: Union[List[float], np.ndarray]) -> float:
        """
        Calculate maximum drawdown.
        
        Args:
            returns: Portfolio returns
            
        Returns:
            Maximum drawdown as negative value
        """
        r = _to_series(returns)
        if r.size == 0:
            return 0.0
            
        # Calculate cumulative returns
        cum_returns = np.cumprod(1 + r)
        running_max = np.maximum.accumulate(cum_returns)
        drawdown = (cum_returns - running_max) / running_max
        
        return float(np.min(drawdown))
    
    def beta_calculation(
        self, 
        portfolio_returns: Union[List[float], np.ndarray],
        market_returns: Union[List[float], np.ndarray]
    ) -> float:
        """
        Calculate portfolio beta relative to market.
        
        Args:
            portfolio_returns: Portfolio returns
            market_returns: Market benchmark returns
            
        Returns:
            Beta coefficient
        """
        port_r = _to_series(portfolio_returns)
        market_r = _to_series(market_returns)
        
        min_len = min(port_r.size, market_r.size)
        if min_len < 2:
            return 1.0  # Default beta
            
        port_r = port_r[:min_len]
        market_r = market_r[:min_len]
        
        covariance = np.cov(port_r, market_r)[0, 1]
        market_variance = np.var(market_r, ddof=1)
        
        if market_variance == 0:
            return 1.0
            
        return float(covariance / market_variance)
    
    def alpha_calculation(
        self, 
        portfolio_returns: Union[List[float], np.ndarray],
        market_returns: Union[List[float], np.ndarray],
        risk_free_rate: float = 0.02
    ) -> float:
        """
        Calculate Jensen's alpha.
        
        Args:
            portfolio_returns: Portfolio returns
            market_returns: Market benchmark returns
            risk_free_rate: Risk-free rate
            
        Returns:
            Alpha value (excess return over CAPM prediction)
        """
        port_r = _to_series(portfolio_returns)
        market_r = _to_series(market_returns)
        
        min_len = min(port_r.size, market_r.size)
        if min_len < 2:
            return 0.0
            
        port_r = port_r[:min_len]
        market_r = market_r[:min_len]
        
        rf_daily = risk_free_rate / 252
        
        # Excess returns
        port_excess = port_r - rf_daily
        market_excess = market_r - rf_daily
        
        # Calculate beta
        beta = self.beta_calculation(port_r, market_r)
        
        # Calculate alpha
        port_mean = np.mean(port_excess)
        market_mean = np.mean(market_excess)
        
        alpha = port_mean - beta * market_mean
        return float(alpha * 252)  # Annualized
    
    def volatility_metrics(self, returns: Union[List[float], np.ndarray]) -> Dict[str, float]:
        """
        Calculate comprehensive volatility metrics.
        
        Args:
            returns: Portfolio returns
            
        Returns:
            Dictionary of volatility metrics
        """
        r = _to_series(returns)
        if r.size < 2:
            return {
                'daily_volatility': 0.0,
                'annual_volatility': 0.0,
                'rolling_vol_30d': 0.0,
                'vol_of_vol': 0.0
            }
        
        daily_vol = np.std(r, ddof=1)
        annual_vol = daily_vol * np.sqrt(252)
        
        # Rolling 30-day volatility
        if r.size >= 30:
            rolling_vols = []
            for i in range(30, r.size + 1):
                window = r[i-30:i]
                rolling_vols.append(np.std(window, ddof=1))
            rolling_vol_30d = np.mean(rolling_vols) if rolling_vols else daily_vol
            vol_of_vol = np.std(rolling_vols, ddof=1) if len(rolling_vols) > 1 else 0.0
        else:
            rolling_vol_30d = daily_vol
            vol_of_vol = 0.0
        
        return {
            'daily_volatility': float(daily_vol),
            'annual_volatility': float(annual_vol),
            'rolling_vol_30d': float(rolling_vol_30d),
            'vol_of_vol': float(vol_of_vol)
        }
    
    def correlation_metrics(
        self, 
        portfolio_returns: Union[List[float], np.ndarray],
        benchmark_returns: Union[List[float], np.ndarray]
    ) -> Dict[str, float]:
        """
        Calculate correlation metrics.
        
        Args:
            portfolio_returns: Portfolio returns
            benchmark_returns: Benchmark returns
            
        Returns:
            Dictionary of correlation metrics
        """
        port_r = _to_series(portfolio_returns)
        bench_r = _to_series(benchmark_returns)
        
        min_len = min(port_r.size, bench_r.size)
        if min_len < 2:
            return {
                'correlation': 0.0,
                'tracking_error': 0.0,
                'information_ratio': 0.0,
                'upside_capture': 0.0,
                'downside_capture': 0.0
            }
        
        port_r = port_r[:min_len]
        bench_r = bench_r[:min_len]
        
        # Correlation
        correlation = np.corrcoef(port_r, bench_r)[0, 1]
        if np.isnan(correlation):
            correlation = 0.0
        
        # Tracking error
        tracking_diff = port_r - bench_r
        tracking_error = np.std(tracking_diff, ddof=1) * np.sqrt(252)
        
        # Information ratio
        mean_diff = np.mean(tracking_diff) * 252
        information_ratio = mean_diff / tracking_error if tracking_error > 0 else 0.0
        
        # Capture ratios
        upside_periods = bench_r > 0
        downside_periods = bench_r < 0
        
        if np.any(upside_periods) and np.mean(bench_r[upside_periods]) != 0:
            upside_capture = np.mean(port_r[upside_periods]) / np.mean(bench_r[upside_periods])
        else:
            upside_capture = 0.0
            
        if np.any(downside_periods) and np.mean(bench_r[downside_periods]) != 0:
            downside_capture = np.mean(port_r[downside_periods]) / np.mean(bench_r[downside_periods])
        else:
            downside_capture = 0.0
        
        return {
            'correlation': float(correlation),
            'tracking_error': float(tracking_error),
            'information_ratio': float(information_ratio),
            'upside_capture': float(upside_capture),
            'downside_capture': float(downside_capture)
        }
    
    def risk_adjusted_returns(
        self, 
        returns: Union[List[float], np.ndarray],
        benchmark_returns: Optional[Union[List[float], np.ndarray]] = None,
        risk_free_rate: float = 0.02
    ) -> Dict[str, float]:
        """
        Calculate comprehensive risk-adjusted return metrics.
        
        Args:
            returns: Portfolio returns
            benchmark_returns: Optional benchmark returns
            risk_free_rate: Risk-free rate
            
        Returns:
            Dictionary of risk-adjusted metrics
        """
        metrics = {
            'sharpe_ratio': self.sharpe_ratio(returns, risk_free_rate),
            'sortino_ratio': self.sortino_ratio(returns, risk_free_rate),
            'calmar_ratio': self.calmar_ratio(returns, risk_free_rate),
            'max_drawdown': self.maximum_drawdown(returns)
        }
        
        if benchmark_returns is not None:
            metrics.update({
                'beta': self.beta_calculation(returns, benchmark_returns),
                'alpha': self.alpha_calculation(returns, benchmark_returns, risk_free_rate),
                **self.correlation_metrics(returns, benchmark_returns)
            })
        
        return metrics
    
    def portfolio_risk_summary(
        self, 
        returns: Union[List[float], np.ndarray],
        positions: Optional[List[Dict[str, Any]]] = None,
        benchmark_returns: Optional[Union[List[float], np.ndarray]] = None
    ) -> Dict[str, Any]:
        """
        Generate comprehensive portfolio risk summary.
        
        Args:
            returns: Portfolio returns
            positions: Optional position data
            benchmark_returns: Optional benchmark returns
            
        Returns:
            Comprehensive risk metrics dictionary
        """
        r = _to_series(returns)
        
        summary = {
            'return_metrics': {
                'total_return': float(np.prod(1 + r) - 1) if r.size > 0 else 0.0,
                'annualized_return': float(np.mean(r) * 252) if r.size > 0 else 0.0,
                'daily_return_mean': float(np.mean(r)) if r.size > 0 else 0.0,
                'daily_return_std': float(np.std(r, ddof=1)) if r.size > 1 else 0.0
            },
            'risk_metrics': self.risk_adjusted_returns(r, benchmark_returns),
            'volatility_metrics': self.volatility_metrics(r),
            'var_metrics': coherent_risk_measures(r, 0.95)
        }
        
        if positions:
            # Add position-based metrics
            total_value = sum(abs(float(pos.get('value', 0))) for pos in positions)
            position_count = len(positions)
            
            summary['position_metrics'] = {
                'total_positions': position_count,
                'total_exposure': total_value,
                'average_position_size': total_value / position_count if position_count > 0 else 0.0,
                'concentration_risk': max(
                    abs(float(pos.get('value', 0))) / total_value 
                    for pos in positions
                ) if total_value > 0 and positions else 0.0
            }
        
        return summary


# Global instance
risk_metrics = RiskMetrics()

# Convenience functions for direct usage
def sharpe_ratio(returns: Union[List[float], np.ndarray], risk_free_rate: float = 0.02) -> float:
    """Calculate Sharpe ratio."""
    return risk_metrics.sharpe_ratio(returns, risk_free_rate)

def sortino_ratio(returns: Union[List[float], np.ndarray], risk_free_rate: float = 0.02) -> float:
    """Calculate Sortino ratio."""
    return risk_metrics.sortino_ratio(returns, risk_free_rate)

def maximum_drawdown(returns: Union[List[float], np.ndarray]) -> float:
    """Calculate maximum drawdown."""
    return risk_metrics.maximum_drawdown(returns)

def beta_calculation(portfolio_returns: Union[List[float], np.ndarray], market_returns: Union[List[float], np.ndarray]) -> float:
    """Calculate portfolio beta."""
    return risk_metrics.beta_calculation(portfolio_returns, market_returns)

def alpha_calculation(portfolio_returns: Union[List[float], np.ndarray], market_returns: Union[List[float], np.ndarray], risk_free_rate: float = 0.02) -> float:
    """Calculate Jensen's alpha."""
    return risk_metrics.alpha_calculation(portfolio_returns, market_returns, risk_free_rate)

def volatility_metrics(returns: Union[List[float], np.ndarray]) -> Dict[str, float]:
    """Calculate volatility metrics."""
    return risk_metrics.volatility_metrics(returns)

def correlation_metrics(portfolio_returns: Union[List[float], np.ndarray], benchmark_returns: Union[List[float], np.ndarray]) -> Dict[str, float]:
    """Calculate correlation metrics."""
    return risk_metrics.correlation_metrics(portfolio_returns, benchmark_returns)

def risk_adjusted_returns(returns: Union[List[float], np.ndarray], benchmark_returns: Optional[Union[List[float], np.ndarray]] = None, risk_free_rate: float = 0.02) -> Dict[str, float]:
    """Calculate risk-adjusted return metrics."""
    return risk_metrics.risk_adjusted_returns(returns, benchmark_returns, risk_free_rate)

def get_risk_metrics() -> RiskMetrics:
    """Get risk metrics calculator instance."""
    return risk_metrics