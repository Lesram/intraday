#!/usr/bin/env python3
"""Spec-vs-runtime drift checker (3-way).

Compares core live constants across THREE sources:
  1. artifacts/resolved_live_runtime_snapshot.json (or runtime_config_snapshot.json)
  2. docs/architecture/mapss.md KEY THRESHOLDS SUMMARY
  3. docs/engineering/baseline_reviews/*/strategy_surface_manifest.json

Fails if any source disagrees on core constants.
Exit 0 = no drift.  Exit 1 = drift detected (prints details).
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_snapshot() -> dict:
    """Load the CODE DEFAULTS snapshot for spec comparison.

    The drift check compares code defaults against spec docs. The resolved
    live snapshot (which includes .env overrides) is for visibility only —
    env overrides are intentional divergences, not spec drift.
    """
    for name in [
        "runtime_defaults_snapshot.json",
        "runtime_config_snapshot.json",
    ]:
        p = ROOT / "artifacts" / name
        if p.exists():
            data = json.loads(p.read_text())
            if data.get("error"):
                print(f"WARNING: {name} has error: {data['error']}")
                continue
            return data

    print("ERROR: no runtime snapshot found in artifacts/")
    print("Run: ./venv/bin/python scripts/runtime/write_runtime_snapshot.py")
    sys.exit(1)


def parse_mapss_thresholds() -> dict:
    """Extract key constants from the mapss.md KEY THRESHOLDS SUMMARY table."""
    mapss = ROOT / "docs" / "architecture" / "mapss.md"
    if not mapss.exists():
        print("ERROR: docs/architecture/mapss.md not found")
        sys.exit(1)

    text = mapss.read_text()
    extracted = {}

    m = re.search(r"Symbol fitness gate.*?(\d+\.\d+)\s*\(production", text)
    if m:
        extracted["fitness_gate_production"] = float(m.group(1))

    m = re.search(r"Confidence entry gate\s*\|\s*(\d+\.\d+)", text)
    if m:
        extracted["confidence_gate_baseline"] = float(m.group(1))

    m = re.search(r"Confidence entry gate\s*\|[^|]*\((\d+\.\d+)\s+in", text)
    if m:
        extracted["confidence_gate_defensive"] = float(m.group(1))

    m = re.search(r"Horizon timeout\s*\|\s*\*?\*?(\d+)\s*bars", text)
    if m:
        extracted["horizon_timeout_bars"] = int(m.group(1))

    m = re.search(r"Full evolution freeze\s*\|\s*\*?\*?(\d+)\+?\s*total", text)
    if m:
        extracted["evolution_freeze_until_trades"] = int(m.group(1))

    m = re.search(r"alpha_top_n.*?(\d+)", text)
    if m:
        extracted["alpha_top_n"] = int(m.group(1))

    m = re.search(r"max_positions.*?(\d+)", text)
    if m:
        extracted["max_positions"] = int(m.group(1))

    m = re.search(r"Kelly risk-budget floor\s*\|\s*\*?\*?(\d+\.\d+)%\s*equity", text)
    if m:
        extracted["risk_budget_learning"] = float(m.group(1)) / 100.0

    m = re.search(r"Drawdown kill switch\s*\|[^|]*code[^:]*:\s*(\d+)%", text)
    if m:
        extracted["drawdown_kill_pct"] = float(m.group(1)) / 100.0

    if "exploration queue removed" in text.lower() or "exploration removed" in text.lower():
        extracted["exploration_enabled"] = False

    return extracted


def load_manifest() -> dict:
    """Load the strategy_surface_manifest.json live_constants block."""
    manifests = sorted(ROOT.glob("docs/engineering/baseline_reviews/*/strategy_surface_manifest.json"))
    if not manifests:
        return {}
    latest = manifests[-1]
    data = json.loads(latest.read_text())
    lc = data.get("live_constants", {})
    # Normalize keys to match snapshot naming
    return {
        "fitness_gate_production": lc.get("fitness_gate_production"),
        "confidence_gate_baseline": lc.get("confidence_gate_baseline"),
        "confidence_gate_defensive": lc.get("confidence_gate_defensive"),
        "horizon_timeout_bars": lc.get("horizon_timeout_bars"),
        "evolution_freeze_until_trades": lc.get("evolution_freeze"),
        "alpha_top_n": lc.get("alpha_top_n"),
        "max_positions": lc.get("max_positions"),
        "risk_budget_learning": lc.get("risk_budget_learning"),
        "drawdown_kill_pct": lc.get("drawdown_kill_pct_default"),
        "exploration_enabled": lc.get("exploration_enabled"),
        "inverse_etfs": lc.get("inverse_etfs"),
    }


CORE_KEYS = [
    "fitness_gate_production",
    "confidence_gate_baseline",
    "confidence_gate_defensive",
    "horizon_timeout_bars",
    "evolution_freeze_until_trades",
    "alpha_top_n",
    "max_positions",
    "risk_budget_learning",
    "drawdown_kill_pct",
]


def compare(a: dict, b: dict, a_label: str, b_label: str) -> list[str]:
    """Compare two sources on core keys. Return drift descriptions."""
    drifts = []
    for key in CORE_KEYS:
        a_val = a.get(key)
        b_val = b.get(key)
        if a_val is None or b_val is None:
            continue
        if isinstance(a_val, float) and isinstance(b_val, float):
            if abs(a_val - b_val) > 0.001:
                drifts.append(f"  {key}: {a_label}={a_val} vs {b_label}={b_val}")
        elif a_val != b_val:
            drifts.append(f"  {key}: {a_label}={a_val} vs {b_label}={b_val}")

    # Boolean: exploration
    for key in ["exploration_enabled"]:
        a_val = a.get(key)
        b_val = b.get(key)
        if a_val is not None and b_val is not None and a_val != b_val:
            drifts.append(f"  {key}: {a_label}={a_val} vs {b_label}={b_val}")

    # List: inverse_etfs
    a_etfs = sorted(a.get("inverse_etfs") or [])
    b_etfs = sorted(b.get("inverse_etfs") or [])
    if a_etfs and b_etfs and a_etfs != b_etfs:
        drifts.append(f"  inverse_etfs: {a_label}={a_etfs} vs {b_label}={b_etfs}")

    return drifts


def main() -> None:
    print("Checking 3-way spec-vs-runtime drift...")

    snapshot = load_snapshot()
    spec = parse_mapss_thresholds()
    manifest = load_manifest()

    print(f"  Parsed {len(spec)} constants from mapss.md")
    print(f"  Runtime snapshot has {len(snapshot)} keys")
    print(f"  Manifest has {len(manifest)} constants")

    all_drifts: list[str] = []

    # 1. snapshot vs mapss.md
    d1 = compare(snapshot, spec, "runtime", "mapss.md")
    if d1:
        all_drifts.append("Runtime vs mapss.md:")
        all_drifts.extend(d1)

    # 2. snapshot vs manifest
    if manifest:
        d2 = compare(snapshot, manifest, "runtime", "manifest")
        if d2:
            all_drifts.append("Runtime vs strategy_surface_manifest.json:")
            all_drifts.extend(d2)

    # 3. mapss.md vs manifest
    if manifest:
        d3 = compare(spec, manifest, "mapss.md", "manifest")
        if d3:
            all_drifts.append("mapss.md vs strategy_surface_manifest.json:")
            all_drifts.extend(d3)

    if all_drifts:
        print(f"\nDRIFT DETECTED ({len(all_drifts)} lines):")
        for d in all_drifts:
            print(d)
        print("\nFix the disagreeing source(s) to match.")
        sys.exit(1)
    else:
        print(f"  All {len(CORE_KEYS)} core constants agree across all sources.")
        print("No spec drift detected.")


if __name__ == "__main__":
    main()
