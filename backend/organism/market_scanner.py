"""
Phase 5 — Market-Wide Scanner.

Scans the ENTIRE US equity market for high-tension stocks using
Alpaca's screener and snapshot endpoints. Feeds discovered candidates
to DynamicUniverseSelector so the organism can trade any stock.

Alpaca Endpoints Used:
- GET /v1beta1/screener/stocks/most-actives  (top volume)
- GET /v1beta1/screener/stocks/movers        (biggest % movers)
- GET /v2/stocks/snapshots                   (batch price data)

Rate-budget: ~3-5 requests per scan cycle (runs every 60s).
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.utils.logger import get_logger

logger = get_logger(__name__)

# ── Configuration (env-overridable) ──────────────────────────────
SCAN_INTERVAL_TICKS = int(os.getenv("SCANNER_INTERVAL_TICKS", "6"))
SCAN_TOP_ACTIVES = int(os.getenv("SCANNER_TOP_ACTIVES", "100"))
SCAN_TOP_MOVERS = int(os.getenv("SCANNER_TOP_MOVERS", "50"))
SCAN_MIN_PRICE = float(os.getenv("SCANNER_MIN_PRICE", "5.0"))
SCAN_MAX_PRICE = float(os.getenv("SCANNER_MAX_PRICE", "1500.0"))
SCAN_MIN_VOLUME = int(os.getenv("SCANNER_MIN_VOLUME", "500000"))
SCAN_MIN_MARKET_CAP = float(os.getenv("SCANNER_MIN_MARKET_CAP", "1e9"))  # $1B
SCAN_MAX_CANDIDATES = int(os.getenv("SCANNER_MAX_CANDIDATES", "80"))
SCAN_TENSION_THRESHOLD = float(os.getenv("SCANNER_TENSION_THRESHOLD", "0.3"))

# Alpaca API base URLs
_DATA_BASE = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets/v2")
_SCREENER_BASE = "https://data.alpaca.markets/v1beta1/screener/stocks"

# Retry config — matches alpaca_data.py HFT settings
_MAX_RETRIES = 2
_RETRY_BACKOFF = 0.2
_RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass
class ScannedStock:
    """A stock discovered by the market scanner."""
    symbol: str
    source: str               # "most_actives", "movers_up", "movers_down", "snapshot"
    price: float = 0.0
    volume: int = 0
    change_pct: float = 0.0   # % change today
    tension_score: float = 0.0  # 0-1 composite score
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "source": self.source,
            "price": round(self.price, 2),
            "volume": self.volume,
            "change_pct": round(self.change_pct, 4),
            "tension_score": round(self.tension_score, 4),
        }


class MarketScanner:
    """Scans the US equity market for trading candidates.

    Uses Alpaca screener endpoints to find:
    - Most actively traded stocks (by volume)
    - Biggest movers up and down (by % change)
    Then scores each with a quick "tension" metric from snapshots.

    Usage::

        scanner = MarketScanner()
        candidates = await scanner.scan()  # Returns list of symbol strings
        # Feed to universe selector:
        universe_selector.rotate(trades, candidate_pool=candidates, ...)
    """

    def __init__(self) -> None:
        # Auth from env (same vars as AlpacaDataClient)
        self._api_key = (
            os.getenv("ALPACA_API_KEY_ID")
            or os.getenv("ALPACA_API_KEY")
            or os.getenv("APCA_API_KEY_ID")
            or ""
        )
        self._api_secret = (
            os.getenv("ALPACA_API_SECRET_KEY")
            or os.getenv("ALPACA_SECRET_KEY")
            or os.getenv("APCA_API_SECRET_KEY")
            or ""
        )

        self._client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )

        # Cache of latest scan results
        self._last_scan_time: float = 0.0
        self._cached_candidates: list[str] = []
        self._cached_scanned: list[ScannedStock] = []
        self._scan_count: int = 0

        # Permanent exclusion list (ETNs, leveraged, etc.)
        self._exclude = {
            "UVXY", "SVXY", "VIXY", "VXX", "TVIX",
            "SQQQ", "TQQQ", "SPXS", "SPXL", "UPRO",
            "SDOW", "UDOW", "SDS", "SSO", "QID", "QLD",
            "TZA", "TNA", "LABU", "LABD", "JNUG", "JDST",
            "NUGT", "DUST", "FNGU", "FNGD", "SOXL", "SOXS",
        }

    def _auth_headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
            "Accept": "application/json",
        }

    async def _request(
        self,
        url: str,
        params: dict | None = None,
    ) -> dict | list | None:
        """HTTP GET with retry (matches AlpacaDataClient retry pattern)."""
        headers = self._auth_headers()
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.get(
                    url, params=params, headers=headers,
                )
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in _RETRIABLE_STATUS_CODES:
                    logger.warning(
                        "Scanner API %d on attempt %d: %s",
                        resp.status_code, attempt + 1, url,
                    )
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(_RETRY_BACKOFF * (2 ** attempt))
                    continue
                # Non-retriable error
                logger.error(
                    "Scanner API error %d: %s → %s",
                    resp.status_code, url, resp.text[:200],
                )
                return None
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                last_exc = exc
                logger.warning("Scanner transient error: %s", exc)
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_BACKOFF * (2 ** attempt))

        if last_exc:
            logger.error("Scanner request failed after retries: %s", last_exc)
        return None

    # ── Alpaca Screener Endpoints ────────────────────────────────

    async def _fetch_most_actives(self) -> list[ScannedStock]:
        """GET /v1beta1/screener/stocks/most-actives

        Returns top stocks by trading volume today.
        """
        url = f"{_SCREENER_BASE}/most-actives"
        params = {"by": "volume", "top": SCAN_TOP_ACTIVES}
        data = await self._request(url, params)
        if not data:
            return []

        results = []
        actives = data.get("most_actives", []) if isinstance(data, dict) else []
        for item in actives:
            sym = item.get("symbol", "")
            if not sym or sym in self._exclude:
                continue
            price = float(item.get("price", 0))
            volume = int(item.get("volume", 0))
            if price < SCAN_MIN_PRICE or price > SCAN_MAX_PRICE:
                continue
            if volume < SCAN_MIN_VOLUME:
                continue
            results.append(ScannedStock(
                symbol=sym,
                source="most_actives",
                price=price,
                volume=volume,
                change_pct=float(item.get("change", 0)),
                timestamp=time.time(),
            ))

        logger.info("Scanner: %d most-actives passed filters", len(results))
        return results

    async def _fetch_movers(self, direction: str = "up") -> list[ScannedStock]:
        """GET /v1beta1/screener/stocks/movers

        Returns biggest % gainers or losers.
        direction: 'up' or 'down'
        """
        url = f"{_SCREENER_BASE}/movers"
        params = {"top": SCAN_TOP_MOVERS}
        data = await self._request(url, params)
        if not data:
            return []

        results = []
        key = "gainers" if direction == "up" else "losers"
        movers = data.get(key, []) if isinstance(data, dict) else []
        for item in movers:
            sym = item.get("symbol", "")
            if not sym or sym in self._exclude:
                continue
            price = float(item.get("price", 0))
            volume = int(item.get("volume", 0))
            change_pct = float(item.get("change_percent", item.get("percent_change", 0)))
            if price < SCAN_MIN_PRICE or price > SCAN_MAX_PRICE:
                continue
            results.append(ScannedStock(
                symbol=sym,
                source=f"movers_{direction}",
                price=price,
                volume=volume,
                change_pct=change_pct,
                timestamp=time.time(),
            ))

        logger.info("Scanner: %d movers_%s passed filters", len(results), direction)
        return results

    async def _fetch_snapshots(
        self, symbols: list[str],
    ) -> dict[str, dict]:
        """GET /v2/stocks/snapshots

        Batch-fetch latest snapshot for multiple symbols.
        Returns dict keyed by symbol -> snapshot data.
        Max 1000 symbols per call (Alpaca limit).
        """
        if not symbols:
            return {}

        all_snapshots: dict[str, dict] = {}
        # Chunk into batches of 1000 (Alpaca limit)
        for i in range(0, len(symbols), 1000):
            batch = symbols[i:i + 1000]
            url = f"{_DATA_BASE}/stocks/snapshots"
            params = {
                "symbols": ",".join(batch),
                "feed": os.getenv("ALPACA_DATA_FEED", "sip"),
            }
            data = await self._request(url, params)
            if data and isinstance(data, dict):
                all_snapshots.update(data)

        return all_snapshots

    # ── Tension Scoring ──────────────────────────────────────────

    def _score_tension(
        self, snapshot: dict,
    ) -> float:
        """Score a stock's 'tension' -- likelihood of an imminent breakout.

        Enhanced scoring with 7 dimensions:
        1. Range compression (coiled spring)
        2. Volume surge (institutional participation)
        3. Proximity to breakout level
        4. Gap / opening momentum
        5. Minute-bar acceleration
        6. Body-to-range ratio (conviction of direction)
        7. Previous day context (multi-bar tension)

        Higher score = more tension = more likely to break out.
        """
        try:
            daily = snapshot.get("dailyBar", {})
            minute = snapshot.get("minuteBar", {})
            prev_bar = snapshot.get("prevDailyBar", {})
            prev_close = float(prev_bar.get("c", 0))
            prev_high = float(prev_bar.get("h", 0))
            prev_low = float(prev_bar.get("l", 0))
            prev_vol = int(prev_bar.get("v", 1))

            d_high = float(daily.get("h", 0))
            d_low = float(daily.get("l", 0))
            d_close = float(daily.get("c", 0))
            d_open = float(daily.get("o", 0))
            d_volume = int(daily.get("v", 0))

            if d_high <= 0 or d_low <= 0 or d_close <= 0:
                return 0.0

            # 1. Range compression: tight range = coiled spring
            daily_range = (d_high - d_low) / d_close
            range_score = max(0, 1.0 - (daily_range / 0.05))
            range_score = min(range_score, 1.0)

            # 2. Volume surge: elevated vs previous day
            vol_ratio = d_volume / max(prev_vol, 1)
            vol_score = min(max(vol_ratio - 1.0, 0) / 3.0, 1.0)
            # Also factor absolute volume
            abs_vol_score = min(d_volume / 5_000_000, 1.0)
            vol_score = vol_score * 0.6 + abs_vol_score * 0.4

            # 3. Proximity to breakout level
            if d_high > d_low:
                proximity = (d_close - d_low) / (d_high - d_low)
            else:
                proximity = 0.5
            breakout_score = max(proximity, 1.0 - proximity)

            # 4. Gap/momentum
            gap = abs(d_open - prev_close) / prev_close if prev_close > 0 else 0
            gap_score = min(gap / 0.03, 1.0)

            # 5. Minute-bar acceleration
            m_close = float(minute.get("c", 0))
            m_open = float(minute.get("o", 0))
            m_volume = int(minute.get("v", 0))
            accel_score = 0.0
            if m_close > 0 and m_open > 0:
                accel = abs(m_close - m_open) / m_open
                accel_score = min(accel / 0.005, 1.0)

            # 6. Body-to-range ratio: strong directional conviction
            body = abs(d_close - d_open)
            total_range = d_high - d_low
            body_ratio = body / total_range if total_range > 0 else 0
            body_score = min(body_ratio / 0.7, 1.0)  # 70%+ body = strong bar

            # 7. Multi-bar context: narrowing range over 2 bars
            prev_range = (prev_high - prev_low) / prev_close if prev_close > 0 else 0.05
            range_narrowing = max(0, 1.0 - daily_range / max(prev_range, 1e-10))
            context_score = min(range_narrowing, 1.0)

            # Weighted composite (7 dimensions)
            tension = (
                0.18 * range_score
                + 0.18 * vol_score
                + 0.18 * breakout_score
                + 0.12 * gap_score
                + 0.12 * accel_score
                + 0.12 * body_score
                + 0.10 * context_score
            )
            return round(min(tension, 1.0), 4)

        except Exception as e:
            logger.debug("Tension score error: %s", e)
            return 0.0

    # ── Main Scan Method ─────────────────────────────────────────

    async def scan(self) -> list[str]:
        """Run full market scan and return candidate symbols.

        Pipeline:
        1. Fetch most-actives (top volume)
        2. Fetch movers (top gainers + losers)
        3. Deduplicate
        4. Fetch snapshots for all candidates
        5. Score tension
        6. Filter by tension threshold
        7. Return top SCAN_MAX_CANDIDATES symbols sorted by tension

        Returns list of symbol strings (suitable for candidate_pool).
        """
        self._scan_count += 1
        t0 = time.time()

        # 1-2. Fetch from screener endpoints (3 API calls, run concurrently)
        actives_task = self._fetch_most_actives()
        movers_up_task = self._fetch_movers("up")
        movers_down_task = self._fetch_movers("down")

        actives, movers_up, movers_down = await asyncio.gather(
            actives_task, movers_up_task, movers_down_task,
            return_exceptions=True,
        )

        # Collect results, handling exceptions
        all_scanned: dict[str, ScannedStock] = {}
        for batch in [actives, movers_up, movers_down]:
            if isinstance(batch, Exception):
                logger.warning("Scanner batch failed: %s", batch)
                continue
            for stock in batch:
                if stock.symbol not in all_scanned:
                    all_scanned[stock.symbol] = stock

        if not all_scanned:
            logger.warning("Scanner: no stocks passed initial filters")
            self._last_scan_time = time.time()
            return self._cached_candidates

        # 3. Get snapshot data for tension scoring (1-2 API calls)
        symbols = list(all_scanned.keys())
        snapshots = await self._fetch_snapshots(symbols)

        # 4. Score tension from snapshots
        scored: list[ScannedStock] = []
        for sym, stock in all_scanned.items():
            snap = snapshots.get(sym, {})
            if snap:
                stock.tension_score = self._score_tension(snap)
                # Update price from snapshot if available
                daily = snap.get("dailyBar", {})
                if daily.get("c"):
                    stock.price = float(daily["c"])
                    stock.volume = int(daily.get("v", stock.volume))
            scored.append(stock)

        # 5. Filter by tension threshold and sort
        scored = [s for s in scored if s.tension_score >= SCAN_TENSION_THRESHOLD]
        scored.sort(key=lambda s: s.tension_score, reverse=True)
        scored = scored[:SCAN_MAX_CANDIDATES]

        # 6. Cache results
        self._cached_scanned = scored
        self._cached_candidates = [s.symbol for s in scored]
        self._last_scan_time = time.time()

        elapsed = time.time() - t0
        logger.info(
            "Market scan #%d complete: %d candidates (%.1fs), "
            "top tension: %s=%.3f",
            self._scan_count,
            len(self._cached_candidates),
            elapsed,
            scored[0].symbol if scored else "N/A",
            scored[0].tension_score if scored else 0,
        )

        return self._cached_candidates

    # ── Properties ───────────────────────────────────────────────

    @property
    def candidates(self) -> list[str]:
        """Latest cached candidate symbols."""
        return list(self._cached_candidates)

    @property
    def scanned_stocks(self) -> list[ScannedStock]:
        """Latest cached scanned stock details."""
        return list(self._cached_scanned)

    @property
    def last_scan_time(self) -> float:
        """Timestamp of last scan."""
        return self._last_scan_time

    @property
    def scan_count(self) -> int:
        return self._scan_count

    async def close(self) -> None:
        """Clean up HTTP client."""
        await self._client.aclose()
