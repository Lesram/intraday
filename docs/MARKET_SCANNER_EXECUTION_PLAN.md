# Market-Wide Scanner — Execution Plan

> **Goal:** Replace the fixed 9-symbol universe with a live market-scanning
> system that discovers high-tension stocks across the entire US equity
> market, feeds them to the organism's intelligence, and lets the AI decide
> what to trade.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Step 1 — Create `MarketScanner` Module](#2-step-1--create-marketscanner-module)
3. [Step 2 — Wire Scanner into Live Engine](#3-step-2--wire-scanner-into-live-engine)
4. [Step 3 — Connect `candidate_pool` to Universe Selector](#4-step-3--connect-candidate_pool-to-universe-selector)
5. [Step 4 — Expand Universe Selector Limits](#5-step-4--expand-universe-selector-limits)
6. [Step 5 — Update `.env` Configuration](#6-step-5--update-env-configuration)
7. [Step 6 — Update `_fetch_and_compute_features` for Dynamic Symbols](#7-step-6--update-_fetch_and_compute_features-for-dynamic-symbols)
8. [Step 7 — Add Quick-Score Pre-Filter (Snapshot-Based)](#8-step-7--add-quick-score-pre-filter-snapshot-based)
9. [Step 8 — Dual-Portfolio Mode (HFT + Swing)](#9-step-8--dual-portfolio-mode-hft--swing)
10. [Verification & Testing](#10-verification--testing)

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    MarketScanner (NEW)                        │
│                                                              │
│  Every N ticks (configurable, default=6 → every 60s):       │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────────────┐ │
│  │ Most-Actives │  │  Movers     │  │ Snapshot Pre-Filter  │ │
│  │ (top volume) │  │ (% change)  │  │ (tension scoring)    │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬───────────┘ │
│         └────────┬───────┘                     │             │
│                  ▼                             │             │
│         candidate_symbols (deduped)            │             │
│                  │                             │             │
│                  ▼                             │             │
│         Quick tension score (snapshot)◄────────┘             │
│                  │                                           │
│                  ▼                                           │
│         self._scanner_candidates (cached list)               │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   OrganismLiveEngine                          │
│                                                              │
│  _live_tick_inner():                                         │
│    Step 0 (NEW): Run scanner every N ticks                   │
│    Step 2: _fetch_and_compute_features()                     │
│            NOW INCLUDES scanner candidates in self._universe │
│    Step 7: Alpha + Breakout scanners score ALL symbols       │
│    Step 11: _retrain_and_evolve() passes candidate_pool      │
│                                                              │
│  DynamicUniverseSelector.rotate():                           │
│    NOW RECEIVES candidate_pool from scanner                  │
│    Can ADD new symbols / DROP underperformers                │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Step 1 — Create `MarketScanner` Module

### File: `backend/organism/market_scanner.py`

Create this new file with the following complete implementation:

```python
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
        # Response: {"most_actives": [{"symbol": "...", "volume": ..., "trade_count": ..., "price": ...}, ...]}
        actives = data.get("most_actives", [])
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
        # Response includes both "gainers" and "losers" arrays
        key = "gainers" if direction == "up" else "losers"
        movers = data.get(key, [])
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
        Returns dict keyed by symbol → snapshot data.
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
        """Score a stock's 'tension' — likelihood of an imminent breakout.

        Uses snapshot data (daily bar, minute bar, prev daily close) to
        compute a 0-1 tension score based on:
        - Intraday range compression (tight range = coiled spring)
        - Volume surge vs daily average
        - Distance from daily high/low (near breakout level)
        - Price acceleration (minute bar momentum)

        Higher score = more tension = more likely to break out.
        """
        try:
            daily = snapshot.get("dailyBar", {})
            minute = snapshot.get("minuteBar", {})
            prev_close = float(snapshot.get("prevDailyBar", {}).get("c", 0))

            d_high = float(daily.get("h", 0))
            d_low = float(daily.get("l", 0))
            d_close = float(daily.get("c", 0))
            d_open = float(daily.get("o", 0))
            d_volume = int(daily.get("v", 0))

            if d_high <= 0 or d_low <= 0 or d_close <= 0:
                return 0.0

            # 1. Range compression: how tight is today's range vs price?
            daily_range = (d_high - d_low) / d_close if d_close > 0 else 0
            # Tighter range → higher tension (inverted, capped)
            range_score = max(0, 1.0 - (daily_range / 0.05))  # 5% range → 0 score
            range_score = min(range_score, 1.0)

            # 2. Volume surge: is volume elevated vs recent avg?
            # (We don't have multi-day avg here, so use absolute threshold)
            vol_score = min(d_volume / 5_000_000, 1.0)  # 5M volume → 1.0

            # 3. Proximity to breakout level: how close to daily high?
            if d_high > d_low:
                proximity = (d_close - d_low) / (d_high - d_low)
            else:
                proximity = 0.5
            # Near high = bullish tension, near low = bearish tension
            breakout_score = max(proximity, 1.0 - proximity)

            # 4. Gap/momentum: opening gap + intraday trend
            gap = 0.0
            if prev_close > 0:
                gap = abs(d_open - prev_close) / prev_close
            gap_score = min(gap / 0.03, 1.0)  # 3% gap → 1.0

            # 5. Minute-bar momentum (acceleration)
            m_close = float(minute.get("c", 0))
            m_open = float(minute.get("o", 0))
            m_volume = int(minute.get("v", 0))
            accel_score = 0.0
            if m_close > 0 and m_open > 0:
                accel = abs(m_close - m_open) / m_open
                accel_score = min(accel / 0.005, 1.0)  # 0.5% in 1 min → 1.0

            # Weighted composite
            tension = (
                0.20 * range_score
                + 0.20 * vol_score
                + 0.25 * breakout_score
                + 0.15 * gap_score
                + 0.20 * accel_score
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
```

### Key Design Decisions:

- **3 concurrent API calls** per scan: most-actives + movers-up + movers-down
- **1-2 snapshot calls** for tension scoring (batched, max 1000/request)
- **Total API budget per scan:** ~4-5 requests (fits within 300/min rate limit)
- **Excludes leveraged ETFs/ETNs** — they create false signals
- **Tension score** is a 0-1 composite of range compression, volume surge, proximity to breakout level, gap, and minute momentum
- **Results cached** between scans so the engine has candidates available every tick

---

## 3. Step 2 — Wire Scanner into Live Engine

### File: `backend/organism/live_engine.py`

#### 2a. Add import (top of file, after existing organism imports ~line 55):

Find this block (around line 55-56):
```python
from backend.organism.universe_selector import DynamicUniverseSelector
from backend.organism.transfer_learning import TransferLearningEngine
```

Add after it:
```python
from backend.organism.market_scanner import MarketScanner, SCAN_INTERVAL_TICKS
```

#### 2b. Add scanner config env var (after `LONG_ONLY` definition, ~line 137):

Find:
```python
LONG_ONLY = _env_bool("ORGANISM_LONG_ONLY", True)
```

Add after it:
```python
SCANNER_ENABLED = _env_bool("SCANNER_ENABLED", True)
```

#### 2c. Initialize scanner in `__init__` (after `universe_selector` init, ~line 235):

Find this block (around line 233-236):
```python
        # ── Dynamic Universe Selector (Phase 4.1) ──────────────
        self.universe_selector = DynamicUniverseSelector(
            seed_symbols=list(self._universe),
        )
```

Add after it:
```python
        # ── Market Scanner (Phase 5) ───────────────────────────
        self.market_scanner: MarketScanner | None = (
            MarketScanner() if SCANNER_ENABLED else None
        )
        self._scanner_candidates: list[str] = []
```

#### 2d. Add scanner step in `_live_tick_inner` (BEFORE step 2 "FETCH LATEST DATA", ~line 438):

Find this block (around line 438-441):
```python
            # 2. FETCH LATEST DATA
            features_by_symbol = await self._fetch_and_compute_features()
```

Insert BEFORE it (so scanner runs before data fetch):
```python
            # 1.5 MARKET SCAN (Phase 5) — discover new stocks
            if (
                self.market_scanner is not None
                and self._tick_count % SCAN_INTERVAL_TICKS == 0
            ):
                try:
                    new_candidates = await self.market_scanner.scan()
                    if new_candidates:
                        self._scanner_candidates = new_candidates
                        # Temporarily add top scanner picks to universe for this tick
                        scanner_additions = [
                            s for s in new_candidates[:20]
                            if s not in self._universe
                        ]
                        if scanner_additions:
                            self._universe = list(self._universe) + scanner_additions
                            logger.info(
                                "Scanner injected %d symbols into universe (total: %d)",
                                len(scanner_additions),
                                len(self._universe),
                            )
                except Exception as e:
                    logger.warning("Market scan failed: %s", e)

```

**Important:** This adds up to 20 scanner-discovered symbols to `self._universe` BEFORE the data fetch, so `_fetch_and_compute_features()` will pull bars for them too. The universe selector will later decide which ones to keep permanently.

#### 2e. Clean up scanner in `shutdown` method:

Find the `shutdown` method (search for `async def shutdown`). Add scanner cleanup:

```python
        # Clean up market scanner
        if self.market_scanner is not None:
            await self.market_scanner.close()
```

---

## 4. Step 3 — Connect `candidate_pool` to Universe Selector

### File: `backend/organism/live_engine.py`

#### 3a. Fix the `_retrain_and_evolve` method (~line 1198):

Find this exact code block (around line 1198-1202):
```python
            new_universe = self.universe_selector.rotate(
                trades=recent_trades,
                open_positions=open_syms,
                generation=self.evolved_params.evolution_generation,
            )
```

Replace with:
```python
            new_universe = self.universe_selector.rotate(
                trades=recent_trades,
                candidate_pool=self._scanner_candidates or None,
                open_positions=open_syms,
                generation=self.evolved_params.evolution_generation,
            )
```

This is the **critical one-line fix** — the `candidate_pool` parameter was already
designed into `DynamicUniverseSelector.rotate()` but NEVER wired up. Now
scanner-discovered symbols flow into the universe rotation decision.

---

## 5. Step 4 — Expand Universe Selector Limits

### File: `backend/organism/universe_selector.py`

#### 4a. Make constants env-configurable (replace the constants block ~lines 29-35):

Find:
```python
# ── Configuration constants ──────────────────────────────────────
MIN_UNIVERSE = 10          # Safety floor — never go below this
MAX_UNIVERSE = 40          # Upper cap — avoid data overload
TOP_ADD = 5                # Max symbols to add per rotation
TOP_DROP = 3               # Max symbols to drop per rotation
MIN_OBSERVATIONS = 5       # Need at least N trades to judge fitness
FITNESS_DECAY = 0.95       # Per-rotation decay (pulls unseen symbols → 0.5)
DEFAULT_FITNESS = 0.50     # Starting fitness for brand-new symbols
```

Replace with:
```python
import os

# ── Configuration constants (env-overridable) ────────────────────
MIN_UNIVERSE = int(os.getenv("UNIVERSE_MIN_SIZE", "15"))
MAX_UNIVERSE = int(os.getenv("UNIVERSE_MAX_SIZE", "80"))
TOP_ADD = int(os.getenv("UNIVERSE_TOP_ADD", "10"))
TOP_DROP = int(os.getenv("UNIVERSE_TOP_DROP", "5"))
MIN_OBSERVATIONS = int(os.getenv("UNIVERSE_MIN_OBSERVATIONS", "3"))
FITNESS_DECAY = float(os.getenv("UNIVERSE_FITNESS_DECAY", "0.95"))
DEFAULT_FITNESS = 0.50     # Starting fitness for brand-new symbols
```

**Why these new defaults:**
- `MIN_UNIVERSE=15` — larger floor so scanner stocks get a fair trial
- `MAX_UNIVERSE=80` — 80 symbols is manageable at 1-min bars with SIP feed
- `TOP_ADD=10` — allow more stocks in per rotation (scanner feeds many)
- `TOP_DROP=5` — allow faster pruning of duds
- `MIN_OBSERVATIONS=3` — judge fitness faster (HFT generates trades fast)

---

## 6. Step 5 — Update `.env` Configuration

### File: `.env`

#### 5a. Replace the fixed universe with a broader seed list:

Find:
```
ORGANISM_LIVE_SYMBOLS=AAPL,MSFT,NVDA,TSLA,AMD,META,AMZN,SPY,QQQ
```

Replace with:
```
# Seed universe (scanner will discover more dynamically)
ORGANISM_LIVE_SYMBOLS=AAPL,MSFT,NVDA,TSLA,AMD,META,AMZN,GOOGL,SPY,QQQ,IWM,XLK,XLE,AVGO,CRM,COST,WMT,LLY,XOM,CAT,NFLX,ADBE,INTC,MU,COIN,SNOW,PLTR,UBER,ABNB,SQ
ORGANISM_MAX_POSITIONS=15
```

#### 5b. Add scanner configuration block:

Add these new lines after the organism config:
```
# ── Market Scanner (Phase 5) ───────────────────────────────────
SCANNER_ENABLED=true
SCANNER_INTERVAL_TICKS=6
SCANNER_TOP_ACTIVES=100
SCANNER_TOP_MOVERS=50
SCANNER_MIN_PRICE=5.0
SCANNER_MAX_PRICE=1500.0
SCANNER_MIN_VOLUME=500000
SCANNER_MAX_CANDIDATES=80
SCANNER_TENSION_THRESHOLD=0.3

# ── Universe Selector (expanded for scanning) ──────────────────
UNIVERSE_MIN_SIZE=15
UNIVERSE_MAX_SIZE=80
UNIVERSE_TOP_ADD=10
UNIVERSE_TOP_DROP=5
UNIVERSE_MIN_OBSERVATIONS=3
```

---

## 7. Step 6 — Update `_fetch_and_compute_features` for Dynamic Symbols

### File: `backend/organism/live_engine.py`

The `_fetch_and_compute_features` method (starting ~line 759) iterates over `self._universe`. No code changes needed here because Step 2d already adds scanner symbols to `self._universe` before the fetch. However, we need to handle the potential for a larger universe gracefully.

#### 6a. Add concurrency limiter to prevent API throttling (~line 759):

Find the start of `_fetch_and_compute_features` (around line 759-768):
```python
    async def _fetch_and_compute_features(
        self,
    ) -> dict[str, pd.DataFrame]:
        """Fetch latest bars and compute ML features for the universe.

        Uses VersionedFeatureStore when available (Phase 3.3),
        falling back to raw compute_ml_features otherwise.
        """
        features_by_symbol: dict[str, pd.DataFrame] = {}
        spy_df = None
```

Replace with:
```python
    async def _fetch_and_compute_features(
        self,
    ) -> dict[str, pd.DataFrame]:
        """Fetch latest bars and compute ML features for the universe.

        Uses VersionedFeatureStore when available (Phase 3.3),
        falling back to raw compute_ml_features otherwise.
        Phase 5: Handles larger dynamic universe with concurrency control.
        """
        features_by_symbol: dict[str, pd.DataFrame] = {}
        spy_df = None
        _concurrency = asyncio.Semaphore(10)  # Max 10 parallel bar fetches
```

Then wrap each symbol's fetch in the semaphore. Find the loop (around line 774):
```python
        for sym in self._universe:
            try:
                if sym == "SPY" and spy_df is not None:
                    raw_df = spy_df
                else:
                    raw_df = await self._fetch_bars(sym)
```

Replace with a concurrent approach:
```python
        async def _fetch_one(sym: str) -> tuple[str, pd.DataFrame | None]:
            async with _concurrency:
                try:
                    if sym == "SPY" and spy_df is not None:
                        raw_df = spy_df
                    else:
                        raw_df = await self._fetch_bars(sym)

                    if raw_df is None or len(raw_df) < MIN_BARS:
                        return sym, None

                    # Phase 3.3: Use feature store when available
                    if self._feature_store is not None:
                        feats, _snapshot = self._feature_store.compute_features(
                            raw_df, symbol=sym,
                        )
                        feats_ml = compute_ml_features(
                            raw_df,
                            spy_df=spy_df if sym != "SPY" else None,
                        )
                        feats = feats.reset_index(drop=True)
                        feats_ml = feats_ml.reset_index(drop=True)
                        n_min = min(len(feats), len(feats_ml))
                        feats = feats.iloc[-n_min:].reset_index(drop=True)
                        feats_ml = feats_ml.iloc[-n_min:].reset_index(drop=True)
                        for col in feats.columns:
                            if col not in feats_ml.columns:
                                feats_ml[col] = feats[col].values
                        feats = feats_ml
                    else:
                        feats = compute_ml_features(
                            raw_df,
                            spy_df=spy_df if sym != "SPY" else None,
                        )
                        feats = feats.reset_index(drop=True)

                    # Preserve OHLCV columns
                    n_feats = len(feats)
                    for col in ["open", "high", "low", "close", "volume"]:
                        if col in raw_df.columns and col not in feats.columns:
                            feats[col] = raw_df[col].values[-n_feats:]

                    # Phase 4.2: Multi-timeframe features
                    feats = add_multi_timeframe_features(feats)

                    return sym, feats
                except Exception as e:
                    logger.warning("Failed to fetch/compute %s: %s", sym, e)
                    return sym, None

        # Fetch all symbols concurrently (semaphore-limited)
        tasks = [_fetch_one(sym) for sym in self._universe]
        results = await asyncio.gather(*tasks)
        for sym, feats in results:
            if feats is not None:
                features_by_symbol[sym] = feats
```

And remove the old `for sym in self._universe:` loop that was there before, along with the closing `return features_by_symbol` which stays.

**Why:** With 80+ symbols, sequential fetches would take 80 × 50ms = 4 seconds minimum. Concurrent with semaphore(10) brings it down to ~0.5s.

---

## 8. Step 7 — Add Quick-Score Pre-Filter (Snapshot-Based)

### File: `backend/organism/live_engine.py`

After the scanner runs (Step 2d), before building entry candidates (Step 7), add an optional boost for scanner-detected high-tension stocks.

#### 7a. In the candidate building section (~line 570-625), add tension score boost:

Find (around line 575):
```python
            cand_dicts = []
            for c in candidates:
                if c.symbol in open_symbols:
                    continue
                if LONG_ONLY and not self.evolved_params.shorts_enabled and c.direction < 0:
                    continue

                bs = breakout_by_sym.get(c.symbol)
                breakout_score = bs.composite_score if bs else 0.0
                confidence = (
                    (c.ml_signal.confidence if c.ml_signal else 0.5)
                    * (1.0 + breakout_score)
                )
```

Replace with:
```python
            # Build tension lookup from scanner
            _tension_lookup: dict[str, float] = {}
            if self.market_scanner is not None:
                for ss in self.market_scanner.scanned_stocks:
                    _tension_lookup[ss.symbol] = ss.tension_score

            cand_dicts = []
            for c in candidates:
                if c.symbol in open_symbols:
                    continue
                if LONG_ONLY and not self.evolved_params.shorts_enabled and c.direction < 0:
                    continue

                bs = breakout_by_sym.get(c.symbol)
                breakout_score = bs.composite_score if bs else 0.0
                tension = _tension_lookup.get(c.symbol, 0.0)
                confidence = (
                    (c.ml_signal.confidence if c.ml_signal else 0.5)
                    * (1.0 + breakout_score)
                    * (1.0 + tension * 0.5)  # Phase 5: scanner tension boost
                )
```

This gives scanner-discovered stocks a confidence boost proportional to their tension score (up to +50% for tension=1.0).

---

## 9. Step 8 — Dual-Portfolio Mode (HFT + Swing)

> This is a **future enhancement** — implement AFTER the core scanner is working.
> Documenting the design here for later execution.

### Concept

Split positions into two logical portfolios:
- **HFT Portfolio**: 1-min bars, 10s ticks, tight stops, <2h hold
- **Swing Portfolio**: 15-min/1-day bars, 5-min ticks, wider stops, multi-day hold

### Implementation Sketch

1. Create `backend/organism/dual_portfolio.py` with:
   - `PortfolioSlot` dataclass: `name`, `timeframe`, `tick_interval`, `max_positions`, `exit_params`
   - `DualPortfolioManager`: manages two `OrganismLiveEngine` instances
   - Shared `MarketScanner` feeds both portfolios
   - HFT portfolio gets scanner "hot" stocks (high tension, high volume)
   - Swing portfolio gets scanner "building" stocks (volume building, range compressing)

2. Route scanner results:
   - `tension_score > 0.6` AND `minute_momentum > 0.005` → HFT
   - `tension_score > 0.3` AND `range_compression > 0.7` → Swing
   - Both can hold the same symbol in different timeframes

3. Separate position limits: `ORGANISM_MAX_POSITIONS_HFT=10`, `ORGANISM_MAX_POSITIONS_SWING=8`

**Not implementing now** — the single-engine scanner is the priority.

---

## 10. Verification & Testing

### 10a. Unit Test: `tests/test_market_scanner.py`

Create a test file that:
1. Mocks Alpaca screener API responses (httpx mock)
2. Tests `_fetch_most_actives()` parsing
3. Tests `_fetch_movers()` parsing
4. Tests `_score_tension()` with known snapshot data
5. Tests `scan()` end-to-end with mocked endpoints
6. Tests exclusion list filtering
7. Tests price/volume filters

### 10b. Integration Verification

After implementation, restart the backend and verify:

```powershell
# 1. Check scanner is running (look for scan log messages)
Get-Content logs/app.log -Tail 50 | Select-String "Scanner|scanner|market_scan"

# 2. Verify universe grows beyond seed
Get-Content logs/app.log -Tail 200 | Select-String "Universe rotated|Scanner injected"

# 3. Check for API errors
Get-Content logs/app.log -Tail 200 | Select-String "Scanner API error|Scanner transient"

# 4. Monitor tick timing (should stay under 60s even with more symbols)
Get-Content logs/app.log -Tail 50 | Select-String "tick_duration"
```

### 10c. Smoke Test Sequence

1. Start backend: `python main.py`
2. Wait 60 seconds (6 ticks at 10s interval)
3. First market scan should fire and log:
   - `"Scanner: N most-actives passed filters"`
   - `"Scanner: N movers_up passed filters"`
   - `"Market scan #1 complete: N candidates"`
4. Next tick should log:
   - `"Scanner injected X symbols into universe"`
5. After 3 minutes (retrain interval):
   - `"Universe rotated: N → M symbols"` with `candidate_pool` fed

### 10d. Rollback Plan

If scanner causes issues, set in `.env`:
```
SCANNER_ENABLED=false
```
The engine will skip scanner initialization and run with the fixed seed universe (existing behavior).

---

## Summary of Files to Create/Modify

| File | Action | Key Change |
|------|--------|------------|
| `backend/organism/market_scanner.py` | **CREATE** | New module: Alpaca screener + tension scoring |
| `backend/organism/live_engine.py` | **MODIFY** | Import scanner, init in `__init__`, run in tick, pass `candidate_pool`, concurrent fetches, tension boost |
| `backend/organism/universe_selector.py` | **MODIFY** | Env-configurable constants, larger defaults |
| `.env` | **MODIFY** | Broader seed, scanner config, universe limits |
| `tests/test_market_scanner.py` | **CREATE** | Unit tests for scanner |

### Execution Order

1. Create `market_scanner.py` (standalone, no dependencies on other changes)
2. Modify `universe_selector.py` (env-configurable constants)
3. Modify `live_engine.py` (import scanner, init, wire into tick, fix candidate_pool, concurrent fetches, tension boost)
4. Modify `.env` (add scanner config, expand seed, expand universe limits)
5. Create unit tests
6. Restart backend and verify

### Rate Limit Budget

Current: 300 requests/min (Algo Trader Plus)

Per tick (10s → 6 ticks/min):
- Bar fetches: ~80 symbols × 6 ticks = 480/min ← **OVER BUDGET**
- Fix: With concurrent semaphore(10), stagger fetches with 50ms delay = 80 × 0.05 = 4s per tick, but request count is still 80/tick × 6/min = 480

**Solution:** Only fetch bars for active universe (≤40), use snapshots for scanner candidates:
- Tick 1-5: Fetch bars for `self._universe` (~30-40 symbols) = ~240 requests/min
- Tick 6 (scan tick): Scanner = 5 requests + normal bars = ~45 total

To stay safe, the scanner should **limit the injected symbols to 20** (already done in Step 2d) and the total active universe should stay ≤50. The `MAX_UNIVERSE=80` is for the candidate_pool, not the active universe. Adjust `MAX_UNIVERSE` env var down if rate limits hit.

**Rate limit safety valve:** If 429 errors appear, auto-reduce universe:
- This is handled by the existing `_DATA_CLIENT_MAX_RETRIES` with backoff
- Universe selector already caps at `MAX_UNIVERSE`
- Scanner injection limited to 20 symbols
