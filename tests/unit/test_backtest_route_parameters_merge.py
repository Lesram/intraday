import datetime
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes.backtest import (
    get_backtest_service,
    get_session,
    get_strategy_service,
    router as backtest_router,
)
from backend.infra.security import AuthenticatedUser, get_authenticated_user
from backend.models.backtest import BacktestResult, EquityPoint, PerformanceMetrics


def _make_minimal_result(*, strategy_id: str, strategy_name: str, start: str, end: str) -> BacktestResult:
    now = datetime.datetime.now(datetime.UTC)
    metrics = PerformanceMetrics(
        total_return=0.0,
        annualized_return=0.0,
        sharpe_ratio=0.0,
        sortino_ratio=0.0,
        calmar_ratio=0.0,
        max_drawdown=0.0,
        max_drawdown_duration_days=0,
        volatility=0.0,
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        win_rate=0.0,
        profit_factor=0.0,
        avg_trade_pnl=0.0,
        avg_win=0.0,
        avg_loss=0.0,
        largest_win=0.0,
        largest_loss=0.0,
        max_consecutive_wins=0,
        max_consecutive_losses=0,
        alpha=None,
        beta=None,
        total_commission=0.0,
        avg_trade_duration_days=0.0,
    )

    equity_curve = [
        EquityPoint(date=datetime.date.fromisoformat(start), value=100_000.0, cash=100_000.0, positions_value=0.0)
    ]

    return BacktestResult(
        id="00000000-0000-0000-0000-000000000000",
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        start_date=datetime.date.fromisoformat(start),
        end_date=datetime.date.fromisoformat(end),
        initial_capital=100_000.0,
        final_equity=100_000.0,
        metrics=metrics,
        equity_curve=equity_curve,
        trade_log=[],
        monthly_returns=[],
        status="completed",
        error_message=None,
        progress=100,
        origin=None,
        created_at=now,
        started_at=now,
        completed_at=now,
    )


def test_backtest_route_does_not_override_strategy_params_when_missing():
    app = FastAPI()
    app.include_router(backtest_router, prefix="/api/v1")
    client = TestClient(app)

    def mock_auth():
        return AuthenticatedUser(username="test_user", roles=["trader"], token_id="t")

    strategy_id = "32b3d122-e80f-470c-966b-76fa95a6f84a"
    strategy_params = {"warmup": 75, "_origin": "optuna", "_origin_run_id": "optuna_best"}
    strategy = {
        "id": strategy_id,
        "name": "optuna_strategy",
        "strategy_type": "momentum",
        "symbols": ["AAPL"],
        "parameters": strategy_params,
    }

    strategy_service = AsyncMock()
    strategy_service.get_strategy = AsyncMock(return_value=strategy)

    captured = {}

    async def _run_backtest_side_effect(**kwargs):
        captured.update(kwargs)
        return _make_minimal_result(
            strategy_id=strategy_id,
            strategy_name="optuna_strategy",
            start="2024-01-01",
            end="2024-01-10",
        )

    backtest_service = AsyncMock()
    backtest_service.run_backtest = AsyncMock(side_effect=_run_backtest_side_effect)

    app.dependency_overrides[get_authenticated_user] = mock_auth
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    app.dependency_overrides[get_strategy_service] = lambda: strategy_service
    app.dependency_overrides[get_backtest_service] = lambda: backtest_service

    try:
        response = client.post(
            f"/api/v1/backtests/strategies/{strategy_id}/backtest",
            json={
                "strategy_id": strategy_id,
                "start_date": "2024-01-01",
                "end_date": "2024-01-10",
                "initial_capital": 100000,
                "parameters": None,
            },
        )

        assert response.status_code == 200
        # Missing parameters should not override strategy params
        assert "parameters" in captured
        assert captured["parameters"] is None
    finally:
        app.dependency_overrides.clear()


def test_backtest_route_merges_parameter_overrides_preserving_optuna_metadata():
    app = FastAPI()
    app.include_router(backtest_router, prefix="/api/v1")
    client = TestClient(app)

    def mock_auth():
        return AuthenticatedUser(username="test_user", roles=["trader"], token_id="t")

    strategy_id = "32b3d122-e80f-470c-966b-76fa95a6f84a"
    strategy_params = {
        "warmup": 75,
        "_origin": "optuna",
        "_origin_run_id": "optuna_best_harder_holdout2025",
        "rsi_buy": 43.0,
    }
    strategy = {
        "id": strategy_id,
        "name": "optuna_strategy",
        "strategy_type": "momentum",
        "symbols": ["AAPL"],
        "parameters": strategy_params,
    }

    strategy_service = AsyncMock()
    strategy_service.get_strategy = AsyncMock(return_value=strategy)

    captured = {}

    async def _run_backtest_side_effect(**kwargs):
        captured.update(kwargs)
        return _make_minimal_result(
            strategy_id=strategy_id,
            strategy_name="optuna_strategy",
            start="2024-01-01",
            end="2024-01-10",
        )

    backtest_service = AsyncMock()
    backtest_service.run_backtest = AsyncMock(side_effect=_run_backtest_side_effect)

    app.dependency_overrides[get_authenticated_user] = mock_auth
    app.dependency_overrides[get_session] = lambda: AsyncMock()
    app.dependency_overrides[get_strategy_service] = lambda: strategy_service
    app.dependency_overrides[get_backtest_service] = lambda: backtest_service

    try:
        response = client.post(
            f"/api/v1/backtests/strategies/{strategy_id}/backtest",
            json={
                "strategy_id": strategy_id,
                "start_date": "2024-01-01",
                "end_date": "2024-01-10",
                "initial_capital": 100000,
                "parameters": {"warmup": 10},
            },
        )

        assert response.status_code == 200
        assert captured["parameters"]["warmup"] == 10
        # Optuna metadata should still be present after merge
        assert captured["parameters"]["_origin"] == "optuna"
        assert captured["parameters"]["_origin_run_id"] == "optuna_best_harder_holdout2025"
        assert captured["parameters"]["rsi_buy"] == 43.0
    finally:
        app.dependency_overrides.clear()
