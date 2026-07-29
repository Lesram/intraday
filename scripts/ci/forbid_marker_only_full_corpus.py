"""V13 W97 (Lens 6: Test / CI Quality) — full-corpus marker-only ratchet.

V12 W73 only gated CRITICAL/HIGH closures.  W97 expands the gate to
the entire wave-test corpus: ``test_wave*_fixes.py``,
``test_v??_w*.py``, ``test_v??_wave*.py``.

Behavior:
- Run ``classify_wave_tests --full-corpus``.
- Compare marker-only ratio against the V13 W97 baseline (committed
  to ``artifacts/audit/v13/marker_only_baseline.json``).
- Pass iff current_marker_only_count <= baseline_marker_only_count.
- If the baseline records exact marker-only test IDs, fail on any new
  marker-only test even when the aggregate count is unchanged.
- An ABSOLUTE ratio target of 30% remains the long-run goal — call
  it out in stdout but don't gate on it (would block all merges
  until the legacy backlog is converted, which is V13.1+ work).

Trend ratchet, not absolute:
- This is a *ratchet* — moving the count down, never up.
- Re-baselining requires explicit ``--update-baseline`` flag (same
  pattern as V12 W75 lint_ratchet).

Usage:
    python scripts/ci/forbid_marker_only_full_corpus.py
    python scripts/ci/forbid_marker_only_full_corpus.py --update-baseline
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = REPO_ROOT / "scripts" / "ci" / "classify_wave_tests.py"
BASELINE_PATH = REPO_ROOT / "artifacts" / "audit" / "v13" / "marker_only_baseline.json"

# V13 long-run goal — informational only.
TARGET_RATIO_PCT = 30.0


def _classify() -> dict:
    """Run the full-corpus classifier and return its summary dict."""
    proc = subprocess.run(
        [sys.executable, str(CLASSIFIER), "--full-corpus"],
        capture_output=True, text=True, check=True, timeout=60,
    )
    return json.loads(proc.stdout)


def _read_baseline() -> dict:
    if not BASELINE_PATH.is_file():
        return {"marker_only": None, "tests_total": None}
    return json.loads(BASELINE_PATH.read_text())


def _write_baseline(payload: dict) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _marker_test_ids(summary: dict) -> list[str]:
    tests = summary.get("tests") or []
    marker_tests = [
        f"{t.get('file')}::{t.get('name')}"
        for t in tests
        if t.get("classification") == "marker-only"
    ]
    return sorted(marker_tests)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="Record the current ratio as the new ratchet ceiling.",
    )
    args = parser.parse_args()

    summary = _classify()
    classification = summary.get("by_classification", {})
    tests_total = summary.get("tests_total", 0) or sum(classification.values())
    marker_only = classification.get("marker-only", 0)
    marker_tests = _marker_test_ids(summary)
    pct = (100.0 * marker_only / tests_total) if tests_total else 0.0
    files_scanned = summary.get("files_scanned", 0)

    print(
        f"V13 W97 full-corpus marker-only ratio: "
        f"{marker_only}/{tests_total} = {pct:.2f}%  "
        f"(files_scanned={files_scanned})"
    )

    baseline = _read_baseline()
    bl_marker = baseline.get("marker_only")
    bl_total = baseline.get("tests_total")
    if bl_marker is not None and bl_total:
        bl_pct = 100.0 * bl_marker / bl_total
        print(
            f"  baseline (committed): {bl_marker}/{bl_total} = {bl_pct:.2f}%"
        )
    else:
        print("  baseline: (not yet recorded)")

    print(f"  long-run target: <= {TARGET_RATIO_PCT}% (V13.1+ legacy conversion)")

    if args.update_baseline:
        _write_baseline({
            "marker_only": marker_only,
            "marker_tests": marker_tests,
            "tests_total": tests_total,
            "files_scanned": files_scanned,
            "pct": round(pct, 4),
        })
        print(f"  baseline updated → {BASELINE_PATH}")
        return 0

    if bl_marker is None:
        print(
            "\nFAIL: no baseline committed.  Run with --update-baseline to "
            "record the current ratio as the V13 W97 ratchet ceiling."
        )
        return 1

    if marker_only > bl_marker:
        print(
            f"\nFAIL: marker-only count regressed: {marker_only} > "
            f"baseline {bl_marker}.  Either fix the new marker tests or "
            f"explicitly raise the ceiling with --update-baseline (CI must "
            f"NOT silently raise — same pattern as V12 W75 lint_ratchet)."
        )
        return 1

    bl_marker_tests = baseline.get("marker_tests")
    if bl_marker_tests is not None:
        new_markers = sorted(set(marker_tests) - set(bl_marker_tests))
        if new_markers:
            sample = "\n  - ".join(new_markers[:10])
            print(
                "\nFAIL: new marker-only tests introduced outside the "
                f"grandfathered baseline ({len(new_markers)} new):\n"
                f"  - {sample}"
            )
            return 1

    if marker_only < bl_marker:
        print(
            f"\nPASS: marker-only count improved: {marker_only} <= "
            f"baseline {bl_marker} ({bl_marker - marker_only} tests "
            f"converted to behavioral).  Run --update-baseline to lower "
            f"the ratchet ceiling."
        )
    else:
        print(
            f"\nPASS: marker-only count steady at {marker_only}."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
