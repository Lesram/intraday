"""
Pydantic models for risk management.
Comprehensive type-safe models for risk metrics, violations, limits, and emergency stops.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RiskStatus(str, Enum):
    """Risk metric status levels"""

    NORMAL = "normal"
    WARNING = "warning"
    CRITICAL = "critical"
    BREACHED = "breached"


class ViolationType(str, Enum):
    """Type of risk violation"""

    WARNING = "warning"
    BREACH = "breach"


class Severity(str, Enum):
    """Violation severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EmergencyStopStatus(str, Enum):
    """Emergency stop status"""

    ACTIVE = "active"
    RESOLVED = "resolved"


# ===========================
# REQUEST MODELS
# ===========================


class UpdateRiskLimitRequest(BaseModel):
    """Request to update a risk limit"""

    limit_value: Decimal = Field(..., gt=0, description="New limit value")
    warning_threshold: Decimal | None = Field(
        80.0, ge=0, le=100, description="Warning threshold %"
    )
    critical_threshold: Decimal | None = Field(
        95.0, ge=0, le=100, description="Critical threshold %"
    )
    enabled: bool | None = Field(True, description="Whether limit is enabled")

    @field_validator("critical_threshold")
    @classmethod
    def validate_thresholds(cls, v, info):
        if "warning_threshold" in info.data and v <= info.data["warning_threshold"]:
            raise ValueError("Critical threshold must be greater than warning threshold")
        return v


class TriggerEmergencyStopRequest(BaseModel):
    """Request to trigger emergency stop"""

    reason: str = Field(
        ..., min_length=10, max_length=500, description="Reason for emergency stop"
    )


# ===========================
# RESPONSE MODELS
# ===========================


class RiskMetric(BaseModel):
    """Real-time risk metric"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int  # Changed from UUID to int
    metric_name: str
    current_value: Decimal
    limit_value: Decimal
    percent_used: Decimal
    status: RiskStatus
    last_updated: datetime
    created_at: datetime


class RiskViolation(BaseModel):
    """Risk limit violation record"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int  # Changed from UUID to int
    metric_name: str
    violation_type: ViolationType
    current_value: Decimal
    limit_value: Decimal
    severity: Severity
    message: str
    resolved: bool
    resolved_at: datetime | None
    created_at: datetime


class RiskLimit(BaseModel):
    """User risk limit configuration"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int  # Changed from UUID to int
    limit_name: str
    limit_value: Decimal
    warning_threshold: Decimal
    critical_threshold: Decimal
    enabled: bool
    created_at: datetime
    updated_at: datetime
    updated_by: int | None  # Changed from UUID to int


class EmergencyStop(BaseModel):
    """Emergency stop record"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: int  # Changed from UUID to int
    triggered_by: int  # Changed from UUID to int
    reason: str
    strategies_stopped: int
    orders_cancelled: int
    status: EmergencyStopStatus
    triggered_at: datetime
    resolved_at: datetime | None
    resolved_by: int | None  # Changed from UUID to int


class RiskDashboardSummary(BaseModel):
    """Summary statistics for risk dashboard"""
    total_metrics: int
    breached_metrics: int
    warning_metrics: int
    critical_metrics: int
    recent_violations_count: int
    is_emergency_active: bool


class RiskDashboardData(BaseModel):
    """Complete risk dashboard data"""

    model_config = ConfigDict()

    metrics: list[RiskMetric]
    recent_violations: list[RiskViolation]
    active_limits: list[RiskLimit]
    emergency_status: EmergencyStop | None
    summary: RiskDashboardSummary
    last_updated: datetime


# ===========================
# WEBSOCKET EVENT MODELS
# ===========================


class RiskMetricUpdate(BaseModel):
    """WebSocket event for risk metric update"""

    type: str = "risk_metric_update"
    data: RiskMetric


class RiskViolationAlert(BaseModel):
    """WebSocket event for new risk violation"""

    type: str = "risk_violation_alert"
    data: RiskViolation


class EmergencyStopEvent(BaseModel):
    """WebSocket event for emergency stop"""

    type: str = "emergency_stop_triggered"
    data: EmergencyStop
