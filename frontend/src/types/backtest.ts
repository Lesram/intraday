/**
 * Backtest Type Definitions
 * 
 * Type definitions for backtesting functionality including requests,
 * results, performance metrics, and trade logs.
 * 
 * @module types/backtest
 */

/**
 * Backtest request parameters
 */
export interface BacktestRequest {
  strategy_id: string;
  start_date: string;  // ISO date format: YYYY-MM-DD
  end_date: string;    // ISO date format: YYYY-MM-DD
  initial_capital: number;
  parameters?: Record<string, unknown>;  // Optional parameter overrides
}

/**
 * Single point on the equity curve
 */
export interface EquityPoint {
  date: string;  // ISO date
  value: number;
  cash: number;
  positions_value: number;
}

/**
 * Individual trade record
 */
export interface Trade {
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  entry_date: string;
  entry_price: number;
  exit_date?: string | null;
  exit_price?: number | null;
  pnl?: number | null;
  pnl_percent?: number | null;
  duration_days?: number | null;
  commission: number | null;
}

/**
 * Comprehensive performance metrics
 */
export interface PerformanceMetrics {
  // Returns
  total_return: number;
  annualized_return: number;
  
  // Risk-adjusted metrics
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  
  // Risk metrics
  max_drawdown: number;
  max_drawdown_duration_days: number;
  volatility: number;
  
  // Trade statistics
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  
  // P&L statistics
  profit_factor: number;
  avg_trade_pnl: number;
  avg_win: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
  
  // Streaks
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  
  // Benchmark comparison (optional)
  alpha?: number;
  beta?: number;
  
  // Additional
  total_commission: number;
  avg_trade_duration_days: number;
}

/**
 * Monthly return data
 */
export interface MonthlyReturn {
  month: string;  // Format: YYYY-MM
  return_pct: number;
  trades: number;
  winning_trades: number;
  losing_trades: number;
}

/**
 * Backtest execution status
 */
export type BacktestStatus = 'pending' | 'running' | 'completed' | 'failed';

/**
 * Complete backtest result
 */
export interface BacktestResult {
  id: string;
  strategy_id: string;
  strategy_name: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  final_equity: number;
  
  // Metrics
  metrics: PerformanceMetrics;
  
  // Detailed results
  equity_curve: EquityPoint[];
  trade_log: Trade[];
  monthly_returns: MonthlyReturn[];
  
  // Execution info
  status: BacktestStatus;
  error_message?: string;
  progress: number;  // 0-100
  
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

/**
 * Lightweight backtest summary for history lists
 */
export interface BacktestSummary {
  id: string;
  strategy_id: string;
  strategy_name: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  
  // Summary metrics (nullable if not completed)
  final_equity?: number;
  total_return?: number;
  sharpe_ratio?: number;
  max_drawdown?: number;
  total_trades?: number;
  
  // Execution info
  status: BacktestStatus;
  error_message?: string;
  created_at: string;
  completed_at?: string;
}

/**
 * Backtest form values
 */
export interface BacktestFormValues {
  strategyId: string;
  startDate: string;
  endDate: string;
  initialCapital: number;
  useCustomParameters: boolean;
  customParameters?: Record<string, unknown>;
}
