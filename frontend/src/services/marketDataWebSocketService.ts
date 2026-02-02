/**
 * Market Data WebSocket Service
 * 
 * Singleton service for managing WebSocket connection to market data backend
 * Handles connection lifecycle, message routing, and automatic reconnection
 * 
 * Based on backend protocol: backend/api/routes/market_data.py
 */

import { ConnectionState } from '../types/marketData';
import type {
  MarketDataMessage,
  ClientAction,
  Quote,
  Trade,
  Bar,
  ErrorMessage,
  QuoteCallback,
  TradeCallback,
  BarCallback,
  ErrorCallback,
  ConnectionCallback,
  MarketDataConfig
} from '../types/marketData';

/**
 * Default configuration
 */
const DEFAULT_CONFIG: Required<MarketDataConfig> = {
  wsUrl: `ws://${window.location.hostname}:8000/api/v1/market-data/ws`, // Fixed: removed duplicate /market-data
  reconnectInterval: 1000, // Start at 1 second
  maxReconnectAttempts: 10,
  heartbeatInterval: 30000 // 30 seconds
};

/**
 * Market Data WebSocket Service
 * Singleton pattern - use getInstance()
 */
export class MarketDataWebSocketService {
  private static instance: MarketDataWebSocketService | null = null;

  private ws: WebSocket | null = null;
  private config: Required<MarketDataConfig>;
  private connectionState: ConnectionState = ConnectionState.DISCONNECTED;
  
  // Client ID assigned by server
  private clientId: string | null = null;
  
  // Reconnection state
  private reconnectAttempts = 0;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private currentReconnectDelay = 1000;
  
  // Heartbeat
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private lastPingTime: number | null = null;
  
  // Subscriptions tracking
  private subscriptions = new Set<string>();
  
  // Callbacks
  private quoteCallbacks = new Map<string, Set<QuoteCallback>>();
  private tradeCallbacks = new Map<string, Set<TradeCallback>>();
  private barCallbacks = new Map<string, Set<BarCallback>>();
  private errorCallbacks = new Set<ErrorCallback>();
  private connectionCallbacks = new Set<ConnectionCallback>();
  
  // Message queue for offline messages
  private messageQueue: ClientAction[] = [];

  /**
   * Private constructor - use getInstance()
   */
  private constructor(config?: Partial<MarketDataConfig>) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  /**
   * Get singleton instance
   */
  public static getInstance(config?: Partial<MarketDataConfig>): MarketDataWebSocketService {
    if (!MarketDataWebSocketService.instance) {
      MarketDataWebSocketService.instance = new MarketDataWebSocketService(config);
    }
    return MarketDataWebSocketService.instance;
  }

  /**
   * Connect to WebSocket server
   */
  public async connect(token: string): Promise<void> {
    if (this.connectionState === ConnectionState.CONNECTED || 
        this.connectionState === ConnectionState.CONNECTING) {
      console.log('[MarketData] Already connected or connecting');
      return;
    }

    this.setConnectionState(ConnectionState.CONNECTING);

    try {
      const wsUrl = `${this.config.wsUrl}?token=${encodeURIComponent(token)}`;
      console.log('[MarketData] Connecting to:', wsUrl.replace(token, '***'));

      this.ws = new WebSocket(wsUrl);
      
      this.ws.onopen = this.handleOpen.bind(this);
      this.ws.onmessage = this.handleMessage.bind(this);
      this.ws.onerror = this.handleError.bind(this);
      this.ws.onclose = this.handleClose.bind(this);

      // Wait for connection with timeout
      await this.waitForConnection(5000);
    } catch (error) {
      console.error('[MarketData] Connection failed:', error);
      this.setConnectionState(ConnectionState.FAILED);
      this.scheduleReconnect(token);
      throw error;
    }
  }

  /**
   * Wait for WebSocket to connect
   */
  private waitForConnection(timeout: number): Promise<void> {
    return new Promise((resolve, reject) => {
      const timeoutId = setTimeout(() => {
        reject(new Error('Connection timeout'));
      }, timeout);

      const checkConnection = () => {
        if (this.connectionState === ConnectionState.CONNECTED) {
          clearTimeout(timeoutId);
          resolve();
        } else if (this.connectionState === ConnectionState.FAILED) {
          clearTimeout(timeoutId);
          reject(new Error('Connection failed'));
        } else {
          setTimeout(checkConnection, 100);
        }
      };

      checkConnection();
    });
  }

  /**
   * Disconnect from WebSocket server
   */
  public disconnect(): void {
    console.log('[MarketData] Disconnecting...');
    
    // Clear reconnection timer
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    
    // Clear heartbeat
    this.stopHeartbeat();
    
    // Close WebSocket
    if (this.ws) {
      this.ws.onclose = null; // Prevent reconnection
      this.ws.close();
      this.ws = null;
    }
    
    this.setConnectionState(ConnectionState.DISCONNECTED);
    this.clientId = null;
    this.reconnectAttempts = 0;
  }

  /**
   * Subscribe to symbol quotes
   */
  public subscribe(symbol: string, callback: QuoteCallback): void {
    const normalizedSymbol = symbol.toUpperCase();
    
    // Add callback
    if (!this.quoteCallbacks.has(normalizedSymbol)) {
      this.quoteCallbacks.set(normalizedSymbol, new Set());
    }
    this.quoteCallbacks.get(normalizedSymbol)!.add(callback);
    
    // Send subscribe message if not already subscribed
    if (!this.subscriptions.has(normalizedSymbol)) {
      this.subscriptions.add(normalizedSymbol);
      this.send({ action: 'subscribe', symbol: normalizedSymbol });
      console.log('[MarketData] Subscribed to:', normalizedSymbol);
    }
  }

  /**
   * Unsubscribe from symbol quotes
   */
  public unsubscribe(symbol: string, callback?: QuoteCallback): void {
    const normalizedSymbol = symbol.toUpperCase();
    
    if (callback) {
      // Remove specific callback
      const callbacks = this.quoteCallbacks.get(normalizedSymbol);
      if (callbacks) {
        callbacks.delete(callback);
        if (callbacks.size === 0) {
          this.quoteCallbacks.delete(normalizedSymbol);
        }
      }
    } else {
      // Remove all callbacks for this symbol
      this.quoteCallbacks.delete(normalizedSymbol);
    }
    
    // If no more callbacks, unsubscribe from server
    if (!this.quoteCallbacks.has(normalizedSymbol) && this.subscriptions.has(normalizedSymbol)) {
      this.subscriptions.delete(normalizedSymbol);
      this.send({ action: 'unsubscribe', symbol: normalizedSymbol });
      console.log('[MarketData] Unsubscribed from:', normalizedSymbol);
    }
  }

  /**
   * Subscribe to trades
   */
  public subscribeToTrades(symbol: string, callback: TradeCallback): void {
    const normalizedSymbol = symbol.toUpperCase();
    
    if (!this.tradeCallbacks.has(normalizedSymbol)) {
      this.tradeCallbacks.set(normalizedSymbol, new Set());
    }
    this.tradeCallbacks.get(normalizedSymbol)!.add(callback);
  }

  /**
   * Subscribe to bars
   */
  public subscribeToBars(symbol: string, callback: BarCallback): void {
    const normalizedSymbol = symbol.toUpperCase();
    
    if (!this.barCallbacks.has(normalizedSymbol)) {
      this.barCallbacks.set(normalizedSymbol, new Set());
    }
    this.barCallbacks.get(normalizedSymbol)!.add(callback);
  }

  /**
   * Add error callback
   */
  public onError(callback: ErrorCallback): () => void {
    this.errorCallbacks.add(callback);
    
    // Return cleanup function
    return () => {
      this.errorCallbacks.delete(callback);
    };
  }

  /**
   * Add connection state callback
   */
  public onConnectionStateChange(callback: ConnectionCallback): () => void {
    this.connectionCallbacks.add(callback);
    
    // Call immediately with current state
    callback(this.connectionState);
    
    // Return cleanup function
    return () => {
      this.connectionCallbacks.delete(callback);
    };
  }

  /**
   * Get current connection state
   */
  public getConnectionState(): ConnectionState {
    return this.connectionState;
  }

  /**
   * Get current subscriptions
   */
  public getSubscriptions(): string[] {
    return Array.from(this.subscriptions);
  }

  /**
   * Send message to server
   */
  private send(message: ClientAction): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      // Queue message for later
      this.messageQueue.push(message);
      console.log('[MarketData] Message queued (not connected):', message);
    }
  }

  /**
   * Handle WebSocket open
   */
  private handleOpen(): void {
    console.log('[MarketData] Connected');
    this.setConnectionState(ConnectionState.CONNECTED);
    this.reconnectAttempts = 0;
    this.currentReconnectDelay = this.config.reconnectInterval;
    
    // Start heartbeat
    this.startHeartbeat();
    
    // Send queued messages
    this.flushMessageQueue();
  }

  /**
   * Handle WebSocket message
   */
  private handleMessage(event: MessageEvent): void {
    try {
      const message: MarketDataMessage = JSON.parse(event.data);
      
      // Route message based on type
      switch (message.type) {
        case 'connected':
          this.clientId = message.client_id;
          console.log('[MarketData] Client ID:', this.clientId);
          break;
          
        case 'quote':
          this.handleQuote(message);
          break;
          
        case 'trade':
          this.handleTrade(message);
          break;
          
        case 'bar':
          this.handleBar(message);
          break;
          
        case 'subscribed':
          console.log('[MarketData] Confirmed subscription:', message.symbol);
          break;
          
        case 'unsubscribed':
          console.log('[MarketData] Confirmed unsubscription:', message.symbol);
          break;
          
        case 'ping':
          // Respond with pong
          this.send({ action: 'pong' });
          this.lastPingTime = Date.now();
          break;
          
        case 'error':
          this.handleServerError(message);
          break;
          
        case 'subscriptions':
          console.log('[MarketData] Current subscriptions:', message.subscriptions);
          break;
          
        default:
          console.warn('[MarketData] Unknown message type:', message);
      }
    } catch (error) {
      console.error('[MarketData] Failed to parse message:', error);
    }
  }

  /**
   * Handle quote update
   */
  private handleQuote(message: { symbol: string; data: Quote }): void {
    const callbacks = this.quoteCallbacks.get(message.symbol);
    if (callbacks) {
      callbacks.forEach(callback => {
        try {
          callback(message.data);
        } catch (error) {
          console.error('[MarketData] Quote callback error:', error);
        }
      });
    }
  }

  /**
   * Handle trade update
   */
  private handleTrade(message: { symbol: string; data: Trade }): void {
    const callbacks = this.tradeCallbacks.get(message.symbol);
    if (callbacks) {
      callbacks.forEach(callback => {
        try {
          callback(message.data);
        } catch (error) {
          console.error('[MarketData] Trade callback error:', error);
        }
      });
    }
  }

  /**
   * Handle bar update
   */
  private handleBar(message: { symbol: string; data: Bar }): void {
    const callbacks = this.barCallbacks.get(message.symbol);
    if (callbacks) {
      callbacks.forEach(callback => {
        try {
          callback(message.data);
        } catch (error) {
          console.error('[MarketData] Bar callback error:', error);
        }
      });
    }
  }

  /**
   * Handle server error
   */
  private handleServerError(message: ErrorMessage): void {
    console.error('[MarketData] Server error:', message.message, message.code);
    
    this.errorCallbacks.forEach(callback => {
      try {
        callback(message);
      } catch (error) {
        console.error('[MarketData] Error callback error:', error);
      }
    });
  }

  /**
   * Handle WebSocket error
   */
  private handleError(event: Event): void {
    console.error('[MarketData] WebSocket error:', event);
  }

  /**
   * Handle WebSocket close
   */
  private handleClose(event: CloseEvent): void {
    console.log('[MarketData] Disconnected:', event.code, event.reason);
    
    this.stopHeartbeat();
    
    // Attempt reconnection if not a clean close
    if (event.code !== 1000 && this.connectionState !== ConnectionState.DISCONNECTED) {
      this.setConnectionState(ConnectionState.RECONNECTING);
      
      // Get token from URL or storage
      const token = this.getStoredToken();
      if (token) {
        this.scheduleReconnect(token);
      } else {
        console.error('[MarketData] Cannot reconnect: no token available');
        this.setConnectionState(ConnectionState.FAILED);
      }
    } else {
      this.setConnectionState(ConnectionState.DISCONNECTED);
    }
  }

  /**
   * Schedule reconnection attempt
   */
  private scheduleReconnect(token: string): void {
    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      console.error('[MarketData] Max reconnection attempts reached');
      this.setConnectionState(ConnectionState.FAILED);
      return;
    }

    this.reconnectAttempts++;
    
    // Exponential backoff with jitter
    const jitter = Math.random() * 1000;
    const delay = Math.min(
      this.currentReconnectDelay + jitter,
      30000 // Max 30 seconds
    );
    
    console.log(
      `[MarketData] Reconnecting in ${(delay / 1000).toFixed(1)}s (attempt ${this.reconnectAttempts}/${this.config.maxReconnectAttempts})`
    );
    
    this.reconnectTimeout = setTimeout(() => {
      this.connect(token).catch(error => {
        console.error('[MarketData] Reconnection failed:', error);
      });
    }, delay);
    
    // Increase delay for next attempt
    this.currentReconnectDelay *= 2;
  }

  /**
   * Start heartbeat
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();
    
    this.heartbeatInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        // Check if we received a ping recently
        if (this.lastPingTime && Date.now() - this.lastPingTime > 60000) {
          console.warn('[MarketData] No ping received in 60s, reconnecting...');
          this.ws.close();
        }
      }
    }, this.config.heartbeatInterval);
  }

  /**
   * Stop heartbeat
   */
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Set connection state and notify callbacks
   */
  private setConnectionState(state: ConnectionState): void {
    if (this.connectionState !== state) {
      this.connectionState = state;
      console.log('[MarketData] State changed:', state);
      
      this.connectionCallbacks.forEach(callback => {
        try {
          callback(state);
        } catch (error) {
          console.error('[MarketData] Connection callback error:', error);
        }
      });
    }
  }

  /**
   * Flush queued messages
   */
  private flushMessageQueue(): void {
    if (this.messageQueue.length > 0) {
      console.log('[MarketData] Flushing', this.messageQueue.length, 'queued messages');
      
      this.messageQueue.forEach(message => {
        this.send(message);
      });
      
      this.messageQueue = [];
    }
  }

  /**
   * Get stored auth token from centralized auth store
   */
  private getStoredToken(): string | null {
    // Use the centralized auth store instead of localStorage
    // This ensures consistency with the rest of the application
    try {
      // Dynamic import to avoid circular dependencies
      const { useAuthStore } = require('@/store/authStore');
      return useAuthStore.getState().accessToken;
    } catch {
      // Fallback to localStorage if auth store not available
      return localStorage.getItem('auth_token');
    }
  }
}

/**
 * Export singleton instance getter
 */
export const getMarketDataService = (config?: Partial<MarketDataConfig>) => {
  return MarketDataWebSocketService.getInstance(config);
};
