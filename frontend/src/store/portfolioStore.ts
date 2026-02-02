/**
 * Portfolio Store
 * Manages portfolio state and real-time updates
 */

import { create } from 'zustand';

// Types
export interface Position {
  symbol: string;
  quantity: number;
  averagePrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnL: number;
  unrealizedPnLPercent: number;
  side: 'long' | 'short';
  exchange: string;
  entryDate?: string; // Date of first buy order
}

export interface Portfolio {
  userId: string;
  totalEquity: number;
  cash: number;
  buyingPower: number;
  marginUsed: number;
  maintenanceMargin: number;
  totalPnL: number;
  totalPnLPercent: number;
  dayPnL: number;
  dayPnLPercent: number;
  positions: Position[];
  lastUpdate: string;
}

interface PortfolioState {
  portfolio: Portfolio | null;
  positions: Position[];
  isLoading: boolean;
  error: string | null;
  
  // Actions
  setPortfolio: (portfolio: Portfolio) => void;
  setPositions: (positions: Position[]) => void;
  updatePosition: (symbol: string, updates: Partial<Position>) => void;
  removePosition: (symbol: string) => void;
  setLoading: (isLoading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  portfolio: null,
  positions: [],
  isLoading: false,
  error: null,
};

export const usePortfolioStore = create<PortfolioState>((set) => ({
  ...initialState,

  setPortfolio: (portfolio) =>
    set({
      portfolio,
      positions: portfolio.positions,
      error: null,
    }),

  setPositions: (positions) =>
    set((state) => ({
      positions,
      portfolio: state.portfolio
        ? {
            ...state.portfolio,
            positions,
          }
        : null,
    })),

  updatePosition: (symbol, updates) =>
    set((state) => {
      const positions = state.positions.map((pos) =>
        pos.symbol === symbol ? { ...pos, ...updates } : pos
      );

      return {
        positions,
        portfolio: state.portfolio
          ? {
              ...state.portfolio,
              positions,
            }
          : null,
      };
    }),

  removePosition: (symbol) =>
    set((state) => {
      const positions = state.positions.filter((pos) => pos.symbol !== symbol);

      return {
        positions,
        portfolio: state.portfolio
          ? {
              ...state.portfolio,
              positions,
            }
          : null,
      };
    }),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  reset: () => set(initialState),
}));
