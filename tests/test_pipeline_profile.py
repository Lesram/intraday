"""Synthetic feature profiling proves real computation and explicit isolation."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from scripts.diagnostics.profile_paper_pipeline import frame_hash, require_offline, synthetic_bars


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/diagnostics/profile_paper_pipeline.py"


@pytest.mark.parametrize("key", ["TESTING", "USE_MOCK_DATA", "USE_MOCK_BROKER"])
def test_requires_explicit_offline_configuration(monkeypatch, key):
    for name in ("TESTING", "USE_MOCK_DATA", "USE_MOCK_BROKER"):
        monkeypatch.setenv(name, "true")
    monkeypatch.setenv("ORGANISM_LIVE_TIMEFRAME", "1Min")
    monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="test isolation"):
        require_offline()


def test_history_is_causal_and_hash_detects_same_timestamp_correction():
    early = synthetic_bars(2, 80)
    later = synthetic_bars(2, 100)
    pd.testing.assert_frame_equal(early, later.iloc[:80])
    assert early.timestamp.dt.tz is not None
    assert early.timestamp.is_monotonic_increasing
    original = frame_hash(early)
    corrected = early.copy(deep=True)
    corrected.loc[79, "close"] += 0.01
    assert corrected.timestamp.equals(early.timestamp)
    assert frame_hash(corrected) != original
    assert frame_hash(early) == original


@pytest.mark.parametrize("feature_store", [True, False])
@pytest.mark.timeout(120)
def test_real_streaming_feeder_recomputes_unchanged_bars_and_held_symbol(tmp_path, feature_store):
    output = tmp_path / "profile.json"
    env = {**os.environ, "TESTING": "true", "USE_MOCK_DATA": "true", "USE_MOCK_BROKER": "true",
           "ORGANISM_LIVE_TIMEFRAME": "1Min", "ORGANISM_LIVE_LOOKBACK": "80", "ORGANISM_MIN_BARS": "50",
           "PYTHONPATH": str(ROOT), "PYTHONDONTWRITEBYTECODE": "1"}
    command = [sys.executable, "-B", str(SCRIPT), "--loads", "2", "--rows", "80", "--repeats", "2",
               "--profile", "--held-symbol", "--output", str(output)]
    if not feature_store:
        command.append("--no-feature-store")
    process = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=110)
    assert process.returncode == 0, process.stdout[-3000:] + process.stderr[-3000:]
    report = json.loads(output.read_text())
    assert report["source_unchanged_during_run"] is True
    run = report["runs"][0]
    assert run["history_prefill_calls"] == ["SPY", "SYN001", "HELD"]
    assert run["rest_fallback_calls"] == 0
    assert run["input_unchanged"] and run["outputs_identical"]
    assert run["universe_count"] == 2 and run["held_only_count"] == 1
    assert len(run["passes"]) == 3
    assert [p["kind"] for p in run["passes"]] == ["timed", "timed", "profiled"]
    for iteration in run["passes"]:
        assert iteration["feature_output_count"] == 3
        assert set(iteration["output_hashes"]) == {"SPY", "SYN001", "HELD"}
        assert iteration["output_hashes"] == run["passes"][0]["output_hashes"]
        # Real feature-store QA/engineering drops warmup rows before alignment.
        assert 50 <= min(iteration["output_rows"].values()) <= 80
        if not feature_store:
            assert min(iteration["output_rows"].values()) == 80
        assert min(iteration["output_columns"].values()) > 70
        assert iteration["wall_seconds"] > 0 and iteration["process_cpu_seconds"] > 0
        stages = iteration["stages"]
        assert stages["ml_features"]["calls"] == 3
        assert stages["multi_timeframe"]["calls"] == 3
        assert ("feature_store" in stages) == feature_store
        if feature_store:
            assert stages["feature_store"]["calls"] == 3
        assert stages["ml_features"]["worker_threads"] >= 1
    profiled = run["passes"][-1]["stages"]["ml_features"]
    assert any(row["function"] == "compute_ml_features" for row in profiled["top_cumulative_cpu"])
    assert profiled["summed_thread_cpu_seconds"] > 0


def test_cli_refuses_wrong_timeframe_before_platform_import(tmp_path):
    env = {**os.environ, "TESTING": "true", "USE_MOCK_DATA": "true", "USE_MOCK_BROKER": "true",
           "ORGANISM_LIVE_TIMEFRAME": "1Day"}
    process = subprocess.run([sys.executable, "-B", str(SCRIPT), "--output", str(tmp_path / "bad.json")],
                             cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert process.returncode != 0
    assert "requires explicit 1Min" in process.stderr
    assert not (tmp_path / "bad.json").exists()
    assert not (tmp_path / "logs").exists()
