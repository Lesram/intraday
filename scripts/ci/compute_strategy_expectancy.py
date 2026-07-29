"""V12 W70/W71/W80: compute brain expectancy stats from trade_history.csv.

V12 W80 (post-audit cleanup): refactored to USE
``backend.organism.strategy_expectancy.compute_from_pnls`` as the
single source of truth.  Pre-W80 this CLI duplicated the math and
returned a different schema (``sharpe_ratio`` + nested ``last_25`` /
``last_50``) than the runtime module (``sharpe_ratio_per_trade`` +
flat ``last_25_*`` / ``last_50_*``), which the V12 external auditor
caught.

Output schema is now identical to ``manifest["strategy_expectancy"]``
and the ``GET /api/v1/health/strategy`` endpoint payload, plus three
provenance fields the API doesn't carry (``csv_path``, ``csv_exists``,
``csv_mtime``).

Usage:
    python scripts/ci/compute_strategy_expectancy.py [--csv organism_brain/trade_history.csv]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

# Make ``backend`` importable when this script is invoked directly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.organism.strategy_expectancy import compute_from_pnls  # noqa: E402


def compute(csv_path: Path) -> dict:
    """Compute the canonical 13-field expectancy payload + provenance.

    Returns the SAME schema as the runtime module / API endpoint, plus:
    - ``csv_path``: absolute path read.
    - ``csv_exists``: bool.
    - ``csv_mtime``: float (seconds since epoch) or None.
    - ``error``: present only when something went wrong.
    """
    if not csv_path.exists():
        payload = compute_from_pnls([])
        payload.update({
            "csv_path": str(csv_path),
            "csv_exists": False,
            "csv_mtime": None,
            "error": "trade_history.csv not found",
        })
        return payload

    pnls: list[float] = []
    with csv_path.open() as fh:
        reader = csv.DictReader(fh)
        if "pnl" not in (reader.fieldnames or []):
            payload = compute_from_pnls([])
            payload.update({
                "csv_path": str(csv_path),
                "csv_exists": True,
                "csv_mtime": os.path.getmtime(csv_path),
                "error": "no pnl column",
                "fieldnames": list(reader.fieldnames or []),
            })
            return payload
        for row in reader:
            try:
                pnls.append(float(row["pnl"]))
            except (KeyError, ValueError, TypeError):
                continue

    payload = compute_from_pnls(pnls)
    payload.update({
        "csv_path": str(csv_path),
        "csv_exists": True,
        "csv_mtime": os.path.getmtime(csv_path),
    })
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv", default="organism_brain/trade_history.csv",
    )
    parser.add_argument(
        "--json", default="-",
    )
    args = parser.parse_args()
    out = compute(Path(args.csv))
    text = json.dumps(out, indent=2, sort_keys=True)
    if args.json == "-":
        print(text)
    else:
        Path(args.json).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
