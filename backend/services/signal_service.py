"""Signal service -- cache layer for trading signals.

P&L-004: This service is a cache/relay layer, NOT a signal generator.
Real signal generation happens in MultiStrategyLiveRunner._generate_strategy_signals().
This service caches those signals for API consumers (dashboards, external systems).

Do NOT rely on generate_signal() for trading decisions -- it returns the last
cached signal or a neutral HOLD.  The live runner updates this cache on every tick
via update_signals().
"""

import logging
import warnings
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class SignalService:
    """Service for generating trading signals via the strategy engine."""

    def __init__(self):
        self._last_signals: list[dict[str, Any]] = []

    def update_signals(self, signals: list[dict[str, Any]]) -> None:
        """Update cached signals from the live runner / strategy engine."""
        self._last_signals = signals

    async def get_signals(self, symbol: str = None) -> list[dict[str, Any]]:
        """Get latest trading signals, optionally filtered by symbol."""
        if not self._last_signals:
            return []
        if symbol:
            return [s for s in self._last_signals if s.get("symbol") == symbol]
        return list(self._last_signals)

    async def generate_signal(self, symbol: str, data: dict[str, Any]) -> dict[str, Any]:
        """Return the most recent cached signal for a symbol.

        P&L-004: This returns cached data from the live runner, NOT a freshly
        computed signal.  If no cached signal exists, returns a conservative
        HOLD with 0% confidence.
        """
        warnings.warn(
            "SignalService.generate_signal() returns cached/stale data. "
            "Use MultiStrategyLiveRunner for real-time signal generation.",
            DeprecationWarning,
            stacklevel=2,
        )
        matching = [s for s in self._last_signals if s.get("symbol") == symbol]
        if matching:
            return matching[-1]
        return {
            "symbol": symbol,
            "signal": "HOLD",
            "confidence": 0.0,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data,
        }


# Global instance
signal_service = SignalService()


async def get_signal_service():
    """Get signal service instance"""
    return signal_service


def get_signals(*args, **kwargs):
    """Synchronous shim for testing — returns empty list by default."""
    return []
