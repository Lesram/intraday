"""
Comprehensive analytics service for trading and portfolio analysis.

Provides advanced analytics capabilities including:
- Performance analytics (returns, Sharpe ratio, etc.)
- Trading analytics (win rate, profit factor, etc.)
- Portfolio analytics (allocation, concentration, etc.)
- Market analytics (correlation, beta, etc.)
- Risk analytics (VaR, drawdown, volatility)
- Statistical analysis (regression, distributions)
- Trend analysis (momentum, mean reversion)
- Correlation analysis (asset relationships)
"""

import asyncio
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from dataclasses import dataclass

# Import our risk metrics
from ..risk.metrics import RiskMetrics
from ..risk.math import value_at_risk, conditional_var, coherent_risk_measures

logger = logging.getLogger(__name__)


@dataclass
class AnalyticsConfig:
    """Configuration for analytics service."""
    lookback_days: int = 252
    risk_free_rate: float = 0.02
    confidence_levels: List[float] = None
    benchmark_symbol: str = "SPY"
    
    def __post_init__(self):
        if self.confidence_levels is None:
            self.confidence_levels = [0.90, 0.95, 0.99]


@dataclass
class PerformanceMetrics:
    """Performance analytics results."""
    total_return: float
    annualized_return: float
    volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float


@dataclass
class TradingMetrics:
    """Trading analytics results."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float
    consecutive_wins: int
    consecutive_losses: int


@dataclass
class PortfolioMetrics:
    """Portfolio analytics results."""
    total_value: float
    cash_allocation: float
    equity_allocation: float
    sector_concentration: Dict[str, float]
    position_count: int
    average_position_size: float
    concentration_risk: float


class AnalyticsService:
    """Comprehensive analytics service for trading and portfolio analysis."""
    
    def __init__(self, config: Optional[AnalyticsConfig] = None):
        """Initialize analytics service."""
        self.config = config or AnalyticsConfig()
        self.risk_metrics = RiskMetrics()
        self._cache = {}
        
    async def performance_analytics(
        self, 
        returns: Union[List[float], np.ndarray, pd.Series],
        benchmark_returns: Optional[Union[List[float], np.ndarray, pd.Series]] = None
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance analytics.
        
        Args:
            returns: Portfolio returns data
            benchmark_returns: Optional benchmark returns for comparison
            
        Returns:
            PerformanceMetrics with comprehensive performance analysis
        """
        returns_array = self._to_array(returns)
        
        if len(returns_array) == 0:
            return PerformanceMetrics(
                total_return=0.0, annualized_return=0.0, volatility=0.0,
                sharpe_ratio=0.0, sortino_ratio=0.0, max_drawdown=0.0,
                calmar_ratio=0.0, win_rate=0.0, profit_factor=0.0
            )
        
        # Basic return metrics
        total_return = float(np.prod(1 + returns_array) - 1)
        annualized_return = float(np.mean(returns_array) * 252)
        volatility = float(np.std(returns_array, ddof=1) * np.sqrt(252))
        
        # Risk-adjusted metrics
        sharpe_ratio = self.risk_metrics.sharpe_ratio(returns_array, self.config.risk_free_rate)
        sortino_ratio = self.risk_metrics.sortino_ratio(returns_array, self.config.risk_free_rate)
        max_drawdown = self.risk_metrics.maximum_drawdown(returns_array)
        calmar_ratio = self.risk_metrics.calmar_ratio(returns_array, self.config.risk_free_rate)
        
        # Trading metrics
        winning_returns = returns_array[returns_array > 0]
        losing_returns = returns_array[returns_array < 0]
        
        win_rate = len(winning_returns) / len(returns_array) if len(returns_array) > 0 else 0.0
        
        total_gains = np.sum(winning_returns) if len(winning_returns) > 0 else 0.0
        total_losses = abs(np.sum(losing_returns)) if len(losing_returns) > 0 else 0.0
        profit_factor = total_gains / total_losses if total_losses > 0 else float('inf')
        
        return PerformanceMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor
        )
    
    async def trading_analytics(
        self, 
        trades: List[Dict[str, Any]]
    ) -> TradingMetrics:
        """
        Calculate comprehensive trading analytics.
        
        Args:
            trades: List of trade dictionaries with 'pnl' field
            
        Returns:
            TradingMetrics with comprehensive trading analysis
        """
        if not trades:
            return TradingMetrics(
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0.0, profit_factor=0.0, average_win=0.0,
                average_loss=0.0, largest_win=0.0, largest_loss=0.0,
                consecutive_wins=0, consecutive_losses=0
            )
        
        pnls = [float(trade.get('pnl', 0)) for trade in trades]
        
        total_trades = len(trades)
        winning_trades = len([pnl for pnl in pnls if pnl > 0])
        losing_trades = len([pnl for pnl in pnls if pnl < 0])
        
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0
        
        # Profit metrics
        winning_pnls = [pnl for pnl in pnls if pnl > 0]
        losing_pnls = [pnl for pnl in pnls if pnl < 0]
        
        total_gains = sum(winning_pnls) if winning_pnls else 0.0
        total_losses = abs(sum(losing_pnls)) if losing_pnls else 0.0
        profit_factor = total_gains / total_losses if total_losses > 0 else float('inf')
        
        average_win = np.mean(winning_pnls) if winning_pnls else 0.0
        average_loss = np.mean(losing_pnls) if losing_pnls else 0.0
        largest_win = max(winning_pnls) if winning_pnls else 0.0
        largest_loss = min(losing_pnls) if losing_pnls else 0.0
        
        # Consecutive streaks
        consecutive_wins = self._max_consecutive(pnls, lambda x: x > 0)
        consecutive_losses = self._max_consecutive(pnls, lambda x: x < 0)
        
        return TradingMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            average_win=average_win,
            average_loss=average_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            consecutive_wins=consecutive_wins,
            consecutive_losses=consecutive_losses
        )
    
    async def portfolio_analytics(
        self, 
        positions: List[Dict[str, Any]],
        cash: float = 0.0
    ) -> PortfolioMetrics:
        """
        Calculate comprehensive portfolio analytics.
        
        Args:
            positions: List of position dictionaries
            cash: Cash holdings
            
        Returns:
            PortfolioMetrics with comprehensive portfolio analysis
        """
        if not positions:
            return PortfolioMetrics(
                total_value=cash,
                cash_allocation=1.0,
                equity_allocation=0.0,
                sector_concentration={},
                position_count=0,
                average_position_size=0.0,
                concentration_risk=0.0
            )
        
        # Calculate position values
        position_values = []
        sectors = {}
        
        for pos in positions:
            value = abs(float(pos.get('value', 0)))
            position_values.append(value)
            
            sector = pos.get('sector', 'Unknown')
            sectors[sector] = sectors.get(sector, 0.0) + value
        
        total_equity = sum(position_values)
        total_value = total_equity + cash
        
        # Allocation metrics
        cash_allocation = cash / total_value if total_value > 0 else 1.0
        equity_allocation = total_equity / total_value if total_value > 0 else 0.0
        
        # Sector concentration
        sector_concentration = {
            sector: value / total_equity 
            for sector, value in sectors.items()
        } if total_equity > 0 else {}
        
        # Position metrics
        position_count = len(positions)
        average_position_size = total_equity / position_count if position_count > 0 else 0.0
        
        # Concentration risk (largest position as % of portfolio)
        concentration_risk = max(position_values) / total_value if total_value > 0 and position_values else 0.0
        
        return PortfolioMetrics(
            total_value=total_value,
            cash_allocation=cash_allocation,
            equity_allocation=equity_allocation,
            sector_concentration=sector_concentration,
            position_count=position_count,
            average_position_size=average_position_size,
            concentration_risk=concentration_risk
        )
    
    async def market_analytics(
        self, 
        portfolio_returns: Union[List[float], np.ndarray],
        market_returns: Union[List[float], np.ndarray]
    ) -> Dict[str, float]:
        """
        Calculate market analytics comparing portfolio to market.
        
        Args:
            portfolio_returns: Portfolio returns
            market_returns: Market benchmark returns
            
        Returns:
            Dictionary with market analytics metrics
        """
        port_array = self._to_array(portfolio_returns)
        market_array = self._to_array(market_returns)
        
        min_len = min(len(port_array), len(market_array))
        if min_len < 2:
            return {
                'beta': 1.0,
                'alpha': 0.0,
                'correlation': 0.0,
                'tracking_error': 0.0,
                'information_ratio': 0.0,
                'upside_capture': 0.0,
                'downside_capture': 0.0
            }
        
        port_aligned = port_array[:min_len]
        market_aligned = market_array[:min_len]
        
        # Market metrics
        beta = self.risk_metrics.beta_calculation(port_aligned, market_aligned)
        alpha = self.risk_metrics.alpha_calculation(port_aligned, market_aligned, self.config.risk_free_rate)
        correlation_metrics = self.risk_metrics.correlation_metrics(port_aligned, market_aligned)
        
        return {
            'beta': beta,
            'alpha': alpha,
            **correlation_metrics
        }
    
    async def risk_analytics(
        self, 
        returns: Union[List[float], np.ndarray],
        positions: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive risk analytics.
        
        Args:
            returns: Portfolio returns
            positions: Optional position data
            
        Returns:
            Dictionary with comprehensive risk metrics
        """
        returns_array = self._to_array(returns)
        
        # VaR metrics for different confidence levels
        var_metrics = {}
        for confidence in self.config.confidence_levels:
            var_metrics[f'var_{int(confidence*100)}'] = value_at_risk(returns_array, confidence)
            var_metrics[f'cvar_{int(confidence*100)}'] = conditional_var(returns_array, confidence)
        
        # Volatility analysis
        vol_metrics = self.risk_metrics.volatility_metrics(returns_array)
        
        # Risk summary
        risk_summary = {
            **var_metrics,
            **vol_metrics,
            'max_drawdown': self.risk_metrics.maximum_drawdown(returns_array),
            'sharpe_ratio': self.risk_metrics.sharpe_ratio(returns_array, self.config.risk_free_rate),
            'sortino_ratio': self.risk_metrics.sortino_ratio(returns_array, self.config.risk_free_rate)
        }
        
        # Add position-based risk if available
        if positions:
            portfolio_risk = self.risk_metrics.portfolio_risk_summary(returns_array, positions)
            risk_summary.update(portfolio_risk.get('position_metrics', {}))
        
        return risk_summary
    
    async def statistical_analysis(
        self, 
        data: Union[List[float], np.ndarray]
    ) -> Dict[str, float]:
        """
        Perform statistical analysis on data.
        
        Args:
            data: Numerical data for analysis
            
        Returns:
            Dictionary with statistical metrics
        """
        array_data = self._to_array(data)
        
        if len(array_data) == 0:
            return {
                'mean': 0.0, 'median': 0.0, 'std': 0.0, 'variance': 0.0,
                'skewness': 0.0, 'kurtosis': 0.0, 'min': 0.0, 'max': 0.0,
                'percentile_25': 0.0, 'percentile_75': 0.0, 'iqr': 0.0
            }
        
        # Basic statistics
        mean = float(np.mean(array_data))
        median = float(np.median(array_data))
        std = float(np.std(array_data, ddof=1)) if len(array_data) > 1 else 0.0
        variance = float(np.var(array_data, ddof=1)) if len(array_data) > 1 else 0.0
        
        # Distribution statistics - fallback implementations
        skewness = self._calculate_skewness(array_data) if len(array_data) > 2 else 0.0
        kurtosis = self._calculate_kurtosis(array_data) if len(array_data) > 3 else 0.0
        
        # Range statistics
        data_min = float(np.min(array_data))
        data_max = float(np.max(array_data))
        
        # Percentiles
        try:
            percentile_25 = float(np.percentile(array_data, 25))
            percentile_75 = float(np.percentile(array_data, 75))
        except (ValueError, TypeError):
            # Fallback for percentile calculation
            sorted_data = np.sort(array_data)
            n = len(sorted_data)
            percentile_25 = float(sorted_data[int(0.25 * (n - 1))])
            percentile_75 = float(sorted_data[int(0.75 * (n - 1))])
        
        iqr = percentile_75 - percentile_25
        
        return {
            'mean': mean,
            'median': median,
            'std': std,
            'variance': variance,
            'skewness': skewness,
            'kurtosis': kurtosis,
            'min': data_min,
            'max': data_max,
            'percentile_25': percentile_25,
            'percentile_75': percentile_75,
            'iqr': iqr
        }
    
    async def trend_analysis(
        self, 
        prices: Union[List[float], np.ndarray],
        window: int = 20
    ) -> Dict[str, Any]:
        """
        Perform trend analysis on price data.
        
        Args:
            prices: Price data
            window: Moving average window
            
        Returns:
            Dictionary with trend analysis results
        """
        price_array = self._to_array(prices)
        
        if len(price_array) < window:
            return {
                'trend_direction': 'neutral',
                'trend_strength': 0.0,
                'moving_average': float(np.mean(price_array)) if len(price_array) > 0 else 0.0,
                'momentum': 0.0,
                'rsi': 50.0
            }
        
        # Moving average
        moving_avg = np.convolve(price_array, np.ones(window)/window, mode='valid')
        current_ma = float(moving_avg[-1])
        
        # Trend direction and strength
        if len(moving_avg) > 1:
            trend_slope = (moving_avg[-1] - moving_avg[0]) / len(moving_avg)
            trend_direction = 'bullish' if trend_slope > 0 else 'bearish' if trend_slope < 0 else 'neutral'
            trend_strength = abs(trend_slope) / np.std(moving_avg) if np.std(moving_avg) > 0 else 0.0
        else:
            trend_direction = 'neutral'
            trend_strength = 0.0
        
        # Momentum (rate of change)
        if len(price_array) >= window:
            momentum = (price_array[-1] - price_array[-window]) / price_array[-window]
        else:
            momentum = 0.0
        
        # RSI calculation
        rsi = self._calculate_rsi(price_array, window=min(14, len(price_array)//2))
        
        return {
            'trend_direction': trend_direction,
            'trend_strength': float(trend_strength),
            'moving_average': current_ma,
            'momentum': float(momentum),
            'rsi': rsi
        }
    
    async def correlation_analysis(
        self, 
        data1: Union[List[float], np.ndarray],
        data2: Union[List[float], np.ndarray],
        method: str = 'pearson'
    ) -> Dict[str, float]:
        """
        Perform correlation analysis between two datasets.
        
        Args:
            data1: First dataset
            data2: Second dataset
            method: Correlation method ('pearson', 'spearman', 'kendall')
            
        Returns:
            Dictionary with correlation analysis results
        """
        array1 = self._to_array(data1)
        array2 = self._to_array(data2)
        
        min_len = min(len(array1), len(array2))
        if min_len < 2:
            return {
                'correlation': 0.0,
                'p_value': 1.0,
                'r_squared': 0.0,
                'rolling_correlation': 0.0
            }
        
        aligned1 = array1[:min_len]
        aligned2 = array2[:min_len]
        
        # Calculate correlation using numpy (fallback implementation)
        if method == 'pearson':
            correlation, p_value = self._pearson_correlation(aligned1, aligned2)
        elif method == 'spearman':
            # Spearman is Pearson on ranks
            ranks1 = self._rank_data(aligned1)
            ranks2 = self._rank_data(aligned2)
            correlation, p_value = self._pearson_correlation(ranks1, ranks2)
        else:
            # Default to Pearson
            correlation, p_value = self._pearson_correlation(aligned1, aligned2)
        
        # Handle NaN values
        if np.isnan(correlation):
            correlation = 0.0
        if np.isnan(p_value):
            p_value = 1.0
        
        r_squared = correlation ** 2
        
        # Rolling correlation (last 30 observations)
        window = min(30, min_len)
        if min_len >= window:
            recent1 = aligned1[-window:]
            recent2 = aligned2[-window:]
            rolling_corr, _ = self._pearson_correlation(recent1, recent2)
            rolling_correlation = rolling_corr if not np.isnan(rolling_corr) else 0.0
        else:
            rolling_correlation = correlation
        
        return {
            'correlation': float(correlation),
            'p_value': float(p_value),
            'r_squared': float(r_squared),
            'rolling_correlation': float(rolling_correlation)
        }
    
    def _to_array(self, data: Union[List[float], np.ndarray, pd.Series]) -> np.ndarray:
        """Convert data to numpy array."""
        if isinstance(data, pd.Series):
            return data.values
        elif isinstance(data, list):
            return np.array(data, dtype=float)
        elif isinstance(data, np.ndarray):
            return data.astype(float)
        else:
            return np.array([], dtype=float)
    
    def _max_consecutive(self, data: List[float], condition) -> int:
        """Calculate maximum consecutive occurrences of condition."""
        max_count = 0
        current_count = 0
        
        for value in data:
            if condition(value):
                current_count += 1
                max_count = max(max_count, current_count)
            else:
                current_count = 0
        
        return max_count
    
    def _calculate_rsi(self, prices: np.ndarray, window: int = 14) -> float:
        """Calculate Relative Strength Index."""
        if len(prices) < window + 1:
            return 50.0
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-window:])
        avg_loss = np.mean(losses[-window:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    def _calculate_skewness(self, data: np.ndarray) -> float:
        """Calculate skewness using method of moments."""
        if len(data) < 3:
            return 0.0
        
        mean = np.mean(data)
        std = np.std(data, ddof=1)
        
        if std == 0:
            return 0.0
        
        n = len(data)
        m3 = np.sum((data - mean) ** 3) / n
        skew = m3 / (std ** 3)
        
        # Bias correction
        skew_corrected = skew * np.sqrt(n * (n - 1)) / (n - 2)
        
        return float(skew_corrected)
    
    def _calculate_kurtosis(self, data: np.ndarray) -> float:
        """Calculate excess kurtosis using method of moments."""
        if len(data) < 4:
            return 0.0
        
        mean = np.mean(data)
        std = np.std(data, ddof=1)
        
        if std == 0:
            return 0.0
        
        n = len(data)
        m4 = np.sum((data - mean) ** 4) / n
        kurt = m4 / (std ** 4) - 3  # Excess kurtosis
        
        # Bias correction
        kurt_corrected = ((n - 1) / ((n - 2) * (n - 3))) * ((n + 1) * kurt + 6)
        
        return float(kurt_corrected)
    
    def _pearson_correlation(self, x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
        """Calculate Pearson correlation coefficient and approximate p-value."""
        if len(x) != len(y) or len(x) < 2:
            return 0.0, 1.0
        
        # Calculate correlation coefficient
        correlation = np.corrcoef(x, y)[0, 1]
        
        if np.isnan(correlation):
            return 0.0, 1.0
        
        # Approximate p-value using t-distribution
        n = len(x)
        t_stat = correlation * np.sqrt((n - 2) / (1 - correlation**2)) if abs(correlation) < 1 else float('inf')
        
        # Simple approximation for p-value (not exact but sufficient for our needs)
        df = n - 2
        if abs(t_stat) > 2.576:  # 99% confidence
            p_value = 0.01
        elif abs(t_stat) > 1.96:  # 95% confidence
            p_value = 0.05
        elif abs(t_stat) > 1.645:  # 90% confidence
            p_value = 0.10
        else:
            p_value = 0.20
        
        return float(correlation), float(p_value)
    
    def _rank_data(self, data: np.ndarray) -> np.ndarray:
        """Calculate ranks of data (for Spearman correlation)."""
        sorted_indices = np.argsort(data)
        ranks = np.empty_like(sorted_indices, dtype=float)
        ranks[sorted_indices] = np.arange(1, len(data) + 1)
        return ranks


# Global instance
analytics_service = AnalyticsService()

# Convenience functions
async def performance_analytics(returns, benchmark_returns=None):
    """Calculate performance analytics."""
    return await analytics_service.performance_analytics(returns, benchmark_returns)

async def trading_analytics(trades):
    """Calculate trading analytics."""
    return await analytics_service.trading_analytics(trades)

async def portfolio_analytics(positions, cash=0.0):
    """Calculate portfolio analytics."""
    return await analytics_service.portfolio_analytics(positions, cash)

async def market_analytics(portfolio_returns, market_returns):
    """Calculate market analytics."""
    return await analytics_service.market_analytics(portfolio_returns, market_returns)

async def risk_analytics(returns, positions=None):
    """Calculate risk analytics."""
    return await analytics_service.risk_analytics(returns, positions)

async def statistical_analysis(data):
    """Perform statistical analysis."""
    return await analytics_service.statistical_analysis(data)

async def trend_analysis(prices, window=20):
    """Perform trend analysis."""
    return await analytics_service.trend_analysis(prices, window)

async def correlation_analysis(data1, data2, method='pearson'):
    """Perform correlation analysis."""
    return await analytics_service.correlation_analysis(data1, data2, method)

def get_analytics_service():
    """Get analytics service instance."""
    return analytics_service