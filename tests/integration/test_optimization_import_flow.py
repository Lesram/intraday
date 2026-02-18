import json
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import optimizations as optimizations_routes
from backend.infra.db import get_session
from backend.infra.security import AuthenticatedUser, get_authenticated_user


@pytest.mark.integration
def test_optimization_to_strategy_to_backtest_flow(tmp_path, monkeypatch):
    run_payload = {
        "name": "optuna_run",
        "source_log": "test_results/optuna_run.txt",
        "symbols": ["AAPL", "MSFT"],
        "env": {
            "OPT_FIXED_SLIPPAGE_BPS": 5.0,
            "OPT_FIXED_COMMISSION_PER_TRADE": 0.25,
        },
        "costs": {
            "slippage_bps": 5.0,
            "commission_per_trade": 0.25,
        },
        "params": {
            "rsi_buy": 42.0,
            "sma_fast": 8,
            "position_size_pct": 0.1,
            "max_positions": 12,
            "min_position_dollars": 500,
        },
    }

    run_path = tmp_path / "optuna_run.json"
    run_path.write_text(json.dumps(run_payload), encoding="utf-8")

    monkeypatch.setattr(optimizations_routes, "_configs_dir", lambda: tmp_path)

    captured = {}

    class FakeStrategyService:
        def __init__(self, session, user_id):
            self.session = session
            self.user_id = user_id

        async def create_strategy(self, strategy_data):
            captured.update(strategy_data)
            timestamp = datetime(2026, 2, 4, 0, 0, 0).isoformat()
            return {
                "id": "11111111-1111-1111-1111-111111111111",
                "name": strategy_data["name"],
                "description": strategy_data.get("description"),
                "strategy_type": strategy_data["strategy_type"],
                "status": "inactive",
                "symbols": strategy_data.get("symbols", []),
                "parameters": strategy_data.get("parameters", {}),
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "max_drawdown_pct": 0.0,
                "created_at": timestamp,
                "updated_at": timestamp,
                "last_executed_at": None,
            }

    def mock_auth():
        return AuthenticatedUser(username="tester", roles=[], token_id="t")

    app = FastAPI()
    app.include_router(optimizations_routes.router, prefix="/api/v1")
    app.dependency_overrides[get_authenticated_user] = mock_auth
    app.dependency_overrides[get_session] = lambda: None

    monkeypatch.setattr(optimizations_routes, "StrategyService", FakeStrategyService)

    client = TestClient(app)

    response = client.get("/api/v1/optimizations")
    assert response.status_code == 200
    runs = response.json()
    assert len(runs) == 1
    assert runs[0]["id"] == "optuna_run"

    response = client.post(
        "/api/v1/optimizations/optuna_run/strategy",
        json={
            "name": "Imported Strategy",
            "description": "Imported from optuna",
            "strategy_type": "technical_analysis",
            "symbols": ["AAPL"],
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Imported Strategy"
    assert payload["strategyType"] == "technical_analysis"
    assert payload["symbols"] == ["AAPL"]

    params = captured["parameters"]
    assert params["rsi_buy"] == 42.0
    assert params["_origin"] == "optuna"
    assert params["_origin_run_id"] == "optuna_run"
    assert "_origin_source" in params
    assert params["slippage_bps"] == 5.0
    assert params["commission_per_trade"] == 0.25
    assert params["use_optuna_position_size"] is True
    assert params["use_optuna_max_positions"] is True
    assert params["use_optuna_min_position_dollars"] is True
