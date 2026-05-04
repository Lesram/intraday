"""Tests for runtime snapshot auth token acquisition."""
import json
import os
from unittest.mock import MagicMock, patch


def test_auth_returns_empty_token_when_env_unset():
    """V12 W89/W90 (post-cleanup, COMP-407/408): when env vars are
    unset, the auth helper now returns an empty token (was: silently
    fell back to dev admin credentials).  Failure is now visible
    instead of silent privilege escalation."""
    import importlib

    import scripts.runtime.write_runtime_snapshot as snap_mod
    importlib.reload(snap_mod)

    env_without = {
        k: v for k, v in os.environ.items()
        if k not in ("INTRA_API_USER", "INTRA_API_PASSWORD")
    }

    with (
        patch.dict(os.environ, env_without, clear=True),
        patch("urllib.request.urlopen") as mock_urlopen,
    ):
        token = snap_mod._get_auth_token("http://localhost:8000")
        # No env → empty token; helper must NOT have called urlopen.
        assert token == ""
        mock_urlopen.assert_not_called()


def test_auth_uses_env_credentials_when_set():
    """When INTRA_API_USER/PASSWORD are set, those are used."""
    import importlib

    import scripts.runtime.write_runtime_snapshot as snap_mod
    importlib.reload(snap_mod)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"access_token": "env_token"}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with (
        patch.dict(
            os.environ,
            {"INTRA_API_USER": "custom@test.com", "INTRA_API_PASSWORD": "secret"},
        ),
        patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen,
    ):
        token = snap_mod._get_auth_token("http://localhost:8000")
        assert token == "env_token"

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data.decode())
        assert body["username"] == "custom@test.com"
        assert body["password"] == "secret"


def test_auth_returns_empty_on_network_failure():
    """Network failure returns empty string (no crash)."""
    import importlib

    import scripts.runtime.write_runtime_snapshot as snap_mod
    importlib.reload(snap_mod)

    with patch("urllib.request.urlopen", side_effect=ConnectionError("refused")):
        token = snap_mod._get_auth_token("http://localhost:8000")
        assert token == ""


def test_legacy_runtime_snapshot_uses_resolved_config():
    """Legacy runtime_config_snapshot.json shape must carry resolved live
    values, not code defaults, so operator artifacts do not hide env
    overrides such as the paper drawdown limit."""
    import importlib

    import scripts.runtime.write_runtime_snapshot as snap_mod
    importlib.reload(snap_mod)

    defaults = {
        "drawdown_kill_pct": 0.05,
        "drawdown_cooldown_s": 3600,
        "max_changes_per_day": 100,
        "max_positions": 8,
        "max_daily_loss": 0.0,
        "max_notional_per_trade": 0.0,
    }
    resolved = {
        "container": "intra-api-1",
        "container_env": {"APP_ENVIRONMENT": "development", "ALPACA_PAPER": "true"},
        "resolution_sources": {
            "drawdown_kill_pct": "container_env",
            "max_daily_loss": "container_env",
        },
        "resolved": {
            "drawdown_kill_pct": 0.20,
            "drawdown_cooldown_s": 3600,
            "max_changes_per_day": 500,
            "max_positions": 8,
            "max_daily_loss": 5500.0,
            "max_notional_per_trade": 2000.0,
            "exploration_enabled": False,
        },
    }
    live = {
        "reachable": True,
        "process_env": {
            "ORGANISM_DRAWDOWN_KILL_PCT": "0.20",
            "ORGANISM_DRAWDOWN_COOLDOWN_S": "3600",
            "ORGANISM_MAX_CHANGES_PER_DAY": "500",
            "ORGANISM_MAX_POSITIONS": "8",
            "ORGANISM_MAX_DAILY_LOSS": "5500",
            "ORGANISM_MAX_NOTIONAL": "2000",
        },
    }

    legacy = snap_mod._build_legacy_runtime_snapshot(defaults, resolved, live)

    assert legacy["snapshot_source"] == "resolved_config_snapshot"
    assert legacy["drawdown_kill_pct"] == 0.20
    assert legacy["max_daily_loss"] == 5500.0
    assert legacy["code_defaults"]["drawdown_kill_pct"] == 0.05
    assert legacy["config_truth_status"]["status"] == "consistent"


def test_runtime_snapshot_truth_status_detects_drift():
    import importlib

    import scripts.runtime.write_runtime_snapshot as snap_mod
    importlib.reload(snap_mod)

    resolved = {"resolved": {"drawdown_kill_pct": 0.05}}
    live = {"process_env": {"ORGANISM_DRAWDOWN_KILL_PCT": "0.20"}}

    status = snap_mod._assess_config_truth(resolved, live)

    assert status["status"] == "drift"
    assert status["mismatches"][0]["key"] == "drawdown_kill_pct"
