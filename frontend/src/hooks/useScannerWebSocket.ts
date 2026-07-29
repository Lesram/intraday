/**
 * Scanner WebSocket Hook
 * 
 * Manages real-time market scanning via WebSocket connection.
 * 
 * Features:
 * - Auto-connect/disconnect WebSocket
 * - Start/stop continuous scanning
 * - Update filters dynamically
 * - Receive live scan results
 * - Configurable scan interval
 * - Connection status monitoring
 * 
 * Phase 7 - Enhanced Features
 * Created: October 16, 2025
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { message } from 'antd';

// ============================================================================
// TYPES
// ============================================================================

export interface ScanFilters {
  // Price filters
  price_min?: number;
  price_max?: number;
  
  // Volume filters
  volume_min?: number;
  volume_spike?: number;
  
  // RSI filters
  rsi_min?: number;
  rsi_max?: number;
  
  // MACD filters
  macd_signal?: 'any' | 'bullish' | 'bearish';
  
  // Moving Average filters
  ma_crossover?: 'none' | 'golden_cross' | 'death_cross';
  above_sma_50?: boolean;
  above_sma_200?: boolean;
  
  // Gap filters
  gap_up?: boolean;
  gap_down?: boolean;
  gap_percentage?: number;
  
  // ATR filter
  atr_multiplier?: number;
  
  // Results
  limit?: number;
}

export interface ScanResult {
  symbol: string;
  price: number;
  change: number;
  change_percent: number;
  volume: number;
  avg_volume?: number;
  rsi?: number;
  macd?: number;
  macd_signal?: number;
  sma_50?: number;
  sma_200?: number;
  atr?: number;
  score: number;
  signals: string[];
}

export interface ScanResponse {
  results: ScanResult[];
  total: number;
  scan_time: number;
  filters_applied: number;
  timestamp?: string;
}

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

// ============================================================================
// HOOK
// ============================================================================

export const useScannerWebSocket = (autoConnect: boolean = false) => {
  // State
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
  const [isScanning, setIsScanning] = useState(false);
  const [lastResults, setLastResults] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  // Refs
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  
  // Get WebSocket URL.
  // V4 O-6 (2026-05-02): hardcoding ":8000" breaks behind a reverse
  // proxy (the FE is served at the same origin as the API). Allow
  // VITE_WS_BASE_URL to fully override; otherwise derive from the
  // current page origin (no explicit port — the proxy/gateway routes
  // /api/v1/scanner/ws on the same scheme/host).
  const getWebSocketUrl = useCallback(() => {
    const { useAuthStore } = require('@/store/authStore');
    const token = useAuthStore.getState().accessToken;
    const tokenQS = token ? `?token=${token}` : '';

    const override = (import.meta as any).env?.VITE_WS_BASE_URL;
    if (override) {
      return `${override.replace(/\/$/, '')}/api/v1/scanner/ws${tokenQS}`;
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/api/v1/scanner/ws${tokenQS}`;
  }, []);
  
  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      console.log('Scanner WebSocket already connected');
      return;
    }
    
    try {
      setConnectionStatus('connecting');
      setError(null);
      
      const ws = new WebSocket(getWebSocketUrl());
      
      ws.onopen = () => {
        console.log('Scanner WebSocket connected');
        setConnectionStatus('connected');
        setError(null);
        
        // Start ping interval
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: 'ping' }));
          }
        }, 30000); // Ping every 30 seconds
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.status) {
            // Status message
            console.log('Scanner status:', data.status, data.message);
            
            if (data.status === 'started') {
              setIsScanning(true);
              message.success('Scanner started');
            } else if (data.status === 'stopped') {
              setIsScanning(false);
              message.info('Scanner stopped');
            } else if (data.status === 'updated') {
              message.success('Filters updated');
            }
          } else if (data.results) {
            // Scan results
            setLastResults({
              ...data,
              timestamp: new Date().toISOString(),
            });
            setError(null);
          }
        } catch (err) {
          console.error('Failed to parse scanner message:', err);
        }
      };
      
      ws.onerror = (event) => {
        console.error('Scanner WebSocket error:', event);
        setConnectionStatus('error');
        setError('WebSocket connection error');
        message.error('Scanner connection error');
      };
      
      ws.onclose = (event) => {
        console.log('Scanner WebSocket closed:', event.code, event.reason);
        setConnectionStatus('disconnected');
        setIsScanning(false);
        
        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }
        
        // Auto-reconnect if not a clean close
        if (event.code !== 1000 && autoConnect) {
          reconnectTimeoutRef.current = setTimeout(() => {
            console.log('Attempting to reconnect scanner WebSocket...');
            connect();
          }, 5000); // Retry after 5 seconds
        }
      };
      
      wsRef.current = ws;
    } catch (err) {
      console.error('Failed to connect scanner WebSocket:', err);
      setConnectionStatus('error');
      setError(`Connection failed: ${err}`);
    }
  }, [getWebSocketUrl, autoConnect]);
  
  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = null;
    }
    
    if (wsRef.current) {
      wsRef.current.close(1000, 'User disconnected');
      wsRef.current = null;
    }
    
    setConnectionStatus('disconnected');
    setIsScanning(false);
  }, []);
  
  // Start scanning
  const startScanning = useCallback((filters: ScanFilters, interval: number = 10) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      message.error('Scanner not connected');
      return;
    }
    
    try {
      wsRef.current.send(JSON.stringify({
        action: 'start',
        filters,
        interval,
      }));
      
      console.log('Start scanning with filters:', filters, 'interval:', interval);
    } catch (err) {
      console.error('Failed to start scanning:', err);
      message.error('Failed to start scanning');
    }
  }, []);
  
  // Stop scanning
  const stopScanning = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      return;
    }
    
    try {
      wsRef.current.send(JSON.stringify({
        action: 'stop',
      }));
      
      console.log('Stop scanning');
      setIsScanning(false);
    } catch (err) {
      console.error('Failed to stop scanning:', err);
      message.error('Failed to stop scanning');
    }
  }, []);
  
  // Update filters
  const updateFilters = useCallback((filters: ScanFilters, interval: number = 10) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      message.error('Scanner not connected');
      return;
    }
    
    try {
      wsRef.current.send(JSON.stringify({
        action: 'update_filters',
        filters,
        interval,
      }));
      
      console.log('Update filters:', filters, 'interval:', interval);
    } catch (err) {
      console.error('Failed to update filters:', err);
      message.error('Failed to update filters');
    }
  }, []);
  
  // Auto-connect on mount if enabled
  useEffect(() => {
    if (autoConnect) {
      connect();
    }
    
    // Cleanup on unmount
    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);
  
  return {
    // State
    connectionStatus,
    isScanning,
    lastResults,
    error,
    isConnected: connectionStatus === 'connected',
    
    // Actions
    connect,
    disconnect,
    startScanning,
    stopScanning,
    updateFilters,
  };
};

export default useScannerWebSocket;
