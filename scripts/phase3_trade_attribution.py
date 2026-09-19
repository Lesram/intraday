"""Phase 3 trade attribution analyzer.

Offline research tool: read the persisted brain trade history and identify
which confidence bands, entry sources, regimes, symbols, and exit families are
creating expectancy drag. This does not change live trading behavior.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRADE_HISTORY = ROOT / "organism_brain" / "trade_history.csv"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase3_trade_attribution"

CONFIDENCE_BUCKETS: tuple[tuple[float, float, str], ...] = (
    (0.00, 0.35, "[0.00,0.35)"),
    (0.35, 0.45, "[0.35,0.45)"),
    (0.45, 0.55, "[0.45,0.55)"),
    (0.55, 0.65, "[0.55,0.65)"),
    (0.65, 0.75, "[0.65,0.75)"),
    (0.75, math.inf, "[0.75,inf)"),
)
WINDOWS: tuple[int, ...] = (200, 100, 50, 25)
LEGACY_BLANK = "legacy_blank"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class AnalyzerConfig:
    min_trades_for_action: int = 20
    min_recent_trades_for_action: int = 10
    min_total_loss_for_action: float = 25.0
    min_recent_loss_for_action: float = 15.0
    top_n: int = 10


@dataclass(frozen=True)
class TradeRecord:
    symbol: str
    direction: str
    pnl: float
    exit_reason: str
    exit_family: str
    predicted_return: float
    actual_return: float
    confidence: float
    confidence_bucket: str
    correct_direction: bool | None
    entry_source: str
    regime_at_entry: str
    regime_at_exit: str
    mfe: float
    mae: float
    bars_held_at_exit: float
    time_in_trade_seconds: float
    closed_at: str


SegmentGetter = Callable[[TradeRecord], str]


def _finite_float(raw: Any, default: float = 0.0) -> float:
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


def _truthy(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    return str(raw).strip().lower() in {"1", "true", "yes", "y"}


def _maybe_bool(raw: Any) -> bool | None:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in {"", "nan"}:
        return None
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _round(value: float, places: int = 4) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, places)


def confidence_bucket(confidence: float) -> str:
    for low, high, label in CONFIDENCE_BUCKETS:
        if low <= confidence < high:
            return label
    if confidence < 0:
        return CONFIDENCE_BUCKETS[0][2]
    return CONFIDENCE_BUCKETS[-1][2]


def exit_family(raw: Any) -> str:
    reason = _label(raw)
    if reason.startswith("pyramid_cut_"):
        return "pyramid_cut"
    return reason


def is_reconciliation_artifact(row: dict[str, Any]) -> bool:
    if _truthy(row.get("is_reconciliation_artifact")):
        return True
    return (
        str(row.get("exit_reason", "")).strip() == "reconciliation_adjustment"
        or str(row.get("entry_source", "")).strip() == "reconciliation_orphan"
    )


def normalise_trade(row: dict[str, Any]) -> TradeRecord | None:
    pnl = _finite_float(row.get("pnl"), default=math.nan)
    if not math.isfinite(pnl):
        return None
    confidence = _finite_float(row.get("confidence"), default=0.0)
    return TradeRecord(
        symbol=_label(row.get("symbol")),
        direction=_label(row.get("direction")),
        pnl=pnl,
        exit_reason=_label(row.get("exit_reason")),
        exit_family=exit_family(row.get("exit_reason")),
        predicted_return=_finite_float(row.get("predicted_return")),
        actual_return=_finite_float(row.get("actual_return")),
        confidence=confidence,
        confidence_bucket=confidence_bucket(confidence),
        correct_direction=_maybe_bool(row.get("correct_direction")),
        entry_source=_label(row.get("entry_source"), blank=LEGACY_BLANK),
        regime_at_entry=_label(row.get("regime_at_entry"), blank=LEGACY_BLANK),
        regime_at_exit=_label(row.get("regime_at_exit"), blank=LEGACY_BLANK),
        mfe=_finite_float(row.get("mfe")),
        mae=_finite_float(row.get("mae")),
        bars_held_at_exit=_finite_float(row.get("bars_held_at_exit")),
        time_in_trade_seconds=_finite_float(row.get("time_in_trade_seconds")),
        closed_at=_label(row.get("closed_at"), blank=""),
    )


def load_strategy_trades(path: Path) -> tuple[list[TradeRecord], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [dict(row) for row in reader]

    records: list[TradeRecord] = []
    excluded = 0
    invalid = 0
    for row in rows:
        if is_reconciliation_artifact(row):
            excluded += 1
            continue
        record = normalise_trade(row)
        if record is None:
            invalid += 1
            continue
        records.append(record)

    return records, {
        "source_csv": str(path),
        "total_csv_rows": len(rows),
        "strategy_rows": len(records),
        "excluded_reconciliation_artifacts": excluded,
        "invalid_pnl_rows": invalid,
    }


def summarise(records: list[TradeRecord]) -> dict[str, Any]:
    n = len(records)
    if n == 0:
        return {
            "n_trades": 0,
            "total_pnl": 0.0,
            "mean_pnl": 0.0,
            "median_pnl": 0.0,
            "win_rate": 0.0,
            "correct_direction_rate": 0.0,
            "avg_confidence": 0.0,
            "avg_predicted_return": 0.0,
            "avg_actual_return": 0.0,
            "avg_mfe": 0.0,
            "avg_mae": 0.0,
            "avg_bars_held": 0.0,
            "avg_hold_minutes": 0.0,
            "profit_factor": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
        }

    pnls = [r.pnl for r in records]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    known_correct = [r.correct_direction for r in records if r.correct_direction is not None]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
    return {
        "n_trades": n,
        "total_pnl": _round(sum(pnls)),
        "mean_pnl": _round(statistics.fmean(pnls)),
        "median_pnl": _round(statistics.median(pnls)),
        "win_rate": _round(len(wins) / n),
        "correct_direction_rate": _round(
            sum(1 for v in known_correct if v) / len(known_correct)
            if known_correct
            else 0.0
        ),
        "avg_confidence": _round(statistics.fmean(r.confidence for r in records)),
        "avg_predicted_return": _round(statistics.fmean(r.predicted_return for r in records)),
        "avg_actual_return": _round(statistics.fmean(r.actual_return for r in records)),
        "avg_mfe": _round(statistics.fmean(r.mfe for r in records)),
        "avg_mae": _round(statistics.fmean(r.mae for r in records)),
        "avg_bars_held": _round(statistics.fmean(r.bars_held_at_exit for r in records)),
        "avg_hold_minutes": _round(
            statistics.fmean(r.time_in_trade_seconds for r in records) / 60.0
        ),
        "profit_factor": _round(profit_factor),
        "best_trade": _round(max(pnls)),
        "worst_trade": _round(min(pnls)),
    }


SEGMENTS: dict[str, SegmentGetter] = {
    "entry_source": lambda r: r.entry_source,
    "regime_at_entry": lambda r: r.regime_at_entry,
    "entry_source_x_regime": lambda r: f"{r.entry_source}|{r.regime_at_entry}",
    "confidence_bucket": lambda r: r.confidence_bucket,
    "entry_source_x_confidence": lambda r: f"{r.entry_source}|{r.confidence_bucket}",
    "exit_family": lambda r: r.exit_family,
    "symbol": lambda r: r.symbol,
    "direction": lambda r: r.direction,
}


def segment_table(records: list[TradeRecord], segment_type: str) -> list[dict[str, Any]]:
    getter = SEGMENTS[segment_type]
    grouped: dict[str, list[TradeRecord]] = defaultdict(list)
    for record in records:
        grouped[getter(record)].append(record)
    rows = [
        {"segment_type": segment_type, "value": value, **summarise(group)}
        for value, group in grouped.items()
    ]
    rows.sort(key=lambda row: (float(row["total_pnl"]), -int(row["n_trades"])))
    return rows


def _window_records(records: list[TradeRecord], window: int | None) -> list[TradeRecord]:
    if window is None:
        return records
    return records[-min(window, len(records)):]


def confidence_inversion(records: list[TradeRecord], config: AnalyzerConfig) -> dict[str, Any]:
    grouped: dict[str, list[TradeRecord]] = defaultdict(list)
    for record in records:
        grouped[record.confidence_bucket].append(record)

    bucket_rows = []
    for _, _, bucket in CONFIDENCE_BUCKETS:
        bucket_rows.append({"bucket": bucket, **summarise(grouped.get(bucket, []))})

    low_mid = [
        record
        for record in records
        if 0.35 <= record.confidence < 0.65
    ]
    high = [record for record in records if record.confidence >= 0.65]
    low_mid_stats = summarise(low_mid)
    high_stats = summarise(high)
    enough = (
        low_mid_stats["n_trades"] >= config.min_trades_for_action
        and high_stats["n_trades"] >= config.min_trades_for_action
    )
    flag = bool(
        enough
        and float(high_stats["mean_pnl"]) < float(low_mid_stats["mean_pnl"])
        and float(high_stats["total_pnl"]) < 0
    )
    return {
        "flag": flag,
        "reason": (
            "confidence>=0.65 underperforms the 0.35-0.65 reference band"
            if flag
            else "insufficient evidence or no high-confidence underperformance"
        ),
        "reference_band": "[0.35,0.65)",
        "high_band": "[0.65,inf)",
        "reference_stats": low_mid_stats,
        "high_stats": high_stats,
        "buckets": bucket_rows,
    }


def classify_candidate(
    *,
    window: str,
    segment: dict[str, Any],
    config: AnalyzerConfig,
) -> dict[str, Any] | None:
    n_trades = int(segment["n_trades"])
    total_pnl = float(segment["total_pnl"])
    mean_pnl = float(segment["mean_pnl"])
    win_rate = float(segment["win_rate"])
    recent = window != "all"
    min_trades = (
        config.min_recent_trades_for_action if recent else config.min_trades_for_action
    )
    min_loss = (
        config.min_recent_loss_for_action if recent else config.min_total_loss_for_action
    )
    if n_trades < min_trades:
        return None

    if total_pnl <= -min_loss and mean_pnl < 0 and win_rate <= 0.45:
        return {
            "window": window,
            "segment_type": segment["segment_type"],
            "value": segment["value"],
            "n_trades": n_trades,
            "total_pnl": _round(total_pnl),
            "mean_pnl": _round(mean_pnl),
            "win_rate": _round(win_rate),
            "candidate_type": "drag",
            "recommendation": "replay_or_shadow_before_live_gate_change",
        }

    if total_pnl >= min_loss and mean_pnl > 0 and win_rate >= 0.50:
        return {
            "window": window,
            "segment_type": segment["segment_type"],
            "value": segment["value"],
            "n_trades": n_trades,
            "total_pnl": _round(total_pnl),
            "mean_pnl": _round(mean_pnl),
            "win_rate": _round(win_rate),
            "candidate_type": "strength",
            "recommendation": "protect_or_expand_only_after_out_of_sample_replay",
        }
    return None


def build_window(
    records: list[TradeRecord],
    *,
    window: str,
    config: AnalyzerConfig,
) -> dict[str, Any]:
    segment_payload = {
        segment_type: segment_table(records, segment_type)
        for segment_type in SEGMENTS
    }
    candidates: list[dict[str, Any]] = []
    for segment_type, rows in segment_payload.items():
        if segment_type == "exit_family":
            # Exit reasons diagnose symptoms; they should not directly become
            # entry disables without a matching entry/regime/symbol slice.
            continue
        for segment in rows:
            candidate = classify_candidate(window=window, segment=segment, config=config)
            if candidate is not None:
                candidates.append(candidate)
    candidates.sort(key=lambda row: (row["candidate_type"] != "drag", row["total_pnl"]))

    return {
        "summary": summarise(records),
        "confidence_inversion": confidence_inversion(records, config),
        "segments": {
            segment_type: rows[:config.top_n]
            for segment_type, rows in segment_payload.items()
        },
        "action_candidates": candidates[:config.top_n],
    }


def analyze(records: list[TradeRecord], metadata: dict[str, Any], config: AnalyzerConfig) -> dict[str, Any]:
    windows: dict[str, dict[str, Any]] = {
        "all": build_window(records, window="all", config=config),
    }
    for window in WINDOWS:
        windows[f"last_{window}"] = build_window(
            _window_records(records, window),
            window=f"last_{window}",
            config=config,
        )

    all_candidates: list[dict[str, Any]] = []
    for window_name, payload in windows.items():
        for candidate in payload["action_candidates"]:
            all_candidates.append({"window": window_name, **candidate})
    all_candidates.sort(key=lambda row: (row["candidate_type"] != "drag", row["total_pnl"]))

    return {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "scope": "offline_research_only_no_live_behavior_change",
        "criteria": asdict(config),
        "metadata": metadata,
        "overall": windows["all"]["summary"],
        "windows": windows,
        "top_action_candidates": all_candidates[:config.top_n],
    }


def flatten_segments(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window, payload in summary["windows"].items():
        for segment_type, segments in payload["segments"].items():
            for segment in segments:
                rows.append({"window": window, **segment})
    return rows


def flatten_candidates(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for window, payload in summary["windows"].items():
        rows.extend(payload["action_candidates"])
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if rows:
        fieldnames = list(rows[0].keys())
    else:
        fieldnames = ["window", "segment_type", "value", "n_trades", "total_pnl"]
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(summary: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "summary_trade_attribution.json"
    segments_path = out_dir / "segments_trade_attribution.csv"
    candidates_path = out_dir / "candidates_trade_attribution.csv"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    _write_csv(segments_path, flatten_segments(summary))
    _write_csv(candidates_path, flatten_candidates(summary))
    return {
        "summary": str(summary_path),
        "segments": str(segments_path),
        "candidates": str(candidates_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trade-history", type=Path, default=DEFAULT_TRADE_HISTORY)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--min-trades-for-action", type=int, default=20)
    parser.add_argument("--min-recent-trades-for-action", type=int, default=10)
    parser.add_argument("--min-total-loss-for-action", type=float, default=25.0)
    parser.add_argument("--min-recent-loss-for-action", type=float, default=15.0)
    parser.add_argument("--top-n", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = AnalyzerConfig(
        min_trades_for_action=args.min_trades_for_action,
        min_recent_trades_for_action=args.min_recent_trades_for_action,
        min_total_loss_for_action=args.min_total_loss_for_action,
        min_recent_loss_for_action=args.min_recent_loss_for_action,
        top_n=args.top_n,
    )
    records, metadata = load_strategy_trades(args.trade_history)
    summary = analyze(records, metadata, config)
    outputs = write_outputs(summary, args.out_dir)

    overall = summary["overall"]
    print(f"[attr] strategy_trades={overall['n_trades']}")
    print(f"[attr] total_pnl={overall['total_pnl']:.2f}")
    print(f"[attr] win_rate={overall['win_rate']:.1%}")
    print(
        "[attr] confidence_inversion="
        f"{summary['windows']['all']['confidence_inversion']['flag']}"
    )
    print(f"[attr] candidates={len(summary['top_action_candidates'])}")
    print(f"[attr] summary={outputs['summary']}")
    print(f"[attr] segments={outputs['segments']}")
    print(f"[attr] candidates_csv={outputs['candidates']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
