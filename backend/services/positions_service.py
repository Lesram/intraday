"""
Positions Service - Provides position data for strategy engine
"""

import logging

logger = logging.getLogger(__name__)


class Position:
    """Simple position data class."""

    def __init__(
        self,
        symbol: str,
        qty: float,
        price: float = 0.0,
        avg_cost: float = 0.0,
        market_value: float = 0.0,
    ):
        self.symbol = symbol
        self.qty = qty
        self.price = price
        self.avg_cost = avg_cost or price
        self.market_value = market_value or (qty * price)


class PositionsService:
    """
    Service for retrieving position data.
    For now, provides mock data since we don't have live positions.
    In production, this would integrate with the positions repository.
    """

    def __init__(self) -> None:
        self._mock_positions: dict[str, Position] = {}

    async def get_positions_by_symbols(self, symbols: list[str]) -> dict[str, Position]:
        """
        Get positions for the specified symbols.

        Args:
            symbols: List of symbol strings

        Returns:
            Dictionary mapping symbol to Position object
        """
        result = {}

        for symbol in symbols:
            # Return mock position with zero quantity for now
            # In production, this would query the positions repository
            if symbol in self._mock_positions:
                result[symbol] = self._mock_positions[symbol]
            else:
                result[symbol] = Position(
                    symbol=symbol,
                    qty=0.0,
                    price=100.0,  # Mock price
                    avg_cost=100.0,
                    market_value=0.0
                )

        logger.debug(f"Retrieved positions for {len(symbols)} symbols")
        return result

    def set_mock_position(self, symbol: str, qty: float, price: float = 100.0) -> None:
        """Set a mock position for testing purposes."""
        self._mock_positions[symbol] = Position(
            symbol=symbol,
            qty=qty,
            price=price,
            avg_cost=price,
            market_value=qty * price
        )
