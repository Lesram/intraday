"""
Portfolio Service - Manages portfolio data and calculations.
Integrates with database to provide real-time portfolio information.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.schemas import Position
from backend.infra.db import get_session_context

logger = logging.getLogger(__name__)


class PortfolioService:
    """Service for portfolio operations and calculations."""
    
    def __init__(self):
        """Initialize portfolio service."""
        self.default_cash = Decimal('100000.00')  # Default starting capital
    
    async def get_user_portfolio(self, user_id: str) -> Dict[str, Any]:
        """
        Get comprehensive portfolio data for a user.
        
        Args:
            user_id: User ID to fetch portfolio for
            
        Returns:
            Dictionary with portfolio summary and positions
        """
        try:
            async with get_session_context() as session:
                # Get all positions (global for now - will add user_id filter later)
                positions_result = await session.execute(
                    select(Position)
                )
                positions = positions_result.scalars().all()
                
                # Calculate real-time metrics
                total_position_value = Decimal('0')
                total_realized_pnl = Decimal('0')
                
                positions_data = []
                for pos in positions:
                    # Calculate unrealized P&L: (current_price - avg_price) * qty
                    # Note: We don't have current_price yet, so unrealized_pnl = 0 for now
                    position_value = pos.avg_price * pos.qty
                    total_position_value += position_value
                    total_realized_pnl += (pos.realized_pnl or Decimal('0'))
                    
                    positions_data.append({
                        'symbol': pos.symbol,
                        'quantity': float(pos.qty),
                        'avg_price': str(pos.avg_price),
                        'market_value': str(position_value),
                        'unrealized_pnl': '0.00',  # Will calculate with real-time prices later
                        'realized_pnl': str(pos.realized_pnl or Decimal('0'))
                    })
                
                # Calculate portfolio totals
                # Cash = starting capital - position values + realized P&L
                cash = self.default_cash - total_position_value + total_realized_pnl
                total_equity = cash + total_position_value
                total_pl = total_equity - self.default_cash
                
                return {
                    'total_value': str(total_equity),
                    'cash': str(cash),
                    'positions_value': str(total_position_value),
                    'total_pl': str(total_pl),
                    'day_pl': '0.00',  # Will calculate with price changes later
                    'positions': positions_data,
                    'user_id': user_id,
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to get portfolio for user {user_id}: {e}")
            # Return default portfolio on error
            return {
                'total_value': '100000.00',
                'cash': '100000.00',
                'positions_value': '0.00',
                'total_pl': '0.00',
                'day_pl': '0.00',
                'positions': [],
                'user_id': user_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
    
    async def get_portfolio_history(
        self,
        user_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        interval: str = '1d'
    ) -> List[Dict[str, Any]]:
        """
        Get portfolio value history.
        
        Args:
            user_id: User ID
            start_date: Start date (ISO format)
            end_date: End date (ISO format)
            interval: Time interval (1m, 5m, 15m, 1h, 1d)
            
        Returns:
            List of historical portfolio snapshots
        """
        # TODO: Implement actual historical data from portfolio_history table
        # For now, return current snapshot as single data point
        
        try:
            current_portfolio = await self.get_user_portfolio(user_id)
            
            return [{
                'timestamp': current_portfolio['timestamp'],
                'total_value': current_portfolio['total_value'],
                'cash': current_portfolio['cash'],
                'positions_value': current_portfolio['positions_value']
            }]
            
        except Exception as e:
            logger.error(f"Failed to get portfolio history for user {user_id}: {e}")
            return []
    
    async def get_position_by_symbol(
        self,
        user_id: str,
        symbol: str
    ) -> Optional[Dict[str, Any]]:
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


# Global service instance
_portfolio_service: Optional[PortfolioService] = None


def get_portfolio_service() -> PortfolioService:
    """Get or create global portfolio service instance."""
    global _portfolio_service
    if _portfolio_service is None:
        _portfolio_service = PortfolioService()
    return _portfolio_service
