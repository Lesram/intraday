"""V13 W93 diagnostic: trace why test_replay_no_throttle_blocking sees 0 orders.

Runs the same setup as the xfailed test, logs every per-tick result to
stdout, then prints a summary of which gate(s) rejected entries.

Usage:
    ./venv/bin/python scripts/debug/replay_throttle_diagnose.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

# Capture warnings + info from live_engine.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)


async def main() -> int:
    from backend.organism.replay_simulator import ReplayEngine, make_features_dict

    bars = make_features_dict(
        ["AAPL", "MSFT", "SPY"], n=700, seed=42, trend="up",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=100_000,
        slippage_bps=5,
        max_entries_per_hour=20,
    )
    result = await engine.run(max_ticks=100)

    # Per-tick rollup.
    sigs = Counter()
    orders = Counter()
    closed = Counter()
    sample_keys = set()
    for r in result.tick_results:
        if not isinstance(r, dict):
            continue
        sigs[r.get("signals_generated", 0)] += 1
        orders[r.get("orders_submitted", 0)] += 1
        closed[r.get("trades_closed", 0)] += 1
        sample_keys.update(r.keys())

    total_orders = sum(r.get("orders_submitted", 0) for r in result.tick_results if isinstance(r, dict))
    total_signals = sum(r.get("signals_generated", 0) for r in result.tick_results if isinstance(r, dict))
    print()
    print("=" * 60)
    print(f"Replay diagnostic — {result.ticks} ticks")
    print("=" * 60)
    print(f"  total_signals_generated = {total_signals}")
    print(f"  total_orders_submitted  = {total_orders}")
    print(f"  signals histogram       = {sorted(sigs.items())}")
    print(f"  orders histogram        = {sorted(orders.items())}")
    print(f"  closed histogram        = {sorted(closed.items())}")
    print(f"  available result fields = {sorted(sample_keys)}")
    print(f"  regime sample           = {list(result.regime_history[:5])}")
    print(f"  trades broker-side      = {len(result.trades)}")
    if result.tick_results:
        print()
        print("  first tick result:")
        print(f"    {result.tick_results[0]}")
        if len(result.tick_results) > 50:
            print()
            print("  tick 50 result:")
            print(f"    {result.tick_results[50]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
