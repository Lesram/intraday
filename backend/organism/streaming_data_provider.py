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
# Audit 2026-09-29 (MDP-01): provider websocket symbol cap (Alpaca IEX
# Basic refuses >~30 symbols with "symbol limit exceeded"). The engine
# already sends a prioritised bounded list; this is defence in depth.
# Default leaves headroom under the documented 30-symbol IEX plan limit;
# keep in sync with live_engine.STREAM_MAX_SYMBOLS (same env var).
MAX_STREAM_SYMBOLS = max(1, int(os.getenv("ORGANISM_STREAM_MAX_SYMBOLS", "28")))


class StreamingDataProvider:
    """In-memory streaming data provider backed by Alpaca WebSocket."""

    STARTUP_RETRY_INTERVAL_S = 30.0
    STARTUP_TIMEOUT_S = 25.0

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
        self._start_config: dict[str, Any] | None = None
        self._desired_symbols: set[str] = set()
        self._recovery_enabled = False
        self._recovery_due_at = 0.0
        self._transport_generation: int | None = None

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(
        self,
        symbols: list[str],
        api_key: str,
        api_secret: str,
        feed: str = "sip",
        data_client: Any | None = None,
        *,
        _prefill_history: bool = True,
    ) -> bool:
        """Connect to Alpaca WebSocket and subscribe to bars + quotes.

        If *data_client* is provided, the ring buffers are pre-filled with
        historical bars via REST for feature warmup. A genuine advancing bar
        in the confirmed current session is still required for stream freshness.
        """
        self._start_config = dict(api_key=api_key, api_secret=api_secret, feed=feed, data_client=data_client)
        self._desired_symbols = {s.upper() for s in symbols}
        self._recovery_enabled = True
        async with self._lifecycle_lock:
            if self._running and self._stream and self._stream.is_authenticated:
                return True
            self._recovery_due_at = time.monotonic() + self.STARTUP_RETRY_INTERVAL_S

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
                async with asyncio.timeout(self.STARTUP_TIMEOUT_S):
                    connected = await stream.connect()
                    if not self._is_current_session(stream, generation):
                        return False
                    if connected is not True:
                        logger.error("StreamingDataProvider failed to connect")
                        return False

                    symbols_upper = [s.upper() for s in symbols]
                    bars_ok = await stream.subscribe_bars(symbols_upper)
                    if not self._is_current_session(stream, generation):
                        return False
                    if bars_ok is not True:
                        logger.error("StreamingDataProvider bar subscription failed")
                        return False
                    self._subscribed_symbols.update(symbols_upper)
                    quotes_ok = await stream.subscribe_quotes(symbols_upper)
                    if not self._is_current_session(stream, generation):
                        return False
                    if quotes_ok is not True:
                        logger.error("StreamingDataProvider quote subscription failed")
                        return False

                    if data_client is not None and _prefill_history:
                        await self._prefill(symbols_upper, data_client)
                    if not self._is_current_session(stream, generation):
                        return False
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

            return started

    async def stop(self) -> None:
        """Disconnect from Alpaca WebSocket cleanly."""
        self._recovery_enabled = False
        self._start_config = None
        self._desired_symbols.clear()
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
        self._transport_generation = None

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
                self._observe_transport_generation(stream)
                await self._on_bar(symbol, data)

        async def on_quote(symbol, data):
            if (self._is_current_session(stream, generation)
                    and symbol.upper() in self._subscribed_symbols):
                await self._on_quote(symbol, data)

        stream.on_bar = on_bar
        stream.on_quote = on_quote

    def _observe_transport_generation(self, stream) -> None:
        generation = getattr(stream, "connection_generation", None)
        if isinstance(generation, int) and generation != self._transport_generation:
            self._transport_generation = generation
            self._last_bar_ts.clear()
            self.last_update_time = None

    async def _retry_start(self) -> bool:
        if not self._recovery_enabled or not self._start_config:
            return False
        if time.monotonic() < self._recovery_due_at:
            return False
        config = dict(self._start_config)
        symbols = sorted(self._desired_symbols)
        try:
            # Retry runs inside the engine's shorter subscription-sync bound.
            # Restore confirmations promptly; the ordinary feeder supplies REST
            # history while this live buffer warms up. Preserve the client for
            # an explicit future start without manufacturing live provenance.
            return await self.start(symbols, **config, _prefill_history=False)
        except Exception:
            logger.exception("Streaming startup retry failed; entries remain blocked")
            return False

    @property
    def is_running(self) -> bool:
        return bool(self._running and self._stream and self._stream.is_authenticated)

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
        desired = self._desired_symbols if self._recovery_enabled else set()
        return set(self._last_bar_ts) | self._subscribed_symbols | desired

    def _bar_receipt_age(self, symbol: str, now: float) -> float:
        if self._recovery_enabled:
            stream = self._stream
            if stream is None or not stream.is_authenticated:
                return float("inf")
            generation = getattr(stream, "connection_generation", None)
            if isinstance(generation, int) and generation != self._transport_generation:
                return float("inf")
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

    async def update_subscriptions(self, symbols: list[str], protected: int = 0) -> bool:
        """Synchronize requested bar/quote subscriptions; True means complete.

        ``protected``: the first N symbols (benchmarks, held positions) are
        requested on their own, before the rest, and are never skipped as
        previously refused, so a refusal of lower-priority names cannot take
        them down with it.

        A successful transport update is not bar freshness. New symbols remain
        stale until an advancing, timely streaming bar arrives. No REST seed
        is performed here. Partial failures retain state for the next retry.
        """
        ordered = self._bounded(symbols)
        if self._recovery_enabled:
            self._desired_symbols = set(ordered)
            if not self._running or not self._stream or not self._stream.is_authenticated:
                if self._transport_reconnecting():
                    # The transport's own bounded reconnect owns recovery; a
                    # provider restart here would kill it and wipe buffers.
                    return False
                if not await self._retry_start():
                    return False
        async with self._lifecycle_lock:
            return await self._update_subscriptions(ordered, protected)

    @staticmethod
    def _bounded(symbols: list[str]) -> list[str]:
        """Priority-ordered, de-duplicated, capped at MAX_STREAM_SYMBOLS."""
        ordered = list(dict.fromkeys(str(s).upper() for s in symbols))
        if len(ordered) > MAX_STREAM_SYMBOLS:
            logger.warning(
                "Streaming desired set %d exceeds provider cap %d; truncating by priority",
                len(ordered), MAX_STREAM_SYMBOLS,
            )
            ordered = ordered[:MAX_STREAM_SYMBOLS]
        return ordered

    def _transport_reconnecting(self) -> bool:
        stream = self._stream
        return bool(stream is not None and getattr(stream, "reconnecting", False))

    def confirmed_symbols(self) -> set[str]:
        """Symbols the current connection has confirmed for bars AND quotes."""
        stream = self._stream
        if stream is None or not stream.is_authenticated:
            return set()
        bars: set[str] = set()
        for names in stream.bar_subscriptions.values():
            bars.update(names)
        return bars & set(stream.quote_subscriptions)

    async def _update_subscriptions(self, symbols: list[str], protected: int = 0) -> bool:
        if not self._stream or not self._stream.is_authenticated:
            logger.warning("Cannot update subscriptions — not connected")
            return False
        stream, generation = self._stream, self._session_generation
        self._observe_transport_generation(stream)

        ordered = self._bounded(symbols)
        new_set = set(ordered)
        current_quotes = set(self._stream.quote_subscriptions)
        current_bars = set()
        for tf_set in self._stream.bar_subscriptions.values():
            current_bars.update(tf_set)
        # Names the transport still wants (e.g. refused) must be retired too,
        # otherwise a reconnect replays them and can exceed the provider cap.
        transport_desired = set(getattr(self._stream, "desired_symbols", set()) or set())

        current_set = current_quotes | current_bars | self._subscribed_symbols
        self._subscribed_symbols.update(current_quotes | current_bars)

        to_remove = sorted((current_set | transport_desired) - new_set)
        complete = True

        # Audit 2026-09-29 (MDP-10): retire first so additions fit under the
        # cap, and never let a failed addition skip the retirement.
        if to_remove:
            removed = await stream.unsubscribe(to_remove)
            if not self._is_current_session(stream, generation):
                return False
            if removed is True:
                self._subscribed_symbols.difference_update(to_remove)
                self._retired_symbols.update(to_remove)
                forget = getattr(stream, "forget_refusals", None)
                if callable(forget):
                    forget()  # capacity freed: refused names may be retried
                for symbol in to_remove:
                    self._bars.pop(symbol, None)
                    self._quotes.pop(symbol, None)
                    self._last_bar_ts.pop(symbol, None)
                self.last_update_time = max(self._last_bar_ts.values(), default=None)
                logger.info("Streaming unsubscribed: -%d symbols", len(to_remove))
            else:
                logger.warning("Streaming unsubscribe failed: %d symbols retained", len(to_remove))
                complete = False

        # Names refused (symbol limit) on this connection are not re-sent: a
        # refusal rejects the whole request, which would take new names with it.
        first = set(ordered[:max(0, protected)])
        refused = set(getattr(stream, "refused_names", ()) or ()) - first
        if refused & new_set:
            complete = False
        bars_to_add = [s for s in ordered if s not in current_bars and s not in refused]
        quotes_to_add = [s for s in ordered if s not in current_quotes and s not in refused]
        # Protected names go in their own first request (a 405 refuses a whole
        # request), then everything else.
        for bars, quotes in (
            ([s for s in bars_to_add if s in first], [s for s in quotes_to_add if s in first]),
            ([s for s in bars_to_add if s not in first], [s for s in quotes_to_add if s not in first]),
        ):
            if bars:
                added = await stream.subscribe_bars(bars)
                if not self._is_current_session(stream, generation):
                    return False
                if added is not True:
                    logger.warning("Streaming bar subscription failed: %d symbols", len(bars))
                    complete = False
                else:
                    self._subscribed_symbols.update(bars)
                    self._retired_symbols.difference_update(bars)
            if quotes:
                added = await stream.subscribe_quotes(quotes)
                if not self._is_current_session(stream, generation):
                    return False
                if added is not True:
                    logger.warning("Streaming quote subscription failed: %d symbols", len(quotes))
                    complete = False
        if complete and (bars_to_add or quotes_to_add):
            logger.info("Streaming subscribed: +%d symbols", len(set(bars_to_add) | set(quotes_to_add)))

        return complete

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
                # REST supports warmup history, never current-session stream
                # provenance. Only advancing live callbacks establish receipts.
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
        if self._recovery_enabled and (
            not self._running or not self._stream or not self._stream.is_authenticated
        ):
            if self._transport_reconnecting():
                return False
            return await self._retry_start()
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
        ages = {symbol: self._bar_receipt_age(symbol, now) for symbol in self._freshness_symbols()}
        max_staleness = max(ages.values(), default=0.0)
        confirmed_bars = set()
        confirmed_quotes = set()
        if self._stream:
            for names in self._stream.bar_subscriptions.values():
                confirmed_bars.update(names)
            confirmed_quotes.update(self._stream.quote_subscriptions)
        complete = (self.is_running and self._desired_symbols <= confirmed_bars
                    and self._desired_symbols <= confirmed_quotes
                    and (confirmed_bars | confirmed_quotes | self._subscribed_symbols)
                    == self._desired_symbols)
        return {
            "running": self.is_running,
            "recovery_enabled": self._recovery_enabled,
            "desired_symbols": len(self._desired_symbols),
            "startup_retry_pending": self._recovery_enabled and not self.is_running,
            "symbols_with_bars": len(self._bars),
            "symbols_with_quotes": len(self._quotes),
            "total_bars": sum(len(b) for b in self._bars.values()),
            "max_staleness_s": round(max_staleness, 1) if math.isfinite(max_staleness) else None,
            "subscriptions_complete": complete,
            "unseen_or_unconfirmed_symbols": sorted(s for s, age in ages.items() if not math.isfinite(age)),
            "stream_stats": self._stream.get_stats() if self._stream else None,
        }
