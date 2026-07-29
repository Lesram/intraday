"""V10 / Wave-54 (2026-05-03): tests for frontend/backend contract.

Locks regressions for:
- VV-3 (HIGH): OrderStatus enum widened to cover Alpaca wire
  vocabulary (`pending_new`, `done_for_day`, `expired`, `replaced`,
  `stopped`, `accepted_for_bidding`, `calculated`, `partially_filled`)
  + `canceled`/`cancelled` orthography aliases.

Wave-54 deferred (frontend-side, next deploy):
- VV-1: OrderValidationResponse alias_generator
- VV-2: Risk Decimal serialization
- VV-4: WebSocketTopic.settings + listener
- VV-5: error envelope handler

Run with: ./venv/bin/python -m pytest tests/test_wave54_fixes.py -v
"""
from __future__ import annotations


def test_vv_3_order_status_includes_alpaca_wire_vocab():
    """OrderStatus must include the Alpaca wire-vocab terms V10 VV-3
    flagged as missing."""
    from backend.risk.types import OrderStatus
    expected_values = {
        "new", "pending_new", "pending", "submitted", "submitting",
        "accepted", "accepted_for_bidding",
        "partially_filled", "partial",
        "filled",
        "canceled", "cancelled",
        "rejected", "expired", "done_for_day", "stopped", "replaced",
        "calculated",
    }
    actual_values = {s.value for s in OrderStatus}
    missing = expected_values - actual_values
    assert not missing, (
        f"VV-3 regression: OrderStatus missing values: {missing}"
    )


def test_vv_3_orthography_aliases_both_present():
    """Both CANCELED (US) and CANCELLED (UK) must be present."""
    from backend.risk.types import OrderStatus
    assert hasattr(OrderStatus, "CANCELED")
    assert hasattr(OrderStatus, "CANCELLED")
    # They should be distinct enum members but with related semantics.
    assert OrderStatus.CANCELED.value == "canceled"
    assert OrderStatus.CANCELLED.value == "cancelled"


def test_vv_3_partial_alias_preserved():
    """Legacy PARTIAL alias kept for back-compat alongside PARTIALLY_FILLED."""
    from backend.risk.types import OrderStatus
    assert hasattr(OrderStatus, "PARTIAL")
    assert hasattr(OrderStatus, "PARTIALLY_FILLED")


def test_vv_plan_doc_present():
    """The wave-54 frontend-contract plan doc must exist."""
    import os
    assert os.path.isfile(
        "docs/engineering/V10_WAVE54_FRONTEND_CONTRACT_PLAN.md"
    )
