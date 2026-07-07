#!/usr/bin/env python3
"""Phase 2 PRECONDITION — Task 0: freeze the decision surface, start the forward clock.

Snapshots the FULL decision surface that determines which trades happen and how
they resolve — not just the four momentum thresholds (Gap 2). The forward corpus
is only "params never saw this data" if every such param is frozen, so a change to
ANY of them must reset the clock. We capture:
  * source hashes of: entry-direction logic, the exit engine, the regime detector,
    the Kelly sizer, and the live entry-gate/dispatch (_live_tick_inner);
  * the strategy config (explicit + hashed);
  * the ORGANISM_EXIT_* env overrides.

Plus the metadata that makes the freeze a permanent, non-re-litigable fact:
FROZEN_AT, git sha, n_target (Task 3, pinned to the prior), and the no-provenance
finding verbatim.

Re-running is safe: if the surface is unchanged, FROZEN_AT is PRESERVED (no clock
reset). If the surface drifted, FROZEN_AT is re-stamped — the clock resets, by
construction, because the forward corpus is now contaminated.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

FREEZE_PATH = Path("artifacts/phase2/param_freeze.json")
N_TARGET = 60                  # pinned to the prior (t≈1.0 @ n≈18 ⇒ ~50–70 to clear)
N_TARGET_RANGE = [50, 70]
PROVENANCE = ("no reconstructable fit-date; all pre-cutoff data contaminated by "
              "construction")

EXIT_ENV_VARS = [
    "ORGANISM_EXIT_ATR_MULT", "ORGANISM_EXIT_DECAY_START",
    "ORGANISM_EXIT_DECAY_START_MULT", "ORGANISM_EXIT_MAX_BARS",
    "ORGANISM_EXIT_MAX_BARS_MULT", "ORGANISM_EXIT_PARTIAL_TP_PCT",
    "ORGANISM_EXIT_PARTIAL_TP_R", "ORGANISM_EXIT_PROFIT_LOCK_R",
    "ORGANISM_EXIT_PROFIT_R", "ORGANISM_EXIT_STOP_ATR_MULT",
    "ORGANISM_EXIT_TRAIL_ATR_MULT", "ORGANISM_EXIT_TRAIL_DIST_ATR",
    "ORGANISM_EXIT_TRAIL_START_ATR",
]

# Phase 3 Task 5: the routing/data half of the decision surface. The DATA FEED
# is a first-class frozen fact (Task 0 — a verdict must never be read out of
# its data context); routing flags decide WHICH code path trades; the
# liquidity floor was recalibrated 20x for IEX (2026-07-06) and gates the
# whole universe; REGIME_POLICY is the Task-4 ranking authority.
ROUTING_DATA_ENV_VARS = [
    "ALPACA_DATA_FEED",
    "ORGANISM_MIN_AVG_DOLLAR_VOLUME",
    "ORGANISM_FRAMEWORK_ROUTING",
    "ORGANISM_FRAMEWORK_ROUTING_V2",
    "ORGANISM_ROUTING_RANK_POLICY",
]


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def compute_surface() -> dict:
    """The full decision surface, normalized (deterministic; no metadata)."""
    from backend.organism.adaptive_exits import AdaptiveExitEngine
    from backend.organism.alpha_scanner import AlphaScanner
    from backend.organism.kelly_sizer import KellySizer
    from backend.organism.live_engine import OrganismLiveEngine
    from backend.organism.regime import RegimeDetector
    from backend.organism.strategies.strategy_config import (
        REGIME_POLICY, STRATEGY_CONFIG,
    )

    source_hashes = {
        "entry_direction": _h(inspect.getsource(AlphaScanner._observable_direction)),
        "exit_engine": _h(inspect.getsource(AdaptiveExitEngine)),
        "regime_detector": _h(inspect.getsource(RegimeDetector)),
        "kelly_sizer": _h(inspect.getsource(KellySizer)),
        "entry_gates_dispatch": _h(inspect.getsource(OrganismLiveEngine._live_tick_inner)),
        # Phase 3: the selector routing path is decision surface once V2 is on.
        "selector_routing": _h(
            inspect.getsource(OrganismLiveEngine._rank_candidates)
            + inspect.getsource(OrganismLiveEngine._scan_all_strategies_v2)
            + inspect.getsource(OrganismLiveEngine._scan_entry_candidates)),
    }
    surface = {
        "source_hashes": source_hashes,
        "strategy_config": STRATEGY_CONFIG,
        "strategy_config_hash": _h(json.dumps(STRATEGY_CONFIG, sort_keys=True, default=str)),
        "regime_policy": REGIME_POLICY,
        "exit_env": {k: os.getenv(k) for k in EXIT_ENV_VARS},
        "routing_data_env": {k: os.getenv(k) for k in ROUTING_DATA_ENV_VARS},
    }
    # Normalize to the JSON representation so on-disk vs in-memory compare cleanly.
    return json.loads(json.dumps(surface, sort_keys=True, default=str))


def _git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def build_freeze() -> dict:
    surface = compute_surface()
    frozen_at = datetime.now(timezone.utc).isoformat()
    note = "clock reset"
    if FREEZE_PATH.exists():
        prev = json.loads(FREEZE_PATH.read_text())
        if prev.get("surface") == surface:
            frozen_at = prev.get("FROZEN_AT", frozen_at)  # unchanged ⇒ preserve clock
            note = "surface unchanged — clock preserved"
    return {
        "FROZEN_AT": frozen_at,
        "git_sha": _git_sha(),
        "n_target": N_TARGET,
        "n_target_range": N_TARGET_RANGE,
        "provenance": PROVENANCE,
        "note": ("Forward-only by construction. The verdict corpus is trades taken "
                 "STRICTLY AFTER FROZEN_AT. Any decision-surface drift (source_hashes/"
                 "strategy_config/exit_env) RESETS the clock — re-run this script."),
        "_note_status": note,
        "surface": surface,
    }


def main() -> int:
    FREEZE_PATH.parent.mkdir(parents=True, exist_ok=True)
    freeze = build_freeze()
    FREEZE_PATH.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n")
    print(f"froze decision surface -> {FREEZE_PATH}")
    print(f"  FROZEN_AT={freeze['FROZEN_AT']}  ({freeze['_note_status']})")
    print(f"  git_sha={freeze['git_sha']}  n_target={freeze['n_target']}")
    print(f"  source_hashes={list(freeze['surface']['source_hashes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
