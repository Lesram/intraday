"""ORB on stocks in play, per PREREG_orb.md (sha256 8ee93696...).

    export INTRA_ENV=/path/to/.env      # holds the Alpaca keys; read, never printed
    python orb.py symbols && python orb.py calendar && python orb.py daily
    python orb.py elig && python orb.py first5 && python orb.py select && python orb.py intraday && python orb.py sim
    python orb_ticks.py fetch && python orb_ticks.py summary

Fetch steps are resumable and stop after BUDGET seconds (second argument, default unlimited).
Run on 2026-10-21 for 2025-01-02..2026-10-20: results/orb_results.txt.
"""
from __future__ import annotations

import json
import os
import pickle
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "feed_and_gap_up_2026_10_21"))
from alpaca_bars import get_bars, load_keys  # noqa: E402

D = Path(os.environ.get("ORB_DATA", "data/orb"))
ET, UTC = ZoneInfo("America/New_York"), ZoneInfo("UTC")
T0 = time.time()
BUDGET = float(sys.argv[2]) if len(sys.argv) > 2 else 1e9
TEST0, TEST1 = "2025-01-02", "2026-10-20"
LISTS = ("nasdaq/nasdaq_full_tickers.json", "nyse/nyse_full_tickers.json", "amex/amex_full_tickers.json")


def keys():
    return load_keys(os.environ.get("INTRA_ENV", ".env"))


def over():
    return time.time() - T0 > BUDGET


def utc(day, hh, mm):
    y, m, d = map(int, day.split("-"))
    return datetime(y, m, d, hh, mm, tzinfo=ET).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sessions():
    return sorted({b[0] for b in json.loads((D / "spy_daily.json").read_text())})


def cmd_symbols():
    for p in LISTS:
        url = "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/" + p
        (D / p.replace("/", "_")).write_bytes(urllib.request.urlopen(url, timeout=60).read())
    print("listings saved")


def symbols():
    out = set()
    for p in LISTS:
        for r in json.load(open(D / p.replace("/", "_"))):
            s, n = r["symbol"].strip(), r.get("name") or ""
            if not s or re.search(r"[\^/. ]", s):
                continue
            if re.search(r"Warrant|\bUnits?\b|\bRights?\b|Preferred|Depositary Shares,? each representing|Notes due|Subordinated", n, re.I):
                continue
            out.add(s)
    return sorted(out)


def cmd_calendar():
    key, sec = keys()
    b = get_bars({"symbols": "SPY", "timeframe": "1Day", "start": "2024-11-01T00:00:00Z", "end": "2026-10-21T00:00:00Z",
                  "feed": "sip", "limit": "10000", "adjustment": "raw"}, key, sec)["SPY"]
    (D / "spy_daily.json").write_text(json.dumps([[x["t"][:10]] for x in b]))
    print("sessions", len(b))


def cmd_daily():
    key, sec = keys()
    syms = symbols()
    (D / "daily").mkdir(exist_ok=True)
    for i in range(0, len(syms), 300):
        f = D / "daily" / f"{i // 300:03d}.json"
        if f.exists():
            continue
        if over():
            break
        bars = get_bars({"symbols": ",".join(syms[i:i + 300]), "timeframe": "1Day", "start": "2024-11-01T00:00:00Z",
                         "end": "2026-10-21T00:00:00Z", "feed": "sip", "limit": "10000", "adjustment": "raw"}, key, sec)
        f.write_text(json.dumps({s: [[b["t"][:10], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in v] for s, v in bars.items()}))
    print(f"symbols {len(syms)}; batches {len(list((D / 'daily').glob('*.json')))}/{(len(syms) + 299) // 300}")


def cmd_elig():
    rows = []
    for f in sorted((D / "daily").glob("*.json")):
        for s, v in json.loads(f.read_text()).items():
            df = pd.DataFrame(v, columns=["d", "o", "h", "l", "c", "v"])
            pc = df.c.shift(1)
            tr = pd.concat([df.h - df.l, (df.h - pc).abs(), (df.l - pc).abs()], axis=1).max(axis=1)
            df["prevc"], df["adv14"], df["atr14"] = pc, df.v.shift(1).rolling(14).mean(), tr.shift(1).rolling(14).mean()
            e = df[(df.prevc > 5) & (df.adv14 >= 1e6) & (df.atr14 > 0.5)]
            rows += [(d, s, a) for d, a in zip(e.d, e.atr14)]
    el = pd.DataFrame(rows, columns=["d", "sym", "atr14"])
    pickle.dump(el, open(D / "elig.pkl", "wb"))
    per = el.groupby("d").size()
    print(f"eligible symbol-days {len(el)}; per session median {per.median():.0f} (min {per.min()}, max {per.max()})")


def fetch_sets():
    el = pickle.load(open(D / "elig.pkl", "rb"))
    by = el.groupby("d")["sym"].apply(set).to_dict()
    days = [d for d in sessions() if "2024-12-10" <= d <= TEST1]
    out = {}
    for k, d in enumerate(days):        # eligible on d or any of the next 14 sessions (RV baselines need them)
        u = set()
        for d2 in days[k:k + 15]:
            u |= by.get(d2, set())
        out[d] = sorted(u)
    return out


def cmd_first5():
    key, sec = keys()
    (D / "first5").mkdir(exist_ok=True)
    sets = fetch_sets()
    todo = [d for d in sets if not (D / "first5" / f"{d}.json").exists()]

    def one(d):
        if over():
            return 0
        syms, res = sets[d], {}
        for i in range(0, len(syms), 700):
            b = get_bars({"symbols": ",".join(syms[i:i + 700]), "timeframe": "5Min", "start": utc(d, 9, 30),
                          "end": utc(d, 9, 35), "feed": "sip", "limit": "10000", "adjustment": "raw"}, key, sec)
            res.update({s: [v[0]["o"], v[0]["h"], v[0]["l"], v[0]["c"], v[0]["v"]] for s, v in b.items()
                        if v and v[0]["t"] == utc(d, 9, 30)})
        (D / "first5" / f"{d}.json").write_text(json.dumps(res))
        return 1

    with ThreadPoolExecutor(max_workers=3) as ex:
        n = sum(ex.map(one, todo))
    print(f"first5 sessions {len(list((D / 'first5').glob('*.json')))}/{len(sets)} (+{n})")


def cmd_select():
    el = pickle.load(open(D / "elig.pkl", "rb"))
    atr = {(d, s): a for d, s, a in zip(el.d, el.sym, el.atr14)}
    eld = el.groupby("d")["sym"].apply(list).to_dict()
    days = [d for d in sessions() if "2024-12-10" <= d <= TEST1]
    f5 = {d: json.loads((D / "first5" / f"{d}.json").read_text()) for d in days}
    sel = {}
    for k, d in enumerate(days):
        if d < TEST0:
            continue
        prior, cand = days[max(0, k - 14):k], []
        for s in eld.get(d, []):
            if s not in f5[d]:
                continue
            hist = [f5[p][s][4] for p in prior if s in f5[p]]
            if len(hist) < 10 or np.mean(hist) <= 0:
                continue
            o, h, l, c, v = f5[d][s]
            rv = v / np.mean(hist)
            if rv >= 1.0 and c != o:
                cand.append((rv, s, 1 if c > o else -1, o, h, l, c, atr[(d, s)]))
        sel[d] = sorted(cand, reverse=True)[:20]
    pickle.dump(sel, open(D / "selection.pkl", "wb"))
    print(f"test sessions {len(sel)}; picks per session median {np.median([len(v) for v in sel.values()]):.0f}")


def cmd_intraday():
    key, sec = keys()
    sel = pickle.load(open(D / "selection.pkl", "rb"))
    (D / "intra").mkdir(exist_ok=True)
    todo = [d for d, picks in sel.items() if picks and not (D / "intra" / f"{d}.json").exists()]

    def one(d):
        if over():
            return 0
        b = get_bars({"symbols": ",".join(p[1] for p in sel[d]), "timeframe": "1Min", "start": utc(d, 9, 35),
                      "end": utc(d, 16, 0), "feed": "sip", "limit": "10000", "adjustment": "raw", "sort": "asc"}, key, sec)
        (D / "intra" / f"{d}.json").write_text(json.dumps(
            {s: [[x["t"], x["o"], x["h"], x["l"], x["c"]] for x in v] for s, v in b.items()}))
        return 1

    with ThreadPoolExecutor(max_workers=3) as ex:
        n = sum(ex.map(one, todo))
    print(f"intraday sessions {len(list((D / 'intra').glob('*.json')))}/{sum(1 for v in sel.values() if v)} (+{n})")


def walk(sel, stop_from_next_bar=None):
    """Yield (day, direction, gross return, stop distance as a fraction) per triggered trade.
    stop_from_next_bar: None = pre-registered (fill bar counts); a set of 'day|sym' keys whose fill-bar
    stop touch happened before the entry (from orb_ticks.py); True = always start at the next bar."""
    for d, picks in sel.items():
        f = D / "intra" / f"{d}.json"
        if not picks or not f.exists():
            continue
        bars = json.loads(f.read_text())
        for rv, s, dr, o5, h5, l5, c5, a in picks:
            b = bars.get(s)
            if not b:
                continue
            O, H, L, C = (np.array([x[k] for x in b]) for k in (1, 2, 3, 4))
            hit = np.nonzero(H >= h5)[0] if dr > 0 else np.nonzero(L <= l5)[0]
            if not len(hit):
                continue
            i = int(hit[0])
            fill = max(h5, O[i]) if dr > 0 else min(l5, O[i])
            risk = 0.1 * a
            stop = fill - dr * risk
            skip = stop_from_next_bar is True or (isinstance(stop_from_next_bar, set) and f"{d}|{s}" in stop_from_next_bar)
            ex = C[-1]
            for j in range(i + 1 if skip else i, len(b)):
                if (dr > 0 and L[j] <= stop) or (dr < 0 and H[j] >= stop):
                    ex = stop if j == i else (min(stop, O[j]) if dr > 0 else max(stop, O[j]))
                    break
            yield d, dr, dr * (ex / fill - 1), risk / fill


def report(rows, label):
    T = pd.DataFrame(rows, columns=["d", "dir", "gross", "rfrac"])
    sess = [d for d in sessions() if TEST0 <= d <= TEST1]
    out = [f"== {label}: trades {len(T)}"]
    for cost in (3e-4, 1e-4):
        T["net"] = T.gross - 2 * cost
        T["R"] = T.net / T.rfrac
        for name, m in (("ALL", T.d.notna()), ("LONG", T.dir > 0), ("SHORT", T.dir < 0),
                        ("ALL 2025", T.d < "2026"), ("ALL 2026", T.d >= "2026")):
            x = T[m]
            per = x.groupby("d").R.mean()
            t = per.mean() / (per.std(ddof=1) / np.sqrt(len(per)))
            out.append(f"{cost * 1e4:.0f}bp/side {name:8s} n={len(x):5d} meanR={x.R.mean():+.3f} t={t:+.2f} "
                       f"gross={1e4 * x.gross.mean():+.1f}bps net={1e4 * x.net.mean():+.1f}bps win={100 * (x.net > 0).mean():.0f}%")
        for name, m in (("ALL", T.d.notna()), ("LONG", T.dir > 0)):
            x = T[m].copy()
            x["notional"] = 0.01 / x.rfrac
            sc = (4.0 / x.groupby("d").notional.transform("sum")).clip(upper=1.0)
            daily = (x.notional * sc * x.net).groupby(x.d).sum().reindex(sess, fill_value=0.0)
            eq = (1 + daily).cumprod()
            out.append(f"   portfolio {name} at {cost * 1e4:.0f}bp/side: total {100 * (eq.iloc[-1] - 1):+.1f}%  "
                       f"Sharpe {daily.mean() / daily.std() * np.sqrt(252):+.2f}  maxDD {100 * (eq / eq.cummax() - 1).min():.1f}%")
    return "\n".join(out)


def cmd_sim():
    sel = pickle.load(open(D / "selection.pkl", "rb"))
    print(report(list(walk(sel)), "pre-registered (a stop touch in the fill minute counts)"))
    print(report(list(walk(sel, True)), "optimistic bound (stop checked from the minute after the fill)"))


if __name__ == "__main__":
    D.mkdir(parents=True, exist_ok=True)
    {"symbols": cmd_symbols, "calendar": cmd_calendar, "daily": cmd_daily, "elig": cmd_elig, "first5": cmd_first5,
     "select": cmd_select, "intraday": cmd_intraday, "sim": cmd_sim}[sys.argv[1]]()
