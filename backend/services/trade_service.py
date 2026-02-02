"""
Trade service - business logic for trade history and analytics.
Handles trade data retrieval, analytics calculations, and CSV export generation.
"""

import csv
from datetime import date, datetime
import io
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.infra.schemas import Order, RealizedTrade
from backend.integrations.alpaca_broker import AlpacaBrokerClient
from backend.services.position_reconciliation_service import PositionReconciliationService
from backend.services.trade_analytics_service import InstitutionalAnalytics
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class TradeService:
    """Service for trade history and analytics operations"""

    def __init__(self, db: AsyncSession, alpaca_client: AlpacaBrokerClient | None = None):
        self.db = db
        self.alpaca_client = alpaca_client or AlpacaBrokerClient()
        self.reconciliation_service = PositionReconciliationService(db, self.alpaca_client)
        self.analytics_service = InstitutionalAnalytics(db)

    async def get_trade_history(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        side: str | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> dict[str, Any]:
        """
        Fetch trade history with filters and pagination.

        Args:
            start_date: Filter trades from this date
            end_date: Filter trades until this date
            symbol: Filter by trading symbol
            strategy_id: Filter by strategy ID
            side: Filter by order side ('buy' or 'sell')
            limit: Maximum number of results (1-1000)
            offset: Pagination offset

        Returns:
            Dictionary with trades list, total count, limit, and offset
        """
        try:
            # Build base query - orders with final status (filled, cancelled, rejected, failed, expired)
            # These are orders that are no longer active/pending
            final_statuses = ['filled', 'partially_filled', 'cancelled', 'rejected', 'failed', 'expired']
            query = (
                select(Order)
                .options(selectinload(Order.executions))
                .where(Order.status.in_(final_statuses))
            )

            # Apply filters
            filters = []

            if start_date:
                filters.append(Order.submitted_at >= datetime.combine(start_date, datetime.min.time()))

            if end_date:
                filters.append(Order.submitted_at <= datetime.combine(end_date, datetime.max.time()))

            if symbol:
                filters.append(Order.symbol == symbol.upper())

            if side and side in ['buy', 'sell']:
                filters.append(Order.side == side.lower())

            if strategy_id:
                filters.append(Order.attributes['strategy_id'].astext == strategy_id)

            if filters:
                query = query.where(and_(*filters))

            # Count total matching records
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await self.db.execute(count_query)
            total = total_result.scalar() or 0

            # Apply ordering and pagination
            query = query.order_by(Order.submitted_at.desc()).limit(limit).offset(offset)

            # Execute query
            result = await self.db.execute(query)
            orders = list(result.scalars().all())

            # Get position status for all orders
            order_ids = [str(order.id) for order in orders]
            position_status_map = await self.reconciliation_service.get_position_status_for_orders(order_ids)

            # Transform to API format with camelCase for frontend
            trades = []
            for order in orders:
                order_id_str = str(order.id)
                position_status_info = position_status_map.get(order_id_str, {
                    "position_status": "unknown",
                    "current_qty": None,
                    "current_price": None,
                    "unrealized_pnl": None,
                    "note": "Unable to determine position status"
                })

                trade = {
                    "orderId": order_id_str,
                    "symbol": order.symbol,
                    "side": order.side,
                    "qty": float(order.qty),
                    "filledQty": float(order.filled_qty),
                    "avgFillPrice": float(order.avg_fill_price) if order.avg_fill_price else None,
                    "orderType": order.order_type,
                    "status": order.status,
                    "submittedAt": order.submitted_at.isoformat(),
                    "updatedAt": order.updated_at.isoformat(),
                    "strategyId": order.attributes.get('strategy_id') if order.attributes else None,
                    "attributes": order.attributes or {},  # Include attributes for imported flag
                    "positionStatus": position_status_info["position_status"],
                    "positionNote": position_status_info["note"],
                    "currentQty": position_status_info["current_qty"],
                    "currentPrice": position_status_info["current_price"],
                    "unrealizedPnL": position_status_info["unrealized_pnl"],
                    "executions": [
                        {
                            "executionId": str(exec.id),
                            "fillQty": float(exec.fill_qty),
                            "fillPrice": float(exec.fill_price),
                            "timestamp": exec.ts.isoformat(),
                            "venue": exec.venue
                        }
                        for exec in order.executions
                    ]
                }
                trades.append(trade)

            logger.info(f"Fetched {len(trades)} trades (total: {total}, offset: {offset})")

            return {
                "trades": trades,
                "total": total,
                "limit": limit,
                "offset": offset
            }

        except Exception as e:
            logger.error(f"Error fetching trade history: {e}")
            raise

    async def calculate_analytics(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        user_id: str | None = None
    ) -> dict[str, Any]:
        """
        Calculate trade analytics and performance metrics.

        Args:
            start_date: Calculate from this date
            end_date: Calculate until this date
            symbol: Filter by trading symbol
            strategy_id: Filter by strategy ID
            user_id: User ID for filtering (used when multi-user auth is enabled)

        Returns:
            Dictionary with comprehensive analytics
        """
        try:
            # Build base query for filled orders
            query = select(Order).where(Order.status == 'filled')

            # Apply filters
            filters = []

            if start_date:
                filters.append(Order.submitted_at >= datetime.combine(start_date, datetime.min.time()))

            if end_date:
                filters.append(Order.submitted_at <= datetime.combine(end_date, datetime.max.time()))

            if symbol:
                filters.append(Order.symbol == symbol.upper())

            if strategy_id:
                filters.append(Order.attributes['strategy_id'].astext == strategy_id)

            if filters:
                query = query.where(and_(*filters))

            # Execute query
            result = await self.db.execute(query)
            orders = list(result.scalars().all())

            # Query realized trades for accurate P&L (from lot tracking)
            realized_trades_query = select(RealizedTrade)
            realized_filters = []

            if start_date:
                realized_filters.append(RealizedTrade.close_date >= datetime.combine(start_date, datetime.min.time()))
            if end_date:
                realized_filters.append(RealizedTrade.close_date <= datetime.combine(end_date, datetime.max.time()))
            if symbol:
                realized_filters.append(RealizedTrade.symbol == symbol.upper())

            if realized_filters:
                realized_trades_query = realized_trades_query.where(and_(*realized_filters))

            realized_result = await self.db.execute(realized_trades_query)
            realized_trades = list(realized_result.scalars().all())

            logger.info(f"Found {len(realized_trades)} realized trades for analytics")

            if not orders:
                # Return empty analytics with camelCase keys
                return {
                    "totalTrades": 0,
                    "totalVolume": 0.0,
                    "buyTrades": 0,
                    "sellTrades": 0,
                    "avgTradeValue": 0.0,
                    "totalRealizedPnL": 0.0,
                    "winningTrades": 0,
                    "losingTrades": 0,
                    "winRate": 0.0,
                    "avgWinningTrade": 0.0,
                    "avgLosingTrade": 0.0,
                    "bestTrade": None,
                    "worstTrade": None,
                    "pnlByDay": []
                }

            # Calculate basic stats
            total_trades = len(orders)
            buy_trades = sum(1 for o in orders if o.side == 'buy')
            sell_trades = sum(1 for o in orders if o.side == 'sell')

            # Calculate volume
            total_volume = sum(
                float(o.filled_qty * o.avg_fill_price)
                for o in orders
                if o.avg_fill_price
            )
            avg_trade_value = total_volume / total_trades if total_trades > 0 else 0.0

            # Calculate P&L from realized trades (accurate cost basis tracking)
            total_realized_pnl = 0.0
            winning_trades = 0
            losing_trades = 0
            winning_pnls = []
            losing_pnls = []
            trade_pnls = []  # For best/worst tracking

            if realized_trades:
                # Use realized trades for accurate P&L
                logger.info(f"Using {len(realized_trades)} realized trades for P&L calculation")

                for trade in realized_trades:
                    pnl = float(trade.realized_pnl)
                    total_realized_pnl += pnl

                    if pnl > 0:
                        winning_trades += 1
                        winning_pnls.append(pnl)
                    elif pnl < 0:
                        losing_trades += 1
                        losing_pnls.append(pnl)
                    # Note: pnl == 0 is break-even, not counted in either

                    trade_pnls.append({
                        'symbol': trade.symbol,
                        'pnl': pnl,
                        'date': trade.close_date,
                        'qty': float(trade.qty),
                        'open_price': float(trade.open_price),
                        'close_price': float(trade.close_price),
                    })
            else:
                # Fallback: Use old FIFO matching if no realized trades exist
                logger.warning("No realized trades found, falling back to legacy FIFO matching")

                buys_by_symbol = {}
                sells_by_symbol = {}

                for order in orders:
                    if not order.avg_fill_price:
                        continue

                    value = float(order.filled_qty * order.avg_fill_price)

                    if order.side == 'buy':
                        if order.symbol not in buys_by_symbol:
                            buys_by_symbol[order.symbol] = []
                        buys_by_symbol[order.symbol].append({
                            'qty': float(order.filled_qty),
                            'price': float(order.avg_fill_price),
                            'value': value,
                            'date': order.submitted_at
                        })
                    else:  # sell
                        if order.symbol not in sells_by_symbol:
                            sells_by_symbol[order.symbol] = []
                        sells_by_symbol[order.symbol].append({
                            'qty': float(order.filled_qty),
                            'price': float(order.avg_fill_price),
                            'value': value,
                            'date': order.submitted_at
                        })

                # Legacy FIFO matching
                for symbol in sells_by_symbol:
                    if symbol not in buys_by_symbol:
                        continue

                    buys = buys_by_symbol[symbol]
                    sells = sells_by_symbol[symbol]

                    for sell in sells:
                        remaining_sell_qty = sell['qty']
                        sell_pnl = 0.0

                        for buy in buys:
                            if remaining_sell_qty <= 0:
                                break

                            if buy.get('qty_remaining', buy['qty']) <= 0:
                                continue

                            matched_qty = min(remaining_sell_qty, buy.get('qty_remaining', buy['qty']))
                            pnl = matched_qty * (sell['price'] - buy['price'])
                            sell_pnl += pnl

                            remaining_sell_qty -= matched_qty
                            buy['qty_remaining'] = buy.get('qty_remaining', buy['qty']) - matched_qty

                        total_realized_pnl += sell_pnl

                        if sell_pnl > 0:
                            winning_trades += 1
                            winning_pnls.append(sell_pnl)
                        elif sell_pnl < 0:
                            losing_trades += 1
                            losing_pnls.append(sell_pnl)

                        trade_pnls.append({
                            'symbol': symbol,
                            'pnl': sell_pnl,
                            'date': sell['date']
                        })

            # Calculate win rate
            completed_trades = winning_trades + losing_trades
            win_rate = (winning_trades / completed_trades * 100) if completed_trades > 0 else 0.0

            # Average winning/losing trade
            avg_winning_trade = sum(winning_pnls) / len(winning_pnls) if winning_pnls else 0.0
            avg_losing_trade = sum(losing_pnls) / len(losing_pnls) if losing_pnls else 0.0

            # Best and worst trades - handle edge cases correctly
            best_trade = None
            worst_trade = None

            if trade_pnls:
                if len(trade_pnls) == 1:
                    # Single trade: assign to best if profitable, worst if losing
                    single = trade_pnls[0]
                    if single['pnl'] > 0:
                        best_trade = single
                    elif single['pnl'] < 0:
                        worst_trade = single
                    # If P&L == 0, both remain None (break-even trade)
                else:
                    # Multiple trades: find actual best and worst
                    sorted_trades = sorted(trade_pnls, key=lambda x: x['pnl'])

                    # Worst trade (most negative)
                    if sorted_trades[0]['pnl'] < 0:
                        worst_trade = sorted_trades[0]

                    # Best trade (most positive)
                    if sorted_trades[-1]['pnl'] > 0:
                        best_trade = sorted_trades[-1]

            # P&L by day
            pnl_by_day_dict = {}
            for trade in trade_pnls:
                day = trade['date'].date().isoformat()
                if day not in pnl_by_day_dict:
                    pnl_by_day_dict[day] = {'pnl': 0.0, 'trades': 0}
                pnl_by_day_dict[day]['pnl'] += trade['pnl']
                pnl_by_day_dict[day]['trades'] += 1

            pnl_by_day = [
                {
                    'date': day,
                    'pnl': data['pnl'],
                    'trades': data['trades']
                }
                for day, data in sorted(pnl_by_day_dict.items())
            ]

            # Return analytics with camelCase keys for frontend compatibility
            analytics = {
                "totalTrades": total_trades,
                "totalVolume": round(total_volume, 2),
                "buyTrades": buy_trades,
                "sellTrades": sell_trades,
                "avgTradeValue": round(avg_trade_value, 2),
                "totalRealizedPnL": round(total_realized_pnl, 2),
                "winningTrades": winning_trades,
                "losingTrades": losing_trades,
                "winRate": round(win_rate, 2),
                "avgWinningTrade": round(avg_winning_trade, 2),
                "avgLosingTrade": round(avg_losing_trade, 2),
                "bestTrade": {
                    "symbol": best_trade['symbol'],
                    "pnl": round(best_trade['pnl'], 2),
                    "date": best_trade['date'].isoformat()
                } if best_trade else None,
                "worstTrade": {
                    "symbol": worst_trade['symbol'],
                    "pnl": round(worst_trade['pnl'], 2),
                    "date": worst_trade['date'].isoformat()
                } if worst_trade else None,
                "pnlByDay": pnl_by_day
            }

            logger.info(f"Calculated analytics: {analytics['totalTrades']} trades, "
                       f"win rate: {analytics['winRate']:.1f}%, "
                       f"total P&L: ${analytics['totalRealizedPnL']:.2f}")

            # Add institutional analytics (Phase 3: Advanced Metrics)
            try:
                # Use provided user_id or default to "admin" for single-user mode
                # PREREQUISITE: Multi-user authentication system (see backend/api/auth.py)
                # When auth is enabled, user_id will be passed from API route via get_current_user dependency
                effective_user_id = user_id or "admin"
                institutional_metrics = await self.analytics_service.calculate_comprehensive_metrics(
                    start_date=start_date,
                    end_date=end_date,
                    symbol=symbol,
                    user_id=effective_user_id
                )

                # Merge institutional metrics into analytics
                analytics.update({
                    "institutionalMetrics": institutional_metrics
                })

                logger.info(f"Added institutional metrics: Sharpe={institutional_metrics.get('sharpeRatio', 0):.2f}, "
                           f"MaxDD={institutional_metrics.get('maxDrawdown', 0):.2f}%, "
                           f"ProfitFactor={institutional_metrics.get('profitFactor', 0):.2f}")
            except Exception as e:
                logger.error(f"Failed to calculate institutional metrics: {e}")
                # Continue without institutional metrics (graceful degradation)
                analytics["institutionalMetrics"] = None

            return analytics

        except Exception as e:
            logger.error(f"Error calculating analytics: {e}")
            raise

    def generate_csv(self, trades: list[dict[str, Any]]) -> str:
        """
        Generate CSV string from trades list.

        Args:
            trades: List of trade dictionaries

        Returns:
            CSV formatted string
        """
        try:
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                'Date',
                'Symbol',
                'Side',
                'Quantity',
                'Filled Qty',
                'Avg Price',
                'Total Value',
                'Status',
                'Order Type',
                'Strategy ID',
                'Order ID'
            ])

            # Write data rows
            for trade in trades:
                filled_qty = trade.get('filled_qty', 0)
                avg_price = trade.get('avg_fill_price', 0)
                total_value = filled_qty * avg_price if avg_price else 0

                writer.writerow([
                    trade.get('submitted_at', '')[:10],  # Date only
                    trade.get('symbol', ''),
                    trade.get('side', '').upper(),
                    f"{trade.get('qty', 0):.6f}",
                    f"{filled_qty:.6f}",
                    f"${avg_price:.2f}" if avg_price else '',
                    f"${total_value:.2f}",
                    trade.get('status', ''),
                    trade.get('order_type', ''),
                    trade.get('strategy_id', '') or 'N/A',
                    trade.get('order_id', '')
                ])

            csv_content = output.getvalue()
            output.close()

            logger.info(f"Generated CSV with {len(trades)} trades")

            return csv_content

        except Exception as e:
            logger.error(f"Error generating CSV: {e}")
            raise
