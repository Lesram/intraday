/**
 * Risk Management Feature Exports
 * Central export point for all risk management components
 */

// Main components
export { default as RiskManagement } from './RiskManagement';
export { default as RiskDashboard } from './RiskDashboard';
export { default as KillSwitchButton } from './KillSwitchButton';
export { default as RiskLimitsConfig } from './RiskLimitsConfig';

// Sub-components
export { default as RiskMetricCard } from './RiskMetricCard';
export { default as RiskViolationList } from './RiskViolationList';

// Types (re-export for convenience)
export type {
  RiskDashboardData,
  RiskMetric,
  RiskViolation,
  RiskLimit,
  EmergencyStop,
  RiskStatus,
  ViolationType,
  Severity,
  EmergencyStopStatus,
  UpdateRiskLimitRequest,
  TriggerEmergencyStopRequest,
  RiskDashboardProps,
  KillSwitchButtonProps,
  RiskLimitsConfigProps,
  RiskMetricCardProps,
  RiskViolationListProps,
} from '../../types/risk';