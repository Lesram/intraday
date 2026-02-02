/**
 * WebSocket Types
 * Message types for WebSocket communication
 */

export interface WebSocketMessage {
  type: string;
  topic?: string;
  data: unknown;
  timestamp: number;
  sequence?: number;
}

export type WebSocketTopic =
  | 'orders'
  | 'positions'
  | 'portfolio'
  | 'market_data'
  | 'signals'
  | 'strategies'
  | 'alerts'
  | 'risk';

export interface SubscribeMessage {
  type: 'subscribe';
  topic: WebSocketTopic;
  symbols?: string[];
  timestamp: number;
}

export interface UnsubscribeMessage {
  type: 'unsubscribe';
  topic: WebSocketTopic;
  timestamp: number;
}

export interface HeartbeatMessage {
  type: 'heartbeat';
  timestamp: number;
}

export interface AcknowledgeMessage {
  type: 'ack';
  original_type: string;
  status: 'success' | 'error';
  message?: string;
  timestamp: number;
}

// Topic-specific message types
export interface OrderUpdateMessage extends WebSocketMessage {
  type: 'order_update';
  topic: 'orders';
  data: {
    order_id: string;
    symbol: string;
    side: 'buy' | 'sell';
    order_type: string;
    quantity: number;
    filled_quantity: number;
    status: string;
    price?: number;
    stop_price?: number;
    timestamp: string;
  };
}

export interface PositionUpdateMessage extends WebSocketMessage {
  type: 'position_update';
  topic: 'positions';
  data: {
    symbol: string;
    quantity: number;
    average_price: number;
    current_price: number;
    unrealized_pnl: number;
    realized_pnl: number;
    timestamp: string;
  };
}

export interface PortfolioUpdateMessage extends WebSocketMessage {
  type: 'portfolio_update';
  topic: 'portfolio';
  data: {
    equity: number;
    cash: number;
    buying_power: number;
    daily_pnl: number;
    daily_pnl_percent: number;
    positions_value: number;
    timestamp: string;
  };
}

export interface MarketDataMessage extends WebSocketMessage {
  type: 'market_data';
  topic: 'market_data';
  data: {
    symbol: string;
    price: number;
    bid: number;
    ask: number;
    volume: number;
    timestamp: string;
  };
}

export interface SignalMessage extends WebSocketMessage {
  type: 'signal';
  topic: 'signals';
  data: {
    signal_id: string;
    strategy_id: string;
    symbol: string;
    action: 'buy' | 'sell' | 'hold';
    confidence: number;
    price: number;
    timestamp: string;
  };
}

export interface StrategyUpdateMessage extends WebSocketMessage {
  type: 'strategy_update';
  topic: 'strategies';
  data: {
    action?: 'updated' | 'deleted';
    strategy?: {
      strategyId: string;
      name: string;
      description: string;
      strategyType: 'momentum' | 'mean_reversion' | 'ensemble' | 'stat_arb';
      symbols: string[];
      parameters: Record<string, unknown>;
      status: 'active' | 'paused' | 'stopped' | 'error';
      performance?: {
        totalTrades: number;
        winRate: number;
        totalPnL: number;
        sharpeRatio: number;
        maxDrawdown: number;
      };
      createdAt: string;
      updatedAt: string;
      lastExecutedAt?: string;
    };
    // Legacy format support
    strategyId: string;
    name?: string;
    description?: string;
    strategyType?: 'momentum' | 'mean_reversion' | 'ensemble' | 'stat_arb';
    symbols?: string[];
    parameters?: Record<string, unknown>;
    status?: 'active' | 'paused' | 'stopped' | 'error';
    performance?: {
      totalTrades: number;
      winRate: number;
      totalPnL: number;
      sharpeRatio: number;
      maxDrawdown: number;
    };
    createdAt?: string;
    updatedAt?: string;
    lastExecutedAt?: string;
  };
}

export interface AlertMessage extends WebSocketMessage {
  type: 'alert';
  topic: 'alerts';
  data: {
    alert_id: string;
    level: 'info' | 'warning' | 'error' | 'critical';
    message: string;
    source: string;
    timestamp: string;
  };
}

export interface RiskUpdateMessage extends WebSocketMessage {
  type: 'risk_update';
  topic: 'risk';
  data: {
    portfolio_var: number;
    max_drawdown: number;
    sharpe_ratio: number;
    risk_score: number;
    warnings: string[];
    timestamp: string;
  };
}
