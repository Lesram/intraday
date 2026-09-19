"""V11 prep / Wave-65 (2026-05-03): VV-2 Decimal-as-number serialization.

Locks the regression for V10 VV-2 (deferred): risk endpoints
serialized Decimal as JSON string, breaking frontend type contract
(`RiskMetric.current_value: number` was a lie; FE masked with
parseFloat(x.toString())).

Wave-65 ships a `@field_serializer` that emits floats on the wire
while preserving Decimal precision server-side.

Run with: ./venv/bin/python -m pytest tests/test_wave65_fixes.py -v
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4


def test_vv_2_risk_metric_serializes_decimal_as_float():
    from backend.models.risk import RiskMetric, RiskStatus
    m = RiskMetric(
        id=uuid4(),
        user_id=1,
        metric_name="daily_loss_pct",
        current_value=Decimal("0.0234"),
        limit_value=Decimal("0.05"),
        percent_used=Decimal("46.8"),
        status=RiskStatus.NORMAL,
        last_updated=datetime.now(),
        created_at=datetime.now(),
    )
    out = m.model_dump()
    # JSON-friendly types: float, not Decimal/str
    assert isinstance(out["current_value"], float)
    assert isinstance(out["limit_value"], float)
    assert isinstance(out["percent_used"], float)
    # Numerically equal to the input Decimal
    assert abs(out["current_value"] - 0.0234) < 1e-9


def test_vv_2_risk_violation_serializes_decimal_as_float():
    from backend.models.risk import RiskViolation, ViolationType, Severity
    v = RiskViolation(
        id=uuid4(),
        user_id=1,
        metric_name="daily_loss_pct",
        violation_type=ViolationType.BREACH,
        current_value=Decimal("0.06"),
        limit_value=Decimal("0.05"),
        severity=Severity.HIGH,
        message="exceeded",
        resolved=False,
        resolved_at=None,
        created_at=datetime.now(),
    )
    out = v.model_dump()
    assert isinstance(out["current_value"], float)
    assert isinstance(out["limit_value"], float)
