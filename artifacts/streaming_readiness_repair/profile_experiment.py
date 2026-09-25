"""Run only through isolated_test_runner.py; every input bar is synthetic.

The outer runner supplies a clean environment, network denial and installed
credential/brain read and write denial. This child adds explicit feature
timeframe settings before platform import; it never sources an env file.
"""

import json
import os
from pathlib import Path
import subprocess
import sys


def test_offline_20_69_profile(tmp_path):
    root = Path(__file__).resolve().parents[2]
    output = root / "artifacts/streaming_readiness_repair"
    report_path = output / "profile_results.json"
    env = {**os.environ, "ORGANISM_LIVE_TIMEFRAME": "1Min", "ORGANISM_LIVE_LOOKBACK": "500",
           "ORGANISM_MIN_BARS": "50", "PYTHONPATH": str(root)}
    args = [sys.executable, "-B", str(root / "scripts/diagnostics/profile_paper_pipeline.py"),
            "--loads", "20", "69", "--rows", "500", "--repeats", "3", "--profile",
            "--output", str(report_path)]
    log_path = output / "profile_experiment_final.log"
    with log_path.open("x") as log:
        result = subprocess.run(args, cwd=tmp_path, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
    assert result.returncode == 0, f"See the retained synthetic-only {log_path.name}"
    report = json.loads(report_path.read_text())
    assert report["source_unchanged_during_run"]
    for run, count in zip(report["runs"], (20, 69), strict=True):
        assert run["universe_count"] == count
        assert run["rest_fallback_calls"] == 0
        assert run["outputs_identical"] and run["input_unchanged"]
        assert len(run["passes"]) == 4
        for iteration in run["passes"]:
            assert iteration["feature_output_count"] == count
            assert all(stage["calls"] == count for stage in iteration["stages"].values())
