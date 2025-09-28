"""
Comprehensive test module for backend/services/integration.py
Test Module 123: backend.services.integration
"""

import asyncio
import hmac
import hashlib
import json
import time
from typing import Any, Dict, List

import pytest

import sys
import os

# Add project root to path (align with existing tests convention)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.services.integration import (
    IntegrationType,
    DataFormat,
    AuthenticationType,
    WebhookStatus,
    AuthenticationConfig,
    RateLimitConfig,
    RetryConfig,
    WebhookConfig,
    DataMapping,
    IntegrationConfig,
    IntegrationRequest,
    IntegrationResponse,
    WebhookEvent,
    IntegrationMetrics,
    RateLimiter,
    DataTransformer,
    WebhookValidator,
    IntegrationConnector,
    RestApiConnector,
    WebhookProcessor,
    IntegrationService,
    get_integration_service,
    set_integration_service,
    make_api_request,
    register_api_integration,
    process_webhook_data,
)


class DummyConnector(IntegrationConnector):
    """A dummy connector to test IntegrationConnector logic without I/O."""

    def __init__(self, config: IntegrationConfig, responses: List[IntegrationResponse] | None = None):
        super().__init__(config)
        self._responses = responses or []
        self._idx = 0

    async def execute_request(self, request: IntegrationRequest) -> IntegrationResponse:
        if self._idx < len(self._responses):
            resp = self._responses[self._idx]
            self._idx += 1
            return resp
        # default success
        return IntegrationResponse(
            request_id=request.id,
            status_code=200,
            data={"ok": True},
            headers={},
            duration=0.01,
            success=True,
        )

    async def health_check(self) -> bool:
        return True


class DummyResponse:
    def __init__(self, status: int = 200, headers: Dict[str, str] | None = None, text_data: str = "{}", json_data: Any = None):
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        self._text = text_data
        self._json = json_data if json_data is not None else {}

    async def text(self):
        return self._text

    async def json(self):
        if isinstance(self._json, Exception):
            raise self._json
        return self._json

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class DummySession:
    def __init__(self, response: DummyResponse):
        self._response = response
        self.closed = False

    def request(self, **kwargs):
        response = self._response

        class _Ctx:
            async def __aenter__(self_inner):
                return response

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()

    async def close(self):
        self.closed = True


class TestRateLimiter:
    def test_can_make_request_and_limits(self, monkeypatch):
        cfg = RateLimitConfig(requests_per_minute=3, requests_per_hour=10, requests_per_day=20, burst_limit=2)
        rl = RateLimiter(cfg)

        base = 1_000_000.0
        monkeypatch.setattr(time, "time", lambda: base)

        # Initially allowed
        assert rl.can_make_request("int-1") is True
        rl.record_request("int-1")
        rl.record_request("int-1")
        # Burst limit (2 in last 10s) reached -> block
        assert rl.can_make_request("int-1") is False

        # Move time forward beyond 10s to reset burst
        monkeypatch.setattr(time, "time", lambda: base + 11)
        assert rl.can_make_request("int-1") is True

        # Fill minute limit
        for _ in range(cfg.requests_per_minute - 1):
            rl.record_request("int-1")
        assert rl.can_make_request("int-1") is False
        wait = rl.get_wait_time("int-1")
        assert wait >= 0

    def test_get_wait_time_default(self, monkeypatch):
        cfg = RateLimitConfig(requests_per_minute=1000)
        rl = RateLimiter(cfg)
        monkeypatch.setattr(time, "time", lambda: 123.0)
        # No records, should be zero wait
        assert rl.get_wait_time("x") == 0.0


class TestDataTransformer:
    def test_transform_basic_and_nested(self):
        tr = DataTransformer()
        data = {"user": {"name": " alice ", "age": "30"}}
        mappings = [
            DataMapping(source_field="user.name", target_field="profile.username", transformation="strip"),
            DataMapping(source_field="user.age", target_field="profile.age", transformation="int"),
        ]
        out = tr.transform_data(data, mappings)
        assert out == {"profile": {"username": "alice", "age": 30}}

    def test_missing_required_raises(self):
        tr = DataTransformer()
        with pytest.raises(ValueError):
            tr.transform_data({}, [DataMapping(source_field="missing.field", target_field="x.y", required=True)])

    def test_optional_with_default_and_custom_transform(self):
        tr = DataTransformer()
        tr.register_transformation("double", lambda v: v * 2)
        out = tr.transform_data({}, [
            DataMapping(source_field="a.b", target_field="z", transformation="double", default_value=5, required=False),
        ])
        assert out["z"] == 10

    def test_eval_expression_and_eval_failure(self, caplog):
        tr = DataTransformer()
        data = {"x": 3}
        # Valid expression
        out = tr.transform_data(data, [DataMapping(source_field="x", target_field="y", transformation="value + 4")])
        assert out["y"] == 7
        # Invalid expression logs warning, keeps original value
        out2 = tr.transform_data(data, [DataMapping(source_field="x", target_field="y", transformation="1/0", required=False)])
        assert out2["y"] == 3


class TestWebhookValidator:
    def test_validate_signature_and_timestamp(self):
        payload = b"{\"ping\":true}"
        secret = "topsecret"
        import hmac, hashlib

        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert WebhookValidator.validate_signature(payload, expected, secret) is True
        assert WebhookValidator.validate_signature(payload, f"sha256={expected}", secret) is True
        assert WebhookValidator.validate_signature(payload, "invalid", secret) is False
        assert WebhookValidator.validate_signature(payload, expected, secret, algorithm="md5") is False

        now = time.time()
        assert WebhookValidator.validate_timestamp(str(now)) is True
        assert WebhookValidator.validate_timestamp(str(now - 99999)) is False
        assert WebhookValidator.validate_timestamp("not-a-number") is False


class TestIntegrationConnectorHelpers:
    def build_config(self, auth: AuthenticationType, **kwargs) -> IntegrationConfig:
        return IntegrationConfig(
            id="int1",
            name="Int 1",
            type=IntegrationType.REST_API,
            base_url="https://example.com",
            authentication=AuthenticationConfig(type=auth, **kwargs),
        )

    @pytest.mark.asyncio
    async def test_prepare_headers_for_all_auth(self):
        # API_KEY
        cfg = self.build_config(AuthenticationType.API_KEY, api_key="k")
        conn = DummyConnector(cfg)
        h = conn._prepare_headers(IntegrationRequest(id="1", integration_id="int1", method="GET", endpoint="/e"))
        assert h["X-API-Key"] == "k"

        # BEARER_TOKEN
        cfg = self.build_config(AuthenticationType.BEARER_TOKEN, token="t")
        conn = DummyConnector(cfg)
        h = conn._prepare_headers(IntegrationRequest(id="2", integration_id="int1", method="GET", endpoint="/e"))
        assert h["Authorization"] == "Bearer t"

        # BASIC_AUTH
        cfg = self.build_config(AuthenticationType.BASIC_AUTH, username="u", password="p")
        conn = DummyConnector(cfg)
        h = conn._prepare_headers(IntegrationRequest(id="3", integration_id="int1", method="GET", endpoint="/e"))
        assert h["Authorization"].startswith("Basic ")

        # CUSTOM_HEADER
        cfg = self.build_config(AuthenticationType.CUSTOM_HEADER, header_name="X-Custom", header_value="V")
        conn = DummyConnector(cfg)
        h = conn._prepare_headers(IntegrationRequest(id="4", integration_id="int1", method="GET", endpoint="/e"))
        assert h["X-Custom"] == "V"

        # NONE
        cfg = self.build_config(AuthenticationType.NONE)
        conn = DummyConnector(cfg)
        h = conn._prepare_headers(IntegrationRequest(id="5", integration_id="int1", method="GET", endpoint="/e"))
        assert isinstance(h, dict)

    def test_update_metrics_success_and_failure(self):
        cfg = self.build_config(AuthenticationType.NONE)
        conn = DummyConnector(cfg)
        r1 = IntegrationResponse(request_id="1", status_code=200, data=None, headers={}, duration=0.2, success=True)
        r2 = IntegrationResponse(request_id="2", status_code=500, data=None, headers={}, duration=0.4, success=False)
        conn._update_metrics(r1)
        conn._update_metrics(r2)
        m = conn.metrics
        assert m.total_requests == 2
        assert m.successful_requests == 1
        assert m.failed_requests == 1
        assert abs(m.average_response_time - 0.3) < 1e-9


class TestRestApiConnector:
    @pytest.mark.asyncio
    async def test_execute_request_success_json(self, monkeypatch):
        cfg = IntegrationConfig(
            id="rest1",
            name="REST 1",
            type=IntegrationType.REST_API,
            base_url="https://api.example.com",
            authentication=AuthenticationConfig(type=AuthenticationType.NONE),
            data_format=DataFormat.JSON,
            timeout=5.0,
        )
        conn = RestApiConnector(cfg)

        dummy_resp = DummyResponse(status=200, text_data="{\"ok\": true}", json_data={"ok": True})
        dummy_session = DummySession(dummy_resp)
        
        # Create a single future and reuse it
        session_future = asyncio.Future()
        session_future.set_result(dummy_session)
        monkeypatch.setattr(conn, "_get_session", lambda: session_future)

        req = IntegrationRequest(id="r1", integration_id="rest1", method="GET", endpoint="/health")
        out = await conn.execute_request(req)
        assert out.success is True
        assert out.status_code == 200

        await conn.close()

    @pytest.mark.asyncio
    async def test_execute_request_text_and_json_parse_error(self, monkeypatch):
        cfg = IntegrationConfig(
            id="rest2",
            name="REST 2",
            type=IntegrationType.REST_API,
            base_url="https://api.example.com",
            authentication=AuthenticationConfig(type=AuthenticationType.NONE),
            data_format=DataFormat.JSON,
        )
        conn = RestApiConnector(cfg)
        # json() raises to ensure fallback to text
        dummy_resp = DummyResponse(status=500, text_data="ERR", json_data=ValueError("bad json"))
        f = asyncio.Future(); f.set_result(DummySession(dummy_resp))
        monkeypatch.setattr(conn, "_get_session", lambda: f)

        req = IntegrationRequest(id="r2", integration_id="rest2", method="POST", endpoint="/x", data={"a":1})
        out = await conn.execute_request(req)
        assert out.success is False
        assert out.status_code == 500
        assert "HTTP 500" in (out.error_message or "")

    @pytest.mark.asyncio
    async def test_rate_limited_and_exception_path(self, monkeypatch):
        cfg = IntegrationConfig(
            id="rest3",
            name="REST 3",
            type=IntegrationType.REST_API,
            base_url="https://api.example.com",
            authentication=AuthenticationConfig(type=AuthenticationType.NONE),
        )
        conn = RestApiConnector(cfg)

        # Rate-limited branch
        monkeypatch.setattr(conn.rate_limiter, "can_make_request", lambda _id: False)
        monkeypatch.setattr(conn.rate_limiter, "get_wait_time", lambda _id: 0)

        async def _noop_sleep(_):
            return None

        monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

        # Now make session .request raise an exception to test exception path
        class BadSession:
            def request(self, **kwargs):
                class _Ctx:
                    async def __aenter__(self_inner):
                        raise RuntimeError("boom")

                    async def __aexit__(self_inner, exc_type, exc, tb):
                        return False

                return _Ctx()

            async def close(self):
                return None

        f = asyncio.Future(); f.set_result(BadSession())
        monkeypatch.setattr(conn, "_get_session", lambda: f)

        req = IntegrationRequest(id="r3", integration_id="rest3", method="GET", endpoint="/err")
        out = await conn.execute_request(req)
        assert out.success is False
        assert out.status_code == 0

    @pytest.mark.asyncio
    async def test_health_check(self, monkeypatch):
        cfg = IntegrationConfig(
            id="rest4",
            name="REST 4",
            type=IntegrationType.REST_API,
            base_url="https://api.example.com",
            authentication=AuthenticationConfig(type=AuthenticationType.NONE),
        )
        conn = RestApiConnector(cfg)

        # Patch execute_request to return success True
        async def _ok(req):
            return IntegrationResponse(request_id=req.id, status_code=200, data={}, headers={}, duration=0.01, success=True)

        monkeypatch.setattr(conn, "execute_request", _ok)
        assert await conn.health_check() is True


class TestWebhookProcessor:
    @pytest.mark.asyncio
    async def test_process_webhook_success_and_handlers(self):
        processor = WebhookProcessor()
        calls: List[WebhookEvent] = []

        def handler(evt: WebhookEvent):
            calls.append(evt)

        async def async_handler(evt: WebhookEvent):
            calls.append(evt)

        processor.register_handler("order.created", handler)
        processor.register_handler("*", async_handler)

        cfg = WebhookConfig(id="wh1", url="https://cb.example.com", secret=None)
        headers = {cfg.timestamp_header: str(time.time())}
        payload = json.dumps({"type": "order.created", "id": 1}).encode()

        evt = await processor.process_webhook(cfg, headers, payload)
        assert evt.status == WebhookStatus.COMPLETED
        assert evt.processed_at is not None
        assert len(calls) == 2

        # Test invalid signature
        cfg2 = WebhookConfig(id="wh2", url="https://cb.example.com", secret="s")
        headers2 = {cfg2.signature_header: "sha256=bad"}
        evt2 = await processor.process_webhook(cfg2, headers2, payload)
        assert evt2.status == WebhookStatus.FAILED
        assert evt2.error_message == "Invalid signature"

        # Test invalid timestamp
        cfg3 = WebhookConfig(id="wh3", url="", secret=None)
        headers3 = {cfg3.timestamp_header: str(time.time() - 99999)}
        evt3 = await processor.process_webhook(cfg3, headers3, payload)
        assert evt3.status == WebhookStatus.FAILED
        assert evt3.error_message == "Timestamp too old"

        # Test invalid JSON
        bad_payload = b"{invalid json}"
        evt4 = await processor.process_webhook(cfg3, {}, bad_payload)
        assert evt4.status == WebhookStatus.FAILED
        assert "Failed to parse payload" in (evt4.error_message or "")


class TestIntegrationService:
    @pytest.mark.asyncio
    async def test_register_and_unregister_integration(self):
        svc = IntegrationService(health_check_interval=0)  # Disable health check for tests
        cfg = IntegrationConfig(
            id="i1",
            name="I1",
            type=IntegrationType.REST_API,
            base_url="https://api.example.com",
            authentication=AuthenticationConfig(type=AuthenticationType.NONE),
        )
        assert svc.register_integration(cfg) is True
        assert "i1" in svc.connectors and "i1" in svc.configurations
        assert svc.unregister_integration("i1") is True
        assert "i1" not in svc.connectors and "i1" not in svc.configurations

    def test_register_unknown_type(self, caplog):
        svc = IntegrationService(health_check_interval=0)  # Disable health check for tests
        cfg = IntegrationConfig(
            id="i2",
            name="I2",
            type=IntegrationType.GRAPHQL,
            base_url="https://api.example.com",
            authentication=AuthenticationConfig(type=AuthenticationType.NONE),
        )
        assert svc.register_integration(cfg) is False

    @pytest.mark.asyncio
    async def test_execute_request_error_paths_and_retries(self, monkeypatch):
        svc = IntegrationService(health_check_interval=0)  # Disable health check for tests
        cfg = IntegrationConfig(
            id="i3",
            name="I3",
            type=IntegrationType.REST_API,
            base_url="https://api.example.com",
            authentication=AuthenticationConfig(type=AuthenticationType.NONE),
            retry_config=RetryConfig(max_attempts=2, initial_delay=0, max_delay=0, backoff_factor=1.0),
        )
        svc.configurations[cfg.id] = cfg
        # Inject dummy connector that returns 500 then 200
        resp1 = IntegrationResponse(request_id="x", status_code=500, data=None, headers={}, duration=0.01, success=False)
        resp2 = IntegrationResponse(request_id="x", status_code=200, data=None, headers={}, duration=0.02, success=True)
        conn = DummyConnector(cfg, responses=[resp1, resp2])
        svc.connectors[cfg.id] = conn

        async def _noop_sleep(_):
            return None

        monkeypatch.setattr(asyncio, "sleep", _noop_sleep)

        req = IntegrationRequest(id="req1", integration_id="i3", method="GET", endpoint="/x")
        out = await svc.execute_request(req)
        assert out.success is True
        assert conn.metrics.total_retries >= 1

        # Now test all retries failed
        cfg2 = IntegrationConfig(
            id="i4",
            name="I4",
            type=IntegrationType.REST_API,
            base_url="https://api.example.com",
            authentication=AuthenticationConfig(type=AuthenticationType.NONE),
            retry_config=RetryConfig(max_attempts=1, initial_delay=0, max_delay=0),
        )
        svc.configurations[cfg2.id] = cfg2
        conn2 = DummyConnector(cfg2, responses=[resp1])
        svc.connectors[cfg2.id] = conn2
        req2 = IntegrationRequest(id="req2", integration_id="i4", method="GET", endpoint="/x")
        out2 = await svc.execute_request(req2)
        assert out2.success is False

    @pytest.mark.asyncio
    async def test_execute_request_integration_not_found_and_disabled(self):
        svc = IntegrationService(health_check_interval=0)  # Disable health check for tests
        # Not found
        req = IntegrationRequest(id="nf", integration_id="none", method="GET", endpoint="/")
        out = await svc.execute_request(req)
        assert out.success is False and "not found" in (out.error_message or "")

        # Disabled config
        cfg = IntegrationConfig(
            id="i5",
            name="I5",
            type=IntegrationType.REST_API,
            base_url="https://api.example.com",
            authentication=AuthenticationConfig(type=AuthenticationType.NONE),
            enabled=False,
        )
        svc.configurations[cfg.id] = cfg
        svc.connectors[cfg.id] = DummyConnector(cfg)
        req2 = IntegrationRequest(id="d", integration_id="i5", method="GET", endpoint="/")
        out2 = await svc.execute_request(req2)
        assert out2.success is False and "disabled" in (out2.error_message or "")

    def test_metrics_and_transform_helpers(self):
        svc = IntegrationService(health_check_interval=0)  # Disable health check for tests
        cfg = IntegrationConfig(
            id="i6",
            name="I6",
            type=IntegrationType.REST_API,
            base_url="https://api.example.com",
            authentication=AuthenticationConfig(type=AuthenticationType.NONE),
        )
        svc.configurations[cfg.id] = cfg
        svc.connectors[cfg.id] = DummyConnector(cfg)

        # No requests yet
        metrics_all = svc.get_integration_metrics()
        assert "i6" in metrics_all
        metrics_one = svc.get_integration_metrics("i6")
        assert "total_requests" in metrics_one["i6"]

        # Transform helpers
        svc.register_transformation("triple", lambda v: v * 3)
        out = svc.transform_data({"a": 2}, [DataMapping(source_field="a", target_field="b", transformation="triple")])
        assert out["b"] == 6


class TestGlobalFunctions:
    @pytest.mark.asyncio
    async def test_global_service_and_convenience_functions(self, monkeypatch):
        # Ensure global service can be set and retrieved
        s1 = IntegrationService(health_check_interval=0)  # Disable health check for tests
        set_integration_service(s1)
        assert get_integration_service() is s1

        # Register an API integration via convenience function
        ok = register_api_integration(
            integration_id="g1",
            base_url="https://api.example.com",
            auth_config=AuthenticationConfig(type=AuthenticationType.NONE),
            name="G1",
        )
        assert ok is True

        # Patch execute_request to avoid network
        async def fake_exec(req: IntegrationRequest):
            return IntegrationResponse(request_id=req.id, status_code=200, data={"ok": True}, headers={}, duration=0.01, success=True)

        s1.connectors["g1"].execute_request = fake_exec  # type: ignore

        resp = await make_api_request("g1", "GET", "/ping")
        assert resp.success is True and resp.status_code == 200

        # Webhook processing via convenience function
        wh_cfg = WebhookConfig(id="whg", url="https://cb.example.com", secret=None)
        s1.register_webhook(wh_cfg)
        evt = await process_webhook_data("whg", {wh_cfg.timestamp_header: str(time.time())}, json.dumps({"type": "x"}).encode())
        assert isinstance(evt, WebhookEvent)


def test_module_imports_and_dataclasses_instantiation():
    # Instantiate dataclasses to execute default factories
    _ = AuthenticationConfig(type=AuthenticationType.NONE)
    _ = RateLimitConfig()
    _ = RetryConfig()
    _ = WebhookConfig(id="w", url="u")
    _ = DataMapping(source_field="a", target_field="b")
    _ = IntegrationConfig(id="id", name="n", type=IntegrationType.REST_API, base_url="u", authentication=AuthenticationConfig(type=AuthenticationType.NONE))
    _ = IntegrationRequest(id="rid", integration_id="id", method="GET", endpoint="/")
    _ = IntegrationResponse(request_id="rid", status_code=200, data=None, headers={}, duration=0.0, success=True)
    _ = WebhookEvent(id="e", webhook_id="w", event_type="t", payload={}, headers={})
    _ = IntegrationMetrics(integration_id="id")


class TestAdditionalCoverage:
    """Additional tests to reach 100% coverage"""
    
    def test_rate_limiter_hour_and_day_limits(self, monkeypatch):
        """Test hour and day rate limiting"""
        cfg = RateLimitConfig(
            requests_per_minute=100,  # High minute limit
            requests_per_hour=2,      # Low hour limit
            requests_per_day=5,       # Low day limit
            burst_limit=100           # High burst limit
        )
        rl = RateLimiter(cfg)
        
        base_time = 1_000_000.0
        monkeypatch.setattr(time, "time", lambda: base_time)
        
        # Fill hour limit
        for _ in range(cfg.requests_per_hour):
            assert rl.can_make_request("test-id") is True
            rl.record_request("test-id")
        
        # Should be blocked by hour limit
        assert rl.can_make_request("test-id") is False
        
        # Move time forward 1 hour and 1 second
        monkeypatch.setattr(time, "time", lambda: base_time + 3661)
        
        # Should be allowed now
        assert rl.can_make_request("test-id") is True
        
        # Fill day limit
        for _ in range(cfg.requests_per_day - cfg.requests_per_hour):
            rl.record_request("test-id")
        
        # Should be blocked by day limit
        assert rl.can_make_request("test-id") is False
    
    def test_webhook_validator_timestamp_validation(self):
        """Test timestamp validation in webhook validator"""
        now = time.time()
        
        # Valid timestamp (within 5 minutes)
        assert WebhookValidator.validate_timestamp(str(int(now)), max_age_seconds=300) is True
        
        # Invalid timestamp (too old)
        old_timestamp = str(int(now - 400))  # 6+ minutes old  
        assert WebhookValidator.validate_timestamp(old_timestamp, max_age_seconds=300) is False
        
        # Invalid timestamp format
        assert WebhookValidator.validate_timestamp("invalid", max_age_seconds=300) is False
    
    def test_data_transformer_advanced_transformations(self):
        """Test advanced transformation features"""
        tr = DataTransformer()
        
        # Test upper and lower transformations (correct method names)
        data = {"text": "Hello World"}
        mappings = [
            DataMapping(source_field="text", target_field="upper_text", transformation="uppercase"),
            DataMapping(source_field="text", target_field="lower_text", transformation="lowercase"),
        ]
        result = tr.transform_data(data, mappings)
        assert result["upper_text"] == "HELLO WORLD"
        assert result["lower_text"] == "hello world"

        # Test bool transformation (Python bool() treats non-empty strings as True)
        data2 = {"flag": True, "flag2": False, "flag3": 1, "flag4": 0, "flag5": ""}
        mappings2 = [
            DataMapping(source_field="flag", target_field="bool1", transformation="bool"),
            DataMapping(source_field="flag2", target_field="bool2", transformation="bool"),
            DataMapping(source_field="flag3", target_field="bool3", transformation="bool"),
            DataMapping(source_field="flag4", target_field="bool4", transformation="bool"),
            DataMapping(source_field="flag5", target_field="bool5", transformation="bool"),
        ]
        result2 = tr.transform_data(data2, mappings2)
        assert result2["bool1"] is True
        assert result2["bool2"] is False
        assert result2["bool3"] is True
        assert result2["bool4"] is False
        assert result2["bool5"] is False

    def test_integration_service_webhook_methods(self):
        """Test webhook-related methods in IntegrationService"""
        svc = IntegrationService(health_check_interval=0)
        
        # Test register webhook (returns None but adds to configs)
        webhook_cfg = WebhookConfig(
            id="test-webhook",
            url="https://example.com/webhook"
        )
        svc.register_webhook(webhook_cfg)  # Returns None
        assert "test-webhook" in svc.webhook_configs
        
        # Test unregister webhook
        svc.unregister_webhook("test-webhook")
        assert "test-webhook" not in svc.webhook_configs

    def test_rate_limiter_cleanup_old_timestamps(self, monkeypatch):
        """Test cleanup of old timestamps in rate limiter"""
        cfg = RateLimitConfig(requests_per_minute=10, burst_limit=5)
        rl = RateLimiter(cfg)
        
        base_time = 1_000_000.0
        monkeypatch.setattr(time, "time", lambda: base_time)
        
        # Add some requests
        for _ in range(3):
            rl.record_request("cleanup-test")
        
        # Move time forward significantly to trigger cleanup
        monkeypatch.setattr(time, "time", lambda: base_time + 100000)  # Way in the future
        
        # This should trigger cleanup of old timestamps
        rl.record_request("cleanup-test")
        
        # Verify the old timestamps were cleaned up
        times = rl._request_times["cleanup-test"]
        assert len(times) <= 1  # Only the most recent request should remain

    def test_webhook_validator_signature_algorithms(self):
        """Test different signature algorithms"""
        payload = b'{"test": "data"}'
        secret = "test-secret"
        
        # Test SHA256 (default)
        expected_sha256 = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        assert WebhookValidator.validate_signature(payload, expected_sha256, secret) is True
        assert WebhookValidator.validate_signature(payload, f"sha256={expected_sha256}", secret) is True
        
        # Test invalid algorithm (should return False)
        assert WebhookValidator.validate_signature(payload, "invalid", secret, algorithm="md5") is False
        assert WebhookValidator.validate_signature(payload, "invalid", secret, algorithm="invalid") is False

    def test_custom_transformation_registration(self):
        """Test registering custom transformations"""
        tr = DataTransformer()
        
        # Register a custom transformation
        def reverse_string(value):
            return str(value)[::-1]
        
        tr.register_transformation("reverse", reverse_string)
        
        # Use the custom transformation
        data = {"text": "hello"}
        mappings = [DataMapping(source_field="text", target_field="reversed", transformation="reverse")]
        result = tr.transform_data(data, mappings)
        assert result["reversed"] == "olleh"


if __name__ == "__main__":
    pytest.main([__file__])
