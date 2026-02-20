"""
Portfolio Service - Manages portfolio data and calculations.
Integrates with database and Alpaca broker to provide real-time portfolio information.
"""

from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any

from sqlalchemy import and_, select

from backend.infra.cache import get_hot_data_cache, portfolio_cache_key
from backend.infra.db import get_session_context
from backend.infra.schemas import Order, PortfolioHistory, Position

logger = logging.getLogger(__name__)


class PortfolioService:
    """Service for portfolio operations and calculations."""

    # Cache TTL for portfolio data (seconds)
    PORTFOLIO_CACHE_TTL = 10.0  # 10 seconds - balance freshness vs performance

    def __init__(self):
        """Initialize portfolio service."""
        self.default_cash = Decimal('100000.00')  # Default starting capital
        self._sync_service = None  # Lazy load to avoid circular imports
        self._broker_client = None  # Lazy load broker client

    def _get_sync_service(self):
        """Lazy load portfolio sync service."""
        if self._sync_service is None:
            from backend.services.portfolio_sync_service import get_portfolio_sync_service
            self._sync_service = get_portfolio_sync_service()
        return self._sync_service

    def _get_broker_client(self):
        """Lazy load Alpaca broker client."""
        if self._broker_client is None:
            from backend.integrations.alpaca_broker import get_alpaca_broker_client
            self._broker_client = get_alpaca_broker_client()
        return self._broker_client

    async def get_user_portfolio(self, user_id: str, force_sync: bool = False) -> dict[str, Any]:
        """
        Get comprehensive portfolio data for a user.

        Uses in-memory cache for hot data (10s TTL) to reduce DB/API load.
        If local database is empty or force_sync=True, syncs from Alpaca first.

        Args:
            user_id: User ID to fetch portfolio for
            force_sync: If True, bypass cache and sync from Alpaca

        Returns:
            Dictionary with portfolio summary and positions
        """
        # Check cache first (unless force_sync)
        cache = get_hot_data_cache()
        cache_key = portfolio_cache_key(user_id)

        if not force_sync:
            cached_portfolio = await cache.get(cache_key)
            if cached_portfolio is not None:
                logger.debug(f"Portfolio cache hit for user {user_id}")
                return cached_portfolio

        try:
            # Fetch real account data from Alpaca
            broker_client = self._get_broker_client()
            account_data = await broker_client.get_account()

            # Use actual Alpaca values
            total_equity = Decimal(str(account_data.get("equity", "100000")))
            cash = Decimal(str(account_data.get("cash", "100000")))
            buying_power = Decimal(str(account_data.get("buying_power", "100000")))
            portfolio_value = Decimal(str(account_data.get("portfolio_value", "0")))

            logger.info(f"Fetched account data from Alpaca: equity={total_equity}, cash={cash}, portfolio_value={portfolio_value}")

            async with get_session_context() as session:
                # Get all positions (global for now - will add user_id filter later)
                positions_result = await session.execute(
                    select(Position)
                )
                positions = positions_result.scalars().all()

                # If no positions found OR force_sync, try syncing from Alpaca
                if (not positions or force_sync):
                    logger.info(f"Local portfolio empty or force_sync=True, syncing from Alpaca for user {user_id}")
                    try:
                        sync_service = self._get_sync_service()
                        sync_result = await sync_service.sync_full_portfolio(user_id)

                        if sync_result.get("success"):
                            logger.info(f"Successfully synced portfolio from Alpaca for user {user_id}")
                            # Re-fetch positions after sync
                            positions_result = await session.execute(
                                select(Position)
                            )
                            positions = positions_result.scalars().all()
                        else:
                            logger.warning(f"Alpaca sync failed, using local data: {sync_result.get('error')}")
                    except Exception as sync_error:
                        logger.warning(f"Failed to sync from Alpaca, using local data: {sync_error}")

                # Build positions data WITH REAL-TIME PRICES FROM ALPACA
                # Fetch Alpaca positions to get current_price and unrealized P&L
                alpaca_positions_list = await broker_client.get_positions()
                alpaca_positions = {p['symbol']: p for p in alpaca_positions_list}

                # Pre-fetch all entry dates in ONE query to avoid N+1 (optimization)
                position_symbols = [pos.symbol for pos in positions]
                if position_symbols:
                    from sqlalchemy import func as sqla_func
                    entry_dates_query = await session.execute(
                        select(
                            Order.symbol,
                            sqla_func.min(Order.submitted_at).label('first_buy_date')
                        )
                        .where(
                            Order.symbol.in_(position_symbols),
                            Order.side == 'buy',
                            Order.status == 'filled'
                        )
                        .group_by(Order.symbol)
                    )
                    entry_dates_map = {row.symbol: row.first_buy_date for row in entry_dates_query.all()}
                else:
                    entry_dates_map = {}

                positions_data = []
                for pos in positions:
                    symbol = pos.symbol
                    qty = float(pos.qty)
                    avg_price = float(pos.avg_price)

                    # Get real-time data from Alpaca positions
                    alpaca_pos = alpaca_positions.get(symbol, {})
                    current_price = float(alpaca_pos.get('current_price', avg_price))
                    unrealized_pl = float(alpaca_pos.get('unrealized_pl', 0.0))
                    unrealized_plpc = float(alpaca_pos.get('unrealized_plpc', 0.0)) * 100  # Convert to %
                    market_value = float(alpaca_pos.get('market_value', qty * avg_price))
                    side = alpaca_pos.get('side', 'long')
                    exchange = alpaca_pos.get('exchange', 'ALPACA')

                    # Get entry date from pre-fetched map (N+1 fix)
                    entry_date_result = entry_dates_map.get(symbol)
                    entry_date = entry_date_result.isoformat() if entry_date_result else pos.created_at.isoformat()

                    # Use camelCase for frontend compatibility
                    positions_data.append({
                        'symbol': symbol,
                        'quantity': qty,
                        'averagePrice': avg_price,
                        'currentPrice': current_price,  # ✅ REAL current price from Alpaca
                        'marketValue': market_value,
                        'unrealizedPnL': unrealized_pl,  # ✅ REAL unrealized P&L from Alpaca
                        'unrealizedPnLPercent': unrealized_plpc,  # ✅ REAL percentage
                        'side': side,
                        'exchange': exchange,  # ✅ Real exchange (NASDAQ, NYSE, ALPACA, etc)
                        'entryDate': entry_date  # ✅ Date of first buy order
                    })

                logger.info(f"Built portfolio data with {len(positions_data)} positions using real-time Alpaca prices")

                # Calculate P&L metrics from actual position data
                total_unrealized_pl = sum(
                    Decimal(str(p.get('unrealizedPnL', 0) or 0)) for p in positions_data
                )
                total_cost_basis = sum(
                    Decimal(str(p.get('quantity', 0) * p.get('averagePrice', 0)))
                    for p in positions_data
                )
                total_pl = total_unrealized_pl
                total_pl_percent = (total_pl / total_cost_basis * 100) if total_cost_basis > 0 else Decimal(0)

                portfolio_data = {
                    'totalEquity': float(total_equity),
                    'cash': float(cash),
                    'buyingPower': float(buying_power),
                    'marginUsed': 0.0,
                    'maintenanceMargin': 0.0,
                    'totalPnL': float(total_pl),
                    'totalPnLPercent': float(total_pl_percent),
                    'dayPnL': 0.0,  # Will calculate with price changes later
                    'dayPnLPercent': 0.0,
                    'positions': positions_data,
                    'userId': user_id,
                    'lastUpdate': datetime.now(UTC).isoformat()
                }

                # Cache the portfolio data
                await cache.set(cache_key, portfolio_data, ttl=self.PORTFOLIO_CACHE_TTL)
                logger.debug(f"Cached portfolio for user {user_id}")

                return portfolio_data

        except Exception as e:
            logger.error(f"Failed to get portfolio for user {user_id}: {e}")
            # Return default portfolio on error
            return {
                'totalEquity': 100000.00,
                'cash': 100000.00,
                'buyingPower': 100000.00,
                'marginUsed': 0.0,
                'maintenanceMargin': 0.0,
                'totalPnL': 0.0,
                'totalPnLPercent': 0.0,
                'dayPnL': 0.0,
                'dayPnLPercent': 0.0,
                'positions': [],
                'userId': user_id,
                'lastUpdate': datetime.now(UTC).isoformat()
            }

    async def get_portfolio_history(
        self,
        user_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
        interval: str = '1d'
    ) -> list[dict[str, Any]]:
        """
        Get portfolio value history from the portfolio_history table.

        Args:
            user_id: User ID
            start_date: Start date (ISO format)
            end_date: End date (ISO format)
            interval: Time interval (1m, 5m, 15m, 1h, 1d) - reserved for future sampling

        Returns:
            List of historical portfolio snapshots
            
        PREREQUISITE: Background job to record snapshots must be running.
        Schema: backend/infra/schemas.py::PortfolioHistory
        See docs/operations/ for snapshot job setup instructions.
        """
        try:
            async with get_session_context() as session:
                # Build query for portfolio history
                query = select(PortfolioHistory).where(
                    PortfolioHistory.user_id == int(user_id) if user_id.isdigit() else True
                )

                # Apply date filters
                filters = []
                if start_date:
                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                    filters.append(PortfolioHistory.timestamp >= start_dt)
                if end_date:
                    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                    filters.append(PortfolioHistory.timestamp <= end_dt)

                if filters:
                    query = query.where(and_(*filters))

                # Order by timestamp descending (most recent first)
                query = query.order_by(PortfolioHistory.timestamp.desc()).limit(500)

                result = await session.execute(query)
                history_records = result.scalars().all()

                if history_records:
                    # Return historical data from database
                    return [record.to_dict() for record in reversed(history_records)]

                # Fallback: If no history exists yet, return current snapshot
                # This provides graceful degradation until snapshot job is running
                logger.info(f"No portfolio history found for user {user_id}, returning current snapshot")
                current_portfolio = await self.get_user_portfolio(user_id)
                return [{
                    'timestamp': current_portfolio['lastUpdate'],
                    'totalEquity': current_portfolio['totalEquity'],
                    'cash': current_portfolio['cash'],
                    'positionsValue': current_portfolio.get('totalEquity', 0) - current_portfolio.get('cash', 0),
                    'dailyPnL': current_portfolio.get('dayPnL'),
                    'dailyPnLPercent': current_portfolio.get('dayPnLPercent'),
                    'totalPnL': current_portfolio.get('totalPnL'),
                    'totalPnLPercent': current_portfolio.get('totalPnLPercent'),
                    'positionCount': len(current_portfolio.get('positions', [])),
                    'snapshotType': 'current',
                }]

        except Exception as e:
            logger.error(f"Failed to get portfolio history for user {user_id}: {e}")
            return []

    async def get_position_by_symbol(
        self,
        user_id: str,
        symbol: str
    ) -> dict[str, Any] | None:
        """
        Get specific position for a symbol.

        Args:
            user_id: User ID
            symbol: Stock symbol

        Returns:
            Position data or None if not found
        """
        try:
            async with get_session_context() as session:
                # Get position for symbol
                result = await session.execute(
                    select(Position).where(
                        Position.symbol == symbol.upper()
                    )
                )
                position = result.scalar_one_or_none()

                if not position:
                    return None

                position_value = position.avg_price * position.qty

                return {
                    'symbol': position.symbol,
                    'qty': float(position.qty),
                    'avg_price': str(position.avg_price),
                    'market_value': str(position_value),
                    'unrealized_pnl': '0.00',  # Will calculate with real-time prices later
                    'realized_pnl': str(position.realized_pnl or Decimal('0'))
                }

        except Exception as e:
            logger.error(f"Failed to get position {symbol} for user {user_id}: {e}")
            return None

    async def broadcast_portfolio_update(self, user_id: str) -> None:
        """
        Fetch current portfolio data and broadcast to user's connected clients.

        Args:
            user_id: User ID to broadcast portfolio update to
        """
        try:
            # Get current portfolio data
            portfolio_data = await self.get_user_portfolio(user_id)

            # Import and call WebSocket broadcast function
            from backend.api.socketio_server import broadcast_portfolio_update

            await broadcast_portfolio_update(user_id, portfolio_data)
            logger.info(f"✅ Broadcasted portfolio update for user {user_id}")

        except Exception as e:
            logger.error(f"❌ Failed to broadcast portfolio update for user {user_id}: {e}")


# Global service instance
_portfolio_service: PortfolioService | None = None


def get_portfolio_service() -> PortfolioService:
    """Get or create global portfolio service instance."""
    global _portfolio_service
    if _portfolio_service is None:
        _portfolio_service = PortfolioService()
    return _portfolio_service
