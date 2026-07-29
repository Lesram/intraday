from __future__ import annotations

import json


def test_phase9_preopen_evidence_readiness_smoke(tmp_path):
    from scripts.ci.phase9_preopen_evidence_readiness import build_readiness_report

    report = build_readiness_report(out_dir=tmp_path)

    assert report["ready"] is True
    assert report["promotion_evidence"] is False
    assert report["production_telemetry_mutated"] is False
    assert set(report["signals_by_strategy"]) == {
        "eod_reversal_shadow",
        "etf_intraday_momentum",
        "orb_sip_v2",
        "residual_mean_reversion",
    }

    rows = [
        json.loads(line)
        for line in (tmp_path / "synthetic_strategy_evidence_events.jsonl")
        .read_text()
        .splitlines()
    ]
    assert rows
    assert all(row["shadow_only"] is True for row in rows)
    assert all("phase9_shadow" in row["matched_filters"] for row in rows)
