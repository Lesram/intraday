"""Snapshot must state the source gate without certifying an unobserved runtime."""
from unittest.mock import patch

from scripts.runtime import write_runtime_snapshot as snapshot


def test_snapshot_reports_actual_final_admission_constant():
    from backend.organism.entry_freshness import ENTRY_TIMEFRAME, MAX_ENTRY_BAR_AGE_SECONDS
    defaults = snapshot._build_defaults_snapshot()
    assert defaults["entry_freshness"] == {
        "required_timeframe": ENTRY_TIMEFRAME,
        "max_bar_age_seconds": MAX_ENTRY_BAR_AGE_SECONDS,
        "minimum_bar_age_seconds": 0.0,
        "timestamp_semantics": "provider_bar_start_utc",
        "checked_at": "final_entry_submission",
        "missing_or_invalid_timestamp": "reject_entry",
        "protective_exits_exempt": True,
    }
    assert MAX_ENTRY_BAR_AGE_SECONDS == 120.0
    assert ENTRY_TIMEFRAME == "1Min"
    with patch.object(snapshot, "_find_api_container", return_value=""):
        resolved = snapshot._build_resolved_config_snapshot()
    assert resolved["resolved"]["entry_freshness"] == defaults["entry_freshness"]
    legacy = snapshot._build_legacy_runtime_snapshot(defaults, resolved, {"reachable": False})
    assert legacy["entry_freshness"] == defaults["entry_freshness"]
    assert legacy["config_truth_status"]["status"] == "unverified"


def test_offline_daily_snapshot_discloses_incompatible_entry_timeframe(monkeypatch):
    monkeypatch.setattr("backend.organism.live_engine.LIVE_TIMEFRAME", "1Day")
    defaults = snapshot._build_defaults_snapshot()
    assert defaults["timeframe"] == "1Day"
    assert defaults["entry_freshness"]["required_timeframe"] == "1Min"
    with patch.object(snapshot, "_find_api_container", return_value=""):
        resolved = snapshot._build_resolved_config_snapshot()
    assert resolved["resolved"]["entry_freshness"]["required_timeframe"] == "1Min"
    assert resolved["engine_observed"] is False
