"""
High-Performance Real-Time Quote Manager

Provides ultra-fast access to market quotes with:
- Batch fetching (up to 100 symbols at once)
- Redis caching (5-second TTL)
- Connection pooling
- Request deduplication
- Sub-100ms latency target

Usage:
    quote_manager = QuoteManager()
    quotes = await quote_manager.get_quotes(['AAPL', 'MSFT', 'GOOGL'])
"""

import asyncio
from datetime import datetime
import logging
import os
import time

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from alpaca.common.exceptions import APIError
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest

logger = logging.getLogger(__name__)


class Quote:
    """Market quote data structure"""
    def __init__(self, symbol: str, bid: float, ask: float, last: float,
                 timestamp: datetime, volume: int = 0):
        self.symbol = symbol
        self.bid = bid
        self.ask = ask
        self.last = last
        self.mid = (bid + ask) / 2 if bid and ask else last
        self.timestamp = timestamp
        self.volume = volume

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'bid': self.bid,
            'ask': self.ask,
            'last': self.last,
            'mid': self.mid,
            'timestamp': self.timestamp.isoformat(),
            'volume': self.volume
        }

    def is_stale(self, max_age_seconds: int = 5) -> bool:
        """Check if quote is older than max_age_seconds"""
        age = (datetime.now() - self.timestamp).total_seconds()
        return age > max_age_seconds


class QuoteManager:
    """
    High-performance quote manager with caching and batch fetching

    Performance targets:
    - Cache hit: <2ms
    - Cache miss: <100ms (including API call)
    - Batch 100 symbols: <150ms
    """

    def __init__(self):
        """Initialize Quote Manager"""
        self.alpaca_client = StockHistoricalDataClient(
            api_key=os.getenv('ALPACA_API_KEY_ID'),
            secret_key=os.getenv('ALPACA_API_SECRET_KEY')
        )

        # Redis cache
        self.redis_client = None
        if REDIS_AVAILABLE:
            try:
                redis_url = os.getenv('REDIS_URL')
                if redis_url:
                    self.redis_client = redis.from_url(
                        redis_url,
                        decode_responses=True,
                        socket_timeout=1,
                        socket_connect_timeout=1,
                        max_connections=50,
                    )
                else:
                    self.redis_client = redis.Redis(
                        host=os.getenv('REDIS_HOST', 'localhost'),
                        port=int(os.getenv('REDIS_PORT', 6379)),
                        db=int(os.getenv('REDIS_DB', 0)),
                        password=os.getenv('REDIS_PASSWORD'),
                        decode_responses=True,
                        socket_timeout=1,
                        socket_connect_timeout=1,
                        max_connections=50,
                    )
                logger.info("Redis cache initialized")
            except Exception as e:
                logger.warning(f"Redis initialization failed: {e}. Running without cache.")
                self.redis_client = None

        # In-memory cache (fallback if Redis unavailable)
        self.memory_cache: dict[str, Quote] = {}
        self.cache_ttl = 5  # 5 seconds

        # Batch processing
        self.pending_requests: dict[str, list[asyncio.Future]] = {}
        self.batch_window = 0.05  # 50ms aggregation window
        self.max_batch_size = 100  # Alpaca limit

        # Performance tracking
        self.metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'api_calls': 0,
            'latencies': []
        }

        logger.info("QuoteManager initialized successfully")

    async def get_quote(self, symbol: str) -> Quote | None:
        """
        Get quote for single symbol

        Args:
            symbol: Stock symbol (e.g., 'AAPL')

        Returns:
            Quote object or None if unavailable
        """
        quotes = await self.get_quotes([symbol])
        return quotes.get(symbol)

    async def get_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """
        Get quotes for multiple symbols (optimized batch fetching)

        Args:
            symbols: List of stock symbols

        Returns:
            Dictionary {symbol: Quote}
        """
        start_time = time.time()

        # Normalize symbols
        symbols = [s.upper() for s in symbols]

        # Check cache first
        cached_quotes, missing_symbols = await self._get_from_cache(symbols)

        if cached_quotes:
            self.metrics['cache_hits'] += len(cached_quotes)

        # Fetch missing symbols
        if missing_symbols:
            self.metrics['cache_misses'] += len(missing_symbols)
            fresh_quotes = await self._fetch_quotes(missing_symbols)

            # Update cache asynchronously (don't wait)
            if fresh_quotes:
                asyncio.create_task(self._update_cache(fresh_quotes))
                cached_quotes.update(fresh_quotes)

        # Track latency
        latency_ms = (time.time() - start_time) * 1000
        self.metrics['latencies'].append(latency_ms)

        return cached_quotes

    async def _get_from_cache(self, symbols: list[str]) -> tuple[dict[str, Quote], list[str]]:
        """
        Get quotes from cache

        Returns:
            (cached_quotes, missing_symbols)
        """
        cached = {}
        missing = []

        if self.redis_client:
            # Try Redis first
            try:
                pipeline = self.redis_client.pipeline()
                for symbol in symbols:
                    pipeline.get(f"quote:{symbol}")

                results = await pipeline.execute()

                for symbol, data in zip(symbols, results, strict=False):
                    if data:
                        quote = self._deserialize_quote(data, symbol)
                        if quote and not quote.is_stale(self.cache_ttl):
                            cached[symbol] = quote
                        else:
                            missing.append(symbol)
                    else:
                        missing.append(symbol)

            except Exception as e:
                logger.warning(f"Redis cache read failed: {e}")
                missing = symbols  # Fallback to fetching all
        else:
            # Use memory cache
            for symbol in symbols:
                quote = self.memory_cache.get(symbol)
                if quote and not quote.is_stale(self.cache_ttl):
                    cached[symbol] = quote
                else:
                    missing.append(symbol)

        return cached, missing

    async def _fetch_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """
        Fetch quotes from Alpaca API (batch optimized)

        Args:
            symbols: List of symbols to fetch

        Returns:
            Dictionary {symbol: Quote}
        """
        if not symbols:
            return {}

        quotes = {}

        # Alpaca supports up to 100 symbols per request
        for i in range(0, len(symbols), self.max_batch_size):
            batch = symbols[i:i + self.max_batch_size]

            try:
                # Fetch from Alpaca
                request = StockLatestQuoteRequest(symbol_or_symbols=batch)
                response = self.alpaca_client.get_stock_latest_quote(request)

                self.metrics['api_calls'] += 1

                # Parse response
                for symbol in batch:
                    if symbol in response:
                        alpaca_quote = response[symbol]

                        # Extract data
                        bid_price = float(alpaca_quote.bid_price) if alpaca_quote.bid_price else 0.0
                        ask_price = float(alpaca_quote.ask_price) if alpaca_quote.ask_price else 0.0

                        # Use last trade price if bid/ask not available
                        if not bid_price or not ask_price:
                            # Fallback: get latest trade
                            try:
                                trades = self.alpaca_client.get_stock_latest_trade(
                                    StockLatestQuoteRequest(symbol_or_symbols=symbol)
                                )
                                if symbol in trades:
                                    last_price = float(trades[symbol].price)
                                    bid_price = ask_price = last_price
                            except Exception as e:
                                logger.warning("Fallback trade quote fetch failed for %s: %s", symbol, e)

                        # Create Quote object
                        quote = Quote(
                            symbol=symbol,
                            bid=bid_price,
                            ask=ask_price,
                            last=bid_price if bid_price else ask_price,  # Use bid as last if available
                            timestamp=alpaca_quote.timestamp,
                            volume=int(alpaca_quote.ask_size + alpaca_quote.bid_size) if alpaca_quote.ask_size and alpaca_quote.bid_size else 0
                        )

                        quotes[symbol] = quote

            except APIError as e:
                logger.error(f"Alpaca API error fetching quotes: {e}")
            except Exception as e:
                logger.error(f"Error fetching quotes for {batch}: {e}")

        return quotes

    async def _update_cache(self, quotes: dict[str, Quote]):
        """Update cache with fresh quotes"""
        if self.redis_client:
            try:
                pipeline = self.redis_client.pipeline()
                for symbol, quote in quotes.items():
                    serialized = self._serialize_quote(quote)
                    pipeline.setex(f"quote:{symbol}", self.cache_ttl, serialized)
                await pipeline.execute()
            except Exception as e:
                logger.warning(f"Redis cache update failed: {e}")

        # Always update memory cache
        for symbol, quote in quotes.items():
            self.memory_cache[symbol] = quote

    def _serialize_quote(self, quote: Quote) -> str:
        """Serialize quote for Redis storage"""
        return f"{quote.bid}|{quote.ask}|{quote.last}|{quote.timestamp.isoformat()}|{quote.volume}"

    def _deserialize_quote(self, data: str, symbol: str = 'UNKNOWN') -> Quote | None:
        """Deserialize quote from Redis"""
        try:
            parts = data.split('|')
            return Quote(
                symbol=symbol,
                bid=float(parts[0]),
                ask=float(parts[1]),
                last=float(parts[2]),
                timestamp=datetime.fromisoformat(parts[3]),
                volume=int(parts[4]) if len(parts) > 4 else 0
            )
        except Exception as e:
            logger.warning(f"Failed to deserialize quote: {e}")
            return None

    def get_metrics(self) -> dict:
        """Get performance metrics"""
        total_requests = self.metrics['cache_hits'] + self.metrics['cache_misses']

        return {
            'cache_hit_rate': self.metrics['cache_hits'] / total_requests if total_requests > 0 else 0,
            'api_calls': self.metrics['api_calls'],
            'avg_latency_ms': sum(self.metrics['latencies']) / len(self.metrics['latencies']) if self.metrics['latencies'] else 0,
            'p95_latency_ms': sorted(self.metrics['latencies'])[int(len(self.metrics['latencies']) * 0.95)] if self.metrics['latencies'] else 0,
            'total_requests': total_requests
        }

    async def close(self):
        """Cleanup resources"""
        if self.redis_client:
            await self.redis_client.close()


# Global instance
_quote_manager = None

def get_quote_manager() -> QuoteManager:
    """Get global QuoteManager instance"""
    global _quote_manager
    if _quote_manager is None:
        _quote_manager = QuoteManager()
    return _quote_manager
