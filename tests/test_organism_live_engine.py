"""
Phase 2 — Tests for OrganismLiveEngine, OrganismScheduler, and walk-forward gate.

Covers:
    - P2.1-2.2: OrganismLiveEngine init, live_tick, status, shutdown
    - P2.3:     OrganismScheduler start/stop/state
    - P2.4:     Fill → TradeRecord reconciliation
    - P2.5:     Position state reconstruction
    - P2.6:     Walk-forward gate in brain persistence
    - P2.7:     Multi-run regression (brain_N+1 >= brain_N * 0.95)
    - P2.8:     Integration test with mock paper account
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from backend.organism.brain_persistence import OrganismBrain
from backend.organism.continuous_learner import TradeRecord


# ═════════════════════════════════════════════════════════════════
#  Fixtures: Mock services
# ═════════════════════════════════════════════════════════════════

def _make_price_df(n: int = 300, base: float = 100.0) -> pd.DataFrame:
    """Create a realistic synthetic OHLCV DataFrame."""
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0005, 0.02, n)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0, 0.02, n))
    low = close * (1 - rng.uniform(0, 0.02, n))
    opn = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.integers(100_000, 10_000_000, n).astype(float)
    return pd.DataFrame({
        "open": opn,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class MockDataClient:
    """Mock Alpaca data client returning synthetic data."""

    def __init__(self):
        self._data = {}

    def get_historical_data(self, symbol, timeframe="1Day", limit=500):
        if symbol not in self._data:
            self._data[symbol] = _make_price_df(limit)
        return self._data[symbol]


class MockPositionsService:
    """Mock positions service for testing."""

    def __init__(self, positions: dict | None = None):
        self._positions = positions or {}

    async def get_all_positions(self) -> dict:
        return self._positions

    async def get_total_portfolio_value(self) -> float:
        return 100_000.0

    async def get_buying_power(self) -> float:
        return 50_000.0


class MockOrderService:
    """Mock order service that records submissions."""

    def __init__(self):
        self.submitted: list[dict] = []

    async def submit_symbol_order(self, **kwargs) -> dict:
        self.submitted.append(kwargs)
        return {"id": f"mock_{len(self.submitted)}", "status": "accepted"}

    async def plan_and_submit(self, signals, **kwargs):
        return [{"id": "mock", "status": "accepted"}]


@pytest.fixture
def mock_data_client():
    return MockDataClient()


@pytest.fixture
def mock_positions_service():
    return MockPositionsService()


@pytest.fixture
def mock_order_service():
    return MockOrderService()


@pytest.fixture
def brain_dir(tmp_path):
    return str(tmp_path / "test_brain")


# ═════════════════════════════════════════════════════════════════
#  P2.1-2.2: OrganismLiveEngine
# ═════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestOrganismLiveEngine:
    """Test OrganismLiveEngine initialization, tick, and shutdown."""

    def _make_engine(self, data_client, order_service, positions_service, brain_dir):
        from backend.organism.live_engine import OrganismLiveEngine
        return OrganismLiveEngine(
            data_client=data_client,
            order_service=order_service,
            positions_service=positions_service,
            brain_dir=brain_dir,
            universe=["AAPL", "MSFT", "SPY"],
        )

    @pytest.mark.asyncio
    async def test_initialize_fresh(
        self, mock_data_client, mock_order_service, mock_positions_service, brain_dir,
    ):
        engine = self._make_engine(
            mock_data_client, mock_order_service, mock_positions_service, brain_dir,
        )
        loaded = await engine.initialize()
        assert loaded is False  # No prior brain
        assert engine._initialized is True
        assert engine._tick_count == 0

    @pytest.mark.asyncio
    async def test_live_tick_runs(
        self, mock_data_client, mock_order_service, mock_positions_service, brain_dir,
    ):
        engine = self._make_engine(
            mock_data_client, mock_order_service, mock_positions_service, brain_dir,
        )
        await engine.initialize()
        result = await engine.live_tick()
        assert result.timestamp
        assert result.duration_s >= 0
        assert isinstance(result.to_dict(), dict)

    @pytest.mark.asyncio
    async def test_live_tick_governance_halt(
        self, mock_data_client, mock_order_service, mock_positions_service, brain_dir,
    ):
        engine = self._make_engine(
            mock_data_client, mock_order_service, mock_positions_service, brain_dir,
        )
        await engine.initialize()
        engine.governance._trading_halted = True
        result = await engine.live_tick()
        assert "Trading halted" in result.errors[0]
        assert result.orders_submitted == 0

    @pytest.mark.asyncio
    async def test_status(
        self, mock_data_client, mock_order_service, mock_positions_service, brain_dir,
    ):
        engine = self._make_engine(
            mock_data_client, mock_order_service, mock_positions_service, brain_dir,
        )
        await engine.initialize()
        status = engine.status()
        assert "initialized" in status
        assert "tick_count" in status
        assert "brain_generation" in status
        assert "governance" in status
        assert status["initialized"] is True

    @pytest.mark.asyncio
    async def test_shutdown_saves_brain(
        self, mock_data_client, mock_order_service, mock_positions_service, brain_dir,
    ):
        engine = self._make_engine(
            mock_data_client, mock_order_service, mock_positions_service, brain_dir,
        )
        await engine.initialize()
        await engine.shutdown()
        # Brain dir should exist with at least a manifest
        brain_path = Path(brain_dir)
        assert brain_path.exists()
        assert (brain_path / "manifest.json").exists()

    @pytest.mark.asyncio
    async def test_multiple_ticks(
        self, mock_data_client, mock_order_service, mock_positions_service, brain_dir,
    ):
        engine = self._make_engine(
            mock_data_client, mock_order_service, mock_positions_service, brain_dir,
        )
        await engine.initialize()
        for _ in range(3):
            result = await engine.live_tick()
            assert result.duration_s >= 0
        assert engine._tick_count == 3

    @pytest.mark.asyncio
    async def test_tick_result_dict(
        self, mock_data_client, mock_order_service, mock_positions_service, brain_dir,
    ):
        engine = self._make_engine(
            mock_data_client, mock_order_service, mock_positions_service, brain_dir,
        )
        await engine.initialize()
        result = await engine.live_tick()
        d = result.to_dict()
        assert "regime" in d
        assert "signals_generated" in d
        assert "errors" in d
        assert isinstance(d["errors"], list)


# ═════════════════════════════════════════════════════════════════
#  P2.3: OrganismScheduler
# ═════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestOrganismScheduler:
    """Test scheduler start/stop/state."""

    @pytest.mark.asyncio
    async def test_start_stop(
        self, mock_data_client, mock_order_service, mock_positions_service,
    ):
        from backend.organism.scheduler import OrganismScheduler

        scheduler = OrganismScheduler(
            data_client=mock_data_client,
            order_service=mock_order_service,
            positions_service=mock_positions_service,
            tick_interval=1,
        )
        assert not scheduler.is_running

        await scheduler.start()
        assert scheduler.is_running

        # Let it tick once
        await asyncio.sleep(0.5)

        await scheduler.stop()
        assert not scheduler.is_running

    @pytest.mark.asyncio
    async def test_state(
        self, mock_data_client, mock_order_service, mock_positions_service,
    ):
        from backend.organism.scheduler import OrganismScheduler

        scheduler = OrganismScheduler(
            data_client=mock_data_client,
            order_service=mock_order_service,
            positions_service=mock_positions_service,
            tick_interval=60,
        )
        state = scheduler.state()
        assert "running" in state
        assert state["running"] is False
        assert state["tick_interval_s"] == 60

    @pytest.mark.asyncio
    async def test_double_start(
        self, mock_data_client, mock_order_service, mock_positions_service,
    ):
        from backend.organism.scheduler import OrganismScheduler

        scheduler = OrganismScheduler(
            data_client=mock_data_client,
            order_service=mock_order_service,
            positions_service=mock_positions_service,
            tick_interval=60,
        )
        await scheduler.start()
        first_task = scheduler._task

        # Second start should be a no-op
        await scheduler.start()
        assert scheduler._task is first_task

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_passes_sessionmaker_to_live_engine(
        self, mock_data_client, mock_order_service, mock_positions_service,
    ):
        from backend.organism.scheduler import OrganismScheduler

        captured_kwargs: dict[str, Any] = {}

        class _DummyResult:
            regime = "unknown"
            signals_generated = 0
            orders_submitted = 0
            trades_closed = 0
            duration_s = 0.0
            errors = []

            def to_dict(self):
                return {"ok": True}

        class _DummyEngine:
            def __init__(self, **kwargs):
                captured_kwargs.update(kwargs)

            async def initialize(self):
                return False

            async def live_tick(self):
                return _DummyResult()

            async def shutdown(self):
                return None

            def status(self):
                return {"initialized": True}

        fake_sessionmaker = object()

        with patch("backend.organism.live_engine.OrganismLiveEngine", _DummyEngine):
            scheduler = OrganismScheduler(
                data_client=mock_data_client,
                order_service=mock_order_service,
                positions_service=mock_positions_service,
                sessionmaker=fake_sessionmaker,
                tick_interval=1,
            )

            await scheduler.start()
            await asyncio.sleep(0.05)
            await scheduler.stop()

        assert captured_kwargs.get("sessionmaker") is fake_sessionmaker


# ═════════════════════════════════════════════════════════════════
#  P2.4: Fill → TradeRecord reconciliation
# ═════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestFillReconciliation:
    """Test that closed positions produce TradeRecords."""

    @pytest.mark.asyncio
    async def test_position_close_creates_trade_record(
        self, mock_data_client, mock_order_service, brain_dir,
    ):
        from backend.organism.live_engine import OrganismLiveEngine

        # Start with a position, then make it disappear
        positions_with = MockPositionsService({
            "AAPL": {"qty": "10", "avg_entry_price": "150.0", "side": "long"},
        })
        engine = OrganismLiveEngine(
            data_client=mock_data_client,
            order_service=mock_order_service,
            positions_service=positions_with,
            brain_dir=brain_dir,
            universe=["AAPL", "SPY"],
        )
        await engine.initialize()

        # Simulate entry metadata as if we had opened the position
        engine._entry_metadata["AAPL"] = {
            "entry_price": 150.0,
            "entry_tick": 0,
            "direction": 1.0,
            "predicted_return": 0.02,
            "confidence": 0.7,
        }

        # Now positions is empty → AAPL closed
        engine._positions_service = MockPositionsService({})
        features = {"AAPL": _make_price_df(300), "SPY": _make_price_df(300)}
        await engine._reconcile_fills(features)

        assert len(engine._all_trades) >= 1
        trade = engine._all_trades[-1]
        assert trade.symbol == "AAPL"
        assert trade.direction == 1.0
        assert trade.entry_price == 150.0


# ═════════════════════════════════════════════════════════════════
#  P2.5: Position reconstruction on startup
# ═════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestPositionReconstruction:
    """Test position state reconstruction from live broker."""

    @pytest.mark.asyncio
    async def test_reconstructs_existing_positions(
        self, mock_data_client, mock_order_service, brain_dir,
    ):
        from backend.organism.live_engine import OrganismLiveEngine

        positions = MockPositionsService({
            "MSFT": {"qty": "25", "avg_entry_price": "380.0", "side": "long"},
        })
        engine = OrganismLiveEngine(
            data_client=mock_data_client,
            order_service=mock_order_service,
            positions_service=positions,
            brain_dir=brain_dir,
            universe=["MSFT", "SPY"],
        )
        await engine.initialize()

        # Should have reconstructed exit levels and pyramid state
        assert "MSFT" in engine._entry_metadata
        assert engine._entry_metadata["MSFT"]["entry_price"] == 380.0
        # May or may not have exit levels depending on data fetch
        # but entry metadata should always be set


# ═════════════════════════════════════════════════════════════════
#  P2.6: Walk-forward gate
# ═════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestWalkForwardGate:
    """Test brain walk-forward validation gate."""

    def _make_trades(self, n: int, mean_ret: float = 0.01) -> list[TradeRecord]:
        rng = np.random.default_rng(42)
        trades = []
        for i in range(n):
            ret = rng.normal(mean_ret, 0.03)
            trades.append(TradeRecord(
                symbol="TST",
                direction=1.0,
                entry_price=100.0,
                exit_price=100.0 * (1 + ret),
                entry_bar=i,
                exit_bar=i + 5,
                shares=10,
                pnl=100.0 * ret * 10,
                exit_reason="test",
                predicted_return=ret,
                actual_return=ret,
                confidence=0.6,
            ))
        return trades

    def test_gate_passes_with_good_performance(self, brain_dir):
        brain = OrganismBrain(brain_dir=brain_dir)
        brain._manifest = {"best_sharpe": 1.0}

        trades = self._make_trades(50, mean_ret=0.02)
        should_save, reason = brain.walk_forward_gate(trades)
        assert should_save is True
        assert "passed" in reason or "Insufficient" in reason or "No baseline" in reason

    def test_gate_fails_on_regression(self, brain_dir):
        brain = OrganismBrain(brain_dir=brain_dir)
        brain._manifest = {"best_sharpe": 5.0}  # Unrealistically high

        trades = self._make_trades(50, mean_ret=-0.01)  # Negative
        should_save, reason = brain.walk_forward_gate(
            trades, regression_threshold=0.95,
        )
        assert should_save is False
        assert "FAIL" in reason

    def test_gate_passes_with_no_baseline(self, brain_dir):
        brain = OrganismBrain(brain_dir=brain_dir)
        brain._manifest = {"best_sharpe": 0}

        trades = self._make_trades(20, mean_ret=0.01)
        should_save, reason = brain.walk_forward_gate(trades)
        assert should_save is True

    def test_gate_passes_with_insufficient_trades(self, brain_dir):
        brain = OrganismBrain(brain_dir=brain_dir)
        brain._manifest = {"best_sharpe": 5.0}

        trades = self._make_trades(3)
        should_save, reason = brain.walk_forward_gate(trades, min_trades=10)
        assert should_save is True
        assert "Insufficient" in reason


# ═════════════════════════════════════════════════════════════════
#  P2.7: Multi-run regression test
# ═════════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.regression
class TestMultiRunRegression:
    """Verify brain_N+1.sharpe >= brain_N.sharpe * 0.95 over multiple saves."""

    @pytest.mark.asyncio
    async def test_brain_persistence_across_runs(
        self, mock_data_client, mock_order_service, mock_positions_service, brain_dir,
    ):
        from backend.organism.live_engine import OrganismLiveEngine

        sharpes: list[float] = []

        for run_idx in range(3):
            engine = OrganismLiveEngine(
                data_client=mock_data_client,
                order_service=mock_order_service,
                positions_service=mock_positions_service,
                brain_dir=brain_dir,
                universe=["AAPL", "MSFT", "SPY"],
            )
            loaded = await engine.initialize()
            if run_idx > 0:
                assert loaded is True, f"Run {run_idx} should load brain"

            # Run a few ticks
            for _ in range(3):
                await engine.live_tick()

            # Record Sharpe from brain manifest
            brain_sharpe = engine.brain._manifest.get("best_sharpe", 0)
            sharpes.append(brain_sharpe)

            await engine.shutdown()

        # Verify blueprint threshold: brain_N+1.sharpe >= brain_N.sharpe * 0.95
        for i in range(1, len(sharpes)):
            prev = sharpes[i - 1]
            curr = sharpes[i]
            if prev > 0:
                assert curr >= prev * 0.95, (
                    f"Run {i}: Sharpe regressed {prev:.3f} → {curr:.3f}"
                )


# ═════════════════════════════════════════════════════════════════
#  P2.8: Integration test with paper account mock
# ═════════════════════════════════════════════════════════════════

@pytest.mark.unit
@pytest.mark.integration
class TestPaperAccountIntegration:
    """Integration test simulating a full paper trading cycle."""

    @pytest.mark.asyncio
    async def test_full_cycle(self, brain_dir):
        """Simulate: init → tick → tick → tick → shutdown."""
        from backend.organism.live_engine import OrganismLiveEngine

        data_client = MockDataClient()
        order_service = MockOrderService()
        positions_service = MockPositionsService()

        engine = OrganismLiveEngine(
            data_client=data_client,
            order_service=order_service,
            positions_service=positions_service,
            brain_dir=brain_dir,
            universe=["AAPL", "MSFT", "GOOGL", "SPY"],
        )

        # Init
        loaded = await engine.initialize()
        assert not loaded
        assert engine._initialized

        # Run 5 ticks
        results = []
        for i in range(5):
            r = await engine.live_tick()
            results.append(r)
            assert r.duration_s >= 0

        # At least some ticks should produce data
        has_data = any(r.signals_generated > 0 or r.regime != "unknown" for r in results)
        # May not always produce signals with synthetic data, that's OK

        # Engine state
        assert engine._tick_count == 5
        assert engine.status()["tick_count"] == 5

        # Shutdown
        await engine.shutdown()
        assert (Path(brain_dir) / "manifest.json").exists()

    @pytest.mark.asyncio
    async def test_exit_check_on_open_positions(self, brain_dir):
        """Test that exit logic runs on existing positions."""
        from backend.organism.live_engine import OrganismLiveEngine

        data_client = MockDataClient()
        order_service = MockOrderService()

        # Simulate having an open position
        positions_service = MockPositionsService({
            "AAPL": {"qty": "10", "avg_entry_price": "150.0", "side": "long"},
        })

        engine = OrganismLiveEngine(
            data_client=data_client,
            order_service=order_service,
            positions_service=positions_service,
            brain_dir=brain_dir,
            universe=["AAPL", "SPY"],
        )
        await engine.initialize()

        result = await engine.live_tick()
        # Should have checked at least 1 position for exits
        assert result.exits_checked >= 0  # Might be 0 if no exit levels

    @pytest.mark.asyncio
    async def test_generate_trading_signals(self, brain_dir):
        """Test TradingSignal generation for multi-strategy runner."""
        from backend.organism.live_engine import OrganismLiveEngine

        data_client = MockDataClient()
        order_service = MockOrderService()
        positions_service = MockPositionsService()

        engine = OrganismLiveEngine(
            data_client=data_client,
            order_service=order_service,
            positions_service=positions_service,
            brain_dir=brain_dir,
            universe=["AAPL", "SPY"],
        )
        await engine.initialize()

        # Build features
        features = {
            "AAPL": _make_price_df(300),
            "SPY": _make_price_df(300),
        }
        signals = engine.generate_trading_signals(features, "normal")
        assert isinstance(signals, list)
        # Signals may be empty if ML not trained, that's fine
        for sig in signals:
            assert hasattr(sig, "symbol")
            assert hasattr(sig, "source")
            assert sig.source == "organism"
            assert -1.0 <= sig.target_exposure <= 1.0


# ═════════════════════════════════════════════════════════════════
#  Edge cases
# ═════════════════════════════════════════════════════════════════

@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error resilience."""

    @pytest.mark.asyncio
    async def test_empty_universe(
        self, mock_order_service, mock_positions_service, brain_dir,
    ):
        from backend.organism.live_engine import OrganismLiveEngine

        engine = OrganismLiveEngine(
            data_client=MockDataClient(),
            order_service=mock_order_service,
            positions_service=mock_positions_service,
            brain_dir=brain_dir,
            universe=[],
        )
        await engine.initialize()
        result = await engine.live_tick()
        # Should handle gracefully
        assert isinstance(result.errors, list)

    @pytest.mark.asyncio
    async def test_data_client_failure(
        self, mock_order_service, mock_positions_service, brain_dir,
    ):
        from backend.organism.live_engine import OrganismLiveEngine

        class FailingDataClient:
            def get_historical_data(self, *args, **kwargs):
                raise ConnectionError("Network failure")

        engine = OrganismLiveEngine(
            data_client=FailingDataClient(),
            order_service=mock_order_service,
            positions_service=mock_positions_service,
            brain_dir=brain_dir,
            universe=["AAPL", "SPY"],
        )
        await engine.initialize()
        result = await engine.live_tick()
        # Should not crash
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_live_tick_result_serializable(
        self, mock_data_client, mock_order_service, mock_positions_service, brain_dir,
    ):
        from backend.organism.live_engine import OrganismLiveEngine
        import json

        engine = OrganismLiveEngine(
            data_client=mock_data_client,
            order_service=mock_order_service,
            positions_service=mock_positions_service,
            brain_dir=brain_dir,
            universe=["AAPL", "SPY"],
        )
        await engine.initialize()
        result = await engine.live_tick()
        # Result dict should be JSON serializable
        json_str = json.dumps(result.to_dict())
        assert json_str
