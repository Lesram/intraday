"""Counterfactual P&L of the logged shadow-strategy signals on full-market bars.

    python shadow_replay.py --evidence ~/VS/intra/organism_brain/strategy_evidence_events.jsonl \
                            --bars data/bars_sip.json --since 2026-09-15

Reads the engine's strategy-evidence log (read-only) and replays every logged
shadow signal of fw_mean_reversion_shadow, fw_orb_shadow, orb_legacy_shadow,
fw_momentum_shadow and fw_breakout_shadow on SIP 1-minute bars:
one position at a time per (strategy, symbol); mean reversion waits 60 minutes
after an exit (its cooldown); ORB takes the first signal per symbol, side and
day. Entry = open of the next minute bar after the signal (09:30-15:58 ET; mean
reversion no entries after 15:30). Exits: logged stop on touch (stop first if a
bar touches both), the mean-reversion target on touch, the 60-bar horizon the
signals carry, or 15:58 ET. Costs 3 bps per side.

This is an approximation of how these strategies would trade (no slippage
model, intrabar touches, IEX-built signals filled at SIP prices). Run on
2026-10-21 for 2026-09-16..2026-10-20: results/shadow_replay.txt.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

SIDE = 3e-4
SIDS = {"fw_mean_reversion_shadow", "fw_orb_shadow", "orb_legacy_shadow", "fw_momentum_shadow", "fw_breakout_shadow"}
ORB = {"fw_orb_shadow", "orb_legacy_shadow"}
MR = "fw_mean_reversion_shadow"
MIN_NS = 60_000_000_000


def load_signals(path: Path, since: str):
    rows = []
    with open(path) as f:
        for line in f:
            if '"shadow_only": true' not in line:
                continue
            e = json.loads(line)
            if e.get("strategy_id") not in SIDS or e.get("timestamp", "") < since:
                continue
            rows.append((e["strategy_id"], e["symbol"], e["timestamp"], e.get("side"),
                         e.get("stop_price"), e.get("target_price"), e.get("regime")))
    return rows


def load_bars(path: Path):
    B = {}
    for s, b in json.loads(path.read_text()).items():
        df = pd.DataFrame(b)
        t = pd.to_datetime(df["t"], utc=True)
        et = t.dt.tz_convert("America/New_York")
        B[s] = dict(ns=t.dt.as_unit("ns").astype("int64").to_numpy(),   # pandas 3 may parse to "us"
                    mod=(et.dt.hour * 60 + et.dt.minute).to_numpy(),
                    day=et.dt.strftime("%Y-%m-%d").to_numpy(), o=df.o.to_numpy(), h=df.h.to_numpy(),
                    l=df.l.to_numpy(), c=df.c.to_numpy())
    return B


def simulate(sig, B) -> pd.DataFrame:
    by = defaultdict(list)
    for sid, sym, ts, side, stop, tgt, regime in sig:
        by[(sid, sym)].append((pd.Timestamp(ts).value, side, stop, tgt, regime, ts[:10]))
    trades = []
    for (sid, sym), lst in by.items():
        if sym not in B:
            continue
        b = B[sym]
        lst.sort()
        busy_until = -1
        seen_orb = set()
        for ns, side, stop, tgt, regime, d in lst:
            if ns < busy_until or (sid in ORB and (d, side) in seen_orb):
                continue
            i = int(np.searchsorted(b["ns"], ns - ns % MIN_NS + MIN_NS, side="left"))
            if i >= len(b["ns"]) or b["day"][i] != d or b["mod"][i] < 570 or b["mod"][i] >= 958:
                continue
            if sid == MR and b["mod"][i] > 930:
                continue
            sgn = 1.0 if side == "long" else -1.0
            entry = b["o"][i]
            exit_px, reason, j = None, "horizon", i
            for j in range(i, min(i + 60, len(b["ns"]))):
                if b["day"][j] != d or b["mod"][j] >= 958:
                    exit_px = b["c"][j - 1] if j > i else b["o"][j]
                    reason, j = "eod", j - 1
                    break
                if stop is not None and ((sgn > 0 and b["l"][j] <= stop) or (sgn < 0 and b["h"][j] >= stop)):
                    exit_px = min(stop, b["o"][j]) if sgn > 0 else max(stop, b["o"][j])
                    reason = "stop"
                    break
                if tgt is not None and sgn > 0 and b["h"][j] >= tgt:
                    exit_px = max(tgt, b["o"][j])
                    reason = "target"
                    break
            if exit_px is None:
                exit_px = b["c"][j]
            trades.append(dict(sid=sid, sym=sym, d=d, side=side, regime=regime,
                               gross=sgn * (exit_px / entry - 1), reason=reason, bars=j - i + 1))
            if sid in ORB:
                seen_orb.add((d, side))
            busy_until = int(b["ns"][min(j, len(b["ns"]) - 1)]) + (60 * MIN_NS if sid == MR else 0)
    return pd.DataFrame(trades)


def summ(df: pd.DataFrame) -> pd.Series:
    net = df.gross - 2 * SIDE
    per = net.groupby(df.d).mean()
    tt = per.mean() / (per.std(ddof=1) / np.sqrt(len(per))) if len(per) > 2 else np.nan
    return pd.Series({"trades": len(df), "sessions": df.d.nunique(), "gross_bps": 1e4 * df.gross.mean(),
                      "net_bps": 1e4 * net.mean(), "t_sess": tt, "hit%": 100 * (net > 0).mean(),
                      "avg_bars": df.bars.mean(), "stop%": 100 * (df.reason == "stop").mean(),
                      "target%": 100 * (df.reason == "target").mean()})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--bars", default="data/bars_sip.json")
    ap.add_argument("--since", default="2026-09-15")
    a = ap.parse_args()
    T = simulate(load_signals(Path(a.evidence).expanduser(), a.since), load_bars(Path(a.bars)))
    pd.set_option("display.width", 200)
    print(T.groupby(["sid", "side"]).apply(summ).round(2).to_string())
    print("\nmean reversion by regime:")
    print(T[T.sid == MR].groupby("regime").apply(summ).round(2).to_string())


if __name__ == "__main__":
    main()
