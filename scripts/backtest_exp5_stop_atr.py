"""Exp 5 — chop stop ATR re-tune replay experiment.

Runs configurations of ``AdaptiveExitEngine.REGIME_STOP_ATR["chop"]``
against the same cached Alpaca bars and brain seed. This is a Phase 3
research tool only: it mutates a copied replay brain under ``artifacts/``
and must not be used as proof of live edge by itself. Use the comparison
summary for relative deltas, then require shadow validation before any live
behavior change.
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
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = ROOT / "artifacts" / "backtest_rc_1_5"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "backtest_exp5"
DEFAULT_SEED_CANDIDATES = (
    ROOT / "artifacts" / "deploy_preflight_rc_1_5_curated"
    / "organism_brain_backup_pre_rc_1_5_curated_20260425_005638",
    ROOT / "artifacts" / "deploy_preflight_eb90fa3"
    / "organism_brain_backup_pre_eb90fa3_20260425",
)


def default_seed_dir() -> Path:
    for candidate in DEFAULT_SEED_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return DEFAULT_SEED_CANDIDATES[0]


def parse_variants(raw: str) -> list[float]:
    variants: list[float] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        value = float(part)
        if value <= 0:
            raise ValueError("chop stop ATR variants must be positive")
        variants.append(value)
    if not variants:
        raise ValueError("at least one chop stop ATR variant is required")
    return variants


def parse_symbols(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    symbols = [part.strip().upper() for part in raw.split(",") if part.strip()]
    if not symbols:
        raise ValueError("symbol filter cannot be empty")
    return symbols


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


def load_cached_bars(cache_dir: Path) -> dict[str, Any]:
    bars_path = cache_dir / "bars.pkl"
    if not bars_path.is_file():
        raise FileNotFoundError(
            f"cached bars missing: {bars_path}. Run "
            "scripts/backtest_rc_1_5_comparison.py first."
        )
    with bars_path.open("rb") as fh:
        bars = pickle.load(fh)
    if not isinstance(bars, dict) or not bars:
        raise ValueError(f"cached bars are empty or invalid: {bars_path}")
    return bars


def select_cached_bars(
    bars: dict[str, Any],
    *,
    symbols: list[str] | None = None,
    bar_limit: int | None = None,
) -> dict[str, Any]:
    selected_symbols = symbols or list(bars.keys())
    missing = [symbol for symbol in selected_symbols if symbol not in bars]
    if missing:
        raise ValueError(f"symbols missing from cached bars: {missing}")
    selected = {symbol: bars[symbol] for symbol in selected_symbols}
    if bar_limit is None:
        return selected
    if bar_limit <= 0:
        raise ValueError("bar limit must be positive")
    limited: dict[str, Any] = {}
    for symbol, frame in selected.items():
        limited[symbol] = frame.tail(bar_limit) if hasattr(frame, "tail") else frame
    return limited


def read_new_trade_rows(brain_dir: Path, seed_count: int) -> list[dict[str, str]]:
    path = brain_dir / "trade_history.csv"
    if not path.is_file():
        return []
    with path.open() as fh:
        rows = list(csv.DictReader(fh))
    return rows[seed_count:] if len(rows) > seed_count else []


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


def summarize_exit_mix(exit_mix: dict[str, int]) -> dict[str, Any]:
    buckets: Counter[str] = Counter()
    for reason, count in exit_mix.items():
        buckets[exit_bucket(reason)] += int(count)
    total = sum(buckets.values())
    shares = {
        bucket: (count / total if total else 0.0)
        for bucket, count in sorted(buckets.items())
    }
    return {
        "total": total,
        "buckets": dict(buckets),
        "shares": shares,
    }


def _variant_trade_count(metrics: dict[str, Any]) -> int:
    return int(
        metrics.get("trades_in_brain_history_during_replay")
        or metrics.get("trades_in_broker_log")
        or 0
    )


def _variant_expectancy(metrics: dict[str, Any]) -> float:
    trades = _variant_trade_count(metrics)
    if trades <= 0:
        return 0.0
    return float(metrics.get("total_pnl_broker", 0.0)) / trades


def build_comparison(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not metrics:
        raise ValueError("no metrics to compare")
    baseline = metrics[0]
    base_expectancy = _variant_expectancy(baseline)
    base_exit_summary = summarize_exit_mix(baseline.get("exit_reason_mix", {}))
    base_pyramid_share = base_exit_summary["shares"].get("pyramid_cut", 0.0)
    base_drawdown = float(baseline.get("max_drawdown", 0.0))

    variants: list[dict[str, Any]] = []
    for item in metrics:
        expectancy = _variant_expectancy(item)
        exit_summary = summarize_exit_mix(item.get("exit_reason_mix", {}))
        pyramid_share = exit_summary["shares"].get("pyramid_cut", 0.0)
        drawdown = float(item.get("max_drawdown", 0.0))
        delta_expectancy = expectancy - base_expectancy
        pyramid_cap = base_pyramid_share * 1.25 if base_pyramid_share else 1.0
        passes_gate = (
            item is not baseline
            and delta_expectancy >= 0.50
            and pyramid_share <= pyramid_cap
            and drawdown <= base_drawdown + 0.005
        )
        variants.append({
            "label": item.get("label"),
            "chop_stop_atr": item.get("chop_stop_atr"),
            "trades": _variant_trade_count(item),
            "brain_trades": int(
                item.get("trades_in_brain_history_during_replay") or 0
            ),
            "broker_sells": int(item.get("trades_in_broker_log") or 0),
            "trade_count_source": (
                "brain_history"
                if item.get("trades_in_brain_history_during_replay")
                else "broker_log"
            ),
            "total_pnl_broker": float(item.get("total_pnl_broker", 0.0)),
            "expectancy_per_trade": expectancy,
            "delta_expectancy_per_trade": delta_expectancy,
            "win_rate_broker": float(item.get("win_rate_broker", 0.0)),
            "max_drawdown": drawdown,
            "pyramid_cut_share": pyramid_share,
            "exit_summary": exit_summary,
            "passes_exp5_gate": passes_gate,
        })

    candidates = [v for v in variants[1:] if v["passes_exp5_gate"]]
    best = max(variants[1:] or variants, key=lambda v: v["delta_expectancy_per_trade"])
    return {
        "baseline_label": baseline.get("label"),
        "criteria": {
            "min_expectancy_lift_per_trade": 0.50,
            "max_pyramid_cut_relative_increase": 0.25,
            "max_drawdown_absolute_worsening": 0.005,
            "replay_scope": "relative_delta_only",
        },
        "variants": variants,
        "recommendation": (
            "shadow_candidate"
            if candidates
            else "do_not_promote_from_replay"
        ),
        "best_variant_by_expectancy_delta": best,
    }


async def run_one(
    chop_stop_atr: float,
    label: str,
    *,
    cache_dir: Path,
    seed_source: Path,
    out_dir: Path,
    max_ticks: int | None = None,
    symbols: list[str] | None = None,
    bar_limit: int | None = None,
) -> dict:
    """Monkeypatch chop stop ATR, run replay, save metrics."""
    # Patch the table BEFORE importing replay/live engine
    from backend.organism import adaptive_exits
    original = adaptive_exits.AdaptiveExitEngine.REGIME_STOP_ATR.copy()
    try:
        adaptive_exits.AdaptiveExitEngine.REGIME_STOP_ATR = {
            **original,
            "chop": chop_stop_atr,
        }
        print(
            f"[exp5/{label}] Patched chop stop ATR: "
            f"{original['chop']} -> {chop_stop_atr}"
        )

        out_dir.mkdir(parents=True, exist_ok=True)
        seed_dir, seed_count = prepare_seed_dir(seed_source, out_dir, label)
        bars = select_cached_bars(
            load_cached_bars(cache_dir),
            symbols=symbols,
            bar_limit=bar_limit,
        )
        sample_rows = next(iter(bars.values()))
        try:
            row_count = len(sample_rows)
        except TypeError:
            row_count = None
        print(
            f"[exp5/{label}] Loaded {len(bars)} symbols from cached bars"
            + (f" ({row_count} rows on first symbol)" if row_count else "")
        )

        from backend.organism.replay_simulator import ReplayEngine

        engine = ReplayEngine(
            bars_by_symbol=bars,
            initial_cash=100_000,
            slippage_bps=5,
            universe=list(bars.keys()),
            timeframe="1Min",
            max_entries_per_hour=20,
            brain_dir=str(seed_dir),
        )

        t0 = time.time()
        result = await engine.run(max_ticks=max_ticks)
        elapsed = time.time() - t0

        print(
            f"[exp5/{label}] complete in {elapsed:.1f}s, "
            f"{result.ticks} ticks, {len(result.trades)} broker sells, "
            f"${result.total_pnl:.2f} pnl"
        )
        print(result.summary())

        new_during_replay = read_new_trade_rows(seed_dir, seed_count)
        exit_mix: Counter[str] = Counter(
            tr.get("exit_reason", "unknown") or "unknown"
            for tr in new_during_replay
        )

        metrics = {
            "label": label,
            "chop_stop_atr": chop_stop_atr,
            "ticks": result.ticks,
            "symbols": list(bars.keys()),
            "bar_limit": bar_limit,
            "max_ticks": max_ticks,
            "seed_trade_count": seed_count,
            "trades_in_broker_log": len(result.trades),
            "trades_in_brain_history_during_replay": len(new_during_replay),
            "total_pnl_broker": float(result.total_pnl),
            "expectancy_per_brain_trade": (
                float(result.total_pnl) / len(new_during_replay)
                if new_during_replay else 0.0
            ),
            "win_rate_broker": float(result.win_rate),
            "max_drawdown": float(result.max_drawdown),
            "sharpe": float(result.sharpe),
            "regime_distribution": dict(Counter(result.regime_history)),
            "exit_reason_mix": dict(exit_mix),
            "exit_summary": summarize_exit_mix(dict(exit_mix)),
            "elapsed_s": elapsed,
            "final_equity": (
                float(result.equity_curve[-1]) if result.equity_curve else None
            ),
            "return_pct": (
                float((result.equity_curve[-1] / result.equity_curve[0] - 1) * 100)
                if result.equity_curve else None
            ),
        }

        out = out_dir / f"metrics_{label}.json"
        out.write_text(json.dumps(metrics, indent=2, default=str))
        print(f"[exp5/{label}] Metrics -> {out}")
        return metrics
    finally:
        adaptive_exits.AdaptiveExitEngine.REGIME_STOP_ATR = original


async def amain() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variants",
        default="2.5,3.0,3.5",
        help="Comma-separated chop_stop_atr values; first is the baseline",
    )
    parser.add_argument("--max-ticks", type=int, default=None)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--seed-dir", type=Path, default=default_seed_dir())
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--summary-out", type=Path, default=None)
    parser.add_argument(
        "--symbols",
        default=None,
        help="Optional comma-separated cached-symbol subset for scout runs",
    )
    parser.add_argument(
        "--bar-limit",
        type=int,
        default=None,
        help="Optional trailing bar count per symbol for bounded scout runs",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full replay warnings/log output instead of quiet research mode",
    )
    args = parser.parse_args()

    configure_replay_logging(verbose=args.verbose)
    variants = parse_variants(args.variants)
    symbols = parse_symbols(args.symbols)
    print(f"[exp5] cache_dir={args.cache_dir}")
    print(f"[exp5] seed_dir={args.seed_dir}")
    print(f"[exp5] out_dir={args.out_dir}")
    print(f"[exp5] symbols={symbols or 'all'}")
    print(f"[exp5] bar_limit={args.bar_limit or 'all'}")

    all_metrics = []
    for atr in variants:
        label = f"atr{atr:.1f}".replace(".", "_")
        m = await run_one(
            atr,
            label,
            cache_dir=args.cache_dir,
            seed_source=args.seed_dir,
            out_dir=args.out_dir,
            max_ticks=args.max_ticks,
            symbols=symbols,
            bar_limit=args.bar_limit,
        )
        all_metrics.append(m)

    comparison = build_comparison(all_metrics)
    summary_out = args.summary_out or (args.out_dir / "summary_exp5.json")
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(json.dumps(comparison, indent=2, default=str))
    print(f"[exp5] Comparison summary -> {summary_out}")

    # Comparison summary
    print("\n" + "=" * 70)
    print("  EXP-5 STOP ATR COMPARISON")
    print("=" * 70)
    print(f"  {'variant':<12} {'trades':>8} {'pnl':>10} {'wr':>8} "
          f"{'exp/tr':>8} {'sharpe':>8} {'maxdd':>8} {'gate':>8}")
    by_label = {v["label"]: v for v in comparison["variants"]}
    for m in all_metrics:
        v = by_label.get(m["label"], {})
        print(f"  atr={m['chop_stop_atr']:<6.1f} "
              f"{m['trades_in_brain_history_during_replay']:>8} "
              f"${m['total_pnl_broker']:>+9.2f} "
              f"{100*m['win_rate_broker']:>6.1f}% "
              f"{v.get('expectancy_per_trade', 0.0):>8.2f} "
              f"{m['sharpe']:>8.3f} "
              f"{100*m['max_drawdown']:>6.2f}% "
              f"{str(v.get('passes_exp5_gate', False)):>8}")

    print("\n  Exit reason mix:")
    for m in all_metrics:
        print(f"  atr={m['chop_stop_atr']:.1f}:")
        summary = m.get("exit_summary") or summarize_exit_mix(m["exit_reason_mix"])
        buckets = summary["buckets"]
        total = summary["total"]
        if total > 0:
            for bucket in (
                "stop_loss",
                "pyramid_cut",
                "trailing_stop",
                "max_holding",
                "failure_to_follow",
                "take_profit",
                "eod_flatten",
                "other",
            ):
                count = buckets.get(bucket, 0)
                print(f"    {bucket:<18} {count:>3} ({100*count/total:>3.0f}%)")
    print(f"\n  Recommendation: {comparison['recommendation']}")


if __name__ == "__main__":
    asyncio.run(amain())
