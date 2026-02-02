"""
Institutional Analytics Service - Advanced metrics for hedge fund reporting.

Implements professional-grade performance metrics including:
- Sharpe Ratio (risk-adjusted returns)
- Maximum Drawdown (peak-to-trough decline)
- Profit Factor (gross profit / gross loss)
- Expectancy (expected $ per trade)
- Sortino Ratio (downside risk)
- Calmar Ratio (return / max drawdown)
- Recovery Factor (net profit / max drawdown)
- Win/loss streaks
- Monthly returns breakdown
- R-Multiple distribution
"""

from collections import defaultdict
from datetime import date, datetime
from typing import Any

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.schemas import RealizedTrade
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class InstitutionalAnalytics:
    """Advanced analytics for institutional-grade performance reporting."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_comprehensive_metrics(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        symbol: str | None = None,
        user_id: str = "admin",
        risk_free_rate: float = 0.05,  # 5% annual risk-free rate
    ) -> dict[str, Any]:
        """
        Calculate comprehensive institutional metrics.

        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            symbol: Filter by symbol
            user_id: User identifier
            risk_free_rate: Annual risk-free rate (default 5%)

        Returns:
            Dictionary with comprehensive metrics
        """
        # Query realized trades
        query = select(RealizedTrade).where(RealizedTrade.user_id == user_id)

        filters = []
        if start_date:
            filters.append(RealizedTrade.close_date >= datetime.combine(start_date, datetime.min.time()))
        if end_date:
            filters.append(RealizedTrade.close_date <= datetime.combine(end_date, datetime.max.time()))
        if symbol:
            filters.append(RealizedTrade.symbol == symbol.upper())

        if filters:
            query = query.where(and_(*filters))

        query = query.order_by(RealizedTrade.close_date.asc())

        result = await self.db.execute(query)
        trades = list(result.scalars().all())

        if not trades:
            return self._empty_metrics()

        logger.info(f"Calculating institutional metrics for {len(trades)} trades")

        # Extract trade data
        trade_pnls = [float(t.realized_pnl) for t in trades]
        trade_returns = [float(t.realized_pnl_percent) / 100 for t in trades]  # Convert to decimal

        # Calculate basic metrics
        total_trades = len(trades)
        winning_trades = [pnl for pnl in trade_pnls if pnl > 0]
        losing_trades = [pnl for pnl in trade_pnls if pnl < 0]

        # Sharpe Ratio
        sharpe = await self.calculate_sharpe_ratio(trade_returns, risk_free_rate)

        # Maximum Drawdown
        equity_curve = self._build_equity_curve(trade_pnls, initial_capital=100000)
        max_dd = await self.calculate_max_drawdown(equity_curve)

        # Profit Factor
        profit_factor = await self.calculate_profit_factor(winning_trades, losing_trades)

        # Expectancy
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0.0
        avg_win = np.mean(winning_trades) if winning_trades else 0.0
        avg_loss = np.mean(losing_trades) if losing_trades else 0.0
        expectancy = await self.calculate_expectancy(win_rate, avg_win, avg_loss)

        # Sortino Ratio (downside deviation)
        sortino = await self.calculate_sortino_ratio(trade_returns, risk_free_rate)

        # Calmar Ratio
        calmar = await self.calculate_calmar_ratio(trade_returns, max_dd['max_dd'])

        # Recovery Factor
        total_pnl = sum(trade_pnls)
        recovery_factor = await self.calculate_recovery_factor(total_pnl, max_dd['max_dd_dollars'])

        # Win/Loss Streaks
        streaks = await self.calculate_streaks(trade_pnls)

        # Monthly Returns
        monthly_returns = await self.calculate_monthly_returns(trades)

        # R-Multiple Distribution
        r_multiples = await self.calculate_r_multiples(trades)

        # Average Trade Duration
        avg_duration = await self.calculate_avg_trade_duration(trades)

        return {
            # Risk-Adjusted Returns
            "sharpeRatio": round(sharpe, 2),
            "sortinoRatio": round(sortino, 2),
            "calmarRatio": round(calmar, 2),

            # Drawdown Metrics
            "maxDrawdown": round(max_dd['max_dd'], 2),
            "maxDrawdownDollars": round(max_dd['max_dd_dollars'], 2),
            "maxDrawdownDuration": max_dd.get('duration_days', 0),

            # Profitability Metrics
            "profitFactor": round(profit_factor, 2),
            "expectancy": round(expectancy, 2),
            "recoveryFactor": round(recovery_factor, 2),

            # Streak Analysis
            "maxWinStreak": streaks['max_win_streak'],
            "maxLossStreak": streaks['max_loss_streak'],
            "currentStreak": streaks['current_streak'],
            "currentStreakType": streaks['current_streak_type'],

            # Returns Distribution
            "monthlyReturns": monthly_returns,
            "rMultiples": r_multiples,

            # Time Metrics
            "avgTradeDurationHours": round(avg_duration, 1),

            # Basic Stats (for reference)
            "totalTrades": total_trades,
            "winningTrades": len(winning_trades),
            "losingTrades": len(losing_trades),
            "winRate": round(win_rate, 2),
            "avgWin": round(avg_win, 2),
            "avgLoss": round(avg_loss, 2),
        }

    async def calculate_sharpe_ratio(
        self,
        returns: list[float],
        risk_free_rate: float = 0.05
    ) -> float:
        """
        Calculate annualized Sharpe Ratio.

        Sharpe Ratio = (Mean Return - Risk Free Rate) / Std Dev of Returns
        Annualized for 252 trading days.

        Args:
            returns: List of trade returns (as decimals, e.g., 0.05 for 5%)
            risk_free_rate: Annual risk-free rate (default 5%)

        Returns:
            Annualized Sharpe Ratio
        """
        if not returns or len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        mean_return = np.mean(returns_array)
        std_return = np.std(returns_array, ddof=1)  # Sample std dev

        if std_return == 0:
            return 0.0

        # Daily risk-free rate
        daily_rf = risk_free_rate / 252

        # Calculate Sharpe
        sharpe = (mean_return - daily_rf) / std_return

        # Annualize (assume 252 trading days)
        annualized_sharpe = sharpe * np.sqrt(252)

        return float(annualized_sharpe)

    async def calculate_sortino_ratio(
        self,
        returns: list[float],
        risk_free_rate: float = 0.05
    ) -> float:
        """
        Calculate annualized Sortino Ratio (downside deviation only).

        Sortino = (Mean Return - Risk Free Rate) / Downside Deviation
        Only considers negative returns in the denominator.

        Args:
            returns: List of trade returns (as decimals)
            risk_free_rate: Annual risk-free rate

        Returns:
            Annualized Sortino Ratio
        """
        if not returns or len(returns) < 2:
            return 0.0

        returns_array = np.array(returns)
        mean_return = np.mean(returns_array)

        # Calculate downside deviation (only negative returns)
        downside_returns = returns_array[returns_array < 0]
        if len(downside_returns) == 0:
            return 0.0

        downside_deviation = np.std(downside_returns, ddof=1)

        if downside_deviation == 0:
            return 0.0

        daily_rf = risk_free_rate / 252
        sortino = (mean_return - daily_rf) / downside_deviation
        annualized_sortino = sortino * np.sqrt(252)

        return float(annualized_sortino)

    async def calculate_max_drawdown(self, equity_curve: list[float]) -> dict[str, Any]:
        """
        Calculate Maximum Drawdown and related metrics.

        Maximum Drawdown = (Trough - Peak) / Peak

        Args:
            equity_curve: List of portfolio values over time

        Returns:
            Dictionary with max_dd, max_dd_dollars, peak_idx, trough_idx
        """
        if not equity_curve or len(equity_curve) < 2:
            return {
                'max_dd': 0.0,
                'max_dd_dollars': 0.0,
                'peak_idx': 0,
                'trough_idx': 0,
                'duration_days': 0
            }

        peak = equity_curve[0]
        peak_idx = 0
        max_dd = 0.0
        max_dd_dollars = 0.0
        max_dd_peak_idx = 0
        max_dd_trough_idx = 0

        for i, value in enumerate(equity_curve):
            if value > peak:
                peak = value
                peak_idx = i

            dd = (peak - value) / peak if peak > 0 else 0
            dd_dollars = peak - value

            if dd > max_dd:
                max_dd = dd
                max_dd_dollars = dd_dollars
                max_dd_peak_idx = peak_idx
                max_dd_trough_idx = i

        return {
            'max_dd': max_dd * 100,  # Convert to percentage
            'max_dd_dollars': max_dd_dollars,
            'peak_idx': max_dd_peak_idx,
            'trough_idx': max_dd_trough_idx,
            'duration_days': max_dd_trough_idx - max_dd_peak_idx
        }

    async def calculate_profit_factor(
        self,
        winning_pnls: list[float],
        losing_pnls: list[float]
    ) -> float:
        """
        Calculate Profit Factor.

        Profit Factor = Gross Profit / Gross Loss
        Values > 1 indicate profitable system.
        Values > 2 are considered excellent.

        Args:
            winning_pnls: List of winning trade P&Ls
            losing_pnls: List of losing trade P&Ls

        Returns:
            Profit Factor
        """
        gross_profit = sum(winning_pnls) if winning_pnls else 0.0
        gross_loss = abs(sum(losing_pnls)) if losing_pnls else 0.0

        if gross_loss == 0:
            return 0.0 if gross_profit == 0 else 999.99  # Cap at 999.99 instead of inf

        return gross_profit / gross_loss

    async def calculate_expectancy(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate Expectancy (expected $ per trade).

        Expectancy = (Win Rate * Avg Win) - (Loss Rate * Avg Loss)

        Args:
            win_rate: Win rate as percentage (e.g., 60.0)
            avg_win: Average winning trade P&L
            avg_loss: Average losing trade P&L (should be negative)

        Returns:
            Expected profit per trade
        """
        loss_rate = 100.0 - win_rate
        expectancy = (win_rate / 100 * avg_win) + (loss_rate / 100 * avg_loss)
        return expectancy

    async def calculate_calmar_ratio(
        self,
        returns: list[float],
        max_drawdown: float
    ) -> float:
        """
        Calculate Calmar Ratio.

        Calmar = Annualized Return / Max Drawdown
        Measures return relative to worst drawdown.

        Args:
            returns: List of trade returns
            max_drawdown: Maximum drawdown as percentage

        Returns:
            Calmar Ratio
        """
        if not returns or max_drawdown == 0:
            return 0.0

        # Calculate annualized return
        total_return = sum(returns)
        n_years = len(returns) / 252  # Assume 252 trading days per year
        if n_years == 0:
            return 0.0

        annualized_return = (total_return / n_years) * 100  # Convert to percentage

        calmar = annualized_return / max_drawdown if max_drawdown != 0 else 0.0
        return calmar

    async def calculate_recovery_factor(
        self,
        net_profit: float,
        max_drawdown_dollars: float
    ) -> float:
        """
        Calculate Recovery Factor.

        Recovery Factor = Net Profit / Max Drawdown (in dollars)
        Measures how well the system recovers from drawdowns.

        Args:
            net_profit: Total net profit
            max_drawdown_dollars: Maximum drawdown in dollars

        Returns:
            Recovery Factor
        """
        if max_drawdown_dollars == 0:
            return 0.0 if net_profit == 0 else 999.99

        return net_profit / max_drawdown_dollars

    async def calculate_streaks(self, trade_pnls: list[float]) -> dict[str, Any]:
        """
        Calculate win/loss streaks.

        Args:
            trade_pnls: List of trade P&Ls

        Returns:
            Dictionary with max_win_streak, max_loss_streak, current_streak
        """
        if not trade_pnls:
            return {
                'max_win_streak': 0,
                'max_loss_streak': 0,
                'current_streak': 0,
                'current_streak_type': 'none'
            }

        max_win_streak = 0
        max_loss_streak = 0
        current_streak = 0
        current_type = None

        for pnl in trade_pnls:
            if pnl > 0:
                if current_type == 'win':
                    current_streak += 1
                else:
                    current_streak = 1
                    current_type = 'win'
                max_win_streak = max(max_win_streak, current_streak)
            elif pnl < 0:
                if current_type == 'loss':
                    current_streak += 1
                else:
                    current_streak = 1
                    current_type = 'loss'
                max_loss_streak = max(max_loss_streak, current_streak)
            # pnl == 0: break-even, resets streak
            else:
                current_streak = 0
                current_type = 'none'

        return {
            'max_win_streak': max_win_streak,
            'max_loss_streak': max_loss_streak,
            'current_streak': current_streak,
            'current_streak_type': current_type or 'none'
        }

    async def calculate_monthly_returns(
        self,
        trades: list[RealizedTrade]
    ) -> list[dict[str, Any]]:
        """
        Calculate monthly returns breakdown.

        Args:
            trades: List of RealizedTrade objects

        Returns:
            List of monthly return summaries
        """
        monthly_data = defaultdict(lambda: {'pnl': 0.0, 'trades': 0, 'wins': 0, 'losses': 0})

        for trade in trades:
            month_key = trade.close_date.strftime('%Y-%m')
            pnl = float(trade.realized_pnl)

            monthly_data[month_key]['pnl'] += pnl
            monthly_data[month_key]['trades'] += 1

            if pnl > 0:
                monthly_data[month_key]['wins'] += 1
            elif pnl < 0:
                monthly_data[month_key]['losses'] += 1

        # Sort by month and format
        monthly_returns = []
        for month in sorted(monthly_data.keys()):
            data = monthly_data[month]
            monthly_returns.append({
                'month': month,
                'pnl': round(data['pnl'], 2),
                'trades': data['trades'],
                'wins': data['wins'],
                'losses': data['losses'],
                'winRate': round((data['wins'] / data['trades'] * 100) if data['trades'] > 0 else 0, 2)
            })

        return monthly_returns

    async def calculate_r_multiples(
        self,
        trades: list[RealizedTrade]
    ) -> dict[str, Any]:
        """
        Calculate R-Multiple distribution.

        R-Multiple = Trade P&L / Initial Risk
        For simplicity, we use P&L % as a proxy for R-Multiple.

        Args:
            trades: List of RealizedTrade objects

        Returns:
            Dictionary with R-Multiple statistics
        """
        if not trades:
            return {
                'avgRMultiple': 0.0,
                'distribution': [],
                'countAbove1R': 0,
                'countBelow1R': 0
            }

        r_multiples = []
        for trade in trades:
            # Use P&L % as R-Multiple proxy
            r_mult = float(trade.realized_pnl_percent)
            r_multiples.append(r_mult)

        above_1r = sum(1 for r in r_multiples if r >= 1.0)
        below_1r = sum(1 for r in r_multiples if r < 0)

        return {
            'avgRMultiple': round(np.mean(r_multiples), 2) if r_multiples else 0.0,
            'medianRMultiple': round(np.median(r_multiples), 2) if r_multiples else 0.0,
            'countAbove1R': above_1r,
            'countBelow1R': below_1r,
            'distribution': {
                '< -5%': sum(1 for r in r_multiples if r < -5),
                '-5% to 0%': sum(1 for r in r_multiples if -5 <= r < 0),
                '0% to 1%': sum(1 for r in r_multiples if 0 <= r < 1),
                '1% to 5%': sum(1 for r in r_multiples if 1 <= r < 5),
                '> 5%': sum(1 for r in r_multiples if r >= 5),
            }
        }

    async def calculate_avg_trade_duration(
        self,
        trades: list[RealizedTrade]
    ) -> float:
        """
        Calculate average trade duration in hours.

        Args:
            trades: List of RealizedTrade objects

        Returns:
            Average duration in hours
        """
        if not trades:
            return 0.0

        durations = []
        for trade in trades:
            duration = (trade.close_date - trade.open_date).total_seconds() / 3600  # Convert to hours
            durations.append(duration)

        return np.mean(durations) if durations else 0.0

    def _build_equity_curve(
        self,
        trade_pnls: list[float],
        initial_capital: float = 100000
    ) -> list[float]:
        """
        Build equity curve from trade P&Ls.

        Args:
            trade_pnls: List of trade P&Ls
            initial_capital: Starting capital

        Returns:
            List of equity values over time
        """
        equity_curve = [initial_capital]

        for pnl in trade_pnls:
            equity_curve.append(equity_curve[-1] + pnl)

        return equity_curve

    def _empty_metrics(self) -> dict[str, Any]:
        """Return empty metrics structure."""
        return {
            "sharpeRatio": 0.0,
            "sortinoRatio": 0.0,
            "calmarRatio": 0.0,
            "maxDrawdown": 0.0,
            "maxDrawdownDollars": 0.0,
            "maxDrawdownDuration": 0,
            "profitFactor": 0.0,
            "expectancy": 0.0,
            "recoveryFactor": 0.0,
            "maxWinStreak": 0,
            "maxLossStreak": 0,
            "currentStreak": 0,
            "currentStreakType": "none",
            "monthlyReturns": [],
            "rMultiples": {
                "avgRMultiple": 0.0,
                "medianRMultiple": 0.0,
                "countAbove1R": 0,
                "countBelow1R": 0,
                "distribution": {}
            },
            "avgTradeDurationHours": 0.0,
            "totalTrades": 0,
            "winningTrades": 0,
            "losingTrades": 0,
            "winRate": 0.0,
            "avgWin": 0.0,
            "avgLoss": 0.0,
        }
