"""
Positions Service - Provides position data for strategy engine
"""

import logging
import time
from decimal import Decimal
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class PositionCalculator:
    """Calculator for position sizing and risk management."""
    
    def calculate_position_size(
        self,
        account_balance: Decimal,
        risk_percentage: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal
    ) -> Decimal:
        """
        Calculate position size based on risk parameters.
        
        Args:
            account_balance: Total account balance
            risk_percentage: Percentage of account to risk (0.02 = 2%)
            entry_price: Entry price per share
            stop_loss: Stop loss price per share
            
        Returns:
            Position size in shares
        """
        if risk_percentage <= 0:
            return Decimal('0')
        
        if entry_price <= 0 or stop_loss <= 0:
            raise ValueError("Entry price and stop loss must be positive")
            
        # For a long position, stop loss should be less than entry price
        # For a short position, stop loss should be greater than entry price
        # This simple implementation assumes long positions
        if stop_loss >= entry_price:
            raise ValueError("Stop loss must be less than entry price for long positions")
            
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share <= 0:
            raise ZeroDivisionError("Risk per share cannot be zero")
            
        total_risk = account_balance * risk_percentage
        position_size = total_risk / risk_per_share
        
        return position_size.quantize(Decimal('0.01'))
        
    def calculate_portfolio_risk(self, positions: List[Dict[str, Any]]) -> Decimal:
        """Calculate total portfolio risk across positions."""
        total_risk = Decimal('0')
        for position in positions:
            total_risk += Decimal(str(position.get('risk_amount', 0)))
        return total_risk
        
    def calculate_position_value(self, quantity: Decimal, price: Decimal) -> Decimal:
        """Calculate total value of a position."""
        return (quantity * price).quantize(Decimal('0.01'))


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

    async def get_user_positions(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all positions for a user."""
        # Mock implementation - return sample positions
        return [
            {
                "symbol": "AAPL",
                "quantity": 100,
                "avg_price": 150.50,
                "market_value": 15050.0,
                "unrealized_pnl": 500.0,
                "position_type": "long"
            },
            {
                "symbol": "MSFT",
                "quantity": 50,
                "avg_price": 300.25,
                "market_value": 15012.50,
                "unrealized_pnl": -250.0,
                "position_type": "long"
            }
        ]

    async def get_position(self, user_id: str, symbol: str) -> Dict[str, Any]:
        """Get position for a specific symbol."""
        if symbol in self._mock_positions:
            pos = self._mock_positions[symbol]
            return {
                "symbol": symbol,
                "quantity": pos.qty,
                "avg_price": pos.avg_cost,
                "market_value": pos.market_value,
                "unrealized_pnl": (pos.market_value - pos.qty * pos.avg_cost),
                "position_type": "long"
            }
        return None

    async def create_position(self, user_id: str, symbol: str, quantity: float, price: float, position_type: str = "long") -> Dict[str, Any]:
        """Create a new position."""
        position_id = f"{user_id}_{symbol}_{int(time.time())}"
        self._mock_positions[symbol] = Position(
            symbol=symbol,
            qty=quantity,
            price=price,
            avg_cost=price,
            market_value=quantity * price
        )
        return {"position_id": position_id, "symbol": symbol}

    async def update_position(self, user_id: str, symbol: str, quantity: float, price: float) -> bool:
        """Update an existing position."""
        if symbol in self._mock_positions:
            pos = self._mock_positions[symbol]
            pos.qty = quantity
            pos.price = price
            pos.market_value = quantity * price
            return True
        return False

    async def close_position(self, user_id: str, symbol: str) -> bool:
        """Close/delete a position."""
        if symbol in self._mock_positions:
            del self._mock_positions[symbol]
            return True
        return False

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
                    market_value=0.0,
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
            market_value=qty * price,
        )
