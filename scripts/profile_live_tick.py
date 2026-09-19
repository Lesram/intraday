"""Profile live_tick() performance.

Runs a short replay under cProfile to identify slow stages. Output:
- Top-30 functions by cumulative time
- Top-30 functions by self time (own work, not callees)
- Tick-level summary
"""

from __future__ import annotations

import asyncio
import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def run_short_replay(max_ticks: int = 100):
    from backend.organism.replay_simulator import (
        ReplayEngine, make_features_dict,
    )
    bars = make_features_dict(
        ["NVDA", "SPY", "QQQ", "AAPL", "MSFT", "AMZN"],
        n=500, base=100.0, trend="up",
    )
    engine = ReplayEngine(
        bars_by_symbol=bars,
        initial_cash=100_000,
        slippage_bps=5,
        timeframe="1Min",
        max_entries_per_hour=20,
    )
    t0 = time.perf_counter()
    result = await engine.run(max_ticks=max_ticks)
    elapsed = time.perf_counter() - t0
    return result, elapsed


def main() -> None:
    profiler = cProfile.Profile()
    profiler.enable()
    result, elapsed = asyncio.run(run_short_replay(max_ticks=100))
    profiler.disable()

    print(f"\n=== Replay summary ===")
    print(f"Ticks:   {result.ticks}")
    print(f"Trades:  {len(result.trades)}")
    print(f"Elapsed: {elapsed:.2f}s")
    if result.ticks > 0:
        print(f"Per-tick: {elapsed / result.ticks * 1000:.1f}ms")

    output = io.StringIO()
    stats = pstats.Stats(profiler, stream=output).sort_stats("cumulative")
    stats.print_stats(30)
    print("\n=== Top 30 by cumulative time ===")
    print(output.getvalue())

    output2 = io.StringIO()
    stats2 = pstats.Stats(profiler, stream=output2).sort_stats("tottime")
    stats2.print_stats(30)
    print("\n=== Top 30 by self time (tottime) ===")
    print(output2.getvalue())

    out = Path(__file__).parent.parent / "artifacts" / "live_tick_profile.txt"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w") as f:
        f.write(f"Replay: {result.ticks} ticks in {elapsed:.2f}s "
                f"(per-tick: {elapsed/result.ticks*1000:.1f}ms)\n\n")
        f.write("=== Top 50 by cumulative time ===\n")
        s3 = pstats.Stats(profiler, stream=f).sort_stats("cumulative")
        s3.print_stats(50)
        f.write("\n\n=== Top 50 by self time ===\n")
        s4 = pstats.Stats(profiler, stream=f).sort_stats("tottime")
        s4.print_stats(50)
    print(f"\nFull profile written to {out}")


if __name__ == "__main__":
    main()
