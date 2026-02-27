export interface DbTable {
  table: string;
  keyColumns: string;
  purpose: string;
}

export const dbTables: DbTable[] = [
  { table: 'users', keyColumns: 'id, username (unique), email (unique), hashed_password, roles (ARRAY)', purpose: 'Auth + RBAC' },
  { table: 'orders', keyColumns: 'id (UUID), user_id, client_idempotency_key (unique), symbol, side, qty, status, broker_order_id, attributes (JSONB)', purpose: 'Order lifecycle' },
  { table: 'executions', keyColumns: 'id (UUID), order_id (FK), fill_qty, fill_price, ts, venue', purpose: 'Fill records' },
  { table: 'outbox_events', keyColumns: 'id, topic, payload (JSONB), status, attempts, next_attempt_at, last_error', purpose: 'Transactional outbox' },
  { table: 'model_lifecycle_events', keyColumns: 'id, model_id, model_name, model_version, event_type, payload', purpose: 'ML model audit trail' },
  { table: 'signals', keyColumns: 'id, symbol, model_name, signal_type, direction, strength, confidence', purpose: 'Trading signals' },
  { table: 'positions', keyColumns: 'id, symbol, qty, avg_cost, market_value, unrealized_pnl, attributes', purpose: 'Position state' },
  { table: 'audit_logs', keyColumns: 'id, action, entity, entity_id, actor, ts', purpose: 'Audit trail' },
  { table: 'model_registry', keyColumns: 'id, name, version, model_type, status, metadata, config, performance_metrics', purpose: 'ML model registry' },
  { table: 'strategies', keyColumns: 'id, name, strategy_type, status, symbols, parameters, total_pnl, win_rate', purpose: 'Strategy config' },
  { table: 'risk_limits', keyColumns: 'id (UUID), user_id (FK), limit_name, limit_value, warning_threshold, critical_threshold', purpose: 'Risk limit definitions' },
  { table: 'risk_metrics', keyColumns: 'id (UUID), user_id (FK), metric_name, current_value, limit_value, percent_used, status', purpose: 'Live risk measurements' },
  { table: 'risk_violations', keyColumns: 'id (UUID), user_id (FK), metric_name, violation_type, severity, resolved', purpose: 'Risk breach records' },
  { table: 'emergency_stops', keyColumns: 'id (UUID), user_id (FK), triggered_by (FK), reason, status (active/resolved)', purpose: 'Emergency stop events' },
  { table: 'portfolio_history', keyColumns: 'id, user_id (FK), timestamp, total_equity, cash, daily_pnl, snapshot_type', purpose: 'Equity time series' },
  { table: 'position_lots', keyColumns: 'id (UUID), user_id (FK), symbol, qty, remaining_qty, cost_basis, status (open/closed)', purpose: 'FIFO tax lot tracking' },
  { table: 'realized_trades', keyColumns: 'id (UUID), user_id (FK), symbol, qty, open_price, close_price, realized_pnl', purpose: 'Closed trade records' },
  { table: 'backtests', keyColumns: 'id (UUID), strategy_id (FK), start/end_date, initial_capital, metrics (JSON), equity_curve (JSON)', purpose: 'Backtest results' },
  { table: 'order_events', keyColumns: 'id, order_id (FK), event_type, data (JSONB), ts', purpose: 'Order lifecycle event log' },
  { table: 'model_monitoring_snapshots', keyColumns: 'id, model_id (FK), metrics (JSONB), ts', purpose: 'ML model performance snapshots' },
  { table: 'watchlists', keyColumns: 'id, user_id (FK), name, symbols (ARRAY), created_at', purpose: 'User watchlists' },
  { table: 'watchlist_symbols', keyColumns: 'id, watchlist_id (FK), symbol, added_at', purpose: 'Watchlist symbol membership' },
  { table: 'chart_templates', keyColumns: 'id, user_id (FK), name, config (JSONB), created_at', purpose: 'Saved chart configurations' },
  { table: 'drawings', keyColumns: 'id, user_id (FK), symbol, drawing_type, data (JSONB), created_at', purpose: 'TradingView-style chart drawings' },
];

export interface StartupStep {
  step: number;
  component: string;
  behavior: string;
}

export const startupSteps: StartupStep[] = [
  { step: 1, component: 'Observability (OTel + Prometheus)', behavior: 'non-critical' },
  { step: 2, component: 'SLO metrics collector', behavior: 'non-critical' },
  { step: 3, component: 'Database init + pool pre-warming', behavior: '5 connections' },
  { step: 4, component: 'Outbox worker start', behavior: 'if DB available, not reload mode' },
  { step: 5, component: 'Living strategy policy', behavior: 'LIVING_STRATEGY_ENABLED=true, opt-out' },
  { step: 6, component: 'Living organism', behavior: 'ORGANISM_ENABLED=0, opt-in' },
  { step: 7, component: 'Multi-strategy runner', behavior: 'MULTI_STRATEGY_LIVE_ENABLED=0, opt-in; skipped if organism active' },
  { step: 8, component: 'Auto breakout scanner', behavior: 'AUTO_BREAKOUT_SCAN_ENABLED=0, opt-in' },
  { step: 9, component: 'ML lifecycle scheduler', behavior: 'ENABLE_ML_LIFECYCLE_SCHEDULER=0, opt-in' },
  { step: 10, component: 'Organism scheduler', behavior: 'ENABLE_ORGANISM_SCHEDULER=0, opt-in; cancels stale orders' },
  { step: 11, component: 'Alpaca WebSocket stream', behavior: 'real broker only' },
  { step: 12, component: 'Reconciliation scheduler', behavior: '15-min default' },
  { step: 13, component: 'Portfolio sync', behavior: 'initial sync' },
  { step: 14, component: 'Order sync from Alpaca', behavior: '500 most recent' },
];
