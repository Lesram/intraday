"""Phase 3 alternative-timeframe replay scout.

Offline research tool: replay the current live decision stack against the same
cached bars at 1Min and resampled 5Min granularity. This is a scout only; it
does not change live behavior and cannot promote a timeframe by itself.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import pickle
import shutil
import sys
import time
import warnings
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_CACHE_DIR = ROOT / "artifacts" / "backtest_rc_1_5"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase3_timeframe_scout"
DEFAULT_SEED_CANDIDATES = (
    ROOT / "artifacts" / "deploy_preflight_rc_1_5_curated"
    / "organism_brain_backup_pre_rc_1_5_curated_20260425_005638",
    ROOT / "artifacts" / "deploy_preflight_eb90fa3"
    / "organism_brain_backup_pre_eb90fa3_20260425",
)
DEFAULT_SYMBOLS = ("NVDA", "SPY", "QQQ")
TIMEFRAME_RULES = {
    "1Min": None,
    "5Min": "5min",
}


def default_seed_dir() -> Path:
    for candidate in DEFAULT_SEED_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return DEFAULT_SEED_CANDIDATES[0]


def parse_csv_list(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("comma-separated list cannot be empty")
    return values


def parse_symbols(raw: str | None) -> list[str]:
    values = parse_csv_list(raw)
    return [value.upper() for value in (values or list(DEFAULT_SYMBOLS))]


def parse_timeframes(raw: str) -> list[str]:
    timeframes = parse_csv_list(raw) or []
    unsupported = [tf for tf in timeframes if tf not in TIMEFRAME_RULES]
    if unsupported:
        raise ValueError(f"unsupported timeframe(s): {unsupported}")
    if "1Min" not in timeframes:
        raise ValueError("1Min baseline must be included")
    return timeframes


def configure_replay_logging(*, verbose: bool) -> None:
    if verbose:
        return
    warnings.filterwarnings(
        "ignore",
        message="divide by zero encountered in log10",
        category=RuntimeWarning,
    )
    for name in (
        "backend.organism.orb_scanner",
        "backend.organism.live_engine",
        "backend.organism.governance",
        "backend.organism.replay_simulator",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)


def count_trade_history_rows(brain_dir: Path) -> int:
    path = brain_dir / "trade_history.csv"
    if not path.is_file():
        raise FileNotFoundError(f"seed missing trade_history.csv: {path}")
    with path.open() as fh:
        return sum(1 for _ in csv.DictReader(fh))


def prepare_seed_dir(seed_source: Path, out_dir: Path, label: str) -> tuple[Path, int]:
    if not seed_source.is_dir():
        raise FileNotFoundError(f"brain seed dir missing: {seed_source}")
    seed_count = count_trade_history_rows(seed_source)
    target = out_dir / f"brain_seed_{label}"
    if seed_source.resolve() == target.resolve():
        raise ValueError("seed source and replay target must be different paths")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(seed_source, target)
    return target, seed_count


def read_new_trade_rows(brain_dir: Path, seed_count: int) -> list[dict[str, str]]:
    path = brain_dir / "trade_history.csv"
    if not path.is_file():
        return []
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    return rows[seed_count:] if len(rows) > seed_count else []


def load_cached_bars(cache_dir: Path, bar_file: str = "bars.pkl") -> dict[str, Any]:
    bars_path = cache_dir / bar_file
    if not bars_path.is_file():
        raise FileNotFoundError(f"cached bars missing: {bars_path}")
    with bars_path.open("rb") as fh:
        bars = pickle.load(fh)
    if not isinstance(bars, dict) or not bars:
        raise ValueError(f"cached bars are empty or invalid: {bars_path}")
    return bars


def normalize_bar_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError(f"bar frame missing required columns: {sorted(required)}")
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    for column in ("open", "high", "low", "close", "volume"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(subset=list(required)).sort_values("timestamp")
    if out.empty:
        raise ValueError("bar frame is empty after normalization")
    return out.reset_index(drop=True)


def select_and_limit_bars(
    bars: dict[str, Any],
    *,
    symbols: list[str],
    bar_limit: int | None,
) -> dict[str, pd.DataFrame]:
    missing = [symbol for symbol in symbols if symbol not in bars]
    if missing:
        raise ValueError(f"symbols missing from cached bars: {missing}")
    if bar_limit is not None and bar_limit <= 0:
        raise ValueError("bar limit must be positive")
    selected: dict[str, pd.DataFrame] = {}
    for symbol in symbols:
        frame = normalize_bar_frame(bars[symbol])
        if bar_limit is not None:
            frame = frame.tail(bar_limit)
        selected[symbol] = frame.reset_index(drop=True)
    return selected


def resample_bars(
    bars: dict[str, pd.DataFrame],
    timeframe: str,
) -> dict[str, pd.DataFrame]:
    rule = TIMEFRAME_RULES[timeframe]
    if rule is None:
        return {symbol: frame.copy().reset_index(drop=True) for symbol, frame in bars.items()}

    resampled: dict[str, pd.DataFrame] = {}
    for symbol, frame in bars.items():
        indexed = frame.set_index("timestamp").sort_index()
        out = indexed.resample(rule).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        out = out.dropna(subset=["open", "high", "low", "close"])
        if out.empty:
            continue
        out["timestamp"] = out.index
        resampled[symbol] = out[
            ["timestamp", "open", "high", "low", "close", "volume"]
        ].reset_index(drop=True)
    if not resampled:
        raise ValueError(f"no bars left after {timeframe} resample")
    return resampled


def exit_bucket(reason: str) -> str:
    reason = (reason or "unknown").lower()
    if "pyramid_cut" in reason:
        return "pyramid_cut"
    if "stop_loss" in reason:
        return "stop_loss"
    if "trailing_stop" in reason:
        return "trailing_stop"
    if "max_holding" in reason:
        return "max_holding"
    if "failure_to_follow" in reason or "ftf" in reason:
        return "failure_to_follow"
    if "take_profit" in reason:
        return "take_profit"
    if "eod_flatten" in reason:
        return "eod_flatten"
    return "other"


def summarize_exit_mix(rows: list[dict[str, str]]) -> dict[str, Any]:
    buckets = Counter(exit_bucket(row.get("exit_reason", "")) for row in rows)
    total = sum(buckets.values())
    return {
        "total": total,
        "buckets": dict(buckets),
        "shares": {
            bucket: count / total if total else 0.0
            for bucket, count in sorted(buckets.items())
        },
    }


async def run_timeframe_variant(
    *,
    timeframe: str,
    bars: dict[str, pd.DataFrame],
    seed_source: Path,
    out_dir: Path,
    max_ticks: int | None,
    lookback: int,
    max_entries_per_hour: int,
) -> dict[str, Any]:
    from backend.organism.replay_simulator import ReplayEngine

    label = timeframe.lower()
    seed_dir, seed_count = prepare_seed_dir(seed_source, out_dir, label)
    replay_bars = resample_bars(bars, timeframe)
    min_rows = min(len(frame) for frame in replay_bars.values())
    effective_max_ticks = min(max_ticks, max(0, min_rows - lookback)) if max_ticks else None
    if effective_max_ticks is not None and effective_max_ticks <= 0:
        raise ValueError(
            f"{timeframe} has too few rows after resample: min_rows={min_rows}, "
            f"lookback={lookback}"
        )

    engine = ReplayEngine(
        bars_by_symbol=replay_bars,
        initial_cash=100_000,
        slippage_bps=5,
        universe=list(replay_bars),
        timeframe=timeframe,
        max_entries_per_hour=max_entries_per_hour,
        brain_dir=str(seed_dir),
        lookback=lookback,
    )

    started = time.time()
    result = await engine.run(max_ticks=effective_max_ticks)
    elapsed_s = time.time() - started
    new_trades = read_new_trade_rows(seed_dir, seed_count)
    trade_count = len(new_trades) or len(result.trades)
    total_pnl = float(result.total_pnl)
    expectancy = total_pnl / trade_count if trade_count else 0.0

    metrics = {
        "label": label,
        "timeframe": timeframe,
        "symbols": list(replay_bars),
        "rows_per_symbol_min": min_rows,
        "lookback": lookback,
        "requested_max_ticks": max_ticks,
        "effective_max_ticks": effective_max_ticks,
        "ticks": int(result.ticks),
        "orders": len(result.orders),
        "broker_trades": len(result.trades),
        "brain_trades": len(new_trades),
        "trade_count_source": "brain_history" if new_trades else "broker_log",
        "total_pnl_broker": round(total_pnl, 4),
        "expectancy_per_trade": round(expectancy, 4),
        "win_rate_broker": round(float(result.win_rate), 4),
        "max_drawdown": round(float(result.max_drawdown), 6),
        "sharpe": round(float(result.sharpe), 4),
        "final_equity": round(float(result.equity_curve[-1]), 4) if result.equity_curve else None,
        "regime_distribution": dict(Counter(result.regime_history)),
        "exit_summary": summarize_exit_mix(new_trades),
        "elapsed_s": round(elapsed_s, 3),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"metrics_{label}.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True)
    )
    return metrics


def build_comparison(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not metrics:
        raise ValueError("no metrics supplied")
    baseline = next((item for item in metrics if item["timeframe"] == "1Min"), metrics[0])
    baseline_expectancy = float(baseline["expectancy_per_trade"])
    baseline_drawdown = float(baseline["max_drawdown"])

    variants: list[dict[str, Any]] = []
    for item in metrics:
        trade_count = int(item["brain_trades"] or item["broker_trades"])
        delta_expectancy = float(item["expectancy_per_trade"]) - baseline_expectancy
        drawdown_delta = float(item["max_drawdown"]) - baseline_drawdown
        sufficient_sample = int(item["ticks"]) >= 50 and trade_count >= 3
        passes_gate = (
            item["timeframe"] != "1Min"
            and sufficient_sample
            and delta_expectancy >= 0.50
            and drawdown_delta <= 0.005
        )
        variants.append({
            **item,
            "trades": trade_count,
            "delta_expectancy_vs_1min": round(delta_expectancy, 4),
            "drawdown_delta_vs_1min": round(drawdown_delta, 6),
            "sufficient_sample": sufficient_sample,
            "passes_shadow_gate": passes_gate,
        })

    candidates = [item for item in variants if item["passes_shadow_gate"]]
    return {
        "scope": "offline_timeframe_scout_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "baseline_timeframe": "1Min",
        "criteria": {
            "min_ticks": 50,
            "min_trades": 3,
            "min_expectancy_lift_per_trade": 0.50,
            "max_drawdown_absolute_worsening": 0.005,
            "promotion_requires_fresh_full_replay": True,
        },
        "variants": variants,
        "recommendation": (
            "shadow_candidate_needs_full_replay"
            if candidates
            else "do_not_promote_from_scout"
        ),
    }


def write_outputs(summary: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary_timeframe_scout.json"
    csv_path = out_dir / "timeframe_scout_results.csv"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

    fields = [
        "timeframe",
        "ticks",
        "trades",
        "orders",
        "total_pnl_broker",
        "expectancy_per_trade",
        "delta_expectancy_vs_1min",
        "win_rate_broker",
        "max_drawdown",
        "drawdown_delta_vs_1min",
        "sharpe",
        "sufficient_sample",
        "passes_shadow_gate",
    ]
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary["variants"])
    return {"summary": str(summary_path), "results": str(csv_path)}


async def amain(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--bar-file", default="bars.pkl")
    parser.add_argument("--seed-dir", type=Path, default=default_seed_dir())
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--timeframes", default="1Min,5Min")
    parser.add_argument("--bar-limit", type=int, default=900)
    parser.add_argument("--max-ticks", type=int, default=80)
    parser.add_argument("--lookback", type=int, default=90)
    parser.add_argument("--max-entries-per-hour", type=int, default=20)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    configure_replay_logging(verbose=args.verbose)
    symbols = parse_symbols(args.symbols)
    timeframes = parse_timeframes(args.timeframes)
    base_bars = select_and_limit_bars(
        load_cached_bars(args.cache_dir, args.bar_file),
        symbols=symbols,
        bar_limit=args.bar_limit,
    )

    metrics = []
    for timeframe in timeframes:
        metrics.append(
            await run_timeframe_variant(
                timeframe=timeframe,
                bars=base_bars,
                seed_source=args.seed_dir,
                out_dir=args.out_dir,
                max_ticks=args.max_ticks,
                lookback=args.lookback,
                max_entries_per_hour=args.max_entries_per_hour,
            )
        )
    outputs = write_outputs(build_comparison(metrics), args.out_dir)
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(amain(argv))


if __name__ == "__main__":
    raise SystemExit(main())
