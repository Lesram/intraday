"""
Position Import Service
Imports pre-existing Alpaca positions as historical orders in the database.
This enables complete portfolio visibility across the platform.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.schemas import Order
from backend.integrations.alpaca_broker import AlpacaBrokerClient
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class PositionImportService:
    """Service for importing Alpaca positions as historical orders"""

    def __init__(self, db: AsyncSession, alpaca_client: AlpacaBrokerClient):
        self.db = db
        self.alpaca_client = alpaca_client

    async def import_existing_positions(self, user_id: str = "demo") -> dict[str, Any]:
        """
        Import all existing Alpaca positions as historical orders.

        This creates order records for positions that existed before the platform
        was built, allowing complete portfolio tracking and analytics.

        Args:
            user_id: User ID to associate positions with

        Returns:
            Dictionary with import summary
        """
        try:
            logger.info("Starting position import from Alpaca...")

            # Fetch positions from Alpaca
            positions = await self.alpaca_client.get_positions()

            if not positions:
                logger.info("No positions to import")
                return {
                    "success": True,
                    "imported": 0,
                    "skipped": 0,
                    "positions": []
                }

            imported = []
            skipped = []

            for position in positions:
                symbol = position['symbol']
                qty = Decimal(str(position['qty']))
                avg_entry_price = Decimal(str(position['avg_entry_price']))

                # Check if position already imported
                existing_import_query = select(Order).where(
                    Order.symbol == symbol,
                    Order.attributes.op('->>')('imported') == 'true'
                )
                result = await self.db.execute(existing_import_query)
                existing_import = result.scalar_one_or_none()

                if existing_import:
                    logger.info(f"Position {symbol} already imported, skipping")
                    skipped.append(f"{symbol} (already imported)")
                    continue

                # CRITICAL: Check if we have ANY filled orders for this symbol
                # If yes, the Alpaca position already includes those orders - DON'T IMPORT
                existing_orders_query = select(Order).where(
                    Order.symbol == symbol,
                    Order.status == 'filled',
                    Order.side == 'buy'  # Only check buy orders
                )
                result = await self.db.execute(existing_orders_query)
                existing_orders = result.scalars().all()

                if existing_orders:
                    total_qty = sum(float(o.filled_qty) for o in existing_orders)
                    logger.warning(
                        f"Skipping {symbol}: Already have {len(existing_orders)} filled buy order(s) "
                        f"totaling {total_qty} shares. Alpaca position ({float(qty)} shares) "
                        f"likely includes these orders - importing would create duplicates."
                    )
                    skipped.append(f"{symbol} (prevents double-counting - {len(existing_orders)} existing orders)")
                    continue

                # Create historical order record
                order = Order(
                    id=uuid4(),
                    client_idempotency_key=f"import-{symbol}-{datetime.now(UTC).timestamp()}",
                    symbol=symbol,
                    side='buy',  # Assume buy for existing positions
                    order_type='market',
                    qty=qty,
                    filled_qty=qty,  # Fully filled
                    avg_fill_price=avg_entry_price,
                    limit_price=None,
                    stop_price=None,
                    tif='gtc',
                    status='filled',  # Already filled
                    submitted_at=datetime.now(UTC),  # Use current time as estimate
                    attributes={
                        'imported': True,  # Mark as imported
                        'import_source': 'alpaca',
                        'import_timestamp': datetime.now(UTC).isoformat(),
                        'original_qty': float(qty),
                        'original_avg_price': float(avg_entry_price),
                        'note': 'Imported from pre-existing Alpaca position'
                    }
                )

                self.db.add(order)
                imported.append({
                    'symbol': symbol,
                    'qty': float(qty),
                    'avg_price': float(avg_entry_price),
                    'value': float(qty * avg_entry_price)
                })

                logger.info(f"Imported position: {symbol} - {qty} shares @ ${avg_entry_price}")

            # Commit all imports
            await self.db.commit()

            summary = {
                "success": True,
                "imported": len(imported),
                "skipped": len(skipped),
                "positions": imported,
                "skipped_symbols": skipped
            }

            logger.info(f"Position import complete: {len(imported)} imported, {len(skipped)} skipped")

            return summary

        except Exception as e:
            logger.error(f"Error importing positions: {e}")
            await self.db.rollback()
            raise

    async def get_import_preview(self) -> dict[str, Any]:
        """
        Preview positions that would be imported without actually importing them.

        Returns:
            Dictionary with positions to be imported and existing imports
        """
        try:
            # Fetch current Alpaca positions
            positions = await self.alpaca_client.get_positions()

            # Check which are already imported or would create duplicates
            to_import = []
            already_imported = []
            would_duplicate = []

            for position in positions:
                symbol = position['symbol']

                # Check if already imported
                existing_import_query = select(Order).where(
                    Order.symbol == symbol,
                    Order.attributes.op('->>')('imported') == 'true'
                )
                result = await self.db.execute(existing_import_query)
                existing_import = result.scalar_one_or_none()

                position_data = {
                    'symbol': symbol,
                    'qty': float(position['qty']),
                    'avg_entry_price': float(position['avg_entry_price']),
                    'current_price': float(position['current_price']),
                    'market_value': float(position['market_value']),
                    'unrealized_pl': float(position['unrealized_pl']),
                    'unrealized_plpc': float(position['unrealized_plpc'])
                }

                if existing_import:
                    already_imported.append(position_data)
                    continue

                # Check if we have existing filled orders (would create duplicates)
                existing_orders_query = select(Order).where(
                    Order.symbol == symbol,
                    Order.status == 'filled',
                    Order.side == 'buy'
                )
                result = await self.db.execute(existing_orders_query)
                existing_orders = result.scalars().all()

                if existing_orders:
                    position_data['existing_orders_count'] = len(existing_orders)
                    position_data['existing_orders_qty'] = sum(float(o.filled_qty) for o in existing_orders)
                    position_data['reason'] = 'Would create duplicates - Alpaca position includes these orders'
                    would_duplicate.append(position_data)
                else:
                    to_import.append(position_data)

            return {
                "to_import": to_import,
                "to_import_count": len(to_import),
                "already_imported": already_imported,
                "already_imported_count": len(already_imported),
                "would_duplicate": would_duplicate,
                "would_duplicate_count": len(would_duplicate),
                "total_positions": len(positions)
            }

        except Exception as e:
            logger.error(f"Error getting import preview: {e}")
            raise
