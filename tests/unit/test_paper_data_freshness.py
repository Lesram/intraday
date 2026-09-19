"""Network-free reproduction of truncated intraday history and stale prefill."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fastapi import HTTPException
import httpx
import pandas as pd
import pytest

from backend.integrations.alpaca_data import AlpacaDataClient
from backend.organism.streaming_data_provider import StreamingDataProvider

NOW = datetime(2026, 9, 18, 19, 59, 40, tzinfo=timezone.utc)


def bar(timestamp, value=100):
    return {"t": timestamp.isoformat(), "o": value, "h": value + 1,
            "l": value - 1, "c": value, "v": 1000}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "test-key")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz)
    monkeypatch.setattr("backend.integrations.alpaca_data.datetime", Clock)
    # Avoid even constructing a real connection pool; requests are injected.
    monkeypatch.setattr("backend.integrations.alpaca_data.httpx.AsyncClient", lambda **kw: AsyncMock())
    return AlpacaDataClient()


def reply(rows, token=None):
    return httpx.Response(200, json={"bars": rows, "next_page_token": token})


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get_historical_closes", "get_historical_bars_df"])
async def test_latest_500_from_large_current_session_window(client, method):
    # More than one old 1000-row page: ascending first-page truncation used
    # to end far before this session. The fake provider obeys real query sort.
    all_bars = [bar(NOW - timedelta(minutes=2000-i), i) for i in range(2000)]
    calls = []
    async def request(*args, params, **kwargs):
        calls.append(params)
        selected = [row for row in all_bars
                    if datetime.fromisoformat(row["t"]) <= datetime.fromisoformat(params["end"])]
        selected.sort(key=lambda row: row["t"], reverse=params["sort"] == "desc")
        return reply(selected[:params["limit"]], "older-page")
    client._request_with_retry = request
    result = await getattr(client, method)("aapl", lookback=500, timeframe="1Min")
    values = result["close"].tolist() if method.endswith("df") else result
    assert values == list(range(1500, 2000))
    assert len(calls) == 1
    assert datetime.fromisoformat(calls[0]["end"]) == NOW
    assert datetime.fromisoformat(calls[0]["start"]) == NOW - timedelta(days=5)
    assert calls[0]["feed"] == "iex"
    assert calls[0]["adjustment"] == "split"
    if method.endswith("df"):
        assert pd.to_datetime(result.timestamp, utc=True).is_monotonic_increasing
        assert pd.Timestamp(result.iloc[-1].timestamp) == pd.Timestamp(NOW - timedelta(minutes=1))


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get_historical_closes", "get_historical_bars_df"])
async def test_short_pages_follow_tokens_deduplicate_and_order(client, method):
    rows = [bar(NOW - timedelta(minutes=i), 10-i) for i in range(1, 7)]
    client._request_with_retry = AsyncMock(side_effect=[
        reply(rows[:2], "two"), reply(rows[1:4], "three"), reply(rows[4:]),
    ])
    result = await getattr(client, method)("AAPL", 5, "1Min")
    values = result.close.tolist() if method.endswith("df") else result
    assert values == [5, 6, 7, 8, 9]
    calls = client._request_with_retry.call_args_list
    assert len(calls) == 3
    assert "page_token" not in calls[0].kwargs["params"]
    assert calls[1].kwargs["params"]["page_token"] == "two"
    assert calls[2].kwargs["params"]["page_token"] == "three"
    assert len({call.kwargs["params"]["end"] for call in calls}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("timestamp", [None, "invalid", "2026-09-18", "2026-09-18T19:59:00", "2026-09-18T20:00:00Z"])
async def test_bad_or_future_historical_timestamp_fails_closed(client, timestamp):
    row = bar(NOW - timedelta(minutes=1)); row["t"] = timestamp
    client._request_with_retry = AsyncMock(return_value=reply([row]))
    with pytest.raises(HTTPException) as exc:
        await client.get_historical_bars_df("AAPL", 5, "1Min")
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_repeated_page_token_is_bounded_failure(client):
    client._request_with_retry = AsyncMock(return_value=reply([], "same"))
    with pytest.raises(HTTPException, match="repeated historical page token"):
        await client.get_historical_closes("AAPL", 500, "1Min")
    assert client._request_with_retry.await_count == 2


@pytest.mark.asyncio
async def test_unique_infinite_tokens_are_bounded_failure(client):
    client._request_with_retry = AsyncMock(side_effect=[reply([], str(i)) for i in range(100)])
    with pytest.raises(HTTPException, match="pagination exceeded"):
        await client.get_historical_closes("AAPL", 500, "1Min")
    assert client._request_with_retry.await_count == 100


@pytest.mark.asyncio
async def test_page_error_does_not_return_incomplete_success(client):
    client._request_with_retry = AsyncMock(side_effect=[
        reply([bar(NOW-timedelta(minutes=1))], "next"), httpx.Response(500, json={"message": "down"}),
    ])
    with pytest.raises(HTTPException):
        await client.get_historical_bars_df("AAPL", 500, "1Min")


def frame(timestamps):
    return pd.DataFrame([{"timestamp": t, "open": 100, "high": 101,
                          "low": 99, "close": i, "volume": 1000}
                         for i, t in enumerate(timestamps)])


@pytest.mark.asyncio
async def test_stale_prefill_uses_event_age_and_forces_rest_fallback():
    provider = StreamingDataProvider(time_fn=lambda: NOW.timestamp())
    latest = NOW - timedelta(days=2)
    data = AsyncMock()
    data.get_historical_bars_df.return_value = frame([latest-timedelta(minutes=1), latest])
    await provider._prefill(["AAPL"], data)
    assert provider.bar_count("AAPL") == 2
    assert provider.get_bar_age("AAPL") == 2*86400
    assert provider.last_update_time == latest.timestamp()
    assert provider.get_bars("AAPL").empty
    assert provider.stale_symbols(120) == [("AAPL", 2*86400)]


@pytest.mark.asyncio
async def test_unsorted_prefill_is_chronological_and_uses_newest_not_last_row():
    provider = StreamingDataProvider(buffer_size=2, time_fn=lambda: NOW.timestamp())
    data = AsyncMock()
    data.get_historical_bars_df.return_value = frame([
        NOW-timedelta(seconds=30), NOW-timedelta(seconds=150), NOW-timedelta(seconds=90),
    ])
    await provider._prefill(["AAPL"], data)
    assert provider.get_bar_age("AAPL") == 30
    assert provider.get_bars("AAPL").close.tolist() == [2, 0]


@pytest.mark.asyncio
@pytest.mark.parametrize("timestamp", [None, "invalid", "2026-09-18", "2026-09-18T19:59:00", NOW+timedelta(seconds=1)])
async def test_invalid_or_future_prefill_does_not_publish_freshness(timestamp):
    provider = StreamingDataProvider(time_fn=lambda: NOW.timestamp())
    data = AsyncMock(); data.get_historical_bars_df.return_value = frame([timestamp])
    await provider._prefill(["AAPL"], data)
    assert not provider.has_data("AAPL")
    assert provider.last_update_time is None
    assert provider.get_bar_age("AAPL") == float("inf")


@pytest.mark.asyncio
async def test_prefill_preserves_stream_bar_received_during_request():
    provider = StreamingDataProvider(time_fn=lambda: NOW.timestamp())
    streamed = {"timestamp": (NOW-timedelta(seconds=40)).isoformat(), "close": 777}
    async def fetch(*args, **kwargs):
        await provider._on_bar("AAPL", streamed)
        return frame([NOW-timedelta(minutes=2), NOW-timedelta(seconds=40)])
    data = AsyncMock(); data.get_historical_bars_df.side_effect = fetch
    await provider._prefill(["AAPL"], data)
    assert provider.bar_count("AAPL") == 2
    assert provider.get_bars("AAPL").iloc[-1].close == 777
    assert provider.get_bar_age("AAPL") == 0  # existing receipt gate unchanged
    assert provider.last_update_time == NOW.timestamp()


@pytest.mark.asyncio
async def test_stale_second_symbol_does_not_lower_global_event_time():
    provider = StreamingDataProvider(time_fn=lambda: NOW.timestamp())
    data = AsyncMock(); data.get_historical_bars_df.side_effect = [
        frame([NOW-timedelta(seconds=30)]), frame([NOW-timedelta(days=2)]),
    ]
    await provider._prefill(["AAPL", "MSFT"], data)
    assert provider.last_update_time == NOW.timestamp()-30
    assert not provider.get_bars("AAPL").empty
    assert provider.get_bars("MSFT").empty
