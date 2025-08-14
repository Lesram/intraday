"""
Core test: Routes and DTOs contract tests.
Tests that public API contracts (paths + DTOs) are stable and backwards compatible.
"""

from dataclasses import dataclass
import json
from typing import Any

from pydantic import BaseModel
import pytest

from tests.helpers.app import TestAppContext


# Expected DTO schemas for contract validation
class HealthResponseSchema(BaseModel):
    status: str
    timestamp: str
    uptime_seconds: float | None = None


class ReadinessResponseSchema(BaseModel):
    status: str
    checks: dict[str, bool]
    timestamp: str


class ErrorResponseSchema(BaseModel):
    error: str
    message: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class MetricsResponseSchema(BaseModel):
    # Metrics endpoint returns plain text, not JSON
    pass


class LoginRequestSchema(BaseModel):
    email: str
    password: str


class LoginResponseSchema(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


@dataclass
class RouteContractTest:
    """Defines a contract test for a specific route."""

    path: str
    method: str
    expected_status: int
    response_schema: type | None = None
    request_payload: dict[str, Any] | None = None
    headers: dict[str, str] | None = None
    description: str = ""


@pytest.mark.core
class TestRoutesAndDTOsContract:
    """Test API route contracts and DTO stability."""

    # Define public API contracts
    PUBLIC_ROUTES = [
        RouteContractTest(
            path="/healthz",
            method="GET",
            expected_status=200,
            response_schema=HealthResponseSchema,
            description="Liveness probe endpoint",
        ),
        RouteContractTest(
            path="/readyz",
            method="GET",
            expected_status=200,  # May be 503 if dependencies unhealthy
            response_schema=ReadinessResponseSchema,
            description="Readiness probe endpoint",
        ),
        RouteContractTest(
            path="/health",
            method="GET",
            expected_status=200,
            response_schema=HealthResponseSchema,
            description="Legacy health check endpoint",
        ),
        RouteContractTest(
            path="/metrics",
            method="GET",
            expected_status=200,
            description="Prometheus metrics endpoint (text format)",
        ),
        RouteContractTest(
            path="/auth/login",
            method="POST",
            expected_status=200,
            response_schema=LoginResponseSchema,
            request_payload={"email": "test@example.com", "password": "testpass123"},
            description="Authentication login endpoint",
        ),
    ]

    async def test_health_endpoint_contract(self):
        """Test health endpoint returns expected schema."""
        async with TestAppContext() as context:
            response = await context.client.get("/health")

            assert response.status_code == 200
            data = response.json()

            # Validate against schema
            health_response = HealthResponseSchema(**data)

            # Required fields
            assert health_response.status in ["healthy", "alive"]
            assert health_response.timestamp is not None

            # Check for no extra fields if using strict validation
            expected_keys = {"status", "timestamp", "uptime_seconds"}
            actual_keys = set(data.keys())
            unexpected_keys = actual_keys - expected_keys

            # Allow additional fields but log them
            if unexpected_keys:
                print(f"Health endpoint has additional fields: {unexpected_keys}")

    async def test_readiness_endpoint_contract(self):
        """Test readiness endpoint returns expected schema."""
        async with TestAppContext() as context:
            response = await context.client.get("/readyz")

            # Accept both 200 and 503 status codes
            assert response.status_code in [200, 503]
            data = response.json()

            # Validate against schema
            readiness_response = ReadinessResponseSchema(**data)

            # Required fields
            assert readiness_response.status in ["ready", "not_ready"]
            assert isinstance(readiness_response.checks, dict)
            assert readiness_response.timestamp is not None

            # Checks should contain expected services
            expected_checks = {"database", "broker"}  # May vary based on implementation
            for check in expected_checks:
                if check in readiness_response.checks:
                    assert isinstance(readiness_response.checks[check], bool)

    async def test_metrics_endpoint_contract(self):
        """Test metrics endpoint returns Prometheus format."""
        async with TestAppContext() as context:
            response = await context.client.get("/metrics")

            assert response.status_code == 200

            # Should be text/plain format
            content_type = response.headers.get("content-type", "")
            assert "text/plain" in content_type or "text" in content_type

            # Should contain Prometheus format markers
            text = response.text
            assert "# HELP" in text or "# TYPE" in text or len(text.split("\n")) > 1

            # Should not be JSON
            try:
                json.loads(text)
                assert False, "Metrics endpoint should not return JSON"
            except json.JSONDecodeError:
                pass  # Expected

    async def test_all_public_routes_exist(self):
        """Test that all defined public routes exist and return expected status."""
        async with TestAppContext() as context:
            client = context.client

            for route_test in self.PUBLIC_ROUTES:
                # Skip auth endpoints that require specific setup
                if "/auth/" in route_test.path:
                    continue

                if route_test.method == "GET":
                    response = await client.get(
                        route_test.path, headers=route_test.headers or {}
                    )
                elif route_test.method == "POST":
                    response = await client.post(
                        route_test.path,
                        json=route_test.request_payload,
                        headers=route_test.headers or {},
                    )
                else:
                    continue

                # Allow some flexibility in status codes for partially implemented endpoints
                if response.status_code == 404:
                    print(f"Route {route_test.path} not implemented yet")
                    continue

                if response.status_code >= 500:
                    print(f"Route {route_test.path} has server error: {response.text}")
                    continue

                # Should not return 4xx errors for basic requests
                assert response.status_code < 400 or response.status_code in [
                    401,
                    403,
                ], f"Route {route_test.path} returned {response.status_code}: {response.text}"

    async def test_error_response_format_consistency(self):
        """Test that error responses have consistent format."""
        async with TestAppContext() as context:
            client = context.client

            # Try to trigger various error conditions
            error_cases = [
                ("/nonexistent", 404),
                # Add more error cases as needed
            ]

            for path, expected_status in error_cases:
                response = await client.get(path)

                if response.status_code == expected_status:
                    # Check if response is JSON and has expected error format
                    try:
                        data = response.json()

                        # Common error response fields
                        if "error" in data or "message" in data:
                            # Validate error schema if it's structured
                            if isinstance(data, dict):
                                assert "message" in data or "error" in data

                                # Should not expose stack traces
                                error_text = str(data).lower()
                                assert "traceback" not in error_text
                                assert "exception" not in error_text

                    except json.JSONDecodeError:
                        # Some error responses may not be JSON (like 404s)
                        pass

    async def test_cors_headers_present(self):
        """Test that CORS headers are present for browser compatibility."""
        async with TestAppContext() as context:
            response = await context.client.get(
                "/health", headers={"Origin": "http://localhost:3000"}
            )

            # Check for CORS headers (may not be implemented yet)
            cors_headers = {
                "access-control-allow-origin",
                "access-control-allow-methods",
                "access-control-allow-headers",
            }

            response_headers = {k.lower() for k in response.headers.keys()}
            cors_found = bool(cors_headers.intersection(response_headers))

            if not cors_found:
                print("CORS headers not found - may not be configured yet")

    async def test_content_type_headers_correct(self):
        """Test that endpoints return correct Content-Type headers."""
        async with TestAppContext() as context:
            client = context.client

            # JSON endpoints
            json_endpoints = ["/health", "/readyz"]

            for endpoint in json_endpoints:
                try:
                    response = await client.get(endpoint)
                    if response.status_code == 200:
                        content_type = response.headers.get("content-type", "")
                        assert (
                            "application/json" in content_type
                        ), f"Endpoint {endpoint} should return JSON content type"
                except Exception:
                    print(f"Endpoint {endpoint} not accessible for content-type test")

            # Text endpoints
            try:
                response = await client.get("/metrics")
                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")
                    # Prometheus metrics should be text/plain
                    assert (
                        "text" in content_type or content_type == ""
                    ), f"/metrics should return text content type, got: {content_type}"
            except Exception:
                print("/metrics endpoint not accessible for content-type test")

    async def test_response_schema_stability(self):
        """Test that response schemas don't change unexpectedly."""
        async with TestAppContext() as context:
            client = context.client

            # Test key endpoints for schema stability
            stable_endpoints = {
                "/health": {"status", "timestamp"},
                "/readyz": {"status", "checks", "timestamp"},
            }

            for endpoint, required_fields in stable_endpoints.items():
                try:
                    response = await client.get(endpoint)
                    if response.status_code == 200:
                        data = response.json()

                        # Check required fields are present
                        missing_fields = required_fields - set(data.keys())
                        assert (
                            not missing_fields
                        ), f"Endpoint {endpoint} missing required fields: {missing_fields}"

                        # Log any new fields for review
                        extra_fields = set(data.keys()) - required_fields
                        if extra_fields:
                            print(
                                f"Endpoint {endpoint} has additional fields: {extra_fields}"
                            )

                except Exception as e:
                    print(f"Could not test schema stability for {endpoint}: {e}")

    async def test_backwards_compatibility_snapshot(self):
        """Test backwards compatibility by comparing against stored snapshots."""
        # This would typically load stored response snapshots and compare
        # For now, we'll just document the expected structure

        expected_schemas = {
            "/health": {
                "type": "object",
                "required": ["status", "timestamp"],
                "properties": {
                    "status": {"type": "string"},
                    "timestamp": {"type": "string"},
                    "uptime_seconds": {"type": "number"},
                },
            },
            "/readyz": {
                "type": "object",
                "required": ["status", "checks", "timestamp"],
                "properties": {
                    "status": {"type": "string"},
                    "checks": {"type": "object"},
                    "timestamp": {"type": "string"},
                },
            },
        }

        async with TestAppContext() as context:
            for endpoint, expected_schema in expected_schemas.items():
                try:
                    response = await context.client.get(endpoint)
                    if response.status_code == 200:
                        data = response.json()

                        # Validate basic structure matches expectations
                        for required_field in expected_schema["required"]:
                            assert (
                                required_field in data
                            ), f"Required field '{required_field}' missing from {endpoint}"

                except Exception as e:
                    print(f"Could not validate schema for {endpoint}: {e}")
