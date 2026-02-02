/**
 * Trade History & Analytics TypeScript Interfaces
 * Type definitions for trade data, filters, and analytics
 */

export interface Execution {
  executionId: string;
  fillQty: number;
  fillPrice: number;
  timestamp: string;
  venue: string;
}

export interface Trade {
  orderId: string;
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  filledQty: number;
  avgFillPrice: number | null;
  orderType: string;
  status: string;
  submittedAt: string;
  updatedAt: string;
  strategyId?: string | null;
  attributes?: Record<string, unknown>;  // Includes imported flag and other metadata
  positionStatus?: 'open' | 'closed' | 'partially_closed' | 'closed_by_sell' | 'not_applicable' | 'unknown';
  positionNote?: string;  // Explanation of position status
  currentQty?: number | null;  // Current quantity at broker
  currentPrice?: number | null;  // Current market price
  unrealizedPnL?: number | null;  // Unrealized profit/loss
  executions: Execution[];
}

export interface TradeFilters {
  startDate?: string;  // ISO date string
  endDate?: string;    // ISO date string
  symbol?: string;
  strategyId?: string;
  side?: 'buy' | 'sell' | null;
  limit?: number;
  offset?: number;
}

export interface TradeHistoryResponse {
  trades: Trade[];
  total: number;
  limit: number;
  offset: number;
}

export interface BestWorstTrade {
  symbol: string;
  pnl: number;
  date: string;
}

export interface PnLByDay {
  date: string;
  pnl: number;
  trades: number;
}

export interface MonthlyReturn {
  month: string;
  pnl: number;
  trades: number;
  wins: number;
  losses: number;
  winRate: number;
}

export interface RMultipleDistribution {
  avgRMultiple: number;
  medianRMultiple: number;
  countAbove1R: number;
  countBelow1R: number;
  distribution: {
    '< -5%': number;
    '-5% to 0%': number;
    '0% to 1%': number;
    '1% to 5%': number;
    '> 5%': number;
  };
}

export interface InstitutionalMetrics {
  // Risk-Adjusted Returns
  sharpeRatio: number;
  sortinoRatio: number;
  calmarRatio: number;
  
  // Drawdown Metrics
  maxDrawdown: number;
  maxDrawdownDollars: number;
  maxDrawdownDuration: number;
  
  // Profitability Metrics
  profitFactor: number;
  expectancy: number;
  recoveryFactor: number;
  
  // Streak Analysis
  maxWinStreak: number;
  maxLossStreak: number;
  currentStreak: number;
  currentStreakType: string;
  
  // Returns Distribution
  monthlyReturns: MonthlyReturn[];
  rMultiples: RMultipleDistribution;
  
  // Time Metrics
  avgTradeDurationHours: number;
  
  // Basic Stats (reference)
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
}

export interface TradeAnalytics {
  totalTrades: number;
  totalVolume: number;
  buyTrades: number;
  sellTrades: number;
  avgTradeValue: number;
  totalRealizedPnL: number;
  winningTrades: number;
  losingTrades: number;
  winRate: number;
  avgWinningTrade: number;
  avgLosingTrade: number;
  bestTrade: BestWorstTrade | null;
  worstTrade: BestWorstTrade | null;
  pnlByDay: PnLByDay[];
  institutionalMetrics?: InstitutionalMetrics | null;
}

// Helper type for date range picker
export type DateRange = [string, string] | null;

// Helper type for filter form values
export interface TradeFilterForm {
  dateRange: DateRange;
  symbol: string;
  strategyId: string;
  side: 'all' | 'buy' | 'sell';
}
