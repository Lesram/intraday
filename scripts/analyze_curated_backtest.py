"""Analyze the curated backtest results.

Reads metrics_curated.json + the run's log file and produces a
clean comparative summary vs baseline:
- Trade-count + P&L delta vs baseline
- Regime distribution
- Shadow disagreement counts (regime, composite gate)
- ORB shadow breakout count + symbol distribution
- Exit reason mix
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

CACHE_DIR = Path("/Users/marselkei/VS/intra/artifacts/backtest_rc_1_5")
LOG_FILE = Path("/tmp/curated_backtest.log")


def load_metrics(label: str) -> dict | None:
    p = CACHE_DIR / f"metrics_{label}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def parse_shadow_events(log_path: Path) -> dict:
    """Count shadow telemetry events in the run log."""
    if not log_path.exists():
        return {"regime_disagreements": 0, "composite_disagreements": 0,
                "orb_breakouts": 0, "orb_symbols": Counter(),
                "regime_disagreement_pairs": Counter()}

    log = log_path.read_text()

    regime_pat = re.compile(r"RC-1\.5 shadow: regime disagreement live=(\w+) shadow=(\w+)")
    comp_pat = re.compile(r"RC-1\.5 shadow: composite gate disagreement (\w+)")
    orb_pat = re.compile(r"ORB shadow BREAKOUT: (\w+) dir=([+-]?[\d.]+) rv=([\d.]+)")

    regime_disagreements = regime_pat.findall(log)
    comp_disagreements = comp_pat.findall(log)
    orb_breakouts = orb_pat.findall(log)

    return {
        "regime_disagreements": len(regime_disagreements),
        "composite_disagreements": len(comp_disagreements),
        "orb_breakouts": len(orb_breakouts),
        "orb_symbols": Counter(b[0] for b in orb_breakouts),
        "regime_disagreement_pairs": Counter(
            f"live={live} → shadow={shadow}"
            for live, shadow in regime_disagreements
        ),
        "composite_disagreement_symbols": Counter(comp_disagreements),
    }


def fmt_pct(num: float, denom: float) -> str:
    if denom == 0:
        return "n/a"
    return f"{100 * num / denom:.1f}%"


def main() -> int:
    curated = load_metrics("curated")
    baseline = load_metrics("baseline")
    treatment = load_metrics("treatment")

    print("=" * 72)
    print("  RC-1.5 CURATED BACKTEST RESULTS")
    print("=" * 72)

    if curated is None:
        print("  (curated metrics not yet written — backtest in flight)")
        return 1

    print(f"\n  Curated run summary:")
    print(f"    Ticks:           {curated['ticks']}")
    print(f"    Trades:          {curated['trades']}")
    print(f"    PnL:             ${curated['total_pnl']:.2f}")
    print(f"    Win rate:        {100*curated['win_rate']:.1f}%")
    print(f"    Sharpe:          {curated['sharpe']:.3f}")
    print(f"    Max drawdown:    {100*curated['max_drawdown']:.3f}%")
    print(f"    Final equity:    ${curated.get('final_equity', 0):,.2f}")
    print(f"    Return:          {curated.get('return_pct', 0):.4f}%")
    print(f"    Elapsed:         {curated.get('elapsed_s', 0):.1f}s")

    if baseline is not None:
        print(f"\n  Baseline (main / eb90fa3) for comparison:")
        print(f"    Trades:    {baseline['trades']}    Δ={curated['trades']-baseline['trades']:+d}")
        print(f"    PnL:       ${baseline['total_pnl']:.2f}    Δ=${curated['total_pnl']-baseline['total_pnl']:+.2f}")
        print(f"    Win rate:  {100*baseline['win_rate']:.1f}%   Δ={100*(curated['win_rate']-baseline['win_rate']):+.1f}pp")
        print(f"    Sharpe:    {baseline['sharpe']:.3f}    Δ={curated['sharpe']-baseline['sharpe']:+.3f}")

    if treatment is not None:
        print(f"\n  Three-fix treatment (rc-1.5-three-fixes — for reference):")
        print(f"    Trades:    {treatment['trades']}    PnL: ${treatment['total_pnl']:.2f}")

    print(f"\n  Regime distribution:")
    for r, c in sorted(curated.get('regime_distribution', {}).items(),
                        key=lambda kv: -kv[1]):
        print(f"    {r:<15} {c:>6} ({fmt_pct(c, curated['ticks'])})")

    # Shadow telemetry events from the log
    shadow = parse_shadow_events(LOG_FILE)

    print(f"\n  Shadow telemetry events (logged, not gated):")
    print(f"    Regime disagreements:    {shadow['regime_disagreements']}")
    if shadow['regime_disagreement_pairs']:
        for pair, count in shadow['regime_disagreement_pairs'].most_common(5):
            print(f"      {pair}: {count}")
    print(f"    Composite-gate disagreements: {shadow['composite_disagreements']}")
    if shadow['composite_disagreement_symbols']:
        top = shadow['composite_disagreement_symbols'].most_common(5)
        print(f"      Top symbols where new ML weights would have differed:")
        for sym, count in top:
            print(f"        {sym}: {count}")
    print(f"    ORB shadow breakouts:    {shadow['orb_breakouts']}")
    if shadow['orb_symbols']:
        print(f"      Symbols with ORB breakouts:")
        for sym, count in shadow['orb_symbols'].most_common(8):
            print(f"        {sym}: {count}")

    print("\n" + "=" * 72)
    print("  INTERPRETATION")
    print("=" * 72)

    # Comparison vs baseline
    if baseline is not None:
        delta_trades = curated['trades'] - baseline['trades']
        delta_pnl = curated['total_pnl'] - baseline['total_pnl']
        if delta_trades < -2:
            print(f"  ✓ Composite-gate fix reduced trade count by {-delta_trades} "
                  f"vs baseline — gate IS filtering low-quality entries.")
        elif delta_trades > 2:
            print(f"  ⚠ Curated produced MORE trades than baseline ({delta_trades:+d}). "
                  f"Investigate.")
        else:
            print(f"  – Trade count similar to baseline (Δ={delta_trades:+d}).")

        if abs(delta_pnl) > 5.0:
            sign = "improved" if delta_pnl > 0 else "worsened"
            print(f"  • PnL {sign} by ${abs(delta_pnl):.2f} vs baseline.")
        else:
            print(f"  – PnL essentially flat vs baseline (Δ=${delta_pnl:+.2f}).")

    # Shadow-mode signals
    if shadow['regime_disagreements'] > 50:
        print(f"  • Shadow regime classifier WOULD HAVE classified differently "
              f"{shadow['regime_disagreements']} times (RC-2 candidate).")
    elif shadow['regime_disagreements'] > 0:
        print(f"  – Shadow regime fired {shadow['regime_disagreements']} disagreements "
              f"(modest — may need more sensitivity).")
    else:
        print(f"  – Shadow regime detector never disagreed with live "
              f"(market in chop throughout).")

    if shadow['orb_breakouts'] > 0:
        print(f"  • ORB shadow detected {shadow['orb_breakouts']} breakouts "
              f"across {len(shadow['orb_symbols'])} symbols. "
              f"Pass criteria: 3-12/session avg.")
    else:
        print(f"  – ORB shadow produced ZERO breakouts. Either: "
              f"(a) no high-RV stocks-in-play in the cached bars, "
              f"(b) min_rv_ratio threshold too high, "
              f"(c) replay's market scanner stub limits the data ORB sees.")

    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
