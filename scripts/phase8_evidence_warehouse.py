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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STRATEGY_TELEMETRY = ROOT / "organism_brain" / "strategy_evidence_events.jsonl"
DEFAULT_CANDIDATE_TELEMETRY = ROOT / "organism_brain" / "candidate_filter_shadow_telemetry.jsonl"
DEFAULT_PHASE6_OUTCOMES = ROOT / "artifacts" / "phase6_strategy_evidence" / "strategy_evidence_outcomes.csv"
DEFAULT_TRADE_HISTORY = ROOT / "organism_brain" / "trade_history.csv"
DEFAULT_OUT_DIR = ROOT / "artifacts" / "phase8_evidence_warehouse"


@dataclass(frozen=True)
class WarehouseInputs:
    strategy_telemetry: Path
    candidate_telemetry: Path
    phase6_outcomes: Path
    trade_history: Path
    out_dir: Path
    db_name: str = "strategy_evidence.sqlite"


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


def normalize_event(source: str, event: dict[str, Any]) -> dict[str, Any]:
    line_number = _int_or_none(event.get("_line_number"))
    timestamp = str(event.get("timestamp") or "")
    symbol = str(event.get("symbol") or "").upper()
    event_id = _stable_hash([
        "event",
        source,
        line_number,
        timestamp,
        symbol,
        event.get("tick"),
        event.get("entry_source"),
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
        "entry_source": str(event.get("entry_source") or ""),
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
    trade_id = _stable_hash([
        "trade",
        row_number,
        symbol,
        row.get("entry_price"),
        row.get("exit_price"),
        row.get("shares"),
        row.get("pnl"),
        closed_at,
        row.get("entry_source"),
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
        "entry_source": str(row.get("entry_source") or ""),
        "regime_at_entry": str(row.get("regime_at_entry") or ""),
        "regime_at_exit": str(row.get("regime_at_exit") or ""),
        "closed_at": closed_at,
        "raw_json": json.dumps(row, sort_keys=True),
    }


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
            regime_at_entry TEXT,
            regime_at_exit TEXT,
            closed_at TEXT,
            raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_trade_history_symbol
            ON trade_history(symbol);

        CREATE TABLE IF NOT EXISTS warehouse_manifest (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )


def _upsert_rows(conn: sqlite3.Connection, table: str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    columns = list(rows[0].keys())
    placeholders = ", ".join("?" for _ in columns)
    update_columns = [col for col in columns if not col.endswith("_id")]
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
    invalid_jsonl_rows: dict[str, int],
) -> dict[str, Any]:
    joined = [row for row in outcomes if row["status"] == "joined"]
    linked = [row for row in outcomes if row["event_id"]]
    strategy_events = [row for row in events if row["source"] == "strategy_evidence"]
    candidate_events = [row for row in events if row["source"] == "candidate_filter_shadow"]
    pnl_values = [row["pnl"] for row in trades if row["pnl"] is not None]
    total_pnl = round(sum(float(value) for value in pnl_values), 4) if pnl_values else 0.0
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
        "counts": {
            "events": len(events),
            "strategy_events": len(strategy_events),
            "candidate_filter_events": len(candidate_events),
            "outcomes": len(outcomes),
            "joined_outcomes": len(joined),
            "linked_outcomes": len(linked),
            "trades": len(trades),
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
        f"- Invalid JSONL rows: `{counts['invalid_jsonl_rows']}`",
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

    db_path = inputs.out_dir / inputs.db_name
    conn = connect(db_path)
    try:
        create_schema(conn)
        inserted_events = _upsert_rows(conn, "evidence_events", events)
        inserted_outcomes = _upsert_rows(conn, "evidence_outcomes", outcomes)
        inserted_trades = _upsert_rows(conn, "trade_history", trades)
        summary = build_summary(
            inputs=inputs,
            db_path=db_path,
            events=events,
            outcomes=outcomes,
            trades=trades,
            invalid_jsonl_rows={
                "strategy_evidence": strategy_invalid,
                "candidate_filter_shadow": candidate_invalid,
            },
        )
        summary["rows_written"] = {
            "events": inserted_events,
            "outcomes": inserted_outcomes,
            "trades": inserted_trades,
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy-telemetry", type=Path, default=DEFAULT_STRATEGY_TELEMETRY)
    parser.add_argument("--candidate-telemetry", type=Path, default=DEFAULT_CANDIDATE_TELEMETRY)
    parser.add_argument("--phase6-outcomes", type=Path, default=DEFAULT_PHASE6_OUTCOMES)
    parser.add_argument("--trade-history", type=Path, default=DEFAULT_TRADE_HISTORY)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--db-name", default="strategy_evidence.sqlite")
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
    )
    summary = build_warehouse(inputs)
    if not args.no_report:
        write_outputs(inputs, summary)
    print(
        "Phase 8 evidence warehouse: "
        f"events={summary['counts']['events']} "
        f"outcomes={summary['counts']['outcomes']} "
        f"trades={summary['counts']['trades']} "
        f"db={inputs.out_dir / inputs.db_name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
