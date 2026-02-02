"""
Position Reconciliation Service
Compares filled buy orders in database with current Alpaca positions
to determine which orders represent open vs closed positions.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.schemas import Order
from backend.integrations.alpaca_broker import AlpacaBrokerClient
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class PositionReconciliationService:
    """
    Service to reconcile database orders with current broker positions.
    Identifies which filled orders are still open positions vs closed.
    """

    def __init__(self, db: AsyncSession, alpaca_client: AlpacaBrokerClient):
        self.db = db
        self.alpaca_client = alpaca_client

    async def get_position_status_for_orders(self, order_ids: list[str]) -> dict[str, dict[str, Any]]:
        """
        Get position status for specific orders.

        Args:
            order_ids: List of order IDs to check

        Returns:
            Dict mapping order_id to status info:
            {
                "order_id": {
                    "position_status": "open" | "closed" | "unknown",
                    "current_qty": float | None,
                    "current_price": float | None,
                    "unrealized_pnl": float | None,
                    "note": str
                }
            }
        """
        try:
            # Get current positions from Alpaca
            alpaca_positions = await self.alpaca_client.get_positions()

            # Create lookup by symbol
            positions_by_symbol = {
                pos['symbol']: pos for pos in alpaca_positions
            }

            # Get orders from database
            query = select(Order).where(Order.id.in_(order_ids))
            result = await self.db.execute(query)
            orders = list(result.scalars().all())

            # Calculate total bought quantity per symbol from ALL filled buy orders in DB
            total_bought_by_symbol = {}
            for order in orders:
                if order.side == 'buy' and order.status == 'filled':
                    symbol = order.symbol
                    qty = float(order.filled_qty)
                    total_bought_by_symbol[symbol] = total_bought_by_symbol.get(symbol, 0) + qty

            # Build status for each order
            status_map = {}

            for order in orders:
                symbol = order.symbol
                order_id_str = str(order.id)

                # Check if this is a buy order that's filled
                if order.side == 'buy' and order.status == 'filled':
                    float(order.filled_qty)
                    total_bought = total_bought_by_symbol.get(symbol, 0)

                    # Check if position exists at Alpaca
                    if symbol in positions_by_symbol:
                        alpaca_pos = positions_by_symbol[symbol]
                        alpaca_qty = float(alpaca_pos['qty'])

                        # Compare Alpaca quantity with total database quantity for this symbol
                        if alpaca_qty >= total_bought:
                            # All orders for this symbol are fully open
                            status_map[order_id_str] = {
                                "position_status": "open",
                                "current_qty": alpaca_qty,
                                "current_price": float(alpaca_pos['current_price']),
                                "unrealized_pnl": float(alpaca_pos['unrealized_pl']),
                                "note": f"Position is open at Alpaca ({alpaca_qty} shares total)"
                            }
                        elif alpaca_qty > 0:
                            # Some shares still exist, but less than we bought
                            # This order might be partially or fully closed
                            missing_qty = total_bought - alpaca_qty
                            status_map[order_id_str] = {
                                "position_status": "partially_closed",
                                "current_qty": alpaca_qty,
                                "current_price": float(alpaca_pos['current_price']),
                                "unrealized_pnl": float(alpaca_pos['unrealized_pl']),
                                "note": f"⚠️ Position partially closed: {alpaca_qty} of {total_bought} shares remain ({missing_qty} shares closed)"
                            }
                        else:
                            # Position closed completely
                            status_map[order_id_str] = {
                                "position_status": "closed",
                                "current_qty": None,
                                "current_price": None,
                                "unrealized_pnl": None,
                                "note": f"⚠️ Position fully closed (was {total_bought} shares)"
                            }
                    else:
                        # Position does not exist at Alpaca at all
                        status_map[order_id_str] = {
                            "position_status": "closed",
                            "current_qty": None,
                            "current_price": None,
                            "unrealized_pnl": None,
                            "note": "⚠️ Position was closed (not found at Alpaca)"
                        }

                elif order.side == 'sell' and order.status == 'filled':
                    # Sell orders close positions
                    status_map[order_id_str] = {
                        "position_status": "closed_by_sell",
                        "current_qty": None,
                        "current_price": None,
                        "unrealized_pnl": None,
                        "note": "Position closed by sell order"
                    }

                else:
                    # Not a filled buy/sell order
                    status_map[order_id_str] = {
                        "position_status": "not_applicable",
                        "current_qty": None,
                        "current_price": None,
                        "unrealized_pnl": None,
                        "note": f"Order status: {order.status}"
                    }

            logger.info(f"Reconciled {len(status_map)} orders with Alpaca positions")
            return status_map

        except Exception as e:
            logger.error(f"Error reconciling positions: {str(e)}")
            # Return unknown status for all orders on error
            return {
                order_id: {
                    "position_status": "unknown",
                    "current_qty": None,
                    "current_price": None,
                    "unrealized_pnl": None,
                    "note": f"Error checking position status: {str(e)}"
                }
                for order_id in order_ids
            }

    async def get_reconciliation_summary(self) -> dict[str, Any]:
        """
        Get a summary of position reconciliation across all filled orders.

        Returns:
            Summary with counts and details
        """
        try:
            # Get all filled buy orders
            query = select(Order).where(
                Order.side == 'buy',
                Order.status == 'filled'
            )
            result = await self.db.execute(query)
            orders = list(result.scalars().all())

            if not orders:
                return {
                    "total_filled_buys": 0,
                    "open_positions": 0,
                    "closed_positions": 0,
                    "discrepancies": []
                }

            # Get position status for all orders
            order_ids = [str(order.id) for order in orders]
            status_map = await self.get_position_status_for_orders(order_ids)

            # Count statuses
            open_count = sum(
                1 for status in status_map.values()
                if status["position_status"] in ["open", "partially_closed"]
            )
            closed_count = sum(
                1 for status in status_map.values()
                if status["position_status"] in ["closed", "closed_by_sell"]
            )

            # Identify discrepancies (filled orders with no position and no sell)
            discrepancies = []
            for order in orders:
                order_id_str = str(order.id)
                status_info = status_map.get(order_id_str, {})

                if status_info.get("position_status") == "closed":
                    # Check if there's a corresponding sell order
                    sell_query = select(Order).where(
                        Order.symbol == order.symbol,
                        Order.side == 'sell',
                        Order.status == 'filled',
                        Order.submitted_at > order.submitted_at
                    )
                    sell_result = await self.db.execute(sell_query)
                    sell_order = sell_result.scalar_one_or_none()

                    if not sell_order:
                        discrepancies.append({
                            "symbol": order.symbol,
                            "order_id": order_id_str,
                            "qty": float(order.filled_qty),
                            "submitted_at": order.submitted_at.isoformat(),
                            "reason": "Position closed but no sell order found in database"
                        })

            return {
                "total_filled_buys": len(orders),
                "open_positions": open_count,
                "closed_positions": closed_count,
                "unknown": len(orders) - open_count - closed_count,
                "discrepancies": discrepancies,
                "discrepancy_count": len(discrepancies)
            }

        except Exception as e:
            logger.error(f"Error generating reconciliation summary: {str(e)}")
            return {
                "error": str(e),
                "total_filled_buys": 0,
                "open_positions": 0,
                "closed_positions": 0,
                "discrepancies": []
            }
