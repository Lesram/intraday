"""Tests for Wave C remediation -- datetime consistency.

XSYS-001: All datetime.utcnow() replaced with datetime.now(UTC).
"""

import ast
import os

import pytest


class TestXSYS001DatetimeConsistency:
    """XSYS-001: No datetime.utcnow() calls should remain in backend."""

    def test_no_utcnow_in_backend(self):
        """Scan all backend .py files for datetime.utcnow() calls."""
        backend_dir = os.path.join(os.path.dirname(__file__), "..", "backend")
        violations = []
        for root, dirs, files in os.walk(backend_dir):
            # Skip __pycache__ and migrations
            dirs[:] = [d for d in dirs if d not in ("__pycache__", "migrations")]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                # Check for datetime.utcnow() but not pd.Timestamp.utcnow()
                lines = content.splitlines()
                file_count = 0
                for line in lines:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if "datetime.utcnow()" in line:
                        file_count += 1
                if file_count > 0:
                    rel = os.path.relpath(fpath, backend_dir)
                    violations.append(f"{rel}: {file_count} occurrence(s)")

        assert not violations, (
            f"datetime.utcnow() still found in {len(violations)} file(s):\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
