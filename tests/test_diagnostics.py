"""
Tests for the System Diagnostics Framework.

Reuses mock helpers from test_organism_integration_smoke.py.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from unittest.mock import AsyncMock

import numpy as np
import pandas as pd
import pytest

from backend.organism.diagnostics import (
    CheckCategory,
    CheckMode,
    CheckSeverity,
    DiagnosticEngine,
    DiagnosticReport,
    DiagnosticResult,
    diagnostics,
)


# ═══════════════════════════════════════════════════════════════════
#  Shared helpers (mirrors test_organism_integration_smoke.py)
# ═══════════════════════════════════════════════════════════════════

def _make_price_df(n: int = 300, base: float = 100.0, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.0005, 0.02, n)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0, 0.02, n))
    low = close * (1 - rng.uniform(0, 0.02, n))
    opn = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(100_000, 10_000_000, n).astype(float)
    return pd.DataFrame({"open": opn, "high": high, "low": low, "close": close, "volume": volume})


class MockDataClient:
    def __init__(self, data: dict[str, pd.DataFrame] | None = None):
        self._data = data or {}

    def get_historical_data(self, symbol, timeframe="1Day", limit=500):
        if symbol not in self._data:
            self._data[symbol] = _make_price_df(max(limit, 300))
        return self._data[symbol]


class MockPositionsService:
    def __init__(self, positions: dict | None = None):
        self.positions = positions or {}

    async def get_all_positions(self) -> dict:
        return dict(self.positions)

    async def get_total_portfolio_value(self) -> float:
        return 100_000.0

    async def get_buying_power(self) -> float:
        return 50_000.0


class MockOrderService:
    def __init__(self):
        self.submitted: list[dict] = []

    async def submit_symbol_order(self, **kwargs) -> dict:
        self.submitted.append(kwargs)
        return {"id": f"mock_{len(self.submitted)}", "status": "accepted"}


@pytest.fixture
def brain_dir(tmp_path):
    return str(tmp_path / "test_brain")


def _make_engine(
    data_client=None,
    order_service=None,
    positions_service=None,
    brain_dir="test_brain",
    universe=None,
):
    from backend.organism.live_engine import OrganismLiveEngine
    return OrganismLiveEngine(
        data_client=data_client or MockDataClient(),
        order_service=order_service or MockOrderService(),
        positions_service=positions_service or MockPositionsService(),
        brain_dir=brain_dir,
        universe=universe or ["AAPL", "MSFT", "SPY"],
    )


# ═══════════════════════════════════════════════════════════════════
#  Test: Preflight Diagnostics
# ═══════════════════════════════════════════════════════════════════

class TestPreflightDiagnostics:
    """Preflight checks catch wiring and config issues before first tick."""

    @pytest.mark.asyncio
    async def test_healthy_engine_passes_preflight(self, brain_dir):
        engine = _make_engine(brain_dir=brain_dir)
        await engine.initialize()

        # Import after engine init to ensure checks are registered
        import backend.organism.diagnostic_checks  # noqa: F401

        report = await diagnostics.run(CheckMode.PREFLIGHT, engine=engine)

        assert report.all_critical_passed, (
            f"Healthy engine should pass all critical checks. Failures: "
            f"{[(r.name, r.message) for r in report.results if not r.passed and r.severity == 'critical']}"
        )
        assert report.summary["total"] > 0

    @pytest.mark.asyncio
    async def test_none_order_service_caught(self, brain_dir):
        engine = _make_engine(brain_dir=brain_dir)
        engine._order_service = None
        await engine.initialize()

        import backend.organism.diagnostic_checks  # noqa: F401

        report = await diagnostics.run(CheckMode.PREFLIGHT, engine=engine)

        order_check = next(
            (r for r in report.results if r.name == "wiring_order_service"),
            None,
        )
        assert order_check is not None, "wiring_order_service check should be in results"
        assert not order_check.passed, "Should fail when order_service is None"
        assert order_check.severity == "critical"

    @pytest.mark.asyncio
    async def test_none_data_client_caught(self, brain_dir):
        engine = _make_engine(brain_dir=brain_dir)
        engine._data_client = None
        await engine.initialize()

        import backend.organism.diagnostic_checks  # noqa: F401

        report = await diagnostics.run(CheckMode.PREFLIGHT, engine=engine)

        dc_check = next(
            (r for r in report.results if r.name == "wiring_data_client"),
            None,
        )
        assert dc_check is not None
        assert not dc_check.passed
        assert dc_check.severity == "critical"


# ═══════════════════════════════════════════════════════════════════
#  Test: Deep Diagnostics
# ═══════════════════════════════════════════════════════════════════

class TestDeepDiagnostics:
    """Deep diagnostics catch runtime state issues."""

    @pytest.mark.asyncio
    async def test_shorts_detected_in_long_only(self, brain_dir, monkeypatch):
        monkeypatch.setenv("ORGANISM_LONG_ONLY", "true")

        # Reload the module-level constant
        import backend.organism.live_engine as le_mod
        orig = le_mod.LONG_ONLY
        monkeypatch.setattr(le_mod, "LONG_ONLY", True)

        positions = MockPositionsService({
            "COIN": {"qty": "-100", "avg_entry_price": "200.0", "side": "short"},
        })
        engine = _make_engine(
            brain_dir=brain_dir,
            positions_service=positions,
        )
        await engine.initialize()

        import backend.organism.diagnostic_checks  # noqa: F401

        report = await diagnostics.run(CheckMode.DEEP, engine=engine)

        short_check = next(
            (r for r in report.results if r.name == "order_long_only_no_shorts"),
            None,
        )
        assert short_check is not None
        assert not short_check.passed, "Should detect short positions in LONG_ONLY mode"

        monkeypatch.setattr(le_mod, "LONG_ONLY", orig)

    @pytest.mark.asyncio
    async def test_orphaned_exit_levels_flagged(self, brain_dir):
        engine = _make_engine(brain_dir=brain_dir)
        await engine.initialize()

        # Create an exit level with no matching broker position
        from backend.organism.adaptive_exits import ExitLevels
        engine._exit_levels["FAKE"] = ExitLevels(
            symbol="FAKE", direction=1.0, entry_price=100.0,
            stop_loss=95.0, take_profit=110.0, trailing_stop=97.0,
            atr_at_entry=2.0, regime_at_entry="unknown",
            highest_favorable=100.0,
        )
        engine._entry_metadata["FAKE"] = {"entry_price": 100.0}

        import backend.organism.diagnostic_checks  # noqa: F401

        report = await diagnostics.run(CheckMode.DEEP, engine=engine)

        orphan_check = next(
            (r for r in report.results if r.name == "broker_orphaned_exit_levels"),
            None,
        )
        assert orphan_check is not None
        assert not orphan_check.passed, "Should flag exit levels for non-existent positions"

    @pytest.mark.asyncio
    async def test_numpy_serialization_verified(self, brain_dir):
        import backend.organism.diagnostic_checks  # noqa: F401

        report = await diagnostics.run(CheckMode.DEEP, engine=None)

        numpy_check = next(
            (r for r in report.results if r.name == "data_numpy_json_serialization"),
            None,
        )
        assert numpy_check is not None
        assert numpy_check.passed, "numpy JSON serialization should pass"


# ═══════════════════════════════════════════════════════════════════
#  Test: Continuous Diagnostics
# ═══════════════════════════════════════════════════════════════════

class TestContinuousDiagnostics:
    """Continuous diagnostics check runtime state."""

    @pytest.mark.asyncio
    async def test_passes_after_init(self, brain_dir):
        engine = _make_engine(brain_dir=brain_dir)
        await engine.initialize()
        engine._tick_count = 10

        import backend.organism.diagnostic_checks  # noqa: F401

        report = await diagnostics.run(CheckMode.CONTINUOUS, engine=engine)

        assert report.all_critical_passed
        assert report.summary["total"] > 0

    @pytest.mark.asyncio
    async def test_negative_tick_count_caught(self, brain_dir):
        engine = _make_engine(brain_dir=brain_dir)
        await engine.initialize()
        engine._tick_count = -5

        import backend.organism.diagnostic_checks  # noqa: F401

        report = await diagnostics.run(CheckMode.CONTINUOUS, engine=engine)

        tick_check = next(
            (r for r in report.results if r.name == "state_tick_counter_integrity"),
            None,
        )
        assert tick_check is not None
        assert not tick_check.passed, "Should catch negative tick count"


# ═══════════════════════════════════════════════════════════════════
#  Test: Report Serialization
# ═══════════════════════════════════════════════════════════════════

class TestReportSerialization:
    """Report.to_dict() must produce JSON-serializable output."""

    def test_report_to_dict_is_json_serializable(self):
        report = DiagnosticReport(
            mode="preflight",
            timestamp="2026-02-24T12:00:00Z",
            results=[
                DiagnosticResult(
                    name="test_check",
                    category="wiring",
                    severity="critical",
                    passed=True,
                    message="All good",
                    duration_ms=1.5,
                ),
                DiagnosticResult(
                    name="test_fail",
                    category="order_flow",
                    severity="warning",
                    passed=False,
                    message="Something wrong",
                    duration_ms=0.3,
                ),
            ],
            duration_ms=5.0,
        )

        d = report.to_dict()
        serialized = json.dumps(d)
        assert serialized  # non-empty
        parsed = json.loads(serialized)
        assert parsed["mode"] == "preflight"
        assert parsed["all_critical_passed"] is True
        assert parsed["summary"]["total"] == 2
        assert parsed["summary"]["passed"] == 1
        assert parsed["summary"]["failed"] == 1
        assert len(parsed["results"]) == 2

    def test_all_critical_passed_property(self):
        report = DiagnosticReport(mode="deep", timestamp="now", results=[
            DiagnosticResult("a", "wiring", "critical", True, "ok"),
            DiagnosticResult("b", "wiring", "critical", False, "fail"),
            DiagnosticResult("c", "wiring", "warning", False, "warn"),
        ])
        assert not report.all_critical_passed

        report2 = DiagnosticReport(mode="deep", timestamp="now", results=[
            DiagnosticResult("a", "wiring", "critical", True, "ok"),
            DiagnosticResult("c", "wiring", "warning", False, "warn"),
        ])
        assert report2.all_critical_passed


# ═══════════════════════════════════════════════════════════════════
#  Test: DiagnosticEngine basics
# ═══════════════════════════════════════════════════════════════════

class TestDiagnosticEngine:
    """Unit tests for the engine registration and execution."""

    @pytest.mark.asyncio
    async def test_check_decorator_registers(self):
        eng = DiagnosticEngine()

        @eng.check(
            name="test_check",
            category=CheckCategory.WIRING,
            severity=CheckSeverity.INFO,
            modes={CheckMode.PREFLIGHT},
        )
        async def my_check(*, engine=None, app=None):
            return DiagnosticResult("test_check", "wiring", "info", True, "ok")

        report = await eng.run(CheckMode.PREFLIGHT)
        assert len(report.results) == 1
        assert report.results[0].passed

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        eng = DiagnosticEngine()

        @eng.check(
            name="slow_check",
            category=CheckCategory.WIRING,
            severity=CheckSeverity.WARNING,
            modes={CheckMode.PREFLIGHT},
            timeout=0.1,
        )
        async def slow_check(*, engine=None, app=None):
            await asyncio.sleep(5)
            return DiagnosticResult("slow_check", "wiring", "warning", True, "done")

        report = await eng.run(CheckMode.PREFLIGHT)
        assert len(report.results) == 1
        assert not report.results[0].passed
        assert "Timed out" in report.results[0].message

    @pytest.mark.asyncio
    async def test_exception_safety(self):
        eng = DiagnosticEngine()

        @eng.check(
            name="crashing_check",
            category=CheckCategory.WIRING,
            severity=CheckSeverity.CRITICAL,
            modes={CheckMode.PREFLIGHT},
        )
        async def crashing(*, engine=None, app=None):
            raise RuntimeError("boom")

        report = await eng.run(CheckMode.PREFLIGHT)
        assert len(report.results) == 1
        assert not report.results[0].passed
        assert "boom" in report.results[0].message

    @pytest.mark.asyncio
    async def test_mode_filtering(self):
        eng = DiagnosticEngine()

        @eng.check(
            name="preflight_only",
            category=CheckCategory.WIRING,
            severity=CheckSeverity.INFO,
            modes={CheckMode.PREFLIGHT},
        )
        async def pf(*, engine=None, app=None):
            return DiagnosticResult("preflight_only", "wiring", "info", True, "ok")

        @eng.check(
            name="deep_only",
            category=CheckCategory.WIRING,
            severity=CheckSeverity.INFO,
            modes={CheckMode.DEEP},
        )
        async def dp(*, engine=None, app=None):
            return DiagnosticResult("deep_only", "wiring", "info", True, "ok")

        pf_report = await eng.run(CheckMode.PREFLIGHT)
        assert len(pf_report.results) == 1
        assert pf_report.results[0].name == "preflight_only"

        deep_report = await eng.run(CheckMode.DEEP)
        assert len(deep_report.results) == 1
        assert deep_report.results[0].name == "deep_only"
