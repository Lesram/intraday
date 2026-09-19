"""H5: Settings API governance bypass prevention.

Tests that PUT /settings/organism, /settings/trading, /settings/ml
all check governance state before allowing changes.
"""

from backend.api.routes.settings import _check_governance
from fastapi import HTTPException
from types import SimpleNamespace
import pytest


def _make_request(frozen=False, halted=False):
    gov = SimpleNamespace(is_frozen=frozen, is_trading_halted=halted)
    app = SimpleNamespace(state=SimpleNamespace(organism_governance=gov))
    return SimpleNamespace(app=app)


def test_h5_allows_when_not_frozen():
    req = _make_request(frozen=False, halted=False)
    _check_governance(req)  # should not raise


def test_h5_blocks_when_frozen():
    req = _make_request(frozen=True, halted=False)
    with pytest.raises(HTTPException) as exc_info:
        _check_governance(req)
    assert exc_info.value.status_code == 403
    assert "frozen" in exc_info.value.detail.lower()


def test_h5_blocks_when_halted():
    req = _make_request(frozen=False, halted=True)
    with pytest.raises(HTTPException) as exc_info:
        _check_governance(req)
    assert exc_info.value.status_code == 403
    assert "halted" in exc_info.value.detail.lower()


def test_h5_no_governance_allows():
    """If governance is not configured, settings changes pass through."""
    app = SimpleNamespace(state=SimpleNamespace(organism_governance=None))
    req = SimpleNamespace(app=app)
    _check_governance(req)  # should not raise
