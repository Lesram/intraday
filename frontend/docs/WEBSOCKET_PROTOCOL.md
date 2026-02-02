# WebSocket Protocol Specification
**Created**: October 5, 2025  
**Version**: 1.0  
**Purpose**: Define complete WebSocket message schemas for real-time communication  
**Status**: 🟢 Ready for Implementation

---

## Overview

This document specifies the complete WebSocket protocol for real-time communication between frontend and backend. The WebSocket connection provides low-latency updates for:

- 📦 **Order updates** - Order status changes (filled, cancelled, rejected)
- 💰 **Position updates** - Real-time P&L, position changes
- 📊 **Market data** - Live price ticks for watchlist symbols
- 🚨 **Alerts & notifications** - System events, risk alerts
- 📡 **Strategy events** - Strategy execution, signal generation
- ⚡ **Heartbeat** - Connection health monitoring

---

## Connection

### Endpoint
```
ws://localhost:8000/ws/realtime/{client_id}
wss://api.yourplatform.com/ws/realtime/{client_id}  # Production with SSL
```

### Authentication
**Option 1: Query Parameter** (Recommended for WebSocket)
```
ws://localhost:8000/ws/realtime/{client_id}?token={jwt_access_token}
```

**Option 2: First Message**
```json
{
  "type": "authenticate",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Client ID Generation
```typescript
// Generate unique client ID (UUID v4)
const clientId = crypto.randomUUID();
// Example: "a3f2c1d4-5b6e-7890-1234-567890abcdef"
```

### Connection Lifecycle
```typescript
// 1. Connect
const ws = new WebSocket(`ws://localhost:8000/ws/realtime/${clientId}?token=${token}`);

// 2. On Open - Subscribe to topics
ws.onopen = () => {
  console.log('WebSocket connected');
  // Subscribe to topics (see below)
};

// 3. On Message - Handle incoming messages
ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  handleMessage(message);
};

// 4. On Error
ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

// 5. On Close - Reconnect with exponential backoff
ws.onclose = (event) => {
  console.log('WebSocket closed:', event.code, event.reason);
  reconnect();
};
```

---

## Message Format

All messages use JSON with the following structure:

### Outgoing (Client → Server)
```typescript
interface OutgoingMessage {
  type: 'subscribe' | 'unsubscribe' | 'heartbeat' | 'authenticate';
  topic?: string;        // For subscribe/unsubscribe
  symbols?: string[];    // For market_data subscription
  token?: string;        // For authenticate
  timestamp?: number;    // Client timestamp
}
```

### Incoming (Server → Client)
```typescript
interface IncomingMessage {
  type: 'order_update' | 'position_update' | 'portfolio_update' | 
        'price_update' | 'signal_generated' | 'strategy_update' | 
        'alert' | 'heartbeat_ack' | 'error' | 'subscribed' | 'unsubscribed';
  topic?: string;        // Topic this message belongs to
  data: any;             // Message-specific payload
  timestamp: number;     // Server timestamp (milliseconds since epoch)
  sequence?: number;     // Message sequence number (for ordering)
}
```

---

## Heartbeat Protocol

Maintain connection health with periodic heartbeats.

### Client → Server (Every 25 seconds)
```json
{
  "type": "heartbeat",
  "timestamp": 1728172800000
}
```

### Server → Client (Acknowledgment)
```json
{
  "type": "heartbeat_ack",
  "timestamp": 1728172800123,
  "server_time": 1728172800125
}
```

### Implementation
```typescript
// Client-side heartbeat
let heartbeatInterval: NodeJS.Timeout;

function startHeartbeat(ws: WebSocket) {
  heartbeatInterval = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'heartbeat',
        timestamp: Date.now()
      }));
    }
  }, 25000); // Every 25 seconds
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
  }
}
```

**Server Timeout**: If server doesn't receive heartbeat for 30+ seconds, it closes the connection.

---

## Topic Subscriptions

### Subscribe to Topic

**Request (Client → Server)**:
```json
{
  "type": "subscribe",
  "topic": "orders",
  "timestamp": 1728172800000
}
```

**Response (Server → Client)**:
```json
{
  "type": "subscribed",
  "topic": "orders",
  "timestamp": 1728172800123,
  "message": "Successfully subscribed to orders"
}
```

### Unsubscribe from Topic

**Request**:
```json
{
  "type": "unsubscribe",
  "topic": "orders",
  "timestamp": 1728172800000
}
```

**Response**:
```json
{
  "type": "unsubscribed",
  "topic": "orders",
  "timestamp": 1728172800123,
  "message": "Successfully unsubscribed from orders"
}
```

### Available Topics
- `orders` - Order status changes
- `positions` - Position and P&L updates
- `portfolio` - Portfolio-level metrics
- `market_data` - Real-time price data (requires symbols)
- `signals` - Trading signals from strategies
- `strategies` - Strategy execution events
- `alerts` - System alerts and notifications
- `risk` - Risk metric changes

---

## Message Schemas by Topic

### 1. Orders (`orders` topic)

**order_update** - Order status change
```typescript
interface OrderUpdateMessage {
  type: 'order_update';
  topic: 'orders';
  timestamp: number;
  sequence: number;
  data: {
    order_id: string;           // "ORD-20251005-001"
    client_order_id?: string;   // Optional client-side ID
    symbol: string;             // "AAPL"
    side: 'buy' | 'sell';
    quantity: number;
    filled_quantity: number;
    remaining_quantity: number;
    order_type: 'market' | 'limit' | 'stop' | 'stop_limit';
    price?: number;             // For limit orders
    stop_price?: number;        // For stop orders
    status: 'pending' | 'open' | 'partially_filled' | 'filled' | 
            'cancelled' | 'rejected' | 'expired';
    time_in_force: 'day' | 'gtc' | 'ioc' | 'fok';
    created_at: string;         // ISO 8601
    updated_at: string;         // ISO 8601
    filled_at?: string;         // ISO 8601
    average_fill_price?: number;
    message?: string;           // Rejection reason or info
    strategy_id?: string;       // If from a strategy
  };
}
```

**Example**:
```json
{
  "type": "order_update",
  "topic": "orders",
  "timestamp": 1728172800123,
  "sequence": 42,
  "data": {
    "order_id": "ORD-20251005-001",
    "symbol": "AAPL",
    "side": "buy",
    "quantity": 100,
    "filled_quantity": 100,
    "remaining_quantity": 0,
    "order_type": "market",
    "status": "filled",
    "time_in_force": "day",
    "created_at": "2025-10-05T15:30:00Z",
    "updated_at": "2025-10-05T15:30:02Z",
    "filled_at": "2025-10-05T15:30:02Z",
    "average_fill_price": 178.45
  }
}
```

---

### 2. Positions (`positions` topic)

**position_update** - Position change or P&L update
```typescript
interface PositionUpdateMessage {
  type: 'position_update';
  topic: 'positions';
  timestamp: number;
  sequence: number;
  data: {
    symbol: string;             // "AAPL"
    quantity: number;           // Can be negative for short
    average_entry_price: number;
    current_price: number;
    market_value: number;
    unrealized_pl: number;
    unrealized_pl_percent: number;
    realized_pl: number;        // For this position (closed trades)
    cost_basis: number;
    side: 'long' | 'short' | 'flat';
    opened_at: string;          // ISO 8601
    updated_at: string;
    strategy_id?: string;       // If from a strategy
  };
}
```

**Example**:
```json
{
  "type": "position_update",
  "topic": "positions",
  "timestamp": 1728172805000,
  "sequence": 43,
  "data": {
    "symbol": "AAPL",
    "quantity": 100,
    "average_entry_price": 178.45,
    "current_price": 178.92,
    "market_value": 17892.00,
    "unrealized_pl": 47.00,
    "unrealized_pl_percent": 0.26,
    "realized_pl": 0,
    "cost_basis": 17845.00,
    "side": "long",
    "opened_at": "2025-10-05T15:30:02Z",
    "updated_at": "2025-10-05T15:35:05Z"
  }
}
```

---

### 3. Portfolio (`portfolio` topic)

**portfolio_update** - Portfolio-level metrics
```typescript
interface PortfolioUpdateMessage {
  type: 'portfolio_update';
  topic: 'portfolio';
  timestamp: number;
  sequence: number;
  data: {
    equity: number;             // Total account value
    cash: number;               // Available cash
    buying_power: number;
    margin_used: number;
    positions_value: number;    // Market value of all positions
    daily_pl: number;
    daily_pl_percent: number;
    total_pl: number;           // All-time P&L
    total_pl_percent: number;
    leverage: number;           // Current leverage ratio
    updated_at: string;
  };
}
```

**Example**:
```json
{
  "type": "portfolio_update",
  "topic": "portfolio",
  "timestamp": 1728172810000,
  "sequence": 44,
  "data": {
    "equity": 105347.00,
    "cash": 87455.00,
    "buying_power": 174910.00,
    "margin_used": 0,
    "positions_value": 17892.00,
    "daily_pl": 347.00,
    "daily_pl_percent": 0.33,
    "total_pl": 5347.00,
    "total_pl_percent": 5.35,
    "leverage": 0.17,
    "updated_at": "2025-10-05T15:35:10Z"
  }
}
```

---

### 4. Market Data (`market_data` topic)

**Subscribe with Symbols**:
```json
{
  "type": "subscribe",
  "topic": "market_data",
  "symbols": ["AAPL", "TSLA", "MSFT"],
  "timestamp": 1728172800000
}
```

**price_update** - Real-time price tick
```typescript
interface PriceUpdateMessage {
  type: 'price_update';
  topic: 'market_data';
  timestamp: number;
  sequence: number;
  data: {
    symbol: string;
    price: number;              // Last trade price
    bid: number;
    ask: number;
    bid_size: number;
    ask_size: number;
    volume: number;             // Daily volume
    change: number;             // $ change from previous close
    change_percent: number;
    high: number;               // Day high
    low: number;                // Day low
    open: number;               // Day open
    previous_close: number;
    trade_time: string;         // ISO 8601 of last trade
  };
}
```

**Example**:
```json
{
  "type": "price_update",
  "topic": "market_data",
  "timestamp": 1728172815000,
  "sequence": 45,
  "data": {
    "symbol": "AAPL",
    "price": 178.92,
    "bid": 178.90,
    "ask": 178.94,
    "bid_size": 300,
    "ask_size": 250,
    "volume": 52347892,
    "change": 2.45,
    "change_percent": 1.39,
    "high": 179.15,
    "low": 176.34,
    "open": 176.50,
    "previous_close": 176.47,
    "trade_time": "2025-10-05T15:35:15Z"
  }
}
```

---

### 5. Signals (`signals` topic)

**signal_generated** - New trading signal from strategy
```typescript
interface SignalGeneratedMessage {
  type: 'signal_generated';
  topic: 'signals';
  timestamp: number;
  sequence: number;
  data: {
    signal_id: string;
    strategy_id: string;
    strategy_name: string;
    symbol: string;
    direction: 'long' | 'short' | 'close' | 'neutral';
    strength: number;           // 0-100
    confidence: number;         // 0-1
    entry_price?: number;
    stop_loss?: number;
    take_profit?: number;
    position_size?: number;
    reason: string;             // Human-readable explanation
    metadata?: Record<string, any>;
    created_at: string;
  };
}
```

**Example**:
```json
{
  "type": "signal_generated",
  "topic": "signals",
  "timestamp": 1728172820000,
  "sequence": 46,
  "data": {
    "signal_id": "SIG-20251005-042",
    "strategy_id": "momentum-001",
    "strategy_name": "Momentum Breakout v2",
    "symbol": "TSLA",
    "direction": "long",
    "strength": 85,
    "confidence": 0.78,
    "entry_price": 245.30,
    "stop_loss": 242.00,
    "take_profit": 252.00,
    "position_size": 50,
    "reason": "Breakout above 20-day MA with strong volume",
    "created_at": "2025-10-05T15:35:20Z"
  }
}
```

---

### 6. Strategies (`strategies` topic)

**strategy_update** - Strategy status or execution event
```typescript
interface StrategyUpdateMessage {
  type: 'strategy_update';
  topic: 'strategies';
  timestamp: number;
  sequence: number;
  data: {
    strategy_id: string;
    strategy_name: string;
    event: 'started' | 'stopped' | 'paused' | 'error' | 
           'position_opened' | 'position_closed' | 'signal_generated';
    status: 'running' | 'stopped' | 'paused' | 'error';
    message?: string;
    positions?: number;         // Current open positions
    daily_pl?: number;
    total_pl?: number;
    signals_today?: number;
    error?: string;
    updated_at: string;
  };
}
```

**Example**:
```json
{
  "type": "strategy_update",
  "topic": "strategies",
  "timestamp": 1728172825000,
  "sequence": 47,
  "data": {
    "strategy_id": "momentum-001",
    "strategy_name": "Momentum Breakout v2",
    "event": "position_opened",
    "status": "running",
    "message": "Opened TSLA long position (50 shares)",
    "positions": 3,
    "daily_pl": 245.50,
    "total_pl": 1823.40,
    "signals_today": 5,
    "updated_at": "2025-10-05T15:35:25Z"
  }
}
```

---

### 7. Alerts (`alerts` topic)

**alert** - System alert or notification
```typescript
interface AlertMessage {
  type: 'alert';
  topic: 'alerts';
  timestamp: number;
  sequence: number;
  data: {
    alert_id: string;
    severity: 'info' | 'warning' | 'error' | 'critical';
    category: 'risk' | 'system' | 'trading' | 'strategy' | 'compliance';
    title: string;
    message: string;
    action_required?: boolean;
    action_label?: string;      // e.g., "Review Position"
    action_link?: string;       // Frontend route
    related_entity?: {
      type: 'order' | 'position' | 'strategy';
      id: string;
    };
    created_at: string;
  };
}
```

**Example - Risk Alert**:
```json
{
  "type": "alert",
  "topic": "alerts",
  "timestamp": 1728172830000,
  "sequence": 48,
  "data": {
    "alert_id": "ALERT-20251005-003",
    "severity": "warning",
    "category": "risk",
    "title": "Approaching Daily Loss Limit",
    "message": "Daily P&L is -$4,500 (90% of $5,000 limit). Consider reducing exposure.",
    "action_required": true,
    "action_label": "Review Positions",
    "action_link": "/portfolio/positions",
    "created_at": "2025-10-05T15:35:30Z"
  }
}
```

**Example - Trading Alert**:
```json
{
  "type": "alert",
  "topic": "alerts",
  "timestamp": 1728172835000,
  "sequence": 49,
  "data": {
    "alert_id": "ALERT-20251005-004",
    "severity": "error",
    "category": "trading",
    "title": "Order Rejected",
    "message": "Order ORD-20251005-042 was rejected: Insufficient buying power",
    "action_required": true,
    "action_label": "View Order",
    "action_link": "/trading/orders/ORD-20251005-042",
    "related_entity": {
      "type": "order",
      "id": "ORD-20251005-042"
    },
    "created_at": "2025-10-05T15:35:35Z"
  }
}
```

---

### 8. Risk (`risk` topic)

**risk_update** - Risk metric change
```typescript
interface RiskUpdateMessage {
  type: 'risk_update';
  topic: 'risk';
  timestamp: number;
  sequence: number;
  data: {
    metric: 'daily_pl' | 'max_drawdown' | 'leverage' | 'var' | 
            'position_concentration' | 'exposure';
    current_value: number;
    limit?: number;
    threshold_percent?: number;  // How close to limit (0-100)
    status: 'normal' | 'warning' | 'critical';
    message?: string;
    updated_at: string;
  };
}
```

**Example**:
```json
{
  "type": "risk_update",
  "topic": "risk",
  "timestamp": 1728172840000,
  "sequence": 50,
  "data": {
    "metric": "daily_pl",
    "current_value": -4500,
    "limit": -5000,
    "threshold_percent": 90,
    "status": "warning",
    "message": "Daily loss approaching limit",
    "updated_at": "2025-10-05T15:35:40Z"
  }
}
```

---

## Error Handling

### Error Message
```typescript
interface ErrorMessage {
  type: 'error';
  timestamp: number;
  data: {
    code: string;               // Error code
    message: string;            // Human-readable message
    details?: any;              // Additional context
  };
}
```

**Example - Authentication Error**:
```json
{
  "type": "error",
  "timestamp": 1728172800000,
  "data": {
    "code": "AUTH_FAILED",
    "message": "Invalid or expired token",
    "details": {
      "reason": "Token expired at 2025-10-05T15:00:00Z"
    }
  }
}
```

**Example - Subscription Error**:
```json
{
  "type": "error",
  "timestamp": 1728172801000,
  "data": {
    "code": "SUBSCRIPTION_FAILED",
    "message": "Cannot subscribe to topic: market_data",
    "details": {
      "reason": "No symbols provided"
    }
  }
}
```

---

## Reconnection Strategy

### Exponential Backoff
```typescript
class WebSocketManager {
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private baseDelay = 1000; // 1 second
  private maxDelay = 30000; // 30 seconds

  reconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnection attempts reached');
      // Show user notification
      return;
    }

    // Calculate delay: min(baseDelay * 2^attempts, maxDelay)
    const delay = Math.min(
      this.baseDelay * Math.pow(2, this.reconnectAttempts),
      this.maxDelay
    );

    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1})`);

    setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }

  onConnected() {
    // Reset on successful connection
    this.reconnectAttempts = 0;
    
    // Resubscribe to previous topics
    this.resubscribe();
  }
}
```

**Backoff Sequence**: 1s, 2s, 4s, 8s, 16s, 30s, 30s, 30s, 30s, 30s (max 10 attempts)

---

## State Recovery

After reconnection, client should:

1. **Resubscribe to all previous topics**
2. **Request snapshot** (optional endpoint):
   ```json
   {
     "type": "request_snapshot",
     "topics": ["orders", "positions", "portfolio"]
   }
   ```
3. **Use sequence numbers** to detect missed messages
4. **Fetch latest data** via REST if sequence gap detected

---

## Best Practices

### Client Implementation

1. **Message Queue**: Handle messages in order using sequence numbers
2. **Deduplication**: Track processed message IDs to avoid duplicates
3. **Throttling**: Batch rapid updates (e.g., price ticks) to avoid UI thrashing
4. **Buffer Management**: Limit stored messages to prevent memory leaks
5. **User Visibility**: Show connection status (connected, connecting, disconnected)

### Example Client Class

```typescript
class TradingWebSocket {
  private ws: WebSocket | null = null;
  private subscriptions: Set<string> = new Set();
  private messageHandlers: Map<string, (data: any) => void> = new Map();
  private reconnectAttempts = 0;
  private heartbeatInterval?: NodeJS.Timeout;
  
  connect(clientId: string, token: string) {
    const url = `ws://localhost:8000/ws/realtime/${clientId}?token=${token}`;
    this.ws = new WebSocket(url);
    
    this.ws.onopen = () => this.onOpen();
    this.ws.onmessage = (event) => this.onMessage(event);
    this.ws.onerror = (error) => this.onError(error);
    this.ws.onclose = (event) => this.onClose(event);
  }
  
  subscribe(topic: string, handler: (data: any) => void) {
    this.subscriptions.add(topic);
    this.messageHandlers.set(topic, handler);
    
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.send({ type: 'subscribe', topic });
    }
  }
  
  unsubscribe(topic: string) {
    this.subscriptions.delete(topic);
    this.messageHandlers.delete(topic);
    
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.send({ type: 'unsubscribe', topic });
    }
  }
  
  private send(message: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ ...message, timestamp: Date.now() }));
    }
  }
  
  private onOpen() {
    console.log('WebSocket connected');
    this.reconnectAttempts = 0;
    this.startHeartbeat();
    this.resubscribe();
  }
  
  private onMessage(event: MessageEvent) {
    const message = JSON.parse(event.data);
    const handler = this.messageHandlers.get(message.topic);
    if (handler) {
      handler(message.data);
    }
  }
  
  private startHeartbeat() {
    this.heartbeatInterval = setInterval(() => {
      this.send({ type: 'heartbeat' });
    }, 25000);
  }
  
  private resubscribe() {
    this.subscriptions.forEach(topic => {
      this.send({ type: 'subscribe', topic });
    });
  }
  
  disconnect() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
    }
    this.ws?.close();
  }
}
```

---

## Testing

### Manual Testing
Use `websocat` tool:
```bash
# Install websocat
cargo install websocat

# Connect
websocat "ws://localhost:8000/ws/realtime/test-client-123?token=YOUR_JWT_TOKEN"

# Subscribe to orders
{"type": "subscribe", "topic": "orders", "timestamp": 1728172800000}

# Send heartbeat
{"type": "heartbeat", "timestamp": 1728172800000}
```

### Integration Tests
```typescript
describe('WebSocket', () => {
  it('should connect and subscribe', async () => {
    const ws = new TradingWebSocket();
    await ws.connect(clientId, token);
    
    const messages: any[] = [];
    ws.subscribe('orders', (data) => messages.push(data));
    
    // Wait for order update
    await waitFor(() => messages.length > 0);
    
    expect(messages[0]).toHaveProperty('order_id');
  });
});
```

---

## Security Considerations

1. **Authentication**: Always use token-based auth (JWT)
2. **Encryption**: Use WSS (WebSocket Secure) in production
3. **Rate Limiting**: Server should limit subscription requests
4. **Authorization**: Server validates user can access requested topics
5. **Message Validation**: Validate all incoming messages on server
6. **Client Validation**: Validate message structure on client

---

## Performance

### Message Frequency Expectations
- **Orders**: Event-driven (typically 1-10/second during active trading)
- **Positions**: Every 1-5 seconds or on change
- **Portfolio**: Every 5 seconds or on significant change (>0.1%)
- **Market Data**: 1-2 second intervals per symbol (or tick-by-tick if available)
- **Signals**: Event-driven (varies by strategy, 0-100/hour)
- **Alerts**: Event-driven (occasional)

### Bandwidth Estimation
- Average message size: ~500 bytes (JSON)
- 10 symbols market data: ~5 KB/sec
- With all topics subscribed: ~10-20 KB/sec typical
- Peak: ~50 KB/sec during high volatility

---

**Last Updated**: October 5, 2025  
**Maintainer**: Backend & Frontend Teams  
**Review Schedule**: Weekly during implementation
