# Alpaca Portfolio Sync Implementation

## Overview

This implementation adds **Alpaca portfolio synchronization** to the algotrading platform. The system now fetches real-time account data and positions from your Alpaca paper trading account and displays them in the dashboard.

## Problem Solved

**Before**: Dashboard showed default $100k value because it only read from local database, which didn't reflect your actual Alpaca paper trading positions.

**After**: Dashboard syncs with Alpaca on startup and displays your real positions, balance, and P&L.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ALPACA PAPER ACCOUNT                      │
│  (Real positions, balance, buying power, P&L)               │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ REST API Calls
                           │ (get_account, get_positions)
                           ↓
┌─────────────────────────────────────────────────────────────┐
│             PORTFOLIO SYNC SERVICE                           │
│  - Fetches account data from Alpaca                         │
│  - Fetches all positions from Alpaca                        │
│  - Syncs to local PostgreSQL database                       │
│  - Runs on startup & on-demand                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              LOCAL DATABASE (PostgreSQL)                     │
│  - Portfolio table (cash, equity, buying power)             │
│  - Position table (symbol, qty, prices, P&L)                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              PORTFOLIO SERVICE                               │
│  - Reads from local DB (fast)                               │
│  - Syncs from Alpaca if DB empty                            │
│  - Serves data to API                                       │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────────┐
│              API ENDPOINTS                                   │
│  GET  /api/v1/portfolio - Get portfolio summary            │
│  POST /api/v1/portfolio/sync - Trigger sync                │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ↓ HTTP & WebSocket
┌─────────────────────────────────────────────────────────────┐
│              DASHBOARD (React Frontend)                      │
│  - Shows real Alpaca data                                   │
│  - WebSocket updates in real-time                           │
│  - Persists across page refreshes                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Components Added/Modified

### 1. AlpacaBrokerClient Enhancement
**File**: `backend/integrations/alpaca_broker.py`

**Added Methods**:
```python
async def get_account(self) -> Dict:
    """Fetch account data: cash, equity, buying power, etc."""
    
async def get_positions(self) -> list[Dict]:
    """Fetch all open positions with P&L."""
```

**Usage**:
```python
from backend.integrations.alpaca_broker import get_alpaca_broker_client

client = get_alpaca_broker_client()
account = await client.get_account()
positions = await client.get_positions()
```

---

### 2. Portfolio Sync Service (NEW)
**File**: `backend/services/portfolio_sync_service.py`

**Responsibilities**:
- Fetch account data from Alpaca API
- Fetch positions from Alpaca API
- Persist to local database (replaces old data)
- Return sync results

**Main Method**:
```python
async def sync_full_portfolio(self, user_id: str) -> dict:
    """
    Perform full sync: account + positions.
    Returns: {"success": True, "portfolio": {...}, "positions": [...]}
    """
```

**Usage**:
```python
from backend.services.portfolio_sync_service import get_portfolio_sync_service

sync_service = get_portfolio_sync_service()
result = await sync_service.sync_full_portfolio("demo")

if result["success"]:
    print(f"Synced {len(result['positions'])} positions")
```

---

### 3. Portfolio Service Enhancement
**File**: `backend/services/portfolio_service.py`

**Smart Fetching Logic**:
```python
async def get_user_portfolio(self, user_id: str, force_sync: bool = False):
    """
    1. Check local database for positions
    2. If empty OR force_sync=True: sync from Alpaca
    3. Return portfolio data
    """
```

**Behavior**:
- First call: Database empty → syncs from Alpaca automatically
- Subsequent calls: Uses cached database data (fast)
- Manual refresh: Call with `force_sync=True`

---

### 4. API Endpoint (NEW)
**File**: `backend/api/portfolio.py`

**Added Endpoint**:
```python
POST /api/v1/portfolio/sync
Authorization: Bearer <token>
```

**Purpose**: Manually trigger portfolio sync from Alpaca

**Response**:
```json
{
  "success": true,
  "message": "Portfolio synced successfully from Alpaca",
  "data": {
    "portfolio": {
      "cash": "95000.00",
      "total_equity": "105000.00",
      "buying_power": "190000.00",
      "day_pnl": "500.00",
      "total_pnl": "5000.00"
    },
    "positions": [
      {
        "symbol": "AAPL",
        "quantity": "50",
        "avg_entry_price": "180.00",
        "current_price": "185.00",
        "market_value": "9250.00",
        "unrealized_pnl": "250.00"
      }
    ],
    "synced_at": "2025-10-06T10:30:00Z"
  }
}
```

---

### 5. Startup Hook
**File**: `backend/api/factory.py`

**Added to `lifespan()` function**:
```python
# PORTFOLIO SYNC ON STARTUP
if not use_mock_broker and database_configured:
    sync_service = get_portfolio_sync_service()
    await sync_service.sync_full_portfolio(default_user_id)
    logger.info("Initial portfolio sync completed")
```

**Behavior**: When backend starts, automatically syncs portfolio from Alpaca

---

## Configuration

### Environment Variables

Required for Alpaca integration:

```bash
# Alpaca API credentials
ALPACA_API_KEY_ID=your_key_here
ALPACA_API_SECRET_KEY=your_secret_here

# Paper trading (set to false for live trading)
ALPACA_PAPER=true

# Base URL (auto-selected based on ALPACA_PAPER)
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Disable mock broker to use real Alpaca
USE_MOCK_BROKER=false

# Database connection
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/algotrading

# Default user for startup sync
DEFAULT_USER_ID=demo
```

---

## Testing

### 1. Automated Test Script

Run the comprehensive test suite:

```bash
python test_alpaca_sync.py
```

**Tests performed**:
1. ✓ Alpaca API connection
2. ✓ Fetch account data
3. ✓ Fetch positions
4. ✓ Sync to database
5. ✓ Portfolio service retrieval

**Expected output**:
```
======================================================================
ALPACA PORTFOLIO SYNC TEST SUITE
======================================================================

Environment Configuration:
  ALPACA_API_KEY_ID: ✓ Set
  ALPACA_API_SECRET_KEY: ✓ Set
  ALPACA_PAPER: true
  DATABASE_URL: ✓ Set
  USE_MOCK_BROKER: false

======================================================================
TEST 1: Alpaca API Connection
======================================================================
✓ Alpaca client initialized
  Base URL: https://paper-api.alpaca.markets
  Paper trading: True
  API key configured: True

======================================================================
TEST 2: Fetch Account Data
======================================================================
✓ Account data fetched successfully
  Account number: PA2XXXXXX
  Cash: $95,000.00
  Portfolio value: $105,000.00
  Equity: $105,000.00
  Buying power: $190,000.00
  Status: ACTIVE

======================================================================
TEST 3: Fetch Positions
======================================================================
✓ Positions fetched successfully
  Position count: 2

  Positions:
    AAPL: 50 shares @ $180.00
      Current: $185.00, Value: $9,250.00
      Unrealized P&L: $250.00
    MSFT: 20 shares @ $300.00
      Current: $305.00, Value: $6,100.00
      Unrealized P&L: $100.00

======================================================================
TEST 4: Portfolio Sync to Database
======================================================================
  Syncing for user: demo
✓ Portfolio synced successfully

  Portfolio Summary:
    Cash: $95,000.00
    Total Equity: $105,000.00
    Buying Power: $190,000.00
    Day P&L: $500.00
    Total P&L: $5,000.00

  Synced 2 positions to database
    AAPL: 50 shares, P&L: $250.00
    MSFT: 20 shares, P&L: $100.00

======================================================================
TEST 5: Portfolio Service Retrieval
======================================================================
  Getting portfolio for user: demo
✓ Portfolio retrieved successfully

  Portfolio Data:
    Total Equity: $105,000.00
    Cash: $95,000.00
    Buying Power: $190,000.00
    Total P&L: $5,000.00 (5.00%)
    Day P&L: $500.00 (0.48%)

  Positions: 2
    AAPL: 50 shares @ $180.00
    MSFT: 20 shares @ $300.00

======================================================================
TEST SUMMARY
======================================================================
  Tests passed: 5/5

✅ All tests passed! Alpaca portfolio sync is working correctly.
```

---

### 2. Manual Testing

#### Start Backend Server
```bash
python main.py
```

**Expected startup logs**:
```
🚀 Starting Algorithmic Trading Platform
==================================================
Environment: development
API Server: http://localhost:8000
Documentation: http://localhost:8000/docs
WebSocket: ws://localhost:8000/socket.io
==================================================
📊 Initializing database...
✅ Database initialized successfully
INFO:backend.api.factory - Outbox worker started successfully
INFO:backend.api.factory - Alpaca WebSocket stream client started successfully
INFO:backend.api.factory - Starting initial portfolio sync from Alpaca...
INFO:backend.services.portfolio_sync_service - Syncing account data from Alpaca
INFO:backend.services.portfolio_sync_service - Account data synced successfully
INFO:backend.services.portfolio_sync_service - Syncing positions from Alpaca
INFO:backend.services.portfolio_sync_service - Synced position symbol=AAPL
INFO:backend.services.portfolio_sync_service - Synced position symbol=MSFT
INFO:backend.api.factory - Initial portfolio sync completed successfully
```

#### Test API Endpoint

**Get Portfolio**:
```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/api/v1/portfolio/
```

**Response**:
```json
{
  "totalEquity": 105000.00,
  "cash": 95000.00,
  "buyingPower": 190000.00,
  "marginUsed": 0.0,
  "maintenanceMargin": 0.0,
  "totalPnL": 5000.00,
  "totalPnLPercent": 5.0,
  "dayPnL": 500.00,
  "dayPnLPercent": 0.48,
  "positions": [
    {
      "symbol": "AAPL",
      "quantity": 50,
      "avg_price": "180.00",
      "market_value": "9250.00",
      "unrealized_pnl": "250.00",
      "realized_pnl": "0.00"
    }
  ],
  "userId": "demo",
  "lastUpdate": "2025-10-06T10:30:00.000Z"
}
```

**Trigger Manual Sync**:
```bash
curl -X POST -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8000/api/v1/portfolio/sync
```

---

### 3. Frontend Testing

1. **Open Dashboard**: http://localhost:3000
2. **Login**: Use your credentials
3. **Verify Display**:
   - Total Equity should match Alpaca account
   - Positions table should show your Alpaca positions
   - P&L values should match Alpaca
4. **Test Refresh**:
   - Refresh page → Data persists (from database)
   - Should NOT reset to $100k anymore
5. **Test Real-Time Updates**:
   - Make a trade in Alpaca (or wait for price changes)
   - Dashboard updates via WebSocket

---

## Usage Examples

### Scenario 1: First-Time Setup

```python
# 1. User logs into platform for first time
# 2. Portfolio service detects empty database
# 3. Automatically syncs from Alpaca
# 4. Dashboard shows real positions
```

**Code flow**:
```python
# In portfolio_service.py
async def get_user_portfolio(self, user_id: str):
    positions = await session.execute(select(Position))
    
    if not positions:  # Database empty
        logger.info("Local portfolio empty, syncing from Alpaca")
        sync_service = self._get_sync_service()
        await sync_service.sync_full_portfolio(user_id)
        # Re-fetch positions after sync
        positions = await session.execute(select(Position))
```

---

### Scenario 2: Manual Refresh

```bash
# User clicks "Refresh Portfolio" button in UI
POST /api/v1/portfolio/sync

# Backend syncs from Alpaca
# WebSocket broadcasts update
# Dashboard shows latest data
```

---

### Scenario 3: Startup Sync

```python
# On server startup (in factory.py lifespan)
sync_service = get_portfolio_sync_service()
await sync_service.sync_full_portfolio("demo")

# All users' portfolios synced on startup
# No stale data when users first access platform
```

---

### Scenario 4: Periodic Background Sync

**Future Enhancement** (not yet implemented):

```python
# In factory.py, add background task
async def periodic_sync_task():
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        sync_service = get_portfolio_sync_service()
        await sync_service.sync_full_portfolio("demo")

# Start task in lifespan
sync_task = asyncio.create_task(periodic_sync_task())
```

---

## Data Flow

### Sync Process

```
1. API Call Trigger
   └─> POST /api/v1/portfolio/sync
       └─> portfolio_sync_service.sync_full_portfolio()

2. Fetch from Alpaca
   └─> alpaca_broker.get_account()
       └─> GET https://paper-api.alpaca.markets/v2/account
           └─> Returns: cash, equity, buying_power, etc.
   
   └─> alpaca_broker.get_positions()
       └─> GET https://paper-api.alpaca.markets/v2/positions
           └─> Returns: [{symbol, qty, prices, P&L}, ...]

3. Database Update
   └─> portfolio_sync_service.sync_account_data()
       └─> UPDATE portfolio SET cash=X, equity=Y WHERE user_id=Z
   
   └─> portfolio_sync_service.sync_positions()
       └─> DELETE FROM position WHERE portfolio_id=X
       └─> INSERT INTO position VALUES (...)  # For each position

4. WebSocket Broadcast
   └─> socketio.emit('portfolio_update', data)
       └─> Frontend receives update
           └─> Dashboard re-renders with new data

5. Response
   └─> Return sync results to API caller
```

---

## Error Handling

### Alpaca API Errors

**Scenario**: Alpaca API is down or credentials invalid

**Behavior**:
```python
try:
    account = await client.get_account()
except HTTPException as e:
    # Returns 502 Bad Gateway
    # Error logged with details
    # Portfolio service falls back to cached data
```

**User Experience**:
- Dashboard shows last known values (from database)
- Banner notification: "Unable to sync with broker, showing cached data"
- Retry button available

---

### Database Errors

**Scenario**: Database connection lost during sync

**Behavior**:
```python
try:
    await session.commit()
except Exception as e:
    await session.rollback()
    logger.error("Database sync failed")
    # Returns error to API caller
```

**User Experience**:
- API returns 500 error
- Frontend shows error toast
- Data not corrupted (rollback ensures consistency)

---

### Empty Portfolio

**Scenario**: User has no positions in Alpaca

**Behavior**:
- Sync succeeds but positions list is empty
- Portfolio shows cash balance only
- Total equity = cash
- Positions table shows "No positions"

---

## Monitoring & Logging

### Startup Logs

```
INFO:backend.api.factory - Starting initial portfolio sync from Alpaca...
INFO:backend.services.portfolio_sync_service - Syncing account data from Alpaca, user_id=demo
INFO:backend.integrations.alpaca_broker - Account data retrieved successfully, cash=95000.00
INFO:backend.services.portfolio_sync_service - Account data synced successfully, total_equity=105000.00
INFO:backend.services.portfolio_sync_service - Syncing positions from Alpaca, user_id=demo
INFO:backend.integrations.alpaca_broker - Positions retrieved successfully, position_count=2
INFO:backend.services.portfolio_sync_service - Synced position, symbol=AAPL, quantity=50
INFO:backend.services.portfolio_sync_service - Synced position, symbol=MSFT, quantity=20
INFO:backend.api.factory - Initial portfolio sync completed successfully, position_count=2
```

### API Request Logs

```
INFO:backend.api.portfolio - [SYNC] Starting portfolio sync from Alpaca for user: demo
INFO:backend.services.portfolio_sync_service - Full portfolio sync completed successfully
INFO:backend.api.portfolio - [SYNC] Successfully synced portfolio for user demo
INFO:backend.api.portfolio - [SYNC] Broadcasted portfolio update via WebSocket
```

### Error Logs

```
ERROR:backend.integrations.alpaca_broker - Failed to retrieve account data, status_code=401, error=Invalid credentials
WARNING:backend.services.portfolio_sync_service - Failed to sync account data, user_id=demo, error=HTTPException
ERROR:backend.api.portfolio - [SYNC] Unexpected error: HTTPException: Alpaca API credentials not configured
```

---

## Troubleshooting

### Issue: Dashboard shows $100k instead of real data

**Diagnosis**:
1. Check `USE_MOCK_BROKER` environment variable
   ```bash
   echo $USE_MOCK_BROKER
   # Should be: false
   ```

2. Check Alpaca credentials
   ```bash
   echo $ALPACA_API_KEY_ID
   echo $ALPACA_API_SECRET_KEY
   # Should both return values
   ```

3. Check startup logs for sync errors
   ```bash
   tail -f logs/app.log | grep -i "sync\|alpaca"
   ```

**Solution**:
```bash
# Fix environment variables
export USE_MOCK_BROKER=false
export ALPACA_API_KEY_ID=your_key
export ALPACA_API_SECRET_KEY=your_secret

# Restart server
python main.py

# Manually trigger sync
curl -X POST http://localhost:8000/api/v1/portfolio/sync \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### Issue: Sync fails with "Invalid credentials"

**Diagnosis**: API key/secret incorrect or expired

**Solution**:
1. Verify credentials in Alpaca dashboard: https://app.alpaca.markets
2. Generate new paper trading keys if needed
3. Update `.env` file
4. Restart server

---

### Issue: Positions not showing after sync

**Diagnosis**: 
- Database connection issue
- User ID mismatch
- No positions in Alpaca account

**Solution**:
```python
# Check database directly
python
>>> from backend.infra.db import get_session
>>> from backend.infra.schemas import Position
>>> async with get_session() as session:
...     positions = await session.execute(select(Position))
...     print(positions.scalars().all())
```

---

### Issue: Sync succeeds but dashboard doesn't update

**Diagnosis**: WebSocket broadcast not working

**Solution**:
1. Check WebSocket connection in browser console
2. Verify user is subscribed to 'portfolio' topic
3. Check backend logs for broadcast errors
4. Manually refresh page (data should be in database)

---

## Performance Considerations

### Sync Frequency

**Recommended**:
- Startup: Always sync (ensures fresh data)
- On-demand: When user clicks "Refresh" button
- Periodic: Every 5-10 minutes (optional background task)
- After trades: When order fills (Alpaca WebSocket triggers sync)

**Not recommended**:
- Every API request (too slow)
- More than once per minute (Alpaca rate limits)

---

### Database Queries

**Optimized**:
```python
# Single query with eager loading
positions = await session.execute(
    select(Position)
    .options(joinedload(Position.portfolio))
    .where(Position.user_id == user_id)
)
```

**Not optimized**:
```python
# N+1 query problem
portfolio = await session.get(Portfolio, portfolio_id)
for symbol in symbols:
    position = await session.get(Position, (portfolio_id, symbol))  # BAD
```

---

### Caching Strategy

**Current**: Database acts as cache
- Fast reads (local PostgreSQL)
- Stale data handled by periodic sync
- Persistent across server restarts

**Future Enhancement**: Redis cache layer
```python
# Check Redis first
cached = await redis.get(f"portfolio:{user_id}")
if cached:
    return json.loads(cached)

# Fallback to database
portfolio = await fetch_from_db(user_id)
await redis.setex(f"portfolio:{user_id}", 60, json.dumps(portfolio))
```

---

## Security

### API Credentials

**Storage**: Environment variables only
```bash
# NEVER commit to Git
ALPACA_API_KEY_ID=your_key
ALPACA_API_SECRET_KEY=your_secret
```

**Access**: Only server-side code
- Frontend never sees Alpaca credentials
- API endpoints require JWT authentication
- User isolation (can only see own portfolio)

---

### User Authorization

```python
@router.get("/")
async def get_portfolio(user=Depends(get_authenticated_user)):
    user_id = get_user_id(user)  # Extract from JWT
    # User can only access their own portfolio
    return await portfolio_service.get_user_portfolio(user_id)
```

---

## Future Enhancements

### 1. Multi-User Support

Currently syncs for single "demo" user. Enhance to:
```python
# Sync all active users on startup
users = await session.execute(select(User).where(User.is_active == True))
for user in users:
    await sync_service.sync_full_portfolio(user.id)
```

---

### 2. Periodic Background Sync

```python
async def background_sync_task():
    while True:
        await asyncio.sleep(300)  # 5 minutes
        users = await get_active_users()
        for user in users:
            await sync_service.sync_full_portfolio(user.id)
```

---

### 3. Real-Time Price Updates

Integrate Alpaca market data WebSocket:
```python
# Subscribe to price updates for portfolio symbols
async for bar in alpaca_data_stream:
    # Update position current_price in database
    # Recalculate unrealized P&L
    # Broadcast to user
```

---

### 4. Historical Portfolio Tracking

```python
# Store snapshot every hour
async def create_portfolio_snapshot():
    portfolio = await get_portfolio(user_id)
    snapshot = PortfolioHistory(
        user_id=user_id,
        timestamp=datetime.now(),
        total_equity=portfolio.total_equity,
        cash=portfolio.cash,
        positions=json.dumps(portfolio.positions)
    )
    await session.add(snapshot)
```

---

### 5. Sync Conflict Resolution

Handle cases where local and Alpaca data diverge:
```python
# Strategy: Alpaca is source of truth
# Always overwrite local data with Alpaca data during sync
# Log discrepancies for audit
if local_position.qty != alpaca_position.qty:
    logger.warning("Position quantity mismatch", 
                   symbol=symbol, local=local_qty, alpaca=alpaca_qty)
    # Use Alpaca value
```

---

## Migration Guide

### From Mock Data to Real Alpaca

**Step 1**: Get Alpaca credentials
- Sign up at https://app.alpaca.markets
- Enable paper trading
- Generate API keys

**Step 2**: Update environment
```bash
# .env file
USE_MOCK_BROKER=false
ALPACA_PAPER=true
ALPACA_API_KEY_ID=your_key_here
ALPACA_API_SECRET_KEY=your_secret_here
```

**Step 3**: Restart server
```bash
# Kill existing server
python main.py
```

**Step 4**: Verify sync
```bash
# Check logs
tail -f logs/app.log | grep "sync"

# Should see:
# INFO - Initial portfolio sync completed successfully
```

**Step 5**: Test dashboard
- Login to platform
- Navigate to dashboard
- Verify equity matches Alpaca dashboard
- Verify positions are correct

---

## Support

### Logs Location
```
logs/app.log - Main application logs
```

### Key Log Searches
```bash
# Sync activity
grep -i "sync" logs/app.log

# Alpaca API calls
grep -i "alpaca" logs/app.log

# Portfolio operations
grep -i "portfolio" logs/app.log

# Errors only
grep -i "error\|fail\|exception" logs/app.log
```

### Debug Mode
```bash
# Enable detailed logging
export LOG_LEVEL=DEBUG
python main.py
```

---

## Summary

✅ **Implemented**:
- Alpaca account data fetching
- Alpaca positions fetching  
- Portfolio sync service
- Database persistence
- API sync endpoint
- Startup auto-sync
- Smart caching (database)
- Error handling
- Comprehensive logging
- Test suite
- Documentation

✅ **Benefits**:
- Dashboard shows real Alpaca data
- Data persists across refreshes
- Automatic sync on startup
- Manual sync available
- WebSocket broadcasts updates
- Supports paper and live trading

✅ **Ready for**:
- Phase 1 Days 3-4: Orders implementation
- Real paper trading
- Production deployment (with proper security review)

---

**Next Steps**: Test with your real Alpaca paper account and verify dashboard shows your actual positions!
