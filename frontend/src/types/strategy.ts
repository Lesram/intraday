/**
 * Strategy Type Definitions
 * 
 * Consolidated type definitions for trading strategies.
 * All fields use camelCase naming convention to match backend API responses.
 * 
 * @module types/strategy
 */

/**
 * Strategy execution status
 * - active: Strategy is running and executing trades
 * - paused: Strategy is temporarily suspended
 * - stopped: Strategy is inactive (backend returns this for 'inactive' status)
 * - error: Strategy encountered an error and stopped
 */
export type StrategyStatus = 'active' | 'paused' | 'stopped' | 'error';

/**
 * Strategy type classification
 * 
 * Implementation Types (Algorithmic):
 * - momentum: Trend continuation algorithm
 * - mean_reversion: Price reversion algorithm
 * - ensemble / ensemble_model: Multiple ML models voting
 * - stat_arb / statistical_arbitrage: Statistical arbitrage pairs trading
 * 
 * Classification Types (Philosophy):
 * - technical / technical_analysis: Chart patterns & indicators
 * - fundamental / fundamental_analysis: Company financials & valuations
 * - quantitative: Mathematical models & ML
 * - hybrid / hybrid_strategy: Multi-approach combination
 * - optuna_meta: Optuna research meta-strategy (platform parity mode)
 */
export type StrategyType = 
  // Implementation types (short and template names)
  | 'momentum' 
  | 'mean_reversion' 
  | 'ensemble' 
  | 'ensemble_model'
  | 'stat_arb'
  | 'statistical_arbitrage'
  // Classification types (short and template names)
  | 'technical'
  | 'technical_analysis'
  | 'fundamental'
  | 'fundamental_analysis'
  | 'quantitative'
  | 'hybrid'
  | 'hybrid_strategy'
  | 'optuna_meta';

/**
 * Performance metrics for a trading strategy
 */
export interface PerformanceMetrics {
  /** Total number of trades executed */
  totalTrades: number;
  
  /** Win rate as decimal (0.0 to 1.0, e.g., 0.65 = 65%) */
  winRate: number;
  
  /** Total profit/loss in dollars */
  totalPnL: number;
  
  /** Sharpe ratio (risk-adjusted return metric) */
  sharpeRatio: number;
  
  /** Maximum drawdown as negative value (e.g., -500.0 = $500 loss) */
  maxDrawdown: number;
}

/**
 * Complete strategy definition
 * Represents a trading strategy with its configuration and performance metrics
 */
export interface Strategy {
  /** Unique identifier (UUID) */
  strategyId: string;
  
  /** Human-readable strategy name (must be unique) */
  name: string;
  
  /** Detailed description of strategy logic and approach */
  description: string;
  
  /** Current execution status */
  status: StrategyStatus;
  
  /** Strategy implementation type */
  strategyType: StrategyType;
  
  /** List of symbols this strategy trades (e.g., ["AAPL", "GOOGL"]) */
  symbols: string[];
  
  /** Strategy-specific configuration parameters (flexible JSON object) */
  parameters: Record<string, unknown>;
  
  /** Performance metrics (updated after trades execute) */
  performance: PerformanceMetrics;
  
  /** ISO 8601 timestamp when strategy was created */
  createdAt: string;
  
  /** ISO 8601 timestamp when strategy was last modified */
  updatedAt: string;
  
  /** ISO 8601 timestamp when strategy last executed a trade (optional) */
  lastExecutedAt?: string;
}

/**
 * Request payload for creating a new strategy
 * Omits auto-generated fields (strategyId, timestamps, performance)
 */
export interface CreateStrategyRequest {
  /** Strategy name (must be unique) */
  name: string;
  
  /** Strategy description */
  description: string;
  
  /** Strategy type */
  strategyType: StrategyType;
  
  /** Symbols to trade */
  symbols: string[];
  
  /** Configuration parameters */
  parameters: Record<string, unknown>;
}

/**
 * Request payload for updating an existing strategy
 * All fields are optional (partial update)
 * Note: Status updates should use start/stop/pause endpoints, not this
 */
export interface UpdateStrategyRequest {
  /** Updated name (must be unique if provided) */
  name?: string;
  
  /** Updated description */
  description?: string;
  
  /** Updated strategy type */
  strategyType?: StrategyType;
  
  /** Updated symbols list */
  symbols?: string[];
  
  /** Updated configuration parameters */
  parameters?: Record<string, unknown>;
}

/**
 * Request payload for updating strategy performance metrics
 * Used by backtesting or live trading engines to update performance
 */
export interface UpdatePerformanceRequest {
  /** Total trades executed */
  totalTrades: number;
  
  /** Win rate (0.0 to 1.0) */
  winRate: number;
  
  /** Total profit/loss */
  totalPnL: number;
  
  /** Sharpe ratio */
  sharpeRatio: number;
  
  /** Maximum drawdown (negative value) */
  maxDrawdown: number;
}

// ============================================================================
// STRATEGY TEMPLATE TYPES (Phase 3.1 - Strategy Builder)
// ============================================================================

/**
 * Parameter input type for strategy templates
 */
export type ParameterType = 'number' | 'string' | 'boolean' | 'select' | 'multiselect';

/**
 * Definition for a single strategy parameter
 * Describes input configuration, validation rules, and metadata
 */
export interface ParameterDefinition {
  /** Parameter identifier (snake_case, matches backend) */
  name: string;
  
  /** Parameter display label */
  label?: string;
  
  /** Input type */
  type: ParameterType;
  
  /** Default value */
  default: unknown;
  
  /** Minimum value (for number type) */
  min?: number;
  
  /** Maximum value (for number type) */
  max?: number;
  
  /** Available options (for select/multiselect types) */
  options?: Array<{ value: string; label: string }>;
  
  /** Parameter description/help text */
  description: string;
  
  /** Whether parameter is required */
  required: boolean;
}

/**
 * Risk management defaults for a strategy template
 */
export interface RiskDefaults {
  /** Maximum position size in dollars */
  maxPositionSize: number;
  
  /** Daily loss limit in dollars */
  dailyLossLimit: number;
  
  /** Maximum drawdown percentage (0.0-1.0) */
  maxDrawdown: number;
  
  /** Stop loss percentage (0.0-1.0) */
  stopLoss: number;
  
  /** Take profit percentage (0.0-1.0) */
  takeProfit: number;
}

/**
 * Complete strategy template definition
 * Pre-configured template with parameter schemas and risk defaults
 */
export interface StrategyTemplate {
  /** Template identifier (matches StrategyType) */
  type: StrategyType;
  
  /** Template display name */
  name: string;
  
  /** Template description */
  description: string;
  
  /** Template category for organization */
  category: string;
  
  /** Icon identifier (for UI) */
  icon: string;
  
  /** Parameter definitions for this template */
  parameters: ParameterDefinition[];
  
  /** Default risk management settings */
  riskDefaults: RiskDefaults;
}

/**
 * Wizard form data model
 * Accumulates data across all wizard steps
 */
export interface StrategyFormData {
  // Step 1: Basic Info
  name: string;
  description: string;
  strategyType: StrategyType | null;
  symbols: string[];
  
  // Step 2: Parameters (dynamic based on strategyType)
  parameters: Record<string, unknown>;
  
  // Step 3: Risk Limits
  riskLimits: RiskDefaults;
  
  // Step 4: Execution Settings
  executionSettings: {
    tradingHoursStart: string; // HH:mm format
    tradingHoursEnd: string;   // HH:mm format
    executionFrequency: 'realtime' | '1min' | '5min' | '15min' | '1hour';
    maxTradesPerDay: number;
  };
}

/**
 * Wizard step validation result
 */
export interface StepValidation {
  valid: boolean;
  errors: Record<string, string>;
}
