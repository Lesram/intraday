/**
 * Trading-related TypeScript interfaces
 * 
 * These types match the backend validation endpoint exactly:
 * - Backend: backend/api/routes/orders.py
 * - Endpoint: POST /api/v1/orders/validate
 * 
 * Field naming: Backend uses snake_case, FastAPI/Pydantic auto-converts to camelCase in JSON
 * All types verified against PHASE_2_1_COMPREHENSIVE_ANALYSIS.md Section 2.1
 */

/**
 * Individual validation check result
 * Represents one of the 8 validation checks performed on an order
 */
export interface ValidationCheck {
  /** Unique name identifying the check (e.g., "Symbol Validation", "Buying Power") */
  name: string;
  
  /** Whether this check passed (true) or failed (false) */
  passed: boolean;
  
  /** Current value being checked (e.g., current buying power, current position size) */
  currentValue?: number;
  
  /** Limit or threshold value (e.g., max position size, concentration limit) */
  limitValue?: number;
  
  /** Human-readable message explaining the check result */
  message: string;
  
  /** Severity level of the result */
  severity: 'info' | 'warning' | 'error';
}

/**
 * Complete validation response from backend
 * Contains all validation checks, warnings, errors, and cost estimates
 */
export interface OrderValidationResponse {
  /** Overall validation result - true if order can proceed, false if blocked */
  valid: boolean;
  
  /** Array of all validation check results (8 checks total) */
  checks: ValidationCheck[];
  
  /** Warning messages (non-blocking, user can proceed with caution) */
  warnings: string[];
  
  /** Error messages (blocking, order cannot proceed) */
  errors: string[];
  
  /** Estimated cost of the order (quantity × price) */
  estimatedCost?: number;
  
  /** Estimated buying power remaining after order execution */
  estimatedBuyingPowerAfter?: number;
}

/**
 * Request payload for order validation
 * Sent to POST /api/v1/orders/validate
 */
export interface OrderValidationRequest {
  /** Stock symbol (1-10 characters, alphabetic) */
  symbol: string;
  
  /** Order side */
  side: 'buy' | 'sell';
  
  /** Number of shares (must be > 0) */
  quantity: number;
  
  /** Type of order */
  orderType: 'market' | 'limit' | 'stop' | 'stop_limit';
  
  /** Limit price (required for limit and stop_limit orders) */
  limitPrice?: number;
}

/**
 * Order form data (internal use in components)
 * Extends validation request with additional UI state
 */
export interface OrderFormData extends OrderValidationRequest {
  /** Stop price (for stop and stop_limit orders) */
  stopPrice?: number;
  
  /** Time in force */
  timeInForce?: 'day' | 'gtc' | 'ioc' | 'fok';
  
  /** Extended hours trading */
  extendedHours?: boolean;
}

/**
 * Validation check names (for filtering/referencing specific checks)
 */
export const ValidationCheckName = {
  SYMBOL: 'Symbol Validation',
  QUANTITY: 'Quantity Validation',
  BUYING_POWER: 'Buying Power',
  POSITION_SIZE: 'Position Size Limit',
  CONCENTRATION: 'Portfolio Concentration',
  DAILY_LOSS: 'Daily Loss Limit',
  RISK_ASSESSMENT: 'Risk Assessment',
  PORTFOLIO_STATE: 'Portfolio State'
} as const;

export type ValidationCheckNameType = typeof ValidationCheckName[keyof typeof ValidationCheckName];

/**
 * Type guard to check if validation response is valid
 */
export const isValidationValid = (response: OrderValidationResponse): boolean => {
  return response.valid && response.errors.length === 0;
};

/**
 * Type guard to check if validation has warnings
 */
export const hasValidationWarnings = (response: OrderValidationResponse): boolean => {
  return response.warnings.length > 0 || 
         response.checks.some(check => check.severity === 'warning' && !check.passed);
};

/**
 * Get color for severity level (for UI rendering)
 */
export const getSeverityColor = (severity: ValidationCheck['severity']): string => {
  switch (severity) {
    case 'error':
      return '#ff4d4f'; // red
    case 'warning':
      return '#faad14'; // orange/yellow
    case 'info':
      return '#52c41a'; // green
    default:
      return '#d9d9d9'; // gray
  }
};

/**
 * Get icon for check result (for UI rendering)
 */
export const getCheckIcon = (check: ValidationCheck): string => {
  if (check.severity === 'error' && !check.passed) {
    return '❌';
  }
  if (check.severity === 'warning') {
    return '⚠️';
  }
  if (check.passed) {
    return '✅';
  }
  return '❌';
};

/**
 * Format currency for display
 */
export const formatCurrency = (amount: number | undefined): string => {
  if (amount === undefined || amount === null) {
    return 'N/A';
  }
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
};

/**
 * Format percentage for display
 */
export const formatPercentage = (value: number | undefined): string => {
  if (value === undefined || value === null) {
    return 'N/A';
  }
  return `${value.toFixed(2)}%`;
};
