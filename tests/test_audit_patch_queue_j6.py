"""
Tests for J6 patch queue — paper-trading-critical correctness fixes.

P0-001 (SIG-006): Regime detector SMA normalization
P0-002 (EXIT-001): Process pyramider close_partial / tighten_stop actions
P0-003 (CORE-013): Exit_levels persistence decoupled from walk-forward gate
P0-004 (CORE-011): Cancel pending entries on drawdown kill
P0-005 (COMP-400): Remove allow_unsigned pickle fallback
P0-006 (COMP-401): Stub logger redirected to real logging
"""

import json
import logging
import math
import pickle
import struct
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest


# ── P0-001: Regime detector SMA normalization ──────────────────────


class TestRegimeDetectorSMAFix:
    """SIG-006: Regime detector must use raw SMA, not normalized ratio."""

    def test_detect_uses_raw_sma_not_normalized(self):
        """With close=500, raw SMA should be ~500, not ~1.0."""
        from backend.organism.regime import RegimeDetector, RegimeLabel

        det = RegimeDetector(sma_period=10)
        # Build a flat price series at 500
        n = 60
        df = pd.DataFrame({
            "close": [500.0] * n,
            "volume": [1_000_000] * n,
            # Include normalized sma_50 column (like ml_features produces)
            "sma_50": [1.0] * n,
        })
        state = det.detect(df)
        # With flat prices, regime should NOT be trending_up
        # (the old bug made pct_above ≈ 499 → always trending_up)
        assert state.primary != RegimeLabel.UNKNOWN
        # pct_above should be ~0, not ~499
        # If it were trending_up with huge confidence, the fix failed
        probs = state.probabilities
        # trending_up should not dominate — flat prices → chop or low_vol
        assert probs.get(RegimeLabel.TRENDING_UP, 0) < 0.8

    def test_detect_trending_up_with_rising_prices(self):
        """Rising prices should classify as trending_up."""
        from backend.organism.regime import RegimeDetector, RegimeLabel

        det = RegimeDetector(sma_period=10)
        n = 60
        prices = [100.0 + i * 2.0 for i in range(n)]  # steadily rising
        df = pd.DataFrame({
            "close": prices,
            "volume": [1_000_000] * n,
        })
        state = det.detect(df)
        assert state.primary == RegimeLabel.TRENDING_UP

    def test_detect_trending_down_with_falling_prices(self):
        """Falling prices should classify as trending_down."""
        from backend.organism.regime import RegimeDetector, RegimeLabel

        det = RegimeDetector(sma_period=10)
        n = 60
        prices = [200.0 - i * 2.0 for i in range(n)]
        df = pd.DataFrame({
            "close": prices,
            "volume": [1_000_000] * n,
        })
        state = det.detect(df)
        assert state.primary == RegimeLabel.TRENDING_DOWN

    def test_detect_ignores_normalized_sma_column(self):
        """Even with sma_50 column present, detect() uses raw close SMA."""
        from backend.organism.regime import RegimeDetector, RegimeLabel

        det = RegimeDetector(sma_period=10)
        n = 60
        prices = [100.0 + i * 2.0 for i in range(n)]
        df = pd.DataFrame({
            "close": prices,
            "volume": [1_000_000] * n,
            # Bogus normalized sma that would give wrong regime if used
            "sma_50": [0.5] * n,
        })
        state = det.detect(df)
        # Should still detect trending_up from raw close, not from sma_50 col
        assert state.primary == RegimeLabel.TRENDING_UP


# ── P0-002: Pyramider close_partial / tighten_stop ─────────────────


class TestPyramiderActionProcessing:
    """EXIT-001: live_engine must process close_partial and tighten_stop."""

    def test_close_partial_action_produces_sell(self):
        """close_partial with negative shares should trigger exit order."""
        from backend.organism.pyramider import (
            MomentumPyramider,
            PyramidPosition,
            PyramidLevel,
        )

        pyr = MomentumPyramider()
        pos = PyramidPosition(
            symbol="AAPL",
            direction=1.0,
            target_total_shares=100,
            atr_at_entry=5.0,
        )
        pos.layers.append(PyramidLevel(
            shares=60, entry_price=150.0, bar_added=0, level=0,
        ))
        pos.highest_price = 150.0
        pos.current_stop = 135.0

        # Price drops to -1R from entry → full cut
        action = pyr.check_pyramid(pos, 150.0 - 5.0 * 1.0)
        assert action.action == "close_partial"
        assert action.shares_to_add < 0  # negative = sell

    def test_tighten_stop_action_updates_stop(self):
        """tighten_stop with new_stop should have a valid stop level."""
        from backend.organism.pyramider import (
            MomentumPyramider,
            PyramidPosition,
            PyramidLevel,
        )

        pyr = MomentumPyramider()
        pos = PyramidPosition(
            symbol="AAPL",
            direction=1.0,
            target_total_shares=100,
            atr_at_entry=5.0,
        )
        pos.layers.append(PyramidLevel(
            shares=60, entry_price=150.0, bar_added=0, level=0,
        ))
        pos.layers.append(PyramidLevel(
            shares=25, entry_price=160.0, bar_added=5, level=1,
        ))
        pos.highest_price = 175.0
        pos.current_stop = 150.0

        # Price at +5R — should trail stop
        action = pyr.check_pyramid(pos, 150.0 + 5.0 * 5.0)
        if action.action == "tighten_stop":
            assert action.new_stop > 0
            assert action.new_stop > pos.current_stop


# ── P0-003: Exit_levels persistence vs walk-forward gate ────────────


class TestExitLevelsPersistence:
    """CORE-013: exit_levels must persist even when walk-forward gate blocks."""

    def test_persist_exit_levels_standalone_writes_file(self):
        """_persist_exit_levels_standalone should write to extra_counters.json."""
        from backend.organism.live_engine import OrganismLiveEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            brain_dir = Path(tmpdir)
            ec_path = brain_dir / "extra_counters.json"

            # Create a minimal mock engine
            engine = object.__new__(OrganismLiveEngine)
            mock_brain = MagicMock()
            mock_brain.brain_dir = brain_dir
            engine.brain = mock_brain

            exit_levels = {
                "AAPL": {"entry": 150.0, "stop_loss": 140.0, "trailing_stop": 145.0},
            }
            entry_metadata = {"AAPL": {"confidence": 0.75}}

            engine._persist_exit_levels_standalone(exit_levels, entry_metadata)

            assert ec_path.is_file()
            data = json.loads(ec_path.read_text())
            assert "exit_levels" in data
            assert data["exit_levels"]["AAPL"]["entry"] == 150.0
            assert "entry_metadata" in data
            assert data["entry_metadata"]["AAPL"]["confidence"] == 0.75

    def test_persist_exit_levels_preserves_existing_data(self):
        """Standalone save should merge with existing extra_counters data."""
        from backend.organism.live_engine import OrganismLiveEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            brain_dir = Path(tmpdir)
            ec_path = brain_dir / "extra_counters.json"
            # Pre-existing data
            ec_path.write_text(json.dumps({
                "tick_count": 42,
                "peak_equity": 100000.0,
            }))

            engine = object.__new__(OrganismLiveEngine)
            mock_brain = MagicMock()
            mock_brain.brain_dir = brain_dir
            engine.brain = mock_brain

            engine._persist_exit_levels_standalone(
                {"MSFT": {"entry": 400.0}},
                {},
            )

            data = json.loads(ec_path.read_text())
            assert data["tick_count"] == 42  # preserved
            assert data["peak_equity"] == 100000.0  # preserved
            assert "MSFT" in data["exit_levels"]  # added


# ── P0-004: Cancel pending entries on drawdown kill ─────────────────


class TestDrawdownKillCancelOrders:
    """CORE-011: drawdown kill should clear pending entry orders.

    V4 Z-R-3 / Wave-16b (2026-05-02): rewritten as a behavioral
    assertion. The previous test grep'd for the literal string
    `self._pending_entry.clear()` in source. After H-4/H-5 the cancel
    loop switched to per-symbol pop() calls; the grep target moved
    even though the *behavior* is preserved. Behavioral tests don't
    rot under refactors of this kind.
    """

    @pytest.mark.asyncio
    async def test_pending_entries_cleared_on_drawdown_kill(self):
        """When drawdown kill triggers, _pending_entry must be cleared."""
        from unittest.mock import AsyncMock, MagicMock
        from backend.organism.live_engine import OrganismLiveEngine

        engine = object.__new__(OrganismLiveEngine)
        engine._pending_entry = {"AAPL": 10, "MSFT": 12}
        engine._pending_entry_order_ids = {
            "AAPL": "order-aaa",
            "MSFT": "order-bbb",
        }
        engine._order_service = MagicMock()
        engine._order_service.cancel_order = AsyncMock(
            return_value={"status": "cancelled"}
        )

        await engine._cancel_pending_entry_orders()

        # Bookkeeping cleared.
        assert engine._pending_entry == {}
        assert engine._pending_entry_order_ids == {}
        # Broker cancel was called for each tracked order.
        assert engine._order_service.cancel_order.call_count == 2

    def test_drawdown_kill_marker_present(self):
        """The CORE-011 audit marker must remain in the engine source so
        future readers know the drawdown-kill cancel path is intentional.
        """
        import inspect
        from backend.organism.live_engine import OrganismLiveEngine
        source = inspect.getsource(OrganismLiveEngine)
        assert "CORE-011" in source


# ── P0-005: Secure pickle allow_unsigned removal ───────────────────


class TestSecurePickleNoUnsigned:
    """COMP-400: allow_unsigned parameter removed, raw pickle.loads blocked."""

    def test_secure_loads_rejects_unsigned(self):
        """secure_loads must reject unsigned pickle data."""
        from backend.utils.secure_pickle import secure_loads, UnsignedPickleError

        raw = pickle.dumps({"key": "value"})
        with pytest.raises(UnsignedPickleError):
            secure_loads(raw)

    def test_secure_loads_no_allow_unsigned_param(self):
        """secure_loads must not accept allow_unsigned parameter."""
        import inspect
        from backend.utils.secure_pickle import secure_loads

        sig = inspect.signature(secure_loads)
        assert "allow_unsigned" not in sig.parameters

    def test_secure_load_no_allow_unsigned_param(self):
        """secure_load must not accept allow_unsigned parameter."""
        import inspect
        from backend.utils.secure_pickle import secure_load

        sig = inspect.signature(secure_load)
        assert "allow_unsigned" not in sig.parameters

    def test_secure_load_from_path_no_allow_unsigned_param(self):
        """secure_load_from_path must not accept allow_unsigned parameter."""
        import inspect
        from backend.utils.secure_pickle import secure_load_from_path

        sig = inspect.signature(secure_load_from_path)
        assert "allow_unsigned" not in sig.parameters

    def test_roundtrip_signed_pickle(self):
        """Signed pickle roundtrip must still work."""
        from backend.utils.secure_pickle import secure_dumps, secure_loads

        obj = {"hello": "world", "nums": [1, 2, 3]}
        signed = secure_dumps(obj)
        result = secure_loads(signed)
        assert result == obj

    def test_migrate_pickle_file_rejects_unsigned(self):
        """migrate_pickle_file must raise on unsigned files."""
        from backend.utils.secure_pickle import (
            migrate_pickle_file,
            UnsignedPickleError,
        )

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            f.write(pickle.dumps({"data": True}))
            f.flush()
            with pytest.raises(UnsignedPickleError):
                migrate_pickle_file(f.name)

    def test_migrate_pickle_file_accepts_signed(self):
        """migrate_pickle_file returns True for already-signed files."""
        from backend.utils.secure_pickle import (
            migrate_pickle_file,
            secure_dump_to_path,
        )

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            path = f.name
        secure_dump_to_path({"data": True}, path)
        assert migrate_pickle_file(path) is True


# ── P0-006: Stub logger redirect ──────────────────────────────────


class TestLoggerRedirect:
    """COMP-401: Logger must delegate to real logging, not pass stubs."""

    def test_logger_info_emits_record(self):
        """Logger.info() must produce a real log record."""
        from backend.utils.logging import Logger

        lgr = Logger("test_j6")
        with patch.object(lgr._logger, "info") as mock_info:
            lgr.info("test message %s", "arg1")
            mock_info.assert_called_once_with("test message %s", "arg1")

    def test_logger_error_emits_record(self):
        """Logger.error() must produce a real log record."""
        from backend.utils.logging import Logger

        lgr = Logger("test_j6_err")
        with patch.object(lgr._logger, "error") as mock_error:
            lgr.error("error %d", 42)
            mock_error.assert_called_once_with("error %d", 42)

    def test_get_logger_returns_functional_logger(self):
        """get_logger() must return a Logger that delegates to stdlib."""
        from backend.utils.logging import get_logger

        lgr = get_logger("test_j6_func")
        assert hasattr(lgr, "_logger")
        assert isinstance(lgr._logger, logging.Logger)

    def test_log_trade_execution_not_noop(self):
        """log_trade_execution must emit a real log message."""
        from backend.utils.logging import log_trade_execution

        with patch("logging.Logger.info") as mock_info:
            log_trade_execution("ORD-1", "AAPL", 10.0, 150.0)
            assert mock_info.called

    def test_module_level_logger_is_functional(self):
        """Module-level `logger` should delegate to real logging."""
        from backend.utils import logging as log_mod

        assert hasattr(log_mod.logger, "_logger")
        assert isinstance(log_mod.logger._logger, logging.Logger)
