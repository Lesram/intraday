"""Offline paper-fill reconciliation; never imports or writes platform state.

Inputs are a saved Alpaca order export (list, or {"orders": [...]}) and the
organism CSV. Sanitized exports may use order_ref/bucket instead of broker IDs.
The report reconstructs long-only, flat-to-flat cash flows, including scale-outs.
It does not replace the frozen corpus or select a cost assumption for trading.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.organism.freeze_contract import validate_active_freeze

# The persisted ledger rounds entry_price to four decimal places. Compare the
# unrounded Decimal VWAP at half that quantum, not a relative price tolerance.
ENTRY_PRICE_TOLERANCE = Decimal("0.00005")


def timestamp(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return result.astimezone(timezone.utc)


def amount(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("invalid numeric field") from exc
    if not result.is_finite():
        raise ValueError("nonfinite numeric field")
    return result


def number(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001")))


def reconcile(
    orders: list[dict], ledger: list[dict], frozen_at: str,
    *, close_tolerance_seconds: int = 180,
) -> dict:
    """Compare supplied evidence without querying a broker or mutating inputs.

    Missing/ambiguous identities, unassigned activity and incomplete positions
    prevent a RECONCILED result. Duplicate orders are flagged and counted once.
    Prices are per-order filled averages: broker fees are not represented here.
    """
    cutoff = timestamp(frozen_at)
    issues: list[dict] = []
    fills: list[dict] = []
    seen: set[str] = set()
    ignored_unfilled = 0
    for index, order in enumerate(orders):
        try:
            qty = amount(order.get("filled_qty", 0))
            if qty == 0:
                ignored_unfilled += 1
                continue
            filled_at = timestamp(order["filled_at"])
            if filled_at <= cutoff:
                continue
            if qty < 0 or order.get("side") not in {"buy", "sell"}:
                raise ValueError("invalid quantity or side")
            price = amount(order["filled_avg_price"])
            if price <= 0:
                raise ValueError("invalid price")
            identifier = order.get("order_ref") or order.get("id")
            if not identifier or not order.get("symbol"):
                raise ValueError("missing identity")
            ref = hashlib.sha256(str(identifier).encode()).hexdigest()[:16]
            if ref in seen:
                issues.append({"kind": "duplicate_order", "order_ref": ref})
                continue
            seen.add(ref)
            bucket = order.get("bucket")
            if bucket is None:
                bucket = ("organism" if str(order.get("client_order_id", ""))
                          .startswith("organism") else "other")
            if bucket != "organism":
                issues.append({"kind": "unattributed_filled_order", "order_ref": ref})
                continue
            fills.append({"symbol": order["symbol"], "side": order["side"],
                          "qty": qty, "price": price, "time": filled_at,
                          "ref": ref})
        except (KeyError, ValueError, TypeError, AttributeError):
            issues.append({"kind": "invalid_filled_order", "input_index": index})

    positions: dict[str, dict] = {}
    cycles: list[dict] = []
    invalid_symbols: set[str] = set()
    for fill in sorted(fills, key=lambda row: (row["time"], row["ref"])):
        symbol = fill["symbol"]
        if symbol in invalid_symbols:
            continue
        position = positions.setdefault(symbol, {
            "symbol": symbol, "qty": Decimal(0), "buy_qty": Decimal(0),
            "sell_qty": Decimal(0), "buy_cash": Decimal(0),
            "sell_cash": Decimal(0), "buy_orders": 0, "sell_orders": 0,
            "first_fill": fill["time"], "order_refs": [],
        })
        side = fill["side"]
        position["qty"] += fill["qty"] if side == "buy" else -fill["qty"]
        position[side + "_qty"] += fill["qty"]
        position[side + "_cash"] += fill["qty"] * fill["price"]
        position[side + "_orders"] += 1
        position["order_refs"].append(fill["ref"])
        if position["qty"] < 0:
            issues.append({"kind": "unmatched_sell_or_carry_in", "symbol": symbol})
            invalid_symbols.add(symbol)
            positions.pop(symbol)
        elif position["qty"] == 0:
            position["last_fill"] = fill["time"]
            position["pnl"] = position["sell_cash"] - position["buy_cash"]
            cycles.append(position)
            positions.pop(symbol)
    for symbol, position in sorted(positions.items()):
        issues.append({"kind": "remaining_open_position", "symbol": symbol,
                       "qty": number(position["qty"])})

    forward: list[dict] = []
    missing_close = 0
    for index, row in enumerate(ledger):
        if not row.get("closed_at"):
            missing_close += 1
            continue
        try:
            closed_at = timestamp(row["closed_at"])
            if closed_at <= cutoff:
                continue
            qty, pnl = amount(row["shares"]), amount(row["pnl"])
            entry = amount(row["entry_price"])
            if qty <= 0 or entry <= 0 or not row.get("symbol"):
                raise ValueError("invalid ledger row")
            forward.append({"row": row, "close": closed_at, "qty": qty,
                            "pnl": pnl, "entry": entry, "index": index})
        except (KeyError, ValueError, TypeError, AttributeError):
            issues.append({"kind": "invalid_ledger_row", "input_index": index})

    matches = []
    used_cycles: set[int] = set()
    mismatch_count = 0
    partial_flag_mismatches = 0
    entry_price_mismatches = 0
    for trade in forward:
        row = trade["row"]
        candidates = [i for i, cycle in enumerate(cycles)
                      if cycle["symbol"] == row["symbol"] and
                      abs((trade["close"] - cycle["last_fill"]).total_seconds())
                      <= close_tolerance_seconds]
        if len(candidates) != 1 or candidates[0] in used_cycles:
            issues.append({"kind": "unmatched_or_ambiguous_ledger_close",
                           "symbol": row["symbol"], "closed_at": row["closed_at"],
                           "candidate_cycles": len(candidates)})
            continue
        cycle_index = candidates[0]
        used_cycles.add(cycle_index)
        cycle = cycles[cycle_index]
        delta = trade["pnl"] - cycle["pnl"]
        broker_entry = cycle["buy_cash"] / cycle["buy_qty"]
        entry_delta = trade["entry"] - broker_entry
        entry_matches = abs(entry_delta) <= ENTRY_PRICE_TOLERANCE
        if not entry_matches:
            entry_price_mismatches += 1
        if trade["qty"] != cycle["buy_qty"]:
            issues.append({"kind": "entry_quantity_mismatch", "symbol": row["symbol"],
                           "closed_at": row["closed_at"]})
        if abs(delta) > Decimal("0.01"):
            mismatch_count += 1
        partial = cycle["sell_orders"] > 1
        declared_partial = str(row.get("had_partial_exits", "")).lower() == "true"
        if partial != declared_partial:
            partial_flag_mismatches += 1
        matches.append({
            "symbol": row["symbol"], "closed_at": row["closed_at"],
            "broker_first_fill": cycle["first_fill"].isoformat(),
            "broker_last_fill": cycle["last_fill"].isoformat(),
            "broker_qty": number(cycle["buy_qty"]),
            "ledger_entry": number(trade["entry"]),
            "broker_average_entry": number(broker_entry),
            "entry_price_matches": entry_matches,
            "entry_price_delta_unrounded": str(entry_delta),
            "entry_notional_delta": number(trade["qty"] * trade["entry"]
                                           - cycle["buy_cash"]),
            "broker_average_exit": number(cycle["sell_cash"] / cycle["sell_qty"]),
            "ledger_pnl": number(trade["pnl"]), "broker_pnl": number(cycle["pnl"]),
            "ledger_minus_broker": number(delta),
            "sell_orders": cycle["sell_orders"],
            "ledger_partial_flag": declared_partial,
            "partial_flag_matches": declared_partial == partial,
            "order_refs": cycle["order_refs"],
        })
    for i, cycle in enumerate(cycles):
        if i not in used_cycles:
            issues.append({"kind": "broker_cycle_missing_from_ledger",
                           "symbol": cycle["symbol"],
                           "closed_at": cycle["last_fill"].isoformat()})
    if not cycles and not forward:
        issues.append({"kind": "no_forward_evidence"})

    broker_pnl = sum((cycle["pnl"] for cycle in cycles), Decimal(0))
    broker_notional = sum((cycle["buy_cash"] for cycle in cycles), Decimal(0))
    ledger_pnl = sum((trade["pnl"] for trade in forward), Decimal(0))
    ledger_notional = sum((trade["qty"] * trade["entry"] for trade in forward), Decimal(0))
    costs = {}
    for bps in (3, 6):
        rate = Decimal(bps) / 10000
        costs[str(bps) + "_bps_round_trip"] = {
            "broker_modeled_net": number(broker_pnl - broker_notional * rate),
            "ledger_modeled_net": number(ledger_pnl - ledger_notional * rate),
        }
    return {
        "schema": "paper_fill_reconciliation_v1", "frozen_at": frozen_at,
        "status": ("INCOMPLETE" if issues else "DISCREPANCY"
                   if mismatch_count or partial_flag_mismatches or entry_price_mismatches
                   else "RECONCILED"),
        "counts": {"organism_filled_orders": len(fills), "broker_cycles": len(cycles),
                   "forward_ledger_rows": len(forward), "matched_closes": len(matches),
                   "ignored_unfilled_orders": ignored_unfilled,
                   "ledger_rows_without_close_at": missing_close,
                   "pnl_differences_over_one_cent": mismatch_count,
                   "entry_price_differences_over_tolerance": entry_price_mismatches,
                   "partial_flag_differences": partial_flag_mismatches},
        "gross": {"broker_pnl": number(broker_pnl), "ledger_pnl": number(ledger_pnl),
                  "ledger_minus_broker": number(ledger_pnl - broker_pnl)},
        "cost_scenarios": costs, "issues": issues, "matches": matches,
        "entry_price_tolerance": {
            "absolute_usd_per_share": str(ENTRY_PRICE_TOLERANCE),
            "comparison": "inclusive; unrounded Decimal prices",
            "reason": "half the persisted ledger's four-decimal price quantum",
            "equivalent_notional_tolerance": "matched quantity times 0.00005 USD",
        },
        "limits": ["Saved order export only; completeness depends on export pagination and scope.",
                   "Long-only flat-to-flat cash flows; carry-in positions require earlier fills.",
                   "Per-order filled averages; broker fees are not included.",
                   "3 bps round trip is the declared runtime model; 6 is research-brief sensitivity.",
                   "Neither modeled scenario changes runtime configuration or the frozen corpus.",
                   "No strategy significance statistic, promotion decision or execution test."],
    }


def write_report(output: Path, report: dict, inputs: list[Path]) -> None:
    resolved = output.resolve()
    aliases_input = resolved in {p.resolve() for p in inputs}
    if resolved.exists():
        aliases_input |= any(p.exists() and resolved.samefile(p) for p in inputs)
    if "organism_brain" in resolved.parts or aliases_input:
        raise ValueError("output must not overwrite brain state or an input")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(report, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orders", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        inputs = [args.orders, args.ledger, args.freeze]
        # A candidate validation boundary must not select or hide forward rows.
        # Validate before reading broker/ledger inputs, and hash these same bytes.
        freeze_raw = args.freeze.read_bytes()
        freeze = validate_active_freeze(json.loads(freeze_raw))
        # Hash the bytes actually analyzed, even if a live atomic save replaces
        # the source path while this report is being computed.
        data = [args.orders.read_bytes(), args.ledger.read_bytes(), freeze_raw]
        payload = json.loads(data[0])
        orders = payload["orders"] if isinstance(payload, dict) else payload
        if not isinstance(orders, list) or not all(isinstance(o, dict) for o in orders):
            raise ValueError("orders must be a list of objects")
        ledger = list(csv.DictReader(io.StringIO(data[1].decode("utf-8-sig"))))
        report = reconcile(orders, ledger, freeze["FROZEN_AT"])
        report["input_sha256"] = {name: hashlib.sha256(content).hexdigest()
                                  for name, content in zip(("orders", "ledger", "freeze"), data)}
        write_report(args.output, report, inputs)
    except (OSError, ValueError, KeyError, TypeError):
        # Do not echo malformed input payloads, which can contain credentials.
        print("Input/output validation failed; no platform state was changed.")
        return 2
    print(json.dumps({"status": report["status"], "counts": report["counts"],
                      "gross": report["gross"], "output": str(args.output)}))
    return 0 if report["status"] == "RECONCILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
