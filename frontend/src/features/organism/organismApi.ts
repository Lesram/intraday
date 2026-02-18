import { apiClient } from '@/services/api';

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
    engine?: Record<string, unknown>;
  };
}

export interface OrganismRunsResponse {
  enabled: boolean;
  running: boolean;
  tick_interval_s?: number;
  runs: OrganismRun[];
  engine?: Record<string, unknown>;
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
};
