"""Backtest Pydantic models for request/response validation"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class BacktestRequest(BaseModel):
    """Request to run a backtest"""
    strategy_id: str
    start_date: date
    end_date: date
    initial_capital: float = Field(ge=1000, le=10_000_000, description="Initial capital in USD")
    parameters: dict[str, Any] | None = None

    @field_validator('end_date')
    @classmethod
    def validate_date_range(cls, v: date, info) -> date:
        """Validate end_date is after start_date and not in future"""
        if hasattr(info, 'data') and 'start_date' in info.data:
            if v < info.data['start_date']:
                raise ValueError('end_date must be after start_date')

        if v > date.today():
            raise ValueError('end_date cannot be in the future')

        # Max 5 years backtest
        if hasattr(info, 'data') and 'start_date' in info.data:
            duration_days = (v - info.data['start_date']).days
            if duration_days > 1825:  # 5 years
                raise ValueError('Maximum backtest duration is 5 years')

        return v


class EquityPoint(BaseModel):
    """Single point on equity curve"""
    date: date
    value: float
    cash: float
    positions_value: float


class Trade(BaseModel):
    """Single trade executed during backtest"""
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: int
    entry_date: date
    entry_price: float
    exit_date: date | None = None
    exit_price: float | None = None
    pnl: float | None = None
    pnl_percent: float | None = None
    duration_days: int | None = None
    commission: float = 0.0


class PerformanceMetrics(BaseModel):
    """All calculated performance metrics"""
    # Returns
    total_return: float = Field(description="Total return percentage")
    annualized_return: float = Field(description="Annualized return percentage")

    # Risk-adjusted metrics
    sharpe_ratio: float = Field(description="Sharpe ratio (risk-free rate = 2%)")
    sortino_ratio: float = Field(description="Sortino ratio (downside deviation)")
    calmar_ratio: float = Field(description="Calmar ratio (return / max drawdown)")

    # Risk metrics
    max_drawdown: float = Field(description="Maximum drawdown percentage")
    max_drawdown_duration_days: int = Field(description="Max drawdown duration in days")
    volatility: float = Field(description="Annualized volatility")

    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float = Field(description="Percentage of winning trades")

    # P&L statistics
    profit_factor: float = Field(description="Gross profit / gross loss")
    avg_trade_pnl: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float

    # Streaks
    max_consecutive_wins: int
    max_consecutive_losses: int

    # Benchmark comparison (optional)
    alpha: float | None = Field(None, description="Excess return vs benchmark")
    beta: float | None = Field(None, description="Correlation with benchmark")

    # Additional metrics
    total_commission: float = Field(default=0.0, description="Total commission paid")
    avg_trade_duration_days: float = Field(description="Average holding period")


class BacktestResult(BaseModel):
    """Complete backtest result"""
    id: str
    strategy_id: str
    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float

    # Summary metrics
    metrics: PerformanceMetrics

    # Detailed results
    equity_curve: list[EquityPoint]
    trade_log: list[Trade]
    monthly_returns: list[dict[str, Any]]  # [{"month": "2024-01", "return": 5.2}]

    # Execution info
    status: str  # pending, running, completed, failed
    error_message: str | None = None
    progress: int = Field(default=0, ge=0, le=100)

    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @property
    def duration_days(self) -> int:
        """Total days in backtest period"""
        return (self.end_date - self.start_date).days

    @property
    def trades_per_day(self) -> float:
        """Average trades per day"""
        if self.duration_days == 0:
            return 0.0
        return self.metrics.total_trades / self.duration_days


class BacktestSummary(BaseModel):
    """Lightweight backtest summary for history list"""
    id: str
    strategy_id: str
    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: float

    # Summary metrics (nullable if backtest not completed)
    final_equity: float | None = None
    total_return: float | None = None
    sharpe_ratio: float | None = None
    max_drawdown: float | None = None
    total_trades: int | None = None

    # Execution info
    status: str
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    @property
    def duration_days(self) -> int:
        """Total days in backtest period"""
        return (self.end_date - self.start_date).days


class MonthlyReturn(BaseModel):
    """Monthly return data"""
    month: str  # Format: "2024-01"
    return_pct: float
    trades: int
    winning_trades: int
    losing_trades: int
