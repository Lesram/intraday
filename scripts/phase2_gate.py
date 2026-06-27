#!/usr/bin/env python3
"""Phase 2 PRECONDITION — verdict-gate status CLI.

Reads the frozen cutoff (param_freeze.json) and the live trade history, builds the
forward-only corpus (trades strictly after FROZEN_AT), and prints the gate state
per strategy. Expected output for a long time: INSUFFICIENT — the corpus fills
from zero at the freeze. This is the deliverable: a trustworthy instrument that
currently says "not yet", not an answer.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.organism.phase2_gate import (
    LOOKS, MOMENTUM_TREND_REGIMES, gate_for_strategy, load_forward_corpus,
)

FREEZE = Path("artifacts/phase2/param_freeze.json")
TRADES = Path("organism_brain/trade_history.csv")


def main() -> int:
    if not FREEZE.exists():
        print("no param_freeze.json — run scripts/phase2_freeze.py first")
        return 2
    frozen_at = json.loads(FREEZE.read_text())["FROZEN_AT"]
    if not TRADES.exists():
        print(f"no {TRADES}")
        return 2
    corpus = load_forward_corpus(str(TRADES), frozen_at)
    print("=" * 66)
    print("PHASE-2 VERDICT GATE STATUS")
    print("=" * 66)
    print(f"FROZEN_AT={frozen_at}  forward trades={len(corpus)}  looks={LOOKS}")
    print("-" * 66)
    # momentum is regime-conditional (trend slice); the rest unconditional.
    for strat, regimes in [("momentum", MOMENTUM_TREND_REGIMES), ("breakout", None),
                           ("mean_reversion", None), ("orb", None)]:
        r = gate_for_strategy(corpus, strat, regimes)
        tag = "" if regimes is None else f" [trend slice: {sorted(regimes)}]"
        print(f"{strat:16s}{tag}")
        print(f"    state={r['state']}  n={r['n']}  look={r['look']}  t={r['t']}")
        if r.get("note"):
            print(f"    {r['note']}")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
