"""Replay the installed regime label on IEX bars and on SIP bars, minute by minute.

    PYTHONPATH=<repo root> python regime_replay.py --data-dir data [--logs-dir ~/VS/intra/logs/sessions]

Uses the bars written by ``feed_compare.py fetch``. The detector is the
installed ``backend.organism.regime.RegimeDetector``, built exactly as the live
engine builds it (``is_intraday=True, bars_per_day=390``) and called through
``detect_cross_asset_regime`` with XLK/XLE as sector features. Each minute's
frames are the last 500 bars completed by that minute (close, volume, and
``atr_14`` = 14-bar mean true range / close, as ``ml_features`` computes it).
This loads the regime module read-only to reproduce its label; it writes no
state and touches no live path.

With --logs-dir, sessions on or after 2026-10-19 (the release this replays) are
also compared with the live tick labels ("Organism tick: regime=...").

Run on 2026-10-21: the IEX replay matched the live label on every minute of
2026-10-19 and 2026-10-20 (09:45-15:44 ET); results in results/regime_replay.txt.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from alpaca_bars import LIVE_SYMBOLS
from backend.organism.regime import RegimeDetector

ET = "America/New_York"
UNIVERSE = LIVE_SYMBOLS  # same order as the brain's universe_selector.active list


def frames(path: Path):
    raw = json.loads(path.read_text())
    out = {}
    for s in UNIVERSE:
        df = pd.DataFrame(raw.get(s, []))
        df["t"] = pd.to_datetime(df["t"], utc=True)
        df = df.sort_values("t").reset_index(drop=True)
        pc = df["c"].shift(1)
        tr = pd.concat([df["h"] - df["l"], (df["h"] - pc).abs(), (df["l"] - pc).abs()], axis=1).max(axis=1)
        f = pd.DataFrame({"close": df["c"], "volume": df["v"].astype(float),
                          "atr_14": tr.rolling(14, min_periods=1).mean() / df["c"].replace(0, 1e-10)})
        out[s] = (df["t"].dt.tz_convert(None).dt.as_unit("ns").to_numpy(), f, df)
    return out


def replay(fr, day: str) -> dict[str, str]:
    det = RegimeDetector(is_intraday=True, bars_per_day=390)
    lab = {}
    start = pd.Timestamp(f"{day} 09:30", tz=ET)
    for g in pd.date_range(start, start + pd.Timedelta(minutes=389), freq="1min"):
        cutoff = (g - pd.Timedelta(minutes=1)).tz_convert(None).to_datetime64()
        fbs = {}
        for s, (ts, f, _) in fr.items():
            n = int(np.searchsorted(ts, cutoff, side="right"))
            if n >= 10:
                fbs[s] = f.iloc[max(0, n - 500):n]
        sec = {s: fbs[s] for s in det.SECTOR_ETFS if s in fbs and len(fbs[s]) >= 10}
        st = det.detect_cross_asset_regime(fbs, sector_features=sec) if sec else det.detect_market_regime(fbs)
        lab[g.strftime("%H:%M")] = str(st.primary)
    return lab


def live_labels(logs_dir: Path | None, day: str) -> dict[str, str]:
    if logs_dir is None or day < "2026-10-19":
        return {}
    p = logs_dir / f"{day}.jsonl"
    if not p.exists():
        return {}
    pat = re.compile(r"Organism tick: regime=(\w+)")
    per_min = collections.defaultdict(collections.Counter)
    for line in open(p):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = pat.search(e.get("message", ""))
        if m:
            t = pd.Timestamp(e["timestamp"]).tz_convert(ET)
            per_min[t.strftime("%H:%M")][m[1]] += 1
    return {k: c.most_common(1)[0][0] for k, c in per_min.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--logs-dir", default=None)
    ap.add_argument("--out", default="regime_replay.csv")
    a = ap.parse_args()
    d = Path(a.data_dir)
    fi, fs = frames(d / "bars_iex.json"), frames(d / "bars_sip.json")
    spy = fs["SPY"][2]
    spy_et = spy["t"].dt.tz_convert(ET)
    in_rth = (spy_et.dt.strftime("%H:%M") >= "09:30") & (spy_et.dt.strftime("%H:%M") < "16:00")
    spy_rth = spy[in_rth].assign(day=spy_et[in_rth].dt.strftime("%Y-%m-%d"))
    days = sorted(spy_rth.day.unique())[1:]          # first session = warm-up only
    logs = Path(a.logs_dir).expanduser() if a.logs_dir else None
    rows = []
    for day in days:
        prev = spy_rth[spy_rth.day < day].iloc[-1]
        today = spy_rth[spy_rth.day == day]
        li, ls, lv = replay(fi, day), replay(fs, day), live_labels(logs, day)
        w = [m for m in sorted(li) if "09:45" <= m <= "15:44"]
        r = {"day": day, "spy_gap%": 100 * (today.o.iloc[0] / prev.c - 1),
             "spy_day%": 100 * (today.c.iloc[-1] / today.o.iloc[0] - 1)}
        for feed, L in (("iex", li), ("sip", ls)):
            for lab in ("trending_up", "trending_down", "high_vol", "low_vol", "chop", "stress"):
                r[f"{feed}_{lab}%"] = 100 * np.mean([L[m] == lab for m in w])
            r[f"{feed}_up_min_before_13"] = sum(L[m] == "trending_up" for m in w if m < "13:00")
            r[f"{feed}_up_min_after_13"] = sum(L[m] == "trending_up" for m in w if m >= "13:00")
        r["agree%"] = 100 * np.mean([li[m] == ls[m] for m in w])
        r["live_vs_iex%"] = 100 * np.mean([li[m] == lv[m] for m in w if m in lv]) if lv else np.nan
        rows.append(r)
    out = pd.DataFrame(rows)
    out.to_csv(a.out, index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(out.round(1).to_string(index=False))
    up_i = out.iex_up_min_before_13 + out.iex_up_min_after_13
    up_s = out.sip_up_min_before_13 + out.sip_up_min_after_13
    print(f"\nsessions {len(out)}; trending_up minutes iex {int(up_i.sum())} (before 13:00 ET "
          f"{int(out.iex_up_min_before_13.sum())}) vs sip {int(up_s.sum())}; sessions with any: "
          f"iex {int((up_i > 0).sum())}, sip {int((up_s > 0).sum())}")


if __name__ == "__main__":
    main()
