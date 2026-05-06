import csv
import json
import sqlite3

from scripts.phase8_evidence_warehouse import (
    WarehouseInputs,
    build_warehouse,
    normalize_event,
    write_outputs,
)


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")


def _write_csv(path, rows):
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_phase8_event_id_is_stable_for_same_event() -> None:
    event = {
        "_line_number": 3,
        "timestamp": "2026-05-06T14:30:00+00:00",
        "symbol": "amd",
        "tick": 10,
        "entry_source": "alpha",
        "confidence": 0.61,
        "ranking_score": 0.22,
        "matched_filters": ["alpha_breakout_chop"],
    }

    first = normalize_event("strategy_evidence", event)
    second = normalize_event("strategy_evidence", dict(event))

    assert first["event_id"] == second["event_id"]
    assert first["symbol"] == "AMD"
    assert json.loads(first["matched_filters_json"]) == ["alpha_breakout_chop"]


def test_phase8_builds_idempotent_sqlite_warehouse(tmp_path) -> None:
    strategy = tmp_path / "strategy.jsonl"
    candidate = tmp_path / "candidate.jsonl"
    outcomes = tmp_path / "outcomes.csv"
    trades = tmp_path / "trade_history.csv"
    out_dir = tmp_path / "out"

    _write_jsonl(
        strategy,
        [
            {
                "timestamp": "2026-05-06T14:30:00+00:00",
                "symbol": "AMD",
                "tick": 10,
                "entry_source": "alpha",
                "direction": 1.0,
                "confidence": 0.61,
                "effective_confidence": 0.61,
                "ranking_score": 0.22,
                "matched_filters": ["alpha_breakout_chop"],
            }
        ],
    )
    _write_jsonl(
        candidate,
        [
            {
                "timestamp": "2026-05-06T14:31:00+00:00",
                "symbol": "NVDA",
                "tick": 11,
                "entry_source": "alpha+breakout",
                "direction": 1.0,
                "confidence": 0.58,
                "ranking_score": 0.2,
                "matched_filters": ["alpha_breakout_chop"],
            }
        ],
    )
    _write_csv(
        outcomes,
        [
            {
                "event_line": "1",
                "event_timestamp": "2026-05-06T14:30:00+00:00",
                "symbol": "AMD",
                "regime": "chop",
                "direction": "1.0",
                "confidence": "0.61",
                "matched_filters": "all_candidates,alpha_breakout_chop",
                "horizon_bars": "5",
                "status": "joined",
                "bar_gap_seconds": "0",
                "entry_bar_timestamp": "2026-05-06T14:30:00+00:00",
                "future_bar_timestamp": "2026-05-06T14:35:00+00:00",
                "entry_close": "100",
                "future_close": "101",
                "raw_return_bps": "100",
                "directional_return_bps": "100",
            }
        ],
    )
    _write_csv(
        trades,
        [
            {
                "symbol": "AMD",
                "direction": "1.0",
                "entry_price": "100",
                "exit_price": "101",
                "shares": "2",
                "pnl": "2.0",
                "exit_reason": "test",
                "confidence": "0.61",
                "is_exploration": "False",
                "is_reconciliation_artifact": "False",
                "entry_source": "alpha",
                "regime_at_entry": "chop",
                "regime_at_exit": "chop",
                "closed_at": "2026-05-06T14:40:00+00:00",
            }
        ],
    )

    inputs = WarehouseInputs(
        strategy_telemetry=strategy,
        candidate_telemetry=candidate,
        phase6_outcomes=outcomes,
        trade_history=trades,
        out_dir=out_dir,
    )
    first = build_warehouse(inputs)
    second = build_warehouse(inputs)
    write_outputs(inputs, second)

    assert first["counts"]["events"] == 2
    assert second["counts"]["linked_outcomes"] == 1
    assert second["trade_history"]["total_pnl"] == 2.0
    assert second["promotion_authorized"] is False

    conn = sqlite3.connect(out_dir / "strategy_evidence.sqlite")
    try:
        event_count = conn.execute("SELECT count(*) FROM evidence_events").fetchone()[0]
        outcome_count = conn.execute("SELECT count(*) FROM evidence_outcomes").fetchone()[0]
        trade_count = conn.execute("SELECT count(*) FROM trade_history").fetchone()[0]
    finally:
        conn.close()

    assert event_count == 2
    assert outcome_count == 1
    assert trade_count == 1
    assert (out_dir / "warehouse_summary.json").exists()
    assert (out_dir / "PHASE8_EVIDENCE_WAREHOUSE_REPORT.md").exists()
