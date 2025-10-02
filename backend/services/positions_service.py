"""
Positions Service - manages portfolio positions and position queries.
Integrates with Alpaca API for real-time position tracking.
"""

import logging
from typing import Dict, List, Optional, Any
from decimal import Decimal

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


class PositionsService:
    """
    Service for managing and querying portfolio positions.
    Provides integration with Alpaca API for live position data.
    """

    def __init__(self, trading_client: Optional[TradingClient] = None):
        """
        Initialize the positions service.
        
        Args:
            trading_client: Alpaca trading client instance
        """
        self.trading_client = trading_client
        self._positions_cache = {}
        self._cache_timestamp = None

    async def get_positions_by_symbols(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
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
            
            # Get all positions from Alpaca
            positions = self.trading_client.get_all_positions()
            
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

    async def get_all_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all current positions.
        
        Returns:
            Dict mapping all held symbols to position data
        """
        try:
            if not self.trading_client:
                logger.warning("No trading client available, returning empty positions")
                return {}
                
            positions = self.trading_client.get_all_positions()
            
            position_map = {}
            for position in positions:
                position_map[position.symbol] = {
                    'symbol': position.symbol,
                    'qty': float(position.qty),
                    'side': 'long' if float(position.qty) > 0 else 'short',
                    'market_value': float(position.market_value) if position.market_value else 0.0,
                    'cost_basis': float(position.cost_basis) if position.cost_basis else 0.0,
                    'unrealized_pl': float(position.unrealized_pl) if position.unrealized_pl else 0.0,
                    'avg_entry_price': float(position.avg_entry_price) if position.avg_entry_price else 0.0
                }
            
            logger.debug(f"Retrieved {len(position_map)} total positions")
            return position_map
            
        except Exception as e:
            logger.error(f"Failed to get all positions: {e}")
            return {}

    async def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
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
                
            position = self.trading_client.get_open_position(symbol)
            
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

    def get_total_portfolio_value(self) -> float:
        """
        Get total portfolio value from all positions.
        
        Returns:
            Total market value of all positions
        """
        try:
            if not self.trading_client:
                return 0.0
                
            account = self.trading_client.get_account()
            return float(account.portfolio_value) if account.portfolio_value else 0.0
            
        except Exception as e:
            logger.error(f"Failed to get portfolio value: {e}")
            return 0.0

    def get_buying_power(self) -> float:
        """
        Get available buying power.
        
        Returns:
            Available buying power
        """
        try:
            if not self.trading_client:
                return 0.0
                
            account = self.trading_client.get_account()
            return float(account.buying_power) if account.buying_power else 0.0
            
        except Exception as e:
            logger.error(f"Failed to get buying power: {e}")
            return 0.0


def create_positions_service(trading_client: Optional[TradingClient] = None) -> PositionsService:
    """
    Factory function to create a PositionsService instance.
    
    Args:
        trading_client: Optional Alpaca trading client
        
    Returns:
        PositionsService instance
    """
    return PositionsService(trading_client=trading_client)