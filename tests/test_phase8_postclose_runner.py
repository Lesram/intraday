from scripts.ci.run_phase8_postclose_evidence import validate_postclose_summary


def _summary():
    return {
        "promotion_authorized": False,
        "counts": {
            "db_orders": 10,
            "db_executions": 10,
            "db_realized_trades": 5,
        },
        "db_extract": {
            "research_summaries": {
                "promotion_authorized_rows": 0,
                "replay_candidate_count": 1,
            },
            "research_outputs": {
                "post_close_verdict": "no_live_promotion_replay_required",
                "replay_candidates": [
                    {
                        "candidate_id": "symbol:AMD",
                        "promotion_authorized": 0,
                        "required_next_step": "replay_before_any_live_change",
                    }
                ],
            },
        },
    }


def test_phase8_postclose_summary_accepts_replay_only_candidate() -> None:
    assert validate_postclose_summary(_summary(), require_db=True) == []


def test_phase8_postclose_summary_rejects_promotion_and_missing_db() -> None:
    summary = _summary()
    summary["promotion_authorized"] = True
    summary["counts"]["db_orders"] = 0
    summary["db_extract"]["research_outputs"]["replay_candidates"][0][
        "promotion_authorized"
    ] = 1

    errors = validate_postclose_summary(summary, require_db=True)

    assert "top-level promotion_authorized must be false" in errors
    assert "db_orders must be non-zero when --require-db is set" in errors
    assert "symbol:AMD authorized promotion" in errors
