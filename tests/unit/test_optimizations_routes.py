import json
from datetime import datetime

import pytest

from backend.api.routes import optimizations as optimizations_routes
from backend.infra.security import AuthenticatedUser


@pytest.mark.asyncio
async def test_list_and_get_optimization_runs(tmp_path, monkeypatch):
    run_payload = {
        "name": "optuna_best_run",
        "source_log": "test_results/optuna_run.txt",
        "symbols": ["AAPL", "MSFT"],
        "range": {"start": "2023-01-01", "end": "2024-12-31"},
        "holdout": {"start": "2024-01-01", "end": "2024-12-31"},
        "params": {"rsi_buy": 42.0, "sma_fast": 8},
    }
    run_path = tmp_path / "optuna_best_run.json"
    run_path.write_text(json.dumps(run_payload), encoding="utf-8")

    monkeypatch.setattr(optimizations_routes, "_configs_dir", lambda: tmp_path)

    user = AuthenticatedUser(username="tester", roles=[], token_id="t")

    runs = await optimizations_routes.list_optimization_runs(current_user=user)
    assert len(runs) == 1
    assert runs[0].id == "optuna_best_run"
    assert runs[0].origin == "optuna"
    assert runs[0].parameters["rsi_buy"] == 42.0

    run = await optimizations_routes.get_optimization_run("optuna_best_run", current_user=user)
    assert run.id == "optuna_best_run"
    assert run.symbols == ["AAPL", "MSFT"]


@pytest.mark.asyncio
async def test_create_strategy_from_optimization(tmp_path, monkeypatch):
    run_payload = {
        "name": "optuna_best_run",
        "source_log": "test_results/optuna_run.txt",
        "symbols": ["AAPL", "MSFT"],
        "env": {
            "OPT_FIXED_SLIPPAGE_BPS": 8.5,
            "OPT_FIXED_COMMISSION_PER_TRADE": 0.3,
        },
        "costs": {
            "slippage_bps": 8.5,
            "commission_per_trade": 0.3,
        },
        "params": {"rsi_buy": 42.0, "sma_fast": 8},
    }
    run_path = tmp_path / "optuna_best_run.json"
    run_path.write_text(json.dumps(run_payload), encoding="utf-8")

    monkeypatch.setattr(optimizations_routes, "_configs_dir", lambda: tmp_path)

    captured = {}

    class FakeStrategyService:
        def __init__(self, session, user_id):
            self.session = session
            self.user_id = user_id

        async def create_strategy(self, strategy_data):
            captured.update(strategy_data)
            timestamp = datetime(2026, 2, 3, 0, 0, 0).isoformat()
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

    monkeypatch.setattr(optimizations_routes, "StrategyService", FakeStrategyService)

    user = AuthenticatedUser(username="tester", roles=[], token_id="t")

    payload = optimizations_routes.OptimizationStrategyCreate(
        name="Imported Strategy",
        description="Imported from optuna",
        strategy_type="technical_analysis",
        symbols=["AAPL"],
    )

    response = await optimizations_routes.create_strategy_from_optimization(
        "optuna_best_run",
        payload,
        session=None,
        current_user=user,
    )

    assert response["name"] == "Imported Strategy"
    assert response["strategyType"] == "technical_analysis"
    assert response["symbols"] == ["AAPL"]

    params = captured["parameters"]
    assert params["rsi_buy"] == 42.0
    assert params["_origin"] == "optuna"
    assert params["_origin_run_id"] == "optuna_best_run"
    assert "_origin_source" in params
    assert params["slippage_bps"] == 8.5
    assert params["commission_per_trade"] == 0.3
