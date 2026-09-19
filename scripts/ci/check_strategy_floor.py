"""V13 W94 (Lens 3: Strategy Expectancy) — CI floor gate.

The V13 framework named expectancy as Lens 3 and required a
configurable floor below which release-branch merges must fail.
W94 ships the mechanism; choosing the actual numeric floor is
product policy and is intentionally NOT defaulted to a hard value
in V13.

Behavior:

- Reads the env ``STRATEGY_FLOOR_TOTAL_PNL``.
- If unset / empty: gate is OPT-IN.  Exit 0 with a notice.
- If set: reads the brain's strategy-expectancy from
  ``organism_brain/manifest.json`` (or via
  ``scripts/ci/compute_strategy_expectancy.py`` fallback) and
  compares ``total_pnl >= floor``.
- Exit 0 if pass; exit 1 if the brain is below the floor.

Optional flags:
- ``--floor=<n>``: override env (used by tests).
- ``--brain-dir=<path>``: override default ``organism_brain``.

Recommended floors (operator-facing guidance, not enforced):
- ``-1500.0``: gives ~$1k of runway from V12 final (-$634.90).
- ``0.0``: any net-positive brain.  Aspirational; not realistic
  this quarter.

To wire into CI for release branches, set
``STRATEGY_FLOOR_TOTAL_PNL=<value>`` in the workflow's env block
for the release-branch job only.

Usage:
    python scripts/ci/check_strategy_floor.py
    STRATEGY_FLOOR_TOTAL_PNL=-1500 python scripts/ci/check_strategy_floor.py
    python scripts/ci/check_strategy_floor.py --floor=-1500
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_brain_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("ORGANISM_BRAIN_DIR")
    if env:
        return Path(env)
    return REPO_ROOT / "organism_brain"


def _read_expectancy(brain_dir: Path) -> dict[str, Any] | None:
    mpath = brain_dir / "manifest.json"
    if not mpath.is_file():
        return None
    try:
        m = json.loads(mpath.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    sx = m.get("strategy_expectancy")
    if isinstance(sx, dict):
        return sx
    return None


def _compute_from_csv(brain_dir: Path) -> dict[str, Any] | None:
    """Fallback: compute from CSV via the canonical helper."""
    csv_path = brain_dir / "trade_history.csv"
    if not csv_path.is_file():
        return None
    sys.path.insert(0, str(REPO_ROOT))
    try:
        import csv as _csv

        from backend.organism.strategy_expectancy import compute_from_pnls
    except ImportError:
        return None
    pnls: list[float] = []
    with csv_path.open() as fh:
        reader = _csv.DictReader(fh)
        for row in reader:
            try:
                pnls.append(float(row.get("pnl", 0)))
            except (TypeError, ValueError):
                continue
    return compute_from_pnls(pnls)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--floor", type=float, default=None,
                        help="Override STRATEGY_FLOOR_TOTAL_PNL env var.")
    parser.add_argument("--brain-dir", default=None,
                        help="Override organism_brain path.")
    parser.add_argument("--strict", action="store_true",
                        help="Fail (exit 2) if no expectancy data is "
                             "readable instead of exit 0.")
    args = parser.parse_args()

    floor: float | None = args.floor
    if floor is None:
        env = os.environ.get("STRATEGY_FLOOR_TOTAL_PNL")
        if env:
            try:
                floor = float(env)
            except ValueError:
                print(f"FAIL: STRATEGY_FLOOR_TOTAL_PNL={env!r} not parseable")
                return 2

    if floor is None:
        print("V13 W94 strategy floor gate: OPT-IN (no STRATEGY_FLOOR_TOTAL_PNL)")
        print("  Set STRATEGY_FLOOR_TOTAL_PNL=<value> to enable on release branch.")
        return 0

    brain_dir = _resolve_brain_dir(args.brain_dir)
    payload = _read_expectancy(brain_dir)
    if payload is None:
        payload = _compute_from_csv(brain_dir)
    if payload is None:
        msg = (
            f"V13 W94 strategy floor gate: NO DATA at {brain_dir} "
            f"(no manifest.json::strategy_expectancy and no trade_history.csv)"
        )
        print(msg)
        return 2 if args.strict else 0

    total_pnl = payload.get("total_pnl")
    n_trades = payload.get("n_trades", 0)
    if total_pnl is None:
        print("FAIL: payload missing total_pnl field")
        return 2
    try:
        total_pnl_f = float(total_pnl)
    except (TypeError, ValueError):
        print(f"FAIL: total_pnl={total_pnl!r} not parseable")
        return 2

    if total_pnl_f >= floor:
        print(
            f"V13 W94 strategy floor gate: PASS "
            f"total_pnl={total_pnl_f:.2f} >= floor={floor:.2f} "
            f"(n_trades={n_trades})"
        )
        return 0

    print(
        f"V13 W94 strategy floor gate: FAIL "
        f"total_pnl={total_pnl_f:.2f} < floor={floor:.2f} "
        f"(n_trades={n_trades}).  "
        f"Brain is below the configured release-branch floor; refuse merge."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
