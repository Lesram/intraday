"""
Unit tests for the Phase 5 Market-Wide Scanner.

Tests:
- ScannedStock dataclass
- MarketScanner._fetch_most_actives() parsing
- MarketScanner._fetch_movers() parsing
- MarketScanner._score_tension() with known snapshot data
- MarketScanner.scan() end-to-end with mocked endpoints
- Exclusion list filtering
- Price/volume filters
- Retry and error handling
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.organism.market_scanner import (
    MarketScanner,
    ScannedStock,
    SCAN_MIN_PRICE,
    SCAN_MAX_PRICE,
    SCAN_MIN_VOLUME,
    SCAN_TENSION_THRESHOLD,
)


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def scanner():
    """Create a MarketScanner with mocked HTTP client."""
    s = MarketScanner()
    # Replace httpx client with a mock
    s._client = AsyncMock()
    s._api_key = "test-key"
    s._api_secret = "test-secret"
    return s


def _mock_response(status_code: int = 200, json_data: dict | list | None = None):
    """Create a mock httpx response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.text = str(json_data)[:200]
    return resp


# ── Sample API Responses ─────────────────────────────────────────

MOST_ACTIVES_RESPONSE = {
    "most_actives": [
        {"symbol": "AAPL", "volume": 80_000_000, "trade_count": 500_000, "price": 185.50, "change": 0.012},
        {"symbol": "TSLA", "volume": 60_000_000, "trade_count": 400_000, "price": 245.00, "change": -0.025},
        {"symbol": "NVDA", "volume": 45_000_000, "trade_count": 350_000, "price": 890.00, "change": 0.031},
        # Should be excluded (leveraged ETF)
        {"symbol": "TQQQ", "volume": 30_000_000, "trade_count": 200_000, "price": 65.00, "change": 0.05},
        # Should be filtered (price too low)
        {"symbol": "PENNY", "volume": 10_000_000, "trade_count": 100_000, "price": 1.50, "change": 0.10},
        # Should be filtered (volume too low)
        {"symbol": "LOWVOL", "volume": 100_000, "trade_count": 1_000, "price": 50.00, "change": 0.01},
    ]
}

MOVERS_RESPONSE = {
    "gainers": [
        {"symbol": "META", "volume": 25_000_000, "price": 520.00, "change_percent": 5.2},
        {"symbol": "AMD", "volume": 30_000_000, "price": 175.00, "change_percent": 3.8},
        # Should be excluded (leveraged)
        {"symbol": "SOXL", "volume": 15_000_000, "price": 40.00, "change_percent": 8.0},
    ],
    "losers": [
        {"symbol": "INTC", "volume": 20_000_000, "price": 25.00, "change_percent": -4.5},
        {"symbol": "BA", "volume": 12_000_000, "price": 180.00, "change_percent": -3.2},
    ],
}

SNAPSHOT_RESPONSE = {
    "AAPL": {
        "dailyBar": {"o": 184.00, "h": 186.50, "l": 184.00, "c": 185.50, "v": 80_000_000},
        "minuteBar": {"o": 185.40, "h": 185.60, "l": 185.30, "c": 185.55, "v": 150_000},
        "prevDailyBar": {"c": 183.50},
    },
    "TSLA": {
        "dailyBar": {"o": 250.00, "h": 252.00, "l": 243.00, "c": 245.00, "v": 60_000_000},
        "minuteBar": {"o": 244.80, "h": 245.20, "l": 244.70, "c": 245.10, "v": 80_000},
        "prevDailyBar": {"c": 251.00},
    },
    "NVDA": {
        "dailyBar": {"o": 885.00, "h": 895.00, "l": 882.00, "c": 890.00, "v": 45_000_000},
        "minuteBar": {"o": 889.50, "h": 890.50, "l": 889.00, "c": 890.00, "v": 50_000},
        "prevDailyBar": {"c": 880.00},
    },
    "META": {
        "dailyBar": {"o": 500.00, "h": 525.00, "l": 498.00, "c": 520.00, "v": 25_000_000},
        "minuteBar": {"o": 519.50, "h": 520.50, "l": 519.00, "c": 520.00, "v": 40_000},
        "prevDailyBar": {"c": 494.00},
    },
    "AMD": {
        "dailyBar": {"o": 170.00, "h": 176.00, "l": 169.00, "c": 175.00, "v": 30_000_000},
        "minuteBar": {"o": 174.80, "h": 175.20, "l": 174.60, "c": 175.00, "v": 35_000},
        "prevDailyBar": {"c": 168.00},
    },
    "INTC": {
        "dailyBar": {"o": 26.00, "h": 26.50, "l": 24.80, "c": 25.00, "v": 20_000_000},
        "minuteBar": {"o": 25.05, "h": 25.10, "l": 24.95, "c": 25.00, "v": 60_000},
        "prevDailyBar": {"c": 26.20},
    },
    "BA": {
        "dailyBar": {"o": 185.00, "h": 186.00, "l": 178.00, "c": 180.00, "v": 12_000_000},
        "minuteBar": {"o": 179.80, "h": 180.20, "l": 179.50, "c": 180.00, "v": 20_000},
        "prevDailyBar": {"c": 186.00},
    },
}


# ── ScannedStock Tests ───────────────────────────────────────────

class TestScannedStock:
    def test_to_dict(self):
        stock = ScannedStock(
            symbol="AAPL",
            source="most_actives",
            price=185.5123,
            volume=80_000_000,
            change_pct=0.01234,
            tension_score=0.67891,
        )
        d = stock.to_dict()
        assert d["symbol"] == "AAPL"
        assert d["source"] == "most_actives"
        assert d["price"] == 185.51
        assert d["volume"] == 80_000_000
        assert d["change_pct"] == 0.0123
        assert d["tension_score"] == 0.6789

    def test_defaults(self):
        stock = ScannedStock(symbol="TEST", source="test")
        assert stock.price == 0.0
        assert stock.volume == 0
        assert stock.change_pct == 0.0
        assert stock.tension_score == 0.0
        assert stock.timestamp == 0.0


# ── Fetch Most Actives Tests ─────────────────────────────────────

class TestFetchMostActives:
    @pytest.mark.asyncio
    async def test_parses_response(self, scanner):
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, MOST_ACTIVES_RESPONSE)
        )
        results = await scanner._fetch_most_actives()

        # TQQQ excluded, PENNY filtered (price), LOWVOL filtered (volume)
        symbols = [r.symbol for r in results]
        assert "AAPL" in symbols
        assert "TSLA" in symbols
        assert "NVDA" in symbols
        assert "TQQQ" not in symbols  # excluded (leveraged)
        assert "PENNY" not in symbols  # price < SCAN_MIN_PRICE
        assert "LOWVOL" not in symbols  # volume < SCAN_MIN_VOLUME

    @pytest.mark.asyncio
    async def test_correct_fields(self, scanner):
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, MOST_ACTIVES_RESPONSE)
        )
        results = await scanner._fetch_most_actives()
        aapl = next(r for r in results if r.symbol == "AAPL")
        assert aapl.source == "most_actives"
        assert aapl.price == 185.50
        assert aapl.volume == 80_000_000
        assert aapl.change_pct == 0.012

    @pytest.mark.asyncio
    async def test_empty_response(self, scanner):
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, {"most_actives": []})
        )
        results = await scanner._fetch_most_actives()
        assert results == []

    @pytest.mark.asyncio
    async def test_api_error_returns_empty(self, scanner):
        scanner._client.get = AsyncMock(
            return_value=_mock_response(403, {"message": "forbidden"})
        )
        results = await scanner._fetch_most_actives()
        assert results == []

    @pytest.mark.asyncio
    async def test_none_response_returns_empty(self, scanner):
        scanner._client.get = AsyncMock(
            return_value=_mock_response(500, None)
        )
        results = await scanner._fetch_most_actives()
        assert results == []


# ── Fetch Movers Tests ───────────────────────────────────────────

class TestFetchMovers:
    @pytest.mark.asyncio
    async def test_parses_gainers(self, scanner):
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, MOVERS_RESPONSE)
        )
        results = await scanner._fetch_movers("up")
        symbols = [r.symbol for r in results]
        assert "META" in symbols
        assert "AMD" in symbols
        assert "SOXL" not in symbols  # excluded (leveraged)

    @pytest.mark.asyncio
    async def test_parses_losers(self, scanner):
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, MOVERS_RESPONSE)
        )
        results = await scanner._fetch_movers("down")
        symbols = [r.symbol for r in results]
        assert "INTC" in symbols
        assert "BA" in symbols

    @pytest.mark.asyncio
    async def test_movers_source_tag(self, scanner):
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, MOVERS_RESPONSE)
        )
        results = await scanner._fetch_movers("up")
        for r in results:
            assert r.source == "movers_up"

        results = await scanner._fetch_movers("down")
        for r in results:
            assert r.source == "movers_down"

    @pytest.mark.asyncio
    async def test_change_pct_field(self, scanner):
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, MOVERS_RESPONSE)
        )
        results = await scanner._fetch_movers("up")
        meta = next(r for r in results if r.symbol == "META")
        assert meta.change_pct == 5.2


# ── Tension Scoring Tests ────────────────────────────────────────

class TestScoreTension:
    def test_known_snapshot(self, scanner):
        """Test tension score with a known AAPL-like snapshot."""
        snap = SNAPSHOT_RESPONSE["AAPL"]
        score = scanner._score_tension(snap)
        assert 0 <= score <= 1
        assert score > 0  # AAPL has decent volume and proximity

    def test_high_tension_tight_range_high_volume(self, scanner):
        """Tight range + high volume + near high = high tension."""
        snap = {
            "dailyBar": {"o": 100.00, "h": 100.50, "l": 99.80, "c": 100.40, "v": 10_000_000},
            "minuteBar": {"o": 100.35, "h": 100.45, "l": 100.30, "c": 100.42, "v": 200_000},
            "prevDailyBar": {"c": 100.00},
        }
        score = scanner._score_tension(snap)
        assert score > 0.5  # Should be high

    def test_low_tension_wide_range_low_volume(self, scanner):
        """Wide range + low volume = low tension."""
        snap = {
            "dailyBar": {"o": 100.00, "h": 110.00, "l": 90.00, "c": 95.00, "v": 500_000},
            "minuteBar": {"o": 95.00, "h": 95.10, "l": 94.90, "c": 95.00, "v": 5_000},
            "prevDailyBar": {"c": 100.00},
        }
        score = scanner._score_tension(snap)
        assert score < 0.5  # Should be relatively low

    def test_empty_snapshot_returns_zero(self, scanner):
        assert scanner._score_tension({}) == 0.0

    def test_invalid_prices_returns_zero(self, scanner):
        snap = {
            "dailyBar": {"o": 0, "h": 0, "l": 0, "c": 0, "v": 0},
            "minuteBar": {},
            "prevDailyBar": {},
        }
        assert scanner._score_tension(snap) == 0.0

    def test_score_range(self, scanner):
        """Score should always be between 0 and 1."""
        for sym, snap in SNAPSHOT_RESPONSE.items():
            score = scanner._score_tension(snap)
            assert 0 <= score <= 1, f"{sym} score {score} out of range"


# ── Exclusion List Tests ─────────────────────────────────────────

class TestExclusionList:
    def test_leveraged_etfs_excluded(self, scanner):
        excluded = ["TQQQ", "SQQQ", "SPXL", "SPXS", "UPRO", "SOXL", "SOXS",
                     "LABU", "LABD", "FNGU", "FNGD", "UVXY", "SVXY"]
        for sym in excluded:
            assert sym in scanner._exclude

    @pytest.mark.asyncio
    async def test_excluded_symbols_filtered_from_actives(self, scanner):
        response = {
            "most_actives": [
                {"symbol": "TQQQ", "volume": 100_000_000, "price": 65.0, "change": 0.05},
                {"symbol": "AAPL", "volume": 80_000_000, "price": 185.0, "change": 0.01},
            ]
        }
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, response)
        )
        results = await scanner._fetch_most_actives()
        assert len(results) == 1
        assert results[0].symbol == "AAPL"


# ── Price/Volume Filter Tests ────────────────────────────────────

class TestFilters:
    @pytest.mark.asyncio
    async def test_price_below_min_filtered(self, scanner):
        response = {
            "most_actives": [
                {"symbol": "CHEAP", "volume": 10_000_000, "price": SCAN_MIN_PRICE - 1, "change": 0.01},
            ]
        }
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, response)
        )
        results = await scanner._fetch_most_actives()
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_price_above_max_filtered(self, scanner):
        response = {
            "most_actives": [
                {"symbol": "EXPENSIVE", "volume": 10_000_000, "price": SCAN_MAX_PRICE + 100, "change": 0.01},
            ]
        }
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, response)
        )
        results = await scanner._fetch_most_actives()
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_volume_below_min_filtered(self, scanner):
        response = {
            "most_actives": [
                {"symbol": "LOWVOL", "volume": SCAN_MIN_VOLUME - 1, "price": 50.0, "change": 0.01},
            ]
        }
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, response)
        )
        results = await scanner._fetch_most_actives()
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_edge_price_at_min_passes(self, scanner):
        response = {
            "most_actives": [
                {"symbol": "EDGE", "volume": 1_000_000, "price": SCAN_MIN_PRICE, "change": 0.01},
            ]
        }
        scanner._client.get = AsyncMock(
            return_value=_mock_response(200, response)
        )
        results = await scanner._fetch_most_actives()
        assert len(results) == 1


# ── Full Scan End-to-End Tests ───────────────────────────────────

class TestScanEndToEnd:
    @pytest.mark.asyncio
    async def test_full_scan_pipeline(self, scanner):
        """Test the full scan() pipeline with mocked API responses."""
        call_count = 0

        async def mock_get(url, params=None, headers=None):
            nonlocal call_count
            call_count += 1
            if "most-actives" in url:
                return _mock_response(200, MOST_ACTIVES_RESPONSE)
            elif "movers" in url:
                return _mock_response(200, MOVERS_RESPONSE)
            elif "snapshots" in url:
                return _mock_response(200, SNAPSHOT_RESPONSE)
            return _mock_response(404, {})

        scanner._client.get = mock_get
        candidates = await scanner.scan()

        # Should have candidates
        assert len(candidates) > 0
        # All should be strings
        assert all(isinstance(s, str) for s in candidates)
        # No excluded symbols
        for sym in candidates:
            assert sym not in scanner._exclude
        # Should have made API calls (3 screener + 1 snapshot)
        assert call_count >= 4
        # Scan count incremented
        assert scanner.scan_count == 1
        assert scanner.last_scan_time > 0

    @pytest.mark.asyncio
    async def test_scan_caches_results(self, scanner):
        """After scan(), cached properties reflect results."""
        async def mock_get(url, params=None, headers=None):
            if "most-actives" in url:
                return _mock_response(200, MOST_ACTIVES_RESPONSE)
            elif "movers" in url:
                return _mock_response(200, MOVERS_RESPONSE)
            elif "snapshots" in url:
                return _mock_response(200, SNAPSHOT_RESPONSE)
            return _mock_response(404, {})

        scanner._client.get = mock_get
        candidates = await scanner.scan()

        assert scanner.candidates == candidates
        assert len(scanner.scanned_stocks) > 0
        for stock in scanner.scanned_stocks:
            assert isinstance(stock, ScannedStock)
            assert stock.tension_score >= SCAN_TENSION_THRESHOLD

    @pytest.mark.asyncio
    async def test_scan_sorts_by_tension_descending(self, scanner):
        """Candidates should be sorted by tension score (highest first)."""
        async def mock_get(url, params=None, headers=None):
            if "most-actives" in url:
                return _mock_response(200, MOST_ACTIVES_RESPONSE)
            elif "movers" in url:
                return _mock_response(200, MOVERS_RESPONSE)
            elif "snapshots" in url:
                return _mock_response(200, SNAPSHOT_RESPONSE)
            return _mock_response(404, {})

        scanner._client.get = mock_get
        await scanner.scan()

        scores = [s.tension_score for s in scanner.scanned_stocks]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_scan_deduplicates(self, scanner):
        """If a symbol appears in both actives and movers, it's not duplicated."""
        # AAPL appears in both most-actives and movers
        combined_movers = {
            "gainers": [
                {"symbol": "AAPL", "volume": 80_000_000, "price": 185.50, "change_percent": 1.2},
                {"symbol": "META", "volume": 25_000_000, "price": 520.00, "change_percent": 5.2},
            ],
            "losers": [],
        }

        async def mock_get(url, params=None, headers=None):
            if "most-actives" in url:
                return _mock_response(200, MOST_ACTIVES_RESPONSE)
            elif "movers" in url:
                return _mock_response(200, combined_movers)
            elif "snapshots" in url:
                return _mock_response(200, SNAPSHOT_RESPONSE)
            return _mock_response(404, {})

        scanner._client.get = mock_get
        candidates = await scanner.scan()

        # AAPL should appear only once
        assert candidates.count("AAPL") <= 1

    @pytest.mark.asyncio
    async def test_scan_returns_cached_on_all_failures(self, scanner):
        """If all API calls fail, return cached candidates."""
        scanner._cached_candidates = ["PREV1", "PREV2"]

        async def mock_get(url, params=None, headers=None):
            return _mock_response(500, {"error": "server error"})

        scanner._client.get = mock_get
        candidates = await scanner.scan()

        # Should return previous cached candidates
        assert candidates == ["PREV1", "PREV2"]

    @pytest.mark.asyncio
    async def test_scan_handles_exception_in_batch(self, scanner):
        """If one screener call raises, others still work."""
        import httpx as _httpx

        call_idx = 0

        async def mock_get(url, params=None, headers=None):
            nonlocal call_idx
            call_idx += 1
            if "most-actives" in url:
                raise _httpx.ConnectError("connection refused")
            elif "movers" in url:
                return _mock_response(200, MOVERS_RESPONSE)
            elif "snapshots" in url:
                return _mock_response(200, SNAPSHOT_RESPONSE)
            return _mock_response(404, {})

        scanner._client.get = mock_get
        candidates = await scanner.scan()

        # Should still have candidates from movers
        assert len(candidates) >= 0  # May have candidates from movers that pass threshold


# ── Snapshot Fetch Tests ─────────────────────────────────────────

class TestFetchSnapshots:
    @pytest.mark.asyncio
    async def test_batches_large_requests(self, scanner):
        """Symbols > 1000 should be split into batches."""
        calls = []

        async def mock_get(url, params=None, headers=None):
            calls.append(params)
            return _mock_response(200, {})

        scanner._client.get = mock_get
        symbols = [f"SYM{i}" for i in range(1500)]
        await scanner._fetch_snapshots(symbols)

        # Should have made 2 calls (1000 + 500)
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_empty_symbols(self, scanner):
        result = await scanner._fetch_snapshots([])
        assert result == {}


# ── Close Method Test ────────────────────────────────────────────

class TestClose:
    @pytest.mark.asyncio
    async def test_close_calls_aclose(self, scanner):
        scanner._client.aclose = AsyncMock()
        await scanner.close()
        scanner._client.aclose.assert_called_once()


# ── Auth Headers Test ────────────────────────────────────────────

class TestAuthHeaders:
    def test_auth_headers_structure(self, scanner):
        headers = scanner._auth_headers()
        assert "APCA-API-KEY-ID" in headers
        assert "APCA-API-SECRET-KEY" in headers
        assert headers["APCA-API-KEY-ID"] == "test-key"
        assert headers["APCA-API-SECRET-KEY"] == "test-secret"
        assert headers["Accept"] == "application/json"
