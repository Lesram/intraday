"""Audit 2026-06-09 finding 3.1 — multi-strategy live path hardening.

Verifies:
1. POST /multi-strategy-live/* requires admin auth (router-level dependency).
2. MultiStrategyLiveRunner.run_once honors the governance kill switch
   (instance state, env fallback, and fail-closed on unreadable state).
3. Both production call sites (HTTP route + scheduler) pass governance in.
"""

import inspect

import pytest

from backend.services.multi_strategy_live_runner import (
    MultiStrategyLiveRunner,
    MultiStrategyRunResult,
)


class _HaltedGovernance:
    is_trading_halted = True


class _ActiveGovernance:
    is_trading_halted = False


class _BrokenGovernance:
    @property
    def is_trading_halted(self):
        raise RuntimeError("governance state unreadable")


class _ExplodingOrderService:
    """Fails the test if any order submission is attempted."""

    async def plan_and_submit(self, *a, **k):
        raise AssertionError("plan_and_submit must not be called while halted")


class _ExplodingDataClient:
    async def get_historical_data(self, *a, **k):
        raise AssertionError("no data should be fetched while halted")


# ── 1. Auth ───────────────────────────────────────────────────────────


def test_router_requires_admin_dependency():
    from backend.api.routes import multi_strategy_live as mod
    from backend.infra.security import require_admin

    dep_calls = mod.router.dependencies
    assert dep_calls, "multi-strategy-live router must have auth dependencies"
    assert any(
        getattr(d, "dependency", None) is require_admin for d in dep_calls
    ), "multi-strategy-live router must depend on require_admin"


# ── 2. Kill switch in the runner ─────────────────────────────────────


@pytest.mark.asyncio
async def test_run_once_blocked_when_governance_halted():
    runner = MultiStrategyLiveRunner()
    result = await runner.run_once(
        symbols=["AAPL"],
        data_client=_ExplodingDataClient(),
        order_service=_ExplodingOrderService(),
        governance=_HaltedGovernance(),
    )
    assert isinstance(result, MultiStrategyRunResult)
    assert result.submitted == []
    assert result.engine_signals_count == 0


@pytest.mark.asyncio
async def test_run_once_blocked_by_env_fallback(monkeypatch):
    monkeypatch.setenv("ORGANISM_HALT_TRADING", "1")
    runner = MultiStrategyLiveRunner()
    result = await runner.run_once(
        symbols=["AAPL"],
        data_client=_ExplodingDataClient(),
        order_service=_ExplodingOrderService(),
        governance=None,
    )
    assert result.submitted == []
    assert result.engine_signals_count == 0


@pytest.mark.asyncio
async def test_run_once_fails_closed_on_unreadable_governance(monkeypatch):
    monkeypatch.delenv("ORGANISM_HALT_TRADING", raising=False)
    runner = MultiStrategyLiveRunner()
    result = await runner.run_once(
        symbols=["AAPL"],
        data_client=_ExplodingDataClient(),
        order_service=_ExplodingOrderService(),
        governance=_BrokenGovernance(),
    )
    assert result.submitted == []


def test_halt_check_inactive_when_not_halted(monkeypatch):
    monkeypatch.delenv("ORGANISM_HALT_TRADING", raising=False)
    assert MultiStrategyLiveRunner._halted_by_governance(_ActiveGovernance()) is False
    assert MultiStrategyLiveRunner._halted_by_governance(None) is False
    assert MultiStrategyLiveRunner._halted_by_governance(_HaltedGovernance()) is True


# ── 3. Call sites pass governance (structural guard) ────────────────


def test_route_passes_governance_to_runner():
    from backend.api.routes import multi_strategy_live as mod

    src = inspect.getsource(mod.run_multi_strategy_once)
    assert "organism_governance" in src, (
        "HTTP route must pass app.state.organism_governance into run_once"
    )


def test_scheduler_passes_governance_to_runner():
    from backend.services import multi_strategy_live_scheduler as mod

    src = inspect.getsource(mod)
    assert "governance=getattr(app.state, \"organism_governance\"" in src, (
        "scheduler must pass app.state.organism_governance into run_once"
    )
