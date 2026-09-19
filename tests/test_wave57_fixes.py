"""V10 / Wave-57 (2026-05-03): tests for UU2-B lint rule + ratchet.

Locks regressions for:
- UU2-B (deliverable): pyproject.toml ruff config enables
  S110/S112/BLE001/G004/TRY401/LOG007 with grandfather ratchet via
  per-file-ignores.

Run with: ./venv/bin/python -m pytest tests/test_wave57_fixes.py -v
"""
from __future__ import annotations

import os


def test_uu2_b_ruff_select_includes_error_handling_rules():
    """pyproject.toml ruff [tool.ruff] select must include the V10
    error-handling rules."""
    src = open("pyproject.toml").read()
    assert "UU2-B" in src, "UU2-B marker missing"
    for rule in ("S110", "S112", "BLE001", "G004", "TRY401", "LOG007"):
        assert f'"{rule}"' in src, (
            f"UU2-B regression: ruff rule {rule} no longer enabled."
        )


def test_uu2_b_grandfather_ratchet_present():
    """Per-file-ignores include the V10 backlog files."""
    src = open("pyproject.toml").read()
    assert "live_engine.py" in src, (
        "UU2-B regression: live_engine.py not in grandfather ratchet."
    )
    assert "brain_persistence.py" in src, (
        "UU2-B regression: brain_persistence.py not in grandfather ratchet."
    )


def test_uu2_b_error_handling_doc_present():
    """docs/engineering/error-handling.md must exist and document the rules."""
    path = "docs/engineering/error-handling.md"
    assert os.path.isfile(path), (
        "UU2-B regression: error-handling.md doc missing."
    )
    src = open(path).read()
    for rule in ("S110", "S112", "BLE001", "G004"):
        assert rule in src, (
            f"UU2-B regression: error-handling.md missing {rule} entry."
        )
