"""
Trade history and analytics API routes.
Provides historical trade data with analytics and export functionality.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_db_session
from backend.infra.security import get_current_user
from backend.services.trade_service import TradeService
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/trades", tags=["Trading", "Protected"])


# Response Models

class Execution(BaseModel):
    """Execution detail model"""
    executionId: str = Field(alias="executionId")
    fillQty: float = Field(alias="fillQty")
    fillPrice: float = Field(alias="fillPrice")
    timestamp: str
    venue: str

    model_config = ConfigDict(populate_by_name=True)


class Trade(BaseModel):
    """Trade model"""
    orderId: str = Field(alias="orderId")
    symbol: str
    side: str
    qty: float
    filledQty: float = Field(alias="filledQty")
    avgFillPrice: float | None = Field(None, alias="avgFillPrice")
    orderType: str = Field(alias="orderType")
    status: str
    submittedAt: str = Field(alias="submittedAt")
    updatedAt: str = Field(alias="updatedAt")
    strategyId: str | None = Field(None, alias="strategyId")
    attributes: dict | None = Field(default_factory=dict)  # Includes imported flag
    positionStatus: str | None = Field(None, alias="positionStatus")  # open, closed, unknown
    positionNote: str | None = Field(None, alias="positionNote")  # Explanation
    currentQty: float | None = Field(None, alias="currentQty")  # Current qty at broker
    currentPrice: float | None = Field(None, alias="currentPrice")  # Current market price
    unrealizedPnL: float | None = Field(None, alias="unrealizedPnL")  # Unrealized P&L
    executions: list[Execution]

    model_config = ConfigDict(populate_by_name=True)


class TradeHistoryResponse(BaseModel):
    """Trade history response"""
    trades: list[Trade]
    total: int
    limit: int
    offset: int


class BestWorstTrade(BaseModel):
    """Best/worst trade model"""
    symbol: str
    pnl: float
    date: str


class PnLByDay(BaseModel):
    """P&L by day model"""
    date: str
    pnl: float
    trades: int


class InstitutionalMetrics(BaseModel):
    """Institutional-grade performance metrics"""
    # Risk-Adjusted Returns
    sharpeRatio: float
    sortinoRatio: float
    calmarRatio: float

    # Drawdown Metrics
    maxDrawdown: float
    maxDrawdownDollars: float
    maxDrawdownDuration: int

    # Profitability Metrics
    profitFactor: float
    expectancy: float
    recoveryFactor: float

    # Streak Analysis
    maxWinStreak: int
    maxLossStreak: int
    currentStreak: int
    currentStreakType: str

    # Returns Distribution
    monthlyReturns: list[dict]
    rMultiples: dict

    # Time Metrics
    avgTradeDurationHours: float

    # Basic Stats
    totalTrades: int
    winningTrades: int
    losingTrades: int
    winRate: float
    avgWin: float
    avgLoss: float


class TradeAnalytics(BaseModel):
    """Trade analytics response"""
    totalTrades: int = Field(alias="totalTrades")
    totalVolume: float = Field(alias="totalVolume")
    buyTrades: int = Field(alias="buyTrades")
    sellTrades: int = Field(alias="sellTrades")
    avgTradeValue: float = Field(alias="avgTradeValue")
    totalRealizedPnL: float = Field(alias="totalRealizedPnL")
    winningTrades: int = Field(alias="winningTrades")
    losingTrades: int = Field(alias="losingTrades")
    winRate: float = Field(alias="winRate")
    avgWinningTrade: float = Field(alias="avgWinningTrade")
    avgLosingTrade: float = Field(alias="avgLosingTrade")
    bestTrade: BestWorstTrade | None = Field(None, alias="bestTrade")
    worstTrade: BestWorstTrade | None = Field(None, alias="worstTrade")
    pnlByDay: list[PnLByDay] = Field(alias="pnlByDay")
    institutionalMetrics: InstitutionalMetrics | None = Field(None, alias="institutionalMetrics")

    model_config = ConfigDict(populate_by_name=True)


# API Endpoints

@router.get(
    "/history",
    response_model=TradeHistoryResponse,
    summary="Get Trade History",
    description="Fetch paginated trade history with optional filters. Returns filled orders with execution details."
)
async def get_trade_history(
    start_date: date | None = Query(None, description="Filter trades from this date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="Filter trades until this date (YYYY-MM-DD)"),
    symbol: str | None = Query(None, description="Filter by trading symbol (e.g., AAPL)"),
    strategy_id: str | None = Query(None, description="Filter by strategy ID"),
    side: str | None = Query(None, description="Filter by order side: buy or sell"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results (1-1000)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user)
) -> TradeHistoryResponse:
    """
    Get trade history with filters and pagination.

    - **start_date**: Optional start date filter
    - **end_date**: Optional end date filter
    - **symbol**: Optional symbol filter (e.g., AAPL, MSFT)
    - **strategy_id**: Optional strategy filter
    - **side**: Optional side filter (buy/sell)
    - **limit**: Page size (default 100, max 1000)
    - **offset**: Pagination offset (default 0)

    Returns paginated list of filled orders with execution details.
    """
    try:
        logger.info(f"Fetching trade history: start={start_date}, end={end_date}, "
                   f"symbol={symbol}, strategy={strategy_id}, side={side}, "
                   f"limit={limit}, offset={offset}")

        trade_service = TradeService(db)
        result = await trade_service.get_trade_history(
            start_date=start_date,
            end_date=end_date,
            symbol=symbol,
            strategy_id=strategy_id,
            side=side,
            limit=limit,
            offset=offset
        )

        return TradeHistoryResponse(**result)

    except Exception as e:
        logger.error(f"Error fetching trade history: {e}")
        raise


@router.get(
    "/analytics",
    response_model=TradeAnalytics,
    summary="Get Trade Analytics",
    description="Calculate comprehensive trade analytics including P&L, win rate, and performance metrics."
)
async def get_trade_analytics(
    start_date: date | None = Query(None, description="Calculate from this date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="Calculate until this date (YYYY-MM-DD)"),
    symbol: str | None = Query(None, description="Filter by trading symbol (e.g., AAPL)"),
    strategy_id: str | None = Query(None, description="Filter by strategy ID"),
    db: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user)
) -> TradeAnalytics:
    """
    Calculate trade analytics and performance metrics.

    - **start_date**: Optional start date filter
    - **end_date**: Optional end date filter
    - **symbol**: Optional symbol filter
    - **strategy_id**: Optional strategy filter

    Returns comprehensive analytics including:
    - Total trades, volume, and P&L
    - Win rate and average trade values
    - Best and worst trades
    - P&L breakdown by day
    """
    try:
        # Extract user_id from authenticated user (when auth is enabled)
        user_id = getattr(user, 'id', None) or getattr(user, 'username', None) or "admin"

        logger.info(f"Calculating trade analytics: start={start_date}, end={end_date}, "
                   f"symbol={symbol}, strategy={strategy_id}, user={user_id}")

        trade_service = TradeService(db)
        analytics = await trade_service.calculate_analytics(
            start_date=start_date,
            end_date=end_date,
            symbol=symbol,
            strategy_id=strategy_id,
            user_id=str(user_id)
        )

        return TradeAnalytics(**analytics)

    except Exception as e:
        logger.error(f"Error calculating analytics: {e}")
        raise


@router.get(
    "/export/csv",
    summary="Export Trades to CSV",
    description="Export filtered trade history to CSV format for download.",
    response_class=Response
)
async def export_trades_csv(
    start_date: date | None = Query(None, description="Filter trades from this date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="Filter trades until this date (YYYY-MM-DD)"),
    symbol: str | None = Query(None, description="Filter by trading symbol (e.g., AAPL)"),
    strategy_id: str | None = Query(None, description="Filter by strategy ID"),
    side: str | None = Query(None, description="Filter by order side: buy or sell"),
    db: AsyncSession = Depends(get_db_session),
    user=Depends(get_current_user)
):
    """
    Export trade history to CSV file.

    - **start_date**: Optional start date filter
    - **end_date**: Optional end date filter
    - **symbol**: Optional symbol filter
    - **strategy_id**: Optional strategy filter
    - **side**: Optional side filter (buy/sell)

    Returns CSV file with trade data for download.
    Maximum 10,000 trades per export.
    """
    try:
        logger.info(f"Exporting trades to CSV: start={start_date}, end={end_date}, "
                   f"symbol={symbol}, strategy={strategy_id}, side={side}")

        trade_service = TradeService(db)

        # Fetch trades (limit to 10K for CSV export)
        result = await trade_service.get_trade_history(
            start_date=start_date,
            end_date=end_date,
            symbol=symbol,
            strategy_id=strategy_id,
            side=side,
            limit=10000,
            offset=0
        )

        # Generate CSV
        csv_content = trade_service.generate_csv(result['trades'])

        # Generate filename with date
        from datetime import datetime as dt
        filename = f"trades_export_{dt.now().strftime('%Y%m%d_%H%M%S')}.csv"

        logger.info(f"Generated CSV export with {len(result['trades'])} trades: {filename}")

        # Return CSV as downloadable file
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        logger.error(f"Error exporting trades to CSV: {e}")
        raise
