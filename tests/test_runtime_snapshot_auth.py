"""Tests for runtime snapshot auth token acquisition."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock


def test_auth_uses_default_credentials_when_env_unset():
    """When INTRA_API_USER/PASSWORD are not set, defaults are used."""
    # Import the function
    import importlib
    import scripts.runtime.write_runtime_snapshot as snap_mod
    importlib.reload(snap_mod)

    # Patch env to ensure vars are unset, and patch urlopen
    env_without = {k: v for k, v in os.environ.items()
                   if k not in ("INTRA_API_USER", "INTRA_API_PASSWORD")}

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"access_token": "test_token"}).encode()
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with patch.dict(os.environ, env_without, clear=True), \
         patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
        token = snap_mod._get_auth_token("http://localhost:8000")
        assert token == "test_token"

        # Verify the request used default credentials
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data.decode())
        assert body["username"] == "admin@example.com"
        assert body["password"] == "admin123"


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
