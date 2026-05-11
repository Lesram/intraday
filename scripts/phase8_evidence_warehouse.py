"""Phase 8 strategy evidence warehouse v2.

Builds an idempotent, queryable SQLite evidence warehouse from the existing
paper shadow telemetry, outcome joins, and brain trade history. This is
research/evidence-only: it never imports live engine code and never changes
ranking, sizing, gates, orders, or promotion state.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.organism.evidence.strategy_league import build_strategy_league
from backend.organism.schema.candidate_signal import infer_strategy_id

DEFAULT_STRATEGY_TELEMETRY = ROOT / "organism_brain" / "strategy_evidence_events.jsonl"
DEFAULT_CANDIDATE_TELEMETRY = ROOT / "organism_brain" / "candidate_filter_shadow_telemetry.jsonl"
DEFAULT_PHASE6_OUTCOMES = ROOT / "artifacts" / "phase6_strategy_evidence" / "strategy_evidence_outcomes.csv"
DEFAULT_TRADE_HISTORY = ROOT / "organism_brain" / "trade_history.csv"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase8_evidence_warehouse"
MIN_FILTER_OUTCOMES_FOR_RESEARCH = 30
MIN_POSITIVE_RATE_FOR_RESEARCH = 0.52
MIN_AVG_DIRECTIONAL_BPS_FOR_RESEARCH = 2.0
MIN_SYMBOL_OUTCOMES_FOR_REPLAY = 10
MIN_SYMBOL_REALIZED_ROWS_FOR_REPLAY = 10
MIN_SYMBOL_AVG_FORWARD_BPS_FOR_REPLAY = 0.5
MIN_SYMBOL_POSITIVE_FORWARD_RATE_FOR_REPLAY = 0.5


@dataclass(frozen=True)
class WarehouseInputs:
    strategy_telemetry: Path
    candidate_telemetry: Path
    phase6_outcomes: Path
    trade_history: Path
    out_dir: Path
    db_name: str = "strategy_evidence.sqlite"
    include_db: bool = False
    db_container: str = "trading_platform_db_paper"
    db_user: str = "trading"
    postgres_db: str = "algotrading"


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _finite_float(raw: Any, default: float | None = None) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def _int_or_none(raw: Any) -> int | None:
    try:
        if raw in ("", None):
            return None
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _tags_json(raw: Any) -> str:
    if isinstance(raw, list):
        tags = [str(item) for item in raw if str(item)]
    elif isinstance(raw, str) and raw.strip():
        tags = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        tags = []
    return json.dumps(tags, sort_keys=True)


def _split_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        tags = [str(item).strip() for item in raw if str(item).strip()]
    elif isinstance(raw, str) and raw.strip():
        tags = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        tags = []
    return tags or ["untagged"]


def _stable_hash(parts: list[Any]) -> str:
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def load_jsonl(path: Path) -> tuple[list[dict[str, Any]], int]:
    rows: list[dict[str, Any]] = []
    invalid = 0
    if not path.exists():
        return rows, invalid
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if not isinstance(event, dict):
            invalid += 1
            continue
        event["_line_number"] = line_number
        rows.append(event)
    return rows, invalid


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def read_psql_csv(inputs: WarehouseInputs, query: str) -> list[dict[str, str]]:
    """Run a read-only psql extract through docker and parse CSV output."""
    if not inputs.include_db:
        return []
    query_head = query.strip().upper()
    if not (query_head.startswith("SELECT") or query_head.startswith("WITH")):
        raise ValueError("Phase 8 DB extracts must be read-only SELECT/WITH queries")
    output = subprocess.check_output(
        [
            "docker",
            "exec",
            inputs.db_container,
            "psql",
            "-U",
            inputs.db_user,
            "-d",
            inputs.postgres_db,
            "--csv",
            "--set",
            "ON_ERROR_STOP=1",
            "-c",
            query,
        ],
        text=True,
    )
    if not output.strip():
        return []
    return list(csv.DictReader(output.splitlines()))


def normalize_event(source: str, event: dict[str, Any]) -> dict[str, Any]:
    line_number = _int_or_none(event.get("_line_number"))
    timestamp = str(event.get("timestamp") or "")
    symbol = str(event.get("symbol") or "").upper()
    entry_source = str(event.get("entry_source") or "")
    strategy_id = infer_strategy_id(entry_source, event.get("strategy_id"))
    event_id = _stable_hash([
        "event",
        source,
        line_number,
        timestamp,
        symbol,
        event.get("tick"),
        entry_source,
        event.get("confidence"),
        event.get("ranking_score"),
    ])
    return {
        "event_id": event_id,
        "source": source,
        "line_number": line_number,
        "timestamp": timestamp,
        "symbol": symbol,
        "tick": _int_or_none(event.get("tick")),
        "regime": str(event.get("regime") or ""),
        "direction": _finite_float(event.get("direction")),
        "confidence": _finite_float(event.get("confidence")),
        "effective_confidence": _finite_float(event.get("effective_confidence")),
        "breakout_score": _finite_float(event.get("breakout_score")),
        "predicted_return": _finite_float(event.get("predicted_return")),
        "ranking_score": _finite_float(event.get("ranking_score")),
        "entry_source": entry_source,
        "strategy_id": strategy_id,
        "matched_filters_json": _tags_json(event.get("matched_filters")),
        "live_pipeline_candidate": 1 if event.get("live_pipeline_candidate", True) else 0,
        "raw_json": json.dumps(
            {k: v for k, v in event.items() if k != "_line_number"},
            sort_keys=True,
            default=str,
        ),
    }


def _event_lookup(events: list[dict[str, Any]]) -> dict[tuple[str, str, int | None], str]:
    lookup: dict[tuple[str, str, int | None], str] = {}
    for event in events:
        key = (event["timestamp"], event["symbol"], event["line_number"])
        lookup.setdefault(key, event["event_id"])
    return lookup


def normalize_outcome(row: dict[str, str], event_lookup: dict[tuple[str, str, int | None], str]) -> dict[str, Any]:
    line_number = _int_or_none(row.get("event_line"))
    timestamp = str(row.get("event_timestamp") or "")
    symbol = str(row.get("symbol") or "").upper()
    horizon = _int_or_none(row.get("horizon_bars"))
    event_id = event_lookup.get((timestamp, symbol, line_number))
    outcome_id = _stable_hash(["outcome", event_id, line_number, timestamp, symbol, horizon, row.get("status")])
    return {
        "outcome_id": outcome_id,
        "event_id": event_id,
        "event_line": line_number,
        "event_timestamp": timestamp,
        "symbol": symbol,
        "regime": str(row.get("regime") or ""),
        "direction": _finite_float(row.get("direction")),
        "confidence": _finite_float(row.get("confidence")),
        "matched_filters": str(row.get("matched_filters") or ""),
        "horizon_bars": horizon,
        "status": str(row.get("status") or ""),
        "bar_gap_seconds": _finite_float(row.get("bar_gap_seconds")),
        "entry_bar_timestamp": str(row.get("entry_bar_timestamp") or ""),
        "future_bar_timestamp": str(row.get("future_bar_timestamp") or ""),
        "entry_close": _finite_float(row.get("entry_close")),
        "future_close": _finite_float(row.get("future_close")),
        "raw_return_bps": _finite_float(row.get("raw_return_bps")),
        "directional_return_bps": _finite_float(row.get("directional_return_bps")),
        "raw_json": json.dumps(row, sort_keys=True),
    }


def normalize_trade(row: dict[str, str], row_number: int) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "").upper()
    closed_at = str(row.get("closed_at") or "")
    entry_source = str(row.get("entry_source") or "")
    strategy_id = infer_strategy_id(entry_source, row.get("strategy_id"))
    trade_id = _stable_hash([
        "trade",
        row_number,
        symbol,
        row.get("entry_price"),
        row.get("exit_price"),
        row.get("shares"),
        row.get("pnl"),
        closed_at,
        entry_source,
    ])
    return {
        "trade_id": trade_id,
        "row_number": row_number,
        "symbol": symbol,
        "direction": _finite_float(row.get("direction")),
        "entry_price": _finite_float(row.get("entry_price")),
        "exit_price": _finite_float(row.get("exit_price")),
        "shares": _finite_float(row.get("shares")),
        "pnl": _finite_float(row.get("pnl")),
        "exit_reason": str(row.get("exit_reason") or ""),
        "confidence": _finite_float(row.get("confidence")),
        "is_exploration": str(row.get("is_exploration") or "").lower() == "true",
        "is_reconciliation_artifact": str(row.get("is_reconciliation_artifact") or "").lower() == "true",
        "entry_source": entry_source,
        "strategy_id": strategy_id,
        "regime_at_entry": str(row.get("regime_at_entry") or ""),
        "regime_at_exit": str(row.get("regime_at_exit") or ""),
        "actual_return": _finite_float(row.get("actual_return")),
        "mfe": _finite_float(row.get("mfe")),
        "mae": _finite_float(row.get("mae")),
        "closed_at": closed_at,
        "raw_json": json.dumps(row, sort_keys=True),
    }


def normalize_order(row: dict[str, str]) -> dict[str, Any]:
    return {
        "order_id": str(row.get("id") or ""),
        "client_idempotency_key": str(row.get("client_idempotency_key") or ""),
        "symbol": str(row.get("symbol") or "").upper(),
        "side": str(row.get("side") or ""),
        "qty": _finite_float(row.get("qty")),
        "order_type": str(row.get("order_type") or ""),
        "status": str(row.get("status") or ""),
        "submitted_at": str(row.get("submitted_at") or ""),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "broker_order_id": str(row.get("broker_order_id") or ""),
        "filled_qty": _finite_float(row.get("filled_qty")),
        "avg_fill_price": _finite_float(row.get("avg_fill_price")),
        "limit_price": _finite_float(row.get("limit_price")),
        "stop_price": _finite_float(row.get("stop_price")),
        "raw_json": json.dumps(row, sort_keys=True, default=str),
    }


def normalize_execution(row: dict[str, str]) -> dict[str, Any]:
    return {
        "execution_id": str(row.get("id") or ""),
        "order_id": str(row.get("order_id") or ""),
        "fill_qty": _finite_float(row.get("fill_qty")),
        "fill_price": _finite_float(row.get("fill_price")),
        "ts": str(row.get("ts") or ""),
        "venue": str(row.get("venue") or ""),
        "created_at": str(row.get("created_at") or ""),
        "raw_json": json.dumps(row, sort_keys=True, default=str),
    }


def normalize_realized_trade(row: dict[str, str]) -> dict[str, Any]:
    return {
        "realized_trade_id": str(row.get("id") or ""),
        "symbol": str(row.get("symbol") or "").upper(),
        "qty": _finite_float(row.get("qty")),
        "open_price": _finite_float(row.get("open_price")),
        "close_price": _finite_float(row.get("close_price")),
        "realized_pnl": _finite_float(row.get("realized_pnl")),
        "realized_pnl_percent": _finite_float(row.get("realized_pnl_percent")),
        "open_order_id": str(row.get("open_order_id") or ""),
        "close_order_id": str(row.get("close_order_id") or ""),
        "lot_id": str(row.get("lot_id") or ""),
        "open_date": str(row.get("open_date") or ""),
        "close_date": str(row.get("close_date") or ""),
        "created_at": str(row.get("created_at") or ""),
        "raw_json": json.dumps(row, sort_keys=True, default=str),
    }


def _safe_bps(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return round(10000.0 * numerator / denominator, 4)


def _execution_stats_by_order(
    executions: list[dict[str, Any]],
) -> dict[str, dict[str, float | None]]:
    grouped: dict[str, dict[str, float]] = {}
    for row in executions:
        order_id = str(row.get("order_id") or "")
        qty = _finite_float(row.get("fill_qty"), 0.0) or 0.0
        price = _finite_float(row.get("fill_price"), 0.0) or 0.0
        stats = grouped.setdefault(order_id, {"qty": 0.0, "notional": 0.0})
        stats["qty"] += qty
        stats["notional"] += qty * price
    return {
        order_id: {
            "exec_qty": round(stats["qty"], 8),
            "exec_vwap": (
                round(stats["notional"] / stats["qty"], 8)
                if stats["qty"]
                else None
            ),
        }
        for order_id, stats in grouped.items()
    }


def _order_qty_delta(
    order: dict[str, Any] | None,
    stats: dict[str, float | None] | None,
) -> float | None:
    if not order or not stats:
        return None
    filled_qty = _finite_float(order.get("filled_qty"))
    exec_qty = _finite_float(stats.get("exec_qty"))
    if filled_qty is None or exec_qty is None:
        return None
    return round(filled_qty - exec_qty, 8)


def build_realized_trade_accounting(
    realized_trades: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    executions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    orders_by_id = {str(row.get("order_id") or ""): row for row in orders}
    executions_by_order = _execution_stats_by_order(executions)
    rows: list[dict[str, Any]] = []
    for trade in realized_trades:
        open_order = orders_by_id.get(str(trade.get("open_order_id") or ""))
        close_order = orders_by_id.get(str(trade.get("close_order_id") or ""))
        open_exec = executions_by_order.get(str(trade.get("open_order_id") or ""))
        close_exec = executions_by_order.get(str(trade.get("close_order_id") or ""))
        open_side = str(open_order.get("side") or "") if open_order else ""
        direction = -1.0 if open_side.lower() == "sell" else 1.0
        open_price = _finite_float(trade.get("open_price"))
        close_price = _finite_float(trade.get("close_price"))
        qty = _finite_float(trade.get("qty"))
        realized_move = (
            direction * (close_price - open_price)
            if open_price is not None and close_price is not None
            else None
        )
        open_order_avg = _finite_float(open_order.get("avg_fill_price")) if open_order else None
        close_order_avg = _finite_float(close_order.get("avg_fill_price")) if close_order else None
        row = {
            "realized_trade_id": str(trade.get("realized_trade_id") or ""),
            "symbol": str(trade.get("symbol") or "").upper(),
            "qty": qty,
            "open_order_id": str(trade.get("open_order_id") or ""),
            "close_order_id": str(trade.get("close_order_id") or ""),
            "open_side": open_side,
            "close_side": str(close_order.get("side") or "") if close_order else "",
            "open_order_status": str(open_order.get("status") or "") if open_order else "",
            "close_order_status": str(close_order.get("status") or "") if close_order else "",
            "open_filled_qty": _finite_float(open_order.get("filled_qty")) if open_order else None,
            "close_filled_qty": (
                _finite_float(close_order.get("filled_qty")) if close_order else None
            ),
            "open_avg_fill_price": open_order_avg,
            "close_avg_fill_price": close_order_avg,
            "open_exec_qty": _finite_float(open_exec.get("exec_qty")) if open_exec else None,
            "close_exec_qty": _finite_float(close_exec.get("exec_qty")) if close_exec else None,
            "open_exec_vwap": _finite_float(open_exec.get("exec_vwap")) if open_exec else None,
            "close_exec_vwap": _finite_float(close_exec.get("exec_vwap")) if close_exec else None,
            "open_price": open_price,
            "close_price": close_price,
            "realized_pnl": _finite_float(trade.get("realized_pnl")),
            "realized_return_bps": _safe_bps(realized_move, open_price),
            "gross_notional": (
                round(abs(qty) * (open_price + close_price), 4)
                if qty is not None and open_price is not None and close_price is not None
                else None
            ),
            "open_price_vs_order_bps": _safe_bps(
                (
                    None
                    if open_price is None or open_order_avg is None
                    else open_price - open_order_avg
                ),
                open_order_avg,
            ),
            "close_price_vs_order_bps": _safe_bps(
                (
                    None
                    if close_price is None or close_order_avg is None
                    else close_price - close_order_avg
                ),
                close_order_avg,
            ),
            "missing_open_order": 0 if open_order else 1,
            "missing_close_order": 0 if close_order else 1,
            "open_exec_qty_delta": _order_qty_delta(open_order, open_exec),
            "close_exec_qty_delta": _order_qty_delta(close_order, close_exec),
            "raw_json": json.dumps(trade, sort_keys=True, default=str),
        }
        rows.append(row)
    return rows


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _positive_rate(values: list[float]) -> float | None:
    return round(sum(1 for value in values if value > 0) / len(values), 4) if values else None


def _filter_recommendation(outcome_count: int, avg_bps: float | None, positive_rate: float | None) -> str:
    if outcome_count < MIN_FILTER_OUTCOMES_FOR_RESEARCH:
        return "collect_more_evidence"
    if avg_bps is None or positive_rate is None:
        return "insufficient_joined_outcomes"
    if (
        avg_bps >= MIN_AVG_DIRECTIONAL_BPS_FOR_RESEARCH
        and positive_rate >= MIN_POSITIVE_RATE_FOR_RESEARCH
    ):
        return "research_candidate_pending_replay"
    if avg_bps <= -MIN_AVG_DIRECTIONAL_BPS_FOR_RESEARCH and positive_rate <= 0.48:
        return "reject_negative_expectancy"
    return "inconclusive_continue_shadow"


def build_filter_outcome_summary(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in outcomes:
        if row.get("status") != "joined":
            continue
        for tag in _split_tags(row.get("matched_filters")):
            grouped.setdefault(tag, []).append(row)

    summaries: list[dict[str, Any]] = []
    for tag, rows in sorted(grouped.items()):
        directional = [
            value
            for value in (_finite_float(row.get("directional_return_bps")) for row in rows)
            if value is not None
        ]
        raw_returns = [
            value
            for value in (_finite_float(row.get("raw_return_bps")) for row in rows)
            if value is not None
        ]
        confidences = [
            value
            for value in (_finite_float(row.get("confidence")) for row in rows)
            if value is not None
        ]
        horizons = [
            value
            for value in (_int_or_none(row.get("horizon_bars")) for row in rows)
            if value is not None
        ]
        avg_bps = _avg(directional)
        positive_rate = _positive_rate(directional)
        recommendation = _filter_recommendation(len(rows), avg_bps, positive_rate)
        summaries.append({
            "filter_tag": tag,
            "joined_outcomes": len(rows),
            "avg_directional_return_bps": avg_bps,
            "positive_directional_rate": positive_rate,
            "avg_raw_return_bps": _avg(raw_returns),
            "avg_confidence": _avg(confidences),
            "min_horizon_bars": min(horizons) if horizons else None,
            "max_horizon_bars": max(horizons) if horizons else None,
            "recommendation": recommendation,
            "promotion_authorized": 0,
        })
    return summaries


def _symbol_verdict(
    forward_avg_bps: float | None,
    realized_total_pnl: float | None,
    realized_rows: int,
) -> str:
    if realized_rows == 0:
        return "forward_only_needs_realized_trades"
    if forward_avg_bps is None:
        return "realized_only_missing_forward_outcomes"
    if forward_avg_bps > 0 and (realized_total_pnl or 0.0) > 0:
        return "aligned_positive_needs_replay"
    if forward_avg_bps > 0 and (realized_total_pnl or 0.0) <= 0:
        return "conflicting_forward_positive_realized_negative"
    if forward_avg_bps <= 0 and (realized_total_pnl or 0.0) <= 0:
        return "aligned_negative_expectancy"
    return "conflicting_forward_negative_realized_positive"


def build_symbol_evidence_summary(
    outcomes: list[dict[str, Any]],
    accounting_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    outcomes_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in outcomes:
        if row.get("status") == "joined":
            outcomes_by_symbol.setdefault(str(row.get("symbol") or "").upper(), []).append(row)
    accounting_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in accounting_rows:
        accounting_by_symbol.setdefault(str(row.get("symbol") or "").upper(), []).append(row)

    symbols = sorted(set(outcomes_by_symbol) | set(accounting_by_symbol))
    summaries: list[dict[str, Any]] = []
    for symbol in symbols:
        outcome_rows = outcomes_by_symbol.get(symbol, [])
        realized_rows = accounting_by_symbol.get(symbol, [])
        forward_values = [
            value
            for value in (
                _finite_float(row.get("directional_return_bps")) for row in outcome_rows
            )
            if value is not None
        ]
        realized_values = [
            value
            for value in (_finite_float(row.get("realized_pnl")) for row in realized_rows)
            if value is not None
        ]
        realized_return_values = [
            value
            for value in (_finite_float(row.get("realized_return_bps")) for row in realized_rows)
            if value is not None
        ]
        forward_avg = _avg(forward_values)
        realized_total = round(sum(realized_values), 4) if realized_values else 0.0
        summaries.append({
            "symbol": symbol,
            "joined_outcomes": len(outcome_rows),
            "avg_forward_directional_bps": forward_avg,
            "positive_forward_rate": _positive_rate(forward_values),
            "realized_rows": len(realized_rows),
            "realized_total_pnl": realized_total,
            "avg_realized_return_bps": _avg(realized_return_values),
            "missing_order_links": sum(
                int(row.get("missing_open_order") or 0)
                + int(row.get("missing_close_order") or 0)
                for row in realized_rows
            ),
            "verdict": _symbol_verdict(forward_avg, realized_total, len(realized_rows)),
            "promotion_authorized": 0,
        })
    return summaries


def build_replay_candidates(
    filter_summaries: list[dict[str, Any]],
    symbol_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in filter_summaries:
        if row.get("recommendation") != "research_candidate_pending_replay":
            continue
        candidate = {
            "candidate_id": f"filter:{row['filter_tag']}",
            "candidate_type": "filter",
            "symbol": "",
            "filter_tag": row["filter_tag"],
            "reason": "filter_forward_returns_pass_research_gate",
            "joined_outcomes": row.get("joined_outcomes"),
            "realized_rows": None,
            "avg_forward_directional_bps": row.get("avg_directional_return_bps"),
            "positive_directional_rate": row.get("positive_directional_rate"),
            "realized_total_pnl": None,
            "avg_realized_return_bps": None,
            "required_next_step": "replay_before_any_live_change",
            "promotion_authorized": 0,
        }
        candidate["raw_json"] = json.dumps(candidate, sort_keys=True, default=str)
        candidates.append(candidate)

    for row in symbol_summaries:
        if row.get("verdict") != "aligned_positive_needs_replay":
            continue
        joined = _int_or_none(row.get("joined_outcomes")) or 0
        realized_rows = _int_or_none(row.get("realized_rows")) or 0
        avg_forward = _finite_float(row.get("avg_forward_directional_bps"))
        positive_rate = _finite_float(row.get("positive_forward_rate"))
        realized_pnl = _finite_float(row.get("realized_total_pnl"), 0.0) or 0.0
        if joined < MIN_SYMBOL_OUTCOMES_FOR_REPLAY:
            continue
        if realized_rows < MIN_SYMBOL_REALIZED_ROWS_FOR_REPLAY:
            continue
        if avg_forward is None or avg_forward < MIN_SYMBOL_AVG_FORWARD_BPS_FOR_REPLAY:
            continue
        if positive_rate is None or positive_rate < MIN_SYMBOL_POSITIVE_FORWARD_RATE_FOR_REPLAY:
            continue
        if realized_pnl <= 0:
            continue
        candidate = {
            "candidate_id": f"symbol:{row['symbol']}",
            "candidate_type": "symbol",
            "symbol": row["symbol"],
            "filter_tag": "",
            "reason": "forward_and_realized_symbol_evidence_aligned_positive",
            "joined_outcomes": joined,
            "realized_rows": realized_rows,
            "avg_forward_directional_bps": avg_forward,
            "positive_directional_rate": positive_rate,
            "realized_total_pnl": realized_pnl,
            "avg_realized_return_bps": row.get("avg_realized_return_bps"),
            "required_next_step": "replay_before_any_live_change",
            "promotion_authorized": 0,
        }
        candidate["raw_json"] = json.dumps(candidate, sort_keys=True, default=str)
        candidates.append(candidate)
    return sorted(candidates, key=lambda item: (item["candidate_type"], item["candidate_id"]))


def build_strategy_league_summary(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    league_inputs: list[dict[str, Any]] = []
    for trade in trades:
        if trade.get("is_reconciliation_artifact"):
            continue
        closed_at = str(trade.get("closed_at") or "")
        session = closed_at[:10] if len(closed_at) >= 10 else ""
        actual_return = _finite_float(trade.get("actual_return"), 0.0) or 0.0
        league_inputs.append({
            "strategy_id": trade.get("strategy_id") or "alpha_baseline",
            "symbol": trade.get("symbol") or "",
            "session": session,
            "pnl": trade.get("pnl") or 0.0,
            "realized_bps": actual_return * 10000.0,
            "r_multiple": 0.0,
            "mfe": trade.get("mfe") or 0.0,
            "mae": trade.get("mae") or 0.0,
        })
    rows = build_strategy_league(league_inputs)
    out: list[dict[str, Any]] = []
    for row in rows:
        materialized = dict(row)
        materialized["raw_json"] = json.dumps(row, sort_keys=True, default=str)
        out.append(materialized)
    return out


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS evidence_events (
            event_id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            line_number INTEGER,
            timestamp TEXT,
            symbol TEXT,
            tick INTEGER,
            regime TEXT,
            direction REAL,
            confidence REAL,
            effective_confidence REAL,
            breakout_score REAL,
            predicted_return REAL,
            ranking_score REAL,
            entry_source TEXT,
            strategy_id TEXT,
            matched_filters_json TEXT,
            live_pipeline_candidate INTEGER,
            raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_events_symbol_ts
            ON evidence_events(symbol, timestamp);
        CREATE INDEX IF NOT EXISTS idx_evidence_events_source
            ON evidence_events(source);

        CREATE TABLE IF NOT EXISTS evidence_outcomes (
            outcome_id TEXT PRIMARY KEY,
            event_id TEXT,
            event_line INTEGER,
            event_timestamp TEXT,
            symbol TEXT,
            regime TEXT,
            direction REAL,
            confidence REAL,
            matched_filters TEXT,
            horizon_bars INTEGER,
            status TEXT,
            bar_gap_seconds REAL,
            entry_bar_timestamp TEXT,
            future_bar_timestamp TEXT,
            entry_close REAL,
            future_close REAL,
            raw_return_bps REAL,
            directional_return_bps REAL,
            raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_evidence_outcomes_event
            ON evidence_outcomes(event_id);
        CREATE INDEX IF NOT EXISTS idx_evidence_outcomes_symbol_horizon
            ON evidence_outcomes(symbol, horizon_bars);

        CREATE TABLE IF NOT EXISTS trade_history (
            trade_id TEXT PRIMARY KEY,
            row_number INTEGER,
            symbol TEXT,
            direction REAL,
            entry_price REAL,
            exit_price REAL,
            shares REAL,
            pnl REAL,
            exit_reason TEXT,
            confidence REAL,
            is_exploration INTEGER,
            is_reconciliation_artifact INTEGER,
            entry_source TEXT,
            strategy_id TEXT,
            regime_at_entry TEXT,
            regime_at_exit TEXT,
            actual_return REAL,
            mfe REAL,
            mae REAL,
            closed_at TEXT,
            raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_trade_history_symbol
            ON trade_history(symbol);

        CREATE TABLE IF NOT EXISTS strategy_league (
            strategy_id TEXT PRIMARY KEY,
            n INTEGER,
            total_pnl REAL,
            profit_factor TEXT,
            win_rate REAL,
            avg_r REAL,
            avg_realized_bps REAL,
            avg_alpha_over_symbol_hold_bps REAL,
            avg_alpha_over_random_bps REAL,
            avg_alpha_over_delay_bps REAL,
            positive_symbol_alpha_rate REAL,
            max_drawdown REAL,
            max_symbol_concentration REAL,
            max_session_concentration REAL,
            verdict TEXT,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS db_orders (
            order_id TEXT PRIMARY KEY,
            client_idempotency_key TEXT,
            symbol TEXT,
            side TEXT,
            qty REAL,
            order_type TEXT,
            status TEXT,
            submitted_at TEXT,
            created_at TEXT,
            updated_at TEXT,
            broker_order_id TEXT,
            filled_qty REAL,
            avg_fill_price REAL,
            limit_price REAL,
            stop_price REAL,
            raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_db_orders_symbol_status
            ON db_orders(symbol, status);
        CREATE INDEX IF NOT EXISTS idx_db_orders_broker_order_id
            ON db_orders(broker_order_id);

        CREATE TABLE IF NOT EXISTS db_executions (
            execution_id TEXT PRIMARY KEY,
            order_id TEXT,
            fill_qty REAL,
            fill_price REAL,
            ts TEXT,
            venue TEXT,
            created_at TEXT,
            raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_db_executions_order_id
            ON db_executions(order_id);

        CREATE TABLE IF NOT EXISTS db_realized_trades (
            realized_trade_id TEXT PRIMARY KEY,
            symbol TEXT,
            qty REAL,
            open_price REAL,
            close_price REAL,
            realized_pnl REAL,
            realized_pnl_percent REAL,
            open_order_id TEXT,
            close_order_id TEXT,
            lot_id TEXT,
            open_date TEXT,
            close_date TEXT,
            created_at TEXT,
            raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_db_realized_trades_symbol
            ON db_realized_trades(symbol);
        CREATE INDEX IF NOT EXISTS idx_db_realized_trades_close_order
            ON db_realized_trades(close_order_id);

        CREATE TABLE IF NOT EXISTS realized_trade_accounting (
            realized_trade_id TEXT PRIMARY KEY,
            symbol TEXT,
            qty REAL,
            open_order_id TEXT,
            close_order_id TEXT,
            open_side TEXT,
            close_side TEXT,
            open_order_status TEXT,
            close_order_status TEXT,
            open_filled_qty REAL,
            close_filled_qty REAL,
            open_avg_fill_price REAL,
            close_avg_fill_price REAL,
            open_exec_qty REAL,
            close_exec_qty REAL,
            open_exec_vwap REAL,
            close_exec_vwap REAL,
            open_price REAL,
            close_price REAL,
            realized_pnl REAL,
            realized_return_bps REAL,
            gross_notional REAL,
            open_price_vs_order_bps REAL,
            close_price_vs_order_bps REAL,
            missing_open_order INTEGER,
            missing_close_order INTEGER,
            open_exec_qty_delta REAL,
            close_exec_qty_delta REAL,
            raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_realized_trade_accounting_symbol
            ON realized_trade_accounting(symbol);
        CREATE INDEX IF NOT EXISTS idx_realized_trade_accounting_orders
            ON realized_trade_accounting(open_order_id, close_order_id);

        CREATE TABLE IF NOT EXISTS filter_outcome_summary (
            filter_tag TEXT PRIMARY KEY,
            joined_outcomes INTEGER,
            avg_directional_return_bps REAL,
            positive_directional_rate REAL,
            avg_raw_return_bps REAL,
            avg_confidence REAL,
            min_horizon_bars INTEGER,
            max_horizon_bars INTEGER,
            recommendation TEXT,
            promotion_authorized INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_filter_outcome_summary_recommendation
            ON filter_outcome_summary(recommendation);

        CREATE TABLE IF NOT EXISTS symbol_evidence_summary (
            symbol TEXT PRIMARY KEY,
            joined_outcomes INTEGER,
            avg_forward_directional_bps REAL,
            positive_forward_rate REAL,
            realized_rows INTEGER,
            realized_total_pnl REAL,
            avg_realized_return_bps REAL,
            missing_order_links INTEGER,
            verdict TEXT,
            promotion_authorized INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_symbol_evidence_summary_verdict
            ON symbol_evidence_summary(verdict);

        CREATE TABLE IF NOT EXISTS replay_candidate_export (
            candidate_id TEXT PRIMARY KEY,
            candidate_type TEXT,
            symbol TEXT,
            filter_tag TEXT,
            reason TEXT,
            joined_outcomes INTEGER,
            realized_rows INTEGER,
            avg_forward_directional_bps REAL,
            positive_directional_rate REAL,
            realized_total_pnl REAL,
            avg_realized_return_bps REAL,
            required_next_step TEXT,
            promotion_authorized INTEGER,
            raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_replay_candidate_export_type
            ON replay_candidate_export(candidate_type);

        CREATE TABLE IF NOT EXISTS warehouse_manifest (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    _ensure_column(conn, "evidence_events", "strategy_id", "TEXT")
    _ensure_column(conn, "trade_history", "strategy_id", "TEXT")
    _ensure_column(conn, "trade_history", "actual_return", "REAL")
    _ensure_column(conn, "trade_history", "mfe", "REAL")
    _ensure_column(conn, "trade_history", "mae", "REAL")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_history_strategy "
        "ON trade_history(strategy_id)"
    )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl_type: str) -> None:
    existing = {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def _upsert_rows(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    primary_key = columns[0]
    update_columns = [col for col in columns if col != primary_key]
    updates = ", ".join(f"{col}=excluded.{col}" for col in update_columns)
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT DO UPDATE SET {updates}"
    )
    values = [[row.get(col) for col in columns] for row in rows]
    conn.executemany(sql, values)
    return len(rows)


def write_manifest(conn: sqlite3.Connection, summary: dict[str, Any]) -> None:
    rows = [(key, json.dumps(value, sort_keys=True, default=str)) for key, value in summary.items()]
    conn.executemany(
        "INSERT INTO warehouse_manifest(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        rows,
    )


def build_summary(
    *,
    inputs: WarehouseInputs,
    db_path: Path,
    events: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    orders: list[dict[str, Any]],
    executions: list[dict[str, Any]],
    realized_trades: list[dict[str, Any]],
    accounting_rows: list[dict[str, Any]],
    filter_summaries: list[dict[str, Any]],
    symbol_summaries: list[dict[str, Any]],
    replay_candidates: list[dict[str, Any]],
    strategy_league: list[dict[str, Any]],
    invalid_jsonl_rows: dict[str, int],
) -> dict[str, Any]:
    joined = [row for row in outcomes if row["status"] == "joined"]
    linked = [row for row in outcomes if row["event_id"]]
    strategy_events = [row for row in events if row["source"] == "strategy_evidence"]
    candidate_events = [row for row in events if row["source"] == "candidate_filter_shadow"]
    pnl_values = [row["pnl"] for row in trades if row["pnl"] is not None]
    total_pnl = round(sum(float(value) for value in pnl_values), 4) if pnl_values else 0.0
    status_counts: dict[str, int] = {}
    for row in orders:
        status = str(row.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
    realized_values = [
        row["realized_pnl"] for row in realized_trades if row["realized_pnl"] is not None
    ]
    realized_total_pnl = (
        round(sum(float(value) for value in realized_values), 4) if realized_values else 0.0
    )
    realized_return_values = [
        row["realized_return_bps"]
        for row in accounting_rows
        if row.get("realized_return_bps") is not None
    ]
    order_exec_delta_rows = [
        row
        for row in accounting_rows
        if abs(_finite_float(row.get("open_exec_qty_delta"), 0.0) or 0.0) > 0.000001
        or abs(_finite_float(row.get("close_exec_qty_delta"), 0.0) or 0.0) > 0.000001
    ]
    filter_recommendations: dict[str, int] = {}
    for row in filter_summaries:
        recommendation = str(row.get("recommendation") or "unknown")
        filter_recommendations[recommendation] = filter_recommendations.get(recommendation, 0) + 1
    symbol_verdicts: dict[str, int] = {}
    for row in symbol_summaries:
        verdict = str(row.get("verdict") or "unknown")
        symbol_verdicts[verdict] = symbol_verdicts.get(verdict, 0) + 1
    return {
        "scope": "phase8_strategy_evidence_warehouse_v2_no_live_behavior_change",
        "generated_at": datetime.now(UTC).isoformat(),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "sha": _git("rev-parse", "HEAD"),
        "db_path": str(db_path),
        "inputs": {
            "strategy_telemetry": str(inputs.strategy_telemetry),
            "candidate_telemetry": str(inputs.candidate_telemetry),
            "phase6_outcomes": str(inputs.phase6_outcomes),
            "trade_history": str(inputs.trade_history),
        },
        "db_extract": {
            "enabled": inputs.include_db,
            "container": inputs.db_container if inputs.include_db else "",
            "postgres_db": inputs.postgres_db if inputs.include_db else "",
            "order_status_counts": dict(sorted(status_counts.items())),
            "realized_total_pnl": realized_total_pnl,
            "accounting_join": {
                "rows": len(accounting_rows),
                "missing_open_orders": sum(
                    int(row["missing_open_order"]) for row in accounting_rows
                ),
                "missing_close_orders": sum(
                    int(row["missing_close_order"]) for row in accounting_rows
                ),
                "order_execution_qty_delta_rows": len(order_exec_delta_rows),
                "winning_rows": sum(
                    1 for row in accounting_rows
                    if (row.get("realized_pnl") is not None and row["realized_pnl"] > 0)
                ),
                "losing_rows": sum(
                    1 for row in accounting_rows
                    if (row.get("realized_pnl") is not None and row["realized_pnl"] < 0)
                ),
                "avg_realized_return_bps": (
                    round(sum(realized_return_values) / len(realized_return_values), 4)
                    if realized_return_values
                    else None
                ),
            },
            "research_summaries": {
                "filter_recommendations": dict(sorted(filter_recommendations.items())),
                "symbol_verdicts": dict(sorted(symbol_verdicts.items())),
                "replay_candidate_count": len(replay_candidates),
                "promotion_authorized_rows": 0,
            },
            "research_outputs": {
                "post_close_verdict": "no_live_promotion_replay_required",
                "replay_candidates": replay_candidates,
                "strategy_league": strategy_league,
            },
        },
        "counts": {
            "events": len(events),
            "strategy_events": len(strategy_events),
            "candidate_filter_events": len(candidate_events),
            "outcomes": len(outcomes),
            "joined_outcomes": len(joined),
            "linked_outcomes": len(linked),
            "trades": len(trades),
            "db_orders": len(orders),
            "db_executions": len(executions),
            "db_realized_trades": len(realized_trades),
            "realized_trade_accounting": len(accounting_rows),
            "filter_outcome_summary": len(filter_summaries),
            "symbol_evidence_summary": len(symbol_summaries),
            "strategy_league": len(strategy_league),
            "replay_candidate_export": len(replay_candidates),
            "invalid_jsonl_rows": invalid_jsonl_rows,
        },
        "trade_history": {
            "total_pnl": total_pnl,
            "profitable": total_pnl > 0,
        },
        "live_behavior": "unchanged",
        "promotion_authorized": False,
    }


def render_report(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    trade = summary["trade_history"]
    db_extract = summary["db_extract"]
    accounting = db_extract["accounting_join"]
    research = db_extract["research_summaries"]
    return "\n".join([
        "# Phase 8 Evidence Warehouse V2 Report",
        "",
        f"Generated: {summary['generated_at']}",
        f"Branch: `{summary['branch']}`",
        f"SHA: `{summary['sha']}`",
        "",
        "## Verdict",
        "",
        "The warehouse build is evidence-only. It does not change live ranking, "
        "sizing, gates, order submission, or promotion state.",
        "",
        "## Counts",
        "",
        f"- Events: `{counts['events']}`",
        f"- Strategy evidence events: `{counts['strategy_events']}`",
        f"- Candidate-filter shadow events: `{counts['candidate_filter_events']}`",
        f"- Outcomes: `{counts['outcomes']}`",
        f"- Joined outcomes: `{counts['joined_outcomes']}`",
        f"- Linked outcomes: `{counts['linked_outcomes']}`",
        f"- Trade-history rows: `{counts['trades']}`",
        f"- DB orders: `{counts['db_orders']}`",
        f"- DB executions: `{counts['db_executions']}`",
        f"- DB realized trades: `{counts['db_realized_trades']}`",
        f"- Realized-trade accounting rows: `{counts['realized_trade_accounting']}`",
        f"- Filter outcome summaries: `{counts['filter_outcome_summary']}`",
        f"- Symbol evidence summaries: `{counts['symbol_evidence_summary']}`",
        f"- Strategy league rows: `{counts['strategy_league']}`",
        f"- Replay candidate exports: `{counts['replay_candidate_export']}`",
        f"- Invalid JSONL rows: `{counts['invalid_jsonl_rows']}`",
        "",
        "## DB Extract",
        "",
        f"- Enabled: `{db_extract['enabled']}`",
        f"- Order status counts: `{db_extract['order_status_counts']}`",
        f"- Realized-trades total PnL loaded from DB: `{db_extract['realized_total_pnl']}`",
        f"- Accounting missing open orders: `{accounting['missing_open_orders']}`",
        f"- Accounting missing close orders: `{accounting['missing_close_orders']}`",
        "- Accounting order/execution quantity deltas: "
        f"`{accounting['order_execution_qty_delta_rows']}`",
        f"- Accounting average realized return bps: `{accounting['avg_realized_return_bps']}`",
        f"- Filter recommendations: `{research['filter_recommendations']}`",
        f"- Symbol verdicts: `{research['symbol_verdicts']}`",
        f"- Replay candidate count: `{research['replay_candidate_count']}`",
        f"- Promotion authorized rows: `{research['promotion_authorized_rows']}`",
        "",
        "## Trading Reality",
        "",
        f"- Trade-history total PnL loaded into the warehouse: `{trade['total_pnl']}`",
        f"- Profitable on loaded trade history: `{trade['profitable']}`",
        "- Promotion authorized: `false`",
        "",
        "## Outputs",
        "",
        f"- SQLite warehouse: `{summary['db_path']}`",
        "- Summary JSON: `warehouse_summary.json`",
        "- Report: `PHASE8_EVIDENCE_WAREHOUSE_REPORT.md`",
        "",
    ])


def render_post_close_report(summary: dict[str, Any]) -> str:
    research_outputs = summary["db_extract"]["research_outputs"]
    candidates = research_outputs["replay_candidates"]
    strategy_league = research_outputs.get("strategy_league", [])
    lines = [
        "# Phase 8 Post-Close Research Decision Report",
        "",
        f"Generated: {summary['generated_at']}",
        f"Branch: `{summary['branch']}`",
        f"SHA: `{summary['sha']}`",
        "",
        "## Verdict",
        "",
        f"- Post-close verdict: `{research_outputs['post_close_verdict']}`",
        "- Live promotion authorized: `false`",
        "- Required next step for every candidate: `replay_before_any_live_change`",
        "",
        "## Replay Candidates",
        "",
    ]
    if not candidates:
        lines.append("- None.")
    else:
        lines.extend([
            "| Candidate | Type | Evidence | Required next step |",
            "|-----------|------|----------|--------------------|",
        ])
        for candidate in candidates:
            label = candidate["symbol"] or candidate["filter_tag"]
            evidence = (
                f"joined={candidate['joined_outcomes']}; "
                f"realized_rows={candidate['realized_rows']}; "
                f"forward_bps={candidate['avg_forward_directional_bps']}; "
                f"realized_pnl={candidate['realized_total_pnl']}"
            )
            lines.append(
                f"| `{label}` | `{candidate['candidate_type']}` | "
                f"`{evidence}` | `{candidate['required_next_step']}` |"
            )
    lines.extend([
        "",
        "## Strategy League",
        "",
    ])
    if not strategy_league:
        lines.append("- None.")
    else:
        lines.extend([
            "| Strategy | N | PnL | PF | Win rate | Verdict |",
            "|----------|---:|----:|----:|---------:|---------|",
        ])
        for row in strategy_league:
            lines.append(
                f"| `{row['strategy_id']}` | `{row['n']}` | "
                f"`{row['total_pnl']}` | `{row['profit_factor']}` | "
                f"`{row['win_rate']}` | `{row['verdict']}` |"
            )
    lines.extend([
        "",
        "## Guardrail",
        "",
        "This report can nominate replay work only. It does not authorize ranking, "
        "sizing, entry, exit, gate, or promotion changes in live/paper behavior.",
        "",
    ])
    return "\n".join(lines)


def build_warehouse(inputs: WarehouseInputs) -> dict[str, Any]:
    strategy_raw, strategy_invalid = load_jsonl(inputs.strategy_telemetry)
    candidate_raw, candidate_invalid = load_jsonl(inputs.candidate_telemetry)
    events = [
        *(normalize_event("strategy_evidence", event) for event in strategy_raw),
        *(normalize_event("candidate_filter_shadow", event) for event in candidate_raw),
    ]
    event_lookup = _event_lookup(events)
    outcomes = [
        normalize_outcome(row, event_lookup)
        for row in read_csv_rows(inputs.phase6_outcomes)
    ]
    trades = [
        normalize_trade(row, row_number)
        for row_number, row in enumerate(read_csv_rows(inputs.trade_history), start=1)
    ]
    orders = [
        normalize_order(row)
        for row in read_psql_csv(
            inputs,
            """
            SELECT id, client_idempotency_key, symbol, side, qty, order_type,
                   status, submitted_at, created_at, updated_at, broker_order_id,
                   filled_qty, avg_fill_price, limit_price, stop_price
            FROM orders
            ORDER BY created_at, id;
            """,
        )
    ]
    executions = [
        normalize_execution(row)
        for row in read_psql_csv(
            inputs,
            """
            SELECT id, order_id, fill_qty, fill_price, ts, venue, created_at
            FROM executions
            ORDER BY ts, id;
            """,
        )
    ]
    realized_trades = [
        normalize_realized_trade(row)
        for row in read_psql_csv(
            inputs,
            """
            SELECT id, symbol, qty, open_price, close_price, realized_pnl,
                   realized_pnl_percent, open_order_id, close_order_id, lot_id,
                   open_date, close_date, created_at
            FROM realized_trades
            ORDER BY created_at, id;
            """,
        )
    ]
    accounting_rows = build_realized_trade_accounting(realized_trades, orders, executions)
    filter_summaries = build_filter_outcome_summary(outcomes)
    symbol_summaries = build_symbol_evidence_summary(outcomes, accounting_rows)
    replay_candidates = build_replay_candidates(filter_summaries, symbol_summaries)
    strategy_league = build_strategy_league_summary(trades)

    db_path = inputs.out_dir / inputs.db_name
    conn = connect(db_path)
    try:
        create_schema(conn)
        inserted_events = _upsert_rows(conn, "evidence_events", events)
        inserted_outcomes = _upsert_rows(conn, "evidence_outcomes", outcomes)
        inserted_trades = _upsert_rows(conn, "trade_history", trades)
        inserted_orders = _upsert_rows(conn, "db_orders", orders)
        inserted_executions = _upsert_rows(conn, "db_executions", executions)
        inserted_realized_trades = _upsert_rows(conn, "db_realized_trades", realized_trades)
        inserted_accounting_rows = _upsert_rows(
            conn,
            "realized_trade_accounting",
            accounting_rows,
        )
        inserted_filter_summaries = _upsert_rows(
            conn,
            "filter_outcome_summary",
            filter_summaries,
        )
        inserted_symbol_summaries = _upsert_rows(
            conn,
            "symbol_evidence_summary",
            symbol_summaries,
        )
        inserted_strategy_league = _upsert_rows(
            conn,
            "strategy_league",
            strategy_league,
        )
        inserted_replay_candidates = _upsert_rows(
            conn,
            "replay_candidate_export",
            replay_candidates,
        )
        summary = build_summary(
            inputs=inputs,
            db_path=db_path,
            events=events,
            outcomes=outcomes,
            trades=trades,
            orders=orders,
            executions=executions,
            realized_trades=realized_trades,
            accounting_rows=accounting_rows,
            filter_summaries=filter_summaries,
            symbol_summaries=symbol_summaries,
            replay_candidates=replay_candidates,
            strategy_league=strategy_league,
            invalid_jsonl_rows={
                "strategy_evidence": strategy_invalid,
                "candidate_filter_shadow": candidate_invalid,
            },
        )
        summary["rows_written"] = {
            "events": inserted_events,
            "outcomes": inserted_outcomes,
            "trades": inserted_trades,
            "db_orders": inserted_orders,
            "db_executions": inserted_executions,
            "db_realized_trades": inserted_realized_trades,
            "realized_trade_accounting": inserted_accounting_rows,
            "filter_outcome_summary": inserted_filter_summaries,
            "symbol_evidence_summary": inserted_symbol_summaries,
            "strategy_league": inserted_strategy_league,
            "replay_candidate_export": inserted_replay_candidates,
        }
        write_manifest(conn, summary)
        conn.commit()
    finally:
        conn.close()
    return summary


def write_outputs(inputs: WarehouseInputs, summary: dict[str, Any]) -> None:
    inputs.out_dir.mkdir(parents=True, exist_ok=True)
    (inputs.out_dir / "warehouse_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    (inputs.out_dir / "PHASE8_EVIDENCE_WAREHOUSE_REPORT.md").write_text(
        render_report(summary)
    )
    (inputs.out_dir / "replay_candidates.json").write_text(
        json.dumps(
            summary["db_extract"]["research_outputs"]["replay_candidates"],
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (inputs.out_dir / "strategy_league.json").write_text(
        json.dumps(
            summary["db_extract"]["research_outputs"]["strategy_league"],
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (inputs.out_dir / "PHASE8_POST_CLOSE_RESEARCH_REPORT.md").write_text(
        render_post_close_report(summary)
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy-telemetry", type=Path, default=DEFAULT_STRATEGY_TELEMETRY)
    parser.add_argument("--candidate-telemetry", type=Path, default=DEFAULT_CANDIDATE_TELEMETRY)
    parser.add_argument("--phase6-outcomes", type=Path, default=DEFAULT_PHASE6_OUTCOMES)
    parser.add_argument("--trade-history", type=Path, default=DEFAULT_TRADE_HISTORY)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--db-name", default="strategy_evidence.sqlite")
    parser.add_argument("--include-db", action="store_true")
    parser.add_argument("--db-container", default="trading_platform_db_paper")
    parser.add_argument("--db-user", default="trading")
    parser.add_argument("--postgres-db", default="algotrading")
    parser.add_argument("--no-report", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inputs = WarehouseInputs(
        strategy_telemetry=args.strategy_telemetry,
        candidate_telemetry=args.candidate_telemetry,
        phase6_outcomes=args.phase6_outcomes,
        trade_history=args.trade_history,
        out_dir=args.out_dir,
        db_name=args.db_name,
        include_db=args.include_db,
        db_container=args.db_container,
        db_user=args.db_user,
        postgres_db=args.postgres_db,
    )
    summary = build_warehouse(inputs)
    if not args.no_report:
        write_outputs(inputs, summary)
    print(
        "Phase 8 evidence warehouse: "
        f"events={summary['counts']['events']} "
        f"outcomes={summary['counts']['outcomes']} "
        f"trades={summary['counts']['trades']} "
        f"db_orders={summary['counts']['db_orders']} "
        f"db_realized_trades={summary['counts']['db_realized_trades']} "
        f"accounting={summary['counts']['realized_trade_accounting']} "
        f"filters={summary['counts']['filter_outcome_summary']} "
        f"symbols={summary['counts']['symbol_evidence_summary']} "
        f"replay_candidates={summary['counts']['replay_candidate_export']} "
        f"db={inputs.out_dir / inputs.db_name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
