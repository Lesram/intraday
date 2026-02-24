import { apiClient } from '@/services/api';

export interface ActivityEvent {
  type: string;
  symbol?: string;
  message: string;
  details?: Record<string, unknown>;
  timestamp?: string;
}

export interface OrganismRun {
  timestamp?: string;
  regime?: string;
  signals_generated?: number;
  orders_submitted?: number;
  exits_checked?: number;
  trades_closed?: number;
  brain_saved?: boolean;
  errors?: string[];
  duration_s?: number;
  // Phase 5: Scanner & Universe
  universe_size?: number;
  scanner_candidates_count?: number;
  scanner_ran?: boolean;
  // Activity feed
  activity?: ActivityEvent[];
}

export interface OrganismStatus {
  enabled?: boolean;
  governance?: {
    frozen?: boolean;
    halted?: boolean;
    drawdown_triggered?: boolean;
    policy_version?: number;
    change_budget_remaining?: number;
  };
  strategies?: Record<string, number>;
  regime?: {
    current?: string;
    confidence?: number;
    drift_detected?: boolean;
    last_regime?: string;
  };
  promotion?: {
    pipeline?: Array<{
      strategy_id: string;
      stage: string;
      entered_at: string;
    }>;
  };
  attribution?: Record<string, {
    pnl: number;
    sharpe: number;
    trades: number;
  }>;
  policy_weights?: Record<string, number>;
  tick_count?: number;
  live_engine?: {
    running?: boolean;
    tick_interval_s?: number;
    last_tick?: OrganismRun;
    tick_history?: OrganismRun[];
    engine?: EngineStats;
  };
}

export interface EngineStats {
  initialized?: boolean;
  tick_count?: number;
  total_trades?: number;
  brain_generation?: number;
  peak_equity?: number;
  current_equity?: number;
  cumulative_pnl?: number;
  win_rate?: number;
  winning_trades?: number;
  losing_trades?: number;
  avg_win?: number;
  avg_loss?: number;
  ml_accuracy?: number;
  ml_trained?: boolean;
  training_history?: Array<Record<string, unknown>>;
  regime?: string;
  shorts_enabled?: boolean;
  positions_tracked?: number;
  universe_size?: number;
  [key: string]: unknown;
}

export interface OrganismRunsResponse {
  enabled: boolean;
  running: boolean;
  tick_interval_s?: number;
  runs: OrganismRun[];
  engine?: EngineStats;
}

export interface OrganismPolicyResponse {
  enabled: boolean;
  weights?: Record<string, number>;
  scores?: Record<string, number>;
  mode?: string;
}

export interface OrganismAttributionResponse {
  attribution?: {
    rows?: Array<Record<string, unknown>>;
    summary?: Record<string, unknown>;
  } | null;
}

export interface ScannedStock {
  symbol: string;
  source: string;
  price: number;
  volume: number;
  change_pct: number;
  tension_score: number;
}

export interface ScannerStatus {
  enabled: boolean;
  scan_count: number;
  last_scan_time: string | null;
  candidate_count: number;
  candidates: ScannedStock[];
}

export interface SymbolFitness {
  symbol: string;
  fitness: number;
  total_trades: number;
  win_rate: number;
  avg_pnl: number;
  avg_volume_quality: number;
  last_rotated_gen: number;
}

export interface UniverseStatus {
  active_symbols: string[];
  universe_size: number;
  fitness_table: SymbolFitness[];
  scanner_candidates: string[];
  rotation_count: number;
  config: {
    min_universe: number;
    max_universe: number;
  };
}

export interface SectorExposure {
  sector: string;
  count: number;
  symbols: string[];
  total_value: number;
}

export interface RegimeTimelineEntry {
  regime: string;
  timestamp: string;
}

export interface ConfidenceBin {
  bin: string;
  correct: number;
  total: number;
}

export interface OrganismAnalytics {
  sector_exposure: SectorExposure[];
  regime_timeline: RegimeTimelineEntry[];
  confidence_distribution: ConfidenceBin[];
  regime_kelly_stats: Record<string, Record<string, number>>;
  calibration: Record<string, unknown>;
}

// ── Decision Telemetry Types ──────────────────────────────────────

export interface AlphaFactorScore {
  symbol: string;
  composite_score: number;
  factors: {
    ml: number;
    breakout: number;
    institutional: number;
    momentum: number;
    momentum_quality: number;
    vol_price_div: number;
    regime: number;
  };
  weights: Record<string, number>;
  direction: number;
  threshold: number;
  distance_to_threshold: number;
  passed_threshold: boolean;
  symbol_fitness: number;
  fitness_gate: number;
  passed_fitness: boolean;
}

export interface BreakoutFactorScore {
  symbol: string;
  composite_score: number;
  factors: {
    squeeze: number;
    volume: number;
    contraction: number;
    rs: number;
    pivot: number;
    flow: number;
  };
  weights: Record<string, number>;
  direction: number;
  squeeze_fired: boolean;
  volume_ratio: number;
  threshold: number;
  distance_to_threshold: number;
  passed_threshold: boolean;
}

export interface ExitProximity {
  symbol: string;
  current_price: number;
  entry_price: number;
  direction: number;
  pnl_pct: number;
  exits: {
    stop_loss: { level: number; distance_pct: number };
    take_profit: { level: number; distance_pct: number };
    trailing_stop: { level: number; distance_pct: number; active: boolean };
    partial_tp: { level: number; distance_pct: number; taken: boolean };
    time: { bars_held: number; max_bars: number; distance_pct: number };
  };
  atr_at_entry: number;
  regime_at_entry: string;
  highest_favorable: number;
  nearest_exit: string;
  nearest_exit_distance_pct: number;
}

export interface KellySizingStage {
  symbol: string;
  pipeline: {
    kelly_raw: number;
    kelly_half: number;
    drawdown_scale: number;
    vol_scale: number;
    regime_scale: number;
    confidence_scale: number;
    breakout_bonus: number;
    final_weight: number;
  };
  position_cap: number;
  shares: number;
  notional: number;
  direction: number;
}

export interface RegimeProbabilities {
  primary: string;
  probabilities: Record<string, number>;
  confidence: number;
  features: Record<string, number>;
}

export interface FilteringSummary {
  total_universe: number;
  had_features: number;
  alpha_scored: number;
  above_alpha_threshold: number;
  breakout_scored: number;
  above_breakout_threshold: number;
  passed_sector_gate: number;
  passed_fitness_gate: number;
  passed_cooldown: number;
  passed_position_limit: number;
  kelly_sized: number;
  orders_submitted: number;
}

export interface EvolutionSnapshot {
  tick_number: number;
  timestamp: string;
  generation: number;
  regime: string;
  equity: number;
  drawdown_pct: number;
  params: Record<string, unknown>;
}

export interface DecisionSnapshot {
  tick_number: number;
  timestamp: string;
  duration_s: number;
  regime: RegimeProbabilities;
  governance: {
    equity: number;
    peak_equity: number;
    drawdown_pct: number;
    is_halted: boolean;
    is_frozen: boolean;
  };
  evolution: {
    generation: number;
    params: Record<string, unknown>;
  };
  alpha_scores: AlphaFactorScore[];
  breakout_scores: BreakoutFactorScore[];
  exit_proximity: ExitProximity[];
  kelly_sizing: KellySizingStage[];
  filtering: FilteringSummary;
  open_positions: number;
  max_positions: number;
}

export interface DecisionResponse {
  active: boolean;
  snapshot: DecisionSnapshot | null;
}

export interface DecisionHistoryResponse {
  active: boolean;
  count: number;
  snapshots: DecisionSnapshot[];
}

export interface SymbolDecisionHistory {
  active: boolean;
  symbol: string;
  count: number;
  history: Array<{
    tick_number: number;
    timestamp: string;
    regime: string;
    alpha?: AlphaFactorScore;
    breakout?: BreakoutFactorScore;
    exit?: ExitProximity;
    kelly?: KellySizingStage;
  }>;
}

export interface ExitProximityResponse {
  active: boolean;
  exits: ExitProximity[];
}

export interface EvolutionHistoryResponse {
  active: boolean;
  count: number;
  history: EvolutionSnapshot[];
}

// ── Organism Orders Types ──────────────────────────────────────────

export interface OrganismOrder {
  order_id: string;
  symbol: string;
  side: string;
  qty: number;
  filled_qty: number;
  order_type: string;
  tif: string;
  status: string;
  avg_fill_price: number | null;
  limit_price: number | null;
  submitted_at: string | null;
  updated_at: string | null;
  reason: string | null;
  confidence: number | null;
  tick: number | null;
  broker_order_id: string | null;
}

export interface OrganismOrdersResponse {
  orders: OrganismOrder[];
  total: number;
}

export const organismApi = {
  async getStatus() {
    const { data } = await apiClient.get<OrganismStatus>('/organism/status');
    return data;
  },

  async getRuns(limit = 50) {
    const { data } = await apiClient.get<OrganismRunsResponse>(`/organism/runs?limit=${limit}`);
    return data;
  },

  async getPolicy() {
    const { data } = await apiClient.get<OrganismPolicyResponse>('/organism/policy');
    return data;
  },

  async getAttribution() {
    const { data } = await apiClient.get<OrganismAttributionResponse>('/organism/attribution');
    return data;
  },

  async getBrain() {
    const { data } = await apiClient.get<Record<string, unknown>>('/organism/brain');
    return data;
  },

  async action(action: 'freeze' | 'unfreeze' | 'halt' | 'resume' | 'train' | 'tick') {
    const { data } = await apiClient.post(`/organism/${action}`, {});
    return data;
  },

  async getScanner() {
    const { data } = await apiClient.get<ScannerStatus>('/organism/scanner');
    return data;
  },

  async getUniverse() {
    const { data } = await apiClient.get<UniverseStatus>('/organism/universe');
    return data;
  },

  async getAnalytics() {
    const { data } = await apiClient.get<OrganismAnalytics>('/organism/analytics');
    return data;
  },

  async getOrders(limit = 200, status = 'all') {
    const { data } = await apiClient.get<OrganismOrdersResponse>(`/organism/orders?limit=${limit}&status=${status}`);
    return data;
  },

  async getDecisions() {
    const { data } = await apiClient.get<DecisionResponse>('/organism/decisions');
    return data;
  },

  async getDecisionHistory(limit = 50) {
    const { data } = await apiClient.get<DecisionHistoryResponse>(`/organism/decisions/history?limit=${limit}`);
    return data;
  },

  async getDecisionBySymbol(symbol: string, limit = 50) {
    const { data } = await apiClient.get<SymbolDecisionHistory>(`/organism/decisions/symbol/${symbol}?limit=${limit}`);
    return data;
  },

  async getExitProximity() {
    const { data } = await apiClient.get<ExitProximityResponse>('/organism/decisions/exits');
    return data;
  },

  async getEvolutionHistory(limit = 50) {
    const { data } = await apiClient.get<EvolutionHistoryResponse>(`/organism/evolution/history?limit=${limit}`);
    return data;
  },
};
