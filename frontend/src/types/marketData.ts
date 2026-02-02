/**
 * Market Data Types
 * 
 * TypeScript type definitions for real-time market data
 * Matches backend WebSocket protocol from backend/services/market_data_service.py
 */

/**
 * Real-time quote data for a symbol
 */
export interface Quote {
  symbol: string;
  bid: number;
  ask: number;
  mid: number;
  spread: number;
  bid_size: number;
  ask_size: number;
  last?: number;
  timestamp: string;
}

/**
 * Trade data
 */
export interface Trade {
  symbol: string;
  price: number;
  size: number;
  exchange: string;
  timestamp: string;
}

/**
 * Bar/Candle data (OHLCV)
 */
export interface Bar {
  symbol: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  timestamp: string;
  timeframe: string;
}

/**
 * WebSocket message types from server
 */
export type MarketDataMessageType = 
  | 'connected'
  | 'quote'
  | 'trade'
  | 'bar'
  | 'subscribed'
  | 'unsubscribed'
  | 'ping'
  | 'error'
  | 'subscriptions';

/**
 * Base message structure
 */
interface BaseMessage {
  type: MarketDataMessageType;
  timestamp?: string;
}

/**
 * Connection established message
 */
export interface ConnectedMessage extends BaseMessage {
  type: 'connected';
  client_id: string;
  message: string;
}

/**
 * Quote update message
 */
export interface QuoteMessage extends BaseMessage {
  type: 'quote';
  symbol: string;
  data: Quote;
}

/**
 * Trade update message
 */
export interface TradeMessage extends BaseMessage {
  type: 'trade';
  symbol: string;
  data: Trade;
}

/**
 * Bar update message
 */
export interface BarMessage extends BaseMessage {
  type: 'bar';
  symbol: string;
  data: Bar;
}

/**
 * Subscription confirmed message
 */
export interface SubscribedMessage extends BaseMessage {
  type: 'subscribed';
  symbol: string;
  message: string;
}

/**
 * Unsubscription confirmed message
 */
export interface UnsubscribedMessage extends BaseMessage {
  type: 'unsubscribed';
  symbol: string;
  message: string;
}

/**
 * Heartbeat ping message
 */
export interface PingMessage extends BaseMessage {
  type: 'ping';
}

/**
 * Error message
 */
export interface ErrorMessage extends BaseMessage {
  type: 'error';
  message: string;
  code: string;
}

/**
 * Subscriptions list message
 */
export interface SubscriptionsMessage extends BaseMessage {
  type: 'subscriptions';
  subscriptions: string[];
}

/**
 * Union type of all possible server messages
 */
export type MarketDataMessage = 
  | ConnectedMessage
  | QuoteMessage
  | TradeMessage
  | BarMessage
  | SubscribedMessage
  | UnsubscribedMessage
  | PingMessage
  | ErrorMessage
  | SubscriptionsMessage;

/**
 * Client action types
 */
export type ClientActionType = 
  | 'subscribe'
  | 'unsubscribe'
  | 'pong'
  | 'get_subscriptions';

/**
 * Base client message structure
 */
interface BaseClientMessage {
  action: ClientActionType;
}

/**
 * Subscribe to symbol
 */
export interface SubscribeAction extends BaseClientMessage {
  action: 'subscribe';
  symbol: string;
}

/**
 * Unsubscribe from symbol
 */
export interface UnsubscribeAction extends BaseClientMessage {
  action: 'unsubscribe';
  symbol: string;
}

/**
 * Heartbeat pong response
 */
export interface PongAction extends BaseClientMessage {
  action: 'pong';
}

/**
 * Request subscriptions list
 */
export interface GetSubscriptionsAction extends BaseClientMessage {
  action: 'get_subscriptions';
}

/**
 * Union type of all possible client actions
 */
export type ClientAction = 
  | SubscribeAction
  | UnsubscribeAction
  | PongAction
  | GetSubscriptionsAction;

/**
 * WebSocket connection state
 */
export enum ConnectionState {
  DISCONNECTED = 'DISCONNECTED',
  CONNECTING = 'CONNECTING',
  CONNECTED = 'CONNECTED',
  RECONNECTING = 'RECONNECTING',
  FAILED = 'FAILED'
}

/**
 * Market data service statistics
 */
export interface MarketDataStats {
  connected_clients: number;
  total_subscriptions: number;
  symbols: string[];
  uptime: number;
}

/**
 * Subscription callback function
 */
export type QuoteCallback = (quote: Quote) => void;
export type TradeCallback = (trade: Trade) => void;
export type BarCallback = (bar: Bar) => void;
export type ErrorCallback = (error: ErrorMessage) => void;
export type ConnectionCallback = (state: ConnectionState) => void;

/**
 * Market data service configuration
 */
export interface MarketDataConfig {
  wsUrl: string;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  heartbeatInterval?: number;
}
