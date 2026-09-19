"""Phase 7 organism operator endpoint serialization regressions."""

from __future__ import annotations

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.infra.security import require_admin
from backend.organism.routes import router


class _Governance:
    def to_dict(self) -> dict:
        return {
            "trading_halted": np.bool_(False),
            "drawdown_triggered": np.bool_(False),
        }


class _Policy:
    def get_weights(self) -> dict:
        return {"alpha_breakout": np.float64(0.65)}


class _Scheduler:
    is_running = np.bool_(True)
    _tick_interval = np.int64(15)
    _last_tick_result = {"ok": np.bool_(True)}
    _tick_history = [
        {"timestamp": "2026-05-06T15:00:00Z", "orders": np.int64(0)},
    ]

    def state(self) -> dict:
        return {
            "running": np.bool_(True),
            "tick_interval_s": np.int64(15),
            "last_tick": {"ok": np.bool_(True)},
            "tick_history": self._tick_history,
            "engine": {
                "initialized": np.bool_(True),
                "ml_trained": np.bool_(True),
                "win_rate": np.float64(0.3333),
                "universe_symbols": np.array(["SPY", "QQQ"]),
            },
        }


def _build_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[require_admin] = lambda: {"roles": ["admin"]}
    app.include_router(router)
    app.state.organism_governance = _Governance()
    app.state.living_policy = _Policy()
    app.state.organism_scheduler = _Scheduler()
    return app


def test_organism_status_serializes_numpy_runtime_state() -> None:
    client = TestClient(_build_app())

    response = client.get("/organism/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["governance"]["trading_halted"] is False
    assert payload["policy_weights"]["alpha_breakout"] == 0.65
    assert payload["live_engine"]["running"] is True
    assert payload["live_engine"]["engine"]["ml_trained"] is True
    assert payload["live_engine"]["engine"]["universe_symbols"] == ["SPY", "QQQ"]


def test_organism_runs_serializes_numpy_runtime_state() -> None:
    client = TestClient(_build_app())

    response = client.get("/organism/runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["running"] is True
    assert payload["tick_interval_s"] == 15
    assert payload["runs"] == [
        {"timestamp": "2026-05-06T15:00:00Z", "orders": 0},
    ]
    assert payload["engine"]["initialized"] is True
