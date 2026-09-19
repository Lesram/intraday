"""Phase 3 ORB shadow outcome simulator.

This is an offline research tool. It uses the current ORBScanner to detect
shadow-style opening-range breakouts from cached bars, then evaluates a simple
next-bar-open hypothetical trade with the scanner's suggested stop and an EOD
exit. It does not change live trading behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import pickle
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.organism.orb_scanner import ORBScanner

DEFAULT_CACHE_DIR = ROOT / "artifacts" / "backtest_rc_1_5"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase3_orb_shadow_outcome"
ET_TZ = "America/New_York"
ORB_START_MINUTE_ET = 9 * 60 + 35
NO_NEW_ENTRY_MINUTE_ET = 15 * 60 + 55


@dataclass(frozen=True)
class SimulationConfig:
    symbols: list[str] | None = None
    top_n: int = 10
    min_rv_ratio: float = 1.5
    stop_atr_mult: float = 1.0
    slippage_bps: float = 5.0
    lookback_rows: int = 3000
    max_stale_minutes: float = 1.0
    max_sessions: int | None = None
    min_trades_for_signal: int = 30


@dataclass(frozen=True)
class OrbOutcome:
    symbol: str
    session: str
    direction: float
    rv_ratio: float
    trigger_ts: str
    entry_ts: str
    exit_ts: str
    entry_open: float
    entry_fill: float
    exit_price: float
    exit_fill: float
    stop_price: float
    exit_reason: str
    pnl_per_share: float
    r_multiple: float
    mfe_r: float
    mae_r: float
    hold_minutes: float
    orb_high: float
    orb_low: float
    orb_open: float
    orb_close: float


def parse_symbols(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    symbols = [part.strip().upper() for part in raw.split(",") if part.strip()]
    if not symbols:
        raise ValueError("symbol filter cannot be empty")
    return symbols


def load_cached_bars(cache_dir: Path) -> dict[str, pd.DataFrame]:
    bars_path = cache_dir / "bars.pkl"
    if not bars_path.is_file():
        raise FileNotFoundError(f"cached bars missing: {bars_path}")
    with bars_path.open("rb") as fh:
        bars = pickle.load(fh)
    if not isinstance(bars, dict) or not bars:
        raise ValueError(f"cached bars are empty or invalid: {bars_path}")
    return bars


def _atr_abs(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    fallback = true_range.rolling(5, min_periods=1).mean()
    return true_range.rolling(period, min_periods=period).mean().fillna(fallback)


def normalize_bars(
    raw_bars: dict[str, pd.DataFrame],
    symbols: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    selected = symbols or sorted(raw_bars)
    missing = [symbol for symbol in selected if symbol not in raw_bars]
    if missing:
        raise ValueError(f"symbols missing from cached bars: {missing}")

    normalized: dict[str, pd.DataFrame] = {}
    for symbol in selected:
        df = raw_bars[symbol]
        if df is None or len(df) == 0:
            continue
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            continue
        out = df.copy()
        out["timestamp"] = pd.to_datetime(
            out["timestamp"],
            errors="coerce",
            utc=True,
        )
        out = out.dropna(subset=["timestamp"]).sort_values("timestamp")
        for col in ("open", "high", "low", "close", "volume"):
            out[col] = pd.to_numeric(out[col], errors="coerce")
        out = out.dropna(subset=["open", "high", "low", "close", "volume"])
        if len(out) < 6:
            continue
        out["atr_abs_14"] = _atr_abs(out)
        normalized[symbol] = out.reset_index(drop=True)
    if not normalized:
        raise ValueError("no usable bars after normalization")
    return normalized


def _et_timestamp(ts: pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(ET_TZ)


def _session(ts: pd.Timestamp) -> str:
    return _et_timestamp(ts).strftime("%Y-%m-%d")


def _minute_et(ts: pd.Timestamp) -> int:
    et = _et_timestamp(ts)
    return int(et.hour) * 60 + int(et.minute)


def _is_decision_time(ts: pd.Timestamp) -> bool:
    minute = _minute_et(ts)
    return ORB_START_MINUTE_ET <= minute < NO_NEW_ENTRY_MINUTE_ET


def _selected_sessions(
    bars: dict[str, pd.DataFrame],
    max_sessions: int | None,
) -> set[str]:
    sessions = sorted({
        _session(ts)
        for df in bars.values()
        for ts in df["timestamp"]
        if _is_decision_time(ts)
    })
    if max_sessions is not None:
        if max_sessions <= 0:
            raise ValueError("max_sessions must be positive")
        sessions = sessions[-max_sessions:]
    return set(sessions)


def iter_decision_times(
    bars: dict[str, pd.DataFrame],
    *,
    max_sessions: int | None,
) -> list[pd.Timestamp]:
    allowed_sessions = _selected_sessions(bars, max_sessions)
    times = {
        pd.Timestamp(ts)
        for df in bars.values()
        for ts in df["timestamp"]
        if _session(ts) in allowed_sessions and _is_decision_time(ts)
    }
    return sorted(times)


def _latest_pos_at_or_before(df: pd.DataFrame, ts: pd.Timestamp) -> int:
    return int(df["timestamp"].searchsorted(ts, side="right") - 1)


def _fresh_snapshot(
    bars: dict[str, pd.DataFrame],
    now: pd.Timestamp,
    config: SimulationConfig,
) -> tuple[dict[str, pd.DataFrame], dict[str, float]]:
    features: dict[str, pd.DataFrame] = {}
    atr_by_symbol: dict[str, float] = {}
    now_session = _session(now)
    max_stale_s = config.max_stale_minutes * 60.0
    for symbol, df in bars.items():
        pos = _latest_pos_at_or_before(df, now)
        if pos < 0:
            continue
        latest_ts = pd.Timestamp(df["timestamp"].iloc[pos])
        if _session(latest_ts) != now_session:
            continue
        stale_s = (pd.Timestamp(now) - latest_ts).total_seconds()
        if stale_s < -1e-9 or stale_s > max_stale_s:
            continue
        start = max(0, pos + 1 - config.lookback_rows)
        frame = df.iloc[start: pos + 1].copy().reset_index(drop=True)
        features[symbol] = frame
        atr = float(frame["atr_abs_14"].iloc[-1])
        atr_by_symbol[symbol] = atr if np.isfinite(atr) and atr > 0 else 0.0
    return features, atr_by_symbol


def _next_bar_position(df: pd.DataFrame, ts: pd.Timestamp) -> int | None:
    pos = int(df["timestamp"].searchsorted(ts, side="right"))
    if pos >= len(df):
        return None
    if _session(pd.Timestamp(df["timestamp"].iloc[pos])) != _session(ts):
        return None
    if _minute_et(pd.Timestamp(df["timestamp"].iloc[pos])) >= NO_NEW_ENTRY_MINUTE_ET:
        return None
    return pos


def _session_exit_position(df: pd.DataFrame, start_pos: int) -> int:
    session = _session(pd.Timestamp(df["timestamp"].iloc[start_pos]))
    exit_pos = start_pos
    for pos in range(start_pos, len(df)):
        ts = pd.Timestamp(df["timestamp"].iloc[pos])
        if _session(ts) != session:
            break
        if _minute_et(ts) >= NO_NEW_ENTRY_MINUTE_ET:
            break
        exit_pos = pos
    return exit_pos


def _apply_entry_slippage(price: float, direction: float, slippage_bps: float) -> float:
    return price * (1 + direction * slippage_bps / 10_000)


def _apply_exit_slippage(price: float, direction: float, slippage_bps: float) -> float:
    return price * (1 - direction * slippage_bps / 10_000)


def evaluate_candidate(
    candidate: Any,
    df: pd.DataFrame,
    *,
    trigger_ts: pd.Timestamp,
    slippage_bps: float,
) -> OrbOutcome | None:
    entry_pos = _next_bar_position(df, trigger_ts)
    if entry_pos is None:
        return None

    direction = float(candidate.direction)
    entry_ts = pd.Timestamp(df["timestamp"].iloc[entry_pos])
    entry_open = float(df["open"].iloc[entry_pos])
    stop_price = float(candidate.suggested_stop)
    if not np.isfinite(entry_open) or not np.isfinite(stop_price):
        return None

    risk = (
        entry_open - stop_price
        if direction > 0
        else stop_price - entry_open
    )
    if risk <= 0 or not np.isfinite(risk):
        return None

    exit_pos = _session_exit_position(df, entry_pos)
    exit_reason = "eod"
    exit_price = float(df["close"].iloc[exit_pos])
    exit_ts = pd.Timestamp(df["timestamp"].iloc[exit_pos])
    mfe = 0.0
    mae = 0.0

    for pos in range(entry_pos, exit_pos + 1):
        high = float(df["high"].iloc[pos])
        low = float(df["low"].iloc[pos])
        if direction > 0:
            mfe = max(mfe, high - entry_open)
            mae = min(mae, low - entry_open)
            if low <= stop_price:
                exit_reason = "stop"
                exit_price = stop_price
                exit_ts = pd.Timestamp(df["timestamp"].iloc[pos])
                break
        else:
            mfe = max(mfe, entry_open - low)
            mae = min(mae, entry_open - high)
            if high >= stop_price:
                exit_reason = "stop"
                exit_price = stop_price
                exit_ts = pd.Timestamp(df["timestamp"].iloc[pos])
                break

    entry_fill = _apply_entry_slippage(entry_open, direction, slippage_bps)
    exit_fill = _apply_exit_slippage(exit_price, direction, slippage_bps)
    pnl = direction * (exit_fill - entry_fill)
    hold_minutes = (exit_ts - entry_ts).total_seconds() / 60.0

    return OrbOutcome(
        symbol=str(candidate.symbol),
        session=_session(trigger_ts),
        direction=direction,
        rv_ratio=float(candidate.rv_ratio),
        trigger_ts=pd.Timestamp(trigger_ts).isoformat(),
        entry_ts=entry_ts.isoformat(),
        exit_ts=exit_ts.isoformat(),
        entry_open=entry_open,
        entry_fill=entry_fill,
        exit_price=exit_price,
        exit_fill=exit_fill,
        stop_price=stop_price,
        exit_reason=exit_reason,
        pnl_per_share=pnl,
        r_multiple=pnl / risk,
        mfe_r=mfe / risk,
        mae_r=mae / risk,
        hold_minutes=hold_minutes,
        orb_high=float(candidate.orb_high),
        orb_low=float(candidate.orb_low),
        orb_open=float(candidate.orb_open),
        orb_close=float(candidate.orb_close),
    )


def run_orb_simulation(
    bars: dict[str, pd.DataFrame],
    config: SimulationConfig,
) -> list[OrbOutcome]:
    scanner = ORBScanner(
        top_n=config.top_n,
        min_rv_ratio=config.min_rv_ratio,
        stop_atr_mult=config.stop_atr_mult,
    )
    outcomes: list[OrbOutcome] = []
    for now in iter_decision_times(bars, max_sessions=config.max_sessions):
        features, atr_by_symbol = _fresh_snapshot(bars, now, config)
        if not features:
            continue
        current_session = _session(now)
        candidates = scanner.scan(
            features,
            now,
            session_date=current_session,
            atr_by_symbol=atr_by_symbol,
        )
        for candidate in candidates:
            if not candidate.breakout_triggered:
                continue
            symbol_bars = bars.get(candidate.symbol)
            if symbol_bars is None:
                continue
            outcome = evaluate_candidate(
                candidate,
                symbol_bars,
                trigger_ts=now,
                slippage_bps=config.slippage_bps,
            )
            if outcome is None:
                continue
            outcomes.append(outcome)
            scanner.mark_fired(candidate.symbol)
    return outcomes


def summarize_outcomes(
    outcomes: list[OrbOutcome],
    config: SimulationConfig,
) -> dict[str, Any]:
    total = len(outcomes)
    gross_pnl = sum(o.pnl_per_share for o in outcomes)
    wins = sum(1 for o in outcomes if o.pnl_per_share > 0)
    r_values = [o.r_multiple for o in outcomes]
    by_reason = Counter(o.exit_reason for o in outcomes)
    by_symbol: dict[str, dict[str, Any]] = {}
    grouped: dict[str, list[OrbOutcome]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.symbol].append(outcome)
    for symbol, rows in sorted(grouped.items()):
        by_symbol[symbol] = {
            "trades": len(rows),
            "pnl_per_share": sum(o.pnl_per_share for o in rows),
            "avg_r": sum(o.r_multiple for o in rows) / len(rows),
            "win_rate": sum(1 for o in rows if o.pnl_per_share > 0) / len(rows),
        }

    avg_pnl = gross_pnl / total if total else 0.0
    avg_r = sum(r_values) / total if total else 0.0
    med_r = median(r_values) if r_values else 0.0
    stop_rate = by_reason.get("stop", 0) / total if total else 0.0
    win_rate = wins / total if total else 0.0

    if total < config.min_trades_for_signal and gross_pnl <= 0:
        recommendation = "insufficient_negative_sample"
    elif total < config.min_trades_for_signal:
        recommendation = "insufficient_sample"
    elif gross_pnl > 0 and avg_r > 0.05 and win_rate >= 0.45:
        recommendation = "continue_shadow_review"
    else:
        recommendation = "do_not_promote_from_offline_sim"

    return {
        "criteria": {
            "min_trades_for_signal": config.min_trades_for_signal,
            "positive_total_pnl_required": True,
            "min_avg_r_for_shadow_review": 0.05,
            "min_win_rate_for_shadow_review": 0.45,
            "scope": "offline_outcome_sim_only",
        },
        "config": asdict(config),
        "total_trades": total,
        "gross_pnl_per_share": gross_pnl,
        "avg_pnl_per_share": avg_pnl,
        "win_rate": win_rate,
        "avg_r": avg_r,
        "median_r": med_r,
        "stop_rate": stop_rate,
        "exit_reason_mix": dict(by_reason),
        "by_symbol": by_symbol,
        "recommendation": recommendation,
    }


def write_outputs(
    outcomes: list[OrbOutcome],
    summary: dict[str, Any],
    out_dir: Path,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary_orb_shadow_outcome.json"
    trades_path = out_dir / "trades_orb_shadow_outcome.csv"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    with trades_path.open("w", newline="") as fh:
        fieldnames = list(asdict(outcomes[0]).keys()) if outcomes else [
            "symbol",
            "session",
            "direction",
            "trigger_ts",
            "entry_ts",
            "exit_ts",
            "pnl_per_share",
            "r_multiple",
            "exit_reason",
        ]
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for outcome in outcomes:
            writer.writerow(asdict(outcome))
    return summary_path, trades_path


def amain() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-rv-ratio", type=float, default=1.5)
    parser.add_argument("--stop-atr-mult", type=float, default=1.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--lookback-rows", type=int, default=3000)
    parser.add_argument("--max-stale-minutes", type=float, default=1.0)
    parser.add_argument("--max-sessions", type=int, default=None)
    parser.add_argument("--min-trades-for-signal", type=int, default=30)
    args = parser.parse_args()

    config = SimulationConfig(
        symbols=parse_symbols(args.symbols),
        top_n=args.top_n,
        min_rv_ratio=args.min_rv_ratio,
        stop_atr_mult=args.stop_atr_mult,
        slippage_bps=args.slippage_bps,
        lookback_rows=args.lookback_rows,
        max_stale_minutes=args.max_stale_minutes,
        max_sessions=args.max_sessions,
        min_trades_for_signal=args.min_trades_for_signal,
    )
    raw_bars = load_cached_bars(args.cache_dir)
    bars = normalize_bars(raw_bars, config.symbols)
    outcomes = run_orb_simulation(bars, config)
    summary = summarize_outcomes(outcomes, config)
    summary_path, trades_path = write_outputs(outcomes, summary, args.out_dir)

    print(f"[orb] bars={len(bars)} symbols")
    print(f"[orb] trades={summary['total_trades']}")
    print(f"[orb] gross_pnl_per_share={summary['gross_pnl_per_share']:.4f}")
    print(f"[orb] avg_r={summary['avg_r']:.4f}")
    print(f"[orb] win_rate={summary['win_rate']:.1%}")
    print(f"[orb] recommendation={summary['recommendation']}")
    print(f"[orb] summary={summary_path}")
    print(f"[orb] trades={trades_path}")


if __name__ == "__main__":
    amain()
