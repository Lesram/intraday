"""
Positions Service - manages portfolio positions and position queries.
Integrates with Alpaca API for real-time position tracking.
"""
import asyncio
import logging
from typing import Any

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.models import Position
    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    # Mock classes for when alpaca-py is not available
    class TradingClient:
        pass
    class Position:
        pass

logger = logging.getLogger(__name__)


class PositionReadError(RuntimeError):
    """The broker position read failed: account state is UNKNOWN, not flat.

    Audit 2026-09-29 EXE-05: ``get_all_positions()`` returns ``{}`` on any
    failure, which callers cannot tell apart from a flat account. Callers
    that make safety decisions from the answer (entries, reconciliation,
    flatness proofs, sell guards) use ``get_all_positions_strict()``.
    """


def _position_dict(position) -> dict[str, Any]:
    # Audit 2026-10-05 C05-01: the organism's broker-price safety nets read
    # current_price, and its exit-window stop/max-loss check reads
    # qty_available (shares not held by open orders). Both are optional on the
    # Alpaca Position. A price that is missing, zero, negative or not finite
    # becomes 0.0, which no safety net acts on; an unreported or malformed
    # qty_available becomes None.
    try:
        current_price = float(getattr(position, 'current_price', None) or 0.0)
    except (TypeError, ValueError):
        current_price = 0.0
    if not 0.0 < current_price < float('inf'):
        current_price = 0.0
    try:
        qty_available = float(getattr(position, 'qty_available', None))
    except (TypeError, ValueError):
        qty_available = None
    if qty_available is not None and not abs(qty_available) < float('inf'):
        qty_available = None
    return {
        'symbol': position.symbol,
        'qty': float(position.qty),
        'side': 'long' if float(position.qty) > 0 else 'short',
        'market_value': float(position.market_value) if position.market_value else 0.0,
        'cost_basis': float(position.cost_basis) if position.cost_basis else 0.0,
        'unrealized_pl': float(position.unrealized_pl) if position.unrealized_pl else 0.0,
        'avg_entry_price': float(position.avg_entry_price) if position.avg_entry_price else 0.0,
        'current_price': current_price,
        'qty_available': qty_available,
    }


class PositionsService:
    """
    Service for managing and querying portfolio positions.
    Provides integration with Alpaca API for live position data.
    """

    def __init__(self, trading_client: TradingClient | None = None):
        """
        Initialize the positions service.

        Args:
            trading_client: Alpaca trading client instance
        """
        self.trading_client = trading_client
        self._positions_cache = {}
        self._cache_timestamp = None

    async def get_positions_by_symbols(self, symbols: list[str]) -> dict[str, dict[str, Any]]:
        """
        Get current positions for specified symbols.

        Args:
            symbols: List of stock symbols to query

        Returns:
            Dict mapping symbols to position data
        """
        try:
            if not self.trading_client:
                logger.warning("No trading client available, returning empty positions")
                return {}

            # Get all positions from Alpaca (async wrapper for sync API)
            positions = await asyncio.to_thread(self.trading_client.get_all_positions)

            # Convert to dict format expected by StrategyEngine
            position_map = {}

            for position in positions:
                if position.symbol in symbols:
                    position_map[position.symbol] = {
                        'symbol': position.symbol,
                        'qty': float(position.qty),
                        'side': 'long' if float(position.qty) > 0 else 'short',
                        'market_value': float(position.market_value) if position.market_value else 0.0,
                        'cost_basis': float(position.cost_basis) if position.cost_basis else 0.0,
                        'unrealized_pl': float(position.unrealized_pl) if position.unrealized_pl else 0.0,
                        'avg_entry_price': float(position.avg_entry_price) if position.avg_entry_price else 0.0
                    }

            # For symbols not in current positions, return empty position
            for symbol in symbols:
                if symbol not in position_map:
                    position_map[symbol] = {
                        'symbol': symbol,
                        'qty': 0.0,
                        'side': None,
                        'market_value': 0.0,
                        'cost_basis': 0.0,
                        'unrealized_pl': 0.0,
                        'avg_entry_price': 0.0
                    }

            logger.debug(f"Retrieved positions for {len(symbols)} symbols, {len([p for p in position_map.values() if p['qty'] != 0])} with holdings")
            return position_map

        except Exception as e:
            logger.error(f"Failed to get positions by symbols: {e}")
            # Return empty positions for all requested symbols
            return {symbol: {
                'symbol': symbol,
                'qty': 0.0,
                'side': None,
                'market_value': 0.0,
                'cost_basis': 0.0,
                'unrealized_pl': 0.0,
                'avg_entry_price': 0.0
            } for symbol in symbols}

    async def get_all_positions_strict(self) -> dict[str, dict[str, Any]]:
        """All current positions, or ``PositionReadError`` when the read fails.

        An empty dict means the broker confirmed a flat account.
        """
        if not self.trading_client:
            raise PositionReadError("no trading client")
        try:
            positions = await asyncio.to_thread(self.trading_client.get_all_positions)
            position_map = {position.symbol: _position_dict(position) for position in positions}
        except Exception as e:
            raise PositionReadError(f"{type(e).__name__}: {e}") from e
        logger.debug(f"Retrieved {len(position_map)} total positions")
        return position_map

    async def get_all_positions(self) -> dict[str, dict[str, Any]]:
        """
        Get all current positions.

        Returns:
            Dict mapping all held symbols to position data. Returns ``{}`` when
            the read fails (legacy contract for display/diagnostic callers);
            safety decisions use ``get_all_positions_strict()``.
        """
        try:
            return await self.get_all_positions_strict()
        except PositionReadError as e:
            if not self.trading_client:
                logger.warning("No trading client available, returning empty positions")
            else:
                logger.error(f"Failed to get all positions: {e}")
            return {}

    async def get_position(self, symbol: str) -> dict[str, Any] | None:
        """
        Get position for a single symbol.

        Args:
            symbol: Stock symbol to query

        Returns:
            Position data dict or None if no position
        """
        try:
            if not self.trading_client:
                return None

            position = await asyncio.to_thread(self.trading_client.get_open_position, symbol)

            if position:
                return {
                    'symbol': position.symbol,
                    'qty': float(position.qty),
                    'side': 'long' if float(position.qty) > 0 else 'short',
                    'market_value': float(position.market_value) if position.market_value else 0.0,
                    'cost_basis': float(position.cost_basis) if position.cost_basis else 0.0,
                    'unrealized_pl': float(position.unrealized_pl) if position.unrealized_pl else 0.0,
                    'avg_entry_price': float(position.avg_entry_price) if position.avg_entry_price else 0.0
                }
            else:
                return None

        except Exception as e:
            logger.debug(f"No position found for {symbol}: {e}")
            return None

    async def get_total_portfolio_value(self) -> float:
        """
        Get total portfolio value from all positions.

        Returns:
            Total market value of all positions
        """
        try:
            if not self.trading_client:
                return 0.0

            account = await asyncio.to_thread(self.trading_client.get_account)
            return float(account.portfolio_value) if account.portfolio_value else 0.0

        except Exception as e:
            logger.error(f"Failed to get portfolio value: {e}")
            return 0.0

    async def get_buying_power(self) -> float:
        """
        Get available buying power.

        Returns:
            Available buying power
        """
        try:
            if not self.trading_client:
                return 0.0

            account = await asyncio.to_thread(self.trading_client.get_account)
            return float(account.buying_power) if account.buying_power else 0.0

        except Exception as e:
            logger.error(f"Failed to get buying power: {e}")
            return 0.0


def create_positions_service(trading_client: TradingClient | None = None) -> PositionsService:
    """
    Factory function to create a PositionsService instance.

    Args:
        trading_client: Optional Alpaca trading client

    Returns:
        PositionsService instance
    """
    return PositionsService(trading_client=trading_client)
