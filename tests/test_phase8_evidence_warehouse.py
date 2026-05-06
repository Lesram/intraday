import csv
import json
import sqlite3

from scripts.phase8_evidence_warehouse import (
    WarehouseInputs,
    build_filter_outcome_summary,
    build_realized_trade_accounting,
    build_replay_candidates,
    build_symbol_evidence_summary,
    build_warehouse,
    normalize_event,
    normalize_order,
    normalize_realized_trade,
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


def test_phase8_normalizes_db_order_and_realized_trade_rows() -> None:
    order = normalize_order(
        {
            "id": "order-1",
            "client_idempotency_key": "key-1",
            "symbol": "amd",
            "side": "buy",
            "qty": "2",
            "order_type": "market",
            "status": "filled",
            "submitted_at": "2026-05-06 14:30:00+00",
            "created_at": "2026-05-06 14:30:00+00",
            "updated_at": "2026-05-06 14:31:00+00",
            "broker_order_id": "broker-1",
            "filled_qty": "2",
            "avg_fill_price": "100.25",
            "limit_price": "",
            "stop_price": "",
        }
    )
    realized = normalize_realized_trade(
        {
            "id": "trade-1",
            "symbol": "nvda",
            "qty": "1.5",
            "open_price": "900.0",
            "close_price": "903.5",
            "realized_pnl": "5.25",
            "realized_pnl_percent": "0.00389",
            "open_order_id": "open-1",
            "close_order_id": "close-1",
            "lot_id": "lot-1",
            "open_date": "2026-05-06 14:30:00+00",
            "close_date": "2026-05-06 14:35:00+00",
            "created_at": "2026-05-06 14:35:01+00",
        }
    )

    assert order["symbol"] == "AMD"
    assert order["qty"] == 2.0
    assert order["avg_fill_price"] == 100.25
    assert realized["symbol"] == "NVDA"
    assert realized["realized_pnl"] == 5.25
    assert realized["close_order_id"] == "close-1"


def test_phase8_builds_realized_trade_accounting_join() -> None:
    orders = [
        normalize_order(
            {
                "id": "open-1",
                "symbol": "amd",
                "side": "buy",
                "qty": "2",
                "status": "filled",
                "filled_qty": "2",
                "avg_fill_price": "100",
            }
        ),
        normalize_order(
            {
                "id": "close-1",
                "symbol": "amd",
                "side": "sell",
                "qty": "2",
                "status": "filled",
                "filled_qty": "2",
                "avg_fill_price": "101",
            }
        ),
    ]
    executions = [
        {
            "execution_id": "exec-open-1",
            "order_id": "open-1",
            "fill_qty": 1.0,
            "fill_price": 99.5,
        },
        {
            "execution_id": "exec-open-2",
            "order_id": "open-1",
            "fill_qty": 1.0,
            "fill_price": 100.5,
        },
        {
            "execution_id": "exec-close-1",
            "order_id": "close-1",
            "fill_qty": 2.0,
            "fill_price": 101.0,
        },
    ]
    realized = [
        {
            "realized_trade_id": "trade-1",
            "symbol": "AMD",
            "qty": 2.0,
            "open_price": 100.0,
            "close_price": 101.0,
            "realized_pnl": 2.0,
            "open_order_id": "open-1",
            "close_order_id": "close-1",
        }
    ]

    accounting = build_realized_trade_accounting(realized, orders, executions)

    assert accounting[0]["realized_trade_id"] == "trade-1"
    assert accounting[0]["open_exec_vwap"] == 100.0
    assert accounting[0]["close_exec_vwap"] == 101.0
    assert accounting[0]["realized_return_bps"] == 100.0
    assert accounting[0]["open_exec_qty_delta"] == 0.0
    assert accounting[0]["close_exec_qty_delta"] == 0.0
    assert accounting[0]["missing_open_order"] == 0
    assert accounting[0]["missing_close_order"] == 0


def test_phase8_builds_filter_and_symbol_research_summaries() -> None:
    outcomes = [
        {
            "symbol": "AMD",
            "status": "joined",
            "matched_filters": "all_candidates,alpha_breakout_chop",
            "directional_return_bps": 4.0,
            "raw_return_bps": 4.0,
            "confidence": 0.61,
            "horizon_bars": 5,
        },
        {
            "symbol": "AMD",
            "status": "joined",
            "matched_filters": "all_candidates,alpha_breakout_chop",
            "directional_return_bps": -1.0,
            "raw_return_bps": -1.0,
            "confidence": 0.59,
            "horizon_bars": 10,
        },
        {
            "symbol": "NVDA",
            "status": "joined",
            "matched_filters": "all_candidates",
            "directional_return_bps": 3.0,
            "raw_return_bps": 3.0,
            "confidence": 0.58,
            "horizon_bars": 5,
        },
    ]
    accounting = [
        {
            "symbol": "AMD",
            "realized_pnl": -2.0,
            "realized_return_bps": -10.0,
            "missing_open_order": 0,
            "missing_close_order": 0,
        }
    ]

    filters = build_filter_outcome_summary(outcomes)
    symbols = build_symbol_evidence_summary(outcomes, accounting)

    alpha = next(row for row in filters if row["filter_tag"] == "alpha_breakout_chop")
    amd = next(row for row in symbols if row["symbol"] == "AMD")
    nvda = next(row for row in symbols if row["symbol"] == "NVDA")

    assert alpha["joined_outcomes"] == 2
    assert alpha["promotion_authorized"] == 0
    assert alpha["recommendation"] == "collect_more_evidence"
    assert amd["avg_forward_directional_bps"] == 1.5
    assert amd["verdict"] == "conflicting_forward_positive_realized_negative"
    assert nvda["verdict"] == "forward_only_needs_realized_trades"


def test_phase8_exports_replay_candidates_without_promotion() -> None:
    filters = [
        {
            "filter_tag": "candidate_filter",
            "recommendation": "research_candidate_pending_replay",
            "joined_outcomes": 40,
            "avg_directional_return_bps": 3.0,
            "positive_directional_rate": 0.55,
        }
    ]
    symbols = [
        {
            "symbol": "AMD",
            "verdict": "aligned_positive_needs_replay",
            "joined_outcomes": 12,
            "realized_rows": 15,
            "avg_forward_directional_bps": 1.2,
            "positive_forward_rate": 0.6,
            "realized_total_pnl": 10.5,
            "avg_realized_return_bps": 2.1,
        },
        {
            "symbol": "PSQ",
            "verdict": "aligned_negative_expectancy",
            "joined_outcomes": 50,
            "realized_rows": 20,
            "avg_forward_directional_bps": -1.0,
            "realized_total_pnl": -5.0,
        },
    ]

    candidates = build_replay_candidates(filters, symbols)

    assert [candidate["candidate_id"] for candidate in candidates] == [
        "filter:candidate_filter",
        "symbol:AMD",
    ]
    assert all(candidate["promotion_authorized"] == 0 for candidate in candidates)
    assert all(
        candidate["required_next_step"] == "replay_before_any_live_change"
        for candidate in candidates
    )


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
    assert second["counts"]["db_orders"] == 0
    assert second["counts"]["realized_trade_accounting"] == 0
    assert second["counts"]["filter_outcome_summary"] == 2
    assert second["counts"]["symbol_evidence_summary"] == 1
    assert second["counts"]["replay_candidate_export"] == 0
    assert second["db_extract"]["enabled"] is False
    assert second["promotion_authorized"] is False

    conn = sqlite3.connect(out_dir / "strategy_evidence.sqlite")
    try:
        event_count = conn.execute("SELECT count(*) FROM evidence_events").fetchone()[0]
        outcome_count = conn.execute("SELECT count(*) FROM evidence_outcomes").fetchone()[0]
        trade_count = conn.execute("SELECT count(*) FROM trade_history").fetchone()[0]
        accounting_count = conn.execute(
            "SELECT count(*) FROM realized_trade_accounting"
        ).fetchone()[0]
        filter_count = conn.execute(
            "SELECT count(*) FROM filter_outcome_summary"
        ).fetchone()[0]
        symbol_count = conn.execute(
            "SELECT count(*) FROM symbol_evidence_summary"
        ).fetchone()[0]
        replay_count = conn.execute(
            "SELECT count(*) FROM replay_candidate_export"
        ).fetchone()[0]
    finally:
        conn.close()

    assert event_count == 2
    assert outcome_count == 1
    assert trade_count == 1
    assert accounting_count == 0
    assert filter_count == 2
    assert symbol_count == 1
    assert replay_count == 0
    assert (out_dir / "warehouse_summary.json").exists()
    assert (out_dir / "PHASE8_EVIDENCE_WAREHOUSE_REPORT.md").exists()
    assert (out_dir / "replay_candidates.json").exists()
    assert (out_dir / "PHASE8_POST_CLOSE_RESEARCH_REPORT.md").exists()
