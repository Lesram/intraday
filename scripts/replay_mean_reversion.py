"""Replay harness for the mean-reversion scanner.

Runs MeanReversionScanner against cached bar history and simulates execution
with the scanner's own asymmetric R:R rules. Measures:
- candidates fired per session
- hit rate (target hit before stop or EOD)
- simulated PnL (long-only, 1R per trade with the scanner's stop math)
- per-symbol breakdown

Compares against the alpha+breakout 4-day baseline (-$0.73/trade strategy).

Usage:
  ./venv/bin/python scripts/replay_mean_reversion.py
  ./venv/bin/python scripts/replay_mean_reversion.py --alt   # use bars_alt.pkl
"""
from __future__ import annotations

import argparse
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path("/Users/marselkei/VS/intra")
sys.path.insert(0, str(REPO_ROOT))

from backend.organism.mean_reversion_scanner import MeanReversionScanner  # noqa: E402

BARS_PRIMARY = REPO_ROOT / "artifacts/backtest_rc_1_5/bars.pkl"
BARS_ALT = REPO_ROOT / "artifacts/backtest_rc_1_5/bars_alt.pkl"
OUT_DIR = REPO_ROOT / "artifacts/ferrari_v1"


# ── ATR computation matching ml_features.py:198 ────────────────


def _compute_atr_14(df: pd.DataFrame) -> pd.Series:
    """ATR(14) computed as fraction of close, matching production form."""
    h = df["high"].astype(float)
    l = df["low"].astype(float)
    c = df["close"].astype(float)
    prev_close = c.shift(1)
    tr1 = h - l
    tr2 = (h - prev_close).abs()
    tr3 = (l - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean()
    return atr / c.replace(0, 1e-10)


def _attach_atr(bars: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {}
    for sym, df in bars.items():
        if df is None or len(df) < 30:
            continue
        df = df.copy().reset_index(drop=True)
        if "timestamp" not in df.columns:
            print(f"  [skip] {sym}: no timestamp column", file=sys.stderr)
            continue
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["atr_14"] = _compute_atr_14(df)
        df = df.dropna(subset=["atr_14"]).reset_index(drop=True)
        if len(df) < 50:
            continue
        out[sym] = df
    return out


# ── Per-bar slicer ─────────────────────────────────────────────


def _bars_to_session_index(bars: dict[str, pd.DataFrame]) -> list[pd.Timestamp]:
    """Return sorted unique 1-min timestamps that exist in at least one symbol."""
    all_ts = set()
    for sym, df in bars.items():
        all_ts.update(df["timestamp"].tolist())
    return sorted(all_ts)


# ── Trade simulation ───────────────────────────────────────────


def _simulate_trade(
    df: pd.DataFrame,
    entry_idx: int,
    entry_price: float,
    target_price: float,
    stop_price: float,
    direction: float,
    eod_idx: int,
) -> tuple[str, float, int]:
    """Walk forward from entry_idx+1 until target/stop/EOD. Long-only support
    primarily (direction=+1); short logic mirrored.

    Returns (exit_reason, pnl_per_share, bars_held).
    """
    last_idx = min(eod_idx, len(df) - 1)
    for i in range(entry_idx + 1, last_idx + 1):
        bar_high = float(df["high"].iloc[i])
        bar_low = float(df["low"].iloc[i])
        if direction > 0:
            # Long: stop below, target above
            if bar_low <= stop_price:
                return ("stop", stop_price - entry_price, i - entry_idx)
            if bar_high >= target_price:
                return ("target", target_price - entry_price, i - entry_idx)
        else:
            if bar_high >= stop_price:
                return ("stop", entry_price - stop_price, i - entry_idx)
            if bar_low <= target_price:
                return ("target", entry_price - target_price, i - entry_idx)
    # EOD flatten at the last bar's close
    last_close = float(df["close"].iloc[last_idx])
    pnl = (last_close - entry_price) * direction
    return ("eod_flatten", pnl, last_idx - entry_idx)


# ── Main replay ────────────────────────────────────────────────


def replay(
    bars_path: Path,
    long_only: bool = True,
    min_displacement_atr: float = 1.5,
    target_retracement: float = 0.65,
    stop_extension_atr: float = 0.5,
    cooldown_minutes: int = 60,
    top_n: int = 5,
) -> dict:
    print(f"[replay] loading {bars_path.name}")
    with open(bars_path, "rb") as f:
        bars_raw = pickle.load(f)

    bars = _attach_atr(bars_raw)
    print(f"[replay] symbols with usable data: {len(bars)}")

    timeline = _bars_to_session_index(bars)
    print(f"[replay] timeline: {len(timeline)} unique 1-min stamps")
    if not timeline:
        return {"error": "empty timeline"}

    # Group timeline by ET-session-date to avoid scanning during off-hours
    et_dates = pd.DatetimeIndex(timeline).tz_convert("America/New_York")
    print(f"[replay] sessions covered: {sorted(set(d.date() for d in et_dates))}")

    scanner = MeanReversionScanner(
        min_displacement_atr=min_displacement_atr,
        target_retracement=target_retracement,
        stop_extension_atr=stop_extension_atr,
        cooldown_minutes=cooldown_minutes,
        top_n=top_n,
        long_only=long_only,
    )

    # Tracking
    candidates_fired = []   # list of dicts
    trades = []             # list of dicts (simulated execution)
    by_session = defaultdict(int)

    # For each timestamp in timeline, slice each symbol's df up to that ts
    # and run scan. We use pd.Index with searchsorted (tz-aware safe) for speed.
    sym_pos = {sym: 0 for sym in bars}
    sym_ts_idx = {sym: pd.DatetimeIndex(df["timestamp"]) for sym, df in bars.items()}

    for now in timeline:
        sliced = {}
        for sym, df in bars.items():
            idx = sym_ts_idx[sym]
            pos = sym_pos[sym]
            # advance pos forward as long as next bar is <= now
            n = len(idx)
            while pos < n - 1 and idx[pos + 1] <= now:
                pos += 1
            sym_pos[sym] = pos
            if idx[pos] != now:
                continue
            sliced[sym] = df.iloc[: pos + 1]

        if not sliced:
            continue

        cands = scanner.scan(sliced, now)
        if not cands:
            continue

        et_date = pd.Timestamp(now).tz_convert("America/New_York").date()
        by_session[et_date] += len(cands)

        for c in cands:
            scanner.mark_fired(c.symbol, now)
            candidates_fired.append({
                "session": str(et_date),
                "ts": pd.Timestamp(now).isoformat(),
                **c.to_dict(),
            })

            # Simulate trade execution
            sym_df = bars[c.symbol]
            sym_idx = sym_ts_idx[c.symbol]
            entry_idx = int(sym_idx.get_indexer([now])[0])
            if entry_idx < 0 or entry_idx >= len(sym_df):
                continue
            # Find EOD index for this session (last bar in this session)
            session_mask = (
                sym_idx.tz_convert("America/New_York").date == et_date
            )
            session_idxs = np.where(session_mask)[0]
            if len(session_idxs) == 0:
                continue
            eod_idx = int(session_idxs[-1])
            if eod_idx <= entry_idx:
                continue

            reason, pnl_per_share, bars_held = _simulate_trade(
                sym_df,
                entry_idx,
                entry_price=c.current_price,
                target_price=c.target_price,
                stop_price=c.stop_price,
                direction=c.direction,
                eod_idx=eod_idx,
            )
            trades.append({
                "session": str(et_date),
                "symbol": c.symbol,
                "entry_ts": pd.Timestamp(now).isoformat(),
                "entry_price": c.current_price,
                "target_price": c.target_price,
                "stop_price": c.stop_price,
                "direction": c.direction,
                "abs_distance_atr": c.abs_distance_atr,
                "expected_r_r": c.expected_r_r,
                "exit_reason": reason,
                "pnl_per_share": pnl_per_share,
                "bars_held": bars_held,
            })

    # Aggregate
    total_trades = len(trades)
    if total_trades == 0:
        summary = {
            "bars_file": bars_path.name,
            "candidates_fired": len(candidates_fired),
            "trades_simulated": 0,
            "note": "scanner produced 0 candidates on this dataset",
            "candidates_per_session": dict(by_session),
        }
        return summary

    total_pnl = sum(t["pnl_per_share"] for t in trades)
    wins = [t for t in trades if t["pnl_per_share"] > 0]
    by_reason = defaultdict(int)
    for t in trades:
        by_reason[t["exit_reason"]] += 1
    by_symbol_pnl = defaultdict(float)
    by_symbol_n = defaultdict(int)
    for t in trades:
        by_symbol_pnl[t["symbol"]] += t["pnl_per_share"]
        by_symbol_n[t["symbol"]] += 1

    avg_winner = (
        sum(t["pnl_per_share"] for t in wins) / len(wins) if wins else 0.0
    )
    losers = [t for t in trades if t["pnl_per_share"] <= 0]
    avg_loser = (
        sum(t["pnl_per_share"] for t in losers) / len(losers) if losers else 0.0
    )

    sessions = sorted(by_session.keys())
    candidates_per_day = (
        len(candidates_fired) / len(sessions) if sessions else 0
    )

    summary = {
        "bars_file": bars_path.name,
        "config": {
            "min_displacement_atr": min_displacement_atr,
            "target_retracement": target_retracement,
            "stop_extension_atr": stop_extension_atr,
            "long_only": long_only,
            "cooldown_minutes": cooldown_minutes,
            "top_n": top_n,
        },
        "candidates_fired": len(candidates_fired),
        "candidates_per_day": round(candidates_per_day, 2),
        "trades_simulated": total_trades,
        "total_pnl_per_share": round(total_pnl, 4),
        "avg_pnl_per_share": round(total_pnl / total_trades, 4),
        "win_rate_pct": round(100.0 * len(wins) / total_trades, 2),
        "avg_winner": round(avg_winner, 4),
        "avg_loser": round(avg_loser, 4),
        "win_to_loss_ratio": (
            round(avg_winner / abs(avg_loser), 3) if avg_loser else None
        ),
        "exit_reasons": dict(by_reason),
        "candidates_per_session": {str(k): v for k, v in by_session.items()},
        "by_symbol_pnl": {k: round(v, 4) for k, v in by_symbol_pnl.items()},
        "by_symbol_n": dict(by_symbol_n),
        "sessions_covered": [str(s) for s in sessions],
    }
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alt", action="store_true", help="use bars_alt.pkl")
    ap.add_argument("--displacement", type=float, default=1.5)
    ap.add_argument("--target", type=float, default=0.65)
    ap.add_argument("--stop", type=float, default=0.5)
    ap.add_argument("--cooldown", type=int, default=60)
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--long-only", action="store_true", default=True)
    ap.add_argument("--shorts-too", action="store_true",
                    help="disable long-only (allow shorts)")
    args = ap.parse_args()

    long_only = not args.shorts_too

    bars_path = BARS_ALT if args.alt else BARS_PRIMARY
    if not bars_path.exists():
        print(f"[error] {bars_path} not found", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    summary = replay(
        bars_path,
        long_only=long_only,
        min_displacement_atr=args.displacement,
        target_retracement=args.target,
        stop_extension_atr=args.stop,
        cooldown_minutes=args.cooldown,
        top_n=args.top_n,
    )

    suffix = "alt" if args.alt else "primary"
    if not long_only:
        suffix += "_shorts"
    out_json = OUT_DIR / f"mean_reversion_replay_{suffix}.json"
    out_json.write_text(json.dumps(summary, indent=2))
    print(f"\n[replay] wrote {out_json}")
    print(json.dumps({k: v for k, v in summary.items() if not isinstance(v, dict) or k == "config"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
