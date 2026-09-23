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

import asyncio
import math
import os
import time
from collections import deque
from datetime import datetime
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
        # Keep subscribed-but-unseen symbols fail-closed, and ignore callbacks
        # arriving after a confirmed unsubscribe until that symbol is re-added.
        self._subscribed_symbols: set[str] = set()
        self._retired_symbols: set[str] = set()

        self._running = False
        self._session_generation = 0
        self._lifecycle_lock = asyncio.Lock()

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
        async with self._lifecycle_lock:
            if self._running:
                logger.warning("StreamingDataProvider already running")
                return

            # Keep a failed disconnect's reference until cleanup succeeds.
            await self._disconnect_stream(self._stream)
            self._invalidate_session()
            generation = self._session_generation
            stream = AlpacaMarketDataStream(
                api_key=api_key, api_secret=api_secret, feed=feed,
            )
            self._stream = stream
            self._wire_callbacks(stream, generation)
            started = False
            try:
                connected = await stream.connect()
                if not self._is_current_session(stream, generation):
                    return
                if connected is not True:
                    logger.error("StreamingDataProvider failed to connect")
                    return

                symbols_upper = [s.upper() for s in symbols]
                bars_ok = await stream.subscribe_bars(symbols_upper)
                if not self._is_current_session(stream, generation):
                    return
                if bars_ok is not True:
                    logger.error("StreamingDataProvider bar subscription failed")
                    return
                self._subscribed_symbols.update(symbols_upper)
                quotes_ok = await stream.subscribe_quotes(symbols_upper)
                if not self._is_current_session(stream, generation):
                    return
                if quotes_ok is not True:
                    logger.error("StreamingDataProvider quote subscription failed")
                    return

                if data_client is not None:
                    await self._prefill(symbols_upper, data_client)
                if not self._is_current_session(stream, generation):
                    return
                self._running = started = True
                logger.info(
                    "StreamingDataProvider started: %d symbols, feed=%s",
                    len(symbols_upper), feed,
                )
            finally:
                if not started:
                    if self._is_current_session(stream, generation):
                        self._invalidate_session()
                    await self._disconnect_stream(stream)

    async def stop(self) -> None:
        """Disconnect from Alpaca WebSocket cleanly."""
        # Invalidate before waiting for an in-flight connect/prefill/rotation.
        # Their continuations and callbacks must not restore stopped state.
        self._invalidate_session()
        async with self._lifecycle_lock:
            # A start already queued ahead of this stop may have completed
            # while the lock was pending. Stop owns the final empty state.
            self._invalidate_session()
            await self._disconnect_stream(self._stream)
        logger.info("StreamingDataProvider stopped")

    def _invalidate_session(self) -> None:
        self._session_generation += 1
        self._running = False
        self._subscribed_symbols.clear()
        self._retired_symbols.clear()
        self._bars.clear()
        self._quotes.clear()
        self._last_bar_ts.clear()
        self.last_update_time = None

    async def _disconnect_stream(self, stream) -> None:
        if stream is not None:
            await stream.disconnect()
            if self._stream is stream:
                self._stream = None

    def _is_current_session(self, stream, generation: int) -> bool:
        return self._stream is stream and self._session_generation == generation

    def _wire_callbacks(self, stream, generation: int) -> None:
        async def on_bar(symbol, data):
            if (self._is_current_session(stream, generation)
                    and symbol.upper() in self._subscribed_symbols):
                await self._on_bar(symbol, data)

        async def on_quote(symbol, data):
            if (self._is_current_session(stream, generation)
                    and symbol.upper() in self._subscribed_symbols):
                await self._on_quote(symbol, data)

        stream.on_bar = on_bar
        stream.on_quote = on_quote

    @property
    def is_running(self) -> bool:
        return self._running

    def stale_symbols(
        self, threshold_s: float, now: float | None = None,
    ) -> list[tuple[str, float]]:
        """V9 PP-6 / Wave-45 (2026-05-03): per-symbol staleness check.

        Returns list of (symbol, staleness_s) for symbols whose last
        advancing, fresh bar update is older than threshold_s. Quotes do not
        establish bar freshness. The aggregate
        `last_update_time` gate is too coarse — active symbols can stop
        streaming while background symbols keep ticking, hiding the
        staleness from the global gate.

        Subscribed symbols with no bar yet are stale until data arrives.
        """
        if now is None:
            now = self._time_fn()
        out: list[tuple[str, float]] = []
        for sym in sorted(self._freshness_symbols()):
            age = self._bar_receipt_age(sym, now)
            if age > threshold_s:
                out.append((sym, age))
        return out

    def _freshness_symbols(self) -> set[str]:
        return set(self._last_bar_ts) | getattr(self, "_subscribed_symbols", set())

    def _bar_receipt_age(self, symbol: str, now: float) -> float:
        ts = self._last_bar_ts.get(symbol)
        if ts is None or not math.isfinite(now) or not math.isfinite(ts) or now < ts:
            return float("inf")
        return now - ts

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
        staleness = self._bar_receipt_age(symbol, self._time_fn())
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
        async with self._lifecycle_lock:
            await self._update_subscriptions(symbols)

    async def _update_subscriptions(self, symbols: list[str]) -> None:
        if not self._stream or not self._stream.is_authenticated:
            logger.warning("Cannot update subscriptions — not connected")
            return
        stream, generation = self._stream, self._session_generation

        new_set = {s.upper() for s in symbols}
        current_quotes = set(self._stream.quote_subscriptions)
        current_bars = set()
        for tf_set in self._stream.bar_subscriptions.values():
            current_bars.update(tf_set)

        current_set = current_quotes | current_bars | self._subscribed_symbols
        self._subscribed_symbols.update(current_set)

        bars_to_add = list(new_set - current_bars)
        quotes_to_add = list(new_set - current_quotes)
        to_remove = list(current_set - new_set)

        if bars_to_add:
            added = await stream.subscribe_bars(bars_to_add)
            if not self._is_current_session(stream, generation):
                return
            if added is not True:
                logger.warning("Streaming bar subscription failed: %d symbols", len(bars_to_add))
                return
            self._subscribed_symbols.update(bars_to_add)
            self._retired_symbols.difference_update(bars_to_add)
        if quotes_to_add:
            added = await stream.subscribe_quotes(quotes_to_add)
            if not self._is_current_session(stream, generation):
                return
            if added is not True:
                logger.warning("Streaming quote subscription failed: %d symbols", len(quotes_to_add))
                return
        if bars_to_add or quotes_to_add:
            logger.info("Streaming subscribed: +%d symbols", len(set(bars_to_add) | set(quotes_to_add)))

        if to_remove:
            removed = await stream.unsubscribe(to_remove)
            if not self._is_current_session(stream, generation):
                return
            if removed is not True:
                logger.warning("Streaming unsubscribe failed: %d symbols retained", len(to_remove))
                return
            self._subscribed_symbols.difference_update(to_remove)
            self._retired_symbols.update(to_remove)
            for symbol in to_remove:
                self._bars.pop(symbol, None)
                self._quotes.pop(symbol, None)
                self._last_bar_ts.pop(symbol, None)
            self.last_update_time = max(self._last_bar_ts.values(), default=None)
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
        generation = self._session_generation

        for symbol in symbols:
            try:
                df = await data_client.get_historical_bars_df(
                    symbol, lookback=lookback, timeframe=timeframe,
                )
                if generation != self._session_generation:
                    return
                if df is None or df.empty:
                    continue

                # Historical arrival is not evidence of a fresh bar. Validate
                # every timestamp before replacing any existing stream state.
                now = self._time_fn()
                rows_by_time: dict[pd.Timestamp, dict[str, Any]] = {}
                for _, row in df.iterrows():
                    timestamp = pd.Timestamp(row.get("timestamp"))
                    if pd.isna(timestamp) or timestamp.tzinfo is None:
                        raise ValueError("prefill timestamp must be timezone-aware")
                    timestamp = timestamp.tz_convert("UTC")
                    if timestamp.timestamp() > now:
                        raise ValueError("prefill timestamp is in the future")
                    rows_by_time[timestamp] = {
                        "timestamp": timestamp.isoformat(),
                        "open": row.get("open"),
                        "high": row.get("high"),
                        "low": row.get("low"),
                        "close": row.get("close"),
                        "volume": row.get("volume"),
                    }
                newest_historical = max(rows_by_time).timestamp()
                # Subscription callbacks can run while REST is awaited. Keep
                # their newer data (and any same-minute stream correction).
                existing = self._bars.get(symbol, ())
                for row in existing:
                    timestamp = pd.Timestamp(row.get("timestamp"))
                    if pd.isna(timestamp) or timestamp.tzinfo is None:
                        raise ValueError("existing stream timestamp must be timezone-aware")
                    timestamp = timestamp.tz_convert("UTC")
                    if timestamp.timestamp() > now:
                        raise ValueError("existing stream timestamp is in the future")
                    rows_by_time[timestamp] = row
                self._bars[symbol] = deque(
                    (rows_by_time[timestamp] for timestamp in sorted(rows_by_time)),
                    maxlen=self._buffer_size,
                )
                # Existing streaming receipt timestamps keep their established
                # semantics; historical-only state uses the actual bar time.
                self._last_bar_ts[symbol] = max(
                    self._last_bar_ts.get(symbol, float("-inf")), newest_historical,
                )
                self.last_update_time = max(self._last_bar_ts.values())
                filled += 1
            except Exception as e:
                logger.warning("Pre-fill failed for %s: %s", symbol, e)

        logger.info("Pre-filled %d/%d symbols", filled, len(symbols))

    # ── Internal Callbacks ────────────────────────────────────────

    async def _on_bar(self, symbol: str, bar_data: dict[str, Any]) -> None:
        """Callback from AlpacaMarketDataStream for bar messages."""
        symbol = symbol.upper()
        if symbol in self._retired_symbols:
            return
        try:
            value = bar_data.get("timestamp")
            if not isinstance(value, (str, datetime, pd.Timestamp)):
                raise ValueError("invalid_timestamp")
            stamp = pd.Timestamp(value)
            now = self._time_fn()
            if pd.isna(stamp) or stamp.tzinfo is None or not math.isfinite(now):
                raise ValueError("invalid_timestamp")
            stamp = stamp.tz_convert("UTC")
            bar_time = stamp.timestamp()
            if not math.isfinite(bar_time) or bar_time > now:
                raise ValueError("future_timestamp")
            prior_receipt = self._last_bar_ts.get(symbol)
            if prior_receipt is not None and (
                not math.isfinite(prior_receipt) or now < prior_receipt
            ):
                raise ValueError("invalid_freshness_clock")
            buf = self._bars.get(symbol)
            latest = pd.Timestamp(buf[-1]["timestamp"]) if buf else None
            if latest is not None and (pd.isna(latest) or latest.tzinfo is None):
                raise ValueError("invalid_buffer_timestamp")
            if latest is not None and stamp < latest:
                # A delayed old bar must not replace the newest feature row or
                # masquerade as evidence that this symbol has recovered.
                return
        except (TypeError, ValueError, OverflowError):
            logger.warning("Streaming bar rejected for %s: invalid timestamp or freshness clock", symbol)
            return
        if symbol not in self._bars:
            self._bars[symbol] = deque(maxlen=self._buffer_size)

        row = {
            "timestamp": stamp.isoformat(),
            "open": bar_data.get("open"),
            "high": bar_data.get("high"),
            "low": bar_data.get("low"),
            "close": bar_data.get("close"),
            "volume": bar_data.get("volume"),
        }
        if latest == stamp:
            # Same-bar corrections replace values without adding rows or
            # renewing the last genuinely advancing fresh-bar receipt.
            self._bars[symbol][-1] = row
        else:
            self._bars[symbol].append(row)
            if now - bar_time <= _STALENESS_REJECT_S:
                self._last_bar_ts[symbol] = now
            elif symbol not in self._last_bar_ts:
                # Delayed history may fill the buffer but is not live recovery.
                self._last_bar_ts[symbol] = bar_time
            self.last_update_time = max(self._last_bar_ts.values(), default=None)

    async def _on_quote(self, symbol: str, quote_data: dict[str, Any]) -> None:
        """Callback from AlpacaMarketDataStream for quote messages."""
        if symbol.upper() in self._retired_symbols:
            return
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
        return self._bar_receipt_age(symbol.upper(), self._time_fn())

    async def check_and_recover_stale_stream(
        self, stale_threshold: float = 300.0,
    ) -> bool:
        """Check if all bar data is stale and force reconnect if so.

        Called from the engine tick loop.  Returns True if a recovery
        was attempted so the caller can log it.

        Only triggers when *every* tracked symbol is stale (avoids false
        positives from a single missing symbol).
        """
        async with self._lifecycle_lock:
            return await self._recover_stale_stream(stale_threshold)

    async def _recover_stale_stream(self, stale_threshold: float) -> bool:
        if not self._running or not self._stream:
            return False

        tracked = self._freshness_symbols()
        if not tracked or not self._last_bar_ts:
            # Missing first bars block entries, but repeatedly reconnecting
            # before the first bar arrives would prevent startup recovery.
            return False

        now = self._time_fn()
        stale_count = sum(
            1 for symbol in tracked
            if self._bar_receipt_age(symbol, now) > stale_threshold
        )

        if stale_count < len(tracked):
            return False  # At least some symbols are fresh

        # All symbols are stale — force reconnect
        logger.warning(
            "ALL %d symbols stale (>%.0fs) — forcing stream reconnect",
            stale_count,
            stale_threshold,
        )

        try:
            stream = self._stream
            # Retain the stale buffers/receipts, but revoke callbacks held by
            # the connection being replaced. Reconnect itself is not health.
            self._session_generation += 1
            generation = self._session_generation
            # Disconnect + reconnect — connect() calls _resubscribe_all()
            await stream._cleanup_connection()
            if not self._is_current_session(stream, generation):
                return True
            success = await stream.connect()
            if not self._is_current_session(stream, generation):
                return True
            if success is True:
                self._wire_callbacks(stream, generation)
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
