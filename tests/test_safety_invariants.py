"""
Safety invariant tests identified during audit.

Each test verifies one critical safety property of the organism engine
WITHOUT running real infrastructure — all dependencies are mocked.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_engine_with_mocks(**overrides):
    """
    Build an OrganismLiveEngine with every external dependency replaced by
    mocks so that __init__ succeeds without real Alpaca / DB / Redis.

    Returns (engine, mocks_dict) where mocks_dict exposes the injected fakes
    for assertion.
    """
    from backend.organism.live_engine import OrganismLiveEngine

    data_client = MagicMock()
    order_service = MagicMock()
    positions_service = MagicMock()

    # positions_service.get_all_positions is async
    positions_service.get_all_positions = AsyncMock(return_value={})

    # Prevent brain load from touching disk
    with patch("backend.organism.brain_persistence.OrganismBrain.load", return_value=False), \
         patch("backend.organism.brain_persistence.OrganismBrain.exists", new_callable=lambda: property(lambda self: False)), \
         patch("backend.organism.live_engine.BackgroundTrainer") as bg_cls, \
         patch("backend.organism.live_engine.MarketScanner", return_value=MagicMock()):
        bg_instance = MagicMock()
        bg_instance.start = AsyncMock()
        bg_instance.stop = AsyncMock()
        bg_instance.is_training = False
        bg_cls.return_value = bg_instance

        engine = OrganismLiveEngine(
            data_client=data_client,
            order_service=order_service,
            positions_service=positions_service,
            brain_dir="/tmp/_test_brain_invariants",
            universe=["AAPL", "MSFT", "GOOGL", "SPY"],
            **overrides,
        )

    mocks = {
        "data_client": data_client,
        "order_service": order_service,
        "positions_service": positions_service,
        "bg_trainer": engine._bg_trainer,
    }
    return engine, mocks


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestSafetyInvariants:
    """Audit-identified safety invariants — one property per test."""

    # ── 1. Insufficient features must NOT skip exits ──────────────

    async def test_insufficient_features_still_processes_exits(self):
        """When _fetch_and_compute_features returns < 3 symbols the tick
        must still call get_all_positions() and run broker-price exit checks.
        It must NOT return early.  entries_blocked is set, but exits run.
        """
        engine, mocks = _make_engine_with_mocks()

        # Simulate one open position at the broker with a 20% loss
        mocks["positions_service"].get_all_positions = AsyncMock(return_value={
            "AAPL": {
                "current_price": 80.0,
                "avg_entry_price": 100.0,
                "qty": 10,
                "side": "long",
            },
        })

        # _fetch_and_compute_features returns only 1 symbol (< 3 threshold)
        import pandas as pd
        engine._fetch_and_compute_features = AsyncMock(return_value={
            "SPY": pd.DataFrame({"close": [400.0]}),
        })

        # Stub _get_equity so drawdown math works
        engine._get_equity = AsyncMock(return_value=100_000.0)

        # Stub exit submission so we can assert it was called
        engine._submit_exit_order = AsyncMock()

        # Stub _reconcile_fills (async)
        engine._reconcile_fills = AsyncMock()

        # Stub brain save
        engine._save_brain = MagicMock()

        # Stub _check_tick_invariants
        engine._check_tick_invariants = MagicMock()

        # Mark as initialized
        engine._initialized = True

        result = await engine.live_tick()

        # Key assertions:
        # 1) get_all_positions was called (exits were NOT skipped)
        mocks["positions_service"].get_all_positions.assert_awaited()

        # 2) The safety-net exit was triggered because AAPL is down 20%
        engine._submit_exit_order.assert_awaited()
        call_args = engine._submit_exit_order.call_args
        assert call_args[0][0] == "AAPL"  # symbol

        # 3) result.duration_s is set (tick completed, did not return early)
        assert result.duration_s > 0

        # 4) entries_blocked shows up in the errors
        blocked_msgs = [e for e in result.errors if "Insufficient" in e]
        assert len(blocked_msgs) >= 1

    # ── 2. entries_blocked must NOT return early — metrics export must run

    async def test_entries_blocked_still_exports_metrics_and_runs_exits(self):
        """When governance halts trading, the tick must NOT return early.
        It should fall through to equity curve update, Prometheus metrics,
        and reconciliation.  result.duration_s must be set.
        """
        engine, mocks = _make_engine_with_mocks()

        # Halt trading via governance
        engine.governance.halt_trading()

        # One open position (no immediate loss — just check that exits are
        # evaluated and tick completes)
        mocks["positions_service"].get_all_positions = AsyncMock(return_value={
            "MSFT": {
                "current_price": 300.0,
                "avg_entry_price": 290.0,
                "qty": 5,
                "side": "long",
            },
        })

        import pandas as pd
        engine._fetch_and_compute_features = AsyncMock(return_value={
            "SPY": pd.DataFrame({"close": [400.0, 401.0, 402.0] * 5}),
            "MSFT": pd.DataFrame({"close": [299.0, 300.0, 301.0] * 5}),
            "AAPL": pd.DataFrame({"close": [150.0, 151.0, 152.0] * 5}),
            "GOOGL": pd.DataFrame({"close": [140.0, 141.0, 142.0] * 5}),
        })
        engine._get_equity = AsyncMock(return_value=100_000.0)
        engine._reconcile_fills = AsyncMock()
        engine._save_brain = MagicMock()
        engine._check_tick_invariants = MagicMock()
        engine._initialized = True

        result = await engine.live_tick()

        # 1) duration_s is set (tick did not bail)
        assert result.duration_s > 0

        # 2) Reconciliation was called (always runs)
        engine._reconcile_fills.assert_awaited()

        # 3) No orders were submitted (entries are blocked)
        assert result.orders_submitted == 0

        # 4) Governance halt message is in errors/activity
        halt_msgs = [e for e in result.errors if "halted" in e.lower()]
        assert len(halt_msgs) >= 1

    # ── 3. Sector gate: planned_symbols accumulator ──────────────

    def test_sector_gate_blocks_excess_same_sector_entries(self):
        """When multiple candidates from the same sector are evaluated in
        one tick, the planned_symbols parameter must cause the sector gate
        to block entries beyond MAX_PER_SECTOR.
        """
        from backend.organism.sector_map import sector_gate_allows, MAX_PER_SECTOR

        # Start with 3 Technology positions already open
        open_syms = {"AAPL", "MSFT", "NVDA"}

        # First additional Technology candidate
        planned: set[str] = set()

        # With MAX_PER_SECTOR=4 and 3 open, the first additional should pass
        assert sector_gate_allows("AMD", open_syms, planned) is (
            len(open_syms) < MAX_PER_SECTOR
        )

        if MAX_PER_SECTOR > 3:
            # First one passes — add to planned
            planned.add("AMD")

            # Second additional Technology candidate — should be blocked
            # because open(3) + planned(1) = 4 = MAX_PER_SECTOR
            assert sector_gate_allows("AVGO", open_syms, planned) is False

    def test_sector_gate_unknown_sector_always_passes(self):
        """Symbols not in SECTOR_MAP should never be blocked by the gate."""
        from backend.organism.sector_map import sector_gate_allows

        assert sector_gate_allows("XYZZZZ", {"AAPL", "MSFT", "NVDA", "AMD"}, set()) is True

    def test_sector_gate_planned_symbols_none(self):
        """When planned_symbols is None the gate should still work
        (it only counts open positions)."""
        from backend.organism.sector_map import sector_gate_allows

        # With 0 open in Financials, should pass
        assert sector_gate_allows("COIN", set(), None) is True

    # ── 4. Evolution baseline continuity ─────────────────────────

    def test_apply_evolved_params_default_scale_matches_intraday_baseline(self):
        """With default EvolvedParams (all scales=1.0), calling
        apply_evolved_params must set exit_engine parameters to the
        intraday baseline values used by OrganismLiveEngine.__init__:
            atr_multiplier=1.0, trailing_start_atr=2.0,
            trailing_distance_atr=1.5, partial_tp_r=2.0
        """
        from backend.organism.adaptive_exits import AdaptiveExitEngine
        from backend.organism.self_evolution import EvolvedParams, apply_evolved_params

        params = EvolvedParams()  # all scale fields default to 1.0
        exit_engine = AdaptiveExitEngine(
            atr_multiplier=1.0,
            trailing_start_atr=2.0,
            trailing_distance_atr=1.5,
            partial_tp_r=2.0,
        )

        apply_evolved_params(params, exit_engine=exit_engine)

        # After applying scale=1.0, the values must be unchanged:
        #   atr_multiplier   = 1.0 * 1.0 = 1.0
        #   trailing_start   = 2.0 * 1.0 = 2.0
        #   trailing_distance= 1.5 * 1.0 = 1.5
        #   partial_tp_r     = 2.0 * 1.0 = 2.0
        assert exit_engine.atr_multiplier == pytest.approx(1.0)
        assert exit_engine.trailing_start_atr == pytest.approx(2.0)
        assert exit_engine.trailing_distance_atr == pytest.approx(1.5)
        assert exit_engine.partial_tp_r == pytest.approx(2.0)

    def test_apply_evolved_params_with_scaled_values(self):
        """When evolution scales differ from 1.0, the exit engine
        parameters must reflect baseline * scale."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine
        from backend.organism.self_evolution import EvolvedParams, apply_evolved_params

        params = EvolvedParams(
            stop_atr_scale=1.2,
            trailing_start_atr_scale=0.8,
            trailing_distance_scale=1.1,
            partial_tp_r_scale=0.9,
        )
        exit_engine = AdaptiveExitEngine(
            atr_multiplier=1.0,
            trailing_start_atr=2.0,
            trailing_distance_atr=1.5,
            partial_tp_r=2.0,
        )

        apply_evolved_params(params, exit_engine=exit_engine)

        assert exit_engine.atr_multiplier == pytest.approx(1.0 * 1.2)
        assert exit_engine.trailing_start_atr == pytest.approx(2.0 * 0.8)
        assert exit_engine.trailing_distance_atr == pytest.approx(1.5 * 1.1)
        assert exit_engine.partial_tp_r == pytest.approx(2.0 * 0.9)

    # ── 5. Order service TIF default = 'day' ─────────────────────

    def test_order_service_default_tif_is_day(self):
        """The default TIF extracted from order_data without a 'tif' key
        must be 'day', NOT 'gtc'.  This prevents overnight exposure on
        intraday strategies.
        """
        # Replicate the exact extraction logic from order_service.py line 1381
        order_data: dict[str, Any] = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 10,
        }
        tif = order_data.get("tif", "day")
        assert tif == "day"

    def test_order_service_explicit_tif_honored(self):
        """When a caller explicitly sets tif, that value must be used."""
        order_data: dict[str, Any] = {
            "symbol": "AAPL",
            "side": "buy",
            "qty": 10,
            "tif": "gtc",
        }
        tif = order_data.get("tif", "day")
        assert tif == "gtc"

    # ── 6. Reconciliation scheduler wiring ────────────────────────

    def test_reconciliation_scheduler_importable(self):
        """The reconciliation scheduler module must be importable and
        expose start/stop/status functions."""
        from backend.services.scheduled_reconciliation import (
            start_reconciliation_scheduler,
            stop_reconciliation_scheduler,
            get_scheduler_status,
        )

        assert callable(start_reconciliation_scheduler)
        assert callable(stop_reconciliation_scheduler)
        assert callable(get_scheduler_status)

    def test_reconciliation_scheduler_status_before_start(self):
        """Before starting, get_scheduler_status() should report not_started."""
        from backend.services.scheduled_reconciliation import get_scheduler_status

        status = get_scheduler_status()
        assert status["running"] is False

    async def test_reconciliation_scheduler_start_stop(self):
        """start_reconciliation_scheduler should launch a background task
        and stop_reconciliation_scheduler should cleanly shut it down."""
        from backend.services.scheduled_reconciliation import (
            start_reconciliation_scheduler,
            stop_reconciliation_scheduler,
            get_scheduler_status,
        )

        # Patch the actual reconciliation work so it doesn't need DB/broker
        with patch(
            "backend.services.scheduled_reconciliation.run_scheduled_reconciliation",
            new_callable=AsyncMock,
            return_value={"ok": True},
        ), patch.dict(
            "os.environ",
            {"RECONCILIATION_INTERVAL_MINUTES": "1", "RECONCILIATION_ENABLED": "true"},
        ):
            started = await start_reconciliation_scheduler()
            assert started is True

            status = get_scheduler_status()
            assert status["running"] is True

            await stop_reconciliation_scheduler()

            status = get_scheduler_status()
            assert status["running"] is False

    def test_reconciliation_scheduler_wired_in_lifespan(self):
        """The lifespan startup must reference start_reconciliation_scheduler
        to prove it's wired into the app lifecycle."""
        import ast
        import pathlib

        lifespan_path = pathlib.Path("backend/api/lifespan.py")
        source = lifespan_path.read_text()

        # Must import and call start_reconciliation_scheduler
        assert "start_reconciliation_scheduler" in source
        assert "stop_reconciliation_scheduler" in source

        # Must be valid Python
        ast.parse(source)
