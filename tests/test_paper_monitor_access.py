"""The monitor can inspect a paper runtime without gaining trading controls."""
from unittest.mock import AsyncMock
import io
import json
import urllib.request

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import paper_monitor
from backend.infra.security import AuthenticatedUser, get_current_user


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER", "true")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    from backend.api.routes import data_integrity_health, deploy_health, strategy_health
    from backend.organism import routes

    monkeypatch.setattr(routes, "get_organism_status", AsyncMock(return_value={"enabled": True}))
    monkeypatch.setattr(deploy_health, "deploy_health", AsyncMock(return_value={"source_sha": "verified"}))
    monkeypatch.setattr(data_integrity_health, "data_integrity", AsyncMock(return_value={"accounting_status": "ok"}))
    monkeypatch.setattr(strategy_health, "edge_health", AsyncMock(return_value={"status": "insufficient"}))
    instance = FastAPI()
    instance.include_router(paper_monitor.router, prefix="/api/v1")
    instance.include_router(routes.router, prefix="/api/v1")
    instance.include_router(deploy_health.router, prefix="/api/v1")
    return instance


def authorize(app, roles):
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        username="test-observer", roles=roles, token_id="test-only",
    )


@pytest.mark.parametrize("path", ["organism/status", "deploy", "data-integrity", "edge"])
def test_observer_reads_only_explicit_paper_endpoints(app, path):
    authorize(app, ["paper_monitor"])
    assert TestClient(app).get(f"/api/v1/paper-monitor/{path}").status_code == 200


@pytest.mark.parametrize("roles,expected", [(None, 401), (["viewer"], 403), (["trader"], 403), (["admin"], 200)])
def test_authentication_and_dedicated_role_required(app, roles, expected):
    if roles is not None:
        authorize(app, roles)
    assert TestClient(app).get("/api/v1/paper-monitor/organism/status").status_code == expected


@pytest.mark.parametrize("paper,url", [
    ("false", "https://api.alpaca.markets"),
    ("true", "https://api.alpaca.markets"),
    ("", "https://paper-api.alpaca.markets"),
])
def test_real_or_ambiguous_broker_configuration_denied(app, monkeypatch, paper, url):
    authorize(app, ["paper_monitor"])
    monkeypatch.setenv("ALPACA_PAPER", paper)
    monkeypatch.setenv("ALPACA_BASE_URL", url)
    assert TestClient(app).get("/api/v1/paper-monitor/deploy").status_code == 403


@pytest.mark.parametrize("path", ["halt", "resume", "tick", "freeze", "unfreeze", "promote", "rollback"])
def test_observer_cannot_use_existing_organism_controls(app, path):
    authorize(app, ["paper_monitor"])
    assert TestClient(app).post(f"/api/v1/organism/{path}").status_code == 403


def test_existing_admin_endpoint_remains_admin_only(app):
    authorize(app, ["paper_monitor"])
    assert TestClient(app).get("/api/v1/health/deploy").status_code == 403


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_monitor_surface_has_no_mutation_methods(app, method):
    authorize(app, ["paper_monitor"])
    client = TestClient(app)
    assert getattr(client, method)("/api/v1/paper-monitor/organism/status").status_code == 405


def test_snapshot_can_use_monitor_status(monkeypatch):
    from scripts.runtime import write_runtime_snapshot as snapshot

    paths = []
    monkeypatch.setattr(snapshot, "_get_auth_token", lambda _base: "synthetic-test-token")

    def urlopen(request, **_kwargs):
        paths.append(request.full_url)
        assert request.get_header("Authorization") == "Bearer synthetic-test-token"
        return io.BytesIO(b'{"enabled": true}')

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert snapshot._curl_organism_status() == {"enabled": True}
    assert paths == ["http://localhost:8000/api/v1/paper-monitor/organism/status"]


@pytest.mark.parametrize("mode,expected_calls", [(0o600, 1), (0o644, 0)])
def test_private_credentials_file_permissions(monkeypatch, tmp_path, mode, expected_calls):
    from scripts.runtime import write_runtime_snapshot as snapshot

    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"username": "observer", "password": "synthetic-secret"}))
    path.chmod(mode)
    monkeypatch.delenv("INTRA_API_USER", raising=False)
    monkeypatch.delenv("INTRA_API_PASSWORD", raising=False)
    monkeypatch.setenv("INTRA_API_CREDENTIALS_FILE", str(path))
    calls = []

    def login(request, **_kwargs):
        calls.append(request.full_url)
        assert json.loads(request.data) == {"username": "observer", "password": "synthetic-secret"}
        return io.BytesIO(b'{"access_token": "synthetic-token"}')

    monkeypatch.setattr(urllib.request, "urlopen", login)
    assert snapshot._get_auth_token("http://localhost:8000") == ("synthetic-token" if expected_calls else "")
    assert len(calls) == expected_calls


def test_scoped_monitor_token_cannot_reach_position_close(app, monkeypatch):
    from backend.api.routes import positions
    from backend.infra import security
    from backend.integrations import alpaca_broker

    app.include_router(positions.router, prefix="/api/v1")
    token = security.create_access_token("observer", ["paper_monitor"])
    monkeypatch.setattr(security, "is_token_blacklisted", AsyncMock(return_value=False))
    broker = AsyncMock()
    monkeypatch.setattr(alpaca_broker, "AlpacaBrokerClient", broker)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/paper-monitor/organism/status", headers=headers).status_code == 200
    response = client.post("/api/v1/positions/AAPL/close", json={}, headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "paper_monitor_scope"
    broker.assert_not_called()


@pytest.mark.parametrize("path", ["/api/v1/organism/halt", "/api/v1/positions/AAPL/close", "/api/v1/orders"])
def test_monitor_scope_cannot_fall_back_to_api_key(app, monkeypatch, path):
    from backend.infra import security
    from backend.api.routes import positions

    app.include_router(positions.router, prefix="/api/v1")
    token = security.create_access_token("observer", ["paper_monitor", "admin"])
    monkeypatch.setattr(security, "is_token_blacklisted", AsyncMock(return_value=False))
    key_check = AsyncMock()
    monkeypatch.setattr(security, "verify_api_key", key_check)
    if path == "/api/v1/orders":
        from fastapi import Depends
        app.post(path)(lambda _user=Depends(security.get_authenticated_user): {"unexpected": True})
    response = TestClient(app).post(path, headers={
        "Authorization": f"Bearer {token}", "X-API-Key": "synthetic-other-key",
    })
    assert response.status_code == 403
    assert response.json()["detail"] == "paper_monitor_scope"
    key_check.assert_not_called()


@pytest.mark.asyncio
async def test_monitor_token_cannot_open_socketio_session(monkeypatch):
    from backend.api import socketio_server

    monkeypatch.setattr(socketio_server, "decode_token", lambda _token: {"sub": "observer", "roles": ["paper_monitor"]})
    enter = AsyncMock()
    monkeypatch.setattr(socketio_server.sio, "enter_room", enter)
    assert await socketio_server.connect("observer-test", {}, {"token": "synthetic-token"}) is False
    assert "observer-test" not in socketio_server.client_subscriptions
    enter.assert_not_called()


@pytest.mark.asyncio
async def test_monitor_token_cannot_open_market_data_websocket(monkeypatch):
    from backend.api.routes import market_data

    monkeypatch.setattr(market_data, "decode_token", lambda _token: {"sub": "observer", "roles": ["paper_monitor"]})
    websocket = AsyncMock()
    await market_data.market_data_websocket(websocket, token="synthetic-token")
    websocket.close.assert_awaited_once_with(code=1008)
    websocket.receive_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_monitor_token_cannot_start_scanner_websocket(monkeypatch):
    from backend.api.routes import scanner
    from backend.infra import security

    monkeypatch.setattr(security, "decode_token", lambda _token: {"sub": "observer", "roles": ["paper_monitor"]})
    connect = AsyncMock()
    monkeypatch.setattr(scanner.scanner_manager, "connect", connect)
    websocket = AsyncMock()
    await scanner.scanner_websocket(websocket, token="synthetic-token")
    websocket.close.assert_awaited_once_with(code=4003, reason="Monitoring token scope excludes WebSockets")
    connect.assert_not_called()
