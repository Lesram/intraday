#!/usr/bin/env python3
"""Phase 3 Task 4 — per-strategy, per-regime attribution report.

Three sections:
  1. CAPITAL (forward corpus): n / costed net expectancy / t / clustered-t
     per strategy per regime, strictly-after-FROZEN_AT trades only — the
     same corpus the verdict gate consumes.
  2. GATE STATES: the phase2_gate verdict per strategy (regime-conditional
     momentum), i.e. what would/does route capital (Rule A).
  3. SHADOW: framework shadow-signal counts per strategy per regime from the
     strategy evidence feed (fw_<name>_shadow) — the un-routed strategies'
     accumulating comparison data.

Usage: PYTHONPATH=. venv/bin/python scripts/phase3_attribution_report.py
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pandas as pd

from backend.organism.confidence_lab import _cluster_tstat, _tstat  # CR + iid t
from backend.organism.phase2_gate import (
    LOOKS, MOMENTUM_TREND_REGIMES, gate_for_strategy, load_forward_corpus,
)

FREEZE = Path("artifacts/phase2/param_freeze.json")
TRADES = Path("organism_brain/trade_history.csv")
EVIDENCE = Path("organism_brain/strategy_evidence_events.jsonl")  # engine default


def main() -> int:
    if not FREEZE.exists():
        print("no param_freeze.json — run scripts/phase2_freeze.py first")
        return 2
    freeze = json.loads(FREEZE.read_text())
    frozen_at = freeze["FROZEN_AT"]
    print("=" * 72)
    print("PHASE-3 ATTRIBUTION — per strategy, per regime")
    print("=" * 72)
    print(f"FROZEN_AT={frozen_at}   looks={LOOKS}")

    corpus = (load_forward_corpus(str(TRADES), frozen_at)
              if TRADES.exists() else pd.DataFrame())
    print(f"\n[1] CAPITAL — forward corpus: {len(corpus)} trades")
    if len(corpus):
        for (strat, regime), sub in corpus.groupby(["strategy", "regime_at_entry"]):
            net = sub["net_pnl"].to_numpy(dtype=float)
            sess = pd.factorize(sub["session"])[0] if "session" in sub else None
            tc = _cluster_tstat(net, sess) if sess is not None else float("nan")
            print(f"  {strat:16s} {str(regime):14s} n={len(net):<5d} "
                  f"exp={net.mean():+.4f}  t={_tstat(net):+.2f}  t_clust={tc:+.2f}")
    else:
        print("  (empty — corpus fills from the freeze cutoff)")

    print("\n[2] GATE STATES (Rule A capital authority)")
    for strat, regimes in [("momentum", MOMENTUM_TREND_REGIMES), ("breakout", None),
                           ("mean_reversion", None), ("orb", None)]:
        r = gate_for_strategy(corpus, strat, regimes)
        print(f"  {strat:16s} state={r['state']:14s} n={r['n']}")

    print("\n[3] SHADOW — framework un-routed signal accumulation")
    if EVIDENCE.exists():
        counts: Counter = Counter()
        bad_lines = 0
        with EVIDENCE.open() as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    bad_lines += 1     # counted + reported below, not swallowed
                    continue
                sid = str(rec.get("strategy_id", ""))
                if sid.startswith("fw_") and sid.endswith("_shadow"):
                    counts[(sid[3:-7], str(rec.get("regime", "?")))] += 1
        if bad_lines:
            print(f"  (skipped {bad_lines} unparseable evidence lines)")
        if counts:
            for (strat, regime), n in sorted(counts.items()):
                print(f"  {strat:16s} {regime:14s} signals={n}")
        else:
            print("  (no framework shadow signals yet — populate under V2)")
    else:
        print(f"  (no evidence feed at {EVIDENCE})")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
