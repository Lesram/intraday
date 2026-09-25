"""Paired synthetic mechanics, not a strategy profitability acceptance test."""
from __future__ import annotations

import asyncio
import json

import pandas as pd
import pytest

from scripts.diagnostics import replay_composite_correction as replay


def test_exact_prior_helper_restored_after_failure():
    from backend.organism import composite_indicators

    current = composite_indicators._safe_div
    with pytest.raises(AttributeError), replay.computation_arm("baseline"):
        composite_indicators._safe_div(100, pd.Series([1.0, 2.0]))
    assert composite_indicators._safe_div is current
    assert current(100, pd.Series([1.0, 2.0])).tolist() == [100, 50]


def test_offline_mode_rejects_credentials_and_missing_guard(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "synthetic-replay-refusal-case")
    with pytest.raises(ValueError, match="refuses broker credentials"):
        replay.require_offline()
    monkeypatch.delenv("ALPACA_API_KEY_ID")
    monkeypatch.setenv("TESTING", "false")
    with pytest.raises(ValueError, match="isolated testing"):
        replay.require_offline()


def test_prefix_fixture_rejects_unknown_or_sliding_input():
    raw = pd.DataFrame({"close": range(280)})
    compute = replay.prefix_compute({"AAPL": raw}, {"AAPL": raw}, [])
    with pytest.raises(ValueError, match="Unknown, mutated or sliding"):
        compute(raw.iloc[1:202].reset_index(drop=True), bars_per_day=390)
    with pytest.raises(ValueError, match="Unsupported"):
        compute(raw.iloc[:201], bars_per_day=1)


@pytest.fixture(scope="module")
def paired_result():
    result = asyncio.run(replay.evaluate())
    output = replay.ROOT / "artifacts/composite_indicator_repair/replay/paired_summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return result


@pytest.mark.timeout(300)
@pytest.mark.parametrize("scenario", replay.SCENARIOS)
def test_equal_inputs_causal_features_and_deterministic_real_replays(paired_result, scenario, record_property):
    pair = paired_result["scenarios"][scenario]
    assert pair["noncomposite_features_identical"]
    for arm in ("baseline", "corrected"):
        row = pair[arm]
        assert row["repeat_equal"]
        assert row["deterministic_outcome_sha256"] == row["repeat_outcome_sha256"]
        assert len(row["feature_proof"]["direct_prefix_checks"]) == 9
        assert row["feature_proof"]["future_tail_invariant"]
        counts = row["feature_proof"]["nonzero_composite_cells_in_executed_bars"]
        if arm == "baseline":
            assert sum(sum(v.values()) for v in counts.values()) == 0
        else:
            assert all(all(value > 0 for value in v.values()) for v in counts.values())
        assert row["metrics"]["ticks"] == (35 if scenario == "eod" else 60)
        assert row["metrics"]["tick_errors"] == row["metrics"]["accounting_pending"] == 0
        assert all(row["safety"].values())
        record_property(arm + "_metrics", json.dumps(row["metrics"], sort_keys=True))
    assert pair["baseline"]["feature_proof"]["computed_feature_sha256"] != pair["corrected"]["feature_proof"]["computed_feature_sha256"]


@pytest.mark.timeout(300)
def test_corrected_actual_orders_protective_exit_and_eod_accounting(paired_result):
    scenarios = paired_result["scenarios"]
    assert sum(row["corrected"]["metrics"]["entry_orders"] for row in scenarios.values()) > 0
    crash = scenarios["crash"]["corrected"]
    assert crash["metrics"]["entry_orders"] > 0
    assert any(t["pnl"] < 0 and pd.Timestamp(t["closed_at"]) >= pd.Timestamp("2026-09-22T14:40:00Z")
               and (t["exit_reason"] in {"stop_loss", "max_loss_limit"}
                    or t["exit_reason"].startswith("pyramid_cut_full"))
               for t in crash["normalized_outcome"]["accounted_trades"])
    eod = scenarios["eod"]["corrected"]
    assert eod["metrics"]["entry_orders"] > 0
    assert eod["metrics"]["exit_mix"].get("eod_flatten", 0) > 0
    assert eod["metrics"]["final_open_positions"] == 0
    assert all(pd.Timestamp(o["submitted_at"]) < pd.Timestamp("2026-09-22T19:58:00Z")
               for o in eod["normalized_outcome"]["orders"] if o["side"] == "buy")


@pytest.mark.parametrize("mutation", ["duplicate", "client", "symbol", "shares", "age", "missing"])
def test_entry_receipt_join_refuses_misbound_proof(mutation):
    orders = [{"side": "buy", "order_id": "one", "idempotency_key": "client-one",
               "symbol": "AAPL", "qty": "2", "filled_qty": "2"}]
    receipt = {"entry_order_id": "one", "client_order_id": "client-one", "symbol": "AAPL",
               "shares": 2, "gate_passed": True, "timestamp_complete": True,
               "timestamp_ordered": True, "bar_age_seconds": 0}
    replay.validate_entry_receipts(orders, [receipt])
    bad = [dict(receipt)]
    if mutation == "duplicate":
        orders = [*orders, {**orders[0], "order_id": "two", "idempotency_key": "client-two"}]
        bad.append(dict(receipt))
    elif mutation == "missing":
        bad = []
    else:
        field, value = {"client": ("client_order_id", "different"),
                        "symbol": ("symbol", "MSFT"), "shares": ("shares", 3),
                        "age": ("bar_age_seconds", 121)}[mutation]
        bad[0][field] = value
    with pytest.raises(AssertionError):
        replay.validate_entry_receipts(orders, bad)


def test_drawdown_includes_loss_on_first_fill_tick():
    assert replay.drawdown_from_initial([999_000, 1_000_000, 999_500]) == pytest.approx(.001)
