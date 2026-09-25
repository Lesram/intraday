"""Candidate helper hashes are visible without certifying an installed runtime."""
import hashlib
import inspect
from unittest.mock import patch

from scripts.runtime import write_runtime_snapshot as snapshot


def test_snapshot_identifies_actual_scanner_source_without_runtime_claim():
    from backend.organism import market_scanner

    defaults = snapshot._build_defaults_snapshot()
    hashes = defaults["candidate_data_pipeline_sources"]
    assert set(hashes) == {
        "market_scanner", "streaming_data_provider", "live_engine_data", "staleness_admission",
        "streaming_universe_initialization", "streaming_subscription_sync",
        "streaming_subscription_timeout", "pipeline_diagnostics",
    }
    assert hashes["market_scanner"] == hashlib.sha256(
        inspect.getsource(market_scanner).encode()
    ).hexdigest()
    with patch.object(snapshot, "_find_api_container", return_value=""):
        resolved = snapshot._build_resolved_config_snapshot()
    assert resolved["resolved"]["candidate_data_pipeline_sources"] == hashes
    assert resolved["engine_observed"] is False
    legacy = snapshot._build_legacy_runtime_snapshot(defaults, resolved, {"reachable": False})
    assert legacy["candidate_data_pipeline_sources"] == hashes
    assert legacy["config_truth_status"]["status"] == "unverified"


def test_snapshot_reads_actual_subscription_deadline_without_runtime_claim():
    from backend.organism.live_engine import OrganismLiveEngine
    with patch.object(OrganismLiveEngine, "_STREAM_SUBSCRIPTION_SYNC_TIMEOUT_S", 7.5):
        defaults = snapshot._build_defaults_snapshot()
        with patch.object(snapshot, "_find_api_container", return_value=""):
            resolved = snapshot._build_resolved_config_snapshot()
    policy = defaults["streaming_subscription_sync"]
    assert policy["timeout_seconds"] == 7.5
    assert resolved["resolved"]["streaming_subscription_sync"] == policy
    assert resolved["engine_observed"] is False
