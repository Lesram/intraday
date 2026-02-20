"""Unit tests for StreamingDataProvider pre-fill logic."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from backend.organism.streaming_data_provider import StreamingDataProvider


# ── Helpers ────────────────────────────────────────────────────────

def _make_bars_df(n: int = 5) -> pd.DataFrame:
    """Return a small OHLCV DataFrame for testing."""
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="min"),
        "open": [100.0 + i for i in range(n)],
        "high": [101.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
        "close": [100.5 + i for i in range(n)],
        "volume": [1000 * (i + 1) for i in range(n)],
    })


_SENTINEL = object()

def _mock_data_client(bars_df: pd.DataFrame | None | object = _SENTINEL) -> MagicMock:
    """Create a mock data client with get_historical_bars_df."""
    client = MagicMock()
    client.get_historical_bars_df = AsyncMock(
        return_value=_make_bars_df() if bars_df is _SENTINEL else bars_df
    )
    return client


def _mock_stream():
    """Create a mock AlpacaMarketDataStream."""
    stream = MagicMock()
    stream.connect = AsyncMock(return_value=True)
    stream.subscribe_bars = AsyncMock()
    stream.subscribe_quotes = AsyncMock()
    stream.disconnect = AsyncMock()
    stream.is_authenticated = True
    return stream


# ── Tests ──────────────────────────────────────────────────────────

class TestPrefillSeedsRingBuffer:
    """Pre-fill should seed the ring buffer with historical bars."""

    @pytest.mark.asyncio
    async def test_prefill_populates_bars(self):
        provider = StreamingDataProvider(buffer_size=2000)
        df = _make_bars_df(10)
        client = _mock_data_client(df)

        with patch(
            "backend.organism.streaming_data_provider.AlpacaMarketDataStream",
            return_value=_mock_stream(),
        ):
            await provider.start(
                symbols=["AAPL", "MSFT"],
                api_key="k",
                api_secret="s",
                data_client=client,
            )

        assert provider.bar_count("AAPL") == 10
        assert provider.bar_count("MSFT") == 10
        assert provider.has_data("AAPL")

    @pytest.mark.asyncio
    async def test_prefill_calls_correct_params(self):
        provider = StreamingDataProvider()
        client = _mock_data_client(_make_bars_df(3))

        with patch(
            "backend.organism.streaming_data_provider.AlpacaMarketDataStream",
            return_value=_mock_stream(),
        ), patch.dict("os.environ", {
            "ORGANISM_LIVE_LOOKBACK": "100",
            "ORGANISM_LIVE_TIMEFRAME": "1Min",
        }):
            await provider.start(
                symbols=["SPY"],
                api_key="k",
                api_secret="s",
                data_client=client,
            )

        client.get_historical_bars_df.assert_called_with(
            "SPY", lookback=100, timeframe="1Min",
        )


class TestPrefillFailureDoesntCrash:
    """If pre-fill fails for a symbol, start() should still succeed."""

    @pytest.mark.asyncio
    async def test_exception_in_one_symbol_doesnt_block_others(self):
        provider = StreamingDataProvider()
        client = MagicMock()

        # AAPL raises, MSFT succeeds
        async def mock_fetch(symbol, **kw):
            if symbol == "AAPL":
                raise ConnectionError("timeout")
            return _make_bars_df(5)

        client.get_historical_bars_df = AsyncMock(side_effect=mock_fetch)

        with patch(
            "backend.organism.streaming_data_provider.AlpacaMarketDataStream",
            return_value=_mock_stream(),
        ):
            await provider.start(
                symbols=["AAPL", "MSFT"],
                api_key="k",
                api_secret="s",
                data_client=client,
            )

        assert provider.is_running
        assert provider.bar_count("AAPL") == 0
        assert provider.bar_count("MSFT") == 5

    @pytest.mark.asyncio
    async def test_empty_df_skipped(self):
        provider = StreamingDataProvider()
        client = _mock_data_client(pd.DataFrame())

        with patch(
            "backend.organism.streaming_data_provider.AlpacaMarketDataStream",
            return_value=_mock_stream(),
        ):
            await provider.start(
                symbols=["AAPL"],
                api_key="k",
                api_secret="s",
                data_client=client,
            )

        assert provider.is_running
        assert provider.bar_count("AAPL") == 0

    @pytest.mark.asyncio
    async def test_none_df_skipped(self):
        provider = StreamingDataProvider()
        client = _mock_data_client(None)

        with patch(
            "backend.organism.streaming_data_provider.AlpacaMarketDataStream",
            return_value=_mock_stream(),
        ):
            await provider.start(
                symbols=["AAPL"],
                api_key="k",
                api_secret="s",
                data_client=client,
            )

        assert provider.is_running
        assert provider.bar_count("AAPL") == 0


class TestGetBarsAfterPrefill:
    """get_bars() should return pre-filled data as a DataFrame."""

    @pytest.mark.asyncio
    async def test_get_bars_returns_prefilled_data(self):
        provider = StreamingDataProvider()
        df = _make_bars_df(20)
        client = _mock_data_client(df)

        with patch(
            "backend.organism.streaming_data_provider.AlpacaMarketDataStream",
            return_value=_mock_stream(),
        ):
            await provider.start(
                symbols=["AAPL"],
                api_key="k",
                api_secret="s",
                data_client=client,
            )

        result = provider.get_bars("AAPL", lookback=10)
        assert len(result) == 10
        assert list(result.columns) >= ["timestamp", "open", "high", "low", "close", "volume"]

    @pytest.mark.asyncio
    async def test_get_bars_lookback_larger_than_buffer(self):
        provider = StreamingDataProvider()
        df = _make_bars_df(5)
        client = _mock_data_client(df)

        with patch(
            "backend.organism.streaming_data_provider.AlpacaMarketDataStream",
            return_value=_mock_stream(),
        ):
            await provider.start(
                symbols=["AAPL"],
                api_key="k",
                api_secret="s",
                data_client=client,
            )

        result = provider.get_bars("AAPL", lookback=200)
        assert len(result) == 5


class TestStreamingBarsAppendAfterPrefill:
    """Streaming bars should append to pre-filled buffer."""

    @pytest.mark.asyncio
    async def test_new_bar_appends_to_prefilled(self):
        provider = StreamingDataProvider()
        df = _make_bars_df(3)
        client = _mock_data_client(df)

        with patch(
            "backend.organism.streaming_data_provider.AlpacaMarketDataStream",
            return_value=_mock_stream(),
        ):
            await provider.start(
                symbols=["AAPL"],
                api_key="k",
                api_secret="s",
                data_client=client,
            )

        assert provider.bar_count("AAPL") == 3

        # Simulate a streaming bar arriving
        await provider._on_bar("AAPL", {
            "timestamp": "2024-01-01T01:00:00Z",
            "open": 200.0,
            "high": 201.0,
            "low": 199.0,
            "close": 200.5,
            "volume": 5000,
        })

        assert provider.bar_count("AAPL") == 4
        result = provider.get_bars("AAPL", lookback=10)
        # Last bar should be the streaming one
        assert result.iloc[-1]["close"] == 200.5


class TestStartWithoutDataClient:
    """start() without data_client should work as before (no pre-fill)."""

    @pytest.mark.asyncio
    async def test_no_data_client_no_prefill(self):
        provider = StreamingDataProvider()

        with patch(
            "backend.organism.streaming_data_provider.AlpacaMarketDataStream",
            return_value=_mock_stream(),
        ):
            await provider.start(
                symbols=["AAPL"],
                api_key="k",
                api_secret="s",
            )

        assert provider.is_running
        assert provider.bar_count("AAPL") == 0
