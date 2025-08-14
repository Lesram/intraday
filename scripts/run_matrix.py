#!/usr/bin/env python3
"""
Matrix test runner that executes pytest subsets sequentially with coverage and JUnit outputs.

Outputs:
- JUnit XML:   test_reports/junit/<subset>.xml
- Coverage XML: test_reports/coverage.xml (merged across runs via --cov-append)
- Coverage HTML: test_reports/coverage_html/

Usage:
    python scripts/run_matrix.py                  # run all subsets
    python scripts/run_matrix.py api ws           # run only specific subsets (space-separated)

Notes:
- This runner disables strict coverage gates during matrix runs (adds --cov-fail-under=0)
    to ensure artifacts are produced even if thresholds aren't met.
"""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path


SUBSETS = [
    "tests/api",
    "tests/ws",
    "tests/mlops",
    "tests/services",
    "tests/risk",
    "tests/integration",
]


def run():
    # Determine repo and project directories
    script_path = Path(__file__).resolve()
    project_dir = script_path.parent.parent  # algotrading_platform/

    # Reports directories
    reports_dir = project_dir / "test_reports"
    junit_dir = reports_dir / "junit"
    htmlcov_dir = reports_dir / "coverage_html"
    cov_xml_path = reports_dir / "coverage.xml"

    junit_dir.mkdir(parents=True, exist_ok=True)
    htmlcov_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Build environment: ensure backend package importable
    env = os.environ.copy()
    # Prepend project_dir to PYTHONPATH so `backend` resolves
    py_path = str(project_dir)
    env["PYTHONPATH"] = (
        py_path
        if not env.get("PYTHONPATH")
        else py_path + os.pathsep + env["PYTHONPATH"]
    )

    # Use current Python executable (works in venvs)
    py_exec = sys.executable

    print(f"Running matrix from: {project_dir}")
    print(f"Using Python: {py_exec}")
    print(f"PYTHONPATH: {env['PYTHONPATH']}")

    overall_rc = 0
    results = []

    # Allow selecting subsets via CLI args (use names without tests/ prefix)
    argv = sys.argv[1:]
    if argv:
        # Map args like "api ws" to paths under tests/
        selected = [f"tests/{arg.strip('/')}" for arg in argv]
    else:
        selected = SUBSETS

    for subset in selected:
        subset_path = project_dir / subset
        name = subset.replace("tests/", "").replace("/", "_") or "root"

        if not subset_path.exists():
            print(f"[SKIP] {subset} (not found)")
            results.append((name, "skipped", 0))
            continue

        junit_xml = junit_dir / f"{name}.xml"

        cmd = [
            py_exec,
            "-m",
            "pytest",
            str(subset_path),
            "--junitxml",
            str(junit_xml),
            "--cov=backend",
            f"--cov-report=xml:{cov_xml_path}",
            f"--cov-report=html:{htmlcov_dir}",
            "--cov-append",
            "--cov-fail-under=0",  # disable coverage gate for matrix runs
            "-o",
            "addopts=",
        ]

        print("\n=== Running subset:", subset, "===")
        try:
            rc = subprocess.call(cmd, cwd=str(project_dir), env=env)
        except KeyboardInterrupt:
            print("Interrupted by user.")
            rc = 130
        except Exception as e:
            print(f"[ERROR] Failed to run {subset}: {e}")
            rc = 1

        status = "ok" if rc == 0 else "fail"
        results.append((name, status, rc))
        overall_rc = overall_rc or rc

    print("\n=== Matrix Summary ===")
    for name, status, rc in results:
        print(f"- {name}: {status} (rc={rc})")

    print(f"\nJUnit:   {junit_dir}")
    print(f"Coverage XML: {cov_xml_path}")
    print(f"Coverage HTML: {htmlcov_dir}")

    sys.exit(overall_rc)


if __name__ == "__main__":
    run()
