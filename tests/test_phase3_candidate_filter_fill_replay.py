"""Tests for Phase 3 candidate-filter fill-path replay."""

from __future__ import annotations

import csv
import json
import pickle
from pathlib import Path

import pandas as pd

from scripts.phase3_candidate_filter_fill_replay import (
    FillReplayConfig,
    _selected_scenarios,
    default_scenarios,
    evaluate_trade_path,
    load_cached_bars,
    load_fill_trades,
    normalise_fill_trade,
    run_fill_replay,
    write_outputs,
)


def _trade_row(
    pnl: float,
    *,
    symbol: str = "AAPL",
    direction: str = "1.0",
    entry_price: str = "100.0",
    exit_price: str = "101.0",
    shares: str = "2",
    confidence: str = "0.50",
    entry_source: str = "alpha+breakout",
    regime_at_entry: str = "chop",
    closed_at: str = "2026-05-04T14:03:00Z",
    hold_seconds: str = "180",
) -> dict[str, str]:
    return {
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "entry_bar": "12345",
        "exit_bar": "12348",
        "shares": shares,
        "pnl": str(pnl),
        "exit_reason": "max_holding_period",
        "predicted_return": "0.001",
        "actual_return": "0.001",
        "confidence": confidence,
        "correct_direction": "true",
        "is_exploration": "false",
        "is_reconciliation_artifact": "false",
        "entry_source": entry_source,
        "regime_at_entry": regime_at_entry,
        "regime_at_exit": regime_at_entry,
        "mfe": "0",
        "mae": "0",
        "bars_held_at_exit": "3",
        "time_in_trade_seconds": hold_seconds,
        "closed_at": closed_at,
    }


def _bars(
    *,
    symbol: str = "AAPL",
    start: str = "2026-05-04T14:00:00Z",
) -> dict[str, pd.DataFrame]:
    ts = pd.date_range(start=start, periods=5, freq="min", tz="UTC")
    return {
        symbol: pd.DataFrame(
            {
                "timestamp": [stamp.isoformat().replace("+00:00", "Z") for stamp in ts],
                "open": [100.0, 100.5, 101.0, 101.0, 100.8],
                "high": [100.5, 103.0, 102.0, 101.5, 101.0],
                "low": [99.0, 100.0, 100.5, 100.8, 100.5],
                "close": [100.2, 102.0, 101.2, 101.0, 100.7],
                "volume": [1000, 1000, 1000, 1000, 1000],
            }
        )
    }


def _write_trade_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_normalise_fill_trade_reconstructs_entry_from_hold_seconds():
    record, reason = normalise_fill_trade(_trade_row(2.0), row_number=2)

    assert reason is None
    assert record is not None
    assert record.closed_at.isoformat() == "2026-05-04T14:03:00+00:00"
    assert record.entry_at.isoformat() == "2026-05-04T14:00:00+00:00"
    assert record.direction == 1.0


def test_load_cached_bars_combines_multiple_bar_files(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    with (cache_dir / "bars.pkl").open("wb") as fh:
        pickle.dump(_bars(), fh)
    with (cache_dir / "bars_alt.pkl").open("wb") as fh:
        pickle.dump(
            _bars(start="2026-05-04T14:04:00Z"),
            fh,
        )

    bars, metadata = load_cached_bars(cache_dir)

    assert metadata["symbols"] == 1
    assert len(bars["AAPL"]) == 9
    assert metadata["coverage"]["AAPL"]["sources"] == ["bars.pkl", "bars_alt.pkl"]


def test_evaluate_trade_path_recomputes_long_mfe_mae_and_giveback():
    record, _ = normalise_fill_trade(_trade_row(2.0), row_number=2)
    assert record is not None
    bars, _ = load_cached_bars_from_payload(_bars())

    result, reason = evaluate_trade_path(record, bars, FillReplayConfig())

    assert reason is None
    assert result is not None
    assert result.reported_pnl == 2.0
    assert result.price_path_pnl == 2.0
    assert result.mfe_total == 6.0
    assert result.mae_total == -2.0
    assert result.giveback_total == 4.0
    assert result.capture_ratio == 0.3333
    assert result.entry_price_seen is True
    assert result.exit_price_seen is True


def test_evaluate_trade_path_handles_short_direction():
    row = _trade_row(
        2.0,
        direction="-1.0",
        entry_price="100.0",
        exit_price="98.0",
        shares="1",
    )
    record, _ = normalise_fill_trade(row, row_number=2)
    assert record is not None
    short_bars = {
        "AAPL": pd.DataFrame(
            {
                "timestamp": [
                    "2026-05-04T14:00:00Z",
                    "2026-05-04T14:01:00Z",
                    "2026-05-04T14:02:00Z",
                    "2026-05-04T14:03:00Z",
                ],
                "open": [100.0, 99.0, 98.5, 98.0],
                "high": [100.5, 101.0, 99.0, 98.4],
                "low": [99.5, 98.0, 97.0, 97.8],
                "close": [99.8, 98.5, 97.5, 98.0],
                "volume": [1000, 1000, 1000, 1000],
            }
        )
    }
    bars, _ = load_cached_bars_from_payload(short_bars)

    result, reason = evaluate_trade_path(record, bars, FillReplayConfig())

    assert reason is None
    assert result is not None
    assert result.price_path_pnl == 2.0
    assert result.mfe_total == 3.0
    assert result.mae_total == -1.0


def test_run_fill_replay_blocks_sparse_candidate_promotion():
    records = []
    for index in range(4):
        row = _trade_row(
            -2.0,
            closed_at=f"2026-05-04T14:0{index + 1}:00Z",
            hold_seconds="60",
        )
        record, reason = normalise_fill_trade(row, row_number=index + 2)
        assert reason is None
        assert record is not None
        records.append(record)
    bars, bar_metadata = load_cached_bars_from_payload(_bars())

    summary = run_fill_replay(
        records,
        {"source_csv": "synthetic", "strategy_rows": len(records)},
        bars,
        bar_metadata,
        config=FillReplayConfig(min_all_matched_trades=10),
    )

    all_results = summary["windows"]["all"]
    candidate = next(
        row for row in all_results if row["scenario"] == "candidate_conf_45_55"
    )
    assert candidate["matched_trades"] == 4
    assert candidate["recommendation"] == "insufficient_fill_sample_need_shadow_telemetry"


def test_fill_replay_supports_new_shadow_filter_scenarios():
    selected = _selected_scenarios(
        "candidate_alpha_breakout_chop_or_trending_down,"
        "candidate_inverse_etf_alpha_breakout_trending_down"
    )

    assert [scenario.name for scenario in selected] == [
        "candidate_alpha_breakout_chop_or_trending_down",
        "candidate_inverse_etf_alpha_breakout_trending_down",
    ]


def test_load_fill_trades_and_write_outputs(tmp_path: Path):
    trade_path = tmp_path / "trade_history.csv"
    _write_trade_csv(
        trade_path,
        [
            _trade_row(2.0),
            _trade_row(100.0, entry_source="reconciliation_orphan"),
        ],
    )
    records, metadata = load_fill_trades(trade_path)
    bars, bar_metadata = load_cached_bars_from_payload(_bars())

    summary = run_fill_replay(
        records,
        metadata,
        bars,
        bar_metadata,
        config=FillReplayConfig(min_all_matched_trades=1),
        scenarios=default_scenarios(),
    )
    outputs = write_outputs(summary, tmp_path / "out")

    loaded = json.loads(Path(outputs["summary"]).read_text())
    assert loaded["scope"] == "offline_fill_path_replay_no_live_behavior_change"
    assert loaded["trade_metadata"]["skipped_rows"]["reconciliation_artifact"] == 1
    assert Path(outputs["results"]).read_text().startswith("window,scenario")
    assert Path(outputs["matched_trades"]).read_text().startswith("row_number,symbol")


def load_cached_bars_from_payload(
    payload: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, object]]:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        cache_dir = Path(tmp)
        with (cache_dir / "bars.pkl").open("wb") as fh:
            pickle.dump(payload, fh)
        return load_cached_bars(cache_dir)
