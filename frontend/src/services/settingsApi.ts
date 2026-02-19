import { apiClient } from '@/services/api';

export interface OrganismSettings {
  tick_interval_seconds: number;
  timeframe: string;
  lookback: number;
  max_positions: number;
  retrain_interval: number;
  use_streaming: boolean;
  universe: string[];
  min_bars: number;
}

export interface TradingSettings {
  max_position_pct: number;
  vol_target: number;
  min_position_usd: number;
  long_only: boolean;
  atr_multiplier: number;
  profit_r_multiple: number;
  trailing_distance_atr: number;
  max_bars_held: number;
  partial_tp_pct: number;
}

export interface MLSettings {
  n_estimators: number;
  max_depth: number;
  learning_rate: number;
  direction_threshold: number;
  retrain_interval: number;
}

export const settingsApi = {
  async getOrganismSettings(): Promise<OrganismSettings> {
    const { data } = await apiClient.get<OrganismSettings>('/settings/organism');
    return data;
  },

  async updateOrganismSettings(settings: Partial<OrganismSettings>): Promise<{ updated: Record<string, unknown>; saved: boolean }> {
    const { data } = await apiClient.put('/settings/organism', settings);
    return data;
  },

  async getTradingSettings(): Promise<TradingSettings> {
    const { data } = await apiClient.get<TradingSettings>('/settings/trading');
    return data;
  },

  async updateTradingSettings(settings: Partial<TradingSettings>): Promise<{ updated: Record<string, unknown>; saved: boolean }> {
    const { data } = await apiClient.put('/settings/trading', settings);
    return data;
  },

  async getMLSettings(): Promise<MLSettings> {
    const { data } = await apiClient.get<MLSettings>('/settings/ml');
    return data;
  },

  async updateMLSettings(settings: Partial<MLSettings>): Promise<{ updated: Record<string, unknown>; saved: boolean }> {
    const { data } = await apiClient.put('/settings/ml', settings);
    return data;
  },

  async restartEngine(): Promise<{ status: string; running: boolean }> {
    const { data } = await apiClient.post('/settings/restart-engine');
    return data;
  },
};
