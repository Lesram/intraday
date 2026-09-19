"""Tests for Residual Master Remediation -- R2 platform hardening + R3 production fixes.

R2-1: COMP-409 -- Redis bind to 127.0.0.1
R2-2: COMP-407/408 -- No hardcoded credential defaults in scripts
R2-3: COMP-324 -- JWT secret requires env var in non-dev
R2-4: COMP-226 -- OTLP insecure flag configurable
R2-5: XSYS-009 -- SHA-256 for file checksums and ETags
R3-1: COMP-002 -- Production broker no run_until_complete
"""

import hashlib
import os
import re

import pytest


class TestCOMP409RedisBinding:
    """COMP-409: Redis must bind to 127.0.0.1 in paper compose."""

    def test_redis_binds_to_localhost(self):
        """COMP-409: Redis port must be 127.0.0.1-only on the host.

        V12 W89 (post-cleanup): V7 EE-3 / Wave-23e set the
        container-internal ``--bind 0.0.0.0`` because cross-container
        traffic on the docker-compose network requires it.  But the
        HOST port mapping was ``"6379:6379"`` (all-interfaces), which
        is the actual security concern COMP-409 raised.  W89 set the
        host mapping to ``"127.0.0.1:6379:6379"`` and updated this
        test to look for the host-side bind, not the container bind.
        """
        compose_path = os.path.join(
            os.path.dirname(__file__), "..", "docker-compose.paper.yml"
        )
        with open(compose_path, "r") as f:
            content = f.read()
        assert (
            '"127.0.0.1:6379:6379"' in content
            or "127.0.0.1:6379:6379" in content
        ), (
            "Redis host port must publish to 127.0.0.1 only — "
            "either ``- 127.0.0.1:6379:6379`` in ports, or remove "
            "the host port publication entirely."
        )


class TestCOMP407408NoCreds:
    """COMP-407/408: Scripts must not have hardcoded credential defaults."""

    def test_write_runtime_snapshot_no_hardcoded_creds(self):
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "runtime", "write_runtime_snapshot.py"
        )
        with open(script_path, "r") as f:
            content = f.read()
        assert "admin@example.com" not in content, "Hardcoded email in write_runtime_snapshot.py"
        assert "admin123" not in content, "Hardcoded password in write_runtime_snapshot.py"

    def test_generate_paper_validation_no_hardcoded_creds(self):
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "runtime", "generate_paper_validation_bundle.py"
        )
        with open(script_path, "r") as f:
            content = f.read()
        assert "admin@example.com" not in content, "Hardcoded email in generate_paper_validation_bundle.py"
        assert "admin123" not in content, "Hardcoded password in generate_paper_validation_bundle.py"


class TestCOMP324JWTSecret:
    """COMP-324: JWT must not use hardcoded fallback in non-dev."""

    def test_auth_no_hardcoded_secret_used_directly(self):
        auth_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "api", "auth.py"
        )
        with open(auth_path, "r") as f:
            content = f.read()
        # The literal production-dangerous string should not appear
        assert "test_secret_NOT_FOR_PRODUCTION" not in content, (
            "Dangerous fallback secret still present in auth.py"
        )


class TestCOMP226OTLPConfigurable:
    """COMP-226: OTLP insecure flag must be env-configurable."""

    def test_observability_insecure_not_hardcoded(self):
        obs_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "infra", "observability.py"
        )
        with open(obs_path, "r") as f:
            lines = f.readlines()
        # Find lines with insecure= and verify they reference env/config, not literal True
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "insecure=" in stripped and not stripped.startswith("#"):
                assert "True" not in stripped or "getenv" in stripped or "config" in stripped.lower(), (
                    f"Line {i}: insecure=True is hardcoded without env override: {stripped}"
                )


class TestXSYS009SHA256:
    """XSYS-009: File checksums and ETags must use SHA-256, not MD5."""

    def test_model_management_uses_sha256(self):
        """V12 W89 (post-cleanup): backend/ml/model_management.py was
        removed in a prior wave but this test still references it.
        Skip when the file is absent (the XSYS-009 concern lives only
        if the file exists)."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "ml", "model_management.py"
        )
        if not os.path.isfile(path):
            pytest.skip(
                "backend/ml/model_management.py removed; XSYS-009 not "
                "applicable in current architecture"
            )
        with open(path, "r") as f:
            content = f.read()
        # Find _calculate_checksum function -- should use sha256 not md5
        if "_calculate_checksum" in content:
            checksum_section = content[content.index("_calculate_checksum"):]
            checksum_fn = checksum_section[:checksum_section.index("\n\n") if "\n\n" in checksum_section else 200]
            assert "md5" not in checksum_fn.lower(), "model_management._calculate_checksum still uses MD5"
            assert "sha256" in checksum_fn.lower(), "model_management._calculate_checksum should use SHA-256"

    def test_positions_etag_uses_sha256(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "api", "routes", "positions.py"
        )
        with open(path, "r") as f:
            content = f.read()
        if "etag" in content.lower() or "compute_etag" in content.lower():
            assert "md5" not in content.lower() or "sha256" in content.lower(), (
                "positions.py ETag computation still uses MD5"
            )


class TestCOMP002ProductionBroker:
    """COMP-002: Production broker must not use run_until_complete in async."""

    def test_no_run_until_complete(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "brokers", "alpaca_production.py"
        )
        if not os.path.exists(path):
            pytest.skip("Production broker file not found")
        with open(path, "r") as f:
            content = f.read()
        assert "run_until_complete" not in content, (
            "Production broker still uses run_until_complete() -- crashes in async context"
        )
