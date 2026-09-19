"""Task D: symmetric short side in _observable_direction (flag-gated, default off)."""
from __future__ import annotations

import pandas as pd

import backend.organism.alpha_scanner as als
from backend.organism.alpha_scanner import AlphaScanner


def _row(**kw):
    base = dict(ret_5d=0.0, ret_20d=0.0, comp_breakout_readiness=0.0,
               comp_squeeze_momentum=0.0, trend_strength=0.0)
    base.update(kw)
    return pd.Series(base)


def _scanner():
    return AlphaScanner(top_n=5)


def test_default_off_is_asymmetric(monkeypatch):
    monkeypatch.setattr(als, "SYMMETRIC_SHORT_ENABLED", False)
    s = _scanner()
    # Bearish 20d + negative trend but ret_5d flat -> OLD logic returns 0 (no short).
    assert s._observable_direction(_row(ret_20d=-0.02, trend_strength=-1.0)) == 0.0
    # Negative squeeze alone -> OLD logic returns 0.
    assert s._observable_direction(_row(comp_squeeze_momentum=-0.8)) == 0.0
    # The one old short path still works.
    assert s._observable_direction(_row(ret_5d=-0.01)) == -1.0


def test_symmetric_on_adds_bearish_paths(monkeypatch):
    monkeypatch.setattr(als, "SYMMETRIC_SHORT_ENABLED", True)
    s = _scanner()
    # Mirror bearish_momentum: ret_20d<-1% & trend<=0 -> short.
    assert s._observable_direction(_row(ret_20d=-0.02, trend_strength=-1.0)) == -1.0
    # bearish_breakdown: strong negative squeeze -> short.
    assert s._observable_direction(_row(comp_squeeze_momentum=-0.8)) == -1.0
    # ret_5d short path still works.
    assert s._observable_direction(_row(ret_5d=-0.01)) == -1.0


def test_bullish_unchanged_both_modes(monkeypatch):
    for flag in (False, True):
        monkeypatch.setattr(als, "SYMMETRIC_SHORT_ENABLED", flag)
        s = _scanner()
        assert s._observable_direction(_row(comp_breakout_readiness=0.7)) == 1.0   # bullish_breakout
        assert s._observable_direction(_row(ret_5d=0.01)) == 1.0                    # bullish_momentum
        assert s._observable_direction(_row()) == 0.0                               # flat -> neutral
