#!/usr/bin/env python3
"""Assemble a Gate-2 report.json from per-arm replay outputs.

Reads <arm>.json (aggregate replay metrics) and <arm>_trades.csv (per-trade
TradeRecords) from an edge_experiments output dir and computes, per arm, the
Gate-2 read the brief asks for: expectancy + t-stat of per-trade pnl after
costs, expectancy restricted to trades held >= 2 bars, PF, win rate,
MFE-giveback, and stability across two non-overlapping sub-periods (split by
entry_bar). Emits deltas vs baseline and a per-arm PASS/FAIL verdict against
Gate-2 thresholds (expectancy>0 at t>=2 after costs, PF>=1.3, both sub-periods
positive).

Usage: ./venv/bin/python scripts/analyze_exit_report.py <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd


def _stats(pnl: pd.Series) -> dict:
    n = int(len(pnl))
    if n == 0:
        return {"n": 0}
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    gl = float(abs(losses.sum()))
    mean = float(pnl.mean())
    std = float(pnl.std(ddof=1)) if n > 1 else 0.0
    t = (mean / (std / (n ** 0.5))) if std > 0 else 0.0
    return {
        "n": n,
        "net": round(float(pnl.sum()), 2),
        "expectancy": round(mean, 4),
        "t_stat": round(t, 3),
        "profit_factor": round(float(wins.sum()) / gl, 4) if gl > 0 else None,
        "win_rate": round(float((pnl > 0).mean()), 4),
    }


def _arm_gate2(csv: Path) -> dict:
    if not csv.exists():
        return {"trades_csv": False}
    df = pd.read_csv(csv)
    if "is_reconciliation_artifact" in df.columns:
        df = df[~df["is_reconciliation_artifact"].astype(str).str.lower().isin(["true", "1"])]
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce")
    df = df.dropna(subset=["pnl"])
    out: dict = {"trades_csv": True, "overall": _stats(df["pnl"])}

    # t>=2: trades held >= 2 bars (drop instant/1-bar exits).
    if "bars_held_at_exit" in df.columns:
        held = pd.to_numeric(df["bars_held_at_exit"], errors="coerce")
        out["held_ge_2"] = _stats(df.loc[held >= 2, "pnl"])

    # MFE giveback.
    if "mfe" in df.columns:
        mfe = pd.to_numeric(df["mfe"], errors="coerce")
        pos = df[mfe > 0]
        sm = float(mfe[mfe > 0].sum())
        out["mfe"] = {
            "pos_mfe_trades": int((mfe > 0).sum()),
            "sum_mfe": round(sm, 2),
            "realized": round(float(pos["pnl"].sum()), 2),
            "given_back": round(sm - float(pos["pnl"].sum()), 2),
            "retention_pct": round(100 * float(pos["pnl"].sum()) / sm, 1) if sm > 0 else None,
        }

    # Two non-overlapping sub-periods, split by entry order (entry_bar).
    sort_col = "entry_bar" if "entry_bar" in df.columns else None
    d = df.sort_values(sort_col) if sort_col else df
    half = len(d) // 2
    if half >= 1:
        out["sub1"] = _stats(d.iloc[:half]["pnl"])
        out["sub2"] = _stats(d.iloc[half:]["pnl"])
    return out


def main() -> None:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("artifacts/edge_experiments_broad")
    arms: dict = {}
    for jf in sorted(out_dir.glob("*.json")):
        if jf.name == "report.json":
            continue
        name = jf.stem
        rec = json.loads(jf.read_text())
        rec["gate2"] = _arm_gate2(out_dir / f"{name}_trades.csv")
        arms[name] = rec

    base = arms.get("baseline", {}).get("gate2", {}).get("overall", {})

    def verdict(g: dict) -> str:
        h = g.get("held_ge_2", {}) or g.get("overall", {})
        ov = g.get("overall", {})
        s1, s2 = g.get("sub1", {}), g.get("sub2", {})
        exp_ok = (h.get("expectancy") or 0) > 0 and (h.get("t_stat") or 0) >= 2
        pf_ok = (ov.get("profit_factor") or 0) >= 1.3
        stable = (s1.get("expectancy") or 0) > 0 and (s2.get("expectancy") or 0) > 0
        return "PASS" if (exp_ok and pf_ok and stable) else "FAIL: " + ", ".join(
            x for x, ok in [("exp>0@t>=2", exp_ok), ("PF>=1.3", pf_ok), ("sub-period-stable", stable)] if not ok
        )

    summary = {}
    for name, rec in arms.items():
        g = rec["gate2"]
        ov, h = g.get("overall", {}), g.get("held_ge_2", {})
        summary[name] = {
            "n": ov.get("n"), "net": ov.get("net"), "expectancy": ov.get("expectancy"),
            "t_stat": ov.get("t_stat"), "pf": ov.get("profit_factor"),
            "exp_held_ge_2": h.get("expectancy"), "t_held_ge_2": h.get("t_stat"),
            "mfe_retention_pct": (g.get("mfe") or {}).get("retention_pct"),
            "sub1_exp": (g.get("sub1") or {}).get("expectancy"),
            "sub2_exp": (g.get("sub2") or {}).get("expectancy"),
            "d_net_vs_baseline": (round((ov.get("net") or 0) - (base.get("net") or 0), 2)
                                  if name != "baseline" else 0.0),
            "verdict": verdict(g),
        }

    report = {"corpus": str(out_dir), "arms": arms, "gate2_summary": summary}
    (out_dir / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
