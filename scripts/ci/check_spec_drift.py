#!/usr/bin/env python3
"""Spec-vs-runtime drift checker.

Parses the runtime config snapshot and the mapss.md key thresholds section,
then fails if core live constants disagree.  Intended to run in CI on every
PR that touches backend/ or docs/architecture/.

Exit 0 = no drift.  Exit 1 = drift detected (prints details).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_snapshot() -> dict:
    """Load runtime_config_snapshot.json (prefer venv-generated full version)."""
    p = ROOT / "artifacts" / "runtime_config_snapshot.json"
    if not p.exists():
        print("ERROR: artifacts/runtime_config_snapshot.json not found")
        print("Run: ./venv/bin/python scripts/runtime/write_runtime_snapshot.py")
        sys.exit(1)
    data = json.loads(p.read_text())
    if data.get("error"):
        print(f"WARNING: snapshot has error: {data['error']}")
        print("Drift check will use fallback values only.")
    return data


def parse_mapss_thresholds() -> dict:
    """Extract key constants from the mapss.md KEY THRESHOLDS SUMMARY table."""
    mapss = ROOT / "docs" / "architecture" / "mapss.md"
    if not mapss.exists():
        print("ERROR: docs/architecture/mapss.md not found")
        sys.exit(1)

    text = mapss.read_text()
    extracted = {}

    # Fitness gate: look for "0.45 (production"
    m = re.search(r"Symbol fitness gate.*?(\d+\.\d+)\s*\(production", text)
    if m:
        extracted["fitness_gate_production"] = float(m.group(1))

    # Confidence entry gate baseline
    m = re.search(r"Confidence entry gate\s*\|\s*(\d+\.\d+)", text)
    if m:
        extracted["confidence_gate_baseline"] = float(m.group(1))

    # Confidence entry gate defensive (in parentheses)
    m = re.search(r"Confidence entry gate\s*\|[^|]*\((\d+\.\d+)\s+in", text)
    if m:
        extracted["confidence_gate_defensive"] = float(m.group(1))

    # Horizon timeout
    m = re.search(r"Horizon timeout\s*\|\s*\*?\*?(\d+)\s*bars", text)
    if m:
        extracted["horizon_timeout_bars"] = int(m.group(1))

    # Full evolution freeze
    m = re.search(r"Full evolution freeze\s*\|\s*\*?\*?(\d+)\+?\s*total", text)
    if m:
        extracted["evolution_freeze_until_trades"] = int(m.group(1))

    # Alpha top_n (from the constants block in LIVE_AUDIT_INDEX or body)
    m = re.search(r"alpha_top_n.*?(\d+)", text)
    if m:
        extracted["alpha_top_n"] = int(m.group(1))

    # Max positions
    m = re.search(r"max_positions.*?(\d+)", text)
    if m:
        extracted["max_positions"] = int(m.group(1))

    # Kelly risk-budget learning
    m = re.search(r"Kelly risk-budget floor\s*\|\s*\*?\*?(\d+\.\d+)%\s*equity", text)
    if m:
        extracted["risk_budget_learning"] = float(m.group(1)) / 100.0

    # Drawdown kill switch — extract code default
    m = re.search(r"Drawdown kill switch\s*\|[^|]*code[^:]*:\s*(\d+)%", text)
    if m:
        extracted["drawdown_kill_pct"] = float(m.group(1)) / 100.0

    # Exploration enabled — check for "exploration removed" or "false"
    if "exploration queue removed" in text.lower() or "exploration removed" in text.lower():
        extracted["exploration_enabled"] = False

    return extracted


def check_drift(snapshot: dict, spec: dict) -> list[str]:
    """Compare snapshot values against spec values. Return list of drift descriptions."""
    drifts = []

    checks = [
        ("fitness_gate_production", "fitness_gate_production"),
        ("confidence_gate_baseline", "confidence_gate_baseline"),
        ("confidence_gate_defensive", "confidence_gate_defensive"),
        ("horizon_timeout_bars", "horizon_timeout_bars"),
        ("evolution_freeze_until_trades", "evolution_freeze_until_trades"),
        ("alpha_top_n", "alpha_top_n"),
        ("max_positions", "max_positions"),
        ("risk_budget_learning", "risk_budget_learning"),
        ("drawdown_kill_pct", "drawdown_kill_pct"),
    ]

    for snap_key, spec_key in checks:
        snap_val = snapshot.get(snap_key)
        spec_val = spec.get(spec_key)

        if spec_val is None:
            continue  # Could not parse from mapss.md

        if snap_val is None:
            drifts.append(f"  {snap_key}: missing from runtime snapshot")
            continue

        # Float comparison with tolerance
        if isinstance(snap_val, float) and isinstance(spec_val, float):
            if abs(snap_val - spec_val) > 0.001:
                drifts.append(f"  {snap_key}: runtime={snap_val} vs spec={spec_val}")
        elif snap_val != spec_val:
            drifts.append(f"  {snap_key}: runtime={snap_val} vs spec={spec_val}")

    # Boolean check: exploration
    if "exploration_enabled" in spec:
        snap_exploration = snapshot.get("exploration_enabled")
        if snap_exploration is not None and snap_exploration != spec["exploration_enabled"]:
            drifts.append(
                f"  exploration_enabled: runtime={snap_exploration} "
                f"vs spec={spec['exploration_enabled']}"
            )

    return drifts


def main() -> None:
    print("Checking spec-vs-runtime drift...")

    snapshot = load_snapshot()
    spec = parse_mapss_thresholds()

    print(f"  Parsed {len(spec)} constants from mapss.md")
    print(f"  Runtime snapshot has {len(snapshot)} keys")

    drifts = check_drift(snapshot, spec)

    if drifts:
        print(f"\nDRIFT DETECTED ({len(drifts)} mismatches):")
        for d in drifts:
            print(d)
        print("\nFix mapss.md or the runtime config to match.")
        sys.exit(1)
    else:
        print(f"  All {len([k for k in spec if k != 'exploration_enabled'])} checked constants match.")
        print("No spec drift detected.")


if __name__ == "__main__":
    main()
