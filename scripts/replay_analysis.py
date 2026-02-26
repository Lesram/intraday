#!/usr/bin/env python3
"""
Replay Simulator — Detailed Trade-Level Analysis
=================================================
Runs a historical replay through the full organism pipeline and
prints comprehensive trade-level analytics.
"""

import asyncio
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Add project root to path so imports work
sys.path.insert(0, str(PROJECT_ROOT))

# ── Configuration ────────────────────────────────────────────────
SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD"]
START = "2024-01-02"
END = "2026-02-25"
TIMEFRAME = "1Day"
INITIAL_CASH = 100_000
SLIPPAGE_BPS = 5


async def main() -> None:
    from backend.organism.replay_simulator import ReplayEngine

    # ── 1. Fetch data & run replay ───────────────────────────────
    print("=" * 70)
    print("  FETCHING HISTORICAL DATA FROM ALPACA")
    print("=" * 70)
    print(f"  Symbols:   {', '.join(SYMBOLS)}")
    print(f"  Period:    {START} -> {END}")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  Cash:      ${INITIAL_CASH:,.0f}")
    print(f"  Slippage:  {SLIPPAGE_BPS} bps")
    print()

    engine = await ReplayEngine.from_alpaca(
        symbols=SYMBOLS,
        start=START,
        end=END,
        timeframe=TIMEFRAME,
        initial_cash=INITIAL_CASH,
        slippage_bps=SLIPPAGE_BPS,
    )

    print()
    print("=" * 70)
    print("  RUNNING REPLAY...")
    print("=" * 70)
    result = await engine.run()
    print()
    print(result.summary())
    print()

    trades = result.trades
    equity = result.equity_curve
    regime_hist = result.regime_history
    signals_log = result.signals_log
    tick_results = result.tick_results

    # ── 1. Every trade with details ──────────────────────────────
    print()
    print("=" * 70)
    print("  1. ALL TRADES — DETAILED LOG")
    print("=" * 70)
    if not trades:
        print("  (No completed trades)")
    else:
        header = f"  {'#':>4}  {'Symbol':<6}  {'Qty':>6}  {'Entry':>10}  {'Exit':>10}  {'PnL $':>12}  {'PnL %':>8}"
        print(header)
        print("  " + "-" * len(header.strip()))
        for i, t in enumerate(trades, 1):
            sym = t.get("symbol", "???")
            qty = t.get("qty", 0)
            entry = t.get("entry_price", 0)
            exit_p = t.get("exit_price", 0)
            pnl = t.get("pnl", 0)
            cost_basis = entry * qty if entry and qty else 1
            pnl_pct = (pnl / cost_basis * 100) if cost_basis != 0 else 0
            print(f"  {i:>4}  {sym:<6}  {qty:>6}  {entry:>10.2f}  {exit_p:>10.2f}  {pnl:>+12.2f}  {pnl_pct:>+7.2f}%")

    # ── 2. Winners vs Losers ─────────────────────────────────────
    print()
    print("=" * 70)
    print("  2. WINNERS vs LOSERS BREAKDOWN")
    print("=" * 70)
    if trades:
        winners = [t for t in trades if t.get("pnl", 0) > 0]
        losers = [t for t in trades if t.get("pnl", 0) <= 0]
        breakeven = [t for t in trades if t.get("pnl", 0) == 0]

        def avg_pnl(tlist):
            if not tlist:
                return 0
            return sum(t.get("pnl", 0) for t in tlist) / len(tlist)

        def avg_pnl_pct(tlist):
            if not tlist:
                return 0
            pcts = []
            for t in tlist:
                entry = t.get("entry_price", 0)
                qty = t.get("qty", 0)
                cb = entry * qty if entry and qty else 1
                pcts.append(t.get("pnl", 0) / cb * 100 if cb != 0 else 0)
            return sum(pcts) / len(pcts)

        print(f"  Total trades:     {len(trades)}")
        print(f"  Winners:          {len(winners)} ({len(winners)/len(trades)*100:.1f}%)")
        print(f"  Losers:           {len(losers)} ({len(losers)/len(trades)*100:.1f}%)")
        if breakeven:
            print(f"    (breakeven):    {len(breakeven)}")
        print()
        print(f"  Avg win  $:       ${avg_pnl(winners):>+,.2f}")
        print(f"  Avg loss $:       ${avg_pnl(losers):>+,.2f}")
        print(f"  Avg win  %:       {avg_pnl_pct(winners):>+.2f}%")
        print(f"  Avg loss %:       {avg_pnl_pct(losers):>+.2f}%")
        print()

        total_win = sum(t.get("pnl", 0) for t in winners)
        total_loss = sum(t.get("pnl", 0) for t in losers)
        profit_factor = abs(total_win / total_loss) if total_loss != 0 else float("inf")
        print(f"  Total win  $:     ${total_win:>+,.2f}")
        print(f"  Total loss $:     ${total_loss:>+,.2f}")
        print(f"  Profit factor:    {profit_factor:.2f}")
    else:
        print("  (No trades to analyze)")

    # ── 3. Biggest winner & loser ────────────────────────────────
    print()
    print("=" * 70)
    print("  3. BIGGEST WINNER & BIGGEST LOSER")
    print("=" * 70)
    if trades:
        best = max(trades, key=lambda t: t.get("pnl", 0))
        worst = min(trades, key=lambda t: t.get("pnl", 0))

        def trade_str(t):
            sym = t.get("symbol", "???")
            qty = t.get("qty", 0)
            entry = t.get("entry_price", 0)
            exit_p = t.get("exit_price", 0)
            pnl = t.get("pnl", 0)
            cb = entry * qty if entry and qty else 1
            pct = pnl / cb * 100 if cb != 0 else 0
            return f"{sym}  qty={qty}  entry=${entry:.2f}  exit=${exit_p:.2f}  PnL=${pnl:+,.2f} ({pct:+.2f}%)"

        print(f"  BEST:   {trade_str(best)}")
        print(f"  WORST:  {trade_str(worst)}")
    else:
        print("  (No trades)")

    # ── 4. Trades grouped by symbol ──────────────────────────────
    print()
    print("=" * 70)
    print("  4. TRADES GROUPED BY SYMBOL")
    print("=" * 70)
    if trades:
        by_sym = defaultdict(list)
        for t in trades:
            by_sym[t.get("symbol", "???")].append(t)

        print(f"  {'Symbol':<6}  {'Trades':>6}  {'Wins':>5}  {'Win%':>6}  {'Total PnL':>14}  {'Avg PnL':>12}")
        print("  " + "-" * 60)
        for sym in sorted(by_sym.keys()):
            st = by_sym[sym]
            wins = sum(1 for t in st if t.get("pnl", 0) > 0)
            total = sum(t.get("pnl", 0) for t in st)
            avg = total / len(st) if st else 0
            wr = wins / len(st) * 100 if st else 0
            tag = "  +" if total > 0 else "  -" if total < 0 else "  ="
            print(f"  {sym:<6}  {len(st):>6}  {wins:>5}  {wr:>5.1f}%  ${total:>+13,.2f}  ${avg:>+11,.2f}{tag}")
    else:
        print("  (No trades)")

    # ── 5. Regime distribution ───────────────────────────────────
    print()
    print("=" * 70)
    print("  5. REGIME DISTRIBUTION")
    print("=" * 70)
    if regime_hist:
        counts = Counter(regime_hist)
        total_ticks = len(regime_hist)
        print(f"  Total ticks with regime data: {total_ticks}")
        print()
        print(f"  {'Regime':<15}  {'Count':>6}  {'Pct':>7}  {'Bar':>40}")
        print("  " + "-" * 72)
        for regime, count in counts.most_common():
            pct = count / total_ticks * 100
            bar = "#" * int(pct / 2)
            print(f"  {regime:<15}  {count:>6}  {pct:>6.1f}%  {bar}")
    else:
        print("  (No regime data)")

    # ── 6. Signals vs Orders ─────────────────────────────────────
    print()
    print("=" * 70)
    print("  6. SIGNAL GENERATION vs ORDER SUBMISSION")
    print("=" * 70)
    if signals_log:
        total_ticks = len(signals_log)
        ticks_with_signals = sum(1 for s in signals_log if s.get("signals", 0) > 0)
        ticks_with_orders = sum(1 for s in signals_log if s.get("orders", 0) > 0)
        ticks_with_exits = sum(1 for s in signals_log if s.get("exits", 0) > 0)
        total_signals = sum(s.get("signals", 0) for s in signals_log)
        total_orders = sum(s.get("orders", 0) for s in signals_log)
        total_exits = sum(s.get("exits", 0) for s in signals_log)

        print(f"  Total ticks:              {total_ticks}")
        print(f"  Ticks w/ signals > 0:     {ticks_with_signals} ({ticks_with_signals/total_ticks*100:.1f}%)")
        print(f"  Ticks w/ orders > 0:      {ticks_with_orders} ({ticks_with_orders/total_ticks*100:.1f}%)")
        print(f"  Ticks w/ exits > 0:       {ticks_with_exits} ({ticks_with_exits/total_ticks*100:.1f}%)")
        print()
        print(f"  Total signals generated:  {total_signals}")
        print(f"  Total orders submitted:   {total_orders}")
        print(f"  Total exits:              {total_exits}")
        print(f"  Signal->Order rate:       {total_orders/total_signals*100:.1f}%" if total_signals else "  Signal->Order rate:       N/A")
    else:
        print("  (No signal data)")

    # ── 7. Equity curve ──────────────────────────────────────────
    print()
    print("=" * 70)
    print("  7. EQUITY CURVE")
    print("=" * 70)
    if equity:
        starting = equity[0]
        peak = max(equity)
        trough = min(equity)
        ending = equity[-1]
        peak_idx = equity.index(peak)
        trough_idx = equity.index(trough)
        total_return = (ending - starting) / starting * 100

        print(f"  Starting equity:  ${starting:>14,.2f}")
        print(f"  Peak equity:      ${peak:>14,.2f}  (tick {peak_idx})")
        print(f"  Trough equity:    ${trough:>14,.2f}  (tick {trough_idx})")
        print(f"  Ending equity:    ${ending:>14,.2f}")
        print(f"  Total return:     {total_return:>+13.2f}%")
        print(f"  Max drawdown:     {result.max_drawdown*100:>13.2f}%")
        print(f"  Sharpe ratio:     {result.sharpe:>13.2f}")

        # Mini ASCII equity chart (50 chars wide)
        print()
        print("  Equity curve (ASCII):")
        chart_width = 60
        n_points = min(chart_width, len(equity))
        step = max(1, len(equity) // n_points)
        sampled = [equity[i] for i in range(0, len(equity), step)]
        if sampled:
            eq_min = min(sampled)
            eq_max = max(sampled)
            eq_range = eq_max - eq_min if eq_max != eq_min else 1
            chart_height = 15
            grid = [[" "] * len(sampled) for _ in range(chart_height)]
            for col, val in enumerate(sampled):
                row = int((val - eq_min) / eq_range * (chart_height - 1))
                row = chart_height - 1 - row  # Invert so top = high
                grid[row][col] = "*"
            print(f"  ${eq_max:>12,.0f} |")
            for row_idx, row in enumerate(grid):
                if row_idx == 0 or row_idx == chart_height - 1 or row_idx == chart_height // 2:
                    print(f"               |{''.join(row)}")
                else:
                    print(f"               |{''.join(row)}")
            print(f"  ${eq_min:>12,.0f} |{'_' * len(sampled)}")
            print(f"               0{' ' * (len(sampled) - 5)}ticks")
    else:
        print("  (No equity data)")

    # ── 8. Trade timing ──────────────────────────────────────────
    print()
    print("=" * 70)
    print("  8. TRADE TIMING — ENTRIES vs EXITS PER TICK")
    print("=" * 70)
    if tick_results:
        entry_ticks = []
        exit_ticks = []
        for i, tr in enumerate(tick_results):
            if isinstance(tr, dict):
                orders = tr.get("orders_submitted", 0)
                exits = tr.get("trades_closed", 0)
                if orders > 0:
                    entry_ticks.append((i, orders))
                if exits > 0:
                    exit_ticks.append((i, exits))

        print(f"  Total ticks:     {len(tick_results)}")
        print(f"  Entry ticks:     {len(entry_ticks)}")
        print(f"  Exit ticks:      {len(exit_ticks)}")
        print()

        if entry_ticks:
            print("  First 20 entry ticks:")
            for tick_num, count in entry_ticks[:20]:
                regime = regime_hist[tick_num] if tick_num < len(regime_hist) else "?"
                print(f"    tick {tick_num:>5}  orders={count}  regime={regime}")
            if len(entry_ticks) > 20:
                print(f"    ... and {len(entry_ticks) - 20} more entry ticks")

        print()
        if exit_ticks:
            print("  First 20 exit ticks:")
            for tick_num, count in exit_ticks[:20]:
                regime = regime_hist[tick_num] if tick_num < len(regime_hist) else "?"
                print(f"    tick {tick_num:>5}  exits={count}  regime={regime}")
            if len(exit_ticks) > 20:
                print(f"    ... and {len(exit_ticks) - 20} more exit ticks")
    else:
        print("  (No tick result data)")

    print()
    print("=" * 70)
    print("  ANALYSIS COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
