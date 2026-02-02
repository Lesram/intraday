/**
 * Core TypeScript type definitions for Trading Platform
 */

// ============================================================================
// User & Authentication
// ============================================================================

export interface User {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  permissions?: string[];
  created_at: string;
  updated_at: string;
}

export type UserRole = 'admin' | 'trader' | 'viewer' | 'risk_manager';

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// ============================================================================
// Trading - Orders
// ============================================================================

export interface Order {
  order_id: string;
  client_order_id?: string;
  symbol: string;
  side: OrderSide;
  quantity: number;
  filled_quantity: number;
  remaining_quantity: number;
  order_type: OrderType;
  price?: number;
  stop_price?: number;
  status: OrderStatus;
  time_in_force: TimeInForce;
  created_at: string;
  updated_at: string;
  filled_at?: string;
  average_fill_price?: number;
  message?: string;
  strategy_id?: string;
}

export type OrderSide = 'buy' | 'sell';
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit';
export type OrderStatus = 'pending' | 'open' | 'partially_filled' | 'filled' | 'cancelled' | 'rejected' | 'expired';
export type TimeInForce = 'day' | 'gtc' | 'ioc' | 'fok';

export interface OrderSubmitRequest {
  symbol: string;
  side: OrderSide;
  quantity: number;
  order_type: OrderType;
  price?: number;
  stop_price?: number;
  time_in_force?: TimeInForce;
  strategy_id?: string;
}

// ============================================================================
// Portfolio & Positions
// ============================================================================

export interface Position {
  symbol: string;
  quantity: number;
  average_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_pl_percent: number;
  realized_pl: number;
  cost_basis: number;
  side: PositionSide;
  opened_at: string;
  updated_at: string;
  strategy_id?: string;
}

export type PositionSide = 'long' | 'short' | 'flat';

export interface Portfolio {
  equity: number;
  cash: number;
  buying_power: number;
  margin_used: number;
  positions_value: number;
  daily_pl: number;
  daily_pl_percent: number;
  total_pl: number;
  total_pl_percent: number;
  leverage: number;
  updated_at: string;
}

// ============================================================================
// Strategies
// ============================================================================

// Import and re-export new strategy types (camelCase)
export type {
  Strategy,
  StrategyStatus,
  StrategyType,
  PerformanceMetrics,
  CreateStrategyRequest,
  UpdateStrategyRequest,
  UpdatePerformanceRequest
} from './strategy';

/**
 * @deprecated Use Strategy from './strategy' instead
 * This interface uses snake_case and is outdated.
 * Will be removed in next major version.
 */
export interface Strategy_DEPRECATED {
  strategy_id: string;
  name: string;
  type: string;
  category: StrategyCategory;
  description?: string;
  status: StrategyStatus_DEPRECATED;
  config: Record<string, unknown>;
  parameters: Record<string, unknown>;
  performance?: StrategyPerformance_DEPRECATED;
  created_at: string;
  updated_at: string;
}

/**
 * @deprecated Use StrategyType from './strategy' instead
 */
export type StrategyCategory = 'momentum' | 'mean_reversion' | 'arbitrage' | 'ml' | 'other';

/**
 * @deprecated Use StrategyStatus from './strategy' instead
 * Note: 'running' is now 'active' in new interface
 */
export type StrategyStatus_DEPRECATED = 'running' | 'stopped' | 'paused' | 'error';

/**
 * @deprecated Use PerformanceMetrics from './strategy' instead
 */
export interface StrategyPerformance_DEPRECATED {
  total_pl: number;
  total_pl_percent: number;
  daily_pl: number;
  win_rate: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  total_trades: number;
}

export interface Signal {
  signal_id: string;
  strategy_id: string;
  strategy_name: string;
  symbol: string;
  direction: SignalDirection;
  strength: number;
  confidence: number;
  entry_price?: number;
  stop_loss?: number;
  take_profit?: number;
  position_size?: number;
  reason: string;
  metadata?: Record<string, unknown>;
  created_at: string;
}

export type SignalDirection = 'long' | 'short' | 'close' | 'neutral';

// ============================================================================
// ML Models
// ============================================================================

export interface MLModel {
  model_id: string;
  name: string;
  type: string;
  status: ModelStatus;
  accuracy?: number;
  version: string;
  features: string[];
  created_at: string;
  updated_at: string;
  last_trained?: string;
}

export type ModelStatus = 'active' | 'training' | 'inactive' | 'error';

export interface Prediction {
  prediction: number;
  confidence: number;
  timestamp: string;
  model_id: string;
  symbol?: string;
}

// ============================================================================
// Risk Management
// ============================================================================

export interface RiskMetrics {
  daily_pl: number;
  max_drawdown: number;
  var: number;
  leverage: number;
  exposure: number;
  position_concentration: number;
  updated_at: string;
}

export interface RiskLimits {
  daily_loss_limit: number;
  position_limit: number;
  leverage_limit: number;
  max_position_size: number;
  max_sector_exposure: number;
}

export interface Alert {
  alert_id: string;
  severity: AlertSeverity;
  category: AlertCategory;
  title: string;
  message: string;
  action_required?: boolean;
  action_label?: string;
  action_link?: string;
  related_entity?: {
    type: 'order' | 'position' | 'strategy';
    id: string;
  };
  created_at: string;
}

export type AlertSeverity = 'info' | 'warning' | 'error' | 'critical';
export type AlertCategory = 'risk' | 'system' | 'trading' | 'strategy' | 'compliance';

// ============================================================================
// Market Data
// ============================================================================

export interface Quote {
  symbol: string;
  price: number;
  bid: number;
  ask: number;
  bid_size: number;
  ask_size: number;
  volume: number;
  change: number;
  change_percent: number;
  high: number;
  low: number;
  open: number;
  previous_close: number;
  trade_time: string;
}

export interface Bar {
  time: number | string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

// ============================================================================
// WebSocket Messages
// ============================================================================

export interface WebSocketMessage {
  type: string;
  topic?: string;
  data: unknown;
  timestamp: number;
  sequence?: number;
}

export interface OrderUpdateMessage extends WebSocketMessage {
  type: 'order_update';
  topic: 'orders';
  data: Order;
}

export interface PositionUpdateMessage extends WebSocketMessage {
  type: 'position_update';
  topic: 'positions';
  data: Position;
}

export interface PortfolioUpdateMessage extends WebSocketMessage {
  type: 'portfolio_update';
  topic: 'portfolio';
  data: Portfolio;
}

export interface PriceUpdateMessage extends WebSocketMessage {
  type: 'price_update';
  topic: 'market_data';
  data: Quote;
}

// ============================================================================
// API Responses
// ============================================================================

export interface ApiResponse<T> {
  data?: T;
  error?: ApiError;
  message?: string;
}

export interface ApiError {
  code: string;
  message: string;
  details?: unknown;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
  has_more: boolean;
}
