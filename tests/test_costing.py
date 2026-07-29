"""Task A: costed P&L helper — realistic round-trip cost applied to the book."""
from __future__ import annotations

import pandas as pd

from backend.organism.costing import apply_costs, costed_summary


def _df():
    # 2 trades: +$10 gross on 100sh @ $50; -$4 gross on 100sh @ $50.
    return pd.DataFrame({
        "entry_price": [50.0, 50.0],
        "shares": [100, 100],
        "pnl": [10.0, -4.0],
    })


def test_apply_costs_round_trip():
    out = apply_costs(_df(), bps=3.0)
    # cost = 3/1e4 * 50 * 100 = $1.50 per trade
    assert abs(out["cost"].iloc[0] - 1.5) < 1e-9
    assert abs(out["net_pnl"].iloc[0] - 8.5) < 1e-9   # 10 - 1.5
    assert abs(out["net_pnl"].iloc[1] - (-5.5)) < 1e-9  # -4 - 1.5


def test_costed_summary_shape_and_values():
    s = costed_summary(_df(), bps=3.0)
    assert s["n"] == 2
    assert s["gross_pnl"] == 6.0          # 10 - 4
    assert s["net_pnl"] == 3.0            # 8.5 - 5.5
    assert s["cost_bps"] == 3.0
    assert s["win_rate"] == 0.5
    assert "t_stat" in s and "profit_factor" in s


def test_zero_cost_equals_gross():
    s = costed_summary(_df(), bps=0.0)
    assert s["net_pnl"] == s["gross_pnl"] == 6.0


def test_empty_and_missing():
    assert costed_summary(pd.DataFrame())["n"] == 0
    assert costed_summary(pd.DataFrame({"x": [1]}))["n"] == 0
