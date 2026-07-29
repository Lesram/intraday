"""V11 prep / Wave-64 (2026-05-03): VV-1 backend serialization aliases.

Locks the regression for V10 VV-1 (deferred): OrderValidationResponse
emitted snake_case keys but frontend read camelCase, leading to
silent undefined/N/A in the pre-trade UI.

Wave-64 ships per-field `serialization_alias` on the camelCase keys
the frontend expects + `populate_by_name=True` so both forms work.

Run with: ./venv/bin/python -m pytest tests/test_wave64_fixes.py -v
"""
from __future__ import annotations


def test_vv_1_order_validation_response_serializes_camel():
    from backend.api.routes.orders import OrderValidationResponse
    resp = OrderValidationResponse(
        valid=True,
        estimated_cost=1234.56,
        estimated_price=42.0,
        estimated_buying_power_after=10000.0,
    )
    # Default model_dump uses field names (snake_case).
    snake = resp.model_dump()
    assert "estimated_cost" in snake
    # by_alias=True emits camelCase.
    camel = resp.model_dump(by_alias=True)
    assert "estimatedCost" in camel
    assert camel["estimatedCost"] == 1234.56
    assert "estimatedBuyingPowerAfter" in camel


def test_vv_1_marker_present():
    import inspect
    from backend.api.routes.orders import OrderValidationResponse
    src = inspect.getsource(OrderValidationResponse)
    assert "VV-1 closure" in src or "Wave-64" in src
    assert "serialization_alias" in src
