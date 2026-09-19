"""Phase 9 shadow strategy evidence report.

Reads Phase 9 CandidateSignal rows from the strategy-evidence JSONL feed and
joins them to cached OHLCV bars. The output compares each shadow signal against
same-symbol hold, market/sector benchmarks, random same-hold nulls, and delayed
entry nulls. Evidence-only: no ranking, sizing, order, or promotion state is
changed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.organism.engines.residual_mean_reversion import SECTOR_ETF_MAP  # noqa: E402
from backend.organism.evidence.benchmark_report import (  # noqa: E402
    BenchmarkComparison,
    directional_return_bps,
)
from backend.organism.evidence.null_models import (  # noqa: E402
    delayed_entry_return_bps,
    random_same_hold_return_bps,
)
from backend.organism.evidence.strategy_league import build_strategy_league  # noqa: E402
from backend.organism.sector_map import get_sector  # noqa: E402
from scripts.phase3_ml_target_redesign import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    load_cached_bars,
    normalize_bars,
    parse_symbols,
)
from scripts.phase8_evidence_warehouse import load_jsonl  # noqa: E402

DEFAULT_TELEMETRY_PATH = ROOT / "organism_brain" / "strategy_evidence_events.jsonl"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase9_shadow_evidence"
PHASE9_STRATEGY_IDS = frozenset({
    "etf_intraday_momentum",
    "orb_legacy_shadow",
    "orb_sip_v2",
    "residual_mean_reversion",
    "eod_reversal_shadow",
})


@dataclass(frozen=True)
class Phase9EvidenceConfig:
    horizons: tuple[int, ...] = (1, 5, 10, 20, 30, 60)
    max_event_to_bar_gap_seconds: float = 120.0
    default_cost_bps: float = 2.0
    random_samples: int = 100


def parse_horizons(raw: str | None) -> tuple[int, ...]:
    if raw is None:
        return Phase9EvidenceConfig().horizons
    values: list[int] = []
    for part in raw.split(","):
        text = part.strip()
        if not text:
            continue
        value = int(text)
        if value <= 0:
            raise ValueError("horizons must be positive integers")
        values.append(value)
    if not values:
        raise ValueError("horizon list cannot be empty")
    return tuple(dict.fromkeys(values))


def _finite_float(raw: Any, default: float = 0.0) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    if isinstance(raw, str) and raw.strip():
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def is_phase9_event(event: dict[str, Any]) -> bool:
    strategy_id = str(event.get("strategy_id") or "").strip().lower()
    tags = set(_tags(event.get("matched_filters")))
    return strategy_id in PHASE9_STRATEGY_IDS or "phase9_shadow" in tags


def _event_timestamp(event: dict[str, Any]) -> pd.Timestamp | None:
    ts = pd.to_datetime(str(event.get("timestamp") or ""), utc=True, errors="coerce")
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def _bar_index(
    frame: pd.DataFrame,
    timestamp: pd.Timestamp,
    max_gap_seconds: float,
) -> tuple[int | None, str, float]:
    timestamps = frame["timestamp"]
    idx = int(timestamps.searchsorted(timestamp, side="left"))
    if idx >= len(frame):
        return None, "no_bar_at_or_after_event", 0.0
    matched_ts = pd.Timestamp(timestamps.iloc[idx])
    gap_seconds = float((matched_ts - timestamp).total_seconds())
    if gap_seconds < 0 or gap_seconds > max_gap_seconds:
        return None, "bar_gap_too_large", gap_seconds
    return idx, "matched", gap_seconds


def _frame_for_symbol(bars: dict[str, pd.DataFrame], symbol: str) -> pd.DataFrame | None:
    frame = bars.get(symbol.upper())
    if frame is None or frame.empty or "close" not in frame.columns:
        return None
    return frame


def _raw_return_bps(frame: pd.DataFrame, entry_idx: int, exit_idx: int) -> float | None:
    if entry_idx >= len(frame) or exit_idx >= len(frame) or entry_idx >= exit_idx:
        return None
    entry = _finite_float(frame["close"].iloc[entry_idx])
    exit_ = _finite_float(frame["close"].iloc[exit_idx])
    if entry <= 0:
        return None
    return (exit_ - entry) / entry * 10000.0


def _benchmark_return(
    bars: dict[str, pd.DataFrame],
    symbol: str,
    timestamp: pd.Timestamp,
    horizon: int,
    max_gap_seconds: float,
) -> float | None:
    frame = _frame_for_symbol(bars, symbol)
    if frame is None:
        return None
    idx, status, _gap = _bar_index(frame, timestamp, max_gap_seconds)
    if idx is None or status != "matched":
        return None
    return _raw_return_bps(frame, idx, idx + horizon)


def _cost_bps(event: dict[str, Any], default_cost_bps: float) -> float:
    features_raw = event.get("features")
    features = features_raw if isinstance(features_raw, dict) else {}
    sip_raw = features.get("stocks_in_play")
    sip = sip_raw if isinstance(sip_raw, dict) else {}
    spread = _finite_float(sip.get("spread_bps"), 0.0)
    return spread if spread > 0 else default_cost_bps


def _stable_seed(*parts: Any) -> int:
    payload = json.dumps([str(part) for part in parts], separators=(",", ":"))
    return int(hashlib.sha256(payload.encode()).hexdigest()[:8], 16)


def join_phase9_event(
    event: dict[str, Any],
    bars: dict[str, pd.DataFrame],
    config: Phase9EvidenceConfig,
) -> list[dict[str, Any]]:
    symbol = str(event.get("symbol") or "").upper()
    strategy_id = str(event.get("strategy_id") or "").lower()
    side = str(event.get("side") or ("short" if _finite_float(event.get("direction")) < 0 else "long"))
    timestamp = _event_timestamp(event)
    base = {
        "event_line": event.get("_line_number", ""),
        "signal_id": event.get("signal_id", ""),
        "strategy_id": strategy_id,
        "engine_version": event.get("engine_version", ""),
        "event_timestamp": str(event.get("timestamp") or ""),
        "symbol": symbol,
        "side": side,
        "regime": str(event.get("regime") or "unknown"),
        "confidence": _finite_float(event.get("confidence")),
        "matched_filters": ",".join(_tags(event.get("matched_filters"))),
    }
    if timestamp is None:
        return [{**base, "horizon_bars": "", "status": "invalid_timestamp"}]
    frame = _frame_for_symbol(bars, symbol)
    if frame is None:
        return [{**base, "horizon_bars": "", "status": "symbol_missing_from_bars"}]
    idx, status, gap_seconds = _bar_index(
        frame,
        timestamp,
        config.max_event_to_bar_gap_seconds,
    )
    if idx is None:
        return [{**base, "horizon_bars": "", "status": status, "bar_gap_seconds": gap_seconds}]

    prices = [float(value) for value in frame["close"].astype(float).tolist()]
    rows: list[dict[str, Any]] = []
    sector_etf = SECTOR_ETF_MAP.get(get_sector(symbol), "SPY")
    for horizon in config.horizons:
        exit_idx = idx + horizon
        if exit_idx >= len(frame):
            rows.append({
                **base,
                "horizon_bars": horizon,
                "status": "insufficient_future_bars",
                "bar_gap_seconds": round(gap_seconds, 4),
            })
            continue
        entry_price = float(frame["close"].iloc[idx])
        future_price = float(frame["close"].iloc[exit_idx])
        raw_bps = directional_return_bps(entry_price, future_price, "long")
        realized_bps = directional_return_bps(entry_price, future_price, side)
        comparison = BenchmarkComparison(
            signal_id=str(event.get("signal_id") or ""),
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            realized_bps=realized_bps,
            same_symbol_hold_bps=raw_bps,
            market_benchmark_bps=_benchmark_return(
                bars,
                "SPY",
                timestamp,
                horizon,
                config.max_event_to_bar_gap_seconds,
            ),
            sector_benchmark_bps=_benchmark_return(
                bars,
                sector_etf,
                timestamp,
                horizon,
                config.max_event_to_bar_gap_seconds,
            ),
            random_null_bps=random_same_hold_return_bps(
                prices,
                hold_bars=horizon,
                side=side,
                samples=config.random_samples,
                seed=_stable_seed(symbol, strategy_id, horizon),
            ),
            delay_1_bps=delayed_entry_return_bps(
                prices, entry_index=idx, exit_index=exit_idx, delay_bars=1, side=side,
            ),
            delay_5_bps=delayed_entry_return_bps(
                prices, entry_index=idx, exit_index=exit_idx, delay_bars=5, side=side,
            ),
            delay_10_bps=delayed_entry_return_bps(
                prices, entry_index=idx, exit_index=exit_idx, delay_bars=10, side=side,
            ),
            cost_bps=_cost_bps(event, config.default_cost_bps),
        )
        rows.append({
            **base,
            **comparison.to_dict(),
            "horizon_bars": horizon,
            "status": "joined",
            "bar_gap_seconds": round(gap_seconds, 4),
            "entry_bar_timestamp": pd.Timestamp(frame["timestamp"].iloc[idx]).isoformat(),
            "future_bar_timestamp": pd.Timestamp(frame["timestamp"].iloc[exit_idx]).isoformat(),
            "entry_close": round(entry_price, 6),
            "future_close": round(future_price, 6),
            "raw_return_bps": round(raw_bps, 6),
            "directional_return_bps": round(realized_bps, 6),
            "sector_etf": sector_etf,
            "promotion_authorized": 0,
        })
    return rows


def build_phase9_shadow_evidence(
    *,
    telemetry_path: Path,
    bars: dict[str, pd.DataFrame],
    config: Phase9EvidenceConfig,
) -> dict[str, Any]:
    raw_events, invalid = load_jsonl(telemetry_path)
    events = [event for event in raw_events if is_phase9_event(event)]
    outcomes: list[dict[str, Any]] = []
    for event in events:
        outcomes.extend(join_phase9_event(event, bars, config))
    joined = [row for row in outcomes if row.get("status") == "joined"]
    league_inputs = [
        {
            "strategy_id": row["strategy_id"],
            "symbol": row["symbol"],
            "session": str(row["event_timestamp"])[:10],
            "pnl": row.get("net_realized_bps") or 0.0,
            "realized_bps": row.get("net_realized_bps") or 0.0,
            "r_multiple": 0.0,
            "alpha_over_symbol_hold_bps": row.get("alpha_over_symbol_hold_bps"),
            "alpha_over_market_bps": row.get("alpha_over_market_bps"),
            "alpha_over_random_bps": row.get("alpha_over_random_bps"),
            "alpha_over_delay_1_bps": row.get("alpha_over_delay_1_bps"),
            "alpha_over_delay_5_bps": row.get("alpha_over_delay_5_bps"),
            "alpha_over_delay_10_bps": row.get("alpha_over_delay_10_bps"),
        }
        for row in joined
    ]
    # Phase 9 shadow candidates do not yet have stop-defined R multiples.
    # Replay nomination is therefore based on after-cost benchmark/null alpha;
    # micro-paper or live promotion still happens later and must require R.
    league = build_strategy_league(league_inputs, require_positive_avg_r=False)
    replay_candidates = [
        {
            "candidate_id": f"strategy:{row['strategy_id']}",
            "candidate_type": "strategy",
            "strategy_id": row["strategy_id"],
            "reason": "phase9_shadow_benchmark_null_gate_passed",
            "joined_outcomes": row["n"],
            "avg_alpha_over_symbol_hold_bps": row["avg_alpha_over_symbol_hold_bps"],
            "avg_alpha_over_random_bps": row["avg_alpha_over_random_bps"],
            "avg_alpha_over_delay_bps": row["avg_alpha_over_delay_bps"],
            "required_next_step": "replay_before_any_micro_paper",
            "promotion_authorized": 0,
        }
        for row in league
        if row.get("verdict") == "replay_eligible"
    ]
    status_counts: dict[str, int] = {}
    for row in outcomes:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "scope": "phase9_shadow_evidence_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "telemetry_path": str(telemetry_path),
        "config": {
            "horizons": list(config.horizons),
            "max_event_to_bar_gap_seconds": config.max_event_to_bar_gap_seconds,
            "default_cost_bps": config.default_cost_bps,
            "random_samples": config.random_samples,
        },
        "counts": {
            "raw_events": len(raw_events),
            "phase9_events": len(events),
            "invalid_jsonl_rows": invalid,
            "outcomes": len(outcomes),
            "joined_outcomes": len(joined),
            "strategy_league": len(league),
            "replay_candidates": len(replay_candidates),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "outcomes": outcomes,
        "strategy_league": league,
        "replay_candidates": replay_candidates,
        "promotion_authorized": False,
        "live_behavior": "unchanged",
    }


def write_outputs(payload: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {key: value for key, value in payload.items() if key != "outcomes"}
    summary_path = out_dir / "phase9_shadow_summary.json"
    outcomes_path = out_dir / "phase9_shadow_outcomes.csv"
    league_path = out_dir / "phase9_strategy_league.json"
    replay_path = out_dir / "phase9_replay_candidates.json"
    report_path = out_dir / "PHASE9_SHADOW_EVIDENCE_REPORT.md"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    league_path.write_text(json.dumps(payload["strategy_league"], indent=2, sort_keys=True) + "\n")
    replay_path.write_text(json.dumps(payload["replay_candidates"], indent=2, sort_keys=True) + "\n")
    _write_csv(outcomes_path, payload["outcomes"])
    report_path.write_text(render_report(payload) + "\n")
    return {
        "summary": str(summary_path),
        "outcomes": str(outcomes_path),
        "strategy_league": str(league_path),
        "replay_candidates": str(replay_path),
        "report": str(report_path),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("")
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_report(payload: dict[str, Any]) -> str:
    counts = payload["counts"]
    lines = [
        "# Phase 9 Shadow Evidence Report",
        "",
        f"Generated: {payload['generated_at']}",
        "",
        "## Verdict",
        "",
        "- Live behavior changed: `false`",
        "- Promotion authorized: `false`",
        "- Required next step for any candidate: `replay_before_any_micro_paper`",
        "",
        "## Counts",
        "",
        f"- Phase 9 events: `{counts['phase9_events']}`",
        f"- Joined outcomes: `{counts['joined_outcomes']}`",
        f"- Status counts: `{counts['status_counts']}`",
        f"- Replay candidates: `{counts['replay_candidates']}`",
        "",
        "## Strategy League",
        "",
    ]
    league = payload["strategy_league"]
    if not league:
        lines.append("- None.")
    else:
        lines.extend([
            "| Strategy | N | Net bps | PF | Symbol alpha | Random alpha | Delay alpha | Verdict |",
            "|----------|---:|--------:|----:|-------------:|-------------:|------------:|---------|",
        ])
        for row in league:
            lines.append(
                f"| `{row['strategy_id']}` | `{row['n']}` | "
                f"`{row['total_pnl']}` | `{row['profit_factor']}` | "
                f"`{row['avg_alpha_over_symbol_hold_bps']}` | "
                f"`{row['avg_alpha_over_random_bps']}` | "
                f"`{row['avg_alpha_over_delay_bps']}` | `{row['verdict']}` |"
            )
    lines.extend([
        "",
        "## Guardrail",
        "",
        "This report can nominate replay work only. It does not authorize live "
        "orders, sizing, ranking, gates, or micro-paper promotion.",
    ])
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--telemetry-path", type=Path, default=DEFAULT_TELEMETRY_PATH)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--bar-file", default="bars.pkl")
    parser.add_argument("--symbols", default=None)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--horizons", default="1,5,10,20,30,60")
    parser.add_argument("--max-event-to-bar-gap-seconds", type=float, default=120.0)
    parser.add_argument("--default-cost-bps", type=float, default=2.0)
    parser.add_argument("--random-samples", type=int, default=100)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = Phase9EvidenceConfig(
        horizons=parse_horizons(args.horizons),
        max_event_to_bar_gap_seconds=args.max_event_to_bar_gap_seconds,
        default_cost_bps=args.default_cost_bps,
        random_samples=args.random_samples,
    )
    bars = normalize_bars(
        load_cached_bars(args.cache_dir, args.bar_file),
        parse_symbols(args.symbols),
    )
    payload = build_phase9_shadow_evidence(
        telemetry_path=args.telemetry_path,
        bars=bars,
        config=config,
    )
    print(json.dumps(write_outputs(payload, args.out_dir), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
