"""Broker ground-truth reconciliation (measurement-integrity audit 2026-06-11).

THE finding that motivates this script: the Alpaca paper account went
100,000 → 111,525 (+$11.5k) while the organism's trade_history.csv sums to
−$633. Account equity and the audited strategy book are NOT the same thing
— at least two execution paths (the organism and the multi-strategy
scheduler) share this account, plus unrealized open-position value.

This script attributes every dollar, using the broker as ground truth:

1. Pulls account equity + all closed orders from Alpaca paper.
2. Classifies orders by client_order_id prefix:
     organism_*        → the audited organism book
     everything else   → multi-strategy runner / manual / unknown
3. Computes realized PnL per bucket (FIFO matching per symbol+side).
4. Reconciles: organism-bucket broker PnL vs trade_history.csv sum —
   any residual beyond open-position unrealized PnL is unexplained and
   must be investigated before trusting per-trade records.

Run ON THE HOST (needs Alpaca API access + .env credentials):

    cd ~/VS/intra && source venv/bin/activate  # or your env
    python scripts/reconcile_broker.py

Read-only: makes no orders, no account changes.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    _load_env()
    import pandas as pd
    import requests

    key = os.environ.get("ALPACA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY")
    sec = (os.environ.get("ALPACA_API_SECRET_KEY")
           or os.environ.get("ALPACA_SECRET_KEY"))
    if not key or not sec:
        sys.exit("Alpaca credentials not found in environment/.env")
    base = "https://paper-api.alpaca.markets"
    H = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec}

    acct = requests.get(f"{base}/v2/account", headers=H, timeout=30).json()
    positions = requests.get(f"{base}/v2/positions", headers=H, timeout=30).json()

    # Page through ALL closed orders.
    orders, until = [], None
    while True:
        params = {"status": "closed", "limit": 500, "direction": "desc"}
        if until:
            params["until"] = until
        page = requests.get(f"{base}/v2/orders", headers=H,
                            params=params, timeout=30).json()
        if not isinstance(page, list) or not page:
            break
        orders.extend(page)
        until = page[-1]["submitted_at"]
        if len(page) < 500:
            break

    filled = [o for o in orders if o.get("filled_qty") and
              float(o["filled_qty"]) > 0]

    def bucket(o) -> str:
        cid = str(o.get("client_order_id") or "")
        if cid.startswith("organism_exit"):
            return "organism"
        if cid.startswith("organism"):
            return "organism"
        return "other"

    # FIFO realized PnL per bucket.
    realized = {"organism": 0.0, "other": 0.0}
    lots: dict[tuple[str, str], deque] = defaultdict(deque)  # (bucket,sym)
    n_orders = {"organism": 0, "other": 0}
    for o in sorted(filled, key=lambda x: x.get("filled_at") or
                    x.get("submitted_at") or ""):
        b = bucket(o)
        n_orders[b] += 1
        sym = o["symbol"]
        qty = float(o["filled_qty"])
        px = float(o.get("filled_avg_price") or 0)
        if px <= 0:
            continue
        q = lots[(b, sym)]
        if o["side"] == "buy":
            q.append([qty, px])
        else:  # sell — match FIFO against buys
            rem = qty
            while rem > 1e-9 and q:
                lot_qty, lot_px = q[0]
                take = min(rem, lot_qty)
                realized[b] += (px - lot_px) * take
                lot_qty -= take
                rem -= take
                if lot_qty <= 1e-9:
                    q.popleft()
                else:
                    q[0][0] = lot_qty

    unrealized = sum(float(p.get("unrealized_pl") or 0) for p in positions)
    equity = float(acct.get("equity") or 0)

    csv_path = ROOT / "organism_brain" / "trade_history.csv"
    df = pd.read_csv(csv_path)
    book_all = df["pnl"].sum()
    book_strategy = df.loc[
        ~df["is_reconciliation_artifact"].astype(bool), "pnl"
    ].sum()

    organism_gap = realized["organism"] - book_all

    # Self-consistency check (added after first run, 2026-06-11): on a
    # SHARED account where multiple execution paths trade the SAME symbols,
    # per-bucket FIFO mis-attributes (one path's sell can close the other
    # path's shares; each bucket then "realizes" PnL on the same underlying
    # position). If the buckets + unrealized don't sum to the equity change,
    # the per-bucket numbers must NOT be trusted as attribution — only the
    # account-level total is real.
    attributed = realized["organism"] + realized["other"] + unrealized
    equity_change = equity - 100_000.0  # curve baseline 2026-03-08
    attribution_consistent = abs(attributed - equity_change) < 100

    report = {
        "attribution_self_consistency": {
            "sum_of_buckets_plus_unrealized": round(attributed, 2),
            "account_equity_change_vs_100k_baseline": round(equity_change, 2),
            "consistent": attribution_consistent,
            "warning": (
                None if attribution_consistent else
                "Bucketed attribution does NOT reconcile with the account "
                "total — shared-account symbol overlap (and/or paper-account "
                "resets) breaks per-bucket FIFO. Treat ONLY the account-level "
                "total as ground truth; per-bucket numbers are indicative at "
                "best."
            ),
        },
        "account_equity": equity,
        "unrealized_open_pnl": round(unrealized, 2),
        "open_positions": len(positions),
        "broker_realized_pnl": {
            "organism_orders": round(realized["organism"], 2),
            "other_orders (multi-strategy/manual)": round(realized["other"], 2),
        },
        "order_counts": n_orders,
        "trade_history_book": {
            "all_rows": round(book_all, 2),
            "strategy_rows_only": round(book_strategy, 2),
        },
        "RECONCILIATION": {
            "organism broker-realized vs book (should be ~0)": round(
                organism_gap, 2
            ),
            "verdict": (
                "RECONCILED" if abs(organism_gap) < 50 else
                "DIVERGED — per-trade records do not match broker reality; "
                "investigate partial-exit accounting and fallback-priced rows"
            ),
        },
        "attribution_note": (
            "Account equity change splits into: organism realized + other-path "
            "realized + unrealized open PnL. Only the organism slice is the "
            "audited strategy book — never judge the strategy by account "
            "equity alone."
        ),
    }
    out = ROOT / "artifacts" / "broker_reconciliation.json"
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
