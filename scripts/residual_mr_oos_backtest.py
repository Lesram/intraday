#!/usr/bin/env python3
"""Costed, out-of-sample backtest of the ResidualMeanReversionEngine signal.

The residual MR engine (shadow-only, never measured by the audit — the audit
rated the PLAIN MR scanner net-negative) signals when a stock's idiosyncratic
residual z-score is extreme. Residual = stock_ret - (0.45*bspy*SPY +
0.25*bqqq*QQQ + 0.30*bsec*SECTOR), z-scored over a 120-bar lookback; long-only
entry when z <= -2.0; intended 20-bar hold. Market-neutral pnl = the forward
RESIDUAL return over the hold (beta hedged out), using betas fixed at entry.

This is the honest read: 72 OOS sessions (broad_corpus_v2, RTH), overnight gaps
masked, gross + net at a cost grid. Verdict = does net clear 0 at t>=2.
"""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.organism.engines.residual_mean_reversion import (
    SECTOR_ETF_MAP,
    ResidualMeanReversionConfig,
)
from backend.organism.sector_map import get_sector

CFG = ResidualMeanReversionConfig()
LOOKBACK, ZTHRESH, HORIZON = CFG.lookback_bars, CFG.min_abs_residual_z, CFG.intended_horizon_bars
EXCLUDE = set(CFG.exclude_symbols)


def main() -> None:
    bars = pickle.load(open(ROOT / "artifacts/broad_corpus_v2/bars.pkl", "rb"))
    closes = {}
    for sym, df in bars.items():
        d = df.copy()
        d["_ts"] = pd.to_datetime(d["timestamp"], utc=True)
        closes[sym] = d.sort_values("_ts").drop_duplicates("_ts").set_index("_ts")["close"].astype(float)
    panel = pd.DataFrame(closes).sort_index()
    rets = panel.pct_change()
    # Mask overnight/session-boundary returns (gap > 5 min) so they don't
    # pollute the minute-return regression or forward sums.
    gap = (panel.index.to_series().diff() > pd.Timedelta(minutes=5)).values
    rets.loc[gap, :] = np.nan

    spy, qqq = rets.get("SPY"), rets.get("QQQ")
    if spy is None or qqq is None:
        raise SystemExit("corpus missing SPY/QQQ factors")

    def roll_beta(y, x, w):
        return y.rolling(w).cov(x) / x.rolling(w).var(ddof=0).replace(0, np.nan)

    HORIZONS = (10, 20, 40)
    ZGRID = (2.0, 2.5, 3.0)
    # collect, per (z, horizon), the list of market-neutral forward returns
    buckets = {(zt, h): [] for zt in ZGRID for h in HORIZONS}
    by_symbol = {}
    for sym in panel.columns:
        if sym in EXCLUDE:
            continue
        sec_etf = SECTOR_ETF_MAP.get(get_sector(sym), "SPY")
        rsec = rets[sec_etf] if sec_etf in rets.columns else spy
        r = rets[sym]
        bspy, bqqq, bsec = roll_beta(r, spy, LOOKBACK), roll_beta(r, qqq, LOOKBACK), roll_beta(r, rsec, LOOKBACK)
        resid = r - (0.45 * bspy * spy + 0.25 * bqqq * qqq + 0.30 * bsec * rsec)
        z = (resid - resid.rolling(LOOKBACK).mean()) / resid.rolling(LOOKBACK).std(ddof=0).replace(0, np.nan)
        rv, spv, qqv, scv = r.values, spy.values, qqq.values, rsec.values
        bsv, bqv, bcv, zv = bspy.values, bqqq.values, bsec.values, z.values
        n = len(r)
        for i in np.where(zv <= -2.0)[0]:  # long-only, widest gate; filter per-z below
            bs, bq, bc = bsv[i], bqv[i], bcv[i]
            if not (np.isfinite(bs) and np.isfinite(bq) and np.isfinite(bc)):
                continue
            for h in HORIZONS:
                if i + 1 + h >= n:
                    continue
                sl = slice(i + 1, i + 1 + h)
                mn = np.nansum(rv[sl] - (0.45 * bs * spv[sl] + 0.25 * bq * qqv[sl] + 0.30 * bc * scv[sl]))
                if not np.isfinite(mn):
                    continue
                for zt in ZGRID:
                    if zv[i] <= -zt:
                        buckets[(zt, h)].append(mn)
                if h == HORIZON and zv[i] <= -ZTHRESH:
                    by_symbol.setdefault(sym, []).append(mn)

    def stats(x):
        x = np.asarray(x)
        nn = len(x)
        if nn == 0:
            return (0, 0.0, 0.0, 0.0)
        m, sd = float(x.mean()), (float(x.std(ddof=1)) if nn > 1 else 0.0)
        ts = m / (sd / np.sqrt(nn)) if sd > 0 else 0.0
        return (nn, m, ts, float((x > 0).mean()))

    print("=== Residual MR OOS backtest (broad_corpus_v2, 72 sessions, RTH) ===")
    print(f"params: lookback={LOOKBACK} long-only, 15 tradeable names (ETFs/factors excluded)")
    print("market-neutral pnl = forward residual return; gross + net at realistic cost.\n")
    print(f"{'z<=-':>5} {'hold':>5} {'n':>6} {'gross(bps)':>11} {'t':>6} {'win':>6} "
          f"{'net@4bps':>9} {'t@4':>6} {'verdict':>9}")
    for zt in ZGRID:
        for h in HORIZONS:
            g = np.array(buckets[(zt, h)]) * 10000.0
            nn, mm, ts, wr = stats(g)
            nnn, m4, t4, _ = stats(g - 4.0)  # ~realistic market-neutral round-trip
            verdict = "EDGE" if (m4 > 0 and t4 >= 2) else "no edge"
            print(f"{zt:>5} {h:>5} {nn:>6} {mm:>11.2f} {ts:>6.2f} {wr:>5.1%} "
                  f"{m4:>9.2f} {t4:>6.2f} {verdict:>9}")

    print("\nper-symbol gross at z<=-2.0/hold20 (bps/trade, n):")
    for s, arr in sorted(by_symbol.items(), key=lambda kv: -np.mean(kv[1])):
        a = np.array(arr)
        print(f"  {s:6} {a.mean()*10000:8.2f}  (n={len(a)})")


if __name__ == "__main__":
    main()
