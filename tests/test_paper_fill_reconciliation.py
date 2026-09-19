"""Read-only research reconciliation: identities, scale-outs and unsafe inputs."""
from __future__ import annotations

import copy
import json

import pytest

from scripts.research.paper_fill_reconciliation import main, reconcile, write_report

FREEZE = "2026-07-07T20:36:49+00:00"


def order(ref, side, qty, price, time, *, symbol="TSLA", bucket="organism"):
    return {"order_ref": ref, "bucket": bucket, "symbol": symbol, "side": side,
            "filled_qty": str(qty), "filled_avg_price": str(price), "filled_at": time}


def trade(pnl, *, symbol="TSLA", qty=6, entry=321, partial=False,
          close="2026-08-03T16:31:25+00:00"):
    return {"symbol": symbol, "closed_at": close, "shares": str(qty),
            "entry_price": str(entry), "pnl": str(pnl), "had_partial_exits": str(partial)}


def scale_out():
    # Actual August-3 numerical counterexample, without broker identifiers.
    return [order("buy", "buy", 6, 321, "2026-08-03T14:54:12Z"),
            order("ml-reversal", "sell", 1, 322.73, "2026-08-03T15:48:06Z"),
            order("final", "sell", 5, 321.81, "2026-08-03T16:31:11Z")]


def test_partial_cashflows_expose_real_ledger_error_without_changing_inputs():
    orders, ledger = scale_out(), [trade(4.86)]
    before = copy.deepcopy((orders, ledger))
    result = reconcile(orders, ledger, FREEZE)
    assert result["status"] == "DISCREPANCY"
    assert result["gross"] == {"broker_pnl": 5.78, "ledger_pnl": 4.86,
                               "ledger_minus_broker": -0.92}
    assert result["counts"]["partial_flag_differences"] == 1
    assert result["cost_scenarios"]["3_bps_round_trip"]["broker_modeled_net"] == 5.2022
    assert result["cost_scenarios"]["6_bps_round_trip"]["broker_modeled_net"] == 4.6244
    assert (orders, ledger) == before


def test_correct_partial_ledger_reconciles():
    result = reconcile(scale_out(), [trade(5.78, partial=True)], FREEZE)
    assert result["status"] == "RECONCILED"
    assert result["matches"][0]["broker_average_exit"] == pytest.approx(321.963333)


def test_wrong_entry_cost_basis_cannot_reconcile_despite_correct_quantity_and_pnl():
    orders, ledger = scale_out(), [trade(5.78, entry=300, partial=True)]
    before = copy.deepcopy((orders, ledger))
    result = reconcile(orders, ledger, FREEZE)
    assert result["status"] == "DISCREPANCY"
    assert result["gross"]["ledger_minus_broker"] == 0
    assert result["counts"]["entry_price_differences_over_tolerance"] == 1
    assert result["matches"][0]["entry_price_matches"] is False
    assert result["matches"][0]["entry_notional_delta"] == -126
    costs = result["cost_scenarios"]["3_bps_round_trip"]
    assert costs["ledger_modeled_net"] != costs["broker_modeled_net"]
    assert (orders, ledger) == before


@pytest.mark.parametrize("entry,status", [("321.00005", "RECONCILED"),
                                          ("320.99995", "RECONCILED"),
                                          ("321.000051", "DISCREPANCY")])
def test_entry_price_tolerance_allows_only_four_decimal_rounding(entry, status):
    result = reconcile(scale_out(), [trade(5.78, entry=entry, partial=True)], FREEZE)
    assert result["status"] == status
    assert result["entry_price_tolerance"]["absolute_usd_per_share"] == "0.00005"
    assert result["matches"][0]["entry_price_matches"] == (status == "RECONCILED")


def test_fractional_shares_and_raw_export_do_not_leak_identifiers():
    orders = [order("b", "buy", ".25", 100, "2026-08-03T15:00:00Z"),
              order("s", "sell", ".25", 101, "2026-08-03T16:31:11Z")]
    for item in orders:
        item["id"] = "sensitive-broker-id-" + item.pop("order_ref")
        item["client_order_id"] = "organism_private-session-id"
        item.pop("bucket")
    result = reconcile(orders, [trade(".25", qty=".25", entry=100)], FREEZE)
    assert result["status"] == "RECONCILED"
    assert result["gross"]["broker_pnl"] == .25
    assert "sensitive-broker-id" not in json.dumps(result)
    assert "private-session-id" not in json.dumps(result)


@pytest.mark.parametrize("kind", ["duplicate", "other", "missing_fill", "open", "short"])
def test_incomplete_broker_evidence_never_reconciles(kind):
    orders = scale_out()
    if kind == "duplicate":
        orders.append(copy.deepcopy(orders[-1]))
    elif kind == "other":
        orders[1]["bucket"] = "manual"
    elif kind == "missing_fill":
        orders = orders[1:]
    elif kind == "open":
        orders.pop()
    else:
        orders[0]["side"] = "sell"
    result = reconcile(orders, [trade(5.78, partial=True)], FREEZE)
    assert result["status"] == "INCOMPLETE"
    assert result["issues"]


def test_unfilled_orders_are_not_realized_cashflows():
    orders = scale_out() + [{"filled_qty": "0", "status": "canceled"}]
    result = reconcile(orders, [trade(5.78, partial=True)], FREEZE)
    assert result["status"] == "RECONCILED"
    assert result["counts"]["ignored_unfilled_orders"] == 1


def test_same_symbol_roundtrips_stay_separate():
    orders = [order("b1", "buy", 1, 100, "2026-08-03T14:00:00Z"),
              order("s1", "sell", 1, 102, "2026-08-03T15:00:00Z"),
              order("b2", "buy", 1, 100, "2026-08-03T16:00:00Z"),
              order("s2", "sell", 1, 99, "2026-08-03T17:00:00Z")]
    ledger = [trade(2, qty=1, entry=100, close="2026-08-03T15:00:20Z"),
              trade(-1, qty=1, entry=100, close="2026-08-03T17:00:20Z")]
    result = reconcile(orders, ledger, FREEZE)
    assert result["status"] == "RECONCILED"
    assert [m["broker_pnl"] for m in result["matches"]] == [2, -1]


def test_duplicate_ledger_row_cannot_match_same_broker_cycle_twice():
    result = reconcile(scale_out(), [trade(5.78, partial=True)] * 2, FREEZE)
    assert result["status"] == "INCOMPLETE"
    assert result["counts"]["matched_closes"] == 1


def test_close_matching_refuses_ambiguous_nearby_roundtrips():
    orders = [order("b1", "buy", 1, 100, "2026-08-03T14:00:00Z"),
              order("s1", "sell", 1, 102, "2026-08-03T15:00:00Z"),
              order("b2", "buy", 1, 100, "2026-08-03T15:00:10Z"),
              order("s2", "sell", 1, 99, "2026-08-03T15:00:30Z")]
    result = reconcile(orders, [trade(2, qty=1, entry=100, close="2026-08-03T15:00:20Z")],
                       FREEZE)
    assert result["status"] == "INCOMPLETE"
    assert result["counts"]["matched_closes"] == 0


@pytest.mark.parametrize("field,value", [("filled_qty", "NaN"), ("filled_avg_price", "inf"),
                                         ("filled_at", "2026-08-03T16:31:11")])
def test_invalid_numeric_or_timezone_fields_block_reconciliation(field, value):
    orders = scale_out()
    orders[-1][field] = value
    result = reconcile(orders, [trade(5.78, partial=True)], FREEZE)
    assert result["status"] == "INCOMPLETE"


def test_prefreeze_entry_is_reported_as_unknown_carry_in_not_free_profit():
    orders = [order("b", "buy", 6, 321, "2026-07-07T20:00:00Z"),
              order("s", "sell", 6, 322, "2026-08-03T16:31:11Z")]
    result = reconcile(orders, [trade(6)], FREEZE)
    assert result["status"] == "INCOMPLETE"
    assert any(i["kind"] == "unmatched_sell_or_carry_in" for i in result["issues"])


def test_empty_inputs_do_not_count_as_a_pass():
    assert reconcile([], [], FREEZE)["status"] == "INCOMPLETE"


def test_output_cannot_overwrite_brain_or_input_even_through_symlink(tmp_path):
    brain = tmp_path / "organism_brain"
    brain.mkdir()
    source = brain / "trade_history.csv"
    source.write_text("original\n")
    link = tmp_path / "report.json"
    link.symlink_to(source)
    for output in (source, brain / "new.json", link):
        with pytest.raises(ValueError):
            write_report(output, {}, [])
    other_input = tmp_path / "orders.json"
    other_input.write_text("[]")
    with pytest.raises(ValueError):
        write_report(other_input, {}, [other_input])
    hardlink = tmp_path / "hardlink.json"
    hardlink.hardlink_to(source)
    with pytest.raises(ValueError):
        write_report(hardlink, {}, [source])
    assert source.read_text() == "original\n"


def test_cli_writes_separate_report_and_nonzero_for_discrepancy(tmp_path):
    orders = tmp_path / "orders.json"
    orders.write_text(json.dumps({"orders": scale_out()}))
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("symbol,closed_at,shares,entry_price,pnl,had_partial_exits\n"
                      "TSLA,2026-08-03T16:31:25Z,6,321,4.86,False\n")
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({"FROZEN_AT": FREEZE}))
    output = tmp_path / "report.json"
    paths = [orders, ledger, freeze]
    before = [p.read_bytes() for p in paths]
    assert main(["--orders", str(orders), "--ledger", str(ledger), "--freeze", str(freeze),
                 "--output", str(output)]) == 1
    result = json.loads(output.read_text())
    assert result["gross"]["ledger_minus_broker"] == -.92
    assert set(result["input_sha256"]) == {"orders", "ledger", "freeze"}
    assert [p.read_bytes() for p in paths] == before
