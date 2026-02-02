"""
Lightweight test matrix runner with stable defaults.

Usage:
    python scripts/run_matrix.py [suite] [extra pytest args]
    python scripts/run_matrix.py --with-coverage [suite] [extra pytest args]

Suites:
    integration  -> runs tests marked integration
    chaos        -> runs tests marked chaos
    api          -> runs tests marked api
    unit         -> runs tests marked unit
    all          -> runs entire test suite

Stability defaults:
    - Isolated worker: xdist -n 1 (if pytest-xdist is installed)
    - Faulthandler enabled via PYTHONFAULTHANDLER=1
    - Timeouts via pytest.ini (thread method)

Coverage:
    Coverage is disabled by default to speed up local runs and avoid incidental
    threshold failures. Enable it with either --with-coverage or env WITH_COV=1.
    When enabled, this script runs tests under coverage and emits
    test_reports/coverage.xml.
"""

from __future__ import annotations

import os
import sys
import shlex
from typing import List, Optional
import subprocess


def _has_plugin(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def build_args(suite: str, extra: List[str], with_cov: bool) -> List[str]:
    args: List[str] = []

    # Disable pytest-cov unless explicitly enabled and plugin is present
    if not with_cov and _has_plugin("pytest_cov"):
        args.append("--no-cov")

    # Stable defaults
    # - quiet output, show slow tests
    # - single worker isolation to avoid cross-test leakage
    args.extend(["-q", "--durations=10", "--maxfail=1", "-s"]) 
    if _has_plugin("xdist"):
        args.extend(["-n", "1"])  # Use worker isolation only if xdist is installed

    # Map suite to markers
    suite = (suite or "").lower()
    marker_map = {
        "integration": "integration",
        "chaos": "chaos",
        "api": "api",
        "unit": "unit",
    }

    if suite and suite != "all":
        marker = marker_map.get(suite)
        if marker:
            args.extend(["-m", marker])
        else:
            # Treat as a -k expression if it's not a known suite
            args.extend(["-k", suite])

    # Append any extra pytest args
    args.extend(extra)
    return args


def main() -> int:
    try:
        import pytest  # type: ignore
    except Exception as exc:
        print(f"Error: pytest is required to run the matrix: {exc}")
        return 2

    # Parse CLI: first arg is suite, the rest are pytest args
    suite = "all"
    extra: List[str] = []
    with_cov = os.environ.get("WITH_COV", "0") == "1"

    if len(sys.argv) > 1:
        # Support a leading flag like --with-coverage
        argv = sys.argv[1:]
        if argv and argv[0] == "--with-coverage":
            with_cov = True
            argv = argv[1:]

        if argv:
            suite = argv[0]
            extra = argv[1:]

    # Support passing a single string of extra args (e.g., from CI)
    if len(extra) == 1 and (" " in extra[0] or "\t" in extra[0]):
        extra = shlex.split(extra[0])

    # Drop any explicit --with-coverage passed via extra
    extra = [a for a in extra if a != "--with-coverage"]

    args = build_args(suite, extra, with_cov)
    # Run from repo root to honor top-level pytest.ini if present. Walk upwards
    # and choose the top-most directory containing a pytest.ini.
    start_dir = os.path.dirname(__file__)
    cur = start_dir
    chosen: Optional[str] = None
    while True:
        if os.path.exists(os.path.join(cur, "pytest.ini")):
            chosen = cur if chosen is None else chosen  # remember first seen
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    # If multiple pytest.ini files exist in parents, prefer the highest (repo root)
    # by re-walking and storing the last seen.
    if chosen is not None:
        cur = start_dir
        last: Optional[str] = None
        while True:
            if os.path.exists(os.path.join(cur, "pytest.ini")):
                last = cur
            parent = os.path.dirname(cur)
            if parent == cur:
                break
            cur = parent
        os.chdir(last or chosen)
    else:
        # Fallback to repo root guess: three levels up from scripts/run_matrix.py
        os.chdir(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    # Ensure faulthandler is active for any hangs
    os.environ.setdefault("PYTHONFAULTHANDLER", "1")

    if with_cov:
        # Ensure coverage is available
        try:
            __import__("coverage")
        except Exception as exc:
            print(f"Error: --with-coverage requested but 'coverage' is not installed: {exc}")
            return 2

        # Run under coverage and emit XML report
        try:
            rc = subprocess.run([sys.executable, "-m", "coverage", "run", "-m", "pytest", *args]).returncode
        finally:
            # Attempt to generate XML even if tests failed
            os.makedirs("test_reports", exist_ok=True)
            subprocess.run([sys.executable, "-m", "coverage", "xml", "-o", os.path.join("test_reports", "coverage.xml")])
        return rc
    else:
        return pytest.main(args)


if __name__ == "__main__":
    raise SystemExit(main())
