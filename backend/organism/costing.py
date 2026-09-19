"""Costed P&L helper (work order Task A, 2026-06-25).

The recorded book is priced on bar-close MIDS — the broker submission returns no
avg_fill_price, so the fill recorder stamps price_source="bar_close" on 556/567
trades. There is no spread/slippage/commission anywhere in the recorded P&L, so
every prior read was flattered. This applies a realistic round-trip cost so the
scoreboard (EOD report, backtests, edge reads) is honest.

cost(per trade) = bps/1e4 * entry_price * |shares|   (round-trip, default 3 bps)
"""
from __future__ import annotations

import os

import pandas as pd

DEFAULT_COST_BPS = float(os.getenv("ORGANISM_COST_BPS", "3.0"))  # round-trip


def apply_costs(df: pd.DataFrame, bps: float = DEFAULT_COST_BPS) -> pd.DataFrame:
    """Return a copy with `cost` and `net_pnl` columns added."""
    out = df.copy()
    ep = pd.to_numeric(out.get("entry_price"), errors="coerce")
    sh = pd.to_numeric(out.get("shares"), errors="coerce").abs()
    out["cost"] = (bps / 1e4) * ep * sh
    out["net_pnl"] = pd.to_numeric(out["pnl"], errors="coerce") - out["cost"]
    return out


def _tstat(x: pd.Series) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    sd = float(x.std(ddof=1))
    return float(x.mean() / (sd / (n ** 0.5))) if sd > 0 else 0.0


def costed_summary(df: pd.DataFrame, bps: float = DEFAULT_COST_BPS) -> dict:
    """Costed {n, gross_pnl, net_pnl, expectancy, profit_factor, win_rate, t_stat}.

    Drops rows with non-finite pnl/entry_price. Returns {"n": 0} if empty.
    """
    if df is None or len(df) == 0 or "pnl" not in df.columns:
        return {"n": 0}
    d = apply_costs(df, bps).dropna(subset=["net_pnl"])
    net = d["net_pnl"]
    n = len(net)
    if n == 0:
        return {"n": 0}
    wins, losses = net[net > 0], net[net < 0]
    gl = float(abs(losses.sum()))
    return {
        "n": n,
        "cost_bps": bps,
        "gross_pnl": round(float(pd.to_numeric(d["pnl"], errors="coerce").sum()), 2),
        "net_pnl": round(float(net.sum()), 2),
        "expectancy": round(float(net.mean()), 4),
        "t_stat": round(_tstat(net), 3),
        "profit_factor": round(float(wins.sum()) / gl, 4) if gl > 0 else None,
        "win_rate": round(float((net > 0).mean()), 4),
    }
