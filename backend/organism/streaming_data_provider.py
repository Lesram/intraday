"""
Streaming Data Provider — zero-latency bar access via Alpaca WebSocket.

Wraps ``AlpacaMarketDataStream`` to maintain in-memory ring buffers
of OHLCV bars and latest quotes per symbol.  The organism engine
calls ``get_bars()`` instead of REST, eliminating ~10s fetch latency.

Usage::

    provider = StreamingDataProvider()
    await provider.start(symbols, api_key, api_secret)
    df = provider.get_bars("AAPL", lookback=200)
    quote = provider.get_latest_quote("AAPL")
    await provider.stop()
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

import pandas as pd

from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Default ring buffer size — enough for ~33 hours of 1-min bars
_DEFAULT_BUFFER_SIZE = 2000


class StreamingDataProvider:
    """In-memory streaming data provider backed by Alpaca WebSocket."""

    def __init__(self, buffer_size: int = _DEFAULT_BUFFER_SIZE) -> None:
        self._buffer_size = buffer_size
        self._stream: AlpacaMarketDataStream | None = None

        # Ring buffers: symbol → deque of OHLCV dicts
        self._bars: dict[str, deque[dict[str, Any]]] = {}
        # Latest quote per symbol
        self._quotes: dict[str, dict[str, Any]] = {}
        # Track last bar timestamp per symbol for freshness checks
        self._last_bar_ts: dict[str, float] = {}

        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(
        self,
        symbols: list[str],
        api_key: str,
        api_secret: str,
        feed: str = "sip",
    ) -> None:
        """Connect to Alpaca WebSocket and subscribe to bars + quotes."""
        if self._running:
            logger.warning("StreamingDataProvider already running")
            return

        self._stream = AlpacaMarketDataStream(
            api_key=api_key,
            api_secret=api_secret,
            feed=feed,
        )

        # Wire callbacks
        self._stream.on_bar = self._on_bar
        self._stream.on_quote = self._on_quote

        connected = await self._stream.connect()
        if not connected:
            logger.error("StreamingDataProvider failed to connect")
            return

        # Subscribe to bars and quotes
        symbols_upper = [s.upper() for s in symbols]
        await self._stream.subscribe_bars(symbols_upper)
        await self._stream.subscribe_quotes(symbols_upper)

        self._running = True
        logger.info(
            "StreamingDataProvider started: %d symbols, feed=%s",
            len(symbols_upper),
            feed,
        )

    async def stop(self) -> None:
        """Disconnect from Alpaca WebSocket cleanly."""
        self._running = False
        if self._stream:
            await self._stream.disconnect()
            self._stream = None
        logger.info("StreamingDataProvider stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Data Access (zero-latency) ────────────────────────────────

    def get_bars(self, symbol: str, lookback: int = 200) -> pd.DataFrame:
        """Return latest N bars from the ring buffer as a DataFrame.

        Returns an empty DataFrame if no data is available.
        Warns if the newest bar is more than 5 minutes stale.
        """
        symbol = symbol.upper()
        buf = self._bars.get(symbol)
        if not buf or len(buf) == 0:
            return pd.DataFrame()

        # Freshness check
        last_ts = self._last_bar_ts.get(symbol, 0)
        staleness = time.time() - last_ts
        if staleness > 300:  # 5 minutes
            logger.warning(
                "Stale data for %s: last bar %.0fs ago",
                symbol,
                staleness,
            )

        # Convert deque to DataFrame (most recent last)
        rows = list(buf)[-lookback:]
        df = pd.DataFrame(rows)

        # Ensure standard column order
        expected = ["timestamp", "open", "high", "low", "close", "volume"]
        for col in expected:
            if col not in df.columns:
                df[col] = None

        return df

    def get_latest_quote(self, symbol: str) -> dict[str, Any]:
        """Return latest bid/ask quote for a symbol."""
        return self._quotes.get(symbol.upper(), {})

    def has_data(self, symbol: str) -> bool:
        """Check if we have any buffered bars for a symbol."""
        buf = self._bars.get(symbol.upper())
        return buf is not None and len(buf) > 0

    def bar_count(self, symbol: str) -> int:
        """Return number of buffered bars for a symbol."""
        buf = self._bars.get(symbol.upper())
        return len(buf) if buf else 0

    # ── Subscription Management ───────────────────────────────────

    async def update_subscriptions(self, symbols: list[str]) -> None:
        """Add/remove symbol subscriptions dynamically for universe rotation."""
        if not self._stream or not self._stream.is_authenticated:
            logger.warning("Cannot update subscriptions — not connected")
            return

        new_set = {s.upper() for s in symbols}
        current_quotes = self._stream.quote_subscriptions
        current_bars = set()
        for tf_set in self._stream.bar_subscriptions.values():
            current_bars.update(tf_set)

        current_set = current_quotes | current_bars

        to_add = list(new_set - current_set)
        to_remove = list(current_set - new_set)

        if to_add:
            await self._stream.subscribe_bars(to_add)
            await self._stream.subscribe_quotes(to_add)
            logger.info("Streaming subscribed: +%d symbols", len(to_add))

        if to_remove:
            await self._stream.unsubscribe(to_remove)
            logger.info("Streaming unsubscribed: -%d symbols", len(to_remove))

    # ── Internal Callbacks ────────────────────────────────────────

    async def _on_bar(self, symbol: str, bar_data: dict[str, Any]) -> None:
        """Callback from AlpacaMarketDataStream for bar messages."""
        symbol = symbol.upper()
        if symbol not in self._bars:
            self._bars[symbol] = deque(maxlen=self._buffer_size)

        self._bars[symbol].append({
            "timestamp": bar_data.get("timestamp"),
            "open": bar_data.get("open"),
            "high": bar_data.get("high"),
            "low": bar_data.get("low"),
            "close": bar_data.get("close"),
            "volume": bar_data.get("volume"),
        })
        self._last_bar_ts[symbol] = time.time()

    async def _on_quote(self, symbol: str, quote_data: dict[str, Any]) -> None:
        """Callback from AlpacaMarketDataStream for quote messages."""
        self._quotes[symbol.upper()] = {
            "bid": quote_data.get("bid"),
            "ask": quote_data.get("ask"),
            "bid_size": quote_data.get("bid_size"),
            "ask_size": quote_data.get("ask_size"),
            "mid": quote_data.get("mid"),
            "spread": quote_data.get("spread"),
            "timestamp": quote_data.get("timestamp"),
        }

    def get_stats(self) -> dict[str, Any]:
        """Return provider statistics."""
        return {
            "running": self._running,
            "symbols_with_bars": len(self._bars),
            "symbols_with_quotes": len(self._quotes),
            "total_bars": sum(len(b) for b in self._bars.values()),
            "stream_stats": self._stream.get_stats() if self._stream else None,
        }
