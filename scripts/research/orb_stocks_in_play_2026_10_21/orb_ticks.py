"""Resolve the fill minute from SIP trades (descriptive check on the pre-registered rule).

In 56% of trades the 1-minute fill bar also touches the stop, and a bar cannot say whether that
happened before or after the entry. This fetches the trades of each such minute and records whether
a trade at or beyond the stop came after the first trade at or beyond the entry level.

    python orb_ticks.py fetch [budget_s]      # resumable, ~4,000 requests
    python orb_ticks.py summary
"""
from __future__ import annotations

import http.client
import json
import pickle
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import numpy as np

import orb
from alpaca_bars import _ctx

OUT = orb.D / "ticks.jsonl"


def trades_of(sym, start, end, key, sec):
    out, token = [], None
    for _ in range(6):
        p = {"symbols": sym, "start": start, "end": end, "feed": "sip", "limit": "10000"}
        if token:
            p["page_token"] = token
        req = urllib.request.Request("https://data.alpaca.markets/v2/stocks/trades?" + urllib.parse.urlencode(p),
                                     headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r:
                    j = json.load(r)
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException, json.JSONDecodeError):
                if attempt == 3:
                    return None
                time.sleep(4 * (attempt + 1))
        out += [(x["t"], x["p"]) for x in (j.get("trades") or {}).get(sym, [])]
        token = j.get("next_page_token")
        if not token:
            return out
    return None                                # more than 60k trades in the minute: unresolved


def cases():
    sel = pickle.load(open(orb.D / "selection.pkl", "rb"))
    for d, picks in sel.items():
        bars = json.loads((orb.D / "intra" / f"{d}.json").read_text())
        for rv, s, dr, o5, h5, l5, c5, a in picks:
            b = bars.get(s)
            if not b:
                continue
            H = np.array([x[2] for x in b])
            L = np.array([x[3] for x in b])
            O = np.array([x[1] for x in b])
            hit = np.nonzero(H >= h5)[0] if dr > 0 else np.nonzero(L <= l5)[0]
            if not len(hit):
                continue
            i = int(hit[0])
            fill = max(h5, O[i]) if dr > 0 else min(l5, O[i])
            stop = fill - dr * 0.1 * a
            if (dr > 0 and L[i] <= stop) or (dr < 0 and H[i] >= stop):
                yield f"{d}|{s}", s, b[i][0], dr, (h5 if dr > 0 else l5), stop


def cmd_fetch():
    key, sec = orb.keys()
    done = {json.loads(line)["k"] for line in OUT.read_text().splitlines()} if OUT.exists() else set()
    todo = [c for c in cases() if c[0] not in done]

    def one(c):
        if orb.over():
            return None
        k, s, t, dr, level, stop = c
        end = (datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        tr = trades_of(s, t, end, key, sec)
        if tr is None:
            return {"k": k, "res": "unresolved"}
        px = [p for _, p in sorted(tr)]
        e = next((n for n, p in enumerate(px) if (p >= level if dr > 0 else p <= level)), None)
        if e is None:
            return {"k": k, "res": "no_entry_tick", "n": len(px)}
        hit = any((p <= stop) if dr > 0 else (p >= stop) for p in px[e + 1:])
        return {"k": k, "res": "stopped_after_entry" if hit else "stop_before_entry", "n": len(px)}

    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = [r for r in ex.map(one, todo) if r]
    with open(OUT, "a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"resolved {len(done) + len(rows)} (+{len(rows)}); {len(todo) - len(rows)} left")


def cmd_summary():
    res = {json.loads(line)["k"]: json.loads(line)["res"] for line in OUT.read_text().splitlines()}
    print("fill-minute outcomes:", dict(Counter(res.values())))
    before = {k for k, v in res.items() if v == "stop_before_entry"}
    sel = pickle.load(open(orb.D / "selection.pkl", "rb"))
    print(orb.report(list(orb.walk(sel, before)), "fill minute resolved from trades"))


if __name__ == "__main__":
    {"fetch": cmd_fetch, "summary": cmd_summary}[sys.argv[1]]()
