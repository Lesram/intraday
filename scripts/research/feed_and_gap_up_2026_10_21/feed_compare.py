"""IEX vs full-market (SIP) 1-minute bars for the live universe.

    python feed_compare.py fetch   --env /path/to/.env --start 2026-09-14T08:00:00Z --end 2026-10-21T00:00:00Z
    python feed_compare.py compare --out iex_vs_sip_summary.csv

``fetch`` writes bars_iex.json and bars_sip.json (all hours) to --data-dir.
``compare`` measures, per symbol, over every session after the first (the first
is warm-up), the things the engine's indicators depend on: regular-hours bar
coverage, volume share, close agreement, 1-minute range and 14-bar ATR ratios,
the regime ATR bucket, the momentum buy trigger, 2x volume surges, the time a
200-bar window spans, and pre-market bars. Windows count bars, as the engine
does. Prints aggregates only.

Run on 2026-10-21 for 2026-09-15..2026-10-20 (26 sessions, all EDT): results in
results/feed_compare.txt.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from alpaca_bars import LIVE_SYMBOLS, fetch_minute_bars, load_keys

HI, LO = 0.0020, 0.00076   # regime atr_14/price thresholds: 0.04/sqrt(390), 0.015/sqrt(390)
ET = "America/New_York"


def frame(bars: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(bars)
    if df.empty:
        return df
    df["t"] = pd.to_datetime(df["t"], utc=True)
    df = df.sort_values("t").reset_index(drop=True)
    h, l, c, v = df["h"], df["l"], df["c"], df["v"]
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["ret5"] = c / c.shift(5) - 1
    df["ret20"] = c / c.shift(20) - 1
    df["surge"] = v.rolling(3).max() / v.shift(3).rolling(10).mean()
    df["span200"] = (df["t"] - df["t"].shift(199)).dt.total_seconds() / 60
    return df


def bucket(x):
    return np.where(x > HI, 2, np.where(x < LO, 0, 1))


def et(day: str, hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"{day} {hhmm}", tz=ET).tz_convert("UTC")


def compare(data_dir: Path) -> pd.DataFrame:
    iex = json.loads((data_dir / "bars_iex.json").read_text())
    sip = json.loads((data_dir / "bars_sip.json").read_text())
    spy = frame(sip["SPY"])
    spy_et = spy["t"].dt.tz_convert(ET)
    rth = spy[(spy_et.dt.strftime("%H:%M") >= "09:30") & (spy_et.dt.strftime("%H:%M") < "16:00")]
    days = sorted(rth["t"].dt.tz_convert(ET).dt.strftime("%Y-%m-%d").unique())[1:]
    rows = []
    for s in LIVE_SYMBOLS:
        fi, fs = frame(iex.get(s, [])), frame(sip.get(s, []))
        acc = {k: [] for k in ("cov_i", "cov_s", "vshare", "pre_i", "pre_s", "span_i", "span_s")}
        common, grid_all = [], []
        for d in days:
            r0, r1, p0, at = et(d, "09:30"), et(d, "16:00"), et(d, "04:00"), et(d, "15:00")
            ri = fi[(fi.t >= r0) & (fi.t < r1)]
            rs = fs[(fs.t >= r0) & (fs.t < r1)]
            acc["cov_i"].append(len(ri) / 390)
            acc["cov_s"].append(len(rs) / 390)
            acc["vshare"].append(ri.v.sum() / max(rs.v.sum(), 1))
            acc["pre_i"].append(int(((fi.t >= p0) & (fi.t < r0)).sum()))
            acc["pre_s"].append(int(((fs.t >= p0) & (fs.t < r0)).sum()))
            acc["span_i"].append(float(fi[fi.t <= at].span200.iloc[-1]))
            acc["span_s"].append(float(fs[fs.t <= at].span200.iloc[-1]))
            common.append(ri.merge(rs, on="t", suffixes=("_i", "_s")))
            g = pd.DataFrame({"g": pd.date_range(et(d, "10:00"), et(d, "15:44"), freq="1min")})
            a = pd.merge_asof(g, fi.rename(columns={"t": "ti"}), left_on="g", right_on="ti", direction="backward")
            b = pd.merge_asof(g, fs.rename(columns={"t": "ts"}), left_on="g", right_on="ts", direction="backward")
            grid_all.append(pd.concat([a.add_suffix("_i"), b.add_suffix("_s")], axis=1))
        m = pd.concat(common)
        G = pd.concat(grid_all)
        cd = (m.c_i - m.c_s).abs() / m.c_s * 1e4
        rr = ((m.h_i - m.l_i) / (m.h_s - m.l_s)).replace([np.inf, -np.inf], np.nan)[(m.h_s - m.l_s) > 0]
        ar = (G.atr_i / G.atr_s).replace([np.inf, -np.inf], np.nan)
        bi, bs = bucket(G.atr_i / G.c_i), bucket(G.atr_s / G.c_s)
        ti = (G.ret5_i > 0.005) | (G.ret20_i > 0.010)
        ts_ = (G.ret5_s > 0.005) | (G.ret20_s > 0.010)
        si, ss = G.surge_i > 2.0, G.surge_s > 2.0
        age = (G.g_i - G.ti_i).dt.total_seconds() / 60
        rows.append({
            "sym": s,
            "cov_iex%": 100 * np.mean(acc["cov_i"]), "cov_sip%": 100 * np.mean(acc["cov_s"]),
            "vol_share%": 100 * np.mean(acc["vshare"]), "iex_bar_age>1m%": 100 * np.mean(age > 1.0),
            "close_bps_med": cd.median(), "close_bps_p95": cd.quantile(0.95),
            "range_ratio_med": rr.median(), "atr_ratio_med": ar.median(),
            "atr_ratio_p10": ar.quantile(0.10), "atr_ratio_p90": ar.quantile(0.90),
            "volbucket_disagree%": 100 * np.mean(bi != bs),
            "hi_vol_iex%": 100 * np.mean(bi == 2), "hi_vol_sip%": 100 * np.mean(bs == 2),
            "lo_vol_iex%": 100 * np.mean(bi == 0), "lo_vol_sip%": 100 * np.mean(bs == 0),
            "buy_trig_iex": int(ti.sum()), "buy_trig_sip": int(ts_.sum()), "trig_disagree%": 100 * np.mean(ti != ts_),
            "surge_iex": int(si.sum()), "surge_sip": int(ss.sum()), "surge_both": int((si & ss).sum()),
            "span200_iex_min": np.mean(acc["span_i"]), "span200_sip_min": np.mean(acc["span_s"]),
            "pre_bars_iex": np.mean(acc["pre_i"]), "pre_bars_sip": np.mean(acc["pre_s"]),
            "grid_n": len(G),
        })
    return pd.DataFrame(rows).set_index("sym").sort_values("cov_iex%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch", "compare"])
    ap.add_argument("--env", default=".env")
    ap.add_argument("--start", default="2026-09-14T08:00:00Z")
    ap.add_argument("--end", default="2026-10-21T00:00:00Z")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out", default="iex_vs_sip_summary.csv")
    a = ap.parse_args()
    d = Path(a.data_dir)
    d.mkdir(parents=True, exist_ok=True)
    if a.cmd == "fetch":
        key, sec = load_keys(a.env)
        for feed in ("iex", "sip"):
            bars = fetch_minute_bars(a.start, a.end, feed, key, sec)
            (d / f"bars_{feed}.json").write_text(json.dumps(bars))
            print(feed, "bars", sum(len(v) for v in bars.values()))
        return
    out = compare(d)
    out.to_csv(a.out)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(out.round(2).to_string())
    print("\nMEDIAN across symbols:")
    print(out.median().round(3).to_string())


if __name__ == "__main__":
    main()
