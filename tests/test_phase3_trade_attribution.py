"""Tests for the Phase 3 offline trade attribution analyzer."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.phase3_trade_attribution import (
    AnalyzerConfig,
    analyze,
    confidence_bucket,
    is_reconciliation_artifact,
    load_strategy_trades,
    summarise,
    write_outputs,
)


def _row(
    pnl: float,
    *,
    symbol: str = "AAPL",
    confidence: float = 0.7,
    entry_source: str = "alpha",
    regime_at_entry: str = "chop",
    exit_reason: str = "stop_loss",
    correct_direction: str = "false",
    is_reconciliation_artifact_value: str = "false",
) -> dict[str, str]:
    return {
        "symbol": symbol,
        "direction": "1.0",
        "entry_price": "100",
        "exit_price": "99",
        "entry_bar": "",
        "exit_bar": "",
        "shares": "1",
        "pnl": str(pnl),
        "exit_reason": exit_reason,
        "predicted_return": "0.001",
        "actual_return": "-0.001",
        "confidence": str(confidence),
        "correct_direction": correct_direction,
        "is_exploration": "false",
        "is_reconciliation_artifact": is_reconciliation_artifact_value,
        "entry_source": entry_source,
        "regime_at_entry": regime_at_entry,
        "regime_at_exit": regime_at_entry,
        "mfe": "0.5",
        "mae": "-1.0",
        "bars_held_at_exit": "4",
        "time_in_trade_seconds": "300",
        "closed_at": "2026-05-04T14:00:00Z",
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_reconciliation_filter_matches_strategy_health_rules():
    assert is_reconciliation_artifact(_row(1.0, is_reconciliation_artifact_value="true"))
    assert is_reconciliation_artifact(
        _row(1.0, exit_reason="reconciliation_adjustment")
    )
    assert is_reconciliation_artifact(
        _row(1.0, entry_source="reconciliation_orphan")
    )
    assert not is_reconciliation_artifact(_row(-1.0))


def test_load_strategy_trades_filters_artifacts_and_normalises_blanks(tmp_path: Path):
    rows = [
        _row(-2.0, entry_source="", regime_at_entry=""),
        _row(50.0, exit_reason="reconciliation_adjustment"),
        _row(20.0, entry_source="reconciliation_orphan"),
        _row(10.0, is_reconciliation_artifact_value="true"),
    ]
    path = tmp_path / "trade_history.csv"
    _write_csv(path, rows)

    records, metadata = load_strategy_trades(path)

    assert metadata["total_csv_rows"] == 4
    assert metadata["strategy_rows"] == 1
    assert metadata["excluded_reconciliation_artifacts"] == 3
    assert records[0].entry_source == "legacy_blank"
    assert records[0].regime_at_entry == "legacy_blank"


def test_confidence_buckets_are_stable():
    assert confidence_bucket(0.10) == "[0.00,0.35)"
    assert confidence_bucket(0.35) == "[0.35,0.45)"
    assert confidence_bucket(0.55) == "[0.55,0.65)"
    assert confidence_bucket(0.80) == "[0.75,inf)"


def test_analyze_flags_high_confidence_drag_and_action_candidates():
    rows = []
    rows.extend(
        _row(
            -3.0,
            symbol="LOSS",
            confidence=0.72,
            entry_source="alpha",
            regime_at_entry="chop",
        )
        for _ in range(24)
    )
    rows.extend(
        _row(
            1.5,
            symbol="WIN",
            confidence=0.55,
            entry_source="breakout",
            regime_at_entry="trending_up",
            exit_reason="max_holding_period",
            correct_direction="true",
        )
        for _ in range(24)
    )
    records = [
        record
        for record in (load_strategy_trades_from_rows(rows))
    ]

    summary = analyze(
        records,
        {"source_csv": "synthetic", "total_csv_rows": len(rows)},
        AnalyzerConfig(min_trades_for_action=20, min_total_loss_for_action=25.0),
    )

    assert summary["overall"]["n_trades"] == 48
    assert summary["windows"]["all"]["confidence_inversion"]["flag"] is True
    candidates = summary["windows"]["all"]["action_candidates"]
    assert any(
        c["segment_type"] == "entry_source"
        and c["value"] == "alpha"
        and c["candidate_type"] == "drag"
        for c in candidates
    )
    assert any(
        c["segment_type"] == "entry_source"
        and c["value"] == "breakout"
        and c["candidate_type"] == "strength"
        for c in candidates
    )


def test_write_outputs_round_trips_json_and_csv(tmp_path: Path):
    records = load_strategy_trades_from_rows([
        _row(-2.0),
        _row(3.0),
        _row(1.0, entry_source="breakout"),
    ])
    summary = analyze(records, {"source_csv": "synthetic"}, AnalyzerConfig(top_n=3))

    outputs = write_outputs(summary, tmp_path)

    loaded = json.loads(Path(outputs["summary"]).read_text())
    assert loaded["overall"]["n_trades"] == 3
    assert Path(outputs["segments"]).read_text().startswith("window,segment_type,value")
    assert Path(outputs["candidates"]).read_text().startswith("window,segment_type,value")


def load_strategy_trades_from_rows(rows: list[dict[str, str]]):
    from scripts.phase3_trade_attribution import normalise_trade

    return [
        record
        for row in rows
        if not is_reconciliation_artifact(row)
        if (record := normalise_trade(row)) is not None
    ]


def test_summarise_uses_real_pnl_and_direction_accuracy():
    records = load_strategy_trades_from_rows([
        _row(5.0, correct_direction="true"),
        _row(-2.0, correct_direction="false"),
        _row(1.0, correct_direction="true"),
    ])

    out = summarise(records)

    assert out["n_trades"] == 3
    assert out["total_pnl"] == 4.0
    assert out["win_rate"] == 0.6667
    assert out["correct_direction_rate"] == 0.6667
