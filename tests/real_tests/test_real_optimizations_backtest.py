import uuid
from datetime import date, timedelta

import pytest
import httpx


@pytest.mark.asyncio
async def test_real_optimization_runs_list_and_get(authenticated_client: httpx.AsyncClient):
    list_response = await authenticated_client.get("/api/v1/optimizations")
    assert list_response.status_code == 200
    runs = list_response.json()

    if not runs:
        pytest.skip("No optimization runs found in configs/")

    run_id = runs[0]["id"]
    get_response = await authenticated_client.get(f"/api/v1/optimizations/{run_id}")
    assert get_response.status_code == 200
    run_payload = get_response.json()
    assert run_payload["id"] == run_id


@pytest.mark.asyncio
async def test_real_create_strategy_from_optimization(authenticated_client: httpx.AsyncClient):
    list_response = await authenticated_client.get("/api/v1/optimizations")
    assert list_response.status_code == 200
    runs = list_response.json()

    if not runs:
        pytest.skip("No optimization runs found in configs/")

    run_id = runs[0]["id"]
    payload = {
        "name": f"optuna_import_{uuid.uuid4().hex[:8]}",
        "description": "Imported from optimization run (real test)",
        "strategy_type": runs[0].get("strategy_type") or "technical_analysis",
        "symbols": runs[0].get("symbols") or [],
    }

    create_response = await authenticated_client.post(
        f"/api/v1/optimizations/{run_id}/strategy",
        json=payload,
    )

    assert create_response.status_code in (200, 201)
    data = create_response.json()
    assert data.get("name") == payload["name"]
    assert data.get("strategyType") == payload["strategy_type"]


@pytest.mark.asyncio
async def test_real_backtest_with_engine_platform(authenticated_client: httpx.AsyncClient):
    list_response = await authenticated_client.get("/api/v1/optimizations")
    assert list_response.status_code == 200
    runs = list_response.json()

    if not runs:
        pytest.skip("No optimization runs found in configs/")

    run_id = runs[0]["id"]
    payload = {
        "name": f"optuna_bt_{uuid.uuid4().hex[:8]}",
        "description": "Imported for backtest (real test)",
        "strategy_type": runs[0].get("strategy_type") or "technical_analysis",
        "symbols": runs[0].get("symbols") or [],
    }

    create_response = await authenticated_client.post(
        f"/api/v1/optimizations/{run_id}/strategy",
        json=payload,
    )
    if create_response.status_code not in (200, 201):
        pytest.skip(f"Could not create strategy from optimization: {create_response.text}")

    strategy_id = (
        create_response.json().get("strategyId")
        or create_response.json().get("id")
        or create_response.json().get("strategy_id")
    )
    if not strategy_id:
        pytest.skip("Optimization import did not return strategy id")

    end_date = date.today() - timedelta(days=2)
    start_date = end_date - timedelta(days=7)

    backtest_payload = {
        "strategy_id": strategy_id,
        "engine": "platform",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "initial_capital": 10000.0,
    }

    bt_response = await authenticated_client.post(
        f"/api/v1/backtests/strategies/{strategy_id}/backtest",
        json=backtest_payload,
    )

    assert bt_response.status_code == 200
    bt_data = bt_response.json()
    assert bt_data.get("engine") == "platform"
    assert bt_data.get("strategy_id") == strategy_id
