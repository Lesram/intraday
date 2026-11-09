"""Pre-registered gap-up momentum test (PREREG_gap_up.md, sha256 465835ee...).

    python gap_up_test.py fetch-daily    --env /path/to/.env
    python gap_up_test.py fetch-sessions --env /path/to/.env [--budget 160]   # resumable
    python gap_up_test.py build
    python gap_up_test.py analyze

Full-market (SIP) 1-minute bars 09:30-14:02 ET for the 20 live symbols, sessions
2024-01-02..2026-10-20, plus split-adjusted daily bars for the SPY gap. Costs
3 bps per side. Prints the cell tables; the primary cell is G+ x E1 x H30, OOS.

Run on 2026-10-21: DEAD (results/gap_up_test.txt).
"""
from __future__ import annotations

import argparse
import json
import pickle
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from alpaca_bars import LIVE_SYMBOLS, get_bars, load_keys

ET, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")
SIDE = 3e-4                     # 3 bps per side


def fetch_daily(d: Path, env: str) -> None:
    key, sec = load_keys(env)
    bars = get_bars({"symbols": ",".join(LIVE_SYMBOLS), "timeframe": "1Day", "start": "2023-12-01T00:00:00Z",
                     "end": "2026-10-21T00:00:00Z", "feed": "sip", "limit": "10000", "adjustment": "split"}, key, sec)
    (d / "daily.json").write_text(json.dumps(bars))
    print("daily bars:", sum(len(v) for v in bars.values()))


def fetch_sessions(d: Path, env: str, budget: float) -> None:
    t0 = time.time()
    key, sec = load_keys(env)
    days = sorted({b["t"][:10] for b in json.loads((d / "daily.json").read_text())["SPY"]
                   if "2024-01-02" <= b["t"][:10] <= "2026-10-20"})
    (d / "intraday").mkdir(exist_ok=True)
    done = 0
    for day in days:
        f = d / "intraday" / f"{day}.json"
        if f.exists():
            continue
        if time.time() - t0 > budget:
            break
        y, m, dd = map(int, day.split("-"))
        s = datetime(y, m, dd, 9, 30, tzinfo=ET).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        e = datetime(y, m, dd, 14, 2, tzinfo=ET).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        bars = get_bars({"symbols": ",".join(LIVE_SYMBOLS), "timeframe": "1Min", "start": s, "end": e,
                         "feed": "sip", "limit": "10000", "adjustment": "raw", "sort": "asc"}, key, sec)
        f.write_text(json.dumps(bars))
        done += 1
        time.sleep(0.25)
    have = len(list((d / "intraday").glob("*.json")))
    print(f"fetched {done} this run; {have}/{len(days)} sessions on disk; {time.time() - t0:.0f}s")


def build(d: Path) -> None:
    parts = []
    for f in sorted((d / "intraday").glob("*.json")):
        for s, b in json.loads(f.read_text()).items():
            df = pd.DataFrame(b, columns=["t", "o", "h", "l", "c", "v"])
            t = pd.to_datetime(df["t"], utc=True).dt.tz_convert("America/New_York")
            df["mod"] = (t.dt.hour * 60 + t.dt.minute).astype("int16")
            df["d"] = f.stem
            df["sym"] = s
            parts.append(df[["d", "sym", "mod", "o", "h", "l", "c"]])
    bars = pd.concat(parts, ignore_index=True)
    bars = bars[(bars["mod"] >= 570) & (bars["mod"] <= 842)].sort_values(["sym", "d", "mod"]).reset_index(drop=True)
    pickle.dump(bars, open(d / "bars.pkl", "wb"))
    print(len(bars), "bars;", bars.d.nunique(), "sessions;", bars.sym.nunique(), "symbols")


def analyze(d: Path) -> None:
    bars = pickle.load(open(d / "bars.pkl", "rb"))
    spy = pd.DataFrame(json.loads((d / "daily.json").read_text())["SPY"])
    spy["d"] = spy["t"].str[:10]
    spy = spy.set_index("d")
    gap = spy["o"] / spy["c"].shift(1) - 1

    g = bars.groupby(["sym", "d"], sort=False)
    bars["ret5"] = bars["c"] / g["c"].shift(5) - 1
    bars["ret20"] = bars["c"] / g["c"].shift(20) - 1
    pc = g["c"].shift(1)
    tr = pd.concat([bars.h - bars.l, (bars.h - pc).abs(), (bars.l - pc).abs()], axis=1).max(axis=1)
    bars["atr"] = tr.groupby([bars.sym, bars.d], sort=False).transform(lambda x: x.rolling(14, min_periods=14).mean())

    trades = []
    for (s, day), x in bars.groupby(["sym", "d"], sort=False):
        mod = x["mod"].astype(int).tolist()
        o, c = x["o"].to_numpy(), x["c"].to_numpy()
        r5, r20, atr = x["ret5"].to_numpy(), x["ret20"].to_numpy(), x["atr"].to_numpy()
        pos = {m: i for i, m in enumerate(mod)}

        def add(rule: str, i: int) -> None:    # decision at close of bar i; entry = next bar's open
            if i + 1 >= len(mod):
                return
            e = i + 1
            me = mod[e]
            for H in (15, 30, 60):
                j = pos.get(me + H)
                if j is None:
                    continue
                gross = c[j] / o[e] - 1
                row = {"sym": s, "d": day, "rule": rule, "H": H, "gross": gross}
                if rule == "E1" and H == 30 and np.isfinite(atr[i]):
                    stop = o[e] - 3.5 * atr[i] * 0.78
                    k = next((k for k in range(e, j + 1) if c[k] <= stop), None)
                    row["gross_stop"] = (c[k] / o[e] - 1) if k is not None else gross
                trades.append(row)

        i0 = pos.get(599)                      # bar stamped 09:59 closes at 10:00
        if i0 is not None:
            add("E0", i0)
        last = -10_000
        for i, m in enumerate(mod):            # decisions at bar closes 10:00 <= t < 13:00
            if 599 <= m <= 778 and ((r5[i] > 0.005) or (r20[i] > 0.010)):
                if m - last >= 30:
                    add("E1", i)
                    last = m

    t = pd.DataFrame(trades)
    t["gap"] = t["d"].map(gap)
    t["bucket"] = np.select([t.gap >= 0.005, t.gap >= 0.003, t.gap.abs() < 0.003, t.gap <= -0.003],
                            ["G++", "G+", "G0", "G-"], "NA")
    t["period"] = np.where(t["d"] < "2025-01-01", "IS", "OOS")
    pickle.dump(t, open(d / "trades.pkl", "wb"))

    def cell(df: pd.DataFrame, col: str = "gross") -> dict:
        net = df[col] - 2 * SIDE
        per = net.groupby(df["d"]).mean()
        n_s = len(per)
        tt = per.mean() / (per.std(ddof=1) / np.sqrt(n_s)) if n_s > 2 and per.std(ddof=1) > 0 else np.nan
        return {"n": len(df), "sessions": n_s, "gross_bps": 1e4 * df[col].mean(), "net_bps": 1e4 * net.mean(),
                "net_3rt_bps": 1e4 * (df[col].mean() - SIDE), "t_sess": tt, "hit%": 100 * (net > 0).mean()}

    def table(rule: str, H: int, col: str = "gross") -> pd.DataFrame:
        out = {}
        if col not in t.columns:
            return pd.DataFrame()
        for per in ("IS", "OOS", "ALL"):
            for b in ("G++", "G+", "G0", "G-"):
                sel = (t.rule == rule) & (t.H == H)
                if per != "ALL":
                    sel &= t.period == per
                sel &= (t.bucket == b) if b != "G+" else t.bucket.isin(["G+", "G++"])   # G+ = gap >= +0.30%
                df = t[sel].dropna(subset=[col])
                if len(df):
                    out[(per, b)] = cell(df, col)
        return pd.DataFrame(out).T.round(2)

    pd.set_option("display.width", 200)
    print("sessions by bucket (SPY gap):", t.drop_duplicates("d").bucket.value_counts().to_dict())
    for rule, H, col in [("E1", 30, "gross"), ("E1", 15, "gross"), ("E1", 60, "gross"),
                         ("E1", 30, "gross_stop"), ("E0", 60, "gross"), ("E0", 30, "gross")]:
        tag = "with 3.5xATR(IEX-like) close stop" if col == "gross_stop" else ""
        print(f"\n=== {rule} H{H} {tag}")
        print(table(rule, H, col).to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["fetch-daily", "fetch-sessions", "build", "analyze"])
    ap.add_argument("--env", default=".env")
    ap.add_argument("--data-dir", default="data/gap")
    ap.add_argument("--budget", type=float, default=1e9, help="stop fetching after this many seconds")
    a = ap.parse_args()
    d = Path(a.data_dir)
    d.mkdir(parents=True, exist_ok=True)
    {"fetch-daily": lambda: fetch_daily(d, a.env),
     "fetch-sessions": lambda: fetch_sessions(d, a.env, a.budget),
     "build": lambda: build(d),
     "analyze": lambda: analyze(d)}[a.cmd]()


if __name__ == "__main__":
    main()
