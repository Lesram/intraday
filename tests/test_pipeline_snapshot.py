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
