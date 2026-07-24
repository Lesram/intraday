#!/usr/bin/env python3
"""Stand-down diagnosis: compute one per-session table row (punchlist 2026-07-24 item 4).

Produces the Sessions 2-3 row for reports/ENTRY_STANDDOWN_DIAGNOSIS.md from the
same predicates the red-team adjudicated for Session 1:

  - regime mix + live candidates: organism_brain/strategy_evidence_events.jsonl
    (live candidates = rows with live_pipeline_candidate=True — the authoritative
    predicate; raw entry_source tags over-count)
  - direction_zero = defensive_filter_reason == "direction_zero" (NOT direction==0)
  - scanner empty / stale-bar rejects / liquidity blocks / orders: logs/application.log
  - fills: organism_brain/trade_history.csv rows with closed_at on the session date

DISCIPLINE RULE (Cowork, red-team round 2): session tables are measured at session
close only — mid-session "0"s on kill counters are unreliable. This script refuses
to run for today's date before 20:05Z unless --force is given.

Usage:
    python scripts/ops/standdown_session_row.py              # today (after close)
    python scripts/ops/standdown_session_row.py 2026-07-24   # explicit date
    python scripts/ops/standdown_session_row.py --force      # override close guard
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE = Path("organism_brain/strategy_evidence_events.jsonl")
TRADES = Path("organism_brain/trade_history.csv")
LOG = Path("logs/application.log")
SESSION_CLOSE_UTC = (20, 5)  # 20:05Z ≈ 16:05 ET — after the 20:00Z close


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    now = datetime.now(timezone.utc)
    date = args[0] if args else now.strftime("%Y-%m-%d")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        print(f"bad date: {date!r} (want YYYY-MM-DD)")
        return 2

    if date == now.strftime("%Y-%m-%d") and not force:
        if (now.hour, now.minute) < SESSION_CLOSE_UTC:
            print(f"REFUSING: it is {now:%H:%M}Z — before session close "
                  f"({SESSION_CLOSE_UTC[0]:02d}:{SESSION_CLOSE_UTC[1]:02d}Z). "
                  "Mid-session kill counts are unreliable (red-team round 2 rule). "
                  "Re-run after close, or pass --force to override deliberately.")
            return 3

    # ── evidence events ──
    regimes: Counter = Counter()
    dz_filter = 0
    dz_direction0 = 0
    live_candidates = 0
    total = 0
    if EVIDENCE.is_file():
        for line in EVIDENCE.open():
            if date not in line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not str(r.get("timestamp", "")).startswith(date):
                continue
            total += 1
            regimes[r.get("regime") or "?"] += 1
            if r.get("defensive_filter_reason") == "direction_zero":
                dz_filter += 1
            d = r.get("direction")
            if d is not None and float(d) == 0.0:
                dz_direction0 += 1
            if r.get("live_pipeline_candidate"):
                live_candidates += 1

    # ── log counters ──
    scanner_empty = 0
    stale = 0
    stale_syms: Counter = Counter()
    liquidity = 0
    orders = 0
    if LOG.is_file():
        stale_re = re.compile(r"Streaming bars REJECTED for ([A-Z]+)")
        for line in LOG.open(errors="replace"):
            if date not in line:
                continue
            if "no stocks passed initial filters" in line:
                scanner_empty += 1
            elif "Streaming bars REJECTED" in line:
                stale += 1
                m = stale_re.search(line)
                if m:
                    stale_syms[m.group(1)] += 1
            elif "Liquidity gate blocked" in line:
                liquidity += 1
            elif re.search(r"submit_entry|order submitted|placing order", line, re.I):
                orders += 1

    # ── fills ──
    fills = 0
    if TRADES.is_file():
        with TRADES.open() as f:
            for row in csv.DictReader(f):
                if str(row.get("closed_at", "")).startswith(date):
                    fills += 1

    # ── output ──
    mix = " / ".join(f"{k} {v}" for k, v in regimes.most_common())
    print(f"SESSION {date} (measured {now:%Y-%m-%dT%H:%M}Z)")
    print(f"  evidence events: {total}   regime mix: {mix or '(none)'}")
    print(f"  scanner empty: {scanner_empty}   stale-bar rejects: {stale} "
          f"(top: {', '.join(f'{s} {n}' for s, n in stale_syms.most_common(5)) or '-'})")
    print(f"  live candidates (live_pipeline_candidate=True): {live_candidates}")
    print(f"  direction_zero filter: {dz_filter}   (rows with direction==0: "
          f"{dz_direction0})   liquidity blocks: {liquidity}")
    print(f"  order submissions: {orders}   fills (trade_history closed_at): {fills}")
    print()
    print("markdown row (paste into reports/ENTRY_STANDDOWN_DIAGNOSIS.md §1):")
    print(f"| **{date}** | {mix or '—'} (n={total}) | {scanner_empty} | {stale} "
          f"| {live_candidates} | {orders} | {fills} |")
    if total == 0 and stale == 0 and scanner_empty == 0:
        print("\nWARNING: all-zero row — was the engine even up on this date? "
              "Check `make paper-status` / container uptime before recording it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
