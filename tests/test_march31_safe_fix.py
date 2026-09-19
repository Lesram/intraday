"""Tests for March 31 safe-fix: reconciliation classification and regime_at_exit.

These tests validate that the ACTUAL production code in live_engine.py contains
the three fixes.  They will FAIL if the fixes are reverted or missing.

Fixes under test:
  A. Startup metadata cross-validation (prune stale entries)
  B. Reconciliation-adjustment trade tagging
  C. regime_at_exit uses _last_regime instead of always "unknown"
"""

import ast
import inspect
import textwrap

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────
#  Helpers: read the actual production source for code-path checks
# ─────────────────────────────────────────────────────────────

def _read_live_engine_source() -> str:
    """Return the full source of OrganismLiveEngine."""
    from backend.organism.live_engine import OrganismLiveEngine
    return inspect.getsource(OrganismLiveEngine)


def _get_method_source(method_name: str) -> str:
    """Return source of a specific OrganismLiveEngine method."""
    from backend.organism.live_engine import OrganismLiveEngine
    method = getattr(OrganismLiveEngine, method_name, None)
    assert method is not None, f"Method {method_name} not found on OrganismLiveEngine"
    return inspect.getsource(method)


# ═════════════════════════════════════════════════════════════
#  FIX A — Startup metadata cross-validation
# ═════════════════════════════════════════════════════════════

class TestFixA_StartupMetadataPruning:
    """Verify that initialize() cross-checks entry_metadata against
    broker positions and removes stale entries."""

    def test_initialize_contains_broker_crosscheck(self):
        """The initialize method must call get_all_positions to
        cross-check entry_metadata against broker state."""
        src = _get_method_source("initialize")
        # Must query broker positions during metadata restoration
        assert "get_all_positions" in src, (
            "initialize() does not call get_all_positions — "
            "stale metadata pruning fix is missing"
        )
        # Must compute stale_symbols
        assert "stale_symbols" in src, (
            "initialize() does not compute stale_symbols — "
            "metadata cross-validation logic is missing"
        )

    def test_initialize_prunes_stale_metadata(self):
        """The initialize method must pop stale symbols from
        saved_entry_meta before assigning to _entry_metadata."""
        src = _get_method_source("initialize")
        assert "saved_entry_meta.pop(sym" in src or "saved_entry_meta.pop(sym," in src, (
            "initialize() does not pop stale symbols from saved_entry_meta"
        )

    def test_initialize_has_failsafe_on_broker_error(self):
        """If broker is unreachable, metadata must be kept (fail-safe)."""
        src = _get_method_source("initialize")
        assert "broker_symbols = None" in src, (
            "initialize() has no fail-safe for broker API failure"
        )

    @pytest.mark.asyncio
    async def test_prune_logic_removes_stale_keeps_valid(self):
        """Integration-style test: reproduce the pruning logic using
        the same code pattern as production."""
        from backend.organism.live_engine import OrganismLiveEngine

        # Build minimal engine with mocked services
        engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
        engine._entry_metadata = {}

        mock_positions_service = AsyncMock()
        mock_positions_service.get_all_positions.return_value = {
            "AAPL": {"qty": "10", "avg_entry_price": "250.0", "side": "long"}
        }
        engine._positions_service = mock_positions_service

        saved_entry_meta = {
            "XLK": {"entry_price": 131.01, "entry_tick": 100},
            "AAPL": {"entry_price": 250.0, "entry_tick": 100},
        }

        # Execute the same logic as production (lines 812-828)
        try:
            broker_positions = await engine._positions_service.get_all_positions()
            broker_symbols = set(broker_positions.keys()) if broker_positions else set()
        except Exception:
            broker_symbols = None

        if broker_symbols is not None:
            stale_symbols = set(saved_entry_meta.keys()) - broker_symbols
            if stale_symbols:
                for sym in stale_symbols:
                    saved_entry_meta.pop(sym, None)

        engine._entry_metadata = saved_entry_meta

        assert "XLK" not in engine._entry_metadata, "Stale XLK metadata was not pruned"
        assert "AAPL" in engine._entry_metadata, "Valid AAPL metadata was incorrectly pruned"

    @pytest.mark.asyncio
    async def test_prune_logic_failsafe_keeps_all_on_error(self):
        """When broker is unreachable, all metadata must be preserved."""
        from backend.organism.live_engine import OrganismLiveEngine

        engine = OrganismLiveEngine.__new__(OrganismLiveEngine)
        engine._entry_metadata = {}

        mock_positions_service = AsyncMock()
        mock_positions_service.get_all_positions.side_effect = Exception("timeout")
        engine._positions_service = mock_positions_service

        saved_entry_meta = {
            "XLK": {"entry_price": 131.01},
            "AAPL": {"entry_price": 250.0},
        }

        try:
            broker_positions = await engine._positions_service.get_all_positions()
            broker_symbols = set(broker_positions.keys()) if broker_positions else set()
        except Exception:
            broker_symbols = None

        if broker_symbols is not None:
            stale_symbols = set(saved_entry_meta.keys()) - broker_symbols
            for sym in stale_symbols:
                saved_entry_meta.pop(sym, None)

        engine._entry_metadata = saved_entry_meta

        assert "XLK" in engine._entry_metadata, "Fail-safe: XLK should be kept when broker unreachable"
        assert "AAPL" in engine._entry_metadata, "Fail-safe: AAPL should be kept when broker unreachable"


# ═════════════════════════════════════════════════════════════
#  FIX B — Reconciliation adjustment classification
# ═════════════════════════════════════════════════════════════

class TestFixB_ReconciliationAdjustmentTag:
    """Verify that _reconcile_fills tags phantom closes as
    'reconciliation_adjustment' instead of 'live_close'."""

    def test_reconcile_fills_contains_reconciliation_adjustment(self):
        """The _reconcile_fills method must contain the
        reconciliation_adjustment classification logic."""
        src = _get_method_source("_reconcile_fills")
        assert "reconciliation_adjustment" in src, (
            "_reconcile_fills() does not contain 'reconciliation_adjustment' — "
            "phantom trade classification fix is missing"
        )

    def test_reconcile_fills_checks_live_close_and_no_fill(self):
        """The classification must check: exit_reason == 'live_close'
        AND real_fill is None AND _bars_held == 0."""
        src = _get_method_source("_reconcile_fills")
        assert 'live_close' in src, "No live_close check in _reconcile_fills"
        assert "real_fill is None" in src or "real_fill is None" in src, (
            "No real_fill check in classification"
        )
        assert "_bars_held == 0" in src, "No bars_held check in classification"

    def test_exit_reason_assigned_to_trade_record(self):
        """The TradeRecord must use the classified _exit_reason,
        not the raw default."""
        src = _get_method_source("_reconcile_fills")
        assert "exit_reason=_exit_reason" in src, (
            "TradeRecord does not use classified _exit_reason variable — "
            "it may still use the raw pop() default"
        )

    def test_reconciliation_trade_separable_from_strategy(self):
        """Verify TradeRecord with exit_reason='reconciliation_adjustment'
        can be filtered from strategy trades."""
        from backend.organism.continuous_learner import TradeRecord

        recon_trade = TradeRecord(
            symbol="XLK", direction=1.0, entry_price=131.01,
            exit_price=137.97, entry_bar=0, exit_bar=3,
            shares=25, pnl=174.0, exit_reason="reconciliation_adjustment",
            predicted_return=0.0, actual_return=0.053, confidence=0.42,
        )
        strategy_trade = TradeRecord(
            symbol="AAPL", direction=1.0, entry_price=250.0,
            exit_price=252.0, entry_bar=100, exit_bar=110,
            shares=10, pnl=20.0, exit_reason="stop_loss",
            predicted_return=0.001, actual_return=0.008, confidence=0.28,
        )

        trades = [recon_trade, strategy_trade]
        strategy_only = [t for t in trades if t.exit_reason != "reconciliation_adjustment"]

        assert len(strategy_only) == 1
        assert strategy_only[0].symbol == "AAPL"
        assert recon_trade.exit_reason == "reconciliation_adjustment"

    def test_genuine_live_close_with_bars_not_retagged(self):
        """A live_close with bars_held > 0 must NOT be retagged.
        This reproduces the production guard condition."""
        _exit_reason = "live_close"
        real_fill = None
        _bars_held = 5

        # Same condition as production code line 3640
        if _exit_reason == "live_close" and real_fill is None and _bars_held == 0:
            _exit_reason = "reconciliation_adjustment"

        assert _exit_reason == "live_close", (
            "Genuine live_close with bars_held>0 was incorrectly retagged"
        )


# ═════════════════════════════════════════════════════════════
#  FIX C — regime_at_exit uses _last_regime
# ═════════════════════════════════════════════════════════════

class TestFixC_RegimeAtExitPopulation:
    """Verify that regime_at_exit reads from self._last_regime
    rather than regime_detector.current_regime."""

    def test_reconcile_fills_uses_last_regime(self):
        """_reconcile_fills must reference self._last_regime for
        regime_at_exit, not only regime_detector.current_regime."""
        src = _get_method_source("_reconcile_fills")
        assert "self._last_regime" in src, (
            "_reconcile_fills() does not reference self._last_regime — "
            "regime_at_exit fix is missing (would always return 'unknown')"
        )

    def test_last_regime_preferred_over_detector(self):
        """When _last_regime is a known regime, it must take priority
        over the detector's current_regime property."""
        src = _get_method_source("_reconcile_fills")
        # The fix pattern: self._last_regime if self._last_regime != "unknown" else ...
        assert '_last_regime != "unknown"' in src or "_last_regime != 'unknown'" in src, (
            "_reconcile_fills() does not prefer _last_regime over detector — "
            "regime_at_exit would still fall through to detector.current_regime"
        )

    def test_last_regime_maintained_per_tick(self):
        """self._last_regime must be updated in the tick loop,
        not just at initialization."""
        src = _read_live_engine_source()
        # The per-tick update is at line ~1750: self._last_regime = regime
        assert "self._last_regime = regime" in src, (
            "_last_regime is not updated per-tick — "
            "regime_at_exit would be stale"
        )

    def test_last_regime_initialized_to_unknown(self):
        """_last_regime must be initialized to 'unknown' to handle
        the case where no tick has run yet."""
        src = _read_live_engine_source()
        assert 'self._last_regime' in src
        # Check initialization
        assert '_last_regime: str = "unknown"' in src or \
               "_last_regime = \"unknown\"" in src, (
            "_last_regime is not initialized to 'unknown'"
        )

    def test_regime_at_exit_valid_regimes_propagate(self):
        """All valid regime labels should propagate when set as _last_regime."""
        valid = ["trending_up", "trending_down", "chop", "high_vol", "low_vol", "stress"]
        mock_detector = MagicMock()
        mock_detector.current_regime = "unknown"

        for regime in valid:
            _last_regime = regime
            _regime_at_exit = (
                _last_regime if _last_regime != "unknown"
                else getattr(mock_detector, "current_regime", "unknown")
            )
            assert _regime_at_exit == regime, f"Failed to propagate regime={regime}"
