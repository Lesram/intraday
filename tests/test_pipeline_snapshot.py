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
        "ml_features", "composite_indicators", "alpaca_market_data_stream",
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


def test_snapshot_reads_transport_and_startup_bounds_without_runtime_claim():
    from backend.integrations.alpaca_market_data_stream import AlpacaMarketDataStream
    from backend.organism.streaming_data_provider import StreamingDataProvider

    with patch.object(AlpacaMarketDataStream, "SUBSCRIPTION_ACK_TIMEOUT_S", 1.25), \
            patch.object(AlpacaMarketDataStream, "SUBSCRIPTION_RETRY_INTERVAL_S", 3.5), \
            patch.object(StreamingDataProvider, "STARTUP_RETRY_INTERVAL_S", 17.0), \
            patch.object(StreamingDataProvider, "STARTUP_TIMEOUT_S", 11.0):
        defaults = snapshot._build_defaults_snapshot()
        with patch.object(snapshot, "_find_api_container", return_value=""):
            resolved = snapshot._build_resolved_config_snapshot()
    policy = defaults["streaming_subscription_sync"]
    assert policy["ack_timeout_seconds"] == 1.25
    assert policy["subscription_retry_interval_seconds"] == 3.5
    assert policy["startup_retry_interval_seconds"] == 17.0
    assert policy["startup_timeout_seconds"] == 11.0
    assert resolved["resolved"]["streaming_subscription_sync"] == policy
    assert resolved["engine_observed"] is False


def test_snapshot_binds_feature_producers_and_reads_actual_column_contract():
    from backend.organism import composite_indicators, ml_features

    with patch.object(composite_indicators, "COMPOSITE_COLUMNS", ["probe_column"]):
        defaults = snapshot._build_defaults_snapshot()
        with patch.object(snapshot, "_find_api_container", return_value=""):
            resolved = snapshot._build_resolved_config_snapshot()
    for name, module in (("ml_features", ml_features), ("composite_indicators", composite_indicators)):
        assert defaults["candidate_data_pipeline_sources"][name] == hashlib.sha256(
            inspect.getsource(module).encode()
        ).hexdigest()
    assert defaults["composite_feature_columns"] == ["probe_column"]
    assert resolved["resolved"]["composite_feature_columns"] == ["probe_column"]
    assert resolved["engine_observed"] is False


def test_snapshot_reads_pending_resolution_bounds_without_runtime_claim():
    from backend.organism import operator_cancellation

    with patch.object(operator_cancellation, "CALL_TIMEOUT", 1.5), \
            patch.object(operator_cancellation, "TOTAL_TIMEOUT", 9.0), \
            patch.object(operator_cancellation, "CONFIRM_ATTEMPTS", 2), \
            patch.object(operator_cancellation, "INVENTORY_LIMIT", 17):
        defaults = snapshot._build_defaults_snapshot()
        with patch.object(snapshot, "_find_api_container", return_value=""):
            resolved = snapshot._build_resolved_config_snapshot()
    policy = defaults["pending_entry_resolution"]
    assert policy["call_timeout_seconds"] == 1.5
    assert policy["total_timeout_seconds"] == 9.0
    assert policy["confirmation_attempts"] == 2
    assert policy["inventory_limit"] == 17
    assert resolved["resolved"]["pending_entry_resolution"] == policy
    assert resolved["engine_observed"] is False
