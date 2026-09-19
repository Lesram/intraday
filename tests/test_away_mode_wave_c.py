"""
Away-mode hardening Wave C tests.

C1: No-trade watchdog
C2: Equity fallback watchdog
C3: Universe drift watchdog
C4: Brain save watchdog
C5: Unified get_watchdog_state()
"""

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Helpers: Build a minimal OrganismLiveEngine for unit testing
# ---------------------------------------------------------------------------

def _make_engine(**overrides):
    """Create an OrganismLiveEngine with fully mocked dependencies."""
    from backend.organism.live_engine import OrganismLiveEngine

    mock_data = MagicMock()
    mock_orders = MagicMock()
    mock_positions = MagicMock()

    engine = OrganismLiveEngine(
        data_client=mock_data,
        order_service=mock_orders,
        positions_service=mock_positions,
    )

    # Apply any overrides
    for k, v in overrides.items():
        setattr(engine, k, v)

    return engine


def _make_result(**overrides):
    """Create a LiveTickResult with optional field overrides."""
    from backend.organism.live_engine import LiveTickResult
    result = LiveTickResult()
    for k, v in overrides.items():
        setattr(result, k, v)
    return result


# ======================================================================
# C1: No-trade watchdog
# ======================================================================

class TestC1NoTradeWatchdog:
    """Detects when the system is silently inert during market hours."""

    def test_watchdog_ok_when_orders_generated(self):
        """After tick with orders, state is OK."""
        engine = _make_engine()
        engine._tick_count = 100
        engine._watchdog_last_order_tick = 0  # old

        result = _make_result(orders_submitted=1, signals_generated=3)
        engine._update_watchdog_state(result)

        assert engine._watchdog_state == "OK"
        assert engine._watchdog_last_order_tick == 100

    def test_watchdog_warning_after_long_inertness(self):
        """After many ticks with no orders, state is WARNING_NO_TRADES."""
        engine = _make_engine()
        engine._tick_count = 3000
        engine._watchdog_last_order_tick = 0

        result = _make_result(orders_submitted=0, signals_generated=0)
        engine._update_watchdog_state(result)

        assert engine._watchdog_state == "WARNING_NO_TRADES"

    def test_watchdog_critical_after_very_long_inertness(self):
        """After >12h of no orders, state is CRITICAL_MULTI_SESSION."""
        engine = _make_engine()
        engine._tick_count = 5000
        engine._watchdog_last_order_tick = 0

        result = _make_result(orders_submitted=0, signals_generated=0)
        engine._update_watchdog_state(result)

        assert engine._watchdog_state == "CRITICAL_MULTI_SESSION"

    def test_watchdog_resets_on_order(self):
        """After warning, new order resets to OK."""
        engine = _make_engine()
        engine._tick_count = 3000
        engine._watchdog_last_order_tick = 0

        # First: get into WARNING
        result1 = _make_result(orders_submitted=0, signals_generated=0)
        engine._update_watchdog_state(result1)
        assert engine._watchdog_state == "WARNING_NO_TRADES"

        # Second: order submitted
        result2 = _make_result(orders_submitted=1, signals_generated=1)
        engine._update_watchdog_state(result2)
        assert engine._watchdog_state == "OK"
        assert engine._watchdog_last_order_tick == 3000

    def test_zero_candidates_counter_increments(self):
        """When no signals generated, zero_candidates_ticks goes up."""
        engine = _make_engine()
        engine._tick_count = 10
        engine._watchdog_last_order_tick = 5

        result = _make_result(orders_submitted=0, signals_generated=0)
        engine._update_watchdog_state(result)
        assert engine._watchdog_zero_candidates_ticks == 1

        engine._tick_count = 11
        engine._update_watchdog_state(result)
        assert engine._watchdog_zero_candidates_ticks == 2

    def test_zero_candidates_resets_on_order(self):
        """When orders are submitted, zero_candidates_ticks resets."""
        engine = _make_engine()
        engine._tick_count = 10
        engine._watchdog_zero_candidates_ticks = 50

        result = _make_result(orders_submitted=1, signals_generated=1)
        engine._update_watchdog_state(result)
        assert engine._watchdog_zero_candidates_ticks == 0


# ======================================================================
# C2: Equity fallback watchdog
# ======================================================================

class TestC2EquityFallbackWatchdog:
    """Tracks how often the equity fallback is used."""

    @pytest.mark.asyncio
    async def test_equity_fallback_counter_increments(self):
        """When fallback used, counter goes up."""
        engine = _make_engine()
        engine._tick_count = 10
        engine._last_valid_equity = 100_000.0
        engine._last_valid_equity_tick = 9  # 1 tick ago, within window

        # Mock positions_service to return 0 (triggering fallback)
        engine._positions_service.get_total_portfolio_value = AsyncMock(return_value=0)
        engine._positions_service.get_buying_power = AsyncMock(return_value=0)

        eq = await engine._get_equity()
        assert eq == 100_000.0
        assert engine._watchdog_equity_fallback_count == 1
        assert engine._watchdog_equity_fallback_streak == 1

    @pytest.mark.asyncio
    async def test_equity_fallback_streak_resets(self):
        """After fresh equity, streak resets to 0."""
        engine = _make_engine()
        engine._tick_count = 10
        engine._watchdog_equity_fallback_streak = 5
        engine._watchdog_equity_fallback_count = 10

        # Mock positions_service to return a valid value
        engine._positions_service.get_total_portfolio_value = AsyncMock(return_value=110_000.0)

        eq = await engine._get_equity()
        assert eq == 110_000.0
        assert engine._watchdog_equity_fallback_streak == 0
        # Total count should NOT reset (it is cumulative)
        assert engine._watchdog_equity_fallback_count == 10

    @pytest.mark.asyncio
    async def test_equity_fallback_streak_warning(self, caplog):
        """After 11 consecutive fallbacks, WARNING logged."""
        engine = _make_engine()
        engine._last_valid_equity = 100_000.0
        engine._last_valid_equity_tick = 0
        engine._EQUITY_FALLBACK_MAX_TICKS = 100

        engine._positions_service.get_total_portfolio_value = AsyncMock(return_value=0)
        engine._positions_service.get_buying_power = AsyncMock(return_value=0)

        with caplog.at_level(logging.WARNING):
            for i in range(1, 12):
                engine._tick_count = i
                await engine._get_equity()

        assert engine._watchdog_equity_fallback_streak == 11
        assert any("C2 WATCHDOG" in msg for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_equity_fallback_streak_critical(self, caplog):
        """After 26 consecutive fallbacks, CRITICAL logged."""
        engine = _make_engine()
        engine._last_valid_equity = 100_000.0
        engine._last_valid_equity_tick = 0
        engine._EQUITY_FALLBACK_MAX_TICKS = 100

        engine._positions_service.get_total_portfolio_value = AsyncMock(return_value=0)
        engine._positions_service.get_buying_power = AsyncMock(return_value=0)

        with caplog.at_level(logging.WARNING):
            for i in range(1, 27):
                engine._tick_count = i
                await engine._get_equity()

        assert engine._watchdog_equity_fallback_streak == 26
        assert any("broker API may be down" in msg for msg in caplog.messages)


# ======================================================================
# C3: Universe drift watchdog
# ======================================================================

class TestC3UniverseDriftWatchdog:
    """Tracks if runtime universe diverges from configured base."""

    def test_universe_drift_detected(self):
        """When active universe differs from base, drift_detected is true."""
        engine = _make_engine()
        # Remove AAPL from active universe
        engine._universe = [s for s in engine._universe if s != "AAPL"]

        drift = engine._check_universe_drift()
        assert drift["drift_detected"] is True
        assert "AAPL" in drift["missing_from_base"]

    def test_protected_missing_flagged(self):
        """When SH missing from active, protected_missing includes SH."""
        engine = _make_engine()
        engine._universe = [s for s in engine._universe if s != "SH"]

        drift = engine._check_universe_drift()
        assert "SH" in drift["protected_missing"]
        assert drift["drift_detected"] is True

    def test_no_drift_when_matching(self):
        """When universes match, drift_detected is false."""
        engine = _make_engine()
        # Default engine universe matches LIVE_UNIVERSE_CSV

        drift = engine._check_universe_drift()
        assert drift["drift_detected"] is False
        assert drift["missing_from_base"] == []
        assert drift["protected_missing"] == []

    def test_added_beyond_base_tracked(self):
        """Extra symbols in active universe are tracked."""
        engine = _make_engine()
        engine._universe = list(engine._universe) + ["EXTRA1", "EXTRA2"]

        drift = engine._check_universe_drift()
        assert "EXTRA1" in drift["added_beyond_base"]
        assert "EXTRA2" in drift["added_beyond_base"]


# ======================================================================
# C4: Brain save watchdog
# ======================================================================

class TestC4BrainSaveWatchdog:
    """Tracks brain save health."""

    def test_brain_save_watchdog_healthy(self):
        """Recent save -> healthy=true."""
        engine = _make_engine()
        engine._tick_count = 100
        engine._watchdog_last_brain_save_tick = 90  # 10 ticks ago

        state = engine.get_watchdog_state()
        assert state["brain_save"]["healthy"] is True
        assert state["brain_save"]["ticks_since_last_save"] == 10

    def test_brain_save_watchdog_stale(self):
        """Old save -> healthy=false."""
        engine = _make_engine()
        engine._tick_count = 2000
        engine._watchdog_last_brain_save_tick = 0  # 2000 ticks ago

        state = engine.get_watchdog_state()
        assert state["brain_save"]["healthy"] is False
        assert state["brain_save"]["ticks_since_last_save"] == 2000

    def test_brain_save_tick_updated_on_save(self):
        """Verify _save_brain updates the watchdog tick on success."""
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine

        source = inspect.getsource(OrganismLiveEngine._save_brain)
        assert "_watchdog_last_brain_save_tick" in source, (
            "_save_brain does not update _watchdog_last_brain_save_tick"
        )


# ======================================================================
# C5: Unified get_watchdog_state()
# ======================================================================

class TestC5UnifiedWatchdogState:
    """All watchdog states combined into a single method."""

    def test_get_watchdog_state_returns_all_sections(self):
        """All 4 sections present in output."""
        engine = _make_engine()
        state = engine.get_watchdog_state()

        assert "no_trade" in state
        assert "equity_fallback" in state
        assert "universe_drift" in state
        assert "brain_save" in state

    def test_no_trade_section_has_required_fields(self):
        """no_trade section contains state, ticks_since_last_order, zero_candidate_ticks."""
        engine = _make_engine()
        state = engine.get_watchdog_state()

        nt = state["no_trade"]
        assert "state" in nt
        assert "ticks_since_last_order" in nt
        assert "zero_candidate_ticks" in nt

    def test_equity_fallback_section_has_required_fields(self):
        """equity_fallback section contains total_fallback_count, current_streak."""
        engine = _make_engine()
        state = engine.get_watchdog_state()

        ef = state["equity_fallback"]
        assert "total_fallback_count" in ef
        assert "current_streak" in ef

    def test_brain_save_section_has_required_fields(self):
        """brain_save section contains ticks_since_last_save, healthy."""
        engine = _make_engine()
        state = engine.get_watchdog_state()

        bs = state["brain_save"]
        assert "ticks_since_last_save" in bs
        assert "healthy" in bs

    def test_watchdog_in_live_tick_result_to_dict(self):
        """LiveTickResult.to_dict() includes watchdog key."""
        from backend.organism.live_engine import LiveTickResult

        result = LiveTickResult(watchdog={"test": True})
        d = result.to_dict()
        assert "watchdog" in d
        assert d["watchdog"] == {"test": True}

    def test_watchdog_in_status_dict(self):
        """Engine status() includes watchdog key."""
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine

        source = inspect.getsource(OrganismLiveEngine.status)
        assert "watchdog" in source, (
            "status() does not include watchdog state"
        )
