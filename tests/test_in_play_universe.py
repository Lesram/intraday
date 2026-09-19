"""Phase 1 step 9 — dynamic in-play universe selector."""
from __future__ import annotations

import pandas as pd

from backend.organism.strategies.in_play_universe import (
    rank_in_play, relative_volume, select_in_play_universe,
)


def _df(base_vol, recent_vol, n=400, recent=5):
    vol = [base_vol] * (n - recent) + [recent_vol] * recent
    return pd.DataFrame({"close": [100.0] * n, "volume": vol})


def test_relative_volume_basic():
    assert relative_volume(_df(100, 300)) == 3.0      # 3x baseline
    assert relative_volume(_df(100, 100)) == 1.0      # normal
    assert relative_volume(pd.DataFrame({"volume": [1, 2]})) == 0.0  # too short


def test_rank_orders_by_rv_and_excludes_spy():
    feats = {
        "HOT": _df(100, 400),    # 4x
        "WARM": _df(100, 200),   # 2x
        "COLD": _df(100, 100),   # 1x
        "SPY": _df(100, 999),    # benchmark — excluded regardless
    }
    ranked = rank_in_play(feats)
    syms = [s for s, _ in ranked]
    assert "SPY" not in syms
    assert syms == ["HOT", "WARM", "COLD"]            # descending RV


def test_select_applies_min_rv_and_top_k():
    feats = {
        "A": _df(100, 400),  # 4x
        "B": _df(100, 200),  # 2x
        "C": _df(100, 130),  # 1.3x -> below 1.5 gate
        "D": _df(100, 300),  # 3x
    }
    sel = select_in_play_universe(feats, top_k=2, min_rv=1.5)
    assert sel == ["A", "D"]                           # top-2 above gate, RV-ranked
    # nothing clears a high gate -> stand down (empty)
    assert select_in_play_universe(feats, top_k=10, min_rv=9.0) == []
