# WebSocket Real-Time Updates - Implementation Guide

## Overview

This document explains the WebSocket infrastructure for real-time data updates in the AlgoTrading Platform.

## Architecture

### Components

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Frontend  │         │    Backend   │         │  Database   │
│  (React)    │◄───────►│  (FastAPI)   │◄───────►│ (PostgreSQL)│
└─────────────┘         └──────────────┘         └─────────────┘
      │                        │
      │  WebSocket             │  Socket.IO
      │  Connection            │  Broadcasts
      │                        │
      └────────────────────────┘
           Real-time Data
```

### Key Files

**Backend:**
- `backend/api/socketio_server.py` - WebSocket server and broadcast functions
- `backend/api/portfolio.py` - Portfolio endpoints (includes test endpoints)
- `backend/api/orders.py` - Order endpoints with WebSocket broadcasts

**Frontend:**
- `frontend/src/services/websocketManager.ts` - WebSocket connection manager
- `frontend/src/hooks/useWebSocket.ts` - React hook for subscriptions
- `frontend/src/hooks/useData.ts` - Data fetching with WebSocket integration
- `frontend/src/store/*Store.ts` - Zustand stores for state management

---

## The Critical Fix

### Problem Identified

The original implementation had API polling (`refetchInterval: 10000`) that **overwrote WebSocket updates** every 10 seconds:

```typescript
// PROBLEM: This overwrites WebSocket updates!
const query = useQuery({
  queryKey: ['portfolio'],
  queryFn: portfolioService.getPortfolio,
  refetchInterval: 10000, // ❌ Bad: Polls every 10 seconds
});

useEffect(() => {
  if (query.data) {
    setPortfolio(query.data); // ❌ Overwrites WebSocket state
  }
}, [query.data]);
```

**Result:** WebSocket would update to $105k, then 3 seconds later API refetch would reset it to $100k.

### Solution

Disable API refetching after initial load - let WebSocket handle ALL updates:

```typescript
// SOLUTION: API only for initial load
const query = useQuery({
  queryKey: ['portfolio'],
  queryFn: portfolioService.getPortfolio,
  refetchInterval: false,          // ✅ No polling
  refetchOnWindowFocus: false,     // ✅ No refetch on focus
  refetchOnReconnect: false,       // ✅ No refetch on reconnect
  staleTime: Infinity,             // ✅ Never stale
});

useEffect(() => {
  if (query.data && !portfolio) {  // ✅ Only on first load
    setPortfolio(query.data);
  }
}, [query.data, setPortfolio, portfolio]);
```

---

## Backend Implementation

### Broadcasting Updates

```python
from backend.api.socketio_server import broadcast_portfolio_update

# Broadcast to specific user
await broadcast_portfolio_update(
    user_id="admin@example.com",
    portfolio_data={
        'totalEquity': 105000.0,
        'cash': 105000.0,
        'buyingPower': 105000.0,
        'marginUsed': 0.0,
        'maintenanceMargin': 0.0,
        'totalPnL': 5000.0,
        'totalPnLPercent': 5.0,
        'dayPnL': 5000.0,
        'dayPnLPercent': 5.0,
        'positions': [],
        'userId': 'admin@example.com',
        'lastUpdate': datetime.now(timezone.utc).isoformat()
    }
)
```

### Test Endpoints

Two test endpoints are available for development:

#### 1. Broadcast to ALL Connected Clients

```bash
POST /api/v1/portfolio/test-broadcast-all
Authorization: Bearer {token}
```

Sends 4 test updates to all connected clients:
- $100k (Initial)
- $105k (Profit +$5k)
- $103k (Adjusted -$2k)
- $100k (Reset)

#### 2. Simple Single Value Broadcast

```bash
POST /api/v1/portfolio/test-simple-broadcast?target_value=125000
Authorization: Bearer {token}
```

Sends a single update with specified value to all clients.

**Usage Example:**

```powershell
# Login
$loginResp = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
  -Method POST `
  -Body (@{username="admin@example.com"; password="Admin123!@#"} | ConvertTo-Json) `
  -ContentType "application/json"
  
$token = $loginResp.access_token

# Broadcast $125k
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/v1/portfolio/test-simple-broadcast?target_value=125000" `
  -Method POST `
  -Headers @{"Authorization"="Bearer $token"}
```

---

## Frontend Implementation

### Subscribing to Updates

```typescript
import { useWebSocket } from '@/hooks/useWebSocket';
import { usePortfolioStore } from '@/store/portfolioStore';

const MyComponent = () => {
  const setPortfolio = usePortfolioStore((state) => state.setPortfolio);
  
  // Handler for portfolio updates
  const handlePortfolioUpdate = useMemo(
    () => (message: PortfolioUpdateMessage) => {
      if (message.data) {
        setPortfolio({
          userId: message.data.userId,
          totalEquity: message.data.totalEquity,
          cash: message.data.cash,
          // ... other fields
        });
      }
    },
    [setPortfolio]
  );
  
  // Subscribe to portfolio updates
  useWebSocket('portfolio', handlePortfolioUpdate);
  
  // Component renders with real-time data from store
  const portfolio = usePortfolioStore((state) => state.portfolio);
  
  return <div>Portfolio: ${portfolio?.totalEquity}</div>;
};
```

### Available Topics

- `portfolio` - Portfolio value and positions updates
- `orders` - Order status changes
- `strategies` - Strategy status and performance
- `market_data` - Real-time market data
- `signals` - Trading signals

---

## Data Flow

### Initial Page Load

```
1. Component mounts
   ↓
2. usePortfolio() fetches from API (ONE TIME)
   ↓
3. Data loaded → setPortfolio(apiData)
   ↓
4. Store populated with initial data
   ↓
5. Component renders with API data
   ↓
6. WebSocket connects and subscribes
   ↓
7. Ready for real-time updates
```

### Real-Time Updates

```
1. Backend event occurs (order fills, price update)
   ↓
2. broadcast_portfolio_update() called
   ↓
3. Message sent via Socket.IO to user's clients
   ↓
4. Frontend websocketManager receives event
   ↓
5. handleMessage() routes to subscribed handlers
   ↓
6. handlePortfolioUpdate() called
   ↓
7. setPortfolio() updates Zustand store
   ↓
8. React re-renders with new data
   ↓
9. UI displays updated values
```

**Key Point:** API is **never** called again after initial load. All updates come via WebSocket.

---

## Testing

### Automated Tests

Run the WebSocket integration test suite:

```bash
pytest tests/test_websocket_integration.py -v
```

**Test Coverage:**
- Connection with valid/invalid tokens
- Topic subscriptions
- Message broadcasting
- Multi-client scenarios
- Reconnection handling
- User isolation (users only receive their own updates)

### Manual Testing

1. **Start servers:**
   ```bash
   # Terminal 1: Backend
   python main.py
   
   # Terminal 2: Frontend
   cd frontend
   npm run dev
   ```

2. **Login to dashboard** (http://localhost:5173)

3. **Trigger test broadcast:**
   ```powershell
   # Get token
   $loginResp = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/auth/login" `
     -Method POST `
     -Body (@{username="admin@example.com"; password="Admin123!@#"} | ConvertTo-Json) `
     -ContentType "application/json"
   $token = $loginResp.access_token
   
   # Send different values
   Invoke-RestMethod -Uri "http://localhost:8000/api/v1/portfolio/test-simple-broadcast?target_value=110000" `
     -Method POST -Headers @{"Authorization"="Bearer $token"}
   
   Start-Sleep -Seconds 2
   
   Invoke-RestMethod -Uri "http://localhost:8000/api/v1/portfolio/test-simple-broadcast?target_value=125000" `
     -Method POST -Headers @{"Authorization"="Bearer $token"}
   ```

4. **Observe dashboard updating in real-time**

---

## Troubleshooting

### Dashboard not updating

**Check:**
1. WebSocket connection status (green indicator in top-right)
2. Browser console for connection errors
3. Backend logs for broadcast confirmation
4. User ID matches between frontend login and backend broadcast

**Common Issues:**

| Symptom | Cause | Solution |
|---------|-------|----------|
| Brief flash then resets | API overwriting | Ensure `refetchInterval: false` in useData.ts |
| No updates at all | Not subscribed | Check `useWebSocket('portfolio', handler)` called |
| Wrong user receives | User ID mismatch | Broadcast to correct user_id |
| Disconnects frequently | Network/timeout | Check firewall, increase ping_interval |

### Debug Mode

Enable detailed logging (for development only):

```typescript
// In websocketManager.ts
console.log('[WebSocket] Message received:', message);

// In Dashboard.tsx
console.log('Portfolio updated:', portfolio);
```

**Note:** Production builds should have all debug logs removed.

---

## Best Practices

### Do's ✅

- ✅ Use WebSocket for real-time updates
- ✅ Use API only for initial page load
- ✅ Set `refetchInterval: false` for WebSocket-powered data
- ✅ Use Zustand stores as single source of truth
- ✅ Broadcast to specific users with `user_{user_id}` topics
- ✅ Test with multiple concurrent clients
- ✅ Handle reconnection gracefully

### Don'ts ❌

- ❌ Don't poll API when using WebSocket
- ❌ Don't fetch from API in component effects
- ❌ Don't broadcast sensitive data without user filtering
- ❌ Don't store WebSocket data in component state
- ❌ Don't ignore connection errors
- ❌ Don't leave debug logs in production

---

## Performance Considerations

### Backend

- Each connected client maintains one WebSocket connection
- Broadcasting scales to thousands of concurrent users
- User-specific topics prevent unnecessary message delivery
- Async/await prevents blocking

### Frontend

- Single WebSocket connection per browser tab
- Zustand provides O(1) state updates
- React re-renders only affected components
- No polling = reduced server load

---

## Security

### Authentication

- JWT token required for WebSocket connection
- Token verified on connect
- Invalid tokens rejected immediately

### Authorization

- Users auto-subscribed to `user_{user_id}` topic
- Broadcasts scoped to specific users
- No cross-user data leakage

### Best Practices

- Rotate JWT tokens regularly
- Use HTTPS/WSS in production
- Validate all broadcast data
- Rate-limit connections per user

---

## Migration Guide

### From Polling to WebSocket

If migrating existing polling-based code:

**Before (Polling):**
```typescript
const query = useQuery({
  queryKey: ['portfolio'],
  queryFn: fetchPortfolio,
  refetchInterval: 5000, // ❌ Polls every 5 seconds
});
```

**After (WebSocket):**
```typescript
const query = useQuery({
  queryKey: ['portfolio'],
  queryFn: fetchPortfolio,
  refetchInterval: false, // ✅ No polling
  refetchOnWindowFocus: false,
  staleTime: Infinity,
});

useWebSocket('portfolio', handlePortfolioUpdate); // ✅ Real-time
```

---

## Future Enhancements

### Planned Features

- [ ] Binary message format for reduced bandwidth
- [ ] Compression for large payloads
- [ ] Message queuing for offline support
- [ ] Heartbeat monitoring with auto-reconnect
- [ ] Message delivery confirmation
- [ ] Historical message replay on reconnect

---

## Support

For issues or questions:

1. Check this documentation
2. Review test suite for examples
3. Check backend logs: `logs/app.log`
4. Check browser console for frontend errors
5. Run integration tests: `pytest tests/test_websocket_integration.py -v`

---

**Last Updated:** October 6, 2025  
**Version:** 1.0.0  
**Status:** Production Ready ✅
