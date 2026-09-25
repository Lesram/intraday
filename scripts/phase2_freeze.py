#!/usr/bin/env python3
"""Build a candidate decision-surface reference or verify an explicit reference.

Snapshots the FULL decision surface that determines which trades happen and how
they resolve — not just the four momentum thresholds (Gap 2). The forward corpus
is only "params never saw this data" if every such param is frozen, so a change to
ANY of them must reset the clock. We capture:
  * source hashes of: entry-direction logic, the exit engine, the regime detector,
    the Kelly sizer, and the live entry-gate/dispatch (_live_tick_inner);
  * the strategy config (explicit + hashed);
  * the ORGANISM_EXIT_* env overrides.

An approved active reference retains FROZEN_AT. Candidate references contain a
validation timestamp, git sha, n_target (pinned to the prior), and the provenance
finding, with no authority to start an evaluation epoch.

Generation writes only a separate, unapproved candidate with VALIDATED_AT.
It never writes the active artifact or starts/resets a forward clock. Publishing
an active FROZEN_AT is a separate approved activation operation.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

FREEZE_PATH = Path("artifacts/phase2/param_freeze.json")
CANDIDATE_FREEZE_PATH = Path("artifacts/phase2/candidate_param_freeze.json")
POLICY_BASELINE_PATH = Path(__file__).resolve().parents[1] / "artifacts/phase2/research_policy_baseline.json"
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


def compute_data_pipeline_sources() -> dict[str, str]:
    """Pin discovery and data-admission helpers outside the original six hashes."""
    from backend.organism import market_scanner, streaming_data_provider, live_engine_data
    from backend.organism import pipeline_diagnostics
    from backend.organism.live_engine import OrganismLiveEngine

    return {
        "market_scanner": _h(inspect.getsource(market_scanner)),
        "streaming_data_provider": _h(inspect.getsource(streaming_data_provider)),
        "live_engine_data": _h(inspect.getsource(live_engine_data)),
        "staleness_admission": _h(inspect.getsource(OrganismLiveEngine._stage_update_data_staleness)),
        "streaming_universe_initialization": _h(inspect.getsource(OrganismLiveEngine.__init__)),
        "streaming_subscription_sync": _h(inspect.getsource(OrganismLiveEngine._sync_streaming_subscriptions)),
        "streaming_subscription_timeout": _h(repr(OrganismLiveEngine._STREAM_SUBSCRIPTION_SYNC_TIMEOUT_S)),
        "pipeline_diagnostics": _h(inspect.getsource(pipeline_diagnostics)),
    }


def compute_surface() -> dict:
    """The full decision surface, normalized (deterministic; no metadata)."""
    from backend.organism.adaptive_exits import AdaptiveExitEngine
    from backend.organism.alpha_scanner import AlphaScanner
    from backend.organism.kelly_sizer import KellySizer
    from backend.organism.live_engine import OrganismLiveEngine
    from backend.organism.regime import RegimeDetector
    from backend.organism import research_policy, research_baseline, trading_phase, background_trainer
    from backend.organism import governance, model_fingerprint, operator_controls
    from backend.organism import entry_evidence, entry_freshness
    from backend.organism.self_evolution import apply_evolved_params
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
    policy_baseline_bytes = POLICY_BASELINE_PATH.read_bytes()
    policy_baseline = json.loads(policy_baseline_bytes)
    baseline_params = policy_baseline["effective_policy_params"]
    if research_policy.effective_policy_hash(baseline_params) != policy_baseline["effective_policy_hash"]:
        raise ValueError("Research policy baseline hash mismatch")
    surface = {
        "source_hashes": source_hashes,
        "strategy_config": STRATEGY_CONFIG,
        "strategy_config_hash": _h(json.dumps(STRATEGY_CONFIG, sort_keys=True, default=str)),
        "regime_policy": REGIME_POLICY,
        "exit_env": {k: os.getenv(k) for k in EXIT_ENV_VARS},
        "routing_data_env": {k: os.getenv(k) for k in ROUTING_DATA_ENV_VARS},
        # Candidate discovery and preliminary data admission can change which
        # trades reach the final entry gate. Keep their helpers inside the
        # frozen surface, even when the six original entry/exit hashes match.
        "data_pipeline_sources": compute_data_pipeline_sources(),
        # The September paper lock closes promotion/training seams that were
        # outside the original six hashes. Changing these also requires an
        # explicitly approved new forward boundary.
        "research_policy": research_policy.policy_status(),
        "effective_policy_baseline": {
            "effective_policy_hash": policy_baseline["effective_policy_hash"],
            "effective_policy_params": baseline_params,
            "artifact_sha256": hashlib.sha256(policy_baseline_bytes).hexdigest(),
        },
        "research_policy_enforcement_env": {
            research_baseline.BASELINE_ENV: os.getenv(research_baseline.BASELINE_ENV),
            operator_controls.STATE_ENV: os.getenv(operator_controls.STATE_ENV),
        },
        "research_policy_sources": {
            "policy": _h(inspect.getsource(research_policy)),
            "baseline_verification": _h(inspect.getsource(research_baseline)),
            "model_fingerprint": _h(inspect.getsource(model_fingerprint)),
            "phase": _h(inspect.getsource(trading_phase)),
            "trainer": _h(inspect.getsource(background_trainer)),
            "startup": _h(inspect.getsource(OrganismLiveEngine.initialize)),
            "sync_training": _h(inspect.getsource(OrganismLiveEngine._retrain_and_evolve)),
            "phase_resolution": _h(inspect.getsource(OrganismLiveEngine._trading_phase.fget)),
            "ml_isolation": _h(inspect.getsource(OrganismLiveEngine._ml_isolation_mode.fget)),
            "fixed_risk": _h(inspect.getsource(OrganismLiveEngine._fixed_risk_sizing_mode.fget)),
            "settings_update": _h(inspect.getsource(OrganismLiveEngine.update_config)),
            "parameter_application": _h(inspect.getsource(apply_evolved_params)),
            "settings_api": _h((Path(__file__).resolve().parents[1] / "backend/api/routes/settings.py").read_text()),
            "scheduler": _h((Path(__file__).resolve().parents[1] / "backend/organism/scheduler.py").read_text()),
            "operator_controls": _h(inspect.getsource(operator_controls)),
            "governance": _h(inspect.getsource(governance)),
            "entry_admission": _h(inspect.getsource(OrganismLiveEngine._authorize_live_entry_order)),
            # Approved September 22 freshness gate depends on the actual frame
            # observer and the final submission seam, not callback receipt age.
            "entry_frame_capture": _h(inspect.getsource(OrganismLiveEngine._passes_entry_gates)),
            "entry_evidence": _h(inspect.getsource(entry_evidence)),
            "entry_freshness": _h(inspect.getsource(entry_freshness)),
            "entry_submission": _h(inspect.getsource(OrganismLiveEngine._submit_entry_order)),
            "operator_api": _h((Path(__file__).resolve().parents[1] / "backend/organism/routes.py").read_text()),
            "emergency_stop_api": _h((Path(__file__).resolve().parents[1] / "backend/api/routes/risk.py").read_text()),
            "emergency_stop_service": _h((Path(__file__).resolve().parents[1] / "backend/services/risk_manager.py").read_text()),
            "entry_cancellation": _h((Path(__file__).resolve().parents[1] / "backend/organism/operator_cancellation.py").read_text()),
        },
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
    """Build non-active candidate metadata, never an activation document."""
    from backend.organism.freeze_contract import load_active_freeze

    surface = compute_surface()
    validated_at = datetime.now(timezone.utc).isoformat()
    note = "new candidate validation boundary; no active clock change"
    if CANDIDATE_FREEZE_PATH.exists():
        prev = _validate_candidate(json.loads(CANDIDATE_FREEZE_PATH.read_text()))
        if prev.get("surface") == surface:
            validated_at = prev["VALIDATED_AT"]
            note = "candidate surface unchanged; validation boundary preserved"
    active_cutoff = (load_active_freeze(FREEZE_PATH)["FROZEN_AT"]
                     if FREEZE_PATH.exists() else None)
    return {
        "VALIDATED_AT": validated_at,
        "candidate_only": True,
        "deployment_approved": False,
        "active_forward_cutoff": active_cutoff,
        "git_sha": _git_sha(),
        "n_target": N_TARGET,
        "n_target_range": N_TARGET_RANGE,
        "provenance": PROVENANCE,
        "note": ("Unapproved candidate source reference only. VALIDATED_AT is not "
                 "a trading cutoff. Active measurement requires a separately "
                 "approved activation artifact; never promote this file."),
        "_note_status": note,
        "surface": surface,
    }


def _validate_candidate(payload: object) -> dict:
    if (not isinstance(payload, dict) or payload.get("candidate_only") is not True
            or payload.get("deployment_approved") is not False
            or "FROZEN_AT" in payload
            or not isinstance(payload.get("VALIDATED_AT"), str)
            or not isinstance(payload.get("surface"), dict)):
        raise ValueError("invalid candidate reference")
    validation_time = datetime.fromisoformat(payload["VALIDATED_AT"])
    if validation_time.tzinfo is None or validation_time.utcoffset() is None:
        raise ValueError("candidate timestamp must be timezone-aware")
    return payload


def _diff_surface(stored: dict, current: dict) -> list[str]:
    """Human-readable list of the exact keys that drifted (≤2 levels deep,
    which covers source_hashes / exit_env / routing_data_env / regime_policy /
    strategy_config-per-strategy)."""
    diffs: list[str] = []
    for k in sorted(set(stored) | set(current)):
        sv, cv = stored.get(k), current.get(k)
        if sv == cv:
            continue
        if isinstance(sv, dict) and isinstance(cv, dict):
            for sk in sorted(set(sv) | set(cv)):
                if sv.get(sk) != cv.get(sk):
                    diffs.append(
                        f"    {k}.{sk}: frozen={sv.get(sk)!r} current={cv.get(sk)!r}")
        else:
            diffs.append(f"    {k}: frozen={sv!r} current={cv!r}")
    return diffs


def verify(*, candidate: bool = False) -> int:
    """READ-ONLY drift check (never writes). Recompute the live decision
    surface and compare it to the frozen artifact. Exit 0 if identical, 1 if
    drifted, 2 if there is no artifact to verify against.

    Candidate verification is explicit and cannot authorize an active cutoff.
    Neither verification mode writes any artifact or changes the clock.
    """
    from backend.organism.freeze_contract import load_active_freeze

    reference = CANDIDATE_FREEZE_PATH if candidate else FREEZE_PATH
    scope = "CANDIDATE" if candidate else "ACTIVE"
    if not reference.exists():
        print(f"{scope} DRIFT-VERIFY FAIL: no freeze artifact at {reference}")
        return 2
    try:
        if candidate:
            stored = _validate_candidate(json.loads(reference.read_text()))
        else:
            stored = load_active_freeze(reference)
    except (OSError, ValueError, TypeError):
        print(f"{scope} DRIFT-VERIFY FAIL: invalid or wrong-authority artifact")
        return 2
    stored_surface = stored.get("surface")
    if not isinstance(stored_surface, dict):
        print(f"{scope} DRIFT-VERIFY FAIL: missing or invalid decision surface")
        return 2
    current = compute_surface()
    boundary = stored.get("VALIDATED_AT" if candidate else "FROZEN_AT")
    if stored_surface == current:
        print(f"{scope} DRIFT-VERIFY OK: decision surface matches reference "
              f"(boundary={boundary}; read-only)")
        return 0
    print(f"{scope} DRIFT-VERIFY FAIL: decision surface DRIFTED from reference "
          f"(boundary={boundary}); no clock change performed. Offending keys:")
    for line in _diff_surface(stored_surface or {}, current):
        print(line)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="read-only reference verification")
    parser.add_argument("--candidate", action="store_true", help="verify the separate candidate reference")
    args = parser.parse_args(argv)
    if args.verify:
        return verify(candidate=args.candidate)
    if CANDIDATE_FREEZE_PATH.resolve() == FREEZE_PATH.resolve():
        print("Refusing to write a candidate over the active artifact")
        return 2
    try:
        freeze = build_freeze()
    except (OSError, ValueError, TypeError):
        print("Cannot build candidate: invalid existing reference")
        return 2
    CANDIDATE_FREEZE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATE_FREEZE_PATH.write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n")
    print(f"candidate decision surface -> {CANDIDATE_FREEZE_PATH}")
    print(f"  VALIDATED_AT={freeze['VALIDATED_AT']}  ({freeze['_note_status']})")
    print(f"  git_sha={freeze['git_sha']}  n_target={freeze['n_target']}")
    print(f"  source_hashes={list(freeze['surface']['source_hashes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
