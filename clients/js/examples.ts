/**
 * Trading Platform API Client Usage Examples
 * 
 * This file demonstrates how to use the TypeScript API client
 * in various scenarios and frameworks.
 */

import { 
  TradingApiClient, 
  isApiError, 
  type ActOnSignalRequest
} from './api';

// ============================================================================
// Basic Usage Example
// ============================================================================

async function basicUsageExample() {
  // Create client instance
  const client = new TradingApiClient('http://localhost:8000');
  
  // Set authentication token (get this from your auth flow)
  const token = 'your-jwt-token-here';
  client.setAuthToken(token);
  
  try {
    // Get trading signals
    console.log('Fetching signals for AAPL...');
    const signals = await client.getSignals('AAPL');
    console.log('Found signals:', signals.signals.length);
    
    // Act on the first signal if available
    if (signals.signals.length > 0) {
      const signal = signals.signals[0];
      if (signal) {
        console.log('Acting on signal:', signal.id);
        
        const orderResult = await client.actOnSignal({
          symbol: signal.symbol,
          side: signal.signal_type === 'buy' ? 'buy' : 'sell',
          qty: 10, // Small test quantity
          order_type: 'market',
          tif: 'gtc',
          signal_id: signal.id
        });
        
        console.log('Order placed:', orderResult.order.id);
        
        // Monitor order status
        let order = orderResult.order;
        let attempts = 0;
        while (order.status === 'submitted' && attempts < 10) {
          await new Promise(resolve => setTimeout(resolve, 1000)); // Wait 1 second
          order = await client.getOrder(order.id);
          console.log(`Order status: ${order.status}`);
          attempts++;
        }
      }
    }
    
    // Get current positions
    const positions = await client.getPositions();
    console.log('Current positions:', positions.positions.length);
    
  } catch (error) {
    if (isApiError(error)) {
      console.error(`API Error ${error.status}: ${error.message}`);
    } else {
      console.error('Unexpected error:', error);
    }
  }
}

// ============================================================================
// React Hook Example (TypeScript)
// ============================================================================

/*
// This would typically be in a separate file: hooks/useTrading.ts
// NOTE: Install React types: npm install @types/react

import React, { useState, useEffect } from 'react';
import { TradingApiClient, isApiError, ActOnSignalRequest } from './api';

export function useTradingApi(baseUrl: string) {
  const [client, setClient] = useState<TradingApiClient | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  
  // Initialize client
  useEffect(() => {
    const apiClient = new TradingApiClient(baseUrl);
    setClient(apiClient);
  }, [baseUrl]);
  
  // Authentication
  const login = async (token: string) => {
    if (client) {
      client.setAuthToken(token);
      setIsAuthenticated(true);
    }
  };
  
  const logout = () => {
    if (client) {
      client.clearAuthToken();
      setIsAuthenticated(false);
    }
  };
  
  // API methods with React state management
  const getSignals = async (symbol: string) => {
    if (!client || !isAuthenticated) {
      throw new Error('Not authenticated');
    }
    return await client.getSignals(symbol);
  };
  
  const placeOrder = async (orderData: ActOnSignalRequest) => {
    if (!client || !isAuthenticated) {
      throw new Error('Not authenticated');
    }
    return await client.actOnSignal(orderData);
  };
  
  return {
    client,
    isAuthenticated,
    login,
    logout,
    getSignals,
    placeOrder
  };
}
*/

// ============================================================================
// React Component Example (TypeScript)
// ============================================================================

/*
// Save this as: components/TradingDashboard.tsx
// NOTE: Install React types: npm install @types/react

import React, { useState } from 'react';
import { useTradingApi } from '../hooks/useTrading';
import { isApiError } from '../api/api';

interface Signal {
  id: string;
  symbol: string;
  signal_type: 'buy' | 'sell';
  confidence: number;
  strength: number;
  strategy?: string;
}

function TradingDashboard() {
  const { isAuthenticated, login, getSignals } = useTradingApi('http://localhost:8000');
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Load signals
  const loadSignals = async (symbol: string) => {
    if (!isAuthenticated) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const response = await getSignals(symbol);
      setSignals(response.signals);
    } catch (err) {
      setError(isApiError(err) ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };
  
  // Handle authentication
  const handleLogin = async () => {
    // Get token from your auth provider
    const token = await getAuthTokenFromProvider();
    await login(token);
    await loadSignals('AAPL');
  };
  
  const handleActOnSignal = async (signal: Signal) => {
    // Implementation for acting on signal
    console.log('Acting on signal:', signal.id);
  };
  
  if (!isAuthenticated) {
    return React.createElement('button', { onClick: handleLogin }, 'Login');
  }
  
  return React.createElement('div', null,
    React.createElement('h1', null, 'Trading Dashboard'),
    
    loading && React.createElement('div', null, 'Loading signals...'),
    
    error && React.createElement('div', { className: 'error' }, `Error: ${error}`),
    
    React.createElement('div', null,
      signals.map(signal =>
        React.createElement('div', { key: signal.id, className: 'signal-card' },
          React.createElement('h3', null, `${signal.symbol} - ${signal.signal_type}`),
          React.createElement('p', null, `Confidence: ${(signal.confidence * 100).toFixed(1)}%`),
          React.createElement('p', null, `Strength: ${(signal.strength * 100).toFixed(1)}%`),
          signal.strategy && React.createElement('p', null, `Strategy: ${signal.strategy}`),
          React.createElement('button', 
            { onClick: () => handleActOnSignal(signal) },
            'Act on Signal'
          )
        )
      )
    )
  );
}

export default TradingDashboard;
*/

// ============================================================================
// Vue 3 Composition API Example (commented for TypeScript compatibility)
// ============================================================================

/*
// This would typically be in a separate file: composables/useTrading.ts
// NOTE: Install Vue 3 types: npm install @vue/runtime-core

import { ref, onMounted, readonly } from 'vue';
import { TradingApiClient, isApiError } from './api';

function useTradingApiVue(baseUrl: string) {
  const client = ref<TradingApiClient | null>(null);
  const isAuthenticated = ref(false);
  const signals = ref([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  
  onMounted(() => {
    client.value = new TradingApiClient(baseUrl);
  });
  
  const login = async (token: string) => {
    if (client.value) {
      client.value.setAuthToken(token);
      isAuthenticated.value = true;
    }
  };
  
  const fetchSignals = async (symbol: string) => {
    if (!client.value || !isAuthenticated.value) return;
    
    loading.value = true;
    error.value = null;
    
    try {
      const response = await client.value.getSignals(symbol);
      signals.value = response.signals;
    } catch (err) {
      error.value = isApiError(err) ? err.message : 'Unknown error';
    } finally {
      loading.value = false;
    }
  };
  
  return {
    client: readonly(client),
    isAuthenticated: readonly(isAuthenticated),
    signals: readonly(signals),
    loading: readonly(loading),
    error: readonly(error),
    login,
    fetchSignals
  };
}

export { useTradingApiVue };
*/

// ============================================================================
// Error Handling Best Practices
// ============================================================================

class TradingApiService {
  private client: TradingApiClient;
  
  constructor(baseUrl: string) {
    this.client = new TradingApiClient(baseUrl, {
      timeout: 30000, // 30 second timeout
      defaultHeaders: {
        'X-Client-Version': '1.0.0'
      }
    });
  }
  
  async withErrorHandling<T>(operation: () => Promise<T>): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      if (isApiError(error)) {
        // Handle API errors
        switch (error.status) {
          case 401:
            // Authentication error - redirect to login
            this.handleAuthError();
            throw new Error('Please log in again');
            
          case 403:
            // Permission error
            throw new Error('You do not have permission for this action');
            
          case 429:
            // Rate limiting
            throw new Error('Too many requests. Please wait a moment.');
            
          case 500:
            // Server error
            throw new Error('Server error. Please try again later.');
            
          default:
            throw new Error(error.message);
        }
      } else if (error instanceof Error) {
        // Network or other errors
        if (error.message.includes('timeout')) {
          throw new Error('Request timed out. Please check your connection.');
        }
        throw error;
      } else {
        throw new Error('An unknown error occurred');
      }
    }
  }
  
  private handleAuthError() {
    // Clear stored token
    this.client.clearAuthToken();
    // Redirect to login page or emit auth error event
    window.location.href = '/login';
  }
  
  // Wrapped API methods with error handling
  async getSignals(symbol: string) {
    return this.withErrorHandling(() => this.client.getSignals(symbol));
  }
  
  async placeOrder(orderData: ActOnSignalRequest) {
    return this.withErrorHandling(() => this.client.actOnSignal(orderData));
  }
}

// ============================================================================
// Testing Utilities (commented for TypeScript compatibility)
// ============================================================================

/*
// Mock client for testing - uncomment and adjust types as needed
export class MockTradingApiClient {
  private mockData = {
    signals: [
      {
        id: 'signal-1',
        symbol: 'AAPL',
        signal_type: 'buy' as const,
        strength: 0.85,
        confidence: 0.72,
        model_name: 'test-model',
        direction: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ],
    orders: [
      {
        id: 'order-1',
        symbol: 'AAPL',
        side: 'buy' as const,
        qty: 10,
        status: 'filled' as const,
        client_idempotency_key: 'test-key',
        order_type: 'market' as const,
        tif: 'gtc' as const,
        created_at: new Date().toISOString(),
        submitted_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      }
    ]
  };
  
  async getSignals(symbol: string, options?: any) {
    return {
      signals: this.mockData.signals.filter(s => s.symbol === symbol),
      total: 1
    };
  }
  
  async actOnSignal(request: ActOnSignalRequest) {
    return {
      order: { ...this.mockData.orders[0], symbol: request.symbol }
    };
  }
  
  setAuthToken(token: string) {
    // Mock implementation
  }
}

// Test helper
export function createMockClient() {
  return new MockTradingApiClient();
}
*/

// ============================================================================
// Export Examples
// ============================================================================

export {
  basicUsageExample,
  TradingApiService
};