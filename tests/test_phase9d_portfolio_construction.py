from __future__ import annotations

import json
from pathlib import Path


def _eligible_row(strategy_id: str, *, family: str | None = None) -> dict:
    return {
        "strategy_id": strategy_id,
        "strategy_family": family,
        "verdict": "micro_paper_eligible",
        "n": 140,
        "profit_factor": 1.45,
        "avg_r": 0.18,
        "avg_alpha_over_symbol_hold_bps": 4.0,
        "avg_alpha_over_random_bps": 3.0,
        "avg_alpha_over_delay_bps": 2.5,
        "max_symbol_concentration": 0.18,
        "max_session_concentration": 0.16,
        "max_drawdown": -8.0,
    }


def test_phase9d_blocks_replay_only_rows_from_portfolio_scaling() -> None:
    from backend.organism.evidence.portfolio_construction import (
        construct_strategy_portfolio,
    )

    row = _eligible_row("etf_intraday_momentum")
    row["verdict"] = "replay_eligible"

    report = construct_strategy_portfolio([row])

    assert report["portfolio_authorized"] is False
    assert report["promotion_authorized"] is False
    assert report["counts"]["allocations"] == 0
    candidate = report["candidates"][0]
    assert "replay_only_not_portfolio_eligible" in candidate["blockers"]
    assert "not_enough_validated_strategies" in report["portfolio_blockers"]


def test_phase9d_requires_multiple_independent_strategy_families() -> None:
    from backend.organism.evidence.portfolio_construction import (
        construct_strategy_portfolio,
    )

    rows = [
        _eligible_row("etf_intraday_momentum"),
        _eligible_row("gamma_flow_momentum"),
    ]

    report = construct_strategy_portfolio(rows)

    assert report["portfolio_authorized"] is False
    assert report["counts"]["eligible_strategies"] == 2
    assert report["counts"]["eligible_families"] == 1
    assert "not_enough_independent_strategy_families" in report["portfolio_blockers"]
    assert report["allocations"] == []


def test_phase9d_allocates_only_after_evidence_beta_and_family_controls_pass() -> None:
    from backend.organism.evidence.portfolio_construction import (
        construct_strategy_portfolio,
    )

    rows = [
        _eligible_row("etf_intraday_momentum"),
        _eligible_row("residual_mean_reversion"),
    ]

    report = construct_strategy_portfolio(
        rows,
        betas={"etf_intraday_momentum": 0.20, "residual_mean_reversion": -0.10},
        correlations={"etf_intraday_momentum:residual_mean_reversion": 0.25},
    )

    assert report["portfolio_authorized"] is True
    assert report["live_behavior"] == "unchanged"
    assert report["promotion_authorized"] is False
    assert report["counts"]["allocations"] == 2
    assert report["allocated_risk_budget_bps"] <= 25.0
    assert report["controls"]["beta"]["status"] == "pass"
    assert {row["strategy_id"] for row in report["allocations"]} == {
        "etf_intraday_momentum",
        "residual_mean_reversion",
    }


def test_phase9d_correlation_cut_removes_lower_quality_strategy() -> None:
    from backend.organism.evidence.portfolio_construction import (
        construct_strategy_portfolio,
    )

    strong = _eligible_row("etf_intraday_momentum")
    weak = _eligible_row("orb_sip_v2")
    weak["avg_alpha_over_symbol_hold_bps"] = 1.0
    weak["avg_alpha_over_random_bps"] = 0.5
    weak["avg_alpha_over_delay_bps"] = 0.5

    report = construct_strategy_portfolio(
        [strong, weak],
        correlations={"etf_intraday_momentum:orb_sip_v2": 0.92},
    )

    orb = {
        candidate["strategy_id"]: candidate
        for candidate in report["candidates"]
    }["orb_sip_v2"]
    assert any(
        blocker.startswith("pairwise_correlation_exceeds_limit")
        for blocker in orb["blockers"]
    )
    assert report["portfolio_authorized"] is False
    assert report["allocations"] == []


def test_phase9d_report_writer_is_advisory_only(tmp_path: Path) -> None:
    from scripts.phase9d_portfolio_construction import (
        build_phase9d_report,
        write_outputs,
    )

    league_path = tmp_path / "league.json"
    league_path.write_text(json.dumps([_eligible_row("etf_intraday_momentum")]))

    payload = build_phase9d_report(league_path=league_path)
    outputs = write_outputs(payload, tmp_path / "out")

    assert payload["live_promotion_authorized"] is False
    assert payload["live_behavior"] == "unchanged"
    assert payload["required_next_step"] == "collect_and_validate_more_strategy_families"
    assert Path(outputs["summary"]).exists()
    assert Path(outputs["report"]).read_text().startswith(
        "# Phase 9D Portfolio Construction Report"
    )
