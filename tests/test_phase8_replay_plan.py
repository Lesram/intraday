import json

from scripts.phase8_replay_plan import build_replay_plan, load_candidates, write_outputs


def test_phase8_replay_plan_generates_symbol_commands(tmp_path) -> None:
    plan = build_replay_plan(
        [
            {
                "candidate_id": "symbol:AMD",
                "candidate_type": "symbol",
                "symbol": "AMD",
                "reason": "forward_and_realized_symbol_evidence_aligned_positive",
                "joined_outcomes": 48,
                "positive_directional_rate": 0.5625,
                "avg_forward_directional_bps": 0.8986,
                "realized_rows": 37,
                "realized_total_pnl": 22.9207,
                "avg_realized_return_bps": 6.2912,
                "promotion_authorized": 0,
                "required_next_step": "replay_before_any_live_change",
            }
        ],
        tmp_path / "out",
    )

    assert plan["candidate_count"] == 1
    assert plan["promotion_authorized"] is False
    assert plan["plan_items"][0]["promotion_authorized"] is False
    assert "phase3_timeframe_scout.py --symbols AMD" in plan["plan_items"][0]["commands"][0]
    assert "phase4_shadow_target_model.py --symbols AMD" in plan["plan_items"][0]["commands"][1]


def test_phase8_replay_plan_generates_filter_commands(tmp_path) -> None:
    plan = build_replay_plan(
        [
            {
                "candidate_id": "filter:alpha_breakout_chop_or_trending_down",
                "candidate_type": "filter",
                "filter_tag": "alpha_breakout_chop_or_trending_down",
                "reason": "filter_forward_returns_pass_research_gate",
                "joined_outcomes": 48,
                "positive_directional_rate": 0.5625,
                "avg_forward_directional_bps": 2.8986,
                "promotion_authorized": 0,
                "required_next_step": "replay_before_any_live_change",
            }
        ],
        tmp_path / "out",
    )

    commands = plan["plan_items"][0]["commands"]
    assert commands == [
        (
            "./venv/bin/python scripts/phase3_candidate_filter_replay.py "
            "--scenarios skip_alpha_breakout_chop_or_trending_down "
            f"--out-dir {tmp_path / 'out' / 'filter_alpha_breakout_chop_or_trending_down' / 'counterfactual'}"
        ),
        (
            "./venv/bin/python scripts/phase3_candidate_filter_fill_replay.py "
            "--scenarios candidate_alpha_breakout_chop_or_trending_down "
            f"--out-dir {tmp_path / 'out' / 'filter_alpha_breakout_chop_or_trending_down' / 'fill_path'}"
        ),
    ]


def test_phase8_replay_plan_skips_promoted_or_unreviewed_candidates(tmp_path) -> None:
    plan = build_replay_plan(
        [
            {
                "candidate_id": "symbol:BAD",
                "candidate_type": "symbol",
                "symbol": "BAD",
                "promotion_authorized": 1,
                "required_next_step": "replay_before_any_live_change",
            },
            {
                "candidate_id": "symbol:WAIT",
                "candidate_type": "symbol",
                "symbol": "WAIT",
                "promotion_authorized": 0,
                "required_next_step": "collect_more_evidence",
            },
        ],
        tmp_path / "out",
    )

    assert plan["candidate_count"] == 0


def test_phase8_replay_plan_loads_and_writes_outputs(tmp_path) -> None:
    candidates = tmp_path / "candidates.json"
    candidates.write_text("[]\n")
    out_dir = tmp_path / "out"

    plan = build_replay_plan(load_candidates(candidates), out_dir)
    write_outputs(plan, out_dir)

    assert json.loads((out_dir / "replay_plan.json").read_text())["candidate_count"] == 0
    assert (out_dir / "PHASE8_REPLAY_PLAN.md").exists()
