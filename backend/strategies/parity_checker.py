"""
Backtest vs Live Parity Check (M-42)

Provides comparison between backtest results and live performance to detect:
- Strategy behavior drift
- Execution quality issues
- Market regime changes
- Model degradation

Follows the existing project patterns with async/await and proper logging.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, date, timedelta
from enum import Enum
from typing import Any
import logging
import statistics

import numpy as np

logger = logging.getLogger(__name__)


class ParityStatus(Enum):
    """Status of backtest/live parity."""
    ALIGNED = "aligned"              # Performance matches within tolerance
    MINOR_DEVIATION = "minor_deviation"  # Small deviation, monitoring needed
    MAJOR_DEVIATION = "major_deviation"  # Significant deviation, investigation needed
    CRITICAL_DIVERGENCE = "critical_divergence"  # Critical divergence, stop strategy
    INSUFFICIENT_DATA = "insufficient_data"  # Not enough data to compare


@dataclass
class ParityMetrics:
    """Metrics comparing backtest to live performance."""
    
    # Return comparison
    backtest_return: float
    live_return: float
    return_difference: float
    return_correlation: float
    
    # Win rate comparison
    backtest_win_rate: float
    live_win_rate: float
    win_rate_difference: float
    
    # Trade frequency comparison
    backtest_trades_per_day: float
    live_trades_per_day: float
    trade_frequency_ratio: float
    
    # Risk metrics comparison
    backtest_max_drawdown: float
    live_max_drawdown: float
    drawdown_difference: float
    
    # Execution quality
    avg_slippage: float
    fill_rate: float
    execution_delay_ms: float
    
    # Overall scores
    parity_score: float  # 0-1, higher is better
    status: ParityStatus
    
    # Metadata
    backtest_period: str
    live_period: str
    comparison_date: datetime
    
    # Details
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class DailyPerformance:
    """Daily performance record for comparison."""
    date: date
    pnl: float
    trades_count: int
    win_count: int
    loss_count: int
    equity: float
    max_drawdown: float = 0.0


class ParityChecker:
    """
    Compares backtest results against live trading performance.
    
    Detects divergences that may indicate:
    - Strategy decay / market regime change
    - Execution quality issues (slippage, latency)
    - Data quality differences
    - Implementation bugs
    
    Usage:
        checker = ParityChecker(
            return_tolerance=0.10,  # 10% return difference tolerance
            win_rate_tolerance=0.05,  # 5% win rate difference tolerance
        )
        
        metrics = checker.compare(backtest_results, live_results)
        
        if metrics.status == ParityStatus.CRITICAL_DIVERGENCE:
            # Alert and potentially stop strategy
            pass
    """
    
    def __init__(
        self,
        return_tolerance: float = 0.10,
        win_rate_tolerance: float = 0.05,
        trade_frequency_tolerance: float = 0.30,
        drawdown_tolerance: float = 0.05,
        min_comparison_days: int = 20,
    ):
        """
        Initialize parity checker with tolerance thresholds.
        
        Args:
            return_tolerance: Max acceptable return difference (as decimal)
            win_rate_tolerance: Max acceptable win rate difference
            trade_frequency_tolerance: Max acceptable trade frequency ratio difference
            drawdown_tolerance: Max acceptable drawdown difference
            min_comparison_days: Minimum days needed for valid comparison
        """
        self.return_tolerance = return_tolerance
        self.win_rate_tolerance = win_rate_tolerance
        self.trade_frequency_tolerance = trade_frequency_tolerance
        self.drawdown_tolerance = drawdown_tolerance
        self.min_comparison_days = min_comparison_days
    
    def compare(
        self,
        backtest_daily: list[DailyPerformance],
        live_daily: list[DailyPerformance],
        execution_stats: dict[str, Any] | None = None,
    ) -> ParityMetrics:
        """
        Compare backtest and live performance.
        
        Args:
            backtest_daily: Daily performance from backtest
            live_daily: Daily performance from live trading
            execution_stats: Optional execution quality stats
            
        Returns:
            ParityMetrics with comparison results
        """
        now = datetime.now(UTC)
        issues: list[str] = []
        recommendations: list[str] = []
        
        # Check data sufficiency
        if len(backtest_daily) < self.min_comparison_days or len(live_daily) < self.min_comparison_days:
            return ParityMetrics(
                backtest_return=0.0,
                live_return=0.0,
                return_difference=0.0,
                return_correlation=0.0,
                backtest_win_rate=0.0,
                live_win_rate=0.0,
                win_rate_difference=0.0,
                backtest_trades_per_day=0.0,
                live_trades_per_day=0.0,
                trade_frequency_ratio=1.0,
                backtest_max_drawdown=0.0,
                live_max_drawdown=0.0,
                drawdown_difference=0.0,
                avg_slippage=0.0,
                fill_rate=1.0,
                execution_delay_ms=0.0,
                parity_score=0.0,
                status=ParityStatus.INSUFFICIENT_DATA,
                backtest_period="",
                live_period="",
                comparison_date=now,
                issues=["Insufficient data for comparison"],
                recommendations=["Collect more live trading data"],
            )
        
        # Calculate returns
        bt_returns = [d.pnl for d in backtest_daily]
        live_returns = [d.pnl for d in live_daily]
        
        bt_total_return = sum(bt_returns) / backtest_daily[0].equity if backtest_daily[0].equity > 0 else 0
        live_total_return = sum(live_returns) / live_daily[0].equity if live_daily[0].equity > 0 else 0
        return_diff = abs(live_total_return - bt_total_return)
        
        # Calculate return correlation (align by date if possible)
        return_corr = self._calculate_return_correlation(backtest_daily, live_daily)
        
        # Calculate win rates
        bt_total_trades = sum(d.trades_count for d in backtest_daily)
        bt_total_wins = sum(d.win_count for d in backtest_daily)
        live_total_trades = sum(d.trades_count for d in live_daily)
        live_total_wins = sum(d.win_count for d in live_daily)
        
        bt_win_rate = bt_total_wins / bt_total_trades if bt_total_trades > 0 else 0
        live_win_rate = live_total_wins / live_total_trades if live_total_trades > 0 else 0
        win_rate_diff = abs(live_win_rate - bt_win_rate)
        
        # Calculate trade frequency
        bt_days = len(backtest_daily)
        live_days = len(live_daily)
        bt_trades_per_day = bt_total_trades / bt_days if bt_days > 0 else 0
        live_trades_per_day = live_total_trades / live_days if live_days > 0 else 0
        trade_freq_ratio = live_trades_per_day / bt_trades_per_day if bt_trades_per_day > 0 else 1.0
        
        # Calculate max drawdowns
        bt_max_dd = max((d.max_drawdown for d in backtest_daily), default=0.0)
        live_max_dd = max((d.max_drawdown for d in live_daily), default=0.0)
        dd_diff = abs(live_max_dd - bt_max_dd)
        
        # Get execution stats
        exec_stats = execution_stats or {}
        avg_slippage = exec_stats.get("avg_slippage", 0.0)
        fill_rate = exec_stats.get("fill_rate", 1.0)
        exec_delay = exec_stats.get("avg_latency_ms", 0.0)
        
        # Score each dimension (0-1, 1 is perfect match)
        return_score = max(0, 1 - return_diff / (self.return_tolerance * 2))
        win_rate_score = max(0, 1 - win_rate_diff / (self.win_rate_tolerance * 2))
        trade_freq_score = max(0, 1 - abs(1 - trade_freq_ratio) / (self.trade_frequency_tolerance * 2))
        dd_score = max(0, 1 - dd_diff / (self.drawdown_tolerance * 2))
        corr_score = (return_corr + 1) / 2  # Convert from -1,1 to 0,1
        
        # Weighted parity score
        parity_score = (
            0.30 * return_score +
            0.25 * win_rate_score +
            0.15 * trade_freq_score +
            0.15 * dd_score +
            0.15 * corr_score
        )
        
        # Determine status and collect issues
        if return_diff > self.return_tolerance * 2:
            issues.append(f"Return deviation {return_diff:.2%} exceeds critical threshold")
        elif return_diff > self.return_tolerance:
            issues.append(f"Return deviation {return_diff:.2%} exceeds tolerance")
        
        if win_rate_diff > self.win_rate_tolerance * 2:
            issues.append(f"Win rate deviation {win_rate_diff:.2%} exceeds critical threshold")
        elif win_rate_diff > self.win_rate_tolerance:
            issues.append(f"Win rate deviation {win_rate_diff:.2%} exceeds tolerance")
        
        if abs(1 - trade_freq_ratio) > self.trade_frequency_tolerance:
            issues.append(f"Trade frequency ratio {trade_freq_ratio:.2f}x differs from backtest")
        
        if dd_diff > self.drawdown_tolerance * 2:
            issues.append(f"Live drawdown {live_max_dd:.2%} significantly higher than backtest {bt_max_dd:.2%}")
        
        if return_corr < 0.3:
            issues.append(f"Low return correlation ({return_corr:.2f}) suggests strategy behavior change")
        
        if avg_slippage > 0.002:  # > 0.2% slippage
            issues.append(f"High average slippage of {avg_slippage:.3%}")
            recommendations.append("Review execution venues and order types")
        
        if fill_rate < 0.95:
            issues.append(f"Low fill rate of {fill_rate:.1%}")
            recommendations.append("Increase order aggressiveness or reduce position sizes")
        
        # Determine overall status
        if parity_score >= 0.85 and not issues:
            status = ParityStatus.ALIGNED
        elif parity_score >= 0.70 or len(issues) <= 1:
            status = ParityStatus.MINOR_DEVIATION
            recommendations.append("Monitor closely for further divergence")
        elif parity_score >= 0.50 or len(issues) <= 3:
            status = ParityStatus.MAJOR_DEVIATION
            recommendations.append("Investigate root cause of divergence")
            recommendations.append("Consider parameter recalibration")
        else:
            status = ParityStatus.CRITICAL_DIVERGENCE
            recommendations.append("Consider pausing live trading")
            recommendations.append("Perform full strategy review and rebacktest")
        
        # Determine periods
        bt_period = ""
        if backtest_daily:
            bt_period = f"{backtest_daily[0].date} to {backtest_daily[-1].date}"
        
        live_period = ""
        if live_daily:
            live_period = f"{live_daily[0].date} to {live_daily[-1].date}"
        
        logger.info(
            "Parity check completed",
            extra={
                "status": status.value,
                "parity_score": f"{parity_score:.2f}",
                "return_diff": f"{return_diff:.2%}",
                "win_rate_diff": f"{win_rate_diff:.2%}",
                "issues_count": len(issues),
            }
        )
        
        return ParityMetrics(
            backtest_return=bt_total_return,
            live_return=live_total_return,
            return_difference=return_diff,
            return_correlation=return_corr,
            backtest_win_rate=bt_win_rate,
            live_win_rate=live_win_rate,
            win_rate_difference=win_rate_diff,
            backtest_trades_per_day=bt_trades_per_day,
            live_trades_per_day=live_trades_per_day,
            trade_frequency_ratio=trade_freq_ratio,
            backtest_max_drawdown=bt_max_dd,
            live_max_drawdown=live_max_dd,
            drawdown_difference=dd_diff,
            avg_slippage=avg_slippage,
            fill_rate=fill_rate,
            execution_delay_ms=exec_delay,
            parity_score=parity_score,
            status=status,
            backtest_period=bt_period,
            live_period=live_period,
            comparison_date=now,
            issues=issues,
            recommendations=recommendations,
        )
    
    def _calculate_return_correlation(
        self,
        backtest_daily: list[DailyPerformance],
        live_daily: list[DailyPerformance],
    ) -> float:
        """Calculate correlation between backtest and live daily returns."""
        # Create date-indexed maps
        bt_by_date = {d.date: d.pnl for d in backtest_daily}
        live_by_date = {d.date: d.pnl for d in live_daily}
        
        # Find overlapping dates
        common_dates = set(bt_by_date.keys()) & set(live_by_date.keys())
        
        if len(common_dates) < 10:
            # Not enough overlapping data, use sequential comparison
            min_len = min(len(backtest_daily), len(live_daily))
            if min_len < 10:
                return 0.0
            
            bt_returns = [d.pnl for d in backtest_daily[:min_len]]
            live_returns = [d.pnl for d in live_daily[:min_len]]
        else:
            sorted_dates = sorted(common_dates)
            bt_returns = [bt_by_date[d] for d in sorted_dates]
            live_returns = [live_by_date[d] for d in sorted_dates]
        
        # Calculate correlation
        try:
            if len(bt_returns) < 2:
                return 0.0
            
            corr_matrix = np.corrcoef(bt_returns, live_returns)
            corr = corr_matrix[0, 1]
            
            if np.isnan(corr):
                return 0.0
            
            return float(corr)
        except Exception:
            return 0.0
    
    def from_backtest_result(
        self,
        backtest_result: dict[str, Any],
    ) -> list[DailyPerformance]:
        """
        Convert backtest result to daily performance list.
        
        Args:
            backtest_result: Backtest result dictionary with equity_curve
            
        Returns:
            List of DailyPerformance records
        """
        equity_curve = backtest_result.get("equity_curve", [])
        if not equity_curve:
            return []
        
        daily_perf: list[DailyPerformance] = []
        prev_equity = backtest_result.get("initial_capital", 100000)
        peak_equity = prev_equity
        
        for point in equity_curve:
            # Handle both dict and object formats
            if isinstance(point, dict):
                point_date = point.get("date")
                point_equity = point.get("value", point.get("equity", prev_equity))
            else:
                point_date = getattr(point, "date", None)
                point_equity = getattr(point, "value", getattr(point, "equity", prev_equity))
            
            if point_date is None:
                continue
            
            # Parse date if string
            if isinstance(point_date, str):
                point_date = date.fromisoformat(point_date[:10])
            
            pnl = point_equity - prev_equity
            peak_equity = max(peak_equity, point_equity)
            drawdown = (peak_equity - point_equity) / peak_equity if peak_equity > 0 else 0
            
            # For backtest, we estimate trades from trade log if available
            daily_perf.append(DailyPerformance(
                date=point_date,
                pnl=pnl,
                trades_count=0,  # Would need to correlate with trade log
                win_count=0,
                loss_count=0,
                equity=point_equity,
                max_drawdown=drawdown,
            ))
            
            prev_equity = point_equity
        
        # Enrich with trade data if trade log available
        trade_log = backtest_result.get("trade_log", [])
        if trade_log:
            self._enrich_with_trades(daily_perf, trade_log)
        
        return daily_perf
    
    def _enrich_with_trades(
        self,
        daily_perf: list[DailyPerformance],
        trade_log: list[dict[str, Any]],
    ) -> None:
        """Enrich daily performance with trade counts from trade log."""
        # Group trades by date
        trades_by_date: dict[date, list[dict]] = {}
        
        for trade in trade_log:
            trade_date = trade.get("exit_date") or trade.get("entry_date")
            if isinstance(trade_date, str):
                trade_date = date.fromisoformat(trade_date[:10])
            elif hasattr(trade_date, "date"):
                trade_date = trade_date.date() if hasattr(trade_date, "date") else trade_date
            
            if trade_date:
                if trade_date not in trades_by_date:
                    trades_by_date[trade_date] = []
                trades_by_date[trade_date].append(trade)
        
        # Update daily performance
        for perf in daily_perf:
            day_trades = trades_by_date.get(perf.date, [])
            perf.trades_count = len(day_trades)
            perf.win_count = sum(1 for t in day_trades if (t.get("pnl") or 0) > 0)
            perf.loss_count = sum(1 for t in day_trades if (t.get("pnl") or 0) < 0)


def create_parity_checker(**kwargs) -> ParityChecker:
    """Factory function to create a parity checker with custom settings."""
    return ParityChecker(**kwargs)
