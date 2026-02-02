"""
Portfolio Sync Service

Synchronizes portfolio data from Alpaca broker to local database.
Handles initial sync on startup and periodic updates.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.db import get_session_context
from backend.infra.schemas import Position
from backend.integrations.alpaca_broker import get_alpaca_broker_client
from backend.utils.logger import get_structured_logger

logger = get_structured_logger(__name__)


class PortfolioSyncService:
    """
    Service for syncing portfolio data from Alpaca to local database.

    This ensures the platform reflects the true state of the Alpaca account,
    including positions created outside the platform.
    """

    def __init__(self):
        """Initialize the portfolio sync service."""
        self.broker_client = get_alpaca_broker_client()
        logger.info("Portfolio sync service initialized")

    async def sync_positions(self, session: AsyncSession) -> tuple[list[Position], dict]:
        """
        Sync positions from Alpaca to local database.

        This replaces all local positions with current Alpaca positions,
        ensuring the local database reflects the true broker state.

        Args:
            session: Database session

        Returns:
            Tuple of (positions list, account_data dict)
        """
        try:
            # Fetch account data from Alpaca
            account_data = await self.broker_client.get_account()

            logger.info("Syncing account data from Alpaca",
                       cash=account_data.get("cash"),
                       portfolio_value=account_data.get("portfolio_value"),
                       buying_power=account_data.get("buying_power"))

            # Fetch positions from Alpaca
            alpaca_positions = await self.broker_client.get_positions()

            logger.info("Syncing positions from Alpaca",
                       alpaca_position_count=len(alpaca_positions))

            # Delete existing positions
            await session.execute(delete(Position))

            # Create new positions from Alpaca data
            synced_positions = []
            for alpaca_pos in alpaca_positions:
                position = Position(
                    symbol=alpaca_pos.get("symbol"),
                    qty=Decimal(str(alpaca_pos.get("qty", "0"))),
                    avg_price=Decimal(str(alpaca_pos.get("avg_entry_price", "0"))),
                    realized_pnl=Decimal("0"),  # Not provided by Alpaca positions API
                )
                session.add(position)
                synced_positions.append(position)

                logger.info("Synced position",
                           symbol=position.symbol,
                           quantity=position.qty)

            await session.commit()

            logger.info("Positions synced successfully",
                       position_count=len(synced_positions))

            return synced_positions, account_data

        except Exception as e:
            logger.error("Failed to sync positions",
                        error=str(e),
                        error_type=type(e).__name__)
            await session.rollback()
            raise

    async def sync_full_portfolio(self, user_id: str = None) -> dict:
        """
        Perform full portfolio sync: account data + positions.

        Args:
            user_id: User ID (for logging/compatibility, not used with current schema)

        Returns:
            Dict containing sync results and portfolio summary
        """
        try:
            logger.info("Starting full portfolio sync", user_id=user_id)

            async with get_session_context() as session:
                # Sync positions and get account data
                positions, account_data = await self.sync_positions(session)

                logger.info("Full portfolio sync completed successfully",
                           user_id=user_id,
                           position_count=len(positions))

                return {
                    "success": True,
                    "user_id": user_id,
                    "portfolio": {
                        "cash": str(account_data.get("cash", "0")),
                        "total_equity": str(account_data.get("equity", "0")),
                        "buying_power": str(account_data.get("buying_power", "0")),
                        "day_pnl": str(Decimal(account_data.get("equity", "0")) - Decimal(account_data.get("last_equity", account_data.get("equity", "0")))),
                        "total_pnl": str(Decimal(account_data.get("equity", "0")) - Decimal("100000.00")),  # Assuming $100k starting capital
                    },
                    "positions": [
                        {
                            "symbol": pos.symbol,
                            "quantity": str(pos.qty),
                            "avg_entry_price": str(pos.avg_price),
                            "current_price": "0",  # Will be updated by market data
                            "market_value": str(pos.qty * pos.avg_price),
                            "unrealized_pnl": "0",  # Will be calculated with current prices
                        }
                        for pos in positions
                    ],
                    "synced_at": datetime.now(UTC).isoformat()
                }

        except Exception as e:
            logger.error("Full portfolio sync failed",
                        user_id=user_id,
                        error=str(e),
                        error_type=type(e).__name__)
            return {
                "success": False,
                "user_id": user_id,
                "error": str(e),
                "synced_at": datetime.now(UTC).isoformat()
            }


# Global service instance
_sync_service: PortfolioSyncService | None = None


def get_portfolio_sync_service() -> PortfolioSyncService:
    """
    Get or create global PortfolioSyncService instance.

    Returns:
        PortfolioSyncService instance for syncing portfolio data
    """
    global _sync_service
    if _sync_service is None:
        _sync_service = PortfolioSyncService()
    return _sync_service
