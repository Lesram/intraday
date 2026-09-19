#!/usr/bin/env python3
"""Intra 2.0 Phase 1 — STEP 5 ENGINE-LEVEL PARITY GATE (acceptance #5).

Runs the REAL engine (OrganismLiveEngine via ReplayEngine: real alpha_scanner,
real Kelly sizing, real exit logic) twice over one fixed, momentum-exercising
window — once with the thin-seam framework flag OFF, once ON — and proves the
two runs are behaviorally identical on the axes that actually matter:

  * entered-symbol SET and SEQUENCE  (top_n ranking order)
  * share counts per entry           (Kelly sizing)
  * exit reasons and exit sizes
  * closed-trade ledger (entry/exit price, pnl) and the full equity curve

A timing-only check would pass while every trade was sized wrong, so this asserts
SIZES and REASONS, not just whether something fired. The window is chosen to
actually trade in trending_up (where momentum is the eligible strategy and the
seam ACTIVELY re-sources direction) — a no-trade/chop window would make the
proof vacuous.

NOTE ON COSTS: this is a flag-on-vs-flag-off PARITY comparison, so the replay's
optimistic-fill default is irrelevant here (both runs use it identically). The
cost-disciplined OOS methodology is the backtester's concern (step 8), not this
gate.

Exit: 0 if parity holds AND the window traded; 1 otherwise.
"""
from __future__ import annotations

import asyncio
import sys

import backend.organism.live_engine as le
from backend.organism.live_engine import OrganismLiveEngine
from backend.organism.replay_simulator import ReplayEngine, make_features_dict

WINDOW = dict(
    symbols=["AAPL", "MSFT", "NVDA", "GOOGL", "SPY"],
    n=600, seed=42, trend="up", max_ticks=250, lookback=200,
)


async def _run_once(framework_on: bool):
    """Run the window once; capture entry/exit submissions at the source."""
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

    # Tripwire: capture the seam's "should be impossible" mismatch log.
    import logging

    class _Trip(logging.Handler):
        def emit(self, record):
            if "FRAMEWORK SEAM MISMATCH" in record.getMessage():
                mismatches.append(record.getMessage())

    trip = _Trip(level=logging.ERROR)
    logging.getLogger("backend.organism.live_engine").addHandler(trip)

    OrganismLiveEngine._submit_entry_order = spy_entry
    OrganismLiveEngine._submit_exit_order = spy_exit
    prev_flag = le.FRAMEWORK_ROUTING_ENABLED
    le.FRAMEWORK_ROUTING_ENABLED = framework_on
    try:
        bars = make_features_dict(WINDOW["symbols"], n=WINDOW["n"],
                                  seed=WINDOW["seed"], trend=WINDOW["trend"])
        eng = ReplayEngine(bars_by_symbol=bars, initial_cash=100_000,
                           lookback=WINDOW["lookback"])
        res = await eng.run(max_ticks=WINDOW["max_ticks"])
    finally:
        le.FRAMEWORK_ROUTING_ENABLED = prev_flag
        OrganismLiveEngine._submit_entry_order = orig_entry
        OrganismLiveEngine._submit_exit_order = orig_exit
        logging.getLogger("backend.organism.live_engine").removeHandler(trip)

    trades = [(t["symbol"], t["qty"], round(t["entry_price"], 6),
               round(t["exit_price"], 6), round(t["pnl"], 6)) for t in res.trades]
    eq = [round(x, 6) for x in res.equity_curve]
    return entries, exits, trades, eq, list(res.regime_history), mismatches


async def main() -> int:
    off_e, off_x, off_t, off_eq, off_reg, off_mis = await _run_once(False)
    on_e, on_x, on_t, on_eq, on_reg, on_mis = await _run_once(True)

    print("=" * 64)
    print("STEP-5 THIN-SEAM ENGINE PARITY  (flag OFF vs ON)")
    print("=" * 64)
    print(f"window: {WINDOW}")
    print(f"regimes traversed: {sorted(set(off_reg))}")
    print(f"OFF: entries={len(off_e)} exits={len(off_x)} trades={len(off_t)}")
    print(f" ON: entries={len(on_e)} exits={len(on_x)} trades={len(on_t)}")
    print(f"entry seq OFF: {off_e}")
    print(f"entry seq  ON: {on_e}")
    print(f"exit  seq OFF: {off_x}")
    print(f"exit  seq  ON: {on_x}")

    ok = True
    # The window must actually trade, and include a trending_up entry (where the
    # seam fires) — otherwise the parity proof is vacuous.
    if not off_e:
        print("FAIL: window produced NO entries — proof would be vacuous.")
        ok = False
    if "trending_up" not in set(off_reg):
        print("FAIL: window never entered trending_up — seam never exercised.")
        ok = False

    checks = [
        ("entered-set + sequence + sizes + entry-reason", off_e == on_e),
        ("exit reasons + exit sizes", off_x == on_x),
        ("closed-trade ledger (qty/entry/exit/pnl)", off_t == on_t),
        ("equity curve", off_eq == on_eq),
        ("regime history", off_reg == on_reg),
        ("seam tripwire silent OFF", not off_mis),
        ("seam tripwire silent ON", not on_mis),
    ]
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        ok = ok and passed

    print("=" * 64)
    print("RESULT:", "PARITY HOLDS ✓" if ok else "PARITY BROKEN ✗")
    print("=" * 64)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
