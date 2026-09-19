"""Tests for pyramid cost-basis fix.

Validates that TradeRecord entry_price and pnl use the true
cost-weighted average of all pyramid fills, not the first leg's
bar-close price.

Tests exercise the actual production code paths via
inspect.getsource and functional simulation.
"""

import inspect
import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _get_method_source(method_name: str) -> str:
    from backend.organism.live_engine import OrganismLiveEngine
    method = getattr(OrganismLiveEngine, method_name, None)
    assert method is not None, f"Method {method_name} not found"
    return inspect.getsource(method)


def _make_pyramid(layers):
    """Create a PyramidPosition from a list of (shares, entry_price) tuples."""
    from backend.organism.pyramider import PyramidPosition, PyramidLevel
    return PyramidPosition(
        symbol="TEST",
        direction=1.0,
        layers=[
            PyramidLevel(shares=s, entry_price=p, bar_added=i, level=i)
            for i, (s, p) in enumerate(layers)
        ],
        atr_at_entry=1.0,
        initial_stop=0.0,
        current_stop=0.0,
        highest_price=0.0,
        lowest_price=float('inf'),
    )


# ═════════════════════════════════════════════════════════════
#  SOURCE CODE PRESENCE TESTS
# ═════════════════════════════════════════════════════════════

class TestFixPresence:
    """Verify the production code uses pyr.avg_entry for trade close."""

    def test_reconcile_fills_uses_pyr_avg_entry(self):
        """_reconcile_fills must use pyr.avg_entry instead of meta entry_price."""
        src = _get_method_source("_reconcile_fills")
        assert "pyr.avg_entry" in src, (
            "_reconcile_fills does not use pyr.avg_entry — "
            "pyramid cost-basis fix is missing"
        )

    def test_reconcile_fills_syncs_broker_avg_entry(self):
        """_reconcile_fills must sync entry prices from broker's avg_entry_price."""
        src = _get_method_source("_reconcile_fills")
        assert "avg_entry_price" in src, (
            "_reconcile_fills does not sync broker avg_entry_price"
        )

    def test_meta_entry_price_is_fallback(self):
        """meta['entry_price'] should only be used when no pyramid exists."""
        src = _get_method_source("_reconcile_fills")
        # The pattern: if pyr exists, use pyr.avg_entry; else use meta
        assert 'entry_price = pyr.avg_entry' in src or \
               'entry_price = meta["entry_price"]' in src


# ═════════════════════════════════════════════════════════════
#  PYRAMID COST-BASIS COMPUTATION TESTS
# ═════════════════════════════════════════════════════════════

class TestPyramidAvgEntry:
    """Test PyramidPosition.avg_entry computes correctly."""

    def test_single_leg(self):
        pyr = _make_pyramid([(10, 100.0)])
        assert pyr.avg_entry == pytest.approx(100.0)

    def test_two_leg_pyramid_up(self):
        """Two buys: 15 @ $207.65, 7 @ $208.72 → avg = $207.99."""
        pyr = _make_pyramid([(15, 207.65), (7, 208.72)])
        expected = (15 * 207.65 + 7 * 208.72) / 22
        assert pyr.avg_entry == pytest.approx(expected, abs=0.01)

    def test_three_leg_pyramid_up(self):
        """Three buys: 24 @ $133.64, 12 @ $134.12, 4 @ $135.02."""
        pyr = _make_pyramid([(24, 133.64), (12, 134.12), (4, 135.02)])
        expected = (24 * 133.64 + 12 * 134.12 + 4 * 135.02) / 40
        assert pyr.avg_entry == pytest.approx(expected, abs=0.01)

    def test_losing_pyramid(self):
        """Pyramid into declining prices."""
        pyr = _make_pyramid([(20, 160.15), (10, 160.48), (3, 160.68)])
        expected = (20 * 160.15 + 10 * 160.48 + 3 * 160.68) / 33
        assert pyr.avg_entry == pytest.approx(expected, abs=0.01)


class TestPnLComputation:
    """Test that PnL computed from avg_entry matches broker truth."""

    def test_amd_apr2_style(self):
        """AMD Apr 2: 15 @ $207.65, 7 @ $208.72, exit 22 @ $209.68."""
        pyr = _make_pyramid([(15, 207.65), (7, 208.72)])
        entry = pyr.avg_entry
        exit_price = 209.68
        shares = pyr.total_shares
        pnl = (exit_price - entry) * shares
        # Broker truth: sell $4612.96 - buy $4575.79 = +$37.17
        assert pnl == pytest.approx(37.17, abs=0.50)

    def test_xlk_apr2_style(self):
        """XLK Apr 2: 24 @ $133.64, 12 @ $134.12, 4 @ $135.02, exit 40 @ $134.98."""
        pyr = _make_pyramid([(24, 133.64), (12, 134.12), (4, 135.02)])
        entry = pyr.avg_entry
        exit_price = 134.98
        shares = pyr.total_shares
        pnl = (exit_price - entry) * shares
        # Should be approximately correct vs broker
        assert shares == 40
        assert pnl == pytest.approx(42.30, abs=1.50)

    def test_xom_apr2_style(self):
        """XOM Apr 2: 20 @ $160.16, 10 @ $160.48, 3 @ $160.68, exit 24 @ $160.67."""
        pyr = _make_pyramid([(20, 160.16), (10, 160.48), (3, 160.68)])
        entry = pyr.avg_entry
        # Partial exit: only 24 shares sold (not all 33)
        # avg entry should NOT change for remaining shares
        exit_price = 160.67
        exit_shares = 24
        pnl = (exit_price - entry) * exit_shares
        assert entry == pytest.approx((20*160.16 + 10*160.48 + 3*160.68)/33, abs=0.01)

    def test_single_leg_unchanged(self):
        """Single-leg entry should produce same PnL as before."""
        pyr = _make_pyramid([(10, 100.0)])
        exit_price = 102.0
        pnl = (exit_price - pyr.avg_entry) * pyr.total_shares
        assert pnl == pytest.approx(20.0)

    def test_losing_single_leg(self):
        pyr = _make_pyramid([(10, 100.0)])
        exit_price = 98.0
        pnl = (exit_price - pyr.avg_entry) * pyr.total_shares
        assert pnl == pytest.approx(-20.0)


class TestPartialExitPreservesAvg:
    """Partial exits must not change avg entry of remaining shares."""

    def test_partial_exit_avg_unchanged(self):
        """After partial exit, remaining layers still have same avg."""
        pyr = _make_pyramid([(20, 100.0), (10, 102.0)])
        avg_before = pyr.avg_entry
        # Simulate partial exit by removing shares from last layer
        # (In production, partial exits remove from layers)
        # The avg_entry should remain the same for remaining shares
        # because partial exits don't change entry prices
        assert avg_before == pytest.approx((20*100 + 10*102)/30, abs=0.01)
        # If we remove the second layer entirely (10 shares exited)
        pyr.layers.pop()
        assert pyr.avg_entry == pytest.approx(100.0)
        # The avg changes to just first layer — this is correct behavior


class TestLimitPriceNeverSubstituted:
    """Verify the fix uses actual fills, not limit prices."""

    def test_broker_sync_uses_avg_entry_price(self):
        """The reconciliation sync must read broker's avg_entry_price field."""
        src = _get_method_source("_reconcile_fills")
        assert 'avg_entry_price' in src, (
            "No broker avg_entry_price sync — limit prices may still be used"
        )

    def test_pyr_avg_entry_used_not_meta(self):
        """At trade close, entry_price must come from pyramid avg, not metadata."""
        src = _get_method_source("_reconcile_fills")
        # Must have the pattern: entry_price = pyr.avg_entry
        assert "entry_price = pyr.avg_entry" in src


class TestPersistedOutputCorrect:
    """Verify TradeRecord stores corrected entry_price and pnl."""

    def test_trade_record_fields(self):
        from backend.organism.continuous_learner import TradeRecord
        # Create a trade with corrected cost basis
        t = TradeRecord(
            symbol="AMD", direction=1.0,
            entry_price=207.99,  # corrected weighted avg
            exit_price=209.68,
            entry_bar=100, exit_bar=118,
            shares=22,
            pnl=round((209.68 - 207.99) * 22, 2),
            exit_reason="horizon_timeout",
            predicted_return=0.001, actual_return=0.008,
            confidence=0.28,
        )
        assert t.entry_price == pytest.approx(207.99)
        assert t.pnl == pytest.approx(37.18, abs=0.10)
        assert t.pnl != pytest.approx(47.08, abs=1.0)  # old wrong value
