/**
 * Risk Management TypeScript Types
 * Complete type definitions for risk metrics, violations, limits, and emergency stops.
 */

// ===========================
// ENUM TYPES
// ===========================

export enum RiskStatus {
  NORMAL = 'normal',
  WARNING = 'warning',
  CRITICAL = 'critical',
  BREACHED = 'breached',
}

export enum ViolationType {
  WARNING = 'warning',
  BREACH = 'breach',
}

export enum Severity {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  CRITICAL = 'critical',
}

export enum EmergencyStopStatus {
  ACTIVE = 'active',
  RESOLVED = 'resolved',
}

// ===========================
// CORE DATA TYPES
// ===========================

export interface RiskMetric {
  id: string;
  user_id: string;
  metric_name: string;
  current_value: number;
  limit_value: number;
  percent_used: number;
  status: RiskStatus;
  last_updated: string;
  created_at: string;
}

export interface RiskViolation {
  id: string;
  user_id: string;
  metric_name: string;
  violation_type: ViolationType;
  current_value: number;
  limit_value: number;
  severity: Severity;
  message: string;
  resolved: boolean;
  resolved_at?: string;
  created_at: string;
}

export interface RiskLimit {
  id: string;
  user_id: string;
  limit_name: string;
  limit_value: number;
  warning_threshold: number;
  critical_threshold: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  updated_by?: string;
}

export interface EmergencyStop {
  id: string;
  user_id: string;
  triggered_by: string;
  reason: string;
  strategies_stopped: number;
  orders_cancelled: number;
  status: EmergencyStopStatus;
  triggered_at: string;
  resolved_at?: string;
  resolved_by?: string;
}

// ===========================
// REQUEST TYPES
// ===========================

export interface UpdateRiskLimitRequest {
  limit_name: string;
  limit_value: number;
  warning_threshold?: number;
  critical_threshold?: number;
  enabled?: boolean;
}

export interface TriggerEmergencyStopRequest {
  reason: string;
  stop_all_strategies?: boolean;
  cancel_all_orders?: boolean;
  notify_admin?: boolean;
}

// ===========================
// DASHBOARD DATA TYPES
// ===========================

export interface RiskDashboardData {
  metrics: RiskMetric[];
  recent_violations: RiskViolation[];
  active_limits: RiskLimit[];
  emergency_status: EmergencyStop | null;
  summary: {
    total_metrics: number;
    breached_metrics: number;
    warning_metrics: number;
    critical_metrics: number;
    recent_violations_count: number;
    is_emergency_active: boolean;
  };
}

// ===========================
// WEBSOCKET EVENT TYPES
// ===========================

export interface RiskMetricUpdate {
  type: 'risk_metric_update';
  data: RiskMetric;
}

export interface RiskViolationAlert {
  type: 'risk_violation_alert';
  data: RiskViolation;
}

export interface EmergencyStopEvent {
  type: 'emergency_stop_event';
  data: EmergencyStop;
}

export type RiskWebSocketEvent = RiskMetricUpdate | RiskViolationAlert | EmergencyStopEvent;

// ===========================
// UI COMPONENT PROPS
// ===========================

export interface RiskDashboardProps {
  className?: string;
  showKillSwitch?: boolean;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

export interface KillSwitchButtonProps {
  className?: string;
  size?: 'small' | 'medium' | 'large';
  disabled?: boolean;
  onConfirm?: () => void;
  onCancel?: () => void;
}

export interface RiskLimitsConfigProps {
  className?: string;
  editable?: boolean;
  onSave?: (limits: RiskLimit[]) => void;
}

export interface RiskMetricCardProps {
  metric: RiskMetric;
  className?: string;
  showDetails?: boolean;
}

export interface RiskViolationListProps {
  violations: RiskViolation[];
  className?: string;
  showResolved?: boolean;
  onResolve?: (violationId: string) => void;
}

// ===========================
// API ERROR TYPES
// ===========================

export interface RiskAPIError {
  detail: string;
  error_code?: string;
  timestamp: string;
}

// ===========================
// UTILITY TYPES
// ===========================

export interface RiskStatusConfig {
  status: RiskStatus;
  color: string;
  icon: string;
  description: string;
}

export interface SeverityConfig {
  severity: Severity;
  color: string;
  priority: number;
  description: string;
}

// ===========================
// FORM TYPES
// ===========================

export interface RiskLimitFormData {
  limit_name: string;
  limit_value: number;
  warning_threshold: number;
  critical_threshold: number;
  enabled: boolean;
}

export interface EmergencyStopFormData {
  reason: string;
  stop_all_strategies: boolean;
  cancel_all_orders: boolean;
  notify_admin: boolean;
}

// ===========================
// CONSTANTS
// ===========================

export const RISK_STATUS_CONFIGS: Record<RiskStatus, RiskStatusConfig> = {
  [RiskStatus.NORMAL]: {
    status: RiskStatus.NORMAL,
    color: '#52c41a',
    icon: 'CheckCircleOutlined',
    description: 'All metrics within normal limits',
  },
  [RiskStatus.WARNING]: {
    status: RiskStatus.WARNING,
    color: '#faad14',
    icon: 'WarningOutlined',
    description: 'Approaching risk limit',
  },
  [RiskStatus.CRITICAL]: {
    status: RiskStatus.CRITICAL,
    color: '#fa8c16',
    icon: 'ExclamationCircleOutlined',
    description: 'Very close to risk limit',
  },
  [RiskStatus.BREACHED]: {
    status: RiskStatus.BREACHED,
    color: '#ff4d4f',
    icon: 'CloseCircleOutlined',
    description: 'Risk limit exceeded',
  },
};

export const SEVERITY_CONFIGS: Record<Severity, SeverityConfig> = {
  [Severity.LOW]: {
    severity: Severity.LOW,
    color: '#52c41a',
    priority: 1,
    description: 'Minor violation, monitor closely',
  },
  [Severity.MEDIUM]: {
    severity: Severity.MEDIUM,
    color: '#faad14',
    priority: 2,
    description: 'Moderate violation, action recommended',
  },
  [Severity.HIGH]: {
    severity: Severity.HIGH,
    color: '#fa8c16',
    priority: 3,
    description: 'Serious violation, immediate attention required',
  },
  [Severity.CRITICAL]: {
    severity: Severity.CRITICAL,
    color: '#ff4d4f',
    priority: 4,
    description: 'Critical violation, emergency response needed',
  },
};

// ===========================
// DEFAULT VALUES
// ===========================

export const DEFAULT_RISK_LIMITS: Partial<RiskLimit> = {
  warning_threshold: 80,
  critical_threshold: 95,
  enabled: true,
};

export const DEFAULT_REFRESH_INTERVAL = 5000; // 5 seconds
export const MAX_RECENT_VIOLATIONS = 10;
export const EMERGENCY_CONFIRM_TIMEOUT = 10000; // 10 seconds