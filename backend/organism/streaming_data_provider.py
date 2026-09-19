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

import os
import time
from collections import deque
from typing import Any

import pandas as pd

from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Default ring buffer size — enough for ~33 hours of 1-min bars
_DEFAULT_BUFFER_SIZE = 2000

# Audit-E findings 5+6 (2026-05-01): the get_bars() function used to only
# WARN on staleness but still return the stale data. Production saw AMZN
# 13:30 UTC bars served at 15:18 UTC (108min stale). The same root cause
# corrupted the ORB cache for IWM (1,295 wrong shadow events). Now: when
# staleness exceeds threshold, return empty DataFrame so callers fall
# through to REST. Default 120s = 2-bar tolerance for 1Min bars.
_STALENESS_REJECT_S = float(os.getenv("ORGANISM_STREAMING_STALENESS_REJECT_S", "120"))


class StreamingDataProvider:
    """In-memory streaming data provider backed by Alpaca WebSocket."""

    def __init__(
        self,
        buffer_size: int = _DEFAULT_BUFFER_SIZE,
        time_fn=None,
    ) -> None:
        # V5 B-T-4 / Wave-19 (2026-05-03): clock injection so replay /
        # synthetic-time tests can drive `get_bar_age()` and the
        # internal staleness checks against a deterministic clock.
        # Default is the canonical `time.time` for live use.
        self._time_fn = time_fn if time_fn is not None else time.time

        self._buffer_size = buffer_size
        self._stream: AlpacaMarketDataStream | None = None

        # Ring buffers: symbol → deque of OHLCV dicts
        self._bars: dict[str, deque[dict[str, Any]]] = {}
        # Latest quote per symbol
        self._quotes: dict[str, dict[str, Any]] = {}
        # Track last bar timestamp per symbol for freshness checks
        self._last_bar_ts: dict[str, float] = {}
        # Global last-update time (max across all symbols) for engine stale gate
        self.last_update_time: float | None = None

        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(
        self,
        symbols: list[str],
        api_key: str,
        api_secret: str,
        feed: str = "sip",
        data_client: Any | None = None,
    ) -> None:
        """Connect to Alpaca WebSocket and subscribe to bars + quotes.

        If *data_client* is provided, the ring buffers are pre-filled with
        historical bars via REST so the engine can trade on the very first tick
        instead of waiting for ``MIN_BARS`` streaming bars to arrive.
        """
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

        # Pre-fill ring buffers with historical bars from REST
        if data_client is not None:
            await self._prefill(symbols_upper, data_client)

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

    def stale_symbols(
        self, threshold_s: float, now: float | None = None,
    ) -> list[tuple[str, float]]:
        """V9 PP-6 / Wave-45 (2026-05-03): per-symbol staleness check.

        Returns list of (symbol, staleness_s) for symbols whose last
        bar / quote update is older than threshold_s.  The aggregate
        `last_update_time` gate is too coarse — active symbols can stop
        streaming while background symbols keep ticking, hiding the
        staleness from the global gate.

        Returns an empty list if no symbols have been seen yet.
        """
        if now is None:
            now = self._time_fn()
        out: list[tuple[str, float]] = []
        for sym, ts in self._last_bar_ts.items():
            age = now - ts
            if age > threshold_s:
                out.append((sym, age))
        return out

    # ── Data Access (zero-latency) ────────────────────────────────

    def get_bars(self, symbol: str, lookback: int = 200) -> pd.DataFrame:
        """Return latest N bars from the ring buffer as a DataFrame.

        Returns an empty DataFrame if no data is available OR if the
        newest bar is older than the staleness reject threshold (default
        120s). The empty-DataFrame return forces the caller to fall
        through to REST, which gets fresh bars from the API.

        Audit-E findings 5+6 (2026-05-01): previously this function only
        WARN'd on staleness > 300s but still returned stale bars. The
        scanners were getting 108min-old AMZN closes; the ORB cache for
        IWM was poisoned with prior-session bars; 1,295 spurious shadow
        events fired Friday. Now: reject + force REST fallback.
        """
        symbol = symbol.upper()
        buf = self._bars.get(symbol)
        if not buf or len(buf) == 0:
            return pd.DataFrame()

        # Freshness check — reject if stale (force REST fallback)
        last_ts = self._last_bar_ts.get(symbol, 0)
        staleness = self._time_fn() - last_ts
        if staleness > _STALENESS_REJECT_S:
            logger.warning(
                "Streaming bars REJECTED for %s: %.0fs stale (> %.0fs threshold) "
                "— caller will fall through to REST",
                symbol, staleness, _STALENESS_REJECT_S,
            )
            return pd.DataFrame()  # force REST fallback
        if staleness > 60:
            # Soft-warn at >1 bar but still return data
            logger.info(
                "Streaming bars for %s slightly stale: %.0fs old",
                symbol, staleness,
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

    # ── Pre-fill ──────────────────────────────────────────────────

    async def _prefill(self, symbols: list[str], data_client: Any) -> None:
        """Seed ring buffers with historical bars so engine can trade immediately.

        Fetches LIVE_LOOKBACK bars per symbol via REST.  Individual failures
        are logged and skipped — remaining symbols still get pre-filled.
        """
        import os

        lookback = int(os.getenv("ORGANISM_LIVE_LOOKBACK", "100"))
        timeframe = os.getenv("ORGANISM_LIVE_TIMEFRAME", "1Day")
        filled = 0

        for symbol in symbols:
            try:
                df = await data_client.get_historical_bars_df(
                    symbol, lookback=lookback, timeframe=timeframe,
                )
                if df is None or df.empty:
                    continue

                buf: deque[dict[str, Any]] = deque(maxlen=self._buffer_size)
                for _, row in df.iterrows():
                    buf.append({
                        "timestamp": row.get("timestamp"),
                        "open": row.get("open"),
                        "high": row.get("high"),
                        "low": row.get("low"),
                        "close": row.get("close"),
                        "volume": row.get("volume"),
                    })
                self._bars[symbol] = buf
                _now = self._time_fn()
                self._last_bar_ts[symbol] = _now
                self.last_update_time = _now
                filled += 1
            except Exception as e:
                logger.warning("Pre-fill failed for %s: %s", symbol, e)

        logger.info("Pre-filled %d/%d symbols", filled, len(symbols))

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
        _now = self._time_fn()
        self._last_bar_ts[symbol] = _now
        self.last_update_time = _now

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

    def get_bar_age(self, symbol: str) -> float:
        """Return seconds since last bar update for symbol.

        Returns float('inf') if no bar data exists for the symbol.
        """
        ts = self._last_bar_ts.get(symbol.upper())
        if ts is None:
            return float("inf")
        return self._time_fn() - ts

    async def check_and_recover_stale_stream(
        self, stale_threshold: float = 300.0,
    ) -> bool:
        """Check if all bar data is stale and force reconnect if so.

        Called from the engine tick loop.  Returns True if a recovery
        was attempted so the caller can log it.

        Only triggers when *every* tracked symbol is stale (avoids false
        positives from a single missing symbol).
        """
        if not self._running or not self._stream:
            return False

        if not self._last_bar_ts:
            return False  # No data yet — don't trigger

        now = self._time_fn()
        stale_count = sum(
            1 for ts in self._last_bar_ts.values()
            if now - ts > stale_threshold
        )

        if stale_count < len(self._last_bar_ts):
            return False  # At least some symbols are fresh

        # All symbols are stale — force reconnect
        logger.warning(
            "ALL %d symbols stale (>%.0fs) — forcing stream reconnect",
            stale_count,
            stale_threshold,
        )

        try:
            stream = self._stream
            # Disconnect + reconnect — connect() calls _resubscribe_all()
            await stream._cleanup_connection()
            success = await stream.connect()
            if success:
                logger.info("Stale stream recovery: reconnected successfully")
            else:
                logger.error("Stale stream recovery: reconnect failed")
            return True
        except Exception as e:
            logger.error("Stale stream recovery failed: %s", e)
            return True

    def get_stats(self) -> dict[str, Any]:
        """Return provider statistics."""
        now = self._time_fn()
        max_staleness = 0.0
        if self._last_bar_ts:
            max_staleness = max(now - ts for ts in self._last_bar_ts.values())
        return {
            "running": self._running,
            "symbols_with_bars": len(self._bars),
            "symbols_with_quotes": len(self._quotes),
            "total_bars": sum(len(b) for b in self._bars.values()),
            "max_staleness_s": round(max_staleness, 1),
            "stream_stats": self._stream.get_stats() if self._stream else None,
        }
