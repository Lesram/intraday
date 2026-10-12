"""Audit 2026-10-05 A6-01, A8-01, A3-01.

A6-01: the dashboard Market Scanner is off unless DASHBOARD_SCANNER_ENABLED=true
(HTTP 503, websocket refused before accept); when enabled its SDK calls run off
the event loop with bounded concurrency and timeouts.
A8-01: watchlist quotes come from ONE batched latest-quote request on a pool
thread behind a shared TTL cache, with a symbol cap and the response shape the
Trading page reads; no AlpacaClient is built per request.
A3-01: the runtime execution-mode override never applies to the organism
engine's own orders, setting it is refused under the research lock, and manual
orders in shadow/dry_run end 'rejected' with zero fill and the event sent.

Offline: no network, no credentials (synthetic values only). The Alpaca SDK runs
for real down to its HTTP session (requests.Session.request answers like the
market-data API); the outbox worker, OrderService and the Alpaca outbox
dispatcher run for real against SQLite with ck_orders_status enforced by
triggers built from the migration's allowed set, and a fake broker client.
"""
from __future__ import annotations

import ast
import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

from fastapi import FastAPI
import httpx
import pytest
import pytest_asyncio
import requests
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from backend.api.routes import admin_trading, scanner, watchlists
from backend.infra.outbox_worker import OutboxWorker
from backend.infra.schemas import (
    AuditLog, Execution, Order, OutboxEvent, PositionLot, RealizedTrade, Watchlist, WatchlistSymbol,
)
from backend.organism import research_policy
from backend.services import dashboard_market_data
from backend.services import trading_execution_mode as tem
from backend.services.order_service import OrderService

REPO = Path(__file__).resolve().parents[1]
BROKER_ID = "0f6b8c1e-2d4a-4c5b-9e7f-8a9b0c1d2e3f"
QUOTE_TIME = "2026-10-12T14:30:00Z"


# ── Helpers ────────────────────────────────────────────────────────────────────
async def max_loop_lag_during(awaitable, interval: float = 0.01):
    """Await ``awaitable`` while a probe measures how late 10 ms timers fire."""
    lags: list[float] = []
    done = asyncio.Event()

    async def probe():
        loop = asyncio.get_running_loop()
        while not done.is_set():
            started = loop.time()
            await asyncio.sleep(interval)
            lags.append(loop.time() - started - interval)

    task = asyncio.create_task(probe())
    try:
        result = await awaitable
    finally:
        done.set()
        await task
    return result, max(lags, default=0.0)


class FakeResponse:
    def __init__(self, status: int, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)

    def json(self):
        return self._payload


class FakeMarketDataAPI:
    """Stands in for Alpaca's HTTP endpoints below the real SDK; records every call."""

    def __init__(self):
        self.calls: list[SimpleNamespace] = []
        self.delay = 0.0
        self.status = 200
        self.quotes: dict[str, tuple[float, float]] = {}
        self.bars_per_symbol = 60
        self._guard = threading.Lock()
        self._bars_in_flight = 0
        self.max_bars_in_flight = 0

    def request(self, method, url, **opts):
        path = url.split("/v2", 1)[-1]
        params = dict(opts.get("params") or {})
        bars = path == "/stocks/bars"
        with self._guard:
            self.calls.append(SimpleNamespace(
                method=method, path=path, params=params, timeout=opts.get("timeout"),
                thread=threading.current_thread().name))
            if bars:
                self._bars_in_flight += 1
                self.max_bars_in_flight = max(self.max_bars_in_flight, self._bars_in_flight)
        try:
            if self.delay:
                time.sleep(self.delay)  # a slow (blocking) HTTP round trip
            if self.status != 200:
                return FakeResponse(self.status, {"message": "synthetic error"})
            symbols = str(params.get("symbols", "")).split(",")
            if path == "/stocks/quotes/latest":
                return FakeResponse(200, {"quotes": {
                    s: {"t": QUOTE_TIME, "bp": self.quotes[s][0], "bs": 1,
                        "ap": self.quotes[s][1], "as": 1}
                    for s in symbols if s in self.quotes}})
            if bars:
                start = datetime(2026, 1, 2, 21, tzinfo=UTC)
                return FakeResponse(200, {"bars": {s: [
                    {"t": (start + timedelta(days=i)).isoformat().replace("+00:00", "Z"),
                     "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.0 + i / 10, "v": 1_000_000,
                     "n": 100, "vw": 100.0}
                    for i in range(self.bars_per_symbol)] for s in symbols}, "next_page_token": None})
            return FakeResponse(404, {"message": "unknown path"})
        finally:
            if bars:
                with self._guard:
                    self._bars_in_flight -= 1


@pytest.fixture
def fake_market_api(monkeypatch):
    api = FakeMarketDataAPI()
    monkeypatch.setattr(requests.Session, "request",
                        lambda _session, method, url, **opts: api.request(method, url, **opts))
    monkeypatch.setenv("ALPACA_API_KEY_ID", "synthetic-key-id")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "synthetic-secret")
    monkeypatch.setattr(dashboard_market_data, "quote_cache", dashboard_market_data.LatestQuoteCache())
    return api


def asgi_client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


# ── A6-01: dashboard Market Scanner ───────────────────────────────────────────
def scanner_app(*, authenticated: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(scanner.router, prefix="/api/v1")
    if authenticated:
        app.dependency_overrides[scanner.get_current_user] = (
            lambda: SimpleNamespace(username="operator", roles=["trader"]))
    return app


async def drive_websocket(app, path: str, query: str, messages=()):
    """Run one websocket connection through the ASGI app; return what it sent."""
    inbox: asyncio.Queue = asyncio.Queue()
    for message in ({"type": "websocket.connect"}, *messages,
                    {"type": "websocket.disconnect", "code": 1000}):
        inbox.put_nowait(message)
    sent: list[dict] = []
    scope = {
        "type": "websocket", "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1", "scheme": "ws", "path": path, "raw_path": path.encode(),
        "query_string": query.encode(), "root_path": "", "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 50000), "server": ("testserver", 80), "subprotocols": [],
    }

    async def receive():
        return await inbox.get()

    async def send(message):
        sent.append(message)

    await asyncio.wait_for(app(scope, receive, send), timeout=10)
    return sent


@pytest.mark.asyncio
async def test_scanner_http_routes_are_refused_by_default(fake_market_api, monkeypatch):
    monkeypatch.delenv("DASHBOARD_SCANNER_ENABLED", raising=False)
    # The engine's own scanner flag does not enable the dashboard scanner.
    monkeypatch.setenv("SCANNER_ENABLED", "true")
    async with asgi_client(scanner_app()) as http:
        for path in ("/api/v1/scanner/scan", "/api/v1/scanner/export/csv",
                     "/api/v1/scanner/export/json"):
            response = await http.post(path, json={"price_min": 10})
            assert response.status_code == 503, path
            assert "DASHBOARD_SCANNER_ENABLED=false" in response.json()["detail"]
        status = await http.get("/api/v1/scanner/status")
        assert status.status_code == 200
        assert status.json()["enabled"] is False
    async with asgi_client(scanner_app(authenticated=False)) as http:
        assert (await http.post("/api/v1/scanner/scan", json={})).status_code == 401
    assert fake_market_api.calls == []  # no market-data request at all


@pytest.mark.asyncio
async def test_scanner_websocket_is_refused_before_accept_by_default(monkeypatch):
    from backend.infra import security

    monkeypatch.delenv("DASHBOARD_SCANNER_ENABLED", raising=False)
    monkeypatch.setattr(security, "decode_token", lambda _token: {"sub": "operator", "roles": ["trader"]})
    sent = await drive_websocket(scanner_app(), "/api/v1/scanner/ws", "token=synthetic-token")
    # Closing before accept rejects the handshake: no connected -> disconnected
    # cycle, so the page's Live mode does not reconnect in a loop.
    assert [message["type"] for message in sent] == ["websocket.close"]
    assert sent[0]["code"] == scanner.SCANNER_DISABLED_WS_CODE
    assert scanner.scanner_manager.active_connections == {}


@pytest.mark.asyncio
async def test_scanner_websocket_is_accepted_when_enabled(monkeypatch):
    from backend.infra import security

    monkeypatch.setenv("DASHBOARD_SCANNER_ENABLED", "true")
    monkeypatch.setattr(security, "decode_token", lambda _token: {"sub": "operator", "roles": ["trader"]})
    sent = await drive_websocket(
        scanner_app(), "/api/v1/scanner/ws", "token=synthetic-token",
        messages=[{"type": "websocket.receive", "text": json.dumps({"action": "ping"})}],
    )
    assert sent[0]["type"] == "websocket.accept"
    replies = [json.loads(m["text"]) for m in sent if m["type"] == "websocket.send"]
    assert replies[0]["status"] == "pong"


@pytest.mark.parametrize("raw,expected", [
    (5, 60), (0, 60), (-10, 60), ("abc", 60), (None, 60), (float("inf"), 60),
    (float("nan"), 60), (120, 120), ("90", 90), (10**9, 3600),
])
def test_scanner_websocket_interval_has_a_server_side_minimum(raw, expected):
    assert scanner._scan_interval(raw) == expected


@pytest.mark.asyncio
async def test_enabled_scan_keeps_the_event_loop_responsive(fake_market_api, monkeypatch):
    symbols = ["AAPL", "MSFT", "NVDA", "AMD", "META", "AMZN"]
    monkeypatch.setenv("DASHBOARD_SCANNER_ENABLED", "true")
    monkeypatch.setattr(scanner, "SCANNABLE_SYMBOLS", symbols)
    # Exercise the bars requests too (the image has no pandas_ta, so indicators
    # still fail after their request and nothing matches).
    monkeypatch.setattr(scanner, "_indicator_backend_available", lambda: True)
    fake_market_api.quotes = {s: (100.0, 100.2) for s in symbols}
    fake_market_api.delay = 0.3  # each blocking SDK round trip

    started = time.monotonic()
    response, lag = await max_loop_lag_during(scanner.scan_market_internal(scanner.ScanFilters()))
    elapsed = time.monotonic() - started

    paths = [call.path for call in fake_market_api.calls]
    assert paths.count("/stocks/quotes/latest") == 1  # one batched quote request
    assert paths.count("/stocks/bars") == 2 * len(symbols)
    assert elapsed >= 0.3 * (1 + 2 * len(symbols) / scanner.SCAN_CONCURRENCY) * 0.9
    # The loop never stalled for a round trip: the calls ran on pool threads.
    assert lag < 0.15
    assert all(call.thread.startswith("dashboard-marketdata") for call in fake_market_api.calls)
    assert all(call.timeout == dashboard_market_data.HTTP_TIMEOUT_S for call in fake_market_api.calls)
    assert fake_market_api.max_bars_in_flight <= scanner.SCAN_CONCURRENCY
    assert response.results == [] and response.total == 0


@pytest.mark.asyncio
async def test_enabled_scan_without_indicator_backend_makes_no_requests(fake_market_api, monkeypatch):
    monkeypatch.setenv("DASHBOARD_SCANNER_ENABLED", "true")
    monkeypatch.setattr(scanner, "_indicator_backend_available", lambda: False)
    response = await scanner.scan_market_internal(scanner.ScanFilters())
    assert response.results == [] and response.total == 0
    assert fake_market_api.calls == []


@pytest.mark.asyncio
async def test_dashboard_quote_requests_never_retry_or_sleep_and_back_off(fake_market_api):
    fake_market_api.status = 429
    started = time.monotonic()
    batch = await dashboard_market_data.get_latest_quotes(["AAPL"])
    # alpaca-py's default would retry 429 three times, sleeping 3 s before each.
    assert time.monotonic() - started < 1.0
    assert len(fake_market_api.calls) == 1
    assert batch.quotes == {} and batch.unavailable == {"AAPL"}
    again = await dashboard_market_data.get_latest_quotes(["AAPL"])
    assert len(fake_market_api.calls) == 1  # no new request for one TTL after a failure
    assert again.unavailable == {"AAPL"}


@pytest.mark.asyncio
async def test_dashboard_market_data_client_refuses_the_event_loop(fake_market_api):
    with pytest.raises(RuntimeError, match="run_blocking"):
        dashboard_market_data.stock_data_client()


# ── A8-01: watchlist quotes ───────────────────────────────────────────────────
@pytest_asyncio.fixture
async def watchlist_db(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "watchlists.sqlite"))
    async with engine.begin() as conn:
        await conn.execute(CreateTable(Watchlist.__table__))
        await conn.execute(CreateTable(WatchlistSymbol.__table__))
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


async def seed_watchlist(sessions, watchlist_id: int, user_id: int, symbols: list[str]):
    async with sessions() as session:
        session.add(Watchlist(id=watchlist_id, user_id=user_id, name=f"list-{watchlist_id}",
                              is_default=False))
        await session.flush()
        for order, symbol in enumerate(symbols):
            session.add(WatchlistSymbol(watchlist_id=watchlist_id, symbol=symbol, order=order))
        await session.commit()


def watchlist_app(sessions, user_id: int) -> FastAPI:
    from backend.api.dependencies import get_current_db_user
    from backend.infra.db import get_db_session

    app = FastAPI()
    app.include_router(watchlists.router, prefix="/api/v1")

    async def db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db_session] = db
    app.dependency_overrides[get_current_db_user] = lambda: SimpleNamespace(id=user_id)
    return app


@pytest.fixture
def no_alpaca_client(monkeypatch):
    from backend.data import alpaca_client

    def refuse(*_args, **_kwargs):
        raise AssertionError("AlpacaClient must not be constructed per request")

    monkeypatch.setattr(alpaca_client.AlpacaClient, "__init__", refuse)


@pytest.mark.asyncio
async def test_watchlist_quotes_use_one_batched_request_and_the_ui_shape(
    fake_market_api, watchlist_db, no_alpaca_client,
):
    await seed_watchlist(watchlist_db, 1, 1, ["AAPL", "MSFT", "ZZZZ"])
    await seed_watchlist(watchlist_db, 2, 2, ["MSFT", "AAPL"])
    fake_market_api.quotes = {"AAPL": (189.0, 189.2), "MSFT": (0.0, 410.0)}

    async with asgi_client(watchlist_app(watchlist_db, 1)) as http:
        response = await http.get("/api/v1/watchlists/1/quotes")
    assert response.status_code == 200
    body = response.json()
    # {symbol: {...}}: the map WatchlistSymbolCard reads with quotes?.[symbol].
    assert list(body) == ["AAPL", "MSFT", "ZZZZ"]
    assert body["AAPL"] == {
        "symbol": "AAPL", "price": 189.1, "change": None, "changePercent": None,
        "bid": 189.0, "ask": 189.2, "timestamp": "2026-10-12T14:30:00+00:00",
    }
    assert (body["MSFT"]["price"], body["MSFT"]["error"]) == (None, "no_two_sided_quote")
    assert (body["ZZZZ"]["price"], body["ZZZZ"]["error"]) == (None, "no_quote")
    for entry in body.values():
        assert {"symbol", "price", "change", "changePercent", "timestamp"} <= set(entry)
        assert entry["price"] is None or isinstance(entry["price"], float)

    [call] = fake_market_api.calls
    assert call.path == "/stocks/quotes/latest"
    assert call.params["symbols"] == "AAPL,MSFT,ZZZZ"
    assert call.timeout == dashboard_market_data.HTTP_TIMEOUT_S
    assert call.thread.startswith("dashboard-marketdata")

    # Another poll and another user's list of the same symbols within the TTL:
    # served from the shared cache, no second request.
    async with asgi_client(watchlist_app(watchlist_db, 1)) as http:
        assert (await http.get("/api/v1/watchlists/1/quotes")).json() == body
    async with asgi_client(watchlist_app(watchlist_db, 2)) as http:
        other = (await http.get("/api/v1/watchlists/2/quotes")).json()
    assert list(other) == ["MSFT", "AAPL"] and other["AAPL"] == body["AAPL"]
    assert len(fake_market_api.calls) == 1


@pytest.mark.asyncio
async def test_watchlist_quotes_cap_symbols_per_request(fake_market_api, watchlist_db, no_alpaca_client):
    symbols = [f"S{i:03d}" for i in range(60)] + ["BTC/USD"]
    await seed_watchlist(watchlist_db, 1, 1, symbols)
    fake_market_api.quotes = {s: (10.0, 10.2) for s in symbols[:60]}

    async with asgi_client(watchlist_app(watchlist_db, 1)) as http:
        body = (await http.get("/api/v1/watchlists/1/quotes")).json()

    [call] = fake_market_api.calls
    assert call.params["symbols"].split(",") == symbols[:watchlists.WATCHLIST_QUOTE_SYMBOL_LIMIT]
    assert watchlists.WATCHLIST_QUOTE_SYMBOL_LIMIT == 50
    assert len(body) == len(symbols)
    assert all(body[s]["price"] == 10.1 for s in symbols[:50])
    assert all((body[s]["price"], body[s]["error"]) == (None, "symbol_limit") for s in symbols[50:60])
    assert (body["BTC/USD"]["price"], body["BTC/USD"]["error"]) == (None, "unsupported_symbol")


@pytest.mark.asyncio
async def test_watchlist_quotes_never_block_the_event_loop(fake_market_api, watchlist_db, no_alpaca_client):
    await seed_watchlist(watchlist_db, 1, 1, ["AAPL", "MSFT"])
    fake_market_api.quotes = {"AAPL": (189.0, 189.2), "MSFT": (409.0, 410.0)}
    fake_market_api.delay = 0.3

    async with asgi_client(watchlist_app(watchlist_db, 1)) as http:
        response, lag = await max_loop_lag_during(http.get("/api/v1/watchlists/1/quotes"))
    assert response.status_code == 200
    assert response.json()["MSFT"]["price"] == 409.5
    assert lag < 0.15
    # Only the batched quote request: no account call, no per-symbol requests.
    assert [call.path for call in fake_market_api.calls] == ["/stocks/quotes/latest"]


@pytest.mark.asyncio
async def test_watchlist_quotes_time_out_quickly_when_market_data_stalls(
    fake_market_api, watchlist_db, no_alpaca_client, monkeypatch,
):
    await seed_watchlist(watchlist_db, 1, 1, ["AAPL"])
    fake_market_api.quotes = {"AAPL": (189.0, 189.2)}
    fake_market_api.delay = 1.5
    monkeypatch.setattr(dashboard_market_data, "SDK_CALL_TIMEOUT_S", 0.2)

    started = time.monotonic()
    async with asgi_client(watchlist_app(watchlist_db, 1)) as http:
        body = (await http.get("/api/v1/watchlists/1/quotes")).json()
        assert time.monotonic() - started < 1.0
        assert (body["AAPL"]["price"], body["AAPL"]["error"]) == (None, "market_data_unavailable")
        again = (await http.get("/api/v1/watchlists/1/quotes")).json()
    assert again["AAPL"]["error"] == "market_data_unavailable"
    assert len(fake_market_api.calls) == 1  # backed off for one TTL


def test_get_current_price_latest_bar_fallback_uses_request_objects():
    from alpaca.data.requests import CryptoLatestBarRequest, StockLatestBarRequest

    from backend.data.alpaca_client import AlpacaClient

    class StockData:  # the real alpaca-py 0.43 signatures: one request object
        def __init__(self):
            self.bar_requests = []

        def get_stock_latest_quote(self, request_params):
            return {"AAPL": SimpleNamespace(bid_price=0.0, ask_price=101.0)}

        def get_stock_latest_bar(self, request_params):
            self.bar_requests.append(request_params)
            return {"AAPL": SimpleNamespace(close=100.5)}

    class CryptoData:
        def __init__(self):
            self.bar_requests = []

        def get_crypto_latest_bar(self, request_params, feed=None):
            self.bar_requests.append(request_params)
            return {"BTC/USD": SimpleNamespace(close=60000.0)}

    client = AlpacaClient(api_key="synthetic-key-id", secret_key="synthetic-secret",
                          paper=True, test_mode=True)
    client.min_request_interval = 0
    client.stock_data_client, client.crypto_data_client = StockData(), CryptoData()
    assert client.get_current_price("AAPL") == 100.5
    [request] = client.stock_data_client.bar_requests
    assert isinstance(request, StockLatestBarRequest) and request.symbol_or_symbols == "AAPL"
    assert client.get_current_price("BTC/USD") == 60000.0
    [request] = client.crypto_data_client.bar_requests
    assert isinstance(request, CryptoLatestBarRequest)


# ── A3-01: execution mode ─────────────────────────────────────────────────────
def _allowed_order_statuses() -> tuple[str, ...]:
    """The production ck_orders_status set, read from the migration source."""
    path = REPO / "backend/migrations/versions/20260503_000002_xx_2_widen_orders_status_check.py"
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "_WIDENED_STATUSES":
            return tuple(ast.literal_eval(node.value))
    raise AssertionError("ck_orders_status set not found")


@pytest_asyncio.fixture
async def order_sessions(tmp_path):
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "orders.sqlite"))
    allowed = ", ".join(f"'{status}'" for status in _allowed_order_statuses())
    async with engine.begin() as conn:
        for table in (Order, Execution, PositionLot, RealizedTrade, AuditLog, OutboxEvent):
            await conn.run_sync(lambda c, t=table.__table__: t.create(c))
        for when in ("INSERT", "UPDATE"):
            await conn.execute(text(
                f"CREATE TRIGGER ck_orders_status_{when.lower()} BEFORE {when} ON orders "
                f"WHEN NEW.status NOT IN ({allowed}) "
                "BEGIN SELECT RAISE(ABORT, 'violates check constraint ck_orders_status'); END"
            ))
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


class FakeBroker:
    """Records every broker call; answers like Alpaca for an accepted order."""

    def __init__(self, *, position=None):
        self.position = position
        self.calls: list[tuple] = []

    async def find_order_by_client_order_id(self, client_order_id):
        self.calls.append(("lookup", client_order_id))
        return None

    async def get_position(self, symbol):
        self.calls.append(("position", symbol))
        return self.position

    async def place_order(self, **order):
        self.calls.append(("POST", order))
        return {"id": BROKER_ID, "client_order_id": order["client_order_id"],
                "symbol": order["symbol"], "side": order["side"], "qty": str(order["qty"]),
                "status": "accepted", "filled_qty": "0", "filled_avg_price": None}

    async def reconcile_order_acknowledgement(self, client_order_id):
        raise AssertionError("lookup-only reconciliation is not part of these flows")

    def kinds(self):
        return [call[0] for call in self.calls]


@pytest.fixture
def execution(monkeypatch, order_sessions):
    """Real worker, dispatcher and execution-mode service; fake broker; SQLite store."""
    from backend import websocket
    from backend.integrations import alpaca_broker, alpaca_outbox
    from backend.services import order_service as order_service_mod

    monkeypatch.setenv("ORGANISM_LONG_ONLY", "true")
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setattr(order_service_mod, "_circuit_breaker", None)
    for name in ("_override_mode", "_override_set_by", "_override_set_at"):
        monkeypatch.setattr(tem, name, None)
    dispatcher = alpaca_outbox.AlpacaOutboxDispatcher.__new__(alpaca_outbox.AlpacaOutboxDispatcher)
    dispatcher.use_mock_broker = False
    monkeypatch.setattr(alpaca_outbox, "get_alpaca_outbox_dispatcher", lambda: dispatcher)
    monkeypatch.setattr(websocket, "broadcaster", SimpleNamespace(broadcast_to_topic=AsyncMock()))

    @asynccontextmanager
    async def context():
        async with order_sessions() as session:
            yield session

    monkeypatch.setattr("backend.infra.db.get_session_context", context)

    def configure(*, configured: str, override: str | None = None):
        """TRADING_EXECUTION_MODE plus an override set as an admin could once the lock lifts."""
        monkeypatch.setenv("TRADING_EXECUTION_MODE", configured)
        if override is not None:
            monkeypatch.setattr(research_policy, "RESEARCH_POLICY_LOCKED", False)
            tem.set_trading_execution_mode_override(override, actor="synthetic-admin")
            monkeypatch.setattr(research_policy, "RESEARCH_POLICY_LOCKED", True)
        return tem.get_trading_execution_mode()

    def bind(broker):
        monkeypatch.setattr(alpaca_broker, "get_alpaca_broker_client", lambda: broker)
        worker = OutboxWorker(order_sessions, initial_backoff=0, jitter_factor=0, max_retries=3)
        worker.use_mock_broker = False
        return worker

    return SimpleNamespace(configure=configure, bind=bind, sessions=order_sessions)


async def submit_organism_exit(sessions, qty=10, symbol="AAPL"):
    """What OrganismLiveEngine._submit_exit_order sends to OrderService (EOD flatten)."""
    result = await OrderService(sessionmaker=sessions).submit_symbol_order(
        symbol=symbol, side="sell", qty=qty, order_type="market", tif="day", reduce_only=True,
        idempotency_key=f"organism_exit_{symbol}_20261012_s1_t390_eod_flatten_q{qty}_{uuid.uuid4().hex[:6]}",
        attributes={"source": "organism", "reason": "eod_flatten", "tick": 390},
    )
    return result["order_id"]


async def submit_organism_entry(sessions, qty=10, symbol="AAPL"):
    """What OrganismLiveEngine._submit_entry_order sends to OrderService."""
    result = await OrderService(sessionmaker=sessions).submit_symbol_order(
        symbol=symbol, side="buy", qty=qty, order_type="limit", tif="day", limit_price=101.25,
        idempotency_key=f"organism_{symbol}_20261012_s1_t10_organism_entry_buy_q{qty}_{uuid.uuid4().hex[:6]}",
        attributes={"source": "organism", "reason": "organism_entry", "tick": 10,
                    "entry_source": "alpha", "strategy_id": "alpha_baseline", "evidence_tier": 0},
    )
    return result["order_id"]


async def submit_manual(sessions, *, symbol="MSFT", side="buy", qty=5, order_type="market"):
    """What POST /api/v1/orders sends to OrderService."""
    result = await OrderService(sessionmaker=sessions).submit_symbol_order(
        symbol=symbol, side=side, qty=qty, order_type=order_type, tif="day",
        limit_price=410.0 if order_type == "limit" else None,
        idempotency_key=f"manual-{uuid.uuid4().hex}",
        attributes={"user_id": "synthetic-admin", "source": "api"},
    )
    return result["order_id"]


async def process_one(worker):
    claimed = await worker._get_pending_events()
    assert len(claimed) == 1
    await worker._process_event(claimed[0])
    return claimed[0]


async def state(sessions, order_id):
    async with sessions() as session:
        order = await session.get(Order, uuid.UUID(order_id))
        event = (await session.execute(select(OutboxEvent))).scalars().one()
        return order, event


def long_position(qty, symbol="AAPL"):
    return {"symbol": symbol, "qty": str(qty), "side": "long", "qty_available": str(qty)}


@pytest.mark.asyncio
@pytest.mark.parametrize("override", ["shadow", "dry_run"])
async def test_organism_exit_dispatches_normally_whatever_the_override(execution, override):
    mode = execution.configure(configured="paper", override=override)
    assert (mode.mode, mode.default_mode, mode.overridden) == (override, "execute", True)
    broker = FakeBroker(position=long_position(10))
    worker = execution.bind(broker)
    order_id = await submit_organism_exit(execution.sessions)

    await process_one(worker)

    assert broker.kinds() == ["lookup", "position", "POST"]  # sent to the broker
    order, event = await state(execution.sessions, order_id)
    assert (event.status, order.status, order.broker_order_id) == ("sent", "accepted", BROKER_ID)
    assert order.filled_qty == 0 and "execution_mode" not in order.attributes


@pytest.mark.asyncio
@pytest.mark.parametrize("override", ["shadow", "dry_run"])
async def test_organism_entry_submission_dispatches_normally_whatever_the_override(execution, override):
    execution.configure(configured="paper", override=override)
    broker = FakeBroker()
    worker = execution.bind(broker)
    order_id = await submit_organism_entry(execution.sessions)
    [claimed] = await worker._get_pending_events()

    result = await worker._process_order_submitted(dict(claimed["payload"]))

    assert result["success"] is True and result["broker"] == "alpaca"
    assert broker.kinds() == ["POST"]
    order, _ = await state(execution.sessions, order_id)
    assert (order.status, order.broker_order_id) == ("accepted", BROKER_ID)


@pytest.mark.asyncio
@pytest.mark.parametrize("configured", ["shadow", "dry_run"])
async def test_engine_orders_follow_the_configured_mode_never_a_runtime_flip(execution, configured):
    # A runtime flip to execute must not make an engine started in a non-execute
    # mode (whose startup guard skipped the loss-breaker check) trade.
    mode = execution.configure(configured=configured, override="execute")
    assert (mode.mode, mode.default_mode) == ("execute", configured)
    broker = FakeBroker(position=long_position(10))
    worker = execution.bind(broker)
    order_id = await submit_organism_exit(execution.sessions)

    await process_one(worker)

    assert broker.calls == []  # nothing sent
    order, event = await state(execution.sessions, order_id)
    assert (event.status, order.status, order.broker_order_id) == ("sent", "rejected", None)
    assert order.filled_qty == 0 and order.avg_fill_price is None
    assert order.attributes["execution_mode"] == configured
    assert order.attributes["source"] == "organism"  # original attributes kept


@pytest.mark.asyncio
@pytest.mark.parametrize("override", ["shadow", "dry_run"])
@pytest.mark.parametrize("order_type", ["market", "limit"])
async def test_manual_orders_in_non_execute_modes_end_rejected_with_no_fill(execution, override, order_type):
    execution.configure(configured="paper", override=override)
    broker = FakeBroker()
    worker = execution.bind(broker)
    order_id = await submit_manual(execution.sessions, order_type=order_type)

    await process_one(worker)

    assert broker.calls == []
    order, event = await state(execution.sessions, order_id)
    # Accountable terminal state (the constraint has no 'shadow'); nothing invented.
    assert event.status == "sent"
    assert (order.status, order.broker_order_id, order.avg_fill_price) == ("rejected", None, None)
    assert order.filled_qty == Decimal(0)
    assert order.attributes["execution_mode"] == override
    assert order.attributes["not_submitted"] == "execution_mode"
    assert order.attributes["source"] == "api"
    assert await worker._get_pending_events() == []  # finished, not retried


@pytest.mark.asyncio
async def test_mock_broker_acknowledges_without_an_invented_fill(execution):
    execution.configure(configured="paper")
    worker = execution.bind(FakeBroker())
    worker.use_mock_broker = True
    order_id = await submit_manual(execution.sessions, symbol="AAPL", order_type="market")

    await process_one(worker)

    order, event = await state(execution.sessions, order_id)
    assert event.status == "sent"
    assert order.status == "accepted" and order.broker_order_id.startswith("MOCK_AAPL_")
    assert order.filled_qty == Decimal(0) and order.avg_fill_price is None


@pytest.mark.asyncio
async def test_execution_mode_override_is_refused_under_the_research_lock(monkeypatch):
    from backend.infra.security import AuthenticatedUser, require_admin

    for name in ("_override_mode", "_override_set_by", "_override_set_at"):
        monkeypatch.setattr(tem, name, None)
    assert research_policy.RESEARCH_POLICY_LOCKED is True  # hard-coded for the research period
    app = FastAPI()
    app.include_router(admin_trading.router, prefix="/api/v1")
    app.dependency_overrides[require_admin] = lambda: AuthenticatedUser(
        username="synthetic-admin", roles=["admin"], token_id="synthetic")
    url = "/api/v1/admin/trading/execution-mode"

    async with asgi_client(app) as http:
        refused = await http.put(url, json={"mode": "shadow"})
        assert refused.status_code == 423
        assert refused.json()["detail"]["code"] == "research_policy_locked"
        current = (await http.get(url)).json()
        assert current["overridden"] is False and current["override_allowed"] is False
        assert "research policy lock" in current["override_blocked_reason"]
        assert (await http.put(url, json={"mode": "pause"})).status_code == 422

        # After the lock lifts, a running engine still refuses the switch.
        monkeypatch.setattr(research_policy, "RESEARCH_POLICY_LOCKED", False)
        app.state.organism_scheduler = SimpleNamespace(is_running=True)
        busy = await http.put(url, json={"mode": "shadow"})
        assert busy.status_code == 409
        assert busy.json()["detail"]["code"] == "organism_engine_running"
        assert (await http.get(url)).json()["override_allowed"] is False

        app.state.organism_scheduler = SimpleNamespace(is_running=False)
        accepted = await http.put(url, json={"mode": "shadow"})
        assert accepted.status_code == 200
        assert (accepted.json()["mode"], accepted.json()["overridden"]) == ("shadow", True)
        cleared = await http.delete(url)
        assert cleared.status_code == 200 and cleared.json()["overridden"] is False

    # The service refuses every caller under the lock, not just the route.
    monkeypatch.setattr(research_policy, "RESEARCH_POLICY_LOCKED", True)
    with pytest.raises(tem.ExecutionModeOverrideRefused):
        tem.set_trading_execution_mode_override("dry_run", actor="synthetic-script")
    assert tem.get_trading_execution_mode().overridden is False
