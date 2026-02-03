"""
API Routes Package

This package contains all API route handlers organized by domain:
- auth: Authentication and authorization endpoints
- orders: Order management endpoints  
- positions: Position tracking endpoints
- risk: Risk management and emergency controls
- strategy: Strategy configuration endpoints
- backtest: Backtesting endpoints
- audit: Audit trail endpoints
- market_data: Market data endpoints
- websocket: WebSocket handlers

L-01 FIX: Added module docstring and exports.
"""

from . import (
    auth,
    orders,
    positions,
    risk,
    strategy,
    backtest,
    audit,
)

__all__ = [
    "auth",
    "orders", 
    "positions",
    "risk",
    "strategy",
    "backtest",
    "audit",
]