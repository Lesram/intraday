"""Developer API tools require supplied credentials; all transport is synthetic."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import requests

from scripts.ci import validate_checklist as checklist
from scripts.testing import performance_test as performance


@pytest.fixture(autouse=True)
def no_real_transport(monkeypatch):
    monkeypatch.delenv("INTRA_API_TOKEN", raising=False)
    login = MagicMock(side_effect=AssertionError("No automatic identity/login allowed"))
    monkeypatch.setitem(sys.modules, "scripts.get_token", SimpleNamespace(get_jwt_token=login))
    session = MagicMock(name="offline_requests_session")
    session_factory = MagicMock(return_value=session)
    monkeypatch.setattr(checklist.requests, "Session", session_factory)
    monkeypatch.setattr(requests, "post", MagicMock(side_effect=AssertionError("No POST allowed")))
    monkeypatch.setattr(performance.aiohttp, "ClientSession", MagicMock(
        side_effect=AssertionError("Use an explicit fake HTTP session in tests")))
    yield SimpleNamespace(session=session, factory=session_factory, login=login)


def make_tool(tool, **kwargs):
    cls = performance.PerformanceTest if tool == "performance" else checklist.StagingChecklistValidator
    return cls(**kwargs)


@pytest.mark.parametrize("tool", ["performance", "checklist"])
@pytest.mark.parametrize("token", [None, "", "   ", "unsafe\nheader"])
def test_missing_or_invalid_token_fails_before_client_or_login(tool, token, no_real_transport):
    with pytest.raises(ValueError, match="INTRA_API_TOKEN"):
        make_tool(tool, api_token=token)
    no_real_transport.factory.assert_not_called()
    no_real_transport.login.assert_not_called()
    performance.aiohttp.ClientSession.assert_not_called()
    requests.post.assert_not_called()


@pytest.mark.parametrize("tool", ["performance", "checklist"])
def test_explicit_token_precedes_environment(tool, monkeypatch, no_real_transport):
    monkeypatch.setenv("INTRA_API_TOKEN", "environment-fixture-token")
    instance = make_tool(tool, api_token="explicit-fixture-token")
    assert instance.api_token == "explicit-fixture-token"
    no_real_transport.login.assert_not_called()


@pytest.mark.parametrize("tool", ["performance", "checklist"])
def test_environment_token_used_when_argument_omitted(tool, monkeypatch, no_real_transport):
    monkeypatch.setenv("INTRA_API_TOKEN", "environment-fixture-token")
    instance = make_tool(tool)
    assert instance.api_token == "environment-fixture-token"
    no_real_transport.login.assert_not_called()


@pytest.mark.parametrize("tool", ["performance", "checklist"])
def test_invalid_explicit_token_does_not_fall_back_to_environment(tool, monkeypatch):
    monkeypatch.setenv("INTRA_API_TOKEN", "environment-fixture-token")
    with pytest.raises(ValueError, match="INTRA_API_TOKEN"):
        make_tool(tool, api_token="")


class FakeResponse:
    def __init__(self, status=200, body="{}"):
        self.status = status
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def text(self):
        return self.body


class FakeSession:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        protected = "/api/v1/" in url
        return FakeResponse(200 if not protected or kwargs.get("headers") else 401)


@pytest.mark.asyncio
async def test_performance_smoke_uses_supplied_header_only_for_authenticated_cases(
    monkeypatch, capsys, caplog
):
    token = "performance-fixture-token"
    session = FakeSession()
    monkeypatch.setattr(performance.aiohttp, "ClientSession", lambda: session)
    monkeypatch.setattr(performance.asyncio, "sleep", AsyncMock())
    tool = performance.PerformanceTest(api_token=token)
    await tool.run_smoke_test(num_requests=1)
    authenticated = [call for call in session.calls if call[2].get("headers")]
    assert len(authenticated) == 6  # One signal request and five positions requests.
    assert all(call[2]["headers"] == {"Authorization": f"Bearer {token}"}
               for call in authenticated)
    assert all(call[0] == "GET" for call in session.calls)
    assert tool.errors == []
    assert token not in capsys.readouterr().out + caplog.text


def test_checklist_auth_checks_preserve_header_and_do_not_login(no_real_transport, caplog):
    token = "checklist-fixture-token"
    no_real_transport.session.get.side_effect = lambda *args, **kwargs: SimpleNamespace(
        status_code=200 if kwargs.get("headers") else 401)
    tool = checklist.StagingChecklistValidator(api_token=token)
    tool.check_auth_endpoints()
    calls = no_real_transport.session.get.call_args_list
    assert len(calls) == 6
    assert all("headers" not in call.kwargs for call in calls[:4])
    assert all(call.kwargs["headers"] == {"Authorization": f"Bearer {token}"}
               for call in calls[4:])
    assert tool.results["authentication"]["overall_status"] == "PASS"
    no_real_transport.login.assert_not_called()
    requests.post.assert_not_called()
    assert token not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["response", "exception"])
@pytest.mark.parametrize("token", ["short-fixture-token", "long-fixture-token-" * 12])
async def test_performance_errors_redact_before_truncation(failure, token, capsys, caplog):
    tool = performance.PerformanceTest(api_token=token)
    session = FakeSession()
    if failure == "response":
        session.request = lambda *a, **kw: FakeResponse(500, f"reflected credential: {token}")
    else:
        session.request = MagicMock(side_effect=RuntimeError(f"reflected credential: {token}"))
    await tool.test_endpoint(session, "failure", "GET", "/test")
    assert tool.errors and "[REDACTED]" in tool.errors[0]
    tool.generate_report()
    text = json.dumps(tool.errors) + capsys.readouterr().out + caplog.text
    assert token not in text and token[:50] not in text


def test_checklist_request_errors_redact_results(no_real_transport, caplog):
    token = "checklist-error-fixture-token"
    no_real_transport.session.get.side_effect = requests.RequestException(
        f"reflected credential: {token}")
    tool = checklist.StagingChecklistValidator(api_token=token)
    tool.check_auth_endpoints()
    tool.check_route_registry()
    output = json.dumps(tool.results) + caplog.text
    assert "[REDACTED]" in output
    assert token not in output


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["performance", "checklist"])
async def test_cli_missing_token_exits_before_http(tool, monkeypatch, no_real_transport, capsys):
    monkeypatch.setattr(sys, "argv", ["developer-tool"])
    with pytest.raises(SystemExit) as caught:
        if tool == "performance":
            await performance.main()
        else:
            checklist.main()
    assert caught.value.code == 2
    assert "INTRA_API_TOKEN" in capsys.readouterr().err
    no_real_transport.factory.assert_not_called()
    no_real_transport.login.assert_not_called()
    performance.aiohttp.ClientSession.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", ["performance", "checklist"])
async def test_cli_explicit_token_takes_priority(tool, monkeypatch, no_real_transport):
    token = "cli-fixture-token"
    monkeypatch.setenv("INTRA_API_TOKEN", "environment-fixture-token")
    monkeypatch.setattr(sys, "argv", ["developer-tool", "--api-token", token])
    observed = []
    if tool == "performance":
        async def smoke(self, num_requests):
            observed.append(self.api_token)
        monkeypatch.setattr(performance.PerformanceTest, "run_smoke_test", smoke)
        await performance.main()
    else:
        def checks(self):
            observed.append(self.api_token)
            return {"stub": {"overall_status": "PASS"}}
        monkeypatch.setattr(checklist.StagingChecklistValidator, "run_all_checks", checks)
        with pytest.raises(SystemExit) as caught:
            checklist.main()
        assert caught.value.code == 0
    assert observed == [token]
    no_real_transport.login.assert_not_called()


def test_checklist_cli_failure_log_does_not_echo_token(monkeypatch, caplog):
    token = "cli-error-fixture-token"
    monkeypatch.setattr(sys, "argv", ["checklist", "--api-token", token])
    monkeypatch.setattr(checklist.StagingChecklistValidator, "run_all_checks", MagicMock(
        side_effect=RuntimeError(f"reflected credential: {token}")))
    with pytest.raises(SystemExit) as caught:
        checklist.main()
    assert caught.value.code == 1
    assert "[REDACTED]" in caplog.text and token not in caplog.text
