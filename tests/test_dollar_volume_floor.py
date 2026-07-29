"""2026-06-24: liquidity gate dollar-volume floor.

The share-count floor (_MIN_AVG_VOLUME) spuriously blocked high-priced / thin
core names (COST ~$900, SH) despite ample dollar volume — observed live
(COST 462, SH 320 blocks). The gate now uses a per-bar DOLLAR-volume floor
when _MIN_AVG_DOLLAR_VOLUME > 0 and a price column is present, falling back to
the share-count floor otherwise. Default-0 (attr unset) preserves legacy
share-count behavior, so the older guards are unaffected.
"""
from __future__ import annotations

import pandas as pd

from backend.organism.live_engine import OrganismLiveEngine


def _engine(min_dollar=1_000_000.0, min_shares=10_000):
    e = OrganismLiveEngine.__new__(OrganismLiveEngine)
    e._MIN_AVG_VOLUME = min_shares
    e._MIN_AVG_DOLLAR_VOLUME = min_dollar
    return e


def test_high_priced_low_share_name_passes_on_dollars():
    """COST-like: ~5k shares/bar but ~$900 -> ~$4.5M/bar dollar volume >> $1M.
    Would FAIL the 10k-share floor; PASSES on dollar volume."""
    e = _engine()
    df = pd.DataFrame({"volume": [5_000] * 20, "close": [900.0] * 20})
    assert e._passes_liquidity_gate("COST", {"COST": df}) is True


def test_genuinely_illiquid_blocked_on_dollars():
    """Penny/thin name: 5k shares @ $2 = $10k/bar << $1M -> blocked."""
    e = _engine()
    df = pd.DataFrame({"volume": [5_000] * 20, "close": [2.0] * 20})
    assert e._passes_liquidity_gate("PENNY", {"PENNY": df}) is False


def test_share_count_fallback_when_no_price():
    """No close column -> fall back to share-count floor."""
    e = _engine(min_shares=100_000)
    below = pd.DataFrame({"volume": [50_000] * 20})
    assert e._passes_liquidity_gate("X", {"X": below}) is False
    above = pd.DataFrame({"volume": [200_000] * 20})
    assert e._passes_liquidity_gate("Y", {"Y": above}) is True


def test_dollar_floor_disabled_uses_share_count():
    """_MIN_AVG_DOLLAR_VOLUME=0 -> legacy share-count behavior (back-compat)."""
    e = _engine(min_dollar=0.0, min_shares=500_000)
    df = pd.DataFrame({"volume": [100_000] * 20, "close": [50.0] * 20})  # $5M but
    assert e._passes_liquidity_gate("LEE", {"LEE": df}) is False  # 100k < 500k shares


def test_fail_closed_preserved():
    e = _engine()
    assert e._passes_liquidity_gate("Z", {}) is False
    assert e._passes_liquidity_gate("Z", {"Z": pd.DataFrame({"volume": [1] * 19})}) is False
