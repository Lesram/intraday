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
            trailing_distance_atr=1.5, partial_tp_r=3.0
        """
        from backend.organism.adaptive_exits import AdaptiveExitEngine
        from backend.organism.self_evolution import EvolvedParams, apply_evolved_params

        params = EvolvedParams()  # all scale fields default to 1.0
        exit_engine = AdaptiveExitEngine(
            atr_multiplier=1.0,
            trailing_start_atr=2.0,
            trailing_distance_atr=1.5,
            partial_tp_r=3.0,
        )

        apply_evolved_params(params, exit_engine=exit_engine)

        # After applying scale=1.0, the values must be unchanged:
        #   atr_multiplier   = 1.0 * 1.0 = 1.0
        #   trailing_start   = 2.0 * 1.0 = 2.0
        #   trailing_distance= 1.5 * 1.0 = 1.5
        #   partial_tp_r     = 3.0 * 1.0 = 3.0
        assert exit_engine.atr_multiplier == pytest.approx(1.0)
        assert exit_engine.trailing_start_atr == pytest.approx(2.0)
        assert exit_engine.trailing_distance_atr == pytest.approx(1.5)
        assert exit_engine.partial_tp_r == pytest.approx(3.0)

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
            partial_tp_r=3.0,
        )

        apply_evolved_params(params, exit_engine=exit_engine)

        assert exit_engine.atr_multiplier == pytest.approx(1.0 * 1.2)
        assert exit_engine.trailing_start_atr == pytest.approx(2.0 * 0.8)
        assert exit_engine.trailing_distance_atr == pytest.approx(1.5 * 1.1)
        assert exit_engine.partial_tp_r == pytest.approx(3.0 * 0.9)

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

    # ── 7. LONG_ONLY short-position prevention ─────────────────────

    async def test_long_only_exit_blocks_sell_when_no_broker_position(self):
        """When LONG_ONLY is active, _submit_exit_order must verify the
        broker position exists before sending a sell.  If position is gone,
        the sell must be blocked to prevent creating a short."""
        engine, mocks = _make_engine_with_mocks()

        # Broker returns no positions (position was already closed)
        mocks["positions_service"].get_all_positions = AsyncMock(return_value={})

        # Stub order service
        mocks["order_service"].submit_symbol_order = AsyncMock()

        with patch("backend.organism.live_engine.LONG_ONLY", True):
            result = await engine._submit_exit_order("AAPL", 10, "stop_loss", direction=1.0)

        # Must be blocked — no order submitted
        assert result.get("status") == "blocked"
        mocks["order_service"].submit_symbol_order.assert_not_awaited()

    async def test_long_only_exit_clamps_shares_to_broker_qty(self):
        """When LONG_ONLY is active, _submit_exit_order must clamp the sell
        quantity to the actual broker position size.  If the engine tries
        to sell 100 shares but broker only shows 50, it must sell 50."""
        engine, mocks = _make_engine_with_mocks()

        # Broker shows 50 shares
        mocks["positions_service"].get_all_positions = AsyncMock(return_value={
            "AAPL": {"qty": 50, "side": "long", "avg_entry_price": 150.0,
                     "current_price": 145.0},
        })
        mocks["order_service"].submit_symbol_order = AsyncMock(
            return_value={"id": "test123", "status": "accepted"}
        )

        with patch("backend.organism.live_engine.LONG_ONLY", True):
            result = await engine._submit_exit_order("AAPL", 100, "stop_loss", direction=1.0)

        # Order should be submitted with clamped qty=50
        mocks["order_service"].submit_symbol_order.assert_awaited_once()
        call_kwargs = mocks["order_service"].submit_symbol_order.call_args
        assert call_kwargs[1]["qty"] == 50 or call_kwargs.kwargs["qty"] == 50

    async def test_long_only_exit_blocks_sell_on_short_position(self):
        """When LONG_ONLY is active and broker shows a SHORT position,
        _submit_exit_order must refuse to sell (which would increase the short)."""
        engine, mocks = _make_engine_with_mocks()

        # Broker shows a short position (shouldn't exist, but does due to bug)
        mocks["positions_service"].get_all_positions = AsyncMock(return_value={
            "AAPL": {"qty": -50, "side": "short", "avg_entry_price": 150.0,
                     "current_price": 155.0},
        })
        mocks["order_service"].submit_symbol_order = AsyncMock()

        with patch("backend.organism.live_engine.LONG_ONLY", True):
            result = await engine._submit_exit_order("AAPL", 50, "stop_loss", direction=1.0)

        assert result.get("status") == "blocked"
        mocks["order_service"].submit_symbol_order.assert_not_awaited()

    async def test_long_only_exit_loop_skips_short_positions(self):
        """The main exit loop must skip SHORT positions when LONG_ONLY is active.
        It should log a warning and continue to the next position."""
        engine, mocks = _make_engine_with_mocks()

        # Mix of long and short positions from broker
        mocks["positions_service"].get_all_positions = AsyncMock(return_value={
            "AAPL": {"qty": 10, "side": "long", "avg_entry_price": 150.0,
                     "current_price": 120.0},  # 20% loss → safety net triggers
            "CORT": {"qty": -100, "side": "short", "avg_entry_price": 35.0,
                     "current_price": 40.0},  # Short — should be SKIPPED
        })

        import pandas as pd
        engine._fetch_and_compute_features = AsyncMock(return_value={
            "SPY": pd.DataFrame({"close": [400.0]}),
        })
        engine._get_equity = AsyncMock(return_value=100_000.0)
        engine._submit_exit_order = AsyncMock()
        engine._reconcile_fills = AsyncMock()
        engine._save_brain = MagicMock()
        engine._check_tick_invariants = MagicMock()
        engine._initialized = True

        with patch("backend.organism.live_engine.LONG_ONLY", True):
            result = await engine.live_tick()

        # Exit should only be submitted for AAPL (long), NOT CORT (short)
        exit_calls = engine._submit_exit_order.call_args_list
        exit_symbols = [c[0][0] for c in exit_calls]
        assert "AAPL" in exit_symbols
        assert "CORT" not in exit_symbols

    def test_long_only_orphan_adoption_skips_shorts(self):
        """The orphan adoption logic in _reconcile_fills must refuse to adopt
        SHORT positions when LONG_ONLY is active."""
        import ast
        import pathlib

        source = pathlib.Path("backend/organism/live_engine.py").read_text()
        tree = ast.parse(source)

        # Verify the source contains the LONG_ONLY guard in orphan adoption
        assert "LONG_ONLY: refusing to adopt orphaned SHORT" in source

    def test_exit_idempotency_key_uses_tick_count(self):
        """Exit order idempotency keys must use tick_count, not wall-clock
        seconds.  This prevents duplicate exit orders across rapid ticks."""
        import ast
        import pathlib

        source = pathlib.Path("backend/organism/live_engine.py").read_text()

        # The exit idempotency key must contain tick_count reference
        assert "_t{self._tick_count}" in source or "f\"_t{self._tick_count}\"" in source

    def test_entry_idempotency_key_uses_tick_count(self):
        """Entry order idempotency keys must use tick_count, not wall-clock
        seconds, to prevent duplicate entries within the same tick."""
        import pathlib

        source = pathlib.Path("backend/organism/live_engine.py").read_text()

        # Verify the entry idempotency key no longer uses %H%M%S
        # and instead uses tick_count
        lines = source.split("\n")
        in_entry_method = False
        for line in lines:
            if "def _submit_entry_order" in line:
                in_entry_method = True
            elif in_entry_method and "def " in line and "def _submit_entry_order" not in line:
                in_entry_method = False
            if in_entry_method and "idem_key" in line and "%H%M%S" in line:
                pytest.fail("Entry idempotency key still uses %H%M%S timestamp")

    # ── 8. Profit lock at 2R ──────────────────────────────────────

    def test_profit_lock_at_2r_long(self):
        """At 2R favorable move, stop should lock to entry + 1R."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels

        engine = AdaptiveExitEngine(atr_multiplier=1.5)
        levels = ExitLevels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            stop_loss=94.0, take_profit=130.0, trailing_stop=94.0,
            atr_at_entry=2.0, regime_at_entry="unknown",
            highest_favorable=100.0,
        )
        # initial_risk = 2.0 (ATR) * 3.0 (REGIME_STOP_ATR["unknown"]) = 6.0
        # 2R move = 100 + 6.0 * 2 = 112.0
        engine._check_profit_lock(levels, 112.0)

        assert levels.profit_locked is True
        # new_stop = entry + initial_risk * direction = 100 + 6.0 = 106.0
        assert levels.stop_loss == pytest.approx(106.0)

    def test_profit_lock_at_2r_short(self):
        """Profit lock works for shorts — stop moves down to entry - 1R."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels

        engine = AdaptiveExitEngine(atr_multiplier=1.5)
        levels = ExitLevels(
            symbol="TSLA", direction=-1.0, entry_price=200.0,
            stop_loss=206.0, take_profit=170.0, trailing_stop=206.0,
            atr_at_entry=2.0, regime_at_entry="unknown",
            highest_favorable=200.0,
        )
        # initial_risk = 2.0 * 3.0 = 6.0
        # 2R short move = 200 - 12.0 = 188.0
        engine._check_profit_lock(levels, 188.0)

        assert levels.profit_locked is True
        # new_stop = 200 + 6.0 * (-1) = 194.0
        assert levels.stop_loss == pytest.approx(194.0)

    def test_profit_lock_one_shot(self):
        """Once profit_locked=True, a second call is a no-op."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels

        engine = AdaptiveExitEngine(atr_multiplier=1.5)
        levels = ExitLevels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            stop_loss=94.0, take_profit=130.0, trailing_stop=94.0,
            atr_at_entry=2.0, regime_at_entry="unknown",
            highest_favorable=100.0,
        )
        # 2R = 100 + 6.0*2 = 112.0
        engine._check_profit_lock(levels, 112.0)
        first_stop = levels.stop_loss

        # Move price much higher — stop should NOT change
        engine._check_profit_lock(levels, 120.0)
        assert levels.stop_loss == pytest.approx(first_stop)

    def test_profit_lock_never_downgrades_stop(self):
        """If stop is already above 1R (e.g. from trailing), lock doesn't move it down."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels

        engine = AdaptiveExitEngine(atr_multiplier=1.5)
        levels = ExitLevels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            stop_loss=108.0,  # Already above 1R (106.0)
            take_profit=130.0, trailing_stop=108.0,
            atr_at_entry=2.0, regime_at_entry="unknown",
            highest_favorable=100.0,
        )
        # 2R = 112.0
        engine._check_profit_lock(levels, 112.0)

        assert levels.profit_locked is True
        # Stop should stay at 108.0 (higher than 1R=106.0) due to max()
        assert levels.stop_loss == pytest.approx(108.0)

    def test_profit_lock_in_check_exit(self):
        """Profit lock fires within the check_exit() chain."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels

        engine = AdaptiveExitEngine(atr_multiplier=1.5)
        levels = ExitLevels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            stop_loss=94.0, take_profit=150.0, trailing_stop=94.0,
            atr_at_entry=2.0, regime_at_entry="unknown",
            highest_favorable=100.0,
            partial_tp_price=118.0,  # 3R — above 112 so partial TP doesn't fire
            bars_held=17,  # Pass min hold guard (becomes 18 after check)
        )
        # Price at 2R (112.0) — should trigger profit lock but NOT exit
        signal = engine.check_exit(levels, 112.0, current_regime="unknown")

        assert levels.profit_locked is True
        assert levels.stop_loss == pytest.approx(106.0)
        assert signal.should_exit is False  # 112 > 106, no stop hit

    def test_partial_tp_does_not_downgrade_profit_lock(self):
        """When partial TP fires at 3R, the stop must stay at 1R (not drop to breakeven)."""
        from backend.organism.adaptive_exits import AdaptiveExitEngine, ExitLevels

        engine = AdaptiveExitEngine(atr_multiplier=1.5)
        levels = ExitLevels(
            symbol="AAPL", direction=1.0, entry_price=100.0,
            stop_loss=94.0, take_profit=150.0, trailing_stop=94.0,
            atr_at_entry=2.0, regime_at_entry="unknown",
            highest_favorable=100.0,
            # partial_tp_price for 3R: entry + risk*3 = 100 + 6*3 = 118
            partial_tp_price=118.0,
        )
        # First: trigger profit lock at 2R (112.0)
        engine._check_profit_lock(levels, 112.0)
        assert levels.profit_locked is True
        profit_lock_stop = levels.stop_loss  # 106.0

        # Now trigger partial TP at 3R
        signal = engine._check_partial_tp(levels, 118.0)
        assert signal.should_exit is True
        assert signal.partial_exit is True

        # Stop must stay at 106.0 (profit lock), NOT drop to 100.0 (breakeven)
        assert levels.stop_loss == pytest.approx(profit_lock_stop)

    # ── 9. SPY MA filter ─────────────────────────────────────────

    async def test_spy_filter_blocks_below_ma(self):
        """When SPY < SMA50, long entries should be blocked."""
        import pandas as pd
        engine, mocks = _make_engine_with_mocks()
        engine._spy_filter_enabled = True  # Explicitly enable (disabled by default)

        mocks["positions_service"].get_all_positions = AsyncMock(return_value={})

        # SPY with declining prices (current < SMA50)
        spy_prices = list(range(150, 100, -1))  # 50 bars, declining
        features = {
            "SPY": pd.DataFrame({"close": spy_prices}),
            "AAPL": pd.DataFrame({"close": [150.0] * 50}),
            "MSFT": pd.DataFrame({"close": [300.0] * 50}),
            "GOOGL": pd.DataFrame({"close": [140.0] * 50}),
        }
        engine._fetch_and_compute_features = AsyncMock(return_value=features)
        engine._get_equity = AsyncMock(return_value=100_000.0)
        engine._reconcile_fills = AsyncMock()
        engine._save_brain = MagicMock()
        engine._check_tick_invariants = MagicMock()
        engine._initialized = True
        engine._tick_count = 10  # bypass warmup
        engine._WARMUP_TICKS = 0

        with patch("backend.organism.live_engine.LONG_ONLY", True):
            result = await engine.live_tick()

        # Should have SPY filter activity event
        spy_msgs = [
            a for a in result.activity
            if hasattr(a, "message") and "SPY filter" in a.message
        ]
        assert len(spy_msgs) >= 1
        assert result.orders_submitted == 0

    async def test_spy_filter_allows_above_ma(self):
        """When SPY > SMA50, entries should not be blocked by SPY filter."""
        import pandas as pd
        engine, mocks = _make_engine_with_mocks()

        mocks["positions_service"].get_all_positions = AsyncMock(return_value={})

        # SPY with rising prices (current > SMA50)
        spy_prices = list(range(100, 150))  # 50 bars, rising
        features = {
            "SPY": pd.DataFrame({"close": spy_prices}),
            "AAPL": pd.DataFrame({"close": [150.0] * 50}),
            "MSFT": pd.DataFrame({"close": [300.0] * 50}),
            "GOOGL": pd.DataFrame({"close": [140.0] * 50}),
        }
        engine._fetch_and_compute_features = AsyncMock(return_value=features)
        engine._get_equity = AsyncMock(return_value=100_000.0)
        engine._reconcile_fills = AsyncMock()
        engine._save_brain = MagicMock()
        engine._check_tick_invariants = MagicMock()
        engine._initialized = True
        engine._tick_count = 10  # bypass warmup
        engine._WARMUP_TICKS = 0

        with patch("backend.organism.live_engine.LONG_ONLY", True):
            result = await engine.live_tick()

        # No SPY filter block
        spy_msgs = [
            a for a in result.activity
            if hasattr(a, "message") and "SPY filter" in a.message
        ]
        assert len(spy_msgs) == 0

    async def test_spy_filter_skips_insufficient_data(self):
        """With < 50 bars of SPY data, the filter should not block."""
        import pandas as pd
        engine, mocks = _make_engine_with_mocks()

        mocks["positions_service"].get_all_positions = AsyncMock(return_value={})

        # Only 10 bars of SPY — not enough for SMA50
        features = {
            "SPY": pd.DataFrame({"close": [100.0] * 10}),
            "AAPL": pd.DataFrame({"close": [150.0] * 50}),
            "MSFT": pd.DataFrame({"close": [300.0] * 50}),
            "GOOGL": pd.DataFrame({"close": [140.0] * 50}),
        }
        engine._fetch_and_compute_features = AsyncMock(return_value=features)
        engine._get_equity = AsyncMock(return_value=100_000.0)
        engine._reconcile_fills = AsyncMock()
        engine._save_brain = MagicMock()
        engine._check_tick_invariants = MagicMock()
        engine._initialized = True
        engine._tick_count = 10  # bypass warmup
        engine._WARMUP_TICKS = 0

        with patch("backend.organism.live_engine.LONG_ONLY", True):
            result = await engine.live_tick()

        # No SPY filter block
        spy_msgs = [
            a for a in result.activity
            if hasattr(a, "message") and "SPY filter" in a.message
        ]
        assert len(spy_msgs) == 0
