/**
 * WebSocket Manager
 * Manages WebSocket connection with auto-reconnect, heartbeat, and subscriptions
 */

import { io, Socket } from 'socket.io-client';
import { logger } from '@/utils/logger';
import type {
  WebSocketMessage,
  WebSocketTopic,
  SubscribeMessage,
  UnsubscribeMessage,
  HeartbeatMessage,
} from '@/types/websocket';

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'http://localhost:8000';

type MessageHandler = (data: unknown) => void;
type ConnectionStateHandler = (connected: boolean) => void;
type ConnectionQuality = 'excellent' | 'good' | 'poor' | 'disconnected';

interface ConnectionStats {
  connected: boolean;
  quality: ConnectionQuality;
  latency: number;
  reconnectCount: number;
  lastHeartbeat: number;
  uptime: number;
}

class WebSocketManager {
  private socket: Socket | null = null;
  private subscriptions: Map<string, Set<MessageHandler>> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private heartbeatInterval?: ReturnType<typeof setInterval>;
  private heartbeatIntervalDuration = 25000; // 25 seconds
  private connectionStateHandlers: Set<ConnectionStateHandler> = new Set();
  
  // Enhanced reconnection with exponential backoff
  private baseReconnectDelay = 1000; // 1 second
  private maxReconnectDelay = 60000; // 60 seconds
  
  // Connection quality monitoring
  private lastHeartbeatTime = 0;
  private lastPongTime = 0;
  private connectionStartTime = 0;
  private totalReconnects = 0;
  private latencyHistory: number[] = [];
  private readonly maxLatencyHistory = 10;

  /**
   * Connect to WebSocket server with exponential backoff
   */
  connect(token: string) {
    if (this.socket?.connected) {
      logger.debug('[WebSocket] Already connected');
      return;
    }

    // Calculate reconnect delay with exponential backoff
    const reconnectDelay = Math.min(
      this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts),
      this.maxReconnectDelay
    );

    logger.debug('[WebSocket] Connecting...');

    this.socket = io(WS_BASE_URL, {
      auth: { token },
      transports: ['websocket'],
      reconnection: true,
      reconnectionDelay: reconnectDelay,
      reconnectionDelayMax: this.maxReconnectDelay,
      reconnectionAttempts: this.maxReconnectAttempts,
    });

    this.setupEventHandlers();
  }

  /**
   * Setup Socket.IO event handlers
   */
  private setupEventHandlers() {
    if (!this.socket) return;

    this.socket.on('connect', () => {
      logger.debug('[WebSocket] Connected');
      this.reconnectAttempts = 0;
      this.connectionStartTime = Date.now();
      if (this.totalReconnects > 0) {
        logger.debug(`[WebSocket] Reconnected (total reconnects: ${this.totalReconnects})`);
      }
      this.startHeartbeat();
      this.resubscribe();
      this.notifyConnectionState(true);
    });

    this.socket.on('disconnect', (reason) => {
      logger.debug('[WebSocket] Disconnected:', reason);
      this.stopHeartbeat();
      this.notifyConnectionState(false);
    });

    this.socket.on('connect_error', (error) => {
      // Silently handle "Connection rejected by server" errors (unauthenticated)
      const errorMsg = error?.message || String(error);
      if (!errorMsg.includes('rejected by server')) {
        logger.error('[WebSocket] Connection error:', error);
      }
      this.reconnectAttempts++;
      
      if (this.reconnectAttempts >= this.maxReconnectAttempts) {
        // Silently fail if rejected by server (no auth)
        if (!errorMsg.includes('rejected by server')) {
          logger.error('[WebSocket] Max reconnection attempts reached');
        }
        this.disconnect();
      }
    });

    this.socket.on('message', (message: WebSocketMessage) => {
      this.handleMessage(message);
    });

    // Handle specific event types
    this.socket.on('order_update', (data) => {
      this.handleMessage({ type: 'order_update', topic: 'orders', data, timestamp: Date.now() });
    });

    this.socket.on('position_update', (data) => {
      this.handleMessage({ type: 'position_update', topic: 'positions', data, timestamp: Date.now() });
    });

    this.socket.on('portfolio_update', (data) => {
      this.handleMessage({ type: 'portfolio_update', topic: 'portfolio', data, timestamp: Date.now() });
    });

    this.socket.on('market_data', (data) => {
      this.handleMessage({ type: 'market_data', topic: 'market_data', data, timestamp: Date.now() });
    });

    this.socket.on('signal', (data) => {
      this.handleMessage({ type: 'signal', topic: 'signals', data, timestamp: Date.now() });
    });

    this.socket.on('strategy_update', (data) => {
      this.handleMessage({ type: 'strategy_update', topic: 'strategies', data, timestamp: Date.now() });
    });

    this.socket.on('alert', (data) => {
      this.handleMessage({ type: 'alert', topic: 'alerts', data, timestamp: Date.now() });
    });

    this.socket.on('risk_update', (data) => {
      this.handleMessage({ type: 'risk_update', topic: 'risk', data, timestamp: Date.now() });
    });

    this.socket.on('error', (error) => {
      logger.error('[WebSocket] Error:', error);
    });
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect() {
    logger.debug('[WebSocket] Disconnecting...');
    this.stopHeartbeat();
    this.socket?.disconnect();
    this.socket = null;
    this.subscriptions.clear();
    this.notifyConnectionState(false);
  }

  /**
   * Subscribe to a topic
   */
  subscribe(topic: WebSocketTopic, handler: MessageHandler, symbols?: string[]) {
    const key = topic;
    
    // Store handler
    if (!this.subscriptions.has(key)) {
      this.subscriptions.set(key, new Set());
    }
    this.subscriptions.get(key)!.add(handler);

    // Send subscribe message if connected
    if (this.socket?.connected) {
      const message: SubscribeMessage = {
        type: 'subscribe',
        topic,
        symbols,
        timestamp: Date.now(),
      };
      this.socket.emit('subscribe', message);
      logger.debug('[WebSocket] Subscribed to:', topic);
    }
  }

  /**
   * Unsubscribe from a topic
   */
  unsubscribe(topic: WebSocketTopic, handler: MessageHandler) {
    const key = topic;
    const handlers = this.subscriptions.get(key);
    
    if (handlers) {
      handlers.delete(handler);
      
      // If no more handlers, unsubscribe from server
      if (handlers.size === 0) {
        this.subscriptions.delete(key);
        
        if (this.socket?.connected) {
          const message: UnsubscribeMessage = {
            type: 'unsubscribe',
            topic,
            timestamp: Date.now(),
          };
          this.socket.emit('unsubscribe', message);
          logger.debug('[WebSocket] Unsubscribed from:', topic);
        }
      }
    }
  }

  /**
   * Handle incoming messages
   */
  private handleMessage(message: WebSocketMessage) {
    const { topic, data } = message;
    
    if (topic) {
      const handlers = this.subscriptions.get(topic);
      if (handlers) {
        handlers.forEach((handler) => {
          try {
            handler(data);
          } catch (error) {
            logger.error('[WebSocket] Handler error:', error);
          }
        });
      }
    }
  }

  /**
   * Resubscribe to all topics after reconnection
   */
  private resubscribe() {
    if (!this.socket?.connected) return;

    this.subscriptions.forEach((_, topic) => {
      const message: SubscribeMessage = {
        type: 'subscribe',
        topic: topic as WebSocketTopic,
        timestamp: Date.now(),
      };
      this.socket!.emit('subscribe', message);
      logger.debug('[WebSocket] Resubscribed to:', topic);
    });
  }

  /**
   * Start heartbeat to keep connection alive and measure latency
   */
  private startHeartbeat() {
    this.stopHeartbeat();
    
    this.heartbeatInterval = setInterval(() => {
      if (this.socket?.connected) {
        this.lastHeartbeatTime = Date.now();
        const message: HeartbeatMessage = {
          type: 'heartbeat',
          timestamp: this.lastHeartbeatTime,
        };
        this.socket.emit('heartbeat', message);
      }
    }, this.heartbeatIntervalDuration);
    
    // Listen for pong to measure latency
    this.socket?.on('pong', () => {
      const now = Date.now();
      this.lastPongTime = now;
      if (this.lastHeartbeatTime > 0) {
        const latency = now - this.lastHeartbeatTime;
        this.latencyHistory.push(latency);
        if (this.latencyHistory.length > this.maxLatencyHistory) {
          this.latencyHistory.shift();
        }
      }
    });
  }

  /**
   * Stop heartbeat
   */
  private stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = undefined;
    }
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.socket?.connected ?? false;
  }

  /**
   * Get connection statistics for monitoring
   */
  getConnectionStats(): ConnectionStats {
    const connected = this.socket?.connected ?? false;
    const avgLatency = this.latencyHistory.length > 0
      ? this.latencyHistory.reduce((a, b) => a + b, 0) / this.latencyHistory.length
      : 0;
    
    let quality: ConnectionQuality = 'disconnected';
    if (connected) {
      if (avgLatency < 100) quality = 'excellent';
      else if (avgLatency < 300) quality = 'good';
      else quality = 'poor';
    }
    
    return {
      connected,
      quality,
      latency: Math.round(avgLatency),
      reconnectCount: this.totalReconnects,
      lastHeartbeat: this.lastPongTime,
      uptime: connected && this.connectionStartTime > 0 
        ? Date.now() - this.connectionStartTime 
        : 0,
    };
  }

  /**
   * Register connection state handler
   */
  onConnectionChange(handler: ConnectionStateHandler) {
    this.connectionStateHandlers.add(handler);
    
    // Return cleanup function
    return () => {
      this.connectionStateHandlers.delete(handler);
    };
  }

  /**
   * Notify all connection state handlers
   */
  private notifyConnectionState(connected: boolean) {
    if (!connected) {
      this.totalReconnects++;
    }
    this.connectionStateHandlers.forEach((handler) => {
      try {
        handler(connected);
      } catch (error) {
        logger.error('[WebSocket] Connection state handler error:', error);
      }
    });
  }
}

// Export singleton instance
export const websocketManager = new WebSocketManager();

// Export types
export type { ConnectionStats, ConnectionQuality };
