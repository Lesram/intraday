from __future__ import annotations

import json
from pathlib import Path

from scripts.ci.platform_truth_observer import (
    build_observer_report,
    is_first_class_event,
)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n")


def test_platform_truth_observer_refuses_green_without_first_class_events(tmp_path):
    telemetry = tmp_path / "strategy_evidence_events.jsonl"
    warehouse = tmp_path / "warehouse_summary.json"
    phase9 = tmp_path / "phase9_shadow_summary.json"
    _write_jsonl(
        telemetry,
        [
            {
                "timestamp": "2026-05-10T14:00:00Z",
                "symbol": "SPY",
                "entry_source": "alpha",
            }
        ],
    )
    _write_json(
        warehouse,
        {
            "sha": "not-current",
            "promotion_authorized": False,
            "count_reconciliation": {"ok": True, "mismatches": {}},
        },
    )
    _write_json(phase9, {"counts": {"phase9_events": 0}})

    report = build_observer_report(
        telemetry_path=telemetry,
        warehouse_summary_path=warehouse,
        phase9_summary_path=phase9,
    )

    assert report["promotion_grade"] is False
    assert report["verdict"] == "not_promotion_grade"
    assert "no_first_class_strategy_events" in report["blockers"]
    assert "no_phase9_forward_events" in report["blockers"]


def test_platform_truth_observer_identifies_first_class_event() -> None:
    row = {
        "signal_id": "sig-1",
        "strategy_id": "etf_intraday_momentum",
        "engine_version": "v1",
        "created_at": "2026-05-10T14:00:00Z",
        "evidence_tier": 0,
        "shadow_only": True,
        "git_sha": "abc123",
        "runtime_config_hash": "cfg123",
    }

    assert is_first_class_event(row)
