/**
 * Market Data Store
 * Manages real-time market data state using Zustand
 */

import { create } from 'zustand';
import type { Quote, ConnectionState } from '../types/marketData';

/**
 * Quote with additional metadata
 */
export interface QuoteWithMetadata extends Quote {
  lastUpdate: number; // Timestamp in ms
  updateCount: number; // Number of updates received
}

/**
 * Market data store state
 */
interface MarketDataState {
  // Connection state
  connectionState: ConnectionState;
  clientId: string | null;
  
  // Quotes by symbol
  quotes: Record<string, QuoteWithMetadata>;
  
  // Subscriptions
  subscriptions: Set<string>;
  
  // Statistics
  totalUpdates: number;
  lastUpdateTime: number | null;
  
  // Error state
  error: string | null;
  
  // Actions
  setConnectionState: (state: ConnectionState) => void;
  setClientId: (clientId: string | null) => void;
  
  updateQuote: (symbol: string, quote: Quote) => void;
  removeQuote: (symbol: string) => void;
  clearQuotes: () => void;
  
  addSubscription: (symbol: string) => void;
  removeSubscription: (symbol: string) => void;
  clearSubscriptions: () => void;
  
  setError: (error: string | null) => void;
  reset: () => void;
  
  // Selectors
  getQuote: (symbol: string) => QuoteWithMetadata | undefined;
  getLatestPrice: (symbol: string) => number | undefined;
  getSpread: (symbol: string) => number | undefined;
  isSubscribed: (symbol: string) => boolean;
}

/**
 * Initial state
 */
const initialState = {
  connectionState: 'DISCONNECTED' as ConnectionState,
  clientId: null,
  quotes: {},
  subscriptions: new Set<string>(),
  totalUpdates: 0,
  lastUpdateTime: null,
  error: null,
};

/**
 * Market data store
 */
export const useMarketDataStore = create<MarketDataState>((set, get) => ({
  ...initialState,
  
  // Connection actions
  setConnectionState: (connectionState) => {
    set({ connectionState });
  },
  
  setClientId: (clientId) => {
    set({ clientId });
  },
  
  // Quote actions
  updateQuote: (symbol, quote) => {
    set((state) => {
      const now = Date.now();
      const existingQuote = state.quotes[symbol];
      
      return {
        quotes: {
          ...state.quotes,
          [symbol]: {
            ...quote,
            lastUpdate: now,
            updateCount: existingQuote ? existingQuote.updateCount + 1 : 1,
          },
        },
        totalUpdates: state.totalUpdates + 1,
        lastUpdateTime: now,
      };
    });
  },
  
  removeQuote: (symbol) => {
    set((state) => {
      const { [symbol]: _removed, ...remaining } = state.quotes;
      return { quotes: remaining };
    });
  },
  
  clearQuotes: () => {
    set({ quotes: {} });
  },
  
  // Subscription actions
  addSubscription: (symbol) => {
    set((state) => ({
      subscriptions: new Set([...state.subscriptions, symbol.toUpperCase()]),
    }));
  },
  
  removeSubscription: (symbol) => {
    set((state) => {
      const newSubscriptions = new Set(state.subscriptions);
      newSubscriptions.delete(symbol.toUpperCase());
      return { subscriptions: newSubscriptions };
    });
  },
  
  clearSubscriptions: () => {
    set({ subscriptions: new Set() });
  },
  
  // Error actions
  setError: (error) => {
    set({ error });
  },
  
  // Reset
  reset: () => {
    set(initialState);
  },
  
  // Selectors
  getQuote: (symbol) => {
    return get().quotes[symbol.toUpperCase()];
  },
  
  getLatestPrice: (symbol) => {
    const quote = get().quotes[symbol.toUpperCase()];
    return quote?.last || quote?.mid;
  },
  
  getSpread: (symbol) => {
    const quote = get().quotes[symbol.toUpperCase()];
    return quote?.spread;
  },
  
  isSubscribed: (symbol) => {
    return get().subscriptions.has(symbol.toUpperCase());
  },
}));

/**
 * Selector hooks for optimized re-renders
 */

/**
 * Get quote for a specific symbol
 */
export const useQuote = (symbol: string): QuoteWithMetadata | undefined => {
  return useMarketDataStore((state) => state.quotes[symbol.toUpperCase()]);
};

/**
 * Get latest price for a symbol
 */
export const useLatestPrice = (symbol: string): number | undefined => {
  return useMarketDataStore((state) => {
    const quote = state.quotes[symbol.toUpperCase()];
    return quote?.last || quote?.mid;
  });
};

/**
 * Get bid/ask for a symbol
 */
export const useBidAsk = (symbol: string): { bid: number; ask: number } | undefined => {
  return useMarketDataStore((state) => {
    const quote = state.quotes[symbol.toUpperCase()];
    if (!quote) return undefined;
    return { bid: quote.bid, ask: quote.ask };
  });
};

/**
 * Get spread for a symbol
 */
export const useSpread = (symbol: string): number | undefined => {
  return useMarketDataStore((state) => state.quotes[symbol.toUpperCase()]?.spread);
};

/**
 * Get connection state
 */
export const useConnectionState = (): ConnectionState => {
  return useMarketDataStore((state) => state.connectionState);
};

/**
 * Check if subscribed to symbol
 */
export const useIsSubscribed = (symbol: string): boolean => {
  return useMarketDataStore((state) => state.subscriptions.has(symbol.toUpperCase()));
};

/**
 * Get all subscriptions
 */
export const useSubscriptions = (): string[] => {
  return useMarketDataStore((state) => Array.from(state.subscriptions));
};

/**
 * Get market data statistics
 */
export const useMarketDataStats = () => {
  return useMarketDataStore((state) => ({
    totalUpdates: state.totalUpdates,
    lastUpdateTime: state.lastUpdateTime,
    activeSubscriptions: state.subscriptions.size,
    quotesInMemory: Object.keys(state.quotes).length,
    connectionState: state.connectionState,
  }));
};
