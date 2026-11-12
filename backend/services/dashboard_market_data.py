"""Market data for dashboard (UI) routes, kept off the trading event loop.

Audit 2026-10-05 A6-01 / A8-01. The API runs as one uvicorn worker whose event
loop also runs the organism scheduler's tick, the outbox worker and the Alpaca
streams. alpaca-py's REST clients are synchronous (``requests``): called from
an ``async def`` handler they block that loop, and on HTTP 429/504 the SDK
sleeps 3 s per retry, up to three times, inside the call. Dashboard routes
therefore read market data only through this module:

* every SDK call runs on a small dedicated thread pool under an
  ``asyncio.wait_for`` timeout. This is the mechanism of ``asyncio.to_thread``
  (``run_in_executor`` with a copied context) on a separate pool, so dashboard
  calls never occupy the default-executor threads the engine uses for broker
  position reads, feature work and brain saves;
* the SDK client is built once per pool thread, never per request, with SDK
  retries disabled (a 429/504 raises at once instead of sleeping) and an HTTP
  timeout on every request;
* latest quotes come from ONE batched ``StockLatestQuoteRequest`` per refresh,
  behind a process-wide cache with a short TTL and a single in-flight fetch,
  so several open tabs and users share one request. A failed refresh is not
  retried for one TTL;
* if the data API refuses a batch (HTTP 400) and names some of its symbols,
  the request is retried once without them, and those symbols stay out of
  batches for ``REFUSED_SYMBOL_HOLD_S``, so one symbol the API does not accept
  cannot take every other price down with it.

Nothing here is read by the trading engine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
import contextvars
from dataclasses import dataclass
from datetime import datetime
import functools
import logging
import math
import os
import re
import threading
import time
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Bound for one SDK call as seen by the awaiting coroutine (queue wait included).
SDK_CALL_TIMEOUT_S = 8.0
# requests (connect, read) timeout injected into every HTTP request the SDK makes,
# so a pool thread is released even when the awaiting coroutine already gave up.
HTTP_TIMEOUT_S: tuple[float, float] = (3.05, 5.0)
# Small on purpose: dashboard market data is a convenience, not a feed.
POOL_WORKERS = 3
# Latest quotes are shared across requests, tabs and users for this long.
QUOTE_CACHE_TTL_S = 10.0
# Most symbols one batched latest-quote request carries.
MAX_BATCH_SYMBOLS = 100
# Symbols the data API refused stay out of batched requests this long, so a bad
# symbol costs one extra request per hold instead of one per refresh.
REFUSED_SYMBOL_HOLD_S = 600.0
# Cache entries kept before expired ones are dropped.
_CACHE_PRUNE_AT = 2048
# HTTP status of a request the data API refuses (for example an invalid symbol).
_REFUSED_REQUEST_STATUS = 400
# Whole words of an error body, compared with the requested symbols.
_ERROR_TOKEN = re.compile(r"[A-Za-z0-9./\-]+")


class MarketDataUnavailable(RuntimeError):
    """Dashboard market data cannot be read (no credentials or unsupported client)."""


_pool: ThreadPoolExecutor | None = None
_pool_guard = threading.Lock()
_thread_state = threading.local()


def _executor() -> ThreadPoolExecutor:
    global _pool
    with _pool_guard:
        if _pool is None:
            _pool = ThreadPoolExecutor(
                max_workers=POOL_WORKERS, thread_name_prefix="dashboard-marketdata"
            )
        return _pool


async def run_blocking(
    fn: Callable[..., T], /, *args: Any, timeout_s: float | None = None, **kwargs: Any
) -> T:
    """Run a blocking call on the dashboard pool, never on the event loop.

    Raises ``asyncio.TimeoutError`` after ``timeout_s`` (default
    ``SDK_CALL_TIMEOUT_S``). A call still queued at that point is cancelled;
    one already running finishes within the HTTP timeout on its pool thread.
    """
    loop = asyncio.get_running_loop()
    call = functools.partial(contextvars.copy_context().run, fn, *args, **kwargs)
    timeout = SDK_CALL_TIMEOUT_S if timeout_s is None else timeout_s
    return await asyncio.wait_for(loop.run_in_executor(_executor(), call), timeout)


class PerLoopLock:
    """An ``asyncio.Lock`` re-created per event loop (production runs one loop)."""

    def __init__(self) -> None:
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def __call__(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._lock is None or self._loop is not loop:
            self._lock, self._loop = asyncio.Lock(), loop
        return self._lock


def bound_rest_client(client: Any) -> Any:
    """Disable SDK retry sleeps and time out every HTTP request (alpaca-py 0.43).

    ``RESTClient._request`` retries 429/504 answers ``_retry`` times with
    ``time.sleep(_retry_wait)`` between attempts; with ``_retry = 0`` the first
    429/504 raises ``APIError``. The constructor's ``retry_attempts`` cannot
    express zero (it ignores values below 1), hence the attribute.
    """
    one_request = getattr(client, "_one_request", None)
    if not hasattr(client, "_retry") or not callable(one_request):
        raise MarketDataUnavailable("unsupported alpaca-py client: requests cannot be bounded")
    client._retry = 0

    def _bounded_one_request(method, url, opts, retry):
        if isinstance(opts, dict) and "timeout" not in opts:
            opts = {**opts, "timeout": HTTP_TIMEOUT_S}
        return one_request(method, url, opts, retry)

    client._one_request = _bounded_one_request
    return client


def _new_stock_data_client() -> Any:
    api_key = os.getenv("ALPACA_API_KEY_ID")
    secret_key = os.getenv("ALPACA_API_SECRET_KEY")
    if not api_key or not secret_key:
        raise MarketDataUnavailable("market data credentials are not configured")
    from alpaca.data.historical import StockHistoricalDataClient

    return bound_rest_client(StockHistoricalDataClient(api_key=api_key, secret_key=secret_key))


def stock_data_client() -> Any:
    """This pool thread's bounded ``StockHistoricalDataClient``, built once per thread.

    Only for code that ``run_blocking`` runs on the dashboard pool.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "dashboard market data client used on the event loop; call it through run_blocking()"
        )
    client = getattr(_thread_state, "stock_client", None)
    if client is None:
        client = _new_stock_data_client()
        _thread_state.stock_client = client
    return client


def _configured_feed() -> Any | None:
    """The deployment's ``ALPACA_DATA_FEED`` (read only), when it names a known feed."""
    value = (os.getenv("ALPACA_DATA_FEED") or "").strip().lower()
    if not value:
        return None
    try:
        from alpaca.data.enums import DataFeed

        return DataFeed(value)
    except ValueError:
        return None


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else None


@dataclass(frozen=True)
class LatestQuote:
    """One symbol's latest quote, as the exchange reported it."""

    symbol: str
    bid: float | None
    ask: float | None
    timestamp: str | None  # the quote's own exchange timestamp

    @property
    def price(self) -> float | None:
        """Midpoint of a two-sided quote; None when either side is missing."""
        if self.bid is None or self.ask is None:
            return None
        return round((self.bid + self.ask) / 2.0, 4)


@dataclass(frozen=True)
class QuoteBatch:
    quotes: dict[str, LatestQuote]  # symbols the API returned a quote for
    unavailable: frozenset[str]  # requested symbols that cannot be read right now
    refused: frozenset[str] = frozenset()  # requested symbols the data API refused


@dataclass(frozen=True)
class FetchedQuotes:
    """The outcome of one fetch: quotes, and the symbols the data API refused."""

    quotes: dict[str, LatestQuote]
    refused: frozenset[str] = frozenset()


def refused_symbols(error: BaseException, symbols: Sequence[str]) -> list[str]:
    """The requested symbols that an HTTP 400 refusal names in its error body.

    alpaca-py raises ``APIError`` with the response body as its text and the
    HTTP status in ``status_code``. Comparing whole words of the body with the
    requested symbols (case-sensitive) does not depend on the exact message.
    Any other error, or a refusal that names none of them, gives ``[]``.
    """
    if getattr(error, "status_code", None) != _REFUSED_REQUEST_STATUS:
        return []
    words = {word.strip(".-") for word in _ERROR_TOKEN.findall(str(error))}
    return [symbol for symbol in symbols if symbol in words]


def _latest_quote_request(symbols: Sequence[str]) -> Any:
    from alpaca.data.requests import StockLatestQuoteRequest

    fields: dict[str, Any] = {"symbol_or_symbols": list(symbols)}
    feed = _configured_feed()
    if feed is not None:
        fields["feed"] = feed
    return stock_data_client().get_stock_latest_quote(StockLatestQuoteRequest(**fields))


def fetch_latest_quotes_blocking(symbols: Sequence[str]) -> FetchedQuotes:
    """ONE batched latest-quote request for ``symbols`` (runs on the dashboard pool).

    If the data API refuses the request (HTTP 400) and names some of the
    requested symbols, it is retried once without them; a second refusal, or
    one that names none of them, is raised.
    """
    requested = list(symbols)
    refused: list[str] = []
    try:
        response = _latest_quote_request(requested)
    except Exception as exc:  # noqa: BLE001 - only a 400 that names requested symbols is retried
        refused = refused_symbols(exc, requested)
        if not refused:
            raise
        requested = [symbol for symbol in requested if symbol not in refused]
        logger.warning(
            "Data API refused %d symbol(s) in a latest-quote request (%s); "
            "retrying once without them",
            len(refused), ",".join(refused)[:200],
        )
        response = _latest_quote_request(requested) if requested else {}
    quotes: dict[str, LatestQuote] = {}
    for symbol in requested:
        quote = response.get(symbol) if isinstance(response, dict) else None
        if quote is None:
            continue
        quotes[symbol] = LatestQuote(
            symbol=symbol,
            bid=_positive(getattr(quote, "bid_price", None)),
            ask=_positive(getattr(quote, "ask_price", None)),
            timestamp=_iso(getattr(quote, "timestamp", None)),
        )
    return FetchedQuotes(quotes=quotes, refused=frozenset(refused))


class LatestQuoteCache:
    """Process-wide latest quotes: TTL cache, one in-flight batched fetch."""

    def __init__(
        self,
        ttl_s: float = QUOTE_CACHE_TTL_S,
        fetch: Callable[[Sequence[str]], FetchedQuotes] = fetch_latest_quotes_blocking,
        refused_hold_s: float = REFUSED_SYMBOL_HOLD_S,
    ) -> None:
        self._ttl = ttl_s
        self._fetch = fetch
        self._refused_hold = refused_hold_s
        self._entries: dict[str, tuple[float, LatestQuote | None]] = {}
        self._refused_until: dict[str, float] = {}
        self._retry_at = 0.0
        self._lock = PerLoopLock()
        self.fetches = 0  # batched requests issued (diagnostics and tests)

    def _fresh(self, symbol: str, now: float) -> bool:
        entry = self._entries.get(symbol)
        return entry is not None and now - entry[0] < self._ttl

    def _refused(self, symbol: str, now: float) -> bool:
        return self._refused_until.get(symbol, 0.0) > now

    async def get(self, symbols: Iterable[str]) -> QuoteBatch:
        ordered = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))
        now = time.monotonic()
        held_out = {s for s in ordered if self._refused(s, now)}
        candidates = [s for s in ordered if s not in held_out]
        wanted, overflow = candidates[:MAX_BATCH_SYMBOLS], candidates[MAX_BATCH_SYMBOLS:]
        if wanted and not all(self._fresh(s, now) for s in wanted):
            async with self._lock():
                now = time.monotonic()
                missing = [s for s in wanted if not self._fresh(s, now) and not self._refused(s, now)]
                if missing and now >= self._retry_at:
                    self.fetches += 1
                    try:
                        fetched = await run_blocking(self._fetch, missing)
                    except Exception as exc:  # noqa: BLE001 - timeouts, API errors (429), no credentials
                        self._retry_at = time.monotonic() + self._ttl
                        logger.warning(
                            "Dashboard latest-quote request failed (%s: %s); no quotes for "
                            "%d symbol(s) for the next %.0f s",
                            type(exc).__name__, str(exc)[:200], len(missing), self._ttl,
                        )
                    else:
                        stamp = time.monotonic()
                        for symbol in fetched.refused:
                            self._refused_until[symbol] = stamp + self._refused_hold
                        for symbol in missing:
                            if symbol not in fetched.refused:
                                self._entries[symbol] = (stamp, fetched.quotes.get(symbol))
                        self._prune(stamp)
        now = time.monotonic()
        quotes: dict[str, LatestQuote] = {}
        unavailable = set(overflow)
        refused = set(held_out)
        for symbol in wanted:
            entry = self._entries.get(symbol)
            if self._refused(symbol, now):
                refused.add(symbol)
            elif entry is None or now - entry[0] >= self._ttl:
                unavailable.add(symbol)
            elif entry[1] is not None:
                quotes[symbol] = entry[1]
        return QuoteBatch(
            quotes=quotes, unavailable=frozenset(unavailable), refused=frozenset(refused),
        )

    def _prune(self, now: float) -> None:
        if len(self._entries) > _CACHE_PRUNE_AT:
            for symbol in [s for s, (at, _) in self._entries.items() if now - at >= self._ttl]:
                del self._entries[symbol]
        if len(self._refused_until) > _CACHE_PRUNE_AT:
            for symbol in [s for s, until in self._refused_until.items() if until <= now]:
                del self._refused_until[symbol]


quote_cache = LatestQuoteCache()


async def get_latest_quotes(symbols: Iterable[str]) -> QuoteBatch:
    """Latest quotes for dashboard routes (shared cache; see the module docstring)."""
    return await quote_cache.get(symbols)
