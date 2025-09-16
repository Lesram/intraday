"""
Signal service for generating and managing trading signals.
"""

import asyncio
from typing import Dict, List, Any
from datetime import datetime, UTC


class SignalService:
    """Service for generating trading signals"""
    
    def __init__(self):
        self.signals = {}
    
    async def get_signals(self, symbol: str = None) -> List[Dict[str, Any]]:
        """Get trading signals"""
        if symbol:
            return [{
                "symbol": symbol,
                "signal": "BUY",
                "confidence": 0.75,
                "timestamp": datetime.now(UTC).isoformat()
            }]
        
        return [{
            "symbol": "AAPL",
            "signal": "BUY", 
            "confidence": 0.8,
            "timestamp": datetime.now(UTC).isoformat()
        }]
    
    async def generate_signal(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a trading signal"""
        return {
            "symbol": symbol,
            "signal": "BUY",
            "confidence": 0.75,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data
        }


# Global instance
signal_service = SignalService()


async def get_signal_service():
    """Get signal service instance"""
    return signal_service

# Minimal default function so tests can monkey-patch by name
from typing import Any, List

def get_signals(*args, **kwargs):
    """Shim function for testing - returns mock signal data by default."""
    # Default mock response for when not patched in tests
    return [
        {
            "symbol": "AAPL",
            "signal_type": "BUY",
            "confidence": 0.8,
            "target_price": 150.0,
            "position_size": 100.0,
            "timestamp": "2024-01-01T12:00:00Z"
        }
    ]
