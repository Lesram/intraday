/**
 * Strategies Service
 * API endpoints for trading strategies
 */

import { apiClient } from './api';
import type {
  Strategy,
  CreateStrategyRequest,
  UpdateStrategyRequest,
  UpdatePerformanceRequest,
  PerformanceMetrics
} from '@/types/strategy';

// Re-export types for convenience
export type {
  Strategy,
  CreateStrategyRequest,
  UpdateStrategyRequest,
  UpdatePerformanceRequest,
  PerformanceMetrics
};

export const strategiesService = {
  /**
   * Get all strategies
   */
  getStrategies: async (): Promise<Strategy[]> => {
    const response = await apiClient.get<Strategy[]>('/strategies');
    return response.data;
  },

  /**
   * Get strategy by ID
   */
  getStrategy: async (strategyId: string): Promise<Strategy> => {
    const response = await apiClient.get<Strategy>(`/strategies/${strategyId}`);
    return response.data;
  },

  /**
   * Create new strategy
   */
  createStrategy: async (data: CreateStrategyRequest): Promise<Strategy> => {
    // Transform camelCase to snake_case for API
    const apiData = {
      name: data.name,
      description: data.description,
      strategy_type: data.strategyType,  // Transform camelCase → snake_case
      symbols: data.symbols,
      parameters: data.parameters,
    };
    const response = await apiClient.post<Strategy>('/strategies', apiData);
    return response.data;
  },

  /**
   * Update strategy
   */
  updateStrategy: async (
    strategyId: string,
    updates: UpdateStrategyRequest
  ): Promise<Strategy> => {
    // Transform camelCase to snake_case for API
    const apiUpdates: Record<string, unknown> = {};
    if (updates.name !== undefined) apiUpdates.name = updates.name;
    if (updates.description !== undefined) apiUpdates.description = updates.description;
    if (updates.strategyType !== undefined) apiUpdates.strategy_type = updates.strategyType;
    if (updates.symbols !== undefined) apiUpdates.symbols = updates.symbols;
    if (updates.parameters !== undefined) apiUpdates.parameters = updates.parameters;
    
    const response = await apiClient.patch<Strategy>(
      `/strategies/${strategyId}`,
      apiUpdates
    );
    return response.data;
  },

  /**
   * Delete strategy
   */
  deleteStrategy: async (strategyId: string): Promise<void> => {
    await apiClient.delete(`/strategies/${strategyId}`);
  },

  /**
   * Start strategy
   */
  startStrategy: async (strategyId: string): Promise<Strategy> => {
    const response = await apiClient.post<Strategy>(
      `/strategies/${strategyId}/start`
    );
    return response.data;
  },

  /**
   * Stop strategy
   */
  stopStrategy: async (strategyId: string): Promise<Strategy> => {
    const response = await apiClient.post<Strategy>(
      `/strategies/${strategyId}/stop`
    );
    return response.data;
  },

  /**
   * Pause strategy
   */
  pauseStrategy: async (strategyId: string): Promise<Strategy> => {
    const response = await apiClient.post<Strategy>(
      `/strategies/${strategyId}/pause`
    );
    return response.data;
  },

  /**
   * Get strategy performance metrics
   */
  getStrategyPerformance: async (strategyId: string): Promise<PerformanceMetrics> => {
    const response = await apiClient.get<PerformanceMetrics>(
      `/strategies/${strategyId}/performance`
    );
    return response.data;
  },

  /**
   * Update strategy performance metrics
   */
  updateStrategyPerformance: async (
    strategyId: string,
    metrics: UpdatePerformanceRequest
  ): Promise<Strategy> => {
    const response = await apiClient.put<Strategy>(
      `/strategies/${strategyId}/performance`,
      metrics
    );
    return response.data;
  },
};
