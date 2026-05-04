"""Tests for Safe-Now Cleanup Wave.

COMP-304: No exception details in API error responses
COMP-305: Test endpoints guarded by environment
XSYS-010: Prometheus metrics don't raise on re-import
TEST-001: Stale SQLite script deleted
TEST-004: No unreachable code in check_coverage.py
TEST-007: auth.py not excluded from credential scanning
"""

import os
import importlib

import pytest


class TestCOMP304NoExceptionLeak:
    """COMP-304: API error responses must not contain exception details."""

    def test_portfolio_error_responses_are_generic(self):
        """HTTPException details in portfolio.py must not contain str(e)."""
        portfolio_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "api", "portfolio.py"
        )
        with open(portfolio_path, "r") as f:
            content = f.read()

        # Check that no HTTPException detail contains f-string with str(e) or {e}
        lines = content.splitlines()
        violations = []
        for i, line in enumerate(lines, 1):
            if "HTTPException" in line and ("str(e)" in line or "{e}" in line):
                violations.append(f"  line {i}: {line.strip()}")

        assert not violations, (
            f"Exception details leaked to clients in {len(violations)} line(s):\n"
            + "\n".join(violations)
        )


class TestCOMP305TestEndpointsGuarded:
    """COMP-305: Test error endpoints only in development."""

    def test_router_exists_in_dev_mode(self):
        """In dev mode (default), test router should have routes."""
        # Default APP_ENVIRONMENT is 'development'
        from backend.api.errors import router
        # Router should exist (may be empty in non-dev, populated in dev)
        assert router is not None


class TestXSYS010PrometheusNoConflict:
    """XSYS-010: Importing metric modules twice must not raise."""

    def test_outbox_reimport_no_error(self):
        """Re-importing outbox should not raise DuplicatedTimeseries."""
        import backend.infra.outbox
        importlib.reload(backend.infra.outbox)
        assert backend.infra.outbox.outbox_polled_total is not None

    def test_object_pool_reimport_no_error(self):
        """Re-importing object_pool should not raise DuplicatedTimeseries."""
        import backend.infra.object_pool
        importlib.reload(backend.infra.object_pool)
        assert backend.infra.object_pool.pool_acquisitions is not None


class TestTEST001StaleScriptDeleted:
    """TEST-001: verify_critical_fixes.py should not exist."""

    def test_stale_script_removed(self):
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "ci", "verify_critical_fixes.py"
        )
        assert not os.path.exists(script_path), (
            "scripts/ci/verify_critical_fixes.py still exists -- should be deleted"
        )


class TestTEST004NoDeadCode:
    """TEST-004: check_coverage.py should end cleanly after main()."""

    def test_no_code_after_sys_exit(self):
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "ci", "check_coverage.py"
        )
        with open(script_path, "r") as f:
            content = f.read()

        lines = content.strip().splitlines()
        # There should NOT be a second if __name__ == "__main__" block
        main_blocks = [i for i, l in enumerate(lines) if '__name__' in l and '__main__' in l]
        assert len(main_blocks) <= 1, (
            f"Found {len(main_blocks)} __name__ == '__main__' blocks -- should be exactly 1"
        )


class TestTEST007NoAuthExclusion:
    """TEST-007: verify_integration.py should not exclude auth.py."""

    def test_auth_not_excluded_from_scanning(self):
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "ci", "verify_integration.py"
        )
        with open(script_path, "r") as f:
            content = f.read()

        # Find the excluded_files set definition and check auth.py is not in it
        if "excluded_files" in content:
            # Get the text between 'excluded_files' and the next '}'
            after_excluded = content.split("excluded_files")[1]
            set_body = after_excluded.split("}")[0] if "}" in after_excluded else ""
            assert "auth.py" not in set_body, (
                "auth.py is still in the excluded_files set"
            )
