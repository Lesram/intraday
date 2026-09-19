#!/usr/bin/env python3
"""Phase 3 Task 3 (5c) COMMIT A — ROUTING-V2 ENGINE PARITY GATE.

Runs the REAL engine (via ReplayEngine) twice over the step-5 momentum-
exercising window — once with ORGANISM_FRAMEWORK_ROUTING_V2 semantics OFF,
once ON — and proves Commit A is STRUCTURALLY INERT: the selector pass
replaces the scattered per-strategy scanner calls without changing a single
decision. Asserted axes (same as the step-5 gate — sizes and reasons, not
just timing):

  * entered-symbol SET and SEQUENCE      * share counts per entry
  * exit reasons and exit sizes          * closed-trade ledger + equity curve
  * regime history                       * seam tripwire silent both runs

Also runs a CHOP window (MR/ORB-shaped conditions) so the v2 shadow-list
population paths execute, not just momentum.

Exit 0 iff parity holds on every window AND the primary window traded.
"""
from __future__ import annotations

import asyncio
import sys

import backend.organism.live_engine as le
from backend.organism.live_engine import OrganismLiveEngine
from backend.organism.replay_simulator import ReplayEngine, make_features_dict

WINDOWS = [
    dict(name="trend_up", symbols=["AAPL", "MSFT", "NVDA", "GOOGL", "SPY"],
         n=600, seed=42, trend="up", max_ticks=250, lookback=200,
         must_trade=True),
    dict(name="chop", symbols=["AAPL", "MSFT", "NVDA", "GOOGL", "SPY"],
         n=600, seed=7, trend="chop", max_ticks=250, lookback=200,
         must_trade=False),
]


async def _run_once(window: dict, v2_on: bool):
    entries: list[tuple] = []
    exits: list[tuple] = []
    mismatches: list[str] = []

    orig_entry = OrganismLiveEngine._submit_entry_order
    orig_exit = OrganismLiveEngine._submit_exit_order

    async def spy_entry(self, symbol, shares, *args, **kwargs):
        entries.append((symbol, int(shares), float(kwargs.get("direction", 1.0)),
                        kwargs.get("reason", "organism_entry")))
        return await orig_entry(self, symbol, shares, *args, **kwargs)

    async def spy_exit(self, symbol, shares, reason="organism_exit", *args, **kwargs):
        exits.append((symbol, int(shares), reason))
        return await orig_exit(self, symbol, shares, reason, *args, **kwargs)

    import logging

    class _Trip(logging.Handler):
        def emit(self, record):
            msg = record.getMessage()
            if "FRAMEWORK SEAM MISMATCH" in msg or "scan_all failed" in msg:
                mismatches.append(msg)

    trip = _Trip(level=logging.WARNING)
    logging.getLogger("backend.organism.live_engine").addHandler(trip)

    OrganismLiveEngine._submit_entry_order = spy_entry
    OrganismLiveEngine._submit_exit_order = spy_exit
    prev = le.FRAMEWORK_ROUTING_V2_ENABLED
    le.FRAMEWORK_ROUTING_V2_ENABLED = v2_on
    try:
        bars = make_features_dict(window["symbols"], n=window["n"],
                                  seed=window["seed"], trend=window["trend"])
        eng = ReplayEngine(bars_by_symbol=bars, initial_cash=100_000,
                           lookback=window["lookback"])
        res = await eng.run(max_ticks=window["max_ticks"])
    finally:
        le.FRAMEWORK_ROUTING_V2_ENABLED = prev
        OrganismLiveEngine._submit_entry_order = orig_entry
        OrganismLiveEngine._submit_exit_order = orig_exit
        logging.getLogger("backend.organism.live_engine").removeHandler(trip)

    trades = [(t["symbol"], t["qty"], round(t["entry_price"], 6),
               round(t["exit_price"], 6), round(t["pnl"], 6)) for t in res.trades]
    eq = [round(x, 6) for x in res.equity_curve]
    return entries, exits, trades, eq, list(res.regime_history), mismatches


async def main() -> int:
    print("=" * 64)
    print("5c COMMIT-A ROUTING-V2 ENGINE PARITY  (flag OFF vs ON)")
    print("=" * 64)
    ok = True
    for w in WINDOWS:
        off = await _run_once(w, v2_on=False)
        on = await _run_once(w, v2_on=True)
        labels = ["entries", "exits", "trade ledger", "equity curve",
                  "regime history"]
        print(f"\nwindow={w['name']}  OFF: entries={len(off[0])} "
              f"trades={len(off[2])}   ON: entries={len(on[0])} trades={len(on[2])}")
        for i, lab in enumerate(labels):
            if off[i] == on[i]:
                print(f"  [PASS] {lab}")
            else:
                ok = False
                print(f"  [FAIL] {lab}\n    OFF: {off[i][:6]}\n     ON: {on[i][:6]}")
        for run_name, run in (("OFF", off), ("ON", on)):
            if run[5]:
                ok = False
                print(f"  [FAIL] tripwire fired ({run_name}): {run[5][:2]}")
            else:
                print(f"  [PASS] tripwire silent {run_name}")
        if w["must_trade"] and not off[2]:
            ok = False
            print("  [FAIL] primary window produced no trades — proof vacuous")
    print("\n" + "=" * 64)
    print("RESULT: PARITY HOLDS ✓" if ok else "RESULT: PARITY BROKEN ✗")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
