from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.phase9_shadow_evidence import (
    Phase9EvidenceConfig,
    build_phase9_shadow_evidence,
    is_phase9_event,
    parse_horizons,
    write_outputs,
)


def _bars(
    *,
    start: str = "2026-05-08T19:20:00Z",
    periods: int = 90,
    base: float = 100.0,
    step: float = 0.05,
) -> pd.DataFrame:
    ts = pd.date_range(start, periods=periods, freq="min")
    close = [base + i * step for i in range(periods)]
    return pd.DataFrame({"timestamp": ts, "close": close})


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")


def test_phase9_event_filter_accepts_strategy_tag_or_id() -> None:
    assert is_phase9_event({
        "strategy_id": "alpha_baseline",
        "matched_filters": ["phase9_shadow"],
    })
    assert is_phase9_event({"strategy_id": "orb_sip_v2", "matched_filters": []})
    assert not is_phase9_event({"strategy_id": "alpha_baseline", "matched_filters": []})
    assert parse_horizons("1,5,5,10") == (1, 5, 10)


def test_phase9_shadow_evidence_joins_benchmarks_and_blocks_promotion(tmp_path: Path) -> None:
    telemetry = tmp_path / "strategy_evidence_events.jsonl"
    _write_jsonl(
        telemetry,
        [
            {
                "timestamp": "2026-05-08T19:25:00+00:00",
                "signal_id": "sig-qqq-1",
                "strategy_id": "etf_intraday_momentum",
                "engine_version": "etf_intraday_momentum.v1",
                "symbol": "QQQ",
                "side": "long",
                "direction": 1.0,
                "confidence": 0.62,
                "regime": "high_vol",
                "matched_filters": [
                    "phase9_shadow",
                    "strategy:etf_intraday_momentum",
                ],
                "features": {},
            },
            {
                "timestamp": "2026-05-08T19:25:00+00:00",
                "strategy_id": "alpha_baseline",
                "symbol": "AMD",
                "matched_filters": ["all_candidates"],
            },
        ],
    )
    bars = {
        "QQQ": _bars(base=400.0, step=0.20),
        "SPY": _bars(base=500.0, step=0.10),
    }

    payload = build_phase9_shadow_evidence(
        telemetry_path=telemetry,
        bars=bars,
        config=Phase9EvidenceConfig(horizons=(1, 5), random_samples=5),
    )

    assert payload["counts"]["raw_events"] == 2
    assert payload["counts"]["phase9_events"] == 1
    assert payload["counts"]["joined_outcomes"] == 2
    assert payload["promotion_authorized"] is False
    joined = [row for row in payload["outcomes"] if row["status"] == "joined"]
    assert joined[0]["signal_id"] == "sig-qqq-1"
    assert joined[0]["strategy_id"] == "etf_intraday_momentum"
    assert "alpha_over_symbol_hold_bps" in joined[0]
    assert "alpha_over_random_bps" in joined[0]
    assert all(row["promotion_authorized"] == 0 for row in joined)

    outputs = write_outputs(payload, tmp_path / "out")
    assert Path(outputs["summary"]).exists()
    assert Path(outputs["outcomes"]).exists()
    assert Path(outputs["report"]).read_text().startswith("# Phase 9 Shadow Evidence Report")


def test_phase9_shadow_evidence_handles_empty_input(tmp_path: Path) -> None:
    telemetry = tmp_path / "empty.jsonl"
    telemetry.write_text("")

    payload = build_phase9_shadow_evidence(
        telemetry_path=telemetry,
        bars={},
        config=Phase9EvidenceConfig(horizons=(1,)),
    )

    assert payload["counts"]["phase9_events"] == 0
    assert payload["counts"]["joined_outcomes"] == 0
    assert payload["strategy_league"] == []
