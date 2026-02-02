/**
 * Market Data WebSocket Hook
 * 
 * React hook for managing WebSocket connection to market data service
 * Integrates WebSocket service with Zustand store
 */

import { useEffect, useCallback, useRef, useMemo } from 'react';
import { useMarketDataStore } from '../store/marketDataStore';
import { getMarketDataService } from '../services/marketDataWebSocketService';
import { ConnectionState } from '../types/marketData';
import type { Quote, ErrorMessage } from '../types/marketData';
import { getAuthToken } from '../utils/auth'; // Use centralized auth utility

/**
 * Hook for managing market data WebSocket connection
 * 
 * @example
 * ```tsx
 * function MyComponent() {
 *   const { subscribe, unsubscribe, connected } = useMarketDataWebSocket();
 *   
 *   useEffect(() => {
 *     subscribe('AAPL');
 *     return () => unsubscribe('AAPL');
 *   }, []);
 *   
 *   const quote = useQuote('AAPL');
 *   return <div>AAPL: ${quote?.last}</div>;
 * }
 * ```
 */
export function useMarketDataWebSocket() {
  const service = useRef(getMarketDataService());
  
  // Track if initialized
  const initialized = useRef(false);
  
  /**
   * Initialize WebSocket connection and callbacks
   */
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    
    const marketDataService = service.current;
    
    // Set up connection state callback
    const unsubscribeConnection = marketDataService.onConnectionStateChange((state) => {
      const storeState = useMarketDataStore.getState();
      storeState.setConnectionState(state);
      
      // Clear quotes on disconnect
      if (state === ConnectionState.DISCONNECTED || state === ConnectionState.FAILED) {
        storeState.clearQuotes();
      }
    });
    
    // Set up error callback
    const unsubscribeError = marketDataService.onError((error: ErrorMessage) => {
      console.error('[useMarketDataWebSocket] Error:', error.message, error.code);
      const storeState = useMarketDataStore.getState();
      storeState.setError(error.message);
      
      // Clear error after 5 seconds
      setTimeout(() => {
        useMarketDataStore.getState().setError(null);
      }, 5000);
    });
    
    // Connect to WebSocket
    const token = getAuthToken();
    if (token) {
      marketDataService.connect(token).catch((error) => {
        console.error('[useMarketDataWebSocket] Connection failed:', error);
        useMarketDataStore.getState().setError('Failed to connect to market data service');
      });
    } else {
      console.warn('[useMarketDataWebSocket] No auth token found');
      useMarketDataStore.getState().setError('Authentication required');
    }
    
    // Cleanup on unmount
    return () => {
      unsubscribeConnection();
      unsubscribeError();
      // Note: Don't disconnect here as other components might be using it
      // Connection will be managed by the service singleton
    };
  }, []); // Run once on mount
  
  /**
   * Subscribe to symbol quotes
   */
  const subscribe = useCallback((symbol: string) => {
    const normalizedSymbol = symbol.toUpperCase();
    const storeState = useMarketDataStore.getState();
    
    // Add to store subscriptions
    storeState.addSubscription(normalizedSymbol);
    
    // Subscribe to service with callback
    const callback = (quote: Quote) => {
      useMarketDataStore.getState().updateQuote(normalizedSymbol, quote);
    };
    
    service.current.subscribe(normalizedSymbol, callback);
    
    return () => {
      service.current.unsubscribe(normalizedSymbol, callback);
      useMarketDataStore.getState().removeSubscription(normalizedSymbol);
      useMarketDataStore.getState().removeQuote(normalizedSymbol);
    };
  }, []); // Empty deps - all dependencies are stable
  
  /**
   * Unsubscribe from symbol quotes
   */
  const unsubscribe = useCallback((symbol: string) => {
    const normalizedSymbol = symbol.toUpperCase();
    const storeState = useMarketDataStore.getState();
    
    service.current.unsubscribe(normalizedSymbol);
    storeState.removeSubscription(normalizedSymbol);
    storeState.removeQuote(normalizedSymbol);
  }, []);
  
  /**
   * Subscribe to multiple symbols
   */
  const subscribeMultiple = useCallback((symbols: string[]) => {
    const unsubscribers = symbols.map(symbol => subscribe(symbol));
    
    return () => {
      unsubscribers.forEach(unsub => unsub());
    };
  }, [subscribe]);
  
  /**
   * Unsubscribe from all symbols
   */
  const unsubscribeAll = useCallback(() => {
    const subscriptions = Array.from(useMarketDataStore.getState().subscriptions);
    subscriptions.forEach(symbol => {
      unsubscribe(symbol);
    });
  }, [unsubscribe]);
  
  /**
   * Reconnect to WebSocket
   */
  const reconnect = useCallback(() => {
    const token = getAuthToken();
    if (token) {
      service.current.disconnect();
      setTimeout(() => {
        service.current.connect(token).catch((error) => {
          console.error('[useMarketDataWebSocket] Reconnection failed:', error);
          useMarketDataStore.getState().setError('Failed to reconnect to market data service');
        });
      }, 1000);
    }
  }, []);
  
  /**
   * Disconnect from WebSocket
   */
  const disconnect = useCallback(() => {
    service.current.disconnect();
    useMarketDataStore.getState().reset();
  }, []);
  
  // Use selectors for reactive values to prevent unnecessary re-renders
  const connectionState = useMarketDataStore((state) => state.connectionState);
  const error = useMarketDataStore((state) => state.error);
  // Don't subscribe to subscriptions here - it causes re-renders
  // Use getState() when needed instead
  
  // Memoize the return object to prevent identity changes
  return useMemo(() => ({
    // State
    connected: connectionState === ConnectionState.CONNECTED,
    connecting: connectionState === ConnectionState.CONNECTING,
    disconnected: connectionState === ConnectionState.DISCONNECTED,
    reconnecting: connectionState === ConnectionState.RECONNECTING,
    connectionState,
    error,
    
    // Subscriptions - use getState() to avoid reactivity
    get subscriptions() {
      return Array.from(useMarketDataStore.getState().subscriptions);
    },
    isSubscribed: (symbol: string) => useMarketDataStore.getState().subscriptions.has(symbol.toUpperCase()),
    
    // Actions
    subscribe,
    unsubscribe,
    subscribeMultiple,
    unsubscribeAll,
    reconnect,
    disconnect,
    
    // Service instance (for advanced usage)
    service: service.current,
  }), [connectionState, error, subscribe, unsubscribe, subscribeMultiple, unsubscribeAll, reconnect, disconnect]);
}

/**
 * Hook to subscribe to a symbol and get its quote
 * Automatically subscribes on mount and unsubscribes on unmount
 * 
 * @example
 * ```tsx
 * function StockPrice({ symbol }) {
 *   const quote = useSymbolQuote(symbol);
 *   
 *   if (!quote) return <div>Loading...</div>;
 *   
 *   return (
 *     <div>
 *       {symbol}: ${quote.last}
 *       <span>Bid: ${quote.bid} | Ask: ${quote.ask}</span>
 *     </div>
 *   );
 * }
 * ```
 */
export function useSymbolQuote(symbol: string) {
  const { subscribe } = useMarketDataWebSocket();
  // Use selector to only re-render when this symbol's quote changes
  const quote = useMarketDataStore((state) => state.quotes[symbol.toUpperCase()]);
  
  useEffect(() => {
    const cleanup = subscribe(symbol);
    return cleanup;
  }, [symbol, subscribe]);
  
  return quote;
}

/**
 * Hook to get latest price for a symbol
 * Automatically subscribes on mount and unsubscribes on unmount
 * 
 * @example
 * ```tsx
 * function CurrentPrice({ symbol }) {
 *   const price = useSymbolPrice(symbol);
 *   
 *   return <div>{symbol}: ${price?.toFixed(2) || '...'}</div>;
 * }
 * ```
 */
export function useSymbolPrice(symbol: string): number | undefined {
  const { subscribe } = useMarketDataWebSocket();
  // Use selector to only re-render when this symbol's price changes
  const price = useMarketDataStore((state) => {
    const quote = state.quotes[symbol.toUpperCase()];
    return quote ? (quote.last || quote.mid) : undefined;
  });
  
  useEffect(() => {
    const cleanup = subscribe(symbol);
    return cleanup;
  }, [symbol, subscribe]);
  
  return price;
}

/**
 * Hook to subscribe to multiple symbols
 * 
 * @example
 * ```tsx
 * function Watchlist({ symbols }) {
 *   useMultipleSymbols(symbols);
 *   
 *   return (
 *     <div>
 *       {symbols.map(symbol => (
 *         <QuoteRow key={symbol} symbol={symbol} />
 *       ))}
 *     </div>
 *   );
 * }
 * ```
 */
export function useMultipleSymbols(symbols: string[]) {
  const { subscribeMultiple } = useMarketDataWebSocket();
  
  useEffect(() => {
    if (symbols.length === 0) return;
    
    const cleanup = subscribeMultiple(symbols);
    return cleanup;
  }, [symbols.join(','), subscribeMultiple]); // Join symbols to create stable dependency
}
