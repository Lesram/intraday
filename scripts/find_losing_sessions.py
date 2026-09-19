#!/usr/bin/env python3
"""Summarize the live book's P&L by session and surface a representative window
for re-running the exit-logic experiment.

Context: the Tier-2 replay (2026-06-20) ran on the only cached bars available
(artifacts/**/bars*.pkl ≈ Apr 15–30) — 8 days, 34 trades, where the *current*
engine nets +$160. That is too small and not representative. This script reports
where the live book actually lost.

IMPORTANT DATA CAVEAT this script exposes: a large share of trades have a BLANK
`closed_at` and cannot be dated from this file (they are also the bulk of the
losses). So per-day targeting is only partial. Combined with the fact that the
replay re-runs the CURRENT engine code (it will not reproduce the historical
live losses), the right move is to test exit policies over a BROAD, multi-month
bar corpus (>=60 sessions), not just the 8-day April slice.

Outputs:
  - summary + per-day P&L for the DATED trades (stdout)
  - artifacts/losing_sessions.json

Run from repo root with the project venv:
    ./venv/bin/python scripts/find_losing_sessions.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "organism_brain" / "trade_history.csv"


def main() -> None:
    df = pd.read_csv(CSV)
    if "is_reconciliation_artifact" in df.columns:
        df = df[~df["is_reconciliation_artifact"].astype(str).str.lower().isin(["true", "1"])]
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce")
    df = df.dropna(subset=["pnl"]).copy()

    total_net = float(df["pnl"].sum())
    et = pd.to_datetime(df["closed_at"], errors="coerce", utc=True).dt.tz_convert("America/New_York")
    df["date"] = et.dt.date
    undated = df["date"].isna()

    print(f"clean trades = {len(df)}   TOTAL net = ${total_net:.2f}")
    print(
        f"UNDATED (blank closed_at) = {int(undated.sum())} trades, "
        f"${df.loc[undated, 'pnl'].sum():.2f}  <-- cannot be assigned to a session"
    )
    print(f"DATED = {int((~undated).sum())} trades, ${df.loc[~undated, 'pnl'].sum():.2f}")

    dd = df[~undated]
    by_day = dd.groupby("date").agg(n=("pnl", "size"), net=("pnl", "sum")).reset_index()
    by_day["net"] = by_day["net"].round(2)
    losing = by_day[by_day["net"] < 0].sort_values("net")
    print(
        f"\nDATED sessions = {len(by_day)}  ({(by_day['net'] < 0).sum()} losing / "
        f"{(by_day['net'] > 0).sum()} winning)   span {by_day['date'].min()} -> {by_day['date'].max()}"
    )
    print("\nWorst 15 DATED sessions:")
    print(losing.head(15).to_string(index=False))

    syms = sorted(dd["symbol"].dropna().unique().tolist())
    manifest = {
        "total_net": round(total_net, 2),
        "undated_trades": int(undated.sum()),
        "undated_pnl": round(float(df.loc[undated, "pnl"].sum()), 2),
        "dated_window": [str(by_day["date"].min()), str(by_day["date"].max())],
        "dated_losing_dates": [str(d) for d in losing["date"]],
        "worst_dated_dates": [str(d) for d in losing.head(15)["date"]],
        "symbols": syms,
        # Primary recommendation: test on a broad corpus, not the April slice.
        "recommended": (
            "Cache (or from_alpaca) minute bars for the FULL dated span above for ALL symbols, "
            "or a >=2-month chop-heavy window. Aim for >=60 sessions of replay trades. "
            "Do NOT rely on per-day targeting alone: closed_at is missing on a large, loss-heavy "
            "share of trades, and the replay re-runs the current engine so it won't reproduce the "
            "historical live losses regardless."
        ),
    }
    out = ROOT / "artifacts" / "losing_sessions.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote {out}  ({len(syms)} symbols).")


if __name__ == "__main__":
    main()
