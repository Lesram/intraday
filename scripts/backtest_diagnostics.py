"""Backtest diagnostics ("go back on the backtest")

Reads a platform BacktestResult JSON export and highlights:
- Worst drawdown segments (peak -> trough -> recovery)
- Worst days / biggest equity drops
- Biggest losing trades + symbol contribution during drawdowns

This is intended to support iterative strategy improvement: identify *where* and *why*
losses occurred, then adjust rules/overlays and re-run.

Usage:
  python scripts/backtest_diagnostics.py --path path/to/backtest_result.json
  python scripts/backtest_diagnostics.py --path path/to/backtest_result.json --top 7

Notes:
- Expects the JSON schema produced by backend backtests (equity_curve + trade_log).
- Works for both engines because it uses the normalized platform result format.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True)
class DrawdownSegment:
    peak_date: date
    peak_value: float
    trough_date: date
    trough_value: float
    recovery_date: date | None
    max_dd_pct: float


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Accept YYYY-MM-DD or ISO timestamps.
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        except Exception:
            try:
                return datetime.strptime(s[:10], "%Y-%m-%d").date()
            except Exception:
                return None
    return None


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _compute_drawdown_segments(dates: list[date], equity: list[float], top: int) -> list[DrawdownSegment]:
    if not dates or not equity or len(dates) != len(equity):
        return []

    peak_idx = 0
    peak_value = equity[0]
    peak_date = dates[0]

    in_drawdown = False
    trough_idx = 0

    segments: list[DrawdownSegment] = []

    for i in range(1, len(equity)):
        v = equity[i]

        if v >= peak_value:
            # New peak; if we were in a drawdown, close it.
            if in_drawdown:
                trough_value = equity[trough_idx]
                dd = (peak_value - trough_value) / peak_value if peak_value > 0 else 0.0
                segments.append(
                    DrawdownSegment(
                        peak_date=peak_date,
                        peak_value=float(peak_value),
                        trough_date=dates[trough_idx],
                        trough_value=float(trough_value),
                        recovery_date=dates[i],
                        max_dd_pct=float(dd * 100.0),
                    )
                )
                in_drawdown = False

            peak_idx = i
            peak_value = v
            peak_date = dates[i]
            trough_idx = i
            continue

        # Below peak
        if not in_drawdown:
            in_drawdown = True
            trough_idx = i
        else:
            if v < equity[trough_idx]:
                trough_idx = i

    # If still in drawdown at the end, emit an unrecovered segment.
    if in_drawdown:
        trough_value = equity[trough_idx]
        dd = (peak_value - trough_value) / peak_value if peak_value > 0 else 0.0
        segments.append(
            DrawdownSegment(
                peak_date=peak_date,
                peak_value=float(peak_value),
                trough_date=dates[trough_idx],
                trough_value=float(trough_value),
                recovery_date=None,
                max_dd_pct=float(dd * 100.0),
            )
        )

    segments.sort(key=lambda s: s.max_dd_pct, reverse=True)
    return segments[: max(1, int(top))]


def _sum_trade_pnl_in_window(trades: list[dict], start: date, end: date) -> dict[str, float]:
    pnl_by_symbol: dict[str, float] = {}
    for t in trades:
        exit_dt = _parse_date(t.get("exit_date"))
        if exit_dt is None:
            continue
        if exit_dt < start or exit_dt > end:
            continue
        sym = str(t.get("symbol") or "?")
        pnl = _coerce_float(t.get("pnl"), 0.0)
        pnl_by_symbol[sym] = pnl_by_symbol.get(sym, 0.0) + pnl
    return dict(sorted(pnl_by_symbol.items(), key=lambda kv: kv[1]))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Backtest diagnostics from a BacktestResult JSON export")
    parser.add_argument("--path", required=True, help="Path to BacktestResult JSON file")
    parser.add_argument("--top", type=int, default=5, help="How many segments/trades to show")
    parser.add_argument(
        "--emit-overlay-template",
        dest="emit_overlay",
        default="",
        help="Optional path to write a suggested overlay JSON template",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    strategy = raw.get("strategy_name") or raw.get("strategy") or "(unknown)"
    engine = raw.get("engine") or "platform"
    metrics = raw.get("metrics") or {}

    equity_curve = raw.get("equity_curve") or []
    trade_log = raw.get("trade_log") or []

    dates: list[date] = []
    equity: list[float] = []
    daily_returns: list[float] = []

    prev = None
    for pt in equity_curve:
        d = _parse_date(pt.get("date") if isinstance(pt, dict) else None)
        v = _coerce_float(pt.get("value") if isinstance(pt, dict) else None, 0.0)
        if d is None:
            continue
        dates.append(d)
        equity.append(v)
        if prev is not None and prev > 0:
            daily_returns.append((v - prev) / prev)
        prev = v

    print("=" * 88)
    print(f"BACKTEST DIAGNOSTICS  |  Engine={engine}  |  Strategy={strategy}")
    print("=" * 88)

    total_return = metrics.get("total_return")
    cagr = metrics.get("annualized_return")
    sharpe = metrics.get("sharpe_ratio")
    mdd = metrics.get("max_drawdown")

    print("Metrics (as reported by backtest):")
    print(f"  total_return:      {total_return}")
    print(f"  annualized_return: {cagr}")
    print(f"  sharpe_ratio:      {sharpe}")
    print(f"  max_drawdown:      {mdd}")

    if not dates or len(dates) < 5:
        print("\nNo usable equity_curve points found.")
        return 0

    # Worst drawdowns
    segments = _compute_drawdown_segments(dates, equity, top=args.top)
    print("\nWorst drawdown segments:")
    for i, seg in enumerate(segments, 1):
        rec = seg.recovery_date.isoformat() if seg.recovery_date else "(not recovered)"
        print(
            f"  {i:>2}. {seg.max_dd_pct:>6.2f}%  peak {seg.peak_date} (${seg.peak_value:,.0f})"
            f" -> trough {seg.trough_date} (${seg.trough_value:,.0f}) -> recovery {rec}"
        )

        contrib = _sum_trade_pnl_in_window(trade_log, seg.peak_date, seg.trough_date)
        worst = list(contrib.items())[: min(8, len(contrib))]
        if worst:
            print("      Biggest PnL contributors (exit during peak->trough):")
            for sym, pnl in worst:
                print(f"        {sym:>6}: {pnl:>12,.2f}")

    # Worst days
    if daily_returns:
        paired = list(zip(dates[1:], daily_returns))
        paired.sort(key=lambda kv: kv[1])
        print("\nWorst single-day equity moves:")
        for d, r in paired[: max(1, int(args.top))]:
            print(f"  {d}: {r * 100.0:>7.2f}%")

    # Worst trades
    losing_trades = []
    for t in trade_log:
        if not isinstance(t, dict):
            continue
        pnl = _coerce_float(t.get("pnl"), 0.0)
        if pnl < 0:
            losing_trades.append(t)

    losing_trades.sort(key=lambda t: _coerce_float(t.get("pnl"), 0.0))
    print("\nBiggest losing trades:")
    for t in losing_trades[: max(1, int(args.top))]:
        sym = str(t.get("symbol") or "?")
        entry = _parse_date(t.get("entry_date"))
        exit_dt = _parse_date(t.get("exit_date"))
        pnl = _coerce_float(t.get("pnl"), 0.0)
        pnl_pct = t.get("pnl_percent")
        reason = t.get("exit_reason")
        print(
            f"  {sym:>6}  pnl={pnl:>10,.2f}  pnl%={pnl_pct!s:>8}  {entry} -> {exit_dt}  reason={reason}"
        )

    print("\nNext iteration ideas (rule overlays to test):")
    print("  - Add a 'kill-switch' when rolling drawdown exceeds X% (pause entries for N days).")
    print("  - Add volatility targeting (size down when realized vol spikes).")
    print("  - Add gap-risk guardrails (avoid holding through known high-risk events, or reduce size).")
    print("  - Add regime-specific stops (tighter stops in risk-off, looser in risk-on).")

    if args.emit_overlay:
        max_dd_pct = max((seg.max_dd_pct for seg in segments), default=0.0)
        # Convert from percent to decimal for params (e.g., 20% -> 0.20)
        max_dd_dec = max_dd_pct / 100.0 if max_dd_pct > 0 else 0.0
        kill_dd = max(0.12, min(0.30, max_dd_dec * 0.8)) if max_dd_dec > 0 else 0.18

        overlay_template = {
            "overlay_kill_switch": 1,
            "overlay_kill_dd_pct": round(kill_dd, 4),
            "overlay_kill_cooldown_days": 10,
            "overlay_kill_force_exit": 1,
            "overlay_vol_enabled": 1,
            "overlay_vol_target": 0.18,
            "overlay_vol_window": 20,
            "overlay_vol_min_mult": 0.5,
            "overlay_vol_max_mult": 1.5,
            "overlay_gap_enabled": 1,
            "overlay_gap_max_pct": 0.04,
            "overlay_risk_off_adjust": 1,
            "overlay_risk_off_stop_mult": 0.7,
            "overlay_risk_off_take_mult": 0.8,
        }

        out_path = Path(args.emit_overlay)
        out_path.write_text(json.dumps(overlay_template, indent=2), encoding="utf-8")
        print(f"\nWrote overlay template to: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
