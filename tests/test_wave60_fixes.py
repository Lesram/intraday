"""V11 prep / Wave-60 (2026-05-03): DD4-3 inverse-ETF effective_regime helper.

Locks the regression for V8 DD2-6 / V10 DD4-3 (deferred since V8): the
inverse-ETF regime flip lived only in alpha_scanner._regime_alignment.
Kelly._regime_scale and AdaptiveExits REGIME_* lookups saw the
un-flipped market regime, producing inconsistent semantics for SH/PSQ
trades.

Wave-60 ships a single canonical helper
`backend.organism.regime.effective_regime_for_symbol(regime, symbol)`
and wires it into Kelly + AdaptiveExits.

Run with: ./venv/bin/python -m pytest tests/test_wave60_fixes.py -v
"""
from __future__ import annotations

import inspect


def test_dd4_3_helper_exists():
    """Canonical helper must be importable."""
    from backend.organism.regime import (
        effective_regime_for_symbol,
        is_inverse_etf,
        _INVERSE_ETFS,
    )
    # Sanity inverse-ETF set.
    assert "SH" in _INVERSE_ETFS
    assert "PSQ" in _INVERSE_ETFS
    assert "AAPL" not in _INVERSE_ETFS


def test_dd4_3_inverse_etf_swaps_trending_directions():
    from backend.organism.regime import effective_regime_for_symbol
    # SH trending_up → trending_down (long SH = short S&P, so up is bad)
    assert effective_regime_for_symbol("trending_up", "SH") == "trending_down"
    assert effective_regime_for_symbol("trending_down", "SH") == "trending_up"
    # Pass-through for non-trending regimes.
    assert effective_regime_for_symbol("chop", "SH") == "chop"
    assert effective_regime_for_symbol("high_vol", "PSQ") == "high_vol"


def test_dd4_3_normal_symbol_unchanged():
    from backend.organism.regime import effective_regime_for_symbol
    assert effective_regime_for_symbol("trending_up", "AAPL") == "trending_up"
    assert effective_regime_for_symbol("trending_down", "AAPL") == "trending_down"
    assert effective_regime_for_symbol("chop", "MSFT") == "chop"


def test_dd4_3_kelly_uses_effective_regime():
    """Kelly's _regime_scale path now consults effective_regime_for_symbol."""
    from backend.organism import kelly_sizer
    src = inspect.getsource(kelly_sizer)
    assert "Wave-60" in src and "effective_regime_for_symbol" in src, (
        "DD4-3 regression: Kelly no longer uses effective_regime_for_symbol; "
        "SH/PSQ trades will be sized against un-flipped regime again."
    )


def test_dd4_3_adaptive_exits_uses_effective_regime():
    """AdaptiveExitEngine.create_exit_levels uses effective_regime_for_symbol."""
    from backend.organism import adaptive_exits
    src = inspect.getsource(adaptive_exits)
    assert "Wave-60" in src and "effective_regime_for_symbol" in src, (
        "DD4-3 regression: AdaptiveExits no longer uses "
        "effective_regime_for_symbol; SH/PSQ stop math diverges from "
        "AlphaScanner."
    )
