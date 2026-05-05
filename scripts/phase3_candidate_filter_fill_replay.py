"""Phase 3 candidate-filter fill-path replay.

Offline research tool: join persisted closed trades to cached minute bars and
recompute fill-path metrics for the candidate filters surfaced by Phase 3.
This is not a replacement-trade simulator and it does not change live behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.phase3_trade_attribution import is_reconciliation_artifact

DEFAULT_TRADE_HISTORY = ROOT / "organism_brain" / "trade_history.csv"
DEFAULT_CACHE_DIR = ROOT / "artifacts" / "backtest_rc_1_5"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase3_candidate_filter_fill_replay"
WINDOWS: tuple[int, ...] = (200, 100, 50, 25)
UNKNOWN = "unknown"


@dataclass(frozen=True)
class FillReplayConfig:
    max_edge_gap_minutes: float = 2.0
    price_tolerance_bps: float = 5.0
    min_abs_price_tolerance: float = 0.02
    min_all_matched_trades: int = 20
    min_recent_matched_trades: int = 10
    min_match_rate: float = 0.50
    min_matched_loss_for_shadow: float = 10.0


@dataclass(frozen=True)
class FillTradeRecord:
    row_number: int
    symbol: str
    direction: float
    entry_price: float
    exit_price: float
    shares: float
    pnl: float
    confidence: float
    entry_source: str
    regime_at_entry: str
    exit_reason: str
    entry_at: pd.Timestamp
    closed_at: pd.Timestamp
    time_in_trade_seconds: float
    bars_held_at_exit: float


Predicate = Callable[[FillTradeRecord], bool]


@dataclass(frozen=True)
class FilterScenario:
    name: str
    description: str
    predicate: Predicate
    baseline: bool = False


@dataclass(frozen=True)
class FillPathResult:
    row_number: int
    symbol: str
    closed_at: str
    entry_at: str
    confidence: float
    entry_source: str
    regime_at_entry: str
    exit_reason: str
    direction: float
    shares: float
    reported_pnl: float
    price_path_pnl: float
    fill_pnl_error: float
    mfe_total: float
    mae_total: float
    giveback_total: float
    capture_ratio: float
    hold_minutes: float
    bars_in_window: int
    entry_price_seen: bool
    exit_price_seen: bool
    bar_start: str
    bar_end: str
    bar_source_count: int


def _round(value: float, places: int = 4) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, places)


def _finite_float(raw: Any, default: float = math.nan) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _label(raw: Any, *, blank: str = UNKNOWN) -> str:
    if raw is None:
        return blank
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return blank
    return text


def _parse_timestamp(raw: Any) -> pd.Timestamp | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() == "nan":
        return None
    compact = text.replace(".", "", 1).replace("-", "", 1)
    if compact.isdigit() and ("T" not in text and ":" not in text):
        return None
    ts = pd.to_datetime(text, utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def _direction(raw: Any) -> float:
    text = str(raw).strip().lower()
    if text in {"short", "sell", "-1"}:
        return -1.0
    value = _finite_float(raw, default=1.0)
    return -1.0 if value < 0 else 1.0


def _first_timestamp(row: dict[str, Any], fields: tuple[str, ...]) -> pd.Timestamp | None:
    for field in fields:
        ts = _parse_timestamp(row.get(field))
        if ts is not None:
            return ts
    return None


def normalise_fill_trade(
    row: dict[str, Any],
    row_number: int,
) -> tuple[FillTradeRecord | None, str | None]:
    if is_reconciliation_artifact(row):
        return None, "reconciliation_artifact"

    symbol = _label(row.get("symbol"))
    entry_price = _finite_float(row.get("entry_price"))
    exit_price = _finite_float(row.get("exit_price"))
    shares = _finite_float(row.get("shares"))
    pnl = _finite_float(row.get("pnl"))
    confidence = _finite_float(row.get("confidence"), default=0.0)
    hold_seconds = _finite_float(row.get("time_in_trade_seconds"), default=math.nan)
    bars_held = _finite_float(row.get("bars_held_at_exit"), default=0.0)
    if (
        symbol == UNKNOWN
        or not math.isfinite(entry_price)
        or not math.isfinite(exit_price)
        or not math.isfinite(shares)
        or shares <= 0
        or not math.isfinite(pnl)
    ):
        return None, "missing_trade_numeric_fields"

    closed_at = _first_timestamp(
        row,
        ("closed_at", "exit_at", "exit_time", "exit_timestamp", "exit_bar"),
    )
    if closed_at is None:
        return None, "missing_exit_timestamp"

    entry_at = _first_timestamp(
        row,
        ("entry_at", "entry_time", "entry_timestamp", "opened_at", "entry_bar"),
    )
    if entry_at is None and math.isfinite(hold_seconds) and hold_seconds > 0:
        entry_at = closed_at - pd.Timedelta(seconds=hold_seconds)
    if entry_at is None:
        return None, "missing_entry_timestamp"
    if entry_at > closed_at:
        return None, "entry_after_exit"

    return (
        FillTradeRecord(
            row_number=row_number,
            symbol=symbol.upper(),
            direction=_direction(row.get("direction")),
            entry_price=entry_price,
            exit_price=exit_price,
            shares=shares,
            pnl=pnl,
            confidence=confidence,
            entry_source=_label(row.get("entry_source")),
            regime_at_entry=_label(row.get("regime_at_entry")),
            exit_reason=_label(row.get("exit_reason")),
            entry_at=entry_at,
            closed_at=closed_at,
            time_in_trade_seconds=hold_seconds if math.isfinite(hold_seconds) else 0.0,
            bars_held_at_exit=bars_held,
        ),
        None,
    )


def load_fill_trades(path: Path) -> tuple[list[FillTradeRecord], dict[str, Any]]:
    with path.open(newline="") as fh:
        rows = [dict(row) for row in csv.DictReader(fh)]

    records: list[FillTradeRecord] = []
    skipped = Counter()
    for index, row in enumerate(rows, start=2):
        record, reason = normalise_fill_trade(row, index)
        if record is None:
            skipped[reason or "invalid"] += 1
            continue
        records.append(record)

    records.sort(key=lambda record: (record.closed_at, record.row_number))
    return records, {
        "source_csv": str(path),
        "total_csv_rows": len(rows),
        "valid_fill_rows": len(records),
        "strategy_rows_with_fill_timestamps": len(records),
        "skipped_rows": dict(skipped),
    }


def discover_bar_files(cache_dir: Path, bar_files: list[str] | None) -> list[Path]:
    if bar_files:
        paths = [
            Path(name) if Path(name).is_absolute() else cache_dir / name
            for name in bar_files
        ]
    else:
        paths = sorted(cache_dir.glob("bars*.pkl"))
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"cached bar files missing: {missing}")
    if not paths:
        raise FileNotFoundError(f"no bars*.pkl files found under {cache_dir}")
    return paths


def _normalise_bar_frame(
    frame: pd.DataFrame,
    *,
    source_file: str,
    source_priority: int,
) -> pd.DataFrame | None:
    required = {"timestamp", "open", "high", "low", "close"}
    if frame is None or not required.issubset(frame.columns):
        return None
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
    for column in ("open", "high", "low", "close"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna(subset=["timestamp", "open", "high", "low", "close"])
    if out.empty:
        return None
    out["bar_source"] = source_file
    out["source_priority"] = source_priority
    return out[
        [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "bar_source",
            "source_priority",
        ]
    ]


def load_cached_bars(
    cache_dir: Path,
    *,
    bar_files: list[str] | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    frames_by_symbol: dict[str, list[pd.DataFrame]] = defaultdict(list)
    paths = discover_bar_files(cache_dir, bar_files)
    for priority, path in enumerate(paths):
        with path.open("rb") as fh:
            payload = pickle.load(fh)
        if not isinstance(payload, dict):
            raise ValueError(f"cached bar file is not a symbol dictionary: {path}")
        for raw_symbol, raw_frame in payload.items():
            frame = _normalise_bar_frame(
                raw_frame,
                source_file=path.name,
                source_priority=priority,
            )
            if frame is not None:
                frames_by_symbol[str(raw_symbol).upper()].append(frame)

    bars: dict[str, pd.DataFrame] = {}
    coverage: dict[str, dict[str, Any]] = {}
    for symbol, frames in frames_by_symbol.items():
        combined = pd.concat(frames, ignore_index=True)
        combined = combined.sort_values(["timestamp", "source_priority"])
        combined = combined.drop_duplicates(subset=["timestamp"], keep="first")
        combined = combined.sort_values("timestamp").reset_index(drop=True)
        if combined.empty:
            continue
        bars[symbol] = combined
        coverage[symbol] = {
            "rows": int(len(combined)),
            "start": pd.Timestamp(combined["timestamp"].iloc[0]).isoformat(),
            "end": pd.Timestamp(combined["timestamp"].iloc[-1]).isoformat(),
            "sources": sorted(set(str(v) for v in combined["bar_source"])),
        }

    if not bars:
        raise ValueError("no usable bars after normalization")
    return bars, {
        "cache_dir": str(cache_dir),
        "bar_files": [str(path) for path in paths],
        "symbols": len(bars),
        "coverage": coverage,
    }


def default_scenarios() -> list[FilterScenario]:
    return [
        FilterScenario(
            name="baseline_all_strategy",
            description="All strategy trades with sufficient cached-bar coverage.",
            predicate=lambda record: True,
            baseline=True,
        ),
        FilterScenario(
            name="candidate_conf_45_55",
            description="Confidence band [0.45,0.55).",
            predicate=lambda record: 0.45 <= record.confidence < 0.55,
        ),
        FilterScenario(
            name="candidate_alpha_breakout_chop",
            description="alpha+breakout entries when regime_at_entry is chop.",
            predicate=lambda record: (
                record.entry_source == "alpha+breakout"
                and record.regime_at_entry == "chop"
            ),
        ),
    ]


def _window_records(
    records: list[FillTradeRecord],
    window: int | None,
) -> list[FillTradeRecord]:
    if window is None:
        return records
    return records[-min(window, len(records)) :]


def _price_tolerance(price: float, config: FillReplayConfig) -> float:
    return max(abs(price) * config.price_tolerance_bps / 10_000, config.min_abs_price_tolerance)


def _price_seen(frame: pd.DataFrame, price: float, config: FillReplayConfig) -> bool:
    if frame.empty:
        return False
    tolerance = _price_tolerance(price, config)
    return bool(
        ((frame["low"] - tolerance <= price) & (price <= frame["high"] + tolerance)).any()
    )


def _edge_frame(
    frame: pd.DataFrame,
    ts: pd.Timestamp,
    config: FillReplayConfig,
) -> pd.DataFrame:
    gap = pd.Timedelta(minutes=config.max_edge_gap_minutes)
    edge = frame[(frame["timestamp"] >= ts - gap) & (frame["timestamp"] <= ts + gap)]
    if not edge.empty:
        return edge
    distances = (frame["timestamp"] - ts).abs()
    nearest_idx = distances.idxmin()
    return frame.loc[[nearest_idx]]


def _bar_window(
    record: FillTradeRecord,
    bars: dict[str, pd.DataFrame],
    config: FillReplayConfig,
) -> tuple[pd.DataFrame | None, str | None]:
    frame = bars.get(record.symbol)
    if frame is None:
        return None, "symbol_missing_from_bar_cache"
    start = pd.Timestamp(frame["timestamp"].iloc[0])
    end = pd.Timestamp(frame["timestamp"].iloc[-1])
    if record.closed_at < start or record.entry_at > end:
        return None, "outside_bar_cache_coverage"

    gap = pd.Timedelta(minutes=config.max_edge_gap_minutes)
    window = frame[
        (frame["timestamp"] >= record.entry_at - gap)
        & (frame["timestamp"] <= record.closed_at + gap)
    ].copy()
    if window.empty:
        return None, "sparse_bar_gap_in_trade_window"
    return window.reset_index(drop=True), None


def evaluate_trade_path(
    record: FillTradeRecord,
    bars: dict[str, pd.DataFrame],
    config: FillReplayConfig,
) -> tuple[FillPathResult | None, str | None]:
    window, reason = _bar_window(record, bars, config)
    if window is None:
        return None, reason

    direction = record.direction
    signed_high = direction * (window["high"].astype(float) - record.entry_price)
    signed_low = direction * (window["low"].astype(float) - record.entry_price)
    all_signed = pd.concat([signed_high, signed_low], ignore_index=True)
    mfe_per_share = float(all_signed.max())
    mae_per_share = float(all_signed.min())
    price_pnl_per_share = direction * (record.exit_price - record.entry_price)
    price_path_pnl = price_pnl_per_share * record.shares
    mfe_total = mfe_per_share * record.shares
    mae_total = mae_per_share * record.shares
    giveback_total = mfe_total - price_path_pnl
    capture_ratio = price_path_pnl / mfe_total if mfe_total > 0 else 0.0

    entry_edge = _edge_frame(window, record.entry_at, config)
    exit_edge = _edge_frame(window, record.closed_at, config)
    sources = set(str(value) for value in window["bar_source"])
    return (
        FillPathResult(
            row_number=record.row_number,
            symbol=record.symbol,
            closed_at=record.closed_at.isoformat(),
            entry_at=record.entry_at.isoformat(),
            confidence=_round(record.confidence),
            entry_source=record.entry_source,
            regime_at_entry=record.regime_at_entry,
            exit_reason=record.exit_reason,
            direction=record.direction,
            shares=_round(record.shares),
            reported_pnl=_round(record.pnl),
            price_path_pnl=_round(price_path_pnl),
            fill_pnl_error=_round(price_path_pnl - record.pnl),
            mfe_total=_round(mfe_total),
            mae_total=_round(mae_total),
            giveback_total=_round(giveback_total),
            capture_ratio=_round(capture_ratio),
            hold_minutes=_round(record.time_in_trade_seconds / 60.0),
            bars_in_window=int(len(window)),
            entry_price_seen=_price_seen(entry_edge, record.entry_price, config),
            exit_price_seen=_price_seen(exit_edge, record.exit_price, config),
            bar_start=pd.Timestamp(window["timestamp"].iloc[0]).isoformat(),
            bar_end=pd.Timestamp(window["timestamp"].iloc[-1]).isoformat(),
            bar_source_count=len(sources),
        ),
        None,
    )


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _summarise_paths(
    *,
    selected: list[FillTradeRecord],
    matched: list[FillPathResult],
    unmatched_reasons: Counter,
    config: FillReplayConfig,
) -> dict[str, Any]:
    input_pnl = sum(record.pnl for record in selected)
    matched_reported_pnl = sum(result.reported_pnl for result in matched)
    matched_price_pnl = sum(result.price_path_pnl for result in matched)
    wins = [result.reported_pnl for result in matched if result.reported_pnl > 0]
    losses = [result.reported_pnl for result in matched if result.reported_pnl < 0]
    gross_profit = sum(wins)
    gross_loss_abs = abs(sum(losses))
    profit_factor = gross_profit / gross_loss_abs if gross_loss_abs > 0 else 0.0
    matched_count = len(matched)
    input_count = len(selected)
    return {
        "input_trades": input_count,
        "input_reported_pnl": _round(input_pnl),
        "matched_trades": matched_count,
        "unmatched_trades": input_count - matched_count,
        "match_rate": _round(matched_count / input_count if input_count else 0.0),
        "unmatched_reasons": dict(unmatched_reasons),
        "matched_reported_pnl": _round(matched_reported_pnl),
        "matched_price_path_pnl": _round(matched_price_pnl),
        "matched_fill_pnl_error": _round(matched_price_pnl - matched_reported_pnl),
        "matched_win_rate": _round(len(wins) / matched_count if matched_count else 0.0),
        "matched_profit_factor": _round(profit_factor),
        "avg_mfe_total": _round(_mean([result.mfe_total for result in matched])),
        "avg_mae_total": _round(_mean([result.mae_total for result in matched])),
        "avg_giveback_total": _round(_mean([result.giveback_total for result in matched])),
        "avg_capture_ratio": _round(_mean([result.capture_ratio for result in matched])),
        "avg_hold_minutes": _round(_mean([result.hold_minutes for result in matched])),
        "entry_price_seen_rate": _round(
            sum(1 for result in matched if result.entry_price_seen) / matched_count
            if matched_count
            else 0.0
        ),
        "exit_price_seen_rate": _round(
            sum(1 for result in matched if result.exit_price_seen) / matched_count
            if matched_count
            else 0.0
        ),
        "price_tolerance_bps": config.price_tolerance_bps,
    }


def _recommendation(
    *,
    scenario: FilterScenario,
    window: str,
    summary: dict[str, Any],
    config: FillReplayConfig,
) -> str:
    if scenario.baseline:
        return "baseline_coverage_only"
    min_required = (
        config.min_all_matched_trades
        if window == "all"
        else config.min_recent_matched_trades
    )
    if int(summary["matched_trades"]) < min_required:
        return "insufficient_fill_sample_need_shadow_telemetry"
    if float(summary["match_rate"]) < config.min_match_rate:
        return "coverage_too_sparse_for_promotion"
    if float(summary["matched_reported_pnl"]) >= 0:
        return "do_not_promote_positive_or_flat_matched_slice"
    if abs(float(summary["matched_reported_pnl"])) < config.min_matched_loss_for_shadow:
        return "weak_negative_fill_slice_needs_more_evidence"
    return "shadow_candidate_from_fill_path_drag"


def evaluate_scenario(
    records: list[FillTradeRecord],
    bars: dict[str, pd.DataFrame],
    scenario: FilterScenario,
    *,
    window: str,
    config: FillReplayConfig,
) -> tuple[dict[str, Any], list[FillPathResult]]:
    selected = [record for record in records if scenario.predicate(record)]
    matched: list[FillPathResult] = []
    unmatched_reasons: Counter = Counter()
    for record in selected:
        result, reason = evaluate_trade_path(record, bars, config)
        if result is None:
            unmatched_reasons[reason or "unmatched"] += 1
            continue
        matched.append(result)

    path_summary = _summarise_paths(
        selected=selected,
        matched=matched,
        unmatched_reasons=unmatched_reasons,
        config=config,
    )
    result = {
        "window": window,
        "scenario": scenario.name,
        "description": scenario.description,
        **path_summary,
    }
    result["recommendation"] = _recommendation(
        scenario=scenario,
        window=window,
        summary=result,
        config=config,
    )
    return result, matched


def run_fill_replay(
    records: list[FillTradeRecord],
    trade_metadata: dict[str, Any],
    bars: dict[str, pd.DataFrame],
    bar_metadata: dict[str, Any],
    *,
    config: FillReplayConfig,
    scenarios: list[FilterScenario] | None = None,
) -> dict[str, Any]:
    selected_scenarios = scenarios or default_scenarios()
    windows: dict[str, list[FillTradeRecord]] = {"all": records}
    for window in WINDOWS:
        windows[f"last_{window}"] = _window_records(records, window)

    all_results: dict[str, list[dict[str, Any]]] = {}
    baseline_all_matches: list[FillPathResult] = []
    for window_name, window_records in windows.items():
        window_results: list[dict[str, Any]] = []
        for scenario in selected_scenarios:
            scenario_result, matched = evaluate_scenario(
                window_records,
                bars,
                scenario,
                window=window_name,
                config=config,
            )
            window_results.append(scenario_result)
            if window_name == "all" and scenario.baseline:
                baseline_all_matches = matched
        all_results[window_name] = window_results

    return {
        "scope": "offline_fill_path_replay_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "limitations": [
            "Closed trades do not preserve every rejected candidate, so skipped-trade replacement behavior is not simulated.",
            "entry_bar/exit_bar are numeric counters in the current brain; timestamps are reconstructed from closed_at minus time_in_trade_seconds.",
            "Cached bar coverage is historical and sparse relative to the full live brain, so low match rates block promotion.",
        ],
        "config": {
            "max_edge_gap_minutes": config.max_edge_gap_minutes,
            "price_tolerance_bps": config.price_tolerance_bps,
            "min_abs_price_tolerance": config.min_abs_price_tolerance,
            "min_all_matched_trades": config.min_all_matched_trades,
            "min_recent_matched_trades": config.min_recent_matched_trades,
            "min_match_rate": config.min_match_rate,
            "min_matched_loss_for_shadow": config.min_matched_loss_for_shadow,
        },
        "trade_metadata": trade_metadata,
        "bar_metadata": bar_metadata,
        "windows": all_results,
        "matched_trades_all": [result.__dict__ for result in baseline_all_matches],
    }


def write_outputs(summary: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary_candidate_filter_fill_replay.json"
    results_path = out_dir / "candidate_filter_fill_results.csv"
    matched_path = out_dir / "matched_trades_candidate_filter_fill_replay.csv"

    with summary_path.open("w") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
        fh.write("\n")

    result_fields = [
        "window",
        "scenario",
        "recommendation",
        "input_trades",
        "input_reported_pnl",
        "matched_trades",
        "unmatched_trades",
        "match_rate",
        "matched_reported_pnl",
        "matched_price_path_pnl",
        "matched_fill_pnl_error",
        "matched_win_rate",
        "matched_profit_factor",
        "avg_mfe_total",
        "avg_mae_total",
        "avg_giveback_total",
        "avg_capture_ratio",
        "avg_hold_minutes",
        "entry_price_seen_rate",
        "exit_price_seen_rate",
        "unmatched_reasons",
        "description",
    ]
    rows = [
        row
        for window_rows in summary["windows"].values()
        for row in window_rows
    ]
    with results_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=result_fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["unmatched_reasons"] = json.dumps(
                out.get("unmatched_reasons", {}),
                sort_keys=True,
            )
            writer.writerow(out)

    matched_fields = [
        "row_number",
        "symbol",
        "entry_at",
        "closed_at",
        "confidence",
        "entry_source",
        "regime_at_entry",
        "exit_reason",
        "direction",
        "shares",
        "reported_pnl",
        "price_path_pnl",
        "fill_pnl_error",
        "mfe_total",
        "mae_total",
        "giveback_total",
        "capture_ratio",
        "hold_minutes",
        "bars_in_window",
        "entry_price_seen",
        "exit_price_seen",
        "bar_start",
        "bar_end",
        "bar_source_count",
    ]
    with matched_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=matched_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary.get("matched_trades_all", []))

    return {
        "summary": str(summary_path),
        "results": str(results_path),
        "matched_trades": str(matched_path),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-history", type=Path, default=DEFAULT_TRADE_HISTORY)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--bar-file",
        action="append",
        dest="bar_files",
        help="Specific cached bar pickle under --cache-dir; repeatable. Defaults to bars*.pkl.",
    )
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-edge-gap-minutes", type=float, default=2.0)
    parser.add_argument("--price-tolerance-bps", type=float, default=5.0)
    parser.add_argument("--min-match-rate", type=float, default=0.50)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = FillReplayConfig(
        max_edge_gap_minutes=args.max_edge_gap_minutes,
        price_tolerance_bps=args.price_tolerance_bps,
        min_match_rate=args.min_match_rate,
    )
    records, trade_metadata = load_fill_trades(args.trade_history)
    bars, bar_metadata = load_cached_bars(args.cache_dir, bar_files=args.bar_files)
    summary = run_fill_replay(
        records,
        trade_metadata,
        bars,
        bar_metadata,
        config=config,
    )
    outputs = write_outputs(summary, args.out_dir)
    print(json.dumps(outputs, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
