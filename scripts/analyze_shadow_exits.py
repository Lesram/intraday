#!/usr/bin/env python3
"""Accumulate the shadow-vs-real exit delta from the Task-S telemetry JSONL.

Reads organism_brain/shadow_exit_telemetry.jsonl (one comparison row per closed
live position: real exit vs what the retracement shadow would have done) and
reports the cumulative gross delta with a t-stat — a live, Gate-2-style
accumulation toward the eventual live-exit decision.

Usage: ./venv/bin/python scripts/analyze_shadow_exits.py [path.jsonl]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _stats(deltas: list[float]) -> dict:
    n = len(deltas)
    if n == 0:
        return {"n": 0}
    mean = sum(deltas) / n
    var = sum((x - mean) ** 2 for x in deltas) / (n - 1) if n > 1 else 0.0
    sd = var ** 0.5
    t = (mean / (sd / (n ** 0.5))) if sd > 0 else 0.0
    return {"n": n, "sum": round(sum(deltas), 2), "mean": round(mean, 4),
            "t_stat": round(t, 3)}


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "organism_brain/shadow_exit_telemetry.jsonl")
    if not path.exists():
        print(f"No shadow telemetry at {path} (flag off, or no closed positions yet).")
        return
    rows = [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]
    if not rows:
        print(f"{path}: empty.")
        return

    deltas = [float(r.get("delta_gross", 0) or 0) for r in rows]
    triggered = [r for r in rows if r.get("shadow_triggered")]

    # Reuse the same summary the EOD scheduled task logs (one source of truth).
    from backend.organism.experimental.shadow_exit import summarize_shadow_telemetry
    s = summarize_shadow_telemetry(path)
    print(f"=== shadow-vs-real exit ({path}) — {len(rows)} closed positions ===")
    print(f"shadow would have changed the exit on {len(triggered)} / {len(rows)} "
          f"({100*len(triggered)/len(rows):.0f}%)")
    print("\nALL closed positions (held-agreed rows have delta 0):")
    print(f"  {s['overall']}")
    print("TRIGGERED only (where retracement diverged from the real exit):")
    print(f"  {s['triggered']}")

    # By regime.
    print("\n-- by regime (triggered) --")
    regs: dict[str, list[float]] = {}
    for r in triggered:
        regs.setdefault(str(r.get("regime")), []).append(float(r.get("delta_gross", 0) or 0))
    for reg, ds in sorted(regs.items(), key=lambda x: -sum(x[1])):
        print(f"  {reg:14} {_stats(ds)}")

    # By the REAL exit reason the shadow competed against.
    print("\n-- by real_exit_reason (triggered) --")
    reasons: dict[str, list[float]] = {}
    for r in triggered:
        reasons.setdefault(str(r.get("real_exit_reason")), []).append(
            float(r.get("delta_gross", 0) or 0))
    for rsn, ds in sorted(reasons.items(), key=lambda x: -sum(x[1])):
        print(f"  {str(rsn):24} {_stats(ds)}")

    # Running two-sub-period split (by row order = time order).
    h = len(rows) // 2
    if h >= 1:
        print("\n-- sub-period stability (all rows, time-ordered) --")
        print(f"  first half:  {_stats(deltas[:h])}")
        print(f"  second half: {_stats(deltas[h:])}")

    print(f"\nVERDICT: positive cumulative delta at t>=2 over enough live "
          f"sessions is the green light to consider flipping live exits "
          f"(separate gate). Current all-rows t={_stats(deltas).get('t_stat')}, "
          f"sum=${_stats(deltas).get('sum')}.")


if __name__ == "__main__":
    main()
