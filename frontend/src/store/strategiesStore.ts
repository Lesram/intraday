/**
 * Strategies Store
 * Manages trading strategies state
 */

import { create } from 'zustand';
import type {
  Strategy,
  StrategyStatus,
  PerformanceMetrics
} from '@/types/strategy';

interface StrategiesState {
  strategies: Strategy[];
  selectedStrategyId: string | null;
  isLoading: boolean;
  error: string | null;

  // Actions
  setStrategies: (strategies: Strategy[]) => void;
  addStrategy: (strategy: Strategy) => void;
  updateStrategy: (strategyId: string, updates: Partial<Strategy>) => void;
  updateStrategyPerformance: (strategyId: string, performance: PerformanceMetrics) => void;
  removeStrategy: (strategyId: string) => void;
  setSelectedStrategy: (strategyId: string | null) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;

  // Computed
  getActiveStrategies: () => Strategy[];
  getStrategyById: (strategyId: string) => Strategy | undefined;
}

const initialState = {
  strategies: [],
  selectedStrategyId: null,
  isLoading: false,
  error: null,
};

export const useStrategiesStore = create<StrategiesState>((set, get) => ({
  ...initialState,

  setStrategies: (strategies) =>
    set({
      strategies,
      error: null,
    }),

  addStrategy: (strategy) =>
    set((state) => ({
      strategies: [strategy, ...state.strategies],
    })),

  updateStrategy: (strategyId, updates) =>
    set((state) => ({
      strategies: state.strategies.map((strategy) =>
        strategy.strategyId === strategyId ? { ...strategy, ...updates } : strategy
      ),
    })),

  updateStrategyPerformance: (strategyId, performance) =>
    set((state) => ({
      strategies: state.strategies.map((strategy) =>
        strategy.strategyId === strategyId
          ? { ...strategy, performance }
          : strategy
      ),
    })),

  removeStrategy: (strategyId) =>
    set((state) => ({
      strategies: state.strategies.filter((s) => s.strategyId !== strategyId),
      selectedStrategyId:
        state.selectedStrategyId === strategyId ? null : state.selectedStrategyId,
    })),

  setSelectedStrategy: (strategyId) =>
    set({ selectedStrategyId: strategyId }),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  reset: () => set(initialState),

  // Computed
  getActiveStrategies: () =>
    get().strategies.filter((strategy) => strategy.status === 'active'),

  getStrategyById: (strategyId) =>
    get().strategies.find((strategy) => strategy.strategyId === strategyId),
}));

// Re-export types for backward compatibility
export type { Strategy, StrategyStatus, PerformanceMetrics };
