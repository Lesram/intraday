"""Tests for runtime snapshot auth token acquisition."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock


def test_auth_returns_empty_token_when_env_unset():
    """V12 W89/W90 (post-cleanup, COMP-407/408): when env vars are
    unset, the auth helper now returns an empty token (was: silently
    fell back to dev admin credentials).  Failure is now visible
    instead of silent privilege escalation."""
    import importlib
    import scripts.runtime.write_runtime_snapshot as snap_mod
    importlib.reload(snap_mod)

    env_without = {k: v for k, v in os.environ.items()
                   if k not in ("INTRA_API_USER", "INTRA_API_PASSWORD")}

    with patch.dict(os.environ, env_without, clear=True), \
         patch("urllib.request.urlopen") as mock_urlopen:
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

    with patch.dict(os.environ, {"INTRA_API_USER": "custom@test.com", "INTRA_API_PASSWORD": "secret"}), \
         patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
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
